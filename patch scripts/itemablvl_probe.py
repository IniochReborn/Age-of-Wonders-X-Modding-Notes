#!/usr/bin/env python3
r"""Read the item-ability-level diagnostic counters out of the RUNNING AoWx.exe.
Pair with build_itemablvl_diag.py. Start the game, enter a tactical battle with
the Dragon Hunter hero, click the hero so the right-side unit panel lists its
abilities, fire the bow once, then run this while the game is still running.
"""
import ctypes, ctypes.wintypes as wt, subprocess, sys, struct, os

k32 = ctypes.windll.kernel32
psapi = ctypes.windll.psapi

PREF_BASE = 0x55700000
DIAG_RVA = 0x558E9B00 - PREF_BASE

GAME = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


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


def u32(h, a):
    buf = ctypes.create_string_buffer(4); got = ctypes.c_size_t()
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(a), buf, 4, ctypes.byref(got)):
        return None
    return struct.unpack('<I', buf.raw)[0]


def load_vmt_names():
    """classname by preferred-base VMT VA, from the on-disk DLL."""
    sys.path.insert(0, os.path.join(os.environ.get('LOCALAPPDATA', ''), 'nonexistent'))
    try:
        scratch = r'C:\Users\<user>\AppData\Local\Temp\claude\C--Users-<user>-Desktop-Age-of-Wonders-X---Claude\af9a924c-2966-4ffc-8efd-4b983e546f21\scratchpad'
        sys.path.insert(0, scratch)
        from aow_pe import PE, find_vmts
        pe = PE(os.path.join(GAME, 'AoWEPACK.dll'))
        return {vmt: n for vmt, (n, p, s) in find_vmts(pe).items()}
    except Exception as ex:
        print('(no vmt names: %s)' % ex)
        return {}


def main():
    ps = pids()
    if not ps:
        print("AoWx.exe is not running."); return 1
    names = load_vmt_names()
    for pid in ps:
        h = k32.OpenProcess(0x410, False, pid)
        if not h:
            print(f"pid {pid}: cannot open"); continue
        m = modules(h)
        base = m.get('aowepack.dll')
        print(f"=== pid {pid}: AoWEPACK.dll base {hex(base) if base else 'NOT LOADED'}")
        if base:
            delta = base - PREF_BASE
            D = base + DIAG_RVA
            v = [u32(h, D + i*4) for i in range(6)]
            print("  GetLevel entries (all)    :", v[0])
            print("  entries for Marksmanship  :", v[1])
            print("  last owner ptr            : %08X" % (v[2] or 0))
            vmt = (v[3] or 0) - delta
            print("  last owner VMT            : %08X (%s)" % (v[3] or 0, names.get(vmt, 'unknown')))
            print("  last own-record arg       : %08X" % (v[4] or 0))
            print("  last returned level       :", v[5])
            owner = v[2]
            if owner:
                walk_owner(h, owner, delta, names)
        k32.CloseHandle(h)
    return 0


def clsname(h, obj, delta, names):
    if not obj: return 'nil'
    vmt = u32(h, obj)
    if vmt is None: return 'unreadable'
    return names.get(vmt - delta, 'vmt=%08X' % vmt)


def walk_owner(h, owner, delta, names):
    print("  ---- owner structure walk ----")
    # own ability set: [owner+8] bits ptr, [owner+0xC] count
    bits, nab = u32(h, owner+8), u32(h, owner+0xC)
    w0 = u32(h, bits) if bits else None
    w1 = u32(h, bits+4) if bits else None
    marks = 'SET' if (w1 is not None and (w1 & 1)) else 'clear'   # id 0x20 = word 1 bit 0
    print("  own set: bitsptr=%08X count=%s words=[%08X %08X] bit0x20(marks)=%s" % (
        bits or 0, nab, w0 or 0, w1 or 0, marks))
    # own record chain
    node = u32(h, owner+0x10)
    chain = []
    seen = 0
    while node and seen < 32:
        chain.append('%08X(%s)' % (node, clsname(h, node, delta, names)))
        node = u32(h, node+8); seen += 1
    print("  own record chain:", ' -> '.join(chain) if chain else '(empty)')
    for off, tag in ((0x70, 'THeroItems [hero+0x70]'), (0x74, 'THeroInventory [hero+0x74]')):
        c = u32(h, owner+off)
        print("  %s = %08X (%s)" % (tag, c or 0, clsname(h, c, delta, names)))
        if not c: continue
        lst = u32(h, c+8)
        print("    [c+8] list = %08X" % (lst or 0))
        if not lst: continue
        data, cnt = u32(h, lst+4), u32(h, lst+8)
        print("    data=%08X count=%s" % (data or 0, cnt))
        if not data or not cnt or cnt > 64: continue
        for i in range(cnt):
            item = u32(h, data + i*4)
            print("    item[%d] = %08X (%s)" % (i, item or 0, clsname(h, item, delta, names)))
            if not item: continue
            node = u32(h, item+0x10); seen = 0
            while node and seen < 16:
                nvmt = u32(h, node)
                lvl = u32(h, node+0xC)
                print("      rec %08X (%s) [rec+0xC..0x10]=%08X %08X" % (
                    node, clsname(h, node, delta, names), lvl or 0, u32(h, node+0x10) or 0))
                node = u32(h, node+8); seen += 1


if __name__ == "__main__":
    sys.exit(main())
