#!/usr/bin/env python3
r"""Scenario-start HP top-up: map-placed units start at the CURRENT max HP.

PROBLEM (user-reported): maps store each placed unit's current HP as a byte
([unit+0x3e], serialized as property 9 in TUnit.ReadWrite). When the mod raises
a unit type's max HP (e.g. Battering Ram 12 -> 15), units already placed in
old maps keep the stored 12 and start the scenario at 12/15 (permanently
wounded-looking) until healed.

FIX: at SCENARIO START ONLY, top every unit up to its own current max HP.
Hook = AoWE.TAoWHSMap.StartNewMap @0x55777D68, which the engine calls only when
a new game/scenario begins (it seeds starting gems/mana per player) — NEVER on
save load (that path is StartLoadedMap @0x55777F10). So a wounded unit in a
saved game is never touched, and a designer's mid-scenario damage is preserved
only insofar as it was never expressible: map placement stores full HP for the
unit type as authored, so topping up = "author meant a healthy unit".

Cave (@0x55810D80): run the original StartNewMap first, then iterate
[AoWHSMap 0x558FA040 + 0xFC] (TUnitControl) via GetCount/GetUnit and per unit:
  maxhp = vcall [unit_vmt+0xD0]        (GetHits; the mod's own HP formula)
  cur   = vcall [unit_vmt+0xCC]        (GetHitPoints)
  if 0 < cur < maxhp: vcall [unit_vmt+0xD4](edx=maxhp)   (SetHitPoints, which
                                        clamps and refreshes defensive strength)
cur==0 is skipped (dead/uninitialised sentinel). Only raises, never lowers, so
a unit type whose HP was LOWERED keeps SetHitPoints' own clamp behaviour.
Deterministic from map state => identical on every machine => LAN-safe.

VMT slots verified by scanning BOTH TUnit (@0x55710CAC) and THero (@0x55711FEC)
vtables for the known method addresses: +0xD0 GetHits (max), +0xE0
GetHitPoints (current, reads [+0x3e]), +0xE4 SetHitPoints. (+0xCC/+0xD4 are
GetResistance/GetMoves — do NOT use.)

Hook: 5 bytes at StartNewMap entry -> jmp cave (no reloc in either range —
asserted). Cave is PIC (globals via delta; calls rel32).
Backup: AoWEPACK.dll.bak_hptopup. Dry-run default; --apply / --revert.
"""
import os, shutil, struct, sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DLL = os.path.join(GAME, "AoWEPACK.dll")
BAK = DLL + ".bak_hptopup"

VA2FILE = 0x55700C00
CAVE_BASE, CAVE_LIMIT = 0x55810D80, 0x55810E80
H_SITE = 0x55777D68                     # TAoWHSMap.StartNewMap entry
H_OLD  = bytes.fromhex("5356578bd8")    # push ebx;push esi;push edi;mov ebx,eax
H_RESUME = H_SITE + 5
GLOB_MAP     = 0x558FA040               # -> TAoWHSMap; +0xFC = TUnitControl
F_GETCOUNT   = 0x5577E908
F_GETUNIT    = 0x5577E93C
VMT_GETHITS  = 0xD0                     # GetHits    (max HP; mod's HP cave)
VMT_GETHP    = 0xE0                     # GetHitPoints (current, reads [+0x3e])
VMT_SETHP    = 0xE4                     # SetHitPoints (clamps + UpdateDefensive)


def build_cave():
    """Top-up pass, then fall through into StartNewMap's real body.

    NOTE: StartNewMap ends with `pop edi/esi/ebx; ret`, balancing its own
    3-push prologue. We must therefore NEVER `call` into the body from a frame
    holding extra data — an inserted return address makes those pops consume
    the wrong slots and the `ret` jump to garbage. Instead: run the top-up
    inside a pushad/popad sandwich, then replay the displaced prologue and JMP
    to the body so its epilogue returns straight to TAoWHSMap.Activate.
    """
    base = CAVE_BASE
    buf = bytearray(); rel = []; labels = {}; jrel = []
    def db(*b): buf.extend(b)
    def dd(v): buf.extend((v & 0xFFFFFFFF).to_bytes(4, 'little'))
    def call(t): db(0xE8); rel.append((len(buf), t)); dd(0)
    def jmp(t): db(0xE9); rel.append((len(buf), t)); dd(0)
    def lab(n): labels[n] = len(buf)
    def j8(op, n): db(op); jrel.append((len(buf), n)); db(0)

    db(0x60)                        # pushad (eax = map, preserved throughout)
    call(base + len(buf) + 5)       # delta trick
    popva = base + len(buf)
    db(0x5B)                        # pop ebx
    db(0x81, 0xEB); dd(popva)       # sub ebx, static -> ebx = load delta
    db(0x8B, 0xA8); dd(0xFC)        # mov ebp,[eax+0xfc] (unit control)
    db(0x85, 0xED)                  # test ebp,ebp
    j8(0x74, 'done')
    db(0x8B, 0xC5)                  # mov eax,ebp
    call(F_GETCOUNT)                # -> eax = count  (clobbers eax only)
    db(0x8B, 0xF8)                  # mov edi,eax
    db(0x33, 0xF6)                  # xor esi,esi
    lab('loop')
    db(0x3B, 0xF7)                  # cmp esi,edi
    j8(0x7D, 'done')                # jge done
    db(0x8B, 0xC5)                  # mov eax,ebp
    db(0x8B, 0xD6)                  # mov edx,esi
    call(F_GETUNIT)                 # -> eax = unit
    db(0x85, 0xC0)                  # test eax,eax
    j8(0x74, 'next')
    db(0x50)                        # push eax (unit)
    db(0x8B, 0x10)                  # mov edx,[eax]
    db(0xFF, 0x92); dd(VMT_GETHITS) # call [vmt+0xd0] GetHits -> al = max
    db(0x0F, 0xB6, 0xC8)            # movzx ecx,al
    db(0x58)                        # pop eax (unit)
    db(0x51)                        # push ecx (max)
    db(0x50)                        # push eax (unit)
    db(0x8B, 0x10)                  # mov edx,[eax]
    db(0xFF, 0x92); dd(VMT_GETHP)   # call [vmt+0xe0] GetHitPoints -> al = cur
    db(0x0F, 0xB6, 0xD0)            # movzx edx,al
    db(0x58)                        # pop eax (unit)
    db(0x59)                        # pop ecx (max)
    db(0x85, 0xD2)                  # test edx,edx
    j8(0x74, 'next')                # cur == 0 -> skip (dead/uninit)
    db(0x3B, 0xD1)                  # cmp edx,ecx
    j8(0x7D, 'next')                # cur >= max -> nothing to do
    db(0x8B, 0xD1)                  # mov edx,ecx (new hp = max)
    db(0x8B, 0x08)                  # mov ecx,[eax]
    db(0xFF, 0x91); dd(VMT_SETHP)   # call [vmt+0xe4] SetHitPoints
    lab('next')
    db(0x46)                        # inc esi
    j8(0xEB, 'loop')
    lab('done')
    db(0x61)                        # popad (restores eax = map)
    db(0x53, 0x56, 0x57)            # displaced prologue: push ebx/esi/edi
    db(0x8B, 0xD8)                  # mov ebx,eax
    jmp(H_RESUME)                   # body runs and returns to Activate itself

    for off, tgt in rel:
        buf[off:off+4] = (tgt - (base + off + 4)).to_bytes(4, 'little', signed=True)
    for off, n in jrel:
        dtl = labels[n] - (off + 1)
        assert -128 <= dtl <= 127, (n, dtl)
        buf[off] = dtl & 0xFF
    assert base + len(buf) <= CAVE_LIMIT, hex(len(buf))
    return bytes(buf)


def reloc_hits(data, ranges):
    e = struct.unpack_from('<I', data, 0x3C)[0]; opt = e + 24
    nsec = struct.unpack_from('<H', data, e + 6)[0]; osz = struct.unpack_from('<H', data, e + 20)[0]
    rrva, rsz = struct.unpack_from('<II', data, opt + 96 + 5*8)
    secs = []; p = opt + osz
    for _ in range(nsec):
        vs, va, rs, raw = struct.unpack_from('<IIII', data, p + 8); secs.append((va, vs, raw, rs)); p += 40
    def r2o(rva):
        for va, vs, raw, rs in secs:
            if va <= rva < va + max(vs, rs): return raw + rva - va
    off = r2o(rrva); end = off + rsz; hits = []
    while off < end:
        page, blk = struct.unpack_from('<II', data, off)
        for i in range((blk - 8)//2):
            w = struct.unpack_from('<H', data, off + 8 + i*2)[0]
            if w >> 12 == 0: continue
            fo = r2o(page + (w & 0xFFF))
            if fo is None: continue
            for lo, hi in ranges:
                if lo <= fo + 3 and fo < hi: hits.append(fo)
        off += blk
    return hits


def main():
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if revert:
        if os.path.exists(BAK):
            shutil.copy2(BAK, DLL); print("restored AoWEPACK.dll"); return 0
        print("no backup"); return 1
    d = bytearray(open(DLL, 'rb').read())
    cave = build_cave()
    h_off = H_SITE - VA2FILE; c_off = CAVE_BASE - VA2FILE
    hits = reloc_hits(bytes(d), [(h_off, h_off+5), (c_off, c_off+len(cave))])
    assert not hits, [hex(x) for x in hits]
    cur = bytes(d[h_off:h_off+5])
    assert cur == H_OLD or cur[0] == 0xE9, cur.hex()
    curc = bytes(d[c_off:c_off+len(cave)])
    assert curc == bytes(len(cave)) or curc[:3] == cave[:3], curc[:8].hex()
    d[c_off:c_off+len(cave)] = cave
    d[h_off:h_off+5] = bytes([0xE9]) + (CAVE_BASE - (H_SITE+5)).to_bytes(4, 'little', signed=True)
    print("cave %dB @0x%X; StartNewMap @0x%X -> jmp cave" % (len(cave), CAVE_BASE, H_SITE))
    if not apply:
        print("Dry run OK — rerun with --apply (or --revert)."); return 0
    if not os.path.exists(BAK):
        shutil.copy2(DLL, BAK); print("Backup ->", os.path.basename(BAK))
    open(DLL, 'wb').write(d)
    print("Written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
