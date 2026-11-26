#!/usr/bin/env python3
r"""Make ITEM-GRANTED Healing behave exactly like the unit ability:
usable overland AND in tactical combat, but only once per day, with the
used-state remembered on the HERO (so dropping/re-picking the item, or
stashing it in inventory, cannot reset it).

SYMPTOMS FIXED (user report 2026-08-21):
  - tactical combat: item Healing always listed as "Healing (used)" yet
    usable without limit
  - overland: displays normally but the heal never fires

ROOT CAUSE (all paths funnel through THealingAbility.GetEnabled @0x5576BF2C):
  GetEnabled(owner) = owner.HasAbility(0x2F) [vmt+0x4C, OWN bits only]
                      && (rec := GetAbilityData(owner) ? rec.used-flag : 1)
  The once-per-day flag lives at [THealingAbilityData+0xC] and the consume
  step (SetUsed @0x5576BEEC, flag=0) targets the HEALER'S STRATEGIC UNIT --
  lazily CREATING the hero's record if missing (so vanilla already writes the
  used-state to the hero even for item healing!). But with the bit only on
  the ITEM:
   - GetName(hero) -> GetEnabled(hero) fails the own-bit test -> "(used)"
     suffix always shown in the tactical panel;
   - THealingTE.Execute (overland) re-validates GetEnabled(healer)
     @0x5576C775 -> heal silently skipped;
   - the tactical UI gates on the MERGED THero.GetAbilityEnabled @0x5578827C
     whose item leg calls item.GetAbEnabled -> ability.GetEnabled(item):
     item has the bit and never a record -> ALWAYS enabled -> unlimited use
     (THealingCA.Execute @0x5576BCE0 itself never validates).
  Daily reset: TAbilityOwner.NewDay @0x5574FE14 loops ability ids and
  dispatches ability.NewDay [vmt+0xAC] (-> SetUsed(owner,1)) ONLY for
  own-bit abilities -> a hero-side record for item healing would never reset.

THE FIX (hero record = single source of truth for the daily use):
  1. cave_ghe  (repoint THealingAbility VMT+0x74 @file 0x20C30):
     no own bit -> THero/TLeader also accept the MERGED HasAbility
     [vmt+0x14C] (unit|carried|inventory bits); then gate on the owner's
     own record as before (no record -> enabled).
  2. cave_mge  (repoint THero VMT+0x148 @0x11534 + TLeader @0x11780):
     reimplements the merged GetAbilityEnabled (own leg 0x5577F5E0, items
     0x55786674, inventory 0x55786154 - unchanged), then for id 0x2F only:
     if the hero carries a Healing data record its used-flag wins. Closes
     the "item leg always enabled" hole for every UI/AI gate.
  3. cave_cagate (code @0x5576BD1A, 10B): THealingCA.Execute now validates
     ability.GetEnabled(healer strat) BEFORE consuming+healing (parity with
     the overland TE; kills unlimited tactical use at the root). Healer
     resolved via the class-checking helper 0x55810F00 (healowner fix);
     unresolvable healer -> heal proceeds unconsumed (= today's behaviour).
  4. cave_ndbit (code @0x5574FE33, 5B): the NewDay own-bit funnel also
     accepts, for id 0x2F on THero/TLeader, the merged HasAbility - so the
     hero-side record resets each day even when the bit lives on an item.
  5. cave_gan  (code @0x557882F0, 8B in THero.GetAbilityName): when Healing
     has been used today (hero record used-flag 0), force the HERO as the
     display owner so the overland hero window shows "Healing (used)"
     instead of the item's eternally-fresh "Healing I".
  6. cave_expand2 (repoint THealingAbility VMT+0xD0 @file 0x20C8C):
     fixes a PRE-EXISTING latent bug in the leveled-healing patch's Expand:
     a SetUsed-created level-0 record (exists today after any item-heal in
     combat!) made a level-up purchase of Healing set level 2 WITHOUT the
     ability bit (dead purchase). Now level-0 record -> proper grant:
     SetBit + level 1, used-flag preserved.

  Item transfer to another hero mid-day lets THAT hero heal once - same as
  two units each owning the ability; the original hero stays used-up.

All caves are position-independent (VMT constants delta-normalized via
call/pop; cross-references rel32) - AoWEPACK.dll is rebased on some
launches. VMT slot repoints keep their existing .reloc entries (targets are
in-module, so rebasing still fixes them correctly); asserted below that no
reloc intersects the three CODE patch sites or the cave region.

Caves @0x55812700..0x55812980 (zeros verified; prior caves end 0x5581263C).
Dry-run default; --apply / --revert.  Backup: AoWEPACK.dll.bak_itemhealdaily
"""
import os, shutil, struct, sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DLL = os.path.join(GAME, "AoWEPACK.dll")
BAK = DLL + ".bak_itemhealdaily"
V2F = 0x55700C00

HEAL_ID   = 0x2F
FINDDATA  = 0x5574F1C4      # TAbilityOwner.GetAbilityData (abdataguard-hooked)
SETUSED   = 0x5576BEEC      # THealingAbility.SetUsed(self, owner, cl=flag)
SETBIT    = 0x5574E718
ADDDATA   = 0x5574F278
TOBJCREATE= 0x55703064
CLASSREF_HD = 0x55721550    # THealingAbilityData class ref (relocated global)
OWN_LEG   = 0x5577F5E0      # TAbstractUnit.GetAbilityEnabled
ITEMS_LEG = 0x55786674      # THeroItems leg of the merged query
INV_LEG   = 0x55786154      # THeroInventory leg
HELPER_STRAT = 0x55810F00   # combat obj -> strat unit | nil (healowner fix)
THERO_VMT   = 0x55711FEC
TLEADER_VMT = 0x55712238

CAVE_GHE     = 0x55812700
CAVE_MGE     = 0x55812760
CAVE_NDBIT   = 0x558127C0
CAVE_CAGATE  = 0x55812820
CAVE_GAN     = 0x55812870
CAVE_EXPAND2 = 0x558128C0
CAVE_END     = 0x55812980

# code patch sites
ND_SITE  = 0x5574FE33       # mov ecx,[eax]; call [ecx+0x4C]   (NewDay bit test)
ND_ORIG  = bytes.fromhex("8b08ff514c")
CA_SITE  = 0x5576BD1A       # mov edx,[edi+0x4C]; xor ecx,ecx; call SetUsed
CA_ORIG  = bytes.fromhex("8b574c33c9e8c8010000")
CA_SKIP  = 0x5576BD41       # CA.Execute epilogue (skip heal entirely)
GAN_SITE = 0x557882F0       # mov ebx,eax; test ebx,ebx; jne+2; mov ebx,esi
GAN_ORIG = bytes.fromhex("8bd885db75028bde")

# VMT slot repoints (file_off, old target, new target, desc)
SLOTS = [
    (0x20C30, 0x5576BF2C, CAVE_GHE,     "THealingAbility VMT+0x74 GetEnabled"),
    (0x11534, 0x5578827C, CAVE_MGE,     "THero VMT+0x148 GetAbilityEnabled"),
    (0x11780, 0x5578827C, CAVE_MGE,     "TLeader VMT+0x148 GetAbilityEnabled"),
    (0x20C8C, 0x5580E7F0, CAVE_EXPAND2, "THealingAbility VMT+0xD0 Expand v2"),
]


class Asm:
    def __init__(self, base):
        self.base = base; self.buf = bytearray(); self.labels = {}; self.j8 = []
    def here(self): return self.base + len(self.buf)
    def db(self, *b): self.buf += bytes(b)
    def dd(self, v): self.buf += struct.pack("<I", v & 0xFFFFFFFF)
    def dds(self, v): self.buf += struct.pack("<i", v)
    def call(self, t):
        self.db(0xE8); self.buf += struct.pack("<i", t - (self.here() + 4))
    def lab(self, n): self.labels[n] = len(self.buf)
    def jcc8(self, op, n): self.db(op); self.j8.append((len(self.buf), n)); self.db(0)
    def pic_delta(self, reg_pop, reg_sub_op):
        """call $+5; pop <reg>; sub <reg>, popva  -> reg = load delta"""
        self.db(0xE8, 0, 0, 0, 0)
        popva = self.here()
        self.db(reg_pop)                      # pop reg
        self.db(0x81, reg_sub_op); self.dd(popva)   # sub reg, popva
    def fin(self, limit):
        for off, n in self.j8:
            d = self.labels[n] - (off + 1)
            assert -128 <= d <= 127, (n, d)
            self.buf[off] = d & 0xFF
        assert self.base + len(self.buf) <= limit, (hex(self.base), len(self.buf))
        return bytes(self.buf)


def build_ghe():
    """GetEnabled(eax=self, edx=owner) -> al. Own bit OR (hero/leader merged
    item bit), then the owner's own record's used-flag (no record -> 1)."""
    a = Asm(CAVE_GHE)
    a.db(0x53, 0x56)                    # push ebx; push esi
    a.db(0x8B, 0xD8)                    # mov ebx,eax (self)
    a.db(0x8B, 0xF2)                    # mov esi,edx (owner)
    a.db(0x8B, 0x53, 0x0C)              # mov edx,[ebx+0xC] (id)
    a.db(0x8B, 0xC6)                    # mov eax,esi
    a.db(0x8B, 0x08)                    # mov ecx,[eax]
    a.db(0xFF, 0x51, 0x4C)              # call [ecx+0x4C]  HasAbility(own)
    a.db(0x84, 0xC0)                    # test al,al
    a.jcc8(0x75, 'has')
    a.pic_delta(0x5A, 0xEA)             # edx = load delta
    a.db(0x8B, 0x06)                    # mov eax,[esi] (owner VMT)
    a.db(0x2B, 0xC2)                    # sub eax,edx -> preferred-base VMT
    a.db(0x3D); a.dd(THERO_VMT)
    a.jcc8(0x74, 'm')
    a.db(0x3D); a.dd(TLEADER_VMT)
    a.jcc8(0x75, 'zero')
    a.lab('m')
    a.db(0x8B, 0x53, 0x0C)              # mov edx,[ebx+0xC]
    a.db(0x8B, 0xC6)                    # mov eax,esi
    a.db(0x8B, 0x08)                    # mov ecx,[eax]
    a.db(0xFF, 0x91); a.dd(0x14C)       # call [ecx+0x14C]  merged HasAbility
    a.db(0x84, 0xC0)                    # test al,al
    a.jcc8(0x74, 'zero')
    a.lab('has')
    a.db(0x8B, 0x53, 0x0C)              # mov edx,[ebx+0xC]
    a.db(0x8B, 0xC6)                    # mov eax,esi
    a.call(FINDDATA)
    a.db(0x85, 0xC0)                    # test eax,eax
    a.jcc8(0x74, 'one')
    a.db(0x8A, 0x40, 0x0C)              # mov al,[eax+0xC] (used-flag)
    a.jcc8(0xEB, 'out')
    a.lab('one')
    a.db(0xB0, 0x01)                    # mov al,1
    a.jcc8(0xEB, 'out')
    a.lab('zero')
    a.db(0x33, 0xC0)                    # xor eax,eax
    a.lab('out')
    a.db(0x5E, 0x5B, 0xC3)              # pop esi; pop ebx; ret
    return a.fin(CAVE_MGE)


def build_mge():
    """Merged GetAbilityEnabled(eax=hero, edx=id) -> al. Vanilla three legs,
    then for Healing the hero's own record's used-flag overrides."""
    a = Asm(CAVE_MGE)
    a.db(0x53, 0x56)                    # push ebx; push esi
    a.db(0x8B, 0xD8)                    # mov ebx,eax (hero)
    a.db(0x8B, 0xF2)                    # mov esi,edx (id)
    a.call(OWN_LEG)                     # own leg (args already in eax/edx)
    a.db(0x84, 0xC0)
    a.jcc8(0x75, 'tail')
    a.db(0x8B, 0xD6)                    # mov edx,esi
    a.db(0x8B, 0x43, 0x70)              # mov eax,[ebx+0x70]
    a.call(ITEMS_LEG)
    a.db(0x84, 0xC0)
    a.jcc8(0x75, 'tail')
    a.db(0x8B, 0xD6)                    # mov edx,esi
    a.db(0x8B, 0x43, 0x74)              # mov eax,[ebx+0x74]
    a.call(INV_LEG)
    a.db(0x84, 0xC0)
    a.jcc8(0x74, 'out')                 # all legs disabled -> al=0
    a.lab('tail')
    a.db(0x83, 0xFE, HEAL_ID)           # cmp esi,0x2F
    a.jcc8(0x75, 'out')
    a.db(0x8B, 0xD6)                    # mov edx,esi
    a.db(0x8B, 0xC3)                    # mov eax,ebx
    a.call(FINDDATA)                    # hero's Healing record
    a.db(0x85, 0xC0)
    a.jcc8(0x74, 'one')
    a.db(0x8A, 0x40, 0x0C)              # mov al,[eax+0xC]
    a.jcc8(0xEB, 'out')
    a.lab('one')
    a.db(0xB0, 0x01)                    # mov al,1
    a.lab('out')
    a.db(0x5E, 0x5B, 0xC3)              # pop esi; pop ebx; ret
    return a.fin(CAVE_NDBIT)


def build_ndbit():
    """NewDay funnel (eax=owner, edx=id) -> al. Own bit, else merged bit for
    Healing on THero/TLeader. Preserves ebx/esi/edi (live in the loop)."""
    a = Asm(CAVE_NDBIT)
    a.db(0x52)                          # push edx (id)
    a.db(0x50)                          # push eax (owner)
    a.db(0x8B, 0x08)                    # mov ecx,[eax]
    a.db(0xFF, 0x51, 0x4C)              # call [ecx+0x4C]  own bit
    a.db(0x84, 0xC0)
    a.jcc8(0x75, 'fin')
    a.db(0x81, 0x7C, 0x24, 0x04); a.dd(HEAL_ID)   # cmp dword [esp+4],0x2F
    a.jcc8(0x75, 'zero')
    a.pic_delta(0x5A, 0xEA)             # edx = delta
    a.db(0x8B, 0x0C, 0x24)              # mov ecx,[esp] (owner)
    a.db(0x8B, 0x01)                    # mov eax,[ecx]
    a.db(0x2B, 0xC2)                    # sub eax,edx
    a.db(0x3D); a.dd(THERO_VMT)
    a.jcc8(0x74, 'm')
    a.db(0x3D); a.dd(TLEADER_VMT)
    a.jcc8(0x75, 'zero')
    a.lab('m')
    a.db(0x8B, 0x04, 0x24)              # mov eax,[esp] (owner)
    a.db(0xBA); a.dd(HEAL_ID)           # mov edx,0x2F
    a.db(0x8B, 0x08)                    # mov ecx,[eax]
    a.db(0xFF, 0x91); a.dd(0x14C)       # call [ecx+0x14C]  merged
    a.jcc8(0xEB, 'fin')
    a.lab('zero')
    a.db(0x33, 0xC0)                    # xor eax,eax
    a.lab('fin')
    a.db(0x83, 0xC4, 0x08)              # add esp,8
    a.db(0xC3)
    return a.fin(CAVE_CAGATE)


def build_cagate():
    """CA.Execute consume site (eax=ability, edi=healer combat) -> al.
    al=1: proceed (used-flag consumed / healer unresolvable); al=0: skip."""
    a = Asm(CAVE_CAGATE)
    a.db(0x50)                          # push eax (ability)
    a.db(0x8B, 0xC7)                    # mov eax,edi
    a.call(HELPER_STRAT)                # -> eax = strat unit | nil
    a.db(0x85, 0xC0)
    a.jcc8(0x74, 'allow')               # unresolvable -> vanilla behaviour
    a.db(0x50)                          # push eax (strat)
    a.db(0x8B, 0xD0)                    # mov edx,eax
    a.db(0x8B, 0x44, 0x24, 0x04)        # mov eax,[esp+4] (ability)
    a.db(0x8B, 0x08)                    # mov ecx,[eax]
    a.db(0xFF, 0x51, 0x74)              # call [ecx+0x74]  GetEnabled(strat)
    a.db(0x5A)                          # pop edx (strat)
    a.db(0x84, 0xC0)
    a.jcc8(0x74, 'out')                 # disabled -> al=0, skip heal
    a.db(0x33, 0xC9)                    # xor ecx,ecx
    a.db(0x8B, 0x04, 0x24)              # mov eax,[esp] (ability)
    a.call(SETUSED)                     # SetUsed(ability, strat, 0)
    a.lab('allow')
    a.db(0xB0, 0x01)                    # mov al,1
    a.lab('out')
    a.db(0x83, 0xC4, 0x04)              # add esp,4
    a.db(0xC3)
    return a.fin(CAVE_GAN)


def build_gan():
    """GetAbilityName owner chooser (eax=finder result, esi=hero, edi=id)
    -> eax = display owner. Healing used today -> the hero (so the window
    shows '(used)'); otherwise vanilla choice (nil -> hero)."""
    a = Asm(CAVE_GAN)
    a.db(0x81, 0xFF); a.dd(HEAL_ID)     # cmp edi,0x2F
    a.jcc8(0x75, 'keep')
    a.db(0x50)                          # push eax
    a.db(0xBA); a.dd(HEAL_ID)           # mov edx,0x2F
    a.db(0x8B, 0xC6)                    # mov eax,esi (hero)
    a.call(FINDDATA)
    a.db(0x85, 0xC0)
    a.jcc8(0x74, 'pk')
    a.db(0x80, 0x78, 0x0C, 0x00)        # cmp byte [eax+0xC],0
    a.jcc8(0x75, 'pk')
    a.db(0x58)                          # pop eax (discard finder choice)
    a.db(0x8B, 0xC6)                    # mov eax,esi (hero)
    a.db(0xC3)                          # ret
    a.lab('pk')
    a.db(0x58)                          # pop eax
    a.lab('keep')
    a.db(0x85, 0xC0)                    # test eax,eax
    a.jcc8(0x75, 'r')
    a.db(0x8B, 0xC6)                    # nil -> hero (vanilla fallback)
    a.lab('r')
    a.db(0xC3)
    return a.fin(CAVE_EXPAND2)


def build_expand2():
    """Expand(eax=self, edx=unit) -> al. v1 logic + level-0-record repair:
    a used-state-only record now gets SetBit + level 1 (used-flag kept)."""
    a = Asm(CAVE_EXPAND2)
    a.db(0x53, 0x56, 0x57, 0x55)        # push ebx/esi/edi/ebp
    a.db(0x8B, 0xF0)                    # mov esi,eax (self)
    a.db(0x8B, 0xFA)                    # mov edi,edx (unit)
    a.db(0x8B, 0x56, 0x0C)              # mov edx,[esi+0xC]
    a.db(0x8B, 0xC7)                    # mov eax,edi
    a.call(FINDDATA)
    a.db(0x8B, 0xE8)                    # mov ebp,eax
    a.db(0x85, 0xED)                    # test ebp,ebp
    a.jcc8(0x75, 'have')
    # create path (v1): level = HasAbility(own)?2:1, new record, bit, link
    a.db(0x8B, 0x56, 0x0C)              # mov edx,[esi+0xC]
    a.db(0x8B, 0xC7)                    # mov eax,edi
    a.db(0x8B, 0x08)                    # mov ecx,[eax]
    a.db(0xFF, 0x51, 0x4C)              # call [ecx+0x4C]
    a.db(0x0F, 0xB6, 0xD8)              # movzx ebx,al
    a.db(0x43)                          # inc ebx
    a.db(0xE8, 0, 0, 0, 0)              # call $+5 (PIC classref read)
    popva = a.here()
    a.db(0x5A)                          # pop edx
    a.db(0x8B, 0x82); a.dds(CLASSREF_HD - popva)  # mov eax,[edx+disp]
    a.db(0xB2, 0x01)                    # mov dl,1
    a.db(0x33, 0xC9)                    # xor ecx,ecx
    a.call(TOBJCREATE)
    a.db(0x8B, 0xE8)                    # mov ebp,eax (rec)
    a.db(0xC6, 0x45, 0x0C, 0x01)        # mov byte [ebp+0xC],1 (fresh today)
    a.db(0x88, 0x5D, 0x0D)              # mov [ebp+0xD],bl (level)
    a.db(0x6A, 0x01)                    # push 1
    a.db(0x8B, 0x4E, 0x0C)              # mov ecx,[esi+0xC]
    a.db(0x8B, 0xD7)                    # mov edx,edi
    a.db(0x8B, 0xC6)                    # mov eax,esi
    a.call(SETBIT)
    a.db(0x8B, 0xD5)                    # mov edx,ebp
    a.db(0x8B, 0xC7)                    # mov eax,edi
    a.call(ADDDATA)
    a.db(0xB0, 0x01)                    # mov al,1
    a.jcc8(0xEB, 'out')
    a.lab('have')
    a.db(0x0F, 0xB6, 0x45, 0x0D)        # movzx eax, byte [ebp+0xD]
    a.db(0x85, 0xC0)
    a.jcc8(0x75, 'lvln')
    # level-0 record (created by SetUsed for item healing): proper grant of I
    a.db(0xC6, 0x45, 0x0D, 0x01)        # mov byte [ebp+0xD],1
    a.db(0x6A, 0x01)                    # push 1
    a.db(0x8B, 0x4E, 0x0C)              # mov ecx,[esi+0xC]
    a.db(0x8B, 0xD7)                    # mov edx,edi
    a.db(0x8B, 0xC6)                    # mov eax,esi
    a.call(SETBIT)
    a.db(0xB0, 0x01)                    # mov al,1
    a.jcc8(0xEB, 'out')
    a.lab('lvln')
    a.db(0x83, 0xF8, 0x03)              # cmp eax,3
    a.jcc8(0x7D, 'fail')
    a.db(0xFE, 0x45, 0x0D)              # inc byte [ebp+0xD]
    a.db(0xB0, 0x01)                    # mov al,1
    a.jcc8(0xEB, 'out')
    a.lab('fail')
    a.db(0x32, 0xC0)                    # xor al,al
    a.lab('out')
    a.db(0x5D, 0x5F, 0x5E, 0x5B)        # pop ebp/edi/esi/ebx
    a.db(0xC3)
    return a.fin(CAVE_END)


def code_patches():
    nd = b"\xE8" + struct.pack("<i", CAVE_NDBIT - (ND_SITE + 5))
    ca = (b"\xE8" + struct.pack("<i", CAVE_CAGATE - (CA_SITE + 5)) +
          b"\x84\xC0" +                                   # test al,al
          bytes([0x74, CA_SKIP - (CA_SITE + 7 + 2)]) +    # je CA_SKIP
          b"\x90")
    assert len(ca) == len(CA_ORIG) == 10
    gan = (b"\xE8" + struct.pack("<i", CAVE_GAN - (GAN_SITE + 5)) +
           b"\x8B\xD8\x90")                               # mov ebx,eax; nop
    assert len(gan) == len(GAN_ORIG) == 8
    return [(ND_SITE, ND_ORIG, nd, "NewDay funnel: merged bit for Healing"),
            (CA_SITE, CA_ORIG, ca, "CA.Execute: validate + consume via cave"),
            (GAN_SITE, GAN_ORIG, gan, "GetAbilityName: used -> hero owner")]


def reloc_hits(data, ranges):
    e = struct.unpack_from('<I', data, 0x3C)[0]; opt = e + 24
    nsec = struct.unpack_from('<H', data, e + 6)[0]
    osz = struct.unpack_from('<H', data, e + 20)[0]
    rrva, rsz = struct.unpack_from('<II', data, opt + 96 + 5 * 8)
    secs = []; p = opt + osz
    for _ in range(nsec):
        vs, va, rs, raw = struct.unpack_from('<IIII', data, p + 8)
        secs.append((va, vs, raw, rs)); p += 40
    def r2o(rva):
        for va, vs, raw, rs in secs:
            if va <= rva < va + max(vs, rs):
                return raw + rva - va
    off = r2o(rrva); end = off + rsz; hits = []
    while off < end:
        page, blk = struct.unpack_from('<II', data, off)
        if blk == 0:
            break
        for i in range((blk - 8) // 2):
            w = struct.unpack_from('<H', data, off + 8 + i * 2)[0]
            if w >> 12 == 0:
                continue
            fo = r2o(page + (w & 0xFFF))
            if fo is None:
                continue
            for lo, hi in ranges:
                if lo <= fo + 3 and fo < hi:
                    hits.append(fo)
        off += blk
    return hits


def main():
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if revert:
        if os.path.exists(BAK):
            shutil.copy2(BAK, DLL); print("restored AoWEPACK.dll"); return 0
        print("no backup"); return 1

    d = bytearray(open(DLL, "rb").read())
    caves = [(CAVE_GHE, build_ghe(), "cave_ghe (GetEnabled, item-aware)"),
             (CAVE_MGE, build_mge(), "cave_mge (merged enabled + heal tail)"),
             (CAVE_NDBIT, build_ndbit(), "cave_ndbit (daily reset funnel)"),
             (CAVE_CAGATE, build_cagate(), "cave_cagate (combat validate)"),
             (CAVE_GAN, build_gan(), "cave_gan (display owner)"),
             (CAVE_EXPAND2, build_expand2(), "cave_expand2 (level-0 repair)")]

    # reloc entries must not touch the code patch sites or the cave region
    code = code_patches()
    ranges = [(va - V2F, va - V2F + len(old)) for va, old, new, _ in code]
    ranges.append((CAVE_GHE - V2F, CAVE_END - V2F))
    hits = reloc_hits(bytes(d), ranges)
    assert not hits, ["reloc hit @file %#x" % h for h in hits]

    ok = True; applied = 0; total = 0
    # cave region: zeros (or already ours)
    for base, blob, desc in caves:
        off = base - V2F
        cur = bytes(d[off:off + len(blob)])
        total += 1
        if cur == blob:
            applied += 1
        elif cur != bytes(len(blob)):
            print("MISMATCH cave %s @%#x: not zero/ours" % (desc, base)); ok = False
    # build_item_healing_carrier.py (round 4) repoints VMT+0x74 further,
    # ghe -> ghe2 @0x55812B80: that value also counts as applied here.
    SUCCESSORS = {0x20C30: (0x55812B80,)}
    for foff, old, new, desc in SLOTS:
        cur = struct.unpack_from("<I", d, foff)[0]
        total += 1
        if cur == new or cur in SUCCESSORS.get(foff, ()):
            applied += 1
        elif cur != old:
            print("MISMATCH slot %s @file %#x: expected %#x got %#x"
                  % (desc, foff, old, cur)); ok = False
    for va, old, new, desc in code:
        off = va - V2F
        cur = bytes(d[off:off + len(old)])
        total += 1
        if cur == new:
            applied += 1
        elif cur != old:
            print("MISMATCH %s @%#x:\n  exp %s\n  got %s"
                  % (desc, va, old.hex(' '), cur.hex(' '))); ok = False

    if applied == total:
        print("ALL ALREADY PATCHED"); return 0
    if not ok:
        print("Aborting."); return 1

    for base, blob, desc in caves:
        print("  %-42s @%#x  %dB" % (desc, base, len(blob)))
    print("Item-granted Healing: once per day, overland + combat, used-state")
    print("kept on the hero (drop/pickup safe), daily reset, '(used)' display.")
    if not apply:
        print("\nDry run OK. Re-run with --apply (or --revert)."); return 0

    if not os.path.exists(BAK):
        shutil.copy2(DLL, BAK); print("Backup ->", os.path.basename(BAK))
    for base, blob, desc in caves:
        d[base - V2F: base - V2F + len(blob)] = blob
    for foff, old, new, desc in SLOTS:
        struct.pack_into("<I", d, foff, new)
        print("Repointed:", desc)
    for va, old, new, desc in code:
        d[va - V2F: va - V2F + len(new)] = new
        print("Patched:", desc)
    open(DLL, "wb").write(d)
    print("AoWEPACK.dll patched successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
