#!/usr/bin/env python3
r"""Warp Self — siege qualification: knowing (and being able to combat-cast)
Warp Self lets a hero/leader attack walled structures, exactly like knowing a
wall-breaching spell does.

Mechanism: AoWE.TSpellCastingAbility.CanCastBreachWallSpell @0x5576DEF0
(AoWEPACK.dll) loops the player's known-spell id list ([magic+0x30], index in
ebx, magic control cached at [ebp-0x18]); per spell it queries the spell's
wall-combat-features via vcall [spell_vmt+0x7C] into a 4-byte record at
[ebp-0xD] and requires bit 1 of byte [ebp-0xA] (breach), then still checks
THero.CanCastCombatSpell. Warp Self (a TCallFlames clone) reports no breach
bit, but functionally bypasses walls (teleport), so it should qualify.

Patch: the 6-byte test+branch @0x5576DF90 (`test byte [ebp-0xA],1; je +0x1E`)
becomes `call cave; nop`. Cave: if the breach bit is set -> ret (falls through
the nop to the qualify path @0x5576DF96). Else re-derive the current spell id
exactly as the surrounding code does (TIntegerList.Get([[ebp-0x18]+0x30], ebx))
and if it is 0xCA -> ret (qualify; CanCastCombatSpell still gates actual
castability); otherwise pop the return address and jmp 0x5576DFB4 (the
original reject path). Only rel32 transfers + register/frame accesses — no
absolute data refs, so no PIC and no reloc exposure (asserted anyway).

Cave: AoWEPACK 0x55810B00 (next free; stage-1 warp cave ends 0x55810B00).
Backup: AoWEPACK.dll.bak_warpsiege. Dry-run default; --apply / --revert.
"""
import os, shutil, struct, sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DLL = os.path.join(GAME, "AoWEPACK.dll")
BAK = DLL + ".bak_warpsiege"

VA2FILE = 0x55700C00
CAVE_VA, CAVE_LIMIT = 0x55810B00, 0x55810B80
H_SITE = 0x5576DF90
H_OLD = bytes.fromhex("f645f601741e")     # test byte [ebp-0xA],1 ; je 0x5576dfb4
RET_QUALIFY = 0x5576DF96                  # fall-through: CanCastCombatSpell check
J_REJECT    = 0x5576DFB4                  # original je target: not this spell
INTLIST_GET = 0x55702E94                  # thunk Engine.TIntegerList.Get
SPELL_ID = 0xCA


def build_cave():
    buf = bytearray(); base = CAVE_VA
    rel = []
    def db(*b): buf.extend(b)
    def dd(v): buf.extend((v & 0xFFFFFFFF).to_bytes(4, 'little'))
    def call(t): db(0xE8); rel.append((len(buf), t)); dd(0)
    def jmp(t): db(0xE9); rel.append((len(buf), t)); dd(0)
    db(0xF6, 0x45, 0xF6, 0x01)      # test byte [ebp-0xA],1 (displaced)
    db(0x75, 0x14)                  # jne -> qualify ret at cave+0x1A
    db(0x8B, 0x45, 0xE8)            # mov eax,[ebp-0x18] (player magic control)
    db(0x8B, 0x40, 0x30)            # mov eax,[eax+0x30] (known-spell id list)
    db(0x8B, 0xD3)                  # mov edx,ebx (loop index)
    call(INTLIST_GET)               # -> eax = spell id
    db(0x3D); dd(SPELL_ID)          # cmp eax,0xCA
    db(0x75, 0x01)                  # jne +1 -> reject
    db(0xC3)                        # qualify: ret (to the nop @+5 -> 0x5576DF96)
    db(0x83, 0xC4, 0x04)            # reject: add esp,4 (drop return addr)
    jmp(J_REJECT)
    for off, tgt in rel:
        buf[off:off+4] = (tgt - (base + off + 4)).to_bytes(4, 'little', signed=True)
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
            if va <= rva < va + max(vs, rs): return raw + rva - va
    off = r2o(rrva); end = off + rsz; hits = []
    while off < end:
        page, blk = struct.unpack_from('<II', data, off)
        if blk < 8: break
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
            shutil.copy2(BAK, DLL); print("restored AoWEPACK.dll from", os.path.basename(BAK))
            return 0
        print("no backup found"); return 1
    d = bytearray(open(DLL, 'rb').read())
    cave = build_cave()
    h_off = H_SITE - VA2FILE; c_off = CAVE_VA - VA2FILE
    cur = bytes(d[h_off:h_off+6])
    assert cur == H_OLD or cur[0] == 0xE8, cur.hex()
    curc = bytes(d[c_off:c_off+len(cave)])
    assert curc == bytes(len(cave)) or curc[:4] == cave[:4], curc[:8].hex()
    hits = reloc_hits(bytes(d), [(h_off, h_off+6), (c_off, c_off+len(cave))])
    assert not hits, [hex(x) for x in hits]
    d[c_off:c_off+len(cave)] = cave
    d[h_off:h_off+6] = bytes([0xE8]) + (CAVE_VA - (H_SITE+5)).to_bytes(4, 'little', signed=True) + b'\x90'
    print("cave %dB @VA 0x%X (file 0x%X); hook @0x%X" % (len(cave), CAVE_VA, c_off, H_SITE))
    if not apply:
        print("Dry run OK — rerun with --apply (or --revert)."); return 0
    if not os.path.exists(BAK):
        shutil.copy2(DLL, BAK); print("Backup ->", os.path.basename(BAK))
    open(DLL, 'wb').write(d)
    print("Written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
