---
name: sphere-combine-opposing-elements
description: "Wizard sphere selection: Life/Death still mutually exclusive, but Fire/Water and Earth/Air CAN now be combined (each pair capped at 4 combined picks). Copied from BXL/Ziggurat. AoWEPACK.dll, 2026-07-23."
metadata:
  node_type: memory
  type: project
  originSessionId: ae619055-3278-433b-b71b-cf21e5789ad7
  modified: 2026-07-23T07:40:57.021Z
---

**GOAL (user, copy from Ziggurat/BXL):** Vanilla forbids picking opposing magic spheres (Life/Death, Fire/Water, Earth/Air). Change so Life/Death STILL can't combine, but Fire/Water and Earth/Air CAN, each opposing-element pair limited to 4 combined picks. Applied 2026-07-23. Backup `AoWEPACK.dll.bak_spheres`.

**SPHERE INDEX ENUM (verified from TMagicSphereRStr array @0x558E8118):** 0=Cosmos, **1=Life, 2=Death** (kept blocked), **3=Earth, 4=Air**, **5=Fire, 6=Water** (element pairs, now combinable). (TSpell sphere field = [spell+0x20].)

**THE FUNCTION: `TLeader.CanAddSphere` @0x5578B1F8** (AoWEPACK.dll, VA=file+0x55700C00; eax=Self leader, dl/bl=sphere to add; returns al=1 can-add / 0 no). Prologue: count=[[esi+0xa0]+8], maxpicks=[esi+0x9c]; if count>=maxpicks -> fail. Then a per-sphere check calling **GetSpherePicks 0x5578B17C** (eax=leader, dl=sphere -> al = picks currently in that sphere). Vanilla blocked all 3 pairs symmetrically: `if bl==X and GetSpherePicks(opposite)!=0 -> fail` for (1,2),(3,4),(5,6).

**THE CHANGE = copied BXL's Ziggurat CanAddSphere byte-for-byte** (both binaries are the SAME base build 0x55700000, same size 2785792, function at same VA; GetSpherePicks 0x5578B17C verified byte-identical; AddSphere @0x5578B2E4 boundary verified identical). BXL's logic:
- **1<->2 (Life/Death): unchanged** — still `if has(opposite): fail`.
- **3<->4 and 5<->6 (Earth/Air, Fire/Water): replaced** with a combined cap — `al = GetSpherePicks(a)+GetSpherePicks(b); if al<4: success else fail` (so a pair's combined picks can reach at most 4). Overall maxpicks top-check still applies.
- His rewrite fit in-place (padded with NOPs @0x5578B2CD-D8), no cave. Copied bytes 0x5578B1F8..0x5578B2E4 (90 bytes changed, all within the function; nothing else touched). No overlap with our caves (@0x5580F000+).

**REVERT:** restore `AoWEPACK.dll.bak_spheres`.

**NOT patched (matches BXL — he only changed AoWEPACK.dpl):** AoWSetup.exe (MP/launcher wizard setup). If MP sphere-pick still restricts opposing elements, AoWSetup.exe may have its own copy of the rule to patch. In-game leader customization (start of game) uses this engine function, so it IS covered. See [[bxl-reference]] (GetSpherePicks 0x5578B17C, TSpell +0x20 sphere).

**CONFIRMED WORKING in-game 2026-07-23** (Fire+Water and Earth+Air combine up to 4; Life+Death still refused).
