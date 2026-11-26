"""Multi-shot breakpoint tracer for TCAI.EvalBattle's own-caster spell blocks (sites 2-4) - 2026-11-14.
Each point fires up to LIMIT times (re-armed with a single step), printing spell id [ebp-0x10], ability [ebp-0xc] and
the caster name.  Detaches by itself.  Usage: py -3.10 tcai_trace2.py [minutes]"""
import ctypes, ctypes.wintypes as wt, struct, subprocess, sys, time

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
psapi = ctypes.windll.psapi
k32.OpenProcess.restype = wt.HANDLE
k32.OpenThread.restype = wt.HANDLE
k32.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
k32.WriteProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
k32.FlushInstructionCache.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_size_t]
k32.Wow64GetThreadContext.argtypes = [wt.HANDLE, ctypes.c_void_p]
k32.Wow64SetThreadContext.argtypes = [wt.HANDLE, ctypes.c_void_p]
psapi.EnumProcessModulesEx.argtypes = [wt.HANDLE, ctypes.POINTER(ctypes.c_void_p), wt.DWORD, ctypes.POINTER(wt.DWORD), wt.DWORD]
psapi.GetModuleBaseNameW.argtypes = [wt.HANDLE, ctypes.c_void_p, wt.LPWSTR, wt.DWORD]
LIMIT = 12
POINTS = [  # TCPCK preferred VA, label
    (0x418BEF, "S2 known"), (0x418C1D, "S2 cancast"), (0x418C46, "S2 ADDED (usable flag 2)"),
    (0x418FCA, "S3 known"), (0x418FF8, "S3 cancast"), (0x419021, "S3 ADDED (usable flag 1)"),
    (0x41963D, "S4 known"), (0x41966F, "S4 cancast"), (0x419698, "S4 ADDED (usable flag 1)"),
]


class EXC(ctypes.Structure):
    _fields_ = [("ExceptionCode", wt.DWORD), ("ExceptionFlags", wt.DWORD), ("ExceptionRecord", ctypes.c_void_p),
                ("ExceptionAddress", ctypes.c_void_p), ("NumberParameters", wt.DWORD),
                ("ExceptionInformation", ctypes.c_void_p * 15)]


class DBGEV(ctypes.Structure):
    _fields_ = [("dwDebugEventCode", wt.DWORD), ("dwProcessId", wt.DWORD), ("dwThreadId", wt.DWORD),
                ("exc", EXC), ("first", wt.DWORD), ("pad", ctypes.c_byte * 64)]


def pid_of():
    o = subprocess.run(["tasklist", "/FI", "IMAGENAME eq AoWx.exe", "/FO", "CSV", "/NH"], capture_output=True, text=True).stdout
    for l in o.splitlines():
        if l.startswith('"AoWx.exe"'):
            return int(l.split('","')[1])
    return 0


def main():
    mins = float(sys.argv[1]) if len(sys.argv) > 1 else 8
    t_end = time.time() + mins * 60
    pid = 0
    while time.time() < t_end and not pid:
        pid = pid_of()
        if not pid:
            time.sleep(2)
    if not pid:
        print("AoWx.exe not running"); return 1
    h = k32.OpenProcess(0x1F0FFF, False, pid)
    tc = 0
    while time.time() < t_end and not tc:
        mods = (ctypes.c_void_p * 1024)(); need = wt.DWORD()
        psapi.EnumProcessModulesEx(h, mods, ctypes.sizeof(mods), ctypes.byref(need), 1)
        for m in mods[:need.value // ctypes.sizeof(ctypes.c_void_p)]:
            nm = ctypes.create_unicode_buffer(260); psapi.GetModuleBaseNameW(h, m, nm, 260)
            if nm.value.lower() == "aowtcpck.dll":
                tc = m
        time.sleep(1)
    time.sleep(6)

    def rd(a, n):
        buf = ctypes.create_string_buffer(n); got = ctypes.c_size_t()
        return buf.raw if k32.ReadProcessMemory(h, ctypes.c_void_p(a), buf, n, ctypes.byref(got)) else None

    def u32(a):
        b = rd(a, 4)
        return struct.unpack("<I", b)[0] if b else 0

    def wr(a, b):
        got = ctypes.c_size_t()
        ok = k32.WriteProcessMemory(h, ctypes.c_void_p(a), b, len(b), ctypes.byref(got))
        k32.FlushInstructionCache(h, ctypes.c_void_p(a), len(b))
        return ok

    if not k32.DebugActiveProcess(pid):
        print("DebugActiveProcess failed", ctypes.get_last_error()); return 1
    k32.DebugSetProcessKillOnExit(False)
    bps = {}
    for va, label in POINTS:
        a = va - 0x400000 + tc
        orig = rd(a, 1)
        if orig and wr(a, bytes([0xCC])):
            bps[a] = [orig, label, 0]
    print("attached pid %d, %d breakpoints, up to %.1f min" % (pid, len(bps), (t_end - time.time()) / 60)); sys.stdout.flush()
    ev = DBGEV(); ctx = ctypes.create_string_buffer(716)
    rearm, alive = {}, True
    try:
        while time.time() < t_end and alive:
            if not k32.WaitForDebugEvent(ctypes.byref(ev), 500):
                continue
            cont = 0x00010002
            if ev.dwDebugEventCode == 1:
                code, addr = ev.exc.ExceptionCode, ev.exc.ExceptionAddress or 0
                if code in (0x80000004, 0x4000001E):
                    if ev.dwThreadId in rearm:
                        wr(rearm.pop(ev.dwThreadId), bytes([0xCC]))
                elif code in (0x80000003, 0x4000001F):
                    if addr in bps:
                        bp = bps[addr]
                        wr(addr, bp[0])
                        bp[2] += 1
                        th = k32.OpenThread(0x1F03FF, False, ev.dwThreadId)
                        struct.pack_into("<I", ctx, 0, 0x10007)
                        if k32.Wow64GetThreadContext(th, ctx):
                            ebp = struct.unpack_from("<I", ctx, 0xB4)[0]
                            struct.pack_into("<I", ctx, 0xB8, addr)
                            if bp[2] < LIMIT:
                                struct.pack_into("<I", ctx, 0xC0, struct.unpack_from("<I", ctx, 0xC0)[0] | 0x100)
                                rearm[ev.dwThreadId] = addr
                            k32.Wow64SetThreadContext(th, ctx)
                            un = u32(u32(ebp - 0x28) + 0x4C)
                            pn = u32(un + 0x60); ln = u32(pn - 4) if pn else 0
                            nm = (rd(pn, ln) or b"").decode("latin1") if 0 < ln < 60 else "?"
                            fl = rd(ebp - 0x5A, 8) or bytes(8)
                            print("[%s] %-28s spell %3d ability %#x caster '%s' owner %d cp %d  flags[-0x57]=%#x [-0x53]=%#x" % (
                                time.strftime("%H:%M:%S"), bp[1], struct.unpack("<i", rd(ebp - 0x10, 4) or bytes(4))[0],
                                u32(ebp - 0xC), nm, struct.unpack("<b", rd(un + 0x24, 1) or b"\0")[0] if un else 0,
                                struct.unpack("<b", rd(un + 0x80, 1) or b"\0")[0] if un else 0, fl[3], fl[7]))
                        k32.CloseHandle(th)
                        sys.stdout.flush()
                else:
                    cont = 0x80010001
            elif ev.dwDebugEventCode == 5:
                alive = False
            k32.ContinueDebugEvent(ev.dwProcessId, ev.dwThreadId, cont)
    finally:
        if alive:
            for a, (orig, _l, _n) in bps.items():
                wr(a, orig)
        k32.DebugActiveProcessStop(pid)
    print("hit counts:", {v[1]: v[2] for v in bps.values()})
    print("trace done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
