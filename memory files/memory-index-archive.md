---
name: memory-index-archive
description: Full snapshot of the MEMORY.md index as of 2026-11-18 (all ~270 entries with their long hooks, cave addresses and status notes) - search here for older topics no longer listed in the short index
metadata:
  type: reference
---

Snapshot taken 2026-11-18 when the index was shortened. Entries for work before November 2026 are listed ONLY here; the topic files they link to are still in this directory. Status notes are as of the snapshot.

# Age of Wonders X - Claude Session Memory

## Project Overview
AoWx — community mod for Age of Wonders (1999, Delphi). No source; everything is binary patching of AoWx.exe, AoWEPACK.dll, AoWTCPCK.dll, HSEPack.dpl, aowInt.dpl, VCL30.dpl, and **AoWDevX.exe** (editor; renamed from AoWDevEd.exe 7/21).
**DLL vs DPL**: .dll = modded/live, .dpl = original — except HSEPack/aowInt/VCL30/Dcpack .dpl are live (no .dll twin).
**VA math**: AoWEPACK.dll = file+0x55700C00 · AoWTCPCK.dll & AoWx.exe = file+0x400C00 · HSEPack.dpl = file+0x55600C00 · aowInt.dpl CODE = file+0x59800C00 (DATA = file+0x59801A00!) · VCL30.dpl = file+0x41300C00 · Dcpack.dpl = file+0x55100C00.
**🏠 10/11 INSTALLED the laptop's Oct-11 delta into the project root** (dual-sphere Death/Fire spells, High Prayer glow, AoO vcall soft-lock fix, SpellTypes relocation → 0x43C000; see [[transfer-home-2026-10-11]]). Overwritten files saved in `backup\pre_oct11\`. Laptop STALE after 10/11.
**🏠 9/20 INSTALLED laptop 410 work INTO THE PROJECT ROOT** (user: no 410 subfolder — the project folder stays the game dir; 410 binaries/data/backups merged over it, AOW_GAME_DIR = project root; laptop backups now in `backup\` via `patch scripts\bakpath.py`). The 31 laptop scripts had BAKED laptop paths (`C:\Users\<user>\...\410 prerelease`) — rewritten 9/20 to `bakpath.game_dir()/game_file()` (AOW_GAME_DIR or parent of patch scripts); all dry-run as ALREADY PATCHED. Home python is `py -3.10`. See [[transfer-home-2026-09-20]] + [[aowx-410-pending-tests]].
**Next free caves** (full history in [next-free-caves.md](next-free-caves.md)): AoWEPACK ⚠ index STALE (0x55864300 taken by drought) — scan script range claims; 0x55833100+ free 10/21 · AoWTCPCK **0x43E820** (to 0x43E900; 0x43B100–0x43C000 + 0x43C240–0x43C400 also free; Implosion v2 zone B 0x43E000–0x43E16D; alias zone now 0x43AD00–0x43AF00; SpellTypes table 0x43C000–0x43C200) · AoWx.exe `.xbfs` FULL → `.xtut` FULL to 0x639000 (scroll spells took 0x638C00) (CODE full; exe DOES have a .reloc) · aowInt **0x59824700** · VCL30 CODE 0x413A91C0 · AoWDevX section table FULL. **Always**: scan .reloc ([[patching-over-relocs-gotcha]]); PIC delta-trick for in-image addresses ([[rebase-crash-runtime-error-216]]).
**Always**: scan .reloc before overwriting code ([[patching-over-relocs-gotcha]]); PIC delta-trick for in-image addresses ([[rebase-crash-runtime-error-216]]).

## Laptop era 2026-08-20→08-30 (installed at home 8/30; laptop game dir stale after)
- [transfer-home-2026-08-30.md](transfer-home-2026-08-30.md) — laptop→desktop package in `transfer to home PC\`.
- [aowx-project-overview.md](aowx-project-overview.md) — (laptop 9/18 version) house conventions; **backups now in `<game>\backup\` via bakpath.py; patch the .dll never the .dpl; r+b in-place writes**.
- [aowint-toolkit-internals.md](aowint-toolkit-internals.md) — aowInt widget toolkit RE: offsets, VMTs, input dispatch.
- [aowint-cave-map.md](aowint-cave-map.md) — aowInt+VCL30 cave map (wheel evolution, chords, VK table 0x413E7170).
- [aowx-exe-string-pipeline.md](aowx-exe-string-pipeline.md) — resourcestring/TranslateRStr machinery, import-repoint technique.
- [aowepack-ability-system.md](aowepack-ability-system.md) — (laptop 9/15 version) ability owners/data/level chain, item granting, once-per-day heal, Holy/Unholy Champion I-III + ranged; runtime-unit-copies gotcha.
- [aowsetup-internals.md](aowsetup-internals.md) — AoWSetup VCL runtime-UI, .xmou section, Mouse tab.
- [aowdevx-binary-notes.md](aowdevx-binary-notes.md) — editor title/icon sites, CODE-tail cave (full), .dlgd slack, Item Properties HP/MV rows (.xitm), Developer prune menu (.xprn; section table FULL); 🛑 dark theme reverted (user: looks bad), RE gold kept; 🔨 valgoto (.vgo) + timerres/render gate (.tres/.rgt) applied 8/31 awaiting test.
- [aowx-release-process.md](aowx-release-process.md) — changelog JSON, build_release_zip.py, upload/ layout; **1.37.410 CUT 9/23** (zip+installer in upload/, awaiting upload; --add list inside).
- [aowx-installer.md](aowx-installer.md) — Inno Setup installer; build_installer.py.
- [aowx-ai-turn-hang.md](aowx-ai-turn-hang.md) — Athendore AI livelock diagnosis; elevated live-probe tooling.
- [ilb-image-format.md](ilb-image-format.md) — .ILB layout, Type-0 terminator gotchas.
- [cam-campaign-format.md](cam-campaign-format.md) — .cam container format, round-trip verified.
- [modding-tools-plan.md](modding-tools-plan.md) — modding launcher/AoWxImg/AoWxQuest/AoWxInk; PySide6.
- [qt-dark-mode-win10-fusion.md](qt-dark-mode-win10-fusion.md) — pin_dark needs setStyle("Fusion") on Win10; pip needs --trusted-host.
- [mld-localisation.md](mld-localisation.md) — .mld format; **Russian REMOVED 8/26**.
- [aowx-bitmap-fonts.md](aowx-bitmap-fonts.md) — Int\Fonts ILB structure; Cyrillic reverted 8/26.
- [aowx-7th-language-crash.md](aowx-7th-language-crash.md) — engine hardcodes 6 languages; VEH crash-capture tool.

## 410 prerelease (laptop 2026-09-09→09-18; merged into project root 9/20)
- ⭐ [410 pending tests](aowx-410-pending-tests.md) — READ FIRST: what is applied in the 410 binaries and still untested (banner ceilings, storm roll/sources, tactical-AI melee/ranged, healing AI, Leadership followers, ranged obstacles); revert order + backups.
- [Transfer home 2026-09-20](transfer-home-2026-09-20.md) — package contents; installed 9/20 by MERGING the 410 folder over the project root (no subfolder), scripts de-baked, memory merged.
- [Tactical AI scoring](aowx-tactical-ai-scoring.md) — TCAI.CheckUnit melee/ranged/touch formulas, frame slots (target=[ebp+0x10], self=[ebp+0x14]), healing valuation, bold-streak roll; caves 0x438B00–0x439010, next free 0x439100.
- [Ranged obstacles + AI shot scoring](aowx-ranged-obstacles.md) — MakeRangedPath block-% formula, EvalPath/EvalHex EV model; patch_ai_ranged_obstacles_v1 applied 9/18.
- [Damage effects + storm debuffs](aowx-damage-effects.md) — ExecuteDamageEffectsRole layout, lightning ignites machines, storm/plant debuffs roll vs RES, Divine Storm/Holy/Unholy Ground effects; next free AoWEPACK cave 0x55816280.
- [Leadership aura machinery](aowx-leadership.md) — "others only" rework (patch_leadership_others_v1); followers fix 9/17; 🔨 10/12 "+V received" suffix added, zone 2 moved to 0x55862200, ⚠ script apply bug (partial rewrite wiped a zone) fixed.
- [Caster-cost / Ritualist wallet](aowx-caster-cost-ritualist.md) — wallet fix patch_caster_cost_wallet_v1 (46 sites, caves 0x55815800–0x55815B8F).
- [Legendary medal abilities](aowx-legendary-abilities.md) — 4th TUnitResource owner (+0x44, pfs tag 0x20), editor Legend tab, unit-window label (.xleg).
- [Item HP/MV + Use-item stats](aowx-item-hpmv.md) — TItem +0x4A/+0x4B, ITEMS.PFS layout, set_item_hpmv.py.
- [Vortex spell mechanics](aowx-vortex-spell.md) — TVortexTE rework (all non-flyers), movement-type bit table.
- [Frost terrain spells](aowx-frost-terrain.md) — Ice Storm lava→wasteland, Freeze Water→Freeze Terrain, spell rename machinery.
- [AI hero level-up chooser (410)](aowx-ai-hero-levelup.md) — ExecuteUpgradeHeroAI caves + weight table; Marksmanship-needs-ranged gate.
- [Taskbar cursor coordinates](aowx-taskbar-coords.md) — X,Y,Z label (.xcrd); PInd-overlap trap.
- [ShowScene flood / MSight.ILB](aowx-showscene-msight.md) — release zip must ADD new files (Images\Effects\MSight.ILB, Images\Items\I_x2026.ilb) by hand (`build_release_zip.py --add`).
- [Bag-ability combat crash](aowx-bag-ability-crash.md) — 406 bug fixed 9/9; token-event offsets; diag_veh_logger.py.
- [ILB icon generator](ilb-icon-generator.md) — 9/21: I_x2026.ilb REBUILT from the user's art (210 icons, build_ilb_items_x2026_v2.py, chroma-key pipeline); old procedural set backed up; ship via `--add` at the 410 cut.
- `changelog_1.37.410_DRAFT.txt` in project root — draft 410 changelog.

## Dual-sphere spells (laptop 2026-10-03→10-07; installed on the desktop 10/11)
- ⭐ [Dual-sphere spells project](aowx-dual-sphere-spells.md) — READ FIRST for this work: SpellTypes relocated (0x43C000/512 entries), sphere pairs 9..22 live + editor drop-down, clone pipeline; Death/Fire 350 Blood Pact (renamed from Bloodbath 10/13) / 351 Summon Hell Hound / 354 Hellfire (custom SpellIcn icons, DualDF.ILB effects, DUALDF_*.WAV, Spells.pfs records); ✅ user 10/11: hound v7 good, portal v19 very good; 🔨 v20 10/11 APPLIED untested: portal +12 px right/up, stones WAIT 50 ticks for the portal (gate cave on both NextStrike sites, driver 200 ticks), hound icon v24 = the sketch design drawn Summon-Boar-clean (solid head w/ cut-outs + mane: v21 top tongues, side tongues swept up in Fire-Halo curls + white gap; v23 alternating curls was reverted; sketch raster = v17 fn); v14 profile + v13 breath kept as fns); portal v23 (+6/+10 from v19); Bloodbath sparkles blood-red; v21 loop sound plays at the cast + swells to full at the stones (castsnd hook 0x421D91, cave 0x43C900); Bloodbath skull icon still unchecked; next: remaining Death/Fire spells (spec in `.dual sphere spells.txt` in the project root). Caves TCPCK 0x43C200–0x43CA00, AoWEPACK 0x55861200–0x55862200.
- [Dual-sphere RE notes](aowx-dual-sphere-re-notes.md) — combat-spell param block + damage masks, CreateDamageCA, High Prayer/Bloodlust ids, upkeep = spell+0x1C, city enchantment types, corpses/TCCorpseHS, DestroyObject hook VMT+0xF4, unit stat cache +0x44..47 refreshed only by TUnit.Changed.
- [Transfer home 2026-10-11](transfer-home-2026-10-11.md) — package contents + how it was installed (delta over root, scripts de-baked, memory hand-merged); ⚠ release zip must ADD DualDF.ILB + Sfx\Zsp\DUALDF_*.WAV by hand.
- ✅ AoO "Add Group Bonuses" soft-lock (laptop 10/4): build_ai_aoo_awareness.py read [obj+0x84]/[obj+0x88] as fields (they are VMT slots) → layered fix patch_aoo_hits_vcall_v1.py (TCPCK SUB 0x43C200); AoO frailty term was garbage before, so AoO behaviour may change — retest AI battles. Details in [410 pending tests](aowx-410-pending-tests.md).
- ✅ High Prayer blue sparkle (patch_highprayer_glow_v1.py, 1 byte AoWEPACK @0x557BB7BE).
- `changelog_1.37.410_DRAFT.txt` still lacks the dual-sphere / High Prayer glow / AoO entries.

## Active Work
- 🔨 [MP host hand-over + OoS dialog](mp-host-migration-oos-handler.md) — ✅ 11/16 host-leave crash = IPXWrapper dpwsockx.dll missing DeletePlayer callback, patched + USER-CONFIRMED (ship dpwsockx.dll); ✅ 11/18 in-place OoS reload rig v2.17 USER-CONFIRMED in tactical combat (trigger-file test rig, NOT wired to a real OoS yet; revert rig before release); lock-ups shelved; tools net_trace.py + mp_lock_probe.py; ✅ combat sword marker + combat-autosave fix confirmed 11/16
- 🔨 [29 levels: 11/16 additions](map-levels-29-plan.md) — Angel Wings level flight, transport-death validation ('Units Fell'), passengers keep MP; APPLIED untested; ⚠ spare BSS/DATA slots are crowded
- 🔍 [Leader fogged in Depths (MP report)](leader-fog-depths-report.md) — 11/14 not reproducible; suspect LOS turn-start fog rebuild; need a save
- 🔥 [Recall/Animate RDTSC roll](recall-animate-rdtsc.md) — 11/14 MP desync source fixed (→ @RandInt) APPLIED untested; full scan: no other rdtsc / time-based rolls exist
- 🔨 [Error Log + OoS recorder](error-log-oos.md) — 11/14 AoWxLog.dll (VEH errors + synced-Random ring dump on OoS) + AoWEPACK entry loader APPLIED; editor-verified only; ship --add AoWxLog.dll
- 🔨 [Independent hero spells](indep-hero-spells.md) — ✅ 11/14 USER-CONFIRMED (auto + tactical): owner 0 = Independents player grant + owner -1 stand-in + TCAI gates/loops + CheckUnit old-table read fixed → tactical AI can use AoWx spells
- 🔨 Editor mouse hotkeys 11/14 (level/grid F5/fog/brush size, AoWxShot) — see [devx-user-sort-wheel.md](devx-user-sort-wheel.md)
- 🔨 [Title logo outline](title-logo-halo.md) — 11/14 soft black halo (title.ilb image 3 composite) APPLIED, not seen in game; ⚠ never launch the game / grab the screen unasked
- 🔨 [Underground palette tabs](ug-palette-tabs.md) — 11/14 UG Grass/Steppe/Desert/Snow/Wasteland tabs (hss EditID moves + DFM grid clones) APPLIED, live-verified by me; ship AoWDevX.exe + Release.hss together
- 🔨 [Sky field class guard](sky-field-class-guard.md) — 11/14 unit on a Sky hex crashed editor (sky code read any field object as hexagon) → patch_sky_field_class_guard_v1 USER-CONFIRMED (no crash) 11/14
- 🔨 [City battle map / touching cities](city-tcmap-adjacent-cities.md) — 11/13 combat-start AV (TCMaps file missing for touching cities) → patch_city_tcmap_same_city_v1 USER-CONFIRMED 11/14; VEH logger --pid attach
- ⚠ [Raise flagged issues immediately](feedback-raise-flagged-issues.md) — never park a known leftover that contradicts the user's instruction (UG Ziggurat defender list incident 11/07)
- 🔨 [Combat autosaves + updater UX](combat-autosave-updater-ux.md) — 11/04 alternating 'autosave - combat(2)' APPLIED untested (MP!); updater facts/minimize/editor-open notice built; ship Unitres.pfs (Hydra SFX)
- 🔨 [Underground dirt roads](ug-dirt-roads.md) — 11/04 Zig road record (terrain 0x0C) appended to Release.hss APPLIED untested; combat road for 0x0C already exists; construct-ability UG roads patch applied
- 🔨 [Teleporter ice/lava/floating variants](teleport-terrain-variants.md) — 11/07 v4 (180f smooth spin, recoloured-ground portraits) APPLIED untested; STR_TELX.ILB --add
- 🔨 [Water/ice twin fade](water-twin-fade.md) — 11/13 v3+v3b (shore gate 0xA0→0x80) verified live in editor by me, user unconfirmed; brushes place ANIMATED class; also minimap sky textures (AoWTools.dll + ScanTile.ilb, see devx-screenshot.md)
- 🔨 [Sky shows level below](sky-below-levels.md) — 11/13 v1 USER-CONFIRMED; v2 adds screenshot entries (cave 0x558E1900 'SKB2'); revert before overlay rebuilds; also 11/13: UG cloud variants (cloud-variants.md), sky in map screenshots (devx-screenshot.md)
- 🔨 [Sky/Chasm transitions](sky-chasm-transitions.md) — 11/07 v2.9b APPLIED untested: per-edge water fog wedges (cave 0x558E15C0, Waterhex 0x100-0x21F), ice thickness, one-sided fades under cliffs, skyfog gates; ship HEXTRANS/Waterhex/IceHex
- 🔨 [Editor map screenshot](devx-screenshot.md) — 11/07 camera button → AoWxShot.dll (pure asm PE): minimap/map PNG, all levels, frame; APPLIED untested; ship DLL
- 🔨 [Missing resources button](devx-missing-resources.md) — 11/07 red X after Validate → AoWxShot list of objects dropped at map load (Enginep reader hooks in memory), right-click centres; APPLIED untested
- 🎨 [Cyclops unit gfx](cyclops-unit-gfx.md) — 11/07 v5 from-scratch render: CYCLOPS.ILB + corpses DeadUnit 325/326 + portrait Add_UNITS 48 INSTALLED; unit record (slot/stats) next
- 🔨 [Editor U-sort + map-only wheel](devx-user-sort-wheel.md) — 11/07 Heroes/Items 'U' sort (AoWEPACK mode 2, cave 0x558E1700-0x558E1880) + WH_MOUSE wheel filter in AoWxShot; APPLIED untested
- 🔨 [Ziggurat map compat](zig-map-compat.md) — 11/07 Highpass: UG Ziggurat RID alias v2 + enchantment nil guard (real grey-view cause, VEH-logged); APPLIED, 0 exceptions on open
- 🔨 [Summon dispel resistance](summon-dispel-resistance.md) — 11/07 v2 level×2 + medals (cave 0x558E1400), APPLIED untested
- 🔨 [Teleporter level names / Groll dest](teleport-padless-fix.md) — 11/04 Groll dest Z wrong level (not a bug); editor level drop-down + status name v1.1 APPLIED awaiting test; status panel 80 px
- 🔥 [comb_res lost records](comb-res-lost-records.md) — 11/02 water battles grass+flashing = engine re-save dropped water hex/node structure/Sky hex (cell-sharing clones); repaired again 11/04 + clones given own cells (fix_comb_res_cells_v1) — verify after next editor save; 430 zip broken → re-cut
- 🔨 [Cloud variants](cloud-variants.md) — 10/30 Sandstorm/Snowstorm/Holy/Death Cloud: Release.hss records (Objects row 3) + ILBs + AoWEPACK caves; APPLIED untested; HSS append + palette EditID/EditIndex RE.
- 🔨 [Scroll items + item enchantments](scroll-items-and-item-enchantments.md) — 10/30 scrolls grant up to 7 spells to the holder's spell book (desc lines, editor 7 pickers, no Use); enchantment abilities on items fixed; APPLIED untested; AI not scroll-aware.
- 🔨 [Great Eagle's Nest](eagle-nest-gfx.md) — 10/31 v11 APPLIED untested: crops only inside ring (structure-image field), crag polish, short flagpole (Flags.ilb 96), CanMoveOn mountain rule, guild art fix; --add PRO_EAGL.ILB + Nest0000.hsm
- 🔨 [Sanctuary razeable](sanctuary-raze.md) — in-game raze works; 11/01 editor Razed-checkbox crash (ESI not loaded in OK branch) fixed as edit v2.1 USER-CONFIRMED, shipped in 1.37.429
- 🔨 [29 map levels + Sky/Chasm plan](map-levels-29-plan.md) — 11/01 city-entry AV fixed (patch_sky_fld_guard_v1, untested); 10/31 levels, overlay, Ziggurat/altars, fly ALL USER-CONFIRMED; sky polish v7 APPLIED (v6 editor OK per user; v7 = subtler Chasm lightning + far webs + cloud flash glow, untested); next Sanctuary razeable
- 🔨 [Editor brush/repair/water teleporter](editor-brush-repair-telewater.md) — 10/31 massive brush v2 (13-hex preview, .xbr section, MBR2) + animated water teleporter v3 APPLIED untested
- 🔨 [Item name/cost limits](item-name-cost-limits.md) — 10/31 editor item gold max 9999, name 64 w/ red past 20 (patch_devx_item_name_cost_v1, .xthm 0x4E4240); APPLIED untested.
- 🔨 [Sign wheel + text limits](sign-text-hero-name-limits.md) — 10/30 non-capturing memos (signs) wheel-scroll; editor sign unlimited, hero name/title 64 w/ red past 15; APPLIED untested.
- 🔨 [Ranged ability popup stats](ranged-ability-popup-stats.md) — 10/30 right-click popup shows base ATK/DMG (UnitIcons art) + damage types for ranged abilities; APPLIED untested.
- 🔨 [Realm Heroes tab columns](realm-heroes-tab-columns.md) — 10/22 exe cols applied; turnmet v1 tag 0x60 COLLIDED with ability records (0x32+id) → reverted; v2 tag 0x10060 validated offline, not applied. ⚠ stream-tag lesson inside.
- 🔨 [Leader's Soul (possess → leader)](possess-leader-transfer.md) — v6 live; v7 (leader's own Incarnate inherits the soul, overworld no-GameOver) built, awaiting apply; Bug 2 AV needs VEH repro.
- 🔨 [Soul portrait in Events tab](dead-leader-portrait.md) — 10/22 patch_exe_soul_portrait_v1 (AoWx.exe .xtut 0x648E00) header shows the 0xCE soul unit's face while the leader is dead; built, NOT applied.
- 🔨 [Lobby dropdowns stay open](lobby-dropdown-stay-open.md) — 10/22 patch_combo_stay_open_v1.py BUILT (aowInt VMT slot 0x59811FFC → cave 0x59823E90, zone to 0x59824000), NOT applied; next free aowInt cave 0x59824000.
- ✅ [MP reload remembers races](mp-reload-remember-races.md) — 10/22 v5 USER-CONFIRMED (stores race id in TPlayer+0xDC tag 0x10061; re-claims late joiners).
- 🔍 [Phoenix corpse gfx](phoenix-corpse-gfx.md) — 10/22 build_phoenix_corpse_v1.py WRITTEN, NOT applied (DeadUnit.ILB +ids 323/324 recoloured to the Phoenix base-sprite ramp, rec 271 corpse ids swapped, 8 B); run after build_phoenix_unit_v1.
- ✅ 1.37.433 LIVE 11/14 (signed, deployed, verified). See [aowx-release-process.md](aowx-release-process.md).
- 🔍 [Leadership-retreat OOS](oos-421-leadership-retreat.md) — 10/21 static RE: vanilla flee keeps the aura on all machines (observer view = synced); no local recompute path found; next = leadership_probe on owner vs observer.
- 🔥 [420 LAN OOS](oos-420-superstack-getbusy.md) — 10/21 OOS at turn start in clean 420; suspect superstack→MoveArmyXYL→GetBusy reads in-progress combat; user: NO reverts, fix forward. ✅ 1.37.421 RELEASED 10/21 (patch_mp_hotfix_421_v1); MP-untested.
- ✅ [Discord /map bot](discord-map-randomizer-bot.md) — 10/22 LIVE: /map Worker aowx-map-bot + online keeper aowx-bot-presence (Durable Object gateway, wrangler in gateway/); update /map = build_worker.py + repaste.
- 🔨 [Discord Rich Presence](presence-game-state-re.md) — 10/22 AoWxPresence.exe built (patch scripts/presence/), started via updater --game-start, exe Mode-Off gate NOP applied; awaiting Discord app id + live test; ship it at next cut.
- ⚠️ Icon override trap: `art import export/<icon key>.png` silently REPLACES a dual-sphere glyph (suffocate.png bit 6 rounds) — check "imported" lines + render the live ILB. See [[airdeath-spells]].
- 🔨 [Earth spells 216-219](earth-single-spells.md) — 10/17 round 2 ALL APPLIED untested: Mend Walls v2 glow, Depths v2, Steadfast v2 shields, Tectonic v2 terrain + cast-only shake, Oil sfx v3; LIFO notes inside.
- 🔨 [Mend Walls 216](mendwalls-spell.md) — 10/17 Earth L1 wall repair (Ooze clone, 19 hexes) APPLIED untested; spec was truncated.
- 🔨 [Air spells 212-215](air-single-spells.md) — Gust / Crosswind (0xC2) / Suspend / Static Shield; 10/24 Crosswind MP OOS = pointer-seeded visual LCG → step length differs; seed fix built.
- 🔨 [Undying + Call of the Dead](undying-callofdead-spells.md) — 10/16 Death 210 Undying (0xC1) + 211 Call of the Dead (Draugr 201) APPLIED untested; Harvest Souls → T3.
- 🔨 [Sanctify + Miracle](sanctify-miracle-spells.md) — 10/16 Life 208 Sanctify (zone, 0xC0) + 209 Miracle (corpse raise) APPLIED untested; ⚠ never apply patch_lifeair_v1 while Sanctify is on.
- 🔨 [Life/Air spells](lifeair-spells.md) — 10/16 308 Heavenly Chorus / 309 Inspiration (0xBC) / 310 Second Wind / 311 Angel Wings (0xBD) APPLIED untested; round 8: Inspiration horn sfx v8 + icon v5, Second Wind retarget block (patch_tc_secondwind_target_v1).
- 🔨 [Air/Death spells](airdeath-spells.md) — 10/15 344 Banshee Gale / 345 Suffocate / 346 Borrow Time (0xBB) / 347 Succubus (unit 229) APPLIED untested.
- 🔨 [Water/Air spells](waterair-spells.md) — 10/15 396 Misty Step (Void Step teleport) / 397 Flashfreeze / 398 Nimue's Favour / 399 Ice Age APPLIED untested; v2 (icons, Flashfreeze ring, Ice Age thaw+glow) applied 10/15.
- 🔨 [Water/Death spells](waterdeath-spells.md) — 10/15 ids 340-343 (not pair formula): Soul Siphon (caster heal) / Plague (spreading, Death Mastery shared) / Black Tide (Earth Mastery shared) / Hydra 264 APPLIED untested.
- 🔨 [Life/Water spells](lifewater-spells.md) — 10/15 324 Holy Water (breath+Turn) / 325 Bountiful Harvest / 326 Blessed Dew / 327 World Healer APPLIED untested; all 6 Masteries now used as donors.
- 🔨 [Earth/Water spells](earthwater-spells.md) — 11/16 Slowed = ×2 move cost via CreateMovePointTable (APPLIED untested); 10/15 380 Slow (0xB9) / 381 Crocodile (unit 283) / 382 Swampwalk (0xBA) / 383 Overgrowth (forest growth) APPLIED untested.
- 🔨 [Earth/Air spells](earthair-spells.md) — 10/14 364 Mammoth / 365 Hurl Boulder (1-strike hail) / 366 Gravity Well (+Grounded 0xB8, rec 194) APPLIED untested; DualDF next free 1766.
- 🔨 [Earth/Life spells](earthlife-spells.md) — 10/14 300 Awaken Spirit / 301 Blessing of the Forest / 302 Golden Age / 303 Summon Ent APPLIED untested; ⭐ pipeline zone moved to 0x55852000 (8 KB).
- 🔨 [Earth/Death spells](earthdeath-spells.md) — 10/14 332 Dire Wolf / 334 Werewolf summons, 333 Rot Away + 335 Thousand Threads (7-strike hail AoE, Rot 0xB5, web) APPLIED untested; ⚠ pipeline zone nearly full.
- 🔨 [Fire/Water spells](firewater-spells.md) — 10/14 404 Blood Boil / 405 Scald (Vaporize clones) / 406 Steam Power (Fire Mastery clone) APPLIED untested; caves + art ids inside.
- 🔨 [Fire/Air spells](fireair-spells.md) — 10/14 388 Sandstorm / 389 Implosion / 390 Frenzied / 391 Drought; round 8 APPLIED untested; ⭐ WER LocalDumps + minidump solved the preview-cave crash; next free TCPCK 0x43E700.
- 🔨 [Earth/Fire spells](earthfire-spells.md) — 10/13 round 3 APPLIED awaiting test: 372 Oil Spring WORKS 10/14 (Ooze clone, 7 oil hexes + Fire Weakness 0xB2; v3.2 = full VMT clone 0x110 + hail-target + 2nd sound cue + range 0x0C; gush driver chained in front of Ashes → Ashes dry-run asserts while applied) / 373 Lionheart (ability 0xB1, icon v3, roar sfx v2) / 374 Forge Blast v3 (20-step quake → Fireball explosion) / 375 Arms Race (+ city text line + city glow incl. Fountain of Life, patch_city_enchant_ui_v1); next free AoWEPACK 0x55863800, TCPCK 0x43DD00.
- 🔨 [Life/Fire spells](lifefire-spells.md) — 10/13: 360 Martyr / 361 Cleansing Flame (TRemedy clones, ability 0xB0) / 362 Summon Phoenix (unit 271, ANIMATED GLOW layer ✅ + Ilpack.dpl glow-sync patch) / 363 Holy Starfire; 353 Ashes to Ashes (Death/Fire L3, class 7 direct, corpse queue + chained strike gate TCPCK 0x43CF00; ⭐ silent-close crash = ILB blendValue 120 > 100, see round 27; Windows event log beats the VEH logger for silent closes); editor ListSpells fix ✅; ⚠ ship Ilpack.dpl + USHADOW.ILB; next free AoWEPACK 0x55862C00.
- 🔨 [Repent + Harvest Souls combat spells](repent-harvest-souls-spells.md) — 10/12 v3 APPLIED awaiting test: 206 Repent (Life T2, holy sparkles → static UFO beam via a kind-0x26 driver, alignment/medal DMG) + 207 Harvest Souls (Death T2, corpses → +5 casting points, purple Animate-Dead twinkles); next free AoWEPACK 0x55862700 / TCPCK 0x43CF00.
- 🔨 [Rejuvenate + Wither terrain spells](terrain-spells-rejuvenate-wither.md) — 10/12 APPLIED awaiting test: ids 204/205 as TRejuvenate clones (dual-sphere pipeline) + per-spell terrain caves (patch_terrain_spells_v1.py, AoWEPACK 0x55862400); Scorch Terrain (= vanilla Rejuvenate 0x29) RE inside; icons 204/205 added to SpellIcn.ILB.
- 🔨 [Power-slider tilt fine step](aowint-cave-map.md) — 10/12 APPLIED awaiting test: `patch_power_slider_tilt_v1.py` (aowInt cave 0x59823E00): wheel tilts (= VK_LEFT/RIGHT via the chord engine) nudge the mana/research slider by 1 while the Power Distribution window is open (g_pslider latch from build_wheel_power_slider.py); right = +1 toward research; hook = TAOWWinManager key dispatch prologue 0x598072FC. ⚠ v1 clobbered ECX (= shift state) on every pass-through key → cheat entry broke; v2 10/12 compares the VK in memory (lesson: the dispatch entry regs eax=mgr, edx=&VK, cl=shift must all survive the pass path).
- 🔨 [Spell-book tilt paging + Load dialog date sort](spellbook-tilt-pages-loaddlg-datesort.md) — 10/11: tilt paging USER-CONFIRMED (orientation swapped on request: left = next); Load dialog date sort v3 (10/12) = DateBtnClick from FindFiles' epilogue gated on mode **0** (probed live: Load = 0, not 1) awaiting test; ⚠ sort direction unverified. TSpellBook/TFileDlgWindow field+method tables inside.
- 🔨 [MP editor-open indicator](mp-editor-open-indicator.md) — 9/21 v2 APPLIED awaiting test: AOWED/AOWEDASG mapping poll (TBWorldUpdate hook) → hidden chat broadcast → per-player flickering green lamp above the race icon (23-px PInd, transparent top) (.xedt section, TBWin.ILB +5 imgs) + .asg chat line; AoWDevX multi-instance (.xprn cave). ⚠ re-run after cursor-coords / prune-v2 rebuilds.
- 🔨 [level-terrain-rocks.md](level-terrain-rocks.md) — 9/21 APPLIED untested: Level Terrain leaves terrain-matched rocks on flattened hexes; TTerrainMO/PlaceTerrain/ClearTerrain RE + Release.hss decoration catalogue; next free AoWEPACK cave 0x55816F00.
- 🔨 [Event tab hover no-jump](eventlog-hover-nojump.md) — 9/21 APPLIED awaiting test: event list stops auto-scrolling while hovered (uses aowInt g_hover 0x5983E100); .xbfs next free 0x60EC40.
- 🔨 [Caster abilities I/II/III](caster-multilevel-abilities.md) — 9/21 APPLIED awaiting test: Evoker/Conjurer/Enchanter/Ritualist multilevel (research −30 % STACKING per leader/hero, cast/upkeep per caster), 4 scripts incl. spellbook display (exe→AoWEPACK via import-slot delta); next free AoWEPACK cave 0x55816B00, .xbfs 0x60EC00.
- 🛑 [Poison plants wasteland art](poison-plants-wasteland-gfx.md) — 9/21 hss edit BROKE LAUNCH → reverted; user does it in the editor (GND_POIS.ILB img 11 = withered plant, terrain slot 5); TILTerrainMO terrain→sequence + TImageSequenceList stream format RE.
- 🔨 [Customize-name → registry](customize-name-registry.md) — 9/21 APPLIED awaiting test: MP leader-customization name saved as player name (v2: also refreshes the pre-lobby edits since TMainForm.FormDestroy re-saves them; .xbfs 0x60EB00, next free 0x60EB80); player-name plumbing RE.
- 🔨 [Group move re-path](aowx-group-move-repath.md) — 9/21: repath v3 + passthrough v2 + **origin-cost v1 (vanilla 0-cost origin hex bug, cost-grid diagnosis via grid_probe.py)** + strategic multi-party partial-move fix (AoWEPACK 1 byte, patch_strat_group_move_partial_v1); next free TCPCK cave 0x43AB40.
- 🔨 [AI hero idle / self-heal drop](aowx-ai-hero-idle.md) — 9/20 fixes APPLIED untested: selfheal-exec, hero gate, AoO type-3/5 swap fix, walk margin, 12 units/frame; ⚠ patch_ai_ranged_trace_v1.py is DIAGNOSTIC — revert before release; open: hero Doom Gaze never proposed.
- 🔨 [AI ram focus after breach](aowx-ai-ram-focus.md) — 9/20 APPLIED awaiting test (patch_ai_ram_focus_v1.py, TCPCK cave 0x43A100, next free 0x43A200): ram value = avg DV over ALL opposing objects incl. walls, frozen at SetupTargets; breach flag [data+0x4D] set by TCombatWall.DestroyObject; design = hook 0x413673 in tcDVtoDEV, devalue harmless crushers (no unit-DV entries) after breach.
- ✅ [mp-leader-kill-freeze.md](mp-leader-kill-freeze.md) — 9/3 defeat-freeze FIXED (user-confirmed): vanilla RemoveEnchantments livelock over an orphaned unit enchantment (our summoned-ability patch wrote unit id 0); guard + heal shipped in 1.37.409, summonuid heal awaiting test; ⭐ game-over chain + enchantment registry RE, hangprof.py EIP sampler.
- ✅ [mp-reload-customize-hang.md](mp-reload-customize-hang.md) — MP save-resume 'Waiting for other players' forever = vanilla hValidateSetupMap bug exposed by mpdefaults; fix USER-CONFIRMED 9/3, shipped in 1.37.408; ⭐ full TSetupControl lobby/resume handshake RE.
- 🔨 [campaign-set-switch.md](campaign-set-switch.md) — game half USER-CONFIRMED 8/31 (v4 named value General\"Vanilla Campaigns\"); AoWSetup dropdown + TEXT.PFS join-text swap applied 8/31 awaiting test; v7.1 self-ensuring site stubs fixed the AoWDevX 216 crash. Full v1–v7 lesson list inside the file.
- 🔨 [unitwindow-party-arrows.md](unitwindow-party-arrows.md) — 8/31 APPLIED awaiting test: unit-window prev/next party arrows now appear in EVERY entry path (events portrait, item pickup), driven by the unit's own TArmy (`[unit+4]`) instead of the map-selected army in TGeneral; v2 8/31 removed a wrong ownership gate that broke enemy/independent stacks. Holds the TUnitWindow/TGeneral field map + ⚠ keystone-hangs-on-comments and AoWx.exe-does-have-.reloc corrections.
- 🔨 [tunnel-cave-structures.md](tunnel-cave-structures.md) — 8/31 first attempt REVERTED (no visible effect); root cause since found: the palette icon is the resource's terrain-0 image and **water is terrain 0**, so the surface tunnel record leads with WHIRLPOOL art while the underground twin leads with STR_CAVE. Fix needs either an .hss record-length edit or the editor's icon path. Holds TCave RE + the Release.hss image-ref record format.
- ✅ [caster-cost-abilities.md](caster-cost-abilities.md) — **user-confirmed 8/31**: Evoker/Conjurer/Enchanter/Ritualist (0xAC-0xAF, −⅓ cast cost; Ritualist = ALL globals) + vanilla instant-cast wallet fix; Ability.pfs records 182-185 (cost 15). Caves 0x55814F00-0x55815100. Holds the Ability.pfs writer recipe.
- 🔨 hpbar+memo clamps (BXL vanilla-bug fixes, 8/31 applied awaiting test; scripts build_hpbar_clamp.py/.bak_hpbarclamp + build_memo_clamp.py/.bak_memoclamp): negative-HP bar "Blt Error" (HitPointsToHitPcnt tail 0x5575A824 → cave 0x55815100-0x55815120) + TAOWMemo.SetListOff lower clamp in-place @0x598192AB aowInt.dpl (covers empty-memo −1; complements our 402 wheel-side clamp).
- 🔨 [ai-explores-sites.md](ai-explores-sites.md) — AI paths to + auto-searches sites, MP-safe via the human search TE. v1 confirmed 8/31; **v2 strength-aware** (ladder 15/30/45/75/100 by group-vs-roster ratio, undef=100; mint gate army≥⅔ roster) applied 8/31 awaiting test. Holds TStructureAIPA/ExecuteAI(+0x1C0)/UpdateAITarget(+0x1C4)/CanSearch/strength RE.
- 🔨 [ai-item-loot.md](ai-item-loot.md) — BXL port evolved: heroes fill/UPGRADE-SWAP equip slots + stash use items by value (5a/10d/10dm/5r + ability ExpandCosts); items group-aware AI targets 10-75. v2.5 8/31 after 3 AV rounds (TItem = bitset owner!). Awaiting clean-run test.
- 🔨 [elemental-feeding.md](elemental-feeding.md) — fire heals fire units (+N popup) ✓, terrain walk +1/hex ✓, tactical +1/hex ✓, autocombat 1-2/round via recorded THealingCA (replay-visible, confirmed) ✓; nodes heal+bless (razed gate); waterlava block; transportgate. Death-stays-dead + priest-heal sanity tests pending.
- 🔨 [los-terrain-lavadirt.md](los-terrain-lavadirt.md) — 8/30 confirmed: Earth/Rock block strategic LOS + fog rebuild; ⭐ raise-terrain matrix (UG casting unlocked — [spell+0x39] flag @0x557A357C; temp terrain via TFrozenWaterHS ext).
- 🔨 [modding-tools-separation.md](modding-tools-separation.md) — tools ship separately (zip+installer in upload/); hub greys missing tools; 407 cut recipe verified NOT applied.
- 📦 [keeper2-armycombatmovete-crash.md](keeper2-armycombatmovete-crash.md) — crash-hunt hub; 404 released 8/13, 405 cut 8/15. Root causes fixed (+0x4C owner family, relocs-under-NOPs). ⚠ revert build_getchild_caller_probe.py (HSEPack SHIPS) before any cut. ⚠ don't ship 402.
- 🛠 [te-exception-dialog-diagnostic.md](te-exception-dialog-diagnostic.md) — **Network.dpl patch REVERTED for the 407 cut (9/1) — re-apply build_te_exception_detail.py when diagnosing, revert again before any cut.** Names TE exception module+offset; assert inventory.
- ✅ [borderless-fullscreen-feature.md](borderless-fullscreen-feature.md) — "Fullscreen (Optimized)" confirmed 8/11; holds new-PE-section + private-import recipe (.xbfs).
- ✅ [scenario-hp-topup.md](scenario-hp-topup.md) — map-placed units start at max HP (confirmed 8/11).
- 🛑 [multilevel-ability-heal.md](multilevel-ability-heal.md) — REMOVED 8/12, corrupted memory; never rerun. ⚠ SHIPPED in 402.
- 🔨 [summon-silver-dragon-spell.md](summon-silver-dragon-spell.md) — Summon Silver Dragon (0xCB) applied 8/10; SPELLICN.ILB record-append recipe.
- ✅ [warp-self-combat-spell.md](warp-self-combat-spell.md) — "Void Step" (0xCA) complete. Open: targeting cursor, LAN OOS test.
- ✅ [mouse-wheel-scrolling.md](mouse-wheel-scrolling.md) — wheel scrolling complete. ⚠ VCL30↔aowInt signature-coupled; laptop era evolved it — see [[aowint-cave-map]]. Editor context-aware attempt 8/31 FAILED and was fully reverted.
- ✅ [summon-mermaid-spell.md](summon-mermaid-spell.md) — Summon Mermaid (0xC9) + 3 engine fixes every custom spell needs.
- ✅ [magic-sight-spell-re.md](magic-sight-spell-re.md) — Magic Sight (0xC8) + .pfs/ILB/icon/dense-registry RE.
- [mapgen-build-and-state.md](mapgen-build-and-state.md) — AoWxGen (source `patch scripts/mapgen/`), v6.4; rebuild/deploy how-to.
- [ghidra-mcp-setup.md](ghidra-mcp-setup.md) — Ghidra MCP bridge (JDK 21); mostly superseded by dasm.py/xref.py.
- ✅ [release-zip-save-folder.md](release-zip-save-folder.md) — zips 401-405 lacked X/Save/ → first-save EFCreateError; fixed for 406+.
- ✅ [spellcast-manares.md](spellcast-manares.md) — hero mana = (SC level)×1.5×RES = (lvl*RES*3)>>1 @0x557885EC (×2 confirmed 8/30; ×1.5 retune 9/1 untested).

## Reference & Tooling
- 🔨 [Map item-list injection](map-item-list-injection.md) — 9/23 x2026 library (164 items) appended to the 50 "AoWx - " maps carrying xNew (add_library_items_to_maps.py, backups .bak_x2026items) awaiting editor check; ⭐ .hsm root tag 0x1E item list, key 9 = last item id, editor import rules, parser zero-length-entry gotcha; ⚠ ship the 50 maps in 410.
- 🔨 [Ooze extinguish](ooze-extinguish-idea.md) — 9/23 APPLIED awaiting test (patch_ooze_extinguish_v1.py, TCPCK hook 0x40C922 → cave 0x43AC40–0x43ACE9, next free 0x43AD00): each of the 19 Ooze hexes frees its TCombatFire (walls too) and strips Burning from the unit there; ⭐ Ooze = 19 TfxHS strikes, per-hex spell dispatch in TCAbRangedTE.Execute, TMapField.FindOwnedChild(ClassID) = field VMT+0x80.
- 🔨 [Town Quake](town-quake-spell.md) — 9/21 retune APPLIED untested (wood 80/stone 50, UG +10, UG ATK 9 vs non-stone; caves 0x55816F00–0x55816F80, next free 0x55816F80) + full RE/expected-damage table.
- ✅ [AoW.exe launcher](aow-exe-launcher.md) — AoW.exe = compiled AHK shim; 9/21 patched to just run AoWx.exe (Slickness helper retired); ⚠ `start AoW.exe` resolves to the vanilla install — use full paths.
- [MP chat button flash](mp-chat-button-flash.md) — 9/21 RE: chat msg → taskbar counter 0x88, ChatBtnUpdate flashes 5× then stops; no unread state; hook points listed.
- [Breath attacks (tactical)](aowx-breath-attacks.md) — 9/21 RE: 12 strikes, fan-angle obstruction lines ≠ damage hex, full-depth lines → corridors block breaths; **patch_breath_line_v1 APPLIED 9/21 awaiting test** (cave 0x43AB40; next free TCPCK 0x43AC20).
- ⚠️ [full-file-backup-revert-gotcha.md](full-file-backup-revert-gotcha.md) — NEVER `--revert` an older patch on a multiply-patched binary (whole-file backup wipes later patches; bit the 410 cut); un-hook in place + audit zipped binaries with dry runs.
- ⚠️ [rebase-crash-runtime-error-216.md](rebase-crash-runtime-error-216.md) — **READ FIRST on startup/intermittent crashes.** AoWEPACK rebases; PIC playbook. Also: ability-reg caves must pass ecx=0 to the ctor (10/15 Slow, see earthwater-spells).
- [patching-over-relocs-gotcha.md](patching-over-relocs-gotcha.md) — scan .reloc; neutralize 3→0 on apply, restore on revert; July-era violations were the "crashes on his machine" mechanism.
- [active-patches.md](active-patches.md) — applied-patch table + reverts (⚠ predates 2026-08 work).
- [aowx-re-reference.md](aowx-re-reference.md) — core RE: Delphi conventions, ability IDs, StrikeEnhancement, HasAbility.
- [ability-id-map.md](ability-id-map.md) — ability name→id map + derivation methods. Hero Slaying = 0x38; 0x81 Animated / 0x83 Decay (8/31).
- [bxl-reference.md](bxl-reference.md) — BXL July drop: catalog, **his cave VAs overlap ours — never run as-is**, MP RNG rules.
- ⭐ [ziggurat-scrolls-dump.md](ziggurat-scrolls-dump.md) — BXL 8/28 archive review: our follow-up flags, adoption candidates, Ghidra catalogues.
- [pfs-unitres-format.md](pfs-unitres-format.md) — Release/*.pfs parsed. ⚠ unit-list index ≠ unit id.
- [hsm-map-format.md](hsm-map-format.md) — .hsm container cracked (CFS+zlib, HSS tree).
- [baked-absolute-paths-gotcha.md](baked-absolute-paths-gotcha.md) — derive paths at runtime; home tooling: `py -3.10`, AOW_GAME_DIR.
- [aowepack-dll-is-live.md](aowepack-dll-is-live.md) — exe imports the .dll; **never patch AoWEPACK.dpl**.
- [no-cd-check-location.md](no-cd-check-location.md) — no-CD = AoWReg @file 0x5776; reference 1.36 dpl patched 8/30.
- [intro-video-codec-fix.md](intro-video-codec-fix.md) — Intro.avi Indeo→Cinepak re-encode.
- [lan-desync-investigation.md](lan-desync-investigation.md) — LAN OOS solved (FIX #8 movedraw); ⭐ two-RNG model (synced [map+0x230] vs bare RandSeed; combat rolls must match in COUNT); Mind Decay audit + build_minddecay_oos.py (8/31, MP-untested); noanim FULLY REVERTED 8/31 — ⚠ LAN moles-repro + state test REQUIRED; fallback build_desync_fix_noanim2.py.
- [custom-music-wav2it.md](custom-music-wav2it.md) — wav2it.py recipe; 11 live tracks + AoWxBard.exe.
- [project-state-2026-07.md](project-state-2026-07.md) — 401 released 7/27; AoWxGen history.
- [transfer-back-home-2026-08-09.md](transfer-back-home-2026-08-09.md) — 8/9 transfer; laptop stale after.
- [project_state_2026_07_03.md](project_state_2026_07_03.md) — old snapshot; superseded.

## Gameplay/Engine Patches (done)
- ✅ [hero-tactical-courage.md](hero-tactical-courage.md) — hero courage + AI AoO awareness v5 (confirmed 8/15; TCPCK caves 0x438660+).
- ✅ [defender-retaliation.md](defender-retaliation.md) — v6.1 shipped 8/15; 🔨 10/22 give-up v1 LIVE (crashed on fast path, 2-attempt lag) → v2 LIVE (auto crashed: TFastCombat ≠ predictor layout) → v3 built, not applied; RE bank in file.
- ✅ [tcai-defender-hold-response.md](tcai-defender-hold-response.md) — damaged defenders engage (confirmed 8/14); corrected TCAI RE.
- [hero-ai-levelup-chooser.md](hero-ai-levelup-chooser.md) — ✅ AI hero level-up 3→30 abilities+stats; tunable heroai_build.py.
- [weakness-abilities-SHELVED.md](weakness-abilities-SHELVED.md) — ✅ DONE (stale name): 8 Weakness abilities.
- [underground-nightvision-atk-penalty.md](underground-nightvision-atk-penalty.md) — UG ATK penalties w/o Night Vision; unplaced-unit guard lesson.
- [trueseeing-vs-invisible-atk-penalty.md](trueseeing-vs-invisible-atk-penalty.md) — ATK penalty vs Invisible w/o True Seeing.
- [ai-combat-spell-once-per-combat.md](ai-combat-spell-once-per-combat.md) — ✅ AI tactical-spell spam stopped.
- [road-build-cost.md](road-build-cost.md) — ✅ road cost per-tile by decoration.
- [path-of-sand-ability.md](path-of-sand-ability.md) — "Path of Sand" (0x9F).
- [sphere-combine-opposing-elements.md](sphere-combine-opposing-elements.md) — Fire/Water & Earth/Air combinable.
- [hero-levelup-event-fixed-location.md](hero-levelup-event-fixed-location.md) — level-up log anti-tracking.
- [reflecting-pool-raze.md](reflecting-pool-raze.md) — ✅ raze+rebuild; raze framework RE.
- [spring-of-life-wasteland.md](spring-of-life-wasteland.md) — wasteland behavior. ⚠ site sound patches stay vanilla forever.
- [mp-default-race-cpu-emperor.md](mp-default-race-cpu-emperor.md) — MP default race → CPU Emperor (LAN test pending).
- [registry-isolation.md](registry-isolation.md) — own `HKCU\...\Age of Wonders X` tree (7/22, pre-401; settings migrated).
- 🔨 [aowsetup-installcheck-devtab.md](aowsetup-installcheck-devtab.md) — install-check fix + Developer tab unhidden (8/13); AoWSetup RE map inside.
- [designer-only-portrait-toggle.md](designer-only-portrait-toggle.md) — ✅ Designer-Only filter restored.
- [ingame-version-location.md](ingame-version-location.md) — version = 3 immediates in TAoWEngine.Create.

## Editor (AoWDevX)
- [editor-dialog-dir-memory.md](editor-dialog-dir-memory.md) — ✅ Open dialogs remember dir+file (INI).
- [editor-about-dialog.md](editor-about-dialog.md) — About rebranded; version runtime-assembled.
- [unitfloater-selectioncontrol-map.md](unitfloater-selectioncontrol-map.md) — floater 160-cap fixed; DFM shrink technique.
- [editor-patch-audit-2026-08-05.md](editor-patch-audit-2026-08-05.md) — patches survived transfer.
- [mapgen-no-regen-after-changes.md](mapgen-no-regen-after-changes.md) — new seeds after generator changes, never regen old names.
- [adblocker-hides-adv-classes.md](adblocker-hides-adv-classes.md) — aowx.org: no ad-like CSS class prefixes.

## Shelved / failed (RE preserved)
- [hurl-skull-SHELVED.md](hurl-skull-SHELVED.md) — hurl firing hardcoded per-id; only reskin works.
- [editor-combat-rating.md](editor-combat-rating.md) — crashed on transports; RE kept.
- [editor-sort-by-status-SHELVED.md](editor-sort-by-status-SHELVED.md) — item window sorts via ordinal-bound grids.
- [hide-goldmana-in-combat-SHELVED.md](hide-goldmana-in-combat-SHELVED.md) — groundwork only.
- [raise-terrain-underground.md](raise-terrain-underground.md) — failed/reverted (superseded by raiseterrain matrix); keeps HSS/TEObject format.
- ✅ [exploration-site-fix.md](exploration-site-fix.md) — MP site combat works (8/11); GetExplored nil-guard chain; revert via #2 not #1.
- [editor-sfx-preview.md](editor-sfx-preview.md) — SFX preview silent: nil SFX object; reverted.
- [Check game running first](feedback-check-game-running.md) — gate apply+VEH chains on tasklist=0; taskkill killed a live session 10/17.
- 🔨 [Water spells 220-223](water-single-spells.md) — 10/17 Crashing Wave / Rite of the Seas / Flash Flood ALL APPLIED untested; 222 reserved (L3).
- 🔨 [Fire spells 224-227](fire-single-spells.md) — 10/17 Smokescreen / Wall of Flames / Pyroclasm forks building; 224 reserved (L1).
- 🔨 [Cosmos spells 228-231](cosmos-single-spells.md) — 10/18 round 2 ALL APPLIED untested (MM per-bolt sfx, City Spy panel+eye, Royal v2 any race, Essence UG+owned); LIFO inside.
- 🔨 [Secret spells 232-235](secret-spells.md) — 10/18 Lucky / Mimic / Reversal / Transmutation ALL APPLIED untested; Secret = sphere 7, cloud 151.
- [Bound pipeline entry edits](feedback-pipeline-entry-bounds.md) — search only inside the target SPELLS dict entry; a fixed line window hit the next entry 10/18.
- 🔨 [Overflow army placement](overflow-army.md) — 10/18 joined units of a full 8-stack go to an adjacent hex (TCombat.Finalize pass-2 Place hook) APPLIED untested.
- 🔨 [Seeker Bolts rework](seeker-bolts.md) — 10/18 v2: shot is KIND 1 (table 0x467248) → v1 never fired; patch_tc_seekerbolts_v2 + solid gold/blue art + sfx v2 APPLIED untested.
- 🔨 [F5 hex grid option](hexgrid-thick.md) — 10/18 Display + AoWSetup dropdown Extra/Default/Vanilla (Flags.ilb #92/#93, .xhgr/.xhgd) APPLIED untested; ship Flags.ilb.
- 🔨 [Ally unit-enchant targeting](ally-enchant-targeting.md) — 10/18 click handler compared player not side; patch_tc_ally_enchant_v1 APPLIED untested; red cursor → run ally_side_probe.py.
- 🔨 [City rebuild per hex](city-rebuild-perhex.md) — 10/18 rebuild turns = city hexes (was 5); AoWEPACK cave 0x55863F80 APPLIED untested.
- 🔨 [Shockwave push](shockwave-push.md) — 10/18 Shockwave pushes survivors 1 hex (Gust machinery), TCPCK 0x450400 APPLIED untested.
- 🔨 [Tutorial confirm popup](title-tutorial-confirm.md) — 10/18 "Start Tutorial?" Yes/No, AoWx.exe .xtut APPLIED untested; ⚠ exe section table FULL.
- 🔨 [Tame Animal 0xC9 + Tamed 0xCA](tame-animal.md) — 10/19 v3 WORKS (user); TCPCK id switch was the bug; fade-out + overhead paw in progress.
- 🔨 [Site defender rows 20](site-defender-rows.md) — 10/18 editor grids MinRowCount 8→25 (game had no cap); APPLIED untested.
- 🔨 [Breath animation fix](breath-anim.md) — 10/18 vanilla fan flight restored, hits unchanged; TCPCK 0x451000 APPLIED untested.
- 📋 [TCPCK data-slack map](tcpck-data-slack-map.md) — owner map of AoWTCPCK scratch memory; 10/18 two collisions fixed (Miracle/Sandstorm, heal-log/Oil VMT).
- 🔨 [No charge popup (+ reverted live upkeep)](caster-upkeep-live.md) — 10/18 charging page only when needed APPLIED; live-upkeep REVERTED by user (caster not tracked).
- 🔨 [Build Bridge construct](build-bridge.md) — 10/18 50 g / 3 turns, hidden-tower carrier, boats pushed; AoWEPACK 0x5581B000 APPLIED untested.
- 🔨 [0 sphere picks](sphere-picks-zero.md) — 10/18 editor spinner 0/3/5/7 (AoWDevX + Vcladdon.dpl) APPLIED untested; ship Vcladdon.dpl.
- 🔨 [Evoker coverage + 33 %](caster-evoker33.md) — 10/18 combat-only unit spells → Evoker; caster discounts 33 %; AoWEPACK 0x5581E000 APPLIED untested.
- 🔨 [Channeler I/II/III 0xCB](channeler.md) — 10/18 +30/50/100 % casting points, 100/100 label smaller font; LADDER→0xCB; APPLIED untested.
- 🔨 [Battles on exploration sites](site-army-combat.md) — 10/18 site cave map for army-vs-army on a site, bags, no adjacent stacks; no site roster; APPLIED untested.
- 🔨 [AI site rules](ai-site-leader-safety.md) — 10/19 v6 set: leader head 1.75×/fight 2× with friend-wait bands + give-up cooldown; leaderless head 1×/fight 1× (1–2× waits 1 turn); APPLIED untested.
- 🔨 [Blood Pact AI spam](bloodpact-ai.md) — 10/19 autocombat recast fixed (Bloodlust-aware scorer); 300/301/390 fixed too (hpclones).
- 🔨 [AI end-turn unit enchants](ai-end-enchant.md) — 10/19 v5 APPLIED (v1–v4 used the leader's ARMY as the leader → turn-1 AI ERROR); untested.
- 🔨 [AI diplomacy extras](ai-diplomacy.md) — 10/19 tributes/sweeteners/suggestions/threats APPLIED untested.
- 🔨 [No pair spells at start](no-pair-start-spells.md) — 10/19 day-1 + campaign grants skip spheres 9–22; APPLIED.
- 🔨 [DLL host guard](airdeath-spells.md) — 10/19 editor AV fixed: DLL caves touching AoWx.exe memory now host-checked (patch_dll_host_guard_v1); ⚠ never hard-code exe addresses in DLL caves without it.
- 📋 [Custom songs size](custom-songs-size.md) — Galaxy.dll has no compressed-sample support; only installer-side lossless decode could cut download size.
- 🔨 [Title quotes + easter eggs](title-quotes-eastereggs.md) — easteregg.pfs quotes, inioch/ziggurat eggs; inioch intro v2 10/23: title music re-enters at 0:30 (order jump) APPLIED untested.
- 🔨 [Dispel Magic on nodes/altars](dispel-nodes-altars.md) — 10/19 +2×lvl node power, altar recharge −lvl; APPLIED untested.
- 🔨 [Help → AoWx Manual](help-aowx-manual.md) — 10/19 menu label + https://aowx.org/ APPLIED.
- 🔨 [BXL ranged abilities 0xCC/0xCD](bxl-ranged-abilities.md) — Hurl Skull AOE + art/sfx (10/19); 10/24 multi-hit fix; 11/16 outer ring half damage APPLIED untested.
- 🔨 [Editor spellcheck squiggles](devx-spellcheck.md) — 10/19 spell/ability description editor red underlines APPLIED untested.
- 🔨 [AI leader superstacks](ai-superstack.md) — 10/20 adjacent units merged/swapped into the leader stack at turn start (no garrison minimum); APPLIED untested.
- 📋 [BXL Ziggurat auto-updater](bxl-ziggurat-updater.md) — GitHub Releases + PowerShell scheduled task + full installer; weaknesses noted; reference for an AoWx updater.
- ✅ [AoWx auto-updater](aowx-autoupdater-plan.md) — 10/21 LIVE with 1.37.420 (signed aowx.org notice + GitHub installer); release recipe + one-click signer inside.
- 🔨 [Observe reveals concealed](observe-conceal-exploit.md) — 10/23 camera never centres on concealed enemy armies (move path 0x5583C000 + all ValidateObservation paths 0x5583C100) APPLIED untested.
- 🔥 [OOS 10/23 BSS slack collisions](oos-423-bss-slack-collisions.md) — Harvest crop buffers overwrote weakness ids (view-dependent → OOS); all overlaps moved; SHIPPED in 1.37.423 (live 10/23), MP-untested; weaknesses work again.
- 🔨 [LogbookChanged exception = combat-log refcount](combatlog-refcount-logbookchanged.md) — 10/23 v1.1 confirmed; 10/24 replacement logbook AVs in GetTextColor → GetPlayers guard (cave 0x5583C380) built; ship both at next cut.
- 🔨 [AoWSetup Audio tab](aowsetup-audio-tab.md) — 10/24 Audio tab (trackbars) + AoWSetup volume follows SFX + game saves Sound on dialog Close; APPLIED untested.
- 🔨 [Right-click closes windows](rclick-close-windows.md) — 10/24 aowInt WinManager hook, 9 dialog classes; APPLIED untested.
- 🔨 [Combat summons](combat-summons.md) — 10/24 IN PROGRESS: RE recipe for mid-combat unit creation + captured-path plan.
- 🔨 [Underground terrain variants](underground-terrain-variants.md) — 10/31 cave mouths + 21 underground structure records get surface-terrain art (slots 1..5) APPLIED untested
- ✅ [Editor autosave](devx-autosave.md) — 10/31 AoWDevX toggle button + Options > Autosave Timer, alternating autosave/autosave2 files; USER-CONFIRMED (v1.1)
- 🔨 [Teleport Z=-1 = Firmament](teleport-firmament.md) — 10/31 ReadWrite translation (file -1 ↔ level 3) + editor dialog; APPLIED untested
- 🔨 [City wall / crop ownership](city-crop-spacing.md) — 10/31 patch_city_wall_v1 APPLIED untested: cities may touch; shared crop → city>farm, larger, nearer, placed first; crop under a city = none
- 🔨 [Title background tiling](title-bg-tile.md) — 10/31 scrolling title panorama tiled across wide screens (no stale strip); APPLIED untested
- 📘 Manual builder 10/31: vanilla spell icons now rendered from SPELLICN.ILB via the icon id in each Spells.pfs record's tag-0x0C image list (SPELLICN sequence frame; NOT the spell id); SPELL_RENAME Freeze Water→Freeze Terrain; The Groll in acknowledgements.
- 📘 11/01 manual sphere icons: cosmos.png / secret.png rebuilt vanilla-style by `patch scripts/manual_build/sph_build2.py` (orb = vanilla radial profile + borrowed grain + rim dashes, recoloured; Cosmos = chunky star from user ref, Secret = brush-drawn ?); originals backupsmos.png.bak_sph / secret.png.bak_sph.
- 📘 11/01 manual: secret.png '?' v3 = classic even-width hook + square dot, crisp ragged edge, light halo + grain-toned body (sph_build2.py vanilla_glyph); Secret-sphere spell icons re-rendered with SECRET_GAIN 2.0 on the cloud (_spellicn_icons gain param; p90 58→116).
- 📘 11/01 secret.png '?' v4 = the game's serif '?' from the custom-leader portrait (cut from user's screenshot sphere_icons/qmark_ref_custom_leader.webp); refs now stored in manual_build/sphere_icons; rebuild = py sph_build2.py in manual_build.
