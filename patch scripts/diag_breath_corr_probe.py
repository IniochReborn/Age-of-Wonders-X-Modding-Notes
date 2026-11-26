"""Live probe for breath animations (patch_breath_anim_v4, 2026-10-19).  Attaches to the running AoWx.exe as a debugger,
arms 4 hardware EXECUTE breakpoints in AoWTCPCK.dll (rebase-aware; addresses read from the v4 zone header +0x10) and
logs, per breath, the corridor decision and, PER STRIKE, which flight path the strike got.  Read-only; never kills the game.

  FAN   fan-cave entry (every category-5 strike, after the block loop):  [ebp-4] te, [te+0x34] s, latch G (te, s)
  DONE  CORR c_done (strike 0):  [ebp-4] sx, [ebp-8] sy, [ebp-0xC] D, [ebp-0x2C] blocked cone entries (bit i = entry i),
        [ebp-0x34] required flank mask, [ebp-0x38] chosen centre entry; flag [0x46BF3C] (bit 0 corridor, byte1/2 = T)
  STR   f_str: this strike is re-pathed STRAIGHT to T (eax = flag)
  MRP   f_mrp: this strike is re-pathed on the vanilla FAN line (v1)
  A strike with FAN but neither STR nor MRP kept its original path (strikes 12..19 of a fan breath = vanilla sweep;
  'latch miss' = the save cave did not run for it).

Usage (game running, in combat, BEFORE the breath):  py -3.10 diag_breath_corr_probe.py [--seconds 600]
Then breathe down a 1-hex corridor (and once in the open).  Stop with Ctrl+C or by creating patch scripts\\breath_probe.stop.
Log: patch scripts\\breath_probe_log.txt.  (Run elevated if attaching fails.)"""
import ctypes as C, ctypes.wintypes as W, struct, sys, time, os, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(HERE, "breath_probe_log.txt"); STOP = os.path.join(HERE, "breath_probe.stop")
SECS = int(sys.argv[sys.argv.index("--seconds") + 1]) if "--seconds" in sys.argv else 600
PREF = 0x400000
CORR, ZONE, ZONE_END = 0x451400, 0x451000, 0x451800
C_TE, C_FLAG = 0x46BF38, 0x46BF3C
DONE_PAT = bytes.fromhex("8b83") + struct.pack("<I", C_FLAG) + bytes.fromhex("89ec5f5e5dc3")
k32 = C.WinDLL("kernel32", use_last_error=True); psapi = C.WinDLL("psapi", use_last_error=True); vp = C.c_void_p


def log(m):
    line = time.strftime("%H:%M:%S ") + m; print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f: f.write(line + "\n")


class EXCEPTION_RECORD(C.Structure):
    _fields_ = [("ExceptionCode", W.DWORD), ("ExceptionFlags", W.DWORD), ("ExceptionRecord", vp), ("ExceptionAddress", vp),
                ("NumberParameters", W.DWORD), ("ExceptionInformation", C.c_ulonglong * 15)]
class EXCEPTION_DEBUG_INFO(C.Structure):
    _fields_ = [("ExceptionRecord", EXCEPTION_RECORD), ("dwFirstChance", W.DWORD)]
class DEBUG_EVENT(C.Structure):
    _fields_ = [("dwDebugEventCode", W.DWORD), ("dwProcessId", W.DWORD), ("dwThreadId", W.DWORD), ("u", C.c_byte * 160)]
class MODULEINFO(C.Structure): _fields_ = [("lpBaseOfDll", vp), ("SizeOfImage", W.DWORD), ("EntryPoint", vp)]
k32.WaitForDebugEvent.argtypes = [C.POINTER(DEBUG_EVENT), W.DWORD]; k32.ContinueDebugEvent.argtypes = [W.DWORD, W.DWORD, W.DWORD]
k32.OpenProcess.restype = vp; k32.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
k32.OpenThread.restype = vp; k32.OpenThread.argtypes = [W.DWORD, W.BOOL, W.DWORD]
k32.ReadProcessMemory.argtypes = [vp, vp, vp, C.c_size_t, C.POINTER(C.c_size_t)]
k32.Wow64GetThreadContext.argtypes = [vp, vp]; k32.Wow64SetThreadContext.argtypes = [vp, vp]; k32.CloseHandle.argtypes = [vp]
psapi.EnumProcessModulesEx.argtypes = [vp, vp, W.DWORD, C.POINTER(W.DWORD), W.DWORD]
psapi.GetModuleBaseNameW.argtypes = [vp, vp, W.LPWSTR, W.DWORD]; psapi.GetModuleInformation.argtypes = [vp, vp, vp, W.DWORD]


def rpm(hp, a, n):
    b = C.create_string_buffer(n); r = C.c_size_t()
    return b.raw[:r.value] if k32.ReadProcessMemory(hp, a, b, n, C.byref(r)) else b""
def u32(hp, a):
    b = rpm(hp, a, 4); return struct.unpack("<I", b)[0] if len(b) == 4 else None
def s32(v):
    return None if v is None else (v - (1 << 32) if v >= 0x80000000 else v)
def u16(hp, a):
    b = rpm(hp, a, 2); return struct.unpack("<H", b)[0] if len(b) == 2 else None
def modules(hp):
    arr = (vp * 1024)(); need = W.DWORD(); psapi.EnumProcessModulesEx(hp, arr, C.sizeof(arr), C.byref(need), 0x03); out = []
    for i in range(need.value // C.sizeof(vp)):
        b = arr[i]
        if not b or b >= 1 << 32: continue
        nm = C.create_unicode_buffer(260); psapi.GetModuleBaseNameW(hp, b, nm, 260); mi = MODULEINFO()
        psapi.GetModuleInformation(hp, b, C.byref(mi), C.sizeof(mi)); out.append((b, mi.SizeOfImage, nm.value))
    return sorted(out)


def _decode_v3(mask):
    out = []
    for side, nm in ((0, "L"), (1, "R")):
        hits = []
        for bb in (1, 2, 3):
            a = [aa for aa in (1, 2, 3) if mask >> (side * 9 + (bb - 1) * 3 + aa - 1) & 1]
            hits.append("b%d:%s" % (bb, ("a%d" % a[0]) if a else "-"))
        out.append(nm + "[" + " ".join(hits) + "]")
    return " ".join(out)


pid = None
out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq AoWx.exe", "/FO", "CSV", "/NH"], capture_output=True, text=True).stdout
for line in out.splitlines():
    if line.lower().startswith('"aowx.exe"'):
        pid = int(line.split('","')[1]); break
if not pid:
    print("AoWx.exe is not running"); sys.exit(1)
hp = k32.OpenProcess(0x1FFFFF, False, pid)
mods = modules(hp); tc = [m for m in mods if m[2].lower() == "aowtcpck.dll"]
if not tc:
    print("AoWTCPCK.dll not loaded"); sys.exit(1)
delta = tc[0][0] - PREF
zone = rpm(hp, ZONE + delta, ZONE_END - ZONE)
if zone[:4] != b"BAN4":
    print("breath-anim v4 is not applied in the running game (zone header %r)" % zone[:4]); sys.exit(1)
o_fan, o_str, o_mrp, o_done = struct.unpack_from("<4H", zone, 0x10)
if zone[o_done:o_done + len(DONE_PAT)] != DONE_PAT:
    print("zone header label offsets look wrong (c_done pattern mismatch)"); sys.exit(1)
ADDRS = [((ZONE + o + delta) & 0xFFFFFFFF, n) for o, n in ((o_fan, "FAN"), (o_done, "DONE"), (o_str, "STR"), (o_mrp, "MRP"))]
G = 0x46BF20


def arm(tid, on=True):
    ht = k32.OpenThread(0x1FFFFF, False, tid)
    if not ht: return False
    ctx = C.create_string_buffer(716); struct.pack_into("<I", ctx, 0, 0x10010)
    if not k32.Wow64GetThreadContext(ht, ctx):
        k32.CloseHandle(ht); return False
    for i, (a, _) in enumerate(ADDRS): struct.pack_into("<I", ctx, 4 + 4 * i, a if on else 0)
    struct.pack_into("<I", ctx, 0x18, 0x55 if on else 0)                              # L0..L3, execute, len 1
    ok = k32.Wow64SetThreadContext(ht, ctx); k32.CloseHandle(ht); return bool(ok)


if not k32.DebugActiveProcess(pid):
    log("DebugActiveProcess failed %d (run elevated?)" % C.get_last_error()); sys.exit(1)
k32.DebugSetProcessKillOnExit(False)
log("attached pid=%d; AoWTCPCK at 0x%08X; fan 0x%08X c_done 0x%08X f_str 0x%08X f_mrp 0x%08X; %ds"
    % ((pid, tc[0][0]) + tuple(a for a, _ in ADDRS) + (SECS,)))
cur = {}


def flush():
    if cur:
        log("    s=%02d  %s" % (cur["s"], cur.get("path") or ("kept original path" if cur["latch"] else "kept original path (latch miss)")))
        cur.clear()

armed = set(); t0 = time.time(); ev = DEBUG_EVENT()
try:
    while time.time() - t0 < SECS and not os.path.exists(STOP):
        if not k32.WaitForDebugEvent(C.byref(ev), 500): continue
        code = ev.dwDebugEventCode; status = 0x00010002
        if code in (2, 3):
            if arm(ev.dwThreadId): armed.add(ev.dwThreadId)
        elif code == 5:
            log("process exited"); k32.ContinueDebugEvent(ev.dwProcessId, ev.dwThreadId, status); break
        elif code == 1:
            info = EXCEPTION_DEBUG_INFO.from_buffer_copy(bytes(ev.u)); xc = info.ExceptionRecord.ExceptionCode
            if xc == 0x80000004:
                ht = k32.OpenThread(0x1FFFFF, False, ev.dwThreadId); ctx = C.create_string_buffer(716); struct.pack_into("<I", ctx, 0, 0x10017)
                k32.Wow64GetThreadContext(ht, ctx)
                edi, esi, ebx, edx, ecx, eax, ebp, eip, _cs, fl, esp = struct.unpack_from("<11I", ctx, 0x9C)
                hit = [n for a, n in ADDRS if a == eip]
                rd = lambda o: s32(u32(hp, (ebp + o) & 0xFFFFFFFF))
                if hit and hit[0] == "FAN":
                    flush()
                    te = u32(hp, (ebp - 4) & 0xFFFFFFFF) or 0
                    sn = s32(u32(hp, te + 0x34)) if te else None
                    if sn == 0:
                        log("BREATH te=%08X spell kind=0x%X id=%d target=(%s,%s)" % (te, u32(hp, te + 0x14) or 0, u32(hp, te + 0x18) or 0,
                                                                                  u16(hp, te + 0x20), u16(hp, te + 0x22)))
                    cur.update(s=sn if sn is not None else -1,
                               latch=(u32(hp, G + delta) == te and s32(u32(hp, G + 4 + delta)) == sn))
                elif hit and hit[0] == "DONE":
                    mask = (u32(hp, (ebp - 0x2C) & 0xFFFFFFFF) or 0); need = (u32(hp, (ebp - 0x34) & 0xFFFFFFFF) or 0)
                    flag = u32(hp, C_FLAG + delta) or 0
                    log("  CORR  shooter=(%s,%s) dir=%s  blocked entries %s  required flanks %s  centre entry %s  -> %s" % (
                        rd(-4), rd(-8), rd(-0xC), [i for i in range(12) if mask >> i & 1], [i for i in range(12) if need >> i & 1],
                        rd(-0x38), ("STRAIGHT to (%d,%d)" % (flag >> 8 & 0xFF, flag >> 16 & 0xFF)) if flag & 1 else "fan"))
                elif hit and hit[0] == "STR":
                    cur["path"] = "STRAIGHT -> (%d,%d)" % (eax >> 8 & 0xFF, eax >> 16 & 0xFF)
                elif hit and hit[0] == "MRP":
                    cur["path"] = "FAN line (v1 re-path)"
                if hit:
                    struct.pack_into("<I", ctx, 0xC0, fl | 0x10000)                  # RF: resume past the breakpoint
                    k32.Wow64SetThreadContext(ht, ctx)
                k32.CloseHandle(ht)
            elif xc in (0x80000003, 0x4000001F):
                pass
            else:
                status = 0x80010001                                                    # not ours: pass to the game
        k32.ContinueDebugEvent(ev.dwProcessId, ev.dwThreadId, status)
except KeyboardInterrupt:
    pass
flush()
for tid in armed: arm(tid, False)
k32.DebugActiveProcessStop(pid)
log("detached")
