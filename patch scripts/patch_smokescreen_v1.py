#!/usr/bin/env python3
r"""
SMOKESCREEN (spell 225, Fire tier 2, 2026-10-17) - AoWEPACK half: the 'Smoke Screened' status 0xC6 and its accuracy
penalty.  The smoke hexes on the combat map live in AoWTCPCK.dll (patch_tc_smokescreen_v1.py - apply THIS script
first, the field script calls this zone's export).

User spec: "Combat spell, long range, large AOE.  Research 50, Cost 4.  Lingering AOE applies debuff to melee /
projectile accuracy to units without True Seeing (same as Invisibility) within the AOE, lasts 3 turns."

'Same as Invisibility' = our True-Seeing-vs-Invisible rule (build 2026-07-23, trueseeing-vs-invisible-atk-penalty):
an attacker WITHOUT True Seeing (0x29) striking a target WITH Invisibility (0x36) loses ATTACK at strike time:
melee -3 (byte clamp >= 1 at CreateStrikeCA; signed modifier in TMeleeRound.CalculateStrikes), ranged by the shot's
range tier [ability+0x28]: tier <= 1 -> 0, 2 -> -2, 3+ -> -3 (byte clamp >= 1).  Smokescreen applies EXACTLY that
penalty when the attacker lacks True Seeing and the ATTACKER OR THE TARGET stands in the smoke (holds 0xC6):
fighting into the smoke = like attacking an invisible unit; fighting out of it = the shooter / striker is blinded too.
It never stacks: when the target is genuinely Invisible the vanilla-rule cave behind us applies its own -3/-2 and we
add nothing.  True Seeing attackers ignore the smoke entirely.

0xC6 'Smoke Screened' = a combat-only TDurationAbility (mode 3 - TDurationAbility.CombatDone removes it at the end of
every combat; the Inspired / Grounded / Sanctified recipe), held by a unit while it stands on a smoke hex (granted /
removed by sm_sync).  Every unit can hold it (machines too); the penalty itself is the True-Seeing test above.

Zone AoWEPACK 0x5587A800..0x5587B000 (verified zero, CODE, reloc-free; PIC call/pop delta - the DLL rebases):
  +0x00 header: the previous chain targets (reg, pom, m1, m2, rg), u32 each
  +0x20 EXPORT jmp sm_sync  (eax = TUnit, dl = 1 'stands on a smoke hex' / 0 'not'): grants 0xC6
        (TAbilityControl.GetAbility(0xC6).Expand, VMT+0xD0) / removes it (RemoveAbility 0x5577F6EC); unit.Changed
        (VMT+0x90) after either.  All registers but eax preserved.
  reg   call-hook CHAINED at 0x557BCF6E (the RegisterAbility chain; today Steadfast's cave): calls the previous cave,
        then registers 0xC6 'Smoke Screened' (ebx = registry).
  pom   jmp-hook CHAINED at 0x55784391 (TUnitHS.PlaceOnMap tail; today Sanctify's pom): for a tactical unit HS (ClassID
        0x220104) sm_sync(unit, its field owns a SMOKE HS (ClassID 0x22010F)); then -> previous (pushal/popal).
  m1    jmp-hook CHAINED at 0x557666D8 (CreateStrikeCA, melee 1; today the True-Seeing cave 0x5580F4C0): attacker ebp,
        target esi, ATK byte bl -> bl -= 3 (clamp >= 1) when smk(ebp, esi); eax/ecx/edx preserved (eax = the class
        pointer, dl = 1 for the replayed strike constructor) -> previous.
  m2    jmp-hook CHAINED at 0x55767C89 (TMeleeRound.CalculateStrikes, melee 2; today 0x5580F520): attacker esi, target
        edi, signed modifier dword [ebx] -> [ebx] -= 3 when smk(esi, edi) -> previous.
  rg    jmp-hook CHAINED at 0x5576EB1E (CreateRangedAttackCA; today 0x5580F580): attacker esi, target [ebp-4], ranged
        ability ebx, ATK byte [esp] (just pushed) -> tier penalty (0 / -2 / -3, clamp >= 1) when smk(esi, [ebp-4])
        -> previous.
  smk(eax = attacker, edx = target) -> al = 1 when: both set, !GAE(attacker, 0x29 True Seeing), !GAE(target, 0x36
        Invisibility - the cave behind us handles that case), and GAE(attacker, 0xC6) or GAE(target, 0xC6).  GAE =
        the combat object's VMT+0xA8 (the True-Seeing caves' own call).  Preserves ebx/ecx/edx/esi/edi.
--revert restores every chain point to the stored previous target (refuses if another patch chained in front of us).
v2 2026-10-17 (user: "when smoke screened, I want a unit's displayed attack (unit panel) to drop if it doesn't have True
  Seeing. same with ranged attack ATK shown in the preview panel. like Crosswind. and make sure ATK never goes below 1"):
  the penalty MOVED from the three strike sites into the attack GETTERS, so the unit panel, the ranged preview and the
  strikes all use the same number:
    ga   5-byte ENTRY hook TUnit.GetAttack 0x557829EC (VMT+0xC0; CU+0x6C = the combat melee attack calls it)
    ha   5-byte ENTRY hook THero.GetAttack 0x55788360 (both hero VMTs)
         -> run the original getter (displaced prologue, jump back), then pen() on its byte result
    ra1/ra2  CHAINED in front of Crosswind's caves on GetAttackRA's two epilogues 0x5576E68E / 0x5576E6A5 (ranged ATK:
         unit panel + preview + the shot; GetAttackRA never adds TUnit.GetAttack, so no double count) - Crosswind's
         placed-unit guard [esi+4], pen(), then Crosswind's -2 + the vanilla epilogue.
    pen(eax = TUnit, bl = attack): own 0xC6 bit (TUnit.HasAbility 0x5577F618 base bit test - safe on any unit, the
         Steadfast-v3 lesson) and NO True Seeing (unit VMT+0x88, items included) -> bl = max(1, bl - 3).
  A flat -3 for melee AND ranged (the getters cannot see the shot's range, so v1's -2/-3 range tiers are gone), and
  only units STANDING in the smoke are penalised (v1 also penalised attacking INTO the smoke - a target-dependent
  penalty no panel can show).  m1 / m2 / rg stay hooked as pure `jmp previous` pass-throughs (chain layout and the
  exact revert unchanged).  --apply on a live v1 upgrades in place (backup .bak_smokescreen2 = the v1 state);
  --revert from v2 restores the getters' vanilla bytes, Crosswind's ra targets and every v1 chain point (= the v1
  script's own revert, byte-identical); --revert on a live v1 undoes exactly what v1 hooked.
Backup <game>\backup\AoWEPACK.dll.bak_smokescreen.  Dry-run default; --apply (rewrites an older build in place) /
--revert / --dis / --dll <copy>.
Also needed: Ability.pfs record 208 (patch_smokescreen_ability_pfs_v1.py), ceilings LADDER += 0xC6 (bound -> 0xC7) in
patch_aowx_banner_ceilings_v1.py + patch_tcablist_ceiling_v1.py, pipeline 225 + ALIAS 225 -> 0x7C, then
patch_tc_smokescreen_v1.py.
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
from patch_earthlife_blessings_v1 import asm_delta, reloc_set, hook_bytes

DEFAULT_DLL = game_file("AoWEPACK.dll")
BAK_SUFFIX = ".bak_smokescreen"
BASE, CODE_V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x5587A800, 0x5587B000
HDR, EXP_SYNC = 0x20, 0x5587A820
SPELL_ID, AB_SMOKE, NAME = 225, 0xC6, b"Smoke Screened"
FIELD_CLASSID, UNITHS_CLASSID = 0x22010F, 0x220104
AB_TRUESEEING, AB_INVIS = 0x29, 0x36
REGABIL, LSTRASG = 0x55750238, 0x55701150
DUR_VMT, DUR_CREATE, HPB_WORD20 = 0x5571DD68, 0x55764CD4, 0x557BB808
REGISTRY, GETABIL, REMOVEABIL = 0x558E92E8, 0x557501C0, 0x5577F6EC
REG_SITE = 0x557BCF6E
CALL_CHAIN = {"reg": REG_SITE}
JMP_CHAIN = {"pom": 0x55784391, "m1": 0x557666D8, "m2": 0x55767C89, "rg": 0x5576EB1E,
             "ra1": 0x5576E68E, "ra2": 0x5576E6A5}                     # v2: GetAttackRA's two epilogues (Crosswind's ra caves)
PREV_OFF = {"reg": 0, "pom": 4, "m1": 8, "m2": 12, "rg": 16, "ra1": 20, "ra2": 24}
# v2: 5-byte ENTRY hooks on the two strategic attack getters (vanilla bytes kept here for the exact revert)
ENTRY = {"ga": (0x557829EC, bytes.fromhex("538bd88bc3")),              # TUnit.GetAttack (VMT+0xC0): push ebx / mov ebx,eax / mov eax,ebx
         "ha": (0x55788360, bytes.fromhex("5356575551"))}             # THero.GetAttack (VMT+0xC0): push ebx/esi/edi/ebp/ecx
HASAB = 0x5577F618                                                    # TUnit.HasAbility base bit test (eax unit, edx id) - safe on any unit
SMOKE_PEN = 3                                                         # v2: flat -3 melee AND ranged, ATK floor 1

from keystone import Ks, KS_ARCH_X86, KS_MODE_32
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def build(d, prev):
    out = bytearray(HDR + 8); where = {}
    for k, off in PREV_OFF.items(): struct.pack_into("<I", out, off, prev[k])
    def place(name, src):
        while len(out) % 16: out.append(0)
        va = ZONE + len(out); where[name] = va; out.extend(asm_delta(src, va))
    while len(out) % 4: out.append(0)
    out += struct.pack("<ii", -1, len(NAME)); where["name"] = ZONE + len(out); out += NAME + b"\0"
    w20 = struct.unpack_from("<H", d, HPB_WORD20 - CODE_V2F)[0]
    place("reg", """
        call %(prev)#x
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
        pop esi
        ret
    """ % {"prev": prev["reg"], "reg": REGABIL, "vmt": DUR_VMT, "create": DUR_CREATE, "aid": AB_SMOKE, "w20": w20,
           "name": where["name"], "lstrasg": LSTRASG})
    # sm_sync(eax = TUnit, dl = on): grant / remove 0xC6; all registers but eax preserved
    place("sync", """
        push ebx
        push ecx
        push edx
        push esi
        push edi
        mov esi, eax
        mov bl, dl
        test esi, esi
        jz s_out
        test bl, bl
        jz s_off
        mov eax, esi
        mov edx, %(ab)d
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x14c]
        test al, al
        jnz s_out
        call $D
        pop edi
        sub edi, $D
        mov eax, dword ptr [edi + %(registry)#x]
        mov eax, dword ptr [eax]
        mov eax, dword ptr [eax + 0x80]
        mov edx, %(ab)d
        call %(getabil)#x
        test eax, eax
        jz s_out
        mov edx, esi
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0xd0]
        jmp s_changed
    s_off:
        mov eax, esi
        mov edx, %(ab)d
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x14c]
        test al, al
        jz s_out
        mov eax, esi
        mov edx, %(ab)d
        call %(removeabil)#x
    s_changed:
        mov eax, esi
        mov edx, dword ptr [eax]
        call dword ptr [edx + 0x90]
    s_out:
        pop edi
        pop esi
        pop edx
        pop ecx
        pop ebx
        ret
    """ % {"ab": AB_SMOKE, "registry": REGISTRY, "getabil": GETABIL, "removeabil": REMOVEABIL})
    # pom: TUnitHS.PlaceOnMap tail (ebx = hs; the call's args already pushed) - everything preserved
    place("pom", """
        pushal
        mov eax, ebx
        mov edx, dword ptr [eax]
        call dword ptr [edx + 0x24]
        cmp eax, %(unitcls)#x
        jne p_out
        mov eax, dword ptr [ebx + 0x1c]
        test eax, eax
        jz p_out
        mov esi, dword ptr [eax + 0x4c]
        test esi, esi
        jz p_out
        xor edi, edi
        mov eax, dword ptr [ebx + 4]
        test eax, eax
        jz p_sync
        mov edx, %(fieldcls)#x
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x80]
        test eax, eax
        setnz al
        movzx edi, al
    p_sync:
        mov eax, esi
        mov edx, edi
        call %(sync)#x
    p_out:
        popal
        jmp %(prev)#x
    """ % {"unitcls": UNITHS_CLASSID, "fieldcls": FIELD_CLASSID, "sync": where["sync"], "prev": prev["pom"]})
    # v2 2026-10-17: the strike-site penalty is GONE (m1 / m2 / rg are kept as pure pass-throughs so the chain layout and
    # the exact revert stay as v1) - the -3 now lives in the attack GETTERS, so the unit panel and the ranged preview show
    # exactly what the strikes use.
    for k in ("m1", "m2", "rg"):
        place(k, "jmp %(prev)#x" % {"prev": prev[k]})
    # pen(eax = TUnit, bl = attack) -> bl -= 3 (floor 1) when the unit is Smoke Screened (own 0xC6 bit, the safe base bit
    # test first) and has no True Seeing (0x29, the unit's full VMT+0x88 test - items included); everything else kept
    place("pen", """
        push eax
        push ecx
        push edx
        push esi
        mov esi, eax
        test esi, esi
        jz n_out
        mov edx, %(ab)d
        call %(hasab)#x
        test al, al
        jz n_out
        mov eax, esi
        mov edx, %(ts)d
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x88]
        test al, al
        jnz n_out
        movsx eax, bl
        sub eax, %(pen)d
        cmp eax, 1
        jge n_set
        mov eax, 1
    n_set:
        mov bl, al
    n_out:
        pop esi
        pop edx
        pop ecx
        pop eax
        ret
    """ % {"ab": AB_SMOKE, "ts": AB_TRUESEEING, "hasab": HASAB, "pen": SMOKE_PEN})
    # ga / ha: entry hooks - run the original getter (displaced prologue + jump back), then pen() on its byte result
    for k, body in (("ga", "push ebx\nmov ebx, eax\nmov eax, ebx"),
                    ("ha", "push ebx\npush esi\npush edi\npush ebp\npush ecx")):
        va, orig = ENTRY[k]
        place(k, """
        push eax
        call body
        pop edx
        push ebx
        mov ebx, eax
        mov eax, edx
        call %(pen)#x
        mov eax, ebx
        pop ebx
        ret
    body:
        %(body)s
        jmp %(cont)#x
    """ % {"pen": where["pen"], "body": body, "cont": va + 5})
    # ra1 / ra2: GetAttackRA epilogues (esi = attacker TUnit, bl = the ranged attack) - Crosswind's guard (placed unit:
    # [esi+4] set; GetAttackRA also runs for unplaced prototypes), pen(), then the previous cave (Crosswind's -2 + the
    # vanilla epilogue `mov eax,ebx / pop esi / pop ebx / ret`)
    for k in ("ra1", "ra2"):
        place(k, """
        test esi, esi
        jz r_prev
        cmp dword ptr [esi + 4], 0
        je r_prev
        push eax
        mov eax, esi
        call %(pen)#x
        pop eax
    r_prev:
        jmp %(prev)#x
    """ % {"pen": where["pen"], "prev": prev[k]})
    out[HDR:HDR + 5] = b"\xe9" + struct.pack("<i", where["sync"] - (EXP_SYNC + 5))
    zone = bytes(out)
    assert ZONE + len(zone) <= ZONE_END, hex(ZONE + len(zone))
    return zone, where


def jmp_target(b, va):
    return va + 5 + struct.unpack_from("<i", b, 1)[0] if b[0] == 0xE9 else None


def call_target(b, va):
    return va + 5 + struct.unpack_from("<i", b, 1)[0] if b[0] == 0xE8 else None


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--dll", default=DEFAULT_DLL)
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true"); ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read())
    rd = lambda va, n: bytes(d[va - CODE_V2F:va - CODE_V2F + n])
    inzone = lambda t: t is not None and ZONE <= t < ZONE_END
    zl = rd(ZONE, ZONE_END - ZONE)
    state, prev = {}, {}
    for k, va in JMP_CHAIN.items():
        t = jmp_target(rd(va, 5), va)
        if t is None: state[k] = "UNEXPECTED(%s)" % rd(va, 6).hex(); prev[k] = 0
        elif inzone(t): state[k] = "ours"; prev[k] = struct.unpack_from("<I", zl, PREV_OFF[k])[0]
        else: state[k] = "chain"; prev[k] = t
    for k, va in CALL_CHAIN.items():
        t = call_target(rd(va, 5), va)
        if t is None: state[k] = "UNEXPECTED(%s)" % rd(va, 5).hex(); prev[k] = 0
        elif inzone(t): state[k] = "ours"; prev[k] = struct.unpack_from("<I", zl, PREV_OFF[k])[0]
        elif t == REGABIL: state[k] = "UNEXPECTED(vanilla - apply patch_secondwind_v1.py first)"; prev[k] = 0
        else: state[k] = "chain"; prev[k] = t
    for k, (va, orig) in ENTRY.items():                                 # v2 entry hooks: vanilla bytes / our jmp
        b = rd(va, 5); t = jmp_target(b, va)
        state[k] = "ours" if inzone(t) else "free" if b == orig else "OTHER(%s)" % b.hex()
    zone, where = build(bytes(d), prev)
    rl = reloc_set(bytes(d))
    sites = list(JMP_CHAIN.values()) + list(CALL_CHAIN.values()) + [va for va, _o in ENTRY.values()]
    bad = [hex(r) for r in rl if ZONE - 3 <= r < ZONE_END or any(va - 3 <= r < va + 5 for va in sites)]
    zstate = "zero" if not any(zl) else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) \
        else "ours(old)" if any(s == "ours" for s in state.values()) else "DIFFERS"
    print("AoWEPACK smokescreen: state %s | prev %s | zone %s (%d B: %s) | relocs in zone/sites %s" % (
        state, {k: hex(v) for k, v in prev.items()}, zstate, len(zone),
        ", ".join("%s=%#x" % (k, v) for k, v in where.items() if k != "name"), bad or "none"))
    print("export: sm_sync %#x -> %#x" % (EXP_SYNC, where["sync"]))
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        cav = sorted((v, k) for k, v in where.items() if k != "name") + [(ZONE + len(zone), None)]
        for (va, nm), (nx, _n) in zip(cav, cav[1:]):
            print("  [%s]" % nm)
            for i in md.disasm(zone[va - ZONE:nx - ZONE], va):
                if i.mnemonic == "add" and i.op_str == "byte ptr [eax], al": break
                print("   %08X  %-18s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad or any(s.startswith(("UNEXPECTED", "OTHER")) for s in state.values()) or zstate == "DIFFERS" \
            or any(p == 0 or inzone(p) for p in prev.values()):
        print("ABORT"); return 1
    if a.revert:
        v1only = all(state[k] == "ours" for k in PREV_OFF if k not in ("ra1", "ra2")) and all(state[k] != "ours" for k in ("ra1", "ra2", "ga", "ha"))
        if v1only:                                                       # an applied v1: undo exactly what v1 hooked
            for k, va in JMP_CHAIN.items():
                if k not in ("ra1", "ra2"): d[va - CODE_V2F:va - CODE_V2F + 5] = hook_bytes("jmp", va, prev[k], 5)
            for k, va in CALL_CHAIN.items(): d[va - CODE_V2F:va - CODE_V2F + 5] = hook_bytes("call", va, prev[k], 5)
            d[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
            with open(a.dll, "r+b") as f: f.write(bytes(d))
            print("reverted v1 build (chain points back, zone zeroed)"); return 0
        if not all(s == "ours" for s in state.values()):
            print("ABORT revert: not (fully) applied, or another patch is chained in front: %s" % state); return 1
        for k, va in JMP_CHAIN.items(): d[va - CODE_V2F:va - CODE_V2F + 5] = hook_bytes("jmp", va, prev[k], 5)
        for k, va in CALL_CHAIN.items(): d[va - CODE_V2F:va - CODE_V2F + 5] = hook_bytes("call", va, prev[k], 5)
        for k, (va, orig) in ENTRY.items(): d[va - CODE_V2F:va - CODE_V2F + 5] = orig
        d[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
        with open(a.dll, "r+b") as f: f.write(bytes(d))
        print("reverted (chain points back to %s, getters vanilla, zone zeroed)" % {k: hex(v) for k, v in prev.items()}); return 0
    if all(s == "ours" for s in state.values()) and zstate == "ours":
        print("already applied"); return 0
    if zstate == "ours(old)": print("older build of this patch detected -> rewriting the zone + every hook in place")
    d[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE); d[ZONE - CODE_V2F:ZONE - CODE_V2F + len(zone)] = zone
    for k, va in JMP_CHAIN.items(): d[va - CODE_V2F:va - CODE_V2F + 5] = hook_bytes("jmp", va, where[k], 5)
    for k, va in CALL_CHAIN.items(): d[va - CODE_V2F:va - CODE_V2F + 5] = hook_bytes("call", va, where[k], 5)
    for k, (va, orig) in ENTRY.items(): d[va - CODE_V2F:va - CODE_V2F + 5] = hook_bytes("jmp", va, where[k], 5)
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(a.dll, BAK_SUFFIX + ("2" if zstate == "ours(old)" else ""))   # v2 upgrade: .bak_smokescreen2 = the v1 state
    if a.dll == DEFAULT_DLL and not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    with open(a.dll, "r+b") as f: f.write(bytes(d))
    assert open(a.dll, "rb").read() == bytes(d); print("Written and verified"); return 0


if __name__ == "__main__":
    sys.exit(main())
