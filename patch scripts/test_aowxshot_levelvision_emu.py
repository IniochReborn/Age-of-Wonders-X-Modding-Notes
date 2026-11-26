#!/usr/bin/env python3
r"""Unicorn test of the AoWxShot.dll Map Level Vision module (aowxshot_levelvision.py): lv_build (tab, list of the map's
levels in display order, ticks from the stored mask) and lv_store (ticks -> mask), through the real Ban List wrappers
bl_fcwrap / bl_ok.  The level-name function is the real code + table from the project's AoWEPACK.dll.

    py -3.10 test_aowxshot_levelvision_emu.py
"""
import os, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import (UC_X86_REG_ESP, UC_X86_REG_EAX, UC_X86_REG_EDX, UC_X86_REG_ECX, UC_X86_REG_EBP,
                               UC_X86_REG_EBX, UC_X86_REG_EDI, UC_X86_REG_ESI, UC_X86_REG_EIP)
import build_aowxshot as SHOT
import aowxshot_banlist as BL
import aowxshot_levelvision as LV

GD = os.path.dirname(HERE)
img, info = SHOT.build(GD)
pe = pefile.PE(data=img)
B = SHOT.BASE
mem = pe.get_memory_mapped_image()
imps = {s.name.decode(): s.address for d in pe.DIRECTORY_ENTRY_IMPORT for s in d.imports}
D, _fp = SHOT.build_data(B + SHOT.SEC_RVA, GD)
G = D.sym
EPDLL = open(os.path.join(GD, "AoWEPACK.dll"), "rb").read()


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


FCWRAP, OKHOOK = labels(["bl_fcwrap", "bl_ok"])
STUB, EXE, EPACK, VCL, HEAP = 0x90000000, 0x400000, 0x55700000, 0x41300000, 0x100000
REG = {"eax": UC_X86_REG_EAX, "edx": UC_X86_REG_EDX, "ecx": UC_X86_REG_ECX, "ebx": UC_X86_REG_EBX, "edi": UC_X86_REG_EDI,
       "esi": UC_X86_REG_ESI, "ebp": UC_X86_REG_EBP, "esp": UC_X86_REG_ESP}
NAMES = ["Surface", "Caverns", "Depths", "Firmament", "Abyss"] + ["Abyss " + r for r in
         "II III IV V VI VII VIII IX X XI XII XIII XIV XV XVI XVII XVIII XIX XX XXI XXII XXIII XXIV XXV".split()]


class Emu(object):
    def __init__(self):
        mu = self.mu = Uc(UC_ARCH_X86, UC_MODE_32)
        mu.mem_map(B, (len(mem) + 0xFFF) & ~0xFFF); mu.mem_write(B, bytes(mem))
        mu.mem_map(HEAP, 0x100000); mu.mem_map(0xDEAD0000, 0x1000); mu.mem_map(STUB, 0x1000); mu.mem_map(EXE, 0x40000)
        mu.mem_map(EPACK + 0x4E000, 0x1000); mu.mem_map(EPACK + 0x1BA000, 0x1000); mu.mem_map(EPACK + 0xE000, 0x1000)
        mu.mem_map(EPACK + 0x151000, 0x1000)
        mu.mem_map(EPACK + 0x13000, 0x1000); mu.mem_map(EPACK + 0x8D000, 0x1000); mu.mem_map(EPACK + 0x78000, 0x1000)
        mu.mem_write(EPACK + 0x151000, EPDLL[0x151000 - 0xC00:0x152000 - 0xC00])         # real NAMEFN + its name table
        mu.mem_map(VCL + 0x66000, 0x1000)
        self.handlers, self.heap, self.redirect = [], HEAP + 0x1000, {}
        mu.hook_add(UC_HOOK_CODE, self._redir, begin=EPACK, end=EPACK + 0x100000)
        mu.hook_add(UC_HOOK_CODE, self._hook, begin=STUB, end=STUB + 0xFFF)

    def r(self, n): return self.mu.reg_read(REG[n])
    def w32(self, a, v): self.mu.mem_write(a, struct.pack("<I", v & 0xFFFFFFFF))
    def r32(self, a): return struct.unpack("<I", self.mu.mem_read(a, 4))[0]
    def arg(self, i): return self.r32(self.r("esp") + 4 + 4 * i)

    def cstr(self, a):
        out = bytearray()
        while True:
            c = self.mu.mem_read(a, 1)[0]
            if not c: return bytes(out)
            out.append(c); a += 1

    def alloc(self, n):
        a = self.heap; self.heap += (n + 15) & ~15; return a

    def stub(self, fn, pop=0):
        self.handlers.append((fn, pop)); return STUB + 16 * (len(self.handlers) - 1)

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
        if addr in self.redirect: mu.reg_write(UC_X86_REG_EIP, self.redirect[addr])

    def jmp_at(self, va, target):
        self.mu.mem_write(va, b"\xe9" + struct.pack("<I", (target - (va + 5)) & 0xFFFFFFFF))

    def arm_refresh(self, st):
        for rva in (LV.ARMY_UPDATE_RVA, LV.UPDVIS_RVA):
            # `push ebx` + the 3 other verified bytes would run: replace what follows the dword check by entering the stub
            # directly - the stub address is hooked, so write head (4 B) and let a code hook redirect the entry
            self.redirect[EPACK + rva] = st["rf%x" % rva]

    def call(self, fn, **regs):
        sp = HEAP + 0xF8000
        self.w32(sp, 0xDEAD0000)
        self.mu.reg_write(UC_X86_REG_ESP, sp); self.mu.reg_write(UC_X86_REG_EBP, 0x77777777)
        keep = {"ebx": 0x11111111, "esi": 0x22222222, "edi": 0x33333333}
        keep.update(regs)
        for k, v in keep.items(): self.mu.reg_write(REG[k], v)
        self.mu.emu_start(fn, 0xDEAD0000, count=20000000)
        assert self.r("esp") == sp + 4, "stack imbalance %#x" % (self.r("esp") - sp - 4)
        for k in ("ebx", "esi", "edi"): assert self.r(k) == keep[k], k
        assert self.r("ebp") == 0x77777777


def setup(e, levels=5, hidden=0, mask=0, instsize=0x488, havemap=True):
    st = {"created": [], "parent": {}, "bounds": {}, "text": {}, "items": {}, "checked": {}, "fc": 0, "apply": 0, "pagectl": {}}
    form = e.alloc(0x300); pagectl = e.alloc(0x40); e.w32(form + BL.F_PAGECTL, pagectl)
    st["form"], st["pagectl_obj"] = form, pagectl
    ivmt = e.alloc(0x100)
    e.w32(ivmt + BL.V_SETPARENT, e.stub(lambda e: st["parent"].__setitem__(e.r("eax"), e.r("edx"))))
    e.w32(ivmt + BL.V_SETBOUNDS, e.stub(lambda e: st["bounds"].__setitem__(e.r("eax"), (e.r("edx"), e.r("ecx"), e.arg(1), e.arg(0))), pop=8))
    svmt = e.alloc(0x100)
    def s_add(e):
        lst = st["items"][e.r("eax")]; lst.append(e.cstr(e.r("edx")))
        assert e.r32(e.r("edx") - 4) == len(lst[-1])                     # a real AnsiString (length prefix)
        return len(lst) - 1
    e.w32(svmt + BL.V_ADD, e.stub(s_add))

    def mk_class(kind, iat):
        cvmt = e.alloc(0x100)
        def ctor(e):
            assert e.r("eax") == cvmt and (e.r("edx") & 0xFF) == 1 and e.r("ecx") == form
            o = e.alloc(0x200); e.w32(o, ivmt); st["created"].append((kind, o))
            if kind == "box":
                items = e.alloc(0x10); e.w32(items, svmt); e.w32(o + BL.LB_ITEMS, items); st["items"][items] = []; st["checked"][o] = {}
                st.setdefault("boxitems", {})[o] = items
            return o
        e.w32(cvmt + BL.V_CREATE, e.stub(ctor)); e.w32(iat, cvmt)
    mk_class("sheet", BL.IAT_TABSHEET); mk_class("label", BL.IAT_LABEL); mk_class("box", BL.IAT_CHECKLB)
    e.w32(BL.IAT_SETCHECKED, e.stub(lambda e: st["checked"][e.r("eax")].__setitem__(e.r("edx"), e.r("ecx") & 0xFF)))
    e.w32(BL.IAT_GETCHECKED, e.stub(lambda e: st["checked"][e.r("eax")].get(e.r("edx"), 0)))
    e.jmp_at(BL.T_SETTEXT, e.stub(lambda e: st["text"].__setitem__(e.r("eax"), e.cstr(e.r("edx")))))
    e.jmp_at(BL.FORMCREATE, e.stub(lambda e: st.__setitem__("fc", st["fc"] + (e.r("eax") == form))))
    e.jmp_at(BL.APPLY, e.stub(lambda e: st.__setitem__("apply", st["apply"] + (e.r("eax") == form))))
    spc = VCL + BL.SPC_RVA
    st["spc_stub"] = e.stub(lambda e: st["pagectl"].__setitem__(e.r("eax"), e.r("edx")))
    code = b"\x53\x56\x8b\xf2\x8b\xd8\x8b\x83\x18\x01\x00\x00" + b"\x8b\xc3" + b"\x8b\xd6" + b"\x5e\x5b"
    e.mu.mem_write(spc, code + b"\xe9" + struct.pack("<I", (st["spc_stub"] - (spc + len(code) + 5)) & 0xFFFFFFFF))
    e.w32(imps["GetModuleHandleA"], e.stub(lambda e: {b"aowepack.dll": EPACK, b"vcl30.dpl": VCL}.get(e.cstr(e.arg(0)).lower(), 0), pop=4))
    e.w32(EPACK + LV.INSTSIZE_RVA, instsize)
    # BAN_GET stays all-zero: the Ban List tab is not built, only ours
    hsset = e.alloc(0x100); cell = e.alloc(4); e.w32(cell, hsset); e.w32(BL.IAT_HSSET, cell)
    m = e.alloc(0x500); cont = e.alloc(0x40); e.w32(m + LV.MAP_CONT, cont); e.w32(cont + LV.CONT_COUNT, levels)
    e.w32(m + LV.MAP_HIDDEN, hidden); e.w32(m + LV.MAP_VISION, mask)
    mcell = e.alloc(4); e.w32(mcell, m if havemap else 0); e.w32(LV.IAT_HSMAP, mcell)
    st["map"], st["mcell"] = m, mcell
    # refresh targets: real first bytes (verified by the DLL), then a jump to a stub
    st["updated"], st["updvis"] = [], []
    for rva, head, fn in ((LV.ARMY_UPDATE_RVA, bytes.fromhex("538bd883"), lambda e: st["updated"].append(e.r("eax"))),
                          (LV.UPDVIS_RVA, bytes.fromhex("535683c4"), lambda e: st["updvis"].append(e.r("eax")))):
        e.mu.mem_write(EPACK + rva, head)
        st["rf%x" % rva] = e.stub(fn)
    # units: 2 armies (3 + 1 units), one unit without owner, one owned by a non-army object, one nil entry
    armies = [e.alloc(0x40), e.alloc(0x40)]
    for a_ in armies: e.w32(a_, EPACK + LV.ARMY_VMT_RVA)
    other = e.alloc(0x40); e.w32(other, 0x12345678)
    owners = [armies[0], armies[0], 0, armies[1], other, armies[0]]
    arr = e.alloc(4 * (len(owners) + 1))
    for i, o in enumerate(owners):
        u = e.alloc(0x50); e.w32(u + 4, o); e.w32(arr + 4 * i, u)
    e.w32(arr + 4 * len(owners), 0)
    lst = e.alloc(0x10); e.w32(lst + 4, arr); e.w32(lst + 8, len(owners) + 1)
    uc = e.alloc(0x20); e.w32(uc + 0x10, lst); e.w32(m + LV.UNITCTRL, uc)
    st["armies"] = armies
    return st


ok = True
def check(name, cond):
    global ok
    print("%-74s %s" % (name, "ok" if cond else "FAIL")); ok &= bool(cond)


def order(levels, hidden):
    disp = [3, 0, 1, 2] + list(range(4, 29))
    return [L for L in disp if L < levels and not hidden >> L & 1]


def default(L): return L not in (0, 3)


for levels, hidden, mask in ((5, 0, 0), (3, 0, 0), (1, 0, 0), (29, 0, 0), (5, 0b01000, 0), (7, 0b10100, 0b0100011), (29, 0, 0x1FFFFFFF), (5, 0, 0b01001)):
    e = Emu(); st = setup(e, levels, hidden, mask); e.arm_refresh(st)
    e.call(FCWRAP, eax=st["form"])
    kinds = [k for k, _o in st["created"]]
    exp = order(levels, hidden)
    tag = "levels %d hidden %#x mask %#x" % (levels, hidden, mask)
    good = kinds == ["sheet", "label", "label", "box"] and st["fc"] == 1
    if good:
        sheet = st["created"][0][1]; labs = [o for k, o in st["created"] if k == "label"]; box = st["created"][3][1]
        items = st["items"][st["boxitems"][box]]
        good = (st["text"].get(sheet) == LV.TAB.encode() and st["pagectl"].get(sheet) == st["pagectl_obj"]
                and all(st["parent"].get(o) == sheet for o in labs + [box])
                and [st["text"].get(o) for o in labs] == [LV.HEAD.encode(), LV.HINT.encode()]
                and st["bounds"].get(box) == (BL.COL1, LV.LV_BOX_TOP, BL.BOX_W, LV.LV_BOX_H) and st["bounds"].get(labs[0])[:2] == (BL.COL1, LV.LV_LBL_TOP)
                and items == [NAMES[L].encode() for L in exp]
                and [st["checked"][box].get(i, None) for i in range(len(exp))] == [int(default(L) ^ bool(mask >> L & 1)) for L in exp])
    check("build  %s: tab, %d levels in display order, ticks" % (tag, len(exp)), good)
    if not good:
        print("   ", kinds, [st["items"][i] for i in st["items"]], st["checked"]); continue
    # OK with unchanged ticks keeps the mask; then flip some ticks
    e.call(OKHOOK, eax=st["form"])
    check("store  %s: unchanged ticks keep the mask, apply called once, no refresh" % tag, e.r32(st["map"] + LV.MAP_VISION) == mask and st["apply"] == 1 and not st["updated"] and not st["updvis"])
    new = {i: (i * 7 + levels) % 3 == 0 for i in range(len(exp))}
    st["checked"][box] = {i: int(v) for i, v in new.items()}
    e.call(OKHOOK, eax=st["form"])
    want = mask
    for i, L in enumerate(exp):
        want &= ~(1 << L)
        if new[i] != default(L): want |= 1 << L
    check("store  %s: new ticks -> mask %#x (other bits kept)" % (tag, want), e.r32(st["map"] + LV.MAP_VISION) == want)
    if want != mask:
        check("        refresh: TArmy.Update on real armies only, then UpdateVisibility(map)", sorted(set(st["updated"])) == sorted(st["armies"]) and len(st["updated"]) == 4 and st["updvis"] == [st["map"]])
        st["updated"].clear(); st["updvis"].clear()
    if (levels, hidden, mask) == (5, 0, 0):
        st["checked"][box] = {i: int(default(L)) for i, L in enumerate(exp)}
        e.call(OKHOOK, eax=st["form"])
        check("store  default ticks -> mask 0 (nothing written to the file)", e.r32(st["map"] + LV.MAP_VISION) == 0)
        other = e.alloc(0x500); e.w32(other + LV.MAP_VISION, 0x55); e.w32(st["mcell"], other)
        st["checked"][box] = {i: 1 for i in range(len(exp))}
        e.call(OKHOOK, eax=st["form"])
        check("store  map changed since the dialog opened -> nothing written", e.r32(other + LV.MAP_VISION) == 0x55 and e.r32(st["map"] + LV.MAP_VISION) == 0)

e = Emu(); st = setup(e); e.arm_refresh(st); e.mu.mem_write(EPACK + LV.ARMY_UPDATE_RVA, bytes.fromhex("558bec83")); e.call(FCWRAP, eax=st["form"])
box = st["created"][3][1]; st["checked"][box] = {i: 1 for i in range(5)}
e.call(OKHOOK, eax=st["form"])
check("foreign TArmy.Update bytes -> mask stored, nothing called", e.r32(st["map"] + LV.MAP_VISION) == 0b01001 and not st["updated"] and not st["updvis"])
e = Emu(); st = setup(e, instsize=0x480); e.call(FCWRAP, eax=st["form"])
check("storage patch missing (InstanceSize 0x480) -> no tab", st["fc"] == 1 and not st["created"])
e.call(OKHOOK, eax=st["form"]); check("  ... and OK only applies", st["apply"] == 1)
e = Emu(); st = setup(e, havemap=False); e.call(FCWRAP, eax=st["form"])
check("no map -> no tab", st["fc"] == 1 and not st["created"])
e = Emu(); st = setup(e); e.mu.mem_write(EPACK + LV.NAMEFN_RVA, b"\x00"); e.call(FCWRAP, eax=st["form"])
check("level-name function missing -> no tab", not st["created"])
e = Emu(); st = setup(e); e.w32(st["form"] + BL.F_PAGECTL, 0); e.call(FCWRAP, eax=st["form"])
check("no page control -> no tab", not st["created"])
print("ALL OK" if ok else "FAILURES")
sys.exit(0 if ok else 1)
