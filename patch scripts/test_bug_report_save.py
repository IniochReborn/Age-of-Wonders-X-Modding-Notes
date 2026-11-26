#!/usr/bin/env python3
r"""Fire a fake "Out of Sync" record in every running AoWx.exe (AoWxLog.dll export TestDump, via a remote thread):
the log gets an OoS entry with a REF and - with a game running - the bug-report save appears in X\Bug Report.
Nothing in the game state is touched.  Only the first trigger per game session makes a save (same error signature).

    py -3.10 test_bug_report_save.py
"""
import ctypes, os, struct, subprocess, sys
from ctypes import wintypes as W

HERE = os.path.dirname(os.path.abspath(__file__))
DLL = os.path.join(os.path.dirname(HERE), "AoWxLog.dll")
k32 = ctypes.WinDLL("kernel32", use_last_error=True); psapi = ctypes.WinDLL("psapi", use_last_error=True)
k32.OpenProcess.restype = W.HANDLE; k32.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
k32.CreateRemoteThread.restype = W.HANDLE
k32.CreateRemoteThread.argtypes = [W.HANDLE, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, W.DWORD, ctypes.c_void_p]
psapi.EnumProcessModulesEx.argtypes = [W.HANDLE, ctypes.c_void_p, W.DWORD, ctypes.POINTER(W.DWORD), W.DWORD]
psapi.GetModuleBaseNameA.argtypes = [W.HANDLE, ctypes.c_void_p, ctypes.c_char_p, W.DWORD]


def export_rva(path, name):
    d = open(path, "rb").read()
    pe = struct.unpack_from("<I", d, 0x3C)[0]; opt = struct.unpack_from("<H", d, pe + 20)[0]; n = struct.unpack_from("<H", d, pe + 6)[0]
    secs = [struct.unpack_from("<IIII", d, pe + 24 + opt + 40 * k + 8) for k in range(n)]
    def off(rva):
        for vs, va, rs, ro in secs:
            if va <= rva < va + max(vs, rs): return ro + rva - va
    e = off(struct.unpack_from("<I", d, pe + 24 + 0x60)[0])
    cnt = struct.unpack_from("<I", d, e + 0x18)[0]; af, an, ao = struct.unpack_from("<III", d, e + 0x1C)
    for i in range(cnt):
        no = off(struct.unpack_from("<I", d, off(an) + 4 * i)[0])
        if d[no:d.index(b"\0", no)].decode() == name:
            return struct.unpack_from("<I", d, off(af) + 4 * struct.unpack_from("<H", d, off(ao) + 2 * i)[0])[0]
    raise SystemExit("export %s not found" % name)


def main():
    rva = export_rva(DLL, "TestDump")
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq AoWx.exe", "/FO", "CSV", "/NH"], capture_output=True, text=True).stdout
    pids = [int(l.split('","')[1]) for l in out.splitlines() if l.lower().startswith('"aowx.exe"')]
    if not pids: print("AoWx.exe is not running"); return 1
    for pid in pids:
        h = k32.OpenProcess(0x1F0FFF, False, pid)
        if not h: print(pid, "cannot open, error", ctypes.get_last_error()); continue
        mods = (ctypes.c_void_p * 1024)(); need = W.DWORD()
        psapi.EnumProcessModulesEx(h, mods, ctypes.sizeof(mods), ctypes.byref(need), 1)   # LIST_MODULES_32BIT
        base = None
        for m in mods[:need.value // ctypes.sizeof(ctypes.c_void_p)]:
            buf = ctypes.create_string_buffer(260); psapi.GetModuleBaseNameA(h, m, buf, 260)
            if buf.value.lower() == b"aowxlog.dll": base = m
        if base is None: print(pid, "AoWxLog.dll is not loaded in this game"); continue
        t = k32.CreateRemoteThread(h, None, 0, base + rva, None, 0, None)
        print(pid, "fake Out of Sync fired" if t else "CreateRemoteThread failed, error %d" % ctypes.get_last_error())
        if t: k32.WaitForSingleObject(W.HANDLE(t), 5000); k32.CloseHandle(W.HANDLE(t))
        k32.CloseHandle(h)
    return 0


if __name__ == "__main__":
    sys.exit(main())
