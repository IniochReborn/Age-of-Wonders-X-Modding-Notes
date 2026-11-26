#!/usr/bin/env python3
r"""
AoWx.exe unit window: 3-digit casting points ("100/100") in a smaller font (Channeler, 2026-10-18).

With Channeler III a Spell Casting V hero has 100 max casting points.  The unit window's "Mana" label
(TUnitWindow +0x70, DFM: parent UStatP2 = 51 px wide, Alignment awCenter / ahTop TopOffset 68, AOWFont
FontModule.AoW15WhiteGrey (Int\Fonts\Age15WhGr.ILB, CharacterDistance 0, digits 6-10 px)) is filled by
0x4087C4..0x408824: IntToStr(cur) + "/" + IntToStr(max) -> TAOWLabel.SetGText (thunk 0x403254).  "50/50" = 43 px;
"100/100" = 59 px would run past the panel (into the ManaIcon on the left / the window frame on the right).

Fix: hook the `call 0x403254` @0x408824 (5 B) -> cave lbl (eax = label, edx = text): text length >= 6 (any 3-digit
value) -> AOWFont := FontModule.Age10s (+0x50; the font of the window's UnitName / MoraleLbl; 6 px digits +
1 px CharacterDistance -> "100/100" = 47 px, fits the 51 px panel centred), else back to AoW15WhiteGrey (+0x5C).
The font switch is TAOWLabel.SetGFont inlined ([label+0x8C] := font, [label+0x2C] := 0); it only switches between
those two fonts (a label carrying any other font is left alone).  Age10s digits sit ~2 px higher in the cell than
Age15's, so on the switch Alignment.TopOffset ([[label+0xD4]+0x20]) and the current y ([label+0x88]) move by
DY = 2 (+2 to small, -2 back - always paired, the switch happens only on an actual font change).  Then the
original SetGText.  FontModule = [[0x45A210]] (CreateForm(TFontModule) @0x4599F6).  AoWx.exe never rebases.

Code: AoWx.exe section table is FULL -> lives in the LAST section .xtut (patch_title_tutorial_confirm_v1.py) at
+0x400..+0x800 (0x634400; .xtut raw is grown 0x400 -> 0x800 if needed - its virtual size is already 0x1000;
+0x800.. is left for another feature).  Header 'CHL1' + original call bytes + the raw size before us.
LIFO: revert this BEFORE patch_title_tutorial_confirm_v1.py (its revert truncates .xtut).
Not changed: the spellbook's two TBarNumber labels (CurrentPointsLbl / CastingPointsMaxLbl, Age10tb, left-aligned:
"100" is 4 px wider than "50") and the hero-info "...: cur/max" line (free-width text).
Dry-run default; --apply / --revert / --dis; --exe <scratch copy>.  Backup <game>\backup\AoWx.exe.bak_chlabel.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DEFAULT_EXE = game_file("AoWx.exe")
BAK_SUFFIX = ".bak_chlabel"
BASE = 0x400000
SEC_NAME, SEC_VA = b".xtut", 0x634000
ZONE, ZONE_END = 0x634400, 0x634800
MAGIC = b"CHL1"
SITE, SITE_ORIG = 0x408824, bytes.fromhex("e82baaffff")
SETGTEXT = 0x403254
FONTMOD_VAR = 0x45A210
F_SMALL, F_BIG = 0x50, 0x5C                  # TFontModule.Age10s / .AoW15WhiteGrey
DY = 2
MINLEN = 6
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, va):
    return bytes(ks.asm(src, va)[0])


def sections(d):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    n = struct.unpack_from("<H", d, e + 6)[0]; opt = struct.unpack_from("<H", d, e + 20)[0]
    tbl = e + 24 + opt; secs = []
    for i in range(n):
        h = tbl + 40 * i
        vs, va, rs, ro = struct.unpack_from("<IIII", d, h + 8)
        secs.append(dict(name=d[h:h + 8].rstrip(b"\0"), vs=vs, va=va, rsz=rs, raw=ro, hdr=h))
    return e, secs


def off(secs, va):
    for s in secs:
        if s["va"] <= va - BASE < s["va"] + max(s["vs"], s["rsz"]) and va - BASE - s["va"] < s["rsz"]:
            return s["raw"] + va - BASE - s["va"]
    raise ValueError(hex(va))


def build():
    code_va = ZONE + 0x10
    code = asm("""
        push ebx
        push esi
        push edi
        mov ebx, eax
        mov esi, edx
        mov ecx, dword ptr [%(fm)#x]
        test ecx, ecx
        je lpass
        mov ecx, dword ptr [ecx]
        test ecx, ecx
        je lpass
        mov edi, dword ptr [ecx + %(big)#x]
        test esi, esi
        je lhave
        cmp dword ptr [esi - 4], %(minlen)d
        jl lhave
        mov edi, dword ptr [ecx + %(small)#x]
    lhave:
        test edi, edi
        je lpass
        mov eax, dword ptr [ebx + 0x8c]
        cmp eax, edi
        je lpass
        cmp eax, dword ptr [ecx + %(big)#x]
        je lsw
        cmp eax, dword ptr [ecx + %(small)#x]
        jne lpass
    lsw:
        mov dword ptr [ebx + 0x8c], edi
        mov byte ptr [ebx + 0x2c], 0
        mov edx, %(dy)d
        cmp edi, dword ptr [ecx + %(small)#x]
        je ldy
        neg edx
    ldy:
        add dword ptr [ebx + 0x88], edx
        mov eax, dword ptr [ebx + 0xd4]
        test eax, eax
        je lpass
        add dword ptr [eax + 0x20], edx
    lpass:
        mov eax, ebx
        mov edx, esi
        pop edi
        pop esi
        pop ebx
        jmp %(setg)#x
    """ % {"fm": FONTMOD_VAR, "big": F_BIG, "small": F_SMALL, "minlen": MINLEN, "dy": DY, "setg": SETGTEXT}, code_va)
    return code_va, code


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=DEFAULT_EXE)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    d = bytearray(open(a.exe, "rb").read())
    e, secs = sections(d)
    sec = next((s for s in secs if s["name"] == SEC_NAME), None)
    if sec is None:
        print("ABORT: no .xtut section - apply patch_title_tutorial_confirm_v1.py first"); return 1
    last = secs[-1]["name"] == SEC_NAME
    assert sec["va"] == SEC_VA - BASE and sec["vs"] >= ZONE_END - SEC_VA, ".xtut layout unexpected"
    code_va, code = build()
    site_o = off(secs, SITE)
    cur_site = bytes(d[site_o:site_o + 5])
    hooked = b"\xE8" + struct.pack("<i", code_va - (SITE + 5))
    zo = sec["raw"] + (ZONE - SEC_VA)
    have = max(0, min(sec["rsz"] - (ZONE - SEC_VA), ZONE_END - ZONE))
    zl = bytes(d[zo:zo + have]) + bytes((ZONE_END - ZONE) - have)
    blob = bytearray(0x10); blob[0:4] = MAGIC; blob[4:9] = SITE_ORIG
    ours = zl[:4] == MAGIC
    orig_rsz = struct.unpack_from("<I", zl, 0x0C)[0] if ours else sec["rsz"]
    struct.pack_into("<I", blob, 0x0C, orig_rsz)
    blob = bytes(blob) + code
    st_site = "ours" if cur_site == hooked else "orig" if cur_site == SITE_ORIG else "OTHER"
    zstate = "zero" if not any(zl) else "ours" if zl[:len(blob)] == blob and not any(zl[len(blob):]) else "DIFFERS"
    print("%s\n  SetGText call @%#x: %s | .xtut raw %#x (last section: %s) | zone %#x: %s (%d B)"
          % (a.exe, SITE, st_site, sec["rsz"], last, ZONE, zstate, len(blob)))
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        for i in md.disasm(code, code_va): print("   %08X  %-24s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if st_site == "OTHER" or zstate == "DIFFERS":
        print("ABORT"); return 1
    if a.revert:
        if st_site == "orig" and zstate == "zero": print("nothing to revert"); return 0
        d[site_o:site_o + 5] = SITE_ORIG
        if have: d[zo:zo + have] = bytes(have)
        if last and orig_rsz < sec["rsz"] and not any(d[sec["raw"] + orig_rsz:sec["raw"] + sec["rsz"]]) \
                and len(d) == sec["raw"] + sec["rsz"]:
            del d[sec["raw"] + orig_rsz:]
            struct.pack_into("<I", d, sec["hdr"] + 16, orig_rsz)
            print("  .xtut raw shrunk back to %#x" % orig_rsz)
        open(a.exe, "wb").write(d); print("reverted"); return 0
    if st_site == "ours" and zstate == "ours": print("already applied"); return 0
    need = ZONE_END - SEC_VA
    if sec["rsz"] < need:
        if not last or len(d) != sec["raw"] + sec["rsz"]:
            print("ABORT: .xtut must be the last section with no overlay to grow it"); return 1
        d += bytes(need - sec["rsz"])
        struct.pack_into("<I", d, sec["hdr"] + 16, need)
        print("  .xtut raw grown %#x -> %#x" % (sec["rsz"], need))
    d[zo:zo + len(blob)] = blob
    d[site_o:site_o + 5] = hooked
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if os.path.abspath(a.exe) == os.path.abspath(DEFAULT_EXE):
        bak = bak_path(a.exe, BAK_SUFFIX)
        if not os.path.exists(bak): shutil.copy2(a.exe, bak); print("backup ->", bak)
    open(a.exe, "wb").write(d)
    assert open(a.exe, "rb").read() == bytes(d)
    print("Written and verified: unit window casting points switch to Age10s for 3-digit values.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
