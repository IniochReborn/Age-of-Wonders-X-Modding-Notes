"""Smoke test for patch_aowx_item_banner_hpmv: launch AoWx.exe (410 folder), wait,
scan memory for TItemBanner instances (VMT 0x406950) and print fields +0x44..+0x84
(the four new ones must be non-nil), list windows, terminate. --pid N attaches."""
import ctypes as C, ctypes.wintypes as W, struct, subprocess, sys, time, os
from bakpath import game_dir, game_file   # game folder = AOW_GAME_DIR or parent of patch scripts (2026-09-20)
GAME = game_dir()
EXE = os.path.join(GAME, "AoWx.exe"); VMT = 0x406950
args = sys.argv[1:]; WAIT = 35; PID = None
for i, a in enumerate(args):
    if a == "--pid": PID = int(args[i+1])
    if a == "--wait": WAIT = int(args[i+1])
k32 = C.WinDLL("kernel32", use_last_error=True); u32 = C.WinDLL("user32"); vp = C.c_void_p
k32.OpenProcess.restype = vp; k32.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
k32.ReadProcessMemory.argtypes = [vp, vp, vp, C.c_size_t, C.POINTER(C.c_size_t)]
k32.VirtualQueryEx.argtypes = [vp, vp, vp, C.c_size_t]; k32.VirtualQueryEx.restype = C.c_size_t
k32.TerminateProcess.argtypes = [vp, W.UINT]
class MBI(C.Structure):
    _fields_ = [("BaseAddress", vp), ("AllocationBase", vp), ("AllocationProtect", W.DWORD), ("PartitionId", W.WORD), ("RegionSize", C.c_size_t), ("State", W.DWORD), ("Protect", W.DWORD), ("Type", W.DWORD)]
def rpm(hp, a, n):
    b = C.create_string_buffer(n); r = C.c_size_t(); return b.raw[:r.value] if k32.ReadProcessMemory(hp, a, b, n, C.byref(r)) else b""
def windows_of(pid):
    t = []
    @C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
    def cb(h, lp):
        p = W.DWORD(); u32.GetWindowThreadProcessId(h, C.byref(p))
        if p.value == pid and u32.IsWindowVisible(h):
            n = u32.GetWindowTextLengthW(h); b = C.create_unicode_buffer(n+1); u32.GetWindowTextW(h, b, n+1); c = C.create_unicode_buffer(64); u32.GetClassNameW(h, c, 64); t.append((c.value, b.value))
        return True
    u32.EnumWindows(cb, 0); return t
if PID is None:
    proc = subprocess.Popen([EXE], cwd=GAME); PID = proc.pid; print("launched pid", PID); time.sleep(WAIT)
hp = k32.OpenProcess(0x0411, False, PID)
pat = struct.pack("<I", VMT); found = []; addr = 0; mbi = MBI()
while addr < 0x7FFF0000:
    if not k32.VirtualQueryEx(hp, addr, C.byref(mbi), C.sizeof(mbi)): break
    b0 = mbi.BaseAddress or 0
    if mbi.State == 0x1000 and mbi.Protect in (0x04, 0x08) and mbi.Type == 0x20000:
        data = rpm(hp, b0, mbi.RegionSize); i = 0
        while True:
            i = data.find(pat, i)
            if i < 0: break
            if i % 4 == 0 and i + 0x88 <= len(data):
                f = struct.unpack_from("<17I", data, i + 0x44)
                found.append((b0 + i, f))
            i += 4
    addr = b0 + mbi.RegionSize
for o, f in found:
    names = ["ItemNameLbl","IBannerPopup","AttackIcon","DefenseIcon","DamageIcon","ResistanceIcon","Attack","Defense","Damage","Resistance","DrawBox","AbLB","AbVSB","HitsIcon","MovesIcon","Hits","Moves"]
    print(f"TItemBanner @{o:#x}:"); print("   " + ", ".join(f"{n}={v:#x}" for n, v in zip(names, f)))
    for n, v in zip(names[13:], f[13:]):
        vm = struct.unpack("<I", rpm(hp, v, 4))[0] if v else 0
        print(f"   {n}: obj {v:#x} vmt {vm:#x}")
    # geometry: TAoWComponent +0x7C width, +0x80 height, +0x84 left, +0x88 top, +0x75 visible
    for n, v in zip(names, f):
        if n in ("IBannerPopup", "AbLB", "AbVSB", "DrawBox", "Attack", "HitsIcon", "MovesIcon") and v:
            g = rpm(hp, v, 0x90)
            if len(g) == 0x90:
                w, h, l, t = struct.unpack_from("<IIII", g, 0x7C); vis = g[0x75]
                print(f"   {n:12} left={l:<4} top={t:<4} width={w:<4} height={h:<4} visible={vis}")
print("instances:", len(found)); print("windows:", windows_of(PID))
if "--keep" not in args: k32.TerminateProcess(hp, 0); print("terminated")

