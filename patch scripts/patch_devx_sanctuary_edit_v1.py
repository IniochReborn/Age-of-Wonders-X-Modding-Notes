#!/usr/bin/env python3
r"""
AoWDevX: Magic Sanctuary instance editor with a 'Razed' checkbox (2026-10-31).  Companion of patch_sanctuary_raze_v1.

User: "it works but i cant set to razed in the editor".  Instance edit dialogs are editor plugins registered with
Engine.TEObjectEditorList.RegisterClass (thunk 0x4025E8), one class per edited map-object ClassID (vmt+0x4C).
A plain TStructure like the Sanctuary has none.  The Teleport's plugin (TTeleportEditor, VMT 0x419658, ClassID
0x20104, registered by 0x419704) opens TTeleportEditForm = destination x/y/level spinners ([obj+30..32],
form +0x220/+0x224/+0x228) + Razed checkbox (form +0x234; load 0x4197B8, OK 0x419861 -> SetRazed vmt+0x14C).
Patch (.xprn slack 0x4EB640..0x4EB800, after ClearSkyBtnClick):
  * TSanctuaryEditor = clone of TTeleportEditor's VMT (0x40 B header + 0x60 B slots) with its own name, self pointer
    and ClassID function (0x2089A); the Teleport registration routine 0x419704 -> stub registering both;
  * TTeleportEditForm load 0x419779 / OK 0x419813: object VMT == TMagicSanctuary (0x557D41F4 + AoWEPACK delta via
    the AoWHSMap import) -> spinners disabled, destination bytes NOT read/written (on a Sanctuary +0x30 is the
    bubble pointer); only the Razed checkbox is used.
Backup .bak_sanctedit.  Dry-run default; --apply; --revert.
"""
import os, shutil, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bakpath import bak_path, game_file  # noqa: E402
import patch_sky_polish_v1 as SP  # noqa: E402
import sky_clouds_overlay_asm as OV  # noqa: E402

EXE, BASE = game_file("AoWDevX.exe"), 0x400000
ZONE, ZONE_END, MAGIC = 0x4EB640, 0x4EB800, b"SED1"
TV = 0x419658                     # TTeleportEditor VMT
REG, REG_ORIG = 0x419704, bytes.fromhex("8b15189641008b4018e8d68efeffc3")
LOAD, LOAD_ORIG = 0x419779, bytes.fromhex("8b830c020000")
OK, OK_ORIG = 0x419813, bytes.fromhex("8b8320020000")
IAT_AOWHSMAP, AOWHSMAP_NOM = 0x43289C, 0x558FA040
SANCT_VMT, SANCT_CID = 0x557D41F4, 0x2089A
REGISTER, SETENABLED = 0x4025E8, 0x401550
NAME = b"TSanctuaryEditor"


def build(d, pe):
    off = lambda va: pe.get_offset_from_rva(va - BASE)  # noqa: E731
    u = lambda va: struct.unpack_from("<I", d, off(va))[0]  # noqa: E731
    assert u(TV - 0x40) == TV
    hdr = bytearray(d[off(TV - 0x40):off(TV)])
    slots = bytearray(d[off(TV):off(TV + 0x60)])
    assert struct.unpack_from("<I", slots, 0x4C)[0] == 0x4196C4
    name_va = ZONE + 0x10
    vmt = ZONE + 0x40 + 0x40               # header at ZONE+0x40, slots at ZONE+0x80
    code_va = vmt + 0x60
    src = f"""
    cid:
        mov eax, {SANCT_CID:#x}
        ret
    reg:
        push eax
        mov edx, dword ptr [0x419618]
        mov eax, dword ptr [eax + 0x18]
        call {REGISTER:#x}
        pop eax
        mov edx, {vmt:#x}
        mov eax, dword ptr [eax + 0x18]
        call {REGISTER:#x}
        ret
    issanct:
        mov eax, dword ptr [ebx + 0x20c]
        mov eax, dword ptr [eax]
        mov edx, dword ptr [{IAT_AOWHSMAP:#x}]
        sub edx, {AOWHSMAP_NOM:#x}
        add edx, {SANCT_VMT:#x}
        cmp eax, edx
        ret
    load:
        call issanct
        jne load_tele
        xor edx, edx
        mov eax, dword ptr [ebx + 0x220]
        call {SETENABLED:#x}
        xor edx, edx
        mov eax, dword ptr [ebx + 0x224]
        call {SETENABLED:#x}
        xor edx, edx
        mov eax, dword ptr [ebx + 0x228]
        call {SETENABLED:#x}
        jmp 0x4197b8
    load_tele:
        mov eax, dword ptr [ebx + 0x20c]
        jmp {LOAD + 6:#x}
    okc:
        call issanct
        je 0x419861
        mov eax, dword ptr [ebx + 0x220]
        jmp {OK + 6:#x}
    .long cid
    .long reg
    .long load
    .long okc
"""
    code = OV.asm(src, code_va)
    e = dict(zip(("cid", "reg", "load", "okc"), struct.unpack("<4I", code[-16:])))
    code = code[:-16]
    struct.pack_into("<I", hdr, 0, vmt)                     # self pointer
    struct.pack_into("<I", hdr, 0x20, name_va)              # class name
    struct.pack_into("<I", slots, 0x4C, e["cid"])
    z = bytearray(code_va + len(code) - ZONE)
    z[0:4] = MAGIC
    z[0x10:0x10 + 1 + len(NAME)] = bytes([len(NAME)]) + NAME
    z[0x40:0x80] = hdr
    z[0x80:0xE0] = slots
    z[code_va - ZONE:] = code
    assert ZONE + len(z) <= ZONE_END, hex(len(z))
    jmp = lambda at, to, n: b"\xe9" + struct.pack("<i", to - (at + 5)) + b"\x90" * (n - 5)  # noqa: E731
    return [(REG, REG_ORIG, jmp(REG, e["reg"], len(REG_ORIG))), (LOAD, LOAD_ORIG, jmp(LOAD, e["load"], 6)),
            (OK, OK_ORIG, jmp(OK, e["okc"], 6)), (ZONE, bytes(len(z)), bytes(z))]


def main():
    import pefile
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    d = open(EXE, "rb").read(); pe = pefile.PE(data=d)
    P = build(d, pe)
    st, bad = SP.state(d, pe, BASE, P)
    # 0x419706 = the absolute [0x419618] operand of the registration routine: a .reloc entry, but the main exe is
    # never rebased, so overwriting it is harmless
    bad = [x for x in bad if x != hex(REG + 2)]
    print("AoWDevX %s relocs %s" % (st, bad or "none (besides the known 0x419706)"))
    if "OTHER" in st or bad or len(set(st)) != 1:
        print("ABORT"); return 1
    want = "vanilla" if revert else "ours"
    if st[0] == want:
        print("already %s" % ("reverted" if revert else "applied")); return 0
    if not apply and not revert:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if SP.busy():
        print("game/editor running - close it first"); return 1
    bk = bak_path(EXE, ".bak_sanctedit")
    if not revert and not os.path.exists(bk):
        shutil.copy2(EXE, bk)
    SP.write_bytes(EXE, BASE, P, revert)
    print("reverted" if revert else "written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
