#!/usr/bin/env python3
r"""Unicorn test of the AoWxShot.dll fog-player module (aowxshot_fogplayer.py): fpinit (in-memory patches + refusal),
fp_fog (seated player follows the Players pick while fog is on) and fp_pick (store + redraw when fog is on).

    py -3.10 test_aowxshot_fogplayer_emu.py
"""
import os, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import (UC_X86_REG_ESP, UC_X86_REG_EAX, UC_X86_REG_EDX, UC_X86_REG_ECX, UC_X86_REG_EBP,
                               UC_X86_REG_EBX, UC_X86_REG_EDI, UC_X86_REG_ESI, UC_X86_REG_EIP)
import build_aowxshot as SHOT
import aowxshot_fogplayer as FP

GD = os.path.dirname(HERE)
img, info = SHOT.build(GD)
pe = pefile.PE(data=img)
B = SHOT.BASE
mem = pe.get_memory_mapped_image()
imps = {s.name.decode(): s.address for d in pe.DIRECTORY_ENTRY_IMPORT for s in d.imports}


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


FPINIT, FPFOG, FPPICK = labels(["fpinit", "fp_fog", "fp_pick"])
STUB, EXE, HEAP, STOP, EPACK = 0x90000000, 0x400000, 0x100000, 0xDEAD0000, 0x55700000
ok = True


def check(name, cond):
    global ok
    print("%-70s %s" % (name, "ok" if cond else "FAIL")); ok &= bool(cond)


class Emu(object):
    def __init__(self):
        mu = self.mu = Uc(UC_ARCH_X86, UC_MODE_32)
        mu.mem_map(B, (len(mem) + 0xFFF) & ~0xFFF); mu.mem_write(B, bytes(mem))
        mu.mem_map(HEAP, 0x100000); mu.mem_map(STOP, 0x1000); mu.mem_map(STUB, 0x1000); mu.mem_map(EXE, 0x40000)
        mu.mem_write(FP.SITE_FOG, FP.FOG_BYTES); mu.mem_write(FP.SITE_PICK, FP.PICK_BYTES)
        self.calls = []
        mu.hook_add(UC_HOOK_CODE, self._hook, begin=STUB, end=STUB + 0xFFF)
        # map object + vmt; VMT+0x100 = SetFogEnabled stub (records, stores [map+0xC8] like the real one)
        self.map = HEAP + 0x1000; self.vmt = HEAP + 0x3000
        mu.mem_write(self.map, struct.pack("<I", self.vmt)); mu.mem_write(self.vmt + FP.V_SETFOG, struct.pack("<I", STUB + 0x10))
        mu.mem_write(imps["VirtualProtect"], struct.pack("<I", STUB + 0x20))
        mu.mem_map(EPACK + 0x76000, 0x1000); mu.mem_write(EPACK + FP.SEATCHG_RVA, struct.pack("<I", FP.SEATCHG_B0))
        mu.mem_write(FP.IAT_HSMAP, struct.pack("<I", EPACK + FP.HSMAP_RVA))
        mu.hook_add(UC_HOOK_CODE, self._seat, begin=EPACK + FP.SEATCHG_RVA, end=EPACK + FP.SEATCHG_RVA)

    def b(self, a): return self.mu.mem_read(a, 1)[0]
    def setb(self, a, v): self.mu.mem_write(a, bytes([v]))

    def _hook(self, mu, addr, size, user):
        sp = mu.reg_read(UC_X86_REG_ESP); ret = struct.unpack("<I", mu.mem_read(sp, 4))[0]
        pop = 0
        if addr == STUB + 0x10:
            m = mu.reg_read(UC_X86_REG_EAX); on = mu.reg_read(UC_X86_REG_EDX) & 0xFF
            self.calls.append(("fog", m, on, self.b(m + FP.MAP_SEATED))); self.setb(m + FP.MAP_FOGON, on)
            mu.reg_write(UC_X86_REG_EAX, 0xBAD0EAA0)
        elif addr == STUB + 0x20:
            self.calls.append(("vp", struct.unpack("<4I", mu.mem_read(sp + 4, 16))[:3])); pop = 16; mu.reg_write(UC_X86_REG_EAX, 1)
        mu.reg_write(UC_X86_REG_EDX, 0xBAD0EDD0); mu.reg_write(UC_X86_REG_ECX, 0xBAD0ECC0)
        mu.reg_write(UC_X86_REG_ESP, sp + 4 + pop); mu.reg_write(UC_X86_REG_EIP, ret)

    def _seat(self, mu, addr, size, user):
        m = mu.reg_read(UC_X86_REG_EAX); self.calls.append(("seatchg", m, self.b(m + FP.MAP_SEATED)))
        sp = mu.reg_read(UC_X86_REG_ESP); ret = struct.unpack("<I", mu.mem_read(sp, 4))[0]
        for r in (UC_X86_REG_EAX, UC_X86_REG_EDX, UC_X86_REG_ECX): mu.reg_write(r, 0xBAD0BAD0)
        mu.reg_write(UC_X86_REG_ESP, sp + 4); mu.reg_write(UC_X86_REG_EIP, ret)

    def call(self, fn, **regs):
        sp = HEAP + 0xF8000
        self.mu.mem_write(sp, struct.pack("<I", STOP))
        keep = {UC_X86_REG_EBX: 0x11111111, UC_X86_REG_ESI: 0x22222222, UC_X86_REG_EDI: 0x33333333, UC_X86_REG_EBP: 0}
        for r, v in keep.items(): self.mu.reg_write(r, v)
        for k, v in regs.items(): self.mu.reg_write({"eax": UC_X86_REG_EAX, "edx": UC_X86_REG_EDX, "ecx": UC_X86_REG_ECX}[k], v)
        self.mu.reg_write(UC_X86_REG_ESP, sp)
        self.mu.emu_start(fn, STOP, count=100000)
        assert self.mu.reg_read(UC_X86_REG_ESP) == sp + 4, "stack imbalance"
        return all(self.mu.reg_read(r) == v for r, v in keep.items() if r in (UC_X86_REG_EBX, UC_X86_REG_EBP))


def rel(e, site): return site + 5 + struct.unpack("<i", e.mu.mem_read(site + 1, 4))[0]


# ---- fpinit ----------------------------------------------------------------------------------------------------------
e = Emu(); e.call(FPINIT)
check("fpinit: fog site -> call fp_fog / nop", e.b(FP.SITE_FOG) == 0xE8 and rel(e, FP.SITE_FOG) == FPFOG and e.b(FP.SITE_FOG + 5) == 0x90)
check("fpinit: pick site -> call fp_pick / nop", e.b(FP.SITE_PICK) == 0xE8 and rel(e, FP.SITE_PICK) == FPPICK and e.b(FP.SITE_PICK + 5) == 0x90)
check("fpinit: both ranges made writable (6 bytes each)", [c[1] for c in e.calls if c[0] == "vp"] == [(FP.SITE_FOG, 6, 0x40), (FP.SITE_PICK, 6, 0x40)])
for site, name in ((FP.SITE_FOG, "fog"), (FP.SITE_PICK, "pick")):
    e = Emu(); e.setb(site + 5, 0x55); e.call(FPINIT)
    check("fpinit refuses foreign bytes at the %s site: nothing patched" % name,
          bytes(e.mu.mem_read(FP.SITE_FOG, 5)) == FP.FOG_BYTES[:5] and bytes(e.mu.mem_read(FP.SITE_PICK, 5)) == FP.PICK_BYTES[:5] and not e.calls)

# ---- fp_fog (called as `call fp_fog` in place of `call [ecx+0x100]`: eax map, dl on/off, ecx vmt) ----------------------------
e = Emu(); e.setb(e.map + FP.MAP_PICK, 5)
kept = e.call(FPFOG, eax=e.map, edx=0xABCDEF01, ecx=e.vmt)
check("fog ON: seated player := the Players pick (5) before SetFogEnabled(1)", e.calls == [("seatchg", e.map, 5), ("fog", e.map, 1, 5)] and e.b(e.map + FP.MAP_SEATED) == 5 and kept)
e.calls.clear()
kept = e.call(FPFOG, eax=e.map, edx=0xABCDEF00, ecx=e.vmt)
check("fog OFF: seated player back to 0 (Independents)", e.calls == [("seatchg", e.map, 0), ("fog", e.map, 0, 0)] and e.b(e.map + FP.MAP_SEATED) == 0 and kept)

# ---- fp_pick (edx map, al player) ---------------------------------------------------------------------------------------
e = Emu()
kept = e.call(FPPICK, eax=0x12345603, edx=e.map)
check("pick with fog off: only the pick is stored", e.b(e.map + FP.MAP_PICK) == 3 and e.b(e.map + FP.MAP_SEATED) == 0 and not e.calls and kept)
e.setb(e.map + FP.MAP_FOGON, 1); e.setb(e.map + FP.MAP_SEATED, 3)
kept = e.call(FPPICK, eax=0x12345607, edx=e.map)
check("pick with fog on: stored, seated := 7, fog toggled off/on to redraw", e.b(e.map + FP.MAP_PICK) == 7 and e.b(e.map + FP.MAP_SEATED) == 7
      and e.calls == [("seatchg", e.map, 7), ("fog", e.map, 0, 7), ("fog", e.map, 1, 7)] and e.b(e.map + FP.MAP_FOGON) == 1 and kept)
e.calls.clear(); kept = e.call(FPPICK, eax=0x12345607, edx=e.map)
check("same pick again with fog on: no rebuild, only the redraw", e.calls == [("fog", e.map, 0, 7), ("fog", e.map, 1, 7)] and kept)
e = Emu(); e.setb(e.map + FP.MAP_PICK, 2); e.mu.mem_write(EPACK + FP.SEATCHG_RVA, b"U"); e.calls.clear()
kept = e.call(FPFOG, eax=e.map, edx=1, ecx=e.vmt)
check("foreign SeatedPlayerChanged bytes: byte stored, routine not called", e.calls == [("fog", e.map, 1, 2)] and kept)
print("ALL OK" if ok else "FAILURES")
sys.exit(0 if ok else 1)
