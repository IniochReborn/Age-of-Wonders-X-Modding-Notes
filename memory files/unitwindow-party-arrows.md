---
name: unitwindow-party-arrows
description: "TUnitWindow RE (AoWx.exe): the party prev/next arrows are gated on the MAP-SELECTED army held in TGeneral, which is why they vanish on the events-portrait and item-pickup paths; build_unitwin_party_arrows.py re-drives them from the unit's own TArmy ([unit+4]). Also holds the TGeneral field map, the 15 unit-window entry points, and the keystone-hangs-on-comments gotcha."
metadata: 
  node_type: memory
  type: project
  originSessionId: bc99310d-e7a0-464e-8b38-a64c2704c9e7
  modified: 2026-09-01T00:32:34.580Z
---

# Unit window party arrows — every entry path (2026-08-31)

**User ask:** the unit window opened from the **party side window** has the
little prev/next arrows under the portrait (cycle party members); the *same*
window opened from the **events-window portrait** or the **items-found pickup
dialog** has none. Wanted: arrows there too. Applied via
`patch scripts/build_unitwin_party_arrows.py` (bak `AoWx.exe.bak_partyarrows`).

## The window
`TUnitWindow`, AoWx.exe, DFM @file **0x1E995C** (dump it with the DFM walker
recipe below). Published field offsets come from the Delphi field table at
`VMT-0x2C` (VMT_TUnitWindow = 0x0040710C; count word, u32 classtab, then
`u32 offset | u16 classIdx | shortstring name` per entry):

| component | field | note |
|---|---|---|
| `PNext` | `[self+0x210]` | TAOWButton, OnClick `TUnitWindow.PNextClick` @0x0040AC9C |
| `PPrev` | `[self+0x214]` | TAOWButton, OnClick `TUnitWindow.PPrevClick` @0x0040ABF0 |
| `UnitMainPnl` | `[self+0x16C]` | the portrait panel both arrows sit on |

Neither arrow is `Visible=False` in the DFM — they are hidden at runtime.
The instance lives at `[[0x0045A53C]]` (= BSS 0x0045B070).

## TGeneral — where the party context actually lives
`G = [[0x0045A420]]` (= BSS 0x0045B2C0) is the **TGeneral** data module (the
DFM's `General.Manager`). Fields that matter:

* `[G+0x44]` — TAOWWinManager
* `[G+0x84 .. +0xA0]` — **8 party slot indices**, `-1` = empty
* `[G+0xA4]` — the `TUnitList` those indices index into
* `[G+0xC0]` — the unit the unit window is currently showing

`TGeneral.PartyIndexOfUnit` @**0x00454100**(eax=G, edx=unit) → slot index or -1.

⚠ **Only `TMapEvents.TheMapArmySelected` @0x0044EC30 writes the slot array and
`[G+0xA4]`** (cleared by `TheMapArmyDeselected` @0x0044EA97). It fills slots in
raw army order, skipping units where `[army vmt+0xB8]` (=
`TArmy.GetUnitConcealedForPlayer`, eax=army, edx=index, cl=local player id)
returns true. **So those fields describe the army currently SELECTED ON THE
MAP — i.e. the bottom control bar's contents — not the unit being displayed.**
That is also why they must never be overwritten to fake a party context:
`TControlWin.Unit1FrameMouseDown` reads the same slots to map a bar frame to a
unit, so writing them would corrupt the bottom bar.

## One refresh routine, 15 entry points
Everything funnels through `UpdateUnitWindow` @**0x00407DB8**(eax=Self).
Callers (xref): `TControlWin.Unit1FrameMouseDown` (**the party window**),
`TItemsFoundDlg.PickupBtnClick` (**item pickup**), `TPInfoW.FaceFrMouseDown`,
`TTCUnit.HeroSMapMouseDown`, `TPartyJoinDlg/THeroJoinDlg.U1MouseDown`,
`TIWindow.MainBtnClick`, `TArmyInfoDlg/THeroInfoDlg.U1MouseDown`,
`TRealmWin.HeroInfoClick`/`.Unit1LBDoubleClick`, `TMapEvents.TheMapArmyChanged`
/`.TheMapUnitChanged`, and PPrev/PNextClick themselves.

Vanilla arrow decision, 0x00407E52..0x00407EAC — **hide** if any of:
1. `[[0x0045EBDC]]` (`AoWTC.AoWCombatMap`) ≠ nil → in tactical combat
2. `[G+0xA4] == nil` → no army selected
3. `PartyIndexOfUnit(G, unit) < 0` → displayed unit is not in the selected army
4. `[G+0x88]` (slot 1) ≤ -1 → selected army has < 2 visible units

else **show** at 0x00407E8D (`mov eax,[esi]; mov eax,[eax+0x214]; mov dl,1;
mov ecx,[eax]; call [ecx+0x6c]` ×2, then `jmp 0x407ECB`). The hide block is
0x00407EAD (same shape with `xor edx,edx`). Throughout, `esi = 0x0045B070`
and `ebx = the displayed unit`.

**Root cause of the user's report: tests 2–4, not a bug in those callers.**
The other paths only do `[G+0xC0] = unit` and call the refresh; if no army is
selected, or the selected army isn't this unit's, the arrows are hidden.

## The fix — drive the arrows from the unit's OWN army
`build_unitwin_party_arrows.py`, cave in **`.xbfs` @0x0060E700** (v2, 541 B; section
0x60D000–0x60F000, last vanilla byte 0x0060E6C4). Three hooks:

* `0x00407EAD` (8 B) → cave; re-tests the combat-map gate, then decides, and
  either `jmp 0x00407E8D` (show) or replays the 2 displaced instructions and
  `jmp 0x00407EB5` (hide).
* `0x0040ABF0` / `0x0040AC9C` (5 B each) → cave; PPrev/PNextClick rewritten.
  Vanilla click sound preserved (`call 0x00455DFC` with **dl=0**; that routine
  is a `PlaySample` dispatcher selected by dl).

Cave head is a fixed 3-slot `jmp` table so the hooks never need a label address.
Cycling steps through the army list with wraparound, skipping concealed units
via `[army vmt+0xB8]`, then `[G+0xC0] = unit` + `call 0x00407DB8`.

### The key engine idiom — army of a unit
**`army := [unit+4]`, guarded by `IsClass(army, TArmy)`.** `[obj+4]` is
`TEObject.Owner` (written by `Engine.TEObject.SetOwner` @0x55519318, EngineP).
Verified in `AoWE.TAbstractUnit.CanDisband` @0x557825D7 and
`.GetLocation` @0x5577EDB2. TArmy class-ref var = `[0x557130AC]` → VMT
**0x557130EC**; `TUnitList` classref `[0x55710E88]` → VMT 0x55710EC8.
⚠ `GetUnitConcealedForPlayer` is a **TArmy-only** slot — TUnitList's VMT is
shorter than +0xB8, so the class check is not optional.

AoWx.exe does **not** import the TArmy class ref, so the cave identifies the
class by the Delphi VMT header instead — name shortstring at `[vmt-0x20]`,
parent at `[vmt-0x18]`, self-pointer at `[vmt-0x40]` used as a validity guard —
walking ≤6 levels looking for `"TArmy"`. Equivalent to IsClass, no new import,
rebase-proof. (Delphi 3 header: selfptr −0x40, className −0x20, parent −0x18.)

### ⚠ v1 REGRESSION — there is NO ownership gate (lesson)
v1 gated `_armyof` on `[unit+0x24] == [[0x0045DF7C]+0xA5]` (unit's player id vs
the map's local player id), assuming vanilla only ever showed the arrows for
your own party. **Wrong — `TheMapArmySelected` has no ownership test**, so
clicking an ENEMY or INDEPENDENT stack on the map fills TGeneral's party slots
with it and vanilla shows *working* arrows for it. The user hit this within
minutes: the arrows were still visible (the vanilla chain passes, so the
visibility cave is never reached) but the rewritten click handlers refused to
act — **arrows present, clicks dead**. Gate removed in v2; the map-nil checks
were kept as validity guards.

**General lesson:** when replacing a handler, the reachability of the code you
replaced is a superset of the cases your new gate imagines. Enumerate who
actually populates the state a feature reads (here: one routine,
`TheMapArmySelected`) *before* inventing a safety condition it never had.

No information leak from dropping it: the concealment filter still runs with
the LOCAL player's id, so units you cannot see are skipped, and browsing a
visible enemy stack is what the army-info dialog already offers.

## Gotchas banked here
* ⚠ **AoWx.exe DOES have a `.reloc` (11911 entries) — the note in
  [[mouse-wheel-scrolling]] that it has none is wrong.** But
  `DllCharacteristics = 0` (no ASLR) and ImageBase 0x400000, so it never
  rebases and **plain absolutes in an `.xbfs` cave are fine** — same assumption
  [[borderless-fullscreen-feature]] already ships on. Still scan .reloc before
  overwriting code ([[patching-over-relocs-gotcha]]); all three sites here are
  reloc-free and nothing branches into the displaced bytes.
* ⚠ **keystone HANGS (not errors) on `;` comment lines** in this project's
  asm blocks — strip comments before `ks.asm()`. Cost a 2-minute timeout.
* keystone exposes no symbol table, and measuring label offsets by assembling
  line prefixes breaks on forward references — use a jump table at the cave
  head instead. Also `"_next:"` is a *suffix* of `"_ao_next:"`, so any
  substring-based label split silently truncates.
* Sections: CODE VA=file+0x400C00, DATA 0x45A000, BSS 0x45B000,
  .idata 0x45C000, .rsrc 0x476000, **.xbfs 0x60D000 (raw 0x208600)**.
  DATA slots in 0x45A4xx/0x45A5xx are *pointers to* BSS globals.

Related: [[aowx-exe-string-pipeline]] (exe RE + import-repoint technique),
[[aowint-toolkit-internals]] (TAOW* widget layout), [[active-patches.md]].
