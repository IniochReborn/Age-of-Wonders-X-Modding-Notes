#!/usr/bin/env python3
"""In-game version number 410 -> 402 (AoWEPACK.dll).

TAoWEngine.Create (VA 0x55797C0B area) sets the engine version as three
immediates:

    31 D2          xor edx, edx
    42             inc edx          ; version part 1 = 1
    31 C9          xor ecx, ecx
    B1 25          mov cl, 0x25     ; version part 2 = 37
    68 9A 01 00 00 push 0x19A       ; version part 3 = 410  (imm32 @ 0x9701B)

The push imm32 operand at file offset 0x9701B reads 9A 01 00 00 (410) -
this is why the game displays "1.37.0410" even though the release was
labeled 1.37.401.  Patch to 92 01 00 00 (402) so the game reports
1.37.0402, matching the 1.37.402 release.

Note: AoWEPACK.dpl (legacy copy, not loaded) has E0 00 00 00 (224) at the
same offset and is deliberately left untouched.

Dry-run by default, --apply to write.  Idempotent; verifies bytes before
writing; backs up to AoWEPACK.dll.bak_version410 on first apply.
"""
import os
import shutil
import sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
TARGET = os.path.join(GAME, "AoWEPACK.dll")
BACKUP = TARGET + ".bak_version410"

OFF = 0x9701B
OLD = bytes.fromhex("9A010000")   # 410
NEW = bytes.fromhex("92010000")   # 402


def main():
    apply = "--apply" in sys.argv
    data = bytearray(open(TARGET, "rb").read())
    cur = bytes(data[OFF:OFF+4])

    if cur == NEW:
        print("version 402 already applied")
        return 0
    if cur != OLD:
        print("MISMATCH @0x%X: %s (expected %s)" % (OFF, cur.hex(), OLD.hex()))
        return 1

    print("version patch ready @0x%X: %s -> %s (410 -> 402)"
          % (OFF, cur.hex(), NEW.hex()))
    if not apply:
        print("Dry run OK - rerun with --apply to write.")
        return 0

    if not os.path.exists(BACKUP):
        shutil.copy2(TARGET, BACKUP)
        print("Backup -> %s" % os.path.basename(BACKUP))
    data[OFF:OFF+4] = NEW
    with open(TARGET, "wb") as f:
        f.write(data)
    print("Written %s" % TARGET)
    return 0


if __name__ == "__main__":
    sys.exit(main())
