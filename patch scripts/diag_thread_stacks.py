#!/usr/bin/env python3
r"""Dump EIP + stack return-address candidates of every thread of a running 32-bit process (hang diagnosis,
2026-11-13).  Usage: py -3.10 diag_thread_stacks.py <process name, e.g. AoWDevX.exe> [depth dwords=400]
Run with a 32-bit OR 64-bit python (uses Wow64GetThreadContext when python is 64-bit)."""
import ctypes as C, struct, sys
from ctypes import wintypes as W
import psutil

k32 = C.WinDLL("kernel32", use_last_error=True)
k32.OpenThread.restype = C.c_void_p
k32.OpenProcess.restype = C.c_void_p
k32.ReadProcessMemory.argtypes = [C.c_void_p, C.c_void_p, C.c_void_p, C.c_size_t, C.c_void_p]


class CTX(C.Structure):                      # WOW64_CONTEXT
    _fields_ = [("ContextFlags", W.DWORD), ("Dr", W.DWORD * 6), ("Float", C.c_byte * 112),
                ("SegGs", W.DWORD), ("SegFs", W.DWORD), ("SegEs", W.DWORD), ("SegDs", W.DWORD),
                ("Edi", W.DWORD), ("Esi", W.DWORD), ("Ebx", W.DWORD), ("Edx", W.DWORD), ("Ecx", W.DWORD),
                ("Eax", W.DWORD), ("Ebp", W.DWORD), ("Eip", W.DWORD), ("SegCs", W.DWORD), ("EFlags", W.DWORD),
                ("Esp", W.DWORD), ("SegSs", W.DWORD), ("Ext", C.c_byte * 512)]


def main():
    name = sys.argv[1].lower(); depth = int(sys.argv[2]) if len(sys.argv) > 2 else 400
    p = [q for q in psutil.process_iter(["name"]) if (q.info["name"] or "").lower() == name][0]
    mods = sorted((int(m.addr, 16), m.path.split("\\")[-1]) for m in p.memory_maps(grouped=False) if m.path)
    def sym(a):
        best = None
        for lo, n in mods:
            if lo <= a < lo + 0x10000 and n.lower().endswith((".exe", ".dll", ".dpl")):
                best = n
        return best
    hp = k32.OpenProcess(0x1F0FFF, False, p.pid)
    for t in p.threads():
        ht = k32.OpenThread(0x1F03FF, False, t.id)
        k32.SuspendThread(C.c_void_p(ht))
        c = CTX(); c.ContextFlags = 0x10007
        ok = k32.Wow64GetThreadContext(C.c_void_p(ht), C.byref(c))
        buf = (C.c_byte * (depth * 4))(); n = C.c_size_t()
        k32.ReadProcessMemory(hp, c.Esp, buf, depth * 4, C.byref(n))
        k32.ResumeThread(C.c_void_p(ht))
        print("thread %d ok=%d eip=%08x (%s) esp=%08x ebp=%08x" % (t.id, ok, c.Eip, sym(c.Eip), c.Esp, c.Ebp))
        for i, v in enumerate(struct.unpack("<%dI" % depth, bytes(buf))):
            s = sym(v)
            if s and not s.lower().startswith(("ntdll", "wow64", "kernel", "user32", "win32u")):
                print("   +%04x %08x %s" % (i * 4, v, s))


if __name__ == "__main__":
    main()
