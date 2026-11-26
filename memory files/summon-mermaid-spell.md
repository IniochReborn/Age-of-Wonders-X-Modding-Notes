---
name: summon-mermaid-spell
description: "✅ COMPLETE+CONFIRMED 2026-08-10: 'Summon Mermaid' (id 0xC9, Secret L1, summons unit 219, vanilla tail icon) + THREE engine bugfixes any future custom spell needs: spellbook id≥100 filter (AoWx.exe), SpellTypes combat table (AoWTCPCK: 18 bound pairs + per-id type bytes), ability-id [0..169] combat bounds."
metadata: 
  node_type: memory
  type: project
  originSessionId: 363e8ad2-56ec-4ede-b38d-8eb55d00d2fc
  modified: 2026-08-10T10:40:19.200Z
---

**NEW SPELL "Summon Mermaid" — id 0xC9 (201), Secret sphere, level 1, cast 5.
Built 2026-08-10 via `patch scripts/build_summon_mermaid.py` (single script,
--apply/--revert, backups *.bak_mermaid). APPLIED, awaiting in-game test.**

Background: vanilla Summon Mermaid (spell 0x4E, class TSummonMermaid, summons
unit 0xF1=241) was repurposed by the user: unit 241 renamed to "Puppet", spell
= "Greater Spirit Puppet" summon (sphere tag 1, icon 155 = old mermaid emblem).
The REAL Mermaid still exists as **unit 219 (0xDB)**. New spell = second
TSummonMermaid instance summoning 219; user's custom spell untouched.

**Key RE (summon spells):**
- TSummonMermaid.Create @0x557E4FD0 (classref [0x557E3E94]): id 0x4E, cost 5,
  [+0x21]=1 level, [+0x20]=2 sphere-byte, **summon unit = TIntegerList.Add(
  [spell+0x38], unitid)** — the summon list is CODE-ONLY (TSummonSpell has no
  ReadWrite override → not in pfs). TIntegerList: items @+4, count @+8
  (Engine.TIntegerList.Get @EngineP rva 0x13D5C).
- All summon machinery generic (TSummonSpell.Activate/SetupSummonSpellTE +
  TSummonSpellTE) — registration alone makes a working summon spell, NO effect
  hook needed.
- RegisterSummonSpells @0x557E508C; LAST RegisterSpell = mermaid @0x557E51CF
  (`E8 6C49F9FF`; ebx=spell control) = the hook site.

**Patch A (DLL):** cave @0x55810900 (bytes 111): displaced RegisterSpell, PIC
delta (edi), create 2nd TSummonMermaid, poke id 0xC9/sphere 7/level 1, patch
list[0] 0xF1→0xDB via [esi+0x38]→[+4]→[0], name literal "Summon Mermaid" via
@LStrAsg (RStr may be translated to the user's custom name — literal overrides),
RegisterSpell, ret→0x557E51D4.
**Patch B (icon):** SPELLICN image id **88** (recs 144/145, was unused): rec144
= blue water cloud copied from rec 160, rec145 = black TRIDENT-over-waves ink
glyph on white. (Other free id: 52.)
**Patch C (pfs):** record key 211 appended = copy of key 88 (user's summon —
proven record shape w/ sound + Spawn cast gfx) with desc ("Summons a Mermaid,
an enchanting creature of the deep."), icon 155→88, cast 5, sphere tag 7, level
1. Root table: ctrl 0x81, nd 108→109, appended dword pair (211, off). CRC
recomputed. **Root-table append recipe works — first new-record insertion into
a pfs.**

**★★ BOOK-VISIBILITY BUG FOUND & FIXED 8/10 (`build_spellbook_id_fix.py`,
APPLIED).** Symptom: tower-bought mermaid (id 201) never showed in the
spellbook while Magic Sight (200) did. Root cause: AoWx.exe book page builder
(@0x42F2E4; builds TSpellList via TPlayerMagicControl.ListSpells, page mask =
1<<[form+0x222] tested vs [spell+0x22]) POST-FILTERS: **any spell id ≥ 0x64
(100) is DELETED from the list unless `AoWTC.SpellTypes[id]` ≠ 0**.
`SpellTypes` = AoWTCPCK.dll export @0x4672F4, **static array[0..130] of byte**
(bounds pairs @0x41B034 etc.), imported by AoWx.exe via IAT 0x45EBEC. The book
reads it UNBOUNDED → id 200 = nonzero garbage (lucky, visible), 201 = zero
(hidden). FIX: 1 byte @0x42F2F5 `7C29 jl → EB29 jmp` (never drop — every
known-list spell is real). Backup AoWx.exe.bak_bookid.
**✅ COMBAT LANDMINES CONFIRMED & FULLY FIXED 8/10
(`build_spelltypes_bounds_fix.py`, APPLIED — 3 iterations to the truth):**
1. "Range check error"/"Exception during OnCastSpell" casting Magic Sight in
   TC = Delphi `bound` guards. Widened ALL 18 pairs → [0..255]: nine
   spell-[0..130] pairs (0x415120, 0x4180E8, 0x41B034, 0x41E00C, 0x41EDF0,
   0x423428, 0x427628, 0x4288A0, **0x40CDC4** = TCRangedToken kind-52) + nine
   ability-[0..169] pairs (0x40B0FC, 0x40CDCC, 0x40F4A8, 0x414D04, 0x415128,
   0x418130, 0x41B03C, 0x41EDF8, 0x4288A8 — ability-type table; Magic Sight's
   ability id 170 overflows these once enchanted units fight).
2. Then "Error - TCRanged Token 52 200, Error during Token Start": token kind
   0x34=52 = SPELL-cast projectile; TCRangedToken.Start reads
   **SpellTypes[spellid] via ptr [0x4693F8] (→ &SpellTypes) as the cast-anim
   TYPE**. ⚠ CORRECTED MODEL (earlier note wrong): **AoWTCPCK DATA section VA
   0x467000 = file 0x66000** (NOT +0x400C00!); SpellTypes @file 0x662F4 is
   **STATICALLY INITIALIZED**: EnchW[16]=7 = unit-enchant combat type; [78]
   vanilla mermaid = 0. Ids >130 read neighboring static data (garbage 6 @200
   → bad anim → Token Start exception). FIX: **SpellTypes[200]=7,[201]=0**
   (file 0x663BC/BD). Ability-type table @file 0x66248 [0..169]; its 2
   alignment-pad bytes (file 0x662F2/F3, read as ability-type[170/171]) zeroed
   (were 139/192). Backup AoWTCPCK.dll.bak_spelltypes (pristine pre-all).
**RULE for future custom spells/abilities: every new spell id needs
SpellTypes[id] set (7 for unit-enchants; file 0x662F4+id), and ability ids
must stay ≤171 unless more table bytes are sanitized.**
Also: ExecuteTE learn = TIntegerList.Add([player+0x54 magicctrl]+0x30, [tower
+0x34]); tower = sphere-BITMASK word [tower+0x31] + level byte [tower+0x33];
GetRandomSpell filters sphere-mask + exact level. [spell+0x22] = book PAGE
byte (unit=1 from TUnitSpell, summon=2 from TSummonSpell) — pfs does NOT
serialize it.

Cave map now: 0x55810400 s1, 0x55810600 s2, 0x55810700 s3, 0x55810800 s4,
**0x55810900 mermaid**; next free 0x55810A00.
Related: [[magic-sight-spell-re]] (all container formats + CRC + toolchain).
