#!/usr/bin/env python3
r"""
Massive brush button follows Brush3Btn at once (2026-10-31).

User: "when opening and closing a map, there is a delay for the new massive brush button to change state like the
regular ones" - Brush4Btn only copied Brush3Btn.Enabled on the 1-second autosave tick (patch_devx_autosave_v1 v1.3
BSYNC routine, data zone .xitm).
  * The two places the editor (de)activates Brush3Btn - close map 0x42A16E, open map 0x42A4AB (both
    `mov eax,[ebx+5F8h]; call TControl.SetEnabled 0x401550`) - call cave 'B4S' instead: SetEnabled, then BSYNC
    under pushad/popad (it uses ebx/esi/edi).
Cave AoWDevX .xthm 0x4E47F0..0x4E4800 (carved off the unused end of patch_devx_item_name_cost_v1 zone).
Backup .bak_brush4sync (AoWDevX.exe).  Dry-run default; --apply; --revert.
"""
import os, re, shutil, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bakpath import bak_path  # noqa: E402
import patch_sky_polish_v1 as SP  # noqa: E402
import patch_devx_massive_brush_v1 as M1  # noqa: E402
import sky_clouds_overlay_asm as OV  # noqa: E402

TAG = ".bak_brush4sync"
DEVX, BASE = M1.DEVX, 0x400000
SETEN = 0x401550
SITES = [0x42A16E, 0x42A4AB]
CAVE, CAVE_END = 0x4E47F0, 0x4E4800


def find_bsync(d, pe):
    m = [x.start() for x in re.finditer(rb"\xa1....\x85\xc0\x74.\x8b\x88\xf8\x05\x00\x00\x85\xc9", d, re.S)]
    assert len(m) == 1, "BSYNC routine (patch_devx_autosave_v1 v1.3) not found"
    return BASE + pe.get_rva_from_offset(m[0])


def patches(d, pe):
    bs = find_bsync(d, pe)
    code = OV.asm(f"""
        call {SETEN:#x}
        pushad
        call {bs:#x}
        popad
        ret
    """, CAVE)
    assert CAVE + len(code) <= CAVE_END
    P = [(CAVE, bytes(len(code)), code)]
    for s in SITES:
        P.append((s, b"\xe8" + struct.pack("<i", SETEN - (s + 5)), b"\xe8" + struct.pack("<i", CAVE - (s + 5))))
    return P


def main():
    import pefile
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if (apply or revert) and SP.busy():
        print("game/editor running - close it first"); return 1
    d = open(DEVX, "rb").read(); pe = pefile.PE(data=d)
    P = patches(d, pe)
    st, bad = SP.state(d, pe, BASE, P)
    print("AoWDevX %s relocs %s" % (st, bad or "none"))
    if "OTHER" in st or bad or len(set(st)) != 1:
        print("ABORT"); return 1
    want = "vanilla" if revert else "ours"
    if st[0] == want:
        print("already %s" % ("reverted" if revert else "applied")); return 0
    if not apply and not revert:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bk = bak_path(DEVX, TAG)
    if not revert and not os.path.exists(bk):
        shutil.copy2(DEVX, bk)
    SP.write_bytes(DEVX, BASE, P, revert)
    print("reverted" if revert else "written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
