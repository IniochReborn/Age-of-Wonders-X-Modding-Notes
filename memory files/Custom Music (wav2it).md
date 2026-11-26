# Custom Music (wav2it)

A **tool / workflow**, not a binary patch. `wav2it.py` wraps a rendered song (WAV or
MP3) as a single-sample Impulse Tracker (`.IT`) module so Age of Wonders 1's music
engine will play custom tracks.

## Why it's needed

AoW1's 1999 music player only understands **tracker modules (IT / S3M)** — it cannot
play MP3 or WAV. So an AI-rendered song (e.g. a Suno export) has to be *repackaged* as a
tracker module. `wav2it.py` builds a **minimal `.IT` module that contains the whole song
as ONE sample**: a single note on the first row triggers the sample, empty patterns span
the song's full duration, then the module ends — so the game rotates to the next track,
exactly like it does with the stock tracks. (The sample has **no loop**, so it plays
once through.)

## Requirements

- **Python ≤ 3.12** — it uses the stdlib `audioop`, which was **removed in 3.13**. On the
  dev box `py` is 3.10.6. No third-party Python packages needed.
- **ffmpeg** only if the input isn't 16-bit PCM WAV (MP3, 24-bit / float WAV). It's found
  on `PATH` or inside an ImageMagick install. Plain 16-bit PCM WAV needs nothing.

## The final working recipe (confirmed good in-game)

```
py wav2it.py Songs/*.wav --loudness -12 --bass 6 --channels 2 -o custom_it_output
```

or single-file with the game-ready 8.3 name written straight into `Songs/`:

```
py wav2it.py "song.mp3" --loudness -12 --bass 6 --channels 2 --short -o Songs
```

Then copy each output into `Songs/` under an **8.3 filename** (game convention; long names
untested). The game folder-scans `Songs/` for `.IT` files.

### Knobs

| Flag | Meaning |
|------|---------|
| `--loudness N` | target RMS loudness in dBFS via a per-channel soft-limiter (default −10; louder = closer to 0; `--loudness 0` disables and keeps original dynamics). Recipe uses **−12**. |
| `--bass N` | low-shelf boost (dB) below ~120 Hz, applied **before** the limiter — adds kick/percussion weight. Recipe uses **6**. |
| `--channels N` | trigger the sample on **N channels at once** so the old player sums them like a vanilla multi-channel module. Recipe uses **2**. |
| `--rate` | output sample rate (default 22050). Lower it (e.g. 16000) or drop `--bits 8` if a track won't load in-game. |
| `--bits` | sample bit depth 8 or 16 (default 16). |
| `--mv` | IT mix volume 0–128 (default 128; stock tracks use 48). |
| `--short` | emit a safe 8.3 filename derived from the track name (drops a leading "X " token). |
| `-o DIR` | output directory. |

## THE LOUDNESS LESSON (why custom tracks kept sounding quiet)

Raising the **sample's** RMS did **not** fix perceived quietness in-game.

- Measured with ffmpeg `volumedetect` on a libopenmpt render: vanilla `.it` tracks
  average **~−24.6 dB mean / ~16.6 dB crest**. A single-channel version of a custom track
  was already **−14.5 dB mean** (≈10 dB *hotter*) yet sounded **quieter** in-game.
- **Root cause:** vanilla tracks are **multi-channel** (8–16 channels) and the 1999 player
  **sums the channels**. A single-channel sample module only fills one mixer slot no matter
  how hot the sample is. All per-channel volume fields were already maxed — multichannel is
  the only remaining lever.
- **Fix:** `--channels 2` makes the engine sum two identical copies (~+6 dB coherent), like
  vanilla. For more level, `--channels 3`/`4` with each channel proportionally quieter.

**Two warnings:**
1. **ffmpeg / libopenmpt is NOT a faithful proxy for the AoW1 engine's balance.** It rated
   the custom track louder than vanilla when the game actually plays it quieter. The
   **in-game player is the only ground truth** for loudness.
2. **Don't over-compress to chase RMS.** Crushing the level flattened the crest factor
   (7.4 vs vanilla ~16.6) and made it lifeless. Keep per-channel loudness moderate (**−12**)
   and get level from **channels**, not the limiter.

**Multichannel clipping headroom:** 2 identical channels sum coherently, so drop the
per-channel level to leave headroom (2ch @ −12 measured −1.9 dB peak — safe). If it
distorts in-game, lower to −15.

## How the pipeline works (`convert()` order)

1. stereo → mono (`audioop.tomono`)
2. resample to `--rate` (`audioop.ratecv`, filtered)
3. low-shelf **bass boost** (before the limiter)
4. **maximize**: raise RMS to `--loudness` with a smooth soft-limiter (soft-knee at 0.5·full
   scale, ceiling 0.985·full scale)
5. **build_it**: embed the PCM as one no-loop `IMPS` sample; compute how many 64-row
   patterns span the song; order list = `[pat0] + [pat1]×(n−1) + [pat2 remainder] + [255 end]`;
   the first row fires `C-5 + sample 1` on **N channels**.

## Drag-and-drop tool: `Songs/AoWxBard.exe`

A standalone **PyInstaller one-file** (~6.5 MB, **needs no Python**) wrapping
`wav2it_drop.py`, which imports `wav2it.convert` with the preset baked in. Drop a WAV/MP3
onto it and it writes the 8.3-named `.IT` into **the folder the EXE itself lives in** (via
`os.path.dirname(sys.executable)` when frozen), so it works on any PC / any folder name.
Console banner: `Age of Wonders X  -  WAV/MP3  ->  IT  Music Converter`. Custom icon = AoWx
dragon over a silver CD.

**Build recipe:**
```
py -m pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org pyinstaller
py -m PyInstaller --onefile --console --icon <scratch>/convert_it.ico --name AoWxBard wav2it_drop.py
```
(The `--trusted-host` flags are only needed on a box behind an SSL-MITM proxy where plain
pip fails `CERTIFICATE_VERIFY_FAILED`.)

## The live custom tracks (10, in `Songs/` as 8.3 `.IT`)

`BLKWATER.IT` Blackwater Lake · `LASTGDBY.IT` Last Goodbye · `NTRADE.IT` Northern Trade
Route · `UNITECLN.IT` Uniting the Clans · `GABRIEL.IT` Gabriel's Last Stand ·
`HALLHERO.IT` Hall of Heroes · `BURBATAK.IT` Isle of Burbatak · `MINEOUT.IT` Mining
Outpost · `PRELWAR.IT` Prelude to War · `SUBPATH.IT` Subterranean Path.

To add more: drop the WAV/MP3 in `Songs/`, re-run the batch command, copy the output to an
8.3 `.IT` name (or just use `AoWxBard.exe`).

---
`wav2it.py` is included in this folder (copied from the game root).
