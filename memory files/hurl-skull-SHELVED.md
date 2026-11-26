---
name: hurl-skull-SHELVED
description: "SHELVED 2026-07-24: new 'Hurl Skull' ability (= Hurl Boulder but death/fire/physical/wall damage). Registers + displays + correct damage types, but a NEW ability id CANNOT fire/target — hurl firing is hardcoded per-id in ~11 combat mechanisms. Reskin an existing hurl is the only reliable path. No files changed (live = bak_weakness_spell)."
metadata:
  node_type: project
  type: project
  originSessionId: ae619055-3278-433b-b71b-cf21e5789ad7
  modified: 2026-07-24T08:28:01.206Z
---

**GOAL (user):** New "Hurl Skull" ability, identical to Hurl Boulder except damage = Death+Fire+Physical+Wall (instead of Physical+Wall).

## HURL ABILITY SYSTEM (fully RE'd)
4 vanilla hurls, all built by **CreateHurl @0x5576ed48**, registered in the hurl-reg function (the `push..;call CreateHurl;RegisterAbility` sequence @**0x5576F5B4..0x5576F6AC**):
| ability | id (eax) | mask | name RStr |
|---|---|---|---|
| Hurl Boulder | 0x18 | 0x180 (Phys+Wall) | HurlBoulderRStr 0x5570985c |
| Hurl Stones | 0x19 | 0x080 (Phys) | HurlStonesRStr 0x55709864 |
| Fire Cannon | 0x2c | 0x180 (Phys+Wall) | FireCannonRStr 0x55709934 |
| Fire Musket | 0x2d | 0x080 (Phys) | FireMusketRStr 0x5570993c |
(HurlFireSkullRStr 0x55709954 is EXPORTED but UNREFERENCED/unregistered — vestigial.)

**Registration call per hurl:** `push p5; push p4; push 3; mov ax,[mask-table]; push eax; push graphic(0x6e-0x71, IGNORED by CreateHurl); edx=name(via 0x55701210 load + 0x557249fc); cl=C; eax=ID; call CreateHurl(ret 0x14); mov edx,eax;mov eax,ebx(control);call RegisterAbility(0x55750238)`.
**CreateHurl(eax=id,edx=name,cl,+5 stack params):** [obj+0xc]=eax=id (THE registered id — NOT the pushed 0x6e-0x71); LStrAsg name→[obj+8]; [obj+0x2b]=mask WORD; [obj+0x28]=p6(3); [obj+0x29]=p8; [obj+0x2a]=cl; [obj+0x2d]=p7. Base ctor 0x5576e5c4 → [obj+0x20]=0x41(category), [obj+0x24]=3. **VMT @0x5571E8D4**: getters at slots +0x10C([obj+0x28]), +0x110(strength calc via [obj+0x29]+HasAbility), +0x118([obj+0x2d]), +0x11C(mask [obj+0x2b]). Damage mask bits: Fire1 Cold2 Ltng4 Magic8 Poison0x10 Death0x20 Holy0x40 Physical0x80, **WALL=0x100**. **Hurl Skull wanted mask = 0x1A1** (Death0x20|Fire0x01|Physical0x80|Wall0x100).

## WHAT WORKED (scratchpad hurlskull.py)
Registered "Hurl Skull" (mask 0x1A1, plain AnsiString name) at a permanent-gap id via check-and-skip on the weakness candidate table (chained off the weakness reg cave's final jmp @0x5580F9E3). Result: **starts clean, shows in editor, displays correct attack + damage types.**

## THE BLOCKER — new id CANNOT fire/target
Attack is selectable in combat but can't pick a valid target (deselects). **Confirmed it's the ID, not the mask** (Boulder-exact mask 0x180 on a new id also can't fire). Ability PROPERTIES are per-object VMT getters (work fine for a new id) — but **hurl firing/targeting is hardcoded by id in ~11 mechanisms / 29 sites**, e.g.:
- Two "add-ability-to-group-list" fns called with ALL 4 hurl ids: **0x557505b8** (→0x557503d4, list built @0x5576F870+) and **0x55779e44** (→0x55779cbc, built @0x557E51F5+). These are the prime targetable/ranged-attack group lists.
- Wall-crush check **@0x5577ED10**: GetAbilityEnabled[+0x148] for ids {0x75 WallCrush, 0x18, 0x41, 0x2c}.
- Damage special-case for 0x2d @0x55781A88 (near ExecuteDamageRole).
**Attempt to add the new id to the two group-lists (0x557505b8/0x55779e44) from the reg cave → BROKE editor visibility**: those add-fns validate the ability's id/ref against the control list and re-insert with exception paths (0x557503d4 reads [obj+0xc], 0x55779cbc reads [obj+0x10]); poking them from the early reg context drops the ability from the editor's list. Dead end for a new id.

## RESUME PATH — RESKIN (only reliable option)
Convert an existing hurl (reuse its id, already in all 11 mechanisms → fires correctly). Patch its reg site: change `mov ax,[mask-table]`→`mov ax,0x1A1` (or repoint) + change the name-RStr pointer to a "Hurl Skull" string. Best candidate: **Fire Cannon 0x2c** (already Phys+Wall like Boulder) or **Fire Musket 0x2d**. Cost: that gunpowder ability becomes Hurl Skull. User SHELVED rather than sacrifice an existing ability.

**STATUS:** SHELVED. No files changed — live = `AoWEPACK.dll.bak_weakness_spell` (complete weakness feature). Scratchpad: hurlskull.py + hurl*.py investigation scripts.
