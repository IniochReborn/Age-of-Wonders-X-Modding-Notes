---
name: aowsetup-installcheck-devtab
description: "AoWSetup.exe: install-check false negative fixed via Root-Directory '.'-fallback cave + hidden Developer tab (DebugMode/LogTokenEvents/AutoDebugSave/StartupDirectory) unhidden. Applied 2026-08-13, user verification pending. Holds AoWSetup RE map (TLoaderForm methods/fields, registry getter, cave space)."
metadata: 
  node_type: memory
  type: project
  originSessionId: 023e7bbb-4366-4edb-ace5-396c4ec6f1e7
  modified: 2026-08-13T20:05:15.944Z
---

**PLAYER BUG (2026-08-13):** AoWSetup showed only Install/Exit. Cause: the
install check reads registry `General\Root Directory` from the mod's isolated
tree `HKCU\...\Age of Wonders X` ([[registry-isolation]], AoWSetup patched to
X-tree 7/31 `.bak_regiso`) and tests `FileExists(path+'\aow.exe')` — but the
X tree only exists after the GAME first runs (or migration, as on the dev
machine). Fresh mod install ⇒ false "not installed". Start buttons launch via
the same path, so forcing the check true alone would have broken them.

**FIX — `patch scripts/build_aowsetup_installcheck_devtab.py` v2** (APPLIED
2026-08-13, backup `AoWSetup.exe.bak_nocheckdev`; user confirmed v1's menu
fix worked, v2 tab-navigation verification pending):
1. Hook the getter's registry call `0x4675A0 call 0x46719C` → cave re-invokes
   the read, and if the out-string is nil, stores the constant `'.'`
   (refcnt −1 Delphi literal @0x4698E0, payload 0x4698E8; storing a constant
   into a NIL string var needs no RTL). Cave code @0x4698EC. '.\aow.exe'
   exists in the game dir ⇒ full menu + working launch with no registry.
2. **v1 LESSON: ALL of MainPageControl's pages are hidden-tab screens
   switched in code (jump table in FormCreate → 0x44BA20(edx=index)), so
   v1's FormCreate `TabVisible:=True` on DeveloperSheet alone made a lone
   one-way tab — user got stuck on the dev page.** v2: FormCreate byte left
   STOCK (hidden at startup); entry hooks on SettingsBtnClick 0x4689F4
   (displace 5 B `538bd88bc3`) → show-cave 0x469930, SettingsOkBtnClick
   0x469090 (6 B `558bec83c4f8`) → hide-cave 0x469948, SettingsCancelBtnClick
   0x469344 (8 B `538bd8a134ba4600`) → hide-cave 0x469960; shared setboth
   helper 0x469910 sets SettingsSheet(+0x1EC)+DeveloperSheet(+0x224)
   TabVisible via 0x43A32C(eax=sheet,dl=bool). Result: a real 2-tab
   Settings/Developer UI only while in settings mode. Method table has NO
   PageControl OnChange ⇒ tab clicks are side-effect-free.
3. **Editor button → AoWDevX.exe** (user request, applied 2026-08-13):
   StartAoWEdBtnClick's `mov edx,0x4689CC('\aowed.exe')` @0x46894F repointed
   to new refcnt−1 const `'\AoWDevX.exe'` @0x469978 (payload 0x469980; no
   in-place room, 10→12 chars). Pre-launch check 0x468594 is only an
   already-running mutex ('AOWEDEVENT'), left alone.
4. **Start-AoW button → AoWx.exe** (applied 2026-08-13): const @0x4688E0
   edited IN PLACE (len dword 8→9 @0x4688DC, pad had room; sole ref
   0x468863). Install check's own '\aow.exe' @0x4686A0 deliberately kept —
   aow.exe ships, so the check stays valid.
5. **★ CHEAT MODE toggle** (user request, applied & **FULLY AGENT-TESTED
   2026-08-13**: checkbox appears under the 4 stock options, tick → OK writes
   `Cheat Mode REG_DWORD 0x1`, reopen reloads it ticked, Play! launches
   `"…\AoWx.exe" beatrix`; unticked launches with no argument):
   **Vanilla cheat = launch arg `beatrix` + press Ctrl+Shift+C in game.**
   AoWEPACK 0x55774060-ish keyboard handler: `cmp word [ebx],0x43` ('C') →
   `(shiftstate AND 5)==5` (5 = ssShift|ssCtrl) → ParamStr(1)=='beatrix'
   (const @0x557741A0, compare 0x55701584) → not MP ([0x558FA040]+0x13A ∉
   {1,2}, [0x558FA048]+0x6E==0) → plays SFX\ATTACK\MAGICB02.WAV and sets
   [esi+0xC]=1. **NO game patch needed — only the launcher passes the arg.**
   Implementation: a REAL TCheckBox created at RUNTIME (lazily, on first
   Settings open, so a failure can't break the main menu), all 4 stock dev
   options kept; state in registry `General\Cheat Mode`; StartAoWBtnClick's
   ShellExecute lpParameters now points at a BSS buffer filled with
   'beatrix' or '' just before launch (12-B block @0x468847 → cave replays
   push 1 / push '' / push BUF).
   **VCL recipe (verified twice — TCheckBox VMT + VCL's own
   CreateMessageDialog @0x4386A0 which builds buttons dynamically):**
   ⚠ **Delphi 3 VMT layout: vmtClassName = −0x20, vmtInstanceSize = −0x1C,
   vmtParent = −0x18, vmtSelfPtr = −0x40** (NOT the Delphi 4+ −0x2C/−0x28).
   ctor = VMT+0x24 (TCheckBox 0x4345D4; eax=VMT, dl=1, **ecx=Owner**) →
   eax=instance · SetParent = VMT+0x18 (0x41C7E4, eax=ctrl, edx=parent) ·
   SetBounds = VMT+0x4C (0x4200B8; eax, edx=Left, ecx=Top, **push Width then
   Height**) · SetText/Caption 0x41CA24 (edx=AnsiString) · Get/SetChecked
   0x434694/0x4346B4 · registry rw 0x4670AC (eax=obj[0x46BA34], edx=section
   ('General' 0x4679C8), ecx=name, push @buf, push flag(0=rd/1=wr), ret 8).
   Delphi refcnt−1 AnsiString consts serve as BOTH caption and registry name.
   Dev-sheet DFM geometry: checkboxes Left 112, Top 128/160/192/232 → new one
   Top 264, W 141, H 17. Form fields: SettingsSheet +0x1EC, DeveloperSheet
   +0x224, Self at [ebp-4] in FormCreate.
   **Cave space:** CODE slack exhausted ⇒ also using DATA tail slack VA
   0x46AEC0-0x46B000 (320 B), which required marking **DATA executable
   (characteristics 0xC0000040 → 0xE0000040)**; variables in the BSS tail
   0x46BA40+ (zero-filled, past the app's last global 0x46BA34). Relocs under
   all displaced ranges neutralized on apply / restored on revert (4 entries).
   ★★ **LESSON (cost a full wrong-apply): the DATA section's VA→file delta is
   NOT the CODE one.** DATA: file = VA − 0x401200 (CODE: VA − 0x400C00). The
   first cut used the CODE delta and wrote the caves 0xC00 bytes early into a
   zero gap — the "cave is empty" assert still passed and the hooks pointed at
   zeroed slack. Script now **reads every cave back through
   `pe.get_offset_from_rva`** after building, which catches exactly this.
   ★★★ **BUG THAT SHIPPED TO THE USER — VMT+0x18 IS `SetName`, NOT
   `SetParent`.** Symptom: clicking Settings raised an "Error" dialog whose
   text rendered as `"▯▯C` — i.e. Delphi's `'"%s" is not a valid component
   name'` with an OBJECT POINTER formatted as the name, because ensure_box
   called `[vmt+0x18](checkbox, DeveloperSheet)`. Real map (Delphi 3 TControl):
   **+0x18 SetName** (0x41C7E4 — recognisable: csDesigning test, GetText,
   compare with FName at +8, then inherited SetName 0x4111E4) ·
   **+0x3C SetParent** (0x41C8CC — compares FParent at **+0x24**, raises the
   "cannot have itself as parent" resstring @0x46ADFC) · +0x28 GetClientOrigin ·
   +0x2C GetClientRect · +0x4C SetBounds (`ret 8`). ⚠ I had inferred +0x18 from
   CreateMessageDialog, where that call is really `Button.Name := …` — **a
   single call site is not enough to identify a VMT slot; confirm the callee's
   BODY does what you think.**
   ★ **AGENT SELF-TEST RECIPE (this is what found it — reuse it):** Windows
   forces UAC only on the *filename* heuristic, so **copy AoWSetup.exe →
   AoWCfg.exe and the copy launches unelevated**, fully drivable:
   `scratchpad/t.py` (kill → copy → optional byte-patch → launch → click →
   report) + `stage.py` (build a cave up to stage N to bisect inside it).
   Gotchas learned: the form is **borderless/skinned** so DFM coords mislead —
   click by window ratio (Settings ≈ 0.62/0.951, Play ≈ 0.15/0.951, Developer
   tab ≈ 0.226/0.092); the app is **DPI-unaware** so the harness must call
   `SetProcessDpiAwareness` before GetWindowRect/ImageGrab; **VCL recreates the
   form's HWND when the settings screen opens**, so re-find the window after
   any click or you'll read a dead handle (looks exactly like a crash);
   `IsWindowVisible` (not handle existence) tells you a page actually opened;
   and read `CBVAR`/`BUF` straight out of the process with ReadProcessMemory to
   see whether cave code ran. End-to-end proof used
   `Get-CimInstance Win32_Process` to read AoWx.exe's command line.
   **Next free AoWSetup cave ≈ 0x469990, slack ends VA 0x469A00.**

**AoWSetup RE MAP (Delphi 3, VA = file + 0x400C00, base 0x400000, exe =
loads at preferred base but DOES have a .reloc dir; ⚠ launching it needs UAC
elevation — "Setup" name triggers the installer heuristic, can't smoke-test
from the agent shell):**
- TLoaderForm methods: FormCreate 0x468A2C · install-check fn **0x468618**
  (getter → nonempty? → +'\aow.exe' → FileExists 0x407194) · StartAoWBtnClick
  0x468808 (getter + '\aow.exe' @0x4688E0 → PChar → launch 0x467F24) ·
  StartAoWEdBtnClick 0x4688F4 · SettingsBtnClick 0x4689F4 · SettingsOk
  0x469090 · SettingsCancel 0x469344 · FormDestroy 0x468E48.
- Root-Directory getter **0x467584** (the ONLY reader; also feeds FormCreate
  dictionary path): obj @[0x46BA34], generic read 0x46719C(eax=obj,
  edx='General', ecx='Root Directory', stack: default, out) `ret 8`.
- Fields: DeveloperSheet +0x224 · DebugMode +0x22C · LogTokenEvents +0x234 ·
  AutoDebugSave +0x238 · StartupDirectoryEdit +0x230 · InstallPnl +0x260 ·
  StartAoW/Ed/Settings/Exit btns +0x250/254/258/25C (graphic-button class,
  no hwnd). FormCreate enables Start buttons from 3× install-check calls
  @0x468D3C/54/6C; not-installed branch je @0x468A62→0x468B59.
- ⚠ Start button launches **aow.exe** (not AoWx.exe) from the path.
- Cave slack: fsopt cave at 0x468C10-area holds "Fullscreen (Optimized)";
  zero run was file 0x68CD9..0x68E00.
**Open:** user to verify full menu + Developer tab; do the dev options'
registry values (DebugMode/LogTokenEvents/AutoDebugSave — likely game-read
booleans) still do anything in AoWx? LogTokenEvents could help TE debugging.

**Cheat WORDS RE (2026-09-01, for the manual's Cheats section):** after
Ctrl+Shift+C sets [kbhandler+0xC]=1, typed chars are buffered ([esi+8]) and
prefix-matched against a 10-string table (const copy @file 0x1E7B78:
gold, mana, explore, fog, spells, win, freemove, towns, lose, research;
runtime table read @0x558E8D7C, loop edi=10..0 @0x55773FA1). A full match
builds a **TCheatTE** (class cell [0x5571D03C]->VMT 0x5571D07C) with
[te+0x10]=player, [te+0x14]=word index, sent through the TE queue (MP-safe;
flag resets after each word -> re-press Ctrl+Shift+C per cheat).
**TCheatTE.Execute = VMT+0x4C -> 0x5574AF10**, switch on [self+0x14]:
0 gold=+1000 gold ALL players ([plr+0xC4]+0x3E8 via SetGold 0x55751F38) ·
1 mana=+1000 mana ALL ([plr+0x54]+0x24) · 2 explore=toggle [engine+0xC9] ·
3 fog=toggle [engine+0xC8] · 4 spells=toggle all-castable ([magicctl+0xC],
copied to ALL players) · 5 win=[+0x244]vt+0x78 cl=1 · 6 freemove=toggle
[engine+0x138] · 7 towns=every independent (player 0) object of classid
0x20108 (town) gets [obj+0x1F0](dl=player) = joins cheater · 8 lose=cl=2 ·
9 research=ALL players get all spells researched ([plr+0x54]+0x30 loop).
