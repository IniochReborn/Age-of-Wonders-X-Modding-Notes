#!/usr/bin/env python3
r"""
Second Wind (310): the Life/Air tier-3 combat spell - "restores 5 HP and 50% movement" to a friendly unit (2026-10-16).
AoWEPACK.dll only.

Registered by patch_dual_sphere_spells_v1.py as a TRemedy instance (donor TRemedy, pfs 45 - like Martyr 360 / Cleansing
Flame 361 / Borrow Time 346: friendly single target, range 12 = long; pokes make it a COMBAT spell).  This script hooks
TRemedy's two spell-specific methods in FRONT of the current chain (Borrow Time's caves, which sit in front of Martyr's):

  ex  TRemedy.ExecuteSpell site 0x557E736C (eax spell, edx caster TUnit, ecx target TUnit; ret 8):  spell 310 ->
      ValidTarget (VMT+0x9C); heal +5 capped at max (TUnit VMT+0xE0 cur / +0xD0 max / +0xE4 set - the vanilla Remedy
      +5 code, as Cleansing Flame does with 3); then the MOVEMENT part, only on the tactical path:
        the call must come from the unit-spell combat action's hook (return address == 0x558166D3, the caster-cost
        cave patch_caster_cost_wallet_v1.py put on TUnitSpell CA.Execute 0x5577B419) - there esi = the CASTER's
        TCombatUnit (0x5577B3D4); the TARGET's CU is found in the combat object list (combat [cu+8] -> data [+0xC]
        -> [+0x34] -> TList [+8]: items +4, count +8) as the object whose [obj+0x4C] == the target TUnit.
        cap = CU GetMoves (VMT+0x94 -> unit VMT+0xD4; = the value TCPCK's NewCombatTurn 0x41CF77 refills [cu+0x5C] with),
        halved if the unit is Slowed (0xB9 - patch_slow_v1 halves [cu+0x5C] at turn start);
        [cu+0x5C] (remaining combat move points, dword; casting zeroes the caster's @0x40B6FE) := min(cap, cur + cap/2).
      Any other caller (fast combat etc.) just gets the heal.  Runs inside the recorded combat action -> replay/LAN
      deterministic.  Other spells -> the previous target (Borrow Time's ex cave).
  vt  TRemedy.ValidTarget site 0x557E7434 (same registers; vanilla prologue `push ebx / push esi / mov esi,ecx /
      mov ecx,esi`, epilogue 0x557E74DB pops esi/ebx):  310 -> the TUnitSpell base check 0x5577ACAC only (any valid
      friendly target: a full-HP unit may still want its moves back).  Other spells -> the previous target.
  AI: TRemedy inherits the EMPTY TCombatSpell AI valuers -> the AI never casts it (like Remedy / Martyr / Cleansing).

Both caves start `cmp dword [eax+0x10], imm32 / je rel8 / jmp rel32` (the chain contract of patch_borrowtime_v1.py's
cave_prev: the next script in front can decode our 'previous').  Caves AoWEPACK 0x55839000..0x55839400 (zero, no
relocs).  PIC: rel32 within the image + call/pop delta for the return-address check.  --revert restores the previous
jmps and refuses if another hook was put in front of ours.  ⚠ With this applied, patch_borrowtime_v1.py's chained
ex/vt sites point here -> its dry run reports OTHER/ABORT (expected chain state): revert Second Wind first.
v3 (2026-10-16, user feedback):
  reg  call-hook on the vanilla `call RegisterAbility` 0x557BCF6E (ebx = registry; the last registration, id 0x91 -
       the next unhooked site; 0x557BCDFB / 0x557BCE30 are still free): replay, then create + register 0xBF 'Second
       Wind' = a plain TDurationAbility, combat-only mode 3 (the Inspired / Heavenly Chorus recipe: VMT 0x5571DD68,
       Create 0x55764CD4, [+0x24]=4, [+0x28]=3, [+0x20]=HighPrayerBlessing word) -> GetName "Second Wind (combat only)",
       TDurationAbility.CombatDone removes it.  A pure marker: no VMT slot / ability check keys on 0xBF -> no per-turn
       effect (the heal and the movement happen ONLY inside ExecuteSpell, i.e. at the cast).
  ex   on the tactical path, after the movement + table record: the target TUnit gains 0xBF (VMT+0x148 check,
       ExpandAbility VMT+0x94) unless it already has it.
  vt   310: the TUnitSpell base check AND the target must NOT hold 0xBF (VMT+0x148) -> a unit can get its second
       wind only once per battle (ex runs vt first, so a re-cast is refused before any effect).
  Ability.pfs record 201 = patch_secondwind_ability_pfs_v1.py; ceilings LADDER += 0xBF (bound -> 0xC0).
  The hover half (ability lists in the unit panel) = patch_exe_secondwind_fullmp_v1.py (AoWx.exe).
Upgrades v1/v2 in place.  --revert also restores the reg site.
Backup <game>\backup\AoWEPACK.dll.bak_secondwind.  Dry-run default.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DEFAULT_DLL = game_file("AoWEPACK.dll")
BAK_SUFFIX = ".bak_secondwind"
BASE, CODE_V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x55839000, 0x55839400
SPELL, HEAL, ABIL_SLOW = 310, 5, 0xB9
EX_SITE, VT_SITE = 0x557E736C, 0x557E7434                 # TRemedy ExecuteSpell / ValidTarget entries (6 B jmps of the chain)
VT_EPI = 0x557E74DB                                       # TRemedy.ValidTarget epilogue (pop esi / pop ebx / ret)
BASECHECK = 0x5577ACAC                                    # TUnitSpell base ValidTarget
CA_RET = 0x558166D3                                       # return address of ExecuteSpell when called from TUnitSpell CA.Execute (tactical)
FM_TAB, FM_N = 0x558E9F80, 8                              # v2 2026-10-16: 'full-MP' table - 8 x TCombatUnit* in DATA zero-fill slack (past raw DATA 0x558E9C00,
                                                          #   below BSS 0x558EA000; diag scripts use up to ~0x558E9D60).  patch_tc_secondwind_fullmp_v1.py (TCPCK)
                                                          #   finds it via the import slot of AoWE.ValidateAoWEngine and treats a listed unit as having FULL move
                                                          #   points for its ability checks; it removes the unit again at the unit's next turn-start MP refill.
AB_SW = 0xBF                                              # v3: 'Second Wind' combat-only marker ability
REG_SITE, REG_ORIG = 0x557BCF6E, bytes.fromhex("e8c532f9ff")   # v3: vanilla `call RegisterAbility` (id 0x91, ebx = registry)
REGABIL, LSTRASG = 0x55750238, 0x55701150
DUR_VMT, DUR_CREATE = 0x5571DD68, 0x55764CD4
HPB_WORD20 = 0x557BB808
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, va):
    return bytes(ks.asm(src, va)[0])


def jmp_target(d, va):
    b = d[va - CODE_V2F:va - CODE_V2F + 5]
    return va + 5 + struct.unpack_from("<i", b, 1)[0] if b[0] == 0xE9 else None


def build(prev_ex, prev_vt, ver=3, w20=0):
    v2 = ver >= 2
    out = bytearray(); where = {}

    def place(name, src):
        while len(out) % 16: out.append(0)
        va = ZONE + len(out); where[name] = va
        b = asm(src, va)
        assert b[0:3] == b"\x81\x78\x10" and b[7] == 0x74 and b[9] == 0xE9, "chain layout broken in %s" % name
        out.extend(b)

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
        mov eax, ebx
        mov edx, [eax]
        call dword ptr [edx + 0xe0]
        movsx edi, al
        add edi, %(heal)d
        mov eax, ebx
        mov edx, [eax]
        call dword ptr [edx + 0xd0]
        movsx eax, al
        cmp edi, eax
        jle hpok
        mov edi, eax
    hpok:
        mov edx, edi
        mov eax, ebx
        mov ecx, [eax]
        call dword ptr [ecx + 0xe4]
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
        mov eax, [eax + 8]
        test eax, eax
        je ok
        mov eax, [eax + 0xc]
        test eax, eax
        je ok
        mov eax, [eax + 0x34]
        test eax, eax
        je ok
        mov eax, [eax + 8]
        test eax, eax
        je ok
        mov ecx, [eax + 8]
        mov edx, [eax + 4]
    find:
        dec ecx
        js ok
        mov edi, [edx + ecx*4]
        test edi, edi
        je find
        cmp [edi + 0x4c], ebx
        jne find
        mov eax, edi
        mov edx, [eax]
        call dword ptr [edx + 0x94]
        mov esi, eax
        mov edx, %(slow)d
        mov eax, ebx
        mov ecx, [eax]
        call dword ptr [ecx + 0x148]
        test al, al
        je noslow
        sar esi, 1
    noslow:
        mov eax, esi
        sar eax, 1
        add eax, [edi + 0x5c]
        cmp eax, esi
        jle mvok
        mov eax, esi
    mvok:
        cmp eax, [edi + 0x5c]
        jle %(after_mv)s
        mov [edi + 0x5c], eax
%(record)s    ok:
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
    """ % {"spell": SPELL, "prev": prev_ex, "heal": HEAL, "caret": CA_RET, "slow": ABIL_SLOW,
           "after_mv": "rec" if v2 else "ok",
           # v2: list the target CU (edi) in the full-MP table (PIC): kept if already listed, else the first empty slot, else
           # slot (cu >> 4) & 7 - deterministic on every machine (runs inside the recorded combat action)
           "record": ("""    rec:
        call fmd
    fmd:
        pop ecx
        sub ecx, fmd
        add ecx, %(tab)#x
        xor edx, edx
    fml:
        mov eax, [ecx + edx*4]
        cmp eax, edi
        je ok
        test eax, eax
        je fmput
        inc edx
        cmp edx, %(n)d
        jb fml
        mov edx, edi
        shr edx, 4
        and edx, %(m)d
    fmput:
        mov [ecx + edx*4], edi
""" % {"tab": FM_TAB, "n": FM_N, "m": FM_N - 1}).replace("je ok", "je grant" if ver >= 3 else "je ok") + (
           # v3: the target gains the 0xBF 'Second Wind' marker (ebx = target TUnit)
           """    grant:
        mov edx, %(ab)d
        mov eax, ebx
        mov ecx, [eax]
        call dword ptr [ecx + 0x148]
        test al, al
        jnz ok
        mov edx, %(ab)d
        mov eax, ebx
        mov ecx, [eax]
        call dword ptr [ecx + 0x94]
""" % {"ab": AB_SW} if ver >= 3 else "") if v2 else ""})

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
%(refuse)s        jmp %(epi)#x
    """ % {"spell": SPELL, "prev": prev_vt, "base": BASECHECK, "epi": VT_EPI,
           "refuse": """        test al, al
        jz vt_out
        mov edx, %(ab)d
        mov eax, esi
        mov ecx, [eax]
        call dword ptr [ecx + 0x148]
        test al, al
        sete al
    vt_out:
""" % {"ab": AB_SW} if ver >= 3 else ""})
    if ver >= 3:                                                           # v3: 0xBF name literal + registration cave
        while len(out) % 4: out.append(0)
        nm = b"Second Wind"
        out += struct.pack("<ii", -1, len(nm)); where["name"] = ZONE + len(out); out += nm + b"\0"
        while len(out) % 16: out.append(0)
        va = ZONE + len(out); where["reg"] = va
        out.extend(asm("""
            call %(reg)#x
            push esi
            call rd
        rd:
            pop esi
            sub esi, rd
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
        """ % {"reg": REGABIL, "vmt": DUR_VMT, "create": DUR_CREATE, "aid": AB_SW, "w20": w20, "name": where["name"],
               "lstrasg": LSTRASG}, va))
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

    def cave_prev(cave):
        o = cave - CODE_V2F
        assert d[o + 7] == 0x74 and d[o + 9] == 0xE9, "cave layout unexpected @%#x" % cave
        return cave + 14 + struct.unpack_from("<i", d, o + 10)[0]

    # the CA return address the movement part keys on must still be the caster-cost cave's call
    assert g(CA_RET - 6, 6) == bytes.fromhex("ff97b4000000"), "TUnitSpell CA ExecuteSpell call @%#x moved: %s" % (CA_RET - 6, g(CA_RET - 6, 6).hex())
    cur = {k: jmp_target(d, va) for k, va in (("ex", EX_SITE), ("vt", VT_SITE))}
    assert cur["ex"] and cur["vt"], "TRemedy sites are not jmp-hooked (patch_martyr_cleansing_v1 + patch_borrowtime_v1 first): %s %s" % (g(EX_SITE, 6).hex(), g(VT_SITE, 6).hex())
    prev = {k: (cave_prev(t) if inzone(t) else t) for k, t in cur.items()}
    w20 = struct.unpack_from("<H", d, HPB_WORD20 - CODE_V2F)[0]
    builds = {v: build(prev["ex"], prev["vt"], ver=v, w20=w20) for v in (3, 2, 1)}
    zone, where = builds[3]
    zver = next((v for v in (3, 2, 1) if zl[:len(builds[v][0])] == builds[v][0] and not any(zl[len(builds[v][0]):])), None)
    zstate = "zero" if not any(zl) else "ours" if zver == 3 else "v%d" % zver if zver else "DIFFERS"
    wz = builds[zver][1] if zver else where                                # where the sites point when an older build is applied
    chained = [("ex", EX_SITE, 6), ("vt", VT_SITE, 6)]
    st = {k: ("ours" if cur[k] == wz[k] else "prev" if not inzone(cur[k]) else "OTHER") for k, _va, _n in chained}
    rb = g(REG_SITE, 5)
    rt = REG_SITE + 5 + struct.unpack_from("<i", rb, 1)[0] if rb[0] == 0xE8 else None
    st["reg"] = "vanilla" if rb == REG_ORIG else "ours" if zver == 3 and rt == where["reg"] else "OTHER(%s)" % rb.hex()
    rl = reloc_set(d)
    bad = [hex(r) for r in rl if ZONE - 3 <= r < ZONE_END or any(va - 3 <= r < va + n for _k, va, n in chained + [("reg", REG_SITE, 5)])]
    print("sites %s | chain ex -> %#x, vt -> %#x | zone %s (%d B) | relocs %s | caves %s"
          % (st, prev["ex"], prev["vt"], zstate, len(zone), bad or "none", ", ".join("%s=%#x" % kv for kv in where.items())))
    if bad or any(v.startswith("OTHER") for v in st.values()) or zstate == "DIFFERS": print("ABORT"); return 1
    if zver in (1, 2) and not (st["ex"] == st["vt"] == "ours"): print("ABORT: zone holds build v%d but the sites do not point at it" % zver); return 1
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        for i in md.disasm(zone, ZONE): print("   %08X  %-16s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if a.revert:
        if not any(v == "ours" for v in st.values()): print("nothing to revert"); return 0
        out = bytearray(d)
        for k, va, n in chained:
            if st[k] == "ours": out[va - CODE_V2F:va - CODE_V2F + n] = rel(0xE9, va, prev[k], n)
        out[REG_SITE - CODE_V2F:REG_SITE - CODE_V2F + 5] = REG_ORIG
        out[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
        write_inplace(a.dll, bytes(out)); print("reverted (ex -> %#x, vt -> %#x, reg site vanilla)" % (prev["ex"], prev["vt"])); return 0
    if all(v == "ours" for v in st.values()) and zstate == "ours": print("already applied"); return 0
    if zstate == "ours": print("ABORT: zone holds our code but the sites do not point at it"); return 1
    if zver in (1, 2): print("older build v%d detected -> upgrading in place" % zver)
    out = bytearray(d)
    out[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
    out[ZONE - CODE_V2F:ZONE - CODE_V2F + len(zone)] = zone
    for k, va, n in chained: out[va - CODE_V2F:va - CODE_V2F + n] = rel(0xE9, va, where[k], n)
    out[REG_SITE - CODE_V2F:REG_SITE - CODE_V2F + 5] = rel(0xE8, REG_SITE, where["reg"], 5)
    print("%d bytes change" % sum(1 for x, y in zip(d, out) if x != y))
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(a.dll, BAK_SUFFIX)
    if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    write_inplace(a.dll, bytes(out)); assert open(a.dll, "rb").read() == bytes(out); print("Written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
