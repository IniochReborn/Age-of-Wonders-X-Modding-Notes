---
name: custom-music-wav2it
description: wav2it.py — convert Suno/WAV songs to AoW1-playable .IT modules; the loudness/bass/multichannel recipe that matches vanilla
metadata: 
  node_type: memory
  type: project
  originSessionId: ae619055-3278-433b-b71b-cf21e5789ad7
  modified: 2026-07-21T23:48:18.377Z
---

Tool `wav2it.py` (game root) wraps a rendered song (WAV) as a **single-sample .IT tracker module** so AoW1's music engine (IT/S3M only, no MP3/WAV) will play custom Suno tracks. The song plays ONCE: one note triggers the sample, empty patterns span the full duration, then the module ends and the game rotates to the next track (matches vanilla behaviour). Needs Python <=3.12 (stdlib `audioop`, removed in 3.13); use `py` (3.10.6 here).

**FINAL WORKING RECIPE (confirmed good in-game 2026-07-21):**
`py wav2it.py Songs/*.wav --loudness -12 --bass 6 --channels 2 -o custom_it_output`
then copy outputs into `Songs/` with 8.3 names (game convention; long names untested).

The 10 live tracks (8.3 name -> song): `BLKWATER.IT` Blackwater Lake, `LASTGDBY.IT` Last Goodbye, `NTRADE.IT` Northern Trade Route, `UNITECLN.IT` Uniting the Clans, `GABRIEL.IT` Gabriel's Last Stand, `HALLHERO.IT` Hall of Heroes, `BURBATAK.IT` Isle of Burbatak, `MINEOUT.IT` Mining Outpost, `PRELWAR.IT` Prelude to War, `SUBPATH.IT` Subterranean Path. Sources = the `X - *.wav` Suno exports in `Songs/` (each also has an `X - *.mp3` the game ignores). To add more: drop the WAV in `Songs/`, rerun the batch command, copy the output to an 8.3 `.IT` name.

**Drag-and-drop tool `Songs/AoWxBard.exe`:** standalone PyInstaller onefile (~6.5 MB, needs NO Python) wrapping `wav2it_drop.py` (imports `wav2it.convert`, preset baked in). Drops the 8.3-named `.IT` into the folder the EXE itself lives in — via `os.path.dirname(sys.executable)` when frozen, so it works on ANY PC / any folder name (does NOT look for our project folder). Console banner: "Age of Wonders X  -  WAV/MP3  ->  IT  Music Converter". Custom icon = AoWx dragon (32x32 via PowerShell `Icon.ExtractAssociatedIcon`) + ImageMagick-drawn silver CD w/ rainbow-arc sheen → `convert_it.ico`, embedded in the exe. (A `wav2it_convert.bat` Python fallback existed briefly but was deleted as redundant — the exe is the sole drop tool; regenerate the bat only if AV ever blocks the exe.) BUILD RECIPE: `py -m pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org pyinstaller` (this box has an SSL-MITM proxy → plain pip fails CERTIFICATE_VERIFY_FAILED, needs --trusted-host), then `py -m PyInstaller --onefile --console --icon <scratch>/convert_it.ico --name AoWxBard wav2it_drop.py`. wav2it.py also reads MP3 / non-16-bit WAV via ffmpeg fallback (`find_ffmpeg()` checks PATH + ImageMagick; NOTE its hardcoded IM paths are dev-machine only and MP3-only — doesn't affect output location), and has `--short` (8.3 name via `short_name()`, drops leading "X").

**Key knobs:** `--loudness` = target RMS dBFS via soft-limiter (per-channel); `--bass` = low-shelf boost dB below ~120 Hz (adds kick/percussion weight, applied pre-limiter); `--channels N` = trigger the sample on N channels at once; `--rate` (22050), `--bits` (16), `--mv` (128).

**THE LOUDNESS LESSON (why it kept sounding quiet):** raising sample RMS did NOT fix perceived quietness. Measured via ffmpeg volumedetect (libopenmpt render): vanilla .it tracks average ~**-24.6 dB mean / ~16.6 dB crest**; a single-channel version of mine was already **-14.5 dB mean** (10 dB HOTTER) yet sounded quieter in-game. Root cause: **vanilla tracks are multi-channel** (8-16 chans) and the 1999 player SUMS channels — a single-channel sample module only fills one mixer slot no matter how hot. Fix = `--channels 2` so the engine sums two copies (~+6 dB coherent) like vanilla. All per-channel volume fields were already maxed; multichannel is the only remaining lever. IMPORTANT: **ffmpeg/libopenmpt is NOT a faithful proxy for the AoW1 engine's balance** (it rated mine louder than vanilla when the game plays it quieter) — the in-game player is the only ground truth for loudness. Also: over-compressing to boost RMS crushed the crest factor (7.4 vs vanilla ~16.6) and made it flat; keep per-channel loudness moderate (-12) and get level from channels instead.

Multichannel clipping risk: 2 identical channels sum coherently, so drop per-channel level to keep headroom (2ch @ -12 measured -1.9 dB peak — safe; if in-game distorts, lower to -15). For more loudness go `--channels 3/4` with each channel proportionally quieter.

See [[active-patches.md]] for the binary mod state (separate from music).
