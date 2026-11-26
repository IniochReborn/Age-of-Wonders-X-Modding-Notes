# Patch Scripts Catalog

All the Python patch scripts from the project, in `patch scripts/`. Each is a self-contained applier (open file → assert original bytes → write patch → save) targeting **AoWEPACK.dll** unless noted. VA = file_offset + 0x55700C00 (imagebase 0x55700000) for AoWEPACK.dll. Most have a full docstring header explaining the RE + byte patches.

**Legend:** ✅ final/current · ⏮ superseded by a later version (kept for history) · ❌ failed/reverted (kept as reference) · 🔵 port of BXL/Ziggurat's own work (included for completeness/attribution).

> Note: several of these ability reworks are also driven at runtime by the **Hero AI Level-Up Chooser** (see that doc) — the chooser reads whatever levels/costs these scripts set.

## Tools / helpers
| Script | What it is |
|---|---|
| `engp.py` | EngineP.dpl disassembly helper (VA math + capstone wrapper). |
| `hse.py` | HSEPack.dpl disassembly helper. |
| `wav2it.py` | ✅ Wraps a rendered song (WAV) as a single-sample no-loop Impulse Tracker `.IT` module the AoW1 engine plays. See "Custom Music" doc. |
| `wav2it_drop.py` | Drag-and-drop launcher compiled into the standalone AoWxBard.exe drop-tool. |

## Leveled-ability reworks & new levels
| Script | What it does |
|---|---|
| `patch_charge_parry_leveled_v1.py` | ✅ Charge I/II/III (+2/+3/+4 DMG) & Parry I/II/III (−2/−3/−4 ATK). |
| `patch_charge_parry_cost_v1.py` | ✅ Charge/Parry level cost 10→3 per level. |
| `patch_healing_leveled_v1.py` | ✅ Healing I/II/III leveled ability. |
| `patch_wallcrush_leveled_v1.py` | ✅ Wall Crushing I/II/III (damage 2-5 / 3-10 / 4-15). |
| `patch_wallcrush_preview_v1.py` | ✅ Wall Crushing damage-preview fix. |
| `patch_lifesteal_leveled_v1.py` | ✅ Life Stealing → 3-level ability (I/II/III = +1/+2/+3 HP per hit). |
| `patch_lifesteal_round_v1.py` | 🔵 Life Stealing works on Round Attack (port of BXL's). |
| `patch_hero_slaying_leveled_v1.py` | ✅ Hero Slaying I/II/III — NEW 3-level ability **id 0x38** (+1/+1, +2/+2, +3/+3 vs heroes/leaders). |
| `patch_hero_slaying_name_v1.py` | ✅ Hero Slaying name/RStr setup (pairs with the leveled script). |
| `patch_monster_slaying_leveled_v1.py` | ✅ Monster Slaying (0x70) → 3-level ability (+1/+1, +2/+2, +3/+3). |
| `patch_monster_slaying_v1.py` | ⏮ early Monster Slaying attempt. |
| `patch_monster_slaying_v2.py` | ⏮ early Monster Slaying attempt. |
| `patch_slaying_v3.py` | ⏮ combined slaying attempt (pre-leveled). |
| `patch_slayers_ranged_v1.py` | ✅ Hero + Monster Slaying apply to short/medium ranged projectile attacks. |
| `patch_marksmanship5_v1.py` | ✅ Marksmanship V (new level V; I-IV unchanged). |
| `patch_turnundead5_v1.py` | ✅ Turn Undead V (new level V). |
| `patch_dispelmagic5_v1.py` | ✅ Dispel Magic IV + V (vanilla cap was 3). |
| `patch_leadership5_v1.py` | 🔵 Leadership rework (port of BXL's leadership4 + leadership_fix). |
| `patch_leadership_aura_refresh_v1.py` | 🔵 Leadership aura instant-refresh (BXL). |
| `patch_inherent_level_fix_v1.py` | ✅ Follow-up fix for the Leadership disable-bug patch. |
| `patch_ability_costs_v1.py` | ✅ Ability skill-point cost retune. |

## XP / medals / rank / morale / upkeep
| Script | What it does |
|---|---|
| `patch_hp_cap_v1.py` | ✅ Post-gold HP cap + XP-overflow fix. |
| `patch_capfinetune_v1.py` | ✅ HP-cap fine-tune (min one level past gold + capped ATK/RES bonus). |
| `patch_medal_icon_v1.py` | ✅ HP-cap medal icon (Combat.ILB idx 8). |
| `patch_medal_killxp_v1.py` | ✅ Victim medals count toward kill XP (units AND heroes). |
| `patch_capture_xp_cap_v1.py` | ✅ Seduce/charm/dominate captures grant only 1 XP. |
| `patch_capxp2x_v1.py` | ✅ Capped-medal victims grant 2× kill XP. |
| `patch_xp_min1_v1.py` | ✅ Minimum 1 XP per kill. |
| `patch_rank_unsigned_v1.py` | ✅ GetRank unsigned-compare fix. |
| `patch_morale_atk_res_v1.py` | ✅ Morale debuffs ATK/RES instead of DEF/RES; Terrible = −3. |
| `patch_upkeep_v2.py` | ✅ Unit upkeep retune. |
| `patch_move_predictor_v1.py` | 🔵 Movement-predictor fix (port of BXL's v4). |

## Reflecting Pool raze (feature bundle — see "Reflecting Pool Raze" doc)
| Script | What it does |
|---|---|
| `patch_reflecting_pool_raze_v2.py` | ✅ Core: makes Reflecting Pools razeable + real razed state. |
| `patch_reflecting_pool_raze_v1.py` | ⏮ first raze attempt. |
| `patch_reflecting_pool_raze_ui_v1.py` | ✅ Side-window raze button (**AoWx.exe** UI part). |
| `patch_pool_rebuild_days.py` | ✅ Rebuild time = 2 turns (like watch towers). |
| `patch_pool_vision_rebuild.py` | ✅ Rebuilding (still-razed) pool grants no pool-network vision. |
| `patch_rebuild_gfx_and_unraze_refresh.py` | ✅ Rebuild graphics (GetRazed-before-image) + unraze vision refresh. |

## GlobalSpells: summon / animate / resurrect
| Script | What it does |
|---|---|
| `patch_summoned_ability_v5.py` | ✅ "Summoned" ability (final; two small caves). |
| `patch_summoned_ability.py` / `_v2` / `_v3` / `_v4` | ⏮ earlier cave sizes/placements. |
| `patch_animate_dead_v3.py` | ✅ Animate Dead spawn (cave @0x10C20D). |
| `patch_animate_dead_v2.py` | ⏮ earlier Animate Dead. |
| `patch_resurrect_hero_animated_v1.py` | ✅ Resurrect Hero grants "Animated" (MakeAnimated vtable path). |
| `patch_recall_spirit_spawn_v1.py` | ✅ Recall Spirit spawn behaviour. |
| `patch_ad_rs_combined_rollback.py` | ⏮ combined Animate-Dead + Resurrect-Spirit rollback-state applier. |

## Other
| Script | What it does |
|---|---|
| `patch_blood_mod_v1.py` | 🔵 Blue/green per-unit blood (VERBATIM from BXL's Ziggurat binary; needs AoWTCPCK.dll + Release.hss + blood ILBs). |

## ❌ Failed / reverted (kept as cautionary reference)
| Script | What it was |
|---|---|
| `patch_raise_terrain_underground.py` | ❌ Raise Terrain (spell 0x13) underground/lava overhaul — blocker never found, fully reverted. |
| `patch_raise_terrain_v2.py` | ❌ Raise Terrain v2 attempt. |

**⚠️ Cross-file / ordering notes for BXL:** these scripts were applied incrementally onto a shared AoWEPACK.dll, so some assume earlier features' caves already exist (e.g. the night-vision melee piece piggybacks on the morale-ATK cave; Weakness registration is chained onto Path of Sand's cave). Cave VAs are this mod's free-space choices — **BXL's caves overlap ours**, so treat the scripts as RE references, not drop-in appliers on a different base.
