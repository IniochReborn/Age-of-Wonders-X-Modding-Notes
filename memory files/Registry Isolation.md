# Registry Isolation

**One-line:** Give the mod its own per-user registry tree (`...\Age of Wonders X\`) instead of sharing vanilla's `...\Age of Wonders\`, so it no longer collides with vanilla or other AoW mods.
**Status:** CONFIRMED clean patch, applied 2026-07-22. Pure in-place string edits (no caves, no hooks).

---

## Files patched
- **AoWEPACK.dll** (ImageBase 0x55700000; VA = file_offset + 0x55700C00). Backup: `AoWEPACK.dll.bak_regiso`.
- Post-step (not a binary edit): a one-time `reg copy` to seed the new key (see below).

The game EXE and both editors do **not** contain the registry path string — they route every registry read/write through AoWEPACK's `TAoWRegistry`. So patching this one DLL isolates the whole mod. (The "Triumph Studios" strings in the EXE/editors are version-info company name only, not registry paths.)

---

## RE findings
- The entire per-user settings tree hangs off **one Delphi string constant** `\Software\Triumph Studios\Age of Wonders\`, present as **6 copies** in AoWEPACK.dll — the low-level `TAoWRegistry` read/write helpers (rwString / rwInteger / rwBool, etc.).
- Each copy is a Delphi long-string (AnsiString) constant laid out as `[refcount=-1 (dword)][length (dword)][chars...][NUL]`, with **3-4 spare 00 pad bytes** after the terminator. That slack is what makes an in-place lengthen possible.
- Settings live under subkeys `General\{strings,booleans,rectangles}`, `Sound`, `Video`, `Workspace`, `Email`; string values are keyed by `IntToStr(id)`.
- 5 copies are the bare path (length 41); 1 copy is the path with `General` appended (length 48).
- The `mov edx,<addr>` instructions that load these constants do **not** change — the string start address is unchanged; only the length dword and the tail chars move within the existing buffer.

**Reusable trick:** a `-1` refcount Delphi const with trailing pad bytes can be lengthened in place — bump the length dword by +2 and write `" X"` into the two freed pad bytes, shifting nothing before it.

### The 6 string locations (verified)
| String VA (chars) | length dword VA | file off (len) | old len -> new len |
|---|---|---|---|
| 0x55703BEC | 0x55703BE8 | 0x002FE8 | 41 -> 43 |
| 0x55703CDC | 0x55703CD8 | 0x0030D8 | 41 -> 43 |
| 0x55703DD4 | 0x55703DD0 | 0x0031D0 | 41 -> 43 |
| 0x55703EC8 | 0x55703EC4 | 0x0032C4 | 41 -> 43 |
| 0x557041BC | 0x557041B8 | 0x0035B8 | 41 -> 43 |
| 0x557046BC (…\General) | 0x557046B8 | 0x003AB8 | 48 -> 50 |

`mov edx` refs (unchanged): 0x55703B60, 0x55703C50, 0x55703D40, 0x55703E38, 0x5570410D, 0x55704670.

Each string is edited in TWO spots: the length dword (low byte only, 41=0x29 -> 43=0x2B, or 48=0x30 -> 50=0x32) and the tail, where the final `\` (`5C`) plus 2 pad `00` bytes becomes `" X\"` (`20 58 5C`) — inserting `" X"` before the last backslash.

---

## The patch (byte-edits — VA / file offset / old -> new)

Five bare-path copies (identical edit each), then the `\General` copy.

| file off | VA | old bytes | new bytes | meaning |
|---|---|---|---|---|
| 0x002FE8 | 0x55703BE8 | `29` | `2B` | len 41->43 |
| 0x003014 | 0x55703C14 | `5C 00 00` | `20 58 5C` | `\`+pad -> ` X\` |
| 0x0030D8 | 0x55703CD8 | `29` | `2B` | len 41->43 |
| 0x003104 | 0x55703D04 | `5C 00 00` | `20 58 5C` | `\`+pad -> ` X\` |
| 0x0031D0 | 0x55703DD0 | `29` | `2B` | len 41->43 |
| 0x0031FC | 0x55703DFC | `5C 00 00` | `20 58 5C` | `\`+pad -> ` X\` |
| 0x0032C4 | 0x55703EC4 | `29` | `2B` | len 41->43 |
| 0x0032F0 | 0x55703EF0 | `5C 00 00` | `20 58 5C` | `\`+pad -> ` X\` |
| 0x0035B8 | 0x557041B8 | `29` | `2B` | len 41->43 |
| 0x0035E4 | 0x557041E4 | `5C 00 00` | `20 58 5C` | `\`+pad -> ` X\` |
| 0x003AB8 | 0x557046B8 | `30` | `32` | len 48->50 |
| 0x003AE4 | 0x557046E4 | `5C 47 65 6E 65 72 61 6C 00 00` | `20 58 5C 47 65 6E 65 72 61 6C` | `\General`+pad -> ` X\General` |

Result strings (verified by reading the live DLL):
`\Software\Triumph Studios\Age of Wonders X\` (x5) and `\Software\Triumph Studios\Age of Wonders X\General`.

Net effect: mod uses `HKCU\Software\Triumph Studios\Age of Wonders X\...`, fully separate from vanilla and other mods.

---

## Post-step (NOT a binary patch): seed settings
One-time, non-destructive migration so an existing install keeps its current settings:
```
reg copy "HKCU\Software\Triumph Studios\Age of Wonders" "HKCU\Software\Triumph Studios\Age of Wonders X" /s /f
```
For distribution you can skip this — the game just creates `Age of Wonders X` with defaults on first run — or ship a `.reg` to seed defaults.

---

## Mechanism
All registry access funnels through `TAoWRegistry` in AoWEPACK.dll. Lengthening the single shared path constant (in all 6 helper copies) transparently redirects every read/write to the new tree. Nothing else in the codebase hard-codes the path.

---

## Landmines & notes
- **Do NOT touch the `mov edx` load instructions** — the string base address is unchanged; only length + tail chars change. Editing the refs would break it.
- The trailing pad bytes are finite: this trick only works because there were >=2 free `00` bytes after each terminator. Adding a longer suffix would overrun into the next constant.
- File-association keys under `HKCR\Software\Classes\.hsm|AOWMAP\...` are system-wide and intentionally left alone.
- **Unrelated pre-existing edit in the same DLL (NOT part of this patch):** `TAoWRegistry.GetLanguage` @0x55704B6C is already patched to force English — `mov al,1; nop` (`B0 01 90`) at VA 0x55704B84 / file 0x4288 (vanilla was `8A 04 24` = read registry value). The three text-system callers (0x5579769B, 0x55797C8B, 0x55797D14) do `and eax,0x7F` on it to index the text-set, so forcing 1 makes the game always use the "English" text set. To revert just that: write `8A 04 24` back at file 0x4288. It is listed here only so a diff of this DLL vs pristine vanilla doesn't surprise you — it is independent of registry isolation.
- Dev-mode / portrait fixes are unaffected (GetDeveloper is hard-coded, not registry-read).
