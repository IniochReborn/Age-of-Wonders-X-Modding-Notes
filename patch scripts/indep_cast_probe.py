"""Read-only live probe for patch_indep_hero_spells_v2 (2026-11-14): waits for AoWx.exe, then every 4 s reports changes of
  * the stand-in magic control (pointer slot AoWEPACK 0x558E9DF0: spell-id list, mana)  -> proves the GetPlayer path ran
  * every THero / TLeader with owner byte 0xFF (independent): name, casting points +0x80, channel +0x84 / +0x88
  * the patched AoWTCPCK bytes actually loaded in the process.
Usage: py -3.10 indep_cast_probe.py [minutes]   (stops by itself; touches nothing in the game)"""
import ctypes, ctypes.wintypes as wt, struct, subprocess, sys, time

k32 = ctypes.windll.kernel32
psapi = ctypes.windll.psapi
k32.OpenProcess.restype = wt.HANDLE
k32.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
psapi.EnumProcessModulesEx.argtypes = [wt.HANDLE, ctypes.POINTER(ctypes.c_void_p), wt.DWORD, ctypes.POINTER(wt.DWORD), wt.DWORD]
psapi.GetModuleBaseNameW.argtypes = [wt.HANDLE, ctypes.c_void_p, wt.LPWSTR, wt.DWORD]


class MBI(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_void_p), ("AllocationBase", ctypes.c_void_p), ("AllocationProtect", wt.DWORD),
                ("PartitionId", wt.WORD), ("RegionSize", ctypes.c_size_t), ("State", wt.DWORD),
                ("Protect", wt.DWORD), ("Type", wt.DWORD)]


k32.VirtualQueryEx.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.POINTER(MBI), ctypes.c_size_t]
VMT = {"THero": 0x55711FEC, "TLeader": 0x55712238}


def pid_of():
    o = subprocess.run(["tasklist", "/FI", "IMAGENAME eq AoWx.exe", "/FO", "CSV", "/NH"], capture_output=True, text=True).stdout
    for l in o.splitlines():
        if l.startswith('"AoWx.exe"'):
            return int(l.split('","')[1])
    return 0


def main():
    mins = float(sys.argv[1]) if len(sys.argv) > 1 else 20
    t_end = time.time() + mins * 60
    pid = 0
    while time.time() < t_end and not pid:
        pid = pid_of()
        if not pid:
            time.sleep(3)
    if not pid:
        print("AoWx.exe never started"); return 1
    h = k32.OpenProcess(0x0410, False, pid)
    mods = (ctypes.c_void_p * 1024)(); need = wt.DWORD()
    base = {}
    for _ in range(20):
        psapi.EnumProcessModulesEx(h, mods, ctypes.sizeof(mods), ctypes.byref(need), 1)
        for m in mods[:need.value // ctypes.sizeof(ctypes.c_void_p)]:
            nm = ctypes.create_unicode_buffer(260); psapi.GetModuleBaseNameW(h, m, nm, 260); base[nm.value.lower()] = m
        if "aowepack.dll" in base and "aowtcpck.dll" in base:
            break
        time.sleep(2)
    ep, tc = base["aowepack.dll"], base["aowtcpck.dll"]

    def rd(a, n):
        buf = ctypes.create_string_buffer(n); got = ctypes.c_size_t()
        if not k32.ReadProcessMemory(h, ctypes.c_void_p(a), buf, n, ctypes.byref(got)):
            return None
        return buf.raw

    def u32(a):
        b = rd(a, 4)
        return struct.unpack("<I", b)[0] if b else 0

    def astr(p):
        if not p:
            return ""
        n = u32(p - 4)
        return (rd(p, n) or b"").decode("latin1") if 0 < n < 80 else "?"

    print("pid %d AoWEPACK %#x AoWTCPCK %#x" % (pid, ep, tc))
    print("tcpck loops:", [u32(tc + a - 0x400000 + 3) for a in (0x4188D4, 0x418C9B, 0x419076, 0x4196F4)],
          "gates:", [(rd(tc + a - 0x400000, 6) or b"").hex() for a in (0x418755, 0x418BA2, 0x4195EB)],
          "getplayer exit:", (rd(ep + 0x544E6, 6) or b"").hex())
    last_slot, last_h, seen_slot_at = None, None, None
    pats = {struct.pack("<I", v - 0x55700000 + ep): k for k, v in VMT.items()}
    while time.time() < t_end and pid_of() == pid:
        blk = u32(ep + 0x1E9DF0)
        if blk:
            cnt = u32(blk + 0x208)
            st = (blk, cnt, tuple(u32(blk + 0x210 + 4 * i) for i in range(min(cnt, 16))), u32(blk + 0x124))
        else:
            st = None
        if st != last_slot:
            print("[%s] stand-in: %s" % (time.strftime("%H:%M:%S"), "not created" if st is None else "blk %#x spells %d %s mana %d" % st))
            last_slot = st
            if st and seen_slot_at is None:
                seen_slot_at = time.time()
        heroes = []
        addr, mbi = 0x10000, MBI()
        while addr < 0x7FFF0000 and k32.VirtualQueryEx(h, ctypes.c_void_p(addr), ctypes.byref(mbi), ctypes.sizeof(mbi)):
            size = mbi.RegionSize
            if mbi.State == 0x1000 and mbi.Protect in (0x04, 0x40) and mbi.Type == 0x20000:
                blob = rd(addr, size)
                if blob:
                    for pat, k in pats.items():
                        i = blob.find(pat)
                        while i >= 0:
                            if i % 4 == 0 and i + 0x90 <= len(blob) and blob[i + 0x24] == 0xFF:
                                heroes.append((k, addr + i, astr(struct.unpack_from("<I", blob, i + 0x60)[0]),
                                               struct.unpack_from("<b", blob, i + 0x80)[0],
                                               struct.unpack_from("<I", blob, i + 0x84)[0],
                                               struct.unpack_from("<I", blob, i + 0x88)[0]))
                            i = blob.find(pat, i + 4)
            addr += size
        hs = tuple(sorted(heroes))
        if hs != last_h:
            print("[%s] independent heroes: %d" % (time.strftime("%H:%M:%S"), len(hs)))
            for k, a, nm, cp, ch, ch2 in hs[:40]:
                print("    %s @%#x '%s' casting points %d  +0x84 %#x  +0x88 %d" % (k, a, nm, cp, ch, ch2))
            last_h = hs
        sys.stdout.flush()
        if seen_slot_at and time.time() - seen_slot_at > 120:
            print("stand-in seen for 2 minutes - stopping"); break
        time.sleep(4)
    print("probe done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
