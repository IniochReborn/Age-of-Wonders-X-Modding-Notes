#!/usr/bin/env python3
r"""
Sky polish v8 (2026-10-31) - supersedes v7 (revert patch_sky_polish_v7 first; this one re-applies all of it).

User after v7: "get rid of the cloud brightening ... i meant the slow moving clouds, not some new added wave".
Overlay only: the Chasm flash glow (CHS_CGLOW) is removed; instead every cloud layer breathes slowly - a pulse
(64-step sin^2, CPULSE_MS per step) whose phase comes from the drifting cloud field itself (layer-2 coordinates,
8-px texels, bilinear) so patches of clouds brighten and fade as they drift: Sky/Clear cloud opacity up to
+35 %, Chasm black clouds up to 27 % lighter.  Pulse cached per 4x2 block with the cloud value.
Everything else = patch_sky_polish_v7.  Backups .bak_skypolish8.  Dry-run default; --apply; --revert.
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import patch_sky_polish_v6  # noqa: E402,F401  (installs the v3..v6 overrides on v2)
import patch_sky_polish_v2 as V2  # noqa: E402

V2.TAG = ".bak_skypolish8"

if __name__ == "__main__":
    sys.exit(V2.main())
