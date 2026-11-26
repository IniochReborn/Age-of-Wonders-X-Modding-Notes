#!/usr/bin/env python3
r"""Read the mouse-wheel diagnostic counters out of the RUNNING AoWx.exe.

Pair with the --diag builds of build_wheel_vcl_pump.py / build_wheel_aowint.py.
Start the game, open the map-select or load window, spin the wheel over the
list, then run this while the game is still running.

Counters (module base + RVA, so rebasing is handled):
  VCL30.dpl  0xE27D4 : +0 SetWindowsHookEx(WH_MOUSE_LL) result (0 = FAILED)
                       +4 low-level hook callback hits (any mouse input)
                       +8 low-level WHEEL events seen
  VCL30.dpl  0xE27E0 : +0 pump hook hits (every peeked message)
                       +4 WM_MOUSEWHEEL messages seen
                       +8 aowInt.dpl located
                       +C helper actually called
                       +10 last wParam (HIWORD = signed wheel delta)
  aowInt.dpl 0x3E110 : +0 mouse-move sweeps (CLR hook)
                       +4 cursor-inside-a-listbox hits (SET hook)
                       +8 WheelScroll entered
                       +C scroll performed
                       +10 last hovered TAOWListBox
             0x3E100 : g_hover (live)

Reading the numbers:
  pump=0                  -> the pump hook never runs (wrong hook site)
  pump>0, wheel=0         -> the app never receives WM_MOUSEWHEEL
  wheel>0, found=0        -> aowInt.dpl not loaded under that name
  found>0, called=0       -> helper signature byte mismatch (patch not applied)
  called>0, entered=0     -> call didn't land (bad RVA)
  entered>0, hover==0     -> hover tracking never fires (SET hook not reached)
  ok>0 but no visual      -> scroll applied; repaint/plumbing is the problem
"""
import ctypes, ctypes.wintypes as wt, subprocess, sys

k32 = ctypes.windll.kernel32
psapi = ctypes.windll.psapi

VCL_CNT_RVA = 0xE27E0
AOW_CNT_RVA = 0x3E110
AOW_HOVER_RVA = 0x3E100


def pids(name="AoWx.exe"):
    out = subprocess.check_output(["tasklist", "/FI", f"IMAGENAME eq {name}", "/FO", "CSV", "/NH"], text=True)
    r = []
    for line in out.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) >= 2 and parts[0].lower() == name.lower():
            r.append(int(parts[1]))
    return r


def modules(h):
    # HMODULE entries must be passed back as void* — a plain int can overflow
    # ctypes' signed-int conversion for bases above 0x7FFFFFFF.
    mods = (ctypes.c_void_p * 2048)()
    need = wt.DWORD()
    psapi.EnumProcessModulesEx(h, mods, ctypes.sizeof(mods), ctypes.byref(need), 0x03)
    out = {}
    nb = ctypes.create_string_buffer(260)
    for i in range(need.value // ctypes.sizeof(ctypes.c_void_p)):
        v = mods[i]
        if not v: continue
        psapi.GetModuleBaseNameA(h, ctypes.c_void_p(v), nb, 260)
        out[nb.value.lower().decode()] = v
    return out


def rd(h, addr, n=4):
    buf = ctypes.create_string_buffer(n); got = ctypes.c_size_t()
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, n, ctypes.byref(got)):
        return None
    return buf.raw


def u32(h, a):
    b = rd(h, a, 4)
    return int.from_bytes(b, 'little') if b else None


def main():
    ps = pids()
    if not ps:
        print("AoWx.exe is not running — start the game first."); return 1
    for pid in ps:
        h = k32.OpenProcess(0x410, False, pid)
        if not h:
            print(f"pid {pid}: cannot open (try running as admin)"); continue
        m = modules(h)
        vcl = m.get("vcl30.dpl"); aow = m.get("aowint.dpl")
        print(f"=== pid {pid} ===")
        print(f"  VCL30.dpl  base {hex(vcl) if vcl else 'NOT LOADED'}")
        print(f"  aowInt.dpl base {hex(aow) if aow else 'NOT LOADED'}")
        if vcl:
            ll = [u32(h, vcl + 0xE27D4 + i*4) for i in range(3)]
            print(f"  LL hook handle : {hex(ll[0] or 0)}  {'INSTALL FAILED' if not ll[0] else 'installed'}")
            print(f"  LL callbacks   : {ll[1]}")
            print(f"  LL wheel events: {ll[2]}")
            c = [u32(h, vcl + VCL_CNT_RVA + i*4) for i in range(5)]
            print(f"  pump hits      : {c[0]}")
            print(f"  wheel msgs     : {c[1]}")
            print(f"  aowInt found   : {c[2]}")
            print(f"  helper called  : {c[3]}")
            print(f"  last wParam    : {hex(c[4] or 0)}  (delta={ctypes.c_short((c[4] or 0) >> 16).value})")
        if aow:
            d = [u32(h, aow + AOW_CNT_RVA + i*4) for i in range(5)]
            print(f"  move sweeps    : {d[0]}")
            print(f"  inside-listbox : {d[1]}")
            print(f"  WheelScroll in : {d[2]}")
            print(f"  scrolled ok    : {d[3]}")
            print(f"  last listbox   : {hex(d[4] or 0)}")
            e = [u32(h, aow + AOW_CNT_RVA + 0x14 + i*4) for i in range(2)]
            print(f"  no-scrollbar fb: {e[0]}   (list had no linked TAOWVScrollBar)")
            print(f"  wheel w/o hover: {e[1]}   (g_hover was 0 at wheel time)")
            print(f"  g_hover (live) : {hex(u32(h, aow + AOW_HOVER_RVA) or 0)}")
        k32.CloseHandle(h)
    return 0


if __name__ == "__main__":
    sys.exit(main())
