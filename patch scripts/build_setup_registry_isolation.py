#!/usr/bin/env python3
r"""FIX: point AoWSetup.exe at the mod's registry tree ("Age of Wonders X").

THE BUG (found 2026-08-12 while adding Fullscreen (Optimized) to AoWSetup)
    The 2026-07-22 registry-isolation patch moved the mod to
        HKCU\Software\Triumph Studios\Age of Wonders X\
    by editing the path string in **AoWEPACK.dll** only - correct for the game
    and both editors, because they all route registry access through
    AoWEPACK's TAoWRegistry.

    **AoWSetup.exe does NOT link AoWEPACK.** It carries its own copies of the
    path constant and was therefore missed, so it still reads and writes the
    VANILLA key:
        HKCU\Software\Triumph Studios\Age of Wonders\
    Net effect: every setting changed in AoWSetup (video mode, resolution,
    sound quality, detail level, intro skip, ...) has had NO effect on the
    modded game, and AoWSetup shows stale/default values rather than the
    game's real settings.

THE FIX
    Same in-place technique as the AoWEPACK patch: each constant is a Delphi
    -1-refcount AnsiString followed by spare zero padding, so the length prefix
    can be bumped 41 -> 43 and " X" inserted before the trailing backslash.
    The characters keep their start address, so the three `mov edx,<ptr>`
    references need no change at all.

        \Software\Triumph Studios\Age of Wonders\    (len 41, 3 pad bytes)
     -> \Software\Triumph Studios\Age of Wonders X\  (len 43, 1 pad byte)

    Sites (VA): 0x467080, 0x467170, 0x467268 - refs at 0x466FF5, 0x4670E5,
    0x4671D5. AoWSetup.exe has no ASLR (DllCharacteristics=0, ImageBase
    0x400000), but nothing here depends on that.

    NOTE FOR USERS UPGRADING: settings previously saved by AoWSetup live under
    the old key. The game already uses the X key, so this simply makes the two
    agree. To carry old values over:
        reg copy "HKCU\Software\Triumph Studios\Age of Wonders" ^
                 "HKCU\Software\Triumph Studios\Age of Wonders X" /s /f

    Backup: AoWSetup.exe.bak_regiso. Dry-run default; --apply / --revert.
"""
import os, shutil, struct, sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
EXE = os.path.join(GAME, "AoWSetup.exe")
BAK = EXE + ".bak_regiso"

BS = 0x5C
OLD = bytes([BS]) + b"Software" + bytes([BS]) + b"Triumph Studios" + bytes([BS]) + b"Age of Wonders" + bytes([BS])
NEW = bytes([BS]) + b"Software" + bytes([BS]) + b"Triumph Studios" + bytes([BS]) + b"Age of Wonders X" + bytes([BS])
SITES = (0x066480, 0x066570, 0x066668)      # file offsets
VA2FILE = 0x400C00


def main():
    apply = "--apply" in sys.argv
    revert = "--revert" in sys.argv
    if revert:
        if os.path.exists(BAK):
            shutil.copy2(BAK, EXE)
            print("restored AoWSetup.exe from", os.path.basename(BAK))
            return 0
        print("no backup found:", BAK)
        return 1

    d = bytearray(open(EXE, 'rb').read())
    want_from, want_to = OLD, NEW
    done = 0
    for off in SITES:
        ln = struct.unpack_from('<I', d, off - 4)[0]
        rc = struct.unpack_from('<i', d, off - 8)[0]
        cur = bytes(d[off:off + ln])
        if cur == want_to:
            print("  0x%06X (VA 0x%X): already patched" % (off, off + VA2FILE))
            done += 1
            continue
        assert rc == -1, "not a const string at 0x%X (refcount %d)" % (off, rc)
        assert cur == want_from, "unexpected string at 0x%X: %r" % (off, cur)
        # need 2 spare zero bytes after the chars (plus keep a terminator)
        pad = 0
        k = off + ln
        while k < len(d) and d[k] == 0:
            pad += 1; k += 1
        assert pad >= 3, "not enough padding at 0x%X (%d)" % (off, pad)
        d[off:off + len(want_to)] = want_to
        struct.pack_into('<I', d, off - 4, len(want_to))
        print("  0x%06X (VA 0x%X): len %d -> %d, %r"
              % (off, off + VA2FILE, ln, len(want_to), want_to.decode()))
        done += 1

    print("%d/%d sites" % (done, len(SITES)))
    if not apply:
        print("Dry run OK - rerun with --apply (or --revert).")
        return 0
    if not os.path.exists(BAK):
        shutil.copy2(EXE, BAK)
        print("Backup ->", os.path.basename(BAK))
    open(EXE, 'wb').write(d)
    print("Written - AoWSetup now uses the mod's registry tree.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
