---
name: editor-about-dialog
description: "Editor Help->About dialog rebranded to AoWDevX (title, label, version 1.36->1.37, and app icon swapped in). AoWDevX.exe patch, applied 2026-07-22."
metadata:
  node_type: memory
  type: project
  originSessionId: ae619055-3278-433b-b71b-cf21e5789ad7
  modified: 2026-07-23T05:47:33.911Z
---

**GOAL:** Editor (AoWDevX.exe) Help -> About window still showed vanilla branding. Rebranded to AoWDevX. Applied 2026-07-22, **CONFIRMED WORKING in-editor**. Backup `AoWDevX.exe.bak_about`.

**FOUR CHANGES (all in AoWDevX.exe; VA = file + 0x400C00):**
1. **Form title** "About AoWEd" -> "About AoWDevX"  — DFM `TAboutDlg` form Caption (`06 0b "About AoWEd"` -> `06 0d "About AoWDevX"`, +2 bytes).
2. **Big label** "AoWEd" -> "AoWDevX" — DFM `TLabel Label1` Caption (`"Caption" 06 05 "AoWEd"` -> `06 07 "AoWDevX"`, +2 bytes).
3. **Icon** vanilla 16-color editor icon -> AoWDevX.exe app icon — DFM `TImage Image2.Picture.Data` embedded TIcon replaced.
4. **Version** "1.36.330" -> "1.37.330" — the "36" is a hardcoded `mov eax,0x24` in the version builder; changed the immediate byte.

**KEY RE — how the About version string is built:** No `version.dll` import; the string is ASSEMBLED at runtime, NOT read from VERSIONINFO. `TAboutDlg.FormCreate @0x42E330` calls builder **`0x42800C`** which does `IntToStr(1) + "." + IntToStr($24=36) + "." + IntToStr(<dynamic build=330 from global [0x432894] method 0x401F80>)` = "1.36.330", then sets the VersionLbl caption. So **"36" = the immediate in `mov eax,0x24` @VA 0x428041 (b8 24 00 00 00); the 0x24 byte is at file 0x27442.** Changed 0x24 -> 0x25 => shows "1.37.330". ("1" and "330" left as-is: "1" is `mov eax,1`, "330" is the engine build number, dynamic.) The DFM `VersionLbl` static caption is just "Version:"; FormCreate overwrites the number label. NB the exe's VERSIONINFO resource itself still says 1.36.53.148 — the About box does NOT use it, so it was left untouched (change RT_VERSION @0xDBDE8 FIXEDFILEINFO+strings only if you want the file-properties version to match).

**ICON DETAIL (lossless in-place-format swap):** App icon = RT_ICON id1 @file 0x446C4, single 32x32 **32bpp** (4264 B) but uses only **7 opaque colors** (#000000,#00E000,#C0C0C0,#404040,#FF0000,#FFFF00,#808080) + binary alpha. The DFM's vanilla icon is 32x32 **4bpp** (766-byte .ico: ICONDIR 6 + ICONDIRENTRY 16 + DIB 744 [BMIH 40 + 16-color pal 64 + XOR 512 + AND 128]). Rebuilt the app icon losslessly as a 766-byte 4bpp .ico (7 colors fit in 16-color palette) so it drops into `Picture.Data` at the SAME size — Delphi-3 TIcon reads it identically to the original. Blob = `05 "TIcon"` + .ico, vaBinary length 0x304 unchanged.

**DFM RELOCATION (why + how):** `TAboutDlg` DFM = RT_RCDATA resource named `TABOUTDLG`, file 0x464BC / RVA 0x49EBC / size 2225. Only the 2 captions changed size (+4 total; icon is same-size); only 3 bytes of alignment slack followed the resource, so it couldn't grow in place. `.rsrc` is the LAST section (raw 0x42600 + 0x99C00 = EOF 0xDC200), so relocated the new 2229-byte DFM by APPENDING it and repointing:
- New DFM appended @file 0xDC200 -> RVA 0xDFC00 (padded to FileAlignment 0x200, new EOF 0xDCC00). Old DFM bytes @0x464BC left as dead space.
- `TABOUTDLG` IMAGE_RESOURCE_DATA_ENTRY (@file 0x43290): OffsetToData 0x49EBC->0xDFC00, Size 2225->2229.
- `.rsrc` section hdr (@file 0x2C0): VirtualSize + SizeOfRawData -> 0x9A600.
- OptionalHeader.SizeOfImage (@file 0x150): 0xE0000 -> 0xE1000. DataDir[RESOURCE].Size (@file 0x18C) -> 0x9A600.
Validated: pefile reparses clean, resource reads back = new DFM (captions + icon + palette all confirmed). Emulation not needed (no code caves; pure resource/data + 1 immediate byte).

**MAIN-WINDOW TITLE BAR "AoWEd" -> "AoWDevX" — SHELVED & REVERTED 2026-07-23 (minor; user dropped it).** Two attempts: v1 AV'd (bad cave, see landmine below); v2 (dead-DFM cave) loaded fine BUT the title bar STILL showed "AoWEd" — **repointing Application.SetTitle had NO visible effect, so the editor's visible top-bar text is NOT Application.Title.** The real source is still unknown — the visible "AoWEd" comes from somewhere else (candidates for a future attempt: the TMainForm.Caption is set at runtime — DFM caption is "Age of Wonders Editor" but maybe overwritten; OR a direct SetWindowText/API call; OR the MDI client caption). Note the ONLY two 'AoWEd' text consts in the exe are the SetTitle one (0x42EFE8) and the dict-path one (0x4288A0, do-not-touch) — so the live title may be built by concatenation or set via a mechanism that doesn't use a plain 'AoWEd' literal. bak_titlebar deleted (was == working state after revert). RE below kept for revival:

**(reverted) attempted approach:** The editor's top window bar / taskbar text came from `Application.SetTitle('AoWEd')` in the .dpr startup, NOT the main form Caption. `[0x432224]` = imported Forms.Application; @VA **0x42EE5E** `mov edx,0x42EFE8; call 0x401318(=Forms.TApplication.SetTitle)`. The 'AoWEd' string const @VA 0x42EFE8 (file 0x2E3E0). "AoWDevX"(7) > "AoWEd"(5) so can't overwrite in place: wrote a new Delphi string const `FF FF FF FF | 07 00 00 00 | "AoWDevX" | 00` (16B) into the **dead old About-DFM bytes** in .rsrc @file 0x464BC / VA 0x449EBC (chars ptr VA **0x449EC4**), and repointed the `mov edx` immediate @file 0x2E25E (`BA E8 EF 42 00` -> `BA C4 9E 44 00`). **LANDMINE (v1 caused an AV):** my first cave was a 30-byte "zero run" in CODE @file 0x7267/VA 0x407E67 — but in this Delphi exe CODE zero-runs are NOT free padding, they're embedded RTTI/data with BASE RELOCATIONS (there's a reloc at RVA 0x7E64 right inside it). Writing the string there corrupted live data -> access violation on open + title unchanged. RULE: for a data cave in AoWDevX.exe, pick a spot with NO base-reloc inside it and that nothing references — the dead About DFM region (2225B @0x464BC, repointed away by the About relocation, resource data = no relocs) is ideal. NB the `mov edx` immediate itself sits on a base reloc (RVA 0x2EE5F) — that's fine/correct: the imm is a rebasable pointer, so pointing it at 0x449EC4 rebases consistently. GOTCHA — do NOT touch the OTHER 'AoWEd' const @VA 0x4288A0 (file 0x27C98): it's used in an LStrCatN building the localization dict path `...Dict\AoWEd.mld` (@VA 0x4284D6). The main form (TMainForm, DFM @file 0x74AFC) Caption stays "Age of Wonders Editor" (untouched; the visible title is Application.Title). Icon left as-is per user (title-bar/taskbar icon = MAINICON RT_ICON id1 = same artwork the About box now shows).

**REVERT:** restore `AoWDevX.exe.bak_about` (covers About's 4 changes) and/or `AoWDevX.exe.bak_titlebar` (covers the title-bar text; note bak_titlebar was taken AFTER bak_about, so it already includes the About changes).

Related: editor rename in [[active-patches.md]] (AoWDevEd->AoWDevX), [[editor-dialog-dir-memory.md]] (other AoWDevX.exe edits: dir-memory cave, DATA RWX).
