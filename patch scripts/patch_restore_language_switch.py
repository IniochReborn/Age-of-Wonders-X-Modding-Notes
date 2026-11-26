"""
patch_restore_language_switch.py - re-enable in-game language switching.

A long-standing "AoW+ bugfix" had forced the game to English by patching
AoWReg.TAoWRegistry.GetLanguage (AoWEPACK.dll, VA 0x55704B84 / file 0x3F84):
    8A 04 24   mov al,[esp]     ; return the real registry language
  ->B0 01 90   mov al,1 ; nop   ; always return 1 (English)
Every language dispatch calls GetLanguage, so the game ignored the selected
language and rendered the English column no matter what. (AoWSetup is a
separate program and was unaffected, which is why only its UI localized.)

This restores the original instruction so the game reads the actual language.
English stays the default (registry value 1 -> English column, the mod's
primary language); only players who explicitly choose another language get it.

    python patch_restore_language_switch.py            dry run
    python patch_restore_language_switch.py --apply    back up, restore vanilla
    python patch_restore_language_switch.py --revert    re-apply force-English
"""
import os, sys, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.abspath(os.path.join(HERE, ".."))
DLL = os.path.join(GAME, "AoWEPACK.dll")
BAK = DLL + ".bak_langswitch"

OFF = 0x3F84
FORCED = b"\xB0\x01\x90"          # mov al,1 ; nop     (force English)
VANILLA = b"\x8A\x04\x24"         # mov al,[esp]        (read real language)


def run(apply_it):
    d = bytearray(open(DLL, "rb").read())
    cur = bytes(d[OFF:OFF + 3])
    if cur == VANILLA:
        print("GetLanguage already reads the real language - nothing to do.")
        return
    if cur != FORCED:
        print("Unexpected bytes at 0x%X: %s (want %s force / %s vanilla)."
              % (OFF, cur.hex(), FORCED.hex(), VANILLA.hex()))
        sys.exit(1)
    print("GetLanguage @0x%X: %s -> %s (restore real language read)"
          % (OFF, FORCED.hex(), VANILLA.hex()))
    if not apply_it:
        print("Dry run - use --apply.")
        return
    if not os.path.isfile(BAK):
        shutil.copy2(DLL, BAK)
    d[OFF:OFF + 3] = VANILLA
    with open(DLL, "wb") as fh:
        fh.write(d)
    print("Applied (backup AoWEPACK.dll.bak_langswitch). In-game language "
          "switching restored.")


def revert():
    # byte-level on purpose: never copy the whole dll back from .bak_langswitch,
    # other patch families have modified AoWEPACK.dll since that backup was cut
    d = bytearray(open(DLL, "rb").read())
    cur = bytes(d[OFF:OFF + 3])
    if cur == FORCED:
        print("Already forced English.")
        return
    if cur != VANILLA:
        print("Unexpected bytes at 0x%X: %s - refusing." % (OFF, cur.hex()))
        sys.exit(1)
    d[OFF:OFF + 3] = FORCED
    with open(DLL, "wb") as fh:
        fh.write(d)
    print("Re-applied force-English (byte patch).")


if __name__ == "__main__":
    if "--revert" in sys.argv:
        revert()
    else:
        run("--apply" in sys.argv)
