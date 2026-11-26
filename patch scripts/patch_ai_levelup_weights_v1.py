#!/usr/bin/env python3
r"""
Retune the AI hero/leader level-up chooser's ability weights in place (2026-09-14).

The July 2026 chooser (heroai_build.py, see memory aowx-ai-hero-levelup) keeps three tables inside
its eligibility cave in AoWEPACK.dll:
    0x5580FDD5  30 x u8   ability id
    0x5580FDF4  30 x u16  "unaffordable" (banking) weight
    0x5580FE30  30 x u16  "affordable" (lock-in) weight
This script sets WEIGHTS[id] = (unaffordable, affordable) for the ids listed, leaving every other
entry alone.  Each edit asserts the value it expects to replace, so a drifted table refuses.

Current retune: Marksmanship 0x20  5/5 -> 20/20  (the ranged-attack gate of
patch_ai_marksmanship_gate_v1.py stays; a bigger weight only matters once that gate passes).

Backup AoWEPACK.dll.bak_aiweights.  Dry-run default; --apply; --revert.
"""
import argparse, os, shutil, struct, sys
from bakpath import game_dir, game_file   # game folder = AOW_GAME_DIR or parent of patch scripts (2026-09-20)

DEFAULT_GAME = game_dir()
BAK = ".bak_aiweights"
from bakpath import bak_path   # backups live in <game>\backup\ (2026-09-17)
FILE_DELTA = 0x55700C00                 # AoWEPACK CODE: file offset = VA - 0x55700C00
T_ID, T_UN, T_AF, N = 0x5580FDD5, 0x5580FDF4, 0x5580FE30, 30
# id: (old_unaff, old_aff, new_unaff, new_aff)
WEIGHTS = {0x20: (5, 5, 20, 20)}       # Marksmanship


def main():
    ap = argparse.ArgumentParser(description="AI level-up chooser weight retune")
    ap.add_argument("--game", default=DEFAULT_GAME)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    a = ap.parse_args()
    dll = os.path.join(a.game, "AoWEPACK.dll")
    if a.revert:
        if not os.path.exists(bak_path(dll, BAK)):
            print("no backup"); return 1
        shutil.copyfile(bak_path(dll, BAK), dll); print("restored AoWEPACK.dll"); return 0
    d = bytearray(open(dll, "rb").read())
    ids = bytes(d[T_ID - FILE_DELTA:T_ID - FILE_DELTA + N])
    un = [struct.unpack_from("<H", d, T_UN - FILE_DELTA + 2 * k)[0] for k in range(N)]
    af = [struct.unpack_from("<H", d, T_AF - FILE_DELTA + 2 * k)[0] for k in range(N)]
    assert len(set(ids)) == N and all(1 <= w <= 65535 for w in un + af), "chooser tables not where expected"
    print("%-6s %-6s %-6s" % ("id", "unaff", "aff"))
    for k in range(N):
        print("0x%02X   %5d  %5d%s" % (ids[k], un[k], af[k], "   <- edit" if ids[k] in WEIGHTS else ""))
    todo, done = [], []
    for aid, (ou, oa, nu, na) in WEIGHTS.items():
        k = ids.index(aid)
        if (un[k], af[k]) == (nu, na):
            done.append(aid); continue
        assert (un[k], af[k]) == (ou, oa), "id 0x%02X reads %d/%d, expected %d/%d" % (aid, un[k], af[k], ou, oa)
        todo.append((k, aid, nu, na))
    if not todo:
        print("ALL ALREADY PATCHED"); return 0
    for k, aid, nu, na in todo:
        print("id 0x%02X: %d/%d -> %d/%d" % (aid, un[k], af[k], nu, na))
    if not a.apply:
        print("\nDry run OK. Re-run with --apply to write."); return 0
    if not os.path.exists(bak_path(dll, BAK)):
        shutil.copyfile(dll, bak_path(dll, BAK)); print("backup: AoWEPACK.dll" + BAK)
    for k, aid, nu, na in todo:
        struct.pack_into("<H", d, T_UN - FILE_DELTA + 2 * k, nu)
        struct.pack_into("<H", d, T_AF - FILE_DELTA + 2 * k, na)
    with open(dll, "r+b") as f:
        f.seek(0); f.write(d)
    print("applied.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
