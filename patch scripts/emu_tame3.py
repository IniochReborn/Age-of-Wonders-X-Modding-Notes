"""Unicorn: the touch-TE id switch (AoWTCPCK 0x40A5F4..).  For every id 0..255, the v3-applied DLL must reach the
same switch target as the pre-v3 DLL, except 0xC9 which must now reach the command case 0x40A752 (Dominate's).
Run at the preferred base and rebased; callee-saved registers + esp must be untouched.
usage: emu_tame3.py <pre-v3 AoWTCPCK.dll> <v3-applied AoWTCPCK.dll>"""
import struct, sys
from unicorn import *
from unicorn.x86_const import *
def load(path, base):
    d = open(path, "rb").read(); pe = struct.unpack_from("<I", d, 0x3C)[0]
    opt = struct.unpack_from("<H", d, pe + 20)[0]; n = struct.unpack_from("<H", d, pe + 6)[0]
    img = struct.unpack_from("<I", d, pe + 24 + 56)[0]
    mu = Uc(UC_ARCH_X86, UC_MODE_32); mu.mem_map(base, (img + 0xFFF) & ~0xFFF)
    for k in range(n):
        vs, va, rs, ro = struct.unpack_from("<IIII", d, pe + 24 + opt + 40 * k + 8)
        mu.mem_write(base + va, d[ro:ro + rs])
    mu.mem_map(0x100000, 0x10000)
    return mu
TARGETS = {0x40A752: "command", 0x40A654: "0x28", 0x40A6D3: "0x1B", 0x40A855: "0x23", 0x40A7D4: "0x26",
           0x40A8D4: "0x2F", 0x40A94B: "0x3C", 0x40A9D1: "0x6A/0x6B", 0x40AAED: "default"}
SAVED = (UC_X86_REG_EBX, UC_X86_REG_ESI, UC_X86_REG_EDI, UC_X86_REG_EBP, UC_X86_REG_ESP)
def target(mu, base, ident):
    dl = base - 0x400000; te = 0x100000
    mu.mem_write(te, bytes(0x100)); mu.mem_write(te + 0x3C, struct.pack("<I", ident))
    mu.reg_write(UC_X86_REG_EAX, te); mu.reg_write(UC_X86_REG_ESP, 0x108000)
    for k, r in enumerate(SAVED[:4]): mu.reg_write(r, 0x11111111 * (k + 1))
    before = [mu.reg_read(r) for r in SAVED]; hit = []
    def hook(uc, addr, size, ud):
        if addr - dl in TARGETS: hit.append(addr - dl); uc.emu_stop()
    h = mu.hook_add(UC_HOOK_CODE, hook); mu.emu_start(base + 0x40A5F4 - 0x400000, 0, count=40); mu.hook_del(h)
    return (hit[0] if hit else None), before == [mu.reg_read(r) for r in SAVED]
fails = 0
for base in (0x400000, 0x1230000):
    pre, post = load(sys.argv[1], base), load(sys.argv[2], base)
    for ident in range(256):
        a, _ = target(pre, base, ident); b, regs = target(post, base, ident)
        want = 0x40A752 if ident == 0xC9 else a
        ok = b == want and regs and b is not None
        if not ok or ident in (0x1C, 0x1D, 0x94, 0xC9, 0xCA, 0x28):
            print("base %#x id %#04x  pre %-9s v3 %-9s %s" % (base, ident, TARGETS.get(a, a), TARGETS.get(b, b), "ok" if ok else "FAIL"))
        fails += not ok
    print("base %#x: 256 ids checked" % base)
print("FAILURES:", fails); sys.exit(1 if fails else 0)
