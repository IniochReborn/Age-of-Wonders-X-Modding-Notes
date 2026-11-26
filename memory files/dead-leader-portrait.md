---
name: dead-leader-portrait
description: "10/22 Events-tab header portrait shows the Leader's Soul unit's face while the leader is dead (patch_exe_soul_portrait_v1, AoWx.exe .xtut 0x648E00); TPInfoW RE"
metadata:
  type: project
---

**User spec (10/22, 422):** first "fade the leader portrait while dead" → CHANGED to: while the leader is dead and the player owns a Leader's Soul unit (0xCE, [[possess-leader-transfer]]), the Events-tab header shows the SOUL UNIT's portrait (possessed unit / possessed hero / Incarnate), following it to each new body; back to the leader's face after resurrect/animate. Name text unchanged. Visual + local only.

**TPInfoW RE (AoWx.exe):** VMT 0x422EC8 (inst 0xA0), instance var 0x45B134 ([0x45A4FC] = &var). Fields: PInfoWin +0x44 (+0x75 visible), EventList +0x54, LeadL +0x58, Turn +0x5C ("Day N" from map+0x174), RShield +0x60, FaceFr +0x74, Player +0x88 (= TPlayer.GetName, the player name, NOT the leader object), Race +0x8C, LeaderCB +0x70. Update/refresh 0x423170 (callers: Events button 0x457457, game setup 0x4551A0, 0x44FE2A). FaceFrDraw 0x423770: GetPlayers thunk 0x402464([map+0x140], [map+0xA5]) → TPlayer.GetFace thunk 0x402424 (= [player+0xD4] VMT+0xF4) at 0x4237F6 (nil test) + 0x42381F (draw face VMT+0x88, edx=^rect, ecx=^drawinfo).
- Unit VMT+0xF4 = GetFace for all classes: TUnit 0x5578283C (unit-window portrait from the gfx resource), THero/TLeader 0x557887DC (face lib), TAbstractUnit/TAdjustableUnit/TWallUnit 0x5577FFE4 (nil). Same image-object draw → the header draws unit portraits fine.
- The header repaints only on window invalidation; nothing invalidates it when the soul moves.

**`patch scripts\patch_exe_soul_portrait_v1.py`** (`.bak_soulface`, zone .xtut 0x648E00–0x649000 'SFP1', 271 B; free tail after the TREALMWIN DFM ending 0x648D56):
- sf 0x648E10: scan [player+0x28] armies/units (VMT+0x54 counts, [[x+8]+4] items) for ability bit 0xCE (inline has-ability: id < [u+0xC], bt [[u+8]]); found → unit VMT+0xF4, nil/none → original GetFace. Dead test = "a 0xCE unit exists" (v3 grants it only when the leader possesses, strips it on return); no AoWEPACK addresses (EPACK can rebase).
- F1/F2 0x4237F6/0x42381F call → sf. tk: TBWorldUpdate 0x457A6C (6 B, after the editor-indicator hook 0x457A4C) → if Events window visible and sf(local player) ≠ last (0x648E04) → FaceFr [+0xA4]=0.
- Scratch-copy tested 10/22 (apply/revert byte-identical); NOT applied, not run live.
