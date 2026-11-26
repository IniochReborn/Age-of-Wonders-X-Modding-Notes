"""
FRENZIED CHARGE (spell 390, Fire/Air tier 3; 2026-10-14) - AoWEPACK.dll only.  v2.

Combat spell, no target: every FRIENDLY unit in the battle gets HASTE and FURY until the end of the combat, shown as
"Haste (combat only)" / "Fury (combat only)" on the unit - the LIONHEART recipe: second instances of the REAL ability
classes registered under new ids, 0xB3 = another THasteAbility (cell 0x557B7C2C, Create 0x557BAD98, the ctor names it
"Haste") and 0xB4 = another TFuryAbility (cell 0x557B82B8, Create 0x557BB2C8, named "Fury"), each with the ctor's
[+0xC] id overwritten.  Both classes descend from TUnitEnchantmentAbility -> TAdjustableAbility (instance size 0x28,
no TDurationAbility +0x24/+0x28 fields: the duration mode is purely the GetDurationMode getter VMT+0x10C, inherited
0x55765A28 = 0 permanent), so each class's VMT+0x10C slot is pointed at a cave that answers 3 (combat only) for the
new id and 0 otherwise - the base CombatDone VMT+0xFC (0x55765B20, reached per unit from TAbilityOwner.TriggerCombatDone
0x5574FEC4, tactical and fast combat alike) then drops the instance through owner.RemoveAbility, which frees the
enchantment data record (TUnitEnchantmentAbility.Remove 0x557659A8).  Fury's +3 attack / -1 defence come with the
shared VMT (+0x5C / +0x60).  Haste's effect is the one by-id check of 0x98 at 0x5577FF43 (TUnit VMT+0x148
GetAbilityEnabled in the movement-cost table build); the two other `mov edx,0x98` sites 0x55769A39 / 0x5578CFE1 are
GetItem([AoWHSSet+0x5C], 152) + SetResource on a scratch unit (unit RESOURCE 152, not the ability) and are left alone.

  reg   call-hook on the vanilla `call RegisterAbility` 0x557BCDC6 (ebx = control): replay, then create + register
        the two instances (vanilla form: xor ecx,ecx / mov dl,1 / mov eax,[cell] / call Create; [+0xC] := new id).
  mdh   THasteAbility VMT+0x10C slot 0x557B7D78 (orig 0x55765A28, carries a reloc by design - kept): cave -> 3 for
        id 0xB3 else 0.      mdf   TFuryAbility VMT+0x10C slot 0x557B8404: 3 for id 0xB4 else 0.
  h1    call-hook on the Haste check 0x5577FF43 (15 B `mov edx,0x98 / mov eax,esi / mov ecx,[eax] / call [ecx+0x148]`,
        resume 0x5577FF52 `test al,al`): GetAbilityEnabled(0x98) OR GetAbilityEnabled(0xB3).
  exe   jmp-hook on TTacticalCombatHighPrayerCA.Execute 0x557F7E98 (6 B prologue): for a 390 CA ([ca+0x18]) call the
        parent like vanilla, resolve the unit (0x55728C68(level [ctx+0xC], target id)), TUnit = [cu+0x4C], then for
        0xB3 and 0xB4: if not GetAbilityEnabled(id) -> TAbstractUnit.ExpandAbility VMT+0x94 (= registry GetAbility ->
        ability.Expand(unit) -> unit.Changed); ret.  Other spells -> replayed prologue, resume 0x557F7E9E (the Blood
        Pact caves 0x55862000.. stay on that path).
v1 (markers 0xB3/0xB4 as TDurationAbility + real 0x9C/0x98 + a `cd` hook on 0x5574FEC4) is DETECTED (cd site hooked)
-> run --revert first (restores every v1/v2 site + zeroes the zone), then --apply.
Zone 0x55863D00..0x55864000 (verified zero, reloc-free); PIC via the call/pop delta (AoWEPACK rebases).
Backup <game>\\backup\\AoWEPACK.dll.bak_frenzy (whole file, taken before v1 - revert ONLY via --revert).
Also needed: Ability.pfs records 189 (0xB3 Haste) / 190 (0xB4 Fury) descriptions; ceilings LADDER bound 0xB5 (done).
Dry-run default; --apply / --revert / --dis.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DEFAULT_DLL = game_file("AoWEPACK.dll")
BAK_SUFFIX = ".bak_frenzy"
BASE, CODE_V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x55863D00, 0x55864000
SPELL_ID = 390
ABIL_HASTE, ABIL_FURY, NEW_HASTE, NEW_FURY = 0x98, 0x9C, 0xB3, 0xB4
REGABIL = 0x55750238
HASTE_CELL, HASTE_CREATE, HASTE_VMT = 0x557B7C2C, 0x557BAD98, 0x557B7C6C
FURY_CELL, FURY_CREATE, FURY_VMT = 0x557B82B8, 0x557BB2C8, 0x557B82F8
MODE_SLOT_ORIG = 0x55765A28                 # TUnitEnchantmentAbility.GetDurationMode (xor eax,eax)
CA_PARENT_EXEC, RESOLVE_UNIT = 0x557F6C84, 0x55728C68
SITES = {   # name: (va, original bytes, hook kind, resume)
    "exe": (0x557F7E98, bytes.fromhex("53568bf28bd8"), "jmp", 0x557F7E9E),
    "reg": (0x557BCDC6, bytes.fromhex("e86d34f9ff"), "call", None),
    "h1":  (0x5577FF43, bytes.fromhex("ba980000008bc68b08ff9148010000"), "call", None),
}
SLOTS = {   # name: (VMT slot va, original pointer)
    "mdh": (HASTE_VMT + 0x10C, MODE_SLOT_ORIG),
    "mdf": (FURY_VMT + 0x10C, MODE_SLOT_ORIG),
}
V1_CD = (0x5574FEC4, bytes.fromhex("535657558bea"))     # v1's extra site (TriggerCombatDone prologue), restored by --revert

ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm_delta(src, va):
    """PIC delta idiom `call $D / pop R / sub R, $D` (R = eax, ebx, ebp, esi, edi): two-pass, every anchor patched."""
    s1 = src.replace("call $D", ".byte 0xe8, 0, 0, 0, 0")
    for r in ("eax", "ebx", "ebp", "esi", "edi"): s1 = s1.replace("sub %s, $D" % r, "sub %s, 0x7fffffff" % r)
    b = bytearray(ks.asm(s1, va)[0]); n = 0
    for pop, sub in ((0x58, 0xE8), (0x5B, 0xEB), (0x5D, 0xED), (0x5E, 0xEE), (0x5F, 0xEF)):
        anchor = bytes([0xE8, 0, 0, 0, 0, pop]) + (b"\x2d" if pop == 0x58 else bytes([0x81, sub])) + b"\xff\xff\xff\x7f"
        k = b.find(anchor)
        while k >= 0:
            struct.pack_into("<I", b, k + len(anchor) - 4, va + k + 5); n += 1; k = b.find(anchor, k + len(anchor))
    assert n == src.count("call $D"), "delta anchors: %d of %d" % (n, src.count("call $D"))
    return bytes(b)


def build():
    out = bytearray(); where = {}
    def place(name, src):
        while len(out) % 16: out.append(0)
        where[name] = ZONE + len(out); out.extend(asm_delta(src, ZONE + len(out)))
    # exe: TTacticalCombatHighPrayerCA.Execute (eax = ca, edx = context): 390 -> grant 0xB3 + 0xB4 to the unit
    place("exe", """
        push ebx
        push esi
        mov esi, edx
        mov ebx, eax
        cmp dword ptr [ebx + 0x18], %(id)d
        jne vanilla
        mov edx, esi
        mov eax, ebx
        call %(parent)#x
        xor edx, edx
        mov dl, byte ptr [ebx + 0xd]
        mov eax, [esi + 0xc]
        call %(resolve)#x
        test eax, eax
        jz done
        mov ebx, [eax + 0x4c]
        test ebx, ebx
        jz done
        mov ecx, %(nhaste)d
        call grant
        mov ecx, %(nfury)d
        call grant
    done:
        pop esi
        pop ebx
        ret
    vanilla:
        jmp %(resume)#x
    grant:
        push ecx
        mov edx, ecx
        mov eax, ebx
        mov ecx, [eax]
        call dword ptr [ecx + 0x148]
        pop edx
        test al, al
        jnz g_done
        mov eax, ebx
        mov ecx, [eax]
        call dword ptr [ecx + 0x94]
    g_done:
        ret
    """ % {"id": SPELL_ID, "parent": CA_PARENT_EXEC, "resolve": RESOLVE_UNIT, "nhaste": NEW_HASTE, "nfury": NEW_FURY, "resume": SITES["exe"][3]})
    # mdh / mdf: GetDurationMode (eax = ability) -> 3 for the new instance, 0 otherwise
    for name, nid in (("mdh", NEW_HASTE), ("mdf", NEW_FURY)):
        place(name, """
        cmp dword ptr [eax + 0xc], %(nid)d
        mov eax, 0
        jne m_done
        mov al, 3
    m_done:
        ret
        """ % {"nid": nid})
    # h1: the Haste check (esi = unit): 0x98 OR 0xB3
    place("h1", """
        mov edx, %(haste)d
        mov eax, esi
        mov ecx, [eax]
        call dword ptr [ecx + 0x148]
        test al, al
        jnz h_done
        mov edx, %(nhaste)d
        mov eax, esi
        mov ecx, [eax]
        call dword ptr [ecx + 0x148]
    h_done:
        ret
    """ % {"haste": ABIL_HASTE, "nhaste": NEW_HASTE})
    # reg: replay the vanilla RegisterAbility call, then create + register the two instances
    place("reg", """
        call %(reg)#x
        push esi
        call $D
        pop esi
        sub esi, $D
        xor ecx, ecx
        mov dl, 1
        mov eax, [esi + %(hcell)#x]
        call %(hcreate)#x
        mov dword ptr [eax + 0xc], %(nhaste)d
        mov edx, eax
        mov eax, ebx
        call %(reg)#x
        xor ecx, ecx
        mov dl, 1
        mov eax, [esi + %(fcell)#x]
        call %(fcreate)#x
        mov dword ptr [eax + 0xc], %(nfury)d
        mov edx, eax
        mov eax, ebx
        call %(reg)#x
        pop esi
        ret
    """ % {"reg": REGABIL, "hcell": HASTE_CELL, "hcreate": HASTE_CREATE, "nhaste": NEW_HASTE, "fcell": FURY_CELL, "fcreate": FURY_CREATE, "nfury": NEW_FURY})
    assert ZONE + len(out) <= ZONE_END, hex(ZONE + len(out))
    return bytes(out), where


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
    hooks = {}
    for name, (va, orig, kind, resume) in SITES.items():
        op = b"\xe9" if kind == "jmp" else b"\xe8"
        hooks[name] = op + struct.pack("<i", where[name] - (va + 5)) + b"\x90" * (len(orig) - 5)
    states = {}
    for name, (va, orig, kind, resume) in SITES.items():
        live = d[va - CODE_V2F:va - CODE_V2F + len(orig)]
        states[name] = "vanilla" if live == orig else "ours" if live == hooks[name] else "v1" if live[0] in (0xE8, 0xE9) and ZONE <= va + 5 + struct.unpack_from("<i", live, 1)[0] < ZONE_END else "OTHER"
    for name, (va, orig) in SLOTS.items():
        v = struct.unpack_from("<I", d, va - CODE_V2F)[0]
        states[name] = "vanilla" if v == orig else "ours" if v == where[name] else "OTHER"
    cdl = d[V1_CD[0] - CODE_V2F:V1_CD[0] - CODE_V2F + 6]
    v1 = cdl != V1_CD[1]
    states["v1-cd"] = "v1 HOOKED" if v1 else "vanilla"
    zl = d[ZONE - CODE_V2F:ZONE_END - CODE_V2F]
    zstate = "zero" if not any(zl) else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else "DIFFERS (older build)"
    rl = reloc_set(d)
    bad = [hex(r) for r in rl if ZONE <= r < ZONE_END or any(va <= r < va + len(orig) for va, orig, _, _ in SITES.values())]
    print("sites %s | zone %s (%d B: %s) | relocs %s (VMT slots keep theirs by design)" % (states, zstate, len(zone), ", ".join("%s @%#x" % (k, v) for k, v in where.items()), bad or "none"))
    if bad or "OTHER" in states.values(): print("ABORT"); return 1
    if a.dis:
        import capstone
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(zone, ZONE): print("   %08X  %-16s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if a.revert:
        out = bytearray(d); out[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
        for name, (va, orig, kind, resume) in SITES.items(): out[va - CODE_V2F:va - CODE_V2F + len(orig)] = orig
        for name, (va, orig) in SLOTS.items(): struct.pack_into("<I", out, va - CODE_V2F, orig)
        out[V1_CD[0] - CODE_V2F:V1_CD[0] - CODE_V2F + 6] = V1_CD[1]
        write_inplace(a.dll, bytes(out)); print("reverted (v1/v2 sites + VMT slots -> vanilla, zone zeroed)"); return 0
    if v1 or zstate.startswith("DIFFERS") or "v1" in states.values(): print("an OLDER build (v1) is applied - run --revert first, then --apply"); return 1
    if all(s == "ours" for k, s in states.items() if k != "v1-cd") and zstate == "ours": print("already applied"); return 0
    out = bytearray(d); out[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
    out[ZONE - CODE_V2F:ZONE - CODE_V2F + len(zone)] = zone
    for name, (va, orig, kind, resume) in SITES.items(): out[va - CODE_V2F:va - CODE_V2F + len(orig)] = hooks[name]
    for name, (va, orig) in SLOTS.items(): struct.pack_into("<I", out, va - CODE_V2F, where[name])
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(a.dll, BAK_SUFFIX)
    if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    write_inplace(a.dll, bytes(out)); assert open(a.dll, "rb").read() == bytes(out); print("Written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
