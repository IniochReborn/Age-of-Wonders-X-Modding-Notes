r"""Network / game-over event tracer for multiplayer host-leave diagnosis (2026-11-16).

Attaches to every running AoWx.exe (one worker per game instance) as a debugger, plants persistent int3 breakpoints
on the network and game-over handlers, and appends one line per hit to  <game>\X\Net Trace <pid>.txt .
Nothing in the game files is changed; the breakpoints are removed when the tracer stops (Ctrl+C), when the game
exits, or after the time limit.

Usage (start it before or after the game instances - new instances are picked up as they start; use an ELEVATED
prompt if the game runs elevated):
    py -3.10 net_trace.py            trace every AoWx.exe for up to 180 minutes
    py -3.10 net_trace.py 60         ... for 60 minutes
Then reproduce (host gets defeated in a 3+ player game) and send all "Net Trace *.txt" files + "Error Log.txt".
"""
import ctypes, ctypes.wintypes as wt, os, struct, subprocess, sys, time

IMAGE = "AoWx.exe"
HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.environ.get("AOW_GAME_DIR") or os.path.dirname(HERE)

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

PREF = {"aowx.exe": 0x400000, "aowepack.dll": 0x55700000, "aowdplay.dpl": 0x400000}
# (module, preferred VA, label, extra) - extra: "" | "pb" = player byte [eax+0x10] | "sys" = DirectPlay system msg id
POINTS = [
    ("aowx.exe", 0x414AA4, "exe DPlayDestroyPlayer (edx = DirectPlay id of the player that left)", ""),
    ("aowx.exe", 0x414878, "exe DPlaySessionLost", ""),
    ("aowx.exe", 0x414A6C, "exe DPlayMessageError", ""),
    ("aowx.exe", 0x4140B0, "exe DPlayEjected", ""),
    ("aowx.exe", 0x41400C, "exe DPlayMessageTimeout", ""),
    ("aowx.exe", 0x411F74, "exe LEAVE network game routine", ""),
    ("aowx.exe", 0x411FDD, "exe leave: hand host role to remote id edx", ""),
    ("aowx.exe", 0x411FFB, "exe leave: CloseSession", ""),
    ("aowx.exe", 0x41200A, "exe leave: DisConnect", ""),
    ("aowx.exe", 0x414806, "exe CloseSession (2nd site)", ""),
    ("aowx.exe", 0x414946, "exe session lost in lobby: DisConnect", ""),
    ("aowdplay.dpl", 0x404544, "DirectPlay SYSTEM message", "sys"),
    ("aowdplay.dpl", 0x405777, "DirectPlay Close() being called", ""),
    ("aowepack.dll", 0x5574A70C, "TTerminatePlayerTE.Execute (graceful leave of player)", "pb"),
    ("aowepack.dll", 0x5574A6C0, "TGameOverTE.Execute", "pb"),
    ("aowepack.dll", 0x557557C0, "TPlayerControl.GameOver (dl = player, cl = status)", ""),
    ("aowepack.dll", 0x5577669C, "TAoWHSMap.ExecuteGameOverEvent", ""),
    ("aowepack.dll", 0x55755EF8, "TPlayerControl.ExitGame (dl = mode)", ""),
    ("aowepack.dll", 0x557763F8, "TAoWHSMap.ExecuteExitGame", ""),
    ("aowepack.dll", 0x55756644, "TPlayerControl.PlayerDisconnected (dl = player)", ""),
    ("aowepack.dll", 0x55756670, "TPlayerControl.ConnectionLost", ""),
    ("aowepack.dll", 0x55754D14, "TPlayerControl.OutOfSync", ""),
    ("aowepack.dll", 0x557DFF44, "TSetupControl.hSetHostRemoteID (edx = new host remote id)", ""),
]
SYSMSG = {3: "CREATEPLAYERORGROUP", 5: "DESTROYPLAYERORGROUP", 0x31: "SESSIONLOST", 0x101: "HOST (this machine is now the DirectPlay host)",
          0x103: "SETPLAYERORGROUPNAME", 0x105: "SETSESSIONDESC", 0x107: "CHAT", 0x10D: "SENDCOMPLETE"}
MAPG = 0x558FA040


class EXC(ctypes.Structure):
    _fields_ = [("ExceptionCode", wt.DWORD), ("ExceptionFlags", wt.DWORD), ("ExceptionRecord", ctypes.c_void_p),
                ("ExceptionAddress", ctypes.c_void_p), ("NumberParameters", wt.DWORD),
                ("ExceptionInformation", ctypes.c_void_p * 15)]


class DBGEV(ctypes.Structure):
    _fields_ = [("dwDebugEventCode", wt.DWORD), ("dwProcessId", wt.DWORD), ("dwThreadId", wt.DWORD),
                ("exc", EXC), ("first", wt.DWORD), ("pad", ctypes.c_byte * 64)]


def pids():
    o = subprocess.run(["tasklist", "/FI", "IMAGENAME eq " + IMAGE, "/FO", "CSV", "/NH"], capture_output=True, text=True).stdout
    return [int(l.split('","')[1]) for l in o.splitlines() if l.lower().startswith('"' + IMAGE.lower() + '"')]


def worker(pid, mins):
    t_end = time.time() + mins * 60
    os.makedirs(os.path.join(GAME, "X"), exist_ok=True)
    out = open(os.path.join(GAME, "X", "Net Trace %d.txt" % pid), "a", encoding="utf-8")

    def log(s):
        line = "[%s.%03d] %s" % (time.strftime("%H:%M:%S"), int(time.time() * 1000) % 1000, s)
        out.write(line + "\n"); out.flush()
        print("pid %d %s" % (pid, line)); sys.stdout.flush()

    h = k32.OpenProcess(0x1F0FFF, False, pid)
    if not h:
        print("pid %d: OpenProcess failed (%d) - run this from an elevated prompt" % (pid, ctypes.get_last_error())); return 1
    base = {}
    t_mod = time.time() + 90                         # a freshly started game: wait until its modules are loaded
    while time.time() < t_mod and not all(m in base for m in PREF):
        mods = (ctypes.c_void_p * 1024)(); need = wt.DWORD()
        psapi.EnumProcessModulesEx(h, mods, ctypes.sizeof(mods), ctypes.byref(need), 1)
        for m in mods[:need.value // ctypes.sizeof(ctypes.c_void_p)]:
            nm = ctypes.create_unicode_buffer(260); psapi.GetModuleBaseNameW(h, m, nm, 260); base[nm.value.lower()] = m
        time.sleep(1)
    time.sleep(6)                                    # let start-up finish before planting breakpoints

    def rd(a, n):
        buf = ctypes.create_string_buffer(n); got = ctypes.c_size_t()
        return buf.raw if k32.ReadProcessMemory(h, ctypes.c_void_p(a), buf, n, ctypes.byref(got)) else None

    def wr(a, b):
        got = ctypes.c_size_t()
        ok = k32.WriteProcessMemory(h, ctypes.c_void_p(a), b, len(b), ctypes.byref(got))
        k32.FlushInstructionCache(h, ctypes.c_void_p(a), len(b))
        return ok

    def u32(a):
        b = rd(a, 4)
        return struct.unpack("<I", b)[0] if b else 0

    def state():
        if "aowepack.dll" not in base: return ""
        mp = u32(MAPG - PREF["aowepack.dll"] + base["aowepack.dll"])
        if not mp: return " | no map"
        b = rd(mp + 0xA4, 2) or b"\xff\xff"
        return " | turn player %d, local player %d, combat %s" % (struct.unpack("b", b[:1])[0], struct.unpack("b", b[1:2])[0],
                                                                 "yes" if u32(mp + 0x120) else "no")

    if not k32.DebugActiveProcess(pid):
        print("pid %d: DebugActiveProcess failed (%d) - run this from an elevated prompt" % (pid, ctypes.get_last_error())); return 1
    k32.DebugSetProcessKillOnExit(False)
    bps = {}
    for mod, va, label, extra in POINTS:
        if mod not in base: continue
        a = va - PREF[mod] + base[mod]
        orig = rd(a, 1)
        if orig and orig != b"\xCC" and wr(a, b"\xCC"):
            bps[a] = (orig, label, extra)
    log("===== tracer attached to pid %d, %d of %d breakpoints, bases %s%s" % (
        pid, len(bps), len(POINTS), {k: hex(v) for k, v in base.items() if k in PREF}, state()))
    ev = DBGEV(); rearm = {}; ctx = ctypes.create_string_buffer(716); alive = True
    try:
        while time.time() < t_end and alive:
            if not k32.WaitForDebugEvent(ctypes.byref(ev), 500):
                continue
            cont = 0x00010002                        # DBG_CONTINUE
            if ev.dwDebugEventCode == 1:
                code, addr = ev.exc.ExceptionCode, ev.exc.ExceptionAddress or 0
                if code in (0x80000004, 0x4000001E):             # single step: put the breakpoint back
                    if ev.dwThreadId in rearm:
                        wr(rearm.pop(ev.dwThreadId), b"\xCC")
                    else:
                        cont = 0x80010001
                elif code in (0x80000003, 0x4000001F):
                    if addr in bps:
                        orig, label, extra = bps[addr]
                        wr(addr, orig)
                        th = k32.OpenThread(0x1F03FF, False, ev.dwThreadId)
                        struct.pack_into("<I", ctx, 0, 0x10007)
                        if k32.Wow64GetThreadContext(th, ctx):
                            r = dict(zip(("edi", "esi", "ebx", "edx", "ecx", "eax", "ebp", "eip"), struct.unpack_from("<8I", ctx, 0x9C)))
                            esp = struct.unpack_from("<I", ctx, 0xC4)[0]
                            struct.pack_into("<I", ctx, 0xB8, addr)
                            struct.pack_into("<I", ctx, 0xC0, struct.unpack_from("<I", ctx, 0xC0)[0] | 0x100)
                            k32.Wow64SetThreadContext(th, ctx)
                            rearm[ev.dwThreadId] = addr
                            x = ""
                            if extra == "pb":
                                b = rd(r["eax"] + 0x10, 1)
                                x = " | player %d" % struct.unpack("b", b)[0] if b else ""
                            elif extra == "sys":
                                x = " | %#x %s" % (r["eax"], SYSMSG.get(r["eax"], "?"))
                            if not (extra == "sys" and r["eax"] == 0x10D):       # SENDCOMPLETE = 5 lines/s of noise
                              log("%s%s | eax=%08X edx=%08X ecx=%08X ret=%08X%s" % (label, x, r["eax"], r["edx"], r["ecx"], u32(esp), state()))
                        k32.CloseHandle(th)
                else:
                    if code >= 0xC0000000:
                        log("EXCEPTION %08X at %08X (first chance)" % (code, addr))
                    cont = 0x80010001                # not ours -> the game's own handlers
            elif ev.dwDebugEventCode == 5:
                log("===== game process exited"); alive = False
            k32.ContinueDebugEvent(ev.dwProcessId, ev.dwThreadId, cont)
    except KeyboardInterrupt:
        pass
    finally:
        if alive:
            for a, (orig, _l, _e) in bps.items():
                wr(a, orig)
            log("===== tracer detached")
        k32.DebugActiveProcessStop(pid)
    return 0


def main():
    if len(sys.argv) > 2 and sys.argv[1] == "--pid":
        return worker(int(sys.argv[2]), float(sys.argv[3]) if len(sys.argv) > 3 else 180)
    mins = float(sys.argv[1]) if len(sys.argv) > 1 else 180
    print("waiting for AoWx.exe instances (Ctrl+C to stop; logs in %s)" % os.path.join(GAME, "X")); sys.stdout.flush()
    t_end, seen, procs = time.time() + mins * 60, set(), []
    try:
        while time.time() < t_end:                   # attach to every instance, including ones started later
            for p in pids():
                if p not in seen:
                    seen.add(p)
                    print("new game instance pid %d" % p); sys.stdout.flush()
                    left = max(1.0, (t_end - time.time()) / 60)
                    procs.append(subprocess.Popen([sys.executable, os.path.abspath(__file__), "--pid", str(p), str(left)]))
            time.sleep(2)
    except KeyboardInterrupt:
        pass
    for p in procs:
        try: p.wait(15)
        except Exception: pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
