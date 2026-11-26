#!/usr/bin/env python3
r"""
Relocate AoWTC.SpellTypes to a 512-entry table and repair BreathDir (AoWTCPCK.dll, 2026-10-03).

Why
  `AoWTC.SpellTypes` is a static byte[0..130] at VA 0x4672F4 (DATA; VA = file + 0x401000) holding each
  spell's tactical-combat class (0 = plain enchant / not combat-relevant, 7 = unit enchant, ...).  It is
  immediately followed by live data: BreathHit (0x467378, 12 dwords) and BreathDir (0x4673A8, 60 dwords),
  the breath-cone hex tables.  Spells above id 130 therefore have no slot:
    * build_spelltypes_bounds_fix.py widened the nine Delphi `bound` pairs from [0,130] to [0,255] so the
      reads stop faulting, and wrote SpellTypes[200] = 7 (Magic Sight) ... at file 0x662F4+200;
    * build_warp_self_stage1.py wrote SpellTypes[202] = 7 (Void Step) the same way.
  Both writes land INSIDE BreathDir: dword 5 (file 0x663BC) reads 0x00070007 instead of 6, so the breath
  reader (`BreathDir[i-1]*12 + BreathHit[j] - 12`, range-checked < 0x48 at 0x43ABC4..) silently skips the
  hex that entry describes.  The dual-sphere project needs 56+ more ids, so the table has to move.

What this does (pure byte patch, no code is added or moved)
  1. Writes a 512-byte table at CAVE (CODE-section zero tail, verified zero + reloc-free before writing):
     vanilla entries 0..130 copied from the live file (asserted against the embedded vanilla hex), then the
     CUSTOM entries below.  Every apply rewrites the whole table, so adding a spell = add it to CUSTOM and
     re-run --apply.
  2. Repoints the 11 `[reg+0x4672F4]` disp32 reads, the pointer slot 0x4693F8 (TCRangedToken kind-52
     path) and the `AoWTC.SpellTypes` export RVA (AoWx.exe imports it by name into IAT 0x45EBEC; its only
     code consumer, the spellbook filter @0x42F304, is already bypassed by build_spellbook_id_fix.py).
     All 12 reads are in-module absolute addresses with .reloc entries; the entries stay valid because the
     new address is in-module too.
  3. Raises the nine SpellTypes bound pairs from [0,255] to [0,511].
  4. Restores BreathDir[5] = 6 and leaves the old 131-byte table in place (nothing reads it any more).

  ⚠ Do not re-run build_spelltypes_bounds_fix.py --apply or build_warp_self_stage1.py --apply afterwards
  without first moving their SpellTypes writes: they still target file 0x662F4+id = BreathDir.  Re-running
  THIS script repairs the dword again, so the recovery is always "re-apply this script".

Backup <game>\backup\AoWTCPCK.dll.bak_spelltypes_reloc (first apply only).  --revert restores that backup
byte-for-byte (which also restores the corrupted BreathDir dword, i.e. the exact pre-state).
Dry-run default; --apply; --revert; --dis (dump sites + table); --dll <path>.
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_dir, game_file

DEFAULT_DLL = game_file("AoWTCPCK.dll")   # 2026-10-11: de-baked
BAK_SUFFIX = ".bak_spelltypes_reloc"

CODE_V2F = 0x400C00          # CODE: VA 0x401000 -> file 0x400
DATA_V2F = 0x401000          # DATA: VA 0x467000 -> file 0x66000
EDATA_RVA_TO_FILE = None     # resolved from the section table at run time

OLD_TABLE_VA = 0x4672F4
OLD_TABLE_LEN = 131
CAVE = 0x43C000              # 512-byte table in the CODE zero tail (zero to 0x466BAC).  Last patched byte in
                             # the live 410 dll is 0x43ACEA (home-PC caves without scripts here) - the gap
                             # below 0x43C000 is left for whatever those scripts reserved.
TABLE_SIZE = 512
NEW_HI = TABLE_SIZE - 1      # bound pairs become [0, 511]

# The 11 instructions that read the table through an absolute disp32 (position of the dword given).
DISP32_SITES = [0x414DCB, 0x418766, 0x41884F, 0x418BB3, 0x418F8E, 0x419601,
                0x41DEF3, 0x41EC51, 0x4233B3, 0x4274F6, 0x4280C0]
PTR_SLOT = 0x4693F8          # DATA dword = @SpellTypes (read @0x40B3FA)
BOUND_PAIRS = [0x415120, 0x4180E8, 0x41B034, 0x41E00C, 0x41EDF0,
               0x423428, 0x427628, 0x4288A0, 0x40CDC4]      # [lo:i32][hi:i32], SpellTypes-exclusive
EXPORT_NAME = b"AoWTC.SpellTypes@57EA1744"

BREATHDIR_VA = 0x4673A8
BREATHDIR5_FILE = BREATHDIR_VA - DATA_V2F + 5 * 4             # 0x663BC
BREATHDIR5_VANILLA = 6
BREATHDIR5_CORRUPT = {0x00070007, 0x00000007, 0x00070000}      # the states the two old scripts can leave

SPELLTYPES_VANILLA_HEX = (
    "000000000000000007000000000000070707000000000000000000000000000007070007070700070707070700000000"
    "000700000000000707000000000000000000000000000000000000000007000000000000000000000000000000000000"
    "000000000607250b21092a0c050007071d07050e0a021e1c280702060a172f2c2e2727")

# ---- custom spells: id -> tactical-combat class byte --------------------------------------------
# 0 = summon / global / anything never cast in combat;  7 = single-unit-target class (unit enchants,
# Slow, Entangle, Call Flames ...).  Measure a donor spell's byte before inventing a value.
CUSTOM = {
    200: 7,     # Magic Sight (unit enchant, EnchW-style)
    201: 0,     # Summon Mermaid
    202: 7,     # Void Step (ex Warp Self, Call Flames chassis)
    203: 0,     # Summon Silver Dragon
}


def sections(d):
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, pe + 6)[0]
    opt = struct.unpack_from("<H", d, pe + 20)[0]
    out = {}
    for k in range(nsec):
        s = pe + 24 + opt + 40 * k
        name = d[s:s + 8].rstrip(b"\0").decode()
        vs, va, rs, ro = struct.unpack_from("<IIII", d, s + 8)
        out[name] = (va, vs, ro, rs)
    return out


def rva2file(secs, rva):
    for va, vs, ro, rs in secs.values():
        if va <= rva < va + max(vs, rs):
            return ro + (rva - va)
    raise ValueError("rva 0x%X not in any section" % rva)


def reloc_set(d, secs):
    va, vs, ro, rs = secs[".reloc"]
    p, out = ro, set()
    while p < ro + vs:
        page, size = struct.unpack_from("<II", d, p)
        if size < 8:
            break
        for q in range(p + 8, p + size, 2):
            e = struct.unpack_from("<H", d, q)[0]
            if e >> 12 == 3:
                out.add(0x400000 + page + (e & 0xFFF))
        p += size
    return out


def export_entry(d, secs):
    """File offset of the export-address-table dword for EXPORT_NAME."""
    va, vs, ro, rs = secs[".edata"]
    nnames = struct.unpack_from("<I", d, ro + 24)[0]
    addr_rva, names_rva, ord_rva = struct.unpack_from("<III", d, ro + 28)
    for i in range(nnames):
        nrva = struct.unpack_from("<I", d, rva2file(secs, names_rva) + 4 * i)[0]
        noff = rva2file(secs, nrva)
        name = d[noff:d.find(b"\0", noff)]
        if name == EXPORT_NAME:
            o = struct.unpack_from("<H", d, rva2file(secs, ord_rva) + 2 * i)[0]
            return rva2file(secs, addr_rva) + 4 * o
    raise ValueError("export %s not found" % EXPORT_NAME.decode())


def build_table(d):
    van = bytes.fromhex(SPELLTYPES_VANILLA_HEX)
    assert len(van) == OLD_TABLE_LEN
    live = bytes(d[OLD_TABLE_VA - DATA_V2F:OLD_TABLE_VA - DATA_V2F + OLD_TABLE_LEN])
    if live != van:
        raise SystemExit("ABORT: live SpellTypes[0..130] differs from vanilla; not touching anything")
    t = bytearray(TABLE_SIZE)
    t[:OLD_TABLE_LEN] = van
    # entries >= 131 written by OTHER scripts (patch_dual_sphere_spells_v1.py owns the dual-sphere ids) are kept
    live_tab = d[CAVE - CODE_V2F:CAVE - CODE_V2F + TABLE_SIZE]
    t[OLD_TABLE_LEN:] = live_tab[OLD_TABLE_LEN:]
    for sid, cls in sorted(CUSTOM.items()):
        if not (OLD_TABLE_LEN <= sid < TABLE_SIZE):
            raise SystemExit("CUSTOM id %d outside %d..%d" % (sid, OLD_TABLE_LEN, TABLE_SIZE - 1))
        t[sid] = cls
    return bytes(t)


def state(d, secs, relocs, exp_off):
    """Classify every patch site: 'vanilla' | 'applied' | 'other'."""
    st = {}
    for va in DISP32_SITES:
        v = struct.unpack_from("<I", d, va - CODE_V2F)[0]
        st["site 0x%X" % va] = ("vanilla" if v == OLD_TABLE_VA else "applied" if v == CAVE else "other(0x%X)" % v, va in relocs)
    v = struct.unpack_from("<I", d, PTR_SLOT - DATA_V2F)[0]
    st["ptr 0x%X" % PTR_SLOT] = ("vanilla" if v == OLD_TABLE_VA else "applied" if v == CAVE else "other(0x%X)" % v, PTR_SLOT in relocs)
    for va in BOUND_PAIRS:
        lo, hi = struct.unpack_from("<ii", d, va - CODE_V2F)
        st["bound 0x%X" % va] = ("vanilla" if (lo, hi) == (0, 255) else "applied" if (lo, hi) == (0, NEW_HI)
                                 else "unwidened[0,130]" if (lo, hi) == (0, 130) else "other(%d,%d)" % (lo, hi), None)
    rva = struct.unpack_from("<I", d, exp_off)[0]
    st["export rva"] = ("vanilla" if rva == OLD_TABLE_VA - 0x400000 else "applied" if rva == CAVE - 0x400000 else "other(0x%X)" % rva, None)
    bd = struct.unpack_from("<I", d, BREATHDIR5_FILE)[0]
    st["BreathDir[5]"] = ("ok(6)" if bd == BREATHDIR5_VANILLA else "CORRUPT(0x%08X)" % bd if bd in BREATHDIR5_CORRUPT else "other(0x%08X)" % bd, None)
    cave = d[CAVE - CODE_V2F:CAVE - CODE_V2F + TABLE_SIZE]
    st["cave"] = ("zero" if not any(cave) else "table" if cave[:OLD_TABLE_LEN] == bytes.fromhex(SPELLTYPES_VANILLA_HEX) else "FOREIGN", None)
    return st


def patch(d, secs, exp_off):
    out = bytearray(d)
    tbl = build_table(d)
    out[CAVE - CODE_V2F:CAVE - CODE_V2F + TABLE_SIZE] = tbl
    for va in DISP32_SITES:
        struct.pack_into("<I", out, va - CODE_V2F, CAVE)
    struct.pack_into("<I", out, PTR_SLOT - DATA_V2F, CAVE)
    for va in BOUND_PAIRS:
        struct.pack_into("<ii", out, va - CODE_V2F, 0, NEW_HI)
    struct.pack_into("<I", out, exp_off, CAVE - 0x400000)
    struct.pack_into("<I", out, BREATHDIR5_FILE, BREATHDIR5_VANILLA)
    return bytes(out), tbl


def write_inplace(path, data):
    """Same-size in-place write (an 'wb' rewrite intermittently fails with EINVAL on this machine)."""
    with open(path, "r+b") as f:
        f.seek(0)
        f.write(data)
        f.truncate(len(data))


def dis(d, tbl):
    print("table @0x%X:" % CAVE)
    for r in range(0, TABLE_SIZE, 32):
        row = tbl[r:r + 32]
        if any(row) or r < OLD_TABLE_LEN + 32:
            print("  [%3d..%3d] %s" % (r, r + 31, " ".join("%02x" % b for b in row)))
    print("custom:", ", ".join("%d->%d" % kv for kv in sorted(CUSTOM.items())))
    try:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        for va in DISP32_SITES:
            for k in (2, 3, 4, 6, 7):            # opcode lengths before the disp32 (8a 80 / 80 b8 / 0f b6 80 / ...)
                st = va - k
                ins = next(md.disasm(d[st - CODE_V2F:st - CODE_V2F + 12], st), None)
                if ins and k + 4 <= ins.size <= k + 5 and va + 4 <= ins.address + ins.size:
                    print("  %08X  %-16s %s %s" % (ins.address, ins.bytes.hex(), ins.mnemonic, ins.op_str))
                    break
    except ImportError:
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dll", default=DEFAULT_DLL)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    dll = a.dll
    bak = bak_path(dll, BAK_SUFFIX, create=a.apply)

    if a.revert:
        if not os.path.exists(bak):
            print("no backup at", bak); return 1
        shutil.copy2(bak, dll); print("restored", dll, "from", bak); return 0

    d = open(dll, "rb").read()
    secs = sections(d)
    relocs = reloc_set(d, secs)
    exp_off = export_entry(d, secs)
    st = state(d, secs, relocs, exp_off)
    for k, (v, rel) in st.items():
        print("  %-18s %s%s" % (k, v, "" if rel is None else ("  (reloc ok)" if rel else "  (NO RELOC ENTRY!)")))
    cave_relocs = sorted(r for r in relocs if CAVE <= r < CAVE + TABLE_SIZE)
    if cave_relocs:
        print("ABORT: .reloc entries inside the cave:", ["0x%X" % r for r in cave_relocs]); return 1
    vals = [v for v, _ in st.values()]
    applied = all(v == "applied" for k, (v, _) in st.items() if k.startswith(("site", "ptr", "bound", "export")))
    if any(v.startswith(("other", "FOREIGN", "unwidened")) for v in vals):
        print("ABORT: unexpected pre-state (see above)"); return 1
    if st["cave"][0] == "FOREIGN":
        print("ABORT: cave holds foreign bytes"); return 1

    new, tbl = patch(d, secs, exp_off)
    if a.dis:
        dis(d, tbl)
    if new == d:
        print("already applied, nothing to do (table + BreathDir match)"); return 0
    changed = sum(1 for x, y in zip(d, new) if x != y)
    print("%s: %d byte(s) would change%s" % ("re-sync" if applied else "apply", changed,
          "; BreathDir[5] repaired" if st["BreathDir[5]"][0] != "ok(6)" else ""))
    if not a.apply:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if not os.path.exists(bak):
        shutil.copy2(dll, bak); print("backup ->", bak)
    write_inplace(dll, new)
    chk = open(dll, "rb").read()
    assert chk == new, "post-write verification failed"
    print("Written and verified:", dll)
    return 0


if __name__ == "__main__":
    sys.exit(main())
