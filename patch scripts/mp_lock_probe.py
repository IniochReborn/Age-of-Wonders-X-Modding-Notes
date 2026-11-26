r"""Multiplayer lock-up snapshot (2026-11-16).

Run this WHILE the game is frozen ("locked up with no error").  It only READS memory of every running AoWx.exe
(no debugger, no breakpoints, nothing written) and appends a report to  <game>\X\Lock Probe.txt :
map state (turn player, combat, seed), the token executer / token controls / AI executer raw state, and three
samples of where the main thread is executing.  Comparing the instances shows who is waiting for whom.

Usage (elevated prompt if the game runs elevated):   py -3.10 mp_lock_probe.py            one snapshot now
                                                     py -3.10 mp_lock_probe.py --watch    keep watching: compact
    state line per instance on every change (X\Lock Watch.txt) + an automatic full snapshot after 90 s of no change
Run it on every PC that takes part (or once on a PC running several instances) and send the file.
"""
import ctypes, ctypes.wintypes as wt, os, struct, subprocess, sys, time

IMAGE = "AoWx.exe"
HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.environ.get("AOW_GAME_DIR") or os.path.dirname(HERE)
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
psapi = ctypes.windll.psapi
k32.OpenProcess.restype = wt.HANDLE
k32.OpenThread.restype = wt.HANDLE
k32.CreateToolhelp32Snapshot.restype = wt.HANDLE
k32.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
k32.Wow64GetThreadContext.argtypes = [wt.HANDLE, ctypes.c_void_p]
psapi.EnumProcessModulesEx.argtypes = [wt.HANDLE, ctypes.POINTER(ctypes.c_void_p), wt.DWORD, ctypes.POINTER(wt.DWORD), wt.DWORD]
psapi.GetModuleBaseNameW.argtypes = [wt.HANDLE, ctypes.c_void_p, wt.LPWSTR, wt.DWORD]


class MODINFO(ctypes.Structure):
    _fields_ = [("lpBaseOfDll", ctypes.c_void_p), ("SizeOfImage", wt.DWORD), ("EntryPoint", ctypes.c_void_p)]


class TE32(ctypes.Structure):
    _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD), ("th32ThreadID", wt.DWORD), ("th32OwnerProcessID", wt.DWORD),
                ("tpBasePri", wt.LONG), ("tpDeltaPri", wt.LONG), ("dwFlags", wt.DWORD)]


psapi.GetModuleInformation.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.POINTER(MODINFO), wt.DWORD]
MAPG = 0x558FA040 - 0x55700000            # AoWEPACK RVA of the map global


def pids():
    o = subprocess.run(["tasklist", "/FI", "IMAGENAME eq " + IMAGE, "/FO", "CSV", "/NH"], capture_output=True, text=True).stdout
    return [int(l.split('","')[1]) for l in o.splitlines() if l.lower().startswith('"' + IMAGE.lower() + '"')]


def probe(pid, out):
    h = k32.OpenProcess(0x1F0FFF, False, pid)
    if not h:
        out("pid %d: OpenProcess failed (%d) - run elevated" % (pid, ctypes.get_last_error())); return
    mods = (ctypes.c_void_p * 1024)(); need = wt.DWORD(); ml = []
    psapi.EnumProcessModulesEx(h, mods, ctypes.sizeof(mods), ctypes.byref(need), 1)
    for m in mods[:need.value // ctypes.sizeof(ctypes.c_void_p)]:
        nm = ctypes.create_unicode_buffer(260); psapi.GetModuleBaseNameW(h, m, nm, 260)
        mi = MODINFO(); psapi.GetModuleInformation(h, m, ctypes.byref(mi), ctypes.sizeof(mi))
        ml.append((m, mi.SizeOfImage, nm.value))
    base = {n.lower(): b for b, _s, n in ml}

    def sym(a):
        for b, s, n in ml:
            if b <= a < b + s: return "%s+0x%X" % (n, a - b)
        return ""

    def rd(a, n):
        buf = ctypes.create_string_buffer(n); got = ctypes.c_size_t()
        return buf.raw if a and k32.ReadProcessMemory(h, ctypes.c_void_p(a), buf, n, ctypes.byref(got)) else None

    def u32(a):
        b = rd(a, 4)
        return struct.unpack("<I", b)[0] if b else 0

    def dump(label, a, n):
        b = rd(a, n)
        if not b: out("  %s @%08X: unreadable" % (label, a)); return b""
        out("  %s @%08X (class %s)" % (label, a, sym(struct.unpack_from("<I", b, 0)[0])))
        for o in range(0, n, 16):
            out("    +%02X  %s" % (o, " ".join("%08X" % x for x in struct.unpack_from("<%dI" % (len(b[o:o + 16]) // 4), b, o))))
        return b

    def tlist(label, a, lim=12, n=0x38):
        b = rd(a, 12)
        if not b: return
        items, cnt = struct.unpack_from("<II", b, 4)
        if not (0 <= cnt <= 4096) or (cnt and not rd(items, 4)): return
        out("  %s: list of %d" % (label, cnt))
        for i in range(min(cnt, lim)):
            dump("%s[%d]" % (label, i), u32(items + 4 * i), n)

    out("===== pid %d  %s  AoWEPACK @%08X" % (pid, time.strftime("%Y-%m-%d %H:%M:%S"), base.get("aowepack.dll", 0)))
    mp = u32(base.get("aowepack.dll", 0) + MAPG)
    if not mp:
        out("  no map loaded"); return
    mb = rd(mp, 0x250) or bytes(0x250)
    g = lambda o, f="<I": struct.unpack_from(f, mb, o)[0]
    out("  map @%08X: turn player %d, local player %d, combat obj %08X, +0x118 %d, +0x11A %d, +0x11C %08X, +0x138..13A %s, game-over lock +0x174 %d, "
        "sync seed +0x230 %08X, play mode +0x239 %d, flags +0x3C %02X" % (mp, g(0xA4, "b"), g(0xA5, "b"), g(0x120), g(0x118, "B"), g(0x11A, "B"),
        g(0x11C), mb[0x138:0x13B].hex(), g(0x174), g(0x230), g(0x239, "B"), g(0x3C, "B")))
    tm = g(0x23C)
    tb = dump("TTokenManager [map+0x23C]", tm, 0x30)
    ex = struct.unpack_from("<I", tb, 4)[0] if len(tb) >= 8 else 0
    eb = dump("TTokenExecuter [tokman+4] (+0x18 executed count, +0x4C lock, +0x54 hold)", ex, 0x60)
    for o in (4, 8, 0xC, 0x10, 0x14):
        if len(eb) >= o + 4:
            p = struct.unpack_from("<I", eb, o)[0]
            if p and rd(p, 4):
                dump("executer+0x%X ->" % o, p, 0x30); tlist("executer+0x%X items" % o, p)
    for o in range(8, 0x30, 4):
        if len(tb) >= o + 4:
            p = struct.unpack_from("<I", tb, o)[0]
            if p and rd(p, 4):
                dump("tokman+0x%X ->" % o, p, 0x30); tlist("tokman+0x%X items" % o, p)
    dump("TAIExecuter [map+0x128] (+0x30 AI lock)", g(0x128), 0x40)
    dump("TPlayerControl [map+0x244] (+0x18 disconnect list, +0x1C OoS shown)", g(0x244), 0x30)
    if g(0x120): dump("TCombat [map+0x120]", g(0x120), 0x40)
    # main thread samples
    snap = k32.CreateToolhelp32Snapshot(4, 0); te = TE32(); te.dwSize = ctypes.sizeof(TE32); tids = []
    ok = k32.Thread32First(snap, ctypes.byref(te))
    while ok:
        if te.th32OwnerProcessID == pid: tids.append(te.th32ThreadID)
        ok = k32.Thread32Next(snap, ctypes.byref(te))
    k32.CloseHandle(snap)
    if tids:
        th = k32.OpenThread(0x1F03FF, False, min(tids)); ctx = ctypes.create_string_buffer(716)
        for s in range(3):
            k32.SuspendThread(th)
            struct.pack_into("<I", ctx, 0, 0x10007)
            if k32.Wow64GetThreadContext(th, ctx):
                eip, esp = struct.unpack_from("<I", ctx, 0xB8)[0], struct.unpack_from("<I", ctx, 0xC4)[0]
                st = rd(esp, 0x600) or b""
                rets = [sym(x) for x in struct.unpack_from("<%dI" % (len(st) // 4), st, 0)]
                rets = [r for r in rets if r and not r.lower().startswith(("ntdll", "wow64"))][:18]
                out("  main thread sample %d: eip %s | stack: %s" % (s + 1, sym(eip) or "%08X" % eip, " ".join(rets)))
            k32.ResumeThread(th)
            time.sleep(0.4)
        k32.CloseHandle(th)
    k32.CloseHandle(h)


def compact(pid):
    """(text, key) of the fields that move while the game runs; key None = no map"""
    h = k32.OpenProcess(0x0410, False, pid)
    if not h: return "open failed", None
    try:
        mods = (ctypes.c_void_p * 1024)(); need = wt.DWORD(); ep = 0
        psapi.EnumProcessModulesEx(h, mods, ctypes.sizeof(mods), ctypes.byref(need), 1)
        for m in mods[:need.value // ctypes.sizeof(ctypes.c_void_p)]:
            nm = ctypes.create_unicode_buffer(260); psapi.GetModuleBaseNameW(h, m, nm, 260)
            if nm.value.lower() == "aowepack.dll": ep = m
        def rd(a, n):
            buf = ctypes.create_string_buffer(n); got = ctypes.c_size_t()
            return buf.raw if a and k32.ReadProcessMemory(h, ctypes.c_void_p(a), buf, n, ctypes.byref(got)) else None
        def u32(a):
            b = rd(a, 4); return struct.unpack("<I", b)[0] if b else 0
        mp = u32(ep + MAPG) if ep else 0
        if not mp: return "no map", None
        mb = rd(mp, 0x250) or bytes(0x250)
        g = lambda o, f="<I": struct.unpack_from(f, mb, o)[0]
        ex = u32(g(0x23C) + 4) if g(0x23C) else 0
        eb = rd(ex, 0x60) or bytes(0x60)
        e = lambda o: struct.unpack_from("<I", eb, o)[0]
        ai = rd(g(0x128), 0x40) or bytes(0x40)
        key = (g(0xA4, "b"), g(0x120) != 0, e(0x18), e(0x4C), e(0x54), struct.unpack_from("<I", ai, 0x30)[0], g(0x230), g(0x11C))
        return ("turn %d local %d combat %s | executed %d lock %d hold %d | AI lock %d | +0x11C %X | seed %08X" % (
            g(0xA4, "b"), g(0xA5, "b"), "yes" if g(0x120) else "no", e(0x18), e(0x4C), e(0x54) & 0xFF,
            struct.unpack_from("<I", ai, 0x30)[0], g(0x11C), g(0x230))), key
    finally:
        k32.CloseHandle(h)


def watch(mins):
    """log a compact state line per instance whenever it changes; full probe once when nothing moved for 90 s"""
    os.makedirs(os.path.join(GAME, "X"), exist_ok=True)
    f = open(os.path.join(GAME, "X", "Lock Watch.txt"), "a", encoding="utf-8")
    def out(s):
        f.write(s + "\n"); f.flush(); print(s); sys.stdout.flush()
    out("===== lock watch started %s (compact line on every change; full dump in Lock Probe.txt after 90 s without change)" % time.strftime("%Y-%m-%d %H:%M:%S"))
    last, since, dumped, beat = {}, {}, set(), {}
    t_end = time.time() + mins * 60
    while time.time() < t_end:
        now = time.time(); ps = pids()
        for p in ps:
            try: txt, key = compact(p)
            except Exception as ex: txt, key = "error %r" % ex, None
            if last.get(p) != (txt if key is None else key):
                last[p] = txt if key is None else key; since[p] = now; dumped.discard(p); beat[p] = now
                out("[%s] pid %d %s" % (time.strftime("%H:%M:%S"), p, txt))
            elif now - beat.get(p, 0) >= 60:
                beat[p] = now
                out("[%s] pid %d unchanged for %d s: %s" % (time.strftime("%H:%M:%S"), p, now - since[p], txt))
            if key is not None and now - since[p] >= 90 and p not in dumped:
                dumped.update(ps)
                out("[%s] pid %d has not moved for 90 s -> full probe of all instances (Lock Probe.txt)" % (time.strftime("%H:%M:%S"), p))
                pf = open(os.path.join(GAME, "X", "Lock Probe.txt"), "a", encoding="utf-8")
                def pout(s): pf.write(s + "\n")
                for rnd in range(2):
                    for q in ps:
                        try: probe(q, pout)
                        except Exception as ex: pout("pid %d: probe error %r" % (q, ex))
                    if rnd == 0: time.sleep(3)
                pout(""); pf.close()
        for p in list(last):
            if p not in ps:
                out("[%s] pid %d exited" % (time.strftime("%H:%M:%S"), p)); last.pop(p)
        time.sleep(2)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--watch":
        watch(float(sys.argv[2]) if len(sys.argv) > 2 else 240); return 0
    ps = pids()
    if not ps:
        print("No AoWx.exe is running."); return 1
    os.makedirs(os.path.join(GAME, "X"), exist_ok=True)
    f = open(os.path.join(GAME, "X", "Lock Probe.txt"), "a", encoding="utf-8")

    def out(s):
        f.write(s + "\n"); print(s)
    for rnd in range(2):                              # two rounds 3 s apart: shows what still advances
        for p in ps:
            try: probe(p, out)
            except Exception as e: out("pid %d: probe error %r" % (p, e))
        if rnd == 0: time.sleep(3)
    out("")
    print("\nwritten to", f.name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
