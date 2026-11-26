#!/usr/bin/env python3
r"""Neutralize ACTIVE relocs left under mod-patched bytes in AoWEPACK.dll.

DISCOVERY (2026-08-13): full audit of active (type-3) relocs whose covered
dword differs between live AoWEPACK.dll and the original found 53 sites.
48 are deliberate absolute rewrites (VMT slots / classrefs redirected to
caves) whose relocs MUST stay active. FIVE are July-era patches (pre-dating
the patching-over-relocs lesson) that overwrote absolute-operand instructions
with NOPs/zeros WITHOUT neutralizing the reloc. AoWEPACK always rebases, so
the loader adds the delta to those bytes on every load, materializing
BASE-DEPENDENT JUNK INSTRUCTIONS -- harmless on this machine's usual bases,
but on other bases they can decode to junk reads/jumps/rets/writes. Prime
suspect for "crashes on his machine, not on mine, identical files" MP
reports, and a possible heap-corruption source.

THE FOUR SITES HANDLED HERE (the fifth, 0x5576BD25, is fixed with real code
by build_combat_heal_owner_fix.py):
  0x55726A4C  damage-halving removal NOP run (ret 4 variant)  live 90909090
  0x55726AE1  damage-halving removal NOP run (ret 8 variant)  live 90909090
  0x55781B26  same patch family, third copy                   live 90909090
  0x55782B77  rewritten stat getter, reloc in dead padding    live 00000000
              (inert -- nothing executes/reads it -- neutralized for hygiene)

--apply sets each entry type 3 -> 0 (byte content untouched); --revert
restores type 3. Backup: AoWEPACK.dll.bak_relocfix.
"""
import os, shutil, struct, sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DLL = os.path.join(GAME, "AoWEPACK.dll")
BAK = DLL + ".bak_relocfix"

# (VA, expected live dword under the reloc)
SITES = [
    (0x55726A4C, bytes.fromhex("90909090")),
    (0x55726AE1, bytes.fromhex("90909090")),
    (0x55781B26, bytes.fromhex("90909090")),
    (0x55782B77, bytes.fromhex("00000000")),
]
VA2FILE = 0x55700C00
IMAGE_BASE = 0x55700000


def reloc_words(d):
    """Yield (file_off_of_word, word, va) for every reloc entry."""
    import pefile
    pe = pefile.PE(data=bytes(d), fast_load=True)
    sec = next(s for s in pe.sections if s.Name.startswith(b".reloc"))
    raw, size = sec.PointerToRawData, sec.SizeOfRawData
    off = raw
    while off < raw + size:
        if off + 8 > raw + size:
            break
        page, blksize = struct.unpack_from("<II", d, off)
        if blksize < 8:
            break
        for eo in range(off + 8, off + blksize, 2):
            w = struct.unpack_from("<H", d, eo)[0]
            yield eo, w, IMAGE_BASE + page + (w & 0xFFF)
        off += blksize


def find_entries(d):
    wanted = {va for va, _ in SITES}
    found = {}
    for eo, w, va in reloc_words(d):
        if va in wanted and (w >> 12) in (0, 3):
            found[va] = (eo, w)
    missing = wanted - set(found)
    assert not missing, f"reloc entries not found: {[hex(v) for v in missing]}"
    return found


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--status"
    d = bytearray(open(DLL, "rb").read())
    entries = find_entries(d)

    if mode == "--status":
        for va, _ in SITES:
            eo, w = entries[va]
            print(f"{va:#010x}: type {w >> 12} "
                  f"({'ACTIVE - junk at load' if w >> 12 == 3 else 'neutralized'})")
        return 0

    if mode in ("--apply", "--revert"):
        want_type = 0 if mode == "--apply" else 3
        for va, expect in SITES:
            fo = va - VA2FILE
            assert bytes(d[fo:fo+4]) == expect, \
                f"{va:#x}: unexpected live bytes {bytes(d[fo:fo+4]).hex()}"
        if mode == "--apply" and not os.path.exists(BAK):
            shutil.copy2(DLL, BAK)
            print("backup ->", os.path.basename(BAK))
        changed = 0
        for va, _ in SITES:
            eo, w = entries[va]
            if (w >> 12) != want_type:
                struct.pack_into("<H", d, eo, (want_type << 12) | (w & 0xFFF))
                changed += 1
        open(DLL, "wb").write(d)
        print(f"{mode} done: {changed} reloc entries -> type {want_type}")
        return 0

    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
