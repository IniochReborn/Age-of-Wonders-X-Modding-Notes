r"""Read-only snapshot of the lobby controller (AoWSetup.TSetupControl) of every running AoWx.exe (2026-11-16).

Purpose: stage A of the out-of-sync "instant reload" - find out what state the lobby machinery is in while a
network game is RUNNING (is it still active, which phase, does it still know the seats / remote ids / map file).
Nothing is written to the game.  Output: <game>\X\Setup Probe.txt
Usage: py -3.10 setup_probe.py        (elevated prompt if the game runs elevated)
"""
import ctypes, ctypes.wintypes as wt, os, struct, subprocess, sys, time

IMAGE = "AoWx.exe"
HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.environ.get("AOW_GAME_DIR") or os.path.dirname(HERE)
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
psapi = ctypes.windll.psapi
k32.OpenProcess.restype = wt.HANDLE
k32.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
psapi.EnumProcessModulesEx.argtypes = [wt.HANDLE, ctypes.POINTER(ctypes.c_void_p), wt.DWORD, ctypes.POINTER(wt.DWORD), wt.DWORD]
psapi.GetModuleBaseNameW.argtypes = [wt.HANDLE, ctypes.c_void_p, wt.LPWSTR, wt.DWORD]


class MODINFO(ctypes.Structure):
    _fields_ = [("lpBaseOfDll", ctypes.c_void_p), ("SizeOfImage", wt.DWORD), ("EntryPoint", ctypes.c_void_p)]


psapi.GetModuleInformation.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.POINTER(MODINFO), wt.DWORD]
G_SETUPFORM, G_MAP, G_DPLAYFORM = 0x45A30C, 0x45DF7C, 0x45A454      # exe globals (pointers to the form variables)


def pids():
    o = subprocess.run(["tasklist", "/FI", "IMAGENAME eq " + IMAGE, "/FO", "CSV", "/NH"], capture_output=True, text=True).stdout
    return [int(l.split('","')[1]) for l in o.splitlines() if l.lower().startswith('"' + IMAGE.lower() + '"')]


def probe(pid, out):
    h = k32.OpenProcess(0x0410, False, pid)
    if not h:
        out("pid %d: OpenProcess failed (%d) - run elevated" % (pid, ctypes.get_last_error())); return
    mods = (ctypes.c_void_p * 1024)(); need = wt.DWORD(); ml = []
    psapi.EnumProcessModulesEx(h, mods, ctypes.sizeof(mods), ctypes.byref(need), 1)
    for m in mods[:need.value // ctypes.sizeof(ctypes.c_void_p)]:
        nm = ctypes.create_unicode_buffer(260); psapi.GetModuleBaseNameW(h, m, nm, 260)
        mi = MODINFO(); psapi.GetModuleInformation(h, m, ctypes.byref(mi), ctypes.sizeof(mi))
        ml.append((m, mi.SizeOfImage, nm.value))

    def sym(a):
        for b, s, n in ml:
            if b <= a < b + s: return "%s+0x%X" % (n, a - b)
        return ""

    def rd(a, n):
        buf = ctypes.create_string_buffer(n); got = ctypes.c_size_t()
        return buf.raw if a and k32.ReadProcessMemory(h, ctypes.c_void_p(a), buf, n, ctypes.byref(got)) else None

    def u32(a):
        b = rd(a, 4)
        return struct.unpack("<I", b)[0] if b else 0

    def lstr(p):
        if not p: return ""
        n = u32(p - 4)
        return (rd(p, n) or b"").decode("latin1") if 0 < n < 400 else ""

    def dump(label, a, n):
        b = rd(a, n)
        if not b: out("  %s @%08X: unreadable" % (label, a)); return b""
        out("  %s @%08X (class %s)" % (label, a, sym(struct.unpack_from("<I", b, 0)[0])))
        for o in range(0, n, 16):
            out("    +%02X  %s" % (o, " ".join("%08X" % x for x in struct.unpack_from("<%dI" % (len(b[o:o + 16]) // 4), b, o))))
        return b

    out("===== pid %d  %s" % (pid, time.strftime("%Y-%m-%d %H:%M:%S")))
    mapvar = u32(G_MAP); mp = u32(mapvar) if mapvar else 0
    out("  map object %08X%s" % (mp, "" if mp else "  (no game running)"))
    if mp:
        b = rd(mp + 0xA4, 2) or b"\xff\xff"
        out("  active player %d, local player %d, play mode %d, map file [map+0x7C] '%s'" % (
            struct.unpack("b", b[:1])[0], struct.unpack("b", b[1:])[0], (rd(mp + 0x239, 1) or b"\0")[0], lstr(u32(mp + 0x7C))))
    form = u32(u32(G_SETUPFORM)); ctrl = u32(form + 0x33C) if form else 0
    dform = u32(u32(G_DPLAYFORM)); ctrl2 = u32(dform + 0x48) if dform else 0
    out("  setup form %08X (class %s): [+0x33C] TSetupControl %08X | DPlay form %08X (class %s): [+0x48] %08X" % (
        form, sym(u32(form)), ctrl, dform, sym(u32(dform)), ctrl2))
    ctrl = ctrl or ctrl2
    if not ctrl: return
    cb = dump("TSetupControl (+0x24 flags, +0x25 phase, +0x28 settings, +0x2C stream, +0x34 local remote-player)", ctrl, 0xA0)
    st = struct.unpack_from("<I", cb, 0x28)[0] if len(cb) >= 0x2C else 0
    sb = dump("TSetupSettings [ctrl+0x28] (+0xC host remote id, +0x38 remote player list)", st, 0x60)
    for o in range(0x10, 0x34, 4):
        if len(sb) >= o + 4:
            s = lstr(struct.unpack_from("<I", sb, o)[0])
            if s: out("    settings +%02X string: '%s'" % (o, s))
    lp = struct.unpack_from("<I", cb, 0x34)[0] if len(cb) >= 0x38 else 0
    lb = dump("local TRemotePlayer [ctrl+0x34] (+8 name, +0xC remote id, +0x10 preferred race, +0x11 status)", lp, 0x20)
    if len(lb) >= 0xC: out("    name '%s'" % lstr(struct.unpack_from("<I", lb, 8)[0]))
    rl = struct.unpack_from("<I", sb, 0x38)[0] if len(sb) >= 0x3C else 0
    rb = rd(rl, 0x10)
    if rb:
        inner = struct.unpack_from("<I", rb, 8)[0]
        ib = rd(inner, 12) if inner else None
        if ib:
            items, cnt = struct.unpack_from("<II", ib, 4)
            out("  remote players: %d" % cnt)
            for i in range(min(cnt, 12)):
                p = u32(items + 4 * i); pb = rd(p, 0x20) or bytes(0x20)
                out("    [%d] @%08X name '%s' remote id %08X pref %d status %d version %08X" % (
                    i, p, lstr(struct.unpack_from("<I", pb, 8)[0]), struct.unpack_from("<I", pb, 0xC)[0], pb[0x10], pb[0x11],
                    struct.unpack_from("<I", pb, 0x14)[0]))
    # per-seat settings list: try the pointers in the settings object
    for o in range(0x34, 0x60, 4):
        if len(sb) >= o + 4:
            p = struct.unpack_from("<I", sb, o)[0]
            if p and rd(p, 4): dump("settings+0x%X ->" % o, p, 0x20)
    gd = u32(u32(u32(G_DPLAYFORM)) + 0x44) if u32(G_DPLAYFORM) else 0
    gb = rd(gd + 0x1E8, 0x10) if gd else None
    if gb: out("  TGDPlay @%08X: connected %d, in session %d, is DirectPlay host %d, closing %d, disconnecting %d" % (
        gd, gb[5], gb[6], gb[7], gb[8], gb[9]))
    k32.CloseHandle(h)


def main():
    ps = pids()
    if not ps:
        print("No AoWx.exe is running."); return 1
    os.makedirs(os.path.join(GAME, "X"), exist_ok=True)
    f = open(os.path.join(GAME, "X", "Setup Probe.txt"), "a", encoding="utf-8")

    def out(s):
        f.write(s + "\n"); print(s)
    for p in ps:
        try: probe(p, out)
        except Exception as e: out("pid %d: probe error %r" % (p, e))
    out("")
    return 0


if __name__ == "__main__":
    sys.exit(main())
