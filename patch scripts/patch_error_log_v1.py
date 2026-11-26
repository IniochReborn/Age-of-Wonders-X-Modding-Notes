#!/usr/bin/env python3
r"""
Loader for AoWxLog.dll ("Error Log.txt": all errors + Out-of-Sync record; see build_aowxlog.py) (2026-11-14).

AoWEPACK.dll entry point 0x5580BDE8 = `jmp 0x557013D0` (5 B, rel32, no relocation) -> cave 0x558E4100..0x558E4180
'ELG1' (PIC): on DLL_PROCESS_ATTACH LoadLibraryA("AoWxLog.dll") - LoadLibraryA borrowed from VCL30's IAT (0x413E4360)
through AoWEPACK's System.@RandInt import slot 0x558FB6DC (VCL30 preferred 0x41303384) -> then the original entry.
A missing DLL is ignored (LoadLibrary just fails), so the DLL can be removed to switch the log off.
--apply also (re)builds AoWxLog.dll.  Dry-run default; --revert (surgical).  Backup backup\AoWEPACK.dll.bak_errorlog.
Ship AoWEPACK.dll + AoWxLog.dll (release zip: --add AoWxLog.dll).
"""
import os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

EP, EP_D = game_file("AoWEPACK.dll"), 0x55700C00
SUF = ".bak_errorlog"
CAVE, CAVE_END, MAGIC = 0x558E4100, 0x558E4180, b"ELG1"
CODE = CAVE + 4
SITE, ORIG = 0x5580BDE8, 0x557013D0
SLOT_RANDINT, VCL_RANDINT, VCL_LOADLIB = 0x558FB6DC, 0x41303384, 0x413E4360
NAME = b"AoWxLog.dll\0"


def jmp(frm, to):
    return b"\xE9" + struct.pack("<i", to - frm - 5)


def cave_code():
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    src = f"""
        cmp dword ptr [esp + 8], 1
        jne go
        pushal
        call n
    n:
        pop ebx
        sub ebx, {CODE + 13:#x}
        mov eax, dword ptr [ebx + {SLOT_RANDINT:#x}]
        sub eax, {VCL_RANDINT:#x}
        lea ecx, [ebx + name]
        push ecx
        call dword ptr [eax + {VCL_LOADLIB:#x}]
        popal
    go:
        jmp {ORIG:#x}
    name:
    """
    enc, _ = Ks(KS_ARCH_X86, KS_MODE_32).asm(src, CODE)
    b = bytes(enc)
    # `call n` must sit at CODE+8 (cmp 5 B, jne 2 B, pushal 1 B) so that n = CODE+13
    assert b[8] == 0xE8 and b[13] == 0x5B, b[:16].hex()
    return b + NAME


def main():
    apply, revert = "--apply" in sys.argv, "--revert" in sys.argv
    ep = bytearray(open(EP, "rb").read())
    blob = MAGIC + cave_code()
    assert len(blob) <= CAVE_END - CAVE
    o_c, o_s = CAVE - EP_D, SITE - EP_D
    site, cave = bytes(ep[o_s:o_s + 5]), bytes(ep[o_c:o_c + (CAVE_END - CAVE)])
    applied = site == jmp(SITE, CODE) and cave.startswith(blob)
    clean = site == jmp(SITE, ORIG) and not any(cave)
    print("cave %#x: %d B | state: %s" % (CAVE, len(blob), "APPLIED" if applied else "clean" if clean else "UNKNOWN"))
    if revert:
        if not applied:
            print("not applied"); return 1
        ep[o_s:o_s + 5] = jmp(SITE, ORIG); ep[o_c:o_c + (CAVE_END - CAVE)] = bytes(CAVE_END - CAVE)
        open(EP, "wb").write(ep); print("reverted (AoWxLog.dll left in place - delete it if unwanted)"); return 0
    if apply:
        import build_aowxlog
        build_aowxlog.main()
    if applied:
        print("ALREADY PATCHED"); return 0
    if not clean:
        print("ABORT: unexpected bytes at the entry point (%s) or cave" % site.hex()); return 1
    if not apply:
        print("Dry run OK - rerun with --apply"); return 0
    b = bak_path(EP, SUF)
    if not os.path.exists(b):
        shutil.copy2(EP, b); print("backup ->", b)
    ep[o_c:o_c + len(blob)] = blob
    ep[o_s:o_s + 5] = jmp(SITE, CODE)
    open(EP, "wb").write(ep)
    print("applied")
    return 0


if __name__ == "__main__":
    sys.exit(main())
