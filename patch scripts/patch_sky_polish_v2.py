#!/usr/bin/env python3
r"""
Sky polish v2 (2026-10-31) - supersedes patch_sky_polish_v1 (revert v1 first; this one re-applies all of it).

User after v1: "combat map for clear sky is the same as sky, it should look like overworld. also they both have
terrible animation in combat map ... animation on combat map should be same as overworld. also, the sky/clear sky
cloud animation pattern is a bit too small/repetitive ... lets also add a very subtle evil/magical animation to
chasm ... give the stars a very subtle twinkling animation ... i cant place clear sky on firmament level without
first placing chasm, then overwriting it with clear sky".

v1 parts kept (from patch_sky_polish_v1): editor Clear Sky buttons + glyphs, Release.hss Sky re-art + Clear Sky
records 0x5A1B0001..4, HSEPack brush flag / GetRndResource / Place filters.
New in v2:
1. AoWEPACK overlay (sky_clouds_overlay_asm): clouds sampled at 1/2 and 1/4 resolution (pattern 4x larger),
   stronger star twinkle (brief dip to ~1/4, per-star phase, 44+ brightness = star), Chasm (terrain 0xB, 15 tile
   tables) gets faint violet veins (ridge of the cloud field) with a slow travelling pulse; a second entry 'combat'
   (no Firmament surface, no global-map check).  Zone 0x558CB000..0x558DAEC0 + texture 0x5588C000..0x5589C000.
2. AoWTCPCK (zone 0x45B800 'SKC3', PIC):
     TAoWCombatMap.DrawDynamicScene 0x41BFB8 -> calls the overlay's combat entry (AoWEPACK delta via the
       AoWHSMap import 0x46E8D4), then the original prologue -> combat Sky/Clear/Chasm animate like the map;
     battle setup 0x424700 (centre sector, [ebp-0x18]==0): the centre map field's hexagon resource RID>>16 ==
       0x5A1B -> HSEPack Clear flag 1, else 0 (HSE delta via the TMapLevel.GetField import 0x46E238) -> the combat
       ground's terrain-0xE picks choose the Clear combat hexagon.
3. comb_res.pfs: child 583 = Sky combat hexagon (581) clone, RID 0x5A1B0101 ('clear'), CLRHEX00/CLRANM00.ILB.
4. ILBs: SKYHEX00 (base = Sky tiles), CLRHEX00 (new: Clear tiles + light-blue edges), SKYANM00/CLRANM00/CHSANM00
   = WaterAnm frames reduced to one pixel at 1 % (the overlay draws the animation now).
5. HSEPack TAbstractHexagon.ChangeTerrain 0x5560A562 (`cmp al,[esi]; je skip` = same terrain -> nothing):
   for terrain 0xE it also re-picks when the hexagon's Clear-ness differs from the brush flag -> Clear Sky paints
   straight over Sky (and Sky over Clear Sky).
Backups .bak_skypolish2.  ⚠ new files CLRHEX00.ILB / CLRANM00.ILB -> release --add.
Dry-run default; --apply; --revert.
"""
import os, shutil, struct, sys, zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "modding tools"))
from bakpath import bak_path, game_dir, game_file  # noqa: E402
import sky_clouds_art as ART  # noqa: E402
import sky_clouds_overlay_asm as OV  # noqa: E402
import patch_sky_polish_v1 as V1  # noqa: E402
import build_sky_chasm_combat_v1 as SC  # noqa: E402
import build_rndhex_previews_hss_v1 as H  # noqa: E402

TAG = ".bak_skypolish2"
EPK, EBASE = V1.EPK, V1.EBASE
HSE, HBASE = V1.HSE, V1.HBASE
TC, TBASE = game_file("AoWTCPCK.dll"), 0x400000
PFS = SC.PFS
IMG = lambda n: game_file(os.path.join("Images", n))  # noqa: E731
ILB_NAMES = ["SKYHEX00.ILB", "CLRHEX00.ILB", "SKYANM00.ILB", "CLRANM00.ILB", "CHSANM00.ILB"]
NEW_FILES = ["CLRHEX00.ILB", "CLRANM00.ILB"]

# ---- HSEPack: v1 cave + ChangeTerrain bypass ------------------------------------------------------------------------
CT, CT_ORIG, CT_GO, CT_SKIP = 0x5560A562, bytes.fromhex("3a060f84a9000000"), 0x5560A56A, 0x5560A613


def hse_src():
    s = V1.hse_src()
    tail = s.index("    .long sct")
    return s[:tail] + f"""
    ct:
        cmp al, byte ptr [esi]
        jne ct_go
        cmp al, 0xe
        jne ct_skip
        mov ecx, dword ptr [ebx + 8]
        mov ecx, dword ptr [ecx + 0xc]
        shr ecx, 16
        xor edx, edx
        cmp ecx, {V1.CLEAR_HI:#x}
        sete dl
        call ct1
    ct1:
        pop ecx
        sub ecx, ct1
        movzx ecx, byte ptr [ecx + {V1.FLAG:#x}]
        cmp ecx, edx
        jne ct_go
    ct_skip:
        jmp {CT_SKIP:#x}
    ct_go:
        jmp {CT_GO:#x}
""" + s[tail:] + "    .long ct\n"


def hse_patches():
    code = OV.asm(hse_src(), V1.HZONE + 0x10)
    ents = dict(zip(("sct", "scl", "grr", "pick", "ct"), struct.unpack("<5I", code[-20:])))
    code = code[:-20]
    assert 0x10 + len(code) <= V1.HZONE_END - V1.HZONE
    z = V1.HMAGIC + bytes(12) + code
    jmp = lambda at, to, n: b"\xe9" + struct.pack("<i", to - (at + 5)) + b"\x90" * (n - 5)  # noqa: E731
    plf_new = (b"\x8b\xc6" + b"\x0f\xbe\x55\x08" + b"\xe8" + struct.pack("<i", ents["pick"] - (V1.PLF + 6 + 5)) +
               b"\x89\x45\xf0" + b"\x90" * 3)
    vanilla_plf = bytes.fromhex("8b4608e8") + struct.pack("<i", V1.RANDOM - (V1.PLF + 8)) + \
        bytes.fromhex("8b56048b04828945f0")
    return [(V1.SCT, V1.SC_ORIG, jmp(V1.SCT, ents["sct"], 6)), (V1.SCL, V1.SC_ORIG, jmp(V1.SCL, ents["scl"], 6)),
            (V1.GRR, V1.GRR_ORIG, jmp(V1.GRR, ents["grr"], 5)), (V1.PLF, vanilla_plf, plf_new),
            (CT, CT_ORIG, jmp(CT, ents["ct"], 8)), (V1.HZONE, bytes(len(z)), z)]


# ---- AoWEPACK ------------------------------------------------------------------------------------------------------
def epk_patches(gd):
    z, tex, ents = OV.blob(gd)
    old = b"\xe9" + struct.pack("<i", OV.HOOK_ZIG - (OV.HOOK + 5)) + b"\x90"
    new = b"\xe9" + struct.pack("<i", ents["main"] - (OV.HOOK + 5)) + b"\x90"
    return [(OV.HOOK, old, new), (OV.ZONE, bytes(len(z)), z), (OV.TEX, bytes(len(tex)), tex)], ents


# ---- AoWTCPCK ------------------------------------------------------------------------------------------------------
TZONE, TZONE_END, TMAGIC = 0x45B800, 0x45BA00, b"SKC3"
DDS, DDS_ORIG = 0x41BFB8, bytes.fromhex("558bec83c4f8")
FLD, FLD_ORIG = 0x424700, bytes.fromhex("8a40148b55e8")
TC_IAT_AOWHSMAP, TC_IAT_GETFIELD, HSE_GETFIELD = 0x46E8D4, 0x46E238, 0x556087B8


def tc_src(combat_entry):
    return f"""
    dds:
        pushal
        call t1
    t1:
        pop ebx
        sub ebx, t1
        mov ecx, dword ptr [ebx + {TC_IAT_AOWHSMAP:#x}]
        sub ecx, {OV.GLOBAL_MAP:#x}
        add ecx, {combat_entry:#x}
        call ecx
        popal
        push ebp
        mov ebp, esp
        add esp, -8
        jmp {DDS + 6:#x}
    fld:
        cmp dword ptr [ebp - 0x18], 0
        jne fl_out
        pushal
        xor esi, esi
        movzx ecx, byte ptr [eax + 0xd]
        mov edx, dword ptr [eax + 8]
    fl_loop:
        test ecx, ecx
        je fl_set
        dec ecx
        mov ebx, dword ptr [edx + ecx*4]
        test byte ptr [ebx + 0xc], 2
        je fl_loop
        mov ebx, dword ptr [ebx + 8]
        mov ebx, dword ptr [ebx + 0xc]
        shr ebx, 16
        cmp ebx, {V1.CLEAR_HI:#x}
        jne fl_loop
        mov esi, 1
    fl_set:
        call t2
    t2:
        pop ebx
        sub ebx, t2
        mov ecx, dword ptr [ebx + {TC_IAT_GETFIELD:#x}]
        sub ecx, {HSE_GETFIELD:#x}
        mov eax, esi
        mov byte ptr [ecx + {V1.FLAG:#x}], al
        popal
    fl_out:
        mov al, byte ptr [eax + 0x14]
        mov edx, dword ptr [ebp - 0x18]
        jmp {FLD + 6:#x}
    .long dds
    .long fld
"""


def tc_patches(combat_entry):
    code = OV.asm(tc_src(combat_entry), TZONE + 0x10)
    e = dict(zip(("dds", "fld"), struct.unpack("<2I", code[-8:])))
    code = code[:-8]
    assert 0x10 + len(code) <= TZONE_END - TZONE
    z = TMAGIC + bytes(12) + code
    jmp = lambda at, to: b"\xe9" + struct.pack("<i", to - (at + 5)) + b"\x90"  # noqa: E731
    return [(DDS, DDS_ORIG, jmp(DDS, e["dds"])), (FLD, FLD_ORIG, jmp(FLD, e["fld"])), (TZONE, bytes(len(z)), z)]


# ---- comb_res.pfs: Clear Sky combat hexagon ---------------------------------------------------------------------------
CLR_CHILD, CLR_RID, SKY_CHILD = 583, 0x5A1B0101, 581


def pfs_build(b):
    assert struct.unpack("<I", b[-4:])[0] == zlib.crc32(b[4:-4]) & 0xFFFFFFFF, "comb_res CRC"
    ce, cbase, recs = SC.pfs_records(b)
    if any(e[0] == CLR_CHILD for e in ce):
        return None
    assert max(e[0] for e in ce) == CLR_CHILD - 1, max(e[0] for e in ce)
    s, t = recs[SKY_CHILD]
    sky = b[s:t]
    fo, td = H.fields(sky)
    assert struct.unpack_from("<I", sky, td + fo[1])[0] == 0xAA0E01 and sky[td + fo[7] + 4] == 0x0E
    assert sky.count(b"SKYHEX00.ILB") >= 1 and sky.count(b"SKYANM00.ILB") >= 1
    r = bytearray(sky)
    struct.pack_into("<I", r, td + fo[1], CLR_RID)
    r = bytes(r).replace(b"SKYHEX00.ILB", b"CLRHEX00.ILB").replace(b"SKYANM00.ILB", b"CLRANM00.ILB")
    region = bytearray(b[cbase:len(b) - 4])
    ce.append([CLR_CHILD, len(region), "d"])
    region += r
    out = bytearray(b[:0xD]) + H.enc_table(ce) + region
    out += struct.pack("<I", zlib.crc32(bytes(out[4:])) & 0xFFFFFFFF)
    ce2, cb2, recs2 = SC.pfs_records(bytes(out))
    s2, t2 = recs2[CLR_CHILD]
    assert out[s2:t2] == r and out[recs2[SKY_CHILD][0]:recs2[SKY_CHILD][1]] == sky
    return bytes(out)


# ---- main ----------------------------------------------------------------------------------------------------------
def main():
    import pefile
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    gd = game_dir()
    files = [EPK, HSE, TC, V1.DEVX, V1.HSS, PFS] + [IMG(n) for n in ILB_NAMES if n not in NEW_FILES]
    if revert:
        if V1.busy():
            print("game/editor running - close it first"); return 1
        for f in files:
            b = bak_path(f, TAG)
            if os.path.exists(b):
                shutil.copy2(b, f); print("restored", b)
        for n in NEW_FILES:
            if os.path.exists(IMG(n)):
                os.remove(IMG(n)); print("removed", IMG(n))
        return 0
    report, todo = [], []
    # byte-patched binaries
    epk, ents = epk_patches(gd)
    for name, path, base, P in (("AoWEPACK", EPK, EBASE, epk), ("HSEPack", HSE, HBASE, hse_patches()),
                                ("AoWTCPCK", TC, TBASE, tc_patches(ents["combat"]))):
        d = open(path, "rb").read(); pe = pefile.PE(data=d)
        st, bad = V1.state(d, pe, base, P)
        report.append("%s %s relocs %s" % (name, st, bad or "none"))
        if "OTHER" in st or bad or len(set(st)) != 1:
            print("\n".join(report))
            print("ABORT (%s) - revert patch_sky_polish_v1 first if it is applied" % name); return 1
        if st[0] == "vanilla":
            todo.append(("bytes", (path, base, P)))
    d = open(HSE, "rb").read(); pe = pefile.PE(data=d)
    fo = pe.get_offset_from_rva(V1.FLAG - HBASE)
    if any(d[fo:fo + 16]):
        print("ABORT: HSEPack flag slack not zero"); return 1
    # editor + Release.hss (v1 builders)
    nd, info = V1.devx_build(open(V1.DEVX, "rb").read())
    report.append("AoWDevX %s" % ("already applied" if nd is None else info))
    if nd is not None:
        todo.append(("file", (V1.DEVX, nd)))
    b = open(V1.HSS, "rb").read()
    nb = V1.hss_build(b)
    report.append("Release.hss %s" % ("already applied" if nb is None else "%d -> %d B" % (len(b), len(nb))))
    if nb is not None:
        todo.append(("file", (V1.HSS, nb)))
    # comb_res
    pb = open(PFS, "rb").read()
    pn = pfs_build(pb)
    report.append("comb_res.pfs %s" % ("already applied" if pn is None else "+child %d (%d -> %d B)"
                                       % (CLR_CHILD, len(pb), len(pn))))
    if pn is not None:
        todo.append(("file", (PFS, pn)))
    # ILBs
    blobs = ART.combat_ilbs(gd)
    for n in ILB_NAMES:
        raw = blobs["Images\\" + n]
        p = IMG(n)
        same = os.path.exists(p) and open(p, "rb").read() == raw
        report.append("Images\\%s %s" % (n, "already applied" if same else ("new" if not os.path.exists(p) else
                                                                           "rebuild") + " (%d B)" % len(raw)))
        if not same:
            todo.append(("file", (p, raw)))
    print("\n".join(report))
    if not todo:
        print("already applied"); return 0
    if not apply:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if V1.busy():
        print("game/editor running - close it first"); return 1
    for kind, x in todo:
        path = x[0]
        if os.path.exists(path):
            bk = bak_path(path, TAG)
            if not os.path.exists(bk):
                shutil.copy2(path, bk)
        if kind == "bytes":
            V1.write_bytes(*x[:2], x[2], False)
        else:
            with open(path, "wb" if not os.path.exists(path) else "r+b") as fh:
                fh.write(x[1]); fh.truncate()
            assert open(path, "rb").read() == x[1]
        print("written", path)
    print("written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
