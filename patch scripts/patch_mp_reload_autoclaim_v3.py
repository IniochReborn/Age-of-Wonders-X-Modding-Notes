r"""
MP reload auto-claim v3 (2026-10-22).  AoWEPACK.dll only.  Upgrades autoclaim v1 or v2 in place.

v2 live probe (host re-hosted X\Save\autosave.asg, save marker 2, two humans): the table held 'Elf' / 'Dark Elf' =
the MAP's default leader templates ([[p+0x58]+0x60]); [p+0xD4] and [p+0x4C] gave nothing.  The decompressed save holds
'Peewee the Peony' / 'Peewee the Peony2' only inside the live TLeader unit objects (class id 0x20232 streamed right
before each name; 5 TLeader objects for 5 players) - a normal save does not stream the player's leader reference
(TPlayer.ReadWrite tag 0x13 is gated on stream flag 4), the leader is relinked from the units after load.
v3 name sources, in priority passes over all saved humans (status != 2, [p+0xA7]==0):
  pass 0  the first TLeader-class unit (vcall ClassID +0x24 == 0x20232) in the player's armies:
          army list [p+0x28] (count vcall +0x54, TArmyList.GetArmy 0x55750808), units [[army+8]+4][j]
          (count vcall +0x54) - the same walk vanilla TArmy.Leader does, but WITHOUT calling TArmy.Leader (Leader Soul
          hooks it and can return a soul vessel)
  pass 1  the first TLeader-class hero in the loaded map's hero control [map+0xF8] (THeroControl.GetCount
          0x5578A3CC / GetHero 0x5578A3BC) whose owner byte [hero+0x24] == [p+0xA6]
  pass 2  [[p+0xD4]+0x60]   pass 3  [[p+0x58]+0x60] (map template, last resort)   pass 4  [p+0x4C]
  -> up to 13 table entries {name, slot index}; every source is tried, AutoClaim matches any of them.
diag DATA 0x558E9F78: +0 players iterated, +1 saved humans, +2 table entries, +3 pick runs (wraps),
  +4 pass-0 hits (army TLeader), +5 pass-1 hits (hero control), +6 pass-2 hits ([p+0xD4]), +7 pass-3/4 hits.
Unchanged from v2: hooks 0x557E23EA / 0x557DFD57 / 0x557DFEC1, zone 0x55836400..0x55836800 ('MRA3'), table
0x558E9F10 (13 x 8 B), AutoClaim (host only, only while the pick is a save, explicit picks win, seated players skipped,
vanilla gate (rec+0x19 & 3)==0), AI slots stay CPU Emperor, SP untouched.
Dry-run default; --apply (from vanilla, v1 or v2) / --revert (to vanilla) / --dis.  Backup .bak_mpautoclaim3.
ALWAYS use --dll <scratch copy> for apply/revert tests - --revert WRITES.
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
from patch_airdeath_fix_v1 import relocs
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
import patch_mp_reload_autoclaim_v1 as v1
import patch_mp_reload_autoclaim_v2 as v2

DLL = game_file("AoWEPACK.dll")
BASE, V2F = v1.BASE, v1.V2F
ZONE, ZONE_END, CODE = v1.ZONE, v1.ZONE_END, v1.CODE
MAGIC = b"MRA3"
TAB, N = v1.TAB, v1.N
DIAG = 0x558E9F78
SITES = v1.SITES
E = dict(GET_REMOTE=v1.GET_REMOTE, UPDATE_SETTINGS=v1.UPDATE_SETTINGS, UPDATE_PREF=v1.UPDATE_PREF,
         GET_SETTINGS=v1.GET_SETTINGS, INDEX_OF_RACE=v1.INDEX_OF_RACE, INDEX_OF_REMOTEID=v1.INDEX_OF_REMOTEID,
         REMOTE_GETPLAYERS=v1.REMOTE_GETPLAYERS, PLAYERLIST_GETPLAYERS=v1.PLAYERLIST_GETPLAYERS,
         LSTR_ASG=v1.LSTR_ASG, LSTR_CLR=v1.LSTR_CLR,
         GET_ARMY=0x55750808, HC_COUNT=0x5578A3CC, HC_HERO=0x5578A3BC)
CID_TLEADER = 0x20232


def asm_src():
    e = {k: "%#x" % v for k, v in E.items()}
    # locals in pick (after sub esp,12): [esp] player count, [esp+4] i, [esp+8] pass; entries k = byte [DIAG+2]
    return f"""
    pick:
        pushad
        call getdelta
        lea esi, [edi + {TAB:#x}]
        inc byte ptr [edi + {DIAG + 3:#x}]
        mov word ptr [edi + {DIAG:#x}], 0
        mov byte ptr [edi + {DIAG + 2:#x}], 0
        mov dword ptr [edi + {DIAG + 4:#x}], 0
        xor ecx, ecx
    pk_clr:
        push ecx
        lea eax, [esi + ecx*8]
        call {e['LSTR_CLR']}
        pop ecx
        mov dword ptr [esi + ecx*8 + 4], 0
        inc ecx
        cmp ecx, {N}
        jb pk_clr
        mov eax, ebx
        call {e['GET_REMOTE']}
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
        mov dword ptr [esp + 8], 0
    pk_pass:
        mov dword ptr [esp + 4], 1
    pk_loop:
        mov eax, dword ptr [esp + 4]
        cmp eax, dword ptr [esp]
        jge pk_endpass
        cmp byte ptr [edi + {DIAG + 2:#x}], {N}
        jae pk_end
        mov edx, eax
        mov eax, dword ptr [ebp - 0xc]
        mov eax, dword ptr [eax + 0x140]
        call {e['PLAYERLIST_GETPLAYERS']}
        test eax, eax
        je pk_next
        cmp dword ptr [esp + 8], 0
        jne pk_nocount
        inc byte ptr [edi + {DIAG:#x}]
    pk_nocount:
        cmp byte ptr [eax + 0x45], 2
        je pk_next
        cmp byte ptr [eax + 0xa7], 0
        jne pk_next
        mov ecx, dword ptr [esp + 8]
        test ecx, ecx
        jne pk_p1
        inc byte ptr [edi + {DIAG + 1:#x}]
        call fla
        jmp pk_have
    pk_p1:
        cmp ecx, 1
        jne pk_p2
        mov edx, dword ptr [ebp - 0xc]
        call flh
        jmp pk_have
    pk_p2:
        cmp ecx, 2
        jne pk_p3
        mov eax, dword ptr [eax + 0xd4]
        jmp pk_obj
    pk_p3:
        cmp ecx, 3
        jne pk_p4
        mov eax, dword ptr [eax + 0x58]
    pk_obj:
        test eax, eax
        je pk_next
        mov eax, dword ptr [eax + 0x60]
        jmp pk_have
    pk_p4:
        mov eax, dword ptr [eax + 0x4c]
    pk_have:
        test eax, eax
        je pk_next
        mov edx, eax
        movzx ecx, byte ptr [edi + {DIAG + 2:#x}]
        lea eax, [esi + ecx*8]
        call {e['LSTR_ASG']}
        movzx ecx, byte ptr [edi + {DIAG + 2:#x}]
        mov eax, dword ptr [esp + 4]
        mov byte ptr [esi + ecx*8 + 4], al
        inc byte ptr [edi + {DIAG + 2:#x}]
        mov ecx, dword ptr [esp + 8]
        cmp ecx, 3
        jbe pk_cnt
        mov ecx, 3
    pk_cnt:
        inc byte ptr [edi + ecx + {DIAG + 4:#x}]
    pk_next:
        inc dword ptr [esp + 4]
        jmp pk_loop
    pk_endpass:
        inc dword ptr [esp + 8]
        cmp dword ptr [esp + 8], 5
        jb pk_pass
    pk_end:
        add esp, 12
        call autoclaim
        test al, al
        je pk_done
        mov eax, ebx
        call {e['UPDATE_PREF']}
    pk_done:
        popad
        mov eax, ebx
        call {e['UPDATE_SETTINGS']}
        jmp {SITES["pick"][2]:#x}

    fla:
        push ebx
        push esi
        push edi
        push ebp
        mov ebx, eax
        mov esi, dword ptr [ebx + 0x28]
        test esi, esi
        je fla_none
        mov eax, esi
        mov edx, dword ptr [eax]
        call dword ptr [edx + 0x54]
        mov edi, eax
        xor ebp, ebp
    fla_a:
        cmp ebp, edi
        jge fla_none
        mov edx, ebp
        mov eax, esi
        call {e['GET_ARMY']}
        inc ebp
        test eax, eax
        je fla_a
        push eax
        push 0
        mov edx, dword ptr [eax]
        call dword ptr [edx + 0x54]
        push eax
    fla_u:
        mov ecx, dword ptr [esp + 4]
        cmp ecx, dword ptr [esp]
        jge fla_upop
        inc dword ptr [esp + 4]
        mov eax, dword ptr [esp + 8]
        mov eax, dword ptr [eax + 8]
        mov eax, dword ptr [eax + 4]
        mov eax, dword ptr [eax + ecx*4]
        test eax, eax
        je fla_u
        push eax
        mov edx, dword ptr [eax]
        call dword ptr [edx + 0x24]
        pop edx
        cmp eax, {CID_TLEADER:#x}
        jne fla_u
        mov eax, dword ptr [edx + 0x60]
        test eax, eax
        je fla_u
        add esp, 12
        jmp fla_out
    fla_upop:
        add esp, 12
        jmp fla_a
    fla_none:
        xor eax, eax
    fla_out:
        pop ebp
        pop edi
        pop esi
        pop ebx
        ret

    flh:
        push ebx
        push esi
        push edi
        push ebp
        mov ebx, eax
        mov esi, dword ptr [edx + 0xf8]
        test esi, esi
        je flh_none
        mov eax, esi
        call {e['HC_COUNT']}
        mov edi, eax
        xor ebp, ebp
    flh_l:
        cmp ebp, edi
        jge flh_none
        mov edx, ebp
        mov eax, esi
        call {e['HC_HERO']}
        inc ebp
        test eax, eax
        je flh_l
        push eax
        mov edx, dword ptr [eax]
        call dword ptr [edx + 0x24]
        pop edx
        cmp eax, {CID_TLEADER:#x}
        jne flh_l
        mov al, byte ptr [edx + 0x24]
        cmp al, byte ptr [ebx + 0xa6]
        jne flh_l
        mov eax, dword ptr [edx + 0x60]
        test eax, eax
        je flh_l
        jmp flh_out
    flh_none:
        xor eax, eax
    flh_out:
        pop ebp
        pop edi
        pop esi
        pop ebx
        ret

    conn:
        call autoclaim
        test al, al
        je cn_1
        mov eax, ebx
        call {e['UPDATE_PREF']}
    cn_1:
        mov eax, ebx
        call {e['UPDATE_SETTINGS']}
        jmp {SITES["conn"][2]:#x}

    upd:
        call autoclaim
        mov eax, ebx
        call {e['UPDATE_PREF']}
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
        call {e['REMOTE_GETPLAYERS']}
        test eax, eax
        je ac_next
        mov ebp, eax
        cmp byte ptr [ebp + 0x10], 0xff
        jne ac_next
        mov edx, dword ptr [ebp + 0xc]
        mov eax, dword ptr [ebx + 0x28]
        call {e['INDEX_OF_REMOTEID']}
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
        push ecx
        push edx
        mov eax, dword ptr [ebx + 0x28]
        call {e['INDEX_OF_RACE']}
        cmp eax, -1
        je ac_pop
        mov edx, eax
        mov eax, dword ptr [ebx + 0x28]
        call {e['GET_SETTINGS']}
        test eax, eax
        je ac_pop
        cmp dword ptr [eax + 0xc], 0
        jne ac_pop
        test byte ptr [eax + 0x19], 3
        jne ac_pop
        pop edx
        pop ecx
        mov byte ptr [ebp + 0x10], dl
        mov dword ptr [esp + 8], 1
        jmp ac_next
    ac_pop:
        pop edx
        pop ecx
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
    code, _ = ks.asm(asm_src() + "".join("    .long %s\n" % n for n in names), CODE)
    code = bytes(code)
    labels = dict(zip(names, struct.unpack("<3I", code[-12:])))
    zone = MAGIC + bytes(12) + code[:-12]
    assert len(zone) <= ZONE_END - ZONE, hex(len(zone))
    return zone, labels


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true"); ap.add_argument("--dll", default=DLL)
    a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read())
    rd = lambda lo, n: bytes(d[lo - V2F:lo - V2F + n])
    zone, ent = build()
    known = {"v3": (zone, ent), "v2": v2.build(), "v1": v1.build()}
    assert DIAG + 8 <= 0x558E9F80 and TAB + N * 8 <= DIAG

    def state():
        zl = rd(ZONE, ZONE_END - ZONE)
        sites = [rd(va, 7) for va, _, _ in SITES.values()]
        for name, (z, en) in known.items():
            if all(s == v1.site_jmp(va, en[k]) for s, (k, (va, _, _)) in zip(sites, SITES.items()))                     and zl[:len(z)] == z and not any(zl[len(z):]):
                return name
        if all(s == orig for s, (_, orig, _) in zip(sites, SITES.values())) and not any(zl):
            return "vanilla"
        return "OTHER"

    st = state()
    rl = relocs(bytes(d), BASE)
    bad = [hex(r) for r in rl if ZONE - 3 <= r < ZONE_END or any(va - 3 <= r < va + 7 for va, _, _ in SITES.values())]
    print("state %s | zone %#x (%d B, entries %s) | table %#x x%d, diag %#x | relocs at sites %s"
          % (st, ZONE, len(zone), " ".join("%s=%#x" % kv for kv in ent.items()), TAB, N, DIAG, bad or "none"))
    if a.dis:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
        inv = {v: k for k, v in ent.items()}
        for i in Cs(CS_ARCH_X86, CS_MODE_32).disasm(zone[0x10:], CODE):
            if i.address in inv: print("  ; ---- %s" % inv[i.address])
            print("  %08X  %-20s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad:
        print("ABORT: relocation entries under patched bytes"); return 1
    if a.revert:
        if st == "vanilla":
            print("already reverted"); return 0
        if st not in ("v1", "v2", "v3"):
            print("ABORT: unknown state - refusing a partial revert"); return 1
        for va, orig, _ in SITES.values(): d[va - V2F:va - V2F + 7] = orig
        d[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE)
    else:
        if st == "v3":
            print("already applied"); return 0
        if st not in ("vanilla", "v1", "v2"):
            print("ABORT: unexpected state (needs vanilla or autoclaim v1/v2)"); return 1
        d[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE)
        d[ZONE - V2F:ZONE - V2F + len(zone)] = zone
        for k, (va, _, _) in SITES.items(): d[va - V2F:va - V2F + 7] = v1.site_jmp(va, ent[k])
    if not (a.apply or a.revert):
        print("Dry run OK (%s -> %s) - rerun with --apply." % (st, "vanilla" if a.revert else "v3")); return 0
    bak = bak_path(a.dll, ".bak_mpautoclaim3")
    if a.apply and not os.path.exists(bak):
        shutil.copy2(a.dll, bak); print("backup ->", bak)
    with open(a.dll, "r+b") as f:
        f.seek(0); f.write(d)
    print("reverted" if a.revert else "applied")
    return 0


if __name__ == "__main__":
    sys.exit(main())
