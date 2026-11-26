"""
CROSSWIND (spell 213, Air tier 2; 2026-10-16) - AoWEPACK.dll only.
User spec: combat spell, infinite range, research 80 / cost 5: enemy units suffer -2 ATK for RANGED attacks for 3 turns.

Spell = a THighPrayer clone (pipeline: donor THighPrayer, tc_type 0x25 = a vanilla INSTANT class - SetSpell 0x4233B0
fires it at once, no targeting step; ALIAS 213 -> 0x66 like Heavenly Chorus 308).  The TC side creates one
TTacticalCombatHighPrayerCA per FRIENDLY unit; for 213 every one of those CAs runs our `hx` cave instead of the High
Prayer body (no heal, no 0x64 blessing), which walks the combat's object list and grants 0xC2 to every living ENEMY
combat unit that lacks it (idempotent, so N friendly CAs = one effect).

0xC2 'Crosswind' = a THIRD TBurningAbility instance (Rot 0xB5's recipe, patch_rotaway_v1.py): its Create gives mode
[+0x28] 2 = combat ROUNDS, duration VMT+0x110 = 3, combat-only (TDurationAbility.CombatDone drops it), its own per-round
tick (VMT+0xF8 0x557BA3D4) counts the record down and removes it at 0.  The tick then rolls Burning's 1-damage
(10 - RES) - `tk` skips that for 0xC2 (no damage; the roll's Random is not consumed either).  No flame overlay (that
is keyed to 0x7F).  Granted with TUnit VMT+0x94 ExpandAbility (like Rot / Burning).

-2 ranged ATK: TRangedAttackAbility.GetAttackRA 0x5576E65C (esi = attacker unit, bl = the ranged attack; its entry
already jumps to the Night Vision cave 0x5580F200) returns through two identical epilogues `mov eax,ebx / pop esi /
pop ebx / ret` (0x5576E68E Marksmanship path, 0x5576E6A5 the rest) -> `ra` cave: unit valid ([esi+4] set, the Night
Vision cave's guard - GetAttackRA also runs for unplaced prototypes) and VMT+0x88(0xC2) -> bl = max(1, bl - 2) (2026-10-17 user: never below 1, e.g. underground without Night Vision).  Only
ranged attacks go through GetAttackRA (melee = TUnit.GetAttack, spells = their own ATK), and the unit panel's ranged
value shows the penalty too.

Hooks (CHAINED in front of what is there now; previous targets kept in the zone header for an exact --revert):
  reg  call-hook 0x557BCE30 (vanilla `call RegisterAbility`, ebx = control): replay, then create + register 0xC2.
  tk   call-site 0x557BA459 in TBurningAbility's round tick (Rot's `def` cave lives there): 0xC2 -> skip to the tick's
       epilogue 0x557BA49A; else the previous target.
  ra1/ra2  jmp-hooks on the two GetAttackRA epilogues (vanilla 5 B each).
  hx   TTacticalCombatHighPrayerCA Execute VMT slot 0x557F4520 (Life/Air's hx cave now).
  fh   THighPrayer VMT+0xD8 fcGetDamageValueEx (fast/auto combat scorer): 213 -> zero record = never auto-cast.
  ai   THighPrayer VMT+0xD0 tactical-AI command builder: 213 -> ret = the AI never casts it.
Zone 0x5586B800..0x5586C000 (verified zero + reloc-free; PIC: only relative jumps/calls into the image + call/pop delta
for the class ref).  Backup <game>\\backup\\AoWEPACK.dll.bak_crosswind.  Dry-run default; --apply / --revert / --dis;
--dll <scratch copy>.
Also needed: pipeline 213 (THighPrayer, tc_type 0x25), ALIAS 213 -> 0x66, Ability.pfs 204
(patch_crosswind_ability_pfs_v1.py), ceilings LADDER += 0xC2 (bound -> 0xC3).
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
from patch_earthlife_blessings_v1 import asm_delta, reloc_set, hook_bytes

DEFAULT_DLL = game_file("AoWEPACK.dll")
BAK_SUFFIX = ".bak_crosswind"
CODE_V2F = 0x55700C00
ZONE, ZONE_END = 0x5586B800, 0x5586C000
HDR = 0x20
SPELL, AB = 213, 0xC2
NAME = b"Crosswind"
REGABIL, LSTRASG, ISCLASS = 0x55750238, 0x55701150, 0x557010C0
BURN_CELL, BURN_CREATE = 0x557B615C, 0x557BA324
TCU_VMT, FINDID, CA_PARENT_EXEC = 0x55715A94, 0x55728C68, 0x557F6C84
HP_VMT = 0x557F458C
TICK_EXIT = 0x557BA49A
REG_SITE, REG_ORIG = 0x557BCE30, bytes.fromhex("e80334f9ff")
TK_SITE = 0x557BA459                                     # `call <prev>` + nop (6 B)
RA_SITES = {"ra1": 0x5576E68E, "ra2": 0x5576E6A5}
RA_ORIG = bytes.fromhex("8bc35e5bc3")
SLOT_CHAIN = {"hx": 0x557F4520, "fh": HP_VMT + 0xD8, "ai": HP_VMT + 0xD0}
PREV_OFF = {"hx": 0, "fh": 4, "ai": 8, "tk": 12}


def build(prev):
    out = bytearray(HDR); where = {}
    for k, off in PREV_OFF.items(): struct.pack_into("<I", out, off, prev[k])
    def place(name, src):
        while len(out) % 16: out.append(0)
        va = ZONE + len(out); where[name] = va; out.extend(asm_delta(src, va))
    out += struct.pack("<ii", -1, len(NAME)); where["name"] = ZONE + len(out); out += NAME + b"\0"
    # reg: replay, then a THIRD TBurningAbility instance (mode 2 combat rounds, duration 3) as 0xC2 'Crosswind'
    place("reg", """
        call %(reg)#x
        push esi
        call $D
        pop esi
        sub esi, $D
        mov eax, [esi + %(cell)#x]
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
    """ % {"reg": REGABIL, "cell": BURN_CELL, "create": BURN_CREATE, "ab": AB, "name": where["name"], "lstrasg": LSTRASG})
    # tk: in TBurningAbility's round tick (edi = the ability): Crosswind deals no damage -> straight to the epilogue
    place("tk", """
        cmp dword ptr [edi + 0xc], %(ab)d
        je tk_skip
        jmp %(prev)#x
    tk_skip:
        add esp, 4
        jmp %(exit)#x
    """ % {"ab": AB, "prev": prev["tk"], "exit": TICK_EXIT})
    # ra: GetAttackRA epilogue (esi = unit, bl = ranged ATK)
    place("ra", """
        test esi, esi
        jz ra_out
        cmp dword ptr [esi + 4], 0
        je ra_out
        mov edx, %(ab)d
        mov eax, esi
        mov ecx, [eax]
        call dword ptr [ecx + 0x88]
        test al, al
        jz ra_out
        cmp bl, 3
        jae ra_sub
        mov bl, 1
        jmp ra_out
    ra_sub:
        sub bl, 2
    ra_out:
        mov eax, ebx
        pop esi
        pop ebx
        ret
    """ % {"ab": AB})
    # hx: High Prayer CA execute (eax = CA, edx = combat context): 213 -> parent exec, then every living enemy
    # combat unit (other combat player than the caster) lacking 0xC2 gets it (ExpandAbility VMT+0x94)
    place("hx", """
        cmp dword ptr [eax + 0x18], %(sp)d
        je hx_mine
        jmp %(prev)#x
    hx_mine:
        push ebx
        push esi
        push edi
        push ebp
        mov esi, edx
        mov ebx, eax
        mov edx, esi
        mov eax, ebx
        call %(parent)#x
        xor edx, edx
        mov dl, byte ptr [ebx + 0xc]
        mov eax, [esi + 0xc]
        call %(findid)#x
        test eax, eax
        jz hx_done
        mov bl, byte ptr [eax + 0x45]
        mov eax, [esi + 0xc]
        mov eax, [eax + 0x34]
        test eax, eax
        jz hx_done
        mov esi, [eax + 8]
        test esi, esi
        jz hx_done
        xor edi, edi
    hx_loop:
        cmp edi, dword ptr [esi + 8]
        jge hx_done
        mov eax, [esi + 4]
        mov ebp, [eax + edi*4]
        test ebp, ebp
        jz hx_next
        call $D
        pop ecx
        sub ecx, $D
        lea edx, [ecx + %(tcu)#x]
        mov eax, ebp
        call %(isclass)#x
        test al, al
        jz hx_next
        test byte ptr [ebp + 0x47], 9
        jnz hx_next
        cmp byte ptr [ebp + 0x45], bl
        je hx_next
        mov eax, [ebp + 0x4c]
        test eax, eax
        jz hx_next
        push eax
        mov edx, %(ab)d
        mov ecx, [eax]
        call dword ptr [ecx + 0x88]
        test al, al
        pop eax
        jnz hx_next
        mov edx, %(ab)d
        mov ecx, [eax]
        call dword ptr [ecx + 0x94]
    hx_next:
        inc edi
        jmp hx_loop
    hx_done:
        pop ebp
        pop edi
        pop esi
        pop ebx
        ret
    """ % {"sp": SPELL, "prev": prev["hx"], "parent": CA_PARENT_EXEC, "findid": FINDID, "tcu": TCU_VMT,
           "isclass": ISCLASS, "ab": AB})
    place("fh", """
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
    """ % {"sp": SPELL, "prev": prev["fh"]})
    place("ai", """
        cmp dword ptr [eax + 0x10], %(sp)d
        je none
        jmp %(prev)#x
    none:
        ret
    """ % {"sp": SPELL, "prev": prev["ai"]})
    zone = bytes(out)
    assert ZONE + len(zone) <= ZONE_END, hex(ZONE + len(zone))
    return zone, where


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--dll", default=DEFAULT_DLL)
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true"); ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read())
    rd = lambda va, n: bytes(d[va - CODE_V2F:va - CODE_V2F + n])
    u32 = lambda va: struct.unpack_from("<I", d, va - CODE_V2F)[0]
    rel = lambda va: va + 5 + struct.unpack_from("<i", d, va - CODE_V2F + 1)[0]
    inzone = lambda t: t is not None and ZONE <= t < ZONE_END
    zl = rd(ZONE, ZONE_END - ZONE)
    hdr = lambda k: struct.unpack_from("<I", zl, PREV_OFF[k])[0]
    state, prev = {}, {}
    for k, va in SLOT_CHAIN.items():
        t = u32(va)
        if inzone(t): state[k] = "ours"; prev[k] = hdr(k)
        else: state[k] = "chain"; prev[k] = t
    tb = rd(TK_SITE, 6)
    if tb[0] == 0xE8 and tb[5] == 0x90:
        t = rel(TK_SITE)
        if inzone(t): state["tk"] = "ours"; prev["tk"] = hdr("tk")
        else: state["tk"] = "chain"; prev["tk"] = t
    else: state["tk"] = "UNEXPECTED(%s)" % tb.hex(); prev["tk"] = 0
    for k, va in RA_SITES.items():
        b = rd(va, 5)
        state[k] = "vanilla" if b == RA_ORIG else "ours" if b[0] == 0xE9 and inzone(rel(va)) else "OTHER(%s)" % b.hex()
    rb = rd(REG_SITE, 5)
    state["reg"] = "vanilla" if rb == REG_ORIG else "ours" if rb[0] == 0xE8 and inzone(rel(REG_SITE)) else "OTHER(%s)" % rb.hex()
    zone, where = build(prev)
    rl = reloc_set(bytes(d))
    bad = [hex(r) for r in rl if ZONE <= r < ZONE_END or TK_SITE <= r < TK_SITE + 6 or REG_SITE <= r < REG_SITE + 5
           or any(va <= r < va + 5 for va in RA_SITES.values())]
    noreloc = [k for k, va in SLOT_CHAIN.items() if va not in rl]
    zstate = "zero" if not any(zl) else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else \
             "ours(old)" if any(s == "ours" for s in state.values()) else "DIFFERS"
    print("state %s | prev %s | zone %s (%d B: %s) | relocs in zone/sites %s | slots without reloc %s" % (
        state, {k: hex(v) for k, v in prev.items()}, zstate, len(zone),
        ", ".join("%s=%#x" % (k, v) for k, v in where.items() if k != "name"), bad or "none", noreloc or "none"))
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        cav = sorted((v, k) for k, v in where.items() if k != "name") + [(ZONE + len(zone), None)]
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
        for k, va in SLOT_CHAIN.items(): struct.pack_into("<I", d, va - CODE_V2F, prev[k])
        d[TK_SITE - CODE_V2F:TK_SITE - CODE_V2F + 6] = hook_bytes("call", TK_SITE, prev["tk"], 6)
        for k, va in RA_SITES.items(): d[va - CODE_V2F:va - CODE_V2F + 5] = RA_ORIG
        d[REG_SITE - CODE_V2F:REG_SITE - CODE_V2F + 5] = REG_ORIG
        d[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
        with open(a.dll, "r+b") as f: f.write(bytes(d))
        print("reverted (chain points back to %s, reg/ra sites vanilla, zone zeroed)" % {k: hex(v) for k, v in prev.items()}); return 0
    if all(s == "ours" for s in state.values()) and zstate == "ours":
        print("already applied"); return 0
    if zstate == "ours(old)": print("older build of this patch detected -> rewriting the zone + every hook in place")
    d[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE); d[ZONE - CODE_V2F:ZONE - CODE_V2F + len(zone)] = zone
    for k, va in SLOT_CHAIN.items(): struct.pack_into("<I", d, va - CODE_V2F, where[k])
    d[TK_SITE - CODE_V2F:TK_SITE - CODE_V2F + 6] = hook_bytes("call", TK_SITE, where["tk"], 6)
    for k, va in RA_SITES.items(): d[va - CODE_V2F:va - CODE_V2F + 5] = hook_bytes("jmp", va, where["ra"], 5)
    d[REG_SITE - CODE_V2F:REG_SITE - CODE_V2F + 5] = hook_bytes("call", REG_SITE, where["reg"], 5)
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if os.path.abspath(a.dll) == os.path.abspath(DEFAULT_DLL):
        bak = bak_path(a.dll, BAK_SUFFIX)
        if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    with open(a.dll, "r+b") as f: f.write(bytes(d))
    assert open(a.dll, "rb").read() == bytes(d); print("Written and verified"); return 0


if __name__ == "__main__":
    sys.exit(main())
