"""Attach the first-chance VEH exception logger of diag_veh_logger.py to an ALREADY
RUNNING AoWx.exe (no relaunch needed - e.g. the game is sitting on an error dialog and
the fault is expected to recur).  Usage:  python diag_veh_attach.py <pid>
Output: veh_attach_log.txt next to this script.  Same record format as veh_log.txt."""
import ctypes as C, struct, sys, time, os
from ctypes import wintypes as W
import diag_veh_logger as L

L.OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "veh_attach_log.txt")
k32, vp = L.k32, L.vp
k32.OpenProcess.restype = vp
k32.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]


def main():
    pid = int(sys.argv[1])
    hp = k32.OpenProcess(0x1FFFFF, False, pid)
    if not hp:
        L.log("OpenProcess failed %d" % C.get_last_error()); return
    nt = L.find_module(hp, "ntdll.dll")          # 32-bit copy (64-bit ones are filtered)
    add_veh = L.resolve_export(hp, nt, b"RtlAddVectoredExceptionHandler") if nt else 0
    L.log("attach pid=%d ntdll32=0x%08X RtlAddVectoredExceptionHandler=0x%08X" % (pid, nt, add_veh))
    if not add_veh:
        L.log("FATAL: cannot resolve AddVEH"); return
    region = k32.VirtualAllocEx(hp, None, 0x10000, L.MEM_CR, L.PAGE_EXEC_RW) & 0xFFFFFFFF
    H, S, COUNTER, BUSY, BUF = region, region + 0x800, region + 0x900, region + 0x904, region + 0x1000
    handler = L.build_handler(BUF, COUNTER, BUSY)
    stub = (b"\x68" + struct.pack("<I", H) + b"\x6A\x01" +
            b"\xB8" + struct.pack("<I", add_veh) + b"\xFF\xD0" + b"\xC2\x04\x00")
    n = C.c_size_t()
    k32.WriteProcessMemory(hp, C.c_void_p(H), handler, len(handler), C.byref(n))
    k32.WriteProcessMemory(hp, C.c_void_p(S), stub, len(stub), C.byref(n))
    ht = k32.CreateRemoteThread(hp, None, 0, C.c_void_p(S), None, 0, None)
    k32.WaitForSingleObject(ht, 5000); k32.CloseHandle(ht)
    L.log("VEH logger installed at 0x%08X ring 0x%08X (COUNTER 0x%08X)" % (H, BUF, COUNTER))

    mods, seen, last = [], 0, 0
    while True:
        if k32.WaitForSingleObject(hp, 0) == 0:
            L.log("game exited"); break
        if time.time() - last > 5:
            mods = L.module_map(hp); last = time.time()
        cnt = L.u32at(hp, COUNTER) or 0
        while seen < cnt:
            if cnt - seen > L.NSLOTS:
                L.log("!! ring overflow: %d lost" % (cnt - seen - L.NSLOTS)); seen = cnt - L.NSLOTS
            d = L.rpm(hp, BUF + (seen % L.NSLOTS) * L.SLOTSZ, L.SLOTSZ)
            if len(d) < L.HDR: break
            (code, xaddr, nparam, i0, i1, eip, esp, ebp, eax, ebx, esi, ecx, edx, seq) = struct.unpack_from("<14I", d, 0)
            L.log("--- exc #%d code=0x%08X addr=%s eip=%s" % (seq, code, L.sym(mods, xaddr) or "0x%08X" % xaddr, L.sym(mods, eip) or "0x%08X" % eip))
            L.log("    esp=%08X ebp=%08X eax=%08X ebx=%08X esi=%08X ecx=%08X edx=%08X" % (esp, ebp, eax, ebx, esi, ecx, edx))
            if code == 0x0EEDFADE and nparam >= 2:
                L.log("    delphi raise@%s obj=%s" % (L.sym(mods, i0) or "0x%08X" % i0, L.delphi_obj_info(hp, i1)))
            elif code == 0xC0000005:
                L.log("    AV %s at data 0x%08X" % ("write" if i0 == 1 else "read", i1))
            stk = d[L.HDR:L.HDR + L.STACKCP]
            lines = []
            for i in range(0, len(stk) - 4, 4):
                v = struct.unpack_from("<I", stk, i)[0]
                s = L.sym(mods, v)
                if not s or s.startswith(("ntdll", "KERNEL", "kernel", "USER32", "user32", "GDI32", "win32u", "IME", "MSCTF", "ddraw")):
                    continue
                pre = L.rpm(hp, v - 6, 6)
                if len(pre) == 6 and (pre[1] == 0xE8 or pre[0] == 0xE8 or 0xFF in (pre[0], pre[1], pre[3], pre[4])):
                    lines.append("      [esp+0x%03X] %s" % (i, s))
            for ln in lines[:16]:
                L.log(ln)
            if len(lines) > 16:
                L.log("      ... %d more" % (len(lines) - 16))
            seen += 1
        time.sleep(0.2)


if __name__ == "__main__":
    main()
