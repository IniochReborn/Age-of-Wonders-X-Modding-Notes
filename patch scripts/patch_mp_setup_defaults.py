#!/usr/bin/env python3
r"""Multiplayer (IPX/LAN) new-game setup defaults (AoWEPACK.dll).

The lobby's session settings live in AoWSetup.TSetupSettings; the host's
starting values come from TSetupSettings.Reset @0x557DF5A0 (called from
TSetupControl.Create). Field map, verified against the hSet* setters:

    +0x3D TacticalCombatAvailability  (tcaNever=0, tcaBetweenHumans=1, tcaAlways=2)
    +0x2A CustomizeLeaders            boolean
    +0x3E AlwaysViewTC                boolean

Three one-byte immediate edits in Reset, no caves:

    mov byte [ebx+3Dh],01h  ->  02h   ; Allow Tactical Combat: Between Humans -> Always
    mov byte [ebx+2Ah],00h  ->  01h   ; Customize Leaders: off -> on
    mov byte [ebx+3Eh],00h  ->  01h   ; Always View TC: off -> on

The host can still change everything in the lobby as usual - only the
initial values change. Clients mirror the host's settings, so patching the
defaults is host-side only (harmless on clients).

Backup: AoWEPACK.dll.bak_mpdefaults. Dry-run default; --apply / --revert.
"""
import os, shutil, sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DLL = os.path.join(GAME, "AoWEPACK.dll")
BAK = DLL + ".bak_mpdefaults"

# (file_offset, old, new, note)   CODE VA = file + 0x55700C00
PATCHES = [
    (0xDE9AE, bytes.fromhex("c6433d01"), bytes.fromhex("c6433d02"),
     "TacticalCombatAvailability: tcaBetweenHumans -> tcaAlways"),
    (0xDE9B2, bytes.fromhex("c6432a00"), bytes.fromhex("c6432a01"),
     "CustomizeLeaders: off -> on"),
    (0xDE9E4, bytes.fromhex("c6433e00"), bytes.fromhex("c6433e01"),
     "AlwaysViewTC: off -> on"),
]


def main():
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if revert:
        if os.path.exists(BAK):
            shutil.copy2(BAK, DLL); print("restored AoWEPACK.dll"); return 0
        print("no backup"); return 1
    d = bytearray(open(DLL, 'rb').read())
    changed = 0
    for off, old, new, note in PATCHES:
        cur = bytes(d[off:off+len(old)])
        if cur == new:
            print("already patched:", note); continue
        assert cur == old, "unexpected bytes at 0x%X: %s (want %s)" % (off, cur.hex(), old.hex())
        d[off:off+len(new)] = new
        changed += 1
        print("0x%06X (VA 0x%08X): %s" % (off, off + 0x55700C00, note))
    if not changed:
        print("nothing to do."); return 0
    if not apply:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if not os.path.exists(BAK):
        shutil.copy2(DLL, BAK); print("Backup ->", os.path.basename(BAK))
    open(DLL, 'wb').write(d)
    print("Written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
