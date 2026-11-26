#!/usr/bin/env python3
r"""
Martyr (360) + Cleansing Flame (361): the Life/Fire tier-1/2 combat spells (2026-10-13).

Both are registered by patch_dual_sphere_spells_v1.py as TRemedy instances (Remedy = Life T1: heals +5 and removes
0x5D Cursed, 0x60 Poisoned, 0x6C, 0x35, 0x5C Stunned, 0x7F Burning).  TRemedy's two spell-specific methods are
hooked at their entry and dispatch on the spell id [spell+0x10]; vanilla Remedy (id 35) falls through untouched.

  TRemedy.ExecuteSpell  VMT+0xB4 = 0x557E736C (eax = spell, edx = caster, ecx = target TUnit; ret 8)
     360 Martyr:  ValidTarget (VMT+0x9C), then grant ability 0xB0 "Martyr" = ability.Expand(unit) (VMT+0xD0) +
                  unit.Changed (VMT+0x90, refreshes the cached stat deltas +0x44..47 - patch_bloodbath_v1.py lesson).
     361 Cleansing Flame: ValidTarget, heal +3 capped at max (the vanilla +5 code with 3), remove Remedy's list
                  WITHOUT Burning plus 0x5F Frozen, 0x5E Entangled, 0x61 Webbed, 0x30 Seduced, 0x95 Charmed,
                  0x96 Dominated (owner VMT+0x98 RemoveAbility), then inflict 0x7F Burning (Expand + Changed).
  TRemedy.ValidTarget   VMT+0x9C = 0x557E7434 (same registers; bl = TUnitSpell base check 0x5577ACAC first)
     360: base check AND the unit does not already carry 0xB0 (VMT+0x148 GetAbilityEnabled).
     361: base check AND (HP < max OR any of the cleansable statuses above).
  Range: Martyr pokes [spell+0x38] = -1 (TUnitSpell.ActivateCombat 0x5577B04E: -1 = no range limit); Cleansing
  keeps Remedy's 12.  AI: TRemedy inherits the EMPTY TCombatSpell AI valuers (+0x84 0x55779490 / +0x98
  0x5577967C zero their result, +0x90 is `ret`), so the AI never casts either - as asked for Martyr.

  The Martyr ability 0xB0 = a second THighPrayerBlessingAbility instance (VMT 0x557B5684: TDurationAbility, mode
  byte +0x28 = 3 "combat only" -> TDurationAbility.CombatDone removes it and GetName appends "(combat only)";
  +0x60 GetDefense / +0x64 GetResistance already return 2).  Registered by splicing the vanilla
  `call RegisterAbility` @0x557BCF39 (ebx = TAbilityControl there): replay, Create (class cell 0x557B5644, ctor; ecx = 0 like the
  vanilla site 0x557BCD86 - TAbility.Create takes a 3rd parameter in ecx, garbage there = Runtime error 216 at init)
  0x557BB764), [+0xC] = 0xB0, LStrAsg name "Martyr", RegisterAbility.  Three slots of THighPrayerBlessingAbility's
  OWN VMT are repointed to caves (their relocs stay valid - the caves are image addresses):
     +0x5C GetAttack  0x557B56E0 -> ga: 2 for id 0xB0, else the base 0 (High Prayer's own blessing unchanged)
     +0x68 GetDamage  0x557B56EC -> gd: same
     +0xFC CombatDone 0x557B5780 -> cd: for id 0xB0 (eax = ability, edx = TCombatUnit) call the combat unit's
           DestroyObject (VMT+0x120 - exactly what TDecayAbility.CombatDone 0x557BA784 does for Mind Decay)
           unless it is already destroyed ([cu+0x47] & 1), then TDurationAbility.CombatDone 0x55764E00.
  The ability's description = Ability.pfs record 0xB0+10 (patch_ability_pfs_martyr.py); re-run
  patch_tcablist_ceiling_v1.py / patch_aowx_banner_ceilings_v1.py after it (they size their id ceiling from the pfs).

Caves 0x55862700.. (CODE zero tail; PIC: rel32 + call/pop delta for the two globals).  Backup
<game>\backup\AoWEPACK.dll.bak_martyr.  Surgical --revert.  Re-apply re-syncs the zone.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DEFAULT_DLL = game_file("AoWEPACK.dll")
BAK_SUFFIX = ".bak_martyr"
BASE, CODE_V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x55862700, 0x55862C00      # next free AoWEPACK cave 0x55862C00
MARTYR, CLEANSE = 360, 361
ABIL_MARTYR, ABIL_BURNING = 0xB0, 0x7F
ABCTRL = 0x558E92E8                 # [[ABCTRL]+0x80] = the ability list GetAbility works on (High Prayer CA idiom @0x557F7ED5)
GETABILITY = 0x557501C0             # eax = list, edx = id -> eax = ability
BASECHECK = 0x5577ACAC              # TUnitSpell target check (eax spell, edx caster, ecx unit) -> al
EX_RESUME, EX_EPI = 0x557E7379, 0x557E742A     # ExecuteSpell: after the replayed bytes / epilogue (eax = result)
VT_RESUME, VT_EPI = 0x557E743A, 0x557E74DB     # ValidTarget: the base-check call / epilogue (eax = result)
HPB_CELL, HPB_CREATE = 0x557B5644, 0x557BB764  # THighPrayerBlessingAbility class cell (holds the VMT) / ctor
HPB_VMT = 0x557B5684
LSTRASG, REGABIL = 0x55701150, 0x55750238
DUR_COMBATDONE = 0x55764E00
CLEANSE_REMOVE = [0x5D, 0x60, 0x6C, 0x35, 0x5C, 0x5F, 0x5E, 0x61, 0x30, 0x95, 0x96]
CLEANSE_CHECK = [0x60, 0x5C, 0x6C, 0x35, 0x5D, 0x5F, 0x5E, 0x61, 0x30, 0x95, 0x96]

# (site VA, original bytes, hook kind, cave)
HOOKS = [(0x557E736C, bytes.fromhex("558bec515356"), "jmp", "ex"),
         (0x557E7434, bytes.fromhex("53568bf18bce"), "jmp", "vt"),
         (0x557BCF39, bytes.fromhex("e8fa32f9ff"), "call", "reg")]
# (VMT slot VA, original pointer, cave)
SLOTS = [(HPB_VMT + 0x5C, 0x5574E990, "ga"), (HPB_VMT + 0x68, 0x5574E99C, "gd"), (HPB_VMT + 0xFC, DUR_COMBATDONE, "cd")]
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, va):
    return bytes(ks.asm(src, va)[0])


def build():
    out = bytearray(); where = {}
    # the ability name: Delphi AnsiString literal (refcount -1, length, chars, NUL); the pointer is to the chars
    lit = b"Martyr"
    out += struct.pack("<ii", -1, len(lit)); where["name"] = ZONE + len(out); out += lit + b"\0"
    while len(out) % 16: out.append(0)

    def place(name, src):
        while len(out) % 16: out.append(0)
        va = ZONE + len(out); where[name] = va
        out.extend(asm(src, va))

    # getab: edx = ability id -> eax = ability object (ecx clobbered).  PIC: the control global via the delta.
    place("getab", """
        push edx
        call next
    next:
        pop ecx
        sub ecx, next
        mov eax, [ecx + %(ctrl)#x]
        mov eax, [eax]
        mov eax, [eax + 0x80]
        pop edx
        call %(get)#x
        ret
    """ % {"ctrl": ABCTRL, "get": GETABILITY})

    unit_calls = lambda ids, slot: "\n".join("mov edx, %#x\n mov eax, ebx\n mov ecx, [eax]\n call [ecx + %#x]" % (i, slot) for i in ids)
    place("ex", """
        push ebp
        mov ebp, esp
        push ecx
        push ebx
        push esi
        mov ebx, ecx
        mov [ebp - 4], edx
        mov esi, eax
        cmp dword ptr [esi + 0x10], %(martyr)d
        je martyr
        cmp dword ptr [esi + 0x10], %(cleanse)d
        je cleanse
        jmp %(resume)#x
    martyr:
        mov ecx, ebx
        mov edx, [ebp - 4]
        mov eax, esi
        mov esi, [eax]
        call [esi + 0x9c]
        test al, al
        je fail
        mov edx, %(abil)d
        call %(getab)#x
        mov edx, ebx
        mov ecx, [eax]
        call [ecx + 0xd0]
        mov eax, ebx
        mov edx, [eax]
        call [edx + 0x90]
        mov al, 1
        jmp %(epi)#x
    fail:
        xor eax, eax
        jmp %(epi)#x
    cleanse:
        mov ecx, ebx
        mov edx, [ebp - 4]
        mov eax, esi
        mov esi, [eax]
        call [esi + 0x9c]
        test al, al
        je fail
        mov eax, ebx
        mov edx, [eax]
        call [edx + 0xe0]
        movsx esi, al
        add esi, 3
        mov eax, ebx
        mov edx, [eax]
        call [edx + 0xd0]
        movsx eax, al
        cmp esi, eax
        jle capped
        mov eax, ebx
        mov edx, [eax]
        call [edx + 0xd0]
        movsx esi, al
    capped:
        mov edx, esi
        mov eax, ebx
        mov ecx, [eax]
        call [ecx + 0xe4]
        %(removes)s
        mov edx, %(burn)d
        call %(getab)#x
        mov edx, ebx
        mov ecx, [eax]
        call [ecx + 0xd0]
        mov eax, ebx
        mov edx, [eax]
        call [edx + 0x90]
        mov al, 1
        jmp %(epi)#x
    """ % {"martyr": MARTYR, "cleanse": CLEANSE, "resume": EX_RESUME, "epi": EX_EPI, "abil": ABIL_MARTYR,
           "burn": ABIL_BURNING, "getab": where["getab"], "removes": unit_calls(CLEANSE_REMOVE, 0x98)})

    checks = "\n".join("mov edx, %#x\n mov eax, esi\n mov ecx, [eax]\n call [ecx + 0x148]\n test al, al\n jne yes" % i for i in CLEANSE_CHECK)
    place("vt", """
        push ebx
        push esi
        mov esi, ecx
        mov ecx, esi
        cmp dword ptr [eax + 0x10], %(martyr)d
        je mv
        cmp dword ptr [eax + 0x10], %(cleanse)d
        je cv
        jmp %(resume)#x
    mv:
        call %(base)#x
        test al, al
        je no
        mov edx, %(abil)d
        mov eax, esi
        mov ecx, [eax]
        call [ecx + 0x148]
        test al, al
        jne no
        jmp yes
    cv:
        call %(base)#x
        test al, al
        je no
        mov eax, esi
        mov edx, [eax]
        call [edx + 0xe0]
        mov bl, al
        mov eax, esi
        mov edx, [eax]
        call [edx + 0xd0]
        cmp bl, al
        jne yes
        %(checks)s
    no:
        xor eax, eax
        jmp %(epi)#x
    yes:
        mov al, 1
        jmp %(epi)#x
    """ % {"martyr": MARTYR, "cleanse": CLEANSE, "resume": VT_RESUME, "base": BASECHECK, "abil": ABIL_MARTYR,
           "checks": checks, "epi": VT_EPI})

    for nm in ("ga", "gd"):
        place(nm, """
            cmp dword ptr [eax + 0xc], %d
            jne base
            mov al, 2
            ret
        base:
            xor eax, eax
            ret
        """ % ABIL_MARTYR)
    place("cd", """
        cmp dword ptr [eax + 0xc], %(abil)d
        jne orig
        test byte ptr [edx + 0x47], 1
        jnz orig
        push eax
        push edx
        mov eax, edx
        mov edx, [eax]
        call [edx + 0x120]
        pop edx
        pop eax
    orig:
        jmp %(orig)#x
    """ % {"abil": ABIL_MARTYR, "orig": DUR_COMBATDONE})
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
    """ % {"reg": REGABIL, "cell": HPB_CELL, "create": HPB_CREATE, "abil": ABIL_MARTYR, "name": where["name"], "lstrasg": LSTRASG})
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
    ap.add_argument("--without", default="", help="comma-separated cave names to leave unhooked (bisecting only)")
    a = ap.parse_args()
    skip = set(x for x in a.without.split(",") if x)
    d = open(a.dll, "rb").read()
    zone, where = build()
    hooks = [(va, orig, hook(va, orig, kind, where[cave])) for va, orig, kind, cave in HOOKS if cave not in skip]
    slots = [(va, struct.pack("<I", orig), struct.pack("<I", where[cave])) for va, orig, cave in SLOTS if cave not in skip]
    live = [bytes(d[va - CODE_V2F:va - CODE_V2F + len(orig)]) for va, orig, _h in hooks + slots]
    zl = d[ZONE - CODE_V2F:ZONE_END - CODE_V2F]
    rl = reloc_set(d)
    bad = [r for r in rl if ZONE <= r < ZONE_END or any(va <= r < va + len(orig) for va, orig, _h in hooks)]
    for va, _o, _n in slots: assert va in rl, "VMT slot %#x has no reloc" % va      # the slots must stay relocated
    state = ["vanilla" if l == orig else "ours" if l == new else "OTHER" for (va, orig, new), l in zip(hooks + slots, live)]
    zstate = "zero" if not any(zl) else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else "DIFFERS"
    print("sites %s | zone %s | relocs %s | caves %s" % (state, zstate, bad or "none", ", ".join("%s=%#x" % kv for kv in where.items())))
    if bad or "OTHER" in state: print("ABORT"); return 1
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        names = sorted(((v, k) for k, v in where.items() if k != "name"))
        for (s, name), nxt in zip(names, [n[0] for n in names[1:]] + [ZONE + len(zone)]):
            print("  --", name)
            for i in md.disasm(zone[s - ZONE:nxt - ZONE], s): print("   %08X  %-16s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if a.revert:
        out = bytearray(d)
        for (va, orig, _n), st in zip(hooks + slots, state):
            if st == "ours": out[va - CODE_V2F:va - CODE_V2F + len(orig)] = orig
        out[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
        write_inplace(a.dll, bytes(out)); print("reverted"); return 0
    if all(s == "ours" for s in state) and zstate == "ours":
        print("already applied"); return 0
    if "ours" not in state and zstate != "zero": print("ABORT: zone not zero on a vanilla dll"); return 1
    out = bytearray(d)
    out[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
    out[ZONE - CODE_V2F:ZONE - CODE_V2F + len(zone)] = zone
    for va, orig, new in hooks + slots: out[va - CODE_V2F:va - CODE_V2F + len(orig)] = new
    print("%d bytes change, zone %d B" % (sum(1 for x, y in zip(d, out) if x != y), len(zone)))
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(a.dll, BAK_SUFFIX)
    if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    write_inplace(a.dll, bytes(out)); assert open(a.dll, "rb").read() == bytes(out); print("Written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
