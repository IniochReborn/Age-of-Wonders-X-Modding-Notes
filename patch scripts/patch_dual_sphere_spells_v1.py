#!/usr/bin/env python3
r"""
Dual-sphere spell CONTENT: table-driven registration of cloned spells (step 3, 2026-10-04).

Every entry in SPELLS becomes a new spell object at package init: the donor class's constructor is called
(classref cell + Create, the "clone the instance, not the class" recipe), the id / sphere / tier / mana /
research / name are poked, optional extra field pokes are applied (e.g. the summon list unit), and the object
is registered with TSpellControl.RegisterSpell.  A Spells.pfs record (key = id + 10) is cloned from the donor's
record with description / mana / research / sphere / tier (and optionally the SPELLICN image id) overridden -
once the record exists the data file wins for those fields, so re-tuning is a pfs edit (or the editor).
Combat-castable clones also get their donor's tactical-combat class byte in the relocated SpellTypes table
(AoWTCPCK.dll, VA 0x43C000 / file 0x3B400, see patch_spelltypes_relocate_v1.py).

Mechanics that differ from the donor (damage types, corpse handling, on-death triggers ...) are NOT here - they
are separate per-spell cave patches that key on the new spell id; this script only makes the spells exist,
research and cast like their donors.

Ids: 300 + 8*(pair sphere - 9) + slot, so Death/Fire (sphere 15) owns 348..355.  Pair spheres 9..22 are defined
in patch_dual_sphere_plumbing_v1.py (research/pick/name plumbing) - that patch must be applied first.

DLL hook: RegisterSummonSpells' second-to-last `call RegisterSpell` @0x557E51B8 (edx = the vanilla spell just
created, eax = ebx = TSpellControl; the last call @0x557E51CF is the Mermaid cave's).  Cave zone 0x55861200..
(CODE zero tail after the plumbing caves), PIC via call/pop delta; the table and name literals live in the cave.

Backups <game>\backup\{AoWEPACK.dll,AoWTCPCK.dll,Release\Spells.pfs}.bak_dualspells (first apply).
--revert restores all three backups.  Dry-run default; --apply; --dis.
"""
import argparse, os, shutil, struct, sys, zlib, importlib.util
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bakpath import bak_path, game_dir, game_file

GAME = game_dir()   # 2026-10-11: de-baked (AOW_GAME_DIR or parent of patch scripts)
BAK_SUFFIX = ".bak_dualspells"
BASE = 0x55700000
CODE_V2F = 0x55700C00
REGISTERSPELL = 0x55779B40
LSTRASG = 0x55701150
H_SITE, H_OLD = 0x557E51B8, bytes.fromhex("e88349f9ff")       # call RegisterSpell (direct, vanilla)
ZONE, ZONE_END = 0x55840000, 0x55848000      # 2026-10-16: MOVED here (32 KB; verified zero + reloc-free, unclaimed: Life/Air ends 0x5583A800, rotaway starts 0x5584A000) - 0x55852000-0x55854000 (8 KB) was at 7722 B before spells 212-215
OLD_ZONES = [(0x55861200, 0x55862000), (0x55852000, 0x55854000)]   # earlier homes of this zone: a hook into one counts as ours; it is zeroed on apply
TC_TABLE_FILE = 0x3B400                                        # relocated SpellTypes[0] in AoWTCPCK.dll

# donor classes: (classref cell, Create) - the cell is the operand of the `mov eax,[cell]` right before the
# vanilla `call X.Create` in the Register* loops (each cell holds cell+0x40, the Delphi class pointer).
# ⚠ NOT the exported class symbol and NOT "VMT-4": using those GPFs at package init (Runtime error 216) -
# learned the hard way 2026-10-04.
DONOR = {
    "TSummonMermaid":    (0x557E3E94, 0x557E4FD0),   # site 0x557E51C6
    "TSummonFireSprite": (0x557E3C48, 0x557E4E50),   # site 0x557E5198
    "TGreatHail":        (0x557F5504, 0x557F8F18),   # site 0x557FA6F4
    "THighPrayer":       (0x557F458C, 0x557F7EFC),   # site 0x557FA5C9
    "TVaporize":         (0x557F5A5C, 0x557F9364),   # site 0x557FA767
    "TWindsOfFury":      (0x557F62A0, 0x557F9E00),   # site 0x557FA808 (id 0x7E Winds of Fury, class 0x2F: ATK 8 DMG 3 Physical, 1 shot, range 0xFF; CreateCA 0x557F9EB8 +2 ATK vs Flying) - Banshee Gale 344 (patch_banshee_v1.py)
    "TAnimateDead":      (0x557F68CC, 0x557FA3BC),   # site 0x557FA7DA
    "TMindDecay":        (0x557F49A8, 0x557F8520),   # site 0x557FA625
    "TFireBall":         (0x557F5618, 0x557F8FD4),   # site 0x557FA70B
    "TWaterMastery":     (0x557EE0F8, 0x557F0970),   # site 0x557F3ACE
    "TEarthMastery":     (0x557EF444, 0x557F34B0),   # site 0x557F3AB0 (id 0x40 Earth Mastery; pfs key 74) - Golden Age 302 (2026-10-14)
    "TFireMastery":      (0x557EF1E8, 0x557F2E5C),   # site 0x557F3A99 (id 0x3F Fire Mastery; pfs key 73) - Steam Power 406 (2026-10-14)
    "TEnchantWeapon":    (0x557E575C, 0x557E6D98),   # site 0x557E8CEF
    "TAnarchy":          (0x557B0048, 0x557B1EF8),   # site 0x557B262C
    "TRejuvenate":       (0x5579D4D4, 0x5579F560),   # site 0x557A2473 (Scorch Terrain = vanilla Rejuvenate 0x29; per-spell terrain rules in patch_terrain_spells_v1.py)
    "TRecallSpirit":     (0x557F66D0, 0x557FA19C),   # site 0x557FA7F1 (id 0x81 Recall Spirit: vmtSelfPtr 0x557F66D0 / Create 0x557FA19C; class 0x27 corpse spell, CreateCA 0x557FA29C -> TRecallSpiritCA [+0x18] = spell id) - Miracle 209 (patch_miracle_v1.py + patch_tc_miracle_v1.py)
    "TDeathRay":         (0x557F46A0, 0x557F82B0),   # site 0x557FA5E0 (id 0x67 Death Ray: ATK 9 DMG 3 Death 1 shot range 0xC)
    "TRemedy":           (0x557E5B0C, 0x557E72B8),   # site 0x557E8D34 (id 0x23 Remedy: heal +5 + cure; [+0x38] range 12, -1 = unlimited)
    # Earth/Fire (2026-10-13, city-spell RE by a fork): CitySpells registration loop 0x557B262C..
    "TTownQuake":        (0x557AFF1C, 0x557B1B54),   # site 0x557B2643 (id 0x47 Town Quake; [+0x38]=2 enemy cities; phases in ExecuteTE 0x557B1DFC)
    "TGoldRush":         (0x557AFB90, 0x557B185C),   # site 0x557B2688 (id 0x35 Gold Rush; [+0x3C]=1 enchantment type, [+0x38] own city; pfs tag 0xE upkeep)
    "TDarkGift":         (0x557E675C, 0x557E83B0),   # site 0x557E8E2A (id 0x4D Dark Gift: grants ability 0xA9 TDarkGiftEnchantment in ExecuteSpell; range 0xC; [+0x3C]=3 duration mode)
    "TSlow":             (0x557F4DC0, 0x557F8890),   # site 0x557FA66A (id 0x6E Slow: ATK 9 DMG 0, 1 shot, range 0xC; TSlowCA grants status ability 0x84 - constant, not pokeable)
    "TOoze":             (0x557F5D94, 0x557F9590),   # site 0x557FA7AC (id 0x7C Ooze: hail class 0x0A, 19 strikes, TDamageCA no-op; each landing places a TCOozeHS mud overlay - Oil Spring v3 clones that with an oil HS, patch_oilspring_v1.py)
    # Fire/Air (2026-10-14, fork RE)
    "TGreatHail":        (0x557F5504, 0x557F8F18),   # site 0x557FA6F4 (id 0x74 Great Hail: hail class 0x0A; 3/8/0x180/3 shots/range 0xC/2 targets; the 0x31006 landing msg damages units, walls and structures)
    "THighPrayer":       (0x557F458C, 0x557F7EFC),   # site 0x557FA5C9 (id 0x66 High Prayer: class 37 no-target all-friendly; one TTacticalCombatHighPrayerCA per friendly unit, Execute 0x557F7E98)
    "TSwarm":            (0x557F53F8, 0x557F8E5C),   # site 0x557FA6DD (id 0x73 Swarm: class 14, 30 strikes on the target unit; ATK 7 DMG 1 types 0x81 fire|physical, range 0xC, fast-combat 5; CreateCA = base TCombatSpell.CreateCA -> TCombatSpellCA rolls the damage in Setup into [ca+0x10])
    # Earth/Water (2026-10-15, fork RE)
    "TWaterWalking":     (0x557E6274, 0x557E7CD8),   # site 0x557E8DA2 (id 0x2A Water Walking; grants 0xA4 by immediate; [+0x3C]=6 duration mode; patch_swampwalk_v1.py re-implements ExecuteSpell/ValidTarget for 382)
    "TAirMastery":       (0x557EDEA0, 0x557F0458),   # site 0x557F3A5B (id 0x3C Air Mastery; pfs key 70) - Overgrowth 383 (patch_overgrowth_v1.py)
    "TDeathMastery":     (0x557EEF90, 0x557F27A8),   # site 0x557F3A89 (id 0x3E Death Mastery; pfs key 72) - Blessed Dew 326 (patch_blesseddew_v1.py)
    "TLifeMastery":      (0x557EED34, 0x557F2158),   # site 0x557F3A6B (id 0x3D Life Mastery; pfs key 71) - Bountiful Harvest 325 (patch_harvest_v1.py)
    "TColdBreath":       (0x557F4BD8, 0x557F8758),   # site 0x557FA653 (id 0x6C Cold Breath: class 5 breath, ATK 8 DMG 4 Cold 0x2, 1 shot, range 4; pfs key 118) - Holy Water 324
    "TDispelMagic":      (0x557E53B4, 0x557E8940),   # Mimic 233's chassis = Dispel Magic (id 8, pfs 18, SpellTypes 7); patch_tc_mimic_v1.py
    "TTremors":          (0x557F50C0, 0x557F8C74),   # site 0x557FA698 (id 0x70 Tremors: class 29 all-units camera-shake spell; Create ATK 3 DMG 8 types 0x180, 1 shot, range 0xFF) - Flash Flood 223 (patch_tc_flashflood_v1.py)
    "TCallFlames":       (0x557F51D0, 0x557F8CE4),   # Void Step's chassis (build_warp_self_stage1) - Misty Step 396 (patch_mistystep_v1.py)
}

# ---- the content table ------------------------------------------------------------------------------
# pokes: list of (offset-from-spell, width, value) applied after Create; "summon unit" is the TIntegerList at
# [spell+0x38], items at [list+4], entry 0.  tc_type = SpellTypes byte (None = not combat-castable, stays 0).
# TCombatSpell parameter block (set in each donor's Create, NOT in Spells.pfs): +0x34 attack, +0x35 damage,
# +0x36 word damage-type mask (1 Fire 2 Cold 4 Lightning 8 Magic 0x10 Poison 0x20 Death 0x40 Holy 0x80 Physical
# 0x100 Wall), +0x38 shots, +0x39 range, +0x3A fast-combat targets, +0x3B target side, +0x3C roll vs RES.
# icon: SPELLICN.ILB image id (build_dual_sphere_icons_v1.py appends ids = spell ids).  sfx: tag 0xB sound list
# (see spellgfx.py: "path" = single, [..] = list; the donor's slot roles are kept: Great Hail = [loop, [impact]],
# High Prayer = [cast]).  gfx: {slot: spellgfx.seq_entry(...)} replaces effect slots of the donor's tag 0xC
# TImageSequenceList (Great Hail: 0 = falling projectile BALLS 15-22, 1 = impact BOLTS 120-129, 2 = splash MISC
# 40-45; High Prayer: 0 = PARTICLE sparkles 12-14, 1 = MAGIC 89-109 aura).  Frame ids are ILB IMAGE IDS; xs/ys
# anchor the sprite (vanilla: -half width, -height+a bit).
import spellgfx as G
SPELLS = [
    dict(id=350, name="Blood Pact", sphere=15, tier=2, mana=4, research=90,          # renamed from "Bloodbath" 2026-10-13 (user)
         donor="THighPrayer", pfs_donor=112, tc_type=0x25, icon=350,
         desc="Whips all friendly units into a Bloodlust during combat.",
         sfx=["SFX\\ZSP\\DUALDF_BLOODBATH.WAV"],                                 # build_dual_sphere_sfx_v1.py mix
         # build_dual_sphere_fx_v1.py: 0-5 deep-red sparkles, 10-39 descending shadow sword + blood gush/pool.
         # f18 = extra ticks per frame (TImageSequence +0x18: total ticks = frames*(f18+1)); the slot-1 effect is
         # spawned at tick 0 for this spell by patch_tc_bloodbath_aura_v1.py (vanilla: tick 100, after the sparkles)
         gfx={0: G.seq_entry("EFFECTS\\DUALDF.ILB", [0, 1, 2, 3, 4, 5], -9, -11, f20=3),
              1: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(100, 200)), -32, -130, f20=5)}),   # 100 frames, 1 tick each
    dict(id=351, name="Summon Hell Hound", sphere=15, tier=1,   # 10/23 user: Level 1 (was 2 - locked out the later Death/Fire research) + research 90 -> 50; editor set Spells.pfs rec 361 to match
         mana=5, research=50, upkeep=2,
         donor="TSummonMermaid", pfs_donor=211, tc_type=0, icon=351,
         desc="Summons a Hell Hound, a fiery beast from the depths.",
         summon_unit=202),
    dict(id=354, name="Hellfire", sphere=15, tier=4, mana=5, research=300,
         donor="TGreatHail", pfs_donor=126, tc_type=0x0A, icon=354,
         desc="Rains hellfire upon the target area, searing units and walls with death and flame.",
         pokes=[(0x36, 2, 0x01A1)],             # Great Hail 0x0180 (Physical+Wall) -> + Death + Fire
         # build_dual_sphere_sfx_v1.py mixes: hail WIND + ZigDSpirit wail (loop), A_FORCE1 crunch + WraithDeath (hit)
         sfx=["SFX\\ZSP\\DUALDF_HFLOOP.WAV", ["SFX\\ZSP\\DUALDF_HFHIT1.WAV", "SFX\\ZSP\\DUALDF_HFHIT2.WAV", "SFX\\ZSP\\DUALDF_HFHIT3.WAV"]],
         # build_dual_sphere_fx_v1.py: 40-47 charred boulders with flame tails, 50-57 small fiery impact flash;
         # FIRESM2 0-5 = small flames licking the hex after the hit (hail: BALLS 15-22 / BOLTS 120-129 / MISC 40-45)
         # slot 3 = hell portal, read by the kind-0x26 effect that patch_tc_hellfire_portal_v1.py spawns 300 px above
         # the target hex (slot 3 is unused by the hail code); 40 frames x (f18+1 = 3) ticks = 120 ticks
         # hail-class slots (TfxHS.Show[0x0A]): 0 = projectile at the path head, 1 = TRAIL drawn at the ~9 previous
         # path points (frame 0 nearest), 2 = impact on the hex.  Slot 3 = the portal (patch_tc_hellfire_portal_v1.py)
         gfx={0: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(40, 48)), -32, -33, f20=6),      # charred stone + flame cap
              1: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(80, 90)), -32, -33, f20=4),      # flame trail big -> ember
              2: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(50, 58)), -32, -33, f20=4),      # impact flash
              3: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(60, 110)), 0, 0, f20=4, f18=3),        # portal DRIVER (invisible, 50 x 4 = 200 ticks: v20 strikes wait 50 ticks for the portal, rain ends ~185; was 37 x 4 = 148)
              4: G.seq_entry("EFFECTS\\DUALDF.ILB", [200, 201, 202], -9, -9, f20=0)}),                 # whirl sparkles (= PARTICLE 15-17)
]
MAX_POKES = 6                # 2026-10-12: Repent needs ATK/DMG/types (was 2); 2026-10-14: Implosion pokes 6 fields (entry = 28 + 12*6 = 100 B; zone 0x55861200-0x55862000 holds it)


VANILLA_PFS = os.path.join(HERE, "..", "reference files", "AoW 1.36", "Release", "Spells.pfs")


def _pfs_slot(key, slot, path=None):
    """An effect sequence copied from a Spells.pfs record (tag 0xC slot) - the live file, or VANILLA_PFS."""
    p = open(path or os.path.join(GAME, "Release", "Spells.pfs"), "rb").read()
    pairs, kb = G.pfs_tab(p, 7); idx = {t: kb + o for t, o in pairs}
    nxt = min([v for v in idx.values() if v > idx[key]] + [len(p) - 4])
    return G.seq_parse(bytes(G.pfs_fields(p, idx[key], nxt)[0xC]))[slot]


def _emblem_slot(key, slot, base_id, path=None):
    """2026-10-16: a vanilla unit-enchantment cast effect (twinkle chain + the ENCHANT.ILB icon emblem) with its EMBLEM
    swapped for ours: every ENCHANT.ILB element is redirected to EFFECTS\DUALDF.ILB and its frames remapped from the
    donor's 5 strengths (e.g. Water Walking 45..49) to base_id..base_id+4, keeping the donor's fade pattern/timing."""
    import copy
    e = copy.deepcopy(_pfs_slot(key, slot, path)); x = e
    while x:
        if "ENCHANT.ILB" in x["name"].upper():
            lo = min(f for f in x["frames"] if f != 999)
            x["name"] = "EFFECTS\DUALDF.ILB"; x["frames"] = [999 if f == 999 else base_id + min(4, f - lo) for f in x["frames"]]
        x = x.get("chain")
    return e


# 2026-10-12: the vanilla Rejuvenate re-created (the original id 0x29 lives on as "Scorch Terrain") + its Death twin.
# Both are TRejuvenate clones; patch_terrain_spells_v1.py gives the shared class per-spell source/target terrain rules
# (204: desert/steppe/ice/wasteland -> grass; 205: grass/desert/snow/steppe/ice/dirt -> wasteland) and makes the
# execute use each spell's OWN pfs sound/gfx.  Icons 204/205 = build_dual_sphere_icons_v1.py (Life / Death clouds).
def _emblem_slot_seq(key, slot, ids, f18=None, path=None):
    """2026-10-18 (Lucky v3): like _emblem_slot, but the ENCHANT.ILB emblem element gets an explicit DualDF id TIMELINE
    (e.g. an eased ramp through 12 strengths) and optionally its own ticks-per-frame (f18); the twinkle chain is untouched."""
    import copy
    e = copy.deepcopy(_pfs_slot(key, slot, path)); x = e
    while x:
        if "ENCHANT.ILB" in x["name"].upper():
            x["name"] = "EFFECTS\\DUALDF.ILB"; x["frames"] = list(ids)
            if f18 is not None: x["f18"] = f18
        x = x.get("chain")
    return e

SPELLS += [
    dict(id=204, name="Rejuvenate", sphere=1, tier=1, mana=6, research=30,   # cost 6 (user spec 2026-10-16)
         donor="TRejuvenate", pfs_donor=51, tc_type=None, icon=204,         # 204 = the vanilla icon 88 copied from the 1.36 ILB (live 88 is now Mermaid's)
         desc="Rejuvenates the land in the target area into fertile grassland.",
         sfx=["SFX\ATTACK\ENCHP02.WAV"],                                    # vanilla Rejuvenate sound
         gfx={0: _pfs_slot(51, 0, VANILLA_PFS)}),                              # vanilla green twinkles (TWINKGR 30-38; Scorch uses the re-coloured 220-228)
    dict(id=205, name="Wither", sphere=2, tier=1, mana=6, research=40,
         donor="TRejuvenate", pfs_donor=51, tc_type=None, icon=205,
         desc="Withers the land in the target area, leaving barren wasteland.",
         sfx=["SFX\\ZSP\\DUALDE_WITHER.WAV"],   # 10/16: own creepy mix (was vanilla ENCHN01)
         gfx={0: _pfs_slot(140, 0)}),                                            # Animate Dead's dark particles; smaller area + preview = patch_terrain_spells_v1.py (the +0x39 poke tried on 10/12 was the wrong object)
    # 2026-10-12: two tier-2 combat spells.  Engine behaviour = patch_repent_harvest_v1.py (AoWEPACK) + patch_tc_repent_harvest_v1.py
    # (TCPCK); Harvest's 7-hex preview/strike entry = patch_tc_spell_alias_v1.py (207 -> 0x82).
    dict(id=206, name="Repent", sphere=1, tier=2, mana=4, research=90,
         donor="TDeathRay", pfs_donor=113, tc_type=0x0A, icon=206,                  # v2: hail class = sky beam (1 strike, vertical, HN 0: patch_tc_repent_harvest_v1.py)
         desc="Smites a single unit with holy judgement from afar, ignoring all obstructions. Base damage 1; 2 against neutral, 3 against evil or pure neutral, 4 against pure evil; +1/+2/+3 if the target bears a silver, gold or legendary medal.",
         pokes=[(0x34, 1, 7), (0x35, 1, 1), (0x36, 2, 0x0040)],                   # ATK 7, DMG 1 (per-target in the cave), Holy
         # v3: static UFO beam.  Slot 0 = the strike's (invisible) falling head; slot 1 = the kind-0x26 DRIVER's
         # animation (sparkles -> beam grows -> hold -> fade, 44 frames x (f18+1 = 3) ticks, frame top-left at the
         # effect XYZ = hex centre -40/-280, see patch_tc_repent_harvest_v1.py); slot 2 = landing flash at the hex.
         # Sounds 0 = cast (caster site), 1 = landing (kind-0x0A NewFrame).
         gfx={0: G.seq_entry("EFFECTS\\DUALDF.ILB", [340], -2, -2, f20=0),
              1: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(400, 439)), 0, 0, f20=3, f18=2),    # v5: 14 motes + 14 grow + 3 hold + 8 fade
              2: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(350, 356)), -32, -40, f20=2)},
         sfx=["SFX\\ZSP\\DUALDF_REPENT.WAV", ["SFX\\ZSP\\DUALDF_REPHIT.WAV"]]),   # hit = custom holy smite mix (2026-10-13 v2);   # v2: choir -> beam hum (mix), hit = plain vanilla Turn Undead;  # 2026-10-13 custom mixes (build_dual_sphere_sfx_v1.py): 0 = cast build-up, 1 = landing.  Entries after the first MUST be variant sub-lists (every vanilla 2-sound spell + hellfire do this; a plain 2nd entry raised inside Play)
    dict(id=207, name="Harvest Souls", sphere=2, tier=3, mana=4, research=150,   # 10/16: tier 2 -> 3, research 90 -> 150 (user)
         donor="TAnimateDead", pfs_donor=140, tc_type=0x27, icon=207,
         desc="Consumes the corpses in the target area. Each soul harvested restores 5 casting points to the caster.",
         gfx={0: G.seq_entry("EFFECTS\\DUALDF.ILB", [334, 335, 336, 335], -17, -18, f20=2),       # v4: 2x (38 px) Animate Dead's twinkle (PARTICLE 15-17, same anchor/timing) tinted purple; the corpse FX spawns 18 kind-0x1F sparkles of slot 0 + our corpse->caster motes
              1: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(460, 481)), -38, -46, f20=2, f18=1)},  # v4: purple summon dome (MAGIC 89-109 tinted) at the CASTER when the corpses pop (kind-0x26 effect, TCPCK switch cave)
         sfx=["SFX\\ZSP\\DUALDF_HARVEST.WAV", ["SFX\\ZSP\\DUALDF_HARVPOP.WAV"]]),   # 2026-10-13 custom mixes (build_dual_sphere_sfx_v1.py);   # 1 = the pop (played by the switch cave) - a variant SUB-LIST like every vanilla 2nd sound (the plain entry = "Error during Token Execute", 10/13)
    dict(id=208, name="Sanctify", sphere=1, tier=3, mana=4, research=120,
         donor="TGreatHail", pfs_donor=126, tc_type=0x0A, icon=208,              # hail class, 7 strikes (patch_rotaway STRIKES[208]); zone = patch_tc_sanctify_field_v1.py
         pokes=[(0x34, 1, 0), (0x35, 1, 0), (0x36, 2, 0), (0x39, 1, 0x0C), (0x3B, 1, 3)],   # ATK 0 / DMG 0 / no damage type / range 12 (long) / own units + enemies + empty hexes
         desc="Consecrates the target hex and every hex around it for 3 turns. Good units standing there are Fearless and fight as Holy Champions (Holy Champion II if pure good); evil and pure neutral units there are Panicked, and pure evil units also suffer Vertigo.",
         gfx={0: G.seq_entry("EFFECTS\\DUALDF.ILB", [340], -2, -2, f20=0),                       # nothing visibly falls
              1: G.seq_entry("EFFECTS\\DUALDF.ILB", [340], -2, -2, f20=0),
              2: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(2885, 2901)), -51, -40, f20=2, f18=1),   # 10/16: x -48 -> -51 (user: centre better)   # per-hex landing: shaft of light + spreading ring
              3: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(2901, 2913)), -19, 0, f20=2, f18=2)},   # 10/16 r6: -16 -> -19   # 10/16: x -12 -> -16 (centre on the hex = HXtoHP+16, LAND_CENTRE); the consecrated-hex loop (drawn by the field HS's Show)
         sfx=["SFX\\ZSP\\DUALDF_SANCTIFY.WAV", ["SFX\\ZSP\\DUALDF_SANCTHIT.WAV"]]),
    dict(id=209, name="Miracle", sphere=1, tier=4, mana=7, research=250,
         donor="TRecallSpirit", pfs_donor=139, tc_type=0x27, icon=209,     # pfs 139 = Recall Spirit's record; SpellTypes 0x27 corpse spell
         desc="A fallen friendly unit or hero rises again where it fell, with 30 to 100% of its hit points and a random share of its movement, until the end of the battle.",
         gfx={0: G.seq_entry("EFFECTS\\DUALDF.ILB", [2960, 2961, 2962, 2963], -17, -18, f20=2)},   # v2: gold CROSS shrinking over 4 frames (was a gold PARTICLE twinkle) at the corpse (Harvest's slot-0 anchor/timing)
         sfx=["SFX\\ZSP\\DUALLI_MIRACLE.WAV"]),
    dict(id=210, name="Undying", sphere=2, tier=2, mana=4, research=80, upkeep=2,
         donor="TWaterWalking", pfs_donor=52, tc_type=7, icon=210,        # patch_undying_v1.py: ability 0xC1 implies Death Immunity 0x0B + Regeneration 0x31
         desc="Enchants a unit with unnatural endurance: it becomes immune to death damage and regenerates its wounds.",
         gfx={0: _emblem_slot(47, 0, 2964, VANILLA_PFS)},   # 10/16 r2: UNHOLY CHAMPION's cast chain (pfs 47, EUHoly 20-24) with our emblem - Death look, not Water Walking's blue                   # Water Walking's twinkle chain with OUR emblem (the icon glowing, DualDF 2964-2968)
         sfx=["SFX\\ZSP\\DUALDE_UNDYING.WAV"]),
    dict(id=211, name="Call of the Dead", sphere=2, tier=4, mana=7, research=250,
         donor="TAnimateDead", pfs_donor=140, tc_type=0x27, icon=211,    # patch_callofdead_v1.py + patch_tc_callofdead_v1.py: EVERY corpse on the field rises as an Undead Draugr (unit 201)
         desc="The dead answer your call: every corpse on the battlefield, friend or foe, rises as an Undead Draugr under your command.",
         gfx={0: G.seq_entry("EFFECTS\\DUALDF.ILB", [3000, 3001, 3002, 3003], -17, -18, f20=2),   # v2: one big SKULL shrinking (slot 0 unused for 211 since the spiral driver)
              1: G.seq_entry("EFFECTS\DUALDF.ILB", list(range(3004, 3034)), -48, -48, f20=3, f18=1)},   # 10/16: five skulls spiralling in, one per corpse (patch_tc_callofdead_spiral_v1.py)   # Animate Dead's corpse twinkle (2x, same anchor/timing) in grave-green
         sfx=["SFX\\ZSP\\DUALDE_CALLDEAD.WAV"]),
    dict(id=212, name="Gust", sphere=4, tier=1, mana=3, research=50,
         donor="TColdBreath", pfs_donor=118, tc_type=5, icon=212,          # class 5 breath cone (as Holy Water 324); patch_tc_gust_v1.py: pushback
         pokes=[(0x34, 1, 8), (0x35, 1, 3), (0x36, 2, 0x80), (0x3A, 1, 3)], # ATK 8 / DMG 3 / Physical; fast-combat 3 targets; range 4 inherited
         desc="A violent gust bursts from the caster in a cone: every unit caught in it is struck (attack 8, damage 3, physical) and blown one hex away from the caster, if there is room to land.",
         gfx={0: G.seq_entry("EFFECTS\\DUALDF.ILB", [340], -2, -2, f20=0),                     # v3: the breath strikes draw NOTHING (blank, like Sanctify's slot 0)
              1: G.seq_entry("EFFECTS\\DUALDF.ILB", [3042, 3043, 3044, 3043], -9, -9, f20=1)},   # v6: back to v3's pale forward spray
         sfx=["SFX\\ZSP\\DUALAI_GUST.WAV"]),
    dict(id=213, name="Crosswind", sphere=4, tier=2, mana=5, research=80,
         donor="THighPrayer", pfs_donor=112, tc_type=0x25, icon=213,     # patch_crosswind_v1.py: enemies get 0xC2 'Crosswind' (-2 ranged ATK, 3 rounds)
         desc="Fierce crosswinds sweep the battlefield: for 3 turns every enemy unit's ranged attacks suffer -2 attack.",
         gfx={0: G.seq_entry("EFFECTS\\DUALDF.ILB", [3600, 3601, 3602, 3601], -5, -5, f20=1),   # v6: the wash particles (small WoF orbs; kind 0x1F tagged 213)
              1: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(3103, 3127)), -41, -61, f20=2, f18=1),
              2: G.seq_entry("EFFECTS\\DUALDF.ILB", [3300, 3300, 3303, 3303, 3306, 3306, 3309, 3309, 3312, 3312, 3312, 3312, 3312, 3312, 3312, 3312, 3312, 3312, 3312, 3312, 3312, 3312, 3312, 3309, 3309, 3309, 3306, 3306, 3306, 3303, 3303, 3303, 3300, 3300, 3300, 3300], -100, -53, f18=2, f20=2),   # v7 cloud 0: 36 frames x 3 ticks = 108: fade in 10, hold 12, fade OUT 14 (smoother)
              3: G.seq_entry("EFFECTS\\DUALDF.ILB", [3301, 3301, 3304, 3304, 3307, 3307, 3310, 3310, 3313, 3313, 3313, 3313, 3313, 3313, 3313, 3313, 3313, 3313, 3313, 3313, 3313, 3313, 3313, 3310, 3310, 3310, 3307, 3307, 3307, 3304, 3304, 3304, 3301, 3301, 3301, 3301], -95, -53, f18=2, f20=2),   # v7 cloud 1
              4: G.seq_entry("EFFECTS\\DUALDF.ILB", [3302, 3302, 3305, 3305, 3308, 3308, 3311, 3311, 3314, 3314, 3314, 3314, 3314, 3314, 3314, 3314, 3314, 3314, 3314, 3314, 3314, 3314, 3314, 3311, 3311, 3311, 3308, 3308, 3308, 3305, 3305, 3305, 3302, 3302, 3302, 3302], -97, -56, f18=2, f20=2),   # v7 cloud 2
              5: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(3390, 3450)), -32, -62, f18=1, f20=60)},   # v4 per-enemy swirl: one 60-frame pass x 2 ticks = 120 ticks (its end = the 0xC2 grant CA)
         sfx=["SFX\\ZSP\\DUALAI_CROSSWIND.WAV"]),
    # NOTE (213): High Prayer's visuals play on the caster's OWN units (who the CAs are for); the effect lands on the enemies.
    dict(id=214, name="Suspend", sphere=4, tier=3, mana=7, research=140,
         donor="TRemedy", pfs_donor=45, tc_type=7, icon=214,          # TRemedy range 12 = long; patch_suspend_v1.py: ability 0xC3 = Flying + cannot move, 3 turns
         pokes=[(0x22, 1, 0), (0x0C, 1, 2)],                          # 10/16: (0x3B,1,3) dropped - on a TUnitSpell +0x38..0x3B is the RANGE dword (side = patch_suspend_fix_v1 GCI)            # combat spell + combat-only context (as Second Wind) + target side mask 3 = own units AND enemies
         desc="Howling winds lift the target unit into the air: for 3 turns it counts as flying but cannot move. Against an enemy it strikes with attack 7 (resisted by the target's resistance); on a friendly unit it never fails.",
         gfx={0: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(3714, 3810)), -48, -104, f20=1, f18=0)},   # rising wind helix around the unit (96x96)
         sfx=["SFX\\ZSP\\DUALAI_SUSPEND.WAV"]),
    dict(id=215, name="Static Shield", sphere=4, tier=4, mana=6, research=250,
         donor="TRemedy", pfs_donor=45, tc_type=7, icon=215,           # patch_staticshield_v1.py: ability 0xC4 implies Lightning Immunity 0x09 + Lightning Strike 0x10 until the battle ends
         pokes=[(0x22, 1, 0), (0x0C, 1, 2), (0x38, 4, 0xFFFFFFFF)],     # COMBAT spell type + combat-only cast context (as Second Wind) + range -1 = unlimited
         desc="Wraps a friendly unit in crackling static until the end of the battle: it becomes immune to lightning and its attacks strike with lightning.",
         gfx={0: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(3200, 3230)), -48, -86, f20=2, f18=1)},   # v2: lightning strike + crackling shell (2 ticks/frame)   # crackling static shell (96x96, Second Wind's canvas)
         sfx=["SFX\\ZSP\\DUALAI_STATICSHIELD.WAV"]),
    dict(id=216, name="Mend Walls", sphere=3, tier=1, mana=4, research=40,
         donor="TOoze", pfs_donor=134, tc_type=0x0A, icon=216,                 # Ooze clone: ATK/DMG 0, 19 strikes, RANGE 0xFF (unlimited) inherited; alias 216 -> 0x7C; patch_tc_mendwalls_v1.py: each strike repairs the city wall / gate on its hex
         desc="Earth magic tears stones and rubble from the ground around the walls and flings them back into place: each damaged wall and gate section in the target area is repaired by a random amount. Fully destroyed wall sections cannot be mended.",
         gfx={0: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(3954, 3962)), -31, -33, f20=3, f18=1),   # tumbling stone block (Ooze's BALLS projectile slot: kind 4, f20 3, f18 1)
              1: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(5144, 5196)), -48, -92, f18=0),               # v7: wall glow, frame 1 = this wall's first hit (engine-clocked)
              3: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(5000, 5036)), -24, -40, f18=0),               # v7: ONE grey rock per effect (engine-clocked + engine-moved)
              4: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(5036, 5072)), -24, -40, f18=0),               # v7: ONE brown stick (piece k % 3 == 1)
              5: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(5072, 5108)), -24, -40, f18=0),               # v7: its additive halo + arrival burst
              7: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(5108, 5144)), -24, -40, f18=0),               # v7: the hole at the source hex (stationary)
              6: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(4850, 4900)), -112, -120, f18=0),              # v5: ... layout B (marker 6 = odd x + y)
              2: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(3966, 3990)), -48, -44, f20=2)},          # dust ring + settling golden earth-glow on each landed hex (Ooze's MISC splash slot; 24 x 2 ticks)
         sfx=["SFX\\ZSP\\DUALER_MENDWALLS.WAV", ["SFX\\ZSP\\DUALER_MENDSTONE1.WAV", "SFX\\ZSP\\DUALER_MENDSTONE2.WAV"], ["SFX\\ZSP\\DUALER_MENDHIT.WAV"]]),   # 0 = cast; 1 = kept (hail chassis); 2 = v7 per-hit crunch (engine, patch_tc_mendwalls_v2.py)
    dict(id=217, name="Depths of Plenty", sphere=3, tier=2, mana=50, research=90, upkeep=10,
         donor="TEarthMastery", pfs_donor=74, tc_type=None, icon=217,          # patch_depthsofplenty_v1.py: marker 217 chained in front of Golden Age's Earth Mastery caves; TMine.GetIncome +1/+2/+3 by level
         pokes=[(0x34, 4, 0xFFFFFFFF)],                                       # AI priority -1 (as Golden Age / Nimue's Favour)
         desc="Rich veins open beneath your realm: each of your mines produces 1 extra gold on the surface, 2 underground and 3 in the depths.",
         gfx={0: G.seq_entry("EFFECTS\\DUALDF.ILB", [4220, 4221, 4222, 4223, 4222, 4221], -10, -10, f20=0)},   # map-wide amber ore glints (Earth Mastery particle)
         sfx=["SFX\\ZSP\\DUALER_DEPTHS.WAV"]),
    dict(id=218, name="Steadfast", sphere=3, tier=3, mana=5, research=130,
         donor="TGreatHail", pfs_donor=126, tc_type=0x0A, icon=218,              # hail class, 7 strikes (patch_rotaway STRIKES[218]); grant + live DEF = patch_steadfast_v1.py
         pokes=[(0x34, 1, 0), (0x35, 1, 0), (0x36, 2, 0), (0x39, 1, 0x0C), (0x3B, 1, 3)],   # ATK 0 / DMG 0 / no damage type / range 12 (long) / own units + enemies + empty hexes (Sanctify's)
         desc="The earth steadies your troops: friendly units in the target hex and every hex around it stand their ground until the end of the battle, gaining +2 defense while they still have their full movement and +1 while they have more than half.",
         gfx={0: G.seq_entry("EFFECTS\\DUALDF.ILB", [340], -2, -2, f20=0),                       # nothing visibly falls (Sanctify's blank)
              1: G.seq_entry("EFFECTS\\DUALDF.ILB", [340], -2, -2, f20=0),
              2: G.seq_entry("EFFECTS\\DUALDF.ILB", [340], -2, -2, f20=0),                       # v2: no per-hex impact (empty/enemy hexes show nothing)
              3: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(4400, 4426)), -48, -112, f18=1, f20=26)},   # v2: per-FRIENDLY-unit shield driver (patch_tc_steadfast_fx_v1.py marker 3; 26 x 2 ticks)
         sfx=["SFX\\ZSP\\DUALER_STEADFAST.WAV", ["SFX\\ZSP\\DUALER_STEADHIT.WAV"], ["SFX\\ZSP\\DUALER_STEADCLANG.WAV"]]),   # 0 = cast; 1 = REQUIRED per landing hex (air rush); 2 = the clang, played per SHIELDED unit by patch_tc_steadfast_clang_v1.py (a LIST so spellgfx gives it ID 2)
    dict(id=219, name="Tectonic Shift", sphere=3, tier=4, mana=75, research=250, upkeep=15,
         donor="TAirMastery", pfs_donor=70, tc_type=None, icon=219,          # patch_tectonic_v1.py: marker 219 chained in front of Overgrowth's Air Mastery caves; NewTurn raises hills/mountains, digs/buries tunnels (permanent)
         pokes=[(0x34, 4, 0xFFFFFFFF)],                                      # AI priority -1 (never cast by the AI, as Ice Age)
         desc="The ground heaves and shifts across the whole world: each turn hills rise from the land, hills harden into mountains and mountains grow ever larger - even out into the shallows - while underground new tunnels wind through the rock and old ones fill in, more so the deeper you go. Changed land glows faintly. Cities, structures, roads and units are never buried, and no passage is ever cut off. When the spell ends the land slowly settles back.",
         gfx={0: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(4600, 4610)), -48, -32, f20=0),      # motes A, 10 brightness levels (v4)
              1: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(4610, 4620)), -48, -32, f20=0),      # motes B
              2: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(4620, 4630)), -48, -32, f20=0),      # motes C
              4: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(4630, 4640)), -32, -24, f20=0),      # fissure line / edge A, 10 levels
              5: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(4640, 4650)), -32, -24, f20=0),      # fissure line / edge B
              6: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(4650, 4660)), -32, -24, f20=0),      # fissure line / edge C
              7: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(4660, 4670)), -40, -28, f20=0),      # open gap A, 10 levels
              8: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(4670, 4680)), -40, -28, f20=0),      # open gap B
              9: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(4680, 4690)), -40, -28, f20=0),      # open gap C
              3: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(4750, 4798)), -16, -31, f20=0)},     # per-hex glow v2: rising motes, 48 frames x 2 ticks (patch_tectonic_v1.py v3.1)
         sfx=["SFX\\ZSP\\DUALER_TECTONIC.WAV"]),
    dict(id=220, name="Crashing Wave", sphere=6, tier=1, mana=4, research=40,
         donor="TColdBreath", pfs_donor=118, tc_type=5, icon=220,          # class 5 breath cone as Gust 212; patch_tc_gust_v1.py v7 (family 212/220): push + shake/hop + spray; patch_tc_crashingwave_v1.py: walls
         pokes=[(0x34, 1, 8), (0x35, 1, 3), (0x36, 2, 0x180), (0x3A, 1, 3)], # ATK 8 / DMG 3 / Physical + Wall (0x100); fast-combat 3 targets; range 4 inherited
         desc="A crashing wave surges from the caster in a cone: every unit caught in it is struck (attack 8, damage 3, physical) and swept one hex away from the caster, if there is room to land. Walls stop the wave, but they are battered by it.",
         gfx={0: G.seq_entry("EFFECTS\\DUALDF.ILB", [340], -2, -2, f20=0),                     # the breath strikes draw nothing (as Gust)
              1: G.seq_entry("EFFECTS\\DUALDF.ILB", [5200, 5201, 5202, 5203], -9, -9, f20=1)},   # blue spray particles (Gust v7 SPR, kind 0x1F)
         sfx=["SFX\\ZSP\\DUALWT_CRASHWAVE.WAV"]),
    dict(id=221, name="Rite of the Seas", sphere=6, tier=2, mana=50, research=90, upkeep=10,
         donor="TEarthMastery", pfs_donor=74, tc_type=None, icon=221,          # patch_riteseas_v1.py: marker 221 chained in front of Depths of Plenty
         pokes=[(0x34, 4, 0xFFFFFFFF)],                                       # AI priority -1 (as Depths of Plenty / Golden Age)
         desc="The sea answers your rite: every ship your shipyards begin to build is launched with a Silver medal, but while the rite lasts each of your shipyards yields 1 less gold.",
         gfx={0: G.seq_entry("EFFECTS\\DUALDF.ILB", [5300, 5301, 5302, 5303, 5302, 5301], -10, -10, f20=0)},   # map-wide sea crests + silver glint (Earth Mastery particle)
         sfx=["SFX\\ZSP\\DUALWT_RITESEAS.WAV"]),
    dict(id=222, name="Summon Sea Serpent", sphere=6, tier=3, mana=40, research=140, upkeep=5,
         donor="TSummonMermaid", pfs_donor=211, tc_type=0, icon=222,
         desc="Summons a Sea Serpent, a great serpent of the deep that rises from the waves to drag ships and swimmers below.",
         summon_unit=218),   # 10/17 (user): vanilla summon gfx/sfx like the other summons (inherits pfs 211); unit 218 Sea Serpent
    dict(id=223, name="Flash Flood", sphere=6, tier=4, mana=6, research=200,
         donor="TTremors", pfs_donor=122, tc_type=0x1D, icon=223,      # class 29 = Tremors' TE + kind-29 carrier; patch_tc_flashflood_v1.py: flood damage + displacement + particles + gentle shake
         pokes=[(0x34, 1, 4), (0x35, 1, 7), (0x36, 2, 0x80)],          # v2 10/17: ATK 4 / DMG 7 / Physical (range 0xFF, 1 shot inherited)
         desc="A raging flash flood sweeps across the battlefield from the caster's side: every unit that is not flying, floating or wind walking is swept up to 4 hexes away in a random direction, hit or not, and struck (attack 4, damage 7, physical). Swimmers, water walkers, swamp walkers and liquid-form units are swept only up to 2 hexes and take half damage, and ships are swept up to 2 hexes but take no damage. Nobody is swept onto a standing wall or gate.",
         gfx={0: G.seq_entry("EFFECTS\\DUALDF.ILB", [5400, 5401, 5402], -28, -12, f20=0)},   # the kind-0x1F flood particles (frame = particle address mod 3)
         sfx=["SFX\\ZSP\\DUALWT_FLASHFLOOD.WAV"]),
    dict(id=228, name="Magic Missile", sphere=0, tier=1, mana=4, research=50,
         donor="TVaporize", pfs_donor=131, tc_type=6, icon=228,      # 2026-10-17 Cosmos L1: class 6 = Flaming Arrow's PROJECTILE class (NextStrike default case 0x40ED2D: MakeRangedPath, stops at the first unit/wall), 3 strikes = 3 bolts one after another
         pokes=[(0x34, 1, 7), (0x35, 1, 1), (0x36, 2, 0x08), (0x38, 1, 3), (0x39, 1, 0x0C), (0x3C, 1, 0)],   # ATK 7 / DMG 1 / Magic (8) / 3 strikes / range 12 / roll vs DEF (as Flashfreeze)
         desc="Hurls three bolts of pure arcane force at a distant enemy, one after another: attack 7, damage 1, magic, each bolt rolled separately. Like an arrow, a bolt can be stopped by walls and units in its path.",
         gfx={0: G.seq_entry("EFFECTS\DUALDF.ILB", list(range(6000, 6008)), -32, -33, f20=0),      # kind-6 HEAD, drawn looped at the path point (0x42E5FC; frame = map clock + self>>2)
              1: G.seq_entry("EFFECTS\DUALDF.ILB", list(range(6008, 6016)), -32, -33, f20=2)},     # kind-6 TRAIL (0x42E85C): frame 0 right behind the head .. 7 oldest (vanilla Flaming Arrow: BOLTS.ILB 70-77, f20 2)
         sfx=["SFX\ZSP\DUALCO_MMISSILE.WAV", ["SFX\ZSP\DUALCO_MMHIT.WAV"]]),                   # cue 0 = cast (strike 0 anim), cue 1 = each landing (kind-6 NewFrame 0x42A0A2)
    dict(id=229, name="City Spy", sphere=0, tier=2, mana=15, research=80, upkeep=2,
         donor="TGoldRush", pfs_donor=63, tc_type=None, icon=229,                  # city enchantment like Arms Race 375; patch_cityspy_v1.py
         pokes=[(0x3C, 1, 5), (0x38, 1, 2)],                                        # enchantment TYPE 5 -> [city+0x5C] bit 0x20; targets: cities NOT owned by the caster (as Town Quake / Anarchy)
         desc="A hidden eye watches over a foreign city: while the enchantment lasts, selecting that city shows its income, size and upgrades, civil status and current production in the info panel just as for your own cities. The watching eye above the city can be seen by everyone.",
         gfx={0: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(6112, 6128)), -36, -56, f20=2, f18=1),   # cast: violet motes spiral into a scrying eye at the city (PlayDefaultCityEffects)
              1: G.seq_entry("EFFECTS\\DUALDF.ILB", [6416] * 2 + [6417] * 2 + [6418] * 2 + [6400] * 3 + [6401] * 2 + [6402, 6403, 6404, 6405, 6406, 6407, 6408, 6409, 6410, 6411, 6412, 6413] + [6414] * 2 + [6360] * 10 + [6359] * 2 + [6358, 6357, 6355, 6354, 6353, 6351, 6350, 6349, 6347, 6346] + [6345] * 2 + [6344] * 20 + [6345] * 2 + [6347, 6348, 6349, 6351, 6353, 6355, 6357, 6359, 6361, 6363, 6365, 6367, 6369, 6371, 6372, 6373] + [6375] * 2 + [6376] * 20 + [6375, 6374, 6373, 6371, 6370, 6368, 6366, 6365, 6363, 6427, 6428, 6413, 6412, 6411] + [6410] * 2 + [6409, 6408, 6406] + [6405] * 2 + [6404, 6403, 6402] + [6401] * 2 + [6400] * 3 + [6418] * 2 + [6417] * 2 + [6416] * 2 + [6343] * 57, -20, -14, f20=2, f18=3)},   # v7 10/18: lids open fully (iris centred) + 0.21 s settle before the look-left; v6 overlapped close kept; 201 x 35 ms = 7.04 s (= cityspy_eye7_timeline(6420, 6400, 6343))
         sfx=["SFX\\ZSP\\DUALCO_CITYSPY.WAV"]),
    dict(id=225, name="Smokescreen", sphere=5, tier=2, mana=4, research=50,
         donor="TOoze", pfs_donor=134, tc_type=0x0A, icon=225,                 # Ooze chassis (19-hex preview), alias 225 -> 0x7C; patch_tc_smokescreen_v1.py: no strikes - the gate lays the smoke field on all 19 hexes; patch_smokescreen_v1.py: 0xC6 + the accuracy penalty
         pokes=[(0x34, 1, 0), (0x35, 1, 0), (0x36, 2, 0), (0x39, 1, 0x0C), (0x3B, 1, 3)],   # ATK 0 / DMG 0 / no damage type / range 12 (long) / own units + enemies + empty hexes (Sanctify's targeting)
         desc="A thick bank of ash-grey smoke billows over the target hex and every hex within two of it for 3 turns. Units without True Seeing standing in the smoke fight half blind: melee and ranged attack -3 (never below 1).",
         gfx={0: G.seq_entry("EFFECTS\\DUALDF.ILB", [340], -2, -2, f20=0),                       # no strikes: nothing falls
              1: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(5650, 5670)), -36, -52, f18=1),   # v2: per-hex ash puff at the cast (kind-0x26 at the hex centre = canvas (36, 52); 20 x 2 ticks)
              2: G.seq_entry("EFFECTS\\DUALDF.ILB", [340], -2, -2, f20=0),
              3: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(5670, 5718)), -120, -88, f18=2),   # v2: the whole-area bank (loop; v3 frame picker: k mod 48)
              4: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(5718, 5738)), -120, -88, f18=2)},  # v3: the bank's grow-in (k < 20), then slot 3 takes over seamlessly
         sfx=["SFX\\ZSP\\DUALFR_SMOKESCREEN.WAV", ["SFX\\ZSP\\DUALFR_SMOKESCREEN.WAV"]]),   # 0 = cast (played by the gate); 1 = the hail chassis' landing list (never reached: no strikes)
    dict(id=226, name="Wall of Flames", sphere=5, tier=3, mana=4, research=70,
         donor="TGreatHail", pfs_donor=126, tc_type=0x0A, icon=226,              # hail class, 7 strikes (patch_rotaway STRIKES[226]); flames = patch_tc_walloflames_v1.py
         pokes=[(0x34, 1, 10), (0x35, 1, 2), (0x36, 2, 0x01), (0x39, 1, 0x0C), (0x3B, 1, 3)],   # v2 10/17: the 6 ring strikes = ATK 10 / DMG 2 / Fire (centre gets none: STRIKES 6 + the hn ring remap); range 12; own + enemy + empty hexes; lingering burn = ATK 10 / DMG 1 fire (engine)
         desc="A ring of fire erupts around the target hex: every unit on the six surrounding hexes is burned (attack 10, damage 2, fire), and the flames linger for 3 turns, burning any unit that moves into them or begins its turn standing in them (attack 10, damage 1, fire).  The centre hex is left untouched.",
         gfx={0: G.seq_entry("EFFECTS\DUALDF.ILB", [340], -2, -2, f20=0),                       # nothing visibly falls (Sanctify's blank)
              1: G.seq_entry("EFFECTS\DUALDF.ILB", [340], -2, -2, f20=0),
              2: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(5750, 5768)), -51, -40, f20=2, f18=1),   # per-hex ignition burst (Sanctify's per-hex canvas / anchor)
              3: G.seq_entry("EFFECTS\\FIRESM.ILB", list(range(12)), -56, -67, f18=7)},   # v2.1 10/17 f18 2->7 (user: way too fast); v2: the LINGERING flame = the strategic 1-hex fire object (vanilla EFFECTS\FIRESM.ILB 0-11, 112x78, flame base (56,71) on the hex centre + 4; 3 ticks/frame, looped by the clone's Show)
         sfx=["SFX\ZSP\DUALFI_WALLFLAMES.WAV", ["SFX\ZSP\DUALFI_FLAMEHIT.WAV"]]),   # 0 = cast; 1 = REQUIRED per landing hex (hail class)
    dict(id=227, name="Pyroclasm", sphere=5, tier=4, mana=75, research=200, upkeep=10,
         donor="TAirMastery", pfs_donor=70, tc_type=None, icon=227,          # patch_pyroclasm_v1.py: marker 227 chained in front of Tectonic's Air Mastery caves; NewTurn: mountains -> volcanoes, lava (permanent)
         pokes=[(0x34, 4, 0xFFFFFFFF)],                                      # AI priority -1 (never cast by the AI, as Tectonic / Ice Age)
         desc="The earth's fire wakes: each turn medium and large mountains slowly become volcanoes, each spilling lava as it wakes and every turn after, and every volcano already on the map erupts when the spell is first cast. Lava creeps on in winding rivers, burns through forests, melts the snow beside it into steppe and engulfs any army that cannot stand in fire. Below ground, the lava of the caverns and depths spreads through the dirt passages. When the spell ends the fire slowly dies: lava cools into wasteland, the volcanoes fall dormant as barren mountains and the lava below ground cools back into open dirt passages.",
         gfx={0: G.seq_entry("EFFECTS\\DUALDF.ILB", [5850], -100, -58, f20=0),                 # Air Mastery map-wide drift: ember-and-ash rain
              1: G.seq_entry("EFFECTS\\DUALDF.ILB", [5851], -98, -54, f20=0),
              2: G.seq_entry("EFFECTS\\DUALDF.ILB", [5852], -96, -58, f20=0),
              3: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(5853, 5901)), -16, -31, f20=0),   # per-hex glow on our volcano / lava hexes (patch_pyroclasm_v1.py glow cave, 48 frames x 2 ticks)
              4: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(5950, 5958)), -5, -5, f20=0),          # v3: ember x 8 levels (frame = level via Show's time; patch_pyroclasm_fx_v1.py)
              5: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(5958, 5966)), -4, -4, f20=0),          # v3: ash fleck x 8 levels
              6: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(5966, 5974)), -6, -6, f20=0),          # v3: lava spark x 8 levels
              7: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(5974, 5982)), -36, -22, f20=0)},       # v3: lava-light haze x 8 levels
         sfx=["SFX\\ZSP\\DUALFR_PYROCLASM.WAV"]),
    dict(id=230, name="Royal Ambition", sphere=0, tier=3, mana=50, research=150, upkeep=7,
         donor="TEarthMastery", pfs_donor=74, tc_type=None, icon=230,          # patch_royalambition_v1.py: marker 230 chained in front of Rite of the Seas (-> Depths -> Golden Age)
         pokes=[(0x34, 4, 0xFFFFFFFF)],                                       # AI priority -1 (as Depths of Plenty / Rite of the Seas)
         desc="Your royal ambition magnifies every deed: while this spell lasts, every gain and every loss in any race's regard for you - from diplomacy (war, peace, alliances, tribute) and from city actions (upgrading, producing, migrating, looting, razing) - is doubled.",
         gfx={0: G.seq_entry("EFFECTS\\DUALDF.ILB", [6150, 6151, 6152, 6153, 6152, 6151], -10, -10, f20=0)},   # map-wide golden star glints (Earth Mastery particle)
         sfx=["SFX\\ZSP\\DUALCO_ROYAL.WAV"]),
    dict(id=231, name="Essence Shift", sphere=0, tier=4, mana=50, research=250,
         donor="TRejuvenate", pfs_donor=51, tc_type=None, icon=231,          # global hex-target (TRejuvenate clone); patch_essenceshift_v1.py does the node transform (terrain sweep off)
         pokes=[(0x39, 1, 0)],                                                # v2 10/18: clear the surface-only flag (TRejuvenate.Create sets 1) -> castable underground / in the depths (target-error routine 0x5579E73C)
         desc="Reshape the essence of a magic node or altar you own: the target (a mana node, an elemental node or an altar that is not razed, on the surface, underground or in the depths) takes on the element you are most devoted to (a tie is decided at random). Altars become the Altar of Life, Death, Pestilence (Earth), Lightning, Fire or Ice. Its guards remain.",
         gfx={0: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(6200, 6244)), -60, -85, f18=1)},   # v3: cosmic six-colour swirl + starlight ring, smooth fade-out tail (96x96, 44 x 2 ticks)
         sfx=["SFX\\ZSP\\DUALCO_ESSENCE.WAV"]),
    dict(id=232, name="Lucky", sphere=7, tier=1, mana=7, research=77, upkeep=1,
         donor="TDarkGift", pfs_donor=87, tc_type=7, icon=232,                   # Secret L1 (sphere 7; research = Wizard's Tower cost); TDarkGift clone like Lionheart 373 - patch_lucky_v1.py grants ability 0xC8 (+3 RES)
         desc="Fortune smiles on the target unit: it gains +3 Resistance while the enchantment lasts.",
         gfx={0: _emblem_slot_seq(49, 0, [6526, 6527, 6529, 6532, 6534, 6535] + [6536] * 9 + [6535, 6535, 6534, 6533, 6532, 6530, 6529, 6528, 6527, 6526, 6526, 6525, 6525], f18=1, path=VANILLA_PFS)},   # v3 10/18 (user: smoother fade-out): 12 emblem strengths, eased in / hold / out at 2 ticks per frame (56 ticks, ends ~3 %) on the vanilla green-twinkle chain
         sfx=["SFX\\ZSP\\DUALSE_LUCKY.WAV"]),
    dict(id=233, name="Mimic", sphere=7, tier=2, mana=5, research=100,
         donor="TDispelMagic", pfs_donor=18, tc_type=7, icon=233,        # Secret L2; a Dispel Magic clone = the fallback when nothing was cast yet; patch_tc_mimic_v1.py turns the book pick into the last spell cast this combat (charged 5)
         pokes=[(0x22, 1, 0), (0x0C, 1, 2)],                          # v3 10/18: COMBAT spell type (Dispel's base ctor 0x5577AC34 sets 1 = unit spell) + combat-only cast context
         desc="Mirrors the last spell cast in this battle by anyone, friend or foe, for Mimic's own cost. If no spell has been cast yet, it casts Dispel Magic instead.",
         gfx={1: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(6600, 6620)), -32, -76, f20=2, f18=1)},   # slot 1 = mirror shimmer at the CASTER (kind-0x26 driver from patch_tc_mimic_v1; 64x96, hex centre at (32,76), 20 x 2 ticks); slot 0 = Dispel Magic's own twinkle (fallback target fx) kept
         sfx=["SFX\\ZSP\\DUALSE_MIMIC.WAV", "SFX\\ZSP\\DUALSE_MIMIC.WAV"]),   # cue 0 = the fallback's cast (cast animation), cue 1 = played by the engine at a copied cast
    dict(id=234, name="Reversal", sphere=7, tier=3, mana=7, research=150,
         donor="TRemedy", pfs_donor=45, tc_type=7, icon=234,          # Suspend's single-target chassis (range 12 = long); patch_reversal_v1.py: ability 0xC7 'Reversed' swaps ATK<->DEF and DMG<->RES until combat end (re-cast toggles back)
         pokes=[(0x22, 1, 0), (0x0C, 1, 2)],                          # COMBAT spell type + combat-only cast context (as Suspend)
         desc="Turns a unit's strengths inside out until the end of the battle: its attack and defense trade places, and so do its resistance and damage. Works on friend or foe; cast it again on the same unit to set it right.",
         gfx={0: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(6700, 6736)), -48, -86, f20=2, f18=1)},   # two counter-rotating ribbons that invert colour + a mirror flash (96x96)
         sfx=["SFX\\ZSP\\DUALSE_REVERSAL.WAV"]),
    dict(id=235, name="Transmutation", sphere=7, tier=4, mana=75, research=300, upkeep=25,
         donor="TEarthMastery", pfs_donor=74, tc_type=None, icon=235,          # patch_transmutation_v1.py: marker 235 chained in front of Royal Ambition's Earth Mastery caves; research share -> gold income, research halted
         pokes=[(0x34, 4, 0xFFFFFFFF)],                                       # AI priority -1 (as Depths of Plenty / Rite of the Seas / Royal Ambition)
         desc="Your scholars' work is poured into the crucible: while this spell lasts, the research points your realm would earn each turn are turned into gold income instead, and your research makes no progress.",
         gfx={0: G.seq_entry("EFFECTS\\DUALDF.ILB", [6800, 6801, 6802, 6803, 6802, 6801], -10, -10, f20=0)},   # map-wide golden alchemical motes with a green glint (Earth Mastery particle)
         sfx=["SFX\\ZSP\\DUALSE_TRANSMUTE.WAV"]),
]

# 2026-10-13: the Life/Fire pair (sphere 11).  Martyr / Cleansing Flame = TRemedy clones whose behaviour lives in
# patch_martyr_cleansing_v1.py (AoWEPACK: ExecuteSpell / ValidTarget dispatch on the id; the Martyr ability 0xB0);
# Summon Phoenix = Mermaid clone summoning unit 271 (build_phoenix_unit_v1.py rebuilds that Unitres/Unitgfx slot);
# Holy Starfire = a plain Great Hail clone (no portal) with holy+fire damage - add 363 to patch_tc_spell_alias_v1.py
# (ALIAS 363 -> 0x74 + SITE_KEEP) exactly like Hellfire.  Art: build_dual_sphere_fx_v1.py 500-587, icons 360-363,
# sounds build_dual_sphere_sfx_v1.py DUALDF_MARTYR/CLEANSE/PHOENIX/STARLOOP/STARHIT1-2.
SPELLS += [
    dict(id=360, name="Martyr", sphere=11, tier=1, mana=3, research=40,
         donor="TRemedy", pfs_donor=45, tc_type=7, icon=360,
         desc="Fills a friendly unit with holy zeal: +2 attack, defense, damage and resistance for the rest of the combat, at the end of which the martyr dies. Unlimited range.",
         pokes=[(0x38, 4, 0xFFFFFFFF), (0x22, 1, 0), (0x0C, 1, 2)],   # 10/15: +0x0C cast-context bits (bit1 map, bit2 combat; TRemedy ctor sets 3) -> 2 = combat only;                               # TUnitSpell range -1 = unlimited; type byte 0 = COMBAT spell (TUnitSpell.Create sets 1 = unit spell: listed + castable on the world map; 10/13 user: "Martyr should be a combat spell")
         gfx={0: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(500, 516)), -32, -50, f20=11, f18=2)},    # gold-red flame motes rising round the unit (10/13: x3 ticks = 48, user: lasted too short)
         sfx=["SFX\\ZSP\\DUALDF_MARTYR.WAV"]),
    dict(id=361, name="Cleansing Flame", sphere=11, tier=2, mana=3, research=50,
         donor="TRemedy", pfs_donor=45, tc_type=7, icon=361,
         desc="Purges a friendly unit with holy fire: heals 3 hit points and removes stun, freezing, poison, curses, entanglement, webs, seduction, charm and domination - then leaves the unit burning.",
         gfx={0: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(520, 536)), -32, -58, f20=11, f18=1)},    # fire burst with a white-gold core
         sfx=["SFX\\ZSP\\DUALDF_CLEANSE.WAV"]),
    dict(id=362, name="Summon Phoenix", sphere=11, tier=3, mana=50, research=120, upkeep=8,
         donor="TSummonMermaid", pfs_donor=211, tc_type=0, icon=362,
         desc="Summons a Phoenix, a great firebird of the heavens.",
         summon_unit=271,
         gfx={0: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(540, 552)), -31, -116, f20=1, f18=1)},    # the Mermaid summon glow (MAGIC 20-31) tinted gold/orange
         sfx=["SFX\\ZSP\\DUALDF_PHOENIX.WAV"]),
    dict(id=363, name="Holy Starfire", sphere=11, tier=4, mana=5, research=300,
         donor="TGreatHail", pfs_donor=126, tc_type=0x0A, icon=363,
         desc="Rains burning stars upon the target area, searing units and walls with holy flame.",
         pokes=[(0x36, 2, 0x01C1)],             # Great Hail 0x0180 (Physical+Wall) -> + Holy + Fire
         gfx={0: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(560, 568)), -32, -33, f20=0),      # falling star (path head)
              1: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(570, 580)), -32, -33, f20=4),      # trail (previous path points)
              2: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(580, 588)), -32, -33, f20=3)},     # impact flash
         sfx=["SFX\\ZSP\\DUALDF_STARLOOP.WAV", ["SFX\\ZSP\\DUALDF_STARHIT1.WAV", "SFX\\ZSP\\DUALDF_STARHIT2.WAV"]]),
]

# 2026-10-13: Ashes to Ashes (Death/Fire tier 3): a Death Ray clone whose cast first burns EVERY corpse on the
# battlefield (patch_tc_ashes_v1.py: corpse sweep in TCAbRangedTE.Execute phase 0, a kind-0x26 effect drawing slot 1
# on each corpse, the corpse sprite freed, the count written into [spell+0x35] = damage).  9 ATK, physical + death +
# fire, range 3, 1 shot.  Art: DualDF 600-619 burning corpse (alpha), 620-623 ember ray head; icon 353; DUALDF_ASHES.WAV.
SPELLS += [
    dict(id=353, name="Ashes to Ashes", sphere=15, tier=3, mana=5, research=120,
         donor="TDeathRay", pfs_donor=113, tc_type=7, icon=353,                 # v2: class 7 = direct single target like Vaporize/Death Ray (v1's 0x0B shot a projectile)
         desc="Sets every corpse on the battlefield ablaze one by one, then the ashes engulf a nearby enemy: attack 9, damage 1, striking once plus once more for every corpse consumed, as physical, death and fire. Consumed corpses cannot be raised.",
         pokes=[(0x34, 1, 9), (0x35, 1, 1), (0x36, 2, 0x00A1), (0x39, 1, 3)],       # v3: ATK 9, DMG 1, Physical+Death+Fire, range 3; strikes = 1 + corpses, set per cast in the TE by patch_tc_ashes_v1.py's gate
         # slot 0 = the hit at the target (class 7 draws it at the target hex like Vaporize's SMOKE 17 x 2 ticks / Death
         # Ray's EXPLTC; 96x96 frames centred on the unit's body: -48 / -80), slot 1 = the burning corpse drawn by the
         # kind-0x26 effect the sweep spawns on every corpse (20 x 2 ticks; the strike gate waits for these to die).
         # v6: a class-7 strike effect LANDS (= damages) only when its sequence reaches the last frame, so slot 0 is now a
         # 4 x 1-tick impact pulse (damage ~4 ticks after each strike) and the swirl is slot 3, a 13-frame segment (6 loop
         # = GAP ticks + 7 fade) that patch_tc_ashes_v1.py's gate spawns as a kind-0x26 driver ([fx+0x24]=1) on every
         # strike pass: consecutive hits chain into one continuous swirl and the last segment fades out after the last hit.
         gfx={0: G.seq_entry("EFFECTS\\DUALDF.ILB", [760, 761, 762, 763], -32, -70, f20=1, f18=0),
              # v9: slots 3..6 = four 6-frame slices of one seamless 24-frame pillar swirl (12 ticks each); the gate spawns slice
              # (strikes done mod 4) on every strike pass, so the spin runs continuously across the hits and stops after the last.
              # v9b: the slices OVERLAP - each is 9 frames (18 ticks) starting 6 frames apart, so a slice outlives the 11-13 tick
              # hit interval and the next one takes over before it dies (no cut-out); frame ids wrap round the 24-frame loop.
              3: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(860, 884)), -48, -84, f20=2, f18=1),             # v10: the full seamless loop; ONE driver kept alive by the gate, killed after the last strike
              4: G.seq_entry("EFFECTS\\DUALDF.ILB", [860 + (6 + j) % 24 for j in range(9)], -48, -84, f20=2, f18=1),
              5: G.seq_entry("EFFECTS\\DUALDF.ILB", [860 + (12 + j) % 24 for j in range(9)], -48, -84, f20=2, f18=1),
              6: G.seq_entry("EFFECTS\\DUALDF.ILB", [860 + (18 + j) % 24 for j in range(9)], -48, -84, f20=2, f18=1),
              2: G.seq_entry("EFFECTS\\DUALDF.ILB", [690, 691, 692, 693, 694, 695], -11, -11, f20=2),     # red-orange ember mote: the kind-0x1F sparkles streaming corpse -> caster (patch_tc_ashes_v1.py v5 slot hook)
              1: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(600, 620)), 0, 0, f20=1, f18=1)},         # burning corpse (kind-0x26 effect at each corpse, 20 x 2 ticks)
         # sound 0 = the hit (vanilla plays it from the caster's cast animation = at the strike, after the burn);
         # 1 = the ignition hiss, played by the sweep cave when corpses burned (variant sub-list like every 2nd sound)
         sfx=["SFX\\ZSP\\DUALDF_ASHHIT.WAV", ["SFX\\ZSP\\DUALDF_ASHIMPACT.WAV"], ["SFX\\ZSP\\DUALDF_ASHES.WAV"]]),   # v11: 0 cast whirl (caster animation, first strike), 1 per-hit impact (kind-7 landing plays sound 1 every hit), 2 corpse ignition (sweep cave)
]

# ---- Earth/Fire (sphere pair 18, ids 372..379; 2026-10-13).  Behaviour caves: patch_forge_arms_v1.py (374/375),
# patch_lionheart_v1.py (373: a second TDarkGiftEnchantment instance = ability 0xB1 "Lionheart", +2 damage, accepted by the
# four Fearless checks; Dark Gift's ExecuteSpell/ValidTarget re-implemented per spell id) + patch_ability_pfs_lionheart.py.
SPELLS += [
    dict(id=372, name="Oil Spring", sphere=18, tier=1, mana=3, research=30,
         donor="TOoze", pfs_donor=134, tc_type=0x0A, icon=372,
         pokes=[(0x39, 1, 0x0C)],                                                 # v3.2 2026-10-14: RANGE byte = 0x0C like Great Hail / Fireball / Slow (Ooze's 0xFF = unlimited); 7-hex area + 7 strikes + preview = patch_oilspring_v1.py                    # v3: Ooze clone (hail class 0x0A, 19 strikes); patch_oilspring_v1.py turns the landings into OIL hexes (no movement penalty) that give any unit standing in them "Fire Weakness (combat only)" (ability 0xB2 named Fire Weakness) until it steps off; alias 372 -> 0x7C with SITE_KEEP at 0x40C8D0 (patch_tc_spell_alias_v1.py)
         desc="A spring of black oil erupts and rains over the target area, leaving the ground slick with oil. Any unit standing in the oil suffers Fire Weakness until it moves off.",
         gfx={0: G.seq_entry("EFFECTS\\DUALDF.ILB", [340], -2, -2, f20=0),                                 # v6 2026-10-14: the glob projectile is INVISIBLE (blank 340) - the oil simply appears on the ground (splash + tile) under the gush
              1: G.seq_entry("EFFECTS\\DUALDF.ILB", [340], -2, -2, f20=0),                                 # trail invisible too
              2: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(1140, 1145)), -33, -31, f20=2),            # splash (Ooze's MISC 40-44 slot)
              3: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(1120, 1125)), 0, 0, f20=0),                # the OIL HEX tile variants, drawn by the oil HS (frame = (self>>2) mod 5)
              4: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(4100, 4166)), -80, -136, f20=1, f18=0),            # v3 RISE: 66 x 1 tick (transient fountain, == loop frame 12 at tick 48)
              5: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(4166, 4196)) * 2, -80, -136, f20=1, f18=0),        # v3 LOOP: one cycle x2 (life 60; the gate wraps it by 30)
              6: G.seq_entry("EFFECTS\\DUALDF.ILB", [4196] * 30 + list(range(4197, 4218)), -80, -136, f20=1, f18=0)},   # v3 END: 30 blank ticks + 21-frame collapse
         sfx=["SFX\\ZSP\\DUALEF_OILSPRING.WAV", ["SFX\\MOVES\\SLIMES1.WAV", "SFX\\MOVES\\SLIMES2.WAV", "SFX\\MOVES\\SLIMES3.WAV"]]),   # v3.2 (2026-10-14): the hail-class TfxHS landing plays sound ID 1 on EVERY strike (TSFXLibrary.Play 0x5540608C finds by ID, nil when missing -> AV per landing = the TokenExecute burst); 0 = the geyser at the cast, 1 = Ooze's slime splats per glob
    dict(id=373, name="Lionheart", sphere=18, tier=2, mana=3, research=60, upkeep=1,
         donor="TDarkGift", pfs_donor=87, tc_type=7, icon=373,                   # SpellTypes[77] = 7: castable in combat on a unit, like Dark Gift
         desc="Fills a unit with a lion's courage: it becomes Fearless and strikes for +2 damage while the enchantment lasts.",
         gfx={0: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(1020, 1030)), -20, -24, f20=2, f18=1)},   # golden-red heart burst on the unit (Dark Gift's slot 0 twinkle)
         sfx=["SFX\\ZSP\\DUALEF_LIONHEART.WAV"]),
    dict(id=374, name="Forge Blast", sphere=18, tier=3, mana=50, research=110,
         donor="TTownQuake", pfs_donor=81, tc_type=None, icon=374,
         desc="A blast from the forges rocks the target city: whatever it was producing is lost (no gold is refunded) and every unit inside is scorched by the blast (attack 8, damage 4, fire). The walls are untouched.",
         gfx={0: _pfs_slot(127, 1, VANILLA_PFS)},                                       # v3: Fireball's EXPLBIG 0-29 explosion (-131/-142, f20=15), played at the city by PlayDefaultCityEffects from the DAMAGE step (patch_forge_arms_v1.py v3) after a 20-step quake
         sfx=["SFX\\ATTACK\\BLAST.WAV", ["SFX\\ATTACK\\EARTH.WAV"]]),                     # 0 = Fireball's impact blast (with the explosion), 1 = Town Quake's EARTH rumble (step 0, during the shake; played via G_SNDIDX)
    dict(id=375, name="Arms Race", sphere=18, tier=4, mana=75, research=250, upkeep=10,
         donor="TGoldRush", pfs_donor=63, tc_type=None, icon=375,
         desc="Drives the city's forges and drill yards day and night: every production started while the enchantment lasts takes one turn less to complete, never less than one.",
         pokes=[(0x3C, 1, 4)],                                                           # city enchantment type 4 -> [city+0x5C] bit 0x10 (patch_forge_arms_v1.py hooks the per-turn countdown)
         gfx={0: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(1060, 1075)), -24, -30, f20=2, f18=1),    # forge-glow cog twinkle over the city (Gold Rush's slot 0 twinkle)
              1: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(1150, 1162)), -24, -26, f20=2, f18=3)},   # 2026-10-14: the CITY ENCHANTMENT shimmer (Fountain of Life glow on every pad hex, patch_city_enchant_ui_v1.py v3; a separate sequence so the unit sparkle is never touched)
         sfx=["SFX\\ZSP\\DUALEF_ARMSRACE.WAV"]),
]

# ---- Fire/Air (sphere pair 20, ids 388..395; 2026-10-14).  Behaviour caves: patch_sandstorm_v1.py (388: the 30 strikes spread
# over the 19-hex area round the clicked unit, x2 damage vs Flying).
SPELLS += [
    dict(id=388, name="Sandstorm", sphere=20, tier=1, mana=3, research=30,
         donor="TGreatHail", pfs_donor=126, tc_type=0x0A, icon=388,                # v2 2026-10-14: hail class (the class-14 Swarm clone crashed); patch_sandstorm_v1.py v2: the landings round-robin over the units inside the 19-hex area (<= 3 hits each), x2 vs Flying; alias 388 -> 0x74 with the preview site overridden to Ooze's 19-hex glow
         pokes=[(0x34, 1, 8), (0x35, 1, 1), (0x36, 2, 0x80)],                           # ATK 8 / DMG 1 / Physical; range 0x0C inherited
         desc="A storm of stinging sand sweeps the target area: every unit inside is battered again and again (attack 8, damage 1, physical); flying units take double damage.",
         gfx={0: G.seq_entry("EFFECTS\\DUALDF.ILB", [340], -2, -2, f20=0),                                 # v4: nothing visibly falls
              1: G.seq_entry("EFFECTS\\DUALDF.ILB", [340], -2, -2, f20=0),
              2: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(1304, 1312)), -24, -30, f20=2, f18=1),    # the dust burst at each hit hex
              4: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(1410, 1418)), -112, -92, f20=2, f18=1),   # v4: the swirl rising over the area (patch_tc_sandswirl_v1.py marker 1)
              5: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(1418, 1430)), -112, -92, f20=2, f18=1),   # v4: the swirl loop (marker 2, kept alive until the last strike)
              6: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(1430, 1449)), -112, -92, f20=2, f18=1)},  # v4: 11 blank + 8 fade frames (marker 3)
         sfx=["SFX\\ZSP\\DUALFA_SANDSTORM.WAV", ["SFX\\ZSP\\DUALFA_SANDHIT.WAV"]]),           # cue 0 = cast/loop (Great Hail: WIND), cue 1 = per landing
    dict(id=389, name="Implosion", sphere=20, tier=2, mana=4, research=70,
         donor="TGreatHail", pfs_donor=126, tc_type=10, icon=389,                    # hail class: falls straight down = nothing obstructs it; patch_implosion_v1.py: 1 strike, dead on the hex; alias 389 -> 0x74 (kept at 0x40B541 / 0x42827A)
         pokes=[(0x34, 1, 8), (0x35, 1, 8), (0x36, 2, 0x181), (0x38, 1, 1), (0x39, 1, 4), (0x3A, 1, 1)],   # ATK 8 / DMG 8 / Fire|Physical|Wall / 1 shot / range 4 / 1 fast-combat target
         desc="The air above the target collapses inward and detonates: the target hex and every hex around it - units, walls and structures alike - take a crushing blast (attack 8, damage 8, fire and physical). Short range; obstructions are no shelter.",
         gfx={0: G.seq_entry("EFFECTS\\DUALDF.ILB", [340], -2, -2, f20=0),                                 # falling head invisible
              1: G.seq_entry("EFFECTS\\DUALDF.ILB", [340], -2, -2, f20=0),                                 # trail invisible
              2: G.seq_entry("EFFECTS\\DUALDF.ILB", [340], -2, -2, f20=0),                                 # v4: no hail impact sprite (the explosion is in the driver)
              3: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(1360, 1403)), -120, -128, f20=2, f18=1)},  # v4: red twinkle ring contracting (14) + Fireball's full EXPLBIG (30), 2 ticks/frame, one kind-0x26 driver at the hex centre
         sfx=["SFX\\ZSP\\DUALFA_IMPLOSION.WAV", ["SFX\\ATTACK\\BLAST.WAV"]]),                     # cue 0 = the ring (in-rush, fire, crack + thud), cue 1 = Fireball's own BLAST at the landing
    dict(id=390, name="Frenzied Charge", sphere=20, tier=3, mana=5, research=100,
         donor="THighPrayer", pfs_donor=112, tc_type=37, icon=390,                    # patch_frenzied_charge_v1.py: the per-unit CA grants the REAL Fury 0x9C + Haste 0x98 plus combat-only markers 0xB3/0xB4 that strip them at CombatDone
         desc="A frenzy sweeps through your army: every friendly unit gains Fury and Haste until the end of the combat.",
         gfx={0: G.seq_entry("EFFECTS\\DUALDF.ILB", [340], -2, -2, f20=0),                                 # v7: NO rising per-unit particles (High Prayer slot 0 rises 100 px every 5 ticks for 100 ticks = the column of swords)
              1: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(1312, 1335)), -20, -56, f20=2, f18=1)},       # v7: the swords play ONCE per unit at tick 0 (patch_tc_bloodbath_aura_v1.py spawns slot 1 at tick 0 for 350 + 390): 3 falling swords + crossed
         sfx=["SFX\\ZSP\\DUALFA_FRENZY.WAV"]),
    dict(id=391, name="Drought", sphere=20, tier=4, mana=75, research=250, upkeep=15,
         donor="TWaterMastery", pfs_donor=55, tc_type=None, icon=391,               # patch_drought_v1.py: the enchantment object is marked [ench+0x14] = 391; a NewTurn hook converts N_LAND=6 random surface hexes (+ a 1-in-4 shallow-water hex) to desert via THSMap.ChangeTerrainEx (synced RNG)
         desc="A merciless sun hangs over the land: each turn the drought turns random stretches of grass, steppe, snow, dirt and wasteland across the whole surface into desert, and now and then a shallow water hex dries out as well.",
         pokes=[(0x34, 4, 0xFFFFFFFF)],                                              # AI priority -1: the AI never casts it
         gfx={0: G.seq_entry("EFFECTS\\DUALDF.ILB", [2234], -100, -58, f20=0),          # v3 2026-10-15: Air Mastery-style map-wide heat drift (patch_drought_worldfx_v1.py v3)
              1: G.seq_entry("EFFECTS\\DUALDF.ILB", [2235], -98, -54, f20=0),
              2: G.seq_entry("EFFECTS\\DUALDF.ILB", [2236], -96, -58, f20=0),
              3: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(2222, 2234)), -33, -39, f20=0)},   # hex glow (moved from slot 1; patch_drought_glow_v1.py GLOW_SLOT 3)
         sfx=["SFX\\ZSP\\DUALFA_DROUGHT.WAV", ["SFX\\ZSP\\DUALFA_DROUGHTP.WAV"]]),              # Water Mastery = [M_WATER, [WATERLG]]
]
# ---- Fire/Water (sphere pair 22, ids 404..411; 2026-10-14).  Blood Boil / Scald = TVaporize clones (class 7 direct single
# target, no projectile / no LOS); Vaporize defaults ATK 9 / DMG 2 / physical / 5 strikes / range 4 (Spells.pfs key 131).
# Behaviour: patch_bloodboil_v1.py (404: machines untargetable + 0 dmg, target gains combat-only Bloodlust 0xA8 via the
# Blood Pact marker) and patch_scald_v1.py (405: DMG dice x1.5 vs Cold Weakness, x0.5 vs machines, in TCombatSpellCA.Setup).
SPELLS += [
    dict(id=404, name="Blood Boil", sphere=22, tier=1, mana=3, research=30,
         donor="TVaporize", pfs_donor=131, tc_type=7, icon=404,
         pokes=[(0x34, 1, 7), (0x35, 1, 4), (0x38, 1, 1), (0x39, 1, 0x0C)],                       # ATK 7 / DMG 4 / 1 strike / range 12 (types 0x80 physical inherited)
         desc="Boils the blood of a single living enemy anywhere in sight: attack 7, damage 4, physical, ignoring obstructions. The victim is driven into a Bloodlust until the end of the combat. Machines have no blood and cannot be targeted.",
         gfx={0: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(1490, 1506)), -46, -80, f18=1)},        # boiling bubbles + crimson steam on the unit (Vaporize's canvas/anchor); the hit lands at the last frame
         sfx=["SFX\\ZSP\\DUALFW_BLOODBOIL.WAV"]),
    dict(id=405, name="Scald", sphere=22, tier=2, mana=4, research=70,
         donor="TVaporize", pfs_donor=131, tc_type=7, icon=405,
         pokes=[(0x34, 1, 8), (0x35, 1, 4), (0x36, 2, 0x80), (0x38, 1, 1), (0x39, 1, 0x0C)],        # ATK 8 / DMG 4 / physical / 1 strike / range 12
         desc="Scalding steam bursts up from the ground beneath the target and engulfs it: attack 8, damage 4, physical; +50% against units with Cold Weakness, -50% against machines. Long range; obstructions are no shelter.",
         gfx={0: G.seq_entry("EFFECTS\\DUALDF.ILB", [1470, 1470, 1471, 1471, 1472, 1472, 1473, 1474, 1475, 1476, 1477, 1478, 1479, 1480, 1481, 1482, 1483], -37, -71, f18=1)},   # v3: v1 timing restored except the opening jet (frames 0-2) held twice = slightly longer start        # steam jet from the ground -> billowing steam (Geyser x Vaporize)
         sfx=["SFX\\ZSP\\DUALFW_SCALD.WAV", ["SFX\\ZSP\\DUALFW_SCALDHIT.WAV"]]),
    dict(id=406, name="Steam Power", sphere=22, tier=3, mana=50, research=100, upkeep=8,
         donor="TFireMastery", pfs_donor=73, tc_type=None, icon=406,                      # patch_steampower_v1.py: marker [ench+0x14]=406, Activate/Deactivate stubbed, Builder's Guild (+ shipyard) income x2, Construct actions half cost / one turn less
         pokes=[(0x34, 4, 0xFFFFFFFF)],                                                    # AI priority -1 (as Drought)
         desc="Steam drives the workshops of your realm: your Builder's Guilds and Shipyards produce double income, and every Construct action (building towers and shipyards, rebuilding structures, laying roads) costs half as much and takes one turn less (minimum one turn).",
         gfx={0: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(1510, 1520)), -24, -58)},     # map-wide steam puffs (Fire Mastery's cast animation draws slot 0 on random visible hexes)
         sfx=["SFX\\ZSP\\DUALFW_STEAMPOWER.WAV", ["SFX\\ZSP\\DUALFW_STEAMPUFF.WAV"]]),
]

# ---- Earth/Death (sphere pair 13, ids 332..339; 2026-10-14).  332 / 334 = summons of the existing Dire Wolf (unit 242) and
# Werewolf (239) via the TSummonMermaid recipe; 333 Rot Away / 335 Thousand Threads = Great Hail clones, 7 strikes (one per
# pattern hex) - behaviour in patch_rotaway_v1.py / patch_threads_v1.py.
SPELLS += [
    dict(id=332, name="Summon Dire Wolf", sphere=13, tier=1, mana=6, research=40, upkeep=2,
         donor="TSummonMermaid", pfs_donor=211, tc_type=0, icon=332,
         desc="Summons a Dire Wolf, a huge and savage beast that stalks the dark forests.",
         gfx={0: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(1520, 1532)), -31, -116, f20=1, f18=1)},      # green-grey summon glow
         summon_unit=242),
    dict(id=334, name="Summon Werewolf", sphere=13, tier=3, mana=40, research=130, upkeep=5,
         donor="TSummonMermaid", pfs_donor=211, tc_type=0, icon=334,
         desc="Summons a Werewolf, a cursed shapeshifter that heals its wounds and strikes fear into its foes.",
         gfx={0: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(1520, 1532)), -31, -116, f20=1, f18=1)},
         summon_unit=239),
    dict(id=333, name="Rot Away", sphere=13, tier=2, mana=4, research=80,
         donor="TGreatHail", pfs_donor=126, tc_type=0x0A, icon=333,                    # patch_rotaway_v1.py: 7 strikes (one per pattern hex), centred landings, x1.5 vs non-undead machines, Rot 0xB5 on machines
         pokes=[(0x34, 1, 7), (0x35, 1, 2), (0x36, 2, 0x90), (0x39, 1, 0x0C)],                    # ATK 7 / DMG 2 / Physical+Poison / range 12
         desc="A rotting blight falls on the target hex and every hex around it: attack 7, damage 2, physical and poison; +50% against machines (not undead ones), and machines it touches start to Rot - they may lose 1 hit point each turn for 3 turns.",
         gfx={0: G.seq_entry("EFFECTS\\DUALDF.ILB", [340], -2, -2, f20=0),                                 # v2: nothing visibly falls
              1: G.seq_entry("EFFECTS\\DUALDF.ILB", [340], -2, -2, f20=0),
              2: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(1610, 1626)), -50, -85, f20=2, f18=1)},   # v2: green bubbles boiling on each hex (Blood Boil recoloured)
         sfx=["SFX\\ZSP\\DUALED_ROTAWAY.WAV", ["SFX\\ZSP\\DUALED_ROTHIT.WAV"]]),
    dict(id=335, name="Thousand Threads", sphere=13, tier=4, mana=6, research=250,
         donor="TGreatHail", pfs_donor=126, tc_type=0x0A, icon=335,                    # patch_rotaway_v1.py (7 strikes) + patch_threads_v1.py (web attempt per hit, as a Giant Spider web; no damage)
         pokes=[(0x34, 1, 4), (0x35, 1, 0), (0x36, 2, 0x80), (0x39, 1, 0x0C)],                    # v2 ATK 4 (user) = web to-hit, DMG 0 (must stay 0: the web flag rides in the dmg-types high byte), range 12
         desc="A storm of sticky threads rains on the target hex and every hex around it: every unit caught in it may be Webbed, exactly as by a Giant Spider's web (attack 4 against defense to hit, then web strength 4 against resistance). Deals no damage.",
         gfx={0: G.seq_entry("EFFECTS\\DUALDF.ILB", [340], -2, -2, f20=0),                                 # v2: nothing visibly falls
              1: G.seq_entry("EFFECTS\\DUALDF.ILB", [340], -2, -2, f20=0),
              2: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(1630, 1644)), -48, -40, f20=2, f18=1)},   # v2: silk spinning fast round each hex of the area
         sfx=["SFX\\ZSP\\DUALED_THREADS.WAV", ["SFX\\ZSP\\DUALED_THREADHIT.WAV"]]),
]

# ---- Earth/Life (sphere pair 9, ids 300..307; 2026-10-14).  300 Awaken Spirit / 301 Blessing of the Forest = THighPrayer
# clones (patch_earthlife_blessings_v1.py); 302 Golden Age = TEarthMastery clone (patch_goldenage_v1.py: city income
# +25 %); 303 Summon Ent = the existing Ent (unit 282).
SPELLS += [
    dict(id=302, name="Golden Age", sphere=9, tier=3, mana=75, research=150, upkeep=10,
         donor="TEarthMastery", pfs_donor=74, tc_type=None, icon=302,
         pokes=[(0x34, 4, 0xFFFFFFFF)],                                                    # AI priority -1 (as Steam Power / Drought)
         desc="A golden age dawns over your realm: all of your cities produce 25% more gold.",
         gfx={0: G.seq_entry("EFFECTS\\DUALDF.ILB", [1670, 1671, 1672, 1671], -10, -10, f20=0)},   # map-wide gold twinkles
         sfx=["SFX\\ZSP\\DUALEL_GOLDENAGE.WAV"]),
    dict(id=303, name="Summon Ent", sphere=9, tier=4, mana=50, research=250, upkeep=6,
         donor="TSummonMermaid", pfs_donor=211, tc_type=0, icon=303,
         desc="Summons an Ent, an ancient shepherd of the trees, slow to anger and terrible when roused.",
         summon_unit=282),
    dict(id=300, name="Awaken Spirit", sphere=9, tier=1, mana=4, research=40,
         donor="THighPrayer", pfs_donor=112, tc_type=37, icon=300,                    # patch_earthlife_blessings_v1.py: grants 0xB6 Awakened (+1 ATK/DMG/DEF/RES, combat only) to non-hero units of level <= 2
         desc="All friendly creatures of level 2 or lower gain +1 attack, damage, defense and resistance for the rest of the combat.",
         gfx={0: G.seq_entry("EFFECTS\\DUALDF.ILB", [1720, 1721, 1722, 1723], -8, -8),                  # rising spirit motes (High Prayer slot 0)
              1: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(1680, 1696)), -24, -62, f20=2, f18=1)},   # the per-unit aura at the end: spirit wisps spiralling up
         sfx=["SFX\\ZSP\\DUALEL_AWAKEN.WAV"]),
    dict(id=301, name="Blessing of the Forest", sphere=9, tier=2, mana=4, research=80,
         donor="THighPrayer", pfs_donor=112, tc_type=37, icon=301,                    # patch_earthlife_blessings_v1.py: grants 0xB7 Barkskin (+1 DEF/RES, Fire + Lightning Weakness, combat only) to all friendly units
         desc="All friendly units gain Barkskin: +1 defense and resistance, but weakness to fire and lightning, for the rest of the combat.",
         gfx={0: G.seq_entry("EFFECTS\\DUALDF.ILB", [1724, 1725, 1726, 1727], -8, -8),                  # rising leaves (High Prayer slot 0)
              1: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(1700, 1716)), -24, -62, f20=2, f18=1)},   # the per-unit aura at the end: leaves drifting down
         sfx=["SFX\\ZSP\\DUALEL_FOREST.WAV"]),
]


# ---- Earth/Air (sphere pair 17, ids 364..371; 2026-10-14).  364 Summon Mammoth = the Wild Mammoth (unit 265);
# 365 Hurl Boulder = Great Hail clone, ONE strike forced onto the target hex (patch_rotaway_v1.py v4 STRIKES/HN0_IDS);
# 366 Gravity Well = Great Hail clone, 7 strikes (rotaway count table), x1.5 vs flyers + Grounded 0xB8
# (patch_gravitywell_v1.py).
SPELLS += [
    dict(id=364, name="Summon Mammoth", sphere=17, tier=1, mana=8, research=50, upkeep=4,
         donor="TSummonMermaid", pfs_donor=211, tc_type=0, icon=364,
         desc="Summons a Wild Mammoth, a shaggy giant of the frozen plains that tramples all before it.",
         summon_unit=265),
    dict(id=365, name="Hurl Boulder", sphere=17, tier=2, mana=3, research=80,
         donor="TGreatHail", pfs_donor=126, tc_type=2, icon=365,          # v2 10/15 (user: same trajectory/animation as the Hurl Boulder ability): kind 2 = fxComet (Fire Ball / Hurl Boulder class); patch_hurlboulder_v1.py: the ability's lob arc + wall hits
         pokes=[(0x34, 1, 5), (0x35, 1, 8), (0x36, 2, 0x180), (0x38, 1, 1), (0x39, 1, 0x0C), (0x3A, 1, 1)],   # ATK 5 / DMG 8 / Physical+Wall / 1 shot / range 12 / 1 fast-combat target
         desc="Hurls a huge boulder through the air onto the target hex, crushing the unit, wall or structure there (attack 5, damage 8, physical).",
         gfx={0: G.seq_entry("TCOMBAT\\OBJECTS\\BALLS.ILB", list(range(7, 15)), -31, -33, f18=1, f20=6),
              1: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(1820, 1838)), -48, -72, f20=2, f18=1)},   # 10/15 v2: caster magic + the boulder shaking and rising from the ground (patch_hurlboulder_glow_v1.py; 18 x 2 = 36 ticks, launch at tick 30)   # the ability's own rotating boulder (Ability.pfs rec 34 slot 0); DualDF 1726-1743 unused since v2
         sfx=["SFX\\ZSP\\DUALEA_BOULDER.WAV", ["SFX\\ATTACK\\A_PUNCH2.WAV"]]),   # cue 0 = magic start-up + the ability's catapult, cue 1 = the ability's own hit
    dict(id=366, name="Gravity Well", sphere=17, tier=3, mana=5, research=150,
         donor="TGreatHail", pfs_donor=126, tc_type=0x0A, icon=366,
         pokes=[(0x34, 1, 7), (0x35, 1, 2), (0x36, 2, 0x80), (0x39, 1, 0x0C)],                      # ATK 7 / DMG 2 / Physical / range 12
         desc="Crushing gravity seizes the target hex and every hex around it: attack 7, damage 2, physical, +50% against flying, floating and wind-walking units. The well lingers until your next turn: any flying, floating or wind-walking unit inside it is Grounded - it moves as a ground unit and can be hit by Tremors until it leaves the well.",
         gfx={0: G.seq_entry("EFFECTS\DUALDF.ILB", [340], -2, -2, f20=0),                                 # nothing visibly falls
              1: G.seq_entry("EFFECTS\DUALDF.ILB", [340], -2, -2, f20=0),
              2: G.seq_entry("EFFECTS\DUALDF.ILB", list(range(1800, 1820)), -48, -52, f20=2, f18=1),   # v3 10/15: additive glowing purple motes + core flash (96x80)
              3: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(1766, 1778)), -12, 0, f20=2, f18=2)},   # v2: the lingering field loop (patch_gravitywell_field_v1.py)   # contracting rings + grit pulled in, per hex
         sfx=["SFX\ZSP\DUALEA_GRAVITY.WAV", ["SFX\ZSP\DUALEA_GRAVHIT.WAV"]]),
]

# ---- Earth/Water (sphere pair 19, ids 380..387; 2026-10-15).  380 Slow (fixed, patch_slow_v1.py) / 381 Summon Crocodile /
# 382 Swampwalk = Water Walking clone, ability 0xBA implies Forestry/Swimming/Poison Immunity (patch_swampwalk_v1.py) /
# 383 Overgrowth = Air Mastery clone, NewTurn grows forest (patch_overgrowth_v1.py).
SPELLS += [
    dict(id=380, name="Slow", sphere=19, tier=1, mana=3, research=30,
         donor="TSlow", pfs_donor=120, tc_type=7, icon=380,            # patch_slow_v1.py: grants 0xB9 Slowed (combat move allowance halved each turn; vanilla 0x84 only bumped strategic move costs)
         pokes=[(0x39, 1, 0xFF)],                                       # infinite range (Ooze-style 0xFF); strength 9 vs RES inherited
         desc="Slows the target unit: its movement is halved for the rest of the combat.",
         gfx={0: _pfs_slot(120, 0, VANILLA_PFS)},                                  # 10/15 (user: vanilla gfx/sfx/icon): vanilla Slow's TWINKGR 190-198 (live record 120 is Hunter's Mark now)
         sfx=["SFX\\ATTACK\\MAGIC02.WAV"]),
    dict(id=381, name="Summon Crocodile", sphere=19, tier=2, mana=6, research=70, upkeep=3,
         donor="TSummonMermaid", pfs_donor=211, tc_type=0, icon=381,
         desc="Summons a Crocodile, a patient predator of rivers and swamps.",
         summon_unit=283),
    dict(id=382, name="Swampwalk", sphere=19, tier=3, mana=3, research=130, upkeep=2,
         donor="TWaterWalking", pfs_donor=52, tc_type=7, icon=382,          # tc_type 7 like the donor (castable on a unit in combat too)
         desc="Enchants a unit with the ways of the swamp: it gains Forestry, Swimming and Poison Immunity while the enchantment lasts.",
         gfx={0: _emblem_slot(52, 0, 2786, VANILLA_PFS)},   # 10/16 (user): its OWN icon glowing (Water Walking's chain, our emblem DualDF 2786-2790)
         sfx=["SFX\\ZSP\\DUALEW_SWAMPWALK.WAV"]),   # 10/15: custom swamp sound (user)
    dict(id=383, name="Overgrowth", sphere=19, tier=4, mana=75, research=250, upkeep=8,
         donor="TAirMastery", pfs_donor=70, tc_type=None, icon=383,          # patch_overgrowth_v1.py: marker [ench+0x14]=383, Air Mastery side effects stubbed, NewTurn grows forest
         pokes=[(0x34, 4, 0xFFFFFFFF)],                                      # AI priority -1 (as Drought / Golden Age)
         desc="Wild, dense forest slowly spreads across the land: each turn existing forests creep outward and new groves sprout on open grassland, steppe, snow and wasteland. Deserts, hills, roads and settlements are spared. When the spell ends, the new forest slowly recedes.",
         gfx={0: G.seq_entry("EFFECTS\\DUALDF.ILB", [1840], -100, -58, f20=0),
              1: G.seq_entry("EFFECTS\\DUALDF.ILB", [1841], -98, -54, f20=0),
              2: G.seq_entry("EFFECTS\\DUALDF.ILB", [1842], -96, -58, f20=0),
              3: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(1860, 1872)), -16, -14, f20=0)},   # 10/15: subtle green glow on overgrown hexes (patch_drought_glow_v1.py v2)
         sfx=["SFX\\ZSP\\DUALEW_OVERGROWTH.WAV"]),
]

# ---- Life/Water (sphere pair 12, ids 324..331; 2026-10-15).  324 Holy Water / 325 Bountiful Harvest (TLifeMastery,
# patch_harvest_v1.py) / 326 Blessed Dew (TDeathMastery, patch_blesseddew_v1.py) / 327 World Healer (TAirMastery shared
# with Overgrowth, patch_overgrowth_v1.py v3).
SPELLS += [
    dict(id=324, name="Holy Water", sphere=12, tier=1, mana=3, research=40,
         donor="TColdBreath", pfs_donor=118, tc_type=5, icon=324,          # class 5 = breath cone (vanilla Cold Breath); patch_holywater_v1.py: undead hit -> Turned (0x22)
         pokes=[(0x34, 1, 7), (0x35, 1, 3), (0x36, 2, 0x40), (0x3A, 1, 3)], # ATK 7 / DMG 3 / Holy; fast-combat 3 targets; range 4 inherited (short)
         desc="Sprays a short cone of blessed water from the caster: every unit caught in it is struck (attack 7, damage 3, holy), and undead it hits are Turned and cannot act.",
         gfx={0: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(1880, 1888)), -32, -33, f18=1, f20=5)},
         sfx=["SFX\\ZSP\\DUALLW_HOLYWATER.WAV"]),
    dict(id=325, name="Bountiful Harvest", sphere=12, tier=2, mana=40, research=80, upkeep=5,
         donor="TLifeMastery", pfs_donor=71, tc_type=None, icon=325,          # patch_harvest_v1.py: marker 325, Life Mastery side effects stubbed, crops pay 2 gold (vanilla rate) for the caster
         pokes=[(0x34, 4, 0xFFFFFFFF)],                                       # AI priority -1 (as Golden Age)
         desc="The fields of your realm grow heavy with grain: every crop around your cities and farms yields 1 more gold each turn.",
         gfx={0: G.seq_entry("EFFECTS\\DUALDF.ILB", [1960], -100, -58, f20=0),                 # v2 10/15 (user: drift across the map): Death Mastery's map-wide drift (patch_harvest_v1.py v5 id_ cave)
              1: G.seq_entry("EFFECTS\\DUALDF.ILB", [1961], -98, -54, f20=0),
              2: G.seq_entry("EFFECTS\\DUALDF.ILB", [1962], -96, -58, f20=0),
              3: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(1980, 2004)), -16, -14, f20=0)},   # subtle green/gold glow on crop fields (patch_harvest_v1.py v6 cg)
         sfx=["SFX\\ZSP\\DUALLW_HARVEST.WAV"]),
    dict(id=326, name="Blessed Dew", sphere=12, tier=3, mana=50, research=150, upkeep=7,
         donor="TDeathMastery", pfs_donor=72, tc_type=None, icon=326,          # patch_blesseddew_v1.py: marker [ench+0x14]=326, Death Mastery side effects stubbed, +5 HP per turn in TAbstractUnit.NewTurn
         pokes=[(0x34, 4, 0xFFFFFFFF)],                                       # AI priority -1
         desc="A blessed dew settles on your lands each dawn: at the start of each of your turns all your units heal 5 hit points (cursed units excepted).",
         gfx={0: dict(name="EFFECTS\\DUALDF.ILB", f8=0, f18=0, kind=0, f20=1920, xs=-99, ys=-51),
              1: dict(name="EFFECTS\\DUALDF.ILB", f8=0, f18=0, kind=0, f20=1921, xs=-100, ys=-47),
              2: dict(name="EFFECTS\\DUALDF.ILB", f8=0, f18=0, kind=0, f20=1922, xs=-92, ys=-52)},
         sfx=["SFX\\ZSP\\DUALLW_BLESSEDDEW.WAV"]),
    dict(id=327, name="World Healer", sphere=12, tier=4, mana=75, research=250, upkeep=15,
         donor="TAirMastery", pfs_donor=70, tc_type=None, icon=327,          # patch_overgrowth_v1.py v3: marker [ench+0x14]=327, NewTurn turns barren land to grass (permanent)
         pokes=[(0x34, 4, 0xFFFFFFFF)],                                      # AI priority -1
         desc="The land heals: each turn fresh grass spreads from existing meadows and new patches sprout across desert, steppe, wasteland, dirt and snow. Water, ice and lava are untouched. The new grass remains after the spell ends.",
         gfx={0: G.seq_entry("EFFECTS\\DUALDF.ILB", [1940], -100, -58, f20=0),
              1: G.seq_entry("EFFECTS\\DUALDF.ILB", [1941], -98, -54, f20=0),
              2: G.seq_entry("EFFECTS\\DUALDF.ILB", [1942], -96, -58, f20=0)},
         sfx=["SFX\\ZSP\\DUALLW_WORLDHEALER.WAV"]),
]

# ---- Water/Death (sphere pair 16; ids 340..343 because the pair formula collides with Life/Fire's 360s; 2026-10-15).
# 340 Soul Siphon (TDeathRay class 7, patch_soulsiphon_v1.py heals the caster by the damage dealt) / 341 Plague
# (Death Mastery shared with Blessed Dew) / 342 Black Tide / 343 Summon Hydra (unit 264).
SPELLS += [
    dict(id=340, name="Soul Siphon", sphere=16, tier=1, mana=3, research=50,
         donor="TDeathRay", pfs_donor=113, tc_type=7, icon=340,          # class 7 direct, raw id (no alias)
         pokes=[(0x34, 1, 8), (0x35, 1, 4), (0x36, 2, 0x20), (0x39, 1, 8)],  # ATK 8 / DMG 4 / Death / range 8 (medium)
         desc="Rips the life force from a target: attack 8, damage 4, death. The caster is healed by the damage inflicted.",
         gfx={0: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(2010, 2022)), -32, -48, f20=2, f18=1),   # the hit (unchanged)
              1: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(2060, 2090)), -32, -48, f20=2, f18=1),   # lingering vortex at the target (kind-0x26 driver, patch_tc_soulsiphon_fx_v1.py)
              2: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(2022, 2028)), -11, -11, f20=2)},         # soul mote (kind-0x1F, target -> caster)
         sfx=["SFX\\ZSP\\DUALWD_SOULSIPHON.WAV"]),
    dict(id=341, name="Plague", sphere=16, tier=2, mana=40, research=90, upkeep=5,
         donor="TDeathMastery", pfs_donor=72, tc_type=None, icon=341,          # patch_blesseddew_v1.py v3: marker 341 (+ origin/K in the high bits), Death Mastery side effects stubbed
         pokes=[(0x34, 4, 0xFFFFFFFF)],                                       # AI priority -1
         desc="A plague breaks out in the city nearest your leader - your own, an ally's or an enemy's - and spreads to another nearby city each turn: infected cities lose 50% of their income and their people grow restless, and units garrisoned there may take poison damage and be Poisoned at the start of each of their owner's turns, like a Poison Plant. Undead cities are immune. The plague ends when the spell does.",
         gfx={0: dict(name="EFFECTS\\DUALDF.ILB", f8=0, f18=0, kind=0, f20=2030, xs=-99, ys=-51),
              1: dict(name="EFFECTS\\DUALDF.ILB", f8=0, f18=0, kind=0, f20=2031, xs=-100, ys=-47),
              2: dict(name="EFFECTS\\DUALDF.ILB", f8=0, f18=0, kind=0, f20=2032, xs=-92, ys=-52),
              3: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(2090, 2106)), -30, -36, f20=0)},   # 10/15 v2: plagued-city hex glow = the Rot overlay frames re-registered at blend 80 (2090-2105) (patch_city_enchant_ui_v1.py v4, per city hex)
         sfx=["SFX\\ZSP\\DUALWD_PLAGUE.WAV"]),
    dict(id=342, name="Black Tide", sphere=16, tier=3, mana=60, research=150, upkeep=8,
         donor="TEarthMastery", pfs_donor=74, tc_type=None, icon=342,          # patch_goldenage_v1.py v2: marker 342, Earth Mastery side effects stubbed, enemy water move costs x10/7
         pokes=[(0x34, 4, 0xFFFFFFFF)],                                       # AI priority -1
         desc="A black tide fouls the waters of the world: enemy units moving through water lose 30% of their movement there.",
         gfx={0: G.seq_entry("EFFECTS\\DUALDF.ILB", [2050, 2051, 2052, 2051], -10, -10, f20=0)},   # map-wide particles (Earth Mastery fxEMParticle draws slot 0)
         sfx=["SFX\\ZSP\\DUALWD_BLACKTIDE.WAV"]),
    dict(id=343, name="Summon Hydra", sphere=16, tier=4, mana=50, research=250, upkeep=7,
         donor="TSummonMermaid", pfs_donor=211, tc_type=0, icon=343,
         desc="Summons a Hydra, a many-headed serpent of the deep whose heads grow back as fast as they are cut.",
         summon_unit=264),
]

# ---- Water/Air (sphere pair 21, ids 396..399; 2026-10-15).  396 Misty Step / 397 Flashfreeze / 398 Nimue's Favour
# (Earth Mastery shared with Golden Age + Black Tide, patch_goldenage_v1.py v3) / 399 Ice Age (Air Mastery shared with
# Overgrowth + World Healer, patch_overgrowth_v1.py).
SPELLS += [
    dict(id=396, name="Misty Step", sphere=21, tier=1, mana=3, research=40,
         donor="TCallFlames", pfs_donor=212, tc_type=7, icon=396,     # pfs 212 = Void Step's record; patch_mistystep_v1.py routes 396 into Void Step's teleport cave
         pokes=[(0x39, 1, 4)],                                         # range 4
         desc="The caster dissolves into mist and reforms at a hex up to 4 away, passing straight through walls and other obstacles.",
         gfx={0: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(2110, 2122)), -31, -34, f18=1, f20=2)},
         sfx=["SFX\\ZSP\\DUALWA_MISTYSTEP.WAV"]),
    dict(id=397, name="Flashfreeze", sphere=21, tier=2, mana=4, research=90,
         donor="TVaporize", pfs_donor=131, tc_type=7, icon=397,       # class 7 raw id like Blood Boil/Scald; shots byte honoured (TE count = GetCombatInfo shots @0x40B5C0)
         pokes=[(0x34, 1, 7), (0x35, 1, 2), (0x36, 2, 0x02), (0x38, 1, 3), (0x39, 1, 4), (0x3C, 1, 0)],   # ATK 7 / DMG 2 / Cold / 3 strikes / range 4 / roll vs DEF
         desc="A blast of killing frost strikes the target three times: attack 7, damage 2, cold, each strike rolled separately.",
         gfx={0: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(2170, 2178)), -37, -71, f18=1),             # frost burst v3: 8 frames x 2 ticks, peak flash on the last = the hit tick
              1: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(2252, 2276)), -80, -52, f20=2, f18=1),   # v2: shrinking frost ring at the target (patch_tc_flashfreeze_v1.py)
              2: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(2240, 2252)), -37, -71, f18=1)},   # v3 post-hit fade (frost_fade; patch_tc_flashfreeze_v1.py v3 fade driver at landing)
         sfx=["SFX\\ZSP\\DUALWA_FFRING.WAV", ["SFX\\ZSP\\DUALWA_FLASHFREEZE.WAV"]]),                     # cue 0 = ring, cue 1 = each hit
    dict(id=398, name="Nimue's Favour", sphere=21, tier=3, mana=60, research=150, upkeep=8,
         donor="TEarthMastery", pfs_donor=74, tc_type=None, icon=398,          # patch_goldenage_v1.py v3: marker 398, own/allied water move costs floor(c*10/13)
         pokes=[(0x34, 4, 0xFFFFFFFF)],                                       # AI priority -1
         desc="The Lady of the Lake favours your realm: your units and your allies' move 30% farther through water.",
         gfx={0: G.seq_entry("EFFECTS\\DUALDF.ILB", [2130, 2131, 2132, 2131], -10, -10, f20=0)},
         sfx=["SFX\\ZSP\\DUALWA_NIMUE.WAV"]),
    dict(id=399, name="Ice Age", sphere=21, tier=4, mana=75, research=250, upkeep=15,
         donor="TAirMastery", pfs_donor=70, tc_type=None, icon=399,          # patch_overgrowth_v1.py v4: marker 399, NewTurn freezes land to snow / water to ice (permanent)
         pokes=[(0x34, 4, 0xFFFFFFFF)],                                      # AI priority -1
         desc="An age of ice descends: each turn snow spreads across grassland, steppe, wasteland and dirt, and open water freezes to ice, creeping out from existing snow and ice. Deserts, forests, mountains, lava, roads, cities and occupied water are spared. When the spell ends the land slowly thaws back.",
         gfx={0: G.seq_entry("EFFECTS\\DUALDF.ILB", [2150], -100, -58, f20=0),
              1: G.seq_entry("EFFECTS\\DUALDF.ILB", [2151], -98, -54, f20=0),
              2: G.seq_entry("EFFECTS\\DUALDF.ILB", [2152], -96, -58, f20=0),
              3: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(2210, 2222)) + list(range(2210, 2222, 2)), -33, -39, f18=2, f20=0)},   # v5: Freeze Water sparkle on frozen hexes (patch_drought_glow_v1.py v3; vanilla slot 0x46 frame order)
         sfx=["SFX\\ZSP\\DUALWA_ICEAGE.WAV"]),
]

# ---- Air/Death (sphere pair 14, ids 344..347 - the pair's own range; 340..343 are Water/Death's; 2026-10-15).
# 344 Banshee Gale / 346 Borrow Time: engine work in their own scripts (forks).  345 Suffocate = TVaporize clone (class 7
# direct single target - ignores obstructions like Vaporize), 5 strikes.  347 Summon Succubus = the Succubus (unit 229).
SPELLS += [
    dict(id=344, name="Banshee Gale", sphere=14, tier=1, mana=4, research=50,
         donor="TWindsOfFury", pfs_donor=136, tc_type=0x2F, icon=344,
         pokes=[(0x34, 1, 7), (0x35, 1, 1), (0x36, 2, 0xA0), (0x38, 1, 1), (0x39, 1, 0x0C), (0x3A, 1, 5)],   # ATK 7 / DMG 1 / Death|Physical / 1 shot (patch_banshee_v1 sets the real count) / range 12 / fast-combat 5 targets
         desc="A shrieking gale of spirits tears through the area around the target: every unit within two hexes is struck (attack 7, damage 1, death and physical), hurled one or two hexes away and may be panicked.",
         gfx={0: G.seq_entry("EFFECTS\\DUALDF.ILB", [340], -9, -10, f20=2),                              # v3: blank trail (no Winds-of-Fury wisps; 340 = DFnone)
              1: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(2571, 2679)), -112, -92, f20=2, f18=1)},   # v12: 108 frames (rise 36 + 24 + 24 + 24) -> 2571-2678 (2423-2506 unused)  # the spinning gale (patch_tc_banshee_vortex_v1.py)
         sfx=["SFX\\ZSP\\DUALAD_BANSHEE.WAV", ["SFX\\ZSP\\DUALAD_BANSHEEHIT.WAV"]]),
    dict(id=345, name="Suffocate", sphere=14, tier=2, mana=4, research=90,
         donor="TVaporize", pfs_donor=131, tc_type=7, icon=345,
         pokes=[(0x34, 1, 8), (0x35, 1, 1), (0x36, 2, 0x80), (0x38, 1, 5), (0x39, 1, 6), (0x3C, 1, 0)],   # ATK 8 / DMG 1 / Physical (v2, user) / 5 strikes / range 6 (medium) / roll vs DEF; no undead/machines = patch_airdeath_fix_v1.py
         desc="The air is torn from the target's lungs: five choking strikes of attack 8, damage 1, physical, each rolled separately. Walls and obstacles do not stop it. Undead and machines cannot be targeted.",
         gfx={0: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(2555, 2571)), -37, -71, f18=0),             # v6: per-hit gasp of breath (16 ticks, hit on the last frame)
              1: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(2507, 2555)), -80, -70, f20=2, f18=1)},   # whole-cast drain (patch_tc_suffocate_v1.py driver, 96 ticks)
         sfx=["SFX\\ZSP\\DUALAD_SUFFOCATE.WAV"]),            # v2: ONE long cue at the cast (cue 0 = once per cast), no per-hit cue
    dict(id=346, name="Borrow Time", sphere=14, tier=3, mana=6, research=150,
         donor="TRemedy", pfs_donor=45, tc_type=7, icon=346,           # TRemedy range 12 = long; patch_borrowtime_v1.py grants ability 0xBB (Borrowed Time)
         pokes=[(0x22, 1, 0), (0x0C, 1, 2)],                           # COMBAT spell type + combat-only cast context (as Martyr)
         desc="Lends a friendly unit time it does not have: until the end of your next turn no blow can kill it - a killing blow leaves it standing with 1 hit point - but then it dies, or when the battle ends, whichever comes first.",
         gfx={0: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(2303, 2323)), -32, -50, f20=11, f18=4)},   # v5: f18 4 = 100 ticks (~3.3 s: fades out during the final tock); v4 f18 3
         sfx=["SFX\\ZSP\\DUALAD_BORROWTIME.WAV"]),
    dict(id=347, name="Summon Succubus", sphere=14, tier=4, mana=50, research=250, upkeep=8,
         donor="TSummonMermaid", pfs_donor=211, tc_type=0, icon=347,
         desc="Summons a Succubus, a winged temptress of the underworld.",
         summon_unit=229),
]

# ---- Life/Air (sphere pair 10, ids 308..311; 2026-10-16).  308 Heavenly Chorus (High Prayer clone, patch_lifeair_v1.py hx:
# Panicked removed + morale -> High) / 309 Inspiration (Great Hail clone, 7 strikes (patch_rotaway STRIKES), ix: grants
# 0xBC Inspired + 0xB3 Haste) / 310 Second Wind / 311 Angel Wings.
SPELLS += [
    dict(id=308, name="Heavenly Chorus", sphere=10, tier=1, mana=3, research=40,
         donor="THighPrayer", pfs_donor=112, tc_type=37, icon=308,
         desc="A heavenly chorus rings across the battlefield: every friendly unit is freed from panic and its morale rises to High.",
         gfx={0: G.seq_entry("EFFECTS\\DUALDF.ILB", [2679, 2680, 2681, 2682], -8, -8),
              1: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(2815, 2845)), -24, -62, f20=2, f18=1)},
         sfx=["SFX\\ZSP\\DUALLA_CHORUS.WAV"]),
    dict(id=309, name="Inspiration", sphere=10, tier=2, mana=4, research=90,
         donor="TGreatHail", pfs_donor=126, tc_type=0x0A, icon=309,
         pokes=[(0x34, 1, 0), (0x35, 1, 0), (0x36, 2, 0), (0x39, 1, 0x0C), (0x3B, 1, 3)],   # ATK 0 / DMG 0 (must stay 0) / v2: no damage type (no 'holy' preview) / range 12 / v2: own units + enemies targetable
         desc="A rousing light falls on the target hex and every hex around it: friendly units there (not machines) are Inspired (+1 resistance, Fearless) and Hastened for the rest of the combat.",
         gfx={0: G.seq_entry("EFFECTS\\DUALDF.ILB", [340], -2, -2, f20=0),
              1: G.seq_entry("EFFECTS\\DUALDF.ILB", [340], -2, -2, f20=0),
              2: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(2770, 2786)), -48, -40, f20=2, f18=1)},
         sfx=["SFX\\ZSP\\DUALLA_INSPIRE.WAV", ["SFX\\ZSP\\DUALLA_INSPHIT.WAV"]]),
    dict(id=310, name="Second Wind", sphere=10, tier=3, mana=6, research=150,
         donor="TRemedy", pfs_donor=45, tc_type=7, icon=310,           # TRemedy range 12 = long; patch_secondwind_v1.py: heal 5 + 50% combat moves
         pokes=[(0x22, 1, 0), (0x0C, 1, 2)],                           # COMBAT spell type + combat-only cast context (as Martyr / Borrow Time)
         desc="A fresh breath of heavenly air fills a friendly unit: it regains 5 hit points and half of its movement.",
         gfx={0: G.seq_entry("EFFECTS\\DUALDF.ILB", list(range(2845, 2885)), -48, -86, f20=11, f18=1)},   # v2: more epic, 96x96
         sfx=["SFX\\ZSP\\DUALLA_SECONDWIND.WAV"]),
    dict(id=311, name="Angel Wings", sphere=10, tier=4, mana=7, research=250, upkeep=5,
         donor="TWaterWalking", pfs_donor=52, tc_type=7, icon=311,     # patch_angelwings_v1.py: ability 0xBD implies Flying, Holy Protection, Lightning/Death/Physical Weakness
         desc="Gives a unit the wings of an angel: it can fly, but becomes weak to fire, lightning, death and physical damage.",
         gfx={0: _emblem_slot(52, 0, 2765, VANILLA_PFS)},   # v2 (user: unit enchantments show their ICON glowing): Water Walking's twinkle chain with OUR emblem (DualDF 2765-2769)
         sfx=["SFX\\ZSP\\DUALLA_ANGELWINGS.WAV"]),
]

ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, addr):
    enc, _ = ks.asm(src, addr)
    return bytes(enc)


# ---- DLL cave --------------------------------------------------------------------------------------------
def build_zone():
    """Table layout per entry (all dwords): cell, create, id, sphere|tier<<8|mana<<16 (packed), research,
    name_ptr (VA of chars, delta-adjusted at run time), summon_unit (0 = none)."""
    data = bytearray()
    names = {}
    for s in SPELLS:
        lit = s["name"].encode("latin1")
        while len(data) % 4: data.append(0)
        data += struct.pack("<ii", -1, len(lit))
        names[s["id"]] = len(data)
        data += lit + b"\0"
    while len(data) % 16: data.append(0)
    tab_off = len(data)
    ENT = 28 + 12 * MAX_POKES
    for s in SPELLS:
        cell, create = DONOR[s["donor"]]
        assert 0 <= s["sphere"] < 256 and 1 <= s["tier"] <= 4 and 0 <= s["mana"] < 256
        data += struct.pack("<IIIIIII", cell, create, s["id"], s["sphere"] | (s["tier"] << 8) | (s["mana"] << 16),
                            s["research"], ZONE + names[s["id"]], s.get("summon_unit", 0))
        pokes = list(s.get("pokes", []))
        assert len(pokes) <= MAX_POKES
        for off, width, val in pokes + [(0, 0, 0)] * (MAX_POKES - len(pokes)):
            assert width in (0, 1, 2, 4) and 0 <= off < 0x100
            data += struct.pack("<III", off, width, val & 0xFFFFFFFF)
    data += struct.pack("<I", 0)                      # terminator (cell == 0)
    while len(data) % 16: data.append(0)
    code_va = ZONE + len(data)
    # cave: call RegisterSpell (displaced), then loop the table.  ebx = delta, ebp = spell control, esi = entry,
    # edi = new spell.  ebx must be restored (= the control) for the caller.
    code = asm("""
        call %#x
        push ebx
        push ebp
        push esi
        push edi
        mov ebp, ebx
        call %#x
        pop ebx
        sub ebx, %#x
        lea esi, [ebx + %#x]
    next:
        mov eax, [esi]
        test eax, eax
        jz done
        add eax, ebx
        mov eax, [eax]
        mov edx, [esi+4]
        add edx, ebx
        mov edi, edx
        xor ecx, ecx
        mov dl, 1
        call edi
        mov edi, eax
        mov eax, [esi+8]
        mov [edi+0x10], eax
        mov eax, [esi+12]
        mov [edi+0x20], al
        mov [edi+0x21], ah
        shr eax, 16
        mov [edi+0x14], eax
        mov eax, [esi+16]
        mov [edi+0x18], eax
        mov edx, [esi+20]
        add edx, ebx
        lea eax, [edi+8]
        call %#x
        mov eax, [esi+24]
        test eax, eax
        jz reg
        mov edx, [edi+0x38]
        mov edx, [edx+4]
        mov [edx], eax
    reg:
        lea edx, [esi+28]
    poke:
        mov ecx, [edx+4]
        test ecx, ecx
        jz pokes_done
        mov eax, [edx+8]
        push edx
        mov edx, [edx]
        cmp ecx, 1
        jne w2
        mov [edi+edx], al
        jmp w_done
    w2:
        cmp ecx, 2
        jne w4
        mov [edi+edx], ax
        jmp w_done
    w4:
        mov [edi+edx], eax
    w_done:
        pop edx
        add edx, 12
        lea eax, [esi+%d]
        cmp edx, eax
        jb poke
    pokes_done:
        mov edx, edi
        mov eax, ebp
        call %#x
        add esi, %d
        jmp next
    done:
        pop edi
        pop esi
        pop ebp
        pop ebx
        ret
    """ % (REGISTERSPELL, code_va + 16, code_va + 16, ZONE + tab_off, LSTRASG, 28 + 12 * MAX_POKES, REGISTERSPELL, ENT), code_va)
    # call(5) + push ebx/ebp/esi/edi(4) + mov ebp,ebx(2) + call next(5) = 16 -> next = code_va+16
    assert code[16:17] == b"\x5b", "delta anchor misplaced"
    zone = bytes(data) + code
    assert ZONE + len(zone) <= ZONE_END
    return zone, code_va


# ---- Spells.pfs ------------------------------------------------------------------------------------------
_ft = None
def ft():
    global _ft
    if _ft is None:
        spec = importlib.util.spec_from_file_location("ft", os.path.join(HERE, "patch_frost_terrain_v1.py"))
        m = importlib.util.module_from_spec(spec); argv = sys.argv; sys.argv = ["x"]; spec.loader.exec_module(m); sys.argv = argv
        _ft = m
    return _ft


def pfs_rebuild(d):
    """Rebuild Spells.pfs: every record NOT owned by SPELLS is kept byte-identical, every owned record (key =
    id+10) is (re)built from its donor with the overrides - so the result is deterministic and idempotent."""
    F = ft()
    assert struct.unpack_from("<I", d, len(d) - 4)[0] == (zlib.crc32(d[4:-4]) & 0xFFFFFFFF), "pfs CRC bad"
    base, ent, recs = F.pfs_records(d)
    ctrl = d[7]; assert ctrl & 0x80, "root index not in wide form"
    ns = ctrl & 0x7F; N = struct.unpack_from("<I", d, 8)[0]
    small_keys = [d[12 + 2 * k] for k in range(ns)]
    assert 12 + 2 * ns + 8 * N == base
    ours = {s["id"] + 10 for s in SPELLS}
    keep = {k: v for k, v in recs.items() if k not in ours}
    for s in SPELLS:
        assert s["pfs_donor"] in keep, "donor record %d missing or owned" % s["pfs_donor"]
    built = {}
    for s in SPELLS:
        body = recs[s["pfs_donor"]]
        dents, dsz = F.body_dir(body)
        fields = F.slice_fields(body, dents, dsz)
        f = dict((t, bytearray(v)) for t, v in fields.items())
        desc = s["desc"].encode("latin1") + b"\r\n"
        f[0xA] = bytearray(struct.pack("<I", len(desc)) + desc)
        f[0xD] = bytearray(struct.pack("<I", s["mana"]))
        f[0xF] = bytearray(struct.pack("<I", s["research"]))
        f[0x10] = bytearray([s["sphere"]]); f[0x11] = bytearray([s["tier"]])
        if s.get("upkeep") is not None:                   # tag 0xE -> spell+0x1C = enchantment / summon upkeep
            assert 0xE in f, "donor record %d has no tag 0xE to carry the upkeep" % s["pfs_donor"]
            f[0xE] = bytearray(struct.pack("<I", s["upkeep"]))
        if s.get("sfx") is not None:
            f[0xB] = bytearray(G.snd_build(s["sfx"]))
        if s.get("gfx"):
            slots = G.seq_parse(bytes(f[0xC]))
            for k, e in s["gfx"].items():
                assert slots[k] is None or slots[k]["kind"] in (4, 5) or slots[k]["kind"] == e["kind"], "slot %d of donor %d is not an effect" % (k, s["pfs_donor"])   # 10/15: same-kind swap allowed (Death Mastery's kind-0 drift images)
                slots[k] = e
            f[0xC] = bytearray(G.seq_build(slots))
        if s.get("icon") is not None:
            slots = G.seq_parse(bytes(f[0xC]))
            ic = [x for x in slots if x and x["name"].upper() == "SPELLICN.ILB"]
            assert len(ic) == 1 and ic[0]["kind"] == 0
            ic[0]["f20"] = s["icon"]
            f[0xC] = bytearray(G.seq_build(slots))
        order = [t for t, _o, _w in sorted(dents, key=lambda e: e[1])]
        # body directory: byte pairs while offsets fit, dword pairs after
        offs, o = {}, 0
        for t in order:
            offs[t] = o; o += len(f[t])
        bp = [(t, offs[t]) for t in order if offs[t] <= 255]
        wp = [(t, offs[t]) for t in order if offs[t] > 255]
        rec = bytes([0x80 | len(bp)]) + struct.pack("<I", len(wp))
        for t, o in bp: rec += bytes([t, o])
        for t, o in wp: rec += struct.pack("<II", t, o)
        for t in order: rec += bytes(f[t])
        built[s["id"] + 10] = rec
    allrecs = dict(keep); allrecs.update(built)
    # lay records out in key order (small-index keys first so their offsets stay < 256), rebuild the root
    keys = sorted(allrecs, key=lambda k: (0 if k in small_keys else 1, k))
    recblob = bytearray(); offs = {}
    for k in keys:
        offs[k] = len(recblob); recblob += allrecs[k]
    small = [(k, offs[k]) for k in keys if k in small_keys]
    assert all(o < 256 for _k, o in small)
    wide = [(k, offs[k]) for k in keys if k not in small_keys]
    root = bytes([0x80 | len(small)]) + struct.pack("<I", len(wide))
    for t, o in small: root += bytes([t, o])
    for t, o in wide: root += struct.pack("<II", t, o)
    body = bytes(d[:7]) + root + bytes(recblob)
    out = body + struct.pack("<I", zlib.crc32(body[4:]) & 0xFFFFFFFF)
    b2, e2, r2 = F.pfs_records(out)
    assert set(r2) == set(allrecs)
    for k in keep:
        assert r2[k] == keep[k], "kept record %d changed" % k
    for s in SPELLS:
        rb = r2[s["id"] + 10]; de, ds = F.body_dir(rb); ff = F.slice_fields(rb, de, ds)
        assert ff[0x10][0] == s["sphere"] and ff[0x11][0] == s["tier"] and struct.unpack_from("<I", ff[0xD])[0] == s["mana"]
        if s.get("upkeep") is not None: assert struct.unpack_from("<I", ff[0xE])[0] == s["upkeep"]
    return out


# ---- helpers -----------------------------------------------------------------------------------------------
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


def write_inplace(path, data):
    with open(path, "r+b") as f:
        f.seek(0); f.write(data); f.truncate(len(data))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", default=GAME)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    dll = os.path.join(a.game, "AoWEPACK.dll"); tc = os.path.join(a.game, "AoWTCPCK.dll"); pfs = os.path.join(a.game, "Release", "Spells.pfs")
    if a.revert:
        for f in (dll, tc, pfs):
            b = bak_path(f, BAK_SUFFIX, create=False)
            if os.path.exists(b): shutil.copy2(b, f); print("restored", f)
            else: print("no backup for", f)
        return 0

    d = open(dll, "rb").read()
    zone, code_va = build_zone()
    hook = b"\xe8" + struct.pack("<i", code_va - (H_SITE + 5))
    site = d[H_SITE - CODE_V2F:H_SITE - CODE_V2F + 5]
    zl = d[ZONE - CODE_V2F:ZONE - CODE_V2F + len(zone)]
    rl = reloc_set(d)
    bad = [r for r in rl if ZONE <= r < ZONE + len(zone) or H_SITE <= r < H_SITE + 5]
    print("dll: site %s | zone %s | relocs %s | cave code @%#x, zone %d B"
          % ("vanilla" if site == H_OLD else "applied" if site == hook else "OTHER(%s)" % site.hex(),
             "zero" if not any(zl) else "ours" if zl == zone else "FOREIGN", bad or "none", code_va, len(zone)))
    if bad: return 1
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        for i in md.disasm(zone[code_va - ZONE:], code_va): print("   %08X  %-18s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    tgt = H_SITE + 5 + struct.unpack_from("<i", site, 1)[0] if site[0] == 0xE8 else None
    ours = tgt is not None and ZONE <= tgt < ZONE_END                                                     # hook into our zone
    ours_old = tgt is not None and any(lo <= tgt < hi for lo, hi in OLD_ZONES)                            # hook into a former home
    if ours_old: print("dll: hook points into a FORMER zone %#x -> moving the zone to %#x and zeroing the old one" % (tgt, ZONE)); ours = True
    dll_applied = site == hook and zl == zone
    if not (site == H_OLD or ours) or (any(zl) and zl != zone and not ours):
        print("ABORT: dll not in an expected state"); return 1
    if ours and not dll_applied:
        print("dll: zone owned by this script differs from the current build -> re-sync (table/code changed)")
    new_dll = bytearray(d)
    if ours:
        new_dll[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)   # clear our old layout first (2026-10-14: a 2nd `new_dll = bytearray(d)` used to undo this)
    if ours_old:
        for lo, hi in OLD_ZONES: new_dll[lo - CODE_V2F:hi - CODE_V2F] = bytes(hi - lo)
    new_dll[ZONE - CODE_V2F:ZONE - CODE_V2F + len(zone)] = zone
    new_dll[H_SITE - CODE_V2F:H_SITE - CODE_V2F + 5] = hook

    t = open(tc, "rb").read()
    new_tc = bytearray(t)
    for s in SPELLS:
        if s["tc_type"] is not None:
            new_tc[TC_TABLE_FILE + s["id"]] = s["tc_type"]
    assert t[TC_TABLE_FILE:TC_TABLE_FILE + 131] == new_tc[TC_TABLE_FILE:TC_TABLE_FILE + 131]
    print("tc: SpellTypes bytes: " + ", ".join("[%d]=%d" % (s["id"], new_tc[TC_TABLE_FILE + s["id"]]) for s in SPELLS)
          + (" (unchanged)" if bytes(new_tc) == t else ""))

    p = open(pfs, "rb").read()
    F = ft(); _b, _e, recs = F.pfs_records(p)
    new_pfs = pfs_rebuild(p)
    pfs_applied = new_pfs == p
    print("pfs: %s (%d -> %d B, %d records)" % ("up to date" if pfs_applied else "rebuilding %d owned records" % len(SPELLS), len(p), len(new_pfs), len(F.pfs_records(new_pfs)[2])))

    if dll_applied and bytes(new_tc) == t and pfs_applied:
        print("already applied"); return 0
    if not a.apply:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    for f, cur, new in ((dll, d, bytes(new_dll)), (tc, t, bytes(new_tc)), (pfs, p, new_pfs)):
        if cur == new: continue
        b = bak_path(f, BAK_SUFFIX)
        if not os.path.exists(b): shutil.copy2(f, b); print("backup ->", b)
        if len(new) == len(cur): write_inplace(f, new)
        else:
            with open(f, "wb") as fh: fh.write(new)
        assert open(f, "rb").read() == new
        print("written", f)
    return 0


if __name__ == "__main__":
    sys.exit(main())
