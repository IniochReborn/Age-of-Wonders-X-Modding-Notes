---
name: release-zip-save-folder
description: Release zips must ship the X/Save/ dir entry — fresh installs EFCreateError on first save write without it; build_release_zip.py now guarantees it
metadata: 
  node_type: memory
  type: project
  originSessionId: 70b0ff8a-b3c2-4345-b855-1cee7c352bb9
  modified: 2026-08-15T20:46:56.599Z
---

**Bug (found 2026-08-15):** No release zip 401–405 ever shipped `X/Save/`. The game saves to `<install root>\X\Save\` and Delphi's `TFileStream.Create` won't create parent dirs, so a **fresh** install dies with `EFCreateError in module VCL30.dpl at 0002087A — Cannot create file ...\X\Save\<name>.acg` on the first save write. Vichan hit it on the campaign victory transition (`Escape from the Valley of Wonders_Won.acg`), which presented as "campaign broken on his machine only" — everyone else had upgraded over installs whose Save folder already existed. It was NOT the earlier suspected Program Files permission issue (admin/ACL fixes didn't help); vichan's confirmation of the folder fix still pending as of 8/15 evening.

**Fixes:**
- `upload/AoWx_1_37_405.zip` was hand-patched by the user 2026-08-15 (now 660 entries: added `X/` and `X/Save/` empty dir entries) and reuploaded; players notified.
- `patch scripts/build_release_zip.py` updated for 406+: directory entries in the prev zip's namelist are now preserved (they were skipped before — a cut from patched 405 would have silently dropped the fix), written as proper dir entries (`external_attr = 0o40755<<16 | 0x10`), and `X/` + `X/Save/` are force-added even when cutting from a pre-fix zip. Tested: build from 405 (0 changed), dry run from 404 (auto-add path prints notes), extraction creates the `X\Save` folder.

**Why:** zip archives cannot represent empty directories implicitly, and this script rebuilds each release from the previous zip's namelist — so anything not an explicit entry never ships.

**How to apply:** nothing extra needed for normal cuts; just don't strip dir entries from the namelist. If a player reports `EFCreateError ... Cannot create file` for any path, first check the parent folder exists before suspecting permissions. Related: [[keeper2-armycombatmovete-crash]] (vichan's separate Delgates crash, still open).
