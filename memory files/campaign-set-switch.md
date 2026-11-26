---
name: campaign-set-switch
description: "AoWx vs VANILLA campaign switch (user request 8/31). Game half APPLIED: AoWx.exe reads General\\strings\\4 at startup and swaps the campaign folder (X\\Campaign\\ <-> Scenario\\Campaign\\) + the Multilizer dictionary file (AoW.MLD <-> AoWVan.MLD). Holds the campaign-path RE, the TSelFactionWin text pipeline, and the AoWSetup + TEXT.pfs work still TODO."
metadata: 
  node_type: memory
  type: project
  originSessionId: bc99310d-e7a0-464e-8b38-a64c2704c9e7
  modified: 2026-09-01T02:24:24.620Z
---

# Campaign set switch — AoWx vs vanilla (2026-08-31)

**Ask:** a dropdown on AoWSetup's Developer tab to switch between the AoWx
campaigns and the original ones, default = AoWx. Must also switch the
campaign-select "setup text" the user rewrote (human perspective / challenge
mode / goal bullets). User chose (a) **ship a second dictionary** rather than
suppress translation, and (b) **also switch the campaign join text**.

## Where everything lives (RE)
* **Campaign folder** = the literal `X\Campaign\`, present as **4 separate
  Delphi AnsiString constants** in AoWx.exe (Delphi copies literals per unit),
  read from **5 sites**; none in AoWEPACK:
  `0x0040CDD8`←push@`0x0040CD3A` · `0x004186A0`←push@`0x004185B8` ·
  `0x0041C330`←push@`0x0041C2DE` · `0x0041D7A8`←push@`0x0041D580` +
  mov ecx@`0x0041D6B4`.
  The path builder is `0x0041C2B0` = `LStrCatN([[AoWEngine]+0x2C], dir, file)`.
  ⚠ **Only the folder differs** — both sets use `Keepers.cam`/`Storm.cam`
  (literals `0x00418678`/`0x0041868C`; vanilla files are .CAM, case-insensitive).
  Campaign chooser: index 0→Keepers, 1→Storm @`0x004184E9`/`0x00418523`, each
  doing SetILTIndex(0xA/0xB) + `TTextControl.RetrieveText(id 0xA/0xB)`.
* **Campaign-select screen** = form **`TSelFactionWin`** (LightPnl/DarkPnl,
  `LName`/`DName` labels, `LText`/`DText` TAOWMemos, LStart/DStart "Join!").
  ⭐ **The DFM still holds the VANILLA English** ("The Keepers", "The Cult of
  Storms", " Accept the Humans and their presence"…). All AoWx wording comes
  from **`Dict\AoW.mld` overriding it at runtime** via Multilizer, keyed by
  (source text, ClassName, ComponentName).
  A strict string-level diff (u16-length-prefixed records) of our AoW.mld vs
  the vanilla 1.36 one = **exactly 9 differing regions, ALL TSelFactionWin**
  (7 LText/DText goal lines + LName + DName), nothing else. Vanilla leaves the
  English slot EMPTY → falls back to the form text. ⇒ **a byte copy of the
  vanilla AoW.mld is a perfect, fully-localised "vanilla campaign screen".**
* **Dictionary file name is built ONCE**, in the unit-init at `0x00453E64`:
  create TIvCustomFileDictionary→`[0x0045B2BC]`; `mov edx,0x00453F60` ('AoW')
  + SetDictionaryName (logical name — keep it); then
  `LStrCatN(3)` of `[[AoWEngine]+0x2C]` + `'Dict\'`(0x00453F6C) +
  `'AoW.MLD'`(0x00453F7C) into `dict.FileName` (`[0x45B2BC]+0x7C`).
* `Campaign.mld` and `CampMaps.mld` are **byte-identical to vanilla** → the
  actual scenario prose needs no switching.
* ⚠ **`Release/TEXT.pfs` is NOT swappable wholesale** — besides the two
  campaign join texts (`RetrieveText` ids **0xA/0xB**, entries named "Campaign
  Join Text (Keepers)"/"(The Cult)") it carries many AoWx diplomacy rewrites.
  Needs vanilla entries added under NEW ids + a runtime id switch.

## The setting
`TAoWRegistry.GetString(idx)` — already imported by AoWx.exe (IAT `0x0045DAE8`,
thunk **`0x00401EFC`**) and already used twice in TMainForm.FormCreate.
Convention proven from those callers: **ecx = @result (AnsiString var, must be
NIL first), eax = the registry = `[[0x0045DF74]+0x5C]`, edx = slot index.**
It does `rwString(self,'General\strings',IntToStr(idx))` ⇒ reads
`HKCU\Software\Triumph Studios\Age of Wonders X\General\strings\<idx>` in the
isolated tree ([[registry-isolation]]). Verified live: slot 0 = player name,
slot 1 = empty, `booleans\0..7` and named `General` values (Cheat Mode, Auto
Debug Save…) are what AoWSetup's Developer tab writes.
**Slot 4 chosen. "1" = vanilla; anything else / missing = AoWx (default).**
⚠ TAoWRegistry caches named settings into object fields at construction, so a
NEW named value would need the loader patched — the indexed string slot avoids
that entirely.

## 🔨 Game half — APPLIED 2026-08-31
`patch scripts/build_campaign_switch.py` (backup `AoWx.exe.bak_campswitch`;
dry-run/--apply/--revert). Cave **`.xbfs` @0x0060E940** (section is **RWX**,
chars 0xE0000060, so the live buffers are writable): four 32 B constant
AnsiString images (campaign X/V, dict X/V) + two 32 B live buffers + init code
@0x0060EA00. Init hooks `mov edx,0x00453F60` @**0x00453E84**, reads the slot,
copies the chosen image into each buffer, restores edx, returns. All 5 campaign
sites → `0x0060E9C8`, the dict push @0x00453EA2 → `0x0060E9E8`.
Buffers ship pre-filled with the AoWx strings, so even if init never ran the
game behaves exactly as before.
* ⚠ **RELOC**: all 7 immediates carry fixups. The 6 pointer sites KEEP theirs
  (still in-image). The hook turns `mov edx,imm32` into `call rel32`, so entry
  **0x00453E85** is neutralised 3→0 and restored on revert.
* ⚠ **Cave-range footgun fixed**: `build_unitwin_party_arrows.py` zero-filled
  `[0x60E700,0x60EF80)` on apply AND revert, which would wipe this cave. Its
  `CAVE_LIMIT` is now **0x0060E940**. Same class as the timerres/.vgo bug —
  always bound a cave-clear to the patch's own region.
* Data: **`Dict\AoWVan.MLD`** = byte copy of `reference files\AoW 1.36\Dict\
  AoW.mld` (staged). `--apply` refuses without it.
* Verified: revert restores the backup byte-for-byte; re-apply reproduces
  identical bytes.

## ⚠ CORRECTION after the first live test (user, 8/31)
Result with slot 4 = "1": campaign folder switched ✅ (vanilla .cam ⇒ vanilla
intro scroll) but the **select screen stayed AoWx** ❌.
**Cause: `TSelFactionWin` fills its labels at RUNTIME from RESOURCESTRINGS,
not from form properties.** e.g. TopLbl @0x00419041:
`LoadResString([0x0045A3B4])` → `AoWE.TranslateRStr` (thunk 0x004021E4) →
`TAOWLabel.SetGText`. TranslateRStr resolves against AoWEPACK's
**ResourceStringDictionary** = `Dict\ResStr.mld`, whose path is built in
`AoWE.TAoWEngine.UpdateStartupDirectory`: pushes 'Dict'@0x55798386 /
**'ResStr'@0x5579838B** / '.mld'@0x55798390 → `[engine+0x78]+0x7C`.
⇒ The AoW.mld swap was aimed at the FORM dictionary and is a no-op here
(kept anyway: harmless, and it is the right file for form-property text).
AoWEPACK loads FOUR dictionaries (Release / CampMaps / ResStr / Campaign);
AoWx.exe loads only AoW.MLD.

⚠ **`ResStr.mld` must NOT be swapped wholesale** — a rigorous record diff
shows **15 differing regions** and only THREE are campaign text
("The Keepers", "The Cult of Storms", "Choose a Faction"). The rest are AoWx
renames that must survive: Age of Wonders→Age of Wonders X (×4),
Dragon→Monster, Dragon Slaying→**Monster Slaying**, Flame Throwing→**Cosmic
Breath**, Rejuvenate→**Scorch Terrain**, Shoot Black Javelin→**Seeker
Bolts**, Slow→**Hunter's Mark**, Summon Mermaid→**Summon Spirit**.

### .MLD format (worked out 8/31, splice-verified)
A record is `<u16 len><original>` + exactly **7 translation slots**, each
`<u16 len><text>`. **Slot 2 = English**, 3=German, 4=French, 5=Italian,
6=Spanish; slots 0/1 unused. An EMPTY slot = no translation ⇒ the engine falls
back to the original, which is exactly how vanilla shows "The Keepers" while
our file overrides slot 2 with "A Human Perspective". The header holds a
language table and **no content checksum**, and records are a flat sequence,
so a record may grow/shrink in place. ⚠ Do NOT try to parse from a fixed
header size — anchor on the record bytes instead (that is what
`build_resstr_vanilla_mld.py` does, validating it lands on the next record).

## Data files (staged 8/31)
* `Dict\AoWVan.MLD` — byte copy of vanilla 1.36 `Dict\AoW.mld`.
* `Dict\ResStrV.mld` — built by **`patch scripts/build_resstr_vanilla_mld.py`
  --write**: OUR ResStr.mld with only those 3 records transplanted from
  vanilla. Verified: all AoWx renames still present, the 3 overrides gone.

## Binaries (v2, APPLIED 8/31, both round-trip verified)
`build_campaign_switch.py` now patches BOTH files. Exe cave @0x0060E940 (465 B)
= 6 constant images + **3 live buffers** (campaign dir @0x0060EA08, AoW dict
@0x0060EA28, **ResStr name @0x0060EA48**) + init @0x0060EA60.
**AoWEPACK `push 'ResStr'` @0x5579838B → push 0x0060EA48** — a pointer into
the EXE image, which is legal because the exe never rebases; its reloc
(0x5579838C) is neutralised 3→0 and restored on revert. Backup
`AoWEPACK.dll.bak_campswitch`.
⚠ Ordering that makes this work: the exe's dictionary unit-init (0x00453E64)
runs during exe initialisation, BEFORE the engine calls
UpdateStartupDirectory — so the buffer is already filled when AoWEPACK reads it.

## ⚠⚠ CORRECTION #2 after live test #2 (user, 8/31) — TIMING
Even with the ResStr swap in place the select screen stayed AoWx.
**Root cause: AoWEPACK creates TAoWEngine during its OWN DLL initialisation**,
so `TAoWEngine.UpdateStartupDirectory` — which assembles the ResStr path AND
immediately loads the dictionary (`call [dict vmt+0x44]` @0x557983AA) — runs
**before any AoWx.exe unit-init**. Proof: AoWx.exe does not import
`TAoWEngine.Create` at all. So the exe-side buffer fill was too late for this
string, while still being in time for the campaign folder (only read when the
campaign screen opens). That is exactly the split the user saw: folder ✅,
screen text ❌.

**Fix (v3, applied):** AoWEPACK fills the ResStr buffer ITSELF, from its own
cave, immediately before the path is built.
* Cave **0x558151D0** (109 B, was next-free; new next free **0x55815240**).
* Hook `mov eax,[0x558FC4E8]` @**0x55798376** (5 B, BaseSoundEnginePath load)
  → `call cave`; reloc **0x55798377** neutralised 3→0, restored on revert.
* Cave: `GetString([esi+0x5C], slot 4)`; if "1" write len=7 + 'V' + NUL into
  the EXE buffer, else len=6 + NUL — i.e. it edits `ResStr` ⇄ `ResStrV`
  in place rather than copying an image. Registry is provably alive there:
  UpdateStartupDirectory's FIRST call is
  `TAoWRegistry.GetStartupDirectory([esi+0x5C])` @0x557982EB.
* PIC: the displaced absolute load is re-based via `call $+5 / pop ebx / sub`;
  the writes into the EXE's `.xbfs` buffer are deliberately plain absolutes
  (that image never rebases) and carry no reloc.
* The exe-side ResStr fill is left in as harmless belt-and-braces — both sides
  read the same slot and compute the same answer.

**LESSON (generalises):** in this codebase AoWEPACK's DLL init runs before the
EXE's unit inits, and the engine + registry + all five dictionaries are alive
by then. Anything that must influence engine startup has to be patched on the
AoWEPACK side; an AoWx.exe unit-init is only early enough for things consumed
later (campaign paths, UI).

## ⚠⚠⚠ CORRECTION #3 (test #3, 8/31) — THE SETTING STORAGE WAS WRONG
Test #3 still showed AoWx text — but the registry check revealed
**`General\strings\4` HAD VANISHED** (only slots 0/1 remained). That key is a
**game-managed list** (slot 0 = the player name); the game rewrites it and
deleted our slot after the first run. So tests #2 and #3 ran with the setting
absent — the v3 ResStr mechanism was never actually exercised. Lesson:
**never store a mod setting in `General\strings` (or `General\booleans`) —
they are managed lists.** Named values under `General` persist (Cheat Mode,
Auto Debug Save, ... survive every run).

## v4 — FINAL ARCHITECTURE (applied 8/31, round-trip verified)
Setting = registry NAMED value **`General\"Vanilla Campaigns"`** ("1" =
vanilla; absent/other = AoWx). Read via **`TAoWRegistry.rwString`
@0x55703D08**: eax=self (a TRegistry; opens '\Software\Triumph Studios\Age of
Wonders X'+edx), edx=subkey, ecx=value name, stack args [@result] then
[mode byte 0=read/1=write], **ret 8**. AnsiString literals are fine
(LStrAddRef on refcount −1 is a no-op).
* **All logic now lives in the AoWEPACK cave** (0x558151D0, 189 B) — it runs
  earliest (DLL init) and fills ALL THREE exe buffers (campaign dir, AoW dict
  name, ResStr name) from the V or X images. The exe-side init hook from
  v1–v3 is REMOVED (it ran later and would have re-filled/clobbered the
  buffers with its own read of the now-defunct slot).
* Exe `.xbfs` cave @0x0060E940 is **DATA ONLY**: 8 constant images (incl.
  'General' @0x0060EA08 and 'Vanilla Campaigns' @0x0060EA28) + 3 live buffers
  (camp 0x0060EA48 / dict 0x0060EA68 / resstr 0x0060EA88 chars). Cave regions
  used: exe 0x0060E940–0x0060EAA0; epack 0x558151D0–0x55815300 (next free
  epack cave **0x55815300**).
* Relocs: epack hook 0x55798377 + ResStr push 0x5579838C neutralised 3→0
  (restored on revert); the exe pointer-site relocs stay valid (in-image).
* Manual toggle:
  `reg add "HKCU\Software\Triumph Studios\Age of Wonders X\General" /v
  "Vanilla Campaigns" /t REG_SZ /d 1 /f` (0/delete = AoWx). Set to "1" on the
  dev machine 8/31 ready for the user's test #4.

## ✅ Game half USER-CONFIRMED (test #4, 8/31)
"it loads all vanilla stuff correctly" — folder + select-screen text + goal
lines all vanilla with the named value set. (Switch-back to AoWx untested but
same code path.)

## 🔨 AoWSetup dropdown — APPLIED 8/31 (awaiting test)
`patch scripts/build_aowsetup_campaign_dropdown.py` (backup
`AoWSetup.exe.bak_campdrop`; dry-run/--apply/--revert). New RWX section
**`.xcmp` @VA 0x513000** (0x600; sections 10→11, SizeOfImage 0x113000→0x114000).
TLabel "Campaigns:" (16,268) + **real TComboBox** csDropDownList (112,264,
w180) on DeveloperSheet ([form+0x224]) with items "AoWx campaigns" /
"Original campaigns". Loaded from the registry on EVERY Settings open
(CB_RESETCONTENT + re-add + CB_SETCURSEL — immune to VCL window re-creation);
written on Settings OK; Cancel untouched (nothing to undo).
**New AoWSetup RE banked:**
* TComboBox VMT **0x0042F594**, ctor 0x004333C0; RTTI: `Style` setter =
  **virtual [vmt+0x88]** (PropInfo 0xFE000088; 2 = csDropDownList — set
  BEFORE parenting), `Items` = field +0x118 (not needed).
* **TWinControl.GetHandle @0x00420714** (byte-shape search
  `53 8b d8 8b c3 e8 ? 8b 83 cc 00 00 00 5b c3`; **FHandle=+0xCC**, creates
  the handle + parents on demand) → drive the combo with raw CB_* messages
  via **SendMessageA IAT [0x0046C4C0]**, sidestepping TStrings.Add entirely.
* **TControl.Perform @0x0041D1A4** (fully-PIC byte signature from VCL30 —
  found but unused; banked for future work).
* advapi32 IAT: RegOpenKeyExA [0x0046C200], RegQueryValueExA [0x0046C1FC],
  RegCreateKeyExA [0x0046C208], RegSetValueExA [0x0046C1F8], RegCloseKey
  [0x0046C20C]. Registry read/write done via raw advapi32 (HKCU 0x80000001).
* DeveloperSheet DFM children: StartupDirLbl(16,24) Edit(16,48) then
  checkboxes x=112 y=128/160/192/232 → our row at y=264 fits (client ~376x352).
**Hook chain (order matters):** devtab → mouse_tab → campaign_dropdown.
Sites SettingsBtnClick 0x4689F4 → cs_show@0x5130F0 and SettingsOk 0x469090 →
cs_ok@0x5131E0; each tail-jmps INDIRECTLY through data slots (+0xDC/+0xE0 =
0x510000/0x510062, the mouse-tab caves) so revert can restore and a mouse-tab
re-apply is fixed by just re-running this script. Cancel site NOT touched.
⚠ Runtime controls don't localise (same as Mouse tab). Round-trip verified.

## v5 — campaign JOIN text + dropdown fixes (8/31, applied, awaiting test)
User feedback on the dropdown round: dropdown worked, but (a) the scrolling
campaign JOIN text ("Every land you have traveled…") stayed AoWx, (b) the
dropdown sat superimposed on the devtab patch's runtime **Cheat Mode checkbox
at (112,264,141,17)** — the DFM alone doesn't show runtime controls, always
check the other patches' creations too — and (c) item text wanted as
"AoWx"/"Vanilla".
* **JOIN TEXT** = `Release\TEXT.PFS`, loaded by `TAoWHSSet.ReadWrite` into
  **[set+0x98]** (the TTextControl behind `RetrieveText(0xA/0xB)`), via ONE
  literal `'TEXT.PFS'` @0x5574CB70 at TWO sites: `mov ecx,imm32`
  **@0x5574C7F9** (read, +0x2D1) and **@0x5574C99D** (write, +0x475). v5 adds
  a 4th image pair + live buffer (chars **0x0060EAE8**) and repoints both;
  their relocs **0x5574C7FA/0x5574C99E** neutralised 3→0 (restored on
  revert). Loads after UpdateStartupDirectory (needs basedir) ⇒ timing safe.
  Data: **`Release\TEXTVAN.PFS`** = byte copy of vanilla 1.36 TEXT.pfs.
  ⚠ DELIBERATE SCOPE: in Vanilla mode ALL TEXT.pfs strings revert, including
  the AoWx diplomacy rewrites — the full vanilla experience. If the user ever
  wants AoWx diplomacy kept in vanilla mode, TEXTVAN.PFS needs a .pfs splice
  (see [[caster-cost-abilities]] for the pfs writer recipe) instead of a copy.
* exe cave layout now **14 blocks** (10 images + 4 buffers): buffers
  camp 0x0060EA88 / dict 0x0060EAA8 / resstr 0x0060EAC8 / textpfs 0x0060EAE8
  (chars). Epack cave now 219 B (still 0x558151D0–0x55815300).
* Dropdown: items now "AoWx"/"Vanilla", row moved to label(16,300)
  combo(112,296) — clear of Cheat Mode. Re-applied in place.
Round-trip verified again on both binaries.

## v5.1 dropdown fix (8/31): blank-on-open
User: combo opened BLANK until a manual pick (v5, everything else confirmed
working). Cause: the synchronous CB_SETCURSEL made during the Settings-open
click gets cleared by something later in the ORIGINAL SettingsBtnClick flow
(runs after the whole hook chain). Fix: issue CB_SETCURSEL twice — SendMessageA
AND **PostMessageA [0x0046C4F4]**; the posted one lands on the next pump cycle
after the click completes. Pattern worth remembering for any runtime-created
control whose state must survive the surrounding VCL flow. Default remains
index 0 = AoWx (_readreg returns 0 on any failure).

## ⚠⚠⚠ v6 (9/1, applied) — v5 BROKE AoWDevX (runtime error 216)
**AoWEPACK.dll is not game-only: AoWDevX loads it and runs the same engine
init.** v5 pointed AoWEPACK's own reads (ResStr push, TEXT.PFS pushes) and
the cave's writes at AoWx.exe `.xbfs` addresses — unmapped in the editor's
process → AV in DLL init → error 216 on editor launch. **RULE: any patched
pointer that AOWEPACK CODE dereferences must target AoWEPACK's own image
(reloc stays ACTIVE, rebase keeps it right in every host); exe-image
absolutes are only legal behind a host check.**
v6 architecture:
* Constants (ResStr/ResStrV/TEXT.PFS/TEXTVAN.PFS/'General'/'Vanilla
  Campaigns' images) in the code cave **0x558151D0–0x55815290** (6×32 B),
  delta-addressed. Code @0x55815290 (467 B total; cave region now
  0x558151D0–0x55815500 → **next free AoWEPACK cave 0x55815500**).
* Live buffers in **BSS slack 0x558FA240/0x558FA260** (zero-init R/W in every
  host; no file backing — the cave always fills them before any consumer;
  BSS slack = 0x558FA231..0x558FB000, ⚠ diag ring precedent at 0x558FAA00,
  real global at 0x558FA044; **DATA slack 0x558E9A5C..0x558E9C00 is FULL** —
  peppered with live dword counters incl. endturn's 0x558E9A80/84).
* The 3 repointed pushes → BSS chars 0x558FA248/0x558FA268; their relocs
  **stay type 3** (intra-module). Only the hook reloc 0x55798377 is
  neutralised.
* Exe buffers (campaign dir/AoW.MLD @0x60EA80/0x60EAA0) written only after a
  **host check**: `[0x40003C]→[hdr+0x50]` SizeOfImage ≥ 0x60F000 AND dword
  @0x0060E948 == 0x61435C58 ('X\Ca' = our .xbfs signature). Host header reads
  are always-mapped ⇒ safe in any process.
* Two call/pop anchors (entry + post-popad displaced load); build converges
  both.
* Consequence: **the editor follows the setting** for ResStr/TEXT.PFS text
  (consistent with the game). Round-trip verified.

## ⚠⚠⚠ v7 (9/1, applied) — v6 STILL broke the editor: ORDER DEPENDENCE
v6's premise was wrong: **the editor never calls UpdateStartupDirectory**
(that hook belongs to the GAME's engine-startup path), so in AoWDevX the BSS
buffers stayed len=0 and TAoWHSSet.ReadWrite built `dir + ''` as the
TEXT.PFS path → load failure during editor init → runtime 216 again.
**LESSON: fill-at-point-A / consume-at-point-B is order-dependent and breaks
in hosts with a different init sequence. Make each consumer site guarantee
its own data.**
v7 architecture (UpdateStartupDirectory hook REMOVED — site 0x55798376 back
to vanilla, its reloc restored):
* The 3 repointed instructions are now **5-byte `call` stubs** (relocs on
  those imm32s neutralised — they're rel32 now; restored on revert):
  - `push 'ResStr'` @0x5579838B → `_stub_res` @0x55815290: dup-ret trick
    (push [esp]; …; write bufptr into the under-slot; ret) replicates the
    push exactly; registry from **[esi+0x5C]** (esi = engine at that site).
  - `mov ecx,'TEXT.PFS'` @0x5574C7F9/0x5574C99D → `_stub_textp` @0x558152B6:
    returns ecx = bufptr; registry via the **AoWE.AoWEngine BSS global
    0x558FA048** (nil-safe) — the surrounding code itself reads it, so it is
    guaranteed set by then.
* `_ensure(eax=registry-or-0, ebx=delta)` @0x558152DF: fast path
  `[BUF_RES len]!=0 → ret`; else pushad + the full fill (registry read via
  rwString, BSS buffers via delta, host-gated exe buffers via absolutes).
  First caller decides for the process: game = ResStr site (real registry,
  inside UpdateStartupDirectory, before exe unit-inits); editor = TEXT.PFS
  site (real registry via the global).
* Cave 524 B (constants 0x558151D0–0x55815290 + code); each stub computes its
  own call/pop delta and passes ebx to _ensure. Round-trip verified.
⚠ If a v8 is ever needed: the editor does NOT load the ResourceStringDict
(never builds its path) — vanilla behavior, unchanged; only TEXT.PFS switches
in the editor.

## v7.1 (9/1) — the host-gate constant was a VA, not an RVA
User: "vanilla campaigns don't load properly" after v7. **Live-probe diagnosis
(launch AoWx.exe + ReadProcessMemory — the game does NOT need elevation, and
a self-launched process is fully readable):** BSS buffers = V variants ✓ but
exe buffers still AoWx defaults ✗ → vanilla TEXT but AoWx campaign FILES.
Cause: **SizeOfImage is in RVA space** — our AoWx.exe header says 0x0020F000
(.xbfs ends at RVA 0x20F000), but the gate compared against 0x60F000 (the VA)
→ never passed. Fix: AOWX_SOI = 0x0020F000 (AoWDevX = 0xE4000, still well
below — discrimination intact).
**Verified LIVE both ways 9/1:** setting=1 → Scenario\Campaign\ / AoWVan.MLD /
ResStrV / TEXTVAN.PFS; setting=0 → all AoWx defaults. Also observed live:
AoWEPACK rebases in the game (bases 0xDA0000/0xDE0000/…) — the PIC and
active-reloc discipline is exercised for real.
⭐ Tooling note: the game-probe scripts (scratchpad gameprobe*.py pattern:
launch, EnumProcessModulesEx for the rebased AoWEPACK base, dump the buffers)
turned a blind guess-cycle into a 2-minute diagnosis — reuse for any future
"which string did the engine actually see" question.

## TODO
1. ~~AoWSetup dropdown~~ DONE 8/31 (above)
   (was: **AoWSetup dropdown** — Developer tab (`DeveloperSheet` @form+0x224).
   Reuse the runtime-VCL machinery in [[aowsetup-internals]]: create controls
   lazily on Settings open, chain into the existing SHOW/HIDEOK/HIDECAN caves
   (0x46AF40/0x46AF80/0x469990). Needs a TComboBox VMT (derive via the
   classname-shortstring→vmt-0x20 recipe) and must write the named value `General\"Vanilla Campaigns"`.) ⚠ runtime-created controls don't localise.
2. ~~Campaign join text~~ DONE in v5 (above). (was: **Campaign join text** — add vanilla ids to TEXT.pfs + switch the
   `mov edx,0xA`/`0xB` at `0x00418517`/`0x0041854E` (5-byte imm32 movs).
3. Flag to the user: switching is read at STARTUP, and campaign saves from one
   set will not resolve against the other.

Related: [[aowsetup-internals]], [[aowsetup-installcheck-devtab]],
[[registry-isolation]], [[mld-localisation]], [[cam-campaign-format]],
[[aowx-exe-string-pipeline]].


## Index note (moved verbatim from MEMORY.md 2026-09-21)
- 🔨 [campaign-set-switch.md](campaign-set-switch.md) — ✅ game half USER-CONFIRMED 8/31 (v4: named value `General\"Vanilla Campaigns"`; v1-v3 lessons: ResStr.mld is the resourcestring dictionary, AoWEPACK DLL-init runs before exe unit-inits, General\strings is a game-managed list). 🔨 AoWSetup dropdown applied 8/31 awaiting test (.xcmp section, TComboBox via GetHandle+CB_* messages). v5 8/31: join text switches too (TEXT.PFS↔TEXTVAN.PFS via TAoWHSSet.ReadWrite literal; ⚠ vanilla mode reverts ALL TEXT.pfs incl. AoWx diplomacy); dropdown items "AoWx"/"Vanilla", moved to y=296 (v1 collided with the runtime Cheat Mode checkbox at y=264); dropdown blank-on-open fixed via one-shot SetTimer (D3 combo recreation restores items, NOT selection); ⚠⚠ v6–v7 9/1: v5 broke AoWDevX (216: exe-image pointers unmapped in the editor); v6 STILL broke it (editor never calls UpdateStartupDirectory → empty buffers). v7.1 = SELF-ENSURING SITE STUBS (+ fixed host-gate: SizeOfImage is RVA-space 0x20F000, not 0x60F000 — live-probe verified both settings): each repointed instruction is a call that fills the BSS buffers (0x558FA240/60) if empty, then yields the pointer — order-independent in every host; exe absolutes only behind a host check (SizeOfImage+.xbfs signature). Editor follows the TEXT.PFS setting; its ResStr dict never loads (vanilla behavior). Was: GAME HALF APPLIED, awaiting test: AoWx.exe reads `General\strings` at startup and swaps the campaign folder (X\Campaign\ ↔ Scenario\Campaign\) + the Multilizer dictionary (AoW.MLD ↔ AoWVan.MLD). ⭐ Holds the campaign-path RE and the TSelFactionWin text pipeline (the DFM still holds vanilla English; AoWx wording is a dictionary override). TODO: AoWSetup dropdown + TEXT.pfs join text.
