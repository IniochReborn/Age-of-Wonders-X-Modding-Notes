---
name: no-cd-check-location
description: Where the CD check lives (AoWEPACK AoWReg unit) and the exact no-CD patch bytes the mod ships
metadata: 
  node_type: memory
  type: reference
  originSessionId: bc99310d-e7a0-464e-8b38-a64c2704c9e7
  modified: 2026-08-30T18:19:53.493Z
---

The "Please insert the Age of Wonders CD" check is in **AoWEPACK's `AoWReg` unit**, not AoW.exe (the exe only *triggers* it at startup, main block @0x45995c → gate on `TAoWEngine+0x6E` byte → `AoWReg.GuaranteeAoWCD`).

Vanilla logic (AoWEPACK VA = file + 0x55700C00):
- `AoWReg.GuaranteeAoWCD` @0x557063B8 — retry-dialog loop; Cancel exits the game.
- `AoWReg.AoWCDInserted` @0x55706370 (file 0x5770) — GetLogicalDrives, scans A–Z via ValidAoWCD, returns drive char or 0.
- `AoWReg.ValidAoWCD` @0x55706270 — `GetDriveTypeA == 5` (DRIVE_CDROM) AND FileExists(`X:\AoWSetup.exe`) AND FileExists(`X:\setup.exe`).
- Message resourcestrings `AoWE.PleaseInsertTheAoWCD[Retry]RStr` exported @0x5570835C/0x55708364.

**The shipped no-CD patch** (present in our AoWEPACK.dll AND byte-identical in Ziggurat's — classic community edit): at **file offset 0x5776** (VA 0x55706376), the 56-byte scan loop (orig starts `33 F6 E8 07 B1 FF FF 8B F8 EB 24…`) is replaced with `B3 01` (mov bl,1 = fake "CD in drive") + `90`×54, through 0x57AD. No relocs/absolutes under it — safe flat overwrite. `ValidAoWCD`, `GuaranteeAoWCD`, and AoW.exe are untouched. Region is identical in retail 1.36 and AoW+ 1.45, so the same offsets apply.

2026-08-30: applied this patch to `reference files\AoW 1.36\AoWEPACK.dpl` on user request (backup `AoWEPACK.dpl.bak_nocd`) — **that reference copy is no longer pristine**; the .bak is the pristine one.

**Why:** answers "where is the no-CD change" without re-deriving; the reference-copy caveat matters for future vanilla-baseline diffs.
