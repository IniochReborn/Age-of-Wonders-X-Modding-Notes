"""
DROUGHT (spell 391, Fire/Air tier 4) - a GLOBAL enchantment that slowly turns the map to desert (2026-10-14; v2 2026-10-14).
v2: v1's `conv` saved esi AFTER pushing the seven ChangeTerrainEx arguments, so the callee's frame was shifted by one
slot (callback read as 0 -> nothing converted; `ret 0x1C` then left the saved esi under a corrupted return) = an
exception every end turn.  esi is now saved before the arguments.  Cast visual/sound: TSpell.PlayCastEffect
0x5577956C plays the spell record's gfx slot 0 + cue 0 at the caster hex (ValidateObservation 0x557759F8 gated) -
nothing hardcoded; the Drought record carries its own slot 0 / cue 0.
AoWEPACK.dll (file + 0x55700C00).  Pipeline donor = Water Mastery (TWaterMastery, spell 0x2D, pfs key 55): an
untargeted global enchantment with upkeep (pfs tag 0xE -> spell+0x1C -> ench+0x20 via SetupEnchantment).

RE (live binary):
  * Global enchantments are objects in TGlobalMagicControl ([AoWHSMap 0x558FA040]+0x188): list [gmc+0x14] (Count =
    list VMT+0x54, Get = 0x5577E13C(eax list, edx idx)); TGlobalEnchantment: +0x10 bit0 active, +0x14 dword (saved,
    tag 0xF; Water Mastery writes 0xAF, nothing reads it) = OUR MARKER (391), +0x18 byte, +0x19 caster player id,
    +0x1C name (AnsiString, set from the SPELL's name by SetupEnchantment), +0x20 upkeep.  ReadWrite 0x5577DA1C
    serialises +8/+0x18/+0x19/+0x1C/+0x20/+0x14 -> the marker survives saves.  There is NO per-turn slot on the
    enchantment (masteries are passive), and Evil Woods (TUnholyGroundSpell, a TARGETED hex spell) / Pestilence
    (TPestilenceStormSpell, a moving storm HS) are not map-wide converters - Drought gets its own per-turn hook.
  * Water Mastery specifics that must NOT run for Drought: TWaterMasteryEnchantment.Activate 0x557F0874 /
    Deactivate 0x557F08E8 (pmc visibility malus bit 0x08 + UpdateVisibility + IncDoubleSphereManaCount 5) - hooked
    to call only the base TGlobalEnchantment.Activate 0x5577DBA0 / Deactivate 0x5577DC3C when [ench+0x14] == 391;
    TWaterMastery.ExecuteTE 0x557F0A24's mastery message SUB 0x557EF7C0 (fires out, node effects) @0x557F0A4A -
    skipped for spell 391 (ebx = spell there).  TWaterMastery.CreateEnchantment 0x557F0960 (15 B, creates the
    TWaterMasteryEnchantment, class cell 0x557EDFCC - same class kept so saves load) - replaced: after the create,
    [ench+0x14] := 391 when [spell+0x10] == 391 (the spell is in eax at entry).
  * Per turn: TPlayerMagicControl.NewTurn 0x5577CC2C (called from 0x5577D293 for the player whose turn starts, on
    every machine - it also draws the research picks from the SYNCED RNG) - prologue hook (9 B): for the player's
    own ACTIVE Drought enchantment (list scan: marker 391, caster == [player+0xA6], bit0) run the drought.
  * Terrain change = THSMap.ChangeTerrainEx (HSEPack 0x5560C888 = TAoWHSMap VMT +0xD4; the Path of Life dispatch
    0x5578042B shows the call: eax = map, edx = 0, ecx = hx; pushes hy, level, radius, obj, callback, 0, 0; callee
    cleans): for every hex of the spiral up to `radius` (0 = the centre only) it reads terrain/overlay, calls
    callback(eax = obj, edx = field, ecx = &terrain, [esp+4] = &overlay; ret 4), writes them back and does the
    engine's own refresh.  Our callback: surface only, overlay 0 only (roads/bridges/mud untouched); Grass 1 /
    Snow 3 / Steppe 4 / Wasteland 5 / Dirt 0xC -> Desert 2; Water 0 -> Desert only when obj == 1 (the water pick).
    Terrain ids: 0 Water 1 Grass 2 Desert 3 Snow 4 Steppe 5 Wasteland 6 Ice 9 Lava 0xC Dirt.
  * Picks: TAoWHSMap.Random 0x5577827C (eax map, edx range -> eax; the SYNCED stream [map+0x230]), surface level =
    TMapContainer.GetMapLevel thunk 0x557020EC(eax [map+0x10], edx 0); width [level+0xC], height [level+0x10];
    field = TMapLevel.GetField thunk 0x557020DC(eax level, edx x, ecx y).  N_LAND random hexes per turn, each
    converted if it is convertible land with overlay 0; then a 1-in-WATER_ODDS roll for one shallow-water hex
    (up to WATER_TRIES picks).  Deterministic: the same draws happen on every machine.
v7 (2026-10-14, user: "WAY more aggressive; shorelines grow one hex into the sea; one-hex rivers fill; when Drought
is removed the terrain slowly reverts"):
  * Per turn (the caster's own NT, synced RNG): up to PICKS random surface picks, stopping at LAND_CAP land conversions:
      - picked hex is DESERT (natural or ours) -> every convertible land neighbour converts (the desert front creeps);
      - picked hex is convertible land (overlay 0xFF, terrain Grass/Snow/Steppe/Wasteland/Dirt) -> converts if it has a
        desert neighbour, or as one of N_SEED fresh seeds per turn;
      - picked hex is WATER (overlay 0xFF) -> converts (max WATER_CAP per turn) if it has an ORIGINAL land neighbour
        (land that is not itself a Drought marker of water origin): coastlines grow exactly ONE ring and 1-hex rivers
        (water with land on both banks) fill, without the sea creeping further every turn.
    Neighbours: column-parity offsets (odd columns sit half a hex lower: HXtoHP y*32 + 16) from a 12-entry table.
  * Memory + revert: every converted hex gets a TFrozenWaterHS marker (the temp-terrain marker build_raiseterrain_
    matrix.py extended: +0xC countdown, +0xD owner, +0xE restore, +0xF target; saved via tags 0x1E/0x1F/0x6E/0x6F ->
    survives save/load and is identical in MP): +0xE = ORIGINAL terrain | 0x80 (bit 7 = a Drought marker; it also
    keeps water = 0 distinguishable from the vanilla-ice 0), +0xF = Desert 2, +0xD = the caster, +0xC = Random(
    REVERT_SPREAD) + 1.  Hexes that already carry a marker (ice / raise-terrain / ours) are skipped.  The marker's
    own NewTurn (0x55764B98: on its OWNER's turn dec +0xC, at <= 0 MeltIce) is hooked (MT): for a Drought marker
    (+0xE bit 7, +0xF == 2) it HOLDS while the owner still has an ACTIVE Drought (same list scan as NT); otherwise
    it counts down and, at 0, restores the original terrain itself (the vanilla MeltIce recipe: map VMT+0xD0 with
    terrain = +0xE & 0x7F) - cave_tchg (P4 of the raise-terrain script) then frees the marker because the terrain
    left +0xF.  So removal / dispel / disjunction / upkeep failure all revert, staggered over REVERT_SPREAD turns.
    Our markers never reach MeltIce (cave_melt would write 0x80|t).  Any other terrain change on the hex frees its
    marker (cave_tchg) - that hex then keeps its new terrain.
    Caveat: a dead/eliminated caster gets no more turns -> its markers never tick -> the desert stays.
Caves 0x55864000..0x55864900 (zero, reloc-free; v7 grew it from 0x55864400; neighbour table at 0x558648E0).  Reloc 0x557F0965 (the class-cell absolute inside the replaced
CreateEnchantment bytes) neutralised 3 -> 0 on apply, restored on revert.  Backup <game>\\backup\\AoWEPACK.dll.bak_drought.
Dry-run default; --apply / --revert / --dis.
Pipeline entry (patch_dual_sphere_spells_v1.py): donor "TWaterMastery", pfs_donor 55, tc_type None, sphere 20, tier 4,
mana 75, research 250, upkeep 15, pokes [(0x34, 4, 0xFFFFFFFF)] (AI priority -1 = the AI never casts it).
Caveats: hexes under cities/structures are not excluded (the engine writes the terrain byte under them like Path of
Life does); the AI never casts Drought; the desert spreads only on the surface.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DEFAULT_DLL = game_file("AoWEPACK.dll")
BAK_SUFFIX = ".bak_drought"
BASE, CODE_V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x55864000, 0x55864900
SPELL_ID = 391
PICKS, LAND_CAP, WATER_CAP, N_SEED, REVERT_SPREAD = 3000, 300, 60, 12, 8   # v8 (user: way more aggressive) aggressiveness / revert knobs
ICE_CAP, STEPPE = 4, 4                                                    # v8: ice melts SLOWLY (<= 4 hexes / turn) to water; snow -> steppe
G_ICE = 0x558FA36C                                                        # v8: ice-melt counter (BSS page slack after G_NY)
G_LCAP, G_WCAP, G_NSEEDS, G_ICAP = 0x558FA370, 0x558FA374, 0x558FA378, 0x558FA37C   # v9: per-turn caps computed from the map AREA
LAND_PM, WATER_PM, PICKS_PM, SEED_DIV, ICE_DIV = 40, 8, 750, 400, 1000   # v9 (user: a bit too fast; scale with map size): caps per mille of w*h; seeds = area/400, ice = area/1000 (each min 1)
TAB_VA = 0x558648E0                                                         # 12 x (dx, dy) signed bytes: even columns, then odd
NBR_TAB = bytes([0, 0xFF, 1, 0xFF, 1, 0, 0, 1, 0xFF, 0, 0xFF, 0xFF,       # even x: N, NE, SE, S, SW, NW
                 0, 0xFF, 1, 0, 1, 1, 0, 1, 0xFF, 1, 0xFF, 0])             # odd x:  N, NE, SE, S, SW, NW
FINDHS, TOBJCREATE, PLACEHX = 0x55701FFC, 0x55703064, 0x557025F4           # HSEngine.TMapField.FindOwnedHS / Engine.TEObject.Create / HSEngine.THSMap.PlaceHX (import table verified)
FW_CLASSREF = 0x55714774                                                    # holder of the TFrozenWaterHS classref (0x557147B4)
MAPPTR = 0x558E9494                                                         # map = *(*MAPPTR) (PlaceHX's map, as the raise-terrain spawn uses it)
G_OWNER, G_LAND, G_WATER, G_SEED, G_CX, G_CY, G_K, G_ORIG, G_KIND, G_NX, G_NY = range(0x558FA340, 0x558FA36C, 4)   # BSS page slack (section ends 0x558FA231)
H_MT = (0x55764B98, bytes.fromhex("3a500d750e"), 0x55764B9D)                 # TFrozenWaterHS.NewTurn: cmp dl,[eax+0xD] / jne ret
N_LAND, WATER_ODDS, WATER_TRIES, LAND_TRIES = 6, 4, 8, 60   # v3: keep picking until N_LAND hexes convert or LAND_TRIES picks are spent (v2 made N_LAND blind picks: most land carries an overlay or a non-convertible terrain, so few or none converted per turn)          # land hexes per turn; 1-in-N chance of one water hex; picks to find water
HILLS = 2    # v10 2026-10-14 (user: hills change too): overlay 2 = hill (0 mountain, 0xFF bare) accepted by both filters + the callback
DESERT = 2   # v6 2026-10-14: 'no overlay' on the strategic map is 0xFF, not 0 (live counters: 420 picks, 7 passes, last overlay 0xFF) - filter + callback now require overlay 0xFF
TRACE = 0x558FA2E0      # v5t diagnostic counters (BSS): +0 NT entries, +4 active Drought matches, +8 picks, +0xC filter passes, +0x10/+0x14 last picked terrain/overlay, +0x18 terrain read back after conv, +0x1C player id, +0x20 last ench caster, +0x24 last ench flags
MAP_GLOBAL = 0x558FA040
MAP_RANDOM = 0x5577827C
GETMAPLEVEL, LEVEL_GETFIELD = 0x557020EC, 0x557020DC   # v5 2026-10-14: the REAL HSEngine.TMapContainer.GetMapLevel / TMapLevel.GetField thunks (0x55701CEC / 0x55701CDC were TXYLList.Error / TXYLList.Clear -> EListError every turn, found with the VEH logger)
LIST_GET = 0x5577E13C
GE_ACTIVATE, GE_DEACTIVATE = 0x5577DBA0, 0x5577DC3C
WM_ENCH_CELL, WM_ENCH_CREATE = 0x557EDFCC, 0x557F06F4
MASTERY_SUB = 0x557EF7C0
CHANGE_TERRAIN_SLOT = 0xD4
G_X, G_Y, G_TRIES = 0x558FA2D0, 0x558FA2D4, 0x558FA2D8                   # BSS slack scratch (the forge/arms flags use 0x558FA2C0..C8): the picked hex
# hook sites: (va, original bytes, resume va)
H_NT = (0x5577CC2C, bytes.fromhex("5356575583c4f88bf0"), 0x5577CC35)              # TPlayerMagicControl.NewTurn prologue
H_CE = (0x557F0960, bytes.fromhex("33c9b201a1ccdf7e55e886fdffffc3"), None)        # TWaterMastery.CreateEnchantment (whole body)
H_AC = (0x557F0874, bytes.fromhex("538bd88bc3e822d3f8ff"), 0x557F087E)            # TWaterMasteryEnchantment.Activate prologue
H_DA = (0x557F08E8, bytes.fromhex("538bd88bc3e84ad3f8ff"), 0x557F08F2)            # TWaterMasteryEnchantment.Deactivate prologue
H_EX = (0x557F0A4A, bytes.fromhex("b2068a4624e86cedffff"), 0x557F0A54)            # TWaterMastery.ExecuteTE: the mastery message
RELOC_NEUTRALISE = [0x557F0965]                                                    # inside H_CE's bytes
SITES = {"NT": H_NT, "CE": H_CE, "AC": H_AC, "DA": H_DA, "EX": H_EX, "MT": H_MT}

ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, va):
    return bytes(ks.asm(src, va)[0])


def asm_delta(src, va, reg="ebx"):
    """`call $D / pop REG / sub REG, $D` PIC idiom (two-pass; keystone hangs on a label used as an immediate)."""
    pops = {"ebx": "5b", "ecx": "59", "edx": "5a"}; subs = {"ebx": "81eb", "ecx": "81e9", "edx": "81ea"}
    s1 = src.replace("call $D", ".byte 0xe8, 0, 0, 0, 0").replace("sub %s, $D" % reg, "sub %s, 0x7fffffff" % reg)
    b = bytearray(ks.asm(s1, va)[0])
    anchor = bytes.fromhex("e800000000" + pops[reg] + subs[reg] + "ffffff7f")
    k = b.find(anchor); assert k >= 0, "delta anchor not found"
    struct.pack_into("<I", b, k + 8, va + k + 5)
    return bytes(b)


def build_nt(va, cb_va):
    """NewTurn prologue replay + the drought for the player's active Drought enchantment (v7).  eax = pmc at entry."""
    src = """
        push ebx
        push esi
        push edi
        push ebp
        add esp, -8
        mov esi, eax
        pushad
        call $D
        pop ebx
        sub ebx, $D
        inc dword ptr [ebx+%(tr)#x]
        mov eax, [esi+0x10]
        movsx edi, byte ptr [eax+0xa6]
        mov [ebx+%(tr)#x+0x1c], edi
        mov eax, [ebx+%(map)#x]
        mov eax, [eax+0x188]
        mov esi, [eax+0x14]
        mov eax, esi
        mov edx, [eax]
        call dword ptr [edx+0x54]
        mov ecx, eax
    scan:
        dec ecx
        js none
        push ecx
        mov eax, esi
        mov edx, ecx
        call %(get)#x
        pop ecx
        cmp dword ptr [eax+0x14], %(id)d
        jne scan
        movsx edx, byte ptr [eax+0x19]
        cmp edx, edi
        jne scan
        mov [ebx+%(tr)#x+0x20], edx
        movzx edx, byte ptr [eax+0x10]
        mov [ebx+%(tr)#x+0x24], edx
        test byte ptr [eax+0x10], 1
        jz scan
        inc dword ptr [ebx+%(tr)#x+4]
        call drought
    none:
        popad
        jmp %(resume)#x
    drought:
        mov eax, [ebx+%(map)#x]
        mov eax, [eax+0x10]
        xor edx, edx
        call %(getlevel)#x
        test eax, eax
        jz dret
        mov esi, eax
        mov [ebx+%(gown)#x], edi
        xor eax, eax
        mov [ebx+%(gland)#x], eax
        mov [ebx+%(gwat)#x], eax
        mov [ebx+%(gseed)#x], eax
        mov [ebx+%(gice)#x], eax
        mov eax, [esi+0xc]
        imul eax, dword ptr [esi+0x10]
        push eax
        imul eax, eax, %(landpm)d
        xor edx, edx
        mov ecx, 1000
        div ecx
        or eax, 1
        mov [ebx+%(glcap)#x], eax
        mov eax, [esp]
        imul eax, eax, %(waterpm)d
        xor edx, edx
        div ecx
        or eax, 1
        mov [ebx+%(gwcap)#x], eax
        mov eax, [esp]
        imul eax, eax, %(pickspm)d
        xor edx, edx
        div ecx
        or eax, 1
        mov [ebx+%(gtries)#x], eax
        mov eax, [esp]
        xor edx, edx
        mov ecx, %(seeddiv)d
        div ecx
        or eax, 1
        mov [ebx+%(gnseeds)#x], eax
        pop eax
        xor edx, edx
        mov ecx, %(icediv)d
        div ecx
        or eax, 1
        mov [ebx+%(gicap)#x], eax
    lp:
        call pick
        inc dword ptr [ebx+%(tr)#x+8]
        test eax, eax
        jz nx
        mov edi, eax
        mov al, byte ptr [edi+0x15]
        cmp al, 0xff
        je ov1
        cmp al, 2
        jne nx
    ov1:
        movzx eax, byte ptr [edi+0x14]
        cmp al, 2
        je spread
        test al, al
        je water
        cmp al, 6
        je ice
        call island
        test eax, eax
        jz nx
        mov edx, [ebx+%(gx)#x]
        mov ecx, [ebx+%(gy)#x]
        call desnbr
        test eax, eax
        jnz doland
        push eax
        mov eax, [ebx+%(gnseeds)#x]
        cmp [ebx+%(gseed)#x], eax
        pop eax
        jae nx
        inc dword ptr [ebx+%(gseed)#x]
    doland:
        mov edx, [ebx+%(gx)#x]
        mov ecx, [ebx+%(gy)#x]
        xor eax, eax
        call cvt
        jmp nx
    water:
        push eax
        mov eax, [ebx+%(gwcap)#x]
        cmp [ebx+%(gwat)#x], eax
        pop eax
        jae nx
        mov edx, [ebx+%(gx)#x]
        mov ecx, [ebx+%(gy)#x]
        call waterok
        test eax, eax
        jz nx
        mov edx, [ebx+%(gx)#x]
        mov ecx, [ebx+%(gy)#x]
        mov eax, 1
        call cvt
        jmp nx
    ice:
        push eax
        mov eax, [ebx+%(gicap)#x]
        cmp [ebx+%(gice)#x], eax
        pop eax
        jae nx
        inc dword ptr [ebx+%(gice)#x]
        mov edx, [ebx+%(gx)#x]
        mov ecx, [ebx+%(gy)#x]
        mov eax, 2
        call cvt
        jmp nx
    spread:
        inc dword ptr [ebx+%(tr)#x+0x14]
        mov eax, [ebx+%(gx)#x]
        mov [ebx+%(gcx)#x], eax
        mov eax, [ebx+%(gy)#x]
        mov [ebx+%(gcy)#x], eax
        mov dword ptr [ebx+%(gk)#x], 0
    sl:
        mov edx, [ebx+%(gcx)#x]
        mov ecx, [ebx+%(gcy)#x]
        mov eax, [ebx+%(gk)#x]
        call nbr
        mov [ebx+%(gnx)#x], edx
        mov [ebx+%(gny)#x], ecx
        call getf
        test eax, eax
        jz sn
        mov dl, byte ptr [eax+0x15]
        cmp dl, 0xff
        je ov2
        cmp dl, 2
        jne sn
    ov2:
        movzx eax, byte ptr [eax+0x14]
        call island
        test eax, eax
        jz sn
        mov edx, [ebx+%(gnx)#x]
        mov ecx, [ebx+%(gny)#x]
        xor eax, eax
        call cvt
    sn:
        push eax
        mov eax, [ebx+%(glcap)#x]
        cmp [ebx+%(gland)#x], eax
        pop eax
        jae dret
        inc dword ptr [ebx+%(gk)#x]
        cmp dword ptr [ebx+%(gk)#x], 6
        jb sl
    nx:
        push eax
        mov eax, [ebx+%(glcap)#x]
        cmp [ebx+%(gland)#x], eax
        pop eax
        jae dret
        dec dword ptr [ebx+%(gtries)#x]
        jnz lp
    dret:
        ret
    island:
        cmp al, 1
        je is_y
        cmp al, 3
        je is_y
        cmp al, 4
        je is_y
        cmp al, 0xc
        je is_y
        xor eax, eax
        ret
    is_y:
        mov eax, 1
        ret
    getf:
        test edx, edx
        js gf_no
        test ecx, ecx
        js gf_no
        cmp edx, [esi+0xc]
        jge gf_no
        cmp ecx, [esi+0x10]
        jge gf_no
        mov eax, esi
        call %(getfield)#x
        ret
    gf_no:
        xor eax, eax
        ret
    nbr:
        test edx, 1
        jz nb_even
        add eax, 6
    nb_even:
        push edi
        lea edi, [ebx+%(tab)#x]
        lea edi, [edi+eax*2]
        movsx eax, byte ptr [edi]
        add edx, eax
        movsx eax, byte ptr [edi+1]
        add ecx, eax
        pop edi
        ret
    desnbr:
        push edi
        push edx
        push ecx
        xor edi, edi
    dn_l:
        mov edx, [esp+4]
        mov ecx, [esp]
        mov eax, edi
        call nbr
        call getf
        test eax, eax
        jz dn_n
        cmp byte ptr [eax+0x14], 2
        je dn_y
    dn_n:
        inc edi
        cmp edi, 6
        jb dn_l
        xor eax, eax
        jmp dn_out
    dn_y:
        mov eax, 1
    dn_out:
        pop ecx
        pop edx
        pop edi
        ret
    waterok:
        push edi
        push edx
        push ecx
        xor edi, edi
    wo_l:
        mov edx, [esp+4]
        mov ecx, [esp]
        mov eax, edi
        call nbr
        call getf
        test eax, eax
        jz wo_n
        movzx edx, byte ptr [eax+0x14]
        test edx, edx
        jz wo_n
        cmp edx, 6
        je wo_n
        cmp edx, 0xa
        je wo_n
        cmp edx, 0xd
        je wo_n
        cmp edx, 0xf
        je wo_n
        mov edx, [ebx+%(cls)#x]
        call %(findhs)#x
        test eax, eax
        jz wo_y
        cmp byte ptr [eax+0xf], 2
        jne wo_y
        cmp byte ptr [eax+0xe], 0x80
        je wo_n
    wo_y:
        mov eax, 1
        jmp wo_out
    wo_n:
        inc edi
        cmp edi, 6
        jb wo_l
        xor eax, eax
    wo_out:
        pop ecx
        pop edx
        pop edi
        ret
    cvt:
        pushad
        mov [ebx+%(gkind)#x], eax
        mov [ebx+%(gx)#x], edx
        mov [ebx+%(gy)#x], ecx
        call getf
        test eax, eax
        jz cv_out
        mov edi, eax
        mov edx, [ebx+%(cls)#x]
        call %(findhs)#x
        test eax, eax
        jnz cv_out
        movzx eax, byte ptr [edi+0x14]
        mov [ebx+%(gorig)#x], eax
        mov eax, [ebx+%(gkind)#x]
        call conv
        mov edx, [ebx+%(gx)#x]
        mov ecx, [ebx+%(gy)#x]
        call getf
        test eax, eax
        jz cv_out
        mov edi, eax
        movzx eax, byte ptr [edi+0x14]
        cmp eax, [ebx+%(gorig)#x]
        je cv_out
        cmp dword ptr [ebx+%(gkind)#x], 0
        jne cv_w
        inc dword ptr [ebx+%(gland)#x]
        inc dword ptr [ebx+%(tr)#x+0xc]
        jmp cv_m
    cv_w:
        inc dword ptr [ebx+%(gwat)#x]
        inc dword ptr [ebx+%(tr)#x+0x10]
    cv_m:
        xor ecx, ecx
        mov dl, 1
        mov eax, [ebx+%(cls)#x]
        call %(create)#x
        push eax
        movzx ecx, byte ptr [edi+0x11]
        push ecx
        movzx ecx, byte ptr [edi+0x12]
        push ecx
        movzx ecx, byte ptr [edi+0x10]
        mov edx, [esp+8]
        mov eax, [ebx+%(mapptr)#x]
        mov eax, [eax]
        call %(placehx)#x
        mov eax, [ebx+%(map)#x]
        mov edx, %(rspread)d
        call %(rnd)#x
        inc eax
        pop edx
        mov [edx+0xc], al
        mov al, byte ptr [ebx+%(gown)#x]
        mov [edx+0xd], al
        mov al, byte ptr [ebx+%(gorig)#x]
        or al, 0x80
        mov [edx+0xe], al
        mov al, byte ptr [edi+0x14]
        mov [edx+0xf], al
    cv_out:
        popad
        ret
    pick:
        mov eax, [ebx+%(map)#x]
        mov edx, [esi+0xc]
        call %(rnd)#x
        mov [ebx+%(gx)#x], eax
        mov eax, [ebx+%(map)#x]
        mov edx, [esi+0x10]
        call %(rnd)#x
        mov [ebx+%(gy)#x], eax
        mov ecx, eax
        mov edx, [ebx+%(gx)#x]
        mov eax, esi
        call %(getfield)#x
        ret
    conv:
        push esi
        push dword ptr [ebx+%(gy)#x]
        push 0
        push 0
        push eax
        lea eax, [ebx+%(cb)#x]
        push eax
        push 0
        push 0
        mov eax, [ebx+%(map)#x]
        mov ecx, [ebx+%(gx)#x]
        xor edx, edx
        mov esi, [eax]
        call dword ptr [esi+%(slot)#x]
        pop esi
        ret
    """ % {"tr": TRACE, "map": MAP_GLOBAL, "get": LIST_GET, "id": SPELL_ID, "resume": H_NT[2], "getlevel": GETMAPLEVEL,
           "rnd": MAP_RANDOM, "getfield": LEVEL_GETFIELD, "cb": cb_va, "slot": CHANGE_TERRAIN_SLOT, "gx": G_X, "gy": G_Y,
           "gtries": G_TRIES, "gice": G_ICE, "icecap": ICE_CAP, "picks": PICKS, "glcap": G_LCAP, "gwcap": G_WCAP, "gnseeds": G_NSEEDS, "gicap": G_ICAP, "landpm": LAND_PM, "waterpm": WATER_PM, "pickspm": PICKS_PM, "seeddiv": SEED_DIV, "icediv": ICE_DIV, "lcap": LAND_CAP, "wcap": WATER_CAP, "nseed": N_SEED, "rspread": REVERT_SPREAD,
           "gown": G_OWNER, "gland": G_LAND, "gwat": G_WATER, "gseed": G_SEED, "gcx": G_CX, "gcy": G_CY, "gk": G_K,
           "gorig": G_ORIG, "gkind": G_KIND, "gnx": G_NX, "gny": G_NY, "tab": TAB_VA, "cls": FW_CLASSREF, "findhs": FINDHS,
           "create": TOBJCREATE, "placehx": PLACEHX, "mapptr": MAPPTR, "desert": DESERT}
    return asm_delta(src, va)


def build_mt(va):
    """TFrozenWaterHS.NewTurn hook (eax = marker, dl = the player whose turn it is): Drought markers hold while their owner
    has an active Drought; afterwards they count down and restore the original terrain themselves."""
    src = """
        cmp dl, byte ptr [eax+0xd]
        jne m_ret
        test byte ptr [eax+0xe], 0x80
        jz m_van
        push ebx
        push esi
        push edi
        push ebp
        mov ebp, eax
        call $D
        pop ebx
        sub ebx, $D
        movsx edi, byte ptr [ebp+0xd]
        mov eax, [ebx+%(map)#x]
        mov eax, [eax+0x188]
        mov esi, [eax+0x14]
        mov eax, esi
        mov edx, [eax]
        call dword ptr [edx+0x54]
        mov ecx, eax
    m_scan:
        dec ecx
        js m_none
        push ecx
        mov eax, esi
        mov edx, ecx
        call %(get)#x
        pop ecx
        cmp dword ptr [eax+0x14], %(id)d
        jne m_scan
        movsx edx, byte ptr [eax+0x19]
        cmp edx, edi
        jne m_scan
        test byte ptr [eax+0x10], 1
        jz m_scan
        jmp m_out
    m_none:
        dec byte ptr [ebp+0xc]
        cmp byte ptr [ebp+0xc], 0
        jg m_out
        mov eax, ebp
        mov edx, [eax]
        call dword ptr [edx+0x78]
        movsx eax, al
        push eax
        mov eax, ebp
        mov edx, [eax]
        call dword ptr [edx+0x7c]
        movsx eax, al
        push eax
        push 0
        movzx eax, byte ptr [ebp+0xe]
        and eax, 0x7f
        push eax
        mov eax, ebp
        mov edx, [eax]
        call dword ptr [edx+0x74]
        movsx ecx, al
        mov edx, ebp
        mov eax, [ebx+%(map)#x]
        mov esi, [eax]
        call dword ptr [esi+0xd0]
    m_out:
        pop ebp
        pop edi
        pop esi
        pop ebx
    m_ret:
        ret
    m_van:
        jmp %(resume)#x
    """ % {"desert": DESERT, "map": MAP_GLOBAL, "get": LIST_GET, "id": SPELL_ID, "resume": H_MT[2]}
    return asm_delta(src, va)


def build_cb(va):
    """ChangeTerrainEx callback: eax = obj (1 = the water pick), edx = field, ecx = &terrain, [esp+4] = &overlay; ret 4."""
    src = """
        push ebp
        mov ebp, esp
        push ebx
        cmp byte ptr [edx+0x12], 0
        jne cdone
        mov ebx, [ebp+8]
        cmp byte ptr [ebx], 0xff
        je cok
        cmp byte ptr [ebx], 2
        jne cdone
    cok:
        movzx ebx, byte ptr [ecx]
        cmp eax, 2
        je cice
        test bl, bl
        jne land
        test eax, eax
        jz cdone
        mov byte ptr [ecx], %(desert)d
        jmp cdone
    cice:
        cmp bl, 6
        jne cdone
        mov byte ptr [ecx], 0
        jmp cdone
    land:
        cmp bl, 3
        jne cl2
        mov byte ptr [ecx], %(steppe)d
        jmp cdone
    cl2:
        cmp bl, 1
        je cset
        cmp bl, 4
        je cset
        cmp bl, 0xc
        jne cdone
    cset:
        mov byte ptr [ecx], %(desert)d
    cdone:
        pop ebx
        pop ebp
        ret 4
    """ % {"desert": DESERT, "steppe": STEPPE}
    return asm(src, va)


def build_ce(va):
    """CreateEnchantment replacement: eax = spell.  Creates the TWaterMasteryEnchantment as vanilla, marks ours, and (v4) copies the spell name [spell+8] into the enchantment name [ench+0x1C] - TWaterMasteryEnchantment.Create 0x557F06F4 HARDCODES "Water Mastery" there (event log + Magic tab upkeep list read it)."""
    src = """
        push ebx
        mov ebx, eax
        call $D
        pop ecx
        sub ecx, $D
        mov eax, [ecx+%(cell)#x]
        xor ecx, ecx
        mov dl, 1
        call %(create)#x
        cmp dword ptr [ebx+0x10], %(id)d
        jne ok
        mov dword ptr [eax+0x14], %(id)d
        push eax
        lea eax, [eax+0x1c]
        mov edx, [ebx+8]
        call %(lstrasg)#x
        pop eax
    ok:
        pop ebx
        ret
    """ % {"cell": WM_ENCH_CELL, "create": WM_ENCH_CREATE, "id": SPELL_ID, "lstrasg": 0x55701150}
    return asm_delta(src, va, reg="ecx")


def build_acda(va, base, resume):
    src = """
        push ebx
        mov ebx, eax
        cmp dword ptr [ebx+0x14], %(id)d
        jne van
        mov eax, ebx
        call %(base)#x
        mov al, 1
        pop ebx
        ret
    van:
        mov eax, ebx
        call %(base)#x
        jmp %(resume)#x
    """ % {"id": SPELL_ID, "base": base, "resume": resume}
    return asm(src, va)


def build_ex(va):
    src = """
        cmp dword ptr [ebx+0x10], %(id)d
        je skip
        mov dl, 6
        mov al, byte ptr [esi+0x24]
        call %(sub)#x
    skip:
        jmp %(resume)#x
    """ % {"id": SPELL_ID, "sub": MASTERY_SUB, "resume": H_EX[2]}
    return asm(src, va)


def reloc_entries(d):
    pe = struct.unpack_from("<I", d, 0x3C)[0]; opt = struct.unpack_from("<H", d, pe + 20)[0]; nsec = struct.unpack_from("<H", d, pe + 6)[0]
    secs = [struct.unpack_from("<IIII", d, pe + 24 + opt + 40 * k + 8) for k in range(nsec)]
    rrva, rsz = struct.unpack_from("<II", d, pe + 24 + 0x88)
    def r2f(rva):
        for vs, va, rs, ro in secs:
            if va <= rva < va + max(vs, rs): return ro + rva - va
    p, end, out = r2f(rrva), r2f(rrva) + rsz, {}
    while p < end:
        page, size = struct.unpack_from("<II", d, p)
        if size < 8: break
        for q in range(p + 8, p + size, 2):
            e = struct.unpack_from("<H", d, q)[0]
            if e >> 12 in (0, 3): out[BASE + page + (e & 0xFFF)] = (q, e >> 12)
        p += size
    return out


def write_inplace(path, data):
    with open(path, "r+b") as f:
        f.seek(0); f.write(data); f.truncate(len(data))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dll", default=DEFAULT_DLL)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--force-revert", action="store_true", help="restore every site to its original bytes, zero the whole zone and restore the reloc, whatever build is applied (use when an older build is in and its old-state script is gone)")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    d = open(a.dll, "rb").read()
    # layout: CB first (the NT cave references it), then NT, CE, AC, DA, EX (16-aligned)
    cb_va = ZONE; cb = build_cb(cb_va); off = (len(cb) + 15) & ~15
    nt_va = ZONE + off; nt = build_nt(nt_va, cb_va); off += (len(nt) + 15) & ~15
    ce_va = ZONE + off; ce = build_ce(ce_va); off += (len(ce) + 15) & ~15
    ac_va = ZONE + off; ac = build_acda(ac_va, GE_ACTIVATE, H_AC[2]); off += (len(ac) + 15) & ~15
    da_va = ZONE + off; da = build_acda(da_va, GE_DEACTIVATE, H_DA[2]); off += (len(da) + 15) & ~15
    ex_va = ZONE + off; ex = build_ex(ex_va); off += (len(ex) + 15) & ~15
    mt_va = ZONE + off; mt = build_mt(mt_va); off += len(mt)
    assert ZONE + off <= TAB_VA, hex(ZONE + off)
    assert ZONE + off <= ZONE_END, hex(ZONE + off)
    zone = bytearray(ZONE_END - ZONE)
    for va, c in ((cb_va, cb), (nt_va, nt), (ce_va, ce), (ac_va, ac), (da_va, da), (ex_va, ex), (mt_va, mt), (TAB_VA, NBR_TAB)): zone[va - ZONE:va - ZONE + len(c)] = c
    off = TAB_VA - ZONE + len(NBR_TAB)
    zone = bytes(zone[:off])
    caves = {"NT": nt_va, "CE": ce_va, "AC": ac_va, "DA": da_va, "EX": ex_va, "MT": mt_va}
    hooks = {k: b"\xe9" + struct.pack("<i", caves[k] - (SITES[k][0] + 5)) + b"\x90" * (len(SITES[k][1]) - 5) for k in SITES}
    states = {}
    for k, (site, orig, _r) in SITES.items():
        live = d[site - CODE_V2F:site - CODE_V2F + len(orig)]
        states[k] = "vanilla" if live == orig else "ours" if live == hooks[k] else "OTHER"
    zl = d[ZONE - CODE_V2F:ZONE_END - CODE_V2F]
    zstate = "zero" if not any(zl) else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else "DIFFERS"
    rl = reloc_entries(d)
    bad = [hex(r) for r, (q, t) in rl.items() if t == 3 and (ZONE <= r < ZONE_END or any(s <= r < s + len(o) for s, o, _ in SITES.values()) and r not in RELOC_NEUTRALISE)]
    neut = ["%#x:%s" % (r, "type3" if rl.get(r, (0, -1))[1] == 3 else "neutralised" if rl.get(r, (0, -1))[1] == 0 else "missing") for r in RELOC_NEUTRALISE]
    print("sites %s | zone %s (%d B: cb @%#x nt @%#x ce @%#x ac @%#x da @%#x ex @%#x mt @%#x tab @%#x) | relocs %s | neutralise %s" % (
        states, zstate, len(zone), cb_va, nt_va, ce_va, ac_va, da_va, ex_va, mt_va, TAB_VA, bad or "none", neut))
    if a.force_revert: a.revert = True
    elif bad or "OTHER" in states.values(): print("ABORT"); return 1
    if a.dis:
        import capstone
        for lab, va, c in (("CB", cb_va, cb), ("NT", nt_va, nt), ("CE", ce_va, ce), ("AC", ac_va, ac), ("DA", da_va, da), ("EX", ex_va, ex), ("MT", mt_va, mt)):
            print("--- cave", lab)
            for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(c, va): print("   %08X  %-16s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    out = bytearray(d)
    if a.revert:
        for k, (site, orig, _r) in SITES.items(): out[site - CODE_V2F:site - CODE_V2F + len(orig)] = orig
        out[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
        for r in RELOC_NEUTRALISE:
            if r in rl: q, t = rl[r]; out[q:q + 2] = struct.pack("<H", (3 << 12) | (r & 0xFFF))
        write_inplace(a.dll, bytes(out)); print("reverted"); return 0
    if all(s == "ours" for s in states.values()) and zstate == "ours": print("already applied"); return 0
    if all(s == "ours" for s in states.values()) and zstate == "DIFFERS": print("an OLDER build (v1) is applied: the hooks are identical, --apply re-syncs the zone in place (--revert then --apply is equivalent)")
    out[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE); out[ZONE - CODE_V2F:ZONE - CODE_V2F + len(zone)] = zone
    for k, (site, orig, _r) in SITES.items(): out[site - CODE_V2F:site - CODE_V2F + len(orig)] = hooks[k]
    for r in RELOC_NEUTRALISE:
        if r in rl: q, t = rl[r]; out[q:q + 2] = struct.pack("<H", (0 << 12) | (r & 0xFFF))
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(a.dll, BAK_SUFFIX)
    if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    write_inplace(a.dll, bytes(out)); assert open(a.dll, "rb").read() == bytes(out); print("Written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
