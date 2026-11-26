"""Live probe for Tame Animal (0xC9) / Dominate (v2, 2026-10-19).  Attaches to the running AoWx.exe as a debugger,
arms 4 hardware EXECUTE breakpoints on EVERY thread on the REAL tactical touch path, logs every pass plus every
first-chance exception, and never kills the game.

v1 was broken: a 64-bit Python reading the debug event with the 32-bit DEBUG_EVENT layout (union at +12 instead
of +16) misread every exception, and WOW64 reports hardware breakpoints as STATUS_WX86_SINGLE_STEP 0x4000001E,
which v1 did not recognise - so its own breakpoint hits were passed to the game as unhandled exceptions (the
'error during token exe strike' seen when casting Dominate) and nothing was logged.

  SW    AoWTCPCK 0x40A5F4  touch TE id switch (v3 hook site):  [eax+0x3C] = ability id  (0x1C/0x1D/0x94/(v3) 0xC9 -> command case)
  CA    AoWEPACK 0x55770358 TCommandAbility +0x128 (create TCommandCA, rolls +0x110):  eax = ability, ecx = target CU
  ROLL  AoWEPACK 0x557681F8 TTouchAbility.Roll after GetAttack:  esi = ATK, bl = to-hit result
  SIDE  AoWEPACK 0x5576FEC2 TCommandAbility.Apply about to switch the target's side:  esi = target CU, dl = new side

Usage (game running, in combat, BEFORE casting):  py -3.10 diag_tame_probe.py [--seconds 600]
Cast Tame Animal a few times (and Dominate once).  Stop: Ctrl+C or create patch scripts\\tame_probe.stop.
Log: patch scripts\\tame_probe_log.txt  (run elevated if the attach fails)."""
import ctypes as C, ctypes.wintypes as W, struct, sys, time, os, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(HERE, "tame_probe_log.txt"); STOP = os.path.join(HERE, "tame_probe.stop")
SECS = int(sys.argv[sys.argv.index("--seconds") + 1]) if "--seconds" in sys.argv else 600
BPS = [("aowtcpck.dll", 0x400000, 0x0040A5F4, "SW"), ("aowepack.dll", 0x55700000, 0x55770358, "CA"),
       ("aowepack.dll", 0x55700000, 0x557681F8, "ROLL"), ("aowepack.dll", 0x55700000, 0x5576FEC2, "SIDE")]
SINGLE_STEP = (0x80000004, 0x4000001E)          # native / WOW64 (STATUS_WX86_SINGLE_STEP)
BREAKPOINT = (0x80000003, 0x4000001F)           # native / WOW64 (STATUS_WX86_BREAKPOINT)
DBG_CONTINUE, DBG_NOT_HANDLED = 0x00010002, 0x80010001
PTR = C.sizeof(C.c_void_p)
k32 = C.WinDLL("kernel32", use_last_error=True); psapi = C.WinDLL("psapi", use_last_error=True); vp = C.c_void_p
k32.WaitForDebugEvent.argtypes = [vp, W.DWORD]; k32.ContinueDebugEvent.argtypes = [W.DWORD, W.DWORD, W.DWORD]
k32.OpenProcess.restype = vp; k32.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
k32.OpenThread.restype = vp; k32.OpenThread.argtypes = [W.DWORD, W.BOOL, W.DWORD]
k32.ReadProcessMemory.argtypes = [vp, vp, vp, C.c_size_t, C.POINTER(C.c_size_t)]
k32.CloseHandle.argtypes = [vp]; k32.CreateToolhelp32Snapshot.restype = vp
k32.SuspendThread.argtypes = [vp]; k32.ResumeThread.argtypes = [vp]
k32.Thread32First.argtypes = [vp, vp]; k32.Thread32Next.argtypes = [vp, vp]
psapi.EnumProcessModulesEx.argtypes = [vp, vp, W.DWORD, C.POINTER(W.DWORD), W.DWORD]
psapi.GetModuleBaseNameW.argtypes = [vp, vp, W.LPWSTR, W.DWORD]; psapi.GetModuleInformation.argtypes = [vp, vp, vp, W.DWORD]
if PTR == 8:
    k32.Wow64GetThreadContext.argtypes = [vp, vp]; k32.Wow64SetThreadContext.argtypes = [vp, vp]
    GETCTX, SETCTX = k32.Wow64GetThreadContext, k32.Wow64SetThreadContext
    U_OFF = 16                                   # DEBUG_EVENT union is 8-aligned on x64
else:
    k32.GetThreadContext.argtypes = [vp, vp]; k32.SetThreadContext.argtypes = [vp, vp]
    GETCTX, SETCTX = k32.GetThreadContext, k32.SetThreadContext
    U_OFF = 12


class MODULEINFO(C.Structure): _fields_ = [("lpBaseOfDll", vp), ("SizeOfImage", W.DWORD), ("EntryPoint", vp)]
class THREADENTRY32(C.Structure):
    _fields_ = [("dwSize", W.DWORD), ("cntUsage", W.DWORD), ("th32ThreadID", W.DWORD), ("th32OwnerProcessID", W.DWORD),
                ("tpBasePri", W.LONG), ("tpDeltaPri", W.LONG), ("dwFlags", W.DWORD)]


def log(m):
    line = time.strftime("%H:%M:%S ") + m; print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f: f.write(line + "\n")
def rpm(hp, a, n):
    b = C.create_string_buffer(n); r = C.c_size_t()
    return b.raw[:r.value] if k32.ReadProcessMemory(hp, a, b, n, C.byref(r)) else b""
def u32(hp, a):
    b = rpm(hp, a, 4); return struct.unpack("<I", b)[0] if len(b) == 4 else None
def u8(hp, a):
    b = rpm(hp, a, 1); return b[0] if b else None
def modules(hp):
    arr = (vp * 1024)(); need = W.DWORD(); psapi.EnumProcessModulesEx(hp, arr, C.sizeof(arr), C.byref(need), 0x03); out = []
    for i in range(need.value // PTR):
        b = arr[i]
        if not b or b >= 1 << 32: continue
        nm = C.create_unicode_buffer(260); psapi.GetModuleBaseNameW(hp, b, nm, 260); mi = MODULEINFO()
        psapi.GetModuleInformation(hp, b, C.byref(mi), C.sizeof(mi)); out.append((b, mi.SizeOfImage, nm.value))
    return sorted(out)
def sym(mods, a):
    for b, s, n in mods:
        if b <= a < b + s: return "%s+0x%X" % (n, a - b)
    return hex(a)
def clsname(hp, obj):
    vmt = u32(hp, obj) if obj else None
    p = u32(hp, vmt - 0x20) if vmt else None          # this Delphi build: vmtClassName = -0x20 (checked on TDominateAbility)
    if not p: return "?"
    n = u8(hp, p) or 0
    return rpm(hp, p + 1, min(n, 63)).decode("latin1", "replace")
def s32(v):
    return v - (1 << 32) if v >= 0x80000000 else v


pid = None
out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq AoWx.exe", "/FO", "CSV", "/NH"], capture_output=True, text=True).stdout
for line in out.splitlines():
    if line.lower().startswith('"aowx.exe"'):
        pid = int(line.split('","')[1]); break
if not pid:
    print("AoWx.exe is not running"); sys.exit(1)
hp = k32.OpenProcess(0x1FFFFF, False, pid)
mods = modules(hp); base_of = {n.lower(): b for b, s, n in mods}
ADDRS = []
for mod, pref, va, nm in BPS:
    if mod not in base_of:
        print("%s not loaded" % mod); sys.exit(1)
    ADDRS.append(((va - pref + base_of[mod]) & 0xFFFFFFFF, nm))


def arm(tid, on=True, suspend=False):
    ht = k32.OpenThread(0x1FFFFF, False, tid)
    if not ht: return False
    if suspend: k32.SuspendThread(ht)
    ctx = C.create_string_buffer(716); struct.pack_into("<I", ctx, 0, 0x10010)          # CONTEXT_i386 | DEBUG_REGISTERS
    ok = False
    if GETCTX(ht, ctx):
        for k, (a, _) in enumerate(ADDRS): struct.pack_into("<I", ctx, 4 + 4 * k, a if on else 0)
        struct.pack_into("<I", ctx, 0x14, 0)                                             # Dr6
        struct.pack_into("<I", ctx, 0x18, 0x55 if on else 0)                             # Dr7: L0..L3, execute, len 1
        ok = bool(SETCTX(ht, ctx))
    if suspend: k32.ResumeThread(ht)
    k32.CloseHandle(ht); return ok


def all_threads():
    snap = k32.CreateToolhelp32Snapshot(0x4, 0); te = THREADENTRY32(); te.dwSize = C.sizeof(te); out = []
    if k32.Thread32First(snap, C.byref(te)):
        while True:
            if te.th32OwnerProcessID == pid: out.append(te.th32ThreadID)
            if not k32.Thread32Next(snap, C.byref(te)): break
    k32.CloseHandle(snap); return out


def describe(hp, nm, r):
    eax, ebx, ecx, edx, esi, edi = r["eax"], r["ebx"], r["ecx"], r["edx"], r["esi"], r["edi"]
    if nm == "SW":
        ident = u32(hp, eax + 0x3C) or 0
        route = "command case" if ident in (0x1C, 0x1D, 0x94) else ("command case only with v3" if ident == 0xC9 else "other/default")
        return "SW    touch TE id=0x%X (%s) TE=%08X [%s]" % (ident, route, eax, clsname(hp, eax))
    if nm == "CA":
        return "CA    ability +0x128 id=0x%X grants=0x%X target CU=%08X [%s]" % (u32(hp, eax + 0xC) or 0, u32(hp, eax + 0x28) or 0, ecx, clsname(hp, ecx))
    if nm == "ROLL":
        return "ROLL  ATK(esi)=%d to-hit(bl)=%d attacker CU=%08X" % (s32(esi), ebx & 0xFF, edi)
    return "SIDE  target CU=%08X new side=%d status obj=%08X id=0x%X" % (esi, edx & 0xFF, edi, u32(hp, edi + 0xC) or 0)


if not k32.DebugActiveProcess(pid):
    log("DebugActiveProcess failed %d (run elevated?)" % C.get_last_error()); sys.exit(1)
k32.DebugSetProcessKillOnExit(False)
log("attached pid=%d; %s; %ds" % (pid, ", ".join("%s@%08X" % (nm, a) for a, nm in ADDRS), SECS))
armed = set(); t0 = time.time(); ev = C.create_string_buffer(256); nexc = 0; first = True
try:
    while time.time() - t0 < SECS and not os.path.exists(STOP):
        if not k32.WaitForDebugEvent(ev, 500): continue
        code, epid, etid = struct.unpack_from("<III", ev, 0); status = DBG_CONTINUE
        if first:                                               # the process is frozen while we hold an event
            for tid in all_threads():
                if arm(tid): armed.add(tid)
            log("armed %d threads" % len(armed)); first = False
        if code == 2:                                           # CREATE_THREAD
            if arm(etid): armed.add(etid)
        elif code == 5:
            log("process exited"); k32.ContinueDebugEvent(epid, etid, status); break
        elif code == 1:
            u = U_OFF
            if PTR == 8:
                xc, xf, _rec, xaddr, npar = struct.unpack_from("<IIQQI", ev, u); info = struct.unpack_from("<15Q", ev, u + 32)
                firstchance = struct.unpack_from("<I", ev, u + 152)[0]
            else:
                xc, xf, _rec, xaddr, npar = struct.unpack_from("<IIIII", ev, u); info = struct.unpack_from("<15I", ev, u + 20)
                firstchance = struct.unpack_from("<I", ev, u + 80)[0]
            if xc in SINGLE_STEP:
                ht = k32.OpenThread(0x1FFFFF, False, etid); ctx = C.create_string_buffer(716); struct.pack_into("<I", ctx, 0, 0x10017)
                GETCTX(ht, ctx)
                edi, esi, ebx, edx, ecx, eax, ebp, eip, _cs, fl, esp = struct.unpack_from("<11I", ctx, 0x9C)
                hit = [n for a, n in ADDRS if a == eip]
                if hit:
                    log(describe(hp, hit[0], dict(eax=eax, ebx=ebx, ecx=ecx, edx=edx, esi=esi, edi=edi)))
                    struct.pack_into("<I", ctx, 0x14, 0)                                 # clear Dr6
                    struct.pack_into("<I", ctx, 0xC0, fl | 0x10000)                      # RF: resume past the breakpoint
                    SETCTX(ht, ctx)
                else:
                    status = DBG_NOT_HANDLED                                              # a genuine single step - not ours
                k32.CloseHandle(ht)
            elif xc in BREAKPOINT:
                pass                                                                     # attach break-in: swallow
            else:
                status = DBG_NOT_HANDLED                                                  # real exception -> the game's handlers
                if firstchance and nexc < 400:
                    nexc += 1; extra = ""
                    if xc == 0x0EEDFADE and npar >= 2:                                    # Delphi: [0] raise addr, [1] object
                        obj = info[1] & 0xFFFFFFFF; msgp = u32(hp, obj + 4)
                        ln = (u32(hp, msgp - 4) or 0) if msgp else 0
                        msg = rpm(hp, msgp, min(ln, 200)).decode("latin1", "replace") if msgp else ""
                        extra = " Delphi %s '%s' raised at %s" % (clsname(hp, obj), msg, sym(mods, info[0] & 0xFFFFFFFF))
                    elif xc == 0xC0000005 and npar >= 2:
                        extra = " AV %s of 0x%08X" % ("write" if info[0] else "read", info[1] & 0xFFFFFFFF)
                    log("EXCEPTION 0x%08X at %s%s" % (xc, sym(mods, xaddr & 0xFFFFFFFF), extra))
        k32.ContinueDebugEvent(epid, etid, status)
except KeyboardInterrupt:
    pass
for tid in set(armed) | set(all_threads()): arm(tid, False, suspend=True)   # no debug event held here
k32.DebugActiveProcessStop(pid)
log("detached")
