#!/usr/bin/env python3
r"""Item-granted Healing round 2: honour the ITEM'S AUTHORED LEVEL and show
leveled names everywhere, including "Healing I/II/III (used)".

Follow-up to build_item_healing_daily.py (user test 2026-08-21):
  - an item authored with Healing III healed only +5 (level I amount)
  - the tactical unit PANEL showed plain "Healing" (no level); the unit
    window showed "Healing III" correctly
  - after use the text never became "Healing III (used)" (vanilla's used
    branch renders base-name + " (used)" with no level - even for innate
    leveled Healing)

CAUSES:
  - cave_healamt @0x5580E6E0 (leveled-healing v1) derives the amount ONLY
    from the healer's OWN THealingAbilityData record ([rec+0xD]); an item
    Healing III record (on the item, found by cave_findrec @0x558124A0) was
    never consulted -> flat 5.
  - the panel calls ability.GetName(strat hero) -> plain branch ->
    GetLevel(hero) [vmt+0x70] which is own-bit-gated -> 0 -> lsnames renders
    the plain name. (The unit window goes through the hero owner-finder and
    asks the ITEM, whose record gives 3.)
  - GetName's used branch @0x5576BFCB is vanilla: name + " (" + T(used) +
    ")" (resourcestring 65450), never leveled.

FIX:
  1. cave_healamt2 @0x558129A0: amount level = max(own record level, item
     record level via cave_findrec) -> 5/7/10. The old cave entry
     0x5580E6E0 becomes `jmp cave_healamt2`, so every existing caller
     (cave_heal/HealUnit, est1, est2 - combat + overland + AI estimates)
     gets the fix without retouching those caves.
  2. cave_gname @0x55812A00 replaces THealingAbility.GetName wholesale
     (VMT+0x58 repoint @file 0x20C14; no direct callers - verified):
       display level = GetLevel(owner) [vmt+0x70]  (item owner -> item rec)
                       max'd with the owner's item record level (hero owner
                       -> item rec; cave_findrec returns nil for non-heroes)
                       clamped to 3; level-0 item record counts as I
       name := cave_lsnames(self, level)          ("Healing"/"Healing I..III")
       used (owner != nil and not GetEnabled)  -> name + " (" + T(used) + ")"
       exactly vanilla's pieces (literals 0x5576C03C " (", 0x5576C048 ")",
       LoadResString rec 0x557069F4 id 65450 -> TranslateRStr 0x557249FC ->
       0x5570156C, _LStrCatN 0x55701198), so localization is preserved.
     Innate leveled Healing improves too: "Healing II (used)" not
     "Healing (used)". Temps are cleared via _LStrArrayClr 0x55701148 (no
     exception frame: these string ops don't raise in practice; vanilla's
     frame only guarded the same calls).

Cave code is position-independent: absolute data (literals, resstring rec)
is addressed via call/pop load-delta; cross-module refs are rel32 or virtual
dispatch. VMT slot keeps its .reloc entry (in-module target).

Caves @0x558129A0..0x55812B00 (zeros verified 0x55812950..0x55812C00).
Dry-run default; --apply / --revert.  Backup: AoWEPACK.dll.bak_itemheallvl
"""
import os, shutil, struct, sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DLL = os.path.join(GAME, "AoWEPACK.dll")
BAK = DLL + ".bak_itemheallvl"
V2F = 0x55700C00

HEAL_ID   = 0x2F
FINDDATA  = 0x5574F1C4      # TAbilityOwner.GetAbilityData
CAVE_FIND = 0x558124A0      # (ecx=id, esi=owner THero/TLeader) -> item rec|nil
LSNAMES   = 0x5580E2A0      # (eax=ability, edx=level, ecx=out) name + " I/II/III"
LOADRES   = 0x55701210      # LoadResString(eax=rec, edx=out)
TRANSLATE = 0x557249FC      # AoWE.TranslateRStr(eax=str, edx=out)
XFORM     = 0x5570156C      # post-translate transform (vanilla GetName uses it)
LSTRCATN  = 0x55701198      # _LStrCatN(eax=dest, edx=count, strings pushed)
LSTRASG   = 0x55701150      # _LStrAsg(eax=dest, edx=src)
LSTRARRCLR= 0x55701148      # _LStrArrayClr(eax=first, edx=count)
RSREC     = 0x557069F4      # resourcestring rec: "used" (id 65450)
LIT_OPEN  = 0x5576C03C      # " ("
LIT_CLOSE = 0x5576C048      # ")"

OLD_HEALAMT = 0x5580E6E0    # leveled-healing v1 cave_healamt entry
OLD_HA_BYTES = bytes.fromhex("515285c074")   # push ecx; push edx; test eax,eax; je+0x20

CAVE_HEALAMT2 = 0x558129A0
CAVE_GNAME    = 0x55812A00
CAVE_END      = 0x55812B00

GNAME_SLOT_FOFF = 0x20C14   # THealingAbility VMT+0x58 (true base 0x557217BC)
GNAME_OLD       = 0x5576BF90


class Asm:
    def __init__(self, base):
        self.base = base; self.buf = bytearray(); self.labels = {}; self.j8 = []
    def here(self): return self.base + len(self.buf)
    def db(self, *b): self.buf += bytes(b)
    def dd(self, v): self.buf += struct.pack("<I", v & 0xFFFFFFFF)
    def call(self, t):
        self.db(0xE8); self.buf += struct.pack("<i", t - (self.here() + 4))
    def lab(self, n): self.labels[n] = len(self.buf)
    def jcc8(self, op, n): self.db(op); self.j8.append((len(self.buf), n)); self.db(0)
    def fin(self, limit):
        for off, n in self.j8:
            dlt = self.labels[n] - (off + 1)
            assert -128 <= dlt <= 127, (n, dlt)
            self.buf[off] = dlt & 0xFF
        assert self.base + len(self.buf) <= limit, (hex(self.base), len(self.buf))
        return bytes(self.buf)


def build_healamt2():
    """(eax = healer strat unit | nil) -> eax = 5/7/10.
    Level = max(own record level, item record level). Preserves ecx/edx/esi
    (+ ebx/edi/ebp via callee contracts) like v1 healamt did."""
    a = Asm(CAVE_HEALAMT2)
    a.db(0x51, 0x52, 0x56)              # push ecx; push edx; push esi
    a.db(0x85, 0xC0)                    # test eax,eax
    a.jcc8(0x74, 'def')
    a.db(0x8B, 0xF0)                    # mov esi,eax (owner)
    a.db(0xBA); a.dd(HEAL_ID)           # mov edx,0x2F
    a.call(FINDDATA)                    # own record
    a.db(0x33, 0xC9)                    # xor ecx,ecx
    a.db(0x85, 0xC0)
    a.jcc8(0x74, 'noown')
    a.db(0x0F, 0xB6, 0x48, 0x0D)        # movzx ecx, byte [eax+0xD]
    a.lab('noown')
    a.db(0x51)                          # push ecx (own level)
    a.db(0xB9); a.dd(HEAL_ID)           # mov ecx,0x2F
    a.call(CAVE_FIND)                   # item record (esi=owner)
    a.db(0x59)                          # pop ecx (own level)
    a.db(0x85, 0xC0)
    a.jcc8(0x74, 'max')
    a.db(0x0F, 0xB6, 0x40, 0x0D)        # movzx eax, byte [eax+0xD]
    a.db(0x3B, 0xC1)                    # cmp eax,ecx
    a.jcc8(0x7E, 'max')                 # jle
    a.db(0x8B, 0xC8)                    # mov ecx,eax
    a.lab('max')
    a.db(0x83, 0xF9, 0x02)              # cmp ecx,2
    a.jcc8(0x72, 'def')                 # jb  -> 5
    a.jcc8(0x74, 'l2')                  # je  -> 7
    a.db(0xB8, 0x0A, 0, 0, 0)           # mov eax,10
    a.jcc8(0xEB, 'out')
    a.lab('l2')
    a.db(0xB8, 0x07, 0, 0, 0)           # mov eax,7
    a.jcc8(0xEB, 'out')
    a.lab('def')
    a.db(0xB8, 0x05, 0, 0, 0)           # mov eax,5
    a.lab('out')
    a.db(0x5E, 0x5A, 0x59, 0xC3)        # pop esi; pop edx; pop ecx; ret
    return a.fin(CAVE_GNAME)


def build_gname():
    """THealingAbility.GetName(eax=self, edx=owner|nil, ecx=out).
    Leveled name; '(used)' suffix (vanilla pieces) keeps the level."""
    a = Asm(CAVE_GNAME)
    a.db(0x53, 0x56, 0x57, 0x55)        # push ebx/esi/edi/ebp
    a.db(0x83, 0xEC, 0x14)              # sub esp,0x14
    a.db(0x8B, 0xEC)                    # mov ebp,esp
    # frame: [ebp]=tmpname [ebp+4]=tmpA [ebp+8]=tmpB [ebp+0xC]=delta [ebp+0x10]=level
    a.db(0x8B, 0xD8)                    # mov ebx,eax (self)
    a.db(0x8B, 0xF2)                    # mov esi,edx (owner)
    a.db(0x8B, 0xF9)                    # mov edi,ecx (out)
    a.db(0x33, 0xC0)                    # xor eax,eax
    a.db(0x89, 0x45, 0x00)              # mov [ebp],eax
    a.db(0x89, 0x45, 0x04)              # mov [ebp+4],eax
    a.db(0x89, 0x45, 0x08)              # mov [ebp+8],eax
    a.db(0x89, 0x45, 0x10)              # mov [ebp+0x10],eax (level=0)
    a.db(0xE8, 0, 0, 0, 0)              # call $+5 (PIC anchor)
    popva = a.here()
    a.db(0x58)                          # pop eax
    a.db(0x2D); a.dd(popva)             # sub eax, popva -> load delta
    a.db(0x89, 0x45, 0x0C)              # mov [ebp+0xC],eax
    # ---- display level
    a.db(0x85, 0xF6)                    # test esi,esi
    a.jcc8(0x74, 'lvldone')             # owner nil -> plain (level 0)
    a.db(0x8B, 0xD6)                    # mov edx,esi
    a.db(0x8B, 0xC3)                    # mov eax,ebx
    a.db(0x8B, 0x08)                    # mov ecx,[eax]
    a.db(0xFF, 0x51, 0x70)              # call [ecx+0x70]  GetLevel(owner)
    a.db(0x89, 0x45, 0x10)              # mov [ebp+0x10],eax
    a.db(0x8B, 0x4B, 0x0C)              # mov ecx,[ebx+0xC] (id)
    a.call(CAVE_FIND)                   # item rec on owner (nil unless hero)
    a.db(0x85, 0xC0)
    a.jcc8(0x74, 'lvldone')
    a.db(0x0F, 0xB6, 0x40, 0x0D)        # movzx eax, byte [eax+0xD]
    a.db(0x85, 0xC0)
    a.jcc8(0x75, 'cmpx')
    a.db(0xB8, 0x01, 0, 0, 0)           # level-0 item rec -> I
    a.lab('cmpx')
    a.db(0x3B, 0x45, 0x10)              # cmp eax,[ebp+0x10]
    a.jcc8(0x7E, 'lvldone')
    a.db(0x89, 0x45, 0x10)              # mov [ebp+0x10],eax
    a.lab('lvldone')
    a.db(0x8B, 0x55, 0x10)              # mov edx,[ebp+0x10]
    a.db(0x83, 0xFA, 0x03)              # cmp edx,3
    a.jcc8(0x7E, 'lok')
    a.db(0xBA, 0x03, 0, 0, 0)           # mov edx,3
    a.lab('lok')
    # ---- tmpname := lsnames(self, level)
    a.db(0x8B, 0xCD)                    # mov ecx,ebp (&tmpname)
    a.db(0x8B, 0xC3)                    # mov eax,ebx
    a.call(LSNAMES)
    # ---- used?
    a.db(0x85, 0xF6)                    # test esi,esi
    a.jcc8(0x74, 'plain')
    a.db(0x8B, 0xD6)                    # mov edx,esi
    a.db(0x8B, 0xC3)                    # mov eax,ebx
    a.db(0x8B, 0x08)                    # mov ecx,[eax]
    a.db(0xFF, 0x51, 0x74)              # call [ecx+0x74]  GetEnabled
    a.db(0x84, 0xC0)
    a.jcc8(0x75, 'plain')
    # ---- out := tmpname + " (" + T(used) + ")"   (vanilla pieces)
    a.db(0xFF, 0x75, 0x00)              # push dword [ebp] (tmpname)
    a.db(0x8B, 0x45, 0x0C)              # mov eax,[ebp+0xC] (delta)
    a.db(0x8D, 0x88); a.dd(LIT_OPEN)    # lea ecx,[eax+" ("]
    a.db(0x51)                          # push ecx
    a.db(0x8D, 0x80); a.dd(RSREC)       # lea eax,[eax+resstringrec]
    a.db(0x8D, 0x55, 0x04)              # lea edx,[ebp+4]
    a.call(LOADRES)                     # tmpA := "used" resource
    a.db(0x8B, 0x45, 0x04)              # mov eax,[ebp+4]
    a.db(0x8D, 0x55, 0x08)              # lea edx,[ebp+8]
    a.call(TRANSLATE)                   # tmpB := localized
    a.db(0x8B, 0x45, 0x08)              # mov eax,[ebp+8]
    a.db(0x8D, 0x55, 0x04)              # lea edx,[ebp+4]
    a.call(XFORM)                       # tmpA := transformed
    a.db(0xFF, 0x75, 0x04)              # push dword [ebp+4]
    a.db(0x8B, 0x45, 0x0C)              # mov eax,[ebp+0xC]
    a.db(0x8D, 0x88); a.dd(LIT_CLOSE)   # lea ecx,[eax+")"]
    a.db(0x51)                          # push ecx
    a.db(0x8B, 0xC7)                    # mov eax,edi (out)
    a.db(0xBA, 0x04, 0, 0, 0)           # mov edx,4
    a.call(LSTRCATN)                    # out := cat(4)
    a.jcc8(0xEB, 'fin')
    a.lab('plain')
    a.db(0x8B, 0xC7)                    # mov eax,edi
    a.db(0x8B, 0x55, 0x00)              # mov edx,[ebp] (tmpname)
    a.call(LSTRASG)                     # out := tmpname
    a.lab('fin')
    a.db(0x8B, 0xC5)                    # mov eax,ebp (&tmpname..tmpB)
    a.db(0xBA, 0x03, 0, 0, 0)           # mov edx,3
    a.call(LSTRARRCLR)                  # release temps
    a.db(0x83, 0xC4, 0x14)              # add esp,0x14
    a.db(0x5D, 0x5F, 0x5E, 0x5B)        # pop ebp/edi/esi/ebx
    a.db(0xC3)
    return a.fin(CAVE_END)


def main():
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if revert:
        if os.path.exists(BAK):
            shutil.copy2(BAK, DLL); print("restored AoWEPACK.dll"); return 0
        print("no backup"); return 1

    d = bytearray(open(DLL, "rb").read())
    ha2, gn = build_healamt2(), build_gname()
    ha_jmp = b"\xE9" + struct.pack("<i", CAVE_HEALAMT2 - (OLD_HEALAMT + 5))

    ok = True; applied = 0; total = 0

    def check(off, old, new, desc):
        nonlocal ok, applied, total
        total += 1
        cur = bytes(d[off:off + len(old)])
        if cur == new:
            applied += 1
        elif cur != old:
            print("MISMATCH %s @file %#x:\n  exp %s\n  got %s"
                  % (desc, off, old.hex(' '), cur.hex(' '))); ok = False

    check(CAVE_HEALAMT2 - V2F, bytes(len(ha2)), ha2, "cave_healamt2")
    check(CAVE_GNAME - V2F, bytes(len(gn)), gn, "cave_gname")
    check(OLD_HEALAMT - V2F, OLD_HA_BYTES, ha_jmp, "healamt entry jmp")
    check(GNAME_SLOT_FOFF, struct.pack("<I", GNAME_OLD),
          struct.pack("<I", CAVE_GNAME), "GetName VMT+0x58 repoint")

    if applied == total:
        print("ALL ALREADY PATCHED"); return 0
    if not ok:
        print("Aborting."); return 1

    print("cave_healamt2 @%#x %dB, cave_gname @%#x %dB"
          % (CAVE_HEALAMT2, len(ha2), CAVE_GNAME, len(gn)))
    print("Healing amount honours the item's authored level (max with own),")
    print("names render 'Healing I/II/III' + '(used)' keeps the level.")
    if not apply:
        print("\nDry run OK. Re-run with --apply (or --revert)."); return 0

    if not os.path.exists(BAK):
        shutil.copy2(DLL, BAK); print("Backup ->", os.path.basename(BAK))
    d[CAVE_HEALAMT2 - V2F: CAVE_HEALAMT2 - V2F + len(ha2)] = ha2
    d[CAVE_GNAME - V2F: CAVE_GNAME - V2F + len(gn)] = gn
    d[OLD_HEALAMT - V2F: OLD_HEALAMT - V2F + 5] = ha_jmp
    struct.pack_into("<I", d, GNAME_SLOT_FOFF, CAVE_GNAME)
    open(DLL, "wb").write(d)
    print("AoWEPACK.dll patched successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
