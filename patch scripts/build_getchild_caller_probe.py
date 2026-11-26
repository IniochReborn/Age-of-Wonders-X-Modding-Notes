#!/usr/bin/env python3
r"""TMapField.GetChild instrumentation (HSEPack.dpl) -- v3.

TWO things, one hook @0x55606E88 (entry of HSEngine.TMapField.GetChild):

1. RAISE-CASE CALLER PROBE (the Keeper2/TArmyCombatMoveTE 'Index out of
   bounds', captured live 2026-08-13): SIGNED index >= count -> deliberate AV
   reading staticVA(caller retaddr)|0x80000000. The Network.dpl detail dialog
   then prints `Read of address 8XXXXXXX`; caller VA = value & 0x7FFFFFFF.
   This replicates vanilla's raise condition EXACTLY.

2. NEGATIVE-INDEX LOGGER (silent, zero behaviour change): vanilla's signed
   `jl` lets a negative index through to read garbage at [children-4n] and
   callers tolerate it (v1 of this probe trapped negatives and immediately
   broke campaign start / DeselectHS -- proof these calls are routine).
   Theory: some of those garbage reads get USED and corrupt the heap
   (candidate source of the wild ability-chain values, e.g. 0x47280000).
   v3 counts them and records first/last caller to DATA-page scratch
   @0x5562E700, then continues bit-for-bit vanilla:
       +0x00 counter of negative-index calls
       +0x04 last caller retaddr (RUNTIME)
       +0x08 first caller retaddr (RUNTIME)
       +0x0C delta (runtime-static; subtract from callers for static VA)
   Read any time while the game runs: --read.

Usage:  --apply | --revert | --status | --read
Backup: HSEPack.dpl.bak_getchildprobe (made on first --apply; --revert
        restores the whole file from it)
"""
import ctypes, os, shutil, struct, sys

GAME = os.environ.get('AOW_GAME_DIR') or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DPL = os.path.join(GAME, 'HSEPack.dpl')
BAK = DPL + '.bak_getchildprobe'

FILE_DELTA = 0x55600C00          # HSEPack CODE: VA = file + 0x55600C00
HOOK_VA   = 0x55606E88           # TMapField.GetChild entry
HOOK_FILE = HOOK_VA - FILE_DELTA
ORIG      = bytes.fromhex('33c98a480d')   # xor ecx,ecx ; mov cl,[eax+0xD]
RESUME_VA = 0x55606E8D           # stock cmp edx,ecx ; jl <body>

CAVE_VA   = 0x5562D820           # CODE-tail slack (verified zeros, no relocs)
CAVE_FILE = CAVE_VA - FILE_DELTA
CAVE_END_FILE = 0x2CE00          # end of CODE raw data

SCRATCH   = 0x5562E700           # DATA-page zero-fill slack, writable
SCRATCH_RVA = SCRATCH - 0x55600000


def build_cave():
    base = CAVE_VA
    buf = bytearray(); labels = {}; j8s = []; rel32 = []; calls = []

    def db(*b): buf.extend(b)
    def dd(v): buf.extend((v & 0xFFFFFFFF).to_bytes(4, 'little'))
    def lab(n): labels[n] = len(buf)
    def j8(op, n): db(op); j8s.append((len(buf), n)); db(0)
    def jmp(tgt): db(0xE9); rel32.append((len(buf), tgt)); dd(0)
    def call_lab(n): db(0xE8); calls.append((len(buf), n)); dd(0)

    # entry: eax=Self, edx=index, [esp]=caller retaddr
    db(0x33, 0xC9)                   # xor ecx,ecx        (displaced)
    db(0x8A, 0x48, 0x0D)             # mov cl,[eax+0xD]   (displaced; count)
    db(0x85, 0xD2)                   # test edx,edx
    j8(0x79, 'nonneg')               # jns

    # ---- negative index: log silently, then vanilla behaviour ----
    db(0x50)                         # push eax
    db(0x51)                         # push ecx
    call_lab('L')
    lab('L')
    db(0x58)                         # pop eax            runtime L
    db(0x2D); dd(base + labels['L']) # sub eax, L_static -> delta
    db(0x8B, 0x4C, 0x24, 0x08)       # mov ecx,[esp+8]    caller retaddr
    db(0x89, 0x88); dd(SCRATCH + 4)  # mov [eax+S+4], ecx   last caller
    db(0x83, 0xB8); dd(SCRATCH + 8); db(0x00)  # cmp dword [eax+S+8],0
    j8(0x75, 'skipfirst')
    db(0x89, 0x88); dd(SCRATCH + 8)  # mov [eax+S+8], ecx   first caller
    lab('skipfirst')
    db(0xFF, 0x80); dd(SCRATCH + 0)  # inc dword [eax+S+0]  counter
    db(0x89, 0x80); dd(SCRATCH + 12) # mov [eax+S+C], eax   delta
    db(0x59)                         # pop ecx  (count)
    db(0x58)                         # pop eax  (Self)
    jmp(RESUME_VA)                   # vanilla garbage-read path, unchanged

    lab('nonneg')
    db(0x3B, 0xD1)                   # cmp edx,ecx
    j8(0x7D, 'bad')                  # jge = exactly vanilla's raise case
    jmp(RESUME_VA)                   # valid index -> stock body

    # ---- raise case: encode static caller VA into a deliberate AV ----
    lab('bad')
    call_lab('L2')
    lab('L2')
    db(0x59)                         # pop ecx            runtime L2
    db(0x81, 0xE9); dd(base + labels['L2'])   # sub ecx, L2_static -> delta
    db(0x8B, 0x04, 0x24)             # mov eax,[esp]      caller retaddr
    db(0x29, 0xC8)                   # sub eax,ecx        -> static VA
    db(0x0D); dd(0x80000000)         # or  eax,0x80000000
    db(0x8B, 0x00)                   # mov eax,[eax]      -> AV @ encoded

    for off, n in j8s:
        d = labels[n] - (off + 1)
        assert -128 <= d <= 127, (n, d)
        buf[off] = d & 0xFF
    for off, tgt in rel32:
        buf[off:off+4] = (tgt - (base + off + 4)).to_bytes(4, 'little', signed=True)
    for off, n in calls:
        buf[off:off+4] = (labels[n] - (off + 4)).to_bytes(4, 'little', signed=True)
    assert CAVE_FILE + len(buf) <= CAVE_END_FILE, 'cave overruns CODE raw'
    return bytes(buf)


def hook_bytes():
    return b'\xe9' + struct.pack('<i', CAVE_VA - (HOOK_VA + 5))


def read_scratch():
    k32 = ctypes.windll.kernel32

    class PE32(ctypes.Structure):
        _fields_ = [("dwSize", ctypes.c_ulong), ("cntUsage", ctypes.c_ulong),
                    ("th32ProcessID", ctypes.c_ulong),
                    ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
                    ("th32ModuleID", ctypes.c_ulong),
                    ("cntThreads", ctypes.c_ulong),
                    ("th32ParentProcessID", ctypes.c_ulong),
                    ("pcPriClassBase", ctypes.c_long),
                    ("dwFlags", ctypes.c_ulong), ("szExeFile", ctypes.c_char * 260)]

    class ME32(ctypes.Structure):
        _fields_ = [("dwSize", ctypes.c_ulong), ("th32ModuleID", ctypes.c_ulong),
                    ("th32ProcessID", ctypes.c_ulong),
                    ("GlblcntUsage", ctypes.c_ulong),
                    ("ProccntUsage", ctypes.c_ulong),
                    ("modBaseAddr", ctypes.c_void_p),
                    ("modBaseSize", ctypes.c_ulong),
                    ("hModule", ctypes.c_void_p),
                    ("szModule", ctypes.c_char * 256),
                    ("szExePath", ctypes.c_char * 260)]

    snap = k32.CreateToolhelp32Snapshot(2, 0)
    pe = PE32(); pe.dwSize = ctypes.sizeof(PE32)
    pid = None
    ok = k32.Process32First(snap, ctypes.byref(pe))
    while ok:
        if pe.szExeFile.lower() == b'aowx.exe':
            pid = pe.th32ProcessID; break
        ok = k32.Process32Next(snap, ctypes.byref(pe))
    k32.CloseHandle(snap)
    if pid is None:
        print('AoWx.exe is not running'); return 1
    snap = k32.CreateToolhelp32Snapshot(8 | 0x10, pid)
    me = ME32(); me.dwSize = ctypes.sizeof(ME32)
    modbase = None
    ok = k32.Module32First(snap, ctypes.byref(me))
    while ok:
        if me.szModule.lower() == b'hsepack.dpl':
            modbase = me.modBaseAddr; break
        ok = k32.Module32Next(snap, ctypes.byref(me))
    k32.CloseHandle(snap)
    if modbase is None:
        print('HSEPack.dpl not found in process'); return 1
    h = k32.OpenProcess(0x10 | 0x400, False, pid)
    buf = (ctypes.c_char * 16)()
    got = ctypes.c_size_t()
    addr = modbase + SCRATCH_RVA
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, 16, ctypes.byref(got)):
        print('ReadProcessMemory failed'); return 1
    k32.CloseHandle(h)
    count, last, first, delta = struct.unpack('<4I', bytes(buf))
    print(f'HSEPack base {modbase:#x}  scratch @{addr:#x}')
    if count == 0:
        print('no negative-index GetChild calls yet'); return 0
    print(f'negative-index GetChild calls: {count}')
    print(f'  first caller runtime {first:#010x}  STATIC {(first - delta) & 0xFFFFFFFF:#010x}')
    print(f'  last  caller runtime {last:#010x}  STATIC {(last - delta) & 0xFFFFFFFF:#010x}')
    return 0


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else '--status'
    if mode == '--read':
        return read_scratch()

    data = bytearray(open(DPL, 'rb').read())
    cur = bytes(data[HOOK_FILE:HOOK_FILE + 5])

    if mode == '--status':
        if cur == ORIG:
            print('probe NOT applied (stock bytes present)')
        elif cur == hook_bytes():
            cave = build_cave()
            live = bytes(data[CAVE_FILE:CAVE_FILE + len(cave)])
            print('probe APPLIED,', 'cave = v3' if live == cave else 'cave DIFFERS (older version?)')
        else:
            print('UNEXPECTED bytes at hook site:', cur.hex())
        return 0

    if mode == '--apply':
        assert cur in (ORIG, hook_bytes()), f'hook site unrecognized: {cur.hex()}'
        cave = build_cave()
        if not os.path.exists(BAK):
            shutil.copy2(DPL, BAK)
            print('backup ->', BAK)
        data[CAVE_FILE:CAVE_END_FILE] = bytes(CAVE_END_FILE - CAVE_FILE)
        data[CAVE_FILE:CAVE_FILE + len(cave)] = cave
        data[HOOK_FILE:HOOK_FILE + 5] = hook_bytes()
        open(DPL, 'wb').write(data)
        print(f'APPLIED v3: hook @{HOOK_VA:#x} -> cave @{CAVE_VA:#x} ({len(cave)} B), '
              f'scratch @{SCRATCH:#x}')
        return 0

    if mode == '--revert':
        assert os.path.exists(BAK), 'no backup found'
        shutil.copy2(BAK, DPL)
        print('reverted from', BAK)
        return 0

    print(__doc__); return 1


if __name__ == '__main__':
    sys.exit(main())
