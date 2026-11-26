---
name: patching-over-relocs-gotcha
description: "Before overwriting DLL code bytes, scan .reloc — a fixup landing inside your patch corrupts it on rebased/ASLR loads (crash only sometimes, e.g. one of two game instances)"
metadata: 
  node_type: memory
  type: project
  originSessionId: 635d8e67-17c7-4211-b98f-1476416bae9e
  modified: 2026-08-08T02:20:34.275Z
---

When hex-patching AoWEPACK.dll (or any DLL) code in place, any overwritten
instruction with an ABSOLUTE 32-bit operand (e.g. `A1 xx xx xx xx` mov
eax,[global]) has a base-relocation entry pointing at its imm32. Overwriting
with `jmp rel32` doesn't remove the reloc: on a REBASED load (ASLR — the two
LAN instances routinely load at different bases) the loader adds the base
delta on top of the new bytes → corrupted jump → instant AV. Symptom is
maddening: works at preferred base, crashes only on the rebased instance
("Exception during AoWHSMap.NewFrame" loop in the 8/7 case).

**Why:** the .reloc table is offset-based, not content-based; the loader
blindly fixes up whatever bytes sit there now.

**How to apply:**
- Before writing any code patch, scan the .reloc table for entries
  intersecting every patched byte range (parser: scratchpad check_relocs.py
  pattern; entries are 16-bit {type:4,offset:12} under 4KB-page blocks,
  dir index 5 of the optional header data directories).
- If a reloc lands inside the patch: neutralize the entry (type 3→0; loader
  skips type 0) as part of apply, restore on revert — see
  build_desync_diag2.py's RELOC_ENTRY_OFF handling. jmp rel32 replacement
  code needs no fixup; cave code should stay PIC (call/pop delta trick).
- Cave/BSS areas added in padding have no relocs, but verify once per new
  region.

Related: [[lan-desync-investigation]] (where this bit us),
[[aowepack-dll-is-live]].
