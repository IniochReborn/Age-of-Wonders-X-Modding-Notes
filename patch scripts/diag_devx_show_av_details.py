#!/usr/bin/env python3
"""DIAGNOSTIC: AoWDevX.exe shows the standard exception dialog (address + module) instead of "Oh dear, it's the end"
for access violations.  Application.OnException handler @0x4281EC: `je 0x428225` @0x4281FE (74 25) -> `jmp` (EB 25).
--apply / --revert.  Revert before any release cut.  Backup AoWDevX.exe.bak_avdiag (in <game>\backup\)."""
import os, shutil, sys
from bakpath import game_file, bak_path
EXE = game_file("AoWDevX.exe"); OFF = 0x4281FE - 0x400C00
d = bytearray(open(EXE, "rb").read()); cur = bytes(d[OFF:OFF + 2]); bak = bak_path(EXE, ".bak_avdiag", create="--apply" in sys.argv)
print("current:", cur.hex(), {"7425": "vanilla (Oh dear)", "eb25": "DIAG (details shown)"}.get(cur.hex(), "UNKNOWN"))
if "--revert" in sys.argv:
    d[OFF:OFF + 2] = b"\x74\x25"; open(EXE, "r+b").write(d); print("reverted to Oh dear"); sys.exit()
if "--apply" in sys.argv and cur == b"\x74\x25":
    if not os.path.exists(bak): shutil.copy2(EXE, bak)
    d[OFF:OFF + 2] = b"\xeb\x25"; open(EXE, "r+b").write(d); print("applied: AVs now show address/module")
