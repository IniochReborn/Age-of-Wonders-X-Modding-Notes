#!/usr/bin/env python3
r"""Hang watcher v2 (2026-11-13): waits for a process (default AoWx.exe) and records where it is stuck.
v1 missed a real hang (WER "Top level window is idle") because it relied on SendMessageTimeout alone.  v2:
  * every second takes a light snapshot of every thread (EIP + symbolised stack return candidates) into a ring;
  * triggers a full dump (hang_dump_N.txt, max 6) when a window is hung (IsHungAppWindow or WM_NULL timeout) for 3 s,
    or the process burns >= 85 % of a core for 8 s in a row;
  * when the process exits, writes the last 40 ring snapshots to hang_ring.txt;
  * logs every state change to hang_watch.log (flushed).
Nothing is injected; threads are only suspended for the snapshot.
Usage: py -3.10 diag_hang_watch.py [AoWx.exe | --pid N] [max minutes=180]"""
import collections, ctypes as C, os, struct, sys, time
from ctypes import wintypes as W
import psutil

k32 = C.WinDLL("kernel32", use_last_error=True); u = C.WinDLL("user32")
k32.OpenThread.restype = C.c_void_p; k32.OpenProcess.restype = C.c_void_p
k32.CreateToolhelp32Snapshot.restype = C.c_void_p
k32.ReadProcessMemory.argtypes = [C.c_void_p, C.c_void_p, C.c_void_p, C.c_size_t, C.c_void_p]
u.SendMessageTimeoutW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM, W.UINT, W.UINT, C.c_void_p]
u.IsHungAppWindow.argtypes = [W.HWND]
CB = C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
HERE = os.path.dirname(os.path.abspath(__file__))
SKIP = ("ntdll", "wow64", "kernel", "user32", "win32u", "gdi32", "klhk")
NCPU = psutil.cpu_count() or 1


def log(*a):
    with open(os.path.join(HERE, "hang_watch.log"), "a", encoding="utf-8") as f:
        f.write(time.strftime("%H:%M:%S ") + " ".join(str(x) for x in a) + "\n")
    print(*a, flush=True)


class CTX(C.Structure):
    _fields_ = [("ContextFlags", W.DWORD), ("Dr", W.DWORD * 6), ("Float", C.c_byte * 112),
                ("SegGs", W.DWORD), ("SegFs", W.DWORD), ("SegEs", W.DWORD), ("SegDs", W.DWORD),
                ("Edi", W.DWORD), ("Esi", W.DWORD), ("Ebx", W.DWORD), ("Edx", W.DWORD), ("Ecx", W.DWORD),
                ("Eax", W.DWORD), ("Ebp", W.DWORD), ("Eip", W.DWORD), ("SegCs", W.DWORD), ("EFlags", W.DWORD),
                ("Esp", W.DWORD), ("SegSs", W.DWORD), ("Ext", C.c_byte * 512)]


class ME(C.Structure):
    _fields_ = [("dwSize", W.DWORD), ("th32ModuleID", W.DWORD), ("th32ProcessID", W.DWORD), ("GlblcntUsage", W.DWORD),
                ("ProccntUsage", W.DWORD), ("modBaseAddr", C.c_void_p), ("modBaseSize", W.DWORD),
                ("hModule", C.c_void_p), ("szModule", C.c_wchar * 256), ("szExePath", C.c_wchar * 260)]


def modules(pid):
    out = []
    h = k32.CreateToolhelp32Snapshot(0x18, pid)
    me = ME(); me.dwSize = C.sizeof(ME)
    ok = k32.Module32FirstW(C.c_void_p(h), C.byref(me))
    while ok:
        out.append((me.modBaseAddr or 0, me.modBaseSize, me.szModule))
        ok = k32.Module32NextW(C.c_void_p(h), C.byref(me))
    k32.CloseHandle(C.c_void_p(h))
    return out


def top_windows(pid):
    out = []
    def cb(h, l):
        q = W.DWORD(); u.GetWindowThreadProcessId(h, C.byref(q))
        if q.value == pid:
            out.append(h)
        return True
    u.EnumWindows(CB(cb), 0)
    return out


class Target:
    def __init__(self, p):
        self.p = p; self.hp = k32.OpenProcess(0x1F0FFF, False, p.pid); self.mods = []; self.tmods = 0

    def sym(self, a):
        for b, s, n in self.mods:
            if b <= a < b + s:
                return "%s+%#x" % (n, a - b)

    def snap(self, depth):
        if time.time() - self.tmods > 10:
            self.mods = modules(self.p.pid) or self.mods; self.tmods = time.time()
        L = [time.strftime("%H:%M:%S")]
        for t in self.p.threads():
            ht = k32.OpenThread(0x1F03FF, False, t.id)
            if not ht:
                continue
            k32.SuspendThread(C.c_void_p(ht))
            c = CTX(); c.ContextFlags = 0x10007
            k32.Wow64GetThreadContext(C.c_void_p(ht), C.byref(c))
            buf = (C.c_byte * (depth * 4))(); n = C.c_size_t()
            k32.ReadProcessMemory(self.hp, c.Esp, buf, depth * 4, C.byref(n))
            k32.ResumeThread(C.c_void_p(ht)); k32.CloseHandle(C.c_void_p(ht))
            L.append("thread %d eip=%08x (%s) esp=%08x ebp=%08x eax=%08x ebx=%08x ecx=%08x edx=%08x esi=%08x edi=%08x"
                     % (t.id, c.Eip, self.sym(c.Eip), c.Esp, c.Ebp, c.Eax, c.Ebx, c.Ecx, c.Edx, c.Esi, c.Edi))
            got = n.value // 4
            for i, v in enumerate(struct.unpack("<%dI" % got, bytes(buf)[:got * 4])):
                s = self.sym(v)
                if s and not s.lower().startswith(SKIP):
                    L.append("   +%04x %08x %s" % (i * 4, v, s))
        return L


def main():
    a = sys.argv[1:]
    pid = int(a[a.index("--pid") + 1]) if "--pid" in a else None
    rest = a[:a.index("--pid")] + a[a.index("--pid") + 2:] if pid else a
    name = next((x for x in rest if not x.isdigit()), "AoWx.exe")
    mins = next((int(x) for x in rest if x.isdigit()), 180)
    end = time.time() + 60 * mins
    tgt = None; ring = collections.deque(maxlen=40); bad = busy = ndump = 0; cool = 0; last = None
    log("watching", pid or name)
    while time.time() < end:
        if tgt is None:
            ps = [q for q in psutil.process_iter(["name"])
                  if (q.pid == pid if pid else (q.info["name"] or "").lower() == name.lower())]
            if not ps:
                time.sleep(1); continue
            tgt = Target(ps[0]); ring.clear(); bad = busy = 0
            log("attached pid", tgt.p.pid); tgt.p.cpu_percent(None)
        try:
            if not tgt.p.is_running():
                raise psutil.NoSuchProcess(tgt.p.pid)
            hung = []
            for h in top_windows(tgt.p.pid):
                res = C.c_size_t()
                if u.IsHungAppWindow(h) or (u.IsWindowVisible(h)
                                            and not u.SendMessageTimeoutW(h, 0, 0, 0, 2, 1000, C.byref(res))):
                    hung.append(h)
            cpu = tgt.p.cpu_percent(None)                      # 100 = one full core
            bad = bad + 1 if hung else 0
            busy = busy + 1 if cpu >= 85 else 0
            st = (bool(hung), cpu >= 85)
            if st != last:
                log("state: hung windows", ["%#x" % h for h in hung], "cpu %.0f%%" % cpu); last = st
            ring.append(["---- cpu %.0f%% hung %d" % (cpu, len(hung))] + tgt.snap(200))
            if (bad >= 3 or busy >= 8) and time.time() > cool and ndump < 6:
                ndump += 1; out = os.path.join(HERE, "hang_dump_%s_%d.txt" % (name, ndump))
                L = ["trigger: %s" % ("window hung" if bad >= 3 else "cpu busy")]
                L += ["  module %08x %08x %s" % m for m in sorted(tgt.mods)]
                for _ in range(10):
                    L += tgt.snap(60); time.sleep(0.15)
                L += ["==== deep"] + tgt.snap(4000)
                open(out, "w", encoding="utf-8").write("\n".join(L) + "\n")
                log("HANG captured ->", out); cool = time.time() + 20
        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            out = os.path.join(HERE, "hang_ring_%s.txt" % name)
            open(out, "w", encoding="utf-8").write("\n".join("\n".join(s) for s in ring) + "\n")
            log("process gone (%s); ring ->" % type(e).__name__, out, "dumps:", ndump)
            tgt = None; last = None
            if pid:
                return
        time.sleep(1)
    log("time up")


if __name__ == "__main__":
    main()
