"""
STEAM POWER (spell 406, Fire/Water sphere pair 22, tier 3) - global enchantment (2026-10-14).  AoWEPACK.dll only.

Spec (user): global spell, research 100, cost 50, upkeep 8.  Double income from Builder's Guilds; all Construct ability
actions are 50 % cheaper and take one turn less (minimum one turn).

DONOR = Fire Mastery (TFireMastery: spell class cell 0x557EF1E8, Create 0x557F2E5C, registered @0x557F3A99 in the
global-spell loop).  Water Mastery is already Drought's donor (its CE/AC/DA/EX sites are hooked by patch_drought_v1.py
for marker 391), so Steam Power clones Fire Mastery and neutralises ITS mastery side effects for marker 406:
  CE  TFireMastery.CreateEnchantment 0x557F2F10 (spell VMT+0xA0; eax = spell): `jmp cave` (5 B; the reloc'd class-cell
      operand behind it becomes dead code, reloc left alone).  The cave replays it (TFireMasteryEnchantment.Create
      0x557F2A18 with the cell 0x557EF0C0 read PIC) and for [spell+0x10] == 406 writes the MARKER [ench+0x14] := 406
      (the serialised dword the ctor sets to 0xAF; tag 0xF -> survives saves) and copies the spell name [spell+8] into
      [ench+0x1C] (System.@LStrAsg thunk 0x55701150, import-checked) - the ctor hardcodes "Fire Mastery" there.
  AC/DE  TFireMasteryEnchantment VMT 0x557EF100 slots +0x68 Activate 0x557F2B84 / +0x60 Deactivate 0x557F2C3C
      (DoubleSphereMana counter 6, the player's magic flag 0x40 [pmc+0x44], a refresh of every unit of every army,
      world update 0x557F2CDC) -> VMT slots re-pointed to caves: marker 406 -> tail-jump to the BASE
      TGlobalEnchantment.Activate 0x5577DBA0 / Deactivate 0x5577DC3C (they set the active bit / caster [ench+0x19] /
      upkeep and return al = 1); anything else -> the Fire Mastery originals.
  CHK slot +0x64 0x557F2AC0 ("already active" check, reached from the cast validation 0x557EF938 through a TEMPORARY
      enchantment made by CreateEnchantment -> it carries our marker): marker 406 -> our own once-per-player test
      (an ACTIVE 406 enchantment cast by this player = refused through Fire Mastery's own message branch 0x557F2B02,
      entered after replaying its prologue, so the text is "<enchantment name> is already active" with our copied
      name; otherwise allowed - Fire Mastery's bit 0x40 is NOT consulted, so an active Fire Mastery doesn't block it).
  MM  TFireMastery.ExecuteTE 0x557F3120 phase 0 `call 0x557EF7C0` @0x557F314F (the sphere mastery message, dl = 5) ->
      call cave: skipped for spell 406 (esi = spell), else tail-jump to the original.
  Kept from the donor: the event-log line, sound 0 of the spell record, and the map-wide animation (paint proc
  0x557F2F20 draws the CAST SPELL's own gfx slot 0 ([anim+0x28] = spell -> [spell+0x2C] list) on random visible
  hexes, plus the global fire-crackle ambience sounds per hex - Steam Power's record slot 0 decides the look); the
  cast happens at phase 0x14 when the animation ends (0x557EF91C -> ench VMT+0x70 Cast with dl = TE player [te+0x24]).

'Is Steam Power active for player P' (sp_active, dl = P): scan TGlobalMagicControl [[AoWHSMap 0x558FA040]+0x188]
list +0x14 (Count = list VMT+0x54, Get 0x5577E13C) for an enchantment with bit0 of [e+0x10] (active), [e+0x14] == 406
and caster [e+0x19] == P.  P = player-list index (structure owner [obj+0x30], army owner [army+0x24], road builder idx)
- the same numbering the caster byte uses (Activate stores the TE's player byte; GetPlayer 0x557544D0 = list index).
Synced game state only -> MP-safe, no RNG.

EFFECT 1 - Builder's Guild income x2:
  Every TProductionPlace (nodes, shipyard, builders guild) reports its per-turn production through VMT+0x1F4 =
  0x557BE500 (base 5 from VMT+0x22C, x1.5 in one case).  The player's income sources call it through
  TPlayerStructureIncomeSource.Income 0x55761AF8 (`call [edx+0x1F4]`) - the real per-turn payout - and the treasury
  line BuildersGuildIncome 0x557CA514 (exe @0x449177) sums the same.  Hook = the VMT slot of TBuildersGuild
  (0x557CA0DC + 0x1F4 = 0x557CA2D0) -> cave: call the original, x2 when the owner [obj+0x30] has Steam Power.
  DOUBLE_SHIPYARDS: the mod's ClassID cave 0x5580D780 counts TShipyard (ClassID 0x204BE) as a Builder's Guild in that
  treasury line, so the Shipyard slot (0x557C715C + 0x1F4 = 0x557C7350) is hooked too (set False to leave it).
  VMT slots carry type-3 relocs: we store the cave's PREFERRED-base VA and the loader rebases it like the original.

EFFECT 2 - Construct ability (0x7D) actions -50 % cost (rounded up), -1 turn (min 1):
  The ability's action list ([ability+0x28]) holds TRebuildConstructionControl, TBuildRoadsControl,
  TTowerConstructionControl (50 gold / 2 turns) and TShipyardConstructionControl (50 / 3).  VMT+0x4C =
  GetCostInfo(eax action, edx army, ecx &name; push &cost, push &turns; ret 8) feeds BOTH the construction TE
  0x55761E40 (charges [player+0xC4] -= cost, structure VMT+0x1A4(turns)) and the exe construct menu (0x43176A).
  Hooked VMT slots: Tower 0x557C3578, Shipyard 0x557C7558, Rebuild 0x55770A74 (Roads reports 0/0 - charged per tile).
  REBUILD itself runs through structure VMT+0x1E4 (TPlayerStructure.StartRebuild) whose costs come from structure
  VMT+0x1DC (base 0x5575F18C: cost 50, turns [res+0x5B]): call sites hooked RA 0x5575EF45 (charge + [obj+0x25] :=
  turns) and RB 0x5575F1EC (affordability); army = esi in both.
  ROADS: per-tile charge in the road-construct routine 0x55771068: RD 0x557710ED (9 B `mov eax,[eax+0xC4] / sub eax,
  ebx / nop`; ebx = tile cost from the July road-cost caves, esi = player index) -> tile cost halved (rounded up);
  the cost PREVIEW 0x55771138 adds tiles through `call 0x5580F790` (cave_pred) @0x55771195 -> RP: our own adder
  (same stack frame: player byte [caller esp], total [caller esp+4], field [caller esp+8]) calling the July
  classifier cave_roadcost 0x5580F700 and halving per tile the same way, so preview == charge.
  Roads are instant (no turns).

Zone 0x5585C000..0x5585E000 (zero, reloc-free; PIC via call/pop delta for every in-image absolute).
Dry-run default; --apply / --revert / --dis.  Backup <game>\\backup\\AoWEPACK.dll.bak_steampower.
Pipeline entry (patch_dual_sphere_spells_v1.py): donor "TFireMastery": (0x557EF1E8, 0x557F2E5C) (site 0x557F3A99),
pfs_donor = Fire Mastery's Spells.pfs key, tc_type None, sphere 22, tier 3, mana 50, research 100, upkeep 8.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DLL = game_file("AoWEPACK.dll")
BASE, CODE_V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x5585C000, 0x5585E000
SPELL_ID = 406
DOUBLE_SHIPYARDS = True

MAP_GLOBAL, LIST_GET = 0x558FA040, 0x5577E13C
BASE_ACT, BASE_DEACT = 0x5577DBA0, 0x5577DC3C
FM_ACT, FM_DEACT, FM_CHK, FM_CHK_MSG, FM_CHK_SEH = 0x557F2B84, 0x557F2C3C, 0x557F2AC0, 0x557F2B02, 0x557F2B74
FM_ENCH_CREATE, FM_ENCH_CELL = 0x557F2A18, 0x557EF0C0
MASTERY_MSG, LSTRASG = 0x557EF7C0, 0x55701150
PROD_INCOME = 0x557BE500
ROADCOST = 0x5580F700
ORIG_4C = {"tower": 0x557C381C, "ship": 0x557C76D0, "rebuild": 0x55770BBC}

# code sites: name -> (va, original bytes, kind)  kind: 'jmp' = jmp cave + nops, 'call' = call cave + nops
CODE_SITES = {
    "CE": (0x557F2F10, bytes.fromhex("33c9b201a1"), "jmp"),
    "MM": (0x557F314F, bytes.fromhex("e86cc6ffff"), "call"),
    "RA": (0x5575EF45, bytes.fromhex("ff97dc010000"), "call"),
    "RB": (0x5575F1EC, bytes.fromhex("ff93dc010000"), "call"),
    "RD": (0x557710ED, bytes.fromhex("8b80c40000002bc390"), "call"),
    "RP": (0x55771195, bytes.fromhex("e8f6e50900"), "call"),
    # v3: the Fire Mastery map animation's per-hex sound (paint proc 0x557F2F20, [ebp-4] = the cast spell): vanilla
    # `call Sound.PlaySample` with AoWE.ExplosionSFX[0x558E8030][hex parity] = the "explosive" sound -> for spell 406
    # TSFXLibrary.Play(spell sound list [spell+0x28], ID 1) = Steam Power's own cue 1 instead.
    "SX": (0x557F30E5, bytes.fromhex("e81afcf0ff"), "call"),
}
# VMT slots: name -> (slot va, original dword, cave name)
VMT_SLOTS = {
    "fmAct":   (0x557EF168, FM_ACT, "ac"),
    "fmDeact": (0x557EF160, FM_DEACT, "de"),
    "fmChk":   (0x557EF164, FM_CHK, "chk"),
    "guild":   (0x557CA2D0, PROD_INCOME, "gi"),
    "tower4C": (0x557C3578, ORIG_4C["tower"], "s4c_tower"),
    "ship4C":  (0x557C7558, ORIG_4C["ship"], "s4c_ship"),
    "reb4C":   (0x55770A74, ORIG_4C["rebuild"], "s4c_rebuild"),
}
if DOUBLE_SHIPYARDS:
    VMT_SLOTS["shipyard"] = (0x557C7350, PROD_INCOME, "gi")
# v2 (2026-10-14, user: "productions in Builder's Guilds and Shipyards take one less turn (minimum one turn)"):
# TProductionPlaceControl (VMT 0x557BD4D0, child of TProductionControl; the production control of every production
# place - [ctl+0x28] = the structure) VMT+0xD4 GetProductionTime = 0x557BDB24 (unit build time, already halved by the
# owner's builder bonus and clamped >= 1; returns an int).  TProductionControl.ExecuteProduction 0x5575D118 stores it
# in the state object (+0x1C total, +0x10 = the turn countdown NewTurn 0x5575DD00 decrements); the production menu
# reads the same getter.  Wrapped: ClassID (structure VMT+0x24) 0x2092E Builder's Guild / 0x204BE Shipyard, owner
# [structure+0x30] has Steam Power and time > 1 -> time - 1.
PROD_TIME = 0x557BDB24
SFX_PLAY, PLAY_SAMPLE = 0x55702CF4, 0x55702D04     # Sound.TSFXLibrary.Play (eax list, edx cue ID) / Sound.PlaySample (eax sample) - import-checked
CLS_GUILD, CLS_SHIPYARD = 0x2092E, 0x204BE
VMT_SLOTS["prodTime"] = (0x557BD5A4, PROD_TIME, "pt")

ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm_pic(src, va):
    """Assemble; every `call $D` / `pop R` / `sub R, $D` triple gets the anchor (the VA after the call) patched in."""
    s1 = src.replace("call $D", ".byte 0xe8, 0, 0, 0, 0")
    for r in ("eax", "ebx", "ecx", "edx", "esi", "edi", "ebp"):
        s1 = s1.replace("sub %s, $D" % r, "sub %s, 0x7fffffff" % r)
    b = bytearray(ks.asm(s1, va)[0])
    k = 0
    while True:
        k = b.find(b"\xe8\x00\x00\x00\x00", k)
        if k < 0: break
        if 0x58 <= b[k + 5] <= 0x5F:
            if b[k + 6] == 0x2D and b[k + 7:k + 11] == b"\xff\xff\xff\x7f":
                struct.pack_into("<I", b, k + 7, va + k + 5)
            elif b[k + 6] == 0x81 and b[k + 8:k + 12] == b"\xff\xff\xff\x7f":
                struct.pack_into("<I", b, k + 8, va + k + 5)
        k += 5
    assert b"\xff\xff\xff\x7f" not in b, "unpatched PIC anchor"
    return bytes(b)


def build():
    out = bytearray(); where = {}
    def place(name, src, pic=False):
        while len(out) % 16: out.append(0)
        va = ZONE + len(out); where[name] = va
        code = asm_pic(src % dict(C, **where), va) if pic else bytes(ks.asm(src % dict(C, **where), va)[0])
        out.extend(code)
    C = {"id": SPELL_ID, "map": MAP_GLOBAL, "get": LIST_GET, "bact": BASE_ACT, "bdeact": BASE_DEACT, "fmact": FM_ACT,
         "fmdeact": FM_DEACT, "fmchk": FM_CHK, "fmmsg": FM_CHK_MSG, "fmseh": FM_CHK_SEH, "fmcreate": FM_ENCH_CREATE,
         "fmcell": FM_ENCH_CELL, "mmsg": MASTERY_MSG, "ptime": PROD_TIME, "cg": CLS_GUILD, "cs": CLS_SHIPYARD, "sfxplay": SFX_PLAY, "playsample": PLAY_SAMPLE, "lstrasg": LSTRASG, "income": PROD_INCOME, "roadcost": ROADCOST}
    C.update({"o_" + k: v for k, v in ORIG_4C.items()})
    clash = set(C) & {"spa", "ce", "mm", "ac", "de", "chk", "gi", "adjt", "adjc", "adj4c", "ra", "rb", "rd", "rp", "pt", "sx"}
    assert not clash, clash   # a constant key equal to a cave name would be silently overridden by dict(C, **where)
    # sp_active: dl = player index -> al = 1 if that player has an ACTIVE Steam Power; all other regs preserved
    place("spa", """
        push ebx
        push ecx
        push edx
        push esi
        push edi
        movsx edi, dl
        call $D
        pop ebx
        sub ebx, $D
        mov eax, [ebx+%(map)#x]
        test eax, eax
        jz spa_no
        mov eax, [eax+0x188]
        test eax, eax
        jz spa_no
        mov esi, [eax+0x14]
        test esi, esi
        jz spa_no
        mov eax, esi
        mov edx, [eax]
        call dword ptr [edx+0x54]
        mov ecx, eax
    spa_lp:
        dec ecx
        js spa_no
        push ecx
        mov eax, esi
        mov edx, ecx
        call %(get)#x
        pop ecx
        test eax, eax
        jz spa_lp
        cmp dword ptr [eax+0x14], %(id)d
        jne spa_lp
        test byte ptr [eax+0x10], 1
        jz spa_lp
        movsx edx, byte ptr [eax+0x19]
        cmp edx, edi
        jne spa_lp
        mov eax, 1
        jmp spa_out
    spa_no:
        xor eax, eax
    spa_out:
        pop edi
        pop esi
        pop edx
        pop ecx
        pop ebx
        ret
    """, pic=True)
    # CE: replayed CreateEnchantment + marker + name (jmp'ed to; eax = spell)
    place("ce", """
        push eax
        push ebx
        call $D
        pop ebx
        sub ebx, $D
        mov eax, [ebx+%(fmcell)#x]
        pop ebx
        xor ecx, ecx
        mov dl, 1
        call %(fmcreate)#x
        pop edx
        cmp dword ptr [edx+0x10], %(id)d
        jne ce_done
        mov dword ptr [eax+0x14], %(id)d
        push eax
        lea eax, [eax+0x1c]
        mov edx, [edx+8]
        call %(lstrasg)#x
        pop eax
    ce_done:
        ret
    """, pic=True)
    place("mm", """
        cmp dword ptr [esi+0x10], %(id)d
        je mm_skip
        jmp %(mmsg)#x
    mm_skip:
        ret
    """)
    place("ac", """
        cmp dword ptr [eax+0x14], %(id)d
        je ac_ours
        jmp %(fmact)#x
    ac_ours:
        jmp %(bact)#x
    """)
    place("de", """
        cmp dword ptr [eax+0x14], %(id)d
        je de_ours
        jmp %(fmdeact)#x
    de_ours:
        jmp %(bdeact)#x
    """)
    # CHK: eax = ench, edx (dl) = player, ecx = &message; returns al (1 = may cast)
    place("chk", """
        cmp dword ptr [eax+0x14], %(id)d
        je chk_ours
        jmp %(fmchk)#x
    chk_ours:
        push eax
        call %(spa)#x
        test al, al
        pop eax
        jnz chk_refuse
        mov eax, 1
        ret
    chk_refuse:
        push ebp
        mov ebp, esp
        push 0
        push 0
        push 0
        push 0
        push 0
        push ebx
        push esi
        push edi
        mov edi, ecx
        mov ebx, edx
        mov esi, eax
        call $D
        pop eax
        sub eax, $D
        add eax, %(fmseh)#x
        push ebp
        push eax
        xor eax, eax
        push dword ptr fs:[eax]
        mov dword ptr fs:[eax], esp
        jmp %(fmmsg)#x
    """, pic=True)
    # guild / shipyard income (VMT+0x1F4, eax = structure)
    place("gi", """
        push ebx
        mov ebx, eax
        call %(income)#x
        test eax, eax
        jle gi_out
        push edx
        push eax
        mov dl, byte ptr [ebx+0x30]
        call %(spa)#x
        test al, al
        pop eax
        pop edx
        jz gi_out
        shl eax, 1
    gi_out:
        pop ebx
        ret
    """)
    # helpers: eax = pointer
    place("adjt", """
        push ecx
        mov ecx, [eax]
        cmp ecx, 1
        jle adjt_r
        dec ecx
        mov [eax], ecx
    adjt_r:
        pop ecx
        ret
    """)
    place("adjc", """
        push ecx
        mov ecx, [eax]
        test ecx, ecx
        jle adjc_r
        inc ecx
        shr ecx, 1
        mov [eax], ecx
    adjc_r:
        pop ecx
        ret
    """)
    # GetCostInfo wrapper tail: edx = army, [esp+4] = &turns, [esp+8] = &cost; returns with ret 8
    place("adj4c", """
        pushal
        cmp edx, 0x10000
        jb a4_done
        mov dl, byte ptr [edx+0x24]
        call %(spa)#x
        test al, al
        jz a4_done
        mov eax, [esp+0x24]
        call %(adjt)#x
        mov eax, [esp+0x28]
        call %(adjc)#x
    a4_done:
        popal
        ret 8
    """)
    for nm in ("tower", "ship", "rebuild"):
        place("s4c_" + nm, """
        push edx
        push dword ptr [esp+0xc]
        push dword ptr [esp+0xc]
        call %%(o_%s)#x
        pop edx
        jmp %%(adj4c)#x
        """ % nm)
    # rebuild cost sites: edx = &cost, ecx = &turns, esi = army; VMT in edi (RA) / ebx (RB)
    for nm, reg in (("ra", "edi"), ("rb", "ebx")):
        place(nm, """
        push edx
        push ecx
        call dword ptr [%s+0x1dc]
        pop ecx
        pop edx
        pushal
        mov dl, byte ptr [esi+0x24]
        call %%(spa)#x
        test al, al
        jz r_done
        mov eax, [esp+0x18]
        call %%(adjt)#x
        mov eax, [esp+0x14]
        call %%(adjc)#x
    r_done:
        popal
        ret
        """ % reg)
    # road charge: replay `mov eax,[eax+0xC4]`, halve the tile cost ebx when the builder (esi = player idx) has it
    place("rd", """
        mov eax, [eax+0xc4]
        push eax
        mov edx, esi
        call %(spa)#x
        test al, al
        pop eax
        jz rd_s
        inc ebx
        shr ebx, 1
    rd_s:
        sub eax, ebx
        ret
    """)
    # road preview adder (replaces `call cave_pred`): [esp+4] player byte, [esp+8] total, [esp+0xC] field
    place("rp", """
        push eax
        push edx
        mov eax, [esp+0x14]
        call %(roadcost)#x
        push eax
        mov dl, byte ptr [esp+0x10]
        call %(spa)#x
        test al, al
        pop eax
        jz rp_a
        inc eax
        shr eax, 1
    rp_a:
        add [esp+0x10], eax
        pop edx
        pop eax
        ret
    """)
    # v2: production time of Builder's Guild / Shipyard productions (VMT+0xD4 of TProductionPlaceControl; eax = control,
    # edx = item).  Placed LAST so the v1 caves keep their addresses.
    place("pt", """
        push ebx
        mov ebx, eax
        call %(ptime)#x
        push eax
        mov ecx, [ebx+0x28]
        test ecx, ecx
        jz pt_out
        push ecx
        mov eax, ecx
        mov edx, [eax]
        call dword ptr [edx+0x24]
        pop ecx
        cmp eax, %(cg)#x
        je pt_ok
        cmp eax, %(cs)#x
        jne pt_out
    pt_ok:
        mov dl, byte ptr [ecx+0x30]
        call %(spa)#x
        test al, al
        jz pt_out
        cmp dword ptr [esp], 1
        jle pt_out
        dec dword ptr [esp]
    pt_out:
        pop eax
        pop ebx
        ret
    """)
    # v3: per-hex sound of the map animation (eax = ExplosionSFX sample); placed last - earlier caves keep their VAs
    place("sx", """
        mov edx, [ebp-4]
        test edx, edx
        jz sx_van
        cmp dword ptr [edx+0x10], %(id)d
        jne sx_van
        mov eax, [edx+0x28]
        test eax, eax
        jz sx_skip
        mov edx, 1
        jmp %(sfxplay)#x
    sx_skip:
        ret
    sx_van:
        jmp %(playsample)#x
    """)
    assert ZONE + len(out) <= ZONE_END, hex(ZONE + len(out))
    return bytes(out), where


def relocs(d):
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
            if e >> 12 == 3: out.add(BASE + page + (e & 0xFFF))
        p += size
    return out


def vaoff(va):
    return va - CODE_V2F


def data_off(d, va):
    """file offset of any VA (VMT slots live in CODE here, but resolve through the section table to be safe)"""
    pe = struct.unpack_from("<I", d, 0x3C)[0]; opt = struct.unpack_from("<H", d, pe + 20)[0]; nsec = struct.unpack_from("<H", d, pe + 6)[0]
    rva = va - BASE
    for k in range(nsec):
        vs, sva, rs, ro = struct.unpack_from("<IIII", d, pe + 24 + opt + 40 * k + 8)
        if sva <= rva < sva + max(vs, rs): return ro + rva - sva
    raise ValueError(hex(va))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true"); ap.add_argument("--dis", action="store_true"); a = ap.parse_args()
    d = bytearray(open(DLL, "rb").read())
    code, where = build()
    rl = relocs(bytes(d))
    zl = bytes(d[vaoff(ZONE):vaoff(ZONE_END)])
    zstate = "zero" if not any(zl) else "ours" if zl[:len(code)] == code and not any(zl[len(code):]) else "DIFFERS"
    hooks, cstate = {}, {}
    for nm, (va, orig, kind) in CODE_SITES.items():
        tgt = where[nm.lower()]
        h = (b"\xe9" if kind == "jmp" else b"\xe8") + struct.pack("<i", tgt - (va + 5)) + b"\x90" * (len(orig) - 5)
        hooks[nm] = h
        live = bytes(d[vaoff(va):vaoff(va) + len(orig)])
        old = live[0] in (0xE8, 0xE9) and ZONE <= va + 5 + struct.unpack_from("<i", live, 1)[0] < ZONE_END and all(b == 0x90 for b in live[5:])
        cstate[nm] = "vanilla" if live == orig else "ours" if live == h else "ours(old)" if old else "OTHER"
    vstate = {}
    for nm, (sva, orig, cave) in VMT_SLOTS.items():
        live = struct.unpack_from("<I", d, data_off(d, sva))[0]
        vstate[nm] = ("vanilla" if live == orig else "ours" if live == where[cave] else "ours(old)" if ZONE <= live < ZONE_END
                      else "OTHER(%#x)" % live)
    bad = [hex(r) for r in rl if ZONE <= r < ZONE_END or any(va <= r < va + len(o) for va, o, _k in CODE_SITES.values())]
    noreloc = [nm for nm, (sva, _o, _c) in VMT_SLOTS.items() if sva not in rl]
    print("code sites %s" % cstate)
    print("vmt slots  %s" % vstate)
    print("zone %s (%d B) | relocs in zone/sites %s | VMT slots without reloc %s" % (zstate, len(code), bad or "none", noreloc or "none"))
    print("caves " + ", ".join("%s=%#x" % kv for kv in where.items()))
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        inv = {v: k for k, v in where.items()}
        for i in md.disasm(code, ZONE):
            if i.address in inv: print("  -- %s" % inv[i.address])
            print("   %08X  %-20s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad or noreloc or any(s.startswith("OTHER") for s in list(cstate.values()) + list(vstate.values())): print("ABORT"); return 1
    if a.revert:
        for nm, (va, orig, _k) in CODE_SITES.items(): d[vaoff(va):vaoff(va) + len(orig)] = orig
        for nm, (sva, orig, _c) in VMT_SLOTS.items(): struct.pack_into("<I", d, data_off(d, sva), orig)
        d[vaoff(ZONE):vaoff(ZONE_END)] = bytes(ZONE_END - ZONE)
        with open(DLL, "r+b") as f: f.write(bytes(d))
        print("reverted"); return 0
    if all(s == "ours" for s in list(cstate.values()) + list(vstate.values())) and zstate == "ours": print("already applied"); return 0
    if zstate == "DIFFERS" and not any(s.startswith("ours") for s in list(cstate.values()) + list(vstate.values())): print("ABORT (zone not free)"); return 1
    if zstate == "DIFFERS": print("older build of this patch detected -> rewriting zone + every site/slot in place")
    d[vaoff(ZONE):vaoff(ZONE_END)] = bytes(ZONE_END - ZONE); d[vaoff(ZONE):vaoff(ZONE) + len(code)] = code
    for nm, (va, orig, _k) in CODE_SITES.items(): d[vaoff(va):vaoff(va) + len(orig)] = hooks[nm]
    for nm, (sva, orig, cave) in VMT_SLOTS.items(): struct.pack_into("<I", d, data_off(d, sva), where[cave])
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(DLL, ".bak_steampower")
    if not os.path.exists(bak): shutil.copy2(DLL, bak); print("backup ->", bak)
    with open(DLL, "r+b") as f: f.write(bytes(d))
    assert open(DLL, "rb").read() == bytes(d); print("Written and verified"); return 0


if __name__ == "__main__":
    sys.exit(main())
