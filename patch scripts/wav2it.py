#!/usr/bin/env python3
"""
wav2it.py — wrap a rendered song (WAV) as a single-sample Impulse Tracker (.IT) module
=======================================================================================
Age of Wonders 1's music engine only plays IT/S3M tracker modules, not MP3/WAV. This
tool embeds a whole recorded song as ONE looping sample in a minimal .IT module (one
note triggers it; the module loops forever), so the game will play your custom track.

Drop the resulting .IT into the game's  Songs\  folder (the game folder-scans it).

Downsamples to mono + a chosen rate to keep the file size sane (a full song at CD
quality is ~30MB; the game's stock tracks are <=3.2MB, so smaller is safer for the old
player). If a track won't load in-game, regenerate at a lower --rate (or --bits 8).

Accepts WAV or MP3 (and 24-bit/float WAV) — anything but 16-bit PCM WAV is decoded via
ffmpeg (found on PATH or in an ImageMagick install) first.

Usage:
  python wav2it.py "song.wav"                       # -> song.IT  (22050 Hz mono 16-bit)
  python wav2it.py "song.mp3"                        # MP3 in, .IT out (needs ffmpeg)
  python wav2it.py "song.wav" --rate 16000          # smaller/lower quality
  python wav2it.py "song.wav" --short               # 8.3 output name (game prefers short names)
  python wav2it.py *.wav -o Songs                   # batch, output into Songs\
Our AoW-tuned preset (matches the vanilla-loudness recipe):
  python wav2it.py "song.mp3" --loudness -12 --bass 6 --channels 2 --short -o Songs
Requires Python <=3.12 (uses the stdlib `audioop`). No external Python packages.
"""
import sys, os, struct, argparse, re
try:
    import audioop
except ImportError:
    sys.exit("ERROR: this needs Python 3.12 or earlier (stdlib 'audioop' was removed in 3.13).")

def find_ffmpeg():
    """Locate ffmpeg (needed to read MP3 / non-16-bit WAV). Checks PATH then ImageMagick."""
    import shutil, glob
    p = shutil.which('ffmpeg')
    if p:
        return p
    for g in (glob.glob(r'C:\Program Files\ImageMagick*\ffmpeg.exe') +
              glob.glob(r'C:\Program Files (x86)\ImageMagick*\ffmpeg.exe')):
        return g
    return None

def decode_with_ffmpeg(inp):
    """Decode any audio (MP3, 24-bit/float WAV, ...) to a temp 16-bit PCM WAV; returns its path."""
    import tempfile, subprocess
    ff = find_ffmpeg()
    if not ff:
        raise RuntimeError("need ffmpeg to read this format (MP3 or non-16-bit WAV). "
                           "Install ffmpeg, or export the track as 16-bit PCM WAV.")
    fd, tmp = tempfile.mkstemp(suffix='.wav'); os.close(fd)
    subprocess.run([ff, '-y', '-i', inp, '-c:a', 'pcm_s16le', tmp],
                   check=True, capture_output=True)
    return tmp

def short_name(base):
    """Derive a safe 8-char (8.3) track name from an arbitrary basename (game likes short names)."""
    s = re.sub(r'[^A-Za-z0-9]', '', base).upper()
    if s.startswith('X') and len(s) > 8:      # drop the user's "X " prefix token when it helps
        s = s[1:]
    return (s or 'SONG')[:8]

def read_wav(path):
    d = open(path, 'rb').read()
    if d[:4] != b'RIFF' or d[8:12] != b'WAVE':
        raise ValueError("not a WAV file")
    i = 12; fmt = None; data = None
    while i + 8 <= len(d):
        cid = d[i:i+4]; sz = struct.unpack_from('<I', d, i+4)[0]; body = i+8
        if cid == b'fmt ':
            af, ch, sr, _, _, bps = struct.unpack_from('<HHIIHH', d, body)
            fmt = (af, ch, sr, bps)
        elif cid == b'data':
            data = d[body:body+sz]
        i = body + sz + (sz & 1)   # chunks are word-aligned
    if not fmt or data is None:
        raise ValueError("missing fmt/data chunk")
    af, ch, sr, bps = fmt
    if af not in (1, 0xFFFE) or bps != 16:
        raise ValueError(f"need 16-bit PCM WAV (got format {af}, {bps}-bit). Re-export as 16-bit PCM.")
    return data, ch, sr, bps

def build_it(name, pcm, rate, bits, mv, nchan=1):
    """pcm = signed 16-bit LE mono; returns .IT file bytes.
    The song plays ONCE: one note triggers the sample, and enough empty patterns
    follow to span the whole song's duration, then the module ends (so the game
    rotates to the next track, exactly like it does with the stock tracks)."""
    import math
    if bits == 8:
        pcm = audioop.lin2lin(pcm, 2, 1); width = 1
    else:
        width = 2
    nsamp = len(pcm) // width
    nm = name.encode('latin1', 'replace')[:25]

    speed, tempo = 6, 125
    spr  = 2.5 * speed / tempo                     # seconds per row (0.12s)
    ROWS = 64                                       # rows per pattern
    dur  = nsamp / rate
    total_rows = math.ceil(dur / spr) + 8           # +8 rows (~1s) tail margin
    nfull = max(1, total_rows // ROWS)              # count of full 64-row patterns (incl pat0)
    rem   = total_rows - nfull * ROWS               # rows in a final short pattern (0..63)
    has_rem = rem > 0
    patnum = 3 if has_rem else 2
    # orders: pat0, then pat1 (nfull-1 times), then pat2 (the remainder), then end
    order_list = [0] + [1] * (nfull - 1) + ([2] if has_rem else []) + [255]
    ordnum = len(order_list)

    hdr = bytearray(192)
    hdr[0:4] = b'IMPM'; hdr[4:4+len(nm)] = nm
    struct.pack_into('<HHHH', hdr, 0x20, ordnum, 0, 1, patnum)
    struct.pack_into('<HHHH', hdr, 0x28, 0x0214, 0x0100, 0x0009, 0x0000)
    hdr[0x30], hdr[0x31], hdr[0x32], hdr[0x33], hdr[0x34], hdr[0x35] = 128, mv, speed, tempo, 128, 0
    for k in range(64): hdr[0x40+k] = 32
    for k in range(64): hdr[0x80+k] = 64

    base = 192 + ordnum + 0 + 4 + patnum * 4
    smphdr_off = base
    pat_start  = smphdr_off + 80

    def pattern(rows):                              # rows: list of per-row bytes (no end marker)
        packed = bytearray()
        for r in rows:
            packed += r; packed.append(0x00)
        return struct.pack('<HH', len(packed), len(rows)) + b'\0\0\0\0' + bytes(packed)

    # trigger the sample on nchan channels at once so the old player sums them like a
    # vanilla multi-channel module (single channel plays much quieter in-game than vanilla).
    firstrow = b''.join(bytes([0x80 | ch, 0x03, 60, 1]) for ch in range(1, nchan + 1))
    pat0 = pattern([firstrow] + [b''] * (ROWS - 1))                     # note C-5 + sample1 x nchan
    pat1 = pattern([b''] * ROWS)                                        # empty filler
    pats = [pat0, pat1] + ([pattern([b''] * rem)] if has_rem else [])
    pat_offs = []; off = pat_start
    for p in pats: pat_offs.append(off); off += len(p)
    smpdata_off = off

    sh = bytearray(80)
    sh[0:4] = b'IMPS'; sh[4:4+8] = b'SONG.PCM'
    sh[0x11] = 64
    sh[0x12] = 0x01 | (0x02 if bits == 16 else 0)   # has sample, 16-bit, NO loop (plays once)
    sh[0x13] = 64
    sh[0x14:0x14+len(nm)] = nm
    sh[0x2e] = 0x01
    struct.pack_into('<I', sh, 0x30, nsamp)
    struct.pack_into('<I', sh, 0x3c, rate)          # C5 speed = sample rate -> C-5 plays at native pitch
    struct.pack_into('<I', sh, 0x48, smpdata_off)

    out = bytearray()
    out += hdr; out += bytes(order_list)
    out += struct.pack('<I', smphdr_off)
    out += struct.pack('<%dI' % patnum, *pat_offs)
    out += sh
    for p in pats: out += p
    out += pcm
    return bytes(out)

def bass_boost(data, fs, gain_db, f0=120.0):
    """Low-shelf EQ: boost frequencies below ~f0 Hz by gain_db (adds kick/bass weight).
    Pre-attenuates for headroom; maximize() renormalises the level afterwards."""
    import array, math
    if gain_db <= 0:
        return data
    A = 10 ** (gain_db / 40.0)
    w0 = 2 * math.pi * f0 / fs; cw = math.cos(w0); sw = math.sin(w0)
    sq = 2 * math.sqrt(A) * (sw / 2 * math.sqrt(2))
    b0 = A * ((A+1) - (A-1)*cw + sq); b1 = 2*A * ((A-1) - (A+1)*cw); b2 = A * ((A+1) - (A-1)*cw - sq)
    a0 =     (A+1) + (A-1)*cw + sq;  a1 = -2 * ((A-1) + (A+1)*cw);   a2 =     (A+1) + (A-1)*cw - sq
    b0/=a0; b1/=a0; b2/=a0; a1/=a0; a2/=a0
    sm = array.array('h'); sm.frombytes(data)
    pre = 0.5; x1=x2=y1=y2=0.0
    for i in range(len(sm)):
        x0 = sm[i] * pre
        y0 = b0*x0 + b1*x1 + b2*x2 - a1*y1 - a2*y2
        x2=x1; x1=x0; y2=y1; y1=y0
        v = int(y0)
        sm[i] = 32767 if v > 32767 else (-32768 if v < -32768 else v)
    return sm.tobytes()

def maximize(data, target_db):
    """Raise average loudness to ~target_db RMS with a smooth soft-limiter on peaks
    (so the game's dense tracker tracks and your wide-dynamic-range master match).
    Returns (data, applied_gain_dB)."""
    import array, math
    rms = audioop.rms(data, 2)
    if rms < 1:
        return data, 0.0
    G = (10 ** (target_db / 20.0) * 32767) / rms
    G = min(G, 12.0)                                          # sanity cap
    T = 0.5 * 32767                                           # soft-knee threshold
    C = 0.985 * 32767                                         # ceiling (tiny headroom)
    S = C - T
    sm = array.array('h'); sm.frombytes(data)
    for i in range(len(sm)):
        v = sm[i] * G
        if v > T:
            o = v - T; v = T + S * o / (o + S)
        elif v < -T:
            o = -v - T; v = -(T + S * o / (o + S))
        sm[i] = int(v)
    return sm.tobytes(), 20 * math.log10(G)

def load_audio(inp):
    """Return (pcm16le, channels, rate, bits). Reads 16-bit PCM WAV directly; anything
    else (MP3, 24-bit/float WAV, ...) is decoded to a temp WAV via ffmpeg first."""
    tmp = None
    try:
        if os.path.splitext(inp)[1].lower() == '.wav':
            try:
                return read_wav(inp) + (None,)
            except ValueError:
                pass                                         # wrong WAV subtype -> ffmpeg
        tmp = decode_with_ffmpeg(inp)
        return read_wav(tmp) + (tmp,)
    except Exception:
        if tmp and os.path.exists(tmp): os.remove(tmp)
        raise

def convert(inp, out_dir, rate, bits, mv, target_db, bass_db, nchan=1, short=False):
    data, ch, sr, bps, tmp = load_audio(inp)
    try:
        if ch == 2: data = audioop.tomono(data, 2, 0.5, 0.5)      # stereo -> mono
        if sr != rate: data, _ = audioop.ratecv(data, 2, 1, sr, rate, None)  # resample (filtered)
        if bass_db > 0:
            data = bass_boost(data, rate, bass_db)               # low-shelf bass boost (before limiter)
        gdb = 0.0
        if target_db is not None:
            data, gdb = maximize(data, target_db)
        songname = os.path.splitext(os.path.basename(inp))[0]
        outbase = short_name(songname) if short else songname
        it = build_it(songname, data, rate, bits, mv, nchan)
        outp = os.path.join(out_dir or os.path.dirname(inp) or '.', outbase + '.IT')
        open(outp, 'wb').write(it)
        return outp, len(it), gdb
    finally:
        if tmp and os.path.exists(tmp): os.remove(tmp)

def main():
    ap = argparse.ArgumentParser(description="Wrap a WAV as a single-sample AoW .IT module (plays once)")
    ap.add_argument('wavs', nargs='+')
    ap.add_argument('--rate', type=int, default=22050, help='output sample rate (default 22050)')
    ap.add_argument('--bits', type=int, default=16, choices=(8, 16), help='sample bit depth')
    ap.add_argument('--mv', type=int, default=128, help='mix volume 0-128 (default 128, stock=48)')
    ap.add_argument('--loudness', type=float, default=-10.0,
                    help='target RMS loudness in dBFS via soft-limiter (default -10; louder = closer to 0; '
                         'use --loudness 0 to disable and keep original dynamics)')
    ap.add_argument('--bass', type=float, default=0.0,
                    help='low-shelf bass boost in dB below ~120 Hz, applied before the limiter '
                         '(adds kick/percussion weight; default 0 = off; try 6)')
    ap.add_argument('--channels', type=int, default=1,
                    help='trigger the sample on N channels at once so the game sums them like a '
                         'vanilla multi-channel module (default 1; try 2-4 for more in-game loudness)')
    ap.add_argument('--short', action='store_true',
                    help='name the output with a safe 8.3 filename derived from the track name '
                         '(the game prefers short names)')
    ap.add_argument('-o', '--out', default=None, help='output directory')
    a = ap.parse_args()
    a.mv = max(0, min(128, a.mv))
    a.channels = max(1, min(16, a.channels))
    target = None if a.loudness >= 0 else a.loudness
    for w in a.wavs:
        try:
            p, n, gdb = convert(w, a.out, a.rate, a.bits, a.mv, target, a.bass, a.channels, a.short)
            print(f"  {os.path.basename(w)} -> {p}  ({n/1048576:.1f} MB, {a.rate}Hz mono {a.bits}-bit, "
                  f"MV={a.mv}, {a.channels}ch, loudness {('%+.1f dB' % gdb) if target is not None else 'off'}, "
                  f"bass {('+%.0f dB' % a.bass) if a.bass > 0 else 'off'})")
        except Exception as e:
            print(f"  {os.path.basename(w)}: ERROR {e}")

if __name__ == '__main__':
    main()
