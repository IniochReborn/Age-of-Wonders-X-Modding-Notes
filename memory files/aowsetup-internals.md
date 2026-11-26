---
name: aowsetup-internals
description: "AoWSetup.exe VCL runtime-UI patch machinery — VMTs, ctors, hook chain, .xmou section"
metadata: 
  node_type: memory
  type: reference
  originSessionId: f9cf769f-4f16-45f7-80e1-b57861214514
  modified: 2026-08-28T03:02:13.141Z
---

AoWSetup.exe (fixed base 0x400000, has .reloc but NO DYNAMIC_BASE → absolute cave addresses safe). Delphi 3 VCL statically linked.

- **VMT derivation validated**: classname shortstring ptr sits at vmt-0x20; find name string, find dword ref to it, VMT = ref+0x20 (verified: TCheckBox 0x430368 matches devtab's proven constant). Ctor = [VMT+0x24] (eax=VMT, dl=1, ecx=Owner → eax=instance).
- VMTs/ctors: TTabSheet 0x438D18/0x43A0A8, TLabel 0x42DD08/0x431CEC, TButton 0x42FCEC/0x434314, TCheckBox 0x430368/0x4345D4, TPageControl 0x4390EC/0x43A378. TControl.SetText 0x41CA24 (eax=ctrl, edx=AnsiString chars-ptr), SetParent slot [vmt+0x3C] (⚠ +0x18 is SetName!), SetBounds slot [vmt+0x4C] (push W, push H, ecx=Top, edx=Left), TTabSheet.SetTabVisible 0x43A32C (eax=sheet, dl), TCheckBox Get/SetChecked 0x434694/0x4346B4. Registry helper 0x4670AC (see devtab script).
- Settings form: MainPageControl @form+0x1E8, SettingsSheet +0x1EC, DeveloperSheet +0x224. Settings hook sites (owned by build_aowsetup_installcheck_devtab.py, now RE-POINTED by build_aowsetup_mouse_tab.py which tail-jmps into the devtab caves): SettingsBtnClick 0x4689F4, SettingsOk 0x469090, SettingsCancel 0x469344 → devtab caves SHOW 0x46AF40 / HIDEOK 0x46AF80 / HIDECAN 0x469990.
- TPageControl.SetActivePage = 0x43A774 (eax=pagecontrol, edx=sheet; found via ActivePage PropInfo RTTI @file 0x385d9 — PropInfo layout: SetProc dword at nameoffset−18). my_show now forces ActivePage:=SettingsSheet on every Settings open (2026-08-23 fix: settings used to reopen on the runtime-created Mouse tab). The mouse-tab script is RE-APPLIABLE in place (refreshes .xmou content + re-points the 3 site jmps).
- **Section .xmou @VA 0x510000 (0x2000, RWX, appended 2026-08-21 by build_aowsetup_mouse_tab.py)**: Mouse tab (stage 2a): runtime-created TTabSheet + data-driven control loop (layout table: {textptr, left:u16, top:u16, w:u16, kind:u8, tabidx:u8}), value labels show the chord VK table read from VCL30.dpl file offset 0xE4770 via kernel32 IAT (GetModuleFileNameA [0x46C158], CreateFileA [0x46C194], ReadFile [0x46C180], WriteFile [0x46C170], SetFilePointer [0x46C174], CloseHandle [0x46C198]); "Reset bindings to default" checkbox → on OK writes DEFAULT_TAB (guarded: only if table readable & byte0≠0). VCL30.dpl IS the config store (game reads the same bytes at startup) — no config file. Stage 2b planned: TEdits + key-name→VK parser writing per-slot values.
- ⚠ kernel32 IAT slot numbers belong to specific import blocks; the ones above are from the first (SysUtils) block and verified present.

- **Settings window title (patched 2026-08-23 by build_aowsetup_xcaption.py, backup .bak_xcaption)**: the Settings UI is a TPanel/TPageControl INSIDE TLoaderForm (the main borderless form; its DFM spans ~0x7e790..0x1097a4 and contains the 398x450 background BMP @0x7eda3). Opening Settings surfaces a caption bar showing LoaderForm's DFM Caption — now "Age of Wonders X" (@0x7e7f1, grown +2) compensated by shortening the dead CD-check message caption (@0x7ec68, −2) so the RCDATA size and everything ≥0x7ec8d (incl. the logo BMP offset) stay put. ⚠ Any hardcoded offset in 0x7e802..0x7ec68 is now +2.

- **Mouse + Hotkeys tabs don't localize (diagnosed 2026-08-25, fix pending)**: both are
  runtime-created by build_aowsetup_mouse_tab.py; their captions ("Mouse"@.xmou VA 0x5104C0,
  "Hotkeys"@0x5104D0/0x51073E) and labels are set via TControl.SetText 0x41CA24 with LITERAL
  string pointers, bypassing Multilizer. The tabs that DO change with the AoWSetup language
  dropdown (Settings/Developer) are NAMED DFM sheets; Multilizer keys translations by
  **(Original-text, ClassName="TLoaderForm" [the FORM class, not the control's], ComponentName
  =the control's Name)** — e.g. ("Developer","TLoaderForm","DeveloperSheet") in AoWSetup.mld.
  The runtime tabs have NO Name set (mouse-tab never calls SetName = VMT+0x18 = 0x41C7E4), so
  the language-change refresh (SetLanguage sites' `mov eax,[form+0x270]; call [vmt+0x34]`, which
  re-iterates form.Components) can't build a key for them → skipped. FIX PLAN: (a) SetName the
  runtime tabsheets/labels (e.g. "MouseSheet"/"HotkeysSheet") in the .xmou creation code;
  (b) add ("Mouse","TLoaderForm","MouseSheet") etc. rows to AoWSetup.mld in each language column.
  Unverified: whether Multilizer's refresh truly re-scans runtime-added Components (the proven
  localizing tabs are all DFM); may instead need a cave hook on LanguageCBChange to re-translate
  the runtime controls via TranslateRStr. Worth a small empirical test before committing.

- **Section .xhub @VA 0x512000 (0x1000 virt/0x200 raw, RWX, appended 2026-08-27 by
  build_aowsetup_modding_button.py, backup .bak_xhub)**: home "Editor" button → "Modding",
  launching X\Modding\AoWxHub.exe. Two dword sites: (1) class-method-table OnCreate binding
  @file 0x677D2 (was FormCreate 0x468A2C) → wrapper @0x512030 (push eax; call FormCreate;
  pop eax; mov eax,[eax+0x258]=StartAoWEdBtn; mov edx,'Modding'@0x512028; call SetText;
  ret) — the DFM caption can't grow in place; (2) StartAoWEdBtnClick's exe-string mov
  @VA 0x46894F (file 0x67D50), devtab's '\AoWDevX.exe' 0x469980 → '\X\Modding\AoWxHub.exe'
  chars @0x512008 (AnsiString -1/len/chars/NUL for LStrCat). ⚠ CHAIN: re-applying the
  devtab patch reverts site (2) — re-run modding_button after it.
  ⚠ **Delphi field-table format: {offset:u32, classidx:u16, name:shortstring} — the
  offset dword PRECEDES the name.** Misreading it as name-then-offset put the wrapper on
  [form+0x258]=SettingsBtn and produced TWO "Modding" buttons (MLD renamed the real one,
  the wrapper renamed Settings); StartAoWEdBtn is 0x254. Fixed 2026-08-27, section
  refreshed in place (the script's --apply is idempotent and re-appliable). Launch flow facts:
  0x468594 = mutex already-running check (not a file check); handler = installdir+string →
  ShellExecute 'open' → Sleep(4000) → form.Close. Home DFM: TSpeedButtons flat MS Sans
  Serif bold at y=416, x=14/106/200/292 w=92; form client 420x525; home BMP 398x450 @file
  0x7eda3. Dict\AoWSetup.mld row (Original='Editor', TLoaderForm, StartAoWEdBtn):
  all 5 translation cols set to 'Modding' (backup .bak_xhub) so a language change can't
  flip the caption back; the Original is the Multilizer key — never change it.

**Why:** any further AoWSetup UI work (stage 2b editing, future tabs) reuses these exact addresses and the chain pattern.

**How to apply:** create controls lazily on Settings open; chain new hooks by re-pointing the site jmps and tail-jumping into the previous owner's caves. Related: [[aowx-project-overview]], [[aowint-cave-map]].

- **Section .xcmp @VA 0x513000 (0x600, RWX, appended 2026-08-31 by
  build_aowsetup_campaign_dropdown.py, backup .bak_campdrop)**: "Campaigns:"
  label + TComboBox (csDropDownList) on the Developer tab, reading/writing
  HKCU General\"Vanilla Campaigns" via raw advapi32. New RE: TComboBox VMT
  0x42F594/ctor 0x4333C0; Style setter = virtual [vmt+0x88] (set BEFORE
  parenting); TWinControl.GetHandle 0x420714 (FHandle=+0xCC) + SendMessageA
  [0x46C4C0] + CB_* messages = the clean way to drive list controls without
  TStrings VMT slots; TControl.Perform @0x41D1A4 (PIC byte-signature from
  VCL30, banked). ⚠ CHAIN ORDER now: devtab -> mouse_tab -> campaign_dropdown
  (SBTN/OK sites -> .xcmp caves -> indirect tails at .xcmp+0xDC/+0xE0 ->
  mouse-tab caves). Cancel site untouched by .xcmp. Re-running mouse_tab
  re-points SBTN/OK to itself -> re-run campaign_dropdown afterwards.
