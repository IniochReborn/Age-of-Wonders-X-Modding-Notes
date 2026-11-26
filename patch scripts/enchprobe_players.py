import ctypes, ctypes.wintypes as W
k32 = ctypes.WinDLL('kernel32', use_last_error=True)
k32.OpenProcess.restype = W.HANDLE
k32.ReadProcessMemory.argtypes = [W.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
hp = k32.OpenProcess(0x1F0FFF, False, 10232)
def rpm(a, n):
    b = ctypes.create_string_buffer(n); g = ctypes.c_size_t()
    return b.raw[:g.value] if k32.ReadProcessMemory(hp, ctypes.c_void_p(a), b, n, ctypes.byref(g)) else b''
def u32(a): d = rpm(a, 4); return int.from_bytes(d, 'little') if len(d) == 4 else 0
def u8(a): d = rpm(a, 1); return d[0] if d else -1
def cls(obj):
    try:
        vmt = u32(obj); p = u32(vmt - 32); n = rpm(p, 1)[0]; return rpm(p + 1, n).decode(errors='replace')
    except Exception: return '?'
mapp = u32(0x00DF0000 + 0x1FA040)
pl = u32(mapp + 0x140); tl = u32(pl + 8); items = u32(tl + 4); cnt = u32(tl + 8)
print(f'players: {cnt}  (map+0x139 net={u8(mapp+0x139)} map+0xA4 cur={u8(mapp+0xA4)} map+0xA5 seated={u8(mapp+0xA5)} map+0x239 phase={u8(mapp+0x239)} map+0x1C8 lock={u32(mapp+0x1C8)})')
for i in range(cnt):
    p = u32(items + 4 * i)
    if not p: continue
    mc = u32(p + 0x54); lst = u32(mc + 0x3C); ch = u32(lst + 8); ei = u32(ch + 4); ec = u32(ch + 8)
    leader = u32(p + 0xD4)
    lname = ''
    if leader:
        sp = u32(leader + 0x60); n = u32(sp - 4) if sp else 0
        lname = rpm(sp, min(n, 40)).decode(errors='replace') if sp and 0 < n < 64 else ''
    print(f'player[{i}] {p:08X} idx={u8(p+0xA6)} ai={u8(p+0xA7)} gameover={u8(p+0x44)} pend={u8(p+0x45)} race={u8(p+0xA5)} leader={leader:08X} "{lname}" enchantments={ec}')
    for j in range(ec):
        e = u32(ei + 4 * j)
        print(f'    [{j}] {e:08X} {cls(e):28s} caster=+0xC:{u8(e+0xC):3d} +0x8={u32(e+8):08X} +0x10={u32(e+0x10)} +0x14={u8(e+0x14)} unitid=+0x18:{u32(e+0x18)} ability=+0x1C:0x{u32(e+0x1C):X}')
