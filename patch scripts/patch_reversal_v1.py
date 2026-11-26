#!/usr/bin/env python3
r"""
Reversal (234): the Secret tier-3 COMBAT spell - "swaps the target unit's ATK/DEF and RES/DMG until the end of combat",
single target (friendly OR enemy), long range (2026-10-18).  AoWEPACK.dll only.

Registered by patch_dual_sphere_spells_v1.py as a TRemedy instance (donor TRemedy, pfs 45, tc_type 7 - the Suspend 214
chassis).  New ability 0xC7 'Reversed' = a plain TDurationAbility (VMT 0x5571DD68, Create 0x55764CD4) in duration
MODE 3 = until combat end (CombatDone - the mod cave 0x55862130 - removes modes 2 and 3 at combat end, as Steadfast's
0xC5), so nothing survives the battle.

Design decisions (documented for the user):
  * MELEE attack (unit VMT+0xC0) <-> DEFENSE (VMT+0xC4) and DAMAGE (VMT+0xC8) <-> RESISTANCE (VMT+0xCC).  The RANGED
    attack (GetAttackRA, its own record field) is NOT swapped - a ranged unit keeps its bow strength.
  * The swap is of the FINAL values: the reversed unit's attack getter returns its full defense getter (every other mod
    included - Steadfast, Smokescreen, medals, items ...) and vice versa.  Shown in the unit panel and used in combat
    (the TCombatUnit getters 0x55725490.. call the same VMT slots).
  * Re-casting Reversal on a reversed unit TOGGLES it back (the ability is removed); on any other unit it is granted.
  * No resistance roll - it always works, on friend or foe (a deliberate swap can help or hurt either side).

Hooks (zone AoWEPACK 0x55880800..0x55881000, verified zero + reloc-free; the header keeps every site's bytes found at
apply time, so --revert restores them EXACTLY; chained sites are decoded at apply time):
  reg  splice of the `call` @0x557BCF6E (RegisterAbility chain): `call prev`, then create + register 0xC7 'Reversed'
       (mode 3, [+0x24] 4, [+0x20] = the HighPrayerBlessing word) - Suspend's recipe.
  ex   TRemedy.ExecuteSpell 0x557E736C (chained in front, 'cmp' layout): 234 -> ValidTarget (VMT+0x9C); tactical path
       only (return address == the caster-cost cave's 0x558166D3, esi = caster CU with [esi+0x4C] == caster):
       target HasAbility(0xC7) ? RemoveAbility (VMT+0x98) : ExpandAbility (VMT+0x94); unit.Changed (VMT+0x90).
       Recorded combat action -> replay / LAN deterministic (no RNG).
  vt   TRemedy.ValidTarget 0x557E7434 (chained in front, 'cmp' layout): 234 -> the TUnitSpell base check only (refuses
       machines), any side.
  gci  TUnitSpell.GetCombatInfo call site 0x5577AC86 (chained in front of patch_suspend_fix_v1's cave): 234 -> info
       shots 1 / range 0x0C / targets 0 / side 3 (own + enemies), ATK byte 0, straight to the epilogue 0x5577AC95.
  vmt  the 4 stat slots (+0xC0/+0xC4/+0xC8/+0xCC) of the 3 unit VMTs (TUnit 0x55710CAC, THero 0x55711FEC / 0x55712238)
       -> 12 trampolines (`push idx / jmp common`).  common: reentrancy flag clear AND the unit holds 0xC7 (the BASE bit
       test TUnit.HasAbility 0x5577F618, bounds-checked, never dereferences a combat unit - the Steadfast-v3 lesson)
       -> flag := 1, call the PARTNER slot through the unit's own VMT (atk<->def, dmg<->res; the partner wrapper sees
       the flag and passes straight to its original), flag := 0, return its value.  Otherwise tail-jump to the slot's
       ORIGINAL pointer (saved in the header; whatever entry hooks live there - Smokescreen's GetAttack, Steadfast's
       GetDefense - keep working).  PIC: header table + flag via a call/pop delta.  The flag lives in AoWEPACK .idata
       page slack 0x5590BFF0 (runtime-only zero memory past the section's raw data).
Dry-run default; --apply / --revert / --dis; --dll <scratch copy>.  Backup <game>\backup\AoWEPACK.dll.bak_reversal.
LIFO: while applied, patch_suspend_fix_v1 / patch_suspend_v1 / anything that re-decodes 0x557BCF6E, 0x557E736C,
0x557E7434 or 0x5577AC86 sees them as OTHER - revert Reversal first, re-run them, re-apply Reversal.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DEFAULT_DLL = game_file("AoWEPACK.dll")
BAK_SUFFIX = ".bak_reversal"
BASE, CODE_V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x55880800, 0x55881000
HDR = 0x60
SPELL, AB = 234, 0xC7
NAME = b"Reversed"
FLAG = 0x5590BFF0                                         # runtime-only .idata page slack (zero at load)
CA_RET = 0x558166D3
BASECHECK, VT_EPI = 0x5577ACAC, 0x557E74DB
HASAB = 0x5577F618
REGABIL, LSTRASG = 0x55750238, 0x55701150
DUR_VMT, DUR_CREATE = 0x5571DD68, 0x55764CD4
HPB_WORD20 = 0x557BB808
GCI_EPI = 0x5577AC95
GCI_INFO47 = 0x03000C01                                   # shots 1 / range 0x0C / targets 0 / side 3
VMTS = (0x55710CAC, 0x55711FEC, 0x55712238)               # TUnit, THero x2 (slot +0xC0 = GetAttack)
STAT_SLOTS = (0xC0, 0xC4, 0xC8, 0xCC)                     # ATK, DEF, DMG, RES
SITES = [("reg", 0x557BCF6E, 5, "call"), ("ex", 0x557E736C, 6, "jmp"), ("vt", 0x557E7434, 6, "jmp"),
         ("gci", 0x5577AC86, 5, "call")]
PTRS = [("p%d_%x" % (v, s), VMTS[v] + s) for v in range(3) for s in STAT_SLOTS]   # 12 slot pointers, idx = v*4 + k
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, va):
    return bytes(ks.asm(src, va)[0])


def rel(op, va, target, size):
    return bytes([op]) + struct.pack("<i", target - (va + 5)) + b"\x90" * (size - 5)


SITE_HDR = sum(n for _nm, _va, n, _k in SITES)            # 22
TABLE_OFF = 0x20                                          # 12 saved slot pointers at ZONE+0x20 = the trampoline table


def build(prev, w20):
    out = bytearray(HDR); where = {}

    def place(name, src, layout=None):
        while len(out) % 16: out.append(0)
        va = ZONE + len(out); where[name] = va
        b = asm(src, va)
        if layout == "cmp": assert b[0:3] == b"\x81\x78\x10" and b[7] == 0x74 and b[9] == 0xE9, name
        if layout == "call": assert b[0] == 0xE8, name
        out.extend(b)

    out += struct.pack("<ii", -1, len(NAME)); where["name"] = ZONE + len(out); out += NAME + b"\0"

    place("ex", """
        cmp dword ptr [eax + 0x10], %(spell)d
        je mine
        jmp %(prev)#x
    mine:
        push ebp
        mov ebp, esp
        sub esp, 12
        push ebx
        push esi
        push edi
        mov [ebp - 4], edx
        mov [ebp - 8], esi
        mov edx, [ebp + 4]
        mov [ebp - 12], edx
        mov ebx, ecx
        mov esi, eax
        mov ecx, ebx
        mov edx, [ebp - 4]
        mov eax, esi
        mov edi, [eax]
        call dword ptr [edi + 0x9c]
        test al, al
        je fail
        call here
    here:
        pop eax
        sub eax, here
        add eax, %(caret)#x
        cmp eax, [ebp - 12]
        jne ok
        mov eax, [ebp - 8]
        test eax, eax
        je ok
        mov edx, [ebp - 4]
        cmp [eax + 0x4c], edx
        jne ok
        mov eax, ebx
        mov edx, %(ab)d
        call %(hasab)#x
        test al, al
        jne rem
        mov edx, %(ab)d
        mov eax, ebx
        mov ecx, [eax]
        call dword ptr [ecx + 0x94]
        jmp chg
    rem:
        mov edx, %(ab)d
        mov eax, ebx
        mov ecx, [eax]
        call dword ptr [ecx + 0x98]
    chg:
        mov eax, ebx
        mov edx, [eax]
        call dword ptr [edx + 0x90]
    ok:
        mov al, 1
        jmp done
    fail:
        xor eax, eax
    done:
        pop edi
        pop esi
        pop ebx
        mov esp, ebp
        pop ebp
        ret 8
    """ % {"spell": SPELL, "prev": prev["ex"], "caret": CA_RET, "ab": AB, "hasab": HASAB}, "cmp")

    place("vt", """
        cmp dword ptr [eax + 0x10], %(spell)d
        je mine
        jmp %(prev)#x
    mine:
        push ebx
        push esi
        mov esi, ecx
        mov ecx, esi
        call %(base)#x
        jmp %(epi)#x
    """ % {"spell": SPELL, "prev": prev["vt"], "base": BASECHECK, "epi": VT_EPI}, "cmp")

    place("gci", """
        cmp dword ptr [esi + 0x10], %(spell)d
        jne other
        mov dword ptr [ebx + 4], %(info)#x
        mov byte ptr [ebx], 0
        pop eax
        jmp %(epi)#x
    other:
        jmp %(prev)#x
    """ % {"spell": SPELL, "info": GCI_INFO47, "epi": GCI_EPI, "prev": prev["gci"]})

    place("common", """
        push ebx
        push esi
        call d1
    d1:
        pop esi
        sub esi, d1
        mov ebx, [esp + 8]
        mov ecx, [esi + ebx*4 + %(table)#x]
        add ecx, esi
        cmp byte ptr [esi + %(flag)#x], 0
        jne pass
        push eax
        push ecx
        mov edx, %(ab)d
        call %(hasab)#x
        test al, al
        pop ecx
        pop eax
        je pass
        mov byte ptr [esi + %(flag)#x], 1
        and ebx, 3
        xor ebx, 1
        mov edx, [eax]
        call dword ptr [edx + ebx*4 + 0xc0]
        mov byte ptr [esi + %(flag)#x], 0
        pop esi
        pop ebx
        add esp, 4
        ret
    pass:
        mov [esp + 8], ecx
        pop esi
        pop ebx
        ret
    """ % {"table": ZONE + TABLE_OFF, "flag": FLAG, "ab": AB, "hasab": HASAB})

    for i in range(len(PTRS)):
        place("t%d" % i, "push %d\njmp %#x" % (i, where["common"]))

    place("reg", """
        call %(prev)#x
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
    """ % {"prev": prev["reg"], "vmt": DUR_VMT, "create": DUR_CREATE, "ab": AB, "w20": w20, "name": where["name"],
           "lstrasg": LSTRASG, "reg": REGABIL}, "call")
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
    g = lambda va, n: bytes(d[va - CODE_V2F:va - CODE_V2F + n])
    zl = g(ZONE, ZONE_END - ZONE)
    tgt = lambda b, va: va + 5 + struct.unpack_from("<i", b, 1)[0] if b[0] in (0xE8, 0xE9) else None
    applied = any(zl[HDR:])
    saved = {}; o = 0
    for name, va, n, _k in SITES: saved[name] = zl[o:o + n]; o += n
    for i, (name, va) in enumerate(PTRS): saved[name] = zl[TABLE_OFF + 4 * i:TABLE_OFF + 4 * i + 4]
    cur = {name: g(va, n) for name, va, n, _k in SITES}
    cur.update({name: g(va, 4) for name, va in PTRS})
    src = saved if applied else cur
    prev = {name: tgt(src[name], va) for name, va, n, _k in SITES}
    w20 = struct.unpack_from("<H", d, HPB_WORD20 - CODE_V2F)[0]
    if not applied:
        for name, va, n, kind in SITES:
            want = 0xE8 if kind == "call" else 0xE9
            assert cur[name][0] == want, "%s site %#x is not chained (%s) - apply the chain below first" % (name, va, cur[name].hex())
        for k, s in enumerate(STAT_SLOTS):                 # all 3 VMTs: slot +0xC0..+0xCC still the unit getters
            vals = [struct.unpack("<I", cur["p%d_%x" % (v, s)])[0] for v in range(3)]
            assert all(0x55700000 < x < 0x558E8000 and not (ZONE <= x < ZONE_END) for x in vals), (hex(s), [hex(x) for x in vals])
    zone, where = build(prev, w20)
    hdr = bytearray(zone[:HDR])
    o = 0
    for name, va, n, _k in SITES: hdr[o:o + n] = (saved if applied else cur)[name]; o += n
    assert o <= TABLE_OFF
    for i, (name, va) in enumerate(PTRS): hdr[TABLE_OFF + 4 * i:TABLE_OFF + 4 * i + 4] = (saved if applied else cur)[name]
    zone = bytes(hdr) + zone[HDR:]
    hooked = {name: rel(0xE8 if kind == "call" else 0xE9, va, where[name], n) for name, va, n, kind in SITES}
    hooked.update({name: struct.pack("<I", where["t%d" % i]) for i, (name, va) in enumerate(PTRS)})
    allsites = [(nm, va, n) for nm, va, n, _k in SITES] + [(nm, va, 4) for nm, va in PTRS]
    st = {nm: ("ours" if cur[nm] == hooked[nm] else "orig" if (not applied or cur[nm] == saved.get(nm)) else "OTHER")
          for nm, _va, _n in allsites}
    zstate = "zero" if not any(zl) else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else "DIFFERS"
    rl = reloc_set(d)
    bad = [hex(r) for r in rl if ZONE - 3 <= r < ZONE_END or any(va - 3 <= r < va + n for _nm, va, n, _k in SITES)]
    ptr_reloc_ok = all(va in rl for _nm, va in PTRS)
    print("sites %s | slots %s | prev %s | zone %s (%d B) | relocs in zone/sites %s | slot relocs %s | caves %s"
          % ({k: st[k] for k, *_ in SITES}, sorted(set(st[nm] for nm, _va in PTRS)),
             ", ".join("%s=%#x" % kv for kv in prev.items()), zstate, len(zone), bad or "none",
             "ok" if ptr_reloc_ok else "MISSING",
             ", ".join("%s=%#x" % (k, v) for k, v in where.items() if not k.startswith("t") or k == "t0")))
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        for i in md.disasm(zone[HDR:], ZONE + HDR): print("   %08X  %-24s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad or not ptr_reloc_ok or "OTHER" in st.values() or zstate == "DIFFERS": print("ABORT"); return 1
    if a.revert:
        if not applied: print("already reverted"); return 0
        out = bytearray(d)
        for nm, va, n in allsites: out[va - CODE_V2F:va - CODE_V2F + n] = saved[nm]
        out[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
        write_inplace(a.dll, bytes(out)); print("reverted (sites + VMT slots restored from the zone header)"); return 0
    if all(v == "ours" for v in st.values()) and zstate == "ours": print("already applied"); return 0
    if applied: print("ABORT: zone holds our code but the sites do not all point at it"); return 1
    out = bytearray(d)
    out[ZONE - CODE_V2F:ZONE - CODE_V2F + len(zone)] = zone
    for nm, va, n in allsites: out[va - CODE_V2F:va - CODE_V2F + n] = hooked[nm]
    print("%d bytes change" % sum(1 for x, y in zip(d, out) if x != y))
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if os.path.abspath(a.dll) == os.path.abspath(DEFAULT_DLL):
        bak = bak_path(a.dll, BAK_SUFFIX)
        if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    write_inplace(a.dll, bytes(out)); assert open(a.dll, "rb").read() == bytes(out); print("Written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
