#!/usr/bin/env python3
r"""
SANCTIFY (spell 208, Life tier 3, 2026-10-16) - AoWEPACK half: the 'Sanctified Ground' status 0xC0 and what it
implies.  The consecrated hexes on the combat map live in AoWTCPCK.dll (patch_tc_sanctify_field_v1.py - apply THIS
script first, the field script calls this zone's export).

User spec: "Combat spell, long range, small AOE.  Research 120, Cost 4.  Creates a small zone that lasts 3 turns, in
which good units gain Fearless and Holy Champion I (Holy Champion II if pure good) and evil/pure neutral units are
Panicked (and/or Vertigo if pure evil)."

0xC0 'Sanctified Ground' = a combat-only TDurationAbility (mode 3; the Inspired / Grounded recipe), held by a unit
while it stands on a consecrated hex (granted / removed by sn_sync).  Its effect is read through GetAbilityEnabled,
by alignment (TAlignment: 0 PureGood 1 Good 2 PureNeutral 3 Neutral 4 Evil 5 PureEvil 6 None = unit VMT+0xFC):
      asked id          true for alignments
      0x43 Fearless     0 PureGood, 1 Good
      0x92 Holy Champ.  0 PureGood, 1 Good  -> the melee/ranged champion blocks pass; v3 (2026-10-16, user: "show the
                                         level - Holy Champion I / II"): the `lvl` cave below lifts the ability's
                                         LEVEL for a 0xC0 holder to >= I (Good) / >= II (PureGood), so the unit panel
                                         names it "Holy Champion I/II" (TMultiLevelAbility.GetName -> GetLevel) and
                                         cave_chbonus reads the same level (+1/+1 resp. +2/+2 vs evil); a real higher
                                         level (own record, item) still wins (max).  v1/v2 implied 0xA0 (the Holy
                                         Champion SPELL enchantment) for PureGood instead - listed without a level.
      0x6C Panicked     2 PureNeutral, 4 Evil, 5 PureEvil - v2 (2026-10-16, user: "should not apply Panicked to units
                                         with Fearless"): only when the unit is NOT Fearless from any other source
                                         (asked through its own VMT+0x148 = natural/item/medal/enchant/implied, with a
                                         re-entrancy latch FL_GUARD so a 0x6C query nested inside it answers plainly)
      0x62 Vertigo      5 PureEvil
Plain Neutral (3), None (6) and machines (GetUnitType VMT+0x114 == 2) never receive 0xC0.

Zone AoWEPACK 0x55868000..0x55868800 (verified zero + reloc-free; PIC call/pop delta - the DLL rebases):
  +0x00 header: the previous chain targets (fl, pom, reg, fg), u32 each
  +0x20 EXPORT jmp sn_sync  (eax = TUnit, dl = 1 'stands on a consecrated hex' / 0 'not'): grants 0xC0
        (TAbilityControl.GetAbility(0xC0).Expand, VMT+0xD0) to an eligible unit / removes it (RemoveAbility
        0x5577F6EC); unit.Changed (VMT+0x90) after either.  All registers but eax preserved.
  reg   call-hook CHAINED at 0x557BCF6E (Second Wind's reg site, `call cave`): calls the previous cave (= the vanilla
        RegisterAbility + 0xBF), then registers 0xC0 'Sanctified Ground' (ebx = registry).
  fl    jmp-hook CHAINED at 0x5577F5E0 TAbstractUnit.GetAbilityEnabled prologue (THero/TLeader VMT+0x148 0x55812760
        calls it first too): the table above when the unit's OWN bitset (VMT+0x14C) holds 0xC0; else -> previous.
  pom   jmp-hook CHAINED at 0x55784391 (TUnitHS.PlaceOnMap tail, Gravity Well's pom): for a tactical unit HS (ClassID
        0x220104) sn_sync(unit, its field owns a SANCTIFY HS (ClassID 0x22010E)); then -> previous (registers and
        stack untouched: pushal/popal).
  lvl   call-hook CHAINED at 0x557651EC (TMultiLevelAbility.GetLevel 0x557651D8: `call 0x55812400` = the item-level
        cave of build_item_ability_levels.py; ebx = ability, esi = owner, eax = own record or 0): calls the previous
        cave, then for ability 0x92 whose owner is a TAbstractUnit (or a hero's THeroItems / THeroInventory ->
        [container+4] = the hero) holding 0xC0 by its own bitset: level = max(level, PureGood ? 2 : Good ? 1 : -).
  fg    TGreatHail VMT+0xD8 fcGetDamageValueEx slot CHAINED: spell 208 -> all-zero result (never cast in auto combat,
        where no field exists); else -> previous (Inspiration's cave).
--revert restores every chain point to the stored previous target (refuses if another patch chained in front of us).
Backup <game>\backup\AoWEPACK.dll.bak_sanctify.  Dry-run default; --apply (upgrades an older build in place) /
--revert / --dis / --dll <copy>.
Also needed: pipeline 208, ALIAS 208 -> 0x74 + SITE_KEEP[0x40F0E3] += 208 + SITE_ALIAS 0x42827A {208: 0x82},
patch_rotaway_v1.py STRIKES[208] = 7, Ability.pfs 202 (patch_sanctify_ability_pfs_v1.py), ceilings LADDER += 0xC0
(bound -> 0xC1), then patch_tc_sanctify_field_v1.py.
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
from patch_earthlife_blessings_v1 import asm_delta, reloc_set, hook_bytes

DEFAULT_DLL = game_file("AoWEPACK.dll")
BAK_SUFFIX = ".bak_sanctify"
BASE, CODE_V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x55868000, 0x55868800
HDR, EXP_SYNC = 0x20, 0x55868020
SPELL_ID, AB_SANCT, NAME = 208, 0xC0, b"Sanctified Ground"
FIELD_CLASSID, UNITHS_CLASSID = 0x22010E, 0x220104
FL_GUARD = 0x558FAE60                            # v2: 1-byte re-entrancy latch (AoWEPACK BSS page slack, zero at load; next to
                                                 #   the field script's clone room 0x558FAD00..0x558FAE50)
# implied id -> bit-set of alignments (bit n = TAlignment n) for which a 0xC0 holder reports it enabled
IMPLY = [(0x43, 0x03), (0x92, 0x03), (0x6C, 0x34), (0x62, 0x20)]       # v3: 0x92 for PureGood too (level II via lvl), no 0xA0
ELIGIBLE = 0x37                                  # alignments that receive 0xC0 at all: 0,1,2,4,5
REGABIL, LSTRASG = 0x55750238, 0x55701150
DUR_VMT, DUR_CREATE, HPB_WORD20 = 0x5571DD68, 0x55764CD4, 0x557BB808
REGISTRY, GETABIL, REMOVEABIL = 0x558E92E8, 0x557501C0, 0x5577F6EC
GH_VMT = 0x557F5504                              # TGreatHail (the 208 donor)
REG_SITE = 0x557BCF6E                            # Second Wind's chained RegisterAbility call site
LVL_SITE = 0x557651EC                            # v3: TMultiLevelAbility.GetLevel's `call 0x55812400` (build_item_ability_levels.py)
CALL_CHAIN = {"reg": REG_SITE, "lvl": LVL_SITE}
HOLY, ISCLASS, TABSUNIT_REF = 0x92, 0x557010C0, 0x55710700
HEROITEMS_VMT, HEROINV_VMT = 0x55711738, 0x5571162C   # link-time VMTs (compared after removing the PIC delta)
JMP_CHAIN = {"fl": 0x5577F5E0, "pom": 0x55784391}
SLOT_CHAIN = {"fg": GH_VMT + 0xD8}
PREV_OFF = {"fl": 0, "pom": 4, "reg": 8, "fg": 12, "lvl": 16}

from keystone import Ks, KS_ARCH_X86, KS_MODE_32
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def build(d, prev):
    out = bytearray(HDR + 8); where = {}
    for k, off in PREV_OFF.items(): struct.pack_into("<I", out, off, prev[k])
    def place(name, src):
        while len(out) % 16: out.append(0)
        va = ZONE + len(out); where[name] = va; out.extend(asm_delta(src, va))
    while len(out) % 4: out.append(0)
    out += struct.pack("<ii", -1, len(NAME)); where["name"] = ZONE + len(out); out += NAME + b"\0"
    w20 = struct.unpack_from("<H", d, HPB_WORD20 - CODE_V2F)[0]
    place("reg", """
        call %(prev)#x
        push esi
        call $D
        pop esi
        sub esi, $D
        lea eax, [esi + %(vmt)#x]
        xor ecx, ecx
        mov dl, 1
        call %(create)#x
        mov dword ptr [eax + 0xc], %(aid)d
        mov byte ptr [eax + 0x24], 4
        mov byte ptr [eax + 0x28], 3
        mov word ptr [eax + 0x20], %(w20)d
        push eax
        lea edx, [esi + %(name)#x]
        add eax, 8
        call %(lstrasg)#x
        pop edx
        mov eax, ebx
        call %(reg)#x
        pop esi
        ret
    """ % {"prev": prev["reg"], "reg": REGABIL, "vmt": DUR_VMT, "create": DUR_CREATE, "aid": AB_SANCT, "w20": w20,
           "name": where["name"], "lstrasg": LSTRASG})
    # eligible(eax = TUnit) -> ZF clear (al = 1) when the unit may hold 0xC0 (alignment in ELIGIBLE, not a machine)
    place("elig", """
        push ebx
        push ecx
        push edx
        mov ebx, eax
        mov ecx, [eax]
        call dword ptr [ecx + 0x114]
        cmp al, 2
        je e_no
        mov eax, ebx
        mov ecx, [eax]
        call dword ptr [ecx + 0xfc]
        movzx eax, al
        cmp eax, 8
        jae e_no
        mov ecx, %(el)d
        bt ecx, eax
        jnc e_no
        mov al, 1
        jmp e_out
    e_no:
        xor eax, eax
    e_out:
        test al, al
        pop edx
        pop ecx
        pop ebx
        ret
    """ % {"el": ELIGIBLE})
    # sn_sync(eax = TUnit, dl = on): grant / remove 0xC0; all registers but eax preserved
    place("sync", """
        push ebx
        push ecx
        push edx
        push esi
        push edi
        mov esi, eax
        mov bl, dl
        test esi, esi
        jz s_out
        test bl, bl
        jz s_off
        mov eax, esi
        call %(elig)#x
        jz s_off
        mov eax, esi
        mov edx, %(ab)d
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x14c]
        test al, al
        jnz s_out
        call $D
        pop edi
        sub edi, $D
        mov eax, dword ptr [edi + %(registry)#x]
        mov eax, dword ptr [eax]
        mov eax, dword ptr [eax + 0x80]
        mov edx, %(ab)d
        call %(getabil)#x
        test eax, eax
        jz s_out
        mov edx, esi
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0xd0]
        jmp s_changed
    s_off:
        mov eax, esi
        mov edx, %(ab)d
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x14c]
        test al, al
        jz s_out
        mov eax, esi
        mov edx, %(ab)d
        call %(removeabil)#x
    s_changed:
        mov eax, esi
        mov edx, dword ptr [eax]
        call dword ptr [edx + 0x90]
    s_out:
        pop edi
        pop esi
        pop edx
        pop ecx
        pop ebx
        ret
    """ % {"elig": where["elig"], "ab": AB_SANCT, "registry": REGISTRY, "getabil": GETABIL, "removeabil": REMOVEABIL})
    # fl: GetAbilityEnabled prologue (eax = unit, edx = id; nothing pushed yet)
    cmps = "\n".join("        cmp edx, %#x\n        je f_%x" % (i, i) for i, _m in IMPLY)
    masks = "\n".join("    f_%x:\n        mov ecx, %#x\n        jmp f_chk" % (i, m) for i, m in IMPLY)
    place("fl", cmps + """
        jmp %(prev)#x
""" % {"prev": prev["fl"]} + masks + """
    f_chk:
        push ebx
        push esi
        push edi
        mov ebx, eax
        mov esi, edx
        mov edi, ecx
        mov edx, %(ab)d
        mov ecx, [eax]
        call dword ptr [ecx + 0x14c]
        test al, al
        jz f_restore
        mov eax, ebx
        mov ecx, [eax]
        call dword ptr [ecx + 0xfc]
        movzx eax, al
        cmp eax, 8
        jae f_restore
        bt edi, eax
        jnc f_restore
        cmp esi, %(panic)#x
        jne f_yes
        call $D
        pop ecx
        sub ecx, $D
        cmp byte ptr [ecx + %(guard)#x], 0
        jne f_yes
        mov byte ptr [ecx + %(guard)#x], 1
        push ecx
        mov eax, ebx
        mov edx, %(fearless)#x
        mov ecx, [eax]
        call dword ptr [ecx + 0x148]
        pop ecx
        mov byte ptr [ecx + %(guard)#x], 0
        test al, al
        jnz f_restore
    f_yes:
        mov al, 1
        pop edi
        pop esi
        pop ebx
        ret
    f_restore:
        mov eax, ebx
        mov edx, esi
        pop edi
        pop esi
        pop ebx
        jmp %(prev)#x
    """ % {"ab": AB_SANCT, "prev": prev["fl"], "panic": 0x6C, "fearless": 0x43, "guard": FL_GUARD})
    # pom: TUnitHS.PlaceOnMap tail (ebx = hs; the call's args already pushed) - everything preserved
    place("pom", """
        pushal
        mov eax, ebx
        mov edx, dword ptr [eax]
        call dword ptr [edx + 0x24]
        cmp eax, %(unitcls)#x
        jne p_out
        mov eax, dword ptr [ebx + 0x1c]
        test eax, eax
        jz p_out
        mov esi, dword ptr [eax + 0x4c]
        test esi, esi
        jz p_out
        xor edi, edi
        mov eax, dword ptr [ebx + 4]
        test eax, eax
        jz p_sync
        mov edx, %(fieldcls)#x
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x80]
        test eax, eax
        setnz al
        movzx edi, al
    p_sync:
        mov eax, esi
        mov edx, edi
        call %(sync)#x
    p_out:
        popal
        jmp %(prev)#x
    """ % {"unitcls": UNITHS_CLASSID, "fieldcls": FIELD_CLASSID, "sync": where["sync"], "prev": prev["pom"]})
    place("fg", """
        cmp dword ptr [eax + 0x10], %(sp)d
        je zero
        jmp %(prev)#x
    zero:
        mov eax, [esp + 4]
        xor edx, edx
        mov [eax], edx
        mov [eax + 4], edx
        mov [eax + 8], edx
        mov [eax + 0xc], edx
        mov word ptr [eax + 0x10], dx
        ret 8
    """ % {"sp": SPELL_ID, "prev": prev["fg"]})
    # lvl (v3): TMultiLevelAbility.GetLevel tail (ebx = ability, esi = owner (never nil here), eax = record or 0)
    place("lvl", """
        call %(prev)#x
        cmp dword ptr [ebx + 0xc], %(holy)#x
        jne l_ret
        push ecx
        push edx
        push edi
        push eax
        call $D
        pop edi
        sub edi, $D
        mov eax, esi
        mov edx, dword ptr [edi + %(absref)#x]
        call %(isclass)#x
        test al, al
        jz l_cont
        mov eax, esi
        jmp l_unit
    l_cont:
        mov eax, dword ptr [esi]
        sub eax, edi
        cmp eax, %(hitems)#x
        je l_hero
        cmp eax, %(hinv)#x
        jne l_done
    l_hero:
        mov eax, dword ptr [esi + 4]
        test eax, eax
        jz l_done
    l_unit:
        push eax
        mov edx, %(ab)d
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x14c]
        pop edx
        test al, al
        jz l_done
        mov eax, edx
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0xfc]
        movzx eax, al
        mov ecx, 2
        test eax, eax
        jz l_want
        mov ecx, 1
        cmp eax, 1
        jne l_done
    l_want:
        cmp dword ptr [esp], ecx
        jge l_done
        mov dword ptr [esp], ecx
    l_done:
        pop eax
        pop edi
        pop edx
        pop ecx
    l_ret:
        ret
    """ % {"prev": prev["lvl"], "holy": HOLY, "absref": TABSUNIT_REF, "isclass": ISCLASS, "hitems": HEROITEMS_VMT,
           "hinv": HEROINV_VMT, "ab": AB_SANCT})
    out[HDR:HDR + 5] = b"\xe9" + struct.pack("<i", where["sync"] - (EXP_SYNC + 5))
    zone = bytes(out)
    assert ZONE + len(zone) <= ZONE_END, hex(ZONE + len(zone))
    return zone, where


def jmp_target(b, va):
    return va + 5 + struct.unpack_from("<i", b, 1)[0] if b[0] == 0xE9 else None


def call_target(b, va):
    return va + 5 + struct.unpack_from("<i", b, 1)[0] if b[0] == 0xE8 else None


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--dll", default=DEFAULT_DLL)
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true"); ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read())
    rd = lambda va, n: bytes(d[va - CODE_V2F:va - CODE_V2F + n])
    u32 = lambda va: struct.unpack_from("<I", d, va - CODE_V2F)[0]
    inzone = lambda t: t is not None and ZONE <= t < ZONE_END
    zl = rd(ZONE, ZONE_END - ZONE)
    state, prev = {}, {}
    for k, va in JMP_CHAIN.items():
        t = jmp_target(rd(va, 5), va)
        if t is None: state[k] = "UNEXPECTED(%s)" % rd(va, 6).hex(); prev[k] = 0
        elif inzone(t): state[k] = "ours"; prev[k] = struct.unpack_from("<I", zl, PREV_OFF[k])[0]
        else: state[k] = "chain"; prev[k] = t
    for k, va in SLOT_CHAIN.items():
        t = u32(va)
        if inzone(t): state[k] = "ours"; prev[k] = struct.unpack_from("<I", zl, PREV_OFF[k])[0]
        else: state[k] = "chain"; prev[k] = t
    for k, va in CALL_CHAIN.items():
        t = call_target(rd(va, 5), va)
        if t is None: state[k] = "UNEXPECTED(%s)" % rd(va, 5).hex(); prev[k] = 0
        elif inzone(t): state[k] = "ours"; prev[k] = struct.unpack_from("<I", zl, PREV_OFF[k])[0]
        elif k == "reg" and t == REGABIL: state[k] = "UNEXPECTED(vanilla - apply patch_secondwind_v1.py first)"; prev[k] = 0
        else: state[k] = "chain"; prev[k] = t
    zone, where = build(bytes(d), prev)
    rl = reloc_set(bytes(d))
    sites = list(JMP_CHAIN.values()) + list(CALL_CHAIN.values())
    bad = [hex(r) for r in rl if ZONE - 3 <= r < ZONE_END or any(va - 3 <= r < va + 5 for va in sites)]
    noreloc = [k for k, va in SLOT_CHAIN.items() if va not in rl]
    zstate = "zero" if not any(zl) else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) \
        else "ours(old)" if any(s == "ours" for s in state.values()) else "DIFFERS"
    print("AoWEPACK sanctify: state %s | prev %s | zone %s (%d B: %s) | relocs in zone/sites %s | slots without reloc %s" % (
        state, {k: hex(v) for k, v in prev.items()}, zstate, len(zone),
        ", ".join("%s=%#x" % (k, v) for k, v in where.items() if k != "name"), bad or "none", noreloc or "none"))
    print("export: sn_sync %#x -> %#x" % (EXP_SYNC, where["sync"]))
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        cav = sorted((v, k) for k, v in where.items() if k != "name") + [(ZONE + len(zone), None)]
        for (va, nm), (nx, _n) in zip(cav, cav[1:]):
            print("  [%s]" % nm)
            for i in md.disasm(zone[va - ZONE:nx - ZONE], va):
                if i.mnemonic == "add" and i.op_str == "byte ptr [eax], al": break
                print("   %08X  %-18s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad or noreloc or any(s.startswith(("UNEXPECTED", "OTHER")) for s in state.values()) or zstate == "DIFFERS" \
            or any(p == 0 or inzone(p) for p in prev.values()):
        print("ABORT"); return 1
    if a.revert:
        if not all(s == "ours" for s in state.values()):
            print("ABORT revert: not (fully) applied, or another patch is chained in front: %s" % state); return 1
        for k, va in JMP_CHAIN.items(): d[va - CODE_V2F:va - CODE_V2F + 5] = hook_bytes("jmp", va, prev[k], 5)
        for k, va in SLOT_CHAIN.items(): struct.pack_into("<I", d, va - CODE_V2F, prev[k])
        for k, va in CALL_CHAIN.items(): d[va - CODE_V2F:va - CODE_V2F + 5] = hook_bytes("call", va, prev[k], 5)
        d[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
        with open(a.dll, "r+b") as f: f.write(bytes(d))
        print("reverted (chain points back to %s, zone zeroed)" % {k: hex(v) for k, v in prev.items()}); return 0
    if all(s == "ours" for s in state.values()) and zstate == "ours":
        print("already applied"); return 0
    if zstate == "ours(old)": print("older build of this patch detected -> rewriting the zone + every hook in place")
    d[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE); d[ZONE - CODE_V2F:ZONE - CODE_V2F + len(zone)] = zone
    for k, va in JMP_CHAIN.items(): d[va - CODE_V2F:va - CODE_V2F + 5] = hook_bytes("jmp", va, where[k], 5)
    for k, va in SLOT_CHAIN.items(): struct.pack_into("<I", d, va - CODE_V2F, where[k])
    for k, va in CALL_CHAIN.items(): d[va - CODE_V2F:va - CODE_V2F + 5] = hook_bytes("call", va, where[k], 5)
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(a.dll, BAK_SUFFIX)
    if a.dll == DEFAULT_DLL and not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    with open(a.dll, "r+b") as f: f.write(bytes(d))
    assert open(a.dll, "rb").read() == bytes(d); print("Written and verified"); return 0


if __name__ == "__main__":
    sys.exit(main())
