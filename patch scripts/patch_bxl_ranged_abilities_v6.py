#!/usr/bin/env python3
r"""v6 (2026-10-19, user: "the projectile needs a bit more glow that stretches to meet its tail, which is currently
separated from the projectile").  NF: the deathfire trail puff (marker 0xCC03) is now spawned at path point idx-1
(was idx-2) from path index 2 (was 3) - the newest puff sits one point behind the skull, inside its aura, so the
streak runs into the head (the art side, fx builder v8, makes the young puff a little bigger / brighter and the
head's fire rim brighter).  Two immediates in the NF cave (`cmp edi,3` -> 2, `sub edi,2` -> 1); same code size and
layout as v5, so every hook keeps its target.  Upgrades v1..v5 in place (v5 recognised by zone magic BXR5); v5's
script refuses a v6 install (magic BXR6); --revert = v1..v5 --revert (all sites back, zones zeroed).

v5 (2026-10-19, user: "the skull is good, the effects around it are mediocre - vanilla-style FIRE and DEATH, a
heavy smooth black glow + a fire glow (skull wrapped by death wrapped by fire), a long smooth fading deathfire TRAIL;
the explosion the SAME as Self-Destruct with death effects ADDED; why can't I see the AOE preview when targeting?; the
scream is bad - get rid of it, make the flight sound evil and epic").  Engine changes (data = pfs v6 + fx/sfx builders):
  NF   cue 2 now plays at path index 2 (right after the throw: the new SKULL_FLIGHT roar, pfs v6 renames the cue) instead
       of the first quarter; and from index 3 on, every tick, a kind-0x26 helper (marker 0xCC03) is spawned at path point
       idx-2 = one DEATHFIRE PUFF of the trail (slot 3 of record 214: 16 frames x 2 ticks of black smoke swelling + fire
       dying, drawn where it was left - a long, smooth, fading trail behind the skull).
  N26 / SLT  marker 0xCC03 -> slot 3 (lifetime and drawn slot), like 0xCC01 -> 2.  The CS cave already sends every 0xCC
       kind-0x26 helper to the next-fx point (never landed - the v3 loop lesson), so the puffs are inert.
  PV   0x428263 (6 B `mov eax,[eax+0x34] / sub eax,0x34`, no reloc) in the tactical TARGET PREVIEW draw 0x427EE4: the
       selected action's +0x34 is the ABILITY id (0x34 = Spell Casting, whose +0x38 spell id picks the area pattern
       through the table at 0x428296: Fire Ball -> case 2 = the 7-hex highlight @0x4283A4).  Abilities never had an
       area preview (case 0x428537 = the single target marker), which is why Hurl Skull showed none since it became an
       AOE in v2.  PV: ability 0xCC -> jmp 0x4283A4 (Fire Ball's 7-hex pattern around the path end), else the vanilla
       `sub eax,0x34` -> 0x428269.  Draw-only, MP-safe.
The head's death aura + bone + fire are a CHAIN of three sequences in slot 0 (TfxHS.Show kind 2 -> 0x42E5FC draws every
chained sequence), and the explosion's death layer is chained in slot 2 in front of the untouched EXPLBIG (the kind-0x26
draw 0x42F050 walks the chain; the first sequence's 30 frames keep the helper's lifetime) - data only.
Upgrades v1..v4 in place (v4's zone-2 caves recognised by address); v4's script refuses a v5 install (magic BXR5);
--revert = v1..v4 --revert (all sites back, zones zeroed).

v4 (2026-10-19, user: "the scream starts too late - it should start fading in immediately"): the mid-flight
SKULL_SCREAM cue moves from the arc MIDPOINT (path index == count/2) to the first quarter (path index == count/4 + 1)
- NF cave `shr eax,1` -> `shr eax,2 / inc eax` (+1 so short throws (count < 4) still reach the index).  Everything else
= v3.  Upgrades v1/v2/v3 in place (v3's zone-2 caves recognised by address; only nf / n26 / slt move); v3's script
refuses a v4 install (zone magic BXR4); --revert = v1/v2/v3 --revert.

v3 (2026-10-19, user: "upon hit it loops the explosion indefinitely" -> game lock; and "it should still be able to
hit itself if it shoots an adjacent hex").  ROOT CAUSE: TCAbRangedTE.Execute walks EVERY fx in the map's effect list
[[0x469420]+0x11C] each tick (0x40B7A3) and lands any finished ([fx+0xC] != 0) ability fx through the generic landing
code.  v2's kind-0x26 explosion helper (AddEffect 0x41C6EC puts it in that same list; [fx+0x14] = 0xCC) therefore
"landed" when its 30-frame explosion finished: CS sent it to the landed path -> SA -> AOE again + a NEW explosion helper
-> which finished 30 frames later -> ... forever (and the area took damage every 30 frames).  v3 CS: a 0xCC fx of kind
0x26 (our helper) goes straight to the next-fx point 0x40CAF2 - it never lands.  HM: the thrower is no longer skipped
(the Fire Ball-sized area now hits it too when it throws at an adjacent hex).  Everything else = v2.  Upgrades v1/v2 in
place (v2's zone-2 caves are recognised by address); v2's script refuses a v3 install; --revert = v1/v2 --revert.


Hurl Skull (ability 0xCC) + Shoot Black Javelin (ability 0xCD) v2 - 2026-10-19.  Supersedes
patch_bxl_ranged_abilities_v1.py and upgrades it IN PLACE (v1's zones keep their layout; the zone magic becomes 'BXR2'
so the v1 script refuses a v2 install).  Data part = patch_bxl_ranged_ability_pfs_v2.py (record 214 v2).

User on v1 (both work): (1) rename 'Hurl Flaming Skull' -> 'Hurl Skull'; (2) Shoot Black Javelin 'seems crooked and
slow' -> match vanilla; (3) Hurl Skull becomes an AOE the size of Fire Ball, same Hurl Boulder arc, Fire Ball /
Self-Destruct explosion on impact with its own explosion sfx, the boulder toss/crunch kept plus a mid-flight scream.

(2) ROOT CAUSE - speed, not data: record 215 is vanilla record 68 byte-for-byte (ARROW.ILB 300-323, 24 directions,
identical to 1.36) and AbilTypes / the flight-shape switch already match 0x3A.  But TfxHS.NewFrame's shared step for
kinds 1/2/3/5/6/0xD (0x429FBB..) adds a SECOND path point per tick for abilities 0x2C/0x2D (cannons), 0x39/0x3A
(javelins) and 0x7B: `add eax,-0x2c / sub eax,2 / jb +1 ... add eax,-5 / sub eax,2 / jb +1 ... sub eax,0x40 / jne`
@0x429FC1.  0xCD was missing from that switch, so its javelin flew at HALF speed along the flat javelin arc - slow,
and with one direction sprite per segment stretched over twice the frames the arc reads as a crooked, wobbling
javelin.  Fix: NF hook @0x429FC1 aliases 0xCD -> 0x39 for that switch too (now every id switch v1/v2 touches treats
0xCD as Shoot Javelin).

(3) Hurl Skull machinery (AoWTCPCK; Fire Ball's 7-hex pattern; RE 2026-10-19):
  * Fire Ball's AOE (TCAbRangedTE.Execute 0x40B814..0x40B8C3): for i = 0..6 CenterHNtoHX(cx, cy, i) 0x4022AC
    (eax cx, edx cy, ecx i, push &x, push &y) -> GetLevel 0x401E64 / GetField 0x401E54 (edx x, ecx y) ->
    SendMsg 0x401DDC (eax field, edx msg) with msg 0x31003 {+8 caster CU, +0x1C -1}; the unit HS handler
    0x420FC1 seeds the damage RNG (Random(0xFFFFFF) 0x40298C -> [[0x46DC08]]), builds GetSpell(0x75).CreateCA(caster,
    target CU [hs+0x1C]) and joins the shared tail 0x42101C (hit flash 0x4236E0 dl 4 if damage, ExecuteCombatAction
    via [[map]+0xE4] 0x40259C, release CA) -> 0x421728.
  * The generic landing @0x40C31F builds ONE CA for the hit unit; the class switch @0x40C6DD (impact hex known,
    [ebp-0x28] / [ebp-0x2C]) sends the boulder's 0x31001 (walls / terrain) - v1's SA alias maps 0xCC there.
  * kind-0x26 helpers (Seeker Bolts' idiom): AddEffect(map, 0x26) 0x41C6EC + one TXYZ point, [+0x14] ability,
    [+0x18] marker; their NewFrame lifetime slot comes from the N26 site 0x42A613 and their drawn slot from the slot
    chain head 0x42E4C4 (both currently Seeker Bolts' caves - chained, not replaced).
  v2 hooks (new zone 0x452000..0x452800 'BXR2', original bytes kept in its header):
    CS  0x40C31F (7 B `mov eax,[ebp-0x20] / cmp byte [eax+0xC],0`): a 0xCC strike skips the single-target CA
        (jumps to 0x40C5A4 = the landed-strike path: impact hex, the Gravity Well / Sanctify 'land' chain @0x40C609,
        then - no CA - the class switch) -> no double hit on the target.
    SA  (v1's cave, rebuilt): 0xCC -> call AOE first, then the 0x18 alias (0x31001 walls / terrain at the centre).
    AOE send msg 0x31020 {+8 caster, +0xC ability 0xCC, +0x1C -1} to the 7 Fire Ball hexes around the impact hex,
        then spawn a kind-0x26 helper (marker 0xCC01) at the strike's last path point = the explosion.
    HM  0x420FC1 (9 B, the unit HS handler's 0x31003 test): msg 0x31020 -> skip the caster / empty HS, seed the RNG
        like Fire Ball, CA = GetAbility([msg+0xC]).CreateCA(caster, unit) (push 0 / 0x402704 / 0x402874 - the generic
        ability path of the landing code) -> Fire Ball's tail 0x42101C.  Every unit in the area (either side, not the
        thrower) rolls the ability's own ATK 3 vs DEF / DMG 8 / mask fire+death+physical+walls like a ranged hit.
    NF  0x429FC1 (6 B): 0xCD -> 0x39 (javelin double step, see (2)); 0xCC -> when the path index reaches count/2 play
        sound cue 2 (SKULL_SCREAM) through the ability's sound library (sound-on gate [map+0x129], Seeker's idiom).
    N26 0x42A613 (5 B `call <Seeker N26>`): call Seeker's cave, then a 0xCC helper with marker 0xCC01 lives for slot 2.
    SLT 0x42E4C4 (chain head `jmp <prev> / nop nop`): 0xCC kind-0x26 helper with marker 0xCC01 -> slot 2; else prev.
  The landing cue 1 (SKULL_HIT) is played by the engine when the lob arrives (unchanged).
MP: deterministic - damage rolls go through the combat RNG exactly like Fire Ball's; sounds behind the sound gate.
AoWEPACK: only the registration literal changes ('Hurl Skull'; same 32-byte name slot -> same zone layout).
LIFO: v2 becomes the head of the N26 / SLT chains (in front of Seeker Bolts) and owns CS / HM / NF -> revert v2 BEFORE
patch_tc_seekerbolts_v3.py, Channeler, Tame v2/v3, Reversal.  --revert restores every v1 + v2 site and zeroes both
zones (= v1's own --revert result).  To go back to v1: v2 --revert, then v1 --apply.
Dry-run default; --apply / --revert / --dis; --dll / --tcdll <scratch copies>.  Backups (first apply):
<game>\backup\AoWEPACK.dll.bak_bxlranged2, AoWTCPCK.dll.bak_bxlranged2.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
from patch_tc_hellfire_portal_v1 import asm_delta

DEFAULT_DLL = game_file("AoWEPACK.dll")
DEFAULT_TC = game_file("AoWTCPCK.dll")
BAK_SUFFIX = ".bak_bxlranged6"
EBASE, TBASE = 0x55700000, 0x400000
EZONE, EZONE_END = 0x55817400, 0x55818000
TZONE, TZONE_END = 0x451D00, 0x452000
MAGIC, MAGIC_V5, MAGIC_V4, MAGIC_V3, MAGIC_V2, MAGIC_V1 = b"BXR6", b"BXR5", b"BXR4", b"BXR3", b"BXR2", b"BXR1"
EHDR, THDR = 0x80, 0x50

CTOR, REGABIL = 0x5576ED48, 0x55750238
REG_SITE = 0x557BCF6E
VAL1_SITE, VAL1_ORIG = 0x5575BB37, bytes.fromhex("ba3a000000")
VAL2_SITE, VAL2_ORIG = 0x5575BC26, bytes.fromhex("ba2c000000")
BRCH_SITE, BRCH_ORIG = 0x5577ED64, bytes.fromhex("ba2c000000")

ABILTYPES = 0x467248
SKULL, JAV = 0xCC, 0xCD
ABIL = [  # id, name, ATK, DMG, shots, range, mask, unused, AbilTypes kind, alias for the TCPCK switches
    (SKULL, b"Hurl Skull", 3, 8, 1, 3, 0x1A1, 0x6E, 2, 0x18),
    (JAV, b"Shoot Black Javelin", 8, 6, 1, 3, 0x0A0, 0x7B, 1, 0x39),
]
SA_SITE, SA_ORIG, SA_BACK = 0x40C6EA, bytes.fromhex("8b401483f82c"), 0x40C6F0
SB_SITE, SB_ORIG, SB_BACK = 0x4175AD, bytes.fromhex("8b45a483f82d"), 0x4175B3
SC_SITE, SC_ORIG, SC_BACK = 0x4271FD, bytes.fromhex("0fbf45fc83f834"), 0x427204
SCANS = {  # name: site, counter frame offset, loop top, exit, list of extra ids, vanilla 13 bytes
    "S1": (0x418A73, -0x14, 0x41870D, 0x418A80, [SKULL, JAV], bytes.fromhex("817decaa0000000f858dfcffff")),
    "S2": (0x418D1F, -0x0C, 0x418B3E, 0x418D2C, [SKULL, JAV], bytes.fromhex("817df4aa0000000f8512feffff")),
    "S4": (0x41977F, -0x0C, 0x41958C, 0x41978C, [SKULL, JAV], bytes.fromhex("817df4aa0000000f8500feffff")),
}
# ---- v2: AoWTCPCK zone 2 (0x452000.., header 'BXR2' + the original bytes of the v2 sites)
TZ2, TZ2_END, T2HDR = 0x452000, 0x452800, 0x40
CS_SITE, CS_ORIG, CS_CONT, CS_SKIP, CS_NEXT = 0x40C31F, bytes.fromhex("8b45e080780c00"), 0x40C326, 0x40C5A4, 0x40CAF2
HM_SITE, HM_ORIG = 0x420FC1, bytes.fromhex("8b45f8813803100300")
HM_CONT, HM_TAIL, HM_END = 0x420FCA, 0x42101C, 0x421728
NF_SITE, NF_ORIG, NF_BACK = 0x429FC1, bytes.fromhex("83c0d483e802"), 0x429FC7
N26_SITE, SLT_SITE = 0x42A613, 0x42E4C4
MSG_AOE, MARK_EXPL, SLOT_EXPL, CUE_SCREAM = 0x31020, 0xCC01, 2, 2
MARK_PUFF, SLOT_PUFF, FLIGHT_IDX, PUFF_FROM, PUFF_BACK = 0xCC03, 3, 2, 2, 1   # v6: puff one point behind (v5: from 3, back 2)
PV_SITE, PV_ORIG, PV_BACK, PV_CASE = 0x428263, bytes.fromhex("8b403483e834"), 0x428269, 0x4283A4
CENTER2HX, GETLEVEL, GETFIELD, SENDMSG = 0x4022AC, 0x401E64, 0x401E54, 0x401DDC
COUNT, GETXYZ, XYZADD, ADDEFFECT, TOBJCREATE = 0x402DFC, 0x402DF4, 0x402DE4, 0x41C6EC, 0x401040
GETABILITY, CREATECA, RANDOM, SFXPLAY = 0x402704, 0x402874, 0x40298C, 0x4022F4
G_COMBAT, G_MAP, G_REG, G_RND, G_SEED, G_TXYZ = 0x469420, 0x46C064, 0x46E8D0, 0x46E8D4, 0x46DC08, 0x46EB24
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, va):
    return bytes(ks.asm(src, va)[0])


def lit(s):
    return struct.pack("<ii", -1, len(s)) + s + b"\0"


def sections(d):
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    n = struct.unpack_from("<H", d, pe + 6)[0]; opt = struct.unpack_from("<H", d, pe + 20)[0]
    return [struct.unpack_from("<IIII", d, pe + 24 + opt + 40 * i + 8) for i in range(n)], pe


def va2off(d, va, base):
    for vs, rva, rs, ro in sections(d)[0]:
        if rva <= va - base < rva + max(vs, rs):
            return ro + va - base - rva
    raise ValueError(hex(va))


def reloc_set(d, base):
    secs, pe = sections(d)
    rrva, rsz = struct.unpack_from("<II", d, pe + 24 + 0x88)
    p = va2off(d, base + rrva, base); end = p + rsz; out = set()
    while p < end:
        page, size = struct.unpack_from("<II", d, p)
        if size < 8: break
        for q in range(p + 8, p + size, 2):
            e = struct.unpack_from("<H", d, q)[0]
            if e >> 12 == 3: out.add(base + page + (e & 0xFFF))
        p += size
    return out


def rel(op, src, dst, n):
    return bytes([op]) + struct.pack("<i", dst - (src + 5)) + b"\x90" * (n - 5)


def jmp_target(b, site):
    return site + 5 + struct.unpack_from("<i", b, 1)[0] if b[0] == 0xE9 else None


# ------------------------------------------------------------------ AoWEPACK
def build_e(prev_reg):
    out = bytearray(EHDR); where = {}

    def place(name, src):
        while len(out) % 16: out.append(0)
        va = EZONE + len(out); where[name] = va
        out.extend(asm(src, va))

    names = {}
    p = 0x30
    for ab in ABIL:
        b = lit(ab[1]); out[p:p + len(b)] = b; names[ab[0]] = EZONE + p + 8; p += (len(b) + 15) & ~15
    assert p <= EHDR
    regs = ""
    for (i, nm, atk, dmg, shots, rng, mask, unused, _k, _a) in ABIL:
        regs += """
        push %(dmg)d
        push %(shots)d
        push %(rng)d
        push %(mask)#x
        push %(unused)#x
        lea edx, [esi + %(name)#x]
        mov cl, %(atk)d
        mov eax, %(id)#x
        call %(ctor)#x
        mov edx, eax
        mov eax, ebx
        call %(reg)#x""" % dict(dmg=dmg, shots=shots, rng=rng, mask=mask, unused=unused, name=names[i], atk=atk, id=i,
                                 ctor=CTOR, reg=REGABIL)
    place("reg", """
        call %(prev)#x
        push esi
        call rd
    rd:
        pop esi
        sub esi, rd
        %(regs)s
        pop esi
        ret
    """ % {"prev": prev_reg, "regs": regs})
    place("val1", """
        mov edx, 0x3a
        mov eax, dword ptr [ebx + 0x38]
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x4c]
        test al, al
        jne 0x5575bb48
        mov edx, %(jav)#x
        mov eax, dword ptr [ebx + 0x38]
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x4c]
        test al, al
        jne 0x5575bb48
        jmp 0x5575bb4b
    """ % {"jav": JAV})
    place("val2", """
        mov edx, 0x2c
        mov eax, dword ptr [ebx + 0x38]
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x4c]
        test al, al
        jne 0x5575bc59
        mov edx, %(sk)#x
        mov eax, dword ptr [ebx + 0x38]
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x4c]
        test al, al
        jne 0x5575bc59
        jmp 0x5575bc37
    """ % {"sk": SKULL})
    place("brch", """
        mov edx, 0x2c
        mov eax, esi
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x148]
        test al, al
        jne 0x5577ed77
        mov edx, %(sk)#x
        mov eax, esi
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x148]
        test al, al
        jne 0x5577ed77
        jmp 0x5577ed80
    """ % {"sk": SKULL})
    assert EZONE + len(out) <= EZONE_END
    return out, where


# ------------------------------------------------------------------ AoWTCPCK
def alias_lines(reg="eax"):
    s = ""
    for (i, _n, _a, _d, _s, _r, _m, _u, _k, al) in ABIL:
        s += """
        cmp %(r)s, %(i)#x
        jne n%(i)x
        mov %(r)s, %(al)#x
    n%(i)x:""" % {"r": reg, "i": i, "al": al}
    return s


def build_t(prev_s2, aoe_va):
    out = bytearray(THDR); where = {}

    def place(name, src):
        while len(out) % 16: out.append(0)
        va = TZONE + len(out); where[name] = va
        out.extend(asm(src, va))

    place("sa", """
        cmp dword ptr [eax + 0x14], %#x
        jne sa_a
        call %#x
    sa_a:
        mov eax, dword ptr [eax + 0x14]
        %s
        cmp eax, 0x2c
        jmp %#x
    """ % (SKULL, aoe_va, alias_lines(), SA_BACK))
    place("sb", """
        mov eax, dword ptr [ebp - 0x5c]
        %s
        cmp eax, 0x2d
        jmp %#x
    """ % (alias_lines(), SB_BACK))
    place("sc", """
        movsx eax, word ptr [ebp - 4]
        %s
        cmp eax, 0x34
        jmp %#x
    """ % (alias_lines(), SC_BACK))
    for nm, (site, ctr, top, ext, ids, _v) in SCANS.items():
        prev = prev_s2 if nm == "S2" else None
        c = "dword ptr [ebp - %#x]" % -ctr
        src = """
        cmp %(c)s, 0xaa
        jb %(top)#x""" % {"c": c, "top": top}
        if prev:
            src += """
        cmp %(c)s, 0xca
        jb %(prev)#x""" % {"c": c, "prev": prev}
        for i in sorted(ids):
            src += """
        cmp %(c)s, %(i)#x
        jbe s%(n)s%(i)x""" % {"c": c, "i": i, "n": nm}
        src += """
        jmp %#x""" % ext
        for i in sorted(ids):
            src += """
    s%(n)s%(i)x:
        mov %(c)s, %(i)#x
        jmp %(top)#x""" % {"c": c, "i": i, "n": nm, "top": top}
        place(nm, src)
    assert TZONE + len(out) <= TZONE_END
    return out, where


def build_t2(prev_n26, prev_slt):
    """v2 caves in AoWTCPCK zone 2 (see the docstring).  prev_n26 / prev_slt = the current N26 call target and the
    slot-chain head's jmp target (Seeker Bolts' caves on the live DLL), chained behind ours."""
    out = bytearray(T2HDR); where = {}
    P = dict(sk=SKULL, jav=JAV, cs_cont=CS_CONT, cs_skip=CS_SKIP, cs_next=CS_NEXT, msg=MSG_AOE, mark=MARK_EXPL, slot=SLOT_EXPL,
             cue=CUE_SCREAM, c2hx=CENTER2HX, getlevel=GETLEVEL, getfield=GETFIELD, send=SENDMSG, count=COUNT,
             getxyz=GETXYZ, xyzadd=XYZADD, add=ADDEFFECT, create=TOBJCREATE, getab=GETABILITY, createca=CREATECA,
             rnd=RANDOM, play=SFXPLAY, gcombat=G_COMBAT, gmap=G_MAP, greg=G_REG, grnd=G_RND, gseed=G_SEED,
             gtxyz=G_TXYZ, hm_cont=HM_CONT, hm_tail=HM_TAIL, hm_end=HM_END, nf_back=NF_BACK,
             mpuff=MARK_PUFF, spuff=SLOT_PUFF, fidx=FLIGHT_IDX, pfrom=PUFF_FROM, pback=PUFF_BACK, pv_back=PV_BACK, pv_case=PV_CASE,
             prev_n26=prev_n26, prev_slt=prev_slt)

    def place(name, src):
        while len(out) % 16: out.append(0)
        va = TZ2 + len(out); where[name] = va
        out.extend(asm_delta(src % dict(P, **where), va))

    # spawn: esi = strike, edi = path index, ecx = marker, ebx = PIC delta -> a kind-0x26 helper at that path point
    # (Seeker Bolts' helper idiom, ability 0xCC)
    place("spawn", """
        push esi
        push edi
        push ebp
        push ecx
        mov eax, [esi+0x1c]
        mov edx, edi
        call %(getxyz)#x
        mov ecx, [eax+4]
        mov edx, [eax+8]
        sub edx, [eax+0xc]
        push edx
        push ecx
        mov eax, [ebx+%(gmap)#x]
        mov dl, 0x26
        call %(add)#x
        mov ebp, eax
        mov dl, 1
        mov eax, [ebx+%(gtxyz)#x]
        call %(create)#x
        mov edx, eax
        mov eax, [ebp+0x1c]
        call %(xyzadd)#x
        mov eax, [ebp+0x1c]
        xor edx, edx
        call %(getxyz)#x
        pop ecx
        mov [eax+4], ecx
        pop edx
        mov [eax+8], edx
        mov dword ptr [eax+0xc], 0
        mov dword ptr [ebp+0x14], %(sk)d
        pop ecx
        mov [ebp+0x18], ecx
        mov dword ptr [ebp+0x2c], 0
        pop ebp
        pop edi
        pop esi
        ret
    """)
    # aoe: called from the SA cave inside TCAbRangedTE.Execute ([ebp-4] TE, [ebp-0x20] strike, [ebp-0x28] / [ebp-0x2c]
    # impact hex x / y).  Locals: [esp] msg (0x40 B), [esp+0x40] x, [esp+0x44] y, [esp+0x48] i.  Preserves all regs.
    place("aoe", """
        pushad
        call $D
        pop ebx
        sub ebx, $D
        sub esp, 0x50
        mov edi, esp
        xor eax, eax
        mov ecx, 0x14
        rep stosd
        mov dword ptr [esp], %(msg)#x
        mov eax, [ebp-4]
        mov eax, [eax+0x10]
        mov [esp+8], eax
        mov dword ptr [esp+0xc], %(sk)#x
        mov dword ptr [esp+0x1c], 0xffffffff
    ao_lp:
        lea eax, [esp+0x40]
        push eax
        lea eax, [esp+0x48]
        push eax
        mov ecx, [esp+0x50]
        mov edx, [ebp-0x2c]
        mov eax, [ebp-0x28]
        call %(c2hx)#x
        mov eax, [ebx+%(gcombat)#x]
        mov eax, [eax]
        mov eax, [eax+0x10]
        xor edx, edx
        call %(getlevel)#x
        mov ecx, [esp+0x44]
        mov edx, [esp+0x40]
        call %(getfield)#x
        test eax, eax
        je ao_nx
        mov edx, esp
        call %(send)#x
    ao_nx:
        inc dword ptr [esp+0x48]
        cmp dword ptr [esp+0x48], 7
        jb ao_lp
        mov esi, [ebp-0x20]
        mov eax, [esi+0x1c]
        call %(count)#x
        lea edi, [eax-1]
        test edi, edi
        jl ao_done
        mov ecx, %(mark)#x
        call %(spawn)#x
    ao_done:
        add esp, 0x50
        popad
        ret
    """)
    place("cs", """
        mov eax, [ebp-0x20]
        cmp dword ptr [eax+0x14], %(sk)#x
        je cs_sk
        cmp byte ptr [eax+0xc], 0
        jmp %(cs_cont)#x
    cs_sk:
        cmp byte ptr [eax+0x34], 0x26
        je cs_hlp
        jmp %(cs_skip)#x
    cs_hlp:
        jmp %(cs_next)#x
    """)
    place("hm", """
        mov eax, [ebp-8]
        cmp dword ptr [eax], %(msg)#x
        je hm_own
        cmp dword ptr [eax], 0x31003
        jmp %(hm_cont)#x
    hm_own:
        mov eax, [ebp-4]
        mov ecx, [eax+0x1c]
        test ecx, ecx
        je hm_out
        push ebx
        call $D
        pop ebx
        sub ebx, $D
        mov eax, [ebx+%(grnd)#x]
        mov eax, [eax]
        mov edx, 0xffffff
        call %(rnd)#x
        mov edx, [ebx+%(gseed)#x]
        mov [edx], eax
        push 0
        mov edx, [ebp-8]
        mov edx, [edx+0xc]
        mov eax, [ebx+%(greg)#x]
        mov eax, [eax]
        mov eax, [eax+0x80]
        call %(getab)#x
        mov ecx, [ebp-4]
        mov ecx, [ecx+0x1c]
        mov edx, [ebp-8]
        mov edx, [edx+8]
        call %(createca)#x
        pop ebx
        test eax, eax
        je hm_out
        jmp %(hm_tail)#x
    hm_out:
        jmp %(hm_end)#x
    """)
    place("nf", """
        cmp eax, %(jav)#x
        jne nf_a
        mov eax, 0x39
    nf_a:
        cmp eax, %(sk)#x
        jne nf_b
        push eax
        push ecx
        push edx
        push ebx
        push esi
        push edi
        mov esi, [ebp-8]
        call $D
        pop ebx
        sub ebx, $D
        mov edi, [esi+0x10]
        cmp edi, %(pfrom)d
        jl nf_np
        mov eax, [esi+0x1c]
        call %(count)#x
        cmp edi, eax
        jge nf_np
        sub edi, %(pback)d
        mov ecx, %(mpuff)#x
        call %(spawn)#x
    nf_np:
        pop edi
        cmp dword ptr [esi+0x10], %(fidx)d
        jne nf_c
        mov eax, [ebx+%(gmap)#x]
        cmp byte ptr [eax+0x129], 0
        je nf_c
        mov eax, [ebx+%(greg)#x]
        mov eax, [eax]
        mov eax, [eax+0x80]
        mov edx, %(sk)#x
        call %(getab)#x
        mov eax, [eax+0x18]
        mov edx, %(cue)d
        call %(play)#x
    nf_c:
        pop esi
        pop ebx
        pop edx
        pop ecx
        pop eax
    nf_b:
        add eax, -0x2c
        sub eax, 2
        jmp %(nf_back)#x
    """)
    place("n26", """
        call %(prev_n26)#x
        push ecx
        mov ecx, [ebp-8]
        cmp dword ptr [ecx+0x14], %(sk)#x
        jne n26_x
        cmp dword ptr [ecx+0x18], %(mark)#x
        jne n26_p
        mov edx, %(slot)d
    n26_p:
        cmp dword ptr [ecx+0x18], %(mpuff)#x
        jne n26_x
        mov edx, %(spuff)d
    n26_x:
        pop ecx
        ret
    """)
    place("slt", """
        push ecx
        mov ecx, [esp+8]
        mov ecx, [ecx-4]
        cmp dword ptr [ecx+0x14], %(sk)#x
        jne sl_p
        cmp byte ptr [ecx+0x34], 0x26
        jne sl_p
        cmp eax, 1
        jne sl_p
        cmp dword ptr [ecx+0x18], %(mark)#x
        jne sl_q
        mov eax, %(slot)d
        jmp sl_p
    sl_q:
        cmp dword ptr [ecx+0x18], %(mpuff)#x
        jne sl_p
        mov eax, %(spuff)d
    sl_p:
        pop ecx
        jmp %(prev_slt)#x
    """)
    place("pv", """
        mov eax, [eax+0x34]
        cmp eax, %(sk)#x
        je pv_aoe
        sub eax, 0x34
        jmp %(pv_back)#x
    pv_aoe:
        jmp %(pv_case)#x
    """)
    assert TZ2 + len(out) <= TZ2_END
    return out, where


def write_inplace(path, data):
    with open(path, "r+b") as f:
        f.seek(0); f.write(data); f.truncate(len(data))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dll", default=DEFAULT_DLL)
    ap.add_argument("--tcdll", default=DEFAULT_TC)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    d = open(a.dll, "rb").read(); t = open(a.tcdll, "rb").read()
    eg = lambda va, n: bytes(d[va2off(d, va, EBASE):va2off(d, va, EBASE) + n])
    tg = lambda va, n: bytes(t[va2off(t, va, TBASE):va2off(t, va, TBASE) + n])
    ezl, tzl, t2l = eg(EZONE, EZONE_END - EZONE), tg(TZONE, TZONE_END - TZONE), tg(TZ2, TZ2_END - TZ2)
    emag, tmag, t2mag = ezl[:4], tzl[:4], t2l[:4]
    eours, tours = emag in (MAGIC, MAGIC_V5, MAGIC_V4, MAGIC_V3, MAGIC_V2, MAGIC_V1), tmag in (MAGIC, MAGIC_V5, MAGIC_V4, MAGIC_V3, MAGIC_V2, MAGIC_V1)
    if eours != tours or (emag in (MAGIC, MAGIC_V5, MAGIC_V4, MAGIC_V3, MAGIC_V2)) != (t2mag in (MAGIC, MAGIC_V5, MAGIC_V4, MAGIC_V3, MAGIC_V2)):
        print("ABORT - half applied (AoWEPACK %s / AoWTCPCK %s / zone2 %s)" % (emag, tmag, t2mag)); return 1
    if not eours and any(t2l):
        print("ABORT - v2 zone 2 is not empty while v1/v2 is absent"); return 1
    state = "v6" if emag == MAGIC else "v5" if emag == MAGIC_V5 else "v4" if emag == MAGIC_V4 else "v3" if emag == MAGIC_V3 else "v2" if emag == MAGIC_V2 else "v1" if emag == MAGIC_V1 else "none"
    cur = {"reg": eg(REG_SITE, 5), "val1": eg(VAL1_SITE, 5), "val2": eg(VAL2_SITE, 5), "brch": eg(BRCH_SITE, 5)}
    tcur = {"ab": tg(ABILTYPES + SKULL, 2), "sa": tg(SA_SITE, 6), "sb": tg(SB_SITE, 6), "sc": tg(SC_SITE, 7)}
    for nm, sc in SCANS.items(): tcur[nm] = tg(sc[0], 13)
    t2cur = {"cs": tg(CS_SITE, 7), "hm": tg(HM_SITE, 9), "nf": tg(NF_SITE, 6), "n26": tg(N26_SITE, 5), "slt": tg(SLT_SITE, 7),
             "pv": tg(PV_SITE, 6)}
    if eours:
        sav = {"reg": ezl[4:9], "val1": ezl[0x0C:0x11], "val2": ezl[0x14:0x19], "brch": ezl[0x1C:0x21]}
        tsav = {"ab": tzl[4:6], "sa": tzl[8:14], "sb": tzl[0x10:0x16], "sc": tzl[0x18:0x1F],
                "S1": tzl[0x20:0x2D], "S2": tzl[0x30:0x3D], "S4": tzl[0x40:0x4D]}
    else:
        sav, tsav = dict(cur), dict(tcur)
    t2sav = ({"cs": t2l[4:11], "hm": t2l[0x10:0x19], "nf": t2l[0x20:0x26], "n26": t2l[0x28:0x2D], "slt": t2l[0x30:0x37]}
             if state in ("v2", "v3", "v4", "v5", "v6") else dict(t2cur))
    t2sav["pv"] = t2l[0x38:0x3E] if state in ("v5", "v6") else t2cur["pv"]
    assert sav["reg"][0] == 0xE8, "reg site original is not a call (%s)" % sav["reg"].hex()
    for k, o in (("val1", VAL1_ORIG), ("val2", VAL2_ORIG), ("brch", BRCH_ORIG)):
        assert sav[k] == o, "%s original %s (expected %s) - another patch?" % (k, sav[k].hex(), o.hex())
    for k, o in (("sa", SA_ORIG), ("sb", SB_ORIG), ("sc", SC_ORIG)):
        assert tsav[k] == o, "%s original %s (expected %s) - another patch?" % (k, tsav[k].hex(), o.hex())
    for nm in ("S1", "S4"):
        assert tsav[nm] == SCANS[nm][5], "%s original %s - another patch?" % (nm, tsav[nm].hex())
    for k, o in (("cs", CS_ORIG), ("hm", HM_ORIG), ("nf", NF_ORIG), ("pv", PV_ORIG)):
        assert t2sav[k] == o, "%s original %s (expected %s) - another patch?" % (k, t2sav[k].hex(), o.hex())
    assert t2sav["n26"][0] == 0xE8, "N26 site %#x is not a call (%s) - Seeker Bolts v2/v3 expected" % (N26_SITE, t2sav["n26"].hex())
    assert t2sav["slt"][0] == 0xE9 and t2sav["slt"][5:] == b"\x90\x90", \
        "slot chain head %#x is not `jmp + nop nop` (%s) - Seeker Bolts v2/v3 expected" % (SLT_SITE, t2sav["slt"].hex())
    prev_n26 = N26_SITE + 5 + struct.unpack_from("<i", t2sav["n26"], 1)[0]
    prev_slt = SLT_SITE + 5 + struct.unpack_from("<i", t2sav["slt"], 1)[0]
    prev_s2 = jmp_target(tsav["S2"], SCANS["S2"][0])
    assert tsav["S2"] == SCANS["S2"][5] or (prev_s2 and tsav["S2"][5:] == b"\x90" * 8), \
        "S2 original %s - neither vanilla nor a 'jmp + 8 nop' hook" % tsav["S2"].hex()
    prev_reg = REG_SITE + 5 + struct.unpack_from("<i", sav["reg"], 1)[0]
    t2zone, t2w = build_t2(prev_n26, prev_slt)
    ezone, ew = build_e(prev_reg); tzone, tw = build_t(prev_s2, t2w["aoe"])
    ezone[0:4] = MAGIC; ezone[4:9] = sav["reg"]; ezone[0x0C:0x11] = sav["val1"]; ezone[0x14:0x19] = sav["val2"]
    ezone[0x1C:0x21] = sav["brch"]
    tzone[0:4] = MAGIC; tzone[4:6] = tsav["ab"]; tzone[8:14] = tsav["sa"]; tzone[0x10:0x16] = tsav["sb"]
    tzone[0x18:0x1F] = tsav["sc"]; tzone[0x20:0x2D] = tsav["S1"]; tzone[0x30:0x3D] = tsav["S2"]; tzone[0x40:0x4D] = tsav["S4"]
    t2zone[0:4] = MAGIC; t2zone[4:11] = t2sav["cs"]; t2zone[0x10:0x19] = t2sav["hm"]; t2zone[0x20:0x26] = t2sav["nf"]
    t2zone[0x28:0x2D] = t2sav["n26"]; t2zone[0x30:0x37] = t2sav["slt"]; t2zone[0x38:0x3E] = t2sav["pv"]
    ezone, tzone, t2zone = bytes(ezone), bytes(tzone), bytes(t2zone)
    hook = {"reg": rel(0xE8, REG_SITE, ew["reg"], 5), "val1": rel(0xE9, VAL1_SITE, ew["val1"], 5),
            "val2": rel(0xE9, VAL2_SITE, ew["val2"], 5), "brch": rel(0xE9, BRCH_SITE, ew["brch"], 5)}
    thook = {"ab": bytes(ab[8] for ab in ABIL), "sa": rel(0xE9, SA_SITE, tw["sa"], 6), "sb": rel(0xE9, SB_SITE, tw["sb"], 6),
             "sc": rel(0xE9, SC_SITE, tw["sc"], 7)}
    for nm, sc in SCANS.items(): thook[nm] = rel(0xE9, sc[0], tw[nm], 13)
    t2hook = {"cs": rel(0xE9, CS_SITE, t2w["cs"], 7), "hm": rel(0xE9, HM_SITE, t2w["hm"], 9),
              "nf": rel(0xE9, NF_SITE, t2w["nf"], 6), "n26": rel(0xE8, N26_SITE, t2w["n26"], 5),
              "slt": rel(0xE9, SLT_SITE, t2w["slt"], 7), "pv": rel(0xE9, PV_SITE, t2w["pv"], 6)}
    # v1 hooks point at the same cave addresses (v1 layout kept) -> 'ours' covers v1 too
    st = {k: "ours" if cur[k] == hook[k] else "orig" if cur[k] == sav[k] else "OTHER" for k in cur}
    v1th = {}
    if state == "v1":                                           # v1's TCPCK caves sit at v1 addresses (sa grew in v2)
        import patch_bxl_ranged_abilities_v1 as V1
        _z, v1tw = V1.build_t(prev_s2)
        v1th = {"sa": rel(0xE9, SA_SITE, v1tw["sa"], 6), "sb": rel(0xE9, SB_SITE, v1tw["sb"], 6), "sc": rel(0xE9, SC_SITE, v1tw["sc"], 7)}
        for nm, sc in SCANS.items(): v1th[nm] = rel(0xE9, sc[0], v1tw[nm], 13)
    tst = {k: "ours" if tcur[k] == thook[k] else "orig" if tcur[k] == tsav[k] else "v1" if v1th.get(k) == tcur[k]
           else "OTHER" for k in tcur}
    v2t2h = {}
    if state in ("v2", "v3", "v4", "v5"):                       # older zone-2 caves sit at their own addresses
        if state == "v2":
            import patch_bxl_ranged_abilities_v2 as V2
        elif state == "v3":
            import patch_bxl_ranged_abilities_v3 as V2
        elif state == "v4":
            import patch_bxl_ranged_abilities_v4 as V2
        else:
            import patch_bxl_ranged_abilities_v5 as V2
        _z2, v2w = V2.build_t2(prev_n26, prev_slt)
        v2t2h = {"cs": rel(0xE9, CS_SITE, v2w["cs"], 7), "hm": rel(0xE9, HM_SITE, v2w["hm"], 9),
                 "nf": rel(0xE9, NF_SITE, v2w["nf"], 6), "n26": rel(0xE8, N26_SITE, v2w["n26"], 5),
                 "slt": rel(0xE9, SLT_SITE, v2w["slt"], 7)}
    t2st = {k: "ours" if t2cur[k] == t2hook[k] else "orig" if t2cur[k] == t2sav[k] else state if v2t2h.get(k) == t2cur[k]
            else "OTHER" for k in t2cur}
    zst = lambda zl, z: ("zero" if not any(zl) else "ours" if zl[:len(z)] == z and not any(zl[len(z):])
                         else "v1" if zl[:4] == MAGIC_V1 else "v2" if zl[:4] == MAGIC_V2 else "v3" if zl[:4] == MAGIC_V3
                         else "v4" if zl[:4] == MAGIC_V4 else "v5" if zl[:4] == MAGIC_V5 else "DIFFERS")
    ezs, tzs, t2zs = zst(ezl, ezone), zst(tzl, tzone), zst(t2l, t2zone)
    er, tr = reloc_set(d, EBASE), reloc_set(t, TBASE)
    ebad = [hex(r) for r in er if EZONE - 3 <= r < EZONE_END or any(s - 3 <= r < s + 5 for s in (REG_SITE, VAL1_SITE, VAL2_SITE, BRCH_SITE))]
    tsites = [(SA_SITE, 6), (SB_SITE, 6), (SC_SITE, 7), (ABILTYPES + SKULL, 2)] + [(sc[0], 13) for sc in SCANS.values()]
    tsites += [(CS_SITE, 7), (HM_SITE, 9), (NF_SITE, 6), (N26_SITE, 5), (SLT_SITE, 7), (PV_SITE, 6)]
    tbad = [hex(r) for r in tr if TZONE - 3 <= r < TZONE_END or TZ2 - 3 <= r < TZ2_END or any(s - 3 <= r < s + n for s, n in tsites)]
    print("%s\n  state %s | AoWEPACK %s | zone %#x %s (%d B) | prev reg head %#x | relocs %s"
          % (a.dll, state, st, EZONE, ezs, len(ezone), prev_reg, ebad or "none"))
    print("%s\n  AoWTCPCK %s | zone %#x %s (%d B) | S2 prev %s" % (a.tcdll, tst, TZONE, tzs, len(tzone), hex(prev_s2) if prev_s2 else "vanilla"))
    print("  v2 sites %s | zone2 %#x %s (%d B) | N26 prev %#x | slot chain prev %#x | relocs %s"
          % (t2st, TZ2, t2zs, len(t2zone), prev_n26, prev_slt, tbad or "none"))
    print("  caves E " + ", ".join("%s=%#x" % kv for kv in ew.items()) + " | T " + ", ".join("%s=%#x" % kv for kv in tw.items())
          + " | T2 " + ", ".join("%s=%#x" % kv for kv in t2w.items()))
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        for z, va0, h in ((ezone, EZONE, EHDR), (tzone, TZONE, THDR), (t2zone, TZ2, T2HDR)):
            for i in md.disasm(z[h:], va0 + h): print("   %08X  %-24s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    allst = list(st.values()) + list(tst.values()) + list(t2st.values())
    if ebad or tbad or "OTHER" in allst or "DIFFERS" in (ezs, tzs, t2zs):
        print("ABORT"); return 1
    eo, to = bytearray(d), bytearray(t)
    eput = lambda va, b: eo.__setitem__(slice(va2off(d, va, EBASE), va2off(d, va, EBASE) + len(b)), b)
    tput = lambda va, b: to.__setitem__(slice(va2off(t, va, TBASE), va2off(t, va, TBASE) + len(b)), b)
    esites = {"reg": REG_SITE, "val1": VAL1_SITE, "val2": VAL2_SITE, "brch": BRCH_SITE}
    tsite = {"ab": ABILTYPES + SKULL, "sa": SA_SITE, "sb": SB_SITE, "sc": SC_SITE}
    for nm, sc in SCANS.items(): tsite[nm] = sc[0]
    t2site = {"cs": CS_SITE, "hm": HM_SITE, "nf": NF_SITE, "n26": N26_SITE, "slt": SLT_SITE, "pv": PV_SITE}
    if a.revert:
        if state == "none": print("nothing to revert"); return 0
        if state == "v1": print("v1 is installed - revert it with patch_bxl_ranged_abilities_v1.py --revert"); return 0
        if state == "v2": print("v2 is installed - revert it with patch_bxl_ranged_abilities_v2.py --revert"); return 0
        if state == "v3": print("v3 is installed - revert it with patch_bxl_ranged_abilities_v3.py --revert"); return 0
        if state == "v4": print("v4 is installed - revert it with patch_bxl_ranged_abilities_v4.py --revert"); return 0
        if state == "v5": print("v5 is installed - revert it with patch_bxl_ranged_abilities_v5.py --revert"); return 0
        for k, va in esites.items(): eput(va, sav[k])
        for k, va in tsite.items(): tput(va, tsav[k])
        for k, va in t2site.items(): tput(va, t2sav[k])
        eput(EZONE, bytes(EZONE_END - EZONE)); tput(TZONE, bytes(TZONE_END - TZONE)); tput(TZ2, bytes(TZ2_END - TZ2))
    else:
        if all(v == "ours" for v in allst) and ezs == tzs == t2zs == "ours":
            print("already applied"); return 0
        if state in ("v1", "v2", "v3", "v4", "v5"): print("  upgrading %s -> v6 in place" % state)
        eput(EZONE, ezone); tput(TZONE, tzone); tput(TZ2, t2zone)
        for k, va in esites.items(): eput(va, hook[k])
        for k, va in tsite.items(): tput(va, thook[k])
        for k, va in t2site.items(): tput(va, t2hook[k])
    print("  %d AoWEPACK bytes + %d AoWTCPCK bytes change" % (sum(1 for x, y in zip(d, eo) if x != y), sum(1 for x, y in zip(t, to) if x != y)))
    if not (a.apply or a.revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    for path, data, dflt in ((a.dll, eo, DEFAULT_DLL), (a.tcdll, to, DEFAULT_TC)):
        if os.path.abspath(path) == os.path.abspath(dflt) and not a.revert:
            bak = bak_path(path, BAK_SUFFIX)
            if not os.path.exists(bak): shutil.copy2(path, bak); print("backup ->", bak)
        write_inplace(path, bytes(data))
        assert open(path, "rb").read() == bytes(data)
    print("reverted (all v1 .. v6 sites restored, zones zeroed)" if a.revert else
          "Written and verified (v6: trail puff one path point behind the skull - the tail meets the head).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
