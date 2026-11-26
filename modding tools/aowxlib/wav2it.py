"""WAV/MP3 -> single-sample Impulse Tracker (.IT) module - AoWxBard's engine.

Derived from the game-root wav2it.py (the proven CLI converter): AoW1's music
player only speaks IT/S3M tracker modules, so a whole rendered song is embedded
as ONE sample that a single note triggers; empty patterns span the song's
duration and the module then ends, so the game rotates to the next track just
like it does with the stock music.

Differences from the CLI script: convert_file() takes the output path and the
in-game (module) name explicitly - the GUI pregenerates and lets the user edit
both - and the loudness/EQ steps are plain booleans (the tuned AoW preset).

Needs Python <= 3.12 (stdlib audioop). MP3 and non-16-bit WAV input additionally
need ffmpeg on the machine (PATH or an ImageMagick install).
"""
import glob
import math
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile

try:
    import audioop
except ImportError:                                        # Python 3.13+
    audioop = None

# the tuned AoW preset (matches the vanilla-loudness recipe)
RATE = 22050
BITS = 16
MIXVOL = 128
LOUDNESS_DB = -12.0        # "Volume balancer" target RMS
BASS_DB = 6.0              # "AoW EQ" low-shelf gain below ~120 Hz
NCHAN = 2                  # trigger on 2 channels like vanilla multi-channel mods
NAME_MAX = 25              # IT module name field length


def find_ffmpeg():
    p = shutil.which("ffmpeg")
    if p:
        return p
    for g in (glob.glob(r"C:\Program Files\ImageMagick*\ffmpeg.exe")
              + glob.glob(r"C:\Program Files (x86)\ImageMagick*\ffmpeg.exe")):
        return g
    return None


def short_name(base):
    """Safe 8-char track name from an arbitrary basename (game likes 8.3)."""
    s = re.sub(r"[^A-Za-z0-9]", "", base).upper()
    if s.startswith("X") and len(s) > 8:
        s = s[1:]
    return (s or "SONG")[:8]


def read_wav(path):
    d = open(path, "rb").read()
    if d[:4] != b"RIFF" or d[8:12] != b"WAVE":
        raise ValueError("not a WAV file")
    i = 12
    fmt = data = None
    while i + 8 <= len(d):
        cid = d[i:i + 4]
        sz = struct.unpack_from("<I", d, i + 4)[0]
        body = i + 8
        if cid == b"fmt ":
            af, ch, sr, _, _, bps = struct.unpack_from("<HHIIHH", d, body)
            fmt = (af, ch, sr, bps)
        elif cid == b"data":
            data = d[body:body + sz]
        i = body + sz + (sz & 1)
    if not fmt or data is None:
        raise ValueError("missing fmt/data chunk")
    af, ch, sr, bps = fmt
    if af not in (1, 0xFFFE) or bps != 16:
        raise ValueError("need 16-bit PCM WAV (got format %d, %d-bit)" % (af, bps))
    return data, ch, sr


def decode_with_ffmpeg(inp):
    ff = find_ffmpeg()
    if not ff:
        raise RuntimeError(
            "reading this format needs ffmpeg (MP3 or non-16-bit WAV). "
            "Install ffmpeg, or export the track as 16-bit PCM WAV.")
    fd, tmp = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    subprocess.run([ff, "-y", "-i", inp, "-c:a", "pcm_s16le", tmp],
                   check=True, capture_output=True,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return tmp


def load_audio(inp):
    """(pcm16le, channels, rate, tempfile-or-None)"""
    tmp = None
    try:
        if os.path.splitext(inp)[1].lower() == ".wav":
            try:
                return read_wav(inp) + (None,)
            except ValueError:
                pass
        tmp = decode_with_ffmpeg(inp)
        return read_wav(tmp) + (tmp,)
    except Exception:
        if tmp and os.path.exists(tmp):
            os.remove(tmp)
        raise


def bass_boost(data, fs, gain_db, f0=120.0):
    """Low-shelf EQ below ~f0 Hz; pre-attenuated, maximize() renormalises."""
    import array
    if gain_db <= 0:
        return data
    A = 10 ** (gain_db / 40.0)
    w0 = 2 * math.pi * f0 / fs
    cw, sw = math.cos(w0), math.sin(w0)
    sq = 2 * math.sqrt(A) * (sw / 2 * math.sqrt(2))
    b0 = A * ((A + 1) - (A - 1) * cw + sq)
    b1 = 2 * A * ((A - 1) - (A + 1) * cw)
    b2 = A * ((A + 1) - (A - 1) * cw - sq)
    a0 = (A + 1) + (A - 1) * cw + sq
    a1 = -2 * ((A - 1) + (A + 1) * cw)
    a2 = (A + 1) + (A - 1) * cw - sq
    b0 /= a0; b1 /= a0; b2 /= a0; a1 /= a0; a2 /= a0
    sm = array.array("h")
    sm.frombytes(data)
    pre = 0.5
    x1 = x2 = y1 = y2 = 0.0
    for i in range(len(sm)):
        x0 = sm[i] * pre
        y0 = b0 * x0 + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        x2 = x1; x1 = x0; y2 = y1; y1 = y0
        v = int(y0)
        sm[i] = 32767 if v > 32767 else (-32768 if v < -32768 else v)
    return sm.tobytes()


def maximize(data, target_db):
    """Raise average loudness to ~target_db RMS, soft-limiting the peaks.
    Returns (data, applied_gain_dB)."""
    import array
    rms = audioop.rms(data, 2)
    if rms < 1:
        return data, 0.0
    G = min((10 ** (target_db / 20.0) * 32767) / rms, 12.0)
    T = 0.5 * 32767
    C = 0.985 * 32767
    S = C - T
    sm = array.array("h")
    sm.frombytes(data)
    for i in range(len(sm)):
        v = sm[i] * G
        if v > T:
            o = v - T
            v = T + S * o / (o + S)
        elif v < -T:
            o = -v - T
            v = -(T + S * o / (o + S))
        sm[i] = int(v)
    return sm.tobytes(), 20 * math.log10(G)


def build_it(name, pcm, rate, bits, mv, nchan):
    """pcm = signed 16-bit LE mono; returns .IT file bytes. The song plays
    once - one note triggers the sample, empty patterns span the duration."""
    if bits == 8:
        pcm = audioop.lin2lin(pcm, 2, 1)
        width = 1
    else:
        width = 2
    nsamp = len(pcm) // width
    nm = name.encode("latin1", "replace")[:NAME_MAX]

    speed, tempo = 6, 125
    spr = 2.5 * speed / tempo
    ROWS = 64
    dur = nsamp / rate
    total_rows = math.ceil(dur / spr) + 8
    nfull = max(1, total_rows // ROWS)
    rem = total_rows - nfull * ROWS
    has_rem = rem > 0
    patnum = 3 if has_rem else 2
    order_list = [0] + [1] * (nfull - 1) + ([2] if has_rem else []) + [255]
    ordnum = len(order_list)

    hdr = bytearray(192)
    hdr[0:4] = b"IMPM"
    hdr[4:4 + len(nm)] = nm
    struct.pack_into("<HHHH", hdr, 0x20, ordnum, 0, 1, patnum)
    struct.pack_into("<HHHH", hdr, 0x28, 0x0214, 0x0100, 0x0009, 0x0000)
    hdr[0x30:0x36] = bytes((128, mv, speed, tempo, 128, 0))
    for k in range(64):
        hdr[0x40 + k] = 32
    for k in range(64):
        hdr[0x80 + k] = 64

    smphdr_off = 192 + ordnum + 4 + patnum * 4
    pat_start = smphdr_off + 80

    def pattern(rows):
        packed = bytearray()
        for r in rows:
            packed += r
            packed.append(0x00)
        return struct.pack("<HH", len(packed), len(rows)) + b"\0\0\0\0" + bytes(packed)

    firstrow = b"".join(bytes([0x80 | ch, 0x03, 60, 1]) for ch in range(1, nchan + 1))
    pats = [pattern([firstrow] + [b""] * (ROWS - 1)), pattern([b""] * ROWS)]
    if has_rem:
        pats.append(pattern([b""] * rem))
    pat_offs = []
    off = pat_start
    for p in pats:
        pat_offs.append(off)
        off += len(p)
    smpdata_off = off

    sh = bytearray(80)
    sh[0:4] = b"IMPS"
    sh[4:4 + 8] = b"SONG.PCM"
    sh[0x11] = 64
    sh[0x12] = 0x01 | (0x02 if bits == 16 else 0)
    sh[0x13] = 64
    sh[0x14:0x14 + len(nm)] = nm
    sh[0x2e] = 0x01
    struct.pack_into("<I", sh, 0x30, nsamp)
    struct.pack_into("<I", sh, 0x3c, rate)
    struct.pack_into("<I", sh, 0x48, smpdata_off)

    out = bytearray()
    out += hdr
    out += bytes(order_list)
    out += struct.pack("<I", smphdr_off)
    out += struct.pack("<%dI" % patnum, *pat_offs)
    out += sh
    for p in pats:
        out += p
    out += pcm
    return bytes(out)


def convert_file(inp, out_path, songname, balance=True, eq=True):
    """Convert one WAV/MP3 to out_path with the given in-game name.
    balance = the -12 dB RMS volume balancer, eq = the +6 dB AoW bass shelf.
    Returns (bytes_written, applied_gain_db)."""
    if audioop is None:
        raise RuntimeError("needs Python 3.12 or earlier (stdlib audioop)")
    data, ch, sr, tmp = load_audio(inp)
    try:
        if ch == 2:
            data = audioop.tomono(data, 2, 0.5, 0.5)
        elif ch != 1:
            raise ValueError("unsupported channel count %d" % ch)
        if sr != RATE:
            data, _ = audioop.ratecv(data, 2, 1, sr, RATE, None)
        if eq:
            data = bass_boost(data, RATE, BASS_DB)
        gdb = 0.0
        if balance:
            data, gdb = maximize(data, LOUDNESS_DB)
        it = build_it(songname, data, RATE, BITS, MIXVOL, NCHAN)
        open(out_path, "wb").write(it)
        return len(it), gdb
    finally:
        if tmp and os.path.exists(tmp):
            os.remove(tmp)
