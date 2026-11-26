---
name: ranged-ability-popup-stats
description: 2026-10-30 ability right-click popup (TInfoBanner) shows base ATK/DMG with UnitIcons art + damage types for ranged abilities; patch_ranged_ability_stats_v1 APPLIED untested; TInfoBanner/TAOWMemo.Draw RE
metadata:
  node_type: memory
  type: project
  originSessionId: 68556280-d707-4a00-a5ee-7f75589fbb89
  modified: 2026-10-30T23:41:40.312Z
---

**Request (10/30):** under every ranged ability's description: ATK + DMG icons with values (BASE only, user: no Marksmanship etc.), then the damage types. The user picked real colour icons over font glyphs / plain text.

**RE:**
- Every ability popup (7 callers: unit window T1AbilityLBMouseDown 0x40AB2C, combat, ...) = `TInfoBanner.ShowInfo 0x40701C(eax=banner [0x45B068], edx=name, ecx=[ability+0x10] Description TStrings)`. TInfoBanner VMT 0x406F44: HeaderLbl +0x44, InfoMemo +0x48 (TAOWMemo, Age8, ItemHeight 10, taCenter, width 100), BannerPopup +0x4C, InfoMemoSB +0x50.
- Ability base fields (from vanilla GetAttackRA/GetRangeRA + generic ctor 0x5576ED48): ATK byte +0x2A, DMG +0x29, RANGE +0x28 (v1 first shipped +0x28 as ATK = wrong), types word +0x2B, shots +0x2D, range +0x24. Ranged classes = TRangedAttackAbility (VMT 0x5571E8D4) + TBolts/TBreath/TFlameThrowing. D3 VMT: -0x20 name, -0x18 parent = ptr to parent's self slot.
- TAbilityControl [AoWHSSet+0x80]: TList [+8] (items +4, count +8), indexed by id.
- Icons: IntGfxMod (TIntGfxMod VMT 0x4039E8, instance var 0x45B03C) .UnitIcons [+0x80]; img 0 ATK, 1 DEF, 2 DMG (15x17).
- TAOWMemo.Draw 0x59819368: per row line = Lines[+0x188][[+0x128]+row]; centre branch draws via `call TImageLibraryFont.SetText` @0x598198A6 (eax font, edx x, ecx y, [esp+4] ctx, [esp+8] str, ret 8). Thunks: GetTextWidth 0x59801884, IL Get 0x598018D4 (img +0x20 w/+0x24 h), ShowClipped 0x59801864 (img, x, y, [esp+4] ctx).

**Patch:** `patch scripts\patch_ranged_ability_stats_v1.py` (backups `.bak_rangedstats` for both files). AoWx.exe 0x407040 → .xtut 0x638900–0x638C00 appends `CRLF #1<UnitIcons ptr hex8><ATK>#2<DMG> CRLF CRLF <types joined ", " + " & " before the last> Damage` (names table ZONE+0x240); aowInt site 0x598198A6 → cave 0x59824400–0x59824600 draws the #1 line as icons + numbers across 2 rows. Types listed: Physical, Magic, Fire, Cold, Lightning, Poison, Death, Holy, Wall (0x100; added 10/30 on request, singular). APPLIED 10/30, untested.

Next free: AoWx.exe .xtut 0x638C00 (to 0x639000); aowInt 0x59824600.
