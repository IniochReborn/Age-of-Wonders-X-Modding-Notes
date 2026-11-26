"""Attach to a running 32-bit game process as a debugger (no elevation needed when the
game runs unelevated) and log every exception event the kernel delivers - this works even
when an in-process VEH cannot run (corrupted stack pointer, faults during dispatch).
Usage: py diag_debug_attach.py <pid> [--log path]
On a non-breakpoint exception: logs code/address, Wow64 thread context, stack return
addresses symbolised against the live module list; continues NOT_HANDLED so the game's own
handling proceeds; on the second chance the process is terminated after logging."""
import ctypes as C, ctypes.wintypes as W, struct, sys, time, os
pid = int(sys.argv[1]); LOG = sys.argv[sys.argv.index("--log") + 1] if "--log" in sys.argv else os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug_attach_log.txt")
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
k32.WaitForDebugEvent.argtypes = [C.POINTER(DEBUG_EVENT), W.DWORD]; k32.ContinueDebugEvent.argtypes = [W.DWORD, W.DWORD, W.DWORD]
k32.OpenProcess.restype = vp; k32.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
k32.OpenThread.restype = vp; k32.OpenThread.argtypes = [W.DWORD, W.BOOL, W.DWORD]
k32.ReadProcessMemory.argtypes = [vp, vp, vp, C.c_size_t, C.POINTER(C.c_size_t)]
k32.Wow64GetThreadContext.argtypes = [vp, vp]; k32.TerminateProcess.argtypes = [vp, W.UINT]
psapi.EnumProcessModulesEx.argtypes = [vp, vp, W.DWORD, C.POINTER(W.DWORD), W.DWORD]; psapi.GetModuleBaseNameW.argtypes = [vp, vp, W.LPWSTR, W.DWORD]; psapi.GetModuleInformation.argtypes = [vp, vp, vp, W.DWORD]
class MODULEINFO(C.Structure): _fields_ = [("lpBaseOfDll", vp), ("SizeOfImage", W.DWORD), ("EntryPoint", vp)]
def rpm(hp, a, n):
    b = C.create_string_buffer(n); r = C.c_size_t(); return b.raw[:r.value] if k32.ReadProcessMemory(hp, a, b, n, C.byref(r)) else b""
def modules(hp):
    arr = (vp * 1024)(); need = W.DWORD(); psapi.EnumProcessModulesEx(hp, arr, C.sizeof(arr), C.byref(need), 0x03); out = []
    for i in range(need.value // C.sizeof(vp)):
        b = arr[i]
        if not b: continue
        nm = C.create_unicode_buffer(260); psapi.GetModuleBaseNameW(hp, b, nm, 260); mi = MODULEINFO(); psapi.GetModuleInformation(hp, b, C.byref(mi), C.sizeof(mi)); out.append((b & 0xFFFFFFFF, mi.SizeOfImage, nm.value))
    return sorted(out)
def sym(mods, a):
    for b, s, n in mods:
        if b <= a < b + s: return f"{n}+0x{a-b:X}"
    return None
hp = k32.OpenProcess(0x1FFFFF, False, pid)
if not k32.DebugActiveProcess(pid): log(f"DebugActiveProcess failed {C.get_last_error()}"); sys.exit(1)
k32.DebugSetProcessKillOnExit(False); log(f"attached to pid {pid}")
ev = DEBUG_EVENT(); mods = modules(hp); seen_bp = False
while True:
    if not k32.WaitForDebugEvent(C.byref(ev), 0xFFFFFFFF): log(f"WaitForDebugEvent failed {C.get_last_error()}"); break
    code, status = ev.dwDebugEventCode, 0x00010002   # DBG_CONTINUE
    if code == 5: log("process exited"); k32.ContinueDebugEvent(ev.dwProcessId, ev.dwThreadId, status); break
    if code == 1:
        info = EXCEPTION_DEBUG_INFO.from_buffer_copy(bytes(ev.u)); rec = info.ExceptionRecord; xc = rec.ExceptionCode; xa = (rec.ExceptionAddress or 0) & 0xFFFFFFFF
        if xc in (0x80000003, 0x4000001F) and not seen_bp: seen_bp = True   # attach breakpoint
        elif xc not in (0x406D1388,):
            if not mods or xc != 0x0EEDFADE: mods = modules(hp)
            ht = k32.OpenThread(0x1FFFFF, False, ev.dwThreadId); ctx = C.create_string_buffer(716); struct.pack_into("<I", ctx, 0, 0x10007)
            ok = k32.Wow64GetThreadContext(ht, ctx)
            edi, esi, ebx, edx, ecx, eax, ebp, eip, _cs, _fl, esp = struct.unpack_from("<11I", ctx, 0x9C)
            log(f"--- exception code=0x{xc:08X} first={info.dwFirstChance} addr={sym(mods, xa) or hex(xa)} tid={ev.dwThreadId} ctx_ok={ok}")
            log(f"    eip={sym(mods, eip) or hex(eip)} esp={esp:08X} ebp={ebp:08X} eax={eax:08X} ebx={ebx:08X} ecx={ecx:08X} edx={edx:08X} esi={esi:08X} edi={edi:08X}")
            if xc == 0xC0000005 and rec.NumberParameters >= 2: log(f"    AV {'write' if rec.ExceptionInformation[0] == 1 else 'read'} at 0x{rec.ExceptionInformation[1] & 0xFFFFFFFF:08X}")
            stk = rpm(hp, esp, 0x800); n = 0
            for i in range(0, len(stk) - 4, 4):
                v = struct.unpack_from("<I", stk, i)[0]; s = sym(mods, v)
                if s and not s.startswith(("ntdll", "KERNEL", "kernel", "USER32", "user32", "GDI32", "win32u", "IME", "MSCTF", "ddraw", "DDRAW")):
                    pre = rpm(hp, v - 6, 6)
                    if len(pre) == 6 and (pre[1] == 0xE8 or pre[0] == 0xE8 or 0xFF in (pre[0], pre[1], pre[3], pre[4])): log(f"      [esp+0x{i:03X}] {s}"); n += 1
                if n >= 24: break
            k32.CloseHandle(ht)
            if xc != 0x0EEDFADE: status = 0x80010001   # DBG_EXCEPTION_NOT_HANDLED -> let the game handle it / second chance
            if xc == 0xC0000005 and not info.dwFirstChance: log("second chance AV - terminating"); k32.TerminateProcess(hp, 1)
        else:
            status = 0x80010001
    k32.ContinueDebugEvent(ev.dwProcessId, ev.dwThreadId, status)
