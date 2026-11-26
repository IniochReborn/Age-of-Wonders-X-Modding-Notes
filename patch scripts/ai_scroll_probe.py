#!/usr/bin/env python3
r"""
Live read of the AI-scroll-spell diagnostic counters (patch_ai_scroll_spells_v1 DIAG, 2026-10-30).
Run while AoWx.exe is running (after the AI has played a turn / a battle):  py -3.10 ai_scroll_probe.py
Counters (AoWEPACK DATA slack 0x558E9BD0, rebased with the module):
  strategic: enter / caster is THero / scroll spell resolved / spell added to the AI list
  fast combat: enter / caster is THero / scroll spell not researched / CanCastSpellInstantly true
"""
import ctypes, ctypes.wintypes as wt, subprocess, struct, sys

LINK_BASE, CNT = 0x55700000, 0x558E9BD0
NAMES = ["ST enter", "ST hero", "ST scroll spell", "ST added",
         "FC enter", "FC hero", "FC unknown scroll spell", "FC can cast"]
k32 = ctypes.windll.kernel32
k32.OpenProcess.restype = wt.HANDLE
psapi = ctypes.windll.psapi


def pid_of(name="AoWx.exe"):
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq %s" % name, "/FO", "CSV", "/NH"],
                         capture_output=True, text=True).stdout
    for line in out.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if parts and parts[0].lower() == name.lower():
            return int(parts[1])
    return None


def main():
    pid = pid_of()
    if not pid:
        print("AoWx.exe is not running"); return 1
    h = k32.OpenProcess(0x0410, False, pid)          # QUERY_INFORMATION | VM_READ
    if not h:
        print("OpenProcess failed (run as the same user / elevated?)"); return 1
    psapi.EnumProcessModulesEx.argtypes = [wt.HANDLE, ctypes.POINTER(ctypes.c_void_p), wt.DWORD,
                                           ctypes.POINTER(wt.DWORD), wt.DWORD]
    psapi.GetModuleBaseNameW.argtypes = [wt.HANDLE, ctypes.c_void_p, wt.LPWSTR, wt.DWORD]
    k32.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
                                      ctypes.POINTER(ctypes.c_size_t)]
    mods = (ctypes.c_void_p * 1024)()
    need = wt.DWORD()
    psapi.EnumProcessModulesEx(h, mods, ctypes.sizeof(mods), ctypes.byref(need), 1)   # LIST_MODULES_32BIT
    base = None
    for m in mods[:need.value // ctypes.sizeof(ctypes.c_void_p)]:
        nm = ctypes.create_unicode_buffer(260)
        psapi.GetModuleBaseNameW(h, m, nm, 260)
        if nm.value.lower() == "aowepack.dll":
            base = m; break
    if base is None:
        print("AoWEPACK.dll not found in the process"); return 1
    addr = base + (CNT - LINK_BASE)
    buf = ctypes.create_string_buffer(32)
    got = ctypes.c_size_t()
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, 32, ctypes.byref(got)):
        print("ReadProcessMemory failed"); return 1
    vals = struct.unpack("<8I", buf.raw)
    print("AoWEPACK base %#x (link %#x)" % (base, LINK_BASE))
    for n, v in zip(NAMES, vals):
        print("  %-26s %d" % (n, v))
    return 0


if __name__ == "__main__":
    sys.exit(main())
