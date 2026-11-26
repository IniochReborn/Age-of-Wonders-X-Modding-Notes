#!/usr/bin/env python3
r"""
Static Shield (215) - LIST HIDE (2026-10-16).  User: "similar to how a unit enchanted with Fire Halo only shows Fire Halo
in the unit panel (not Fire Immunity / Fire Strike), don't display Lightning Immunity and Lightning Strike in the unit
panel, only Static Shield."

Why they showed: patch_staticshield_v1.py answers 0x09 Lightning Immunity / 0x10 Lightning Strike as IMPLIED for a 0xC4
holder in the GetAbilityEnabled 'not present' tails (t1 0x5574FD98 owner VMT+0x88 path, t2 0x5577F612 TAbstractUnit
VMT+0x148) - and the ability LISTS enumerate ids through those same queries:
  * in-combat unit panel  AoWTC.TTacticalCombatUnitHS.CreateTCAbList 0x423430 (AoWTCPCK): per id 1..BOUND-1
    `call [ecx+0xA8]` @0x42349B = TCombatUnit.HasAbility -> 0x55725004 -> unit VMT+0x148 -> t2;
  * unit banner popup (AoWx.exe) loop @0x455D45: per id `call [ecx+0x148]` @0x455D4F.
  (The overland unit window TAbstractUnit.ListAbilityInfo 0x5577FA50 enumerates the OWN bitset VMT+0x14C - implied
  abilities never appear there, nothing to do.)

Fix = a LISTING flag, one byte in AoWx.exe's .xbfs (the exe never rebases - ImageBase 0x400000, DllCharacteristics 0 -
so every module can address it absolutely; no reloc needed):
  TC   AoWTCPCK site 0x42349B `call [ecx+0xA8]` (6 B, no reloc) -> `call cave + nop`; cave 0x444400: flag=1 / call
       [ecx+0xA8] / flag=0 / ret (regs + al result untouched).
  EXE  AoWx.exe site 0x455D4F `call [ecx+0x148]` (6 B, no reloc) -> `call cave + nop`; cave .xbfs 0x60EF80: same.
  T1/T2 AoWEPACK: a filter cave chained IN FRONT of Static Shield's t1/t2 caves (site jmp decoded AT APPLY TIME; same
       `jmp +5 / jmp prev` header so later scripts can chain): flag set AND id (esi) is 0x09/0x10 -> jump straight to
       the target BEHIND Static Shield's cave (decoded from its header at apply time) = the 0xC4 implication is skipped
       while a list is built; anything else -> Static Shield's cave as before.  Damage/immunity checks never run with
       the flag set, so the unit still really is immune and still strikes with lightning.
Flag byte 0x60EFE0 (.xbfs zero slack; 0x60EFF0.. = the datesort --diag counters).  Zones: AoWEPACK 0x5586E000..,
AoWTCPCK 0x444400.., AoWx.exe 0x60EF80..0x60EFE0 (all verified zero, reloc-free).
Zone headers keep the previous site targets for an exact --revert.  Backups <game>\backup\*.bak_sslisthide.
Dry-run default; --apply / --revert / --dll / --tc / --exe <scratch copies>.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
import pefile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

FLAG = 0x60EFE0
SUF = ".bak_sslisthide"
IMPLIED = (0x09, 0x10)
ks = Ks(KS_ARCH_X86, KS_MODE_32)
TOK = b"SSLH"                                         # zone header magic


def asm(src, va):
    return bytes(ks.asm(src, va)[0])


class Img:
    def __init__(self, path):
        self.path = path; self.d = bytearray(open(path, "rb").read())
        pe = pefile.PE(data=bytes(self.d)); self.base = pe.OPTIONAL_HEADER.ImageBase; self.pe = pe
        self.rel = {e.rva + self.base for b in getattr(pe, "DIRECTORY_ENTRY_BASERELOC", []) for e in b.entries if e.type}

    def off(self, va): return self.pe.get_offset_from_rva(va - self.base)
    def rd(self, va, n): o = self.off(va); return bytes(self.d[o:o + n])
    def wr(self, va, b): o = self.off(va); self.d[o:o + len(b)] = b
    def relocs(self, lo, hi): return [v for v in self.rel if lo <= v < hi]


def rel32(b, va): return va + len(b) + struct.unpack_from("<i", b, len(b) - 4)[0] if False else va + 5 + struct.unpack_from("<i", b, 1)[0]


def wrap_cave(zone, orig_call_disp, flag):
    # header: magic + 6 original site bytes (+pad) ; code at zone+0x10
    code = asm("""
        mov byte ptr [%(f)#x], 1
        call dword ptr [ecx+%(disp)#x]
        mov byte ptr [%(f)#x], 0
        ret
    """ % {"f": flag, "disp": orig_call_disp}, zone + 0x10)
    return code


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dll", default=game_file("AoWEPACK.dll")); ap.add_argument("--tc", default=game_file("AoWTCPCK.dll"))
    ap.add_argument("--exe", default=game_file("AoWx.exe"))
    a = ap.parse_args()
    E, T, X = Img(a.dll), Img(a.tc), Img(a.exe)

    # ---- wrap sites (TC + EXE) ----
    WR = [("TC", T, 0x42349B, 0x444400, bytes.fromhex("ff91a8000000"), 0xA8),
          ("EXE", X, 0x455D4F, 0x60EF80, bytes.fromhex("ff9148010000"), 0x148)]
    # ---- AoWEPACK filter caves in front of Static Shield's t1/t2 ----
    EZ = 0x5586E000
    TSITES = [("t1", 0x5574FD98), ("t2", 0x5577F612)]

    st = {}
    for nm, im, site, zone, orig, disp in WR:
        cur = im.rd(site, 6); hdr = im.rd(zone, 4)
        if cur == orig and hdr == b"\0\0\0\0": st[nm] = "vanilla"
        elif cur[0] == 0xE8 and rel32(cur, site) == zone + 0x10 and hdr == TOK: st[nm] = "ours"
        else: st[nm] = "OTHER(%s)" % cur.hex()
        assert not [r for r in im.relocs(site, site + 6)], (nm, "reloc under site")
        assert not im.relocs(zone, zone + 0x40), (nm, "reloc in zone")
    ehdr = E.rd(EZ, 4)
    tstate = {}
    for nm, site in TSITES:
        cur = E.rd(site, 5); assert cur[0] == 0xE9, (nm, cur.hex())
        tgt = rel32(cur, site)
        tstate[nm] = (tgt, "ours" if ehdr == TOK and EZ <= tgt < EZ + 0x800 else "chain")
    assert not E.relocs(EZ, EZ + 0x100)
    print("sites:", st, "| AoWEPACK t1/t2:", {k: (hex(v[0]), v[1]) for k, v in tstate.items()})

    if a.revert:
        if all(v == "vanilla" for v in st.values()) and all(v[1] == "chain" for v in tstate.values()): print("already reverted"); return 0
        assert all(v in ("ours", "vanilla") for v in st.values()), "something chained in front - inspect first"
        for nm, im, site, zone, orig, disp in WR:
            if st[nm] == "ours":
                im.wr(site, orig); im.wr(zone, b"\0" * 0x40)
        # AoWEPACK: restore the site jmps from the zone header, zero the zone
        for k, (nm, site) in enumerate(TSITES):
            if tstate[nm][1] == "ours":
                prev = struct.unpack_from("<I", E.rd(EZ + 4 + 4 * k, 4))[0]
                E.wr(site, b"\xE9" + struct.pack("<i", prev - (site + 5)))
        E.wr(EZ, b"\0" * 0x100)
        for im in (E, T, X): open(im.path, "wb").write(im.d)
        print("reverted"); return 0

    if all(v == "ours" for v in st.values()) and all(v[1] == "ours" for v in tstate.values()): print("already applied"); return 0
    assert all(v == "vanilla" for v in st.values()) and all(v[1] == "chain" for v in tstate.values()), "mixed state - inspect"

    # build AoWEPACK filter caves
    out = bytearray(TOK + b"".join(struct.pack("<I", tstate[nm][0]) for nm, _ in TSITES)); where = {}
    for nm, site in TSITES:
        ss = tstate[nm][0]; h = E.rd(ss, 7); assert h[:3] == b"\xeb\x05\xe9", (nm, "Static Shield cave header?", h.hex())
        behind = ss + 7 + struct.unpack_from("<i", h, 3)[0]
        while len(out) % 16: out.append(0)
        va = EZ + len(out); where[nm] = va
        tests = "\n".join("cmp esi, %#x\n je hide" % i for i in IMPLIED)
        b = asm("""
            jmp body
            jmp %(ss)#x
        body:
            cmp byte ptr [%(f)#x], 0
            je pass
            %(tests)s
        pass:
            jmp %(ss)#x
        hide:
            jmp %(behind)#x
        """ % {"ss": ss, "f": FLAG, "tests": tests, "behind": behind}, va)
        assert b[:3] == b"\xeb\x05\xe9"
        out += b
        print("  %s: site %#x -> filter %#x -> Static Shield %#x (behind it %#x)" % (nm, site, va, ss, behind))
    assert len(out) <= 0x100
    for nm, im, site, zone, orig, disp in WR:
        code = wrap_cave(zone, disp, FLAG)
        print("  %s: site %#x -> wrap %#x (%d B)" % (nm, site, zone + 0x10, len(code)))
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0

    for im, suf in ((E, "AoWEPACK.dll"), (T, "AoWTCPCK.dll"), (X, "AoWx.exe")):
        if os.path.abspath(im.path) == os.path.abspath(game_file(suf)):
            b = bak_path(im.path, SUF)
            if not os.path.exists(b): shutil.copy2(im.path, b); print("backup ->", b)
    E.wr(EZ, bytes(out))
    for nm, site in TSITES:
        E.wr(site, b"\xE9" + struct.pack("<i", where[nm] - (site + 5)))
    for nm, im, site, zone, orig, disp in WR:
        im.wr(zone, TOK + orig + b"\0" * 6); im.wr(zone + 0x10, wrap_cave(zone, disp, FLAG))
        im.wr(site, b"\xE8" + struct.pack("<i", zone + 0x10 - (site + 5)) + b"\x90")
    for im in (E, T, X): open(im.path, "wb").write(im.d)
    print("Written."); return 0


if __name__ == "__main__":
    sys.exit(main())
