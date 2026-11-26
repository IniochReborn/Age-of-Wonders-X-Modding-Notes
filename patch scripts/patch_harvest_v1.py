"""
BOUNTIFUL HARVEST (spell 325, Life/Water sphere pair 12, tier 2) - global enchantment (2026-10-15).  AoWEPACK.dll only.

Spec (user): global spell, research 80, cost 40, upkeep 5.  "Crops yield +1 gold (farms and cities)".

WHAT A "CROP" IS (RE 2026-10-15):  TCity and TFarm both derive from TPlayerCropStructure (VMT 0x557A5634; Delphi 3
layout: class name at VMT-0x20, parent cell at VMT-0x18).  Their per-turn gold is the byte [obj+0x3C]
(GetIncome 0x557A6100 = VMT+0x1F4), recomputed by VMT+0x230: TFarm keeps the base 0x557A6230, TCity overrides it with
0x557ABB94 (currently wrapped by Golden Age's ci cave).  Both start from 0x557A6480 = the CROP COUNT: the TCrop field
objects (class id 0x2036A, [crop+0x1C] == this structure) on the structure's crop-hex list ([[obj+8]+0x74]).  VANILLA
paid 2 gold per crop (`add edx,edx` @0x557A6255 farm, `add ebx,ebx` @0x557ABBC6 city, `add eax,eax` @0x557ABA4E /
0x557ABAA8 in the city income panel); AoWx (an older script not on this PC) NOP'd all four -> 1 gold per crop.
=> Bountiful Harvest = +1 gold per crop: while the OWNER has an active 325, each crop pays 2 again - in the payout
(farm + city UpdateIncome) and in the city income panel.  The crop count itself (0x557A6480) is NOT touched: crop
GROWTH (0x557A61B4 = VMT+0x22C: grow while count < max) also reads it.

DONOR = Life Mastery (TLifeMastery: class cell 0x557EED34, Create 0x557F2158, registered @0x557F3A6B; spell id 0x3D,
Spells.pfs key 71).  Golden Age recipe (patch_goldenage_v1.py):
  CE  TLifeMastery.CreateEnchantment 0x557F220C (spell VMT+0xA0: `xor ecx,ecx / mov dl,1 / mov eax,[0x557EEC0C] / call
      TLifeMasteryEnchantment.Create 0x557F1EA8 / ret`): `jmp cave` - replay (cell PIC), marker [ench+0x14] := 325
      (serialised) and the spell name [spell+8] -> [ench+0x1C].
  AC/DE/CHK  TLifeMasteryEnchantment VMT 0x557EEC4C slots +0x68 0x557EECB4 (Activate 0x557F2028: mastery counter,
      the player's Life flag 0x10 [pmc+0x44], a refresh of every unit) / +0x60 0x557EECAC (Deactivate 0x557F20C8) /
      +0x64 0x557EECB0 (CanActivate 0x557F1F50: base check 0x5577DAE8, then flag 0x10; message branch 0x557F1FAA,
      frame -0x18, SEH handler 0x557F2018) -> marker 325: base TGlobalEnchantment Activate/Deactivate only; CanActivate
      = base check + "this player already has an active 325" (refused through Life Mastery's own message branch).
  MM  TLifeMastery.ExecuteTE 0x557F221C (esi = spell): the sphere mastery message `call 0x557EF7C0` @0x557F2241 ->
      skipped for 325.
  ID  the world FX (an animated sprite at the caster's capital, 0x557FB300 object) looks up GetSpell(0x3D) slot 0 by a
      hard-coded `mov edx,0x3D` @0x557F2298 -> 325 for our spell, so Bountiful Harvest shows its OWN gfx slot 0.
  Kept from the donor: the spell's own sound 0 (@0x557F22DC) and the event-log line (@0x557F22EB).

INCOME hooks (ebx/esi = the structure, owner = player-list index byte [obj+0x30]; hva = 'has an active 325'):
  F   0x557A6253 (6 B `mov edx,eax / nop / nop / mov eax,ebx`, farm base UpdateIncome)  -> edx = count (x2 if hva)
  C   0x557ABBC4 (6 B `mov ebx,eax / nop / nop / mov eax,esi`, TCity.UpdateIncome)        -> ebx = count (x2 if hva)
  P1  0x557ABA49 / P2 0x557ABAA3 (7 B `call 0x557A6480 / inc eax / dec eax`, the city income panel) -> count x2 if hva
  The new value shows whenever a structure's income is next recomputed (UpdateIncome runs on its updates / new turns),
  like Golden Age.  Golden Age (+25 %) applies on top in cities (its wrapper calls TCity.UpdateIncome first).

v2 (2026-10-15, user: "crop yield shows doubled in city screen but it doesnt actually grant the income"; farms too):
  ROOT CAUSE - income is CACHED.  [obj+0x3C] is written only by UpdateIncome (VMT+0x230) -> SetIncome 0x557A617C, which
  also refreshes the player's cached total [player+0xD0] (0x55751F88).  Per turn, UpdateIncome only ran when a crop
  REGREW (TPlayerCropStructure.NewTurn 0x557A6200 -> CropsEnabled -> RegrowCrops -> SetCropCount); a city or farm with
  full crops never recomputed, so F/C never ran and the payout (0x557553C4: gold += [player+0xD0] @0x5575542E) kept
  the old value.  The panel (P1/P2) computes live, hence the mismatch.
  NT  0x557A620F (5 B `cmp bl,[esi+0x30] / jne`, crop NewTurn) -> recompute UpdateIncome on every owner's turn.
  ORDER: the payout function adds [player+0xD0] BEFORE it broadcasts the new-turn message 0x20020002 (@0x55755536)
  that runs the structures' NewTurn -> a cast/dispel shows in the gold received from the turn AFTER the next one
  (one-turn lag), steady state thereafter.

v3 (2026-10-15, user: "still doesnt work properly. cities/farms income unchanged"): the bonus no longer relies on the
  cached byte being recomputed.  Re-trace: payout 0x557553C4 -> gold := [p+0xC4] + [p+0xD0] - expenses (0x5575542E);
  [p+0xD0] is a CACHE rebuilt only by 0x55751F88 = [p+0xB0] + SUM over [p+0x64] (TPlayerStructureIncomeSource, VMT
  0x55714160, created per crop structure @0x557A609C into [obj+0x40]) of source VMT+0x50 0x55761AF8 = the structure's
  GetIncome VMT+0x1F4 (0x557A6100 `movzx eax,[eax+0x3C]`) x race factor; 0x55751F88 only ran when SetIncome CHANGED a
  byte.  So the payout was only as fresh as the last refresh, and any staleness in the UpdateIncome -> SetIncome chain
  kept paying 1 per crop.
  GI  the GetIncome slot of TPlayerCropStructure / TCity / TFarm (0x557A5828 / 0x557A75E4 / 0x557B2A10, all
      0x557A6100) -> cave gi = [obj+0x3C] + (owner has an active 325 ? crop count : 0).  Every reader (the income source
      -> the player total, the realm overview sums 0x557B482C / 0x557CA57C, the tooltips 0x557B2BFB / 0x557B442F) sees
      the bonus; nothing feeds GetIncome back into SetIncome, so it cannot compound.
  PAY the payout's `add edx,[eax+0xD0]` @0x5575542E (6 B) -> call cave pay: rebuild the player's total (0x55751F88)
      first, then add it -> the gold paid is always current (no lag after a cast / dispel).
  F / C retired (restored to the live 1-per-crop bytes) - with GI they would double-count.  P1/P2 (panel crop lines)
  and NT (per-turn UpdateIncome, keeps Golden Age's +25 % fresh) stay.  The +1 per crop is added after Golden Age's
  +25 % (flat, not boosted); the player-level race factor in 0x55751F88 applies to it like any income.
  Probe: patch scripts\harvest_probe.py (read-only) prints every player's gold / [D0] and every source's [obj+0x3C].

hva / every cave reads synced state only (the global-magic list) -> MP-safe, no RNG.
Zone 0x55828000..0x5582A000 (verified zero; PIC call/pop delta for every in-image absolute).
Dry-run default; --apply (upgrades an older build in place) / --revert / --dis.  Backup <game>\\backup\\AoWEPACK.dll.bak_harvest.
Pipeline entry (patch_dual_sphere_spells_v1.py): DONOR "TLifeMastery": (0x557EED34, 0x557F2158) (site 0x557F3A6B),
pfs_donor 71, tc_type None, sphere 12, tier 2, mana 40, research 80, upkeep 5, pokes [(0x34, 4, 0xFFFFFFFF)].

v7 (2026-10-15; user: the boosted amounts everywhere relevant + the treasury/income display must update on cast/removal;
the 10/15 live probe confirmed the payout already includes the bonus: [p+0xD0] 624 vs 607 unboosted):
  * AC/DE now call the base Activate/Deactivate and then RF = rebuild the caster's cached income total [p+0xD0]
    (0x55751F88, which sums every income source's GetIncome -> includes GI's crop bonus) - the treasury window
    (AoWx.exe 0x448F1C/0x448F6E reads [p+0xD0] directly) is right the moment the spell is cast, dispelled or lost.
  * S1/S2: the exported City.CityIncome / Farm.FarmIncome (per-player sums the exe treasury breakdown imports) summed the
    raw byte [obj+0x3C]; now each TCity / TFarm's GetIncome (cave GS).
  * The AoWx.exe-side displays that printed the raw byte are patch_harvest_display_exe_v1.py (city window header,
    structure info window, city info, city list).
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DLL = game_file("AoWEPACK.dll")
BASE, CODE_V2F = 0x55700C00 - 0xC00, 0x55700C00
ZONE, ZONE_END = 0x55828000, 0x5582A000
TW_COUNT, TW_RADIUS, TW_SPREAD = 240, 220, 45      # v4: world-FX twinkles for 325 (vanilla Life Mastery 100 / 64 / 30)
DRIFT_CLS, DRIFT_CTOR, DRIFT_CB, MAP_VAR, ID_TAIL = 0x557FAE60, 0x557FB4A8, 0x557F286C, 0x558E9494, 0x557F22D7   # v5: Death Mastery's map-wide drift
SPELL_ID, LM_ID = 325, 0x3D

MAP_GLOBAL, LIST_GET = 0x558FA040, 0x5577E13C
BASE_ACT, BASE_DEACT, BASE_CHK = 0x5577DBA0, 0x5577DC3C, 0x5577DAE8
LM_ACT, LM_DEACT, LM_CHK, LM_CHK_MSG, LM_CHK_SEH = 0x557F2028, 0x557F20C8, 0x557F1F50, 0x557F1FAA, 0x557F2018
LM_ENCH_CREATE, LM_ENCH_CELL = 0x557F1EA8, 0x557EEC0C
MASTERY_MSG, LSTRASG = 0x557EF7C0, 0x55701150
CROP_COUNT = 0x557A6480
# v6 (2026-10-15, user: a subtle green/gold hex glow on crop fields while Bountiful Harvest is active):
# TCrop (VMT 0x557A5A1C, a TILTerrainMO: x/y bytes [+0x10]/[+0x11], owner structure [+0x1C]) draws through VMT+0x9C =
# ILTer.TILTerrainMO.Show (thunk 0x55703564; eax self, edx scroll x, ecx scroll y, push surface; ret 4).  The slot now
# points at cave cg: the original Show, then - if the owner structure's player ([struct+0x30]) has an active 325
# (hva) - a PURE frame draw of spell 325 gfx slot GLOW_SLOT at the hex, placed exactly like Drought/Overgrowth's
# marker glow (HXtoHP + 16 - scroll; the art carries its own xs/ys), frame = (tick / GLOW_PERIOD + phase) mod frames,
# phase = x + 3y.  Visual only: no game state, no RNG.
TCROP_SHOW_SLOT, ILTER_SHOW = 0x557A5AB8, 0x55703564
HXTOHP, GETSPELL, GETIMAGESEQ, IMAGEEXIST, LIBGET = 0x557026B4, 0x55779AC8, 0x557028E4, 0x55702944, 0x55702934
AOWHSSET = 0x558FA044
GLOW_SLOT, GLOW_PERIOD = 3, 6
# v8 (2026-10-15, user: the crop glow does not animate): TCrop is a TILTerrainMO - drawn into the CACHED STATIC scene
# (HSEPack THSMap.DrawStaticScene = VMT+0x98 DrawStaticHS over the static list [map+0x1C], then VMT+0xA0 DrawStaticHSEx;
# redrawn only when the static scene is invalidated), so a glow drawn from TCrop.Show is frozen at whatever frame the
# cache was built with.  Hex sprites in the DYNAMIC list (TFrozenWaterHS markers: Drought / Overgrowth) redraw every
# frame (DrawDynamicScene = VMT+0x9C DrawDynamicHS over [map+0x20], then VMT+0xA4 DrawDynamicHSEx).  The base
# DrawStaticHSEx / DrawDynamicHSEx (HSEPack 0x5560D620 / 0x5560D6E0) are empty `ret`s - free per-scene hook points.
# v8: cg (TCrop.Show) only RECORDS each owned crop (hex x, hex y, owner player: 3 bytes in a 4-byte entry, no pointers)
# into a PENDING list; TAoWHSMap's DrawStaticHSEx slot (VMT 0x5570E874 +0xA0 = 0x5570E914; called right after every
# static redraw) copies PENDING -> ACTIVE and clears PENDING; TAoWHSMap's DrawDynamicHSEx slot (+0xA4 = 0x5570E918,
# eax = map, edx = surface; every dynamic frame) draws the glow (spell 325 gfx slot GLOW_SLOT, frame = (tick / PERIOD +
# phase) mod frames, tick = [[0x558FA040]+0x40] = the animation timer vanilla map effects use) for every ACTIVE entry
# whose owner has an active 325 - hva per entry per frame, so a cast/dispel shows at once.  Buffers live in the BSS
# slack page (BSS ends 0x558FA231, the page runs to 0x558FB000; no reloc / script refs to these ranges):
# PENDING 0x558FA580..0x558FA6A4, ACTIVE 0x558FA6A4..0x558FA7C8 (count dword + CROP_CAP entries each).  Visual only.
# ⚠ 10/23 MP OOS FIX: v8 had ACTIVE at 0x558FA820..0x558FA9F8 = ON TOP of the weakness ability-id table WEAK_IDS
# (0x558FA810..0x558FA82F, read by StrikeDmg x1.5 / effect-roll -3) and the defender-retaliation mark table
# (0x558FA800..0x558FAA00).  It is rewritten from each machine's ON-SCREEN crops after every static redraw ->
# per-machine weakness ids + retaliation marks -> OOS.  Now both buffers stay inside 0x558FA580..0x558FA800 (nothing
# else references it), cap 116 -> 72.  Backup before the move: backup\AoWEPACK.dll.bak_harvestbuf.
# 0x558FA7C8..0x558FA800 now holds the relocated Spring-of-Life diag bytes + weakness block (patch_slack_relocate_v1.py).
CROP_PEND, CROP_ACT, CROP_CAP = 0x558FA580, 0x558FA6A4, 72
MAP_SEX_SLOT, MAP_DEX_SLOT = 0x5570E914, 0x5570E918                        # TAoWHSMap VMT +0xA0 / +0xA4
BASE_SEX, BASE_DEX = 0x55702634, 0x5570264C                                # thunks -> HSEPack THSMap.DrawStaticHSEx / DrawDynamicHSEx (empty)

CODE_SITES = {
    "CE": (0x557F220C, bytes.fromhex("33c9b201a1"), "jmp"),
    "MM": (0x557F2241, bytes.fromhex("e87ad5ffff"), "call"),
    "ID": (0x557F2298, bytes.fromhex("ba3d000000"), "call"),
    "P1": (0x557ABA49, bytes.fromhex("e832aaffff4048"), "call"),
    "P2": (0x557ABAA3, bytes.fromhex("e8d8a9ffff4048"), "call"),
    "NT": (0x557A620F, bytes.fromhex("3a5e307518"), "call"),             # v2: crop NewTurn - always recompute income on the owner's turn
    "PAY": (0x5575542E, bytes.fromhex("0390d0000000"), "call"),          # v3: turn payout - rebuild [p+0xD0] before adding it
    "S1": (0x557AE220, bytes.fromhex("33c08a433c"), "call"),             # v7: City.CityIncome(player) (exported; the exe treasury breakdown) - sum GetIncome, not the raw byte
    "S2": (0x557B2F20, bytes.fromhex("33c08a433c"), "call"),             # v7: Farm.FarmIncome(player) - ditto
}
RETIRED = {                                                               # v3: v1/v2 cache-doubling hooks, now restored (GI does the bonus)
    "F": (0x557A6253, bytes.fromhex("8bd090908bc3")),                     # farm base UpdateIncome (live 1-per-crop bytes)
    "C": (0x557ABBC4, bytes.fromhex("8bd890908bc6")),                     # TCity.UpdateIncome
}
PLAYER_REFRESH = 0x55751F88                                               # [p+0xD0] := [p+0xB0] + sum of income sources (x race factor)
PLAYER_GET = 0x557544D0                                                   # v7: eax = [world+0x140] player list, edx = index -> eax = player
GETINCOME = 0x557A6100
NT_END = 0x557A622C                                                       # TPlayerCropStructure.NewTurn epilogue (pop esi / pop ebx / ret)
VMT_SLOTS = {
    "lmAct":   (0x557EECB4, LM_ACT, "ac"),
    "lmDeact": (0x557EECAC, LM_DEACT, "de"),
    "lmChk":   (0x557EECB0, LM_CHK, "chk"),
    "giBase":  (0x557A5828, 0x557A6100, "gi"),                            # v3: GetIncome (VMT+0x1F4) of TPlayerCropStructure
    "giCity":  (0x557A75E4, 0x557A6100, "gi"),                            #     ... TCity
    "giFarm":  (0x557B2A10, 0x557A6100, "gi"),                            #     ... TFarm
    "cropShow": (TCROP_SHOW_SLOT, ILTER_SHOW, "cg"),                      # v6/v8: TCrop VMT+0x9C Show -> record the crop for the dynamic glow
    "mapSEx":   (MAP_SEX_SLOT, BASE_SEX, "sx"),                           # v8: TAoWHSMap.DrawStaticHSEx -> commit PENDING -> ACTIVE
    "mapDEx":   (MAP_DEX_SLOT, BASE_DEX, "dx"),                           # v8: TAoWHSMap.DrawDynamicHSEx -> draw the animated glows
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
    C = {"id": SPELL_ID, "lmid": LM_ID, "twcount": TW_COUNT, "twradius": TW_RADIUS, "twspread": TW_SPREAD, "driftcls": DRIFT_CLS, "driftctor": DRIFT_CTOR, "driftcb": DRIFT_CB, "mapvar": MAP_VAR, "idtail": ID_TAIL, "map": MAP_GLOBAL, "get": LIST_GET, "bact": BASE_ACT, "bdeact": BASE_DEACT,
         "bchk": BASE_CHK, "lmact": LM_ACT, "lmdeact": LM_DEACT, "lmchk": LM_CHK, "lmmsg": LM_CHK_MSG, "lmseh": LM_CHK_SEH,
         "lmcreate": LM_ENCH_CREATE, "lmcell": LM_ENCH_CELL, "mmsg": MASTERY_MSG, "lstrasg": LSTRASG, "cropcnt": CROP_COUNT,
         "ntend": NT_END, "refresh": PLAYER_REFRESH, "ilshow": ILTER_SHOW, "hxtohp": HXTOHP, "getspell": GETSPELL,
         "getseq": GETIMAGESEQ, "exist": IMAGEEXIST, "libget": LIBGET, "hsset": AOWHSSET, "gslot": GLOW_SLOT, "gperiod": GLOW_PERIOD,
         "pget": PLAYER_GET, "pend": CROP_PEND, "act": CROP_ACT, "cap": CROP_CAP}
    # hva: dl = player index -> eax = 1 if that player has an ACTIVE Bountiful Harvest; ebx/ecx/edx/esi/edi preserved
    place("hva", """
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
        jz hva_no
        mov eax, [eax+0x188]
        test eax, eax
        jz hva_no
        mov esi, [eax+0x14]
        test esi, esi
        jz hva_no
        mov eax, esi
        mov edx, [eax]
        call dword ptr [edx+0x54]
        mov ecx, eax
    hva_lp:
        dec ecx
        js hva_no
        push ecx
        mov eax, esi
        mov edx, ecx
        call %(get)#x
        pop ecx
        test eax, eax
        jz hva_lp
        cmp dword ptr [eax+0x14], %(id)d
        jne hva_lp
        movsx edx, byte ptr [eax+0x19]
        cmp edx, edi
        jne hva_lp
        mov eax, 1
        jmp hva_out
    hva_no:
        xor eax, eax
    hva_out:
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
        mov eax, [ebx+%(lmcell)#x]
        pop ebx
        xor ecx, ecx
        mov dl, 1
        call %(lmcreate)#x
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
    # v4 (2026-10-15, user: "didnt it used to spread over the map, now its very centralized/small"): the world FX is a
    # TTwinkleAnimation (class [0x557FB300], setup 0x557FC008: [+0x40] count, [+0x44] radius, [+0x48] lifetime,
    # [+0x4C] start spread, [+0x50] flags; Life Mastery pushes 100/64/50/30, flags 8 = radius shrinks over the
    # lifetime -> twinkles converge on the capital from <= ~114 px - vanilla Life Mastery is the same small burst).
    # At this call the four pushes sit at [esp+4] spread / +8 lifetime / +0xC radius / +0x10 count -> for 325 widen
    # them (TW_* below) so the harvest twinkles gather in from across the screen.
    # v5 (2026-10-15, user: "bountiful harvest gfx should spread/drift like the others across the whole map"): for 325
    # the twinkle just built (edi) is freed and Death Mastery's MAP-WIDE DRIFT is built instead - the callback animation
    # class [0x557FAE60] (ctor 0x557FB4A8) with draw callback 0x557F286C, exactly as Death Mastery's world FX
    # (0x557F299A..0x557F29ED): each tick it draws 5/10/20 (detail setting) sprites picked by System.Random(3) from the
    # spell's OWN gfx slots 0-2 ([spell+0x2C]) at random viewport positions drifting left/down, for 0x5A ticks.  Visual
    # only (unsynced System.Random, like vanilla).  Then it rejoins the shared tail at 0x557F22D7 (cast sound slot 0,
    # event log).  At this call: [esp] = return 0x557F229D, [esp+4..+0x10] = the twinkle setup's 4 pushes, esi = spell,
    # edi = the new (unregistered) twinkle; both ctors only initialise, so Destroy ([vmt-4], dl=1) is safe.
    place("id_", """
        mov edx, %(lmid)d
        cmp dword ptr [esi+0x10], %(id)d
        jne id_done
        add esp, 0x14
        mov eax, edi
        mov dl, 1
        mov ecx, dword ptr [eax]
        call dword ptr [ecx-4]
        call $D
        pop edi
        sub edi, $D
        xor ecx, ecx
        mov dl, 1
        mov eax, dword ptr [edi+%(driftcls)#x]
        call %(driftctor)#x
        mov byte ptr [eax+0xb], 0x1c
        mov dword ptr [eax+0x28], esi
        lea edx, [edi+%(driftcb)#x]
        mov dword ptr [eax+0x24], edx
        mov edx, dword ptr [edi+%(mapvar)#x]
        mov edx, dword ptr [edx]
        mov dword ptr [eax+0x38], edx
        mov ecx, dword ptr [edi+%(mapvar)#x]
        mov ecx, dword ptr [ecx]
        mov edx, dword ptr [ecx+0x8c]
        and edx, 0xffff
        mov ecx, dword ptr [ecx+0x90]
        shl ecx, 0x10
        or edx, ecx
        mov dword ptr [eax+0x34], edx
        mov edx, dword ptr [eax]
        call dword ptr [edx+0xe0]
        jmp %(idtail)#x
    id_done:
        ret
    """, pic=True)
    # RF (v7, 2026-10-15; user: the treasury/income display must update when the spell is cast/removed): al = player index
    # -> rebuild that player's cached income total [p+0xD0] (0x55751F88 = [p+0xB0] + every income source's GetIncome, which
    # includes the GI crop bonus) so the treasury window / income readouts are right at once instead of at the next payout.
    # Runs from Activate/Deactivate, which every peer executes for the same synced cast/dispel/upkeep loss -> deterministic.
    place("rf", """
        push ebx
        push ecx
        push edx
        push esi
        movsx edx, al
        test edx, edx
        js rf_out
        call $D
        pop esi
        sub esi, $D
        mov eax, [esi+%(map)#x]
        test eax, eax
        jz rf_out
        mov eax, [eax+0x140]
        test eax, eax
        jz rf_out
        call %(pget)#x
        test eax, eax
        jz rf_out
        call %(refresh)#x
    rf_out:
        pop esi
        pop edx
        pop ecx
        pop ebx
        ret
    """, pic=True)
    # AC / DE: for 325 only the base global-enchantment Activate/Deactivate (no Life Mastery side effects), then (v7) refresh
    # the caster's income total.  Activate: eax = ench, dl = player (stored at [ench+0x19]); returns al.  Deactivate may end
    # in the enchantment's own VMT+0x2C, so the player index is read BEFORE it.
    place("ac", """
        cmp dword ptr [eax+0x14], %(id)d
        je ac_ours
        jmp %(lmact)#x
    ac_ours:
        push edx
        call %(bact)#x
        pop edx
        push eax
        mov al, dl
        call %(rf)#x
        pop eax
        ret
    """)
    place("de", """
        cmp dword ptr [eax+0x14], %(id)d
        je de_ours
        jmp %(lmdeact)#x
    de_ours:
        movsx edx, byte ptr [eax+0x19]
        push edx
        call %(bdeact)#x
        pop edx
        push eax
        mov al, dl
        call %(rf)#x
        pop eax
        ret
    """)
    # CHK: eax = ench, dl = player, ecx = &message; returns al (1 = may cast).  Refusal = Life Mastery's own message
    # branch 0x557F1FAA entered after replaying its prologue (frame -0x18, three zeroed string locals, SEH 0x557F2018).
    place("chk", """
        cmp dword ptr [eax+0x14], %(id)d
        je chk_ours
        jmp %(lmchk)#x
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
        call %(hva)#x
        test al, al
        pop eax
        jnz chk_refuse
        mov eax, 1
        ret
    chk_refuse:
        push ebp
        mov ebp, esp
        add esp, -0x18
        push ebx
        push esi
        push edi
        xor ebx, ebx
        mov [ebp-8], ebx
        mov [ebp-0x14], ebx
        mov [ebp-0x18], ebx
        mov edi, ecx
        mov [ebp-1], dl
        mov esi, eax
        call $D
        pop eax
        sub eax, $D
        add eax, %(lmseh)#x
        push ebp
        push eax
        xor eax, eax
        push dword ptr fs:[eax]
        mov dword ptr fs:[eax], esp
        jmp %(lmmsg)#x
    """, pic=True)
    # GI (v3): GetIncome for crop structures (eax = structure) -> [obj+0x3C] + (owner has an active 325 ? crop count : 0)
    place("gi", """
        push ebx
        push ecx
        push edx
        mov ebx, eax
        movzx ecx, byte ptr [ebx+0x3c]
        mov dl, byte ptr [ebx+0x30]
        cmp dl, 0xff
        je gi_out
        call %(hva)#x
        test al, al
        jz gi_out
        push ecx
        mov eax, ebx
        call %(cropcnt)#x
        pop ecx
        add ecx, eax
    gi_out:
        mov eax, ecx
        pop edx
        pop ecx
        pop ebx
        ret
    """)
    # PAY (v3): turn payout @0x5575542E (eax = player, edx = gold) -> rebuild the player's income total, then add it
    place("pay", """
        push ecx
        push edx
        push eax
        call %(refresh)#x
        pop eax
        pop edx
        pop ecx
        add edx, dword ptr [eax+0xd0]
        ret
    """)
    # P: the city income panel (eax = ebx = city): the crop count, x2 for a Harvest owner
    place("p", """
        call %(cropcnt)#x
        cmp byte ptr [ebx+0x30], 0xff
        je p_out
        push edx
        push eax
        mov dl, byte ptr [ebx+0x30]
        call %(hva)#x
        test al, al
        pop eax
        pop edx
        jz p_out
        add eax, eax
    p_out:
        ret
    """)
    # NT (v2, 2026-10-15): TPlayerCropStructure.NewTurn 0x557A6200 (eax/esi = structure, bl = the player whose turn it is)
    # @0x557A620F `cmp bl,[esi+0x30] / jne epilogue` -> call.  Replays the owner's-turn body (VMT+0x228 CropsEnabled ->
    # VMT+0x22C RegrowCrops) and then ALWAYS re-runs VMT+0x230 UpdateIncome, so the cached income byte [obj+0x3C] (and
    # with it the player's cached total [player+0xD0]) picks up Bountiful Harvest / its removal every turn - vanilla only
    # recomputed it when a crop actually regrew, so full-crop cities and farms never saw the doubling.  Then drops the
    # return address and jumps to the epilogue.  Both TCity.NewTurn (direct call @0x557AB81E) and TFarm (VMT+0x178) run it.
    place("nt", """
        cmp bl, byte ptr [esi+0x30]
        jne nt_out
        mov eax, esi
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x228]
        test al, al
        je nt_inc
        mov eax, esi
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x22c]
    nt_inc:
        mov eax, esi
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x230]
    nt_out:
        add esp, 4
        jmp %(ntend)#x
    """)
    # CG (v8): TCrop.Show replacement (eax = crop, edx = scroll x, ecx = scroll y, [esp+4] = surface; ret 4): the original
    # Show, then - for a crop with an owner structure ([crop+0x1C], player [struct+0x30] != 0xFF) - append (x, y, player)
    # to the PENDING list (capped at CROP_CAP).  No drawing here: the static scene is cached (see v8 note).
    place("cg", """
        push ebx
        mov ebx, eax
        push dword ptr [esp+8]
        call %(ilshow)#x
        mov eax, dword ptr [ebx+0x1c]
        test eax, eax
        jz cg_out
        mov dl, byte ptr [eax+0x30]
        cmp dl, 0xff
        je cg_out
        call $D
        pop ecx
        sub ecx, $D
        mov eax, dword ptr [ecx+%(pend)#x]
        cmp eax, %(cap)d
        jae cg_out
        push esi
        mov esi, eax
        lea eax, [ecx+esi*4+%(pend)#x+4]
        mov byte ptr [eax+2], dl
        mov dl, byte ptr [ebx+0x10]
        mov byte ptr [eax], dl
        mov dl, byte ptr [ebx+0x11]
        mov byte ptr [eax+1], dl
        inc esi
        mov dword ptr [ecx+%(pend)#x], esi
        pop esi
    cg_out:
        pop ebx
        ret 4
    """, pic=True)
    # SX (v8): TAoWHSMap.DrawStaticHSEx (eax = map, edx = surface; the base is an empty ret; runs right after every
    # static redraw): ACTIVE := PENDING, PENDING := empty.
    place("sx", """
        push esi
        push edi
        call $D
        pop edx
        sub edx, $D
        mov ecx, dword ptr [edx+%(pend)#x]
        mov dword ptr [edx+%(pend)#x], 0
        mov dword ptr [edx+%(act)#x], ecx
        lea esi, [edx+%(pend)#x+4]
        lea edi, [edx+%(act)#x+4]
    sx_cp:
        test ecx, ecx
        jz sx_done
        mov eax, dword ptr [esi]
        mov dword ptr [edi], eax
        add esi, 4
        add edi, 4
        dec ecx
        jmp sx_cp
    sx_done:
        pop edi
        pop esi
        ret
    """, pic=True)
    # DX (v8): TAoWHSMap.DrawDynamicHSEx (eax = map, edx = surface; every dynamic frame; the base is an empty ret): for
    # every ACTIVE entry whose owner has an active 325, a pure frame draw of spell 325 gfx slot GLOW_SLOT at the hex
    # (HXtoHP + 16 - scroll [map+0x80]/[map+0x84] + the art's xs/ys), frame = (tick / PERIOD + x + 3y) mod frames.
    # locals: [ebp-4] map, [ebp-8] surface, [ebp-0xc] PIC delta, [ebp-0x10] seq, [ebp-0x14] px, [ebp-0x18] py
    place("dx", """
        push ebp
        mov ebp, esp
        sub esp, 0x18
        push ebx
        push esi
        push edi
        mov dword ptr [ebp-4], eax
        mov dword ptr [ebp-8], edx
        call $D
        pop eax
        sub eax, $D
        mov dword ptr [ebp-0xc], eax
        cmp dword ptr [eax+%(act)#x], 0
        je dx_out
        mov eax, dword ptr [eax+%(hsset)#x]
        mov eax, dword ptr [eax+0x84]
        mov edx, %(id)d
        call %(getspell)#x
        test eax, eax
        jz dx_out
        mov eax, dword ptr [eax+0x2c]
        test eax, eax
        jz dx_out
        mov edx, %(gslot)d
        call %(getseq)#x
        test eax, eax
        jz dx_out
        mov dword ptr [ebp-0x10], eax
        mov eax, dword ptr [eax+0x1c]
        test eax, eax
        jz dx_out
        cmp dword ptr [eax+8], 0
        je dx_out
        xor esi, esi
    dx_loop:
        mov ecx, dword ptr [ebp-0xc]
        cmp esi, dword ptr [ecx+%(act)#x]
        jge dx_out
        lea ebx, [ecx+esi*4+%(act)#x+4]
        mov dl, byte ptr [ebx+2]
        call %(hva)#x
        test al, al
        jz dx_next
        lea eax, [ebp-0x18]
        push eax
        lea ecx, [ebp-0x14]
        movsx eax, byte ptr [ebx]
        movsx edx, byte ptr [ebx+1]
        call %(hxtohp)#x
        mov ecx, dword ptr [ebp-0xc]
        mov eax, dword ptr [ecx+%(map)#x]
        test eax, eax
        jz dx_next
        mov eax, dword ptr [eax+0x40]
        xor edx, edx
        mov ecx, %(gperiod)d
        div ecx
        movsx ecx, byte ptr [ebx]
        add eax, ecx
        movsx ecx, byte ptr [ebx+1]
        lea ecx, [ecx+ecx*2]
        add eax, ecx
        and eax, 0xffff
        mov ecx, dword ptr [ebp-0x10]
        mov ecx, dword ptr [ecx+0x1c]
        mov ecx, dword ptr [ecx+8]
        xor edx, edx
        div ecx
        mov eax, dword ptr [ebp-0x10]
        mov eax, dword ptr [eax+0x1c]
        mov eax, dword ptr [eax+4]
        mov edi, dword ptr [eax+edx*4]
        mov edx, edi
        mov eax, dword ptr [ebp-0x10]
        mov eax, dword ptr [eax+0x10]
        call %(exist)#x
        test al, al
        jz dx_next
        mov edx, edi
        mov eax, dword ptr [ebp-0x10]
        mov eax, dword ptr [eax+0x10]
        call %(libget)#x
        test eax, eax
        jz dx_next
        push dword ptr [ebp-8]
        mov ecx, dword ptr [ebp-4]
        mov edx, dword ptr [ebp-0x14]
        sub edx, dword ptr [ecx+0x80]
        add edx, 0x10
        mov edi, dword ptr [ebp-0x10]
        add edx, dword ptr [edi+0x24]
        mov edi, dword ptr [ebp-0x18]
        sub edi, dword ptr [ecx+0x84]
        add edi, 0x10
        mov ecx, dword ptr [ebp-0x10]
        add edi, dword ptr [ecx+0x28]
        mov ecx, edi
        mov edi, dword ptr [eax]
        call dword ptr [edi+0x84]
    dx_next:
        inc esi
        jmp dx_loop
    dx_out:
        pop edi
        pop esi
        pop ebx
        mov esp, ebp
        pop ebp
        ret
    """, pic=True)
    # GS (v7): City.CityIncome / Farm.FarmIncome per-player sums (@0x557AE220 / 0x557B2F20 `xor eax,eax / mov al,[ebx+0x3c]`,
    # ebx = a TCity / TFarm of that player) -> the structure's GetIncome (VMT+0x1F4 = the GI cave: + crops while 325 is active).
    # Display-side readers only (the exe treasury breakdown); edx is dead there (reloaded each iteration).
    place("gs", """
        mov eax, ebx
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x1f4]
        ret
    """)
    return bytes(out), where


CAVE_OF = {"CE": "ce", "MM": "mm", "ID": "id_", "P1": "p", "P2": "p", "NT": "nt", "PAY": "pay", "S1": "gs", "S2": "gs"}


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
    rstate = {}
    for nm, (va, orig) in RETIRED.items():
        live = bytes(d[vaoff(va):vaoff(va) + len(orig)])
        inzone = live[0] in (0xE8, 0xE9) and ZONE <= va + 5 + struct.unpack_from("<i", live, 1)[0] < ZONE_END
        rstate[nm] = "vanilla" if live == orig else "ours(retired)" if inzone else "OTHER"
    vstate = {}
    for nm, (sva, orig, cave) in VMT_SLOTS.items():
        live = struct.unpack_from("<I", d, data_off(d, sva))[0]
        vstate[nm] = ("vanilla" if live == orig else "ours" if live == where[cave] else "ours(old)" if ZONE <= live < ZONE_END
                      else "OTHER(%#x)" % live)
    bad = [hex(r) for r in rl if ZONE <= r < ZONE_END or any(va <= r < va + len(o) for va, o, _k in CODE_SITES.values())
           or any(va <= r < va + len(o) for va, o in RETIRED.values())]
    noreloc = [nm for nm, (sva, _o, _c) in VMT_SLOTS.items() if sva not in rl]
    print("code sites %s" % cstate)
    print("retired    %s" % rstate)
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
    if bad or noreloc or any(s.startswith("OTHER") for s in list(cstate.values()) + list(vstate.values()) + list(rstate.values())): print("ABORT"); return 1
    if a.revert:
        for nm, (va, orig, _k) in CODE_SITES.items(): d[vaoff(va):vaoff(va) + len(orig)] = orig
        for nm, (va, orig) in RETIRED.items(): d[vaoff(va):vaoff(va) + len(orig)] = orig
        for nm, (sva, orig, _c) in VMT_SLOTS.items(): struct.pack_into("<I", d, data_off(d, sva), orig)
        d[vaoff(ZONE):vaoff(ZONE_END)] = bytes(ZONE_END - ZONE)
        with open(DLL, "r+b") as f: f.write(bytes(d))
        print("reverted"); return 0
    if all(s == "ours" for s in list(cstate.values()) + list(vstate.values())) and all(s == "vanilla" for s in rstate.values()) and zstate == "ours": print("already applied"); return 0
    if zstate == "DIFFERS" and not any(s.startswith("ours") for s in list(cstate.values()) + list(vstate.values()) + list(rstate.values())): print("ABORT (zone not free)"); return 1
    if zstate == "DIFFERS": print("older build of this patch detected -> rewriting zone + every site/slot in place")
    d[vaoff(ZONE):vaoff(ZONE_END)] = bytes(ZONE_END - ZONE); d[vaoff(ZONE):vaoff(ZONE) + len(code)] = code
    for nm, (va, orig, _k) in CODE_SITES.items(): d[vaoff(va):vaoff(va) + len(orig)] = hooks[nm]
    for nm, (va, orig) in RETIRED.items(): d[vaoff(va):vaoff(va) + len(orig)] = orig
    for nm, (sva, orig, cave) in VMT_SLOTS.items(): struct.pack_into("<I", d, data_off(d, sva), where[cave])
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(DLL, ".bak_harvest")
    if not os.path.exists(bak): shutil.copy2(DLL, bak); print("backup ->", bak)
    with open(DLL, "r+b") as f: f.write(bytes(d))
    assert open(DLL, "rb").read() == bytes(d); print("Written and verified"); return 0


if __name__ == "__main__":
    sys.exit(main())
