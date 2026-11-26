---
name: lobby-dropdown-stay-open
description: "MP lobby dropdowns force-close on every lobby update. Static RE 10/22: the full lobby refresh refills each combo's Items, Items.OnChange invalidates the size, and Setup→TAOWComboBox.SetSize collapses it. Proposed fix = an aowInt SetSize override that re-fits instead of collapsing while dropped. NOT built."
metadata:
  node_type: memory
  type: project
  originSessionId: 511f9df3-964c-401e-b2ff-e5d99b017377
  modified: 2026-10-22T07:21:18.697Z
---

**User request (10/22, for 422):** in the MP lobby, an open dropdown (race owner/AI level, AI behaviour, preferred race, …) force-closes whenever another player joins, leaves, or changes something. They want it to stay open. Static research only so far; nothing patched.

## Why it closes (static, high confidence)
- The lobby form is **TScenSetup** in AoWx.exe: published method table at file 0xFCE8, events bound in code 0x4108EA–0x410B52.
  - RacePlayerCBChange 0x412A24, RaceBehaviorCBChange 0x412AC8, PreferredRaceCBChange 0x412534; also TurnsCB, PlayModeCB, LeadersOnMapCB, TacticalCombatCB, AlwaysViewTCCB, AlliedVictoryCB.
- **Full refresh** = 0x411460, called from the form setup at 0x410EC7 and from the TSetupControl update handler at 0x41441B (every lobby message).
  - It Clears and re-adds the items of the global combos/lists.
  - It then calls the per-race-row refresh **0x410F2C** 12 times (0x411946…0x411C53). Arguments: eax = form, edx = race psettings, ecx = RacePlayerCB, and on the stack the behaviour CB, the preferred/other control and labels.
  - The row refresh does `Items.BeginUpdate (0x4014E4) / Clear (vmt+0x40) / ListAvailablePlayers / EndUpdate (0x4014EC)` on RacePlayerCB, the same for RaceBehaviorCB (6 fixed strings), then SetIndex (combo vmt+0xB8 = 0x5981281C).
- aowInt **TAOWComboBox** (VMT 0x59811FCC):
  - Its Items (`[cb+0x11C]`) get `OnChange := [VMT+0x28]` = **TAoWComponent.OnChangeText 0x59802464** (`mov byte [eax+0x2E],0`), set at Create 0x59812484 (`[items+0x1C]`, owner `[items+0x20]`).
  - EndUpdate → OnChange → `+0x2E=0` (size invalid).
  - **TAoWComponent.Setup 0x598033D0** (recursive over children, slot 0x38) calls slot 0x30 = **TAOWComboBox.SetSize 0x598125E0** whenever `+0x2E==0`.
  - SetSize's first instruction is `mov [ebx+0x118],0`, which is the dropped-down flag (−1 open), so the list **collapses**.
  - SetSize ends with `call 0x598030B0` (`+0x2E=1`, `+0xA4=0` repaint, propagates to children).
- The other `+0x2E` invalidators (SetWidth 0x59802FDC, SetHeight 0x59802FE4, ReAlign, Validate) all funnel into the same SetSize. **Hooking SetSize covers every cause.**

## Open/close facts
- Open is inline in CheckMouseDown 0x59813254 (≈0x598133C7…0x598135D0). It sets `+0x118=-1` and `+0x124` vis rows = min(count, max rows `+0x128`). Scrollbar `[cb+0x120]` setup:
  - SetFMin 0x5980C9B8 = 0
  - SetFMax 0x5980C9D8 = count−1
  - SetFPos 0x5980CA28 = top `+0x12C`
  - SetFNum 0x5980C9F8 = vis
  - Visibility: if SB `+0x114==1` and count−1 < vis it is hidden; otherwise the right inset `+0x150` = SB `+0x7C`, and `+0x154` = SB visible.
- Select/close is in CheckMouseUp 0x59813788. It computes index = top + row and **clamps to Count** (0x5981395D), sets `+0x138`, `+0x118=0`, `+0x80` = collapsed height, hides the SB, then fires OnChange `[cb+0x6C]`.
- Draw 0x5981296C row loop: stops at row ≥ Count but reads Items[top+row]. If top + vis > Count after a shrink, that would be an **OOB EListError**, so a fix must clamp top.

## Proposed fix (aowInt only, about 150–200 B, cave 0x59823E80+, free and reloc-free)
Repoint TAOWComboBox VMT slot 0x30 (`0x59811FFC`, has a reloc, so write a VA) to a cave `SetSizeKeepOpen`:
```
if [cb+0x118]==0 or [cb+0x75]==0 → jmp 0x598125E0 (vanilla collapse/recompute)
n = Items.Count; if n<=0 → vanilla
top = min([cb+0x12C], max(0, n − [cb+0x124]))
SB = [cb+0x120]: SetFMin 0, SetFMax n−1, SetFPos top, SetFNum vis; mirror the vanilla SB show/hide + inset (+0x150/+0x154)
call 0x598030B0   ; mark valid and repaint (so it does not re-run every frame and fight SB drags)
```
- **Stale-selection safety:** the items stay LIVE because the refresh rebuilt them, and MouseUp clamps the index to Count.
  - Handlers act on the combo's fixed race row (Tag `[cb+0xC]`).
  - RacePlayerCBChange resolves the player **by name** (PlayerNameToPlayerID, no-op if not found).
  - Behaviour uses a fixed 6-item list.
  - So a selection can never land on the wrong player. The worst case is clicking an entry at the instant the list re-sorts.
- **Cosmetic limits:** vis rows are not regrown while open. Growth beyond vis needs the scrollbar, now shown. A shrink leaves blank rows. Both are fixed on the next open.
- **Compatible with** build_wheel_combo (SetFPos + Update while open) and patch_power_slider_tilt (different cave).

## Live test plan
1. LAN host plus a second instance.
2. Open each dropdown type and keep it open while the other side joins or leaves, changes preferred race, changes its own race or behaviour, chats, and while the host changes turn limits.
3. Expected: the dropdown stays open, entries update, and picking an entry applies to the right race row.
4. Also: wheel-scroll an open list across a refresh, select after a player left (no-op), and check a single-player scenario-setup screen still works.

## 10/22 BUILT, NOT APPLIED: `patch scripts\patch_combo_stay_open_v1.py`
The coordinator applies it sequentially. The script has dry-run, --apply, --revert and --dis; the backup is `aowInt.dpl.bak_combostay`.
- Zone **0x59823E80..0x59824000**: header 'CSO1', code at 0x59823E90, 308 B. Verified zero, reloc-free, and unclaimed (the power-slider tilt patch ends at 0x59823E80). **Next free aowInt cave: 0x59824000.**
- VMT slot 0x59811FFC: 0x598125E0 becomes 0x59823E90. The slot keeps its reloc, so the loader adjusts the absolute VA. The cave uses only rel32 calls and jumps, so it is rebase-safe.
- The cave follows the design above. It sets the inset to the frame width (ILB lookup 0x598018D4 [+0x180]+4 → [+0x20]) before the scrollbar block, the same as CheckMouseDown, and ends with `call 0x598030B0`.
- Revert is surgical: it refuses a partial state.
- Composes with build_wheel_combo (dry-run still says ALL ALREADY PATCHED).
