#!/usr/bin/env python3
"""In-game version number 435 -> 436 (1.37.436: multiplayer tactical-combat lock-up fix = patch_combat_remote_tc_purge_v1; revert to go back to 435) (AoWEPACK.dll).

TAoWEngine.Create sets the engine version as three immediates:

    31 D2          xor edx, edx
    42             inc edx          ; part 1 = 1
    31 C9          xor ecx, ecx
    B1 25          mov cl, 0x25     ; part 2 = 37
    68 9A 01 00 00 push 0x19A       ; part 3 = 410  (imm32 @ file 0x9701B)

Part 3 renders zero-padded in-game ("1.37.0420"); text files use the
unpadded "1.37.420" per user preference.

Note: AoWEPACK.dpl is a stale legacy copy that the game does not load -
deliberately left untouched.

Dry-run by default, --apply to write, --revert to go back to 435.
Idempotent; verifies bytes before writing. Backup: AoWEPACK.dll.bak_ver436
"""
import os
import shutil
import sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
TARGET = os.path.join(GAME, "AoWEPACK.dll")
from bakpath import bak_path
BACKUP = bak_path(TARGET, ".bak_ver436")

OFF = 0x9701B
OLD = bytes.fromhex("b3010000")   # 435
NEW = bytes.fromhex("b4010000")   # 436


def main():
    apply = "--apply" in sys.argv
    revert = "--revert" in sys.argv
    data = bytearray(open(TARGET, "rb").read())
    cur = bytes(data[OFF:OFF + 4])
    want_from, want_to = (NEW, OLD) if revert else (OLD, NEW)

    if cur == want_to:
        print("already at %d - nothing to do." % int.from_bytes(want_to, "little"))
        return 0
    if cur != want_from:
        print("UNEXPECTED bytes at 0x%X: %s (expected %s)"
              % (OFF, cur.hex(), want_from.hex()))
        return 1

    data[OFF:OFF + 4] = want_to
    print("version %d -> %d at file 0x%X"
          % (int.from_bytes(want_from, "little"),
             int.from_bytes(want_to, "little"), OFF))
    if not apply and not revert:
        print("Dry run OK - rerun with --apply.")
        return 0
    if not os.path.exists(BACKUP):
        shutil.copy2(TARGET, BACKUP)
        print("Backup ->", os.path.basename(BACKUP))
    with open(TARGET, "r+b") as f:   # in place (house rule; "wb" fails while another process maps the DLL)
        f.seek(0); f.write(data)
    print("Written - game will report 1.37.0%d."
          % int.from_bytes(want_to, "little"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
