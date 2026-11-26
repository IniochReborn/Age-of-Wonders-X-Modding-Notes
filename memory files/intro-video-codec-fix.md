---
name: intro-video-codec-fix
description: Intro.avi black-screen-with-sound fixed by re-encoding Indeo 3.2 → Cinepak (codec Windows 10/11 removed vs still ships)
metadata: 
  node_type: memory
  type: project
  originSessionId: 363e8ad2-56ec-4ede-b38d-8eb55d00d2fc
  modified: 2026-08-09T23:36:48.312Z
---

**FIXED 2026-08-09: intro plays sound but black video on Win10 AND Win11.**
Root cause: `Images/Scenes/Intro.avi` used **Indeo Video 3.2 (IV32)**, which
Microsoft removed/blocked from Windows (security), so it's absent on 10/11.
`VideoP.dpl` plays via **Video for Windows** (avifil32 + msvfw32, dynamic
LoadLibrary; ICLocate/ICDecompress/AVIStreamGetFrame → decodes each frame into
a GFXE.TDIBSurface and blits). No codec → ICDecompress fails → black frames;
audio is 16-bit stereo 22050 PCM (universal) so sound plays. Both-OS = codec,
not machine.

FIX: re-encoded video IV32 → **Cinepak (cvid)** — its decoder `iccvid.dll`
STILL ships with Win10/11 (unlike Indeo) and VfW ICLocate finds it; audio
copied verbatim. `ffmpeg -y -i Intro.avi -c:v cinepak -c:a copy out.avi`
(ffmpeg's built-in indeo3 decoder reads the input Windows can't; cinepak
encoder is SLOW ~0.1x realtime, ~20min for 2:15). Result: 640x480 15fps cvid +
PCM, 79MB (was 94MB). Original backed up `Intro.avi.bak_indeo` (same folder).
FALLBACK if Cinepak ever unavailable: Microsoft Video 1 (`msvideo1`/MSVC,
also ships, faster encode, blockier). MJPEG/modern codecs WON'T work (no
default VfW decoder). Uncompressed too big (~1.8GB).
NOTE for distribution: ship the re-encoded Intro.avi; every player's Win10/11
has the Cinepak decoder. Same fix applies to any other IV32 scene videos.
