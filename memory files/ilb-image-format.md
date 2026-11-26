---
name: ilb-image-format
description: "Validated AoW1 .ILB image-library format — header/directory/record layout, the empty-image terminator gotcha, and a census of all 689 game ILBs"
metadata: 
  node_type: memory
  type: reference
  originSessionId: 66c54916-064a-4d90-b1cc-a7e1edb96f02
  modified: 2026-08-25T00:24:51.888Z
---

The AoW1 `.ILB` (Image Library) format, verified against all 689 ILBs in the install
(689/689 parse cleanly with the rules below). Primary sources, both in
`old modding tools\`: `ILB desc.pdf` (21-page spec by the ILBEditor author) and
IlbMaker's C# codec (`IlbMaker_Source_1.0.2.7\AoW1Graphics.cs`, `AoWGraphics.cs`).
See [[old-modding-tools]] for the tools themselves.

**Header** — `magic=0x424C4904` ("\x04ILB"), `someId` (unused; 0x0040F000 / 0x0040DB00),
`version` as a **float** (3.0=0x40400000, 4.0=0x40800000), `hdrLength` (16 for v3, 24 for v4).
v4 adds `imgDirectory` (byte offset where pixel data starts), `fileLength`, `numPalette`.
Each palette = id `0x88801B18` + 256 × (R,G,B,pad) = 1028 bytes.

**Image directory** — repeating: `Id` (u32; `0xFFFFFFFF` ends the directory), optional
`isComposite` (`0x100`, layered sub-images), `Type`, then type-specific fields, then
`lastWord = 0xFFFFFFFF`. Common prefix: `InfoByte`, Delphi-style name (u32 len + chars),
wide, high, xshift, yshift, subid, unknownA(byte), size, `offset` **only if InfoByte != 1**,
totalwide, totalhigh. 8-bit types then have unknownB + (unknownC/D if InfoByte==3) + palette
index; 16-bit types have (drawMode+blendValue if InfoByte==3) + pixelFormat. Types 2/3/17/18/22
add clipwide/cliphigh/clipxoff/clipyoff/transparent; types 2/17/18 additionally add `clip_x`.
If InfoByte==1 the pixel data is inline here (v3 style); otherwise it lives at
`imgDirectory + offset`.

**Two terminator gotchas that break naive parsers** (both cost me a debugging pass):
- A standalone **empty image** (`Type == 0`) is `Id, 0, filler` and has **NO** `0xFFFFFFFF`
  terminator — the next Id follows immediately. The PDF's own dumper `continue`s past the
  terminator check, which is easy to miss when reading the prose.
- **End-of-composite** is a bare `Type == 0` with **no filler dword and no terminator**;
  the enclosing image's terminator follows. So Type 0 means two different things
  depending on whether you are inside a composite.

**Corpus census** (Images\ + Int\, 689 files, 33 003 images / 33 475 records incl. sub-images):
- versions: 686 × v4.0, 3 × v3.0. Palettes/file: 392 × 0, 281 × 1, 16 × **2**.
- types: RLESprite08 20660, RLESprite16 5799, Sprite16 4795, Picture16 1922,
  TransparentRLESprite16 299, Empty 75. **No Picture08/Sprite08 in AoW1 data** (those are AoW2/SM).
- InfoByte: 2 → 18390, 3 → 15010, 1 → 75. unknownA is 1 except 69×2 and 57×0. unknownB always 0.
- pixelFormat is **always** 0x56509310 (RGB565). 514 composite images.
- `clip_x` observed: 0 (22334), 0x466214 (2627), 0x465EEC (1226), 0x466014 (351),
  **0x466344 (177), 0x465D4C (39), 0x4673E8 (4)**. The last three are NOT among IlbMaker's
  five known constants, so IlbMaker silently rewrites them to 0 on round-trip — a real
  corruption risk any replacement tool must avoid by preserving the raw value.

**Signedness traps** — `clipwide`/`cliphigh` and `xshift`/`yshift` are **signed** i32, not u32.
85 records across 6 files (ADD_STRUCTURES1/2, Add_DeadUnit, BHMed1*) have a *negative*
(degenerate) clip box paired with `size == 0`, meaning "blank image"; 144 records have
negative shifts. Reading these unsigned produces widths like 4294967233 and crashes decoders.

**RLE encoding** (matches the game's own encoder bit-for-bit): per scanline emit
`u32 length` then the run stream, where a background pixel becomes the pair
`(back, count)`; length = bytes-in-stream + 4. For 16-bit, values are u16 and the count is
stored as **2×run** (byte count), and if the stream holds an odd number of u16s one extra
`back` value is appended as padding *after* the length field was computed. Re-encoding
4,161 real RLE images reproduced the original bytes exactly.
**Latent bug in IlbMaker**: its 8-bit run counter is a `Byte`, so a background run > 255
silently wraps and corrupts. Real AoW1 data never triggers it (max 8-bit clip width is 103),
but any newly imported wide 8-bit sprite would — a correct encoder must split runs at 255.
The 16-bit counter is an Int16 holding 2×run, so it is safe (max real width 618).

Working lossless codec: `scratchpad\ilbcodec.py` (`read()`/`write()`; **689/689 game ILBs
round-trip byte-identical**), plus `ilbcensus.py`, `ilbdecode.py`, `rle_test.py`
(session scratch — re-create from this note if gone). Our own patch scripts only do
surgical byte-appends into existing ILBs (`build_summon_silver_dragon.py`,
`build_magic_sight_icon.py`), not a general codec.
