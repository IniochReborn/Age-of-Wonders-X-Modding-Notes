---
name: qt-dark-mode-win10-fusion
description: "PySide6 dark pinning needs Fusion style — Win10's windowsvista style silently ignores setColorScheme(Dark)"
metadata: 
  node_type: memory
  type: project
  originSessionId: bc99310d-e7a0-464e-8b38-a64c2704c9e7
  modified: 2026-08-30T17:41:38.834Z
---

Found 2026-08-30 on the Win10 desktop: the modding suite's `pin_dark()` (in `modding tools\aowxlib\gui.py`) originally only called `app.styleHints().setColorScheme(Qt.ColorScheme.Dark)`. That works on Windows 11 because Qt defaults to the `windows11` style (dark-capable), but on Windows 10 Qt falls back to `windowsvista`, which cannot render a dark palette — Qt keeps the light palette and the call is a silent no-op. Same exes: dark on the Win11 laptop, light on the Win10 desktop.

**Fix (applied 2026-08-30, user chose Fusion-everywhere):** `pin_dark()` now does `app.setStyle("Fusion")` before `setColorScheme(Dark)`. Verified on the desktop: Fusion+Dark → window #1e1e1e / text #ffffff, the exact palette the decoration pass was designed against. All six exes (five tools + hub) rebuilt with it; the hub is fully custom-painted so Fusion is cosmetically inert there.

Also Win10-degraded but accepted: `DWMWA_CAPTION_COLOR` (attr 35) is Win11-only, so the red caption pin on **dialogs** no-ops on Win10 (stock title bars); main windows are fine — they use the custom `GradientTitleBar`.

Desktop build environment (2026-08-30): the transfer README asks for Python 3.12, but the desktop's **py -3.10** works (audioop still present ≤3.12); installed PySide6 6.11.2 + pyspellchecker 0.9.0 into it (PyInstaller 6.21/pillow were present). ⚠ pip on this machine fails `files.pythonhosted.org` with CERTIFICATE_VERIFY_FAILED (self-signed cert in chain — local TLS interception, happens sandboxed AND unsandboxed); workaround: `--trusted-host pypi.org --trusted-host files.pythonhosted.org`.

**Why:** any future PySide6 tool or rebuild must keep the Fusion line, or it ships light-themed to every Win10 player.

**How to apply:** never rely on setColorScheme alone on Windows; pair it with `setStyle("Fusion")`. Related: [[modding-tools-plan]].
