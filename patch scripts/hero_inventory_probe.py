#!/usr/bin/env python3
r"""
Live dump of every THero/TLeader in a running AoWx.exe: owner, name, worn items [+0x70], backpack [+0x74]
(item type, scroll spell slots).  Finds the objects by scanning committed memory for their (rebased) VMT pointers.
Diagnostic for the AI-scroll-spell investigation (2026-10-30).  Usage: py -3.10 hero_inventory_probe.py
"""
import ctypes, ctypes.wintypes as wt, struct, sys
from ai_scroll_probe import pid_of

LINK = 0x55700000
VMT = {"THero": 0x55711FEC, "TLeader": 0x55712238}
TITEM = 0x5570FAFC
k32 = ctypes.windll.kernel32
psapi = ctypes.windll.psapi
k32.OpenProcess.restype = wt.HANDLE
k32.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
                                  ctypes.POINTER(ctypes.c_size_t)]
psapi.EnumProcessModulesEx.argtypes = [wt.HANDLE, ctypes.POINTER(ctypes.c_void_p), wt.DWORD,
                                       ctypes.POINTER(wt.DWORD), wt.DWORD]
psapi.GetModuleBaseNameW.argtypes = [wt.HANDLE, ctypes.c_void_p, wt.LPWSTR, wt.DWORD]


class MBI(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_void_p), ("AllocationBase", ctypes.c_void_p), ("AllocationProtect", wt.DWORD),
                ("PartitionId", wt.WORD), ("RegionSize", ctypes.c_size_t), ("State", wt.DWORD),
                ("Protect", wt.DWORD), ("Type", wt.DWORD)]


k32.VirtualQueryEx.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.POINTER(MBI), ctypes.c_size_t]


def main():
    pid = pid_of()
    if not pid:
        print("AoWx.exe not running"); return 1
    h = k32.OpenProcess(0x0410, False, pid)
    mods = (ctypes.c_void_p * 1024)(); need = wt.DWORD()
    psapi.EnumProcessModulesEx(h, mods, ctypes.sizeof(mods), ctypes.byref(need), 1)
    base = None
    for m in mods[:need.value // 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else need.value // 4]:
        nm = ctypes.create_unicode_buffer(260); psapi.GetModuleBaseNameW(h, m, nm, 260)
        if nm.value.lower() == "aowepack.dll":
            base = m
    d = base - LINK
    rv = {name: v + d for name, v in VMT.items()}
    titem = TITEM + d

    def rd(a, n):
        buf = ctypes.create_string_buffer(n); got = ctypes.c_size_t()
        if not k32.ReadProcessMemory(h, ctypes.c_void_p(a), buf, n, ctypes.byref(got)):
            return None
        return buf.raw

    def u32(a):
        b = rd(a, 4)
        return struct.unpack("<I", b)[0] if b else None

    def astr(p):
        if not p:
            return ""
        n = u32(p - 4)
        if not n or n > 200:
            return "?"
        return (rd(p, n) or b"").decode("latin1")

    found = []
    addr = 0x10000
    mbi = MBI()
    pats = {struct.pack("<I", v): k for k, v in rv.items()}
    while addr < 0x7FFF0000 and k32.VirtualQueryEx(h, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
        size = mbi.RegionSize
        if mbi.State == 0x1000 and mbi.Protect in (0x04, 0x40) and mbi.Type == 0x20000:   # private RW
            blob = rd(addr, size)
            if blob:
                for pat, k in pats.items():
                    i = blob.find(pat)
                    while i >= 0:
                        if i % 4 == 0:
                            found.append((addr + i, k))
                        i = blob.find(pat, i + 4)
        addr += size
    print("AoWEPACK base %#x; %d hero objects" % (base, len(found)))
    for obj, k in found:
        inv = u32(obj + 0x74); worn = u32(obj + 0x70)
        owner = (rd(obj + 0x24, 1) or b"\0")[0]
        print("%s @%#x owner %d name '%s' title '%s'" % (k, obj, owner, astr(u32(obj + 0x60)), astr(u32(obj + 0x64))))
        for lbl, cont in (("worn", worn), ("pack", inv)):
            if not cont:
                print("   %s: nil" % lbl); continue
            lst = u32(cont + 8)
            if not lst:
                print("   %s: container %#x, list nil" % (lbl, cont)); continue
            cnt, arr = u32(lst + 8), u32(lst + 4)
            items = []
            for j in range(min(cnt or 0, 40)):
                it = u32(arr + 4 * j)
                if not it:
                    continue
                vm = u32(it)
                ty = (rd(it + 0x34, 1) or b"\xff")[0]
                sp = struct.unpack("<7I", rd(it + 0x38, 4) + rd(it + 0x4C, 24))
                items.append("%s type %d name '%s' spells %s" % ("TItem" if vm == titem else "vmt %#x" % vm, ty,
                                                                 astr(u32(it + 0x18)), list(sp)))
            print("   %s: container %#x vmt %#x, %d item(s)" % (lbl, cont, u32(cont), cnt or 0))
            for s in items:
                print("      " + s)
    return 0


if __name__ == "__main__":
    sys.exit(main())
