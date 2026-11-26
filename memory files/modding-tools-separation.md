---
name: modding-tools-separation
description: "Modding tools ship separately from the main mod as of 8/30 — hub greys missing tools, own installer, 407 cut recipe"
metadata: 
  node_type: memory
  type: project
  originSessionId: bc99310d-e7a0-464e-8b38-a64c2704c9e7
  modified: 2026-08-30T21:34:19.761Z
---

Decided 2026-08-30: the X\Modding tools (AoWxBard/Gen/Img/Ink/Quest) ship SEPARATELY from the main mod upload. **AoWxHub.exe stays in the MAIN mod** (it must exist to show the not-installed state; AoWDevX also ships with main).

**Hub behavior (implemented + verified 8/30 via PrintWindow/PostMessage probe):** `modding tools\AoWxHub.py` — per-tool `os.path.isfile` check; missing tools' slabs painted greyed (`SlabButton.set_greyed`: washed pens #8a8178/#7e7468, no hover/press tint, arrow cursor) but stay clickable; clicking one shows a QMessageBox (RichText): "AoWx modding tools not found. Please <a>download</a> and install." — `TOOLS_URL = https://aow.heavengames.com/downloads/lister.php?category=misc` (**user says link will be updated later — it's a constant at the top of AoWxHub.py; rebuild hub after changing**). AoWDevX row never greys. Buttons re-check on click (installing tools while hub open un-greys). AoWSetup itself unchanged — its Modding button still just launches the hub.

**AoWSetup FIX C (guard confirmed working by user 8/30; dialog v2 applied same day, byte-verified):** vanilla StartAoWEdBtnClick tail closed AoWSetup unconditionally after ShellExecute — a missing X\Modding\AoWxHub.exe silently closed AoWSetup (user-reported). `build_aowsetup_modding_button.py` v2 hooks the `push 0xfa0` @0x468974 (5B, no relocs under it) → .xhub guard (@0x5120FC as of v2 dialog): EAX>32 → Sleep(4000)+Close as before; else **MB_YESNO** (MessageBoxA IAT 0x46C1A8) "AoWx modding tools not found. Please download and install.\n\nOpen the download page in your browser?" — Yes → ShellExecuteA (IAT 0x46C710) opens TOOLS_URL — and AoWSetup STAYS OPEN either way (native MessageBox can't hyperlink a word, hence Yes/No instead of the hub's inline link). ⚠ TOOLS_URL constant exists in BOTH AoWxHub.py and this build script — keep in sync when the link changes (re-run script; sites loop now auto-refreshes a stale jmp when the cave layout moves). Bytes 0x468979-0x468985 dead. ⚠ chain rule unchanged: re-applying the devtab patch reverts the launch-string dword — re-run this script after it.

**Tools package (built 8/30, in upload\):** `AoWx_Modding_Tools_1_01_0002.zip` (256MB, drag-drop layout X/Modding/*.exe) + `AoWx Modding Tools Installer (version 1.01.0002).exe` (258.9MB). Built by `patch scripts\installer\build_tools_installer.py` (version auto-read from aowxlib\gui.py VERSION; ships the LIVE X\Modding exes, never dist; `--zip-only` flag) compiling `AoWxToolsInstaller.iss` — a trimmed derivative of AoWxInstaller.iss (same splash/dark style/burgundy bar/SFX/fun-facts ticker; single folder page prefilled from `HKCU\Software\Triumph Studios\Age of Wonders X\General → Root Directory`, validates AoWx.exe present; installs into <game>\X\Modding; deletes stale dot-prefixed + root-level tool copies).

**Main release 407 cut recipe** (dry-run VERIFIED 8/30, not applied):
`py -3.10 build_release_zip.py --prev 406 --next 407 --drop ".AoWxBard.exe;.AoWxGen.exe" --add "X/Modding/;X/Modding/AoWxHub.exe" [--apply]`
- build_release_zip.py gained `--add` (appends new entries; handles files absent from prev zip in the changed-report).
- 406 zip shipped NO X/Modding entries at all but still listed the retired dot-prefixed console tools (gone from disk since the 8/26 GUI rebuilds) — hence the --drop.
- The dry run showed AoWSetup.exe (+512B Modding-button patch) and 6 Dict/*.mld + Splash.BMP changes riding along — this closes the "Installer TODO" from [[modding-tools-plan]] (patched AoWSetup + AoWSetup.mld "Modding" row ship in 407).
- Main installer AoWxInstaller.iss needs NO change (it installs the zip verbatim; its stale-delete block only touches root-level copies, so an existing tools install survives a main-mod update).

**Why:** the split halves the main download (~256MB of PySide6 exes) and lets tools rev independently (tools version 1.01.xxxx vs mod 1.37.xxx).
**How to apply:** after any tool rebuild+deploy, rerun build_tools_installer.py; keep hub in main zip; when the download link changes, edit TOOLS_URL in AoWxHub.py, `build_tools.py hub`, redeploy, and the next 40x cut picks it up. Related: [[aowx-release-process]], [[aowx-installer]], [[qt-dark-mode-win10-fusion]].

**2026-09-01: AoWxHub.exe RENAMED to AoWxSuite.exe** (X\Modding\). AoWSetup's
Modding button re-pointed via build_aowsetup_modding_button.py (HUB_PATH
updated, re-applied; script now tolerates stale in-.xhub pointers when the
cave layout shifts). build_release_zip.py docstring updated: the 407 cut adds
`X/Modding/;X/Modding/AoWxSuite.exe`. Manual: Modding AoWx page now has an
"AoWx Modding Suite" section below AoWDevX describing all five tools.
**Manual gotcha fixed same day**: the Overview page's Installation +
Thanks/Acknowledgements had only ever been updated in the GENERATED HTML, not
in build_manual_from_game.py — regens silently reverted them to the doc's old
zip-install text. Now hardcoded in the builder (overviewitems override).

**9/1 FINAL: AoWxSuite.exe ships with the BASE MOD (zip + installer), NOT the
tools package.** Briefly moved to the tools installer 9/1 at user request,
then reverted the same day: with the suite the tools installer hits 302 MB,
over AoWHeaven's 256 MB upload limit (without it: 246.9 MiB, under). The 407
base zip re-cut with `X/Modding/;X/Modding/AoWxSuite.exe` in --add; tools
zip/installer 1.01.0002 rebuilt without the suite (byte-identical intent to
the 8/30 builds).
