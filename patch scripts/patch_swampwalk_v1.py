#!/usr/bin/env python3
r"""
Swampwalk (382): the Earth/Water tier-3 unit enchantment - grants FORESTRY (3), POISON IMMUNITY (0xA) and SWIMMING (2)
while enchanted (2026-10-15).

Registered by patch_dual_sphere_spells_v1.py as a TWaterWalking clone (Water Walking = Water T2, id 0x2A, pfs key 52).
RE (AoWEPACK.dll):
  TWaterWalking  cell 0x557E6274 / VMT 0x557E62B4 / ctor 0x557E7CD8 (id [+0x10]=0x2A, [+0x14]=5, sphere 6, tier 2,
     range [+0x38]=0xC, duration mode [+0x3C]=6); registered @0x557E8DA2..0x557E8DB0.
  ExecuteSpell VMT+0xB4 = 0x557E7D90 (eax spell, edx caster, ecx TUnit; ret 8): ValidTarget (VMT+0x9C), unit
     ExpandAbility(0xA4) (unit VMT+0x94), GetAbilityData(unit, 0xA4) 0x5574F1C4 -> [data+0x10] = the TUnitEnchantment:
     VMT+0x54(spell upkeep [spell+0x1C]), VMT+0x58(caster player [caster+0x24]), [ench+0x14] = [spell+0x3C].
     The ability id 0xA4 is an IMMEDIATE (0x557E7DB1, 0x557E7DC4).
  ValidTarget VMT+0x9C = 0x557E7E00: TUnitSpell base check 0x5577ACAC AND NOT (Sailing 0x17 / Swimming 2 / Water
     Walking 0xA4 / Flying 1 / Floating 0x3B) via unit VMT+0x148.
  Ability 0xA4 = TWaterWalkingEnchantment (cell 0x557B8CB0, VMT 0x557B8CF0, ctor 0x557BB9B0 sets [+0xC]=0xA4; class
     TUnitEnchantmentAbility; own override VMT+0xD4 0x557BBA44 = base expand check + a map refresh of the unit's
     hex - harmless/helpful for a movement enchantment); registered by `mov eax,ebx / call RegisterAbility` @0x557BCCC9.
  Water walking itself is granted BY ID: the movement-type builder 0x5574F764 asks VMT+0x88 for 0xA4 explicitly, so a
     second instance of the class with another id grants nothing by itself.
  The ability ids Swampwalk must imply (Ability.pfs descriptions, key = id + 10): 2 Swimming ("travel across water"),
     3 Forestry ("less restricted movement through forests"), 0xA Poison Immunity.  Vanilla precedent: Liquid Form
     0xA6 = "Swimming and Physical Protection" by the same by-id implication.
  Every by-id ability query ends in one of two bodies (both entered AFTER patch_earthlife_blessings_v1.py's w1/w2
     prologue hooks, which jump back into them):
       TAbilityOwner.GetAbilityEnabled 0x5574FD68 (= VMT+0x88 of TAbstractUnit/TUnit/TAdjustableUnit/THero/TLeader;
         used by the movement-type builder 0x5574F764 and the immunity/protection builders 0x5574F97C/0x5574FAD0);
       TAbstractUnit.GetAbilityEnabled 0x5577F5E0 (VMT+0x148 via patch_grounded_melee_v1.py's stubs; THero/TLeader's
         0x55812760 calls it first; TCombatUnit.HasAbility VMT+0xA8 -> [cu+0x4C] VMT+0x148 = every tactical check).
     Both end their "not present / not enabled" path in the same 5 bytes `xor eax,eax / pop esi / pop ebx / ret`
     (0x5574FD98, 0x5577F612; ebx = owner, esi = id).
So:
  * reg  : after the vanilla RegisterAbility(TWaterWalkingEnchantment) @0x557BCCC9 (call splice): a second instance,
           id 0xBA, name "Swampwalk" (LStrAsg into [ability+8]); description = Ability.pfs record 196
           (patch_swampwalk_ability_pfs_v1.py).
  * ex/vt: TWaterWalking.ExecuteSpell / ValidTarget entry hooks (6 B jmp each) - spell id 382 takes our re-implementation
           (ability 0xBA; valid = base check AND not already Swampwalk), every other spell replays the 6 bytes and
           continues in vanilla.  Upkeep, caster and duration mode are set exactly as vanilla does for Water Walking,
           so dispel / expiry / unpaid upkeep remove 0xBA through the generic TUnitEnchantment path (no orphan).
  * t1/t2: the two "return false" tails -> asked for 2, 3 or 0xA and the owner HAS 0xBA (own-bitset test: VMT+0x4C on
           the TAbilityOwner path, VMT+0x14C on the TAbstractUnit path - no GetAbilityEnabled recursion) -> return 1.
           Live, derived from the enchantment: nothing to add or remove, save/load-safe, MP-deterministic.
Caves 0x55822000..0x55824000 (CODE zero gap, verified; PIC: rel32 within the image + call/pop delta for the cell and
the name literal).  Backup <game>\backup\AoWEPACK.dll.bak_swampwalk.  Surgical --revert.  Dry-run default.
After applying: append the record 196 description (patch_swampwalk_ability_pfs_v1.py) and add 0xBA to the ceiling
scripts' LADDER (see that script).
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DEFAULT_DLL = game_file("AoWEPACK.dll")
BAK_SUFFIX = ".bak_swampwalk"
BASE, CODE_V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x55822000, 0x55824000
SPELL, ABIL_SW, ABIL_WW = 382, 0xBA, 0xA4
IMPLIED = (2, 3, 0xA)                                    # Swimming, Forestry, Poison Immunity
WWE_CELL, WWE_CREATE = 0x557B8CB0, 0x557BB9B0            # TWaterWalkingEnchantment class cell / ctor
LSTRASG, REGABIL = 0x55701150, 0x55750238
BASECHECK, GETABILITYDATA = 0x5577ACAC, 0x5574F1C4
EX_RESUME, VT_RESUME = 0x557E7D96, 0x557E7E06
# (site VA, original bytes, hook kind, cave)
HOOKS = [(0x557BCCC9, bytes.fromhex("e86a35f9ff"), "call", "reg"),            # call RegisterAbility after the vanilla TWaterWalkingEnchantment
         (0x557E7D90, bytes.fromhex("558bec515356"), "jmp", "ex"),           # TWaterWalking.ExecuteSpell entry
         (0x557E7E00, bytes.fromhex("53568bf18bce"), "jmp", "vt"),           # TWaterWalking.ValidTarget entry
         (0x5574FD98, bytes.fromhex("33c05e5bc3"), "jmp", "t1"),             # TAbilityOwner.GetAbilityEnabled: return-false tail
         (0x5577F612, bytes.fromhex("33c05e5bc3"), "jmp", "t2")]             # TAbstractUnit.GetAbilityEnabled: return-false tail
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, va):
    return bytes(ks.asm(src, va)[0])


def build():
    out = bytearray(); where = {}
    lit = b"Swampwalk"
    out += struct.pack("<ii", -1, len(lit)); where["name"] = ZONE + len(out); out += lit + b"\0"

    def place(name, src):
        while len(out) % 16: out.append(0)
        va = ZONE + len(out); where[name] = va
        out.extend(asm(src, va))

    # ex: TWaterWalking.ExecuteSpell - Swampwalk re-implemented (ability 0xBA), everything else continues in vanilla.
    place("ex", """
        cmp dword ptr [eax+0x10], %(sp)d
        je mine
        push ebp
        mov ebp, esp
        push ecx
        push ebx
        push esi
        jmp %(resume)#x
    mine:
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
        mov edx, %(ab)d
        mov eax, esi
        mov ecx, [eax]
        call dword ptr [ecx+0x94]
        test al, al
        je ok
        mov edx, %(ab)d
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
    """ % {"sp": SPELL, "resume": EX_RESUME, "ab": ABIL_SW, "gad": GETABILITYDATA})

    # vt: TWaterWalking.ValidTarget (eax spell, edx caster, ecx unit -> al) - Swampwalk: base check AND not already
    # Swampwalk (any unit, flyers and swimmers included); everything else continues in vanilla.
    place("vt", """
        cmp dword ptr [eax+0x10], %(sp)d
        je mine
        push ebx
        push esi
        mov esi, ecx
        mov ecx, esi
        jmp %(resume)#x
    mine:
        push ebx
        push esi
        mov esi, ecx
        mov ecx, esi
        call %(base)#x
        test al, al
        je no
        mov edx, %(ab)d
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
        pop esi
        pop ebx
        ret
    """ % {"sp": SPELL, "resume": VT_RESUME, "base": BASECHECK, "ab": ABIL_SW})

    # t1 / t2: the "not present" tails (ebx = owner, esi = id; esi/ebx pushed by the body) - Swampwalk implies 2/3/0xA.
    for name, has in (("t1", 0x4C), ("t2", 0x14C)):
        place(name, """
            cmp esi, %(i0)d
            je chk
            cmp esi, %(i1)d
            je chk
            cmp esi, %(i2)d
            jne no
        chk:
            mov eax, ebx
            mov edx, %(ab)d
            mov ecx, [eax]
            call dword ptr [ecx+%(has)#x]
            test al, al
            je no
            mov al, 1
            pop esi
            pop ebx
            ret
        no:
            xor eax, eax
            pop esi
            pop ebx
            ret
        """ % {"i0": IMPLIED[0], "i1": IMPLIED[1], "i2": IMPLIED[2], "ab": ABIL_SW, "has": has})

    # reg: after the vanilla RegisterAbility(TWaterWalkingEnchantment): a second instance, id 0xBA, name "Swampwalk".
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
        mov dword ptr [eax + 0xc], %(ab)d
        push eax
        lea edx, [esi + %(name)#x]
        add eax, 8
        call %(lstrasg)#x
        pop edx
        mov eax, ebx
        call %(reg)#x
        pop esi
        ret
    """ % {"reg": REGABIL, "cell": WWE_CELL, "create": WWE_CREATE, "ab": ABIL_SW, "name": where["name"], "lstrasg": LSTRASG})
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


def interior_branches(d):
    """Direct rel8/rel32 branches anywhere in CODE that land INSIDE a hook site (not on its first byte)."""
    inner = set()
    for va, orig, _k, _c in HOOKS: inner.update(range(va + 1, va + len(orig)))
    lo, hi = 0x55701000, 0x55860000
    hits = []
    for f in range(lo - CODE_V2F, hi - CODE_V2F - 6):
        b = d[f]
        if b in (0xE8, 0xE9):
            t = lo + (f - (lo - CODE_V2F)) + 5 + struct.unpack_from("<i", d, f + 1)[0]
        elif b == 0x0F and 0x80 <= d[f + 1] <= 0x8F:
            t = lo + (f - (lo - CODE_V2F)) + 6 + struct.unpack_from("<i", d, f + 2)[0]
        elif 0x70 <= b <= 0x7F or b == 0xEB:
            t = lo + (f - (lo - CODE_V2F)) + 2 + struct.unpack_from("<b", d, f + 1)[0]
        else:
            continue
        if t in inner: hits.append((hex(lo + (f - (lo - CODE_V2F))), hex(t)))
    return hits


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
    states = []
    for va, orig, kind, cave in HOOKS:
        live = d[va - CODE_V2F:va - CODE_V2F + len(orig)]
        states.append("vanilla" if live == orig else "ours" if live == hook(va, orig, kind, where[cave]) else "OTHER")
    zl = d[ZONE - CODE_V2F:ZONE_END - CODE_V2F]
    zstate = "zero" if not any(zl) else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else "DIFFERS"
    ib = interior_branches(d) if "vanilla" in states else []
    print("sites %s | zone %s (%d B) | relocs %s | branches into sites %s | caves %s"
          % (states, zstate, len(zone), bad or "none", ib or "none", {k: hex(v) for k, v in where.items()}))
    if bad or ib or "OTHER" in states: print("ABORT"); return 1
    if zstate == "DIFFERS" and "ours" not in states: print("ABORT: zone not free"); return 1
    if a.dis:
        import capstone
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(zone[where["ex"] - ZONE:], where["ex"]):
            print("   %08X  %-16s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    out = bytearray(d)
    if a.revert:
        for va, orig, kind, cave in HOOKS: out[va - CODE_V2F:va - CODE_V2F + len(orig)] = orig
        out[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
        write_inplace(a.dll, bytes(out)); print("reverted"); return 0
    if all(s == "ours" for s in states) and zstate == "ours": print("already applied"); return 0
    out[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE); out[ZONE - CODE_V2F:ZONE - CODE_V2F + len(zone)] = zone
    for va, orig, kind, cave in HOOKS: out[va - CODE_V2F:va - CODE_V2F + len(orig)] = hook(va, orig, kind, where[cave])
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(a.dll, BAK_SUFFIX)
    if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    write_inplace(a.dll, bytes(out)); assert open(a.dll, "rb").read() == bytes(out); print("Written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
