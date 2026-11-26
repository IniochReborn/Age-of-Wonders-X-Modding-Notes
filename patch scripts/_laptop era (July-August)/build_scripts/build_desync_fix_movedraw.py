#!/usr/bin/env python3
"""LAN out-of-sync FIX #8 (AoWEPACK.dll): drop the discarded per-move synced
Random draw ("movedraw").  Approach (C).

ROOT-CAUSE evidence (repro #15, diag v6): a human move onto a neutral stack
(2nd click -> recruit/attack) creates a Local move token.  On the creator it
executes immediately; TMoveTE.Execute's state 0->1 transition draws
TAoWHSMap.Random(0xFFFFF) @0x557478ED **and immediately discards the result**
(eax overwritten by `mov eax,[ebx+14h]` at 0x557478F2).  That draw is the
move's ONLY synced side effect - it advances the shared seed by one.  In the
decisive repro the creator's seed went F3480932 -> BEB5F5FB solely from this
draw while the peer (which had not executed the move at that stream position)
stayed at F3480932; the very next TSyncTE compared F3480932 vs BEB5F5FB ->
OOS.  Every other token in the window matched.

FIX: NOP the 5-byte `call Random` at 0x557478ED so a move token's first
execute consumes ZERO synced draws.  The result was already discarded, so
gameplay is unchanged; the shared RNG stream simply advances one-fewer per
move UNIFORMLY on both machines (identical DLL), preserving determinism for
all normal play.  The recruit move's execution can then fall at different
stream positions on the two machines without perturbing the synced seed ->
no false OOS.

SAFETY NOTE (why this is not merely hiding a desync): the moved army is the
human's own Local token, which IS transmitted (repro #13 NET ring) and
executes on the peer at its counter; the ONLY thing that made the transient
timing observable was this throwaway draw.  IF the peer ever genuinely
DROPS the move (counter overtaken by concurrent AI tokens) the game states
would still diverge silently - so VERIFY IN PLAY that both clients agree on
army positions after a recruit, not merely that the OOS dialog is gone.  If
states diverge, revert and move to approach (B) (serialize the human move
against concurrent AI token generation).

Single 5-byte NOP patch (no cave).  Reloc scan built in.  Companions stay
applied: #1 noanim, #2 aiowner, #4 joindest.  Diag v6/v7 may stay applied
during verification (they only record).  Backup AoWEPACK.dll.bak_movedraw.
Dry-run; --apply / --revert.
"""
import os
import shutil
import struct
import sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
TARGET = os.path.join(GAME, "AoWEPACK.dll")
BACKUP = TARGET + ".bak_movedraw"

VA2FILE = 0x55700C00

H_DRAW = 0x557478ED
DRAW_OLD = bytes.fromhex("E88A090300")   # call TAoWHSMap.Random (result discarded)
DRAW_NEW = b"\x90" * 5                    # NOP x5


def reloc_check(data, ranges):
    e_lfanew = struct.unpack_from('<I', data, 0x3C)[0]
    opt = e_lfanew + 24
    nsec = struct.unpack_from('<H', data, e_lfanew + 6)[0]
    opt_size = struct.unpack_from('<H', data, e_lfanew + 20)[0]
    reloc_rva, reloc_sz = struct.unpack_from('<II', data, opt + 96 + 5*8)
    secs = []
    p = opt + opt_size
    for _ in range(nsec):
        vsz, va, rsz, raw = struct.unpack_from('<IIII', data, p + 8)
        secs.append((va, vsz, raw, rsz)); p += 40
    def rva2off(rva):
        for va, vsz, raw, rsz in secs:
            if va <= rva < va + max(vsz, rsz):
                return raw + rva - va
    off = rva2off(reloc_rva); end = off + reloc_sz
    hits = []
    while off < end:
        page_rva, blksz = struct.unpack_from('<II', data, off)
        for i in range((blksz - 8) // 2):
            w = struct.unpack_from('<H', data, off + 8 + i*2)[0]
            typ, ofs = w >> 12, w & 0xFFF
            if typ == 0:
                continue
            foff = rva2off(page_rva + ofs)
            if foff is None:
                continue
            for lo, hi in ranges:
                if lo <= foff + 3 and foff < hi:
                    hits.append((typ, foff))
        off += blksz
    return hits


def main():
    apply = "--apply" in sys.argv
    revert = "--revert" in sys.argv
    data = bytearray(open(TARGET, "rb").read())
    off = H_DRAW - VA2FILE

    hits = reloc_check(data, [(off, off + 5)])
    if hits:
        print("ABORT: reloc fixups intersect patch range: %s" % hits); return 1
    print("reloc scan clean")

    new = DRAW_OLD if revert else DRAW_NEW
    cur = bytes(data[off:off + 5])
    if cur == new:
        print("  draw @0x%X already %s" % (H_DRAW, "restored" if revert else "NOPed"))
        return 0
    if cur not in (DRAW_OLD, DRAW_NEW):
        print("  draw @0x%X MISMATCH: %s" % (H_DRAW, cur.hex())); return 1
    if not apply and not revert:
        print("Dry run OK (@0x%X: %s -> %s) - rerun with --apply (or --revert)."
              % (H_DRAW, cur.hex(), new.hex())); return 0
    if not os.path.exists(BACKUP):
        shutil.copy2(TARGET, BACKUP); print("Backup -> %s" % os.path.basename(BACKUP))
    data[off:off + 5] = new
    open(TARGET, "wb").write(data)
    print("Written %s (@0x%X = %s)" % (TARGET, H_DRAW, new.hex()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
