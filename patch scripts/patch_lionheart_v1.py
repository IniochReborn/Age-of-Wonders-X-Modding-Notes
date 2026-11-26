#!/usr/bin/env python3
r"""
Lionheart (373): the Earth/Fire tier-2 unit enchantment - grants FEARLESS and +2 DAMAGE (2026-10-13).

Registered by patch_dual_sphere_spells_v1.py as a TDarkGift clone (Dark Gift = Death T1, id 0x4D: "Death Strike and
+1 damage").  RE (AoWEPACK.dll):
  TDarkGift.Create 0x557E83B0 (cell 0x557E675C, site 0x557E8E2A): id [+0x10]=0x4D, [+0x14]=5, sphere [+0x20]=2,
     tier [+0x21]=3, range [+0x38]=0xC, [+0x3C]=3 (duration mode copied into the ability data), [+0x40]=0xE1,
     [+0x30]=5.  NO field holds the granted ability or the bonus:
  TDarkGift.ExecuteSpell VMT+0xB4 = 0x557E8478 (eax spell, edx caster, ecx TUnit; ret 8): ValidTarget (VMT+0x9C),
     unit.ExpandAbility(0xA9) (unit VMT+0x94), GetAbilityData(unit, 0xA9) -> [data+0x10] = the TUnitEnchantment:
     VMT+0x54(spell upkeep [spell+0x1C]), VMT+0x58(caster player byte [caster+0x24]), [data+0x14] = [spell+0x3C].
  TDarkGift.ValidTarget   VMT+0x9C = 0x557E84E8: TUnitSpell base check 0x5577ACAC AND NOT unit.GetAbilityEnabled(0xA9)
     (unit VMT+0x148).  The ability id 0xA9 is an IMMEDIATE in both (3 sites: 0x557E8499, 0x557E84AC, 0x557E84F9).
  Ability 0xA9 = TDarkGiftEnchantment (registered @0x557BCD9D: cell 0x557B935C, ctor 0x557BB69C, VMT 0x557B939C,
     class TUnitEnchantmentAbility): its only overrides are VMT+0x68 GetDamage 0x557BB730 (`mov al,1`) and +0x114
     GetAIUpkeepPriority.  The DEATH STRIKE is not granted at all - TStrikeAbility.GetDamageTypes 0x55766EBE checks
     "unit has 0x12 OR unit has 0xA9".  Fearless (0x43) is likewise checked by id at exactly four sites:
     TStrikeCA.Generate 0x557668F5 (TCombatUnit VMT+0xA8 HasAbility, esi), TFastCombatTerrorCA.Generate 0x557F983D
     and TTacticalCombatTerrorCA.Generate 0x557F99C1 (same, ebx), TAbstractUnit.ExecuteLifeMasteryFearRole
     0x55780BB6 (TAbstractUnit VMT+0x148 GetAbilityEnabled, ebx) - all `mov edx,0x43 / mov eax,REG / mov ecx,[eax] /
     call [ecx+SLOT]` (15 B, no relocs).
So, exactly like Martyr (patch_martyr_cleansing_v1.py): the Lionheart ability 0xB1 = a SECOND TDarkGiftEnchantment
instance (spliced after the vanilla `call RegisterAbility` @0x557BCDAF; ecx = 0 for the ctor), and:
  * ExecuteSpell / ValidTarget are re-implemented in caves (entry hooks, 6 B each) choosing 0xA9 or 0xB1 by
    [spell+0x10] == 373 - vanilla Dark Gift behaves exactly as before;
  * TDarkGiftEnchantment VMT+0x68 GetDamage -> cave: 2 for id 0xB1, else 1;
  * the four Fearless checks -> caves that also accept 0xB1 (15-B site = call + 10 nops, the cave returns al);
  * Death Strike is NOT conferred (GetDamageTypes checks 0xA9 only) - as wanted.
The ability's name "Lionheart" lives in the cave (LStrAsg into [ability+8] at registration); its description =
Ability.pfs record 0xB1+10 (clone patch_ability_pfs_martyr.py); then re-run patch_tcablist_ceiling_v1.py and
patch_aowx_banner_ceilings_v1.py with 0xB1 added to their LADDER (ceiling 0xB2).
Caves 0x55863000..0x55863200 (CODE zero tail, no relocs; PIC: rel32 + call/pop delta for the cell/name).
Backup <game>\backup\AoWEPACK.dll.bak_lionheart.  Surgical --revert.  Dry-run default.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DEFAULT_DLL = game_file("AoWEPACK.dll")
BAK_SUFFIX = ".bak_lionheart"
BASE, CODE_V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x55863300, 0x55863500       # 2026-10-13: 0x55862C00..0x55863000 = Forge Blast/Arms Race caves, 0x55863000..0x55863300 = Oil Spring
LION, ABIL_LION, ABIL_DARKGIFT, FEARLESS = 373, 0xB1, 0xA9, 0x43
DGE_CELL, DGE_CREATE, DGE_VMT = 0x557B935C, 0x557BB69C, 0x557B939C     # TDarkGiftEnchantment class cell / ctor / VMT
LSTRASG, REGABIL = 0x55701150, 0x55750238
BASECHECK, GETABILITYDATA = 0x5577ACAC, 0x5574F1C4
# (site VA, original bytes, hook kind, cave)
HOOKS = [(0x557E8478, bytes.fromhex("558bec515356"), "jmp", "ex"),           # TDarkGift.ExecuteSpell entry
         (0x557E84E8, bytes.fromhex("53568bf18bce"), "jmp", "vt"),           # TDarkGift.ValidTarget entry
         (0x557BCDAF, bytes.fromhex("e88434f9ff"), "call", "reg"),           # call RegisterAbility after the vanilla TDarkGiftEnchantment
         (0x557668F5, bytes.fromhex("ba430000008bc68b08ff91a8000000"), "call", "f1"),   # TStrikeCA.Generate (esi, +0xA8)
         (0x55780BB6, bytes.fromhex("ba430000008bc38b08ff9148010000"), "call", "f2"),   # ExecuteLifeMasteryFearRole (ebx, +0x148)
         (0x557F983D, bytes.fromhex("ba430000008bc38b08ff91a8000000"), "call", "f3"),   # TFastCombatTerrorCA.Generate (ebx, +0xA8)
         (0x557F99C1, bytes.fromhex("ba430000008bc38b08ff91a8000000"), "call", "f4")]   # TTacticalCombatTerrorCA.Generate (ebx, +0xA8)
# (VMT slot VA, original pointer, cave)
SLOTS = [(DGE_VMT + 0x68, 0x557BB730, "gd")]
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, va):
    return bytes(ks.asm(src, va)[0])


def build():
    out = bytearray(); where = {}
    lit = b"Lionheart"
    out += struct.pack("<ii", -1, len(lit)); where["name"] = ZONE + len(out); out += lit + b"\0"
    while len(out) % 16: out.append(0)

    def place(name, src):
        while len(out) % 16: out.append(0)
        va = ZONE + len(out); where[name] = va
        out.extend(asm(src, va))

    # ex: TDarkGift.ExecuteSpell re-implemented; the ability id is 0xA9 unless the spell is Lionheart.
    place("ex", """
        push ebp
        mov ebp, esp
        push ecx
        push ebx
        push esi
        push edi
        mov esi, ecx
        mov [ebp-4], edx
        mov ebx, eax
        mov ecx, esi
        mov edx, [ebp-4]
        mov eax, ebx
        mov edi, [eax]
        call dword ptr [edi+0x9c]
        test al, al
        je fail
        mov edx, %(dg)d
        cmp dword ptr [ebx+0x10], %(lion)d
        jne nolion1
        mov edx, %(lab)d
    nolion1:
        push edx
        mov eax, esi
        mov ecx, [eax]
        call dword ptr [ecx+0x94]
        pop edx
        test al, al
        je ok
        mov eax, esi
        call %(gad)#x
        mov esi, [eax+0x10]
        mov edx, [ebx+0x1c]
        mov eax, esi
        mov ecx, [eax]
        call dword ptr [ecx+0x54]
        mov eax, [ebp-4]
        mov dl, byte ptr [eax+0x24]
        mov eax, esi
        mov ecx, [eax]
        call dword ptr [ecx+0x58]
        mov al, byte ptr [ebx+0x3c]
        mov [esi+0x14], al
    ok:
        mov al, 1
        jmp done
    fail:
        xor eax, eax
    done:
        pop edi
        pop esi
        pop ebx
        pop ecx
        pop ebp
        ret 8
    """ % {"dg": ABIL_DARKGIFT, "lion": LION, "lab": ABIL_LION, "gad": GETABILITYDATA})

    # vt: TDarkGift.ValidTarget re-implemented (eax spell, edx caster, ecx unit -> al): base check AND not already enchanted.
    place("vt", """
        push ebx
        push esi
        push edi
        mov edi, eax
        mov esi, ecx
        mov ecx, esi
        call %(base)#x
        mov ebx, eax
        test bl, bl
        je no
        mov edx, %(dg)d
        cmp dword ptr [edi+0x10], %(lion)d
        jne nolion2
        mov edx, %(lab)d
    nolion2:
        mov eax, esi
        mov ecx, [eax]
        call dword ptr [ecx+0x148]
        test al, al
        je yes
    no:
        xor eax, eax
        jmp done
    yes:
        mov al, 1
    done:
        pop edi
        pop esi
        pop ebx
        ret
    """ % {"base": BASECHECK, "dg": ABIL_DARKGIFT, "lion": LION, "lab": ABIL_LION})

    # gd: TDarkGiftEnchantment.GetDamage (eax = ability): 2 for Lionheart, 1 for Dark Gift.
    place("gd", """
        cmp dword ptr [eax+0xc], %(lab)d
        mov al, 1
        jne r
        mov al, 2
    r:
        ret
    """ % {"lab": ABIL_LION})

    # f1..f4: the Fearless checks accept 0xB1 too.  Site = `mov edx,0x43 / mov eax,REG / mov ecx,[eax] / call [ecx+SLOT]`.
    for name, reg, slot in (("f1", "esi", 0xA8), ("f2", "ebx", 0x148), ("f3", "ebx", 0xA8), ("f4", "ebx", 0xA8)):
        place(name, """
            mov edx, %(fl)d
            mov eax, %(reg)s
            mov ecx, [eax]
            call dword ptr [ecx+%(slot)#x]
            test al, al
            jnz d
            mov edx, %(lab)d
            mov eax, %(reg)s
            mov ecx, [eax]
            call dword ptr [ecx+%(slot)#x]
        d:
            ret
        """ % {"fl": FEARLESS, "reg": reg, "slot": slot, "lab": ABIL_LION})

    # reg: after the vanilla RegisterAbility(TDarkGiftEnchantment): a second instance, id 0xB1, name "Lionheart".
    place("reg", """
        call %(reg)#x
        push esi
        call next
    next:
        pop esi
        sub esi, next
        lea eax, [esi + %(cell)#x]
        mov eax, [eax]
        xor ecx, ecx
        mov dl, 1
        call %(create)#x
        mov dword ptr [eax + 0xc], %(abil)d
        push eax
        lea edx, [esi + %(name)#x]
        add eax, 8
        call %(lstrasg)#x
        pop edx
        mov eax, ebx
        call %(reg)#x
        pop esi
        ret
    """ % {"reg": REGABIL, "cell": DGE_CELL, "create": DGE_CREATE, "abil": ABIL_LION, "name": where["name"], "lstrasg": LSTRASG})
    assert ZONE + len(out) <= ZONE_END, hex(ZONE + len(out))
    return bytes(out), where


def hook(va, orig, kind, target):
    return (b"\xe9" if kind == "jmp" else b"\xe8") + struct.pack("<i", target - (va + 5)) + b"\x90" * (len(orig) - 5)


def reloc_set(d):
    pe = struct.unpack_from("<I", d, 0x3C)[0]; opt = struct.unpack_from("<H", d, pe + 20)[0]; nsec = struct.unpack_from("<H", d, pe + 6)[0]
    secs = [struct.unpack_from("<IIII", d, pe + 24 + opt + 40 * k + 8) for k in range(nsec)]
    rrva, rsz = struct.unpack_from("<II", d, pe + 24 + 0x88)
    def r2f(rva):
        for vs, va, rs, ro in secs:
            if va <= rva < va + max(vs, rs): return ro + rva - va
    p, end, out = r2f(rrva), r2f(rrva) + rsz, set()
    while p < end:
        page, size = struct.unpack_from("<II", d, p)
        if size < 8: break
        for q in range(p + 8, p + size, 2):
            e = struct.unpack_from("<H", d, q)[0]
            if e >> 12 == 3: out.add(BASE + page + (e & 0xFFF))
        p += size
    return out


def write_inplace(path, data):
    with open(path, "r+b") as f:
        f.seek(0); f.write(data); f.truncate(len(data))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dll", default=DEFAULT_DLL)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    d = open(a.dll, "rb").read()
    zone, where = build()
    rl = reloc_set(d)
    bad = [hex(r) for r in rl if ZONE <= r < ZONE_END or any(va <= r < va + len(o) for va, o, _k, _c in HOOKS)]
    # VMT slots carry relocs by design (image addresses) - they stay valid for the caves
    states = []
    for va, orig, kind, cave in HOOKS:
        live = d[va - CODE_V2F:va - CODE_V2F + len(orig)]
        states.append("vanilla" if live == orig else "ours" if live == hook(va, orig, kind, where[cave]) else "OTHER")
    for sva, orig, cave in SLOTS:
        live = struct.unpack_from("<I", d, sva - CODE_V2F)[0]
        states.append("vanilla" if live == orig else "ours" if live == where[cave] else "OTHER")
    zl = d[ZONE - CODE_V2F:ZONE_END - CODE_V2F]
    zstate = "zero" if not any(zl) else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else "DIFFERS"
    print("sites %s | zone %s (%d B) | relocs %s | caves %s" % (states, zstate, len(zone), bad or "none", {k: hex(v) for k, v in where.items()}))
    if bad or "OTHER" in states: print("ABORT"); return 1
    if a.dis:
        import capstone
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(zone, ZONE): print("   %08X  %-16s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    out = bytearray(d)
    if a.revert:
        for va, orig, kind, cave in HOOKS: out[va - CODE_V2F:va - CODE_V2F + len(orig)] = orig
        for sva, orig, cave in SLOTS: struct.pack_into("<I", out, sva - CODE_V2F, orig)
        out[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
        write_inplace(a.dll, bytes(out)); print("reverted"); return 0
    if all(s == "ours" for s in states) and zstate == "ours": print("already applied"); return 0
    out[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE); out[ZONE - CODE_V2F:ZONE - CODE_V2F + len(zone)] = zone
    for va, orig, kind, cave in HOOKS: out[va - CODE_V2F:va - CODE_V2F + len(orig)] = hook(va, orig, kind, where[cave])
    for sva, orig, cave in SLOTS: struct.pack_into("<I", out, sva - CODE_V2F, where[cave])
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(a.dll, BAK_SUFFIX)
    if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    write_inplace(a.dll, bytes(out)); assert open(a.dll, "rb").read() == bytes(out); print("Written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
