"""
LIFE/AIR (2026-10-16) - AoWEPACK.dll only.  Sphere pair 10 (Life/Air):
  308 Heavenly Chorus  THighPrayer clone (class 37, infinite range, every friendly unit): removes Panicked (0x6C) and
                       raises morale to High (morale byte [unit+0x26] := 85 when below; levels: <=20 Terrible, 21-40
                       Poor, 41-60 Okay, 61-80 Good, >80 High - 0x5575AD64 via GetMorale 0x5577F178).
  309 Inspiration      TGreatHail clone (class 0x0A, 7 strikes = target hex + the 6 around it via patch_rotaway_v1.py
                       STRIKES[309] = 7, DMG 0): every FRIENDLY (same combat player as the caster) non-machine unit hit
                       gains 0xBC 'Inspired' (+1 RES, counts as Fearless) and 0xB3 'Haste (combat only)' (Frenzied
                       Charge's combat-only Haste instance - patch_frenzied_charge_v1.py makes every Haste check accept it).
0xBC 'Inspired' = a plain TDurationAbility instance, combat-only mode 3 (the Oil Spring / Earth-Life recipe: VMT
0x5571DD68, Create 0x55764CD4, [+0x24]=4, [+0x28]=3, [+0x20]=HighPrayerBlessing word) -> GetName "(combat only)",
TDurationAbility.CombatDone removes it.

Hooks (all CHAINED in front of what is there now; the previous target is stored in the zone header so --revert puts
it back exactly; --revert refuses if something else was chained in front of us since):
  reg  call-hook on the vanilla `call RegisterAbility` 0x557BCE9A (ebx = registry, the next unhooked site after Borrow
       Time's 0x557BCE65): replay, then create + register 0xBC 'Inspired'.
  sr   TDurationAbility VMT+0x64 (RES) slot: id 0xBC -> 1, else -> the previous slot target (Earth/Life's sr cave).
  fl   jmp-hook 0x5577F5E0 TAbstractUnit.GetAbilityEnabled prologue (Earth/Life's w2 jmp lives there): asked for 0x43
       Fearless and the unit's own bitset (VMT+0x14C) holds 0xBC -> TRUE; else the previous target.  Every Fearless check
       (TStrikeCA.Generate, ExecuteLifeMasteryFearRole, both Terror CAs - Lionheart's caves - and TCombatUnit
       GetAbilityEnabled 0x55725004 which forwards to unit VMT+0x148) lands here.
  hx   TTacticalCombatHighPrayerCA Execute VMT slot 0x557F4520 (Earth/Life's exe cave now): spell 308 -> parent
       0x557F6C84, result flag [ca+0x14], unit 0x55728C68(level [ctx+0xC], target [ca+0xD]), TUnit [cu+0x4C]:
       GetAbilityEnabled(0x6C) VMT+0x148 -> RemoveAbility VMT+0x98 (Healing's own recipe 0x5576C421); morale byte
       [unit+0x26] < 85 -> 85 + TUnit.Changed VMT+0x90.  NO heal.  Other spells -> previous target.
  ix   jmp-hook 0x557F6A20 TCombatSpellCA execute entry (Thousand Threads' jmp lives there): spell 309 -> resolve
       target ([ca+0xE]) and caster ([ca+0xD]) combat units; same combat player [cu+0x45], target TUnit not a machine
       (VMT+0x114 GetUnitType != 2) -> grant 0xBC and 0xB3 if not already enabled (VMT+0x148 / ExpandAbility VMT+0x94,
       which refreshes the stat cache).  Then always -> previous target (the CA's normal 0-damage execute).
v2 (2026-10-16, user feedback):
  308 no longer writes [unit+0x26] (that persisted after the battle): hx grants 0xBE 'Heavenly Chorus' (a second
       combat-only TDurationAbility, registered by the same reg cave right after 0xBC) + TUnit.Changed.
  gm   jmp-hook TAbstractUnit.GetMorale 0x5577F178 (9 B, vanilla movsx/call; the only path to MoraleValueToMorale;
       AoWx.exe's unit window imports it, the attack/defence morale tables at 0x5580F0A0/A5 index its grade): grade
       = MoraleValueToMorale([unit+0x26]) (0 Terrible .. 4 High); a unit holding 0xBE (own bitset VMT+0x14C) reports
       grade+1 (max 4) = one stage up for the rest of the combat.
  fh/fg THighPrayer / TGreatHail VMT+0xD8 fcGetDamageValueEx (fast/auto-combat scorer): spell 308 / 309 -> an
       all-zero result record + ret 8 (fcPrefetchCombatCommands drops a zero score) = never cast in auto combat.
  ai   THighPrayer VMT+0xD0 (tactical-AI command builder; TRemedy's is an empty ret): spell 308 -> ret = never cast
       by the AI.
Zone 0x5583A000..0x5583A800 (verified zero + reloc-free; PIC via call/pop delta, the DLL rebases).  Backup
<game>\\backup\\AoWEPACK.dll.bak_lifeair.  Dry-run default; --apply (upgrades an older build in place) / --revert / --dis.
Also needed: pipeline 308/309, ALIAS 308 -> 0x66 / 309 -> 0x74 + SITE_KEEP[0x40F0E3] += 309 + SITE_ALIAS 0x42827A
{309: 0x82}, patch_rotaway_v1.py STRIKES[309] = 7, Ability.pfs 198 (patch_lifeair_ability_pfs_v1.py), ceilings
LADDER += 0xBC (bound -> 0xBD).
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
from patch_earthlife_blessings_v1 import asm_delta, reloc_set, hook_bytes

DEFAULT_DLL = game_file("AoWEPACK.dll")
BAK_SUFFIX = ".bak_lifeair"
BASE, CODE_V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x5583A000, 0x5583A800
HDR = 0x20                                      # zone header: stored previous targets (u32 each)
SP_CHORUS, SP_INSPIRE = 308, 309
AB_INSPIRED, AB_HASTE_C, AB_FEARLESS, AB_PANICKED = 0xBC, 0xB3, 0x43, 0x6C
AB_CHORUS = 0xBE                                # v2: 'Heavenly Chorus' combat-only marker (morale +1 stage)
GETMORALE, MORALE_GRADE = 0x5577F178, 0x5575AD64  # v2: TAbstractUnit.GetMorale (exported; AoWx.exe imports it) / MoraleValueToMorale
GM_ORIG = bytes.fromhex("0fbe4026e8e3bbfdff")   # movsx eax,byte [eax+26h] / call MoraleValueToMorale
HP_VMT, GH_VMT = 0x557F458C, 0x557F5504         # THighPrayer / TGreatHail VMTs (the 308 / 309 donors)
REGABIL, LSTRASG = 0x55750238, 0x55701150
DUR_VMT, DUR_CREATE = 0x5571DD68, 0x55764CD4
HPB_WORD20 = 0x557BB808
CA_PARENT_EXEC, RESOLVE_UNIT = 0x557F6C84, 0x55728C68
REG_SITE, REG_ORIG = 0x557BCE9A, bytes.fromhex("e89933f9ff")
JMP_CHAIN = {"fl": 0x5577F5E0, "ix": 0x557F6A20}           # sites that currently hold another patch's `jmp cave` (5 B + nop)
SLOT_CHAIN = {"sr": DUR_VMT + 0x64, "hx": 0x557F4520,       # VMT slots: pointer chained
              "fh": HP_VMT + 0xD8, "fg": GH_VMT + 0xD8,     # v2: fast-combat scorers (fcGetDamageValueEx) of THighPrayer / TGreatHail
              "ai": HP_VMT + 0xD0}                         # v2: THighPrayer tactical-AI command builder
PREV_OFF = {"fl": 0, "ix": 4, "sr": 8, "hx": 12, "fh": 16, "fg": 20, "ai": 24}   # where each previous target is stored in the header

from keystone import Ks, KS_ARCH_X86, KS_MODE_32
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def build(d, prev):
    out = bytearray(HDR); where = {}
    for k, off in PREV_OFF.items(): struct.pack_into("<I", out, off, prev[k])
    def place(name, src):
        while len(out) % 16: out.append(0)
        va = ZONE + len(out); where[name] = va; out.extend(asm_delta(src, va))
    while len(out) % 4: out.append(0)
    nm = b"Inspired"
    out += struct.pack("<ii", -1, len(nm)); where["name"] = ZONE + len(out); out += nm + b"\0"
    while len(out) % 4: out.append(0)
    nm2 = b"Heavenly Chorus"
    out += struct.pack("<ii", -1, len(nm2)); where["name2"] = ZONE + len(out); out += nm2 + b"\0"
    w20 = struct.unpack_from("<H", d, HPB_WORD20 - CODE_V2F)[0]
    place("reg", """
        call %(reg)#x
        push esi
        call $D
        pop esi
        sub esi, $D
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
        lea eax, [esi + %(vmt)#x]
        xor ecx, ecx
        mov dl, 1
        call %(create)#x
        mov dword ptr [eax + 0xc], %(aid2)d
        mov byte ptr [eax + 0x24], 4
        mov byte ptr [eax + 0x28], 3
        mov word ptr [eax + 0x20], %(w20)d
        push eax
        lea edx, [esi + %(name2)#x]
        add eax, 8
        call %(lstrasg)#x
        pop edx
        mov eax, ebx
        call %(reg)#x
        pop esi
        ret
    """ % {"reg": REGABIL, "vmt": DUR_VMT, "create": DUR_CREATE, "aid": AB_INSPIRED, "aid2": AB_CHORUS, "w20": w20,
           "name": where["name"], "name2": where["name2"], "lstrasg": LSTRASG})
    place("sr", """
        cmp dword ptr [eax + 0xc], %(aid)d
        je one
        jmp %(prev)#x
    one:
        mov eax, 1
        ret
    """ % {"aid": AB_INSPIRED, "prev": prev["sr"]})
    place("fl", """
        cmp edx, %(fear)d
        jne pass
        push ebx
        push esi
        mov ebx, eax
        mov esi, edx
        mov edx, %(aid)d
        mov ecx, [eax]
        call dword ptr [ecx + 0x14c]
        test al, al
        jz restore
        mov al, 1
        pop esi
        pop ebx
        ret
    restore:
        mov eax, ebx
        mov edx, esi
        pop esi
        pop ebx
    pass:
        jmp %(prev)#x
    """ % {"fear": AB_FEARLESS, "aid": AB_INSPIRED, "prev": prev["fl"]})
    place("hx", """
        cmp dword ptr [eax + 0x18], %(sp)d
        je ours
        jmp %(prev)#x
    ours:
        push ebx
        push esi
        push edi
        mov esi, edx
        mov ebx, eax
        mov edx, esi
        mov eax, ebx
        call %(parent)#x
        cmp byte ptr [ebx + 0x14], 0
        je done
        xor edx, edx
        mov dl, byte ptr [ebx + 0xd]
        mov eax, [esi + 0xc]
        call %(resolve)#x
        test eax, eax
        jz done
        mov edi, [eax + 0x4c]
        test edi, edi
        jz done
        mov edx, %(pan)d
        mov eax, edi
        mov ecx, [eax]
        call dword ptr [ecx + 0x148]
        test al, al
        jz morale
        mov edx, %(pan)d
        mov eax, edi
        mov ecx, [eax]
        call dword ptr [ecx + 0x98]
    morale:
        mov edx, %(cho)d
        mov eax, edi
        mov ecx, [eax]
        call dword ptr [ecx + 0x148]
        test al, al
        jnz done
        mov edx, %(cho)d
        mov eax, edi
        mov ecx, [eax]
        call dword ptr [ecx + 0x94]
        mov eax, edi
        mov ecx, [eax]
        call dword ptr [ecx + 0x90]
    done:
        pop edi
        pop esi
        pop ebx
        ret
    """ % {"sp": SP_CHORUS, "prev": prev["hx"], "parent": CA_PARENT_EXEC, "resolve": RESOLVE_UNIT, "pan": AB_PANICKED, "cho": AB_CHORUS})
    place("ix", """
        cmp dword ptr [eax + 0x18], %(sp)d
        jne pass
        pushad
        mov esi, edx
        mov ebx, eax
        xor edx, edx
        mov dl, byte ptr [ebx + 0xe]
        mov eax, [esi + 0xc]
        call %(resolve)#x
        test eax, eax
        jz out
        mov edi, eax
        xor edx, edx
        mov dl, byte ptr [ebx + 0xd]
        mov eax, [esi + 0xc]
        call %(resolve)#x
        test eax, eax
        jz out
        mov dl, byte ptr [eax + 0x45]
        cmp dl, byte ptr [edi + 0x45]
        jne out
        mov edi, [edi + 0x4c]
        test edi, edi
        jz out
        mov eax, edi
        mov ecx, [eax]
        call dword ptr [ecx + 0x114]
        cmp al, 2
        je out
        mov ebp, %(inspired)d
        call grant
        mov ebp, %(haste)d
        call grant
    out:
        popad
    pass:
        jmp %(prev)#x
    grant:
        mov edx, ebp
        mov eax, edi
        mov ecx, [eax]
        call dword ptr [ecx + 0x148]
        test al, al
        jnz g_done
        mov edx, ebp
        mov eax, edi
        mov ecx, [eax]
        call dword ptr [ecx + 0x94]
    g_done:
        ret
    """ % {"sp": SP_INSPIRE, "prev": prev["ix"], "resolve": RESOLVE_UNIT, "inspired": AB_INSPIRED, "haste": AB_HASTE_C})
    place("gm", """
        push eax
        movsx eax, byte ptr [eax + 0x26]
        call %(grade)#x
        movzx eax, al
        pop edx
        cmp eax, 4
        jge gm_out
        push eax
        mov eax, edx
        mov edx, %(cho)d
        mov ecx, [eax]
        call dword ptr [ecx + 0x14c]
        test al, al
        pop eax
        jz gm_out
        inc eax
    gm_out:
        ret
    """ % {"grade": MORALE_GRADE, "cho": AB_CHORUS})
    for nm_, sp_ in (("fh", SP_CHORUS), ("fg", SP_INSPIRE)):
        place(nm_, """
            cmp dword ptr [eax + 0x10], %(sp)d
            je zero
            jmp %(prev)#x
        zero:
            mov eax, [esp + 4]
            xor edx, edx
            mov [eax], edx
            mov [eax + 4], edx
            mov [eax + 8], edx
            mov [eax + 0xc], edx
            mov word ptr [eax + 0x10], dx
            ret 8
        """ % {"sp": sp_, "prev": prev[nm_]})
    place("ai", """
        cmp dword ptr [eax + 0x10], %(sp)d
        je none
        jmp %(prev)#x
    none:
        ret
    """ % {"sp": SP_CHORUS, "prev": prev["ai"]})
    zone = bytes(out)
    assert ZONE + len(zone) <= ZONE_END, hex(ZONE + len(zone))
    return zone, where


def jmp_target(b, va):
    return va + 5 + struct.unpack_from("<i", b, 1)[0] if b[0] == 0xE9 else None


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--dll", default=DEFAULT_DLL)
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true"); ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read())
    rd = lambda va, n: bytes(d[va - CODE_V2F:va - CODE_V2F + n])
    u32 = lambda va: struct.unpack_from("<I", d, va - CODE_V2F)[0]
    inzone = lambda t: t is not None and ZONE <= t < ZONE_END
    zl = rd(ZONE, ZONE_END - ZONE)
    # current state of each chain point + the previous target it should chain to
    state, prev = {}, {}
    for k, va in JMP_CHAIN.items():
        t = jmp_target(rd(va, 5), va)
        if t is None: state[k] = "UNEXPECTED(%s)" % rd(va, 6).hex(); prev[k] = 0
        elif inzone(t): state[k] = "ours"; prev[k] = struct.unpack_from("<I", zl, PREV_OFF[k])[0]
        else: state[k] = "chain"; prev[k] = t
    for k, va in SLOT_CHAIN.items():
        t = u32(va)
        if inzone(t): state[k] = "ours"; prev[k] = struct.unpack_from("<I", zl, PREV_OFF[k])[0]
        else: state[k] = "chain"; prev[k] = t
    rb = rd(REG_SITE, 5)
    rt = REG_SITE + 5 + struct.unpack_from("<i", rb, 1)[0] if rb[0] == 0xE8 else None
    state["reg"] = "vanilla" if rb == REG_ORIG else "ours" if inzone(rt) else "OTHER(%s)" % rb.hex()
    gb = rd(GETMORALE, len(GM_ORIG))
    state["gm"] = "vanilla" if gb == GM_ORIG else "ours" if gb[0] == 0xE9 and inzone(jmp_target(gb, GETMORALE)) else "OTHER(%s)" % gb.hex()
    zone, where = build(bytes(d), prev)
    rl = reloc_set(bytes(d))
    bad = [hex(r) for r in rl if ZONE <= r < ZONE_END or any(va <= r < va + 6 for va in list(JMP_CHAIN.values()) + [REG_SITE])
           or GETMORALE <= r < GETMORALE + len(GM_ORIG)]
    noreloc = [k for k, va in SLOT_CHAIN.items() if va not in rl]
    zstate = "zero" if not any(zl) else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else "ours(old)" if any(s == "ours" for s in state.values()) else "DIFFERS"
    print("state %s | prev %s | zone %s (%d B: %s) | relocs in zone/sites %s | slots without reloc %s" % (
        state, {k: hex(v) for k, v in prev.items()}, zstate, len(zone), ", ".join("%s=%#x" % (k, v) for k, v in where.items() if not k.startswith("name")),
        bad or "none", noreloc or "none"))
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        cav = sorted((v, k) for k, v in where.items() if not k.startswith("name")) + [(ZONE + len(zone), None)]
        for (va, nm), (nx, _n) in zip(cav, cav[1:]):
            print("  [%s]" % nm)
            for i in md.disasm(zone[va - ZONE:nx - ZONE], va):
                if i.mnemonic == "add" and i.op_str == "byte ptr [eax], al": break
                print("   %08X  %-18s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad or noreloc or any(s.startswith(("UNEXPECTED", "OTHER")) for s in state.values()) or zstate == "DIFFERS" \
            or any(p == 0 or inzone(p) for p in prev.values()):
        print("ABORT"); return 1
    if a.revert:
        if not all(s == "ours" for s in state.values()):
            print("ABORT revert: not (fully) applied, or another patch is chained in front: %s" % state); return 1
        for k, va in JMP_CHAIN.items(): d[va - CODE_V2F:va - CODE_V2F + 5] = hook_bytes("jmp", va, prev[k], 5)
        for k, va in SLOT_CHAIN.items(): struct.pack_into("<I", d, va - CODE_V2F, prev[k])
        d[REG_SITE - CODE_V2F:REG_SITE - CODE_V2F + 5] = REG_ORIG
        d[GETMORALE - CODE_V2F:GETMORALE - CODE_V2F + len(GM_ORIG)] = GM_ORIG
        d[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
        with open(a.dll, "r+b") as f: f.write(bytes(d))
        print("reverted (chain points back to %s, reg site vanilla, zone zeroed)" % {k: hex(v) for k, v in prev.items()}); return 0
    if all(s == "ours" for s in state.values()) and zstate == "ours":
        print("already applied"); return 0
    if zstate == "ours(old)": print("older build of this patch detected -> rewriting the zone + every hook in place")
    d[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE); d[ZONE - CODE_V2F:ZONE - CODE_V2F + len(zone)] = zone
    for k, va in JMP_CHAIN.items(): d[va - CODE_V2F:va - CODE_V2F + 5] = hook_bytes("jmp", va, where[k], 5)
    for k, va in SLOT_CHAIN.items(): struct.pack_into("<I", d, va - CODE_V2F, where[k])
    d[REG_SITE - CODE_V2F:REG_SITE - CODE_V2F + 5] = hook_bytes("call", REG_SITE, where["reg"], 5)
    d[GETMORALE - CODE_V2F:GETMORALE - CODE_V2F + len(GM_ORIG)] = hook_bytes("jmp", GETMORALE, where["gm"], len(GM_ORIG))
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(a.dll, BAK_SUFFIX)
    if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    with open(a.dll, "r+b") as f: f.write(bytes(d))
    assert open(a.dll, "rb").read() == bytes(d); print("Written and verified"); return 0


if __name__ == "__main__":
    sys.exit(main())
