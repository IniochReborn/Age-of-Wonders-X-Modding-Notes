#!/usr/bin/env python3
r"""FIX: Hero-Slaying ranged bonus crashes when the TARGET is a combat wall.

THE BUG (found by the 2026-08-12 combat-object audit; same family as
build_wall_damage_rank_crash_fix.py)
    In the ranged-attack cave @0x5580E500 (hooked at
    AoWE.TRangedAttackAbility.CreateRangedAttackCA+0x50) the Hero-Slaying
    (ability 0x38) branch does:

        mov edx,[delta+0x55711FAC]   ; THero class
        mov eax,[ebp-4]              ; the TARGET combat object
        mov eax,[eax+0x4c]           ; <-- assumed to be the target's TUnit
        test eax,eax / je skip       ; ONLY a nil check
        call System.@IsClass         ; <-- dereferences eax's VMT

    `[obj+0x4C]` is the underlying TUnit only on TCombatUnit/TFastCombatUnit.
    On a **TCombatWall** it is a packed BYTE pair (type at +0x4C, hit points at
    +0x4D - see TCombatWall.GetHits @0x55725C30 / GetHitPoints @0x55725C3C), so
    the dword read comes back as a small integer such as 1. That is non-nil, so
    it survives the nil check and @IsClass then does `mov eax,[eax]` on it =>
    access violation. Net effect: **a Hero-Slaying unit shooting a city or fort
    wall crashes the combat**, which the turn-event handler swallows.

THE FIX
    Replace the 10 bytes

        mov eax,[ebp-4] / mov eax,[eax+0x4c] / test eax,eax / je skip

    with

        mov eax,[ebp-4] / call helper / je skip          (also 10 bytes)

    helper (cave, 46 B) returns the underlying TUnit *only* when the object
    really IsClass TCombatUnit (which also covers TFastCombatUnit), else nil,
    and sets ZF so the caller's `je` still works. Walls now simply get no
    Hero-Slaying bonus - the correct answer, since a wall is not a hero.
    ⚠ EDX must survive: the caller loaded the THero class into it two
    instructions earlier and uses it for the @IsClass that follows. The helper
    saves and restores it.

    Cave @0x55810F00, PIC (call/pop delta; `lea edx,[delta+0x55715A94]` = the
    runtime TCombatUnit VMT). Backup: AoWEPACK.dll.bak_rangedheroslay.
    Dry-run default; --apply / --revert.
"""
import os, shutil, struct, sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DLL = os.path.join(GAME, "AoWEPACK.dll")
BAK = DLL + ".bak_rangedheroslay"

VA2FILE = 0x55700C00
CAVE_BASE, CAVE_LIMIT = 0x55810F00, 0x55810F80

PATCH_AT = 0x5580E573
PATCH_LEN = 10
SKIP_TO = 0x5580E5A0
VMT_TCOMBATUNIT = 0x55715A94
F_ISCLASS = 0x557010C0
OLD = bytes.fromhex("8b45fc8b40 4c85c07423".replace(" ", ""))


def build_cave():
    base = CAVE_BASE
    buf = bytearray(); rel = []; labels = {}; jcc8 = []

    def db(*b): buf.extend(b)
    def dd(v): buf.extend((v & 0xFFFFFFFF).to_bytes(4, 'little'))
    def call(t): db(0xE8); rel.append((len(buf), t)); dd(0)
    def lab(n): labels[n] = len(buf)
    def j8(op, n): db(op); jcc8.append((len(buf), n)); db(0)

    # eax = combat object (may be nil). Must preserve EDX (holds the THero class).
    db(0x85, 0xC0)                  # test eax,eax
    j8(0x74, 'zero')
    db(0x52)                        # push edx      (save THero class)
    db(0x50)                        # push eax      (save the object)
    call(base + len(buf) + 5)       # delta trick
    popva = base + len(buf)
    db(0x5A)                        # pop edx
    db(0x81, 0xEA); dd(popva)       # sub edx, static -> delta
    db(0x8D, 0x92); dd(VMT_TCOMBATUNIT)   # lea edx,[edx+VMT] -> runtime class
    call(F_ISCLASS)                 # eax = object, edx = class -> al
    db(0x59)                        # pop ecx       (ecx = the object)
    db(0x5A)                        # pop edx       (restore THero class)
    db(0x84, 0xC0)                  # test al,al
    j8(0x74, 'zero')
    db(0x8B, 0x41, 0x4C)            # mov eax,[ecx+0x4c]   (the real TUnit)
    db(0x85, 0xC0)                  # test eax,eax         (ZF for the caller)
    db(0xC3)                        # ret
    lab('zero')
    db(0x33, 0xC0)                  # xor eax,eax
    db(0x85, 0xC0)                  # test eax,eax         (ZF=1 -> caller skips)
    db(0xC3)                        # ret

    for off, tgt in rel:
        buf[off:off+4] = (tgt - (base + off + 4)).to_bytes(4, 'little', signed=True)
    for off, n in jcc8:
        dtl = labels[n] - (off + 1)
        assert -128 <= dtl <= 127, (n, dtl)
        buf[off] = dtl & 0xFF
    assert base + len(buf) <= CAVE_LIMIT, hex(len(buf))
    return bytes(buf)


def build_patch():
    b = bytearray()
    b += b"\x8B\x45\xFC"                                   # mov eax,[ebp-4]
    site = PATCH_AT + len(b)
    b += b"\xE8" + (CAVE_BASE - (site + 5)).to_bytes(4, 'little', signed=True)
    site = PATCH_AT + len(b)
    disp = SKIP_TO - (site + 2)
    assert -128 <= disp <= 127, hex(disp)
    b += b"\x74" + bytes([disp & 0xFF])                    # je skip
    assert len(b) == PATCH_LEN, len(b)
    return bytes(b)


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
    patch = build_patch()
    p_off = PATCH_AT - VA2FILE
    c_off = CAVE_BASE - VA2FILE

    hits = reloc_hits(bytes(d), [(p_off, p_off + PATCH_LEN), (c_off, c_off + len(cave))])
    assert not hits, ["reloc in patch range: " + hex(x) for x in hits]

    cur = bytes(d[p_off:p_off + PATCH_LEN])
    assert cur == OLD or cur[:3] == b"\x8B\x45\xFC" and cur[3] == 0xE8, \
        "unexpected bytes at 0x%X: %s" % (PATCH_AT, cur.hex())
    curc = bytes(d[c_off:c_off + len(cave)])
    assert curc == bytes(len(cave)) or curc[:2] == cave[:2], "cave not free: " + curc[:8].hex()

    d[c_off:c_off + len(cave)] = cave
    d[p_off:p_off + PATCH_LEN] = patch
    print("cave %d B @0x%X; patch %d B @0x%X -> skip 0x%X"
          % (len(cave), CAVE_BASE, len(patch), PATCH_AT, SKIP_TO))
    print("Hero-Slaying ranged bonus now requires the target to be a TCombatUnit")
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
