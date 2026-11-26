#!/usr/bin/env python3
r"""Read the fcheal autocombat diagnostic counters out of the RUNNING AoWx.exe.
Pairs with build_fcheal_diag.py. Apply the diag, start the game, run ONE
autocombat with a damaged elemental standing on its home terrain (e.g. Fire
Elemental on lava), leave the game running, then run this.
"""
import ctypes
import ctypes.wintypes as wt
import subprocess
import struct
import sys

k32 = ctypes.windll.kernel32
psapi = ctypes.windll.psapi

PREF_BASE = 0x55700000
DIAG_RVA = 0x558E9B40 - PREF_BASE
RIDX_RVA = 0x558E9C40 - PREF_BASE
RING_RVA = 0x558E9C48 - PREF_BASE
DIE_RVA = 0x558E9D50 - PREF_BASE

FIELDS = [
    (0x00, "rounds (hook hits)"),
    (0x04, "last TCombatData ptr"),
    (0x08, "last defender-hex pair"),
    (0x0C, "last attacker-hex pair"),
    (0x10, "last defender field ptr"),
    (0x14, "last attacker field ptr"),
    (0x18, "units passing IsClass"),
    (0x1C, "dead-flag skips"),
    (0x20, "null-strat skips"),
    (0x24, "HP==0 skips"),
    (0x28, "last unit resource index"),
    (0x2C, "last unit side byte"),
    (0x30, "index matches"),
    (0x34, "cursed skips"),
    (0x38, "heals applied"),
    (0x3C, "last roll (1-4)"),
    (0x40, "last HP before heal"),
    (0x48, "rounds w/ both pairs zero"),
    (0x4C, "last GetCount result"),
]
HEXFIELDS = {0x04, 0x08, 0x0C, 0x10, 0x14}


def pids(name="AoWx.exe"):
    out = subprocess.check_output(
        ["tasklist", "/FI", "IMAGENAME eq %s" % name, "/FO", "CSV", "/NH"],
        text=True)
    r = []
    for line in out.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) >= 2 and parts[0].lower() == name.lower():
            r.append(int(parts[1]))
    return r


def modules(h):
    mods = (ctypes.c_void_p * 2048)()
    need = wt.DWORD()
    psapi.EnumProcessModulesEx(h, mods, ctypes.sizeof(mods),
                               ctypes.byref(need), 0x03)
    out = {}
    nb = ctypes.create_string_buffer(260)
    for i in range(need.value // ctypes.sizeof(ctypes.c_void_p)):
        v = mods[i]
        if not v:
            continue
        psapi.GetModuleBaseNameA(h, ctypes.c_void_p(v), nb, 260)
        out[nb.value.lower().decode()] = v
    return out


def u32(h, a):
    buf = ctypes.create_string_buffer(4)
    got = ctypes.c_size_t()
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(a), buf, 4,
                                 ctypes.byref(got)):
        return None
    return struct.unpack("<I", buf.raw)[0]


def main():
    ps = pids()
    if not ps:
        print("AoWx.exe is not running.")
        return 1
    for pid in ps:
        h = k32.OpenProcess(0x410, False, pid)
        if not h:
            print("pid %d: cannot open" % pid)
            continue
        m = modules(h)
        base = m.get("aowepack.dll")
        print("=== pid %d: AoWEPACK.dll base %s"
              % (pid, hex(base) if base else "NOT LOADED"))
        if base:
            Dg = base + DIAG_RVA
            for off, name in FIELDS:
                v = u32(h, Dg + off)
                if v is None:
                    print("  %-28s: <unreadable>" % name)
                elif off in HEXFIELDS:
                    print("  %-28s: %08X" % (name, v))
                else:
                    print("  %-28s: %d" % (name, v))
            ridx = u32(h, base + RIDX_RVA) or 0
            print("  --- heal ring (%d writes, showing last %d) ---"
                  % (ridx, min(ridx, 32)))
            first = max(0, ridx - 32)
            for n in range(first, ridx):
                slot = n % 32
                w0 = u32(h, base + RING_RVA + slot * 8)
                w1 = u32(h, base + RING_RVA + slot * 8 + 4)
                if w0 is None:
                    break
                print("  heal#%-3d round=%-3d hp_before=%-3d roll=%d strat=%08X"
                      % (n, w0 >> 16, w0 & 0xFF, (w0 >> 8) & 0xFF, w1 or 0))
            dv = [u32(h, base + DIE_RVA + i * 4) for i in range(6)]
            print("  --- Die() records ---")
            print("  Die calls                   : %d" % (dv[0] or 0))
            print("  last unit ptr               : %08X" % (dv[1] or 0))
            print("  last flags<<8|side          : %04X" % (dv[2] or 0))
            print("  last strat HP at Die        : %d" % (dv[3] or 0))
            print("  last unit resource index    : %d" % (dv[4] or 0))
            print("  last combat ptr             : %08X" % (dv[5] or 0))
        k32.CloseHandle(h)
    return 0


if __name__ == "__main__":
    sys.exit(main())
