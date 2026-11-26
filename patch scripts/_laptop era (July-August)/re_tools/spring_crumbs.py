#!/usr/bin/env python3
"""Read the Spring of Life diagnostic breadcrumbs from a running AoWx.exe.

The v4.2 cave (build_spring_wasteland.py) records its progress in BSS slack
at VA 0x558FA8F0 (AoWEPACK.dll preferred base 0x55700000, RVA 0x1FA8F0):

  +0  flags: bit0 wasteland, bit1 blessed        (written at cave return)
  +1  stage: 10 entry, 20 count-ok, 30 terrain-read, 40 reseeded,
             50 log-created, 58 log-filled, 60 snapshot, 70 loop,
             80 loop-done, 90 gameover-checked, A0 distributed,
             B0 log-freed, C0 validated, FF returned
  +2  sound-block entries this placement (sfx_pick increments)
  +3  last sfx pick (1 = ENCHP02 blessing chime, 2 = APest)
  +4  terrain byte read from the cell
  +5  anim gate: 1 = blessing anim shown, 2 = suppressed, 0 = not reached

If the exception fired mid-cave, +1 shows the LAST completed stage - the
throw happened between it and the next one. Run any time after the error
(before the next spring placement overwrites it); the game must still be
running. 64-bit Python reads the 32-bit process fine.
"""
import ctypes
import ctypes.wintypes as wt
import sys

SCRATCH_RVA = 0x1FA8F0
N = 8

PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
LIST_MODULES_32BIT = 0x01

k32 = ctypes.windll.kernel32
psapi = ctypes.windll.psapi

STAGES = {0x10: "entry", 0x20: "count-ok", 0x30: "terrain-read",
          0x40: "reseed+BeginUpdate", 0x50: "log-created", 0x58: "log-filled",
          0x60: "snapshot", 0x70: "unit-loop", 0x80: "loop-done",
          0x90: "gameover-checked", 0xA0: "distributed", 0xB0: "log-freed",
          0xC0: "validate+EndUpdate", 0xFF: "returned (cave completed)"}
TNAMES = {0: 'Water', 1: 'Grass', 2: 'Desert', 3: 'Snow', 4: 'Steppe',
          5: 'Wasteland', 6: 'Ice', 9: 'Lava', 0xB: 'CaveWasteland', 0xC: 'Dirt'}


def find_pid(name=b"aowx.exe"):
    import subprocess
    out = subprocess.check_output(
        ["tasklist", "/FI", "IMAGENAME eq AoWx.exe", "/FO", "CSV", "/NH"],
        text=True)
    for line in out.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) >= 2 and parts[0].lower() == "aowx.exe":
            return int(parts[1])
    return None


def module_base(h, want=b"aowepack.dll"):
    mods = (wt.HMODULE * 1024)()
    needed = wt.DWORD()
    if not psapi.EnumProcessModulesEx(h, mods, ctypes.sizeof(mods),
                                      ctypes.byref(needed), LIST_MODULES_32BIT):
        return None
    buf = ctypes.create_string_buffer(260)
    for i in range(needed.value // ctypes.sizeof(wt.HMODULE)):
        psapi.GetModuleBaseNameA(h, mods[i], buf, 260)
        if buf.value.lower() == want:
            return mods[i]
    return None


def main():
    pid = find_pid()
    if not pid:
        print("AoWx.exe is not running.")
        return 1
    h = k32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
    if not h:
        print("OpenProcess failed (err %d)" % k32.GetLastError())
        return 1
    base = module_base(h)
    if not base:
        print("AoWEPACK.dll not found in process %d." % pid)
        return 1
    addr = base + SCRATCH_RVA
    buf = ctypes.create_string_buffer(N)
    got = ctypes.c_size_t()
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, N,
                                 ctypes.byref(got)):
        print("ReadProcessMemory failed (err %d)" % k32.GetLastError())
        return 1
    d = buf.raw
    print("AoWx.exe pid %d, AoWEPACK.dll base 0x%X (delta %+#x), scratch @0x%X"
          % (pid, base, base - 0x55700000, addr))
    print("raw bytes:", d.hex(" "))
    print("  flags     : 0x%02X (wasteland=%d blessed=%d)" % (d[0], d[0] & 1, (d[0] >> 1) & 1))
    print("  stage     : 0x%02X %s" % (d[1], STAGES.get(d[1], "?? (mid-stage - threw after previous stage)")))
    print("  sfx count : %d" % d[2])
    print("  sfx pick  : %d (%s)" % (d[3], {0: "none", 1: "ENCHP02 chime", 2: "APest"}.get(d[3], "?")))
    print("  terrain   : 0x%02X %s" % (d[4], TNAMES.get(d[4], "?")))
    print("  anim gate : %d (%s)" % (d[5], {0: "not reached", 1: "anim shown", 2: "suppressed"}.get(d[5], "?")))
    if d[1] not in (0, 0xFF):
        print("\n>>> cave did NOT complete - exception between stage 0x%02X (%s) and the next stage." % (d[1], STAGES.get(d[1], '?')))
    elif d[1] == 0xFF:
        print("\n>>> cave completed; if an exception occurred it was AFTER the cave (sound block or later).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
