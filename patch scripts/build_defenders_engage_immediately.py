#!/usr/bin/env python3
r"""Site defenders engage immediately - the NARROW re-implementation.

BACKGROUND: the mod used to stub AoWTCPCK's whole `TAoWMapField.GetExplored`
import thunk to `mov eax,1; ret` so every combat tile read as "explored". That
made lair/dungeon defenders attack at once instead of waiting to be spotted -
but it lied to ALL TEN call sites in the combat code and, because the stub
never dereferenced its argument, it silently null-guarded them too. That hid a
real nil-field deref which surfaced in MP as
"Error - TCMoveToken: Error during Token" (see build_getexplored_nilguard.py).

With the real function restored (plus the nil guard), defenders are back to
vanilla "wait until seen". This patch re-adds the behaviour at the ONE place
that actually decides it:

  AoWTC.TCAI.EvalBattle, inside the "Create Unit List" phase (0x4183A2..):

      call  HSEngine.TMapContainer.GetField     ; a field the AI is considering
      mov   edx,[0x46C064] / movsx edx,byte [edx+0xA5]   ; the VIEWING player
      call  0x40287C                            ; GetExplored(field, viewer)
      test  al,al
      je    skip
      mov   byte [ebp-0x33],1                   ; "we have been spotted"

i.e. the tactical AI asks "can the human see this tile?" and only engages once
the answer is yes. Forcing that single answer to TRUE makes the defenders act
from turn one, while movement, cursor, ranged and melee code all keep genuine
exploration semantics (and keep the nil guard).

Patch: 5 bytes at 0x4183B7, `call 0x40287C` -> `mov al,1` + 3 nops.
No cave, no relocation involved (a rel32 call carries no fixup).

Backup AoWTCPCK.dll.bak_engage. Dry-run default; --apply / --revert.
"""
import os, shutil, struct, sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DLL = os.path.join(GAME, "AoWTCPCK.dll")
BAK = DLL + ".bak_engage"

VA2FILE = 0x400C00
SITE = 0x4183B7
GETEXPLORED = 0x40287C
OLD = b"\xE8" + struct.pack("<i", GETEXPLORED - (SITE + 5))   # call GetExplored
NEW = bytes.fromhex("B001909090")                             # mov al,1 ; nop*3


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--dry-run"
    if mode == "--revert":
        if not os.path.exists(BAK):
            sys.exit("no backup")
        shutil.copyfile(BAK, DLL)
        print("reverted", DLL)
        return

    data = bytearray(open(DLL, "rb").read())
    cur = bytes(data[SITE - VA2FILE: SITE - VA2FILE + 5])
    if cur == NEW:
        print("already applied - defenders engage immediately")
        return
    assert cur == OLD, "site mismatch @%08X: %s (expected %s)" % (
        SITE, cur.hex(' '), OLD.hex(' '))
    print("site  @ %08X: %s -> %s" % (SITE, cur.hex(' '), NEW.hex(' ')))
    print("       (TCAI.EvalBattle's 'can the human see this tile?' check)")
    if mode != "--apply":
        print("dry run OK - rerun with --apply")
        return
    if not os.path.exists(BAK):
        shutil.copyfile(DLL, BAK)
        print("backup ->", os.path.basename(BAK))
    data[SITE - VA2FILE: SITE - VA2FILE + 5] = NEW
    open(DLL, "wb").write(data)
    print("APPLIED - site defenders engage from the first turn again.")


main()
