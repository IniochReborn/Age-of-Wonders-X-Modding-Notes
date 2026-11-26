# Reflecting Pool Raze

**Binary patch to `AoWEPACK.dll`** (ImageBase `0x55700000`; **VA = file_offset +
0x55700C00**). **CONFIRMED WORKING in-game 2026-07-04.** Lets Reflecting Pools be **razed**
(with animation + sound + defender fight), **rebuilt** for 50 gold (1-turn build with a
construction animation), and handles all the **pool-vision** consequences correctly.

The apply script `reflecting_pool_raze_patch.py` (this folder) writes the exact bytes;
the table at the bottom lists every edit with file-offset + VA + old→new. Byte data was
extracted by diffing the pre-feature backup (`AoWEPACK.dll.bak_reflecting_pool_raze`)
against the live, fully-patched `AoWEPACK.dll`, keeping only the pool-feature ranges.

> Note: an `AoWx.exe` **UI patch** (not included in this DLL script) is also required to
> show the side-window raze button — see "UI side" at the bottom.

---

## What & why — the raze framework

- **Razeability is a data flag**, byte at **resource + 0x58** (`TStructure.GetRazeable` =
  `mov eax,[eax+08h]; mov al,[eax+58h]; ret`). It is hardcoded per resource-class
  constructor, **not** loaded from data files. `TStructureResource.Create` defaults it to 0;
  razeable classes (towers, teleports…) set 1.
- `TReflectingPoolResource.Create` **explicitly set [esi+58h]=00** → pools were unrazeable.
  First half of the fix: make the ctor set it to **1**.
- But `TReflectingPool` doesn't override `SetRazed`/`GetRazed` — it inherits the **stubs**
  `GetRazed = xor eax,eax; ret` and `SetRazed = ret`. So flipping the razeable flag alone
  makes raze "succeed" while the pool keeps working and can be razed repeatedly. **Real
  razed state and all its side-effects had to be implemented.**

### Raze flow (vanilla, reused)
`TStructure.Raze` (UI + confirm dialog) → `RazeEx` → network **token** (MP-safe) →
`ExecuteRaze` on all clients. `ExecuteRaze` calls `CanRaze`, logs "StructureRazed", plays
image sequences **0x14/0x15**, then `SetRazed(true)` via VMT+0x14C. `CanRaze` fails if
already razed, requires `GetRazeable`, and requires the razing player's units present.

### TReflectingPool layout (InstanceSize 0x40)
`+30h` owner byte (FF=none) · `+31h` turns-owned · `+34h` victory bitlist · `+38h` current
unfog radius · `+3Ch` frame counter · **`+39h..+3Bh` = zero-init padding → used for the
razed flag** (bit 0 of `+39h`). `+24h`/`+25h` = rebuild builder/days.

### Pool-vision internals (the hard part)
`PoolVisionPlayer(eax=self, dl=player)` → true if that player (or an ally, relation 2) owns
**≥1** pool. `UpdateUnfog` caches the applied radius in `[self+38h]`.
`UpdateReflectingPoolsExploration` walks a player's **owned-pool list** (`[player+68h]`;
pools enlist/delist themselves). `MapFieldMsgProc` msg **0x110A** = live visibility query
→ `PoolVisionPlayer`. Unowned pools' cached unfog only re-evaluates on map-wide fog
rebuilds (turn/seat change) — same staleness exists in vanilla on pool capture.

### Serializer is version-tolerant (verified in Enginep.dpl)
Read via stream VMT `+0x30` (byte field): looks up field ID in the record directory;
**missing ID → zero-fill**. Writer **skips value 0**. So adding a new tagged field is fully
backward/forward compatible; saves stay byte-identical unless a pool is actually razed. The
razed byte is streamed as **field id 0x70**.

---

## The implementation (5 sub-patches, all 2026-07-04)

**1. Make pools razeable + rebuildable in 1 turn** — inline rewrite of
`TReflectingPoolResource.Create` field writes (@ file 0xD47E5). `mov [esi+58h],01`
(razeable) and `mov [esi+5Bh],01` (rebuild days=1). Rebuild days are read only by
`TStructure.GetRebuildInfo` (`mov al,[ebx+5Bh]`; cost hardcoded 0x32=50g). days=1 vs 0
behave identically at runtime (dec 1→0 fires `BuildingDone` same turn) but **1 displays
correctly** in the rebuild UI.

**2. Real razed state** — three caves + VMT repoints:
- **GetRazed** cave `0x5580C2A0`: `test byte[eax+39h],1; setnz al; ret`. VMT `+0x150`
  repointed to it.
- **SetRazed** cave `0x5580C300` (VMT `+0x14C`): `dl=1` → `SetPlayer(-1)` via VMT+0x1F0
  (delists, self-unfog, `UpdateReflectingPoolsExploration`), set bit `+39h`, `UpdateUnfog`
  via VMT+0x204; `dl=0` → clear bit; **both** paths recompute `[self+14h] =
  GetTerrainTypeImage([self+18h])` via VMT+0x12C (teleport-style) so the sprite/minimap
  updates immediately.
- **ReadWrite** cave `0x5580C2D8` (VMT `+0x18`): call base `TPlayerStructure.ReadWrite`
  (`0x55760F44`), then stream byte `+39h` as field id **0x70** via stream VMT+0x30.

**3. Razed pool grants no vision** — `PoolVisionPlayer` entry hook (@ file 0xD4630) into
a **razed-guard cave** inside `0x5580C300`: if the pool at `[eax+39h]&1` is razed → return
0 (drops it out of the reflection network for both cached unfog and 0x110A live queries).

**4. Rebuild must not grant vision early** — while rebuilding, `SetPlayer(builder)`
re-enlists the still-razed pool into `[player+68h]`, which would make `PoolVisionPlayer`'s
"Count≠0" ownership test pass at rebuild **start**. Fix: a **rebuild-count helper** (in the
`0x5580C300` cave block) that returns 1 iff ≥1 list item with `([item+39h]&1)==0` (i.e. a
*non-razed* owned pool). Both `PoolVisionPlayer` count fetches (`mov edx,[eax]; call
[edx+54h]`, at file 0xD464F own-list and 0xD468B ally-loop) are redirected to it.

**5. Rebuild graphics + unraze refresh** — image indexes (DevEd hex numbering): razed =
0x16/0x17/0x18, rebuild-animation = 0x19/0x1A/0x1B. `TStructure.GetTerrainTypeImage`
(file 0x5DAA0) checks `GetRazed` **first**, so a rebuilding (razed+building) pool kept the
razed image. A **global entry hook** (@ file 0x5DAA0) into a **gfx cave** (tail of
`0x5580C300`): if the structure is building (`[self+24h]!=FF`) return 0x19/1A/1B by terrain,
else replicate the entry bytes and fall through. Also the SetRazed cave's clear-path was
extended (jz operand retargeted `1C→76`) to an **unraze-ext** stub that clears `+39h` bit 0
and calls `UpdateReflectingPoolsExploration` (`0x557D5084`) so pool vision refreshes on the
completion turn.

### Completion path (already closes correctly)
`NewTurn` → decrement days → at 0 `BuildingDone`: event log, **SetRazed(false)** (clears
`+39h`), `[+24h]=FF`, image recompute; then `TPlayerStructure.BuildingDone` → UpdatePlayer /
UpdateExploration / UpdateUnfog → vision resumes. `TPlayerStructure.SetPlayer` refuses
ownership change when razed & not building → **a razed pool can't be recaptured by
visiting.**

### Known cosmetic caveat
The **main-map pool sprite** is unchanged when razed (pools ship no razed graphic);
minimap / terrain-type use the generic razed images 0x16–0x18. The global
`GetTerrainTypeImage` hook affects **all** structures on VMT+0x12C — vanilla razeables
(towers/teleports) now show construction images 0x19–0x1B while rebuilding too (confirmed
not a regression: they already had those images).

---

## TReflectingPool VMT slots (reference)
`+0x18` ReadWrite · `+0x12C` GetTerrainTypeImage(recompute) · `+0x14C` SetRazed ·
`+0x150` GetRazed · `+0x154` GetRazeable · `+0x178` NewTurn · `+0x19C` BuildingDone ·
`+0x1A0` ExecuteRebuild · `+0x1EC` CanRaze · `+0x1F0` SetPlayer · `+0x204` UpdateUnfog ·
`+0x208` UpdateExploration · `+0x220` UpdatePlayer.

---

## Byte-patch table

All offsets are file offsets into `AoWEPACK.dll`; VA = offset + 0x55700C00.
"old" = pre-feature (`bak_reflecting_pool_raze`), "new" = live. The apply script writes
these exactly and was verified to reproduce the live pool bytes with zero stray changes.
272 feature bytes across 10 ranges.

| File off | VA | Len | What |
|----------|----|-----|------|
| `0x5DAA0` | `0x5575E6A0` | 6 | `GetTerrainTypeImage` entry hook → gfx cave. old `53568bf28bd8` → new `e9ebdc0a0090` |
| `0xD3CE0` | `0x557D48E0` | 3 | VMT `+0x18` ReadWrite hook. old `404d7d` → new `d8c280` |
| `0xD3E14` | `0x557D4A14` | 7 | VMT `+0x14C` SetRazed + `+0x150` GetRazed hooks. old `e8ed7555e4ed75` → new `00c38055a0c280` |
| `0xD4630` | `0x557D5230` | 6 | `PoolVisionPlayer` entry → razed-guard cave. old `535651881424` → new `e90b71030090` |
| `0xD464F` | `0x557D524F` | 5 | own-list count → rebuild-count helper. old `8b10ff5254` → new `e800710300` |
| `0xD468B` | `0x557D528B` | 5 | ally-list count → rebuild-count helper. old `8b10ff5254` → new `e8c4700300` |
| `0xD47E5` | `0x557D53E5` | 14 | `TReflectingPoolResource.Create` rewrite (razeable=1, rebuild=1 turn). old `4401c6464500c6466400c6465800` → new `4500c6466400c6465801c6465b01` |
| `0x10B6A0` | `0x5580C2A0` | 8 | **cave** GetRazed: `test byte[eax+39h],1; setnz al; ret`. `f64039010f95c0c3` |
| `0x10B6D8` | `0x5580C2D8` | 29 | **cave** ReadWrite (base RW then stream `+39h` id 0x70). `53568bf28bd8e8614cf5ff8d5339b9700000008bc68b30ff56305e5bc3` |
| `0x10B700` | `0x5580C300` | 189 | **cave** SetRazed v2 + PoolVisionPlayer razed-guard + rebuild-count helper + unraze-ext + rebuild-gfx (see script for full bytes) |

Full 189-byte cave (`0x5580C300`) new bytes:
```
538bd884d27476b2ff8bc38b08ff91f0010000804b39018bc38b08ff9104020000eb04
806339fe0fbe53188bc38b08ff912c0100008943145bc3000000000000f6403901750b
535651881424e9e58efcff33c0c356578bf08b16ff52548bf88b76088b76044f78108b
04bef640390175f4b801000000eb0233c05f5ec3806339fe8bc3e8fc8cfcffe99affff
ff000000807824ff741cb81900000083fa037506b81a000000c383fa057506b81b0000
00c3c353568bf28bd8e9e922f5ff
```
(The v1 SetRazed cave once at `0x5580C2B0–0x5580C2CD` is left zeroed; not part of this
patch.)

---

## MP / save safety
- All raze/rebuild goes through the network **token** path → MP-safe on patched clients
  (both sides must be patched).
- New razed byte is a tolerant tagged stream field (id 0x70) → **old saves load fine**
  (pools read unrazed) and saves stay byte-identical unless a pool is actually razed.
- The AI (`TAIGroupRazeControl.ValidateRazeStructure`) uses the same `CanRaze`, so the AI
  can now raze pools too.

## UI side (separate `AoWx.exe` patch — not in this DLL script)
The engine patch alone shows **no side-window raze button** (the side info window picks a
per-class handler; the exe has no `TReflectingPool` import, so pools fall to a generic
handler that doesn't show `RazePnl`). The `AoWx.exe` UI patch reroutes the generic handler
to show the raze panel driven by `GetRazeable` (VMT+0x154) → SetVisible (VMT+0x6C). See the
`patch_reflecting_pool_raze_ui_v1.py` writeup if you also want the button; the generic
`RazeBtnClick` handler (reads structure, calls `CanRaze` then `Raze`) already works for
pools unchanged.
