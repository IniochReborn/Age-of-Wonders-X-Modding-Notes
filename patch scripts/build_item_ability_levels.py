#!/usr/bin/env python3
r"""Make item-granted leveled abilities actually work (Marksmanship et al).

VANILLA BUG (confirmed present in stock AoW): "Use" items grant abilities by
setting the ability BIT on the item (TItem is a TAbilityOwner), but the item
editor never creates ability-DATA records, and levels live in those records.
The hero-side machinery is complete - THero.GetAbilityLevel/GetAbilityName
route through an owner-finder @0x557881DC that picks the best owner among the
hero, carried items [hero+0x70] and inventory [hero+0x74], and combat stats
delegate back into it (TCombatUnit.GetAbilityLevel -> strat [vmt+0x144]).
The chain dies at the last step: the ability's GetLevel does
GetAbilityData(owner) -> nil -> level 0, so a bow's Marksmanship displays as
plain "Marksmanship" and adds nothing to ranged attacks.

Vanilla's own devs fixed exactly this in ONE class: TDispelMagicAbility.
GetLevel @0x5576CEFC ends with `record ? rec.level : 1` - an item granting
Dispel Magic works at level I. The other leveled families never got the
fallback:

  TMultiLevelAbility.GetLevel @0x557651D8  (Marksmanship, Path Finding, ...)
  TTurnUndeadAbility.GetLevel @0x5576AE8C
  TLeadershipAbility.GetLevel @0x557661C4  (level = max(own[+0xC], aura[+0x10]))

FIX (v2): in each function the 10 bytes after GetAbilityData (`test eax,eax;
je zero; movzx/...; jmp exit`) become `call cave; jmp exit-with-eax; nop*3`.
The cave: own record -> its level (unchanged); no record -> virtual
[owner.vmt+0x4C] HasAbility(id) (the SAME check Dispel Magic's fallback and
the ability-set merge use) -> if the bit is present, cave_findrec searches the
owner's ITEM containers (THero/TLeader only: carried [hero+0x70] + inventory
[hero+0x74]) for the ability's data record and returns ITS level - so an item
authored with Marksmanship III gives III - else level 1 (bits-only item).
Without the bit -> 0, so nothing that is inert today starts working.

Why item records must be searched here: combat does NOT use the hero's
owner-finder (THero.GetAbilityLevel @0x557881DC path) - GetAttackRA and the
tactical panel's ListAbilities (AoWTCPCK 0x42355C) query the STRATEGIC unit
directly via TAbilityOwner.GetAbLevel/ability.GetName(strat), which land in
these GetLevel functions with owner=hero. v1 (flat level-1 fallback) made
combat show/apply level I while the unit window showed the item's true III.

Not touched: GetInherentLevel (purchase/medal templates), record-present
semantics, the mod's own leveled abilities (Healing/Lifesteal/... already
default no-record -> level 1 by design).

Caves @0x55812400 (zeros verified 0x55812240..0x55830000; abdataguard ends
0x55811100, probe data ends 0x55812240). Caves are fully position-independent
(register work + one virtual call). Dry-run default; --apply / --revert.
Backup: AoWEPACK.dll.bak_itemablvl
"""
import os, shutil, struct, sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DLL = os.path.join(GAME, "AoWEPACK.dll")
BAK = DLL + ".bak_itemablvl"
VA2FILE = 0x55700C00

# sites: 10 bytes right after `call GetAbilityData` in each GetLevel
MLA_SITE = 0x557651EC          # TMultiLevelAbility.GetLevel
MLA_EXIT = 0x557651FD          # pop esi; pop ebx; ret (returns eax)
TU_SITE  = 0x5576AEA0          # TTurnUndeadAbility.GetLevel
TU_EXIT  = 0x5576AEB1
LDR_SITE = 0x557661D8          # TLeadershipAbility.GetLevel
LDR_EXIT = 0x557661F9

SITE_MLA_TU = bytes.fromhex("85c074060fb6400ceb07")   # test;je;movzx [eax+C];jmp
SITE_LDR    = bytes.fromhex("85c074168a480c8a5010")   # test;je;mov cl,[eax+C];mov dl,[eax+10]

CAVE_LVL1 = 0x55812400         # shared: MLA + TU (level byte [rec+0xC])
CAVE_LDR  = 0x55812440         # Leadership (max of [rec+0xC], [rec+0x10])
CAVE_FIND = 0x558124A0         # find ability-data record on the hero's items
CAVE_GATE = 0x55812600         # marksmanship enabled-gate with item fallback
CAVE_END  = 0x55812680

# ⚠ AoWEPACK.dll DOES get rebased on some launches (observed at 0x2560000).
# Original code is fixed up by .reloc; cave code must be position-independent:
# compute the load delta (call/pop) and normalize VMTs before comparing.

# TRangedAttackAbility Get{Attack,Damage}RA gate their marksmanship block on
# virtual [owner.vmt+0x88] GetAbEnabled -> [owner.vmt+0x4C] own-bit test. The
# hero's OWN set never contains item-granted bits (only the hero-window
# owner-finder resolves items), so the whole block is skipped for item
# marksmanship. Both gates: `mov ecx,[eax]; call [ecx+0x88]` (8 bytes).
ATK_GATE = 0x5576E66E          # in GetAttackRA  (esi = owner)
DMG_GATE = 0x5576E626          # in GetDamageRA  (esi = owner)
GATE_ORIG = bytes.fromhex("8b08ff9188000000")

# hero classes (only they own the item containers at +0x70/+0x74)
THERO_VMT   = 0x55711FEC
TLEADER_VMT = 0x55712238       # TLeader : THero
TITEM_VMT   = 0x5570FAFC
ITEMS_OFF, INV_OFF = 0x70, 0x74


class Asm:
    def __init__(self, base):
        self.base = base; self.buf = bytearray(); self.labels = {}
        self.j8 = []; self.j32 = []
    def db(self, *b): self.buf += bytes(b)
    def lab(self, n): self.labels[n] = len(self.buf)
    def jcc8(self, op, n): self.db(op); self.j8.append((len(self.buf), n)); self.db(0)
    def jcc32(self, op, n):
        self.db(0x0F, op); self.j32.append((len(self.buf), n)); self.buf += bytes(4)
    def fin(self):
        for off, n in self.j8:
            d = self.labels[n] - (off + 1)
            assert -128 <= d <= 127, (n, d)
            self.buf[off] = d & 0xFF
        for off, n in self.j32:
            self.buf[off:off+4] = (self.labels[n] - (off + 4)).to_bytes(4, 'little', signed=True)
        return bytes(self.buf)


def build_findrec():
    """cave_findrec: (ecx=ability id, esi=owner) -> eax = ability-data record
    found on the owner's items, or nil.

    Only THero/TLeader own the item containers ([hero+0x70] carried THeroItems,
    [hero+0x74] THeroInventory); any other owner class -> nil. Containers hold
    a TList at +8 (data +4, count +8); each item's data-record chain starts at
    [item+0x10], node id via virtual [node.vmt+0x4C], next at [node+8] - the
    exact walk TAbilityOwner.GetAbilityData does on the owner itself.
    Preserves ebx/esi/edi/ebp (callers keep ability/owner there)."""
    a = Asm(CAVE_FIND)
    a.db(0x53, 0x57, 0x55)              # push ebx/edi/ebp
    a.db(0x83, 0xEC, 0x0C)              # sub esp,12
    a.db(0x89, 0x0C, 0x24)              # mov [esp],ecx (id)
    # load delta -> [esp+8] (PIC anchor)
    a.db(0xE8, 0, 0, 0, 0)              # call $+5
    popva = a.base + len(a.buf)
    a.db(0x5A)                          # pop edx
    a.db(0x81, 0xEA); a.buf += struct.pack("<I", popva)   # sub edx, popva
    a.db(0x89, 0x54, 0x24, 0x08)        # mov [esp+8],edx (delta)
    a.db(0x8B, 0x06)                    # mov eax,[esi] (runtime VMT)
    a.db(0x2B, 0xC2)                    # sub eax,edx -> preferred-base VMT
    a.db(0x3D); a.buf += struct.pack("<I", THERO_VMT)    # cmp eax,THero
    a.jcc8(0x74, 'ok')
    a.db(0x3D); a.buf += struct.pack("<I", TLEADER_VMT)  # cmp eax,TLeader
    a.jcc32(0x85, 'nil')
    a.lab('ok')
    a.db(0xBD, ITEMS_OFF, 0, 0, 0)      # mov ebp,0x70 (container offset)
    a.lab('cont')
    a.db(0x8B, 0x04, 0x2E)              # mov eax,[esi+ebp] (container obj)
    a.db(0x3D); a.buf += struct.pack("<I", 0x10000)           # plausible ptr?
    a.jcc32(0x82, 'nextcont')
    a.db(0x3D); a.buf += struct.pack("<I", 0x7F000000)
    a.jcc32(0x83, 'nextcont')
    a.db(0x8B, 0x40, 0x08)              # mov eax,[eax+8] (TList)
    a.db(0x3D); a.buf += struct.pack("<I", 0x10000)
    a.jcc32(0x82, 'nextcont')
    a.db(0x3D); a.buf += struct.pack("<I", 0x7F000000)
    a.jcc32(0x83, 'nextcont')
    a.db(0x8B, 0x50, 0x04)              # mov edx,[eax+4] (data)
    a.db(0x89, 0x54, 0x24, 0x04)        # mov [esp+4],edx
    a.db(0x81, 0xFA); a.buf += struct.pack("<I", 0x10000)     # data plausible?
    a.jcc32(0x82, 'nextcont')
    a.db(0x8B, 0x78, 0x08)              # mov edi,[eax+8] (count)
    a.db(0x83, 0xFF, 0x40)              # cmp edi,0x40 (sane slot count)
    a.jcc32(0x87, 'nextcont')           # ja: garbage, skip container
    a.lab('item')
    a.db(0x4F)                          # dec edi
    a.jcc32(0x88, 'nextcont')           # js
    a.db(0x8B, 0x44, 0x24, 0x04)        # mov eax,[esp+4]
    a.db(0x8B, 0x1C, 0xB8)              # mov ebx,[eax+edi*4] (item)
    # during map streaming the list may briefly hold IDs / stale entries -
    # only walk entries that are real, live TItem objects (exact VMT match,
    # delta-normalized: the DLL can be rebased)
    a.db(0x81, 0xFB); a.buf += struct.pack("<I", 0x10000)     # cmp ebx,0x10000
    a.jcc8(0x72, 'item')                # jb: nil / small int placeholder
    a.db(0x81, 0xFB); a.buf += struct.pack("<I", 0x7F000000)  # user-space cap
    a.jcc8(0x73, 'item')
    a.db(0x8B, 0x03)                    # mov eax,[ebx] (item VMT)
    a.db(0x2B, 0x44, 0x24, 0x08)        # sub eax,[esp+8] (delta)
    a.db(0x3D); a.buf += struct.pack("<I", TITEM_VMT)         # cmp eax,TItem
    a.jcc8(0x75, 'item')
    a.db(0x8B, 0x5B, 0x10)              # mov ebx,[ebx+0x10] (record chain)
    a.lab('node')
    a.db(0x81, 0xFB); a.buf += struct.pack("<I", 0x10000)     # node plausible?
    a.jcc8(0x72, 'item')
    a.db(0x81, 0xFB); a.buf += struct.pack("<I", 0x7F000000)
    a.jcc8(0x73, 'item')
    a.db(0x8B, 0x13)                    # mov edx,[ebx] (node VMT)
    a.db(0x2B, 0x54, 0x24, 0x08)        # sub edx,[esp+8] -> preferred-base VMT
    a.db(0x81, 0xFA); a.buf += struct.pack("<I", 0x55700000)  # VMT in AoWEPACK?
    a.jcc8(0x72, 'item')
    a.db(0x81, 0xFA); a.buf += struct.pack("<I", 0x55900000)
    a.jcc8(0x73, 'item')
    a.db(0x8B, 0xC3)                    # mov eax,ebx
    a.db(0x8B, 0x10)                    # mov edx,[eax] (runtime VMT for call)
    a.db(0xFF, 0x52, 0x4C)              # call [edx+0x4C] GetAbilityID -> eax
    a.db(0x3B, 0x04, 0x24)              # cmp eax,[esp]
    a.jcc8(0x74, 'found')
    a.db(0x8B, 0x5B, 0x08)              # mov ebx,[ebx+8] (next)
    a.jcc8(0xEB, 'node')
    a.lab('nextcont')
    a.db(0x83, 0xC5, 0x04)              # add ebp,4
    a.db(0x83, 0xFD, INV_OFF)           # cmp ebp,0x74
    a.jcc32(0x86, 'cont')               # jbe: run 0x70 then 0x74
    a.lab('nil')
    a.db(0x33, 0xC0)                    # xor eax,eax
    a.jcc8(0xEB, 'out')
    a.lab('found')
    a.db(0x8B, 0xC3)                    # mov eax,ebx
    a.lab('out')
    a.db(0x83, 0xC4, 0x0C)              # add esp,12
    a.db(0x5D, 0x5F, 0x5B)              # pop ebp/edi/ebx
    a.db(0xC3)
    return a.fin()


def build_lvl1():
    """(eax=record|nil, ebx=ability, esi=owner!=nil) -> eax=level.
    Own record -> its level. Else search the owner's items for the record
    FIRST (the hero's own bit-set never contains item bits, so the item search
    cannot hide behind a bit gate); found -> the item's level. Else bit -> 1,
    no bit -> 0."""
    a = Asm(CAVE_LVL1)
    a.db(0x85, 0xC0)                    # test eax,eax
    a.jcc8(0x75, 'rec')                 # jnz: own record exists
    a.db(0x8B, 0x4B, 0x0C)              # mov ecx,[ebx+0xC] (id)
    a.db(0xE8); a.buf += struct.pack("<i", CAVE_FIND - (a.base + len(a.buf) + 4))
    a.db(0x85, 0xC0)                    # test eax,eax
    a.jcc8(0x75, 'rec')                 # item record found -> its level
    a.db(0x8B, 0x53, 0x0C)              # mov edx,[ebx+0xC] (ability id)
    a.db(0x8B, 0xC6)                    # mov eax,esi (owner)
    a.db(0x8B, 0x08)                    # mov ecx,[eax]
    a.db(0xFF, 0x51, 0x4C)              # call [ecx+0x4C]  own-bit -> al
    a.db(0x84, 0xC0)                    # test al,al
    a.jcc8(0x74, 'zero')
    a.db(0xB8, 0x01, 0, 0, 0)           # mov eax,1 (bit without any record)
    a.db(0xC3)                          # ret
    a.lab('rec')
    a.db(0x0F, 0xB6, 0x40, 0x0C)        # movzx eax, byte [eax+0xC]
    a.db(0xC3)                          # ret
    a.lab('zero')
    a.db(0x33, 0xC0)                    # xor eax,eax
    a.db(0xC3)                          # ret
    return a.fin()


def build_ldr():
    """Same contract; record path replicates max(own [rec+0xC], aura [rec+0x10])."""
    a = Asm(CAVE_LDR)
    a.db(0x85, 0xC0)                    # test eax,eax
    a.jcc8(0x75, 'rec')
    a.db(0x8B, 0x4B, 0x0C)              # mov ecx,[ebx+0xC] (id)
    a.db(0xE8); a.buf += struct.pack("<i", CAVE_FIND - (a.base + len(a.buf) + 4))
    a.db(0x85, 0xC0)                    # test eax,eax
    a.jcc8(0x75, 'rec')                 # item record found
    a.db(0x8B, 0x53, 0x0C)              # mov edx,[ebx+0xC]
    a.db(0x8B, 0xC6)                    # mov eax,esi
    a.db(0x8B, 0x08)                    # mov ecx,[eax]
    a.db(0xFF, 0x51, 0x4C)              # call [ecx+0x4C]
    a.db(0x84, 0xC0)                    # test al,al
    a.jcc8(0x74, 'zero')
    a.db(0xB8, 0x01, 0, 0, 0)           # mov eax,1
    a.db(0xC3)                          # ret
    a.lab('rec')
    a.db(0x0F, 0xB6, 0x48, 0x0C)        # movzx ecx, byte [eax+0xC]  (own)
    a.db(0x0F, 0xB6, 0x50, 0x10)        # movzx edx, byte [eax+0x10] (aura)
    a.db(0x3B, 0xCA)                    # cmp ecx,edx
    a.jcc8(0x73, 'own')                 # jae
    a.db(0x8B, 0xC2)                    # mov eax,edx
    a.db(0xC3)
    a.lab('own')
    a.db(0x8B, 0xC1)                    # mov eax,ecx
    a.db(0xC3)
    a.lab('zero')
    a.db(0x33, 0xC0)
    a.db(0xC3)
    return a.fin()


def build_gate():
    """cave_msgate, replaces `mov ecx,[eax]; call [ecx+0x88]` at both RA gates.
    In: eax=owner (also in esi at both sites), edx=ability id. Out: al=enabled.
    Normal virtual GetAbEnabled first; if it says no, a hero/leader holding an
    item with this ability's data record counts as enabled (Marksmanship has
    no disable state, so a record is sufficient)."""
    a = Asm(CAVE_GATE)
    a.db(0x52)                          # push edx (id)
    a.db(0x8B, 0x08)                    # mov ecx,[eax]
    a.db(0xFF, 0x91); a.buf += struct.pack("<I", 0x88)   # call [ecx+0x88]
    a.db(0x5A)                          # pop edx
    a.db(0x84, 0xC0)                    # test al,al
    a.jcc8(0x75, 'done')                # normally enabled
    # PIC: normalize the owner's VMT by the load delta before comparing
    a.db(0xE8, 0, 0, 0, 0)              # call $+5
    popva = a.base + len(a.buf)
    a.db(0x59)                          # pop ecx
    a.db(0x81, 0xE9); a.buf += struct.pack("<I", popva)  # sub ecx, popva
    a.db(0x8B, 0x06)                    # mov eax,[esi] (owner VMT)
    a.db(0x2B, 0xC1)                    # sub eax,ecx
    a.db(0x3D); a.buf += struct.pack("<I", THERO_VMT)
    a.jcc8(0x74, 'h')
    a.db(0x3D); a.buf += struct.pack("<I", TLEADER_VMT)
    a.jcc8(0x75, 'fail')
    a.lab('h')
    a.db(0x8B, 0xCA)                    # mov ecx,edx (id)
    a.db(0xE8); a.buf += struct.pack("<i", CAVE_FIND - (a.base + len(a.buf) + 4))
    a.db(0x85, 0xC0)                    # test eax,eax
    a.jcc8(0x74, 'fail')
    a.db(0xB0, 0x01)                    # mov al,1
    a.db(0xC3)
    a.lab('fail')
    a.db(0x33, 0xC0)                    # xor eax,eax
    a.lab('done')
    a.db(0xC3)
    return a.fin()


def gate_patch(site):
    """call cave_msgate; nop*3 (exactly 8 bytes)"""
    return b"\xE8" + struct.pack("<i", CAVE_GATE - (site + 5)) + b"\x90\x90\x90"


def site_patch(site, cave, exit_va):
    """call cave; jmp short exit; nop*3  (exactly 10 bytes)"""
    b = b"\xE8" + struct.pack("<i", cave - (site + 5))
    jmp_at = site + 5
    rel = exit_va - (jmp_at + 2)
    assert 0 <= rel <= 127, rel
    b += bytes([0xEB, rel]) + b"\x90\x90\x90"
    assert len(b) == 10
    return b


def main():
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if revert:
        if os.path.exists(BAK):
            shutil.copy2(BAK, DLL); print("restored AoWEPACK.dll"); return 0
        print("no backup"); return 1

    d = bytearray(open(DLL, "rb").read())
    lvl1, ldr, findrec, gate = build_lvl1(), build_ldr(), build_findrec(), build_gate()
    assert CAVE_LVL1 + len(lvl1) <= CAVE_LDR, len(lvl1)
    assert CAVE_LDR + len(ldr) <= CAVE_FIND, len(ldr)
    assert CAVE_FIND + len(findrec) <= CAVE_GATE, len(findrec)
    assert CAVE_GATE + len(gate) <= CAVE_END, len(gate)

    # exit epilogues must be `pop esi; pop ebx; ret`
    for exit_va in (MLA_EXIT, TU_EXIT, LDR_EXIT):
        off = exit_va - VA2FILE
        assert bytes(d[off:off+3]) == bytes.fromhex("5e5bc3"), (hex(exit_va), d[off:off+3].hex())

    patches = [
        (CAVE_LVL1, bytes(len(lvl1)), lvl1, "cave_lvl1 (MLA+TU fallback)"),
        (CAVE_LDR,  bytes(len(ldr)),  ldr,  "cave_ldr (Leadership fallback)"),
        (CAVE_FIND, bytes(len(findrec)), findrec, "cave_findrec (item record search)"),
        (CAVE_GATE, bytes(len(gate)), gate, "cave_msgate (RA enabled-gate item fallback)"),
        (ATK_GATE, GATE_ORIG, gate_patch(ATK_GATE),
         "GetAttackRA marksmanship gate: hero item record counts as enabled"),
        (DMG_GATE, GATE_ORIG, gate_patch(DMG_GATE),
         "GetDamageRA marksmanship gate: hero item record counts as enabled"),
        (MLA_SITE, SITE_MLA_TU, site_patch(MLA_SITE, CAVE_LVL1, MLA_EXIT),
         "TMultiLevelAbility.GetLevel: no-record -> HasAbility ? 1 : 0"),
        (TU_SITE,  SITE_MLA_TU, site_patch(TU_SITE, CAVE_LVL1, TU_EXIT),
         "TTurnUndeadAbility.GetLevel: no-record -> HasAbility ? 1 : 0"),
        (LDR_SITE, SITE_LDR,    site_patch(LDR_SITE, CAVE_LDR, LDR_EXIT),
         "TLeadershipAbility.GetLevel: no-record -> HasAbility ? 1 : 0"),
    ]

    ok = True; applied = 0
    for va, orig, new, desc in patches:
        off = va - VA2FILE
        cur = bytes(d[off:off+len(orig)])
        if cur == new: applied += 1
        elif cur != orig:
            print("MISMATCH @0x%X (%s):\n  exp %s\n  got %s" % (va, desc, orig.hex(' '), cur.hex(' ')))
            ok = False
    if applied == len(patches):
        print("ALL ALREADY PATCHED"); return 0
    if not ok:
        print("Aborting."); return 1
    print("Item-granted leveled abilities: Marksmanship/MLA, Turn Undead, Leadership")
    print("now resolve to level I when granted bit-only (same rule as vanilla Dispel Magic).")
    if not apply:
        print("\nDry run OK. Re-run with --apply to write."); return 0

    if not os.path.exists(BAK):
        shutil.copyfile(DLL, BAK); print("Backup:", os.path.basename(BAK))
    for va, orig, new, desc in patches:
        off = va - VA2FILE
        d[off:off+len(new)] = new
        print("Patched:", desc)
    open(DLL, "wb").write(d)
    print("AoWEPACK.dll patched successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
