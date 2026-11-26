#!/usr/bin/env python3
r"""
Caster abilities: Evoker covers combat-only unit spells, and every -30 % step becomes -33 % (2026-10-18).

User: "Evoker doesn't reduce the casting cost of some of our new combat spells like Static Shield, Suspend,
Reversal, Second Wind" + "for Conjurer/Evoker/Ritualist/Enchanter, when it would reduce by 30% make it 33%".

Root cause (Evoker): both classifiers -- cave_cost2 0x55816480 (patch_caster_levels_v1, THero.CastingMana entry)
and classify 0x55816620 (patch_caster_research_upkeep_v1: research steps, h_upkeep, h_count) -- pick the ability
from the spell CLASS (VMT slot +0x6C minus +0x18: 0x6B27C summon -> Conjurer, 0x1FF4 TUnitSpell -> Enchanter,
0x120 + TCombatSpell slot +0x80 -> Evoker, else Ritualist).  Our combat-only spells built on TRemedy / TDispelMagic
(214 Suspend, 215 Static Shield, 233 Mimic, 234 Reversal, 310 Second Wind, 346 Borrow Time, 360 Martyr) are
TUnitSpell instances -> classified Enchanter, so Evoker never touched them.
New rule (both classifiers, Enchanter branch only): a TUnitSpell whose book type [spell+0x22] == 0 ("Combat") or
whose cast context [spell+0x0C] lacks the map bit 1 (combat-only) -> Evoker.  No vanilla unit spell has either
(all 16 vanilla unit-spell ctors set context 3 or 1, type 1) -> vanilla classification unchanged.

33 % (all four abilities, cast / research / upkeep; Evoker III's -50 % unchanged):
  cave_cost2: (v*7+4)/10 and Evoker III (v*5+4)/10 share `add eax,4 / div 10` -> rescaled to /30:
      mul 20 (2/3) / mul 15 (1/2), add 14, div 30 -- identical to nearest-halves-down of 2v/3 and of the old v/2.
  d30 0x55816580 (research steps, enchantment / summon / global-enchantment upkeep, spellbook + research window via
      the exported helpers): (7v+4)/10 -> (2v+1)/3 (nearest of 2v/3; the min-discount-1 rule for upkeep kept).
  h_scale 0x55816A40 (per-turn research estimate, ceil): (10v+6)/7 -> (3v+1)/2 (the v6 turn-step search refines it).
  Ability.pfs records 182-185 (Evoker..Ritualist): "30%" -> "33%" in the descriptions.
All edits are same-length in the existing caves except two 7-/6-byte branch sites redirected to a new PIC cave in
AoWEPACK 0x5581E000..0x5581E800 (zero, reloc-free, freed by the reverted live-upkeep patch).  Stateless: existing
enchantments keep the upkeep stored at creation; running research ([ctl+0x38] raw) picks up the new rate at once.

LIFO: this layers over patch_caster_levels_v1 and patch_caster_research_upkeep_v1 (their dry runs will report
their cost2 / d30 / classify / h_scale caves as changed while this is applied) -> revert THIS first before
reverting or re-applying either.  Backups AoWEPACK.dll.bak_evoker33 / Release\Ability.pfs.bak_evoker33.
Dry-run default; --apply; --revert.
"""
import argparse, os, shutil, struct, sys
from bakpath import game_file, bak_path
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

DLL = game_file(r"AoWEPACK.dll")
PFS = game_file(r"Release\Ability.pfs")
BAK = ".bak_evoker33"
BASE = 0x55700000
ZONE, ZONE_END = 0x5581E000, 0x5581E800
EVOKER, ENCHANTER = 0xAC, 0xAE
COST2_ENCH, COST2_LVL = 0x558164DA, 0x558164E6      # cave_cost2: c_ench (mov edi,0xAE / jmp c_lvl), c_lvl
CLS_ENCH = 0x5581665D                                # classify: c_ench (mov eax,0xAE / ret)
PFS_KEYS = (182, 183, 184, 185)
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, addr):
    return bytes(ks.asm(src, addr)[0])


def cave():
    ev1 = ZONE
    a = asm(f"""
        cmp byte ptr [esi+0x22], 0
        je e1
        test byte ptr [esi+0x0C], 1
        jz e1
        mov edi, {ENCHANTER:#x}
        jmp {COST2_LVL:#x}
    e1:
        mov edi, {EVOKER:#x}
        jmp {COST2_LVL:#x}
    """, ev1)
    ev2 = (ev1 + len(a) + 15) & ~15
    b = asm(f"""
        cmp byte ptr [eax+0x22], 0
        je e2
        test byte ptr [eax+0x0C], 1
        jz e2
        mov eax, {ENCHANTER:#x}
        ret
    e2:
        mov eax, {EVOKER:#x}
        ret
    """, ev2)
    blob = a + bytes(ev2 - ev1 - len(a)) + b
    assert ZONE + len(blob) <= ZONE_END
    return ev1, ev2, blob


EV1, EV2, CAVE = cave()
SITES = [   # (va, vanilla bytes, new bytes, what)
    (COST2_ENCH, bytes.fromhex("bfae000000eb05"), asm(f"jmp {EV1:#x}", COST2_ENCH) + b"\x90\x90", "cost2 Enchanter branch -> reclass cave"),
    (0x558164F2, bytes.fromhex("b907000000"), bytes.fromhex("b914000000"), "cost2 mul 7 -> 20"),
    (0x55816504, bytes.fromhex("b905000000"), bytes.fromhex("b90f000000"), "cost2 Evoker III mul 5 -> 15"),
    (0x5581650E, bytes.fromhex("83c004"), bytes.fromhex("83c00e"), "cost2 add 4 -> 14"),
    (0x55816513, bytes.fromhex("b90a000000"), bytes.fromhex("b91e000000"), "cost2 div 10 -> 30"),
    (CLS_ENCH, bytes.fromhex("b8ae000000c3"), asm(f"jmp {EV2:#x}", CLS_ENCH) + b"\x90", "classify Enchanter branch -> reclass cave"),
    (0x55816584, bytes.fromhex("6bc007"), bytes.fromhex("6bc002"), "d30 mul 7 -> 2"),
    (0x55816587, bytes.fromhex("83c004"), bytes.fromhex("83c001"), "d30 add 4 -> 1"),
    (0x5581658D, bytes.fromhex("b90a000000"), bytes.fromhex("b903000000"), "d30 div 10 -> 3"),
    (0x55816A51, bytes.fromhex("6bc00a"), bytes.fromhex("6bc003"), "h_scale mul 10 -> 3"),
    (0x55816A54, bytes.fromhex("83c006"), bytes.fromhex("83c001"), "h_scale add 6 -> 1"),
    (0x55816A5A, bytes.fromhex("b907000000"), bytes.fromhex("b902000000"), "h_scale div 7 -> 2"),
]
for va, old, new, _ in SITES:
    assert len(old) == len(new), hex(va)


def sections(d):
    e = struct.unpack_from("<I", d, 0x3C)[0]; n = struct.unpack_from("<H", d, e + 6)[0]
    opt = struct.unpack_from("<H", d, e + 20)[0]
    return [struct.unpack_from("<IIII", d, e + 24 + opt + 40 * i + 8) for i in range(n)], e


def off(d, va):
    secs, _ = sections(d); r = va - BASE
    for vs, v0, rs, ra in secs:
        if v0 <= r < v0 + rs:
            return ra + r - v0
    raise ValueError(hex(va))


def relocs(d):
    secs, e = sections(d)
    rva, size = struct.unpack_from("<II", d, e + 24 + 0x88)   # PE32 data directory 5 = base relocations
    out = set(); p = off(d, BASE + rva); end = p + size
    while p < end:
        page, bs = struct.unpack_from("<II", d, p)
        if bs < 8: break
        for k in range((bs - 8) // 2):
            w = struct.unpack_from("<H", d, p + 8 + 2 * k)[0]
            if w >> 12: out.add(BASE + page + (w & 0xFFF))
        p += bs
    return out


# ---- Ability.pfs ----------------------------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import patch_reversal_ability_pfs_v1 as R
from patch_seekerbolts_pfs_v1 import fields, build_record, replace


def allrecs(raw):
    _p, _pre, smalls, wides, body = R.load(raw)
    ents = sorted(list(smalls) + list(wides), key=lambda x: x[1]); out = {}
    for i, (k, o) in enumerate(ents):
        out[k] = body[o:ents[i + 1][1] if i + 1 < len(ents) else len(body)]
    return out


def desc_of(rec):
    _o, v = fields(rec); n = struct.unpack_from("<I", v[5])[0]
    return v[5][4:4 + n]


def with_desc(rec, text):
    order, v = fields(rec); v = dict(v)
    n = struct.unpack_from("<I", v[5])[0]
    v[5] = struct.pack("<I", len(text)) + text + v[5][4 + n:]
    return build_record(order, v)


def pfs_new(raw):
    out = raw
    for k in PFS_KEYS:
        rec = allrecs(out)[k]; t = desc_of(rec)
        out = replace(out, k, with_desc(rec, t.replace(b"30%", b"33%")))
    return out


def pfs_state(raw):
    st = []
    for k in PFS_KEYS:
        t = desc_of(allrecs(raw)[k])
        st.append("33" if b"30%" not in t and b"33%" in t else "30" if b"30%" in t else "?")
    return st


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dll", default=DLL); ap.add_argument("--pfs", default=PFS)
    a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read()); raw = open(a.pfs, "rb").read()
    rel = relocs(d)
    bad = sorted(r for r in rel if any(va - 3 <= r < va + len(o) for va, o, _n, _w in SITES) or ZONE - 3 <= r < ZONE_END)
    assert not bad, "relocs under sites/zone: %s" % [hex(r) for r in bad]
    states = []
    for va, old, new, what in SITES:
        cur = bytes(d[off(d, va):off(d, va) + len(old)])
        s = "vanilla" if cur == old else "applied" if cur == new else "FOREIGN"
        states.append(s); print("  %#010x %-8s %s" % (va, s, what))
    z = bytes(d[off(d, ZONE):off(d, ZONE) + len(CAVE)])
    zs = "zero" if z == bytes(len(CAVE)) else "ours" if z == CAVE else "FOREIGN"
    rest = bytes(d[off(d, ZONE) + len(CAVE):off(d, ZONE_END)])
    print("  zone %#x (%d B): %s; rest of zone %s; relocs none" % (ZONE, len(CAVE), zs, "zero" if rest == bytes(len(rest)) else "NOT ZERO"))
    ps = pfs_state(raw); print("  Ability.pfs 182-185 descriptions:", ps)
    if "FOREIGN" in states or zs == "FOREIGN" or "?" in ps:
        print("unexpected state - refusing"); return 1
    if a.revert:
        if all(s == "vanilla" for s in states) and zs == "zero" and ps == ["30"] * 4:
            print("nothing to revert"); return 0
        for va, old, new, _ in SITES:
            o = off(d, va); d[o:o + len(old)] = old
        o = off(d, ZONE); d[o:o + len(CAVE)] = bytes(len(CAVE))
        with open(a.dll, "r+b") as f: f.seek(0); f.write(d)
        if ps != ["30"] * 4:
            b = bak_path(a.pfs, BAK); assert os.path.isfile(b), "no Ability.pfs backup"
            braw = open(b, "rb").read(); out = raw
            for k in PFS_KEYS:
                out = replace(out, k, allrecs(braw)[k])
            open(a.pfs, "wb").write(out)
        print("reverted"); return 0
    if all(s == "applied" for s in states) and zs == "ours" and ps == ["33"] * 4:
        print("already applied"); return 0
    if not a.apply:
        print("dry run OK (vanilla/partial -> --apply)"); return 0
    newraw = pfs_new(raw) if ps != ["33"] * 4 else raw
    ra, rb = allrecs(raw), allrecs(newraw)
    assert set(ra) == set(rb) and all(ra[k] == rb[k] for k in ra if k not in PFS_KEYS), "another record changed"
    assert [desc_of(rb[k]) for k in PFS_KEYS] == [desc_of(ra[k]).replace(b"30%", b"33%") for k in PFS_KEYS]
    for path in (a.dll, a.pfs):
        b = bak_path(path, BAK)
        if not os.path.isfile(b): shutil.copyfile(path, b); print("  backup ->", b)
    for va, old, new, _ in SITES:
        o = off(d, va); d[o:o + len(new)] = new
    o = off(d, ZONE); d[o:o + len(CAVE)] = CAVE
    with open(a.dll, "r+b") as f: f.seek(0); f.write(d)
    if newraw != raw:
        open(a.pfs, "wb").write(newraw)
    back = open(a.dll, "rb").read()
    assert all(back[off(back, va):off(back, va) + len(n)] == n for va, _o, n, _w in SITES)
    print("applied: Evoker covers combat-only unit spells; caster discounts 30 % -> 33 %"); return 0


if __name__ == "__main__":
    sys.exit(main())
