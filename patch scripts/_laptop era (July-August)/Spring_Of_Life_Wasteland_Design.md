# Spring of Life — undead/wasteland conditional effect

**Status: v5 applied 2026-08-07, awaiting in-game test - core behavior + Pestilence
popup (both confirmed in v4.2) + in-cave APest SFX (new).** v4's two 5-byte site
patches in the sound/anim block caused "Exception occured during
TArmyDefaultMoveTE" + army corruption on spring placements; empirically proven
(sites reverted → stable), never explained statically — **do not re-add them**.
v5 keeps both sites byte-for-byte vanilla and plays the sound from inside the
cave instead (see v5 section below). Build:
`build_scripts/build_spring_wasteland.py` (`--apply`). Binary: **`AoWEPACK.dll`**
(the live module — AoWx.exe imports AoWEPACK.**dll**, verified in its import table;
AoWEPACK.dpl is a stale drifted copy, do not patch it). Backup:
`AoWEPACK.dll.bak_spring_wasteland`. Revert = copy the backup over the live DLL.
All addresses preferred-base VAs (base 0x55700000, file = VA − 0x55700C00); the DLL
rebases at runtime → cave is position-independent (rel32 calls + call/pop delta for
data globals).

## Behavior (user spec 2026-08-06)

| terrain under spring | living (non-undead) unit | undead unit |
|---|---|---|
| anything except wasteland | heal + Nature's Blessing (vanilla) | **nothing** (new) |
| Wasteland (5) / Cave Wasteland (0xB) | **poison-cloud effect** (new) | heal + Nature's Blessing (new) |

- **Undead test** = the engine's own Turn Undead target test
  (`TTurnUndeadAbility.CanTouchUnit`): `GetRace [vmt+0xA4] == 0x0B` OR
  `GetAbilityEnabled(0x81 Animated) [vmt+0x148]`. Covers all 14 Undead-race units
  plus runtime Animate Dead products.
- **Poison-cloud effect** = `TAbstractUnit.ExecuteStormDamage(unit, 6=Pestilence, nil)`
  @`0x55780668` — the exact per-unit routine `TPoisonCloud.ArmyPlaced` →
  `TArmy.IncommingStorm(…, 6, …)` uses: poison damage roll (role 7 / str 1, ×4 on the
  storm's on-type terrain — which wasteland is — Poison **Immunity** blocks,
  Protection halves) + Poisoned (0x60) debuff when damage > 0. The
  `TAoWMapField.GetMagicShieldActive` gate from the poison cloud is kept (shielded
  hex ⇒ no poison, blessing filter still applies).

## Where

`Spring.TSpringOfLife.ArmyPlaced` @`0x557A3F30` (sole caller) →
`ExecuteNaturesBlessing` @`0x557A3DE4`. Vanilla loop
(`0x557A3DEF..0x557A3E21`, 0x33 bytes) blindly `ExpandAbility(0x63 Nature's
Blessing) [vmt+0x94]` on every unit of the placed army — `ExpandAbility` carries the
whole heal+bless effect. The blessing sound + `TSpringOfLifeAnimation` follow at
`0x557A3E22`; function epilogue at `0x557A3F0F`.

### Hook (51 bytes, in place)

```
557A3DEF  call cave_spring        ; AL = "anyone got blessed"
557A3DF4  test al, al
557A3DF6  jz   0x557A3F0F         ; nobody blessed -> skip sound+animation
557A3DFC  jmp  0x557A3E22         ; else continue vanilla sound+animation
          nop ×36
```

### Cave @`0x55810000` (file 0x10F400, 207 bytes; free-zeros run 0x10F370–0x1E6E10)

In: `[esp+4]` = argMO (the army map-object arg; `+0x04` its message-hub
`TMapField`, `+0x1C` its `TArmy`); `esi` = spring (preserved). `ebx`/`edi` are dead
in the caller after the loop (verified) — used as flags/index.

> **v2/v3 history (same day).** v1/v2 “did nothing on wasteland” for a reason
> found only in v3: **vanilla gates the whole blessing on the terrain under the
> spring** — TSpringOfLife.ArmyPlaced @0x557A3F47 reads [self+4]+0x14
> (spring’s field → terrain) and returns without calling
> ExecuteNaturesBlessing when it is Snow(3) or Wasteland(5). A frozen/dead
> spring is vanilla behavior — the cave was simply never reached on wasteland.
> **v3 NOPs the Wasteland je** (0x557A3F53: 74 09 → 90 90); Snow stays
> inactive (vanilla, user didn’t ask to change it). The v2 rewrite of the
> terrain read (below) was motivated by a wrong “two field objects” theory —
> [argMO+4]+0x14 was in fact a fine terrain read — but the GetLocation→
> GetField pattern is equally correct and battle-tested, so it stays.

1. terrain: `TAbstractUnit.GetLocation(unit0, &x, &y, &lvl)` @`0x5577ED94`
   (x==0xFF ⇒ off-map ⇒ treat as non-wasteland), then
   `TMapContainer.GetField([AoWHSMap+0x10], x, y, lvl)` @thunk `0x557020FC`,
   terrain = byte `[cell+0x14]`; wasteland = 5 or 0xB → `bl`. Empty army ⇒ no-op.
2. if wasteland — `IncommingStorm` entry parity for MP determinism:
   reseed `System.RandSeed` (IAT slot `0x558FB720`) from `TAoWHSMap.Random(0xFFFFFF)`
   @`0x5577827C` (map ptr global `0x558FA040`, PIC via call/pop delta), then
   `TEChangeNotifyNode.BeginUpdate(army)` @`0x55703284` (thunk)
3. per unit (`TUnitList.GetUnit` @`0x5578309C`, live Count each pass):
   bless iff `undead == wasteland` (sets `bh`); poison living-on-wasteland via
   `ExecuteStormDamage` unless `GetMagicShieldActive(field)` @`0x55771D38`
4. if wasteland: `TArmy.Validate` @`0x5578CF7C` (reap poison deaths) then
   `EndUpdate` @`0x5570328C` — same order as `IncommingStorm`'s tail
5. `AL = bh`

## v4 additions — event popup + wasteland SFX (user request after v3 confirmed)

- **Pestilence event popup**: the cave now replicates IncommingStorm's event-log
  flow on wasteland — `TArmyEventLog.Create` @`0x5578BB6C` (classref slot
  `0x557135E8`), name/text = `TranslateRStr(TStormTypeRStr[6])` @`0x557249FC` into
  log+0x1C (`LStrAsg` `0x55701150`) and log+0x20 vcall+0x34, owner byte
  `[army+0x12]` → log+0x10, type 2 → log+0x24, army snapshot via log+0x18
  vcall+0xC0 (cl=0xFF), per-unit (damage, `StormDamageType[6]`=0x10) appended to
  log+0x28/+0x2C TByteLists (`Add` @`0x55702EFC`; blessed/skipped undead log
  damage 0, like immune units in a real cloud). If any damage landed:
  `TArmyEventLog.ValidateGameOver` @`0x5578BDDC` (closes the old leader-death gap)
  + `DistributeLocationEventLog` @`0x557FE558` (the popup). Log freed via
  vcall+0x2C; temp AnsiString LStrClr'd (`0x55701140`).
- ~~**Wasteland SFX via site patches**~~ **REMOVED (caused the crashes)**: v4
  redirected SFX @`0x557A3E67` (`mov eax, ENCHP02-literal` → `call sfx_pick`)
  and Anim @`0x557A3E94` (`call Visible` → `call anim_gate`). Result:
  "Exception occured during TArmyDefaultMoveTE" (Network.dpl token-wrapper
  catch-all) on spring placements + army corruption (disband/duplicate) from
  the interrupted move token. Sites reverted → stable. **Never re-add.**

## v5 (2026-08-07) — in-cave APest SFX, sites stay vanilla

Vanilla sound gate (disassembled @`0x557A3E22..66`): play ENCHP02 if the placed
army's owner byte `[army+0x12]` == local player byte `[[0x558E9494]]+0xA5`,
else if `TAoWHSMap.Watching(map=[[0x558E9494]], x, y, 0, level)` @`0x55775B88`
— spring coords via `esi` virtuals `+0x74`(x)/`+0x78`(y)/`+0x7C`(level), args
pushed level, 0, y(popped to ecx), x in edx, `ret 8`.

The cave now replicates that gate byte-for-byte (globals via PIC delta) **on
wasteland when bh≠0** (someone blessed or poisoned; all-shielded stays silent),
then `PlaySample(APest-literal)` @thunk `0x55702D04` — placed *before*
`TArmy.Validate` so the army is still intact. The cave then returns **AL=0 on
wasteland**, so the hook's `jz` skips the whole vanilla sound/anim block: no
chime, no sparkle on wasteland. On normal terrain AL = blessed-any and the
vanilla block runs untouched (chime + sparkle, its own gates intact).
`sfx_pick`/`anim_gate` deleted from the cave; the two sites are permanently
vanilla (the build script restores them if it finds a prior version's call).
Diag: scratch+3 = 2 (APest played) / 3 (gated off, not watching).

## Remaining deviations from a real poison cloud

- Poison strength 4 (1×4 wasteland on-type bonus) rolled once per placement; no
  looping ambient cloud visual — the spring keeps its own graphics.

## Notes / verification trail

- Vcall slots verified on the **TAbstractUnit** VMT @`0x55710740` (not the combat
  VMT): +0x94 ExpandAbility, +0xA4 GetRace, +0x148 GetAbilityEnabled, +0xEC
  GetImmunityTypes.
- Ability ids: 0x63 `TNaturesBlessingAbility`, 0x81 `TAnimatedAbility`,
  0x60 Poisoned; Undead race = 0x0B; Pestilence storm index = 6.
- Poison-immunity coverage (game-sourced manual data): 13/14 Undead-race units are
  Poison-Immune; **Hell Hound is not** — a Hell Hound on a wasteland spring gets
  blessed and is *not* poisoned (per-unit filtering, not army-wide
  `IncommingStorm`, exactly for this case + Animated units).
- Springs flip behavior dynamically if terrain changes (Death Storm makes
  wasteland; Healing Showers cures it) — terrain is read per placement.
