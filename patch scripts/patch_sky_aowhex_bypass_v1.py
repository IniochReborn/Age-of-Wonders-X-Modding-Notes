#!/usr/bin/env python3
r"""
Sky <-> Clear Sky paint over each other in the editor - the REAL same-terrain skip (2026-11-01).

User: "i cant put sky over clear sky, and i cant put clear sky over sky".
diag_sky_paint_probe (11/01) showed the HSEPack TAbstractHexagon.ChangeTerrain bypass (sky polish v2/v4) is never
reached by a brush stroke: AoW maps are made of AoWEPACK TAoWHexagon objects (VMT 0x5579A1D0) whose slot 0x9C
ChangeTerrain 0x5579A89C has its own `cmp al,[esi]; je skip` (0x5579A8B5).  Sky and Clear Sky are both terrain
0xE -> skipped.
  * 0x5579A8B5 -> cave 'SKA1' (AoWEPACK 0x558E0A00, PIC): same terrain 0xE while the editor paint gate is set
    (HSEPack 0x5562E5F1, set around MsgProc case 0/1) and the hexagon's Clear-ness (resource RID>>16 == 0x5A1B)
    differs from the brush Clear flag (HSEPack 0x5562E5F0) -> fall through into the re-pick (0x5579A8BD; its
    GetRndResource is HSEPack's, filtered by the flag via sky polish 'grr'); otherwise vanilla.
    HSEPack delta = [IAT 0x558FBBA0 (HSEPack GetRndResource)] - 0x5560E94C.
Backup .bak_skyaowhex (AoWEPACK.dll).  Dry-run default; --apply; --revert.
"""
import os, shutil, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bakpath import bak_path  # noqa: E402
import patch_sky_polish_v1 as SP  # noqa: E402
import sky_clouds_overlay_asm as OV  # noqa: E402

TAG = ".bak_skyaowhex"
SITE, SITE_ORIG = 0x5579A8B5, bytes.fromhex("3a060f848b000000")   # cmp al,[esi] / je 0x5579A948
GO, SKIP = 0x5579A8BD, 0x5579A948
IAT_GRR, HSE_GRR = 0x558FBBA0, 0x5560E94C
GATE, FLAG, CLEAR_HI = 0x5562E5F1, 0x5562E5F0, 0x5A1B
CAVE, CAVE_END, MAGIC = 0x558E0A00, 0x558E0A80, b"SKA1"


def patches(d, pe):
    at = CAVE + len(MAGIC)

    def src(dl):
        return f"""
            cmp al, byte ptr [esi]
            jne go
            cmp al, 0xe
            jne skip
            call l0
        l0:
            pop ecx
            add ecx, {dl:#x}
            mov ecx, dword ptr [ecx]
            sub ecx, {HSE_GRR:#x}
            cmp byte ptr [ecx + {GATE:#x}], 0
            je skip
            mov edx, dword ptr [ebx + 8]
            mov edx, dword ptr [edx + 0xc]
            shr edx, 16
            cmp edx, {CLEAR_HI:#x}
            sete dl
            movzx edx, dl
            movzx ecx, byte ptr [ecx + {FLAG:#x}]
            cmp ecx, edx
            jne go
        skip:
            jmp {SKIP:#x}
        go:
            jmp {GO:#x}
        """
    probe = OV.asm(src(0x11111111), at)
    l0 = at + probe.index(b"\x59\x81\xc1")
    code = OV.asm(src((IAT_GRR - l0) & 0xFFFFFFFF), at)
    assert len(code) == len(probe)
    blob = MAGIC + code
    assert CAVE + len(blob) <= CAVE_END
    return [(CAVE, bytes(len(blob)), blob),
            (SITE, SITE_ORIG, b"\xe9" + struct.pack("<i", at - (SITE + 5)) + b"\x90" * 3)]


def main():
    import pefile
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if (apply or revert) and SP.busy():
        print("game/editor running - close it first"); return 1
    d = open(SP.EPK, "rb").read(); pe = pefile.PE(data=d)
    P = patches(d, pe)
    st, bad = SP.state(d, pe, SP.EBASE, P)
    print("AoWEPACK %s relocs %s" % (st, bad or "none"))
    if "OTHER" in st or bad or len(set(st)) != 1:
        print("ABORT"); return 1
    want = "vanilla" if revert else "ours"
    if st[0] == want:
        print("already %s" % ("reverted" if revert else "applied")); return 0
    if not apply and not revert:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bk = bak_path(SP.EPK, TAG)
    if not revert and not os.path.exists(bk):
        shutil.copy2(SP.EPK, bk)
    SP.write_bytes(SP.EPK, SP.EBASE, P, revert)
    print("reverted" if revert else "written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
