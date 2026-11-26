---
name: aowepack-dll-is-live
description: AoWx.exe loads AoWEPACK.dll (verified import table); AoWEPACK.dpl is a stale drifted copy - never patch the .dpl
metadata: 
  node_type: memory
  type: project
  originSessionId: 0640c8a2-97cf-4093-817b-403e78ebf145
  modified: 2026-08-07T00:45:54.425Z
---

**AoWx.exe imports AoWEPACK.dll, AoWTCPCK.dll, AoWTools.dll** (verified in its
import table 2026-08-06) — the .dll files are what the game loads, despite most
other packages being .dpl (HSEPack.dpl, EngineP.dpl, etc.).

`AoWEPACK.dpl` in the game dir is a **stale copy** that has drifted ~9 KB from
the .dll (different patch history; even has a different baked version number,
224 vs 410→402). Patching it does nothing in-game. Some older BXL docs (e.g.
Turn_Undead_Damage_RES.md) say "Binary: AoWEPACK.dpl" — that reflects the
home-PC-era setup or is simply loose wording; on this install the .dll is live
(hence all the AoWEPACK.dll.bak_* backups).

Cave space in AoWEPACK.dll: the old 0x5580E000-0x5580E700 region is nearly
full; there is a huge verified-zeros run at **file 0x10F370-0x1E6E10
(VA 0x5580FF70+, ~883 KB)** inside CODE. First allocation there:
cave_spring @0x55810000 ([[spring-of-life-wasteland]]).
