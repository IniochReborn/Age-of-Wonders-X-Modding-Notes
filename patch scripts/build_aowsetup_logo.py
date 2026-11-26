#!/usr/bin/env python3
r"""Put the AoWx logo onto AoWSetup.exe's own background art.

AoWSetup's 398x450 background BMP is embedded at file offset 0x7eda3
(538254 bytes, 24-bit, the same resource the installer splash is built from).
This patch replaces it in place with the same composite the installer uses:
black patch over the baked vanilla logo (solid to y142, faded out by y154),
then the AoWx logo (manual HTML "logo" base64 PNG) pasted in exact
registration (scale 0.938, offset 44,23). The 4-slot button bar is untouched
(AoWSetup still draws its own buttons there).

The composite is always built from the PRISTINE art: from AoWSetup.exe.bak_logo
when it exists, so re-running is idempotent. --revert restores only the BMP
slice, preserving unrelated AoWSetup patches made later.

Usage:
    py build_aowsetup_logo.py            # dry run
    py build_aowsetup_logo.py --apply
    py build_aowsetup_logo.py --revert
"""
import base64, io, os, re, shutil, struct, sys
from PIL import Image

GAME = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
EXE = os.path.join(GAME, "AoWSetup.exe")
BAK = EXE + ".bak_logo"
BMP_OFF, BMP_LEN = 0x7eda3, 538254


def load_logo():
    d = open(os.path.join(GAME, ".AoWx Manual.html"), encoding="utf-8", errors="replace").read()
    m = re.search(r'"logo": "data:image/(png|jpeg);base64,([^"]+)"', d)
    return Image.open(io.BytesIO(base64.b64decode(m.group(2)))).convert("RGBA")


def composite(bmp_bytes):
    bg = Image.open(io.BytesIO(bmp_bytes)).convert("RGB")
    assert bg.size == (398, 450), f"unexpected art size {bg.size}"
    px = bg.load()
    for y in range(14, 154):
        a = 1.0 if y <= 142 else 1.0 - (y - 142) / 12.0
        for x in range(14, bg.width - 14):
            r, g, b = px[x, y]
            px[x, y] = (int(r * (1 - a)), int(g * (1 - a)), int(b * (1 - a)))
    logo = load_logo()
    logo_s = logo.resize((round(logo.width * 0.938), round(logo.height * 0.938)), Image.LANCZOS)
    bg.paste(logo_s, (44, 23), logo_s)
    out = io.BytesIO()
    bg.save(out, "BMP")
    blob = out.getvalue()
    assert len(blob) == BMP_LEN, f"re-encoded BMP is {len(blob)} bytes, need {BMP_LEN}"
    return blob


def main():
    apply = "--apply" in sys.argv
    revert = "--revert" in sys.argv

    cur = open(EXE, "rb").read()
    print(f"AoWSetup.exe: {len(cur)} bytes")

    if revert:
        if not os.path.isfile(BAK):
            print("!! no backup to revert from:", BAK)
            return 1
        bak = open(BAK, "rb").read()
        patched = cur[:BMP_OFF] + bak[BMP_OFF:BMP_OFF + BMP_LEN] + cur[BMP_OFF + BMP_LEN:]
        open(EXE, "wb").write(patched)
        print("REVERTED background BMP slice from backup")
        return 0

    src = open(BAK, "rb").read() if os.path.isfile(BAK) else cur
    if os.path.isfile(BAK):
        print("compositing from pristine backup", os.path.basename(BAK))
    slice_ = src[BMP_OFF:BMP_OFF + BMP_LEN]
    assert slice_[:2] == b"BM", "no BMP at expected offset"
    assert struct.unpack_from("<I", slice_, 2)[0] == BMP_LEN, "BMP size field mismatch"
    w, h = struct.unpack_from("<ii", slice_, 18)
    assert (w, h) == (398, 450), f"unexpected BMP dims {w}x{h}"

    blob = composite(slice_)
    diff = sum(1 for a, b in zip(blob, cur[BMP_OFF:BMP_OFF + BMP_LEN]) if a != b)
    print(f"patched BMP differs from current exe content in {diff} of {BMP_LEN} bytes")
    if diff == 0:
        print("already patched - nothing to do")
        return 0

    if not apply:
        print("\nDry run only - rerun with --apply")
        return 0

    if not os.path.isfile(BAK):
        shutil.copy2(EXE, BAK)
        print("backup written:", os.path.basename(BAK))
    open(EXE, "wb").write(cur[:BMP_OFF] + blob + cur[BMP_OFF + BMP_LEN:])
    print("WROTE AoWSetup.exe with AoWx logo background")
    return 0


if __name__ == "__main__":
    sys.exit(main())
