---
name: transfer-home-2026-10-11
description: "Laptop→desktop transfer package prepared 2026-10-11: full 410 folder + 410 delta since the 2026-09-23 desktop import + all memory + whole patch scripts; carries the Death/Fire dual-sphere work (Bloodbath/Hell Hound/Hellfire) and the AoO/High Prayer fixes; supersedes the 2026-09-20 transfer"
metadata:
  node_type: memory
  type: project
  originSessionId: 10dbf4c6-4e87-4a49-8150-7c72bc67146f
  modified: 2026-10-11T17:32:19.240Z
---

On 2026-10-11 a laptop→desktop transfer was staged in `transfer to home PC (new oct 11)\` (README inside: `README - TRANSFER 2026-10-11.txt`).

Timeline that matters: the laptop's 410 folder was overwritten with the DESKTOP's copy on 2026-09-23 02:22 (every file carries that timestamp, incl. `X\Modding\*.exe`, `Sfx\Kain`, `Songs`); all laptop work since then is dated 2026-10-03..10-07 by file clock (the memory notes label those sessions 2026-10-08..10-10 — same work, clock drift; do not look for anything newer than the 10/7 files).

Package layout:
- `Age of Wonders X - 410\` — full robocopy of the live 410 folder (2890 files, ~1.06 GB) incl. `backup\*.bak_*`.
- `410 delta since 2026-09-23\` — only the 42 files that differ from the 9/23 desktop state (AoWEPACK.dll, AoWTCPCK.dll, AoWDevX.exe, 9 new backups, Images\Effects\DualDF.ILB, Images\SpellIcn.ILB, Release\*.pfs + Release.hss, Sfx\Zsp\DUALDF_*.WAV, User\*.ail/.ahl, X\Modding\*.exe (10/4 builds), `.dual sphere spells.txt`). Use this if the desktop 410 folder changed after 9/23; otherwise just take the full copy.
- `memory, scripts, etc\claude memory 2026-10-11\` — all 38 memory files incl. MEMORY.md and this note.
- `memory, scripts, etc\patch scripts\` — the whole folder minus `__pycache__` (2026-10-03+ files are the dual-sphere/AoO work: build_dual_sphere_{fx,icons,sfx}_v1.py, patch_dual_sphere_{plumbing,spells}_v1.py, patch_tc_{hellfire_portal,spell_alias,hail_msg_spell,bloodbath_aura}_v1.py, patch_bloodbath_v1.py, patch_highprayer_glow_v1.py, patch_spelltypes_relocate_v1.py, patch_devx_sphere_items_v1.py, patch_aoo_hits_vcall_v1.py, build_ai_aoo_awareness.py, spellgfx.py, hail_trace_probe.py).
- `memory, scripts, etc\changelog_1.37.410_DRAFT.txt` (unchanged since 09-16; dual-sphere entries NOT yet added).

**Why:** everything from 2026-10-03 on (dual-sphere Death/Fire spells, High Prayer glow, AoO soft-lock fix, SpellTypes relocation) exists only on the laptop.

**How to apply:** after this date the DESKTOP is current; a later laptop session must check file dates before trusting the game dir. On the desktop, install the memory snapshot, then read [[aowx-dual-sphere-spells]] — the open items are the in-game retests of hound icon v7, portal v19, the post-Hellfire delay fix and the Bloodbath skull icon. Still standing: release-zip namelist must get the new files by hand (DualDF.ILB, DUALDF_*.WAV, I_x2026.ilb, MSight.ILB) per [[aowx-showscene-msight]]; delete `AoWEd_LastDirs.ini` after copying; tooling = Python 3.12 + keystone-engine/capstone/pillow + `AOW_GAME_DIR`. Previous transfers: [[transfer-home-2026-09-20]], [[transfer-home-2026-08-30]].

**INSTALLED on the desktop 2026-10-11** (project root = game dir, no 410 subfolder): hash check first — the desktop's AoWEPACK.dll / AoWTCPCK.dll / AoWDevX.exe were byte-identical to the laptop's 9/23 backups (`.bak_dualsphere` / `.bak_spelltypes_reloc` / `.bak_sphereitems`), so the 42-file delta was copied straight over the root (binaries, Release\*.pfs + Release.hss, SpellIcn.ILB, DualDF.ILB, 5 DUALDF WAVs, User lists, X\Modding exes, 9 new `backup\*.bak_*` + the 5 laptop 9/23 backups incl. backup\Release\Spells.pfs.bak_dualspells and backup\Images\SpellIcn.ILB.bak_dualicons). Every overwritten file was first saved to `backup\pre_oct11\<relpath>`. Desktop-only work after 9/23 (9/24 map edits: AoWx - Lord of the Rings / Xergal's Legacy / San Andreas .hsm, 9/27 saves) is untouched; the only data conflict was `User\xZig.ail` (desktop 9/24 7061 B vs laptop 10/7 7055 B, a 6-byte list difference) — laptop version taken, desktop copy in pre_oct11. Scripts: the laptop's `patch scripts` was the OLD pre-9/20 set plus new files, so NOT merged wholesale — only the 19 new files + build_spelltypes_bounds_fix.py / build_warp_self_stage1.py (SpellTypes-relocation notes) + veh_attach_log.txt copied; the 15 new scripts had the laptop path baked in and were rewritten to `bakpath.game_dir()/game_file()`; the 10/04 vcall warning was hand-merged into the desktop's build_ai_aoo_awareness.py (which keeps the 9/20 type-3/5 fix the laptop copy lacked). All 11 new patch scripts dry-run as ALREADY APPLIED against the installed binaries. Memory: 3 new files added, aowx-410-pending-tests hand-merged, index updated; the laptop MEMORY.md (38-file index) was NOT taken. The laptop is STALE after 2026-10-11.
