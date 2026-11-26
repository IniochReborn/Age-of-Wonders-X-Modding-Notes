#!/usr/bin/env python3
r"""
Bountiful Harvest (325) - show the BOOSTED income in the AoWx.exe-side displays (2026-10-15).

The bonus itself lives in AoWEPACK (patch_harvest_v1.py: the GetIncome slot VMT+0x1F4 of TPlayerCropStructure /
TCity / TFarm returns [obj+0x3C] + the crop count while the owner has an active 325; the live probe confirmed the
payout).  Four exe displays printed the RAW cached byte [obj+0x3C] instead of calling GetIncome, so they never showed
the bonus (the other exe income displays - 0x43F679/0x43F68F, 0x44286B - already call VMT+0x1F4):

  A  0x43B3BE  city window header "Income: X gold" ([window+0x2B0] = the TCity; every setter is TCity-checked)
               `movzx eax,byte [eax+0x3c] / call IntToStr`                      (9 B)
  B  0x442A92  structure info window, generic branch "Income X" (esi = the structure; the same window already calls
               esi's VMT+0x1F4 in 0x44275C, which this branch runs first)
               `xor eax,eax / mov al,[esi+0x3c] / call IntToStr`               (10 B)
  C  0x443454  structure info window, city branch (esi = the city; 0x44275C(esi) runs first too)      (10 B)
  D  0x4493B6  city list line (esi = a TCity: the routine checks the class first)                       (10 B)

Each site -> `call cave` + NOPs; the cave saves edx (= &string), calls the object's GetIncome (VMT+0x1F4), restores edx
and tail-jumps IntToStr 0x4013AC, so it returns straight to the NOPs.  No absolute addresses, no state: display only.
Caves in .xbfs 0x60ED00..0x60ED40 (zero-verified).  Revert restores the four sites IN PLACE and zeroes the caves (no
whole-file restore - AoWx.exe carries many patches).  A one-time safety copy goes to backup\ (bakpath).
Dry-run default; --apply; --revert; --dis.
"""
import argparse, os, shutil, struct, sys
from bakpath import game_file, bak_path
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

DEFAULT_EXE = game_file(r"AoWx.exe")
BAK = ".bak_harvestdisp"
BASE = 0x400000
INTTOSTR = 0x4013AC
CAVE, CAVE_END = 0x60ED00, 0x60ED40
SITES = {                                     # name: (va, original bytes, cave key)
    "A": (0x43B3BE, bytes.fromhex("0fb6403ce8e55ffcff"), "eax"),
    "B": (0x442A92, bytes.fromhex("33c08a463ce810e9fbff"), "esi"),
    "C": (0x443454, bytes.fromhex("33c08a463ce84edffbff"), "esi"),
    "D": (0x4493B6, bytes.fromhex("33c08a463ce8ec7ffbff"), "esi"),
}
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, va):
    return bytes(ks.asm(src, va)[0])


def build():
    out = bytearray(); where = {}
    def place(name, src):
        while len(out) % 16: out.append(0)
        va = CAVE + len(out); where[name] = va; out.extend(asm(src, va))
    place("eax", f"""
        push edx
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x1f4]
        pop edx
        jmp {INTTOSTR:#x}
    """)
    place("esi", f"""
        push edx
        mov eax, esi
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x1f4]
        pop edx
        jmp {INTTOSTR:#x}
    """)
    assert CAVE + len(out) <= CAVE_END
    return bytes(out), where


def va2off(d, va):
    e = struct.unpack_from("<I", d, 0x3C)[0]; n = struct.unpack_from("<H", d, e + 6)[0]; opt = struct.unpack_from("<H", d, e + 20)[0]
    for k in range(n):
        vs, rva, rs, ro = struct.unpack_from("<IIII", d, e + 24 + opt + 40 * k + 8)
        if rva <= va - BASE < rva + max(vs, rs): return ro + va - BASE - rva
    raise ValueError(hex(va))


def reloc_hits(d, ranges):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    rva, sz = struct.unpack_from("<II", d, e + 24 + 0x88)
    if not sz: return []
    off = va2off(d, BASE + rva); end = off + sz; hits = []
    while off + 8 <= end:
        page, bsz = struct.unpack_from("<II", d, off)
        if bsz < 8: break
        for i in range((bsz - 8) // 2):
            ent = struct.unpack_from("<H", d, off + 8 + 2 * i)[0]
            if ent >> 12:
                va = BASE + page + (ent & 0xFFF)
                if any(lo <= va < hi for lo, hi in ranges): hits.append(va)
        off += bsz
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("exe", nargs="?", default=DEFAULT_EXE)
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true"); ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    d = bytearray(open(a.exe, "rb").read())
    code, where = build()
    hooks, state = {}, {}
    for nm, (va, orig, key) in SITES.items():
        h = b"\xe8" + struct.pack("<i", where[key] - (va + 5)) + b"\x90" * (len(orig) - 5)
        hooks[nm] = h
        live = bytes(d[va2off(d, va):va2off(d, va) + len(orig)])
        state[nm] = "vanilla" if live == orig else "ours" if live == h else "OTHER(%s)" % live.hex()
    zl = bytes(d[va2off(d, CAVE):va2off(d, CAVE_END)])
    zstate = "zero" if not any(zl) else "ours" if zl[:len(code)] == code and not any(zl[len(code):]) else "DIFFERS"
    rl = reloc_hits(d, [(va, va + len(o)) for va, o, _k in SITES.values()] + [(CAVE, CAVE_END)])
    print("target: %s\n  sites %s\n  caves %s (%d B) zone %s | relocs %s"
          % (a.exe, state, ", ".join("%s=%#x" % kv for kv in where.items()), len(code), zstate, [hex(v) for v in rl] or "none"))
    if a.dis:
        import capstone
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(code, CAVE):
            print("   %08X  %-16s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if rl or any(s.startswith("OTHER") for s in state.values()): print("ABORT"); return 1
    if a.revert:
        for nm, (va, orig, _k) in SITES.items(): d[va2off(d, va):va2off(d, va) + len(orig)] = orig
        if zstate == "ours": d[va2off(d, CAVE):va2off(d, CAVE_END)] = bytes(CAVE_END - CAVE)
        with open(a.exe, "r+b") as f: f.write(bytes(d))
        print("reverted (sites restored in place, caves zeroed)"); return 0
    if all(s == "ours" for s in state.values()) and zstate == "ours": print("already applied"); return 0
    if zstate == "DIFFERS": print("ABORT (cave zone not free)"); return 1
    d[va2off(d, CAVE):va2off(d, CAVE_END)] = bytes(CAVE_END - CAVE); d[va2off(d, CAVE):va2off(d, CAVE) + len(code)] = code
    for nm, (va, orig, _k) in SITES.items(): d[va2off(d, va):va2off(d, va) + len(orig)] = hooks[nm]
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(a.exe, BAK)
    if not os.path.exists(bak): shutil.copy2(a.exe, bak); print("  safety copy ->", bak)
    with open(a.exe, "r+b") as f: f.write(bytes(d))
    assert open(a.exe, "rb").read() == bytes(d); print("Written and verified"); return 0


if __name__ == "__main__":
    sys.exit(main())
