---
name: teleport-padless-fix
description: "2026-11-04 ALL teleporters dead since water-teleporter v2 (padless) - part-byte bug fixed (patch_teleport_padless_fix_v1); editor teleporter level drop-down + status bar name w/o \"Level\" (patch_devx_teleport_levelname_v1)"
metadata:
  node_type: memory
  type: project
  originSessionId: 51e7ec29-dff4-436b-b86a-657a622b25dd
  modified: 2026-11-05T00:53:39.762Z
---

**Bug (mapmaker, The Groll 1f: teleporter 19/104/5 -> 31/98/5 "does nothing"):** not level-related. Since
patch_teleport_water_v2 (10/31) cleared TTeleportResource res+0x44 (padless, so water teleporters stay water), EVERY
teleporter/Divine Gate stopped working. HSEngine calls each structure on a map field with its footprint PART byte:
TMapField.UpdateMapField (HSE 0x55608028) -> VMT+0xEC {field, part}; TMapField.MoveExclusive (HSE 0x55608204) ->
VMT+0xD8 {ctx, field, part}. TTeleport 0x557A4E1C (field flag 0x8000) / 0x557A4E2C (pathfinder edge via 0x55745928)
only acted for part 0; pad placement = part 0, generic placement = footprint part (editor status "HS:3").
**Fix APPLIED 11/04, untested:** `patch_teleport_padless_fix_v1.py` (.bak_telepadfix): both handlers act when the
field (+0x10/+0x11/+0x12) == teleporter GetXhx/GetYhx/GetLhx (VMT +0x74/+0x78/+0x7C). Cave AoWEPACK 0x558E0A80 'TPF1'.
Lesson: changing a structure's pad/placement mode changes the part byte every HSE per-field callback receives.

**Editor UI BUILT 11/04 (apply blocked: editor was open):** `patch_devx_teleport_levelname_v1.py` (.bak_telelvl):
Teleport Properties L spinner hidden -> runtime TComboBox of visible levels (Firmament, Surface, Caverns, Depths, Abyss..
via NAMEFN, Objects[] = level), dialog widened 3x spin height, combo ptr in LtoEdit.Tag (+0x0C); status bar "Level %s"
-> "%s" (4 LoadResString sites, AoWEPACK LevelXRStr untouched); EditStatusBar panel 1 width 65->100 in live TMAINFORM
(.xprn 0x4ED000 - rewritten by prune/theme scripts -> re-run after them). Stubs .tres 0x4E2080..B0 (VirtualSize
0x76->0x100) via v3 trampoline 0x429F12; AoWEPACK zone 0x558E0B00 'TLV1'. Next free AoWEPACK 0x558E0E00.
Names: level 5 = "Abyss II" (4 = Abyss) - user had said "Abyss III instead of 5".
VCL30 facts: TControl Left/Top/Width/Height +0x30..+0x3C, Visible +0x44, FParent +0x24; TComponent Tag +0x0C,
FComponents +0x10; TComboBox Items +0x118, Style +0x121; TStrings VMT Add +0x34, AddObject +0x38, GetObject +0x18,
Clear +0x40. Keystone: labels k1..k7 = AVX-512 mask regs -> "Invalid operand".
Related: [[map-levels-29-plan]], [[teleport-firmament]], [[editor-brush-repair-telewater]].

**UPDATE 11/04 (live probe, tele_field_probe.py, elevated):** the part-byte theory was WRONG - live fields show the
teleporter at part 0 with flag 0x8000; patch_teleport_padless_fix_v1 REVERTED. Real cause: both Groll teleporters sit on
internal level 6 (Abyss III) but their dest Z = 5 (Abyss II = solid rock terrain 7 there) - the mapmaker counted
Firmament as -1 (Abyss III = 5). Fix = set dest to Abyss III via the new drop-down. In-game AoWEPACK was REBASED
(0xE20000) that session - PIC caves matter. Probe: `tele_field_probe.py aowx|devx x y z ...` (needs RunAs).
Editor patch v1.1: first build crashed (AV 0x4197B8 read 0x27B) - `push ebx` was placed AFTER the SetBounds width/height
pushes, so SetBounds got ebx as AHeight and ebx came back = width. Script now updates an older TLV1 zone in place.
