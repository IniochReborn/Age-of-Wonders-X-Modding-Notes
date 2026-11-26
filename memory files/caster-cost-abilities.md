---
name: caster-cost-abilities
description: "Four caster-cost hero abilities (Evoker/Conjurer/Enchanter/Ritualist 0xAC-0xAF, −⅓ casting cost) + vanilla instant-cast wallet fix — applied 2026-08-31, awaiting test"
metadata: 
  node_type: memory
  type: project
  originSessionId: bc99310d-e7a0-464e-8b38-a64c2704c9e7
  modified: 2026-08-31T10:30:34.461Z
---

**BXL adoption w/ user re-tunes, applied 8/31** — `build_caster_cost.py` (.bak_castercost, AoWEPACK.dll) + `patch_ability_pfs_castercost.py` (.bak_castercost on Release/Ability.pfs).

## The abilities (ids 0xAC-0xAF, verified free; Ability.pfs records 182-185)
- Evoker 0xAC → combat spells (30) · Conjurer 0xAD → summons (incl our Mermaid) · Enchanter 0xAE → unit enchantments (incl Magic Sight) · **Ritualist 0xAF → ALL global spells** (user re-scope; BXL only covered the 12 global enchantments — ours catches gtarget/city/storms/hero-globals via ELSE-classification, future-proof for new spells).
- **Discount (user formula, not BXL's 50%): newCost = cost − (cost+1)div3** → 1→1,2→1,3→2,4→3,5→3,6→4,7→5,8→5,9→6,10→7. Free stays free; ⚠ user's example said 8→6, formula gives 8→5 (flagged as likely slip — every closed form fitting the other 9 gives 5).
- Level-up cost 15 each = **Ability.pfs tag 6** (records minted programmatically; cave-written [ability+0x14] is FUTILE — pfs load overwrites; BXL's lesson). Selection mask tag 9 = 0x3FF.

## Edits (caves 0x55814F00–0x55815100; **next free 0x55815100**)
- HOOK1 THero.CastingMana entry 0x557894EC (7B) → cave_cost @0x55814F00 (124B): replay; classify spell by **[vmt+0x6C]−[vmt+0x18]** (rebase-invariant slot diff; full subtree walk on OUR dll verified: 0x6B27C summon / 0x1FF4 unit-ench / 0x120+confirm([+0x80]−[+0x18]==0x7E034) combat, confirm-fail = abstract TSpell → none / **else → Ritualist**); GetAbilityEnabled(vmt+0x148) on caster; apply formula. Vanilla off-sphere ×2 (GetSphereManaDoubled inline) still runs AFTER (we have no mastery_cost — BXL's floor hook2 dropped as unneeded; formula result ≥1 by construction).
- HOOK3 register splice 0x557BCF04 → cave_reg @0x55814FC0 (218B): replays RegisterAbility call; 4× CreateEnhancementAbility(0x5576601C; eax=id, edx=in-cave AnsiString name refcount −1 via call/pop anchors, cx=0x3FF) + RegisterAbility(0x55750238, eax=ebx control). No cost writes.
- **Wallet fix (VANILLA BUG)**: instant-cast branch charged RAW [spell+0x14] bypassing CastingMana (display≠charge; band discounted≤points<raw silently no-oped). SITE A TGlobalEnchantmentSpell.Activate 0x557EFA7C → cave_gench; SITE B TSummonSpell.Activate 0x557E44F8 → cave_summon (both call CastingMana — through our hook ✓); SITE C TSummonSpellTE.Process 0x557E4353 in-place `8b45fc ff701c 90` (push [TE+0x1C]). ⚠ Behavior change: vanilla off-sphere ×2 now actually charges on instant summons/genches.
- BXL's tripwires to remember: **Water Mastery (spell 45) ExecuteTE reads raw cost** — currently unreachable-instant (250→ over 90-pt ceiling) but re-check if its cost/casting ladder/discounts change; **Cosmagic-style spells via TCosmeticSurgerySpellCaster.Cast push raw** (residual band at SC level 1).

## Ability.pfs writer knowledge (patch_ability_pfs_castercost.py)
Container: [u32 magic 0x2144DF1C][payload][crc32(payload)]. **Top index = 3-byte prefix (01 00 00) + directory** (u8 n|0x80, u32 widecount, smalls (u8,u8), wides (u32,u32); offsets relative to directory END). Appending largest-id records: +4 wide entries + bodies at payload tail, existing offsets untouched, re-CRC. Record body (no classid): dir + tags 5(u32-len desc) 6(u32 cost) 7(01 01 00 00) 8(0) 9(u16 mask).

## Test list
Hero with Conjurer: summon costs −⅓ in book AND charged (5→3 etc); Ritualist: EVERY global (Freeze Water, storms, Town Gate, Resurrect Hero, enchantments); no ability → vanilla; 1-cost stays 1; level-up shows the four at 15 points; instant casts charge the shown price; editor can assign 0xAC-0xAF.
