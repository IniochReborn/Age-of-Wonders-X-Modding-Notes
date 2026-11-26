#!/usr/bin/env python3
r"""Live diagnosis of the power-slider wheel patch (build_wheel_power_slider).

Run while the game is running, ideally with the Power Distribution window
open. Samples twice (2s apart) so you can spin the wheel between samples.

Reads (module base + RVA):
  aowInt.dpl 0x3E100 g_hover      0x3E104 g_facenext
             0x3E108 g_faceprev   0x3E10C g_pslider   <- must be nonzero
                                                         while the dlg is open
  aowInt.dpl 0x23600 CLR2 cave (0x53)  0x23680 SLD cave (0x53)
             0x23700 WheelPower (0x55)
  aowInt.dpl 0x06494 H_CLR hook jmp target
             0x1FA5C H_SLD hook (0xE9 = hooked H-scrollbar CheckMouseMove)
  VCL30.dpl  0xE7140 G_PENDING (queued notches)   0xE7148 G_THREADED
             0xA8A00 pump cave first byte (0x60)  0xA8B00 LL cave (0x55)

How to read it:
  g_pslider == 0 with the dlg open          -> latch scan fails (CLR2)
  g_pslider != 0, PENDING grows as you spin -> LL queues but pump never
                                               drains (modal loop bypasses
                                               TApplication.ProcessMessage)
  g_pslider != 0, PENDING stays 0           -> LL hook never sees the wheel
                                               (hook order / AHK first)
"""
import ctypes, ctypes.wintypes as wt, subprocess, sys, time

k32 = ctypes.windll.kernel32
psapi = ctypes.windll.psapi


def pids(name="AoWx.exe"):
    out = subprocess.check_output(["tasklist", "/FI", f"IMAGENAME eq {name}", "/FO", "CSV", "/NH"], text=True)
    r = []
    for line in out.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) >= 2 and parts[0].lower() == name.lower():
            r.append(int(parts[1]))
    return r


def modules(h):
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


def u8(h, a):
    b = rd(h, a, 1)
    return b[0] if b else None


def sample(h, aow, vcl, tag):
    print(f"--- sample {tag} ---")
    if aow:
        print("  g_hover    : %s" % hex(u32(h, aow + 0x3E100) or 0))
        print("  g_facenext : %s" % hex(u32(h, aow + 0x3E104) or 0))
        print("  g_pslider  : %s" % hex(u32(h, aow + 0x3E10C) or 0))
        unext = u32(h, aow + 0x3E140) or 0
        uprev = u32(h, aow + 0x3E144) or 0
        print("  g_unext    : %s   g_uprev : %s   g_uarmed : %s"
              % (hex(unext), hex(uprev), u32(h, aow + 0x3E148)))
        for tag, btn in (("PNext", unext), ("PPrev", uprev)):
            if not btn: continue
            par = u32(h, btn + 0x10C) or 0
            if not par: continue
            print("    %s btn rect l=%s t=%s w=%s h=%s | parent l=%s t=%s w=%s h=%s"
                  % (tag, u32(h, btn+0x84), u32(h, btn+0x88), u32(h, btn+0x7C), u32(h, btn+0x80),
                     u32(h, par+0x84), u32(h, par+0x88), u32(h, par+0x7C), u32(h, par+0x80)))
    if vcl:
        print("  G_PENDING  : %s" % (u32(h, vcl + 0xE7140),))
        print("  G_THREADED : %s" % (u32(h, vcl + 0xE7148),))


def main():
    ps = pids()
    if not ps:
        print("AoWx.exe is not running."); return 1
    for pid in ps:
        h = k32.OpenProcess(0x410, False, pid)
        if not h:
            print(f"pid {pid}: cannot open"); continue
        m = modules(h)
        aow = m.get("aowint.dpl"); vcl = m.get("vcl30.dpl")
        print(f"=== pid {pid} ===")
        print(f"  aowInt base {hex(aow) if aow else 'NOT LOADED'} | VCL30 base {hex(vcl) if vcl else 'NOT LOADED'}")
        if aow:
            print("  CLR2 cave byte   : %s (want 0x53)" % hex(u8(h, aow + 0x23600) or 0))
            print("  SLD cave byte    : %s (want 0x53)" % hex(u8(h, aow + 0x23680) or 0))
            print("  WheelPower byte  : %s (want 0x55)" % hex(u8(h, aow + 0x23700) or 0))
            print("  H_SLD first byte : %s (want 0xe9 = hooked)" % hex(u8(h, aow + 0x1FA5C) or 0))
            hook = rd(h, aow + 0x6494, 6)
            if hook and hook[0] == 0xE9:
                rel = int.from_bytes(hook[1:5], 'little', signed=True)
                print("  H_CLR jmp target : base+%s (CLR2=+0x23600, old CLR=+0x22800)"
                      % hex(0x6494 + 5 + rel))
            else:
                print("  H_CLR bytes      : %s (NOT HOOKED?)" % (hook.hex() if hook else '??'))
        if vcl:
            print("  pump cave byte   : %s (want 0x60)" % hex(u8(h, vcl + 0xA8A00) or 0))
            print("  LL cave byte     : %s (want 0x55)" % hex(u8(h, vcl + 0xA8B00) or 0))
            print("  LL hook handle   : %s" % hex(u32(h, vcl + 0xE27F8) or 0))
        sample(h, aow, vcl, "1")
        print("  ... spin the wheel now (2s) ...")
        time.sleep(2)
        sample(h, aow, vcl, "2")
        k32.CloseHandle(h)
    return 0


if __name__ == "__main__":
    sys.exit(main())
