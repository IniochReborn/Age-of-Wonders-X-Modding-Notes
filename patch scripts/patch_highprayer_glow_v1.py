#!/usr/bin/env python3
r"""
AoWEPACK.dll: units blessed by High Prayer show the blue "enchanted" sparkle glow in combat (2026-10-10).

The glow (TCPCK TTacticalCombatUnitHS.Show @0x422754 `test byte [unit+0x25],0x20` -> general-FX list slot 0x46
ShowLooped; same test on the strategic map in TAbstractUnit.ShowEx @0x557819BB) is driven by ONE flag on the TUnit,
bit 0x20 of +0x25, refreshed by AoWE.TAbstractUnit.UpdateEnchanted 0x5577F18C (sole caller: TAbstractUnit.Changed
@0x55780FC9).  UpdateEnchanted sets the bit iff the unit has an ENABLED ability from TAbilityControl's type-4 list
([ctl+0x1C]; RegisterAbility files each ability under its type byte +0x24: 0 Enhancement, 1 Handicap, 2 Movement,
3 Combat, 4 Enchantment).  Bloodlust (0xA8) is type 4 in vanilla -> Bloodbath already glows; the High Prayer blessing
(0x64, THighPrayerBlessingAbility, a TDurationAbility like Bloodlust) is type 0 -> no glow.

Patch = ONE immediate byte in THighPrayerBlessingAbility.Create 0x557BB764: `mov byte [esi+0x24],0` @0x557BB7BE ->
4.  The type byte is set only in the ctor (TAbility.ReadWrite streams +0x10..+0x20 only), the ctor runs once at
registration before RegisterAbility reads GetType (VMT+0x54).  Every consumer of the type-4 list that touches
enchantment data (RemoveEnchantments 0x5577F1EC / RegisterEnchantments 0x5577F29C / UnregisterEnchantments
0x5577F328 / AbilityToEnchantment 0x5577F3B4 used by CanDispelEnchantment + ListEnchantments) IsClass-guards on
TUnitEnchantmentAbility first, so the blessing stays non-dispellable and off the enchantment list - exactly how
vanilla Bloodlust already lives in that list.  Visible side effect: the ability-type label in unit info lists reads
"Enchantment" instead of "Enhancement" for the blessing.  Timing: patch_bloodbath_v1.py's cave c7 already calls
unit.Changed after the tactical grant (glow on the spot); CombatDone -> RemoveAbility calls Changed -> glow gone.
Backup <game>\backup\AoWEPACK.dll.bak_hpglow.  Dry run by default; --apply / --revert.
"""
import argparse, os, shutil, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_dir, game_file

DEFAULT_DLL = game_file("AoWEPACK.dll")   # 2026-10-11: de-baked
BAK_SUFFIX = ".bak_hpglow"
CODE_V2F = 0x55700C00
SITE = 0x557BB7BE                                   # THighPrayerBlessingAbility.Create: mov byte [esi+0x24], TYPE
CTX = bytes.fromhex("c7460c64000000")               # preceded by mov [esi+0xC], 0x64 (ability id) @0x557BB7B7
ORIG = bytes.fromhex("c6462400c6462803")            # type 0 ; mode 3 (combat only)
NEW = bytes.fromhex("c6462404c6462803")             # type 4 = Enchantment


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dll", default=DEFAULT_DLL)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read())
    f = SITE - CODE_V2F
    if d[f - len(CTX):f] != CTX: print("ABORT: context mismatch at %#x" % SITE); return 1
    live = bytes(d[f:f + len(ORIG)])
    state = "vanilla" if live == ORIG else "ours" if live == NEW else "OTHER"
    print("site %#x: %s (%s)" % (SITE, state, live.hex()))
    if state == "OTHER": print("ABORT"); return 1
    want = ORIG if a.revert else NEW
    if live == want: print("already %s" % ("reverted" if a.revert else "applied")); return 0
    d[f:f + len(want)] = want
    if not a.apply and not a.revert: print("1 byte change. Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(a.dll, BAK_SUFFIX)
    if not a.revert and not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    open(a.dll, "wb").write(bytes(d)); assert open(a.dll, "rb").read() == bytes(d)
    print("reverted" if a.revert else "Written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
