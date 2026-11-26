#!/usr/bin/env python3
r"""Read the --trace ring written by patch_tc_hail_msg_spell_v1.py's diagnostic caves out of the RUNNING game.

Run elevated (the game runs elevated):  Start-Process py -Verb RunAs -ArgumentList '"...\hail_trace_probe.py"'
Output goes to hail_trace_log.txt next to this script (and stdout).
Layout (AoWTCPCK.dll, VA relative to its preferred base 0x400000; the DLL is always relocated):
  0x46B7C8 handler hits, 0x46B7CC sender hits, 0x46B7D0 8 x {msg+0xC spell id, msg id} ring, 0x46B810 last sender id.
"""
import ctypes, ctypes.wintypes as wt, os, struct, subprocess, sys, time

k32 = ctypes.windll.kernel32
psapi = ctypes.windll.psapi
PREF = 0x400000
TRACE = 0x46B7C8
LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hail_trace_log.txt")


def pids(name="AoWx.exe"):
    out = subprocess.check_output(["tasklist", "/FI", f"IMAGENAME eq {name}", "/FO", "CSV", "/NH"], text=True)
    r = []
    for line in out.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) >= 2 and parts[0].lower() == name.lower():
            r.append(int(parts[1]))
    return r


def modules(h):
    mods = (ctypes.c_void_p * 2048)(); need = wt.DWORD()
    psapi.EnumProcessModulesEx(h, mods, ctypes.sizeof(mods), ctypes.byref(need), 0x03)
    out = {}; nb = ctypes.create_string_buffer(260)
    for i in range(need.value // ctypes.sizeof(ctypes.c_void_p)):
        v = mods[i]
        if not v: continue
        psapi.GetModuleBaseNameA(h, ctypes.c_void_p(v), nb, 260)
        out[nb.value.lower().decode()] = v
    return out


def rd(h, a, n):
    buf = ctypes.create_string_buffer(n); got = ctypes.c_size_t()
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(a), buf, n, ctypes.byref(got)):
        return None
    return buf.raw[:got.value]


def main():
    lines = []
    def say(s):
        print(s); lines.append(s)
    ps = pids()
    if not ps:
        say("AoWx.exe not running"); return 1
    h = k32.OpenProcess(0x0410, False, ps[0])
    if not h:
        say("OpenProcess failed (run elevated): err %d" % k32.GetLastError()); return 1
    mods = modules(h)
    base = mods.get("aowtcpck.dll")
    say("pid %d  AoWTCPCK.dll base %s" % (ps[0], hex(base) if base else None))
    if not base:
        say("AoWTCPCK.dll not loaded (not in combat yet?)"); return 1
    a = base + (TRACE - PREF)
    b = rd(h, a, 0x4C)
    if not b:
        say("read failed at %#x err %d" % (a, k32.GetLastError())); return 1
    hits, shits = struct.unpack_from("<II", b, 0)
    last_sender = struct.unpack_from("<I", b, 0x48)[0]
    say("handler hits %d | sender hits %d | last sender spell id %d" % (hits, shits, last_sender))
    for i in range(8):
        sid, mid = struct.unpack_from("<II", b, 8 + 8 * i)
        say("  ring[%d] msg+0xC=%d msg id=%#x%s" % (i, sid, mid, "  <- newest" if hits and i == (hits - 1) % 8 else ""))
    # also show the caves themselves to prove the trace build is the one loaded
    cave = rd(h, base + (0x43C400 - PREF), 0x80)
    say("cave bytes @0x43C400: %s" % (cave.hex() if cave else None))
    open(LOG, "w").write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    rc = main()
    if "--wait" in sys.argv: input("enter to close")
    sys.exit(rc)
