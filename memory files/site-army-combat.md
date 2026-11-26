---
name: site-army-combat
description: 2026-10-18 attacking an army on an exploration site fights on the site's cave map (attacker at entrance, defender inside, bags, no adjacent stacks); patch_site_army_combat_v1 via site MapFieldMsgProc 0x1107 + AddArmy slot hook; site roster defenders NOT added (no 3rd side)
metadata:
  type: project
---
TArmyCombatMoveTE → TCombat.Setup (+0x60) → field msg 0x1107 to the hex; unhandled → AddArmies 0x55727BCC (adds adjacent via 0x5572760C); vanilla only TCity handles it. Site exploration (TExplorationSite.SetupCombat VMT+0x1F4) sets [combat+0x40]=1 + [combat+0x44]=loot list ([site+0x3C], dungeons [site+0x38]); TCPCK map builder reads +0x40 @0x42462F (cave map + bags; unpicked bags returned 0x41CD14). Slot from army location 0x55727764. Patch (zone 0x55819200–0x55819400, `.bak_sitearmy`): 7 site classes' MapFieldMsgProc (+0xCC) → handler chaining build_ai_sitesearch's 0x55814A40, on unhandled 0x1107 with a foreign army on the site sets +0x40/+0x44, adds attacker side 0 (explorer slot) + defender side 1 (slot 1), [msg+0x1C]=1; AddArmy hook @0x55727855 forces slot while dword 0x5590BFC0 ≠ 0. Empty loot list afterwards → site cleared (vanilla rule). Revert BEFORE build_ai_sitesearch. APPLIED 10/18, VEH 6, untested.
**10/19 user decision:** keep as is — site roster defenders do NOT join army-vs-army site battles (3rd hostile side infeasible: 2 side objects, CheckTerminate 0x557274D8, ~105 GetSide callers, 10 bound [0..1] side reads in TCPCK would crash on side 2).
