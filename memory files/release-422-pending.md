---
name: release-422-pending
description: "Checklist for the 1.37.422 cut (started 10/22) - zip --add/--drop entries, installer changes, items done/pending"
metadata:
  node_type: memory
  type: project
  originSessionId: 511f9df3-964c-401e-b2ff-e5d99b017377
  modified: 2026-10-22T07:17:27.336Z
---

The user asked for these before releasing 422 (10/22).

DONE:
- **Slow 380 icon:** vanilla glyph on the Earth→Water cloud. Added GLYPH_COPIES to build_dual_sphere_icons_v1.py and applied it; only id 380 changed (verified). Backup `backup\SpellIcn.ILB.bak_slow422`. NOTE: the script's own `.bak_dualicons` is ANCIENT, so never use its --revert. The manual takes its icons from the live ILB, so it regenerates at the cut.
- **Map renames:** `Scenario\Custom\AoWx - Greed_s Paradise / Igor_s Folly / Oracle_s Eye.hsm` → `'s` (the internal titles already used apostrophes). AoWxInstaller.iss got an [InstallDelete] section for the three old names.
- **Xergal's Legacy:** `AoWx - Xergal's Legacy.hsm` was never shipped (the 421 zip lacks it, though the changelog mentions it).
- **Discord Rich Presence:** AoWxPresence.exe + the rebuilt AoWxUpdater.exe + the AoWx.exe launch-gate NOP. See [[presence-game-state-re]].

AT THE CUT (build_release_zip.py):
- `--drop "Scenario/Custom/AoWx - Greed_s Paradise.hsm;Scenario/Custom/AoWx - Igor_s Folly.hsm;Scenario/Custom/AoWx - Oracle_s Eye.hsm"`
- `--add "Scenario/Custom/AoWx - Greed's Paradise.hsm;Scenario/Custom/AoWx - Igor's Folly.hsm;Scenario/Custom/AoWx - Oracle's Eye.hsm;Scenario/Custom/AoWx - Xergal's Legacy.hsm;AoWxPresence.exe"`
- A version patch 421→422 (patch_version_422.py), plus the changelog and manual.

IN RESEARCH (forks 10/22, read-only): realm heroes tab columns (Turn Met / Experience), phoenix corpse gfx, MP reload remember races, lobby dropdowns staying open, possess → leader transfer.

10/22 BUILD PHASE. Forks write the scripts; Claude applies them one at a time. AoWEPACK zones assigned:
- heroes tab: 0x55836000-0x55836400
- MP reload autoclaim: 0x55836400-0x55836800
- possess leader: reserve 0x55836800-0x55837000

User decisions:
- Turn Met = the turn the hero joined its current owner. Resurrection or animation counts as joining again.
- Pre-422 saves show "-".
- The name column gets shortened.
- No AI-level restore.
- Phoenix corpse uses the base-sprite colours with no glow. The script is built but NOT applied; it waits for the user's OK on the preview.
- Possess: waiting on 3 answers (Resurrect Hero dual leader, desertion/upkeep, spellcasting).
- 10/22 APPLIED, in this order:
  1. build_phoenix_corpse_v1 (user OK'd the preview)
  2. patch_combo_stay_open_v1 (aowInt)
  3. patch_mp_reload_autoclaim_v1 (AoWEPACK; name table in DATA slack 0x558E9F10-0x558E9F78)
  4. patch_hero_turnmet_v1 (AoWEPACK)
  5. patch_exe_realm_heroes_cols_v1 (AoWx.exe; .xtut grown to 0x15000; dfmbin.py helper)
  All of them dry-run as applied. The game starts to the title window (15 s smoke test). Live tests are pending with the user.
- Changed files to ship: Images\UNITS\DeadUnit.ILB and Release\Unitgfx.pfs (both are already in the zip, so they are picked up as changed).
- 10/22 ❌ patch_hero_turnmet_v1 BROKE hero loading: the SP leader-customization was blank (no name, face or abilities) and an old save showed Turn Met 717. REVERTED (AoWEPACK == .bak_turnmet). The likely cause is tag 0x60 read out of order in the tagged stream. Sent back to the fork for v2 with offline validation against a real hsm and save. Saves made while v1 was on may be bad.
- 10/22 MP reload autoclaim did NOT work for the user: rehosting a turn-1 autosave assigned nothing. The user was asked about host role, leader names vs lobby names, and join timing.
- 10/22 Leader's Soul built, NOT applied (apply order: patch_leader_soul_v1 → patch_leader_soul_ability_pfs_v1 → banner_ceilings → tcablist_ceiling). The user was asked whether the soul body should keep the leader's mana income.
- 10/22 Leader's Soul APPLIED (4 scripts in order; startup smoke OK). The user decided the soul body does NOT get the leader's mana income (vanilla). Live tests pending.
- 10/22 Autoclaim v1 was accidentally reverted by the fork. v2 is APPLIED (MRA2: leader name from [[p+0x58]+0x60] first, claim check flags&3, diag block 0x558E9F78). Probe: autoclaim_probe.py [--watch], run on the host after picking the save and again after the client joins. Lesson: forks must never run --revert/--apply without --dll pointing at a copy.
- 10/22 Turn Met v2 APPLIED (tag 0x10060). Runtime error 217 on EXIT: TAbilityControl.UnregisterAbility → TAbility.Destroy → invalid free, i.e. Leader Soul ability 0xCE registration. Sent to the possess fork for v2. Autoclaim v2 still failed live; the user needs to run autoclaim_probe.py.
- 10/22 Leader Soul v2 APPLIED: it drops the out-of-bounds [eax+0x24] write on the 36-byte TAbility. Exit is now clean (code 0, no exceptions, checked with the VEH logger).
- 10/22 Probe result: autoclaim v2 collected the map TEMPLATE leader names ("Elf"/"Dark Elf" from [[p+0x58]+0x60]) instead of the live leaders ("Peewee the Peony" is in the save). v3 is requested: read the live TLeader name from the loaded map armies.
- 10/22 v3 also failed: the lobby save load has NO unit data (names exist only in root tag 0x1; tag-21 player records hold no name). v4 requested: save the lobby name in TPlayer (new dword tag) at game start, and AutoClaim reads it. Pre-422 saves cannot be auto-assigned.
- 10/22 autoclaim v4 APPLIED (TPlayer+0xDC lobby name, tag 0x10061, InstanceSize 0xE0; SetupMap hook). Startup and exit clean under the VEH logger. All-files tag scan OK. Live test needs a NEW MP game saved after v4.
- 10/22 v4 live: names are stored and read correctly (TPlayer+0xDC hits 2). BUT the pref is off by one: the host was seated in slot 2 (Azracs) instead of slot 1, and the client was not claimed. v5 requested.
- 10/22 autoclaim v5 APPLIED: the pref is a RACE id (IndexOfRace compares record+0x18), and the late-join re-claim was fixed. The model on the real autosave gives host→Elves, client→Dark Elves.
- 10/22 ✅ USER-CONFIRMED: MP reload autoclaim v5 works (lobby remembers races on rehost).
- 10/22 User results: Turn Met/hero cols OK-ish (not fully tested), lobby dropdowns ✅, phoenix corpse ✅, Slow icon ✅, maps ✅. Leader's Soul: resurrect/animate CRASHED (v2 used [hero+0x20] as army; army is [unit+4]). Leader Soul v3 APPLIED 10/22 17:00 (fix + 50% synced coin flip leader vs other dead heroes, leader if none + immediate morale + Mind Decay immunity c8); startup/exit smoke clean (code 0). Awaiting user retest.
- 10/22 17:26 Leader Soul v4 APPLIED (TLeader VMT+0x180 setup-leader compare refused the revived leader at every hex → override for PICK/0x80/0x81; location fallback; nil-abort guard; diag counters via leader_soul_probe.py). Smoke clean. Awaiting user retest.
- 10/22 17:30 patch_exe_soul_portrait_v1 APPLIED (AoWx.exe .xtut 0x648E00, Events header shows the 0xCE unit's face; backup .bak_soulface). Smoke clean. Ship AoWx.exe. Awaiting user test together with Leader Soul v4.
- 10/22 intro egg: fade-in 0.3 s (was 0.8, WAV only; music ramp-down unchanged 0–1.5 s); fade 0.5 s sooner again: WAV fade-out 13.5–15.8 s (rebuilt), music back up 13.5–15.5 s (4 imm32 patched in place in AoWx.exe zone 0x638195/1A1/1AA/1B4; backups .bak_introfade135). patch_exe_intro_egg_v1 dry-run ABORTs on layout since .xtut growth (pre-existing) — never --revert it. Ship INTRO_EGG.WAV + AoWx.exe.
- 10/22 title music return fade = 1 s (13.5→14.5 s; imm32 0x6381A1 T3=17700, 0x6381B4 diff=1221).
- 10/22 17:52 Leader Soul v5 APPLIED (leader joins the soul's stack directly, bypassing the vanilla placer; coin flip only counts the caster's OWN dead heroes; STAGE breadcrumbs 0x5590B3D8 via leader_soul_probe.py). Smoke clean. v4 live failures: no-pick with enemy dead heroes in the pool; leader pick → TSpellTE exc + VCL30 garbage AV + 217 at exit.
- 10/22 17:55 v5 LIVE WORKS (STAGE 8 both, clean exit). User change → v6: leader joins the CASTER's stack (fallback soul stack → placer).
- 10/22 18:03 Leader Soul v6 APPLIED (caster stack → summon-style 30-ring search, place-then-add → fizzle consumed like summons; never soul stack). Smoke clean. EFCreateError at cast = two instances sharing autosave.asg (benign).
- 10/22 16:29 user's intended EDITOR balance changes (for the 422 changelog; keep them, never restore Release pfs from older backups):
  Spells: Hunter's Mark research 45→35; Summon Boar research 30→40.
  Units: Djinn DEF 4→2, Shadow DEF 4→3, Incarnate DEF 3→1 (all gain up to +3 DEF vs units without True Seeing via Invisibility).
  That editor save dropped Ability.pfs rec 216 (Leader's Soul) → re-applied 18:10; fork investigating why the editor drops it.
- 10/22 18:30 fork: editor registers 0xCE fine (count 0xCF), the save path has no filter, and the possess grant is pure bit ops (no pfs dependency), so why 216 was dropped is UNKNOWN. Workaround: re-run patch_leader_soul_ability_pfs_v1.py after every editor save. Pending user test: possess grants the soul? plus the editor list/save test (back up Ability.pfs first).
- 10/22 18:58 patch_retaliation_giveup_v1 APPLIED (AoWEPACK zone 0x55837800-0x55837C00; after a result-2 "Cannot inflict damage" combat, the marked group goes homebound if the predictor shows zero damage possible; --read shows the counters). Smoke clean. LIFO: revert before build_defender_retaliation. Awaiting user test.
- 10/22 manual home Spells tile → "N spells across 8 spheres and 14 dual-spheres" (computed from names with '/'); template.html + live manual edited.
- 10/22 19:09 retaliation give-up v2 APPLIED (fixes the auto-combat AV from v1's stale [TE+0x28]; gives up on the first result-2: auto = no damage dealt, tactical = result 2). Smoke clean. Awaiting user retest.
- 10/22 19:18 give-up v2 LIVE: tactical gives up after 1 try ✅; AUTO AVs in cave A fast path (0x5583787A, [TFastCombat+0x10]=4 not a list) → TE abort leaves [map+0x120] set → infinite 'Combat already created'. v3 requested.
- 10/22 19:20 give-up v3 APPLIED (TFastCombat IS a TCombat; one guarded path via pos2 map lookup, no damage scan; STAGE 0x558FAB14, 0x19 = clean). Smoke clean. Awaiting auto + tactical retest.
- 10/22 19:27 ✅ USER: retaliation give-up v3 WORKS (auto + tactical). New Leader Soul bugs → v7 requested: a leader dying while it carries Possessed spawns an Incarnate WITHOUT 0xCE (ic/iv only inherit from 0xCE, not TLeader); an AV at rebased 00CB1BF7 (read 0x3EE) when the Incarnate possesses in the same combat.
- 10/22 19:36 Leader Soul v7 APPLIED (ic7/iv7: an Incarnate made from a TLeader gets 0xCE + morale; overworld GameOver suppressed for that one Killed call). Smoke clean. Bug 2 (AV read 0x3EE) needs a VEH-logged repro.
