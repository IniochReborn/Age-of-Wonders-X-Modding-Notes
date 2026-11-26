#!/usr/bin/env python3
r"""Make scrollbar-less TAOWMemo text boxes fully INERT to the mouse wheel.

User call (2026-08-21): city-view text boxes "just shouldn't be scrollable" -
they have no scrollbar, and wheel-scrolling them (even clamped by
build_memo_scroll_clamp.py) is unwanted.

The WheelScroll cave (@0x59822880, mouse-wheel patch) ends in a no-scrollbar
fallback that adjusts the hovered control's first-visible-line directly:

  0x59822A11  cmp [ebp-0x14],1        ; mode: 0=listbox 1=memo >1=other
  0x59822A15  je  0x59822A25          ; memo -> direct first-line adjust
  0x59822A17  jg  0x59822A55          ; other -> ret 0
  0x59822A1D  ...listbox SetListOff path (clamps, keep)...

ONE-BYTE PATCH: retarget the memo je to the ret-0 exit (rel8 0x0E -> 0x3E),
so a memo with no scrollbar of its own and no sibling scrollbar is simply not
scrolled. Memos that DO have a scrollbar (own [+0x120] or a hunted sibling
TAOWVScrollBar) still scroll through the earlier scrollbar path, unchanged.
The clamp fix stays as a safety net for those paths.

Backup: aowInt.dpl.bak_memoinert. Dry-run default; --apply / --revert.
"""
import os, shutil, sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DPL = os.path.join(GAME, "aowInt.dpl")
BAK = DPL + ".bak_memoinert"
V2F = 0x59800C00

SITE = 0x59822A15            # je rel8 (memo fallback)
OLD = bytes.fromhex("740e")  # je 0x59822A25 (memo first-line adjust)
NEW = bytes.fromhex("743e")  # je 0x59822A55 (ret 0: not scrolled)
CTX = 0x59822A11             # cmp dword [ebp-0x14],1 must precede
CTX_BYTES = bytes.fromhex("837dec01")


def main():
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    d = bytearray(open(DPL, "rb").read())
    off = SITE - V2F
    assert bytes(d[CTX - V2F:CTX - V2F + 4]) == CTX_BYTES, "context mismatch"
    cur = bytes(d[off:off + 2])

    if revert:
        assert cur == NEW, "patch not present: " + cur.hex()
        d[off:off + 2] = OLD
        open(DPL, "wb").write(d)
        print("reverted: memo no-scrollbar wheel fallback restored")
        return 0

    if cur == NEW:
        print("ALL ALREADY PATCHED"); return 0
    assert cur == OLD, "unexpected bytes: " + cur.hex()
    print("WheelScroll memo fallback %#x: je +0x0E -> je +0x3E (ret 0)" % SITE)
    print("Scrollbar-less memos are now inert to the wheel.")
    if not apply:
        print("\nDry run OK. Re-run with --apply (or --revert)."); return 0
    if not os.path.exists(BAK):
        shutil.copy2(DPL, BAK); print("Backup ->", os.path.basename(BAK))
    d[off:off + 2] = NEW
    open(DPL, "wb").write(d)
    print("aowInt.dpl patched successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
