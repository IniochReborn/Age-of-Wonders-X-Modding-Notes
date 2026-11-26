#!/usr/bin/env python3
"""dasm.py <file> <va_start> [<va_end>|+len]  -- capstone x86-32 disassembly by VA (module bases known)."""
import sys, pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_32
BASES = {"aowepack.dll": 0x55700000, "aowtcpck.dll": 0x400000, "aowx.exe": 0x400000, "hsepack.dpl": 0x55600000,
         "aowint.dpl": 0x59800000, "vcl30.dpl": 0x41300000, "dcpack.dpl": 0x55100000, "ilpack.dpl": 0x55200000, "enginep.dpl": 0x55400000, "aowdevx.exe": 0x400000, "aowed.exe": 0x400000, "aowdplay.dpl": 0x400000, "gfxepack.dpl": 0x55000000}
f = sys.argv[1]; base = BASES[f.lower().split("/")[-1].split("\\")[-1]]
pe = pefile.PE(f, fast_load=True); d = pe.__data__
s = int(sys.argv[2], 16); e = sys.argv[3] if len(sys.argv) > 3 else "+0x100"
e = s + int(e[1:], 16) if e.startswith("+") else int(e, 16)
o = pe.get_offset_from_rva(s - base)
md = Cs(CS_ARCH_X86, CS_MODE_32)
for i in md.disasm(d[o:o + (e - s)], s):
    print(f"{i.address:08X}  {i.bytes.hex():<16} {i.mnemonic:<7} {i.op_str}")
