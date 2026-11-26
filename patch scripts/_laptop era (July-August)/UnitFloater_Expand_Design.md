# Unit Floater expansion — all units visible + specials tabs for races

**Date:** 2026-08-06 · **Script:** `build_scripts/build_unitfloater_expand.py` ·
**Target:** `AoWDevX.exe` · **Backup:** `AoWDevX.exe.pre-unitfloater_expand` · **Status:** applied

## Problem

1. The Unit Floater (shared popup used to pick units for structure productions,
   race unit lists, etc.) could only ever show **160 units** in a tab — units past
   that were unviewable/unselectable, and the game has more than 160 units.
2. The floater shown for **race** unit lists / default city productions
   (opened from `TRaceResourceEditForm`) had only the **All** tab — no
   Creatures/Humanoids tabs.

## Architecture (findings)

- `TUnitFloater` form lives in **AoWDevX.exe**, DFM at file `0xD6200–0xD6E8A`
  (global instance ptr at `[0x42F100]`). Children (field offsets on the form):
  `MainPageControl +0x1DC`, `UnitSelectionSheet +0x1E0`, `UnitTabControl +0x1E4`,
  `UnitSelectionGrid +0x1E8`, `HeroSelectionSheet +0x1EC`, `HeroControlGrid +0x1F0`.
- `TUnitTabControl` / `TUnitIndexGrid` are implemented in **AoWEPACK.dpl**
  (`UnitTabC` / `UnitIGrd` units; VMTs `0x55800EA4` / `0x557FF7A8`).
  The tab control owns a `AoWE.TUnitSelectionControl` at `+0x140` which builds
  the tab list and per-tab unit lists (`UpdateSelection @ 0x5574DCC4`):
  - `+0x2C/+0x2D` min/max unit level filter, `+0x2E` alignment filter
  - `+0x30` TBitList race-tabs enabled, `+0x34` TBitList specials enabled
    (both created with default-true byte `+0x10`)
  - `+0x38` race categories, `+0x3C` specials (0=Humanoid, 1=Creatures,
    2=Siege Machines; tab index = −(i+1)), `+0x40` All list (tab index −16/0xF0)
  - `+0x44` selected unit index
  - **flags: `+0x49` race tabs, `+0x4A` specials tabs, `+0x4B` All tab**
- Each editor context configures the shared floater then calls
  `TUnitTabControl.UpdateSelection`. Config sites in AoWDevX.exe (flag writes):
  `0x409421` (construction, +level filter 1–4), `0x40A0B1`, `0x40A81D`,
  `0x40AC57`, `0x41A2E3` = all three tabs on; **`0x4117DB`
  (`TRaceResourceEditForm.FormCreate`) = All only (races=0, specials=0)**.
- **160 cap root cause:** `ILPACK ImageLib.TCustomImageDrawGrid.UpdateDimensions
  (0x55214D24)` — with `GrowDirection=ilHorizontal` (enum 1) the grid grows by
  adding **columns** (`SetColCount`, RowCount untouched), and `SetColCount
  (0x55214EB0)` clamps to `MaxColCount +0x1D0`. The floater grid's DFM had
  `ilHorizontal` + `MaxColCount=8` + `RowCount=20` → 8×20 = 160 cells, hard cap.
  `ilVertical` (enum 2) grows **rows**, clamped by `MaxRowCount +0x1CC` which is
  0 = unlimited; grid already has `ScrollBars=ssVertical`.
  (Main-form unit palette also uses `ilHorizontal` but with `MaxColCount=0`,
  so it grows sideways unbounded — not capped, left untouched.)

## Patches (all AoWDevX.exe, file offsets)

| # | Offset | Change |
|---|---|---|
| P1 | `0x10BE3` (VA 0x4117E3) | `mov byte [eax+0x4A],0` → `,1`: race-context floater gains Humanoid/Creatures/Siege Machines tabs |
| P2 | `0xD626A` | DFM `ClientHeight` 253 → 475 (≈8 unit rows visible instead of ≈3) |
| P3 | `0xD6A4C` | DFM `GrowDirection` ident `ilHorizontal` → `ilVertical`; ident is 2 bytes shorter so DFM tail (1058 bytes) shifted up 2, block zero-padded (trailing bytes after root object are ignored by TReader) |

Race tabs in the race-context floater were deliberately left off (`+0x49`
stays 0) — flip the byte at file `0x10BDF` (VA 0x4117DF) the same way if ever
wanted.

## Revert

Copy `AoWDevX.exe.pre-unitfloater_expand` over `AoWDevX.exe`.
