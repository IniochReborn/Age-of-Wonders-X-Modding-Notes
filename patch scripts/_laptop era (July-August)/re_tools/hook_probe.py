# -*- coding: utf-8 -*-
"""Verify fix1/fix2 hook bytes in the loaded AoWEPACK of running AoWx processes."""
import ctypes
import ctypes.wintypes as wt
import subprocess

k32 = ctypes.windll.kernel32
psapi = ctypes.windll.psapi


def rd(h, addr, n):
    buf = ctypes.create_string_buffer(n)
    got = ctypes.c_size_t()
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, n, ctypes.byref(got)):
        return None
    return buf.raw


out = subprocess.check_output(
    ["tasklist", "/FI", "IMAGENAME eq AoWx.exe", "/FO", "CSV", "/NH"], text=True)
pids = []
for line in out.splitlines():
    parts = [p.strip('"') for p in line.split('","')]
    if len(parts) >= 2 and parts[0].lower() == "aowx.exe":
        pids.append(int(parts[1]))

for pid in pids:
    h = k32.OpenProcess(0x410, False, pid)
    mods = (wt.HMODULE * 1024)()
    needed = wt.DWORD()
    psapi.EnumProcessModulesEx(h, mods, ctypes.sizeof(mods), ctypes.byref(needed), 0x01)
    base = None
    nb = ctypes.create_string_buffer(260)
    for i in range(needed.value // ctypes.sizeof(wt.HMODULE)):
        psapi.GetModuleBaseNameA(h, mods[i], nb, 260)
        if nb.value.lower() == b"aowepack.dll":
            base = mods[i]
            break
    print("pid %d base 0x%X" % (pid, base))
    for name, rva, n in (("fix2 A @428B2", 0x428B2, 5),
                         ("fix2 B @427D1", 0x427D1, 6),
                         ("fix2 cave @112100", 0x112100, 8),
                         ("fix1 MoveVisible", 0x48198, 6),
                         ("diag5 CRE3 MvAEx", 0x4A318, 6),   # fix3 reverted 8/9; site now H12
                         ("diag5 cave @110400", 0x110400, 8),
                         ("fix4 join @8FC24", 0x8FC24, 7),
                         ("fix4 cave @112200", 0x112200, 8),
                         ("diag6 CRE5 @93078", 0x93078, 6),
                         ("fix8 movedraw @478ED (9090909090=on)", 0x478ED, 5),
                         ("fix cave @112280 (clear)", 0x112280, 8)):
        b = rd(h, base + rva, n)
        print("  %-18s %s" % (name, b.hex() if b else "READ FAIL"))

    def u32(addr):
        b = rd(h, addr, 4)
        return int.from_bytes(b, "little") if b else 0

    mapp = u32(base + 0x1FA040)
    holder = u32(mapp + 0x240) if mapp else 0
    pcc = u32(holder + 0x1C) if holder else 0
    lst = u32(pcc + 0xC) if pcc else 0
    inner = u32(lst + 8) if lst else 0
    data = u32(inner + 4) if inner else 0
    sts = []
    for idx in range(6):
        recp = u32(data + idx * 4) if data else 0
        st = rd(h, recp + 8, 1) if recp else None
        sts.append(st[0] if st else -1)
    print("  comm statuses p0..p5: %s  (0 Local, 1 Remote, 2 Global)" % sts)
    k32.CloseHandle(h)
