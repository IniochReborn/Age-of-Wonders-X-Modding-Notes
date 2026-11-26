"""Tiny UI driver for the running game window: click / key / screenshot (downscaled + optional crop)."""
import sys, time, ctypes
from ctypes import wintypes
from PIL import ImageGrab, Image
u = ctypes.windll.user32
u.SetProcessDPIAware()
OUT = r"C:\Users\<user>\.claude\jobs\47241cad\tmp"

def find_game():
    h = u.FindWindowW(None, "Age of Wonders")
    if not h:
        h = u.FindWindowW(None, "Age of Wonders X")
    return h

def focus():
    h = find_game()
    if h: u.SetForegroundWindow(h)
    return h

def win_rect():
    h = find_game(); r = wintypes.RECT(); u.GetClientRect(h, ctypes.byref(r))
    p = wintypes.POINT(0, 0); u.ClientToScreen(h, ctypes.byref(p))
    return p.x, p.y, r.right, r.bottom

def click(x, y, button="left", double=False):
    """x, y = CLIENT coordinates of the game window."""
    ox, oy, w, h = win_rect(); sx, sy = ox + x, oy + y
    u.SetCursorPos(sx, sy); time.sleep(0.08)
    down, up = (0x0002, 0x0004) if button == "left" else (0x0008, 0x0010)
    for _ in range(2 if double else 1):
        u.mouse_event(down, 0, 0, 0, 0); time.sleep(0.06); u.mouse_event(up, 0, 0, 0, 0); time.sleep(0.12)

def move(x, y):
    ox, oy, w, h = win_rect(); u.SetCursorPos(ox + x, oy + y)

def key(vk, hold=0.05):
    u.keybd_event(vk, 0, 0, 0); time.sleep(hold); u.keybd_event(vk, 0, 2, 0); time.sleep(0.1)

def text(s):
    for ch in s:
        vk = u.VkKeyScanW(ord(ch)) & 0xFF; key(vk)

def shot(name, crop=None, scale=3):
    ox, oy, w, h = win_rect(); im = ImageGrab.grab((ox, oy, ox + w, oy + h))
    if crop: im = im.crop(crop)
    small = im.resize((im.width // scale, im.height // scale), Image.LANCZOS) if scale > 1 else im
    p = OUT + "\\" + name + ".png"; small.save(p); print("shot", name, "client", (w, h), "crop", crop, "->", small.size)
    return im

if __name__ == "__main__":
    cmd = sys.argv[1:]
    i = 0
    while i < len(cmd):
        c = cmd[i]
        if c == "click": click(int(cmd[i+1]), int(cmd[i+2])); i += 3
        elif c == "rclick": click(int(cmd[i+1]), int(cmd[i+2]), "right"); i += 3
        elif c == "dclick": click(int(cmd[i+1]), int(cmd[i+2]), double=True); i += 3
        elif c == "move": move(int(cmd[i+1]), int(cmd[i+2])); i += 3
        elif c == "key": key(int(cmd[i+1], 0)); i += 2
        elif c == "text": text(cmd[i+1]); i += 2
        elif c == "sleep": time.sleep(float(cmd[i+1])); i += 2
        elif c == "shot": shot(cmd[i+1]); i += 2
        elif c == "shotc":
            shot(cmd[i+1], tuple(int(v) for v in cmd[i+2].split(",")), int(cmd[i+3])); i += 4
        elif c == "focus": focus(); i += 1
        elif c == "rect": print("rect", win_rect()); i += 1
        else: raise SystemExit("unknown " + c)
