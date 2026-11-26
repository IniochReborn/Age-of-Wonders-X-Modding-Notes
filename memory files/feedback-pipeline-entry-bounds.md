---
name: feedback-pipeline-entry-bounds
description: When editing a SPELLS dict entry in patch_dual_sphere_spells_v1.py, bound the search to that entry (up to the next `dict(`), never a fixed N-line window
metadata:
  type: feedback
---
Editing entry N by searching "the next 10 lines" for pokes=/desc=/gfx= can hit the FOLLOWING entry's line. On 10/18 Mimic's pokes overwrote Reversal's (identical values, so harmless) and Mimic itself stayed a unit spell until the user noticed.

**Why:** entries are short; a fixed window spills into the neighbour.
**How to apply:** compute the entry range i..j where j = next line starting with `dict(` or `]`, search only inside it, and after editing print the pokes/gfx lines of the touched entry and its neighbours. Related: [[secret-spells]].
