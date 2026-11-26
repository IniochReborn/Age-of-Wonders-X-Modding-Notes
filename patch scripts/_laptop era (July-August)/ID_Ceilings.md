# Ability and spell ID ceilings — the complete bound map

**Status: CONFIRMED against the live binaries 2026-08-28.** Written after adjudicating Inioch's
id-ceiling claims (checklist rows S5N-151, S5F-103, S5P-132, S5N-137, S5F-104, S5N-82, S5P-71,
S5P-33, S5P-32, S5N-80, S5N-81, S5F-66, S5F-83, S5P-118, S5N-136).

## The headline

**Ziggurat ships nothing that exceeds a real, enforced engine limit.** No crash, no range-check
error, no out-of-bounds read — despite shipping seven ability ids (`0xAA`–`0xB0`, 170–176) above a
genuine `[0..169]` hardware `BOUND` in `AoWTCPCK.dpl`.

The reason is a gate, not luck, and it is the fact this whole page turns on:

```
; AoWTCPCK.dpl  SelectAbility -- deciding HEAD (selectable) vs TAIL (display-only)
004234E1  call dword ptr [ecx + 0x98]     ; TAbility.GetControlType
004234E7  test al, 2                      ; acCombatAction?
004234E9  je   0x423539                   ;   no  -> TList.Add  = TAIL
0042350B  call dword ptr [ecx + 0x84]     ; TAbility.GetCombatMode
00423511  cmp  al, 1
00423513  je   0x423539                   ;         -> TAIL
00423524  call TList.Insert at index [self+0x3c]
0042352C  add  dword ptr [eax + 0x3c], 1  ; HEAD, count++

; and the only writer of the bounded field refuses anything past the head count:
00422FFB  cmp  eax, dword ptr [ebp - 0x14]
00422FFE  jle  0x4231bd                   ; index >= head count -> BAIL, [+0x34] stays -1
```

`[TTacticalCombatUnitHS+0x34]` is **the only ability-id value that ever reaches a `BOUND`**. All
seven Ziggurat ids are plain `TEnhancementAbility` — verified: Shield's registration cave at
`0x5582313E` is `mov eax,0xB0` / `call 0x5576601C CreateEnhancementAbility` — and
`TAbility.GetControlType @0x5574E730` is `mov al,[0x5574E738]` with that byte **= 0x00**. So
`test al,2` is false, they go to the tail, they are never selectable, and `+0x34` never holds
170–176.

⚠ **This is a property of the ABILITY CLASS, not of the id.** See the forward hazard below.

## Every real limit

Only `AoWTCPCK.dpl` was compiled with range checks on; `AoW.exe`, `AoWEPACK.dpl` and `aowInt.dpl`
contain no real `BOUND` instructions at all.

| # | module | site(s) | limit | guards | above it | ours? |
|---|---|---|---|---|---|---|
| A1 | AoWTCPCK | 15 `bound` reads, 9 distinct pairs | `[0..169]` | `AoWTC.AbilTypes @0x00467248` (170 B) | `BOUND` #BR → range-check error | vanilla, **unreachable** (see above) |
| A2 | AoWTCPCK | `0x0042354A` `cmp [ebp-8],0xB1` | ids 1..0xB0 | `CreateTCAbList` loop | id silently unlisted | **ours** — `build_tcablist_ceiling.py` raised 0xAA→0xB1 |
| A3 | AoWTCPCK | `0x418A73 0x418D1F 0x4190FA 0x41977F` `cmp …,0xAA` | ids ≤ 0xA9 | four `TCAI.EvalBattle` scan loops | **the tactical AI never sees the ability** | vanilla, **unraised** |
| A4 | AoW.exe | `0x00406DEF` `cmp esi,0xAA` | ids ≤ 0xA9 | `TItemBanner.IBannerPopupShow` | omitted from the item banner popup | vanilla, **unraised** |
| A5 | AoW.exe | `0x00455DE1` `cmp ebx,0xAA` | ids ≤ 0xA9 | unit hover banner popup | omitted from the hover popup | vanilla, **unraised** |
| A6 | AoWTCPCK | `0x4227AD`/`0x4227D3` | 14-entry whitelist | `AoWTC.StatusAbils @0x004675B8` | no status overlay icon | vanilla |
| A7 | AoWEPACK | `TAbilityControl.GetAbility @0x557501C0` | `id<0` / `id>=Count` | registry TList | negative → assertion `'Invalid AbilityID'`; **≥Count → nil, silent** | vanilla |
| A8 | AoWEPACK | `RegisterAbility @0x55750238` | **no upper bound**; nil-pads to `id` | registry | **duplicate id → runtime 217** | vanilla |
| A9 | AoWEPACK | `0x5577F618`, `0x5574E0E0` | `cmp edx,[eax+0xC]; jae` | per-owner bitset | returns False — no wild read | vanilla |
| S1 | AoWTCPCK | 13 reads, 9 pairs | `[0..130]` | `AoWTC.SpellTypes @0x004672F4` (131 B) | `BOUND` #BR → range-check error | vanilla |
| S2 | AoWTCPCK | `0x4188D4 0x418C9B 0x419076 0x4196F4` `cmp …,0x83` | ids ≤ 130 | `TCAI.EvalBattle` spell scans | AI never evaluates the spell | vanilla |
| S3 | AoW.exe | `0x0042F30D` | `id≥100` needs `SpellTypes[id]≠0` | spellbook page builder | **spell silently deleted from the book** | the neighbouring `jl` at `0x42F2F5` is `build_tierresearch_exe.py`'s cave call |
| S4 | AoWEPACK | `RegisterSpell @0x55779B40` | none — TList grows | spell registry | `GetSpell` → nil past count | vanilla |

## The true ceilings today

**Abilities — highest working id 176 (`0xB0`, Shield).** 156 ids in use, 0…176, with 21 vanilla
gaps (`33, 78–85, 91, 102–105, 110, 133–137, 151`). Sparseness is harmless — A7/A9 fail closed and
A8 nil-pads.

⚠ **The forward hazard.** A new ability at id ≥ 170 built on `TTouchAbility`,
`TRangedAttackAbility`, `THealingAbility`, `TDispelMagicAbility` or `TSpellCastingAbility` **is**
selectable (`GetControlType & 2`), so it lands in `+0x34` and **will** hit `bound eax,(0,169)` on
the next map click — a range-check error. `TEnhancementAbility` / `TStrikeAbility` (`0x00`) and
`TConstructAbility` (`0x01`) stay safe. **So the rule is: above 169, passives only — or raise A1's
nine bound pairs first.**

**Spells — highest working id 130.** 108 ids in use, 1…130; free ids are **79–99 and 109** (22).
Every shipped id ≥ 100 has a non-zero `SpellTypes` byte, so none is hidden by S3.

⚠ **131 is a genuine wall, and widening it is worse than hitting it.** `AoWTC.SpellTypes` is sized
to exactly 131 bytes and the next byte is live data (`AoWTC.BreathHit @0x467378`, then
`BreathDir @0x4673A8`). Raising the nine `[0..130]` bound pairs converts a loud `ERangeError` into
a **silent read of the breath tables**, and *writing* a `SpellTypes` byte past 130 corrupts them.
Going past 130 honestly means relocating the array — 12 disp32 refs, the DATA pointer
`0x004693F8`, nine bound pairs, the export RVA, and `AoW.exe`'s IAT slot `0x0045EBEC`.

**New-spell build rule:** any new spell id ≥ 100 must be given a non-zero `SpellTypes[id]` byte or
it vanishes from the spellbook without a word (S3).

## Claims examined and rejected

- **"A sparse ability id crashes at startup with runtime error 216."** False, and Inioch retracts
  it himself (his real cause was a wrong base classref). We ship 21 vanilla gaps that boot fine.
  The correct pair: **217 = duplicate id** (`RegisterAbility` raises before a handler exists);
  **216 in this project's records is heap corruption from the combat-log length-byte over-read**,
  nothing to do with ability ids. **Density does not matter; uniqueness does.**
- **"`SpellTypes` is bound-limited, not size-limited"** — refuted. The export gap to `BreathHit`
  is 132 bytes for a declared 131. `SpellTypes[200]` does not read 0; it reads 6.
- **"He had a spell working at id 202"** — he has a latent range-check error, not a working spell.
  `SpellTypes[202]` is byte 2 of `BreathDir` element 6; `EvalBreath @0x4151B2` then computes
  `n*12+off-12` and bounds it to `[0..71]`, which 7 already overflows.
- **"Ability ids must stay ≤ 171"** — an artefact of where he stopped zeroing pad bytes, not an
  engine property. The real constraint is the class rule above.
- **"pfs key ↔ spell id is not closed-form"** — refuted. `key = id + 10`, 108/108 in our data,
  and code-derived from `TSpellControl.ReadWrite @0x55779A6C` (`lea ecx,[ebx+0xA]`).

## ⚠ What IS wrong in our build (found by this pass)

Not a crash — a **silence**. Three vanilla `0xAA` ceilings were never raised alongside
`build_tcablist_ceiling.py`, so all seven Ziggurat abilities are missing from:

1. **the tactical AI's evaluation** (A3, four loops) — the AI is blind to Shield, Magebane,
   Drillmaster and the rest when scoring a battle. This is a balance defect, not cosmetic.
2. **the item banner popup** (A4)
3. **the unit hover popup** (A5)

Demonstration: hover a Human Man-at-Arms (Unitres record 3, carries `0xB0`) — Shield is absent
from the banner popup while present in the full unit dialog and the in-combat panel. Same one-byte
idiom `build_tcablist_ceiling.py` already fixed once; three more sites of it exist.
