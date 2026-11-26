#!/usr/bin/env python3
r"""AoWx -- elemental terrain feeding: +1 HP per hex of "home" terrain walked.

NEW FEATURE (user spec 2026-08-30, companion to build_firefeed.py):
  Fire Elemental (0xE2) / Fire Sprite (0xE4)  heal +1 per LAVA (9) hex entered
  Water Elemental (0xE3)                      heal +1 per WATER (0 / CaveWater
                                              0xA) hex entered (walk or swim)
  Earth Elemental (0xE1)                      heal +1 per DIRT (0xC) hex
  Air Elemental (0xE0)                        no terrain heal (per spec)
No elemental heals from elemental DAMAGE except the pure-fire case handled by
build_firefeed.py. Amount fixed at +1/hex (user spec); TUnit.SetHitPoints
clamps to max, so it can never overflow.

MECHANISM: 6-byte hook at 0x55780336 in TAbstractUnit.MovedTo (the two
displaced byte loads `mov cl,[esi+0x15]; mov dl,[esi+0x14]` are replayed at
the cave tail). At that point: EBX = the moving unit, ESI = the DESTINATION
map field, [EBP-4] = the FROM field (0 for placement/teleport-in -> no heal,
mirroring the Path abilities' own from!=0 gate), EAX/ECX/EDX/EDI scratch
(EDI is assigned two instructions later from a call result).

CURSED EXCLUSION (user spec 2026-08-30 v2): a unit with the Cursed debuff
(ability 0x5D) enabled heals nothing from terrain (checked via the
item-aware GetAbilityEnabled, vmt+0x148).

CARRIED-PASSENGER EXCLUSION (user spec via BXL's transportgate semantics): a
unit being transported is not touching the terrain. The cave replicates
MovedTo's own army gate: army = [unit+4]; if IsClass(army, TArmy) and
Transporter(army,0xFF) returns a unit that is NOT me -> skip the heal. The
transporter itself (and any unit in a transporterless army) heals normally.
Works identically whether or not build_path_transportgate.py is applied (we
call the REAL Transporter @0x5578E00C, not the hooked call site).

Unit identity read position-independently (unit+0x40 -> resource, +4 -> list,
call [list.vtable+0x84] = UnitResourceIndex), null-guarded -- heroes and
everything else get a non-elemental index and fall through. The one absolute
datum (the TArmy classref holder 0x557130AC) is reached via call/pop delta
(anchor scheme: pop the RUNTIME anchor, displacement = target - anchor).

MP-safe: MovedTo runs in synchronized move execution; +1 is deterministic.

Hook site byte-verified vanilla-identical (2026-08-30); no relocs under it.

Usage: dry run default; --apply; --revert (surgical).
"""
import os
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.environ.get("AOW_GAME_DIR") or os.path.dirname(HERE)
DLL = os.path.join(GAME, "AoWEPACK.dll")
BAK = DLL + ".bak_terrainfeed"

D = 0x55700C00
HOOK = 0x55780336
HOOK_ORIG = bytes.fromhex("8a4e158a5614")   # mov cl,[esi+0x15]; mov dl,[esi+0x14]
RESUME = 0x5578033C
ISCLASS = 0x557010C0
TRANSPORTER = 0x5578E00C
ARMY_CLASSREF = 0x557130AC                  # global holding the TArmy classref
CAVE = 0x558140C0
CAVE_HI = 0x55814180
PH_CLS = 0x11111111

LAVA_PAIR = 0x00E400E2                      # fire sprite | fire elemental
WATER_PAIR = 0x00E300E3
DIRT_PAIR = 0x00E100E1


def rel(src, dst):
    return struct.pack("<i", dst - (src + 5))


def make_cave():
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    src = f"""
        cmp  dword ptr [ebp-4], 0
        je   _done
        mov  al, [esi+0x14]
        cmp  al, 9
        je   _lava
        cmp  al, 0
        je   _water
        cmp  al, 0xA
        je   _water
        cmp  al, 0xC
        je   _dirt
        jmp  _done
    _lava:
        mov  edi, 0x{LAVA_PAIR:X}
        jmp  _ident
    _water:
        mov  edi, 0x{WATER_PAIR:X}
        jmp  _ident
    _dirt:
        mov  edi, 0x{DIRT_PAIR:X}
    _ident:
        mov  edx, [ebx+0x40]
        test edx, edx
        jz   _done
        mov  eax, [edx+4]
        mov  ecx, [eax]
        call dword ptr [ecx+0x84]
        movzx ecx, di
        cmp  eax, ecx
        je   _carry
        shr  edi, 16
        cmp  eax, edi
        jne  _done
    _carry:
        mov  eax, [ebx+4]
        test eax, eax
        jz   _heal
        push eax
        call _anch
    _anch:
        pop  ecx
        mov  edx, [ecx + 0x{PH_CLS:X}]
        pop  eax
        push eax
        call 0x{ISCLASS:X}
        pop  ecx
        test al, al
        jz   _heal
        mov  eax, ecx
        mov  dl, 0xFF
        call 0x{TRANSPORTER:X}
        test eax, eax
        jz   _heal
        cmp  eax, ebx
        jne  _done
    _heal:
        mov  edx, 0x5D
        mov  eax, ebx
        mov  ecx, [eax]
        call dword ptr [ecx+0x148]
        test al, al
        jnz  _done
        mov  eax, ebx
        mov  edx, [eax]
        call dword ptr [edx+0xe0]
        movzx edx, al
        inc  edx
        mov  eax, ebx
        mov  ecx, [eax]
        call dword ptr [ecx+0xe4]
    _done:
        mov  cl, [esi+0x15]
        mov  dl, [esi+0x14]
        jmp  0x{RESUME:X}
    """
    src = "\n".join(ln.split(";")[0] for ln in src.splitlines())
    code, _ = Ks(KS_ARCH_X86, KS_MODE_32).asm(src, CAVE)
    code = bytearray(code)
    # patch the anchor displacement: find `call next / pop ecx`
    i = next(k for k in range(len(code) - 5)
             if code[k] == 0xE8 and code[k + 1:k + 5] == b"\x00\x00\x00\x00"
             and code[k + 5] == 0x59)
    anchor = CAVE + i + 5
    j = code.find(struct.pack("<I", PH_CLS))
    assert j != -1
    code[j:j + 4] = struct.pack("<i", ARMY_CLASSREF - anchor)
    return bytes(code)


def main():
    apply = "--apply" in sys.argv
    revert = "--revert" in sys.argv
    d = bytearray(open(DLL, "rb").read())
    cave = make_cave()
    assert CAVE + len(cave) <= CAVE_HI, len(cave)
    hook = b"\xE9" + rel(HOOK, CAVE) + b"\x90"
    edits = [(CAVE, bytes(len(cave)), cave, "cave_terrainfeed"),
             (HOOK, HOOK_ORIG, hook, "MovedTo hook")]
    states = []
    for va, ob, nb, nm in edits:
        c = bytes(d[va - D:va - D + len(nb)])
        st = "original" if c == ob else "applied" if c == nb else "FOREIGN"
        states.append(st)
        print("  %-24s @0x%08X  %s (%d B)" % (nm, va, st, len(nb)))
    if "FOREIGN" in states:
        print("FOREIGN - refusing")
        return 1
    if revert:
        for va, ob, nb, _ in edits:
            d[va - D:va - D + len(nb)] = ob
        open(DLL, "wb").write(bytes(d))
        print("reverted")
        return 0
    if not apply:
        print("dry run (--apply / --revert)")
        return 0
    if all(s == "applied" for s in states):
        print("already applied")
        return 0
    if not os.path.isfile(BAK):
        shutil.copy2(DLL, BAK)
        print("backed up")
    for va, ob, nb, _ in edits:
        d[va - D:va - D + len(nb)] = nb
    open(DLL, "wb").write(bytes(d))
    print("APPLIED - test: damaged Fire Elemental walks across lava -> +1 HP "
          "per hex; Water Elemental swims water / Earth Elemental walks dirt "
          "-> +1/hex; Air Elemental nothing; carried units heal NOTHING while "
          "transported; normal units unaffected; no heal on summon placement")
    return 0


if __name__ == "__main__":
    sys.exit(main())
