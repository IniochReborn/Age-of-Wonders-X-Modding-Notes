#!/usr/bin/env python3
r"""Let the overland unit window use item-granted activatable abilities
(Spell Casting items) on heroes without the base ability.

TUnitWindow.UseAbility @0x409E90 (AoWx.exe) gates on
    ability.GetEnabled(unit)      ; virtual [ability.vmt+0x74] @0x409EF7
which reduces to the unit's OWN ability bit - item-granted Spell Casting
fails it, so clicking the ability in the unit window silently did nothing.
The party-window path works because it uses the hero's MERGED query
(THero.GetAbilityEnabled: unit OR carried items OR inventory), which lives at
virtual slot +0x148 of the strategic-unit hierarchy (TAbstractUnit base
@0x5577F5E0, THero override @0x5578827C).

Patch: the 5 bytes `mov ecx,[eax]; call [ecx+0x74]` become `call cave`. The
cave runs the original virtual first; only if it says disabled does it retry
via [unit.vmt+0x148] GetAbilityEnabled(unit, [ability+0xC]) - identical
result for non-heroes (base implementation is the same ability.GetEnabled),
merged for heroes/leaders. No DLL addresses are embedded (virtual dispatch
only), so AoWEPACK rebasing cannot break it. Everything after the gate
(turn-ownership checks, the ability's use action) is unchanged.

Cave in .idata slack right after the guard-area label cave (@0x46E3D8;
.idata is executable since the raze-UI patch, asserted here).
Backup: AoWx.exe.bak_unitwin_itemuse. Dry-run default; --apply / --revert.
"""
import os, shutil, struct, sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
EXE = os.path.join(GAME, "AoWx.exe")
BAK = EXE + ".bak_unitwin_itemuse"

CODE2FILE  = 0x400C00
IDATA2FILE = 0x402400

SITE      = 0x409EF7           # in TUnitWindow.UseAbility
SITE_ORIG = bytes.fromhex("8b08ff5174")   # mov ecx,[eax]; call [ecx+0x74]

CAVE_VA  = 0x46E3D8            # .idata slack (guard-area literal ends 0x46E3D6)
CAVE_END = 0x46E400


def build_cave():
    b = bytearray()
    b += b"\x50"                                    # push eax (ability)
    b += b"\x52"                                    # push edx (unit)
    b += b"\x8B\x08"                                # mov ecx,[eax]
    b += b"\xFF\x51\x74"                            # call [ecx+0x74] GetEnabled
    b += b"\x5A"                                    # pop edx (unit)
    b += b"\x59"                                    # pop ecx (ability)
    b += b"\x84\xC0"                                # test al,al
    b += b"\x75\x0D"                                # jnz done
    b += b"\x8B\xC2"                                # mov eax,edx (unit)
    b += b"\x8B\x51\x0C"                            # mov edx,[ecx+0xC] (ability id)
    b += b"\x8B\x08"                                # mov ecx,[eax]
    b += b"\xFF\x91\x48\x01\x00\x00"                # call [ecx+0x148] merged enabled
    b += b"\xC3"                                    # done: ret
    return bytes(b)


def main():
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if revert:
        if os.path.exists(BAK):
            shutil.copy2(BAK, EXE); print("restored AoWx.exe"); return 0
        print("no backup"); return 1

    d = bytearray(open(EXE, "rb").read())
    cave = build_cave()
    assert CAVE_VA + len(cave) <= CAVE_END, len(cave)

    site_off = SITE - CODE2FILE
    cave_off = CAVE_VA - IDATA2FILE
    new_site = b"\xE8" + struct.pack("<i", CAVE_VA - (SITE + 5))

    # .idata must be executable (raze-UI patch sets it)
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    off = pe + 24 + struct.unpack_from("<H", d, pe + 20)[0]
    chars = None
    for _ in range(struct.unpack_from("<H", d, pe + 6)[0]):
        if d[off:off+8].rstrip(b"\x00") == b".idata":
            chars = struct.unpack_from("<I", d, off + 36)[0]
        off += 40
    assert chars is not None and chars & 0x20000000, "apply raze-UI patch first"

    cur = bytes(d[site_off:site_off+5])
    assert cur in (SITE_ORIG, new_site), cur.hex()
    seg = bytes(d[cave_off:cave_off+len(cave)])
    assert seg == bytes(len(cave)) or seg[:1] == b"\x50", seg[:4].hex()

    d[cave_off:cave_off+len(cave)] = cave
    d[site_off:site_off+5] = new_site

    print("AoWx: UseAbility gate -> item-aware cave %dB @0x%X" % (len(cave), CAVE_VA))
    if not apply:
        print("Dry run OK — rerun with --apply (or --revert)."); return 0
    if not os.path.exists(BAK):
        shutil.copy2(EXE, BAK); print("Backup ->", os.path.basename(BAK))
    open(EXE, "wb").write(d)
    print("Written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
