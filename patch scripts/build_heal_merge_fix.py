#!/usr/bin/env python3
r"""Item-granted Healing round 3: propagate the hero's daily-used record
through the bit-gated ability MERGE, so the UI copies learn the used state.

DIAGNOSIS (live probes, 2026-08-21): the game keeps several copies of each
hero (server world unit, client/UI unit, transient window copies, fast-combat
clones). The heal consume (SetUsed) correctly marks the copy that executes
the action, and the state then flows to the display copies through
TAbilityOwner "merge abilities" @0x5574F518:

    for id in 0..source.AbilityCount-1:
        if NOT source.HasAbility(id): continue        <-- BIT-GATED
        if dest.HasAbility(id) and levels not better: continue
        copy source's data record -> dest; dest.SetAbility(id, true)

Innate Healing has the bit -> its record (whose [rec+0xC] is the once-per-day
used flag) propagates -> the name flips to "(used)" immediately (confirmed
in-game). ITEM-granted Healing keeps the bit on the item; the hero-side
used-state record is bit-less, so the merge drops it at every hop and every
UI copy shows the ability eternally fresh (confirmed: poking the used flag
into individual world copies never reached the visible window copy).

FIX: hook the merge's per-id source-bit test (5 bytes @0x5574F533,
`mov ecx,[eax]; call [ecx+0x4C]`) -> cave_mrg:
  - source has the bit -> al=1, normal path (unchanged);
  - else, for Healing (0x2F) only: if the source carries a healing record,
    copy it to dest RIGHT HERE (RemoveAbilityData(dest, id) + clone via
    0x557030CC with the game context [0x558FA048] + AddAbilityData), then
    return al=0 so the normal path still skips the id - crucially WITHOUT
    dest.SetAbility, so no unit ever gains a healing BIT it doesn't own.
Sources with no bit and no record (library templates, plain units) hit the
FINDDATA-nil path -> al=0, exactly vanilla. The map auto-update caves that
call this merge use library sources (never carry bit-less healing recs), so
they are unaffected.

Cave is position-independent (the [0x558FA048] read goes through the
call/pop load delta; everything else rel32/virtual). No reloc intersects the
hook or cave (asserted).

Cave @0x55812B00..0x55812B80 (zeros verified to 0x55830000; gname ends
0x55812AED). Dry-run default; --apply / --revert.
Backup: AoWEPACK.dll.bak_healmerge
"""
import os, shutil, struct, sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DLL = os.path.join(GAME, "AoWEPACK.dll")
BAK = DLL + ".bak_healmerge"
V2F = 0x55700C00

HEAL_ID  = 0x2F
FINDDATA = 0x5574F1C4       # GetAbilityData(eax=owner, edx=id) -> rec|nil
REMDATA  = 0x5574F2B8       # RemoveAbilityData(eax=owner, edx=id)
ADDDATA  = 0x5574F278       # AddAbilityData(eax=owner, edx=rec)
CLONE    = 0x557030CC       # clone(eax=obj, edx=game ctx) -> eax
GAMECTX  = 0x558FA048       # global the vanilla merge passes to CLONE

SITE     = 0x5574F533       # mov ecx,[eax]; call [ecx+0x4C]   (source bit test)
SITE_ORIG= bytes.fromhex("8b08ff514c")

CAVE_MRG = 0x55812B00
CAVE_END = 0x55812B80


def build_mrg():
    """(eax=source, edx=id; ebx=id, esi=dest, edi=source) -> al
    al=1: id owned by source, caller proceeds normally.
    al=0: caller skips - after we optionally copied the bit-less healing rec."""
    b = bytearray()
    base = CAVE_MRG
    rel = []
    j8 = []
    labels = {}

    def db(*x): b.extend(x)
    def dd(v): b.extend(struct.pack("<I", v))
    def call(t):
        db(0xE8); rel.append((len(b), t)); dd(0)
    def lab(n): labels[n] = len(b)
    def jcc(op, n): db(op); j8.append((len(b), n)); db(0)

    db(0x8B, 0x08)                      # mov ecx,[eax]
    db(0xFF, 0x51, 0x4C)                # call [ecx+0x4C]  source.HasAbility(id)
    db(0x84, 0xC0)                      # test al,al
    jcc(0x75, 'ret')                    # bit owned -> normal path (al=1)
    db(0x83, 0xFB, HEAL_ID)             # cmp ebx,0x2F
    jcc(0x75, 'zero')
    db(0x8B, 0xD3)                      # mov edx,ebx (id)
    db(0x8B, 0xC7)                      # mov eax,edi (source)
    call(FINDDATA)
    db(0x85, 0xC0)                      # test eax,eax
    jcc(0x74, 'zero')                   # no bit-less rec -> vanilla skip
    db(0x50)                            # push eax (source rec)
    db(0x8B, 0xD3)                      # mov edx,ebx
    db(0x8B, 0xC6)                      # mov eax,esi (dest)
    call(REMDATA)                       # drop dest's stale rec for this id
    db(0xE8, 0, 0, 0, 0)                # call $+5 (PIC anchor)
    popva = base + len(b)
    db(0x5A)                            # pop edx
    db(0x81, 0xEA); dd(popva)           # sub edx,popva -> load delta
    db(0x8B, 0x92); dd(GAMECTX)         # mov edx,[edx+GAMECTX] (relocated global)
    db(0x58)                            # pop eax (source rec)
    call(CLONE)                         # -> eax = cloned rec
    db(0x8B, 0xD0)                      # mov edx,eax
    db(0x8B, 0xC6)                      # mov eax,esi (dest)
    call(ADDDATA)
    lab('zero')
    db(0x33, 0xC0)                      # xor eax,eax (skip id; NO bit set)
    lab('ret')
    db(0xC3)                            # ret

    for off, tgt in rel:
        b[off:off+4] = struct.pack("<i", tgt - (base + off + 4))
    for off, n in j8:
        d = labels[n] - (off + 1)
        assert -128 <= d <= 127, (n, d)
        b[off] = d & 0xFF
    assert base + len(b) <= CAVE_END, len(b)
    return bytes(b)


def reloc_hits(data, ranges):
    e = struct.unpack_from('<I', data, 0x3C)[0]; opt = e + 24
    nsec = struct.unpack_from('<H', data, e + 6)[0]
    osz = struct.unpack_from('<H', data, e + 20)[0]
    rrva, rsz = struct.unpack_from('<II', data, opt + 96 + 5 * 8)
    secs = []; p = opt + osz
    for _ in range(nsec):
        vs, va, rs, raw = struct.unpack_from('<IIII', data, p + 8)
        secs.append((va, vs, raw, rs)); p += 40
    def r2o(rva):
        for va, vs, raw, rs in secs:
            if va <= rva < va + max(vs, rs):
                return raw + rva - va
    off = r2o(rrva); end = off + rsz; hits = []
    while off < end:
        page, blk = struct.unpack_from('<II', data, off)
        if blk == 0:
            break
        for i in range((blk - 8) // 2):
            w = struct.unpack_from('<H', data, off + 8 + i * 2)[0]
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
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if revert:
        if os.path.exists(BAK):
            shutil.copy2(BAK, DLL); print("restored AoWEPACK.dll"); return 0
        print("no backup"); return 1

    d = bytearray(open(DLL, "rb").read())
    cave = build_mrg()
    hook = b"\xE8" + struct.pack("<i", CAVE_MRG - (SITE + 5))

    hits = reloc_hits(bytes(d), [(SITE - V2F, SITE - V2F + 5),
                                 (CAVE_MRG - V2F, CAVE_END - V2F)])
    assert not hits, [hex(x) for x in hits]

    s_off = SITE - V2F
    c_off = CAVE_MRG - V2F
    cur_s = bytes(d[s_off:s_off + 5])
    cur_c = bytes(d[c_off:c_off + len(cave)])

    if cur_s == hook and cur_c == cave:
        print("ALL ALREADY PATCHED"); return 0
    ok = True
    if cur_s != SITE_ORIG and cur_s != hook:
        print("MISMATCH at merge gate:", cur_s.hex(' ')); ok = False
    if cur_c != bytes(len(cave)) and cur_c != cave:
        print("MISMATCH cave region not zero"); ok = False
    if not ok:
        print("Aborting."); return 1

    print("cave_mrg @%#x %dB; merge gate @%#x -> call cave" % (CAVE_MRG, len(cave), SITE))
    print("Bit-less Healing records now propagate through the ability merge")
    print("(no bit is ever granted) -> UI copies learn the daily-used state.")
    if not apply:
        print("\nDry run OK. Re-run with --apply (or --revert)."); return 0

    if not os.path.exists(BAK):
        shutil.copy2(DLL, BAK); print("Backup ->", os.path.basename(BAK))
    d[c_off:c_off + len(cave)] = cave
    d[s_off:s_off + 5] = hook
    open(DLL, "wb").write(d)
    print("AoWEPACK.dll patched successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
