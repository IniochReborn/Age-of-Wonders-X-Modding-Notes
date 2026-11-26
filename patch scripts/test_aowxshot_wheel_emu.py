#!/usr/bin/env python3
"""Unicorn checks for AoWxShot.dll v1.6: the VCL30 LL plain-wheel arm replacement (llwheel / ismap: arrow keys posted
to the map only while the cursor is over it, then the original pass-through) and the 'User' sort click handlers
(on_usort / on_isort -> sortu).  Win32 + VCL30 calls are emulated by Python stubs (stdcall)."""
import os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_ESP, UC_X86_REG_EAX, UC_X86_REG_EIP, UC_X86_REG_EBP, UC_X86_REG_EBX, \
    UC_X86_REG_ESI, UC_X86_REG_EDI, UC_X86_REG_EDX, UC_X86_REG_ECX
_exit, sys.exit = sys.exit, (lambda *_a: None)
import test_aowxshot_missing_emu as T   # reuses its build + label helper (its own checks run first)
sys.exit = _exit

LLWHEEL, LLTILT, ON_USORT, ON_ISORT = T.labels(["llwheel", "lltilt", "on_usort", "on_isort"])
mem, B, G, imps = T.mem, T.B, T.G, T.imps
STUB = 0x1E0000
BAIL = 0x1E0800                       # stands in for VCL30 0x413A909B (emulation stops there)
SWAL = 0x1E0900                       # stands in for VCL30 0x413A90A5 (tilt exit)
MAP, PANEL, SCAN = 0x111, 0x222, 0x333
CLS = {MAP: b"THSMEdit", PANEL: b"TPanel", SCAN: b"TDisplay", 0x444: b"THSMEditX"}
NAMES = ["GetCursorPos", "WindowFromPoint", "GetClassNameA", "PostMessageA", "UPD", "LOOKUP"]
NARGS = {"GetCursorPos": 1, "WindowFromPoint": 2, "GetClassNameA": 3, "PostMessageA": 4, "UPD": 0, "LOOKUP": 0}


class Env(object):
    def __init__(self, under, vk=0x28):
        self.under, self.vk, self.posts, self.calls, self.lookups = under, vk, [], [], []
        mu = self.mu = Uc(UC_ARCH_X86, UC_MODE_32)
        mu.mem_map(B, (len(mem) + 0xFFF) & ~0xFFF)
        mu.mem_write(B, bytes(mem))
        mu.mem_map(0x100000, 0x100000)
        mu.mem_map(0xDEAD0000, 0x1000)
        mu.mem_map((0x12340000 + 0x413E7150) & ~0xFFF, 0x1000)     # VCL30 chord state byte
        self.stubs = {}
        for i, n in enumerate(NAMES):
            a = STUB + 0x10 * i
            mu.mem_write(a, b"\xc3")
            self.stubs[a] = n
            if n in imps:
                mu.mem_write(imps[n], struct.pack("<I", a))
        mu.mem_write(G["g_vlook"], struct.pack("<I", STUB + 0x50))
        mu.mem_write(G["g_vbail"], struct.pack("<I", BAIL))
        mu.mem_write(G["g_vswal"], struct.pack("<I", SWAL))
        mu.hook_add(UC_HOOK_CODE, self.hook, begin=STUB, end=STUB + 0x100)

    def arg(self, i):
        return struct.unpack("<I", self.mu.mem_read(self.mu.reg_read(UC_X86_REG_ESP) + 4 + 4 * i, 4))[0]

    def hook(self, mu, addr, size, _u):
        n = self.stubs.get(addr)
        if n is None:
            return
        a = [self.arg(i) for i in range(NARGS[n])]
        r = 0
        if n == "GetCursorPos":
            mu.mem_write(a[0], struct.pack("<ii", 640, 480)); r = 1
        elif n == "WindowFromPoint":
            assert (a[0], a[1]) == (640, 480), a
            r = self.under
        elif n == "GetClassNameA":
            c = CLS.get(a[0], b"X")
            mu.mem_write(a[1], c + b"\0"); r = len(c)
        elif n == "PostMessageA":
            self.posts.append(a); r = 1
        elif n == "UPD":
            self.calls.append(mu.reg_read(UC_X86_REG_EAX))
        elif n == "GetForegroundWindow":
            r = self.fg
        elif n == "LOOKUP":                      # VCL30 VK lookup: needs the VCL delta (ebx) + row (edx) intact
            self.lookups.append((mu.reg_read(UC_X86_REG_EBX), mu.reg_read(UC_X86_REG_EDX)))
            r = self.vk
        sp = mu.reg_read(UC_X86_REG_ESP)
        ret = struct.unpack("<I", mu.mem_read(sp, 4))[0]
        mu.reg_write(UC_X86_REG_ESP, sp + 4 + 4 * NARGS[n])
        mu.reg_write(UC_X86_REG_EAX, r)
        mu.reg_write(UC_X86_REG_EIP, ret)

    def wheel(self, entry=None, stop=BAIL):
        mu = self.mu
        sp = 0x1F8000
        regs = {UC_X86_REG_EBX: 0x12340000, UC_X86_REG_EDX: 0x413E7173, UC_X86_REG_ESI: 0x150000,
                UC_X86_REG_EDI: 0xD1, UC_X86_REG_EBP: 0x1F9000, UC_X86_REG_ECX: 0xCC}
        mu.reg_write(UC_X86_REG_ESP, sp)
        for r, v in regs.items():
            mu.reg_write(r, v)
        mu.emu_start(entry or LLWHEEL, stop, count=100000)
        assert mu.reg_read(UC_X86_REG_EIP) == stop, hex(mu.reg_read(UC_X86_REG_EIP))
        assert mu.reg_read(UC_X86_REG_ESP) == sp, "stack not balanced"
        assert all(mu.reg_read(r) == v for r, v in regs.items()), "registers not restored for the VCL30 tail"
        assert self.lookups == [(0x12340000, 0x413E7173)], self.lookups
        return self.posts


ok = True


def check(name, got, want):
    global ok
    print("%-62s %s" % (name, "ok" if got == want else "FAIL got %r want %r" % (got, want)))
    ok &= got == want


check("cursor over map -> VK_DOWN down+up posted to the map, pass-through",
      Env(MAP).wheel(), [[MAP, 0x100, 0x28, 1], [MAP, 0x101, 0x28, 0xC0000001]])
check("cursor over side panel -> no keys, pass-through", Env(PANEL).wheel(), [])
check("cursor over scanner -> no keys, pass-through", Env(SCAN).wheel(), [])
check("class 'THSMEditX' is not the map", Env(0x444).wheel(), [])
check("unbound wheel (VK 0) -> nothing", Env(MAP, vk=0).wheel(), [])
check("wheel up row -> VK_UP", Env(MAP, vk=0x26).wheel()[0][2], 0x26)
check("tilt over map -> VK_RIGHT posted, exits via the swallow tail",
      Env(MAP, vk=0x27).wheel(LLTILT, SWAL), [[MAP, 0x100, 0x27, 1], [MAP, 0x101, 0x27, 0xC0000001]])
check("tilt over side panel -> nothing, swallow tail", Env(PANEL, vk=0x25).wheel(LLTILT, SWAL), [])

for fn, off, cache in ((ON_USORT, 0x3AC, "g_hupd"), (ON_ISORT, 0x39C, "g_iupd")):
    e = Env(under=0)
    mu = e.mu
    form, grid = 0x160000, 0x170000
    mu.mem_write(form + off, struct.pack("<I", grid))
    mu.mem_write(grid + 0x1EC, b"\x01")
    mu.mem_write(G[cache], struct.pack("<I", STUB + 0x40))
    sp = 0x1F8000
    mu.mem_write(sp, struct.pack("<I", 0xDEAD0000))
    mu.reg_write(UC_X86_REG_ESP, sp)
    mu.reg_write(UC_X86_REG_EAX, form)
    mu.reg_write(UC_X86_REG_EBX, 0xB0B)
    mu.emu_start(fn, 0xDEAD0000, count=100000)
    check("sort-user click grid +%#x: mode 2 + Update(grid)" % off,
          (mu.mem_read(grid + 0x1EC, 1)[0], e.calls, mu.reg_read(UC_X86_REG_ESP), mu.reg_read(UC_X86_REG_EBX)),
          (2, [grid], sp + 4, 0xB0B))

# ---- v1.8: Mouse5 + wheel chord arm (llchord) -> map level up / down through a posted WM_TIMER (lvl_tp)
LLCHORD, LVL_TP = T.labels(["llchord", "lvl_tp"])
CHRET, FG_STUB = 0x1E0A00, STUB + 0x60
MAINF, DLG = 0x555, 0x666
CLS.update({MAINF: b"TMainForm", DLG: b"TPropForm", SCAN: b"TScannerFloater"})


def chord(vk, fg, state=2):
    e = Env(under=0, vk=vk)
    mu = e.mu
    mu.mem_write(FG_STUB, b"\xc3")
    e.stubs[FG_STUB] = "GetForegroundWindow"
    NARGS["GetForegroundWindow"] = 0
    mu.mem_write(imps["GetForegroundWindow"], struct.pack("<I", FG_STUB))
    mu.mem_write(G["g_vchret"], struct.pack("<I", CHRET))
    e.fg = fg
    mu.mem_write(0x12340000 + 0x413E7150, bytes([state]))
    level = vk in (0x21, 0x22) or state & 1
    stop = SWAL if level else CHRET
    sp = 0x1F8000
    regs = {UC_X86_REG_EBX: 0x12340000, UC_X86_REG_EDX: 0x413E7172, UC_X86_REG_ESI: 0x150000,
            UC_X86_REG_EDI: 0xD1, UC_X86_REG_EBP: 0x1F9000, UC_X86_REG_ECX: 0x20A}
    mu.reg_write(UC_X86_REG_ESP, sp)
    for r, v in regs.items():
        mu.reg_write(r, v)
    mu.emu_start(LLCHORD, stop, count=100000)
    assert mu.reg_read(UC_X86_REG_EIP) == stop, hex(mu.reg_read(UC_X86_REG_EIP))
    assert mu.reg_read(UC_X86_REG_ESP) == sp, "stack not balanced"
    assert all(mu.reg_read(r) == v for r, v in regs.items()), "registers not restored"
    if not level:
        assert mu.reg_read(UC_X86_REG_EAX) == vk
    return e.posts, len(e.lookups)


check("Mouse5+wheel up (PgUp), main form in front -> WM_TIMER(level up) posted, swallowed",
      chord(0x21, MAINF), ([[MAINF, 0x113, 0x4C560021, LVL_TP]], 1))
check("Mouse5+wheel down (PgDn), scanner floater in front -> level down posted",
      chord(0x22, SCAN), ([[SCAN, 0x113, 0x4C560022, LVL_TP]], 1))
check("PgUp chord while a dialog is in front -> nothing, swallowed", chord(0x21, DLG), ([], 1))
check("PgUp chord, no foreground window -> nothing", chord(0x21, 0), ([], 1))
check("other chord VK ('N', Mouse5) -> original path: lookup re-run, returns to the keybd_event call", chord(0x4E, MAINF), ([], 2))
check("unbound chord (VK 0) -> original path", chord(0, MAINF), ([], 2))
check("Mouse4+wheel, main form in front -> WM_TIMER(fog) posted, swallowed, no key",
      chord(0x4E, MAINF, state=1), ([[MAINF, 0x113, 0x4C560001, LVL_TP]], 0))
check("Mouse4+wheel while a dialog is in front -> nothing", chord(0x50, DLG, state=1), ([], 0))

for wparam, want in ((0x4C560021, [("up", 0x160000)]), (0x4C560022, [("down", 0x160000)]), (0x7F01, []),
                     (0x4C560026, [])):
    e = Env(under=0)
    mu = e.mu
    mu.mem_map(0x429000, 0x1000)
    mu.mem_write(0x429ED8, b"\xc3"); mu.mem_write(0x429D80, b"\xc3")
    got = []
    mu.hook_add(UC_HOOK_CODE, lambda m, a, s, u: got.append(("up" if a == 0x429ED8 else "down", m.reg_read(UC_X86_REG_EAX)))
                if a in (0x429ED8, 0x429D80) else None, begin=0x429000, end=0x42A000)
    mu.mem_write(G["g_mform"], struct.pack("<I", 0x160000))
    sp = 0x1F8000
    mu.mem_write(sp, struct.pack("<IIIII", 0xDEAD0000, MAINF, 0x113, wparam, 1234))
    mu.reg_write(UC_X86_REG_ESP, sp)
    for r in (UC_X86_REG_EBX, UC_X86_REG_ESI, UC_X86_REG_EDI, UC_X86_REG_EBP):
        mu.reg_write(r, 0xB0B)
    mu.emu_start(LVL_TP, 0xDEAD0000, count=100000)
    check("timer callback id %#x -> %s" % (wparam, want or "nothing"),
          (got, mu.reg_read(UC_X86_REG_ESP), [mu.reg_read(r) for r in (UC_X86_REG_EBX, UC_X86_REG_ESI, UC_X86_REG_EDI, UC_X86_REG_EBP)]),
          (want, sp + 0x14, [0xB0B] * 4))


def tilt_x1(row, fg):
    e = Env(under=0, vk=0x44)
    mu = e.mu
    e.stubs[FG_STUB] = "GetForegroundWindow"; mu.mem_write(FG_STUB, b"\xc3"); NARGS["GetForegroundWindow"] = 0
    mu.mem_write(imps["GetForegroundWindow"], struct.pack("<I", FG_STUB)); e.fg = fg
    mu.mem_write(0x12340000 + 0x413E7150, b"\x01")
    sp = 0x1F8000
    regs = {UC_X86_REG_EBX: 0x12340000, UC_X86_REG_EDX: row, UC_X86_REG_ESI: 0x150000,
            UC_X86_REG_EDI: 0xD1, UC_X86_REG_EBP: 0x1F9000, UC_X86_REG_ECX: 0x20E}
    mu.reg_write(UC_X86_REG_ESP, sp)
    for r, v in regs.items():
        mu.reg_write(r, v)
    mu.emu_start(LLTILT, SWAL, count=100000)
    assert mu.reg_read(UC_X86_REG_EIP) == SWAL and mu.reg_read(UC_X86_REG_ESP) == sp
    assert all(mu.reg_read(r) == v for r, v in regs.items()), "registers not restored"
    return e.posts, len(e.lookups)


check("Mouse4 + tilt right -> WM_TIMER(brush bigger), swallowed, no key",
      tilt_x1(0x413E7179, MAINF), ([[MAINF, 0x113, 0x4C560003, LVL_TP]], 0))
check("Mouse4 + tilt left -> WM_TIMER(brush smaller)", tilt_x1(0x413E7176, MAINF), ([[MAINF, 0x113, 0x4C560002, LVL_TP]], 0))
check("Mouse4 + tilt with a dialog in front -> nothing", tilt_x1(0x413E7176, DLG), ([], 0))

for cur, wparam, want in ((1, 3, (1, 0x4296B4)), (2, 3, (2, 0x4296C4)), (3, 3, (3, 0x4296C4)), (7, 3, (0, 0x4296A4)),
                          (1, 2, (3, 0x4296C4)), (7, 2, (2, 0x4296C4)), (2, 2, (0, 0x4296A4))):
    e = Env(under=0)
    mu = e.mu
    mu.mem_map(0x402000, 0x1000); mu.mem_map(0x429000, 0x1000); mu.mem_map(0x432000, 0x1000)
    form, hsm, comps, items, mapobj = 0x160000, 0x161000, 0x162000, 0x162100, 0x163000
    btn = [0x164000 + 0x100 * i for i in range(4)]
    for a in (0x402318, 0x4296A4, 0x4296B4, 0x4296C4):
        mu.mem_write(a, b"\xc3")
    mu.mem_write(form + 0x22C, struct.pack("<I", hsm)); mu.mem_write(hsm + 0x1BC, b"\x01"); mu.mem_write(hsm + 0x1AC, bytes([cur]))
    mu.mem_write(form + 0x10, struct.pack("<I", comps)); mu.mem_write(comps + 4, struct.pack("<II", items, 6))
    mu.mem_write(items, struct.pack("<6I", 0x111, btn[0], btn[1], btn[2], btn[3], 0x222))
    mu.mem_write(form + 0x5F0, struct.pack("<3I", *btn[:3]))
    mu.mem_write(0x43289C, struct.pack("<I", 0x432900)); mu.mem_write(0x432900, struct.pack("<I", mapobj))
    mu.mem_write(G["g_mform"], struct.pack("<I", form))
    TICK = STUB + 0x70
    mu.mem_write(TICK, b"\xc3"); e.stubs[TICK] = "GetTickCount"; NARGS["GetTickCount"] = 0
    mu.mem_write(imps["GetTickCount"], struct.pack("<I", TICK))
    got = []

    def hk(m, a, sz, u):
        if a == 0x402318:
            got.append(("down", m.reg_read(UC_X86_REG_EAX), m.reg_read(UC_X86_REG_EDX) & 0xFF))
        elif a in (0x4296A4, 0x4296B4, 0x4296C4):
            got.append(("click", a, m.reg_read(UC_X86_REG_EAX), m.reg_read(UC_X86_REG_EDX)))
    mu.hook_add(UC_HOOK_CODE, hk, begin=0x402000, end=0x42A000)
    sp = 0x1F8000
    mu.mem_write(sp, struct.pack("<IIIII", 0xDEAD0000, MAINF, 0x113, 0x4C560000 | wparam, 1234))
    mu.reg_write(UC_X86_REG_ESP, sp)
    for r in (UC_X86_REG_EBX, UC_X86_REG_ESI, UC_X86_REG_EDI, UC_X86_REG_EBP):
        mu.reg_write(r, 0xB0B)
    # GetTickCount stub returns 0 -> pre-age the debounce stamp
    mu.mem_write(G["g_brt"], struct.pack("<I", 0x80000000))
    mu.emu_start(LVL_TP, 0xDEAD0000, count=100000)
    b = btn[want[0]]
    check("brush size %d, id %d -> button %d, handler %#x" % (cur, wparam, want[0] + 1, want[1]),
          (got, mu.reg_read(UC_X86_REG_ESP), mu.reg_read(UC_X86_REG_EBX)),
          ([("down", b, 1), ("click", want[1], form, b)], sp + 0x14, 0xB0B))

print("ALL OK" if ok else "FAILURES")
sys.exit(0 if ok else 1)
