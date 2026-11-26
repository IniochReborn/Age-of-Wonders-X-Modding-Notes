#!/usr/bin/env python3
r"""
ROT AWAY (spell 333, Earth/Death sphere pair 13, tier 2) + the shared 7-hex hail AoE plumbing for 333 and 335
(Thousand Threads) - 2026-10-14.  AoWEPACK.dll + AoWTCPCK.dll.

Spec (user): combat spell, long range, small AOE; 7 ATK / 2 DMG, Physical + Poison; +50 % damage against MACHINES
(except Undead); inflicts ROT on machines only (the unit may lose 1 HP per turn for 3 turns).

Spell objects = GREAT HAIL clones (hail class 0x0A, like Hellfire 354) registered by patch_dual_sphere_spells_v1.py
(donor TGreatHail, pfs 126, tc_type 0x0A; pokes ATK/DMG/types 0x90 for 333).  Alias entries (patch_tc_spell_alias_v1.py,
Hellfire precedent): ALIAS[333] = ALIAS[335] = 0x74 and SITE_KEEP[0x40F0E3] += {333, 335}.

RE (live DLLs):
  * TCAbRangedTE phase 0: every class branch stores the strike count [te+0x28] and converges at 0x40B630
    (`mov eax,[ebp-4] / mov al,[eax+0x24]`); Great Hail's count is 0x15 (replayed by the Hellfire portal cave 0x43C503,
    which resumes at 0x40B630).  NextStrike's hail case picks HN = HailPattern[[te+0x34] mod 7] (pattern 0x4671FC =
    6,0,1,3,4,5,2,...; the mod is 7 for any id but Ooze, p5 cave 0x43CA00 replays `sub eax,0x7C` on the RAW id) ->
    7 strikes = the 7 hexes HN 0..6 exactly once.  The Great Hail branch (0x40E372; the oilspring tgt cave 0x40E35D
    only diverts 372/388/389) stores the unit standing on the STORED pattern hex in [fx+0x2C] -> at the landing a
    unit hex gets the direct CreateCA (0x40C39B) and skips the class switch; an EMPTY hex sends map msg 0x31006 to the
    field at HPtoHX(last path point) = the JITTERED pixel (0x40C5B1..0x40C604) -> jitter could spill onto a
    neighbouring unit's hex (= a second hit).
  * TDamageType: Fire 0x01, Cold 0x02, Lightning 0x04, Magic 0x08, Poison 0x10, Death 0x20, Holy 0x40, Physical 0x80,
    Wall 0x100 (typeinfo TDamageType).  TUnitType (TUnit VMT+0x114 = [[u+0x40]+0x30]): 0 Humanoid, 1 Creature,
    2 Machine.  Undead (Turn Undead CanTouchUnit 0x5576ADC4): TUnit VMT+0xA4 race == 0x0B or VMT+0x148
    GetAbilityEnabled(0x81).
  * Hit creation TCombatSpell.CreateCA 0x557F72C0 (TGreatHail/TVaporize VMT +0x78; ebx = spell, edi = target
    TCombatUnit): pushes ATK, DMG (0x557F72E8 = Repent's jmp cave, resumes at 0x557F72F0 with DMG on [esp]), types,
    then TCombatSpellCA.Setup.  The CA executes in 0x557F6A20 (ebx = CA, esi = context; call TDamageCA.Execute at
    0x557F6A2A = Blood Boil's EX hook), then `cmp [ebx+0x1C],0 / je 0x557F6A69` at 0x557F6A2F.
  * TDurationAbility (VMT 0x5571DD68, Create 0x55764CD4): Expand (VMT+0xD0 0x55765054) makes the record (+0xC days =
    VMT+0x110 = 3); NewDay (VMT+0xAC 0x55764D30; eax abil, edx owner, cl player) runs for EVERY unit on EVERY player's
    NewTurn broadcast 0x20020002 (TAbilityOwner.NewDay 0x5574FE14, player = [msg+0x18]); it only counts down when
    rec+0xD == that player and removes the ability (owner VMT+0x98) at 0.  Mode [abil+0x28] 1 = days.

Hooks:
  AoWTCPCK
    cnt  0x40B630 (6 B, call): replay; id in AOE_IDS -> [te+0x28] := 7.
    ctr  0x40E317 (6 B, call): id in AOE_IDS -> landing offsets [ebp-0x2C] / [ebp-0x30] := 16 (= the hex centre, the
         Implosion sc1/sc2 value) before the replayed `mov ecx,[ebp-0x34] / add ecx,[ebp-0x2C]` (flags survive ret for
         the following jno).  Repent's 'steps' cave resumes at 0x40E317 -> chains through this naturally.
  AoWEPACK
    reg  0x557BCD98 (5 B call RegisterAbility in the vanilla master loop, ebx = control): replay, then register ability
         0xB5 'Rot' = a plain TDurationAbility, mode 1 (days, 3), [+0x24] 4 and [+0x20] word as Oil Spring's 0xB2.
    dmg  0x557F72F0 (7 B, jmp): spell 333 and target IsClass TCombatUnit with a TUnit that is a Machine and NOT undead
         -> the pushed DMG byte [esp] x1.5 (2 -> 3; dice count before the roll -> deterministic, MP-safe).  Also runs
         for the 0x31006 handler's CreateCA (same function).
    rot  0x557F6A2F (6 B, jmp): after the CA executed: spell 333, target alive (CU VMT+0x88 > 0) and a Machine ->
         Expand Rot 0xB5 on the TUnit ([cu+0x4C]); a NEW record gets rec+0xD = 0xFF (latch); TUnit VMT+0x90 Changed.
    nd   0x55764D30 (7 B, jmp): TDurationAbility.NewDay for ability 0xB5: latch rec+0xD := the first player whose
         NewTurn arrives (so the 3 days count from then); on a counting day (rec+0xC > 0, rec+0xD == player) roll
         TAoWHSMap.Random(map, 2) (synced) and on 0 the unit loses 1 HP (never below 1: TUnit VMT+0xE0 / +0xE4
         SetHitPoints, +0x90 Changed); then the vanilla NewDay counts down / removes.
Undead machines get no +50 % but DO get Rot (spec: "machines only").
v4 2026-10-14 (Earth/Air): the TCPCK plumbing is a per-spell table - STRIKES {333: 7, 335: 7, 366 Gravity Well: 7,
  365 Hurl Boulder: 1}; `ctr` centres the landing for all of them; new `hn0` call-hook at 0x40E29B (7 B, vanilla
  `mov eax,[ebp-4] / movzx eax,word [eax+0x20]`, no relocs; the only branch into it is repent's 'pat' cave jmp to
  0x40E29B = our call, so both chain) forces HN (ecx) := 0 for HN0_IDS (365) - Great Hail's pattern[0] is HN 6, a
  neighbour.  Gravity Well's own effects are not in this script.
v2 2026-10-14 (user: Rot applied but stayed 3/3 days forever, no damage) - ROOT CAUSE: TAoWHSMap.Random 0x5577827C RAISES
  (0x55701B7C) unless its guard 0x55775608 passes ([map+0x234] / [[map+0x23C]+4]+0x48 / [map+0x3C]&2) or [map+0x3C]&8;
  during the NewTurn broadcast 0x20020002 that dispatches TDurationAbility.NewDay none holds -> the nd cave threw
  BEFORE the vanilla countdown ran -> Rot's NewDay aborted every turn (no countdown, no HP loss).  Fix: the roll is a
  deterministic hash of synced state (HP, days left, owner player, race byte [[u+0x40]+0x20]) - identical on every
  peer, never throws, ~50 %; and rec+0xD := the owner's player byte [unit+0x24] (the byte TUnit.NewTurn 0x55780D4C
  compares with the message's [msg+0x18]) on the grant and on every NewDay, so the vanilla code counts 3 -> 0 on the
  OWNER's 3 turns and removes Rot (owner VMT+0x98).  NewDay reaches units via TUnit's message handler 0x55781238 ->
  inherited TAbilityOwner handler 0x5574FF10 -> TAbilityOwner.NewDay 0x5574FE14 (per set bit, cl = [msg+0x18]).
  Record streaming (TDurationAbilityData.ReadWrite 0x55764C84: +0xC tag 0xB days, +0xE id, +0xD tag 0xD player,
  +0x10 tag 0xE) copies +0xD, so copies keep it.

v3 2026-10-14 (user: v2 still stayed 3/3 days, no damage; NEW DESIGN 'make it similar to BURNING (10 ATK / 1 DMG) except
  PHYSICAL ... combat only like burning'): the day-based Rot is GONE.
  * Vanilla Burning = ability 0x7F, class TBurningAbility (cell 0x557B615C, Create 0x557BA324, VMT 0x557B619C = a
    TDurationAbility with mode [+0x28] 2 = combat rounds, duration VMT+0x110 = 3, and its own per-round VMT+0xF8
    0x557BA3D4: count the record down (rec+0xC; rec+0xD = the round owner), remove at 0, then roll
    0x55725D98(10 - strategic unit VMT+0xCC GetResistance) and on a hit the combat unit takes 1 (VMT+0x124(1)).
    Applied by ExecuteDamageEffectsRole through TUnit VMT+0x94 ExpandAbility(0x7F) (0x55781F70); dropped at combat
    end by TDurationAbility.CombatDone (modes 2/3).
  * Rot 0xB5 = a SECOND TBurningAbility instance (reg cave: Burning's Create, then id 0xB5 + name 'Rot') -> identical
    countdown, combat-only lifetime and 1-damage tick; hook `def` 0x557BA459 (`call [edx+0xCC]` in that tick, 6 B ->
    call cave + nop): for 0xB5 the roll uses VMT+0xC4 GetDefense instead = physical (10 ATK vs defence, 1 DMG).
    Rot Away's `rot` cave now grants it exactly like Burning: TUnit VMT+0x94 ExpandAbility(0xB5) on a living machine.
  * The v1/v2 `nd` hook on TDurationAbility.NewDay 0x55764D30 and its roll are RETIRED: --apply restores its vanilla
    bytes (5356578bd98bf2); --revert too.
  * Why v2 still showed 3/3: Rot was a TDurationAbility in mode 1 (days); its NewDay countdown runs from the NewTurn
    broadcast, which (unverified live) evidently never reached / matched the rotting unit's record - moot now.
Zones: AoWEPACK 0x5584A000..0x5584D000, AoWTCPCK 0x43E900..0x43EB00 (verified zero / reloc-free; 0x43E700..0x43E900 = patch_bloodboil_v1.py's declared zone).  PIC via call/pop
delta (both DLLs rebase).  Thunks import-table checked: LStrAsg 0x55701150, IsClass 0x557010C0.  Every site's live
bytes were vanilla and no other script references them.  Dry-run default; --apply (also upgrades an older build of
this patch in place) / --revert / --dis.  Backups .bak_rotaway.
TODO elsewhere (not this script): Ability.pfs record for 0xB5 'Rot' + re-run patch_aowx_banner_ceilings_v1.py /
patch_tcablist_ceiling_v1.py (append 0xB5 to their LADDER) so the ability shows in the unit banner / tactical list.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

SPELL_ID, LAND_CENTRE = 333, 16
STRIKES = {333: 7, 335: 7, 366: 7, 365: 1, 309: 7, 208: 7, 218: 7, 226: 6}     # v4: per-spell hail strike count (Rot Away, Thousand Threads, Gravity Well, Hurl Boulder)
HN0_IDS = (365,)                                # v4: single-strike spells whose strike lands on the TARGET hex (HN 0)
AOE_IDS = tuple(STRIKES)
ROT_ID, ROT_NAME = 0xB5, b"Rot"
ks = Ks(KS_ARCH_X86, KS_MODE_32)
ANCHOR = bytes.fromhex("e8000000005d81edffffff7f")      # call $D / pop ebp / sub ebp, $D


def asm_pic(src, va):
    s1 = src.replace("call $D", ".byte 0xe8, 0, 0, 0, 0").replace("sub ebp, $D", "sub ebp, 0x7fffffff")
    b = bytearray(ks.asm(s1, va)[0]); k = 0
    while True:
        k = b.find(ANCHOR, k)
        if k < 0: break
        struct.pack_into("<I", b, k + 8, va + k + 5); k += len(ANCHOR)
    return bytes(b)


# ------------------------------------------------------------------------------------------------ AoWEPACK
REGABIL, DUR_VMT, DUR_CREATE, LSTRASG, HPB_WORD20 = 0x55750238, 0x5571DD68, 0x55764CD4, 0x55701150, 0x557BB808
FINDID, GETABILITY, GETABDATA, ISCLASS, RANDOM = 0x55728C68, 0x557501C0, 0x5574F1C4, 0x557010C0, 0x5577827C
TCU_CLASSREF, REGISTRY, MAP_GLOBAL = 0x55715A54, 0x558E92E8, 0x558FA040
BURN_CELL, BURN_CREATE = 0x557B615C, 0x557BA324           # TBurningAbility class cell / Create (VMT 0x557B619C)
EXPAND_BY_ID_SLOT = 0x94                                    # TUnit VMT+0x94 = TAbilityOwner.ExpandAbility(id) 0x5574F5B4
EP = dict(name="AoWEPACK", dll=game_file("AoWEPACK.dll"), base=0x55700000, v2f=0x55700C00, zone=(0x5584A000, 0x5584D000),
          sites=[("reg", 0x557BCD98, bytes.fromhex("e89b34f9ff"), "call"),
                 ("dmg", 0x557F72F0, bytes.fromhex("508a433c508bcf"), "jmp"),
                 ("rot", 0x557F6A2F, bytes.fromhex("837b1c007434"), "jmp"),
                 ("def", 0x557BA459, bytes.fromhex("ff92cc000000"), "call")],
          retired=[("nd", 0x55764D30, bytes.fromhex("5356578bd98bf2"))])     # v1/v2's day-based NewDay hook: restored to vanilla


def ep_build(d):
    zone = EP["zone"][0]
    out = bytearray(); where = {}
    out += struct.pack("<ii", -1, len(ROT_NAME)); where["name"] = zone + len(out); out += ROT_NAME + b"\0"
    def place(name, src):
        while len(out) % 16: out.append(0)
        va = zone + len(out); where[name] = va; out.extend(asm_pic(src, va))
    # reg: replay the vanilla RegisterAbility, then register 0xB5 'Rot' = a SECOND TBurningAbility instance (its Create
    # sets mode [+0x28] 2 = combat rounds, [+0x24] 1, word +0x20; duration VMT+0x110 = 3) with id 0xB5 + name 'Rot'
    place("reg", """
        call %(reg)#x
        push ebp
        call $D
        pop ebp
        sub ebp, $D
        mov eax, [ebp + %(cell)#x]
        xor ecx, ecx
        mov dl, 1
        call %(create)#x
        mov dword ptr [eax + 0xc], %(rot)d
        push eax
        lea edx, [ebp + %(name)#x]
        add eax, 8
        call %(lstrasg)#x
        pop edx
        mov eax, ebx
        call %(reg)#x
        pop ebp
        ret
    """ % {"reg": REGABIL, "cell": BURN_CELL, "create": BURN_CREATE, "rot": ROT_ID, "name": where["name"], "lstrasg": LSTRASG})
    # dmg: ebx = spell, edi = target TCombatUnit, [esp] = the pushed DMG (low byte)
    place("dmg", """
        cmp dword ptr [ebx + 0x10], %(id)d
        jne d_replay
        test edi, edi
        jz d_replay
        push eax
        push ecx
        push edx
        push ebp
        call $D
        pop ebp
        sub ebp, $D
        mov eax, edi
        mov edx, [ebp + %(tcu)#x]
        call %(isclass)#x
        pop ebp
        test al, al
        jz d_rest
        mov eax, [edi + 0x4c]
        test eax, eax
        jz d_rest
        push eax
        mov ecx, [eax]
        call dword ptr [ecx + 0x114]
        cmp al, 2
        pop eax
        jne d_rest
        push eax
        mov ecx, [eax]
        call dword ptr [ecx + 0xa4]
        cmp al, 0xb
        pop eax
        je d_rest
        mov edx, 0x81
        mov ecx, [eax]
        call dword ptr [ecx + 0x148]
        test al, al
        jnz d_rest
        movzx eax, byte ptr [esp + 12]
        mov ecx, eax
        shr ecx, 1
        add eax, ecx
        mov byte ptr [esp + 12], al
    d_rest:
        pop edx
        pop ecx
        pop eax
    d_replay:
        push eax
        mov al, byte ptr [ebx + 0x3c]
        push eax
        mov ecx, edi
        jmp %(dres)#x
    """ % {"id": SPELL_ID, "tcu": TCU_CLASSREF, "isclass": ISCLASS, "dres": 0x557F72F7})
    # rot: after TDamageCA.Execute (ebx = CA, esi = combat context): spell 333, target alive and a Machine ->
    # TUnit.ExpandAbility(0xB5) - exactly how ExecuteDamageEffectsRole applies Burning 0x7F (0x55781F70)
    place("rot", """
        cmp dword ptr [ebx + 0x18], %(id)d
        jne r_tail
        pushal
        mov eax, [esi + 0xc]
        mov dl, byte ptr [ebx + 0xe]
        call %(findid)#x
        test eax, eax
        jz r_out
        mov edi, eax
        mov ecx, [eax]
        call dword ptr [ecx + 0x88]
        test al, al
        jz r_out
        mov esi, [edi + 0x4c]
        test esi, esi
        jz r_out
        mov eax, esi
        mov ecx, [eax]
        call dword ptr [ecx + 0x114]
        cmp al, 2
        jne r_out
        mov eax, esi
        mov edx, %(rot)d
        mov ecx, [eax]
        call dword ptr [ecx + %(exp)#x]
    r_out:
        popal
    r_tail:
        cmp dword ptr [ebx + 0x1c], 0
        je %(skip)#x
        jmp %(res)#x
    """ % {"id": SPELL_ID, "findid": FINDID, "rot": ROT_ID, "exp": EXPAND_BY_ID_SLOT, "skip": 0x557F6A69, "res": 0x557F6A35})
    # def: TBurningAbility per-round tick (VMT+0xF8 0x557BA3D4; edi = ability, eax = strategic unit, edx = its VMT):
    # vanilla rolls 10 - Resistance (VMT+0xCC); Rot (0xB5) = PHYSICAL -> 10 - Defense (VMT+0xC4).  Tail-call keeps the
    # vanilla return path (the callee returns to 0x557BA45F).
    place("def", """
        cmp dword ptr [edi + 0xc], %(rot)d
        je f_def
        jmp dword ptr [edx + 0xcc]
    f_def:
        jmp dword ptr [edx + 0xc4]
    """ % {"rot": ROT_ID})
    return bytes(out), where


# ------------------------------------------------------------------------------------------------ AoWTCPCK
TP = dict(name="AoWTCPCK", dll=game_file("AoWTCPCK.dll"), base=0x400000, v2f=0x400C00, zone=(0x43E900, 0x43EB00),
          sites=[("cnt", 0x40B630, bytes.fromhex("8b45fc8a4024"), "call"),
                 ("ctr", 0x40E317, bytes.fromhex("8b4dcc034dd4"), "call"),
                 ("hn0", 0x40E29B, bytes.fromhex("8b45fc0fb74020"), "call")])


def tp_build(d):
    zone = TP["zone"][0]; out = bytearray(); where = {}
    def place(name, src):
        while len(out) % 16: out.append(0)
        va = zone + len(out); where[name] = va; out.extend(bytes(ks.asm(src, va)[0]))
    def ids(lst, hit):
        return "".join("        cmp dword ptr [eax + 0x18], %d\n        je %s\n" % (i, hit) for i in lst)
    groups = {}
    for i, n in STRIKES.items(): groups.setdefault(n, []).append(i)
    sets = "".join(ids(lst, "c_%d" % n) for n, lst in sorted(groups.items()))
    tails = "".join("    c_%d:\n        mov dword ptr [eax + 0x28], %d\n        jmp c_go\n" % (n, n) for n in sorted(groups))
    place("cnt", """
        mov eax, [ebp - 4]
""" + sets + """
        jmp c_go
""" + tails + """
    c_go:
        mov al, byte ptr [eax + 0x24]
        ret
    """)
    place("ctr", ("""
        push eax
        mov eax, [ebp - 4]
""" + ids(AOE_IDS, "t_set") + """
        jmp t_go
    t_set:
        mov dword ptr [ebp - 0x2c], %(c)d
        mov dword ptr [ebp - 0x30], %(c)d
    t_go:
        pop eax
        mov ecx, [ebp - 0x34]
        add ecx, [ebp - 0x2c]
        ret
    """) % {"c": LAND_CENTRE})
    # hn0 (v4): 0x40E29B = the replayed `mov eax,[ebp-4] / movzx eax,word [eax+0x20]` right after the pattern lookup
    # (ecx = HN; repent's 'pat' cave resumes here, so it chains): HN0_IDS -> ecx := 0 = the target hex itself.
    place("hn0", """
        mov eax, [ebp - 4]
""" + ids(HN0_IDS, "h_set") + """
        jmp h_go
    h_set:
        xor ecx, ecx
    h_go:
        movzx eax, word ptr [eax + 0x20]
        ret
    """)
    return bytes(out), where


# ------------------------------------------------------------------------------------------------ common
def reloc_set(d, base):
    pe = struct.unpack_from("<I", d, 0x3C)[0]; opt = struct.unpack_from("<H", d, pe + 20)[0]; nsec = struct.unpack_from("<H", d, pe + 6)[0]
    secs = [struct.unpack_from("<IIII", d, pe + 24 + opt + 40 * k + 8) for k in range(nsec)]
    rrva, rsz = struct.unpack_from("<II", d, pe + 24 + 0x88)
    def r2f(rva):
        for vs, va, rs, ro in secs:
            if va <= rva < va + max(vs, rs): return ro + rva - va
    p = r2f(rrva); end = p + rsz; out = set()
    while p < end:
        page, size = struct.unpack_from("<II", d, p)
        if size < 8: break
        for q in range(p + 8, p + size, 2):
            e = struct.unpack_from("<H", d, q)[0]
            if e >> 12 == 3: out.add(base + page + (e & 0xFFF))
        p += size
    return out


def plan(cfg, builder, dis):
    d = bytearray(open(cfg["dll"], "rb").read()); V = cfg["v2f"]; z0, z1 = cfg["zone"]
    blob, where = builder(bytes(d)); assert z0 + len(blob) <= z1, hex(z0 + len(blob))
    states, hooks = {}, {}
    for name, va, orig, kind in cfg["sites"]:
        op = b"\xe8" if kind == "call" else b"\xe9"
        hooks[name] = op + struct.pack("<i", where[name] - (va + 5)) + b"\x90" * (len(orig) - 5)
        live = bytes(d[va - V:va - V + len(orig)])
        if live == orig: states[name] = "vanilla"
        elif live == hooks[name]: states[name] = "ours"
        elif live[0] in (0xE8, 0xE9) and z0 <= va + 5 + struct.unpack_from("<i", live, 1)[0] < z1: states[name] = "ours(old)"
        else: states[name] = "OTHER"
    retired = {}
    for name, va, orig in cfg.get("retired", []):
        live = bytes(d[va - V:va - V + len(orig)])
        if live == orig: retired[name] = "vanilla"
        elif live[0] in (0xE8, 0xE9) and z0 <= va + 5 + struct.unpack_from("<i", live, 1)[0] < z1: retired[name] = "ours(old)"
        else: retired[name] = "OTHER"
        states["retired:" + name] = retired[name]
    zl = bytes(d[z0 - V:z1 - V])
    zstate = "zero" if not any(zl) else "ours" if zl[:len(blob)] == blob and not any(zl[len(blob):]) else "DIFFERS"
    rl = reloc_set(bytes(d), cfg["base"])
    bad = [hex(r) for r in rl if z0 <= r < z1 or any(va <= r < va + len(o) for _n, va, o, _k in cfg["sites"])]
    print("%s: sites %s | zone %s (%d B: %s) | relocs %s" % (cfg["name"], states, zstate, len(blob),
          ", ".join("%s=%#x" % kv for kv in where.items() if kv[0] != "name"), bad or "none"))
    if dis:
        import capstone
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(blob, z0): print("   %08X  %-18s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    return d, blob, states, hooks, zstate, bad


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true"); ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    jobs = [(EP, ep_build), (TP, tp_build)]
    plans = [(cfg,) + plan(cfg, b, a.dis) for cfg, b in jobs]
    for cfg, d, blob, states, hooks, zstate, bad in plans:
        if bad or "OTHER" in states.values(): print("ABORT (%s: relocs or a foreign hook)" % cfg["name"]); return 1
        if zstate == "DIFFERS" and not any(s.startswith("ours") for s in states.values()):
            print("ABORT (%s: zone not free)" % cfg["name"]); return 1
    outs = []
    for cfg, d, blob, states, hooks, zstate, bad in plans:
        V = cfg["v2f"]; z0, z1 = cfg["zone"]; out = bytearray(d)
        if a.revert:
            for name, va, orig, kind in cfg["sites"]: out[va - V:va - V + len(orig)] = orig
            for name, va, orig in cfg.get("retired", []): out[va - V:va - V + len(orig)] = orig
            out[z0 - V:z1 - V] = bytes(z1 - z0)
        else:
            out[z0 - V:z1 - V] = bytes(z1 - z0); out[z0 - V:z0 - V + len(blob)] = blob
            for name, va, orig, kind in cfg["sites"]: out[va - V:va - V + len(orig)] = hooks[name]
            for name, va, orig in cfg.get("retired", []): out[va - V:va - V + len(orig)] = orig
        outs.append((cfg, d, out))
    if all(o[1] == o[2] for o in outs): print("already applied" if not a.revert else "already vanilla"); return 0
    if not (a.apply or a.revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    for cfg, d, out in outs:
        if bytes(out) == bytes(d): continue
        bak = bak_path(cfg["dll"], ".bak_rotaway")
        if not os.path.exists(bak): shutil.copy2(cfg["dll"], bak); print("backup ->", bak)
        with open(cfg["dll"], "r+b") as f: f.write(bytes(out))
        assert open(cfg["dll"], "rb").read() == bytes(out); print("%s: %s and verified" % (cfg["name"], "reverted" if a.revert else "written"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
