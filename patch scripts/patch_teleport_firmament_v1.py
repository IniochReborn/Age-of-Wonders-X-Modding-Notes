#!/usr/bin/env python3
r"""
Teleporters to the Firmament as Z = -1 (2026-10-31).

User: "for teleporters, having firmament be level 3, then abyss 4+ is confusing. but the surface/underground/depths
map levels cant change or it would break existing maps with teleporters. that was why i wanted firmament to be map
level -1".  Internally the Firmament stays level 3 (patch_map_levels_*: order Surface 0, Caverns 1, Depths 2,
Firmament 3, Abyss 4..28); only the teleporter destination's FILE value and the editor dialog use -1.
  * Game + editor (AoWEPACK, TTeleport.ReadWrite 0x557A4DC8): the destination Z byte [tele+0x32] is streamed by one
    rwByte call (tag 9) for both load and save -> wrapped (0x557A4DF6 -> cave 0x558E0540 'TFM1'): before the call
    in-memory 3 -> 0xFF (a save writes -1), after it 0xFF -> 3 (a load of -1, or restoring after the save).  So every
    reader (MoveExclusive, Teleport, animations, AI) keeps seeing level 3; a file value 3 still works as well.
  * Editor dialog (AoWDevX TTeleportEditForm): load @0x4197A9 shows 3 as -1 and lowers the Z spinner's MinValue
    ([spin+0x130]) to -1; OK @0x419858 stores -1 as 3.  Caves .xprn 0x4ECFC0..0x4ED000 (carved off the end of
    patch_devx_autosave_v1's code zone).
Backups .bak_telefirm (AoWEPACK.dll, AoWDevX.exe).  Dry-run default; --apply; --revert.
"""
import os, shutil, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bakpath import bak_path, game_file  # noqa: E402
import patch_sky_polish_v1 as SP  # noqa: E402
import sky_clouds_overlay_asm as OV  # noqa: E402

TAG = ".bak_telefirm"
DEVX = game_file("AoWDevX.exe")
E_SITE, E_ORIG, E_BACK = 0x557A4DF6, bytes.fromhex("8d5332b9090000008bc68b38ff5730"), 0x557A4E05
E_CAVE, E_END, E_MAGIC = 0x558E0540, 0x558E0580, b"TFM1"
L_SITE, L_ORIG, L_BACK = 0x4197A9, bytes.fromhex("0fbe50328b8328020000"), 0x4197B3
S_SITE, S_ORIG, S_BACK = 0x419858, bytes.fromhex("8bb30c020000884632"), 0x419861
D_CAVE, D_END = 0x4ECFC0, 0x4ED000


def epk_patches():
    code = OV.asm(f"""
        cmp byte ptr [ebx + 0x32], 0x3
        jne pre
        mov byte ptr [ebx + 0x32], 0xff
    pre:
        lea edx, [ebx + 0x32]
        mov ecx, 0x9
        mov eax, esi
        mov edi, dword ptr [eax]
        call dword ptr [edi + 0x30]
        cmp byte ptr [ebx + 0x32], 0xff
        jne post
        mov byte ptr [ebx + 0x32], 0x3
    post:
        jmp {E_BACK:#x}
    """, E_CAVE + 4)
    z = E_MAGIC + code
    assert len(z) <= E_END - E_CAVE
    return [(E_SITE, E_ORIG, b"\xe9" + struct.pack("<i", E_CAVE + 4 - (E_SITE + 5)) + b"\x90" * 10),
            (E_CAVE, bytes(len(z)), z)]


def devx_patches():
    load = OV.asm(f"""
        movsx edx, byte ptr [eax + 0x32]
        cmp edx, 0x3
        jne l1
        or edx, 0xffffffff
    l1:
        mov eax, dword ptr [ebx + 0x228]
        mov dword ptr [eax + 0x130], 0xffffffff
        jmp {L_BACK:#x}
    """, D_CAVE)
    s_at = D_CAVE + len(load)
    store = OV.asm(f"""
        mov esi, dword ptr [ebx + 0x20c]
        cmp al, 0xff
        jne s1
        mov al, 0x3
    s1:
        mov byte ptr [esi + 0x32], al
        jmp {S_BACK:#x}
    """, s_at)
    z = load + store
    assert D_CAVE + len(z) <= D_END, len(z)
    return [(L_SITE, L_ORIG, b"\xe9" + struct.pack("<i", D_CAVE - (L_SITE + 5)) + b"\x90" * 5),
            (S_SITE, S_ORIG, b"\xe9" + struct.pack("<i", s_at - (S_SITE + 5)) + b"\x90" * 4),
            (D_CAVE, bytes(len(z)), z)]


def main():
    import pefile
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if (apply or revert) and SP.busy():
        print("game/editor running - close it first"); return 1
    work = []
    for name, path, base, P, known in (("AoWEPACK", SP.EPK, SP.EBASE, epk_patches(), ()),
                                       ("AoWDevX", DEVX, 0x400000, devx_patches(), ())):
        d = open(path, "rb").read(); pe = pefile.PE(data=d)
        st, bad = SP.state(d, pe, base, P)
        if name == "AoWDevX":
            bad = []            # the exe never rebases (fixed base, DllCharacteristics 0)
        print("%s %s relocs %s" % (name, st, bad or "none"))
        if "OTHER" in st or bad or len(set(st)) != 1:
            print("ABORT"); return 1
        work.append((name, path, base, P, st[0]))
    if revert:
        for name, path, base, P, st in work:
            if st == "ours":
                SP.write_bytes(path, base, P, True); print("reverted", name)
        return 0
    if all(w[4] == "ours" for w in work):
        print("already applied"); return 0
    if not apply:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    for name, path, base, P, st in work:
        if st == "vanilla":
            bk = bak_path(path, TAG)
            if not os.path.exists(bk):
                shutil.copy2(path, bk)
            SP.write_bytes(path, base, P, False)
    print("written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
