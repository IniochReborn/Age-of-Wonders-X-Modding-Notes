#!/usr/bin/env python3
r"""
Second Wind (310) - the HOVER half of "abilities as if the unit had full movement" (2026-10-16).  AoWx.exe side; needs
patch_secondwind_v1.py v2+ (AoWEPACK: the 8-slot full-MP table at FM_TAB) and pairs with patch_tc_secondwind_fullmp_v1.py
(AoWTCPCK: targeting / click / AI gates + the turn-start clear).

User 10/16: "after using Second Wind I can use the ability successfully, but it doesn't HIGHLIGHT when hovered".  The
TCPCK gates only cover the map side.  The combat unit panel's ABILITY LISTS live in AoWx.exe and run their own strict
test `full MP (TUnit VMT+0xD4) == [cu+0x5C]` (cu = [[0x45A420]+0xC4]+0x1C, the selected TCombatUnit), for the active
abilities (GetAbility VMT+0x84 kind 3..5) and Spellcasting (0x34):
  S1 0x407D82 `cmp eax,[edx+5C] / je 0x407D8B`        list A item draw: usable colour 0xDFFEFF vs dimmed 0x8FA9A0
  S2 0x409B22 `cmp eax,[edx+5C] / jne 0x409BBB`       list A mouse-over: show the hover highlight/hint ([ebx+0x78])
  S3 0x43487B `cmp eax,[edi+5C] / jne 0x434892`       list B item draw: white vs grey 0xC0C0C0
  S4 0x434B5C `cmp eax,[esi+5C] / jle 0x434B71`       list B mouse-over: else hover index [list+0x188] := -1 (no highlight)
Each site -> `jmp cave` (+nops); the cave keeps the original test (pass -> the original pass target) and otherwise
passes when the CU is listed in the AoWEPACK table, else -> the original deny target.  Pure UI (nothing recorded).
The table: [IAT slot 0x45DC00 = AoWE.AoWE@00000000] + (FM_TAB - that export's static VA).  AoWx.exe never rebases
(DllCharacteristics 0) -> absolute addresses in .xbfs are fine.
Caves .xbfs 0x60ED40..0x60EE40 (zero-verified; 0x60ED00..0x60ED40 = harvest display, 0x60EFF0.. = datesort diag).
Backup <game>\backup\AoWx.exe.bak_swhover.  Dry-run default; --apply / --revert / --dis.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DEFAULT_EXE = game_file("AoWx.exe")
EPACK = game_file("AoWEPACK.dll")
BAK_SUFFIX = ".bak_swhover"
XBFS_VA, XBFS_RAW = 0x60D000, 0x208600
ZONE, ZONE_END = 0x60ED40, 0x60EE40
FM_TAB, FM_N = 0x558E9F80, 8                       # must match patch_secondwind_v1.py
IAT_SLOT, IAT_NAME = 0x45DC00, b"AoWE.AoWE@00000000"
# (name, site, vanilla bytes, CU register, pass condition, pass target, deny target)
SITES = [("S1", 0x407D82, "3b425c7404", "edx", "je", 0x407D8B, 0x407D87),
         ("S2", 0x409B22, "3b425c0f8590000000", "edx", "je", 0x409B2B, 0x409BBB),
         ("S3", 0x43487B, "3b475c7512", "edi", "je", 0x434880, 0x434892),
         ("S4", 0x434B5C, "3b465c7e10", "esi", "jle", 0x434B71, 0x434B61)]
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def export_va(path, name):
    import pefile
    pe = pefile.PE(path)
    for e in pe.DIRECTORY_ENTRY_EXPORT.symbols:
        if e.name == name: return pe.OPTIONAL_HEADER.ImageBase + e.address
    raise SystemExit("export %s not found in %s" % (name, path))


def iat_check(path):
    import pefile
    pe = pefile.PE(path)
    for imp in pe.DIRECTORY_ENTRY_IMPORT:
        for i in imp.imports:
            if i.address == IAT_SLOT: return i.name == IAT_NAME and b"EPACK" in imp.dll.upper()
    return False


def build(tab_off):
    out = bytearray(); where = {}
    for name, site, van, reg, jcc, ptgt, dtgt in SITES:
        while len(out) % 16: out.append(0)
        va = ZONE + len(out); where[name] = va
        out.extend(ks.asm("""
            cmp eax, [%(r)s + 0x5c]
            %(jcc)s %(p)#x
            push eax
            push ecx
            mov eax, dword ptr [%(iat)#x]
            add eax, %(off)#x
            mov ecx, %(n)d
        lp:
            cmp [eax], %(r)s
            je hit
            add eax, 4
            dec ecx
            jnz lp
            pop ecx
            pop eax
            jmp %(dn)#x
        hit:
            pop ecx
            pop eax
            jmp %(p)#x
        """ % {"r": reg, "jcc": jcc, "p": ptgt, "dn": dtgt, "iat": IAT_SLOT, "off": tab_off, "n": FM_N}, va)[0])
    assert ZONE + len(out) <= ZONE_END, hex(ZONE + len(out))
    return bytes(out), where


def reloc_set(d):
    pe = struct.unpack_from("<I", d, 0x3C)[0]; opt = struct.unpack_from("<H", d, pe + 20)[0]; nsec = struct.unpack_from("<H", d, pe + 6)[0]
    secs = [struct.unpack_from("<IIII", d, pe + 24 + opt + 40 * k + 8) for k in range(nsec)]
    rrva, rsz = struct.unpack_from("<II", d, pe + 24 + 0x88)
    def r2f(rva):
        for vs, va, rs, ro in secs:
            if va <= rva < va + max(vs, rs): return ro + rva - va
    p, end, out = r2f(rrva), r2f(rrva) + rsz, set()
    while p < end:
        page, size = struct.unpack_from("<II", d, p)
        if size < 8: break
        for q in range(p + 8, p + size, 2):
            e = struct.unpack_from("<H", d, q)[0]
            if e >> 12 == 3: out.add(0x400000 + page + (e & 0xFFF))
        p += size
    return out


def write_inplace(path, data):
    with open(path, "r+b") as f:
        f.seek(0); f.write(data); f.truncate(len(data))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=DEFAULT_EXE)
    ap.add_argument("--epack", default=EPACK)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    import pefile
    d = open(a.exe, "rb").read()
    pe = pefile.PE(data=d, fast_load=True)
    f = lambda va: pe.get_offset_from_rva(va - 0x400000)
    g = lambda va, n: bytes(d[f(va):f(va) + n])
    assert pe.OPTIONAL_HEADER.DllCharacteristics & 0x40 == 0, "AoWx.exe is DYNAMIC_BASE - absolute caves unsafe"
    assert f(ZONE) == XBFS_RAW + ZONE - XBFS_VA, ".xbfs layout changed"
    assert iat_check(a.exe), "AoWx.exe import slot %#x is not %s" % (IAT_SLOT, IAT_NAME)
    tab_off = (FM_TAB - export_va(a.epack, IAT_NAME)) & 0xFFFFFFFF
    zone, where = build(tab_off)
    st = {}
    for name, site, van, reg, jcc, ptgt, dtgt in SITES:
        n = len(bytes.fromhex(van)); b = g(site, n)
        hook = bytes([0xE9]) + struct.pack("<i", where[name] - (site + 5)) + b"\x90" * (n - 5)
        st[name] = "vanilla" if b.hex() == van else "ours" if b == hook else "OTHER(%s)" % b.hex()
    zl = g(ZONE, ZONE_END - ZONE)
    zstate = "zero" if not any(zl) else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else "DIFFERS"
    rl = reloc_set(d)
    bad = [hex(r) for r in rl if any(s - 3 <= r < s + len(v) // 2 for _nm, s, v, *_r in SITES) or ZONE - 3 <= r < ZONE_END]
    print("sites %s | zone %s (%d B) | table off %#x | relocs %s" % (st, zstate, len(zone), tab_off, bad or "none"))
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        for i in md.disasm(zone, ZONE): print("   %08X  %-24s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad or any(v.startswith("OTHER") for v in st.values()) or zstate == "DIFFERS": print("ABORT"); return 1
    out = bytearray(d)
    if a.revert:
        if zstate == "zero" and all(v == "vanilla" for v in st.values()): print("nothing to revert"); return 0
        for name, site, van, *_r in SITES: out[f(site):f(site) + len(van) // 2] = bytes.fromhex(van)
        out[f(ZONE):f(ZONE) + ZONE_END - ZONE] = bytes(ZONE_END - ZONE)
        write_inplace(a.exe, bytes(out)); print("reverted"); return 0
    if all(v == "ours" for v in st.values()) and zstate == "ours": print("already applied"); return 0
    out[f(ZONE):f(ZONE) + len(zone)] = zone
    for name, site, van, *_r in SITES:
        n = len(van) // 2
        out[f(site):f(site) + n] = bytes([0xE9]) + struct.pack("<i", where[name] - (site + 5)) + b"\x90" * (n - 5)
    print("%d bytes change" % sum(1 for x, y in zip(d, out) if x != y))
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(a.exe, BAK_SUFFIX)
    if not os.path.exists(bak): shutil.copy2(a.exe, bak); print("backup ->", bak)
    write_inplace(a.exe, bytes(out)); assert open(a.exe, "rb").read() == bytes(out); print("Written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
