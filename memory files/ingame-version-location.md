---
name: ingame-version-location
description: In-game version number lives in AoWEPACK.dll TAoWEngine.Create as three code immediates; file offset 0x9701B holds part 3 (push imm32)
metadata: 
  node_type: memory
  type: project
  originSessionId: 0640c8a2-97cf-4093-817b-403e78ebf145
  modified: 2026-09-03T06:44:03.935Z
---

The version the game displays (e.g. "1.37.0410") is NOT read from
`X\Documentation\changelogs.txt` or any text file — editing those does
nothing in-game. It is set in **AoWEPACK.dll**, `TAoWEngine.Create`
(VA ~0x55797C13, file offsets below) as three immediates:

- 0x97013: `xor edx,edx; inc edx` → part 1 = 1
- 0x97016: `xor ecx,ecx; mov cl,0x25` → part 2 = 37
- 0x9701A: `push imm32`, operand at **0x9701B** → part 3 (patched per release via `patch scripts/patch_version_<N>.py`, currently **410** = `9A 01 00 00`, 2026-09-21; patch_version_410.py, backup backup\AoWEPACK.dll.bak_version409 via bakpath)

Part 3 renders zero-padded in-game (410 → "0410"), so the manual's old
"Version 1.37.0410" badge was game-sourced, not a typo — the binary really
said 410 while the release was labeled 1.37.401. Text files use the
unpadded form ("1.37.402") per user preference.

Patch script: `reference files\BXL\build_scripts\patch_version_402.py`
(dry-run/--apply, backs up to AoWEPACK.dll.bak_version410).

Gotcha: **AoWEPACK.dpl** is a stale legacy copy (has 224 = `E0 00 00 00`
at the same offset) and is not what the game loads — leave it alone; all
live patches target the .dll (see the many `.bak_*` files).
