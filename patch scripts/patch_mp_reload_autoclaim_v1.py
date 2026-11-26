r"""
MP reload: the lobby remembers each human's race (2026-10-22, for 1.37.422).  AoWEPACK.dll only.

User: re-hosting a saved multiplayer game makes everyone re-assign their races.  Vanilla hPickMap 0x557E20C8 resets
every remote player's preferred race to 0xFF and (networked, our mprace patch) builds every non-map-assigned slot as
CPU Emperor, ignoring the save's human flag [player+0xA7]==0.  The save has no lobby-name field, but SetupMap writes
the claiming player's lobby name into the leader hero's name [[player+0xD4]+0x60] (loaded games / customize off; with
customize on the customized name is also saved as the lobby name - customize-name-registry), so leader name == lobby
name.  RE + design: memory mp-reload-remember-races.

Design (host-authoritative; the result reaches every machine through the vanilla UpdateSettings broadcast):
  PICK  hPickMap @0x557E23EA (`mov eax,ebx; call UpdateSettings`) -> cave: clear the name table; if networked
        (GetRemote) and the picked file is a save ([settings+0x20]!=0): for each saved player index 1..n-1 with status
        [p+0x45]!=2 and [p+0xA7]==0 (human) store {leader name ([[p+0xD4]+0x60], or [p+0x4C] without a leader), index};
        AutoClaim; if it set anything -> UpdatePreferredRaces; then the displaced UpdateSettings, back to 0x557E23F1.
        A virgin map leaves the table empty -> no stale claims.
  CONN  hConnectPlayer @0x557DFD57 (`mov eax,ebx; call UpdateSettings`) -> AutoClaim (+UpdatePreferredRaces if it set
        anything) for players who join after the pick; UpdateSettings; back to 0x557DFD5E.
  UPD   hUpdatePlayer @0x557DFEC1 (`mov eax,ebx; call UpdatePreferredRaces`) -> AutoClaim, then the displaced
        UpdatePreferredRaces; back to 0x557DFEC8 (a client update carrying pref 0xFF would otherwise release the seat).
  AutoClaim (only while the picked map is a save, [settings+0x20]!=0, so a table left over from an earlier pick
        never seats anyone on a virgin map): for every remote player (TSetupSettings+0x38) whose preferred race [rp+0x10]==0xFF (an explicit pick
        always wins) and who holds no seat yet (IndexOfRemoteID == -1), find a table entry whose name equals [rp+8]
        (ASCII case-insensitive); if that slot's record is unclaimed ([rec+0xC]==0) and not Forced ([rec+0x19]&2),
        set [rp+0x10] = slot index.  The vanilla UpdatePreferredRaces then claims it exactly like a manual pick, so
        hValidateSetupMap / the mpreload customize fix see nothing new.  AI slots stay CPU Emperor (user: no AI-level
        restore).  Hotseat (not networked) and PBEM (hPickMap bails) are untouched.

Code zone AoWEPACK 0x55836400..0x55836800 ('MRA1' header; assigned by the coordinator, verified zero + reloc-free).
Name table (writable): AoWEPACK DATA zero-fill slack 0x558E9F10..0x558E9F78 = 13 x {AnsiString name, byte index, 3 pad}
  - CODE is not writable (0x60000020); DATA (0xC0000040) raw ends 0x558E9C00, BSS starts 0x558EA000.
  - claimed DATA slack around it: steadfast TAB 0x558E9E00 + idx dword 0x558E9F00, Second Wind FM_TAB 0x558E9F80,
    Miracle 0x558E9FC0; nothing else names 0x558E9F04..0x558E9F7F.  Not in the 421 MPH1 reset ranges (.idata).
  - runtime-only zero-fill, never saved; strings are refcounted via LStrAsg/LStrClr.
All data reached via a call/pop delta (rebase-safe); all calls rel32.
Dry-run default; --apply / --revert / --dis.  Backup <game>\backup\AoWEPACK.dll.bak_mpautoclaim.
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
from patch_airdeath_fix_v1 import relocs
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

DLL = game_file("AoWEPACK.dll")
BASE, V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x55836400, 0x55836800
CODE = ZONE + 0x10
MAGIC = b"MRA1"
TAB, N = 0x558E9F10, 13                    # 8-byte entries: +0 AnsiString name, +4 slot index byte
DATA_RAW_END, BSS = 0x558E9C00, 0x558EA000

# engine
GET_REMOTE, UPDATE_SETTINGS, UPDATE_PREF = 0x557E125C, 0x557E11FC, 0x557E1484
GET_SETTINGS, INDEX_OF_RACE, INDEX_OF_REMOTEID = 0x557DF5F4, 0x557DF668, 0x557DF63C
REMOTE_GETPLAYERS, PLAYERLIST_GETPLAYERS = 0x557DF3C8, 0x557544D0
LSTR_ASG, LSTR_CLR = 0x55701150, 0x55701140

SITES = {   # name: (va, original 7 bytes, resume va)
    "pick": (0x557E23EA, bytes.fromhex("8bc3e80beeffff"), 0x557E23F1),
    "conn": (0x557DFD57, bytes.fromhex("8bc3e89e140000"), 0x557DFD5E),
    "upd":  (0x557DFEC1, bytes.fromhex("8bc3e8bc150000"), 0x557DFEC8),
}


def asm_src():
    return f"""
    pick:
        pushad
        call getdelta
        lea esi, [edi + {TAB:#x}]
        xor ecx, ecx
    pk_clr:
        push ecx
        lea eax, [esi + ecx*8]
        call {LSTR_CLR:#x}
        pop ecx
        mov dword ptr [esi + ecx*8 + 4], 0
        inc ecx
        cmp ecx, {N}
        jb pk_clr
        mov eax, ebx
        call {GET_REMOTE:#x}
        test al, al
        je pk_done
        mov eax, dword ptr [ebx + 0x28]
        cmp dword ptr [eax + 0x20], 0
        je pk_done
        mov eax, dword ptr [ebp - 0xc]
        mov eax, dword ptr [eax + 0x140]
        mov edx, dword ptr [eax]
        call dword ptr [edx + 0x54]
        sub esp, 12
        mov dword ptr [esp], eax
        mov dword ptr [esp + 4], 1
        mov dword ptr [esp + 8], 0
    pk_loop:
        mov eax, dword ptr [esp + 4]
        cmp eax, dword ptr [esp]
        jge pk_end
        cmp dword ptr [esp + 8], {N}
        jge pk_end
        mov edx, eax
        mov eax, dword ptr [ebp - 0xc]
        mov eax, dword ptr [eax + 0x140]
        call {PLAYERLIST_GETPLAYERS:#x}
        test eax, eax
        je pk_next
        cmp byte ptr [eax + 0x45], 2
        je pk_next
        cmp byte ptr [eax + 0xa7], 0
        jne pk_next
        mov edx, dword ptr [eax + 0xd4]
        test edx, edx
        je pk_noleader
        mov edx, dword ptr [edx + 0x60]
        jmp pk_have
    pk_noleader:
        mov edx, dword ptr [eax + 0x4c]
    pk_have:
        test edx, edx
        je pk_next
        mov ecx, dword ptr [esp + 8]
        lea eax, [esi + ecx*8]
        call {LSTR_ASG:#x}
        mov ecx, dword ptr [esp + 8]
        mov eax, dword ptr [esp + 4]
        mov byte ptr [esi + ecx*8 + 4], al
        inc dword ptr [esp + 8]
    pk_next:
        inc dword ptr [esp + 4]
        jmp pk_loop
    pk_end:
        add esp, 12
        call autoclaim
        test al, al
        je pk_done
        mov eax, ebx
        call {UPDATE_PREF:#x}
    pk_done:
        popad
        mov eax, ebx
        call {UPDATE_SETTINGS:#x}
        jmp {SITES["pick"][2]:#x}

    conn:
        call autoclaim
        test al, al
        je cn_1
        mov eax, ebx
        call {UPDATE_PREF:#x}
    cn_1:
        mov eax, ebx
        call {UPDATE_SETTINGS:#x}
        jmp {SITES["conn"][2]:#x}

    upd:
        call autoclaim
        mov eax, ebx
        call {UPDATE_PREF:#x}
        jmp {SITES["upd"][2]:#x}

    getdelta:
        call gd_here
    gd_here:
        pop edi
        sub edi, gd_here
        ret

    autoclaim:
        pushad
        mov eax, dword ptr [ebx + 0x28]
        cmp dword ptr [eax + 0x20], 0
        jne ac_go
        mov dword ptr [esp + 28], 0
        popad
        ret
    ac_go:
        call getdelta
        lea esi, [edi + {TAB:#x}]
        mov eax, dword ptr [ebx + 0x28]
        mov eax, dword ptr [eax + 0x38]
        mov edx, dword ptr [eax]
        call dword ptr [edx + 0x54]
        push 0
        push eax
        push 0
    ac_loop:
        mov eax, dword ptr [esp]
        cmp eax, dword ptr [esp + 4]
        jge ac_end
        mov edx, eax
        mov eax, dword ptr [ebx + 0x28]
        mov eax, dword ptr [eax + 0x38]
        call {REMOTE_GETPLAYERS:#x}
        test eax, eax
        je ac_next
        mov ebp, eax
        cmp byte ptr [ebp + 0x10], 0xff
        jne ac_next
        mov edx, dword ptr [ebp + 0xc]
        mov eax, dword ptr [ebx + 0x28]
        call {INDEX_OF_REMOTEID:#x}
        cmp eax, -1
        jne ac_next
        xor ecx, ecx
    ac_k:
        cmp ecx, {N}
        jae ac_next
        mov edx, dword ptr [esi + ecx*8]
        mov eax, dword ptr [ebp + 8]
        push ecx
        call strieq
        pop ecx
        test al, al
        je ac_knext
        movzx edx, byte ptr [esi + ecx*8 + 4]
        push edx
        mov eax, dword ptr [ebx + 0x28]
        call {INDEX_OF_RACE:#x}
        cmp eax, -1
        je ac_pop
        mov edx, eax
        mov eax, dword ptr [ebx + 0x28]
        call {GET_SETTINGS:#x}
        test eax, eax
        je ac_pop
        cmp dword ptr [eax + 0xc], 0
        jne ac_pop
        test byte ptr [eax + 0x19], 2
        jne ac_pop
        pop edx
        mov byte ptr [ebp + 0x10], dl
        mov dword ptr [esp + 8], 1
        jmp ac_next
    ac_pop:
        pop edx
        jmp ac_next
    ac_knext:
        inc ecx
        jmp ac_k
    ac_next:
        inc dword ptr [esp]
        jmp ac_loop
    ac_end:
        mov eax, dword ptr [esp + 8]
        add esp, 12
        mov dword ptr [esp + 28], eax
        popad
        ret

    strieq:
        test eax, eax
        je se_no
        test edx, edx
        je se_no
        mov ecx, dword ptr [eax - 4]
        cmp ecx, dword ptr [edx - 4]
        jne se_no
        push ebx
    se_l:
        test ecx, ecx
        je se_yes
        dec ecx
        mov bl, byte ptr [eax + ecx]
        mov bh, byte ptr [edx + ecx]
        cmp bl, 0x61
        jb se_f1
        cmp bl, 0x7a
        ja se_f1
        sub bl, 0x20
    se_f1:
        cmp bh, 0x61
        jb se_f2
        cmp bh, 0x7a
        ja se_f2
        sub bh, 0x20
    se_f2:
        cmp bl, bh
        je se_l
        pop ebx
    se_no:
        xor eax, eax
        ret
    se_yes:
        pop ebx
        mov eax, 1
        ret
    """


def build():
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    names = ("pick", "conn", "upd")
    # keystone exports no labels: append .long probes for the entry points, read them back, then drop them
    code, _ = ks.asm(asm_src() + "".join("    .long %s\n" % n for n in names), CODE)
    code = bytes(code)
    labels = dict(zip(names, struct.unpack("<3I", code[-12:])))
    code = code[:-12]
    zone = MAGIC + bytes(12) + code
    assert len(zone) <= ZONE_END - ZONE, hex(len(zone))
    return zone, labels


def site_jmp(va, dst):
    return b"\xe9" + struct.pack("<i", dst - (va + 5)) + b"\x90\x90"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true"); ap.add_argument("--dll", default=DLL)
    a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read())
    rd = lambda lo, n: bytes(d[lo - V2F:lo - V2F + n])
    zone, ent = build()
    assert DATA_RAW_END <= TAB and TAB + N * 8 <= 0x558E9F80 and TAB + N * 8 < BSS

    states = {}
    for k, (va, orig, _) in SITES.items():
        cur = rd(va, 7)
        states[k] = "v1" if cur == site_jmp(va, ent[k]) else "vanilla" if cur == orig else "OTHER " + cur.hex()
    zl = rd(ZONE, ZONE_END - ZONE)
    zst = "v1" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else "zero" if not any(zl) else "OTHER"
    rl = relocs(bytes(d), BASE)
    bad = [hex(r) for r in rl if ZONE - 3 <= r < ZONE_END or any(va - 3 <= r < va + 7 for va, _, _ in SITES.values())]
    print("sites %s | zone %#x %s (%d B, entries %s) | table %#x x%d | relocs at sites %s"
          % (", ".join("%s %s" % kv for kv in states.items()), ZONE, zst, len(zone),
             " ".join("%s=%#x" % kv for kv in ent.items()), TAB, N, bad or "none"))
    if a.dis:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
        inv = {v: k for k, v in ent.items()}
        for i in Cs(CS_ARCH_X86, CS_MODE_32).disasm(zone[0x10:], CODE):
            if i.address in inv: print("  ; ---- %s" % inv[i.address])
            print("  %08X  %-20s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad:
        print("ABORT: relocation entries under patched bytes"); return 1
    allst = set(states.values())
    if a.revert:
        if allst == {"vanilla"}:
            print("already reverted"); return 0
        if allst != {"v1"} or zst != "v1":
            print("ABORT: not in the v1 state - refusing a partial revert"); return 1
        for va, orig, _ in SITES.values(): d[va - V2F:va - V2F + 7] = orig
        d[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE)
    else:
        if allst == {"v1"} and zst == "v1":
            print("already applied"); return 0
        if allst != {"vanilla"} or zst != "zero":
            print("ABORT: unexpected state (sites must be vanilla, zone zero)"); return 1
        d[ZONE - V2F:ZONE - V2F + len(zone)] = zone
        for k, (va, _, _) in SITES.items(): d[va - V2F:va - V2F + 7] = site_jmp(va, ent[k])
    if not (a.apply or a.revert):
        print("Dry run OK - rerun with --apply."); return 0
    bak = bak_path(a.dll, ".bak_mpautoclaim")
    if a.apply and not os.path.exists(bak):
        shutil.copy2(a.dll, bak); print("backup ->", bak)
    with open(a.dll, "r+b") as f:
        f.seek(0); f.write(d)
    print("reverted" if a.revert else "applied")
    return 0


if __name__ == "__main__":
    sys.exit(main())
