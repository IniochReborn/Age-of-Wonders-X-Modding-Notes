#!/usr/bin/env python3
r"""
Tactical AI never chose a spell id >= 131: TCAI.CheckUnit still read the OLD spell-type table (2026-11-14).

patch_spelltypes_relocate_v1 moved the tactical spell-type table from 0x4672F4 (131 entries, DATA) to 0x43C000
(512 entries) and re-pointed its readers - but missed the one in TCAI.CheckUnit @0x4159EC:
    bound eax,[0x4180E8] / movzx eax, byte ptr [eax + 0x4672F4] / cmp eax,0x2F / ja skip / class -> case map
The old table is still there for ids 0..130, so vanilla spells kept working; any new spell reads the bytes behind
it (id 228 Magic Missile -> 4 = a "skip" class) and is dropped from the AI's choice.  Found with tcai_trace2.py: the
independent hero's Magic Missile was known, castable and in the candidate list, yet never cast (auto combat fine).
Fix: imm32 @0x4159EF 0x4672F4 -> 0x43C000 (keeps its relocation entry; the `bound` limits are already 0..0x1FF).
Together with the 0x83 -> 0x200 loop limits (patch_indep_hero_spells_v2) the tactical AI can now use AoWx spells.
Dry-run default; --apply / --revert.  Backup backup\AoWTCPCK.dll.bak_checkunittab.
"""
import os, shutil, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

TC, D = game_file("AoWTCPCK.dll"), 0x400C00
SITE, OLD, NEW = 0x4159EF, 0x4672F4, 0x43C000


def main():
    apply, revert = "--apply" in sys.argv, "--revert" in sys.argv
    b = bytearray(open(TC, "rb").read())
    assert bytes(b[SITE - D - 3:SITE - D]) == bytes.fromhex("0fb680"), "site moved"
    cur = struct.unpack_from("<I", b, SITE - D)[0]
    print("site %#x: table %#x (%s)" % (SITE, cur, {OLD: "old/unpatched", NEW: "PATCHED"}.get(cur, "?")))
    if cur not in (OLD, NEW):
        return 1
    if revert:
        struct.pack_into("<I", b, SITE - D, OLD); open(TC, "wb").write(b); print("reverted"); return 0
    if cur == NEW:
        print("ALREADY PATCHED"); return 0
    if not apply:
        print("Dry run OK - rerun with --apply"); return 0
    bk = bak_path(TC, ".bak_checkunittab")
    if not os.path.exists(bk):
        shutil.copy2(TC, bk); print("backup ->", bk)
    struct.pack_into("<I", b, SITE - D, NEW); open(TC, "wb").write(b); print("applied")
    return 0


if __name__ == "__main__":
    sys.exit(main())
