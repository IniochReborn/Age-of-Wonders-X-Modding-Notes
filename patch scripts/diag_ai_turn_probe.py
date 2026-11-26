"""Live probe: WHY the AI does (or doesn't) go for exploration sites / item bags (2026-10-20).

Read-only debugger (fixed skeleton of diag_ai_site_probe.py: WOW64 DEBUG_EVENT layout, rebase-aware, never kills the
game, stop file) using SOFTWARE breakpoints (int3 -> restore byte -> single-step -> re-arm) so it can watch many sites.
Every value it prints comes from the engine's own registers at that moment (strengths are the engine's ALL-KINDS
numbers from our caves), so no strength is re-estimated here.

  SCORE   0x5573C633  TAIGroupTargetSelector.Score tail: one line per candidate target a group considered:
                      target hex, answer priority, path cost, final score, the group's committed target/mode.
  SITEIN  0x55814AC2  site answer input: site hex/class, roster strength (engine), group strength after the
                      leader-safety judge (0 = leader group refused), asking group.
  SITEOUT 0x5581C946  site answer output: final priority (after recruit/ladder/boost), BOOSTED flag.
                      (SITEIN without SITEOUT for the same site = the group was refused.)
  RTAG    0x5573A20C  recruit tag check in TargetFoundEvent (target key, its required strength before the tag).
  GATE    0x558147DC  search gate (converge v5): AI army ON the site vs roster.  MINT 0x558147E6 = search minted.
  XSOK    0x557C1A6F  ExecuteSearch passed CanSearch (leader-safety XS gate next).  XSNO 0x557C1CF2 = search refused.
  ITEMQ   0x55814D7F  item-bag answer started (anti-lure check next).  ITEMBEST 0x55814EB8 = best useful value found
                      (0 = nothing a hero wants).  ITEMOUT 0x5581C3C0 = item priority written (prio/busy check passed).
                      ITEMQ without ITEMOUT = anti-lure veto, busy group, or nothing useful (see ITEMBEST).
  STACK   0x55819410  superstack step for a player.  MOVE 0x5574A490 = MoveArmyXYL (every queued move: AI/superstack).

Lines are grouped under '=== TURN player N ===' headers ([engine+0xA5] = current player).
At attach it dumps a SNAPSHOT: players (AI flag), leader + leader stack, every army of every player (hex, units).

Usage (game running, BEFORE ending your turn):  py -3.10 diag_ai_turn_probe.py [--seconds 1200] [--noscore]
Stop: Ctrl+C or create patch scripts\\ai_turn_probe.stop.  Log: patch scripts\\ai_turn_probe_log.txt
(--noscore drops the SCORE lines if the AI turn gets too slow.)  Run elevated if attach fails.
Do not run while another debugger probe is attached."""
import ctypes as C, ctypes.wintypes as W, struct, sys, time, os, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(HERE, "ai_turn_probe_log.txt"); STOP = os.path.join(HERE, "ai_turn_probe.stop")
SECS = int(sys.argv[sys.argv.index("--seconds") + 1]) if "--seconds" in sys.argv else 1200
NOSCORE = "--noscore" in sys.argv
EPREF = 0x55700000
SITES = {0x5573C633: "SCORE", 0x55814AC2: "SITEIN", 0x5581C946: "SITEOUT", 0x5573A20C: "RTAG",
         0x558147DC: "GATE", 0x558147E6: "MINT", 0x557C1A6F: "XSOK", 0x557C1CF2: "XSNO",
         0x55814D7F: "ITEMQ", 0x55814EB8: "ITEMBEST", 0x5581C3C0: "ITEMOUT",
         0x55819410: "STACK", 0x5574A490: "MOVE"}
if NOSCORE: SITES.pop(0x5573C633)
SINGLE_STEP = (0x80000004, 0x4000001E)
BREAKPOINT = (0x80000003, 0x4000001F)
DBG_CONTINUE, DBG_NOT_HANDLED = 0x00010002, 0x80010001
PTR = C.sizeof(C.c_void_p)
k32 = C.WinDLL("kernel32", use_last_error=True); psapi = C.WinDLL("psapi", use_last_error=True); vp = C.c_void_p
k32.WaitForDebugEvent.argtypes = [vp, W.DWORD]; k32.ContinueDebugEvent.argtypes = [W.DWORD, W.DWORD, W.DWORD]
k32.OpenProcess.restype = vp; k32.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
k32.OpenThread.restype = vp; k32.OpenThread.argtypes = [W.DWORD, W.BOOL, W.DWORD]
k32.ReadProcessMemory.argtypes = [vp, vp, vp, C.c_size_t, C.POINTER(C.c_size_t)]
k32.WriteProcessMemory.argtypes = [vp, vp, vp, C.c_size_t, C.POINTER(C.c_size_t)]
k32.VirtualProtectEx.argtypes = [vp, vp, C.c_size_t, W.DWORD, C.POINTER(W.DWORD)]
k32.FlushInstructionCache.argtypes = [vp, vp, C.c_size_t]
k32.CloseHandle.argtypes = [vp]; k32.CreateToolhelp32Snapshot.restype = vp
k32.SuspendThread.argtypes = [vp]; k32.ResumeThread.argtypes = [vp]
k32.Thread32First.argtypes = [vp, vp]; k32.Thread32Next.argtypes = [vp, vp]
psapi.EnumProcessModulesEx.argtypes = [vp, vp, W.DWORD, C.POINTER(W.DWORD), W.DWORD]
psapi.GetModuleBaseNameW.argtypes = [vp, vp, W.LPWSTR, W.DWORD]; psapi.GetModuleInformation.argtypes = [vp, vp, vp, W.DWORD]
if PTR == 8:
    k32.Wow64GetThreadContext.argtypes = [vp, vp]; k32.Wow64SetThreadContext.argtypes = [vp, vp]
    GETCTX, SETCTX = k32.Wow64GetThreadContext, k32.Wow64SetThreadContext
    U_OFF = 16
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
def rpm(a, n):
    b = C.create_string_buffer(n); r = C.c_size_t()
    return b.raw[:r.value] if a and k32.ReadProcessMemory(hp, a, b, n, C.byref(r)) else b""
def u32(a):
    b = rpm(a, 4); return struct.unpack("<I", b)[0] if len(b) == 4 else None
def u8(a):
    b = rpm(a, 1); return b[0] if b else None
def s32(v):
    return None if v is None else (v - (1 << 32) if v >= 0x80000000 else v)
def wpm(a, data):
    old = W.DWORD(); r = C.c_size_t()
    k32.VirtualProtectEx(hp, a, len(data), 0x40, C.byref(old))
    ok = k32.WriteProcessMemory(hp, a, data, len(data), C.byref(r))
    k32.VirtualProtectEx(hp, a, len(data), old.value, C.byref(old))
    k32.FlushInstructionCache(hp, a, len(data))
    return bool(ok)
def modules():
    arr = (vp * 1024)(); need = W.DWORD(); psapi.EnumProcessModulesEx(hp, arr, C.sizeof(arr), C.byref(need), 0x03); out = []
    for i in range(need.value // PTR):
        b = arr[i]
        if not b or b >= 1 << 32: continue
        nm = C.create_unicode_buffer(260); psapi.GetModuleBaseNameW(hp, b, nm, 260); mi = MODULEINFO()
        psapi.GetModuleInformation(hp, b, C.byref(mi), C.sizeof(mi)); out.append((b, mi.SizeOfImage, nm.value))
    return sorted(out)
def sym(a):
    for b, s, n in mods:
        if b <= a < b + s: return "%s+0x%X" % (n, a - b)
    return hex(a)
def clsname(obj):
    vmt = u32(obj) if obj else None
    p = u32(vmt - 0x20) if vmt else None
    if not p: return "?"
    n = u8(p) or 0
    return rpm(p + 1, min(n, 63)).decode("latin1", "replace")
def ep(va): return (va - EPREF + EPB) & 0xFFFFFFFF
def tlist(lst):
    """object with a TList at +8 (TUnitList-style) -> items; or a bare TList (+4 items, +8 count)."""
    if not lst: return []
    for tl in (u32(lst + 8), lst):
        if not tl: continue
        n = u32(tl + 8); it = u32(tl + 4)
        if n is not None and it and 0 <= n <= 256:
            out = [u32(it + 4 * i) or 0 for i in range(n)]
            if all(x == 0 or x > 0x10000 for x in out): return out
    return []
def loc(obj):
    """map object (army / site / bag HS): [+0x10]&1 placed, [+0x13]=x [+0x14]=y [+0x15]=level (TArmy GetLocation)."""
    if not obj: return "?"
    if not (u8(obj + 0x10) or 0) & 1: return "(off-map)"
    return "(%d,%d L%d)" % (u8(obj + 0x13) or 0, u8(obj + 0x14) or 0, u8(obj + 0x15) or 0)
def key(k):
    if k is None: return "?"
    if k == 0xFFFFFFFF: return "none"
    return "(%d,%d L%d)" % (k & 0xFF, (k >> 8) & 0xFF, (k >> 16) & 0xFF)
def engine(): return u32(ep(0x558FA040))
def players():
    g = engine(); pl = u32(g + 0x140) if g else None
    return tlist(pl)
def cur_player():
    g = engine(); v = u8(g + 0xA5) if g else None
    return -1 if v is None else (v - 256 if v > 127 else v)
def pdesc(idx):
    ps = players()
    if idx is None or idx < 0 or idx >= len(ps): return "indep" if idx == -1 else "p?%s" % idx
    p = ps[idx]; return "P%d(%s)" % (idx, "AI" if u8(p + 0xA7) else "HUMAN")
def day():
    m = u32(ep(0x558E9494)); m = u32(m) if m else None
    return s32(u32(m + 0x174)) if m else -1
def units_desc(lst):
    us = tlist(lst); parts = []
    for u in us:
        c = clsname(u); parts.append("*LEADER*" if c == "TLeader" else c)
    return len(us), ", ".join(parts)
def army_desc(army):
    if not army: return "army=nil"
    own = u8(army + 0x12); own = None if own is None else (own - 256 if own > 127 else own)
    n, parts = units_desc(army)
    return "%s army %08X @%s %d units [%s]" % (pdesc(own), army, loc(army), n, parts)
def group_desc(gc):
    """gc = group controller ([msg+0x10]); grp = [gc+0xC] = the AI group (unit list + +0x38 target, +0x3C mode)."""
    if not gc: return "group=nil"
    grp = u32(gc + 0xC)
    n, parts = units_desc(grp)
    armies = sorted({u32(u + 4) for u in tlist(grp) if u})
    where = " ".join(loc(a) for a in armies if a)
    return "group %08X %d units at %s [%s] committed->%s mode=%s" % (grp or 0, n, where or "?", parts,
                                                                  key(u32(grp + 0x38) if grp else None),
                                                                  u8(grp + 0x3C) if grp else "?")


LAST_TURN = [None]
def turn_header():
    p = cur_player()
    if p != LAST_TURN[0]:
        LAST_TURN[0] = p; log("=== TURN %s, day %d ===" % (pdesc(p), day()))


def describe(nm, r):
    eax, ebx, ecx, edx, esi, edi, ebp, esp = (r[k] for k in ("eax", "ebx", "ecx", "edx", "esi", "edi", "ebp", "esp"))
    if nm == "SCORE":
        # esi = target record, edi = final score, ebp = group, ebx = selector
        return "SCORE   target %s prio=%s pathcost=%s -> score %d | %s" % (
            key(u32(esi + 0x30)), s32(u32(esi + 0x18)), s32(u32(esi + 0x34)), s32(edi),
            group_desc_from_grp(ebp))
    if nm == "SITEIN":
        return "SITEIN  site %s %s roster S=%d | group S(eff)=%d%s (ratio %.2f) | %s" % (
            clsname(esi), loc(esi), s32(ebp), s32(eax), "  <-- 0 = LEADER GROUP REFUSED" if eax == 0 else "",
            (s32(eax) / s32(ebp)) if ebp and s32(ebp) > 0 else 0.0, group_desc(u32(edi + 0x10)))
    if nm == "SITEOUT":
        return "SITEOUT site %s %s roster S=%d -> priority %d%s (record had %s)" % (
            clsname(esi), loc(esi), s32(ebp), s32(eax), " BOOSTED" if ecx else "", s32(u32(ebx)))
    if nm == "RTAG":
        return "RTAG    target %s required S before tag=%s" % (key(u32(ebx + 0x30)), s32(u32(ebx + 0x40)))
    if nm == "GATE":
        return "GATE    site %s %s roster S=%d | army on site S=%d (ratio %.2f) | %s" % (
            clsname(ebx), loc(ebx), s32(edi), s32(eax), (s32(eax) / s32(edi)) if edi and s32(edi) > 0 else 0.0,
            pdesc(s32(esi)))
    if nm == "MINT":
        return "MINT    site %s %s -> AI SEARCH STARTED" % (clsname(ebx), loc(ebx))
    if nm == "XSOK":
        return "XSOK    ExecuteSearch site %s %s searcher %s (leader-safety XS gate next)" % (
            clsname(ebx), loc(ebx), army_desc(u32(esi + 0x1C) if esi else 0))
    if nm == "XSNO":
        return "XSNO    ExecuteSearch site %s %s REFUSED/failed" % (clsname(ebx), loc(ebx))
    if nm == "ITEMQ":
        rec = u32(edi + 0xC)
        return "ITEMQ   bag %s at %s asked by %s" % (clsname(esi), loc(esi), group_desc(u32(edi + 0x10)))
    if nm == "ITEMBEST":
        return "ITEMBEST best useful item value=%s (0 = nothing a hero in the group would take)" % s32(u32(esp + 4))
    if nm == "ITEMOUT":
        return "ITEMOUT item priority %d written (record had %s)" % (s32(eax), s32(u32(ebx)))
    if nm == "STACK":
        return "STACK   superstack step (eax=%08X)" % eax
    if nm == "MOVE":
        ret = u32(esp) or 0
        return "MOVE    MoveArmyXYL %s mask=%08X to x=%d (caller %s)" % (army_desc(eax), edx, ecx & 0xFF, sym(ret))
    return nm


def group_desc_from_grp(grp):
    if not grp: return "group=nil"
    n, parts = units_desc(grp)
    armies = sorted({u32(u + 4) for u in tlist(grp) if u})
    where = " ".join(loc(a) for a in armies if a)
    return "group %08X %d units at %s [%s] committed->%s mode=%s" % (grp, n, where or "?", parts,
                                                                  key(u32(grp + 0x38)), u8(grp + 0x3C))


def snapshot():
    log("=== SNAPSHOT day %d, current %s ===" % (day(), pdesc(cur_player())))
    for i, p in enumerate(players()):
        if not p: continue
        lead = u32(p + 0xD4)
        log("  %s leader=%s %s" % (pdesc(i), clsname(lead) if lead else "none",
                                   ("in " + army_desc(u32(lead + 4))) if lead else ""))
        for a in tlist(u32(p + 0x28)):
            if a: log("      " + army_desc(a))


pid = None
out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq AoWx.exe", "/FO", "CSV", "/NH"], capture_output=True, text=True).stdout
for line in out.splitlines():
    if line.lower().startswith('"aowx.exe"'):
        pid = int(line.split('","')[1]); break
if not pid:
    print("AoWx.exe is not running"); sys.exit(1)
hp = k32.OpenProcess(0x1FFFFF, False, pid)
mods = modules(); base_of = {n.lower(): b for b, s, n in mods}; EPB = base_of.get("aowepack.dll")
if not EPB:
    print("AoWEPACK.dll not loaded"); sys.exit(1)
BPS = {}                       # live addr -> [name, original byte]
for va, nm in SITES.items():
    BPS[ep(va)] = [nm, None]


def all_threads():
    snap = k32.CreateToolhelp32Snapshot(0x4, 0); te = THREADENTRY32(); te.dwSize = C.sizeof(te); out = []
    if k32.Thread32First(snap, C.byref(te)):
        while True:
            if te.th32OwnerProcessID == pid: out.append(te.th32ThreadID)
            if not k32.Thread32Next(snap, C.byref(te)): break
    k32.CloseHandle(snap); return out


def install():
    n = 0
    for a, v in BPS.items():
        b = rpm(a, 1)
        if not b: continue
        if b[0] == 0xCC: log("WARN %s @%08X already int3 - skipped" % (v[0], a)); continue
        v[1] = b[0]
        if wpm(a, b"\xCC"): n += 1
        else: v[1] = None; log("WARN could not arm %s @%08X" % (v[0], a))
    return n
def remove_all():
    for a, v in BPS.items():
        if v[1] is not None: wpm(a, bytes([v[1]]))


if not k32.DebugActiveProcess(pid):
    log("DebugActiveProcess failed %d (run elevated?)" % C.get_last_error()); sys.exit(1)
k32.DebugSetProcessKillOnExit(False)
log("attached pid=%d AoWEPACK@%08X, %d sites, %ds%s" % (pid, EPB, len(BPS), SECS, " (no SCORE)" if NOSCORE else ""))
t0 = time.time(); ev = C.create_string_buffer(256); first = True; pending = {}   # tid -> bp addr to re-arm
nexc = 0; hits = 0


def handle(code, etid):
    """returns continue status for one EXCEPTION event."""
    global nexc, hits
    u = U_OFF
    if PTR == 8:
        xc, xf, _rec, xaddr, npar = struct.unpack_from("<IIQQI", ev, u); info = struct.unpack_from("<15Q", ev, u + 32)
        firstchance = struct.unpack_from("<I", ev, u + 152)[0]
    else:
        xc, xf, _rec, xaddr, npar = struct.unpack_from("<IIIII", ev, u); info = struct.unpack_from("<15I", ev, u + 20)
        firstchance = struct.unpack_from("<I", ev, u + 80)[0]
    xaddr &= 0xFFFFFFFF
    if xc in BREAKPOINT and xaddr in BPS:
        nm, orig = BPS[xaddr]
        ht = k32.OpenThread(0x1FFFFF, False, etid); ctx = C.create_string_buffer(716); struct.pack_into("<I", ctx, 0, 0x10007)
        GETCTX(ht, ctx)
        edi, esi, ebx, edx, ecx, eax, ebp, eip, _cs, fl, esp = struct.unpack_from("<11I", ctx, 0x9C)
        if orig is not None:
            try:
                turn_header(); hits += 1
                log(describe(nm, dict(eax=eax, ebx=ebx, ecx=ecx, edx=edx, esi=esi, edi=edi, ebp=ebp, esp=esp)))
            except Exception as e:                                           # never let a decode error hurt the game
                log("%s decode error %r" % (nm, e))
            wpm(xaddr, bytes([orig]))
            struct.pack_into("<I", ctx, 0xB8, xaddr)                            # back to the original instruction
            struct.pack_into("<I", ctx, 0xC0, fl | 0x100)                       # TF: single-step it, then re-arm
            pending[etid] = xaddr
        else:
            struct.pack_into("<I", ctx, 0xB8, xaddr)
        SETCTX(ht, ctx); k32.CloseHandle(ht)
        return DBG_CONTINUE
    if xc in SINGLE_STEP:
        if etid in pending:
            a = pending.pop(etid)
            if BPS[a][1] is not None and not stopping: wpm(a, b"\xCC")
            return DBG_CONTINUE
        return DBG_NOT_HANDLED
    if xc in BREAKPOINT:
        return DBG_CONTINUE                                                    # attach break-in
    if firstchance and nexc < 200:
        nexc += 1; extra = ""
        if xc == 0x0EEDFADE and npar >= 2:
            obj = info[1] & 0xFFFFFFFF; msgp = u32(obj + 4)
            ln = (u32(msgp - 4) or 0) if msgp else 0
            msg = rpm(msgp, min(ln, 200)).decode("latin1", "replace") if msgp else ""
            extra = " Delphi %s '%s' raised at %s" % (clsname(obj), msg, sym(info[0] & 0xFFFFFFFF))
        elif xc == 0xC0000005 and npar >= 2:
            extra = " AV %s of 0x%08X" % ("write" if info[0] else "read", info[1] & 0xFFFFFFFF)
        log("EXCEPTION 0x%08X at %s%s" % (xc, sym(xaddr), extra))
    return DBG_NOT_HANDLED


stopping = False
try:
    while time.time() - t0 < SECS and not os.path.exists(STOP):
        if not k32.WaitForDebugEvent(ev, 500): continue
        code, epid, etid = struct.unpack_from("<III", ev, 0); status = DBG_CONTINUE
        if first:                                                    # process frozen while we hold this event
            try: snapshot()
            except Exception as e: log("snapshot error %r" % e)
            log("armed %d breakpoints" % install()); first = False
        if code == 5:
            log("process exited"); k32.ContinueDebugEvent(epid, etid, status); break
        if code == 1:
            status = handle(code, etid)
        k32.ContinueDebugEvent(epid, etid, status)
except KeyboardInterrupt:
    pass
# Detach safely: remove every int3, then drain events until no thread is mid-single-step.
stopping = True
try:
    remove_all()
    t1 = time.time()
    while (pending or time.time() - t1 < 1.0) and time.time() - t1 < 5.0:
        if not k32.WaitForDebugEvent(ev, 200): continue
        code, epid, etid = struct.unpack_from("<III", ev, 0); status = DBG_CONTINUE
        if code == 1: status = handle(code, etid)
        k32.ContinueDebugEvent(epid, etid, status)
finally:
    k32.DebugActiveProcessStop(pid)
    log("detached (%d breakpoint hits%s)" % (hits, "; WARNING threads still pending: %s" % list(pending) if pending else ""))
