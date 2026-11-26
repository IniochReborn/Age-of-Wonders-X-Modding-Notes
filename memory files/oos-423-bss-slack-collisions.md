---
name: oos-423-bss-slack-collisions
description: 10/23 MP OOS (Azracs vs Highmen, 422) root-caused to AoWEPACK BSS-slack collisions — Harvest v8 crop buffers (view-dependent) overwrote the weakness ability ids; also weakness wiped by retaliation Create, give-up counters on Wall of Flames' clone. All moved; APPLIED, MP-untested
metadata:
  type: project
---
**Report 10/23:** live MP game (2 humans + AI players, save `X\Save\new bug autosave OoS.asg`, day 9) went OOS; reload + spectate didn't repro; user's local 2-instance tests (fresh, and one instance playing a turn first) didn't OOS either.

**Root cause (proven live with a ReadProcessMemory peek):** `patch_harvest_v1.py` v8 glow (10/15) kept PENDING 0x558FA580 / ACTIVE **0x558FA820** crop buffers, refilled from every crop field DRAWN on that machine's screen after each static redraw — runs even if nobody casts Bountiful Harvest. ACTIVE sat on WEAK_IDS 0x558FA810..82F (slot 4 = on-screen crop count, slots 5–7 = crop x|y<<8|owner<<16) → StrikeDmg x1.5 / effect-roll −3 weakness checks used per-machine ability ids → combat divergence → OOS. Running game showed slot4 = 0x0A.

**Other collisions fixed the same day (user approved):**
- defender-retaliation mark table 0x558FA800..0x558FAA00 (zeroed every TAoWHSMap.Create) overlapped the weakness scratch 0x558FA800 + WEAK_IDS → weaknesses were DEAD since August (slots 0–3 read 0). Now restored → ⚠ gameplay change: 8 weakness abilities 0x51–0x55/0x85–0x87 work again.
- Spring-of-Life wasteland diag breadcrumbs 0x558FA8F0..8F4 = retaliation entry 15.
- retaliation give-up v3 counters 0x558FAB00..1B on Wall of Flames' TCombatFire VMT clone header (built-flag [VMT−0x40]) → crash class.

**New layout:** Harvest PEND 0x558FA580 / ACT 0x558FA6A4 (cap 116→72, ends 0x7C8) · Spring diag 0x558FA7C8..7CC · weakness scratch 0x558FA7D0, WEAK_IDS 0x558FA7E0..7FF · retaliation alone 0x558FA800..0x558FAA00 · give-up CNT 0x558FAAE0..AAFB · WoF clone 0x558FAB00..AC50 alone.
**Scripts:** patch_harvest_v1.py (constants edited, in-place upgrade) · patch_retaliation_giveup_v3.py (CNT override, reverted→re-applied) · NEW `patch_slack_relocate_v1.py` (30 disp32 sites, capstone-checked, --revert) — BXL weakness/spring build scripts no longer dry-run "applied". Backups: backup\AoWEPACK.dll.bak_harvestbuf (before any move), .bak_slackfix (before give-up/cap-72/relocate), .bak_slackreloc. Smoke: title clean under VEH logger; live peek WEAK_IDS = 51..55,85..87.
**Lesson:** byte-scan refs (`$TEMP\aowx_oos\slackrefs.py`) only see absolute/PIC disp32 — relative-addressed tables are invisible; claim slack ranges in a shared map before using them. Open: host-only TAoWHSMap.Create in lobby (hPickMap) also runs the retaliation/MPH1 wipes — unverified.
