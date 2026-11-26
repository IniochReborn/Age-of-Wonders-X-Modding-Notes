#!/usr/bin/env python3
r"""AoWx -- clamp TAOWMemo's first-visible-line at 0 in the SETTER
(aowInt.dpl) -- kills the "Exception during Draw" from a negative index.

ADOPTED 2026-08-31 from BXL/Ziggurat's build_memo_clamp.py (his RE kept):
AoWMemo.TAOWMemo.SetListOff @0x59819298 clamps the UPPER bound only. Two
negative paths: (1) any negative request is `< Count` and stored verbatim
(the wheel-scroll case -- OUR 402 wheel patch already clamps this at the
CALLER, but only for the wheel); (2) an EMPTY memo stores Count-1 = -1.
TAOWMemo.Draw indexes Lines[FirstLine+i] -> EListError -> "Exception
during Draw", widget stops painting.

FIX (in place, LENGTH-NEUTRAL, no cave): the function computes Count twice
and the second computation is redundant (EAX still holds it) -- those 11
bytes fund the missing lower clamp:

  OLD @0x598192AB: 7c0e | 8b83 88010000 8b10 ff5214 | 8bf0 | 4e
       jl +14       <recompute Count (redundant)>     mov esi,eax  dec esi
  NEW:             7c03 | 89c6 | 4e | 85f6 | 7902 | 31f6 | 90*5
       jl +3   mov esi,eax  dec esi  test esi,esi  jns +2  xor esi,esi

Both arms converge on the lower clamp: negative request -> 0; empty-memo
-1 -> 0. "FirstLine 0, Count 0" is every memo's initial state, so 0 is
provably safe. Behaviour change: scrolling above the top pins at line 0.
Complements (does not replace) our wheel-side clamp. Site reloc-scanned
clean on our aowInt.dpl 2026-08-31; tail signature verified.

⚠ aowInt.dpl is LIVE (no .dll twin). CODE VA = file + 0x59800C00.

Usage: dry run default; --apply; --revert (surgical).
"""
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.environ.get("AOW_GAME_DIR") or os.path.dirname(HERE)
DLL = os.path.join(GAME, "aowInt.dpl")
BAK = DLL + ".bak_memoclamp"

D = 0x59800C00
SITE = 0x598192AB
OLD = bytes.fromhex("7c0e8b83880100008b10ff52148bf04e")
NEW = bytes.fromhex("7c0389c64e85f6790231f69090909090")
TAIL = 0x598192BB
TAIL_EXPECT = bytes.fromhex("3bb32801000074")


def main():
    apply = "--apply" in sys.argv
    revert = "--revert" in sys.argv
    d = bytearray(open(DLL, "rb").read())
    assert bytes(d[TAIL - D:TAIL - D + len(TAIL_EXPECT)]) == TAIL_EXPECT, \
        "SetListOff tail signature mismatch - wrong function?"
    cur = bytes(d[SITE - D:SITE - D + 16])
    st = "original" if cur == OLD else "applied" if cur == NEW else "FOREIGN"
    print("  SetListOff clamp @0x%08X  %s" % (SITE, st))
    if st == "FOREIGN":
        print("FOREIGN: %s - refusing" % cur.hex())
        return 1
    if revert:
        d[SITE - D:SITE - D + 16] = OLD
        open(DLL, "wb").write(bytes(d))
        print("reverted")
        return 0
    if not apply:
        print("dry run (--apply / --revert)")
        return 0
    if st == "applied":
        print("already applied")
        return 0
    if not os.path.isfile(BAK):
        shutil.copy2(DLL, BAK)
        print("backed up")
    d[SITE - D:SITE - D + 16] = NEW
    open(DLL, "wb").write(bytes(d))
    print("APPLIED - test: wheel-scroll a city text box up past the top "
          "(pins at first line, no Draw exception); empty text boxes draw "
          "fine; normal scrolling unchanged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
