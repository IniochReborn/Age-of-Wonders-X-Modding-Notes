---
name: editor-patch-audit-2026-08-05
description: Full audit of which AoWDevX editor patches survived the laptop transfer + why the editor may feel laggy here
metadata: 
  node_type: memory
  type: project
  originSessionId: 163b870a-0be3-4c48-b23d-8bb716073fbe
  modified: 2026-08-09T08:54:20.898Z
---

2026-08-05 audit (user reported editor lag returning on laptop): **every editor patch IS present in the shipped binaries** — the lag is NOT a missing patch.

Verified byte-level in `AoWDevX.exe` + DPLs:
- **FrameRate fix (edfps, THE lag fix)**: present — map-view DFM byte @0x751a0 = 60 (vanilla 15). Home PC's AoWDevX was also 60 (all its backups show 60); the "120" bump only ever went to AoWDevEd/AoWEd. Laptop panel is 60 Hz so 60 is the effective max anyway. Detection: scan for anchor `\x09FrameRate\x02`, value byte follows. MapDrawSteps=1 everywhere is DELIBERATE (do not "fix").
- **Toolbar modernization**: present (.rsrc +2560 B, 283 TPanels vs 282 vanilla).
- **dlgdirs v2 / dirmem / inipath / about**: present ([[baked-absolute-paths-gotcha]]).
- **HSEPack mapcursor**, **VCL30 wheel**: present (hooks differ from their .bak files).
- **Autosave**: absent BY DESIGN — Editor_Autosave_Design.md says "APPLIED + LIVE-TESTED + REVERTED"; don't flag as missing.
- Laptop's plain `AoWEd.exe` and `AoWDevEd.exe*` copies = FrameRate 15 (vanilla) — only matters if the user launches those instead of AoWDevX.

Likely real lag causes on the laptop (machine state that never transfers with files):
1. **150% display scaling + no HIGHDPIAWARE compat flag** → AoWDevX is DPI-virtualized (renders at 1280×720 logical, DWM bitmap-stretches 1.5×). Old install entries (Games\Age of Wonders) have HIGHDPIAWARE/DISABLEDWM; the Desktop AoWDevX.exe has none. Fix offered (not applied): add HIGHDPIAWARE to HKCU AppCompatFlags\Layers for AoWDevX.exe.
2. Iris Xe vs home RTX 4090; frame loop is a vblank spin (~25% of a core inherent); laptop power plans throttle.

**Gotcha for tooling: on the LAPTOP `AoWDevX.exe` carried a `~ RUNASADMIN` compat flag (HKCU Layers; likely user-set)** — non-elevated launches fail WinError 740, so editor_probe.py could not launch it until the flag is removed or the probe runs elevated. Also in that session type, GUI apps launched from the shell exited immediately even unsandboxed (renamed copy + vanilla AoWEd both died rc=0) — 8/4 probe sessions could; don't assume probes work without testing.

**HOME PC (2026-08-09):** the DPI-scaling and RUNASADMIN quirks above are LAPTOP machine state (HKCU compat flags don't travel with files) — re-verify before assuming either applies at home; home is the RTX 4090 machine, so the Iris Xe/power-throttle lag causes don't apply.
