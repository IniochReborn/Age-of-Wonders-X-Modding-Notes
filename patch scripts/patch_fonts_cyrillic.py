"""
patch_fonts_cyrillic.py - paint the 66 Russian glyphs into the bitmap fonts.

The game draws text from glyph strips in Int\\Fonts\\*.ILB, indexing images by
the raw text byte (verified: image id == ord(ch)). aowxlib.cyrillic assigns the
66 Cyrillic letters to byte values no game text ever uses, so adding glyphs at
those ids cannot disturb German/French/Italian/Spanish.

This patch covers the nine text fonts that carry ~99% of the game's text
(Age8/8s, Age10/10s/10b/10bs/10tb/10LB, Age16s). The three Age15 display fonts
and Age14G (one reference each in AoWx.exe - title/screen headers) are NOT yet
covered; they need composed 16-bit calligraphic art and will follow.

How each font is built:
  * Age8, Age10, Age10b get hand-drawn pixel art in each face's own style;
    letters identical to Latin (A E O ...) are copied from the font itself,
    And/N/R are mirrored into I/Ya, E-diaeresis becomes Yo.
  * The "s" shadow variants reuse the same letterforms; the black drop shadow
    is the glyph shifted down one row, drawn where no glyph pixel sits - the
    exact rule the retail s-fonts follow (verified on I L o .).
  * Age10tb and Age10LB get the plain Age10 glyphs, Age16s gets the Age10bs
    glyphs - byte-for-byte the strategy retail used for those fonts' accents.

Glyphs are RLESprite08 records cloned from a sibling glyph of the same library
(so palette index, load mode and naming all match), inserted in id order.
Existing never-referenced accent frames at claimed ids are replaced in place.

    python patch_fonts_cyrillic.py            dry run - report what would change
    python patch_fonts_cyrillic.py --apply    back up Int\\Fonts, then patch
    python patch_fonts_cyrillic.py --revert   restore the backup
"""
import os, sys, shutil, struct

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.abspath(os.path.join(HERE, ".."))
FONTS = os.path.join(GAME, "Int", "Fonts")
BACKUP = os.path.join(GAME, "backup", "Fonts.bak_cyrillic")

for cand in (os.path.join(GAME, "modding tools"),):
    if cand not in sys.path:
        sys.path.insert(0, cand)
from aowxlib import ilb                                              # noqa: E402
from aowxlib.cyrillic import RU_MAP, RU_ALPHABET                     # noqa: E402

# The byte mapping the glyphs are painted at MUST match what aowxlib.cyrillic
# encodes text with. If cyrillic.py ever changes its assignment, stop dead.
_EXPECTED = {"А": 0x80, "Е": 0x86, "Ё": 0x87, "Я": 0xA6, "а": 0xA9,
             "ё": 0xB0, "р": 0xC2, "я": 0xE3}
assert len(RU_MAP) == 66, "RU_MAP no longer has 66 letters"
for _ch, _b in _EXPECTED.items():
    assert RU_MAP[_ch] == _b, "RU_MAP moved %r: 0x%02X" % (_ch, RU_MAP[_ch])

A = "art"

# ---------------------------------------------------------------------------
# Age8 set - cell 11 rows, baseline row 7, caps rows 0-7, x-height rows 2-7.
# ---------------------------------------------------------------------------
SET_AGE8 = {
    "А": ("copy", "A"), "В": ("copy", "B"), "Е": ("copy", "E"),
    "Ё": ("copy", "Ë"), "К": ("copy", "K"), "М": ("copy", "M"),
    "Н": ("copy", "H"), "О": ("copy", "O"), "Р": ("copy", "P"),
    "С": ("copy", "C"), "Т": ("copy", "T"), "Х": ("copy", "X"),
    "И": ("mirror", "N"), "Я": ("mirror", "R"),
    "а": ("copy", "a"), "е": ("copy", "e"), "ё": ("copy", "ë"),
    "о": ("copy", "o"), "р": ("copy", "p"), "с": ("copy", "c"),
    "у": ("copy", "y"), "х": ("copy", "x"),
    "Б": (A, "#####|#....|#....|####.|#...#|#...#|#...#|####.", 0),
    "Г": (A, "#####|#....|#....|#....|#....|#....|#....|#....", 0),
    "Д": (A, ".####.|.#..#.|.#..#.|.#..#.|.#..#.|.#..#.|#...#.|######|#....#", 0),
    "Ж": (A, "#..#..#|#..#..#|.#.#.#.|..###..|.#.#.#.|#..#..#|#..#..#|#..#..#", 0),
    "З": (A, ".###.|#...#|....#|..##.|....#|....#|#...#|.###.", 0),
    "Й": (A, "#...#|.###.|#...#|#..##|#.#.#|##..#|#...#|#...#", 0),
    "Л": (A, ".####|.#..#|.#..#|.#..#|.#..#|.#..#|.#..#|#...#", 0),
    "П": (A, "#####|#...#|#...#|#...#|#...#|#...#|#...#|#...#", 0),
    "У": (A, "#...#|#...#|.#.#.|.#.#.|..#..|..#..|.#...|#....", 0),
    "Ф": (A, "..#..|.###.|#.#.#|#.#.#|#.#.#|.###.|..#..|..#..", 0),
    "Ц": (A, "#...#.|#...#.|#...#.|#...#.|#...#.|#...#.|#...#.|######|.....#", 0),
    "Ч": (A, "#...#|#...#|#...#|.####|....#|....#|....#|....#", 0),
    "Ш": (A, "#..#..#|#..#..#|#..#..#|#..#..#|#..#..#|#..#..#|#..#..#|#######", 0),
    "Щ": (A, "#..#..#.|#..#..#.|#..#..#.|#..#..#.|#..#..#.|#..#..#.|#..#..#.|"
             "########|.......#", 0),
    "Ъ": (A, "##....|.#....|.#....|.###..|.#..#.|.#..#.|.#..#.|.###..", 0),
    "Ы": (A, "#....#|#....#|#....#|###..#|#..#.#|#..#.#|#..#.#|###..#", 0),
    "Ь": (A, "#....|#....|#....|###..|#..#.|#..#.|#..#.|###..", 0),
    "Э": (A, ".###.|#...#|....#|..###|....#|....#|#...#|.###.", 0),
    "Ю": (A, "#...###.|#..#...#|#..#...#|##.#...#|#..#...#|#..#...#|#..#...#|"
             "#...###.", 0),
    "б": (A, "..##.|.#...|.##..|#..#.|#..#.|#..#.|#..#.|.##..", 0),
    "в": (A, "###..|#..#.|###..|#..#.|#..#.|###..", 2),
    "г": (A, "####.|#....|#....|#....|#....|#....", 2),
    "д": (A, ".###.|.#.#.|.#.#.|.#.#.|#..#.|#####|#...#", 2),
    "ж": (A, "#.#.#|#.#.#|.###.|#.#.#|#.#.#|#.#.#", 2),
    "з": (A, ".##..|#..#.|..#..|...#.|#..#.|.##..", 2),
    "и": (A, "#..#.|#..#.|#.##.|##.#.|#..#.|#..#.", 2),
    "й": (A, "#..#.|.##..|#..#.|#.##.|##.#.|#..#.|#..#.", 1),
    "к": (A, "#..#.|#.#..|##...|##...|#.#..|#..#.", 2),
    "л": (A, ".###.|.#.#.|.#.#.|.#.#.|.#.#.|#..#.", 2),
    "м": (A, "#...#.|##.##.|#.#.#.|#...#.|#...#.|#...#.", 2),
    "н": (A, "#..#.|#..#.|####.|#..#.|#..#.|#..#.", 2),
    "п": (A, "####.|#..#.|#..#.|#..#.|#..#.|#..#.", 2),
    "т": (A, "#####|..#..|..#..|..#..|..#..|..#..", 2),
    "ф": (A, "...#...|...#...|.#####.|#..#..#|#..#..#|#..#..#|.#####.|...#...|"
             "...#...", 0),
    "ц": (A, "#..#.|#..#.|#..#.|#..#.|#..#.|#####|....#", 2),
    "ч": (A, "#..#.|#..#.|.###.|...#.|...#.|...#.", 2),
    "ш": (A, "#..#..#|#..#..#|#..#..#|#..#..#|#..#..#|#######", 2),
    "щ": (A, "#..#..#.|#..#..#.|#..#..#.|#..#..#.|#..#..#.|########|.......#", 2),
    "ъ": (A, "##...|.#...|.##..|.#.#.|.#.#.|.##..", 2),
    "ы": (A, "#....#|#....#|##...#|#.#..#|#.#..#|##...#", 2),
    "ь": (A, "#....|#....|###..|#..#.|#..#.|###..", 2),
    "э": (A, ".##..|#..#.|..##.|...#.|#..#.|.##..", 2),
    "ю": (A, "#..##..|#.#..#.|###..#.|#.#..#.|#.#..#.|#..##..", 2),
    "я": (A, ".####|#...#|.####|..#.#|.#..#|#...#", 2),
}

# ---------------------------------------------------------------------------
# Age10 set - cell 12 rows, baseline row 8, caps rows 0-8, x-height rows 3-8.
# ---------------------------------------------------------------------------
SET_AGE10 = {
    "А": ("copy", "A"), "В": ("copy", "B"), "Е": ("copy", "E"),
    "Ё": ("copy", "Ë"), "З": ("copy", "3"), "К": ("copy", "K"),
    "М": ("copy", "M"), "Н": ("copy", "H"), "О": ("copy", "O"),
    "Р": ("copy", "P"), "С": ("copy", "C"), "Т": ("copy", "T"),
    "Х": ("copy", "X"),
    "И": ("mirror", "N"), "Я": ("mirror", "R"),
    "а": ("copy", "a"), "е": ("copy", "e"), "ё": ("copy", "ë"),
    "о": ("copy", "o"), "р": ("copy", "p"), "с": ("copy", "c"),
    "у": ("copy", "y"), "х": ("copy", "x"),
    "Б": (A, "######.|#......|#......|#####..|#....#.|#.....#|#.....#|#....#.|"
             "#####..", 0),
    "Г": (A, "######|#.....|#.....|#.....|#.....|#.....|#.....|#.....|#.....", 0),
    "Д": (A, "..####..|..#..#..|..#..#..|..#..#..|..#..#..|.#...#..|.#...#..|"
             "#.....#.|########|#......#", 0),
    "Ж": (A, "#...#...#|.#..#..#.|.#..#..#.|..#.#.#..|...###...|..#.#.#..|"
             ".#..#..#.|.#..#..#.|#...#...#", 0),
    "Й": (A, ".#...#.|..###..|#.....#|#....##|#...#.#|#..#..#|#.#...#|##....#|"
             "#.....#", 0),
    "Л": (A, "..#####|..#...#|..#...#|..#...#|..#...#|..#...#|..#...#|.#....#|"
             "##....#", 0),
    "П": (A, "#######|#.....#|#.....#|#.....#|#.....#|#.....#|#.....#|#.....#|"
             "#.....#", 0),
    "У": (A, "#.....#|#.....#|.#...#.|.#...#.|..#.#..|...##..|...#...|..#....|"
             "##.....", 0),
    "Ф": (A, "...#...|.#####.|#..#..#|#..#..#|#..#..#|.#####.|...#...|...#...|"
             "...#...", 0),
    "Ц": (A, "#.....#.|#.....#.|#.....#.|#.....#.|#.....#.|#.....#.|#.....#.|"
             "#.....#.|########|.......#|.......#", 0),
    "Ч": (A, "#.....#|#.....#|#.....#|#....##|.####.#|......#|......#|......#|"
             "......#", 0),
    "Ш": (A, "#...#...#|#...#...#|#...#...#|#...#...#|#...#...#|#...#...#|"
             "#...#...#|#...#...#|#########", 0),
    "Щ": (A, "#...#...#.|#...#...#.|#...#...#.|#...#...#.|#...#...#.|#...#...#.|"
             "#...#...#.|#...#...#.|##########|.........#|.........#", 0),
    "Ъ": (A, "###....|..#....|..#....|..####.|..#...#|..#...#|..#...#|..#...#|"
             "..####.", 0),
    "Ы": (A, "#......#|#......#|#......#|####...#|#...#..#|#...#..#|#...#..#|"
             "#...#..#|####...#", 0),
    "Ь": (A, "#.....|#.....|#.....|####..|#...#.|#....#|#....#|#...#.|####..", 0),
    "Э": (A, ".####..|#....#.|......#|......#|...####|......#|......#|#....#.|"
             ".####..", 0),
    "Ю": (A, "#...####..|#..#....#.|#.#......#|#.#......#|###......#|#.#......#|"
             "#.#......#|#..#....#.|#...####..", 0),
    "б": (A, "..###|.#...|#....|####.|#...#|#...#|#...#|#...#|.###.", 0),
    "в": (A, "####.|#...#|####.|#...#|#...#|####.", 3),
    "г": (A, "####|#...|#...|#...|#...|#...", 3),
    "д": (A, ".####.|.#..#.|.#..#.|.#..#.|######|#....#", 3),
    "ж": (A, "#..#..#|.#.#.#.|..###..|.#.#.#.|#..#..#|#..#..#", 3),
    "з": (A, ".###.|#...#|..##.|....#|#...#|.###.", 3),
    "и": (A, "#...#|#..##|#.#.#|##..#|#...#|#...#", 3),
    "й": (A, "#...#|.###.|#...#|#..##|#.#.#|##..#|#...#|#...#", 1),
    "к": (A, "#..##|#.#..|##...|##...|#.#..|#..##", 3),
    "л": (A, ".####|.#..#|.#..#|.#..#|.#..#|##..#", 3),
    "м": (A, "#.....#|##...##|#.#.#.#|#..#..#|#.....#|#.....#", 3),
    "н": (A, "#...#|#...#|#####|#...#|#...#|#...#", 3),
    "п": (A, "#####|#...#|#...#|#...#|#...#|#...#", 3),
    "т": (A, "#####|..#..|..#..|..#..|..#..|..#..", 3),
    "ф": (A, "...#...|...#...|.#####.|#..#..#|#..#..#|#..#..#|#..#..#|.#####.|"
             "...#...|...#...", 1),
    "ц": (A, "#...#.|#...#.|#...#.|#...#.|#...#.|######|.....#", 3),
    "ч": (A, "#...#|#...#|.####|....#|....#|....#", 3),
    "ш": (A, "#..#..#|#..#..#|#..#..#|#..#..#|#..#..#|#######", 3),
    "щ": (A, "#..#..#.|#..#..#.|#..#..#.|#..#..#.|#..#..#.|########|.......#", 3),
    "ъ": (A, "##....|.#....|.####.|.#...#|.#...#|.####.", 3),
    "ы": (A, "#.....#|#.....#|####..#|#...#.#|#...#.#|####..#", 3),
    "ь": (A, "#....|#....|####.|#...#|#...#|####.", 3),
    "э": (A, ".###.|#...#|..###|....#|#...#|.###.", 3),
    "ю": (A, "#..###.|#.#...#|###...#|#.#...#|#.#...#|#..###.", 3),
    "я": (A, ".####|#...#|.####|..#.#|.#..#|#...#", 3),
}

# ---------------------------------------------------------------------------
# Age10b (bold) set - cell 12 rows, baseline row 8, 2px strokes.
# ---------------------------------------------------------------------------
SET_AGE10B = {
    "А": ("copy", "A"), "В": ("copy", "B"), "Е": ("copy", "E"),
    "Ё": ("copy", "Ë"), "З": ("copy", "3"), "К": ("copy", "K"),
    "М": ("copy", "M"), "Н": ("copy", "H"), "О": ("copy", "O"),
    "Р": ("copy", "P"), "С": ("copy", "C"), "Т": ("copy", "T"),
    "Х": ("copy", "X"),
    "И": ("mirror", "N"), "Я": ("mirror", "R"),
    "а": ("copy", "a"), "е": ("copy", "e"), "ё": ("copy", "ë"),
    "о": ("copy", "o"), "р": ("copy", "p"), "с": ("copy", "c"),
    "у": ("copy", "y"), "х": ("copy", "x"),
    "Б": (A, "########..|##........|##........|#######...|##....##..|##.....##.|"
             "##.....##.|##....##..|#######...", 0),
    "Г": (A, "########|##......|##......|##......|##......|##......|##......|"
             "##......|##......", 0),
    "Д": (A, "...######..|...##...##.|...##...##.|...##...##.|..##....##.|"
             "..##....##.|.##.....##.|.##.....##.|###########|##.......##", 0),
    "Ж": (A, "##...##...##|##...##...##|.##..##..##.|..##.##.##..|...######...|"
             "..##.##.##..|.##..##..##.|##...##...##|##...##...##", 0),
    "Й": (A, "..##..##..|...####...|##.....##.|##...####.|##..##.##.|##..#..##.|"
             "##.##..##.|####...##.|##.....##.", 0),
    "Л": (A, "..########|..##....##|..##....##|..##....##|..##....##|..##....##|"
             ".##.....##|.##.....##|##......##", 0),
    "П": (A, "#########.|##.....##.|##.....##.|##.....##.|##.....##.|##.....##.|"
             "##.....##.|##.....##.|##.....##.", 0),
    "У": (A, "##.....##.|##.....##.|.##...##..|.##...##..|..##.##...|...###....|"
             "...##.....|..##......|###.......", 0),
    "Ф": (A, ".....##.....|..########..|.##..##..##.|.##..##..##.|.##..##..##.|"
             "..########..|.....##.....|.....##.....|.....##.....", 0),
    "Ц": (A, "##.....##..|##.....##..|##.....##..|##.....##..|##.....##..|"
             "##.....##..|##.....##..|##.....##..|###########|.........##|"
             ".........##", 0),
    "Ч": (A, "##.....##.|##.....##.|##.....##.|##.....##.|#########.|.......##.|"
             ".......##.|.......##.|.......##.", 0),
    "Ш": (A, "##...##...##|##...##...##|##...##...##|##...##...##|##...##...##|"
             "##...##...##|##...##...##|##...##...##|############", 0),
    "Щ": (A, "##...##...##.|##...##...##.|##...##...##.|##...##...##.|"
             "##...##...##.|##...##...##.|##...##...##.|##...##...##.|"
             "#############|...........##|...........##", 0),
    "Ъ": (A, "####.....|..##.....|..##.....|..######.|..##...##|..##...##|"
             "..##...##|..##...##|..######.", 0),
    "Ы": (A, "##.......##|##.......##|##.......##|######...##|##...##..##|"
             "##...##..##|##...##..##|##...##..##|######...##", 0),
    "Ь": (A, "##......|##......|##......|#######.|##....##|##....##|##....##|"
             "##....##|#######.", 0),
    "Э": (A, "...######..|..##....##.|.##......##|.........##|....#######|"
             ".........##|.##......##|..##....##.|...######..", 0),
    "Ю": (A, "##...######..|##..##....##.|##.##......##|##.##......##|"
             "#####......##|##.##......##|##.##......##|##..##....##.|"
             "##...######..", 0),
    "б": (A, "..####|.##...|##....|#####.|##..##|##..##|##..##|##..##|.####.", 0),
    "в": (A, "#####.|##..##|#####.|##..##|##..##|#####.", 3),
    "г": (A, "#####|##...|##...|##...|##...|##...", 3),
    "д": (A, "..#####.|..##.##.|..##.##.|..##.##.|.##..##.|.##..##.|########|"
             "##....##", 3),
    "ж": (A, "##..##..##|.##.##.##.|..######..|.##.##.##.|##..##..##|##..##..##", 3),
    "з": (A, ".####.|##..##|..###.|....##|##..##|.####.", 3),
    "и": (A, "##...##|##..###|##.#.##|###..##|##...##|##...##", 3),
    "й": (A, ".#...#.|..###..|##...##|##..###|##.#.##|###..##|##...##|##...##", 1),
    "к": (A, "##..##|##.##.|####..|####..|##.##.|##..##", 3),
    "л": (A, ".######|.##..##|.##..##|.##..##|##...##|##...##", 3),
    "м": (A, "##.....##|###...###|####.####|##.###.##|##..#..##|##.....##", 3),
    "н": (A, "##..##|##..##|######|##..##|##..##|##..##", 3),
    "п": (A, "######|##..##|##..##|##..##|##..##|##..##", 3),
    "т": (A, "######|..##..|..##..|..##..|..##..|..##..", 3),
    "ф": (A, "....##....|....##....|.########.|##..##..##|##..##..##|##..##..##|"
             "##..##..##|.########.|....##....|....##....", 1),
    "ц": (A, "##..##.|##..##.|##..##.|##..##.|##..##.|#######|.....##", 3),
    "ч": (A, "##..##|##..##|.#####|....##|....##|....##", 3),
    "ш": (A, "##..##..##|##..##..##|##..##..##|##..##..##|##..##..##|##########", 3),
    "щ": (A, "##..##..##.|##..##..##.|##..##..##.|##..##..##.|##..##..##.|"
             "###########|.........##", 3),
    "ъ": (A, "###....|.##....|.#####.|.##..##|.##..##|.#####.", 3),
    "ы": (A, "##....##|##....##|#####.##|##.##.##|##.##.##|#####.##", 3),
    "ь": (A, "##....|##....|#####.|##..##|##..##|#####.", 3),
    "э": (A, ".####.|##..##|..####|....##|##..##|.####.", 3),
    "ю": (A, "##..####.|##.##..##|#####..##|##.##..##|##.##..##|##..####.", 3),
    "я": (A, ".#####|##..##|.#####|.##.##|##..##|##..##", 3),
}

# ---------------------------------------------------------------------------
# Which fonts get which set, and how the pixels are indexed there.
#   source  - library the copy/mirror glyphs are decoded from (its full index
#             grid is reused verbatim, shadows included)
#   glyph   - palette index the art strokes use
#   shadow  - palette index for the derived drop shadow (None = no shadow)
#   transp  - background/transparent palette index for the RLE encoding
#   pal     - palette number for NEW records (replaced records keep their own)
#   cell    - full cell height in rows
# ---------------------------------------------------------------------------
CONFIGS = [
    ("Age8",    SET_AGE8,   "Age8",    1, None, 0, 0, 11),
    ("Age8s",   SET_AGE8,   "Age8s",   1, 0,    2, 0, 11),
    ("Age10",   SET_AGE10,  "Age10",   1, None, 0, 0, 12),
    ("Age10s",  SET_AGE10,  "Age10s",  2, 1,    0, 0, 12),
    ("Age10b",  SET_AGE10B, "Age10b",  1, None, 0, 0, 12),
    ("Age10bs", SET_AGE10B, "Age10bs", 2, 0,    1, 0, 12),
    ("Age10tb", SET_AGE10,  "Age10",   1, None, 0, 1, 12),
    ("Age10LB", SET_AGE10,  "Age10",   1, None, 0, 1, 12),
    ("Age16s",  SET_AGE10B, "Age10bs", 2, 0,    1, 1, 12),
]


def raw_indices(lib, r):
    """Decode an 8-bit RLE record to a full-cell grid of palette indices
    (None = transparent)."""
    w, h = r["w"], r["h"]
    grid = [[None] * w for _ in range(h)]
    if r.blank:
        return grid
    data = lib.record_bytes(r)
    ch = ilb.s32(r.get("ch", h))
    cx, cy = ilb.s32(r.get("cx", 0)), ilb.s32(r.get("cy", 0))
    b0 = (r.get("transp") or 0) & 0xFF
    p = 0
    for y in range(cy, cy + ch):
        ln = struct.unpack_from("<I", data, p)[0]
        p += 4
        n = ln - 4
        x = cx
        while n > 0:
            v = data[p]
            p += 1
            n -= 1
            if v == b0:
                cnt = data[p]
                p += 1
                n -= 1
                x += cnt
            else:
                if 0 <= x < w and 0 <= y < h:
                    grid[y][x] = v
                x += 1
    return grid


def rec_of(lib, iid):
    for im in lib.images:
        if im.id == iid and im.parts:
            return im.parts[0]
    return None


def build_glyph_grids(glyph_set, source_lib, glyph_idx, shadow_idx, cell):
    """Return {char: (w, grid)} - grid is cell rows of palette indices/None."""
    out = {}
    for ch, spec in glyph_set.items():
        kind = spec[0]
        if kind in ("copy", "mirror"):
            r = rec_of(source_lib, ord(spec[1]))
            if r is None:
                raise KeyError("source %s lacks glyph %r for %r"
                               % (source_lib.path, spec[1], ch))
            w = r["w"]
            grid = raw_indices(source_lib, r)
            if len(grid) < cell:
                grid = grid + [[None] * w for _ in range(cell - len(grid))]
            if kind == "mirror":
                grid = [list(reversed(row)) for row in grid]
                # flush left: the source's right padding lands on the left
                while w > 1 and all(row[0] is None for row in grid):
                    grid = [row[1:] + [None] for row in grid]
        else:                                        # hand-drawn art
            rows = spec[1].split("|")
            off = spec[2]
            w = max(len(ln) for ln in rows)
            grid = [[None] * w for _ in range(cell)]
            for i, ln in enumerate(rows):
                y = off + i
                if y >= cell:
                    raise ValueError("%r art overflows the %d-row cell" % (ch, cell))
                for x, c in enumerate(ln):
                    if c == "#":
                        grid[y][x] = glyph_idx
            if shadow_idx is not None:
                # retail rule: shadow = glyph shifted down 1 row, where empty
                for y in range(cell - 1, 0, -1):
                    for x in range(w):
                        if grid[y][x] is None and grid[y - 1][x] == glyph_idx:
                            grid[y][x] = shadow_idx
        out[ch] = (w, grid)
    return out


def encode_grid(rec, w, grid, transp):
    """Fill a record's geometry + RLE data from an index grid."""
    h = len(grid)
    rec["w"], rec["h"] = w, h
    rec["xs"] = rec["ys"] = 0
    rec["totw"], rec["toth"] = w, h
    rec["transp"] = transp
    top, left, bottom, right = h, w, -1, -1
    for y, row in enumerate(grid):
        for x in range(w):
            if row[x] is not None:
                top, bottom = min(top, y), max(bottom, y)
                left, right = min(left, x), max(right, x)
    if bottom < 0:
        raise ValueError("empty glyph")
    cw, chh = right - left + 1, bottom - top + 1
    rec["cx"], rec["cy"], rec["cw"], rec["ch"] = left, top, cw, chh
    rows = [[transp if grid[y][x] is None else grid[y][x]
             for x in range(left, left + cw)]
            for y in range(top, top + chh)]
    rec["newdata"] = ilb.encode_rle8(rows, transp)
    rec["size"] = len(rec["newdata"])


def patch_font(name, glyph_set, source_name, glyph_idx, shadow_idx, transp,
               pal, cell, libs):
    lib = libs[name]
    source_lib = libs[source_name]
    grids = build_glyph_grids(glyph_set, source_lib, glyph_idx, shadow_idx, cell)
    by_id = {im.id: im for im in lib.images}
    # template for NEW records: an accent sibling for pal-1 fonts (so palette
    # number and naming match how retail added those), else the 'A' record
    tmpl_id = 0xA1 if pal == 1 else ord("A")
    tmpl = rec_of(lib, tmpl_id) or rec_of(lib, ord("A"))
    replaced = added = 0
    for ch in RU_ALPHABET:
        w, grid = grids[ch]
        b = RU_MAP[ch]
        if b in by_id and by_id[b].parts:
            rec = by_id[b].parts[0]
            replaced += 1
        else:
            rec = ilb.Record(tmpl)               # shallow copy of the template
            rec["newdata"] = None
            img = ilb.Image(b, [rec])
            lib.images.append(img)
            by_id[b] = img
            added += 1
        encode_grid(rec, w, grid, transp)
    lib.images.sort(key=lambda im: im.id)
    return replaced, added, grids


def verify_font(path, glyph_set, grids, before_pixels):
    """Re-read the written file; every Cyrillic glyph must decode to exactly
    the intended grid, every untouched image to its previous pixels."""
    lib = ilb.read(path)
    by_id = {im.id: im for im in lib.images}
    problems = []
    for ch in RU_ALPHABET:
        b = RU_MAP[ch]
        img = by_id.get(b)
        if img is None or not img.parts:
            problems.append("missing glyph %r at id 0x%02X" % (ch, b))
            continue
        got = raw_indices(lib, img.parts[0])
        w, want = grids[ch]
        if len(got) != len(want) or any(got[y] != want[y] for y in range(len(want))):
            problems.append("glyph %r at id 0x%02X decodes wrong" % (ch, b))
    claimed = set(RU_MAP.values())
    for iid, px in before_pixels.items():
        if iid in claimed:
            continue
        img = by_id.get(iid)
        cur = raw_indices(lib, img.parts[0]) if img and img.parts else None
        if cur != px:
            problems.append("untouched image #%d changed" % iid)
    return problems


# ---------------------------------------------------------------------------
# Age15 display fonts (WhIn / WhGr / BlBr) - 18px calligraphic, 16-bit.
# One glyph set is COMPOSED from Age15WhIn's own antialiased Latin art
# (copies, mirrors, and piece surgery), then:
#   WhIn gets it directly, BlBr gets it recolored via a mapping learned from
#   the retail WhIn/BlBr glyph pairs, and WhGr gets two layers per glyph -
#   the art plus retail's shadow rule: colors inverted (254-v), down 1 row.
# ---------------------------------------------------------------------------
CELL15 = 18


def _quant(p):
    r, g, b = ilb._c565(ilb.to_rgb565(p[0], p[1], p[2]))
    return (r, g, b, 255)


def build_age15_glyphs(lib):
    """{char: (w, CELL15 rows of RGBA)} - composed from lib's own glyphs."""
    cache = {}

    def G(ch):
        iid = ord(ch) if len(ch) == 1 else int(ch, 16)
        if iid not in cache:
            r = rec_of(lib, iid)
            if r is None:
                raise KeyError("Age15 source lacks glyph %r" % ch)
            w, h, rows = ilb.decode_record(lib, r)
            while len(rows) < CELL15:
                rows.append([(0, 0, 0, 0)] * w)
            cache[iid] = (w, [tuple(x) for x in rows])
        w, rows = cache[iid]
        return w, [list(x) for x in rows]

    def blank(w):
        return w, [[(0, 0, 0, 0)] * w for _ in range(CELL15)]

    def mirror(g):
        return g[0], [list(reversed(r)) for r in g[1]]

    def vflip(g):
        return g[0], [list(r) for r in reversed(g[1])]

    def crop(g, x0, y0, x1, y1):
        w, rows = g
        nw = x1 - x0
        out = [[(0, 0, 0, 0)] * nw for _ in range(CELL15)]
        for y in range(max(0, y0), min(CELL15, y1)):
            for x in range(x0, min(x1, w)):
                out[y][x - x0] = rows[y][x]
        return nw, out

    def erase(g, x0, y0, x1, y1):
        w, rows = g
        for y in range(max(0, y0), min(CELL15, y1)):
            for x in range(max(0, x0), min(x1, w)):
                rows[y][x] = (0, 0, 0, 0)
        return w, rows

    def paste(dst, src, dx, dy=0, under=False):
        dw, drows = dst
        sw, srows = src
        for y in range(CELL15):
            ty = y + dy
            if not (0 <= ty < CELL15):
                continue
            for x in range(sw):
                tx = x + dx
                if not (0 <= tx < dw):
                    continue
                p = srows[y][x]
                if p[3] and (not under or drows[ty][tx][3] == 0):
                    drows[ty][tx] = p
        return dw, drows

    def shift(g, dx, dy):
        c = blank(g[0] + max(0, dx))
        return paste(c, g, dx, dy)

    def trim(g, pad=0):
        w, rows = g
        used = [x for x in range(w) if any(rows[y][x][3] for y in range(CELL15))]
        if not used:
            return g
        return crop((w, rows), used[0], 0, used[-1] + 1 + pad, CELL15)

    def hstack(*gs, gap=0):
        total = sum(g[0] for g in gs) + gap * (len(gs) - 1)
        c = blank(total)
        x = 0
        for g in gs:
            paste(c, g, x)
            x += g[0] + gap
        return c

    def u_stem(side):
        u = G("u")
        return trim(crop(u, 0, 0, 4, CELL15) if side == "L"
                    else crop(u, u[0] - 4, 0, u[0], CELL15))

    def breve():
        w, rows = G("Û")                 # Û - flip its circumflex
        piece = crop((w, rows), 0, 0, w, 4)
        pw, prow = trim(piece)
        band = list(reversed(prow[0:4]))
        out = blank(pw)[1]
        for i in range(4):
            out[i] = band[i]
        return pw, out

    def e_bar(width_from=1):
        e = G("e")
        return trim(crop(e, width_from, 7, e[0] - 1, 9))

    def q_tail():
        q = G("Q")
        return trim(crop(q, q[0] - 5, 10, q[0], CELL15))

    def lo_tail():
        q = G("q")
        return trim(crop(q, q[0] - 4, 12, q[0], CELL15))

    def i_core():
        i = G("i")
        return trim(crop(i, 0, 4, i[0], CELL15))

    def cap_soft():
        b = G("B")
        return erase(b, 4, 1, b[0], 6)

    def lo_soft():
        b = G("b")
        return erase(b, 0, 0, 4, 4)

    def cap_lambda():
        return shift(vflip(G("V")), 0, -3)

    R = {}
    for ch, src in [("А", "A"), ("В", "B"), ("Е", "E"), ("З", "3"),
                    ("К", "K"), ("М", "M"), ("Н", "H"), ("О", "O"),
                    ("Р", "P"), ("С", "C"), ("Т", "T"), ("Х", "X"),
                    ("а", "a"), ("е", "e"), ("о", "o"), ("р", "p"),
                    ("с", "c"), ("у", "y"), ("х", "x"),
                    ("б", "6"), ("п", "n"), ("д", "g")]:
        R[ch] = (lambda s: (lambda: G(s)))(src)
    R["Ё"] = lambda: G("Ë")
    R["ё"] = lambda: G("ë")
    R["И"] = lambda: trim(mirror(G("N")), 1)
    R["Я"] = lambda: trim(mirror(G("R")), 1)
    R["з"] = lambda: trim(mirror(G("s")), 1)
    R["и"] = lambda: trim(mirror(G("u")), 1)
    R["л"] = lambda: vflip(G("v"))
    R["П"] = lambda: shift(vflip(G("U")), 0, -3)
    R["Л"] = cap_lambda
    R["Ь"] = cap_soft
    R["ь"] = lo_soft

    def cap_gamma():
        return trim(erase(G("T"), 0, 0, 3, CELL15), 1)
    R["Г"] = cap_gamma

    def cap_de():
        lam = cap_lambda()
        w = lam[0]
        c = blank(w + 4)
        paste(c, lam, 2)
        z = G("z")
        bar = trim(crop(z, 1, 11, z[0] - 1, 13))
        x = 0
        while x < w + 4:
            paste(c, bar, x, 1, under=True)
            x += bar[0]
        c = (c[0], [row[:w + 4] for row in c[1]])
        l = G("l")
        foot = trim(crop(l, 0, 10, 5, 13))
        paste(c, foot, 0, 3, under=True)
        paste(c, foot, w + 4 - foot[0], 3, under=True)
        return c
    R["Д"] = cap_de

    def cap_zhe():
        x = G("X")
        c = blank(x[0])
        paste(c, x, 0)
        i = trim(G("I"))
        paste(c, i, (x[0] - i[0]) // 2, 0)
        return c
    R["Ж"] = cap_zhe

    def cap_i_breve():
        i = trim(mirror(G("N")), 1)
        b = breve()
        c = blank(i[0])
        paste(c, i, 0)
        paste(c, b, (i[0] - b[0]) // 2, -1, under=True)
        return c
    R["Й"] = cap_i_breve

    def cap_u():
        v = G("V")
        y = G("y")
        tail = trim(crop(y, 0, 10, y[0], CELL15))
        c = blank(v[0])
        paste(c, v, 0)
        paste(c, tail, v[0] // 2 - 2, 3, under=True)
        return c
    R["У"] = cap_u

    def cap_ef():
        o = G("O")
        l = trim(G("l"))
        c = blank(o[0])
        paste(c, o, 0)
        cx = (o[0] - l[0]) // 2
        paste(c, l, cx, 2, under=True)
        top = trim(crop(G("l"), 0, 1, 5, 5))
        paste(c, top, cx, -1, under=True)
        return c
    R["Ф"] = cap_ef

    def cap_tse():
        u = G("U")
        c = blank(u[0] + 2)
        paste(c, u, 0)
        paste(c, q_tail(), u[0] - 3, 2, under=True)
        return c
    R["Ц"] = cap_tse

    def cap_che():
        return trim(erase(G("H"), 0, 9, 4, CELL15), 1)
    R["Ч"] = cap_che

    def cap_sha():
        u = G("U")
        c = blank(u[0] + 4)
        paste(c, u, 0)
        i = trim(G("I"))
        paste(c, i, (u[0] - i[0]) // 2, 0, under=True)
        return c
    R["Ш"] = cap_sha

    def cap_shcha():
        s = cap_sha()
        paste(s, q_tail(), s[0] - 6, 2, under=True)
        return s
    R["Щ"] = cap_shcha

    def cap_hard():
        s = cap_soft()
        t = G("T")
        bar = trim(crop(t, 1, 1, 6, 4))
        c = blank(s[0] + 2)
        paste(c, s, 2)
        paste(c, bar, 0, 0)
        return c
    R["Ъ"] = cap_hard

    def cap_yeru():
        s = cap_soft()
        h = G("H")
        stem = trim(crop(h, 6, 0, h[0], CELL15))
        return hstack(s, stem, gap=1)
    R["Ы"] = cap_yeru

    def cap_e():
        c0 = trim(mirror(G("C")), 1)
        h = G("H")
        bar = trim(crop(h, 3, 7, 8, 9))
        paste(c0, bar, 2, 0)
        return c0
    R["Э"] = cap_e

    def cap_yu():
        h = G("H")
        stem = trim(crop(h, 0, 0, 5, CELL15))
        bar = trim(crop(h, 3, 7, 7, 9))
        o = G("O")
        c = blank(stem[0] + 1 + o[0])
        paste(c, stem, 0)
        paste(c, o, stem[0] + 1)
        paste(c, bar, stem[0] - 1, 0)
        return c
    R["Ю"] = cap_yu

    def cap_be():
        s = cap_soft()
        t = G("T")
        bar = trim(crop(t, 1, 1, t[0] - 1, 4))
        c = blank(max(s[0], bar[0] + 1))
        paste(c, s, 0)
        paste(c, bar, 1, 0)
        return c
    R["Б"] = cap_be

    def lo_ibreve():
        i = trim(mirror(G("u")), 1)
        b = breve()
        c = blank(i[0])
        paste(c, i, 0)
        paste(c, b, (i[0] - b[0]) // 2, 1, under=True)
        return c
    R["й"] = lo_ibreve

    def lo_zhe():
        x = G("x")
        c = blank(x[0])
        paste(c, x, 0)
        paste(c, i_core(), (x[0] - i_core()[0]) // 2, 0)   # stem OVER the x
        return c
    R["ж"] = lo_zhe

    def lo_ka():
        x = G("x")
        right = trim(crop(x, x[0] // 2, 0, x[0], CELL15))
        return hstack(u_stem("L"), right)
    R["к"] = lo_ka

    def lo_yeru():
        return hstack(trim(lo_soft(), 0), u_stem("R"), gap=1)
    R["ы"] = lo_yeru

    def lo_hard():
        s = trim(lo_soft())
        z = G("z")
        bar = trim(crop(z, 0, 4, 4, 7))
        c = blank(s[0] + 2)
        paste(c, s, 2)
        paste(c, bar, 0, 0)
        return c
    R["ъ"] = lo_hard

    def lo_ve():
        s = trim(lo_soft())
        c = blank(s[0])
        paste(c, s, 0)
        paste(c, e_bar(), 1, 1, under=True)
        return c
    R["в"] = lo_ve

    def lo_e():
        c0 = trim(mirror(G("c")), 1)
        e = G("e")
        bar = trim(crop(e, 1, 8, e[0] - 1, 10))
        paste(c0, bar, 1, 0)
        return c0
    R["э"] = lo_e

    def lo_yu():
        st = u_stem("L")
        o = G("o")
        e = G("e")
        bar = trim(crop(e, 1, 8, 5, 10))
        c = blank(st[0] + 1 + o[0])
        paste(c, st, 0)
        paste(c, o, st[0] + 1)
        paste(c, bar, st[0] - 1, 0, under=True)
        return c
    R["ю"] = lo_yu

    def lo_ya():
        p = trim(mirror(G("p")), 1)
        p = erase(p, 0, 13, p[0], CELL15)
        x = G("x")
        leg = trim(crop(x, 0, 10, 5, 14))
        c = blank(p[0] + 1)
        paste(c, p, 1)
        paste(c, leg, 0, -1)
        return c
    R["я"] = lo_ya

    def lo_ge():
        st = u_stem("L")
        z = G("z")
        bar = trim(crop(z, 0, 4, z[0], 7))
        c = blank(max(st[0] + 1, bar[0]))
        paste(c, st, 0)
        paste(c, bar, 0, 0)
        return c
    R["г"] = lo_ge

    def lo_te():
        z = G("z")
        bar = trim(crop(z, 0, 4, z[0], 7))
        c = blank(bar[0])
        paste(c, bar, 0, 0)
        paste(c, i_core(), (bar[0] - i_core()[0]) // 2, 0, under=True)
        return c
    R["т"] = lo_te

    def lo_em():
        v = G("v")
        stl, str_ = u_stem("L"), u_stem("R")
        c = blank(stl[0] + v[0] + str_[0] - 2)
        paste(c, stl, 0)
        paste(c, v, stl[0] - 1, 0, under=True)
        paste(c, str_, stl[0] + v[0] - 2, 0, under=True)
        return c
    R["м"] = lo_em

    def lo_en():
        stl, str_ = u_stem("L"), u_stem("R")
        c = blank(stl[0] + 3 + str_[0])
        paste(c, stl, 0)
        paste(c, str_, stl[0] + 3)
        paste(c, e_bar(), 1, 0, under=True)
        return c
    R["н"] = lo_en

    def lo_tse():
        u = G("u")
        c = blank(u[0] + 2)
        paste(c, u, 0)
        paste(c, lo_tail(), u[0] - 2, 1, under=True)
        return c
    R["ц"] = lo_tse

    def lo_sha():
        u = G("u")
        c = blank(u[0] + 2)
        paste(c, u, 0)
        paste(c, i_core(), (u[0] - i_core()[0]) // 2, 0, under=True)
        return c
    R["ш"] = lo_sha

    def lo_shcha():
        s = lo_sha()
        paste(s, lo_tail(), s[0] - 4, 1, under=True)
        return s
    R["щ"] = lo_shcha

    def lo_che():
        stl = u_stem("L")
        str_ = u_stem("R")
        stl = erase(stl, 0, 10, stl[0], CELL15)
        c = blank(stl[0] + 3 + str_[0])
        paste(c, stl, 0)
        paste(c, str_, stl[0] + 3)
        paste(c, e_bar(), 1, 2, under=True)
        return c
    R["ч"] = lo_che

    def lo_ef():
        o = G("o")
        l = trim(G("l"))
        c = blank(o[0])
        paste(c, o, 0)
        cx = (o[0] - l[0]) // 2
        paste(c, l, cx, 0, under=True)
        tail = trim(crop(G("l"), 0, 9, 5, 13))
        paste(c, tail, cx, 3, under=True)
        return c
    R["ф"] = lo_ef

    out = {}
    for ch in RU_ALPHABET:
        w, rows = R[ch]()
        out[ch] = (w, [[_quant(p) if p[3] else (0, 0, 0, 0) for p in row]
                       for row in rows])
    return out


def learn_blbr_map(whin, blbr):
    """WhIn color -> BlBr color, majority vote over the retail glyph pairs."""
    votes = {}
    for im in whin.images:
        r1, r2 = rec_of(whin, im.id), rec_of(blbr, im.id)
        if r1 is None or r2 is None:
            continue
        w1, h1, a = ilb.decode_record(whin, r1)
        w2, h2, b = ilb.decode_record(blbr, r2)
        if (w1, h1) != (w2, h2):
            continue
        for y in range(h1):
            for x in range(w1):
                if a[y][x][3] and b[y][x][3]:
                    votes.setdefault(a[y][x][:3], {}).setdefault(b[y][x][:3], 0)
                    votes[a[y][x][:3]][b[y][x][:3]] += 1
    return {k: max(v.items(), key=lambda kv: kv[1])[0] for k, v in votes.items()}


def _recolor(grid, cmap):
    def f(p):
        if not p[3]:
            return (0, 0, 0, 0)
        c = cmap.get(p[:3])
        if c is None:
            c = tuple(max(0, 254 - v) for v in p[:3])
            c = _quant((c[0], c[1], c[2], 255))[:3]
        return (c[0], c[1], c[2], 255)
    return [[f(p) for p in row] for row in grid]


def _shadow_layer(grid):
    """Retail WhGr rule: colors inverted (254-v), shifted down one row."""
    inv = [[(0, 0, 0, 0)] * len(grid[0]) for _ in range(CELL15)]
    for y in range(CELL15 - 1):
        for x, p in enumerate(grid[y]):
            if p[3]:
                c = tuple(max(0, 254 - v) for v in p[:3])
                inv[y + 1][x] = _quant((c[0], c[1], c[2], 255))
    return inv


def encode16(rec, w, grid, key):
    rec["w"], rec["h"] = w, CELL15
    rec["xs"] = rec["ys"] = 0
    rec["totw"], rec["toth"] = w, CELL15
    rec["transp"] = key
    rec["pixFmt"] = ilb.PIXFMT_565
    top, left, bottom, right = CELL15, w, -1, -1
    for y, row in enumerate(grid):
        for x in range(w):
            if row[x][3]:
                top, bottom = min(top, y), max(bottom, y)
                left, right = min(left, x), max(right, x)
    if bottom < 0:
        raise ValueError("empty glyph")
    cw, chh = right - left + 1, bottom - top + 1
    rec["cx"], rec["cy"], rec["cw"], rec["ch"] = left, top, cw, chh
    rows = []
    for y in range(top, top + chh):
        line = []
        for x in range(left, left + cw):
            p = grid[y][x]
            if not p[3]:
                line.append(key)
            else:
                v = ilb.to_rgb565(p[0], p[1], p[2])
                line.append(v ^ 1 if v == key else v)
        rows.append(line)
    rec["newdata"] = ilb.encode_raw16(rows)
    rec["size"] = len(rec["newdata"])


def patch_age15(libs15, glyphs):
    cmap = learn_blbr_map(libs15["Age15WhIn"], libs15["Age15BlBr"])
    stats = {}
    for name in ("Age15WhIn", "Age15BlBr", "Age15WhGr"):
        lib = libs15[name]
        by_id = {im.id: im for im in lib.images}
        tmpl_img = by_id[ord("A")]
        replaced = added = 0
        for ch in RU_ALPHABET:
            w, grid = glyphs[ch]
            b = RU_MAP[ch]
            if name == "Age15BlBr":
                use = _recolor(grid, cmap)
            else:
                use = grid
            if name == "Age15WhGr":
                parts_data = [(_shadow_layer(use), 0xFFFF), (use, 0x0000)]
            else:
                parts_data = [(use, 0x0000)]
            if b in by_id and by_id[b].parts:
                img = by_id[b]
                replaced += 1
                while len(img.parts) < len(parts_data):
                    img.parts.append(ilb.Record(tmpl_img.parts[len(img.parts)]))
            else:
                img = ilb.Image(b, [ilb.Record(t) for t in tmpl_img.parts],
                                composite=tmpl_img.composite)
                lib.images.append(img)
                by_id[b] = img
                added += 1
            for rec, (g, key) in zip(img.parts, parts_data):
                rec["newdata"] = None
                encode16(rec, w, g, key)
        lib.images.sort(key=lambda im: im.id)
        expected = {}
        by_id2 = {im.id: im for im in lib.images}
        for ch in RU_ALPHABET:
            img = by_id2[RU_MAP[ch]]
            expected[RU_MAP[ch]] = [ilb.decode_record(lib, r) for r in img.parts]
        stats[name] = (replaced, added, len(lib.images), expected)
    return stats


def snapshot16(lib):
    return {im.id: [ilb.decode_record(lib, r) for r in im.parts]
            for im in lib.images if im.parts}


def verify_age15(path, before, expected):
    lib = ilb.read(path)
    by_id = {im.id: im for im in lib.images}
    problems = []
    claimed = set(RU_MAP.values())
    for ch in RU_ALPHABET:
        b = RU_MAP[ch]
        img = by_id.get(b)
        if img is None or not img.parts:
            problems.append("missing glyph %r at id 0x%02X" % (ch, b))
            continue
        cur = [ilb.decode_record(lib, r) for r in img.parts]
        if cur != expected[b]:
            problems.append("glyph %r at id 0x%02X decodes wrong" % (ch, b))
    for iid, parts in before.items():
        if iid in claimed:
            continue
        img = by_id.get(iid)
        cur = [ilb.decode_record(lib, r) for r in img.parts] if img else None
        if cur != parts:
            problems.append("untouched image #%d changed" % iid)
    return problems


def run(apply_it):
    libs = {}
    for name, *_ in CONFIGS:
        libs[name] = ilb.read(os.path.join(FONTS, name + ".ILB"))
    # snapshot original pixels for the verify pass
    originals = {}
    for name in libs:
        originals[name] = {im.id: raw_indices(libs[name], im.parts[0])
                           for im in libs[name].images if im.parts}

    libs15 = {n: ilb.read(os.path.join(FONTS, n + ".ILB"))
              for n in ("Age15WhIn", "Age15BlBr", "Age15WhGr")}
    originals15 = {n: snapshot16(libs15[n]) for n in libs15}

    print("Cyrillic byte mapping: %s = 0x%02X .. %s = 0x%02X (66 letters)"
          % (RU_ALPHABET[0], RU_MAP[RU_ALPHABET[0]],
             RU_ALPHABET[-1], RU_MAP[RU_ALPHABET[-1]]))
    results = {}
    for name, gset, src, gi, si, tr, pal, cell in CONFIGS:
        replaced, added, grids = patch_font(name, gset, src, gi, si, tr, pal,
                                            cell, libs)
        results[name] = grids
        print("  %-9s %2d frames replaced, %2d added -> %d images"
              % (name, replaced, added, len(libs[name].images)))

    # composition only reads Latin donor glyphs, which stay pristine forever,
    # so re-running against an already-patched WhIn is safe
    glyphs15 = build_age15_glyphs(libs15["Age15WhIn"])
    stats15 = patch_age15(libs15, glyphs15)
    for name, (replaced, added, total, _exp) in stats15.items():
        print("  %-9s %2d frames replaced, %2d added -> %d images (16-bit)"
              % (name, replaced, added, total))

    if not apply_it:
        print("\nDry run - nothing written. Use --apply to patch.")
        return

    os.makedirs(BACKUP, exist_ok=True)
    for name in list(libs) + list(libs15):
        src = os.path.join(FONTS, name + ".ILB")
        dst = os.path.join(BACKUP, name + ".ILB")
        if not os.path.isfile(dst):
            shutil.copy2(src, dst)
    print("\nBacked up originals to %s" % BACKUP)

    ok = True
    for name, gset, *_ in CONFIGS:
        path = os.path.join(FONTS, name + ".ILB")
        ilb.save(libs[name], path)
        problems = verify_font(path, gset, results[name], originals[name])
        if problems:
            ok = False
            print("  %-9s VERIFY FAILED:" % name)
            for p in problems[:8]:
                print("      " + p)
        else:
            print("  %-9s written and verified (%d bytes)"
                  % (name, os.path.getsize(path)))
    for name in ("Age15WhIn", "Age15BlBr", "Age15WhGr"):
        path = os.path.join(FONTS, name + ".ILB")
        ilb.save(libs15[name], path)
        problems = verify_age15(path, originals15[name], stats15[name][3])
        if problems:
            ok = False
            print("  %-9s VERIFY FAILED:" % name)
            for p in problems[:8]:
                print("      " + p)
        else:
            print("  %-9s written and verified (%d bytes)"
                  % (name, os.path.getsize(path)))
    if not ok:
        print("\nVERIFICATION FAILED - restore with --revert and investigate.")
        sys.exit(1)
    print("\nDone. Twelve fonts now carry the 66 Cyrillic glyphs "
          "(Age14G still pending).")


def revert():
    if not os.path.isdir(BACKUP):
        print("No backup at %s - nothing to revert." % BACKUP)
        sys.exit(1)
    n = 0
    for fn in os.listdir(BACKUP):
        shutil.copy2(os.path.join(BACKUP, fn), os.path.join(FONTS, fn))
        n += 1
        print("  restored %s" % fn)
    print("Reverted %d file(s) from %s" % (n, BACKUP))


if __name__ == "__main__":
    if "--revert" in sys.argv:
        revert()
    else:
        run("--apply" in sys.argv)
