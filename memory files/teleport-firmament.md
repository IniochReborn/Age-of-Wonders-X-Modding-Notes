---
name: teleport-firmament
description: 2026-10-31 teleporter destination Z = -1 means Firmament (internal level 3): ReadWrite translation + editor dialog; APPLIED untested
metadata:
  type: project
---

**APPLIED 10/31, untested** — `patch scripts/patch_teleport_firmament_v1.py` (.bak_telefirm AoWEPACK + AoWDevX). User: Firmament as level 3 (Abyss 4+) is confusing; Surface/Caverns/Depths 0/1/2 must not change (existing maps) → wanted -1.
- Internal level stays 3 ([[map-levels-29-plan]] order 0,1,2,3=Firmament,4..28 Abyss). TTeleport dest bytes +0x30/+0x31/+0x32 (x,y,z). TTeleport.ReadWrite 0x557A4DC8 streams z via one rwByte call (tag 9) for load AND save → wrapped @0x557A4DF6 → cave 0x558E0540 'TFM1': pre 3→0xFF, post 0xFF→3. File value -1 (or 3) = Firmament; every reader sees 3.
- Editor TTeleportEditForm: load 0x4197A9 shows 3 as -1 + Z spin MinValue [+0x130] = -1; OK 0x419858 stores -1 as 3. Caves AoWDevX 0x4ECFC0..0x4ED000 (autosave code zone shrunk to end 0x4ECFC0).
- Not guarded: Z=-1 on a map without a Firmament level (spinner min is always -1).
