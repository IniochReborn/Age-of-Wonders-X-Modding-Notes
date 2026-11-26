r"""
presence_probe.py - READ-ONLY live check of the game-state fields a Discord Rich Presence helper would read.

  py -3.10 presence_probe.py            one snapshot
  py -3.10 presence_probe.py --watch    every 2 s until Ctrl+C

Finds AoWx.exe by name, gets AoWEPACK.dll's live base (it CAN be rebased - seen at 0x00DF0000), then follows
(all offsets from static RE 10/21, see memory presence-game-state-re):
  map      = [AoWEPACK + 0x1FA040]          AoWE.AoWHSMap export; nil when no map (TAoWEngine.CloseHSM clears it)
  turn     = int32  [map+0x174]             0 at TAoWHSMap.Create, ++ in TPlayerControl.NewDay, stream tag 0x13
  conn     = byte   [map+0x13A]             TPlayerConnectionType 0 pcLocal / 1 pcNetwork / 2 pcEmail
  playmode = byte   [map+0x239]             TPlayMode 0 none / 1 turn / 2 simultaneous
  hotseat  = byte   [map+0x139]             set by TTurnPlayerControl.DefaultStartMap
  name     = AnsiString [map+0xE4]          stream tag 0x19 = the .hsm map title ("After the Fall")
  seated   = int8   [map+0xA5]              local/seated player index (SetSeatedPlayer)
  plist    = [map+0x140] TPlayerList: [+8] TList of TPlayer (items [+4], count [+8]);
             [+0x1C] list of local HUMAN player indices (count [+8]) -> >1 = hotseat
  player   = items[seated];  race = byte [player+0xA5] (TPlayer.SetRace); type [player+0xA7] 0 = human
The game usually runs elevated -> run this from an elevated prompt if OpenProcess fails (error 5).
"""
import ctypes, ctypes.wintypes as W, sys, time

RACES = ["Humans", "Azracs", "Lizardmen", "Frostlings", "Elves", "Halflings",
         "Dwarves", "High Men", "Dark Elves", "Orcs", "Goblins", "Undead"]
CONN = {0: "local", 1: "network", 2: "email"}
MAP_RVA = 0x1FA040

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
k32.OpenProcess.restype = W.HANDLE
k32.CreateToolhelp32Snapshot.restype = W.HANDLE
k32.ReadProcessMemory.argtypes = [W.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]


class PE32(ctypes.Structure):
    _fields_ = [("dwSize", W.DWORD), ("cntUsage", W.DWORD), ("th32ProcessID", W.DWORD), ("th32DefaultHeapID", ctypes.c_void_p),
                ("th32ModuleID", W.DWORD), ("cntThreads", W.DWORD), ("th32ParentProcessID", W.DWORD),
                ("pcPriClassBase", ctypes.c_long), ("dwFlags", W.DWORD), ("szExeFile", ctypes.c_char * 260)]


class ME32(ctypes.Structure):
    _fields_ = [("dwSize", W.DWORD), ("th32ModuleID", W.DWORD), ("th32ProcessID", W.DWORD), ("GlblcntUsage", W.DWORD),
                ("ProccntUsage", W.DWORD), ("modBaseAddr", ctypes.c_void_p), ("modBaseSize", W.DWORD), ("hModule", W.HMODULE),
                ("szModule", ctypes.c_char * 256), ("szExePath", ctypes.c_char * 260)]


def find_pid(name=b"aowx.exe"):
    snap = k32.CreateToolhelp32Snapshot(2, 0)
    e = PE32(); e.dwSize = ctypes.sizeof(PE32); ok = k32.Process32First(snap, ctypes.byref(e)); pid = None
    while ok:
        if e.szExeFile.lower() == name:
            pid = e.th32ProcessID; break
        ok = k32.Process32Next(snap, ctypes.byref(e))
    k32.CloseHandle(snap)
    return pid


def module_base(pid, name=b"aowepack.dll"):
    snap = k32.CreateToolhelp32Snapshot(0x8 | 0x10, pid)          # TH32CS_SNAPMODULE | SNAPMODULE32
    if snap in (None, W.HANDLE(-1).value):
        return None
    m = ME32(); m.dwSize = ctypes.sizeof(ME32); ok = k32.Module32First(snap, ctypes.byref(m)); base = None
    while ok:
        if m.szModule.lower() == name:
            base = m.modBaseAddr; break
        ok = k32.Module32Next(snap, ctypes.byref(m))
    k32.CloseHandle(snap)
    return base


class Proc:
    def __init__(self, pid):
        self.h = k32.OpenProcess(0x0410, False, pid)                # QUERY_INFORMATION | VM_READ
        if not self.h:
            raise OSError("OpenProcess failed (error %d) - run elevated if the game is elevated" % ctypes.get_last_error())

    def rd(self, a, n):
        b = ctypes.create_string_buffer(n); g = ctypes.c_size_t()
        return b.raw[:g.value] if a and k32.ReadProcessMemory(self.h, ctypes.c_void_p(a), b, n, ctypes.byref(g)) else b""

    def u32(self, a):
        d = self.rd(a, 4); return int.from_bytes(d, "little") if len(d) == 4 else 0

    def i8(self, a):
        d = self.rd(a, 1); return int.from_bytes(d, "little", signed=True) if d else None

    def u8(self, a):
        d = self.rd(a, 1); return d[0] if d else None

    def astr(self, p, cap=200):                                     # Delphi AnsiString: length dword at p-4
        if not p:
            return ""
        n = self.u32(p - 4)
        return self.rd(p, min(n, cap)).decode("cp1252", "replace") if 0 < n < 0x10000 else ""


def snapshot():
    pid = find_pid()
    if not pid:
        return "AoWx not running"
    base = module_base(pid)
    if not base:
        return "AoWx pid %d: AoWEPACK.dll not found (module list unreadable? run elevated)" % pid
    p = Proc(pid)
    mp = p.u32(base + MAP_RVA)
    out = ["pid %d  AoWEPACK base %08X  map %08X" % (pid, base, mp)]
    if not mp:
        out.append("in_game: no (no map loaded - title screen / menus)")
        return "\n".join(out)
    turn = p.u32(mp + 0x174); conn = p.u8(mp + 0x13A); pmode = p.u8(mp + 0x239); hot = p.u8(mp + 0x139)
    name = p.astr(p.u32(mp + 0xE4)); seat = p.i8(mp + 0xA5); cur = p.i8(mp + 0xA4)
    pl = p.u32(mp + 0x140); tl = p.u32(pl + 8); items = p.u32(tl + 4); cnt = p.u32(tl + 8)
    lh = p.u32(pl + 0x1C); local_humans = p.u32(lh + 8) if lh else 0
    humans = sum(1 for i in range(min(cnt, 32)) if p.u8(p.u32(items + 4 * i) + 0xA7) == 0)
    mp_mode = conn in (1, 2) or local_humans > 1
    out.append("in_game: %s   (turn>=1 and players>0)" % ("yes" if turn >= 1 and cnt > 0 else "map loaded, not started"))
    out.append("mode: %s   conn=%s playmode=%s hotseat=%s local_humans=%d humans=%d"
               % ("Multiplayer" if mp_mode else "Single-Player", CONN.get(conn, conn), pmode, hot, local_humans, humans))
    out.append("map name: %r" % name)
    out.append("turn: %d" % turn)
    out.append("seated player %s (current %s), %d players" % (seat, cur, cnt))
    if seat is not None and 0 <= seat < cnt:
        pp = p.u32(items + 4 * seat); r = p.u8(pp + 0xA5)
        out.append("local player %08X id=%s type=%s race=%s (%s)" % (pp, p.u8(pp + 0xA6), p.u8(pp + 0xA7), r,
                   RACES[r] if r is not None and r < 12 else "?"))
    for i in range(min(cnt, 16)):
        pp = p.u32(items + 4 * i)
        out.append("   [%d] id=%s type=%s race=%s status=%s" % (i, p.u8(pp + 0xA6), p.u8(pp + 0xA7), p.u8(pp + 0xA5), p.u8(pp + 0x45)))
    return "\n".join(out)


if __name__ == "__main__":
    if "--watch" in sys.argv:
        try:
            while True:
                print(snapshot(), "\n" + "-" * 60); time.sleep(2)
        except KeyboardInterrupt:
            pass
    else:
        print(snapshot())
