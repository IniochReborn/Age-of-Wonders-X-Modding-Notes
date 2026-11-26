#!/usr/bin/env python3
r"""Find who references the given object addresses in the running AoWx.exe.
Usage: py ref_probe.py 0A3301B4 022C6D5C ...
For each dword hit, walks back up to 0x400 bytes to find the owning object's
VMT (classified via AoWEPACK class names or module ranges) + field offset."""
import ctypes, ctypes.wintypes as wt, subprocess, struct, sys, os, re

k32 = ctypes.windll.kernel32
psapi = ctypes.windll.psapi
GAME = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


def pids(name="AoWx.exe"):
    out = subprocess.check_output(
        ["tasklist", "/FI", f"IMAGENAME eq {name}", "/FO", "CSV", "/NH"], text=True)
    return [int(p[1]) for p in
            ([q.strip('"') for q in l.split('","')] for l in out.splitlines())
            if len(p) >= 2 and p[0].lower() == name.lower()]


def modules(h):
    mods = (ctypes.c_void_p * 2048)()
    need = wt.DWORD()
    psapi.EnumProcessModulesEx(h, mods, ctypes.sizeof(mods), ctypes.byref(need), 0x03)
    out = []
    nb = ctypes.create_string_buffer(260)

    class MODINFO(ctypes.Structure):
        _fields_ = [("lpBaseOfDll", ctypes.c_void_p), ("SizeOfImage", wt.DWORD),
                    ("EntryPoint", ctypes.c_void_p)]
    mi = MODINFO()
    for i in range(need.value // ctypes.sizeof(ctypes.c_void_p)):
        v = mods[i]
        if not v:
            continue
        psapi.GetModuleBaseNameA(h, ctypes.c_void_p(v), nb, 260)
        psapi.GetModuleInformation(h, ctypes.c_void_p(v), ctypes.byref(mi), ctypes.sizeof(mi))
        out.append((v, v + mi.SizeOfImage, nb.value.decode()))
    return out


def rd(h, a, n):
    buf = ctypes.create_string_buffer(n)
    got = ctypes.c_size_t()
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(a), buf, n, ctypes.byref(got)):
        return None
    return buf.raw[:got.value]


def u32(h, a):
    b = rd(h, a, 4)
    return struct.unpack('<I', b)[0] if b and len(b) == 4 else None


class MBI(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_void_p), ("AllocationBase", ctypes.c_void_p),
                ("AllocationProtect", wt.DWORD), ("RegionSize", ctypes.c_size_t),
                ("State", wt.DWORD), ("Protect", wt.DWORD), ("Type", wt.DWORD)]


def load_names(delta):
    d = open(os.path.join(GAME, 'AoWEPACK.dll'), 'rb').read()
    V2F = 0x55700C00
    names = {}
    for m in re.finditer(rb'[\x04-\x28][A-Z][A-Za-z0-9]{3,39}', d):
        off = m.start()
        ln = d[off]
        if ln != len(m.group()) - 1:
            continue
        needle = struct.pack('<I', off + V2F)
        i = d.find(needle)
        while i != -1:
            names[i + V2F + 32 + delta] = d[off+1:off+1+ln].decode('ascii', 'replace')
            i = d.find(needle, i + 1)
    return names


def main():
    targets = [int(a, 16) for a in sys.argv[1:]]
    if not targets:
        print("usage: ref_probe.py <hexaddr> ...")
        return 1
    ps = pids()
    if not ps:
        print("game not running")
        return 1
    pid = ps[0]
    h = k32.OpenProcess(0x410, False, pid)
    mods = modules(h)
    aowe = next((b for b, e, n in mods if n.lower() == 'aowepack.dll'), None)
    delta = (aowe or 0x55700000) - 0x55700000
    names = load_names(delta)

    def classify(vmt):
        if vmt in names:
            return 'AoWEPACK.' + names[vmt]
        for b, e, n in mods:
            if b <= vmt < e:
                return f'{n}+{vmt-b:#x}'
        return None

    pats = {struct.pack('<I', t): t for t in targets}
    addr = 0
    mbi = MBI()
    while addr < 0x7FFF0000:
        if not k32.VirtualQueryEx(h, ctypes.c_void_p(addr), ctypes.byref(mbi),
                                  ctypes.sizeof(mbi)):
            break
        base = mbi.BaseAddress or 0
        size = mbi.RegionSize
        if (mbi.State == 0x1000 and mbi.Type != 0x1000000 and
                mbi.Protect in (0x04, 0x08, 0x40, 0x80)):
            data = rd(h, base, size)
            if data:
                for pat, tgt in pats.items():
                    i = data.find(pat)
                    while i != -1:
                        if i % 4 == 0:
                            hit = base + i
                            # walk back to find owning object's VMT
                            owner = '?'
                            for back in range(0, 0x404, 4):
                                if i - back < 0:
                                    break
                                cand = struct.unpack_from('<I', data, i - back)[0]
                                cls = classify(cand)
                                if cls:
                                    owner = f'{cls} obj@{hit-back:08X} field+{back:#x}'
                                    break
                            print(f'{tgt:08X} <- ref at {hit:08X}  ({owner})')
                        i = data.find(pat, i + 1)
        addr = base + size
    k32.CloseHandle(h)
    return 0


if __name__ == "__main__":
    sys.exit(main())
