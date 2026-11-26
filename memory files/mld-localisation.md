---
name: mld-localisation
description: "AoW1 .mld Multilizer dictionary format, the 8 Dict files, how the game picks a language, MLDEdit's file-corrupting writer bugs, and what blocks Russian"
metadata: 
  node_type: memory
  type: reference
  originSessionId: 66c54916-064a-4d90-b1cc-a7e1edb96f02
  modified: 2026-08-26T23:17:52.225Z
---

AoW1 localisation lives in **8 Multilizer dictionaries** at `<install>\Dict\`:
`AoW, AoWEd, AoWSetup, Campaign, CampMaps, CustMaps, Release, ResStr` — **6,683 records**.
Owners: AoW.mld→AoWx.exe, AoWEd.mld→AoWEd.exe, AoWSetup.mld→AoWSetup.exe, the rest→AoWEPACK.dll.
Working codec: `modding tools\aowxlib\mld.py` (also in `old modding tools\research\`) —
**32/32 files round-trip byte-identically** (8 live + 24 across the three reference sets).

**Format** — magic `MLD\x03`, all little-endian, `wstr` = u16 byte-count + raw bytes (no
terminator). 42-byte header (LanguageCount, LanguageOffSet, TranslationsCount,
TranslationsOffSet, InfoSize/Offset), then a `TLanguageData` per language, then records.
Each record is `Original`, `ClassName`, `ComponentName`, then one wstr **per language column**.
**All languages live side by side in one file** — never one file per language.

**Critical: records have no ID.** The key is the `Original` string itself — the game looks up
the native English text at runtime. So *never* edit `Original` unless the matching source text
in `Release\*.pfs` or the DFM captions changes too, or the lookup fails and you get raw English.

**Columns**: 0 `Native` (pseudo-language, = the English source), 1 English, 2 German,
3 French, 4 Italian, 5 Spanish. The **English column is deliberately almost empty** (1 entry in
stock) because Multilizer falls back to `Original`. Note the game's enum order is
Auto/English/German/French/**Spanish/Italian**, which does NOT match column order — AoWx.exe
(file 0x0532DB) and AoWEPACK.dll (file 0x096AAF) both carry a jump table remapping 4→5, 5→4.

**How AoWx renames things** — it fills the **English column** and leaves `Original` as the key.
That is why foreign text goes stale: `Original='Dragon Slaying'`, English=`'Monster Slaying'`,
but German was still `'Drachentöten'`. Exactly **32 such overrides** existed; all four foreign
columns for them were refreshed 2026-08-25 by `patch scripts\patch_translations_aowx.py`
(112 cells, dry-run/--apply/--revert, backs up to `backup\Dict.bak_translations`, and asserts
no unintended cell changes). Its `enc()` normalises NBSP/smart quotes — **stock French uses
zero 0xA0 bytes in 6620 cells**, and 0xA0 would index a wrong bitmap glyph.
Translation style to match: spell stat names out — de Angriff/Schaden/Verteidigung/Widerstand,
fr Attaque/Dommages/Défense/Résistance, it Attacco/Danno/Difesa/Resistenza,
es ataque/daños/defensa/resistencia — with the number in parentheses, e.g. "Angriff (+3)".

**Language selection**: `HKCU\Software\Triumph Studios\Age of Wonders X\General\Language`
REG_DWORD, 0=Auto 1=English 2=German 3=French 4=Spanish 5=Italian(now Russian). Written by
AoWSetup's `LanguageCB`. Read once at package init — **changing it needs a restart**.

⚠ **The game IGNORED this and always showed English** because an old "AoW+ bugfix" had patched
`AoWReg.TAoWRegistry.GetLanguage` (AoWEPACK.dll VA 0x55704B84 / **file 0x3F84**) from
`8A 04 24` (mov al,[esp] = read the real registry value) to `B0 01 90` (mov al,1;nop = force
English). Every in-game language dispatch calls GetLanguage, so the selected language never
applied to game text (AoWSetup is a separate exe and localized fine, which masked this).
`patch scripts\patch_restore_language_switch.py` toggles it (backup
AoWEPACK.dll.bak_langswitch; its --revert is now BYTE-level — never restore the whole dll
from that stale backup, other patch families touched it since).
Briefly unlocked 2026-08-26 for a multi-language test, then **RE-LOCKED the same day at the
user's request** ("never mind") — force-English (B0 01 90 @0x3F84) is back and is again the
intended state: the game is English-only by design. Do not remove the force again without an
explicit new request.

**Rename-mechanism ground truth (verified 2026-08-26, do not "fix" this)**: of the 33
Source≠English override rows, 31 are CORRECT as-is — the binary still emits the vanilla
Original (e.g. 'Dragon Slaying' is still AoWEPACK's resourcestring; the tutorial/campaign
strings are still in AoWx.exe / the map files) and the English column does the rename at
lookup time. Copying English→Original would break the key match and revert every rename
in-game. The user asked for exactly that on 2026-08-26; evidence said no; only the TWO rows
whose runtime text lives in pfs files AoWx edited had stale keys (Release.mld rows 248/352 —
'…against dragonkind.' and 'Halves the target's mobility…' vs the Ability.pfs/Spells.pfs
wording). `patch scripts\patch_dict_key_sync.py` fixed them, but the user **REVERTED that
too the same day** along with the re-lock: Release.mld is back to its original keys
(verified byte-identical to Release.mld.bak_keysync). With the game English-locked the stale
keys are cosmetically harmless (English shows the pfs text raw). Leave them alone unless
languages are ever unlocked again — the script is ready if so.

**MLDEdit corrupts every file it saves** (VA 0x468E87): it never writes `Primary`, writes
`ISODefaultCountry` twice overlapping, never recomputes header offsets, never writes the Info
block, and saves without truncating. The two size bugs cancel so it still parses — damage is
silent and cumulative. **6 of the 8 live files are already damaged** (all but Campaign.mld and
CampMaps.mld); index-based language selection still works, but `alAuto` cannot match the system
locale. **Repaired 2026-08-25** by `patch scripts\patch_mld_repair.py`, which copies the canonical
language table verbatim from the stock 1.36 dictionaries (rather than guessing) and asserts
every record stays bit-identical — 138 fields across 6 files, backup in
`backup\Dict.bak_langrepair`. All 8 now read en/9 de/7 fr/12 it/16 es/10, cp1252.
It mattered because explicit language choice is index-based and unaffected, but **Auto** asks
Multilizer to match the Windows locale against `Primary`/`DefaultSub`, so a German player on
Auto was getting English. AoWxInk must never reintroduce this: always rewrite offsets and the
full language table.

**Russian CAN be added without harming the Latin accents** — an earlier assumption that it
could not was wrong, so don't repeat it. In-game text is drawn from bitmap glyph strips: 13
image libraries in `Int\Fonts\` (Age8/8s, Age10/10s/10b/10bs/10tb/10LB, Age14G, Age15BlBr/
WhGr/WhIn, Age16s), each holding 155 frames whose **image id IS the character's byte value**
(confirmed by rendering "Age of Wonders X" from Age15WhGr.ILB with `id = ord(ch)`).
Census of every high byte in real text (all 8 dictionaries + text-like runs in `Release\*.pfs`):
**57 high bytes are used, 71 are never used by anything.** Russian needs 66 (33 upper +
33 lower incl. Ё/ё), so it **fits in the free slots with 5 to spare and zero existing glyphs
disturbed**. Of the 71: 30 need a brand-new frame in every font, 41 already have a frame that
no text ever references (repurposing those is invisible).
The approach is therefore a **custom AoWx-Russian byte encoding** mapping Cyrillic onto those
free byte values — *not* cp1251 — because the game indexes glyphs by raw byte and we control
both the glyph table and the stored bytes (glyphs painted 2026-08-25, see [[aowx-bitmap-fonts]]).

**7th language APPLIED 2026-08-25** (`patch scripts\patch_language_russian.py`, backups
`*.bak_ru7`; Dict columns via `patch_dict_russian.py`, backup `Dict.bak_ru7`):
- There were 13 `and eax,7F/cmp eax,5` switch sites, not 2. True SetLanguage sites (7-entry
  table in a cave + `mov edx,6` stub): AoWx.exe VA 0x453EC8 (dict @0x45B2BC, thunk 0x4020E4,
  caves in .xbfs 0x60E6E0-0x60E72C), AoWEPACK.dll VA 0x557976A0 + 0x55797C90 (import
  IvDictio.TIvDictionary.SetLanguage via 0x5570655C; caves 0x55812C80-0x55812DA0),
  AoWSetup.exe VA 0x468AA6/0x469351/0x46942E (static SetLanguage 0x44BA20, caves in .xmou
  0x5114E0-0x511598). Case bodies map enum→column: 1,2,3, 4(Spanish)→5, 5(Italian)→4,
  Russian 6→6.
- Behavior switches (AoWx 0x4091E5 + five in AoWEPACK 0x557A7DCA..0x557A8C43 whose defaults
  return NIL strings): case 6 → the English case body (7-entry cave tables, no stub).
- AoWEd.exe left alone (forces language 1 anyway; 6 → default is harmless).
- AoWSetup Settings DFM: "Russian" added to LanguageCB Items.Strings, size-compensated by
  deleting the combo's ItemHeight property (13 freed, 9 used, 4 zero-padded at stream end) —
  resource size and all offsets unchanged. Registry Language=6 = Russian.
- All 8 Dict files now have 7 languages (index 6 = ru/RU, Primary 0x19, CodePage **1251**
  which AoWxInk maps to the aowx-ru codec); empty cells fall back to Original (English).
  First seeds in ResStr (Обучение/Опции/Выход/Продолжить/Загрузить игру) via
  `patch_translations_ru_seed.py`, backup `Dict.bak_ruseed`.
- **Multilizer language guards — EIGHT raises, all must die** (whack-a-mole, four rounds).
  TIvDictionary has TWO validation routines, each with a mode byte at [dict+0x78] selecting a
  mode-1 (system-locale) or mode-2 (codepage) check that raises when the lang's locale/CodePage
  ≠ the OS default (cp1251 vs Western cp1252; and locale (25,1)=Primary 0x19/Sub 1 for Russian):
  * Routine A "... is not supported by the {system|code page}" (AoWSetup worker 0x44BBCC):
    skip-jnes at AoWSetup file 0x4B17E + 0x4B1B5; Localize 0x6A1A + 0x6A51.
  * Routine B "The locale (%d,%d) is not supported by the {system|current code page}"
    (AoWSetup worker ~0x44BE??): skip-jnes at AoWSetup file 0x4B315 (near, 0F85→90E9 nop;jmp)
    + 0x4B36F (short 75→EB); Localize 0x6BB1 (near) + 0x6C0B (short).
  Different loaded dicts carry different mode bytes, so each patch just moved the failure to the
  next dict/routine — needed all eight. Both copies patched: AoWSetup.exe (static link) and
  Localize.dpl (serves AoWx.exe + AoWEPACK.dll via IvDictio imports; relative jumps, rebase-proof).
  Backups *.bak_ru7. NOT viable: the common gate 0x44DFC4 (test [dict+0x20],0x10; setne al) that
  fronts both routines has 16 callers — forcing it true would change unrelated behavior; the
  targeted jne→jmp per raise is the safe path.
  ⚠ AoWSetup.exe holds a FILE LOCK while running (elevated → can't kill externally); the patch
  script now skips a locked target and reports it — close AoWSetup, re-run --apply.
- ⚠ **CAVE ALLOCATION LESSON (caused AVs, fixed same day)**: never claim "free" space in
  a patch-owned section by scanning for zeros — the mouse-tab blob in AoWSetup's .xmou
  ENDS with zero-initialized runtime buffers (gotbuf/g_vallab/tabbuf/pathbuf, 360 bytes)
  and GetModuleFileNameA overwrote the v1 jump tables the moment Settings opened. Same
  latent risk in AoWx.exe's .xbfs (fullscreen blob). v2 puts all exe caves in dedicated
  appended `.xlng` sections: AoWx.exe VA 0x60F000 (raw 0x20A600), AoWSetup.exe VA
  0x512000 (raw 0x10C200), both 0x200 bytes, chars 0x60000020. AoWEPACK caves stay at
  0x55812C80–0x55812DA0 (documented cave map, safe).

**STATUS 2026-08-26: Russian was REMOVED from the game (user decision).** The ru7 binary patches are reverted (AoWx.exe / AoWSetup.exe / Localize.dpl / AoWEPACK.dll all byte-identical to their .bak_ru7 backups), the ru column is gone from all 8 Dicts (back to Native/English/German/French/Italian/Spanish), and the Cyrillic glyphs are out of the font ILBs. Do not propose Russian/7th-language work. AoWxInk keeps its aowx-ru codec + Add-language Russian preset as dormant tooling only.
