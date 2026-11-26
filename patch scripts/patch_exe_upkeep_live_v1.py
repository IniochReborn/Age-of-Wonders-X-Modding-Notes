#!/usr/bin/env python3
r"""
Magic window enchantment list shows the LIVE caster-discounted upkeep (AoWx.exe, 2026-10-18).
Companion of patch_caster_upkeep_live_v1.py (AoWEPACK) - REQUIRED: the cave calls its exported adj_u 0x5581E200.

The magic window's own-enchantment list (TMagicWin fill 0x42CE5x, per row) printed [ench+0x10] directly
(0x42CEF3 `mov eax,[eax+0x10]`).  With patch_caster_upkeep_live_v1 the enchantments hold the RAW upkeep and the
Conjurer/Enchanter III discount is applied by readers -> this row now asks adj_u.
  site 0x42CEEE (8 B) `call 0x4025FC (TEnchantmentList.GetEnchantments) ; mov eax,[eax+0x10]` -> `call cave ; 3x nop`
  cave .xibn 0x611840 (slack after patch_aowx_item_banner_hpmv's code, zero-verified, reloc-free):
      call 0x4025FC ; mov ecx,[0x45DCA4] ; add ecx, adj_u - 0x557894EC ; call ecx ; ret
  (AoWEPACK is rebased at runtime: adj_u is reached through the CastingMana import slot, as patch_spellbook_discounts_v1)
Global-enchantment rows already use VMT+0x50 (GetUpkeep, repointed by the AoWEPACK patch).
Apply AFTER patch_caster_upkeep_live_v1.py; revert this one FIRST.  Backup AoWx.exe.bak_upkeeplive.
Dry-run default; --apply; --revert.
"""
import argparse, os, shutil, struct, sys
from bakpath import game_file, bak_path
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

DEFAULT_EXE = game_file(r"AoWx.exe")
BAK = ".bak_upkeeplive"
BASE = 0x400000
SITE, ORIG = 0x42CEEE, bytes.fromhex("e80957fdff8b4010")
LIST_GET_THUNK = 0x4025FC
IMP_CASTINGMANA, CASTINGMANA_LINK = 0x45DCA4, 0x557894EC
ADJ_U = 0x5581E200
CAVE, CAVE_END = 0x611840, 0x611880
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, va):
    enc, _ = ks.asm(src, va); return bytes(enc)


def build():
    cave = asm(f"""
        call {LIST_GET_THUNK:#x}
        mov ecx, [{IMP_CASTINGMANA:#x}]
        add ecx, {(ADJ_U - CASTINGMANA_LINK) & 0xFFFFFFFF:#x}
        call ecx
        ret
    """, CAVE)
    assert len(cave) <= CAVE_END - CAVE
    site = asm(f"call {CAVE:#x}", SITE) + b"\x90" * 3
    return cave, site


def sections(d):
    e = struct.unpack_from("<I", d, 0x3C)[0]; n = struct.unpack_from("<H", d, e + 6)[0]
    opt = struct.unpack_from("<H", d, e + 20)[0]; out = []
    for i in range(n):
        s = e + 24 + opt + 40 * i
        vs, sva, rs, ra = struct.unpack_from("<IIII", d, s + 8); out.append((sva, vs, ra, rs))
    return out, e


def off(d, va):
    for sva, vs, ra, rs in sections(d)[0]:
        if sva <= va - BASE < sva + rs: return ra + va - BASE - sva
    raise ValueError("not in raw data: " + hex(va))


def relocs(d):
    secs, e = sections(d)
    rva, size = struct.unpack_from("<II", d, e + 24 + 136)
    o = off(d, BASE + rva); end = o + size; out = set()
    while o < end:
        page, bs = struct.unpack_from("<II", d, o)
        if bs == 0: break
        for i in range((bs - 8) // 2):
            ent = struct.unpack_from("<H", d, o + 8 + 2 * i)[0]
            if ent >> 12: out.add(BASE + page + (ent & 0xFFF))
        o += bs
    return out


def dll_ready(exe):
    dll = os.path.join(os.path.dirname(os.path.abspath(exe)), "AoWEPACK.dll")
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import patch_caster_upkeep_live_v1 as U
    L, _ = U.build()
    blob = next(b for va, b, n in L.caves if n == "adj_u")
    dd = open(dll, "rb").read()
    return dd[U.off(dd, ADJ_U):U.off(dd, ADJ_U) + len(blob)] == blob


def main():
    ap = argparse.ArgumentParser(description="magic window: live caster-discounted enchantment upkeep")
    ap.add_argument("exe", nargs="?", default=DEFAULT_EXE)
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    a = ap.parse_args()
    cave, site = build()
    d = bytearray(open(a.exe, "rb").read())
    so, co = off(d, SITE), off(d, CAVE)
    cur, zone = bytes(d[so:so + 8]), bytes(d[co:co + (CAVE_END - CAVE)])
    st = "applied" if cur == site and zone.startswith(cave) else ("vanilla" if cur == ORIG and not any(zone) else "FOREIGN")
    rl = [hex(r) for r in relocs(d) if SITE - 3 < r < SITE + 8 or CAVE - 3 < r < CAVE_END]
    print(f"AoWx.exe enchantment-list upkeep @{SITE:#x}: {st}; cave {CAVE:#x} {'ours' if zone.startswith(cave) else ('zero' if not any(zone) else 'FOREIGN')}; relocs {rl or 'none'}")
    assert not rl
    if st == "FOREIGN": sys.exit("unexpected bytes - refusing")
    if a.revert:
        if st == "vanilla": print("not applied"); return
        d[so:so + 8] = ORIG; d[co:co + (CAVE_END - CAVE)] = bytes(CAVE_END - CAVE)
        with open(a.exe, "r+b") as f: f.seek(0); f.write(d)
        print("reverted"); return
    if st == "applied": print("already applied"); return
    if not dll_ready(a.exe): sys.exit("AoWEPACK.dll: patch_caster_upkeep_live_v1 not applied (adj_u missing) - apply it first")
    if not a.apply: print("dry run OK - nothing written (use --apply)"); return
    bak = bak_path(a.exe, BAK)
    if not os.path.exists(bak): shutil.copyfile(a.exe, bak); print("backup ->", bak)
    d[co:co + len(cave)] = cave; d[so:so + 8] = site
    with open(a.exe, "r+b") as f: f.seek(0); f.write(d)
    print("written and verified" if open(a.exe, "rb").read()[so:so + 8] == site else "VERIFY FAILED")


if __name__ == "__main__":
    main()
