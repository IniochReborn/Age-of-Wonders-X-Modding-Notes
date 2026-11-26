"""Launch AoWx.exe (409 folder) with an injected VEH that LOGS every first-chance
exception to a ring buffer and continues search (game behaves normally).
Python side polls the ring, decodes each record (incl. Delphi exception object
class+message for 0x0EEDFADE), symbolizes addresses against live module list,
walks the captured stack for module return addresses. Output: veh_log.txt.
Based on diag_inject_veh.py (same WOW64 gotchas)."""
import ctypes as C
from bakpath import game_dir, game_file   # game folder = AOW_GAME_DIR or parent of patch scripts (2026-09-20)
from ctypes import wintypes as W
import struct, time, os, sys

k32 = C.WinDLL("kernel32", use_last_error=True)
vp = C.c_void_p
k32.GetProcAddress.restype = vp
k32.GetProcAddress.argtypes = [vp, C.c_char_p]
k32.VirtualAllocEx.restype = vp
k32.VirtualAllocEx.argtypes = [vp, vp, C.c_size_t, W.DWORD, W.DWORD]
k32.CreateRemoteThread.restype = vp
k32.CreateRemoteThread.argtypes = [vp, vp, C.c_size_t, vp, vp, W.DWORD, vp]
k32.WriteProcessMemory.argtypes = [vp, vp, C.c_char_p, C.c_size_t, vp]
k32.ReadProcessMemory.argtypes = [vp, vp, vp, C.c_size_t, vp]
k32.WaitForSingleObject.argtypes = [vp, W.DWORD]
k32.ResumeThread.argtypes = [vp]
k32.TerminateProcess.argtypes = [vp, W.UINT]

GAME = game_dir()
if len(sys.argv) > 1 and os.path.isdir(sys.argv[1]):
    GAME = os.path.abspath(sys.argv[1])
EXE = os.path.join(GAME, "AoWx.exe")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "veh_log.txt")
# 2026-11-07: --exe <name> launches another exe from the game folder (e.g. AoWDevX.exe - it is RUNASADMIN, so run
# this script from an ELEVATED prompt); the log then goes to veh_log_<name>.txt
if "--exe" in sys.argv:
    _n = sys.argv[sys.argv.index("--exe") + 1]
    EXE = os.path.join(GAME, _n)
    OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "veh_log_%s.txt" % os.path.splitext(_n)[0])
CMDLINE = None
if "--args" in sys.argv:                                   # e.g. --args "C:\...\map.hsm" (editor opens ParamStr(1))
    CMDLINE = '"%s" %s' % (EXE, sys.argv[sys.argv.index("--args") + 1])

CREATE_SUSPENDED = 0x4
MEM_CR = 0x3000
PAGE_EXEC_RW = 0x40
NSLOTS = 32
SLOTSZ = 0x440          # 0x40 header + 0x400 stack copy
HDR = 0x40
STACKCP = 0x400


def log(msg):
    line = "%s %s" % (time.strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    with open(OUT, "a", encoding="utf-8") as f:
        f.write(line + "\n")


class STARTUPINFO(C.Structure):
    _fields_ = [("cb", W.DWORD)] + [(n, W.LPWSTR) for n in
                ("lpReserved", "lpDesktop", "lpTitle")] + \
               [(n, W.DWORD) for n in ("dwX", "dwY", "dwXSize", "dwYSize",
                "dwXCountChars", "dwYCountChars", "dwFillAttribute", "dwFlags")] + \
               [("wShowWindow", W.WORD), ("cbReserved2", W.WORD),
                ("lpReserved2", C.POINTER(C.c_byte))] + \
               [(n, W.HANDLE) for n in ("hStdInput", "hStdOutput", "hStdError")]


class PROCESS_INFORMATION(C.Structure):
    _fields_ = [("hProcess", W.HANDLE), ("hThread", W.HANDLE),
                ("dwProcessId", W.DWORD), ("dwThreadId", W.DWORD)]


psapi = C.WinDLL("psapi", use_last_error=True)
psapi.EnumProcessModulesEx.argtypes = [vp, vp, W.DWORD, C.POINTER(W.DWORD), W.DWORD]
psapi.GetModuleBaseNameW.argtypes = [vp, vp, W.LPWSTR, W.DWORD]
psapi.GetModuleInformation.argtypes = [vp, vp, vp, W.DWORD]


class MODULEINFO(C.Structure):
    _fields_ = [("lpBaseOfDll", vp), ("SizeOfImage", W.DWORD), ("EntryPoint", vp)]


def rpm(hp, addr, size):
    buf = (C.c_ubyte * size)()
    n = C.c_size_t()
    if k32.ReadProcessMemory(hp, C.c_void_p(addr), buf, size, C.byref(n)):
        return bytes(buf[:n.value])
    return b""


def u32at(hp, addr):
    d = rpm(hp, addr, 4)
    return struct.unpack("<I", d)[0] if len(d) == 4 else None


def resolve_export(hp, base, want):
    hdr = rpm(hp, base, 0x400)
    pe = struct.unpack_from("<I", hdr, 0x3C)[0]
    exp_rva = struct.unpack_from("<I", hdr, pe + 0x78)[0]
    exp = rpm(hp, base + exp_rva, 0x28)
    nfun, nname = struct.unpack_from("<II", exp, 0x14)
    faddr, naddr, oaddr = struct.unpack_from("<III", exp, 0x1C)
    names = struct.unpack_from("<%dI" % nname, rpm(hp, base + naddr, 4 * nname), 0)
    ords = struct.unpack_from("<%dH" % nname, rpm(hp, base + oaddr, 2 * nname), 0)
    fns = struct.unpack_from("<%dI" % nfun, rpm(hp, base + faddr, 4 * nfun), 0)
    for i, nr in enumerate(names):
        nm = rpm(hp, base + nr, 64).split(b"\0")[0]
        if nm == want:
            return base + fns[ords[i]]
    return 0


def module_map(hp):
    arr = (vp * 1024)()
    need = W.DWORD()
    psapi.EnumProcessModulesEx(hp, arr, C.sizeof(arr), C.byref(need), 0x03)
    cnt = need.value // C.sizeof(vp)
    mods = []
    for i in range(cnt):
        b = arr[i]
        if not b:
            continue
        buf = C.create_unicode_buffer(260)
        psapi.GetModuleBaseNameW(hp, C.c_void_p(b), buf, 260)
        mi = MODULEINFO()
        psapi.GetModuleInformation(hp, C.c_void_p(b), C.byref(mi), C.sizeof(mi))
        if b >= 0x100000000:
            continue          # 64-bit side of the WOW64 process (ntdll/wow64*.dll) - irrelevant
        mods.append((b, mi.SizeOfImage, buf.value))
    return sorted(mods)


def sym(mods, a):
    for b, s, nm in mods:
        if b <= a < b + s:
            return "%s+0x%X" % (nm, a - b)
    return None


def find_module(hp, name):
    for b, s, nm in module_map(hp):
        if nm.lower() == name.lower():
            return b
    return 0


def probe_addveh():
    si = STARTUPINFO(); si.cb = C.sizeof(si)
    pi = PROCESS_INFORMATION()
    k32.CreateProcessW(EXE, None, None, None, False, 0, None, GAME,
                       C.byref(si), C.byref(pi))
    hp = pi.hProcess
    nt = 0
    for _ in range(50):
        time.sleep(0.1)
        nt = find_module(hp, "ntdll.dll")
        if nt:
            break
    addr = resolve_export(hp, nt, b"RtlAddVectoredExceptionHandler") if nt else 0
    k32.TerminateProcess(hp, 1)
    k32.CloseHandle(pi.hThread); k32.CloseHandle(pi.hProcess)
    return addr & 0xFFFFFFFF


def build_handler(BUF, COUNTER, BUSY):
    """VEH: log every exception (except 0x406D1388 SetThreadName) to ring, continue search.
    Header dwords: 0 code, 1 ExceptionAddress, 2 NumberParameters, 3 Info0, 4 Info1,
    5 Eip, 6 Esp, 7 Ebp, 8 Eax, 9 Ebx, 10 Esi, 11 Ecx, 12 Edx, 13 seq. Then 0x400 stack."""
    def u32(v): return struct.pack("<I", v & 0xFFFFFFFF)
    b = b""
    # reentrancy guard
    b += b"\x83\x3D" + u32(BUSY) + b"\x00"          # cmp dword [BUSY],0
    jnz_busy_at = len(b); b += b"\x0F\x85" + b"\x00\x00\x00\x00"  # jnz pass (rel32, fix)
    b += b"\xC7\x05" + u32(BUSY) + u32(1)           # mov [BUSY],1
    b += b"\x56\x57\x53"                            # push esi/edi/ebx
    b += b"\x8B\x44\x24\x10"                        # mov eax,[esp+10h] ExceptionInfo
    b += b"\x8B\x08"                                # mov ecx,[eax] rec
    b += b"\x8B\x50\x04"                            # mov edx,[eax+4] ctx
    b += b"\x81\x39" + u32(0x406D1388)              # cmp [ecx],406D1388h
    je_skip_at = len(b); b += b"\x0F\x84" + b"\x00\x00\x00\x00"   # je unbusy
    # slot = BUF + (seq & 31)*SLOTSZ
    b += b"\xA1" + u32(COUNTER)                     # mov eax,[COUNTER]
    b += b"\x8B\xD8"                                # mov ebx,eax (seq)
    b += b"\x83\xE0\x1F"                            # and eax,1Fh
    b += b"\x69\xC0" + u32(SLOTSZ)                  # imul eax,eax,SLOTSZ
    b += b"\x05" + u32(BUF)                         # add eax,BUF
    # header
    def cpy(srcreg_off_to_slot):  # helper composed inline below instead
        pass
    def rec_to_slot(recoff, slotoff):
        return b"\x8B\x71" + bytes([recoff]) + b"\x89\x70" + bytes([slotoff])
    def ctx_to_slot(ctxoff, slotoff):
        return (b"\x8B\xB2" + u32(ctxoff)) + b"\x89\x70" + bytes([slotoff])
    b += b"\x8B\x31" + b"\x89\x30"                  # mov esi,[ecx]; mov [eax],esi (code)
    b += rec_to_slot(0x0C, 0x04)                    # ExceptionAddress
    b += rec_to_slot(0x10, 0x08)                    # NumberParameters
    b += rec_to_slot(0x14, 0x0C)                    # Info[0]
    b += rec_to_slot(0x18, 0x10)                    # Info[1]
    b += ctx_to_slot(0xB8, 0x14)                    # Eip
    b += ctx_to_slot(0xC4, 0x18)                    # Esp
    b += ctx_to_slot(0xB4, 0x1C)                    # Ebp
    b += ctx_to_slot(0xB0, 0x20)                    # Eax
    b += ctx_to_slot(0xA4, 0x24)                    # Ebx
    b += ctx_to_slot(0xA0, 0x28)                    # Esi
    b += ctx_to_slot(0xAC, 0x2C)                    # Ecx
    b += ctx_to_slot(0xA8, 0x30)                    # Edx
    b += b"\x89\x58\x34"                            # mov [eax+34h],ebx (seq)
    # copy 0x100 dwords of stack from ctx.Esp
    b += b"\x8B\xB2" + u32(0xC4)                    # mov esi,[edx+0C4h]
    b += b"\x8D\x78" + bytes([HDR])                 # lea edi,[eax+HDR]
    b += b"\xB9" + u32(STACKCP // 4)                # mov ecx,100h
    b += b"\xF3\xA5"                                # rep movsd
    # publish: increment COUNTER last
    b += b"\xFF\x05" + u32(COUNTER)                 # inc dword [COUNTER]
    unbusy_off = len(b)
    b += b"\x5B\x5F\x5E"                            # pop ebx/edi/esi
    b += b"\xC7\x05" + u32(BUSY) + u32(0)           # mov [BUSY],0
    pass_off = len(b)
    b += b"\x33\xC0"                                # xor eax,eax CONTINUE_SEARCH
    b += b"\xC2\x04\x00"                            # ret 4
    b = bytearray(b)
    struct.pack_into("<i", b, jnz_busy_at + 2, pass_off - (jnz_busy_at + 6))
    struct.pack_into("<i", b, je_skip_at + 2, unbusy_off - (je_skip_at + 6))
    return bytes(b)


def delphi_obj_info(hp, obj):
    """class name + Message string of a Delphi exception object."""
    if not obj:
        return "nil"
    vmt = u32at(hp, obj)
    if not vmt:
        return "obj@0x%08X unreadable" % obj
    name = "?"
    p = u32at(hp, vmt - 32)
    if p:
        d = rpm(hp, p, 64)
        if d and 0 < d[0] < 64:
            name = d[1:1 + d[0]].decode("latin-1")
    msg = ""
    mp = u32at(hp, obj + 4)
    if mp:
        raw = rpm(hp, mp, 256)
        msg = raw.split(b"\0")[0].decode("latin-1", "replace")
    return "%s: %r" % (name, msg)


def main():
    attach = int(sys.argv[sys.argv.index("--pid") + 1]) if "--pid" in sys.argv else 0   # 2026-11-13: attach to a running game
    pi = PROCESS_INFORMATION()
    if attach:
        k32.OpenProcess.restype = vp
        hp = k32.OpenProcess(0x1F0FFF, False, attach)
        if not hp:
            log("OpenProcess failed %d" % C.get_last_error()); return
        add_veh = resolve_export(hp, find_module(hp, "ntdll.dll"), b"RtlAddVectoredExceptionHandler") & 0xFFFFFFFF
        log("attached to pid=%d, AddVEH @ 0x%08X" % (attach, add_veh))
        if not add_veh:
            return
    else:
        add_veh = probe_addveh()
        log("RtlAddVectoredExceptionHandler @ 0x%08X" % add_veh)
        if not add_veh:
            log("FATAL: cannot resolve AddVEH")
            return
        si = STARTUPINFO(); si.cb = C.sizeof(si)
        cl = C.create_unicode_buffer(CMDLINE) if CMDLINE else None
        if not k32.CreateProcessW(EXE, cl, None, None, False, CREATE_SUSPENDED,
                                  None, GAME, C.byref(si), C.byref(pi)):
            log("CreateProcess failed %d" % C.get_last_error())
            return
        hp = pi.hProcess
        log("launched suspended pid=%d" % pi.dwProcessId)
    region = k32.VirtualAllocEx(hp, None, 0x10000, MEM_CR, PAGE_EXEC_RW)
    region &= 0xFFFFFFFF
    H = region                    # handler code
    S = region + 0x800            # install stub
    COUNTER = region + 0x900
    BUSY = region + 0x904
    BUF = region + 0x1000         # ring 32*0x440 = 0x8800
    handler = build_handler(BUF, COUNTER, BUSY)
    stub = (b"\x68" + struct.pack("<I", H) + b"\x6A\x01" +
            b"\xB8" + struct.pack("<I", add_veh) + b"\xFF\xD0" + b"\xC2\x04\x00")
    n = C.c_size_t()
    k32.WriteProcessMemory(hp, C.c_void_p(H), handler, len(handler), C.byref(n))
    k32.WriteProcessMemory(hp, C.c_void_p(S), stub, len(stub), C.byref(n))
    ht = k32.CreateRemoteThread(hp, None, 0, C.c_void_p(S), None, 0, None)
    k32.WaitForSingleObject(ht, 5000)
    k32.CloseHandle(ht)
    log("VEH logger installed at 0x%08X ring 0x%08X; resuming game" % (H, BUF))
    if not attach:
        k32.ResumeThread(pi.hThread)

    mods = []
    seen = 0
    last_modrefresh = 0
    while True:
        if k32.WaitForSingleObject(hp, 0) == 0:
            ec = W.DWORD()
            k32.GetExitCodeProcess(hp, C.byref(ec))
            log("game exited, code=%d (0x%08X)" % (
                C.c_int32(ec.value).value, ec.value))
            break
        now = time.time()
        if now - last_modrefresh > 5:
            mods = module_map(hp)
            last_modrefresh = now
        cnt = u32at(hp, COUNTER) or 0
        while seen < cnt:
            if cnt - seen > NSLOTS:
                log("!! ring overflow: %d records lost" % (cnt - seen - NSLOTS))
                seen = cnt - NSLOTS
            slot = BUF + (seen % NSLOTS) * SLOTSZ
            d = rpm(hp, slot, SLOTSZ)
            if len(d) < HDR:
                break
            (code, xaddr, nparam, i0, i1, eip, esp, ebp, eax, ebx,
             esi, ecx, edx, seq) = struct.unpack_from("<14I", d, 0)
            smod = sym(mods, xaddr) or "0x%08X" % xaddr
            log("--- exc #%d code=0x%08X addr=%s eip=%s" %
                (seq, code, smod, sym(mods, eip) or "0x%08X" % eip))
            log("    esp=%08X ebp=%08X eax=%08X ebx=%08X esi=%08X ecx=%08X edx=%08X"
                % (esp, ebp, eax, ebx, esi, ecx, edx))
            if code == 0x0EEDFADE and nparam >= 2:
                # Delphi: Info[0]=raise addr, Info[1]=exception object
                log("    delphi raise@%s obj=%s" %
                    (sym(mods, i0) or "0x%08X" % i0, delphi_obj_info(hp, i1)))
            elif code == 0xC0000005:
                log("    AV %s at data 0x%08X" %
                    ("write" if i0 == 1 else "read", i1))
            # stack return addresses into modules
            stk = d[HDR:HDR + STACKCP]
            lines = []
            for i in range(0, len(stk) - 4, 4):
                v = struct.unpack_from("<I", stk, i)[0]
                s = sym(mods, v)
                if not s or s.startswith(("ntdll", "KERNEL", "kernel", "USER32",
                                          "user32", "GDI32", "win32u", "IME",
                                          "MSCTF", "ddraw")):
                    continue
                pre = rpm(hp, v - 6, 6)
                iscall = len(pre) == 6 and (pre[1] == 0xE8 or pre[0] == 0xE8 or
                                            0xFF in (pre[0], pre[1], pre[3], pre[4]))
                if iscall:
                    lines.append("      [esp+0x%03X] %s" % (i, s))
            for ln in lines[:14]:
                log(ln)
            if len(lines) > 14:
                log("      ... %d more module rets" % (len(lines) - 14))
            seen += 1
        time.sleep(0.2)


if __name__ == "__main__":
    main()
