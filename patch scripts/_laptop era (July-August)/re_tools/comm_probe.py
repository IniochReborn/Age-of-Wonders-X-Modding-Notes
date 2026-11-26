# -*- coding: utf-8 -*-
"""Live probe for the noanim desync fix: reads each running AoWx.exe and dumps
(1) whether the MoveVisible hook + cave are present in the loaded AoWEPACK,
(2) [map+0x239] mode byte, pcc chain, and per-player communication status
    (rec = [[[pcc+0xC]+8]+4][idx], status = byte [rec+8]; 0 Local 1 Remote 2 Global).
Run while instances are alive (frozen at OOS is fine)."""
import ctypes
import ctypes.wintypes as wt

k32 = ctypes.windll.kernel32
psapi = ctypes.windll.psapi
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
LIST_MODULES_32BIT = 0x01
PREF = 0x55700000


def find_pids():
    import subprocess
    out = subprocess.check_output(
        ["tasklist", "/FI", "IMAGENAME eq AoWx.exe", "/FO", "CSV", "/NH"], text=True)
    pids = []
    for line in out.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) >= 2 and parts[0].lower() == "aowx.exe":
            pids.append(int(parts[1]))
    return pids


def module_base(h, want=b"aowepack.dll"):
    mods = (wt.HMODULE * 1024)()
    needed = wt.DWORD()
    if not psapi.EnumProcessModulesEx(h, mods, ctypes.sizeof(mods),
                                      ctypes.byref(needed), LIST_MODULES_32BIT):
        return None
    buf = ctypes.create_string_buffer(260)
    for i in range(needed.value // ctypes.sizeof(wt.HMODULE)):
        psapi.GetModuleBaseNameA(h, mods[i], buf, 260)
        if buf.value.lower() == want:
            return mods[i]
    return None


def rd(h, addr, n):
    buf = ctypes.create_string_buffer(n)
    got = ctypes.c_size_t()
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, n, ctypes.byref(got)):
        return None
    return buf.raw


def u32(h, addr):
    b = rd(h, addr, 4)
    return int.from_bytes(b, 'little') if b else None


for pid in find_pids():
    h = k32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
    base = module_base(h)
    if not base:
        print("pid %d: no AoWEPACK" % pid)
        continue
    delta = base - PREF
    print("\n===== pid %d  AoWEPACK base 0x%X (delta %+#x) =====" % (pid, base, delta))
    hook = rd(h, base + 0x48198, 6)
    cave = rd(h, base + 0x112000, 8)
    print("  MoveVisible entry bytes: %s  (%s)" % (
        hook.hex(), "HOOK PRESENT" if hook[0] == 0xE9 else "VANILLA/UNPATCHED!"))
    print("  cave @+0x112000:         %s  (%s)" % (
        cave.hex(), "present" if cave[:4] == bytes.fromhex("505251E8") else "MISSING!"))
    if hook[0] == 0xE9:
        tgt = base + 0x48198 + 5 + int.from_bytes(hook[1:5], 'little', signed=True)
        print("  hook jmp target: 0x%X (expect cave 0x%X)" % (tgt, base + 0x112000))
    mapp = u32(h, base + 0x1FA040)
    print("  map = 0x%X" % (mapp or 0))
    if not mapp:
        continue
    mode = rd(h, mapp + 0x239, 1)
    print("  mode byte [map+0x239] = %d" % mode[0])
    holder = u32(h, mapp + 0x240)
    print("  [map+0x240] = 0x%X" % (holder or 0))
    if not holder:
        continue
    pcc = u32(h, holder + 0x1C)
    print("  pcc [holder+0x1C] = 0x%X" % (pcc or 0))
    if not pcc:
        continue
    lst = u32(h, pcc + 0xC)
    inner = u32(h, lst + 8) if lst else None
    data = u32(h, inner + 4) if inner else None
    print("  list=0x%X inner=0x%X data=0x%X" % (lst or 0, inner or 0, data or 0))
    if not data:
        continue
    names = {0: "Local", 1: "Remote", 2: "Global"}
    for idx in range(9):
        recp = u32(h, data + idx * 4)
        if not recp or recp > 0x7FFF0000:
            print("  player %d: rec nil/bad (0x%X)" % (idx, recp or 0))
            continue
        st = rd(h, recp + 8, 1)
        print("  player %d: rec=0x%X status=%d (%s)" % (
            idx, recp, st[0], names.get(st[0], "?")))
    k32.CloseHandle(h)
