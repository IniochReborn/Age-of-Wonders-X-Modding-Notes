#!/usr/bin/env python3
r"""TEMPORARY diagnostic for fcheal v5 (autocombat elemental terrain healing).
Pairs with fcheal_probe.py. REMOVE BEFORE RELEASE (--revert).

v5 (cave 0x55814500) looks statically correct but the user reports autocombat
healing still misbehaves. This script repoints the round-loop hook
@0x55744A5E from the v5 cave to an INSTRUMENTED copy @0x55814700 that records
what it actually sees each round into DATA slack @0x558E9B40 (PIC: all
counter/global accesses go through the call/pop anchor -- raw runtime anchor,
displacement = target - anchor, NO sub).

Counter layout (u32 each, base 0x558E9B40):
  +0x00 rounds (hook hits)            +0x04 last TCombatData ptr
  +0x08 last defender-hex pair        +0x0C last attacker-hex pair
  +0x10 last defender field ptr       +0x14 last attacker field ptr
  +0x18 units passing IsClass         +0x1C dead-flag skips
  +0x20 null-strat skips              +0x24 HP==0 skips
  +0x28 last unit resource index      +0x2C last unit side byte
  +0x30 index matches                 +0x34 cursed skips
  +0x38 heals applied                 +0x3C last roll (1-4)
  +0x40 last HP before heal           +0x44 (unused)
  +0x48 rounds with both pairs zero   +0x4C last GetCount result

v2 additions (in the DATA zero-fill tail 0x558E9C00+, NOT file-backed -- they
start zero on every game launch and cannot be pre-seeded/zeroed in the file):
  0x558E9C40 heal ring write index
  0x558E9C48 ring of 32 x 8B heal records:
      dword0 = hp_before | roll<<8 | round<<16   dword1 = strat unit ptr
  0x558E9D50 Die() records: +0 calls, +4 last unit ptr,
      +8 flags[unit+0x47]<<8|side[unit+0x45], +0xC strat HP at Die,
      +0x10 unit resource index, +0x14 combat ptr [unit+8]
plus a hook on TCombatUnit.Die @0x557256F0 (6B prologue, reloc-free,
replayed in cave @0x55814A00) recording every death fast OR tactical-side
combat processes through AoWEPACK.

--apply: hook -> diag cave (v5 cave left in place, untouched) + Die hook
--revert: hook -> v5 cave, Die prologue restored, caves zeroed
"""
import os
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.environ.get("AOW_GAME_DIR") or os.path.dirname(HERE)
DLL = os.path.join(GAME, "AoWEPACK.dll")

D = 0x55700C00          # CODE: VA = file + D
DD = 0x55701200         # DATA: VA = file + DD

FC_HOOK = 0x55744A5E
FC_RESUME = 0x55744A63
VALIDATE_WB = 0x5574480C
V5_CAVE = 0x55814500
DIAG_CAVE = 0x55814700
DIAG_HI = 0x55814A00
GETCOUNT = 0x55728BEC
GETOBJS = 0x55728BF8
ISCLASS = 0x557010C0
FCU_VMT = 0x5571D4BC
GETFIELDXYL = 0x557020FC
RANDINT = 0x55701080
MAPPTR = 0x558E9494
DIAG = 0x558E9B40
DIAG_LEN = 0x50
RIDX = 0x558E9C40          # zero-fill tail: runtime-only, not file-backed
RING = 0x558E9C48
DIE_REC = 0x558E9D50
DIE_HOOK = 0x557256F0
DIE_ORIG = bytes.fromhex("53568bd88bc3")   # push ebx;push esi;mov ebx,eax;mov eax,ebx
DIE_RESUME = 0x557256F6
DIE_CAVE = 0x55814A00
DIE_HI = 0x55814B00

LAVA_PAIR = 0x00E400E2
WATER_PAIR = 0x00E300E3
DIRT_PAIR = 0x00E100E1


def rel(src, dst):
    return struct.pack("<i", dst - (src + 5))


def make_diag():
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    ks = Ks(KS_ARCH_X86, KS_MODE_32)

    def build(anchor):
        def dg(off):
            return DIAG + off - anchor
        src = f"""
            pushad
            mov  ebx, [eax+0xC]
            test ebx, ebx
            jz   _out0
            call _a
        _a:
            pop  ebp
            inc  dword ptr [ebp + {dg(0x00)}]
            mov  [ebp + {dg(0x04)}], ebx
            mov  eax, [ebp + {MAPPTR - anchor}]
            mov  eax, [eax]
            mov  eax, [eax+0x10]
            mov  edx, [ebx+8]
            mov  ecx, [ebx+0xC]
            push dword ptr [ebx+0x10]
            call 0x{GETFIELDXYL:X}
            mov  [ebp + {dg(0x10)}], eax
            call _t2p
            mov  [ebp + {dg(0x08)}], edi
            push edi
            mov  eax, [ebp + {MAPPTR - anchor}]
            mov  eax, [eax]
            mov  eax, [eax+0x10]
            mov  edx, [ebx+0x14]
            mov  ecx, [ebx+0x18]
            push dword ptr [ebx+0x1C]
            call 0x{GETFIELDXYL:X}
            mov  [ebp + {dg(0x14)}], eax
            call _t2p
            mov  [ebp + {dg(0x0C)}], edi
            push edi
            mov  eax, [esp]
            or   eax, [esp+4]
            jnz  _have
            inc  dword ptr [ebp + {dg(0x48)}]
            jmp  _out2
        _have:
            mov  eax, ebx
            call 0x{GETCOUNT:X}
            mov  [ebp + {dg(0x4C)}], eax
            mov  esi, eax
        _loop:
            dec  esi
            js   _out2
            mov  eax, ebx
            mov  edx, esi
            call 0x{GETOBJS:X}
            test eax, eax
            jz   _loop
            push eax
            lea  edx, [ebp + {FCU_VMT - anchor}]
            call 0x{ISCLASS:X}
            test al, al
            jz   _next
            inc  dword ptr [ebp + {dg(0x18)}]
            mov  ecx, [esp]
            test byte ptr [ecx+0x47], 1
            jz   _alive
            inc  dword ptr [ebp + {dg(0x1C)}]
            jmp  _next
        _alive:
            mov  ecx, [ecx+0x4C]
            test ecx, ecx
            jnz  _hasstrat
            inc  dword ptr [ebp + {dg(0x20)}]
            jmp  _next
        _hasstrat:
            push ecx
            mov  eax, ecx
            mov  edx, [eax]
            call dword ptr [edx+0xE0]
            test al, al
            jnz  _hpok
            inc  dword ptr [ebp + {dg(0x24)}]
            jmp  _nextpop
        _hpok:
            mov  ecx, [esp]
            mov  edx, [ecx+0x40]
            test edx, edx
            jz   _nextpop
            mov  eax, [edx+4]
            mov  ecx, [eax]
            call dword ptr [ecx+0x84]
            mov  [ebp + {dg(0x28)}], eax
            mov  ecx, [esp+4]
            movzx ecx, byte ptr [ecx+0x45]
            mov  [ebp + {dg(0x2C)}], ecx
            test ecx, ecx
            jz   _att
            mov  edi, [esp+0xC]
            jmp  _havep
        _att:
            mov  edi, [esp+8]
        _havep:
            test edi, edi
            jz   _nextpop
            movzx ecx, di
            cmp  eax, ecx
            je   _match
            mov  ecx, edi
            shr  ecx, 16
            cmp  eax, ecx
            jne  _nextpop
        _match:
            inc  dword ptr [ebp + {dg(0x30)}]
            mov  ecx, [esp]
            mov  edx, 0x5D
            mov  eax, ecx
            mov  ecx, [eax]
            call dword ptr [ecx+0x148]
            test al, al
            jz   _notcursed
            inc  dword ptr [ebp + {dg(0x34)}]
            jmp  _nextpop
        _notcursed:
            mov  eax, 4
            call 0x{RANDINT:X}
            inc  eax
            mov  [ebp + {dg(0x3C)}], eax
            mov  ecx, [esp]
            push eax
            mov  eax, ecx
            mov  edx, [eax]
            call dword ptr [edx+0xE0]
            movzx edx, al
            mov  [ebp + {dg(0x40)}], edx
            mov  ecx, [esp]
            shl  ecx, 8
            or   ecx, edx
            mov  edi, [ebp + {dg(0x00)}]
            shl  edi, 16
            or   ecx, edi
            mov  edi, [ebp + {RIDX - anchor}]
            and  edi, 31
            shl  edi, 3
            mov  [ebp + edi + {RING - anchor}], ecx
            mov  ecx, [esp+4]
            mov  [ebp + edi + {RING - anchor + 4}], ecx
            inc  dword ptr [ebp + {RIDX - anchor}]
            pop  eax
            add  edx, eax
            pop  eax
            mov  ecx, [eax]
            call dword ptr [ecx+0xE4]
            inc  dword ptr [ebp + {dg(0x38)}]
            pop  eax
            jmp  _loop
        _nextpop:
            pop  ecx
        _next:
            pop  ecx
            jmp  _loop
        _out2:
            add  esp, 8
        _out0:
            popad
            call 0x{VALIDATE_WB:X}
            jmp  0x{FC_RESUME:X}
        _t2p:
            test eax, eax
            jz   _t0
            mov  al, [eax+0x14]
            cmp  al, 9
            je   _tl
            cmp  al, 0
            je   _tw
            cmp  al, 0xA
            je   _tw
            cmp  al, 0xC
            je   _td
        _t0:
            xor  edi, edi
            ret
        _tl:
            mov  edi, 0x{LAVA_PAIR:X}
            ret
        _tw:
            mov  edi, 0x{WATER_PAIR:X}
            ret
        _td:
            mov  edi, 0x{DIRT_PAIR:X}
            ret
        """
        code, _ = ks.asm(src, DIAG_CAVE)
        return bytearray(code)

    # iterate until the call/pop anchor position converges
    anchor = DIAG_CAVE + 0x10
    for _ in range(6):
        code = build(anchor)
        i = next(k for k in range(len(code) - 5)
                 if code[k] == 0xE8 and code[k+1:k+5] == b"\x00\x00\x00\x00"
                 and code[k+5] == 0x5D)
        real = DIAG_CAVE + i + 5
        if real == anchor:
            return bytes(code)
        anchor = real
    raise RuntimeError("anchor did not converge")


def make_die():
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    ks = Ks(KS_ARCH_X86, KS_MODE_32)

    def build(anchor):
        def dr(off):
            return DIE_REC + off - anchor
        src = f"""
            push eax
            push ebp
            pushfd
            call _b
        _b:
            pop  ebp
            inc  dword ptr [ebp + {dr(0x00)}]
            mov  [ebp + {dr(0x04)}], eax
            movzx edx, byte ptr [eax+0x47]
            shl  edx, 8
            mov  dl, [eax+0x45]
            mov  [ebp + {dr(0x08)}], edx
            mov  edx, [eax+8]
            mov  [ebp + {dr(0x14)}], edx
            mov  ecx, [eax+0x4C]
            test ecx, ecx
            jz   _done
            push ecx
            mov  eax, ecx
            mov  edx, [eax]
            call dword ptr [edx+0xE0]
            movzx eax, al
            mov  [ebp + {dr(0x0C)}], eax
            pop  ecx
            mov  edx, [ecx+0x40]
            test edx, edx
            jz   _done
            mov  eax, [edx+4]
            mov  ecx, [eax]
            call dword ptr [ecx+0x84]
            mov  [ebp + {dr(0x10)}], eax
        _done:
            popfd
            pop  ebp
            pop  eax
            push ebx
            push esi
            mov  ebx, eax
            mov  eax, ebx
            jmp  0x{DIE_RESUME:X}
        """
        code, _ = ks.asm(src, DIE_CAVE)
        return bytearray(code)

    anchor = DIE_CAVE + 0x10
    for _ in range(6):
        code = build(anchor)
        i = next(k for k in range(len(code) - 5)
                 if code[k] == 0xE8 and code[k+1:k+5] == b"\x00\x00\x00\x00"
                 and code[k+5] == 0x5D)
        real = DIE_CAVE + i + 5
        if real == anchor:
            return bytes(code)
        anchor = real
    raise RuntimeError("die anchor did not converge")


def main():
    apply = "--apply" in sys.argv
    revert = "--revert" in sys.argv
    d = bytearray(open(DLL, "rb").read())
    cave = make_diag()
    assert DIAG_CAVE + len(cave) <= DIAG_HI, len(cave)
    die = make_die()
    assert DIE_CAVE + len(die) <= DIE_HI, len(die)

    hook_v5 = b"\xE9" + rel(FC_HOOK, V5_CAVE)
    hook_dg = b"\xE9" + rel(FC_HOOK, DIAG_CAVE)
    die_jmp = b"\xE9" + struct.pack("<i", DIE_CAVE - (DIE_HOOK + 5)) + b"\x90"
    cur = bytes(d[FC_HOOK - D:FC_HOOK - D + 5])
    dcur = bytes(d[DIE_HOOK - D:DIE_HOOK - D + 6])

    if revert:
        assert cur in (hook_dg, hook_v5), cur.hex()
        assert dcur in (DIE_ORIG, die_jmp), dcur.hex()
        d[FC_HOOK - D:FC_HOOK - D + 5] = hook_v5
        d[DIE_HOOK - D:DIE_HOOK - D + 6] = DIE_ORIG
        d[DIAG_CAVE - D:DIAG_HI - D] = bytes(DIAG_HI - DIAG_CAVE)
        d[DIE_CAVE - D:DIE_HI - D] = bytes(DIE_HI - DIE_CAVE)
        d[DIAG - DD:DIAG - DD + DIAG_LEN] = bytes(DIAG_LEN)
        open(DLL, "wb").write(bytes(d))
        print("diag removed; hook -> v5 cave + Die prologue restored")
        return 0

    assert cur in (hook_v5, hook_dg), "v5 not applied? hook=" + cur.hex()
    assert dcur in (DIE_ORIG, die_jmp), "Die prologue foreign: " + dcur.hex()
    if not apply:
        print("diag cave %d B @0x%X; die cave %d B @0x%X; counters @0x%X; "
              "ring @0x%X; dry run OK (--apply / --revert)"
              % (len(cave), DIAG_CAVE, len(die), DIE_CAVE, DIAG, RING))
        return 0
    d[DIAG_CAVE - D:DIAG_HI - D] = bytes(DIAG_HI - DIAG_CAVE)
    d[DIAG_CAVE - D:DIAG_CAVE - D + len(cave)] = cave
    d[DIE_CAVE - D:DIE_CAVE - D + len(die)] = die
    d[DIAG - DD:DIAG - DD + DIAG_LEN] = bytes(DIAG_LEN)
    d[FC_HOOK - D:FC_HOOK - D + 5] = hook_dg
    d[DIE_HOOK - D:DIE_HOOK - D + 6] = die_jmp
    open(DLL, "wb").write(bytes(d))
    print("DIAG v2 APPLIED. Run ONE autocombat with a damaged elemental on "
          "its home terrain, leave the game running, then run fcheal_probe.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
