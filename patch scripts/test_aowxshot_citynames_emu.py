#!/usr/bin/env python3
r"""Unicorn test of the AoWxShot.dll city-names module (aowxshot_citynames.py) against the real Dict\xCityNamesV.mld:
cninit (in-memory patches + refusal), cn_create (new city name), cn_setrace (race change), cn_update (Update
Nameless), and the tab (cn_build / cn_store through the Ban List wrappers).

    py -3.10 test_aowxshot_citynames_emu.py
"""
import collections, os, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "modding tools"))
import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import (UC_X86_REG_ESP, UC_X86_REG_EAX, UC_X86_REG_EDX, UC_X86_REG_ECX, UC_X86_REG_EBP,
                               UC_X86_REG_EBX, UC_X86_REG_EDI, UC_X86_REG_ESI, UC_X86_REG_EIP, UC_X86_REG_EFLAGS)
import build_aowxshot as SHOT
import aowxshot_banlist as BL
import aowxshot_citynames as CN
import aowxshot_levelvision as LV
from aowxlib import mld as MLD

GD = os.path.dirname(HERE)
img, info = SHOT.build(GD)
pe = pefile.PE(data=img)
B = SHOT.BASE
mem = pe.get_memory_mapped_image()
imps = {s.name.decode(): s.address for d in pe.DIRECTORY_ENTRY_IMPORT for s in d.imports}
MLDBYTES = open(os.path.join(GD, "Dict", "xCityNamesV.mld"), "rb").read()
LISTS = collections.defaultdict(set)
for r in MLD.MLDFile.parse(MLDBYTES).records:
    LISTS[r.ClassName.decode()].add(r.Original)


def labels(names):
    D_, _ = SHOT.build_data(B + SHOT.SEC_RVA, GD)
    D_.align(16)
    ib, IAT, *_r = SHOT.build_imports(SHOT.SEC_RVA + len(D_.b))
    body = (len(D_.b) + len(ib) + 15) & ~15
    code_va = B + SHOT.SEC_RVA + body
    assert code_va == info["code_va"]
    nl = chr(10)
    src = SHOT.asm_text(D_, IAT, code_va).replace("        mov eax, initx" + nl, "        mov eax, initx" + nl + "".join(
        "        mov eax, %s" % n + nl for n in names))
    c = SHOT.assemble(src, code_va + 0x20)
    t = c[-5 * len(names):]
    return [struct.unpack_from("<I", t, 5 * i + 1)[0] for i in range(len(names))]


CNINIT, CNCREATE, CNSETRACE, CNUPDATE, FCWRAP, OKHOOK, CNRACECB = labels(["cninit", "cn_create", "cn_setrace", "cn_update", "bl_fcwrap", "bl_ok", "cn_racecb"])
STUB, EXE, EPACK, VCL, HEAP, STOP = 0x90000000, 0x400000, 0x55700000, 0x41300000, 0x100000, 0xDEAD0000
REG = {"eax": UC_X86_REG_EAX, "edx": UC_X86_REG_EDX, "ecx": UC_X86_REG_ECX, "ebx": UC_X86_REG_EBX, "edi": UC_X86_REG_EDI,
       "esi": UC_X86_REG_ESI, "ebp": UC_X86_REG_EBP, "esp": UC_X86_REG_ESP}
ok = True


def check(name, cond):
    global ok
    print("%-78s %s" % (name, "ok" if cond else "FAIL")); ok &= bool(cond)


class Emu(object):
    def __init__(self, instsize=CN.INSTSIZE_WANT, mapflags=0, mbox=6, havefile=True):
        mu = self.mu = Uc(UC_ARCH_X86, UC_MODE_32)
        mu.mem_map(B, (len(mem) + 0xFFF) & ~0xFFF); mu.mem_write(B, bytes(mem))
        mu.mem_map(HEAP, 0x300000); mu.mem_map(STOP, 0x1000); mu.mem_map(STUB, 0x1000); mu.mem_map(EXE, 0x40000)
        mu.mem_map(EPACK, 0x200000); mu.mem_map(VCL, 0x80000)
        self.heap = HEAP + 0x1000; self.handlers = []; self.redirect = {}; self.log = []
        self.mbox, self.havefile, self.tick = mbox, havefile, 0x12345
        mu.hook_add(UC_HOOK_CODE, self._hook, begin=STUB, end=STUB + 0xFFF)
        mu.hook_add(UC_HOOK_CODE, self._redir, begin=EPACK, end=VCL + 0x80000)
        w32 = self.w32
        # AoWEPACK image bits
        w32(EPACK + CN.INSTSIZE_RVA, instsize)
        site = EPACK + CN.CREATE_CALL_RVA
        mu.mem_write(site, b"\xe8" + struct.pack("<i", EPACK + CN.LSTRASG_THUNK_RVA - (site + 5)))
        mu.mem_write(EPACK + CN.SETRACE_RVA, bytes.fromhex("538bd83a53457421"))
        self.map = self.alloc(0x500); w32(self.map + CN.MAP_SET, mapflags)
        mu.mem_write(CN.SITE_RACECB, bytes.fromhex("ff9144020000"))
        w32(EPACK + CN.CITY_VMT_RVA + CN.V_SETRACE, EPACK + CN.SETRACE_RVA)
        self.edit_text = {}
        def gettext(e):
            t_ = self.edit_text.get(e.r("eax"), b""); w32(e.r("edx"), self.ansi(t_) if t_ else 0)
        self.jmp_at(CN.T_GETTEXT, self.stub(gettext))
        self.jmp_at(CN.T_LSTRCLR, self.stub(lambda e: w32(e.r("eax"), 0)))
        def settext(e):
            p_ = e.r("edx"); self.edit_text[e.r("eax")] = e.cstr(p_) if p_ else b""; self.log.append(("settext", e.r("eax"), self.edit_text[e.r("eax")]))
        self.jmp_at(BL.T_SETTEXT, self.stub(settext))
        def setname_thunk(e):
            c_, s_ = e.r("eax"), e.r("edx"); nm_ = e.cstr(s_) if s_ else b""
            self.log.append(("setname", c_, nm_)); w32(c_ + CN.CITY_NAME, self.ansi(nm_) if nm_ else 0)
        self.jmp_at(CN.T_CITY_SETNAME, self.stub(setname_thunk))
        w32(EPACK + CN.HSMAP_RVA, self.map); w32(CN.IAT_HSMAP, EPACK + CN.HSMAP_RVA)
        self.redirect[EPACK + CN.LSTRASG_THUNK_RVA] = self._lstrasg
        self.redirect[EPACK + CN.SETNAME_RVA] = self._setname
        self.redirect[EPACK + CN.SETRACE_BACK_RVA] = self._setrace_back
        self.redirect[VCL + CN.SETSTYLE_RVA] = lambda: self._ret(("style", self.r("eax"), self.r("edx") & 0xFF))
        self.redirect[VCL + BL.SPC_RVA] = lambda: self._ret(("spc", self.r("eax"), self.r("edx")))
        mu.mem_write(VCL + BL.SPC_RVA, struct.pack("<II", BL.SPC_B0, BL.SPC_B1))
        w32(VCL + CN.SETSTYLE_RVA, CN.SETSTYLE_B0)
        # Win32
        def gmh(e): return {b"aowepack.dll": EPACK, b"vcl30.dpl": VCL}.get(e.cstr(e.arg(0)).lower(), 0)
        self.imp("GetModuleHandleA", gmh, 4); self.imp("VirtualProtect", lambda e: 1, 16)
        def gmfn(e):
            p = b"C:\\Games\\Age of Wonders X\\AoWDevX.exe"; mu.mem_write(e.arg(1), p + b"\0"); return len(p)
        self.imp("GetModuleFileNameA", gmfn, 12)
        def cf(e):
            self.log.append(("open", e.cstr(e.arg(0)))); return 0x77 if self.havefile else 0xFFFFFFFF
        self.imp("CreateFileA", cf, 28)
        self.imp("GetFileSize", lambda e: len(MLDBYTES), 8)
        self.imp("VirtualAlloc", lambda e: self.alloc(e.arg(1)), 16)
        def rf(e):
            mu.mem_write(e.arg(1), MLDBYTES[:e.arg(2)]); w32(e.arg(3), min(e.arg(2), len(MLDBYTES))); return 1
        self.imp("ReadFile", rf, 20)
        self.imp("CloseHandle", lambda e: self.log.append(("close", e.arg(0))) or 1, 4)
        def tick(e): self.tick += 977; return self.tick
        self.imp("GetTickCount", tick, 0)
        def cmpi(e):
            a_, b_ = e.cstr(e.arg(0)).lower(), e.cstr(e.arg(1)).lower(); return (a_ > b_) - (a_ < b_)
        self.imp("lstrcmpiA", cmpi, 8)
        self.imp("GetActiveWindow", lambda e: 0x5151, 0)
        self.imp("MessageBoxA", lambda e: self.log.append(("mbox", e.arg(0), e.cstr(e.arg(1)), e.cstr(e.arg(2)), e.arg(3))) or self.mbox, 16)

    # ---- helpers
    def r(self, n): return self.mu.reg_read(REG[n])
    def w32(self, a, v): self.mu.mem_write(a, struct.pack("<I", v & 0xFFFFFFFF))
    def r32(self, a): return struct.unpack("<I", self.mu.mem_read(a, 4))[0]
    def arg(self, i): return self.r32(self.r("esp") + 4 + 4 * i)
    def alloc(self, n):
        a = self.heap; self.heap += (n + 31) & ~15; return a
    def cstr(self, a):
        out = bytearray()
        while True:
            c = self.mu.mem_read(a, 1)[0]
            if not c: return bytes(out)
            out.append(c); a += 1
    def ansi(self, text, ref=1):
        a = self.alloc(len(text) + 9); self.mu.mem_write(a, struct.pack("<ii", ref, len(text)) + text + b"\0"); return a + 8
    def imp(self, name, fn, pop): self.w32(imps[name], self.stub(fn, pop))
    def stub(self, fn, pop=0):
        self.handlers.append((fn, pop)); return STUB + 16 * (len(self.handlers) - 1)
    def jmp_at(self, va, target):
        self.mu.mem_write(va, b"\xe9" + struct.pack("<I", (target - (va + 5)) & 0xFFFFFFFF))

    def _hook(self, mu, addr, size, user):
        fn, pop = self.handlers[(addr - STUB) // 16]
        saved = tuple(self.r(n) for n in ("ebx", "esi", "edi", "ebp"))
        res = fn(self)
        assert saved == tuple(self.r(n) for n in ("ebx", "esi", "edi", "ebp"))
        sp = self.r("esp"); ret = self.r32(sp)
        mu.reg_write(UC_X86_REG_ESP, sp + 4 + pop)
        if res is not None: mu.reg_write(UC_X86_REG_EAX, res & 0xFFFFFFFF)
        mu.reg_write(UC_X86_REG_EDX, 0xBAD0EDD0); mu.reg_write(UC_X86_REG_ECX, 0xBAD0ECC0)
        mu.reg_write(UC_X86_REG_EIP, ret)

    def _redir(self, mu, addr, size, user):
        fn = self.redirect.get(addr)
        if fn: fn()

    def _ret(self, entry=None, clobber=True):
        if entry is not None: self.log.append(entry)
        sp = self.r("esp"); ret = self.r32(sp)
        self.mu.reg_write(UC_X86_REG_ESP, sp + 4)
        if clobber:
            for r_ in (UC_X86_REG_EAX, UC_X86_REG_EDX, UC_X86_REG_ECX): self.mu.reg_write(r_, 0xBAD0BAD0)
        self.mu.reg_write(UC_X86_REG_EIP, ret)

    def _lstrasg(self):
        src = self.r("edx")
        self.log.append(("asg", self.r("eax"), self.cstr(src), struct.unpack("<i", self.mu.mem_read(src - 8, 4))[0], self.r32(src - 4), self.r("ebp")))
        self._ret()

    def _setname(self):
        city, src = self.r("eax"), self.r("edx")
        nm = self.cstr(src)
        assert self.r32(src - 4) == len(nm)
        self.log.append(("setname", city, nm))
        self.w32(city + CN.CITY_NAME, self.ansi(nm))
        self._ret()

    def _setrace_back(self):
        zf = self.mu.reg_read(UC_X86_REG_EFLAGS) >> 6 & 1
        sp = self.r("esp")
        self.log.append(("back", self.r("eax"), self.r("edx") & 0xFF, self.r("ebx"), zf, self.r32(sp), self.r("ebp")))
        if not zf: self.mu.mem_write(self.r("ebx") + CN.CITY_RACE, bytes([self.r("edx") & 0xFF]))          # the routine's own store
        self.mu.reg_write(UC_X86_REG_EBX, self.r32(sp)); self.mu.reg_write(UC_X86_REG_ESP, sp + 4)     # the routine's own pop ebx
        self._ret(clobber=False)

    def city(self, name, race, vmt=None):
        c = self.alloc(0x80); self.w32(c, EPACK + CN.CITY_VMT_RVA if vmt is None else vmt)
        self.w32(c + CN.CITY_NAME, self.ansi(name) if name is not None else 0)
        self.mu.mem_write(c + CN.CITY_RACE, struct.pack("b", race)); return c

    def call(self, fn, ebp=0x77777777, **regs):
        sp = HEAP + 0x2F8000
        self.w32(sp, STOP)
        keep = {"ebx": 0x11111111, "esi": 0x22222222, "edi": 0x33333333, "ebp": ebp}
        for k, v_ in keep.items(): self.mu.reg_write(REG[k], v_)
        for k, v_ in regs.items(): self.mu.reg_write(REG[k], v_)
        self.mu.reg_write(UC_X86_REG_ESP, sp)
        self.mu.emu_start(fn, STOP, count=80000000)
        assert self.r("esp") == sp + 4, "stack imbalance %#x" % (self.r("esp") - sp - 4)
        for k in keep:
            if k not in regs: assert self.r(k) == keep[k], k


# ---- 1. cninit -------------------------------------------------------------------------------------------------------
e = Emu(); e.call(CNINIT, ebp=0, esi=0, edi=0)
site = EPACK + CN.CREATE_CALL_RVA; sr = EPACK + CN.SETRACE_RVA
rel = lambda a: a + 5 + struct.unpack("<i", e.mu.mem_read(a + 1, 4))[0]   # noqa: E731
check("cninit: TCity.Create's LStrAsg call -> cn_create", e.mu.mem_read(site, 1)[0] == 0xE8 and rel(site) == CNCREATE)
check("cninit: TCity.SetRace entry -> jmp cn_setrace / nop", e.mu.mem_read(sr, 1)[0] == 0xE9 and rel(sr) == CNSETRACE and e.mu.mem_read(sr + 5, 1)[0] == 0x90
      and bytes(e.mu.mem_read(sr + 6, 2)) == b"\x74\x21")
e2 = Emu(); e2.mu.mem_write(sr + 4, b"\x99"); e2.call(CNINIT, ebp=0, esi=0, edi=0)
check("cninit refuses foreign SetRace bytes: nothing patched", rel.__call__ and e2.mu.mem_read(sr, 1)[0] == 0x53 and
      site + 5 + struct.unpack("<i", e2.mu.mem_read(site + 1, 4))[0] == EPACK + CN.LSTRASG_THUNK_RVA)
e2 = Emu(); e2.mu.mem_write(site + 1, struct.pack("<i", 0x1234)); e2.call(CNINIT, ebp=0, esi=0, edi=0)
check("cninit refuses a foreign Create call target", e2.mu.mem_read(sr, 1)[0] == 0x53 and struct.unpack("<i", e2.mu.mem_read(site + 1, 4))[0] == 0x1234)

# ---- 2. cn_create (in place of LStrAsg: eax = @field, edx = 'Noname') ---------------------------------------------------
noname = e.ansi(b"Noname", ref=-1)
names = []
for i in range(300):
    e.log.clear(); e.call(CNCREATE, eax=0x00ABC000 + i, edx=noname)
    (kind, dest, nm, ref, ln, ebp_), = [x for x in e.log if x[0] == "asg"]
    names.append(nm)
    assert dest == 0x00ABC000 + i and ref == -1 and ln == len(nm) and ebp_ == 0x77777777
check("new city: 300 names, all from the Random category", all(n in LISTS["Random"] for n in names))
check("  ... %d different ones (list has %d), file opened once" % (len(set(names)), len(LISTS["Random"])), len(set(names)) > 120)
e.log.clear(); e.call(CNCREATE, eax=1, edx=noname)
check("  ... file path = <exe dir>\\Dict\\xCityNamesV.mld, not reopened", not [x for x in e.log if x[0] == "open"])
e3 = Emu(); e3.call(CNINIT, ebp=0, esi=0, edi=0); e3.call(CNCREATE, eax=5, edx=e3.ansi(b"Noname", ref=-1))
check("  ... opened %r" % [x[1] for x in e3.log if x[0] == "open"], [x[1] for x in e3.log if x[0] == "open"] == [b"C:\\Games\\Age of Wonders X\\Dict\\xCityNamesV.mld"]
      and ("close", 0x77) in e3.log)
e3 = Emu(mapflags=1); e3.call(CNINIT, ebp=0, esi=0, edi=0); nn = e3.ansi(b"Noname", ref=-1); e3.call(CNCREATE, eax=5, edx=nn)
check("generator switched off in the map: plain 'Noname'", [x[2] for x in e3.log if x[0] == "asg"] == [b"Noname"] and not [x for x in e3.log if x[0] == "open"])
e3 = Emu(havefile=False); e3.call(CNINIT, ebp=0, esi=0, edi=0); nn = e3.ansi(b"Noname", ref=-1)
e3.call(CNCREATE, eax=5, edx=nn); e3.call(CNCREATE, eax=5, edx=nn)
check("list file missing: 'Noname', one open attempt only", [x[2] for x in e3.log if x[0] == "asg"] == [b"Noname"] * 2 and len([x for x in e3.log if x[0] == "open"]) == 1)
e3 = Emu(instsize=0x480); e3.call(CNINIT, ebp=0, esi=0, edi=0); nn = e3.ansi(b"Noname", ref=-1); e3.call(CNCREATE, eax=5, edx=nn)
check("settings storage not installed: generator simply on", [x[2] for x in e3.log if x[0] == "asg"][0] in LISTS["Random"])

# ---- 3. cn_setrace (jmp from TCity.SetRace: eax city, dl race) ----------------------------------------------------------
only_human = sorted(LISTS["Human"] - LISTS["Elf"] - LISTS["Random"])[0]
a_random = sorted(LISTS["Random"])[5]
def setrace(em, name, race, new, expect_cat):
    c = em.city(name, race); em.log.clear()
    em.call(CNSETRACE, eax=c, edx=0xAABBCC00 | (new & 0xFF))
    sn = [x for x in em.log if x[0] == "setname"]; back, = [x for x in em.log if x[0] == "back"]
    good = back[1:] == (c, new & 0xFF, c, int(new == race), 0x11111111, 0x77777777)
    if expect_cat is None: return good and not sn
    return good and len(sn) == 1 and sn[0][1] == c and sn[0][2] in LISTS[expect_cat]
check("race change, name 'Noname' (random -> Dwarf): Dwarf name, then the original routine", setrace(e, b"Noname", -1, 6, "Dwarf"))
check("race change, name from the Random list (random -> Orc): Orc name", setrace(e, a_random, -1, 9, "Orc"))
check("race change, name from the Human list on a Human city -> Undead name", setrace(e, only_human, 0, 11, "Undead"))
check("race change back to random (-1): Random name", setrace(e, only_human, 0, -1, "Random"))
check("race change to another random kind (-3): Random name", setrace(e, b"noname", 4, -3, "Random"))
check("mapmaker's own name: untouched", setrace(e, b"Codyville", -1, 6, None))
check("a Human-list name on an ELF city counts as the mapmaker's: untouched", setrace(e, only_human, 4, 6, None))
check("same race again: no rename, ZF set for the routine's own early exit", setrace(e, b"Noname", 6, 6, None))
check("empty name pointer: treated as nameless", setrace(e, None, -1, 2, "Lizardman"))
e3 = Emu(mapflags=1); e3.call(CNINIT, ebp=0, esi=0, edi=0)
check("generator off: race change never renames", setrace(e3, b"Noname", -1, 6, None))
allcats = True
for i, cat in enumerate(CN.CATS[:12]):
    allcats &= setrace(e, b"Noname", -1, i, cat)
check("every race index 0..11 picks from its own category", allcats)

# ---- 3b. cn_racecb (the dialog's race combo: in place of `call [ecx+0x244]`; ebx = form, eax = city, dl = race) -----------
check("cninit: race combo call site -> call cn_racecb / nop", e.mu.mem_read(CN.SITE_RACECB, 1)[0] == 0xE8 and
      CN.SITE_RACECB + 5 + struct.unpack("<i", e.mu.mem_read(CN.SITE_RACECB + 1, 4))[0] == CNRACECB and e.mu.mem_read(CN.SITE_RACECB + 5, 1)[0] == 0x90)
def racecb(em, objname, edittext, race, new):
    c = em.city(objname, race); form = em.alloc(0x300); edit = em.alloc(0x20); em.w32(form + CN.F_NAMEEDIT, edit)
    em.edit_text[edit] = edittext; em.log.clear()
    em.call(CNRACECB, eax=c, edx=0x55667700 | (new & 0xFF), ecx=EPACK + CN.CITY_VMT_RVA, ebx=form)
    nm = em.cstr(em.r32(c + CN.CITY_NAME)) if em.r32(c + CN.CITY_NAME) else b""
    return nm, em.edit_text[edit], struct.unpack("b", em.mu.mem_read(c + CN.CITY_RACE, 1))[0], [x for x in em.log if x[0] == "settext"]
nm, ed, rc, st_ = racecb(e, a_random, a_random, -1, 6)
check("dialog race combo: random-list name -> Dwarf name in the city AND in the name box", nm in LISTS["Dwarf"] and ed == nm and rc == 6 and len(st_) == 1)
nm, ed, rc, st_ = racecb(e, a_random, b"Codyville", -1, 6)
check("  a name just typed in the box is the mapmaker's: kept, race still changes", nm == b"Codyville" and ed == b"Codyville" and rc == 6 and not st_)
nm, ed, rc, st_ = racecb(e, a_random, a_random, -1, -1)
check("  same race picked again: nothing changes", nm == a_random and ed == a_random and not st_)
nm2, ed2, rc2, st2 = racecb(e, b"Noname", b"Noname", -1, 4)
check("  'Noname' -> Elf name, shown in the box", nm2 in LISTS["Elf"] and ed2 == nm2 and rc2 == 4)
e3 = Emu(mapflags=1); e3.call(CNINIT, ebp=0, esi=0, edi=0)
nm, ed, rc, st_ = racecb(e3, a_random, a_random, -1, 6)
check("  generator off: race changes, name and box untouched", nm == a_random and ed == a_random and rc == 6 and not st_)

# ---- 4. cn_update (button OnClick: eax = form, edx = sender) --------------------------------------------------------------
def world(em):
    cs = [em.city(b"Noname", 2), em.city(b"noname", -1), em.city(b"Keepme", 5), em.city(b"NONAME", 7), em.city(None, 10),
          em.city(b"Noname", 3, vmt=0x12340000)]
    def tlist(items):
        arr = em.alloc(4 * len(items) + 4)
        for i, o in enumerate(items): em.w32(arr + 4 * i, o)
        l = em.alloc(0x10); em.w32(l + 4, arr); em.w32(l + 8, len(items)); return l
    def holder(items):
        h = em.alloc(0x10); em.w32(h + 8, tlist(items)); return h
    def player(structs):
        p = em.alloc(0x40); em.w32(p + CN.PLAYER_STRUCTS, holder(structs)); return p
    noplayerlist = em.alloc(0x40)                                  # a player without a structure list
    pl = holder([player([cs[0], 0, cs[2]]), 0, noplayerlist, player([cs[1], cs[3], cs[4], cs[5]])])
    em.w32(em.map + CN.MAP_PLAYERS, pl)
    return cs
cs = world(e); e.log.clear(); e.call(CNUPDATE, eax=0x600D, edx=0x5E4D)
mb = [x for x in e.log if x[0] == "mbox"]; sn = {x[1]: x[2] for x in e.log if x[0] == "setname"}
check("Update Nameless: asks %r, Yes/No + question icon" % (mb[0][2:4],), mb == [("mbox", 0x5151, CN.ASK.encode(), CN.BTN.encode(), 0x24)])
check("  Yes: the 4 nameless cities renamed by race, the named one and the non-city untouched",
      set(sn) == {cs[0], cs[1], cs[3], cs[4]} and sn[cs[0]] in LISTS["Lizardman"] and sn[cs[1]] in LISTS["Random"] and sn[cs[3]] in LISTS["Highman"] and sn[cs[4]] in LISTS["Goblin"])
e3 = Emu(mbox=7); e3.call(CNINIT, ebp=0, esi=0, edi=0); world(e3); e3.log.clear(); e3.call(CNUPDATE, eax=1, edx=2)
check("  No: nothing renamed", not [x for x in e3.log if x[0] == "setname"])
e3 = Emu(mapflags=1); e3.call(CNINIT, ebp=0, esi=0, edi=0); cs3 = world(e3); e3.call(CNUPDATE, eax=1, edx=2)
check("  works with the generator tick off too (explicit request)", len([x for x in e3.log if x[0] == "setname"]) == 4)

# ---- 5. the tab ----------------------------------------------------------------------------------------------------------
def ui(em):
    st = {"created": [], "parent": {}, "bounds": {}, "text": {}, "items": {}, "checked": {}, "index": {}, "fc": 0, "apply": 0}
    form = em.alloc(0x300); pagectl = em.alloc(0x40); em.w32(form + BL.F_PAGECTL, pagectl); st["form"], st["pagectl"] = form, pagectl
    ivmt = em.alloc(0x100)
    em.w32(ivmt + BL.V_SETPARENT, em.stub(lambda e_: st["parent"].__setitem__(e_.r("eax"), e_.r("edx"))))
    em.w32(ivmt + BL.V_SETBOUNDS, em.stub(lambda e_: st["bounds"].__setitem__(e_.r("eax"), (e_.r("edx"), e_.r("ecx"), e_.arg(1), e_.arg(0))), pop=8))
    svmt = em.alloc(0x100)
    em.w32(svmt + BL.V_ADD, em.stub(lambda e_: st["items"][e_.r("eax")].append(e_.cstr(e_.r("edx")))))
    def mk(kind, iat):
        cvmt = em.alloc(0x100)
        def ctor(e_):
            assert e_.r("eax") == cvmt and (e_.r("edx") & 0xFF) == 1 and e_.r("ecx") == form
            o = em.alloc(0x200); em.w32(o, ivmt); st["created"].append((kind, o))
            if kind in ("combo", "box"):
                items = em.alloc(0x10); em.w32(items, svmt); em.w32(o + BL.LB_ITEMS, items); st["items"][items] = []; st.setdefault("itemsof", {})[o] = items
            return o
        em.w32(cvmt + BL.V_CREATE, em.stub(ctor)); em.w32(iat, cvmt)
    mk("sheet", BL.IAT_TABSHEET); mk("label", BL.IAT_LABEL); mk("box", BL.IAT_CHECKLB)
    mk("check", CN.IAT_CHECKBOX); mk("combo", CN.IAT_COMBO); mk("button", CN.IAT_BUTTON)
    em.jmp_at(BL.T_SETTEXT, em.stub(lambda e_: st["text"].__setitem__(e_.r("eax"), e_.cstr(e_.r("edx")))))
    em.jmp_at(CN.T_SETCHECKED, em.stub(lambda e_: st["checked"].__setitem__(e_.r("eax"), e_.r("edx") & 0xFF)))
    em.jmp_at(CN.T_GETCHECKED, em.stub(lambda e_: st["checked"].get(e_.r("eax"), 0)))
    em.jmp_at(CN.T_SETITEMINDEX, em.stub(lambda e_: st["index"].__setitem__(e_.r("eax"), e_.r("edx"))))
    em.jmp_at(CN.T_GETITEMINDEX, em.stub(lambda e_: st["index"].get(e_.r("eax"), 0xFFFFFFFF)))
    em.jmp_at(BL.FORMCREATE, em.stub(lambda e_: st.__setitem__("fc", st["fc"] + 1)))
    em.jmp_at(BL.APPLY, em.stub(lambda e_: st.__setitem__("apply", st["apply"] + 1)))
    hsset = em.alloc(0x100); cell = em.alloc(4); em.w32(cell, hsset); em.w32(BL.IAT_HSSET, cell)
    return st

for flags, want_chk, want_ix in ((0, 1, 0), (1, 0, 0), (0x0500, 1, 0)):
    e = Emu(mapflags=flags); e.call(CNINIT, ebp=0, esi=0, edi=0); st = ui(e); e.log.clear()
    e.call(FCWRAP, eax=st["form"])
    kinds = [k for k, _o in st["created"]]
    good = kinds == ["sheet", "check", "label", "combo", "button"] and st["fc"] == 1
    if good:
        sheet, chk, lbl, combo, btn = [o for _k, o in st["created"]]
        good = (st["text"].get(sheet) == CN.TAB.encode() and ("spc", sheet, st["pagectl"]) in e.log
                and all(st["parent"].get(o) == sheet for o in (chk, lbl, combo, btn))
                and st["text"].get(chk) == CN.CHK.encode() and st["text"].get(lbl) == CN.LBL.encode() and st["text"].get(btn) == CN.BTN.encode()
                and st["bounds"].get(chk) == (12, 12, 300, 17) and st["bounds"].get(combo) == (12, 66, 210, 21) and st["bounds"].get(btn) == (12, 104, 130, 25)
                and st["bounds"].get(lbl)[:2] == (12, 48)
                and st["checked"].get(chk) == want_chk and ("style", combo, 2) in e.log
                and st["items"][st["itemsof"][combo]] == [n.encode() for n in CN.LISTS] and st["index"].get(combo) == want_ix
                and e.r32(btn + CN.ON_CLICK) == CNUPDATE and e.r32(btn + CN.ON_CLICK + 4) == st["form"])
    check("tab for map settings %#x: sheet, tick=%d, label, drop-down list [%s] index %d, button" % (flags, want_chk, ", ".join(CN.LISTS), want_ix), good)
    if not good:
        print("   ", kinds, st["text"], st["bounds"], st["checked"], st["index"], e.log[:6]); continue
    e.call(OKHOOK, eax=st["form"])
    check("  OK with nothing changed: settings %#x kept (list index clamped)" % flags, e.r32(e.map + CN.MAP_SET) == (flags & 1) and st["apply"] == 1)
    st["checked"][chk] = 0; e.call(OKHOOK, eax=st["form"])
    check("  untick + OK: generator off bit set", e.r32(e.map + CN.MAP_SET) == 1)
    st["checked"][chk] = 1; e.call(OKHOOK, eax=st["form"])
    check("  tick + OK: back to 0 (nothing written to the file)", e.r32(e.map + CN.MAP_SET) == 0)
e = Emu(instsize=0x480); e.call(CNINIT, ebp=0, esi=0, edi=0); st = ui(e); e.call(FCWRAP, eax=st["form"])
check("settings storage not installed: no tab, OK only applies", not st["created"] and st["fc"] == 1)
e.call(OKHOOK, eax=st["form"]); ok &= st["apply"] == 1
print("ALL OK" if ok else "FAILURES")
sys.exit(0 if ok else 1)
