"""Shared look-and-feel pieces for the AoWx tools (AoWxBard, AoWxGen, ...).

MossBack paints one of the game's stone backgrounds across a container,
kept subtle at low opacity:
  moss  - the long flat green stones of the game's text windows, tiled
          (Int\\GenericT.ilb image 0, TextBackGround.BMP, seamless)
  stone - the setup screen's dark cracked stone wall, scaled to cover
          (Int\\Scenes\\LSetup.ILB image 0, LSBackg.BMP, border cropped)

draw_backdrop paints the same texture straight onto any widget, either at
the theme's normal opacity or at FAINT for panes that hold text/rows - the
texture stays "barely there" behind real content.

EMBLEM_PATH is the carved celtic panel (Int\\FCWin.ILB image 34, FC-Party.BMP,
game-cropped at its gold outline) the tools centre on their empty work areas:
draw a BLACK rect first, then the emblem at 55% - the backdrop must never show
through the panel, and it stays subtle by fading toward black.
"""
import ctypes
import os
import sys
from ctypes import wintypes

from PySide6.QtCore import QEvent, QObject, QRect, QSize, Qt
from PySide6.QtGui import (QColor, QCursor, QIcon, QLinearGradient, QPainter,
                           QPainterPath, QPen, QPixmap)
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QMainWindow,
                               QToolButton, QWidget)

VERSION = "1.01.0002"

HERE = getattr(sys, "_MEIPASS",
               os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EMBLEM_PATH = os.path.join(HERE, "assets", "bard_emblem.png")

# theme -> (file, normal opacity, tiled?)
THEMES = {"moss": ("bard_moss.png", 0.25, True),
          "stone": ("bard_stone.png", 0.22, False)}
FAINT = 0.10                 # "barely visible" opacity behind populated panes
_PIX = {}


def theme_pixmap(theme):
    if theme not in THEMES:
        theme = "moss"
    if theme not in _PIX:
        _PIX[theme] = QPixmap(os.path.join(HERE, "assets", THEMES[theme][0]))
    return _PIX[theme]


def draw_backdrop(p, w, h, theme, opacity=None):
    """Paint the moss/stone texture over a w x h area.
    opacity None = the theme's normal opacity; pass FAINT behind content."""
    if theme not in THEMES:
        theme = "moss"
    pm = theme_pixmap(theme)
    if pm.isNull():
        return
    _, normal, tiled = THEMES[theme]
    p.setOpacity(normal if opacity is None else opacity)
    if tiled:
        p.drawTiledPixmap(QRect(0, 0, w, h), pm)
    else:
        sc = max(w / pm.width(), h / pm.height())
        tw, th = int(pm.width() * sc), int(pm.height() * sc)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.drawPixmap((w - tw) // 2, (h - th) // 2, tw, th, pm)
    p.setOpacity(1.0)


# COLORREF (0x00BBGGRR) for dialog title bars: the dark red-tinted caption
# the user's wallpaper gave the windows via Mica (sampled #2a1b1c) - pinned
# so a wallpaper change can't take it away. DWMWA_CAPTION_COLOR needs Win 11.
CAPTION_COLOR = 0x001C1B2A

# main windows draw their own caption with the Mica look made permanent:
# black edges, the red tint in the middle
CAPTION_H = 34
CAPTION_GRADIENT = [(0.0, "#0d0d0d"), (0.5, "#3b1f21"), (1.0, "#0d0d0d")]


def _pin_caption(widget):
    try:
        import ctypes
        from ctypes import wintypes
        # explicit HWND type: a bare int is passed as c_int and a 64-bit
        # window handle gets truncated, silently pinning nothing
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(int(widget.winId())),
            wintypes.DWORD(35),                        # DWMWA_CAPTION_COLOR
            ctypes.byref(wintypes.DWORD(CAPTION_COLOR)),
            wintypes.DWORD(4))
    except Exception:
        pass                                           # pre-Win11: keep stock


class _CaptionPinner(QObject):
    """App-wide filter: every top-level window gets the pinned caption colour
    the moment it is shown (main windows, dialogs, message boxes)."""

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Show and isinstance(obj, QWidget) and obj.isWindow():
            _pin_caption(obj)
        return False


def pin_dark(app):
    """Lock the suite's look against OS theme changes: force the dark colour
    scheme the decoration was designed against (a Windows light/dark flip no
    longer restyles the tools) and pin the red-tinted caption colour on every
    window. Must run after QApplication is created.
    Fusion is forced because Win10's fallback style (windowsvista) cannot
    render a dark palette, so setColorScheme(Dark) is a no-op there."""
    app.setStyle("Fusion")
    app.styleHints().setColorScheme(Qt.ColorScheme.Dark)
    app._caption_pinner = _CaptionPinner(app)
    app.installEventFilter(app._caption_pinner)


def paint_chrome(widget, theme):
    """The faint moss/stone wash a whole window carries behind its plain
    chrome (toolbars, side panels, dialog forms). Opaque panes such as tables
    and text edits still paint their own Base over it."""
    p = QPainter(widget)
    p.fillRect(widget.rect(), widget.palette().window())
    draw_backdrop(p, widget.width(), widget.height(), theme, FAINT)
    p.end()


class ChromeDialog(QDialog):
    """QDialog with the suite's faint chrome backdrop. The theme is taken
    from the nearest ancestor with a bg_theme attribute (every Main window
    has one) unless passed explicitly."""

    def __init__(self, parent=None, theme=None):
        super().__init__(parent)
        if theme is None:
            w = parent
            while w is not None and getattr(w, "bg_theme", None) is None:
                w = w.parentWidget()
            theme = getattr(w, "bg_theme", "moss")
        self.bg_theme = theme

    def paintEvent(self, ev):
        paint_chrome(self, self.bg_theme)
        super().paintEvent(ev)


def _caption_glyph(kind):
    """Windows-style caption glyphs (min / max / restore / close), drawn
    bright enough for the dark gradient bar."""
    pm = QPixmap(16, 16)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor("#e2dcdc"), 1.2))
    if kind == "min":
        p.drawLine(3, 8, 13, 8)
    elif kind == "max":
        p.drawRect(3, 3, 10, 10)
    elif kind == "restore":
        p.drawRect(3, 5, 8, 8)
        p.drawLine(6, 3, 13, 3)
        p.drawLine(13, 3, 13, 10)
    else:                                              # close
        p.drawLine(4, 4, 12, 12)
        p.drawLine(12, 4, 4, 12)
    p.end()
    return QIcon(pm)


class GradientTitleBar(QWidget):
    """Custom-drawn caption: black edges fading to the pinned red in the
    middle - the look the user's wallpaper used to give via Mica, made
    permanent. Icon + title are painted, the three buttons are widgets."""

    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.setFixedHeight(CAPTION_H)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addStretch(1)
        self.b_min = self._button("min", win.showMinimized)
        self.b_max = self._button("max", self._toggle_max)
        self.b_close = self._button("close", win.close, close=True)
        for b in (self.b_min, self.b_max, self.b_close):
            lay.addWidget(b)
        win.windowTitleChanged.connect(lambda _t: self.update())
        win.windowIconChanged.connect(lambda _i: self.update())
        win.installEventFilter(self)

    def eventFilter(self, obj, ev):
        if ev.type() in (QEvent.WindowStateChange, QEvent.ActivationChange):
            self.b_max.setIcon(_caption_glyph(
                "restore" if self.win.isMaximized() else "max"))
            self.update()
        return False

    def _button(self, kind, slot, close=False):
        b = QToolButton(self)
        b.setFixedSize(46, CAPTION_H)
        b.setIcon(_caption_glyph(kind))
        b.setIconSize(QSize(16, 16))
        b.setFocusPolicy(Qt.NoFocus)
        b.clicked.connect(slot)
        b.setStyleSheet(
            "QToolButton{border:none;background:transparent;}"
            "QToolButton:hover{background:%s;}"
            % ("#c42b1c" if close else "rgba(255,255,255,25)"))
        return b

    def _toggle_max(self):
        if self.win.isMaximized():
            self.win.showNormal()
        else:
            self.win.showMaximized()

    def paintEvent(self, ev):
        p = QPainter(self)
        g = QLinearGradient(0, 0, self.width(), 0)
        active = self.win.isActiveWindow()
        for pos, col in CAPTION_GRADIENT:
            c = QColor(col)
            if not active:                             # dim like real captions
                c = QColor(c.red() * 11 // 20, c.green() * 11 // 20,
                           c.blue() * 11 // 20)
            g.setColorAt(pos, c)
        p.fillRect(self.rect(), g)
        x = 10
        ic = self.win.windowIcon()
        if not ic.isNull():
            p.drawPixmap(x, (CAPTION_H - 18) // 2, ic.pixmap(18, 18))
            x += 26
        p.setPen(QColor("#d6d0d0" if active else "#8a8484"))
        avail = max(10, self.b_min.x() - x - 8)
        p.drawText(x, 0, avail, CAPTION_H, Qt.AlignVCenter | Qt.AlignLeft,
                   p.fontMetrics().elidedText(self.win.windowTitle(),
                                              Qt.ElideMiddle, avail))
        p.end()


class _NCCALCSIZE_PARAMS(ctypes.Structure):
    _fields_ = [("rgrc", wintypes.RECT * 3), ("lppos", ctypes.c_void_p)]


class CaptionedMainWindow(QMainWindow):
    """QMainWindow wearing the GradientTitleBar. The native caption is eaten
    via WM_NCCALCSIZE while the frame styles stay, so drag, snap, minimise
    animations, double-click-maximise and the DWM shadow all survive;
    WM_NCHITTEST serves the resize borders and marks the gradient bar as the
    caption (its buttons excepted)."""

    def __init__(self):
        super().__init__()
        self._titlebar = GradientTitleBar(self)
        self.setMenuWidget(self._titlebar)

    def showEvent(self, ev):
        super().showEvent(ev)
        try:
            class _MARGINS(ctypes.Structure):
                _fields_ = [("l", ctypes.c_int), ("r", ctypes.c_int),
                            ("t", ctypes.c_int), ("b", ctypes.c_int)]
            ctypes.windll.dwmapi.DwmExtendFrameIntoClientArea(
                wintypes.HWND(int(self.winId())),
                ctypes.byref(_MARGINS(0, 0, 1, 0)))   # keep the DWM shadow
        except Exception:
            pass

    def nativeEvent(self, etype, message):
        if etype != b"windows_generic_MSG":
            return False, 0
        msg = wintypes.MSG.from_address(int(message))
        if msg.message == 0x0083 and msg.wParam:       # WM_NCCALCSIZE
            r = _NCCALCSIZE_PARAMS.from_address(msg.lParam).rgrc[0]
            if self.isMaximized():
                u = ctypes.windll.user32
                pad = u.GetSystemMetrics(32) + u.GetSystemMetrics(92)
                r.left += pad
                r.top += pad
                r.right -= pad
                r.bottom -= pad
            return True, 0                             # client = whole window
        if msg.message == 0x0084:                      # WM_NCHITTEST
            u = ctypes.windll.user32
            rc = wintypes.RECT()
            u.GetWindowRect(wintypes.HWND(msg.hWnd), ctypes.byref(rc))
            x = ctypes.c_short(msg.lParam & 0xFFFF).value
            y = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value
            if not self.isMaximized():
                bw = u.GetSystemMetrics(32) + u.GetSystemMetrics(92)
                left = x < rc.left + bw
                right = x >= rc.right - bw
                top = y < rc.top + bw
                bottom = y >= rc.bottom - bw
                if top:
                    return True, 13 if left else 14 if right else 12
                if bottom:
                    return True, 16 if left else 17 if right else 15
                if left:
                    return True, 10
                if right:
                    return True, 11
            lp = self._titlebar.mapFromGlobal(QCursor.pos())
            if self._titlebar.rect().contains(lp):
                #  HTCLIENT over the buttons, HTCAPTION elsewhere on the bar
                return True, 1 if self._titlebar.childAt(lp) else 2
            return True, 1
        return False, 0


# ---------------------------------------------------------------------------
# start-up splash: PyInstaller's bootloader splash (--splash, baked from
# EDIMAGES\Splash_<tool>.BMP by build_tools.py). It appears the instant the
# exe runs - during onefile extraction, long before Python - and the app
# dismisses it the moment its loaded main window is ready to show.
# ---------------------------------------------------------------------------
def close_splash():
    """Dismiss the bootloader splash; call right before showing the main
    window. A no-op when running from source or built without a splash."""
    try:
        import pyi_splash
        pyi_splash.close()
    except Exception:
        pass


class ChromePage(QWidget):
    """Tab page carrying the faint backdrop. Tab panes paint an opaque fill
    that masks the window's chrome texture, so the page lays it on again -
    over the style's fill, keeping the pane's own shade."""

    def __init__(self, theme_cb):
        super().__init__()
        self._theme_cb = theme_cb

    def paintEvent(self, ev):
        p = QPainter(self)
        draw_backdrop(p, self.width(), self.height(), self._theme_cb(), FAINT)
        p.end()
        super().paintEvent(ev)


class MossBack(QWidget):
    THEMES = THEMES

    def __init__(self, theme="moss"):
        super().__init__()
        self.theme = theme if theme in THEMES else "moss"

    def set_theme(self, theme):
        if theme in THEMES:
            self.theme = theme
            self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.fillRect(self.rect(), self.palette().window())
        draw_backdrop(p, self.width(), self.height(), self.theme)
        p.end()


def draw_emblem_centred(painter, emblem, vw, vh, max_frac=0.42):
    """Draw the celtic panel centred in a vw x vh area over a black cutout.
    Returns the panel height used (for laying out a hint under it)."""
    if emblem.isNull():
        return 0
    th = max(emblem.height(), min(int(vh * max_frac), emblem.height() * 2))
    tw = int(emblem.width() * th / emblem.height())
    ex, ey = (vw - tw) // 2, (vh - th) // 2
    painter.fillRect(ex, ey, tw, th, QColor(0, 0, 0))
    painter.setOpacity(0.55)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)
    painter.drawPixmap(ex, ey, tw, th, emblem)
    painter.setOpacity(1.0)
    return th


def draw_hint_under(painter, palette, vw, vh, emblem_h, hint, pt=12):
    """The 'drop files here' style hint, centred under the emblem."""
    painter.setPen(palette.placeholderText().color())
    f = painter.font()
    f.setPointSize(pt)
    painter.setFont(f)
    painter.drawText(0, (vh + emblem_h) // 2 + 6, vw, 60,
                     Qt.AlignHCenter | Qt.AlignTop, hint)


def play_icon():
    """A bright gold play triangle. The stock SP_MediaPlay icon is dark grey
    and near-invisible on the dark toolbar - every tool's main action uses
    this instead."""
    icon = QIcon()
    for s in (16, 20, 24, 32, 48):
        pm = QPixmap(s, s)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        m = s * 0.14
        path = QPainterPath()
        path.moveTo(m, m * 0.7)
        path.lineTo(s - m * 0.5, s / 2)
        path.lineTo(m, s - m * 0.7)
        path.closeSubpath()
        g = QLinearGradient(0, 0, 0, s)
        g.setColorAt(0.0, QColor("#ffe9a8"))
        g.setColorAt(0.5, QColor("#f0c25c"))
        g.setColorAt(1.0, QColor("#c8892a"))
        p.setPen(QPen(QColor("#4a3608"), max(1.0, s / 16.0)))
        p.setBrush(g)
        p.drawPath(path)
        p.end()
        icon.addPixmap(pm)
    return icon
