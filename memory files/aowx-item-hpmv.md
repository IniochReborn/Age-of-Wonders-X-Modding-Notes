---
name: aowx-item-hpmv
description: "Items grant HP/MV and \"Use\" items grant stats from the backpack (2026-09-12) — TItem fields/tags, hero stat-getter hook sites, item library (.PFS/.ail) tagged-container layout, tools"
metadata: 
  node_type: memory
  type: project
  originSessionId: 2eb9e75f-d259-4a21-8f8a-bfb22139df71
  modified: 2026-09-13T02:54:06.025Z
---

**Feature (applied to the 410 prerelease dll 2026-09-12, `patch scripts\patch_item_hpmv_use_v1.py`,
backup `.bak_item_hpmv`, caves 0x55813610–0x55813909):** ported from BXL's Ziggurat (Sept 2026 dpl,
he marked it untested) + Inioch's rule: worn items count; backpack items count ONLY if Use type.

- **TItem** (VMT 0x5570FAFC, size 0x4C): +0x46 atk, +0x47 def, +0x48 dam, +0x49 res (tags 0x0B–0x0E),
  **+0x4A HP (tag 0x17), +0x4B MV (tag 0x18)** — same tags as BXL so item libraries interchange.
  +0x34 item type byte (0 head, 1 torso, 2 attack, 3 defense, 4 ring, 6 = Use). TItem.ReadWrite
  0x557945C8 (VMT+0x18) hooked at its tail 0x55794712; it also backs EngineP `TEObject.Assign/Copy`
  (write-to-memstream + read-back), so UpdateFromLibrary/maps/saves/libraries all carry the tags.
  The writer omits zero-valued byte tags.
- **THero** (parent TAbstractUnit, NOT TUnit): +0x40 template (+0x24..+0x29 base atk/def/dam/hits/moves/res),
  +0x6A..+0x6F own bonus bytes, +0x70 THeroItems (worn), +0x74 THeroInventory (backpack). Getters:
  VMT+0xC0 GetAttack 0x55788360, +0xC4 GetDefense 0x557883E8, +0xC8 GetDamage 0x55788484,
  +0xCC GetResistance 0x5578850C (each: ability modifiers loop → THeroItems.GetTotalX → own bonus →
  clamp 1..50), **+0xD0 GetHits 0x5578859C, +0xD4 GetMoves 0x557885C0** (template+own, clamp 1..50;
  now → stubs adding item sums, jmp back to the clamp tail 0x557885A5/0x557885C9). +0xA8..+0xB4 =
  base-without-items getters. TLeader inherits all.
- **THeroItems helpers** (eax=container; [container+4] = carrying hero): GetTotalAttack 0x55786354,
  Defense 0x55786388, Damage 0x557863BC, Resistance 0x557863F0 (sum byte over items via count
  [vmt+0x54], TList [cont+8], array [list+4]); flag ORs 0x55786424 (per-item 0x5574F764 → byte),
  0x55786470 (0x5574FADC → word), 0x557864C0 (0x5574F97C → word) = movement/terrain/immunity
  flags derived from item abilities (used by THero VMT+0xE8/+0xEC/+0xF0). All seven now = stubs →
  cave_total(worn, [hero+0x74] filtered type 6, callback). Estimators untouched.
- **Item library format** (Release\ITEMS.PFS, User\*.ail = same TAoWDir container as .CAM, see
  [[cam-campaign-format]]): root magic 3 B `01 00 00`, fields 0x15 int32, 0x01 = item list (0-byte
  magic; ids = index; short entries for the first 3, long for the rest); each item = record with
  4-byte magic `68 02 02 00` and TItem.ReadWrite tags. ⚠ Records with ability DATA records have
  TWO interleaved tables: short table = writer order (2, 3, 0x31 ability-id list, 7, 8, ...), long
  table = per-ability records keyed by ability id (ids ≥ 0x80 → long form) whose payload sits
  between field 0x31 and field 7 — entry lengths must come from offsets sorted across BOTH tables
  (camcodec's "next table entry" rule is wrong there). `patch scripts\set_item_hpmv.py`
  (list/set/check; byte-identical round trip verified on ITEMS.PFS + both .ail) authors HP/MV —
  the editor (HSEPack item dialog) has no fields for them.
- Verified: startup with a modified library → live TItem objects show HP=3/MV=-1 (dll rebased
  0xD60000), probe `patch scripts\item_hpmv_probe.py`. NOT yet play-tested: current-HP behaviour when
  a +HP item is equipped/removed (max changes, current does not), MV refill next turn.

**In-game item popup (2026-09-13, `patch scripts\patch_aowx_item_banner_hpmv.py`, backup AoWx.exe `.bak_itembanner`, section `.xibn` @0x60F000, SizeOfImage 0x20F000→0x212000):** the popup is **TItemBanner** (unit AoWItemBanner, a DFM data module: RCDATA TITEMBANNER 7411 B, res data entry @file 0x72f70; VMT 0x406950, field table @0x406978 (13 fields, class table @0x406aa0: idx0 TAOWLabel, idx2 TAOWImage), instance 0x78). Icons = TAOWImage ImageLib IntGfxMod.UnitIcons (Int\Icons.ILB ids 0 atk,1 def,2 dam,3 res,4 hits; 15x17) — the unit banner's MovesIcon is IntGfxMod.MoveIcons #16 (32x17). IBannerPopupShow 0x406AE8 (OnShow) lays stats out: icon.Left=esi+10, label.Left=esi+30, esi 30→80→wrap (row +20). Technique that WORKED: extended DFM (cloned AttackIcon/Attack → HitsIcon/Hits/MovesIcon/Moves before DrawBox) placed in the new section with the **resource data entry repointed** (any RVA works for LoadResource), **field table copied+4 entries and VMT-44 repointed, VMT-28 instance size 0x78→0x88** so the DFM reader fills the new fields by name; cave hooked @0x406D7D. Verified live: TItemBanner instance has all 4 new fields populated at startup. `patch scripts\item_banner_probe.py` scans for it.
**Item popup layout facts (final, 2026-09-13, user-approved):** IBannerPopupShow: stats start [ebp-8]=100 (now 94, imm @0x406B91), icon.Left=esi+10 / label.Left=esi+30 / label.Top=top+5, vanilla 2 columns (esi 30,80; pitch 50; wrap 130) via inline 20-byte sequences @0x406BFB/0x406C75/0x406CEF/0x406D69 (now `call adv` in .xibn; row pitch 18); a `setup` cave at 0x406B89 counts non-zero stats: >4 → compact 3-column grid (start 12, pitch 40, wrap 132). Then list TopOffset = statsBottom+10 (now +4, imm @0x406D99), popup height = statsBottom + 50 (now 36, imm @0x406E16) + 10×abilities, **clamped to 200 @0x406E24/0x406E30** (the popup DFM WinHeight and any SetHeight in OnShow are overridden by this). AbLB is ahBoth with BottomOffset 24 (now 16 in the relocated DFM); its scrollbar follows it. **Wheel-scroll crash root cause:** two stat rows + the 200 cap left the list 26 px → TAOWListBox.Update repaint → AV in ILPACK TRLESprite16.GrabImage (+0x10DFA/+0x10E21); the process dies WITHOUT any VEH/first-chance dispatch (only WER logs module+offset) — a VEH logger is useless for this class; measure geometry live instead (item_banner_probe.py --pid N --keep prints popup/list/scrollbar left/top/width/height). MovesIcon = IconMove.ILB #0 (foot at x 8..17 of a 32-wide frame; UnitIcons art starts x=2 → icon.Left shift −6; Masked must be True). A taller popup (cap 240) fixed the crash but the user rejected it ("weird behaviour"); the tightened spacing was accepted.

**Editor icons (v2 of patch_devx_item_hpmv_ui.py):** TITEMEDITFORM DFM relocated to section `.xdfm` @0x4E6000 (res data entry @file 0x434e0 repointed) with two TImage components (assets\item_hp_icon.bmp heart 16x16 / item_mv_icon.bmp boot 32x15 — both lifted from the THEROEDITFORM DFM Image11/Image12; the editor's 4 stat icons are 16x16 24-bpp BMPs on (191,191,191)); Movement label at x=38 because of the wide boot.

**Why:** the item/hero stat plumbing is spread over seven helpers plus two getters; any later item
stat feature (or a DevEd item-dialog patch for HP/MV) starts from these sites.

**How to apply:** new item-carried values → add a TItem byte + ReadWrite tag (next free 0x19) and a
callback for cave_total; keep the type-6 rule for backpack items. Related: [[aowepack-ability-system]].


**Negative ATK/DEF/DMG/RES on items (2026-09-21, `patch scripts\patch_devx_item_negative_stats.py`, backup AoWDevX.exe `.bak_itemneg`, APPLIED, editor-untested):** the game side was already signed (dialog loader movsx @0x413377.., OnChange handlers 0x413A7C/0x413AA4/0x413ACC/0x413AF4 `bound -128..127` then store AL, THeroItems totals sum signed bytes, hero getters clamp 1..50); only the DFM MinValue 0 of the four TSpin controls blocked it. Live TITEMEDITFORM DFM in `.xdfm` @0x4E6000: MinValue vaInt8 0 → -10 for AttackEdit/DefenseEdit/ResistanceEdit/DamageEdit (MaxValue stays 10). ⚠ patch_devx_item_hpmv_ui.py rebuilds .xdfm → re-run this after it. Item libraries authored with negatives need no format change (tags 0x0B-0x0E are bytes).
