"""Hardware WRITE watchpoint on one dword in the running 32-bit game (WOW64), via debugger
attach.  Logs eip/regs/stack for every write to the address, continues, never kills the game.
Usage: py diag_hwbp.py <pid> <hex address> [--seconds N] [--log path]
Stops after N seconds (default 300) or when <log dir>\\hwbp.stop exists; detaches cleanly."""
import ctypes as C, ctypes.wintypes as W, struct, sys, time, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

pid = int(sys.argv[1]); ADDR = int(sys.argv[2], 16)
SECS = int(sys.argv[sys.argv.index("--seconds") + 1]) if "--seconds" in sys.argv else 300
HERE = os.path.dirname(os.path.abspath(__file__))
LOG = sys.argv[sys.argv.index("--log") + 1] if "--log" in sys.argv else os.path.join(HERE, "hwbp_log.txt")
STOP = os.path.join(HERE, "hwbp.stop")
k32 = C.WinDLL("kernel32", use_last_error=True); psapi = C.WinDLL("psapi", use_last_error=True); vp = C.c_void_p


def log(m):
    line = time.strftime("%H:%M:%S ") + m; print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f: f.write(line + "\n")


class EXCEPTION_RECORD(C.Structure):
    _fields_ = [("ExceptionCode", W.DWORD), ("ExceptionFlags", W.DWORD), ("ExceptionRecord", vp), ("ExceptionAddress", vp), ("NumberParameters", W.DWORD), ("ExceptionInformation", C.c_ulonglong * 15)]
class EXCEPTION_DEBUG_INFO(C.Structure):
    _fields_ = [("ExceptionRecord", EXCEPTION_RECORD), ("dwFirstChance", W.DWORD)]
class DEBUG_EVENT(C.Structure):
    _fields_ = [("dwDebugEventCode", W.DWORD), ("dwProcessId", W.DWORD), ("dwThreadId", W.DWORD), ("u", C.c_byte * 160)]
class MODULEINFO(C.Structure): _fields_ = [("lpBaseOfDll", vp), ("SizeOfImage", W.DWORD), ("EntryPoint", vp)]
k32.WaitForDebugEvent.argtypes = [C.POINTER(DEBUG_EVENT), W.DWORD]; k32.ContinueDebugEvent.argtypes = [W.DWORD, W.DWORD, W.DWORD]
k32.OpenProcess.restype = vp; k32.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
k32.OpenThread.restype = vp; k32.OpenThread.argtypes = [W.DWORD, W.BOOL, W.DWORD]
k32.ReadProcessMemory.argtypes = [vp, vp, vp, C.c_size_t, C.POINTER(C.c_size_t)]
k32.Wow64GetThreadContext.argtypes = [vp, vp]; k32.Wow64SetThreadContext.argtypes = [vp, vp]
psapi.EnumProcessModulesEx.argtypes = [vp, vp, W.DWORD, C.POINTER(W.DWORD), W.DWORD]; psapi.GetModuleBaseNameW.argtypes = [vp, vp, W.LPWSTR, W.DWORD]; psapi.GetModuleInformation.argtypes = [vp, vp, vp, W.DWORD]


def rpm(hp, a, n):
    b = C.create_string_buffer(n); r = C.c_size_t(); return b.raw[:r.value] if k32.ReadProcessMemory(hp, a, b, n, C.byref(r)) else b""
def modules(hp):
    arr = (vp * 1024)(); need = W.DWORD(); psapi.EnumProcessModulesEx(hp, arr, C.sizeof(arr), C.byref(need), 0x03); out = []
    for i in range(need.value // C.sizeof(vp)):
        b = arr[i]
        if not b or b >= 1 << 32: continue
        nm = C.create_unicode_buffer(260); psapi.GetModuleBaseNameW(hp, b, nm, 260); mi = MODULEINFO(); psapi.GetModuleInformation(hp, b, C.byref(mi), C.sizeof(mi)); out.append((b, mi.SizeOfImage, nm.value))
    return sorted(out)
def sym(mods, a):
    for b, s, n in mods:
        if b <= a < b + s: return f"{n}+0x{a-b:X}"
    return None


def arm(tid):
    ht = k32.OpenThread(0x1FFFFF, False, tid)
    if not ht: return False
    ctx = C.create_string_buffer(716); struct.pack_into("<I", ctx, 0, 0x10010)      # CONTEXT_i386 | DEBUG_REGISTERS
    if not k32.Wow64GetThreadContext(ht, ctx): k32.CloseHandle(ht); return False
    struct.pack_into("<I", ctx, 4, ADDR)                                             # Dr0
    struct.pack_into("<I", ctx, 0x18, 0x000D0001)                                    # Dr7: L0, RW0=write, LEN0=4
    ok = k32.Wow64SetThreadContext(ht, ctx); k32.CloseHandle(ht); return bool(ok)


hp = k32.OpenProcess(0x1FFFFF, False, pid)
if not k32.DebugActiveProcess(pid): log(f"DebugActiveProcess failed {C.get_last_error()}"); sys.exit(1)
k32.DebugSetProcessKillOnExit(False)
log(f"attached pid={pid}, write-watch on 0x{ADDR:08X} for {SECS}s")
mods = modules(hp); armed = set(); t0 = time.time(); ev = DEBUG_EVENT(); hits = 0
while time.time() - t0 < SECS and not os.path.exists(STOP):
    if not k32.WaitForDebugEvent(C.byref(ev), 500):
        continue
    code = ev.dwDebugEventCode; status = 0x00010002
    if code in (2, 3):                      # CREATE_THREAD / CREATE_PROCESS: arm the thread
        if arm(ev.dwThreadId): armed.add(ev.dwThreadId)
    elif code == 5:
        log("process exited"); k32.ContinueDebugEvent(ev.dwProcessId, ev.dwThreadId, status); break
    elif code == 1:
        info = EXCEPTION_DEBUG_INFO.from_buffer_copy(bytes(ev.u)); xc = info.ExceptionRecord.ExceptionCode
        if xc == 0x80000004:                # single step = our watchpoint
            hits += 1
            ht = k32.OpenThread(0x1FFFFF, False, ev.dwThreadId); ctx = C.create_string_buffer(716); struct.pack_into("<I", ctx, 0, 0x10007)
            k32.Wow64GetThreadContext(ht, ctx)
            edi, esi, ebx, edx, ecx, eax, ebp, eip, _cs, _fl, esp = struct.unpack_from("<11I", ctx, 0x9C)
            if not sym(mods, eip): mods = modules(hp)
            val = struct.unpack("<I", rpm(hp, ADDR, 4) or b"\0\0\0\0")[0]
            log(f"--- WRITE #{hits} by eip={sym(mods, eip) or hex(eip)} new value=0x{val:08X} eax={eax:08X} edx={edx:08X} ecx={ecx:08X} esi={esi:08X} edi={edi:08X} ebx={ebx:08X}")
            stk = rpm(hp, esp, 0x400); n = 0
            for i in range(0, len(stk) - 4, 4):
                v = struct.unpack_from("<I", stk, i)[0]; s = sym(mods, v)
                if s and not s.startswith(("ntdll", "KERNEL", "kernel", "USER32", "user32", "GDI32", "win32u")):
                    pre = rpm(hp, v - 6, 6)
                    if len(pre) == 6 and (pre[1] == 0xE8 or pre[0] == 0xE8 or 0xFF in (pre[0], pre[1], pre[3], pre[4])): log(f"      [esp+0x{i:03X}] {s}"); n += 1
                if n >= 12: break
            k32.CloseHandle(ht)
        elif xc in (0x80000003, 0x4000001F):
            pass                            # attach breakpoint
        else:
            status = 0x80010001             # not ours: let the game handle it
    k32.ContinueDebugEvent(ev.dwProcessId, ev.dwThreadId, status)
# disarm and detach
for tid in armed:
    ht = k32.OpenThread(0x1FFFFF, False, tid)
    if ht:
        ctx = C.create_string_buffer(716); struct.pack_into("<I", ctx, 0, 0x10010)
        if k32.Wow64GetThreadContext(ht, ctx):
            struct.pack_into("<I", ctx, 0x18, 0); k32.Wow64SetThreadContext(ht, ctx)
        k32.CloseHandle(ht)
k32.DebugActiveProcessStop(pid)
log(f"detached; {hits} writes logged")
