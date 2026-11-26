"""
AoWxGen - random map generator for Age of Wonders X.

GUI over the proven generate_map_v4 engine (the old console AoWxGen, v6.5),
in the same style as the other AoWx tools. Pick what to make on the left -
Random Map Batch, a Custom RNG Map built from a series of selections (size,
levels, players, terrain inversion, landmass, up to three combinable terrain
style presets with a strength dial), or Image to Map (drop a picture on the
window) - then Generate. Finished maps land in the game's Scenario\\Custom
folder, validated, with the seed stamped into the file name.
"""
from __future__ import annotations
import os, random, sys

from PySide6.QtCore import Qt, QSize, QSettings, QThread, Signal
from PySide6.QtGui import QAction, QFont, QIcon, QKeySequence, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QCheckBox, QComboBox, QPushButton, QFileDialog, QStatusBar,
    QToolBar, QStyle, QStackedWidget, QGroupBox, QSlider, QLineEdit,
    QPlainTextEdit, QGridLayout,
)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from aowxlib import mapgen                                          # noqa: E402
from aowxlib.gui import (MossBack, EMBLEM_PATH, VERSION,            # noqa: E402
                         CaptionedMainWindow, close_splash,
                         draw_emblem_centred, pin_dark, play_icon)

APP = "AoWxGen"
HERE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
IMG_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp")


class GenWorker(QThread):
    line = Signal(str)
    finished_all = Signal(int, int)

    def __init__(self, root, mode, params, parent=None):
        super().__init__(parent)
        self.root, self.mode, self.params = root, mode, params

    def run(self):
        out = self.line.emit
        ok = total = 0
        if self.mode == "batch":
            sizes = ("S", "S", "M", "M", "L", "L", "XL", "XL")
            total = len(sizes)
            for sz in sizes:
                seed = random.randrange(1_000_000)
                out("\n== %s map, seed %d\n" % (sz, seed))
                if mapgen.run_generator(self.root, seed, sz, out_cb=out,
                                        quiet_map=True):
                    if mapgen.finish_map(self.root,
                                         "Scenario/Custom/xGen6 %s.hsm" % sz,
                                         "xGen6 %s (seed %d).hsm" % (sz, seed),
                                         out_cb=out):
                        ok += 1
        elif self.mode == "custom":
            p = self.params
            total = 1
            seed = random.randrange(1_000_000)
            env = {"AOW_LEVELS": p["levels"], "AOW_XLEVEL": p["inversion"],
                   "AOW_LANDMASS": p["landmass"],
                   "AOW_TPRESET": ",".join(p["styles"]),
                   "AOW_TSTRENGTH": str(p["strength"])}
            out("\n== %s map, seed %d (levels=%s, inversion=%s, %s, %s str %d)\n"
                % (p["size"], seed, p["levels"], p["inversion"], p["landmass"],
                   "+".join(p["styles"]), p["strength"]))
            if mapgen.run_generator(self.root, seed, p["size"],
                                    players=p["players"], env=env, out_cb=out):
                tag = ("" if p["styles"] == ["classic"] else
                       " " + "+".join(t.capitalize() for t in p["styles"]))
                if mapgen.finish_map(self.root,
                                     "Scenario/Custom/xGen6 %s.hsm" % p["size"],
                                     "xGen6 %s%s (seed %d).hsm"
                                     % (p["size"], tag, seed), out_cb=out):
                    ok += 1
        else:                                            # image
            img = self.params["image"]
            base = os.path.splitext(os.path.basename(img))[0][:24]
            total = len(mapgen.SIZES)
            for sz in mapgen.SIZES:
                seed = random.randrange(1_000_000)
                out("\n== %s map from %s, seed %d\n" % (sz, base, seed))
                try:
                    ov = mapgen.image_override(self.root, img, sz)
                except Exception as ex:
                    out("image processing failed: %r\n" % ex)
                    break
                if mapgen.run_generator(self.root, seed, sz,
                                        env={"AOW_IMG_OVERRIDE": ov},
                                        out_cb=out, quiet_map=True):
                    if mapgen.finish_map(self.root,
                                         "Scenario/Custom/xImg6 %s.hsm" % sz,
                                         "xImg6 %s %s (seed %d).hsm"
                                         % (sz, base, seed), out_cb=out):
                        ok += 1
        self.finished_all.emit(ok, total)


class GenLog(QPlainTextEdit):
    """Output pane; shows the celtic emblem + a hint until the first run."""

    def __init__(self):
        super().__init__()
        self.setReadOnly(True)
        f = QFont("Consolas")
        f.setPointSize(9)
        self.setFont(f)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.setFrameShape(QPlainTextEdit.NoFrame)
        self.setStyleSheet("QPlainTextEdit { background: transparent; }")
        self.viewport().setAutoFillBackground(False)
        self.emblem = QPixmap(EMBLEM_PATH)

    def paintEvent(self, ev):
        # fully transparent: the MossBack behind stays visible under the
        # generator output, exactly like Bard's queue table
        if self.document().isEmpty():
            p = QPainter(self.viewport())
            vw, vh = self.viewport().width(), self.viewport().height()
            th = draw_emblem_centred(p, self.emblem, vw, vh)
            p.setPen(self.palette().placeholderText().color())
            f = p.font()
            f.setPointSize(12)
            p.setFont(f)
            p.drawText(0, (vh + th) // 2 + 6, vw, 60,
                       Qt.AlignHCenter | Qt.AlignTop,
                       "Choose your settings, then Generate (F5)")
            p.end()
        super().paintEvent(ev)

    def feed(self, txt):
        c = self.textCursor()
        c.movePosition(c.MoveOperation.End)
        self.setTextCursor(c)
        self.insertPlainText(txt)
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())


class Main(CaptionedMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("AoWx", "AoWxGen")
        self.worker = None
        self.setWindowTitle(APP)
        ico = os.path.join(HERE, "assets", "aowxgen.ico")
        if os.path.isfile(ico):
            self.setWindowIcon(QIcon(ico))
        self.resize(1080, 620)
        self.setAcceptDrops(True)

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

        self.act_gen = act("Generate", QStyle.SP_MediaPlay, self.generate,
                           "F5", "Generate map(s) with the chosen settings")
        self.act_gen.setIcon(play_icon())       # the stock icon is too dark
        act("Open maps folder", QStyle.SP_DirOpenIcon, self.open_out_dir,
            None, "Open Scenario\\Custom in Explorer")
        tb.addSeparator()
        tb.addWidget(QLabel(" Background: "))
        self.cb_theme = QComboBox()
        self.cb_theme.addItem("Moss", "moss")
        self.cb_theme.addItem("Stone", "stone")
        cur = self.settings.value("bg_theme", "moss")
        self.cb_theme.setCurrentIndex(max(0, self.cb_theme.findData(cur)))
        self.cb_theme.currentIndexChanged.connect(self.change_theme)
        tb.addWidget(self.cb_theme)
        ver = QLabel("   Version %s" % VERSION)
        ver.setStyleSheet("color:#888;")
        tb.addWidget(ver)

        # ---- left: the series of selections, on plain UI chrome ----
        form_host = QWidget()
        form_host.setAutoFillBackground(True)
        form_host.setFixedWidth(380)
        fv = QVBoxLayout(form_host)
        fv.setContentsMargins(10, 8, 10, 8)

        fv.addWidget(QLabel("<b>What would you like to make?</b>"))
        self.cb_mode = QComboBox()
        self.cb_mode.addItem("Random Map Batch", "batch")
        self.cb_mode.addItem("Custom RNG Map", "custom")
        self.cb_mode.addItem("Image to Map", "image")
        self.cb_mode.currentIndexChanged.connect(
            lambda i: self.stack.setCurrentIndex(i))
        fv.addWidget(self.cb_mode)

        self.stack = QStackedWidget()
        fv.addWidget(self.stack, 1)

        # batch page
        pg = QWidget()
        pv = QVBoxLayout(pg)
        lbl = QLabel("Creates two maps of each size (Small, Medium, Large, "
                     "Extra Large) using default random map generation "
                     "settings.")
        lbl.setWordWrap(True)
        pv.addWidget(lbl)
        pv.addStretch(1)
        self.stack.addWidget(pg)

        # custom page
        pg = QWidget()
        pv = QVBoxLayout(pg)
        fl = QFormLayout()
        self.cb_size = QComboBox()
        for k in mapgen.SIZES:
            self.cb_size.addItem(mapgen.SIZE_LABELS[k], k)
        self.cb_size.setCurrentIndex(1)
        fl.addRow("Map size:", self.cb_size)
        self.cb_levels = QComboBox()
        for k, label in mapgen.LEVELS:
            self.cb_levels.addItem(label, k)
        self.cb_levels.setCurrentIndex(2)
        fl.addRow("Map levels:", self.cb_levels)
        self.cb_players = QComboBox()
        self.cb_players.addItem("Random", None)
        for n in range(2, 13):
            self.cb_players.addItem(str(n), n)
        fl.addRow("Players:", self.cb_players)
        self.cb_inv = QComboBox()
        for k, label in mapgen.INVERSIONS:
            self.cb_inv.addItem(label.split(" - ")[0], k)
            self.cb_inv.setItemData(self.cb_inv.count() - 1, label,
                                    Qt.ToolTipRole)
        fl.addRow("Terrain inversion:", self.cb_inv)
        self.cb_lm = QComboBox()
        for k, label in mapgen.LANDMASSES:
            self.cb_lm.addItem(label.split(" - ")[0], k)
            self.cb_lm.setItemData(self.cb_lm.count() - 1, label,
                                   Qt.ToolTipRole)
        fl.addRow("Landmass:", self.cb_lm)
        pv.addLayout(fl)

        gb = QGroupBox("Terrain style (combine up to 3)")
        gv = QGridLayout(gb)
        self.style_checks = []
        for i, (k, label) in enumerate(mapgen.STYLES):
            cb = QCheckBox(label.split(" - ")[0])
            cb.setToolTip(label)
            cb.setProperty("style_key", k)
            cb.toggled.connect(self.style_toggled)
            gv.addWidget(cb, i // 2, i % 2)
            self.style_checks.append(cb)
        self.style_checks[0].setChecked(True)
        pv.addWidget(gb)

        srow = QHBoxLayout()
        srow.addWidget(QLabel("Style strength:"))
        self.sl_str = QSlider(Qt.Horizontal)
        self.sl_str.setRange(1, 9)
        self.sl_str.setValue(5)
        self.sl_str.setTickPosition(QSlider.TicksBelow)
        self.sl_str.setTickInterval(1)
        srow.addWidget(self.sl_str, 1)
        self.lbl_str = QLabel("5")
        self.sl_str.valueChanged.connect(lambda v: self.lbl_str.setText(str(v)))
        srow.addWidget(self.lbl_str)
        pv.addLayout(srow)
        self.sl_str.setEnabled(False)
        pv.addStretch(1)
        self.stack.addWidget(pg)

        # image page
        pg = QWidget()
        pv = QVBoxLayout(pg)
        lbl = QLabel("Turns a picture into playable maps - one of each size.\n\n"
                     "Drop an image on the window, or browse:")
        lbl.setWordWrap(True)
        pv.addWidget(lbl)
        irow = QHBoxLayout()
        self.ed_img = QLineEdit()
        self.ed_img.setReadOnly(True)
        self.ed_img.setPlaceholderText("no image chosen")
        irow.addWidget(self.ed_img, 1)
        b = QPushButton("Browse...")
        b.clicked.connect(self.browse_image)
        irow.addWidget(b)
        pv.addLayout(irow)
        pv.addStretch(1)
        self.stack.addWidget(pg)

        self.cb_mode.setCurrentIndex(1)
        self.stack.setCurrentIndex(1)

        # ---- right: log pane on the stone/moss backdrop ----
        self.mossw = MossBack(self.settings.value("bg_theme", "moss"))
        mv = QVBoxLayout(self.mossw)
        mv.setContentsMargins(8, 8, 8, 8)
        self.log = GenLog()
        mv.addWidget(self.log)

        central = QWidget()
        h = QHBoxLayout(central)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        h.addWidget(form_host)
        h.addWidget(self.mossw, 1)
        self.setCentralWidget(central)

        self.setStatusBar(QStatusBar())
        self.root = self.settings.value("game_root", "")
        if not mapgen.is_game_root(self.root):
            self.root = mapgen.find_game_root() or ""
        if self.root:
            self.settings.setValue("game_root", self.root)
            mapgen.ensure_templates(self.root, out_cb=None)
            self.status("AoWx install: %s   -   maps go to Scenario\\Custom"
                        % self.root)
        else:
            self.status("Could not find your AoWx folder - you will be asked "
                        "when generating.")

    # -- plumbing -----------------------------------------------------------
    def status(self, m):
        self.statusBar().showMessage(m)

    def change_theme(self):
        t = self.cb_theme.currentData()
        self.mossw.set_theme(t)
        self.settings.setValue("bg_theme", t)

    def style_toggled(self, on):
        src = self.sender()
        if on:
            key = src.property("style_key")
            if key == "classic":
                for cb in self.style_checks[1:]:
                    cb.setChecked(False)
            else:
                self.style_checks[0].setChecked(False)
                picked = [c for c in self.style_checks[1:] if c.isChecked()]
                if len(picked) > 3:
                    src.setChecked(False)
                    self.status("At most 3 style presets can be combined.")
        if not any(c.isChecked() for c in self.style_checks):
            self.style_checks[0].setChecked(True)
        if hasattr(self, "sl_str"):    # the ctor's setChecked fires this slot
            self.sl_str.setEnabled(not self.style_checks[0].isChecked())

    def picked_styles(self):
        keys = [c.property("style_key") for c in self.style_checks
                if c.isChecked()]
        return keys or ["classic"]

    # -- drag & drop (image mode) ------------------------------------------
    def dragEnterEvent(self, ev):
        if any(u.toLocalFile().lower().endswith(IMG_EXTS)
               for u in ev.mimeData().urls()):
            ev.acceptProposedAction()

    def dropEvent(self, ev):
        for u in ev.mimeData().urls():
            f = u.toLocalFile()
            if f.lower().endswith(IMG_EXTS):
                self.ed_img.setText(f)
                self.cb_mode.setCurrentIndex(2)
                ev.acceptProposedAction()
                return

    def browse_image(self):
        start = self.settings.value("img_dir", "")
        f, _ = QFileDialog.getOpenFileName(
            self, "Choose a picture", start,
            "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp);;All files (*.*)")
        if f:
            self.settings.setValue("img_dir", os.path.dirname(f))
            self.ed_img.setText(f)

    # -- game root / output -------------------------------------------------
    def need_root(self):
        while not mapgen.is_game_root(self.root):
            d = QFileDialog.getExistingDirectory(
                self, "Select your AoWx folder (the one with AoW.exe)")
            if not d:
                return False
            if mapgen.is_game_root(d):
                self.root = d
                self.settings.setValue("game_root", d)
                mapgen.ensure_templates(d, out_cb=self.log.feed)
            else:
                self.status("No Release\\Release.hss there - try again.")
        return True

    def open_out_dir(self):
        if mapgen.is_game_root(self.root):
            os.startfile(os.path.join(self.root, "Scenario", "Custom"))

    # -- generation ---------------------------------------------------------
    def generate(self):
        if self.worker and self.worker.isRunning():
            return
        if not self.need_root():
            return
        mode = self.cb_mode.currentData()
        params = {}
        if mode == "custom":
            params = dict(size=self.cb_size.currentData(),
                          levels=self.cb_levels.currentData(),
                          players=self.cb_players.currentData(),
                          inversion=self.cb_inv.currentData(),
                          landmass=self.cb_lm.currentData(),
                          styles=self.picked_styles(),
                          strength=self.sl_str.value())
        elif mode == "image":
            img = self.ed_img.text()
            if not (img and os.path.isfile(img)):
                self.status("Pick an image first (browse or drop one on the "
                            "window).")
                return
            params = dict(image=img)
        self.act_gen.setEnabled(False)
        self.worker = GenWorker(self.root, mode, params, self)
        self.worker.line.connect(self.log.feed)
        self.worker.finished_all.connect(self.on_finished)
        self.worker.start()
        self.status("Generating...")

    def on_finished(self, ok, total):
        self.act_gen.setEnabled(True)
        self.status("Finished %d/%d map(s). They are in Scenario\\Custom, "
                    "playable from the game's Custom Scenario menu." % (ok, total))

    def closeEvent(self, ev):
        if self.worker and self.worker.isRunning():
            self.worker.wait(120000)
        ev.accept()


# ---------------------------------------------------------------------------
def selftest():
    out = []
    ok = True
    try:
        dd = mapgen.data_dir()
        need = ["generate_map_v4.py", "validate_map.py", "ab_masks.pkl",
                "decor_palette.pkl", "mtn_records.pkl", "obj_extra.pkl",
                "obj_records.pkl", "player_kit.pkl", "unit_pool.pkl",
                "veg_records.pkl"]
        for n in need:
            assert os.path.isfile(os.path.join(dd, n)), "missing %s in %s" % (n, dd)
        out.append("engine data present (%d files) in %s" % (len(need), dd))
        td = mapgen.templates_dir()
        for n in mapgen.TEMPLATE_NAMES.values():
            assert os.path.isfile(os.path.join(td, n)), "missing template " + n
        out.append("4 map templates present")
        for a in ("assets/aowxgen.ico", "assets/bard_moss.png",
                  "assets/bard_stone.png", "assets/bard_emblem.png"):
            assert os.path.isfile(os.path.join(HERE, a.replace("/", os.sep))), \
                "missing " + a
        out.append("assets present")
        from PIL import Image  # noqa: F401
        out.append("Pillow available (image mode works)")
        root = mapgen.find_game_root()
        out.append("game root: %s" % (root or "not found (asked at runtime)"))
        if root:
            import tempfile
            im = Image.new("RGB", (60, 40))
            for y in range(40):
                for x in range(60):
                    im.putpixel((x, y), (40, 90, 200) if x < 30 else (60, 160, 60))
            tp = os.path.join(tempfile.gettempdir(), "aowxgen_selftest.png")
            im.save(tp)
            ov = mapgen.image_override(root, tp, "S")
            assert os.path.isfile(ov)
            out.append("image->terrain override ok (%s)" % os.path.basename(ov))
            if "--selftest-gen" in sys.argv:
                lines = []
                okg = mapgen.run_generator(root, 99999, "S",
                                           out_cb=lines.append, quiet_map=True)
                assert okg, "generation failed:\n" + "".join(lines[-8:])
                dst = mapgen.finish_map(root, "Scenario/Custom/xGen6 S.hsm",
                                        "xGen6 S (SELFTEST).hsm",
                                        out_cb=lines.append)
                assert dst and "validation: OK" in "".join(lines)
                os.remove(dst)
                out.append("full generation round-trip ok (S map, validated, "
                           "removed)")
    except Exception as e:
        import traceback
        out.append("FAILED: %s\n%s" % (e, traceback.format_exc()))
        ok = False
    out.append("SELFTEST %s" % ("PASS" if ok else "FAIL"))
    report = "\n".join(out)
    print(report)
    try:
        import tempfile as tf
        with open(os.path.join(tf.gettempdir(), "aowx_selftest_gen.txt"),
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
    close_splash()
    w.showMaximized()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
