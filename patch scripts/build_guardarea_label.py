#!/usr/bin/env python3
r"""Distinct in-game action text for Guard vs Guard Area behaviours.

TArmy behaviours (AoWEPACK enum): gbNone=0, gbPatrol=1, gbGuard=2,
gbGuardArea=3, gbScout=4, gbRefuge=5, gbRaid=6, gbAggressive=7,
gbDefensive=8, gbFortify=9, gbSuicidal=10, gbPassive=11, ...

The "Party Action:" label text comes from one switch in AoWx.exe:
  004051C9  mov eax,[esi] ; mov eax,[eax+0xA4]
  004051D3  call TArmy.GetBehavior (import 0x40280C)
  004051D8  and eax,0x7F ; cmp eax,0xA ; ja default(Wandering)
  004051E4  jmp [eax*4 + 0x4051EB]          ; 11-slot jump table
Each case does: LoadResString(action RStr) -> AoWE.TranslateRStr (localization
pass, thunk 0x4021E4) -> TAOWLabel.SetGText([edi+0x174], text, thunk 0x403254)
-> jmp 0x405527. Slots 2 (gbGuard) AND 3 (gbGuardArea) both point at the
"Guarding" case @0x405242 - that is the merge this patch removes.

Patch: repoint slot 3 at a cave that pushes the literal "Guarding Area"
through the same TranslateRStr + SetGText tail (unknown text passes through
the translator unchanged, so an English game shows it verbatim). The literal
is a Delphi string constant (refcount -1, length dword, chars, NUL) so the
runtime never tries to free it.

Cave in .idata tail slack right after the reflecting-pool-raze UI cave
(patch_reflecting_pool_raze_ui_v1.py @0x46E380, 28 B); that patch already gave
.idata the EXECUTE characteristic, which this script asserts. AoWx.exe always
loads at 0x400000, so absolute addresses are safe.

Backup: AoWx.exe.bak_guardarea_label. Dry-run default; --apply / --revert.
"""
import os, shutil, struct, sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
EXE = os.path.join(GAME, "AoWx.exe")
BAK = EXE + ".bak_guardarea_label"

CODE2FILE  = 0x400C00          # CODE:   file = VA - this
IDATA2FILE = 0x402400          # .idata: file = VA - this (raw 0x59C00, va 0x45C000)

SLOT3_VA   = 0x4051F7          # jump table 0x4051EB + 3*4 (gbGuardArea)
SLOT_OLD   = 0x00405242        # the shared "Guarding" case
CASE_TAIL  = 0x405527          # common 'jmp end' target of every case

T_TRANSLATE = 0x4021E4         # thunk -> AoWEPACK!AoWE.TranslateRStr (eax=src, edx=^dest)
T_SETGTEXT  = 0x403254         # thunk -> aowInt!TAOWLabel.SetGText (eax=label, edx=text)

CAVE_VA   = 0x46E3A0           # .idata slack, after raze-UI cave (ends 0x46E39C)
CAVE_END  = 0x46E400           # .idata raw end (0x6C000 = .reloc start)
TEXT      = b"Guarding Area"


def build():
    lit_hdr = CAVE_VA + 0x20                  # dword-aligned literal header
    lit_chars = lit_hdr + 8
    code = bytearray()
    code += b"\xB8" + struct.pack("<I", lit_chars)        # mov eax,lit
    code += b"\x8D\x55\xFC"                               # lea edx,[ebp-4]
    code += b"\xE8" + struct.pack("<i", T_TRANSLATE - (CAVE_VA + len(code) + 5))
    code += b"\x8B\x55\xFC"                               # mov edx,[ebp-4]
    code += b"\x8B\x87\x74\x01\x00\x00"                   # mov eax,[edi+0x174]
    code += b"\xE8" + struct.pack("<i", T_SETGTEXT - (CAVE_VA + len(code) + 5))
    code += b"\xE9" + struct.pack("<i", CASE_TAIL - (CAVE_VA + len(code) + 5))
    assert len(code) <= 0x20, len(code)
    code += bytes(0x20 - len(code))                       # pad to the literal
    code += struct.pack("<i", -1)                         # refcount: constant
    code += struct.pack("<I", len(TEXT))                  # length
    code += TEXT + b"\x00"
    return bytes(code)


def main():
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if revert:
        if os.path.exists(BAK):
            shutil.copy2(BAK, EXE); print("restored AoWx.exe"); return 0
        print("no backup"); return 1

    d = bytearray(open(EXE, "rb").read())
    blob = build()
    assert CAVE_VA + len(blob) <= CAVE_END, len(blob)

    slot_off = SLOT3_VA - CODE2FILE
    cave_off = CAVE_VA - IDATA2FILE

    # version checks: slot 2 must stay "Guarding", the case code must look right
    cur3 = struct.unpack_from("<I", d, slot_off)[0]
    assert cur3 in (SLOT_OLD, CAVE_VA), hex(cur3)
    cur2 = struct.unpack_from("<I", d, slot_off - 4)[0]
    assert cur2 == SLOT_OLD, hex(cur2)
    case_off = 0x405242 - CODE2FILE
    assert d[case_off:case_off+3] == bytes.fromhex("8D55F8"), "Guarding case moved"

    # .idata must already be executable (raze-UI patch sets it)
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    off = pe + 24 + struct.unpack_from("<H", d, pe + 20)[0]
    chars = None
    for _ in range(struct.unpack_from("<H", d, pe + 6)[0]):
        if d[off:off+8].rstrip(b"\x00") == b".idata":
            chars = struct.unpack_from("<I", d, off + 36)[0]
        off += 40
    assert chars is not None and chars & 0x20000000, \
        "apply patch_reflecting_pool_raze_ui_v1.py first (.idata not executable): %r" % chars

    seg = bytes(d[cave_off:cave_off + len(blob)])
    assert seg == bytes(len(blob)) or seg[:1] == b"\xB8", seg[:8].hex()

    d[cave_off:cave_off + len(blob)] = blob
    struct.pack_into("<I", d, slot_off, CAVE_VA)

    print("AoWx: GuardArea case %dB @0x%X; jump-table slot3 0x%X -> cave"
          % (len(blob), CAVE_VA, SLOT3_VA))
    if not apply:
        print("Dry run OK — rerun with --apply (or --revert)."); return 0
    if not os.path.exists(BAK):
        shutil.copy2(EXE, BAK); print("Backup ->", os.path.basename(BAK))
    open(EXE, "wb").write(d)
    print("Written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
