#!/usr/bin/env python3
r"""Unicorn test of the AoWxShot.dll Ban List module (aowxshot_banlist.py): baninit (in-memory patches + refusal),
the FormCreate wrapper (tab / labels / check lists created, lists filled sorted, ticks from the ban buffer) and the
OK hook (ticks written back).  Every engine / VCL / Win32 call is a Python stub that also checks the stack discipline.

    py -3.10 test_aowxshot_banlist_emu.py
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

GD = os.path.dirname(HERE)
img, info = SHOT.build(GD)
pe = pefile.PE(data=img)
B = SHOT.BASE
mem = pe.get_memory_mapped_image()
imps = {s.name.decode(): s.address for d in pe.DIRECTORY_ENTRY_IMPORT for s in d.imports}
D, _fp = SHOT.build_data(B + SHOT.SEC_RVA, GD)
G = D.sym


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


BANINIT, FCWRAP, OKHOOK = labels(["baninit", "bl_fcwrap", "bl_ok"])
STUB, EXE, EPACK, VCL, HEAP = 0x90000000, 0x400000, 0x55700000, 0x41300000, 0x100000
REG = {"eax": UC_X86_REG_EAX, "edx": UC_X86_REG_EDX, "ecx": UC_X86_REG_ECX, "ebx": UC_X86_REG_EBX, "edi": UC_X86_REG_EDI,
       "esi": UC_X86_REG_ESI, "ebp": UC_X86_REG_EBP, "esp": UC_X86_REG_ESP}


class Emu(object):
    def __init__(self):
        mu = self.mu = Uc(UC_ARCH_X86, UC_MODE_32)
        mu.mem_map(B, (len(mem) + 0xFFF) & ~0xFFF); mu.mem_write(B, bytes(mem))
        mu.mem_map(HEAP, 0x100000)                       # objects + stack
        mu.mem_map(0xDEAD0000, 0x1000)
        mu.mem_map(STUB, 0x1000)
        mu.mem_map(EXE, 0x40000)
        mu.mem_map(EPACK + 0x4E000, 0x1000); mu.mem_map(EPACK + 0x1BA000, 0x1000)
        mu.mem_map(EPACK + 0xE000, 0x1000); mu.mem_write(EPACK + 0xE858, struct.pack("<I", 0x480))   # no Map Level Vision storage -> lv_build stays inert (its own test: test_aowxshot_levelvision_emu.py)
        mu.mem_map(VCL + 0x66000, 0x1000)
        self.handlers, self.log, self.heap = [], [], HEAP + 0x1000
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

    def ansi(self, text):
        a = self.alloc(len(text) + 9); self.mu.mem_write(a, struct.pack("<ii", -1, len(text)) + text + b"\0"); return a + 8

    def stub(self, fn, pop=0):
        """fn(emu) -> eax or None; `pop` = bytes of stack arguments the callee removes"""
        self.handlers.append((fn, pop)); return STUB + 16 * (len(self.handlers) - 1)

    def _hook(self, mu, addr, size, user):
        fn, pop = self.handlers[(addr - STUB) // 16]
        saved = tuple(self.r(n) for n in ("ebx", "esi", "edi", "ebp"))
        res = fn(self)
        assert saved == tuple(self.r(n) for n in ("ebx", "esi", "edi", "ebp"))
        sp = self.r("esp"); ret = self.r32(sp)
        mu.reg_write(UC_X86_REG_ESP, sp + 4 + pop)
        if res is not None: mu.reg_write(UC_X86_REG_EAX, res & 0xFFFFFFFF)
        mu.reg_write(UC_X86_REG_EDX, 0xBAD0EDD0); mu.reg_write(UC_X86_REG_ECX, 0xBAD0ECC0)   # volatile registers die
        mu.reg_write(UC_X86_REG_EIP, ret)

    def jmp_at(self, va, target):
        self.mu.mem_write(va, b"\xe9" + struct.pack("<I", (target - (va + 5)) & 0xFFFFFFFF))

    def call(self, fn, **regs):
        sp = HEAP + 0xF8000
        self.w32(sp, 0xDEAD0000)
        self.mu.reg_write(UC_X86_REG_ESP, sp); self.mu.reg_write(UC_X86_REG_EBP, 0x77777777)
        keep = {"ebx": 0x11111111, "esi": 0x22222222, "edi": 0x33333333}
        keep.update(regs)
        for k, v in keep.items(): self.mu.reg_write(REG[k], v)
        self.mu.emu_start(fn, 0xDEAD0000, count=20000000)
        assert self.r("esp") == sp + 4, "stack imbalance %#x" % (self.r("esp") - sp - 4)
        return keep


def setup(e, with_storage=True, n_spells=40):
    """fake editor: dialog form, classes, registries.  Returns a dict of what was built."""
    st = {"created": [], "parent": {}, "bounds": {}, "text": {}, "items": {}, "checked": {}, "fc": 0, "apply": 0, "pagectl": {}}
    form = e.alloc(0x300); pagectl = e.alloc(0x40); e.w32(form + BL.F_PAGECTL, pagectl)
    st["form"], st["pagectl_obj"] = form, pagectl
    # instance vmt shared by every runtime control: SetParent / SetBounds
    ivmt = e.alloc(0x100)
    e.w32(ivmt + BL.V_SETPARENT, e.stub(lambda e: st["parent"].__setitem__(e.r("eax"), e.r("edx"))))
    e.w32(ivmt + BL.V_SETBOUNDS, e.stub(lambda e: st["bounds"].__setitem__(e.r("eax"), (e.r("edx"), e.r("ecx"), e.arg(1), e.arg(0))), pop=8))   # Delphi register: AWidth pushed first, AHeight last
    svmt = e.alloc(0x100)                                    # TStrings of a list box: Add
    def s_add(e):
        lst = st["items"][e.r("eax")]; lst.append(e.cstr(e.r("edx"))); return len(lst) - 1
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
    # the exe sites baninit patches
    e.w32(BL.MT_FORMCREATE, BL.FORMCREATE)
    e.mu.mem_write(BL.OK_SITE, b"\xe8" + struct.pack("<I", BL.OK_SITE_REL))
    # VCL30 SetPageControl (bytes checked, then executed -> jump straight to a stub is impossible: keep the 8 bytes
    # and continue with a jmp)
    spc = VCL + BL.SPC_RVA
    e.mu.mem_write(spc, struct.pack("<II", BL.SPC_B0, BL.SPC_B1))
    st["spc_stub"] = e.stub(lambda e: st["pagectl"].__setitem__(e.r("eax"), e.r("edx")))
    # modules
    def gmh(e):
        name = e.cstr(e.arg(0)).lower()
        return {b"aowepack.dll": EPACK, b"vcl30.dpl": VCL}.get(name, 0)
    e.w32(imps["GetModuleHandleA"], e.stub(gmh, pop=4))
    e.w32(imps["VirtualProtect"], e.stub(lambda e: 1, pop=16))
    def cmpi(e):
        a, b = e.cstr(e.arg(0)).lower(), e.cstr(e.arg(1)).lower()
        return (a > b) - (a < b)
    e.w32(imps["lstrcmpiA"], e.stub(cmpi, pop=8))
    # storage
    buf = e.alloc(96); st["buf"] = buf
    if with_storage:
        e.jmp_at(EPACK + BL.BANGET_RVA, e.stub(lambda e: buf))
    # registries
    hsset = e.alloc(0x100); cell = e.alloc(4); e.w32(cell, hsset); e.w32(BL.IAT_HSSET, cell)
    def mk_ctl(objs):
        arr = e.alloc(4 * len(objs) + 4)
        for i, o in enumerate(objs): e.w32(arr + 4 * i, o)
        lst = e.alloc(0x10); e.w32(lst + 4, arr); e.w32(lst + 8, len(objs))
        ctl = e.alloc(0x10); e.w32(ctl + 8, lst); return ctl
    base_cost_vmt = e.alloc(0x100); e.w32(base_cost_vmt + BL.V_EXPANDCOST, EPACK + BL.EXPANDCOST_RVA)
    own_cost_vmt = e.alloc(0x100); e.w32(own_cost_vmt + BL.V_EXPANDCOST, 0x55555555)
    def obj(name, cost=0, vmt=base_cost_vmt):
        o = e.alloc(0x30); e.w32(o, vmt)
        e.w32(o + 8, e.ansi(name) if name is not None else 0); e.w32(o + 0x14, cost); return o
    import random
    rnd = random.Random(7)
    spells, st["spell_names"] = [], {}
    for i in range(n_spells):
        if i % 9 == 4: spells.append(0); continue                       # hole in the registry
        if i % 11 == 6: spells.append(obj(None)); continue                # no name
        if i % 13 == 8: spells.append(obj(b"")); continue                 # empty name
        nm = bytes(rnd.choice(b"abcdefgHIJKLmnop") for _ in range(rnd.randint(3, 9))) + b" %d" % i
        spells.append(obj(nm)); st["spell_names"][i] = nm
    e.w32(hsset + BL.SET_SPELLS, mk_ctl(spells))
    abil_spec = [(b"Zeal", 3, base_cost_vmt), (b"Walking", 0, base_cost_vmt), None, (b"archery", 2, base_cost_vmt),
                 (b"Spell Casting", 0, own_cost_vmt), (b"", 5, base_cost_vmt), (b"Bard's Skills", 1, base_cost_vmt),
                 (b"Fire Weakness", 0, base_cost_vmt), (b"Marksmanship", 4, base_cost_vmt)]
    abils, st["abil_names"] = [], {}
    for i, a in enumerate(abil_spec):
        if a is None: abils.append(0); continue
        abils.append(obj(a[0], a[1], a[2]))
        if a[0] and (a[1] or a[2] == own_cost_vmt): st["abil_names"][i] = a[0]
    e.w32(hsset + BL.SET_ABILS, mk_ctl(abils))
    return st


def spc_trampoline(e, st):
    # SetPageControl is entered at its real address; after the 8 verified bytes put a jmp to the stub.  The 8 bytes are
    # push ebx / push esi / mov esi,edx / mov ebx,eax / mov eax,[ebx+...]: undo the two pushes first.
    spc = VCL + BL.SPC_RVA
    code = b"\x53\x56\x8b\xf2\x8b\xd8\x8b\x83\x18\x01\x00\x00" + b"\x8b\xc3" + b"\x8b\xd6" + b"\x5e\x5b"   # real head, then mov eax,ebx / mov edx,esi / pop esi / pop ebx
    e.mu.mem_write(spc, code + b"\xe9" + struct.pack("<I", (st["spc_stub"] - (spc + len(code) + 5)) & 0xFFFFFFFF))
    assert struct.unpack("<II", code[:8]) == (BL.SPC_B0, BL.SPC_B1)


ok = True
def check(name, cond):
    global ok
    print("%-58s %s" % (name, "ok" if cond else "FAIL")); ok &= bool(cond)


# ---- 1. baninit ------------------------------------------------------------------------------------------------------
e = Emu(); st = setup(e)
e.call(BANINIT, ebp=0)
check("baninit: FormCreate entry -> bl_fcwrap", e.r32(BL.MT_FORMCREATE) == FCWRAP)
rel = struct.unpack("<i", e.mu.mem_read(BL.OK_SITE + 1, 4))[0]
check("baninit: OK call -> bl_ok", e.mu.mem_read(BL.OK_SITE, 1)[0] == 0xE8 and BL.OK_SITE + 5 + rel == OKHOOK)
e2 = Emu(); st2 = setup(e2); e2.w32(BL.MT_FORMCREATE, 0x4E4040)
e2.call(BANINIT, ebp=0)
check("baninit refuses a foreign FormCreate entry", e2.r32(BL.MT_FORMCREATE) == 0x4E4040 and e2.r32(BL.OK_SITE + 1) == BL.OK_SITE_REL)
e2 = Emu(); st2 = setup(e2); e2.mu.mem_write(BL.OK_SITE, b"\xe8\x00\x10\x00\x00")
e2.call(BANINIT, ebp=0)
check("baninit refuses a foreign OK call", e2.r32(BL.MT_FORMCREATE) == BL.FORMCREATE)

# ---- 2. FormCreate wrapper ---------------------------------------------------------------------------------------------
e = Emu(); st = setup(e)
# VCL bytes are checked with the image's SetPageControl still pristine, the trampoline keeps them
spc_trampoline(e, st)
banned_spells = [i for i in st["spell_names"]][::5]
banned_abils = [3, 4]
for i in banned_spells: e.mu.mem_write(st["buf"] + (i >> 3), bytes([e.mu.mem_read(st["buf"] + (i >> 3), 1)[0] | (1 << (i & 7))]))
for i in banned_abils: e.mu.mem_write(st["buf"] + 64 + (i >> 3), bytes([e.mu.mem_read(st["buf"] + 64 + (i >> 3), 1)[0] | (1 << (i & 7))]))
e.call(FCWRAP, eax=st["form"], edx=st["form"])
kinds = [k for k, _o in st["created"]]
check("original FormCreate called once", st["fc"] == 1)
check("controls: sheet, 3 labels, 2 boxes", kinds == ["sheet", "label", "label", "label", "box", "box"])
sheet = st["created"][0][1]
check("sheet joined MainPageControl", st["pagectl"].get(sheet) == st["pagectl_obj"])
check("sheet caption", st["text"].get(sheet) == b"Ban List")
labs = [o for k, o in st["created"] if k == "label"]; boxes = [o for k, o in st["created"] if k == "box"]
check("every control parented to the sheet", all(st["parent"].get(o) == sheet for o in labs + boxes))
check("label texts", [st["text"].get(o) for o in labs] == [b"Spells\r\n(remove from Research)", b"Abilities (remove from\r\ncustomization and level-up)", BL.HINT.encode()])
check("label bounds", [st["bounds"].get(o) for o in labs] == [(BL.COL1, BL.LBL_TOP, 200, 16), (BL.COL2, BL.LBL_TOP, 200, 16), (BL.COL1, BL.HINT_TOP, 434, 16)])
check("box bounds", [st["bounds"].get(o) for o in boxes] == [(BL.COL1, BL.BOX_TOP, BL.BOX_W, BL.BOX_H), (BL.COL2, BL.BOX_TOP, BL.BOX_W, BL.BOX_H)])
sp_items = st["items"][st["boxitems"][boxes[0]]]; ab_items = st["items"][st["boxitems"][boxes[1]]]
exp_sp = sorted(st["spell_names"].items(), key=lambda kv: kv[1].lower())
check("spell list = named spells, sorted", sp_items == [n for _i, n in exp_sp])
exp_ab = sorted(st["abil_names"].items(), key=lambda kv: kv[1].lower())
check("ability list = buyable abilities, sorted", ab_items == [n for _i, n in exp_ab])
print("   abilities:", ab_items)
sid = struct.unpack("<%dH" % len(exp_sp), e.mu.mem_read(G["g_blsid"], 2 * len(exp_sp)))
aid = struct.unpack("<%dH" % len(exp_ab), e.mu.mem_read(G["g_blaid"], 2 * len(exp_ab)))
check("index -> id tables", list(sid) == [i for i, _n in exp_sp] and list(aid) == [i for i, _n in exp_ab])
check("ticks = ban bits (spells)", [k for k, v in sorted(st["checked"][boxes[0]].items()) if v] == [k for k, (i, _n) in enumerate(exp_sp) if i in banned_spells]
      and len(st["checked"][boxes[0]]) == len(exp_sp))
check("ticks = ban bits (abilities)", [k for k, v in sorted(st["checked"][boxes[1]].items()) if v] == [k for k, (i, _n) in enumerate(exp_ab) if i in banned_abils])

# ---- 3. OK hook ---------------------------------------------------------------------------------------------------------
new_sp = [0, 3, len(exp_sp) - 1]; new_ab = [1]
st["checked"][boxes[0]] = {k: 1 for k in new_sp}; st["checked"][boxes[1]] = {k: 1 for k in new_ab}
e.mu.mem_write(st["buf"], b"\xff" * 96)                                        # stale bits everywhere
e.call(OKHOOK, eax=st["form"])
buf = bytes(e.mu.mem_read(st["buf"], 96))
want = bytearray(96)
for k in new_sp: i = exp_sp[k][0]; want[i >> 3] |= 1 << (i & 7)
for k in new_ab: i = exp_ab[k][0]; want[64 + (i >> 3)] |= 1 << (i & 7)
check("OK: original apply called once", st["apply"] == 1)
check("OK: buffer = exactly the ticked ids", buf == bytes(want))

# ---- 4. no storage patch -> no tab, OK leaves everything alone ----------------------------------------------------------------
e = Emu(); st = setup(e, with_storage=False); spc_trampoline(e, st)
e.call(FCWRAP, eax=st["form"], edx=st["form"])
check("no BAN_GET: FormCreate still runs, no control created", st["fc"] == 1 and not st["created"])
e.call(OKHOOK, eax=st["form"])
check("no BAN_GET: OK only applies", st["apply"] == 1)

# ---- 5. a later dialog after one without map data: statics reset -------------------------------------------------------------
e = Emu(); st = setup(e, n_spells=600); spc_trampoline(e, st)
e.call(FCWRAP, eax=st["form"], edx=st["form"])
boxes = [o for k, o in st["created"] if k == "box"]
n = len(st["items"][st["boxitems"][boxes[0]]])
check("600 registry entries: capped at ids < 512 (%d listed)" % n, n == len([i for i in st["spell_names"] if i < 512]))
print("ALL OK" if ok else "FAILURES")
sys.exit(0 if ok else 1)
