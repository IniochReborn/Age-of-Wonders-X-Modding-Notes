#!/usr/bin/env python3
r"""
v9 2026-09-22: the four notify caves' reads of the engine global [0x558FA040] are nil-guarded (the resolve helper is left as is so the exported helper addresses 0x55816830/0x558168F0/0x55816A20 used by the exe patch do not move; it only runs during spell execution) (the EDITOR loads AoWEPACK.dll with no
engine object: adding a caster ability to a hero in AoWDevX ran cave_expandnotify -> AV read 0x140).
Evoker / Conjurer / Enchanter / Ritualist three-level abilities, part 2+3: research cost (level I) and upkeep
(level III) (AoWEPACK.dll, 2026-09-21).  Requires patch_caster_levels_v1 (part 1: ML abilities + cast cost).

Rules (user spec): level I = research cost of the ability's spell class -30 %; level III = upkeep -30 %
(Conjurer: summoned units' mana upkeep; Enchanter: unit enchantments; Ritualist: global enchantments), rounding
"nearest, halves down" = (v*7+4) div 10, upkeep with a minimum discount of 1 (1->0, 2->1); research plain.
Research uses the best level among the player's leader and heroes; upkeep uses the CASTER's level at creation
time (the value is stored in the enchantment, so it persists like vanilla).

Engine facts (see memory caster-multilevel-abilities): TSpell +0x14 cost / +0x18 research / +0x1C upkeep;
TPlayerMagicControl.ExecuteResearchSpell 0x5577D538 copies [spell+0x18] into [ctl+0x38] (0x5577D564);
TPlayer +0x80 THeroList (GetHero 0x5578A208), +0xD4 -> [+4] leader; TEnchantment.SetUpkeep 0x5577C10C
(eax=ench, edx=upkeep) is the single setter for TUnitEnchantment upkeep [+0x10] (Summoned records and unit
enchantments; [+0x1C] = ability id, 0x9B = Summoned); the summon spawn sets it at 0x557E4180 with the TE in
[ebp-4] ([TE+0x14] = caster unit id); TGlobalEnchantmentSpell.SetupEnchantment 0x557EF914 (eax=spell,
edx=hero at Activate / TSpellTE in the token path, ecx=gench) writes [gench+0x20] := [spell+0x1C];
TSpellTE.Process 0x55779948 (base, used by all unit-spell TEs) and TUnitSpell.ExecuteCA's virtual call
0x5577B419 (edx = caster strategic unit) bracket every unit-enchantment creation.

Hooks (caves 0x55816580.., BSS global G_CASTER 0x558FA2A0 = caster unit id while a spell executes):
  H1 0x55779948 TSpellTE.Process entry -> wrapper: G := [TE+0x14]; run original; G := 0.
  H2 0x5577B419 ExecuteCA virtual call -> G := [caster+0x18] around the call.
  H3 0x5577C10C TEnchantment.SetUpkeep entry -> exact TUnitEnchantment + G set -> caster hero level of
     Conjurer (Summoned) / Enchanter (other) >= 3 -> upkeep discounted (min 1).
  H4 0x557E4180 summon spawn SetUpkeep call -> same via [[ebp-4]+0x14] (summon TEs have their own Process).
  H5 0x557EF914 SetupEnchantment -> caster from edx (THero, or TSpellTE -> [+0x14]) -> Ritualist >= 3.
  H6 0x5577D564 ExecuteResearchSpell -> h_research: classify spell (VMT deltas as in cave_cost2), one -30 % step
     per leader/hero owning level >= 1 (STACKING, v2 2026-09-21).  h_research 0x55816830 / h_upkeep 0x558168F0 are
     also called by the exe spellbook (patch_spellbook_discounts_v1) for the displayed research turns / upkeep.
  v3 (2026-09-21, discount gained mid-research applies immediately, save/MP safe): [ctl+0x38] now holds the
     remaining points in RAW (undiscounted) units (H6 stores [spell+0x18] unchanged); H7 0x5577CD68 per-turn step
     lowers the raw remaining until the discounted remaining has dropped by exactly the turn's power (v6; v3-v5
     subtracted a ceil-scaled power and drifted a turn ahead); H8 0x5577CFE4 GetResearchTurnsLeft and the exe research window
     (patch_spellbook_discounts_v1) read h_remain 0x55816A20 (eax=ctl) = raw remaining with the current steps applied;
     steps = h_count over the roster for the spell in [ctl+0x34].
  H9 0x557653D9 TMultiLevelAbility.Expand tail: a THero gaining 0xAC-0xAF -> GetPlayer([unit+0x24]).[+0x54]
     TPlayerMagicControl.Changed 0x5577D248 so the magic-management tab repaints immediately (v4 2026-09-21).
  H10 0x5578A2F0 THeroList.Changed entry: when a player's hero list changes (hero died/left/joined) and a research
     is running, TPlayerMagicControl.Changed is raised for that player (owner found by scanning the players list
     [[engine]+0x140] for [p+0x80] == list) before the original notify (v5 2026-09-21).
  H11 0x557854E5 THeroUpgradeTE.Execute tail (v7 2026-09-21): the human level-up applies the chosen abilities through
     the bit-gated ability merge (mod cave 0x5580E120 -> 0x5574F518), NOT via TMultiLevelAbility.Expand, so H9 never
     fired for it; the token tail now raises TPlayerMagicControl.Changed for the hero's player while researching.
  H12 0x5578733A THero.SetPlayer (VMT+0x16C; THero.Killed calls it with -1): after the removal from the old player's
     hero list raise Changed for the old player (v8 2026-09-21) -- the list's own Changed (H10) is not on that path.
Not covered: fast (auto) combat unit enchantments, combat-spawned summons (Recall Spirits/Animate Dead).
Backup AoWEPACK.dll.bak_casterru (in <game>\backup\).  Dry-run default; --apply; --revert; --dis.
"""
import argparse, os, shutil, struct, sys
from bakpath import game_dir, game_file, bak_path
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

DEFAULT_DLL = game_file(r"AoWEPACK.dll")
BAK = ".bak_casterru"
BASE = 0x55700000
EVOKER, CONJURER, ENCHANTER, RITUALIST = 0xAC, 0xAD, 0xAE, 0xAF
G_CASTER = 0x558FA2A0          # BSS slack dword
G_ENGINE = 0x558FA040          # [.]+0xFC = map object; [map+0xC] unit list
FIND_UNIT = 0x5577E948         # (eax=map, edx=id) -> unit
IS_CLASS = 0x557010C0          # (eax=obj, edx=class) -> al
THERO_REF = 0x55711FAC         # dword -> THero classptr
TSPELLTE_REF = 0x55722F84      # dword -> TSpellTE classptr
TUNITENCH_CLS = 0x55722198     # TUnitEnchantment classptr (exact-class compare, delta-adjusted)
GET_ABILITY_LEVEL = 0x5578831C
GET_SPELL = 0x55779AC8
GET_HERO = 0x5578A208
H1, H1_ORIG, H1_RESUME = 0x55779948, bytes.fromhex("5356578bfa8bd8"), 0x5577994F
H2, H2_ORIG, H2_RESUME = 0x5577B419, bytes.fromhex("8b4424088b38ff97b4000000"), 0x5577B425
H3, H3_ORIG, H3_RESUME = 0x5577C10C, bytes.fromhex("53568bf03b5610"), 0x5577C113
H4, H4_ORIG, H4_RESUME = 0x557E4180, bytes.fromhex("8b501c8bc68b08ff5154"), 0x557E418A
H5, H5_ORIG = 0x557EF914, bytes.fromhex("8b401c894120c3")
H6, H6_ORIG, H6_RESUME = 0x5577D564, bytes.fromhex("e85fc5ffff8b4018"), 0x5577D56C
CAVE_BASE, CAVE_END = 0x55816580, 0x55816D00
GET_SPELLCTL = 0x558FA044       # [.]+0x84 = spell control for GET_SPELL
H7, H7_ORIG, H7_RESUME = 0x5577CD68, bytes.fromhex("e813020000294638"), 0x5577CD70   # turn step: call GetNetPower ; sub [esi+0x38],eax
H8, H8_ORIG, H8_RESUME = 0x5577CFE4, bytes.fromhex("8b4b388bc3e8c2ffffff"), 0x5577CFEE   # GetResearchTurnsLeft tail
H9, H9_ORIG = 0x557653D9, bytes.fromhex("8bc35d5f5e5bc3")   # TMultiLevelAbility.Expand tail (esi=ability, edi=unit, bl=result)
GET_PLAYER = 0x557544D0        # (eax=player list [[engine]+0x140], edx=idx) -> TPlayer
MAGIC_CHANGED = 0x5577D248     # TPlayerMagicControl.Changed(eax=ctl) -> repaints the magic tab
H10, H10_ORIG, H10_RESUME, H10_SKIP = 0x5578A2F0, bytes.fromhex("83780c00750a"), 0x5578A2F6, 0x5578A300   # THeroList.Changed entry
H11, H11_ORIG, H11_RESUME = 0x557854E5, bytes.fromhex("c64754008bc3"), 0x557854EB   # THeroUpgradeTE.Execute tail (edi=hero, ebx=result)
H12, H12_ORIG, H12_RESUME = 0x5578733A, bytes.fromhex("ff516c8bd38bc6"), 0x55787341   # THero.SetPlayer: remove from old player's hero list
HELPER_REMAIN_EXPECT = 0x55816A20   # h_remain, exported to the exe research window hook
HELPER_RESEARCH_EXPECT, HELPER_UPKEEP_EXPECT = 0x55816830, 0x558168F0   # exported to patch_spellbook_discounts_v1 (exe)
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, addr):
    enc, _ = ks.asm(src, addr)
    return bytes(enc)


def pic(pre, body, va):
    """pre (may not touch ebx) ; call/pop -> ebx = load delta ; body may use [ebx+ABS]"""
    p = asm(pre, va) if pre.strip() else b""
    call_at = va + len(p); nxt = call_at + 5
    p += asm(f"call {nxt:#x}", call_at)
    p += asm(f"pop ebx\nsub ebx, {nxt:#x}\n" + body, nxt)
    return p


class Layout:
    def __init__(self, base): self.cur = base; self.caves = []
    def add(self, name, fn):
        va = self.cur; blob = fn(va); self.caves.append((va, blob, name)); self.cur = (va + len(blob) + 15) & ~15; return va


def build():
    L = Layout(CAVE_BASE)
    # d30: eax=value, edx=min1 -> eax = (7v+4)/10, min discount 1 when edx!=0
    D30 = L.add("d30", lambda va: asm("""
        push ecx
        push edx
        mov ecx, eax
        imul eax, eax, 7
        add eax, 4
        xor edx, edx
        push ecx
        mov ecx, 10
        div ecx
        pop ecx
        pop edx
        test edx, edx
        jz d_ret
        cmp eax, ecx
        jne d_ret
        test eax, eax
        jz d_ret
        dec eax
    d_ret:
        pop ecx
        ret
    """, va))
    # resolve: eax=unit id -> eax=unit or 0
    RESOLVE = L.add("resolve", lambda va: pic("""
        push ebx
        push edx
        mov edx, eax
    """, f"""
        test edx, edx
        jz r_zero
        mov eax, [ebx+{G_ENGINE:#x}]
        mov eax, [eax+0xFC]
        call {FIND_UNIT:#x}
        pop edx
        pop ebx
        ret
    r_zero:
        xor eax, eax
        pop edx
        pop ebx
        ret
    """, va))
    # lvl: eax=obj, edx=id -> eax=level (0 if not a THero/TLeader)
    LVL = L.add("lvl", lambda va: pic("""
        push ebx
        push esi
        push edi
        mov esi, eax
        mov edi, edx
    """, f"""
        test esi, esi
        jz l_zero
        mov eax, esi
        mov edx, [ebx+{THERO_REF:#x}]
        call {IS_CLASS:#x}
        test al, al
        jz l_zero
        mov eax, esi
        mov edx, edi
        call {GET_ABILITY_LEVEL:#x}
        jmp l_ret
    l_zero:
        xor eax, eax
    l_ret:
        pop edi
        pop esi
        pop ebx
        ret
    """, va))
    # classify: eax=spell -> eax=ability id or 0 (clobbers ecx, edx)
    CLS = L.add("classify", lambda va: asm(f"""
        mov ecx, [eax]
        mov edx, [ecx+0x6C]
        sub edx, [ecx+0x18]
        cmp edx, 0x6B27C
        je c_conj
        cmp edx, 0x1FF4
        je c_ench
        cmp edx, 0x120
        jne c_rit
        mov edx, [ecx+0x80]
        sub edx, [ecx+0x18]
        cmp edx, 0x7E034
        jne c_none
        mov eax, {EVOKER:#x}
        ret
    c_conj:
        mov eax, {CONJURER:#x}
        ret
    c_ench:
        mov eax, {ENCHANTER:#x}
        ret
    c_rit:
        mov eax, {RITUALIST:#x}
        ret
    c_none:
        xor eax, eax
        ret
    """, va))
    # H1 wrapper around TSpellTE.Process
    def procwrap(va):
        tramp = None
        body = f"""
            push eax
            mov eax, [eax+0x14]
            mov [ebx+{G_CASTER:#x}], eax
            pop eax
            call p_tramp
            mov dword ptr [ebx+{G_CASTER:#x}], 0
            pop ebx
            ret
        p_tramp:
            push ebx
            push esi
            push edi
            mov edi, edx
            mov ebx, eax
            jmp {H1_RESUME:#x}
        """
        return pic("push ebx", body, va)
    PROC = L.add("procwrap", procwrap)
    # H2 tactical ExecuteCA virtual call
    CA = L.add("ca", lambda va: pic("push ebx", f"""
        mov eax, [edx+0x18]
        mov [ebx+{G_CASTER:#x}], eax
        pop ebx
        mov eax, [esp+8]
        mov edi, [eax]
        call [edi+0xB4]
        push eax
        push ebx
        call ca_n
    ca_n:
        pop ebx
        sub ebx, ca_n
        mov dword ptr [ebx+{G_CASTER:#x}], 0
        pop ebx
        pop eax
        jmp {H2_RESUME:#x}
    """, va))
    # H3 SetUpkeep entry
    SETUP = L.add("setupkeep", lambda va: pic("""
        push ebx
        push esi
        push edi
        mov esi, eax
        mov edi, edx
    """, f"""
        lea ecx, [ebx+{TUNITENCH_CLS:#x}]
        cmp [esi], ecx
        jne s_done
        mov eax, [ebx+{G_CASTER:#x}]
        test eax, eax
        jz s_done
        call {RESOLVE:#x}
        test eax, eax
        jz s_done
        mov edx, {ENCHANTER:#x}
        cmp dword ptr [esi+0x1C], 0x9B
        jne s_id
        mov edx, {CONJURER:#x}
    s_id:
        call {LVL:#x}
        cmp eax, 3
        jl s_done
        mov eax, edi
        mov edx, 1
        call {D30:#x}
        mov edi, eax
    s_done:
        mov eax, esi
        mov edx, edi
        pop edi
        pop esi
        pop ebx
        push ebx
        push esi
        mov esi, eax
        cmp edx, [esi+0x10]
        jmp {H3_RESUME:#x}
    """, va))
    # H4 summon spawn
    SUMM = L.add("summon", lambda va: asm(f"""
        mov edx, [eax+0x1C]
        push esi
        push edi
        mov edi, edx
        mov eax, [ebp-4]
        mov eax, [eax+0x14]
        call {RESOLVE:#x}
        test eax, eax
        jz m_done
        mov edx, {CONJURER:#x}
        call {LVL:#x}
        cmp eax, 3
        jl m_done
        mov eax, edi
        mov edx, 1
        call {D30:#x}
        mov edi, eax
    m_done:
        mov edx, edi
        pop edi
        pop esi
        mov eax, esi
        mov ecx, [eax]
        call [ecx+0x54]
        jmp {H4_RESUME:#x}
    """, va))
    # H5 global enchantment SetupEnchantment (whole function replaced)
    GENCH = L.add("gench", lambda va: pic("""
        push ebx
        push esi
        push edi
        mov esi, ecx
        mov edi, [eax+0x1C]
        mov eax, edx
    """, f"""
        test eax, eax
        jz g_done
        push eax
        mov edx, [ebx+{THERO_REF:#x}]
        call {IS_CLASS:#x}
        test al, al
        pop eax
        jnz g_hero
        push eax
        mov edx, [ebx+{TSPELLTE_REF:#x}]
        call {IS_CLASS:#x}
        test al, al
        pop eax
        jz g_done
        mov eax, [eax+0x14]
        call {RESOLVE:#x}
        test eax, eax
        jz g_done
    g_hero:
        mov edx, {RITUALIST:#x}
        call {LVL:#x}
        cmp eax, 3
        jl g_done
        mov eax, edi
        mov edx, 1
        call {D30:#x}
        mov edi, eax
    g_done:
        mov [esi+0x20], edi
        pop edi
        pop esi
        pop ebx
        ret
    """, va))
    # helper_research: eax=player, edx=spell -> eax = research cost with one -30 % per leader/hero owning the class ability (stacking)
    RESH = L.add("h_research", lambda va: asm(f"""
        push ebx
        push esi
        push edi
        push ebp
        mov ebp, esp
        sub esp, 16
        mov ebx, eax
        mov esi, edx
        mov edi, [esi+0x18]
        mov eax, esi
        call {CLS:#x}
        test eax, eax
        jz h_done
        test ebx, ebx
        jz h_done
        mov [ebp-4], eax
        mov dword ptr [ebp-8], 0
        mov eax, [ebx+0xD4]
        test eax, eax
        jz h_heroes
        mov eax, [eax+4]
        test eax, eax
        jz h_heroes
        mov edx, [ebp-4]
        call {LVL:#x}
        cmp eax, 1
        jl h_heroes
        inc dword ptr [ebp-8]
    h_heroes:
        mov eax, [ebx+0x80]
        test eax, eax
        jz h_apply
        mov edx, [eax]
        call [edx+0x54]
        mov [ebp-16], eax
        mov dword ptr [ebp-12], 0
    h_loop:
        mov eax, [ebp-12]
        cmp eax, [ebp-16]
        jge h_apply
        mov edx, eax
        mov eax, [ebx+0x80]
        call {GET_HERO:#x}
        test eax, eax
        jz h_next
        mov edx, [ebp-4]
        call {LVL:#x}
        cmp eax, 1
        jl h_next
        inc dword ptr [ebp-8]
    h_next:
        inc dword ptr [ebp-12]
        jmp h_loop
    h_apply:
        cmp dword ptr [ebp-8], 0
        jle h_done
        mov eax, edi
        xor edx, edx
        call {D30:#x}
        mov edi, eax
        dec dword ptr [ebp-8]
        jmp h_apply
    h_done:
        mov eax, edi
        mov esp, ebp
        pop ebp
        pop edi
        pop esi
        pop ebx
        ret
    """, va))
    # helper_upkeep: eax=hero, edx=spell -> eax = upkeep the hero would pay (level III of the class ability -> -30 % min 1)
    UPKH = L.add("h_upkeep", lambda va: asm(f"""
        push ebx
        push esi
        push edi
        mov ebx, eax
        mov esi, edx
        mov edi, [esi+0x1C]
        mov eax, esi
        call {CLS:#x}
        test eax, eax
        jz u_done
        cmp eax, {EVOKER:#x}
        je u_done
        mov edx, eax
        mov eax, ebx
        call {LVL:#x}
        cmp eax, 3
        jl u_done
        mov eax, edi
        mov edx, 1
        call {D30:#x}
        mov edi, eax
    u_done:
        mov eax, edi
        pop edi
        pop esi
        pop ebx
        ret
    """, va))
    assert RESH == HELPER_RESEARCH_EXPECT and UPKH == HELPER_UPKEEP_EXPECT, (hex(RESH), hex(UPKH))
    # H6 research: ExecuteResearchSpell stores the RAW cost ([ctl+0x38] = remaining points in undiscounted units;
    # the discount is applied on read (h_remain) and by scaling the per-turn power (h_scale) -> save/MP safe, no state)
    RES = L.add("research", lambda va: asm(f"""
        call {GET_SPELL:#x}
        mov eax, [eax+0x18]
        jmp {H6_RESUME:#x}
    """, va))
    # h_count: eax=player, edx=spell -> eax = number of leader/heroes owning level >= 1 of the spell's class ability
    CNT = L.add("h_count", lambda va: asm(f"""
        push ebx
        push esi
        push edi
        push ebp
        mov ebp, esp
        sub esp, 16
        mov ebx, eax
        mov esi, edx
        xor edi, edi
        test ebx, ebx
        jz k_done
        mov eax, esi
        call {CLS:#x}
        test eax, eax
        jz k_done
        mov [ebp-4], eax
        mov eax, [ebx+0xD4]
        test eax, eax
        jz k_heroes
        mov eax, [eax+4]
        test eax, eax
        jz k_heroes
        mov edx, [ebp-4]
        call {LVL:#x}
        cmp eax, 1
        jl k_heroes
        inc edi
    k_heroes:
        mov eax, [ebx+0x80]
        test eax, eax
        jz k_done
        mov edx, [eax]
        call [edx+0x54]
        mov [ebp-16], eax
        mov dword ptr [ebp-12], 0
    k_loop:
        mov eax, [ebp-12]
        cmp eax, [ebp-16]
        jge k_done
        mov edx, eax
        mov eax, [ebx+0x80]
        call {GET_HERO:#x}
        test eax, eax
        jz k_next
        mov edx, [ebp-4]
        call {LVL:#x}
        cmp eax, 1
        jl k_next
        inc edi
    k_next:
        inc dword ptr [ebp-12]
        jmp k_loop
    k_done:
        mov eax, edi
        mov esp, ebp
        pop ebp
        pop edi
        pop esi
        pop ebx
        ret
    """, va))
    # h_steps: eax=ctl -> eax = discount steps (leader/heroes owning level I) for the spell being researched, 0 if none
    STEPS = L.add("h_steps", lambda va: pic("""
        push ebx
        push esi
        push edi
        mov esi, eax
    """, f"""
        xor edi, edi
        mov edx, [esi+0x34]
        test edx, edx
        jz st_done
        mov eax, [esi+0x10]
        test eax, eax
        jz st_done
        push eax
        mov eax, [ebx+{GET_SPELLCTL:#x}]
        mov eax, [eax+0x84]
        call {GET_SPELL:#x}
        mov edx, eax
        pop eax
        test edx, edx
        jz st_done
        call {CNT:#x}
        mov edi, eax
    st_done:
        mov eax, edi
        pop edi
        pop esi
        pop ebx
        ret
    """, va))
    # h_remain: eax=ctl -> eax = remaining research points as displayed/charged (raw [ctl+0x38] with the steps applied)
    REM = L.add("h_remain", lambda va: asm(f"""
        push ecx
        push esi
        mov esi, eax
        call {STEPS:#x}
        mov ecx, eax
        mov eax, [esi+0x38]
    rm_loop:
        test ecx, ecx
        jle rm_done
        xor edx, edx
        call {D30:#x}
        dec ecx
        jmp rm_loop
    rm_done:
        pop esi
        pop ecx
        ret
    """, va))
    assert REM == HELPER_REMAIN_EXPECT, hex(REM)
    # h_scale: eax=ctl, edx=power -> eax = power scaled by (10/7)^steps (ceil), i.e. raw points removed per turn
    SCALE = L.add("h_scale", lambda va: asm(f"""
        push ecx
        push esi
        mov esi, edx
        call {STEPS:#x}
        mov ecx, eax
        mov eax, esi
    sc_loop:
        test ecx, ecx
        jle sc_done
        imul eax, eax, 10
        add eax, 6
        xor edx, edx
        push ecx
        mov ecx, 7
        div ecx
        pop ecx
        dec ecx
        jmp sc_loop
    sc_done:
        pop esi
        pop ecx
        ret
    """, va))
    # h_discn: eax=value, ecx=n -> eax = D30^n(value)
    DISCN = L.add("h_discn", lambda va: asm(f"""
        push ecx
    dn_loop:
        test ecx, ecx
        jle dn_done
        xor edx, edx
        call {D30:#x}
        dec ecx
        jmp dn_loop
    dn_done:
        pop ecx
        ret
    """, va))
    # H7 turn step: advance the RAW remaining so that the DISCOUNTED remaining drops by exactly this turn's power
    # (v6: the scaled-power estimate is tightened by searching r with D30^n(r) == D30^n(raw) - P; no rounding drift)
    TURN = L.add("turnstep", lambda va: asm(f"""
        push ebx
        push edi
        push ebp
        mov ebp, esp
        sub esp, 16
        mov eax, esi
        call 0x5577CF80
        mov [ebp-4], eax
        mov eax, esi
        call {STEPS:#x}
        mov [ebp-8], eax
        test eax, eax
        jz t_vanilla
        mov eax, [esi+0x38]
        mov ecx, [ebp-8]
        call {DISCN:#x}
        sub eax, [ebp-4]
        mov [ebp-12], eax
        cmp eax, 0
        jg t_search
        mov [esi+0x38], eax
        jmp t_done
    t_search:
        mov edx, [ebp-4]
        mov eax, esi
        call {SCALE:#x}
        mov ebx, [esi+0x38]
        sub ebx, eax
    t_down:
        cmp ebx, 0
        jle t_up
        mov eax, ebx
        mov ecx, [ebp-8]
        call {DISCN:#x}
        cmp eax, [ebp-12]
        jle t_up
        dec ebx
        jmp t_down
    t_up:
        lea eax, [ebx+1]
        cmp eax, [esi+0x38]
        jge t_store
        mov ecx, [ebp-8]
        call {DISCN:#x}
        cmp eax, [ebp-12]
        jg t_store
        inc ebx
        jmp t_up
    t_store:
        mov [esi+0x38], ebx
        jmp t_done
    t_vanilla:
        mov eax, [ebp-4]
        sub [esi+0x38], eax
    t_done:
        mov esp, ebp
        pop ebp
        pop edi
        pop ebx
        jmp {H7_RESUME:#x}
    """, va))
    # H8 GetResearchTurnsLeft: use the discounted remaining
    LEFT = L.add("turnsleft", lambda va: asm(f"""
        push edx
        mov eax, ebx
        call {REM:#x}
        mov ecx, eax
        pop edx
        mov eax, ebx
        call 0x5577CFB0
        jmp {H8_RESUME:#x}
    """, va))
    # H9 Expand tail: a hero gaining Evoker..Ritualist -> TPlayerMagicControl.Changed so the magic tab repaints now
    EXP = L.add("expandnotify", lambda va: pic("""
        push ebx
        push esi
        push edi
    """, f"""
        cmp byte ptr [esp+8], 0
        je e_done
        mov eax, [esi+0xC]
        cmp eax, {EVOKER:#x}
        jl e_done
        cmp eax, {RITUALIST:#x}
        jg e_done
        mov eax, edi
        test eax, eax
        jz e_done
        mov edx, [ebx+{THERO_REF:#x}]
        call {IS_CLASS:#x}
        test al, al
        jz e_done
        movzx edx, byte ptr [edi+0x24]
        cmp edx, 0xFF
        je e_done
        mov eax, [ebx+{G_ENGINE:#x}]
        test eax, eax
        jz e_done
        mov eax, [eax+0x140]
        call {GET_PLAYER:#x}
        test eax, eax
        jz e_done
        mov eax, [eax+0x54]
        test eax, eax
        jz e_done
        call {MAGIC_CHANGED:#x}
    e_done:
        pop edi
        pop esi
        pop ebx
        mov eax, ebx
        pop ebp
        pop edi
        pop esi
        pop ebx
        ret
    """, va))
    # H10 THeroList.Changed: a hero list that changed (hero gained/lost/died) -> its player's TPlayerMagicControl.Changed
    # (only while a research is running), then the original notify.  Player found by scanning [[engine]+0x140] for [p+0x80]==list.
    HL = L.add("herolistnotify", lambda va: pic(f"""
        cmp dword ptr [eax+0xC], 0
        jne {H10_SKIP:#x}
        push ebx
        push esi
        push edi
        push ebp
        mov esi, eax
    """, f"""
        mov edi, [ebx+{G_ENGINE:#x}]
        test edi, edi
        jz hl_out
        mov edi, [edi+0x140]
        test edi, edi
        jz hl_out
        mov ebp, [edi+8]
        mov ebp, [ebp+8]
        xor ecx, ecx
    hl_loop:
        cmp ecx, ebp
        jge hl_out
        push ecx
        mov eax, edi
        mov edx, ecx
        call {GET_PLAYER:#x}
        pop ecx
        test eax, eax
        jz hl_next
        cmp [eax+0x80], esi
        jne hl_next
        mov eax, [eax+0x54]
        test eax, eax
        jz hl_out
        cmp dword ptr [eax+0x34], 0
        je hl_out
        call {MAGIC_CHANGED:#x}
        jmp hl_out
    hl_next:
        inc ecx
        jmp hl_loop
    hl_out:
        mov eax, esi
        pop ebp
        pop edi
        pop esi
        pop ebx
        jmp {H10_RESUME:#x}
    """, va))
    # H11 THeroUpgradeTE.Execute tail: the human level-up applies abilities via the ability MERGE (mod cave 0x5580E120 ->
    # 0x5574F518), never through TMultiLevelAbility.Expand -> raise TPlayerMagicControl.Changed here for the hero's player
    UPG = L.add("upgradenotify", lambda va: pic("""
        push ebx
        push esi
        push edi
    """, f"""
        movzx edx, byte ptr [edi+0x24]
        cmp edx, 0xFF
        je g_done
        mov eax, [ebx+{G_ENGINE:#x}]
        test eax, eax
        jz g_done
        mov eax, [eax+0x140]
        call {GET_PLAYER:#x}
        test eax, eax
        jz g_done
        mov eax, [eax+0x54]
        test eax, eax
        jz g_done
        cmp dword ptr [eax+0x34], 0
        je g_done
        call {MAGIC_CHANGED:#x}
    g_done:
        pop edi
        pop esi
        pop ebx
        mov byte ptr [edi+0x54], 0
        mov eax, ebx
        jmp {H11_RESUME:#x}
    """, va))
    # H12 THero.SetPlayer 0x557872D0: after `call [ecx+0x6C]` removed the hero from the OLD player's list (death = SetPlayer(-1),
    # transfers), raise TPlayerMagicControl.Changed for the old player (esi = hero, [esi+0x24] still the old index) while researching
    SETP = L.add("setplayernotify", lambda va: pic("""
        call [ecx+0x6C]
        push ebx
        push esi
        push edi
    """, f"""
        movzx edx, byte ptr [esi+0x24]
        cmp edx, 0xFF
        je sp_done
        mov eax, [ebx+{G_ENGINE:#x}]
        test eax, eax
        jz sp_done
        mov eax, [eax+0x140]
        call {GET_PLAYER:#x}
        test eax, eax
        jz sp_done
        mov eax, [eax+0x54]
        test eax, eax
        jz sp_done
        cmp dword ptr [eax+0x34], 0
        je sp_done
        call {MAGIC_CHANGED:#x}
    sp_done:
        pop edi
        pop esi
        pop ebx
        mov edx, ebx
        mov eax, esi
        jmp {H12_RESUME:#x}
    """, va))
    assert L.cur <= CAVE_END, hex(L.cur)
    return L.caves, dict(PROC=PROC, CA=CA, SETUP=SETUP, SUMM=SUMM, GENCH=GENCH, RES=RES, TURN=TURN, LEFT=LEFT, EXP=EXP, HL=HL, UPG=UPG, SETP=SETP)


def va2off(pe_bytes, va):
    e_lfanew = struct.unpack_from("<I", pe_bytes, 0x3C)[0]
    nsec = struct.unpack_from("<H", pe_bytes, e_lfanew + 6)[0]
    opt = struct.unpack_from("<H", pe_bytes, e_lfanew + 20)[0]
    sec = e_lfanew + 24 + opt
    for i in range(nsec):
        s = sec + 40 * i
        vsz, rva, rsz, roff = struct.unpack_from("<IIII", pe_bytes, s + 8)
        if rva <= va - BASE < rva + max(vsz, rsz):
            return roff + (va - BASE - rva)
    raise ValueError(f"VA {va:#x} not in any section")


def reloc_hits(pe_bytes, ranges):
    e_lfanew = struct.unpack_from("<I", pe_bytes, 0x3C)[0]
    dd_rva, dd_sz = struct.unpack_from("<II", pe_bytes, e_lfanew + 24 + 0x88)
    if not dd_sz:
        return []
    off = va2off(pe_bytes, BASE + dd_rva); end = off + dd_sz; hits = []
    while off + 8 <= end:
        page, bsz = struct.unpack_from("<II", pe_bytes, off)
        if bsz < 8:
            break
        for i in range((bsz - 8) // 2):
            e = struct.unpack_from("<H", pe_bytes, off + 8 + 2 * i)[0]
            if e >> 12:
                va = BASE + page + (e & 0xFFF)
                if any(lo <= va < hi for lo, hi in ranges):
                    hits.append(va)
        off += bsz
    return hits


def jmp_bytes(src, dst, ln):
    return b"\xe9" + struct.pack("<i", dst - (src + 5)) + b"\x90" * (ln - 5)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dll", nargs="?", default=DEFAULT_DLL)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    dll = a.dll
    bak = bak_path(dll, BAK, create=a.apply)
    caves, T = build()
    hooks = [("H1 Process", H1, H1_ORIG, T["PROC"]), ("H2 ExecuteCA", H2, H2_ORIG, T["CA"]),
             ("H3 SetUpkeep", H3, H3_ORIG, T["SETUP"]), ("H4 summon", H4, H4_ORIG, T["SUMM"]),
             ("H5 gench", H5, H5_ORIG, T["GENCH"]), ("H6 research", H6, H6_ORIG, T["RES"]),
             ("H7 turnstep", H7, H7_ORIG, T["TURN"]), ("H8 turnsleft", H8, H8_ORIG, T["LEFT"]),
             ("H9 expand", H9, H9_ORIG, T["EXP"]), ("H10 herolist", H10, H10_ORIG, T["HL"]), ("H11 upgrade", H11, H11_ORIG, T["UPG"]), ("H12 setplayer", H12, H12_ORIG, T["SETP"])]
    if a.dis:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
        md = Cs(CS_ARCH_X86, CS_MODE_32)
        for va, blob, name in caves:
            print(f"\n; ---- {name} @{va:#x} ({len(blob)} B) ----")
            for ins in md.disasm(blob, va):
                print(f"{ins.address:08X}  {ins.mnemonic:<7} {ins.op_str}")
    if a.revert:
        if not os.path.exists(bak):
            sys.exit(f"no backup {bak}")
        shutil.copy2(bak, dll); print(f"reverted {dll} from {bak}"); return
    data = bytearray(open(dll, "rb").read())
    print(f"target: {dll}")
    states = []
    for name, va, orig, cave in hooks:
        o = va2off(data, va); cur = bytes(data[o:o + len(orig)])
        st = "vanilla" if cur == orig else "ALREADY PATCHED" if cur[0] == 0xE9 and CAVE_BASE <= va + 5 + struct.unpack_from("<i", cur, 1)[0] < CAVE_END else f"UNKNOWN {cur.hex()}"
        states.append(st); print(f"  {name:12} 0x{va:x}: {st}")
    for va, blob, name in caves:
        print(f"  cave {name:10} {va:#x}..{va + len(blob):#x} ({len(blob)} B)")
    z0, z1 = va2off(data, CAVE_BASE), va2off(data, CAVE_END)
    zone_zero = all(v == 0 for v in data[z0:z1])
    rl = reloc_hits(data, [(va, va + len(orig)) for _, va, orig, _ in hooks] + [(CAVE_BASE, CAVE_END)])
    print(f"  cave zone zero: {zone_zero}; relocs: {[hex(v) for v in rl] or 'none'}")
    if not a.apply:
        print("dry run - nothing written (use --apply)"); return
    if rl or any(s.startswith("UNKNOWN") for s in states):
        sys.exit("refusing: relocs or unexpected bytes")
    applied = any(s == "ALREADY PATCHED" for s in states)
    if not applied and not zone_zero:
        sys.exit("cave zone not empty - refusing")
    if not os.path.exists(bak):
        shutil.copy2(dll, bak); print(f"  backup -> {bak}")
    for va, blob, name in caves:
        o = va2off(data, va); data[o:o + len(blob)] = blob
    for name, va, orig, cave in hooks:
        o = va2off(data, va); data[o:o + len(orig)] = jmp_bytes(va, cave, len(orig))
    with open(dll, "r+b") as f:
        f.seek(0); f.write(data)
    print("applied." if not applied else "re-applied (caves rewritten).")


if __name__ == "__main__":
    main()
