#!/usr/bin/env python3
r"""
AoWx.exe unit window: 3-digit casting points ("100/100") in CONDENSED AoW15WhiteGrey digits (Channeler, v2 2026-10-18).

v1 (patch_exe_channeler_label_v1.py) switched the Mana label to Age10s for >= 6-char text - the user: "the font is too
different, it looks janky".  v2 keeps the label's own font (FontModule.AoW15WhiteGrey = Int\Fonts\Age15WhGr.ILB) and
instead maps the digits / slash of the text to the condensed copies of that font's glyphs that
patch_font_age15_condensed_digits_v1.py adds at control-byte ids ('0'..'9' -> 0x10..0x19, '/' -> 0x1A): same art,
colour, height and shadow, 1-2 px narrower per glyph -> "100/100" 59 px -> 48 px, fits the 51 px panel (UStatP2).

Label: TUnitWindow +0x70 ("Mana"; centred, AoW15WhiteGrey, CharacterDistance 0), text built at 0x4087C4..0x40881C as
IntToStr(cur) + "/" + IntToStr(max) by LStrCatN into the local [ebp-8] (a fresh string, refcount 1), then
`call TAOWLabel.SetGText` @0x408824 (hooked by v1 -> cave 0x634410, same address in v2, so the site is unchanged).
Cave: text length >= 6 (any 3-digit value), label font == FontModule.AoW15WhiteGrey ([[0x45A210]]+0x5C) and the string
is unshared ([s-8] == 1) -> rewrite '0'..'9' / '/' in place to 0x10..0x1A; anything else passes through untouched.
Then jmp SetGText.  No font switch / y shift any more (v1's Age10s TopOffset +2 is gone with it - fresh state per run).
The font's width = image w + CharacterDistance, so TAOWLabel's centring uses the condensed widths automatically.
ImageLib.ParseFontText only treats 0x0A / 0x0D / 0x20 specially; TAOWLabel.SetGText/Draw do no trimming.

Code: .xtut +0x400..+0x800 (0x634400, header 'CHL2' + original call bytes + .xtut raw size before us), the same zone as
v1 - an applied v1 is UPGRADED IN PLACE (header 'CHL1' -> 'CHL2', code rewritten, its saved raw size kept).
v1's script refuses a v2 zone (DIFFERS) - revert with this script.  --revert restores vanilla (site call, zone zeroed,
.xtut raw shrunk back) = exactly what v1's --revert gives.
ORDER: patch_font_age15_condensed_digits_v1.py --apply FIRST (this script refuses without its glyphs); revert this
before reverting the font script and before patch_title_tutorial_confirm_v1.py (its revert truncates .xtut).
Dry-run default; --apply / --revert / --dis; --exe <scratch copy>; --ilb <font ILB>.  Backup backup\AoWx.exe.bak_chlabel2.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file, game_dir

DEFAULT_EXE = game_file("AoWx.exe")
BAK_SUFFIX = ".bak_chlabel2"
BASE = 0x400000
SEC_NAME, SEC_VA = b".xtut", 0x634000
ZONE, ZONE_END = 0x634400, 0x634800
MAGIC, MAGIC_V1 = b"CHL2", b"CHL1"
SITE, SITE_ORIG = 0x408824, bytes.fromhex("e82baaffff")
SETGTEXT = 0x403254
FONTMOD_VAR = 0x45A210
F_BIG = 0x5C                                 # TFontModule.AoW15WhiteGrey
MINLEN = 6
CID0, CSLASH = 0x10, 0x1A                    # condensed '0' / '/' ids (patch_font_age15_condensed_digits_v1.py)
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
        test esi, esi
        je lpass
        mov ecx, dword ptr [%(fm)#x]
        test ecx, ecx
        je lpass
        mov ecx, dword ptr [ecx]
        test ecx, ecx
        je lpass
        mov eax, dword ptr [ecx + %(big)#x]
        test eax, eax
        je lpass
        cmp dword ptr [ebx + 0x8c], eax
        jne lpass
        mov ecx, dword ptr [esi - 4]
        cmp ecx, %(minlen)d
        jl lpass
        cmp dword ptr [esi - 8], 1
        jne lpass
        xor edi, edi
    lloop:
        mov al, byte ptr [esi + edi]
        cmp al, 0x2f
        jne lnum
        mov byte ptr [esi + edi], %(cs)#x
        jmp lnext
    lnum:
        sub al, 0x30
        cmp al, 9
        ja lnext
        add al, %(c0)#x
        mov byte ptr [esi + edi], al
    lnext:
        inc edi
        cmp edi, ecx
        jl lloop
    lpass:
        mov eax, ebx
        mov edx, esi
        pop edi
        pop esi
        pop ebx
        jmp %(setg)#x
    """ % {"fm": FONTMOD_VAR, "big": F_BIG, "minlen": MINLEN, "cs": CSLASH, "c0": CID0, "setg": SETGTEXT}, code_va)
    return code_va, code


def v1_blob(orig_rsz):
    """the exact zone bytes patch_exe_channeler_label_v1.py writes (for the in-place upgrade check)"""
    import patch_exe_channeler_label_v1 as V1
    b = bytearray(0x10); b[0:4] = MAGIC_V1; b[4:9] = SITE_ORIG
    struct.pack_into("<I", b, 0x0C, orig_rsz)
    return bytes(b) + V1.build()[1]


def font_ready(path):
    import patch_font_age15_condensed_digits_v1 as F
    return F.build(open(path, "rb").read())[0] == "APPLIED"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=DEFAULT_EXE)
    ap.add_argument("--ilb", default=os.path.join(game_dir(), "Int", "Fonts", "Age15WhGr.ILB"))
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
    hdr_ours = zl[:4] in (MAGIC, MAGIC_V1)
    orig_rsz = struct.unpack_from("<I", zl, 0x0C)[0] if hdr_ours else sec["rsz"]
    blob = bytearray(0x10); blob[0:4] = MAGIC; blob[4:9] = SITE_ORIG
    struct.pack_into("<I", blob, 0x0C, orig_rsz)
    blob = bytes(blob) + code
    v1 = v1_blob(orig_rsz)
    st_site = "ours" if cur_site == hooked else "orig" if cur_site == SITE_ORIG else "OTHER"
    if not any(zl):
        zstate = "zero"
    elif zl[:len(blob)] == blob and not any(zl[len(blob):]):
        zstate = "v2"
    elif zl[:len(v1)] == v1 and not any(zl[len(v1):]):
        zstate = "v1"
    else:
        zstate = "DIFFERS"
    print("%s\n  SetGText call @%#x: %s | .xtut raw %#x (last section: %s) | zone %#x: %s (v2 %d B)"
          % (a.exe, SITE, st_site, sec["rsz"], last, ZONE, zstate, len(blob)))
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        for i in md.disasm(code, code_va): print("   %08X  %-24s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if st_site == "OTHER" or zstate == "DIFFERS" or (st_site == "orig") != (zstate == "zero"):
        print("ABORT: unexpected site/zone combination"); return 1
    if a.revert:
        if st_site == "orig": print("nothing to revert"); return 0
        d[site_o:site_o + 5] = SITE_ORIG
        if have: d[zo:zo + have] = bytes(have)
        if last and orig_rsz < sec["rsz"] and not any(d[sec["raw"] + orig_rsz:sec["raw"] + sec["rsz"]]) \
                and len(d) == sec["raw"] + sec["rsz"]:
            del d[sec["raw"] + orig_rsz:]
            struct.pack_into("<I", d, sec["hdr"] + 16, orig_rsz)
            print("  .xtut raw shrunk back to %#x" % orig_rsz)
        open(a.exe, "wb").write(d); print("reverted to vanilla (was %s)" % zstate); return 0
    if zstate == "v2": print("already applied"); return 0
    if not font_ready(a.ilb):
        print("ABORT: %s lacks the condensed digits - run patch_font_age15_condensed_digits_v1.py --apply first" % a.ilb)
        return 1
    if zstate == "v1": print("  upgrading v1 -> v2 in place")
    need = ZONE_END - SEC_VA
    if sec["rsz"] < need:
        if not last or len(d) != sec["raw"] + sec["rsz"]:
            print("ABORT: .xtut must be the last section with no overlay to grow it"); return 1
        d += bytes(need - sec["rsz"])
        struct.pack_into("<I", d, sec["hdr"] + 16, need)
        print("  .xtut raw grown %#x -> %#x" % (sec["rsz"], need))
        zo = sec["raw"] + (ZONE - SEC_VA)
    d[zo:zo + (ZONE_END - ZONE)] = bytes(ZONE_END - ZONE)
    d[zo:zo + len(blob)] = blob
    d[site_o:site_o + 5] = hooked
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if os.path.abspath(a.exe) == os.path.abspath(DEFAULT_EXE):
        bak = bak_path(a.exe, BAK_SUFFIX)
        if not os.path.exists(bak): shutil.copy2(a.exe, bak); print("backup ->", bak)
    open(a.exe, "wb").write(d)
    assert open(a.exe, "rb").read() == bytes(d)
    print("Written and verified: unit window casting points use condensed AoW15WhiteGrey digits for 3-digit values.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
