---
name: designer-only-portrait-toggle
description: "RESOLVED 2026-07-21 - restored vanilla Designer Only/Reserved portrait filter AoW+ removed, via a 2-byte GetDeveloper revert in AoWEPACK.dll."
metadata: 
  node_type: memory
  type: project
  originSessionId: ae619055-3278-433b-b71b-cf21e5789ad7
  modified: 2026-07-22T01:22:24.135Z
---

**GOAL:** Restore vanilla behavior where hero/leader portraits flagged "Designer Only" in DevEd don't appear in in-game leader customization. AoW+ removed this; our files are AoW+-based. Task 2026-07-21.

**==== SOLVED (patched 2026-07-21, awaiting user in-game confirmation) ====**
Root cause (found via Ghidra headless): `AoWEPACK.TFaceResourceList.NextFace`/`PrevFace` skip faces whose record byte `[face+0x28] != 0` (the Reserved/Designer-Only flag) **unless** `AoWReg.TAoWRegistry.GetDeveloper()` returns true. Vanilla `GetDeveloper` = `33 C0 C3` (xor eax,eax; ret => always FALSE => reserved always hidden in-game). AoW+ patched it to `33 C0 40 C3` (added `inc eax` => always TRUE => dev mode always on => reserved faces never skipped). That IS AoW+'s changelog "Reserved campaign portraits can be selected when creating leaders."
**FIX (FINAL, surgical - preserves dev mode):** In `AoWEPACK.dll`, NOP the `jne <accept>` after `test al,al` in both face functions so the reserved check ALWAYS runs regardless of dev flag, and leave GetDeveloper=true (so dev keyboard stays):
  - PrevFace: file **0x4CA4D** `750f` (jne) -> `9090` (nop nop)
  - NextFace: file **0x4CA90** `750f` (jne) -> `9090` (nop nop)
  - GetDeveloper file 0x3A44 kept at AoW+ `33c040c3` (returns true).
(First tried & user-confirmed working: reverting GetDeveloper @0x3A44 to vanilla `33c0c390` = return false; but that also disabled AoW+'s dev keyboard, so switched to the surgical NOP version above per user.) Backup of AoW+-original AoWEPACK: `AoWEPACK.dll.bak_predevfix`. Revert-the-fix = write `750f` back at 0x4CA4D & 0x4CA90 (and GetDeveloper already true).
GetDeveloper's 3 callers: NextFace @0x5574D62E, PrevFace @0x5574D672 (faces), TAoWHSMapKeyboard.KeyDown @0x55773EC3 (dev keyboard - now unaffected).
Editor toggle never touched by AoW+ (AoWEd.dev.exe identical vanilla/AoW+); user sets flag in DevEd -> writes byte [face+0x28].
Ghidra: headless works via `Ghidra/ghidra_11.3.2_PUBLIC/support/analyzeHeadless.bat` on JDK 25; project `Ghidra/AoWx Claude Ghidra.gpr`; scratch project ghidra_proj/AoWxHL has AoWx.exe+AoWEPACK.dll analyzed. Decompile via -postScript Jython (needs `# -*- coding: utf-8 -*-`). GhidraMCP plugin installed but Module.manifest is malformed (GUI/8080 route unused; headless is enough).

**RE FINDINGS (investigation, not yet patched):**
- The DevEd toggle is INTACT: `AoWEd.dev.exe` (=our `AoWDevEd.exe` lineage) still has `DesignerOnlyBox`/`Designer Only` on `THeroResourceEditForm`. Editor binary is byte-IDENTICAL vanilla 1.36 vs AoW+ 1.45 — AoW+ did NOT touch the editor. So restoring = re-add the GAME-SIDE filter, no editor work.
- AoW+ changelog (reference files/AoW+ 1.45/+/Documentation/Changelog.txt line ~187) lists it under **Cosmetic Changes: "Reserved campaign portraits can be selected when creating leaders."** So "Designer Only" == "Reserved" flag; AoWEPACK export `AoWE.ReservedRStr` is the label.
- NOT in AoWEPACK: all leader/face/hero-type functions (`TLeaderSetupControl.*`, `TFaceResource*`, `TFaceResourceList.*` incl NextFace/PrevFace, `TSetupControl.CustomizeLeaders/ListAvailablePlayers`, `THeroType`) are **0-diff** vanilla-vs-AoW+. AoW+ changed 2133 bytes / 110 funcs in AoWEPACK but NONE are the portrait path (all economy/city/hero-stat rework).
- IS in the main EXE: our `AoWx.exe` (2131456 b) is based on **`AoW+.exe`** (same size; only 1323 b are our own edits). Vanilla `AoW.exe` is 2127872 b — AoW+ grew ONLY `.rsrc` (+0xE00); **CODE section is identical layout (roff 0x400, rsz 0x59000), so vanilla-vs-AoW+ CODE is directly byte-comparable.** AoW+ made 283 CODE bytes / 22 clusters of changes in the exe. The 6 changelog "Cosmetic Changes" live here.
- Identified exe clusters so far: map-size ID (va 0x4202F6 jz->jl chain + 0x420544 "?"->"XXL"); `+\Campaign\`/`+\Save\` path redirects (AoW+ infra); big city/realm-overview display func at 0x43C000-0x43D000 (multiple edits incl a block-skip `lea eax,[ebp-8]`->`jmp 0x43c9a7;nop` at 0x43C93B — this skips a byte[obj+0x45]->stringtable[0x45e000] label format, likely a status-text cosmetic, NOT the portrait filter); two call-redirects at 0x4256D9 & 0x425BA8 (likely singular->plural race name). **The exact portrait-filter cluster is NOT yet pinned** — needs Ghidra on the exe (no symbols in Delphi exe) to find the leader-customize face-enumeration and confirm which cluster gates "Reserved".
- CAUTION: some 0x43Cxxx bytes are `ours=OTHER` (our own exe patches overlap that function) — revert must be surgical, preserve our edits.

**22 EXE CODE CLUSTERS (vanilla AoW.exe vs AoW+.exe), classified (diff at file_off, va=off-0x400+0x401000):**
- Path redirects to AoW+'s `+\` folder (INFRA, not changelog): va 0x40CDD4, 0x41869C, 0x41C32C, 0x41D7A4 ("Scenario\Campaign\"->"+\Campaign\"); 0x4143E0, 0x41F9DC ("Save\"->"+\Save\").
- Map-size cosmetic ("nonstandard map sizes identified"): va 0x4202F6 (jz->jl compare chain) + 0x420544 ("?"->"XXL").
- AoW+ added helper fn at 0x41832F: big rewrite va 0x418327 (148b, vanilla was a switch doing `mov edx,const{4,6,5,2,1,3,8,9,10,..}; mov eax,[ebx+18]; call`), and two call-redirects va 0x4256D9 & 0x425BA8 (`call 0x402374`->`call 0x41832F`). Purpose unconfirmed (looks like an ordered-list/difficulty helper) — NOT obviously portraits.
- Cosmetic text swap: va 0x449186 (`mov eax,[0x45E0BC]`->`[0x45E3B0]`, different display string).
- Big display function 0x43C000-0x43D000 (city/realm overview cosmetics — merged income/plural races/Enslaved->Oppressed?): va 0x43C0B7,0x43C0D3,0x43C140,0x43C15C,0x43C77C,0x43CA79,0x43CB99 (small const/ptr tweaks); **0x43C93B block-skip** `lea eax,[ebp-8]`->`jmp 0x43C9A7;nop` (skips a byte[obj+0x45]->stringtable[0x45E000] label build); va 0x43CA95,0x43CBB5 (`e2`->`9c`, **ours=OTHER = our own edits here**).

**STATUS: NOT definitively pinned by static analysis.** None of the 22 clusters is an obvious "skip reserved face in a loop." The portrait filter is most likely (a) inside the 0x43Cxxx display func, or (b) the 0x41832F helper feature, or (c) possibly a .rsrc/DFM change (leader-customize form) not yet examined. User chose to STOP before patching (2026-07-21). TO FINISH: load Ghidra on AoWx.exe, find the leader-customize face-enumeration (xref the "Portrait"/"HeroList"/"CustomizeLeader" strings & AoWEPACK TFaceResourceList imports), identify the exact vanilla vs AoW+ divergence, then surgically restore vanilla bytes in AoWx.exe (backup first; preserve our 1323 b of edits). Also worth checking the exe `.rsrc` for a leader-customize form and whether AoW+ changed the TFaceResource "Reserved" field read.
- AoWTools.dll: AoW+ revised it (77 b vs vanilla; we match AoW+). It's the EDITOR toolkit — likely NOT the game filter, but not fully ruled out.

**TOOLS:** capstone 5.0.7 in `py` (3.10). Exe VA: file_off - 0x400 + 0x401000 (imgbase 0x400000, CODE rva 0x1000 @ file 0x400). AoWEPACK VA = file + 0x55700C00 (imgbase 0x55700000). Ghidra MCP available but Ghidra not running (port 8080 refused). See [[active-patches.md]], [[aowx-re-reference.md]].
