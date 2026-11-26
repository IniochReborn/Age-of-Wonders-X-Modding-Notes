---
name: raise-terrain-underground
description: "Raise Terrain underground/lava — FAILED ATTEMPT, fully reverted 2026-07-05; keep for RE notes (spell 0x13, terrain/overlay enums, TRaisedMountain, HSS format) and next-time diagnostic leads"
metadata: 
  node_type: memory
  type: project
  originSessionId: ad93df79-b27b-4162-be65-6e3ee8569741
  modified: 2026-08-30T23:08:54.264Z
---

# ✅ MYSTERY SOLVED 2026-08-30 — see [[los-terrain-lavadirt]] §2b
The unknown gate was NEVER in the ValidTarget* functions: TGlobalTargetSpell's target-error routine @0x5579E73C checks **[spell+0x39], a surface-only flag** set in TRaiseTerrain.Create (@0x557A3579), extracts the target's level via 0x5577ED94→pos vmt+0x98, and rejects level≠0 with a resourcestring. Fix = imm byte 0x557A357C 01→00. Underground casting now live via build_raiseterrain_matrix.py. Everything below is the July history (its RE of the TE/mountain/resource machinery remains valid and was reused).

# Raise Terrain underground + lava — ATTEMPT FAILED, FULLY REVERTED 2026-07-05

## STATUS: all changes reverted at user request; retry planned later
- AoWEPACK.dll restored from .bak_raise_terrain_ug — byte-diff confirmed ONLY the 4 raise-terrain regions differed (0xA2758, 0xA29CB, 0xA2A23, 0x10B7C0); all pool/rebuild patches verified intact post-revert.
- Release/Release.hss restored from .bak_raised_earth (Raised Earth clone id 1143 removed; size+CRC verified original).
- Patch scripts remain on disk, NOT applied: patch_raise_terrain_underground.py, patch_raise_terrain_v2.py.

## WHY IT FAILED — unknown gate, the central mystery for next time
User symptoms IDENTICAL through all three iterations (cannot target underground at all; surface lava refused) even after: (1) terrain bt-mask passed Lava(9)/Dirt(12) in BOTH ValidTargetMapF and ValidTargetSelectionMapF (bytes verified in-binary); (2) the [field+15h] overlay≠0 checks NOPed in both; (3) Earth spawn resource present in Release.hss.
⇒ The blocker is NOT (only) in TRaiseTerrain's two Valid* functions. Candidates never ruled out:
- Spell DATA in game data files (AoW1 spells likely carry data-driven properties/target masks — we only ever patched CODE; find where spell 0x13's data record lives and dump it).
- TGlobalTargetSpell fields +38h/+39h (set in Create: [esi+39h]=01) — semantics never resolved.
- Casting-UI/TSpellControl-level pre-check before per-hex validation, or targeting control never querying those hexes (does the level toggle even work during global-spell targeting?).
- Base TGlobalTargetSpell.ValidTargetSelectionMapF's GetExplored([spell+38h]) path behaving differently on those hexes.
- The overlay-0 inference for lava/dirt tiles was BY ELIMINATION, never read from real map data — could be wrong, meaning the real gate was something else entirely from the start.
**NEXT-TIME FIRST STEP (cheap diagnostic): patch TRaiseTerrain.ValidTargetSelectionMapF entry to `mov al,1; ret` (B0 01 C3). If lava/UG still refuse → gate is definitively upstream; binary-search the call chain (who calls ValidTargetSelectionMapF — find the targeting cursor logic in AoWx.exe/AoWEPACK). If they accept → gate is inside and my rewrite missed something subtle.**

## Terrain type enum (from name-list builder at asm line ~102705, AoWEPACK.asm)
0=Water 1=Grass 2=Desert 3=Snow 4=Steppe 5=Wasteland 6=Ice 7=Earth 8=Rock 9=Lava
10=Water2 11=Reserved 12=Dirt 13=Ice2 14=Coast 15=Border 16=Mountain 17=DenseVegetation 18=Hill 19=Vegetation 20=Road 21=Bridge

## Spell 0x13 mechanism (Mountain unit, asm 242414+)
- TRaiseTerrain (spell, ID 0x13 at [spell+10h]) → TargetSelected → TRaiseTerrainTE token → Process → RaiseTerrainTE.RaiseTerrain (file ~0xA26xx).
- TE fields: +20h/+21h x/y, +22h LEVEL (0=surface), +24h caster player.
- TE walks 2-radius hexes; per valid field: saves [field+15h] → [mountain+1Fh], ClearTerrain, spawns TRaisedMountain MO (ClassID 0x2016A) from resource (ClassID 0x2016B), duration [mnt+1Eh]=2-4 turns (Random(11)-5 idiv 5 +3), caster [mnt+1Dh]. TRaisedMountain.NewTurn (msg 0x20020002) decrements; RestoreTerrain places back saved type if >0 (PlaceTerrain). Also restores on msg 0x1132 (TAoWMapField.RestoreTerrain broadcast).
- Mapfield bytes: +14h = effective terrain type, +15h = plain/base tile type (0 once ClearTerrain removed it → the ≠0 check blocks re-casting on raised hexes). Combat setup reads both (+20h/+21h of combat).
- Resource scan (vanilla): first (from end) resource with ClassID 0x2016B && TTerrainList.UsedTerrain([res+28h])==1 → the single-hex "small mountain". Painted terrain = TTerrainList.GetTerrain([res+28h], 0).
- Import thunks (AoWEPACK): TTerrainList.UsedTerrain VA 0x55701CA4, TTerrainList.GetTerrain VA 0x55701C8C (eax=list, edx=hex idx → al, <0 invalid).

## Patch (see MEMORY.md table)
1. Filters at 0xA29CB (ValidTargetMapF) / 0xA2A23 (ValidTargetSelectionMapF): vanilla sub/jz chain blocked {0,6,10,13}; replaced with `movzx eax,[fld+14h]; mov ecx,2541h; bt ecx,eax; jc FAIL` → blocks {0,6,8,10,13} = Water/Ice/ROCK/Water2/Ice2. Lava(9)/Earth(7)/Dirt(12) castable. 14 bytes + 5 NOP in the 19-byte region; jc disp 0x1D to original FAIL label both fns.
2. Scan redirect 0xA2758 (11B): `call cave; test al,al; jnz +6 (accept); nop2` — fallthrough = reject path.
3. Cave 0x10B7C0 (51B, VA 0x5580C3C0): UsedTerrain==1 else reject; GetTerrain(list,0) → al; [esp+4]=TE self → [TE+22h] level; level!=0 (UG): accept only al==7; level==0: accept only al!=7. Preserves ebx/esi/ebp.

## DATA REQUIREMENT (user, in AoWDevEd)
Underground spawn needs a SECOND resource of the Raised Mountain resource class (TRaisedMountainResource, ClassID 0x2016B): single hex (terrain at index 0), painted terrain = Earth (7), earth-fill graphics. Until it exists: underground cast validates but spawns nothing (casting consumed). Surface picks the non-Earth (vanilla mountain) resource. The MO class from ResourceUserClassID (0x2016A) gives the new resource the full temp/expire/restore behavior automatically.

## v2 findings (2026-07-04, after user reported lava+UG still blocked)
- **Mapfield layout CONFIRMED** (HSEPack.dpl disasm via capstone; helper script `hse.py` in project dir parses exports + disassembles): field+10h/11h/12h=x/y/level, **+14h=cached terrain** (topmost HS GetTerrain[vmt+4Ch]≥0, else 0xFF), **+15h=cached overlay** (GetOverlay[vmt+58h], else 0xFF), +1Ah=fog. Updaters: TMapField.UpdateTerrainType/UpdateOverlayType @0x55607df4/0x55607e48.
- **TTerrainList**: [+4]=count, [+8]=array of (terrain,overlay) byte pairs per hex; 0xFF=unused; UsedTerrain counts terrain≥0 entries. GetTerrain/GetOverlay(list,idx)→al.
- **Map composition**: plain tiles = TAbstractHexagon (MO ClassID 0x10170, resource-less-ish, ignore ClearTerrain msg 0x10); decor MOs (forest/shrubs/stones; 789 records ClassID 0x20167 in Release/Release.hss, ~2.7MB) provide overlays 1/2/3/8/9 and die on msg 0x10; plain tile overlays = 4/5 (PlaceTerrain's simple path {4,5}); **lava + UG floor tiles have overlay 0** (inferred by elimination — vanilla [+15h]≠0 check was what blocked lava/UG casts).
- **Raised mountain resource**: EXACTLY ONE 0x2016B record in Release.hss @0xBDF86, no name, uses MOUNTAIN\MOUNTAIN.ILB imagery (why it looks identical to permanent small mountains), terrain list = [(0,0)] → paints terrain0/overlay0 = deliberate re-cast guard (0 blocked by terrain mask, and vanilla +15h≠0).
- **RestoreTerrain logic decoded**: destroy MO (tile underneath survives) → if saved overlay >0, PlaceTerrain re-creates the DECOR that ClearTerrain killed ({4,5}→plain-hex refresh path, else match 0x20167 resource by (fld+14h terrain, saved overlay)). Overlay-0 hexes have no decor → vanilla skip (`test bl,bl; jle`) is CORRECT for them → no RestoreTerrain patch needed.
- **HSS record format**: [classid:4][0x80|nbytefields:1][ndwordfields:4][byte pairs (id,off)][dword pairs (id,off)][data]. Field 6=ShortString name, field 7=terrain list ([count:4][(t,o) pairs]).
- **v2 patch** (patch_raise_terrain_v2.py, bak .bak_raise_terrain_v2): mask 0x2541→0x25C1 (adds Earth(7) → blocks earth-on-earth + re-cast on raised earth) at 0xA29D0/0xA2A28; NOP 7-byte `[fld+15h]!=0` checks at 0xA29DE/0xA2A36 (both were 8A 4x 15 84 C0 74 11). **NOT YET APPLIED — DLL was file-locked (game running); run script when closed.**
- Underground targeting: no level gate found anywhere in validation; if UI still refuses after v2, investigate targeting control/level switching.

## Raised Earth resource clone (2026-07-05) — REVERTED same day (procedure documented for reuse)
- (was) backup Release/Release.hss.bak_raised_earth; v2 DLL patch had been applied same day after file lock cleared.
- New child id **1143** = copy of the raised-mountain record (child id 263): ClassID 0x2016B, terrain list count=1 pair **(7,0)** (was (0,0)), field1 uid bumped 6082AA08→6182AA08. Still uses MOUNTAIN\MOUNTAIN.ILB imagery — LOOKS like a mountain until re-imaged (image refs = fields 8/9 in the record: ILB config @field8, image list with 'MOUNTAIN\MOUNTAIN.ILB' strings @field9).
- Insertion surgery: clone (321B) inserted at abs 0xBE0C7 (after original), new 8B table entry (1143, rel 0xBBC87) appended at children-table end (abs 0x2440), nd 0x476→0x477, 879 sibling offsets ≥ rel(0xBE0C7-0x2440) += 0x141, root's 7 dword-field offsets += 0x149, trailing CRC32 recomputed. All verified by full re-parse (1144 children OK, shifted content byte-identical).

## Release.hss / TEObject storage FORMAT (fully reversed 2026-07-05 — REUSABLE)
- File: [0x34-byte header: dword 0x34(len), ShortStr 'HSS', ShortStr set-name, zeros, misc dwords (unused by game loader)] [object tree from 0x34: `01 00 00` then root property table @0x37] ... [**last 4 bytes = CRC32(file[:-4])** — zlib crc32, checked by THSEngine.LoadHSS @0x5560f75c].
- Property table (TPropertyTable.LoadFromStream @EngineP 0x5550fc3c): [byte b; if b&0x80: dword nd; nb=b&0x7F] [nb × (id:byte, off:byte)] [nd × (id:dword, off:dword)]. Offsets relative to table END (=data start). No record lengths anywhere — reader is offset-driven, so INSERTION requires fixing every ancestor/following-sibling offset.
- Record = [classid:dword][property table][data]. Child object field (rwEObject, id) = table directly (no classid). Children list (rwChildren, field id 1 on TECustomOwner, stack-mode 2): field 1 → a property table whose entries = (child id, offset); each child = full [classid][table][data] record at children-base+offset.
- Release.hss root (THSSet): field2=byte@0, field4=ShortStr name@1, **field5 = MOR owner record @+9** (table {(2,0),(1,1)}, data@+5: field2=byte, field1=children table: dirbyte 0x81, byte-pair (0,0)=child id 0 at offset 0, then nd dword entries ids 1..N; children base = table end). Root dword fields 06/07/0A/0B/11/12/01 = other lists near file end.
- ShortString fields: [len][chars]. TTerrainList field: [count:dword][count × (terrain:byte, overlay:byte)], 0xFF=unused.
- Helper scripts in project dir: **hse.py** (HSEPack.dpl export parser + capstone disasm; exec then dis(NAMES[...]) / find(regex)), **engp.py** (same for Enginep.dpl). AoWEPACK.asm remains best for AoWE code.

## Test checklist
- Rock/Ice/Water invalid everywhere; Earth(7) hexes also invalid (by design).
- Lava surface → mountain, reverts to lava. Dirt/lava UG → earth (needs Earth resource!), reverts.
- Cast on forest/shrub hex still works + decor comes back on expiry (regression check for filter rewrite).
- Data side: duplicate the 0x2016B resource for Earth variant: 1 hex, terrain pair (7,0), earth graphics. DevEd if possible; else I can clone the record binary in Release.hss (format known, but watch for container directory/counts).
