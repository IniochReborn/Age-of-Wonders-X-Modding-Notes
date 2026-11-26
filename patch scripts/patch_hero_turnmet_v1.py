r"""
!! SUPERSEDED by patch_hero_turnmet_v2.py - DO NOT APPLY: tag 0x60 collides with ability record tags
!! (0x32 + ability id) -> garbage Turn Met on old saves + blank leader in Leader customization (user 10/22).
Hero "Turn Met" storage (2026-10-22, for 1.37.422).  AoWEPACK.dll only.  Pairs with patch_exe_realm_heroes_cols_v1.py
(the Realm window Heroes tab shows the value).

Field: word THero+0x9A (bytes 0x99..0x9B are unused by every module; byte 0x98 is used, TLeader fields start at 0x9C).
  0xFFFF = unknown (hero from a pre-422 save / map heroes not owned by a player) -> shown "-"
  0      = map hero of a game started in 422+ (never changed owner)             -> shown "1"
  N      = the turn ([map+0x174]) the hero joined its CURRENT owner             -> shown "N"

1. STREAM  THero.ReadWrite @0x55788B02 (`lea edx,[edi+0x50]; mov ecx,0x27`, 8 B) -> cave: new tag 0x60 via the stream's
   rwWord (vmt +0x34) on the value+1:  inc word [hero+0x9A]; rwWord(&[hero+0x9A], 0x60); dec word [hero+0x9A].
   Read: a missing tag reads 0 (TEReadStorageStream.rwWord 0x55510FE4) -> 0-1 = 0xFFFF = unknown; a stored T+1 -> T.
   Write: 0xFFFF+1 = 0 is skipped by the writer (0x555101D0 never writes zero words) -> stays "unknown" on reload;
   every real value (0..0xFFFE) is written as 1..0xFFFF.  Compare streams (MP desync check) see the same +1 form on
   both sides.  Old builds simply ignore the unknown tag.
2. OWNER   THero.SetPlayer 0x557872D0 (vmt +0x16C; vanilla already returns when new == old owner) @0x557872DF
   (`cmp byte [esi+0x24],0xFF; je 0x5578733D`, 6 B) -> cave: if the new owner bl != 0xFF (not "none"/death), store
   clamp(turn [AoWHSMap+0x174], 1, 0xFFFE).  Covers hiring, dungeon/event/quest joins, resurrection and Animate Dead
   (SetPlayer from none), seduce/charm (from another owner), campaign transfer.  Death = SetPlayer(-1) -> untouched.
   The map global 0x558FA040 is read through a call/pop delta (rebase-safe).
3. NEW GAME  the three StartNewMap paths call through a reset that turns 0xFFFF into 0 for every hero in every
   player's hero list (map heroes of a fresh game read the tag-less .hsm as 0xFFFF):
     TTurnPlayerControl.StartNewMap    @0x55756F89  call TPlayerControl.StartNewMap 0x5575573C
     TSimultaniousPlayerControl.StartNewMap @0x55759363 call 0x5575573C
     TPBEMPlayerControl.StartNewMap    @0x55758B33  call DefaultStartMap 0x55756F30
   (loaded games use StartLoadedMap* -> never reset.)
Load safety: the owner byte [+0x24] is streamed directly (TAbstractUnit tag 0x2F, no SetPlayer), and SetPlayer
returns early when the owner does not change; if SetPlayer ran on a zero-initialised hero before its own ReadWrite,
the tag read afterwards overwrites the field anyway.  LIVE CHECK: reload a save and compare the column.

Zone AoWEPACK 0x55836000..0x55836400 (assigned; 'HTM1' header; verified zero + reloc-free).
Dry-run default; --apply / --revert / --dis.  Backup <game>\backup\AoWEPACK.dll.bak_turnmet.
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
from patch_airdeath_fix_v1 import relocs
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

DLL = game_file("AoWEPACK.dll")
BASE, V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x55836000, 0x55836400
MAGIC = b"HTM1"
CODE = ZONE + 0x10

MAPG = 0x558FA040                  # AoWE.AoWHSMap global
GETPLAYERS = 0x557544D0            # TPlayerList.GetPlayers(eax=list, edx=index)
TAG = 0x60
FIELD = 0x9A

RW_SITE, RW_OLD, RW_BACK = 0x55788B02, bytes.fromhex("8d5750b927000000"), 0x55788B0A
SP_SITE, SP_OLD = 0x557872DF, bytes.fromhex("807e24ff7458")
SP_SAME, SP_CONT = 0x5578733D, 0x557872E5
CALLS = ((0x55756F89, 0x5575573C), (0x55759363, 0x5575573C), (0x55758B33, 0x55756F30))


def rel(op, src, dst, n=5):
    return op + struct.pack("<i", dst - (src + n))


def build():
    """sequential blocks (each assembled at its own address); returns (zone bytes, entry addresses)"""
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    fmt = dict(F=FIELD, TAG=TAG, RW_BACK=RW_BACK, MAPG=MAPG, SP_SAME=SP_SAME, SP_CONT=SP_CONT, GP=GETPLAYERS,
               PC=0x5575573C, DSM=0x55756F30)
    blocks = [("rw", """
        inc word ptr [edi+{F:#x}]
        lea edx, [edi+{F:#x}]
        mov ecx, {TAG:#x}
        mov eax, esi
        mov ebx, dword ptr [eax]
        call dword ptr [ebx+0x34]
        dec word ptr [edi+{F:#x}]
        lea edx, [edi+0x50]
        mov ecx, 0x27
        jmp {RW_BACK:#x}
    """), ("sp", """
        cmp bl, 0xff
        je sp_tail
        push eax
        push ecx
        call sp_here
    sp_here:
        pop ecx
        sub ecx, sp_here
        mov eax, dword ptr [ecx+{MAPG:#x}]
        xor ecx, ecx
        test eax, eax
        je sp_clamp
        mov ecx, dword ptr [eax+0x174]
    sp_clamp:
        cmp ecx, 1
        jge sp_lo
        mov ecx, 1
    sp_lo:
        cmp ecx, 0xfffe
        jle sp_store
        mov ecx, 0xfffe
    sp_store:
        mov word ptr [esi+{F:#x}], cx
        pop ecx
        pop eax
    sp_tail:
        cmp byte ptr [esi+0x24], 0xff
        je {SP_SAME:#x}
        jmp {SP_CONT:#x}
    """), ("reset", """
        pushad
        call rs_here
    rs_here:
        pop ebp
        sub ebp, rs_here
        mov eax, dword ptr [ebp+{MAPG:#x}]
        test eax, eax
        je rs_done
        mov edi, dword ptr [eax+0x140]
        test edi, edi
        je rs_done
        mov eax, edi
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x54]
        mov esi, eax
        xor ebx, ebx
    rs_player:
        cmp ebx, esi
        jge rs_done
        mov eax, edi
        mov edx, ebx
        call {GP:#x}
        test eax, eax
        je rs_next
        mov eax, dword ptr [eax+0x80]
        test eax, eax
        je rs_next
        mov eax, dword ptr [eax+8]
        test eax, eax
        je rs_next
        mov ecx, dword ptr [eax+8]
        mov edx, dword ptr [eax+4]
    rs_hero:
        test ecx, ecx
        jle rs_next
        dec ecx
        mov eax, dword ptr [edx+ecx*4]
        test eax, eax
        je rs_hero
        cmp word ptr [eax+{F:#x}], 0xffff
        jne rs_hero
        mov word ptr [eax+{F:#x}], 0
        jmp rs_hero
    rs_next:
        inc ebx
        jmp rs_player
    rs_done:
        popad
        ret
    """), ("new_pc", """
        call {PC:#x}
        jmp {RESET:#x}
    """), ("new_dsm", """
        call {DSM:#x}
        jmp {RESET:#x}
    """)]
    code = b""; ent = {}
    for name, src in blocks:
        at = CODE + len(code)
        ent[name] = at
        fmt["RESET"] = ent.get("reset", 0)
        enc, _ = ks.asm(src.format(**fmt), at)
        code += bytes(enc)
        code += b"\xcc" * (-len(code) % 4)
    zone = MAGIC + bytes(12) + code
    assert len(zone) <= ZONE_END - ZONE, hex(len(zone))
    return zone, {k: ent[k] for k in ("rw", "sp", "new_pc", "new_dsm")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true"); ap.add_argument("--dll", default=DLL)
    a = ap.parse_args()
    if a.apply:
        print('ABORT: SUPERSEDED - refusing to apply v1 (tag 0x60 collides with ability records); use patch_hero_turnmet_v2.py')
        return 1
    d = bytearray(open(a.dll, "rb").read())
    rd = lambda lo, n: bytes(d[lo - V2F:lo - V2F + n])
    zone, ent = build()
    new = {RW_SITE: rel(b"\xe9", RW_SITE, ent["rw"]) + b"\x90" * 3,
           SP_SITE: rel(b"\xe9", SP_SITE, ent["sp"]) + b"\x90"}
    old = {RW_SITE: RW_OLD, SP_SITE: SP_OLD}
    for site, tgt in CALLS:
        old[site] = rel(b"\xe8", site, tgt)
        new[site] = rel(b"\xe8", site, ent["new_dsm"] if tgt == 0x55756F30 else ent["new_pc"])
    st = {}
    for s in old:
        cur = rd(s, len(old[s]))
        st[s] = "v1" if cur == new[s] else "vanilla" if cur == old[s] else "OTHER " + cur.hex()
    zl = rd(ZONE, ZONE_END - ZONE)
    zst = "v1" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else "zero" if not any(zl) else "OTHER"
    rl = relocs(bytes(d), BASE)
    bad = [hex(r) for r in rl if ZONE - 3 <= r < ZONE_END or any(s - 3 <= r < s + len(old[s]) for s in old)]
    print("sites: " + ", ".join("%#x %s" % (s, st[s]) for s in sorted(st)))
    print("zone %#x %s (%d B) | relocs at sites/zone %s" % (ZONE, zst, len(zone), bad or "none"))
    print("entries: " + ", ".join("%s %#x" % kv for kv in ent.items()))
    if a.dis:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
        for i in Cs(CS_ARCH_X86, CS_MODE_32).disasm(zone[0x10:], CODE):
            print("  %08X  %-22s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad:
        print("ABORT: relocation entries under patched bytes"); return 1
    states = set(st.values())
    if a.revert:
        if states == {"vanilla"} and zst == "zero":
            print("already reverted"); return 0
        if states != {"v1"} or zst != "v1":
            print("ABORT: not in the v1 state - refusing a partial revert"); return 1
        for s in old: d[s - V2F:s - V2F + len(old[s])] = old[s]
        d[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE)
    else:
        if states == {"v1"} and zst == "v1":
            print("already applied"); return 0
        if states != {"vanilla"} or zst != "zero":
            print("ABORT: unexpected state (sites must be vanilla and the zone zero)"); return 1
        d[ZONE - V2F:ZONE - V2F + len(zone)] = zone
        for s in new: d[s - V2F:s - V2F + len(new[s])] = new[s]
    if not (a.apply or a.revert):
        print("Dry run OK - rerun with --apply."); return 0
    bak = bak_path(a.dll, ".bak_turnmet")
    if a.apply and not os.path.exists(bak):
        shutil.copy2(a.dll, bak); print("backup ->", bak)
    with open(a.dll, "r+b") as f:
        f.seek(0); f.write(d)
    print("reverted" if a.revert else "applied")
    return 0


if __name__ == "__main__":
    sys.exit(main())
