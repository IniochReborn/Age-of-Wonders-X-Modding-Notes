#!/usr/bin/env python3
r"""
Clear Sky paints over Sky in the editor's clear-terrain mode too (2026-10-31) - on top of patch_sky_polish_v8.

User: "the editor doesnt let me place clear sky over sky terrain. i have to first place chasm over sky, then clear
sky over chasm".
Sky and Clear Sky are both terrain 0xE; TAbstractHexagon.ChangeTerrain skips same-terrain calls, and the sky polish
bypass (v2 ct cave, gated by v4's paint byte 0x5562E5F1) re-picks the tile when the Clear-ness differs from the
brush - but the gate is only set around THSMPlaceControl.MsgProc case 0 (change terrain, 0x55612989).  The terrain
buttons pick case 1 (clear terrain = remove objects, then the same map ChangeTerrain [vmt+0xD0]) when the editor's
clear toggle ([form+0x60C]) is down: THSMap.ClearTerrain 0x5560CBEC, called at 0x556129AD - ungated -> the
Clear-vs-Sky re-pick never ran.
  * 0x556129AD `call 0x5560CBEC` -> cave 'SCG1' 0x5561CF00: gate = 1, call, gate = 0 (PIC delta, like pc1).
Backup .bak_skyclrgate (HSEPack.dpl).  Dry-run default; --apply; --revert.
"""
import os, shutil, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bakpath import bak_path  # noqa: E402
import patch_sky_polish_v1 as SP  # noqa: E402
import patch_devx_massive_brush_v1 as M1  # noqa: E402
import sky_clouds_overlay_asm as OV  # noqa: E402

TAG = ".bak_skyclrgate"
HSE, HBASE = M1.HSE, M1.HBASE
GATE = 0x5562E5F1
SITE, CLEARTER, BACK = 0x556129AD, 0x5560CBEC, 0x556129B2
CAVE, CAVE_END, MAGIC = 0x5561CF00, 0x5561CF80, b"SCG1"


def patches():
    at = CAVE + len(MAGIC)
    code = OV.asm(f"""
        push eax
        call g1
    g1:
        pop eax
        sub eax, g1
        mov byte ptr [eax + {GATE:#x}], 1
        pop eax
        call {CLEARTER:#x}
        push eax
        call g2
    g2:
        pop eax
        sub eax, g2
        mov byte ptr [eax + {GATE:#x}], 0
        pop eax
        jmp {BACK:#x}
    """, at)
    blob = MAGIC + code
    assert CAVE + len(blob) <= CAVE_END
    return [(CAVE, bytes(len(blob)), blob),
            (SITE, b"\xe8" + struct.pack("<i", CLEARTER - (SITE + 5)), b"\xe9" + struct.pack("<i", at - (SITE + 5)))]


def main():
    import pefile
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if (apply or revert) and SP.busy():
        print("game/editor running - close it first"); return 1
    d = open(HSE, "rb").read(); pe = pefile.PE(data=d)
    P = patches()
    st, bad = SP.state(d, pe, HBASE, P)
    print("HSEPack %s relocs %s" % (st, bad or "none"))
    if "OTHER" in st or bad or len(set(st)) != 1:
        print("ABORT"); return 1
    want = "vanilla" if revert else "ours"
    if st[0] == want:
        print("already %s" % ("reverted" if revert else "applied")); return 0
    if not apply and not revert:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bk = bak_path(HSE, TAG)
    if not revert and not os.path.exists(bk):
        shutil.copy2(HSE, bk)
    SP.write_bytes(HSE, HBASE, P, revert)
    print("reverted" if revert else "written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
