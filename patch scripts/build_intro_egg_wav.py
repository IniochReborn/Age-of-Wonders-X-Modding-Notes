#!/usr/bin/env python3
r"""
Title-screen 'inioch' intro song (2026-10-21): converts reference files\01. Intro.mp3 into Sfx\Zsp\INTRO_EGG.WAV.

User: the title music crossfades into the intro song, which fades in smoothly, plays to about 0:15, then fades out
and must be fully silent before 0:18 (a drum hits at ~18.3 s).  The fades are BAKED into the file so the sample can
never reach the drum, whatever the engine does:
  0.00 - 0.80 s  raised-cosine fade-in
  0.80 - 14.50 s full level
  14.50 - 16.80 s raised-cosine fade-out to silence
  16.80 - 17.00 s silence, file ends at 17.00 s (source position 17.0 s, 1.3 s before the drum)
Format: 16-bit PCM stereo 44100 Hz (the engine plays 44.1 kHz stereo WAVs, e.g. Sfx\Attack\*.WAV), peak 0.90.
The patch (patch_exe_intro_egg_v1.py) ramps the title music down 0-1.5 s and back up 14.5-16.5 s to match.

Usage: py -3.10 build_intro_egg_wav.py [--src <mp3>] [--out <wav>] [--apply]   (dry run writes to the scratch dir only)
"""
import argparse, os, subprocess, sys, tempfile, wave
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.dirname(HERE) if os.path.basename(HERE).lower() == "patch scripts" else r"C:\Users\<user>\Desktop\Age of Wonders X - Claude"
SRC = os.path.join(GAME, "reference files", "01. Intro.mp3")
OUT = os.path.join(GAME, "Sfx", "xSFX", "INTRO_EGG.WAV")   # 10/21 user: moved to xSFX
FFMPEG = r"C:\Program Files\ImageMagick-7.1.1-Q16-HDRI\ffmpeg.exe"
SR, LEN = 44100, 17.0
FI_END, FO_START, FO_END = 0.30, 14.00, 15.80   # 10/23 user: fade-out starts 0.5 s later (keep 'MIGHTY' at full), same end, steeper (was 13.5-15.8 raised-cosine; 10/22: fade-in 0.3 s)
FO_POW = 3.0                                    # fade-out gain = (1-x)^3: -6 dB after 0.36 s, -18 dB at the midpoint
PEAK = 0.90


def build(src):
    tmp = os.path.join(tempfile.gettempdir(), "intro_egg_src.wav")
    subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-i", src, "-map", "0:a:0", "-t", "%.2f" % LEN,
                    "-ac", "2", "-ar", str(SR), "-sample_fmt", "s16", tmp], check=True)
    w = wave.open(tmp)
    a = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").reshape(-1, 2).astype(np.float64) / 32768.0
    w.close(); os.remove(tmp)
    n = int(LEN * SR)
    if len(a) < n:
        a = np.vstack([a, np.zeros((n - len(a), 2))])
    a = a[:n]
    t = np.arange(n) / SR
    g = np.ones(n)
    fi = t < FI_END
    g[fi] = 0.5 - 0.5 * np.cos(np.pi * t[fi] / FI_END)
    fo = (t >= FO_START) & (t < FO_END)
    g[fo] = (1.0 - (t[fo] - FO_START) / (FO_END - FO_START)) ** FO_POW
    g[t >= FO_END] = 0.0
    a *= g[:, None]
    pk = np.abs(a).max()
    if pk > 0:
        a *= PEAK / pk
    return (np.clip(a, -1, 32767 / 32768) * 32768).round().astype("<i2")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    pcm = build(a.src)
    out = a.out if a.apply else os.path.join(HERE, "INTRO_EGG.WAV")
    with wave.open(out, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())
    tail = np.abs(pcm[int(FO_END * SR):]).max()
    print("written %s  (%.2f s, %d bytes, silent tail max %d)" % (out, len(pcm) / SR, os.path.getsize(out), tail))
    return 0


if __name__ == "__main__":
    sys.exit(main())
