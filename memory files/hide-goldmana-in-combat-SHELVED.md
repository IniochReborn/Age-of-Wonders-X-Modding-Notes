---
name: hide-goldmana-in-combat-SHELVED
description: "SHELVED 2026-07-23. Goal: always hide the gold/mana HUD panels during tactical combat (MP info-leak fix — game already hides them via a flag but inconsistently). RE groundwork found (AoWx.exe WGoldPnl/WManaPnl panels + SetVisible logic); shelved because wiring the combat-active condition needs deep RE in the symbol-less Delphi client. NO files changed (read-only)."
metadata:
  node_type: memory
  type: project
  originSessionId: ae619055-3278-433b-b71b-cf21e5789ad7
  modified: 2026-07-23T09:17:50.825Z
---

**GOAL:** In tactical combat the strategic HUD still shows a player's gold/mana totals+income. In MP this leaks info — the game hides it *most* of the time but inconsistently. User wanted the simple fix: **always hide gold/mana while in tactical combat.** **SHELVED 2026-07-23** ("thought it would be easier") — no binary was modified (pure read-only RE).

**WHY NOT EASY:** the display is in **AoWx.exe** (the client HUD), a LARGE symbol-less Delphi exe with code+data heavily interleaved → linear/backward disasm is unreliable, so recovering the function boundary / tracing the `ebx` hide-flag source / finding a clean "in tactical combat" signal is deep RE. Best future path = **Ghidra decompile** of the resource-update function (headless workflow exists, see [[designer-only-portrait-toggle]]).

**RE GROUNDWORK (AoWx.exe, VA = file + 0x400C00, ImageBase 0x400000):**
- Main game window has **W-prefixed strategic-HUD controls** AND **TC-prefixed tactical-combat controls** (same form). W = the gold/mana display shown (buggily) during combat.
- **Form field offsets** (decoded from the D3 published-field table; entry = `[offset:u32][classindex:u16][namelen:u8][name]` right before each name): **WGoldPnl +0xDC**, **WManaPnl +0xF0**, WGTLbl(gold total) +0x58, WGILbl(gold income) +0x54, WMTLbl(mana total) +0xE8, WMILbl(mana income) +0xE4, WGIPnl +0x80, WMIPnl +0xEC, WGSign +0xE0, WMTSign +0xF4, TCPnl +0xD4. (Other gold/mana labels belong to OTHER forms: LGoldLbl/LManaLbl = hero/item **Transfer Book** window; MBGold* = a bribe UI.)
- **The show/hide logic (gold): ~0x405610** `mov edx,ebx; xor dl,1; mov eax,[edi+0xDC](WGoldPnl); mov ecx,[eax]; call [ecx+0x6C]` → **vtable +0x6C = SetVisible**, so `WGoldPnl.Visible := NOT ebx`. **`ebx` = the "hide gold" flag** (=1 hides). It also hides [edi+0xFC] and shows/hides an alternate placeholder [edi+0x11C] (shown when ebx=1). **Mana equivalent at ~0x405C10** (`mov eax,[edi+0xF0](WManaPnl)`). Both in what looks like one big resource-display-update method spanning ~0x4055F3..0x405C20 (references player obj via esi, player field [player+0x88]).
- **THE FIX (when revisited):** make `ebx` (the hide flag) = 1 whenever a tactical combat is active, at the WGoldPnl/WManaPnl SetVisible sites — i.e. `ebx := ebx OR inCombat`. NEED: (a) the function's entry + where ebx is set (Ghidra), and (b) a reliable "in tactical combat" signal. Candidate combat signals to chase: AoWTCPCK `TTacticalCombat.Initialize @0x429088 / .Deactivate @0x429064` likely set/clear a global "current combat" pointer; the main window reaches TC controls via `[[mainwin]+0x60]+0xD4`(TCPnl) and sets a state byte `[TCPnl+0x28]` (=1/4) at ~0x4080C3 (a combat-mode method) — [mainwin+0x60] may be the combat manager (null when not in combat).
- Alternative simpler fix if the ebx path is too tangled: blank the label CAPTIONS (WGTLbl/WGILbl/WMTLbl/WMILbl) when in combat instead of toggling panel Visible.
