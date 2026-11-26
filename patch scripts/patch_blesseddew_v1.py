"""
BLESSED DEW (spell 326, Life/Water sphere pair 12, tier 3) - global enchantment (2026-10-15).  AoWEPACK.dll only.

Spec (user): global spell, research 150, cost 50, upkeep 7.  Friendly units heal 5 HP at the beginning of each turn.

DONOR = Death Mastery (TDeathMastery: spell class cell 0x557EEF90, Create 0x557F27A8, registered @0x557F3A89 in the
global-spell loop; spell id 0x3E = 62, Spells.pfs key 72).  Air/Water/Fire/Earth Mastery are taken (Overgrowth, Drought,
Steam Power, Golden Age) and Life Mastery (0x3D, key 71) goes to another Life/Water spell.  Recipe = patch_goldenage_v1.py:
  CE  TDeathMastery.CreateEnchantment 0x557F285C (spell VMT+0xA0; `xor ecx,ecx / mov dl,1 / mov eax,[0x557EEE64] /
      call TDeathMasteryEnchantment.Create 0x557F2300 / ret`): `jmp cave` (5 B; the reloc'd cell operand behind it is
      dead code).  The cave replays it (cell read PIC) and for [spell+0x10] == 326 writes the MARKER [ench+0x14] := 326
      (vanilla 0xAF; serialised -> survives saves) and copies the spell name [spell+8] into [ench+0x1C] (the ctor
      hardcodes "Death Mastery").
  AC/DE  TDeathMasteryEnchantment VMT 0x557EEEA4 +0x68 Activate 0x557F2480 / +0x60 Deactivate 0x557F24E8 (sphere
      mastery counter 0x5577E220/0x5577E228 (gmc, dl 1), the player's magic flag 0x20 [pmc+0x44], and on deactivate a
      0x20020101 refresh broadcast) -> VMT slots re-pointed: marker 326 -> the BASE TGlobalEnchantment.Activate
      0x5577DBA0 / Deactivate 0x5577DC3C only; anything else -> the Death Mastery originals.  No flag 0x20 -> none of
      Death Mastery's world effects (darkness, curses, ...) ever run for Blessed Dew.
  CHK +0x64 0x557F23A8 ("already active": base check 0x5577DAE8, then flag 0x20; message branch 0x557F2402 builds
      "<VMT+0x4C name> is already active" into [edi] and returns 0): marker 326 -> base check, then our once-per-player
      test (an ACTIVE 326 cast by this player); refused through Death Mastery's own message branch, entered after
      replaying its prologue (frame -0x18, [ebp-8]/[ebp-0x14]/[ebp-0x18] zeroed, SEH handler 0x557F2470 read PIC).
  MM  TDeathMastery.ExecuteTE 0x557F2944: `call 0x557EF7C0` @0x557F2968 (the sphere mastery message, dl = 2; esi = spell)
      -> skipped for spell 326.
  Kept from the donor: the base execute, the event-log line, sound 0 and the map-wide cast animation (TE callback
  0x557F286C draws Random(3) = gfx slots 0..2 of the spell's OWN record; Death Mastery's are kind-0 single images,
  MAGIC 167-169 ~200x100 at ~-99/-51).

'Is Blessed Dew active for player P' (bda, dl = P): scan TGlobalMagicControl [[AoWHSMap 0x558FA040]+0x188] list +0x14
(Count = VMT+0x54, Get 0x5577E13C) for an enchantment with bit0 of [e+0x10] (active), [e+0x14] == 326 and caster
[e+0x19] == P (player-list index; the unit owner byte [unit+0x24] is the same index space - TAbstractUnit.NewTurn and
the Death Activate both resolve it through [map+0x140] Get 0x557544D0).  Synced state only -> MP-safe, no RNG.

EFFECT - +5 HP per turn:
  TAbstractUnit.NewTurn 0x55780D4C = VMT+0x13C of TAbstractUnit/TUnit/TAdjustableUnit (THero/TLeader 0x55787FCC call it
  through cave 0x55814900 first) runs from the unit message handler 0x55781238 on msg 0x20020002 (the new-turn
  broadcast, every peer).  For the OWNER's turn (dl == [unit+0x24]) it resets moves, then the vanilla heal: unless
  Cursed (0x5D), HP += max(1, 10 % of max HP) (Regeneration 0x31: back to full) via SetHitPoints VMT+0xE4.  Both heal
  branches (and the 'already full / cursed' skip) converge at 0x55780DFE `mov edx,0x6D` (5 B, no reloc, a jump target)
  -> `call cave` (HL): if the owner has Blessed Dew, the unit is not Cursed and is alive (HP > 0) and hurt,
  HP := min(max HP, HP + 5) through the same VMT+0xE0 / +0xD0 / +0xE4 calls the vanilla heal uses; then the replayed
  `mov edx,0x6D` and back.  So Blessed Dew stacks ON TOP of the vanilla 10 % regeneration.
  Who heals: exactly the units that get the vanilla turn-start heal - every unit/hero the player owns on the strategic
  map, including garrisons in cities and units in carried stacks; Cursed units do not (same rule as vanilla healing and
  our terrain healing).  Units fighting a tactical combat are not affected (the strategic turn does not start mid-
  combat).  No popup: the vanilla strategic heal shows none either.  No RNG (map.Random raises during this broadcast).

Zone 0x5582A000..0x5582C000 (zero, reloc-free; PIC via call/pop delta for every in-image absolute).
Dry-run default; --apply (upgrades an older build of this patch in place) / --revert / --dis.
Backup <game>\\backup\\AoWEPACK.dll.bak_blesseddew.
Pipeline entry (patch_dual_sphere_spells_v1.py): donor "TDeathMastery": (0x557EEF90, 0x557F27A8) (site 0x557F3A89),
pfs_donor 72, tc_type None, sphere 12, tier 3, mana 50, research 150, upkeep 7, pokes [(0x34, 4, 0xFFFFFFFF)].

v3 2026-10-15 - PLAGUE (spell 341, Water/Death, tier 2) shares this Death Mastery plumbing (cf. Overgrowth/World Healer):
  Markers: [ench+0x14] bits 0..8 = spell id (326 / 341); Blessed Dew keeps the plain dword 326.  PLAGUE STATE lives in
  the high bits of its marker (the ONLY serialised dword we can use - TGlobalEnchantment.ReadWrite 0x5577DA1C saves
  [+8] id, [+0x18], [+0x19], [+0x1C] name, [+0x20] upkeep, [+0x14]; no vanilla/exe code reads [+0x14]):
      bits 9..16 origin hex x, 17..24 origin hex y, 25 origin level, 26..31 K = number of infected cities (1..KMAX).
  Origin = the caster's LEADER location at cast time (TPlayer.GetLeaderLocation 0x557536E4; no leader -> hex 0,0).
  Activate (AC, marker 341): base Activate, then origin + K := 1 written into the marker, then every city re-runs
  UpdateIncome (rca) so the penalty shows at once.  Deactivate (DE): base Deactivate (removes it from the list), then
  rca again (penalties gone).  Spread: TDeathMasteryEnchantment.MsgProc VMT+0x44 (slot 0x557EEEE8, vanilla
  0x557F2760) -> cave mp: for 341, inherited MsgProc 0x557030F4, then on the new-turn broadcast 0x20020002 whose
  player [msg+0x18] is the caster: K := min(K + 1, KMAX), rca.  (Every peer runs the broadcast -> deterministic.)
  INFECTED SET (inf, esi = city -> al): for every active Plague P (marker id 341, active bit, K > 0): the target must
  be ELIGIBLE for P's caster (owner != caster and not allied: owner <= 0 (independent) always eligible, else
  TPlayerList relation 0x55754150 (eax list, dl caster, cl owner) != drAlliance 2); then a deterministic greedy chain
  over all cities (players [[map]+0x140], each player's income sources [[p+0x64]+8] (a container holding the TList at +8 - v3.1 10/15 fix: v3 read [p+0x64] as the TList itself -> garbage count -> AV at cast) -> structure [src+8] whose VMT is
  TCity 0x557A73F0; hex x [+0x10], y [+0x11], level VMT+0x7C): city 1 = the eligible city nearest the origin, then
  repeatedly the eligible uninfected city nearest ANY infected city (squared hex-offset distance, +100000 across
  levels), K picks.  Recomputed on every query from synced state -> MP-safe; ownership changes re-route the chain
  (a city the caster or an ally takes is never plagued).  Cost O(K*n) per Plague per query (n <= 128 cities).
  EFFECTS on an infected city:
    IC  TCity.UpdateIncome 0x557ABB94, the Gold Rush test @0x557ABC0B (6 B `test byte [esi+0x5C],2 / je`) ->
        jmp cave ic: Gold Rush x2 replayed, then if infected [city+0x3C] -= [city+0x3C] / 4 (-25 %) via SetIncome
        0x557A617C; back to the epilogue 0x557ABC28.  Golden Age's VMT wrapper runs AFTER (its +25 % on top).
    CS  TCity.GetCivilStatus 0x557AC14C epilogue @0x557AC48A (5 B `add esp,0x1C / pop ebp / pop edi`) -> jmp cave
        cs: if infected, Cheerful 4 -> Content 3 -> Stable 2 -> Unrest 1 -> Unruly 0 (one step worse; Oppressed 5 /
        Slavery 6 unchanged) = the 'morale penalty': Unrest rebels 10 %, Unruly 50 % per turn (CheckRebellion
        0x557AB534; owner 0 never rebels) and the city panel shows the worse status.
  CHK: per-spell 'already active' (a player may run one Blessed Dew AND one Plague).  MM: no mastery message for 341.
v4 2026-10-15 (user): income -50 % (IC: [city+0x3C] -= [city+0x3C] / 2); ELIGIBLE = any city (own, allied, enemy,
  independent) whose race is not Undead (TCity.GetRace 0x557AC9BC = byte [city+0x45]; Undead = race index 0x0B, the same
  index the combat undead test uses) - the first city is still the one nearest the caster's leader, the spread the
  nearest uninfected eligible city.  New fixed export INF_EXPORT 0x5582BFF0 = `jmp inf` (esi = city -> al) used by
  patch_city_enchant_ui_v1.py v4 (the 'Plague' line in the city panel + the plague hex glow) - apply THIS script first.
  Zone grows inside 0x5582A000..0x5582C000.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DLL = game_file("AoWEPACK.dll")
BASE, CODE_V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x5582A000, 0x5582C000
SPELL_ID, HEAL = 326, 5
PLAGUE_ID, KMAX, MAXC = 341, 40, 128                                    # v3: Plague spell id, max infected cities, max cities scanned
PLAYER_GET, DIPLO_REL, LEADER_LOC = 0x557544D0, 0x55754150, 0x557536E4
TCITY_VMT, CROP_SETINC = 0x557A73F0, 0x557A617C
DM_MSG, INH_MSG = 0x557F2760, 0x557030F4
UPDINC_TAIL, CIV_TAIL = 0x557ABC28, 0x557AC48F

MAP_GLOBAL, LIST_GET = 0x558FA040, 0x5577E13C
BASE_ACT, BASE_DEACT, BASE_CHK = 0x5577DBA0, 0x5577DC3C, 0x5577DAE8
DM_ACT, DM_DEACT, DM_CHK, DM_CHK_MSG, DM_CHK_SEH = 0x557F2480, 0x557F24E8, 0x557F23A8, 0x557F2402, 0x557F2470
DM_ENCH_CREATE, DM_ENCH_CELL = 0x557F2300, 0x557EEE64
MASTERY_MSG, LSTRASG = 0x557EF7C0, 0x55701150
CURSED = 0x5D
UNDEAD_RACE = 0x0B                                                    # v4: race index of the Undead (TCity [city+0x45] / unit GetRace)
INF_EXPORT = 0x5582BFF0                                              # v4: fixed `jmp inf` for patch_city_enchant_ui_v1.py (esi = city -> al = plagued)

CODE_SITES = {
    "CE": (0x557F285C, bytes.fromhex("33c9b201a1"), "jmp"),
    "MM": (0x557F2968, bytes.fromhex("e853ceffff"), "call"),
    "HL": (0x55780DFE, bytes.fromhex("ba6d000000"), "call"),
    "IC": (0x557ABC0B, bytes.fromhex("f6465c027417"), "jmp"),        # v3 Plague: TCity.UpdateIncome Gold Rush test -> -25 %
    "CS": (0x557AC48A, bytes.fromhex("83c41c5d5f"), "jmp"),          # v3 Plague: TCity.GetCivilStatus epilogue -> one step worse
}
VMT_SLOTS = {
    "dmAct":   (0x557EEF0C, DM_ACT, "ac"),
    "dmDeact": (0x557EEF04, DM_DEACT, "de"),
    "dmChk":   (0x557EEF08, DM_CHK, "chk"),
    "dmMsg":   (0x557EEEE8, DM_MSG, "mp"),                          # v3 Plague: MsgProc VMT+0x44 (spread on the caster's new turn)
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
    C = {"id": SPELL_ID, "pid": PLAGUE_ID, "kmax": KMAX, "maxc": MAXC, "heal": HEAL, "cursed": CURSED, "map": MAP_GLOBAL,
         "get": LIST_GET, "bact": BASE_ACT, "bdeact": BASE_DEACT, "bchk": BASE_CHK, "dmact": DM_ACT, "dmdeact": DM_DEACT,
         "dmchk": DM_CHK, "dmmsg": DM_CHK_MSG, "dmseh": DM_CHK_SEH, "dmcreate": DM_ENCH_CREATE, "dmcell": DM_ENCH_CELL,
         "mmsg": MASTERY_MSG, "lstrasg": LSTRASG, "pget": PLAYER_GET, "diplo": DIPLO_REL, "leaderloc": LEADER_LOC,
         "tcity": TCITY_VMT, "setinc": CROP_SETINC, "dmmp": DM_MSG, "inhmsg": INH_MSG, "updtail": UPDINC_TAIL,
         "civtail": CIV_TAIL, "kone": 1 << 26, "pidk1": PLAGUE_ID | (1 << 26), "undead": UNDEAD_RACE}
    clash = set(C) & {"dlt", "has", "bda", "ce", "mm", "ac", "de", "chk", "hl", "col", "dst", "elg", "inf", "rca", "mp", "ic", "cs"}
    assert not clash, clash
    # dlt: eax = load delta (PIC anchor)
    place("dlt", """
        call $D
        pop eax
        sub eax, $D
        ret
    """, pic=True)
    # has: dl = player index, ecx = spell id -> al = 1 if that player owns a listed enchantment whose marker id
    # (bits 0..8) is ecx; all other regs preserved
    place("has", """
        push ebx
        push ecx
        push edx
        push esi
        push edi
        push ebp
        mov ebp, ecx
        movsx edi, dl
        call %(dlt)#x
        mov eax, [eax+%(map)#x]
        test eax, eax
        jz has_no
        mov eax, [eax+0x188]
        test eax, eax
        jz has_no
        mov esi, [eax+0x14]
        test esi, esi
        jz has_no
        mov eax, esi
        mov edx, [eax]
        call dword ptr [edx+0x54]
        mov ecx, eax
    has_lp:
        dec ecx
        js has_no
        push ecx
        mov eax, esi
        mov edx, ecx
        call %(get)#x
        pop ecx
        test eax, eax
        jz has_lp
        mov edx, [eax+0x14]
        and edx, 0x1ff
        cmp edx, ebp
        jne has_lp
        movsx edx, byte ptr [eax+0x19]
        cmp edx, edi
        jne has_lp
        mov eax, 1
        jmp has_out
    has_no:
        xor eax, eax
    has_out:
        pop ebp
        pop edi
        pop esi
        pop edx
        pop ecx
        pop ebx
        ret
    """)
    # bda: dl = player -> al = 1 if that player has a Blessed Dew (all other regs preserved)
    place("bda", """
        push ecx
        mov ecx, %(id)d
        call %(has)#x
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
        mov eax, [ebx+%(dmcell)#x]
        pop ebx
        xor ecx, ecx
        mov dl, 1
        call %(dmcreate)#x
        pop edx
        mov ecx, [edx+0x10]
        cmp ecx, %(id)d
        je ce_ours
        cmp ecx, %(pid)d
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
    # MM: ExecuteTE's sphere-mastery message (esi = spell; al/dl already loaded)
    place("mm", """
        cmp dword ptr [esi+0x10], %(id)d
        je mm_skip
        cmp dword ptr [esi+0x10], %(pid)d
        je mm_skip
        jmp %(mmsg)#x
    mm_skip:
        ret
    """)
    # col: edi = buffer of MAXC (city, coord) pairs -> eax = number of TCity objects on the map; coord = x | y<<8 |
    # level<<16.  Preserves ebx esi edi ebp.
    place("col", """
        push ebx
        push esi
        push ebp
        xor ebp, ebp
        call %(dlt)#x
        mov ebx, eax
        mov eax, [ebx+%(map)#x]
        test eax, eax
        jz col_out
        mov eax, [eax+0x140]
        test eax, eax
        jz col_out
        push eax
        mov edx, [eax]
        call dword ptr [edx+0x54]
        mov esi, eax
    col_pl:
        dec esi
        js col_pend
        mov eax, [esp]
        mov edx, esi
        call %(pget)#x
        test eax, eax
        jz col_pl
        mov eax, [eax+0x64]
        test eax, eax
        jz col_pl
        mov eax, [eax+8]
        test eax, eax
        jz col_pl
        mov ecx, [eax+8]
        mov edx, [eax+4]
    col_src:
        dec ecx
        js col_pl
        mov eax, [edx+ecx*4]
        test eax, eax
        jz col_src
        mov eax, [eax+8]
        test eax, eax
        jz col_src
        push edx
        lea edx, [ebx+%(tcity)#x]
        cmp [eax], edx
        pop edx
        jne col_src
        cmp ebp, %(maxc)d
        jae col_src
        mov [edi+ebp*8], eax
        push ecx
        push edx
        push eax
        mov edx, [eax]
        call dword ptr [edx+0x7c]
        movzx ecx, al
        shl ecx, 16
        pop eax
        movzx edx, byte ptr [eax+0x11]
        shl edx, 8
        or ecx, edx
        movzx edx, byte ptr [eax+0x10]
        or ecx, edx
        mov [edi+ebp*8+4], ecx
        pop edx
        pop ecx
        inc ebp
        jmp col_src
    col_pend:
        pop eax
    col_out:
        mov eax, ebp
        pop ebp
        pop esi
        pop ebx
        ret
    """)
    # dst: eax, edx = coords -> eax = dx*dx + dy*dy (+100000 across levels); preserves ebx ecx edx
    place("dst", """
        push ebx
        push ecx
        push edx
        movzx ebx, al
        movzx ecx, dl
        sub ebx, ecx
        imul ebx, ebx
        movzx ecx, ah
        movzx edx, dh
        sub ecx, edx
        imul ecx, ecx
        add ebx, ecx
        mov edx, [esp]
        shr eax, 16
        shr edx, 16
        cmp al, dl
        je dst_s
        add ebx, 100000
    dst_s:
        mov eax, ebx
        pop edx
        pop ecx
        pop ebx
        ret
    """)
    # elg (v4 10/15, user: Plague may hit ANY city - own, allied, enemy, independent - except UNDEAD ones): eax = city,
    # edx = caster index (unused since v4) -> al = 1 if the city's race (TCity.GetRace 0x557AC9BC = byte [city+0x45])
    # is not the Undead race index 0x0B (the same index the combat undead test uses: u.GetRace() != 0x0B).
    # Preserves every register except eax.
    place("elg", """
        cmp byte ptr [eax+0x45], %(undead)d
        je elg_no
        mov eax, 1
        ret
    elg_no:
        xor eax, eax
        ret
    """)
    # inf: esi = city -> al = 1 if any active Plague has infected it; all other regs preserved.
    # frame: [ebp-4] n (-1 = not collected), -0x10 caster, -0x14 K, -0x18 origin coord, -0x1C step, -0x24 list index,
    # -0x28 list, -0x2C target; -0x440 (city, coord) x MAXC; -0x640 min distance x MAXC; -0x740 flags x MAXC
    # (1 = eligible, 2 = infected in this chain)
    place("inf", """
        push ebp
        mov ebp, esp
        sub esp, 0x740
        push ebx
        push ecx
        push edx
        push esi
        push edi
        mov [ebp-0x2c], esi
        mov dword ptr [ebp-4], -1
        call %(dlt)#x
        mov eax, [eax+%(map)#x]
        test eax, eax
        jz inf_no
        mov eax, [eax+0x188]
        test eax, eax
        jz inf_no
        mov eax, [eax+0x14]
        test eax, eax
        jz inf_no
        mov [ebp-0x28], eax
        mov edx, [eax]
        call dword ptr [edx+0x54]
        mov [ebp-0x24], eax
    inf_gl:
        dec dword ptr [ebp-0x24]
        js inf_no
        mov eax, [ebp-0x28]
        mov edx, [ebp-0x24]
        call %(get)#x
        test eax, eax
        jz inf_gl
        mov ecx, [eax+0x14]
        mov edx, ecx
        and edx, 0x1ff
        cmp edx, %(pid)d
        jne inf_gl
        test byte ptr [eax+0x10], 1
        jz inf_gl
        mov edx, ecx
        shr edx, 26
        test edx, edx
        jz inf_gl
        mov [ebp-0x14], edx
        mov edx, ecx
        shr edx, 9
        and edx, 0xffff
        mov ebx, ecx
        shr ebx, 25
        and ebx, 1
        shl ebx, 16
        or edx, ebx
        mov [ebp-0x18], edx
        movsx edx, byte ptr [eax+0x19]
        mov [ebp-0x10], edx
        mov eax, [ebp-0x2c]
        call %(elg)#x
        test al, al
        jz inf_gl
        cmp dword ptr [ebp-4], -1
        jne inf_have
        lea edi, [ebp-0x440]
        call %(col)#x
        mov [ebp-4], eax
    inf_have:
        xor esi, esi
    inf_init:
        cmp esi, [ebp-4]
        jge inf_steps
        mov eax, [ebp+esi*8-0x440]
        mov edx, [ebp-0x10]
        call %(elg)#x
        mov byte ptr [ebp+esi-0x740], al
        mov eax, [ebp+esi*8-0x43c]
        mov edx, [ebp-0x18]
        call %(dst)#x
        mov [ebp+esi*4-0x640], eax
        inc esi
        jmp inf_init
    inf_steps:
        mov dword ptr [ebp-0x1c], 0
    inf_step:
        mov eax, [ebp-0x1c]
        cmp eax, [ebp-0x14]
        jge inf_gl
        mov edi, -1
        mov ebx, 0x7fffffff
        xor esi, esi
    inf_scan:
        cmp esi, [ebp-4]
        jge inf_pick
        cmp byte ptr [ebp+esi-0x740], 1
        jne inf_sn
        mov eax, [ebp+esi*4-0x640]
        cmp eax, ebx
        jge inf_sn
        mov ebx, eax
        mov edi, esi
    inf_sn:
        inc esi
        jmp inf_scan
    inf_pick:
        test edi, edi
        js inf_gl
        mov byte ptr [ebp+edi-0x740], 2
        mov eax, [ebp+edi*8-0x440]
        cmp eax, [ebp-0x2c]
        je inf_yes
        mov ecx, [ebp+edi*8-0x43c]
        xor esi, esi
    inf_upd:
        cmp esi, [ebp-4]
        jge inf_next
        cmp byte ptr [ebp+esi-0x740], 1
        jne inf_un
        mov eax, [ebp+esi*8-0x43c]
        mov edx, ecx
        call %(dst)#x
        cmp eax, [ebp+esi*4-0x640]
        jge inf_un
        mov [ebp+esi*4-0x640], eax
    inf_un:
        inc esi
        jmp inf_upd
    inf_next:
        inc dword ptr [ebp-0x1c]
        jmp inf_step
    inf_yes:
        mov eax, 1
        jmp inf_out
    inf_no:
        xor eax, eax
    inf_out:
        pop edi
        pop esi
        pop edx
        pop ecx
        pop ebx
        mov esp, ebp
        pop ebp
        ret
    """)
    # rca: every city re-runs its UpdateIncome (VMT+0x230) - after a Plague is cast / spreads / ends
    place("rca", """
        push ebp
        mov ebp, esp
        sub esp, 0x400
        push ebx
        push esi
        push edi
        lea edi, [ebp-0x400]
        call %(col)#x
        mov esi, eax
    rca_lp:
        dec esi
        js rca_out
        mov eax, [edi+esi*8]
        mov edx, [eax]
        call dword ptr [edx+0x230]
        jmp rca_lp
    rca_out:
        pop edi
        pop esi
        pop ebx
        mov esp, ebp
        pop ebp
        ret
    """)
    place("ac", """
        mov ecx, [eax+0x14]
        and ecx, 0x1ff
        cmp ecx, %(id)d
        je ac_ours
        cmp ecx, %(pid)d
        je ac_pl
        jmp %(dmact)#x
    ac_ours:
        jmp %(bact)#x
    ac_pl:
        push ebx
        push esi
        push edi
        mov ebx, eax
        movsx esi, dl
        call %(bact)#x
        call %(dlt)#x
        mov eax, [eax+%(map)#x]
        mov eax, [eax+0x140]
        mov edx, esi
        call %(pget)#x
        sub esp, 8
        mov dword ptr [esp], 0xffffffff
        mov dword ptr [esp+4], 0xffffffff
        test eax, eax
        jz ac_noleader
        lea edx, [esp]
        lea ecx, [esp+1]
        lea edi, [esp+2]
        push edi
        call %(leaderloc)#x
    ac_noleader:
        movzx edx, byte ptr [esp]
        movzx ecx, byte ptr [esp+1]
        movzx edi, byte ptr [esp+2]
        add esp, 8
        cmp edx, 0xff
        jne ac_have
        xor edx, edx
        xor ecx, ecx
        xor edi, edi
    ac_have:
        and edi, 1
        shl edi, 25
        shl ecx, 17
        shl edx, 9
        or edx, ecx
        or edx, edi
        or edx, %(pidk1)#x
        mov [ebx+0x14], edx
        call %(rca)#x
        mov eax, 1
        pop edi
        pop esi
        pop ebx
        ret
    """)
    place("de", """
        mov ecx, [eax+0x14]
        and ecx, 0x1ff
        cmp ecx, %(id)d
        je de_ours
        cmp ecx, %(pid)d
        je de_pl
        jmp %(dmdeact)#x
    de_ours:
        jmp %(bdeact)#x
    de_pl:
        call %(bdeact)#x
        push eax
        call %(rca)#x
        pop eax
        ret
    """)
    # CHK: eax = ench, dl = player, ecx = &message; returns al (1 = may cast)
    place("chk", """
        push ecx
        mov ecx, [eax+0x14]
        and ecx, 0x1ff
        cmp ecx, %(id)d
        je chk_o
        cmp ecx, %(pid)d
        je chk_o
        pop ecx
        jmp %(dmchk)#x
    chk_o:
        pop ecx
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
        and ecx, 0x1ff
        call %(has)#x
        test al, al
        pop ecx
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
        add eax, %(dmseh)#x
        push ebp
        push eax
        xor eax, eax
        push dword ptr fs:[eax]
        mov dword ptr fs:[eax], esp
        jmp %(dmmsg)#x
    """, pic=True)
    # HL: TAbstractUnit.NewTurn after the vanilla heal (esi = unit, owner's turn); replays `mov edx,0x6D`
    place("hl", """
        push eax
        push ebx
        push ecx
        mov dl, byte ptr [esi+0x24]
        call %(bda)#x
        test al, al
        jz hl_out
        mov edx, %(cursed)d
        mov eax, esi
        mov ecx, [eax]
        call dword ptr [ecx+0x148]
        test al, al
        jnz hl_out
        mov eax, esi
        mov edx, [eax]
        call dword ptr [edx+0xd0]
        movzx ebx, al
        mov eax, esi
        mov edx, [eax]
        call dword ptr [edx+0xe0]
        movzx edx, al
        test edx, edx
        jz hl_out
        cmp edx, ebx
        jae hl_out
        add edx, %(heal)d
        cmp edx, ebx
        jbe hl_set
        mov edx, ebx
    hl_set:
        mov eax, esi
        mov ecx, [eax]
        call dword ptr [ecx+0xe4]
    hl_out:
        pop ecx
        pop ebx
        pop eax
        mov edx, 0x6d
        ret
    """)
    # mp: TDeathMasteryEnchantment.MsgProc (eax = ench, edx = msg); Plague spreads on its caster's new turn
    place("mp", """
        mov ecx, [eax+0x14]
        and ecx, 0x1ff
        cmp ecx, %(pid)d
        je mp_ours
        jmp %(dmmp)#x
    mp_ours:
        push ebx
        push esi
        mov ebx, eax
        mov esi, edx
        call %(inhmsg)#x
        cmp dword ptr [esi], 0x20020002
        jne mp_out
        test byte ptr [ebx+0x10], 1
        jz mp_out
        movsx eax, byte ptr [ebx+0x19]
        cmp eax, [esi+0x18]
        jne mp_out
        mov eax, [ebx+0x14]
        mov edx, eax
        shr edx, 26
        cmp edx, %(kmax)d
        jae mp_rc
        add eax, %(kone)#x
        mov [ebx+0x14], eax
    mp_rc:
        call %(rca)#x
    mp_out:
        pop esi
        pop ebx
        ret
    """)
    # IC: TCity.UpdateIncome @0x557ABC0B (esi = city): Gold Rush x2 replayed, then the Plague -50 % (v4; v3 -25 %); -> epilogue
    place("ic", """
        test byte ptr [esi+0x5c], 2
        jz ic_pl
        mov dl, byte ptr [esi+0x3c]
        add edx, edx
        mov eax, esi
        call %(setinc)#x
    ic_pl:
        call %(inf)#x
        test al, al
        jz ic_out
        movzx edx, byte ptr [esi+0x3c]
        mov eax, edx
        shr eax, 1
        sub edx, eax
        mov eax, esi
        call %(setinc)#x
    ic_out:
        jmp %(updtail)#x
    """)
    # CS: TCity.GetCivilStatus epilogue @0x557AC48A (al = status, esi = city): one step worse if plagued
    place("cs", """
        push eax
        call %(inf)#x
        test al, al
        pop eax
        jz cs_out
        cmp al, 1
        jb cs_out
        cmp al, 4
        ja cs_out
        dec al
    cs_out:
        add esp, 0x1c
        pop ebp
        pop edi
        jmp %(civtail)#x
    """)
    # v4: a FIXED entry point other scripts can call (patch_city_enchant_ui_v1.py: the Plague line in the city panel and
    # the plague glow): INF_EXPORT = `jmp inf` (esi = city -> al = 1 if plagued; every other register preserved).
    assert ZONE + len(out) <= INF_EXPORT, hex(ZONE + len(out))
    out.extend(bytes(INF_EXPORT - ZONE - len(out)))
    where["infx"] = INF_EXPORT
    out.extend(bytes([0xE9]) + struct.pack("<i", where["inf"] - (INF_EXPORT + 5)))
    return bytes(out), where


CAVE_OF = {"CE": "ce", "MM": "mm", "HL": "hl", "IC": "ic", "CS": "cs"}


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
    bak = bak_path(DLL, ".bak_blesseddew")
    if not os.path.exists(bak): shutil.copy2(DLL, bak); print("backup ->", bak)
    with open(DLL, "r+b") as f: f.write(bytes(d))
    assert open(DLL, "rb").read() == bytes(d); print("Written and verified"); return 0


if __name__ == "__main__":
    sys.exit(main())
