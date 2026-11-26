"""
aowxlib.cyrillic - adding Russian to AoW1 without disturbing the Latin accents.

The game does not render text with GDI. Every widget draws from bitmap glyph
strips held in image libraries under Int\\Fonts\\, and a text byte is used
directly as the glyph's image id (verified by rendering "Age of Wonders X" out
of Age15WhGr.ILB with id = ord(ch)).

That means the byte -> glyph mapping is ours to define. A census of every high
byte appearing in real text - all eight dictionaries plus text-like runs inside
Release\\*.pfs - found:

    57 high bytes (0x80-0xFF) are used by game text
    71 high bytes are never used by anything

Russian needs 66 glyphs (А-Я, а-я, Ё, ё). 66 fits inside those 71 with five to
spare, so Cyrillic can be added WITHOUT touching a single accented character
that German, French, Italian or Spanish rely on.

So we do not use cp1251. We define our own byte assignment onto free slots and
a matching codec. Text stored in the dictionary uses these bytes; the fonts get
Cyrillic glyphs painted at the same ids.
"""
from __future__ import annotations
import codecs

# Bytes that real game text uses - do not touch these, they are live glyphs.
USED_BYTES = {
    0x85, 0x92, 0x9C, 0xA0, 0xA1, 0xA2, 0xA7, 0xA8, 0xAA, 0xB4, 0xB5, 0xB6,
    0xB7, 0xBF, 0xC0, 0xC1, 0xC4, 0xC8, 0xC9, 0xCA, 0xCB, 0xCD, 0xD0, 0xD2,
    0xD3, 0xD4, 0xD6, 0xDA, 0xDC, 0xDE, 0xDF, 0xE0, 0xE1, 0xE2, 0xE4, 0xE6,
    0xE7, 0xE8, 0xE9, 0xEA, 0xEB, 0xEC, 0xED, 0xEE, 0xEF, 0xF0, 0xF1, 0xF2,
    0xF3, 0xF4, 0xF6, 0xF8, 0xF9, 0xFA, 0xFB, 0xFC, 0xFF,
}

# Everything in 0x80..0xFF that no game text uses - free for us to claim.
FREE_BYTES = [b for b in range(0x80, 0x100) if b not in USED_BYTES]

RU_UPPER = "АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ"
RU_LOWER = "абвгдеёжзийклмнопрстуфхцчшщъыьэюя"
RU_ALPHABET = RU_UPPER + RU_LOWER            # 66 characters

if len(RU_ALPHABET) > len(FREE_BYTES):
    raise RuntimeError("Cyrillic does not fit: need %d slots, %d free"
                       % (len(RU_ALPHABET), len(FREE_BYTES)))

# char -> byte, assigned in order over the free slots so the block stays tidy
RU_MAP = {ch: FREE_BYTES[i] for i, ch in enumerate(RU_ALPHABET)}
RU_REVERSE = {b: ch for ch, b in RU_MAP.items()}

AOWX_RU_CODEC = "aowx-ru"
AOWX_RU_CODEPAGE = 1251        # what we declare in the .mld language record


def check_clashes():
    """Any glyph slot we claimed that game text actually uses. Must be empty."""
    return sorted(b for b in RU_MAP.values() if b in USED_BYTES)


def encode(s, codec="cp1252"):
    """Text -> bytes for storage in a dictionary."""
    if not s:
        return b""
    if codec == AOWX_RU_CODEC:
        out = bytearray()
        for ch in s:
            if ch in RU_MAP:
                out.append(RU_MAP[ch])
            else:
                try:
                    out += ch.encode("cp1252")
                except UnicodeEncodeError:
                    out += b"?"
        return bytes(out)
    # normalise typography the bitmap fonts cannot draw
    s = s.replace(" ", " ").replace(" ", " ")
    s = s.replace("’", "'").replace("‘", "'")
    s = s.replace("“", '"').replace("”", '"')
    s = s.replace("–", "-").replace("—", "-").replace("…", "...")
    try:
        return s.encode(codec)
    except (UnicodeEncodeError, LookupError):
        return s.encode("cp1252", "replace")


def decode(b, codec="cp1252"):
    """Bytes from a dictionary -> text."""
    if not b:
        return ""
    if isinstance(b, str):
        return b
    if codec == AOWX_RU_CODEC:
        return "".join(RU_REVERSE.get(x, bytes([x]).decode("cp1252", "replace")) for x in b)
    try:
        return bytes(b).decode(codec)
    except (UnicodeDecodeError, LookupError):
        return bytes(b).decode("cp1252", "replace")


def codec_name_for_cp(cp):
    if cp == AOWX_RU_CODEPAGE:
        return AOWX_RU_CODEC
    if not cp or cp == 1252:
        return "cp1252"
    return "cp%d" % cp


def codec_name(language):
    return codec_name_for_cp(getattr(language, "CodePage", 1252))


# ---------------------------------------------------------------------------
# canonical language metadata, used to repair what MLDEdit mangles
# ---------------------------------------------------------------------------
CANON = {
    "english":  dict(Primary=0x09, ISOLanguage=b"en", DefaultSub=1, ISODefaultCountry=b"US"),
    "german":   dict(Primary=0x07, ISOLanguage=b"de", DefaultSub=1, ISODefaultCountry=b"DE"),
    "french":   dict(Primary=0x0C, ISOLanguage=b"fr", DefaultSub=1, ISODefaultCountry=b"FR"),
    "italian":  dict(Primary=0x10, ISOLanguage=b"it", DefaultSub=1, ISODefaultCountry=b"IT"),
    "spanish":  dict(Primary=0x0A, ISOLanguage=b"es", DefaultSub=1, ISODefaultCountry=b"ES"),
    "russian":  dict(Primary=0x19, ISOLanguage=b"ru", DefaultSub=1, ISODefaultCountry=b"RU"),
}
CANON_BY_NAME = CANON
CANON_BY_ISO = {v["ISOLanguage"].decode(): v for v in CANON.values()}

LANGUAGE_PRESETS = {
    "russian": dict(
        EnglishName="Russian", NativeName="Русский", ISOLanguage="ru",
        ISODefaultCountry="RU", Primary=0x19, DefaultSub=1, CodePage=AOWX_RU_CODEPAGE,
        note=("Uses the AoWx Russian glyph mapping: Cyrillic is stored in %d byte slots "
              "that no existing text uses, so German, French, Italian and Spanish accents "
              "are untouched. The bitmap fonts in Int\\Fonts still need those glyphs "
              "painted before it renders in-game." % len(RU_MAP))),
    "polish": dict(
        EnglishName="Polish", NativeName="Polski", ISOLanguage="pl",
        ISODefaultCountry="PL", Primary=0x15, DefaultSub=1, CodePage=1250,
        note="Code page 1250 - several glyphs would need adding to the fonts."),
    "dutch": dict(
        EnglishName="Dutch", NativeName="Nederlands", ISOLanguage="nl",
        ISODefaultCountry="NL", Primary=0x13, DefaultSub=1, CodePage=1252,
        note="Latin-1; every glyph it needs already exists in the fonts."),
    "portuguese": dict(
        EnglishName="Portuguese", NativeName="Portugues", ISOLanguage="pt",
        ISODefaultCountry="PT", Primary=0x16, DefaultSub=1, CodePage=1252,
        note="Latin-1; every glyph it needs already exists in the fonts."),
    "custom": dict(
        EnglishName="Custom", NativeName="Custom", ISOLanguage="xx",
        ISODefaultCountry="XX", Primary=0, DefaultSub=1, CodePage=1252, note=""),
}
