#!/usr/bin/env python3
r"""
Angel Wings (311): the Life/Air tier-4 UNIT ENCHANTMENT - grants FLYING (1), HOLY PROTECTION (0x48), LIGHTNING WEAKNESS
(0x53), DEATH WEAKNESS (0x85) and PHYSICAL WEAKNESS (0x87) while enchanted (2026-10-16).  AoWEPACK.dll only.

Registered by patch_dual_sphere_spells_v1.py as a TWaterWalking clone (like Swampwalk 382: Water Walking = id 0x2A,
pfs key 52, a strategic unit enchantment with upkeep; tc_type 7 so it is castable on a unit in combat too).  Exactly
Swampwalk's mechanism (patch_swampwalk_v1.py, see its RE notes), with a second marker ability:

  reg   splice of the vanilla `call RegisterAbility` @0x557BCE9A (ebx = TAbilityControl there; the 0x8D site, never hooked
        before): replay, then a THIRD TWaterWalkingEnchantment instance (cell 0x557B8CB0, ctor 0x557BB9B0, ecx = 0 - the
        216 lesson), [+0xC] = 0xBD, LStrAsg name "Angel Wings", RegisterAbility.  Description = Ability.pfs record 199
        (patch_angelwings_ability_pfs_v1.py).
  ex    TWaterWalking.ExecuteSpell site 0x557E7D90 (Swampwalk's 6-B jmp; chained IN FRONT of its cave):  spell 311 ->
        ValidTarget (VMT+0x9C), unit ExpandAbility(0xBD) (VMT+0x94), then the TUnitEnchantment of GetAbilityData(unit,
        0xBD) [data+0x10]: VMT+0x54 upkeep [spell+0x1C], VMT+0x58 caster player [caster+0x24], [ench+0x14] = duration
        mode [spell+0x3C] - exactly vanilla Water Walking, so dispel / unpaid upkeep / expiry remove 0xBD through the
        generic TUnitEnchantment path (no orphans).  Other spells -> Swampwalk's cave (-> vanilla).
  vt    TWaterWalking.ValidTarget site 0x557E7E00 (chained in front of Swampwalk's):  311 -> the TUnitSpell base check
        0x5577ACAC AND NOT already Angel Wings (unit VMT+0x148) - flyers and swimmers allowed.
  t1/t2 the two "not present" tails (TAbilityOwner.GetAbilityEnabled 0x5574FD98 = VMT+0x88 bodies used by the movement-
        type builder 0x5574F764 and the protection / immunity mask builders 0x5574F97C / 0x5574FAD0; TAbstractUnit.
        GetAbilityEnabled 0x5577F612 = VMT+0x148 used by TCombatUnit.HasAbility VMT+0xA8 = every tactical check, incl.
        the mod's damage-roll weakness lookup 0x5580FC00 via TCombatUnit.GetAbilityEnabled 0x55725004).  Swampwalk's
        tail caves sit there; ours go IN FRONT: ebx = owner, esi = id; asked for 1/0x48/0x53/0x85/0x87 and the owner HAS
        0xBD (own-bitset test: VMT+0x4C on the owner path, VMT+0x14C on the unit path - no recursion) -> return 1, else
        -> Swampwalk's tail cave (which ends in the vanilla `xor eax,eax / pop esi / pop ebx / ret`).
        Live, derived from the enchantment: save/load-safe, MP-deterministic.  The tactical move-type cache [cu+0x55]
        is built at combat start (Swampwalk note) -> Flying applies from the next battle when cast on the map, and an
        in-combat cast gives the protections/weaknesses at once but flight only from the next battle (as Swampwalk).
Chain layouts (so the next script in front can decode us): ex/vt caves start `cmp dword [eax+0x10], imm32 / je rel8 /
jmp rel32` (prev = cave+14+rel32); t1/t2 caves start `jmp short +5 / jmp rel32 prev` (prev = cave+7+rel32).
Caves AoWEPACK 0x55839400..0x55839800 (zero, no relocs).  PIC: rel32 + call/pop delta (class cell, name literal).
⚠ With this applied, patch_swampwalk_v1.py's ex/vt/t1/t2 sites point here -> its dry run reports OTHER/ABORT (expected
chain state): revert Angel Wings before touching Swampwalk.  --revert restores the previous targets / the vanilla
reg call and refuses if another hook was put in front of ours.  Backup <game>\backup\AoWEPACK.dll.bak_angelwings.
After applying: patch_angelwings_ability_pfs_v1.py (record 199) and LADDER += 0xBD in patch_tcablist_ceiling_v1.py and
patch_aowx_banner_ceilings_v1.py, re-run both (bound 0xBE).  Dry-run default.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DEFAULT_DLL = game_file("AoWEPACK.dll")
BAK_SUFFIX = ".bak_angelwings"
BASE, CODE_V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x55839400, 0x55839800
SPELL, ABIL = 311, 0xBD
IMPLIED = (1, 0x51, 0x53, 0x85, 0x87)                    # v2 2026-10-16 (user): Flying, FIRE Weakness (was Holy Protection 0x48), Lightning / Death / Physical Weakness
WWE_CELL, WWE_CREATE = 0x557B8CB0, 0x557BB9B0            # TWaterWalkingEnchantment class cell / ctor
LSTRASG, REGABIL = 0x55701150, 0x55750238
BASECHECK, GETABILITYDATA = 0x5577ACAC, 0x5574F1C4
REG_SITE, REG_ORIG = 0x557BCECF, bytes.fromhex("e86433f9ff")   # 2026-10-16: moved from 0x557BCE9A (taken by patch_lifeair_v1.py's 0xBC) to the next site (0x8E, same body, ebx = control)
CHAINED = [("ex", 0x557E7D90, 6, "cmp"), ("vt", 0x557E7E00, 6, "cmp"),          # TWaterWalking ExecuteSpell / ValidTarget (Swampwalk's jmps)
           ("t1", 0x5574FD98, 5, "hdr"), ("t2", 0x5577F612, 5, "hdr")]          # GetAbilityEnabled 'not present' tails (Swampwalk's jmps)
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, va):
    return bytes(ks.asm(src, va)[0])


def jmp_target(d, va):
    b = d[va - CODE_V2F:va - CODE_V2F + 5]
    return va + 5 + struct.unpack_from("<i", b, 1)[0] if b[0] == 0xE9 else None


def build(prev):
    out = bytearray(); where = {}
    lit = b"Angel Wings"
    out += struct.pack("<ii", -1, len(lit)); where["name"] = ZONE + len(out); out += lit + b"\0"

    def place(name, src, layout=None):
        while len(out) % 16: out.append(0)
        va = ZONE + len(out); where[name] = va
        b = asm(src, va)
        if layout == "cmp": assert b[0:3] == b"\x81\x78\x10" and b[7] == 0x74 and b[9] == 0xE9, name
        if layout == "hdr": assert b[0:2] == b"\xeb\x05" and b[2] == 0xE9, name
        out.extend(b)

    place("ex", """
        cmp dword ptr [eax+0x10], %(sp)d
        je mine
        jmp %(prev)#x
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
        test eax, eax
        je ok
        mov esi, [eax+0x10]
        test esi, esi
        je ok
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
    """ % {"sp": SPELL, "prev": prev["ex"], "ab": ABIL, "gad": GETABILITYDATA}, "cmp")

    place("vt", """
        cmp dword ptr [eax+0x10], %(sp)d
        je mine
        jmp %(prev)#x
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
    """ % {"sp": SPELL, "prev": prev["vt"], "base": BASECHECK, "ab": ABIL}, "cmp")

    for name, has in (("t1", 0x4C), ("t2", 0x14C)):
        tests = "\n".join("cmp esi, %#x\n je chk" % i for i in IMPLIED)
        place(name, """
            jmp body
            jmp %(prev)#x
        body:
            %(tests)s
            jmp nxt
        chk:
            mov eax, ebx
            mov edx, %(ab)d
            mov ecx, [eax]
            call dword ptr [ecx+%(has)#x]
            test al, al
            je nxt
            mov al, 1
            pop esi
            pop ebx
            ret
        nxt:
            jmp %(prev)#x
        """ % {"prev": prev[name], "tests": tests, "ab": ABIL, "has": has}, "hdr")

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
    """ % {"reg": REGABIL, "cell": WWE_CELL, "create": WWE_CREATE, "ab": ABIL, "name": where["name"], "lstrasg": LSTRASG})
    assert ZONE + len(out) <= ZONE_END, hex(ZONE + len(out))
    return bytes(out), where


def rel(op, va, target, size):
    return bytes([op]) + struct.pack("<i", target - (va + 5)) + b"\x90" * (size - 5)


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
    g = lambda va, n: bytes(d[va - CODE_V2F:va - CODE_V2F + n])
    zl = d[ZONE - CODE_V2F:ZONE_END - CODE_V2F]
    inzone = lambda va: va is not None and ZONE <= va < ZONE_END

    def cave_prev(cave, layout):
        o = cave - CODE_V2F
        if layout == "cmp":
            assert d[o + 7] == 0x74 and d[o + 9] == 0xE9, "cave layout unexpected @%#x" % cave
            return cave + 14 + struct.unpack_from("<i", d, o + 10)[0]
        assert d[o] == 0xEB and d[o + 2] == 0xE9, "cave layout unexpected @%#x" % cave
        return cave + 7 + struct.unpack_from("<i", d, o + 3)[0]

    cur = {k: jmp_target(d, va) for k, va, _n, _l in CHAINED}
    for k, va, n, _l in CHAINED:
        assert cur[k], "%s site %#x is not jmp-hooked (patch_swampwalk_v1.py must be applied first): %s" % (k, va, g(va, n).hex())
    prev = {k: (cave_prev(cur[k], l) if inzone(cur[k]) else cur[k]) for k, _va, _n, l in CHAINED}
    zone, where = build(prev)
    st = {k: ("ours" if cur[k] == where[k] else "prev" if not inzone(cur[k]) else "OTHER") for k, _va, _n, _l in CHAINED}
    rb = g(REG_SITE, 5)
    st["reg"] = "ours" if rb == rel(0xE8, REG_SITE, where["reg"], 5) else "vanilla" if rb == REG_ORIG else "OTHER"
    zstate = "zero" if not any(zl) else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else "DIFFERS"
    rl = reloc_set(d)
    spans = [(va, va + n) for _k, va, n, _l in CHAINED] + [(REG_SITE, REG_SITE + 5)]
    bad = [hex(r) for r in rl if ZONE - 3 <= r < ZONE_END or any(lo - 3 <= r < hi for lo, hi in spans)]
    print("sites %s | prev %s | zone %s (%d B) | relocs %s | caves %s"
          % (st, {k: hex(v) for k, v in prev.items()}, zstate, len(zone), bad or "none",
             ", ".join("%s=%#x" % kv for kv in where.items() if kv[0] != "name")))
    if bad or "OTHER" in st.values() or zstate == "DIFFERS": print("ABORT"); return 1
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        start = where["ex"] - ZONE
        for i in md.disasm(zone[start:], where["ex"]): print("   %08X  %-16s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if a.revert:
        if not any(v == "ours" for v in st.values()): print("nothing to revert"); return 0
        out = bytearray(d)
        for k, va, n, _l in CHAINED:
            if st[k] == "ours": out[va - CODE_V2F:va - CODE_V2F + n] = rel(0xE9, va, prev[k], n)
        if st["reg"] == "ours": out[REG_SITE - CODE_V2F:REG_SITE - CODE_V2F + 5] = REG_ORIG
        out[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
        write_inplace(a.dll, bytes(out)); print("reverted (sites -> %s)" % {k: hex(v) for k, v in prev.items()}); return 0
    if all(v == "ours" for v in st.values()) and zstate == "ours": print("already applied"); return 0
    if zstate == "ours": print("ABORT: zone holds our code but the sites do not point at it"); return 1
    out = bytearray(d)
    out[ZONE - CODE_V2F:ZONE - CODE_V2F + len(zone)] = zone
    for k, va, n, _l in CHAINED: out[va - CODE_V2F:va - CODE_V2F + n] = rel(0xE9, va, where[k], n)
    out[REG_SITE - CODE_V2F:REG_SITE - CODE_V2F + 5] = rel(0xE8, REG_SITE, where["reg"], 5)
    print("%d bytes change" % sum(1 for x, y in zip(d, out) if x != y))
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(a.dll, BAK_SUFFIX)
    if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    write_inplace(a.dll, bytes(out)); assert open(a.dll, "rb").read() == bytes(out); print("Written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
