---
name: summon-dispel-resistance
description: "2026-11-07 summoned units' dispel resistance = level x 2 (vanilla 7 + level): patch_summon_dispel_res_v1 3 bytes @0x557BB205, BUILT not applied"
metadata:
  type: project
---

**APPLIED 11/07, untested** — `patch scripts/patch_summon_dispel_res_v1.py` (.bak_sumdispel; backup already created by the failed first apply = vanilla, fine).
- PassiveAb.TSummonedAbility.GetDefaultDispelResistance @0x557BB1E4 = IsInstance TUnit ? GetUnitLevel (VMT+0xA0 = [[unit+0x40]+0x2F], base tier 1..4) **+ 7** : 0 → vanilla 8..11, not flat 7. Also via SummonSpells.TSummonSpell.GetDispelResistance 0x557E4460. GetDefaultManaUpkeep 0x557BB1B8 = (L+1)×2.
- Rating feeds TEnchantment.DispelChance 0x5577C1A0: clamp(dispelValue − 10×rating + 50, 10, 90).
- Patch `83 C0 07` → `01 C0 90` (add eax,eax) = level×2 (2..8). No relocs; only copy across AoWEPACK/TCPCK/exe.
- AoWEPACK exports: pefile's default parse misses many names — walk the export table manually (10036 names).
- **11/07 v2 APPLIED, untested** (user: "(unit level X 2) + 1 for each medal"): `patch_summon_dispel_res_v2.py` (.bak_sumdispel2): tail 0x557BB202 → jmp cave 'SDR2' 0x558E1400–0x558E1440 (level×2 + TUnit.GetRank 0x5578294C = earned medals from XP ≥10/≥20). Ability-granted medals (0x6B/0x22) NOT counted. Works from vanilla or v1; --revert → vanilla. v1 script now reports OTHER (expected). Next free AoWEPACK cave 0x558E1440.
