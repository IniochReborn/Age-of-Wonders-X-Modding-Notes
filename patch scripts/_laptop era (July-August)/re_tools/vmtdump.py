# -*- coding: utf-8 -*-
"""Dump VMT slots of a Delphi class with symbol names.
Usage: py vmtdump.py <module> <classref-or-vmt-va-hex> [maxslot-hex]
Accepts either the class-ref slot VA (holds VMT ptr) or the VMT VA itself
(detected via self-ptr at [VMT-0x40])."""
import sys
import aowsyms

mod = sys.argv[1]
va = int(sys.argv[2], 16)
maxslot = int(sys.argv[3], 16) if len(sys.argv) > 3 else 0x140

pe, base, syms, iat = aowsyms.get_symbols(mod)

def u32(va_):
    return pe.u32(va_ - base)

# resolve: VMT self-ptr at VMT-0x40 equals VMT
cand = va
if u32(cand - 0x40) != cand:
    cand = u32(va)  # treat as class-ref slot
    if cand is None or u32(cand - 0x40) != cand:
        print("neither VA nor [VA] looks like a VMT (self-ptr check failed)")
        sys.exit(1)

vmt = cand
nameptr = u32(vmt - 0x20)
cname = pe.shortstr(nameptr - base) if nameptr else "?"
print("VMT %08X  class=%s" % (vmt, cname))
for off in range(0, maxslot + 4, 4):
    fp = u32(vmt + off)
    if fp is None:
        break
    nm = syms.get(fp)
    if nm is None:
        # nearest symbol below
        below = [(fp - a, n) for a, n in syms.items() if 0 <= fp - a < 0x4000]
        if below:
            d, n = min(below)
            nm = "%s+0x%X" % (n, d) if d else n
        else:
            nm = ""
    print("  +0x%03X  %08X  %s" % (off, fp, nm))
