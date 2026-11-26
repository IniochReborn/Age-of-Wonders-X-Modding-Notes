# -*- coding: utf-8 -*-
"""Dump the token-control queues of running AoWx.exe processes (frozen at OOS).

Walks: map=[0x558FA040] -> tokman=[map+0x23C]; executer=[tokman+4]
(executed count [exec+0x18], lock [exec+0x4C]); TC list = TList [tokman+0x10]
(data [+4], count [+8]).  Per TC: player idx [tc+0xC], pending event list
[tc+4] -> inner [tel+8] -> (vcall GetCount equivalent: [[tel+8]+8] count via
[inner+8]+8 pattern; data [[tel+8]+8]+4).  Each pending token event's VMT is
matched against known class-ref slots to name it; move TEs get their path
first-hex printed.  Comm status per player from the pcc chain."""
import ctypes
import ctypes.wintypes as wt
import subprocess

k32 = ctypes.windll.kernel32
psapi = ctypes.windll.psapi

# classref slots in AoWEPACK (RVA = VA - 0x55700000): slot holds VMT ptr
CLASSREFS = {
    0x1C5E4: "TArmyDefaultMoveTE",
    0x1C994: "TArmyCombatMoveTE",
    0x1C6EC: "TArmyNegotiateMoveTE",
    0x1C7F8: "TArmyCombineMoveTE",
    0x1C3C8: "TMultiMoveTE",
}


def rd(h, addr, n):
    buf = ctypes.create_string_buffer(n)
    got = ctypes.c_size_t()
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, n, ctypes.byref(got)):
        return None
    return buf.raw


def find_procs():
    out = subprocess.check_output(
        ["tasklist", "/FI", "IMAGENAME eq AoWx.exe", "/FO", "CSV", "/NH"], text=True)
    pids = []
    for line in out.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) >= 2 and parts[0].lower() == "aowx.exe":
            pids.append(int(parts[1]))
    return pids


def modules(h):
    mods = (wt.HMODULE * 1024)()
    needed = wt.DWORD()
    psapi.EnumProcessModulesEx(h, mods, ctypes.sizeof(mods), ctypes.byref(needed), 0x01)
    out = {}
    nb = ctypes.create_string_buffer(260)
    for i in range(needed.value // ctypes.sizeof(wt.HMODULE)):
        psapi.GetModuleBaseNameA(h, mods[i], nb, 260)
        out[nb.value.lower().decode()] = mods[i]
    return out


for pid in find_procs():
    h = k32.OpenProcess(0x410, False, pid)
    mods = modules(h)
    aow = mods.get("aowepack.dll")
    net = mods.get("network.dpl")

    def u32(addr):
        b = rd(h, addr, 4)
        return int.from_bytes(b, "little") if b else 0

    def u8(addr):
        b = rd(h, addr, 1)
        return b[0] if b else -1

    vmts = {}
    for rva, name in CLASSREFS.items():
        v = u32(aow + rva)
        if v:
            vmts[v] = name

    def vmt_name(v):
        if v in vmts:
            return vmts[v]
        for mname, mbase in (("AoWEPACK", aow), ("Network", net)):
            if mbase and 0 <= v - mbase < 0x300000:
                return "%s+0x%X" % (mname, v - mbase)
        return "0x%08X" % v

    print("\n===== pid %d  (AoWEPACK 0x%X, Network 0x%X) =====" % (pid, aow, net or 0))
    mapp = u32(aow + 0x1FA040)
    tokman = u32(mapp + 0x23C) if mapp else 0
    execu = u32(tokman + 4) if tokman else 0
    print("map=0x%X tokman=0x%X exec=0x%X" % (mapp, tokman, execu))
    if execu:
        print("  exec: executed-count=%d lock=%d [+0x54]=%d [+0x50]=0x%X" %
              (u32(execu + 0x18), u32(execu + 0x4C), u32(execu + 0x54), u32(execu + 0x50)))
        # executer PENDING list [exec+0x10] is a TTokenEventList (same shape as
        # a TC's [tc+4]).  Contents = tokens received/queued but NOT yet
        # executed.  If the divergent move sits here on the peer -> state will
        # converge (it just executes late); if absent -> it was dropped/
        # collided (real divergence).  Each event's counter = [te+0xC].
        pl = u32(execu + 0x10)
        pin = u32(pl + 8) if pl else 0
        pin2 = u32(pin + 8) if pin else 0
        pcnt = u32(pin2 + 8) if pin2 else 0
        pdata = u32(pin2 + 4) if pin2 else 0
        print("  exec PENDING list [+0x10] @0x%X: %d event(s)" % (pl, pcnt))
        for j in range(min(pcnt, 16)):
            te = u32(pdata + j * 4)
            if not te:
                continue
            name = vmt_name(u32(te))
            ctr = u32(te + 0xC)
            extra = ""
            if "Move" in name and "TE" in name:
                path = u32(te + 0x14)
                pd = u32(path + 4) if path else 0
                first = u32(pd) if pd else 0
                extra = " first-hex=(%d,%d,%d)" % (first & 0xFF, (first >> 8) & 0xFF,
                                                   (first >> 16) & 0xFF)
            print("     [%d] te=0x%X counter=%d %s%s" % (j, te, ctr, name, extra))
    # comm statuses
    holder = u32(mapp + 0x240) if mapp else 0
    pcc = u32(holder + 0x1C) if holder else 0
    lst = u32(pcc + 0xC) if pcc else 0
    inner = u32(lst + 8) if lst else 0
    data = u32(inner + 4) if inner else 0
    sts = {}
    for idx in range(8):
        recp = u32(data + idx * 4) if data else 0
        if recp:
            sts[idx] = u8(recp + 8)
    print("  comm: %s" % sts)

    tclist = u32(tokman + 0x10) if tokman else 0
    n = u32(tclist + 8) if tclist else 0
    tdata = u32(tclist + 4) if tclist else 0
    print("  %d token controls:" % n)
    for i in range(min(n, 16)):
        tc = u32(tdata + i * 4)
        if not tc:
            continue
        pidx = u32(tc + 0xC)
        tel = u32(tc + 4)
        tin = u32(tel + 8) if tel else 0
        tin2 = u32(tin + 8) if tin else 0
        cnt = u32(tin2 + 8) if tin2 else 0
        edata = u32(tin2 + 4) if tin2 else 0
        st = sts.get(pidx, "?")
        print("   TC[%d] @0x%X player=%s comm=%s pending=%d" % (i, tc, pidx, st, cnt))
        for j in range(min(cnt, 12)):
            te = u32(edata + j * 4)
            if not te:
                continue
            vmt = u32(te)
            name = vmt_name(vmt)
            ctr = u32(te + 0xC)
            extra = ""
            if "Move" in name and "TE" in name:
                path = u32(te + 0x14)
                pd = u32(path + 4) if path else 0
                first = u32(pd) if pd else 0
                extra = " first-hex=(%d,%d,%d)" % (first & 0xFF, (first >> 8) & 0xFF,
                                                   (first >> 16) & 0xFF)
            print("     [%d] te=0x%X counter=%d %s%s" % (j, te, ctr, name, extra))
    k32.CloseHandle(h)
