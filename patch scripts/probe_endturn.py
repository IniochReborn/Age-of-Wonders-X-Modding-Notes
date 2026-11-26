#!/usr/bin/env python3
r"""Live diagnosis of the end-turn hotkey light patch (build_endturn_hotkey_light).

Run while the game is running, after pressing Ctrl+Enter / Ctrl+E on the map.

Reads (AoWEPACK.dll base + RVA):
  0x1E9A80 cave-entered count   -> 0 means the hotkey never reaches the
                                   patched keyboard sites (different path)
  0x1E9A84 click-replayed count -> 0 with entered>0 means the TTBWindow /
                                   TurnButton guards failed (fell back to
                                   plain EndTurn)
Also dumps the TurnButton's live lit byte (+0x13C), busy byte (+0x120) and
dirty byte (+0xA4) via AoWx.exe global 0x45A0CC.
"""
import ctypes, ctypes.wintypes as wt, subprocess, sys

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


def main():
    ps = pids()
    if not ps:
        print("AoWx.exe is not running."); return 1
    for pid in ps:
        h = k32.OpenProcess(0x410, False, pid)
        if not h:
            print(f"pid {pid}: cannot open"); continue
        m = modules(h)
        ep = m.get("aowepack.dll")
        print(f"=== pid {pid} ===  AoWEPACK base {hex(ep) if ep else 'NOT LOADED'}")
        if ep:
            print("  cave first byte : %s (want 0x53)" % hex(u8(h, ep + 0x160000) or 0))
            print("  cave entered    :", u32(h, ep + 0x1E9A80))
            print("  click replayed  :", u32(h, ep + 0x1E9A84))
        cell = u32(h, 0x45A0CC)
        print("  [0x45A0CC] cell :", hex(cell or 0))
        if cell:
            inst = u32(h, cell)
            print("  TTBWindow ctrl  :", hex(inst or 0))
            if inst:
                btn = u32(h, inst + 0x5C)
                print("  TurnButton      :", hex(btn or 0))
                if btn:
                    print("    lit  +0x13C :", u8(h, btn + 0x13C))
                    print("    busy +0x120 :", u8(h, btn + 0x120))
                    print("    dirty+0xA4  :", u8(h, btn + 0xA4))
        k32.CloseHandle(h)
    return 0


if __name__ == "__main__":
    sys.exit(main())
