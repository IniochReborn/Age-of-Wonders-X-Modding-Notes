# Road Build Cost by Decoration

**One-line:** Construct/Build-Road cost becomes **per-tile by ground decoration** instead of the vanilla flat 10 gold/tile.

**Costs:** open ground / light vegetation / bones = **2** · rocks / toadstools = **3** · Vegetation & Dense tree-forest = **5**.

**Status:** CONFIRMED WORKING in-game. Target: `AoWEPACK.dll` (ImageBase `0x55700000`, VA = file_off + `0x55700C00`).

---

## Files patched
- `AoWEPACK.dll` only.
- Backup of the confirmed build: `AoWEPACK.dll.bak_roadveg_final`. **The live build carries one further tweak** vs that backup: toadstools 5→3, a 1-byte `je`-retarget at `0x5580F757` (`74 02` → `74 09`). The patch script below reproduces the **live** (toadstools=3) state.

## RE findings (reusable)
### Road system
- **Actual road-construct fn @`0x55771068`.** Field ptr lives in `esi` (valid only until `0x557710B9`), player idx in `ebx`/`bl` (until `0x557710D8`), and the charge is `sub eax,gold` @`0x557710F3` — **vanilla `83 E8 0A` = `sub eax,10`** (the flat cost).
- **UI cost-preview path-walker `FUN_55771138`:** field at `[esp+8]`, per-tile adder @`0x55771195` (vanilla `83 44 24 04 0A` = `add [esp+4],10`). Feeds `ConstructingRoadCostsXRStr` @`0x5570777C` (formatted @`0x55792AE5`).
- **Buildable-tile helper `FUN_55770FF0`:** base terrain `[field+0x14]` ∈ {1..5}, overlay ∉ {0,2,4,5}, no `TStructure` MO.
- `TSelectedArmy.SelectBuildRoad` @`0x55793B98` (UI targeting). `GetTerrain` thunk @`0x55701C8C`.

### Per-hex signals (the actual discovery)
- **`[field+0x15]` = cached overlay byte:** open/transparent = **255**, Light Veg = **9**, Vegetation & Dense (trees) = **1**. ⚠ Veg and Dense **share value 1** — not separable per-hex (accepted "tree forest = 5").
- **Decoration object on the hex** = a `TAoWTerrain` MapObject found by matching its **`MapFieldMsgProc == 0x5579BE0C` at vtable offset `+0xCC`**. This is how the engine's `SendMapFieldMsg` (@HSEPack `0x55607944`) dispatches: iterate children `[field+8]`, count = byte `[field+0xD]`, child = `[[field+8]+i*4]`, handler = `[[child]+0xCC]`.
  - ⚠ **`FindChild` (@`0x55701FEC`) / `FindNoneTransparentHS` (@`0x55702004`) do NOT work here** — they match by class `+0x24` / is-a, which the veg MOs override or mismatch. Use the MsgProc match above.
- **`[MO+8]` = resource; `[resource+0x44]` = decoration category:** trees = **0**, rocks = **1**, bones = **2**, toadstools = **4**. (This is decoration *type*, not density.)
- **Dead ends (don't retry):** `[resource+0x48]` = combat tag (varies by base terrain, dense IDs overlap light's); `GetTerrain(list)` = base terrain; `GetOverlay` = 1 for both veg & dense; `GetConcealmentActive` = always 0 here. The editor's "overlay terrain type" (Light 25 / Veg 19 / Dense 17) is **not** stored in any per-hex-readable field.

## The patch
### Hooks / edits
| VA | original (vanilla) | new | purpose |
|---|---|---|---|
| `0x557710B6` | `8a 4e 10 8b 30` (`mov cl,[esi+10]; mov esi,[eax]`) | `e8 f5e60900` (`call 0x5580F7B0`) | cave_capA (field in esi) |
| `0x557710D8` | `0f be f3 8b d6` (`movsx esi,bl; mov edx,esi`) | `e8 13e70900` (`call 0x5580F7F0`) | cave_capB (load cost) |
| `0x557710F3` | `83 e8 0a` (`sub eax,10`) | `2b c3 90` (`sub eax,ebx; nop`) | charge per-tile cost (ebx) |
| `0x55771195` | `83 44 24 04 0a` (`add [esp+4],10`) | `e8 f6e50900` (`call 0x5580F790`) | cave_pred (UI preview adder) |

### Caves (previously-zero free space)
- **cave_roadcost @`0x5580F700` (117B):** classifier, field in `eax` → cost 2/3/5 in `eax`; preserves edx/ecx/ebx/esi/edi/ebp. Logic: `overlay[field+0x15]==9 → 2`; `==1 → 5`; else find deco MO by MsgProc-match; none → 2; `cat[res+0x44]==1(rocks) → 3`; `==4(toadstools) → 3`; else (bones/other) → 2. The `0x5579BE0C` MsgProc address is computed via a **`call $+5; pop; sub; add` delta-trick** (PIC-safe).
- **cave_pred @`0x5580F790` (14B):** `field=[esp+0xC]`; call cave_roadcost; `add [esp+8], cost`; ret.
- **cave_capA @`0x5580F7B0` (37B):** field in `esi` → cave_roadcost → store cost to scratch **SC = `0x558FA800`** (writable BSS); then replay stolen `mov cl,[esi+0x10]; mov esi,[eax]`.
- **cave_capB @`0x5580F7F0` (23B):** replay stolen `movsx esi,bl; mov edx,esi`; then `ebx = [SC]` (per-tile cost) for the `sub eax,ebx` charge.

## Mechanism
Prediction and actual-charge both call the **same** cave_roadcost classifier, so the UI preview always equals the gold charged. The actual path can't keep the field ptr alive to the charge site, so cave_capA stashes the computed cost into the SC scratch and cave_capB reloads it just before the `sub eax,ebx`.

## Landmines & notes
- **Scratch SC = `0x558FA800` must be in WRITABLE BSS**, not the code section. An earlier code-section scratch crashed. SC is transient (capA writes, capB reads, same tile) → MP-safe.
- All caves PIC-safe (delta-trick for the MsgProc VA); the caves call fixed helper VAs via rel32 (position-independent).
- To change a cost: edit the immediate in cave_roadcost's `mov eax,N` (5 @~`0x5580F75B`, 3 @`0x5580F762`, 2 @`0x5580F769`), or retarget a category's `je` (e.g. toadstools 5→3 = point the `cat==4` `je` @`0x5580F757` at `mov eax,3` instead of `mov eax,5`).
- Vanilla flat cost was **10** (`sub eax,0x0A`); a prior interim build used flat **5** (backups `bak_roadcost` / `bak_roadveg`) — do not mistake those for vanilla.

## Apply
Accompanying `road_build_cost_by_decoration_patch.py` (baseline = pristine vanilla `AoWEPACK_original_backup.dpl`) writes the 8 ranges and self-verifies with `--verify`.
