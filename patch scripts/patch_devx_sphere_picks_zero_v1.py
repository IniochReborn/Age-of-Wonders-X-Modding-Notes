#!/usr/bin/env python3
r"""
Editor (AoWDevX) Map Settings: "Sphere picks" may be 0 as well as 3 / 5 / 7 (2026-10-18).

Where the option lives: AoWDevX.exe TMapSettingsDlg (Restrictions box) "Sphere picks:" = VCLADDON TSpin
MaxSpherePicksEdit (form field +0x24C), DFM Increment 2 / MinValue 3 / MaxValue 7 / EditorEnabled False.
The dialog loads it from the map dword [map+0xEC] (0x422BA4 -> TSpin.SetValue) and stores TSpin.GetValue back
(0x422E1B -> 0x422E2E).  The game reads that byte at the start (AoWEPACK msg 0x20020005 @0x5578B32B:
TLeader.SetSpherePicksMax(leader, [map+0xEC])), which trims the leader's spheres to the max (count >= max ->
delete last) and CanAddSphere refuses at count >= max - so 0 = every leader starts with no spheres and can't add
any.  No 3..7 validation exists in the game; the AoWxGen generator and the in-game setup have no such option.

Patch (two files, each byte-exact revert of only the bytes written):
  1. AoWDevX.exe  - TMapSettingsDlg DFM: MinValue 3 -> 0 (vaInt8 `02 03` -> `02 00`).
  2. Vcladdon.dpl - TSpin.CheckValue tail @0x403709 (`mov eax,ecx / pop ebx / ret` + lea padding, no relocs)
     -> jmp cave @0x414710 (CODE raw slack, VirtualSize 0x13710 -> 0x13800, same page): for a spin with
     Increment 2 / Min 0 / Max 7 (only MaxSpherePicksEdit has that in AoWDevX/ILToolsP/SoundP) the clamped
     value 1 -> 0 and 2 -> 3, so the arrows step 7 5 3 0 / 0 3 5 7.  Every other spin returns unchanged.
     Position-independent (rel32 only).  Vcladdon is used only by the editor tools, not by AoWx.exe.
Backups <game>\backup\AoWDevX.exe.bak_spheres0 / Vcladdon.dpl.bak_spheres0.  Dry-run default; --apply; --revert.
"""
import argparse, os, shutil, struct, sys
from bakpath import game_file, bak_path

EXE = game_file("AoWDevX.exe")
DPL = game_file("Vcladdon.dpl")
BAK = ".bak_spheres0"

DFM_KEY = b"\x05TSpin\x12MaxSpherePicksEdit"   # DFM object header (the bare name is also in the field table)
MIN_OLD, MIN_NEW = b"\x08MinValue\x02\x03", b"\x08MinValue\x02\x00"

SITE_RVA, CAVE_RVA = 0x3709, 0x14710
SITE_OLD = bytes.fromhex("8bc15bc38d")
VS_OLD, VS_NEW = 0x13710, 0x13800


def cave_bytes():
    # eax = TSpin self, ecx = clamped value, [esp] = saved ebx (CheckValue's push ebx)
    c = bytearray()
    c += bytes.fromhex("83b83801000002")       # cmp dword [eax+0x138],2   Increment
    c += bytes.fromhex("7523")                 # jne done
    c += bytes.fromhex("83b83001000000")       # cmp dword [eax+0x130],0   MinValue
    c += bytes.fromhex("751a")                 # jne done
    c += bytes.fromhex("83b83401000007")       # cmp dword [eax+0x134],7   MaxValue
    c += bytes.fromhex("7511")                 # jne done
    c += bytes.fromhex("83f901")               # cmp ecx,1
    c += bytes.fromhex("7502")                 # jne c2
    c += bytes.fromhex("31c9")                 # xor ecx,ecx
    c += bytes.fromhex("83f902")               # c2: cmp ecx,2
    c += bytes.fromhex("7505")                 # jne done
    c += bytes.fromhex("b903000000")           # mov ecx,3
    c += bytes.fromhex("8bc15bc3")             # done: mov eax,ecx / pop ebx / ret
    return bytes(c)


def pe_info(d):
    e = struct.unpack_from("<I", d, 0x3C)[0]; n = struct.unpack_from("<H", d, e + 6)[0]
    sec = e + 24 + struct.unpack_from("<H", d, e + 20)[0]
    out = []
    for i in range(n):
        h = sec + 40 * i
        out.append((d[h:h + 8].rstrip(b"\0"), h, *struct.unpack_from("<IIII", d, h + 8)))
    return out


def rva2off(d, rva):
    for name, h, vs, va, rs, ro in pe_info(d):
        if va <= rva < va + max(vs, rs):
            return ro + rva - va
    raise ValueError(hex(rva))


def relocs(d):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    rva, size = struct.unpack_from("<II", d, e + 24 + 96 + 5 * 8)
    out = set()
    if not rva:
        return out
    o = rva2off(d, rva); end = o + size
    while o < end:
        page, bs = struct.unpack_from("<II", d, o)
        if bs < 8:
            break
        for k in range((bs - 8) // 2):
            w = struct.unpack_from("<H", d, o + 8 + 2 * k)[0]
            if w >> 12:
                out.add(page + (w & 0xFFF))
        o += bs
    return out


def jmp(frm, to):
    return b"\xe9" + struct.pack("<i", to - (frm + 5))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    a = ap.parse_args()
    ex = bytearray(open(EXE, "rb").read()); dp = bytearray(open(DPL, "rb").read())

    # --- AoWDevX DFM
    k = ex.find(DFM_KEY); assert k > 0 and ex.find(DFM_KEY, k + 1) < 0, "MaxSpherePicksEdit DFM not unique"
    seg = bytes(ex[k:k + 160]); mo = seg.find(MIN_OLD); mn = seg.find(MIN_NEW)
    dfm_state = "vanilla" if mo >= 0 else ("patched" if mn >= 0 else "UNKNOWN")
    dfm_off = k + (mo if mo >= 0 else mn) + len(MIN_OLD) - 1
    # --- Vcladdon
    secs = pe_info(dp); code = [s for s in secs if s[0] == b"CODE"][0]
    so = rva2off(dp, SITE_RVA); co = rva2off(dp, CAVE_RVA); cv = cave_bytes()
    cur = bytes(dp[so:so + 5])
    if cur == SITE_OLD:
        site_state = "vanilla"
    elif cur == jmp(SITE_RVA, CAVE_RVA) and bytes(dp[co:co + len(cv)]) == cv:
        site_state = "patched"
    else:
        site_state = "UNKNOWN"
    rl = relocs(dp)
    bad = [hex(r) for r in rl if SITE_RVA <= r < SITE_RVA + 5 or CAVE_RVA <= r < CAVE_RVA + len(cv)]
    cave_free = not any(dp[co:co + len(cv)])
    print(f"AoWDevX TMapSettingsDlg MaxSpherePicksEdit MinValue: {dfm_state} (file {dfm_off:#x})")
    print(f"Vcladdon TSpin.CheckValue tail {0x400000 + SITE_RVA:#x}: {site_state} | cave {0x400000 + CAVE_RVA:#x} "
          f"{'zero' if cave_free else 'ours/used'} ({len(cv)} B) | CODE VS {code[2]:#x} | relocs {bad or 'none'}")
    assert not bad, "relocation under patch bytes"
    assert CAVE_RVA + len(cv) <= code[3] + code[4], "cave beyond CODE raw data"

    vs_off = code[1] + 8
    if a.revert:
        if dfm_state == "patched":
            ex[dfm_off] = 0x03
        if site_state == "patched":
            dp[so:so + 5] = SITE_OLD; dp[co:co + len(cv)] = b"\0" * len(cv)
            if struct.unpack_from("<I", dp, vs_off)[0] == VS_NEW:
                struct.pack_into("<I", dp, vs_off, VS_OLD)
        for p, b in ((EXE, ex), (DPL, dp)):
            with open(p, "r+b") as f:
                f.seek(0); f.write(b)
        print("reverted"); return 0
    if "UNKNOWN" in (dfm_state, site_state):
        print("unexpected state - inspect first"); return 1
    if dfm_state == site_state == "patched":
        print("ALREADY APPLIED"); return 0
    if not a.apply:
        print("dry run OK - nothing written (use --apply)"); return 0
    if site_state == "vanilla":
        assert cave_free, "cave not zero"
    for p in (EXE, DPL):
        b = bak_path(p, BAK, create=True)
        if not os.path.exists(b):
            shutil.copy2(p, b); print("backup ->", b)
    ex[dfm_off] = 0x00
    if site_state == "vanilla":
        dp[co:co + len(cv)] = cv; dp[so:so + 5] = jmp(SITE_RVA, CAVE_RVA)
        if struct.unpack_from("<I", dp, vs_off)[0] < VS_NEW:
            struct.pack_into("<I", dp, vs_off, VS_NEW)
    for p, b in ((EXE, ex), (DPL, dp)):
        with open(p, "r+b") as f:
            f.seek(0); f.write(b)
    print("applied: Map Settings -> Sphere picks steps 0 / 3 / 5 / 7 (close + reopen AoWDevX)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
