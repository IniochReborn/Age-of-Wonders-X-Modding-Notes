#!/usr/bin/env python3
r"""
Tame Animal (ability 0xC9, 2026-10-18): a Dominate-style combat touch ability that only works on CREATURES.

User spec: "similar to Dominate/Charm/etc, except it should only target creatures.  6 ATK against level 1
creatures, 5 ATK level 2, 4 ATK level 3, 3 ATK level 4.  Does not target: Greater Spirit Puppet, Spirit Puppet,
Djinn, Beholder, Yeti, Fairy, Satyr, Centaur, Lady of Pain, Nymph, Spider Queen, Shadow, any creature with
Fearless."

RE (AoWEPACK.dll):
  * TDominateAbility (VMT 0x55720878, class cell 0x55720838, Create 0x557705BC, instance 0x2C, parent
    TCommandAbility) / TCharmAbility (VMT 0x55720BAC) / TSeduceAbility (VMT 0x55720ED8) share every slot except
      +0x20  Create         (Dominate sets id 0x1C, name, [+0x28] = 0x96 Dominated = the status it grants)
      +0x10C GetAttack      (eax = ability, edx = ability level -> al = the touch ATK: Dominate 5, Charm 6,
                             Seduce 4; called with NO target)
      +0x11C CanTouch (combat)     eax = ability, edx = attacker TCombatUnit, ecx = target TCombatUnit
      +0x120 CanTouch (unit)       eax = ability, ecx = target TUnit (autocombat / valuation path)
  * The ATK is consumed by the shared TTouchAbility methods, which all know the target:
      +0x110 0x557681B0  the success roll   (ecx = target TCombatUnit)
      +0x114 0x55768234  success chance      (ecx = target TCombatUnit)
      +0x118 0x55768130  value estimate      (ecx = target TUnit)
    plus two target-less callers (+0x104 info line, +0xE0 attacker valuation).
  * Unit type: TUnit VMT+0x114 GetUnitType = [res+0x30] = TUnitType {utHumanoid, utCreature, utMachined}
    -> creature = 1 (heroes/leaders return 0).  Level = [res+0x2F] (Unitres tag 0x14).  Unit id =
    TUnitResource.UnitResourceIndex 0x5574D3C8 (eax = res -> the Unitres child id).  Fearless = 0x43 via
    TUnit VMT+0x148 (item/enchantment aware; TCombatUnit VMT+0xA8 forwards there).

Design (no VMT clone): a SECOND TDominateAbility instance is registered with id 0xC9 and name "Tame Animal"
(Dominate's Create, then id / name overwritten) -> it inherits every Dominate behaviour (Dominated status 0x96,
roll, take-control, combat-end handling, gfx/sfx from its own Ability.pfs record 211).  Six Dominate VMT slots
are pointed at caves that test [ability+0xC] == 0xC9 and otherwise tail-jump to the original method, so
Dominate itself (and Charm/Seduce, whose VMTs are untouched) is unchanged:
  +0x10C w10c  0xC9: ATK = 7 - level of the stashed target (level <= 1 -> 6, >= 4 -> 3; no target -> 6)
  +0x110/+0x114/+0x118  w110/w114/w118  0xC9: stash ecx (the target) in STASH around the original call
  +0x11C w11c  0xC9: original && creature filter on the target combat unit
  +0x120 w120  0xC9: original && creature filter on the target unit
  creature filter: resolve TCombatUnit -> [+0x4C] TUnit; IsClass TUnit; GetUnitType == 1; unit id not in
  EXCLUDE; not HasAbility(0x43 Fearless).
  reg  splice of the RegisterAbility chain call @0x557BCF6E: `call prev`, then create + register 0xC9.
AoWTCPCK.dll: AbilTypes[0xC9] (DATA 0x467248 + 0xC9 = 0x467311, a byte of the dead old SpellTypes table since
patch_spelltypes_relocate_v1) := 4 = touch, so a click with the ability selected runs the touch flow (0x41EC5A).

PIC: the cave reaches STASH, the name literal and the two class cells through a call/pop delta; all calls/jumps
are rel32 to in-image code.  STASH = AoWEPACK .idata page slack 0x5590BF80 (runtime-only zero memory).
MP: deterministic (same stash/ATK on every client; no RNG touched besides the vanilla roll).
AI: the tactical AI's ability scan stops at 0xA9 (vanilla AbilTypes size), so the AI does not use Tame Animal
(same as every other ability minted above 0xA9).

Zone AoWEPACK 0x5588B000..0x5588B400 (verified zero + reloc-free at apply).  Header: +0 'TAM1', +4 reg
original (5 B), +0x0C original AbilTypes byte, +0x10 six original slot pointers, +0x30 name literal.
Dry-run default; --apply / --revert / --dis; --dll / --tcdll <scratch copies>.  Backups (first apply):
<game>\backup\AoWEPACK.dll.bak_tame, AoWTCPCK.dll.bak_tame.
LIFO: the chain head @0x557BCF6E becomes ours -> revert this BEFORE reverting/re-running patch_reversal_v1.py
(or anything else that decodes 0x557BCF6E); re-apply this afterwards.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DEFAULT_DLL = game_file("AoWEPACK.dll")
DEFAULT_TC = game_file("AoWTCPCK.dll")
BAK_SUFFIX = ".bak_tame"
BASE, CODE_V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x5588B000, 0x5588B400
HDR = 0x60
MAGIC = b"TAM1"
AB = 0xC9
NAME = b"Tame Animal"
STASH = 0x5590BF80                                       # runtime-only .idata page slack (zero at load)
DOM_VMT, DOM_CELL, DOM_CREATE = 0x55720878, 0x55720838, 0x557705BC
CU_CELL, UNIT_CELL = 0x55715A54, 0x55710C6C              # TCombatUnit / TUnit class cells
ISCLASS, RESIDX = 0x557010C0, 0x5574D3C8
REGABIL, LSTRASG = 0x55750238, 0x55701150
REG_SITE = 0x557BCF6E
SLOTS = (0x10C, 0x110, 0x114, 0x118, 0x11C, 0x120)
VANILLA_SLOTS = {0x10C: 0x55770664, 0x110: 0x557681B0, 0x114: 0x55768234, 0x118: 0x55768130,
                 0x11C: 0x55770008, 0x120: 0x55770068}
FEARLESS = 0x43
CREATURE = 1
EXCLUDE = {130: "Spirit Puppet", 241: "Greater Spirit Puppet", 25: "Djinn", 24: "Beholder", 41: "Yeti",
           76: "Fairy", 96: "Satyr", 98: "Centaur", 148: "Lady of Pain", 77: "Nymph", 150: "Spider Queen",
           151: "Shadow"}                               # Unitres child ids (= UnitResourceIndex)
TC_ABILTYPES = 0x467248
TC_BYTE_VA = TC_ABILTYPES + AB                           # 0x467311
TOUCH = 4
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, va):
    return bytes(ks.asm(src, va)[0])


def build(prev_reg, orig):
    out = bytearray(HDR); where = {}

    def place(name, src):
        while len(out) % 16: out.append(0)
        va = ZONE + len(out); where[name] = va
        out.extend(asm(src, va))

    def label(name):
        return where[name]

    # name literal (AnsiString constant: refcount -1, length, chars, NUL) at +0x30
    lit = struct.pack("<ii", -1, len(NAME)) + NAME + b"\0"
    assert 0x30 + len(lit) <= HDR
    out[0x30:0x30 + len(lit)] = lit
    where["name"] = ZONE + 0x30 + 8

    excl = "\n".join("        cmp eax, %d\n        je fno" % k for k in sorted(EXCLUDE))
    # getunit: eax = TCombatUnit | TUnit | anything -> eax = TUnit or 0  (ebx/esi/edi preserved)
    place("getunit", """
        push ebx
        push esi
        mov ebx, eax
        test ebx, ebx
        je gzero
        call gd
    gd:
        pop esi
        sub esi, gd
        mov eax, ebx
        mov edx, dword ptr [esi + %(cucell)#x]
        call %(isclass)#x
        test al, al
        je gnotcu
        mov ebx, dword ptr [ebx + 0x4c]
        test ebx, ebx
        je gzero
    gnotcu:
        mov eax, ebx
        mov edx, dword ptr [esi + %(unitcell)#x]
        call %(isclass)#x
        test al, al
        je gzero
        mov eax, ebx
        jmp gout
    gzero:
        xor eax, eax
    gout:
        pop esi
        pop ebx
        ret
    """ % {"cucell": CU_CELL, "unitcell": UNIT_CELL, "isclass": ISCLASS})

    # filt: eax = target object -> al = 1 if a tameable creature
    place("filt", """
        push ebx
        call %(getunit)#x
        test eax, eax
        je fno
        mov ebx, eax
        mov edx, dword ptr [eax]
        call dword ptr [edx + 0x114]
        cmp al, %(creature)d
        jne fno
        mov eax, dword ptr [ebx + 0x40]
        test eax, eax
        je fno
        call %(residx)#x
%(excl)s
        mov eax, ebx
        mov edx, %(fearless)d
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x148]
        test al, al
        jne fno
        mov al, 1
        jmp fout
    fno:
        xor eax, eax
    fout:
        pop ebx
        ret
    """ % {"getunit": label("getunit"), "creature": CREATURE, "residx": RESIDX, "excl": excl, "fearless": FEARLESS})

    place("w10c", """
        cmp dword ptr [eax + 0xc], %(ab)d
        je m
        jmp %(orig)#x
    m:
        push ecx
        push edx
        push esi
        call hd
    hd:
        pop esi
        sub esi, hd
        mov eax, dword ptr [esi + %(stash)#x]
        call %(getunit)#x
        test eax, eax
        je dflt
        mov eax, dword ptr [eax + 0x40]
        test eax, eax
        je dflt
        movzx eax, byte ptr [eax + 0x2f]
        cmp eax, 1
        jbe dflt
        cmp eax, 4
        jb mid
        mov eax, 3
        jmp wout
    mid:
        neg eax
        add eax, 7
        jmp wout
    dflt:
        mov eax, 6
    wout:
        pop esi
        pop edx
        pop ecx
        ret
    """ % {"ab": AB, "orig": orig[0x10C], "stash": STASH, "getunit": label("getunit")})

    for s in (0x110, 0x114, 0x118):
        place("w%x" % s, """
        cmp dword ptr [eax + 0xc], %(ab)d
        je m
        jmp %(orig)#x
    m:
        push ebx
        call hd
    hd:
        pop ebx
        sub ebx, hd
        push dword ptr [ebx + %(stash)#x]
        mov dword ptr [ebx + %(stash)#x], ecx
        call %(orig)#x
        pop dword ptr [ebx + %(stash)#x]
        pop ebx
        ret
        """ % {"ab": AB, "orig": orig[s], "stash": STASH})

    for s in (0x11C, 0x120):
        place("w%x" % s, """
        cmp dword ptr [eax + 0xc], %(ab)d
        je m
        jmp %(orig)#x
    m:
        push ecx
        call %(orig)#x
        pop ecx
        test al, al
        je wout
        mov eax, ecx
        call %(filt)#x
    wout:
        ret
        """ % {"ab": AB, "orig": orig[s], "filt": label("filt")})

    place("reg", """
        call %(prev)#x
        push esi
        call rd
    rd:
        pop esi
        sub esi, rd
        mov eax, dword ptr [esi + %(cell)#x]
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
    """ % {"prev": prev_reg, "cell": DOM_CELL, "create": DOM_CREATE, "ab": AB, "name": where["name"],
           "lstrasg": LSTRASG, "reg": REGABIL})
    assert ZONE + len(out) <= ZONE_END, hex(ZONE + len(out))
    return out, where


def sections(d):
    pe = struct.unpack_from("<I", d, 0x3C)[0]; opt = struct.unpack_from("<H", d, pe + 20)[0]; nsec = struct.unpack_from("<H", d, pe + 6)[0]
    return [struct.unpack_from("<IIII", d, pe + 24 + opt + 40 * k + 8) for k in range(nsec)], pe


def va2off(d, va, base):
    secs, _ = sections(d)
    for vs, sva, rs, ro in secs:
        if sva <= va - base < sva + max(vs, rs): return ro + va - base - sva
    raise ValueError(hex(va))


def reloc_set(d, base):
    secs, pe = sections(d)
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
            if e >> 12 == 3: out.add(base + page + (e & 0xFFF))
        p += size
    return out


def write_inplace(path, data):
    with open(path, "r+b") as f:
        f.seek(0); f.write(data); f.truncate(len(data))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dll", default=DEFAULT_DLL)
    ap.add_argument("--tcdll", default=DEFAULT_TC)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    d = open(a.dll, "rb").read(); t = open(a.tcdll, "rb").read()
    g = lambda va, n: bytes(d[va - CODE_V2F:va - CODE_V2F + n])
    tco = va2off(t, TC_BYTE_VA, 0x400000)
    zl = g(ZONE, ZONE_END - ZONE)
    applied = zl[:4] == MAGIC
    slot_va = {s: DOM_VMT + s for s in SLOTS}
    cur_reg = g(REG_SITE, 5)
    cur_slot = {s: struct.unpack("<I", g(slot_va[s], 4))[0] for s in SLOTS}
    cur_tc = t[tco]
    if applied:
        sav_reg = zl[4:9]; sav_tc = zl[0xC]
        sav_slot = {s: struct.unpack_from("<I", zl, 0x10 + 4 * k)[0] for k, s in enumerate(SLOTS)}
    else:
        sav_reg, sav_tc, sav_slot = cur_reg, cur_tc, dict(cur_slot)
        assert cur_reg[0] == 0xE8, "reg site %#x is not a call (%s)" % (REG_SITE, cur_reg.hex())
        for s in SLOTS:
            assert 0x55701000 <= cur_slot[s] < 0x558E8000 and not (ZONE <= cur_slot[s] < ZONE_END), (hex(s), hex(cur_slot[s]))
        assert cur_tc == 0, "AbilTypes[0xC9] = %d (expected 0) - another patch uses it?" % cur_tc
    prev_reg = REG_SITE + 5 + struct.unpack_from("<i", sav_reg, 1)[0]
    zone, where = build(prev_reg, sav_slot)
    zone[0:4] = MAGIC; zone[4:9] = sav_reg; zone[0xC] = sav_tc
    for k, s in enumerate(SLOTS): struct.pack_into("<I", zone, 0x10 + 4 * k, sav_slot[s])
    zone = bytes(zone)
    hooked_reg = b"\xE8" + struct.pack("<i", where["reg"] - (REG_SITE + 5))
    hooked_slot = {s: where["w%x" % s] for s in SLOTS}
    st = {"reg": "ours" if cur_reg == hooked_reg else ("orig" if cur_reg == sav_reg else "OTHER")}
    for s in SLOTS:
        st["s%x" % s] = "ours" if cur_slot[s] == hooked_slot[s] else ("orig" if cur_slot[s] == sav_slot[s] else "OTHER")
    st["tc"] = "ours" if cur_tc == TOUCH else ("orig" if cur_tc == sav_tc else "OTHER")
    zstate = "zero" if not any(zl) else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else "DIFFERS"
    rl = reloc_set(d, BASE); rlt = reloc_set(t, 0x400000)
    bad = [hex(r) for r in rl if ZONE - 3 <= r < ZONE_END or REG_SITE - 3 <= r < REG_SITE + 5]
    bad += ["tc:" + hex(r) for r in rlt if TC_BYTE_VA - 3 <= r <= TC_BYTE_VA]
    slot_rel = all(slot_va[s] in rl for s in SLOTS)
    nonvan = [hex(s) for s in SLOTS if sav_slot[s] != VANILLA_SLOTS[s]]
    print("states %s | zone %s (%d B) | prev reg %#x | relocs in zone/sites %s | slot relocs %s | non-vanilla slot "
          "originals %s | caves %s" % (st, zstate, len(zone), prev_reg, bad or "none", "ok" if slot_rel else "MISSING",
                                       nonvan or "none", ", ".join("%s=%#x" % kv for kv in where.items())))
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        for i in md.disasm(zone[HDR:], ZONE + HDR): print("   %08X  %-24s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad or not slot_rel or "OTHER" in st.values() or zstate == "DIFFERS": print("ABORT"); return 1
    if a.revert:
        if not applied: print("already reverted"); return 0
        out = bytearray(d)
        out[REG_SITE - CODE_V2F:REG_SITE - CODE_V2F + 5] = sav_reg
        for s in SLOTS: struct.pack_into("<I", out, slot_va[s] - CODE_V2F, sav_slot[s])
        out[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
        tout = bytearray(t); tout[tco] = sav_tc
        write_inplace(a.tcdll, bytes(tout)); write_inplace(a.dll, bytes(out))
        print("reverted (reg site, 6 Dominate VMT slots, AbilTypes[0xC9], zone cleared)"); return 0
    if all(v == "ours" for v in st.values()) and zstate == "ours": print("already applied"); return 0
    if applied: print("ABORT: zone holds our code but the sites do not all point at it"); return 1
    out = bytearray(d)
    out[ZONE - CODE_V2F:ZONE - CODE_V2F + len(zone)] = zone
    out[REG_SITE - CODE_V2F:REG_SITE - CODE_V2F + 5] = hooked_reg
    for s in SLOTS: struct.pack_into("<I", out, slot_va[s] - CODE_V2F, hooked_slot[s])
    tout = bytearray(t); tout[tco] = TOUCH
    print("%d AoWEPACK bytes + 1 AoWTCPCK byte change" % sum(1 for x, y in zip(d, out) if x != y))
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    for path, data in ((a.dll, d), (a.tcdll, t)):
        if os.path.abspath(path) in (os.path.abspath(DEFAULT_DLL), os.path.abspath(DEFAULT_TC)):
            bak = bak_path(path, BAK_SUFFIX)
            if not os.path.exists(bak): shutil.copy2(path, bak); print("backup ->", bak)
    write_inplace(a.tcdll, bytes(tout)); write_inplace(a.dll, bytes(out))
    assert open(a.dll, "rb").read() == bytes(out) and open(a.tcdll, "rb").read() == bytes(tout)
    print("Written and verified.  Next: patch_tame_ability_pfs_v1.py --apply, then the two ceiling scripts.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
