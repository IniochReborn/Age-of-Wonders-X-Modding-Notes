---
name: trueseeing-vs-invisible-atk-penalty
description: "Attackers WITHOUT True Seeing (0x29) suffer ATK penalties when striking a target WITH Invisibility (0x36): melee -3, ranged by range tier (short 0 / medium -2 / long -3). Strike-time injection at 3 combat sites. Stacks with the night-vision stat penalty. AoWEPACK.dll, 2026-07-23. CONFIRMED WORKING in-game (after 2 fixes: melee-1 PIC hook move, and the Path-of-Sand rebase fix that was the real startup-crash culprit)."
metadata:
  node_type: memory
  type: project
  originSessionId: ae619055-3278-433b-b71b-cf21e5789ad7
  modified: 2026-07-23T08:55:05.318Z
---

**GOAL (user):** Hybrid of BXL's True-Seeing-vs-Invisible idea + our night-vision debuff, but as a DEBUFF: a unit/hero that LACKS **True Seeing** ("True Vision", ability **0x29**) and attacks a target that HAS **Invisibility** (**0x36**) suffers **melee -3 ATK**, **ranged: short 0 / medium -2 / long -3** (by ability range tier). **Trigger = target-invisible only** (chosen by user; NOT underground, NOT unconditional). **Stacks with the night-vision penalty** (night-vision is applied to the ATTACK STAT via TUnit/THero.GetAttack + GetAttackRA; this one is applied at STRIKE time to the already-computed value, so they add). Applied 2026-07-23. Backup `AoWEPACK.dll.bak_trueseeing`.

**WHY STRIKE-TIME (not stat-level like night vision):** the condition needs the TARGET (is it invisible?), which only exists at strike/shot creation. So this is a slayer-style injection, NOT a GetAttack modifier — it does NOT show on the unit's general Attack stat (correct: it's conditional). Combat objects: **GetAbilityEnabled = VMT+0xa8** (`mov edx,id; mov eax,obj; mov ecx,[eax]; call [ecx+0xa8]`).

**THREE injection sites (melee needs TWO tables — BXL's "only-opportunities-worked" lesson; one covers deliberate+retaliation, the other round/opportunity/ability):**
| site | function | attacker | target | ATK slot | hook (steal→jmp cave→re-emit→jmp back) | cave |
|---|---|---|---|---|---|---|
| melee 1 | global CreateStrikeCA @0x557665E4 | **ebp** | **esi** | **bl** (byte, clamp≥1) | @**0x557666D8** steal 5B `e8d731fcff` (=call 0x557298b4) → back 0x557666DD | cave_ts_melee @**0x5580F4C0** (64B) |
| melee 2 | TMeleeRound.CalculateStrikes @~0x55767C50 | **esi** | **edi** | **dword[ebx]** (signed modifier, no clamp) | @**0x55767C89** steal 7B `8bc78b10ff5270` → back 0x55767C90 | cave_ts_melee3 @**0x5580F520** (53B) |
| ranged | CreateRangedAttackCA @0x5576EAE4 | **esi** | **[ebp-4]** | **byte[esp]** (pushed @0x5576EB1D, clamp≥1) | @**0x5576EB1E** steal 10B `8bc68b10ff92b8000000` → back 0x5576EB28 | cave_ts_rng @**0x5580F580** (84B) |

Each cave: `if !GAE(attacker,0x29) && GAE(target,0x36): <ATK> -= penalty`. Ranged penalty = tier from **[ebx+0x28]** (ebx=the ranged ability at that site; [+0x28]=GetRangeRA tier): tier<=1→0, tier2→-2, tier3+→-3 (cap 3). Emulation-verified all 3: penalties correct, tier curve correct, byte-clamp to 1, HAS-TS / not-invisible → no change, registers/stack preserved. Caves in fresh space after path-of-sand (0x5580F4A9); NO overlap with our slayer/hero caves @0x5580E0xx-E5xx.

**SCOPE:** "invisible" = Invisibility 0x36 ONLY (BXL's recommended default). To also count the **Concealment enchantment 0xa2** (units hidden by the Concealment spell), add a `|| GAE(target,0xa2)` per cave. Terrain concealments intentionally excluded.

**REVERT:** restore `AoWEPACK.dll.bak_trueseeing`. Layering note: hooks CreateStrikeCA/CalculateStrikes/CreateRangedAttackCA which ALSO host our existing slayer/hero-slaying caves (jmps to 0x5580E3B0/E410/E470/E4A0/E500) — my hooks are at DIFFERENT offsets (after those), independent. See [[underground-nightvision-atk-penalty]] (the stat-level night-vision penalty this stacks with), [[bxl-reference]] (True Vision 0x29 / Invisibility 0x36; slayer injection framework).

**STARTUP-CRASH BUG (v1) — FIXED as v2 2026-07-23.** v1 hooked melee-1 @0x557666CF and re-emitted the stolen `mov eax,[0x5571e304]` (an ABSOLUTE class-pointer ref) inside the cave. AoWEPACK can load REBASED (seen at 0x01170000) — at a rebased base the cave read the wrong class pointer, and the strike constructor call 0x557298b4 deref'd garbage → **"Runtime error 216 at 00003924" at EXE STARTUP** (CreateStrikeCA is exercised during startup init). Our existing JMP-caves avoid this via the PIC trick (`call $+5;pop;sub base;mov [reg+abs]`) — a plain `mov [abs]` in a cave is a LATENT rebase bug. **FIX: moved the melee-1 hook to @0x557666D8 (steal the rel32 `call 0x557298b4` — position-independent), leaving the absolute `mov eax,[0x5571e304]` in place at 0x557666D3; the cave push/pops eax/ecx/edx around the checks and re-emits the rel32 call.** All 3 caves now verified to contain ZERO absolute `[0x55xxxxxx]` refs (M1/M2/RNG all PIC-safe). Backup of the crashing v1 attempt approach not kept; pre-v2 backup = `AoWEPACK.dll.bak_trueseeing` (clean) + `AoWEPACK.dll.bak_trueseeing2`. **NOTE — latent rebase risk elsewhere:** the night-vision caves and path-of-sand caves DO use plain `mov eax,[0x558fa040]`/`[0x557bcfc0]` absolutes; they've worked only because those launches were at the PREFERRED base. If a rebased launch ever breaks them, convert those data reads to the PIC trick too.

**CONFIRMED WORKING in-game 2026-07-23** (reliable startup across many launches + penalties correct). NOTE: the intermittent "Runtime error 216 at 00003924" startup crash during this feature's testing was NOT true-seeing — it was the Path-of-Sand caves' bare-absolute rebase bug (see [[path-of-sand-ability]]); true-seeing's own caves are all PIC-safe.
