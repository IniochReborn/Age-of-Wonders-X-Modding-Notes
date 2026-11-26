---
name: editor-sort-by-status-SHELVED
description: "SHELVED 2026-07-26: add 'sort by placed-on-map status' to the editor's hero/item placement windows (repeated-press of an existing sort button). PoC hooking TItemList.SortOnName had NO effect (item window sorts via ordinal-bound GRID classes, not TItemList). Deep rabbit hole + untestable without in-editor feedback each round. No files changed (reverted clean). Reusable sort/compare-fn RE + resume path kept."
metadata:
  node_type: memory
  type: project
  originSessionId: ae619055-3278-433b-b71b-cf21e5789ad7
  modified: 2026-07-26T05:48:16.398Z
---

**GOAL (user):** In the map editor's hero/item placement windows (sortable by name / type-level), add sorting by **placed-on-map status** (free/unused vs already placed), grouping unplaced at top. Chosen delivery: **repeated-press of an existing sort button** toggles status-sort (keeps it all in AoWEPACK.dll — no editor-exe/DFM changes).

**STATUS: SHELVED.** PoC built + tested → **no effect**. Reverted; no files changed.

## RE GOLD (reusable)
### Editor sort UI wiring
- Editor form (**AoWDevX.exe**, base 0x400000): buttons `SortOnNamesButton` + handler `SortOnNameBtnClick` (also SortItemNames/SortItemTypes). Hints "Sort on name/level", "Sort item on name/type".
- The grid sort methods are **imported by the exe from AoWEPACK.dll**: `HeroGrid.THeroGrid.SortOnName/SortOnLevel`, `ItemGrid.TItemGrid.SortOnName/SortOnType`, `HeroCtrl.THeroControlGrid.*`, `ItemCtrl.TItemControlGrid.*` (IAT slots ~0x00433500-0x004335C4 in AoWDevX.exe). **⚠️ These are ORDINAL-bound** — they are NOT in AoWEPACK.dll's 10036 *named* exports, so you can't `pe.DIRECTORY_ENTRY_EXPORT` them by name. Must resolve via the exe's import ordinal → AoWEPACK.dll export-by-ordinal.

### Sort mechanism (AoWEPACK.dll) — clean and reusable
- `SortOnName` bodies are tiny: `mov edx, <comparefn>; mov eax,[self+8] (the TList); call 0x5570167C (generic Sort thunk)`.
- **Compare-fn convention:** `eax=item1, edx=item2` → returns `eax = (key1 - key2)`, tie-break `item1 - item2` (pointer diff). To add a mode: write a new compare fn + call the same `Sort(eax=list, edx=cmpfn)`.
- **TItemList.SortOnName @0x55794AB8** (cmpfn 0x55794A70, name string at `[item+0x18]`, uses str-cmp 0x55701584). **TItemList.SortOnType @0x55794AC8** (cmpfn 0x55794A9C, type byte at `[item+0x34]`).
- **BUT the item placement window does NOT route through TItemList.SortOnName** — hooking it did nothing. The display order comes from the **grid** class's own sort (the ordinal-bound TItemGrid/TItemControlGrid.SortOnName). That is the real hook target.

### Placed-on-map predicate (UNVERIFIED lead)
- `NotPlacedOnMapRStr` global @0x55706B0C. Display routine @~0x55751CFE branches: `mov eax,[esi+0xd4]; cmp dword[eax+4],0; jne <placed>` → i.e. **placed iff `[[obj+0xd4]+4] != 0`** (nonzero placement-count). `esi`'s exact class (the grid item vs form) was NOT confirmed — verify before trusting `+0xd4`.

### Landmines learned
- **Writable BSS scratch:** BSS section VA 0x558EA000 vsize 0x10231 (rawsize 0), page-extends to 0x558FB000; the tail **0x558FA231-0x558FB000** is runtime-zero writable scratch (road-cost uses 0x558FA800, weakness 0x558FA810 — see [[road-build-cost]]). **The flat file offset `va-0x55700C00` is WRONG for BSS** (rawsize 0) — BSS is runtime-only, don't assert file bytes there; toggle/scratch bytes are never written in the file, only referenced (via PIC delta) and written at runtime.
- AoWEPACK.dll rebases → caves need the PIC delta trick (`call/pop/sub`); `lea edx,[ebx+<preferredVA>]` to load a rebased in-image address.

## RESUME PATH (if revisited)
1. Disassemble the exe's `SortOnNameBtnClick` handler → find the exact IAT slot (~0x004335xx) it `call`s → that's the real grid-sort function; resolve its **ordinal** in AoWEPACK.dll's export table → get the code address → hook THAT (not TItemList).
2. Verify the placed predicate (`[griditem+0xd4]` count) against a known placed vs unplaced item.
3. Design (was built, PIC-safe): repeated-press **toggle byte** in BSS scratch (e.g. 0x558FAF00); on alt press pass a **status compare fn** (`placed1-placed2` unplaced-first, tie-break = call the name cmpfn) to the generic Sort. `jz`-after-`xor toggle,1` gives press1=name / press2=status.
4. Repeat for heroes (separate grid class).
