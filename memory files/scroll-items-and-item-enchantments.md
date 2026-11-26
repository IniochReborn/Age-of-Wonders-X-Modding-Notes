---
name: scroll-items-and-item-enchantments
description: "2026-10-30 scroll items grant up to 7 spells to the holding hero's spell book (+ description lines, editor 7 pickers, Use disabled) and enchantment abilities on items no longer crash; 5 scripts APPLIED untested; AI does not use scroll spells yet"
metadata:
  node_type: memory
  type: project
  originSessionId: 68556280-d707-4a00-a5ee-7f75589fbb89
  modified: 2026-10-31T01:41:57.176Z
---

**Scrolls (TItemType itScroll=5).** Vanilla: spell 1 = dword [item+0x38] (tag 0x14); TItem.ExecuteUse 0x55793F68 taught it to the whole PLAYER and destroyed the scroll (CanUse 0x557940AC gate). New design (user 10/30): held in the backpack [hero+0x74] → only that hero can cast its spells; up to 7; description lists real spells only.
- `patch_scroll_spells_store_v1.py` (AoWEPACK, zone 0x55848000): TItem instance 0x4C→0x64; slots 2..7 = dwords [item+0x4C+4k] storing **id+1 (0=None)** (spell id 0 may be real); tags 0x19..0x1E chained off the item-hpmv RW cave tail jmp @0x55813904.
- `patch_exe_scroll_spells_v1.py` (AoWx.exe .xtut 0x638C00–0x639000): 5 ListSpells sites (0x42F0F9/0x42F20C/0x430D58/0x430DDE/0x430EDD, ebx=TSpellBook, caster [book+0x22C] valid iff [book+0x230]≠0) append the caster's scroll spells (type-set filter, dedupe, TList.Add IAT 0x45D4D8); TItemBanner @0x406DF7 adds "Spell: <name>" lines.
- `patch_devx_scroll_spells_v1.py` (AoWDevX): TITEMEDITFORM DFM (.xdfm) +6 TComboBox Sp2..Sp7 (grid 2 cols), SpellComboBox width 177; FormCreate entry (fo 0x12489, chained to hpmv wrapper 0x4E519F) fills "None"+spells; load @0x4135FF, save @0x4138D3; code in .xthm 0x4E4000 (⚠ reverted dark theme's section — never re-apply build_editor_dark_theme.py). DFM slack left 0xC.
- `patch_scroll_nouse_v1.py`: CanUse @0x557940DF je→jmp (scrolls never "Use").
- RE (spellbook agent): logic never checks "known" on cast (CanCastSpellInstantly/CastSpell/CastCombatSpell/TSpellTE.Validate) → UI-only lists. **AI DONE 10/30 `patch_ai_scroll_spells_v1.py`** (AoWEPACK 0x55848400–0x55848800 strategic ListSpells wrap + fast-combat pre-loop; AoWTCPCK 0x454000–0x454400 4 IndexOf stubs; .bak_aiscroll) — sites: TCAI.EvalBattle IndexOf sites AoWTCPCK 0x418796/0x418BE3/0x418FBE/0x419631, fast combat fcPrefetchCombatCommands loop 0x5576E3CE, strategic TCastSpellAIPA ListSpells 0x5577BA86. Multi-turn casts continue if the scroll is dropped.

**Enchantment abilities on items** — `patch_item_enchant_abilities_v1.py` (AoWEPACK zone 0x55848100–0x55848400): TUnitEnchantmentAbility (VMT 0x55722364) state = per-unit data record (+0x10 TUnitEnchantment) created only by Expand; items have bits only → unit paths gated by VMT+0x148 (item-inclusive) then deref nil record. Fix: 8 gates (Register 0x5577F2DC, Unregister 0x5577F368, GetFace 0x557887E8, Summoned 0x5577FC9C, masteries 0x55780968/A1C/ABC/D1C) + 8 ValidTargetUnit own-id checks (Bless/DarkGift/EnchantWeapon/FreeMovement/Fury/Haste/LiquidForm/StoneSkin) 0x148→0x4C (own bits); GetSourceName nil → item name ([item+0x18]) via owner-finder VMT+0x154; Blessed/StoneSkin/FireProtection overrides nil-safe. Item copy: no TUnitEnchantment → no upkeep, not dispellable.

Next free: AoWEPACK 0x55848C00–0x5584A000; AoWTCPCK 0x454400 (unclaimed 0x452800–0x45C000); AoWx .xtut none left (0x639000 = realm-heroes zone); AoWDevX .xthm 0x4E4400+ (check code end).

**AI scroll DIAG 10/30:** user: AI (leader with Spell Casting, mixed vanilla/custom spells of all types) never cast scroll spells on map, tactical or auto combat. Static review found no bug → counters added to patch_ai_scroll_spells_v1 caves (DATA slack 0x558E9BD0..0x558E9BEF: ST enter/hero/scroll spell/added, FC enter/hero/unknown scroll spell/cancast) + `patch scriptsi_scroll_probe.py` (live ReadProcessMemory). Awaiting a probe run. Note: TCAI tactical loop skips when the unit's owner byte [unit+0x24] <= 0 (0x418755).

**Probe result 10/30:** ST enter 4 / hero 4 / scroll spell 0; FC enter 6 / hero 6 / 0 → caves run, hero OK, but NO scroll spells found in [hero+0x74] → next: `hero_inventory_probe.py` (scans live memory for THero/TLeader VMTs, dumps worn/pack items, type, spell slots) with the user's save loaded. Also `patch_ai_pickup_scrolls_v1.py` (AI loot use-pass + targeting type test 6→5/jb: scrolls picked up like use items; was only 1 via engine AutoPlaceItem) APPLIED.

**Editor enchant-on-item error (10/30):** AoWDevX TAbilitySelectionDlg Add 0x410690 → item VMT+0x94 ExpandAbility → TUnitEnchantmentAbility.Expand 0x55765894 asserts owner IsClass TAbstractUnit. `patch_item_enchant_expand_v1.py` (zone 0x55848C00–0x55848C80): non-unit owner → TAbility.Expand 0x5574E90C (just SetAb). Remove already nil-safe. APPLIED untested. Next free AoWEPACK 0x55848C80.
