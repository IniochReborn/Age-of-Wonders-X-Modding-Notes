"""
AoWxHub - the Modding hub AoWSetup's "Modding" button opens.

A borderless window with the exact size (420x525) and look of AoWSetup's
home screen: its framed artwork on top, then seven full-width stone-slab
buttons (assets/aowxhub_bg.png, composed from AoWSetup.exe's home BMP by
patch scripts/make_hub_background.py). Each tool button carries the tool
name plus its splash-screen description, drawn in the home screen's own
button font (MS Sans Serif bold).
"""
import os
import subprocess
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QAbstractButton, QApplication,
                               QMessageBox, QWidget)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from aowxlib.gui import close_splash, pin_dark                       # noqa: E402

APP = "AoWxHub"
HERE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
# the home window's TRUE runtime client size (FormCreate ends with
# SetClientWidth(398)/SetClientHeight(449); the DFM's 420x525 is only the
# install-mode layout)
W, H = 398, 449

# AoWDevX on top, the AoWx tools alphabetical below it
# (name, splash-image description, exe relative to the game root)
TOOLS = [
    ("AoWDevX", "Editor for Age of Wonders X", "AoWDevX.exe"),
    ("AoWxBard", "Music Tool for Age of Wonders X",
     os.path.join("X", "Modding", "AoWxBard.exe")),
    ("AoWxGen", "Map Generator for Age of Wonders X",
     os.path.join("X", "Modding", "AoWxGen.exe")),
    ("AoWxImg", "Image Tool for Age of Wonders X",
     os.path.join("X", "Modding", "AoWxImg.exe")),
    ("AoWxInk", "Text Editor for Age of Wonders X",
     os.path.join("X", "Modding", "AoWxInk.exe")),
    ("AoWxQuest", "Campaign Editor for Age of Wonders X",
     os.path.join("X", "Modding", "AoWxQuest.exe")),
]
# where players get the separately-shipped modding tools package
# (link will be updated later)
TOOLS_URL = "https://aow.heavengames.com/downloads/lister.php?category=misc"

# slab rects on aowxhub_bg.png (see make_hub_background.py)
BTN_X, BTN_W = 14, 370
TOOL_Y0, TOOL_H, TOOL_PITCH = 171, 36, 39
EXIT_Y, EXIT_H = 407, 22

# the home screen's button font: MS Sans Serif bold (the app runs DPI-unaware
# with the GDI font engine - see main() - so the genuine bitmap font renders
# and Windows stretches the window exactly like it stretches AoWSetup)
FONT_NAME = QFont("MS Sans Serif", 10)
FONT_NAME.setBold(True)
FONT_DESC = QFont("MS Sans Serif", 8)
FONT_DESC.setBold(True)


def game_root():
    """Walk up from the exe (X\\Modding) / source dir to the game folder."""
    bases = [os.getcwd()]
    if getattr(sys, "frozen", False):
        bases.insert(0, os.path.dirname(sys.executable))
    else:
        bases.insert(0, os.path.dirname(os.path.abspath(__file__)))
    for base in bases:
        d = os.path.abspath(base)
        for _ in range(6):
            if os.path.isfile(os.path.join(d, "AoWSetup.exe")):
                return d
            nd = os.path.dirname(d)
            if nd == d:
                break
            d = nd
    return None


class SlabButton(QAbstractButton):
    """Flat button drawn straight onto the background's stone slab: bold
    name, dimmer description, hover/press tints like the home screen.
    A greyed slab (modding tools not installed) stays clickable — the click
    shows the download dialog — but drops the hand cursor, the hover/press
    tints and the press nudge, and paints its text washed out."""

    def __init__(self, name, desc, parent):
        super().__init__(parent)
        self.name = name
        self.desc = desc
        self.greyed = False
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)

    def set_greyed(self, greyed):
        if self.greyed == greyed:
            return
        self.greyed = greyed
        self.setCursor(Qt.ArrowCursor if greyed else Qt.PointingHandCursor)
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        if not self.greyed:
            if self.isDown():
                p.fillRect(self.rect(), QColor(0, 0, 0, 70))
            elif self.underMouse():
                p.fillRect(self.rect(), QColor(255, 255, 255, 28))
        dx = 1 if self.isDown() and not self.greyed else 0
        name_pen = QColor("#8a8178") if self.greyed else QColor("#1a0f08")
        desc_pen = QColor("#7e7468") if self.greyed else QColor("#43301c")
        p.setPen(name_pen)
        if self.desc:
            p.setFont(FONT_NAME)
            p.drawText(12 + dx, dx, self.width() - 24, self.height() // 2 + 2,
                       Qt.AlignLeft | Qt.AlignBottom, self.name)
            p.setFont(FONT_DESC)
            p.setPen(desc_pen)
            p.drawText(12 + dx, self.height() // 2 + 1 + dx,
                       self.width() - 24, self.height() // 2 - 2,
                       Qt.AlignLeft | Qt.AlignTop, self.desc)
        else:
            p.setFont(FONT_NAME)
            p.drawText(self.rect().adjusted(dx, dx, dx, dx),
                       Qt.AlignCenter, self.name)
        p.end()

    def enterEvent(self, ev):
        self.update()
        super().enterEvent(ev)

    def leaveEvent(self, ev):
        self.update()
        super().leaveEvent(ev)


class Hub(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setFixedSize(W, H)
        self.setWindowTitle("AoWx Modding")
        ico = os.path.join(HERE, "assets", "aowx_dragon.ico")
        if os.path.isfile(ico):
            self.setWindowIcon(QIcon(ico))
        self.bg = QPixmap(os.path.join(HERE, "assets", "aowxhub_bg.png"))
        self.root = game_root()
        self._drag = None

        self.tool_btns = []          # (button, exe) for the X\Modding tools
        for i, (name, desc, exe) in enumerate(TOOLS):
            b = SlabButton(name, desc, self)
            b.setGeometry(BTN_X, TOOL_Y0 + i * TOOL_PITCH, BTN_W, TOOL_H)
            b.clicked.connect(lambda _c=False, e=exe: self.launch(e))
            if name != "AoWDevX":
                self.tool_btns.append((b, exe))
        b = SlabButton("Back", "", self)
        b.setGeometry(BTN_X, EXIT_Y, BTN_W, EXIT_H)
        b.clicked.connect(self.go_back)
        self.refresh_tools()

        # open exactly where the AoWSetup window is (it lingers ~4 s after
        # launching us before closing itself); centred when run standalone
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            user32.FindWindowW.restype = wintypes.HWND
            hwnd = user32.FindWindowW("TLoaderForm", None)
            if hwnd:
                r = wintypes.RECT()
                user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(r))
                self.move(r.left, r.top)
        except Exception:
            pass

    def go_back(self):
        """Reopen AoWSetup's home screen and close the hub. ShellExecute (not
        Popen) so AoWSetup's elevation prompt works; stay open if it fails or
        the user cancels the prompt."""
        exe = self.root and os.path.join(self.root, "AoWSetup.exe")
        if not exe or not os.path.isfile(exe):
            QMessageBox.warning(self, APP, "AoWSetup.exe not found.")
            return
        import ctypes
        ret = ctypes.windll.shell32.ShellExecuteW(
            None, "open", exe, None, self.root, 1)
        if ret > 32:
            self.close()

    def tool_installed(self, rel):
        return bool(self.root) and os.path.isfile(os.path.join(self.root, rel))

    def refresh_tools(self):
        """Grey out the AoWx tool slabs whose exe is not installed.
        AoWDevX ships with the mod itself and is never greyed."""
        for b, exe in self.tool_btns:
            b.set_greyed(not self.tool_installed(exe))

    def tools_missing_dialog(self):
        box = QMessageBox(self)
        box.setWindowTitle(APP)
        box.setTextFormat(Qt.RichText)
        box.setText(
            'AoWx modding tools not found. Please '
            '<a href="%s">download</a> and install.' % TOOLS_URL)
        box.setStandardButtons(QMessageBox.Ok)
        box.exec()

    def launch(self, rel):
        if not self.root:
            QMessageBox.warning(self, APP, "Game folder not found - keep "
                                "AoWxHub.exe inside X\\Modding.")
            return
        exe = os.path.join(self.root, rel)
        if not os.path.isfile(exe):
            # a tool from the separate modding-tools package is missing
            if os.sep + "Modding" + os.sep in exe:
                self.refresh_tools()
                self.tools_missing_dialog()
            else:
                QMessageBox.warning(self, APP, "Not found:\n" + exe)
            return
        # installed since startup (or ever greyed by mistake): un-grey and run
        self.refresh_tools()
        subprocess.Popen([exe], cwd=os.path.dirname(exe))

    def paintEvent(self, ev):
        p = QPainter(self)
        p.drawPixmap(0, 0, W, H, self.bg)
        p.end()

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self._drag = ev.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, ev):
        if self._drag is not None and ev.buttons() & Qt.LeftButton:
            self.move(ev.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, ev):
        self._drag = None

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(ev)


def selftest():
    out = []
    ok = True
    for a in ("assets/aowxhub_bg.png", "assets/aowx_dragon.ico"):
        p = os.path.join(HERE, a.replace("/", os.sep))
        present = os.path.isfile(p)
        out.append("%s: %s" % (a, "ok" if present else "MISSING"))
        ok &= present
    pm = QPixmap(os.path.join(HERE, "assets", "aowxhub_bg.png"))
    out.append("background: %dx%d" % (pm.width(), pm.height()))
    ok &= (pm.width(), pm.height()) == (W, H)
    out.append("SELFTEST %s" % ("PASS" if ok else "FAIL"))
    report = "\n".join(out)
    print(report)
    try:
        import tempfile
        with open(os.path.join(tempfile.gettempdir(), "aowx_selftest_hub.txt"),
                  "w", encoding="utf-8") as fh:
            fh.write(report)
    except Exception:
        pass
    return 0 if ok else 1


def main():
    # DPI-unaware + GDI font engine: Windows bitmap-stretches this window
    # exactly like it stretches the DPI-unaware AoWSetup (same on-screen
    # size), and the genuine bitmap "MS Sans Serif" renders like the home
    # screen's buttons instead of a DirectWrite substitute.
    os.environ.setdefault("QT_QPA_PLATFORM", "windows:dpiawareness=0:fontengine=gdi")
    app = QApplication(sys.argv)
    app.setApplicationName(APP)
    pin_dark(app)
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    w = Hub()
    close_splash()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
