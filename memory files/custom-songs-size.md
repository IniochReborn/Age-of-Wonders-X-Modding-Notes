---
name: custom-songs-size
description: 2026-10-19 custom .IT songs (11, ~99 MB) cannot shrink losslessly on disk — Galaxy.dll plays only uncompressed IT samples; only download-size savings possible via installer-side lossless decode
metadata:
  type: reference
---
Each custom IT (ASHSTEPP…BLKWATER) = one 16-bit mono 22050 Hz uncompressed sample (already reduced from 44.1k stereo WAV sources; WAVs not shipped). Galaxy.dll IT sample loader (header 0x10020FDB–0x10021243, loader 0x10027410) honours only flags 0x02/0x10/0x40 + cvt bit 0 — no IT2.14/2.15 decompressor (flag 0x08 / cvt 0x04 ignored → noise). Other Galaxy formats also uncompressed. Only option: ship FLAC-style/delta+LZMA encoded and decode to identical .IT at install time (~60 MB vs 95 MB in zip). Not implemented.
User 10/19: drop the music-shrinking idea (do not revisit).
