#!/usr/bin/env python3
r"""
Second Wind (310) - "maintain +50% movement, but allow ABILITIES to be used as if the unit had full movement"
(2026-10-16).  AoWTCPCK.dll side; needs patch_secondwind_v1.py v2 (AoWEPACK), which lists every unit Second Wind
refreshes in an 8-slot table of TCombatUnit pointers at AoWEPACK DATA zero-fill slack FM_TAB (0x558E9F80).

The tactical game only lets a unit use an ability (ranged shot, touch, breath, spell...) while its remaining combat move
points [cu+0x5C] still equal its full move points - four equality gates, all `cmp eax,[edx+0x5c] / jne <deny>` with
eax = full MP (CU VMT+0x94 GetMoves, or the unit's VMT+0xD4) and edx = the TCombatUnit:
  A 0x41DDD5 -> 0x41DFCD   the ability target/range highlight for the hovered unit
  B 0x42302E -> 0x4231BD   player click handler, Spellcasting (0x34) branch
  C 0x4230C8 -> 0x4231BD   player click handler, every other ability
  D 0x417CBF -> 0x417E6C   tactical AI (TCAI) ability use
Each 9-byte gate -> `jmp ckX` + 4 nops; ckX keeps the original test (equal -> pass) and otherwise passes when edx is
listed in the AoWEPACK table, else jumps to <deny>.  Actual movement is untouched (+50% from Second Wind).
  CL  turn-start clear: the MP refill (TCPCK NewCombatTurn 0x41CF77 `call [edx+0x94]`) continues into
      `jmp 0x43F000` (patch_slow_v1's cave) @0x41CF7D - we chain IN FRONT: remove [ebp-4] (the CU being refilled) from
      the table, then jmp to the previous target.  So the grant lasts until the unit's own next turn starts.
The table lives in AoWEPACK (it rebases, so does TCPCK): TCPCK finds it through its own import slot of
AoWE.ValidateAoWEngine (IAT 0x46E4A0, read via the call/pop delta) + (FM_TAB - that export's static VA).
Deterministic (only data written inside recorded combat actions / turn starts) -> LAN/replay safe.
Zone TCPCK 0x43F400..0x43F600 (zero, reloc-free; 0x43F040..0x43F400 = Soul Siphon fx).  ⚠ With CL applied,
patch_slow_v1.py's 0x41CF7D jmp points here -> its dry run reports OTHER (expected chain state): revert this first.
Backup <game>\backup\AoWTCPCK.dll.bak_swfullmp.  Dry-run default.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DEFAULT_DLL = game_file("AoWTCPCK.dll")
EPACK = game_file("AoWEPACK.dll")
BAK_SUFFIX = ".bak_swfullmp"
BASE, CODE_V2F = 0x400000, 0x400C00
ZONE, ZONE_END = 0x43F400, 0x43F600
FM_TAB, FM_N = 0x558E9F80, 8                       # must match patch_secondwind_v1.py
IAT_SLOT, IAT_NAME = 0x46E4A0, b"AoWE.ValidateAoWEngine@CD438450"
GATES = [("A", 0x41DDD5, 0x41DFCD), ("B", 0x42302E, 0x4231BD), ("C", 0x4230C8, 0x4231BD), ("D", 0x417CBF, 0x417E6C)]
CL_SITE = 0x41CF7D                                 # jmp rel32 (vanilla: after the refill call; patch_slow_v1 put jmp 0x43F000 here)
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


def asm_delta(src, va):
    """call $D / pop ebx / sub ebx, $D -> ebx = load delta (TCPCK rebases)."""
    s1 = src.replace("call $D", ".byte 0xe8, 0, 0, 0, 0").replace("sub ebx, $D", "sub ebx, 0x7fffffff")
    b = bytearray(ks.asm(s1, va)[0])
    k = b.find(bytes.fromhex("e8000000005b81ebffffff7f")); assert k >= 0, "delta anchor not found"
    struct.pack_into("<I", b, k + 8, va + k + 5)
    return bytes(b)


def build(prev_cl, tab_off):
    out = bytearray(); where = {}

    def place(name, src):
        while len(out) % 16: out.append(0)
        va = ZONE + len(out); where[name] = va
        out.extend(asm_delta(src, va))

    for name, site, deny in GATES:
        place(name, """
            cmp eax, [edx + 0x5c]
            je pass
            push eax
            push ecx
            push ebx
            call $D
            pop ebx
            sub ebx, $D
            mov eax, [ebx + %(iat)#x]
            add eax, %(off)#x
            mov ecx, %(n)d
        lp:
            cmp [eax], edx
            je hit
            add eax, 4
            dec ecx
            jnz lp
            pop ebx
            pop ecx
            pop eax
            jmp %(deny)#x
        hit:
            pop ebx
            pop ecx
            pop eax
        pass:
            jmp %(back)#x
        """ % {"iat": IAT_SLOT, "off": tab_off, "n": FM_N, "deny": deny, "back": site + 9})
    # the clear cave: `jmp short +5 / jmp rel32 prev` header (decodable 'previous' for whoever chains in front later)
    while len(out) % 16: out.append(0)
    va = ZONE + len(out); where["CL"] = va
    hdr = bytes([0xEB, 0x05, 0xE9]) + struct.pack("<i", prev_cl - (va + 7))
    body = hdr + asm_delta("""
        pushad
        call $D
        pop ebx
        sub ebx, $D
        mov eax, [ebx + %(iat)#x]
        add eax, %(off)#x
        mov edx, [ebp - 4]
        mov ecx, %(n)d
    lp:
        cmp [eax], edx
        jne nx
        mov dword ptr [eax], 0
    nx:
        add eax, 4
        dec ecx
        jnz lp
        popad
        jmp %(prev)#x
    """ % {"prev": prev_cl, "iat": IAT_SLOT, "off": tab_off, "n": FM_N}, va + 7)
    out.extend(body)
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
            if e >> 12 == 3: out.add(BASE + page + (e & 0xFFF))
        p += size
    return out


def write_inplace(path, data):
    with open(path, "r+b") as f:
        f.seek(0); f.write(data); f.truncate(len(data))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dll", default=DEFAULT_DLL)
    ap.add_argument("--epack", default=EPACK)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    d = open(a.dll, "rb").read()
    g = lambda va, n: bytes(d[va - CODE_V2F:va - CODE_V2F + n])
    assert iat_check(a.dll), "TCPCK import slot %#x is not %s" % (IAT_SLOT, IAT_NAME)
    tab_off = (FM_TAB - export_va(a.epack, IAT_NAME)) & 0xFFFFFFFF
    zl = g(ZONE, ZONE_END - ZONE)
    inzone = lambda va: ZONE <= va < ZONE_END
    clb = g(CL_SITE, 5); assert clb[0] == 0xE9, "turn-start site %#x is not a jmp: %s" % (CL_SITE, clb.hex())
    cl_cur = CL_SITE + 5 + struct.unpack_from("<i", clb, 1)[0]
    if inzone(cl_cur):                                                     # ours: decode 'prev' from the CL header
        o = cl_cur - CODE_V2F; assert d[o] == 0xEB and d[o + 2] == 0xE9, "CL cave layout unexpected"
        prev_cl = cl_cur + 7 + struct.unpack_from("<i", d, o + 3)[0]
    else:
        prev_cl = cl_cur
    zone, where = build(prev_cl, tab_off)
    st = {}
    for name, site, deny in GATES:
        b = g(site, 9)
        van = bytes.fromhex("3b425c0f85") + struct.pack("<i", deny - (site + 9))
        hook = bytes([0xE9]) + struct.pack("<i", where[name] - (site + 5)) + b"\x90" * 4
        st[name] = "vanilla" if b == van else "ours" if b == hook else "OTHER"
    st["CL"] = "ours" if cl_cur == where["CL"] else "prev" if not inzone(cl_cur) else "OTHER"
    zstate = "zero" if not any(zl) else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else "DIFFERS"
    rl = reloc_set(d)
    spans = [(s, s + 9) for _n, s, _d in GATES] + [(CL_SITE, CL_SITE + 5), (ZONE, ZONE_END)]
    bad = [hex(r) for r in rl if any(lo - 3 <= r < hi for lo, hi in spans)]
    print("gates %s | CL %s (prev %#x) | zone %s (%d B) | table off %#x | relocs %s"
          % (st, st["CL"], prev_cl, zstate, len(zone), tab_off, bad or "none"))
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        for i in md.disasm(zone, ZONE): print("   %08X  %-24s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad or "OTHER" in st.values() or zstate == "DIFFERS": print("ABORT"); return 1
    if a.revert:
        if zstate == "zero" and all(v in ("vanilla", "prev") for v in st.values()): print("nothing to revert"); return 0
        out = bytearray(d)
        for name, site, deny in GATES:
            out[site - CODE_V2F:site - CODE_V2F + 9] = bytes.fromhex("3b425c0f85") + struct.pack("<i", deny - (site + 9))
        out[CL_SITE - CODE_V2F:CL_SITE - CODE_V2F + 5] = bytes([0xE9]) + struct.pack("<i", prev_cl - (CL_SITE + 5))
        out[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
        write_inplace(a.dll, bytes(out)); print("reverted (CL -> %#x)" % prev_cl); return 0
    if all(v == "ours" for v in st.values()) and zstate == "ours": print("already applied"); return 0
    out = bytearray(d)
    out[ZONE - CODE_V2F:ZONE - CODE_V2F + len(zone)] = zone
    for name, site, deny in GATES:
        out[site - CODE_V2F:site - CODE_V2F + 9] = bytes([0xE9]) + struct.pack("<i", where[name] - (site + 5)) + b"\x90" * 4
    out[CL_SITE - CODE_V2F:CL_SITE - CODE_V2F + 5] = bytes([0xE9]) + struct.pack("<i", where["CL"] - (CL_SITE + 5))
    print("%d bytes change" % sum(1 for x, y in zip(d, out) if x != y))
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(a.dll, BAK_SUFFIX)
    if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    write_inplace(a.dll, bytes(out)); assert open(a.dll, "rb").read() == bytes(out); print("Written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
