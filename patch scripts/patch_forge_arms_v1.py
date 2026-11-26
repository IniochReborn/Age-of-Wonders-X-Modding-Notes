#!/usr/bin/env python3
r"""
AoWEPACK.dll: Earth/Fire city spells (2026-10-13) - FORGE BLAST (374) and ARMS RACE (375).   v3

Both spells are clones made by patch_dual_sphere_spells_v1.py (374 = TTownQuake clone, 375 = TGoldRush clone with
[spell+0x3C] = 4 = a new city-enchantment type); this patch gives them their own behaviour.

CITY PRODUCTION (RE 2026-10-13): [city+0x50] = City.TCityProductionControl (base AoWE.TProductionControl; class ptr
0x557A6D34; [ctl+0x28] = the city, [ctl+0x14] = TProductionQueue, [ctl+0x20] = state byte (0 idle, 1 = queued /
starting next turn, 2 = in progress), [ctl+0x24] = the production STATE object: +0x08 cost, +0x10 turns LEFT
(byte), +0x1C TOTAL turns (byte), +0x1D owner player, +0x20 AI group id).  Production is a turn countdown:
ExecuteProduction (base 0x5575D118 for units/research, city override 0x557A7F0C for upgrade/fortify/... which calls
the base first) creates the state object with +0x1C = time, +0x10 = +0x1C; TProductionControl.NewTurn 0x5575DD00
does `dec byte [obj+0x10]` on the owner's turn @0x5575DD61 and completes the item at 0.  The "N turns" the player
sees is +0x10.  Vanilla ExecuteCancelProduction 0x5575CD64 = UnregisterGroupProduction, refund gold/mana
(turnsLeft x cost / total), state-object VMT+0x30 (Free), state := 1, Update.  ExecuteDeleteProduction(ctl, idx)
0x5575D368 (VMT+0x68): idx 0 -> frees queue item 0 and starts the next item (VMT+0x60) or sets state 0.

FORGE BLAST (374): TTownQuake.ExecuteTE 0x557B1DFC phase 0x32: esi = spell, ebx = target city.  The retune
patch_town_quake_v1.py already hooks 0x557B1E79 (`jmp 0x55816F00`, its cave rolls the walls and stores G_ATK) and
0x557B1CE7 in TriggerArmyDamage (`jmp 0x55816F60`, edx = ATK).  This patch CHAINS in front of both (the pass path
jumps to whatever the site pointed at before; --revert puts that back):
  * hook A (0x557B1E79): spell id 374 -> G_FORGE := 1 and CANCEL the city's current production WITHOUT refund:
    state 2 -> UnregisterGroupProduction, state-object Free, state := 1; then ExecuteDeleteProduction(0) drops
    the queue entry (the next queued item starts at full time, or the city idles = "producing merchandise");
    then jump to 0x557B1E91 = past the wall roll / SetWallType (no wall damage).  Any other spell -> G_FORGE := 0
    and jump on to the Town Quake cave.
  * hook B (0x557B1CE7, ecx = DMG 5, [esp] = the pushed damage-type word 0x80): G_FORGE set -> [esp] := 1 (Fire),
    ecx := 4 (DMG), edx := 8 (ATK) and resume at 0x557B1CEC; else jump on to the Town Quake cave (edx := G_ATK).
    Every unit in the city gets one ATK 8 / DMG 4 fire roll via the vanilla TriggerArmyDamage.
  * hook F (0x557B1C41, TriggerArmyDamage's event-log line): G_FORGE set -> the log text "Town Quake Damage"
    (RStr 64779) is replaced by the cave literal "Forge Blast Damage" (LStrAsg copies a refcount -1 constant).
  G_FORGE = BSS page slack dword 0x558FA2C0 (section vsize ends 0x558FA231; 0x558FA240/60 campaign switch,
  0x558FA2A0 caster, 0x558FA2B0 Town Quake G_ATK are taken).

ARMS RACE (375, city enchantment type 4 -> [city+0x5C] bit 0x10, set by TCity.ActivateEnchantment 0x557A9968 and
rebuilt by UpdateActiveEnchantments):
  * hook D at the City.TCityProductionControl.ExecuteProduction exit 0x557A8274 (8 B = the try/finally epilogue
    `xor eax,eax / pop edx / pop ecx / pop ecx / mov fs:[eax],edx`; esi = control, bl = result, no ebx write in the
    whole override): result true, state 2, state object with turns-left > 1 and the city has bit 0x10 ->
    `dec byte [obj+0x10]` at once.  Every production started under Arms Race (units, research, upgrade, fortify,
    AI too) shows and takes one turn less, minimum one; the displayed turns are right at queue time.  A production
    already running when the enchantment is cast is NOT shortened.  (v1 hook C at the NewTurn countdown is gone:
    it only acted on the first processed turn, so the number shown right after queueing was unchanged.)
  * hook E at City.TCityEnchantment.GetName 0x557AE35C (6 B prologue): type >= 4 would index the 4-entry name
    table 0x558E8E2C (AnsiStrings loaded at unit init) past its end -> [0x558E8E3C] = 0xFA (the JoinAmount relation
    table) -> TranslateRStr(0xFA) -> access violation whenever the enchantment is listed (Magic tab).  Type 4 now
    returns the cave literal "Arms Race"; any other type >= 4 "City Enchantment".
  GetAIUpkeepPriority -> TCity.AICityEnchantmentUpkeepPriority returns 0 for type 4; ListEnhancementsInfo uses
  sequential compares (type 4 gets no detail line).

FORGE BLAST PRESENTATION v3 (user: "a shortened Town Quake shake, then Fireball's explosion gfx/sfx"):
  TTownQuake.ExecuteTE(eax spell, edx te, ecx player, [ebp+8] step) is called by the spell TE once per token step
  (TSpellTE.Execute 0x55779948 -> 0x5577991C with step = [token+0x20]); step 0 = PlayDefaultCityEffects (VMT+0xA0:
  gfx slot 0 + sound 0 at every visible city hex) + shake start (0x557A9C64 sets a bit in [city+0x44]); steps
  1..0x31 just return "continue"; step 0x32 = shake stop (0x557A9C78), wall roll, damage.  v3:
  * hook P0 (0x557B1E1E, step 0, before the VMT+0xA0 call): id 374 -> G_SKIPGFX := 1, G_SNDIDX := 1.
  * hook G1 inside PlayDefaultCityEffects (0x557B0458 = the TImageSequenceAnimation create): G_SKIPGFX set -> no
    animation (jump to the "visible" flag set, 0x557B04F2) - the visibility/fog gating is reused unchanged.
  * hook S1 (0x557B0532, the final `xor edx,edx / call Play(list, 0)`): edx := G_SNDIDX, so step 0 plays sound 1 =
    EARTH.WAV (Town Quake's rumble) during the shake.
  * hook P1 (0x557B1E2D, right after the VMT+0xA0 call): clears both flags, replays the shake start.
  * hook PH (0x557B1E48, `cmp eax,0x32 / jne`): id 374 compares the step with FORGE_PHASE instead -> the shake is
    shortened to FORGE_PHASE steps.
  * cave A (the damage step) now first calls PlayDefaultCityEffects again with the flags clear: gfx slot 0 =
    Fireball's EXPLBIG explosion (pipeline entry 374 = _pfs_slot(127, 1)) + sound 0 = BLAST.WAV (Fireball's impact),
    then cancels the production and scorches the units as before.
  G_SKIPGFX 0x558FA2C4 / G_SNDIDX 0x558FA2C8 = BSS slack after G_FORGE.
Caves 0x55862D00.. (zero, no relocs; PIC via call/pop delta).  Backup <game>\backup\AoWEPACK.dll.bak_forgearms
(made by v1; v2 applies over the v1 state - restores v1's hook C bytes, re-reads the chain targets from the live
caves).  ⚠ patch_town_quake_v1.py will report its two sites as "OTHER" while this is applied: revert this patch
first if Town Quake ever has to be re-applied, then re-apply this.
Dry-run default; --apply; --revert; --dis.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DEFAULT_DLL = game_file("AoWEPACK.dll")
BAK_SUFFIX = ".bak_forgearms"
BASE, CODE_V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x55862D00, 0x55863000
ID_FORGE, ID_ARMS = 374, 375
FORGE_ATK, FORGE_DMG, FORGE_TYPES = 8, 4, 0x0001           # Fire
ARMS_BIT = 0x10                                              # city enchantment type 4 -> [city+0x5C] bit 4
ARMS_TYPE = 4
G_FORGE = 0x558FA2C0
G_SKIPGFX, G_SNDIDX = 0x558FA2C4, 0x558FA2C8                 # v3 (BSS slack after G_FORGE; 0x558FA2D0+ free)
FORGE_PHASE = 20                                             # v3: the shake lasts this many token steps for 374 (Town Quake: 0x32 = 50)
SHAKE_START, ANIM_CREATE, SND_PLAY = 0x557A9C64, 0x557FBBF4, 0x55702CF4
TQ_ZONE = (0x55816F00, 0x55816F80)                           # patch_town_quake_v1.py caves (chain targets)
UNREG_GROUP, LSTR_ASG = 0x5575CE68, 0x55701150               # TProductionControl.UnregisterGroupProduction, System.LStrAsg
MAP_RANDOM = 0x5577827C
# hook A: TTownQuake.ExecuteTE wall roll.  Vanilla `mov edx,0xA / call map.Random` (10 B); live = Town Quake's jmp.
HA, HA_LEN, HA_VANILLA, HA_SKIP, HA_VRESUME = 0x557B1E79, 10, bytes.fromhex("ba0a000000e8f963fcff"), 0x557B1E91, 0x557B1E83
# hook B: TriggerArmyDamage `mov edx,7` (5 B); live = Town Quake's jmp.  Resume = `mov eax,esi`.
HB, HB_LEN, HB_VANILLA, HB_RESUME = 0x557B1CE7, 5, bytes.fromhex("ba07000000"), 0x557B1CEC
# v1 hook C (NewTurn countdown, 12 B) - no longer used; restored to vanilla when found.
HC, HC_LEN, HC_ORIG = 0x5575DD58, 12, bytes.fromhex("8b4624807810007e03fe4810")
# hook D: city ExecuteProduction exit (8 B), resume = `push 0x557a829e`.
HD, HD_LEN, HD_ORIG, HD_RESUME = 0x557A8274, 8, bytes.fromhex("33c05a5959648910"), 0x557A827C
# hook E: TCityEnchantment.GetName prologue (6 B), resume = `mov edx,esi`.
HE, HE_LEN, HE_ORIG, HE_RESUME = 0x557AE35C, 6, bytes.fromhex("53568bf28bd8"), 0x557AE362
# hook F: TriggerArmyDamage log text (9 B), resume = `call LStrAsg`.
HF, HF_LEN, HF_ORIG, HF_RESUME = 0x557B1C41, 9, bytes.fromhex("8b55ec8b45f883c01c"), 0x557B1C4A
# v3 hooks (all inside TTownQuake.ExecuteTE 0x557B1DFC / TCityTargetSpell.PlayDefaultCityEffects 0x557B037C; no relocs)
HP0, HP0_LEN, HP0_ORIG, HP0_RESUME = 0x557B1E1E, 7, bytes.fromhex("8bcb8b55f88bc6"), 0x557B1E25        # mov ecx,ebx / mov edx,[ebp-8] / mov eax,esi
HP1, HP1_LEN, HP1_ORIG, HP1_RESUME = 0x557B1E2D, 7, bytes.fromhex("8bc3e8307effff"), 0x557B1E34        # mov eax,ebx / call ShakeStart
HPH, HPH_LEN, HPH_ORIG, HPH_RESUME, HPH_OTHER = 0x557B1E48, 9, bytes.fromhex("83f8320f8599000000"), 0x557B1E51, 0x557B1EEA   # cmp eax,0x32 / jne
HG1, HG1_LEN, HG1_ORIG, HG1_RESUME, HG1_SKIP = 0x557B0458, 7, bytes.fromhex("e897b704008be8"), 0x557B045F, 0x557B04F2        # call Create / mov ebp,eax
HS1, HS1_LEN, HS1_ORIG, HS1_RESUME = 0x557B0532, 7, bytes.fromhex("33d2e8bb27f5ff"), 0x557B0539        # xor edx,edx / call Play
OFF_A, OFF_B, OFF_D, OFF_E, OFF_F = 0x000, 0x0C0, 0x100, 0x140, 0x1C0
OFF_V3 = 0x210                                               # the v3 caves follow cave F (which ends at 0x20B), 16-aligned
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm_delta(src, va, reg="ebx"):
    """`call $D / pop REG / sub REG, $D` = the PIC delta idiom (REG := load delta), resolved by a two-pass assembly;
    several anchors per source are fine."""
    regs = {"eax": 0, "ecx": 1, "edx": 2, "ebx": 3}
    r = regs[reg]
    s1 = src.replace("call $D", ".byte 0xe8, 0, 0, 0, 0").replace("sub %s, $D" % reg, "sub %s, 0x7fffffff" % reg).replace("pop $R", "pop " + reg)
    b = bytearray(ks.asm(s1, va)[0])
    anchor = bytes([0xE8, 0, 0, 0, 0, 0x58 + r, 0x81, 0xE8 + r, 0xFF, 0xFF, 0xFF, 0x7F])
    n, k = 0, b.find(anchor)
    while k >= 0:
        struct.pack_into("<I", b, k + 8, va + k + 5); n += 1; k = b.find(anchor, k + len(anchor))
    assert n == src.count("call $D") and n >= 1, "delta anchor(s) not found"
    return bytes(b)


def literal(s):
    """Delphi AnsiString constant: refcount -1, length, chars, NUL.  The string pointer is at +8."""
    b = s.encode("latin-1")
    return struct.pack("<ii", -1, len(b)) + b + b"\0"


def build_a(va, chain):
    """0x557B1E79: esi = spell, ebx = city, eax = map (kept for the chain).  ecx/edx are scratch here (the skip
    target 0x557B1E91 reloads everything it uses).  v3: for 374 first PlayDefaultCityEffects(spell, player [ebp-8],
    city) = the explosion (gfx slot 0) + sound 0 at the city; edi (the TList) survives the call (callee-saved)."""
    tail = "jmp %#x" % chain if chain is not None else "mov edx, 10\n call %#x\n jmp %#x" % (MAP_RANDOM, HA_VRESUME)
    src = """
        cmp dword ptr [esi+0x10], %(id)d
        jne a_pass
        push eax
        push ebx
        mov ecx, ebx
        mov edx, [ebp-8]
        mov eax, esi
        mov ebx, [eax]
        call dword ptr [ebx+0xa0]
        pop ebx
        call $D
        pop $R
        sub ecx, $D
        mov dword ptr [ecx+%(g)#x], 1
        mov eax, [ebx+0x50]
        test eax, eax
        jz a_done
        cmp byte ptr [eax+0x20], 0
        je a_done
        push esi
        mov esi, eax
        cmp byte ptr [esi+0x20], 2
        jne a_del
        mov eax, esi
        call %(unreg)#x
        mov eax, [esi+0x24]
        test eax, eax
        jz a_state
        mov edx, [eax]
        call dword ptr [edx+0x30]
    a_state:
        mov byte ptr [esi+0x20], 1
    a_del:
        mov eax, esi
        xor edx, edx
        mov ecx, [eax]
        call dword ptr [ecx+0x68]
        pop esi
    a_done:
        pop eax
        jmp %(skip)#x
    a_pass:
        call $D
        pop $R
        sub ecx, $D
        mov dword ptr [ecx+%(g)#x], 0
        %(tail)s
    """ % {"id": ID_FORGE, "g": G_FORGE, "skip": HA_SKIP, "unreg": UNREG_GROUP, "tail": tail}
    return asm_delta(src, va, "ecx")


def build_b(va, chain):
    """0x557B1CE7: [esp] = pushed damage types, ecx = DMG (live on the pass path), edx := ATK at the resume (so edx is
    the free delta register; eax must not be used - keystone encodes `sub eax,imm32` as 2D, not 81 E8)."""
    tail = "jmp %#x" % chain if chain is not None else "mov edx, 7\n jmp %#x" % HB_RESUME
    src = """
        call $D
        pop $R
        sub edx, $D
        cmp dword ptr [edx+%(g)#x], 0
        je b_pass
        mov dword ptr [esp], %(types)d
        mov ecx, %(dmg)d
        mov edx, %(atk)d
        jmp %(resume)#x
    b_pass:
        %(tail)s
    """ % {"g": G_FORGE, "types": FORGE_TYPES, "dmg": FORGE_DMG, "atk": FORGE_ATK, "resume": HB_RESUME, "tail": tail}
    return asm_delta(src, va, "edx")


def build_d(va):
    """0x557A8274: esi = city production control, bl = ExecuteProduction result.  Replays the epilogue."""
    src = """
        test bl, bl
        jz d_out
        cmp byte ptr [esi+0x20], 2
        jne d_out
        mov eax, [esi+0x24]
        test eax, eax
        jz d_out
        cmp byte ptr [eax+0x10], 1
        jbe d_out
        mov edx, [esi+0x28]
        test edx, edx
        jz d_out
        test byte ptr [edx+0x5c], %(bit)d
        jz d_out
        dec byte ptr [eax+0x10]
    d_out:
        xor eax, eax
        pop edx
        pop ecx
        pop ecx
        mov dword ptr fs:[eax], edx
        jmp %(resume)#x
    """ % {"bit": ARMS_BIT, "resume": HD_RESUME}
    return bytes(ks.asm(src, va)[0])


def build_e(va):
    """0x557AE35C GetName(eax = self, edx = out string).  Type >= 4 -> LStrAsg(out, literal)."""
    code_len = 0x40
    lit_arms = literal("Arms Race"); lit_gen = literal("City Enchantment")
    p_arms = va + code_len + 8; p_gen = p_arms + len(lit_arms)
    src = """
        push ebx
        push esi
        mov esi, edx
        mov ebx, eax
        cmp byte ptr [ebx+0x24], %(type)d
        jb e_vanilla
        call $D
        pop $R
        sub ecx, $D
        lea edx, [ecx+%(gen)#x]
        cmp byte ptr [ebx+0x24], %(type)d
        jne e_asg
        lea edx, [ecx+%(arms)#x]
    e_asg:
        mov eax, esi
        call %(asg)#x
        pop esi
        pop ebx
        ret
    e_vanilla:
        jmp %(resume)#x
    """ % {"type": ARMS_TYPE, "gen": p_gen, "arms": p_arms, "asg": LSTR_ASG, "resume": HE_RESUME}
    code = asm_delta(src, va, "ecx")
    assert len(code) <= code_len, len(code)
    return code + bytes(code_len - len(code)) + lit_arms + lit_gen


def build_f(va):
    """0x557B1C41: edx := [ebp-0x14] (the translated log text) -> under G_FORGE the cave literal instead."""
    code_len = 0x30
    lit = literal("Forge Blast Damage"); p_lit = va + code_len + 8
    src = """
        mov edx, [ebp-0x14]
        call $D
        pop $R
        sub ecx, $D
        cmp dword ptr [ecx+%(g)#x], 0
        je f_keep
        lea edx, [ecx+%(lit)#x]
    f_keep:
        mov eax, [ebp-8]
        add eax, 0x1c
        jmp %(resume)#x
    """ % {"g": G_FORGE, "lit": p_lit, "resume": HF_RESUME}
    code = asm_delta(src, va, "ecx")
    assert len(code) <= code_len, len(code)
    return code + bytes(code_len - len(code)) + lit


def build_p0(va):
    """0x557B1E1E (step 0, esi = spell, ebx = city): 374 -> set the skip-gfx / sound-1 flags, then replay."""
    src = """
        cmp dword ptr [esi+0x10], %(id)d
        jne p0_pass
        call $D
        pop $R
        sub ecx, $D
        mov dword ptr [ecx+%(gskip)#x], 1
        mov dword ptr [ecx+%(gsnd)#x], 1
    p0_pass:
        mov ecx, ebx
        mov edx, [ebp-8]
        mov eax, esi
        jmp %(resume)#x
    """ % {"id": ID_FORGE, "gskip": G_SKIPGFX, "gsnd": G_SNDIDX, "resume": HP0_RESUME}
    return asm_delta(src, va, "ecx")


def build_p1(va):
    """0x557B1E2D (right after the VMT+0xA0 call): clear both flags, replay `mov eax,ebx / call ShakeStart`."""
    src = """
        call $D
        pop $R
        sub ecx, $D
        mov dword ptr [ecx+%(gskip)#x], 0
        mov dword ptr [ecx+%(gsnd)#x], 0
        mov eax, ebx
        call %(shake)#x
        jmp %(resume)#x
    """ % {"gskip": G_SKIPGFX, "gsnd": G_SNDIDX, "shake": SHAKE_START, "resume": HP1_RESUME}
    return asm_delta(src, va, "ecx")


def build_ph(va):
    """0x557B1E48 (eax = step, esi = spell): 374 compares with FORGE_PHASE, anything else with 0x32."""
    src = """
        cmp dword ptr [esi+0x10], %(id)d
        jne ph_v
        cmp eax, %(phase)d
        jmp ph_j
    ph_v:
        cmp eax, 0x32
    ph_j:
        jne %(other)#x
        jmp %(resume)#x
    """ % {"id": ID_FORGE, "phase": FORGE_PHASE, "other": HPH_OTHER, "resume": HPH_RESUME}
    return bytes(ks.asm(src, va)[0])


def build_g1(va):
    """0x557B0458 inside PlayDefaultCityEffects (ecx = 0, dl = 1, eax = class, ebx = city live): G_SKIPGFX ->
    no animation object, jump to the visible-flag set; else replay the Create."""
    src = """
        push ebx
        call $D
        pop ebx
        sub ebx, $D
        cmp dword ptr [ebx+%(gskip)#x], 0
        pop ebx
        jne g_skip
        call %(create)#x
        mov ebp, eax
        jmp %(resume)#x
    g_skip:
        jmp %(skip)#x
    """ % {"gskip": G_SKIPGFX, "create": ANIM_CREATE, "resume": HG1_RESUME, "skip": HG1_SKIP}
    return asm_delta(src, va, "ebx")


def build_s1(va):
    """0x557B0532 (eax = the spell's sound list): edx := G_SNDIDX (0 normally, 1 = the rumble at step 0)."""
    src = """
        push ebx
        call $D
        pop ebx
        sub ebx, $D
        mov edx, [ebx+%(gsnd)#x]
        pop ebx
        call %(play)#x
        jmp %(resume)#x
    """ % {"gsnd": G_SNDIDX, "play": SND_PLAY, "resume": HS1_RESUME}
    return asm_delta(src, va, "ebx")


def reloc_set(d):
    pe = struct.unpack_from("<I", d, 0x3C)[0]; opt = struct.unpack_from("<H", d, pe + 20)[0]; nsec = struct.unpack_from("<H", d, pe + 6)[0]
    secs = [struct.unpack_from("<IIII", d, pe + 24 + opt + 40 * k + 8) for k in range(nsec)]
    rrva, rsz = struct.unpack_from("<II", d, pe + 24 + 0x88)
    def r2f(rva):
        for vs, va, rs, ro in secs:
            if va <= rva < va + max(vs, rs): return ro + rva - va
    p, end, out = r2f(rrva), r2f(rrva) + rsz, set()
    while p < end:
        page, size = struct.unpack_from("<II", d, p)
        if size < 8: break
        for q in range(p + 8, p + size, 2):
            e = struct.unpack_from("<H", d, q)[0]
            if e >> 12 == 3: out.add(BASE + page + (e & 0xFFF))
        p += size
    return out


def jmp_target(d, site):
    b = d[site - CODE_V2F:site - CODE_V2F + 5]
    return site + 5 + struct.unpack_from("<i", b, 1)[0] if b[0] == 0xE9 else None


def chain_from_cave(d, cave):
    """Decode an applied cave of ours (v1 or v2 layout): walk its instructions until zero padding; the chain target
    is the jmp into the Town Quake zone, or None if the cave replays vanilla (calls map.Random / `mov edx,7`)."""
    import capstone
    cs = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    blob = d[cave - CODE_V2F:cave - CODE_V2F + 0x100]
    for i in cs.disasm(blob, cave):
        if i.bytes == b"\x00\x00": break
        if i.mnemonic == "jmp" and i.op_str.startswith("0x"):
            t = int(i.op_str, 16)
            if TQ_ZONE[0] <= t < TQ_ZONE[1]: return t
    return None


def write_inplace(path, data):
    with open(path, "r+b") as f:
        f.seek(0); f.write(data); f.truncate(len(data))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dll", default=DEFAULT_DLL)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    d = open(a.dll, "rb").read()
    va_a, va_b, va_d, va_e, va_f = ZONE + OFF_A, ZONE + OFF_B, ZONE + OFF_D, ZONE + OFF_E, ZONE + OFF_F
    # chain targets: what the Town Quake sites point at now (its caves), vanilla, or our own cave (v1 or v2) -> decode
    chains = {}
    for name, site, vanilla in (("A", HA, HA_VANILLA), ("B", HB, HB_VANILLA)):
        live = d[site - CODE_V2F:site - CODE_V2F + len(vanilla)]
        t = jmp_target(d, site)
        if live == vanilla: chains[name] = ("vanilla", None)
        elif t is not None and ZONE <= t < ZONE_END: chains[name] = ("ours", chain_from_cave(d, t))
        elif t is not None and TQ_ZONE[0] <= t < TQ_ZONE[1]: chains[name] = ("townquake", t)
        else: print("ABORT: unexpected bytes at site %s %#x: %s" % (name, site, live.hex())); return 1
    ca, cb_ = chains["A"][1], chains["B"][1]
    cave_a, cave_b, cave_d, cave_e, cave_f = build_a(va_a, ca), build_b(va_b, cb_), build_d(va_d), build_e(va_e), build_f(va_f)
    assert len(cave_a) <= OFF_B - OFF_A and len(cave_b) <= OFF_D - OFF_B and len(cave_d) <= OFF_E - OFF_D and len(cave_e) <= OFF_F - OFF_E, (
        len(cave_a), len(cave_b), len(cave_d), len(cave_e))
    assert OFF_F + len(cave_f) <= OFF_V3, hex(OFF_F + len(cave_f))
    # v3 caves, 16-aligned after cave F
    v3 = []; off = OFF_V3
    for lab, fn_ in (("P0", build_p0), ("P1", build_p1), ("PH", build_ph), ("G1", build_g1), ("S1", build_s1)):
        c = fn_(ZONE + off); v3.append((lab, off, c)); off = (off + len(c) + 15) & ~15
    assert off <= ZONE_END - ZONE, hex(off)
    va_p0, va_p1, va_ph, va_g1, va_s1 = [ZONE + o for _l, o, _c in v3]
    zone = bytearray(ZONE_END - ZONE)
    for off_, c in [(OFF_A, cave_a), (OFF_B, cave_b), (OFF_D, cave_d), (OFF_E, cave_e), (OFF_F, cave_f)] + [(o, c) for _l, o, c in v3]: zone[off_:off_ + len(c)] = c
    used = v3[-1][1] + len(v3[-1][2]); zone = bytes(zone[:used])
    hooks = {}
    for name, site, n, cave in (("A", HA, HA_LEN, va_a), ("B", HB, HB_LEN, va_b), ("D", HD, HD_LEN, va_d), ("E", HE, HE_LEN, va_e), ("F", HF, HF_LEN, va_f),
                                ("P0", HP0, HP0_LEN, va_p0), ("P1", HP1, HP1_LEN, va_p1), ("PH", HPH, HPH_LEN, va_ph), ("G1", HG1, HG1_LEN, va_g1), ("S1", HS1, HS1_LEN, va_s1)):
        hooks[name] = b"\xe9" + struct.pack("<i", cave - (site + 5)) + b"\x90" * (n - 5)
    rest_a = HA_VANILLA if ca is None else b"\xe9" + struct.pack("<i", ca - (HA + 5)) + b"\x90" * (HA_LEN - 5)
    rest_b = HB_VANILLA if cb_ is None else b"\xe9" + struct.pack("<i", cb_ - (HB + 5))
    def live(site, n): return d[site - CODE_V2F:site - CODE_V2F + n]
    states = {}
    V3SITES = (("P0", HP0, HP0_LEN, HP0_ORIG), ("P1", HP1, HP1_LEN, HP1_ORIG), ("PH", HPH, HPH_LEN, HPH_ORIG), ("G1", HG1, HG1_LEN, HG1_ORIG), ("S1", HS1, HS1_LEN, HS1_ORIG))
    for name, site, n, orig in (("D", HD, HD_LEN, HD_ORIG), ("E", HE, HE_LEN, HE_ORIG), ("F", HF, HF_LEN, HF_ORIG)) + V3SITES:
        states[name] = "vanilla" if live(site, n) == orig else "ours" if live(site, n) == hooks[name] else "OTHER"
    lc = live(HC, HC_LEN)
    states["C"] = "vanilla" if lc == HC_ORIG else "v1-ours" if lc[0] == 0xE9 and ZONE <= jmp_target(d, HC) < ZONE_END else "OTHER"
    zl = d[ZONE - CODE_V2F:ZONE_END - CODE_V2F]
    rl = reloc_set(d)
    sites = ((HA, HA_LEN), (HB, HB_LEN), (HC, HC_LEN), (HD, HD_LEN), (HE, HE_LEN), (HF, HF_LEN)) + tuple((st, n) for _n, st, n, _o in V3SITES)
    bad = [r for r in rl if ZONE <= r < ZONE_END or any(s <= r < s + n for s, n in sites)]
    zstate = "zero" if not any(zl) else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else "v1/other"
    print("site A %s (chain -> %s) | site B %s (chain -> %s) | site C %s | D %s | E %s | F %s | v3 P0 %s P1 %s PH %s G1 %s S1 %s | zone %s (%d B) | relocs %s | G_FORGE %#x" % (
        chains["A"][0], "vanilla replay" if ca is None else "%#x" % ca, chains["B"][0], "vanilla replay" if cb_ is None else "%#x" % cb_,
        states["C"], states["D"], states["E"], states["F"], states["P0"], states["P1"], states["PH"], states["G1"], states["S1"], zstate, len(zone), bad or "none", G_FORGE))
    if bad or "OTHER" in states.values(): print("ABORT"); return 1
    if a.dis:
        import capstone
        for off, c, lab in [(OFF_A, cave_a, "A"), (OFF_B, cave_b, "B"), (OFF_D, cave_d, "D"), (OFF_E, cave_e, "E"), (OFF_F, cave_f, "F")] + [(o, c, l) for l, o, c in v3]:
            print("--- cave", lab)
            for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(c, ZONE + off):
                if i.bytes == b"\x00\x00": break
                print("   %08X  %-16s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if a.revert:
        out = bytearray(d)
        out[HA - CODE_V2F:HA - CODE_V2F + HA_LEN] = rest_a; out[HB - CODE_V2F:HB - CODE_V2F + HB_LEN] = rest_b
        out[HC - CODE_V2F:HC - CODE_V2F + HC_LEN] = HC_ORIG
        for site, n, orig in [(HD, HD_LEN, HD_ORIG), (HE, HE_LEN, HE_ORIG), (HF, HF_LEN, HF_ORIG)] + [(st, n, o) for _n, st, n, o in V3SITES]: out[site - CODE_V2F:site - CODE_V2F + n] = orig
        out[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
        write_inplace(a.dll, bytes(out)); print("reverted (sites A/B -> %s / %s)" % ("vanilla" if ca is None else "%#x" % ca, "vanilla" if cb_ is None else "%#x" % cb_)); return 0
    if chains["A"][0] == "ours" and chains["B"][0] == "ours" and states["C"] == "vanilla" and all(states[k] == "ours" for k in ("D", "E", "F", "P0", "P1", "PH", "G1", "S1")) and zstate == "ours":
        print("already applied"); return 0
    out = bytearray(d); out[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE); out[ZONE - CODE_V2F:ZONE - CODE_V2F + len(zone)] = zone
    for name, site, n in (("A", HA, HA_LEN), ("B", HB, HB_LEN), ("D", HD, HD_LEN), ("E", HE, HE_LEN), ("F", HF, HF_LEN),
                          ("P0", HP0, HP0_LEN), ("P1", HP1, HP1_LEN), ("PH", HPH, HPH_LEN), ("G1", HG1, HG1_LEN), ("S1", HS1, HS1_LEN)):
        out[site - CODE_V2F:site - CODE_V2F + n] = hooks[name]
    out[HC - CODE_V2F:HC - CODE_V2F + HC_LEN] = HC_ORIG
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(a.dll, BAK_SUFFIX)
    if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    write_inplace(a.dll, bytes(out)); assert open(a.dll, "rb").read() == bytes(out); print("Written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
