#!/usr/bin/env python3
r"""
Teleporter terrain variants v1 (2026-11-06): ICE, LAVA and FLOATING (Sky / Clear Sky / Chasm) teleporters, on top of
patch_teleport_water_v1..v3 (padless teleporters; image slot = GetTerrainTypeImage(terrain) = terrain id).

User: "we added water teleporters but i think we should also add ice teleporters for when the water theyre on gets
frozen.... lets also add lava teleporters. i also want to add teleporters for sky/clear sky/chasm however these should
have different GFX because they would be floating. and maybe slowly rotating/levitating?"

Before this, records 201 (surface teleporter) / 218 (underground) had NO image in slots 6 (Ice), 9 (Lava), 11 (Chasm),
13 (Cave Ice) and 14 (Sky; Clear Sky is the same terrain 0xE) -> a teleporter whose water froze had no map image.
  1. Images\STR_TELX.ILB (NEW, art = tele_variants_art.py):
       ice base 0 / 1 (surface / underground stones), ice glints 10.. / 110..  (ICE_N)
       lava base 2 / 3, lava rim+ember frames 40.. / 140..                     (LAVA_N)
       floating sky frames 200.., sky glow 300.., chasm frames 400.., chasm glow 500..   (FLOAT_N, 80x124 canvas;
       the glow frames are type 22 / drawMode 770 / blend 45 like the vanilla STR_TELE flames)
  2. Release.hss 201 / 218 (list grown 43 -> 55):
       slot 6 + 13 (ice): the record's slot-1 chain (base + 5 flame layers) with the base -> STR_TELX ice base, plus
                           a7 = glint layer
       slot 9 (lava):     same with the lava base, a7 = rim/ember layer
       slot 14 (sky), 11 (chasm): a1 = rotating/bobbing island frames, a2 = moving flame frames (the five fixed
                           vanilla flame layers would not follow the turning stones) - same art in both records
       side-image tags: 43-45 ice, 46-48 lava, 49-51 sky, 52-54 chasm (= the record's own top/filler border images
                           + a new BORDER portrait)
  3. Images\BORDER.ILB + 210/211 ice (surface/underground), 212/213 lava, 214 sky, 215 chasm.
  4. AoWEPACK: TTeleport VMT 0x557A4A28 +0x138/+0x13C/+0x140 move from the TWB2 caves (water only) to cave 0x558E1000
     'TWB3': image slot [self+0x14] 0/10 -> tags 40.., 6/13 -> 43.., 9 -> 46.., 14 -> 49.., 11 -> 52..; a record
     without the tag (Divine Gates) falls back to the TStructure getter.  PIC (relative calls only).
v2 11/06 (user: lava/ice base effects more subtle like water; floating: no island, pillar bottoms extended
naturally, glow out of sync with the turning pillars): tele_variants_art v2 + both floating layers b=0 (see seq()).
v3 11/07 (user: spin slower; small pieces float at the big stones' mid height; ice base without dots; side images:
water/ice/lava ground in perspective (no flat strip), sky = full pillars, chasm = all-purple void): FLOAT_N 120 x
FLOAT_HOLD 3, image ids moved (ice glints 1000../1100.., floating 2000/2200/2400/2600..), BORDER 208/209 (water
portraits from patch_teleport_water_v1) are rebuilt here too (the .bak_teleterrain BORDER keeps the v1 ones).
Re-running rebuilds STR_TELX / BORDER 210-215 / the hss slots in place.
Backups .bak_teleterrain (Release.hss, BORDER.ILB, AoWEPACK.dll); STR_TELX.ILB removed by --revert.
⚠ NEW file Images\STR_TELX.ILB -> release --add.  Dry-run default; --apply; --revert.
"""
import copy, os, shutil, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "modding tools"))
from bakpath import bak_path, game_file  # noqa: E402
from aowxlib import ilb  # noqa: E402
import build_rndhex_previews_hss_v1 as H  # noqa: E402
import imgseq as Q  # noqa: E402
import patch_sky_polish_v1 as SP  # noqa: E402
import patch_sanctuary_raze_v1 as R  # noqa: E402
import sky_clouds_overlay_asm as OV  # noqa: E402
import patch_teleport_water_v1 as V1  # noqa: E402
import patch_teleport_water_v2 as V2  # noqa: E402
import tele_variants_art as ART  # noqa: E402

TAG = ".bak_teleterrain"
HSS, BORDER = V1.HSS, V1.BORDER
TELX = game_file(os.path.join("Images", "STR_TELX.ILB"))
ILBNAME = "STR_TELX.ILB"
UNDER = {201: False, 218: True}
# STR_TELX ids
ICE_BASE, ICE_GL = {False: 0, True: 1}, {False: 1000, True: 1100}          # v3: ICE_N 32 -> moved off 10../110..
LAVA_BASE, LAVA_AN = {False: 2, True: 3}, {False: 40, True: 140}
FLOAT_FR, FLOAT_GL = {"sky": 2000, "chasm": 2800}, {"sky": 2400, "chasm": 3200}   # v6: FLOAT_N 360
# BORDER portraits and side tags
PORTRAIT = {("ice", False): 210, ("ice", True): 211, ("lava", False): 212, ("lava", True): 213,
            ("sky", None): 214, ("chasm", None): 215}
TAGS = {"ice": 43, "lava": 46, "sky": 49, "chasm": 52}
SLOTS = {"ice": (6, 13), "lava": (9,), "sky": (14,), "chasm": (11,)}
LIST_LEN = 55
CAVE, CAVE_END, MAGIC = 0x558E1000, 0x558E1200, b"TWB3"


# ------------------------------------------------------------------------------------------------------------- art
def build_telx(gd):
    from PIL import Image
    raw = open(os.path.join(gd, "Images", "STR_TELE.ILB"), "rb").read()
    src = {im.id: im for im in ilb.read(raw).images}
    tpl, gtpl = src[0].primary, src[6].primary            # 17/256 stones, 22/770/45 flame
    lib = ilb.read(raw); lib.images = []

    def add(iid, arr, glow=False):
        rec = copy.deepcopy(gtpl if glow else tpl); rec["name"] = "str_telx%d.BMP" % iid
        ilb.encode_image(lib, rec, Image.fromarray(arr, "RGBA"))
        lib.images.append(ilb.Image(iid, parts=[rec]))
    for u in (False, True):
        add(ICE_BASE[u], ART.ice_base(gd, u))
        for k, fr in enumerate(ART.ice_glints(gd, u)):
            add(ICE_GL[u] + k, fr)
        add(LAVA_BASE[u], ART.lava_base(gd, u))
        for k, fr in enumerate(ART.lava_anim(gd, u)):
            add(LAVA_AN[u] + k, fr)
    for kind in ("sky", "chasm"):
        for k, fr in enumerate(ART.float_frames(gd, kind)):
            add(FLOAT_FR[kind] + k, fr)
        for k, fr in enumerate(ART.float_glow(gd, kind)):
            add(FLOAT_GL[kind] + k, fr, glow=True)
    lib.images.sort(key=lambda im: im.id)
    return ilb.write(lib)


def build_border(raw, gd):
    from PIL import Image
    lib = ilb.read(raw)
    by = {im.id: im for im in lib.images}
    want = {}
    for (kind, u), nid in PORTRAIT.items():
        if kind == "ice":
            want[nid] = ART.portrait_ice(gd, 131 if u else 41, u)
        elif kind == "lava":
            want[nid] = ART.portrait_lava(gd, 131 if u else 41, u)
        else:
            want[nid] = ART.portrait_float(gd, kind)
    want[208], want[209] = ART.portrait_water(gd, False), ART.portrait_water(gd, True)   # v3: water v1 portraits
    names = {nid: by[nid].primary["name"] for nid in want if nid in by}
    lib.images = [im for im in lib.images if im.id not in want]          # re-runs replace our own images
    for nid, arr in sorted(want.items()):
        rec = copy.deepcopy(by[41].primary); rec["name"] = names.get(nid, "B_TelepX.BMP")
        ilb.encode_image(lib, rec, Image.fromarray(arr, "RGBA"))
        lib.images.append(ilb.Image(nid, parts=[rec]))
    lib.images.sort(key=lambda im: im.id)
    out = ilb.write(lib)
    return None if out == raw else out


# ------------------------------------------------------------------------------------------------------------- hss
def chain(s):
    out = []
    while s:
        out.append(s); s = s["sub"]
    return out


def link(layers):
    for a, b in zip(layers, layers[1:]):
        a["sub"] = b
    layers[-1]["sub"] = None
    return layers[0]


def seq(tpl, a, first, n, x, y, hold):
    s = copy.deepcopy(tpl); s["sub"] = None
    # b = the sequence's frame DELAY (TImageSequence +0x18, extra ticks per frame).  v1 copied b=1 from the base layer
    # for the stones but b=0 from a flame layer for the glow -> the stones ran at half speed and the glow drifted off
    # them.  All our animated layers use b=0 (the HOLD repeats in the list set the speed).
    s.update(name=ILBNAME, a=a, b=0, frame=0, x=x, y=y, mode=4, frames=[f for f in range(first, first + n) for _ in range(hold)])
    s.setdefault("z", 0)
    return s


def ground_variant(lst, base_id, anim_first, anim_n):
    ch = [copy.deepcopy(x) for x in chain(lst[1])]
    assert len(ch) == 6 and ch[0]["a"] == 1 and ch[0]["mode"] == 4, ch
    ch[0]["name"] = ILBNAME; ch[0]["frames"] = [base_id]; ch[0]["frame"] = 0
    tpl = ch[-1]
    ch.append(seq(tpl, 7, anim_first, anim_n, ch[0]["x"], ch[0]["y"], ART.HOLD))
    ch[-1]["b"] = 0
    return link(ch)


def float_variant(lst, kind):
    ch = chain(lst[1])
    x, y = ch[0]["x"] - ART.OX, ch[0]["y"] - ART.OY
    base = seq(ch[0], 1, FLOAT_FR[kind], ART.FLOAT_N, x, y, ART.FLOAT_HOLD)
    glow = seq(ch[1], 2, FLOAT_GL[kind], ART.FLOAT_N, x, y, ART.FLOAT_HOLD)
    return link([base, glow])


def hss_build(b):
    A = H.parse(b)
    changed = {}
    for c, u in UNDER.items():
        r = bytes(A["recs"][c])
        assert struct.unpack_from("<I", r, 0)[0] == 0x20105
        fo, td = H.fields(r)
        lst = Q.parse_list(r, td + fo[9])[0]
        assert len(lst) >= 43 and lst[42] is not None, "patch_teleport_water_v1 must be applied"
        new = copy.deepcopy(lst)
        while len(new) < LIST_LEN:
            new.append(None)
        v = {"ice": ground_variant(lst, ICE_BASE[u], ICE_GL[u], ART.ICE_N),
             "lava": ground_variant(lst, LAVA_BASE[u], LAVA_AN[u], ART.LAVA_N),
             "sky": float_variant(lst, "sky"), "chasm": float_variant(lst, "chasm")}
        for kind, slots in SLOTS.items():
            for s in slots:
                assert lst[s] is None or (len(lst) > 43 and chain(lst[s])[0]["name"] == ILBNAME), (c, s)
                new[s] = copy.deepcopy(v[kind])
            t = TAGS[kind]
            new[t] = copy.deepcopy(lst[30]); new[t + 1] = copy.deepcopy(lst[31])
            new[t + 2] = copy.deepcopy(lst[32])
            new[t + 2]["frame"] = PORTRAIT[(kind, u if kind in ("ice", "lava") else None)]
        if new != lst:
            changed[c] = R.rec_with_list(r, new)
    if not changed:
        return None
    for c, v in changed.items():
        A["recs"][c] = bytearray(v)
    nb = SP.hss_rebuild(b, A)
    old = H.parse(b)["recs"]
    for c, v in H.parse(nb)["recs"].items():
        assert bytes(v) == (changed[c] if c in changed else bytes(old[c]))
    return nb


# -------------------------------------------------------------------------------------------------------- AoWEPACK
def twb2_entries():
    P = V2.epk_patches()
    return {V1.GETTERS[i][1]: struct.unpack("<I", P[i][2])[0] for i in range(3)}   # orig getter -> TWB2 cave


def epk_patches():
    twb2 = twb2_entries()
    P, at = [], CAVE + len(MAGIC)
    blob = bytearray(MAGIC)
    for i, (slot, orig, _) in enumerate(V1.GETTERS):
        sel = "\n".join(f"""
            mov edx, {base + i:#x}
            {chr(10).join(f"cmp ecx, {s:#x}" + chr(10) + "je w" for s in slots)}"""
                        for base, slots in ((40, (0, 10)), (TAGS["ice"], SLOTS["ice"]), (TAGS["lava"], SLOTS["lava"]),
                                            (TAGS["sky"], SLOTS["sky"]), (TAGS["chasm"], SLOTS["chasm"])))
        c = OV.asm(f"""
            mov ecx, dword ptr [eax + 0x14]
            {sel}
            jmp o
        w:
            push ebx
            push esi
            mov ebx, eax
            mov esi, edx
            mov eax, dword ptr [ebx + 0x8]
            mov eax, dword ptr [eax + 0x24]
            test eax, eax
            jz f
            mov edx, esi
            call {V1.LIST_FIND:#x}
            test eax, eax
            jz f
            mov eax, dword ptr [ebx + 0x8]
            mov eax, dword ptr [eax + 0x24]
            mov edx, esi
            call {V1.LIST_FIND:#x}
            call {V1.LIST_IMG:#x}
            pop esi
            pop ebx
            ret
        f:
            mov eax, ebx
            pop esi
            pop ebx
        o:
            jmp {orig:#x}
        """, at)
        P.append((V1.VMT + slot, struct.pack("<I", twb2[orig]), struct.pack("<I", at)))
        blob += c; at += len(c)
    assert CAVE + len(blob) <= CAVE_END, hex(CAVE + len(blob))
    P.append((CAVE, bytes(len(blob)), bytes(blob)))
    return P


def main():
    import pefile
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if (apply or revert) and SP.busy():
        print("game/editor running - close it first"); return 1
    d = open(SP.EPK, "rb").read(); pe = pefile.PE(data=d)
    P = epk_patches(); st, bad = SP.state(d, pe, SP.EBASE, P)
    bad = [x for x in bad if int(x, 16) not in [V1.VMT + s for s, _, _ in V1.GETTERS]]
    print("AoWEPACK %s relocs %s" % (st, bad or "none (VMT slot relocs expected)"))
    if "OTHER" in st or bad or len(set(st)) != 1:
        print("ABORT (patch_teleport_water_v2 must be applied; cave must be free)"); return 1
    if revert:
        if st[0] == "ours":
            SP.write_bytes(SP.EPK, SP.EBASE, P, True); print("reverted AoWEPACK")
        for f in (HSS, BORDER):
            bk = bak_path(f, TAG)
            if os.path.exists(bk):
                shutil.copy2(bk, f); print("restored", bk)
        if os.path.exists(TELX):
            os.remove(TELX); print("removed", TELX)
        return 0
    gd = os.path.dirname(HERE)
    nh = hss_build(open(HSS, "rb").read())
    nb = build_border(open(BORDER, "rb").read(), gd)
    nt = build_telx(gd); nt = None if os.path.exists(TELX) and open(TELX, "rb").read() == nt else nt
    files = [(HSS, nh), (BORDER, nb)]
    for f, data in files + [(TELX, nt)]:
        print(os.path.basename(f), "already applied" if data is None else "write (%d B)" % len(data))
    if all(x is None for _, x in files) and nt is None and st[0] == "ours":
        print("already applied"); return 0
    if not apply:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if st[0] == "vanilla":
        bk = bak_path(SP.EPK, TAG)
        if not os.path.exists(bk):
            shutil.copy2(SP.EPK, bk)
        SP.write_bytes(SP.EPK, SP.EBASE, P, False)
    for f, data in files:
        if data is None:
            continue
        bk = bak_path(f, TAG)
        if not os.path.exists(bk):
            shutil.copy2(f, bk)
        with open(f, "r+b") as fh:
            fh.write(data); fh.truncate()
        assert open(f, "rb").read() == data
    if nt is not None:
        with open(TELX, "wb") as fh:
            fh.write(nt)
    print("written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
