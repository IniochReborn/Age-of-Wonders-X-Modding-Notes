#!/usr/bin/env python3
r"""
Ranged-ability popup shows base ATK / DMG with the unit-window icons + the damage types (2026-10-30).

User: below the description of every ranged damage ability (Archery, Black Bolts, ...) show the ATK and DMG icons with
those stats, and below that the damage types (Physical, Magic, Cold, ...).  BASE values only - no Marksmanship etc.

Where the text comes from: right-clicking an ability (unit window, combat panel, ... - 7 callers) runs
TInfoBanner.ShowInfo 0x40701C(banner, name, ability.Description) - Description = the TStrings at [ability+0x10].
TInfoBanner = HeaderLbl (+0x44) + InfoMemo (+0x48, TAOWMemo, Age8, ItemHeight 10, taCenter) + scrollbar; text only.

1. AoWx.exe  0x407040 (`mov eax,esi / mov ecx,[eax] / call [ecx+0x1C]` = Description.GetTextStr -> [ebp-4], 7 B)
   -> jmp cave (.xtut 0x638910).  The cave runs the original call, then finds the ability whose [+0x10] is this
   TStrings (TAbilityControl [AoWHSSet+0x80] -> TList [+8]: items [+4], count [+8]) and walks its class chain
   (VMT-0x20 name, VMT-0x18 parent slot) for 'TRangedAttackAbility' (TBolts/TBreath/TFlameThrowing descend from it).
   Ranged -> appends   CRLF  #1 <IntGfxMod.UnitIcons ptr, 8 hex> <ATK> #2 <DMG>  CRLF CRLF  <types joined ', ' with ' & ' before the last> Damage
   ATK = byte [ab+0x2A], DMG = byte [ab+0x29] (+0x28 = range, +0x2D = shots), types = word [ab+0x2B] (raw fields: GetAttackRA/GetDamageRA add the
   Marksmanship-style bonuses, these do not).  Types: Physical 0x80, Magic 8, Fire 1, Cold 2, Lightning 4,
   Poison 0x10, Death 0x20, Holy 0x40, Wall 0x100 (hurts walls).
   UnitIcons = [[0x45B03C] (IntGfxMod) + 0x80] - the TImageLibrary the unit window's UAttackIcon (img 0) and
   UDamageIcon (img 2) draw from (15x17).
2. aowInt.dpl  TAOWMemo.Draw centred-line text call @0x598198A6 (`call TImageLibraryFont.SetText`) -> cave
   0x59824410.  A line starting with #1 is drawn as  [ATK icon] atk   [DMG icon] dmg  centred on the line's
   original centre; the icons span the marker line + the blank line under it (2 x ItemHeight), numbers centred in
   that band.  Every other line jumps straight to SetText.  Images via TCustomImageLibrary.Get + TLibraryImage.
   ShowClipped with Draw's clip context, so scrolling clips them like text.  PIC (rel32 only).

Zones: AoWx.exe .xtut 0x638900..0x638C00 ('RAS1' + original bytes), aowInt 0x59824400..0x59824600 ('RAS1').
Dry-run default; --apply / --revert.  Backups <game>\backup\AoWx.exe.bak_rangedstats, aowInt.dpl.bak_rangedstats.
"""
import os, shutil, struct, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

MAGIC = b"RAS1"

# ---- AoWx.exe ----
EXE = game_file("AoWx.exe")
EXE_BASE = 0x400000
E_SITE, E_ORIG = 0x407040, bytes.fromhex("8bc68b08ff511c")
E_RET = 0x407047
E_ZONE, E_ZONE_END = 0x638900, 0x638C00
E_CODE = E_ZONE + 0x10
E_NAMES = E_ZONE + 0x240
TYPES = [(0x80, "Physical"), (0x08, "Magic"), (0x01, "Fire"), (0x02, "Cold"), (0x04, "Lightning"),
         (0x10, "Poison"), (0x20, "Death"), (0x40, "Holy"), (0x100, "Wall")]

E_SRC = """
    mov  eax, esi
    mov  ecx, dword ptr [eax]
    call dword ptr [ecx + 0x1C]
    pushad
    mov  eax, dword ptr [0x45DF78]
    mov  eax, dword ptr [eax]
    test eax, eax
    jz   out
    mov  eax, dword ptr [eax + 0x80]
    test eax, eax
    jz   out
    mov  eax, dword ptr [eax + 8]
    test eax, eax
    jz   out
    mov  ecx, dword ptr [eax + 8]
    mov  edx, dword ptr [eax + 4]
find:
    dec  ecx
    js   out
    mov  ebx, dword ptr [edx + ecx*4]
    test ebx, ebx
    jz   find
    cmp  dword ptr [ebx + 0x10], esi
    jne  find
    mov  eax, dword ptr [ebx]
    mov  ecx, 6
cls:
    mov  edx, dword ptr [eax - 0x20]
    cmp  byte ptr [edx], 20
    jne  nxt
    cmp  dword ptr [edx + 1], 0x6E615254
    jne  nxt
    cmp  dword ptr [edx + 5], 0x41646567
    jne  nxt
    cmp  dword ptr [edx + 9], 0x63617474
    jne  nxt
    cmp  dword ptr [edx + 13], 0x6962416B
    jne  nxt
    cmp  dword ptr [edx + 17], 0x7974696C
    je   ranged
nxt:
    mov  eax, dword ptr [eax - 0x18]
    test eax, eax
    jz   out
    mov  eax, dword ptr [eax]
    dec  ecx
    jnz  cls
    jmp  out
ranged:
    mov  eax, dword ptr [0x45B03C]
    test eax, eax
    jz   out
    mov  eax, dword ptr [eax + 0x80]
    test eax, eax
    jz   out
    sub  esp, 0x108
    mov  dword ptr [esp + 0x104], 0
    lea  edi, [esp + 1]
    mov  word ptr [edi], 0x0A0D
    mov  byte ptr [edi + 2], 1
    add  edi, 3
    mov  ecx, 8
hx:
    rol  eax, 4
    mov  edx, eax
    and  edx, 0xF
    cmp  dl, 10
    jb   hxd
    add  dl, 7
hxd:
    add  dl, 0x30
    mov  byte ptr [edi], dl
    inc  edi
    dec  ecx
    jnz  hx
    movzx eax, byte ptr [ebx + 0x2A]
    call dec3
    mov  byte ptr [edi], 2
    inc  edi
    movzx eax, byte ptr [ebx + 0x29]
    call dec3
    movzx edx, word ptr [ebx + 0x2B]
    test edx, edx
    jz   tydone
    mov  dword ptr [edi], 0x0A0D0A0D
    add  edi, 4
    mov  esi, %(names)s
    xor  ebx, ebx
cnt:
    movzx eax, word ptr [esi]
    test eax, eax
    jz   cntd
    test edx, eax
    jz   cntn
    inc  ebx
cntn:
    add  esi, 16
    jmp  cnt
cntd:
    mov  dword ptr [esp + 0x100], ebx
    mov  esi, %(names)s
    xor  ebx, ebx
ty:
    movzx eax, word ptr [esi]
    test eax, eax
    jz   tyend
    test edx, eax
    jz   tynext
    test ebx, ebx
    jz   tyfirst
    lea  eax, [ebx + 1]
    cmp  eax, dword ptr [esp + 0x100]
    je   amp
    mov  word ptr [edi], 0x202C
    add  edi, 2
    jmp  tyfirst
amp:
    mov  word ptr [edi], 0x2620
    mov  byte ptr [edi + 2], 0x20
    add  edi, 3
tyfirst:
    inc  ebx
    movzx ecx, byte ptr [esi + 2]
    push esi
    add  esi, 3
    rep  movsb
    pop  esi
tynext:
    add  esi, 16
    jmp  ty
tyend:
    test ebx, ebx
    jz   tydone
    mov  dword ptr [edi], 0x6D614420
    mov  dword ptr [edi + 4], 0x00656761
    add  edi, 7
tydone:
    lea  eax, [esp + 1]
    sub  edi, eax
    mov  eax, edi
    mov  byte ptr [esp], al
    lea  eax, [esp + 0x104]
    mov  edx, esp
    call 0x401100
    lea  eax, [ebp - 4]
    mov  edx, dword ptr [esp + 0x104]
    call 0x401118
    lea  eax, [esp + 0x104]
    call 0x4010D8
    add  esp, 0x108
out:
    popad
    jmp  %(ret)s
dec3:
    cmp  eax, 100
    jb   d2
    xor  edx, edx
    mov  ecx, 100
    div  ecx
    add  al, 0x30
    mov  byte ptr [edi], al
    inc  edi
    mov  eax, edx
    jmp  d2f
d2:
    cmp  eax, 10
    jb   d1
d2f:
    xor  edx, edx
    mov  ecx, 10
    div  ecx
    add  al, 0x30
    mov  byte ptr [edi], al
    inc  edi
    mov  eax, edx
d1:
    add  al, 0x30
    mov  byte ptr [edi], al
    inc  edi
    ret
""" % {"names": hex(E_NAMES), "ret": hex(E_RET)}

# ---- aowInt.dpl ----
DPL = game_file("aowInt.dpl")
DPL_BASE = 0x59800000
A_SITE = 0x598198A6                    # TAOWMemo.Draw, taCenter branch: call TImageLibraryFont.SetText
SETTEXT = 0x59801894                   # thunk ILPACK TImageLibraryFont.SetText(font, x, y; [esp+4]=ctx, [esp+8]=str)
GETTEXTW = 0x59801884                  # thunk TImageLibraryFont.GetTextWidth(font, str)
ILGET = 0x598018D4                     # thunk TCustomImageLibrary.Get(lib, idx) -> image (+0x20 w, +0x24 h)
SHOWCLIP = 0x59801864                  # thunk TLibraryImage.ShowClipped(img, x, y; [esp+4]=ctx)
A_ZONE, A_ZONE_END = 0x59824400, 0x59824600
A_CODE = A_ZONE + 0x10
A_ORIG = b"\xe8" + struct.pack("<i", SETTEXT - (A_SITE + 5))

A_SRC = """
    push ebx
    push esi
    push edi
    push ebp
    mov  esi, dword ptr [esp + 0x18]
    test esi, esi
    jz   pass
    cmp  byte ptr [esi], 1
    jne  pass
    cmp  dword ptr [esi - 4], 9
    jl   pass
    mov  edi, ebp
    mov  ebp, esp
    sub  esp, 0x80
    mov  dword ptr [ebp - 4], eax
    mov  dword ptr [ebp - 8], edx
    mov  dword ptr [ebp - 0xC], ecx
    mov  dword ptr [ebp - 0x2C], edi
    xor  ebx, ebx
    mov  ecx, 8
    lea  edi, [esi + 1]
hx:
    shl  ebx, 4
    movzx eax, byte ptr [edi]
    sub  eax, 0x30
    cmp  eax, 9
    jbe  hd
    sub  eax, 7
hd:
    and  eax, 0xF
    or   ebx, eax
    inc  edi
    dec  ecx
    jnz  hx
    mov  dword ptr [ebp - 0x10], ebx
    test ebx, ebx
    jz   rpass
    mov  ecx, dword ptr [esi - 4]
    lea  edx, [esi + ecx]
    lea  ebx, [ebp - 0x48]
    xor  ecx, ecx
c1:
    cmp  edi, edx
    jae  c1e
    mov  al, byte ptr [edi]
    inc  edi
    cmp  al, 2
    je   c1e
    cmp  ecx, 12
    jae  c1
    mov  byte ptr [ebx + ecx], al
    inc  ecx
    jmp  c1
c1e:
    mov  byte ptr [ebx + ecx], 0
    mov  dword ptr [ebp - 0x4C], ecx
    mov  dword ptr [ebp - 0x50], -1
    lea  ebx, [ebp - 0x70]
    xor  ecx, ecx
c2:
    cmp  edi, edx
    jae  c2e
    mov  al, byte ptr [edi]
    inc  edi
    cmp  ecx, 12
    jae  c2
    mov  byte ptr [ebx + ecx], al
    inc  ecx
    jmp  c2
c2e:
    mov  byte ptr [ebx + ecx], 0
    mov  dword ptr [ebp - 0x74], ecx
    mov  dword ptr [ebp - 0x78], -1
    mov  eax, dword ptr [ebp - 0x10]
    xor  edx, edx
    call %(ilget)s
    mov  dword ptr [ebp - 0x20], eax
    test eax, eax
    jz   rpass
    mov  eax, dword ptr [ebp - 0x10]
    mov  edx, 2
    call %(ilget)s
    mov  dword ptr [ebp - 0x24], eax
    test eax, eax
    jz   rpass
    mov  eax, dword ptr [ebp - 4]
    mov  edx, esi
    call %(gtw)s
    sar  eax, 1
    add  dword ptr [ebp - 8], eax
    mov  eax, dword ptr [ebp - 4]
    lea  edx, [ebp - 0x48]
    call %(gtw)s
    mov  dword ptr [ebp - 0x18], eax
    mov  eax, dword ptr [ebp - 4]
    lea  edx, [ebp - 0x70]
    call %(gtw)s
    mov  dword ptr [ebp - 0x1C], eax
    mov  eax, dword ptr [ebp - 0x2C]
    mov  eax, dword ptr [eax - 4]
    mov  eax, dword ptr [eax + 0x164]
    mov  dword ptr [ebp - 0x28], eax
    mov  eax, dword ptr [ebp - 0x20]
    mov  ebx, dword ptr [eax + 0x20]
    add  ebx, dword ptr [ebp - 0x18]
    mov  eax, dword ptr [ebp - 0x24]
    add  ebx, dword ptr [eax + 0x20]
    add  ebx, dword ptr [ebp - 0x1C]
    add  ebx, 14
    sar  ebx, 1
    mov  eax, dword ptr [ebp - 8]
    sub  eax, ebx
    mov  dword ptr [ebp - 0x14], eax
    mov  edi, dword ptr [ebp - 0x20]
    call icon
    lea  ebx, [ebp - 0x48]
    call text
    mov  eax, dword ptr [ebp - 0x18]
    add  eax, 10
    add  dword ptr [ebp - 0x14], eax
    mov  edi, dword ptr [ebp - 0x24]
    call icon
    lea  ebx, [ebp - 0x70]
    call text
    mov  esp, ebp
    pop  ebp
    pop  edi
    pop  esi
    pop  ebx
    ret  8
rpass:
    mov  eax, dword ptr [ebp - 4]
    mov  edx, dword ptr [ebp - 8]
    mov  ecx, dword ptr [ebp - 0xC]
    mov  esp, ebp
pass:
    pop  ebp
    pop  edi
    pop  esi
    pop  ebx
    jmp  %(settext)s
icon:
    mov  eax, dword ptr [ebp - 0x28]
    add  eax, eax
    sub  eax, dword ptr [edi + 0x24]
    sar  eax, 1
    add  eax, dword ptr [ebp - 0xC]
    mov  ecx, eax
    push dword ptr [ebp + 0x14]
    mov  edx, dword ptr [ebp - 0x14]
    mov  eax, edi
    call %(show)s
    mov  eax, dword ptr [edi + 0x20]
    add  eax, 2
    add  dword ptr [ebp - 0x14], eax
    ret
text:
    push ebx
    push dword ptr [ebp + 0x14]
    mov  eax, dword ptr [ebp - 4]
    mov  edx, dword ptr [ebp - 0x14]
    mov  ecx, dword ptr [ebp - 0x28]
    sar  ecx, 1
    add  ecx, dword ptr [ebp - 0xC]
    call %(settext)s
    ret
""" % {"ilget": hex(ILGET), "gtw": hex(GETTEXTW), "settext": hex(SETTEXT), "show": hex(SHOWCLIP)}


def asm(src, at):
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    return bytes(Ks(KS_ARCH_X86, KS_MODE_32).asm(src, at)[0])


def exe_zone():
    z = bytearray(E_ZONE_END - E_ZONE)
    z[0:4] = MAGIC
    z[4:4 + len(E_ORIG)] = E_ORIG
    code = asm(E_SRC, E_CODE)
    assert 0x10 + len(code) <= E_NAMES - E_ZONE, hex(len(code))
    z[0x10:0x10 + len(code)] = code
    p = E_NAMES - E_ZONE
    for mask, name in TYPES:
        struct.pack_into("<HB", z, p, mask, len(name)); z[p + 3:p + 3 + len(name)] = name.encode(); p += 16
    return bytes(z)                         # terminator = the zero record after the table


def dpl_zone():
    z = bytearray(A_ZONE_END - A_ZONE)
    z[0:4] = MAGIC
    z[4:9] = A_ORIG
    code = asm(A_SRC, A_CODE)
    assert 0x10 + len(code) <= len(z), hex(len(code))
    z[0x10:0x10 + len(code)] = code
    return bytes(z)


def reloc_targets(pe, base):
    out = set()
    if hasattr(pe, "DIRECTORY_ENTRY_BASERELOC"):
        for blk in pe.DIRECTORY_ENTRY_BASERELOC:
            for e in blk.entries:
                if e.type == 3:
                    out.add(base + e.rva)
    return out


def game_running():
    try:
        r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq AoWx.exe"], capture_output=True, text=True)
        return "AoWx.exe" in r.stdout
    except Exception:
        return False


def main():
    import pefile
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    plan = []
    for path, base, site, orig_site, hook_site, zone_va, zone_end, zone in (
            (EXE, EXE_BASE, E_SITE, E_ORIG, b"\xe9" + struct.pack("<i", E_CODE - (E_SITE + 5)) + b"\x90\x90",
             E_ZONE, E_ZONE_END, exe_zone()),
            (DPL, DPL_BASE, A_SITE, A_ORIG, b"\xe8" + struct.pack("<i", A_CODE - (A_SITE + 5)),
             A_ZONE, A_ZONE_END, dpl_zone())):
        d = open(path, "rb").read()
        pe = pefile.PE(data=d)
        if path == EXE:
            assert pe.OPTIONAL_HEADER.DllCharacteristics & 0x40 == 0, "AoWx.exe became DYNAMIC_BASE"
        off = lambda va: pe.get_offset_from_rva(va - base)  # noqa: E731
        so, zo = off(site), off(zone_va)
        cur_site = d[so:so + len(orig_site)]
        cur_zone = d[zo:zo + (zone_end - zone_va)]
        rl = reloc_targets(pe, base)
        bad = [hex(r) for r in rl if site - 3 <= r < site + len(orig_site) or zone_va - 3 <= r < zone_end]
        if cur_site == orig_site and not any(cur_zone):
            st = "vanilla"
        elif cur_site == hook_site and cur_zone == zone:
            st = "ours"
        else:
            st = "OTHER"
        name = os.path.basename(path)
        print("%-10s site %#x %s | zone %#x %s | code %d B | relocs in range: %s"
              % (name, site, cur_site.hex(), zone_va, "zero" if not any(cur_zone) else cur_zone[:4],
                 len(zone.rstrip(b"\0")), bad or "none"))
        print("           state: %s" % st)
        if st == "OTHER" or bad:
            print("ABORT"); return 1
        plan.append((path, so, zo, orig_site, hook_site, zone, st))
    want = "vanilla" if revert else "ours"
    if all(p[6] == want for p in plan):
        print("already %s" % ("reverted" if revert else "applied")); return 0
    if not apply and not revert:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if game_running():
        print("AoWx.exe is running - close the game first"); return 1
    for path, so, zo, orig_site, hook_site, zone, st in plan:
        if st == want:
            continue
        bak = bak_path(path, ".bak_rangedstats")
        if not revert and not os.path.exists(bak):
            shutil.copy2(path, bak); print("backup ->", bak)
        new_site, new_zone = (orig_site, bytes(len(zone))) if revert else (hook_site, zone)
        try:
            with open(path, "r+b") as f:             # in-place (house rule)
                f.seek(zo); f.write(new_zone)
                f.seek(so); f.write(new_site)
        except PermissionError:
            print("LOCKED - close the game/editor and retry"); return 1
        d2 = open(path, "rb").read()
        assert d2[so:so + len(new_site)] == new_site and d2[zo:zo + len(new_zone)] == new_zone
        print("%s %s" % (os.path.basename(path), "reverted" if revert else "written and verified"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
