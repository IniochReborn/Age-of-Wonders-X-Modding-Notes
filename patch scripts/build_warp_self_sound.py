#!/usr/bin/env python3
r"""Warp Self — sound: point the spell's cast sound at the vanilla teleporter
sound instead of Call Flames' fire-start.

Warp Self's Spells.pfs record (key 212) was cloned from Call Flames; its combat
param tag 0x0B embeds the length-prefixed sound path 'SFX\ATTACK\FIRESTRT.WAV'.
'SFX\PLACES\TELEPORT.WAV' (Sfx\Places\Teleport.WAV, vanilla teleporter site
sound) is exactly the same 23-char length, so it swaps in place; only the
trailing CRC-32 needs recomputing. The stage-2 v5 cave plays [spell+0x28]
(loaded from this path) via the engine's own PlayEx block on a successful warp.

Backup: Spells.pfs.bak_warpsound. Dry-run default; --apply / --revert.
"""
import os, shutil, struct, sys, zlib

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
PFS = os.path.join(GAME, "Release", "Spells.pfs")
BAK = PFS + ".bak_warpsound"

OLD = b"\x17SFX\\ATTACK\\FIRESTRT.WAV"
NEW = b"\x17SFX\\PLACES\\TELEPORT.WAV"
NEW_KEY = 212


def rec_bounds(d, key):
    p = 7
    b = d[p]; p += 1
    nb = b & 0x7F; nd = 0
    if b & 0x80:
        nd = struct.unpack_from('<I', d, p)[0]; p += 4
    pairs = []
    for _ in range(nb):
        pairs.append((d[p], d[p+1])); p += 2
    for _ in range(nd):
        pairs.append(struct.unpack_from('<II', d, p)); p += 8
    idx = {t: p + o for t, o in pairs}
    off = idx[key]
    later = [v for v in idx.values() if v > off]
    return off, (min(later) if later else len(d) - 4)


def main():
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if revert:
        if os.path.exists(BAK):
            shutil.copy2(BAK, PFS); print("restored Spells.pfs"); return 0
        print("no backup"); return 1
    d = bytearray(open(PFS, 'rb').read())
    assert zlib.crc32(bytes(d[4:-4])) & 0xFFFFFFFF == struct.unpack_from('<I', d, len(d)-4)[0], "src CRC bad"
    lo, hi = rec_bounds(d, NEW_KEY)
    seg = bytes(d[lo:hi])
    assert len(OLD) == len(NEW)
    n_old, n_new = seg.count(OLD), seg.count(NEW)
    if n_new == 1 and n_old == 0:
        print("already applied"); return 0
    assert n_old == 1, (n_old, n_new)
    d[lo:hi] = seg.replace(OLD, NEW)
    struct.pack_into('<I', d, len(d)-4, zlib.crc32(bytes(d[4:-4])) & 0xFFFFFFFF)
    print("record %d: sound -> SFX\\PLACES\\TELEPORT.WAV; CRC updated" % NEW_KEY)
    if not apply:
        print("Dry run OK — rerun with --apply (or --revert)."); return 0
    if not os.path.exists(BAK):
        shutil.copy2(PFS, BAK); print("Backup ->", os.path.basename(BAK))
    open(PFS, 'wb').write(d)
    print("Written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
