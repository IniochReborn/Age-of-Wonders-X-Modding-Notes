#!/usr/bin/env python3
r"""Dump the live Healing state of every hero/leader in the RUNNING game.

Use: start AoWx, get the hero with the Healing item, USE the heal (combat or
overland), leave the game running, then:  py "patch scripts\heal_probe.py"

Prints, for every THero/TLeader instance found on the heap:
  - own ability-set bit for Healing (0x2F)
  - the own record chain (class, [rec+0xC] used-flag, [rec+0xD] level)
  - carried items / inventory: per item the Healing bit and its records
  - the value THealingAbility.GetEnabled(hero) would compute from that state
"""
import ctypes, ctypes.wintypes as wt, subprocess, struct, sys, os

k32 = ctypes.windll.kernel32
psapi = ctypes.windll.psapi
PREF = 0x55700000
HEAL_ID = 0x2F

# preferred-base VMT values as stored in live instances
VMT_THERO   = 0x55711FEC
VMT_TLEADER = 0x55712238
VMT_TITEM   = 0x5570FAFC
VMT_HEALDATA = 0x55721590        # THealingAbilityData instance VMT

GAME = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


def pids(name="AoWx.exe"):
    out = subprocess.check_output(
        ["tasklist", "/FI", f"IMAGENAME eq {name}", "/FO", "CSV", "/NH"], text=True)
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
        if not v:
            continue
        psapi.GetModuleBaseNameA(h, ctypes.c_void_p(v), nb, 260)
        out[nb.value.lower().decode()] = v
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


def u8(h, a):
    b = rd(h, a, 1)
    return b[0] if b else None


class MBI(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_void_p), ("AllocationBase", ctypes.c_void_p),
                ("AllocationProtect", wt.DWORD), ("RegionSize", ctypes.c_size_t),
                ("State", wt.DWORD), ("Protect", wt.DWORD), ("Type", wt.DWORD)]


def scan_for(h, needles):
    """yield (needle, va) for every aligned dword match in committed RW memory"""
    addr = 0
    mbi = MBI()
    pats = {struct.pack('<I', n): n for n in needles}
    while addr < 0x7FFF0000:
        if not k32.VirtualQueryEx(h, ctypes.c_void_p(addr), ctypes.byref(mbi),
                                  ctypes.sizeof(mbi)):
            break
        base = mbi.BaseAddress or 0
        size = mbi.RegionSize
        # MEM_COMMIT, readable+writable, not an image section
        if (mbi.State == 0x1000 and mbi.Type != 0x1000000 and
                mbi.Protect in (0x04, 0x08, 0x40, 0x80)):
            data = rd(h, base, size)
            if data:
                for pat, val in pats.items():
                    i = data.find(pat)
                    while i != -1:
                        if i % 4 == 0:
                            yield val, base + i
                        i = data.find(pat, i + 1)
        addr = base + size


def has_bit(h, owner, aid):
    bits, cnt = u32(h, owner + 8), u32(h, owner + 0xC)
    if not bits or cnt is None or aid >= cnt:
        return False
    w = u32(h, bits + (aid >> 5) * 4)
    return bool(w is not None and (w >> (aid & 31)) & 1)


def chain(h, owner, delta):
    out = []
    node = u32(h, owner + 0x10)
    n = 0
    while node and n < 32:
        vmt = (u32(h, node) or 0) - delta
        out.append((node, vmt, u8(h, node + 0xC), u8(h, node + 0xD)))
        node = u32(h, node + 8)
        n += 1
    return out


def cname(vmt, names):
    return names.get(vmt, 'vmt=%08X' % vmt)


def load_names():
    """classname per instance-VMT (nameptr_loc+32) from the on-disk DLL."""
    d = open(os.path.join(GAME, 'AoWEPACK.dll'), 'rb').read()
    V2F = 0x55700C00
    names = {}
    import re
    for m in re.finditer(rb'[\x04-\x28][A-Z][A-Za-z0-9]{3,39}', d):
        off = m.start()
        ln = d[off]
        if ln != len(m.group()) - 1 or not d[off+1:off+2].isupper():
            continue
        name_va = off + V2F
        needle = struct.pack('<I', name_va)
        i = d.find(needle)
        while i != -1:
            names[i + V2F + 32] = d[off+1:off+1+ln].decode('ascii', 'replace')
            i = d.find(needle, i + 1)
    return names


def main():
    ps = pids()
    if not ps:
        print("AoWx.exe is not running.")
        return 1
    names = load_names()
    for pid in ps:
        h = k32.OpenProcess(0x410, False, pid)
        if not h:
            print(f"pid {pid}: cannot open (try an elevated prompt)")
            continue
        m = modules(h)
        base = m.get('aowepack.dll')
        if not base:
            print(f"pid {pid}: AoWEPACK.dll not loaded")
            continue
        delta = base - PREF
        print(f"=== pid {pid}: AoWEPACK base {base:#x} (delta {delta:+#x})")
        # confirm the loaded DLL carries our patches (VMT+0x74 slot value)
        slot = u32(h, 0x557217BC + 0x74 + delta)
        print("  live THealingAbility VMT+0x74 =", hex((slot or 0) - delta),
              "(expect 0x55812700 cave_ghe)")
        slot = u32(h, 0x557217BC + 0x58 + delta)
        print("  live THealingAbility VMT+0x58 =", hex((slot or 0) - delta),
              "(expect 0x55812a00 cave_gname)")
        targets = {VMT_THERO + delta: 'THero', VMT_TLEADER + delta: 'TLeader'}
        seen = set()
        for vmtval, va in scan_for(h, list(targets)):
            if va in seen:
                continue
            seen.add(va)
            hero = va
            kind = targets[vmtval]
            player = u8(h, hero + 0x24)
            ownbit = has_bit(h, hero, HEAL_ID)
            ch = chain(h, hero, delta)
            heal_recs = [c for c in ch if c[1] == VMT_HEALDATA]
            items_report = []
            item_heal_bit = False
            for off, tag in ((0x70, 'items'), (0x74, 'inv')):
                cont = u32(h, hero + off)
                if not cont:
                    continue
                lst = u32(h, cont + 8)
                if not lst:
                    continue
                data, cnt = u32(h, lst + 4), u32(h, lst + 8)
                if not data or not cnt or cnt > 64:
                    continue
                for i in range(cnt):
                    item = u32(h, data + i * 4)
                    if not item or item < 0x10000:
                        continue
                    ivmt = (u32(h, item) or 0) - delta
                    if ivmt != VMT_TITEM:
                        continue
                    ib = has_bit(h, item, HEAL_ID)
                    item_heal_bit |= ib
                    irecs = [c for c in chain(h, item, delta) if c[1] == VMT_HEALDATA]
                    if ib or irecs:
                        items_report.append((tag, i, item, ib, irecs))
            if not (ownbit or item_heal_bit or heal_recs):
                continue        # hero without any healing: skip noise
            print(f"\n  {kind} @{hero:08X} player={player} ownHealBit={ownbit}")
            for node, vmt, fC, fD in ch:
                mark = '  <-- HEALING' if vmt == VMT_HEALDATA else ''
                print(f"    rec {node:08X} {cname(vmt, names):28s} "
                      f"+0xC(used-flag)={fC} +0xD(level)={fD}{mark}")
            for tag, i, item, ib, irecs in items_report:
                print(f"    {tag}[{i}] item {item:08X} healBit={ib}")
                for node, vmt, fC, fD in irecs:
                    print(f"        item rec {node:08X} {cname(vmt, names)} "
                          f"+0xC={fC} +0xD={fD}")
            # what cave_ghe would return
            if heal_recs:
                verdict = heal_recs[0][2]
            elif ownbit or item_heal_bit:
                verdict = 1
            else:
                verdict = 0
            print(f"    => GetEnabled(hero) computes: {verdict} "
                  f"({'ENABLED - name plain' if verdict else 'DISABLED - name (used)'})")
        k32.CloseHandle(h)
    return 0


if __name__ == "__main__":
    sys.exit(main())
