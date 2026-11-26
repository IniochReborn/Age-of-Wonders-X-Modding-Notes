#!/usr/bin/env python3
r"""
Undying (210): the Death tier-2 UNIT ENCHANTMENT - grants DEATH IMMUNITY (0x0B) and REGENERATION (0x31) while
enchanted (2026-10-16).  AoWEPACK.dll only.  A copy of patch_angelwings_v1.py's mechanism (see its notes), with a
fourth TWaterWalkingEnchantment marker ability:

  reg   splice of the vanilla `call RegisterAbility` @0x557BCDFB (the 0x8A site, same body as 0x557BCECF: ebx =
        TAbilityControl; never hooked before): replay, then a TWaterWalkingEnchantment instance (cell 0x557B8CB0, ctor
        0x557BB9B0, ecx = 0), [+0xC] = 0xC1, name "Undying", RegisterAbility.  Description = Ability.pfs record 203
        (patch_undying_ability_pfs_v1.py).
  ex/vt TWaterWalking.ExecuteSpell / ValidTarget sites 0x557E7D90 / 0x557E7E00, chained IN FRONT of Angel Wings' caves:
        spell 210 -> vanilla Water Walking cast (ValidTarget, ExpandAbility 0xC1, TUnitEnchantment upkeep / caster /
        duration mode) / base check AND not already Undying.  Other spells -> Angel Wings' cave (-> Swampwalk -> vanilla).
  t1/t2 the GetAbilityEnabled "not present" tails 0x5574FD98 (VMT+0x88 owner path: movement / protection / IMMUNITY mask
        builders) and 0x5577F612 (TAbstractUnit VMT+0x148: every unit check, incl. the strategic new-turn heal
        0x55780D4C, whose `GetAbilityEnabled(0x31)` @0x55780D9D picks Regeneration's FULL heal over the normal partial
        one): asked for 0x0B / 0x31 and the owner holds 0xC1 (own bitset VMT+0x4C / VMT+0x14C) -> 1, else -> Angel
        Wings' tail cave.
  RE: Regeneration in this build is ONLY that strategic heal (no tactical per-round regeneration exists: no other code
  asks for 0x31 - the TCPCK 0x415AEE `cmp eax,0x31` is the AI's spell-id switch), and it already goes through
  VMT+0x148, so an implied Regeneration really heals.  Death Immunity reaches the immunity mask through the t1 path.
Chain layouts as Angel Wings (ex/vt: `cmp [eax+0x10],imm32 / je / jmp prev`; t1/t2: `jmp +5 / jmp prev`).
Caves AoWEPACK 0x55869000..0x55869800 (zero, no relocs).  ⚠ With this applied, patch_angelwings_v1.py's sites point
here -> its dry run reports OTHER/ABORT (expected): revert Undying before touching Angel Wings (or Swampwalk).
Backup <game>\backup\AoWEPACK.dll.bak_undying.  After applying: patch_undying_ability_pfs_v1.py (record 203) and
LADDER += 0xC1 in patch_tcablist_ceiling_v1.py and patch_aowx_banner_ceilings_v1.py, re-run both (bound 0xC2).
Dry-run default; --dll <copy> for scratch runs.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DEFAULT_DLL = game_file("AoWEPACK.dll")
BAK_SUFFIX = ".bak_undying"
BASE, CODE_V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x55869000, 0x55869800
SPELL, ABIL = 210, 0xC1
IMPLIED = (0x0B, 0x31)                                   # Death Immunity, Regeneration
WWE_CELL, WWE_CREATE = 0x557B8CB0, 0x557BB9B0            # TWaterWalkingEnchantment class cell / ctor
LSTRASG, REGABIL = 0x55701150, 0x55750238
BASECHECK, GETABILITYDATA = 0x5577ACAC, 0x5574F1C4
REG_SITE, REG_ORIG = 0x557BCDFB, bytes.fromhex("e83834f9ff")   # the 0x8A site (same body as 0x557BCECF, ebx = control); free 2026-10-16
CHAINED = [("ex", 0x557E7D90, 6, "cmp"), ("vt", 0x557E7E00, 6, "cmp"),          # TWaterWalking ExecuteSpell / ValidTarget (Angel Wings' jmps)
           ("t1", 0x5574FD98, 5, "hdr"), ("t2", 0x5577F612, 5, "hdr")]          # GetAbilityEnabled 'not present' tails (Angel Wings' jmps)
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, va):
    return bytes(ks.asm(src, va)[0])


def jmp_target(d, va):
    b = d[va - CODE_V2F:va - CODE_V2F + 5]
    return va + 5 + struct.unpack_from("<i", b, 1)[0] if b[0] == 0xE9 else None


def build(prev):
    out = bytearray(); where = {}
    lit = b"Undying"
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
        assert cur[k], "%s site %#x is not jmp-hooked (patch_angelwings_v1.py must be applied first): %s" % (k, va, g(va, n).hex())
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
