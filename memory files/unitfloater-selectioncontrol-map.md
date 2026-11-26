---
name: unitfloater-selectioncontrol-map
description: RE map of editor Unit Floater / TUnitSelectionControl internals + 2026-08-06 expand patch
metadata: 
  node_type: memory
  type: project
  originSessionId: 94c05805-50ad-4e48-b1ca-2c96994bfa58
  modified: 2026-08-06T22:51:54.623Z
---

Editor Unit Floater patched 2026-08-06 (`build_unitfloater_expand.py`, doc
`UnitFloater_Expand_Design.md` in BXL): uncapped the 160-unit All tab
(DFM GrowDirection ilHorizontal→ilVertical; cap was MaxColCount=8 × RowCount=20
via ILPACK `TCustomImageDrawGrid.UpdateDimensions`), floater ClientHeight
253→475, and race-context floater got Humanoid/Creatures/Siege tabs
(flag byte +0x4A at VA 0x4117E3 in TRaceResourceEditForm.FormCreate).
Backup: `AoWDevX.exe.pre-unitfloater_expand`.

Key internals (full details in the design doc): TUnitFloater DFM in
AoWDevX.exe @0xD6200, global instance ptr [0x42F100]; grid/tab classes in
AoWEPACK.dpl (`UnitIGrd`/`UnitTabC`); `AoWE.TUnitSelectionControl` flags —
+0x49 race tabs, +0x4A specials tabs, +0x4B All tab, +0x2C/+0x2D level filter;
per-context config sites in AoWDevX.exe write these bytes then call
`TUnitTabControl.UpdateSelection`. Delphi DFM idents can be shortened in
place if the DFM tail is shifted and zero-padded (TReader ignores trailing
bytes). Related: [[editor-patch-audit-2026-08-05]]
