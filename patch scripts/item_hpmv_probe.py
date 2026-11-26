"""End-to-end check for patch_item_hpmv_use_v1: launch AoWx.exe from the 410
folder (or --pid N to attach), wait for the item library to load, scan process
memory for TItem objects (VMT = AoWEPACK base + 0xFAFC) and print every item
whose HP (+0x4A) or MV (+0x4B) byte is non-zero, plus any names given with
--name.  Terminates the game unless --keep."""
import ctypes as C, ctypes.wintypes as W, struct, subprocess, sys, time, os
from bakpath import game_dir, game_file   # game folder = AOW_GAME_DIR or parent of patch scripts (2026-09-20)

GAME = game_dir()
EXE = os.path.join(GAME, "AoWx.exe")
TITEM_RVA = 0x5570FAFC - 0x55700000
args = sys.argv[1:]
WAIT = 30; PID = None; KEEP = "--keep" in args; NAMES = []
for i, a in enumerate(args):
    if a == "--pid": PID = int(args[i+1])
    if a == "--wait": WAIT = int(args[i+1])
    if a == "--name": NAMES.append(args[i+1].lower())

k32 = C.WinDLL("kernel32", use_last_error=True); psapi = C.WinDLL("psapi", use_last_error=True); u32 = C.WinDLL("user32")
vp = C.c_void_p
k32.OpenProcess.restype = vp; k32.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
k32.ReadProcessMemory.argtypes = [vp, vp, vp, C.c_size_t, C.POINTER(C.c_size_t)]
k32.VirtualQueryEx.argtypes = [vp, vp, vp, C.c_size_t]; k32.VirtualQueryEx.restype = C.c_size_t
k32.TerminateProcess.argtypes = [vp, W.UINT]
psapi.EnumProcessModulesEx.argtypes = [vp, vp, W.DWORD, C.POINTER(W.DWORD), W.DWORD]
psapi.GetModuleBaseNameW.argtypes = [vp, vp, W.LPWSTR, W.DWORD]
class MBI(C.Structure):
    _fields_ = [("BaseAddress", vp), ("AllocationBase", vp), ("AllocationProtect", W.DWORD), ("PartitionId", W.WORD),
                ("RegionSize", C.c_size_t), ("State", W.DWORD), ("Protect", W.DWORD), ("Type", W.DWORD)]
def rpm(hp, addr, size):
    buf = C.create_string_buffer(size); n = C.c_size_t()
    return buf.raw[:n.value] if k32.ReadProcessMemory(hp, addr, buf, size, C.byref(n)) else b""
def modules(hp):
    arr = (vp * 512)(); need = W.DWORD(); psapi.EnumProcessModulesEx(hp, arr, C.sizeof(arr), C.byref(need), 0x01)
    out = {}
    for i in range(need.value // C.sizeof(vp)):
        nm = C.create_unicode_buffer(260); psapi.GetModuleBaseNameW(hp, arr[i], nm, 260); out[nm.value.lower()] = arr[i]
    return out
def windows_of(pid):
    titles = []
    @C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
    def cb(hwnd, lp):
        p = W.DWORD(); u32.GetWindowThreadProcessId(hwnd, C.byref(p))
        if p.value == pid and u32.IsWindowVisible(hwnd):
            n = u32.GetWindowTextLengthW(hwnd); b = C.create_unicode_buffer(n+1); u32.GetWindowTextW(hwnd, b, n+1)
            cls = C.create_unicode_buffer(64); u32.GetClassNameW(hwnd, cls, 64); titles.append((cls.value, b.value))
        return True
    u32.EnumWindows(cb, 0); return titles

if PID is None:
    proc = subprocess.Popen([EXE], cwd=GAME); PID = proc.pid; print("launched pid", PID); time.sleep(WAIT)
hp = k32.OpenProcess(0x0411, False, PID)
mods = modules(hp); base = mods.get("aowepack.dll")
if not base: print("!! AoWEPACK not loaded / process gone"); sys.exit(1)
vmt = base + TITEM_RVA; pat = struct.pack("<I", vmt); print(f"AoWEPACK base 0x{base:X}, TItem VMT 0x{vmt:X}")
found = []; addr = 0; mbi = MBI(); nitems = 0
while addr < 0x7FFF0000:
    if not k32.VirtualQueryEx(hp, addr, C.byref(mbi), C.sizeof(mbi)): break
    b0 = mbi.BaseAddress or 0
    if mbi.State == 0x1000 and mbi.Protect in (0x04, 0x08) and mbi.Type == 0x20000:
        data = rpm(hp, b0, mbi.RegionSize); i = 0
        while True:
            i = data.find(pat, i)
            if i < 0: break
            if i % 4 == 0 and i + 0x4C <= len(data):
                rec = data[i:i+0x4C]; nitems += 1
                nameptr = struct.unpack_from("<I", rec, 0x18)[0]
                name = rpm(hp, nameptr, 40).split(b"\0")[0].decode("latin1") if nameptr else ""
                hpv, mvv = struct.unpack_from("<bb", rec, 0x4A); typ = rec[0x34]
                atk, df, dm, rs = struct.unpack_from("<bbbb", rec, 0x46)
                if hpv or mvv or name.lower() in NAMES:
                    found.append((b0+i, name, typ, atk, df, dm, rs, hpv, mvv))
            i += 4
    addr = b0 + mbi.RegionSize
print(f"TItem objects scanned: {nitems}")
for o, name, typ, atk, df, dm, rs, hpv, mvv in sorted(found, key=lambda t: t[1]):
    print(f"  @0x{o:X} {name!r:32} type={typ} atk={atk} def={df} dam={dm} res={rs} HP={hpv} MV={mvv}")
print("windows:", windows_of(PID))
if not KEEP: k32.TerminateProcess(hp, 0); print("terminated")
