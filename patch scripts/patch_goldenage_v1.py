"""
GOLDEN AGE (spell 302, Earth/Life sphere pair 9, tier 3) - global enchantment (2026-10-14).  AoWEPACK.dll only.

Spec (user): global spell, research 150, cost 75, upkeep 10.  All of the caster's cities produce 25 % more income.

DONOR = Earth Mastery (TEarthMastery: spell class cell 0x557EF444, Create 0x557F34B0, registered @0x557F3AB0 in the
global-spell loop; spell id 0x40 = 64, Spells.pfs key 74).  Water Mastery (Drought 391) and Fire Mastery (Steam Power
406) are taken.  Recipe = patch_steampower_v1.py:
  CE  TEarthMastery.CreateEnchantment 0x557F373C (spell VMT+0xA0; `xor ecx,ecx / mov dl,1 / mov eax,[0x557EF318] /
      call TEarthMasteryEnchantment.Create 0x557F3204 / ret`): `jmp cave` (5 B; the reloc'd cell operand behind it
      becomes dead code).  The cave replays it (cell read PIC) and for [spell+0x10] == 302 writes the MARKER
      [ench+0x14] := 302 (serialised -> survives saves) and copies the spell name [spell+8] into [ench+0x1C]
      (System.@LStrAsg 0x55701150) - the ctor hardcodes "Earth Mastery".
  AC/DE  TEarthMasteryEnchantment VMT 0x557EF358 +0x68 Activate 0x557F3370 / +0x60 Deactivate 0x557F3410 (sphere
      mastery counter 0x5577E220/0x5577E228(gmc, 4), the player's magic flag 0x80 [pmc+0x44], a refresh of every unit
      of every army) -> VMT slots re-pointed: marker 302 -> the BASE TGlobalEnchantment.Activate 0x5577DBA0 /
      Deactivate 0x5577DC3C only; anything else -> the Earth Mastery originals.
  CHK +0x64 0x557F32AC ("already active": base check 0x5577DAE8, then flag 0x80; message branch 0x557F3303 builds
      "<[ench+0x1C]> is already active" and returns 0): marker 302 -> base check, then our once-per-player test
      (an ACTIVE 302 cast by this player); refused through Earth Mastery's own message branch, entered after replaying
      its prologue (frame -0x14, SEH handler 0x557F335F read PIC).  Earth Mastery's flag is NOT consulted, so an
      active Earth Mastery doesn't block Golden Age (and vice versa).
  MM  TEarthMastery.ExecuteTE 0x557F36B8: `call 0x557EF7C0` @0x557F36D9 (the sphere mastery message, dl = 3) ->
      skipped for spell 302 (esi = spell).
  World FX (display only, System.Random, MP-safe): ExecuteTE @0x557F3712 `mov dl,9 / call 0x55779068` creates a
      TWorldFXHS type 9 fxEarthMastery; NewFrame case 9 (0x5579698C) spawns type-10 fxEMParticle particles
      (@0x557969B0, `mov ebx,eax / mov eax,0xC` @0x557969B5); Show case 10 (0x55797199) draws GetSpell(0x40) slot 0
      (`mov edx,0x40` @0x557971A4).  Same trick as patch_drought_worldfx_v1.py, marker value 2 in the unused padding
      byte [hs+0x25] (Drought uses 1 on the type-2/4 paths only):
        EV @0x557F3712 (7 B): replay, and for spell 302 mark the master [eax+0x25] := 2.
        PS @0x557969B5 (7 B): `mov ebx,eax` + copy the master's [ [ebp-4] + 0x25 ] into the particle + `mov eax,0xC`.
        ID @0x557971A4 (5 B): edx = 0x40, or 302 when [[ebp-4]+0x25] == 2 -> Golden Age's OWN record slot 0.
  Kept from the donor: sound 0 of the spell record (0x557F371E) and the event-log line (0x557F372A).

'Is Golden Age active for player P' (gaa, dl = P): scan TGlobalMagicControl [[AoWHSMap 0x558FA040]+0x188] list +0x14
(Count = VMT+0x54, Get 0x5577E13C) for an enchantment with bit0 of [e+0x10] (active), [e+0x14] == 302 and caster
[e+0x19] == P (player-list index = structure owner byte [obj+0x30]).  Synced state only -> MP-safe, no RNG.

EFFECT - city income +25 % (rounded down, capped at 255 - the income is a byte):
  A city's per-turn gold = byte [city+0x3C] (TPlayerCropStructure.GetIncome 0x557A6100 = TCity VMT+0x1F4, read by
  TPlayerStructureIncomeSource.Income 0x55761AF8 = the real payout; City.CityIncome 0x557AE1BC = the treasury line sums
  the same byte; TCity.ListIncomeInfo = the city panel breakdown).  It is (re)computed by TCity.UpdateIncome 0x557ABB94
  = TCity VMT+0x230 (slot 0x557A7620; base 0x557A6480, size bonus, Gold Rush x2 - recomputed from scratch each time,
  so no compounding) -> slot wrapped (cave ci): call the original, then if the owner has Golden Age,
  SetIncome(city, min(255, inc + inc/4)) via TPlayerCropStructure.SetIncome 0x557A617C (which also notifies the
  owner's income).  Gold Rush's doubling is inside UpdateIncome, so +25 % applies on top of it.
  The new value appears whenever the city's income is next recomputed (UpdateIncome runs on the city's own updates /
  new turns) - a fresh cast or a dispel shows from then on.

Zone 0x55856000..0x55858000 (zero, reloc-free; PIC via call/pop delta for every in-image absolute).
Dry-run default; --apply (upgrades an older build of this patch in place) / --revert / --dis.
Backup <game>\\backup\\AoWEPACK.dll.bak_goldenage.
Pipeline entry (patch_dual_sphere_spells_v1.py): donor "TEarthMastery": (0x557EF444, 0x557F34B0) (site 0x557F3AB0),
pfs_donor 74, tc_type None, sphere 9, tier 3, mana 75, research 150, upkeep 10, pokes [(0x34, 4, 0xFFFFFFFF)].

v2 (2026-10-15) - the same Earth Mastery plumbing ALSO serves BLACK TIDE (spell 342, Water/Death tier 3; research 150,
cost 60, upkeep 8: "enemy units suffer -30 % movement in water"), the way patch_overgrowth_v1.py v3 serves 383 + 327:
  * CE writes the marker for 302 OR 342 (+ name); MM skipped for both; AC/DE: marker 302/342 -> base Activate/
    Deactivate only; CHK: marker 302/342 -> base check, then "already have an ACTIVE <this marker>" (per spell - Golden
    Age and Black Tide don't block each other); scan gxa (dl = player, ecx = spell id) - gaa = gxa(302).
  * World FX: EV marks Black Tide's TWorldFXHS with 3; ID draws GetSpell(342) slot 0 for mark 3 (302 for mark 2).
  * EFFECT - MP (prologue of TAbstractUnit.CreateMovePointTable 0x5577FDC4: `push ebx/push esi/push edi/add esp,-0x10`,
    6 B, no relocs; register args eax = unit, edx = 256-byte table; called directly by every strategic path/cost user,
    incl. the AI path builders and the single-hex cost reader 0x55780848) -> jmp cave mp: run the original (replayed
    prologue, jump to 0x5577FDCA; it returns into the cave), then btp: if ANY player C has an ACTIVE 342 and the unit's
    owner O = [unit+0x24] is C's enemy (O != C and (O <= 0 (independents) or relation(O, C) != 2 - relation =
    TPlayerList [[0x558FA040]+0x140].GetRelation 0x55754150, dl = O, cl = C; 2 = allied/self)), WATER row 0 of the table
    (rows = terrain id 0..15, Water 0; columns = overlay + 1; [row*16 + overlay + 1] read at 0x55780869) gets every
    passable cost c > 0 -> max(c + 1, round(c * 10 / 7)) (= -30 % movement; capped 0x7F; 0xFF impassable untouched).
    Applied once however many enemies cast it (no stacking).  Rebuilt from the base table on every call -> nothing
    compounds; synced state only -> MP-safe and deterministic; the AI paths with the same costs.  Strategic map only
    (tactical combat water hexes are not changed).

v3 (2026-10-15) - NIMUE'S FAVOUR (spell 398, Water/Air tier 3; research 150, cost 60, upkeep 8: "friendly units gain
+30 % movement in water") shares the same plumbing as the mirror of Black Tide:
  * CE/MM/AC/DE/CHK treat marker 398 like 302/342 (per-spell "already active"); EV marks its TWorldFXHS 4, ID draws
    GetSpell(398) slot 0 for mark 4.
  * MP now runs btp (the Black Tide penalty) and THEN nfp: if ANY player C has an ACTIVE 398 and the unit's owner O is
    C itself or C's ally (O > 0 and (O == C or relation(O, C) == 2)), WATER row 0 passable costs c > 0 ->
    max(1, floor(c * 10 / 13)) (= +30 % movement: 2->1, 3->2, 4->3, 5->3, 6->4, 8->6; a cost of 1 stays 1, never 0;
    0xFF impassable untouched).  Applied once however many friendly casters (no stacking).  A unit hit by an enemy's
    Black Tide AND its own side's Nimue's Favour gets the penalty first, then the bonus (e.g. 3 -> 5 -> 3).
    Independents (O <= 0) never get the bonus.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DLL = game_file("AoWEPACK.dll")
BASE, CODE_V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x55856000, 0x55858000
SPELL_ID, EM_ID, FX_MARK = 302, 0x40, 2
BT_ID, BT_MARK = 342, 3                      # v2: Black Tide shares the plumbing
NF_ID, NF_MARK = 398, 4                      # v3: Nimue's Favour shares the plumbing
CMPT_BODY, PLIST_REL = 0x5577FDCA, 0x55754150   # CreateMovePointTable after its 6-byte prologue; TPlayerList.GetRelation

MAP_GLOBAL, LIST_GET = 0x558FA040, 0x5577E13C
BASE_ACT, BASE_DEACT, BASE_CHK = 0x5577DBA0, 0x5577DC3C, 0x5577DAE8
EM_ACT, EM_DEACT, EM_CHK, EM_CHK_MSG, EM_CHK_SEH = 0x557F3370, 0x557F3410, 0x557F32AC, 0x557F3303, 0x557F335F
EM_ENCH_CREATE, EM_ENCH_CELL = 0x557F3204, 0x557EF318
MASTERY_MSG, LSTRASG, WORLD_EVENT = 0x557EF7C0, 0x55701150, 0x55779068
CITY_UPDINC, CROP_SETINC = 0x557ABB94, 0x557A617C

CODE_SITES = {
    "CE": (0x557F373C, bytes.fromhex("33c9b201a1"), "jmp"),
    "MM": (0x557F36D9, bytes.fromhex("e8e2c0ffff"), "call"),
    "EV": (0x557F3712, bytes.fromhex("b209e84f59f8ff"), "call"),
    "PS": (0x557969B5, bytes.fromhex("8bd8b80c000000"), "call"),
    "ID": (0x557971A4, bytes.fromhex("ba40000000"), "call"),
    "MP": (0x5577FDC4, bytes.fromhex("53565783c4f0"), "jmp"),     # v2: CreateMovePointTable prologue (Black Tide)
}
VMT_SLOTS = {
    "emAct":   (0x557EF3C0, EM_ACT, "ac"),
    "emDeact": (0x557EF3B8, EM_DEACT, "de"),
    "emChk":   (0x557EF3BC, EM_CHK, "chk"),
    "cityInc": (0x557A7620, CITY_UPDINC, "ci"),
}

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
    C = {"id": SPELL_ID, "bt": BT_ID, "btmark": BT_MARK, "nf": NF_ID, "nfmark": NF_MARK, "cmpt": CMPT_BODY, "rel": PLIST_REL, "emid": EM_ID, "mark": FX_MARK, "map": MAP_GLOBAL, "get": LIST_GET, "bact": BASE_ACT,
         "bdeact": BASE_DEACT, "bchk": BASE_CHK, "emact": EM_ACT, "emdeact": EM_DEACT, "emchk": EM_CHK, "emmsg": EM_CHK_MSG,
         "emseh": EM_CHK_SEH, "emcreate": EM_ENCH_CREATE, "emcell": EM_ENCH_CELL, "mmsg": MASTERY_MSG, "lstrasg": LSTRASG,
         "wev": WORLD_EVENT, "updinc": CITY_UPDINC, "setinc": CROP_SETINC}
    clash = set(C) & {"gaa", "gxa", "ce", "mm", "ac", "de", "chk", "ev", "ps", "id_", "ci", "mp", "btp", "nfp"}
    assert not clash, clash
    # gxa: dl = player index, ecx = spell id -> al = 1 if that player has an ACTIVE global enchantment with that marker;
    # all other regs preserved.  (v2: generalised from gaa so Black Tide 342 shares it.)
    place("gxa", """
        push ebx
        push ecx
        push edx
        push esi
        push edi
        push ebp
        movsx edi, dl
        mov ebp, ecx
        call $D
        pop ebx
        sub ebx, $D
        mov eax, [ebx+%(map)#x]
        test eax, eax
        jz gxa_no
        mov eax, [eax+0x188]
        test eax, eax
        jz gxa_no
        mov esi, [eax+0x14]
        test esi, esi
        jz gxa_no
        mov eax, esi
        mov edx, [eax]
        call dword ptr [edx+0x54]
        mov ecx, eax
    gxa_lp:
        dec ecx
        js gxa_no
        push ecx
        mov eax, esi
        mov edx, ecx
        call %(get)#x
        pop ecx
        test eax, eax
        jz gxa_lp
        cmp dword ptr [eax+0x14], ebp
        jne gxa_lp
        test byte ptr [eax+0x10], 1
        jz gxa_lp
        movsx edx, byte ptr [eax+0x19]
        cmp edx, edi
        jne gxa_lp
        mov eax, 1
        jmp gxa_out
    gxa_no:
        xor eax, eax
    gxa_out:
        pop ebp
        pop edi
        pop esi
        pop edx
        pop ecx
        pop ebx
        ret
    """, pic=True)
    # gaa: dl = player index -> al = 1 if that player has an ACTIVE Golden Age; all other regs preserved
    place("gaa", """
        push ecx
        mov ecx, %(id)d
        call %(gxa)#x
        pop ecx
        ret
    """)
    # CE: replayed CreateEnchantment + marker + name (jmp'ed to; eax = spell)
    place("ce", """
        push eax
        push ebx
        call $D
        pop ebx
        sub ebx, $D
        mov eax, [ebx+%(emcell)#x]
        pop ebx
        xor ecx, ecx
        mov dl, 1
        call %(emcreate)#x
        pop edx
        mov ecx, [edx+0x10]
        cmp ecx, %(id)d
        je ce_ours
        cmp ecx, %(bt)d
        je ce_ours
        cmp ecx, %(nf)d
        jne ce_done
    ce_ours:
        mov dword ptr [eax+0x14], ecx
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
        cmp dword ptr [esi+0x10], %(bt)d
        je mm_skip
        cmp dword ptr [esi+0x10], %(nf)d
        je mm_skip
        jmp %(mmsg)#x
    mm_skip:
        ret
    """)
    place("ac", """
        cmp dword ptr [eax+0x14], %(id)d
        je ac_ours
        cmp dword ptr [eax+0x14], %(bt)d
        je ac_ours
        cmp dword ptr [eax+0x14], %(nf)d
        je ac_ours
        jmp %(emact)#x
    ac_ours:
        jmp %(bact)#x
    """)
    place("de", """
        cmp dword ptr [eax+0x14], %(id)d
        je de_ours
        cmp dword ptr [eax+0x14], %(bt)d
        je de_ours
        cmp dword ptr [eax+0x14], %(nf)d
        je de_ours
        jmp %(emdeact)#x
    de_ours:
        jmp %(bdeact)#x
    """)
    # CHK: eax = ench, dl = player, ecx = &message; returns al (1 = may cast)
    place("chk", """
        cmp dword ptr [eax+0x14], %(id)d
        je chk_ours
        cmp dword ptr [eax+0x14], %(bt)d
        je chk_ours
        cmp dword ptr [eax+0x14], %(nf)d
        je chk_ours
        jmp %(emchk)#x
    chk_ours:
        push eax
        push ecx
        push edx
        call %(bchk)#x
        test al, al
        pop edx
        pop ecx
        pop eax
        jnz chk_base_ok
        xor eax, eax
        ret
    chk_base_ok:
        push eax
        push ecx
        mov ecx, [eax+0x14]
        call %(gxa)#x
        test al, al
        pop ecx
        pop eax
        jnz chk_refuse
        mov eax, 1
        ret
    chk_refuse:
        push ebp
        mov ebp, esp
        add esp, -0x14
        push ebx
        push esi
        push edi
        xor ebx, ebx
        mov [ebp-8], ebx
        mov [ebp-0xc], ebx
        mov edi, ecx
        mov [ebp-1], dl
        mov esi, eax
        call $D
        pop eax
        sub eax, $D
        add eax, %(emseh)#x
        push ebp
        push eax
        xor eax, eax
        push dword ptr fs:[eax]
        mov dword ptr fs:[eax], esp
        jmp %(emmsg)#x
    """, pic=True)
    # EV: the world event (esi = spell) - mark Golden Age's TWorldFXHS
    place("ev", """
        mov dl, 9
        call %(wev)#x
        cmp dword ptr [esi+0x10], %(id)d
        jne ev_bt
        mov byte ptr [eax+0x25], %(mark)d
        ret
    ev_bt:
        cmp dword ptr [esi+0x10], %(bt)d
        jne ev_nf
        mov byte ptr [eax+0x25], %(btmark)d
        ret
    ev_nf:
        cmp dword ptr [esi+0x10], %(nf)d
        jne ev_done
        mov byte ptr [eax+0x25], %(nfmark)d
    ev_done:
        ret
    """)
    # PS: a spawned fxEMParticle inherits the master's marker ([ebp-4] = the master TWorldFXHS in NewFrame)
    place("ps", """
        mov ebx, eax
        push ecx
        mov ecx, [ebp-4]
        mov cl, byte ptr [ecx+0x25]
        mov byte ptr [ebx+0x25], cl
        pop ecx
        mov eax, 0xc
        ret
    """)
    # ID: Show case 10 ([ebp-4] = the particle): Golden Age's own record when marked
    place("id_", """
        mov edx, %(emid)d
        push ecx
        mov ecx, [ebp-4]
        cmp byte ptr [ecx+0x25], %(mark)d
        jne id_bt
        mov edx, %(id)d
        jmp id_done
    id_bt:
        cmp byte ptr [ecx+0x25], %(btmark)d
        jne id_nf
        mov edx, %(bt)d
        jmp id_done
    id_nf:
        cmp byte ptr [ecx+0x25], %(nfmark)d
        jne id_done
        mov edx, %(nf)d
    id_done:
        pop ecx
        ret
    """)
    # CI: TCity.UpdateIncome wrapper (VMT+0x230; eax = city)
    place("ci", """
        push ebx
        push esi
        mov esi, eax
        call %(updinc)#x
        mov dl, byte ptr [esi+0x30]
        cmp dl, 0xff
        je ci_out
        call %(gaa)#x
        test al, al
        jz ci_out
        movzx eax, byte ptr [esi+0x3c]
        mov edx, eax
        shr edx, 2
        add edx, eax
        cmp edx, 0xff
        jbe ci_set
        mov edx, 0xff
    ci_set:
        mov eax, esi
        call %(setinc)#x
    ci_out:
        pop esi
        pop ebx
        ret
    """)
    # BTP: eax = unit, edx = move-point table -> water row 0 x10/7 for enemies of an active Black Tide; preserves all
    place("btp", """
        pushad
        mov esi, edx
        movsx edi, byte ptr [eax+0x24]
        call $D
        pop ebx
        sub ebx, $D
        mov eax, [ebx+%(map)#x]
        test eax, eax
        jz btp_out
        mov eax, [eax+0x188]
        test eax, eax
        jz btp_out
        mov ebp, [eax+0x14]
        test ebp, ebp
        jz btp_out
        mov eax, ebp
        mov edx, [eax]
        call dword ptr [edx+0x54]
        mov ecx, eax
    btp_lp:
        dec ecx
        js btp_out
        push ecx
        mov eax, ebp
        mov edx, ecx
        call %(get)#x
        pop ecx
        test eax, eax
        jz btp_lp
        cmp dword ptr [eax+0x14], %(bt)d
        jne btp_lp
        test byte ptr [eax+0x10], 1
        jz btp_lp
        movsx edx, byte ptr [eax+0x19]
        cmp edx, edi
        je btp_lp
        test edi, edi
        jle btp_apply
        push ecx
        mov ecx, edx
        mov edx, edi
        mov eax, [ebx+%(map)#x]
        mov eax, [eax+0x140]
        call %(rel)#x
        pop ecx
        cmp al, 2
        je btp_lp
    btp_apply:
        mov ebp, 7
        xor ecx, ecx
    btp_ap:
        movsx eax, byte ptr [esi+ecx]
        test eax, eax
        jle btp_nx
        mov edi, eax
        inc edi
        imul eax, eax, 10
        add eax, 3
        xor edx, edx
        div ebp
        cmp eax, edi
        jge btp_big
        mov eax, edi
    btp_big:
        cmp eax, 0x7f
        jbe btp_st
        mov eax, 0x7f
    btp_st:
        mov byte ptr [esi+ecx], al
    btp_nx:
        inc ecx
        cmp ecx, 16
        jb btp_ap
    btp_out:
        popad
        ret
    """, pic=True)
    # NFP (v3): eax = unit, edx = move-point table -> water row 0 floor(c*10/13) (min 1) for the side of an active
    # Nimue's Favour (owner == caster or allied); preserves all
    place("nfp", """
        pushad
        mov esi, edx
        movsx edi, byte ptr [eax+0x24]
        test edi, edi
        jle nfp_out
        call $D
        pop ebx
        sub ebx, $D
        mov eax, [ebx+%(map)#x]
        test eax, eax
        jz nfp_out
        mov eax, [eax+0x188]
        test eax, eax
        jz nfp_out
        mov ebp, [eax+0x14]
        test ebp, ebp
        jz nfp_out
        mov eax, ebp
        mov edx, [eax]
        call dword ptr [edx+0x54]
        mov ecx, eax
    nfp_lp:
        dec ecx
        js nfp_out
        push ecx
        mov eax, ebp
        mov edx, ecx
        call %(get)#x
        pop ecx
        test eax, eax
        jz nfp_lp
        cmp dword ptr [eax+0x14], %(nf)d
        jne nfp_lp
        test byte ptr [eax+0x10], 1
        jz nfp_lp
        movsx edx, byte ptr [eax+0x19]
        cmp edx, edi
        je nfp_apply
        push ecx
        mov ecx, edx
        mov edx, edi
        mov eax, [ebx+%(map)#x]
        mov eax, [eax+0x140]
        call %(rel)#x
        pop ecx
        cmp al, 2
        jne nfp_lp
    nfp_apply:
        mov ebp, 13
        xor ecx, ecx
    nfp_ap:
        movsx eax, byte ptr [esi+ecx]
        test eax, eax
        jle nfp_nx
        imul eax, eax, 10
        xor edx, edx
        div ebp
        cmp eax, 1
        jge nfp_st
        mov eax, 1
    nfp_st:
        mov byte ptr [esi+ecx], al
    nfp_nx:
        inc ecx
        cmp ecx, 16
        jb nfp_ap
    nfp_out:
        popad
        ret
    """, pic=True)
    # MP (v2/v3): CreateMovePointTable prologue jmp -> run the original as a callee, then the Black Tide water penalty,
    # then (v3) the Nimue's Favour water bonus
    place("mp", """
        push eax
        push edx
        call mp_orig
        pop edx
        pop eax
        call %(btp)#x
        jmp %(nfp)#x
    mp_orig:
        push ebx
        push esi
        push edi
        add esp, -0x10
        jmp %(cmpt)#x
    """)
    return bytes(out), where


CAVE_OF = {"CE": "ce", "MM": "mm", "EV": "ev", "PS": "ps", "ID": "id_", "MP": "mp"}


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
    assert ZONE + len(code) <= ZONE_END
    rl = relocs(bytes(d))
    zl = bytes(d[vaoff(ZONE):vaoff(ZONE_END)])
    zstate = "zero" if not any(zl) else "ours" if zl[:len(code)] == code and not any(zl[len(code):]) else "DIFFERS"
    hooks, cstate = {}, {}
    for nm, (va, orig, kind) in CODE_SITES.items():
        tgt = where[CAVE_OF[nm]]
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
    bak = bak_path(DLL, ".bak_goldenage")
    if not os.path.exists(bak): shutil.copy2(DLL, bak); print("backup ->", bak)
    with open(DLL, "r+b") as f: f.write(bytes(d))
    assert open(DLL, "rb").read() == bytes(d); print("Written and verified"); return 0


if __name__ == "__main__":
    sys.exit(main())
