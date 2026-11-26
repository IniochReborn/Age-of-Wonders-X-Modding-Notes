"""
ROYAL AMBITION (spell 230, Cosmos tier 3) - global enchantment.  AoWEPACK.dll + AoWx.exe (v2).

Spec (user 2026-10-17): global spell, research 150, cost 50, upkeep 7.  "Diplomatic bonuses and penalties are doubled
for the caster's race."  v2 (2026-10-18, user: "doesn't seem to work, or at least doesn't display properly, possibly
both.  City actions (migrate, upgrade, loot, raze, etc) should have double bonus/malus.  And diplomatic actions
(peace, war, alliance, etc) should also double bonus/malus.").

RE - race relations:
  Every race (TRace, list [map+0x144], TRaceList.GetRace 0x5574D1F0 by index; a player's own race index = [player+0xA5])
  keeps one relation value per player in [race+0x10] (TIntList indexed player-1, stored minus [[map+0x144]+0x10]).
  ALL gameplay changes go through TRace.SetPlayerRelationValue 0x5574CDC4 (eax = race, dl = player index 1-based =
  the enchantment caster byte [ench+0x19], ecx = the NEW absolute value) as set(get + delta).  The 18 callers:
    TDiplomaticAction.ExecuteAccept (+0xF6 / +0x136) and .ExecuteSend (+0x1E5 / +0x22B / +0x339 / +0x37F) - every
      diplomatic action (war, peace, alliance, tribute, ...): per race, delta = TDiplomaticAction.GetRelationModifier
      0x5572CEAC (eax = action, dl = player, cl = race) - the SAME routine AoWx.exe's diplomacy window imports
      (IAT 0x45DF24) to PREVIEW the change;
    TCityProductionControl.ExecuteProduction (+0x20B loot: city race -30 / +0x363 migrate: -15), .NewTurn (+0xFF /
      +0x2F9 / +0x5B2: upgrade / production completion race effects), .ExecuteCancelProduction (4 sites);
    TPlayerCropStructure.CropTrampled, TCity.CropTrampled, TCity.ExecuteRaze (+0x53).
  The daily drift (TRace.NewDay) and the resets write the list directly (not changed).
  AoWx.exe's city screen (TCityScreen, ebx = screen, [ebx+0x2B0] = city) PREVIEWS the city-action race effects with
  HARD-CODED constants: -40 @0x43C0D0, +20 @0x43C159, +10 @0x43C779, +5 @0x43C964, -60 @0x43CA92, -60 @0x43CBB2
  (`mov dword [ebp-x], imm32`, formatted through XRelationMinus/PlusYRStr).

ROOT CAUSE of v1 "doesn't work / doesn't display": v1 doubled ONLY when the changed race was the caster's OWN race
  (race == GetRace([player+0xA5])).  Loot / migrate / raze / production change the CITY's race, and diplomatic
  actions change every race by its own modifier - so practically nothing the user did was doubled; and none of the
  PREVIEWS (diplomacy window = GetRelationModifier, city screen = exe constants) were ever doubled.

v2 EFFECT: while player P has an ACTIVE Royal Ambition, EVERY relation change caused for P is doubled (any race,
  bonus and malus):
  * GRM - entry hook on TDiplomaticAction.GetRelationModifier (7 B `push ebx/esi/edi/ebp; add esp,-8`): returns
    2 x the vanilla modifier when dl = P has 230 -> diplomatic actions AND the diplomacy window preview double.
  * RS - entry hook on TRace.SetPlayerRelationValue (5 B): dl = P has 230 -> new' = 2*new - old, clamped to
    [min(new,0), max(new,100)]; calls returning to the 6 TDiplomaticAction sites are NOT doubled again (already
    doubled by GRM) - only clamped to [min(old,0), max(old,100)].  Ret addresses compared PIC (rebase-safe).
  * XCHK (fixed entry ZONE+0x60): eax = a city -> eax = 1 if its owner (TStructure.GetPlayer 0x5575E7B4) has 230.
  * AoWx.exe: the 6 city-screen constants -> `call` a cave (.xedt 0x62FB00..0x62FD00) that stores imm or 2*imm
    (XCHK reached through the AoWEPACK IAT slot 0x45DF24 delta - AoWEPACK rebases at runtime).
  Deterministic, synced state only (MP-safe; the exe part is display only).

GLOBAL PLUMBING (unchanged from v1) - Earth Mastery donor with marker 230 (copy of patch_riteseas_v1.py's), CHAINED
IN FRONT of whatever sits at the Earth Mastery sites (vanilla sites get replay stubs).  LIFO: royal -> rite -> depths
-> goldenage (revert this one first).

AoWEPACK zone 0x5587E800..0x5587F000.  v2 header: +0 "RYA2", +0x10 7 x 8 B saved site bytes, +0x48 3 dwords saved
slots, +0x60 XCHK entry (jmp), caves from +0x70.  v1 ("RYA1": 6 sites at +0x10, slots at +0x40) upgrades in place.
AoWx.exe zone 0x62FB00..0x62FD00: +0 "RYX2", +0x10 6 x 8 B saved constant instructions, caves from +0x50.
Dry-run default; --apply / --revert / --dis; --dll / --exe <path> = work on copies (scratch tests).
Backups <game>\backup\AoWEPACK.dll.bak_royal2 / AoWx.exe.bak_royal2 (v1 backup .bak_royal kept).
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

BASE = 0x55700000
ZONE, ZONE_END = 0x5587E800, 0x5587F000
MAGIC, MAGIC1 = b"RYA2", b"RYA1"
HDR_SITES, HDR_SLOTS, XCHK_OFF, CAVES = 0x10, 0x48, 0x60, 0x70
V1_HDR_SITES, V1_HDR_SLOTS = 0x10, 0x40
XCHK_VA = ZONE + XCHK_OFF
SPELL_ID, EM_ID, FX_MARK = 230, 0x40, 0xE6

MAP_GLOBAL, LIST_GET = 0x558FA040, 0x5577E13C
BASE_ACT, BASE_DEACT, BASE_CHK = 0x5577DBA0, 0x5577DC3C, 0x5577DAE8
EM_ACT, EM_DEACT, EM_CHK, EM_CHK_MSG, EM_CHK_SEH = 0x557F3370, 0x557F3410, 0x557F32AC, 0x557F3303, 0x557F335F
EM_ENCH_CREATE, EM_ENCH_CELL = 0x557F3204, 0x557EF318
MASTERY_MSG, LSTRASG, WORLD_EVENT = 0x557EF7C0, 0x55701150, 0x55779068
REL_SET, REL_GET = 0x5574CDC4, 0x5574CDFC     # TRace.SetPlayerRelationValue / GetPlayerRelationValue (eax = race, dl = player)
REL_SET_JLE = 0x5574CDF7                      # the vanilla prologue's `jle` target (pop ebx / ret)
GRM, GRM_RESUME = 0x5572CEAC, 0x5572CEB3      # TDiplomaticAction.GetRelationModifier (eax = action, dl = player, cl = race) / after the 7 B prologue
STRUCT_GETPLAYER = 0x5575E7B4                 # TStructure.GetPlayer (eax = structure) -> al = owner index (-1 = none)
DIPLO_RETS = (0x5572DEAF, 0x5572DEEF, 0x5572E7AA, 0x5572E7F0, 0x5572E8FE, 0x5572E944)   # SetPlayerRelationValue returns in ExecuteAccept / ExecuteSend

SITES = [   # name, VA, vanilla bytes, hook kind, our cave
    ("CE", 0x557F373C, bytes.fromhex("33c9b201a1"), "jmp", "ce"),
    ("MM", 0x557F36D9, bytes.fromhex("e8e2c0ffff"), "call", "mm"),
    ("EV", 0x557F3712, bytes.fromhex("b209e84f59f8ff"), "call", "ev"),
    ("PS", 0x557969B5, bytes.fromhex("8bd8b80c000000"), "call", "ps"),
    ("ID", 0x557971A4, bytes.fromhex("ba40000000"), "call", "id_"),
    ("RS", REL_SET, bytes.fromhex("5384d27e2e"), "jmp", "rs"),
    ("GRM", GRM, bytes.fromhex("5356575583c4f8"), "jmp", "grm"),
]
OWN = ("RS", "GRM")                           # entry hooks we own outright (must be vanilla before us)
SLOTS = [   # name, slot VA, vanilla target, our cave
    ("emAct", 0x557EF3C0, EM_ACT, "ac"),
    ("emDeact", 0x557EF3B8, EM_DEACT, "de"),
    ("emChk", 0x557EF3BC, EM_CHK, "chk"),
]

# AoWx.exe (never rebases): the city-screen relation-preview constants
EXE_BASE = 0x400000
XZ, XZ_END, XMAGIC, X_HDR, X_CAVES = 0x62FB00, 0x62FD00, b"RYX2", 0x10, 0x50
IAT_GRM = 0x45DF24                            # AoWx.exe IAT slot = runtime address of TDiplomaticAction.GetRelationModifier
EXE_SITES = [   # VA, vanilla 7 B `mov dword [ebp+d8], imm32`, value (doc)
    (0x43C0D0, bytes.fromhex("c745f4d8ffffff"), -40),
    (0x43C159, bytes.fromhex("c745f414000000"), 20),
    (0x43C779, bytes.fromhex("c745ec0a000000"), 10),
    (0x43C964, bytes.fromhex("c745ec05000000"), 5),
    (0x43CA92, bytes.fromhex("c745ecc4ffffff"), -60),
    (0x43CBB2, bytes.fromhex("c745ecc4ffffff"), -60),
]
SCREEN_CITY = 0x2B0                           # TCityScreen field = the city shown (ebx = the screen at every site)

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


def build(saved_sites, saved_slots):
    """saved_sites: name -> the site's bytes before us; saved_slots: name -> the slot's value before us.
    Returns the whole zone image (header + XCHK entry + caves) and the cave VAs."""
    out = bytearray(CAVES); out[0:4] = MAGIC; where = {}
    for k, (nm, _va, orig, _kind, _c) in enumerate(SITES):
        out[HDR_SITES + 8 * k:HDR_SITES + 8 * k + len(orig)] = saved_sites[nm]
    for k, (nm, _sva, _orig, _c) in enumerate(SLOTS):
        struct.pack_into("<I", out, HDR_SLOTS + 4 * k, saved_slots[nm])
    C = {"id": SPELL_ID, "emid": EM_ID, "mark": FX_MARK, "map": MAP_GLOBAL, "get": LIST_GET, "bact": BASE_ACT,
         "bdeact": BASE_DEACT, "bchk": BASE_CHK, "emmsg": EM_CHK_MSG, "emseh": EM_CHK_SEH, "emcreate": EM_ENCH_CREATE,
         "emcell": EM_ENCH_CELL, "mmsg": MASTERY_MSG, "lstrasg": LSTRASG, "wev": WORLD_EVENT,
         "relget": REL_GET, "rsret": REL_SET + 5, "rsjle": REL_SET_JLE, "grmres": GRM_RESUME,
         "sgetpl": STRUCT_GETPLAYER}
    for k, r in enumerate(DIPLO_RETS): C["dr%d" % k] = r

    def place(name, src, pic=False):
        while len(out) % 16: out.append(0)
        va = ZONE + len(out); where[name] = va
        d = dict(C, **where)
        out.extend(asm_pic(src % d, va) if pic else bytes(ks.asm(src % d, va)[0]))

    # previous targets: a site still vanilla gets a replay stub; otherwise decode its call/jmp
    prev = {}
    for nm, va, orig, kind, _c in SITES:
        if nm in OWN: continue  #                       # our own entry hook: the prologue is replayed inline in `rs`
        live = saved_sites[nm]
        if live != orig:
            prev[nm] = va + 5 + struct.unpack_from("<i", live, 1)[0]; continue
        if nm == "CE":
            place("stubCE", """
                push ebx
                call $D
                pop ebx
                sub ebx, $D
                mov eax, [ebx+%(emcell)#x]
                pop ebx
                xor ecx, ecx
                mov dl, 1
                jmp %(emcreate)#x
            """, pic=True)
        elif nm == "MM":
            where["stubMM"] = MASTERY_MSG
        elif nm == "EV":
            place("stubEV", "mov dl, 9\njmp %(wev)#x")
        elif nm == "PS":
            place("stubPS", "mov ebx, eax\nmov eax, 0xc\nret")
        elif nm == "ID":
            place("stubID", "mov edx, %(emid)d\nret")
        prev[nm] = where["stub" + nm]
    for nm, _sva, _orig, _c in SLOTS:
        prev[nm] = saved_slots[nm]
    C.update({"p" + k: v for k, v in prev.items()})

    # gxa: dl = player index, ecx = marker -> al = 1 if that player has an ACTIVE global enchantment with that
    # marker; all other regs preserved (copy of Golden Age's scanner)
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
    # RS (v2): TRace.SetPlayerRelationValue entry (jmp'ed to; eax = race, dl = player index, ecx = NEW value).
    # dl > 0 and the player has an ACTIVE marker-230 enchantment -> ANY race:
    #   a call returning into TDiplomaticAction.ExecuteAccept/ExecuteSend (already doubled by GRM) -> only clamped to
    #   [min(old,0), max(old,100)];  any other caller -> ecx = 2*new - old, clamped to [min(new,0), max(new,100)].
    # The return address is compared to the preferred-base VAs via the PIC delta (AoWEPACK rebases at runtime).
    # Then the vanilla prologue is replayed (push ebx / test dl,dl / jle 0x5574CDF7) and execution resumes at +5.
    place("rs", """
        test dl, dl
        jle rs_replay
        pushal
        mov esi, eax
        mov edi, ecx
        movsx ebp, dl
        mov ecx, %(id)d
        call %(gxa)#x
        test al, al
        jz rs_done
        call $D
        pop ebx
        sub ebx, $D
        mov eax, [esp+0x20]
        sub eax, ebx
        xor ebx, ebx
        cmp eax, %(dr0)#x
        je rs_dip
        cmp eax, %(dr1)#x
        je rs_dip
        cmp eax, %(dr2)#x
        je rs_dip
        cmp eax, %(dr3)#x
        je rs_dip
        cmp eax, %(dr4)#x
        je rs_dip
        cmp eax, %(dr5)#x
        jne rs_go
    rs_dip:
        inc ebx
    rs_go:
        mov eax, esi
        mov edx, ebp
        call %(relget)#x
        test ebx, ebx
        jnz rs_dclamp
        mov ecx, edi
        add ecx, edi
        sub ecx, eax
        mov eax, edi
        jmp rs_clamp
    rs_dclamp:
        mov ecx, edi
    rs_clamp:
        mov edx, eax
        test edx, edx
        jle rs_lo
        xor edx, edx
    rs_lo:
        cmp ecx, edx
        jge rs_lo_ok
        mov ecx, edx
    rs_lo_ok:
        mov edx, eax
        cmp edx, 100
        jge rs_hi
        mov edx, 100
    rs_hi:
        cmp ecx, edx
        jle rs_hi_ok
        mov ecx, edx
    rs_hi_ok:
        mov [esp+0x18], ecx
    rs_done:
        popal
    rs_replay:
        push ebx
        test dl, dl
        jle %(rsjle)#x
        jmp %(rsret)#x
    """, pic=True)
    # GRM (v2): TDiplomaticAction.GetRelationModifier entry (jmp'ed to; eax = action, dl = player, cl = race) ->
    # the vanilla modifier (prologue replayed in grm_orig), doubled when dl has an ACTIVE Royal Ambition.  Used by
    # ExecuteSend / ExecuteAccept (the effect) AND by AoWx.exe's diplomacy window (the preview).
    place("grm_orig", """
        push ebx
        push esi
        push edi
        push ebp
        add esp, -8
        jmp %(grmres)#x
    """)
    place("grm", """
        push edx
        call %(grm_orig)#x
        pop edx
        push eax
        push ecx
        mov ecx, %(id)d
        call %(gxa)#x
        test al, al
        pop ecx
        pop eax
        jz grm_ret
        add eax, eax
    grm_ret:
        ret
    """)
    # XCHK (v2; entered through the fixed jmp at ZONE+0x60 - AoWx.exe calls it via its IAT delta): eax = a city ->
    # eax = 1 if the city's owner (TStructure.GetPlayer, al, -1 = none) has an ACTIVE Royal Ambition, else 0.
    # Keeps ebx / ecx / edx / esi / edi / ebp.
    place("xchk", """
        push ecx
        push edx
        test eax, eax
        jz xc_no
        call %(sgetpl)#x
        test al, al
        jle xc_no
        mov dl, al
        mov ecx, %(id)d
        call %(gxa)#x
        movzx eax, al
        jmp xc_out
    xc_no:
        xor eax, eax
    xc_out:
        pop edx
        pop ecx
        ret
    """)
    # CE (jmp'ed to; eax = spell): ours -> prev creates the enchantment, then marker + name
    place("ce", """
        cmp dword ptr [eax+0x10], %(id)d
        jne ce_prev
        push eax
        call %(pCE)#x
        pop edx
        mov dword ptr [eax+0x14], %(id)d
        push eax
        lea eax, [eax+0x1c]
        mov edx, [edx+8]
        call %(lstrasg)#x
        pop eax
        ret
    ce_prev:
        jmp %(pCE)#x
    """)
    place("mm", """
        cmp dword ptr [esi+0x10], %(id)d
        je mm_skip
        jmp %(pMM)#x
    mm_skip:
        ret
    """)
    place("ac", """
        cmp dword ptr [eax+0x14], %(id)d
        je ac_ours
        jmp %(pemAct)#x
    ac_ours:
        jmp %(bact)#x
    """)
    place("de", """
        cmp dword ptr [eax+0x14], %(id)d
        je de_ours
        jmp %(pemDeact)#x
    de_ours:
        jmp %(bdeact)#x
    """)
    # CHK: eax = ench, dl = player, ecx = &message; returns al (1 = may cast)
    place("chk", """
        cmp dword ptr [eax+0x14], %(id)d
        je chk_ours
        jmp %(pemChk)#x
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
    # EV (called; esi = spell): prev makes the TWorldFXHS (eax), ours marks it
    place("ev", """
        call %(pEV)#x
        cmp dword ptr [esi+0x10], %(id)d
        jne ev_done
        mov byte ptr [eax+0x25], %(mark)d
    ev_done:
        ret
    """)
    # PS (called): prev (mov ebx,eax / mov eax,0xC), then the particle ebx inherits the master's mark ([ebp-4])
    place("ps", """
        call %(pPS)#x
        push ecx
        mov ecx, [ebp-4]
        mov cl, byte ptr [ecx+0x25]
        mov byte ptr [ebx+0x25], cl
        pop ecx
        ret
    """)
    # ID (called; [ebp-4] = the particle): prev picks edx, ours overrides for our mark
    place("id_", """
        call %(pID)#x
        push ecx
        mov ecx, [ebp-4]
        cmp byte ptr [ecx+0x25], %(mark)d
        jne id_done
        mov edx, %(id)d
    id_done:
        pop ecx
        ret
    """)
    # the fixed XCHK entry at ZONE+0x60 (AoWx.exe calls this exact VA + the runtime delta)
    out[XCHK_OFF:XCHK_OFF + 5] = b"\xe9" + struct.pack("<i", where["xchk"] - (XCHK_VA + 5))
    return bytes(out), where


def build_exe(saved):
    """saved: list of the 6 sites' bytes before us.  -> (zone image, cave VAs).  Each site `mov dword [ebp+d], imm`
    becomes `call cave; nop; nop`; the cave stores imm, or 2*imm when the shown city's owner has Royal Ambition."""
    out = bytearray(X_CAVES); out[0:4] = XMAGIC; where = []
    for k, b in enumerate(saved): out[X_HDR + 8 * k:X_HDR + 8 * k + 7] = b
    for k, (va, orig, _v) in enumerate(EXE_SITES):
        disp = orig[2]; imm = struct.unpack_from("<i", orig, 3)[0]
        while len(out) % 16: out.append(0)
        cva = XZ + len(out); where.append(cva)
        src = """
            pushfd
            pushal
            mov edx, %(imm)d
            mov eax, dword ptr [ebx+%(city)#x]
            test eax, eax
            jz x_st
            mov ecx, dword ptr [%(iat)#x]
            sub ecx, %(grm)#x
            add ecx, %(xchk)#x
            call ecx
            mov edx, %(imm)d
            test eax, eax
            jz x_st
            add edx, edx
        x_st:
            mov dword ptr [ebp%(disp)+d], edx
            popal
            popfd
            ret
        """ % {"imm": imm, "city": SCREEN_CITY, "iat": IAT_GRM, "grm": GRM, "xchk": XCHK_VA,
               "disp": disp - 256 if disp > 127 else disp}
        out.extend(bytes(ks.asm(src, cva)[0]))
    return bytes(out), where


def xhook(va, cva):
    return b"\xe8" + struct.pack("<i", cva - (va + 5)) + b"\x90\x90"


def relocs(d, base=BASE):
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


def foff(d, va, base=BASE):
    pe = struct.unpack_from("<I", d, 0x3C)[0]; opt = struct.unpack_from("<H", d, pe + 20)[0]; nsec = struct.unpack_from("<H", d, pe + 6)[0]
    rva = va - base
    for k in range(nsec):
        vs, sva, rs, ro = struct.unpack_from("<IIII", d, pe + 24 + opt + 40 * k + 8)
        if sva <= rva < sva + max(vs, rs): return ro + rva - sva
    raise ValueError(hex(va))


def hook_bytes(va, orig, kind, tgt):
    return (b"\xe9" if kind == "jmp" else b"\xe8") + struct.pack("<i", tgt - (va + 5)) + b"\x90" * (len(orig) - 5)


def dis(code, where):
    import capstone
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    inv = {v: k for k, v in where.items()}
    for i in md.disasm(code[CAVES:], ZONE + CAVES):
        if i.address in inv: print("  -- %s" % inv[i.address])
        print("   %08X  %-20s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))


def zone_state(d, rl):
    """-> (state, saved_sites, saved_slots) for the AoWEPACK half; state in vanilla / v1 / v2 / bad:<why>."""
    zo = foff(d, ZONE); zl = bytes(d[zo:zo + ZONE_END - ZONE])
    bad = [hex(r) for r in rl if ZONE - 3 < r < ZONE_END or any(va - 3 < r < va + len(o) for _n, va, o, _k, _c in SITES)]
    noreloc = [nm for nm, sva, _o, _c in SLOTS if sva not in rl]
    if bad or noreloc: return "bad:relocs in zone/sites %s | slots without reloc %s" % (bad, noreloc), None, None
    if zl[:4] == MAGIC:
        ss = {nm: zl[HDR_SITES + 8 * k:HDR_SITES + 8 * k + len(o)] for k, (nm, _va, o, _k, _c) in enumerate(SITES)}
        sl = {nm: struct.unpack_from("<I", zl, HDR_SLOTS + 4 * k)[0] for k, (nm, *_r) in enumerate(SLOTS)}
        return "v2", ss, sl
    if zl[:4] == MAGIC1:
        ss = {nm: zl[V1_HDR_SITES + 8 * k:V1_HDR_SITES + 8 * k + len(o)] for k, (nm, _va, o, _k, _c) in enumerate(SITES[:6])}
        sl = {nm: struct.unpack_from("<I", zl, V1_HDR_SLOTS + 4 * k)[0] for k, (nm, *_r) in enumerate(SLOTS)}
        ss["GRM"] = bytes(d[foff(d, GRM):foff(d, GRM) + 7])
        return "v1", ss, sl
    if any(zl): return "bad:zone not free", None, None
    return "vanilla", None, None


def main():
    ap = argparse.ArgumentParser()
    for f in ("--apply", "--revert", "--dis"): ap.add_argument(f, action="store_true")
    ap.add_argument("--dll", default=None); ap.add_argument("--exe", default=None); a = ap.parse_args()
    DLL = a.dll or game_file("AoWEPACK.dll"); EXE = a.exe or game_file("AoWx.exe")
    d = bytearray(open(DLL, "rb").read()); e = bytearray(open(EXE, "rb").read())
    rl = relocs(bytes(d))
    st, saved_sites, saved_slots = zone_state(d, rl)
    live_sites = {nm: bytes(d[foff(d, va):foff(d, va) + len(o)]) for nm, va, o, _k, _c in SITES}
    live_slots = {nm: struct.unpack_from("<I", d, foff(d, sva))[0] for nm, sva, _o, _c in SLOTS}
    if st.startswith("bad"): print("AoWEPACK:", st, "-> ABORT"); return 1

    # ---- AoWx.exe half state
    xrl = relocs(bytes(e), EXE_BASE)
    xbad = [hex(r) for r in xrl if XZ - 3 < r < XZ_END or any(va - 3 < r < va + 7 for va, _o, _v in EXE_SITES)]
    if xbad: print("AoWx.exe: relocs in zone/sites %s -> ABORT" % xbad); return 1
    xo = foff(e, XZ, EXE_BASE); xl = bytes(e[xo:xo + XZ_END - XZ])
    xlive = [bytes(e[foff(e, va, EXE_BASE):foff(e, va, EXE_BASE) + 7]) for va, _o, _v in EXE_SITES]
    if xl[:4] == XMAGIC:
        xsaved = [xl[X_HDR + 8 * k:X_HDR + 8 * k + 7] for k in range(len(EXE_SITES))]
        xcode, xwhere = build_exe(xsaved)
        xok = xl[:len(xcode)] == xcode and not any(xl[len(xcode):]) and \
            all(xlive[k] == xhook(va, xwhere[k]) for k, (va, _o, _v) in enumerate(EXE_SITES))
        xst = "v2" if xok else "DIFFERS"
    elif any(xl): xst = "bad:zone not free"
    else:
        xsaved = xlive
        xst = "vanilla" if all(xlive[k] == o for k, (_va, o, _v) in enumerate(EXE_SITES)) else \
            "bad:sites not vanilla %s" % [x.hex() for x in xlive]
    if xst.startswith("bad") or xst == "DIFFERS": print("AoWx.exe:", xst, "-> ABORT"); return 1

    zo = foff(d, ZONE)
    if st == "v2":
        code, where = build(saved_sites, saved_slots)
        s2 = {nm: "ours" if live_sites[nm] == hook_bytes(va, o, kind, where[c]) else "OTHER" for nm, va, o, kind, c in SITES}
        s2.update({nm: "ours" if live_slots[nm] == where[c] else "OTHER(%#x)" % live_slots[nm] for nm, _s, _o, c in SLOTS})
        zl = bytes(d[zo:zo + ZONE_END - ZONE]); zok = zl[:len(code)] == code and not any(zl[len(code):])
        print("AoWEPACK: applied (v2) | zone %s (%d B) | %s | AoWx.exe %s" % ("ours" if zok else "DIFFERS", len(code), s2, xst))
        if a.dis: dis(code, where)
        if not zok or any(v != "ours" for v in s2.values()):
            print("ABORT (something chained in front of us or the zone changed - revert that first, LIFO)"); return 1
        if not a.revert:
            if xst == "v2": print("already applied (v2)"); return 0
            print("AoWx.exe half missing -> re-applying it")
    elif st == "v1":
        # v1 hooks must still be ours: every site a call/jmp into our zone, every slot pointing into it
        def inz(v): return ZONE <= v < ZONE_END
        s1 = {}
        for nm, va, o, kind, _c in SITES[:6]:
            lv = live_sites[nm]; t = va + 5 + struct.unpack_from("<i", lv, 1)[0]
            s1[nm] = "ours(v1)" if lv[0] == (0xE9 if kind == "jmp" else 0xE8) and inz(t) else "OTHER"
        for nm, _s, _o, _c in SLOTS: s1[nm] = "ours(v1)" if inz(live_slots[nm]) else "OTHER"
        s1["GRM"] = "vanilla" if live_sites["GRM"] == SITES[6][2] else "OTHER"
        print("AoWEPACK: applied (v1) | %s | AoWx.exe %s" % (s1, xst))
        if any(v.startswith("OTHER") for v in s1.values()):
            print("ABORT (something chained in front of v1 - revert that first, LIFO)"); return 1
    else:
        s0 = {}
        for nm, va, o, kind, _c in SITES:
            lv = live_sites[nm]
            if lv == o: s0[nm] = "vanilla"
            elif nm not in OWN and lv[0] == (0xE9 if kind == "jmp" else 0xE8) and all(b == 0x90 for b in lv[5:]):
                s0[nm] = "chain->%#x" % (va + 5 + struct.unpack_from("<i", lv, 1)[0])
            else: s0[nm] = "UNKNOWN"
        for nm, _s, o, _c in SLOTS:
            s0[nm] = "vanilla" if live_slots[nm] == o else "chain->%#x" % live_slots[nm]
        print("AoWEPACK: not applied | %s | AoWx.exe %s" % (s0, xst))
        if "UNKNOWN" in s0.values(): print("ABORT (RS / GRM must be vanilla; others vanilla or a plain call/jmp chain)"); return 1
        if a.revert:
            if xst != "v2": print("not applied - nothing to revert"); return 0
            print("AoWEPACK half not applied - reverting the AoWx.exe half only")
        saved_sites, saved_slots = live_sites, live_slots

    if a.revert:
        if st in ("v1", "v2"):
            for nm, va, o, _k, _c in SITES:
                if nm in saved_sites: d[foff(d, va):foff(d, va) + len(o)] = saved_sites[nm]
            for nm, sva, _o, _c in SLOTS: struct.pack_into("<I", d, foff(d, sva), saved_slots[nm])
            d[zo:zo + ZONE_END - ZONE] = bytes(ZONE_END - ZONE)
            with open(DLL, "r+b") as f: f.write(bytes(d))
        if xst == "v2":
            for k, (va, _o, _v) in enumerate(EXE_SITES): e[foff(e, va, EXE_BASE):foff(e, va, EXE_BASE) + 7] = xsaved[k]
            e[xo:xo + XZ_END - XZ] = bytes(XZ_END - XZ)
            with open(EXE, "r+b") as f: f.write(bytes(e))
        print("reverted (%s: AoWEPACK sites/slots + AoWx.exe constants restored to their pre-apply bytes)" % st); return 0

    code, where = build(saved_sites, saved_slots)
    assert ZONE + len(code) <= ZONE_END, "zone overflow"
    xcode, xwhere = build_exe(xsaved)
    assert XZ + len(xcode) <= XZ_END, "exe zone overflow"
    print("AoWEPACK zone %d B; caves %s | AoWx.exe zone %d B" % (len(code), ", ".join("%s=%#x" % kv for kv in where.items()), len(xcode)))
    if a.dis: dis(code, where)
    d[zo:zo + ZONE_END - ZONE] = bytes(ZONE_END - ZONE); d[zo:zo + len(code)] = code
    for nm, va, o, kind, c in SITES: d[foff(d, va):foff(d, va) + len(o)] = hook_bytes(va, o, kind, where[c])
    for nm, sva, _o, c in SLOTS: struct.pack_into("<I", d, foff(d, sva), where[c])
    e[xo:xo + XZ_END - XZ] = bytes(XZ_END - XZ); e[xo:xo + len(xcode)] = xcode
    for k, (va, _o, _v) in enumerate(EXE_SITES): e[foff(e, va, EXE_BASE):foff(e, va, EXE_BASE) + 7] = xhook(va, xwhere[k])
    if not a.apply:
        print("Dry run OK%s - rerun with --apply (or --revert)." % (" (in-place upgrade v1 -> v2)" if st == "v1" else "")); return 0
    for path, sfx in ((DLL, ".bak_royal2"), (EXE, ".bak_royal2")):
        bak = path + sfx if (a.dll or a.exe) else bak_path(path, sfx)
        if not os.path.exists(bak): shutil.copy2(path, bak); print("backup ->", bak)
    with open(DLL, "r+b") as f: f.write(bytes(d))
    with open(EXE, "r+b") as f: f.write(bytes(e))
    assert open(DLL, "rb").read() == bytes(d) and open(EXE, "rb").read() == bytes(e)
    print("Written and verified (v2)"); return 0


if __name__ == "__main__":
    sys.exit(main())
