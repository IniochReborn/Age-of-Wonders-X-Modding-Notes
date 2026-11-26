---
name: hexgrid-thick
description: 2026-10-18 F5 hex grid overlay doubled to 2 px via Images\Flags.ilb #7 (patch_hexgrid_thick_v1.py); DrawGrid RE; ship Flags.ilb
metadata:
  type: project
---
F5 (AoWx.exe 0x451409→0x451618) toggles [map+0xCA] on the combat map [0x45EBDC] else strategic [0x45DF7C]; both draw loops (AoWEPACK 0x55778A78, TCPCK 0x41BFE7) call TAbstractAoWHSMap.DrawGrid 0x55772DA8, which blits **Images\Flags.ilb #7 hexgrid.BMP** (48x32, top edge + two left diagonals per tile) per field. `patch_hexgrid_thick_v1.py` adds an inward 2nd pixel (49→97 ink px), backup `backup\Images\Flags.ilb.bak_hexgrid`. APPLIED 10/18, untested. ⚠ release zip must `--add Images\Flags.ilb`.
**10/18 later:** user OK with 2 px, asked to try 3 px → script now takes `--px 2|3` (default 3, rebuilt from the vanilla backup each time); 3 px APPLIED. Go back with `--apply --px 2`.

**Option 10/18 (user: in-game Settings→Display dropdown + AoWSetup dropdown "Hex Grid Thickness (F5)": Extra/Default/Vanilla):** thick_v1 REVERTED (image 7 vanilla again); `patch_hexgrid_option_ilb_v1.py` appends #92 (2 px) / #93 (3 px) to Flags.ilb; `patch_hexgrid_option_v1.py` = AoWx.exe section `.xhgr` 0x630000 (TVIDEODIALOG DFM rebuilt 280→290 px, new row y 212, DlgShow → hg_show, saves on pick) + AoWEPACK DrawGrid `mov edx,7/call Get` @0x55772E7C → cave 0x5581F800 (host AoWx.exe only, count-checked, fallback #7); `build_aowsetup_hexgrid_dropdown.py` = AoWSetup `.xhgd` 0x514000, row under Language, OK saves (hooks after the Campaigns dropdown → revert first). Registry HKCU\...\Age of Wonders X\General\"Hex Grid Thickness" DWORD 3/2/1, default 2. Revert order: setup, option, ilb. ⚠ patch_aowx_cursor_coords --revert restores a whole-file backup (would wipe .xhgr). Ship AoWx.exe, AoWEPACK.dll, AoWSetup.exe, --add Images\Flags.ilb. APPLIED, VEH 6, untested.
