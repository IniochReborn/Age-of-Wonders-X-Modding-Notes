r"""
Construct dialog one row taller (2026-10-18; user: "the construct scroll bar is messed up - instead of a scrollbar,
slightly increase the window so Build Bridge fits").  AoWx.exe only, DFM resource TCONSTRUCTDLG, same-length edits.

Layout (DFM @file 0xAF80C, aowInt Alignment model): Dlg (ahCenter, WinHeight 208) > ConstructPnl (ahBoth, Top 55 /
Bottom 50 -> 103) > ConstructionList / ConstructionCostList / ConstructionTurnsList (ahBoth, Top 14 / Bottom 1 -> 88,
ItemHeight 17 -> 5 rows) + ConSB (ahNone, 88).  Construct / Cancel / celtic bar are ahBottom (BottomOffset 11), so
they follow the dialog's bottom edge.  With Build Bridge the control list has 5 entries (Rebuild, Roads, Tower,
Shipyard, Bridge) and the list showed the scrollbar.  +17 px (one item row) on the dialog: Dlg 208 -> 225, and the
stored design heights of the anchored children are raised to match (panel 103 -> 120, the three lists and ConSB
88 -> 105) so the first layout pass and the alignment pass agree.  Every value keeps its DFM encoding (Int16 / Int8)
-> no resource size change.  The dialog stays centred (ahCenter).

Dry-run default; --apply / --revert (exact, vanilla values) / --exe <copy>.  Backup <game>\backup\AoWx.exe.bak_condlg.
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
import dfm_edit

EXE = game_file("AoWx.exe")
DFM_AT = 0xAF80C
ROW = 17
EDITS = [   # (path suffix, prop, vanilla, new)
    ("/ConstructDlg/Dlg", "WinHeight", 208, 208 + ROW),
    ("/ConstructDlg/ConstructPnl", "WinHeight", 103, 103 + ROW),
    ("/ConstructDlg/ConstructionList", "WinHeight", 88, 88 + ROW),
    ("/ConstructDlg/ConstructionCostList", "WinHeight", 88, 88 + ROW),
    ("/ConstructDlg/ConstructionTurnsList", "WinHeight", 88, 88 + ROW),
    ("/ConstructDlg/ConSB", "WinHeight", 88, 88 + ROW),
]


def spans(d):
    assert d[DFM_AT:DFM_AT + 4] == b"TPF0" and d[DFM_AT + 5:DFM_AT + 5 + 13] == b"TConstructDlg", "TConstructDlg DFM not found"
    w = dfm_edit.walk(d[DFM_AT:DFM_AT + 0x20000])
    out = []
    for path, prop, van, new in EDITS:
        hits = [p for p in w.props if p[0] == path and p[1] == prop]
        assert len(hits) == 1, (path, prop, len(hits))
        _, _, t, s, e, v = hits[0]
        assert t in (dfm_edit.I8, dfm_edit.I16), (path, t)
        n = 1 if t == dfm_edit.I8 else 2
        lo, hi = (-128, 127) if n == 1 else (-32768, 32767)
        assert lo <= new <= hi, "new value does not fit the stored encoding"
        out.append((path, prop, DFM_AT + e - n, n, v, van, new))
    return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--exe", default=EXE); a = ap.parse_args()
    d = bytearray(open(a.exe, "rb").read())
    sp = spans(bytes(d))
    states = []
    for path, prop, off, n, cur, van, new in sp:
        st = "vanilla" if cur == van else "ours" if cur == new else "FOREIGN(%d)" % cur
        states.append(st); print("  %-40s %s %4d  %s  @file %#x" % (path, prop, cur, st, off))
    if any(s.startswith("FOREIGN") for s in states): print("ABORT (unexpected value)"); return 1
    n_ = bytearray(d)
    for path, prop, off, n, cur, van, new in sp:
        struct.pack_into("<b" if n == 1 else "<h", n_, off, van if a.revert else new)
    if n_ == d: print("already %s" % ("reverted" if a.revert else "applied")); return 0
    if not (a.apply or a.revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if os.path.abspath(a.exe) == os.path.abspath(EXE):
        bak = bak_path(a.exe, ".bak_condlg")
        if not os.path.exists(bak): shutil.copy2(a.exe, bak); print("backup ->", bak)
    with open(a.exe, "r+b") as f: f.write(n_)
    assert open(a.exe, "rb").read() == bytes(n_)
    assert dfm_edit.walk(bytes(n_)[DFM_AT:DFM_AT + 0x20000]).consumed == dfm_edit.walk(bytes(d)[DFM_AT:DFM_AT + 0x20000]).consumed
    print("written", a.exe); return 0


if __name__ == "__main__":
    sys.exit(main())
