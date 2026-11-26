#!/usr/bin/env python3
r"""GetAbilityData owner-guard v3: pre-detect wild chain nodes + RECORD the culprit.

WHY (2026-08-13): with full 403 + guard, the crash family fired again live:
    EAccessViolation in AoWEPACK.dll at 0011102D, read of 0x47280000
0x5581102D = the guard cave's own `mov eax,[ecx]` node-vtable read: node ptr
0x47280000 passed the old plausibility range (0x10000..0x7F000000) but is
unmapped -- the guard's documented honest limit.

V3 CHANGES (same hook @0x5574F1C4, same cave slot 0x55811000..0x55811100):
  1. Node-pointer ceiling tightened to 0x40000000. Real TAbilityData nodes are
     Delphi heap objects (low hundreds of MB); 0x47280000-class garbage is now
     DETECTED instead of faulted on -> graceful nil return, combat proceeds,
     NO crash dialog. (Vtable range stays 0x10000..0x7F000000 -- vtables live
     in rebased modules and can sit high.)
  2. First bogus call is RECORDED to BSS scratch @0x558FAF40 (page slack after
     our AI-spell flags 0x558FAF20-22; zero-init, writable):
        +0x00 flag       0 = nothing recorded, 1 = recorded (sticky)
        +0x04 caller     return address (RUNTIME; subtract delta for static)
        +0x08 owner      Self passed to GetAbilityData
        +0x0C bad node   chain node that failed (or 1 = Self itself was bad)
        +0x10 ability id edx argument
        +0x14 delta      runtime-static (subtract from caller for static VA)
     Read it any time with --read while the game is running.

RESIDUAL LIMIT: a node in 0x10000..0x40000000 that is unmapped still faults on
the vtable read (unchanged from v2, but the window is far narrower).

Usage: --apply | --revert (restores v2 plain guard) | --status | --read
Backup: AoWEPACK.dll.bak_abguardrec
"""
import ctypes, importlib.util, os, shutil, struct, sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DLL = os.path.join(GAME, "AoWEPACK.dll")
BAK = DLL + ".bak_abguardrec"

VA2FILE = 0x55700C00
HOOK = 0x5574F1C4
RESUME = 0x5574F1CB
CAVE_BASE, CAVE_LIMIT = 0x55811000, 0x55811100
SCRATCH = 0x558FAF40                 # BSS page slack (see docstring)
SCRATCH_RVA = SCRATCH - 0x55700000
MIN_PTR, MAX_PTR = 0x10000, 0x7F000000
NODE_MIN = 0x400000    # heap objects never sit below the exe image (2026-08-13
                       # crash: node 0xE0000 slipped the 0x10000 floor and
                       # faulted on the vtable read; this floor catches it)
NODE_MAX = 0x40000000
MAX_NODES = 32
HOOK_BYTES = (b"\xE9" + (CAVE_BASE - (HOOK + 5)).to_bytes(4, "little", signed=True)
              + b"\x90\x90")


def build_cave():
    base = CAVE_BASE
    buf = bytearray(); rel32 = []; labels = {}; j8s = []; j32s = []; calls = []

    def db(*b): buf.extend(b)
    def dd(v): buf.extend((v & 0xFFFFFFFF).to_bytes(4, "little"))
    def lab(n): labels[n] = len(buf)
    def jmp(tgt_va): db(0xE9); rel32.append((len(buf), tgt_va)); dd(0)
    def j8(op, n): db(op); j8s.append((len(buf), n)); db(0)
    def j32(cc, n): db(0x0F, cc); j32s.append((len(buf), n)); dd(0)
    def call_lab(n): db(0xE8); calls.append((len(buf), n)); dd(0)

    # ---- entry: eax=Self, edx=ability id, [esp]=caller retaddr ----
    db(0x3D); dd(MIN_PTR)            # cmp eax, MIN
    j32(0x82, "bad_self")            # jb
    db(0x3D); dd(MAX_PTR)            # cmp eax, MAX
    j32(0x83, "bad_self")            # jae
    db(0x51)                         # push ecx
    db(0x52)                         # push edx
    db(0x8B, 0x48, 0x10)             # mov ecx,[eax+0x10]   chain head
    db(0xBA); dd(MAX_NODES)          # mov edx, 32
    lab("walk")
    db(0x85, 0xC9)                   # test ecx,ecx
    j8(0x74, "ok")                   # nil terminator = healthy
    db(0x81, 0xF9); dd(NODE_MIN)     # cmp ecx, NODE_MIN (v3.1: was MIN_PTR)
    j8(0x72, "bad_node")
    db(0x81, 0xF9); dd(NODE_MAX)     # cmp ecx, NODE_MAX  (v3: tightened)
    j8(0x73, "bad_node")
    db(0x50)                         # push eax
    db(0x8B, 0x01)                   # mov eax,[ecx]        node vtable
    db(0x3D); dd(MIN_PTR)
    j8(0x72, "bad_node2")
    db(0x3D); dd(MAX_PTR)
    j8(0x73, "bad_node2")
    db(0x58)                         # pop eax
    db(0x8B, 0x49, 0x08)             # mov ecx,[ecx+8]      next
    db(0x4A)                         # dec edx
    j8(0x75, "walk")
    lab("ok")
    db(0x5A)                         # pop edx
    db(0x59)                         # pop ecx
    db(0x53, 0x56, 0x8B, 0xF2, 0x8B, 0x58, 0x10)   # displaced stock 7 bytes
    jmp(RESUME)

    lab("bad_node2")
    db(0x58)                         # pop eax   (restore Self)
    lab("bad_node")                  # ecx = bad node; stack: [id][ecx0][ret]
    call_lab("REC")
    db(0x5A)                         # pop edx
    db(0x59)                         # pop ecx
    db(0x33, 0xC0)                   # xor eax,eax
    db(0xC3)                         # ret

    lab("bad_self")                  # nothing pushed yet
    db(0x51)                         # push ecx
    db(0x52)                         # push edx    (match REC's stack shape)
    db(0xB9); dd(1)                  # mov ecx,1   marker: Self itself bad
    call_lab("REC")
    db(0x5A)                         # pop edx
    db(0x59)                         # pop ecx
    db(0x33, 0xC0)
    db(0xC3)

    # ---- REC: eax=owner, ecx=bad node/marker; stack:
    # [retREC][id][ecx0][caller_ret] -> after pushes:
    # +0 edx  +4 eax  +8 retREC  +C id  +10 ecx0  +14 caller_ret
    lab("REC")
    db(0x50)                         # push eax
    db(0x52)                         # push edx
    call_lab("L")
    lab("L")
    db(0x5A)                         # pop edx            runtime L
    db(0x81, 0xEA); dd(base + labels["L"])   # sub edx, L_static -> delta
    db(0x83, 0xBA); dd(SCRATCH + 0); db(0x00)  # cmp dword [edx+S+0],0
    j8(0x75, "rec_done")             # already recorded -> sticky
    db(0xC7, 0x82); dd(SCRATCH + 0); dd(1)     # mov dword [edx+S+0],1
    db(0x89, 0x82); dd(SCRATCH + 0x08)         # mov [edx+S+8], eax   owner
    db(0x89, 0x8A); dd(SCRATCH + 0x0C)         # mov [edx+S+C], ecx   bad node
    db(0x8B, 0x44, 0x24, 0x14)                 # mov eax,[esp+0x14]   caller
    db(0x89, 0x82); dd(SCRATCH + 0x04)         # mov [edx+S+4], eax
    db(0x8B, 0x44, 0x24, 0x0C)                 # mov eax,[esp+0x0C]   ability id
    db(0x89, 0x82); dd(SCRATCH + 0x10)         # mov [edx+S+10], eax
    db(0x89, 0x92); dd(SCRATCH + 0x14)         # mov [edx+S+14], edx  delta
    lab("rec_done")
    db(0x5A)                         # pop edx
    db(0x58)                         # pop eax
    db(0xC3)                         # ret

    for off, tgt in rel32:
        buf[off:off+4] = (tgt - (base + off + 4)).to_bytes(4, "little", signed=True)
    for off, n in j8s:
        d = labels[n] - (off + 1)
        assert -128 <= d <= 127, (n, d)
        buf[off] = d & 0xFF
    for off, n in j32s:
        buf[off:off+4] = (labels[n] - (off + 4)).to_bytes(4, "little", signed=True)
    for off, n in calls:
        buf[off:off+4] = (labels[n] - (off + 4)).to_bytes(4, "little", signed=True)
    assert base + len(buf) <= CAVE_LIMIT, hex(len(buf))
    return bytes(buf)


def old_cave():
    spec = importlib.util.spec_from_file_location(
        "oldguard", os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "build_abilitydata_owner_guard.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.build_cave()


def read_scratch():
    TH32CS_SNAPPROCESS = 2
    TH32CS_SNAPMODULE, TH32CS_SNAPMODULE32 = 8, 0x10
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

    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    pe = PE32(); pe.dwSize = ctypes.sizeof(PE32)
    pid = None
    ok = k32.Process32First(snap, ctypes.byref(pe))
    while ok:
        if pe.szExeFile.lower() == b"aowx.exe":
            pid = pe.th32ProcessID; break
        ok = k32.Process32Next(snap, ctypes.byref(pe))
    k32.CloseHandle(snap)
    if pid is None:
        print("AoWx.exe is not running"); return 1

    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, pid)
    me = ME32(); me.dwSize = ctypes.sizeof(ME32)
    modbase = None
    ok = k32.Module32First(snap, ctypes.byref(me))
    while ok:
        if me.szModule.lower() == b"aowepack.dll":
            modbase = me.modBaseAddr; break
        ok = k32.Module32Next(snap, ctypes.byref(me))
    k32.CloseHandle(snap)
    if modbase is None:
        print("AoWEPACK.dll not found in process"); return 1

    PROCESS_VM_READ, PROCESS_QUERY_INFORMATION = 0x10, 0x400
    h = k32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)
    buf = (ctypes.c_char * 24)()
    got = ctypes.c_size_t()
    addr = modbase + SCRATCH_RVA
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, 24, ctypes.byref(got)):
        print("ReadProcessMemory failed"); return 1
    k32.CloseHandle(h)
    flag, caller, owner, node, abid, delta = struct.unpack("<6I", bytes(buf))
    print(f"AoWEPACK base {modbase:#x}  scratch @{addr:#x}")
    if not flag:
        print("flag=0: no bogus GetAbilityData call recorded yet")
        return 0
    print(f"RECORDED bogus call:")
    print(f"  caller  runtime {caller:#010x}  STATIC {(caller - delta) & 0xFFFFFFFF:#010x}")
    print(f"  owner   {owner:#010x}")
    print(f"  bad     {'Self itself out of range' if node == 1 else f'chain node {node:#010x}'}")
    print(f"  ability id {abid:#x}")
    return 0


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--status"
    if mode == "--read":
        return read_scratch()

    d = bytearray(open(DLL, "rb").read())
    h_off, c_off = HOOK - VA2FILE, CAVE_BASE - VA2FILE
    cave, old = build_cave(), old_cave()
    region = bytes(d[c_off:c_off + 0x100])

    if mode == "--status":
        if bytes(d[h_off:h_off+7]) != HOOK_BYTES:
            print("hook NOT present:", bytes(d[h_off:h_off+7]).hex()); return 1
        if region[:len(cave)] == cave:
            print("v3 RECORDER applied")
        elif region[:len(old)] == old:
            print("v2 plain guard applied (recorder not installed)")
        else:
            print("UNRECOGNIZED cave contents")
        return 0

    if mode == "--apply":
        # cave slot is fully rewritten; only the hook must be as expected
        # (accepts any prior v2/v3 cave variant living in the slot)
        assert bytes(d[h_off:h_off+7]) == HOOK_BYTES, "guard hook not present"
        if not os.path.exists(BAK):
            shutil.copy2(DLL, BAK); print("backup ->", os.path.basename(BAK))
        d[c_off:c_off + 0x100] = bytes(0x100)
        d[c_off:c_off + len(cave)] = cave
        open(DLL, "wb").write(d)
        print(f"v3 recorder cave written: {len(cave)} B @{CAVE_BASE:#x}, "
              f"scratch @{SCRATCH:#x}")
        return 0

    if mode == "--revert":
        d[c_off:c_off + 0x100] = bytes(0x100)
        d[c_off:c_off + len(old)] = old
        open(DLL, "wb").write(d)
        print("v2 plain guard cave restored")
        return 0

    print(__doc__); return 1


if __name__ == "__main__":
    sys.exit(main())
