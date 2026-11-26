---
name: aowx-7th-language-crash
description: "Why a 7th game language (Russian, index 6) crashes with RTE 216: the engine's hardcoded 6-language assumption; TAoWEngine.field64 nil; plus the VEH-injection crash-capture tool that cracked the heisenbug"
metadata: 
  node_type: memory
  type: project
  originSessionId: 7caffbff-32ec-402f-944f-c6ef4032cc30
  modified: 2026-08-26T02:52:11.574Z
---

**OUTCOME 2026-08-25: the entire Russian effort was ABANDONED and fully reverted** at the
user's request — Russian rendered in only part of the menu and wasn't worth the effort. The
game is back to its prior English-locked working state: `patch_fonts_cyrillic.py --revert`
(fonts pristine), `patch_replace_italian_russian.py --revert` (Italian restored), and the
force-English GetLanguage lock re-applied (`patch_restore_language_switch.py --revert`). English
is the mod's only real language by design. This note is kept ONLY for its reusable technical
findings (below) — the VEH crash-capture tool, the 6-language engine cap, and the GetLanguage
force. Do not re-attempt Russian unless the user asks again. The patch scripts and `backup\`
folders from the attempt still exist (harmless, unused).

--- Technical findings (reference only) ---
**Status (during the attempt)**: adding Russian as a true **7th** selectable language is blocked
by a hardcoded 6-language assumption in the engine. Fonts, dictionary column, AoWSetup dropdown,
and the Multilizer validation-guard removals all work; German (index 2) and other existing
languages work fine with the 7-language dict present. Only *selecting* index 6 crashes.

**Symptom**: pick Russian in AoWSetup (writes registry Language=6), launch → **Runtime error
216 at 00003924** at ~0.4s (startup language-init, NOT menu render). 216 = Delphi GPF; the
"00003924" is module-relative: **vcl30.dpl + 0x3924 = TObject.Free** (`mov ecx,[eax]; call
[ecx-4]`) freeing a garbage pointer.

**Root cause (pinned via live capture)**: the FIRST fault is a near-null deref in AoWEPACK at
**file 0x7B24B / VA 0x5577BE4E** (function 0x5577BE44, builds localized text):
`mov eax,[ebx+0x64]; mov esi,[eax+0x84]` where **ebx = a TAoWEngine instance** and
**[TAoWEngine+0x64] is NIL for language 6**. TAoWEngine+0x30 holds the language count (=7 with
our added column). field64 is normally a valid per-language object, assigned unconditionally at
**0x557985D5** (`field64 := TSomething.Create` via ctor 0x5574b9ec on class [0x55714a78],
also stored at +0x38). For index 6 that setter path never populates field64 before the
text-builder reads it → nil deref → Delphi unwinds → a `try..finally obj.Free` on the
uninitialized/garbage object → the fatal vcl30+0x3924. NEXT STEP to continue: resolve the
call-order/condition between the field64 setter (0x557985B8 region) and the reader
(0x5577BE44), find the hardcoded-6 gate, patch it — then expect MORE 6-limits to surface
(iterative). TAoWEngine VMT this-run 0x00F044F0 (floats; classname at vmt-0x20).

**THE HEISENBUG + HOW IT WAS BEATEN** (reusable): the crash NEVER reproduces under a launched
or attached debugger — Delphi uses its own memory manager, and any debugger changes heap layout
so the out-of-bounds read lands on benign memory. `_NO_DEBUG_HEAP` does not help (that's the
Windows heap, not Delphi's). Solution = **`patch scripts\diag_inject_veh.py`**: launch AoWx.exe
SUSPENDED, `VirtualAllocEx` a RWX region, write x86 shellcode for a **vectored exception
handler** + an install stub, `CreateRemoteThread` the stub (calls RtlAddVectoredExceptionHandler),
`ResumeThread`. The VEH runs IN-PROCESS (no debugger flag → real heap → real crash), filters to
the target fault (first near-null AV, or vcl30+0x3924), copies CONTEXT+stack to the region and
**spins (jmp $) to freeze the thread**, then the Python side reads registers/stack/memory at
leisure. WOW64 gotchas handled: resolve RtlAddVectoredExceptionHandler from the TARGET's 32-bit
ntdll (my 64-bit Python's copy is the wrong bitness) — and at CREATE_SUSPENDED the loader list
is empty, so do a throwaway normal launch first to read the boot-consistent 32-bit ntdll base +
export, then reuse it for the suspended injection. Use `Wow64GetThreadContext` for 32-bit regs.
⚠ my VirtualAllocEx can grab AoWEPACK's preferred base 0x55700000, relocating it to a floating
base (e.g. 0xEE0000) in the captured run — an artifact; the fault itself is base-independent.

**Measuring crash timing**: poll for a class `#32770` window (the RTE MessageBox) owned by the
pid; its Static child text reads "Runtime error 216 at 00003924". Appears at ~0.4s.

**Current on-disk state**: the REDUCED language patch set is applied (see [[mld-localisation]]):
only the SetLanguage dispatch (so column 6 activates) + the 8 Multilizer validation jne→jmp +
7-language Dict columns + AoWSetup "Russian" dropdown item. The behavior/grammar switch patches
were REMOVED (routing lang 6 to English case did NOT prevent the crash — proven). Russian is
selectable but crashes; every other language works. Registry left at 1 (English). To fully back
out: `patch_language_russian.py --revert`, `patch_dict_russian.py --revert`.
Decision pending with user: keep hunting the (possibly several) 6-limits, or fall back to
Russian REPLACING an existing language slot (index ≤5, no overflow, reliable).

**RESOLVED 2026-08-25 — Russian REPLACES Italian** (user chose this over more engine hunting).
`patch scripts\patch_replace_italian_russian.py` (dry-run/--apply/--revert, backups
`AoWSetup.exe.bak_ruit` / `Localize.dpl.bak_ruit` / `backup\Dict.bak_ruit`). The 7th-language
patches were fully reverted first. What it does: renames the AoWSetup LanguageCB dropdown item
"Italian"→"Russian" (same 7 letters, in place at file 0x1092B1); retags language[4] (the Italian
slot) in all 8 Dict\\*.mld to Russian (EnglishName "Russian", NativeName "Русский" aowx-ru bytes,
ISO ru/RU, Primary 0x19, **CodePage 1251** so AoWxInk edits it as Cyrillic); empties the old
Italian cells (fall back to English until translated) and seeds the menu strings. Keeps the 4+4
Multilizer validation jne→jmp guards (AoWSetup 0x4B17E/0x4B1B5/0x4B315/0x4B36F, Localize
0x6A1A/0x6A51/0x6BB1/0x6C0B) so CodePage 1251 doesn't pop the codepage dialog. Dropdown index 5
→ SetLanguage(4) = column 4, **inside the 6-slot range → NO crash** (verified: game launches
clean with Language=6... wait registry value 5). Cyrillic renders via the painted fonts
([[aowx-bitmap-fonts]]); strings stay raw AnsiString so aowx-ru bytes reach the renderer. NO
language-count binary patches needed. Registry value 5 = the (former Italian) Russian slot.
Bulk Russian translation is now normal AoWxInk work on that column.

**CONFIRMED WORKING IN-GAME 2026-08-25** once the force-English GetLanguage patch was reverted
(see [[mld-localisation]] — that patch, not the slot choice, was why the game had stayed
English). With Language=5 the title-screen Exit orb renders "Выход". So the pipeline is proven
end to end: AoWSetup dropdown "Russian" → registry 5 → SetLanguage(4) → column 4 (Cyrillic
bytes) → painted fonts. Remaining Russian work is pure translation of column 4 in AoWxInk.
(English remains the mod's primary language by design; Russian was added only for a couple of
Russian players.)

**OUTCOME 2026-08-26: abandoned.** Russian was removed from the game entirely; all 7th-language patches reverted (binaries byte-identical to .bak_ru7). Keep this memory only as engine internals reference (6-language hardcode, TAoWEngine.field64, VEH crash-capture tool).
