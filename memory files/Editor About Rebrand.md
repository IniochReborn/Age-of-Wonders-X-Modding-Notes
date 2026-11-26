# Editor About Rebrand

**One-line:** Rebrand the editor's Help → About dialog to "AoWDevX" — form title, big label, embedded app icon, and version bumped 1.36 → 1.37.

**Status:** DONE / confirmed working in-editor. Backup: `AoWDevX.exe.bak_about`.

---

## File patched
- **AoWDevX.exe** (the editor) — ImageBase `0x400000`. CODE section: raw offset `0x400`, RVA `0x1000`. `.rsrc` is the LAST section. Compute file offsets from the PE section table (do **not** rely on a fixed `VA − imagebase − 0xC00`), because the resource edits and the DFM relocation live in `.rsrc`.

## The four changes
1. **Form title** "About AoWEd" → "About AoWDevX" — DFM `TAboutDlg` `Caption` (`06 0B "About AoWEd"` → `06 0D "About AoWDevX"`, +2 bytes).
2. **Big label** "AoWEd" → "AoWDevX" — DFM `TLabel Label1` `Caption` (`06 05 "AoWEd"` → `06 07 "AoWDevX"`, +2 bytes).
3. **Icon** vanilla 16-color editor icon → AoWDevX app icon — DFM `TImage Image2.Picture.Data` embedded `TIcon` replaced (same size, see below).
4. **Version** "1.36.330" → "1.37.330" — a single immediate byte in the runtime version-string builder.

## RE findings

### The About version string is assembled at runtime (NOT VERSIONINFO)
There is no `version.dll` import. `TAboutDlg.FormCreate` @VA `0x42E330` calls a builder at **`0x42800C`** which does `IntToStr(1) + "." + IntToStr($24=36) + "." + IntToStr(<dynamic build 330 from global [0x432894] via 0x401F80>)` = `"1.36.330"`, then sets the version label caption. So **"36" is the immediate in `mov eax,0x24` @VA `0x428041` (`B8 24 00 00 00`); the `0x24` byte is at file `0x27442`.** Change `0x24` → `0x25` ⇒ "1.37.330". ("1" is `mov eax,1`; "330" is the engine build number, dynamic — both left alone.) The DFM's static `VersionLbl` caption is just "Version:"; FormCreate overwrites the number label.
> The exe's VERSIONINFO resource still says 1.36.53.148 — the About box does not use it, so it was left untouched.

### Icon (lossless in-place-format swap)
The app icon (`RT_ICON` id 1 @file `0x446C4`) is a 32×32 **32bpp** image (4264 B) but uses only **7 opaque colors** + binary alpha. The DFM's vanilla icon is a 32×32 **4bpp** 766-byte `.ico` (ICONDIR 6 + ICONDIRENTRY 16 + DIB 744). The app icon was rebuilt losslessly as a 766-byte 4bpp `.ico` (7 colors fit in a 16-color palette) so it drops into `Picture.Data` at the **same size** — Delphi-3 `TIcon` reads it identically. Blob = `05 "TIcon"` + `.ico`, vaBinary length `0x304` unchanged.

### DFM relocation (why the file grows)
`TAboutDlg` is the `RT_RCDATA` resource named `TABOUTDLG` (file `0x464BC` / RVA `0x49EBC` / size 2225). Changes 1 & 2 grow it by +4 bytes (the icon is same-size); only 3 bytes of slack follow it, so it can't grow in place. `.rsrc` is the last section, so the new **2229-byte** DFM is **appended at EOF** (padded to 2560 = `0xA00`) and everything is repointed:

| Field | File offset | Old | New |
|---|---|---|---|
| SizeOfImage | `0x150` (dword) | `0x000E0000` | `0x000E1000` |
| DataDir[RESOURCE].Size | `0x18C` (dword) | `0x00099A64` | `0x0009A600` |
| `.rsrc` VirtualSize | `0x2C8` (dword) | `0x00099A64` | `0x0009A600` |
| `.rsrc` SizeOfRawData | `0x2D0` (dword) | `0x00099C00` | `0x0009A600` |
| `TABOUTDLG` entry OffsetToData | `0x43290` (dword) | `0x00049EBC` | `0x000DFC00` |
| `TABOUTDLG` entry Size | `0x43294` (dword) | `2225` (`0x8B1`) | `2229` (`0x8B5`) |
| **new DFM** | append @ `0xDC200` | — | 2560 bytes → RVA `0xDFC00` / VA `0x4DFC00` |

The version byte (change 4) is independent:

| Field | File offset | VA | Old | New |
|---|---|---|---|---|
| version "36"→"37" | `0x27442` | `0x428042` | `24` | `25` |

The old DFM bytes @`0x464BC` are left as dead space (later reused by other features as a reloc-free data cave).

**Binary verification:** diffing `AoWDevX.exe.bak_about` (pre-About, 901632 B) → `AoWDevX.exe.pre-dlgdirs` (post-About, 904192 B) shows exactly the 5 header/entry ranges above + the version byte + the 2560-byte append. The apply-script reproduces `pre-dlgdirs` byte-for-byte from `bak_about`. `pefile` reparses the result cleanly and the resource reads back as the new DFM (captions + icon + palette all confirmed).

## Landmines & notes
- **The current live `AoWDevX.exe` has a later unrelated patch (dlgdirs — the Open-dialog directory memory) stacked on top**, which re-bumped `SizeOfImage` and the `.rsrc`/section sizes *again* and appended its own section. So the correct "after" reference for the isolated About feature is `AoWDevX.exe.pre-dlgdirs`, not the live exe. The version byte (`0x27442`) and the `TABOUTDLG` resource relocation (`0x43290`) are unchanged by dlgdirs and are still present in the live exe; only the PE header size fields differ (because dlgdirs advanced them further).
- **Do NOT touch the other 'AoWEd' string const @VA `0x4288A0`** (file `0x27C98`) — it builds the localization dict path `…Dict\AoWEd.mld`.
- The main-window title bar still reads "AoWEd"; a separate attempt to rebrand it was reverted (the visible top-bar text is **not** `Application.Title` — repointing SetTitle had no visible effect; real source unknown).
- When placing a data cave in this exe, avoid CODE zero-runs: they are embedded RTTI/data with **base relocations** (writing there causes an access violation). The dead old-About-DFM region in `.rsrc` (no relocs, repointed away) is the safe cave.

## Revert
Restore `AoWDevX.exe.bak_about` (covers all four About changes).
