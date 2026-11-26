---
name: tcpck-data-slack-map
description: AoWTCPCK DATA/BSS/.idata page-slack owner map (2026-10-18 audit) — check before using any TCPCK scratch memory; Miracle/Sandstorm + heal-log/Oil-VMT collisions fixed by patch_tcpck_slack_fix_v1
metadata:
  type: reference
---
**Fixed 10/18 (patch_tcpck_slack_fix_v1.py, APPLIED, VEH 6):** Miracle latch 0x46BFB0 (inside Sandstorm list) → 0x46BFF0 (refs 0x440C4B/0x440C70/0x440D1A); heal-AI log ring 60→44 slots (imm @0x4394A2) so it no longer overwrites Oil Spring's VMT clone 0x46CDC0 (would crash after many AI heal evals). Owner scripts patch_tc_miracle_v1 / patch_heal_ai_tcpck_v1 updated. Note patch_tc_miracle_v1 dry-run ABORTs because Call of the Dead hooks the same sites in front (expected, LIFO).

DATA page slack (raw end 0x46B800 → page end 0x46C000): 0x46B7C8–0x46B814 hail trace (diag) · 0x46B840 hellfire gate · 0x46B860 repent latch · 0x46B870–0x46B8D8 banshee · 0x46B8E0 banshee_vortex · 0x46B900–0x46BA10 ashes queue · 0x46BA70–0x46BB00 sandstorm stats+table · 0x46BB00–0x46BF10 ashes TRACE (diag) · 0x46BF20–0x46BF38 breath_anim · 0x46BF40 oilgush · 0x46BF44 sandstorm HN · 0x46BF48 sandswirl · 0x46BF4C oilgush_smooth · 0x46BF50/54/58 sandstorm te/cx/cy · **0x46BF5C free** · 0x46BF60 implosion · 0x46BF64 sandstorm N · 0x46BF68–0x46BFE0 sandstorm list · 0x46BFE0 hurlboulder · 0x46BFE4 flashfreeze · 0x46BFE8 suffocate · 0x46BFF0 miracle · **0x46BFF1–0x46C000 free**.
BSS slack (VS end 0x46C0A1 → 0x46D000): 0x46C100–0x46CD90 aoo recorder (DORMANT, RECORD=False; enabling collides with gust/crosswind/heal/oil) · 0x46C640–0x46C6D0 gust table · 0x46C6E0–0x46C6F4 crosswind_fx · 0x46C700–0x46C7D8 gust · 0x46C800–0x46CD90 heal log (44) · 0x46CDC0–0x46CF10 oilspring VMT · 0x46CFA0–0x46CFE8 suspend_fadein.
.idata slack (0x479EC8 → 0x47A000): 0x479EC8 ai_ranged_trace (diag) · 0x479ED0–0x479F98 crashingwave FXT · 0x479FA0–0x479FE8 crashingwave HIT · 0x479FF0 gust family · 0x479FF8–0x47A000 flashflood SIDE.
Added 10/18: 0x46BF38 / 0x46BF3C = breath_anim v2 corridor state. Code zones: 0x450000 ally-enchant · 0x450400–0x450C40 shockwave · 0x450D00–0x450D62 tame · 0x451000–0x4515C2 breath_anim.
