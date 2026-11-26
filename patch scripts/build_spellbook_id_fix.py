#!/usr/bin/env python3
r"""Spellbook fix: show known spells with id > 130 (new custom spells).

RE'd root cause: the spellbook page builder in AoWx.exe (@0x42F2E4) post-
filters its spell list: any spell with id >= 100 is DELETED from the display
list unless `AoWTC.SpellTypes[id]` is nonzero. SpellTypes (exported from
AoWTCPCK.dll @0x4672F4) is a static `array[0..130] of byte` sized for the
vanilla spell range — the book reads it UNBOUNDED, so new spells (Magic Sight
200, Summon Mermaid 201) index past the array into arbitrary data: 200 read
nonzero garbage (visible by luck), 201 read zero (silently hidden).

Fix: turn the filter's `jl keep` (id < 100 -> keep) into an unconditional
`jmp keep` — every spell in the player's known list is a real registered
spell, so the drop branch is pure hazard for ids > 130.

  0042F2F1  cmp dword ptr [eax+0x10], 0x64
  0042F2F5  7C 29  jl 0x42f320      ->  EB 29  jmp 0x42f320

(Known separate landmine, NOT fixed here: AoWTCPCK's tactical-combat code
reads SpellTypes[id] with Delphi `bound` checks [0..130] — casting a >130
spell IN TACTICAL COMBAT may raise a range error. See memory notes.)

Backup AoWx.exe.bak_bookid. Dry-run; --apply / --revert.
"""
import os, shutil, sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
EXE = os.path.join(GAME, "AoWx.exe")
BACKUP = EXE + ".bak_bookid"

VA2FILE = 0x400C00
SITE = 0x42F2F5
OLD, NEW = b'\x7c\x29', b'\xeb\x29'


def main():
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    d = bytearray(open(EXE, 'rb').read())
    off = SITE - VA2FILE
    cur = bytes(d[off:off+2])
    want_old, want_new = (NEW, OLD) if revert else (OLD, NEW)
    if cur == want_new:
        print("already %s" % ("reverted" if revert else "applied")); return 0
    if cur != want_old:
        print("MISMATCH @0x%X: %s" % (SITE, cur.hex())); return 1
    d[off:off+2] = want_new
    print("site @0x%X: %s -> %s" % (SITE, cur.hex(), want_new.hex()))
    if not apply and not revert:
        print("Dry run OK — rerun with --apply (or --revert)."); return 0
    if not os.path.exists(BACKUP):
        shutil.copy2(EXE, BACKUP); print("Backup -> %s" % os.path.basename(BACKUP))
    open(EXE, 'wb').write(d); print("Written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
