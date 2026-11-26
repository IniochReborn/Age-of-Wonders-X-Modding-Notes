---
name: oos-421-leadership-retreat
description: "10/21 LAN OOS after a leader retreated from a tactical site combat (observer still saw the aura); static RE found NO machine-local aura path, root cause open, no fix written"
metadata:
  node_type: memory
  type: project
  originSessionId: 511f9df3-964c-401e-b2ff-e5d99b017377
  modified: 2026-10-22T02:02:28.356Z
---

**Report (user, 10/21, clean 1.37.420 over LAN):** a player explored a site in tactical combat. His Leadership leader retreated while the rest of his party fought on. The OBSERVER (a non-participant) still saw the leadership bonus on the remaining units. The user ASSUMES the owner's screen dropped it (unverified). OOS came shortly after.

**Static RE 10/21 (no fix written, because the root cause is not established):**
- Flee = `TCombatMoveTE.ExecuteDefaultMove` (TCPCK 0x408278). The hex has a TFleeLocation (vcall +0x7C, id 0x220528). The unit side is checked against `[[[[0x469420]]+0xE4]+0xC]+0x25`.
  - Then `TCombatUnit.SetStatus(8)` 0x557256BC writes the WHOLE status byte, so bit 4 (in party) is cleared. `TCombat.CheckTerminate` follows.
  - The HS is then freed (0x40842C) and `[cu+0x60] := 0`. This is a synced TE, and it has no party or army or formation side effects.
- The aura is computed ONLY by `TArmy.UpdateFormation` 0x5578D034. Its callers are `TArmy.Update`, `TCombatUnit.SetParty` 0x55725094, and mod cave 0x5580E14C (after the ability merge). `TArmy.Update` is reached from `TArmy.Changed` (VMT +0x88), Activate, ToggleGuard, AoWTer, and FireBarrier.
- `TCombatUnit.UpdateParty` 0x557250E0 (requires status bit 4) → `SetParty(nil)` → `unit.SetArmy(nil)`. It is reached only from `TCombatUnit.Activate`/`Deactivate` (VMT +0xBC/+0xC0, from TCombat.Activate/Deactivate at combat start/end, and `TCombatObject.Destroy`) and from the Miracle cave 0x5584E12A.
- AoWx.exe and TCPCK import NO army/formation/ability-changing functions (exe: only `TArmy` getters).
- ⇒ In vanilla flow, the fled leader stays in its TArmy, so the aura persists on EVERY machine until combat ends. **The observer's view is the expected synced state. Owner-side loss is unproven.**
- Checked as NOT the cause:
  - `TFleeLocation.NewFrame` reads the seat `[TCmap+0xEC]`, but only for the visual fade.
  - Site observer-vision cave TCPCK 0x438500 (`build_mp_site_observer_vision.py`): on the observer it seats the explorer, i.e. `SetSeatedCombatPlayer` → `[TCmap+0xA5] :=` the explorer's id, then `[TCmap+0xEC] := 0xFF`. It is re-seated every turn because its skip check compares against 0xFF (cosmetic bug). Readers of `[+0xA5]`/`[+0xEC]` in TCPCK are camera, cursor, selection and display. Not audited exhaustively: EndTurn+0x44, SetAuto, Surrender, Select.
  - AoO awareness skips fled units (`[obj+0x47] & 9`).

**Next step:** verify instead of guessing. Run the read-only `patch scripts\leadership_probe.py` (bit/record/borrowed/cache per party) on the OWNER and the OBSERVER right after a leader retreats, and diff the two. If the owner really drops the aura, hunt the local caller (hardware write-watch on a follower's `[rec+0x10]` via `diag_hwbp.py`). If they match, the OOS is elsewhere: use the desync logger, see [[lan-desync-investigation]].
- Design question still open for the user: SHOULD a retreated leader's aura end mid-combat? Vanilla keeps it.

Related: [[aowx-leadership]], [[oos-420-superstack-getbusy]].
