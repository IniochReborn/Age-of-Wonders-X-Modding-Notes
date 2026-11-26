# Weakness Abilities — 8 editor-assignable inverses of Protection

**One-line summary:** 8 new "Weakness" abilities (Fire / Cold / Lightning / Magic / Poison / Death / Holy / Physical). A unit with a Weakness takes **×1.5 damage** of that type (round up) and **−3 RES** vs that type's status effect. A matching Protection cancels it; a matching Immunity wins. Also bumps vanilla Protection's status-resist from **+2 → +3 RES**.

**Status:** DONE & CONFIRMED WORKING in-game (registration + damage + status effects, on both the tactical-combat and spell/strategic damage paths).

> **PREREQUISITE:** this mod's registration is *chained off* the **Path of Sand** registration cave. Apply the Path of Sand patch **first**. (Details in "The patch → chain hook" below.)

---

## Files patched
- `AoWEPACK.dll` (ImageBase 0x55700000). **VA = file_offset + 0x55700C00.**
- Writable BSS scratch used: `WEAK_IDS[8]` at **`0x558FA810`** (the assigned ability ids, index 0..7 = Fire, Cold, Lightning, Magic, Poison, Death, Holy, Physical). BSS at `0x558FA800+` is genuinely writable (a code-section table would give Runtime error 216).

---

## RE findings — the reusable gold

### Damage-type bits
`Fire=0x01, Cold=0x02, Lightning=0x04, Magic=0x08, Poison=0x10, Death=0x20, Holy=0x40, Physical=0x80.`

### Two unit classes with DIFFERENT VMT layouts (critical)
| | Strategic unit | Combat unit |
|---|---|---|
| GetImmunityTypes | `[self+0xEC]` | `[self+0x7C]` |
| GetProtectionTypes | `[self+0xF0]` | `[self+0x80]` |
| RES | `[self+0xCC]` | `[self+0x74]` |
| **HasAbility** | **`[self+0x88]`** | **`[self+0xA8]`** |

The tactical-combat damage funnels use the **combat** unit (`HasAbility [self+0xA8]`). The spell/strategic damage funnel and the status-effect funnel use the **strategic** unit (`HasAbility [self+0x88]`).

### Damage funnels (where ×1.5 is injected)
- **Tactical melee/ranged:** `StrikeDmg1 @0x557269EF` and `StrikeDmg2 @0x55726A6C` (virtual, 4 vtable refs). Roll @ `0x55725EAC`. Each has a "halve if fully protected" block: `prot=[self+0x80]; if (types & ~prot)==0 → dmg=(dmg+1)>>1`. `ebx`=self (combat unit), `edi`=rolled dmg, `si`=`types & ~imm`.
- **Spell / strategic:** `TAbstractUnit.ExecuteDamageRole @0x55781AC4` — the same halve pattern but with strategic getters (`prot=[self+0xF0]`). `ebx`=self (strategic unit).
- (`ExecuteDamageRole` is **not** on the tactical melee/ranged path — hooking only it does nothing for melee, which is why both StrikeDmg funnels are needed.)

### Status-effect funnel (where ±RES is injected)
`TAbstractUnit.ExecuteDamageEffectsRole @0x55781BA4` (1 caller @ `0x55724C3C`, a combat-unit vtable method that passes `[combat+0x4C]` = the **strategic** unit as self → HasAbility `[self+0x88]`). It has **6 per-type blocks** (no Magic/Physical status effect). Each: `imm=[self+0x148](immid) skip; RES=[self+0xCC]; prot mask in [esp+2]; per type: if prot-bit set → edi=RES+N else edi=RES; roll HitRole(0x55725D98)(strength − edi)`. HitRole @ `0x55725D98` takes a single `eax` (= strength − effRES → `*10+50` percentage), preserves `ebx`. **Protection = RES+N (harder to inflict); Weakness = RES−N (mirror).**

Block base strengths: Fire 4, Lightning 6, Poison 3, Death 4, Holy 3, Cold 3.

### Registration recipe (`TEnhancementAbility`)
`CreateEnhancementAbility @0x5576601C` (`EAX`=id, `EDX`=name AnsiString ptr, `CX`=category 0x37) then `RegisterAbility @0x55750238` (`EAX`=control, `EDX`=obj). Both preserve `EBX/ESI/EDI/EBP`.

### The registration blocker & solution (hard-won)
Abilities are stored on a unit as a **linked list** (not a bitmask), but every id must be **control-registered before any unit loads** (both the editor list and unit-load resolve ids via `GetAbility @0x557501C0`). The ability array is built across **interleaved passes** (code-registered abilities + data abilities loaded from `Release.hss`), so:
- IDs **above the vanilla max (~0xA9)** → **Localize.dpl crash** (`TIvDictionary.Translate` on an oversized id).
- IDs **merely free at hook time** → **Runtime error 217 "already registered"** at `RegisterAbility+0x83` (`0x557502BB`), because a later pass claims that slot.
- **Only ids that are NEVER registered by ANY pass (true permanent gaps) are safe.** Found by **unioning all id-enumeration patterns** (direct `C7 /0 [reg+0xC],imm32` id-sets in ctors; `mov [reg+0xC],reg` ← preceding `mov reg,imm`; create-helper/RegisterAbility backtracks; known aggregators) → 146 registered ids, leaving 21 in-range gaps. The strongest are consecutive runs (5-in-a-row = genuine holes): **0x51–0x55, 0x66–0x69, 0x85–0x89**. The registration cave iterates a candidate table, runtime-checks each slot free, and registers the first 8.

---

## The patch

### A. Registration

**Chain hook** — the only thing wiring the weakness registration in:
| VA | file off | original (Path of Sand standalone) | patched to |
|----|----------|-----------------------------------|-----------|
| 0x5580F4B1 | 0x10E8B1 | rel32 `39 D5 FA FF` (Path of Sand reg-cave tail `jmp 0x557BC9EE`) | rel32 `CB 04 00 00` (`jmp 0x5580F980`) |

So Path of Sand's registration cave, after registering id 0x9F, now falls into the weakness registration cave, which finishes and returns to `0x557BC9EE` itself. **This is why Path of Sand must be applied first** — the `E9` opcode at `0x5580F4B0` belongs to Path of Sand's cave.

**Data tables** (VA 0x5580F810…0x5580F915, 261 bytes): the 8 name AnsiStrings, a `NAME_OFF[8]` table of PIC offsets @ `0x5580F8E0`, and the 21-byte **CANDIDATE id table** @ `0x5580F900` (gap ids, strongest first).

**cave_weakreg @ `0x5580F980`** (104 bytes, PIC) — `ebx` = ability-control on entry:
```
push esi/edi/ebp ; call $+5 ; pop esi ; sub esi,0x5580F988   ; esi = load delta
mov eax,[ebx+8] ; mov edi,[eax+4]      ; edi = ability-id array base ([data+id*4])
xor ebp,ebp ; xor ecx,ecx              ; ebp = count registered, ecx = candidate index
loop: cmp ecx,0x15 ; jge end           ; 21 candidates
  movzx eax,byte[esi+ecx+0x5580F900]   ; candidate id
  mov edx,[edi+eax*4] ; test edx,edx ; jnz next   ; skip if already registered
  mov [esi+ebp*4+0x558FA810],eax       ; WEAK_IDS[count] = id
  mov edx,[esi+ebp*4+0x5580F8E0] ; add edx,esi    ; PIC name ptr
  mov cx,0x37 ; call 0x5576601C        ; CreateEnhancementAbility(id, name, cat 0x37)
  mov edx,eax ; mov eax,ebx ; call 0x55750238     ; RegisterAbility
  inc ebp ; cmp ebp,8 ; jge end
next: inc ecx ; jmp loop
end:  pop ebp/edi/esi ; jmp 0x557BC9EE
```
`WEAK_IDS[found]` (index 0..7) ↔ damage bit `1 << found`.

### B. Damage ×1.5

Two mask helpers build a bitmask of the unit's weaknesses by scanning `WEAK_IDS[0..7]` and calling `HasAbility`:
- **cave_weakmask (combat) @ `0x5580FA00`** — `HasAbility [self+0xA8]`, returns mask in `EAX`.
- **strategic weakmask @ `0x5580FC40`** — `HasAbility [self+0x88]`, returns mask in `EAX`. (Lives just past cave_shared.)

Three damage caves, each replacing the vanilla halve block with the weakness-aware version:

| hook VA | orig | redirect | returns to | cave | self getter |
|---------|------|----------|-----------|------|-------------|
| 0x55726A3A | halve block (StrikeDmg1) | `jmp 0x5580FB00` + NOPs | 0x55726A5D | `0x5580FB00` (90B) | combat `[self+0x80]` |
| 0x55726ACF | halve block (StrikeDmg2) | `jmp 0x5580FB80` + NOPs | 0x55726AF2 | `0x5580FB80` (90B) | combat `[self+0x80]` |
| 0x55781B14 | halve block (ExecuteDamageRole) | `jmp 0x5580FCC0` + NOPs | 0x55781B37 | `0x5580FCC0` (90B) | strategic `[self+0xF0]` |

Cave logic (all three identical apart from the getter/weakmask helper):
```
prot = GetProtection(self)          ; combat [self+0x80] or strategic [self+0xF0]
weak = weakmask(self)               ; cave_weakmask / strategic weakmask
si   = types & ~imm                 ; (already in the caller's si/cx)
effP = prot & ~weak                 ; a matching Protection cancels the Weakness
if (si & ~effP) == 0:               ; fully (effectively) protected
    dmg = (dmg + 1) >> 1            ; halve, round up  (vanilla behaviour)
else:
    effW = si & weak & ~prot        ; weaknesses that aren't cancelled by a protection
    if effW != 0:
        dmg = (3*dmg + 1) >> 1      ; ×1.5, round up
```
Immunity already removed its bits from `si` upstream, so **Immunity fully negates and outranks Weakness**.

### C. Status-effect chance (±RES)

**cave_shared @ `0x5580FC00`** (`ret 8`) — args `push found; push strength`:
```
found = [esp+8] ; id = WEAK_IDS[found]
if id != 0 and HasAbility[self+0x88](id):   ; strategic self (via [combat+0x4C])
    sub edi, 3                               ; Weakness: effRES = RES − 3
eax = strength ([esp+4]) ; sub eax,edi ; call HitRole(0x55725D98) ; ret 8
```

Each of the 6 status blocks in `ExecuteDamageEffectsRole` is edited two ways:
1. **Protection add `+2 → +3`**: the `add edi,2` (`83 C7 02`) becomes `add edi,3` (imm at file 0x081020/0x081080/0x0810D2/0x081124/0x081176/0x0811D6, VAs 0x55781C1E/…). This makes vanilla Protection resist +3 and, being applied *before* the weakness subtract, lets a Protection cancel the Weakness; being *after* the immunity skip lets Immunity win.
2. **Tail replaced**: the block's `mov eax,<str>; sub eax,edi; call HitRole` (12 bytes) → `push <found>; push <str>; call 0x5580FC00; nop×3`.

Block map (VA of the `add`, strength, damage bit, `found` index):
`Fire(0x55781C1E, 4, 0x01, 0)`, `Lightning(0x55781C7E, 6, 0x04, 2)`, `Poison(0x55781CD0, 3, 0x10, 4)`, `Death(0x55781D22, 4, 0x20, 5)`, `Holy(0x55781D74, 3, 0x40, 6)`, `Cold(0x55781DD4, 3, 0x02, 1)`.

---

## Mechanism / how it works
At load, the weakness registration cave (chained off Path of Sand) registers 8 new abilities into permanent-gap ids and records them in `WEAK_IDS`. In combat, each damage roll passes through a StrikeDmg/ExecuteDamageRole cave that: cancels a Weakness if the unit also has the matching Protection, lets Immunity fully negate, otherwise multiplies uncancelled-weakness damage by 1.5 (round up). Status-effect rolls pass through `cave_shared`, subtracting 3 from effective RES when the (strategic) unit has the matching Weakness — the mirror of Protection's +3. Because Fire Halo (= fire immunity), Liquid Form (= physical protection) and Blessed (= death protection) are already in the game's immunity/protection masks, they cancel their corresponding weaknesses automatically.

---

## Landmines & notes
- **⚠️ Dependency on Path of Sand.** The registration is wired only by re-pointing Path of Sand's reg-cave tail jump (byte record @ 0x5580F4B1). Apply Path of Sand first; the weakness apply-script asserts the Path-of-Sand tail-jump bytes and refuses (exit 2) if they're absent.
- **⚠️ Two VMT layouts.** Damage caves on the tactical path use combat offsets (`HasAbility [self+0xA8]`, prot `[self+0x80]`); the spell/strategic damage cave and status caves use strategic offsets (`HasAbility [self+0x88]`, prot `[self+0xF0]`). Mixing them silently does nothing or reads garbage.
- **⚠️ Registration id choice.** Only use ids that are *never* registered by any pass. Slots merely free at hook time → Runtime error 217. Ids above ~0xA9 → Localize.dpl crash. The candidate table sticks to verified 5-in-a-row gaps.
- **BSS, not code, for the id table.** `WEAK_IDS` lives at `0x558FA810` (writable BSS). Writing the assigned ids into the code section gives Runtime error 216.
- **Rounding.** Damage ×1.5 = `(3*dmg + 1) >> 1` (round up); halve = `(dmg + 1) >> 1` (round up), matching vanilla.
- **RES modifier N = 3** for both weakness (`sub edi,3`) and vanilla protection (`add edi,3`). Change all seven imm bytes together if you retune it.
- **PIC.** All caves use the `call $+5; pop reg; sub reg,<popVA>` delta trick for data/table refs and rel32 for calls/jumps, so they survive `AoWEPACK.dll` rebasing.
- **Backups:** `bak_weakness_reg` (registration only), `bak_weakness_dmg` (+ damage), `bak_weakness_full` / `bak_weakness_spell` (+ status effects + spell/strategic damage = the shipped state). Pre-feature: `bak_preweakness`.
