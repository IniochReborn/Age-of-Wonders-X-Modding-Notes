#!/usr/bin/env python3
r"""Combat-cast fix for high-id spells: widen the SpellTypes[] range checks.

Symptom: casting (or AI evaluating) a spell with id > 130 IN TACTICAL COMBAT
raised "Range check error" / "Exception during OnCastSpell" (e.g. Magic Sight
id 200). Cause: AoWTCPCK.dll reads `AoWTC.SpellTypes[id]` (static array
[0..130] of byte @0x4672F4) at 12 combat sites, each guarded by a Delphi `bound`
range check against a `[0, 130]` constant pair. New spells index past 130 -> the
bound faults before the (harmless) read.

The DATA section maps well past the array (to 0x46B800) and every byte in
[131..255] there reads 0 = SpellType 0, the generic type Enchant Weapon and
nearly all spells use — correct for an enchant like Magic Sight. So the read is
safe; only the bound is fatal. Fix = raise the upper bound of the 8 (verified
SpellTypes-exclusive, all value [0,130]) bounds-constant pairs to 255. Each pair
is `[lo:i32=0][hi:i32=130]`; we set hi -> 255. No code bytes move.

(The book-visibility half of the same undersized-array bug is fixed separately
in build_spellbook_id_fix.py.)

Backup AoWTCPCK.dll.bak_spelltypes. Dry-run; --apply / --revert.
"""
import os, shutil, struct, sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DLL = os.path.join(GAME, "AoWTCPCK.dll")
BACKUP = DLL + ".bak_spelltypes"

VA2FILE = 0x400C00
# spell-id [0..130] pairs (SpellTypes) — widened first pass
BOUND_PAIRS = [0x415120, 0x4180E8, 0x41B034, 0x41E00C,
               0x41EDF0, 0x423428, 0x427628, 0x4288A0,
               0x40CDC4,                                 # TCRangedToken kind-52 spell lookup
               # ability-id [0..169] pairs (ability-type table @0x467248) —
               # Magic Sight's enchantment ability id 170 overflows these
               0x40B0FC, 0x40CDCC, 0x40F4A8, 0x414D04, 0x415128,
               0x418130, 0x41B03C, 0x41EDF8, 0x4288A8]
OLD_HIS = (130, 169)
NEW_HI = 255

# static data fixes (DATA section: VA 0x467000 -> file 0x66000):
#   SpellTypes @file 0x662F4 is STATICALLY INITIALIZED (EnchW[16]=7 = the
#   unit-enchant combat-cast type; the TCRangedToken kind-52 path reads
#   SpellTypes[spellid] via ptr [0x4693F8] for the cast animation). Ids > 130
#   read neighboring static data -> garbage type -> "Error during Token Start".
#   Set proper types for our spells. Also zero the 2 alignment-padding bytes
#   between the ability-type table (@file 0x66248, [0..169]) and SpellTypes —
#   ability id 170 reads them once the [0..169] bounds are widened.
# ⚠ SUPERSEDED 2026-10-03 by patch_spelltypes_relocate_v1.py: SpellTypes now lives in a 512-entry table at
#   VA 0x43C000 (file 0x3B400) and the bound pairs are [0,511], so this script aborts with MISMATCH on the
#   live dll.  Its two SpellTypes writes below hit BreathDir[5] (file 0x663BC) — that was the bug.
DATA_FIXES = [
    (0x3B400 + 200, 7,   "SpellTypes[200] Magic Sight = 7 (EnchW's type)"),
    (0x3B400 + 201, 0,   "SpellTypes[201] Summon Mermaid = 0 (vanilla mermaid's)"),
    (0x66248 + 170, 0,   "ability-type padding byte [170] = 0"),
    (0x66248 + 171, 0,   "ability-type padding byte [171] = 0"),
]


def main():
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if revert:
        if os.path.exists(BACKUP):
            shutil.copy2(BACKUP, DLL); print("restored from backup"); return 0
        print("no backup"); return 1
    d = bytearray(open(DLL, 'rb').read())
    changed = 0
    for va in BOUND_PAIRS:
        off = va - VA2FILE + 4                    # hi dword
        lo = struct.unpack_from('<i', d, va - VA2FILE)[0]
        hi = struct.unpack_from('<i', d, off)[0]
        if lo != 0:
            print("ABORT: pair @0x%X lo=%d (expected 0)" % (va, lo)); return 1
        if hi == NEW_HI:
            continue
        if hi not in OLD_HIS:
            print("MISMATCH: pair @0x%X hi=%d" % (va, hi)); return 1
        struct.pack_into('<i', d, off, NEW_HI); changed += 1
        print("  pair @0x%X: [0..%d] -> [0..%d]" % (va, hi, NEW_HI))
    for off, val, why in DATA_FIXES:
        if d[off] != val:
            print("  data @file 0x%X: %d -> %d (%s)" % (off, d[off], val, why))
            d[off] = val; changed += 1
    print("%d change(s)" % changed)
    if not apply:
        print("Dry run OK — rerun with --apply (or --revert)."); return 0
    if not os.path.exists(BACKUP):
        shutil.copy2(DLL, BACKUP); print("Backup -> %s" % os.path.basename(BACKUP))
    open(DLL, 'wb').write(d); print("Written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
