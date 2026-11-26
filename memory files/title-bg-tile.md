---
name: title-bg-tile
description: 2026-10-31 title screen scrolling panorama (title.ilb #0, 1514 px) drew only 2 copies → stale strip on wide screens; now tiled across the surface width; APPLIED untested
metadata:
  type: project
---

**APPLIED 10/31, untested** — `patch scripts/patch_exe_title_bg_tile_v1.py` (.bak_titlebg AoWx.exe). TTitleScene VMT 0x4192F4 (methods TitleSceneCreate 0x41A310, WindowDrawSurfaceEx 0x41A030, WindowUpdate 0x638225 .xtut). Background helper 0x419C84: x0 = −((ticks−25 clamp0 + 0x1EA) mod W), W = Int\Scenes\title.ilb image 0 (ScrollBackg5 1514x432) width [img+0x20]; drew at x0 and x0+W only (0x419D45..0x419D88) → in place replaced by a loop while x < surface width [esi+0x8C] (loop var [ebp−0x10]). Draw = img vmt+0x84 (eax=img, edx=x, ecx=y, push surface).
