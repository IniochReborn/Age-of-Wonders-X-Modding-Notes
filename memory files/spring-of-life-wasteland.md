---
name: spring-of-life-wasteland
description: "Spring of Life patched 2026-08-06 - blessing only for living (or only undead on wasteland), poison for living on wasteland; v3 core CONFIRMED in-game, v4 adds Pestilence popup + APest SFX"
metadata: 
  node_type: memory
  type: project
  originSessionId: 0640c8a2-97cf-4093-817b-403e78ebf145
  modified: 2026-08-07T22:27:53.015Z
---

CURRENT LIVE STATE (2026-08-07): **v5 APPLIED, awaiting in-game test.** Sound
sites stay byte-for-byte vanilla; the cave itself now plays APest on wasteland
(replicating the vanilla gate found by disassembly @0x557A3E22..66: play if
army owner [army+0x12] == local player [[0x558E9494]]+0xA5, else if
TAoWHSMap.Watching with spring esi virtuals +0x74/78/7C — args level, 0,
y→ecx, x→edx, ret 8), gated on bh≠0 (all-shielded = silent), placed BEFORE
TArmy.Validate. Cave returns AL=0 on wasteland → hook skips the vanilla
sound/anim block (no chime, no sparkle there); normal springs fully vanilla.
sfx_pick/anim_gate removed from cave; --revert-sites flag removed (sites
always vanilla now, restored if a prior call found). Diag scratch+3: 2=APest
played, 3=gated off. Behavior + popup were confirmed stable in v4.2.

HISTORY: v4's two 5-byte site patches (SFX pick @0x557A3E67 replacing the
`mov eax,ENCHP02` and anim gate @0x557A3E94 rerouting `call Visible` with a
pop-ebx/forward-args/jmp-ebx trick) caused "Exception occured during
TArmyDefaultMoveTE" (Network.dpl token-wrapper catch-all) on spring
placements, plus army corruption (disband/duplicate) from the interrupted
move token. Empirically proven: sites reverted → stable. Static analysis
never found the defect — do NOT re-add those site patches.

NEXT STEP: user tests v5 in-game (wasteland spring → APest sound + popup, no
chime/sparkle; normal spring → vanilla chime+sparkle; watch for any
TArmyDefaultMoveTE exception). If it recurs even with sites vanilla, the
suspect becomes PlaySample-from-cave timing, not the sites.

Diagnostics: scratch @0x558FA8F0 (BSS RW slack, proven writable): +1 stage
breadcrumb, +4 terrain; reader = re_tools/spring_crumbs.py (reads live
process). Crumb/scratch writes proven harmless. KEY VANILLA FACT found during debugging: vanilla
TSpringOfLife.ArmyPlaced has a TERRAIN GATE — it reads [self+4]+0x14 (the
spring's field terrain) and skips the blessing entirely on Snow(3) and
Wasteland(5) — a "frozen/dead spring" is vanilla design. v1/v2 appeared to
"do nothing on wasteland" solely because of that gate. v3 NOPs the wasteland
je (0x557A3F53); Snow stays inactive. (A v2 theory that HSE has separate
"message-hub" vs "terrain cell" field objects was WRONG — map object +4 IS
the field, +0x14 IS its terrain; both the [argMO+4]+0x14 read and the
GetLocation→TMapContainer.GetField read are valid.)

- non-wasteland: blessing/heal for living units only, undead get nothing
- wasteland (terrain 5 or 0xB): blessing/heal for undead only; living units get
  the poison-cloud effect (ExecuteStormDamage Pestilence 6, magic shield
  respected, immunity blocks)
- undead test = race 0x0B or Animated (0x81), same as Turn Undead

Build: `reference files\BXL\build_scripts\build_spring_wasteland.py`
(dry-run/--apply, backup AoWEPACK.dll.bak_spring_wasteland). Full RE trail in
`reference files\BXL\Spring_Of_Life_Wasteland_Design.md` (hook @0x557A3DEF in
ExecuteNaturesBlessing, cave @0x55810000). See [[aowepack-dll-is-live]] for
why the .dll not the .dpl.

Remaining deliberate gaps: no looping cloud visual; poison str 4 (1×4
wasteland on-type bonus); blessing sound+anim suppressed when nobody blessed
(poison-only placements get APest sound + popup, no sparkle).

**2026-11-14 UG wasteland picture:** user: spring "doesn't change on wasteland underground". Painted UG wasteland is terrain 5 too (hss palette page 10), so the behaviour cave is level independent; the miss was ART: structure image slot = terrain id, surface record (hss child 207) slot 5 = dead spring (STR_SOL image 11), UG record (child 226, page 23) slot 5 was a copy of the flowing spring. `patch_ug_spring_wasteland_gfx_v1.py` (Release.hss, .bak_ugspring, in-place --revert) copies the surface slot 5; APPLIED, not checked in game. ⚠ The old "0xB = cave wasteland" id in the cave is now Chasm (harmless: no springs there). Ship Release.hss.
