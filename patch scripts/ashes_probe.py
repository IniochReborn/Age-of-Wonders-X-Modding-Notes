#!/usr/bin/env python3
r"""Read the Ashes to Ashes gate TRACE ring out of a RUNNING AoWx.exe (2026-10-13).

patch_tc_ashes_v1.py v10t writes 64 x 16-byte records at AoWTCPCK.dll VA 0x46BB10 (write index at 0x46BB00):
  code 1 = all-strikes-done branch (driver killed), 2 = corpse popped, 4 = gap/refresh tick, 5 = strike pass
  then [te+0x34] strikes done, [te+0x28] strike count, driver (effect ptr found, 0 = none -> spawned on code 5).
Also dumps the corpse queue (0x46B900: count / next / tick / fresh).
Cast the spell, leave the game open, run:  py -3.10 ashes_probe.py
"""
import ctypes as C, ctypes.wintypes as W, struct, sys

k32 = C.WinDLL("kernel32", use_last_error=True); psapi = C.WinDLL("psapi", use_last_error=True)
PROCESS_QUERY_INFORMATION, PROCESS_VM_READ = 0x400, 0x10
TH32CS_SNAPPROCESS = 2

class PROCESSENTRY32W(C.Structure):
    _fields_ = [("dwSize", W.DWORD), ("cntUsage", W.DWORD), ("th32ProcessID", W.DWORD), ("th32DefaultHeapID", C.POINTER(C.c_ulong)),
                ("th32ModuleID", W.DWORD), ("cntThreads", W.DWORD), ("th32ParentProcessID", W.DWORD), ("pcPriClassBase", C.c_long),
                ("dwFlags", W.DWORD), ("szExeFile", C.c_wchar * 260)]

def find_pid(name):
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0); pe = PROCESSENTRY32W(); pe.dwSize = C.sizeof(pe)
    ok = k32.Process32FirstW(snap, C.byref(pe)); pid = None
    while ok:
        if pe.szExeFile.lower() == name.lower(): pid = pe.th32ProcessID; break
        ok = k32.Process32NextW(snap, C.byref(pe))
    k32.CloseHandle(snap); return pid

def module_base(h, name):
    arr = (C.c_void_p * 1024)(); needed = W.DWORD()
    psapi.EnumProcessModulesEx.argtypes = [W.HANDLE, C.POINTER(C.c_void_p), W.DWORD, C.POINTER(W.DWORD), W.DWORD]
    if not psapi.EnumProcessModulesEx(h, arr, C.sizeof(arr), C.byref(needed), 3): raise OSError(C.get_last_error())
    buf = C.create_unicode_buffer(520)
    for k in range(needed.value // C.sizeof(C.c_void_p)):
        psapi.GetModuleFileNameExW(h, arr[k], buf, 520)
        if buf.value.lower().endswith("\\" + name.lower()): return arr[k]
    return None

def main():
    pid = find_pid("AoWx.exe")
    if not pid: print("AoWx.exe is not running"); return 1
    k32.OpenProcess.restype = W.HANDLE; h = k32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
    if not h: print("OpenProcess failed (%d) - run from an elevated prompt" % C.get_last_error()); return 1
    base = module_base(h, "AoWTCPCK.dll")
    if base is None: print("AoWTCPCK.dll not found in the process"); return 1
    print("pid %d, AoWTCPCK.dll base %#x" % (pid, base))
    def rd(va, n):
        buf = C.create_string_buffer(n); got = C.c_size_t()
        k32.ReadProcessMemory.argtypes = [W.HANDLE, C.c_void_p, C.c_void_p, C.c_size_t, C.POINTER(C.c_size_t)]
        if not k32.ReadProcessMemory(h, base + (va - 0x400000), buf, n, C.byref(got)): raise OSError("ReadProcessMemory %#x: %d" % (va, C.get_last_error()))
        return buf.raw
    q = rd(0x46B900, 16); print("queue: count %d next %d tick %d fresh %d" % struct.unpack("<4I", q))
    t = rd(0x46BB00, 0x410); idx = struct.unpack_from("<I", t, 0)[0]; print("trace writes:", idx)
    names = {1: "DONE->kill", 2: "corpse pop", 4: "gap tick ", 5: "STRIKE    ", 6: "fx26 mark ", 7: "fx26 tick "}
    n = min(idx, 64); start = idx - n
    for k in range(start, idx):
        code, done, total, drv = struct.unpack_from("<4I", t, 0x10 + (k & 63) * 16)
        if code in (6, 7): print("  #%3d %-10s effect kindword=%#x f28=%#x %s=%d" % (k, names[code], done, total, "marker" if code == 6 else "tick", drv))
        elif code in (8, 9): print("  #%3d %-10s tick=%d landed=%d done=%d slot=%d" % (k, "nf frame  " if code == 8 else "show      ", struct.unpack("<i", struct.pack("<I", done))[0], total & 0xFF, total >> 8, drv))
        else: print("  #%3d %-10s done=%d total=%d driver=%#x%s" % (k, names.get(code, str(code)), done, total, drv, "  (spawned)" if code == 5 and drv == 0 else ""))
    k32.CloseHandle(h); return 0

if __name__ == "__main__":
    sys.exit(main())
