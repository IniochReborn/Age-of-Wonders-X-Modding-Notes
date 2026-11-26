#!/usr/bin/env python3
r"""
AoWEPACK sky overlay: clouds also drift over the sky fog that spills into sky-shored water / ice hexes (2026-11-07).

User: "the transitions are really good now, the only issue is the moving clouds and how they interact with
transition edges. the clouds are awesome so dont change anything about them, only improve the transition" ->
"look how there is a hex shape that doesnt draw cloud at the edge".

The overlay (sky_clouds_overlay_asm, installed by patch_sky_polish_v1 in zone 0x558CB000 'SKY2') walks only Sky (0xE)
and Chasm (0xB) hexagons, so the sky-coloured shore fog inside a water hexagon (Waterhex / IceHex 0xA0..0xFF,
patch_sky_transitions_v2) never got clouds and the cloud field stopped dead on the hex line.  With water=True the
overlay also walks water / ice (0 / 6) hexagons whose TAoWWaterHexagon shore uses a Sky-family set (side base byte
[hex+0x1A+dir] >= 0xA0 for a set mask bit - Ziggurat's own test at 0x55850B10) and matches their pixels against ALL
27 tile tables (Sky / Clear / Chasm).  The cloud model itself (look, speed, colours) is byte-for-byte unchanged; the
shore fog is now made of pure tile pixels, so exactly the fog gets clouds and the water never does.
v2 (user: "the clouds still arent going into the transition hex"): the water hex draws its shore pieces in
TAoWWaterHexagon.ShowDynamic, i.e. INSIDE THSMap.DrawDynamicScene - after the overlay (hooked at the prologue of
TAoWHSMap.DrawDynamicScene 0x55778A60) had already run, so it never saw the fog.  Now the main pass skips water
hexes and a second, water-only pass runs right after the dynamic scene: the call THSMap.DrawDynamicScene @0x55778A6A
-> wrapper 'dynw' (0x558E1480 'SOW2'): original call, then overlay core(mode 2).  Fog pixels are recognised by their
position on the water->sky colour line (residual check keeps units standing on the hex untouched).
Replaces the zone code in place (state: installed == sky_polish's build -> vanilla; == water build -> ours).
⚠ Re-running patch_sky_polish_v1 would see this as OTHER - revert this first.  Backup .bak_skywater.
Dry-run default; --apply; --revert.
"""
import os, shutil, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bakpath import bak_path, game_file  # noqa: E402
import struct  # noqa: E402
import patch_sky_polish_v1 as SP  # noqa: E402
import sky_clouds_overlay_asm as OV  # noqa: E402
import sky_overlay_ext_asm as EXT  # noqa: E402

EPK = game_file("AoWEPACK.dll")
B = 0x55700C00
TAG = ".bak_skywater"
CALL_AT, DDS_THUNK = 0x55778A6A, 0x55702654
DW, DW_END = 0x558E1480, 0x558E14C0


def rel(at, to):
    return struct.pack("<i", to - (at + 5))


def dynw():
    core = OV.core_va(True)
    c = bytes.fromhex("5052") + bytes([0xE8]) + rel(DW + 2, DDS_THUNK) + bytes.fromhex("5a58") + bytes([0x6A, 0x02])
    c += bytes([0xE8]) + rel(DW + len(c), core) + bytes([0xC3])
    assert len(c) <= DW_END - DW
    return c


def main():
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if (apply or revert) and SP.busy():
        print("game/editor running - close it first"); return 1
    gd = os.path.dirname(HERE)
    d = open(EPK, "rb").read()
    old = OV.blob(gd, False)[0]
    new = OV.blob(gd, True)[0]
    dw = dynw()
    ext = EXT.build(*OV.labels_va(True))                   # v3: fog code at EXTRA (water + Sky/Clear/Chasm pairs)
    c_old, c_new = bytes([0xE8]) + rel(CALL_AT, DDS_THUNK), bytes([0xE8]) + rel(CALL_AT, DW)
    zo, co, wo, xo = OV.ZONE - B, CALL_AT - B, DW - B, EXT.EXTRA - B
    cur = (d[zo:zo + len(old)], d[co:co + 5], d[wo:wo + len(dw)], d[xo:xo + len(ext)])
    van, ours = (old, c_old, bytes(len(dw)), bytes(len(ext))), (new, c_new, dw, ext)
    st = "vanilla" if cur == van else "ours" if cur == ours else "OTHER"
    print("overlay zone %#x + dynamic-scene call %#x + wrapper %#x: %s" % (OV.ZONE, CALL_AT, DW, st))
    if st == "OTHER":
        print("ABORT"); return 1
    want = van if revert else ours
    if cur == want:
        print("already %s" % ("reverted" if revert else "applied")); return 0
    if not apply and not revert:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bk = bak_path(EPK, TAG)
    if not revert and not os.path.exists(bk):
        shutil.copy2(EPK, bk)
    with open(EPK, "r+b") as fh:
        for off, b_ in zip((zo, co, wo, xo), want):
            fh.seek(off); fh.write(b_)
    chk = open(EPK, "rb").read()
    assert (chk[zo:zo + len(old)], chk[co:co + 5], chk[wo:wo + len(dw)], chk[xo:xo + len(ext)]) == want
    print("reverted" if revert else "written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
