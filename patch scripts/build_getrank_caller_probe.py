#!/usr/bin/env python3
r"""DIAGNOSTIC #2: name the caller that passes a bogus unit pointer to
AoWE.TUnit.GetRank.

CONTEXT
    Keeper2.csm reproduces "Exception occured during TArmyCombatMoveTE".
    build_te_exception_detail.py revealed the real fault:

        Access violation at address 0122294F in module 'AoWEPACK.dll'.
        Read of address 0000003D

    0x0122294F - base 0x011A0000 + 0x55700000 = 0x5578294F =
    AoWE.TUnit.GetRank+0x3, i.e. `mov dl, byte ptr [eax+0x3c]`.
    Read address 0x3D = eax + 0x3C  =>  **eax = 1**, not nil - somebody calls
    TUnit.GetRank with the integer 1 as Self. GetRank has 19 direct callers
    (TUnit.GetAttack/GetDefense/GetDamage/GetResistance/ShowEx/SetRank/
    SetUnitResource/NewDay, TArena.UnitTrainCost, and the mod's SetExperience
    cave @0x5580FF20), so the faulting instruction alone cannot identify it.

WHAT THIS DOES
    Guards GetRank's entry: if Self < 0x10000 it deliberately faults reading
    (staticVA(return address) | 0x80000000). The existing Network.dpl dialog
    then prints

        Read of address 8XXXXXXX

    where XXXXXXX & 0x7FFFFFFF is the **static VA of the instruction after the
    offending `call TUnit.GetRank`** - already rebase-corrected by the cave, so
    it can be looked up directly with dasm.py without re-reading module bases.
    The normal path costs one cmp + one jb.

HOW
    Hook: 6 bytes at TUnit.GetRank 0x5578294C (`push ebx; xor edx,edx;
    mov dl,[eax+0x3c]`) -> `jmp cave` + nop. Cave @0x55810E80 replays those
    three instructions and jmps back to 0x55782952. PIC: the static-VA
    conversion uses the call/pop delta trick (AoWEPACK rebases - it loaded at
    0x011A0000 in the observed run).

    Backup: AoWEPACK.dll.bak_rankprobe. Dry-run default; --apply / --revert.

THIS IS A DIAGNOSTIC BUILD - revert it (and build_te_exception_detail.py)
before shipping.
"""
import os, shutil, struct, sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DLL = os.path.join(GAME, "AoWEPACK.dll")
BAK = DLL + ".bak_rankprobe"

VA2FILE = 0x55700C00
CAVE_BASE, CAVE_LIMIT = 0x55810E80, 0x55810F80
H_SITE = 0x5578294C                                  # TUnit.GetRank entry
H_OLD = bytes.fromhex("5331d28a503c")                # push ebx; xor edx,edx; mov dl,[eax+3c]
H_BACK = 0x55782952                                  # resume: cmp dl,0xa
MIN_PTR = 0x10000                                    # anything below = bogus Self


def build_cave():
    base = CAVE_BASE
    buf = bytearray(); rel = []; labels = {}; jcc8 = []

    def db(*b): buf.extend(b)
    def dd(v): buf.extend((v & 0xFFFFFFFF).to_bytes(4, 'little'))
    def jmp(t): db(0xE9); rel.append((len(buf), t)); dd(0)
    def lab(n): labels[n] = len(buf)
    def j8(op, n): db(op); jcc8.append((len(buf), n)); db(0)

    db(0x3D); dd(MIN_PTR)           # cmp eax, 0x10000
    j8(0x72, 'bogus')               # jb bogus
    # ---- normal path: the displaced original instructions ----
    db(0x53)                        # push ebx
    db(0x31, 0xD2)                  # xor edx,edx
    db(0x8A, 0x50, 0x3C)            # mov dl,[eax+0x3c]
    jmp(H_BACK)
    # ---- bogus path: encode the caller's return address into an AV ----
    lab('bogus')
    db(0x8B, 0x0C, 0x24)            # mov ecx,[esp]      (caller's return addr, runtime)
    db(0xE8); dd(0)                 # call $+5
    popva = base + len(buf)
    db(0x5A)                        # pop edx
    db(0x81, 0xEA); dd(popva)       # sub edx, static    -> edx = runtime-static delta
    db(0x29, 0xD1)                  # sub ecx, edx       -> ecx = STATIC VA of return addr
    db(0x81, 0xC9); dd(0x80000000)  # or ecx, 0x80000000 -> guaranteed unmapped
    db(0x8B, 0x09)                  # mov ecx,[ecx]      -> AV names the address
    db(0xC3)                        # ret (never reached)

    for off, tgt in rel:
        buf[off:off+4] = (tgt - (base + off + 4)).to_bytes(4, 'little', signed=True)
    for off, n in jcc8:
        dtl = labels[n] - (off + 1)
        assert -128 <= dtl <= 127, (n, dtl)
        buf[off] = dtl & 0xFF
    assert base + len(buf) <= CAVE_LIMIT, hex(len(buf))
    return bytes(buf)


def reloc_hits(data, ranges):
    e = struct.unpack_from('<I', data, 0x3C)[0]; opt = e + 24
    nsec = struct.unpack_from('<H', data, e + 6)[0]
    osz = struct.unpack_from('<H', data, e + 20)[0]
    rrva, rsz = struct.unpack_from('<II', data, opt + 96 + 5*8)
    secs = []; p = opt + osz
    for _ in range(nsec):
        vs, va, rs, raw = struct.unpack_from('<IIII', data, p + 8)
        secs.append((va, vs, raw, rs)); p += 40

    def r2o(rva):
        for va, vs, raw, rs in secs:
            if va <= rva < va + max(vs, rs):
                return raw + rva - va

    off = r2o(rrva)
    if off is None or rsz == 0:
        return []
    end = off + rsz; hits = []
    while off < end:
        page, blk = struct.unpack_from('<II', data, off)
        if blk < 8:
            break
        for i in range((blk - 8)//2):
            w = struct.unpack_from('<H', data, off + 8 + i*2)[0]
            if w >> 12 == 0:
                continue
            fo = r2o(page + (w & 0xFFF))
            if fo is None:
                continue
            for lo, hi in ranges:
                if lo <= fo + 3 and fo < hi:
                    hits.append(fo)
        off += blk
    return hits


def main():
    apply = "--apply" in sys.argv
    revert = "--revert" in sys.argv
    if revert:
        if os.path.exists(BAK):
            shutil.copy2(BAK, DLL)
            print("restored AoWEPACK.dll from", os.path.basename(BAK))
            return 0
        print("no backup found:", BAK)
        return 1

    d = bytearray(open(DLL, 'rb').read())
    cave = build_cave()
    h_off = H_SITE - VA2FILE
    c_off = CAVE_BASE - VA2FILE

    hits = reloc_hits(bytes(d), [(h_off, h_off + 6), (c_off, c_off + len(cave))])
    assert not hits, ["reloc in patch range: " + hex(x) for x in hits]

    cur = bytes(d[h_off:h_off+6])
    assert cur == H_OLD or cur[0] == 0xE9, "unexpected bytes at GetRank: " + cur.hex()
    curc = bytes(d[c_off:c_off+len(cave)])
    assert curc == bytes(len(cave)) or curc[:1] == cave[:1], \
        "cave not free: " + curc[:8].hex()

    d[c_off:c_off+len(cave)] = cave
    d[h_off:h_off+6] = bytes([0xE9]) + (CAVE_BASE - (H_SITE + 5)).to_bytes(4, 'little', signed=True) + b'\x90'

    print("cave %d B @0x%X (limit 0x%X)" % (len(cave), CAVE_BASE, CAVE_LIMIT))
    print("hook: TUnit.GetRank @0x%X -> cave, resume 0x%X" % (H_SITE, H_BACK))
    print("on a bogus Self the dialog will read: 'Read of address 8XXXXXXX'")
    print("  -> static VA of the calling instruction's return = value & 0x7FFFFFFF")
    if not apply:
        print("Dry run OK - rerun with --apply (or --revert).")
        return 0
    if not os.path.exists(BAK):
        shutil.copy2(DLL, BAK)
        print("Backup ->", os.path.basename(BAK))
    open(DLL, 'wb').write(d)
    print("Written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
