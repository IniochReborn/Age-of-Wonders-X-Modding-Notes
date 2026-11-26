"""Launch AoWx.exe SUSPENDED, inject a vectored-exception-handler shellcode that
freezes on the fatal AV at vcl30+0x3924 with the full context+stack captured,
resume, then read the capture. In-process => normal Delphi heap => real crash."""
import ctypes as C
from bakpath import game_dir, game_file   # game folder = AOW_GAME_DIR or parent of patch scripts (2026-09-20)
from ctypes import wintypes as W
import struct, time, os

k32 = C.WinDLL("kernel32", use_last_error=True)
vp = C.c_void_p
k32.GetProcAddress.restype = vp
k32.GetProcAddress.argtypes = [vp, C.c_char_p]
k32.GetModuleHandleW.restype = vp
k32.GetModuleHandleW.argtypes = [W.LPCWSTR]
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
EXE = os.path.join(GAME, "AoWx.exe")
VCL_FAULT = 0x41303924            # stable this boot

CREATE_SUSPENDED = 0x4
MEM_COMMIT_RESERVE = 0x3000
PAGE_EXEC_RW = 0x40


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


def rpm_raw(hp, addr, size):
    buf = (C.c_ubyte * size)()
    n = C.c_size_t()
    if k32.ReadProcessMemory(hp, C.c_void_p(addr), buf, size, C.byref(n)):
        return bytes(buf[:n.value])
    return b""


def resolve_export(hp, base, want):
    """Parse a module's PE export table in the target to find `want`'s VA."""
    hdr = rpm_raw(hp, base, 0x400)
    pe = struct.unpack_from("<I", hdr, 0x3C)[0]
    exp_rva = struct.unpack_from("<I", hdr, pe + 0x78)[0]
    exp = rpm_raw(hp, base + exp_rva, 0x28)
    nfun, nname = struct.unpack_from("<II", exp, 0x14)
    funcs = struct.unpack_from("<III", exp, 0x1C)   # AddrOfFuncs, Names, Ordinals
    faddr, naddr, oaddr = funcs
    names = struct.unpack_from("<%dI" % nname, rpm_raw(hp, base + naddr, 4 * nname), 0)
    ords = struct.unpack_from("<%dH" % nname, rpm_raw(hp, base + oaddr, 2 * nname), 0)
    fns = struct.unpack_from("<%dI" % nfun, rpm_raw(hp, base + faddr, 4 * nfun), 0)
    for i, nr in enumerate(names):
        nm = rpm_raw(hp, base + nr, 40).split(b"\0")[0]
        if nm == want:
            return base + fns[ords[i]]
    return 0


def find_module(hp, name):
    arr = (vp * 512)()
    need = W.DWORD()
    psapi.EnumProcessModulesEx(hp, arr, C.sizeof(arr), C.byref(need), 0x03)
    cnt = need.value // C.sizeof(vp)
    for i in range(cnt):
        b = arr[i]
        if not b:
            continue
        buf = C.create_unicode_buffer(260)
        psapi.GetModuleBaseNameW(hp, C.c_void_p(b), buf, 260)
        if buf.value.lower() == name.lower():
            return b & 0xFFFFFFFF
    return 0


def build_handler(BUF, FLAG):
    """Assemble the VEH. Layout offsets resolved against absolute BUF/FLAG."""
    def u32(v):
        return struct.pack("<I", v & 0xFFFFFFFF)
    body = b""
    body += b"\x8B\x44\x24\x04"                 # mov eax,[esp+4]  ExceptionInfo
    body += b"\x8B\x08"                         # mov ecx,[eax]    ExceptionRecord
    body += b"\x81\x39" + u32(0xC0000005)       # cmp [ecx],AV
    jne1_at = len(body); body += b"\x75\x00"    # jne pass (fix later)
    body += b"\x8B\x51\x18"                     # mov edx,[ecx+18h] fault address
    body += b"\x81\xFA" + u32(0x00100000)       # cmp edx,00100000h
    jae2_at = len(body); body += b"\x73\x00"    # jae pass  (fault>=1MB => not nil deref)
    body += b"\x8B\x50\x04"                     # mov edx,[eax+4]  ContextRecord
    body += b"\x56\x57"                         # push esi; push edi
    body += b"\x8B\xF2"                         # mov esi,edx
    body += b"\xBF" + u32(BUF)                  # mov edi,BUF
    body += b"\xB9" + u32(0xB3)                 # mov ecx,0B3h (context dwords)
    body += b"\xF3\xA5"                         # rep movsd
    body += b"\x8B\x35" + u32(BUF + 0xC4)       # mov esi,[BUF+0C4h]  Esp
    body += b"\xBF" + u32(BUF + 0x300)          # mov edi,BUF+300h
    body += b"\xB9" + u32(0x200)                # mov ecx,200h (2KB stack)
    body += b"\xF3\xA5"                         # rep movsd
    body += b"\xC7\x05" + u32(FLAG) + u32(1)    # mov dword [FLAG],1
    body += b"\xEB\xFE"                         # spin: jmp $
    pass_off = len(body)
    body += b"\x33\xC0"                         # xor eax,eax  (CONTINUE_SEARCH)
    body += b"\xC2\x04\x00"                     # ret 4
    body = bytearray(body)
    body[jne1_at + 1] = (pass_off - (jne1_at + 2)) & 0xFF
    body[jae2_at + 1] = (pass_off - (jae2_at + 2)) & 0xFF
    return bytes(body)


def probe_addveh():
    """Phase 1: launch AoWx briefly so its 32-bit ntdll loads, resolve
    RtlAddVectoredExceptionHandler (boot-consistent base), kill."""
    si = STARTUPINFO(); si.cb = C.sizeof(si)
    pi = PROCESS_INFORMATION()
    k32.CreateProcessW(EXE, None, None, None, False, 0, None, GAME,
                       C.byref(si), C.byref(pi))
    hp = pi.hProcess
    nt = 0
    for _ in range(30):
        time.sleep(0.1)
        nt = find_module(hp, "ntdll.dll")
        if nt:
            break
    addr = resolve_export(hp, nt, b"RtlAddVectoredExceptionHandler") if nt else 0
    k32.TerminateProcess(hp, 1)
    return nt & 0xFFFFFFFF, addr & 0xFFFFFFFF


def main():
    ntbase, add_veh = probe_addveh()
    print("ntdll@0x%08X  RtlAddVectoredExceptionHandler@0x%08X" % (ntbase, add_veh))
    if not add_veh:
        print("could not resolve RtlAddVectoredExceptionHandler"); return
    si = STARTUPINFO(); si.cb = C.sizeof(si)
    pi = PROCESS_INFORMATION()
    if not k32.CreateProcessW(EXE, None, None, None, False, CREATE_SUSPENDED,
                              None, GAME, C.byref(si), C.byref(pi)):
        print("CreateProcess failed", C.get_last_error()); return
    hp = pi.hProcess
    region = k32.VirtualAllocEx(hp, None, 0x2000, MEM_COMMIT_RESERVE, PAGE_EXEC_RW)
    region &= 0xFFFFFFFF
    H = region
    S = region + 0x100
    BUF = region + 0x400
    FLAG = region + 0x1C00
    handler = build_handler(BUF, FLAG)
    stub = (b"\x68" + struct.pack("<I", H) +            # push H
            b"\x6A\x01" +                                # push 1
            b"\xB8" + struct.pack("<I", add_veh & 0xFFFFFFFF) +  # mov eax,AddVEH
            b"\xFF\xD0" +                                # call eax
            b"\xC2\x04\x00")                             # ret 4
    def write(addr, data):
        n = C.c_size_t()
        k32.WriteProcessMemory(hp, C.c_void_p(addr), data, len(data), C.byref(n))
    write(H, handler)
    write(S, stub)
    # run the install stub, wait for it to finish
    ht = k32.CreateRemoteThread(hp, None, 0, C.c_void_p(S), None, 0, None)
    k32.WaitForSingleObject(ht, 5000)
    k32.CloseHandle(ht)
    print("VEH installed; resuming game")
    k32.ResumeThread(pi.hThread)
    # poll FLAG
    flagbuf = (C.c_uint * 1)()
    n = C.c_size_t()
    for _ in range(200):
        time.sleep(0.1)
        k32.ReadProcessMemory(hp, C.c_void_p(FLAG), flagbuf, 4, C.byref(n))
        if flagbuf[0] == 1:
            print("FATAL fault captured!")
            break
    else:
        print("no capture in 20s (did not fault at vcl30+0x3924)")
        k32.TerminateProcess(hp, 1); return
    ctx = (C.c_ubyte * 0x2CC)()
    k32.ReadProcessMemory(hp, C.c_void_p(BUF), ctx, 0x2CC, C.byref(n))
    def dw(off):
        return struct.unpack_from("<I", bytes(ctx), off)[0]
    regs = dict(Edi=dw(0x9C), Esi=dw(0xA0), Ebx=dw(0xA4), Edx=dw(0xA8),
                Ecx=dw(0xAC), Eax=dw(0xB0), Ebp=dw(0xB4), Eip=dw(0xB8),
                Esp=dw(0xC4))
    print("  " + "  ".join("%s=%08X" % (k, v) for k, v in regs.items()))

    class MBI2(C.Structure):
        _fields_ = [("BaseAddress", vp), ("AllocationBase", vp),
                    ("AllocationProtect", W.DWORD), ("RegionSize", C.c_size_t),
                    ("State", W.DWORD), ("Protect", W.DWORD), ("Type", W.DWORD)]
    k32.VirtualQueryEx.argtypes = [vp, vp, C.POINTER(MBI2), C.c_size_t]
    mbi = MBI2()
    k32.VirtualQueryEx(hp, C.c_void_p(regs["Eip"]), C.byref(mbi), C.sizeof(mbi))
    ab = (mbi.AllocationBase or 0) & 0xFFFFFFFF
    print("  fault module AllocBase=0x%08X  eip=module+0x%X" % (ab, regs["Eip"] - ab))
    print("  bytes @eip-8: %s" % rpm_raw(hp, regs["Eip"] - 8, 24).hex())

    def classname(obj):
        vt = rpm_raw(hp, obj, 4)
        if len(vt) < 4:
            return None
        vmt = struct.unpack("<I", vt)[0]
        for delta in (-0x20, -0x38, -0x28, 0x2C):     # Delphi3 vmtClassName candidates
            p = rpm_raw(hp, vmt + delta, 4)
            if len(p) < 4:
                continue
            sp = struct.unpack("<I", p)[0]
            s = rpm_raw(hp, sp, 40)
            if s and 1 <= s[0] < 40:
                nm = s[1:1 + s[0]]
                if all(32 <= c < 127 for c in nm):
                    return "vmt=0x%08X %+d -> %s" % (vmt, delta, nm.decode())
        return "vmt=0x%08X (name not found)" % vmt
    for rn in ("Ebx", "Esi", "Ecx"):
        print("  self(%s=0x%08X) class: %s"
              % (rn, regs[rn], classname(regs[rn])))
    # dump the object's fields so we can see +0x64
    obj = rpm_raw(hp, regs["Ebx"], 0x90)
    print("  object dwords: " + " ".join("%08X" % struct.unpack_from("<I", obj, k)[0]
                                         for k in range(0, min(len(obj), 0x88), 4)))
    # the faulting thread is frozen (spinning in the VEH), so read its LIVE
    # stack directly, as deep as we like
    STK = 0x4000
    sb = rpm_raw(hp, regs["Esp"], STK)
    KNOWN = {0x400000: "AoWx.exe", 0x41300000: "vcl30", 0x55000000: "Gfxepack",
             0x55100000: "Dcpack", 0x55200000: "Ilpack", 0x55400000: "SoundP",
             0x55500000: "Enginep.dpl", 0x55600000: "HSEPack", 0x55700000: "AoWEPACK.dll",
             0x55800000: "Network", 0x59700000: "AoWTools", 0x59800000: "aowInt"}

    def own(a):
        bs = sorted(KNOWN)
        for i, b in enumerate(bs):
            nx = bs[i + 1] if i + 1 < len(bs) else b + 0x400000
            if b <= a < nx:
                return KNOWN[b], b
        return None, 0
    esp = regs["Esp"]

    def at(addr):
        off = addr - esp
        if 0 <= off < len(sb) - 4:
            return struct.unpack_from("<I", sb, off)[0]
        return rpm_raw(hp, addr, 4)[:4] and struct.unpack("<I", rpm_raw(hp, addr, 4))[0]

    print("  EBP-chain call frames:")
    ebp = regs["Ebp"]
    for depth in range(24):
        if not (esp - 0x10 <= ebp < esp + len(sb)):
            break
        ret = at(ebp + 4)
        nxt = at(ebp)
        if ret is None:
            break
        nm, b = own(ret)
        tag = ("%s+0x%X" % (nm, ret - b)) if nm else "0x%08X (non-game)" % ret
        star = "  <<< GAME" if nm and nm not in ("vcl30", "VCLDB30", "VCLX30") else ""
        print("    #%-2d ebp=0x%08X ret=0x%08X  %s%s" % (depth, ebp, ret, tag, star))
        if not nxt or nxt <= ebp:
            break
        ebp = nxt
    CODE = [(0x401000, 0x459000, "AoWx.exe"),
            (0x55501000, 0x55548000, "Enginep.dpl"),
            (0x55701000, 0x558E8000, "AoWEPACK.dll"),
            (0x59801000, 0x59900000, "aowInt.dpl"),
            (0x55001000, 0x55100000, "Gfxepack.dpl"),
            (0x55201000, 0x5522d000, "Ilpack.dpl")]

    def code_owner(a):
        for lo, hi, nm in CODE:
            if lo <= a < hi:
                return nm, lo & ~0xFFFFF if False else (a - (a - lo) if False else lo)
        return None, 0

    print("  return addresses into GAME code (call-preceded), stack order:")
    for i in range(0, len(sb) - 4, 4):
        v = struct.unpack_from("<I", sb, i)[0]
        hit = None
        for lo, hi, nm in CODE:
            if lo <= v < hi:
                hit = (nm, lo)
                break
        if not hit:
            continue
        pre = rpm_raw(hp, v - 6, 6)
        if len(pre) < 6:
            continue
        call = None
        if pre[1] == 0xE8:
            tgt = (v + struct.unpack("<i", pre[2:6])[0]) & 0xFFFFFFFF
            call = "call ->0x%08X" % tgt
        elif pre[4] == 0xFF and (pre[5] & 0x38) in (0x10, 0x18):
            call = "icall [reg]"
        elif pre[3] == 0xFF and (pre[4] & 0x38) in (0x10, 0x18):
            call = "icall [reg+d8]"
        elif pre[0] == 0xFF and (pre[1] & 0x38) in (0x10, 0x18):
            call = "icall"
        if call:
            base = KNOWN.get(hit[1] & 0xFFF00000, None)
            modbase = {"AoWx.exe": 0x400000, "Enginep.dpl": 0x55500000,
                       "AoWEPACK.dll": 0x55700000, "aowInt.dpl": 0x59800000,
                       "Gfxepack.dpl": 0x55000000, "Ilpack.dpl": 0x55200000}[hit[0]]
            print("    [esp+0x%04X] 0x%08X  %s+0x%X   %s"
                  % (i, v, hit[0], v - modbase, call))
    # Find where the garbage value (=array[6]) is STORED: that slot is
    # array_base + 6*4, with 6 valid object pointers just before it.
    print("\n  scanning memory for the garbage value 0x%08X (= a slot holding it):"
          % regs["Eax"])
    target_val = regs["Eax"]

    class MBI(C.Structure):
        _fields_ = [("BaseAddress", vp), ("AllocationBase", vp),
                    ("AllocationProtect", W.DWORD), ("RegionSize", C.c_size_t),
                    ("State", W.DWORD), ("Protect", W.DWORD), ("Type", W.DWORD)]
    k32.VirtualQueryEx.argtypes = [vp, vp, C.POINTER(MBI), C.c_size_t]
    addr = 0x10000
    hits = 0
    while addr < 0x7F000000 and hits < 12:
        mbi = MBI()
        if not k32.VirtualQueryEx(hp, C.c_void_p(addr), C.byref(mbi), C.sizeof(mbi)):
            break
        rs = mbi.RegionSize
        if mbi.State == 0x1000 and (mbi.Protect & 0x04 or mbi.Protect & 0x40 or mbi.Protect & 0x02):
            data = rpm_raw(hp, addr, min(rs, 0x400000))
            start = 0
            while True:
                j = data.find(struct.pack("<I", target_val), start)
                if j < 0 or j % 4:
                    if j < 0:
                        break
                    start = j + 1
                    continue
                slot = addr + j
                # dump the 8 dwords ending at this slot (candidate array tail)
                ctxd = rpm_raw(hp, slot - 24, 48)
                dwords = struct.unpack_from("<12I", ctxd, 0) if len(ctxd) >= 48 else ()
                # heuristic: preceding dwords look like heap object pointers?
                pre6 = dwords[:6]
                looks = sum(1 for x in pre6 if 0x00400000 <= x <= 0x02000000)
                if looks >= 3:
                    print("    slot 0x%08X  (array_base~0x%08X)  preceding: %s"
                          % (slot, slot - 24, " ".join("%08X" % x for x in dwords)))
                    hits += 1
                start = j + 4
        addr += rs
    if not hits:
        print("    (no plausible array slot found)")
    k32.TerminateProcess(hp, 1)


if __name__ == "__main__":
    main()
