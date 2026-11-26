#!/usr/bin/env python3
r"""
AoWDevX: show more rows in the resource editor's random defender / prisoner tables (2026-10-18).

User: "each exploration site structure has a defender/prisoner list with 10 rows in the editor, so 10 sets of
defenders to choose from randomly - can these be expanded?"

FINDINGS (RE 2026-10-18):
  * The tables are NOT per map.  They live in the structure RESOURCES in Release\Release.hss:
      TExplorationSiteResource [+0x64] tag 0x19 "Defenders"   (ReadWrite 0x557C21C0; lairs/ruins/crypts/...)
      TDungeonResource         [+0x68] tag 0x1E "Prisoners"   (ReadWrite 0x557C6290; dungeons also have 0x19)
      TStructureResource       [+0x5C] tag 0x1C "Raze Defenders" (ReadWrite 0x55760554; not changed by default)
    Maps only reference the resource; a placed site's own fixed army (TExplorationSiteEditForm, 4x2 TUnitGrid) is a
    different thing.  Generated defenders are stored in the site's army in saves -> no map/save format involved.
  * Data structure: AoWE.TUnitIndexListCollection = ONE flat TUnitIndexList (Engine.TIntegerList, fill value -1)
    read as rows of width [+4] = 8.  Rows = ceil(len/8) (GetCount 0x55783514); a row's unit count = entries before the
    first -1 (GetCollectionCount 0x557834D8).  Streamed by TIntegerList.SaveToStream/LoadFromStream (count + RLE of
    the fill value) -> ANY length round-trips.  Live Release.hss already holds 8-, 9-, 10- AND 11-row tables (e.g.
    child 205/241 = 85/87 entries = 11 rows).
  * Game side has NO 10: every reader (TExplorationSite.GenerateDefenders 0x557C1FC0, TDungeon.GeneratePrisoners
    0x557C5C2C, TStructure.GenerateRazeDefenders 0x5575FD1C, 0x557BF22F) goes through GetRndCollection 0x557835B4 =
    random(GetCount) with up to 10 re-rolls past empty rows, then the first non-empty row.  (The 0x0A there is the
    re-roll count, not a row count.)  Empty rows are skipped, so gaps are harmless.
  * Editor side is what limits it: the TUnitIndexGrid (UnitIGrd, AoWEPACK 0x557FFCD8) sizes itself through
    ImageLib.TCustomImageDrawGrid.SetCount -> UpdateDimensions: rows = count div 8 + 1, clamped to
    [MinRowCount, MaxRowCount] (SetRowCount 0x55214F50, ILPACK).  DFM: MinRowCount 8, MaxRowCount 0 (no cap).  So a
    table shows ONE row past its last full row - the next row only appears once the last one holds 8 units, and the
    Add button (collection.AddUnit + grid.Invalidate, e.g. AoWDevX 0x409398/0x40A8A4/0x40ACC0) never re-sizes the grid
    until the form is reopened.  With most last rows < 8 units, users are stuck at the 10 rows they see.
  * Adding into any row beyond the data is safe: AddUnit -> TIntegerList.Put auto-grows via SetCount, padding with -1;
    TUnitIndexGrid.DrawCell 0x557FFDD0 skips indexes >= count.

FIX (this script): a same-length DFM edit in AoWDevX.exe - MinRowCount 8 -> ROWS (default 20) on
    TEXPLORATIONSITERESOURCEEDITFORM.DefendersGrid  (TDungeonResourceEditForm INHERITS it -> dungeon Defenders too)
    TDUNGEONRESOURCEEDITFORM.PrisonersGrid
    [--raze] TCONSTRUCTIONRESOURCEEDITFORM.RazeDefendersGrid
  Every table then always offers >= ROWS rows (more if the data already has more).  No game-binary or data change:
  rows the designer fills are saved into Release.hss and the game picks among them automatically.  Values are vaInt8
  (1..127), 1 byte each, no relocations, no resource-size change.

Dry-run default; --apply [--rows N] [--raze]; --revert (puts 8 back).  Backup AoWDevX.exe.bak_unitrows (first apply).
"""
import argparse, os, shutil, struct, sys
import pefile
from bakpath import game_dir, bak_path
import dfm_edit

BAK = ".bak_unitrows"
VANILLA = 8
GRIDS = [("TEXPLORATIONSITERESOURCEEDITFORM", "DefendersGrid", "exploration-site Defenders (dungeons inherit it)"),
         ("TDUNGEONRESOURCEEDITFORM", "PrisonersGrid", "dungeon Prisoners")]
RAZE = ("TCONSTRUCTIONRESOURCEEDITFORM", "RazeDefendersGrid", "construction Raze Defenders")


def find_sites(path, grids):
    pe = pefile.PE(path)
    d = bytes(pe.__data__)
    out = []
    want = {g[0]: g for g in grids}
    for t in pe.DIRECTORY_ENTRY_RESOURCE.entries:
        if t.id != 10:
            continue
        for e in t.directory.entries:
            nm = str(e.name) if e.name else ""
            if nm not in want:
                continue
            for l in e.directory.entries:
                r = l.data.struct
                o = pe.get_offset_from_rva(r.OffsetToData)
                blob = d[o:o + r.Size]
                w = dfm_edit.walk(blob)
                assert w.consumed == len(blob), "%s: DFM walk desync" % nm
                hits = [p for p in w.props if p[0].split("/")[-1] == want[nm][1] and p[1] == "MinRowCount"]
                assert len(hits) == 1, "%s.%s: expected one MinRowCount, got %d" % (nm, want[nm][1], len(hits))
                path_, name, typ, s, en, val = hits[0]
                assert typ == dfm_edit.I8 and en - s == 1 + len("MinRowCount") + 2, "%s: MinRowCount not vaInt8" % nm
                out.append((o + en - 1, val, want[nm]))
    found = {x[2][0] for x in out}
    missing = [g[0] for g in grids if g[0] not in found]
    assert not missing, "form(s) not found: %s" % missing
    return out


def main():
    ap = argparse.ArgumentParser(description="more rows in AoWDevX's random defender/prisoner tables")
    ap.add_argument("--game", default=game_dir())
    ap.add_argument("--exe", default=None, help="editor exe (default <game>\\AoWDevX.exe)")
    ap.add_argument("--rows", type=int, default=20)
    ap.add_argument("--raze", action="store_true", help="also the construction resources' Raze Defenders table")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    a = ap.parse_args()
    exe = a.exe or os.path.join(a.game, "AoWDevX.exe")
    assert 1 <= a.rows <= 127, "--rows must fit vaInt8 (1..127)"
    grids = GRIDS + [RAZE]          # always inspect all three; only write the selected ones
    sites = find_sites(exe, grids)
    sel = {g[0] for g in GRIDS} | ({RAZE[0]} if a.raze else set())
    target = VANILLA if a.revert else a.rows
    todo = []
    for off, cur, g in sites:
        state = "vanilla" if cur == VANILLA else "patched (%d)" % cur
        print("  file %#08x  %-34s MinRowCount %3d  %s  - %s" % (off, g[0] + "." + g[1], cur, state, g[2]))
        if a.revert:
            if cur != VANILLA:
                todo.append((off, cur))
        elif g[0] in sel and cur != target:
            if cur != VANILLA and cur not in range(1, 128):
                print("    unexpected value - refusing"); return 1
            todo.append((off, cur))
    if not todo:
        print("NOTHING TO DO (%s)" % ("all vanilla" if a.revert else "already %d rows" % target)); return 0
    if not (a.apply or a.revert):
        print("\nDry run OK: %d site(s) -> %d.  Re-run with --apply (or --revert)." % (len(todo), target)); return 0
    if a.apply and not os.path.exists(bak_path(exe, BAK)):
        shutil.copyfile(exe, bak_path(exe, BAK)); print("backup -> " + bak_path(exe, BAK))
    with open(exe, "r+b") as f:
        for off, _ in todo:
            f.seek(off); f.write(bytes([target]))
    for off, _ in todo:
        with open(exe, "rb") as f:
            f.seek(off); assert f.read(1)[0] == target, "read-back failed @%#x" % off
    print("%s: %d site(s) -> MinRowCount %d.  Close + reopen AoWDevX; resource editor -> an exploration site / dungeon"
          " -> Defenders (Prisoners) tab now lists %d rows; fill any row, save Release.hss."
          % ("reverted" if a.revert else "applied", len(todo), target, target))
    return 0


if __name__ == "__main__":
    sys.exit(main())
