#!/usr/bin/env python3
r"""
Static Shield (215): the Air tier-4 combat spell - "grants the target unit Lightning Immunity and Lightning Strike
until the end of combat" (2026-10-16).  AoWEPACK.dll only (the tactical cursor/click half = patch_tc_staticshield_target_v1.py).

Registered by patch_dual_sphere_spells_v1.py as a TRemedy instance (donor TRemedy, pfs 45 - like Second Wind 310 /
Borrow Time 346 / Martyr 360: friendly single target, combat-only pokes; range poke [+0x38] = -1 = unlimited).

  reg  call-hook on `call RegisterAbility` 0x557BCF6E - CHAINED: the site's current call target (Sanctify's / Suspend's
       reg cave, decoded AT APPLY TIME and kept in the zone header for --revert) is called first, then a plain
       TDurationAbility, combat-only mode 3 (the Second Wind / Inspired / Heavenly Chorus recipe: VMT 0x5571DD68,
       Create 0x55764CD4, [+0x24]=4, [+0x28]=3, [+0x20]=the HighPrayerBlessing word) is created as 0xC4
       'Static Shield' and registered -> GetName "Static Shield (combat only)", TDurationAbility.CombatDone removes it
       when the battle ends.  Description = Ability.pfs record 206 (patch_staticshield_ability_pfs_v1.py).
  ex   TRemedy.ExecuteSpell site 0x557E736C, chained IN FRONT of the current chain (Second Wind's cave): spell 215 ->
       ValidTarget (VMT+0x9C); the target TUnit gains 0xC4 (ExpandAbility VMT+0x94 = Expand + Changed) unless it
       already holds it.  Other spells -> previous target.
  vt   TRemedy.ValidTarget site 0x557E7434: 215 -> the TUnitSpell base check AND the target must NOT hold 0xC4
       (VMT+0x148) -> no re-cast on a shielded unit.  Other spells -> previous target.
  t1/t2 the GetAbilityEnabled 'not present' tails 0x5574FD98 (owner VMT+0x88 path: the IMMUNITY mask builder
       0x5574FAxx asks 0x06..0x0D there) and 0x5577F612 (TAbstractUnit VMT+0x148: the melee damage-type builder
       0x55766DFE asks the strikes 0x0E..0x14 there; TCombatUnit.GetAbilityEnabled 0x55725004 forwards to it), chained
       in front of Undying's tails: asked for 0x09 Lightning Immunity / 0x10 Lightning Strike and the owner holds 0xC4
       (own bitset, VMT+0x4C / VMT+0x14C) -> 1.  Both builders query live, so the implied pair really works: the unit's
       melee gains the lightning damage type and lightning damage cannot hurt it.
  AI: TRemedy inherits the EMPTY TCombatSpell AI valuers -> the AI never casts it (like Second Wind / Martyr).

Chain layouts: ex/vt `cmp dword [eax+0x10],imm32 / je rel8 / jmp prev` (cave_prev contract), t1/t2 `jmp +5 / jmp prev`.
Zone AoWEPACK 0x5586C800..0x5586D000 (verified zero, no relocs).  --revert restores every previous target and refuses
when something was chained in front of one of our sites.  ⚠ With this applied the dry runs of patch_secondwind_v1.py
(ex/vt), patch_undying_v1.py (t1/t2) and the reg-site owner (Suspend / Sanctify) report OTHER / ABORT - expected chain
state: revert Static Shield first.  Backup <game>\backup\AoWEPACK.dll.bak_staticshield.  Dry-run default; --dll <copy>.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DEFAULT_DLL = game_file("AoWEPACK.dll")
BAK_SUFFIX = ".bak_staticshield"
BASE, CODE_V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x5586C800, 0x5586D000
SPELL, ABIL = 215, 0xC4
IMPLIED = (0x09, 0x10)                                   # Lightning Immunity, Lightning Strike
BASECHECK = 0x5577ACAC                                   # TUnitSpell base ValidTarget
VT_EPI = 0x557E74DB                                      # TRemedy.ValidTarget epilogue (pop esi / pop ebx / ret)
REG_SITE = 0x557BCF6E                                    # `call RegisterAbility` (vanilla e8c532f9ff), chained call-hook
REGABIL, LSTRASG = 0x55750238, 0x55701150
DUR_VMT, DUR_CREATE = 0x5571DD68, 0x55764CD4
HPB_WORD20 = 0x557BB808
CHAINED = [("ex", 0x557E736C, 6, "cmp"), ("vt", 0x557E7434, 6, "cmp"),          # TRemedy ExecuteSpell / ValidTarget
           ("t1", 0x5574FD98, 5, "hdr"), ("t2", 0x5577F612, 5, "hdr")]          # GetAbilityEnabled 'not present' tails
HDR = 8                                                  # zone header: dword prev reg-call target, dword 0
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, va):
    return bytes(ks.asm(src, va)[0])


def build(prev, prev_reg, w20):
    out = bytearray(struct.pack("<II", prev_reg, 0)); where = {}
    lit = b"Static Shield"
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
        call dword ptr [ecx+0x148]
        test al, al
        jne ok
        mov edx, %(ab)d
        mov eax, esi
        mov ecx, [eax]
        call dword ptr [ecx+0x94]
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
    """ % {"sp": SPELL, "prev": prev["ex"], "ab": ABIL}, "cmp")

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
        jz vt_out
        mov edx, %(ab)d
        mov eax, esi
        mov ecx, [eax]
        call dword ptr [ecx+0x148]
        test al, al
        sete al
    vt_out:
        jmp %(epi)#x
    """ % {"sp": SPELL, "prev": prev["vt"], "base": BASECHECK, "ab": ABIL, "epi": VT_EPI}, "cmp")

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
        call %(prevreg)#x
        push esi
        call rd
    rd:
        pop esi
        sub esi, rd
        lea eax, [esi + %(vmt)#x]
        xor ecx, ecx
        mov dl, 1
        call %(create)#x
        mov dword ptr [eax + 0xc], %(ab)d
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
    """ % {"prevreg": prev_reg, "vmt": DUR_VMT, "create": DUR_CREATE, "ab": ABIL, "w20": w20, "name": where["name"],
           "lstrasg": LSTRASG, "reg": REGABIL})
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

    def target(va, op):
        b = g(va, 5)
        return va + 5 + struct.unpack_from("<i", b, 1)[0] if b[0] == op else None

    def cave_prev(cave, layout):
        o = cave - CODE_V2F
        if layout == "cmp":
            assert d[o + 7] == 0x74 and d[o + 9] == 0xE9, "cave layout unexpected @%#x" % cave
            return cave + 14 + struct.unpack_from("<i", d, o + 10)[0]
        assert d[o] == 0xEB and d[o + 2] == 0xE9, "cave layout unexpected @%#x" % cave
        return cave + 7 + struct.unpack_from("<i", d, o + 3)[0]

    cur = {k: target(va, 0xE9) for k, va, _n, _l in CHAINED}
    for k, va, n, _l in CHAINED:
        assert cur[k], "%s site %#x is not jmp-hooked (Second Wind / Undying must be applied first): %s" % (k, va, g(va, n).hex())
    prev = {k: (cave_prev(cur[k], l) if inzone(cur[k]) else cur[k]) for k, _va, _n, l in CHAINED}
    creg = target(REG_SITE, 0xE8)
    assert creg, "reg site %#x is not a call: %s" % (REG_SITE, g(REG_SITE, 5).hex())
    prev_reg = struct.unpack_from("<I", zl, 0)[0] if inzone(creg) else creg
    w20 = struct.unpack_from("<H", d, HPB_WORD20 - CODE_V2F)[0]
    zone, where = build(prev, prev_reg, w20)
    st = {k: ("ours" if cur[k] == where[k] else "chain-ready" if not inzone(cur[k]) else "OTHER") for k, _va, _n, _l in CHAINED}
    st["reg"] = "ours" if creg == where["reg"] else "chain-ready" if not inzone(creg) else "OTHER"
    zstate = "zero" if not any(zl) else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else "DIFFERS"
    rl = reloc_set(d)
    spans = [(va, va + n) for _k, va, n, _l in CHAINED] + [(REG_SITE, REG_SITE + 5)]
    bad = [hex(r) for r in rl if ZONE - 3 <= r < ZONE_END or any(lo - 3 <= r < hi for lo, hi in spans)]
    print("sites %s | prev %s, reg %#x | zone %s (%d B) | relocs %s | caves %s"
          % (st, {k: hex(v) for k, v in prev.items()}, prev_reg, zstate, len(zone), bad or "none",
             ", ".join("%s=%#x" % kv for kv in where.items() if kv[0] != "name")))
    ours = [k for k, v in st.items() if v == "ours"]
    if bad or "OTHER" in st.values() or zstate == "DIFFERS" or (ours and len(ours) != len(st)):
        print("ABORT (relocs / something chained in front of one of our sites / mixed state / zone not free)"); return 1
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        start = where["ex"] - ZONE
        for i in md.disasm(zone[start:], where["ex"]): print("   %08X  %-16s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    out = bytearray(d)
    if a.revert:
        if not ours: print("already reverted"); return 0
        for k, va, n, _l in CHAINED: out[va - CODE_V2F:va - CODE_V2F + n] = rel(0xE9, va, prev[k], n)
        out[REG_SITE - CODE_V2F:REG_SITE - CODE_V2F + 5] = rel(0xE8, REG_SITE, prev_reg, 5)
        out[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
        write_inplace(a.dll, bytes(out)); print("reverted (sites -> %s, reg -> %#x)" % ({k: hex(v) for k, v in prev.items()}, prev_reg)); return 0
    if ours and zstate == "ours": print("already applied"); return 0
    out[ZONE - CODE_V2F:ZONE - CODE_V2F + len(zone)] = zone
    for k, va, n, _l in CHAINED: out[va - CODE_V2F:va - CODE_V2F + n] = rel(0xE9, va, where[k], n)
    out[REG_SITE - CODE_V2F:REG_SITE - CODE_V2F + 5] = rel(0xE8, REG_SITE, where["reg"], 5)
    print("%d bytes change" % sum(1 for x, y in zip(d, out) if x != y))
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if os.path.abspath(a.dll) == os.path.abspath(DEFAULT_DLL):
        bak = bak_path(a.dll, BAK_SUFFIX)
        if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    write_inplace(a.dll, bytes(out)); assert open(a.dll, "rb").read() == bytes(out); print("Written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
