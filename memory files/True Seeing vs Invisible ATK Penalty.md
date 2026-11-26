# True Seeing vs Invisible ATK Penalty

**One-line:** An attacker that **lacks True Seeing / True Vision** (ability `0x29`) and strikes a target that **has Invisibility** (ability `0x36`) takes an ATK penalty — melee **−3**, ranged **short/tier1 = 0 / medium/tier2 = −2 / long/tier3+ = −3**.

**Status:** CONFIRMED WORKING in-game. Target: `AoWEPACK.dll` (ImageBase `0x55700000`, VA = file_off + `0x55700C00`).

---

## Files patched
- `AoWEPACK.dll` only.
- Pre-feature backup: `AoWEPACK.dll.bak_trueseeing`.

## Design note
The trigger requires the **target** (is it invisible?), which only exists at strike/shot creation — so this is a **strike-time** slayer-style injection, NOT a `GetAttack` modifier. It therefore does **not** show on the unit's general Attack stat (correct — it's conditional). It **stacks additively** with the Night-Vision underground penalty (that one is applied stat-level; this one on the already-computed value).

## RE findings (reusable)
- **True Seeing / True Vision = ability id `0x29`; Invisibility = ability id `0x36`.**
- **Combat-object HasAbility (`GetAbilityEnabled`) = vtable `[ecx+0xA8]`.** Call form: `mov edx,<id>; mov eax,<combat unit>; mov ecx,[eax]; call [ecx+0xA8]` → `al != 0` = has it.
- **Melee needs TWO strike tables** (the "only-opportunities-worked" lesson): one covers deliberate + retaliation strikes, the other round/opportunity/ability strikes. Both are hooked.

| site | function | attacker reg | target reg | ATK slot |
|---|---|---|---|---|
| melee 1 | global `CreateStrikeCA` @`0x557665E4` | `ebp` | `esi` | `bl` (byte, clamp ≥1) |
| melee 2 | `TMeleeRound.CalculateStrikes` @~`0x55767C50` | `esi` | `edi` | `dword[ebx]` (signed) |
| ranged | `CreateRangedAttackCA` @`0x5576EAE4` | `esi` | `[ebp-4]` | `byte[esp]` (clamp ≥1) |

- **Ranged range tier = `[ebx+0x28]`** at the ranged site (`ebx` = the ranged ability). Tier ≤1 → 0, tier2 → −2, tier3+ → cap −3.

## The patch
### Hooks (steal → jmp cave → re-emit stolen → jmp back)
| VA | original bytes | new | back-jmp |
|---|---|---|---|
| `0x557666D8` | `e8 d731fcff` (`call 0x557298B4`) | `e9 e38d0a00` (`jmp 0x5580F4C0`) | `0x557666DD` |
| `0x55767C89` | `8b c7 8b 10 ff 52 70` (`mov eax,edi; mov edx,[eax]; call [edx+70]`) | `e9 92780a00 90 90` (`jmp 0x5580F520`) | `0x55767C90` |
| `0x5576EB1E` | `8b c6 8b 10 ff 92 b8 00 00 00` (`mov eax,esi; mov edx,[eax]; call [edx+b8]`) | `e9 5d0a0a00` + 5×`90` (`jmp 0x5580F580`) | `0x5576EB28` |

Note the melee-1 hook was deliberately placed at `0x557666D8` to steal the **rel32 `call`** (position-independent) rather than the preceding `mov eax,[0x5571E304]` absolute — see landmines.

### Caves (previously-zero free space)
- **cave_ts_melee @`0x5580F4C0` (64B):** `if !GAE(ebp,0x29) && GAE(esi,0x36): bl -= 3; if bl<1: bl=1`. Re-emit `call 0x557298B4`; `jmp 0x557666DD`. (pushes/pops eax,ecx,edx around the checks.)
- **cave_ts_melee3 @`0x5580F520` (53B):** `if !GAE(esi,0x29) && GAE(edi,0x36): dword[ebx] -= 3` (no clamp — signed modifier). Re-emit `mov eax,edi; call [edx+70]`; `jmp 0x55767C90`.
- **cave_ts_rng @`0x5580F580` (84B):** `if !GAE(esi,0x29) && GAE([ebp-4],0x36)`: tier = `[ebx+0x28]`; `if tier<=1: penalty 0`; `else { if tier>3: tier=3; dl=tier }`; `byte[esp] -= dl; if <1: =1`. Re-emit `call [edx+b8]`; `jmp 0x5576EB28`.

## Mechanism
At each strike/shot creation, if the striker lacks `0x29` and the victim has `0x36`, the ATK slot is reduced (melee −3, ranged by tier curve) before the strike command is built. Melee is double-covered so retaliation and opportunity strikes are also penalised.

## Landmines & notes
- **All three caves are PIC-safe** (verified: zero bare in-image `[0x55xxxxxx]` absolute derefs). This matters: `AoWEPACK.dll` can load **rebased** (seen at `0x01170000`). An earlier v1 hooked melee-1 at `0x557666CF` and re-emitted a stolen `mov eax,[0x5571E304]` (absolute class-pointer) inside the cave → at a rebased base it read garbage and the strike constructor `call 0x557298B4` deref'd it → **"Runtime error 216 at 00003924" at EXE startup** (CreateStrikeCA runs during startup init). Fix = move the hook to steal only the rel32 `call`, leaving the absolute `mov` in place at `0x557666D3`.
- **Latent-rebase warning for neighbours:** the Night-Vision and Path-of-Sand caves DO use bare `mov eax,[abs]` reads; they've only worked because those launches were at the preferred base. Convert to the PIC delta-trick if a rebased launch ever breaks them.
- **Layering:** these hooks share the CreateStrikeCA / CalculateStrikes / CreateRangedAttackCA functions with the mod's slayer/hero-slaying caves — but at **different offsets** (after them), so they're independent.
- **Scope choice:** "invisible" = Invisibility `0x36` only. To also count the Concealment enchantment (`0xA2`), add `|| GAE(target,0xA2)` per cave. Terrain concealments intentionally excluded.

## Apply
Accompanying `true_seeing_vs_invisible_atk_penalty_patch.py` writes the 6 ranges and self-verifies with `--verify`.
