"""One-shot breakpoint tracer for the tactical AI's spell block (TCAI.EvalBattle site 1) - 2026-11-14.
Attaches to AoWx.exe as a debugger, plants int3 at a few addresses, and reports which of them were reached (each
breakpoint fires once and is removed; registers are printed).  Removes everything and detaches when all fired, when
the game exits, or after the time limit.  Usage: py -3.10 indep_cast_trace.py [minutes]"""
import ctypes, ctypes.wintypes as wt, os, struct, subprocess, sys, time

IMAGE = os.environ.get("TRACE_IMAGE", "AoWx.exe")

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
psapi = ctypes.windll.psapi
k32.OpenProcess.restype = wt.HANDLE
k32.OpenThread.restype = wt.HANDLE
k32.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
k32.WriteProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
k32.FlushInstructionCache.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_size_t]
psapi.EnumProcessModulesEx.argtypes = [wt.HANDLE, ctypes.POINTER(ctypes.c_void_p), wt.DWORD, ctypes.POINTER(wt.DWORD), wt.DWORD]
psapi.GetModuleBaseNameW.argtypes = [wt.HANDLE, ctypes.c_void_p, wt.LPWSTR, wt.DWORD]

# (module, preferred VA, label)
POINTS = [
    ("aowtcpck.dll", 0x418B54, "A2 own unit HAS the looped ability (site 2)"),
    ("aowtcpck.dll", 0x418B7A, "C2 own unit: ability == 0x34 Spell Casting"),
    ("aowtcpck.dll", 0x418B93, "D2 caster is a THero"),
    ("aowtcpck.dll", 0x418BBE, "E2 spell type != 0 -> asks GetPlayer"),
    ("aowtcpck.dll", 0x418BEF, "F2 spell is KNOWN"),
    ("aowtcpck.dll", 0x418C1D, "G2 CanCastSpellInstantly = true"),
    ("aowtcpck.dll", 0x418C46, "H2 spell usable in combat -> added to the cast candidates"),
    ("aowtcpck.dll", 0x418F7E, "D3 site 3: hero caster"),
    ("aowtcpck.dll", 0x4195E1, "D4 site 4: hero caster"),
    ("aowepack.dll", 0x558E4224, "K GetPlayer(<0) stand-in path"),
]
PREF = {"aowtcpck.dll": 0x400000, "aowepack.dll": 0x55700000}


class EXC(ctypes.Structure):
    _fields_ = [("ExceptionCode", wt.DWORD), ("ExceptionFlags", wt.DWORD), ("ExceptionRecord", ctypes.c_void_p),
                ("ExceptionAddress", ctypes.c_void_p), ("NumberParameters", wt.DWORD),
                ("ExceptionInformation", ctypes.c_void_p * 15)]


class DBGEV(ctypes.Structure):
    _fields_ = [("dwDebugEventCode", wt.DWORD), ("dwProcessId", wt.DWORD), ("dwThreadId", wt.DWORD),
                ("exc", EXC), ("first", wt.DWORD), ("pad", ctypes.c_byte * 64)]


def pid_of():
    o = subprocess.run(["tasklist", "/FI", "IMAGENAME eq " + IMAGE, "/FO", "CSV", "/NH"], capture_output=True, text=True).stdout
    for l in o.splitlines():
        if l.startswith('"' + IMAGE + '"'):
            return int(l.split('","')[1])
    return 0


def main():
    mins = float(sys.argv[1]) if len(sys.argv) > 1 else 8
    t_end = time.time() + mins * 60
    pid = 0
    while time.time() < t_end and not pid:
        pid = pid_of() or (time.sleep(2) or 0)
    if not pid:
        print("AoWx.exe not running"); return 1
    h = k32.OpenProcess(0x1F0FFF, False, pid)
    base = {}
    want = [m for m in PREF if IMAGE == "AoWx.exe" or m == "aowepack.dll"]
    while time.time() < t_end and not all(m in base for m in want):
        mods = (ctypes.c_void_p * 1024)(); need = wt.DWORD()
        psapi.EnumProcessModulesEx(h, mods, ctypes.sizeof(mods), ctypes.byref(need), 1)
        for m in mods[:need.value // ctypes.sizeof(ctypes.c_void_p)]:
            nm = ctypes.create_unicode_buffer(260); psapi.GetModuleBaseNameW(h, m, nm, 260); base[nm.value.lower()] = m
        time.sleep(1)
    time.sleep(8)                                    # let start-up finish

    def rd(a, n):
        buf = ctypes.create_string_buffer(n); got = ctypes.c_size_t()
        return buf.raw if k32.ReadProcessMemory(h, ctypes.c_void_p(a), buf, n, ctypes.byref(got)) else None

    def wr(a, b):
        got = ctypes.c_size_t()
        ok = k32.WriteProcessMemory(h, ctypes.c_void_p(a), b, len(b), ctypes.byref(got))
        k32.FlushInstructionCache(h, ctypes.c_void_p(a), len(b))
        return ok

    if not k32.DebugActiveProcess(pid):
        print("DebugActiveProcess failed", ctypes.get_last_error()); return 1
    k32.DebugSetProcessKillOnExit(False)
    bps = {}
    for mod, va, label in POINTS:
        if mod not in base:
            continue
        a = va - PREF[mod] + base[mod]
        orig = rd(a, 1)
        if orig and wr(a, b"\xCC"):
            bps[a] = [orig, label, False]
    print("attached pid %d, %d breakpoints, waiting up to %.0f min" % (pid, len(bps), (t_end - time.time()) / 60)); sys.stdout.flush()
    ev = DBGEV()
    pers = 0x418B54 - 0x400000 + base["aowtcpck.dll"] if "aowtcpck.dll" in base else 0
    rearm, units, pers_hits = {}, {}, [0]
    ctx = ctypes.create_string_buffer(716)
    k32.Wow64GetThreadContext.argtypes = [wt.HANDLE, ctypes.c_void_p]
    k32.Wow64SetThreadContext.argtypes = [wt.HANDLE, ctypes.c_void_p]
    alive = True
    try:
        while time.time() < t_end and alive and not (all(v[2] for v in bps.values()) and pers_hits[0] >= 400000):
            if not k32.WaitForDebugEvent(ctypes.byref(ev), 500):
                continue
            cont = 0x00010002                        # DBG_CONTINUE
            if ev.dwDebugEventCode == 1:             # exception
                code, addr = ev.exc.ExceptionCode, ev.exc.ExceptionAddress or 0
                if code in (0x80000004, 0x4000001E):            # single step: re-arm the persistent breakpoint
                    if rearm.get(ev.dwThreadId):
                        wr(rearm.pop(ev.dwThreadId), b"\xCC")
                elif code in (0x80000003, 0x4000001F):
                    if addr in bps and (not bps[addr][2] or addr == pers):
                        first = not bps[addr][2]
                        bps[addr][2] = True
                        wr(addr, bps[addr][0])
                        th = k32.OpenThread(0x1F03FF, False, ev.dwThreadId)
                        struct.pack_into("<I", ctx, 0, 0x10007)
                        if k32.Wow64GetThreadContext(th, ctx):
                            r = dict(zip(("edi", "esi", "ebx", "edx", "ecx", "eax", "ebp", "eip"), struct.unpack_from("<8I", ctx, 0x9C)))
                            struct.pack_into("<I", ctx, 0xB8, addr)
                            if addr == pers:
                                pers_hits[0] += 1
                                cu = struct.unpack("<I", rd(r["ebp"] - 0x28, 4) or b"\0\0\0\0")[0]
                                un = struct.unpack("<I", rd(cu + 0x4C, 4) or b"\0\0\0\0")[0] if cu else 0
                                if un and un not in units:
                                    ub = rd(un, 0x90) or bytes(0x90)
                                    vmt, bits, nbits = struct.unpack_from("<I", ub, 0)[0], struct.unpack_from("<I", ub, 8)[0], struct.unpack_from("<I", ub, 0xC)[0]
                                    raw = rd(bits, min((nbits + 7) // 8, 64)) or b""
                                    abil = [i for i in range(min(nbits, len(raw) * 8)) if raw[i // 8] >> (i % 8) & 1]
                                    hero = vmt - base["aowepack.dll"] + 0x55700000 in (0x55711FEC, 0x55712238)
                                    nm = ""
                                    if hero:
                                        pn = struct.unpack_from("<I", ub, 0x60)[0]
                                        ln = struct.unpack("<I", rd(pn - 4, 4) or b"\0\0\0\0")[0] if pn else 0
                                        nm = (rd(pn, ln) or b"").decode("latin1") if 0 < ln < 60 else ""
                                    units[un] = 1
                                    print("    AI unit %#x vmt %#x %s owner %d cp %d abilities %s%s" % (
                                        un, vmt - base["aowepack.dll"] + 0x55700000, ("HERO '%s'" % nm) if hero else "unit",
                                        struct.unpack_from("<b", ub, 0x24)[0], struct.unpack_from("<b", ub, 0x80)[0],
                                        " ".join("%X" % i for i in abil), "  <-- has 0x34" if 0x34 in abil else ""))
                                if pers_hits[0] < 400000:
                                    struct.pack_into("<I", ctx, 0xC0, struct.unpack_from("<I", ctx, 0xC0)[0] | 0x100)
                                    rearm[ev.dwThreadId] = addr
                            k32.Wow64SetThreadContext(th, ctx)
                            if not first:
                                k32.CloseHandle(th)
                                k32.ContinueDebugEvent(ev.dwProcessId, ev.dwThreadId, cont)
                                sys.stdout.flush()
                                continue
                            extra = ""
                            fr = rd(r["ebp"] - 0x30, 0x30)
                            if fr and bps[addr][1][0] in "ACDEFGH":
                                extra = " | ability [ebp-0xc]=%#x spell [ebp-0x10]=%d" % (struct.unpack_from("<I", fr, 0x30 - 0xC)[0], struct.unpack_from("<i", fr, 0x30 - 0x10)[0])
                            print("[%s] HIT %s  eax=%08X edx=%08X%s" % (time.strftime("%H:%M:%S"), bps[addr][1], r["eax"], r["edx"], extra))
                        k32.CloseHandle(th)
                        sys.stdout.flush()
                else:
                    cont = 0x80010001                # not ours -> the game's own handlers
            elif ev.dwDebugEventCode == 5:           # exit process
                alive = False
            k32.ContinueDebugEvent(ev.dwProcessId, ev.dwThreadId, cont)
    finally:
        if alive:
            for a, (orig, _l, hit) in bps.items():
                wr(a, orig)
        k32.DebugActiveProcessStop(pid)
    print("not reached:", [v[1] for v in bps.values() if not v[2]])
    print("trace done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
