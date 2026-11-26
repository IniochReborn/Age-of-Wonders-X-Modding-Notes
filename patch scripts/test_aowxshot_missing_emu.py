#!/usr/bin/env python3
"""Unicorn checks for aowxshot_missing (AoWxShot.dll v2): logit (owner-chain walk to the TMapField incl. a derived
class, message copy with control chars -> spaces, overflow line), patch5 (bytes verified, jmp out + jmp back
encoding) and setclick (component found by name, OnClick TMethod written)."""
import os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
from unicorn.x86_const import UC_X86_REG_ESP, UC_X86_REG_EAX, UC_X86_REG_EDX, UC_X86_REG_ECX, UC_X86_REG_EBP, \
    UC_X86_REG_EBX, UC_X86_REG_EDI, UC_X86_REG_ESI
import build_aowxshot as SHOT
import aowxshot_missing as MS

img, info = SHOT.build(os.path.dirname(HERE))
pe = pefile.PE(data=img)
B = SHOT.BASE
mem = pe.get_memory_mapped_image()
code = mem
sym = {}


def find(pat):
    i = mem.find(bytes.fromhex(pat))
    assert i > 0 and mem.find(bytes.fromhex(pat), i + 1) < 0, pat
    return B + i


def labels(names):
    """re-assemble the DLL source with extra probes appended after the last one -> label VAs (code before them is
    unchanged)"""
    gd = os.path.dirname(HERE)
    D_, _ = SHOT.build_data(B + SHOT.SEC_RVA, gd)
    D_.align(16)
    imp_rva = SHOT.SEC_RVA + len(D_.b)
    ib, IAT, *_r = SHOT.build_imports(imp_rva)
    body = len(D_.b) + len(ib)
    body = (body + 15) & ~15
    code_va = B + SHOT.SEC_RVA + body
    src = SHOT.asm_text(D_, IAT, code_va)
    nl = chr(10)
    src = src.replace("        mov eax, initx" + nl, "        mov eax, initx" + nl + "".join(
        "        mov eax, %s" % n + nl for n in names))
    c = SHOT.assemble(src, code_va + 0x20)
    t = c[-5 * len(names):]
    assert code_va == info["code_va"]
    return [struct.unpack_from("<I", t, 5 * i + 1)[0] for i in range(len(names))]


LOGIT, PATCH5, SETCLICK, HOOK_A, HA_RET, RG_L, RG_DONE = labels(["logit", "patch5", "setclick", "hook_a", "ha_ret", "rg_l", "rg_done"])
imps = {s.name.decode(): s.address for d in pe.DIRECTORY_ENTRY_IMPORT for s in d.imports}
D, _fp = SHOT.build_data(B + SHOT.SEC_RVA, os.path.dirname(HERE))
G = D.sym


def mk():
    mu = Uc(UC_ARCH_X86, UC_MODE_32)
    mu.mem_map(B, (len(mem) + 0xFFF) & ~0xFFF)
    mu.mem_write(B, bytes(mem))
    mu.mem_map(0x100000, 0x100000)                 # heap / stack
    mu.mem_map(0xDEAD0000, 0x1000)
    stubs = 0x1F0000
    # IsBadReadPtr -> 0 (ret 8), VirtualProtect -> 1 (ret 0x10)
    mu.mem_write(stubs, b"\x31\xc0\xc2\x08\x00")
    mu.mem_write(stubs + 0x10, b"\xb8\x01\x00\x00\x00\xc2\x10\x00")
    mu.mem_write(imps["IsBadReadPtr"], struct.pack("<I", stubs))
    mu.mem_write(imps["VirtualProtect"], struct.pack("<I", stubs + 0x10))
    return mu


def call(mu, fn, **regs):
    sp = 0x1F8000
    mu.mem_write(sp, struct.pack("<I", 0xDEAD0000))
    mu.reg_write(UC_X86_REG_ESP, sp)
    mu.reg_write(UC_X86_REG_EBP, 0)                 # load delta 0 (image at its preferred base)
    for k, v in regs.items():
        mu.reg_write({"eax": UC_X86_REG_EAX, "edx": UC_X86_REG_EDX, "ecx": UC_X86_REG_ECX, "ebx": UC_X86_REG_EBX,
                      "edi": UC_X86_REG_EDI, "esi": UC_X86_REG_ESI}[k], v)
    mu.emu_start(fn, 0xDEAD0000, count=200000)
    return mu.reg_read(UC_X86_REG_EAX)


def w32(mu, a, v):
    mu.mem_write(a, struct.pack("<I", v))


def r32(mu, a):
    return struct.unpack("<I", mu.mem_read(a, 4))[0]


ok = True
mu = mk()
# classes: FV (TMapField), FV2 derived (parent cell -> FV), AV army, LV level
FV, FV2, AV, LV = 0x110100, 0x110200, 0x110300, 0x110400
PC = 0x110500
w32(mu, PC, FV)
w32(mu, FV2 - 0x18, PC)
w32(mu, FV - 0x18, 0)
w32(mu, AV - 0x18, 0)
w32(mu, LV - 0x18, 0)
w32(mu, G["g_fieldvmt"], FV)
F, L, A, E, S = 0x120000, 0x120100, 0x120200, 0x120300, 0x120400
w32(mu, F, FV2); w32(mu, F + 4, L); mu.mem_write(F + 0x10, bytes([12, 34, 2]))
w32(mu, L, LV); w32(mu, L + 4, 0)
w32(mu, A, AV); w32(mu, A + 4, F)
msg = b"unit resource missing (77)\r\nnext"
mu.mem_write(S, msg + b"\0"); w32(mu, E, 0x55555555); w32(mu, E + 4, S)
call(mu, LOGIT, eax=A, edx=E, ecx=123)
e0 = G["g_ents"]
cid, x, y, lv = struct.unpack("<iiii", mu.mem_read(e0, 16))
txt = bytes(mu.mem_read(e0 + 16, 64)).split(b"\0")[0]
print("entry0", cid, x, y, lv, txt)
ok &= (cid, x, y, lv) == (123, 12, 34, 2) and txt == b"unit resource missing (77)  next"
# no field in the chain -> location -1
w32(mu, A + 4, 0)
call(mu, LOGIT, eax=A, edx=0, ecx=0xFFFFFFFF)
cid, x, y, lv = struct.unpack("<iiii", mu.mem_read(e0 + MS.ESZ, 16))
print("entry1", cid, x, y, lv)
ok &= (x, y, lv) == (-1, -1, -1) and r32(mu, G["g_ncnt"]) == 2
# overflow: count stops at MAXE + 1
w32(mu, G["g_ncnt"], MS.MAXE)
call(mu, LOGIT, eax=0, edx=0, ecx=1)
call(mu, LOGIT, eax=0, edx=0, ecx=1)
print("overflow count", r32(mu, G["g_ncnt"]))
ok &= r32(mu, G["g_ncnt"]) == MS.MAXE + 1
# patch5
SITE, STUB, RET = 0x130000, 0x131000, 0x132000
mu.mem_write(SITE, MS.ENG_BYTES); mu.mem_write(G["x_eng"], MS.ENG_BYTES)
r = call(mu, PATCH5, edi=SITE, esi=STUB, ecx=RET, edx=G["x_eng"])
j = bytes(mu.mem_read(SITE, 5)); jb = bytes(mu.mem_read(RET, 5))
print("patch5", r, j.hex(), jb.hex())
ok &= r == 1 and j[0] == 0xE9 and SITE + 5 + struct.unpack("<i", j[1:])[0] == STUB
ok &= jb[0] == 0xE9 and RET + 5 + struct.unpack("<i", jb[1:])[0] == SITE + 5
mu.mem_write(SITE + 0x100, b"\x90" * 5)
r = call(mu, PATCH5, edi=SITE + 0x100, esi=STUB, ecx=RET + 0x100, edx=G["x_eng"])
print("patch5 mismatch ->", r, bytes(mu.mem_read(SITE + 0x100, 5)).hex())
ok &= r == 0 and bytes(mu.mem_read(SITE + 0x100, 5)) == b"\x90" * 5
# setclick: form +0x10 = TList (+4 items, +8 count); component name AnsiString at +8
FORM, LST, ITEMS = 0x140000, 0x140100, 0x140200
w32(mu, FORM + 0x10, LST); w32(mu, LST + 4, ITEMS); w32(mu, LST + 8, 3)
names = [b"ValidateMapBtn", b"MissingBtn", b"ScreenshotBtn"]
for i, n in enumerate(names):
    c = 0x141000 + i * 0x200
    w32(mu, ITEMS + 4 * i, c)
    s = 0x150000 + i * 0x40
    w32(mu, s - 4, len(n)); mu.mem_write(s, n + b"\0")
    w32(mu, c + 8, s)
mu.mem_write(G["s_btnmiss"], b"MissingBtn\0")
call(mu, SETCLICK, ebx=FORM, edx=G["s_btnmiss"], ecx=0xC0DE)
c1 = 0x141200
print("setclick", hex(r32(mu, c1 + 0xA4)), hex(r32(mu, c1 + 0xA8)), hex(r32(mu, 0x141000 + 0xA4)))
ok &= r32(mu, c1 + 0xA4) == 0xC0DE and r32(mu, c1 + 0xA8) == FORM and r32(mu, 0x141000 + 0xA4) == 0
# hook_a at the rwCreateEObject handler entry: [ebp-8] = slot -> failing object, [obj+4] = owner field
mu = mk()
w32(mu, PC, FV); w32(mu, FV2 - 0x18, PC); w32(mu, FV - 0x18, 0); w32(mu, AV - 0x18, 0); w32(mu, LV - 0x18, 0)
w32(mu, G["g_fieldvmt"], FV)
OBJ, FR, SLOT = 0x121000, 0x1F7000, 0x121100
w32(mu, OBJ, AV); w32(mu, OBJ + 4, F)
w32(mu, F, FV2); w32(mu, F + 4, L); mu.mem_write(F + 0x10, bytes([9, 41, 5])); w32(mu, L, LV); w32(mu, L + 4, 0)
w32(mu, SLOT, OBJ); w32(mu, FR - 8, SLOT); w32(mu, FR - 0x10, 777)
mu.mem_write(S, b"Resource Missing TFooMO: 4242" + bytes(1)); w32(mu, E + 4, S)
mu.reg_write(UC_X86_REG_ESP, 0x1F6000); mu.reg_write(UC_X86_REG_EBP, FR); mu.reg_write(UC_X86_REG_EBX, E)
mu.reg_write(UC_X86_REG_ESI, 0x31337)
mu.emu_start(HOOK_A, HA_RET, count=100000)
cid, x, y, lv = struct.unpack("<iiii", mu.mem_read(G["g_ents"], 16))
txt = bytes(mu.mem_read(G["g_ents"] + 16, 64)).split(bytes(1))[0]
print("hook_a", cid, x, y, lv, txt, hex(mu.reg_read(UC_X86_REG_EAX)), hex(mu.reg_read(UC_X86_REG_EBP)),
      hex(mu.reg_read(UC_X86_REG_ESI)))
ok &= (cid, x, y, lv) == (777, 9, 41, 5) and txt == b"Resource Missing TFooMO: 4242"
ok &= mu.reg_read(UC_X86_REG_EAX) == OBJ and mu.reg_read(UC_X86_REG_EBP) == FR and mu.reg_read(UC_X86_REG_ESI) == 0x31337
# site defender: unit -> army (owner nil); g_cursite = site whose [+0x34] is that army; site [+4] = field
mu = mk()
w32(mu, PC, FV); w32(mu, FV2 - 0x18, PC); w32(mu, FV - 0x18, 0); w32(mu, AV - 0x18, 0); w32(mu, LV - 0x18, 0)
w32(mu, G["g_fieldvmt"], FV)
UNIT, ARMY, SITE = 0x122000, 0x122100, 0x122200
w32(mu, UNIT, AV); w32(mu, UNIT + 4, ARMY); w32(mu, ARMY, AV); w32(mu, ARMY + 4, 0)
w32(mu, SITE, AV); w32(mu, SITE + 4, F); w32(mu, SITE + 0x34, ARMY)
w32(mu, F, FV2); w32(mu, F + 4, L); mu.mem_write(F + 0x10, bytes([20, 30, 1])); w32(mu, L, LV); w32(mu, L + 4, 0)
w32(mu, G["g_cursite"], SITE)
call(mu, LOGIT, eax=UNIT, edx=0, ecx=5)
cid, x, y, lv = struct.unpack("<iiii", mu.mem_read(G["g_ents"], 16))
print("site defender", cid, x, y, lv)
ok &= (x, y, lv) == (20, 30, 1)
w32(mu, SITE + 0x34, 0x99999)            # a different site's army -> no match
call(mu, LOGIT, eax=UNIT, edx=0, ecx=6)
cid, x, y, lv = struct.unpack("<iiii", mu.mem_read(G["g_ents"] + MS.ESZ, 16))
print("other site", cid, x, y, lv)
ok &= (x, y, lv) == (-1, -1, -1)
# regen loop: stubs log (id, eax, edx); units: TUnit w/ type, THero, TUnit w/o type, TUnit w/ type
mu = mk()
TU, TH = 0x160000, 0x160100
LOGP, LOGB, ST = 0x170000, 0x170010, 0x171000
w32(mu, LOGP, LOGB)
for k, nm in enumerate(("r_unreg", "r_setres", "r_reg", "r_changed")):
    code = (bytes.fromhex("8b0d") + struct.pack("<I", LOGP) + bytes.fromhex("c701") + struct.pack("<I", k) + bytes.fromhex("8941048951088305") + struct.pack("<I", LOGP) + bytes.fromhex("0c31c031d231c9c3"))
    mu.mem_write(ST + 0x40 * k, code); w32(mu, G[nm], ST + 0x40 * k)
w32(mu, G["r_tunit"], TU)
UC, LST, IT = 0x172000, 0x172100, 0x172200
us = [(TU, 0xAAA1), (TH, 0xBBB1), (TU, 0), (TU, 0xAAA2)]
for i, (cls, res) in enumerate(us):
    u = 0x173000 + 0x100 * i; w32(mu, u, cls); w32(mu, u + 0x40, res); w32(mu, IT + 4 * i, u)
w32(mu, UC + 0x10, LST); w32(mu, LST + 4, IT); w32(mu, LST + 8, len(us)); w32(mu, G["g_uc"], UC)
mu.reg_write(UC_X86_REG_ESP, 0x1F6000); mu.reg_write(UC_X86_REG_EBP, 0)
mu.reg_write(UC_X86_REG_ESI, 0); mu.reg_write(UC_X86_REG_EDI, 0)
mu.emu_start(RG_L, RG_DONE, count=100000)
n = (r32(mu, LOGP) - LOGB) // 12
calls = [struct.unpack("<III", mu.mem_read(LOGB + 12 * i, 12)) for i in range(n)]
print("regen calls", [(c[0], hex(c[1]), hex(c[2])) for c in calls], "done", mu.reg_read(UC_X86_REG_EDI))
u0, u3 = 0x173000, 0x173300
exp = [(0, u0), (1, u0, 0), (1, u0, 0xAAA1), (2, u0), (3, u0), (0, u3), (1, u3, 0), (1, u3, 0xAAA2), (2, u3), (3, u3)]
ok &= len(calls) == len(exp) and all(c[0] == e[0] and c[1] == e[1] and (len(e) < 3 or c[2] == e[2]) for c, e in zip(calls, exp))
ok &= mu.reg_read(UC_X86_REG_EDI) == 2
print("ALL OK" if ok else "FAILED")
sys.exit(0 if ok else 1)
