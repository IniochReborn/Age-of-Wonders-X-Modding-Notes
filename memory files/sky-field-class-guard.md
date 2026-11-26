---
name: sky-field-class-guard
description: "Unit on a Sky hex crashed the editor/game (sky code read every field object as a hexagon); fix patch_sky_field_class_guard_v1 (ClassID 0x20152 test), applied 11/14, untested"
metadata:
  node_type: memory
  type: project
  originSessionId: 2c63b60f-49b3-44ba-9088-66d07407269f
  modified: 2026-11-14T06:32:44.810Z
---

**Symptom (2026-11-14):** user: editor crashes "putting an elf swordsman on a spring of life". VEH log: AV at AoWEPACK 0x558DB1EF (overlay ext `kindof`), read 0x1B000B28. Not the spring: the hex was Sky (0xE) and the code walked the field object list ([fld+8], count byte [fld+0xD]) reading [[obj+8]+0xC] as hexagon resource RID for EVERY object; a unit has other data at +8.

**Fix:** `patch_sky_field_class_guard_v1.py` — 4 sites (AoWEPACK 0x558DB1DB + 0x558E126B → cave 0x558DBF40; AoWTools 0x5970A05F → cave 0x5970A0C0; AoWTCPCK 0x45B8C3 → cave 0x454520) now require obj.ClassID (virtual slot 0x24) == 0x20152 (THexagon; TAoWHexagon inherits it via HSEPack). Backups .bak_skycls1. APPLIED 11/14, user confirmed the editor no longer crashes. Ship AoWEPACK.dll, AoWTools.dll, AoWTCPCK.dll.

**How to apply:**
- Any new code that walks a map field's object list must class-test the object first (ClassID slot 0x24, or `is` like HSEPack TMapField.FindNoneTransparentHS 0x55607714 = TCPCK thunk 0x401DB4).
- While applied, patch_minimap_sky_v1 reports OTHER and patch_sky_fld_guard_v1 asserts in dry-run; revert this guard before rebuilding/reverting the overlay ext ([[sky-chasm-transitions]]), minimap patch or fld guard ([[map-levels-29-plan]]).
- Next free TCPCK cave after this: 0x454550.
