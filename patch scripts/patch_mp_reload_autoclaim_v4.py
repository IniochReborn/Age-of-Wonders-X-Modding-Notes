r"""
MP reload auto-claim v4 (2026-10-22).  AoWEPACK.dll only.  Upgrades autoclaim v1 / v2 / v3 in place.

v3 live: all name sources empty in the lobby (army/hero-control TLeader 0 hits) - the lobby's load of a save never
materialises units; the player records (root tag 21, which the lobby DOES read through TPlayer.ReadWrite: race, number,
type) carry no name at all.  v4 makes the game SAVE the controlling human's lobby name in the TPlayer itself:
  (1) TPlayer.InstanceSize (VMT 0x5570C508 - 0x1C = 0x5570C4EC) 0xDC -> 0xE0: new AnsiString field TPlayer+0xDC
      (zero-initialised by NewInstance; no TPlayer subclasses anywhere; other modules import only TPlayer RStrs).
      Not in the class init table -> not finalised (a few bytes leak per destroyed player; refcounting otherwise normal).
  (2) TPlayer.ReadWrite hook @0x5575320C (`lea edx,[ebx+0xA6]`, 6 B): stream vcall +0x20 rwString(&[ebx+0xDC],
      tag 0x10061) for every mode.  Writer (TEWriteStorageStream.rwString 0x5551047C) skips empty strings and raises on a
      duplicate tag; reader (0x555111A8) clears the field when the tag is missing (pre-422 saves / maps -> ''); compare
      stream (0x55513198) compares - identical on every machine (names come from the synced lobby list / the same file).
      Tag 0x10061: real player tables carry 2 3 5 a 10 12 17 19 1c-24 27 33-36 3a (autosave.asg; highest 0x3a);
      offline model (ptab.py / turnmet_validate.py / pname_validate.py) shows all original offsets unchanged.
  (3) TSetupControl.SetupMap hook @0x557E0CFD (`cmp byte [eax+8],0; jne 0x557E0D57`, 6 B, inside its GetRemote branch,
      eax = slot record, esi = TPlayer): for a Human slot (rec+8 == 0) whose owner id rec+0xC is in the remote list,
      LStrAsg([esi+0xDC], remote name).  Runs on every machine of a networked game start (new or loaded), before the
      vanilla customize gate; hotseat/PBEM/SP never reach it.  An AI-taken slot keeps the name it was loaded with.
  (4) the hPickMap table builder: pass 0 [p+0xDC], pass 1 [[p+0xD4]+0x60], pass 2 [[p+0x58]+0x60], pass 3 [p+0x4C]
      (v3's army / hero-control walks dropped: proven empty in the lobby).
diag DATA 0x558E9F78: +0 players, +1 saved humans, +2 table entries, +3 pick runs, +4..+7 hits per pass 0..3.
Unchanged: hooks 0x557E23EA / 0x557DFD57 / 0x557DFEC1, zone 0x55836400..0x55836800 ('MRA4'), table 0x558E9F10,
AutoClaim (host only, save picks only, explicit picks win, seated players skipped, (rec+0x19 & 3)==0), AI stays Emperor.
Pre-422 saves cannot be helped (no name stored) - manual assignment as before.
Dry-run default; --apply (from vanilla, v1, v2 or v3) / --revert (to vanilla) / --dis.  Backup .bak_mpautoclaim4.
ALWAYS use --dll <scratch copy> for apply/revert tests - --revert WRITES.
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
from patch_airdeath_fix_v1 import relocs
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
import patch_mp_reload_autoclaim_v1 as v1
import patch_mp_reload_autoclaim_v2 as v2
import patch_mp_reload_autoclaim_v3 as v3

DLL = game_file("AoWEPACK.dll")
BASE, V2F = v1.BASE, v1.V2F
ZONE, ZONE_END, CODE = v1.ZONE, v1.ZONE_END, v1.CODE
MAGIC = b"MRA4"
TAB, N = v1.TAB, v1.N
DIAG = 0x558E9F78
SITES = v1.SITES
E = dict(GET_REMOTE=v1.GET_REMOTE, UPDATE_SETTINGS=v1.UPDATE_SETTINGS, UPDATE_PREF=v1.UPDATE_PREF,
         GET_SETTINGS=v1.GET_SETTINGS, INDEX_OF_RACE=v1.INDEX_OF_RACE, INDEX_OF_REMOTEID=v1.INDEX_OF_REMOTEID,
         REMOTE_GETPLAYERS=v1.REMOTE_GETPLAYERS, PLAYERLIST_GETPLAYERS=v1.PLAYERLIST_GETPLAYERS,
         LSTR_ASG=v1.LSTR_ASG, LSTR_CLR=v1.LSTR_CLR,
         REMOTE_INDEXOF=0x557DF3D4)
NAME_FIELD, NAME_TAG = 0xDC, 0x10061
ISZ_VA, ISZ_OLD, ISZ_NEW = 0x5570C4EC, 0xDC, 0xE0               # TPlayer VMT InstanceSize
XSITES = {  # extra 6-byte hooks: name: (va, original, resume)
    "rwname": (0x5575320C, bytes.fromhex("8d93a6000000"), 0x55753212),
    "smap":   (0x557E0CFD, bytes.fromhex("807808007554"), 0x557E0D03),
}
SMAP_SKIP = 0x557E0D57


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
        mov eax, dword ptr [eax + {NAME_FIELD:#x}]
        jmp pk_have
    pk_p1:
        cmp ecx, 1
        jne pk_p2
        mov eax, dword ptr [eax + 0xd4]
        jmp pk_obj
    pk_p2:
        cmp ecx, 2
        jne pk_p3
        mov eax, dword ptr [eax + 0x58]
    pk_obj:
        test eax, eax
        je pk_next
        mov eax, dword ptr [eax + 0x60]
        jmp pk_have
    pk_p3:
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
        inc byte ptr [edi + ecx + {DIAG + 4:#x}]
    pk_next:
        inc dword ptr [esp + 4]
        jmp pk_loop
    pk_endpass:
        inc dword ptr [esp + 8]
        cmp dword ptr [esp + 8], 4
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

    rwname:
        push eax
        push ecx
        push edx
        push edi
        lea edx, [ebx + {NAME_FIELD:#x}]
        mov ecx, {NAME_TAG:#x}
        mov eax, esi
        mov edi, dword ptr [eax]
        call dword ptr [edi + 0x20]
        pop edi
        pop edx
        pop ecx
        pop eax
        lea edx, [ebx + 0xa6]
        jmp {XSITES["rwname"][2]:#x}

    smap:
        push eax
        cmp byte ptr [eax + 8], 0
        jne sm_out
        mov edx, dword ptr [eax + 0xc]
        mov eax, dword ptr [ebp - 4]
        mov eax, dword ptr [eax + 0x28]
        mov eax, dword ptr [eax + 0x38]
        push eax
        call {e['REMOTE_INDEXOF']}
        mov edx, eax
        pop eax
        cmp edx, -1
        je sm_out
        call {e['REMOTE_GETPLAYERS']}
        test eax, eax
        je sm_out
        mov edx, dword ptr [eax + 8]
        lea eax, [esi + {NAME_FIELD:#x}]
        call {e['LSTR_ASG']}
    sm_out:
        pop eax
        cmp byte ptr [eax + 8], 0
        jne {SMAP_SKIP:#x}
        jmp {XSITES["smap"][2]:#x}

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
    names = ("pick", "conn", "upd", "rwname", "smap")
    code, _ = ks.asm(asm_src() + "".join("    .long %s\n" % n for n in names), CODE)
    code = bytes(code)
    labels = dict(zip(names, struct.unpack("<5I", code[-20:])))
    zone = MAGIC + bytes(12) + code[:-20]
    assert len(zone) <= ZONE_END - ZONE, hex(len(zone))
    return zone, labels


def xjmp(va, dst):
    return b"\xe9" + struct.pack("<i", dst - (va + 5)) + b"\x90"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true"); ap.add_argument("--dll", default=DLL)
    a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read())
    rd = lambda lo, n: bytes(d[lo - V2F:lo - V2F + n])
    zone, ent = build()
    known = {"v4": (zone, ent), "v3": v3.build(), "v2": v2.build(), "v1": v1.build()}
    assert DIAG + 8 <= 0x558E9F80 and TAB + N * 8 <= DIAG

    def base_state():
        zl = rd(ZONE, ZONE_END - ZONE)
        sites = [rd(va, 7) for va, _, _ in SITES.values()]
        for name, (z, en) in known.items():
            if all(s == v1.site_jmp(va, en[k]) for s, (k, (va, _, _)) in zip(sites, SITES.items())) \
                    and zl[:len(z)] == z and not any(zl[len(z):]):
                return name
        if all(s == orig for s, (_, orig, _) in zip(sites, SITES.values())) and not any(zl):
            return "vanilla"
        return "OTHER"

    def extra_state():
        isz = struct.unpack("<I", rd(ISZ_VA, 4))[0]
        xs = [rd(va, 6) for va, _, _ in XSITES.values()]
        if isz == ISZ_NEW and all(x == xjmp(va, ent[k]) for x, (k, (va, _, _)) in zip(xs, XSITES.items())):
            return "v4"
        if isz == ISZ_OLD and all(x == orig for x, (_, orig, _) in zip(xs, XSITES.values())):
            return "vanilla"
        return "OTHER isz=%#x %s" % (isz, " ".join(x.hex() for x in xs))

    bst, xst = base_state(), extra_state()
    st = "v4" if (bst, xst) == ("v4", "v4") else bst if xst == "vanilla" and bst != "v4" else "OTHER(%s/%s)" % (bst, xst)
    rl = relocs(bytes(d), BASE)
    hot = [(va, 7) for va, _, _ in SITES.values()] + [(va, 6) for va, _, _ in XSITES.values()] + [(ISZ_VA, 4)]
    bad = [hex(r) for r in rl if ZONE - 3 <= r < ZONE_END or any(va - 3 <= r < va + n for va, n in hot)]
    print("state %s | zone %#x (%d B, entries %s) | TPlayer+%#x tag %#x, InstanceSize %#x | relocs at sites %s"
          % (st, ZONE, len(zone), " ".join("%s=%#x" % kv for kv in ent.items()), NAME_FIELD, NAME_TAG,
             struct.unpack("<I", rd(ISZ_VA, 4))[0], bad or "none"))
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
        if st not in ("v1", "v2", "v3", "v4"):
            print("ABORT: unknown state - refusing a partial revert"); return 1
        for va, orig, _ in SITES.values(): d[va - V2F:va - V2F + 7] = orig
        for va, orig, _ in XSITES.values(): d[va - V2F:va - V2F + 6] = orig
        d[ISZ_VA - V2F:ISZ_VA - V2F + 4] = struct.pack("<I", ISZ_OLD)
        d[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE)
    else:
        if st == "v4":
            print("already applied"); return 0
        if st not in ("vanilla", "v1", "v2", "v3"):
            print("ABORT: unexpected state (needs vanilla or autoclaim v1/v2/v3)"); return 1
        d[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE)
        d[ZONE - V2F:ZONE - V2F + len(zone)] = zone
        for k, (va, _, _) in SITES.items(): d[va - V2F:va - V2F + 7] = v1.site_jmp(va, ent[k])
        for k, (va, _, _) in XSITES.items(): d[va - V2F:va - V2F + 6] = xjmp(va, ent[k])
        d[ISZ_VA - V2F:ISZ_VA - V2F + 4] = struct.pack("<I", ISZ_NEW)
    if not (a.apply or a.revert):
        print("Dry run OK (%s -> %s) - rerun with --apply." % (st, "vanilla" if a.revert else "v4")); return 0
    bak = bak_path(a.dll, ".bak_mpautoclaim4")
    if a.apply and not os.path.exists(bak):
        shutil.copy2(a.dll, bak); print("backup ->", bak)
    with open(a.dll, "r+b") as f:
        f.seek(0); f.write(d)
    print("reverted" if a.revert else "applied")
    return 0


if __name__ == "__main__":
    sys.exit(main())
