#!/usr/bin/env python3
r"""Scan the RUNNING AoWx.exe for THero/TLeader instances and dump their item
containers + ability record chains. Finds combat copies vs originals without
needing the diag patch."""
import ctypes, ctypes.wintypes as wt, subprocess, sys, struct, os

k32 = ctypes.windll.kernel32
psapi = ctypes.windll.psapi
PREF = 0x55700000
THERO, TLEADER, TITEM = 0x55711FEC, 0x55712238, 0x5570FAFC

scratch = r'C:\Users\<user>\AppData\Local\Temp\claude\C--Users-<user>-Desktop-Age-of-Wonders-X---Claude\af9a924c-2966-4ffc-8efd-4b983e546f21\scratchpad'
sys.path.insert(0, scratch)
from aow_pe import PE, find_vmts

GAME = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


class MBI(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_void_p), ("AllocationBase", ctypes.c_void_p),
                ("AllocationProtect", wt.DWORD), ("RegionSize", ctypes.c_size_t),
                ("State", wt.DWORD), ("Protect", wt.DWORD), ("Type", wt.DWORD)]


def pids(name="AoWx.exe"):
    out = subprocess.check_output(["tasklist", "/FI", f"IMAGENAME eq {name}", "/FO", "CSV", "/NH"], text=True)
    return [int(l.split('","')[1]) for l in out.splitlines() if l.lower().startswith('"' + name.lower()[:6])]


def modules(h):
    mods = (ctypes.c_void_p * 2048)(); need = wt.DWORD()
    psapi.EnumProcessModulesEx(h, mods, ctypes.sizeof(mods), ctypes.byref(need), 0x03)
    out = {}
    nb = ctypes.create_string_buffer(260)
    for i in range(need.value // 4):
        v = mods[i]
        if not v: continue
        psapi.GetModuleBaseNameA(h, ctypes.c_void_p(v), nb, 260)
        out[nb.value.lower().decode()] = v
    return out


def rd(h, a, n):
    buf = ctypes.create_string_buffer(n); got = ctypes.c_size_t()
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(a), buf, n, ctypes.byref(got)):
        return None
    return buf.raw[:got.value]


def u32(h, a):
    b = rd(h, a, 4)
    return struct.unpack('<I', b)[0] if b and len(b) == 4 else None


def main():
    ps = pids()
    if not ps:
        print("AoWx.exe not running"); return 1
    pe = PE(os.path.join(GAME, 'AoWEPACK.dll'))
    names = {v: n for v, (n, p, s) in find_vmts(pe).items()}
    def cls(h, obj, delta):
        if not obj: return 'nil'
        v = u32(h, obj)
        return names.get((v or 0) - delta, 'vmt=%08X' % (v or 0))
    pid = ps[0]
    h = k32.OpenProcess(0x410, False, pid)
    m = modules(h)
    base = m.get('aowepack.dll')
    delta = base - PREF
    thero, tleader, titem = THERO + delta, TLEADER + delta, TITEM + delta
    print("pid %d, AoWEPACK base %X (delta %X)" % (pid, base, delta))
    # scan committed RW private memory for hero VMT dwords at 4-aligned offsets
    hits = []
    addr = 0x10000
    pat_h = struct.pack('<I', thero); pat_l = struct.pack('<I', tleader)
    while addr < 0x7F000000:
        mbi = MBI()
        if not ctypes.windll.kernel32.VirtualQueryEx(h, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
            break
        size = mbi.RegionSize
        if mbi.State == 0x1000 and mbi.Protect in (0x04, 0x08) and size < 0x4000000:
            data = rd(h, mbi.BaseAddress, size)
            if data:
                for pat, tag in ((pat_h, 'THero'), (pat_l, 'TLeader')):
                    i = -1
                    while True:
                        i = data.find(pat, i + 1)
                        if i < 0: break
                        if i % 4 == 0:
                            hits.append((mbi.BaseAddress + i, tag))
        addr = mbi.BaseAddress + size
    print(len(hits), "hero-object candidates")
    for obj, tag in hits[:40]:
        print("== %s @ %08X" % (tag, obj))
        node = u32(h, obj + 0x10); chain = []
        n = 0
        while node and n < 24:
            chain.append(cls(h, node, delta)); node = u32(h, node + 8); n += 1
        print("   own records:", ', '.join(chain) if chain else '(none)')
        for off, t in ((0x70, 'items'), (0x74, 'inventory')):
            c = u32(h, obj + off)
            line = "   +0x%X %s: c=%08X(%s)" % (off, t, c or 0, cls(h, c, delta))
            if c:
                lst = u32(h, c + 8)
                if lst:
                    data_p, cnt = u32(h, lst + 4), u32(h, lst + 8)
                    line += " count=%s" % cnt
                    if data_p and cnt and cnt <= 16:
                        for i in range(cnt):
                            it = u32(h, data_p + i * 4)
                            line += "\n      item[%d]=%08X(%s)" % (i, it or 0, cls(h, it, delta))
                            if it:
                                rn = u32(h, it + 0x10); rr = []
                                k = 0
                                while rn and k < 12:
                                    rid = '?'
                                    rr.append('%s lvl=%s' % (cls(h, rn, delta), (u32(h, rn + 0xC) or 0) & 0xFF))
                                    rn = u32(h, rn + 8); k += 1
                                if rr: line += " recs: " + '; '.join(rr)
            print(line)
    k32.CloseHandle(h)
    return 0


if __name__ == "__main__":
    sys.exit(main())
