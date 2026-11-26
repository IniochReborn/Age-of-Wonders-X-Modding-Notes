#!/usr/bin/env python3
r"""
Map levels: Firmament + Abyss I..XXV = up to 29 levels - engine half (AoWEPACK.dll, 2026-10-31).
Port + generalisation of BXL's Ziggurat (5 levels: Firmament idx 3, Abyss idx 4).

Level indices: 0 Surface, 1 Caverns, 2 Depths (vanilla), 3 Firmament, 4..28 Abyss I..XXV.
Display / stacking order (what "up" and "down" mean): Firmament(3) > Surface(0) > Caverns(1) > Depths(2) >
Abyss(4) > Abyss II(5) > ... > Abyss XXV(28).
User rulings 10/31: Firmament counts as SURFACE for every spell/ability check; Abyss levels behave like Depths
(vanilla only ever tests level == 0, so every Abyss level is "underground" automatically - scanned: no
Caverns/Depths-specific spell or ability test exists); no Ziggurat depth-morale; Firmament +3 sight (cap 15).

  A  TAoWHSMap.AddMapLevel cap 0x5577768E: 3 -> 29 (the only constant cap in the dll).
  B  InitializeMapLevel 0x5577747E: level 3 is filled with Sky (0xE), every other new level with EarthWall.
  C  VisibilityRange 0x55780F32 / 0x55780F4C: Firmament = surface (no Night Vision needed, no halving);
     0x55780F79: Firmament +3 sight, capped at 15 (Ziggurat).
  D  Global-target spells 0x5579E78B, storms 0x557CDCC8 + AI 0x557CDF88, Bird's View 0x557EAB90: castable on
     the Firmament like on the Surface.
  E  Caves / tunnels (TCave Destroy, CanPlace, PlaceHX x4, MoveExclusive x2, EnterMovePoints, CanEnterSelection,
     EnterEx, ArmyPlaced = 14 sites): the twin is the NEIGHBOUR IN DISPLAY ORDER, not level +-1 (vanilla would
     dig a Depths "down" cave into the Firmament).  Ziggurat's cave block 0x55844000..0x558442E8 copied
     byte-for-byte, rel32 exits re-targeted, its order helper replaced by a 29-level arithmetic one (no
     disabled-level mask; up/down beyond the map's level count = no neighbour).
  S  Our own surface-only rules now also accept the Firmament (level 0 or 3): Path of Sand 0x5580F3D1, frost Ice
     Storm 0x55816004, Town Quake 0x55816F2A, unit bridge cost 0x5581B720, Overgrowth/Ice Age 0x55824674 /
     0x558248F4, Rejuvenate/Wither 0x55862498, Drought 0x55864004.
     ⚠ those sites live in other scripts' zones -> revert THIS script before re-running / reverting them.
Zone AoWEPACK 0x55851100..0x55851700 ('MLV1'); PIC (rel32 + call/pop delta for the map global).
Not here (later steps): editor/game level UI, Firmament sky overlay, fly up/down for flyers.
Dry-run default; --apply / --revert.  Backup AoWEPACK.dll.bak_maplevels.
"""
import os, shutil, struct, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DLL, VAN, BASE = game_file("AoWEPACK.dll"), game_file("AoWEPACK.dpl"), 0x55700000
ZIG = r"C:\Users\<user>\Desktop\AoW Ziggurat\Ziggurat\AoWEPACK.dpl"
ZONE, ZONE_END = 0x55851100, 0x55851700
MAGIC = b"MLV1"
ZB_OLD, ZB_END = 0x55844000, 0x558442E8          # Ziggurat block (helper at 0x55844308 and stream hook excluded)
BLK = ZONE + 0x10                                 # new block base (keeps all internal offsets)
HELPER = BLK + 0x308                              # same offset as Ziggurat's helper
SIGHT = ZONE + 0x3C0
STUBS = ZONE + 0x400
GLOBAL_MAP = 0x558FA040                           # AoWE.AoWHSMap (nil in the editor)
ENTRIES = [0x000, 0x020, 0x040, 0x060, 0x080, 0x0A0, 0x0C0, 0x0E0, 0x100, 0x128, 0x13C, 0x14C, 0x16C, 0x180,
           0x1A0, 0x1B4, 0x1C4, 0x1D4, 0x1E4, 0x1F4, 0x214, 0x234, 0x254]
HOOKS = [  # site, length (Ziggurat's E9 hook into his block)
    (0x5577747E, 5), (0x55780F32, 5), (0x55780F4C, 5), (0x5579E78B, 6), (0x557CDCC8, 6), (0x557CDF88, 6),
    (0x557EAB90, 6), (0x557B3494, 5), (0x557B34D4, 5), (0x557B3652, 15), (0x557B36BB, 5), (0x557B36FD, 5),
    (0x557B373D, 5), (0x557B377F, 5), (0x557B3810, 5), (0x557B3832, 5), (0x557B38D6, 30), (0x557B393C, 30),
    (0x557B3A8E, 33), (0x557B3E3C, 34)]
CAP_VA, CAP_OLD, CAP_NEW = 0x5577768E, 0x03, 0x1D
SIGHT_SITE, SIGHT_ORIG = 0x55780F79, bytes.fromhex("8bc65a5e5bc3")
SURFACE = [0x5580F3D1, 0x55816004, 0x55816F2A, 0x5581B720, 0x55824674, 0x558248F4, 0x55862498, 0x55864004]


def asm(src, at):
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    return bytes(Ks(KS_ARCH_X86, KS_MODE_32).asm(src, at)[0])


def relocate_block(zig):
    """copy Ziggurat's block; walk every entry recursively, re-target rel32 branches that leave it"""
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    blob = bytearray(zig[:ZB_END - ZB_OLD])
    out = bytearray(blob)
    seen, work, exits = set(), [ZB_OLD + e for e in ENTRIES], []
    while work:
        a = work.pop()
        if a in seen:
            continue
        for ins in md.disasm(bytes(blob[a - ZB_OLD:]), a):
            if ins.address in seen:
                break
            seen.add(ins.address)
            b = ins.bytes
            tgt = None
            if ins.mnemonic.startswith("j") or ins.mnemonic == "call":
                if ins.op_str.startswith("0x"):
                    tgt = int(ins.op_str, 16)
            for tok in ("0x5584", "0x558f", "0x5585"):
                assert tok not in ins.op_str or tgt is not None, ("absolute operand", hex(ins.address), ins.op_str)
            if tgt is not None:
                if ZB_OLD <= tgt < ZB_END:
                    work.append(tgt)
                elif tgt == 0x55844308:
                    pass                                   # thunk to the helper: re-pointed below
                else:
                    at = {0xE8: 1, 0xE9: 1}.get(b[0], 2 if b[0] == 0x0F else None)
                    assert at is not None and len(b) in (5, 6), ("short exit", hex(ins.address), ins.op_str)
                    assert 0x55700000 <= tgt < 0x55840000, hex(tgt)
                    p = ins.address - ZB_OLD + at
                    struct.pack_into("<i", out, p, tgt - (BLK + ins.address - ZB_OLD + len(b)))
                    exits.append(tgt)
            if ins.mnemonic == "ret" or (ins.mnemonic == "jmp" and tgt is not None):
                break
    # thunk 0x55844100 = jmp 0x55844308 -> jmp new helper
    assert blob[0x100] == 0xE9 and 0x55844105 + struct.unpack_from("<i", blob, 0x101)[0] == 0x55844308
    struct.pack_into("<i", out, 0x101, HELPER - (BLK + 0x105))
    return bytes(out), sorted(set(exits))


def helper_code():
    """NeighbourLevel(eax=level, dl=1 down / 0 up) -> eax = neighbour level or -1; preserves other regs.
    pos(L) = 0 for 3 (Firmament), L+1 for 0..2, L for 4..; inverse: 0 -> 3, 1..3 -> p-1, else p.
    A neighbour must be < the map's level count ([AoWHSMap+0x10]+0x14; 0x7F when no engine map)."""
    k = 0x11111111
    for _ in range(3):
        src = f"""
            push ebx
            push ecx
            call g
        g:
            pop  ecx
            sub  ecx, {k:#x}
            mov  ecx, dword ptr [ecx + {GLOBAL_MAP:#x}]
            mov  ebx, 0x7F
            test ecx, ecx
            jz   cnt
            mov  ecx, dword ptr [ecx + 0x10]
            test ecx, ecx
            jz   cnt
            mov  ebx, dword ptr [ecx + 0x14]
        cnt:
            test eax, eax
            js   fail
            cmp  eax, 0x7F
            jg   fail
            cmp  eax, 3
            jne  p1
            xor  eax, eax
            jmp  step
        p1:
            jg   step
            inc  eax
        step:
            test dl, dl
            jz   up
            inc  eax
            jmp  inv
        up:
            dec  eax
            js   fail
        inv:
            test eax, eax
            jnz  i1
            mov  eax, 3
            jmp  chk
        i1:
            cmp  eax, 3
            jg   chk
            dec  eax
        chk:
            cmp  eax, ebx
            jge  fail
            pop  ecx
            pop  ebx
            ret
        fail:
            or   eax, 0xFFFFFFFF
            pop  ecx
            pop  ebx
            ret
        """
        code = asm(src, HELPER)
        g = HELPER + code.index(b"\x59")             # pop ecx right after the call
        if g == k:
            return code
        k = g
    raise AssertionError("helper layout")


def py_neighbour(level, down, count):
    pos = 0 if level == 3 else (level + 1 if level < 3 else level)
    pos += 1 if down else -1
    if pos < 0:
        return -1
    lv = 3 if pos == 0 else (pos - 1 if pos <= 3 else pos)
    return lv if lv < count else -1


def sight_code():
    return asm(f"""
        cmp  byte ptr [esp + 2], 3
        jne  done
        add  esi, 3
        cmp  esi, 0xF
        jbe  done
        mov  esi, 0xF
    done:
        mov  eax, esi
        pop  edx
        pop  esi
        pop  ebx
        ret
    """, SIGHT)


def surface_stub(d, off, site, at):
    """site = `cmp byte [r+0x12],0 ; jcc short` (6 B) -> stub: ZF = (level == 0 || level == 3), same jcc"""
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    raw = d[off(site):off(site) + 6]
    i1, i2 = list(md.disasm(raw, site))[:2]
    assert i1.mnemonic == "cmp" and i1.op_str.endswith("+ 0x12], 0") and i1.size == 4, (hex(site), i1.op_str)
    assert i2.mnemonic in ("je", "jne") and i2.size == 2, (hex(site), i2.mnemonic)
    mem = i1.op_str[:-3]
    code = asm(f"""
        cmp  {mem}, 0
        je   z
        cmp  {mem}, 3
    z:
        {i2.mnemonic} {int(i2.op_str, 16):#x}
        jmp  {site + 6:#x}
    """, at)
    return raw, code


def main():
    import pefile
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    for lv, dn, cnt, want in [(0, 0, 29, 3), (3, 1, 29, 0), (0, 1, 29, 1), (2, 1, 29, 4), (4, 0, 29, 2), (4, 1, 29, 5),
                              (28, 1, 29, -1), (3, 0, 29, -1), (0, 0, 3, -1), (2, 1, 3, -1), (2, 1, 5, 4), (5, 0, 29, 4)]:
        assert py_neighbour(lv, dn, cnt) == want, (lv, dn, cnt)
    d = open(DLL, "rb").read(); v = open(VAN, "rb").read(); z = open(ZIG, "rb").read()
    pe = pefile.PE(data=d); zpe = pefile.PE(data=z, fast_load=True)
    off = lambda va: pe.get_offset_from_rva(va - BASE)  # noqa: E731
    zg = lambda va, n: zpe.get_data(va - BASE, n)  # noqa: E731
    blk, exits = relocate_block(zg(ZB_OLD, ZB_END - ZB_OLD))
    zone = bytearray(ZONE_END - ZONE)
    zone[0:4] = MAGIC
    zone[BLK - ZONE:BLK - ZONE + len(blk)] = blk
    hc = helper_code()
    zone[HELPER - ZONE:HELPER - ZONE + len(hc)] = hc
    assert HELPER + len(hc) <= SIGHT
    sc = sight_code()
    zone[SIGHT - ZONE:SIGHT - ZONE + len(sc)] = sc
    P = [(CAP_VA, bytes([CAP_OLD]), bytes([CAP_NEW]), "level cap")]
    for site, n in HOOKS:
        zb = zg(site, n)
        assert zb[0] == 0xE9, hex(site)
        zt = site + 5 + struct.unpack_from("<i", zb, 1)[0]
        assert ZB_OLD <= zt < ZB_END, (hex(site), hex(zt))
        orig = v[pefile.PE(data=v, fast_load=True).get_offset_from_rva(site - BASE):][:n] if False else None
        new = b"\xe9" + struct.pack("<i", BLK + (zt - ZB_OLD) - (site + 5)) + zb[5:]
        P.append((site, d[off(site):off(site) + n], new, "zig hook"))
    vpe = pefile.PE(data=v, fast_load=True)
    for i, (site, o, n, lab) in enumerate(P):
        if lab == "zig hook":
            vo = vpe.get_offset_from_rva(site - BASE)
            van = v[vo:vo + len(o)]
            P[i] = (site, van, n, lab)
    P.append((SIGHT_SITE, SIGHT_ORIG, b"\xe9" + struct.pack("<i", SIGHT - (SIGHT_SITE + 5)) + b"\x90", "sight"))
    at = STUBS
    for site in SURFACE:
        cur = d[off(site):off(site) + 6]
        if cur[0] == 0xE9:                                # already ours: rebuild from the backup's bytes
            b = open(bak_path(DLL, ".bak_maplevels"), "rb").read()
            src_d, src_off = b, off
        else:
            src_d, src_off = d, off
        raw, code = surface_stub(src_d, src_off, site, at)
        zone[at - ZONE:at - ZONE + len(code)] = code
        P.append((site, raw, b"\xe9" + struct.pack("<i", at - (site + 5)) + b"\x90", "surface"))
        at = (at + len(code) + 0xF) & ~0xF
    assert at <= ZONE_END, hex(at)
    P.append((ZONE, bytes(len(zone)), bytes(zone), "zone"))
    rl = {BASE + e.rva for blk_ in pe.DIRECTORY_ENTRY_BASERELOC for e in blk_.entries if e.type == 3}
    bad = [hex(r) for r in rl if any(s - 3 <= r < s + len(o) for s, o, _, _ in P)]
    sts = []
    for s, o, n, lab in P:
        c = d[off(s):off(s) + len(o)]
        sts.append("vanilla" if c == o else "ours" if c == n else "OTHER")
        if sts[-1] == "OTHER":
            print("  OTHER %s %#x: %s (want %s)" % (lab, s, c.hex(), o.hex()))
    print("%d sites %s | relocs %s | block exits %d | helper %d B @%#x | stubs end %#x"
          % (len(P), {k: sts.count(k) for k in set(sts)}, bad or "none", len(exits), len(hc), HELPER, at))
    if "OTHER" in sts or bad or len(set(sts)) != 1:
        print("ABORT"); return 1
    want = "vanilla" if revert else "ours"
    if sts[0] == want:
        print("already %s" % ("reverted" if revert else "applied")); return 0
    if not apply and not revert:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    r = subprocess.run(["tasklist"], capture_output=True, text=True).stdout
    if "AoWx.exe" in r or "AoWDevX.exe" in r:
        print("game/editor running - close it first"); return 1
    bak = bak_path(DLL, ".bak_maplevels")
    if not revert and not os.path.exists(bak):
        shutil.copy2(DLL, bak); print("backup ->", bak)
    with open(DLL, "r+b") as f:
        for s, o, n, lab in reversed(P):
            f.seek(off(s)); f.write(o if revert else n)
    d2 = open(DLL, "rb").read()
    assert all(d2[off(s):off(s) + len(o)] == (o if revert else n) for s, o, n, lab in P)
    print("reverted" if revert else "written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
