#!/usr/bin/env python3
r"""Read Sandstorm (388) per-cast counters out of a RUNNING AoWx.exe (patch_sandstorm_v1.py v3, AoWTCPCK DATA slack
0x46BA70: +0 landings on units this cast, +4 units found in the 19 hexes at strike 0, +8 strike count set; 0x46BA80:
16 x {unit HS, landings}).  Cast Sandstorm, leave the game open, run:  py -3.10 sandstorm_probe.py
A landings total above 3 x units (or units = 0 with landings > 0) means the strike-0 enumeration is not doing its job."""
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
    if not h: print("OpenProcess failed (%d)" % C.get_last_error()); return 1
    base = module_base(h, "AoWTCPCK.dll")
    if base is None: print("AoWTCPCK.dll not found"); return 1
    buf = C.create_string_buffer(0x90); got = C.c_size_t()
    k32.ReadProcessMemory.argtypes = [W.HANDLE, C.c_void_p, C.c_void_p, C.c_size_t, C.POINTER(C.c_size_t)]
    if not k32.ReadProcessMemory(h, base + (0x46BA70 - 0x400000), buf, 0x90, C.byref(got)): print("read failed", C.get_last_error()); return 1
    v = struct.unpack("<36I", buf.raw)
    print("pid %d AoWTCPCK base %#x" % (pid, base))
    print("  landings on units this cast %d | units at strike 0 %d | strike count set %d" % (v[0], v[1], v[2]))
    for k in range(16):
        hs, n = v[4 + 2 * k], v[5 + 2 * k]
        if hs: print("  unit HS %#010x landings %d" % (hs, n))
    k32.CloseHandle(h); return 0

if __name__ == "__main__":
    sys.exit(main())
