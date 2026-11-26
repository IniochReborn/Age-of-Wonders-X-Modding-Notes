---
name: ai-explores-sites
description: "AI players path to and search exploration sites (build_ai_sitesearch.py) — applied 2026-08-31, awaiting test. Holds the site-search TE mint recipe + TStructureAIPA/ExecuteAI RE."
metadata: 
  node_type: memory
  type: project
  originSessionId: bc99310d-e7a0-464e-8b38-a64c2704c9e7
  modified: 2026-08-31T09:37:48.346Z
---

**Feature (user request 2026-08-31): AI heroes/armies seek out and search exploration sites, MP-safe.** `patch scripts/build_ai_sitesearch.py` (.bak_aisitesearch), APPLIED 8/31 awaiting test. Vanilla gap (same as BXL's AI-item finding): sites' ExecuteAI (VMT+0x1C0 → stub 0x5575E698 `xor eax,eax;ret`) and UpdateAITarget (VMT+0x1C4 → stub 0x5575E69C bare `ret`) are no-ops → AI never paths to nor searches sites; its only loot source is hero drops.

## The two caves (AoWEPACK.dll; next free cave after this = 0x55814840)
- **cave_execai @0x55814780** (repointed into 7 site VMTs +0x1C0): pass ecx∈{1,2} (altar-compatible) → `CanSearch 0x557C1E1C(eax=site, dl=player)` → mint the search TE VERBATIM from the engine's own no-dialog branch (TExplorationSite.Search @0x557C1F34): `[vmt+0x160]` CreateTE (class [0x557146AC]) → `[vmt+0x164]` InitTE (binds class-id via [vmt+0x24] + site x/y/l) → `[te+0x18]=0, [te+0x20]=1` (auto-combat) → `GetTokenControl 0x5570372C([[0x558E9494]]+0x23C, movsx [te+0x13])` → `[ctrl vmt+0x10](te)` submit → `[te vmt+0x2C]` release. Returns 0 always (AIPA drops the site from this turn's worklist; worklist rebuilt every AI turn). PIC anchor for the map holder.
- **cave_updait @0x55814800** (7 VMTs +0x1C4): answers AI-target broadcast 0x1200 (eax=site, edx=ctx{player,relation,mode}, ecx=result rec): mode==0, player!=0 (no neutral raiders), `[vmt+0x1F0]==0` (defenders remain = loot remains) → max-combine **priority 30** into [rec+0] ONLY (never +8/+0xC = gold/mana costs — BXL's warning). 30 < neutral mine (50) < armies/cities → only idle groups detour.
- 7 site classes (enumerated via selfptr+parent walk): TExplorationSite 0x557C1440 (base), TItemExplorationSite 0x557C23BC, TMonsterlair 0x557C2D24, TDungeon 0x557C557C, TCrypt 0x557C64D0, TRuin 0x557C68FC, TPyramid 0x557C6D20. All slots carried relocs → stay valid (in-image VAs).

## MP safety chain (reasoning CORRECTED 8/31 during the RNG audit)
**AIPAs/AI run on ALL machines identically** (Global players are locally simulated everywhere — the engine's sync model; NOT one-machine+broadcast as first documented). Our ExecuteAI therefore mints the search TE on every machine — safely, because every gate (CanSearch, strengths, pass) is deterministic game state, so all machines mint the IDENTICAL token at the identical logical point, exactly like vanilla AI move tokens. ExecuteSearch @0x557C1A20 revalidates at execution; its RNG is the synced stream drawn on all machines equally. Caves draw no RNG themselves.

## RE bank (2026-08-31)
- **TStructureAIPA**: Activate @0x55762594 (gate `[player+0xA6]>0`; fills worklist [aipa+0x18] with every registered structure id [s+0x1C]); Execute @0x557625F4 pops+resolves via [map+0x100] registry, calls `[vmt+0x1C0](eax=struct, dl=[player+0xA6]=player idx, ecx=[aipa+0x14] pass)` → al = keep-queued/pause. **ExecuteAI = slot +0x1C0; UpdateAITarget = slot +0x1C4** (dispatched from TStructure.MapFieldMsgProc @0x5575F730 on msg 0x1200 with edx=[msg+8] ctx, ecx=[msg+0xC] rec; site marks stop-propagation when [rec]<0... msg 0x1124→+0x188, 0x1102→+0x180, 0x1103→+0x184, 0x1126→+0x170, 0x1127→+0x16C, 0x1131 sets [msg+0xC]=1 when [field-obj +0x45]).
- **TAltar.ExecuteAI @0x557CF2B0** = vanilla model: gate owner==dl + pass 1|2, find own army within 12 hexes (0x557CC7D0), mana-budget check ([player+0x8C]→[+0x38], 0x55736B38), then order minting. (Not copied — sites use the simpler search-TE path.)
- **CanSearch @0x557C1E1C**(site, dl=player): `[vmt+0x1F0]` (site "cleared" test: roster [site+0x3C] count==0 — TDungeon [.+0x38]; base class hardcodes al=1=cleared) must be 0, AND [site+4]→GetObjectOfType(0x20217 TArmyHS)→[.+0x1C]→owner[+0x12]==dl.
- **TMine.UpdateAITarget @0x557B4498**: ctx mode switch ([ctx+2]); mode0: skip own/razed; **neutral (owner 0) mine priority = 0x32 (50)**; else diplomacy 0x5575B974.
- Search chain constants: Search slot +0x200 @0x557C1E5C; ExecuteSearch slot +0x1FC @0x557C1A20; ExecuteTE @0x557C1D28 (TE+0x18==0 → ExecuteSearch(dl=[te+0x20]) → 1 kept/2 done); combat-type request log created from classref [0x557172AC], its +0x18 = chosen type (0 cancel/1 auto/2 tactical), callback @0x557C1DBC.

## v2 (2026-08-31, APPLIED — strength-aware, after user round-1 feedback: "stragglers gather around sites; only attract/search when strong enough; weight attraction by defender strength". v1 base behavior CONFIRMED working first.)
- **Strength metric**: TUnitList.GetStrength @0x55783300 (eax=list, dl=kind 0; sums TAbstractUnit.GetStrength 0x5577F8F4 = lazily-cached (band+10)*[unit+0x34]); TArmy descends from TUnitList so on-site army uses it too. Asking group = TAIGroupControl.GetStrengthMax @0x557389D4 (eax=gc, **dx=kind BITMASK**, dx=1 = kind 0; cached at [gc+0x28+k*4]). Defender roster = **[site+0x34]** (the list ExecuteSearch feeds to combat; +0x3C/+0x38 is the loot/cleared list behind [vmt+0x1F0]). Ratios are scale-free — no calibration needed.
- **Targeting rework**: +0x1C4 dispatch passes only ctx+rec (NO msg → no group!), so v2 reverts +0x1C4 to stubs and instead repoints the 7 sites' **MapFieldMsgProc VMT+0xCC** (all inherited TStructure's 0x5575F730) → cave_msgproc @0x55814A40: chains inherited first, then handles 0x1200 itself with [msg+0x10]=TAIGroupControl. **Ladder (user re-tune 8/31 rounds 2-3): S_def==0 → 100 (city-tier); 2×grp < 3×def → NOTHING; grp≥10×def → 100; ≥5× → 75; ≥3× → 45; ≥2× → 30; else (≥1.5×) → 15.** Max-combined into [rec+0] only.
- **Mint gate** (cave_execai v2 @0x55814780, 0xBB B): after CanSearch, if roster strength ≠ 0, army=[site+4]→GetObjectOfType(0x20217)→[+0x1C]; mint only when 3*S_army ≥ 2*S_def (laxer than the 1.5× attraction bar since groups split). Undefended always mints.
- Note on the user's "undefended site ignored" report: if a site LOOKS undefended but was already looted, [vmt+0x1F0]==1 → correctly ignored. A genuinely unlooted undefended site now advertises 45.
- Cave map: 0x55814780–0x55814840 execai v2, 0x55814A40–0x55814B40 msgproc v2 (0x55814840–0x55814A40 = [[ai-item-loot]]). **Next free 0x55814B40.**

## v2 candidates / watch in test
- Strength gate (roster vs army) before advertising/minting — v1 accepts AI losses (priority 30 keeps them rare).
- Drawn auto-combat → roster survives → AI retries next turn (progressive whittling, intended).
- If AI stacks detour mid-war for sites → lower priority or gate on group behavior.
Related: [[exploration-site-fix]] (human search chain + MP dialog work), [[ziggurat-scrolls-dump]] (BXL AI-item pair = the natural companion feature).
