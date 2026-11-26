#!/usr/bin/env python3
r"""
Title screen 'inioch' intro song (2026-10-21).  AoWx.exe only; UI only (no game state, MP-irrelevant).

User: "when the user types 'inioch' at the title screen (cycles flavor text), the title screen music fades out /
crossfades into the intro song, which fades in smoothly; it plays to about 0:15 then fades out (fully faded before
0:18 to avoid a drum), then crossfades back with the title music resuming."

Sound plumbing (SoundP.dpl, unit Sound; the music player is Galaxy):
  * Sound.PlaySample(eax = AnsiString file name) [IAT 0x45D96C] plays a WAV through the SFX channel at the user's SFX
    volume (returns quietly if SFX are disabled or the sound system is absent) - concurrently with the music.
  * Sound.SetMusicVolume(eax = 0..100) [IAT 0x45D958] = TGalaxySoundSystem VMT+0x50 -> glxSetMusicVolume(v*127/100, 0)
    (immediate) - it does NOT touch the user's configured volume, which lives in the settings object
    [[[0x45A158]]+0xE8]+0x148 (0..100; the game itself uses it as the FadeMusicVolume target at 0x427E68/0x428090).
  * Sound.GetSFXEnabled 0x55406858 / GetMusicEnabled 0x55406824 (not imported by the exe) are reached through the
    SoundP link delta = [IAT 0x45D958] - 0x554067A8.
So a true crossfade is possible: the intro WAV (Sfx\Zsp\INTRO_EGG.WAV, fades BAKED in: 0.8 s fade-in, full to 14.5 s,
fade-out 14.5 -> 16.8 s, 17.0 s long, never reaches the 18.3 s drum) plays on the SFX channel while the music volume
is ramped per frame:  0 -> 1.5 s  V -> 0 (linear)  |  1.5 -> 14.5 s  0  |  14.5 -> 16.5 s  0 -> V  |  then V, done.

Hooks (all layered on the live title-quotes v3 / updater-title v4 chain):
  KEY  0x63510A in title-quotes v3's key cave: the 'inioch' match `jmp qpick` (E9 rel32) -> egg_start, which (unless
       an intro is already playing, quotes are off (QON 0x635450 = 0), SFX are disabled or the sound system is absent)
       plays the WAV, records the start time (KUSER_SHARED_DATA InterruptTime, 0.8192 ms ticks) and the configured
       volume V, then jumps on to qpick (the quote still cycles).  No restart while playing.
  UPD  method pointer 0x4193DA (TitleScene WindowUpdate, currently updater v4's wrapper) -> egg_upd: per-frame ramp
       (only calls SetMusicVolume when the value changes), then jmp to the previous target.
  DES  method pointer 0x4193A8 (TitleSceneDestroy, currently updater v4's wrapper) -> egg_des: if a ramp is running,
       SetMusicVolume(V) at once and stop the state machine, then jmp to the previous target.  (The intro sample
       itself cannot be stopped - PlaySample returns no handle - it simply finishes its <= 17 s, baked fade-out.)
  If music is disabled, the intro still plays (SFX channel) and no volume calls are made.

.xtut (last section) grows again: raw 0x3200 -> 0x4400, VirtualSize 0x4000 -> 0x5000, SizeOfImage 0x238000 ->
0x239000.  Code zone 0x638000..0x638400 ('IEG1' header + original bytes/targets), runtime data 0x638400..0x638440.
Revert = exact (sites, zone dropped, raw/VS/SizeOfImage restored, file truncated).  LIFO: revert this BEFORE
patch_exe_updater_title_v4 / patch_exe_title_quotes_v3 (their dry runs report OTHER/FOREIGN while this is applied).
Ship: AoWx.exe + Sfx\Zsp\INTRO_EGG.WAV (build_release_zip --add Sfx/Zsp/INTRO_EGG.WAV).

Dry-run default; --apply / --revert / --dis / --exe <copy>.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
try:
    from bakpath import bak_path, game_file
    DEFAULT_EXE = game_file("AoWx.exe")
except Exception:                                   # scratch use
    bak_path = lambda p, s: p + s
    DEFAULT_EXE = r"C:\Users\<user>\Desktop\Age of Wonders X - Claude\AoWx.exe"

BASE = 0x400000
SEC_VA = 0x634000
RAW_OLD, RAW_NEW = 0x3200, 0x4400
VS_OLD, VS_NEW = 0x4000, 0x5000
ZONE, ZONE_END = 0x638000, 0x638400
DATA = 0x638400
MAGIC = b"IEG1"
SUF = ".bak_introegg"

SITE_K = 0x63510A                          # title-quotes v3: 'inioch' -> jmp qpick
SITE_U, SITE_D = 0x4193DA, 0x4193A8        # method pointers (WindowUpdate / TitleSceneDestroy)
QON = 0x635450
IAT_SETMV, IAT_PLAY = 0x45D958, 0x45D96C
SND_SETMV, SND_GETSFX, SND_GETMUS = 0x554067A8, 0x55406858, 0x55406824
WAVNAME = b"Sfx\\xSFX\\INTRO_EGG.WAV"   # 10/21 user: moved to xSFX

TICK = 0.0008192                           # seconds per (InterruptTime >> 13) unit
T1 = int(round(1.5 / TICK))                # music fully down
T2 = int(round(13.5 / TICK))   # 10/22 user: another 0.5 s sooner (was 14.0; live exe patched in place, see .bak_introfade135)
T3 = int(round(14.5 / TICK))               # music back at V (10/22 user: 1 s return fade; was 15.5, before that 16.0)
TEND = int(round(17.2 / TICK))             # intro sample over (music-disabled case)

D_STATE, D_T0, D_V, D_LAST, D_MUS = DATA + 0, DATA + 4, DATA + 8, DATA + 0xC, DATA + 0x10


def asm(src, va):
    enc, _ = Ks(KS_ARCH_X86, KS_MODE_32).asm(src, va)
    return bytes(enc)


def build(prev_k, prev_u, prev_d):
    """zone: +0 MAGIC, +4 orig KEY rel bytes(5), +0x10 prev_k, +0x14 prev_u, +0x18 prev_d, +0x20 literal, +0x60 code"""
    lit_hdr = ZONE + 0x20
    lit = struct.pack("<iI", -1, len(WAVNAME)) + WAVNAME + b"\0"
    LIT = lit_hdr + 8
    code_va = ZONE + 0x60
    src = f"""
now:
    push edx
n_again:
    mov edx, dword ptr [0x7ffe000c]
    mov eax, dword ptr [0x7ffe0008]
    cmp edx, dword ptr [0x7ffe0010]
    jne n_again
    shrd eax, edx, 13
    pop edx
    ret

sndbase:
    mov eax, dword ptr [{IAT_SETMV:#x}]
    sub eax, {SND_SETMV:#x}
    ret

setvol:
    mov ecx, dword ptr [{IAT_SETMV:#x}]
    call ecx
    ret

egg_start:
    pushad
    cmp dword ptr [{D_STATE:#x}], 0
    jne es_out
    cmp byte ptr [{QON:#x}], 0
    je es_out
    call sndbase
    mov ebx, eax
    lea eax, [ebx + {SND_GETSFX:#x}]
    call eax
    test al, al
    je es_out
    lea eax, [ebx + {SND_GETMUS:#x}]
    call eax
    mov byte ptr [{D_MUS:#x}], al
    xor esi, esi
    mov eax, dword ptr [0x45a158]
    mov eax, dword ptr [eax]
    test eax, eax
    jz es_nov
    mov eax, dword ptr [eax+0xe8]
    test eax, eax
    jz es_nov
    mov esi, dword ptr [eax+0x148]
    jmp es_clamp
es_nov:
    mov byte ptr [{D_MUS:#x}], 0
es_clamp:
    test esi, esi
    jge es_c1
    xor esi, esi
es_c1:
    cmp esi, 100
    jle es_c2
    mov esi, 100
es_c2:
    mov dword ptr [{D_V:#x}], esi
    mov eax, {LIT:#x}
    mov ecx, dword ptr [{IAT_PLAY:#x}]
    call ecx
    call now
    mov dword ptr [{D_T0:#x}], eax
    mov dword ptr [{D_LAST:#x}], -1
    mov dword ptr [{D_STATE:#x}], 1
es_out:
    popad
    jmp {prev_k:#x}

tick:
    cmp dword ptr [{D_STATE:#x}], 0
    je t_ret
    call now
    sub eax, dword ptr [{D_T0:#x}]
    mov ebx, eax
    cmp byte ptr [{D_MUS:#x}], 0
    jne t_mus
    cmp ebx, {TEND}
    jb t_ret
    mov dword ptr [{D_STATE:#x}], 0
    ret
t_mus:
    mov esi, dword ptr [{D_V:#x}]
    cmp ebx, {T1}
    jae t_a
    mov eax, {T1}
    sub eax, ebx
    imul eax, esi
    xor edx, edx
    mov ecx, {T1}
    div ecx
    jmp t_set
t_a:
    cmp ebx, {T2}
    jae t_b
    xor eax, eax
    jmp t_set
t_b:
    cmp ebx, {T3}
    jae t_done
    mov eax, ebx
    sub eax, {T2}
    imul eax, esi
    xor edx, edx
    mov ecx, {T3 - T2}
    div ecx
    jmp t_set
t_done:
    mov dword ptr [{D_STATE:#x}], 0
    mov eax, esi
    call setvol
    mov dword ptr [{D_LAST:#x}], esi
    ret
t_set:
    cmp eax, dword ptr [{D_LAST:#x}]
    je t_ret
    mov dword ptr [{D_LAST:#x}], eax
    call setvol
t_ret:
    ret

egg_upd:
    pushad
    call tick
    popad
    jmp {prev_u:#x}

egg_des:
    pushad
    cmp dword ptr [{D_STATE:#x}], 0
    je d_out
    mov dword ptr [{D_STATE:#x}], 0
    cmp byte ptr [{D_MUS:#x}], 0
    je d_out
    mov eax, dword ptr [{D_V:#x}]
    call setvol
d_out:
    popad
    jmp {prev_d:#x}
"""
    code = asm(src, code_va)
    labels = {}
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    for name in ("now", "egg_start", "tick", "egg_upd", "egg_des"):
        enc, _ = ks.asm(src + f"\nlookup_{name}:\n    mov eax, {name}\n", code_va)
        labels[name] = struct.unpack_from("<I", bytes(enc), len(bytes(enc)) - 4)[0]
    z = bytearray(ZONE_END - ZONE)
    z[0:4] = MAGIC
    struct.pack_into("<III", z, 0x10, prev_k, prev_u, prev_d)
    z[lit_hdr - ZONE:lit_hdr - ZONE + len(lit)] = lit
    assert code_va + len(code) <= ZONE_END, hex(len(code))
    z[code_va - ZONE:code_va - ZONE + len(code)] = code
    return bytes(z), labels, len(code)


def sections(d):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    n = struct.unpack_from("<H", d, e + 6)[0]; opt = struct.unpack_from("<H", d, e + 20)[0]
    tbl = e + 24 + opt; secs = []
    for i in range(n):
        h = tbl + 40 * i
        vs, va, rs, ro = struct.unpack_from("<IIII", d, h + 8)
        secs.append(dict(name=d[h:h + 8].rstrip(b"\0"), vs=vs, va=va, rsz=rs, raw=ro, hdr=h))
    return e, secs


def off(secs, va):
    for s in secs:
        if s["va"] <= va - BASE < s["va"] + s["rsz"]:
            return s["raw"] + va - BASE - s["va"]
    raise ValueError(hex(va))


def relocs(d):
    import pefile
    pe = pefile.PE(data=bytes(d), fast_load=True)
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_BASERELOC"]])
    out = set()
    for b in getattr(pe, "DIRECTORY_ENTRY_BASERELOC", []):
        for en in b.entries:
            if en.type: out.add(en.rva + BASE)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=DEFAULT_EXE)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    d = bytearray(open(a.exe, "rb").read())
    e, secs = sections(d)
    sec = secs[-1]
    soi_off = e + 24 + 56
    soi = struct.unpack_from("<I", d, soi_off)[0]
    if sec["name"] != b".xtut" or sec["va"] + BASE != SEC_VA:
        print("ABORT: .xtut is not the last section"); return 1
    applied = sec["rsz"] == RAW_NEW and bytes(d[off(secs, ZONE):off(secs, ZONE) + 4]) == MAGIC
    ko = off(secs, SITE_K)
    kb = bytes(d[ko:ko + 5])
    if kb[0] != 0xE9:
        print("ABORT: key site %#x is not a jmp (title-quotes v3 missing?)" % SITE_K); return 1
    k_tgt = (SITE_K + 5 + struct.unpack_from("<i", kb, 1)[0]) & 0xFFFFFFFF
    u_cur = struct.unpack_from("<I", d, off(secs, SITE_U))[0]
    d_cur = struct.unpack_from("<I", d, off(secs, SITE_D))[0]

    if applied:
        zo = off(secs, ZONE)
        prev_k, prev_u, prev_d = struct.unpack_from("<III", d, zo + 0x10)
        blob, lab, clen = build(prev_k, prev_u, prev_d)
        ok = (bytes(d[zo:zo + len(blob)]) == blob and k_tgt == lab["egg_start"] and u_cur == lab["egg_upd"]
              and d_cur == lab["egg_des"])
        print("%s\n  state: applied (%s) | key -> %#x upd -> %#x des -> %#x | prev %#x/%#x/%#x"
              % (a.exe, "consistent" if ok else "INCONSISTENT", k_tgt, u_cur, d_cur, prev_k, prev_u, prev_d))
        if not a.revert:
            print("already applied" if ok else "ABORT: inconsistent state"); return 0 if ok else 1
        if not ok:
            print("ABORT: cannot revert an inconsistent install"); return 1
        struct.pack_into("<i", d, ko + 1, prev_k - (SITE_K + 5))
        struct.pack_into("<I", d, off(secs, SITE_U), prev_u)
        struct.pack_into("<I", d, off(secs, SITE_D), prev_d)
        struct.pack_into("<I", d, sec["hdr"] + 8, VS_OLD)
        struct.pack_into("<I", d, sec["hdr"] + 16, RAW_OLD)
        struct.pack_into("<I", d, soi_off, SEC_VA - BASE + VS_OLD)
        d = d[:sec["raw"] + RAW_OLD]
        with open(a.exe, "wb") as f:
            f.write(d)
        print("reverted (raw %#x, VS %#x, SizeOfImage %#x)" % (RAW_OLD, VS_OLD, SEC_VA - BASE + VS_OLD)); return 0

    if a.revert:
        print("not applied - nothing to revert"); return 0
    # vanilla-for-us state checks
    want = (sec["rsz"] == RAW_OLD and sec["vs"] == VS_OLD and soi == SEC_VA - BASE + VS_OLD
            and len(d) == sec["raw"] + RAW_OLD)
    rl = relocs(d)
    bad = [hex(r) for r in rl if SITE_K - 3 <= r < SITE_K + 5]
    blob, lab, clen = build(k_tgt, u_cur, d_cur)
    print("%s\n  .xtut raw %#x VS %#x SizeOfImage %#x filelen %#x (%s) | key jmp -> %#x | upd %#x | des %#x | "
          "code %d B @%#x | relocs at key site: %s"
          % (a.exe, sec["rsz"], sec["vs"], soi, len(d), "ok" if want else "UNEXPECTED", k_tgt, u_cur, d_cur, clen,
             ZONE + 0x60, bad or "none"))
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        for i in md.disasm(blob[0x60:0x60 + clen], ZONE + 0x60):
            print("   %08x  %s %s" % (i.address, i.mnemonic, i.op_str))
    if not want or bad or not (SEC_VA <= k_tgt < SEC_VA + VS_OLD) or not (SEC_VA <= u_cur < SEC_VA + VS_OLD) \
            or not (SEC_VA <= d_cur < SEC_VA + VS_OLD):
        print("ABORT: unexpected layout (need title-quotes v3 + updater-title v4 applied, nothing after .xtut)")
        return 1
    if not a.apply:
        print("Dry run OK - rerun with --apply"); return 0
    bp = bak_path(a.exe, SUF)
    if not os.path.exists(bp):
        shutil.copy2(a.exe, bp); print("backup -> " + bp)
    d += bytes(RAW_NEW - RAW_OLD)
    struct.pack_into("<I", d, sec["hdr"] + 8, VS_NEW)
    struct.pack_into("<I", d, sec["hdr"] + 16, RAW_NEW)
    struct.pack_into("<I", d, soi_off, SEC_VA - BASE + VS_NEW)
    e2, secs2 = sections(d)
    zo = off(secs2, ZONE)
    d[zo:zo + len(blob)] = blob
    struct.pack_into("<i", d, ko + 1, lab["egg_start"] - (SITE_K + 5))
    struct.pack_into("<I", d, off(secs2, SITE_U), lab["egg_upd"])
    struct.pack_into("<I", d, off(secs2, SITE_D), lab["egg_des"])
    with open(a.exe, "wb") as f:
        f.write(d)
    chk = open(a.exe, "rb").read()
    assert chk[zo:zo + 4] == MAGIC
    print("Written and verified: 'inioch' crossfades the title music into Sfx\\xSFX\\INTRO_EGG.WAV.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
