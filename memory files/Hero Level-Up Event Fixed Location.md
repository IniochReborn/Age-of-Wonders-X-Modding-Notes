# Hero Level-Up Event: Fixed Location

**One-line:** In the event log, right-clicking a **hero level-up** entry now centers on the ORIGINAL spot where the level-up happened, instead of following the hero's current position (which let players track enemy heroes).
**Status:** CONFIRMED working in-game, applied 2026-07-23. 2 PIC-safe caves + 1 hook + 1 VMT-slot repoint. Save/MP-safe by design.

---

## Files patched
- **AoWEPACK.dll** (ImageBase 0x55700000; VA = file_offset + 0x55700C00). Backup: `AoWEPACK.dll.bak_heroevt`.

---

## RE findings
The event-log class hierarchy is a Delphi unit with exported class methods.

- **Event class `THeroUpgradeEventLog`**, VMT base **0x55711B88**; **VMT+0x74 = ViewLocation** (the right-click "center view" virtual). Fields:
  - `[+0x18]` = hero ID (4 bytes), resolved by `0x5577E948` (get-unit-by-token) using the map global at `[0x558FA040 + 0xFC]`.
  - `[+0x1C]` / `[+0x1D]` = old / new level (used by GetText).
  - **`[+0x20]` = 4 bytes, SERIALIZED (ReadWrite tag 0x1C @0x55785545) but otherwise UNUSED** -> repurposed to store the captured location (3 loc bytes + a valid flag).
- **`THeroUpgradeEventLog.ViewLocation @0x557857E0`** (the culprit): resolves the hero from `[+0x18]`, calls `GetLocation(hero) @0x5577ED94` (CURRENT loc), and centers via **`TEventLog.CenterViewTo @0x557FD5F4`** (`push level; cl=y; dl=x; eax=Self; ret 4`). Because it recomputes the hero's live location every time, the view follows the hero.
- Base `TEventLog.ViewLocation @0x557FD64C` uses the virtual GetLocation; `THeroUpgradeEventLog` overrides ViewLocation to follow the hero.
- **Battle events (`TCombatEventLog.ViewLocation @0x55729274`) center on a STORED fixed loc** — the desired pattern, copied here.
- **`TEventLogbook.AddEvent @0x557FDB9D`**: runs when ANY event is added, while the hero is still at the level-up spot — the ideal capture point. The original instruction there is `call 0x55775608` (rel32 `E8 66 7A F7 FF`); the hook steals it and re-emits it.

**Reusable trick:** the object's VMT pointer is rebased at load, so you cannot compare `[esi]` to a hard-coded VMT constant. The cave computes the expected VMT base **PIC-style** (`call $+5; pop ecx; sub ecx, here; lea eax,[ecx + 0x55711B88]`) so the compare survives DLL rebasing. Same delta trick reaches the map global 0x558FA040. (This is the standard fix for the "works one launch, crashes the next" rebase bug.)

---

## The patch

### Hook 1 — TEventLogbook.AddEvent -> cave_evtcap
| file off | VA | old bytes | new bytes |
|---|---|---|---|
| 0x0FCF9D | 0x557FDB9D | `E8 66 7A F7 FF` (`call 0x55775608`) | `E9 5E 1A 01 00` (`jmp 0x5580F600`) |

### Edit 2 — VMT ViewLocation slot repoint (THeroUpgradeEventLog)
| file off | VA | old bytes | new bytes |
|---|---|---|---|
| 0x010FFC | 0x55711BFC | `E0 57 78` (…55 = 0x557857E0) | `C0 F6 80` (…55 = 0x5580F6C0) |

VMT+0x74 slot (0x55711B88 + 0x74 = 0x55711BFC) repointed from `ViewLocation 0x557857E0` to `cave_vloc 0x5580F6C0`. Its base-reloc entry is preserved so it rebases correctly.

### Cave 1 — cave_evtcap @0x5580F600 (file 0x10EA00, 118 bytes)
Overwrites a run of zero bytes (free space after the true-seeing caves).
```
0x5580F600: push eax
0x5580F601: call 0x5580F606          ; PIC: get EIP
0x5580F606: pop  ecx
0x5580F607: sub  ecx, 0x5580F606     ; ecx = rebase delta
0x5580F60D: lea  eax, [ecx + 0x55711B88]   ; expected THeroUpgradeEventLog VMT (rebased)
0x5580F613: cmp  [esi], eax          ; is this event a hero-upgrade event?
0x5580F615: jne  0x5580F66B          ;   no -> just replay stolen call
0x5580F61B: mov  eax, [ecx + 0x558FA040]    ; map global (rebased)
0x5580F621: mov  eax, [eax + 0xFC]          ; unit token table
0x5580F627: mov  edx, [esi + 0x18]          ; hero ID
0x5580F62A: call 0x5577E948          ; resolve hero -> eax
0x5580F62F: test eax, eax
0x5580F631: je   0x5580F66B          ; hero gone -> skip
0x5580F637: sub  esp, 4              ; 3-byte loc out-buffer
0x5580F63A: lea  edx, [esp + 2]
0x5580F63E: push edx
0x5580F63F: lea  ecx, [esp + 5]
0x5580F643: lea  edx, [esp + 4]
0x5580F647: call 0x5577ED94          ; GetLocation(hero) -> 3 bytes
0x5580F64C: mov  al, [esp]
0x5580F64F: cmp  al, 0xFF            ; unplaced?
0x5580F651: je   0x5580F668          ;   yes -> skip store
0x5580F653: mov  [esi + 0x20], al    ; store loc byte 0
0x5580F656: mov  al, [esp + 1]
0x5580F65A: mov  [esi + 0x21], al    ; store loc byte 1
0x5580F65D: mov  al, [esp + 2]
0x5580F661: mov  [esi + 0x22], al    ; store loc byte 2
0x5580F664: mov  byte [esi + 0x23], 1 ; valid flag
0x5580F668: add  esp, 4
0x5580F66B: pop  eax
0x5580F66C: call 0x55775608          ; replay the stolen original call
0x5580F671: jmp  0x557FDBA2          ; return to AddEvent
```
Raw bytes (118):
`50 E8 00 00 00 00 59 81 E9 06 F6 80 55 8D 81 88 1B 71 55 39 06 0F 85 50 00 00 00 8B 81 40 A0 8F 55 8B 80 FC 00 00 00 8B 56 18 E8 19 F3 F6 FF 85 C0 0F 84 34 00 00 00 83 EC 04 8D 54 24 02 52 8D 4C 24 05 8D 54 24 04 E8 48 F7 F6 FF 8A 04 24 3C FF 74 15 88 46 20 8A 44 24 01 88 46 21 8A 44 24 02 88 46 22 C6 46 23 01 83 C4 04 58 E8 97 5F F6 FF E9 2C E5 FE FF`

Note: the cave stores the **same 3 bytes ViewLocation reads** — no need to know which is x / y / level, it just replays them.

### Cave 2 — cave_vloc @0x5580F6C0 (file 0x10EAC0, 38 bytes)
Overwrites zero bytes; this is the new VMT ViewLocation target.
```
0x5580F6C0: cmp  byte [eax + 0x23], 0   ; captured-loc valid flag
0x5580F6C4: jne  0x5580F6CF
0x5580F6CA: jmp  0x557857E0             ; flag=0 -> original follow-hero behavior
0x5580F6CF: push ebx
0x5580F6D0: mov  ebx, eax
0x5580F6D2: movzx eax, byte [ebx + 0x22]
0x5580F6D6: push eax                    ; push level/3rd byte
0x5580F6D7: mov  cl, [ebx + 0x21]       ; cl = y
0x5580F6DA: mov  dl, [ebx + 0x20]       ; dl = x
0x5580F6DD: mov  eax, ebx               ; eax = Self
0x5580F6DF: call 0x557FD5F4             ; TEventLog.CenterViewTo -> STORED original loc
0x5580F6E4: pop  ebx
0x5580F6E5: ret
```
Raw bytes (38):
`80 78 23 00 0F 85 05 00 00 00 E9 11 61 F7 FF 53 8B D8 0F B6 43 22 50 8A 4B 21 8A 53 20 8B C3 E8 10 DF FE FF 5B C3`

---

## Mechanism
When any event is added (hero still at the level-up hex), `cave_evtcap` checks whether it is a `THeroUpgradeEventLog` (PIC VMT compare), resolves the hero, reads GetLocation, and latches the 3 location bytes + a valid flag into the event's serialized `[+0x20]` field. Later, right-clicking the event calls `cave_vloc` (via the repointed VMT slot): if the flag is set it centers on the STORED location; otherwise it falls back to the original follow-the-hero `ViewLocation`.

---

## Landmines & notes
- **Save/MP-safe by design:** `[+0x20]` is already serialized (RW tag 0x1C), so the stored location persists in savegames and network-syncs automatically. Old/pre-mod events have flag byte = 0 (objects zero-init; the field was unused) and correctly fall back to original behavior.
- **PIC is mandatory:** AoWEPACK rebases between launches; comparing `[esi]` to a hard-coded VMT constant, or dereferencing a bare in-image absolute, causes the intermittent "Runtime error 216" crash. The delta trick (compute VMT base and the map global from EIP) avoids it. The repointed VMT slot keeps its base-reloc entry so it rebases too. Emulation-verified at the preferred base AND at a rebased base (0x01170000): capture correct, fallback correct, stack balanced.
- The capture is at `AddEvent`, not the true event-creation factory site (not located). If MP observers can still somehow track, moving the capture to the factory would be the next step — but in testing (SP and MP-in-vision) it centers on the original spot.
- Your OWN hero's level-up also jumps to the original spot (acceptable, consistent with battle events).
