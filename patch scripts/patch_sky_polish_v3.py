#!/usr/bin/env python3
r"""
Sky polish v3 (2026-10-31) - supersedes v2 (revert patch_sky_polish_v2 first; this one re-applies all of it).

User after v2: "clouds look better but now it seems low framerate or something, like it isnt smooth enough
animation... also for chasm ... make it look more like purple pulsing lightning 'webs' and black 'clouds'".
Changes vs v2 (overlay only, sky_clouds_overlay_asm / sky_clouds_art):
  * smooth motion: cloud positions in 1/16 px, both layers bilinear-filtered (v2 moved in 2/4-px texel jumps);
  * cost: cloud field computed once per 4x2 pixel block (64-slot cache in the frame) -> ~165 instructions per
    processed pixel in the emulator (v2 ~330);
  * Chasm: violet haze between black smoke clouds + domain-warped Voronoi lightning webs (own 256x256 texture at
    AoWEPACK 0x5589C000..0x558AC000, patches only) flickering with a double flash, phase varying across the map.
Everything else = patch_sky_polish_v2 (combat overlay, Clear combat hexagon, editor buttons, Clear-over-Sky fix).
Backups .bak_skypolish3.  Dry-run default; --apply; --revert.
"""
import os, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sky_clouds_overlay_asm as OV  # noqa: E402
import patch_sky_polish_v2 as V2  # noqa: E402


def epk_patches(gd):
    z, tex, web, ents = OV.blob(gd)
    old = b"\xe9" + struct.pack("<i", OV.HOOK_ZIG - (OV.HOOK + 5)) + b"\x90"
    new = b"\xe9" + struct.pack("<i", ents["main"] - (OV.HOOK + 5)) + b"\x90"
    return [(OV.HOOK, old, new), (OV.ZONE, bytes(len(z)), z), (OV.TEX, bytes(len(tex)), tex),
            (OV.WEB, bytes(len(web)), web)], ents


V2.TAG = ".bak_skypolish3"
V2.epk_patches = epk_patches

if __name__ == "__main__":
    sys.exit(V2.main())
