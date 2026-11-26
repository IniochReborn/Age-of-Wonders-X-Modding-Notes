"""
AoWxBard - music converter for Age of Wonders X.

Drop WAV/MP3 files onto the window (or click / Add files) and each becomes an
in-game .IT music track in the game's Songs folder. The in-game name and the
output file name are pregenerated from the source file and stay editable in
the table before converting. The two AoW-tuned mastering steps - the volume
balancer (-12 dB RMS soft-limited, matches the vanilla soundtrack's loudness)
and the AoW EQ (+6 dB low-shelf bass below ~120 Hz) - are on by default and
can be toggled per batch.

MP3 (and non-16-bit WAV) input needs ffmpeg on the machine; plain 16-bit PCM
WAV converts with no dependencies.
"""
from __future__ import annotations
import os, re, sys

from PySide6.QtCore import Qt, QSize, QSettings, QThread, Signal
from PySide6.QtGui import (QAction, QColor, QIcon, QKeySequence, QPainter,
                           QPixmap)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QCheckBox, QComboBox, QPushButton, QFileDialog, QMessageBox, QStatusBar,
    QToolBar, QTableWidget, QTableWidgetItem, QStyle, QHeaderView,
    QAbstractItemView,
)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from aowxlib import wav2it                                          # noqa: E402
from aowxlib.gui import (MossBack, EMBLEM_PATH, VERSION,            # noqa: E402
                         CaptionedMainWindow, close_splash,
                         draw_emblem_centred, pin_dark, play_icon)

APP = "AoWxBard"
HERE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
AUDIO_EXTS = (".wav", ".mp3")
BAD_FS = re.compile(r'[\\/:*?"<>|]')

COL_SRC, COL_NAME, COL_FILE, COL_STATUS = range(4)


def find_songs_dir():
    """The game's Songs folder, walking up from where the tool runs."""
    start = (os.path.dirname(sys.executable) if getattr(sys, "frozen", False)
             else os.path.dirname(os.path.abspath(__file__)))
    d = start
    for _ in range(5):
        songs = os.path.join(d, "Songs")
        if os.path.isdir(songs) and (os.path.isfile(os.path.join(d, "AoWx.exe"))
                                     or os.path.isfile(os.path.join(d, "AoW.exe"))):
            return songs
        d = os.path.dirname(d)
        if not d or os.path.dirname(d) == d:
            break
    return ""


class ConvertWorker(QThread):
    row_status = Signal(int, str)
    finished_all = Signal(int, int)

    def __init__(self, jobs, balance, eq, parent=None):
        super().__init__(parent)
        self.jobs = jobs                     # [(row, src, out_path, songname)]
        self.balance, self.eq = balance, eq

    def run(self):
        ok = 0
        for row, src, out_path, songname in self.jobs:
            self.row_status.emit(row, "converting...")
            try:
                existed = os.path.exists(out_path)
                n, gdb = wav2it.convert_file(src, out_path, songname,
                                             self.balance, self.eq)
                msg = "OK  %.1f MB" % (n / 1048576.0)
                if self.balance:
                    msg += "  (%+.1f dB)" % gdb
                if existed:
                    msg += "  (replaced)"
                self.row_status.emit(row, msg)
                ok += 1
            except Exception as e:
                self.row_status.emit(row, "FAIL: %s" % e)
        self.finished_all.emit(ok, len(self.jobs))


class SongTable(QTableWidget):
    """The queue table; transparent so the moss backdrop shows through, with a
    click-to-browse hint while empty."""
    browse_requested = Signal()

    def __init__(self):
        super().__init__(0, 4)
        self.setHorizontalHeaderLabels(
            ["Source file", "In-game name", "File name", "Status"])
        self.setAlternatingRowColors(False)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        h = self.horizontalHeader()
        # all columns grab-and-drag resizable; Status soaks up the remainder
        for c in (COL_SRC, COL_NAME, COL_FILE, COL_STATUS):
            h.setSectionResizeMode(c, QHeaderView.Interactive)
        h.setStretchLastSection(True)
        self._sized = False
        self.setStyleSheet(
            "QTableWidget { background: transparent; }"
            "QTableWidget::item { background: transparent; }")
        self.viewport().setAutoFillBackground(False)
        # the carved celtic emblem panel, centred on the drop area
        self.emblem = QPixmap(EMBLEM_PATH)

    def showEvent(self, ev):
        super().showEvent(ev)
        if not self._sized:
            self._sized = True
            saved = QSettings("AoWx", "AoWxBard").value("col_widths")
            try:
                widths = [int(v) for v in saved][:3]
                assert len(widths) == 3 and all(20 <= v <= 4000 for v in widths)
            except Exception:
                widths = None
            if widths:
                # the user's last widths are the default
                for c, w in zip((COL_SRC, COL_NAME, COL_FILE), widths):
                    self.setColumnWidth(c, w)
            else:
                # first run: Source = half the window; In-game name + File
                # name = ~75% of the rest; Status = the remainder
                w = self.viewport().width()
                self.setColumnWidth(COL_SRC, w // 2)
                rem = w - w // 2
                self.setColumnWidth(COL_NAME, int(rem * 0.40))
                self.setColumnWidth(COL_FILE, int(rem * 0.35))

    def save_widths(self):
        QSettings("AoWx", "AoWxBard").setValue(
            "col_widths", [self.columnWidth(c)
                           for c in (COL_SRC, COL_NAME, COL_FILE)])

    def paintEvent(self, ev):
        p = QPainter(self.viewport())
        vw, vh = self.viewport().width(), self.viewport().height()
        th = draw_emblem_centred(p, self.emblem, vw, vh)
        if self.rowCount() == 0:
            p.setPen(self.palette().placeholderText().color())
            f = p.font()
            f.setPointSize(13)
            p.setFont(f)
            th2 = th if not self.emblem.isNull() else 0
            p.drawText(0, (vh + th2) // 2 + 6, vw, 60, Qt.AlignHCenter | Qt.AlignTop,
                       "Drop WAV or MP3 files here, or click to browse")
        p.end()
        super().paintEvent(ev)

    def mouseReleaseEvent(self, ev):
        if self.rowCount() == 0 and ev.button() == Qt.LeftButton:
            self.browse_requested.emit()
            return
        super().mouseReleaseEvent(ev)


class Main(CaptionedMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("AoWx", "AoWxBard")
        self.worker = None
        self.setWindowTitle(APP)
        ico = os.path.join(HERE, "assets", "aowxbard.ico")
        if os.path.isfile(ico):
            self.setWindowIcon(QIcon(ico))
        self.resize(980, 560)
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

        act("Add files", QStyle.SP_DialogOpenButton, self.browse, "Ctrl+O",
            "Browse for WAV/MP3 files to convert (or drop them on the window)")
        act("Remove", QStyle.SP_TrashIcon, self.remove_selected, "Del",
            "Remove the selected rows from the queue")
        tb.addSeparator()
        self.act_convert = act("Convert all", QStyle.SP_MediaPlay,
                               self.convert_all, "F5",
                               "Convert every queued file into the Songs folder")
        self.act_convert.setIcon(play_icon())   # the stock icon is too dark
        tb.addSeparator()
        act("Open Songs folder", QStyle.SP_DirOpenIcon, self.open_out_dir,
            None, "Open the output folder in Explorer")
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

        # options row lives ABOVE the textured area, as plain UI chrome
        central = QWidget()
        v = QVBoxLayout(central)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        optw = QWidget()
        optw.setAutoFillBackground(True)
        opts = QHBoxLayout(optw)
        opts.setContentsMargins(9, 6, 9, 6)
        self.chk_balance = QCheckBox("Volume balancer")
        self.chk_balance.setChecked(True)
        self.chk_balance.setToolTip(
            "Raise the track's average loudness to the vanilla soundtrack's level\n"
            "(-12 dB RMS with a soft peak limiter). Off = keep the original dynamics.")
        self.chk_eq = QCheckBox("AoW EQ")
        self.chk_eq.setChecked(True)
        self.chk_eq.setToolTip(
            "+6 dB low-shelf bass boost below ~120 Hz, matching the weight of the\n"
            "game's tracker music, along with dynamic compression. Off = flat.")
        opts.addWidget(QLabel("Export options:"))
        opts.addWidget(self.chk_balance)
        opts.addWidget(self.chk_eq)
        opts.addStretch(1)
        opts.addWidget(QLabel("Output:"))
        self.lbl_out = QLabel("")
        self.lbl_out.setStyleSheet("color:#888;")
        opts.addWidget(self.lbl_out)
        b = QPushButton("Change...")
        b.clicked.connect(self.pick_out_dir)
        opts.addWidget(b)
        v.addWidget(optw)

        self.mossw = MossBack(self.settings.value("bg_theme", "moss"))
        mv = QVBoxLayout(self.mossw)
        mv.setContentsMargins(8, 8, 8, 8)
        self.table = SongTable()
        self.table.browse_requested.connect(self.browse)
        mv.addWidget(self.table)
        v.addWidget(self.mossw, 1)
        self.setCentralWidget(central)

        self.setStatusBar(QStatusBar())
        self.out_dir = (self.settings.value("out_dir", "") or find_songs_dir())
        if not os.path.isdir(self.out_dir):
            self.out_dir = ""
        self.update_out_label()
        if wav2it.find_ffmpeg():
            self.status("Drop WAV/MP3 files to queue them. Output: %s"
                        % (self.out_dir or "choose a folder"))
        else:
            self.status("ffmpeg not found: WAV (16-bit PCM) works, MP3 needs "
                        "ffmpeg installed.")

    # -- plumbing -----------------------------------------------------------
    def status(self, m):
        self.statusBar().showMessage(m)

    def change_theme(self):
        t = self.cb_theme.currentData()
        self.mossw.set_theme(t)
        self.settings.setValue("bg_theme", t)

    def update_out_label(self):
        self.lbl_out.setText(self.out_dir or "(not set)")
        self.lbl_out.setToolTip(self.out_dir)

    # -- drag & drop --------------------------------------------------------
    def dragEnterEvent(self, ev):
        if any(u.toLocalFile().lower().endswith(AUDIO_EXTS)
               for u in ev.mimeData().urls()):
            ev.acceptProposedAction()

    def dropEvent(self, ev):
        files = [u.toLocalFile() for u in ev.mimeData().urls()
                 if u.toLocalFile().lower().endswith(AUDIO_EXTS)]
        if files:
            self.add_files(files)
            ev.acceptProposedAction()

    # -- queue --------------------------------------------------------------
    def browse(self):
        start = self.settings.value("browse_dir", "")
        files, _ = QFileDialog.getOpenFileNames(
            self, "Choose music files", start,
            "Music (*.wav *.mp3);;All files (*.*)")
        if files:
            self.settings.setValue("browse_dir", os.path.dirname(files[0]))
            self.add_files(files)

    def queued_filenames(self):
        return {self.table.item(r, COL_FILE).text().upper()
                for r in range(self.table.rowCount())}

    def add_files(self, files):
        taken = self.queued_filenames()
        added = 0
        for f in files:
            stem = os.path.splitext(os.path.basename(f))[0]
            base = wav2it.short_name(stem)
            fname = base + ".IT"
            n = 2
            while fname.upper() in taken:
                fname = (base[:7] + str(n)) + ".IT"
                n += 1
            taken.add(fname.upper())
            row = self.table.rowCount()
            self.table.insertRow(row)
            src = QTableWidgetItem(os.path.basename(f))
            src.setToolTip(f)
            src.setData(Qt.UserRole, f)
            src.setFlags(src.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, COL_SRC, src)
            self.table.setItem(row, COL_NAME,
                               QTableWidgetItem(stem[:wav2it.NAME_MAX]))
            self.table.setItem(row, COL_FILE, QTableWidgetItem(fname))
            stat = QTableWidgetItem("queued")
            stat.setFlags(stat.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, COL_STATUS, stat)
            added += 1
        if added:
            self.status("%d file(s) queued. Edit the names if you like, then "
                        "Convert all (F5)." % added)

    def remove_selected(self):
        for r in sorted({i.row() for i in self.table.selectedIndexes()},
                        reverse=True):
            self.table.removeRow(r)

    # -- output dir ---------------------------------------------------------
    def pick_out_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Choose the Songs folder",
                                             self.out_dir or "")
        if d:
            self.out_dir = d
            self.settings.setValue("out_dir", d)
            self.update_out_label()

    def open_out_dir(self):
        if self.out_dir and os.path.isdir(self.out_dir):
            os.startfile(self.out_dir)

    # -- conversion ---------------------------------------------------------
    def convert_all(self):
        if self.worker and self.worker.isRunning():
            return
        if self.table.rowCount() == 0:
            self.status("Nothing queued - drop WAV/MP3 files first.")
            return
        if not self.out_dir or not os.path.isdir(self.out_dir):
            self.pick_out_dir()
            if not self.out_dir:
                return
        jobs = []
        for r in range(self.table.rowCount()):
            src = self.table.item(r, COL_SRC).data(Qt.UserRole)
            name = self.table.item(r, COL_NAME).text().strip()[:wav2it.NAME_MAX]
            fname = self.table.item(r, COL_FILE).text().strip()
            fname = BAD_FS.sub("", fname)
            if not fname:
                fname = wav2it.short_name(name or "SONG") + ".IT"
            if not fname.upper().endswith(".IT"):
                fname += ".IT"
            self.table.item(r, COL_NAME).setText(name)
            self.table.item(r, COL_FILE).setText(fname)
            jobs.append((r, src, os.path.join(self.out_dir, fname),
                         name or os.path.splitext(fname)[0]))
        dupes = len(jobs) - len({j[2].upper() for j in jobs})
        if dupes:
            QMessageBox.warning(self, APP, "%d rows share the same output file "
                                           "name - make them unique first." % dupes)
            return
        self.act_convert.setEnabled(False)
        self.worker = ConvertWorker(jobs, self.chk_balance.isChecked(),
                                    self.chk_eq.isChecked(), self)
        self.worker.row_status.connect(self.on_row_status)
        self.worker.finished_all.connect(self.on_finished)
        self.worker.start()
        self.status("Converting %d file(s)..." % len(jobs))

    def on_row_status(self, row, msg):
        if row < self.table.rowCount():
            self.table.item(row, COL_STATUS).setText(msg)

    def on_finished(self, ok, total):
        self.act_convert.setEnabled(True)
        self.status("Finished %d/%d. Restart the game to hear the new tracks "
                    "(they play from the Songs folder)." % (ok, total))

    def closeEvent(self, ev):
        self.table.save_widths()
        if self.worker and self.worker.isRunning():
            self.worker.wait(30000)
        ev.accept()


# ---------------------------------------------------------------------------
def selftest():
    import math as m
    import struct as st
    import tempfile
    out = []
    ok = True
    try:
        # synth a 2-second 440 Hz 16-bit PCM WAV
        sr = 44100
        n = sr * 2
        pcm = b"".join(st.pack("<h", int(12000 * m.sin(2 * m.pi * 440 * i / sr)))
                       for i in range(n))
        hdr = (b"RIFF" + st.pack("<I", 36 + len(pcm)) + b"WAVE"
               + b"fmt " + st.pack("<IHHIIHH", 16, 1, 1, sr, sr * 2, 2, 16)
               + b"data" + st.pack("<I", len(pcm)))
        td = tempfile.mkdtemp(prefix="aowxbard_")
        wav = os.path.join(td, "Test Song.wav")
        open(wav, "wb").write(hdr + pcm)

        outp = os.path.join(td, "TESTSONG.IT")
        size, gdb = wav2it.convert_file(wav, outp, "Test Song", True, True)
        d = open(outp, "rb").read()
        assert d[:4] == b"IMPM", "bad IT magic"
        assert d[4:4 + 9] == b"Test Song", "module name not embedded"
        out.append("convert: %d bytes, balancer %+.1f dB, magic+name ok"
                   % (size, gdb))
        size2, _ = wav2it.convert_file(wav, outp, "Test Song", False, False)
        out.append("toggles off: %d bytes (no balancer/EQ path ok)" % size2)
        assert wav2it.short_name("X My Fancy Track 01!") == "MYFANCYT"
        out.append("short_name ok")
        ff = wav2it.find_ffmpeg()
        out.append("ffmpeg: %s" % (ff or "NOT FOUND (WAV-only until installed)"))
        for a in ("assets/aowxbard.ico", "assets/bard_moss.png",
                  "assets/bard_stone.png", "assets/bard_emblem.png"):
            p = os.path.join(HERE, a.replace("/", os.sep))
            assert os.path.isfile(p), "missing " + a
        out.append("assets present (icon, moss + stone backgrounds, emblem)")
    except Exception as e:
        import traceback
        out.append("FAILED: %s\n%s" % (e, traceback.format_exc()))
        ok = False
    out.append("SELFTEST %s" % ("PASS" if ok else "FAIL"))
    report = "\n".join(out)
    print(report)
    try:
        import tempfile as tf
        with open(os.path.join(tf.gettempdir(), "aowx_selftest_bard.txt"),
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
    files = [a for a in sys.argv[1:]
             if a.lower().endswith(AUDIO_EXTS) and os.path.isfile(a)]
    if files:
        w.add_files(files)
    close_splash()
    w.showMaximized()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
