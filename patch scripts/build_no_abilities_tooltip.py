#!/usr/bin/env python3
r"""Remove the "Lists unit's abilities" hover tooltip from ability listboxes.

User request (2026-08-21): the descriptive hover popup over the abilities
list (noticed in leader customization; the same tooltip exists on the ability
list of 8 windows in AoWx.exe form streams) is unnecessary and annoying.

MECHANISM: each form stream sets, on the ability listbox,
    ToolTip = General.ToolTip
    ToolTipText.Strings = ("Lists unit's abilities")
The toolkit's hover state machine (aowInt @0x5980BA80) only shows a tooltip
when the strings' Count > 0 (`call [vmt+0x14]; test eax,eax; jle skip`), so
an EMPTY list = no popup, with zero risk to the tooltip machinery elsewhere.

DFM streams are length-sensitive, so the 26-byte property value
    vaList(01) vaString(06) len(16) "Lists unit's abilities" listEnd(00)
is re-encoded IN PLACE, same length, as an empty list padded with four
`Tag = 0` assignments:
    vaList(01) listEnd(00)                       -> ToolTipText.Strings = ()
    (03 "Tag" vaInt8(02) 00) x4                  -> Tag := 0 (its default)
2 + 6*4 = 26 bytes; the stream stays byte-for-byte aligned. `Tag` is the one
published property EVERY component inherits from VCL30's TComponent (present
in its RTTI prop table right after Name - verified), so the standard TReader
that loads these forms always accepts it; the repeated default assignment is
a no-op. (v1 padded with ToolTipStatic/Visible, which are published on OTHER
classes in the toolkit but not on this listbox -> EReadError at startup,
reverted 2026-08-21.)

Patches every occurrence found (8 in the shipped exe), located by searching
for the full `ToolTipText.Strings` + value pattern, so offsets need not be
hardcoded. Backup: AoWx.exe.bak_abtooltip. Dry-run default; --apply/--revert.
"""
import os, re, shutil, sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
EXE = os.path.join(GAME, "AoWx.exe")
BAK = EXE + ".bak_abtooltip"

PROP = b"\x13ToolTipText.Strings"
OLD_VAL = b"\x01\x06\x16Lists unit's abilities\x00"
NEW_VAL = b"\x01\x00" + b"\x03Tag\x02\x00" * 4
assert len(OLD_VAL) == len(NEW_VAL) == 26


def main():
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if revert:
        if os.path.exists(BAK):
            shutil.copy2(BAK, EXE); print("restored AoWx.exe"); return 0
        print("no backup"); return 1

    d = bytearray(open(EXE, "rb").read())
    old_pat = PROP + OLD_VAL
    new_pat = PROP + NEW_VAL
    olds = [m.start() for m in re.finditer(re.escape(old_pat), bytes(d))]
    news = [m.start() for m in re.finditer(re.escape(new_pat), bytes(d))]

    if not olds and news:
        print("ALL ALREADY PATCHED (%d sites)" % len(news)); return 0
    if not olds:
        print("no sites found - nothing to do"); return 1

    print("found %d tooltip site(s):" % len(olds), [hex(o) for o in olds])
    print("ToolTipText.Strings -> empty list (+ 4x inert 'Tag = 0' padding)")
    if not apply:
        print("\nDry run OK. Re-run with --apply (or --revert)."); return 0

    if not os.path.exists(BAK):
        shutil.copy2(EXE, BAK); print("Backup ->", os.path.basename(BAK))
    for off in olds:
        d[off:off + len(old_pat)] = new_pat
    open(EXE, "wb").write(d)
    print("AoWx.exe patched successfully (%d sites)." % len(olds))
    return 0


if __name__ == "__main__":
    sys.exit(main())
