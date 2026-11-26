r"""
autoclaim_probe.py - READ-ONLY live dump of the MP lobby state behind patch_mp_reload_autoclaim (2026-10-22).

  py -3.10 autoclaim_probe.py            one snapshot of every running AoWx.exe (two instances on one PC = both)
  py -3.10 autoclaim_probe.py --watch    every 2 s until Ctrl+C

Run it on the HOST while the MP lobby is open (after picking the save, and again after the client joins).  The game
usually runs elevated -> run from an elevated prompt if OpenProcess fails (error 5).  Nothing is written.

Prints, per AoWx.exe:
  * the autoclaim name table, AoWEPACK DATA slack 0x558E9F10 (13 x {AnsiString name, slot index}) plus, when the v2
    patch is applied, its diag block 0x558E9F78 (v2: counts + save marker; v3: counts + hits per name source)
  * v4: when a game map is loaded, every TPlayer's stored lobby name [p+0xDC] (written at game start / read from saves)
  * the lobby TSetupControl (found by scanning memory for an object whose [+0x28] is a TSetupSettings and [+0x34] a
    TRemotePlayer): phase [+0x25], flags [+0x24] (4 = networked), own player [+0x34] (name, id, preferred race)
  * TSetupSettings: [+0x20] save marker (= the picked file's turn; 0 = virgin map), [+0x14] file, [+0xC] host id
  * remote players ([settings+0x38]): name [+8], id [+0xC], preferred race [+0x10] (a RACE id matched against record +0x18 by IndexOfRace, 0xFF = none)
  * slot records ([settings+8]): player index [+0x20] (IndexOfPlayer key), race [+0x18] (IndexOfRace key), owner type [+8] (0 human, 7 Emperor ...), owner id
    [+0xC] (0 = unclaimed), flags [+0x19] (1 map-assigned, 2 forced), leader name [[+0x1C]+0x60]
"""
import ctypes, ctypes.wintypes as W, struct, sys, time

from presence_probe import k32, PE32, module_base, Proc

PREF = 0x55700000
TAB, N, DIAG = 0x558E9F10, 13, 0x558E9F78
VMT_SETTINGS, VMT_REMOTE, VMT_REC = 0x557DEC54, 0x557DE92C, 0x557DEB70
RACES = ["Humans", "Azracs", "Lizardmen", "Frostlings", "Elves", "Halflings",
         "Dwarves", "High Men", "Dark Elves", "Orcs", "Goblins", "Undead"]
OWNER = {0: "Human", 1: "CPU Warrior", 2: "CPU Knight", 3: "CPU Lord", 4: "Independent", 5: "Free",
         6: "CPU King", 7: "CPU Emperor"}


class MBI(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_void_p), ("AllocationBase", ctypes.c_void_p), ("AllocationProtect", W.DWORD),
                ("RegionSize", ctypes.c_size_t), ("State", W.DWORD), ("Protect", W.DWORD), ("Type", W.DWORD)]


k32.VirtualQueryEx.argtypes = [W.HANDLE, ctypes.c_void_p, ctypes.POINTER(MBI), ctypes.c_size_t]
k32.VirtualQueryEx.restype = ctypes.c_size_t


def all_pids(name=b"aowx.exe"):
    snap = k32.CreateToolhelp32Snapshot(2, 0)
    e = PE32(); e.dwSize = ctypes.sizeof(PE32); ok = k32.Process32First(snap, ctypes.byref(e)); out = []
    while ok:
        if e.szExeFile.lower() == name:
            out.append(e.th32ProcessID)
        ok = k32.Process32Next(snap, ctypes.byref(e))
    k32.CloseHandle(snap)
    return out


class P(Proc):
    def u32(self, a):
        b = self.rd(a, 4)
        return struct.unpack("<I", b)[0] if len(b) == 4 else None

    def u8(self, a):
        b = self.rd(a, 1)
        return b[0] if b else None

    def astr(self, p):
        if not p:
            return ""
        n = self.u32(p - 4)
        if n is None or n <= 0 or n > 512:
            return "<bad>"
        return self.rd(p, n).decode("cp1252", "replace")

    def tlist(self, lst):
        if not lst:
            return []
        items, cnt = self.u32(lst + 4), self.u32(lst + 8)
        if not items or cnt is None or cnt > 64:
            return []
        b = self.rd(items, cnt * 4)
        return list(struct.unpack("<%dI" % (len(b) // 4), b))

    def regions(self):
        a, m = 0x10000, MBI()
        while a < 0x7FFF0000 and k32.VirtualQueryEx(self.h, ctypes.c_void_p(a), ctypes.byref(m), ctypes.sizeof(m)):
            size = m.RegionSize or 0x1000
            if m.State == 0x1000 and m.Protect in (0x04, 0x40) and m.Type == 0x20000:   # committed RW private
                yield a, size
            a += size


def find_controls(p, delta):
    """lobby TSetupControl candidates: [o+0x28] -> TSetupSettings, [o+0x34] -> TRemotePlayer"""
    vs, vr = VMT_SETTINGS + delta, VMT_REMOTE + delta
    blobs = []
    for a, size in p.regions():
        b = p.rd(a, size)
        if b:
            blobs.append((a, b))

    def hits(needle):
        pat = struct.pack("<I", needle)
        for a, b in blobs:
            i = b.find(pat)
            while i != -1:
                if i % 4 == 0:
                    yield a + i
                i = b.find(pat, i + 1)

    found = []
    for s in list(hits(vs)):                       # every TSetupSettings object ...
        for f in hits(s):                          # ... and every field pointing at it
            o = f - 0x28
            r = p.u32(o + 0x34)
            if r and p.u32(r) == vr:
                found.append(o)
    return sorted(set(found))


def dump(pid):
    print("=" * 78)
    print("AoWx.exe pid %d" % pid)
    base = module_base(pid)
    if not base:
        print("  AoWEPACK.dll not found (still starting, or access denied - try an elevated prompt)"); return
    try:
        p = P(pid)
    except OSError as e:
        print("  " + str(e)); return
    d = base - PREF
    print("  AoWEPACK base %#x (delta %+#x)" % (base, d))
    magic = p.rd(0x55836400 + d, 4)
    print("  name table @%#x (%s):" % (TAB + d, "key = saved RACE id (v5)" if magic == b"MRA5" else "key = saved player index (v1-v4)"))
    any_name = False
    for k in range(N):
        np_, ix = p.u32(TAB + d + k * 8), p.u8(TAB + d + k * 8 + 4)
        if np_:
            any_name = True
            lab = RACES[ix] if magic == b"MRA5" and ix is not None and ix < 12 else "slot %s" % ix
            print("    [%2d] %-12s name %r" % (k, lab, p.astr(np_)))
    if not any_name:
        print("    (empty)")
    dg = p.rd(DIAG + d, 8)
    print("  autoclaim zone magic %r" % magic)
    if len(dg) == 8 and any(dg):
        if magic in (b"MRA4", b"MRA5"):
            print("  v4 diag: players %d, saved humans %d, table entries %d, pick runs %d | hits: TPlayer+0xDC name %d, "
                  "[p+0xD4] %d, [p+0x58] template %d, [p+0x4C] %d" % tuple(dg))
        elif magic == b"MRA3":
            print("  v3 diag: players %d, saved humans %d, table entries %d, pick runs %d | hits: army TLeader %d, "
                  "hero-control TLeader %d, [p+0xD4] %d, template/[p+0x4C] %d" % tuple(dg))
        else:
            print("  v2 diag: players %d, humans %d, table entries %d, pick runs %d, save marker %d"
                  % (dg[0], dg[1], dg[2], dg[3], struct.unpack("<I", dg[4:])[0]))
    gmap = p.u32(0x558FA040 + d)                     # AoWE.AoWHSMap global (the game map once a game runs)
    if gmap:
        pl = p.u32(gmap + 0x140)
        players = p.tlist(p.u32(pl + 8)) if pl else []
        print("  game map @%#x turn %s: TPlayer+0xDC stored lobby names (autoclaim v4):" % (gmap, p.u32(gmap + 0x174)))
        for i, pp in enumerate(players):
            if i and pp:
                print("    player %d race %s type %s -> %r" % (i, p.u8(pp + 0xA5), p.u8(pp + 0xA7), p.astr(p.u32(pp + 0xDC))))
    ctls = find_controls(p, d)
    if not ctls:
        print("  no lobby TSetupControl in memory (not in an MP/SP setup screen?)"); return
    for c in ctls:
        st, me = p.u32(c + 0x28), p.u32(c + 0x34)
        flags, phase = p.u8(c + 0x24), p.u8(c + 0x25)
        print("  TSetupControl @%#x  phase %s  flags %#x (%s)  host id %s"
              % (c, phase, flags or 0, "networked" if (flags or 0) & 4 else "local", p.u32(st + 0xC)))
        print("    own player: %r id %s pref %s" % (p.astr(p.u32(me + 8)), p.u32(me + 0xC), p.u8(me + 0x10)))
        print("    settings @%#x  save marker [+0x20] = %s  file %r  conn %s"
              % (st, p.u32(st + 0x20), p.astr(p.u32(st + 0x14)), p.u8(st + 0x3C)))
        rl = p.u32(st + 0x38)
        rps = p.tlist(p.u32(rl + 8)) if rl else []
        print("    remote players (%d):" % len(rps))
        for rp in rps:
            print("      %-20r id %-11s pref %-4s status %s" % (p.astr(p.u32(rp + 8)), p.u32(rp + 0xC), p.u8(rp + 0x10), p.u8(rp + 0x11)))
        recs = p.tlist(p.u32(st + 8))
        print("    slot records (%d):" % len(recs))
        for r in recs:
            race, typ, fl = p.u8(r + 0x18), p.u8(r + 8), p.u8(r + 0x19)
            ldr = p.u32(r + 0x1C)
            print("      index %-3s race %-10s owner %-12s id %-11s flags %#04x  leader %r"
                  % (p.u8(r + 0x20), RACES[race] if race is not None and race < 12 else race,
                     OWNER.get(typ, typ), p.u32(r + 0xC), fl or 0, p.astr(p.u32(ldr + 0x60)) if ldr else None))


def main():
    while True:
        pids = all_pids()
        if not pids:
            print("AoWx not running")
        for pid in pids:
            dump(pid)
        if "--watch" not in sys.argv:
            return 0
        time.sleep(2)


if __name__ == "__main__":
    sys.exit(main())
