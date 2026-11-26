# -*- coding: utf-8 -*-
"""AoWx Map Generator — portable console launcher (AoWxGen, v6.5).

v6.5 (user spec): CLASSIC landmass reworked - one giant landmass cut by
large rivers, with real oceans only some of the time (was: fragmented
land under big oceans). Isles and continents are unchanged.

v6.4 (user spec): limited terrain inversion now grows MUSHROOM GROVES on
underground grass — mushrooms seed on UG grass at a much higher rate and
spread into adjacent/nearby grass, forming dense caps instead of lone ones.


Menu front-end over generate_map_v4.py. Built into a standalone exe with
PyInstaller; other players drop it anywhere inside their AoWx install (or point
it at one) and it writes finished maps to Scenario/Custom.

  1) Random Map Batch  — two maps of each size, default random settings
  2) Custom RNG Map    — size / levels / players / terrain inversion /
                         landmass preset / terrain style preset walkthrough
                         (v6.2: combine up to 3 style presets + strength 1-9)
  3) Image to Map      — one map of each size from a picture

Build (from the game root):
  py -m PyInstaller --onefile --console --name AoWxGen ^
     "patch scripts/mapgen/aowx_mapgen_launcher.py" ^
     --add-data "patch scripts/mapgen/generate_map_v4.py;." ^
     --add-data "patch scripts/mapgen/validate_map.py;." ^
     --add-data "patch scripts/mapgen/*.pkl;." ^
     --add-data "Scenario/Custom/xTemplate Small.hsm;templates" ^
     --add-data "Scenario/Custom/xTemplate Medium.hsm;templates" ^
     --add-data "Scenario/Custom/xTemplate Large.hsm;templates" ^
     --add-data "Scenario/Custom/xTemplate XLarge.hsm;templates"
"""
import os, sys, io, struct, zlib, random, runpy, shutil, pickle, tempfile, colorsys
import threading, time

VERSION = '6.5'
SIZES = ('S', 'M', 'L', 'XL')
TEMPLATE_NAMES = {'S': 'xTemplate Small.hsm', 'M': 'xTemplate Medium.hsm',
                  'L': 'xTemplate Large.hsm', 'XL': 'xTemplate XLarge.hsm'}


def data_dir():
    """Bundled resources: PyInstaller onefile extracts next to _MEIPASS."""
    return getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))


def find_game_root():
    """The AoWx install = the folder holding Release/Release.hss. Look at the
    exe's own location and upward, then ask."""
    cands = []
    exe_dir = os.path.dirname(os.path.abspath(
        sys.executable if getattr(sys, 'frozen', False) else __file__))
    p = exe_dir
    for _ in range(5):
        cands.append(p)
        p = os.path.dirname(p)
    cands.append(os.getcwd())
    for c in cands:
        if os.path.exists(os.path.join(c, 'Release', 'Release.hss')):
            return c
    print('Could not find an Age of Wonders install near the launcher.')
    while True:
        c = input('Path to your AoWx folder (the one with AoW.exe): ').strip('" ')
        if os.path.exists(os.path.join(c, 'Release', 'Release.hss')):
            return c
        print('  No Release/Release.hss there — try again.')


def ensure_templates(root):
    """Install the bundled empty template maps if the user doesn't have them."""
    dst_dir = os.path.join(root, 'Scenario', 'Custom')
    os.makedirs(dst_dir, exist_ok=True)
    for nm in TEMPLATE_NAMES.values():
        dst = os.path.join(dst_dir, nm)
        if not os.path.exists(dst):
            src = os.path.join(data_dir(), 'templates', nm)
            shutil.copyfile(src, dst)
            print('  installed template:', nm)


class _Spinner:
    """'Preparing to generate map. Please wait...' with slowly cycling dots
    (. -> .. -> ...) so the console never looks frozen. Shown immediately when
    generation starts; cleared the instant real output flows; comes back (as
    'Generating map. ...') whenever the generator goes silent again."""
    MSG0 = 'Preparing to generate map. Please wait'
    MSG1 = 'Generating map. Please wait'
    IDLE = 1.2                  # output silence before the spinner (re)appears
    _W = len(MSG0) + 6          # widest frame, for clearing the line

    def __init__(self, out):
        self.out = out
        self.lock = threading.Lock()
        self.visible = False
        self.started_output = False
        self.last = 0.0         # epoch of the generator's last write (0 = never)
        self._stop = threading.Event()
        self._th = threading.Thread(target=self._run, daemon=True)

    def _frame(self, n):
        msg = self.MSG1 if self.started_output else self.MSG0
        self.out.write('\r' + msg + '.' * n + '   ')
        self.out.flush()
        self.visible = True

    def _clear(self):
        if self.visible:
            self.out.write('\r' + ' ' * self._W + '\r')
            self.out.flush()
            self.visible = False

    def _run(self):
        n = 2                   # start() already showed frame 1
        while not self._stop.wait(0.5):
            with self.lock:
                if time.time() - self.last < self.IDLE:
                    n = 1
                    continue
                try:
                    self._frame(n)
                except Exception:
                    return
            n = n % 3 + 1

    def start(self):
        with self.lock:
            try:
                self._frame(1)
            except Exception:
                pass
        self._th.start()

    def wrote(self):
        """The generator produced output: clear our line first, mark activity."""
        with self.lock:
            self.last = time.time()
            self.started_output = True
            try:
                self._clear()
            except Exception:
                pass

    def stop(self):
        if self._stop.is_set():
            return
        self._stop.set()
        self._th.join(timeout=1.0)
        with self.lock:
            try:
                self._clear()
            except Exception:
                pass


class _SpinnerFeed:
    """stdout proxy: every generator write clears any visible spinner frame
    before reaching the console and resets the silence timer."""
    def __init__(self, inner, spin):
        self.inner = inner
        self.spin = spin

    def write(self, txt):
        self.spin.wrote()
        self.inner.write(txt)

    def flush(self):
        self.inner.flush()


def run_generator(root, seed, size, players=None, env=None, quiet_map=False):
    """Run generate_map_v4.py in-process (cwd = game root). Returns True/False."""
    genpath = os.path.join(data_dir(), 'generate_map_v4.py')
    old_argv, old_cwd = sys.argv, os.getcwd()
    old_env = {}
    env = dict(env or {})
    try:
        os.chdir(root)
        for k, v in env.items():
            old_env[k] = os.environ.get(k)
            os.environ[k] = v
        sys.argv = ['generate_map_v4.py', str(seed), size] + (
            [str(players)] if players else [])
        real = sys.stdout
        if quiet_map:
            _MAPCH = set("~.dw*,#L=^TBC$fto'u: ")

            class _Tee:
                skipnl = False
                def write(s, txt):
                    body = txt.rstrip('\n')
                    # suppress the big ASCII preview (rows are pure map charset)
                    if body and len(body) > 10 and all(c in _MAPCH for c in body):
                        s.skipnl = txt.endswith('\n') is False
                        return
                    if s.skipnl and txt == '\n':
                        s.skipnl = False
                        return
                    s.skipnl = False
                    real.write(txt)
                def flush(s):
                    real.flush()
            sys.stdout = _Tee()
        spin = _Spinner(real)
        sys.stdout = _SpinnerFeed(sys.stdout, spin)
        spin.start()
        try:
            runpy.run_path(genpath, run_name='__main__')
        finally:
            spin.stop()
            sys.stdout = real
        return True
    except SystemExit as ex:
        if ex.code in (0, None):
            return True
        print('  generator exited with error:', ex.code)
        return False
    except Exception as ex:
        print('  GENERATION FAILED:', repr(ex))
        return False
    finally:
        sys.argv = old_argv
        os.chdir(old_cwd)
        for k, v in old_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def validate(root, relpath):
    """Run the bundled validator quietly; return 'OK' / 'FAIL' / 'skipped'."""
    vpath = os.path.join(data_dir(), 'validate_map.py')
    if not os.path.exists(vpath):
        return 'skipped'
    old_argv, old_cwd, old_out = sys.argv, os.getcwd(), sys.stdout
    try:
        os.chdir(root)
        sys.argv = ['validate_map.py', relpath]
        sys.stdout = io.StringIO()
        runpy.run_path(vpath, run_name='__main__')
        txt = sys.stdout.getvalue()
        return 'FAIL' if 'FAIL' in txt else 'OK'
    except Exception:
        return 'skipped'
    finally:
        sys.stdout = old_out
        sys.argv = old_argv
        os.chdir(old_cwd)


def finish_map(root, produced, final):
    """Rename the generator's fixed output name to a seed-stamped one."""
    src = os.path.join(root, produced)
    dst = os.path.join(root, 'Scenario', 'Custom', final)
    if not os.path.exists(src):
        print('  ERROR: expected output missing:', produced)
        return None
    os.replace(src, dst)
    state = validate(root, os.path.join('Scenario', 'Custom', final))
    print('  -> %s  [validation: %s]' % (final, state))
    return dst


def ask(prompt, options, default=None):
    """options = list of (key, label). Returns the chosen key."""
    print()
    print(prompt)
    for i, (_, label) in enumerate(options, 1):
        print('  %d. %s' % (i, label))
    while True:
        c = input('> ').strip()
        if not c and default is not None:
            return default
        if c.isdigit() and 1 <= int(c) <= len(options):
            return options[int(c) - 1][0]
        print('  enter a number 1-%d' % len(options))


# ------------------------------------------------------------------ menu flows
def do_batch(root):
    print('\nRandom Map Batch: two maps of each size, default settings.\n')
    for sz in ('S', 'S', 'M', 'M', 'L', 'L', 'XL', 'XL'):
        seed = random.randrange(1_000_000)
        print('== %s map, seed %d' % (sz, seed))
        if run_generator(root, seed, sz, quiet_map=True):
            finish_map(root, 'Scenario/Custom/xGen6 %s.hsm' % sz,
                       'xGen6 %s (seed %d).hsm' % (sz, seed))


def do_custom(root):
    size = ask('Map size?', [('S', 'Small'), ('M', 'Medium'),
                             ('L', 'Large'), ('XL', 'Extra Large')])
    levels = ask('Map levels?', [
        ('1', 'Surface only'),
        ('2', 'Surface + Underground'),
        ('3', 'Surface + Underground + Depths')], default='3')
    while True:
        pl = input('\nAmount of players (2-12, blank = random)?\n> ').strip()
        if not pl:
            players = None
            break
        if pl.isdigit() and 2 <= int(pl) <= 12:
            players = int(pl)
            break
        print('  enter 2-12 or leave blank')
    inv = ask('Terrain inversion (underground worlds use surface terrain)?', [
        ('off', 'No'),
        ('limited', 'Limited - surface terrain seeps in around cave entrances.'),
        ('full', 'Extensive - entire "surface worlds" in underground layers.')],
        default='off')
    lm = ask('Surface landmass preset?', [
        ('classic', 'Classic - Default landmass generation.'),
        ('isles', 'Isles - Many small islands.'),
        ('continents', 'Continents - Few large landmasses.')], default='classic')
    _TPS = [('classic', 'Classic - Default mixed terrain generation.'),
            ('grasslands', 'Grasslands - Sparse, fertile plains and rivers.'),
            ('woodlands', 'Woodlands - Lush, densely vegetated forests.'),
            ('arctic', 'Arctic - Abundant snow and ice amidst frozen tundras.'),
            ('desert', 'Desert - Sparse deserts.'),
            ('highlands', 'Highlands - Hills and mountains.'),
            ('marshlands', 'Marshlands - Swamps and wetlands.'),
            ('desolate', 'Desolate - Wastelands and steppe.'),
            ('apocalyptic', 'Apocalyptic - Wastelands and lava.')]
    print()
    print('Terrain style preset(s)? Pick up to 3 to combine into one map,')
    print('in any order/format - "3 4 6", "3,4,6" or "346" all work.')
    print('(Classic cannot be combined. Blank = Classic.)')
    for i, (_, label) in enumerate(_TPS, 1):
        print('  %d. %s' % (i, label))
    while True:
        c = input('> ').strip()
        if not c:
            picks = [1]
            break
        if any(not (ch.isdigit() or ch in ' ,;+/') for ch in c):
            print('  enter preset numbers 1-9 (e.g. "3 4 6")')
            continue
        digs = [int(ch) for ch in c if ch.isdigit()]
        if not digs or any(d < 1 or d > 9 for d in digs):
            print('  enter preset numbers 1-9 (e.g. "3 4 6")')
            continue
        picks = []
        for d in digs:
            if d not in picks:
                picks.append(d)
        if len(picks) > 3:
            print('  at most 3 presets can be combined')
            continue
        if 1 in picks and len(picks) > 1:
            print('  Classic is the default mix - it cannot be combined')
            continue
        break
    tps = [_TPS[d - 1][0] for d in picks]
    tstr = 5
    if tps != ['classic']:
        while True:
            c = input('\nTerrain style preset strength'
                      ' (1 subtle - 9 extreme, blank = 5 default)?\n> ').strip()
            if not c:
                break
            if c.isdigit() and 1 <= int(c) <= 9:
                tstr = int(c)
                break
            print('  enter 1-9 or leave blank')
    seed = random.randrange(1_000_000)
    env = {'AOW_LEVELS': levels, 'AOW_XLEVEL': inv,
           'AOW_LANDMASS': lm, 'AOW_TPRESET': ','.join(tps),
           'AOW_TSTRENGTH': str(tstr)}
    print('\n== %s map, seed %d (levels=%s, inversion=%s, %s, %s str %d)'
          % (size, seed, levels, inv, lm, '+'.join(tps), tstr))
    if run_generator(root, seed, size, players=players, env=env):
        tag = ('' if tps == ['classic']
               else ' ' + '+'.join(t.capitalize() for t in tps))
        finish_map(root, 'Scenario/Custom/xGen6 %s.hsm' % size,
                   'xGen6 %s%s (seed %d).hsm' % (size, tag, seed))


# ---------------------------------------------------------- image-to-map flow
def _tbl(dd, p):
    b = dd[p]; p += 1; nd = 0
    if b & 0x80:
        nd = struct.unpack_from('<I', dd, p)[0]; p += 4
    nb = b & 0x7F; f = {}
    for _ in range(nb):
        f[dd[p]] = dd[p + 1]; p += 2
    for _ in range(nd):
        t, o = struct.unpack_from('<II', dd, p); f[t] = o; p += 8
    return f, p


def _classify(r, g, b):
    h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
    if s < 0.16:
        return (1, None)
    if 0.45 < h < 0.75:
        return (0, None)
    if 0.20 <= h <= 0.45:
        return (1, 'veg' if (v < 0.50 or (s > 0.70 and v < 0.68)) else None)
    if (h < 0.065 or h > 0.92) and s > 0.35:
        return (2, 'mtn')
    if 0.06 <= h < 0.14 and v < 0.55:
        return (2, 'mtn')
    if 0.02 <= h < 0.14:
        return (2, None)
    return (1, None)


def image_override(root, img_path, size):
    """Port of image_to_map.py: picture -> terrain/veg/mtn grids for one size.
    Returns the path of the override pickle."""
    from PIL import Image
    template = os.path.join(root, 'Scenario', 'Custom', TEMPLATE_NAMES[size])
    inner = zlib.decompress(open(template, 'rb').read()[5:])
    r0, base = _tbl(inner, 0x13)
    kids, kb = _tbl(inner, base + r0[1])
    coff = kb + sorted(kids.items(), key=lambda x: x[1])[0][1]
    cf, cb = _tbl(inner, coff + 4)
    W, H = inner[cb + cf[3]], inner[cb + cf[4]]
    lk, lkb = _tbl(inner, cb + cf[1])
    lf, lb = _tbl(inner, lkb + sorted(lk.items())[0][1] + 4)
    s, e = lb + 2, lb + lf[1]
    paint = [[False] * W for _ in range(H)]
    q, idx = s, 0
    while q < e and idx < W * H:
        L = struct.unpack_from('<I', inner, q)[0]
        if L == 14 and struct.unpack_from('<H', inner, q + 4 + 3)[0] != 0x0557:
            paint[idx // W][idx % W] = True
        q += 4 + L; idx += 1
    xs = [x for y in range(H) for x in range(W) if paint[y][x]]
    ys = [y for y in range(H) for x in range(W) if paint[y][x]]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    iw, ih = x1 - x0 + 1, y1 - y0 + 1

    src = Image.open(img_path).convert('RGB')
    sw, sh = src.size
    target = iw / ih
    if sw / sh > target:
        nw = int(sh * target)
        src = src.crop(((sw - nw) // 2, 0, (sw - nw) // 2 + nw, sh))
    else:
        nh = int(sw / target)
        src = src.crop((0, (sh - nh) // 2, sw, (sh - nh) // 2 + nh))
    src = src.resize((iw, ih), Image.BILINEAR)
    sp = src.load()

    grid = [[None] * W for _ in range(H)]
    vegset, mtnset = set(), set()
    for y in range(H):
        for x in range(W):
            if not paint[y][x]:
                continue
            r, g, b = sp[x - x0, y - y0]
            t, dc = _classify(r, g, b)
            grid[y][x] = t
            if dc == 'veg':
                vegset.add((x, y))
            elif dc == 'mtn':
                mtnset.add((x, y))
    ng = [row[:] for row in grid]        # de-speckle: lone hexes -> neighbourhood
    for y in range(H):
        for x in range(W):
            if grid[y][x] is None:
                continue
            cnt = {}
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < H and 0 <= nx < W and grid[ny][nx] is not None:
                        cnt[grid[ny][nx]] = cnt.get(grid[ny][nx], 0) + 1
            if cnt.get(grid[y][x], 0) <= 2:
                ng[y][x] = max(cnt, key=cnt.get)
    ov = os.path.join(tempfile.gettempdir(), 'aowx_img_override_%s.pkl' % size)
    pickle.dump(dict(grid=ng, veg=vegset, mtn=mtnset,
                     image=os.path.basename(img_path)), open(ov, 'wb'))
    return ov


def do_image(root):
    print('\nImage to Map: makes one map of each size from a picture.')
    print('Colours: blue=water, green=grass (dark green=forest), tan=desert,')
    print('red-brown=mountains, grey=grass. Any common image format works.')
    while True:
        img = input('\nPath to the image file:\n> ').strip('" ')
        if os.path.isfile(img):
            break
        print('  file not found — try again (you can drag & drop it here)')
    try:
        import PIL  # noqa: F401
    except ImportError:
        print('ERROR: this build is missing Pillow — image mode unavailable.')
        return
    base = os.path.splitext(os.path.basename(img))[0][:24]
    for sz in SIZES:
        seed = random.randrange(1_000_000)
        print('== %s map from %s, seed %d' % (sz, base, seed))
        try:
            ov = image_override(root, img, sz)
        except Exception as ex:
            print('  image processing failed:', repr(ex))
            return
        if run_generator(root, seed, sz, env={'AOW_IMG_OVERRIDE': ov},
                         quiet_map=True):
            finish_map(root, 'Scenario/Custom/xImg6 %s.hsm' % sz,
                       'xImg6 %s %s (seed %d).hsm' % (sz, base, seed))


def _set_console_icon():
    """Stamp the console window (title bar + taskbar) with the exe's own icon.
    conhost picks the icon up through Windows' icon cache, which can serve a
    stale image after an in-place rebuild — setting it explicitly bypasses
    every cache layer."""
    if not getattr(sys, 'frozen', False) or os.name != 'nt':
        return
    try:
        import ctypes
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if not hwnd:
            return
        hicon = ctypes.windll.shell32.ExtractIconW(0, sys.executable, 0)
        if hicon and hicon > 1:
            WM_SETICON = 0x80
            ctypes.windll.user32.SendMessageW(hwnd, WM_SETICON, 0, hicon)
            ctypes.windll.user32.SendMessageW(hwnd, WM_SETICON, 1, hicon)
    except Exception:
        pass


def main():
    _set_console_icon()
    print('=' * 62)
    print('  AoWx Map Generator (version %s)' % VERSION)
    print('  Generated maps will be located in the Scenario/Custom folder'
          ' of your AoWx install.')
    print('=' * 62)
    root = find_game_root()
    print('\nAoWx install: %s' % root)
    ensure_templates(root)
    while True:
        choice = ask('What would you like to make?', [
            ('batch', 'Random Map Batch - Create two maps of each size using '
                      'default random map generation settings.'),
            ('custom', 'Custom RNG Map - Create a random map based on user '
                       'preferences.'),
            ('image', 'Image to Map - Turn a picture into playable maps '
                      '(one per size).'),
            ('quit', 'Quit')])
        if choice == 'batch':
            do_batch(root)
        elif choice == 'custom':
            do_custom(root)
        elif choice == 'image':
            do_image(root)
        else:
            break


if __name__ == '__main__':
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        pass
    except Exception as ex:
        print('\nUNEXPECTED ERROR:', repr(ex))
        input('press Enter to close')
