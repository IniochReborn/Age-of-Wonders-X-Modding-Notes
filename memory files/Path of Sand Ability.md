# Path of Sand — new terraform ability (id 0x9F)

**One-line summary:** A new passive ability that is a faithful clone of vanilla **Path of Life** but converts surrounding surface terrain to **Desert (2)** instead of **Grass (1)**.

**Status:** CONFIRMED WORKING in-game (built fresh in our free cave space; PIC/rebase-safe). Ability icon is blank — expected, see notes.

Rebuilt from scratch in our binary (not copied from BXL's version, whose caves overlap ours and depend on his outer-ring/transport-gate mods).

---

## Files patched
- `AoWEPACK.dll` (ImageBase 0x55700000). **VA = file_offset + 0x55700C00.**

---

## RE findings — the vanilla Path mechanism

- **Paths are plain `TEnhancementAbility` objects**, not a special class. Vanilla path ids: Decay `0x44`, **Life `0x45`**, Frost `0x6D`. Category word (`obj+0x20`) = **0x37** (from `word[0x557BCFC0]`).
- **Terrain byte values:** `0`=Water, `1`=Grass, `2`=Desert, `3`=Snow, `4`=Steppe, `5`=Wasteland, `6`=Ice, `9`=Lava, `0xC`=Dirt.

### Registration — `RegisterPassiveAbilities` (~`0x557BC960`)
For each path: `CreateEnhancementAbility` @ **`0x5576601C`** (`EAX`=id, `EDX`=name AnsiString ptr, `CX`=category → builds obj, sets `obj+0xC`=id, `LStrAsg(obj+8,name)`, `obj+0x20`=cx), then `RegisterAbility` @ **`0x55750238`** (`EAX`=ability-control, `EDX`=obj). `EBX` holds the ability-control throughout. Both calls preserve `EBX/ESI/EDI/EBP`.

### Dispatch — `TAbstractUnit.MovedTo` @ `0x55780328`
After a transporter gate (`0x55780416`: suppresses all paths on transporter armies) and a surface gate (`0x55780421`: `cmp byte[field+0x12],0; jne …` skips Life/Decay underground), each path does:
```
mov edx, <ID>            ; path ability id
mov eax, ebx ; mov ecx,[eax]
call [ecx+0x148]          ; GetAbilityEnabled(id)
test al,al ; jz next
; if enabled -> flood-fill radius 1 with a terrain callback:
map.Flood([map_vtable+0xD4], x=field[+0x10], radius=1, unit=ebx,
          cb=<terrain fn>, level=field[+0x12], y=field[+0x11])
```
Vanilla callback pointers: Life `0x557801A4`, Decay `0x557801C4`, Frost `0x557801E4`.

### Terrain callback (ECX = &terrain byte, EDX = field record, RET 4)
Life @ `0x557801A4`: `movsx eax,[ecx]; if ax==6 (Ice) or ax==0 (Water) skip; if field[+0x12]!=0 (underground) skip; else mov byte[ecx],1 (Grass)`. Decay is identical → writes `5` (Wasteland).

---

## The patch

Two hooks + three cave pieces in free exec-cave space at `0x5580F3A0+` (CODE section, large zero gap). All caves are **PIC (position-independent)** — see landmines.

### Hooks (VA: original → redirect)
| VA | file off | original bytes | patched to |
|----|----------|----------------|-----------|
| 0x557804B7 | 0x07F8B7 | `BA 6D 00 00 00` (`mov edx,0x6D` — Frost's id load) | `E9 44 EF 08 00` = `jmp 0x5580F400` (only 4 bytes change; trailing `00` stays) |
| 0x557BC9E9 | 0x0BBDE9 | `E8 4A 38 F9 FF` (`call 0x55750238` — Frost's RegisterAbility) | `E9 92 2A 05 00` = `jmp 0x5580F480` |

### Caves
**cave_sand_cb @ `0x5580F3C0`** (30 bytes) — terrain callback, exact clone of Life's with the terminal write changed `mov byte[ecx],1` → **`mov byte[ecx],2`** (Desert):
```
push ebp ; mov ebp,esp
movsx eax,byte[ecx]
cmp ax,6 ; je out        ; Ice -> skip
test ax,ax ; je out      ; Water -> skip
cmp byte[edx+0x12],0 ; jne out   ; underground -> skip
mov byte[ecx],2          ; -> Desert
out: pop ebp ; ret 4
```

**cave_sanddispatch @ `0x5580F400`** (94 bytes, PIC) — clone of Life's dispatch block for id **0x9F**, re-emits Frost's displaced `mov edx,0x6D`, then returns to `0x557804BC`:
```
call $+5 ; pop edi ; sub edi,0x5580F405   ; edi = load delta (PIC)
mov edx,0x9F ; mov eax,ebx ; mov ecx,[eax] ; call [ecx+0x148]  ; GetAbilityEnabled(0x9F)
test al,al ; jz done
  ... push args (y=[fld+0x11], level=[fld+0x12], radius=1, unit=ebx,
      cb = lea eax,[edi+0x5580F3C0], 0, 0, x=[fld+0x10]) ...
  mov eax,[edi+0x558FA040]   ; map global (PIC via delta)
  mov esi,[eax] ; call [esi+0xD4]   ; Flood
done: mov edx,0x6D             ; re-emit Frost's displaced instruction
      jmp 0x557804BC
```
(`[ebp-4]` = field record; `ebx` = unit/ability-control; delta reg = `edi`, which is dead in MovedTo.)

**cave_sandreg @ `0x5580F480`** (53 bytes, PIC) — re-issues Frost's displaced `call RegisterAbility`, then creates + registers Path of Sand:
```
call 0x55750238            ; Frost's displaced RegisterAbility
call $+5 ; pop eax ; sub eax,0x5580F48A   ; eax = load delta (PIC)
lea edx,[eax+0x5580F3A8]   ; name-string chars ptr  (PIC)
mov cx,word[eax+0x557BCFC0]; category 0x37           (PIC)
mov eax,0x9F
call 0x5576601C            ; CreateEnhancementAbility
mov edx,eax ; mov eax,ebx
call 0x55750238            ; RegisterAbility
jmp 0x557BC9EE            ; back to game  (STANDALONE)
```

### Name string @ `0x5580F3A0`
AnsiString `"Path of Sand"`: `FF FF FF FF | 0C 00 00 00 | "Path of Sand" | 00`; the chars pointer is `0x5580F3A8`.

---

## Mechanism / how it works
At package load, `RegisterPassiveAbilities` registers Path of Sand (id 0x9F, category 0x37) exactly like the vanilla paths, so it shows up in the editor's ability list (registry-driven `ListAbilities` enumerates by category). When a unit with the ability moves on the **surface**, `MovedTo` checks `GetAbilityEnabled(0x9F)` and flood-fills radius 1, calling `cave_sand_cb` on each tile — turning eligible terrain to Desert. Water/Ice tiles and underground moves are skipped, and transports suppress it, all inherited unmodified from the vanilla Path framework.

---

## Landmines & notes
- **⚠️ PIC / rebase-safety is mandatory.** `AoWEPACK.dll`'s load base **varies between launches** (observed rebasing to e.g. `0x01170000`). A cave that dereferences a **bare in-image absolute** (`mov r,[0x55..]`, `mov r,0x55..addr`, `push 0x55..addr`, bare `[disp32]`) is a **latent Runtime error 216 startup crash** — the loader only relocates the game's own refs, not ours. An earlier draft used a bare `mov edx,0x5580F3A8` (name ptr) and `push 0x5580F3C0` / `mov eax,[0x558FA040]`; these were rewritten with the **PIC delta-trick** (`call $+5; pop reg; sub reg,<pop VA>` → reg = load delta; then `lea`/`mov` with `reg+abs`). Use rel32 for calls/jmps (already position-independent). The shipped caves above are all clean.
- **id 0x9F** is a genuine permanent free slot in the vanilla ability range. A collision would raise a loud "Ability already registered" at startup (safe failure → bump the id).
- **Blank icon** is expected: ability icons are keyed per-ability via `LinkToIL`; a brand-new id has no library image. Not a crash. Optional fix: point the ability's `+0x1C` image-seq at an existing Path icon, or add a "Path of Sand" entry to the ability ILB.
- **Relationship to the Weakness-abilities mod:** in our shipping binary, `cave_sandreg`'s final `jmp 0x557BC9EE` is re-pointed to `jmp 0x5580F980` to chain the Weakness-abilities registration onto it. The **standalone** Path of Sand (this doc + `path_of_sand_patch.py`) returns straight to the game. Apply Path of Sand **first**, then the weakness patch, to reproduce the live binary exactly.
- **Revert:** restore `AoWEPACK.dll.bak_pathsand`.
