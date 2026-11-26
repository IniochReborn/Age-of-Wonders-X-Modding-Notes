"""Startup smoke test for patch_champion_leveled_ranged_v1: launch AoWx.exe from
the 410 folder, wait, scan process memory for TMultiLevelAbility objects with id
0x92/0x93, dump name/cap/cost list, list the process's top-level windows (error
dialogs would show here), then terminate the game."""
import ctypes as C, ctypes.wintypes as W, struct, subprocess, sys, time, os
from bakpath import game_dir, game_file   # game folder = AOW_GAME_DIR or parent of patch scripts (2026-09-20)

GAME = game_dir()
EXE = os.path.join(GAME, "AoWx.exe")
WAIT = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 30
ML_VMT_RVA = 0x5571DFD0 - 0x55700000
HOLY_VMT_RVA = 0x557B51B8 - 0x55700000

k32 = C.WinDLL("kernel32", use_last_error=True); psapi = C.WinDLL("psapi", use_last_error=True); u32 = C.WinDLL("user32")
vp = C.c_void_p
k32.OpenProcess.restype = vp; k32.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
k32.ReadProcessMemory.argtypes = [vp, vp, vp, C.c_size_t, C.POINTER(C.c_size_t)]
k32.VirtualQueryEx.argtypes = [vp, vp, vp, C.c_size_t]; k32.VirtualQueryEx.restype = C.c_size_t
k32.TerminateProcess.argtypes = [vp, W.UINT]
psapi.EnumProcessModulesEx.argtypes = [vp, vp, W.DWORD, C.POINTER(W.DWORD), W.DWORD]
psapi.GetModuleBaseNameW.argtypes = [vp, vp, W.LPWSTR, W.DWORD]

class MBI(C.Structure):
    _fields_ = [("BaseAddress", vp), ("AllocationBase", vp), ("AllocationProtect", W.DWORD),
                ("PartitionId", W.WORD), ("RegionSize", C.c_size_t), ("State", W.DWORD),
                ("Protect", W.DWORD), ("Type", W.DWORD)]

def rpm(hp, addr, size):
    buf = C.create_string_buffer(size); n = C.c_size_t()
    if not k32.ReadProcessMemory(hp, addr, buf, size, C.byref(n)): return b""
    return buf.raw[:n.value]

def modules(hp):
    arr = (vp * 512)(); need = W.DWORD()
    psapi.EnumProcessModulesEx(hp, arr, C.sizeof(arr), C.byref(need), 0x01)  # LIST_MODULES_32BIT
    out = {}
    for i in range(need.value // C.sizeof(vp)):
        name = C.create_unicode_buffer(260); psapi.GetModuleBaseNameW(hp, arr[i], name, 260)
        out[name.value.lower()] = arr[i]
    return out

def windows_of(pid):
    titles = []
    @C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
    def cb(hwnd, lp):
        p = W.DWORD(); u32.GetWindowThreadProcessId(hwnd, C.byref(p))
        if p.value == pid and u32.IsWindowVisible(hwnd):
            n = u32.GetWindowTextLengthW(hwnd); b = C.create_unicode_buffer(n + 1)
            u32.GetWindowTextW(hwnd, b, n + 1); cls = C.create_unicode_buffer(64); u32.GetClassNameW(hwnd, cls, 64)
            titles.append((cls.value, b.value))
        return True
    u32.EnumWindows(cb, 0); return titles

class _Attached:
    def __init__(self, pid): self.pid = pid
    def poll(self):
        h = k32.OpenProcess(0x0400, False, self.pid)
        if not h: return -1
        code = W.DWORD(); k32.GetExitCodeProcess(h, C.byref(code)); k32.CloseHandle(h)
        return None if code.value == 259 else code.value
if "--pid" in sys.argv:
    proc = _Attached(int(sys.argv[sys.argv.index("--pid") + 1])); print("attached pid", proc.pid)
else:
    proc = subprocess.Popen([EXE], cwd=GAME)
    print("launched pid", proc.pid); time.sleep(WAIT)
if proc.poll() is not None:
    print("!! process exited early with", proc.poll()); sys.exit(1)
hp = k32.OpenProcess(0x0411, False, proc.pid)  # QUERY_INFORMATION | VM_READ | TERMINATE
mods = modules(hp); base = mods.get("aowepack.dll")
print("modules:", {k: hex(v) for k, v in mods.items() if k.startswith("aow")})
if not base: print("!! AoWEPACK not loaded"); k32.TerminateProcess(hp, 0); sys.exit(1)
ml_vmt = base + ML_VMT_RVA; holy_vmt = base + HOLY_VMT_RVA
print(f"AoWEPACK base 0x{base:X}  ML VMT 0x{ml_vmt:X}")
pat_ml = struct.pack("<I", ml_vmt); pat_holy = struct.pack("<I", holy_vmt)
found = []; addr = 0; mbi = MBI()
while addr < 0x7FFF0000:
    if not k32.VirtualQueryEx(hp, addr, C.byref(mbi), C.sizeof(mbi)): break
    if mbi.State == 0x1000 and mbi.Protect in (0x04, 0x08) and mbi.Type == 0x20000:  # committed private RW
        data = rpm(hp, mbi.BaseAddress or 0, mbi.RegionSize); i = 0
        while True:
            i = data.find(pat_ml, i)
            if i < 0: break
            if i % 4 == 0:
                obj = mbi.BaseAddress + i; rec = data[i:i+0x30]
                if len(rec) == 0x30:
                    aid = struct.unpack_from("<I", rec, 0xC)[0]
                    if aid in (0x92, 0x93, 0x38, 0x70, 0x76):
                        nameptr, mask, cap, costlist = struct.unpack_from("<I", rec, 8)[0], struct.unpack_from("<H", rec, 0x20)[0], struct.unpack_from("<I", rec, 0x28)[0], struct.unpack_from("<I", rec, 0x2C)[0]
                        name = rpm(hp, nameptr, 32).split(b"\0")[0].decode("latin1") if nameptr else ""
                        costs = ""
                        if costlist:
                            lst = rpm(hp, costlist, 0x10)  # TIntegerList: guess +4 items ptr, +8 count
                            if len(lst) == 0x10:
                                items, cnt = struct.unpack_from("<I", lst, 4)[0], struct.unpack_from("<I", lst, 8)[0]
                                if items and 0 < cnt < 16: costs = list(struct.unpack("<%dI" % cnt, rpm(hp, items, cnt*4)))
                        found.append((obj, aid, name, mask, cap, costs))
            i += 4
        if pat_holy in data: print(f"  (note: a THolyChampionAbility instance still exists in region 0x{mbi.BaseAddress:X})")
    addr = (mbi.BaseAddress or 0) + mbi.RegionSize
for obj, aid, name, mask, cap, costs in sorted(found, key=lambda t: t[1]):
    print(f"ML object @0x{obj:X} id=0x{aid:02X} name={name!r} mask=0x{mask:X} cap={cap} costs={costs}")
print("windows:", windows_of(proc.pid))
print("process alive:", proc.poll() is None)
k32.TerminateProcess(hp, 0); print("terminated")
