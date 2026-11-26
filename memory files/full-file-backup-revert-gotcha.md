---
name: full-file-backup-revert-gotcha
description: A patch script's --revert copies a WHOLE-FILE backup taken at apply time, so reverting an older patch silently discards every patch applied to that binary afterwards (bit the 410 cut on 2026-09-23 with the ranged-trace diagnostic); un-hook in place instead.
metadata:
  type: feedback
---

**Rule:** never use `--revert` of a patch script on a binary that received LATER patches. Every script's backup (`backup\<file>.bak_<tag>`) is a full copy of the file as it was when THAT patch was applied; restoring it rolls the binary back to that moment.

**Why:** 2026-09-23, cutting 1.37.410: `patch_ai_ranged_trace_v1.py --revert` (the diagnostic that must not ship) restored `AoWTCPCK.dll.bak_rtrace` from 9/20 14:44, wiping the AoO-type fix, units-per-frame, walk margin, the three group-move patches, breath-line and Ooze. The first 410 zip/installer were built from that DLL before the audit caught it (the Ooze dry-run on the zipped DLL said "vanilla"). Recovery: copy the newest backup of the binary (`.bak_oozeext` = state right before the last patch), re-apply the last patch, then restore the diagnostic's hook bytes IN PLACE from its HOOK_ORIG constants and zero its cave (0x43A300–0x43A500; backup of the pre-unhook state `AoWTCPCK.dll.bak_rtrace_inplace_20260923`), then re-run every TCPCK patch script's dry run until all say ALREADY PATCHED.

**How to apply:**
- To remove one patch from a multiply-patched binary: write its original hook bytes back (the script's `*_ORIG` constants) and zero its cave; restore any reloc entries it neutralised (3→0 back to 3) only if the original bytes contained an absolute address.
- Before any release cut, audit the shipped binaries by running every patch script's dry run against the file INSIDE the zip (extract to a temp path; most scripts accept the path as first positional arg) — expected states: all feature patches ALREADY PATCHED, diagnostics (`patch_ai_ranged_trace_v1`, `build_te_exception_detail`, `build_getchild_caller_probe`, `diag_devx_show_av_details`) vanilla.
- Backup mtimes are copied from the source (`shutil.copy2`), so a backup's mtime = when the binary was last modified before that patch, i.e. the apply ORDER of patches — useful to see what a revert would lose. Related: [[patching-over-relocs-gotcha]], [[aowx-release-process]].
