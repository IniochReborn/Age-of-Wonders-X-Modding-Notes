#!/usr/bin/env python3
r"""AoWx -- four hero abilities that cut the INITIAL CASTING COST of one spell
family each, + the vanilla instant-cast wallet bug fix they depend on.

ADOPTED 2026-08-31 from BXL/Ziggurat's build_caster_cost.py with AoWx re-tunes:
    Evoker    0xAC  combat spells        (30 classes)
    Conjurer  0xAD  summons              (13 + our Summon Mermaid = 14)
    Enchanter 0xAE  unit enchantments    (18, incl our Magic Sight)
    Ritualist 0xAF  ALL global spells    (user re-scope; BXL covered only the
                    12 global enchantments -- ours also catches the 13
                    global-target spells, 6 storms, 9 city spells and the 8
                    hero/special globals, via else-classification)

DISCOUNT (user formula, replaces BXL's 50%): newCost = cost - (cost+1)/3
(integer div) -- 1->1, 2->1, 3->2, 4->3, 5->3, 6->4, 7->5, 8->5, 9->6, 10->7.
Free spells stay free; every cost >=2 drops by at least 1; result never
reaches 0. (User's example said 8->6; every closed form fitting the other
nine gives 8->5 -- flagged, assumed a slip.) Applied BEFORE vanilla's
inline off-sphere x2 (GetSphereManaDoubled path, which our build keeps --
we have no mastery_cost mod, so BXL's floor hook and cave-interplay notes
do not apply and HOOK2 is dropped).

CLASSIFICATION (BXL's rebase-invariant VMT-slot-difference trick, verified
against OUR dll by a full TSpell-subtree walk 2026-08-31):
    d = [spellVMT+0x6C](Activate) - [spellVMT+0x18](ReadWrite)
    d == 0x6B27C -> summon family; d == 0x1FF4 -> unit-ench family;
    d == 0x120   -> combat IF ALSO [VMT+0x80]-[VMT+0x18] == 0x7E034
                    (else it is the abstract TSpell -> no discount);
    anything else -> GLOBAL (every remaining subtree family: gench 0x767E0,
    gtarget 0x255B0, city 0x37818, storm 0x54AEC, singletons 0x714xx..0x744xx)
    -- future-proof: any new global spell class lands on Ritualist.

WALLET FIX (vanilla bug, sites byte-identical in our dll): THero.CastSpell's
instant branch charges the RAW [spell+0x14] and TSpellTE.Validate re-checks
raw, bypassing THero.CastingMana entirely -- so discounts (and vanilla's own
off-sphere doubling) never reached the wallet, and in the band
discounted <= points < raw the cast silently no-oped. Three re-routes:
    SITE A TGlobalEnchantmentSpell.Activate @0x557EFA7C -> cave_gench
    SITE B TSummonSpell.Activate            @0x557E44F8 -> cave_summon
    SITE C TSummonSpellTE.Process           @0x557E4353 in place:
           push [TE+0x1C] (the stored computed cost) instead of raw
Behavioral note: vanilla's off-sphere x2 now genuinely charges on
instantly-cast summons/genches (display == charge for the first time).

REGISTRATION: HOOK3 splices a spare `call RegisterAbility` @0x557BCF04 ->
cave_reg: registers the four via CreateEnhancementAbility(id, name, mask
0x3FF) -- names are in-cave Delphi AnsiString literals (refcount -1).
Level-up cost lives in Ability.pfs tag 6 (= 15, minted by
patch_ability_pfs_castercost.py) -- writing [ability+0x14] in the cave is
FUTILE (the pfs load overwrites it; BXL's hard lesson) and is omitted.

Caves: 0x55814F00..0x55815100 (verified zero; next free after this =
0x55815100). cave_cost is fully register/relative (the classification is a
slot DIFFERENCE so rebase cancels; the replay bytes are the originals).
cave_reg uses call/pop PIC anchors for the name literals.

Ability ids 0xAC-0xAF verified free (Ability.pfs tops at 0xAA; our custom
abilities 0x9F/0x46-0x4D/0xAA don't clash).

Usage: dry run default; --apply; --revert (surgical).
"""
import os
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.environ.get("AOW_GAME_DIR") or os.path.dirname(HERE)
DLL = os.path.join(GAME, "AoWEPACK.dll")
BAK = DLL + ".bak_castercost"

D = 0x55700C00

CASTINGMANA = 0x557894EC
CM_RESUME = 0x557894F3
REG_SPLICE = 0x557BCF04
REGISTERAB = 0x55750238
CREATEENH = 0x5576601C
GENCH_ACT = 0x557EFA7C
GENCH_RESUME = 0x557EFA83
SUMMON_ACT = 0x557E44F8
SUMMON_RESUME = 0x557E44FF
SUMMONTE_PROC = 0x557E4353

EVOKER, CONJURER, ENCHANTER, RITUALIST = 0xAC, 0xAD, 0xAE, 0xAF
ORDER = [EVOKER, CONJURER, ENCHANTER, RITUALIST]
NAMES = {EVOKER: "Evoker", CONJURER: "Conjurer",
         ENCHANTER: "Enchanter", RITUALIST: "Ritualist"}
SEL_MASK = 0x03FF

D_SUMMON = 0x0006B27C
D_UNIT = 0x00001FF4
D_COMBAT_PRE = 0x00000120
D_COMBAT_CFM = 0x0007E034

CAVE_COST = 0x55814F00
CAVE_GENCH = 0x55814F80
CAVE_SUMMON = 0x55814FA0
CAVE_REG = 0x55814FC0
ZONE_HI = 0x55815100

ORIG = {
    CASTINGMANA: bytes.fromhex("53568bf28b5e14"),
    REG_SPLICE: bytes.fromhex("e82f33f9ff"),
    GENCH_ACT: bytes.fromhex("8b4314508a4e24"),
    SUMMON_ACT: bytes.fromhex("8b4314508b45fc"),
    SUMMONTE_PROC: bytes.fromhex("8b4014508b45fc"),
}
SITEC_NEW = bytes.fromhex("8b45fcff701c90")   # mov eax,[ebp-4]; push [eax+0x1C]; nop


def asm(src, addr):
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    src = "\n".join(ln.split(";")[0] for ln in src.splitlines())
    code, _ = Ks(KS_ARCH_X86, KS_MODE_32).asm(src, addr)
    return bytearray(code)


def rel(src, dst):
    return struct.pack("<i", dst - (src + 5))


def make_cost():
    body_at = CAVE_COST + len(ORIG[CASTINGMANA])
    src = f"""
        test eax, eax
        jz   _back
        mov  ecx, [eax]
        cmp  [ecx-0x40], ecx
        jnz  _back
        mov  ecx, [esi]
        mov  edx, [ecx+0x6C]
        sub  edx, [ecx+0x18]
        cmp  edx, 0x{D_SUMMON:X}
        je   _conj
        cmp  edx, 0x{D_UNIT:X}
        je   _ench
        cmp  edx, 0x{D_COMBAT_PRE:X}
        jne  _ritu
        mov  edx, [ecx+0x80]
        sub  edx, [ecx+0x18]
        cmp  edx, 0x{D_COMBAT_CFM:X}
        jne  _back
        mov  edx, {EVOKER}
        jmp  _q
    _conj:
        mov  edx, {CONJURER}
        jmp  _q
    _ench:
        mov  edx, {ENCHANTER}
        jmp  _q
    _ritu:
        mov  edx, {RITUALIST}
    _q:
        mov  ecx, [eax]
        call dword ptr [ecx+0x148]
        test al, al
        jz   _back
        lea  eax, [ebx+1]
        xor  edx, edx
        mov  ecx, 3
        div  ecx
        sub  ebx, eax
    _back:
        jmp  0x{CM_RESUME:X}
    """
    return ORIG[CASTINGMANA] + bytes(asm(src, body_at))


def make_gench():
    src = f"""
        mov  eax, esi
        mov  edx, ebx
        call 0x{CASTINGMANA:X}
        push eax
        mov  cl, [esi+0x24]
        jmp  0x{GENCH_RESUME:X}
    """
    return bytes(asm(src, CAVE_GENCH))


def make_summon():
    src = f"""
        mov  eax, [ebp-4]
        mov  edx, ebx
        call 0x{CASTINGMANA:X}
        push eax
        mov  eax, [ebp-4]
        jmp  0x{SUMMON_RESUME:X}
    """
    return bytes(asm(src, CAVE_SUMMON))


REG_BLOCK = 36     # call$+5(5) pop(1) lea(6) mov ecx(5) mov eax(5) call(5)
                   # mov edx,eax(2) mov eax,ebx(2) call(5) = 36


def make_reg():
    va = CAVE_REG
    lit_start = va + 5 + REG_BLOCK * len(ORDER) + 1
    lits, name_at, addr = bytearray(), {}, lit_start
    for i in ORDER:
        nm = NAMES[i].encode("ascii")
        name_at[i] = addr + 8
        lits += b"\xff\xff\xff\xff" + struct.pack("<I", len(nm)) + nm + b"\x00"
        addr += 9 + len(nm)

    buf = bytearray()
    buf += b"\xE8" + struct.pack("<i", REGISTERAB - (va + len(buf) + 5))
    for i in ORDER:
        start = len(buf)
        buf += b"\xE8\x00\x00\x00\x00"                       # call $+5
        anchor = va + len(buf)                               # = addr of pop eax
        buf += b"\x58"                                       # pop eax
        buf += b"\x8D\x90" + struct.pack("<i", name_at[i] - anchor)  # lea edx,[eax+d]
        buf += b"\xB9" + struct.pack("<I", SEL_MASK)         # mov ecx, mask
        buf += b"\xB8" + struct.pack("<I", i)                # mov eax, id
        buf += b"\xE8" + struct.pack("<i", CREATEENH - (va + len(buf) + 5))
        buf += b"\x89\xC2"                                   # mov edx, eax
        buf += b"\x89\xD8"                                   # mov eax, ebx
        buf += b"\xE8" + struct.pack("<i", REGISTERAB - (va + len(buf) + 5))
        assert len(buf) - start == REG_BLOCK, len(buf) - start
    buf += b"\xC3"
    assert va + len(buf) == lit_start, (hex(va + len(buf)), hex(lit_start))
    buf += lits
    # verify each lea lands on the string bytes of a well-formed literal
    p = 5
    for i in ORDER:
        anchor = va + p + 5
        assert buf[p + 5] == 0x58 and buf[p + 6:p + 8] == b"\x8D\x90"
        disp = struct.unpack_from("<i", buf, p + 8)[0]
        k = anchor + disp - va
        nm = NAMES[i].encode("ascii")
        assert buf[k - 8:k - 4] == b"\xff\xff\xff\xff"
        assert struct.unpack_from("<I", buf, k - 4)[0] == len(nm)
        assert buf[k:k + len(nm)] == nm and buf[k + len(nm)] == 0
        p += REG_BLOCK
    return bytes(buf)


def main():
    apply = "--apply" in sys.argv
    revert = "--revert" in sys.argv
    d = bytearray(open(DLL, "rb").read())
    cc, cg, cs, cr = make_cost(), make_gench(), make_summon(), make_reg()
    assert CAVE_COST + len(cc) <= CAVE_GENCH, len(cc)
    assert CAVE_GENCH + len(cg) <= CAVE_SUMMON, len(cg)
    assert CAVE_SUMMON + len(cs) <= CAVE_REG, len(cs)
    assert CAVE_REG + len(cr) <= ZONE_HI, len(cr)

    edits = [
        (CAVE_COST, bytes(len(cc)), cc, "cave_cost (classify + discount)"),
        (CAVE_GENCH, bytes(len(cg)), cg, "cave_gench (wallet fix A)"),
        (CAVE_SUMMON, bytes(len(cs)), cs, "cave_summon (wallet fix B)"),
        (CAVE_REG, bytes(len(cr)), cr, "cave_reg (4 abilities)"),
        (CASTINGMANA, ORIG[CASTINGMANA],
         b"\xE9" + rel(CASTINGMANA, CAVE_COST) + b"\x90\x90",
         "HOOK1 CastingMana entry"),
        (REG_SPLICE, ORIG[REG_SPLICE],
         b"\xE8" + rel(REG_SPLICE, CAVE_REG), "HOOK3 register splice"),
        (GENCH_ACT, ORIG[GENCH_ACT],
         b"\xE9" + rel(GENCH_ACT, CAVE_GENCH) + b"\x90\x90",
         "SITE A gench Activate"),
        (SUMMON_ACT, ORIG[SUMMON_ACT],
         b"\xE9" + rel(SUMMON_ACT, CAVE_SUMMON) + b"\x90\x90",
         "SITE B summon Activate"),
        (SUMMONTE_PROC, ORIG[SUMMONTE_PROC], SITEC_NEW, "SITE C summonTE charge"),
    ]
    states = []
    for va, ob, nb, nm in edits:
        c = bytes(d[va - D:va - D + len(nb)])
        st = "original" if c == ob else "applied" if c == nb else "FOREIGN"
        states.append(st)
        print("  %-34s @0x%08X  %s (%d B)" % (nm, va, st, len(nb)))
    if "FOREIGN" in states:
        print("FOREIGN - refusing")
        return 1
    if revert:
        for va, ob, nb, _ in edits:
            d[va - D:va - D + len(nb)] = ob
        open(DLL, "wb").write(bytes(d))
        print("reverted")
        return 0
    if not apply:
        print("dry run (--apply / --revert)")
        return 0
    if all(s == "applied" for s in states):
        print("already applied")
        return 0
    if not os.path.isfile(BAK):
        shutil.copy2(DLL, BAK)
        print("backed up")
    for va, ob, nb, _ in edits:
        d[va - D:va - D + len(nb)] = nb
    open(DLL, "wb").write(bytes(d))
    print("APPLIED - run patch_ability_pfs_castercost.py --apply next (level "
          "costs), then test: hero with Conjurer sees summon costs cut by a "
          "third (5->3 etc) in the book AND is charged that; Ritualist "
          "discounts EVERY global spell (enchantments, Freeze Water, storms, "
          "Town Gate, Resurrect Hero...); no ability -> vanilla costs; "
          "1-cost spells stay 1; instant casts charge the displayed price")
    return 0


if __name__ == "__main__":
    sys.exit(main())
