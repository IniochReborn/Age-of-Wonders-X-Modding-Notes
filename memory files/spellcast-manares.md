---
name: spellcast-manares
description: "Hero mana income = (Spellcasting level) x 1.5 x Resistance — BXL adoption; x2 confirmed 8/30, retuned x1.5 9/1"
metadata: 
  node_type: memory
  type: project
  originSessionId: bc99310d-e7a0-464e-8b38-a64c2704c9e7
  modified: 2026-09-01T07:51:20.187Z
---

Applied 2026-08-30 (`patch scripts\build_spellcast_manares.py`, backup `AoWEPACK.dll.bak_manares`; **user-confirmed in-game 8/30**: Spellcasting I + RES 6 → +12 mana). Idea from BXL's build_spellcast_manares.py (Ziggurat Scrolls); formula per user spec: **(level×2)×RES** (his was ×1). No cave, no hook — in-place rewrite of the 40-byte level→power body @0x557885EC..0x55788613 (24B used).

**Surprise finding:** our AoWEPACK was already NON-vanilla here — an AoWx pre-Claude patch had collapsed THero.GetPowerGeneration @0x557885E4 to `call 0x5578B43C; ret` and put a **5/10/20/40/80 flat table** in the freed zone (vanilla was inline level*5+5 = 10..30; BXL's tree had an analogous old patch with 10/20/40/60/90). `--revert` restores the AoWx table, not vanilla.

Mechanics (RE from BXL, byte-verified on ours): power chain THeroPowerSource.Power @0x557867D0 → hero vtable[+0x134]; TLeader.GetPowerGeneration @0x5578B43C checks/reads Spellcasting 0x34 via item-aware +0x148/+0x144 then `call 0x557885EC` @0x5578B461 (the zone's ONLY ref, swept). Zone entry contract: EAX=level, EBX=hero (callee-saved). RES via vtable[+0xCC] = THero.GetResistance 0x5578850C (same for THero+TLeader, clamped [0,40] internally). Units unaffected: TUnit/TAdjustableUnit +0x134 = zero stub 0x5577FDB4. Exe/TCPCK carry no copy of the formula — all displays + AI budget follow via GetPower @0x5577CA00 / GetManaIncome @0x5577C95C. New body is register-relative only (PIC, no relocs). MP-safe (deterministic).

In-game checklist: Spellcasting I + RES 6 hero adds 12 (was 5); RES raise raises income; leader scales same; unit with Spellcasting adds 0; magic-window per-hero line matches.

**How to apply:** rerun script (idempotent); tune = edit NEW_BODY tail. Related: [[ziggurat-scrolls-dump]], [[bxl-reference]].

**9/1 retune ×2 → ×1.5** (user request): new 27-byte body computes `(level*RES*3)>>1` — single final round-down (`imul eax,edx / imul eax,eax,3 / shr eax,1`), so e.g. SC I + RES 5 = 7, SC I + RES 6 = 9. Script keeps the old ×2 body as `PREV_2X` and upgrades/reverts from it in place; applied 9/1 over the ×2 state, env checks ALL PASS, in-game untested (checklist: SC I + RES 6 hero adds 9, was 12). changelogs.txt + manual (Magic section + changelog tab) updated to "(Spellcasting level) x 1.5 x Resistance".
