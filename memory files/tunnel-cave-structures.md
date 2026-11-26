---
name: tunnel-cave-structures
description: "Cave/tunnel (TCave) RE: entrance-side byte, border-image tag sets, editor palette preview path; surface-preview fix applied 2026-08-31"
metadata:
  type: project
---

**Feature (user 2026-08-31):** the editor's structure-placement side panel previewed SURFACE tunnels with the water-tunnel art (the user added water-tunnel GFX long ago and wants it to keep working); underground tunnels previewed as normal tunnels. Wanted: normal art for both, water tunnels still functional. `patch scripts/build_tunnel_preview_normal.py` (.bak_tunnelpreview) APPLIED — awaiting test.

## RE
- Tunnel = **`Cave.TCave`** VMT 0x557B3018 (parent TStructure), resource `TCaveResource` VMT 0x557B326C (overrides only Create/ClassID/ResourceEditName/ResourceUserClassID — **no image logic**, so previews come from the structure side).
- **[cave+0x30] = entrance side.** TCave.Create @0x557B3424 sets it to **1**; TCave.ReadWrite @0x557B37C4 streams it as **tag 6** (1 byte). **1 = upper/surface mouth, 0 = the partner mouth one level down** — proven by PlaceHX @0x557B3670 (creates the level+1 partner only when ==1) and CanPlace @0x557B362C (only requires "a level exists below" when !=0).
- **TCave.GetTerrainTypeImage** (VMT +0x12C) @0x557B361C: `[+0x30]==1 → image = edx; else edx+30`. (Base TStructure version @0x5575E6A0 is already a mod: `jmp 0x5580C390`, which returns 0x19/0x1A/0x1B for terrain 3/5 when [struct+0x24]!=0xFF — an existing AoWx edit, unrelated.)
- **Editor palette preview path**: `TStructure.ShowBorderImageDC` @0x5575FAB4 — **no caller inside AoWEPACK, and AoWDevX.exe imports it** ⇒ the editor is the caller. It calls [vmt+0x140] GetBottomBorderImage first (0 ⇒ no preview), then composes via ShowBorderImage @0x5575F99C.
- **Two border-image tag sets** (image list at `[resource+0x24]`, looked up by tag via 0x557028E4 + 0x557028A4):
  - surface side → base TStructure getters → tags **0x1E / 0x1F / 0x20**
  - underground side → TCave overrides 0x557B3538 / 0x557B3584 / 0x557B35D0 → tags **0x21 / 0x22 / 0x23**
- **Release.hss data** (parsed 8/31; both tunnel records identical, at file offsets 0xC1CAF and 0xC4AEF): the 0x1E-0x20 set points into **BORDER.ILB** (imgs 3,4,5 and 6,7,8), the 0x21-0x23 set into **STR_CAVE.ILB imgs 5, 5, 6**. So underground previews render the plain cave art; the surface side rendered the BORDER.ILB variant the user sees as the water tunnel.
  - .hss image-ref record format: `<u32 namelen><NAME><00 00 00><u32 imgIndex><i32 xoff><i32 yoff>` — e.g. STR_CAVE.ILB img 5 at (-12,-24). Useful for any future .hss art repointing (no HSS parser exists in the tree yet).

## The fix
Each TCave border getter starts `cmp byte [ebx+0x30],0 / jne <base impl>`. The three `jne` (bytes **75 36**) at **0x557B3540 / 0x557B358C / 0x557B35D8** are NOPed, so BOTH entrance sides take the STR_CAVE (tag 0x21-0x23) path. Display-only: CanPlace/PlaceHX/CanEnter/Enter/EnterEx untouched ⇒ **water tunnels keep working**; TCave has no descendants so nothing else is affected. Also normalises the map placement-border preview to the same art (intended). Reloc-free; `--revert` restores 75 36.
