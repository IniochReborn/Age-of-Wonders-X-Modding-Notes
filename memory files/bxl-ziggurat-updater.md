---
name: bxl-ziggurat-updater
description: 2026-10-20 how BXL's Ziggurat auto-update works (PowerShell update.ps1 + scheduled task + GitHub Releases API latest → full Inno installer, SHA-256 from API digest) — reference for a possible AoWx updater
metadata:
  type: reference
---
Files in AoW Ziggurat\Ziggurat\: update.ps1 (whole updater), ZigUpdater.cmd (manual run), version.txt (e.g. 2026.10.19), ZigUpdater.png; .NET AoWzSetup.exe 'Updates' tab writes HKCU\Software\Triumph Studios\Age of Wonders Z\Updater Mode=Ask/Auto/Off (+ Every, LastChecked) and runs update.ps1 -Register. No updater in game binaries. Trigger: per-user Scheduled Task "Ziggurat updater" (logon +2 min, daily 18:00, StartWhenAvailable) → update.ps1 -Scheduled; due if Every days since LastChecked; skips while AoW*/editor/setup processes run. Source: https://api.github.com/repos/BING-XI/Ziggurat-Engine-Mod/releases/latest; asset 'Ziggurat?Setup*.exe' (not *Web*) → %TEMP%; SHA-256 vs API 'digest'. Version = tag_name equality vs version.txt (not newer-than). Apply = run full offline Inno installer /DIR=<game> (Auto /VERYSILENT, Ask /SILENT, manual wizard); custom WinForms parchment dialog. Weaknesses: digest optional (skips check if missing), hash from same API (no signature), unsigned installer (SmartScreen bypass advice), equality version check can downgrade, scheduled script in user-writable folder.
