---
name: feedback-check-game-running
description: Never run the VEH check/taskkill or write game files when tasklist shows AoWx/AoWDevX running — the user may be playing
metadata:
  type: feedback
---
Always check `tasklist | grep -ci 'aowx.exe\|aowdevx'` = 0 and STOP (don't continue the chain) if it is non-zero — the user is often playtesting while I work. On 10/17 I chained the check with `;` and my VEH step's `taskkill //F //IM AoWx.exe` killed a running session.

**Why:** taskkill /F kills every AoWx.exe instance, including the user's game; writing DLL/ILB files under a running game also fails or corrupts.
**How to apply:** gate the whole apply+VEH chain with `[ "$(tasklist | grep -ci 'aowx.exe\|aowdevx')" = 0 ] && ...`; if busy, wait and tell the user. Related: [[aowx-dual-sphere-spells]].
