#!/usr/bin/env python3
"""Read-only live probe: dump the tactical-combat AI state (TCAI lists + per-unit facts) from the
running AoWx.exe.  Nothing is written to the process.  2026-09-20.

Reads AoWTCPCK's combat map global [0x46C064] (rebased), then
  map+0x118 TCAI ([cai+4] side, +8 own list, +0xC allies, +0x10 enemies, +0x2C attack counter,
                  +0x34 threatened, +0x36 turn state), map+0x134 round, map+0xED current side,
  map+0xE4 TCombat -> +0xC TCombatData (+0x4C walls, +0x4D breached).
Per combat object: class, [obj+0x47] flags (bit0 dead), [obj+0x5C] moves left, [obj+0x66] flee flag,
  [obj+0x40] cached target value, [obj+0x45] combat player, [obj+0x4C] TUnit -> class + resource name
  ([unit+0x40]->+0x24), HP via TUnit VMT+0xE0/+0xD0 (decoded getters) and position = [[obj+0x60]+4]+0x10/+0x11.
  --watch [seconds]: poll the TCAI move list during the AI turn and print every distinct state.
"""
import ctypes, struct, sys
from ctypes import wintypes
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

k32 = ctypes.windll.kernel32
BASE = 0x400000
G_COMBATMAP = 0x46C064
md = Cs(CS_ARCH_X86, CS_MODE_32); md.detail = True


class PE32(ctypes.Structure):
    _fields_ = [('dwSize', wintypes.DWORD), ('cntUsage', wintypes.DWORD), ('th32ProcessID', wintypes.DWORD),
                ('th32DefaultHeapID', ctypes.c_void_p), ('th32ModuleID', wintypes.DWORD), ('cntThreads', wintypes.DWORD),
                ('th32ParentProcessID', wintypes.DWORD), ('pcPriClassBase', wintypes.LONG), ('dwFlags', wintypes.DWORD),
                ('szExeFile', ctypes.c_char * 260)]


class ME32(ctypes.Structure):
    _fields_ = [('dwSize', wintypes.DWORD), ('th32ModuleID', wintypes.DWORD), ('th32ProcessID', wintypes.DWORD),
                ('GlblcntUsage', wintypes.DWORD), ('ProccntUsage', wintypes.DWORD), ('modBaseAddr', ctypes.c_void_p),
                ('modBaseSize', wintypes.DWORD), ('hModule', ctypes.c_void_p), ('szModule', ctypes.c_char * 256),
                ('szExePath', ctypes.c_char * 260)]


def find_game():
    snap = k32.CreateToolhelp32Snapshot(2, 0)
    pe = PE32(); pe.dwSize = ctypes.sizeof(PE32); pid = 0
    if k32.Process32First(snap, ctypes.byref(pe)):
        while True:
            if pe.szExeFile.lower() == b'aowx.exe':
                pid = pe.th32ProcessID; break
            if not k32.Process32Next(snap, ctypes.byref(pe)):
                break
    k32.CloseHandle(snap)
    if not pid:
        sys.exit("AoWx.exe not running")
    snap = k32.CreateToolhelp32Snapshot(0x18, pid)
    me = ME32(); me.dwSize = ctypes.sizeof(ME32); mods = {}
    if k32.Module32First(snap, ctypes.byref(me)):
        while True:
            mods[me.szModule.lower().decode()] = me.modBaseAddr
            if not k32.Module32Next(snap, ctypes.byref(me)):
                break
    k32.CloseHandle(snap)
    return pid, mods


class Mem:
    def __init__(self, pid):
        self.h = k32.OpenProcess(0x10, False, pid)
        if not self.h:
            sys.exit("OpenProcess failed")

    def read(self, addr, n):
        buf = (ctypes.c_byte * n)(); got = ctypes.c_size_t()
        if not k32.ReadProcessMemory(self.h, ctypes.c_void_p(addr), buf, n, ctypes.byref(got)) or got.value != n:
            return None
        return bytes(buf)

    def u32(self, a):
        b = self.read(a, 4); return struct.unpack('<I', b)[0] if b else None

    def i32(self, a):
        b = self.read(a, 4); return struct.unpack('<i', b)[0] if b else None

    def u8(self, a):
        b = self.read(a, 1); return b[0] if b else None

    def shortstr(self, a):
        b = self.read(a, 1)
        if not b: return '?'
        s = self.read(a + 1, b[0]); return s.decode('latin1', 'replace') if s else '?'

    def ansistr(self, p):
        if not p: return ''
        n = self.u32(p - 4)
        if n is None or n > 200: return '?'
        s = self.read(p, n); return s.decode('latin1', 'replace') if s else '?'

    def classname(self, obj):
        vmt = self.u32(obj)
        if not vmt: return '?'
        p = self.u32(vmt - 0x20)
        return self.shortstr(p) if p else '?'

    def vslot_field(self, obj, slot):
        """Decode a trivial getter at VMT[slot] (mov/movsx/movzx reg,[eax+disp]) -> (disp, size) or None."""
        vmt = self.u32(obj)
        fn = self.u32(vmt + slot) if vmt else None
        code = self.read(fn, 24) if fn else None
        if not code: return None
        for ins in md.disasm(code, fn):
            if ins.mnemonic in ('mov', 'movsx', 'movzx') and len(ins.operands) == 2 and ins.operands[1].type == 3:
                m = ins.operands[1].mem
                if m.base != 0 and m.index == 0:
                    return m.disp, ins.operands[1].size
            if ins.mnemonic in ('ret', 'jmp', 'call'):
                return None
        return None

    def vget(self, obj, slot, signed=True):
        f = self.vslot_field(obj, slot)
        if not f: return None
        disp, size = f
        b = self.read(obj + disp, size)
        if not b: return None
        return int.from_bytes(b, 'little', signed=signed)


def dump_list(mem, name, lst, my_side):
    if not lst:
        print(f"  {name}: (nil)"); return
    items, cnt = mem.u32(lst + 4), mem.u32(lst + 8)
    print(f"  {name}: {cnt} objects")
    for i in range(cnt or 0):
        obj = mem.u32(items + 4 * i)
        if not obj:
            print(f"    [{i}] nil"); continue
        cls = mem.classname(obj)
        flags = mem.u8(obj + 0x47); moves = mem.i32(obj + 0x5C); flee = mem.u8(obj + 0x66)
        val = mem.i32(obj + 0x40); dirty = mem.u8(obj + 0x44); cp = mem.u8(obj + 0x45)
        unit = mem.u32(obj + 0x4C)
        ucls = mem.classname(unit) if unit else '-'
        res = mem.u32(unit + 0x40) if unit else 0
        rname = mem.ansistr(mem.u32(res + 0x24)) if res else ''
        hp = mx = None
        if unit:
            hp = mem.vget(unit, 0xE0); mx = mem.vget(unit, 0xD0)
        hs = mem.u32(obj + 0x60)
        ho = mem.u32(hs + 4) if hs else 0      # THexSpace object: x byte +0x10, y byte +0x11 (getters VMT+0x74/+0x78)
        x = mem.u8(ho + 0x10) if ho else None; y = mem.u8(ho + 0x11) if ho else None
        dead = 'DEAD ' if flags is not None and flags & 1 else ''
        print(f"    [{i}] {obj:#010x} {cls} unit={ucls} '{rname}' {dead}hp {hp}/{mx} pos ({x},{y}) moves {moves} "
              f"flee {flee} cplayer {cp} value {val}{' (dirty)' if dirty else ''} flags {flags:#04x}" if flags is not None else
              f"    [{i}] {obj:#010x} {cls} (unreadable)")


def unit_of_move(mem, rec):
    hs = mem.u32(rec + 0x14)
    return mem.u32(hs + 0x1C) if hs else 0


def describe(mem, obj):
    if not obj: return 'nil'
    unit = mem.u32(obj + 0x4C)
    ucls = mem.classname(unit) if unit else '-'
    res = mem.u32(unit + 0x40) if unit else 0
    rname = mem.ansistr(mem.u32(res + 0x24)) if res else ''
    return f"{obj:#x} {ucls} '{rname}' mv {mem.i32(obj + 0x5C)}"


def watch(mem, cmap, seconds):
    import time
    cai = mem.u32(cmap + 0x118)
    ml = mem.u32(cai + 0x14)
    print(f"watching TCAI {cai:#x} move list {ml:#x} for {seconds}s - end your turn now")
    t0 = time.time(); last = None; snaps = 0
    while time.time() - t0 < seconds:
        phase = mem.i32(cai + 0x1C); cnt = mem.u32(ml + 8); atk = mem.i32(cai + 0x2C); ts = mem.u8(cai + 0x36)
        uidx = mem.i32(cai + 0x20)
        items = mem.u32(ml + 4) if cnt else 0
        recs = []
        for i in range(min(cnt or 0, 40)):
            rec = mem.u32(items + 4 * i)
            if not rec: continue
            raw = mem.read(rec, 0x24)
            if not raw: continue
            typ = raw[4]; val = struct.unpack_from('<i', raw, 0xC)[0]; sup = struct.unpack_from('<i', raw, 0x10)[0]
            tgt = struct.unpack_from('<I', raw, 0x18)[0]
            dx, dy = struct.unpack_from('<HH', raw, 0x1C)
            recs.append((typ, val, sup, unit_of_move(mem, rec), tgt, dx, dy))
        key = (phase, cnt, atk, ts, uidx, tuple(recs))
        if key != last:
            last = key; snaps += 1
            print(f"[{time.time() - t0:6.2f}s] phase {phase} unit-idx {uidx} attacks {atk} turnstate {ts} moves {cnt} round {mem.i32(cmap + 0x134)} side {mem.u8(cmap + 0xED)}")
            for typ, val, sup, u, tgt, dx, dy in recs:
                print(f"      type {typ} value {val:>10} support {sup:>8} by {describe(mem, u)} -> target {describe(mem, tgt)} dest ({dx},{dy})")
        time.sleep(0.001)
    print(f"done: {snaps} distinct states")


def main():
    pid, mods = find_game()
    tc = mods.get('aowtcpck.dll')
    if tc is None:
        sys.exit("AoWTCPCK.dll not in process")
    mem = Mem(pid)
    delta = tc - BASE
    cmap = mem.u32(G_COMBATMAP + delta)
    print(f"AoWx pid {pid}; AoWTCPCK base {tc:#x} (delta {delta:+#x}); combat map {cmap:#x}")
    if not cmap:
        print("no tactical combat map active"); return
    if len(sys.argv) > 1 and sys.argv[1] == '--watch':
        watch(mem, cmap, float(sys.argv[2]) if len(sys.argv) > 2 else 120.0); return
    cai = mem.u32(cmap + 0x118)
    rnd = mem.i32(cmap + 0x134); cur_side = mem.u8(cmap + 0xED)
    combat = mem.u32(cmap + 0xE4); data = mem.u32(combat + 0xC) if combat else 0
    walls = mem.u8(data + 0x4C) if data else None; breached = mem.u8(data + 0x4D) if data else None
    print(f"round {rnd}, current side {cur_side}, walls present {walls}, breached {breached}")
    print(f"TCAI {cai:#x}: side {mem.u8(cai + 4)}, attack-moves-this-cycle {mem.i32(cai + 0x2C)}, "
          f"threatened {mem.u8(cai + 0x34)}, turn-state {mem.u8(cai + 0x36)}, phase {mem.i32(cai + 0x1C)}, "
          f"unit-index {mem.i32(cai + 0x20)}, non-hero count {mem.i32(cai + 0x30)}")
    my_side = mem.u8(cai + 4)
    dump_list(mem, "own units   [cai+8]", mem.u32(cai + 8), my_side)
    dump_list(mem, "allied units[cai+C]", mem.u32(cai + 0xC), my_side)
    dump_list(mem, "enemies     [cai+10]", mem.u32(cai + 0x10), my_side)
    ml = mem.u32(cai + 0x14)
    print(f"  move list [cai+14]: {mem.u32(ml + 8) if ml else 'nil'} entries (only populated during the AI's turn)")
    if data:
        n = mem.u32(data + 0x8)  # not necessarily count; informational
    print("\nnote: lists reflect the AI's LAST phase-0 rebuild; dead units may still be listed.")


if __name__ == '__main__':
    main()
