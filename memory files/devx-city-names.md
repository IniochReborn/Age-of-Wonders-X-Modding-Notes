---
name: devx-city-names
description: "2026-11-22 editor random city-name generator: Dict\\xCityNamesV.mld (vanilla names by race), Map Settings 'City Names' tab, new-city / race-change naming, Update Nameless; APPLIED, emulator-tested only"
metadata:
  node_type: memory
  type: project
  originSessionId: 5c12d565-3244-4a28-ba8c-c8f2ac12c9a3
  modified: 2026-11-23T02:04:19.754Z
---

User 11/22: random city names in the editor from a list compiled out of the vanilla 1.36 custom + campaign maps; Map Settings tab "City Names" (tick "Randomly generate city names" default on, "City Name List" drop-down with "Vanilla AoW", button "Update Nameless" + Yes/No prompt); a newly placed city (random race, "Noname") gets a Random-category name; a race change gives a name of the new race unless the mapmaker renamed the city. User wants to add more lists for mapmakers later (LISTS in aowxshot_citynames.py + one mld per list; the loader currently opens only xCityNamesV.mld - the list index is stored but not yet used to pick a file).

**Built + APPLIED 11/22, emulator-tested (`test_aowxshot_citynames_emu.py`), NOT yet seen in the editor:**
- `build_citynames_vanilla.py --apply` -> `Dict\xCityNamesV.mld`: 65 maps, 1948 cities, 1658 names; ordinary Multilizer mld (language table copied from CustMaps.mld), record Original = name, ClassName = category (Human, Azrac, Lizardman, Frostling, Elf, Halfling, Dwarf, Highman, Dark Elf, Orc, Goblin, Undead, Random), sorted by category then name; "noname" dropped.
- City RE: hex child class 0x20108; stream tag 0xC name, 0xD race (signed byte, tag absent = 0 Human; negative = random race, -1 plain, -2..-4 campaign variants); object: race byte [city+0x45], name AnsiString [city+0x48]; TCity.Create 0x557A952C sets race 0xFF + Translate(NonameRStr) via `call LStrAsg` @0x557A959B; TCity.SetName 0x557AC92C; TCity.SetRace 0x557AC990 = city VMT+0x244; editor city dialog OK 0x4192B0 calls SetName, SetUpgradeLevel, SetRace, SetWallType in that order. Cities of a map: [map+0x140] player list -> [+8] TList (items +4, count +8) -> [player+0x1C] structure list -> [+8] TList; city VMT = AoWEPACK RVA 0xA73F0. VCL _LStrAsg copies a source with refcount -1 (so DLL-owned "literals" are safe to assign).
- `aowxshot_citynames.py` (AoWxShot.dll, in-memory hooks of AoWEPACK in the editor process only): cninit patches the Create call -> cn_create and the SetRace entry -> cn_setrace; "automatic name" = Noname/empty or present in the list under the city's CURRENT race category (my rule for "not renamed by the mapmaker"; survives save/reopen). Tab built from the Ban List hooks (cn_build / cn_store); combo made a drop-down list via TCustomComboBox.SetStyle (VCL30 RVA 0x50760, style byte +0x121); TControl OnClick = +0xA4 code / +0xA8 data.
- Settings storage: `patch_levelvision_v1.py` v2 now keeps a SECOND dword, map +0x484 (InstanceSize 0x488), tag 0x10065: bit 0 = generator OFF, bits 8..15 = list index. aowxshot_levelvision checks InstanceSize == 0x488 now.
- 11/22 user: placing works ("good"); "Catacombs" removed from the list (EXCLUDE in the builder, 1657 names). Race change did NOT rename: the city dialog applies the race LIVE (race combo OnChange 0x4191AC -> city VMT+0x244 @0x4191DA, city [form+0x20C]) and OK then re-applies the name edit [form+0x234] (old text). Fix v2 APPLIED, emulator-tested, user verdict pending: cninit also patches 0x4191DA -> cn_racecb (edit text -> city first, SetRace, then the new name into the edit box). Thunks: TControl.GetText 0x401560, TCity.SetName 0x402930, LStrClr 0x4010B0.
- Ship: Dict\xCityNamesV.mld (new file - add to the release list), AoWxShot.dll, AoWEPACK.dll.
Related: [[map-level-vision]], [[ban-list]], [[mld-localisation]].
