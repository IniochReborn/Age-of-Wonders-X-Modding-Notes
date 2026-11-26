#!/usr/bin/env python3
r"""
AoWDevX.exe: Item Properties dialog accepts negative Attack/Defense/Damage/Resistance (2026-09-21).

The four VCLADDON TSpin controls of TItemEditForm (AttackEdit/DefenseEdit/ResistanceEdit/DamageEdit) carry
MinValue 0 / MaxValue 10 in the DFM, so the editor could not author a penalty although the game already treats
the item bytes (+0x46..+0x49) as signed (movsx in the dialog loader 0x413377.., THeroItems totals sum signed
bytes, the OnChange handlers store AL).  HP/MV (our runtime spinners) already allow -20..30 / -10..10.
Patch: in the live TITEMEDITFORM DFM (section .xdfm @0x4E6000 - patch_devx_item_hpmv_ui.py relocated it there;
⚠ re-run this script after re-applying that one) set MinValue -10 for the four controls (vaInt8 `02 F6`).
Backup AoWDevX.exe.bak_itemneg (in <game>\backup\).  Dry-run default; --apply; --revert.
"""
import argparse, os, re, shutil, sys
from bakpath import game_file, bak_path

EXE = game_file(r"AoWDevX.exe")
BAK = ".bak_itemneg"
DFM_VA, DFM_SPAN = 0x4E6000, 0x3000
NAMES = [b"AttackEdit", b"DefenseEdit", b"ResistanceEdit", b"DamageEdit"]
MIN_OLD, MIN_NEW = b"\x08MinValue\x02\x00", b"\x08MinValue\x02\xf6"


def va2off(d, va):
    import struct
    e = struct.unpack_from("<I", d, 0x3C)[0]; n = struct.unpack_from("<H", d, e + 6)[0]; sec = e + 24 + struct.unpack_from("<H", d, e + 20)[0]
    for i in range(n):
        vsz, rva, rsz, roff = struct.unpack_from("<IIII", d, sec + 40 * i + 8)
        if rva <= va - 0x400000 < rva + max(vsz, rsz):
            return roff + (va - 0x400000 - rva)
    raise ValueError


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    a = ap.parse_args(); bak = bak_path(EXE, BAK, create=a.apply)
    if a.revert:
        if not os.path.exists(bak):
            sys.exit(f"no backup {bak}")
        shutil.copy2(bak, EXE); print(f"reverted {EXE} from {bak}"); return
    d = bytearray(open(EXE, "rb").read()); o = va2off(d, DFM_VA); dfm = bytes(d[o:o + DFM_SPAN])
    assert dfm[:4] == b"TPF0", "no DFM at .xdfm"
    sites = []
    for nm in NAMES:
        i = dfm.find(b"\x05TSpin" + bytes([len(nm)]) + nm); assert i >= 0, nm
        seg = dfm[i:i + 160]
        jo, jn = seg.find(MIN_OLD), seg.find(MIN_NEW)
        assert (jo >= 0) != (jn >= 0), nm
        sites.append((o + i + (jo if jo >= 0 else jn), "vanilla" if jo >= 0 else "PATCHED", nm.decode()))
    print(f"target: {EXE}")
    for off, st, nm in sites:
        print(f"  {nm:15} MinValue @file {off:#x}: {st}")
    if not a.apply:
        print("dry run - nothing written (use --apply)"); return
    if not os.path.exists(bak):
        shutil.copy2(EXE, bak); print(f"  backup -> {bak}")
    for off, st, nm in sites:
        d[off:off + len(MIN_NEW)] = MIN_NEW
    with open(EXE, "r+b") as f:
        f.seek(0); f.write(d)
    print("applied: Attack/Defense/Damage/Resistance spinners now -10..10.")


if __name__ == "__main__":
    main()
