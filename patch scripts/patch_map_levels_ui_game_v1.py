#!/usr/bin/env python3
r"""
29 map levels, step 4b: the game's level strip (AoWx.exe + AoWEPACK, 2026-10-31).
Needs patch_map_levels_engine_v1 + patch_map_levels_ui_editor_v3 (NAMEFN / name literals in AoWEPACK 'MLU2', the
hidden-level mask TAoWHSMap+0x41C).

The strip (TSWindow.ScannerTab, an aowInt TAOWTabPanel) has room for 3 tabs, so it becomes a sliding 3-tab
window onto the map's VISIBLE levels in display order (Firmament > Surface > Caverns > Depths > Abyss I .. XXV;
hidden levels skipped).  The viewed level sits in the middle tab (at the ends: the edge tab); clicking a
neighbour tab or PgUp / PgDn moves one level and the strip slides on.  Maps with <= 3 visible levels look and
behave as vanilla.  Tab captions: levels 0..2 = vanilla resourcestrings (translated), others = NAMEFN literals,
also through TranslateRStr.
  G1 0x454FED map-load caption fill -> fill around the Surface; resume 0x45509B (dead block 0x454FF8..0x45508E
     keeps its relocs; its reloc-free run 0x455000.. holds the exe trampoline + stubs).
  G2 0x451BDC ScannerTabChange: tab -> level (vanilla only knew 0..2).
  G3 0x451145 MapViewerSceneChanged SetIndex call -> recentre (+ refill when the window moved), then SetIndex.
  G4 0x4514BF / G5 0x4514D5 PgUp / PgDn: previous / next visible level (also stops vanilla's -1 / count overrun).
State: window start in AoWx DATA slack 0x45A7F0.  Code AoWEPACK zone 0x55835400..0x55835C00 ('MLG1'); exe
trampoline adds the AoWEPACK rebase delta ([IAT AoWHSMap 0x45DF7C] - 0x558FA040); AoWEPACK calls the fixed-base
exe absolutely.
Dry-run default; --apply; --revert; --dis.  Backups <file>.bak_mlvgame.
"""
import os, shutil, struct, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

EP, EPBASE = game_file("AoWEPACK.dll"), 0x55700000
EXE, EXEBASE = game_file("AoWx.exe"), 0x400000
ZONE, ZONE_END = 0x55835400, 0x55835C00
CODE = ZONE + 0x10
GLOBAL_MAP = 0x558FA040
MAPSLOT = 0x45DF7C
NAMEFN = 0x55851710
MASK = 0x41C
WIN = 0x45A7F0
RS = [0x45A0C0, 0x45A288, 0x45A3F8]          # Surface / Caverns / Depths resourcestring records
LOADRES, TRANSLATE, LSTRCLR, SETINDEX, SETSCENEL = 0x401180, 0x4021E4, 0x4010D8, 0x4031E4, 0x401E54

G1, G1_ORIG = 0x454FED, "8b80140100008b10ff5240"
G2, G2_ORIG = 0x451BDC, "83ea0172077425 4a7445".replace(" ", "")
G3 = 0x451145
G4, G5 = 0x4514BF, 0x4514D5
TRAMP = 0x455000
ST_G3, ST_PU, ST_PD = TRAMP + 17, TRAMP + 24, TRAMP + 31
DEAD_END = 0x455032                          # reloc at 0x455032


def asm(src, at):
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    src = "\n".join(l.split(";")[0].rstrip() for l in src.split("\n"))   # keystone hangs on comments
    return bytes(Ks(KS_ARCH_X86, KS_MODE_32).asm(src, at)[0])


def src():
    return f"""
    gmap:
        call gm1
    gm1:
        pop  eax
        mov  eax, dword ptr [eax + GMOFF]
        ret
    isvis:
        push ecx
        mov  ecx, dword ptr [esi + 0x10]
        cmp  eax, dword ptr [ecx + 0x14]
        jge  isv0
        mov  ecx, dword ptr [esi + {MASK:#x}]
        bt   ecx, eax
        jc   isv0
        mov  eax, 1
        pop  ecx
        ret
    isv0:
        xor  eax, eax
        pop  ecx
        ret
    slotlvl:
        mov  eax, ecx
        test ecx, ecx
        jne  sl1
        mov  eax, 3
        ret
    sl1:
        cmp  ecx, 3
        jg   sl2
        dec  eax
    sl2:
        ret
    vcount:
        xor  edx, edx
        xor  ecx, ecx
    vc1:
        call slotlvl
        call isvis
        add  edx, eax
        inc  ecx
        cmp  ecx, 29
        jb   vc1
        mov  eax, edx
        ret
    kcount:
        call vcount
        cmp  eax, 3
        jle  kc1
        mov  eax, 3
    kc1:
        ret
    vpos:
        push edi
        mov  edi, eax
        xor  edx, edx
        xor  ecx, ecx
    vp1:
        call slotlvl
        cmp  eax, edi
        je   vp2
        call isvis
        add  edx, eax
        inc  ecx
        cmp  ecx, 29
        jb   vp1
        jmp  vpn
    vp2:
        mov  eax, edi
        call isvis
        test eax, eax
        je   vpn
        mov  eax, edx
        pop  edi
        ret
    vpn:
        or   eax, -1
        pop  edi
        ret
    lvlat:
        push edi
        mov  edi, eax
        test edi, edi
        js   lan
        xor  ecx, ecx
    la1:
        call slotlvl
        mov  edx, eax
        call isvis
        test eax, eax
        je   la2
        test edi, edi
        je   lafound
        dec  edi
    la2:
        inc  ecx
        cmp  ecx, 29
        jb   la1
    lan:
        or   eax, -1
        pop  edi
        ret
    lafound:
        mov  eax, edx
        pop  edi
        ret
    recenter:
        push esi
        push edi
        push ebx
        mov  ebx, eax
        call gmap
        mov  esi, eax
        test esi, esi
        je   rz
        mov  eax, ebx
        call vpos
        mov  edi, eax
        test eax, eax
        js   rz
        call vcount
        mov  ebx, eax
        call kcount
        sub  ebx, eax
        lea  eax, [edi - 1]
        test eax, eax
        jge  rc1
        xor  eax, eax
    rc1:
        cmp  eax, ebx
        jle  rc2
        mov  eax, ebx
    rc2:
        mov  dword ptr [{WIN:#x}], eax
        mov  eax, edi
        sub  eax, dword ptr [{WIN:#x}]
        pop  ebx
        pop  edi
        pop  esi
        ret
    rz:
        xor  eax, eax
        mov  dword ptr [{WIN:#x}], eax
        pop  ebx
        pop  edi
        pop  esi
        ret
    fill:
        push ebp
        mov  ebp, esp
        push 0
        push 0
        push ebx
        push esi
        push edi
        mov  ebx, eax
        call gmap
        mov  esi, eax
        mov  eax, dword ptr [ebx + 0x114]
        mov  edx, dword ptr [eax]
        call dword ptr [edx + 0x40]
        test esi, esi
        je   fdone2
        call kcount
        mov  edi, eax
        push 0
    fl:
        mov  eax, dword ptr [esp]
        cmp  eax, edi
        jge  fdone
        add  eax, dword ptr [{WIN:#x}]
        call lvlat
        test eax, eax
        js   fnext
        cmp  eax, 3
        jae  flit
        mov  ecx, {RS[0]:#x}
        test eax, eax
        je   frs
        mov  ecx, {RS[1]:#x}
        cmp  eax, 1
        je   frs
        mov  ecx, {RS[2]:#x}
    frs:
        mov  eax, dword ptr [ecx]
        lea  edx, [ebp - 4]
        mov  ecx, {LOADRES:#x}
        call ecx
        mov  eax, dword ptr [ebp - 4]
        jmp  ftr
    flit:
        call {NAMEFN:#x}
    ftr:
        lea  edx, [ebp - 8]
        mov  ecx, {TRANSLATE:#x}
        call ecx
        mov  edx, dword ptr [ebp - 8]
        mov  eax, dword ptr [ebx + 0x114]
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x34]
    fnext:
        inc  dword ptr [esp]
        jmp  fl
    fdone:
        pop  eax
    fdone2:
        lea  eax, [ebp - 4]
        mov  ecx, {LSTRCLR:#x}
        call ecx
        lea  eax, [ebp - 8]
        mov  ecx, {LSTRCLR:#x}
        call ecx
        pop  edi
        pop  esi
        pop  ebx
        mov  esp, ebp
        pop  ebp
        ret
    g1:
        push eax
        xor  eax, eax
        call recenter
        push eax
        mov  eax, dword ptr [esp + 4]
        call fill
        pop  edx
        pop  eax
        mov  dword ptr [eax + 0x118], -1
        push 0x45509B
        mov  ecx, {SETINDEX:#x}
        jmp  ecx
    g2:
        push ebx
        push esi
        mov  ebx, eax
        call gmap
        mov  esi, eax
        test esi, esi
        je   g2x
        test edx, edx
        js   g2x
        push edx
        call kcount
        pop  edx
        cmp  edx, eax
        jge  g2x
        mov  eax, edx
        add  eax, dword ptr [{WIN:#x}]
        call lvlat
        test eax, eax
        js   g2x
        mov  edx, eax
        mov  ecx, dword ptr [ebx + 0x5C]
        mov  dword ptr [ecx + 0x17C], -1
        mov  eax, esi
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0xB8]
    g2x:
        pop  esi
        pop  ebx
        ret
    g3:
        push eax
        push dword ptr [{WIN:#x}]
        mov  eax, edx
        call recenter
        mov  edx, eax
        pop  ecx
        cmp  ecx, dword ptr [{WIN:#x}]
        je   g3s
        push edx
        mov  eax, dword ptr [esp + 4]
        call fill
        pop  edx
        mov  eax, dword ptr [esp]
        mov  dword ptr [eax + 0x118], -1
    g3s:
        pop  eax
        mov  ecx, {SETINDEX:#x}
        jmp  ecx
    pgu:
        mov  ecx, -1
        jmp  pg
    pgd:
        mov  ecx, 1
    pg:
        push eax
        push esi
        push ebx
        mov  ebx, ecx
        call gmap
        mov  esi, eax
        test esi, esi
        je   pgn
        mov  eax, edx
        call vpos
        test eax, eax
        js   pgn
        add  eax, ebx
        call lvlat
        test eax, eax
        js   pgn
        mov  edx, eax
        pop  ebx
        pop  esi
        pop  eax
        mov  ecx, {SETSCENEL:#x}
        jmp  ecx
    pgn:
        pop  ebx
        pop  esi
        pop  eax
        ret
    """


ENTRIES = ("g1", "g2", "g3", "pgu", "pgd")


def blob():
    k = 0x11111111
    for _ in range(4):
        s = src().replace("GMOFF", hex(k))
        labs = ENTRIES + ("gm1",)
        full = asm(s + "\n" + "\n".join(".long " + l for l in labs), CODE)
        code = full[:-4 * len(labs)]
        ent = dict(zip(labs, struct.unpack("<%dI" % len(labs), full[-4 * len(labs):])))
        n = (GLOBAL_MAP - ent["gm1"]) & 0xFFFFFFFF
        if n == k:
            break
        k = n
    else:
        raise AssertionError("layout")
    assert CODE + len(code) <= ZONE_END, hex(len(code))
    z = bytearray(ZONE_END - ZONE)
    z[:4] = b"MLG1"
    z[CODE - ZONE:CODE - ZONE + len(code)] = code
    return bytes(z), ent, code


def exe_patches(ent):
    t = lambda lab: struct.pack("<I", ent[lab])  # noqa: E731
    rel = lambda at, to: struct.pack("<i", to - (at + 5))  # noqa: E731
    tramp = bytes.fromhex("50a1") + struct.pack("<I", MAPSLOT) + b"\x2d" + struct.pack("<I", GLOBAL_MAP) + \
        bytes.fromhex("0144240458c3")
    stubs = tramp
    for at, lab in ((ST_G3, "g3"), (ST_PU, "pgu"), (ST_PD, "pgd")):
        assert TRAMP + len(stubs) == at
        stubs += b"\x68" + t(lab) + b"\xeb" + struct.pack("<b", TRAMP - (at + 7))
    assert TRAMP + len(stubs) <= DEAD_END - 3
    g1 = b"\x68" + t("g1") + b"\xeb" + struct.pack("<b", TRAMP - (G1 + 7))
    g2 = b"\x68" + t("g2") + b"\xe9" + rel(G2 + 5, TRAMP)
    d = open(EXE, "rb").read()
    import pefile
    pe = pefile.PE(data=d)
    off = lambda va: pe.get_offset_from_rva(va - EXEBASE)  # noqa: E731
    return [
        (G1, bytes.fromhex(G1_ORIG), g1 + b"\x90" * 4),
        (TRAMP, d[off(TRAMP):off(TRAMP) + len(stubs)], stubs),
        (G2, bytes.fromhex(G2_ORIG), g2),
        (G3, b"\xe8" + rel(G3, SETINDEX), b"\xe8" + rel(G3, ST_G3)),
        (G4, b"\x4a\xe8" + rel(G4 + 1, SETSCENEL), b"\xe8" + rel(G4, ST_PU) + b"\x90"),
        (G5, b"\x42\xe8" + rel(G5 + 1, SETSCENEL), b"\xe8" + rel(G5, ST_PD) + b"\x90"),
    ]


def plan(path, base, P):
    import pefile
    d = open(path, "rb").read()
    pe = pefile.PE(data=d)
    off = lambda va: pe.get_offset_from_rva(va - base)  # noqa: E731
    rl = {base + e.rva for b in pe.DIRECTORY_ENTRY_BASERELOC for e in b.entries if e.type == 3}
    bad = [hex(r) for r in rl if any(s - 3 <= r < s + len(o) for s, o, _ in P)]
    st = []
    for s, o, n in P:
        c = d[off(s):off(s) + len(o)]
        st.append("vanilla" if c == o else "ours" if c == n else "OTHER")
    return off, st, bad


def main():
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    z, ent, code = blob()
    if "--dis" in sys.argv:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
        inv = {v: k for k, v in ent.items()}
        for i in Cs(CS_ARCH_X86, CS_MODE_32).disasm(code, CODE):
            if i.address in inv:
                print("%s:" % inv[i.address])
            print("  %08x %s %s" % (i.address, i.mnemonic, i.op_str))
        return 0
    if b"MLU2" not in open(EP, "rb").read():
        print("ABORT: patch_map_levels_ui_editor_v3 (name literals) is not applied"); return 1
    print("entries:", {k: hex(v) for k, v in ent.items()})
    EXP = exe_patches(ent)
    EXP[1] = (EXP[1][0], bytes.fromhex("e87bc1faff8b45ec8d55f0e8d4d1faff8b55f08b038b404c8b80140100008b08ff5134"
                                       "8b068b40108378140100")[:len(EXP[1][2])], EXP[1][2])
    files = [(EP, EPBASE, [(ZONE, bytes(len(z)), z)]), (EXE, EXEBASE, EXP)]
    plans = []
    for path, base, P in files:
        off, st, bad = plan(path, base, P)
        print("%-12s %s relocs %s" % (os.path.basename(path), st, bad or "none"))
        plans.append((path, off, P, st, bad))
    allst = {s for p in plans for s in p[3]}
    if "OTHER" in allst or any(p[4] for p in plans):
        print("ABORT"); return 1
    want = "vanilla" if revert else "ours"
    if allst == {want}:
        print("already %s" % ("reverted" if revert else "applied")); return 0
    if len(allst) != 1:
        print("ABORT (mixed state)"); return 1
    if not apply and not revert:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    r = subprocess.run(["tasklist"], capture_output=True, text=True).stdout
    if "AoWx.exe" in r or "AoWDevX.exe" in r:
        print("game/editor running - close it first"); return 1
    for path, off, P, st, bad in plans:
        bak = bak_path(path, ".bak_mlvgame")
        if not revert and not os.path.exists(bak):
            shutil.copy2(path, bak)
        with open(path, "r+b") as f:
            for s, o, n in P:
                f.seek(off(s)); f.write(o if revert else n)
        d2 = open(path, "rb").read()
        assert all(d2[off(s):off(s) + len(o)] == (o if revert else n) for s, o, n in P)
    print("reverted" if revert else "written and verified (AoWEPACK zone + %d exe sites)" % len(EXP))
    return 0


if __name__ == "__main__":
    sys.exit(main())
