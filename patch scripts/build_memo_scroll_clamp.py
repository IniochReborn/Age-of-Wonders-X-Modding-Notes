#!/usr/bin/env python3
r"""Fix "Exception during Draw" / "List index out of bounds (-N)" when
wheel-scrolling over city-view text boxes (TAOWMemo), aowInt.dpl.

DIAGNOSIS (live first-chance exception monitor + hover probe, 2026-08-21):
the mouse-wheel patch's WheelScroll cave (@0x59822880) handles a hovered
TAOWMemo without a scrollbar via its no-scrollbar fallback: it computes
first-visible-line +/-3 and calls TAOWMemo.SetFirstLine @0x59819298. That
vanilla setter clamps ONLY the upper bound:

    if new >= Lines.Count then new := Lines.Count - 1;   // no lower clamp!
    FFirstLine := new;

Wheel-up from line 0 stores -3 (observed -2/-3 live in [memo+0x128]); the
memo's draw then indexes Lines[-N] -> EListError, caught per-widget by the
toolkit as "Error - <name> / Exception during Draw" (seen on IncomeHdr), and
the widget stops painting (the "missing UI" effect). Bonus latent bug: with
an EMPTY memo, Count-1 stores -1 even for a valid input. Keyboard scrolling
never triggers it (different path) - confirmed in-game.

FIX: re-implement the 59-byte setter in a cave with BOTH clamps
(new = max(0, min(new, Count-1)); Count<=0 -> 0) and hook the entry with a
5-byte jmp (the cave fully replaces the body - no return into it). Every
caller (the wheel fallback, any keyboard/native path) is covered.

Cave @0x59823D00 (aowInt CODE-tail free zeros per cave map), fully
position-independent (virtual call only). No reloc intersects hook or cave
(asserted). Backup: aowInt.dpl.bak_memoclamp. Dry-run default; --apply /
--revert.
"""
import os, shutil, struct, sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DPL = os.path.join(GAME, "aowInt.dpl")
BAK = DPL + ".bak_memoclamp"
V2F = 0x59800C00

SETTER = 0x59819298
SETTER_OLD = bytes.fromhex("53568bf28bd8")   # push ebx;push esi;mov esi,edx;mov ebx,eax
CAVE = 0x59823D00
CAVE_END = 0x59823D60


def build_cave():
    b = bytearray()
    base = CAVE
    def db(*x): b.extend(x)
    b_j8 = []
    labels = {}
    def j8(op, n): db(op); b_j8.append((len(b), n)); db(0)
    def lab(n): labels[n] = len(b)

    db(0x53, 0x56)                      # push ebx; push esi
    db(0x8B, 0xF2)                      # mov esi,edx (new)
    db(0x8B, 0xD8)                      # mov ebx,eax (memo)
    db(0x85, 0xF6)                      # test esi,esi
    j8(0x79, 'lo_ok')                   # jns
    db(0x33, 0xF6)                      # xor esi,esi
    lab('lo_ok')
    db(0x8B, 0x83); b.extend(struct.pack("<I", 0x188))   # mov eax,[ebx+0x188] Lines
    db(0x8B, 0x10)                      # mov edx,[eax]
    db(0xFF, 0x52, 0x14)                # call [edx+0x14]  Count
    db(0x85, 0xC0)                      # test eax,eax
    j8(0x7F, 'have')                    # jg: count > 0
    db(0x33, 0xF6)                      # count<=0 -> first line 0
    j8(0xEB, 'store')
    lab('have')
    db(0x3B, 0xF0)                      # cmp esi,eax
    j8(0x7C, 'store')                   # jl: within range
    db(0x8D, 0x70, 0xFF)                # lea esi,[eax-1]
    lab('store')
    db(0x3B, 0xB3); b.extend(struct.pack("<I", 0x128))   # cmp esi,[ebx+0x128]
    j8(0x74, 'done')
    db(0x89, 0xB3); b.extend(struct.pack("<I", 0x128))   # mov [ebx+0x128],esi
    db(0xC6, 0x83); b.extend(struct.pack("<I", 0xA4)); db(0x00)  # repaint flag
    lab('done')
    db(0x5E, 0x5B)                      # pop esi; pop ebx
    db(0xC3)                            # ret

    for off, n in b_j8:
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
        if blk < 8:
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
            shutil.copy2(BAK, DPL); print("restored aowInt.dpl"); return 0
        print("no backup"); return 1

    d = bytearray(open(DPL, "rb").read())
    cave = build_cave()
    hook = b"\xE9" + struct.pack("<i", CAVE - (SETTER + 5)) + b"\x90"

    s_off = SETTER - V2F
    c_off = CAVE - V2F
    hits = reloc_hits(bytes(d), [(s_off, s_off + 6), (c_off, c_off + len(cave))])
    assert not hits, [hex(x) for x in hits]

    cur_s = bytes(d[s_off:s_off + 6])
    cur_c = bytes(d[c_off:c_off + len(cave)])
    if cur_s == hook and cur_c == cave:
        print("ALL ALREADY PATCHED"); return 0
    ok = True
    if cur_s not in (SETTER_OLD, hook):
        print("MISMATCH at setter entry:", cur_s.hex(' ')); ok = False
    if cur_c != bytes(len(cave)) and cur_c != cave:
        print("MISMATCH: cave region not zero"); ok = False
    if not ok:
        print("Aborting."); return 1

    print("cave_setfirst %dB @%#x; TAOWMemo.SetFirstLine @%#x -> jmp cave"
          % (len(cave), CAVE, SETTER))
    print("Memo first-line now clamped to [0, Count-1] (0 when empty).")
    if not apply:
        print("\nDry run OK. Re-run with --apply (or --revert)."); return 0

    if not os.path.exists(BAK):
        shutil.copy2(DPL, BAK); print("Backup ->", os.path.basename(BAK))
    d[c_off:c_off + len(cave)] = cave
    d[s_off:s_off + 6] = hook
    open(DPL, "wb").write(d)
    print("aowInt.dpl patched successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
