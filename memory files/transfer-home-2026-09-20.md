---
name: transfer-home-2026-09-20
description: "Laptop→desktop transfer package prepared 2026-09-20: 410 prerelease folder + everything since 409 (memory, patch scripts, changelog draft, I_x2026.ilb, Discord drops, BXL Sept references); supersedes the 2026-08-30 transfer"
metadata: 
  node_type: memory
  type: project
  originSessionId: 66789e63-73a2-4017-b28e-e3141c79cafc
  modified: 2026-09-20T17:10:00.000Z
---

On 2026-09-20 a laptop→desktop transfer was staged in `transfer to home PC (new sept 20)\`:

- `Age of Wonders X - 410 prerelease\` — full copy of the live 410 game folder (1629 files, 523 MB), copied by the user, verified identical.
- `memory, scripts, etc\` — built by Claude (1651 files, 336 MB): `claude memory 2026-09-20\` (all 34 memory files incl. MEMORY.md), the **whole** `patch scripts\` folder (240 files; the 2026-09-09+ ones are the 410 work), `changelog_1.37.410_DRAFT.txt`, `Images\Items\I_x2026.ilb` (NOT inside the 410 folder — must be dropped into it before cutting 410), `Scenario\Custom\________Test.hsm`, the two Sept Discord zips (`AoWx_410_WIP_scripts_and_notes_2026-09-15.zip`, `AoWx_to_Zig - Vince_Carter_on_Weis.zip`), `reference files\BXL-notes-20260829-to-20260909 (1)\` and `reference files\AoW Ziggurat (Sept 2026)\Ziggurat\` (BXL's Sept dump; the rest of that folder is a stock 8/22 game copy, not shipped).
- README: `transfer to home PC (new sept 20)\README - TRANSFER 2026-09-20.txt`.

The previous full transfer was 2026-08-30 ([[transfer-home-2026-08-30]] recipe still applies: no baked paths, delete `AoWEd_LastDirs.ini`, Python 3.12 + keystone/capstone/pillow, `AOW_GAME_DIR`). Nothing outside the 410 folder changed between 08-30 and 09-09 except the 08-30 transfer staging itself, so this package plus the 08-30 one covers everything.

**INSTALLED on the desktop 2026-09-20** (`C:\Users\<user>\Desktop\Age of Wonders X - Claude`) — **the user did NOT want a 410 subfolder**: the 410 folder's contents were merged OVER the project root (the project folder is the game dir, as before the laptop era). Hash comparison first: 37 files added (laptop `backup\*.bak_*`, AoWDevX_dbg.exe, a few maps/saves), 26 overwritten (all 5 patched binaries, Dict/Release.mld + ResStr.mld, Release/Ability.pfs + Release.hss + Spells.pfs + Unitres.pfs, user maps), 1 root-newer file kept (Scenario\Custom\Reign of Chaos.hsm). Then the subfolder was deleted and `AOW_GAME_DIR` (user env var) set back to the project root. I_x2026.ilb + MSight.ILB are in place. The root's August `.bak_*` files are untouched; laptop backups live in `backup\` (bakpath legacy fallback still finds the old ones). 50 laptop scripts merged into `patch scripts\` (6 home-newer kept: build_release_zip.py --add, manual builder, hub/installer assets). ⚠ 31 laptop scripts hardcoded `C:\Users\<user>\...410 prerelease` defaults — all rewritten to `from bakpath import game_dir, game_file` (added 9/20: AOW_GAME_DIR if set, else parent of patch scripts); dry runs of vortex/heal-ai/cursor-coords/prune-v2/ranged-obstacles report ALREADY PATCHED against the root binaries. Memory merged (17 new, 4 replaced, aowdevx-binary-notes hand-merged, home kept aowsetup-internals + aowx-release-process). Desktop-only 8/31–9/3 patches are in the 410 binaries via the 409 base (dev-dir binaries were == 409 install). Python here is 3.10 (all scripts compile; pefile/keystone/capstone/Pillow present). The laptop is now STALE.

**Why:** the 2026-09-09 → 09-18 work (410 prerelease: item HP/MV, Legendary abilities, Vortex, frost terrain, tactical-AI rebalance, healing AI, Leadership rework, caster-cost wallet, DevX prune, diag_veh tooling) exists only on this machine.

**How to apply:** after this date the OTHER machine is current; if a session runs here, check file dates before trusting the game dir. On the receiving machine, install the memory snapshot into its own slug dir, then follow [[aowx-410-pending-tests]] for what is still untested. Related: [[discord-share-drops]], [[aowx-showscene-msight]] (release-zip new-file list).

**Superseded:** the desktop's state went back to the laptop on 2026-09-23 02:22 (game folder only, not memory/scripts) and the laptop was current again until the next transfer, [[transfer-home-2026-10-11]] (installed on the desktop 2026-10-11).
