#!/usr/bin/env python3
r"""FIX: access violation when damage is applied to a COMBAT WALL.

THE BUG (root cause of "Exception occured during TArmyCombatMoveTE" on
campaign Keeper2.csm; user-reproduced on turn 2, 2026-08-12)
    The mod's damage cave @0x5580F060 (hooked over the `call [edx+0xA0]`
    GetLevel in AoWE.TCombatObject.DoDamage @0x55726B7F and
    AoWE.TDamageEffectCA.Execute @0x5572A00C) adds a rank bonus:

        mov  eax,esi / mov edx,[eax] / call [edx+0xA0]   ; original GetLevel
        and  eax,0xff
        push ebx
        mov  ebx,[esi+0x4c]        ; <-- assumed to be the underlying TUnit
        test ebx,ebx / je skip     ; ONLY a nil check
        <16 NOPs>                  ; a validity test used to live here
        push eax / mov eax,ebx
        call AoWE.TUnit.GetRank    ; <-- AV

    `[obj+0x4C]` is the underlying TUnit **only for TCombatUnit** (set by
    TCombatUnit.SetUnit; read by GetHits/GetHitPoints/GetAbilityOwner/...).
    But the hook sits in TCombatObject.DoDamage, the BASE-class method, and the
    hierarchy is:
        TCombatObject
          TCombatUnit
            TFastCombatUnit          <- also stores the TUnit at +0x4C
          TCombatWall                <- DOES NOT
    On a **TCombatWall**, +0x4C is a packed BYTE pair, not a pointer:
        TCombatWall.GetHits      @0x55725C30: cmp byte [eax+0x4c],2   (wall type)
        TCombatWall.GetHitPoints @0x55725C3C: mov al, byte [eax+0x4d] (wall HP)
    so the dword read at +0x4C comes back as a small integer - observed **1** -
    which passes the nil check and is then used as Self:

        Access violation at address 0122294F in module 'AoWEPACK.dll'.
        Read of address 0000003D          ; = 1 + 0x3C, in TUnit.GetRank+0x3

    i.e. **any damage dealt to a city/fort wall crashes the combat**. The
    exception is swallowed by NetworkE.TTokenExecuter.ExecuteTokenEvent, which
    marks the turn event done, so the half-built combat is never torn down and
    the next fight then raises 'Combat already created'
    (TAoWHSMap.CreateCombat+0x85). Both errors have this single cause.
    Pre-dates 1.37.401: the 16 NOPs are present in 72 AoWEPACK.dll.bak_* files
    (the validity test was dropped during the victim-XP / no-halving work; note
    it would ALSO have crashed on a wall, one instruction earlier, since it did
    `mov edx,[eax]` on the same bogus pointer).

THE FIX
    Fill the 16 spare NOP bytes with a real type check - apply the rank bonus
    only when the combat object actually IS a TCombatUnit (which also covers
    TFastCombatUnit, since @IsClass matches descendants). Walls fall through to
    the existing `skip` at 0x5580F09E, which returns the plain GetLevel result -
    exactly the vanilla value, so wall damage is unchanged.

        push eax                      ; keep the level result
        mov  eax,esi
        call cave                     ; al = IsClass(esi, TCombatUnit)
        test al,al
        pop  eax                      ; POP does not touch flags
        je   0x5580F09E               ; not a unit -> no rank bonus
    cave @0x55810E80 (28 B): PIC (AoWEPACK rebases) - call/pop delta, then
    `lea edx,[delta + 0x55715A94]` = the runtime TCombatUnit VMT = the class
    operand for VCL30 System.@IsClass (thunk 0x557010C0).

    Backup: AoWEPACK.dll.bak_wallrank. Dry-run default; --apply / --revert.
    NOTE: run build_getrank_caller_probe.py --revert FIRST - that diagnostic
    occupies this same cave.
"""
import os, shutil, struct, sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DLL = os.path.join(GAME, "AoWEPACK.dll")
BAK = DLL + ".bak_wallrank"

VA2FILE = 0x55700C00
CAVE_BASE, CAVE_LIMIT = 0x55810E80, 0x55810F00

PATCH_AT = 0x5580F077          # the 16 spare bytes inside the damage cave
PATCH_LEN = 0x10
SKIP_TO = 0x5580F09E           # existing "no bonus" exit (pop ebx; ret)
VMT_TCOMBATUNIT = 0x55715A94   # verified: selfptr @0x55715A54 holds this
F_ISCLASS = 0x557010C0         # VCL30 System.@IsClass (eax=obj, edx=class)
OLD_NOPS = b"\x90" * PATCH_LEN


def build_cave():
    base = CAVE_BASE
    buf = bytearray(); rel = []

    def db(*b): buf.extend(b)
    def dd(v): buf.extend((v & 0xFFFFFFFF).to_bytes(4, 'little'))
    def call(t): db(0xE8); rel.append((len(buf), t)); dd(0)

    db(0x53)                          # push ebx
    db(0x52)                          # push edx
    call(base + len(buf) + 5)         # call $+5  (delta trick)
    popva = base + len(buf)
    db(0x5B)                          # pop ebx
    db(0x81, 0xEB); dd(popva)         # sub ebx, static -> ebx = delta
    db(0x8D, 0x93); dd(VMT_TCOMBATUNIT)   # lea edx,[ebx+VMT] -> runtime class
    call(F_ISCLASS)                   # eax already = the object -> al
    db(0x5A)                          # pop edx
    db(0x5B)                          # pop ebx
    db(0xC3)                          # ret

    for off, tgt in rel:
        buf[off:off+4] = (tgt - (base + off + 4)).to_bytes(4, 'little', signed=True)
    assert base + len(buf) <= CAVE_LIMIT, hex(len(buf))
    return bytes(buf)


def build_guard():
    """The 16-byte in-place guard written over the NOPs."""
    b = bytearray()
    b += b"\x50"                                          # push eax
    b += b"\x8B\xC6"                                      # mov eax,esi
    site = PATCH_AT + len(b)
    b += b"\xE8" + (CAVE_BASE - (site + 5)).to_bytes(4, 'little', signed=True)
    b += b"\x84\xC0"                                      # test al,al
    b += b"\x58"                                          # pop eax (flags kept)
    site = PATCH_AT + len(b)
    disp = SKIP_TO - (site + 2)
    assert -128 <= disp <= 127, hex(disp)
    b += b"\x74" + bytes([disp & 0xFF])                   # je skip
    assert len(b) <= PATCH_LEN, len(b)
    b += b"\x90" * (PATCH_LEN - len(b))
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
    guard = build_guard()
    p_off = PATCH_AT - VA2FILE
    c_off = CAVE_BASE - VA2FILE

    hits = reloc_hits(bytes(d), [(p_off, p_off + PATCH_LEN), (c_off, c_off + len(cave))])
    assert not hits, ["reloc in patch range: " + hex(x) for x in hits]

    cur = bytes(d[p_off:p_off + PATCH_LEN])
    assert cur == OLD_NOPS or cur[:1] == b"\x50", \
        "unexpected bytes at 0x%X: %s" % (PATCH_AT, cur.hex())
    curc = bytes(d[c_off:c_off + len(cave)])
    assert curc == bytes(len(cave)) or curc[:2] == cave[:2], \
        "cave not free (run build_getrank_caller_probe.py --revert first): " + curc[:8].hex()

    # sanity: the routine must still look like the one we analysed
    assert bytes(d[0x5580F070 - VA2FILE:0x5580F077 - VA2FILE]) == \
        bytes.fromhex("8b5e4c85db7427"), "damage cave differs from the analysed build"

    d[c_off:c_off + len(cave)] = cave
    d[p_off:p_off + PATCH_LEN] = guard

    print("cave %d B @0x%X; guard %d B @0x%X -> skip 0x%X"
          % (len(cave), CAVE_BASE, len(guard), PATCH_AT, SKIP_TO))
    print("rank bonus now applies only when the combat object IsClass TCombatUnit")
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
