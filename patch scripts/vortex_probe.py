#!/usr/bin/env python3
r"""Watch every live ship (TUnit with Sailing 0x17) in the RUNNING game and report HP / movement
changes -- to see what the Vortex drain actually writes and to which object copy.

Use:  start AoWx (410), load the game, select nothing, then in an (elevated) prompt:
        py "patch scripts\vortex_probe.py"            one snapshot of all ships
        py "patch scripts\vortex_probe.py" --watch    poll twice a second; prints every change
      then cast Vortex on a ship stack and watch the console.

Per ship object: address, player, unit id, HP [+0x3E], MP [+0x3D], max MV (resource +0x2D),
resource name, owning army [+4]. Several copies of the same unit id are normal (world copy,
UI copy, fast-combat twins) -- the point is to see which copy's MP moves, if any.
"""
import ctypes, ctypes.wintypes as wt, subprocess, struct, sys, os, time

k32 = ctypes.windll.kernel32
psapi = ctypes.windll.psapi
PREF = 0x55700000
VMT_TUNIT = 0x55710CAC
SAILING = 0x17


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


def u32(h, a):
    b = rd(h, a, 4); return struct.unpack('<I', b)[0] if b and len(b) == 4 else None


def u8(h, a):
    b = rd(h, a, 1); return b[0] if b else None


def s8(h, a):
    v = u8(h, a); return None if v is None else (v - 256 if v > 127 else v)


class MBI(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_void_p), ("AllocationBase", ctypes.c_void_p),
                ("AllocationProtect", wt.DWORD), ("RegionSize", ctypes.c_size_t),
                ("State", wt.DWORD), ("Protect", wt.DWORD), ("Type", wt.DWORD)]


def scan_for(h, needle):
    addr = 0; mbi = MBI(); pat = struct.pack('<I', needle)
    while addr < 0x7FFF0000:
        if not k32.VirtualQueryEx(h, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
            break
        base = mbi.BaseAddress or 0; size = mbi.RegionSize
        if mbi.State == 0x1000 and mbi.Type != 0x1000000 and mbi.Protect in (0x04, 0x08, 0x40, 0x80):
            data = rd(h, base, size)
            if data:
                i = data.find(pat)
                while i != -1:
                    if i % 4 == 0: yield base + i
                    i = data.find(pat, i + 1)
        addr = base + size


def has_bit(h, owner, aid):
    bits, cnt = u32(h, owner + 8), u32(h, owner + 0xC)
    if not bits or cnt is None or aid >= cnt or cnt > 4096: return False
    w = u32(h, bits + (aid >> 5) * 4)
    return bool(w is not None and (w >> (aid & 31)) & 1)


def ansistr(h, p, n=40):
    if not p: return ""
    ln = u32(h, p - 4) or 0
    if ln <= 0 or ln > n: return ""
    b = rd(h, p, ln); return b.decode('latin1', 'replace') if b else ""


def snapshot(h, ships):
    out = {}
    for u in ships:
        out[u] = (u8(h, u + 0x3E), s8(h, u + 0x3D))
    return out


def describe(h, u):
    res = u32(h, u + 0x40) or 0
    mv = u8(h, res + 0x2D) if res else None
    nm = ansistr(h, u32(h, res + 0x24) or 0) if res else ""
    return "unit %08X id=%-4s pl=%-2s army=%08X %-16s HP=%-3s MP=%-3s maxMV=%s" % (
        u, u32(h, u + 0x18), u8(h, u + 0x24), u32(h, u + 4) or 0, nm, u8(h, u + 0x3E), s8(h, u + 0x3D), mv)


def main():
    ps = pids()
    if not ps:
        print("AoWx.exe is not running."); return 1
    watch = "--watch" in sys.argv
    pid = ps[0]
    h = k32.OpenProcess(0x410, False, pid)
    if not h:
        print("cannot open pid %d (try an elevated prompt)" % pid); return 1
    base = modules(h).get('aowepack.dll')
    if not base:
        print("AoWEPACK.dll not loaded"); return 1
    delta = base - PREF
    print("pid %d  AoWEPACK base %#x (delta %+#x)" % (pid, base, delta))
    def find_ships():
        found = set()
        for va in scan_for(h, VMT_TUNIT + delta):
            if has_bit(h, va, SAILING):
                found.add(va)
        return found

    ships = sorted(find_ships())
    print("%s  %d TUnit object(s) with Sailing:" % (time.strftime("%H:%M:%S"), len(ships)), flush=True)
    for u in ships:
        print("  " + describe(h, u), flush=True)
    if not watch:
        return 0
    print("\nwatching (Ctrl+C to stop) -- rescans for new ship objects every 5 s; cast Vortex when ready", flush=True)
    last = snapshot(h, ships)
    tick = 0
    try:
        while True:
            time.sleep(0.5)
            tick += 1
            if tick % 10 == 0:
                new = sorted(find_ships() - set(ships))
                if new:
                    print("  %s  %d new ship object(s):" % (time.strftime("%H:%M:%S"), len(new)), flush=True)
                    for u in new:
                        print("    " + describe(h, u), flush=True)
                    ships += new
                    for u in new:
                        last[u] = snapshot(h, [u])[u]
            cur = snapshot(h, ships)
            for u in ships:
                if cur[u] != last[u]:
                    print("  %s  CHANGED HP %s->%s  MP %s->%s   %s" % (
                        time.strftime("%H:%M:%S"), last[u][0], cur[u][0], last[u][1], cur[u][1],
                        describe(h, u)), flush=True)
            last = cur
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
