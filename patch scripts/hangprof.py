"""hangprof.py <pid> [samples] -- WOW64 EIP/stack sampler for a hung 32-bit game.
Prints per-thread EIP histogram (symbolized via module export tables) and a
return-address scan of the hottest thread's stack."""
import ctypes, ctypes.wintypes as W, sys, time, os, bisect, collections
import pefile

k32 = ctypes.WinDLL('kernel32', use_last_error=True)
PID = int(sys.argv[1]); NS = int(sys.argv[2]) if len(sys.argv) > 2 else 60
PROCESS_ALL = 0x1F0FFF
THREAD_ALL = 0x1F03FF
TH32CS_SNAPTHREAD = 4; TH32CS_SNAPMODULE = 8; TH32CS_SNAPMODULE32 = 0x10

class THREADENTRY32(ctypes.Structure):
    _fields_ = [('dwSize', W.DWORD), ('cntUsage', W.DWORD), ('th32ThreadID', W.DWORD),
                ('th32OwnerProcessID', W.DWORD), ('tpBasePri', W.LONG), ('tpDeltaPri', W.LONG), ('dwFlags', W.DWORD)]
class MODULEENTRY32W(ctypes.Structure):
    _fields_ = [('dwSize', W.DWORD), ('th32ModuleID', W.DWORD), ('th32ProcessID', W.DWORD),
                ('GlblcntUsage', W.DWORD), ('ProccntUsage', W.DWORD), ('modBaseAddr', ctypes.c_void_p),
                ('modBaseSize', W.DWORD), ('hModule', ctypes.c_void_p), ('szModule', W.WCHAR * 256), ('szExePath', W.WCHAR * 260)]

k32.CreateToolhelp32Snapshot.restype = W.HANDLE
k32.OpenProcess.restype = W.HANDLE
k32.OpenThread.restype = W.HANDLE
k32.ReadProcessMemory.argtypes = [W.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]

hp = k32.OpenProcess(PROCESS_ALL, False, PID)
if not hp:
    hp = k32.OpenProcess(0x0410, False, PID)  # VM_READ|QUERY
    print('OpenProcess(all) failed err', ctypes.get_last_error(), '-> fallback', bool(hp))
if not hp: sys.exit('cannot open process (needs elevation?)')

# modules
mods = []
snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, PID)
me = MODULEENTRY32W(); me.dwSize = ctypes.sizeof(me)
if k32.Module32FirstW(snap, ctypes.byref(me)):
    while True:
        mods.append((me.modBaseAddr, me.modBaseSize, me.szModule, me.szExePath))
        if not k32.Module32NextW(snap, ctypes.byref(me)): break
k32.CloseHandle(snap)
mods.sort()
print(f'{len(mods)} modules')
for b, s, n, p in mods:
    if not p.lower().startswith('c:\\windows'):
        print(f'  {b:08X}-{b+s:08X} {n}')

# export symbols per module (Delphi packages export nearly everything)
symcache = {}
def load_syms(path, base):
    try:
        pe = pefile.PE(path, fast_load=True)
        pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_EXPORT']])
        syms = []
        if hasattr(pe, 'DIRECTORY_ENTRY_EXPORT'):
            for e in pe.DIRECTORY_ENTRY_EXPORT.symbols:
                if e.address and e.name:
                    syms.append((base + e.address, e.name.decode(errors='replace')))
        syms.sort()
        return syms
    except Exception as ex:
        return []

def modof(a):
    for b, s, n, p in mods:
        if b <= a < b + s: return (b, s, n, p)
    return None

def sym(a):
    m = modof(a)
    if not m: return None
    b, s, n, p = m
    if n not in symcache: symcache[n] = load_syms(p, b)
    syms = symcache[n]
    rva = a - b
    if syms:
        i = bisect.bisect_right([x for x, _ in syms], a) - 1
        if i >= 0 and a - syms[i][0] < 0x2000:
            return f'{n}!{syms[i][1]}+0x{a-syms[i][0]:X} (rva 0x{rva:X})'
    return f'{n}+0x{rva:X}'

# threads
tids = []
snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0)
te = THREADENTRY32(); te.dwSize = ctypes.sizeof(te)
if k32.Thread32First(snap, ctypes.byref(te)):
    while True:
        if te.th32OwnerProcessID == PID: tids.append(te.th32ThreadID)
        if not k32.Thread32Next(snap, ctypes.byref(te)): break
k32.CloseHandle(snap)
print(f'{len(tids)} threads: {tids}')

CTX_FULL = 0x10007
def get_ctx(ht):
    buf = ctypes.create_string_buffer(716)
    ctypes.memmove(buf, bytes(ctypes.c_uint32(CTX_FULL)), 4)
    if k32.SuspendThread(ht) == 0xFFFFFFFF: return None
    ok = k32.Wow64GetThreadContext(ht, buf)
    k32.ResumeThread(ht)
    if not ok: return None
    u32 = lambda o: int.from_bytes(buf.raw[o:o+4], 'little')
    return dict(eip=u32(184), esp=u32(196), ebp=u32(180), eax=u32(176), ebx=u32(164), ecx=u32(172), edx=u32(168), esi=u32(160), edi=u32(156))

def rpm(addr, n):
    buf = ctypes.create_string_buffer(n); got = ctypes.c_size_t()
    if k32.ReadProcessMemory(hp, ctypes.c_void_p(addr), buf, n, ctypes.byref(got)): return buf.raw[:got.value]
    return b''

hist = {t: collections.Counter() for t in tids}
last = {}
handles = {t: k32.OpenThread(THREAD_ALL, False, t) for t in tids}
for i in range(NS):
    for t in tids:
        ht = handles[t]
        if not ht: continue
        c = get_ctx(ht)
        if c: hist[t][c['eip']] += 1; last[t] = c
    time.sleep(0.02)

hot = None; hotn = -1
for t in tids:
    if not hist[t]: continue
    top = hist[t].most_common(3)
    # score: samples landing in non-Windows modules
    ingame = sum(n for a, n in hist[t].items() if (m := modof(a)) and not m[3].lower().startswith('c:\\windows'))
    print(f'\nthread {t}: {sum(hist[t].values())} samples, {len(hist[t])} distinct EIPs, {ingame} in game modules')
    for a, n in top:
        print(f'   {n:4d}x {a:08X} {sym(a)}')
    if ingame > hotn: hotn = ingame; hot = t

for t in (sorted(tids, key=lambda t: -sum(n for a, n in hist[t].items() if (m := modof(a)) and not m[3].lower().startswith('c:\\windows')))[:2]):
    c = last.get(t)
    if not c: continue
    print(f'\n=== thread {t} stack scan (esp={c["esp"]:08X} ebp={c["ebp"]:08X} eip={c["eip"]:08X} eax={c["eax"]:08X} ebx={c["ebx"]:08X} ecx={c["ecx"]:08X} edx={c["edx"]:08X} esi={c["esi"]:08X} edi={c["edi"]:08X})')
    stk = rpm(c['esp'], 0x3000)
    for off in range(0, len(stk) - 3, 4):
        v = int.from_bytes(stk[off:off+4], 'little')
        m = modof(v)
        if m and not m[3].lower().startswith('c:\\windows'):
            # plausible return address: byte before is a call (E8 / FF)
            pre = rpm(v - 6, 6)
            iscall = len(pre) == 6 and (pre[1] == 0xE8 or pre[0] == 0xFF or pre[4] == 0xFF or pre[3] == 0xFF)
            print(f'  [esp+0x{off:04X}] {v:08X} {sym(v)}{"  <call>" if iscall else ""}')
