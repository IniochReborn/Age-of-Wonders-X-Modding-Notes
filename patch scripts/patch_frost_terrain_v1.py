#!/usr/bin/env python3
r"""
Frost terrain changes (2026-09-14), ported from BXL's Ziggurat with the user's own rules:

 1. ICE STORM cools lava to wasteland.  Storms.TIceStorm.ChangeStormTerrain @0x557CCED4 maps
    Water(0)->Ice(6), Ice(6)->refresh the frozen-water marker, and EVERYTHING ELSE -> Snow(3)
    through one catch-all `mov [ecx],3; jmp epilogue` at 0x557CCEF0.  That catch-all now sends
    Lava(9) to Wasteland(5); every other terrain still becomes snow, water still freezes.
    Both the Ice Storm spell and the storm an Altar of Ice fires create the same TIceStorm
    class (TIceStormSpell.CreateStorm / TAltarOfIce.CreateStorm both load class ref
    0x557CB3DC), so one hook covers both.
    ⚠ TBlastStorm.UpdateStorm re-applies ChangeStormTerrain over the WHOLE disc four times as
    the radius grows (frame counter [storm+0x10] = 8/0xC/0x12/0x16 -> radius 1/2/3/4), so a
    naive lava->wasteland would be followed by wasteland->snow on the next pass (BXL got a
    snow core inside a wasteland ring and added a random skip gate).  Here lava is converted
    only on the LAST pass (frame 0x16, radius 4, which covers the whole disc) and left alone
    on the earlier ones, so no later pass can snow it over.  No RNG, nothing else changes.

 2. FREEZE WATER becomes FREEZE TERRAIN.  GlobalTargetSpells.TFreezeWaterTE.ChangeTerrain
    @0x5579E884 only ever handled Water(0)->Ice(6), CaveWater(A)->CaveIce(D) and refreshed
    the melt timer on existing ice; everything else fell through untouched.  Hooked at
    0x5579E89B (after the "no army on the hex" gate): Lava(9)->Wasteland(5); Grass(1),
    Desert(2), Steppe(4), Wasteland(5)->Snow(3) directly (no ladder); water arm unchanged.
    Underground Dirt(C), Earth/Rock, Snow, Ice and anything else stay as they are; lava cools on
    every level (Ice Storm's lava branch is surface-only, wasteland being a surface terrain, but
    the user wants Freeze Terrain and Path of Frost to work underground).  The land changes are
    PERMANENT: TFreezeWaterTE.TerrainChanged only mints a TFrozenWaterHS melt marker when the
    new terrain is ice, so only the ice thaws (as before).
    The two water-only target gates (TFreezeWater.ValidTargetMapF @0x5579EBA0 and
    ValidTargetSelectionMapF @0x5579EBF0, 15 B each) are widened so any explored hex without
    a structure or army can be targeted -- both must move together (BXL: patch one and the
    spell is either uncastable or untargetable).
    Name: Dict\ResStr.mld row 'Freeze Water' gets English 'Freeze Terrain' (+ de/fr/it/es);
    the Original stays as the lookup key (how AoWx renames things).
    Descriptions: Release\Spells.pfs record 20 (Freeze Water, spell id 0xA + 10) and record
    14 (Ice Storm, id 4 + 10) tag 10 rewritten (length-changing pfs edit after BXL's
    build_pfs_typos.py: body directory + later index offsets shifted, CRC repaired), and the
    matching Dict\Release.mld rows re-keyed to the new text with fresh de/fr/it/es.

Backups: AoWEPACK.dll.bak_frost, Dict\ResStr.mld.bak_frost, Dict\Release.mld.bak_frost,
Release\Spells.pfs.bak_frost.  Dry-run default; --apply; --revert; --dis.
Caves at 0x55816000 (free per the cave map: legendary caves end at 0x55815F36).
Needs keystone-engine, capstone; uses modding tools\aowxlib\mld.py.
"""
import argparse, os, shutil, struct, sys, zlib
from bakpath import game_dir, game_file   # game folder = AOW_GAME_DIR or parent of patch scripts (2026-09-20)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "modding tools"))
DEFAULT_GAME = game_dir()
BAK = ".bak_frost"
from bakpath import bak_path   # backups live in <game>\backup\ (2026-09-17)
DLL_BASE = 0x55700000

# ---- AoWEPACK.dll sites (verified against the 410 prerelease dll 2026-09-14) ----
ICE_ELSE, ICE_ELSE_ORIG = 0x557CCEF0, bytes.fromhex("c60103eb44")       # mov [ecx],3 ; jmp epilogue
ICE_EPILOGUE = 0x557CCF39
STORM_FRAME_OFF, STORM_LAST_FRAME = 0x10, 0x16                           # [storm+0x10] == 0x16 on the radius-4 pass
FRZ_HOOK, FRZ_HOOK_ORIG = 0x5579E89B, bytes.fromhex("0fbe036685c0")     # movsx eax,[ebx] ; test ax,ax
FRZ_RESUME, FRZ_DONE = 0x5579E8A1, 0x5579E8F7
GATE_VTM, GATE_VTS = 0x5579EBA0, 0x5579EBF0
GATE_ORIG = {GATE_VTM: bytes.fromhex("0fbe7b146685ff74066683ff0a7511"),
             GATE_VTS: bytes.fromhex("0fbe7e146685ff74066683ff0a7511")}
POF_HOOK, POF_HOOK_ORIG = 0x55780231, bytes.fromhex("8a01482c02")         # PathOfFrostTerrainChange land arm: mov al,[ecx]; dec eax; sub al,2
POF_RESUME, POF_DONE = 0x55780236, 0x55780246                             # -> jb (the existing snow test) / epilogue
FIELD_LEVEL = 0x12                                                        # TAoWMapField +0x12 = level (0 = surface)
CAVE_ICE, CAVE_FRZ, CAVE_POF, CAVE_END = 0x55816000, 0x55816040, 0x55816080, 0x558160C0
T_LAVA, T_WASTE, T_SNOW = 9, 5, 3
FREEZE_TO_SNOW = (1, 2, 4, 5)                                            # Grass, Desert, Steppe, Wasteland

# ---- text ----
NAME_ROW = b"Freeze Water"
NAME_NEW = ["Freeze Terrain", "Gel\xe4nde gefrieren", "Gel du terrain", "Congela terreno", "Congelar terreno"]
DESC = {
    20: ("Freezes a small area of water, rendering it solid enough to walk over.",
         "Freezes a small area: water turns to ice solid enough to walk over, lava cools into wasteland and other land is buried under snow.",
         ["Gefriert ein kleines Gebiet: Wasser wird zu begehbarem Eis, Lava k\xfchlt zu \xd6dland ab und anderes Land versinkt im Schnee.",
          "G\xe8le une petite zone : l'eau devient une glace assez solide pour marcher dessus, la lave se refroidit en terre d\xe9sol\xe9e et le reste du terrain est enseveli sous la neige.",
          "Congela una piccola zona: l'acqua diventa ghiaccio abbastanza solido da poterci camminare, la lava si raffredda in terra desolata e il resto del terreno viene sepolto dalla neve.",
          "Congela una peque\xf1a zona: el agua se convierte en hielo lo bastante s\xf3lido para caminar, la lava se enfr\xeda en tierra bald\xeda y el resto del terreno queda cubierto de nieve."]),
    14: ("Summons a massive blizzard, covering an area with ice and freezing water solid. Units caught in the storm suffer cold damage.",
         "Summons a massive blizzard, covering an area with ice, freezing water solid and cooling lava into wasteland. Units caught in the storm suffer cold damage.",
         ["Ruft einen gewaltigen Schneesturm herbei, der ein Gebiet mit Eis bedeckt, Wasser gefrieren l\xe4\xdft und Lava zu \xd6dland abk\xfchlt. Davon betroffene Einheiten erleiden K\xe4ltesch\xe4den.",
          "Invoque une \xe9norme temp\xeate de neige, couvrant la zone de glace, gelant l'eau et refroidissant la lave en terre d\xe9sol\xe9e. Les unit\xe9s pi\xe9g\xe9es subissent des dommages du froid.",
          "Evoca una bufera di neve che ricopre un'area con ghiaccio, congela l'acqua e raffredda la lava in terra desolata. Le unit\xe0 colpite dalla tempesta subiscono danni di freddo.",
          "Invoca una enorme tempestad de nieve, que cubre la zona de hielo, hiela las aguas y enfr\xeda la lava hasta convertirla en tierra bald\xeda. Las unidades atrapadas por la tormenta sufren los da\xf1os del fr\xedo."]),
}


# ------------------------------------------------------------------ PE helpers
def pe_secs(d):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    n = struct.unpack_from("<H", d, e + 6)[0]
    optsz = struct.unpack_from("<H", d, e + 20)[0]
    secs = []
    for i in range(n):
        s = d[e + 24 + optsz + 40 * i:][:40]
        vs, va, rs, ra = struct.unpack_from("<IIII", s, 8)
        secs.append((s[:8].rstrip(b"\0"), va, vs, ra, rs))
    return secs


def va2off(secs, va):
    r = va - DLL_BASE
    for _n, va0, vs, ra, rs in secs:
        if va0 <= r < va0 + max(vs, rs):
            return ra + (r - va0)
    raise ValueError("VA %#x unmapped" % va)


def reloc_targets(d, secs):
    """Set of RVAs that the .reloc section patches (HIGHLOW entries)."""
    out = set()
    for nm, va, vs, ra, rs in secs:
        if nm != b".reloc":
            continue
        p, end = ra, ra + vs
        while p + 8 <= end:
            page, size = struct.unpack_from("<II", d, p)
            if size < 8:
                break
            for q in range(p + 8, p + size, 2):
                v = struct.unpack_from("<H", d, q)[0]
                if v >> 12 == 3:
                    out.add(page + (v & 0xFFF))
            p += size
    return out


# ------------------------------------------------------------------ caves
def assemble():
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    H = lambda v: "0x%X" % v  # noqa: E731  (keystone reads bare decimals as hex)
    ice = "\n".join([
        "cmp  al, %s" % H(T_LAVA),
        "jne  snow",
        "cmp  byte ptr [esi + %s], 0" % H(FIELD_LEVEL),    # esi = field; wasteland is a surface terrain
        "jne  snow",
        "cmp  dword ptr [ebx + %s], %s" % (H(STORM_FRAME_OFF), H(STORM_LAST_FRAME)),
        "jne  skip",                                     # earlier pass: leave the lava for now
        "mov  byte ptr [ecx], %s" % H(T_WASTE),
        "jmp  %s" % H(ICE_EPILOGUE),
        "snow:",
        "mov  byte ptr [ecx], %s" % H(T_SNOW),
        "jmp  %s" % H(ICE_EPILOGUE),
        "skip:",
        "jmp  %s" % H(ICE_EPILOGUE),
    ])
    frz = ["movsx eax, byte ptr [ebx]",
           "cmp  al, %s" % H(T_LAVA),
           "jne  land",                                      # any level: underground lava cools too (user 2026-09-14)
           "mov  byte ptr [ebx], %s" % H(T_WASTE),
           "jmp  %s" % H(FRZ_DONE),
           "land:"]
    for t in FREEZE_TO_SNOW:
        frz += ["cmp  al, %s" % H(t), "je   snow"]
    frz += ["test ax, ax",                                # replay the displaced pair, back to the water arm
            "jmp  %s" % H(FRZ_RESUME),
            "snow:",
            "mov  byte ptr [ebx], %s" % H(T_SNOW),
            "jmp  %s" % H(FRZ_DONE)]
    # Path of Frost (unit walks): eax=unit, edx=field (edi inside), ecx=&terrain.  Our AoWx build already
    # has a land arm (1/2/4/5 -> snow, surface only); lava -> wasteland joins it with the same gate.
    pof = "\n".join([
        "mov  al, byte ptr [ecx]",
        "cmp  al, %s" % H(T_LAVA),
        "jne  orig",                                         # any level (the snow arm below keeps its surface gate)
        "mov  byte ptr [ecx], %s" % H(T_WASTE),
        "done:",
        "jmp  %s" % H(POF_DONE),
        "orig:",
        "dec  eax",                                          # the displaced pair, flags flow into the jb
        "sub  al, 0x2",
        "jmp  %s" % H(POF_RESUME),
    ])
    ice_code = bytes(ks.asm(ice, CAVE_ICE)[0])
    frz_code = bytes(ks.asm("\n".join(frz), CAVE_FRZ)[0])
    pof_code = bytes(ks.asm(pof, CAVE_POF)[0])
    assert CAVE_ICE + len(ice_code) <= CAVE_FRZ and CAVE_FRZ + len(frz_code) <= CAVE_POF and CAVE_POF + len(pof_code) <= CAVE_END
    return ice_code, frz_code, pof_code


def jmp5(src, dst):
    return b"\xE9" + struct.pack("<i", dst - (src + 5))


def dll_patches():
    ice_code, frz_code, pof_code = assemble()
    p = [(CAVE_ICE, bytes(len(ice_code)), ice_code, "cave: Ice Storm lava->wasteland on the last pass"),
         (CAVE_FRZ, bytes(len(frz_code)), frz_code, "cave: Freeze Terrain land arm"),
         (CAVE_POF, bytes(len(pof_code)), pof_code, "cave: Path of Frost lava->wasteland"),
         (ICE_ELSE, ICE_ELSE_ORIG, jmp5(ICE_ELSE, CAVE_ICE), "TIceStorm.ChangeStormTerrain catch-all -> cave"),
         (FRZ_HOOK, FRZ_HOOK_ORIG, jmp5(FRZ_HOOK, CAVE_FRZ) + b"\x90", "TFreezeWaterTE.ChangeTerrain -> cave"),
         (POF_HOOK, POF_HOOK_ORIG, jmp5(POF_HOOK, CAVE_POF), "TAbstractUnit.PathOfFrostTerrainChange land arm -> cave")]
    for site, orig in GATE_ORIG.items():
        p.append((site, orig, b"\xEB\x0D" + b"\x90" * 13, "TFreezeWater target gate widened @%#x" % site))
    return p, (ice_code, frz_code, pof_code)


def dll_state(d, secs, patches):
    cur = [bytes(d[va2off(secs, va):va2off(secs, va) + len(new)]) for va, _o, new, _d in patches]
    if all(c == new for c, (_v, _o, new, _d) in zip(cur, patches)):
        return "applied"
    if all(c == old for c, (_v, old, _n, _d) in zip(cur, patches)):
        return "clean"
    return "mixed"


# ------------------------------------------------------------------ pfs (after BXL's build_pfs_typos.py)
def index_layout(d):
    best = None
    for s in range(0, 0x40):
        ids, offs, p = [], [], s
        while p + 8 <= len(d):
            i, o = struct.unpack_from("<II", d, p)
            if ids and (i <= ids[-1] or o <= offs[-1]):
                break
            if i > 0x10000 or o > len(d):
                break
            ids.append(i); offs.append(o); p += 8
        if len(ids) > 5 and (best is None or len(ids) > len(best[1])):
            best = (s, ids, offs)
    S, wids, _ = best
    N = len(wids)
    for p in range(0, S):
        if not (d[p] & 0x80) or struct.unpack_from("<I", d, p + 1)[0] != N:
            continue
        ns = d[p] & 0x7F
        if p + 5 + 2 * ns == S:
            ent = [(d[p + 5 + 2 * k], d[p + 6 + 2 * k], p + 6 + 2 * k, 1) for k in range(ns)]
            ent += [(struct.unpack_from("<I", d, S + 8 * k)[0], struct.unpack_from("<I", d, S + 8 * k + 4)[0], S + 8 * k + 4, 4) for k in range(N)]
            return S + 8 * N, ent
    raise ValueError("pfs index layout not recognised")


def body_dir(body):
    n = body[0]; p = 1
    small, wide = n & 0x7F, 0
    if n & 0x80:
        wide = struct.unpack_from("<I", body, p)[0]; p += 4
    ent = []
    for _ in range(small):
        ent.append((body[p], body[p + 1], 1)); p += 2
    for _ in range(wide):
        t, o = struct.unpack_from("<II", body, p); ent.append((t, o, 4)); p += 8
    return ent, p


def slice_fields(body, ent, dsz):
    order = sorted(range(len(ent)), key=lambda k: ent[k][1])
    out = {}
    for j, k in enumerate(order):
        t, o, _ = ent[k]
        a = dsz + o
        b = dsz + ent[order[j + 1]][1] if j + 1 < len(order) else len(body)
        assert dsz <= a <= b <= len(body)
        out[t] = body[a:b]
    return out


def pfs_records(d):
    base, ent = index_layout(d)
    ents = sorted(ent, key=lambda e: e[1])
    recs = {}
    for k, (rid, off, _pos, _w) in enumerate(ents):
        end = base + ents[k + 1][1] if k + 1 < len(ents) else len(d) - 4
        recs[rid] = d[base + off:end]
    return base, ent, recs


def pfs_set_text(d, rec, tag, old_text, new_text):
    """Return the file with record `rec` tag `tag` (u32-prefixed string) replaced; asserts `old_text`."""
    assert struct.unpack_from("<I", d, len(d) - 4)[0] == (zlib.crc32(d[4:-4]) & 0xFFFFFFFF), "pfs CRC wrong before edit"
    base, ent, recs = pfs_records(d)
    body = recs[rec]
    dents, dsz = body_dir(body)
    fields = slice_fields(body, dents, dsz)
    f = fields[tag]
    assert struct.unpack_from("<I", f, 0)[0] + 4 == len(f), "tag %d is not a u32 string" % tag
    cur = f[4:].decode("latin-1")
    tail = "\r\n" if cur.endswith("\r\n") else ""             # the pfs text keeps a CRLF the dictionary key lacks
    if cur == new_text + tail:
        return d, "same"
    assert cur == old_text + tail, "record %d tag %d reads %r" % (rec, tag, cur)
    new_text += tail
    nf = struct.pack("<I", len(new_text)) + new_text.encode("latin-1")
    shift = len(nf) - len(f)
    off_t = dict((t, o) for t, o, _ in dents)[tag]
    new_dir = bytearray(body[:dsz])
    p = 1 + (4 if body[0] & 0x80 else 0)
    for t, o, w in dents:
        v = o + shift if o > off_t else o
        if w == 1:
            assert v <= 0xFF, "record %d tag %d offset %d exceeds the u8 directory ceiling: shorten the text" % (rec, t, v)
            new_dir[p + 1] = v
        else:
            struct.pack_into("<I", new_dir, p + 4, v)
        p += 2 if w == 1 else 8
    payload = bytearray(len(body) - dsz + shift)
    for t, o, _ in dents:
        blob = nf if t == tag else fields[t]
        v = o + shift if o > off_t else o
        payload[v:v + len(blob)] = blob
    new_body = bytes(new_dir) + bytes(payload)
    rec_off = dict((a, b) for a, b, _, _ in ent)[rec]
    a0 = base + rec_off
    out = bytearray(d)
    out[a0:a0 + len(body)] = new_body
    for _rid, o, pos, w in ent:
        if o <= rec_off:
            continue
        v = o + shift
        if w == 1:
            assert v <= 0xFF
            out[pos] = v
        else:
            struct.pack_into("<I", out, pos, v)
    struct.pack_into("<I", out, len(out) - 4, zlib.crc32(bytes(out[4:-4])) & 0xFFFFFFFF)
    out = bytes(out)
    # every other record byte-identical, the edited one parses
    _b2, _e2, recs2 = pfs_records(out)
    assert set(recs2) == set(recs)
    for rid in recs:
        if rid != rec:
            assert recs2[rid] == recs[rid], "collateral change in record %d" % rid
    f2 = slice_fields(recs2[rec], *body_dir(recs2[rec]))[tag]
    assert f2[4:].decode("latin-1") == new_text
    return out, "tag %d %d -> %d B, %d later offsets %+d" % (tag, len(f), len(nf), sum(1 for _r, o, _p, _w in ent if o > rec_off), shift)


# ------------------------------------------------------------------ mld
def mld_edit(path, edits):
    """edits: [(original bytes, new_original or None, new_translations dict {col: text})]. Returns new bytes."""
    from aowxlib.mld import MLDFile
    raw = open(path, "rb").read()
    m = MLDFile.parse(raw)
    assert m.dump() == raw, "%s does not round-trip through the codec" % path
    names = m.lang_names()
    assert names == ["Native", "English", "German", "French", "Italian", "Spanish"], names
    notes = []
    for original, new_original, cols in edits:
        rows = [r for r in m.records if r.Original == original]
        assert len(rows) == 1, "%s: %d rows for %r" % (os.path.basename(path), len(rows), original)
        r = rows[0]
        before = (r.Original, list(r.translations))
        if new_original is not None:
            r.Original = new_original.encode("cp1252")
        for col, text in cols.items():
            r.translations[col] = text.encode("cp1252")
        after = (r.Original, list(r.translations))
        notes.append("%r: %s" % (original[:40], "unchanged" if before == after else "updated"))
    return m.dump(), notes


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser(description="Ice Storm lava->wasteland + Freeze Terrain")
    ap.add_argument("--game", default=DEFAULT_GAME)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true")
    args = ap.parse_args()
    G = args.game
    DLL = os.path.join(G, "AoWEPACK.dll")
    RESSTR = os.path.join(G, "Dict", "ResStr.mld")
    RELEASE = os.path.join(G, "Dict", "Release.mld")
    PFS = os.path.join(G, "Release", "Spells.pfs")
    targets = [DLL, RESSTR, RELEASE, PFS]

    if args.revert:
        for t in targets:
            if os.path.exists(bak_path(t, BAK)):
                shutil.copyfile(bak_path(t, BAK), t); print("restored", os.path.basename(t))
            else:
                print("no backup for", os.path.basename(t))
        return 0

    # ---- every file is rebuilt from its pristine backup when one exists, so a re-tune re-applies cleanly
    def base_of(path):
        return open(bak_path(path, BAK) if os.path.exists(bak_path(path, BAK)) else path, "rb").read()
    cur_dll = open(DLL, "rb").read()
    d = bytearray(base_of(DLL))
    secs = pe_secs(d)
    patches, caves = dll_patches()
    st = dll_state(d, secs, patches)
    relocs = reloc_targets(d, secs)
    for va, _o, new, desc in patches:
        rva = va - DLL_BASE                      # a HIGHLOW entry patches 4 bytes at r..r+3
        hit = [r for r in relocs if rva - 3 <= r < rva + len(new)]
        assert not hit, "reloc entries inside %s: %s" % (desc, [hex(x) for x in hit])
    print("AoWEPACK.dll: %s" % st.upper())
    for va, old, new, desc in patches:
        cur = bytes(d[va2off(secs, va):va2off(secs, va) + len(new)])
        tag = "patched" if cur == new else ("clean" if cur == old else "*** FOREIGN ***")
        print("  %08x %-58s %s" % (va, desc, tag))
    if st == "mixed":
        print("  aborting: foreign bytes at a patch site"); return 1
    if args.dis:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
        cs = Cs(CS_ARCH_X86, CS_MODE_32)
        for va, code in zip((CAVE_ICE, CAVE_FRZ, CAVE_POF), caves):
            print("  --- cave @%08x (%d B)" % (va, len(code)))
            for i in cs.disasm(code, va):
                print("    %08x  %-18s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))

    # ---- dictionaries
    from aowxlib.mld import MLDFile
    resstr_new, n1 = mld_edit(bak_path(RESSTR, BAK) if os.path.exists(bak_path(RESSTR, BAK)) else RESSTR, [(NAME_ROW, None, dict(enumerate(NAME_NEW)))])
    rel_src = bak_path(RELEASE, BAK) if os.path.exists(bak_path(RELEASE, BAK)) else RELEASE
    rel_keys = {r.Original for r in MLDFile.load(rel_src).records}
    edits, n2 = [], []
    for old, new, tr in DESC.values():
        if old.encode("cp1252") in rel_keys:
            edits.append((old.encode("cp1252"), new, {1: tr[0], 2: tr[1], 3: tr[2], 4: tr[3]}))
        else:
            assert new.encode("cp1252") in rel_keys, "Release.mld: neither the old nor the new key for %r" % old[:40]
            n2.append("%r: already re-keyed" % new[:40])
    release_new, notes = mld_edit(rel_src, edits)
    n2 += notes
    print("ResStr.mld: " + "; ".join(n1) + (" (unchanged)" if resstr_new == open(RESSTR, "rb").read() else " -> will write"))
    print("Release.mld: " + "; ".join(n2) + (" (unchanged)" if release_new == open(RELEASE, "rb").read() else " -> will write"))

    # ---- Spells.pfs
    pfs = open(PFS, "rb").read()
    pfs_new = base_of(PFS)
    for rec, (old, new, _tr) in DESC.items():
        pfs_new, note = pfs_set_text(pfs_new, rec, 10, old, new)
        print("Spells.pfs record %d: %s" % (rec, note))

    for va, _o, new, _d in patches:                       # the dll image to write = base + patches
        o = va2off(secs, va); d[o:o + len(new)] = new
    changes = [(DLL, bytes(d) != cur_dll), (RESSTR, resstr_new != open(RESSTR, "rb").read()),
               (RELEASE, release_new != open(RELEASE, "rb").read()), (PFS, pfs_new != pfs)]
    if not any(c for _t, c in changes):
        print("ALL ALREADY PATCHED"); return 0
    if not args.apply:
        print("\nDry run OK. Re-run with --apply to write."); return 0

    for t, c in changes:
        if c and not os.path.exists(bak_path(t, BAK)):
            shutil.copyfile(t, bak_path(t, BAK)); print("backup:", os.path.basename(t) + BAK)
    if changes[0][1]:
        assert len(d) == len(cur_dll)
        with open(DLL, "r+b") as f:              # same-size in-place write (see project notes on 'wb')
            f.seek(0); f.write(d)
        print("AoWEPACK.dll patched")
    for path, blob, c in ((RESSTR, resstr_new, changes[1][1]), (RELEASE, release_new, changes[2][1]), (PFS, pfs_new, changes[3][1])):
        if c:
            tmp = path + ".tmp"; open(tmp, "wb").write(blob); os.replace(tmp, path); print("wrote", os.path.basename(path))
    print("Done. UNTESTED in-game until cast: Ice Storm on lava, Freeze Terrain on land and water.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
