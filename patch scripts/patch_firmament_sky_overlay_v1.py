#!/usr/bin/env python3
r"""
Firmament sky overlay (2026-10-31): Ziggurat's TAoWHSMap.DrawDynamicScene addition, moved byte-for-byte.

User ruling 10/31: copy Ziggurat's Firmament +3 sight (done in patch_map_levels_engine_v1) and the sky overlay.
What it does (Ziggurat AoWEPACK 0x55852200..0x5585B881, PIC, ebp = load delta): while the viewport shows level 3
(Firmament), every Sky (terrain 0xE) hex gets the Surface far below blended into it - the first frame renders the
whole Surface level into an off-screen buffer (GetMem; cached per map + pixel format, BSS 0x558FAF00..0x558FAF1B),
then each frame copies it, faded (weights 0xC0/0x1D through a 565 / 555 mask table), over the Sky pixels that
match the Sky tile palette (two 0x4200-byte pixel tables for 565 / 555 screens at +0x1240 / +0x5440).
  hook 0x55778A60 (DrawDynamicScene prologue `push ebx/push esi/mov esi,edx/mov ebx,eax`, 6 B) -> block; the
  block replays the prologue and returns to 0x55778A66.
Relocation: Ziggurat block -> 0x558C0200 (free, reloc-free, unclaimed); in the reachable code (walked from its 3
entries) every disp/imm inside the block gets +delta, every rel32 leaving it is re-aimed; the external
references are vanilla thunks/VMTs/IAT (byte-identical in ours) + the AoWHSMap global + the BSS dwords.
Dry-run default; --apply; --revert.  Backup AoWEPACK.dll.bak_skyoverlay.
"""
import os, shutil, struct, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DLL, BASE = game_file("AoWEPACK.dll"), 0x55700000
ZIG = r"C:\Users\<user>\Desktop\AoW Ziggurat\Ziggurat\AoWEPACK.dpl"
ZS, ZE = 0x55852200, 0x5585B881
ENTRIES = [0x55852200, 0x55852600, 0x55852900]
NEW = 0x558C0200
DELTA = NEW - ZS
HOOK, HOOK_ORIG, RESUME = 0x55778A60, bytes.fromhex("53568bf28bd8"), 0x55778A66
BSS = (0x558FAF00, 0x558FAF1C)
EXTERNAL_OK = {0x557133A0, 0x5579A458, 0x558FA040, 0x558FB714, 0x558FB718,
               0x55702034, 0x5570203C, 0x557020DC, 0x557020EC, 0x5570260C, 0x55702614, RESUME} | \
              set(range(BSS[0], BSS[1], 4))


def relocated(z, zoff):
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32, CS_GRP_JUMP, CS_GRP_CALL
    from capstone.x86 import X86_OP_IMM, X86_OP_MEM
    md = Cs(CS_ARCH_X86, CS_MODE_32); md.detail = True
    blk = bytearray(z[zoff(ZS):zoff(ZE)])
    seen, todo, ext, fixes = set(), list(ENTRIES), set(), 0
    while todo:
        a = todo.pop()
        while ZS <= a < ZE and a not in seen:
            ins = next(md.disasm(bytes(blk[a - ZS:a - ZS + 16]), a))
            seen.add(a)
            branch = ins.group(CS_GRP_JUMP) or ins.group(CS_GRP_CALL)
            for op in ins.operands:
                if op.type == X86_OP_IMM and branch:
                    t = op.imm & 0xFFFFFFFF
                    if ZS <= t < ZE:
                        todo.append(t)
                    else:
                        ext.add(t)
                        assert ins.bytes[0] in (0xE8, 0xE9) or ins.bytes[0] == 0x0F, ins
                        p = a - ZS + ins.size - 4
                        struct.pack_into("<i", blk, p, t - (a + DELTA + ins.size))
                        fixes += 1
            for v, kind in [(op.mem.disp & 0xFFFFFFFF, "m") for op in ins.operands if op.type == X86_OP_MEM] + \
                           [(op.imm & 0xFFFFFFFF, "i") for op in ins.operands if op.type == X86_OP_IMM and not branch]:
                if v < 0x55700000 or v >= 0x56000000:
                    continue
                raw = bytes(blk[a - ZS:a - ZS + ins.size])
                k = raw.rfind(struct.pack("<I", v))
                assert k > 0, ins
                if ZS <= v < ZE + 0x80:
                    struct.pack_into("<I", blk, a - ZS + k, v + DELTA)
                    fixes += 1
                else:
                    ext.add(v)
            if ins.mnemonic == "ret" or (ins.mnemonic == "jmp"):
                break
            a += ins.size
    bad = sorted(hex(e) for e in ext if e not in EXTERNAL_OK)
    assert not bad, bad
    return bytes(blk), len(seen), fixes


def main():
    import pefile
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    z = open(ZIG, "rb").read(); zpe = pefile.PE(data=z)
    zoff = lambda va: zpe.get_offset_from_rva(va - BASE)  # noqa: E731
    blk, ninsn, nfix = relocated(z, zoff)
    d = open(DLL, "rb").read(); pe = pefile.PE(data=d)
    off = lambda va: pe.get_offset_from_rva(va - BASE)  # noqa: E731
    hook = b"\xe9" + struct.pack("<i", NEW - (HOOK + 5)) + b"\x90"
    P = [(HOOK, HOOK_ORIG, hook), (NEW, bytes(len(blk)), blk)]
    rl = {BASE + e.rva for b in pe.DIRECTORY_ENTRY_BASERELOC for e in b.entries if e.type == 3}
    badrl = [hex(r) for r in rl if any(s - 3 <= r < s + len(o) for s, o, _ in P)]
    # nobody else may use the BSS dwords
    code = pe.sections[0]
    cd = d[code.PointerToRawData:code.PointerToRawData + code.SizeOfRawData]
    users = [hex(BASE + code.VirtualAddress + i) for v in range(BSS[0], BSS[1])
             for i in [cd.find(struct.pack("<I", v))] if i >= 0 and not
             (NEW <= BASE + code.VirtualAddress + i < NEW + len(blk))]
    st = []
    for s, o, n in P:
        c = d[off(s):off(s) + len(o)]
        st.append("vanilla" if c == o else "ours" if c == n else "OTHER")
    print("block %d B -> %#x (%d insns walked, %d fixups) | %s | relocs %s | BSS users %s"
          % (len(blk), NEW, ninsn, nfix, st, badrl or "none", users or "none"))
    if "OTHER" in st or badrl or (users and set(st) != {"ours"}):
        print("ABORT"); return 1
    want = "vanilla" if revert else "ours"
    if set(st) == {want}:
        print("already %s" % ("reverted" if revert else "applied")); return 0
    if len(set(st)) != 1:
        print("ABORT (mixed state)"); return 1
    if not apply and not revert:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    r = subprocess.run(["tasklist"], capture_output=True, text=True).stdout
    if "AoWx.exe" in r or "AoWDevX.exe" in r:
        print("game/editor running - close it first"); return 1
    bak = bak_path(DLL, ".bak_skyoverlay")
    if not revert and not os.path.exists(bak):
        shutil.copy2(DLL, bak)
    with open(DLL, "r+b") as f:
        for s, o, n in P:
            f.seek(off(s)); f.write(o if revert else n)
    d2 = open(DLL, "rb").read()
    assert all(d2[off(s):off(s) + len(o)] == (o if revert else n) for s, o, n in P)
    print("reverted" if revert else "written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
