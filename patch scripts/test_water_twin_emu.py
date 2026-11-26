#!/usr/bin/env python3
r"""
Unicorn test of patch_water_twin_fade_v2 on the REAL AoWEPACK code (patches applied in memory):
  1. TAoWWaterHexagon.UpdateTransitions 0x5579AD98 with six fake neighbours (HSE imports stubbed) -> shore mask
     [hex+0x14], edge bits [hex+0x15], side bases [hex+0x1A+side];
  2. the ShowDynamic shore block from 0x5579B1C1 -> list of drawn image ids.
Neighbour spec per side (engine order top, UR, LR, bottom, LL, UL): (terrain, kind) kind 'L' land hexagon,
'W' TLowerIsometricHexagon (water class), 'B' border.
"""
import os, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import patch_water_twin_fade_v3 as W  # noqa: E402
import patch_sky_polish_v1 as SP  # noqa: E402

from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE  # noqa: E402
from unicorn.x86_const import *  # noqa: E402,F401,F403

B = 0x55700C00
UPD, SHORE, SHORE_END, SHORE_RET = 0x5579AD98, 0x5579B1C1, 0x5579B546, 0x5579B1C6
T_INIT, T_NEXT, T_GETFIELD, T_FIND, T_GETIMG = 0x557026D4, 0x557026DC, 0x557020DC, 0x55701FFC, 0x55702934
CLS_LOWER, CLS_BORDER = 0x558FCD70, 0x558FCCF0
RET = 0x55A00000


def machine(patched=True):
    d = bytearray(open(SP.EPK, "rb").read())
    if patched:
        for va, o, n in W.epk_patches():
            cur = bytes(d[va - B:va - B + len(n)])
            assert cur in (o, n), hex(va)
            d[va - B:va - B + len(n)] = n
    mu = Uc(UC_ARCH_X86, UC_MODE_32)
    mu.mem_map(0x55700000, 0x400000)
    mu.mem_write(0x55701000, bytes(d[0x400:0x400 + 0x1E6A00]))
    mu.mem_map(0x100000, 0x100000)
    mu.mem_map(0x300000, 0x100000)
    return mu


def run(own, nbs, patched=True):
    mu = machine(patched)
    w = lambda a, v: mu.mem_write(a, struct.pack("<I", v & 0xFFFFFFFF))  # noqa: E731
    r = lambda a: struct.unpack("<I", bytes(mu.mem_read(a, 4)))[0]       # noqa: E731
    HEX, FLD, LVL, VMT = 0x300000, 0x300100, 0x300200, 0x300300
    w(HEX, VMT); w(HEX + 4, FLD); w(HEX + 0x10, 1)
    mu.mem_write(HEX + 0x14, bytes([0x55, 0xFF]) + bytes([0x77] * 10))      # stale mask / edge bits / bases
    w(FLD + 4, LVL); mu.mem_write(FLD + 0x10, bytes([3, 3])); mu.mem_write(FLD + 0x14, bytes([own]))
    w(LVL + 0xC, 50); w(LVL + 0x10, 50)
    w(VMT + 0x4C, 0x55A00100)
    w(CLS_LOWER, 0xC1A55001); w(CLS_BORDER, 0xC1A55002)
    for i, (t, k) in enumerate(nbs):
        mu.mem_write(0x301000 + i * 0x40 + 0x14, bytes([t]))
    st = {"walk": 0}

    def ret(val=None, pop=0):
        sp = mu.reg_read(UC_X86_REG_ESP)
        if val is not None:
            mu.reg_write(UC_X86_REG_EAX, val & 0xFFFFFFFF)
        mu.reg_write(UC_X86_REG_EIP, r(sp)); mu.reg_write(UC_X86_REG_ESP, sp + 4 + pop)

    def setwalk(n):
        base = st["walk"]
        w(base + 8, n); w(base + 0x10, n); w(base + 0x14, 0)

    drawn = []

    def hook(uc, addr, size, _):
        if addr == T_INIT:
            st["walk"] = uc.reg_read(UC_X86_REG_EAX); setwalk(1); ret(pop=4)
        elif addr == T_NEXT:
            setwalk(r(st["walk"] + 8) + 1); ret()
        elif addr == T_GETFIELD:
            ret(0x301000 + (uc.reg_read(UC_X86_REG_EDX) - 1) * 0x40)
        elif addr == T_FIND:
            i = (uc.reg_read(UC_X86_REG_EAX) - 0x301000) // 0x40
            cls = uc.reg_read(UC_X86_REG_EDX)
            k = nbs[i][1]
            ret(1 if (cls == 0xC1A55001 and k == "W") or (cls == 0xC1A55002 and k == "B") else 0)
        elif addr == 0x55A00100:
            ret(own)
        elif addr == T_GETIMG:
            drawn.append(uc.reg_read(UC_X86_REG_EDX)); ret(0x300400)
        elif addr == 0x55A00200:
            ret(pop=4)
    mu.hook_add(UC_HOOK_CODE, hook)
    w(0x300400, 0x300500); w(0x300500 + 0x84, 0x55A00200)
    SP0 = 0x180000
    w(SP0, RET)
    mu.reg_write(UC_X86_REG_ESP, SP0); mu.reg_write(UC_X86_REG_EAX, HEX)
    mu.emu_start(UPD, RET, count=100000)
    assert mu.reg_read(UC_X86_REG_EIP) == RET and mu.reg_read(UC_X86_REG_ESP) == SP0 + 4
    hx = bytes(mu.mem_read(HEX + 0x14, 12))
    mask, edge, bases = hx[0], hx[1] & 0x3F, list(hx[6:12])
    # shore block
    EBP = 0x190000
    w(EBP - 0x1C, 0x300600); w(EBP - 0x10, 100); w(EBP - 0xC, 200); w(EBP + 8, 0xDC)
    mu.reg_write(UC_X86_REG_EBP, EBP); mu.reg_write(UC_X86_REG_ESI, HEX); mu.reg_write(UC_X86_REG_ESP, SP0)
    mu.reg_write(UC_X86_REG_EBX, 0)
    end = {}

    def stop(uc, addr, size, _):
        if addr in (SHORE_END, SHORE_RET):
            end["at"] = addr; end["esp"] = uc.reg_read(UC_X86_REG_ESP); uc.emu_stop()
    mu.hook_add(UC_HOOK_CODE, stop)
    mu.emu_start(SHORE, RET, count=100000)
    assert end.get("esp") == SP0, end
    return mask, edge, [b if mask >> i & 1 else None for i, b in enumerate(bases)], drawn, end["at"] == SHORE_END


def main():
    fails = 0
    L, Wc = "L", "W"
    grass = (2, L)
    single = [0xD, 0x11, 0xF, 0x17, 0xE, 0x10]

    def chk(name, got, want):
        nonlocal fails
        ok = got == want
        print("  %-58s %s" % (name, "ok" if ok else "FAIL\n     got  %r\n     want %r" % (got, want)))
        fails += not ok
    for kind in (L, Wc):                      # whichever hexagon class the cave tiles really are
        tag = "cave tiles = %s" % ("land hexagons" if kind == L else "lower hexagons")
        m, e, b, dr, done = run(0, [(0xA, kind)] * 6)
        chk("water ringed by cave water (%s)" % tag, (m, e, b, sorted(dr), done),
            (0x3F, 0, [0x80] * 6, [0x220 + s * 4 + 3 for s in range(6)], True))
        m, e, b, dr, done = run(6, [(0xD, kind)] * 6)
        chk("ice ringed by cave ice (%s)" % tag, (m, e, b, sorted(dr), done),
            (0x3F, 0, [0x80] * 6, [0x220 + s * 4 + 3 for s in range(6)], True))
        m, e, b, dr, done = run(0, [(0xD, kind), (0, Wc), (0, Wc), (0xA, kind), (0xA, kind), (0, Wc)])
        chk("water: cave ice top, cave water bottom + LL (%s)" % tag, (m, e, b, sorted(dr), done),
            (0b011001, 0, [0x88, None, None, 0x80, 0x80, None], sorted([0x238 + 0, 0x220 + 12 + 1, 0x220 + 16 + 2]), True))
        m, e, b, dr, done = run(6, [(0xA, kind), grass, (6, Wc), (6, Wc), (6, Wc), (6, Wc)])
        chk("ice: cave water top, grass UR (%s)" % tag, (m, e, b, sorted(dr), done),
            (0b000011, 0, [0x88, 0, None, None, None, None], sorted([0x238, 0 + single[1]]), True))
    m, e, b, dr, done = run(0, [(6, Wc), grass, (0, Wc), (0, Wc), (0, Wc), (0, Wc)])
    chk("water: ice top (edge bit kept), grass UR -> engine path", (m, e, b, dr, done), (0b10, 1, [None, 0] + [None] * 4, [], False))
    m, e, b, dr, done = run(0, [(0xE, L), (0xA, L), (0, Wc), (0, Wc), (0, Wc), (0, Wc)])
    chk("water: sky top, cave water UR", (m, e, b[:2], sorted(dr), done),
        (0b11, 0, [b[0], 0x80], sorted([0x100 + 0 * 48 + ((b[0] - 0xA0) // 0x20) * 16, 0x220 + 4]), True))
    m, e, b, dr, done = run(0, [(0, Wc)] * 6)
    chk("open water", (m, e, dr, done), (0, 0, [], True))
    un = run(0, [(0xA, L)] * 6, patched=False)
    print("  (unpatched, cave water as land: mask %#x edge %#x bases %s)" % (un[0], un[1], un[2]))
    un = run(0, [(0xA, Wc)] * 6, patched=False)
    print("  (unpatched, cave water as lower hexagon: mask %#x edge %#x)" % (un[0], un[1]))
    # HEXTRANS rule hook (TAoWHexagon.UpdateTransition tail): own / neighbour terrain, upper neighbour class
    def rule(own, nb, bl, lower_cls):
        mu = machine(True)
        w = lambda a, v: mu.mem_write(a, struct.pack("<I", v & 0xFFFFFFFF))  # noqa: E731
        r = lambda a: struct.unpack("<I", bytes(mu.mem_read(a, 4)))[0]       # noqa: E731
        HEX, FLD = 0x300000, 0x300100
        w(HEX + 4, FLD); w(FLD + 4, 0x300200); mu.mem_write(HEX + 0x10, bytes([0xFF] * 4))
        w(CLS_LOWER, 0xC1A55001)
        SP0 = 0x180000
        w(SP0, 0); w(SP0 + 4, 7); w(SP0 + 8, 9)
        res = {}

        def hook(uc, addr, size, _):
            sp = uc.reg_read(UC_X86_REG_ESP)
            if addr == T_GETFIELD:
                assert (uc.reg_read(UC_X86_REG_EAX), uc.reg_read(UC_X86_REG_EDX), uc.reg_read(UC_X86_REG_ECX)) == \
                    (0x300200, 7, 9)
                uc.reg_write(UC_X86_REG_EAX, 0x301000); uc.reg_write(UC_X86_REG_EIP, r(sp)); uc.reg_write(UC_X86_REG_ESP, sp + 4)
            elif addr == T_FIND:
                assert uc.reg_read(UC_X86_REG_EDX) == 0xC1A55001
                uc.reg_write(UC_X86_REG_EAX, 1 if lower_cls else 0); uc.reg_write(UC_X86_REG_EIP, r(sp)); uc.reg_write(UC_X86_REG_ESP, sp + 4)
            elif addr == W.B2_OLD:
                res["at"] = "old"; res["al"] = uc.reg_read(UC_X86_REG_EAX) & 0xFF
        mu.hook_add(UC_HOOK_CODE, hook)
        for reg, v in ((UC_X86_REG_EAX, 0xAABBCC00 | own), (UC_X86_REG_EDI, nb), (UC_X86_REG_ESI, HEX),
                       (UC_X86_REG_EBX, 0x11223300 | bl), (UC_X86_REG_ESP, SP0)):
            mu.reg_write(reg, v)
        mu.mem_write(W.B2_OLD, bytes([0xE9]) + struct.pack("<i", 0x5579AC88 - (W.B2_OLD + 5)))
        mu.emu_start(0x5579AA92, 0x5579AC88, count=10000)
        assert mu.reg_read(UC_X86_REG_EIP) == 0x5579AC88 and mu.reg_read(UC_X86_REG_ESP) == SP0 and mu.reg_read(UC_X86_REG_ESI) == HEX and mu.reg_read(UC_X86_REG_EBX) == 0x11223300 | bl
        return res.get("at", "exit"), bytes(mu.mem_read(HEX + 0x10, 4))[bl], res.get("al")
    for (lo, up), base in W.PAIR_ID.items():
        for bl in range(3):
            at, slot, _ = rule(lo, up, bl, False)
            chk("rule %X under plain %X, bl %d -> fade %#x" % (lo, up, bl, base + bl), (at, slot), ("exit", base + bl))
        if up in (0, 6):
            chk("rule %X under water-class %X -> nothing" % (lo, up), rule(lo, up, 1, True)[:2], ("exit", 0xFF))
    for own, nb in ((2, 0), (0, 2), (0xA, 9), (0xE, 0), (0, 6), (0xA, 0xD), (6, 0xE)):
        at, slot, al = rule(own, nb, 2, False)
        chk("rule %X / %X untouched" % (own, nb), (at, slot, al), ("old", 0xFF, own))
    print("TEST %s" % ("FAILED" if fails else "passed"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
