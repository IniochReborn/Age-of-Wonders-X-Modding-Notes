---
name: reflecting-pool-raze
description: Reflecting Pool raze patch — CONFIRMED WORKING in-game 2026-07-04 (v2 engine + UI patch); full raze-framework RE notes
metadata: 
  node_type: memory
  type: project
  originSessionId: ebf0ca0e-1a05-4d39-8b48-faa4774ae872
---

# Raze framework (AoWEPACK.dll) — findings 2026-07-04

All line refs are into `AoWEPACK.asm` (PE Explorer dump with full symbols — the asm dump has EVERY function name; grep it instead of guessing offsets).

## Why Reflecting Pools can't be razed
- Razeability is a **data flag**: `TStructure.GetRazeable` (asm line 133014) = `mov eax,[eax+08h]; mov al,[eax+58h]; ret` — byte at **resource+0x58**.
- Flag is hardcoded per resource-class constructor, NOT loaded from data files. `TStructureResource.Create` defaults it to 0 (line 135337); razeable classes set 1 (e.g. `TTeleportResource.Create` line 246184: `[esi+58h]=01, [esi+5Ah]=19h, [esi+5Bh]=02`).
- `TReflectingPoolResource.Create` (line 314051) **explicitly sets [esi+58h]=00** — patch point (change to 01).
- Resource +0x5B = rebuild days (used by `TStructure.GetRebuildInfo`, cost fixed 50g); +0x5A likely raze-related param.
- TReflectingPool does NOT override SetRazed/GetRazed → inherits stubs: `TStructure.GetRazed` = `xor eax,eax; ret`, `TStructure.SetRazed` = `ret` (lines 133020/133025). So flipping the flag alone → raze "succeeds" but pool keeps working and can be razed repeatedly.

## Raze flow
`TStructure.Raze` (UI, confirm dialog via TRazeStructureEventLog) → `RazeEx` → network **token** ([vmt+0x160]/[0x164], TTokenManager) → `ExecuteRaze` (line 134863) on all clients (MP-safe). ExecuteRaze: calls CanRaze [vmt+0x1EC]; event log "StructureRazed"; plays image sequences **0x14/0x15** from [resource+0x24] list (skipped safely if nil); ValidateObservation; **[vmt+0x14C](dl=1) = SetRazed(true)**; [vmt+0x1AC].
`TStructure.CanRaze` (line 134418): fails if GetRazed [vmt+0x150]; requires GetRazeable [vmt+0x154]; then requires razing player's units present (combat predictor).

## TReflectingPool layout
- Extends TPlayerStructure. InstanceSize = **0x40**. Fields: +30h owner byte (FF=none), +31h turns-owned counter (serialized tag 7), +34h TBitList victory, +38h current unfog radius (byte, used by UpdateUnfog), +3Ch frame counter (dword). **+39h..+3Bh = padding, zero-initialized → free for a razed flag.**
- `TReflectingPool.ReadWrite` (line 313360) = just `call TPlayerStructure.ReadWrite; ret`.
- Serializer is TAG-based (`lea edx,[field]; mov ecx,TAG; call [stream_vmt+30h]` for byte). TStructure uses tags 0,0x62,0x63; TPlayerStructure tags 5,6,7. Likely version-tolerant (needs verification in EngineP.dpl) — would allow appending razed byte with a new tag.

## TReflectingPool VMT slots (asm lines 313024+, VMT_Entry; class name string at file ~0xD3ED2)
- 0x18 ReadWrite (own), 0xE0 Activate, 0xE4 Deactivate, **0x14C SetRazed (inherited stub), 0x150 GetRazed (inherited stub), 0x154 GetRazeable**, 0x1EC CanRaze, 0x1F0 SetPlayer, 0x204 UpdateUnfog.

## Useful framework behavior (already handles razed generically)
- `TPlayerStructure.SetPlayer` skips ownership change if GetRazed → razed pool can't be recaptured.
- `TStructure.GetTerrainTypeImage`: if GetRazed → generic razed images 0x16/0x17/0x18 (minimap/terrain-type). Main structure image handling for razed via [vmt+0x12C] recompute (Teleport.SetRazed does `[self+14h] = [vmt+0x12C]([self+18h])`) — pool may lack a razed graphic (cosmetic caveat).
- AI: AGCPlugins.TAIGroupRazeControl.ValidateRazeStructure uses same checks → AI would also start razing pools.

## IMPLEMENTED 2026-07-04 — v1: patch_reflecting_pool_raze_v1.py, v2: patch_reflecting_pool_raze_v2.py
Backups: AoWEPACK.dll.bak_reflecting_pool_raze (pre-v1), AoWEPACK.dll.bak_pool_raze_v2 (pre-v2).
| Offset | Change | Purpose |
|--------|--------|---------|
| D47F2 | 00→01 | TReflectingPoolResource.Create razeable flag [res+58h] — SUPERSEDED 2026-07-04 by D47E3 block rewrite below |
| 10B6A0 | cave 8B | GetRazed: `test byte[eax+39h],1; setnz al; ret` |
| 10B700 | cave 58B (v2) | SetRazed: dl=1→ SetPlayer(-1) via [vmt+1F0h] (delists, self unfog, UpdateReflectingPoolsExploration), set bit +39h, UpdateUnfog [vmt+204h] (guarded→refogs); dl=0→ clear bit; both→ recompute [self+14h]=GetTerrainTypeImage([self+18h]) via [vmt+12Ch] (teleport-style, fixes appearance immediately) |
| 10B740 | cave 20B (v2) | PoolVisionPlayer razed-guard: razed pool ([eax+39h]&1) → return 0 (drops out of pool reflection network: cached unfog AND 0x110A live queries) |
| D4630 | 53 56 51 88 14 24 → E9 0B 71 03 00 90 | PoolVisionPlayer entry hook → guard cave |
| 10B6D8 | cave 29B | ReadWrite: call TPlayerStructure.ReadWrite(0x55760F44), then byte +39h as field id 0x70 via [stream_vmt+30h] |
| D3CE0 | VMT+0x18 → 5580C2D8 | ReadWrite hook |
| D3E14 | VMT+0x14C → 5580C300 | SetRazed v2 hook (v1 cave at 10B6B0 zeroed) |
| D3E18 | VMT+0x150 → 5580C2A0 | GetRazed hook |

Cave space used: 0x10B6A0–0x10B6F5 and 0x10B700–0x10B753. 0x10B6B0–0x10B6CD zeroed (was v1 SetRazed).
v1 test results: button worked, animation+sound+raze defenders+realm-tab removal+self vision loss all OK. Two bugs fixed in v2: appearance only changed after save/reload (missing [self+14h] recompute — on load it's recomputed from GetRazed, which is why reload fixed it); other pools' reflected vision persisted (manual Deactivate bypassed SetPlayer's UpdateReflectingPoolsExploration; plus PoolVisionPlayer had no razed check).
Pool vision internals: PoolVisionPlayer(eax=self, dl=player)→AL: true if player (or ally, relation 2) owns ≥1 pool — self state not consulted in vanilla. UpdateUnfog caches applied radius in [self+38h]. UpdateReflectingPoolsExploration walks OWNED pools only ([player+68h] lists) calling [vmt+208h]/[vmt+204h]. MapFieldMsgProc: msg 0x110A = live visibility query → PoolVisionPlayer; 0x110D → NotifyPlayerChanged. Unowned pools' cached unfog only re-evaluates on map-wide fog rebuilds (turn/seat change) — same staleness exists in vanilla on pool capture.

## Rebuild time = 2 turns (patch_pool_rebuild_days.py, 2026-07-04) — backup AoWEPACK.dll.bak_pool_rebuild_days
- Rebuild days = byte [resource+0x5B], read ONLY by TStructure.GetRebuildInfo (`mov al,[ebx+5Bh]`; cost hardcoded 0x32=50g in same fn). Towers/teleports set 02; pool ctor left it 0 → rebuilt next turn.
- Inline rewrite at file 0xD47E3 (16 bytes, TReflectingPoolResource.Create field writes). The `mov [esi+44h],01` was redundant (TStructureResource.Create already sets +44h=01), freed the slot:
  - OLD: `C6 46 44 01  C6 46 45 00  C6 46 64 00  C6 46 58 01` (58h imm was the old D47F2 razeable patch)
  - NEW: `C6 46 45 00  C6 46 64 00  C6 46 58 01  C6 46 5B 02`
- No cave needed. +5Ah (towers set 0x19) is written by many ctors but NEVER read in AoWEPACK — left at 0 for pool.
- 2026-07-04 later: reduced to 1 turn, USER CONFIRMED WORKING — byte at 0xD47F2 (imm of `mov [esi+5Bh]`) 02→01. Backup AoWEPACK.dll.bak_pool_rebuild_1turn. Note: days=1 and days=0 behave identically in TStructure.NewTurn (dec 1→0 fires BuildingDone same call), but 1 displays correctly in GetRebuildInfo UI.

## Rebuild must not grant vision early (patch_pool_vision_rebuild.py, 2026-07-04) — backup AoWEPACK.dll.bak_pool_vision_rebuild
- Bug: ExecuteRebuild → SetPlayer(builder) → TReflectingPool.SetPlayer enlists still-razed pool into [player+68h] (pools-only list; pool enlists/delists ITSELF via [list_vmt+70h]/[+6Ch]) → PoolVisionPlayer's `Count != 0` ownership check passes at rebuild START.
- Fix: helper cave @ 0x10B754 (41B, VA 0x5580C354): EAX=TPlayerStructureList → EAX=1 iff ≥1 item with ([item+39h]&1)==0. Inlines GetStructure ([list+8]→[+4]→items[i*4]); Count via [list_vmt+54h].
- Both PoolVisionPlayer count fetches `8B 10 FF 52 54` (mov edx,[eax]; call [edx+54h]) → `E8 rel32` to cave: file 0xD464F (own list) and 0xD468B (ally loop, relation==2). test eax,eax after each site unchanged.
- Completion is already handled: TStructure.NewTurn → BuildingDone → SetRazed(false) [clears +39h bit], then TPlayerStructure.BuildingDone calls vmt+220h, +208h (UpdateExploration), +204h (UpdateUnfog) → vision resumes immediately once built. Other pools re-lighting for a first-pool owner rides on 0x110A live queries + fog rebuilds, same as vanilla capture.
- PoolVisionPlayer entry razed-guard (D4630 → cave 0x10B740) unchanged — the two patches compose: entry guard = "razed pool grants no vision AT its hex"; this patch = "razed pool doesn't COUNT as owned".

## Rebuild graphics + unraze refresh (patch_rebuild_gfx_and_unraze_refresh.py, 2026-07-04) — backup AoWEPACK.dll.bak_rebuild_gfx
- Image indexes (DevEd numbering = hex): razed = idx 22/23/24 = 0x16/0x17/0x18 (terrain type else/3/5); rebuild anim = idx 25/26/27 = 0x19/0x1A/0x1B. TStructure.GetTerrainTypeImage (file 0x5DAA0, VA 0x5575E6A0) checks GetRazed FIRST → rebuild (razed+building) kept razed image. GLOBAL entry hook → gfx cave 0x10B790 (45B): if [self+24h]!=FF (GetBuilding inline) → return 0x19/1A/1B by edx terrain (3→1A, 5→1B, else 19); else replicate entry bytes (53 56 8B F2 8B D8) and jmp entry+6. Affects ALL structures on slot +12Ch — vanilla razeables (tower/teleport) now show construction imgs during rebuild too; check they have imgs 25-27 or it's a cosmetic regression.
- Image recompute points already in place: ExecuteRebuild recomputes [self+14h] at start (→ now rebuild img), BuildingDone recomputes after [+24h]=FF (→ normal img). SetRazed cave common also recomputes.
- Unraze ext: SetRazed cave jz (0x10B705) retargeted 1C→76 → ext cave 0x10B77D (16B): `and byte[ebx+39h],0xFE; mov eax,ebx; call UpdateReflectingPoolsExploration (VA 0x557D5084, file 0xD4484); jmp cave common 0x5580C327`. Old inline unraze bytes at 0x10B723-26 now dead. Purpose: refresh pool vision on completion turn.
- RESOLVED 2026-07-04, USER CONFIRMED ALL WORKING: rebuild anim shows during rebuild, no vision while rebuilding, vision restored once rebuilt. The earlier "no vision after rebuilt" was fixed by the unraze ext (UpdateReflectingPoolsExploration on completion — vision at other pools relies on 0x110A live fog queries which otherwise only refresh on turn/seat-change fog rebuilds). User says other structures already showed imgs 25-27 in vanilla contexts, so global GetTerrainTypeImage hook is not a regression concern. Completion path reference: NewTurn (msg 0x20020002 → TStructure.MsgProc → [vmt+178h]) → days [+25h] hit 0 → BuildingDone [vmt+19Ch]: event log → SetRazed(0) → [+24h]=FF → img recompute; then TPlayerStructure.BuildingDone → [+220h] UpdatePlayer, [+208h] UpdateExploration, [+204h] UpdateUnfog.
- Vtable map (TReflectingPool VMT, slot offsets): +178h NewTurn, +19Ch BuildingDone, +1A0h ExecuteRebuild, +1C8h Update, +1DCh GetRebuildInfo, +1E0h CanRebuild, +1E4h Rebuild (UI/token), +200h VisibilityRange, +214h StructureCaptured, +220h UpdatePlayer. TReflectingPool.Activate ADDS self to [owner+68h] pool list, Deactivate REMOVES (besides TReflectingPool.SetPlayer enlist/delist); base TPlayerStructure.SetPlayer/Activate/Deactivate manage [player+1Ch] all-structures list. NewFrame/ActivatePoolCentering = pool camera slideshow ([+3Ch] frame counter), not map sprite.

## Serializer verified TOLERANT (Enginep.dpl TEReadStorageStream/TEWriteStorageStream, instsize 0x2C)
- Read vmt+30h (byte field, RVA 0x10344 read / 0xf584 write... VAs 0x55510f44/0x55510184): looks up field ID in record directory [stream+10h]; **missing ID → `mov byte[edi],0`** (zero-fill default). Writer **skips writing value 0**. → new field IDs are fully backward/forward compatible; saves byte-identical unless a pool is actually razed.
- ecx in ReadWrite calls = FIELD ID (not version). `TEObject.ClassVersion` returns 0, irrelevant here.
- Stream vmt: +0x30 byte, +0x2C dword, +0x1C buf(size,id-on-stack), +0x44 (cl=default value!, id on stack — TStructure +24h uses cl=FF default).

## Rebuild cycle (verified closes correctly)
- [self+24h]=builder player (FF=none, default FF via serializer), [self+25h]=days left. GetBuilding = ([+24h]!=FF).
- ExecuteRebuild: CanRebuild → pay 50g → [+25h]=days([res+5Bh], 0 for pools → completes next turn), [+24h]=player; TPlayerStructure.ExecuteRebuild then SetPlayer(builder) — allowed while GetBuilding even if razed.
- TStructure.NewTurn(builder): dec days; at 0 → BuildingDone → event, **SetRazed(false)**, [+24h]=FF, image recompute.
- SetPlayer guard (TPlayerStructure.SetPlayer): razed && !building → ownership change refused → razed pool uncapturable. Pool's own SetPlayer override routes through base → guard applies.

## UI patch (AoWx.exe) — patch_reflecting_pool_raze_ui_v1.py, backup AoWx.exe.bak_reflecting_pool_raze_ui
Engine patch alone showed NO side-window raze button. Cause: the side info window (TIWindow, DFM root `TIWindow.IWindow`, global instance ptr at [0x45A5C4]; AoWx.exe VA = file_off + 0x400C00) selects a per-CLASS handler via a dispatcher at file 0x43388: owned TPlayerStructure → tests TCity/TProductionPlace/TMine/TPowerNode/TFarm/TTower/TAltar (IsClass against IAT class-ref imports); each razeable-class handler ends with "show RazePnl"; everything else (incl. pool — exe has NO TReflectingPool import) falls to a generic handler (0x43344) that doesn't.
- **TIWindow field table (file 0x40d90-0x41414): entry format is [offset:dword][type:word][name:shortstr] — offset comes BEFORE the name** (first read shifted by one entry = wrong). RazePnl=+0x10C, RazeBg=+0x110, RazeBtn=+0x114, SingleButPnl=+0xAC(?), MainBtn=+0x5C.
- AOW control vtable: [vmt+0x6C] = SetVisible(dl). Reset routine (0x419D8) hides RazePnl each refresh; handlers re-show.
- Dispatcher also routes GetRazed structures ([vmt+0x150]) to a "lies in ruins" handler (0x43090 area) → razed pools show ruins text automatically.
- RazeBtnClick (TIWindow method, file 0x41678, VA 0x442278) reads structure from [[0x45A420]]+0xA8, calls CanRaze [vmt+0x1EC] then Raze — fully generic, works for pools unchanged.
- **Patch**: jmp at file 0x43511 (was `E9 E7 00 00 00` → end 0x435FD) redirected to cave at file 0x6BF80 / VA 0x46E380 (.idata tail slack): `mov eax,ebx; mov ecx,[eax]; call [ecx+0x154](GetRazeable); mov dl,al; mov eax,[esi+0x10C]; mov ecx,[eax]; call [ecx+0x6C](SetVisible); jmp 0x4441FD`. ebx=structure, esi=window at that point. Driven by GetRazeable → any future razeable structure falling to generic handler gets the button too.
- .idata section Characteristics 0xC0000040 → 0xE0000040 (+EXECUTE) for DEP safety.
- Note: teleports' handler does NOT show RazePnl in vanilla (they're engine-razeable but had no side-window button either).
- Editor (AoWDevEd) loads AoWEPACK.dll → editor razed-state toggling worked before the UI patch; confirms engine caves.

## Test checklist — USER CONFIRMED WORKING 2026-07-04 (v2). Raze button, animation/sound, raze defenders, realm-tab removal, vision loss, immediate appearance change, cross-pool vision refresh all OK. Not yet explicitly verified: rebuild flow, MP sync, old-save load.
Original checklist:
0. Raze button (torch, RazePnl) appears on owned pool in side window; NOT on other non-razeable structures.
1. Raze button appears on pool with own units standing on it; confirm dialog; event log.
2. Pool stops giving vision after raze; can't be captured by visiting.
3. Save+load with razed pool → stays razed. Load PRE-patch save → pools unrazed, no errors.
4. Rebuild for 50g → next turn owned+working again.
5. MP sync (both clients patched).
6. AI may now raze pools (TAIGroupRazeControl uses same CanRaze).
Known cosmetic: main-map pool sprite unchanged when razed (no razed image in resources); minimap/terrain-type uses generic razed images (0x16-0x18).
