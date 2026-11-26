# Underground Night Vision ATK Penalty

**One-line:** On underground map levels, any unit/hero that lacks **Night Vision** (ability `0x27`) takes an ATK penalty — melee **−1**, ranged **short/tier1 = 0 / medium/tier2 = −1 / long/tier3+ = −2**.

**Status:** CONFIRMED WORKING in-game (incl. city-production crash fix). Target: `AoWEPACK.dll` (ImageBase `0x55700000`, VA = file_off + `0x55700C00`).

---

## Files patched
- `AoWEPACK.dll` only.
- Pre-feature backup: `AoWEPACK.dll.bak_nightvision`. Shipped build: `AoWEPACK.dll.bak_nightvision_fix2` (== live at these offsets).

## Design note
The penalty is applied **at the ATK-stat getters**, not strike-time — so it *is* visible in the unit's Attack stat / previews while underground (unlike the True-Seeing feature, which is conditional on the target and injected strike-time). Ranged and melee use **separate** getters, so there is no double-dip.

## RE findings (reusable)
- **Night Vision = ability id `0x27`.**
- **Ranged ATK getter = `TRangedAttackAbility.GetAttackRA` @`0x5576E65C`.** On entry `eax` = the ranged-attack ability (Self), `esi` = attacker unit, `bl` = the attack accumulator that the function returns via `mov eax,ebx` at every exit. **Range tier = byte `[ability+0x28]`** (`GetRangeRA` @`0x5576E610`). ⚠ `[ability+0x28]` is a **range TIER (0..3), not a hex count** — the +1/+2/+4 distance bonus in `fcValidRoundDistance` @`0x5576ECF0` keys off it.
- **Melee ATK getter (regular units) = `TUnit.GetAttack` @`0x557829EC`.** Strategic `TUnit` = `ebx` throughout. It already hosted a "morale→ATK" cave via `call 0x5580F0B0` @`0x55782A00` (single caller) — this feature repoints that call to a wrapper.
- **Melee ATK getter (heroes) = `THero.GetAttack` @`0x55788360`.** Hero = `ebp`; base atk sits in the stack byte `[esp]`. It hosted a hero-morale cave (exit `mov [esp],al; jmp 0x557883B6` @`0x5580F127`) — repointed here.
- **HasAbility used by these caves = vtable `[ecx+0x88]`** — the "GetAbilityEnabled" wrapper (`mov edx,id; mov eax,unit; mov ecx,[eax]; call [ecx+0x88]`, returns `al`). *(Combat-unit HasAbility is `[ecx+0xA8]`; the strategic-unit getters here use `[ecx+0x88]`.)*
- **Underground detection = `GetLocation` @`0x5577ED94`** (`eax`=unit; `edx`/`ecx`=out ptrs; +1 pushed stack-ptr; `ret 4`). Snippet: `sub esp,3; lea eax,[esp+2]; push eax; lea ecx,[esp+4]; lea edx,[esp+3]; mov eax,<unit>; call 0x5577ED94; mov al,[esp+2]; add esp,3`. `al` = level byte; **`!=0` ⇒ underground**, `0` ⇒ surface. Safe on unplaced units (returns `0xFF` sentinel) **but only if the unit's data is ready** — see landmines.

## The patch
### Hooks / repoints
| VA | original | new | purpose |
|---|---|---|---|
| `0x5576E660` | `8a 58 2a 85 f6` (`mov bl,[eax+2a]; test esi,esi`) | `e9 9b0b0a00` (`jmp 0x5580F200`) | GetAttackRA entry → cave_ranged |
| `0x55782A00` | `e8 abc60800` (`call 0x5580F0B0` morale) | `e8 bfc80800` (`call 0x5580F2C4`) | TUnit.GetAttack morale-call → cave_matk |
| `0x5580F127` | `e9 8a92f7ff` (`jmp 0x557883B6`) | `e9 14020000` (`jmp 0x5580F340`) | hero-morale cave exit → cave_hmatk |

### Caves (previously-zero free space)
- **cave_ranged @`0x5580F200` (98B):** `movzx edx,[eax+28]`(tier); `mov bl,[eax+2a]`(stolen base). Guard `esi` and `[esi+4]`. NV check (`push edx; mov edx,0x27; mov eax,esi; mov ecx,[eax]; call [ecx+0x88]; pop edx; test al; jne fin`). GetLocation(esi) underground. Penalty: `mov al,dl; cmp al,1; jbe fin; dec al; cmp al,2; jbe; mov al,2; sub bl,al` (= max(0,min(tier,3)−1)). `fin: test esi,esi` (re-emit stolen) `jmp 0x5576E665`. **Tier kept on the stack across calls — never in `bh`** (see landmine).
- **cave_matk @`0x5580F2C4` (76B):** `call 0x5580F0B0`(morale, returns al=base+morale, preserves ebx); `push eax`; guard `ebx` and `[ebx+4]`; NV(`[ecx+0x88]`,0x27); GetLocation(ebx) underground → `pop eax; dec al; ret`; else `pop eax; ret`. Melee −1.
- **cave_hmatk @`0x5580F340` (75B):** guard `[ebp+8]`(ability-bitmask ptr) and `[ebp+4]`(location link); NV(`[ecx+0x88]`,0x27); GetLocation(ebp) underground → `dec byte[esp]`; `jmp 0x557883B6`. Hero melee −1.

## Mechanism
Every call to the ranged/melee/hero ATK getter is intercepted; if the unit lacks `0x27` and its map level ≠ 0, the accumulator is reduced (ranged by tier−1, melee/hero by 1) with a min-1 clamp downstream.

## Landmines & notes
- **Never use `bl`/`bh`/`bx` as cave scratch inside `GetAttackRA`.** `ebx` is that function's return accumulator (`mov eax,ebx` on exit). An earlier version stashed the tier in `bh`; callers that read the *wide* return value (city-production display) got a corrupted pointer → AV in a downstream `GetLocation` caller. Fix = keep tier on the stack.
- **Every cave that runs during unit display / strength calc MUST guard for unplaced/prototype units** (null `[unit+4]` location link, null `[ebp+8]` ability bitmask). City production, unit lists, AI strength eval and map-load all call these getters on not-fully-placed units; unguarded `HasAbility`/`GetLocation` there crashes. cave_matk and cave_hmatk both got these guards after crashes.
- **Dependency:** the melee & hero pieces piggyback on the pre-existing "morale-ATK" cave (`0x5580F0B0` + hero-morale cave). Port that first, or apply on a binary that already has it. cave_ranged is self-contained.
- **Rebase note:** cave_matk uses a bare absolute is *not* present; but these caves DO call fixed VAs (`0x5580F0B0`, `0x5577ED94`) via rel32 (position-independent) — safe. (No bare `mov [0x55xxxxxx]` data absolutes in these three caves.)
- Dwarf-exemption RE (reverted, kept for reuse): a unit's/hero's race = byte `[[unit+0x40]+0x20]` (`TUnit.GetRace` @`0x55782C90`, `THero.GetRace` @`0x55786F9C`); dwarf index = **6** (order: 0 Human,1 Azrac,2 Lizard,3 Frostling,4 Elf,5 Halfling,6 Dwarf,7 Highman,8 DarkElf,9 Orc,10 Goblin,11 Undead,12 Independent).

## Apply
`road`-style Python script `underground_night_vision_atk_penalty_patch.py` (accompanying) writes the 6 ranges at file offsets and self-verifies with `--verify`.
