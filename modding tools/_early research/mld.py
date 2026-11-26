"""
mld.py -- codec for Age of Wonders 1 ".mld" (Multi-Language Dictionary) files.

Format reverse-engineered from MLDEdit.exe (Delphi 3, classes TMLDFile /
TLanguageData / TTranslationData / TLocale).  All field names below are the
ORIGINAL names taken from MLDEdit's own debug-trace format strings.

All integers little-endian.  All "wstr" = uint16 byte-count followed by that
many raw single-byte characters (NO terminator).  Text codepage is per-language
(TLanguageData.CodePage, 1252 for every stock language).

FILE HEADER  (42 = 0x2A bytes, always immediately followed by the language table)
  off  size  field
  0x00  3   Tag                 'MLD'   (stored as the body of a ShortString[3])
  0x03  1   Version             3
  0x04  1   ByteOrder           1
  0x05  1   CharacterSet        1
  0x06  1   Context             1   (1 => records carry both ClassName and
                                     ComponentName; 2 => ComponentName only;
                                     3 => ClassName only; see reader logic)
  0x07  5   <reserved, read and discarded by MLDEdit>   all 00
  0x0C  2   LanguageCount       6
  0x0E  4   LanguageOffSet      0x2A
  0x12  2   TranslationsCount   number of string records
  0x14  4   TranslationsOffSet  0x118 in every stock file
  0x18  2   LocaleCount         0 in every stock file
  0x1A  4   LocaleOffSet        0
  0x1E  2   InfoSize            bytes
  0x20  4   InfoOffSet
  0x24  6   <reserved, read and discarded>  all 00

LANGUAGE ENTRY (TLanguageData) -- LanguageCount of them, back to back
  +0x00 2   DataSize            total byte size of THIS entry, incl. these 2
  +0x02 2   Primary             Windows PRIMARYLANGID (0x09 en, 0x07 de,
                                0x0C fr, 0x10 it, 0x0A es, 0 for 'Native')
  +0x04 2   ISOLanguage         2 raw chars, 'en'/'de'/... ('  ' for Native)
  +0x06 2   DefaultSub          Windows SUBLANGID (1 for all stock langs)
  +0x08 2   ISODefaultCountry   2 raw chars, 'US'/'DE'/... ('  ' for Native)
  +0x0A wstr AllSubs            empty in every stock file
  +0x?? wstr ISOAllCountries    empty in every stock file
  +0x?? 2   CharacterSet        0 in every stock file
  +0x?? 2   CodePage            1252 (0 for 'Native')
  +0x?? 1   Options             0 for real languages, 2 for 'Native'
  +0x?? wstr EnglishName        'English', 'German', ...
  +0x?? wstr NativeName         'English', 'Deutsch', 'francais', ...
  +0x?? wstr FontName           empty in every stock file
  +0x?? 1   FontSize            0 in every stock file

TRANSLATION RECORD (TTranslationData) -- TranslationsCount of them, back to back
  wstr  Original      the source ("Native") string; also the msgid
  wstr  ClassName     present when Context in {1,3} and Version > 2
  wstr  ComponentName present when Context in {1,2} and Version > 2
  wstr x (LanguageCount-1)   the translations, in language-table order
                             starting at language index 1 (index 0 = 'Native',
                             whose text is Original)

INFO BLOCK (InfoSize bytes at InfoOffSet, immediately after the records)
  wstr  Name          'Campaign Texts' / 'Custom Maps' / ''
  wstr  <empty>
  wstr  <empty>       (MLDEdit does not read this block at all)
  1     Day
  1     Month
  2     Year
  1     Hour
  1     Minute
  1     Second
"""
import struct, io, datetime

MAGIC = b'MLD'


class BinReader:
    def __init__(self, d, p=0): self.d = d; self.p = p
    def bytes(self, n):
        v = self.d[self.p:self.p + n]
        if len(v) != n: raise EOFError('short read at %#x' % self.p)
        self.p += n; return v
    def u8(self): return self.bytes(1)[0]
    def u16(self): return struct.unpack('<H', self.bytes(2))[0]
    def u32(self): return struct.unpack('<I', self.bytes(4))[0]
    def wstr(self): return self.bytes(self.u16())


class BinWriter:
    def __init__(self): self.b = bytearray()
    def bytes(self, v): self.b += v
    def u8(self, v): self.b += bytes((v,))
    def u16(self, v): self.b += struct.pack('<H', v)
    def u32(self, v): self.b += struct.pack('<I', v)
    def wstr(self, v): self.u16(len(v)); self.b += v


class Language:
    """One TLanguageData entry.  Text fields are kept as raw bytes."""
    FIELDS = ('Primary ISOLanguage DefaultSub ISODefaultCountry AllSubs '
              'ISOAllCountries CharacterSet CodePage Options EnglishName '
              'NativeName FontName FontSize').split()

    def __init__(self, **kw):
        for f in self.FIELDS: setattr(self, f, kw.get(f))

    @classmethod
    def read(cls, r):
        start = r.p
        size = r.u16()
        o = cls()
        o.Primary            = r.u16()
        o.ISOLanguage        = r.bytes(2)
        o.DefaultSub         = r.u16()
        o.ISODefaultCountry  = r.bytes(2)
        o.AllSubs            = r.wstr()
        o.ISOAllCountries    = r.wstr()
        o.CharacterSet       = r.u16()
        o.CodePage           = r.u16()
        o.Options            = r.u8()
        o.EnglishName        = r.wstr()
        o.NativeName         = r.wstr()
        o.FontName           = r.wstr()
        o.FontSize           = r.u8()
        if r.p - start != size:
            raise ValueError('language entry size mismatch at %#x: declared %d, consumed %d'
                             % (start, size, r.p - start))
        return o

    def body(self):
        w = BinWriter()
        w.u16(self.Primary); w.bytes(self.ISOLanguage)
        w.u16(self.DefaultSub); w.bytes(self.ISODefaultCountry)
        w.wstr(self.AllSubs); w.wstr(self.ISOAllCountries)
        w.u16(self.CharacterSet); w.u16(self.CodePage); w.u8(self.Options)
        w.wstr(self.EnglishName); w.wstr(self.NativeName); w.wstr(self.FontName)
        w.u8(self.FontSize)
        return bytes(w.b)

    def write(self, w):
        b = self.body()
        w.u16(len(b) + 2); w.bytes(b)

    @property
    def is_native(self): return bool(self.Options & 2)

    def codec(self):
        cp = self.CodePage or 1252
        return 'cp%d' % cp

    def __repr__(self):
        return "<Language %s_%s '%s'/'%s' cp=%d primary=%#x sub=%d opt=%d>" % (
            self.ISOLanguage.decode('latin-1'), self.ISODefaultCountry.decode('latin-1'),
            self.EnglishName.decode('latin-1', 'replace'),
            self.NativeName.decode('latin-1', 'replace'),
            self.CodePage, self.Primary, self.DefaultSub, self.Options)


class Record:
    """One TTranslationData record.  `texts[i]` is the string for language i;
    texts[0] is the 'Original' (Native) column."""
    __slots__ = ('Original', 'ClassName', 'ComponentName', 'translations')

    def __init__(self, Original=b'', ClassName=b'', ComponentName=b'', translations=None):
        self.Original = Original; self.ClassName = ClassName
        self.ComponentName = ComponentName; self.translations = translations or []

    @property
    def key(self):
        return (self.Original, self.ClassName, self.ComponentName)

    def texts(self):
        return [self.Original] + list(self.translations)


class MLDFile:
    def __init__(self):
        self.Tag = MAGIC; self.Version = 3; self.ByteOrder = 1
        self.CharacterSet = 1; self.Context = 1
        self.reserved1 = b'\0' * 5; self.reserved2 = b'\0' * 6
        self.LocaleCount = 0; self.LocaleOffSet = 0
        self.languages = []; self.records = []
        self.info = b''          # raw Info block
        self.tail = b''          # anything after the records that is not Info
        self.stale_info_header = False

    # ---------- read ----------
    @classmethod
    def load(cls, path):
        return cls.parse(open(path, 'rb').read())

    @classmethod
    def parse(cls, d):
        o = cls()
        h = BinReader(d)
        o.Tag = h.bytes(3)
        if o.Tag != MAGIC: raise ValueError('not an MLD file (tag=%r)' % o.Tag)
        o.Version = h.u8(); o.ByteOrder = h.u8()
        o.CharacterSet = h.u8(); o.Context = h.u8()
        o.reserved1 = h.bytes(5)
        LanguageCount = h.u16(); LanguageOffSet = h.u32()
        TranslationsCount = h.u16(); TranslationsOffSet = h.u32()
        o.LocaleCount = h.u16(); o.LocaleOffSet = h.u32()
        InfoSize = h.u16(); InfoOffSet = h.u32()
        o.reserved2 = h.bytes(6)
        assert h.p == 0x2A, h.p
        o.header_size = h.p

        r = BinReader(d, LanguageOffSet)
        for _ in range(LanguageCount):
            o.languages.append(Language.read(r))
        if r.p != TranslationsOffSet:
            raise ValueError('language table ends at %#x, TranslationsOffSet=%#x'
                             % (r.p, TranslationsOffSet))

        nfield = 1 + (1 if o.Context in (1, 3) and o.Version > 2 else 0) \
                   + (1 if o.Context in (1, 2) and o.Version > 2 else 0)
        r = BinReader(d, TranslationsOffSet)
        for _ in range(TranslationsCount):
            rec = Record()
            rec.Original = r.wstr()
            if o.Context in (1, 3) and o.Version > 2: rec.ClassName = r.wstr()
            if o.Context in (1, 2) and o.Version > 2: rec.ComponentName = r.wstr()
            rec.translations = [r.wstr() for _ in range(LanguageCount - 1)]
            o.records.append(rec)
        o.records_end = r.p

        rest = d[r.p:]
        o.info = rest; o.tail = b''
        o._declared_info = (InfoOffSet, InfoSize)
        if not (InfoOffSet == r.p and InfoSize == len(rest)):
            o.stale_info_header = True   # header's Info pointer is stale/broken
        return o

    # ---------- write ----------
    def dump(self, exact=False):
        langs = BinWriter()
        for l in self.languages: l.write(langs)
        recs = BinWriter()
        for rec in self.records:
            recs.wstr(rec.Original)
            if self.Context in (1, 3) and self.Version > 2: recs.wstr(rec.ClassName)
            if self.Context in (1, 2) and self.Version > 2: recs.wstr(rec.ComponentName)
            for t in rec.translations: recs.wstr(t)
        LanguageOffSet = 0x2A
        TranslationsOffSet = LanguageOffSet + len(langs.b)
        InfoOffSet = TranslationsOffSet + len(recs.b)
        InfoSize = len(self.info)
        if exact and getattr(self, '_declared_info', None):
            InfoOffSet, InfoSize = self._declared_info
        w = BinWriter()
        w.bytes(self.Tag); w.u8(self.Version); w.u8(self.ByteOrder)
        w.u8(self.CharacterSet); w.u8(self.Context); w.bytes(self.reserved1)
        w.u16(len(self.languages)); w.u32(LanguageOffSet)
        w.u16(len(self.records)); w.u32(TranslationsOffSet)
        w.u16(self.LocaleCount); w.u32(self.LocaleOffSet)
        w.u16(InfoSize); w.u32(InfoOffSet)
        w.bytes(self.reserved2)
        w.bytes(langs.b); w.bytes(recs.b); w.bytes(self.info)
        return bytes(w.b)

    def save(self, path):
        open(path, 'wb').write(self.dump())

    # ---------- convenience ----------
    def lang_names(self):
        return [l.EnglishName.decode('latin-1') or '?' for l in self.languages]

    def decode_info(self):
        try:
            r = BinReader(self.info)
            name = r.wstr(); a = r.wstr(); b = r.wstr()
            day = r.u8(); mon = r.u8(); yr = r.u16(); hh = r.u8(); mm = r.u8(); ss = r.u8()
            return dict(Name=name.decode('cp1252'), F2=a, F3=b,
                        Stamp='%04d-%02d-%02d %02d:%02d:%02d' % (yr, mon, day, hh, mm, ss))
        except Exception as e:
            return dict(error=str(e), raw=self.info.hex(' '))


if __name__ == '__main__':
    import sys, glob, os
    ROOT = r"C:\Users\<user>\Desktop\Age of Wonders X - Claude"
    sets = [('live', ROOT + r"\Dict"),
            ('1.36', ROOT + r"\reference files\AoW 1.36\Dict"),
            ('1.45', ROOT + r"\reference files\AoW+ 1.45\Dict"),
            ('Zigg', ROOT + r"\reference files\AoW Ziggurat\Dict")]
    ok = tot = 0
    for tag, dp in sets:
        for f in sorted(glob.glob(dp + r"\*.mld")):
            raw = open(f, 'rb').read()
            tot += 1
            try:
                m = MLDFile.parse(raw)
            except Exception as e:
                print("%-5s %-14s PARSE FAIL: %s" % (tag, os.path.basename(f), e)); continue
            same = m.dump(exact=True) == raw
            ok += same
            print("%-5s %-14s recs=%-5d langs=%d info=%-3d roundtrip=%s%s" % (
                tag, os.path.basename(f), len(m.records), len(m.languages), len(m.info),
                "OK" if same else "MISMATCH",
                "  [header InfoOffSet/InfoSize stale: says %#x/%d, actual %#x/%d]"
                % (m._declared_info[0], m._declared_info[1], m.records_end, len(m.info))
                if m.stale_info_header else ""))
    print("\nround-trip: %d/%d byte-identical" % (ok, tot))
