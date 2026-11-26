---
name: realm-heroes-tab-columns
description: "10/22 static RE + patch design for adding \"Turn Met\" and \"Experience\" columns to the Realm window Heroes tab (TRealmWin DFM in AoWx.exe, hero XP fields, new streamed THero word for turn joined); NOTHING applied"
metadata:
  node_type: memory
  type: project
  originSessionId: 511f9df3-964c-401e-b2ff-e5d99b017377
  modified: 2026-10-22T07:26:33.998Z
---

User request (10/22, for 422): Heroes tab columns Name | Turn Met | Health | Experience (cur/next, e.g. 10/15) | Level. Research only, nothing applied.

**UI = AoWx.exe TRealmWin** (a Delphi form; DFM = RCDATA "TREALMWIN", 57,682 B; parser in the session scratchpad, dfm.py).
- VMT is 0x4484F0. Delphi 3 layout: SelfPtr -0x40, FieldTable -0x2C = 0x448518, MethodTable -0x28 = 0x4489F5, ClassName -0x20, InstanceSize -0x1C = 0x19C.
- The field table is immediately followed by the method table, which is immediately followed by the class name. There is no slack.
- Field class table 0x448E5B: idx 6 = TAOWListBox, idx 5 = TAOWButton (refs are IAT cells).
- Heroes tab controls (all inside panel T5LBFr: x=70, w=354; rows 17 px, Age10 font; headers are TAOWButton, Age8 font, GenericB 85/88/91):
  - T5Name +0x110: x0, w230, awBoth, RightOffset 124.
  - T5Health +0x114: x229, w72, awRight, RO 53, taCenter.
  - T5Level +0x118: x300, w54, awRight, RO 0. Owns VScrollBar = HeroSB +0x134 (x337, 4 rows).
  - Headers T5SName +0x11C, T5SHealth +0x120, T5SLevel +0x124. Their texts come from the DFM ("Hero Name", "Health", "Level").
  - TIvTranslator "Translator" (DictionaryName 'AoW') translates the Text, Items and ToolTipText properties.
- Methods:
  - Fill routine 0x449894: clears the 3 Items (vcall +0x40). It walks the local player's armies → units with IsClass THero (so leaders are included). Per hero:
    - T5Name.Items.AddObject(GetName vcall +0xF8, army)
    - T5Health.AddObject("hp/max" built from +0xE0, '/' and +0xD0, hero)
    - T5Level.Add(IntToStr(THero.GetLevel thunk 0x40270C)) @0x449A92
    - Then SetIndex(0) and HeroListChange.
  - HeroListChange 0x44B100: SetIndex (0x40365C) on all 3.
  - HeroVSBChange 0x44B13C: SetListOff (0x403664) on [self+0xC8], which is **T3Name** (the places list, likely a vanilla bug), plus T5Health and T5Level. T5Name is not scrolled → names may misalign with 5+ heroes. LIVE CHECK.
  - Sort clicks: T5SNameClick 0x44B2B8 (mode 0), T5SHealthClick 0x44B318 (mode 1), T5SLevelClick 0x44B378 (mode 2). Each builds a TList (0x401058, class [0x45D4E8]) of [key, others…] via TList.Add 0x4014B4, then calls sort 0x455744(mgr [[0x45A420]], &list, cl=mode).
    - Modes 0/1 compare strings; 2/3 compare StrToInt numerically. "10/15" fails StrToInt and is skipped.
    - The sort permutes the other lists with TStrings.Move (vcall +0x60).
  - The portrait draw T5HeroInfDraw 0x44B188 uses T5Health.Objects[sel] = hero.
- Section table FULL: 13 sections, the table ends at 0x400 = SizeOfHeaders. Grow the last section, **.xtut** (0x634000, raw 0x4400 / v 0x5000), as earlier patches did.

**XP:**
- THero experience = dword [hero+0x48]. Level = ExperienceToLevel. Byte [hero+0x4C] is the stored level.
- Virtual slots (TAbstractUnit, THero, TLeader): GetExperience +0x15C, SetExperience +0x160, GetNextLevelExperience +0x164.
- THero.GetNextLevelExperience 0x5578770C returns the CUMULATIVE XP of the next level. At max level it returns LevelToExperience(current level) ≤ cur, so test next<=cur → show "Max".
- Max level = 50, or the map's [[map+0x18C]+0x18] (0x55787628).
- Table HeroExperienceTable 0x558E84B4 (dword pairs; value at +4): 15 / 30 / 50 / 75 / 100 / 250 per level for the decades 1-9 / 10-19 / … / 50. Cumulative: L2=15, L3=30, …, L10=135, L11=165.
- The exe does not import GetExperience → use the vcalls.

**Turn met: no existing per-hero data** (only the per-player TPlayer.ResetBaseHeroJoinDay). Design: a new word at **THero+0x9A**.
- 0x99–0x9B are unused in all of AoWEPACK, the exe, TCPCK and HSEPack (byte 0x98 is used; TLeader fields start at 0x9C). Zero-initialised.
- Stream it with a NEW tag via rwWord (stream vcall +0x34).
  - Enginep TEReadStorageStream.rwWord 0x55510FE4 writes 0 for a missing tag, so old saves load as 0.
  - The writer 0x555101D0 skips zero values.
  - A duplicate tag hits a writer check (0x5550FE48 → 0x5551009C), so pick an unused tag. Used tags: 4,5,6,7–0x1B,0x1D–0x1F,0x21–0x27,0x2D (TLeader),0x2F,0x30, plus TAbilityOwner's. Suggest **0x60**.
- Hooks (AoWEPACK; zone not yet chosen; 0x55833100+ was free on 10/21, so re-scan the scripts' claims):
  - (a) THero.ReadWrite @0x55788B02 `8D5750 B927000000` (8 B, reloc-free): cave does rwWord(&[edi+0x9A], 0x60), replays the 2 instructions, jmp 0x55788B0A.
  - (b) THero.SetPlayer 0x557872D0 (VMT +0x16C; it already early-exits when new==old). Hook @0x557872DF `807E24FF 7458` (6 B).
    - If new bl != 0xFF and (word[esi+0x9A]==0 or old [esi+0x24] != 0xFF): store max(1, [map+0x174] turn).
    - The map is the global [0x558FA040]; use the PIC call/pop delta.
    - Replay the cmp/je (je → 0x5578733D).
    - Hire, dungeon, event and quest joins all route through SetPlayer. A resurrect (old 0xFF, field set) keeps the original turn. Death is SetPlayer(-1) → skipped.
    - The owner byte [+0x24] is streamed directly (TAbstractUnit tag 0x2F), so a load should not call SetPlayer. LIVE CHECK.
  - Map-placed heroes, leaders and old saves read 0 → display "1".
  - Deterministic: the turn counter is synced and SetPlayer runs inside synced TEs, so the field is MP-safe. TCompareStorageStream compares it consistently.
- Est. ~120 B of AoWEPACK cave.

**Exe patch design:**
1. Copy the TREALMWIN DFM to the grown .xtut and repoint its resource data entry (OffsetToData RVA + Size). Edit it:
   - shrink T5Name and T5SName (awBoth RightOffset 124 → ~224);
   - move T5Health and T5SHealth (RightOffset → ~117);
   - clone T5Health/T5SHealth raw records as T5Turn, T5STurn, T5Exp and T5SExp with new RightOffset/WinWidth/Text/ToolTip.
   - Suggested widths: Turn 46 / Health 62 / Exp 64 / Level 54 → Name ≈ 130 px. Watch long hero names.
2. InstanceSize 0x19C → 0x1AC. Add a new field table in .xtut: the 86 entries plus T5Turn +0x19C, T5Exp +0x1A0, T5STurn +0x1A4, T5SExp +0x1A8. Point VMT-0x2C at it.
3. For a sortable Turn header: a new method table (the old one plus 'T5STurnClick' → cave sort mode 2). Point VMT-0x28 at it. The Exp header can use OnClick 'T5SLevelClick'.
4. Caves:
   - fill hook @0x449A84 (12 B: `mov eax,[eax+0x118]; mov eax,[eax+0x114]`, ahead of the Level Add) adds the turn and the exp "cur/next" (or "Max");
   - clear hook ~0x4498E1;
   - HeroListChange tail @0x44B128;
   - HeroVSBChange (optionally fix 0xC8 → 0x110);
   - the 3 sort handlers @0x44B303 / 0x44B363 / 0x44B3C3 (`8BD4 A120A44500`, 7 B) append the 2 new lists.
   - Helpers: IntToStr 0x4013AC, LStrCatN 0x401128, LStrArrayClr 0x4010E0, TStrings vcalls Add +0x34, AddObject +0x38, Clear +0x40.
   - ~0.8 KB of code + ~61.5 KB of DFM → grow .xtut by ~0x10000.

**Risks / live checks:**
- the TIvTranslator dictionary may lack "Turn Met" (other languages would show English);
- the name width;
- Delphi tolerance of the DFM edits;
- the vanilla HeroVSBChange T3Name bug;
- SetPlayer at load;
- the turn number shown vs [map+0x174].


## 10/22 BUILT (user-approved design; NOT applied, the coordinator applies sequentially)
**User decisions:**
- Turn Met = the turn the hero joined its CURRENT owner, re-stamped on every SetPlayer to a real owner. That covers resurrection, Animate Dead, charm and seduce.
- Pre-422 saves show "-". A 422 map hero shows "1".
- The name column may shrink.
- Fix the HeroVSBChange scroll bug.

**`patch scripts\patch_hero_turnmet_v1.py`** (AoWEPACK; zone 0x55836000–0x55836400 'HTM1', 296 B; `.bak_turnmet`):
- word THero+0x9A: 0xFFFF = unknown, 0 = map hero, N = turn.
- ReadWrite hook @0x55788B02: tag 0x60 rwWord on the value+1. A missing tag (an old save, or any .hsm) reads 0 → 0xFFFF. 0xFFFF writes as 0, which the writer skips. The compare stream sees the same +1 form on both sides.
- SetPlayer hook @0x557872DF: when the new owner is not 0xFF, store clamp([map+0x174], 1, 0xFFFE). The map global is read via the PIC delta.
- New-game reset, 0xFFFF → 0 across every player's hero list ([player+0x80]+8 TList). Rel-call redirects at:
  - 0x55756F89 (Turn: call TPlayerControl.StartNewMap);
  - 0x55759363 (Simultaneous: same);
  - 0x55758B33 (PBEM: call DefaultStartMap).
  - Load paths (StartLoadedMap*) are untouched.
- SetPlayer callers: TArmy.AddChild and SetPlayer, Killed/Resurrect/Animate, Recall Spirit/AnimateDead CA, campaign transfer, TStructure.MapFieldMsgProc, THero.MsgProc.
- Load safety: the owner byte is streamed directly, so SetPlayer exits early when the owner is unchanged. LIVE CHECK.

**`patch scripts\patch_exe_realm_heroes_cols_v1.py`** (AoWx.exe; `.bak_realmhero`) + new helper **`patch scripts\dfmbin.py`** (binary DFM raw round-trip model):
- .xtut grows from raw 0x4400 / VS 0x5000 to 0x15000 / 0x15000 (SOI 0x249000, file 0x242000).
- Code zone 0x639000–0x63A000 'RHC1' (3,164 B: literals '-' and 'Max', 688 B of code, new field table 0x6392D8, method table 0x6397EC).
- The DFM (57,682 → 60,758 B) lives at 0x63A000. Resource entry (file 0x730C0) RVA 0x163C74 → 0x23A000.
- VMT 0x4484F0: InstanceSize 0x1AC. Fields: T5Turn +0x19C, T5Exp +0x1A0, T5STurn +0x1A4, T5SExp +0x1A8. Method T5STurnClick = cave 0x63925C (sort mode 2).
- Hooks:
  - clear 0x4498E4
  - fill 0x449A84
  - sel 0x44B128
  - vsb fix 0x44B14B (0xC8 → 0x110)
  - vsb 0x44B179
  - sorts 0x44B2F5 / 0x44B355 / 0x44B3B5
- Geometry (x, w, RightOffset): Name 0/132/222, Turn 131/46/177, Health 176/62/116, Exp 237/64/53, Level unchanged. The Exp header's OnClick is T5SLevelClick.
- The apply → revert round trip on scratch copies is byte-identical for both files.
- LIFO: revert this before any later .xtut grower; the intro egg must stay applied underneath.

**Apply order:** the two scripts are independent (either order). Exe: after intro_egg; nothing else grows .xtut. AoWEPACK: its own zone only.

**Live tests:**
- new game: map heroes and the leader show 1;
- hire a hero on turn N → N;
- save, reload → values kept;
- an old 421 save → "-";
- Experience "cur/next", "Max" at the cap;
- 5+ heroes: scrollbar keeps the rows aligned (the fix);
- clicking each header sorts all 5 columns together;
- Turn Met sort direction (mode 2, same as Level);
- name truncation at 132 px;
- non-English languages: header text translated or not;
- resurrect / charm → the turn updates;
- MP: no desync.


## 10/22 v1 FAILED LIVE → v2
**Symptoms:** After the Fall's Leader customization showed a blank name, default face and no abilities. An old save showed Turn Met 717. The coordinator reverted v1; patch_exe_realm_heroes_cols_v1 stays applied.

**Root cause:** a hero's property scope ALSO holds its ability-data child records, tagged **0x32 + ability id** (TAbilityOwner.ReadWrite 0x5574F318; key list = tag 0x31; TCustomAbilityList uses tags 2/3). So 0x60 is ability 0x2E's record.
- Reading returned 2 bytes of that record: 0x2CE − 1 = 717. The offline model reproduces exactly 717 for every leader with that ability.
- WRITING hit the duplicate check (TEWriteStorageStream PropertyExist 0x5550FE48 → 0x5551009C raises), which aborted the leader copy.

**Fix:** `patch_hero_turnmet_v2.py`. The dword tag **0x10060** ('HTM2', `.bak_turnmet2`) is otherwise identical to v1. v1 is marked SUPERSEDED and now refuses `--apply`.
- Offline validation in the session scratchpad (turnmet_validate.py + ptab.py = a Python model of TPropertyTable LoadFromStream / FindOffset / SaveToStream) against After the Fall.hsm, AoWx - After the Fall.asg and autosave.asg (32 hero/leader tables):
  - the new tag is absent everywhere → "-" sentinel;
  - all original tags resolve to the same offsets after appending the tag;
  - +1 round trip OK.
- Apply → revert on a scratch copy is byte-identical.

**Engine stream facts** (Enginep.dpl):
- TPropertyTable fields: +4 entries (tag, offset dwords), +0xC count, +0x10 cursor, +0x14 max tag, +0x24 scope start, +0x18/+0x1C scope stack.
- Each child EObject: BackupSettings pushes the scope and appends the child's table; RestoreSettings truncates it again.
- FindOffset tries the cursor first, then scans the scope; a missing tag returns −1 and the rw* call writes 0.
- Writer: zero values are skipped. A tag ≤ 0x7F with offset ≤ 0xFF is stored as a compact (tag byte, offset byte) entry; anything else as a dword pair.
- Header byte = compact count | 0x80 if a dword-entry count follows.
- StorageMode bits: 1 = read, 2 = write, 8 = stream flag [+0x24], 0x40 = compare (MP desync check).

**LESSON:** before adding a stream tag to ANY object, list the tags that actually occur in real files for that class (the ability owners add 0x32 + id records). Pick a dword tag far above that range, and validate with the offline model.
- Scan of every X\Save\*.asg + AoWx map: 4,077 hero-like tables, highest tag 0x39F (some may be false-positive tables), so 0x10060 is clear by a wide margin.
