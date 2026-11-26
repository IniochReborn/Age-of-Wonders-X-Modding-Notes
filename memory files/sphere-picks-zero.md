---
name: sphere-picks-zero
description: 2026-10-18 editor Map Settings "Sphere picks" spinner allows 0 (was 3/5/7); game needs no change (TLeader.SetSpherePicksMax from [map+0xEC]); patch_devx_sphere_picks_zero_v1 edits AoWDevX DFM + Vcladdon.dpl TSpin cave; ship Vcladdon.dpl
metadata:
  type: project
---
Map Settings → Restrictions spinner (Inc 2, Min 3, Max 7) stores [map+0xEC] (load 0x422BA4 / store 0x422E2E); AoWEPACK msg 0x20020005 @0x5578B32B → SetSpherePicksMax; no 3–7 validation in game. Script: AoWDevX DFM MinValue 3→0 (file 0xC381C) + Vcladdon.dpl TSpin.CheckValue tail 0x403709 → 48-B cave 0x414710 (CODE slack, VS 0x13710→0x13800) mapping 1→0 / 2→3 for Inc2/Min0/Max7 spins only. `.bak_spheres0`. APPLIED 10/18; 0-sphere game untested (research/AI). ⚠ release zip must include Vcladdon.dpl (new modified file).
