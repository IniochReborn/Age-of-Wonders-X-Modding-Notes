---
name: feedback-verify-changelog-vs-data
description: "Before every release cut, check each changelog value change (costs, stats, levels) against the data files that actually go in the zip; 434 shipped Hurl Skull at 25 while the changelog said 20"
metadata:
  node_type: memory
  type: feedback
  originSessionId: 0b831bd8-9b1b-446a-877b-e67f98571de3
  modified: 2026-11-21T06:07:43.916Z
---

Before cutting a release, read every concrete value the changelog claims (ability cost, spell level/research, unit stats) out of the files that go into the zip (Release\Ability.pfs, Spells.pfs, Unitres.pfs ...) and compare. A mismatch stops the cut and gets raised to the user at once.

**Why:** 1.37.434 (11/20/2026) changelog said "Hurl Skull level-up cost reduced from 25 to 20" and the user says they explicitly asked me to make sure it made the upload. I only wrote "Level up cost: 20" into the manual's General Changes block; the shipped Ability.pfs record 214 tag 6 was still 25 (the editor data save of 11/20 10:01 carried the user's new Hurl Skull description but cost 25; nothing wrote the file after that, so no script reverted it — the value was simply never 20 in the file at cut time, and I never checked). User found out after release and was angry (11/21). Fixed locally with patch_hurlskull_cost_v2.py (25 -> 20, backup .bak_hskcost20).

**How to apply:** at the docs step of a cut, for each "X changed from A to B" line, print the live value from the pfs and confirm it equals B; also check the manual's Abilities/Spells tab (read live from the pfs) agrees with the General Changes text. Costs the user sets in the editor are not mine to assume — verify. Related: [[aowx-release-process]], [[feedback-raise-flagged-issues]].
