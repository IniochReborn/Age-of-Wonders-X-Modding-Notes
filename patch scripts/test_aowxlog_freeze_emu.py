#!/usr/bin/env python3
r"""Unicorn test of the AoWxLog.dll freeze report (build_aowxlog.py, 2026-11-21).  Runs DllMain and the 100 ms timer
proc against a fake game (map, token manager / executer / controls / events with Delphi class names, players) with
every Win32 call stubbed in Python.  Checks: automatic report after 60 s busy without progress (network games only,
once per episode), follow-up line when the game moves on, Ctrl+F report + its in-game confirmation (status text via
map VMT+0x110 with the game's own sound silenced, then the chat sound), no map, junk pointers, stack balance;
Ctrl+R manual restore: host prompt (TMessageEventLog via map VMT+0x12C), Yes -> report + X_MAN + V_OOS 6, No /
client / handler busy or absent / non-network game -> no restore.

    py -3.10 test_aowxlog_freeze_emu.py [--show]
"""
import os, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE, UcError
from unicorn.x86_const import *
import build_aowxlog as L

img, info = L.build()
B = L.BASE
STUB, HEAP, STACK, EPACK, EXE = 0x90000000, 0x02000000, 0x00300000, 0x55700000, 0x400000
SHOWDLG, ADDSTR, RELEASE, CREATE = 0x90000820, 0x90000830, 0x90000840, 0x55700000 + L.MSGLOG_CREATE_RVA
SHOWMSG, PLAY, SLOT = 0x90000800, 0x90000810, 0x55700000 + 0x1FC4C8
PID = 4242
FZ = L.FZ_SECS


def load_image(mu):
    pe = struct.unpack_from("<I", img, 0x3C)[0]
    n = struct.unpack_from("<H", img, pe + 6)[0]; opt = struct.unpack_from("<H", img, pe + 20)[0]
    soi = struct.unpack_from("<I", img, pe + 24 + 56)[0]
    mu.mem_map(B, (soi + 0xFFF) & ~0xFFF)
    for i in range(n):
        o = pe + 24 + opt + 40 * i
        vs, va, rs, rp = struct.unpack_from("<IIII", img, o + 8)
        mu.mem_write(B + va, img[rp:rp + rs])
    return soi


class Emu(object):
    def __init__(self):
        mu = self.mu = Uc(UC_ARCH_X86, UC_MODE_32)
        self.soi = load_image(mu)
        mu.mem_map(STUB, 0x1000); mu.mem_map(HEAP, 0x100000); mu.mem_map(STACK, 0x100000)
        mu.mem_map(EPACK, 0x200000); mu.mem_map(EXE, 0x240000)
        self.regions = [(B, self.soi), (HEAP, 0x100000), (STACK, 0x100000), (EPACK, 0x200000), (EXE, 0x240000)]
        self.heap = HEAP + 0x1000
        self.out = bytearray(); self.tick = 1000; self.keys = set(); self.fg_pid = PID; self.timer = None; self.calls = []
        names = sorted(info["iat"], key=lambda k: info["iat"][k])
        self.stub = {}
        for i, nme in enumerate(names):
            a = STUB + 0x10 * (i + 1)
            mu.mem_write(a, b"\xC3"); self.stub[a] = nme
            mu.mem_write(info["iat"][nme], struct.pack("<I", a))
        mu.mem_write(STUB, b"\xF4")                          # return address sentinel
        mu.mem_write(SHOWMSG, b"\xC3"); mu.mem_write(PLAY, b"\xC3")
        for a_ in (SHOWDLG, ADDSTR, RELEASE): mu.mem_write(a_, b"\xC3")
        mu.mem_write(CREATE, bytes.fromhex("558bec6a") + b"\xC3")
        mu.hook_add(UC_HOOK_CODE, self.on_create, begin=CREATE, end=CREATE)
        self.dialogs, self.added, self.released = [], [], 0
        mu.mem_map(0, 0x1000); self.w32(0, 0xFFFFFFFF)     # fs base is 0 in this emulator: fs:[0] = SEH chain head
        self.shown, self.played, self.slot_seen = [], [], []
        mu.hook_add(UC_HOOK_CODE, self.on_code, begin=STUB, end=STUB + 0xFFF)

    # ---- memory helpers
    def u32(self, a): return struct.unpack("<I", self.mu.mem_read(a, 4))[0]
    def w32(self, a, v): self.mu.mem_write(a, struct.pack("<I", v & 0xFFFFFFFF))
    def cstr(self, a):
        o = bytearray()
        while True:
            c = self.mu.mem_read(a, 1)[0]
            if not c: return o.decode("latin-1")
            o.append(c); a += 1
    def alloc(self, n, fill=0):
        a = self.heap; self.heap += (n + 15) & ~15
        self.mu.mem_write(a, bytes([fill]) * n); return a
    def readable(self, a, n):
        return any(b <= a and a + n <= b + s for b, s in self.regions)
    def klass(self, name, slots=()):
        """a fake Delphi VMT whose [VMT-0x20] points at the class-name ShortString"""
        blk = self.alloc(0x200); nm = self.alloc(len(name) + 2)
        self.mu.mem_write(nm, bytes([len(name)]) + name.encode())
        self.w32(blk + 0x40 - 0x20, nm)
        for off, val in slots: self.w32(blk + 0x40 + off, val)
        return blk + 0x40
    def obj(self, cls, size, fields=()):
        a = self.alloc(size); self.w32(a, self.klass(cls))
        for off, val in fields: self.w32(a + off, val)
        return a
    def tlist(self, items):
        arr = self.alloc(4 * max(1, len(items)))
        for i, it in enumerate(items): self.w32(arr + 4 * i, it)
        return self.obj("TList", 0x10, [(4, arr), (8, len(items))])
    def evlist(self, events):
        inner = self.obj("TObjectList", 0x10, [(8, self.tlist(events))])
        return self.obj("TTokenEventList", 0x10, [(8, inner)])

    def on_create(self, mu, addr, size, ud):
        """TMessageEventLog.Create(eax class, dl 1, ecx 0) -> eax = new log (title, TStrings at +0x20)"""
        assert mu.reg_read(UC_X86_REG_EAX) == self.u32(EPACK + L.MSGLOG_CLS_RVA) and mu.reg_read(UC_X86_REG_EDX) & 0xFF == 1
        assert mu.reg_read(UC_X86_REG_ECX) == 0
        strings = self.alloc(0x10); self.w32(strings, self.klass("TStringList", [(0x34, ADDSTR)]))
        log = self.alloc(0x40); self.w32(log, self.klass("TMessageEventLog", [(0x2C, RELEASE)])); self.w32(log + 0x20, strings)
        esp = mu.reg_read(UC_X86_REG_ESP)
        mu.reg_write(UC_X86_REG_EIP, self.u32(esp)); mu.reg_write(UC_X86_REG_ESP, esp + 4)
        mu.reg_write(UC_X86_REG_EAX, log); mu.reg_write(UC_X86_REG_ECX, 0xCCCCCCCC); mu.reg_write(UC_X86_REG_EDX, 0xDDDDDDDD)

    # ---- Win32 stubs
    def on_code(self, mu, addr, size, ud):
        if addr == STUB: mu.emu_stop(); return
        if addr == SHOWMSG:                                  # TAbstractAoWHSMap.ShowMessage(eax map, edx AnsiString)
            p = mu.reg_read(UC_X86_REG_EDX)
            assert self.u32(p - 8) == 0xFFFFFFFF and self.u32(p - 4) == len(self.cstr(p)), 'not a constant AnsiString'
            self.shown.append(self.cstr(p)); self.slot_seen.append(self.u32(SLOT))
            mu.reg_write(UC_X86_REG_ECX, 0xCCCCCCCC); mu.reg_write(UC_X86_REG_EDX, 0xDDDDDDDD); return
        if addr == ADDSTR:                                   # TStrings.Add(eax strings, edx AnsiString)
            self.added.append(self.cstr(mu.reg_read(UC_X86_REG_EDX))); return
        if addr == RELEASE: self.released += 1; return
        if addr == SHOWDLG:                                  # map VMT+0x12C(eax map, edx log, cl, push cbObj, push cbFn) - callee pops 8
            esp = mu.reg_read(UC_X86_REG_ESP); log = mu.reg_read(UC_X86_REG_EDX)
            assert mu.reg_read(UC_X86_REG_ECX) & 0xFF == 0
            self.dialogs.append(dict(log=log, fn=self.u32(esp + 4), obj=self.u32(esp + 8), style=mu.mem_read(log + 0x25, 1)[0],
                                     title=self.cstr(self.u32(log + 0x18))))
            mu.reg_write(UC_X86_REG_EIP, self.u32(esp)); mu.reg_write(UC_X86_REG_ESP, esp + 12)
            mu.reg_write(UC_X86_REG_ECX, 0xCCCCCCCC); mu.reg_write(UC_X86_REG_EDX, 0xDDDDDDDD); return
        if addr == PLAY:                                     # Sound.PlaySample(eax AnsiString)
            p = mu.reg_read(UC_X86_REG_EAX)
            assert self.u32(p - 8) == 0xFFFFFFFF and self.u32(p - 4) == len(self.cstr(p)), 'not a constant AnsiString'
            self.played.append(self.cstr(p))
            mu.reg_write(UC_X86_REG_ECX, 0xCCCCCCCC); mu.reg_write(UC_X86_REG_EDX, 0xDDDDDDDD); return
        name = self.stub.get(addr)
        if name is None: return
        esp = mu.reg_read(UC_X86_REG_ESP)
        arg = lambda i: self.u32(esp + 4 + 4 * i)
        ret, nargs = 0, 0
        self.calls.append(name)
        if name == "wsprintfA":
            fmt = self.cstr(arg(1)); o, i, k = "", 0, 2
            while i < len(fmt):
                c = fmt[i]
                if c != "%": o += c; i += 1; continue
                j = i + 1
                while fmt[j] in "0123456789.": j += 1
                spec, conv = fmt[i + 1:j], fmt[j]
                if conv == "%": o += "%"; i = j + 1; continue
                val = arg(k); k += 1
                if conv == "s":
                    t = self.cstr(val)
                    if "." in spec: t = t[:int(spec.split(".")[1] or 0)]
                    o += t
                elif conv == "d": o += ("%" + spec + "d") % (val - (1 << 32) if val & 0x80000000 else val)
                elif conv == "u": o += ("%" + spec + "u") % val
                elif conv == "X": o += ("%" + spec + "X") % val
                else: raise AssertionError("format %r" % fmt)
                i = j + 1
            assert len(o) < 1024, "wsprintfA overflow: %r" % o
            mu.mem_write(arg(0), o.encode("latin-1") + b"\0"); ret = len(o)
            mu.reg_write(UC_X86_REG_EAX, ret); mu.reg_write(UC_X86_REG_ECX, 0xCCCCCCCC); mu.reg_write(UC_X86_REG_EDX, 0xDDDDDDDD)
            return                                               # cdecl: plain ret
        if name in ("IsBadReadPtr", "IsBadWritePtr"): ret, nargs = (0 if self.readable(arg(0), arg(1)) else 1), 2
        elif name == "GetModuleHandleA": ret, nargs = (EPACK if self.cstr(arg(0)).lower() == "aowepack.dll" else 0), 1
        elif name == "GetModuleFileNameA":
            mu.mem_write(arg(1), b"C:\\Game\\AoWx.exe\0"); ret, nargs = 16, 3
        elif name == "CreateFileA": ret, nargs = 0x77, 7
        elif name == "WriteFile":
            self.out += mu.mem_read(arg(1), arg(2)); self.w32(arg(3), arg(2)); ret, nargs = 1, 5
        elif name == "lstrlenA": ret, nargs = len(self.cstr(arg(0))), 1
        elif name == "lstrcmpA": ret, nargs = (0 if self.cstr(arg(0)) == self.cstr(arg(1)) else 1), 2
        elif name == "GetLocalTime":
            mu.mem_write(arg(0), struct.pack("<8H", 2026, 11, 6, 21, 20, 15, 30, 0)); nargs = 1
        elif name == "GetTickCount": ret = self.tick
        elif name == "GetCurrentProcessId": ret = PID
        elif name == "GetAsyncKeyState": ret, nargs = (0x8000 if arg(0) in self.keys else 0), 1
        elif name == "GetForegroundWindow": ret = 0x1234
        elif name == "GetWindowThreadProcessId": self.w32(arg(1), self.fg_pid); ret, nargs = 1, 2
        elif name == "SetTimer": self.timer = arg(3); ret, nargs = 1, 4
        elif name == "RegOpenKeyExA": ret, nargs = 2, 5
        elif name == "VirtualQuery": ret, nargs = 0, 3
        else:
            nargs = {"CloseHandle": 1, "SetFilePointer": 4, "SetEndOfFile": 1, "GetFileSize": 2, "CreateDirectoryA": 2,
                     "MoveFileA": 2, "DeleteFileA": 1, "AddVectoredExceptionHandler": 2, "VirtualProtect": 4,
                     "RegQueryValueExA": 6, "RegCloseKey": 1}[name]
        ra = self.u32(esp)
        mu.reg_write(UC_X86_REG_ESP, esp + 4 + 4 * nargs)
        mu.reg_write(UC_X86_REG_EIP, ra)
        mu.reg_write(UC_X86_REG_EAX, ret & 0xFFFFFFFF); mu.reg_write(UC_X86_REG_ECX, 0xCCCCCCCC); mu.reg_write(UC_X86_REG_EDX, 0xDDDDDDDD)

    def call(self, fn, args, nret, eax=0, edx=0):
        mu = self.mu
        esp0 = STACK + 0x80000
        regs = {UC_X86_REG_EBX: 0x0B0B0B0B, UC_X86_REG_ESI: 0x51515151, UC_X86_REG_EDI: 0xD1D1D1D1, UC_X86_REG_EBP: 0xB9B9B9B9}
        for r, val in regs.items(): mu.reg_write(r, val)
        esp = esp0
        for x in reversed(args): esp -= 4; self.w32(esp, x)
        esp -= 4; self.w32(esp, STUB)
        mu.reg_write(UC_X86_REG_ESP, esp); mu.reg_write(UC_X86_REG_EAX, eax); mu.reg_write(UC_X86_REG_EDX, edx)
        mu.emu_start(fn, 0, count=5_000_000)
        assert mu.reg_read(UC_X86_REG_EIP) in (STUB, STUB + 1), "did not return (eip %08X)" % mu.reg_read(UC_X86_REG_EIP)
        assert mu.reg_read(UC_X86_REG_ESP) == esp0 - 4 * len(args) + 4 * nret, "stack imbalance"
        for r, val in regs.items(): assert mu.reg_read(r) == val, "callee-saved register changed"
        return mu.reg_read(UC_X86_REG_EAX)

    def tproc(self, advance_ms=1000):
        self.tick += advance_ms
        self.call(self.timer, [0, 0x113, 1, self.tick], 4)

    def take(self):
        t = self.out.decode("latin-1"); self.out = bytearray(); return t


def fake_game(e, network=1, lock=1, status=0):
    hs = e.obj("TTacticalCombatUnitHS", 0x30, [(0x14, 0xAB0003)])
    tu = e.obj("TUnit", 0x50, [(0x3C, 0x00170000)])
    cu = e.obj("TTacticalCombatUnit", 0x70, [(0x44, 0x09000A00), (0x4C, tu), (0x54, 1), (0x60, hs)])
    ev = e.obj("TArmyCombatMoveTE", 0x60, [(0xC, 77), (0x1C, cu), (0x38, 4), (0x39, 2)])
    tc0 = e.obj("TTokenControl", 0x20, [(4, e.evlist([])), (0xC, 0), (0x10, 1)])
    tc1 = e.obj("TTokenControl", 0x20, [(4, e.evlist([ev])), (0xC, 1), (0x10, 1)])
    ex = e.obj("TTokenExecuter", 0x60, [(4, tc1), (8, tc1), (0xC, 1), (0x10, e.evlist([ev])), (0x14, e.tlist([tc0, tc1])),
                                         (0x18, 4321), (0x1C, 9), (0x24, status), (0x4C, lock), (0x50, e.evlist([]))])
    tm = e.obj("TTokenManager", 0x30, [(4, ex)])
    ai = e.obj("TAIExecuter", 0x40)
    players = [e.obj("TPlayer", 0xB0) for _ in range(3)]
    e.mu.mem_write(players[0] + 0x2C, b"\x01"); e.mu.mem_write(players[1] + 0x45, b"\x01")
    plist = e.obj("TPlayerList", 0x10, [(8, e.tlist(players))])
    mp = e.obj("TMapBase", 0x250, [(0x120, 0), (0x128, ai), (0x140, plist), (0x230, 0xDEADBEEF), (0x23C, tm),
                                    (0x240, e.obj("TPlayerCommunicator", 0x30)), (0x244, e.obj("TSimultaniousPlayerControl", 0x30))])
    e.w32(mp, e.klass("TAoWHSMap", [(0x110, SHOWMSG), (0x12C, SHOWDLG)]))
    e.mu.mem_write(mp + 0xA4, bytes([1, 0])); e.mu.mem_write(mp + 0x13A, bytes([network]))
    for rva in (L.HANDLEANY_RVA, L.DONEEXCEPT_RVA, L.PLAY_THUNK_RVA): e.mu.mem_write(EPACK + rva, b"\xFF\x25")
    e.w32(EPACK + L.PLAY_THUNK_RVA + 2, SLOT); e.w32(SLOT, PLAY)
    e.w32(EPACK + L.MAP_RVA, mp)
    gd = e.alloc(0x200, 0x11)
    form = e.obj("TDPlayForm", 0x50, [(0x44, gd)])
    e.w32(EPACK + L.MSGLOG_CLS_RVA, 0x557FCD24); e.w32(EPACK + L.RIG_V_RVA + L.RV_REALDR, 0x41414141)   # handler running
    cell = e.alloc(4); e.w32(cell, form); e.w32(L.X_DPFORM, cell)
    return dict(map=mp, ex=ex, tm=tm, ai=ai, gd=gd)


def boot():
    e = Emu()
    assert e.call(info["main"], [B, 1, 0], 3) == 1 and e.timer, "DllMain"
    return e


def main():
    show = "--show" in sys.argv
    n_ok = 0

    def ok(cond, what):
        nonlocal n_ok
        assert cond, "FAILED: " + what
        n_ok += 1; print("  ok  " + what)

    # 1. no map: timer runs, nothing written
    e = boot()
    for _ in range(5): e.tproc()
    ok(e.take() == "", "no map -> nothing logged")

    # 2. network game locked without progress -> one automatic report at FZ_SECS
    g = fake_game(e)
    for _ in range(FZ - 2): e.tproc()
    ok("FREEZE" not in e.take(), "nothing before %d s" % FZ)
    for _ in range(5): e.tproc()
    t = e.take()
    if show: print(t)
    ok(t.count("*** GAME STATE REPORT ***") == 1 and "automatic" in t, "one automatic report at %d s" % FZ)
    for needle in ("turn player 1, local player 0", "network 1", "sync seed DEADBEEF", "executed 4321", "lock count 1",
                   "current seat index 1", "(TTokenManager)", "(TTokenExecuter)", "events of the current seat: 1 waiting",
                   "event @", "(TArmyCombatMoveTE)", "system events: 0 waiting", "token control 0 @", "seat 1, active 1  <- current",
                   "(TAIExecuter)", "(TSimultaniousPlayerControl)", "(TPlayerCommunicator)", "player 0: turn ended 1",
                   "player 1: turn ended 0, +44 0, +45 1", "player 2:", "restore handler state", "DirectPlay state",
                   "11111111 11111111", "(end of the game state report)",
                   "first event: object at +1C (combat unit of a move) @", "(TTacticalCombatUnit)", "09000A00",
                   "its +60 (unit on the battlefield) @", "(TTacticalCombatUnitHS)", "00AB0003", "its +4C (unit) @", "(TUnit)"):
        ok(needle in t, "report has %r" % needle)
    for _ in range(120): e.tproc()
    ok(e.take() == "", "no second report in the same episode")
    # progress -> follow-up line, then a new episode can report again
    e.w32(g["ex"] + 0x18, 4322); e.tproc()
    t = e.take()
    ok("game state report follow-up: the game moved on after about %d s" % (FZ - 2 + 5 + 120) in t, "follow-up line with the lock time (%s)" % t.strip()[-40:])
    for _ in range(FZ - 1): e.tproc()
    ok(e.take() == "", "new episode: quiet for %d s" % (FZ - 1))
    for _ in range(3): e.tproc()
    ok(e.take().count("*** GAME STATE REPORT ***") == 1, "new episode reports again")
    # lock released -> follow-up, idle -> nothing
    e.w32(g["ex"] + 0x4C, 0); e.tproc()
    ok("follow-up" in e.take(), "follow-up when the lock is released")
    for _ in range(200): e.tproc()
    ok(e.take() == "", "idle game (no lock) never reports")

    # 3. event mid-execution (status bit 2) and AI lock also count as busy
    e.mu.mem_write(g["ex"] + 0x24, b"\x02")
    for _ in range(FZ + 3): e.tproc()
    ok("*** GAME STATE REPORT ***" in e.take(), "status bit 2 counts as busy")
    e.mu.mem_write(g["ex"] + 0x24, b"\x00"); e.tproc(); e.take()
    e.w32(g["ai"] + 0x30, 1)
    for _ in range(FZ + 3): e.tproc()
    ok("*** GAME STATE REPORT ***" in e.take(), "AI executer lock counts as busy")

    ok(e.shown == [] and e.played == [], "automatic reports stay silent (no status text, no sound)")

    # 4. hot-seat / single player: no automatic report, but Ctrl+F works; held key = one report; other window = none
    e = boot(); g = fake_game(e, network=0)
    for _ in range(200): e.tproc()
    ok(e.take() == "", "non-network game: no automatic report")
    e.keys = {0x11, 0x46}
    for _ in range(5): e.tproc(100)
    t = e.take()
    ok(t.count("*** GAME STATE REPORT ***") == 1 and "requested with Ctrl+F" in t, "Ctrl+F -> exactly one report while held")
    ok(e.shown == ["Game state data recorded to Error Log"], "status-bar text shown once: %r" % e.shown)
    ok(e.played == ["SFX\\EVENTS\\CHAT.WAV"], "chat sound played once: %r" % e.played)
    ok(len(e.slot_seen) == 1 and B <= e.slot_seen[0] < B + e.soi, "the game's own message sound is silenced during the call")
    ok(e.u32(SLOT) == PLAY, "sound import slot restored")
    e.keys = set(); e.tproc(100); e.keys = {0x11, 0x46}; e.fg_pid = 1; e.tproc(100)
    ok(e.take() == "" and len(e.shown) == 1, "Ctrl+F with another window in front -> nothing")
    e.keys = {0x46}; e.fg_pid = PID; e.tproc(100)
    ok(e.take() == "" and len(e.shown) == 1, "F without Ctrl -> nothing")
    e.keys = set(); e.tproc(100); e.keys = {0x11, 0x46}; e.tproc(100)
    ok("*** GAME STATE REPORT ***" in e.take() and len(e.shown) == 2 and len(e.played) == 2, "second press -> second report + confirmation")
    # sound thunk not recognised -> report still written, no confirmation, nothing touched
    e = boot(); g = fake_game(e, network=0); e.mu.mem_write(EPACK + L.PLAY_THUNK_RVA, b"\x90\x90")
    e.keys = {0x11, 0x46}; e.tproc(100)
    ok("*** GAME STATE REPORT ***" in e.take() and e.shown == [] and e.played == [] and e.u32(SLOT) == PLAY,
       "unknown sound thunk -> report only, no confirmation")

    # 5. junk pointers everywhere: no crash, report still ends cleanly
    e = boot(); g = fake_game(e)
    e.w32(g["ex"] + 0x10, 0x12345678); e.w32(g["ex"] + 0x14, 0xFFFFFFF0); e.w32(g["ex"] + 0x50, 3)
    e.w32(g["map"] + 0x128, 0x7FFFFFFF); e.w32(g["map"] + 0x140, 0xABCDEF01); e.w32(g["map"] + 0x244, 0); e.w32(L.X_DPFORM, 0x666)
    e.w32(g["map"] + 0x120, 0xBAD0BAD0)
    for _ in range(FZ + 3): e.tproc()
    t = e.take()
    ok("*** GAME STATE REPORT ***" in t and "(end of the game state report)" in t and "not readable" in t, "junk pointers -> report completes")
    e.w32(g["map"] + 0x23C, 0x99999999)
    e.keys = {0x11, 0x46}; e.tproc(100)
    t = e.take()
    ok("(end of the game state report)" in t, "junk token manager -> manual report completes")

    # 6. export TestFreeze
    e = boot(); fake_game(e)
    e.call(info["tfz"], [0], 1)
    ok("*** GAME STATE REPORT ***" in e.take(), "export TestFreeze writes a report")
    e2 = boot(); e2.call(info["tfz"], [0], 1)
    ok(e2.take() == "", "TestFreeze without a map -> nothing")
    # 7. Ctrl+R manual restore
    V = EPACK + L.RIG_V_RVA
    CTRL_R = {0x11, 0x52}

    def press(e, keys=CTRL_R):
        e.keys = set(); e.tproc(100); e.keys = set(keys); e.tproc(100)

    def answer(e, result):
        dlg = e.dialogs[-1]
        e.mu.mem_write(dlg["log"] + 0x26, bytes([result]))
        e.call(dlg["fn"], [], 0, eax=dlg["obj"], edx=dlg["log"])

    e = boot(); g = fake_game(e, lock=0)
    press(e)
    ok(len(e.dialogs) == 1 and e.dialogs[0]["style"] == 2 and e.dialogs[0]["title"] == "Restore Game"
       and e.added == ["Restore the game for all players?"], "host Ctrl+R -> Yes/No prompt: %r %r" % (e.dialogs and e.dialogs[0]["title"], e.added))
    ok(e.dialogs[0]["fn"] == info["rscb"] and e.dialogs[0]["obj"] == g["map"] and e.released == 1, "prompt shown with our callback, our reference released")
    ok(e.take() == "" and e.mu.mem_read(V + L.RV_OOS, 1)[0] == 0, "nothing happens before the answer")
    for _ in range(5): e.tproc(100)
    press(e)
    ok(len(e.dialogs) == 1, "no second prompt while one is open")
    answer(e, 4)
    for _ in range(5): e.tproc(100)
    ok(e.take() == "" and e.mu.mem_read(V + L.RV_OOS, 1)[0] == 0 and e.mu.mem_read(L.X_MAN, 1)[0] == 0, "No -> no restore, no report")
    press(e)
    ok(len(e.dialogs) == 2, "after No the prompt can be opened again")
    answer(e, 3); e.keys = set(); e.tproc(100)
    t = e.take()
    ok(t.count("*** GAME STATE REPORT ***") == 1 and "requested with Ctrl+R (restore)" in t, "Yes -> freeze report first")
    ok(e.mu.mem_read(V + L.RV_OOS, 1)[0] == 6 and e.mu.mem_read(L.X_MAN, 1)[0] == L.MAN_MARK, "Yes -> manual marker set + handler told to restore (V_OOS 6)")
    press(e)
    ok(len(e.dialogs) == 2, "while the handler is busy (V_OOS != 0) Ctrl+R does nothing")
    # Yes, but the handler became busy in the meantime (e.g. an Out of Sync restore started)
    e = boot(); g = fake_game(e, lock=0); press(e)
    e.mu.mem_write(V + L.RV_STATE, b"\x01"); answer(e, 3); e.keys = set(); e.tproc(100)
    ok(e.take() == "" and e.mu.mem_read(V + L.RV_OOS, 1)[0] == 0 and e.mu.mem_read(L.X_MAN, 1)[0] == 0, "Yes while the handler is busy -> dropped")
    # client
    e = boot(); g = fake_game(e, lock=0); e.mu.mem_write(g["gd"] + 0x1EF, b"\x00"); press(e)
    ok(e.dialogs == [] and e.shown == ["Only the host can restore the game"] and e.played == ["SFX\\EVENTS\\CHAT.WAV"]
       and e.mu.mem_read(V + L.RV_OOS, 1)[0] == 0, "client Ctrl+R -> notice only: %r" % e.shown)
    # handler absent / frozen / dialog up / somebody dropped / not a network game / other window
    for what, prep in (("restore handler not running", lambda e, g: e.w32(V + L.RV_REALDR, 0)),
                       ("handler frozen", lambda e, g: e.mu.mem_write(V + L.RV_FROZEN, b"\x01")),
                       ("handler dialog open", lambda e, g: e.mu.mem_write(V + L.RV_DLG, b"\x01")),
                       ("a player dropped (role set)", lambda e, g: (e.w32(L.X_RIG, g["gd"]), e.mu.mem_write(g["gd"], b"\x01"))),
                       ("another window in front", lambda e, g: setattr(e, "fg_pid", 1))):
        e = boot(); g = fake_game(e, lock=0); prep(e, g); press(e)
        ok(e.dialogs == [] and e.shown == [] and e.take() == "", "Ctrl+R ignored: " + what)
    e = boot(); g = fake_game(e, network=0, lock=0); press(e)
    ok(e.dialogs == [] and e.shown == [], "Ctrl+R ignored in a non-network game")
    e = boot(); g = fake_game(e, lock=0); press(e, {0x52})
    ok(e.dialogs == [], "R without Ctrl -> nothing")
    print("ALL %d CHECKS PASSED" % n_ok)
    return 0


if __name__ == "__main__":
    sys.exit(main())
