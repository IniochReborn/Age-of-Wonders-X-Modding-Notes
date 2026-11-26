#!/usr/bin/env python3
"""Read-only (2026-11-04): dump the HSE map fields of a teleporter and its destination in a running AoWx.exe or
AoWDevX.exe - per field: xyz, terrain, flags (0x8000 = exclusive move), structure list with part bytes + class names,
and for TTeleport objects their position (+0x10/+0x11, level) and destination (+0x30..+0x33).
Usage: tele_field_probe.py [aowx|devx] x y z [x y z ...]"""
import ctypes, sys
sys.argv, args = sys.argv[:1], sys.argv[1:]
sys.path.insert(0, '.')
import ai_state_probe as P

target = b'aowdevx.exe' if args and args[0] == 'devx' else b'aowx.exe'
coords = [int(a) for a in args[1:]]
k32 = P.k32
snap = k32.CreateToolhelp32Snapshot(2, 0)
pe = P.PE32(); pe.dwSize = ctypes.sizeof(P.PE32); pid = 0
if k32.Process32First(snap, ctypes.byref(pe)):
    while True:
        if pe.szExeFile.lower() == target:
            pid = pe.th32ProcessID; break
        if not k32.Process32Next(snap, ctypes.byref(pe)):
            break
k32.CloseHandle(snap)
if not pid:
    sys.exit(f"{target.decode()} not running")
snap = k32.CreateToolhelp32Snapshot(0x18, pid)
me = P.ME32(); me.dwSize = ctypes.sizeof(P.ME32); mods = {}
if k32.Module32First(snap, ctypes.byref(me)):
    while True:
        mods[me.szModule.lower().decode()] = me.modBaseAddr
        if not k32.Module32Next(snap, ctypes.byref(me)):
            break
mem = P.Mem(pid)
ep = mods['aowepack.dll']
gmap = mem.u32(0x558FA040 - 0x55700000 + ep)
print(f"pid {pid} AoWEPACK {ep:#x} AoWHSMap {gmap:#x}")
hsmap = mem.u32(gmap + 0x10)
levels = mem.u32(mem.u32(hsmap + 8) + 4); nlev = mem.u32(mem.u32(hsmap + 8) + 8)
print(f"hsmap {hsmap:#x} levels {nlev} W {mem.u32(hsmap+0xc)} H {mem.u32(hsmap+0x10)} count {mem.u32(hsmap+0x14)}")


def field(x, y, z):
    lv = mem.u32(levels + 4 * z)
    return mem.u32(mem.u32(lv + 0x74) + 4 * x) + mem.u32(mem.u32(lv + 0x78) + 4 * y)


for i in range(0, len(coords), 3):
    x, y, z = coords[i:i + 3]
    f = field(x, y, z)
    cap, cnt = mem.u8(f + 0xc), mem.u8(f + 0xd)
    arr = mem.u32(f + 8)
    print(f"\nfield ({x},{y},{z}) @{f:#x}: xyz=({mem.u8(f+0x10)},{mem.u8(f+0x11)},{mem.u8(f+0x12)}) "
          f"terrain {mem.u8(f+0x14)}/{mem.u8(f+0x15)} flags {mem.u32(f+0x18):#x} [+0xf]={mem.u8(f+0xf):#x} cap {cap} n {cnt}")
    for k in range(cnt):
        o = mem.u32(arr + 4 * k); part = mem.u8(arr + 4 * cap + k)
        cn = mem.classname(o)
        line = f"   [{k}] part {part} {cn} @{o:#x}"
        if cn in ('TTeleport',):
            line += (f"  pos ({mem.u8(o+0x10)},{mem.u8(o+0x11)}) owner-field {mem.u32(o+4):#x} "
                     f"lvl {mem.u8(mem.u32(o+4)+0x12) if mem.u32(o+4) else '-'} "
                     f"dest ({mem.u8(o+0x30)},{mem.u8(o+0x31)},{mem.u8(o+0x32)}) flags33 {mem.u8(o+0x33):#x} "
                     f"res {mem.u32(o+8):#x} pad {mem.u8(mem.u32(o+8)+0x44)}")
        print(line)
