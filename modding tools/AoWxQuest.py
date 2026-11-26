"""
AoWxQuest - campaign editor, a modern replacement for AoWCGE's campaign side.

Fixes the three things that made AoWCGE painful:
  * nodes are dragged on the map instead of typing X/Y by hand
  * a branch tree with per-branch visibility toggles unclutters the map
    (a real campaign puts ~139 nodes on one 640x480 backdrop; at a 32px icon
     96% of them overlap something and the buried ones cannot be clicked)
  * story text is spell-checked with red underlining
"""
from __future__ import annotations
import os, sys, re, json

from PySide6.QtCore import Qt, QRectF, QPointF, QSize, Signal, QTimer, QSettings
from PySide6.QtGui import (QAction, QPixmap, QImage, QColor, QPen, QBrush, QPainter,
                           QFont, QKeySequence, QTextCharFormat, QSyntaxHighlighter,
                           QPainterPath, QIcon, QTextCursor, QPalette)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QSplitter, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit, QSpinBox, QComboBox,
    QPushButton, QFileDialog, QMessageBox, QGroupBox, QTextEdit, QTabWidget,
    QGraphicsView, QGraphicsScene, QGraphicsItem, QGraphicsPixmapItem,
    QGraphicsEllipseItem, QGraphicsPathItem, QGraphicsSimpleTextItem,
    QToolBar, QStatusBar, QCheckBox, QDialog, QDialogButtonBox, QStyle,
    QListWidget, QListWidgetItem, QInputDialog, QMenu, QPlainTextEdit, QDockWidget,
)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from aowxlib import cam, ilb                                       # noqa: E402
from aowxlib.gui import (FAINT, VERSION, ChromeDialog, ChromePage,  # noqa: E402
                         CaptionedMainWindow, close_splash,
                         draw_backdrop, paint_chrome, pin_dark,
                         play_icon)

try:
    from spellchecker import SpellChecker
except ImportError:
    SpellChecker = None

APP = "AoWxQuest"
# when frozen by PyInstaller the bundled assets live in sys._MEIPASS
HERE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
MAP_W, MAP_H = 640, 480

COL_SCEN = QColor(70, 190, 90)
COL_SCEN_START = QColor(250, 205, 60)
COL_CA = QColor(215, 80, 80)
COL_NEXT = QColor(70, 200, 100)
COL_LINK = QColor(90, 150, 235)

UNDO_LIMIT = 60

# current moss/stone background theme, shared with widgets that paint it
# themselves (set by Main from its persisted setting)
BG = {"theme": "moss"}


def decode_to_pixmap(lib, rec):
    """Decode an ILB record straight into a QPixmap via a raw RGBA buffer.

    Book-page art is 272x372, so per-pixel QImage calls are far too slow.
    """
    w, h, rows = ilb.decode_record(lib, rec)
    if w <= 0 or h <= 0:
        return None
    buf = bytearray(w * h * 4)
    i = 0
    for row in rows:
        for r, g, b, a in row:
            buf[i] = r
            buf[i + 1] = g
            buf[i + 2] = b
            buf[i + 3] = a
            i += 4
    qi = QImage(bytes(buf), w, h, w * 4, QImage.Format_RGBA8888)
    return QPixmap.fromImage(qi.copy())


# ---------------------------------------------------------------------------
# book-page picture resolution
# ---------------------------------------------------------------------------
class ImageResolver:
    """Finds and decodes the ILB pictures used on campaign book pages.

    Retail campaigns reference them by bare filename (BPGen.ILB, Custom.ilb,
    ...) and every one of them lives in <game root>\\Int\\Scenes.
    """
    SUBDIRS = (os.path.join("Int", "Scenes"), "Int", os.path.join("Images", "Scenes"), "Images")

    def __init__(self):
        self.root = None
        self._libs = {}
        self._cache = {}

    def guess_root(self, cam_path):
        """A .cam normally sits in <root>\\X\\Campaign or <root>\\Scenario\\Campaign."""
        if not cam_path:
            return
        d = os.path.dirname(os.path.abspath(cam_path))
        for up in (2, 1, 3):
            cand = os.path.abspath(os.path.join(d, *([".."] * up)))
            if os.path.isdir(os.path.join(cand, "Int", "Scenes")):
                self.set_root(cand)
                return
        self.set_root(None)

    def set_root(self, root):
        if root != self.root:
            self._libs.clear()
            self._cache.clear()
        self.root = root

    def find(self, name):
        if not name or not self.root:
            return None
        for sub in self.SUBDIRS:
            folder = os.path.join(self.root, sub)
            if not os.path.isdir(folder):
                continue
            direct = os.path.join(folder, name)
            if os.path.isfile(direct):
                return direct
            low = name.lower()
            try:
                for f in os.listdir(folder):
                    if f.lower() == low:
                        return os.path.join(folder, f)
            except OSError:
                pass
        return None

    def library(self, name):
        key = (name or "").lower()
        if key in self._libs:
            return self._libs[key]
        path = self.find(name)
        lib = None
        if path:
            try:
                lib = ilb.read(path)
            except Exception:
                lib = None
        self._libs[key] = lib
        return lib

    def count(self, name):
        lib = self.library(name)
        return len(lib.images) if lib else 0

    def pixmap(self, name, index):
        """Decoded picture for <name> #<index>, or None."""
        key = ((name or "").lower(), index)
        if key in self._cache:
            return self._cache[key]
        lib = self.library(name)
        pm = None
        img = None
        if lib and index is not None:
            # campaigns reference pictures by image id, which is usually but not
            # always the position in the file
            for cand in lib.images:
                if cand.id == index:
                    img = cand
                    break
            if img is None and 0 <= index < len(lib.images):
                img = lib.images[index]
        if img is not None and img.parts:
            try:
                pm = decode_to_pixmap(lib, img.parts[0])
            except Exception:
                pm = None
        self._cache[key] = pm
        return pm


class ImagePicker(ChromeDialog):
    """Visual chooser for a book-page picture."""

    def __init__(self, resolver, name, index, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Choose book picture")
        self.resolver = resolver
        self.chosen_name = name
        self.chosen_index = index
        v = QVBoxLayout(self)

        hb = QHBoxLayout()
        hb.addWidget(QLabel("Library:"))
        self.combo = QComboBox()
        self.combo.setEditable(True)
        libs = []
        if resolver.root:
            folder = os.path.join(resolver.root, "Int", "Scenes")
            if os.path.isdir(folder):
                libs = sorted(f for f in os.listdir(folder) if f.lower().endswith(".ilb"))
        for f in libs:
            self.combo.addItem(f)
        if name and self.combo.findText(name) < 0:
            self.combo.addItem(name)
        if name:
            self.combo.setCurrentText(name)
        self.combo.currentTextChanged.connect(self.reload)
        hb.addWidget(self.combo, 1)
        v.addLayout(hb)

        self.list = QListWidget()
        self.list.setViewMode(QListWidget.IconMode)
        self.list.setIconSize(QSize(96, 120))
        self.list.setResizeMode(QListWidget.Adjust)
        self.list.setSpacing(6)
        self.list.itemDoubleClicked.connect(lambda _i: self.accept())
        v.addWidget(self.list, 1)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self.resize(720, 560)
        self.reload(self.combo.currentText())

    def reload(self, name):
        self.list.clear()
        lib = self.resolver.library(name)
        if not lib:
            self.list.addItem("library not found")
            return
        for i in range(len(lib.images)):
            pm = self.resolver.pixmap(name, i)
            it = QListWidgetItem("#%d" % i)
            if pm is not None and not pm.isNull():
                it.setIcon(QIcon(pm))
            it.setData(Qt.UserRole, i)
            self.list.addItem(it)
            if i == self.chosen_index:
                self.list.setCurrentItem(it)

    def accept(self):
        self.chosen_name = self.combo.currentText()
        it = self.list.currentItem()
        if it is not None and it.data(Qt.UserRole) is not None:
            self.chosen_index = it.data(Qt.UserRole)
        super().accept()


# ---------------------------------------------------------------------------
# spell checking
# ---------------------------------------------------------------------------
class Dictionary:
    """General dictionary + a per-campaign word list the user can grow."""

    BRITISH = {
        "favour", "favours", "favoured", "favourable", "favourite", "honour", "honours",
        "honoured", "honourable", "dishonourable", "rumour", "rumours", "rumoured",
        "endeavour", "endeavours", "behaviour", "behaviours", "labour", "labours",
        "vigour", "fervour", "demeanour", "armour", "armoured", "colour", "coloured",
        "neighbour", "neighbours", "harbour", "splendour", "valour", "saviour",
        "realisation", "realise", "realised", "realises", "organise", "organised",
        "recognise", "recognised", "apologise", "civilised", "defence", "offence",
        "travelled", "travelling", "marvellous", "counsellor", "sceptre", "centre",
        "theatre", "sombre", "manoeuvre", "practise", "grey",
    }
    EXTRA = {
        "undeath", "undead", "commonfolk", "frontlines", "singlehandedly",
        "berserkers", "teleport", "teleports", "hobbits", "mana", "manna",
    }

    def __init__(self, path=None):
        self.sp = SpellChecker() if SpellChecker else None
        self.custom = set()
        self.path = path
        self.load()

    def load(self):
        self.custom = set()
        if self.path and os.path.isfile(self.path):
            try:
                self.custom = {w.lower() for w in json.load(open(self.path, encoding="utf-8"))}
            except Exception:
                pass

    def save(self):
        if not self.path:
            return
        try:
            json.dump(sorted(self.custom), open(self.path, "w", encoding="utf-8"), indent=1)
        except Exception:
            pass

    def seed_from_campaign(self, campaign):
        """Names the author already uses are not typos."""
        words = set()
        for r in campaign.records:
            for s in (r.short_title, r.full_title, r.ca_description):
                for w in re.findall(r"[A-Za-z][A-Za-z']*", s or ""):
                    words.add(w.lower())
        self.seeded = words
        return words

    def known(self, word):
        lw = word.lower().strip("'")
        if not lw or len(lw) == 1:
            return True
        if lw in self.custom or lw in self.BRITISH or lw in self.EXTRA:
            return True
        if lw in getattr(self, "seeded", ()):
            return True
        if lw.endswith("'s") and self._base(lw[:-2]):
            return True
        return self._base(lw)

    def _base(self, w):
        if self.sp is None:
            return True
        return w in self.sp

    def suggest(self, word):
        if self.sp is None:
            return []
        lw = word.lower().strip("'")
        try:
            cands = self.sp.candidates(lw) or set()
        except Exception:
            cands = set()
        return sorted(cands)[:6]

    def add(self, word):
        self.custom.add(word.lower().strip("'"))
        self.save()


class SpellHighlighter(QSyntaxHighlighter):
    def __init__(self, doc, dictionary):
        super().__init__(doc)
        self.dict = dictionary
        self.enabled = True
        self.fmt = QTextCharFormat()
        self.fmt.setUnderlineColor(QColor(220, 60, 60))
        self.fmt.setUnderlineStyle(QTextCharFormat.SpellCheckUnderline)

    def highlightBlock(self, text):
        if not self.enabled or self.dict is None:
            return
        for m in re.finditer(r"[A-Za-z][A-Za-z']*", text):
            w = m.group(0)
            if not self.dict.known(w):
                self.setFormat(m.start(), len(w), self.fmt)


class SpellTextEdit(QTextEdit):
    """Story-text editor with red squiggles and a right-click correction menu."""

    def __init__(self, dictionary, parent=None):
        super().__init__(parent)
        self.dict = dictionary
        self.hl = SpellHighlighter(self.document(), dictionary)
        self.setAcceptRichText(False)
        # moss/stone backdrop behind the story text, barely visible once the
        # pane holds text. Palette (not stylesheet) transparency: a stylesheet
        # background here breaks the native scrollbars (black grooves)
        pal = self.palette()
        pal.setBrush(QPalette.Base, QColor(0, 0, 0, 0))
        self.setPalette(pal)
        self.viewport().setAutoFillBackground(False)

    def paintEvent(self, ev):
        p = QPainter(self.viewport())
        vw, vh = self.viewport().width(), self.viewport().height()
        p.fillRect(0, 0, vw, vh, QApplication.palette().base())
        draw_backdrop(p, vw, vh, BG["theme"],
                      FAINT if not self.document().isEmpty() else None)
        p.end()
        super().paintEvent(ev)

    def contextMenuEvent(self, ev):
        menu = self.createStandardContextMenu()
        cur = self.cursorForPosition(ev.pos())
        cur.select(QTextCursor.WordUnderCursor)
        word = cur.selectedText()
        if word and not self.dict.known(word):
            menu.addSeparator()
            for s in self.dict.suggest(word):
                a = menu.addAction('Replace with "%s"' % s)
                a.triggered.connect(lambda _c=False, ss=s, cc=QTextCursor(cur):
                                    (cc.insertText(ss), self.hl.rehighlight()))
            a = menu.addAction('Add "%s" to campaign dictionary' % word)
            a.triggered.connect(lambda _c=False, w=word:
                                (self.dict.add(w), self.hl.rehighlight()))
        menu.exec(ev.globalPos())


# ---------------------------------------------------------------------------
# map canvas
# ---------------------------------------------------------------------------
class NodeItem(QGraphicsEllipseItem):
    R = 9

    def __init__(self, rec, view):
        super().__init__(-self.R, -self.R, self.R * 2, self.R * 2)
        self.rec = rec
        self.view = view
        self.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIsSelectable |
                      QGraphicsItem.ItemSendsGeometryChanges)
        self.setCursor(Qt.OpenHandCursor)
        self.setZValue(10)
        self.label = QGraphicsSimpleTextItem(rec.short_title or str(rec.id), self)
        f = QFont()
        f.setPointSize(7)
        self.label.setFont(f)
        self.label.setBrush(QBrush(QColor(245, 245, 245)))
        self.label.setPos(self.R + 2, -6)
        self.label.setZValue(11)
        # the record's ID drawn inside the marker, for quick cross-reference
        self.idtext = QGraphicsSimpleTextItem("", self)
        idf = QFont()
        idf.setPointSize(6)
        idf.setBold(True)
        self.idtext.setFont(idf)
        self.idtext.setZValue(12)
        self.refresh()
        self.setPos(rec.x, rec.y)

    def refresh(self):
        is_scen = self.rec.is_scenario
        start = self.view.main.campaign and self.view.main.campaign.records \
            and self.view.main.campaign.records[0] is self.rec
        col = COL_SCEN_START if start else (COL_SCEN if is_scen else COL_CA)
        self.setBrush(QBrush(col))
        self.setPen(QPen(QColor(20, 20, 20), 1.4))
        self.label.setText(self.rec.short_title or str(self.rec.id))
        self.update_id_text()

    def update_id_text(self):
        show = getattr(self.view, "show_ids", False)
        if not show:
            self.idtext.setText("")
            self.idtext.setVisible(False)
            return
        t = str(self.rec.id)
        self.idtext.setText(t)
        # dark text on the light markers reads better than white
        self.idtext.setBrush(QBrush(QColor(15, 20, 15)))
        br = self.idtext.boundingRect()
        self.idtext.setPos(-br.width() / 2.0, -br.height() / 2.0)
        self.idtext.setVisible(True)
        self.setToolTip("#%d  %s\n%s\n%s" % (
            self.rec.id, self.rec.short_title,
            self.rec.full_title or "", self.rec.scenario_file or ""))

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange and self.scene():
            p = value
            p.setX(max(0, min(MAP_W - 1, p.x())))
            p.setY(max(0, min(MAP_H - 1, p.y())))
            return p
        if change == QGraphicsItem.ItemPositionHasChanged:
            self.rec.x = int(self.pos().x())
            self.rec.y = int(self.pos().y())
            self.view.main.mark_dirty()
            self.view.redraw_links()
            self.view.main.sync_coords(self.rec)
        return super().itemChange(change, value)

    def mousePressEvent(self, ev):
        # snapshot once, before the drag begins
        self.view.main.snapshot("move '%s'" % (self.rec.short_title or self.rec.id))
        self.setCursor(Qt.ClosedHandCursor)
        super().mousePressEvent(ev)

    def mouseReleaseEvent(self, ev):
        self.setCursor(Qt.OpenHandCursor)
        super().mouseReleaseEvent(ev)

    def mouseDoubleClickEvent(self, ev):
        self.view.main.focus_record(self.rec)
        super().mouseDoubleClickEvent(ev)


class MapView(QGraphicsView):
    def __init__(self, main):
        super().__init__()
        self.main = main
        self.setScene(QGraphicsScene(self))
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.nodes = {}
        self.link_items = []
        self.bg = None
        self.show_next = True
        self.show_ca_links = True
        self.show_ids = False
        self.show_labels = True
        self._zoom = 1.0

    def refresh_markers(self):
        for it in self.nodes.values():
            it.update_id_text()
            it.label.setVisible(self.show_labels)

    def wheelEvent(self, ev):
        f = 1.15 if ev.angleDelta().y() > 0 else 1 / 1.15
        if 0.25 < self._zoom * f < 8:
            self._zoom *= f
            self.scale(f, f)

    def load_background(self):
        sc = self.scene()
        for cand in ("worldmap_annotated.jpg", "worldmap.jpg"):
            p = os.path.join(HERE, "assets", cand)
            if os.path.isfile(p):
                pm = QPixmap(p)
                if not pm.isNull():
                    self.bg = QGraphicsPixmapItem(pm)
                    self.bg.setZValue(-100)
                    sc.addItem(self.bg)
                    break
        sc.setSceneRect(0, 0, MAP_W, MAP_H)
        if self.bg is None:
            sc.addRect(0, 0, MAP_W, MAP_H, QPen(QColor(80, 80, 90)),
                       QBrush(QColor(38, 42, 50))).setZValue(-100)

    def rebuild(self, campaign):
        sc = self.scene()
        sc.clear()
        self.nodes.clear()
        self.link_items.clear()
        self.bg = None
        self.load_background()
        if not campaign:
            return
        for r in campaign.records:
            it = NodeItem(r, self)
            sc.addItem(it)
            self.nodes[id(r)] = it
        self.redraw_links()

    def redraw_links(self):
        sc = self.scene()
        for it in self.link_items:
            if it.scene():
                sc.removeItem(it)
        self.link_items.clear()
        campaign = self.main.campaign
        if not campaign:
            return
        for r in campaign.records:
            a = self.nodes.get(id(r))
            if a is None or not a.isVisible():
                continue
            if self.show_next:
                for nid in r.next_missions:
                    t = campaign.by_id(nid)
                    b = self.nodes.get(id(t)) if t else None
                    if b is not None and b.isVisible():
                        self._arrow(a.pos(), b.pos(), COL_NEXT)
            if self.show_ca_links and r.counter_action is not None:
                t = campaign.by_id(r.counter_action)
                b = self.nodes.get(id(t)) if t else None
                if b is not None and b.isVisible():
                    self._arrow(a.pos(), b.pos(), COL_LINK, dashed=True)

    def _arrow(self, p1, p2, colour, dashed=False):
        path = QPainterPath(p1)
        dx, dy = p2.x() - p1.x(), p2.y() - p1.y()
        path.quadTo(QPointF(p1.x() + dx * 0.5 - dy * 0.12,
                            p1.y() + dy * 0.5 + dx * 0.12), p2)
        item = QGraphicsPathItem(path)
        pen = QPen(colour, 1.6)
        if dashed:
            pen.setStyle(Qt.DashLine)
        pen.setCosmetic(True)
        item.setPen(pen)
        item.setZValue(1)
        self.scene().addItem(item)
        self.link_items.append(item)

    def set_visible_records(self, keep):
        for r_id, it in self.nodes.items():
            it.setVisible(r_id in keep)
        self.redraw_links()

    def centre_on(self, rec):
        it = self.nodes.get(id(rec))
        if it:
            self.centerOn(it)


# ---------------------------------------------------------------------------
# org-chart / flow view
# ---------------------------------------------------------------------------
class FlowNode(QGraphicsPathItem):
    W, H = 128, 34

    def __init__(self, rec, view, kind="scenario"):
        super().__init__()
        self.rec = rec
        self.view = view
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.W, self.H, 6, 6)
        self.setPath(path)
        fill = {"scenario": QColor(46, 74, 52), "start": QColor(96, 80, 26),
                "counter": QColor(80, 40, 42), "ending": QColor(38, 68, 66)}[kind]
        edge = {"scenario": COL_SCEN, "start": COL_SCEN_START,
                "counter": COL_CA, "ending": QColor(154, 209, 196)}[kind]
        self.setBrush(QBrush(fill))
        pen = QPen(edge, 1.6)
        pen.setCosmetic(True)
        self.setPen(pen)
        self.setZValue(10)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setAcceptHoverEvents(True)
        title = QGraphicsSimpleTextItem(rec.short_title or "(untitled)", self)
        f = QFont()
        f.setPointSize(7)
        f.setBold(kind == "start")
        title.setFont(f)
        title.setBrush(QBrush(QColor(238, 238, 240)))
        title.setPos(7, 5)
        sub = QGraphicsSimpleTextItem("#%d%s" % (rec.id, "" if kind != "counter" else "  CA"), self)
        f2 = QFont()
        f2.setPointSize(6)
        sub.setFont(f2)
        sub.setBrush(QBrush(QColor(176, 176, 186)))
        sub.setPos(7, 19)
        self.setToolTip("#%d  %s\n%s" % (rec.id, rec.short_title, rec.scenario_file or ""))

    def mousePressEvent(self, ev):
        self.view.main.focus_record(self.rec, from_tree=True)
        super().mousePressEvent(ev)


class FlowView(QGraphicsView):
    """Automatic layered layout of the campaign - the org-chart view."""

    def __init__(self, main):
        super().__init__()
        self.main = main
        self.setScene(QGraphicsScene(self))
        self.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setBackgroundBrush(QBrush(QColor(28, 30, 36)))
        self.nodes = {}
        self.show_cas = True
        self._zoom = 1.0

    def wheelEvent(self, ev):
        f = 1.15 if ev.angleDelta().y() > 0 else 1 / 1.15
        if 0.1 < self._zoom * f < 6:
            self._zoom *= f
            self.scale(f, f)

    def rebuild(self, campaign, show_cas=True, keep=None):
        """keep = set of id(record) to draw; None means everything."""
        sc = self.scene()
        sc.clear()
        self.nodes.clear()
        self.show_cas = show_cas
        self.keep = keep
        if not campaign:
            return
        nxt, indeg, _roots = cam.build_graph(campaign)
        allowed = None
        if keep is not None:
            allowed = {r.id for r in campaign.records if id(r) in keep}
            nxt = {a: [b for b in bs if b in allowed]
                   for a, bs in nxt.items() if a in allowed}
            # the filtered subgraph needs its OWN roots, otherwise the branch
            # root is never used as a starting point and everything piles into
            # a single row
            indeg = {i: 0 for i in allowed}
            for a, bs in nxt.items():
                for b in bs:
                    indeg[b] = indeg.get(b, 0) + 1

        # ---- assign a depth to every scenario (longest path, cycle-safe) ----
        order = []
        depth = {}
        if allowed is None:
            start_ids = [campaign.records[0].id] if campaign.records else []
            for r in campaign.scenarios:
                if indeg.get(r.id, 0) == 0 and r.id not in start_ids:
                    start_ids.append(r.id)
        else:
            start_ids = [r.id for r in campaign.records
                         if r.id in allowed and indeg.get(r.id, 0) == 0]
            if not start_ids and allowed:
                start_ids = [next(r.id for r in campaign.records if r.id in allowed)]
        # BFS shortest-path depth. Longest-path is unbounded here because the
        # campaign loops back on itself, which produced a 32000px tall canvas.
        queue = [(rid, 0) for rid in start_ids]
        while queue:
            rid, d = queue.pop(0)
            if rid in depth:
                continue
            depth[rid] = d
            order.append(rid)
            for k in nxt.get(rid, []):
                if k not in depth:
                    queue.append((k, d + 1))
        for r in campaign.records:                       # anything unplaced
            if r.id not in depth and r.is_scenario:
                if keep is None or id(r) in keep:
                    depth[r.id] = 0

        layers = {}
        for rid in sorted(depth, key=lambda k: (depth[k], order.index(k) if k in order else 0)):
            layers.setdefault(depth[rid], []).append(rid)

        GAPX, GAPY = 30, 74
        pos = {}
        for d in sorted(layers):
            row = layers[d]
            total = len(row) * (FlowNode.W + GAPX)
            x0 = -total / 2.0
            for i, rid in enumerate(row):
                pos[rid] = (x0 + i * (FlowNode.W + GAPX), d * (FlowNode.H + GAPY))

        # ---- boxes ----
        for rid, (x, y) in pos.items():
            rec = campaign.by_id(rid)
            if rec is None:
                continue
            if rec.is_scenario:
                kind = "start" if (campaign.records and rec is campaign.records[0]) else "scenario"
            else:
                kind = "ending"
            n = FlowNode(rec, self, kind)
            n.setPos(x, y)
            sc.addItem(n)
            self.nodes[id(rec)] = n
            if show_cas and rec.counter_action is not None:
                ca = campaign.by_id(rec.counter_action)
                if ca is not None and id(ca) not in self.nodes:
                    cn = FlowNode(ca, self, "counter")
                    cn.setScale(0.72)
                    cn.setPos(x + FlowNode.W * 0.30, y + FlowNode.H + 6)
                    sc.addItem(cn)
                    self.nodes[id(ca)] = cn
                    self._link(QPointF(x + FlowNode.W / 2, y + FlowNode.H),
                               QPointF(x + FlowNode.W * 0.30 + FlowNode.W * 0.36,
                                       y + FlowNode.H + 6),
                               COL_LINK, dashed=True)

        # ---- connectors ----
        for rid, kids in nxt.items():
            if rid not in pos:
                continue
            x1, y1 = pos[rid]
            for k in kids:
                if k not in pos:
                    continue
                x2, y2 = pos[k]
                a = QPointF(x1 + FlowNode.W / 2, y1 + FlowNode.H)
                b = QPointF(x2 + FlowNode.W / 2, y2)
                back = y2 <= y1
                self._link(a, b, QColor(200, 170, 90) if back else COL_NEXT, dashed=back)
        sc.setSceneRect(sc.itemsBoundingRect().adjusted(-60, -60, 60, 60))

    def _link(self, a, b, colour, dashed=False):
        path = QPainterPath(a)
        midy = (a.y() + b.y()) / 2.0
        if abs(a.x() - b.x()) < 1:
            path.lineTo(b)
        else:
            path.lineTo(a.x(), midy)
            path.lineTo(b.x(), midy)
            path.lineTo(b)
        it = QGraphicsPathItem(path)
        pen = QPen(colour, 1.4)
        pen.setCosmetic(True)
        if dashed:
            pen.setStyle(Qt.DashLine)
        it.setPen(pen)
        it.setBrush(QBrush(Qt.NoBrush))
        it.setZValue(1)
        self.scene().addItem(it)

    def set_visible_records(self, keep):
        for rid, it in self.nodes.items():
            it.setVisible(rid in keep)

    def centre_on(self, rec):
        it = self.nodes.get(id(rec))
        if it:
            self.centerOn(it)


# ---------------------------------------------------------------------------
# main window
# ---------------------------------------------------------------------------
class BranchTree(QTreeWidget):
    """The campaign-branch tree, with the moss/stone backdrop barely visible
    behind the rows once a campaign is loaded."""

    def __init__(self, main):
        super().__init__()
        self.main = main
        # palette (not stylesheet) transparency: a stylesheet background here
        # breaks the native scrollbars (black grooves)
        pal = self.palette()
        pal.setBrush(QPalette.Base, QColor(0, 0, 0, 0))
        self.setPalette(pal)
        self.viewport().setAutoFillBackground(False)

    def paintEvent(self, ev):
        p = QPainter(self.viewport())
        vw, vh = self.viewport().width(), self.viewport().height()
        pal = QApplication.palette()
        loaded = self.main.campaign is not None
        p.fillRect(0, 0, vw, vh, pal.base() if loaded else pal.window())
        draw_backdrop(p, vw, vh, BG["theme"], FAINT if loaded else None)
        p.end()
        super().paintEvent(ev)


class Main(CaptionedMainWindow):
    @property
    def bg_theme(self):
        # ChromeDialog looks the theme up here; BG stays the single source
        return BG["theme"]

    def paintEvent(self, ev):
        paint_chrome(self, BG["theme"])
        super().paintEvent(ev)

    def __init__(self):
        super().__init__()
        self.campaign = None
        self.path = None
        self.dirty = False
        self.current = None
        self.dict = Dictionary()
        self.settings = QSettings("AoWx", "AoWxQuest")
        BG["theme"] = self.settings.value("bg_theme", "moss")
        self._loading = False
        self.resolver = ImageResolver()
        self._undo, self._redo = [], []
        self._burst = None
        self._burst_timer = QTimer(self)
        self._burst_timer.setSingleShot(True)
        self._burst_timer.setInterval(1200)
        self._burst_timer.timeout.connect(lambda: setattr(self, "_burst", None))
        self.setWindowTitle(APP)
        ico = os.path.join(HERE, "assets", "aowxquest.ico")
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

        act("New", QStyle.SP_FileIcon, self.new_campaign, "Ctrl+N")
        act("Open", QStyle.SP_DialogOpenButton, self.open, "Ctrl+O")
        act("Save", QStyle.SP_DialogSaveButton, self.save, "Ctrl+S")
        act("Save As", QStyle.SP_DriveFDIcon, self.save_as)
        tb.addSeparator()
        self.act_undo = act("Undo", QStyle.SP_ArrowBack, self.undo, "Ctrl+Z")
        self.act_redo = act("Redo", QStyle.SP_ArrowForward, self.redo, "Ctrl+Y")
        self.act_undo.setEnabled(False)
        self.act_redo.setEnabled(False)
        tb.addSeparator()
        act("Add scenario", QStyle.SP_FileDialogNewFolder,
            lambda: self.add_record(True), None, "Add a scenario node")
        act("Add counter action", QStyle.SP_FileDialogListView,
            lambda: self.add_record(False), None, "Add a counter-action node")
        act("Delete", QStyle.SP_TrashIcon, self.delete_record, "Del")
        tb.addSeparator()
        a_start = act("Set as start", QStyle.SP_MediaPlay, self.set_start, None,
                      "The game always starts at the FIRST record - this moves it there")
        a_start.setIcon(play_icon())            # the stock icon is too dark
        tb.addSeparator()
        act("Find typos", QStyle.SP_FileDialogContentsView, self.find_typos, "Ctrl+T",
            "List every suspect word and jump straight to it")
        act("Check campaign", QStyle.SP_MessageBoxWarning, self.check_campaign, None,
            "Look for broken links: missing counter actions, scenarios with none, "
            "unreachable branches")
        act("Game folder", QStyle.SP_DirIcon, self.choose_root, None,
            "Where to look for book-page image libraries (Int\\Scenes)")
        tb.addSeparator()
        tb.addWidget(QLabel(" Background: "))
        self.cb_theme = QComboBox()
        self.cb_theme.addItem("Moss", "moss")
        self.cb_theme.addItem("Stone", "stone")
        self.cb_theme.setCurrentIndex(max(0, self.cb_theme.findData(BG["theme"])))
        self.cb_theme.currentIndexChanged.connect(self.change_theme)
        tb.addWidget(self.cb_theme)
        ver = QLabel("   Version %s" % VERSION)
        ver.setStyleSheet("color:#888;")
        tb.addWidget(ver)

        split = QSplitter(Qt.Horizontal)

        # ---- left: branch tree + visibility ----
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(4, 4, 4, 4)
        lv.addWidget(QLabel("<b>Campaign branches</b>"))
        self.tree = BranchTree(self)
        self.tree.setHeaderLabels(["Scenario", "ID"])
        self.tree.setColumnWidth(0, 250)
        self.tree.itemChanged.connect(self.on_tree_check)
        self.tree.currentItemChanged.connect(self.on_tree_select)
        self.tree.itemClicked.connect(self.on_tree_click)
        lv.addWidget(self.tree, 1)

        vis = QGroupBox("Show on map")
        vv = QVBoxLayout(vis)
        self.chk_scen = QCheckBox("Scenarios")
        self.chk_ca = QCheckBox("Counter actions")
        self.chk_next = QCheckBox("Next-mission links")
        self.chk_calink = QCheckBox("Counter-action links")
        self.chk_only = QCheckBox("Only ticked branches")
        self.chk_only.setToolTip("Hide anything not ticked above. Counter actions appear "
                                 "under the scenario they belong to.")
        self.chk_ids = QCheckBox("ID numbers on markers")
        self.chk_names = QCheckBox("Names beside markers")
        self.chk_names.setChecked(True)
        for c in (self.chk_scen, self.chk_ca, self.chk_next, self.chk_calink):
            c.setChecked(True)
        for c in (self.chk_scen, self.chk_ca, self.chk_next, self.chk_calink,
                  self.chk_only, self.chk_ids, self.chk_names):
            c.stateChanged.connect(self.apply_visibility)
            vv.addWidget(c)
        hb = QHBoxLayout()
        b1 = QPushButton("Tick all")
        b1.clicked.connect(lambda: self.set_all_checks(True))
        b2 = QPushButton("Untick all")
        b2.clicked.connect(lambda: self.set_all_checks(False))
        hb.addWidget(b1)
        hb.addWidget(b2)
        vv.addLayout(hb)
        hb2 = QHBoxLayout()
        b3 = QPushButton("Only this branch")
        b3.setToolTip("Show only the selected scenario and everything below it "
                      "(same as Shift+clicking a row)")
        b3.clicked.connect(self.isolate_branch)
        b4 = QPushButton("Scenarios only")
        b4.clicked.connect(lambda: (self.chk_scen.setChecked(True),
                                    self.chk_ca.setChecked(False)))
        hb2.addWidget(b3)
        hb2.addWidget(b4)
        vv.addLayout(hb2)
        vv.addWidget(QLabel("<i>Shift+click a row = only that branch<br>"
                            "Ctrl+click = tick just that one</i>"))
        lv.addWidget(vis)
        split.addWidget(left)

        # ---- middle: world map / flow chart ----
        self.views = QTabWidget()
        self.map = MapView(self)
        self.map.load_background()
        self.views.addTab(self.map, "World map")
        self.flow = FlowView(self)
        self.views.addTab(self.flow, "Flow chart")
        self.views.currentChanged.connect(self.on_view_changed)
        split.addWidget(self.views)

        # ---- right: properties ----
        right = QTabWidget()
        self._chrome_pages = []
        gen = ChromePage(lambda: BG["theme"])
        self._chrome_pages.append(gen)
        form = QFormLayout(gen)
        self.f_id = QSpinBox()
        self.f_id.setRange(0, 99999)
        self.f_id.valueChanged.connect(lambda v: self.set_field("id", v))
        form.addRow("Scenario ID", self.f_id)
        self.f_short = QLineEdit()
        self.f_short.editingFinished.connect(
            lambda: self.set_field("short_title", self.f_short.text()))
        form.addRow("Short title", self.f_short)
        self.f_full = QLineEdit()
        self.f_full.editingFinished.connect(
            lambda: self.set_field("full_title", self.f_full.text()))
        form.addRow("Full title", self.f_full)
        hb = QHBoxLayout()
        self.f_csm = QLineEdit()
        self.f_csm.editingFinished.connect(
            lambda: self.set_field("scenario_file", self.f_csm.text()))
        bb = QPushButton("...")
        bb.setMaximumWidth(28)
        bb.clicked.connect(self.browse_csm)
        hb.addWidget(self.f_csm)
        hb.addWidget(bb)
        w = QWidget()
        w.setLayout(hb)
        form.addRow("Scenario file", w)
        self.f_music = QLineEdit()
        self.f_music.editingFinished.connect(
            lambda: self.set_field("music_file", self.f_music.text()))
        form.addRow("Music file", self.f_music)
        self.f_x = QSpinBox()
        self.f_x.setRange(0, MAP_W - 1)
        self.f_x.valueChanged.connect(lambda v: self.set_field("x", v))
        form.addRow("Map X", self.f_x)
        self.f_y = QSpinBox()
        self.f_y.setRange(0, MAP_H - 1)
        self.f_y.valueChanged.connect(lambda v: self.set_field("y", v))
        form.addRow("Map Y", self.f_y)
        self.f_next = QLineEdit()
        self.f_next.setPlaceholderText("up to 3 IDs, comma separated")
        self.f_next.editingFinished.connect(self.set_next)
        form.addRow("Next missions", self.f_next)
        cah = QHBoxLayout()
        self.f_ca = QComboBox()
        self.f_ca.setToolTip(
            "Every scenario has one counter action - the enemy's move while you play it.\n"
            "Pick an existing one here, or press 'New' to create one linked to this scenario.")
        self.f_ca.currentIndexChanged.connect(self.set_ca)
        b_newca = QPushButton("New")
        b_newca.setMaximumWidth(46)
        b_newca.setToolTip("Create a counter action and link it to this scenario")
        b_newca.clicked.connect(self.new_linked_ca)
        cah.addWidget(self.f_ca, 1)
        cah.addWidget(b_newca)
        caw = QWidget()
        caw.setLayout(cah)
        form.addRow("Counter action", caw)
        self.f_cadesc = QLineEdit()
        self.f_cadesc.editingFinished.connect(
            lambda: self.set_field("ca_description", self.f_cadesc.text()))
        form.addRow("CA description", self.f_cadesc)
        self.f_unk = QSpinBox()
        self.f_unk.setRange(0, 255)
        self.f_unk.valueChanged.connect(lambda v: self.set_field("unknown16", v))
        form.addRow("Field 0x16", self.f_unk)
        self.lbl_kind = QLabel("-")
        form.addRow("Record type", self.lbl_kind)
        right.addTab(gen, "General")

        self.page_tabs = {}
        for which in ("prologue", "epilogue"):
            page = ChromePage(lambda: BG["theme"])
            self._chrome_pages.append(page)
            pv = QVBoxLayout(page)
            hb2 = QHBoxLayout()
            hb2.addWidget(QLabel("Page"))
            spin = QSpinBox()
            spin.setRange(1, cam.PAGES_PER_CHAPTER)
            hb2.addWidget(spin)
            hb2.addStretch(1)
            pv.addLayout(hb2)
            title = QLineEdit()
            pv.addWidget(QLabel("Page title"))
            pv.addWidget(title)
            text = SpellTextEdit(self.dict)
            pv.addWidget(QLabel("Story text (typos underlined in red)"))
            pv.addWidget(text, 1)
            hb3 = QHBoxLayout()
            img = QLineEdit()
            img.setPlaceholderText("image library, e.g. BPGob.ILB")
            picnr = QSpinBox()
            picnr.setRange(-1, 99999)
            picnr.setSpecialValueText("-")
            browse = QPushButton("Pick...")
            browse.setMaximumWidth(58)
            full = QPushButton("Full size")
            full.setMaximumWidth(74)
            full.setToolTip("Open this picture at its real size (272x372 for book art)")
            hb3.addWidget(QLabel("Image"))
            hb3.addWidget(img, 1)
            hb3.addWidget(QLabel("ID"))
            hb3.addWidget(picnr)
            hb3.addWidget(browse)
            hb3.addWidget(full)
            pv.addLayout(hb3)
            thumb = QLabel("no picture")
            thumb.setAlignment(Qt.AlignCenter)
            thumb.setMinimumHeight(300)
            thumb.setStyleSheet("background:#1e1e22; border:1px solid #3a3a42; color:#777;")
            pv.addWidget(thumb, 1)
            full.clicked.connect(lambda _c=False, wch=which: self.show_full_picture(wch))
            right.addTab(page, which.capitalize())
            self.page_tabs[which] = (spin, title, text, img, picnr, thumb)
            spin.valueChanged.connect(lambda _v, wch=which: self.load_page(wch))
            title.editingFinished.connect(lambda wch=which: self.save_page(wch))
            text.textChanged.connect(lambda wch=which: self.save_page(wch))
            img.editingFinished.connect(lambda wch=which: self.save_page(wch))
            picnr.valueChanged.connect(lambda _v, wch=which: self.save_page(wch))
            browse.clicked.connect(lambda _c=False, wch=which: self.pick_picture(wch))
        split.addWidget(right)
        split.setSizes([300, 760, 440])
        self.setCentralWidget(split)

        # ---- typo finder dock ----
        self.typo_dock = QDockWidget("Typo finder", self)
        self.typo_dock.setAllowedAreas(Qt.BottomDockWidgetArea | Qt.RightDockWidgetArea)
        tw = QWidget()
        tv = QVBoxLayout(tw)
        bar = QHBoxLayout()
        b_scan = QPushButton("Scan campaign")
        b_scan.clicked.connect(self.scan_typos)
        bar.addWidget(b_scan)
        self.b_addword = QPushButton("Add word to dictionary")
        self.b_addword.clicked.connect(self.typo_add_word)
        bar.addWidget(self.b_addword)
        # note: NOT chk_names - that is the map's "Names beside markers" box,
        # and reusing the attribute silently broke it
        self.chk_typonames = QCheckBox("Show likely names too")
        self.chk_typonames.setToolTip(
            "A capitalised word used 3+ times is almost always a character or place "
            "name rather than a typo, so it is listed separately.")
        self.chk_typonames.stateChanged.connect(lambda: self.scan_typos() if self.campaign else None)
        bar.addWidget(self.chk_typonames)
        self.typo_count = QLabel("not scanned")
        bar.addWidget(self.typo_count)
        bar.addStretch(1)
        tv.addLayout(bar)
        self.typo_tree = QTreeWidget()
        self.typo_tree.setHeaderLabels(["Word / location", "Suggestions", "Where"])
        self.typo_tree.setColumnWidth(0, 260)
        self.typo_tree.setColumnWidth(1, 240)
        self.typo_tree.itemActivated.connect(self.goto_typo)
        self.typo_tree.itemClicked.connect(self.goto_typo)
        tv.addWidget(self.typo_tree)
        self.typo_dock.setWidget(tw)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.typo_dock)
        self.typo_dock.hide()

        self.setStatusBar(QStatusBar())
        self.status("New or open a campaign (.cam).")

    # -- infrastructure -----------------------------------------------------
    def status(self, m):
        self.statusBar().showMessage(m)

    def change_theme(self):
        BG["theme"] = self.cb_theme.currentData()
        self.settings.setValue("bg_theme", BG["theme"])
        self.update()
        for pg in self._chrome_pages:
            pg.update()
        self.tree.viewport().update()
        for spin, title, text, img, picnr, thumb in self.page_tabs.values():
            text.viewport().update()

    def mark_dirty(self):
        self.dirty = True
        self.update_title()

    # -- undo / redo --------------------------------------------------------
    def snapshot(self, label, burst=None):
        """Record the state BEFORE a change. `burst` coalesces a run of edits
        (typing) into a single undo step."""
        if self.campaign is None or self._loading:
            return
        if burst is not None:
            self._burst_timer.start()
            if self._burst == burst:
                return
            self._burst = burst
        else:
            self._burst = None
        try:
            blob = self.campaign.build()
        except Exception:
            return
        cur = self.current.id if self.current is not None else None
        self._undo.append((blob, cur, label))
        if len(self._undo) > UNDO_LIMIT:
            self._undo.pop(0)
        self._redo.clear()
        self.update_undo_actions()

    def update_undo_actions(self):
        self.act_undo.setEnabled(bool(self._undo))
        self.act_redo.setEnabled(bool(self._redo))
        self.act_undo.setToolTip("Undo %s" % self._undo[-1][2] if self._undo else "Undo")
        self.act_redo.setToolTip("Redo %s" % self._redo[-1][2] if self._redo else "Redo")

    def _restore(self, entry):
        blob, rec_id, label = entry
        self.campaign = cam.loads(blob)
        self.campaign.path = self.path
        self._burst = None
        self.dict.seed_from_campaign(self.campaign)
        self.map.rebuild(self.campaign)
        self.flow.rebuild(self.campaign, self.chk_ca.isChecked())
        self.rebuild_tree()
        self.apply_visibility()
        rec = self.campaign.by_id(rec_id) if rec_id is not None else None
        if rec is None and self.campaign.records:
            rec = self.campaign.records[0]
        if rec is not None:
            self.focus_record(rec)
        self.mark_dirty()
        return label

    def undo(self):
        if not self._undo:
            return
        cur = self.campaign.build()
        cur_id = self.current.id if self.current is not None else None
        entry = self._undo.pop()
        self._redo.append((cur, cur_id, entry[2]))
        label = self._restore(entry)
        self.update_undo_actions()
        self.status("Undid: %s" % label)

    def redo(self):
        if not self._redo:
            return
        cur = self.campaign.build()
        cur_id = self.current.id if self.current is not None else None
        entry = self._redo.pop()
        self._undo.append((cur, cur_id, entry[2]))
        label = self._restore(entry)
        self.update_undo_actions()
        self.status("Redid: %s" % label)

    def update_title(self):
        n = os.path.basename(self.path) if self.path else "(new campaign)"
        self.setWindowTitle("%s - %s%s" % (APP, n, " *" if self.dirty else ""))

    # -- file ---------------------------------------------------------------
    def new_campaign(self):
        self.campaign = cam.new_campaign()
        self.path = None
        self.dirty = False
        self.after_load()

    def open(self):
        f, _ = QFileDialog.getOpenFileName(self, "Open campaign", "",
                                           "AoW campaigns (*.cam *.CAM);;All files (*)")
        if f:
            self.load(f)

    def load(self, path):
        try:
            self.campaign = cam.read(path)
        except Exception as e:
            QMessageBox.critical(self, APP, "Could not read:\n%s\n\n%s" % (path, e))
            return
        self.path = path
        self.dirty = False
        self.dict.path = os.path.splitext(path)[0] + ".dict.json"
        self.dict.load()
        self.after_load()

    def after_load(self):
        c = self.campaign
        self._undo.clear()
        self._redo.clear()
        self._burst = None
        self.update_undo_actions()
        self.typo_tree.clear()
        self.typo_count.setText("not scanned")
        self.resolver.guess_root(self.path)
        self.dict.seed_from_campaign(c)
        self.map.rebuild(c)
        self.rebuild_tree()
        self.apply_visibility()
        nxt, indeg, roots = cam.build_graph(c)
        self.status("%s  -  %d scenarios, %d counter actions, replaces %s.  "
                    "%d root(s), %d branch point(s)."
                    % (c.name, len(c.scenarios), len(c.counter_actions),
                       "Cult of Storms" if c.replaces_storm else "Keepers",
                       len(roots), sum(1 for k in nxt if len(nxt[k]) > 1))
                    + ("  Book pictures: %s" % self.resolver.root if self.resolver.root
                       else "  (game folder not found - set it to preview book pictures)"))
        self.update_title()
        if c.records:
            self.focus_record(c.records[0])

    def save(self):
        if not self.campaign:
            return
        if not self.path:
            return self.save_as()
        try:
            n = self.campaign.save(self.path)
        except Exception as e:
            QMessageBox.critical(self, APP, "Save failed:\n%s" % e)
            return
        self.dirty = False
        self.update_title()
        self.status("Wrote %s (%d bytes)" % (os.path.basename(self.path), n))

    def save_as(self):
        f, _ = QFileDialog.getSaveFileName(self, "Save campaign", self.path or "Keepers.cam",
                                           "AoW campaigns (*.cam)")
        if f:
            self.path = f
            self.dict.path = os.path.splitext(f)[0] + ".dict.json"
            self.save()

    # -- tree ---------------------------------------------------------------
    def rebuild_tree(self):
        """Branch tree. Linear runs are kept at the same indent level so a long
        chain does not march off to the right - only real branch points indent."""
        self._loading = True
        self.tree.clear()
        self.tree.setIndentation(14)
        if not self.campaign:
            self._loading = False
            return
        nxt, indeg, _roots = cam.build_graph(self.campaign)
        placed_ca = set()

        def make_item(rec, extra="", colour=None):
            label = (rec.short_title or "(untitled)") + extra
            it = QTreeWidgetItem([label, str(rec.id)])
            it.setData(0, Qt.UserRole, rec)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(0, Qt.Checked)
            if colour:
                it.setForeground(0, QColor(colour))
            return it

        def attach_ca(parent, rec):
            """Show the scenario's counter action as a child, so it is visible
            and can be ticked like anything else."""
            cid = rec.counter_action
            if cid is None:
                return
            ca = self.campaign.by_id(cid)
            if ca is None:
                miss = QTreeWidgetItem(["counter action #%d is MISSING" % cid, str(cid)])
                miss.setForeground(0, QColor("#e06666"))
                miss.setData(0, Qt.UserRole, None)
                parent.addChild(miss)
                return
            placed_ca.add(id(ca))
            parent.addChild(make_item(ca, "   [counter action]", "#d98b8b"))

        seen = set()

        def walk(rid, parent, guard):
            """Follow a chain; only indent when a scenario really branches."""
            while True:
                rec = self.campaign.by_id(rid)
                if rec is None:
                    return
                if rid in seen:
                    it = make_item(rec, "   [loops back]", "#c8a04a")
                    it.setFlags(it.flags() & ~Qt.ItemIsUserCheckable)
                    (parent.addChild(it) if parent else self.tree.addTopLevelItem(it))
                    return
                seen.add(rid)
                is_start = self.campaign.records and rec is self.campaign.records[0]
                if not rec.is_scenario:
                    # a record with no music field that a scenario points to as its
                    # next mission is a branch ENDING, not a counter action
                    placed_ca.add(id(rec))
                    it = make_item(rec, "   [ending]", "#9ad1c4")
                elif is_start:
                    it = make_item(rec, "   [START]", "#e8c84a")
                else:
                    it = make_item(rec, "")
                if parent is None:
                    self.tree.addTopLevelItem(it)
                else:
                    parent.addChild(it)
                attach_ca(it, rec)
                kids = [k for k in nxt.get(rid, []) if k not in guard]
                if len(kids) == 1:
                    # straight continuation: same parent, so the chain reads as a
                    # flat run instead of stepping one indent per scenario
                    rid = kids[0]
                    guard = guard | {rid}
                    continue
                for k in kids:
                    walk(k, it, guard | {k})
                return

        start_ids = []
        if self.campaign.records:
            start_ids.append(self.campaign.records[0].id)
        for r in self.campaign.scenarios:
            if indeg.get(r.id, 0) == 0 and r.id not in start_ids:
                start_ids.append(r.id)
        for rid in start_ids:
            walk(rid, None, frozenset({rid}))
        for r in self.campaign.scenarios:          # anything unreachable
            if r.id not in seen:
                walk(r.id, None, frozenset({r.id}))

        orphan = [r for r in self.campaign.counter_actions if id(r) not in placed_ca]
        if orphan:
            top = QTreeWidgetItem(["Counter actions not linked to any scenario", ""])
            top.setFlags(top.flags() | Qt.ItemIsUserCheckable)
            top.setCheckState(0, Qt.Checked)
            top.setForeground(0, QColor("#d98b8b"))
            top.setData(0, Qt.UserRole, None)
            for r in orphan:
                top.addChild(make_item(r, "", "#d98b8b"))
            self.tree.addTopLevelItem(top)
        # keep everything open - hunting through collapsed arrows was the complaint
        self.tree.expandAll()
        self._loading = False

    def set_all_checks(self, on, refresh=True):
        was = self._loading
        self._loading = True
        st = Qt.Checked if on else Qt.Unchecked
        def walk(it):
            if it.flags() & Qt.ItemIsUserCheckable:
                it.setCheckState(0, st)
            for i in range(it.childCount()):
                walk(it.child(i))
        for i in range(self.tree.topLevelItemCount()):
            walk(self.tree.topLevelItem(i))
        self._loading = was
        if refresh:
            self.apply_visibility()

    def on_tree_check(self, item, col):
        if self._loading or col != 0:
            return
        # ticking a branch ticks its whole subtree
        st = item.checkState(0)
        self._loading = True
        def walk(it):
            for i in range(it.childCount()):
                c = it.child(i)
                c.setCheckState(0, st)
                walk(c)
        walk(item)
        self._loading = False
        self.apply_visibility()

    def on_tree_click(self, item, _col):
        """Shift+click isolates a branch; Ctrl+click ticks just that one row."""
        mods = QApplication.keyboardModifiers()
        if mods & Qt.ShiftModifier:
            self.isolate_branch(item)
        elif mods & Qt.ControlModifier:
            self._loading = True
            self.set_all_checks(False, refresh=False)
            item.setCheckState(0, Qt.Checked)
            self._loading = False
            self.chk_only.setChecked(True)
            self.apply_visibility()

    def isolate_branch(self, item=None):
        """Show only what is reachable from the selected scenario.

        This follows the next-mission GRAPH, not the tree - a straight run is
        drawn as siblings, so 'the rows underneath' is not the same thing as
        'the rest of this branch'.
        """
        if item is None or isinstance(item, bool):
            item = self.tree.currentItem()
        rec = item.data(0, Qt.UserRole) if item is not None else None
        if rec is None:
            return
        keep = cam.branch_from(self.campaign, rec.id)
        self._loading = True

        def walk(it):
            r = it.data(0, Qt.UserRole)
            if it.flags() & Qt.ItemIsUserCheckable:
                it.setCheckState(0, Qt.Checked if (r is not None and r.id in keep)
                                 else Qt.Unchecked)
            for i in range(it.childCount()):
                walk(it.child(i))
        for i in range(self.tree.topLevelItemCount()):
            walk(self.tree.topLevelItem(i))
        self._loading = False
        self.chk_only.setChecked(True)
        self.apply_visibility()
        self.status("Showing only the branch from '%s' - %d record(s)."
                    % (rec.short_title or rec.id, len(keep)))

    def on_tree_select(self, cur, _prev):
        if cur is None:
            return
        rec = cur.data(0, Qt.UserRole)
        if rec is not None:
            self.focus_record(rec, from_tree=True)

    def apply_visibility(self):
        if not self.campaign:
            return
        checked = set()
        def walk(it):
            rec = it.data(0, Qt.UserRole)
            if rec is not None and it.checkState(0) == Qt.Checked:
                checked.add(id(rec))
            for i in range(it.childCount()):
                walk(it.child(i))
        for i in range(self.tree.topLevelItemCount()):
            walk(self.tree.topLevelItem(i))
        keep = set()
        for r in self.campaign.records:
            if r.is_scenario and not self.chk_scen.isChecked():
                continue
            if (not r.is_scenario) and not self.chk_ca.isChecked():
                continue
            if self.chk_only.isChecked() and id(r) not in checked:
                continue
            keep.add(id(r))
        self.map.show_next = self.chk_next.isChecked()
        self.map.show_ca_links = self.chk_calink.isChecked()
        self.map.show_ids = self.chk_ids.isChecked()
        self.map.show_labels = self.chk_names.isChecked()
        self.map.refresh_markers()
        self.map.set_visible_records(keep)
        if self.views.currentIndex() == 1:
            # re-lay the chart out so hidden branches do not leave holes
            self.flow.rebuild(self.campaign, self.chk_ca.isChecked(),
                              keep if self.chk_only.isChecked() else None)
        else:
            self.flow.set_visible_records(keep)
        ns = sum(1 for r in self.campaign.records if r.is_scenario and id(r) in keep)
        self.status("%d of %d nodes shown  (%d scenarios, %d counter actions)"
                    % (len(keep), len(self.campaign.records), ns, len(keep) - ns))

    # -- record editing -----------------------------------------------------
    def focus_record(self, rec, from_tree=False):
        self.current = rec
        self._loading = True
        self.f_id.setValue(rec.id)
        self.f_short.setText(rec.short_title)
        self.f_full.setText(rec.full_title)
        self.f_csm.setText(rec.scenario_file)
        self.f_music.setText(rec.music_file)
        self.f_x.setValue(max(0, min(MAP_W - 1, rec.x)))
        self.f_y.setValue(max(0, min(MAP_H - 1, rec.y)))
        self.f_next.setText(", ".join(str(i) for i in rec.next_missions))
        self.fill_ca_combo(rec)
        self.f_cadesc.setText(rec.ca_description)
        self.f_unk.setValue(rec.unknown16)
        is_s = rec.is_scenario
        start = self.campaign.records and self.campaign.records[0] is rec
        self.lbl_kind.setText(("Scenario" if is_s else "Counter action") +
                              ("   <b>[START]</b>" if start else ""))
        for w in (self.f_csm, self.f_music, self.f_next):
            w.setEnabled(is_s)
        self._loading = False
        for which in ("prologue", "epilogue"):
            self.load_page(which)
        if not from_tree:
            (self.flow if self.views.currentIndex() == 1 else self.map).centre_on(rec)

    def on_view_changed(self, idx):
        if self.campaign and idx == 1:
            self.apply_visibility()
            if self.current is not None:
                self.flow.centre_on(self.current)

    def sync_coords(self, rec):
        if rec is self.current:
            self._loading = True
            self.f_x.setValue(max(0, min(MAP_W - 1, rec.x)))
            self.f_y.setValue(max(0, min(MAP_H - 1, rec.y)))
            self._loading = False

    def set_field(self, attr, value):
        if self._loading or self.current is None:
            return
        if getattr(self.current, attr, None) == value:
            return
        self.snapshot("change %s" % attr, burst=("field", id(self.current), attr))
        setattr(self.current, attr, value)
        self.mark_dirty()
        it = self.map.nodes.get(id(self.current))
        if it:
            if attr in ("x", "y"):
                it.setPos(self.current.x, self.current.y)
            it.refresh()
        if attr in ("short_title", "id"):
            self.rebuild_tree()
            self.apply_visibility()
        self.map.redraw_links()

    def set_next(self):
        if self._loading or self.current is None:
            return
        ids = []
        for tok in re.split(r"[,\s]+", self.f_next.text().strip()):
            if tok.lstrip("-").isdigit():
                ids.append(int(tok))
        if ids[:cam.MAX_NEXT] == self.current.next_missions:
            return
        self.snapshot("change next missions")
        self.current.next_missions = ids[:cam.MAX_NEXT]
        self.mark_dirty()
        self.rebuild_tree()
        self.apply_visibility()

    def fill_ca_combo(self, rec):
        self.f_ca.clear()
        self.f_ca.addItem("(none)", None)
        for ca in sorted(self.campaign.counter_actions, key=lambda r: r.id):
            self.f_ca.addItem("#%d  %s" % (ca.id, ca.short_title or "(untitled)"), ca.id)
        cur = rec.counter_action
        i = self.f_ca.findData(cur)
        if cur is not None and i < 0:            # dangling reference - show it as such
            self.f_ca.addItem("#%d  <MISSING>" % cur, cur)
            i = self.f_ca.count() - 1
        self.f_ca.setCurrentIndex(max(0, i))

    def set_ca(self):
        if self._loading or self.current is None:
            return
        new = self.f_ca.currentData()
        if new == self.current.counter_action:
            return
        self.snapshot("change counter action")
        self.current.counter_action = new
        self.mark_dirty()
        self.map.redraw_links()
        self.rebuild_tree()
        self.apply_visibility()

    def new_linked_ca(self):
        if self.current is None or not self.current.is_scenario:
            QMessageBox.information(self, APP, "Select a scenario first.")
            return
        self.snapshot("add linked counter action")
        ca = self.campaign.new_record(False, x=self.current.x + 18, y=self.current.y + 18,
                                      title="CA for %s" % (self.current.short_title or
                                                           self.current.id))
        self.current.counter_action = ca.id
        self.mark_dirty()
        self.map.rebuild(self.campaign)
        self.flow.rebuild(self.campaign, self.chk_ca.isChecked())
        self.rebuild_tree()
        self.apply_visibility()
        self.focus_record(self.current)
        self.status("Created counter action #%d and linked it to '%s'."
                    % (ca.id, self.current.short_title))

    def browse_csm(self):
        f, _ = QFileDialog.getOpenFileName(self, "Select scenario file", "",
                                           "AoW campaign scenarios (*.csm);;All files (*)")
        if f:
            self.f_csm.setText(os.path.basename(f))
            self.set_field("scenario_file", os.path.basename(f))

    def add_record(self, scenario=True):
        if not self.campaign:
            self.new_campaign()
        self.snapshot("add %s" % ("scenario" if scenario else "counter action"))
        centre = self.map.mapToScene(self.map.viewport().rect().center())
        r = self.campaign.new_record(scenario, x=int(centre.x()), y=int(centre.y()),
                                     title="New scenario" if scenario else "New counter action")
        self.mark_dirty()
        self.map.rebuild(self.campaign)
        self.flow.rebuild(self.campaign, self.chk_ca.isChecked())
        self.rebuild_tree()
        self.apply_visibility()
        self.focus_record(r)

    def delete_record(self):
        if not self.current or not self.campaign:
            return
        if QMessageBox.question(
                self, APP, "Delete '%s' (#%d)?\nReferences to it will be cleared."
                % (self.current.short_title, self.current.id)) != QMessageBox.Yes:
            return
        self.snapshot("delete '%s'" % self.current.short_title)
        self.campaign.delete_record(self.current)
        self.current = None
        self.mark_dirty()
        self.map.rebuild(self.campaign)
        self.flow.rebuild(self.campaign, self.chk_ca.isChecked())
        self.rebuild_tree()
        self.apply_visibility()

    def set_start(self):
        if not self.current or not self.campaign:
            return
        if not self.current.is_scenario:
            QMessageBox.warning(self, APP, "Only a scenario can be the start point.")
            return
        self.snapshot("set start scenario")
        self.campaign.move_to_start(self.current)
        self.mark_dirty()
        self.map.rebuild(self.campaign)
        self.flow.rebuild(self.campaign, self.chk_ca.isChecked())
        self.rebuild_tree()
        self.apply_visibility()
        self.focus_record(self.current)
        self.status("'%s' is now the campaign start." % self.current.short_title)

    # -- book pages ---------------------------------------------------------
    def _chapter(self, which):
        if self.current is None:
            return None
        return getattr(self.current, which)

    def load_page(self, which):
        ch = self._chapter(which)
        spin, title, text, img, picnr, thumb = self.page_tabs[which]
        if ch is None:
            return
        self._loading = True
        pg = ch.pages[spin.value() - 1]
        title.setText(pg.title)
        text.setPlainText(pg.text)
        img.setText(pg.image)
        picnr.setValue(pg.picnr if pg.picnr is not None else -1)
        self._loading = False
        self.update_thumb(which)

    def save_page(self, which):
        if self._loading:
            return
        ch = self._chapter(which)
        if ch is None:
            return
        spin, title, text, img, picnr, thumb = self.page_tabs[which]
        pg = ch.pages[spin.value() - 1]
        # the game stores CRLF; the editor gives us LF
        body = text.toPlainText().replace("\r\n", "\n").replace("\n", "\r\n")
        new = (title.text(), body, img.text(),
               None if picnr.value() < 0 else picnr.value())
        if (pg.title, pg.text, pg.image, pg.picnr) == new:
            return
        self.snapshot("edit %s page %d" % (which, spin.value()),
                      burst=("page", id(self.current), which, spin.value()))
        pg.title, pg.text, pg.image, pg.picnr = new
        self.mark_dirty()
        self.update_thumb(which)

    def update_thumb(self, which):
        spin, title, text, img, picnr, thumb = self.page_tabs[which]
        name = img.text().strip()
        idx = picnr.value()
        if not name:
            thumb.setPixmap(QPixmap())
            thumb.setText("no picture on this page")
            return
        if not self.resolver.root:
            thumb.setPixmap(QPixmap())
            thumb.setText("set the game folder to preview '%s'" % name)
            return
        if self.resolver.library(name) is None:
            thumb.setPixmap(QPixmap())
            thumb.setText("'%s' not found under %s" % (name, self.resolver.root))
            return
        if idx < 0:
            thumb.setPixmap(QPixmap())
            thumb.setText("%s - %d pictures, none selected" % (name, self.resolver.count(name)))
            return
        pm = self.resolver.pixmap(name, idx)
        if pm is None or pm.isNull():
            thumb.setPixmap(QPixmap())
            thumb.setText("%s #%d - no picture (library has %d)"
                          % (name, idx, self.resolver.count(name)))
            return
        box = thumb.size()
        if pm.width() > box.width() - 8 or pm.height() > box.height() - 8:
            pm = pm.scaled(box.width() - 8, box.height() - 8,
                           Qt.KeepAspectRatio, Qt.SmoothTransformation)
        thumb.setPixmap(pm)
        thumb.setText("")

    def show_full_picture(self, which):
        spin, title, text, img, picnr, thumb = self.page_tabs[which]
        pm = self.resolver.pixmap(img.text().strip(), picnr.value())
        if pm is None or pm.isNull():
            QMessageBox.information(self, APP, "No picture to show for this page.")
            return
        dlg = ChromeDialog(self)
        dlg.setWindowTitle("%s  #%d   (%dx%d)"
                           % (img.text().strip(), picnr.value(), pm.width(), pm.height()))
        v = QVBoxLayout(dlg)
        lab = QLabel()
        lab.setPixmap(pm)
        lab.setAlignment(Qt.AlignCenter)
        lab.setStyleSheet("background:#15151a;")
        v.addWidget(lab)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(dlg.reject)
        v.addWidget(bb)
        dlg.resize(pm.width() + 40, pm.height() + 80)
        dlg.exec()

    def pick_picture(self, which):
        spin, title, text, img, picnr, thumb = self.page_tabs[which]
        if not self.resolver.root:
            self.choose_root()
            if not self.resolver.root:
                return
        dlg = ImagePicker(self.resolver, img.text().strip(), picnr.value(), self)
        if dlg.exec() == QDialog.Accepted:
            img.setText(dlg.chosen_name)
            picnr.setValue(dlg.chosen_index if dlg.chosen_index is not None else -1)
            self.save_page(which)

    def choose_root(self):
        d = QFileDialog.getExistingDirectory(
            self, "Select the Age of Wonders folder (the one containing Int\\Scenes)",
            self.resolver.root or "")
        if d:
            self.resolver.set_root(d)
            for w in self.page_tabs:
                self.update_thumb(w)
            self.status("Book pictures will be read from %s" % d)

    # -- integrity check ----------------------------------------------------
    def check_campaign(self):
        if not self.campaign:
            return
        c = self.campaign
        ids = {r.id for r in c.records}
        ca_ids = {r.id for r in c.counter_actions}
        lines = []

        dup = {}
        for r in c.records:
            dup.setdefault(r.id, []).append(r)
        clash = {k: v for k, v in dup.items() if len(v) > 1}
        if clash:
            lines.append("DUPLICATE IDs (%d) - links become ambiguous:" % len(clash))
            for k, v in sorted(clash.items()):
                lines.append("   #%d used by %s" % (k, ", ".join(r.short_title or "?" for r in v)))
            lines.append("")

        missing_ca = [(s, s.counter_action) for s in c.scenarios
                      if s.counter_action is not None and s.counter_action not in ca_ids]
        if missing_ca:
            lines.append("Scenarios pointing at a counter action that does not exist (%d):"
                         % len(missing_ca))
            for s, cid in missing_ca:
                lines.append("   #%-4d %-24s -> #%d missing" % (s.id, s.short_title, cid))
            lines.append("")

        no_ca = [s for s in c.scenarios if s.counter_action is None]
        if no_ca:
            lines.append("Scenarios with no counter action (%d) - AoW expects one each:"
                         % len(no_ca))
            lines.append("   " + ", ".join("#%d %s" % (s.id, s.short_title) for s in no_ca))
            lines.append("")

        next_targets = {n for s in c.scenarios for n in s.next_missions}
        endings = [r for r in c.counter_actions
                   if r.id in next_targets
                   and not any(s.counter_action == r.id for s in c.scenarios)]
        if endings:
            lines.append("Branch endings (%d) - empty records a scenario points to as its "
                         "next mission, i.e. where a storyline stops:" % len(endings))
            lines.append("   " + ", ".join("#%d" % r.id for r in endings))
            lines.append("")

        unref = [r for r in c.counter_actions
                 if not any(s.counter_action == r.id for s in c.scenarios)
                 and r.id not in next_targets]
        if unref:
            lines.append("Counter actions nothing refers to (%d) - dead weight on the map:"
                         % len(unref))
            for r in unref:
                lines.append("   #%-4d %-24s at (%d,%d)"
                             % (r.id, r.short_title or "(untitled)", r.x, r.y))
            lines.append("")

        bad_next = []
        for s in c.scenarios:
            for n in s.next_missions:
                if n not in ids:
                    bad_next.append((s, n))
        if bad_next:
            lines.append("Next-mission links pointing nowhere (%d):" % len(bad_next))
            for s, n in bad_next:
                lines.append("   #%-4d %-24s -> #%d missing" % (s.id, s.short_title, n))
            lines.append("")

        nxt, indeg, roots = cam.build_graph(c)
        reach = set()
        stack = [c.records[0].id] if c.records else []
        while stack:
            k = stack.pop()
            if k in reach:
                continue
            reach.add(k)
            stack.extend(nxt.get(k, []))
        unreach = [s for s in c.scenarios if s.id not in reach]
        if unreach:
            lines.append("Scenarios unreachable from the start (%d):" % len(unreach))
            lines.append("   " + ", ".join("#%d %s" % (s.id, s.short_title) for s in unreach))
            lines.append("")

        head = ("%s: %d scenarios, %d counter actions. Start = #%s %s\n"
                % (c.name, len(c.scenarios), len(c.counter_actions),
                   c.records[0].id if c.records else "-",
                   c.records[0].short_title if c.records else ""))
        if not lines:
            lines = ["No problems found."]
        dlg = ChromeDialog(self)
        dlg.setWindowTitle("Campaign check")
        v = QVBoxLayout(dlg)
        te = QPlainTextEdit(head + "\n" + "\n".join(lines))
        te.setReadOnly(True)
        te.setStyleSheet("font-family:Consolas,monospace;")
        v.addWidget(te)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(dlg.reject)
        v.addWidget(bb)
        dlg.resize(820, 560)
        dlg.exec()

    # -- typo finder --------------------------------------------------------
    def find_typos(self):
        self.typo_dock.show()
        self.typo_dock.raise_()
        self.scan_typos()

    def scan_typos(self):
        if not self.campaign:
            return
        if SpellChecker is None:
            QMessageBox.warning(self, APP, "pyspellchecker is not installed.")
            return
        self.typo_tree.clear()
        hits = {}
        for r in self.campaign.records:
            for which in ("prologue", "epilogue"):
                for i, pg in enumerate(getattr(r, which).pages):
                    for field, raw in (("title", pg.title), ("text", pg.text)):
                        # the editor shows LF; stored text is CRLF, so normalise
                        # before computing offsets or navigation lands off by one
                        # per preceding line break
                        s = (raw or "").replace("\r\n", "\n").replace("\r", "\n")
                        for m in re.finditer(r"[A-Za-z][A-Za-z']*", s):
                            w = m.group(0)
                            if self.dict.known(w):
                                continue
                            ctx = " ".join((s[max(0, m.start() - 30):m.end() + 30]).split())
                            hits.setdefault(w, []).append(
                                (r.id, which, i + 1, field, m.start(), ctx))
        total = sum(len(v) for v in hits.values())

        def is_name(w):
            # a capitalised word used repeatedly is a character/place name,
            # not a typo - real typos are nearly always one-offs
            return w[:1].isupper() and len(hits[w]) >= 3

        typos = sorted((w for w in hits if not is_name(w)),
                       key=lambda k: (-len(hits[k]), k.lower()))
        names = sorted((w for w in hits if is_name(w)),
                       key=lambda k: (-len(hits[k]), k.lower()))

        def add_group(title, words, colour, expand):
            if not words:
                return None
            grp = QTreeWidgetItem(["%s  (%d)" % (title, len(words)), "", ""])
            grp.setData(0, Qt.UserRole, None)
            grp.setForeground(0, QColor(colour))
            f = grp.font(0)
            f.setBold(True)
            grp.setFont(0, f)
            for w in words:
                sug = ", ".join(self.dict.suggest(w)[:4])
                top = QTreeWidgetItem([("%s   (%d)" % (w, len(hits[w]))), sug, ""])
                top.setData(0, Qt.UserRole, ("word", w))
                top.setForeground(0, QColor(colour))
                for (rid, which, page, field, pos, ctx) in hits[w]:
                    rec = self.campaign.by_id(rid)
                    label = "#%d %s" % (rid, rec.short_title if rec else "?")
                    child = QTreeWidgetItem(["   " + ctx, "",
                                             "%s / %s page %d (%s)" % (label, which, page, field)])
                    child.setData(0, Qt.UserRole, ("hit", rid, which, page, field, pos, w))
                    top.addChild(child)
                grp.addChild(top)
            self.typo_tree.addTopLevelItem(grp)
            grp.setExpanded(expand)
            return grp

        add_group("Likely typos", typos, "#e8837f", True)
        if self.chk_typonames.isChecked():
            add_group("Probably names", names, "#9fb8d8", False)
        self.typo_count.setText(
            "%d likely typo(s), %d probable name(s), %d occurrence(s)"
            % (len(typos), len(names), total))
        self.status("Typo scan: %d likely typos (%d names set aside). Click one to jump to it."
                    % (len(typos), len(names)))

    def goto_typo(self, item, _col=0):
        d = item.data(0, Qt.UserRole)
        if not d:
            return
        if d[0] == "word":
            item.setExpanded(not item.isExpanded())
            return
        _kind, rid, which, page, field, pos, word = d
        rec = self.campaign.by_id(rid)
        if rec is None:
            return
        self.focus_record(rec)
        # bring the right chapter tab forward
        tabs = self.centralWidget().widget(2)
        tabs.setCurrentIndex(1 if which == "prologue" else 2)
        spin, title, text, img, picnr, thumb = self.page_tabs[which]
        if spin.value() != page:
            spin.setValue(page)
        else:
            self.load_page(which)
        target = title if field == "title" else text
        if field == "text":
            cur = text.textCursor()
            cur.setPosition(pos)
            cur.setPosition(pos + len(word), QTextCursor.KeepAnchor)
            text.setTextCursor(cur)
            text.setFocus()
            text.ensureCursorVisible()
        else:
            title.setFocus()
            title.setSelection(pos, len(word))
        self.status("'%s' - scenario #%d, %s page %d" % (word, rid, which, page))

    def typo_add_word(self):
        it = self.typo_tree.currentItem()
        if it is None:
            return
        d = it.data(0, Qt.UserRole)
        if not d:
            return
        word = d[1] if d[0] == "word" else d[6]
        self.dict.add(word)
        for which in self.page_tabs:
            self.page_tabs[which][2].hl.rehighlight()
        self.scan_typos()
        self.status("Added '%s' to the campaign dictionary." % word)

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
    for name in ("worldmap_annotated.jpg", "worldmap.jpg"):
        p = os.path.join(HERE, "assets", name)
        good = os.path.isfile(p)
        out.append("asset %-24s %s" % (name, "found" if good else "MISSING"))
        ok &= good
    if SpellChecker is None:
        out.append("spellchecker: NOT BUNDLED")
        ok = False
    else:
        try:
            d = Dictionary()
            bad = not d.known("teh")
            brit = d.known("favour")
            sug = d.suggest("curcamstance")
            out.append("spellchecker: dictionary loaded, flags 'teh'=%s, "
                       "accepts 'favour'=%s, suggests %s" % (bad, brit, sug[:2]))
            ok &= bad and brit
        except Exception as e:
            out.append("spellchecker FAILED: %s" % e)
            ok = False
    try:
        c = cam.new_campaign("Selftest")
        s = c.new_record(True, title="Intro")
        a = c.new_record(False, title="Enemy")
        s.counter_action = a.id
        s.prologue.pages[0].text = "Hello"
        blob = c.build()
        import tempfile
        p = os.path.join(tempfile.gettempdir(), "_aowx_selftest.cam")
        open(p, "wb").write(blob)
        c2 = cam.read(p)
        os.remove(p)
        good = (len(c2.records) == 2 and c2.scenarios[0].counter_action == a.id
                and c2.scenarios[0].prologue.pages[0].text == "Hello")
        out.append("campaign codec: %d bytes, round-trip %s" % (len(blob), "ok" if good else "BAD"))
        ok &= good
    except Exception as e:
        out.append("campaign codec FAILED: %s" % e)
        ok = False
    out.append("SELFTEST %s" % ("PASS" if ok else "FAIL"))
    report = "\n".join(out)
    print(report)
    try:
        import tempfile
        with open(os.path.join(tempfile.gettempdir(), "aowx_selftest_quest.txt"),
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

