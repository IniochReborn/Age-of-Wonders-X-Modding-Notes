"""
AoWxImg - image library (.ILB) editor, a modern replacement for ILB Maker.

Every image parameter stays visible and editable; adding images is one click
because new images inherit the library's own settings by default.
"""
from __future__ import annotations
import os, sys, io, json, traceback

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import (QAction, QImage, QPixmap, QIcon, QColor, QKeySequence,
                           QPainter, QPalette)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QSplitter, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QComboBox, QSpinBox, QLineEdit,
    QPushButton, QFileDialog, QMessageBox, QGroupBox, QScrollArea, QCheckBox,
    QDialog, QDialogButtonBox, QRadioButton, QColorDialog, QStatusBar, QToolBar,
    QPlainTextEdit, QListWidget, QListWidgetItem, QStyle,
)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from aowxlib import ilb, presets                                    # noqa: E402
from aowxlib.gui import (EMBLEM_PATH, FAINT, VERSION,               # noqa: E402
                         CaptionedMainWindow, close_splash, draw_backdrop,
                         draw_emblem_centred, draw_hint_under, pin_dark)

try:
    from PIL import Image as PILImage
except ImportError:
    PILImage = None

APP = "AoWxImg"
HERE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
CHECKER = (0x30, 0x30, 0x34), (0x3a, 0x3a, 0x40)


class Settings:
    """Remembers separate folders for opening, importing and exporting.

    Exporting to the desktop should never move the 'open a library' dialog out
    of the game folder, which is what made the old tool tedious.
    """
    KEYS = ("lib_dir", "import_dir", "export_dir")
    OPTS = ("bg_theme",)                # plain values, not folder paths

    def __init__(self):
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        self.path = os.path.join(base, "AoWxTools", "aowximg.json")
        self.data = {k: "" for k in self.KEYS + self.OPTS}
        try:
            with open(self.path, encoding="utf-8") as fh:
                self.data.update({k: v for k, v in json.load(fh).items()
                                  if k in self.KEYS + self.OPTS})
        except Exception:
            pass

    def get_opt(self, key, default=""):
        return self.data.get(key) or default

    def set_opt(self, key, value):
        if self.data.get(key) != value:
            self.data[key] = value
            self.save()

    def get(self, key):
        d = self.data.get(key) or ""
        return d if os.path.isdir(d) else ""

    def set(self, key, path):
        if not path:
            return
        d = path if os.path.isdir(path) else os.path.dirname(path)
        if d and self.data.get(key) != d:
            self.data[key] = d
            self.save()

    def save(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as fh:
                json.dump(self.data, fh, indent=1)
        except Exception:
            pass


def rec_to_qimage(lib, rec):
    w, h, rows = ilb.decode_record(lib, rec)
    if w <= 0 or h <= 0:
        return None
    img = QImage(w, h, QImage.Format_ARGB32)
    for y in range(h):
        row = rows[y]
        for x in range(w):
            r, g, b, a = row[x]
            img.setPixelColor(x, y, QColor(r, g, b, a))
    return img


def checkerboard(pix: QPixmap, cell=8):
    out = QPixmap(pix.size())
    out.fill(QColor(*CHECKER[0]))
    p = QPainter(out)
    c2 = QColor(*CHECKER[1])
    for y in range(0, pix.height(), cell):
        for x in range(0, pix.width(), cell):
            if (x // cell + y // cell) % 2:
                p.fillRect(x, y, cell, cell, c2)
    p.drawPixmap(0, 0, pix)
    p.end()
    return out


class AddImagesDialog(QDialog):
    """Choose how new images get their parameters - this is the whole point."""

    def __init__(self, lib, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add images")
        self.lib = lib
        self.files = []
        v = QVBoxLayout(self)

        self.list = QListWidget()
        self.list.setMinimumHeight(120)
        v.addWidget(QLabel("Files to add (in order):"))
        v.addWidget(self.list)
        hb = QHBoxLayout()
        b = QPushButton("Choose files...")
        b.clicked.connect(self.pick)
        hb.addWidget(b)
        hb.addStretch(1)
        v.addLayout(hb)

        gb = QGroupBox("Parameters for the new images")
        gv = QVBoxLayout(gb)
        sig, share, distinct, total = presets.library_profile(lib)
        self.rb_match = QRadioButton()
        if sig is not None:
            self.rb_match.setText(
                "Match this library  -  %s, %s   (%.0f%% of its %d images use this)"
                % (ilb.TYPE_NAMES.get(sig[0], sig[0]),
                   "sub%d" % sig[1] if sig[1] is not None else "?", share * 100, total))
        else:
            self.rb_match.setText("Match this library (library is empty)")
            self.rb_match.setEnabled(False)
        self.rb_match.setChecked(sig is not None)
        gv.addWidget(self.rb_match)

        hb2 = QHBoxLayout()
        self.rb_preset = QRadioButton("Use preset:")
        self.rb_preset.setChecked(sig is None)
        self.cb_preset = QComboBox()
        for k, p in presets.PRESETS.items():
            cw, ch = p["canvas"]
            self.cb_preset.addItem(
                "%s  -  %s%s" % (p["label"], p["depth"],
                                 ("  %dx%d" % (cw, ch)) if cw else ""), k)
        hb2.addWidget(self.rb_preset)
        hb2.addWidget(self.cb_preset, 1)
        gv.addLayout(hb2)

        hb3 = QHBoxLayout()
        hb3.addWidget(QLabel("Transparent colour:"))
        self.btn_colour = QPushButton()
        self.transparent = (255, 0, 255)
        self._paint_colour()
        self.btn_colour.clicked.connect(self.pick_colour)
        hb3.addWidget(self.btn_colour)
        hb3.addWidget(QLabel("(pixels of this colour, and alpha<50%, become transparent)"))
        hb3.addStretch(1)
        gv.addLayout(hb3)

        self.chk_compact = QCheckBox("Append after the last used slot (otherwise fill empty slots first)")
        self.chk_compact.setChecked(True)
        gv.addWidget(self.chk_compact)
        v.addWidget(gb)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self.resize(720, 420)

    def _paint_colour(self):
        r, g, b = self.transparent
        self.btn_colour.setStyleSheet(
            "background:rgb(%d,%d,%d); min-width:56px; min-height:20px;" % (r, g, b))
        self.btn_colour.setText("#%02X%02X%02X" % (r, g, b))

    def pick_colour(self):
        c = QColorDialog.getColor(QColor(*self.transparent), self, "Transparent colour")
        if c.isValid():
            self.transparent = (c.red(), c.green(), c.blue())
            self._paint_colour()

    def pick(self):
        start = ""
        p = self.parent()
        if p is not None and hasattr(p, "settings"):
            start = p.settings.get("import_dir")
        fs, _ = QFileDialog.getOpenFileNames(
            self, "Choose images", start,
            "Images (*.png *.bmp *.gif *.jpg *.jpeg *.tga);;All files (*)")
        if fs and p is not None and hasattr(p, "settings"):
            p.settings.set("import_dir", fs[0])
        if fs:
            self.files = list(fs)
            self.list.clear()
            for f in self.files:
                self.list.addItem(os.path.basename(f))

    def make_record(self, name):
        if self.rb_match.isChecked() and self.rb_match.isEnabled():
            return presets.match_library(self.lib, name)
        return presets.apply_preset(self.cb_preset.currentData(), name)


class PropertyPanel(QWidget):
    """Every ILB field, visible and editable."""

    def __init__(self, main):
        super().__init__()
        self.main = main
        self.rec = None
        self._loading = False
        form = QFormLayout(self)
        form.setLabelAlignment(Qt.AlignRight)

        self.name = QLineEdit()
        self.name.editingFinished.connect(lambda: self.push("name", self.name.text()))
        form.addRow("Name", self.name)

        self.type = QComboBox()
        for t in (1, 2, 3, 16, 17, 18, 22):
            self.type.addItem("%s (0x%02X)" % (ilb.TYPE_NAMES[t], t), t)
        self.type.currentIndexChanged.connect(self.change_type)
        form.addRow("Image type", self.type)

        self.sub = QComboBox()
        self.sub.addItem("SubType 2 - no blend fields", 2)
        self.sub.addItem("SubType 3 - blend fields present", 3)
        self.sub.currentIndexChanged.connect(
            lambda: self.push("info", self.sub.currentData(), True))
        form.addRow("Sub type", self.sub)

        self.load = QComboBox()
        for k, v in ilb.LOAD_MODES.items():
            self.load.addItem(v, k)
        self.load.currentIndexChanged.connect(
            lambda: self.push("loadMode", self.load.currentData()))
        form.addRow("Load mode", self.load)

        self.show = QComboBox()
        for k, v in ilb.SHOW_MODES.items():
            self.show.addItem(v, k)
        self.show.currentIndexChanged.connect(self.push_draw)
        form.addRow("Show mode", self.show)

        self.blend = QComboBox()
        for k, v in ilb.BLEND_MODES.items():
            self.blend.addItem(v, k)
        self.blend.currentIndexChanged.connect(self.push_draw)
        form.addRow("Blend mode", self.blend)

        self.blendval = QSpinBox()
        self.blendval.setRange(0, 100)
        self.blendval.valueChanged.connect(
            lambda v: self.push("blendValue", v))
        form.addRow("Blend value %", self.blendval)

        self.clipx = QComboBox()
        self.clipx.setEditable(True)
        for k, v in ilb.CLIPX_NAMES.items():
            self.clipx.addItem("%s  (0x%06X)" % (v, k), k)
        self.clipx.currentIndexChanged.connect(
            lambda: self.push("clip_x", self.clipx.currentData()))
        form.addRow("clip_x hack", self.clipx)

        self.inst = QSpinBox()
        self.inst.setRange(0, 1 << 30)
        self.inst.valueChanged.connect(lambda v: self.push("sub", v))
        form.addRow("Instance no.", self.inst)

        self.shx = QSpinBox()
        self.shx.setRange(-30000, 30000)
        self.shx.valueChanged.connect(lambda v: self.push("xs", ilb.u32(v)))
        form.addRow("Shift X", self.shx)
        self.shy = QSpinBox()
        self.shy.setRange(-30000, 30000)
        self.shy.valueChanged.connect(lambda v: self.push("ys", ilb.u32(v)))
        form.addRow("Shift Y", self.shy)

        self.pal = QSpinBox()
        self.pal.setRange(0, 15)
        self.pal.valueChanged.connect(lambda v: self.push("pal", v))
        form.addRow("Palette #", self.pal)

        self.transp = QLineEdit()
        self.transp.editingFinished.connect(self.push_transp)
        form.addRow("Transparent", self.transp)

        self.info_lbl = QLabel("-")
        self.info_lbl.setWordWrap(True)
        self.info_lbl.setStyleSheet("color:#888;")
        form.addRow("Stored", self.info_lbl)

    # -- populate -----------------------------------------------------------
    def load_record(self, lib, rec):
        self._loading = True
        self.rec = rec
        self.lib = lib
        en = rec is not None
        for w in (self.name, self.type, self.sub, self.load, self.show, self.blend,
                  self.blendval, self.clipx, self.inst, self.shx, self.shy,
                  self.pal, self.transp):
            w.setEnabled(en)
        if not en:
            self._loading = False
            return
        self.name.setText(rec.get("name", ""))
        self._set_data(self.type, rec["type"])
        self._set_data(self.sub, rec.get("info", 3))
        self._set_data(self.load, rec.get("loadMode", 1))
        eight = rec.is_8bit
        has_blend = (not eight) and rec.get("info") == 3
        for w in (self.show, self.blend, self.blendval):
            w.setEnabled(has_blend)
        if has_blend:
            self._set_data(self.show, rec.show_mode or 0)
            self._set_data(self.blend, rec.blend_mode or 0)
            self.blendval.setValue(rec.get("blendValue", 0) or 0)
        self.clipx.setEnabled(rec["type"] in ilb.TYPES_WITH_CLIPX)
        if rec["type"] in ilb.TYPES_WITH_CLIPX:
            self._set_data(self.clipx, rec.get("clip_x", 0))
        self.pal.setEnabled(eight)
        if eight:
            self.pal.setValue(rec.get("pal", 0))
        self.inst.setValue(rec.get("sub", 0))
        self.shx.setValue(ilb.s32(rec.get("xs", 0)))
        self.shy.setValue(ilb.s32(rec.get("ys", 0)))
        t = rec.get("transp")
        self.transp.setEnabled(rec["type"] in ilb.TYPES_WITH_CLIPBOX)
        self.transp.setText("" if t is None else ("%d" % t if eight else "0x%04X" % (t & 0xFFFF)))
        self.info_lbl.setText(
            "%dx%d px, clip %dx%d at (%d,%d), %d bytes%s"
            % (rec.get("w", 0), rec.get("h", 0),
               ilb.s32(rec.get("cw", 0)), ilb.s32(rec.get("ch", 0)),
               ilb.s32(rec.get("cx", 0)), ilb.s32(rec.get("cy", 0)),
               rec.get("size", 0), "  [BLANK]" if rec.blank else ""))
        self._loading = False

    @staticmethod
    def _set_data(combo, val):
        i = combo.findData(val)
        if i >= 0:
            combo.setCurrentIndex(i)
        elif combo.isEditable():
            combo.setEditText("0x%06X" % val)

    # -- write back ---------------------------------------------------------
    def push(self, key, value, relayout=False):
        if self._loading or self.rec is None:
            return
        self.rec[key] = value
        self.main.mark_dirty()
        self.main.refresh_row()
        if relayout:
            self.load_record(self.lib, self.rec)

    def push_draw(self):
        if self._loading or self.rec is None:
            return
        self.rec.set_draw(self.show.currentData(), self.blend.currentData())
        self.main.mark_dirty()
        self.main.refresh_row()

    def push_transp(self):
        if self._loading or self.rec is None:
            return
        t = self.transp.text().strip()
        try:
            v = int(t, 16) if t.lower().startswith("0x") else int(t)
        except ValueError:
            return
        self.rec["transp"] = v
        self.main.mark_dirty()
        self.main.refresh_row()

    def change_type(self):
        if self._loading or self.rec is None:
            return
        new = self.type.currentData()
        old = self.rec["type"]
        if new == old:
            return
        self.rec["type"] = new
        # add/remove the fields that type implies, keeping existing values
        if new in ilb.TYPES_8BIT:
            self.rec.setdefault("unkB", 0)
            self.rec.setdefault("pal", 0)
            self.rec.pop("pixFmt", None)
        else:
            self.rec["pixFmt"] = ilb.PIXFMT_565
            if self.rec.get("info") == 3:
                self.rec.setdefault("drawMode", 0x0100)
                self.rec.setdefault("blendValue", 0)
        if new in ilb.TYPES_WITH_CLIPBOX:
            for k, d in (("cw", self.rec.get("w", 0)), ("ch", self.rec.get("h", 0)),
                         ("cx", 0), ("cy", 0), ("transp", 0)):
                self.rec.setdefault(k, d)
        if new in ilb.TYPES_WITH_CLIPX:
            self.rec.setdefault("clip_x", 0)
        QMessageBox.information(
            self, APP,
            "Image type changed to %s.\n\nThe stored pixel bytes are still in the old "
            "encoding - re-import the picture for this slot to re-encode it."
            % ilb.TYPE_NAMES[new])
        self.main.mark_dirty()
        self.main.refresh_row()
        self.load_record(self.lib, self.rec)


class LibTree(QTreeWidget):
    """The image table. The moss/stone backdrop carries the emblem + a hint
    while no library is open, then stays barely visible behind the rows; the
    alternating row shading is kept via a translucent alternate colour."""

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

    def paintEvent(self, ev):
        p = QPainter(self.viewport())
        vw, vh = self.viewport().width(), self.viewport().height()
        pal = QApplication.palette()
        loaded = self.main.lib is not None
        p.fillRect(0, 0, vw, vh, pal.base() if loaded else pal.window())
        draw_backdrop(p, vw, vh, self.main.bg_theme, FAINT if loaded else None)
        if not loaded:
            th = draw_emblem_centred(p, self.emblem, vw, vh)
            draw_hint_under(p, pal, vw, vh, th,
                            "Click to open an .ILB image library (Ctrl+O)")
        p.end()
        super().paintEvent(ev)

    def mouseReleaseEvent(self, ev):
        # Bard-style: while no library is open the emblem pane is one big
        # "open" button
        if self.main.lib is None and ev.button() == Qt.LeftButton:
            self.main.open()
            return
        super().mouseReleaseEvent(ev)


class PreviewPane(QLabel):
    """Preview label with the moss/stone backdrop behind the checkerboarded
    image."""

    def __init__(self, main, text=""):
        super().__init__(text)
        self.main = main
        self.setStyleSheet("background: transparent;")

    def paintEvent(self, ev):
        p = QPainter(self)
        p.fillRect(self.rect(), QApplication.palette().window())
        draw_backdrop(p, self.width(), self.height(), self.main.bg_theme)
        p.end()
        super().paintEvent(ev)


class Main(CaptionedMainWindow):
    COLS = ["#", "Inst", "Name", "Size", "Clip", "Type", "Sub", "Load",
            "Show", "Blend", "Val", "clip_x", "Transp", "Bytes"]

    def __init__(self):
        super().__init__()
        self.lib = None
        self.dirty = False
        self.path = None
        self.settings = Settings()
        self.bg_theme = self.settings.get_opt("bg_theme", "moss")
        self.last_zoom = 4                 # what Ctrl+Space enlarges to
        self.setWindowTitle(APP)
        ico = os.path.join(HERE, "assets", "aowximg.ico")
        if os.path.isfile(ico):
            self.setWindowIcon(QIcon(ico))
        self.resize(1360, 780)

        tb = QToolBar("Main")
        tb.setIconSize(QSize(16, 16))
        self.addToolBar(tb)
        st = self.style()

        def act(text, icon, slot, shortcut=None, tip=None):
            a = QAction(st.standardIcon(icon), text, self)
            a.triggered.connect(slot)
            if shortcut:
                a.setShortcut(QKeySequence(shortcut))
            a.setToolTip(tip or text)
            tb.addAction(a)
            return a

        act("Open", QStyle.SP_DialogOpenButton, self.open, "Ctrl+O")
        act("Save", QStyle.SP_DialogSaveButton, self.save, "Ctrl+S")
        act("Save As", QStyle.SP_DriveFDIcon, self.save_as)
        tb.addSeparator()
        act("Add images", QStyle.SP_FileDialogNewFolder, self.add_images, "Ins",
            "Add pictures, inheriting this library's own settings")
        act("Remove", QStyle.SP_TrashIcon, self.remove_selected, "Del")
        act("Re-import", QStyle.SP_BrowserReload, self.reimport,
            "Replace the selected slot's picture, keeping its parameters")
        tb.addSeparator()
        act("Export", QStyle.SP_DialogSaveButton, self.export_selected,
            "Ctrl+E", "Export the selected image, choosing its name (Ctrl+E)")
        tb.addSeparator()
        self.act_zoom = QAction(st.standardIcon(QStyle.SP_FileDialogDetailedView),
                                "Enlarge preview", self)
        self.act_zoom.setCheckable(True)
        self.act_zoom.setShortcut(QKeySequence("Ctrl+Space"))
        self.act_zoom.setToolTip("Toggle between in-game size (1:1) and an enlarged "
                                 "preview  [Ctrl+Space]")
        self.act_zoom.toggled.connect(self.toggle_zoom)
        tb.addAction(self.act_zoom)
        act("Check", QStyle.SP_MessageBoxInformation, self.check_outliers,
            None, "List images whose settings differ from the rest of the library")
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
        self.tree = LibTree(self)
        self.tree.setColumnCount(len(self.COLS))
        self.tree.setHeaderLabels(self.COLS)
        self.tree.setRootIsDecorated(True)
        self.tree.setAlternatingRowColors(True)
        self.tree.setSelectionMode(QTreeWidget.ExtendedSelection)
        self.tree.currentItemChanged.connect(self.on_select)
        self.tree.setUniformRowHeights(True)
        split.addWidget(self.tree)

        right = QSplitter(Qt.Vertical)
        prev_box = QWidget()
        pv = QVBoxLayout(prev_box)
        pv.setContentsMargins(0, 0, 0, 0)
        pv.setSpacing(2)
        # scrollable, so a picture bigger than the pane is not silently clipped
        self.preview_scroll = QScrollArea()
        self.preview_scroll.setWidgetResizable(True)
        self.preview_scroll.setAlignment(Qt.AlignCenter)
        self.preview_scroll.setStyleSheet("background: transparent; border:none;")
        self.preview_scroll.viewport().setAutoFillBackground(False)
        self.preview = PreviewPane(self, "no image")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview_scroll.setWidget(self.preview)
        self.preview_scroll.setMinimumHeight(240)
        pv.addWidget(self.preview_scroll, 1)
        zrow = QHBoxLayout()
        zrow.addWidget(QLabel("Zoom"))
        self.cb_zoom = QComboBox()
        for label, val in (("Fit", "fit"), ("1:1 (in-game)", 1), ("2x", 2), ("3x", 3),
                           ("4x", 4), ("6x", 6), ("8x", 8), ("12x", 12)):
            self.cb_zoom.addItem(label, val)
        self.cb_zoom.setCurrentIndex(1)
        self.cb_zoom.currentIndexChanged.connect(self.on_zoom_changed)
        zrow.addWidget(self.cb_zoom)
        self.preview_note = QLabel("")
        self.preview_note.setStyleSheet("color:#888; font-size:11px;")
        zrow.addWidget(self.preview_note, 1)
        pv.addLayout(zrow)
        right.addWidget(prev_box)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.props = PropertyPanel(self)
        scroll.setWidget(self.props)
        right.addWidget(scroll)
        right.setSizes([260, 520])
        split.addWidget(right)
        split.setSizes([880, 480])
        self.setCentralWidget(split)

        self.setStatusBar(QStatusBar())
        self.status("Open an .ILB file to begin.")

    # -- helpers ------------------------------------------------------------
    def status(self, msg):
        self.statusBar().showMessage(msg)

    def change_theme(self):
        self.bg_theme = self.cb_theme.currentData()
        self.settings.set_opt("bg_theme", self.bg_theme)
        self.tree.viewport().update()
        self.preview.update()

    def mark_dirty(self):
        self.dirty = True
        self.update_title()

    def update_title(self):
        n = os.path.basename(self.path) if self.path else "(no file)"
        self.setWindowTitle("%s - %s%s" % (APP, n, " *" if self.dirty else ""))

    def current_record(self):
        it = self.tree.currentItem()
        if it is None:
            return None
        d = it.data(0, Qt.UserRole)
        return d[1] if d else None

    # -- file ---------------------------------------------------------------
    def open(self):
        f, _ = QFileDialog.getOpenFileName(self, "Open image library",
                                           self.settings.get("lib_dir"),
                                           "AoW image libraries (*.ilb *.ILB);;All files (*)")
        if f:
            self.settings.set("lib_dir", f)
            self.load(f)

    def load(self, path):
        try:
            self.lib = ilb.read(path)
        except Exception as e:
            QMessageBox.critical(self, APP, "Could not read:\n%s\n\n%s" % (path, e))
            return
        self.path = path
        self.dirty = False
        self.populate()
        sig, share, distinct, total = presets.library_profile(self.lib)
        self.status("%d images, %d palette(s), v%.1f  -  %d distinct parameter set(s), "
                    "dominant covers %.0f%%"
                    % (len(self.lib.images), len(self.lib.palettes), self.lib.version,
                       distinct, share * 100))
        self.update_title()

    def save(self):
        if not self.lib:
            return
        if not self.path:
            return self.save_as()
        try:
            n = ilb.save(self.lib, self.path)
        except Exception as e:
            QMessageBox.critical(self, APP, "Save failed:\n%s" % e)
            return
        self.dirty = False
        self.update_title()
        self.status("Wrote %s (%d bytes)" % (os.path.basename(self.path), n))

    def save_as(self):
        start = self.path or self.settings.get("lib_dir")
        f, _ = QFileDialog.getSaveFileName(self, "Save image library", start,
                                           "AoW image libraries (*.ilb)")
        if f:
            self.settings.set("lib_dir", f)
            self.path = f
            self.save()

    # -- table --------------------------------------------------------------
    def populate(self):
        self.tree.setUpdatesEnabled(False)
        self.tree.clear()
        for img in self.lib.images:
            if img.empty:
                it = QTreeWidgetItem(["%d" % img.id, "", "(empty slot)"])
                it.setForeground(2, QColor("#777"))
                it.setData(0, Qt.UserRole, None)
                self.tree.addTopLevelItem(it)
                continue
            for k, rec in enumerate(img.parts):
                row = self.row_values(img, rec, k)
                if k == 0:
                    it = QTreeWidgetItem(row)
                    it.setData(0, Qt.UserRole, (img, rec))
                    self.tree.addTopLevelItem(it)
                    parent = it
                else:
                    ch = QTreeWidgetItem(row)
                    ch.setData(0, Qt.UserRole, (img, rec))
                    parent.addChild(ch)
                    parent.setExpanded(True)
        for c in range(len(self.COLS)):
            self.tree.resizeColumnToContents(c)
        self.tree.setUpdatesEnabled(True)

    def row_values(self, img, rec, part=0):
        sm = rec.show_mode
        bm = rec.blend_mode
        cx = rec.get("clip_x")
        t = rec.get("transp")
        return [
            "%d" % img.id if part == 0 else "  layer %d" % part,
            str(rec.get("sub", 0)),
            rec.get("name", ""),
            "%dx%d" % (rec.get("w", 0), rec.get("h", 0)),
            "%dx%d" % (ilb.s32(rec.get("cw", 0)), ilb.s32(rec.get("ch", 0))),
            rec.type_name,
            str(rec.get("info", "")),
            ilb.LOAD_MODES.get(rec.get("loadMode"), "?"),
            ilb.SHOW_MODES.get(sm, "") if sm is not None else "",
            ilb.BLEND_MODES.get(bm, "") if bm is not None else "",
            str(rec.get("blendValue", "")) if rec.get("blendValue") is not None else "",
            ("0x%06X" % cx) if cx else ("" if cx is None else "0"),
            ("%d" % t if rec.is_8bit else "0x%04X" % (t & 0xFFFF)) if t is not None else "",
            str(rec.get("size", 0)),
        ]

    def refresh_row(self):
        it = self.tree.currentItem()
        d = it.data(0, Qt.UserRole) if it else None
        if not d:
            return
        img, rec = d
        part = img.parts.index(rec) if rec in img.parts else 0
        for i, v in enumerate(self.row_values(img, rec, part)):
            it.setText(i, v)

    def on_select(self, cur, _prev):
        d = cur.data(0, Qt.UserRole) if cur else None
        if not d:
            self.props.load_record(self.lib, None)
            self.preview.setText("empty slot")
            self.preview.setPixmap(QPixmap())
            return
        img, rec = d
        self.props.load_record(self.lib, rec)
        self.show_preview(rec)

    def toggle_zoom(self, on):
        """Ctrl+Space / toolbar button: flip between 1:1 and the last enlargement."""
        if on:
            want = self.last_zoom if self.last_zoom not in (1, "fit") else 4
        else:
            want = 1
        i = self.cb_zoom.findData(want)
        self.cb_zoom.setCurrentIndex(i if i >= 0 else 1)

    def on_zoom_changed(self):
        val = self.cb_zoom.currentData()
        if val != 1:
            self.last_zoom = val
        if self.act_zoom.isChecked() != (val != 1):
            self.act_zoom.blockSignals(True)
            self.act_zoom.setChecked(val != 1)
            self.act_zoom.blockSignals(False)
        self.refresh_preview()

    def refresh_preview(self):
        it = self.tree.currentItem()
        d = it.data(0, Qt.UserRole) if it else None
        if d:
            self.show_preview(d[1])

    def show_preview(self, rec):
        try:
            qi = rec_to_qimage(self.lib, rec)
        except Exception:
            qi = None
        if qi is None:
            self.preview.setText("no pixels")
            self.preview.setPixmap(QPixmap())
            self.preview_note.setText("")
            return
        pm = QPixmap.fromImage(qi)
        w0, h0 = pm.width(), pm.height()
        val = self.cb_zoom.currentData()
        if val == "fit":
            box = self.preview_scroll.viewport().size()
            fx = (box.width() - 8) / max(1, w0)
            fy = (box.height() - 8) / max(1, h0)
            f = max(0.05, min(fx, fy))
            pm = pm.scaled(max(1, int(w0*f)), max(1, int(h0*f)),
                           Qt.KeepAspectRatio,
                           Qt.FastTransformation if f >= 1 else Qt.SmoothTransformation)
            note = "fit to pane (%.0f%%)" % (f * 100)
        else:
            f = int(val)
            if f > 1:
                # nearest-neighbour: never invent pixels the game does not draw
                pm = pm.scaled(w0*f, h0*f, Qt.KeepAspectRatio, Qt.FastTransformation)
                note = "enlarged %dx  [Ctrl+Space back to 1:1]" % f
            else:
                note = "in-game size (1:1)  [Ctrl+Space to enlarge]"
        self.preview.setPixmap(checkerboard(pm))
        self.preview.resize(pm.size())
        self.preview.setMinimumSize(pm.size())
        self.preview_note.setText("%dx%d  -  %s" % (w0, h0, note))

    # -- editing ------------------------------------------------------------
    def add_images(self):
        if not self.lib:
            QMessageBox.information(self, APP, "Open a library first.")
            return
        if PILImage is None:
            QMessageBox.critical(self, APP, "Pillow is required to import pictures.")
            return
        dlg = AddImagesDialog(self.lib, self)
        if dlg.exec() != QDialog.Accepted or not dlg.files:
            return
        next_id = max([i.id for i in self.lib.images], default=-1) + 1
        added = 0
        for f in dlg.files:
            try:
                pil = PILImage.open(f)
                rec = dlg.make_record(os.path.basename(f))
                ilb.encode_image(self.lib, rec, pil, dlg.transparent)
                self.lib.images.append(ilb.Image(next_id, [rec]))
                next_id += 1
                added += 1
            except Exception as e:
                QMessageBox.warning(self, APP, "Failed on %s:\n%s" % (os.path.basename(f), e))
        if added:
            self.mark_dirty()
            self.populate()
            self.status("Added %d image(s)." % added)

    def reimport(self):
        rec = self.current_record()
        if rec is None:
            return
        f, _ = QFileDialog.getOpenFileName(self, "Replace picture",
                                           self.settings.get("import_dir"),
                                           "Images (*.png *.bmp *.gif *.jpg *.jpeg)")
        if not f:
            return
        self.settings.set("import_dir", f)
        try:
            pil = PILImage.open(f)
            t = rec.get("transp", 0)
            if rec.is_8bit:
                pal = self.lib.palette_rgb(rec.get("pal", 0))
                trgb = pal[t & 0xFF] if pal else (255, 0, 255)
            else:
                trgb = ilb._c565(t & 0xFFFF)
            ilb.encode_image(self.lib, rec, pil, trgb)
            rec["name"] = os.path.basename(f)
        except Exception as e:
            QMessageBox.critical(self, APP, "Import failed:\n%s" % e)
            return
        self.mark_dirty()
        self.refresh_row()
        self.on_select(self.tree.currentItem(), None)
        self.status("Re-imported %s" % os.path.basename(f))

    def remove_selected(self):
        items = self.tree.selectedItems()
        if not items or not self.lib:
            return
        drop = set()
        for it in items:
            d = it.data(0, Qt.UserRole)
            if d:
                drop.add(id(d[0]))
        if not drop:
            return
        if QMessageBox.question(self, APP, "Remove %d image(s)?" % len(drop)) != QMessageBox.Yes:
            return
        self.lib.images = [i for i in self.lib.images if id(i) not in drop]
        self.mark_dirty()
        self.populate()

    def export_selected(self):
        """One image -> a Save As dialog so you can name it.
        Several -> pick a folder once and they are written with their own names."""
        if not self.lib:
            return
        recs = []
        for it in self.tree.selectedItems():
            d = it.data(0, Qt.UserRole)
            if d:
                recs.append(d)
        if not recs:
            QMessageBox.information(self, APP, "Select the image(s) to export first.")
            return
        start = self.settings.get("export_dir")

        if len(recs) == 1:
            img, rec = recs[0]
            qi = rec_to_qimage(self.lib, rec)
            if qi is None:
                QMessageBox.warning(self, APP, "That slot has no pixels to export.")
                return
            base = os.path.splitext(rec.get("name") or "image")[0]
            suggested = os.path.join(start, "%s.png" % base) if start else "%s.png" % base
            f, _ = QFileDialog.getSaveFileName(
                self, "Export image", suggested,
                "PNG image (*.png);;Windows bitmap (*.bmp);;All files (*)")
            if not f:
                return
            if not os.path.splitext(f)[1]:
                f += ".png"
            if not qi.save(f):
                QMessageBox.warning(self, APP, "Could not write %s" % f)
                return
            self.settings.set("export_dir", f)
            self.status("Exported #%d to %s" % (img.id, f))
            return

        folder = QFileDialog.getExistingDirectory(self, "Export %d images to folder" % len(recs),
                                                  start)
        if not folder:
            return
        self.settings.set("export_dir", folder)
        n = 0
        for img, rec in recs:
            qi = rec_to_qimage(self.lib, rec)
            if qi is None:
                continue
            base = os.path.splitext(rec.get("name") or "image")[0]
            if qi.save(os.path.join(folder, "%03d_%s.png" % (img.id, base))):
                n += 1
        self.status("Exported %d image(s) to %s" % (n, folder))

    def check_outliers(self):
        if not self.lib:
            return
        out = presets.outliers(self.lib)
        sig, share, distinct, total = presets.library_profile(self.lib)
        if not out:
            QMessageBox.information(
                self, APP, "All %d images share the same parameter set." % total)
            return
        lines = ["%d of %d images differ from the library's dominant settings "
                 "(%.0f%% share those):\n" % (len(out), total, share * 100)]
        for img, rec in out[:60]:
            lines.append("  #%-4d %-22s %-22s sub%s  draw=%s  clip_x=%s"
                         % (img.id, rec.get("name", "")[:22], rec.type_name,
                            rec.get("info"), rec.get("drawMode"), rec.get("clip_x")))
        if len(out) > 60:
            lines.append("  ... and %d more" % (len(out) - 60))
        dlg = QDialog(self)
        dlg.setWindowTitle("Parameter check")
        v = QVBoxLayout(dlg)
        te = QPlainTextEdit("\n".join(lines))
        te.setReadOnly(True)
        te.setStyleSheet("font-family:Consolas,monospace;")
        v.addWidget(te)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(dlg.reject)
        bb.accepted.connect(dlg.accept)
        v.addWidget(bb)
        dlg.resize(760, 460)
        dlg.exec()

    def closeEvent(self, ev):
        if self.dirty:
            r = QMessageBox.question(self, APP, "Save changes before closing?",
                                     QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
            if r == QMessageBox.Cancel:
                ev.ignore()
                return
            if r == QMessageBox.Yes:
                self.save()
        ev.accept()


def selftest():
    """--selftest : verify the frozen build has everything it needs."""
    out = []
    ok = True
    out.append("Pillow: %s" % ("yes" if PILImage else "NO - image import disabled"))
    ok &= PILImage is not None
    try:
        n = len(presets.PRESETS)
        out.append("presets: %d" % n)
        ok &= n > 0
    except Exception as e:
        out.append("presets FAILED: %s" % e)
        ok = False
    try:
        lib = ilb.IlbLibrary()
        rec = presets.apply_preset("item_icon", "t.bmp")
        img = PILImage.new("RGBA", (16, 16), (255, 0, 0, 255))
        ilb.encode_image(lib, rec, img, (255, 0, 255))
        lib.images.append(ilb.Image(0, [rec]))
        blob = ilb.write(lib)
        lib2 = ilb.read(blob)
        w, h, rows = ilb.decode_record(lib2, lib2.images[0].parts[0])
        solid = sum(1 for r in rows for p in r if p[3] > 0)
        out.append("codec round-trip: %d bytes, %dx%d, %d opaque px" % (len(blob), w, h, solid))
        ok &= solid == 256
    except Exception as e:
        out.append("codec FAILED: %s" % e)
        ok = False
    out.append("SELFTEST %s" % ("PASS" if ok else "FAIL"))
    report = "\n".join(out)
    print(report)
    try:
        import tempfile
        with open(os.path.join(tempfile.gettempdir(), "aowx_selftest_img.txt"),
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
    if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
        w.load(sys.argv[1])
    close_splash()
    w.showMaximized()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()


