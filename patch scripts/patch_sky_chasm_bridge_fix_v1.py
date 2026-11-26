#!/usr/bin/env python3
r"""
Sky / Chasm bridges: orientation + bridge battle maps (2026-10-31).

User: "bridges work, but they are oriented incorrectly. make them like water bridges where they orient based on
valid hexes they are joining. also, the bridge combat maps have water instead of sky/chasm".

Orientation - bridges join LAND across non-land; Sky/Chasm counted as land:
  1. AoWEPACK  AoWE.Land 0x5575AEA4 (not land = Water 0, Ice 6, Lava 9, CaveWater 0xA, CaveIce 0xD) -> also 0xB/0xE.
     Callers: THexagonBridge.DirectionValid / UpdateExclusiveMoves (14) + our patch_build_bridge cave (1) - all
     bridge logic.  Whole function moved to cave 0x55851000 (PIC, no relocs).
  2. HSEPack   Bridge.TBridge.UpdateTransitions (road-type bridge art): a neighbour is land unless terrain 0 or the
     bridge's own terrain -> also not land for 0xB/0xE (site 0x55617C24 cmp/je -> cave 0x5561C840).
Bridge battles - AoWTCPCK TRndTacHsm.RandomMap picks TCMaps\Br<code><A|B|C>000.HSM by the bridge hex's terrain
(Ice6 Ic, Lava9 La, CaveWater UW, CaveIce UI, else Wa):
  3. site 0x424E83 -> cave 0x454480: Sky -> "Sk", Chasm -> "Ch" (AnsiString literals inside the cave, PIC).
  4. TCMaps\BrSk{A,B,C}000.hsm / BrCh{A,B,C}000.hsm = BrWa* with every water combat hexagon (class 0x220598,
     guid 0x005A8502, 1206 per map) re-pointed at the Sky (0xAA0E01) / Chasm (0xAA0B01) combat hexagons from
     build_sky_chasm_combat_v1.  ⚠ new files -> build_release_zip.py --add.
Dry-run default; --apply; --revert.  Backups <file>.bak_skybridgefix.
"""
import os, shutil, struct, subprocess, sys, zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_dir, game_file

WATER_GUID, SKY_GUID, CHASM_GUID = 0x005A8502, 0x00AA0E01, 0x00AA0B01
WATER_CLS1 = 0x220597                              # class - 1 as stored in map records
MAPS = [("Sk", SKY_GUID), ("Ch", CHASM_GUID)]


def asm(src, at):
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    return bytes(Ks(KS_ARCH_X86, KS_MODE_32).asm(src, at)[0])


def land_cave(z):
    return asm(f"""
        cmp  al, 0xB
        je   nl
        cmp  al, 0xE
        je   nl
        test al, al
        je   nl
        sub  al, 6
        je   nl
        add  al, 0xFD
        sub  al, 2
        jb   nl
        sub  al, 2
        je   nl
        xor  eax, eax
        xor  al, 1
        ret
    nl:
        mov  al, 1
        xor  al, 1
        ret
    """, z)


def hse_cave(z):
    return asm(f"""
        mov  al, byte ptr [esp + 0x28]
        test al, al
        je   nl
        cmp  al, 0xB
        je   nl
        cmp  al, 0xE
        je   nl
        jmp  0x55617C2B
    nl:
        jmp  0x55617C52
    """, z)


def tc_cave(z):
    # AnsiString literals: refcount -1, length 2, chars, NUL; string data at +0x48 ("Sk") / +0x58 ("Ch").
    # PIC: call/pop; the add immediates are solved by re-assembling until the layout is stable.
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    k1 = k2 = 0x11111111
    for _ in range(4):
        code = asm(f"""
            mov  eax, dword ptr [ebp - 8]
            mov  al, byte ptr [eax + 0x9F0]
            cmp  al, 0xE
            je   sky
            cmp  al, 0xB
            je   chs
            sub  al, 6
            jmp  0x424E8E
        sky:
            call g1
        g1:
            pop  edx
            add  edx, {k1:#x}
            jmp  cat
        chs:
            call g2
        g2:
            pop  edx
            add  edx, {k2:#x}
        cat:
            lea  eax, [ebp - 0x40]
            call 0x4010E8
            jmp  0x424EE7
        """, z)
        pops = [i.address for i in md.disasm(code, z) if i.mnemonic == "pop"]
        n1, n2 = z + 0x48 - pops[0], z + 0x58 - pops[1]
        if (n1, n2) == (k1, k2):
            break
        k1, k2 = n1, n2
    assert len(code) <= 0x40, len(code)
    blob = bytearray(0x68)
    blob[:len(code)] = code
    for off, s in ((0x40, b"Sk"), (0x50, b"Ch")):
        struct.pack_into("<iI", blob, off, -1, len(s))
        blob[off + 8:off + 8 + len(s)] = s
    return bytes(blob)


def tc_cave_check(blob, z):
    """verify the PIC adds land on the literals"""
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    pops = []
    last_pop = None
    for ins in md.disasm(blob[:0x40], z):
        if ins.mnemonic == "pop":
            last_pop = ins.address
        if ins.mnemonic == "add" and ins.op_str.startswith("edx,") and last_pop is not None:
            pops.append(last_pop + int(ins.op_str.split(",")[1], 16))
    assert pops == [z + 0x48, z + 0x58], [hex(p) for p in pops]


SITES = [  # dll, base, site, original, zone, cave builder, hook length
    ("AoWEPACK.dll", 0x55700000, 0x5575AEA4, "84c074132c06740f04fd2c0272092c02740533c03401c3b0013401c3", 0x55851000, land_cave, 28),
    ("HSEPack.dpl", 0x55600000, 0x55617C24, "807c2428007427", 0x5561C840, hse_cave, 7),
    ("AoWTCPCK.dll", 0x400000, 0x424E83, "8b45f88a80f00900002c06", 0x454480, tc_cave, 11),
]


def conv_map(raw, guid):
    assert raw[:5] == b"CFS\x00\x02"
    inner = zlib.decompress(raw[5:])
    old = struct.pack("<I", WATER_CLS1) + b"\x01\x01\x00" + struct.pack("<I", WATER_GUID)
    new = struct.pack("<I", WATER_CLS1) + b"\x01\x01\x00" + struct.pack("<I", guid)
    n = inner.count(old)
    assert n > 1000 and inner.count(struct.pack("<I", WATER_GUID)) == n, n
    return b"CFS\x00\x02" + zlib.compress(inner.replace(old, new), 9)


def main():
    import pefile
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    gd = game_dir()
    plans = []
    for dll, base, site, orig, zone, mk, n in SITES:
        path = game_file(dll)
        d = open(path, "rb").read()
        pe = pefile.PE(data=d)
        off = lambda va, pe=pe, base=base: pe.get_offset_from_rva(va - base)  # noqa: E731
        cave = mk(zone)
        if mk is tc_cave:
            tc_cave_check(cave, zone)
        hook = b"\xe9" + struct.pack("<i", zone - (site + 5)) + b"\x90" * (n - 5)
        P = [(site, bytes.fromhex(orig), hook), (zone, bytes(len(cave)), cave)]
        rl = {base + e.rva for b in pe.DIRECTORY_ENTRY_BASERELOC for e in b.entries if e.type == 3}
        bad = [hex(r) for r in rl if any(s - 3 <= r < s + len(o) for s, o, _ in P)]
        st = []
        for s, o, nw in P:
            c = d[off(s):off(s) + len(o)]
            st.append("vanilla" if c == o else "ours" if c == nw else "OTHER")
        plans.append((path, off, P, st, bad))
        print("%-13s %s relocs %s" % (dll, st, bad or "none"))
    maps = []
    for code, guid in MAPS:
        for v in "ABC":
            src = os.path.join(gd, "TCMaps", "BrWa%s000.hsm" % v)
            dst = os.path.join(gd, "TCMaps", "Br%s%s000.hsm" % (code, v))
            maps.append((src, dst, guid))
    mst = "ours" if all(os.path.exists(d) for _, d, _ in maps) else "vanilla"
    print("TCMaps bridge templates:", mst)
    allst = {s for p in plans for s in p[3]} | {mst}
    if "OTHER" in allst or any(p[4] for p in plans):
        print("ABORT"); return 1
    want = "vanilla" if revert else "ours"
    if allst == {want}:
        print("already %s" % ("reverted" if revert else "applied")); return 0
    if len(allst) != 1:
        print("ABORT (mixed state)"); return 1
    if not apply and not revert:
        for src, dst, guid in maps:
            conv_map(open(src, "rb").read(), guid)
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    r = subprocess.run(["tasklist"], capture_output=True, text=True).stdout
    if "AoWx.exe" in r or "AoWDevX.exe" in r:
        print("game/editor running - close it first"); return 1
    for path, off, P, st, bad in plans:
        bak = bak_path(path, ".bak_skybridgefix")
        if not revert and not os.path.exists(bak):
            shutil.copy2(path, bak)
        with open(path, "r+b") as f:
            for s, o, nw in reversed(P):
                f.seek(off(s)); f.write(o if revert else nw)
        d2 = open(path, "rb").read()
        assert all(d2[off(s):off(s) + len(o)] == (o if revert else nw) for s, o, nw in P)
    for src, dst, guid in maps:
        if revert:
            if os.path.exists(dst):
                os.remove(dst)
        else:
            with open(dst, "wb") as f:
                f.write(conv_map(open(src, "rb").read(), guid))
    print("reverted" if revert else "written and verified (3 dlls + 6 TCMaps)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
