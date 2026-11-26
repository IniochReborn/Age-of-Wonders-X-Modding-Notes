#!/usr/bin/env python3
r"""A/B toggle for the always-explored stub in AoWTCPCK.dll.

The mod stubs AoWTCPCK's import thunk for `AoWE.TAoWMapField.GetExplored`
(file 0x1C7C / VA 0x40287C) to `mov eax,1; ret`, so every combat tile reports
"explored" to AoWTCPCK. That is the "site defenders attack immediately instead
of waiting to be seen" behaviour.

WHY YOU MIGHT WANT TO TOGGLE IT (2026-08-11): that stub is called from inside
the block that raises **"Error - TCAI: Error during Create Unit List"** -
`TCAI.EvalBattle` phase 0 (try/except 0x4181F8..0x418ABE, MessageBoxA at
0x418AD6). At 0x4183AA the AI does:

    mov   edx,[0x46C064]          ; the combat map
    movsx edx,byte [edx+0xA5]     ; the SEATED player id
    call  0x40287C                ; GetExplored(field, player)  <-- stubbed
    test  al,al / je ...          ; drives [ebp-0x33]

so the stub makes that scan answer "explored" for every field and every player.
Restoring the real import lets us A/B whether the stub is what breaks the
tactical AI's unit-list build in MP exploration-site combat.

  --restore : put the real `jmp [AoWE.TAoWMapField.GetExplored]` thunk back
              (defenders go back to waiting until seen)
  --stub    : re-apply the always-explored stub (the mod's normal state)
  (no args) : just report which state the file is in

Backup AoWTCPCK.dll.bak_getexplored is written on the first change.
"""
import os, shutil, struct, sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DLL = os.path.join(GAME, "AoWTCPCK.dll")
BAK = DLL + ".bak_getexplored"

OFF = 0x1C7C                       # VA 0x40287C
IAT_SLOT = 0x46E630                # AoWEPACK.dll!AoWE.TAoWMapField.GetExplored
REAL = b"\xFF\x25" + struct.pack("<I", IAT_SLOT)   # jmp dword [slot]
STUB = bytes.fromhex("B801000000C3")               # mov eax,1 ; ret


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--status"
    data = bytearray(open(DLL, "rb").read())
    cur = bytes(data[OFF:OFF + 6])
    state = ("STUB (always explored - defenders act immediately)" if cur == STUB
             else "REAL (vanilla - defenders wait until seen)" if cur == REAL
             else "UNKNOWN: " + cur.hex(' '))
    print("thunk @ VA %08X (file %#x): %s" % (OFF + 0x400C00, OFF, state))
    if mode == "--status":
        print("pass --restore (vanilla) or --stub (mod default)")
        return
    want = REAL if mode == "--restore" else STUB if mode == "--stub" else None
    if want is None:
        sys.exit("unknown option %r" % mode)
    if cur == want:
        print("already in that state - nothing to do")
        return
    if cur not in (REAL, STUB):
        sys.exit("refusing to touch an unrecognised thunk")
    if not os.path.exists(BAK):
        shutil.copyfile(DLL, BAK)
        print("backup ->", os.path.basename(BAK))
    data[OFF:OFF + 6] = want
    open(DLL, "wb").write(data)
    print("now:", "REAL (vanilla)" if want == REAL else "STUB (always explored)")


main()
