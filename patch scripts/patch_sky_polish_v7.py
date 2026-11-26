#!/usr/bin/env python3
r"""
Sky polish v7 (2026-10-31) - supersedes v6 (revert patch_sky_polish_v6 first; this one re-applies all of it).

User after v6 (editor OK): "chasm looks great, but lets make the lightning slightly more subtle/less bright ...
add more lightning webs behind it, but make those very very subtle ... also add very subtle brightened pulses to
the clouds".  Overlay only (sky_clouds_overlay_asm / sky_clouds_art):
  * main web LUT peak 220 -> 185;
  * far webs: the web texture again at 2x density (world*2), own drift, flash phase +21, strength 40/256,
    colour CHS_WEB2;
  * the black clouds glow faintly (CHS_CGLOW, 60/256 x cloud density x local flash) when lightning flashes nearby.
Everything else = patch_sky_polish_v6.  Backups .bak_skypolish7.  Dry-run default; --apply; --revert.
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import patch_sky_polish_v6  # noqa: E402,F401  (installs the v3..v6 overrides on v2)
import patch_sky_polish_v2 as V2  # noqa: E402

V2.TAG = ".bak_skypolish7"

if __name__ == "__main__":
    sys.exit(V2.main())
