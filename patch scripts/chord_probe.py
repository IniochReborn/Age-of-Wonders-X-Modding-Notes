#!/usr/bin/env python3
r"""Read the live mouse-chord engine state from the running AoWx.exe.
Run while the game is up (after moving the mouse in it) to see whether the
chord proc is armed, resolved and firing. Pairs with build_mouse_chords.py."""
import ctypes, ctypes.wintypes as wt, subprocess, struct

k32 = ctypes.windll.kernel32
psapi = ctypes.windll.psapi
PREF = 0x41300000

out = subprocess.check_output(['tasklist', '/FI', 'IMAGENAME eq AoWx.exe', '/FO', 'CSV', '/NH'], text=True)
line = out.splitlines()[0]
if 'INFO:' in line:
    print("AoWx.exe is not running."); raise SystemExit(1)
pid = int([p.strip('"') for p in line.split('","')][1])
h = k32.OpenProcess(0x410, False, pid)

mods = (ctypes.c_void_p * 2048)()
need = wt.DWORD()
psapi.EnumProcessModulesEx(h, mods, ctypes.sizeof(mods), ctypes.byref(need), 0x03)
nb = ctypes.create_string_buffer(260)
base = None
for i in range(need.value // 4):
    if not mods[i]:
        continue
    psapi.GetModuleBaseNameA(h, ctypes.c_void_p(mods[i]), nb, 260)
    if nb.value.lower() == b'vcl30.dpl':
        base = mods[i]; break
if not base:
    print("VCL30.dpl not loaded"); raise SystemExit(1)
delta = base - PREF


def u32(a):
    b = ctypes.create_string_buffer(4); g = ctypes.c_size_t()
    k32.ReadProcessMemory(h, ctypes.c_void_p(a + delta), b, 4, ctypes.byref(g))
    return struct.unpack('<I', b.raw)[0]


def rdb(a, n):
    b = ctypes.create_string_buffer(n); g = ctypes.c_size_t()
    k32.ReadProcessMemory(h, ctypes.c_void_p(a + delta), b, n, ctypes.byref(g))
    return b.raw


print("pid %d, VCL30 base %#x (delta %+#x)" % (pid, base, delta))
print("lpfn dword:        %#x (expect chproc 0x413a8d00+delta)" % u32(0x413A8C3E))
print("G_AOWBASE:         %#x" % u32(0x413E27FC))
st = u32(0x413E7150)
print("held state:        %#x (bit0 X1, bit1 X2, bit2 L, bit3 R)" % st)
kb = u32(0x413E7154)
print("keybd_event ptr:   %#x %s" % (kb, "(UNRESOLVED)" if kb == 0 else "(POISONED - resolution failed!)" if kb == 1 else "(ok)"))
print("GetForegroundWnd:  %#x  GWTPid: %#x  GCPid: %#x" % (u32(0x413E7158), u32(0x413E715C), u32(0x413E7160)))
print("chord events seen: %d" % u32(0x413E7164))
print("keys synthesized:  %d" % u32(0x413E7168))
print("VK table:          %s" % rdb(0x413E7170, 20).hex(' '))
