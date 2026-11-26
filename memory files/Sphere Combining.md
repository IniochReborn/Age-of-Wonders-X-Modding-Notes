# Sphere Combining — allow opposing element spheres

**One-line summary:** Wizard sphere selection lets Fire/Water and Earth/Air be combined (each opposing pair capped at 4 combined picks); Life/Death remain mutually exclusive.

**Status:** CONFIRMED WORKING in-game. In-place rewrite of one function (no cave).

This mirrors BXL/Ziggurat's change byte-for-byte (both binaries are the same base build 0x55700000, same size 2785792, same function VA).

---

## Files patched
- `AoWEPACK.dll` (ImageBase 0x55700000). **VA = file_offset + 0x55700C00.**

No other files. (Note: matching BXL, `AoWSetup.exe` is *not* touched — if the MP launcher wizard has its own copy of the rule it would need a separate patch. In-game leader customization uses this engine function and is covered.)

---

## RE findings

### The function: `TLeader.CanAddSphere` @ VA `0x5578B1F8`
Delphi convention: `EAX` = Self (leader), `DL`/`BL` = sphere index to add; returns `AL` = 1 (can add) / 0 (cannot).

Prologue (unchanged by the mod):
```
push ebx ; push esi
mov ebx,edx          ; ebx/bl = candidate sphere
mov esi,eax          ; esi = leader
mov eax,[esi+0xA0]
mov eax,[eax+8]      ; eax = current total sphere-pick count
movzx edx,byte[esi+0x9C]  ; edx = max picks
cmp eax,edx ; jge fail   ; global cap check
test bl,bl ; jz fail     ; sphere 0 (Cosmos) rejected here
```
There is also a per-sphere sub-cap check at `0x5578B222`–`0x5578B23C` (reads global `[0x558FA048]+0x6E`, `cmp al,2`) that is **unchanged** by this mod.

### Sub-function: `GetSpherePicks` @ VA `0x5578B17C`
`EAX` = leader, `DL` = sphere index → returns `AL` = number of picks currently in that sphere. Used by CanAddSphere for every opposing-pair test. (Verified byte-identical to BXL's binary.)

### Sphere index enum (from `TMagicSphereRStr` array @ `0x558E8118`)
`0 = Cosmos, 1 = Life, 2 = Death, 3 = Earth, 4 = Air, 5 = Fire, 6 = Water`. (A `TSpell`'s sphere is field `[spell+0x20]`.)

### Vanilla logic (what changed)
Vanilla blocked **all three** opposing pairs symmetrically. For each pair `(a,b)`: `if bl==a and GetSpherePicks(b)!=0 → return 0`. Pairs handled: Earth/Air `(3,4)` at `0x5578B241`, Fire/Water `(5,6)` at `0x5578B255`, Life/Death `(1,2)` at `0x5578B281`. (The early `cmp al,4 / cmp al,2` blocks at `0x5578B236`/`0x5578B24A` are the general per-sphere sub-caps and remain.)

---

## The patch

Two changed byte ranges, both **inside** the function (`0x5578B1F8`…`0x5578B2E4`); the rewrite fits in place, padded with NOPs at the tail (`0x5578B2CD`–`0x5578B2D8`). No cave.

| VA | file offset | length | change |
|----|-------------|--------|--------|
| 0x5578B257 | 0x08A657 | 5 bytes | re-order the pair dispatch |
| 0x5578B26D | 0x08A66D | 108 bytes | new pair logic + NOP padding |

### New logic (LIVE disassembly)
```
; --- Life/Death: UNCHANGED (still mutually exclusive) ---
0x5578B255: cmp bl,1 ; jne +  ; if adding Life
0x5578B25A:   mov dl,2 ; call GetSpherePicks   ; picks in Death
0x5578B263:   test al,al ; jz ok ; else return 0   (fail if any Death)
0x5578B26B: cmp bl,2 ; jne +  ; if adding Death
0x5578B270:   mov dl,1 ; call GetSpherePicks   ; picks in Life
0x5578B279:   test al,al ; jz success ; else return 0

; --- Earth/Air: COMBINED CAP 4 ---
0x5578B281: cmp bl,3 ; je L1 ; cmp bl,4 ; jne skipEA
0x5578B28B: L1: mov dl,3 ; call GetSpherePicks ; push al   ; Earth picks
0x5578B295:     mov dl,4 ; call GetSpherePicks              ; Air picks
0x5578B29E:     pop ecx ; add al,cl        ; total = Earth+Air
0x5578B2A1:     cmp al,4 ; jb success ; else fail

; --- Fire/Water: COMBINED CAP 4 ---
0x5578B2A7: cmp bl,5 ; je L2 ; cmp bl,6 ; jne skipFW
0x5578B2B1: L2: mov dl,5 ; call GetSpherePicks ; push al   ; Fire picks
0x5578B2BB:     mov dl,6 ; call GetSpherePicks              ; Water picks
0x5578B2C4:     pop ecx ; add al,cl        ; total = Fire+Water
0x5578B2C7:     cmp al,4 ; jb success ; else fail

0x5578B2CD: nop*12 (padding)
0x5578B2D9: success: mov al,1 ; pop esi ; pop ebx ; ret
0x5578B2DE: fail:    xor eax,eax ; pop esi ; pop ebx ; ret
```

- **Life (1) / Death (2):** unchanged — any pick in the opposite sphere blocks the add.
- **Earth (3) / Air (4)** and **Fire (5) / Water (6):** replaced with a combined cap — `GetSpherePicks(a) + GetSpherePicks(b) < 4` → allowed, else blocked. So each element pair's *combined* picks can reach at most 4.
- The global top-level cap (`count >= maxpicks`) still applies over everything.

---

## Mechanism / how it works
A wizard building a leader calls `CanAddSphere` for each candidate sphere. The rewrite keeps the Life/Death exclusivity but converts the Earth/Air and Fire/Water "opposite present → forbidden" tests into a shared budget of 4 combined picks per element pair. Both `je` fall-throughs (`bl==3 || bl==4`, `bl==5 || bl==6`) route into the same combined-sum block so the cap is symmetric regardless of which side you add.

---

## Landmines & notes
- **PIC / rebase:** this patch touches only game-relocated code and the existing `call GetSpherePicks` rel32s (self-relative, already position-independent). No new absolute-address dereferences are introduced, so there is no rebase-crash exposure here.
- **Scope:** engine-side only. If opposing spheres are still restricted specifically in the multiplayer setup/launcher wizard, that path may live in `AoWSetup.exe` and would need its own edit.
- **The cap is combined, not per-sphere:** e.g. Fire 3 + Water 1 = 4 is the ceiling; a 5th combined pick is refused even if one side is empty.
- **Revert:** restore `AoWEPACK.dll.bak_spheres`.
