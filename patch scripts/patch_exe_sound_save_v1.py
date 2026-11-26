#!/usr/bin/env python3
r"""AoWx.exe: save the Sound settings to the registry when the in-game Sound dialog is CLOSED (2026-10-24).

User report (a player): "audio settings reset every update".  RE: the game keeps them in
HKCU\Software\Triumph Studios\Age of Wonders X\Sound (SFX/Music Volume 0..100, Sound Effects / Music Enabled, Sound
Quality, Use DirectSound - AoWReg.TAoWRegistry in AoWEPACK) but writes them ONLY in TMainForm.FormDestroy
(0x4539E2..0x453A5A, the last block of the settings save).  Nothing in the installer / updater touches that key, so any
session that does not end in a clean FormDestroy (crash on exit, killed process, power loss) silently drops every
audio change made in it.

Fix: TSoundDlg's published method CloseClick (method-table entry 0x42116D, DFM OnClick of the Close button) is
re-pointed to a wrapper: first run a copy of FormDestroy's sound block (esi =
[0x45DF74] (-> TAoWRegistry owner, [obj+0x5C]), edi = [0x45A158] (-> TSoundDlg)): SetUseDirectSound / SetSFXEnabled /
SetMusicEnabled / SetSoundQuality / SetSFXVolume / SetMusicVolume from the dialog's live values, then tail-jmp to the original CloseClick 0x4213DC.  FormDestroy still
saves them again on exit (unchanged).
Zone .xtut 0x638800..0x638900 ('ASV1' + the original entry value); free (intro-egg runtime data ends 0x638440).
AoWx.exe has no ASLR flag (DllCharacteristics 0) -> absolute addresses in the cave are safe; the method-table dword
carries a base reloc, which stays valid (the new value is also an in-image VA).
Backup <game>\backup\AoWx.exe.bak_soundsave.  Dry run by default; --apply / --revert.
"""
import os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

EXE = game_file("AoWx.exe")
BASE = 0x400000
ENTRY_VA, ENTRY_ORIG = 0x42116D, 0x4213DC        # TSoundDlg method table: CloseClick
ZONE, ZONE_END = 0x638800, 0x638900
MAGIC = b"ASV1"
CODE = ZONE + 0x10

SRC = """
    pushad
    mov  esi, dword ptr [0x45DF74]
    mov  edi, dword ptr [0x45A158]
    mov  eax, dword ptr [edi]
    test eax, eax
    jz   out
    mov  eax, dword ptr [esi]
    test eax, eax
    jz   out
    mov  eax, dword ptr [edi]
    mov  dl, byte ptr [eax + 0x11D]
    mov  eax, dword ptr [esi]
    mov  eax, dword ptr [eax + 0x5C]
    call 0x401FE4
    mov  eax, dword ptr [edi]
    mov  dl, byte ptr [eax + 0x124]
    mov  eax, dword ptr [esi]
    mov  eax, dword ptr [eax + 0x5C]
    call 0x401FC4
    mov  eax, dword ptr [edi]
    mov  dl, byte ptr [eax + 0x11C]
    mov  eax, dword ptr [esi]
    mov  eax, dword ptr [eax + 0x5C]
    call 0x401FD4
    mov  eax, dword ptr [edi]
    mov  edx, dword ptr [eax + 0x110]
    mov  eax, dword ptr [esi]
    mov  eax, dword ptr [eax + 0x5C]
    call 0x401F7C
    mov  eax, dword ptr [edi]
    mov  eax, dword ptr [eax + 0xEC]
    mov  edx, dword ptr [eax + 0x148]
    mov  eax, dword ptr [esi]
    mov  eax, dword ptr [eax + 0x5C]
    call 0x401F9C
    mov  eax, dword ptr [edi]
    mov  eax, dword ptr [eax + 0xE8]
    mov  edx, dword ptr [eax + 0x148]
    mov  eax, dword ptr [esi]
    mov  eax, dword ptr [eax + 0x5C]
    call 0x401F8C
out:
    popad
    jmp  0x4213DC
"""


def build_zone():
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    code = bytes(Ks(KS_ARCH_X86, KS_MODE_32).asm(SRC, CODE)[0])
    z = bytearray(ZONE_END - ZONE)
    z[0:4] = MAGIC
    struct.pack_into("<I", z, 4, ENTRY_ORIG)
    assert 0x10 + len(code) <= len(z)
    z[0x10:0x10 + len(code)] = code
    return bytes(z)


def main():
    import pefile
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    d = open(EXE, "rb").read()
    pe = pefile.PE(data=d, fast_load=True)
    assert pe.OPTIONAL_HEADER.DllCharacteristics & 0x40 == 0, "AoWx.exe became DYNAMIC_BASE"
    off = lambda va: pe.get_offset_from_rva(va - BASE)
    eo, zo = off(ENTRY_VA), off(ZONE)
    assert d[eo + 4:eo + 15] == b"\x0aCloseClick", d[eo:eo + 16]
    entry = struct.unpack_from("<I", d, eo)[0]
    zone_now = d[zo:zo + (ZONE_END - ZONE)]
    zone = build_zone()
    state = ("vanilla" if entry == ENTRY_ORIG and not any(zone_now) else
             "ours" if entry == CODE and zone_now == zone else "OTHER")
    print("CloseClick entry %#x -> %#x | zone %#x %s -> %s" % (ENTRY_VA, entry, ZONE, "zero" if not any(zone_now) else zone_now[:4], state))
    if state == "OTHER": print("ABORT"); return 1
    if state == ("vanilla" if revert else "ours"): print("already %s" % ("reverted" if revert else "applied")); return 0
    if not apply and not revert: print("Dry run OK (%d B code) - rerun with --apply (or --revert)." % len(zone.rstrip(b"\0"))); return 0
    bak = bak_path(EXE, ".bak_soundsave")
    if not revert and not os.path.exists(bak): shutil.copy2(EXE, bak); print("backup ->", bak)
    new_entry, new_zone = (ENTRY_ORIG, bytes(len(zone))) if revert else (CODE, zone)
    try:
        with open(EXE, "r+b") as f:                  # in-place (house rule)
            f.seek(eo); f.write(struct.pack("<I", new_entry))
            f.seek(zo); f.write(new_zone)
    except PermissionError:
        print("LOCKED - close AoWx.exe and retry"); return 1
    d2 = open(EXE, "rb").read()
    assert struct.unpack_from("<I", d2, eo)[0] == new_entry and d2[zo:zo + len(new_zone)] == new_zone
    print("reverted" if revert else "Written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
