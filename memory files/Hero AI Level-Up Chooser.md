# Hero AI Level-Up Chooser — expanded (AoWEPACK.dll)

**What it does:** Expands the AI hero/leader level-up ability chooser from vanilla's **3** ability options (Parry / Dragon(Monster) Slaying / Spellcasting) to a **weighted pool of 30 abilities** + retuned stat weights, with a two-weight *banking / lock-in* system so the AI saves toward and reliably grabs expensive abilities. Fully data-driven — retune by editing a table and re-running the build script.

**Status:** Confirmed working in-game. All addresses are AoWEPACK.dll (imagebase 0x55700000; **VA = file_offset + 0x55700C00**).

---

## The function — `ExecuteUpgradeHeroAI`
Vanilla builds a weighted `Engine.TDoubleItemList` (from EngineP.dpl) of upgrade options, RNG-picks one via `RandomChanceItemB`, applies it, then **LOOPS** — re-entering the top at **0x55787A40** to apply MORE upgrades until the hero's SkillPoints hit 0 **or the option list comes up empty**.

Key functions / offsets:
- **GetAbility** `0x557501c0` — eax=ability control, edx=id → eax=ability (or null). control = `[[0x558fa044]+0x80]` (0x558fa044 = game-manager global).
- **AddAB** = `Engine.TDoubleItemList.AddAB` (import thunk `0x55702fcc`): eax=list, edx=itemA(=optId), ecx=itemB(=weight). Stores an (optId,weight) pair and **grows dynamically** (no capacity cap — it calls Grow when full).
- **RandomChanceItemB** thunk `0x5570300c`; **Get** `0x55702fe4`; **Clear** `0x55702fd4`. (All EngineP.dpl exports.)
- Ability VMT: **CanExpand** `[ability+0xc4]`, **ExpandCost** `[ability+0xc8]`, **Expand** `[ability+0xd0]`. Hero **ExpandAbility** `[hero_vtable+0x94]` (generic — grants a single-level ability or levels a multi-level one).
- **SkillPoints(hero)** `0x557875c4`. In this function the point total lives in **esi** the whole time (verified preserved by every pick-phase call — they push/pop esi).
- **Loop-back check `0x55787d2a` ("DONE")**: `cmp [edi+8],0; je exit; call 0x557875c4; test eax; je exit; test esi; jne 0x55787a40` — i.e. if the list is non-empty AND points remain, loop to the top and apply another upgrade.
- **Exit `0x55787d43`**: frees the list (`0x557010b8`) + epilogue + ret.
- Original stat handlers @ `0x55787c90/ca0/cad/cba/cc7` (ATK/DEF/RES/DMG/HP); each ends `jmp 0x55787d2a`. Original apply dispatch @ `0x55787C5C`: `mov eax,[esp+4]` (the chosen optId) then `cmp eax,7; ja done; jmp [table+eax*4]`.

## The two-weight banking / lock-in mechanic
Each ability carries **two weights**: an **unaffordable weight** (used while the hero can't yet afford it) and an **affordable / lock-in weight** (used the instant it's affordable). Every learnable ability is **always in the pool** (if `CanExpand`), so the RNG picks proportional to weight; affordability decides which weight and what happens on apply:

- **cave_elig** (replaces the 3 hardcoded ability options): loop a table; per id → GetAbility (null→skip) → CanExpand (false→skip) → ExpandCost → choose aff or unaff weight by `esi(points) ≥ cost` → AddAB.
- **cave_apply** (replaces `cmp eax,7`): optId 0–4 → jump to the original stat handlers; else (an ability id) **re-check affordability**: affordable → `ExpandAbility` → `jmp DONE` (loop-back, apply more); **unaffordable → `jmp EXIT`** (bank the remaining points, terminate).

**Why unaff/aff both matter:** the *unaff* weight drives accumulation — a high-weight-but-expensive option gets picked often while unaffordable, which triggers the bank-and-exit, so the AI saves toward it across levels. The *aff* weight then makes it grabbed the moment it's affordable. Vanilla did exactly this for Spellcasting only (weight **9999 affordable / 100 unaffordable**, with an `xor esi,esi` on the unaffordable pick to exit); this generalizes it to every ability with per-ability tuning.

### ⚠️ Landmine: exit-on-unaffordable is mandatory
Vanilla's loop terminates on "list empty". Because always-add keeps the list **permanently non-empty**, that exit never fires — so if a hero has leftover points that are `> 0` but `< the cheapest option's cost`, every pick is a bank-and-do-nothing and the loop **spins forever** (new game hangs / end-turn hangs). Routing the unaffordable pick straight to the loop's **EXIT** guarantees termination: every iteration either spends points (affordable→loop) or ends the session (unaffordable→exit).

## The patch (all in AoWEPACK.dll)
- **cave_elig @ 0x5580FD40**, then 3 parallel tables **TABLE_ID** (1 byte/id), **TABLE_UN** (LE word), **TABLE_AF** (LE word) indexed by loop index, then **cave_apply**. End ≈ 0x5580FEE8 at 30 abilities (cave free-space limit here ≈ 0x5580FF00 — near full).
- **Hook 1 @ 0x55787B15** (`8b 45 00 …` = the ability-options entry) → `jmp cave_elig`.
- **Hook 2 @ 0x55787C60** (`83 f8 07` = `cmp eax,7`) → `jmp cave_apply`.
- **Stat weight immediates** edited in place (low byte after `b9`): ATK @0x55787A67, RES @0x55787AB4, DMG @0x55787ADC, HP @0x55787B04. DEF @0x55787A8C left 0xff. Stat point-gates untouched (ATK/RES/HP `cmp esi,5`; DEF/DMG `cmp esi,0xa` — this is why DEF is offered less often than ATK; fold the stats into the same two-weight pool if you want DEF to compete purely on weight).

## PIC / rebasing (critical for AoWEPACK.dll)
AoWEPACK.dll rebases between launches, so a cave must never dereference a bare in-image absolute. Both caves compute a delta first: `push ebp; call gd; gd: pop ebp; sub ebp, gd` → ebp = runtime−preferred delta; then `[ebp+0x558fa044]` for the game-manager global and `[ebp+TABLE_x]` for the tables. All inter-function calls/jumps are rel32 (already position-independent). Getting this wrong yields the classic intermittent "Runtime error 216".

## Build / tune
See **`Hero AI Level-Up Chooser.py`** (keystone-engine assembler; needs `pip install keystone-engine capstone`). It rebuilds fresh from a pre-feature backup of AoWEPACK.dll each run, two-pass-assembles to resolve the table VAs, and writes the caves + hooks + stat edits. Edit the `ABILS = [(id,"name",unaff,aff), …]` table and `STAT` weights, re-run. (Cave VAs are specific to this mod's free space — pick your own free region if your layout differs.)
