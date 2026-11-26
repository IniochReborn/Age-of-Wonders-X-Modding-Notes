#!/usr/bin/env python3
r"""
AoWDevX: Magic Sanctuary properties window (2026-10-31) - supersedes patch_devx_sanctuary_edit_v1 (revert v1 first).

User after v1 (Teleport dialog with the destination spinners greyed out): "why is the teleporter stuff re-used? ...
make it its own window".  A truly separate form class would also need a new TSANCTUARYEDITFORM resource in .rsrc;
instead the Teleport dialog is turned into the Sanctuary's own window at load time:
  * TSanctuaryEditor plugin (TTeleportEditor VMT clone, ClassID 0x2089A, registered with the Teleport's) - as v1;
  * TTeleportEditForm load ENTRY 0x419714 (v1 hooked 0x419779, after the spinner set-up): for a TMagicSanctuary
    (VMT 0x557D41F4 + AoWEPACK delta) -> 'Teleport position' group (GroupBox1 form+0x210) hidden, Razed checkbox
    (form+0x234) moved to Top 20, ClientPnl (= MainPageControl form+0x204 .Parent) and the window 85 px shorter,
    ButtonPnl (the other child of the form's FWinControls list +0xC0) 85 px up, caption 'Magic Sanctuary
    Properties'; then only the Razed checkbox is loaded (0x4197B8) - the destination spinners are never touched;
  * OK 0x419813: Sanctuary -> only SetRazed (as v1).
TControl: FParent +0x24, FTop +0x34, FHeight +0x3C; thunks SetTop 0x401500, SetHeight 0x401510, SetVisible 0x401548,
SetText 0x401568.  Zone .xprn 0x4EB640..0x4EB800 'SED2' + caption literal in the method-table tail 0x4EC4D8.
Backup .bak_sanctedit2.  Dry-run default; --apply; --revert.
"""
import os, shutil, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bakpath import bak_path, game_file  # noqa: E402
import patch_sky_polish_v1 as SP  # noqa: E402
import sky_clouds_overlay_asm as OV  # noqa: E402
import patch_devx_sanctuary_edit_v1 as V1  # noqa: E402

EXE, BASE = V1.EXE, V1.BASE
ZONE, ZONE_END, MAGIC = 0x4EB640, 0x4EB800, b"SED2"
ENTRY, ENTRY_ORIG = 0x419714, bytes.fromhex("538bd8a19c284300")
CAPTION_VA, CAPTION_END = 0x4EC4D8, 0x4EC500
CAPTION = b"Magic Sanctuary Properties"
SHRINK = 85
SETTOP, SETHEIGHT, SETVISIBLE, SETTEXT = 0x401500, 0x401510, 0x401548, 0x401568


def build(d, pe, v21=True):
    # v2.1 (11/01): the Sanctuary branch must load ESI = edited object (form+0x20C) before rejoining at 0x419861
    # (SetRazed = [esi vmt+0x14C]); the teleporter path sets ESI in the firmament cave 0x4ECFE1, v2 skipped it ->
    # garbage vcall (AV at 0x0CFFFFFF / C000001D) when OK was pressed on a Sanctuary.
    okc_sanct = ("jne okt\n        mov esi, dword ptr [ebx + 0x20c]\n        jmp 0x419861\n    okt:" if v21
                 else "je 0x419861")
    off = lambda va: pe.get_offset_from_rva(va - BASE)  # noqa: E731
    u = lambda va: struct.unpack_from("<I", d, off(va))[0]  # noqa: E731
    TV = V1.TV
    assert u(TV - 0x40) == TV
    hdr = bytearray(d[off(TV - 0x40):off(TV)])
    slots = bytearray(d[off(TV):off(TV + 0x60)])
    assert struct.unpack_from("<I", slots, 0x4C)[0] == 0x4196C4
    name_va = ZONE + 0x4
    vmt = ZONE + 0x58
    code_va = vmt + 0x60
    cap_chars = CAPTION_VA + 8
    src = f"""
    cid:
        mov eax, {V1.SANCT_CID:#x}
        ret
    reg:
        push eax
        mov edx, dword ptr [0x419618]
        mov eax, dword ptr [eax + 0x18]
        call {V1.REGISTER:#x}
        pop eax
        mov edx, {vmt:#x}
        mov eax, dword ptr [eax + 0x18]
        call {V1.REGISTER:#x}
        ret
    issanct:
        mov eax, dword ptr [ebx + 0x20c]
        mov eax, dword ptr [eax]
        mov edx, dword ptr [{V1.IAT_AOWHSMAP:#x}]
        sub edx, {V1.AOWHSMAP_NOM:#x}
        add edx, {V1.SANCT_VMT:#x}
        cmp eax, edx
        ret
    load:
        push ebx
        mov ebx, eax
        call issanct
        je lsanct
        mov eax, dword ptr [{V1.IAT_AOWHSMAP:#x}]
        jmp {ENTRY + 8:#x}
    lsanct:
        push esi
        push edi
        xor edx, edx
        mov eax, dword ptr [ebx + 0x210]
        call {SETVISIBLE:#x}
        mov edx, 20
        mov eax, dword ptr [ebx + 0x234]
        call {SETTOP:#x}
        mov eax, dword ptr [ebx + 0x204]
        mov esi, dword ptr [eax + 0x24]
        mov edx, dword ptr [esi + 0x3c]
        sub edx, {SHRINK}
        mov eax, esi
        call {SETHEIGHT:#x}
        mov ecx, dword ptr [ebx + 0xc0]
        test ecx, ecx
        je lnobtn
        xor edi, edi
        mov edx, dword ptr [ecx + 8]
    lfind:
        dec edx
        js lfound
        mov eax, dword ptr [ecx + 4]
        mov eax, dword ptr [eax + edx*4]
        cmp eax, esi
        je lfind
        test edi, edi
        je ltake
        push edx
        mov edx, dword ptr [eax + 0x34]
        cmp edx, dword ptr [edi + 0x34]
        pop edx
        jle lfind
    ltake:
        mov edi, eax
        jmp lfind
    lfound:
        test edi, edi
        je lnobtn
        mov edx, dword ptr [edi + 0x34]
        sub edx, {SHRINK}
        mov eax, edi
        call {SETTOP:#x}
    lnobtn:
        mov edx, dword ptr [ebx + 0x3c]
        sub edx, {SHRINK}
        mov eax, ebx
        call {SETHEIGHT:#x}
        mov edx, {cap_chars:#x}
        mov eax, ebx
        call {SETTEXT:#x}
        pop edi
        pop esi
        jmp 0x4197b8
    okc:
        call issanct
        {okc_sanct}
        mov eax, dword ptr [ebx + 0x220]
        jmp {V1.OK + 6:#x}
    .long cid
    .long reg
    .long load
    .long okc
"""
    code = OV.asm(src, code_va)
    e = dict(zip(("cid", "reg", "load", "okc"), struct.unpack("<4I", code[-16:])))
    code = code[:-16]
    struct.pack_into("<I", hdr, 0, vmt)
    struct.pack_into("<I", hdr, 0x20, name_va)
    struct.pack_into("<I", slots, 0x4C, e["cid"])
    z = bytearray(code_va + len(code) - ZONE)
    z[0:4] = MAGIC
    z[0x4:0x4 + 1 + len(V1.NAME)] = bytes([len(V1.NAME)]) + V1.NAME
    assert 0x4 + 1 + len(V1.NAME) <= 0x18
    z[0x18:0x58] = hdr
    z[0x58:0xB8] = slots
    z[code_va - ZONE:] = code
    assert ZONE + len(z) <= ZONE_END, hex(len(z))
    cap = struct.pack("<iI", -1, len(CAPTION)) + CAPTION + b"\x00"
    assert CAPTION_VA + len(cap) <= CAPTION_END
    jmp = lambda at, to, n: b"\xe9" + struct.pack("<i", to - (at + 5)) + b"\x90" * (n - 5)  # noqa: E731
    return [(V1.REG, V1.REG_ORIG, jmp(V1.REG, e["reg"], len(V1.REG_ORIG))),
            (ENTRY, ENTRY_ORIG, jmp(ENTRY, e["load"], 8)),
            (V1.OK, V1.OK_ORIG, jmp(V1.OK, e["okc"], 6)),
            (ZONE, bytes(len(z)), bytes(z)), (CAPTION_VA, bytes(len(cap)), cap)]


def main():
    import pefile
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    d = open(EXE, "rb").read(); pe = pefile.PE(data=d)
    P = build(d, pe)
    st, bad = SP.state(d, pe, BASE, P)
    known = {hex(V1.REG + 2), hex(ENTRY + 4)}      # absolute operands (.reloc) of the main exe - never rebased
    bad = [x for x in bad if x not in known]
    print("AoWDevX %s relocs %s" % (st, bad or "none (besides known exe operands)"))
    if "OTHER" in st and not revert:                # v2 applied -> code-only upgrade of the zone to v2.1
        P0 = build(d, pe, v21=False)
        st0, _ = SP.state(d, pe, BASE, P0)
        if set(st0) == {"ours"}:
            z0, z1 = P0[3][2], P[3][2]
            old = z0 + bytes(len(z1) - len(z0))
            assert d[pe.get_offset_from_rva(ZONE - BASE):][:len(old)] == old
            if not apply:
                print("v2 applied - dry run OK, --apply upgrades the OK branch to v2.1"); return 0
            if SP.busy():
                print("game/editor running - close it first"); return 1
            bk = bak_path(EXE, ".bak_sanctedit21")
            if not os.path.exists(bk):
                shutil.copy2(EXE, bk)
            SP.write_bytes(EXE, BASE, [(ZONE, old, z1)], False)
            print("upgraded to v2.1 (written and verified)"); return 0
    if "OTHER" in st or bad or len(set(st)) != 1:
        print("ABORT - revert patch_devx_sanctuary_edit_v1 first if it is applied"); return 1
    want = "vanilla" if revert else "ours"
    if st[0] == want:
        print("already %s" % ("reverted" if revert else "applied")); return 0
    if not apply and not revert:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if SP.busy():
        print("game/editor running - close it first"); return 1
    bk = bak_path(EXE, ".bak_sanctedit2")
    if not revert and not os.path.exists(bk):
        shutil.copy2(EXE, bk)
    SP.write_bytes(EXE, BASE, P, revert)
    print("reverted" if revert else "written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
