"""
AoWxInk - localisation editor for Age of Wonders 1, replacing MLDEdit.

MLDEdit's bar is low: it has no undo, no Save As, no backup, and its writer
silently corrupts every file it touches (it never writes `Primary`, writes
`ISODefaultCountry` twice overlapping, never recomputes header offsets and
never truncates). AoWxInk writes the format correctly, repairs damage it finds
on load, and keeps every record bit-identical unless you edited it.
"""
from __future__ import annotations
import os, sys, re, json, shutil, datetime, collections

from PySide6.QtCore import (Qt, QAbstractTableModel, QModelIndex, QSize,
                            QSortFilterProxyModel, QSettings)
from PySide6.QtGui import (QAction, QColor, QIcon, QKeySequence, QFont, QBrush,
                           QPainter, QPixmap, QPalette)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QSplitter, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QComboBox, QPushButton, QTableView, QListWidget,
    QListWidgetItem, QFileDialog, QMessageBox, QToolBar, QStatusBar, QCheckBox,
    QDialog, QDialogButtonBox, QGroupBox, QPlainTextEdit, QStyle, QHeaderView,
    QAbstractItemView, QFormLayout, QSpinBox, QRadioButton, QTextEdit,
    QDockWidget, QTreeWidget, QTreeWidgetItem, QStyledItemDelegate,
)

try:
    from spellchecker import SpellChecker
except Exception:
    SpellChecker = None

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from aowxlib import mld                                              # noqa: E402
from aowxlib.mld import MLDFile, Language, Record                    # noqa: E402
from aowxlib import cyrillic                                         # noqa: E402
from aowxlib.gui import (EMBLEM_PATH, FAINT, VERSION, ChromeDialog,  # noqa: E402
                         CaptionedMainWindow, close_splash,
                         draw_backdrop, draw_emblem_centred,
                         draw_hint_under, paint_chrome, pin_dark)

APP = "AoWxInk"
HERE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
DICT_FILES = ["AoW", "AoWEd", "AoWSetup", "Campaign", "CampMaps",
              "CustMaps", "Release", "ResStr"]
UNDO_LIMIT = 200


def dec(b, codec="cp1252"):
    if isinstance(b, (bytes, bytearray)):
        try:
            return b.decode(codec)
        except Exception:
            return b.decode("cp1252", "replace")
    return b or ""


# ---------------------------------------------------------------------------
# model
# ---------------------------------------------------------------------------
class Book:
    """One .mld file plus its edit state."""

    def __init__(self, name, path, f: MLDFile, repaired=0):
        self.name = name
        self.path = path
        self.f = f
        self.dirty = False
        self.repaired = repaired

    @property
    def langs(self):
        return self.f.languages

    def codec_for(self, col):
        """col 0 = Original (always cp1252); col n = translation n-1."""
        if col == 0:
            return "cp1252"
        i = col
        if 0 <= i < len(self.f.languages):
            return cyrillic.codec_name(self.f.languages[i])
        return "cp1252"

    def text(self, row, col):
        r = self.f.records[row]
        raw = r.Original if col == 0 else (r.translations[col - 1]
                                           if col - 1 < len(r.translations) else b"")
        return cyrillic.decode(raw, self.codec_for(col))

    def set_text(self, row, col, s):
        r = self.f.records[row]
        raw = cyrillic.encode(s, self.codec_for(col))
        if col == 0:
            r.Original = raw
        else:
            while len(r.translations) < col:
                r.translations.append(b"")
            r.translations[col - 1] = raw


class TableModel(QAbstractTableModel):
    HEAD_EXTRA = ["Class", "Component"]

    def __init__(self, main):
        super().__init__()
        self.main = main
        self.book = None
        self.hidden = set()

    def set_book(self, book):
        self.beginResetModel()
        self.book = book
        self.endResetModel()

    def col_count(self):
        if not self.book:
            return 0
        return 1 + len(self.book.langs) + 2         # Original + langs(incl Native? no) + 2

    def rowCount(self, parent=QModelIndex()):
        return 0 if not self.book or parent.isValid() else len(self.book.f.records)

    def columnCount(self, parent=QModelIndex()):
        if not self.book or parent.isValid():
            return 0
        # 0 = Original(source), 1..n-1 = language columns 1..n-1, then Class, Component
        return len(self.book.langs) + 2

    def lang_index_for_column(self, col):
        """Column 0 is Original (== Native, language 0). Columns 1..n-1 map to
        language index col. The last two columns are Class/Component."""
        if col == 0:
            return 0
        if col < len(self.book.langs):
            return col
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation != Qt.Horizontal or role != Qt.DisplayRole or not self.book:
            return None
        n = len(self.book.langs)
        if section == 0:
            return "Source (Native)"
        if section < n:
            L = self.book.langs[section]
            return "%s%s" % (dec(L.EnglishName) or dec(L.ISOLanguage),
                             "" if L.CodePage in (0, 1252) else "  [cp%d]" % L.CodePage)
        return self.HEAD_EXTRA[section - n]

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not self.book:
            return None
        row, col = index.row(), index.column()
        n = len(self.book.langs)
        rec = self.book.f.records[row]
        if col >= n:
            if role in (Qt.DisplayRole, Qt.ToolTipRole):
                return dec(rec.ClassName if col == n else rec.ComponentName)
            return None
        if role in (Qt.DisplayRole, Qt.EditRole, Qt.ToolTipRole):
            return self.book.text(row, col)
        if role == Qt.ForegroundRole:
            if col == 0:
                return QBrush(QColor("#d8d8dc"))
            src = self.book.text(row, 0)
            cur = self.book.text(row, col)
            if not cur:
                return QBrush(QColor("#7a7a86"))
            if cur == src:
                return QBrush(QColor("#c8a04a"))          # untranslated
        return None

    def flags(self, index):
        if not index.isValid() or not self.book:
            return Qt.NoItemFlags
        f = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if index.column() < len(self.book.langs):
            f |= Qt.ItemIsEditable
        return f

    def setData(self, index, value, role=Qt.EditRole):
        if role != Qt.EditRole or not self.book:
            return False
        row, col = index.row(), index.column()
        if col >= len(self.book.langs):
            return False
        old = self.book.text(row, col)
        if old == str(value):
            return False
        self.main.apply_edit(self.book, row, col, str(value), push_undo=True)
        return True


class FilterProxy(QSortFilterProxyModel):
    MODES = ["All rows", "Untranslated (same as source)", "Empty", "Translated"]

    def __init__(self):
        super().__init__()
        self.mode = 0
        self.needle = ""
        self.search_col = -1        # -1 = any
        self.use_regex = False
        self.focus_lang = 1

    def filterAcceptsRow(self, row, parent):
        m = self.sourceModel()
        if m.book is None:
            return False
        n = len(m.book.langs)
        if self.mode:
            col = self.focus_lang if self.focus_lang < n else 1
            src = m.book.text(row, 0)
            cur = m.book.text(row, col)
            if self.mode == 1 and not (cur and cur == src):
                return False
            if self.mode == 2 and cur:
                return False
            if self.mode == 3 and (not cur or cur == src):
                return False
        if self.needle:
            cols = range(n) if self.search_col < 0 else [self.search_col]
            hit = False
            for c in cols:
                t = m.book.text(row, c)
                if self.use_regex:
                    try:
                        if re.search(self.needle, t, re.I):
                            hit = True
                            break
                    except re.error:
                        hit = True
                        break
                elif self.needle.lower() in t.lower():
                    hit = True
                    break
            if not hit:
                return False
        return True


# ---------------------------------------------------------------------------
# spell checking
# ---------------------------------------------------------------------------
SPELL_LANGS = {
    "en": "en", "english": "en",
    "de": "de", "german": "de", "deutsch": "de",
    "fr": "fr", "french": "fr", "français": "fr", "francais": "fr",
    "es": "es", "spanish": "es", "español": "es", "espanol": "es",
    "it": "it", "italian": "it", "italiano": "it",
    "nl": "nl", "dutch": "nl", "nederlands": "nl",
    "ru": "ru", "russian": "ru", "русский": "ru",
}

_SPELL_CACHE = {}


def spell_checker(code):
    """A SpellChecker for an ISO code, or None if pyspellchecker does not
    bundle that dictionary (it raises on a missing language)."""
    if code not in _SPELL_CACHE:
        try:
            _SPELL_CACHE[code] = SpellChecker(language=code)
        except Exception:
            _SPELL_CACHE[code] = None
    return _SPELL_CACHE[code]


def spell_code_for(language):
    """Map a .mld Language record to a pyspellchecker code, else None."""
    for name in (dec(language.ISOLanguage).strip(),
                 dec(language.EnglishName).strip(),
                 cyrillic.decode(language.NativeName, cyrillic.codec_name(language)).strip()):
        code = SPELL_LANGS.get(name.lower())
        if code:
            return code
    return None


# game markup: printf/Delphi placeholders (%s, %d, %1, %0:s, %-5d) and
# backslash escapes (\n, \t, stray backslashes)
_RX_MARKUP = re.compile(r"%[%\-.#0-9:]*[A-Za-z]?|\\+[A-Za-z]?")
# a pure word: letters only, apostrophes allowed inside (Merlin's, l'armée)
_RX_WORD = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*$")
_STRIP = "\"'‘’“”«».,;:!?()[]{}<>*+/=|~^–—-_"


def flatten(s):
    """Cell text with markup stripped and whitespace collapsed."""
    return " ".join(_RX_MARKUP.sub(" ", s).replace("&", "").split())


def extract_words(s):
    """Words worth spellchecking: markup stripped, ampersand hotkey markers
    removed (&File -> File), then only pure-letter tokens of 3+ letters that
    are not ALL-CAPS. Tokens with digits or embedded punctuation are game
    codes, not prose."""
    words = []
    for chunk in flatten(s).split():
        core = chunk.strip(_STRIP)
        if len(core) < 3 or core.isupper():
            continue
        if not _RX_WORD.match(core):
            continue
        words.append(core)
    return words


_BRIT_SUBS = [("isation", "ization"), ("ising", "izing"), ("ised", "ized"),
              ("ise", "ize"), ("yse", "yze"), ("our", "or")]


def spell_known(word, sp, english=False):
    """True if the dictionary accepts the word. pyspellchecker's 'en' list is
    en-US, so for English a word also counts as correct when a standard
    British->American suffix transform of it is known: -our->-or (colour),
    -ise/-isation->-ize/-ization (organise), -re->-er (centre), and a
    travelled-style doubled consonant collapsed before the suffix."""
    lw = word.lower().strip("'’")
    if lw.endswith("'s") or lw.endswith("’s"):
        lw = lw[:-2]
    if lw in sp:
        return True
    if english:
        cands = [lw.replace(a, b, 1) for a, b in _BRIT_SUBS if a in lw]
        if lw.endswith("re"):
            cands.append(lw[:-2] + "er")
        m = re.sub(r"ll(ed|ing|er|ers|ous)$", r"l\1", lw)
        if m != lw:
            cands.append(m)
        return any(c in sp for c in cands)
    return False


def scan_language(books, col, sp, english=False, accepted=(), only=None):
    """Spellcheck one language column. `only` limits the scan to that book
    index (scanning all 8 dictionaries at once is too slow on weaker
    machines); None keeps the old scan-everything behaviour for tests.
    Returns {word: [(book_index, row, context), ...]} of flagged words."""
    hits = {}
    for bi, b in enumerate(books):
        if only is not None and bi != only:
            continue
        if col >= len(b.langs):
            continue
        for row in range(len(b.f.records)):
            s = b.text(row, col)
            if not s:
                continue
            flat = None
            for w in extract_words(s):
                if w.lower() in accepted or spell_known(w, sp, english):
                    continue
                if flat is None:
                    flat = flatten(s)
                p = flat.find(w)
                ctx = flat[max(0, p - 30):p + len(w) + 30] if p >= 0 else flat[:60]
                hits.setdefault(w, []).append((bi, row, ctx))
    return hits


# ---------------------------------------------------------------------------
# dialogs
# ---------------------------------------------------------------------------
class PropagateDialog(ChromeDialog):
    """Fill other languages from a chosen source language."""

    def __init__(self, books, langs, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Propagate translations")
        v = QVBoxLayout(self)
        v.addWidget(QLabel(
            "<b>Source language</b> - the column that is correct and up to date.<br>"
            "Every other language is then brought into line with it."))
        self.cb_src = QComboBox()
        for i, L in enumerate(langs):
            self.cb_src.addItem("%s" % (dec(L.EnglishName) or dec(L.ISOLanguage) or "Native"), i)
        self.cb_src.setCurrentIndex(0)
        v.addWidget(self.cb_src)

        gb = QGroupBox("What to do")
        gv = QVBoxLayout(gb)
        self.chk_memory = QCheckBox(
            "Reuse existing translations of the same source text (translation memory)")
        self.chk_memory.setChecked(True)
        self.chk_memory.setToolTip(
            "The same string often appears in several dictionaries. If it is already "
            "translated somewhere, copy that translation here.")
        self.chk_stale = QCheckBox(
            "Flag entries whose source text changed since the translation was written")
        self.chk_stale.setChecked(True)
        self.chk_seed = QCheckBox("Fill still-empty cells with the source text")
        self.chk_seed.setChecked(False)
        self.chk_seed.setToolTip(
            "Leaves nothing blank, but the result reads as English until a human "
            "translates it. Off by default.")
        for w in (self.chk_memory, self.chk_stale, self.chk_seed):
            gv.addWidget(w)
        v.addWidget(gb)

        gb2 = QGroupBox("Scope")
        g2 = QVBoxLayout(gb2)
        self.rb_all = QRadioButton("All %d dictionaries" % len(books))
        self.rb_all.setChecked(True)
        self.rb_one = QRadioButton("Only the current dictionary")
        g2.addWidget(self.rb_all)
        g2.addWidget(self.rb_one)
        v.addWidget(gb2)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self.resize(620, 380)


class AddLanguageDialog(ChromeDialog):
    PRESETS = cyrillic.LANGUAGE_PRESETS

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add a language")
        v = QVBoxLayout(self)
        form = QFormLayout()
        self.cb_preset = QComboBox()
        for key, p in self.PRESETS.items():
            self.cb_preset.addItem(p["EnglishName"], key)
        self.cb_preset.currentIndexChanged.connect(self.fill)
        form.addRow("Preset", self.cb_preset)
        self.f_en = QLineEdit()
        self.f_native = QLineEdit()
        self.f_iso = QLineEdit()
        self.f_country = QLineEdit()
        self.f_primary = QSpinBox()
        self.f_primary.setRange(0, 255)
        self.f_sub = QSpinBox()
        self.f_sub.setRange(0, 255)
        self.f_cp = QSpinBox()
        self.f_cp.setRange(0, 65535)
        for lab, w in (("English name", self.f_en), ("Native name", self.f_native),
                       ("ISO language", self.f_iso), ("ISO country", self.f_country),
                       ("Primary LANGID", self.f_primary), ("Sub LANGID", self.f_sub),
                       ("Code page", self.f_cp)):
            form.addRow(lab, w)
        v.addLayout(form)
        self.note = QLabel()
        self.note.setWordWrap(True)
        self.note.setStyleSheet("color:#c8a04a;")
        v.addWidget(self.note)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self.fill()
        self.resize(560, 420)

    def fill(self):
        p = self.PRESETS[self.cb_preset.currentData()]
        self.f_en.setText(p["EnglishName"])
        self.f_native.setText(p["NativeName"])
        self.f_iso.setText(p["ISOLanguage"])
        self.f_country.setText(p["ISODefaultCountry"])
        self.f_primary.setValue(p["Primary"])
        self.f_sub.setValue(p["DefaultSub"])
        self.f_cp.setValue(p["CodePage"])
        self.note.setText(p.get("note", ""))

    def language(self):
        L = Language()
        L.Primary = self.f_primary.value()
        L.ISOLanguage = self.f_iso.text().encode("latin-1", "replace")[:2].ljust(2, b" ")
        L.DefaultSub = self.f_sub.value()
        L.ISODefaultCountry = self.f_country.text().encode("latin-1", "replace")[:2].ljust(2, b" ")
        L.AllSubs = b""
        L.ISOAllCountries = b""
        L.CharacterSet = 0
        L.CodePage = self.f_cp.value()
        L.Options = 0
        L.EnglishName = self.f_en.text().encode("latin-1", "replace")
        L.NativeName = cyrillic.encode(self.f_native.text(),
                                       cyrillic.codec_name_for_cp(self.f_cp.value()))
        L.FontName = b""
        L.FontSize = 0
        return L


# ---------------------------------------------------------------------------
# main window
# ---------------------------------------------------------------------------
class InkTable(QTableView):
    """The translation grid. The moss/stone backdrop carries the emblem + a
    hint until a Dict folder is opened, then stays barely visible behind the
    rows; alternating shading is kept via a translucent alternate colour."""

    class _OpaqueEditors(QStyledItemDelegate):
        """Cell editors must not inherit the view's transparent Base."""

        def createEditor(self, parent, option, index):
            ed = super().createEditor(parent, option, index)
            if ed is not None:
                ed.setPalette(QApplication.palette())
                ed.setAutoFillBackground(True)
            return ed

    def __init__(self, main):
        super().__init__()
        self.main = main
        self.emblem = QPixmap(EMBLEM_PATH)
        # palette (not stylesheet) transparency: a stylesheet background here
        # breaks the native scrollbars (black grooves)
        pal = self.palette()
        pal.setBrush(QPalette.Base, QColor(0, 0, 0, 0))
        pal.setBrush(QPalette.AlternateBase, QColor(128, 128, 128, 30))
        self.setPalette(pal)
        self.viewport().setAutoFillBackground(False)
        self.setItemDelegate(self._OpaqueEditors(self))

    def paintEvent(self, ev):
        p = QPainter(self.viewport())
        vw, vh = self.viewport().width(), self.viewport().height()
        pal = QApplication.palette()
        loaded = self.main.book is not None
        p.fillRect(0, 0, vw, vh, pal.base() if loaded else pal.window())
        draw_backdrop(p, vw, vh, self.main.bg_theme, FAINT if loaded else None)
        if not loaded:
            th = draw_emblem_centred(p, self.emblem, vw, vh)
            draw_hint_under(p, pal, vw, vh, th,
                            "Open the game's Dict folder to begin (Ctrl+O)")
        p.end()
        super().paintEvent(ev)


class Main(CaptionedMainWindow):
    def __init__(self):
        super().__init__()
        self.books = []
        self.book = None
        self.folder = None
        self.settings = QSettings("AoWx", "AoWxInk")
        self.bg_theme = self.settings.value("bg_theme", "moss")
        self._hidden_cols = set()
        self._undo, self._redo = [], []
        self._loading = False
        self.setWindowTitle(APP)
        ico = os.path.join(HERE, "assets", "aowxink.ico")
        if os.path.isfile(ico):
            self.setWindowIcon(QIcon(ico))
        self.resize(1500, 880)

        tb = QToolBar("Main")
        tb.setIconSize(QSize(16, 16))
        self.addToolBar(tb)
        st = self.style()

        def act(text, icon, slot, sc=None, tip=None):
            a = QAction(st.standardIcon(icon), text, self)
            a.triggered.connect(slot)
            if sc:
                a.setShortcut(QKeySequence(sc))
            a.setToolTip(tip or text)
            tb.addAction(a)
            return a

        act("Open Dict folder", QStyle.SP_DirOpenIcon, self.open_folder, "Ctrl+O")
        act("Save", QStyle.SP_DialogSaveButton, self.save_current, "Ctrl+S")
        act("Save all", QStyle.SP_DriveFDIcon, self.save_all, "Ctrl+Shift+S")
        tb.addSeparator()
        self.act_undo = act("Undo", QStyle.SP_ArrowBack, self.undo, "Ctrl+Z")
        self.act_redo = act("Redo", QStyle.SP_ArrowForward, self.redo, "Ctrl+Y")
        self.act_undo.setEnabled(False)
        self.act_redo.setEnabled(False)
        tb.addSeparator()
        act("Propagate", QStyle.SP_BrowserReload, self.propagate, "Ctrl+P",
            "Bring every language into line with a chosen source language")
        act("Add language", QStyle.SP_FileDialogNewFolder, self.add_language, None,
            "Add a new language column to every dictionary")
        tb.addSeparator()
        act("Export TSV", QStyle.SP_ArrowUp, self.export_tsv, None,
            "Export the current dictionary for external translation")
        act("Import TSV", QStyle.SP_ArrowDown, self.import_tsv)
        act("Stats", QStyle.SP_MessageBoxInformation, self.show_stats)
        act("Find typos", QStyle.SP_FileDialogContentsView, self.find_typos, "Ctrl+T",
            "Spellcheck one language column across all dictionaries")
        tb.addSeparator()
        tb.addWidget(QLabel(" Background: "))
        self.cb_theme = QComboBox()
        self.cb_theme.addItem("Moss", "moss")
        self.cb_theme.addItem("Stone", "stone")
        self.cb_theme.setCurrentIndex(max(0, self.cb_theme.findData(self.bg_theme)))
        self.cb_theme.currentIndexChanged.connect(self.change_theme)
        tb.addWidget(self.cb_theme)
        ver = QLabel("   Version %s" % VERSION)
        ver.setStyleSheet("color:#888;")
        tb.addWidget(ver)

        split = QSplitter(Qt.Horizontal)
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(4, 4, 4, 4)
        lv.addWidget(QLabel("<b>Dictionaries</b>"))
        self.file_list = QListWidget()
        self.file_list.currentRowChanged.connect(self.on_file_changed)
        lv.addWidget(self.file_list, 1)
        self.lang_box = QGroupBox("Columns")
        self.lang_layout = QVBoxLayout(self.lang_box)
        lv.addWidget(self.lang_box)
        split.addWidget(left)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(4, 4, 4, 4)
        bar = QHBoxLayout()
        bar.addWidget(QLabel("Find"))
        self.f_search = QLineEdit()
        self.f_search.setPlaceholderText("substring, or a regular expression")
        self.f_search.textChanged.connect(self.apply_filter)
        bar.addWidget(self.f_search, 2)
        self.chk_regex = QCheckBox("regex")
        self.chk_regex.stateChanged.connect(self.apply_filter)
        bar.addWidget(self.chk_regex)
        bar.addWidget(QLabel("in"))
        self.cb_scol = QComboBox()
        self.cb_scol.currentIndexChanged.connect(self.apply_filter)
        bar.addWidget(self.cb_scol)
        bar.addWidget(QLabel("Show"))
        self.cb_mode = QComboBox()
        self.cb_mode.addItems(FilterProxy.MODES)
        self.cb_mode.currentIndexChanged.connect(self.apply_filter)
        bar.addWidget(self.cb_mode)
        self.cb_focus = QComboBox()
        self.cb_focus.setToolTip("which language the Show filter applies to")
        self.cb_focus.currentIndexChanged.connect(self.apply_filter)
        bar.addWidget(self.cb_focus)
        rv.addLayout(bar)

        self.model = TableModel(self)
        self.proxy = FilterProxy()
        self.proxy.setSourceModel(self.model)
        self.table = InkTable(self)
        self.table.setModel(self.proxy)
        self.table.setSelectionBehavior(QAbstractItemView.SelectItems)
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked |
                                   QAbstractItemView.SelectedClicked |
                                   QAbstractItemView.EditKeyPressed)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setDefaultSectionSize(20)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.selectionModel_connected = False
        rv.addWidget(self.table, 3)

        self.editor = QTextEdit()
        self.editor.setPlaceholderText("full text of the selected cell - edit here for long strings")
        self.editor.setMaximumHeight(150)
        self.editor.focusOutEvent = self._editor_commit(self.editor.focusOutEvent)
        rv.addWidget(self.editor, 1)
        split.addWidget(right)
        split.setSizes([260, 1240])
        self.setCentralWidget(split)

        # ---- typo finder dock ----
        self.typo_dock = QDockWidget("Typo finder", self)
        self.typo_dock.setAllowedAreas(Qt.BottomDockWidgetArea | Qt.RightDockWidgetArea)
        tw = QWidget()
        tv = QVBoxLayout(tw)
        tbar = QHBoxLayout()
        b_scan = QPushButton("Scan this dictionary")
        b_scan.setToolTip("Spellchecks the selected language column of the "
                          "dictionary selected on the left. One dictionary at "
                          "a time keeps the scan fast.")
        b_scan.clicked.connect(self.scan_typos)
        tbar.addWidget(b_scan)
        tbar.addWidget(QLabel("Language"))
        self.cb_typo_lang = QComboBox()
        tbar.addWidget(self.cb_typo_lang)
        self.b_addword = QPushButton("Add word")
        self.b_addword.setToolTip(
            "Accept the selected word forever. Accepted words are stored in "
            "aowxink_accepted_words.json next to the dictionaries.")
        self.b_addword.clicked.connect(self.typo_add_word)
        tbar.addWidget(self.b_addword)
        self.typo_count = QLabel("not scanned")
        tbar.addWidget(self.typo_count)
        tbar.addStretch(1)
        tv.addLayout(tbar)
        self.typo_tree = QTreeWidget()
        self.typo_tree.setHeaderLabels(["Word / occurrence",
                                        "Suggestions (click the word)", "Where"])
        self.typo_tree.setColumnWidth(0, 380)
        self.typo_tree.setColumnWidth(1, 240)
        self.typo_tree.itemActivated.connect(self.goto_typo)
        self.typo_tree.itemClicked.connect(self.goto_typo)
        tv.addWidget(self.typo_tree)
        self.typo_dock.setWidget(tw)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.typo_dock)
        self.typo_dock.hide()

        self.setStatusBar(QStatusBar())
        self.status("Open the game's Dict folder to begin.")

    # -- plumbing -----------------------------------------------------------
    def _editor_commit(self, orig):
        def handler(ev):
            self.commit_editor()
            return orig(ev)
        return handler

    def status(self, m):
        self.statusBar().showMessage(m)

    def change_theme(self):
        self.bg_theme = self.cb_theme.currentData()
        self.settings.setValue("bg_theme", self.bg_theme)
        self.table.viewport().update()
        self.update()

    def paintEvent(self, ev):
        paint_chrome(self, self.bg_theme)
        super().paintEvent(ev)

    def update_title(self):
        n = sum(1 for b in self.books if b.dirty)
        self.setWindowTitle("%s - %s%s" % (APP, self.folder or "(no folder)",
                                           "  *%d unsaved*" % n if n else ""))

    # -- open / save --------------------------------------------------------
    def open_folder(self):
        start = self.folder or self.settings.value("last_folder", "")
        if start and not os.path.isdir(start):
            start = ""
        d = QFileDialog.getExistingDirectory(self, "Select the game's Dict folder",
                                             start)
        if d:
            self.load_folder(d)

    def load_folder(self, folder):
        self.books = []
        self.folder = folder
        repaired_total = 0
        for name in DICT_FILES:
            p = os.path.join(folder, name + ".mld")
            if not os.path.isfile(p):
                continue
            try:
                f = MLDFile.load(p)
            except Exception as e:
                QMessageBox.warning(self, APP, "Could not read %s:\n%s" % (name, e))
                continue
            fixed = self.repair_languages(f)
            repaired_total += fixed
            self.books.append(Book(name, p, f, fixed))
        if not self.books:
            QMessageBox.information(self, APP, "No .mld dictionaries found in that folder.")
            return
        self.settings.setValue("last_folder", folder)
        self._typo_seed = None
        self.file_list.clear()
        for b in self.books:
            self.file_list.addItem(QListWidgetItem("%s   (%d)" % (b.name, len(b.f.records))))
        self._undo.clear()
        self._redo.clear()
        self.update_undo_actions()
        self.file_list.setCurrentRow(0)
        total = sum(len(b.f.records) for b in self.books)
        msg = "%d dictionaries, %d records." % (len(self.books), total)
        if repaired_total:
            msg += ("  Repaired %d damaged language field(s) in memory - "
                    "save to write the fix." % repaired_total)
        self.status(msg)
        self.update_title()

    @staticmethod
    def repair_languages(f: MLDFile):
        """MLDEdit mangles Primary/ISODefaultCountry. Restore what we can infer."""
        fixed = 0
        for L in f.languages:
            if L.is_native:
                continue
            iso = dec(L.ISOLanguage).strip().lower()
            canon = cyrillic.CANON_BY_ISO.get(iso)
            if canon is None:
                canon = cyrillic.CANON_BY_NAME.get(dec(L.EnglishName).strip().lower())
            if canon is None:
                continue
            for fld in ("Primary", "DefaultSub", "ISODefaultCountry", "ISOLanguage"):
                want = canon[fld]
                if isinstance(want, str):
                    want = want.encode("latin-1")
                if getattr(L, fld) != want:
                    setattr(L, fld, want)
                    fixed += 1
        return fixed

    def save_book(self, b):
        bak = b.path + ".bak_aowxink"
        if not os.path.isfile(bak):
            shutil.copy2(b.path, bak)
        tmp = b.path + ".tmp"
        b.f.save(tmp)
        MLDFile.load(tmp)                     # re-parse before trusting it
        os.replace(tmp, b.path)
        b.dirty = False
        b.repaired = 0

    def save_current(self):
        if self.book:
            self.commit_editor()
            try:
                self.save_book(self.book)
            except Exception as e:
                QMessageBox.critical(self, APP, "Save failed:\n%s" % e)
                return
            self.status("Saved %s" % self.book.name)
            self.update_title()

    def save_all(self):
        self.commit_editor()
        n = 0
        for b in self.books:
            if b.dirty or b.repaired:
                try:
                    self.save_book(b)
                    n += 1
                except Exception as e:
                    QMessageBox.critical(self, APP, "Saving %s failed:\n%s" % (b.name, e))
                    return
        self.status("Saved %d dictionary file(s)." % n)
        self.update_title()

    # -- view ---------------------------------------------------------------
    def on_file_changed(self, row):
        if row < 0 or row >= len(self.books):
            return
        self.book = self.books[row]
        self.model.set_book(self.book)
        self.rebuild_lang_controls()
        self.table.resizeColumnsToContents()
        h = self.table.horizontalHeader()
        for c in range(self.model.columnCount()):
            if self.table.columnWidth(c) > 420:
                self.table.setColumnWidth(c, 420)
        try:
            self.table.selectionModel().currentChanged.disconnect()
        except Exception:
            pass
        self.table.selectionModel().currentChanged.connect(self.on_cell)
        self.apply_filter()

    def rebuild_lang_controls(self):
        # keep the user's filter choices stable while navigating between
        # dictionaries: remember them before the rebuild, restore after
        prev_scol = self.cb_scol.currentData() if self.cb_scol.count() else None
        prev_focus = self.cb_focus.currentData() if self.cb_focus.count() else None
        hidden = self._hidden_cols
        while self.lang_layout.count():
            w = self.lang_layout.takeAt(0).widget()
            if w:
                w.deleteLater()
        self.cb_scol.blockSignals(True)
        self.cb_focus.blockSignals(True)
        self.cb_scol.clear()
        self.cb_focus.clear()
        self.cb_scol.addItem("any column", -1)
        for i, L in enumerate(self.book.langs):
            name = dec(L.EnglishName) or dec(L.ISOLanguage) or "Native"
            if i == 0:
                name = "Source (Native)"
            cb = QCheckBox(name)
            cb.setChecked(i not in hidden)
            cb.stateChanged.connect(lambda _s, col=i: self.toggle_col(col))
            self.lang_layout.addWidget(cb)
            self.cb_scol.addItem(name, i)
            self.cb_focus.addItem(name, i)

        # first time: "any column" / Source (Native); afterwards whatever the
        # user last picked, until they change it themselves
        def pick(combo, want):
            combo.setCurrentIndex(0)
            if want is not None:
                for j in range(combo.count()):
                    if combo.itemData(j) == want:
                        combo.setCurrentIndex(j)
                        break
        pick(self.cb_scol, prev_scol)
        pick(self.cb_focus, prev_focus)
        self.cb_scol.blockSignals(False)
        self.cb_focus.blockSignals(False)
        for c in range(self.model.columnCount()):
            self.table.setColumnHidden(c, c in hidden)
        self.rebuild_typo_langs()

    def rebuild_typo_langs(self):
        """Offer only languages pyspellchecker has a dictionary for; keep the
        user's pick across navigation, else follow the Show filter."""
        prev = (self.cb_typo_lang.currentData()
                if self.cb_typo_lang.count() else None)
        self.cb_typo_lang.blockSignals(True)
        self.cb_typo_lang.clear()
        missing = []
        for i, L in enumerate(self.book.langs):
            name = "Source (Native)" if i == 0 else (
                dec(L.EnglishName) or dec(L.ISOLanguage) or "?")
            # the Native column holds the game's embedded English source text
            code = spell_code_for(L) or ("en" if i == 0 else None)
            if code and SpellChecker and spell_checker(code):
                self.cb_typo_lang.addItem(name, (i, code))
            else:
                missing.append(name)
        want = prev[0] if prev else self.cb_focus.currentData()
        for j in range(self.cb_typo_lang.count()):
            if self.cb_typo_lang.itemData(j)[0] == want:
                self.cb_typo_lang.setCurrentIndex(j)
                break
        tip = "language column to spellcheck"
        if missing:
            tip += "\nno spelling dictionary for: %s" % ", ".join(missing)
        self.cb_typo_lang.setToolTip(tip)
        self.cb_typo_lang.blockSignals(False)

    def toggle_col(self, col):
        hid = not self.table.isColumnHidden(col)
        self.table.setColumnHidden(col, hid)
        (self._hidden_cols.add if hid else self._hidden_cols.discard)(col)

    def apply_filter(self):
        self.proxy.needle = self.f_search.text()
        self.proxy.use_regex = self.chk_regex.isChecked()
        self.proxy.search_col = self.cb_scol.currentData() if self.cb_scol.count() else -1
        self.proxy.mode = self.cb_mode.currentIndex()
        d = self.cb_focus.currentData()
        self.proxy.focus_lang = 1 if d is None else d   # 0 = Source is valid
        self.proxy.invalidateFilter()
        if self.book:
            self.status("%s: %d of %d rows shown"
                        % (self.book.name, self.proxy.rowCount(), len(self.book.f.records)))

    def on_cell(self, cur, _prev):
        if not cur.isValid() or not self.book:
            return
        src = self.proxy.mapToSource(cur)
        self._cell = (src.row(), src.column())
        self._loading = True
        if src.column() < len(self.book.langs):
            self.editor.setPlainText(self.book.text(src.row(), src.column()))
            self.editor.setEnabled(True)
        else:
            self.editor.setPlainText("")
            self.editor.setEnabled(False)
        self._loading = False

    def commit_editor(self):
        if self._loading or not self.book or not hasattr(self, "_cell"):
            return
        row, col = self._cell
        if col >= len(self.book.langs):
            return
        new = self.editor.toPlainText()
        if new != self.book.text(row, col):
            self.apply_edit(self.book, row, col, new, push_undo=True)

    # -- editing / undo -----------------------------------------------------
    def apply_edit(self, book, row, col, new, push_undo=True):
        old = book.text(row, col)
        if old == new:
            return
        if push_undo:
            self._undo.append((book, row, col, old, new))
            if len(self._undo) > UNDO_LIMIT:
                self._undo.pop(0)
            self._redo.clear()
            self.update_undo_actions()
        book.set_text(row, col, new)
        book.dirty = True
        idx = self.model.index(row, col)
        self.model.dataChanged.emit(idx, idx)
        self.update_title()

    def update_undo_actions(self):
        self.act_undo.setEnabled(bool(self._undo))
        self.act_redo.setEnabled(bool(self._redo))

    def undo(self):
        if not self._undo:
            return
        book, row, col, old, new = self._undo.pop()
        self._redo.append((book, row, col, old, new))
        self.goto(book, row, col)
        self.apply_edit(book, row, col, old, push_undo=False)
        self.update_undo_actions()
        self.status("Undid an edit in %s" % book.name)

    def redo(self):
        if not self._redo:
            return
        book, row, col, old, new = self._redo.pop()
        self._undo.append((book, row, col, old, new))
        self.goto(book, row, col)
        self.apply_edit(book, row, col, new, push_undo=False)
        self.update_undo_actions()
        self.status("Redid an edit in %s" % book.name)

    def goto(self, book, row, col):
        if book is not self.book:
            self.file_list.setCurrentRow(self.books.index(book))
        idx = self.proxy.mapFromSource(self.model.index(row, col))
        if idx.isValid():
            self.table.setCurrentIndex(idx)
            self.table.scrollTo(idx)

    # -- propagate ----------------------------------------------------------
    def propagate(self):
        if not self.books:
            return
        self.commit_editor()
        dlg = PropagateDialog(self.books, self.book.langs, self)
        if dlg.exec() != QDialog.Accepted:
            return
        src_col = dlg.cb_src.currentData()
        scope = self.books if dlg.rb_all.isChecked() else [self.book]

        memory = collections.defaultdict(dict)
        if dlg.chk_memory.isChecked():
            for b in self.books:
                for row in range(len(b.f.records)):
                    key = b.text(row, src_col)
                    if not key:
                        continue
                    for col in range(1, len(b.langs)):
                        if col == src_col:
                            continue
                        val = b.text(row, col)
                        if val and val != key:
                            memory[key].setdefault(col, val)

        filled = seeded = 0
        stale = []
        for b in scope:
            for row in range(len(b.f.records)):
                key = b.text(row, src_col)
                if not key:
                    continue
                for col in range(1, len(b.langs)):
                    if col == src_col:
                        continue
                    cur = b.text(row, col)
                    if not cur and dlg.chk_memory.isChecked() and col in memory.get(key, {}):
                        self.apply_edit(b, row, col, memory[key][col], push_undo=True)
                        filled += 1
                        continue
                    if not cur and dlg.chk_seed.isChecked():
                        self.apply_edit(b, row, col, key, push_undo=True)
                        seeded += 1
                        continue
                    if dlg.chk_stale.isChecked() and cur and cur == key and src_col == 0:
                        stale.append((b.name, row, col, key))

        lines = ["Source language: %s" %
                 (dec(self.book.langs[src_col].EnglishName) or "Native"), ""]
        lines.append("%d cell(s) filled from translations found elsewhere" % filled)
        if dlg.chk_seed.isChecked():
            lines.append("%d empty cell(s) seeded with the source text" % seeded)
        if dlg.chk_stale.isChecked():
            lines.append("")
            lines.append("%d cell(s) still read exactly like the source - these are the ones "
                         "a translator needs to look at:" % len(stale))
            per = collections.Counter((n, c) for n, _r, c, _k in stale)
            for (n, c), cnt in sorted(per.items()):
                name = dec(self.book.langs[c].EnglishName) if c < len(self.book.langs) else str(c)
                lines.append("   %-10s %-10s %d" % (n, name, cnt))
        self.report("Propagate", "\n".join(lines))
        self.apply_filter()
        self.update_title()

    # -- languages ----------------------------------------------------------
    def add_language(self):
        if not self.books:
            return
        dlg = AddLanguageDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return
        L = dlg.language()
        name = dec(L.EnglishName)
        if QMessageBox.question(
                self, APP,
                "Add '%s' as a new language column to all %d dictionaries?\n\n"
                "Every record gains one empty slot. Existing text is untouched."
                % (name, len(self.books))) != QMessageBox.Yes:
            return
        for b in self.books:
            b.f.languages.append(Language(**{k: getattr(L, k) for k in Language.FIELDS}))
            for r in b.f.records:
                r.translations.append(b"")
            b.dirty = True
        self.model.set_book(self.book)
        self.rebuild_lang_controls()
        self.update_title()
        extra = ""
        if L.CodePage == cyrillic.AOWX_RU_CODEPAGE:
            extra = ("\n\nThis language uses the AoWx Russian glyph mapping. The game's "
                     "bitmap fonts need the Cyrillic glyphs added before the text will "
                     "render in-game; the dictionary side is ready now.")
        self.report("Add language",
                    "Added '%s' to %d dictionaries.\nSave to write it to disk.%s"
                    % (name, len(self.books), extra))

    # -- import / export ----------------------------------------------------
    def export_tsv(self):
        if not self.book:
            return
        start = self.settings.value("last_tsv_dir", "") or self.folder or ""
        f, _ = QFileDialog.getSaveFileName(self, "Export TSV",
                                           os.path.join(start, self.book.name + ".tsv"),
                                           "TSV (*.tsv)")
        if not f:
            return
        self.settings.setValue("last_tsv_dir", os.path.dirname(f))
        n = len(self.book.langs)
        with open(f, "w", encoding="utf-8", newline="") as fh:
            heads = ["row"] + [self.model.headerData(c, Qt.Horizontal) for c in range(n)]
            fh.write("\t".join(heads) + "\n")
            for row in range(len(self.book.f.records)):
                cells = [str(row)] + [self.book.text(row, c).replace("\t", "\\t")
                                      .replace("\r", "\\r").replace("\n", "\\n")
                                      for c in range(n)]
                fh.write("\t".join(cells) + "\n")
        self.status("Exported %s" % f)

    def import_tsv(self):
        if not self.book:
            return
        start = self.settings.value("last_tsv_dir", "") or self.folder or ""
        f, _ = QFileDialog.getOpenFileName(self, "Import TSV", start, "TSV (*.tsv)")
        if not f:
            return
        self.settings.setValue("last_tsv_dir", os.path.dirname(f))
        n = len(self.book.langs)
        changed = 0
        with open(f, encoding="utf-8") as fh:
            next(fh, None)
            for line in fh:
                parts = line.rstrip("\n").split("\t")
                if len(parts) < 2 or not parts[0].isdigit():
                    continue
                row = int(parts[0])
                if row >= len(self.book.f.records):
                    continue
                for c in range(1, min(n, len(parts) - 1) + 1):
                    val = (parts[c].replace("\\t", "\t").replace("\\r", "\r")
                           .replace("\\n", "\n"))
                    if c - 1 == 0:
                        continue                 # never rewrite the lookup key from a TSV
                    if val != self.book.text(row, c - 1):
                        self.apply_edit(self.book, row, c - 1, val, push_undo=True)
                        changed += 1
        self.report("Import TSV", "%d cell(s) updated.\nThe Source column is never "
                                  "imported - it is the game's lookup key." % changed)

    # -- stats --------------------------------------------------------------
    def show_stats(self):
        if not self.books:
            return
        langs = self.book.langs
        lines = ["%-10s %6s" % ("", "records") +
                 "".join("%18s" % (dec(L.EnglishName) or "Native") for L in langs[1:])]
        tot = [0] * len(langs)
        totrec = 0
        for b in self.books:
            row = "%-10s %6d" % (b.name, len(b.f.records))
            totrec += len(b.f.records)
            for c in range(1, len(langs)):
                done = 0
                for r in range(len(b.f.records)):
                    cur = b.text(r, c)
                    if cur and cur != b.text(r, 0):
                        done += 1
                tot[c] += done
                row += "%18s" % ("%d (%d%%)" % (done, 100 * done / max(1, len(b.f.records))))
            lines.append(row)
        lines.append("")
        lines.append("%-10s %6d" % ("TOTAL", totrec) +
                     "".join("%18s" % ("%d (%d%%)" % (tot[c], 100 * tot[c] / max(1, totrec)))
                             for c in range(1, len(langs))))
        lines.append("")
        lines.append("'Done' means the cell is filled AND differs from the source text.")
        lines.append("A cell that merely repeats the English source counts as untranslated.")
        self.report("Translation coverage", "\n".join(lines))

    # -- typo finder --------------------------------------------------------
    def accepted_path(self):
        return os.path.join(self.folder, "aowxink_accepted_words.json") if self.folder else None

    def load_accepted(self):
        p = self.accepted_path()
        if p and os.path.isfile(p):
            try:
                return {w.lower() for w in json.load(open(p, encoding="utf-8"))}
            except Exception:
                pass
        return set()

    def save_accepted(self, words):
        p = self.accepted_path()
        if p:
            try:
                json.dump(sorted(words), open(p, "w", encoding="utf-8"), indent=1)
            except Exception:
                pass

    def find_typos(self):
        if not self.books:
            return
        if SpellChecker is None:
            QMessageBox.warning(self, APP, "pyspellchecker is not installed.")
            return
        self.typo_dock.show()
        self.typo_dock.raise_()
        self.scan_typos()

    def scan_typos(self):
        if not self.books:
            return
        if SpellChecker is None:
            QMessageBox.warning(self, APP, "pyspellchecker is not installed.")
            return
        d = self.cb_typo_lang.currentData()
        if d is None:
            QMessageBox.information(
                self, APP,
                "No spelling dictionary is available for any language in this file.\n"
                "pyspellchecker bundles English, German, French, Spanish, Italian, "
                "Dutch and Russian.")
            return
        col, code = d
        sp = spell_checker(code)
        if sp is None:
            QMessageBox.information(self, APP, "No '%s' spelling dictionary is bundled." % code)
            return
        self.commit_editor()
        bi_cur = self.books.index(self.book)
        hits = scan_language(self.books, col, sp, code == "en",
                             self.load_accepted(), only=bi_cur)
        self._typo_sp = sp                 # for lazy suggestions on click
        # a flagged word that also occurs in the English source column is a
        # game proper noun (Azrac, Syron, ...) left untranslated, not a typo.
        # Built once per loaded folder - it walks all 8 dictionaries.
        seed = set()
        if col != 0:
            if getattr(self, "_typo_seed", None) is None:
                self._typo_seed = set()
                for b in self.books:
                    for row in range(len(b.f.records)):
                        for w in extract_words(b.text(row, 0)):
                            self._typo_seed.add(w.lower())
            seed = self._typo_seed
        total = sum(len(v) for v in hits.values())

        def is_name(w):
            # a capitalised word used repeatedly is a character/place name -
            # real typos are nearly always one-offs
            return w.lower() in seed or (w[:1].isupper() and len(hits[w]) >= 3)

        typos = sorted((w for w in hits if not is_name(w)),
                       key=lambda k: (-len(hits[k]), k.lower()))
        names = sorted((w for w in hits if is_name(w)),
                       key=lambda k: (-len(hits[k]), k.lower()))
        self.typo_tree.clear()

        def add_group(title, words, colour, expand):
            if not words:
                return
            grp = QTreeWidgetItem(["%s  (%d)" % (title, len(words)), "", ""])
            grp.setData(0, Qt.UserRole, None)
            grp.setForeground(0, QBrush(QColor(colour)))
            f = grp.font(0)
            f.setBold(True)
            grp.setFont(0, f)
            for w in words:
                # suggestions are NOT computed here: SpellChecker.candidates()
                # can take seconds per word, which froze whole-scan runs.
                # goto_typo fills them in when a word is clicked.
                top = QTreeWidgetItem(["%s   (%d)" % (w, len(hits[w])), "", ""])
                top.setData(0, Qt.UserRole, ("word", w))
                top.setForeground(0, QBrush(QColor(colour)))
                for (bi, row, ctx) in hits[w]:
                    child = QTreeWidgetItem(["   " + ctx, "",
                                             "%s row %d" % (self.books[bi].name, row)])
                    child.setData(0, Qt.UserRole, ("hit", bi, row, col, w))
                    top.addChild(child)
                grp.addChild(top)
            self.typo_tree.addTopLevelItem(grp)
            grp.setExpanded(expand)

        add_group("Likely typos", typos, "#e8837f", True)
        add_group("Probable names", names, "#9fb8d8", False)
        self.typo_count.setText("%s: %d likely typo(s), %d probable name(s), %d occurrence(s)"
                                % (self.book.name, len(typos), len(names), total))
        self.status("Typo scan of %s (%s): %d likely typos, %d names set aside. "
                    "Click a word for suggestions, an occurrence to jump to it."
                    % (self.book.name, code, len(typos), len(names)))

    def goto_typo(self, item, _col=0):
        d = item.data(0, Qt.UserRole)
        if not d:
            return
        if d[0] == "word":
            if not item.text(1):
                # lazy suggestions: candidates() is too slow to run for every
                # word during the scan, but is fine one word at a time
                sp = getattr(self, "_typo_sp", None)
                if sp is not None:
                    QApplication.setOverrideCursor(Qt.WaitCursor)
                    try:
                        w = d[1]
                        sug = ", ".join(sorted(sp.candidates(w.lower()) or set())[:4])
                    except Exception:
                        sug = ""
                    finally:
                        QApplication.restoreOverrideCursor()
                    item.setText(1, sug or "(no suggestions)")
            item.setExpanded(not item.isExpanded())
            return
        _kind, bi, row, col, word = d
        book = self.books[bi]
        self.goto(book, row, col)
        if not self.proxy.mapFromSource(self.model.index(row, col)).isValid():
            # the row is hidden by the current filter - clear it and retry
            self.f_search.clear()
            self.cb_mode.setCurrentIndex(0)
            self.goto(book, row, col)
        self.status("'%s' - %s row %d" % (word, book.name, row))

    def typo_add_word(self):
        it = self.typo_tree.currentItem()
        d = it.data(0, Qt.UserRole) if it else None
        if not d or not self.folder:
            return
        word = d[1] if d[0] == "word" else d[4]
        words = self.load_accepted()
        words.add(word.lower())
        self.save_accepted(words)
        self.scan_typos()
        self.status("Added '%s' to aowxink_accepted_words.json" % word)

    def report(self, title, text):
        dlg = ChromeDialog(self)
        dlg.setWindowTitle(title)
        v = QVBoxLayout(dlg)
        te = QPlainTextEdit(text)
        te.setReadOnly(True)
        te.setStyleSheet("font-family:Consolas,monospace;")
        v.addWidget(te)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(dlg.reject)
        v.addWidget(bb)
        dlg.resize(860, 520)
        dlg.exec()

    def closeEvent(self, ev):
        self.commit_editor()
        if any(b.dirty for b in self.books):
            r = QMessageBox.question(self, APP, "Save changes before closing?",
                                     QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
            if r == QMessageBox.Cancel:
                ev.ignore()
                return
            if r == QMessageBox.Yes:
                self.save_all()
        ev.accept()


def selftest():
    out = []
    ok = True
    try:
        n = len(cyrillic.RU_MAP)
        out.append("cyrillic map: %d glyph slots" % n)
        ok &= n >= 66
        s = "Эпоха Чудес"
        b = cyrillic.encode(s, cyrillic.AOWX_RU_CODEC)
        back = cyrillic.decode(b, cyrillic.AOWX_RU_CODEC)
        out.append("russian round-trip: %r -> %s -> %r" % (s, b.hex(), back))
        ok &= (back == s)
        clash = cyrillic.check_clashes()
        out.append("glyph slots clashing with used text bytes: %d" % len(clash))
        ok &= not clash
    except Exception as e:
        out.append("cyrillic FAILED: %s" % e)
        ok = False
    try:
        f = MLDFile()
        out.append("codec import ok (MLDFile, Language, Record)")
    except Exception as e:
        out.append("codec FAILED: %s" % e)
        ok = False
    try:
        if SpellChecker is None:
            out.append("spellchecker: NOT BUNDLED")
            ok = False
        else:
            avail = [c for c in ("en", "de", "fr", "es", "it", "nl", "ru")
                     if spell_checker(c) is not None]
            out.append("spellchecker languages available: %s" % ", ".join(avail))
            ok &= all(c in avail for c in ("en", "de", "fr", "es"))
            en = spell_checker("en")
            flags = not spell_known("teh", en, True)
            brit = (spell_known("colour", en, True) and spell_known("organise", en, True)
                    and spell_known("centre", en, True))
            out.append("en: flags 'teh'=%s, accepts British colour/organise/centre=%s"
                       % (flags, brit))
            ok &= flags and brit
            if "ru" in avail:
                ru = spell_checker("ru")
                good = spell_known("привет", ru) and not spell_known("превет", ru)
                out.append("ru: knows Cyrillic 'привет', flags 'превет': %s" % good)
                ok &= good
            ws = extract_words("Teh &Wizard casts %s at\\nthe 3rd RUNE of %1 rune-lore")
            out.append("markup strip: %s" % ws)
            ok &= ws == ["Teh", "Wizard", "casts", "the"]
            fb = MLDFile()
            fb.languages = [Language(EnglishName=b"English", ISOLanguage=b"en"),
                            Language(EnglishName=b"German", ISOLanguage=b"de")]
            fb.records = [Record(Original=b"The teh wizard travelled",
                                 translations=[b"Der Zaubrer reist"])]
            book = Book("test", "", fb)
            h_en = scan_language([book], 0, en, True)
            h_de = scan_language([book], 1, spell_checker("de"))
            out.append("synthetic scan: en flags %s, de flags %s"
                       % (sorted(h_en), sorted(h_de)))
            ok &= sorted(h_en) == ["teh"] and "Zaubrer" in h_de
    except Exception as e:
        out.append("spellchecker FAILED: %s" % e)
        ok = False
    out.append("SELFTEST %s" % ("PASS" if ok else "FAIL"))
    report = "\n".join(out)
    try:
        print(report)
    except UnicodeEncodeError:
        # frozen windowed exe: stdout is cp1252 and chokes on the Cyrillic
        # test strings - the utf-8 report file below is the real output
        print(report.encode("ascii", "backslashreplace").decode("ascii"))
    try:
        import tempfile
        with open(os.path.join(tempfile.gettempdir(), "aowx_selftest_ink.txt"),
                  "w", encoding="utf-8") as fh:
            fh.write(report)
    except Exception:
        pass
    return 0 if ok else 1


def main():
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    app = QApplication(sys.argv)
    app.setApplicationName(APP)
    pin_dark(app)
    w = Main()
    # load behind the splash so the window opens already populated
    loaded = False
    for a in sys.argv[1:]:
        if os.path.isdir(a):
            w.load_folder(a)
            loaded = True
            break
    if not loaded:
        # reopen the Dict folder from the previous session automatically
        last = w.settings.value("last_folder", "")
        if last and os.path.isdir(last) and any(
                os.path.isfile(os.path.join(last, n + ".mld"))
                for n in DICT_FILES):
            w.load_folder(last)
    close_splash()
    w.showMaximized()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
