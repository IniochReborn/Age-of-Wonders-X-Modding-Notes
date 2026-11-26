---
name: ug-palette-tabs
description: "2026-11-14 editor Underground Tiles palette got Grass/Steppe/Desert/Snow/Wasteland tabs (patch_ug_palette_tabs_v1: Release.hss EditID/EditIndex moves + 5 cloned DFM grids); verified live by me, user unconfirmed; how grids map to palette pages"
metadata:
  type: project
---

**APPLIED 11/14, verified live by me (editor launched, all 5 new tabs show the right decorations), user unconfirmed** — `patch scripts/patch_ug_palette_tabs_v1.py` (.bak_ugtabs for AoWDevX.exe + Release\Release.hss; ⚠ ship BOTH together).

User ask: underground tabs like the surface's, without changing any IDs. Underground is now Places | Objects | Dirt | Grass | Steppe | Desert | Snow | Wasteland | Developer (my choice: Dirt kept as its own tab, in its old third position).

- Cause of the old mess: underground twins of the surface decorations (own RIDs) sat in row blocks of page 22 (uObjects: Grass from cell 32, Steppe 180, Desert 304) and page 10 (Dirt: Snow 76, Wasteland 200). Each block = the surface page layout + that offset.
- Fix in Release.hss = in-place u32 writes of field 2 (EditID) / field 3 (EditIndex) only + CRC. RIDs untouched.
- ⭐ Grid → page mapping: `TEResourceEditSettings.GetEditID(name)` (Enginep 0x5551B32C) looks the grid's COMPONENT NAME up in the name list stored in Release.hss (ids 1..44); an unknown name gets the first free id at run time (order-dependent — avoid). The list still holds names of grids that no longer exist, on unused ids: uSpeedBarMOR 1, FastSelectMOR 2, uCitiesMOR 8, CitiesMOR 12, UnderGroundSpeedBar 18, SurfaceSpeedBar 19 (27 EResourceGrid11 / 28 CPlacesMORu unchecked). The new grids took those names: Grass = uCitiesMOR (8), Steppe = uSpeedBarMOR (1), Desert = FastSelectMOR (2), Snow = UnderGroundSpeedBar (18), Wasteland = CitiesMOR (12). Still free: SurfaceSpeedBar (19).
- DFM: 5 clones of DirtSheet/DirtMOR inserted after DirtSheet (sheets uGrassSheet, uSteppeSheet, uDesertSheet, uSnowSheet, uWastelandSheet2); no published fields needed (grids carry only OnLinkToResourceList). TMAINFORM grew +3564 B → .xprn raw 0x74600, SizeOfImage 0x15E000. Old hidden uWastelandSheet / page 9 (3 chasm records) left alone.
- Live-test driver recipe (no foreground steal): launch `AoWDevX.exe <map>` with SW_SHOWNOACTIVATE, PrintWindow(…, 2) capture, PostMessage WM_LBUTTONDOWN/UP to the child HWND (toolbar TPanel for speed buttons, the TPageControl for tabs). On this 4K/300% desktop: screen px = capture px × 3 − 24. Related: [[devx-screenshot]], [[cloud-variants]], [[aowdevx-binary-notes]].
