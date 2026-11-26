#!/usr/bin/env python3
r"""
WALL OF FLAMES (spell 226, Fire tier 3, 2026-10-17) - the burning ring on the combat map.  AoWTCPCK.dll only.

Spec (user): combat spell, long range, small AOE (7 hexes), R70 C5.  Flames on the OUTER ring (6 hexes, not the
centre) linger for 3 turns; enemies moving through the flames or beginning their turn on them suffer fire damage
"same as Fire Barrier".

Spell object = GREAT HAIL clone like Sanctify 208 / Steadfast 218 (patch_dual_sphere_spells_v1.py: donor TGreatHail,
pfs 126, tc_type 0x0A, pokes ATK 0 / DMG 0 / no type / range 12 / side mask 3 - the 7 strikes themselves do no harm),
ALIAS 226 -> 0x74 + SITE_KEEP 0x40F0E3 + SITE_ALIAS 0x42827A -> 0x82 (patch_tc_spell_alias_v1.py), 7 strikes =
the 7 hexes once (patch_rotaway_v1.py STRIKES[226] = 7, landing at the hex centre).

RE (live DLLs, 2026-10-17):
  * Vanilla combat fire = TCombatFire (VMT 0x406B24, ClassID 0x22054A, instance 0x1C) = BURNING VEGETATION:
    CreateFire 0x406D64 only lights decoration types 9/1/2/3 or wooden walls; at its owner's next turn
    (VMT+0x44 0x4071B4 -> NewTurn 0x4070CC) it sends field msg 0x31007 (only wooden walls react: TCityWall
    MapFieldMsgProc case 0x31007), spreads 50 % to each neighbour (CreateFire) and frees itself.  It never damages
    units (no unit-HS case 0x31007; TUnitHS.MapFieldMsgProc 0x557849BC only handles msg 0x10).  Its Show (VMT+0xA8
    0x4071F8) draws combat image sequence 0x3C at the hex with the random jitter [+0xC]/[+0x10] set on placement
    (VMT+0xE0 0x407054: 2 x RandInt(10)+11, [+0x14] = [map+0xED] turn side, [+0x18] = 1).  VMT+0xD0 0x407304 = the
    AI path danger (+20, +10 Fire Resistance 0x47, 0 Fire Immunity 7) - kept, so the AI avoids our flames.
  * "Fire Barrier" (TFireBarrier, a strategic spell) burns armies through TArmy.TriggerFireDamage 0x55790110 =
    ExecuteDamageRole(unit, 4, 4, fire) per unit -> our combat burn = ATK 4 / DMG 4, damage type Fire (0x01).
  * Unit hit path: the unit HS MapFieldMsgProc (VMT+0xCC 0x420E5C) case 0x31013 (0x421177, the breath hit):
    Random seed -> GetSpell([msg+0xC]) -> spell VMT+0x78 CreateCA(edx = [msg+8], ecx = [hs+0x1C] target CU, push 0)
    -> hurt animation (dmg > 0) -> AddAction([0x46C064]+0xE4) -> CA.Execute (death included).  With the push-0 flag
    CreateCA never reads the caster (edx); the dual-sphere hooks in it key on other spell ids -> edx = the target CU.
  * Turn side: the turn broadcast 0x20021001 is sent by map VMT+0x68 at 0x41BEFD ([ebp-4] = map), new turn side =
    [map+0xED] (movsx) - the same encoding as the combat unit side byte [cu+0x45] (move TE end compares them,
    0x408ED2).  [map+0x3C] & 2 = vanilla fire's skip flag (also honoured here), & 8 = AI simulation (skip).
  * Move step: TCombatMoveTE step 0x408278 (HS -> next field, MovedTo, ...) returns 1 when the unit moved on; the TE
    frame then calls the post-step 0x4085F0 (arg = TE frame ebp, TE = [arg-4], CU = [TE+0x1C]) which FIRST checks
    CU VMT+0x60 (alive) - vanilla's attacks of opportunity run in it.  Hitting the unit at its entry is therefore
    death-safe exactly like an AoO (a death inside MovedTo would leave the step using a freed HS).

Behaviour:
  * land 0x40C609 (CHAINED in front of the current head - Steadfast clang 0x44A010 today): every landed 226 strike
    (fx kind 0x34) whose hex is NOT the target hex ([te+0x20]/[te+0x22]) and holds no intact wall / gate section
    (0x220504 / 0x220506 with HP [+0x20] > 0) gets a FLAME HS (one per hex; a re-cast refreshes owner + lifetime).
    Flames are placed under units too (the unit standing there is not hurt by the cast itself; it burns when its
    turn begins, if it is an enemy).
  * FLAME HS = a runtime CLONE of the TCombatFire VMT (all slots VMT-0x40..+0x110) in AoWEPACK's BSS page slack
    0x558FAB00..0x558FAC50 (VMT ptr 0x558FAB40; free span per the BSS map: LOS flags end 0x558FAA41, Sanctify's
    clone starts 0x558FAD00), reached through the TCombatUnit.SetUnit import-slot delta (Sanctify recipe).
    Instance size 0x20: +0x14 owner side, +0x19 turns left (3), +0x1C last CU burned by moving in (compared by
    value only, never dereferenced; cleared every turn).  Slots changed: +0x24 ClassID -> 0x220114 (unused by
    any binary or script), +0x44 MsgProc -> inherited TEObject.MsgProc, then on the turn broadcast: clear +0x1C;
    at the start of the OWNER's turn count +0x19 down, free at 0 (TCombatFire.NewTurn's own idiom).  Show / level /
    priority / AI danger stay TCombatFire's = the vanilla burning-hex flames.
    Cast in owner turn T0 -> burns at the starts of enemy turns E1, E2, E3 -> gone when T3 begins.
  * bc 0x41BEF2 (14 B: the broadcast call + its 4 argument loads, replayed): AFTER the turn broadcast (no sprite
    list is being iterated any more) scan the battlefield x 6..0x3A / y 6..0x34 (Tremors' range): every flame whose
    owner != the new turn side S burns the unit standing on it if that unit's side == S and it is alive.
  * step 0x4085F0 (6 B prologue, replayed): after each completed move step, a living unit entering a flame of the
    other side is burned once (dedupe [flame+0x1C] = that CU, reset each turn).  Pushes (Gust / Flash Flood call the
    step 0x408278 directly) do not run 0x4085F0 -> no burn.
  * burn(hs): GetSpell(226), temporarily ATK 4 / DMG 4 / types 0x0001 / shots 1 in the spell's +0x34..+0x38, unit HS
    VMT+0xCC(msg 0x31013, +8 = target CU, +0xC = 226), restore.  Everything runs inside TE execution / the turn
    processing with the synced map Random -> identical on every peer.  Fast combat: the 7 strikes do 0 damage and no
    flames exist (the spell is effectively a no-op there, like Sanctify).

Zone 0x44C800..0x44D000 (zero, reloc-free, CODE).  PIC call/pop delta for every in-image absolute (TCPCK rebases).
Thunks import-table checked.  Dry-run default; --apply / --revert / --dis / --dll <copy> [--ep <AoWEPACK copy>].
Backup <game>\backup\AoWTCPCK.dll.bak_walloflames.  LIFO: anything later chained in front of land (0x40C609) must be
reverted first; revert refuses while step / bc / land no longer point at us.

v2.1 2026-10-17 (crash: 'AoO killed him and the game locked into a unit move token'): the move-in burn can KILL the
  mover in the post-step (0x4085F0) - OUTSIDE the move TE's strike states.  Vanilla only ever kills a mover inside an
  AoO strike, whose End state (0x408C4C) sees the death and returns 3 (TE done); the plain step path 0x408D05 just
  returns 1 ('continue') while the mover is dead -> the TCombatMoveTE never finishes = the move token locks forever
  (e.g. AoO leaves the unit at 1 HP, the next step enters a flame, the 1-damage burn kills it).  Fix: after the burn,
  if the mover is no longer alive (CU VMT+0x60) set the Execute frame's status byte [arg-9] = 3, exactly what the
  End state does for an AoO death -> the TE finishes on this pass (every caller of 0x4085F0 jumps to 0x408EB3,
  which reads [ebp-9]).
v2 2026-10-17 (user: "the lingering flames currently don't do anything ... wall of flames should do 10 ATK / 2 DMG fire
damage when cast, then the lingering flames should do 10 ATK / 1 DMG fire damage to any unit walking through or
beginning turn on it.  outside hexes of AOE only, center hex remains empty ... nothing should appear on the center hex
... use the overworld 1-hex fire object GFX for the lingering flames"):
  * WHY v1 DID NOTHING (most likely; not observed live): the burn's only damage path is the unit HS breath-hit case
    (msg 0x31013 @0x421177), which first calls TAoWHSMap.Random([[0x46E8D4]], 0xFFFFFF) (@0x42118C).  Random RAISES
    unless TAoWHSMap.GetSynchronised (0x55775608: [map+0x234] != 0 / [[map+0x23C]+4]+0x48 / [map+0x3C] & 2) holds
    (same trap as Rot Away v2) -> outside a running TE the burn threw before any damage existed.  v1 also only ever
    burned ENEMIES, did nothing at the cast (strikes ATK 0) and burned with ATK 4 (mostly misses vs real defences).
    v2: every burn is bracketed by SynchroniseBegin/End inline (inc / dec [[0x46E8D4]+0x234] - the exported
    TAoWHSMap.SynchroniseBegin 0x557755F8 body) -> the synced map seed is used, never the throwing path; all peers run
    the same code at the same point (turn start / move TE) -> MP-identical.
    Diagnostic counters (AoWEPACK .idata page slack, zero at load, via the SetUnit import delta) DIAG_EP+0 flames
    placed, +4 turn-start scans, +8 turn-start burns, +0xC move-in burns, +0x10 burns completed (the handler
    returned) - read live with wof_probe.py.
  * CAST: the strikes themselves now hurt: pipeline pokes ATK 10 / DMG 2 / Fire on 226 -> the vanilla hail landing
    (direct CreateCA on a unit hex, map msg 0x31006 on an empty hex) - all units on the ring (side mask 3 kept).
  * CENTRE EMPTY: 6 strikes (patch_rotaway_v1.py STRIKES[226] = 6) and new hook `hn` (CHAINED in front of rotaway's
    hn0 call at 0x40E29B; ecx = HN after it): for 226 ecx := 1 + ([te+0x34] mod 6) -> the 6 strikes land on HN 1..6
    = the ring exactly once; HN 0 (the target hex) gets no strike -> no burst, no landing sound, no damage, no flame.
  * LINGER: ATK 10 / DMG 1 fire (spell +0x34..+0x38 poked around the hit, restored).  ANY unit (both sides, the
    caster's own too): beginning its turn on a flame (turn-start scan after the broadcast: units whose side == the
    new turn side) or moving into a flame (post-step 0x4085F0, once per flame per turn).
  * LOOK: the clone's Show slot (VMT+0xA8) -> `show`: the vanilla TCombatFire placement math (HXtoHP of the hex - the
    view origin, + 16/16 = the hex centre) but drawn with ImageLib.TImageSequenceList.ShowLooped(GetSpell(226)+0x2C,
    SLOT_FLAME = 3, x, y, [[0x46E8D4]+0x40] + ((self >> 2) & 0xFFFF), target) = the STRATEGIC 1-hex fire object
    EFFECTS\FIRESM.ILB (Release.hss's burning-hex sequence, 12 frames 112x78; flame base at canvas (56, 71)) looped,
    each flame out of phase like vanilla's.  Pipeline slot 3 = seq_entry("EFFECTS\FIRESM.ILB", 0..11, -56, -67, f18=2).
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DEFAULT_DLL = game_file("AoWTCPCK.dll"); DEFAULT_EP = game_file("AoWEPACK.dll")
BASE, V2F = 0x400000, 0x400C00
ZONE, ZONE_END = 0x44C800, 0x44D000
HDR = 0x10                        # zone header: +0 previous land-site call target, +4 magic
MAGIC, OLD_MAGICS = b"WoF3", (b"WoF1", b"WoF2")   # header +0 prev land, +4 magic, +8 prev hn target (v2)
SPELL_ID, FIELD_CLASSID, UNITHS_CLASSID, WALL_CLS, GATE_CLS, FX_STRIKE = 226, 0x220114, 0x220104, 0x220504, 0x220506, 0x34
TURNS, INST = 3, 0x20
BURN_ATK, BURN_DMG, BURN_TYPES = 10, 1, 0x0001       # v2: lingering burn 10 ATK / 1 DMG fire (the cast = the strikes, pipeline pokes 10 / 2)
TURN_MSG, HIT_MSG = 0x20021001, 0x31013
SKIP_BITS = 0x0A                  # [map+0x3C] & 2 (vanilla fire skip) | 8 (AI simulation)
X0, X1, Y0, Y1 = 6, 0x3B, 6, 0x35  # Tremors' battlefield range (x 6..58, y 6..52)
SETUNIT_SLOT, SETUNIT_VA = 0x46E858, 0x55725194
CLONE_EP, VMT_LO, VMT_HI = 0x558FAB40, 0x40, 0x110   # AoWEPACK BSS slack 0x558FAB00..0x558FAC50 (VMT ptr = +0x40)
MAPLIST, HSSET = 0x469420, 0x46E8D0
FIRE_CELL, FIRE_CREATE = 0x406AE4, 0x406F68
T_MSGPROC, T_FREE, T_GETSPELL, T_PLACEHX, T_GETLEVEL, T_GETFIELD = 0x401404, 0x401050, 0x4029B4, 0x402264, 0x401E64, 0x401E54
T_HXTOHP, T_SHOWLOOP = 0x4022BC, 0x4016EC
STRATMAP = 0x46E8D4                 # [[.]] = the AoWE TAoWHSMap (Random / Synchronise owner, frame counter +0x40)
SLOT_FLAME, SYNC_OFS = 3, 0x234
FRAME_100NS = 1430000             # v3 10/17: lingering flame = 1 FIRESM frame per 143 ms (~7 fps, 12-frame loop 1.7 s), real-time clock (KUSER InterruptTime) - ShowLooped's kind-4 GetFrameIndex ADVANCES a counter shared by the sequence on every CALL (and ignores the time arg), so 6 flames = 6x speed, 2 casts = 12x; v3 pins [seq+0x34]=frame, [seq+0x30]=1 before each call
DIAG_EP = 0x5590B400                # AoWEPACK .idata page slack (raw data ends 0x5590B200; Smokescreen clone 0x5590B200..B350)
HN_SITE, HN_LEN = 0x40E29B, 7       # rotaway hn0 call-hook (e8 rel32 90 90); chained in front (v2)
RING = 6
THUNKS = {T_MSGPROC: "TEObject.MsgProc", T_HXTOHP: "HSEngine.HXtoHP", T_SHOWLOOP: "TImageSequenceList.ShowLooped", T_FREE: "TObject.Free", T_GETSPELL: "TSpellControl.GetSpell",
          T_PLACEHX: "THSMap.PlaceHX", T_GETLEVEL: "TMapContainer.GetMapLevel", T_GETFIELD: "TMapLevel.GetField"}
LAND = 0x40C609
LAND_VANILLA = bytes.fromhex("8b45e083783000")
STEP, STEP_VANILLA, STEP_RESUME = 0x4085F0, bytes.fromhex("558bec83c4ec"), 0x4085F6
BC, BC_VANILLA = 0x41BEF2, bytes.fromhex("8d55bc8b4dfc8b45fc8b18ff5368")
FIRE_VMT = 0x406B24

ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm_delta(src, va):
    """PIC delta idiom `call $D / pop R / sub R, $D` (R = ebx, esi, edi): every anchor patched with its own VA."""
    s1 = src.replace("call $D", ".byte 0xe8, 0, 0, 0, 0")
    for r in ("ebx", "esi", "edi"): s1 = s1.replace("sub %s, $D" % r, "sub %s, 0x7fffffff" % r)
    b = bytearray(ks.asm(s1, va)[0]); n = 0
    for pop, sub in ((0x5B, 0xEB), (0x5E, 0xEE), (0x5F, 0xEF)):
        anchor = bytes([0xE8, 0, 0, 0, 0, pop, 0x81, sub]) + b"\xff\xff\xff\x7f"
        k = b.find(anchor)
        while k >= 0:
            struct.pack_into("<I", b, k + len(anchor) - 4, va + k + 5); n += 1; k = b.find(anchor, k + len(anchor))
    assert n == src.count("call $D"), "delta anchors: %d of %d" % (n, src.count("call $D"))
    return bytes(b)


def build(prev_land, prev_hn):
    out = bytearray(HDR); where = {}
    struct.pack_into("<I", out, 0, prev_land); out[4:8] = MAGIC; struct.pack_into("<I", out, 8, prev_hn)
    def place(name, src):
        while len(out) % 16: out.append(0)
        va = ZONE + len(out); where[name] = va; out.extend(asm_delta(src, va))
    P = {"slot": SETUNIT_SLOT, "suva": SETUNIT_VA, "clone": CLONE_EP, "maplist": MAPLIST, "hsset": HSSET,
         "fire": FIRE_CELL, "create": FIRE_CREATE, "msgproc": T_MSGPROC, "free": T_FREE, "getspell": T_GETSPELL,
         "placehx": T_PLACEHX, "getlevel": T_GETLEVEL, "getfield": T_GETFIELD, "id": SPELL_ID, "fcls": FIELD_CLASSID,
         "ucls": UNITHS_CLASSID, "wcls": WALL_CLS, "gcls": GATE_CLS, "kind": FX_STRIKE, "turns": TURNS, "inst": INST,
         "turn": TURN_MSG, "hit": HIT_MSG, "skip": SKIP_BITS, "lo": VMT_LO, "ndw": (VMT_LO + VMT_HI) // 4,
         "atk": BURN_ATK, "dmg": BURN_DMG, "types": BURN_TYPES, "x0": X0, "x1": X1, "y0": Y0, "y1": Y1,
         "prev": prev_land, "prevhn": prev_hn, "sresume": STEP_RESUME, "strat": STRATMAP, "sync": SYNC_OFS,
         "hxtohp": T_HXTOHP, "showlp": T_SHOWLOOP, "fslot": SLOT_FLAME, "diag": DIAG_EP, "ring": RING, "fms": FRAME_100NS}
    place("classid", "mov eax, %(fcls)#x\n ret" % P)
    # cnt(ecx = counter offset): ++dword [AoWEPACK DIAG_EP + ecx] (via the SetUnit import-slot delta); keeps all regs
    place("cnt", """
        pushal
        call $D
        pop ebx
        sub ebx, $D
        mov edx, [ebx + %(slot)#x]
        sub edx, %(suva)#x
        add edx, %(diag)#x
        inc dword ptr [edx + ecx]
        popal
        ret
    """ % P)
    # burn(eax = unit HS): one ATK 10 / DMG 1 fire hit through the unit HS's own breath-hit case (msg 0x31013),
    # bracketed by SynchroniseBegin/End on the AoWE map (the case calls TAoWHSMap.Random, which raises otherwise)
    place("burn", """
        pushal
        mov esi, eax
        test esi, esi
        jz b_out
        mov edi, [esi + 0x1c]
        test edi, edi
        jz b_out
        call $D
        pop ebx
        sub ebx, $D
        mov eax, [ebx + %(hsset)#x]
        mov eax, [eax]
        mov eax, [eax + 0x84]
        mov edx, %(id)d
        call %(getspell)#x
        test eax, eax
        jz b_out
        mov ebp, eax
        push dword ptr [ebp + 0x38]
        push dword ptr [ebp + 0x34]
        mov byte ptr [ebp + 0x34], %(atk)d
        mov byte ptr [ebp + 0x35], %(dmg)d
        mov word ptr [ebp + 0x36], %(types)d
        mov byte ptr [ebp + 0x38], 1
        mov eax, [ebx + %(strat)#x]
        mov eax, [eax]
        push eax
        inc dword ptr [eax + %(sync)#x]
        sub esp, 0x30
        xor eax, eax
        mov ecx, 12
    b_zero:
        mov [esp + ecx * 4 - 4], eax
        dec ecx
        jnz b_zero
        mov dword ptr [esp], %(hit)#x
        mov [esp + 8], edi
        mov dword ptr [esp + 0xc], %(id)d
        mov eax, esi
        mov edx, esp
        mov ecx, [eax]
        call dword ptr [ecx + 0xcc]
        add esp, 0x30
        pop eax
        dec dword ptr [eax + %(sync)#x]
        pop dword ptr [ebp + 0x34]
        pop dword ptr [ebp + 0x38]
        mov ecx, 0x10
        call %(cnt)#x
    b_out:
        popal
        ret
    """ % dict(P, cnt=where["cnt"]))
    # MsgProc(eax = self, edx = msg, ecx): inherited; on the turn broadcast clear the move dedupe and count the
    # owner's turns down (free at 0)
    place("msg", """
        push ebx
        push esi
        push edi
        mov esi, eax
        mov edi, edx
        call %(msgproc)#x
        cmp dword ptr [edi], %(turn)#x
        jne m_out
        mov dword ptr [esi + 0x1c], 0
        call $D
        pop ebx
        sub ebx, $D
        mov eax, [ebx + %(maplist)#x]
        mov eax, [eax]
        test byte ptr [eax + 0x3c], 2
        jnz m_out
        movsx eax, byte ptr [eax + 0xed]
        cmp eax, [esi + 0x14]
        jne m_out
        dec byte ptr [esi + 0x19]
        jg m_out
        mov eax, esi
        call %(free)#x
    m_out:
        pop edi
        pop esi
        pop ebx
        ret
    """ % P)
    # show(eax = self, edx = origin x, ecx = origin y, [esp+4] = target; ret 4): TCombatFire.Show's placement, drawn
    # with ShowLooped(GetSpell(226)+0x2C, slot 3 = the strategic EFFECTS\FIRESM.ILB fire, x, y, time, target)
    place("show", """
        push ebp
        mov ebp, esp
        sub esp, 0x10
        push ebx
        push esi
        push edi
        mov esi, eax
        mov [ebp - 4], edx
        mov [ebp - 8], ecx
        lea eax, [ebp - 0x10]
        push eax
        lea ecx, [ebp - 0xc]
        mov eax, [esi + 4]
        movsx edx, byte ptr [eax + 0x11]
        movsx eax, byte ptr [eax + 0x10]
        call %(hxtohp)#x
        call $D
        pop ebx
        sub ebx, $D
        mov eax, [ebx + %(hsset)#x]
        mov eax, [eax]
        mov eax, [eax + 0x84]
        mov edx, %(id)d
        call %(getspell)#x
        test eax, eax
        jz w_out
        mov edi, [eax + 0x2c]
        test edi, edi
        jz w_out
        cmp dword ptr [edi + 8], %(fslot)d
        jle w_out
        mov ecx, %(fms)d
        mov eax, dword ptr [0x7ffe000c]
        xor edx, edx
        div ecx
        mov eax, dword ptr [0x7ffe0008]
        div ecx
        mov edx, esi
        shr edx, 4
        and edx, 0xffff
        add eax, edx
        xor edx, edx
        mov ecx, 12
        div ecx
        mov eax, [edi + 4]
        mov eax, [eax + %(fslot)d*4]
        test eax, eax
        jz w_out
        mov byte ptr [eax + 0x30], 1
        mov dword ptr [eax + 0x34], edx
        xor eax, eax
        mov ecx, [ebp - 0xc]
        sub ecx, [ebp - 4]
        add ecx, 16
        mov edx, [ebp - 0x10]
        sub edx, [ebp - 8]
        add edx, 16
        push edx
        push eax
        push dword ptr [ebp + 8]
        mov eax, edi
        mov edx, %(fslot)d
        call %(showlp)#x
    w_out:
        pop edi
        pop esi
        pop ebx
        mov esp, ebp
        pop ebp
        ret 4
    """ % P)
    # getcls -> eax = the clone VMT (built on first use from TCombatFire's VMT); keeps every other register
    place("getcls", """
        push ebx
        push ecx
        push edx
        push esi
        push edi
        call $D
        pop ebx
        sub ebx, $D
        mov edx, [ebx + %(slot)#x]
        sub edx, %(suva)#x
        add edx, %(clone)#x
        cmp dword ptr [edx - 0x40], 0
        jne g_done
        mov esi, [ebx + %(fire)#x]
        sub esi, %(lo)d
        lea edi, [edx - %(lo)d]
        mov ecx, %(ndw)d
        .byte 0xf3, 0xa5
        mov dword ptr [edx - 0x1c], %(inst)d
        lea ecx, [ebx + %(classid)#x]
        mov [edx + 0x24], ecx
        lea ecx, [ebx + %(msg)#x]
        mov [edx + 0x44], ecx
        lea ecx, [ebx + %(show)#x]
        mov [edx + 0xa8], ecx
        mov [edx - 0x40], edx
    g_done:
        mov eax, edx
        pop edi
        pop esi
        pop edx
        pop ecx
        pop ebx
        ret
    """ % dict(P, classid=where["classid"], msg=where["msg"], show=where["show"]))
    # land: every landed fx, hex = [ebp-0x28]/[ebp-0x2C], fx = [ebp-0x20], te = [ebp-4]; then the previous target
    place("land", """
        pushal
        mov eax, [ebp - 4]
        cmp dword ptr [eax + 0x18], %(id)d
        jne l_out
        mov edx, [ebp - 0x20]
        cmp dword ptr [edx + 0x14], %(kind)d
        jne l_out
        cmp dword ptr [ebp - 0x28], -1
        jle l_out
        movsx edx, word ptr [eax + 0x20]
        cmp edx, [ebp - 0x28]
        jne l_ring
        movsx edx, word ptr [eax + 0x22]
        cmp edx, [ebp - 0x2c]
        je l_out
    l_ring:
        call $D
        pop ebx
        sub ebx, $D
        mov eax, [ebx + %(maplist)#x]
        mov eax, [eax]
        test byte ptr [eax + 0x3c], %(skip)d
        jnz l_out
        mov eax, [eax + 0x10]
        xor edx, edx
        call %(getlevel)#x
        test eax, eax
        jz l_out
        mov edx, [ebp - 0x28]
        mov ecx, [ebp - 0x2c]
        call %(getfield)#x
        test eax, eax
        jz l_out
        mov esi, eax
        mov edx, %(wcls)#x
        mov ecx, [esi]
        call dword ptr [ecx + 0x80]
        test eax, eax
        jz l_nowall
        cmp dword ptr [eax + 0x20], 0
        jg l_out
    l_nowall:
        mov eax, esi
        mov edx, %(gcls)#x
        mov ecx, [esi]
        call dword ptr [ecx + 0x80]
        test eax, eax
        jz l_nogate
        cmp dword ptr [eax + 0x20], 0
        jg l_out
    l_nogate:
        mov eax, esi
        mov edx, %(fcls)#x
        mov ecx, [esi]
        call dword ptr [ecx + 0x80]
        test eax, eax
        jz l_new
        mov edx, [ebx + %(maplist)#x]
        mov edx, [edx]
        movsx edx, byte ptr [edx + 0xed]
        mov [eax + 0x14], edx
        mov byte ptr [eax + 0x19], %(turns)d
        mov dword ptr [eax + 0x1c], 0
        jmp l_cnt
    l_new:
        call %(getcls)#x
        xor ecx, ecx
        mov dl, 1
        call %(create)#x
        mov edi, eax
        mov edx, [ebx + %(maplist)#x]
        mov edx, [edx]
        movsx edx, byte ptr [edx + 0xed]
        mov [edi + 0x14], edx
        mov byte ptr [edi + 0x19], %(turns)d
        mov dword ptr [edi + 0x1c], 0
        push dword ptr [ebp - 0x2c]
        push 0
        mov eax, [ebx + %(maplist)#x]
        mov eax, [eax]
        mov edx, edi
        mov ecx, [ebp - 0x28]
        call %(placehx)#x
        test al, al
        jnz l_cnt
        mov eax, edi
        call %(free)#x
        jmp l_out
    l_cnt:
        xor ecx, ecx
        call %(cnt)#x
    l_out:
        popal
        jmp %(prev)#x
    """ % dict(P, getcls=where["getcls"], cnt=where["cnt"]))
    # step (jmp'ed to from the post-step prologue 0x4085F0; [esp] = return, [esp+4] = the TE frame ebp):
    # ANY living unit entering a flame burns once per flame per turn
    place("step", """
        pushal
        call $D
        pop ebx
        sub ebx, $D
        mov eax, [ebx + %(maplist)#x]
        mov eax, [eax]
        test byte ptr [eax + 0x3c], %(skip)d
        jnz s_out
        mov eax, [esp + 0x24]
        mov eax, [eax - 4]
        test eax, eax
        jz s_out
        mov edi, [eax + 0x1c]
        test edi, edi
        jz s_out
        mov eax, edi
        mov edx, [eax]
        call dword ptr [edx + 0x60]
        test al, al
        jz s_out
        mov esi, [edi + 0x60]
        test esi, esi
        jz s_out
        mov eax, [esi + 4]
        test eax, eax
        jz s_out
        mov edx, %(fcls)#x
        mov ecx, [eax]
        call dword ptr [ecx + 0x80]
        test eax, eax
        jz s_out
        cmp [eax + 0x1c], edi
        je s_out
        mov [eax + 0x1c], edi
        mov ecx, 0xc
        call %(cnt)#x
        mov eax, esi
        call %(burn)#x
        mov eax, edi
        mov edx, [eax]
        call dword ptr [edx + 0x60]
        test al, al
        jnz s_out
        mov eax, [esp + 0x24]
        mov byte ptr [eax - 9], 3
    s_out:
        popal
        push ebp
        mov ebp, esp
        add esp, -0x14
        jmp %(sresume)#x
    """ % dict(P, burn=where["burn"], cnt=where["cnt"]))
    # bc (called from 0x41BEF2): replay the turn broadcast, then burn EVERY living unit of the new turn side S
    # standing on a flame (any flame owner)
    place("bc", """
        lea edx, [ebp - 0x44]
        mov ecx, [ebp - 4]
        mov eax, [ebp - 4]
        mov ebx, [eax]
        call dword ptr [ebx + 0x68]
        pushal
        call $D
        pop esi
        sub esi, $D
        mov eax, [esi + %(maplist)#x]
        mov eax, [eax]
        test byte ptr [eax + 0x3c], %(skip)d
        jnz c_ret
        movsx edx, byte ptr [eax + 0xed]
        push edx
        mov ecx, 4
        call %(cnt)#x
        mov eax, [eax + 0x10]
        xor edx, edx
        call %(getlevel)#x
        test eax, eax
        jz c_out
        mov edi, eax
        mov ebx, %(x0)d
    c_x:
        mov ebp, %(y0)d
    c_y:
        mov eax, edi
        mov edx, ebx
        mov ecx, ebp
        call %(getfield)#x
        test eax, eax
        jz c_next
        mov esi, eax
        mov edx, %(fcls)#x
        mov ecx, [esi]
        call dword ptr [ecx + 0x80]
        test eax, eax
        jz c_next
        mov eax, esi
        mov edx, %(ucls)#x
        mov ecx, [esi]
        call dword ptr [ecx + 0x80]
        test eax, eax
        jz c_next
        mov esi, eax
        mov eax, [esi + 0x1c]
        test eax, eax
        jz c_next
        movsx edx, byte ptr [eax + 0x45]
        cmp edx, [esp]
        jne c_next
        mov edx, [eax]
        call dword ptr [edx + 0x60]
        test al, al
        jz c_next
        mov ecx, 8
        call %(cnt)#x
        mov eax, esi
        call %(burn)#x
    c_next:
        inc ebp
        cmp ebp, %(y1)d
        jl c_y
        inc ebx
        cmp ebx, %(x1)d
        jl c_x
    c_out:
        pop edx
    c_ret:
        popal
        ret
    """ % dict(P, burn=where["burn"], cnt=where["cnt"]))
    # hn (called from 0x40E29B, in front of rotaway's hn0; after it ecx = HN, eax = target x, edx = target y):
    # spell 226 -> HN := 1 + ([te+0x34] mod 6) = the ring only (6 strikes), never HN 0 (the target hex)
    place("hn", """
        call %(prevhn)#x
        push eax
        push edx
        mov eax, [ebp - 4]
        cmp dword ptr [eax + 0x18], %(id)d
        jne h_out
        mov eax, [eax + 0x34]
        xor edx, edx
        mov ecx, %(ring)d
        div ecx
        lea ecx, [edx + 1]
    h_out:
        pop edx
        pop eax
        ret
    """ % P)
    zone = bytes(out)
    assert ZONE + len(zone) <= ZONE_END, hex(ZONE + len(zone))
    return zone, where


def reloc_set(d):
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


def check_thunks(d):
    import pefile
    pe = pefile.PE(data=bytes(d), fast_load=True); pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]])
    iat = {}
    for ent in getattr(pe, "DIRECTORY_ENTRY_IMPORT", []):
        for imp in ent.imports: iat[imp.address] = imp.name or b""
    for va, want in THUNKS.items():
        b = d[va - V2F:va - V2F + 6]
        assert b[:2] == b"\xff\x25", "thunk %#x is not jmp [mem]: %s" % (va, b.hex())
        slot = struct.unpack_from("<I", b, 2)[0]
        name = iat.get(slot, b"").decode("latin-1")
        assert all(p in name for p in want.split(".")), "thunk %#x -> %r, wanted %r" % (va, name, want)
    assert "SetUnit" in iat.get(SETUNIT_SLOT, b"").decode("latin-1"), "import slot %#x is %r" % (SETUNIT_SLOT, iat.get(SETUNIT_SLOT))
    assert struct.unpack_from("<I", d, FIRE_CELL - V2F)[0] == FIRE_VMT, "TCombatFire class cell moved"
    assert 0x558FAA42 <= CLONE_EP - VMT_LO and CLONE_EP + VMT_HI <= 0x558FAD00, "clone room outside the free BSS span"


def ep_check(path):
    """The clone room (BSS page slack) and the v2 diag counters (.idata page slack beyond its raw data) must be
    zero-at-load, writable AoWEPACK image memory."""
    import pefile
    pe = pefile.PE(path, fast_load=True)
    def room(lo_va, hi_va, what):
        for s in pe.sections:
            lo = 0x55700000 + s.VirtualAddress; vs = s.Misc_VirtualSize; raw_end = lo + s.SizeOfRawData
            if lo <= lo_va < lo + ((vs + 0xFFF) & ~0xFFF):
                if hi_va > lo + ((vs + 0xFFF) & ~0xFFF): return "%s runs past section %s's last page" % (what, s.Name)
                if lo_va < max(lo + vs, raw_end if s.SizeOfRawData else lo): return "%s inside section %s data (not slack)" % (what, s.Name)
                if not (s.Characteristics & 0x80000000): return "section %s not writable" % s.Name
                return None
        return "%s not inside any AoWEPACK section page" % what
    return room(CLONE_EP - VMT_LO, CLONE_EP + VMT_HI, "clone room") or room(DIAG_EP, DIAG_EP + 0x20, "diag counters")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--dll", default=DEFAULT_DLL); ap.add_argument("--ep", default=DEFAULT_EP)
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true"); ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read())
    check_thunks(d)
    rd = lambda va, n: bytes(d[va - V2F:va - V2F + n])
    inzone = lambda t: ZONE <= t < ZONE_END
    zl = rd(ZONE, ZONE_END - ZONE)
    zmagic = zl[4:8]
    site = rd(LAND, 7)
    if site[0] == 0xE8 and site[5:] == b"\x90\x90":
        t = LAND + 5 + struct.unpack_from("<i", site, 1)[0]
        if inzone(t): lstate, prev = "ours", struct.unpack_from("<I", zl, 0)[0]
        else: lstate, prev = "chain", t
    elif site == LAND_VANILLA:
        lstate, prev = "vanilla", 0
    else:
        lstate, prev = "OTHER(%s)" % site.hex(), 0
    # v2: rotaway's hn0 call-hook at 0x40E29B (e8 rel32 90 90) - chained in front of
    hs = rd(HN_SITE, HN_LEN)
    if hs[0] == 0xE8 and hs[5:] == b"\x90\x90":
        t = HN_SITE + 5 + struct.unpack_from("<i", hs, 1)[0]
        if inzone(t):
            hstate, prev_hn = ("ours", struct.unpack_from("<I", zl, 8)[0]) if zmagic in (MAGIC, b"WoF2") else ("OTHER(zone call, no v2 header)", 0)
        else: hstate, prev_hn = "chain", t
    else:
        hstate, prev_hn = "OTHER(%s)" % hs.hex(), 0
    zone, where = build(prev if prev else 0x7FFFFFF0, prev_hn if prev_hn else 0x7FFFFFF0)
    want_step = b"\xe9" + struct.pack("<i", where["step"] - (STEP + 5)) + b"\x90"
    want_bc = b"\xe8" + struct.pack("<i", where["bc"] - (BC + 5)) + b"\x90" * 9
    want_hn = b"\xe8" + struct.pack("<i", where["hn"] - (HN_SITE + 5)) + b"\x90\x90"
    sb, bb = rd(STEP, 6), rd(BC, 14)
    sstate = "vanilla" if sb == STEP_VANILLA else "ours" if sb[0] == 0xE9 and inzone(STEP + 5 + struct.unpack_from("<i", sb, 1)[0]) else "OTHER(%s)" % sb.hex()
    bstate = "vanilla" if bb == BC_VANILLA else "ours" if bb[0] == 0xE8 and inzone(BC + 5 + struct.unpack_from("<i", bb, 1)[0]) else "OTHER(%s)" % bb.hex()
    rl = reloc_set(bytes(d))
    bad = [hex(r) for r in rl if ZONE - 3 <= r < ZONE_END or LAND - 3 <= r < LAND + 7 or STEP - 3 <= r < STEP + 6
           or BC - 3 <= r < BC + 14 or HN_SITE - 3 <= r < HN_SITE + HN_LEN]
    zstate = "zero" if not any(zl) else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) \
        else "ours(old)" if zmagic == MAGIC or zmagic in OLD_MAGICS else "DIFFERS"
    epmsg = ep_check(a.ep)
    print("AoWTCPCK wall of flames v3: land %s (prev %#x) | hn %s (prev %#x) | step %s | bc %s | zone %s [%s] (%d B: %s) | relocs %s | AoWEPACK clone room %s" % (
        lstate, prev, hstate, prev_hn, sstate, bstate, zstate, zmagic, len(zone), ", ".join("%s=%#x" % kv for kv in where.items()),
        bad or "none", epmsg or "ok"))
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        cav = sorted((v, k) for k, v in where.items()) + [(ZONE + len(zone), None)]
        for (va, nm), (nx, _n) in zip(cav, cav[1:]):
            print("  [%s]" % nm)
            for i in md.disasm(zone[va - ZONE:nx - ZONE], va):
                if i.mnemonic == "add" and i.op_str == "byte ptr [eax], al": break
                print("   %08X  %-18s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if a.revert:
        if lstate != "ours" or sstate != "ours" or bstate != "ours" or hstate not in ("ours", "chain"):
            print("ABORT revert: not ours (land %s, hn %s, step %s, bc %s) - revert whatever chained in front first" % (lstate, hstate, sstate, bstate)); return 1
        d[LAND - V2F:LAND - V2F + 5] = b"\xe8" + struct.pack("<i", prev - (LAND + 5))
        if hstate == "ours":   # v2 -> rotaway's call again (a v1 build never touched the hn site)
            d[HN_SITE - V2F:HN_SITE - V2F + HN_LEN] = b"\xe8" + struct.pack("<i", prev_hn - (HN_SITE + 5)) + b"\x90\x90"
        d[STEP - V2F:STEP - V2F + 6] = STEP_VANILLA
        d[BC - V2F:BC - V2F + 14] = BC_VANILLA
        d[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE)
        with open(a.dll, "r+b") as f: f.write(bytes(d))
        print("reverted (land -> %#x, hn -> %s, step / bc vanilla, zone zeroed)" % (prev, hex(prev_hn) if hstate == "ours" else "untouched")); return 0
    if bad or lstate.startswith("OTHER") or sstate.startswith("OTHER") or bstate.startswith("OTHER") or hstate.startswith("OTHER") \
            or zstate == "DIFFERS" or lstate == "vanilla":
        print("ABORT (%s)" % ("land site is vanilla - the Gravity Well / Sanctify / Steadfast chain is expected in front of it" if lstate == "vanilla"
                              else "relocs / foreign hook / zone not free (hn site must be rotaway's hn0 call or ours)"))
        return 1
    if epmsg: print("ABORT (%s)" % epmsg); return 1
    if lstate == "ours" and zstate == "ours" and sstate == "ours" and bstate == "ours" and hstate == "ours":
        print("already applied (v3)"); return 0
    if zstate == "ours(old)": print("older build of this patch detected (%s) -> in-place upgrade to v3" % zmagic)
    d[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE); d[ZONE - V2F:ZONE - V2F + len(zone)] = zone
    d[LAND - V2F:LAND - V2F + 5] = b"\xe8" + struct.pack("<i", where["land"] - (LAND + 5))
    d[HN_SITE - V2F:HN_SITE - V2F + HN_LEN] = want_hn
    d[STEP - V2F:STEP - V2F + 6] = want_step
    d[BC - V2F:BC - V2F + 14] = want_bc
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(a.dll, ".bak_walloflames3" if zstate == "ours(old)" else ".bak_walloflames")
    if os.path.abspath(a.dll) == os.path.abspath(DEFAULT_DLL) and not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    with open(a.dll, "r+b") as f: f.write(bytes(d))
    assert open(a.dll, "rb").read() == bytes(d); print("Written and verified"); return 0


if __name__ == "__main__":
    sys.exit(main())
