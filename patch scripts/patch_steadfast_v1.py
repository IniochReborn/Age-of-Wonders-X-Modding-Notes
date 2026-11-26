#!/usr/bin/env python3
r"""
Steadfast (218): the Earth tier-3 combat spell - "long range, small AOE; friendly units within the AOE gain additional
defense based on remaining movement (+1 DEF if >50%, +2 DEF if full movement)" (2026-10-17).  AoWEPACK.dll only.

Registered by patch_dual_sphere_spells_v1.py as a GREAT HAIL clone (hail class 0x0A, 7 strikes = the 7-hex pattern,
ATK 0 / DMG 0, range 12) exactly like Inspiration 309 / Sanctify 208; the strike count / alias / preview plumbing lives
in patch_tc_spell_alias_v1.py + patch_rotaway_v1.py (see _steadfast_integration.txt).  A strike landing on a unit hex
creates a TCombatSpellCA (spell id at [ca+0x18]) whose execute entry is 0x557F6A20.

  reg  call-hook on `call RegisterAbility` 0x557BCF6E - CHAINED: the site's current call target (Static Shield's reg
       cave today, decoded AT APPLY TIME, kept in the zone header) is called first, then a combat-only
       TDurationAbility (VMT 0x5571DD68, Create 0x55764CD4, [+0x24]=4, [+0x28]=3, [+0x20]=the HighPrayerBlessing
       word) is created as 0xC5 'Steadfast' and registered -> GetName "Steadfast (combat only)", CombatDone removes it
       at the end of the battle.  Description = Ability.pfs record 207 (patch_steadfast_ability_pfs_v1.py).
  ix   jmp-hook 0x557F6A20 (TCombatSpellCA execute entry), chained IN FRONT of the current jmp: spell 218 -> resolve
       target ([ca+0xE]) and caster ([ca+0xD]) combat units (0x55728C68, level [ctx+0xC]); same combat side
       [cu+0x45], TUnit [cu+0x4C] not a machine (VMT+0x114 != 2), not already holding 0xC5 (VMT+0x148) ->
       ExpandAbility VMT+0x94 (0xC5).  Then always -> the previous target (the CA's normal 0-damage execute).
       Enemies on the pattern are untouched.
  def  TCombatUnit.GetDefense 0x5572549C (CU VMT+0x70; the 12-byte vanilla stub `mov eax,[eax+4c] / mov edx,[eax] /
       call [edx+0xc4] / ret` = the strategic defense) -> jmp cave: base = the same call; if the TUnit's own
       bitset (VMT+0x14C) holds 0xC5: full = CU VMT+0x94 (GetMoves), rem = [cu+0x5C] (remaining combat MP, the
       field the four full-MP ability gates compare):  rem >= full -> +2;  2*rem > full -> +1;  else +0.  The sum
       is capped at 50 (never below base).  LIVE: every hit/touch roll asks CU VMT+0x70, so the bonus follows the
       unit's MP as it moves (no stale stat cache; the ability's own VMT+0x60 stays 0).  The MP refill happens at
       the side's turn start, so a unit that held its ground keeps the +2 through the enemy's turn.
  fg   TGreatHail VMT+0xD8 fcGetDamageValueEx (fast/auto-combat scorer, already chained): spell 218 -> all-zero
       result + ret 8 = never cast in auto combat (Inspiration's recipe).
v2 2026-10-17 (user: "it doesn't apply any stat increase; stats unchanged with or without moving"): ROOT CAUSE - the
       bonus lived ONLY in TCombatUnit.GetDefense (CU VMT+0x70); every DEF the player sees (unit window, combat info)
       comes from TUnit.GetDefense 0x55782A40 / THero.GetDefense 0x557883E8 (TUnit VMT+0xC4), which never saw it.
       v2 moves the bonus INTO those two getters (5-byte entry hooks `ud` / `hd`: run the original body, then add the
       live +1/+2, cap 50) and restores the vanilla CU stub (CU+0x70 calls TUnit VMT+0xC4, so rolls still get it,
       exactly once).  The getters only have the TUnit, so the `ix` grant records (TUnit, TCombatUnit) pairs in a
       32-entry table in AoWEPACK DATA zero-fill slack TAB 0x558E9E00 (+ round-robin index @0x558E9F00; free: diag
       scripts end ~0x558E9D60, Second Wind's FM table starts 0x558E9F80); the getter looks the unit up, checks
       [cu+0x4C] == unit and the own 0xC5 bit (VMT+0x14C) and compares [cu+0x5C] with the unit's GetMoves (VMT+0xD4,
       = CU VMT+0x94).  Units without a table entry (other runtime copies) get no bonus.
v3 2026-10-17 (user: "loaded a game after using Steadfast -> crash/game lock, something about hsm"; not reproducible):
       ROOT CAUSE (code review, Windows log shows only an AppHangB1 6:37 with no dump): the v2 getter looked the TUnit up
       in the (TUnit, TCombatUnit) table FIRST and read [cu+0x4C] of the stored TCombatUnit - but the table was never
       cleared, so after the battle (and across a game LOAD, where the old world is freed - Delphi's heap decommits big
       freed spans - and new TUnits reuse old addresses) it dereferenced FREED combat units -> intermittent AV inside
       TUnit.GetDefense during the load stream ("...hsm") / later.  v3: (1) the getter tests the unit's OWN 0xC5 bit
       FIRST with the base bit test TUnit.HasAbility 0x5577F618 (bounds-checked [unit+0xC] / bitset [unit+8], safe on
       any constructed unit, no VMT) - 0xC5 is combat-only (TDurationAbility mode 3, removed in TCombatUnit.CombatDone
       0x55724B54 -> TriggerCombatDone 0x5574FEC4 while the CU is still alive), so outside a battle the table is never
       touched; (2) new 6-byte entry hook `cd` on TCombatUnit.Destroy 0x55724A6C (the destructor every combat unit -
       both VMTs 0x55715A94 / 0x5571D4BC slot -4, TCPCK subclasses via inherited - runs) zeroes every table entry whose
       CU is the one being destroyed, so a stored CU is ALWAYS alive.  Bonus can never leak outside combat.
Zone AoWEPACK 0x5586F800..0x55870000 (verified zero + reloc-free; PIC via call/pop delta - the DLL rebases).
--revert restores every previous target + the 12 vanilla GetDefense bytes and refuses when something was chained in
front of one of our sites.  ⚠ With this applied, the reg-site owner (patch_staticshield_v1.py) and every ix/fg
chainer behind us (patch_lifeair_v1.py, patch_threads_v1.py, ...) report OTHER/ABORT in their dry runs - expected chain
state: revert Steadfast first.  Backup <game>\backup\AoWEPACK.dll.bak_steadfast.  Dry-run default; --dll <copy>.
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
from patch_earthlife_blessings_v1 import asm_delta, reloc_set, hook_bytes

DEFAULT_DLL = game_file("AoWEPACK.dll")
BAK_SUFFIX = ".bak_steadfast"
BASE, CODE_V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x5586F800, 0x55870000
HDR = 0x10                                      # zone header: prev reg-call / ix jmp / fg slot targets (u32 each)
SPELL, ABIL = 218, 0xC5
DEF_CAP = 50
REG_SITE = 0x557BCF6E                           # `call RegisterAbility` (vanilla e8c532f9ff), chained call-hook
REGABIL, LSTRASG = 0x55750238, 0x55701150
DUR_VMT, DUR_CREATE = 0x5571DD68, 0x55764CD4
HPB_WORD20 = 0x557BB808
RESOLVE_UNIT = 0x55728C68
IX_SITE = 0x557F6A20                            # TCombatSpellCA execute entry (another patch's `jmp cave` + nop)
GH_VMT = 0x557F5504
FG_SLOT = GH_VMT + 0xD8                         # TGreatHail fcGetDamageValueEx (VMT slot pointer)
DEF_SITE = 0x5572549C                           # TCombatUnit.GetDefense (CU VMT+0x70)
DEF_ORIG = bytes.fromhex("8b404c8b10ff92c4000000c3")
PREV_OFF = {"reg": 0, "ix": 4, "fg": 8}
UD_SITE, UD_ORIG = 0x55782A40, bytes.fromhex("538bd88bc3")          # TUnit.GetDefense entry: push ebx / mov ebx,eax / mov eax,ebx
HD_SITE, HD_ORIG = 0x557883E8, bytes.fromhex("5356575551")          # THero.GetDefense entry: push ebx/esi/edi/ebp/ecx
TAB, TAB_N, TAB_IDX = 0x558E9E00, 32, 0x558E9F00                    # DATA zero-fill slack (runtime only, not file-backed)
HASAB = 0x5577F618                                                  # TUnit.HasAbility base bit test (eax unit, edx id)
CD_SITE, CD_ORIG = 0x55724A6C, bytes.fromhex("53568bda8bf0")        # TCombatUnit.Destroy entry: push ebx/esi, mov ebx,edx, mov esi,eax


def build(prev, w20):
    out = bytearray(HDR); where = {}
    for k, off in PREV_OFF.items(): struct.pack_into("<I", out, off, prev[k])
    nm = b"Steadfast"
    out += struct.pack("<ii", -1, len(nm)); where["name"] = ZONE + len(out); out += nm + b"\0"

    def place(name, src):
        while len(out) % 16: out.append(0)
        va = ZONE + len(out); where[name] = va; out.extend(asm_delta(src, va))

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
    """ % {"prev": prev["reg"], "vmt": DUR_VMT, "create": DUR_CREATE, "ab": ABIL, "w20": w20, "name": where["name"],
           "lstrasg": LSTRASG, "reg": REGABIL})

    place("ix", """
        cmp dword ptr [eax + 0x18], %(sp)d
        jne pass
        pushal
        mov esi, edx
        mov ebx, eax
        xor edx, edx
        mov dl, byte ptr [ebx + 0xe]
        mov eax, dword ptr [esi + 0xc]
        call %(resolve)#x
        test eax, eax
        je out
        mov edi, eax
        xor edx, edx
        mov dl, byte ptr [ebx + 0xd]
        mov eax, dword ptr [esi + 0xc]
        call %(resolve)#x
        test eax, eax
        je out
        mov dl, byte ptr [eax + 0x45]
        cmp dl, byte ptr [edi + 0x45]
        jne out
        mov ebp, edi
        mov edi, dword ptr [edi + 0x4c]
        test edi, edi
        je out
        mov eax, edi
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x114]
        cmp al, 2
        je out
        call $D
        pop esi
        sub esi, $D
        lea ecx, [esi + %(tab)#x]
        mov ebx, %(n)d
    find:
        cmp dword ptr [ecx], edi
        je store
        add ecx, 8
        dec ebx
        jne find
        mov eax, dword ptr [esi + %(idx)#x]
        and eax, %(mask)d
        lea ecx, [esi + eax*8 + %(tab)#x]
        inc eax
        mov dword ptr [esi + %(idx)#x], eax
    store:
        mov dword ptr [ecx], edi
        mov dword ptr [ecx + 4], ebp
        mov edx, %(ab)d
        mov eax, edi
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x148]
        test al, al
        jne out
        mov edx, %(ab)d
        mov eax, edi
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x94]
    out:
        popal
    pass:
        jmp %(prev)#x
    """ % {"sp": SPELL, "prev": prev["ix"], "resolve": RESOLVE_UNIT, "ab": ABIL, "tab": TAB, "idx": TAB_IDX, "n": TAB_N, "mask": TAB_N - 1})

    place("common", """
        push ebx
        push esi
        push edi
        push ecx
        movsx esi, al
        mov edi, edx
        mov eax, edi
        mov edx, %(ab)d
        call %(hasab)#x
        test al, al
        je keep
        call $D
        pop ebx
        sub ebx, $D
        lea ecx, [ebx + %(tab)#x]
        mov ebx, %(n)d
    look:
        cmp dword ptr [ecx], edi
        je found
        add ecx, 8
        dec ebx
        jne look
        jmp keep
    found:
        mov ebx, dword ptr [ecx + 4]
        test ebx, ebx
        je keep
        cmp dword ptr [ebx + 0x4c], edi
        jne keep
        mov eax, edi
        mov edx, dword ptr [eax]
        call dword ptr [edx + 0xd4]
        movsx eax, al
        test eax, eax
        jle keep
        mov ecx, dword ptr [ebx + 0x5c]
        mov edx, 2
        cmp ecx, eax
        jge bonus
        mov edx, 1
        add ecx, ecx
        cmp ecx, eax
        jle keep
    bonus:
        lea eax, [esi + edx]
        cmp eax, %(cap)d
        jle done
        mov eax, %(cap)d
        cmp esi, eax
        jle done
    keep:
        mov eax, esi
    done:
        pop ecx
        pop edi
        pop esi
        pop ebx
        ret
    """ % {"ab": ABIL, "cap": DEF_CAP, "tab": TAB, "idx": TAB_IDX, "n": TAB_N, "hasab": HASAB})

    # cd = TCombatUnit.Destroy entry (eax = the combat unit, dl = outer flag): forget every table entry for this CU
    place("cd", """
        pushal
        call $D
        pop esi
        sub esi, $D
        lea ecx, [esi + %(tab)#x]
        mov ebx, %(n)d
    scan:
        cmp dword ptr [ecx + 4], eax
        jne nxt
        xor edx, edx
        mov dword ptr [ecx], edx
        mov dword ptr [ecx + 4], edx
    nxt:
        add ecx, 8
        dec ebx
        jne scan
        popal
        push ebx
        push esi
        mov ebx, edx
        mov esi, eax
        jmp %(cont)#x
    """ % {"tab": TAB, "n": TAB_N, "cont": CD_SITE + len(CD_ORIG)})

    place("ud", """
        push eax
        call body
        pop edx
        jmp %(common)s
    body:
        push ebx
        mov ebx, eax
        mov eax, ebx
        jmp %(cont)#x
    """ % {"common": "%#x" % where["common"], "cont": UD_SITE + 5})
    place("hd", """
        push eax
        call body
        pop edx
        jmp %(common)s
    body:
        push ebx
        push esi
        push edi
        push ebp
        push ecx
        jmp %(cont)#x
    """ % {"common": "%#x" % where["common"], "cont": HD_SITE + 5})

    place("fg", """
        cmp dword ptr [eax + 0x10], %(sp)d
        je zero
        jmp %(prev)#x
    zero:
        mov eax, dword ptr [esp + 4]
        xor edx, edx
        mov dword ptr [eax], edx
        mov dword ptr [eax + 4], edx
        mov dword ptr [eax + 8], edx
        mov dword ptr [eax + 0xc], edx
        mov word ptr [eax + 0x10], dx
        ret 8
    """ % {"sp": SPELL, "prev": prev["fg"]})
    zone = bytes(out)
    assert ZONE + len(zone) <= ZONE_END, hex(ZONE + len(zone))
    return zone, where


def rel_target(b, va, op):
    return va + 5 + struct.unpack_from("<i", b, 1)[0] if b[0] == op else None


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--dll", default=DEFAULT_DLL)
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true"); ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read())
    rd = lambda va, n: bytes(d[va - CODE_V2F:va - CODE_V2F + n])
    u32 = lambda va: struct.unpack_from("<I", d, va - CODE_V2F)[0]
    inzone = lambda t: t is not None and ZONE <= t < ZONE_END
    zl = rd(ZONE, ZONE_END - ZONE)
    hdr = lambda k: struct.unpack_from("<I", zl, PREV_OFF[k])[0]
    state, prev = {}, {}
    for k, va, op in (("reg", REG_SITE, 0xE8), ("ix", IX_SITE, 0xE9)):
        t = rel_target(rd(va, 5), va, op)
        if t is None: state[k] = "UNEXPECTED(%s)" % rd(va, 6).hex(); prev[k] = 0
        elif inzone(t): state[k] = "ours"; prev[k] = hdr(k)
        else: state[k] = "chain"; prev[k] = t
    t = u32(FG_SLOT)
    state["fg"], prev["fg"] = ("ours", hdr("fg")) if inzone(t) else ("chain", t)
    db = rd(DEF_SITE, len(DEF_ORIG))                 # v1 hooked CU.GetDefense; v2 wants it vanilla
    defst = "vanilla" if db == DEF_ORIG else "v1" if inzone(rel_target(db, DEF_SITE, 0xE9)) else "OTHER(%s)" % db.hex()
    gst = {}
    for k, va, orig in (("ud", UD_SITE, UD_ORIG), ("hd", HD_SITE, HD_ORIG), ("cd", CD_SITE, CD_ORIG)):
        b = rd(va, len(orig))
        gst[k] = "vanilla" if b == orig else "ours" if inzone(rel_target(b, va, 0xE9)) else "OTHER(%s)" % b.hex()
    w20 = struct.unpack_from("<H", d, HPB_WORD20 - CODE_V2F)[0]
    zone, where = build(prev, w20)
    rl = reloc_set(bytes(d))
    bad = [hex(r) for r in rl if ZONE - 3 <= r < ZONE_END or any(va - 3 <= r < va + n for va, n in
           ((REG_SITE, 5), (IX_SITE, 6), (DEF_SITE, len(DEF_ORIG)), (UD_SITE, 5), (HD_SITE, 5), (CD_SITE, len(CD_ORIG))))]
    if FG_SLOT not in rl: bad.append("fg slot %#x has NO reloc" % FG_SLOT)
    zstate = "zero" if not any(zl) else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else "old"
    print("state %s | CU.GetDefense %s | getters %s | prev %s | zone %s (%d B: %s) | relocs %s" % (
        state, defst, gst, {k: hex(v) for k, v in prev.items()}, zstate, len(zone),
        ", ".join("%s=%#x" % kv for kv in where.items() if kv[0] != "name"), bad or "none"))
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        cav = sorted((v, k) for k, v in where.items() if k != "name") + [(ZONE + len(zone), None)]
        for (va, nm), (nx, _n) in zip(cav, cav[1:]):
            print("  [%s]" % nm)
            for i in md.disasm(zone[va - ZONE:nx - ZONE], va):
                if i.mnemonic == "add" and i.op_str == "byte ptr [eax], al": break
                print("   %08X  %-18s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    ours = [k for k, s_ in state.items() if s_ == "ours"]
    weird = any(s_.startswith(("UNEXPECTED", "OTHER")) for s_ in list(state.values()) + [defst] + list(gst.values()))
    if bad or weird or any(p == 0 or inzone(p) for p in prev.values()) or (ours and len(ours) != len(state)) \
            or (not ours and (zstate != "zero" or defst != "vanilla" or "ours" in gst.values())):
        print("ABORT (relocs / unexpected site bytes / mixed state / zone not free)"); return 1
    if a.revert:
        if not ours: print("already reverted"); return 0
        d[REG_SITE - CODE_V2F:REG_SITE - CODE_V2F + 5] = hook_bytes("call", REG_SITE, prev["reg"], 5)
        d[IX_SITE - CODE_V2F:IX_SITE - CODE_V2F + 5] = hook_bytes("jmp", IX_SITE, prev["ix"], 5)
        struct.pack_into("<I", d, FG_SLOT - CODE_V2F, prev["fg"])
        d[DEF_SITE - CODE_V2F:DEF_SITE - CODE_V2F + len(DEF_ORIG)] = DEF_ORIG
        d[UD_SITE - CODE_V2F:UD_SITE - CODE_V2F + 5] = UD_ORIG
        d[HD_SITE - CODE_V2F:HD_SITE - CODE_V2F + 5] = HD_ORIG
        d[CD_SITE - CODE_V2F:CD_SITE - CODE_V2F + len(CD_ORIG)] = CD_ORIG
        d[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
        with open(a.dll, "r+b") as f: f.write(bytes(d))
        print("reverted (reg -> %#x, ix -> %#x, fg -> %#x, GetDefense x3 + CU.Destroy vanilla, zone zeroed)" % (prev["reg"], prev["ix"], prev["fg"])); return 0
    if ours and zstate == "ours" and defst == "vanilla" and set(gst.values()) == {"ours"}: print("already applied (v3)"); return 0
    frm = "v1" if defst != "vanilla" else "v2"
    if ours: print("in-place upgrade (%s -> v3): zone re-synced, chain targets kept from the zone header" % frm)
    d0 = bytes(d)
    d[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = zone + bytes(ZONE_END - ZONE - len(zone))
    d[REG_SITE - CODE_V2F:REG_SITE - CODE_V2F + 5] = hook_bytes("call", REG_SITE, where["reg"], 5)
    d[IX_SITE - CODE_V2F:IX_SITE - CODE_V2F + 5] = hook_bytes("jmp", IX_SITE, where["ix"], 5)
    struct.pack_into("<I", d, FG_SLOT - CODE_V2F, where["fg"])
    d[DEF_SITE - CODE_V2F:DEF_SITE - CODE_V2F + len(DEF_ORIG)] = DEF_ORIG
    d[UD_SITE - CODE_V2F:UD_SITE - CODE_V2F + 5] = hook_bytes("jmp", UD_SITE, where["ud"], 5)
    d[HD_SITE - CODE_V2F:HD_SITE - CODE_V2F + 5] = hook_bytes("jmp", HD_SITE, where["hd"], 5)
    d[CD_SITE - CODE_V2F:CD_SITE - CODE_V2F + len(CD_ORIG)] = hook_bytes("jmp", CD_SITE, where["cd"], 6)
    print("%d bytes change" % sum(1 for x, y in zip(d0, d) if x != y))
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(a.dll, BAK_SUFFIX + (("2" if frm == "v1" else "3") if ours else ""))
    if os.path.abspath(a.dll) == os.path.abspath(DEFAULT_DLL) and not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    with open(a.dll, "r+b") as f: f.write(bytes(d))
    assert open(a.dll, "rb").read() == bytes(d); print("Written and verified"); return 0


if __name__ == "__main__":
    sys.exit(main())
