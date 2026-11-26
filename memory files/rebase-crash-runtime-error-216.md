---
name: rebase-crash-runtime-error-216
description: "PLAYBOOK: intermittent 'Runtime error 216' / startup crash = a cave DEREFERENCES an in-image absolute address, and AoWEPACK.dll rebases between launches so the un-relocated ref points to garbage. Fix = PIC delta-trick. Hit us via Path-of-Sand caves 2026-07-23."
metadata:
  node_type: memory
  type: reference
  originSessionId: ae619055-3278-433b-b71b-cf21e5789ad7
  modified: 2026-07-23T08:57:28.313Z
---

# ⚠️ REBASE-CRASH PLAYBOOK — read this FIRST if the game crashes at startup or intermittently

## SYMPTOM (how to recognize it)
- **"Runtime error 216 at 00003924"** (or a similar low garbage address) — a Delphi/BorlndMM access violation.
- **INTERMITTENT**: the game starts fine one launch, then fails the next with the SAME error, with NO file change in between. Close-and-reopen flips it.
- Can present as **"can't start the EXE at all"** (a cave that runs at package init, e.g. an ability-registration cave) OR as a **play-time crash** (a cave that runs in combat / on unit move).
- The error address is often **consistent** (same garbage value each crash) because it's a deterministic wrong-pointer, not random uninitialized data.

## ROOT CAUSE
**AoWEPACK.dll (and likely the other .dpl packages) load at a DIFFERENT base address between launches** — a "rebase." Preferred base = **0x55700000**; observed rebased to **0x01170000**. This is a package-load-order / address-conflict thing, environmental and non-deterministic → hence the intermittency.

When rebased, the OS loader relocates every absolute address **that has a base-relocation entry**. The game's own code has those entries (built by its linker). **Our hand-written caves do NOT** — when we hand-assemble `mov edx, 0x5580f3a8` into free space, we don't add a `.reloc` entry for it. So at a rebased load our absolute is left pointing at the PREFERRED address, which is now garbage/unmapped → deref → crash. At the preferred base (delta 0) it happens to work, which is why it can pass testing for a long time before biting.

## THE DANGEROUS PATTERNS (what to grep caves for)
Any cave instruction that **dereferences or takes the address of an in-image location as a bare absolute**:
- `mov reg, [0x55xxxxxx]` / `mov cx, [0x557bcfc0]`  (bare `[disp32]` memory operand — base=0, index=0)
- `mov reg, 0x55xxxxxx`  (an in-image ADDRESS loaded as an immediate — e.g. a string/callback ptr; NOT small consts like `mov edx,0x27`)
- `push 0x55xxxxxx`  (pushing an in-image address, e.g. a callback)
- `lea reg, [0x55xxxxxx]` (bare disp)
**SAFE (already position-independent), do NOT flag:** `call/jmp 0x55xxxxxx` (rel32), all `jcc` (rel8/32), `[reg+disp]` memory (base register present), small immediates, `sub reg,<VA>` used as the delta computation below.

## THE FIX — PIC delta-trick (the pattern the game's own slayer caves use, e.g. @0x5580E3B0)
Compute the runtime load-delta once, then reach every absolute through a base register:
```
call $+5              ; E8 00 00 00 00  (call to the very next instruction)
pop  <reg>            ; reg = runtime address of this pop
sub  <reg>, <preferred VA of this pop>   ; reg = load delta (0 at preferred base)
...
; then rewrite each absolute:
mov edx, 0xADDR       ->  lea edx, [reg + 0xADDR]
mov  cx, [0xADDR]     ->  mov  cx, [reg + 0xADDR]
push 0xADDR           ->  lea eax, [reg + 0xADDR] ; push eax
mov eax, [0xADDR]     ->  mov eax, [reg + 0xADDR]
```
Pick `reg` = a register that's free/dead at the hook and survives the intervening calls (callee-saved regs survive game calls; e.g. we used **edi** in MovedTo where edi is dead, **eax** in the reg-cave before the id load). VERIFY by emulating the cave mapped at a fake rebased base (e.g. 0x01170000) and checking the computed delta == load-0x55700000.

## AUDIT SNIPPET (capstone, detail=True) — run on every cave region before applying
```python
for ins in md.disasm(bytes(d[fo:fo+n]), va):
    if ins.mnemonic in ("jmp","call") or ins.mnemonic[0]=="j": continue
    for op in ins.operands:
        if op.type==X86_OP_MEM and op.mem.base==0 and op.mem.index==0 and 0x55700000<=op.mem.disp&0xffffffff<0x559C0000:
            print("BARE-MEM", hex(ins.address), ins.mnemonic, ins.op_str)
        if op.type==X86_OP_IMM and ins.mnemonic in ("mov","push","lea") and 0x55700000<=op.imm&0xffffffff<0x559C0000:
            print("ADDR-IMM", hex(ins.address), ins.mnemonic, ins.op_str)
```
(from capstone.x86 import X86_OP_MEM, X86_OP_IMM)

## THE INSTANCE THAT BIT US (2026-07-23)
- **cave_sandreg @0x5580F480** (runs at STARTUP, ability registration): `mov edx,0x5580f3a8` (name ptr) + `mov cx,[0x557bcfc0]` → **the startup Runtime-error-216**.
- **cave_sanddispatch @0x5580F400** (unit move): `push 0x5580f3c0` (callback) + `mov eax,[0x558fa040]` (map global) → same latent bug, would crash terraforming when rebased.
- Both rewritten PIC-safe (delta in eax / edi). Night-vision + true-seeing caves audited CLEAN (they only used register-relative + rel32). See [[path-of-sand-ability]], [[trueseeing-vs-invisible-atk-penalty]], [[active-patches]] (has the short ⚠️ rule at top).

## PREVENTION (apply going forward)
1. When hand-writing a cave, **default to register-relative + rel32**. If you MUST reach a fixed global/string/callback, use the PIC delta-trick — never a bare absolute.
2. **Run the audit snippet on every new cave before applying.**
3. If a rebase crash ever recurs in a cave you can't easily rework: the heavier alternative is to ADD `.reloc` (IMAGE_REL_BASED_HIGHLOW, type 3) entries for each absolute's imm32/disp32 offset so the loader fixes them — but PIC is simpler and self-contained.


## 2026-09-01 — a SECOND way to get error 216 from an AoWEPACK patch
Not rebase this time: **cross-host**. AoWEPACK.dll is loaded by AoWx.exe AND
AoWDevX.exe (and possibly tools). A patch that points AoWEPACK code at
addresses in the GAME EXE's image (e.g. an `.xbfs` cave) crashes every other
host at DLL-init with runtime error 216, because that memory is unmapped
there. Fix pattern (campaign-set-switch v6): in-module constants/buffers with
ACTIVE relocs for anything AoWEPACK dereferences; exe-image absolutes only
behind a host check ([0x40003C]→[hdr+0x50] SizeOfImage + a signature dword in
the target section). See [[campaign-set-switch]].

Follow-up (same day): fixing the cross-host pointers was NOT enough — the
editor's init never runs the game's fill hook (UpdateStartupDirectory), so
point-A-fills/point-B-consumes designs are ORDER-DEPENDENT across hosts and
still crash (empty path string -> failed load at init). Final pattern:
SELF-ENSURING SITE STUBS — every consumer site calls a stub that fills the
shared buffers if empty, then returns the pointer. See [[campaign-set-switch]] v7.
