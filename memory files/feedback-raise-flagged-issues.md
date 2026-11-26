---
name: feedback-raise-flagged-issues
description: When a fix leaves a known related problem (e.g. another record still carrying foreign data the user rejected), tell the user right away - never park it as "only if asked"
metadata:
  type: feedback
---

On 11/07 I gave the Highpass UG Ziggurat alias the user's defender list. I knew our own underground Ziggurat (0x5A1A0001) still carried the Ziggurat mod's list, but only noted it in memory as "optional, only if the user asks". The user later found it while editing and was angry: "i specifically told you to ensure our AoWx defender list was preserved".

**Why:** the user's instruction was about the outcome (their AoWx data everywhere), not the single record I happened to be touching. A known leftover that contradicts an explicit instruction is part of the same task.

**How to apply:**
- When a fix leaves a known sibling problem that contradicts what the user asked for, fix it in the same pass, or tell the user explicitly in the final message.
- When copying records from another mod (Ziggurat/BXL), check every user-tunable field (defender lists f25, costs, stats) and default to OUR values, not theirs.

See [[zig-map-compat]].
