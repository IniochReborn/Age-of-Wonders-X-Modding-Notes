"""Random-map-generator engine adapter for the AoWxGen GUI.

The actual generator is the proven `generate_map_v4.py` from
`patch scripts\\mapgen` (bundled verbatim, with its .pkl data and the empty
template maps, exactly like the old console AoWxGen build). This module is the
GUI-friendly version of the old console launcher's plumbing
(aowx_mapgen_launcher.py v6.5): same seeds, env-var knobs, output names and
validation - minus every input()/spinner console-ism. Output text is streamed
to a callback instead of stdout.
"""
import colorsys
import io
import os
import pickle
import runpy
import shutil
import struct
import sys
import tempfile
import zlib

SIZES = ("S", "M", "L", "XL")
SIZE_LABELS = {"S": "Small", "M": "Medium", "L": "Large", "XL": "Extra Large"}
TEMPLATE_NAMES = {"S": "xTemplate Small.hsm", "M": "xTemplate Medium.hsm",
                  "L": "xTemplate Large.hsm", "XL": "xTemplate XLarge.hsm"}

LEVELS = [("1", "Surface only"),
          ("2", "Surface + Underground"),
          ("3", "Surface + Underground + Depths")]
INVERSIONS = [
    ("off", "No"),
    ("limited", "Limited - surface terrain seeps in around cave entrances"),
    ("full", "Extensive - entire \"surface worlds\" in underground layers")]
LANDMASSES = [("classic", "Classic - Default landmass generation"),
              ("isles", "Isles - Many small islands"),
              ("continents", "Continents - Few large landmasses")]
STYLES = [("classic", "Classic - Default mixed terrain generation"),
          ("grasslands", "Grasslands - Sparse, fertile plains and rivers"),
          ("woodlands", "Woodlands - Lush, densely vegetated forests"),
          ("arctic", "Arctic - Abundant snow and ice amidst frozen tundras"),
          ("desert", "Desert - Sparse deserts"),
          ("highlands", "Highlands - Hills and mountains"),
          ("marshlands", "Marshlands - Swamps and wetlands"),
          ("desolate", "Desolate - Wastelands and steppe"),
          ("apocalyptic", "Apocalyptic - Wastelands and lava")]

_MAPCH = set("~.dw*,#L=^TBC$fto'u: ")


def data_dir():
    """Where generate_map_v4.py + its .pkl files live."""
    if getattr(sys, "frozen", False):
        return os.path.join(sys._MEIPASS, "mapgen")
    return os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "patch scripts", "mapgen")


def templates_dir():
    if getattr(sys, "frozen", False):
        return os.path.join(sys._MEIPASS, "templates")
    return os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "Scenario", "Custom")


def find_game_root(extra=()):
    """The AoWx install = the folder holding Release\\Release.hss, looked for
    at the exe's location and upward. Returns None when not found."""
    cands = list(extra)
    exe_dir = os.path.dirname(os.path.abspath(
        sys.executable if getattr(sys, "frozen", False) else __file__))
    p = exe_dir
    for _ in range(6):
        cands.append(p)
        p = os.path.dirname(p)
    cands.append(os.getcwd())
    for c in cands:
        if c and os.path.exists(os.path.join(c, "Release", "Release.hss")):
            return c
    return None


def is_game_root(path):
    return bool(path) and os.path.exists(os.path.join(path, "Release",
                                                      "Release.hss"))


def ensure_templates(root, out_cb=None):
    dst_dir = os.path.join(root, "Scenario", "Custom")
    os.makedirs(dst_dir, exist_ok=True)
    for nm in TEMPLATE_NAMES.values():
        dst = os.path.join(dst_dir, nm)
        if not os.path.exists(dst):
            shutil.copyfile(os.path.join(templates_dir(), nm), dst)
            if out_cb:
                out_cb("installed template: %s\n" % nm)


class _CbOut:
    """stdout proxy feeding the GUI, optionally suppressing the generator's
    big ASCII map preview (rows made purely of the map charset)."""

    def __init__(self, cb, quiet_map):
        self.cb = cb
        self.quiet = quiet_map
        self.skipnl = False

    def write(self, txt):
        if self.quiet:
            body = txt.rstrip("\n")
            if body and len(body) > 10 and all(c in _MAPCH for c in body):
                self.skipnl = not txt.endswith("\n")
                return
            if self.skipnl and txt == "\n":
                self.skipnl = False
                return
            self.skipnl = False
        self.cb(txt)

    def flush(self):
        pass


def run_generator(root, seed, size, players=None, env=None, out_cb=print,
                  quiet_map=False):
    """Run generate_map_v4.py in-process (cwd = game root). True on success."""
    genpath = os.path.join(data_dir(), "generate_map_v4.py")
    old_argv, old_cwd, old_out = sys.argv, os.getcwd(), sys.stdout
    old_env = {}
    env = dict(env or {})
    try:
        os.chdir(root)
        for k, v in env.items():
            old_env[k] = os.environ.get(k)
            os.environ[k] = v
        sys.argv = ["generate_map_v4.py", str(seed), size] + (
            [str(players)] if players else [])
        sys.stdout = _CbOut(out_cb, quiet_map)
        runpy.run_path(genpath, run_name="__main__")
        return True
    except SystemExit as ex:
        if ex.code in (0, None):
            return True
        out_cb("generator exited with error: %s\n" % ex.code)
        return False
    except Exception as ex:
        out_cb("GENERATION FAILED: %r\n" % ex)
        return False
    finally:
        sys.stdout = old_out
        sys.argv = old_argv
        os.chdir(old_cwd)
        for k, v in old_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def validate(root, relpath):
    vpath = os.path.join(data_dir(), "validate_map.py")
    if not os.path.exists(vpath):
        return "skipped"
    old_argv, old_cwd, old_out = sys.argv, os.getcwd(), sys.stdout
    try:
        os.chdir(root)
        sys.argv = ["validate_map.py", relpath]
        sys.stdout = io.StringIO()
        runpy.run_path(vpath, run_name="__main__")
        txt = sys.stdout.getvalue()
        return "FAIL" if "FAIL" in txt else "OK"
    except Exception:
        return "skipped"
    finally:
        sys.stdout = old_out
        sys.argv = old_argv
        os.chdir(old_cwd)


def finish_map(root, produced, final, out_cb=print):
    """Rename the generator's fixed output name to a seed-stamped one."""
    src = os.path.join(root, produced)
    dst = os.path.join(root, "Scenario", "Custom", final)
    if not os.path.exists(src):
        out_cb("ERROR: expected output missing: %s\n" % produced)
        return None
    os.replace(src, dst)
    state = validate(root, os.path.join("Scenario", "Custom", final))
    out_cb("-> %s  [validation: %s]\n" % (final, state))
    return dst


# ------------------------------------------------------------- image-to-map
def _tbl(dd, p):
    b = dd[p]; p += 1; nd = 0
    if b & 0x80:
        nd = struct.unpack_from("<I", dd, p)[0]; p += 4
    nb = b & 0x7F; f = {}
    for _ in range(nb):
        f[dd[p]] = dd[p + 1]; p += 2
    for _ in range(nd):
        t, o = struct.unpack_from("<II", dd, p); f[t] = o; p += 8
    return f, p


def _classify(r, g, b):
    h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
    if s < 0.16:
        return (1, None)
    if 0.45 < h < 0.75:
        return (0, None)
    if 0.20 <= h <= 0.45:
        return (1, "veg" if (v < 0.50 or (s > 0.70 and v < 0.68)) else None)
    if (h < 0.065 or h > 0.92) and s > 0.35:
        return (2, "mtn")
    if 0.06 <= h < 0.14 and v < 0.55:
        return (2, "mtn")
    if 0.02 <= h < 0.14:
        return (2, None)
    return (1, None)


def image_override(root, img_path, size):
    """Picture -> terrain/veg/mtn override pickle for one size (verbatim port
    of the console launcher's image mode)."""
    from PIL import Image
    template = os.path.join(root, "Scenario", "Custom", TEMPLATE_NAMES[size])
    inner = zlib.decompress(open(template, "rb").read()[5:])
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
        L = struct.unpack_from("<I", inner, q)[0]
        if L == 14 and struct.unpack_from("<H", inner, q + 4 + 3)[0] != 0x0557:
            paint[idx // W][idx % W] = True
        q += 4 + L; idx += 1
    xs = [x for y in range(H) for x in range(W) if paint[y][x]]
    ys = [y for y in range(H) for x in range(W) if paint[y][x]]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    iw, ih = x1 - x0 + 1, y1 - y0 + 1

    src = Image.open(img_path).convert("RGB")
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
            if dc == "veg":
                vegset.add((x, y))
            elif dc == "mtn":
                mtnset.add((x, y))
    ng = [row[:] for row in grid]       # de-speckle: lone hexes -> majority
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
    ov = os.path.join(tempfile.gettempdir(), "aowx_img_override_%s.pkl" % size)
    pickle.dump(dict(grid=ng, veg=vegset, mtn=mtnset,
                     image=os.path.basename(img_path)), open(ov, "wb"))
    return ov
