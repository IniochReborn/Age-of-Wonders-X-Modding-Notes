---
name: city-tcmap-adjacent-cities
description: "Combat-start AV at AoWTCPCK 0x41B742 = battle map file not loaded; city TCMap name counts ANY neighbouring TCity; fix patch_city_tcmap_same_city_v1 (11/13, applied, untested)"
metadata:
  node_type: memory
  type: project
  originSessionId: 2c63b60f-49b3-44ba-9088-66d07407269f
  modified: 2026-11-14T04:59:26.964Z
---

**Symptom (2026-11-13):** user reported "crash/freeze opening another player's map" and "starting combat causes a bunch of errors". Real error: EAccessViolation at AoWTCPCK 0x41B742 (write [nil+0xE4]), called from 0x424FB7 in the combat set-up 0x4245EC — tactical scene global [0x46C064] is nil because the TCMaps file did not load.

**Cause:** for a TCity the name is `TCMaps\0<digits>c000.HSM`, one digit per neighbour direction 1..6 whose hex holds a TCity (loop 0x424A02..0x424A82, FindObject call 0x401DB4 at 0x424A42, class global 0x46ECA8 = TCity). Any city counts, so touching cities give a shape with no file (existing: 0xxx 02xx 05xx 012x 023x 034x 056x 0126 0345).

**Fix:** `patch_city_tcmap_same_city_v1.py` — call routed through cave 0x454500 (13 B) returning nil unless the found city == [ebp-0x44]. Backup .bak_citytcmap1. APPLIED 11/13, awaiting the user's retest. Not verified that the failing city really touched another (assumption: mine). Unrelated to the shared-crops patch ([[patch_city_wall_v1]]).

**How to apply (diagnosis lessons):**
- WER "AppHangB1 / Top level window is idle" entries for AoWx.exe are NOT proof of a hang — the game's loop was ticking normally; do not build theories on them.
- Ask the user exactly what they do/see before theorising; I wasted a round on a crop "ping-pong" theory.
- Tools: `diag_veh_logger.py --pid <pid>` attaches the exception logger to a RUNNING game (added 11/13); `diag_hang_watch.py` v2 keeps a 40 s ring of thread stacks (hang_ring_<name>.txt). Other combat set-up name logic: structure class switch at 0x4248CA, bridge terrains cave 0x454480 (Sk/Ch).
