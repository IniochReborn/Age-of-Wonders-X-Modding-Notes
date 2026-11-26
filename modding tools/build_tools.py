"""Build AoWxIlb.exe and AoWxCampaign.exe with PyInstaller.

    python build_tools.py           build both
    python build_tools.py ilb       build only the ILB editor
    python build_tools.py campaign  build only the campaign editor
"""
import os, subprocess, sys, shutil, time

HERE = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(HERE, "dist")
BUILD = os.path.join(HERE, "build")

EXCLUDE = [
    "PySide6.QtNetwork", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.Qt3DCore",
    "PySide6.QtMultimedia", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
    "PySide6.QtOpenGL", "PySide6.QtCharts", "PySide6.QtDataVisualization",
    "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtPdf", "PySide6.QtDesigner",
    "tkinter", "unittest", "pydoc", "doctest", "numpy", "matplotlib",
]

TARGETS = {
    "img": dict(
        splash="Splash_xImg.BMP",
        script="AoWxImg.py", name="AoWxImg", icon="assets/aowximg.ico",
        data=[("assets/ilb_presets.json", "assets"),
              ("assets/aowximg.ico", "assets"),
              ("assets/bard_moss.png", "assets"),
              ("assets/bard_stone.png", "assets"),
              ("assets/bard_emblem.png", "assets")],
        hidden=["PIL.Image", "PIL.BmpImagePlugin", "PIL.PngImagePlugin"],
        collect=[],
    ),
    "quest": dict(
        splash="Splash_xQuest.BMP",
        script="AoWxQuest.py", name="AoWxQuest", icon="assets/aowxquest.ico",
        data=[("assets/worldmap.jpg", "assets"),
              ("assets/worldmap_annotated.jpg", "assets"),
              ("assets/aowxquest.ico", "assets"),
              ("assets/bard_moss.png", "assets"),
              ("assets/bard_stone.png", "assets"),
              ("assets/bard_emblem.png", "assets")],
        hidden=["spellchecker"],
        collect=["spellchecker"],
    ),
    "ink": dict(
        splash="Splash_xInk.BMP",
        script="AoWxInk.py", name="AoWxInk", icon="assets/aowxink.ico",
        data=[("assets/aowxink.ico", "assets"),
              ("assets/bard_moss.png", "assets"),
              ("assets/bard_stone.png", "assets"),
              ("assets/bard_emblem.png", "assets")],
        hidden=["spellchecker"],
        collect=["spellchecker"],
    ),
    "gen": dict(
        splash="Splash_xGen.BMP",
        script="AoWxGen.py", name="AoWxGen", icon="assets/aowxgen.ico",
        data=[("assets/aowxgen.ico", "assets"),
              ("assets/bard_moss.png", "assets"),
              ("assets/bard_stone.png", "assets"),
              ("assets/bard_emblem.png", "assets")]
             + [("../patch scripts/mapgen/" + n, "mapgen") for n in
                ("generate_map_v4.py", "validate_map.py", "ab_masks.pkl",
                 "decor_palette.pkl", "mtn_records.pkl", "obj_extra.pkl",
                 "obj_records.pkl", "player_kit.pkl", "unit_pool.pkl",
                 "veg_records.pkl", "_img_override.pkl")]
             + [("../Scenario/Custom/" + n, "templates") for n in
                ("xTemplate Small.hsm", "xTemplate Medium.hsm",
                 "xTemplate Large.hsm", "xTemplate XLarge.hsm")],
        # heapq: used by the bundled generate_map_v4.py, which PyInstaller
        # never analyses (it ships as data and runs via runpy)
        hidden=["PIL.Image", "heapq"],
        collect=[],
    ),
    "hub": dict(
        script="AoWxHub.py", name="AoWxHub", icon="assets/aowx_dragon.ico",
        data=[("assets/aowxhub_bg.png", "assets"),
              ("assets/aowx_dragon.ico", "assets"),
              ("assets/bard_moss.png", "assets"),
              ("assets/bard_stone.png", "assets"),
              ("assets/bard_emblem.png", "assets")],
        hidden=[],
        collect=[],
    ),
    "bard": dict(
        splash="Splash_xBard.BMP",
        script="AoWxBard.py", name="AoWxBard", icon="assets/aowxbard.ico",
        data=[("assets/aowxbard.ico", "assets"),
              ("assets/bard_moss.png", "assets"),
              ("assets/bard_stone.png", "assets"),
              ("assets/bard_emblem.png", "assets")],
        hidden=[],
        collect=[],
    ),
}
# old names kept so existing muscle memory still works
TARGETS["ilb"] = TARGETS["art"] = TARGETS["img"]
TARGETS["campaign"] = TARGETS["quest"]


def build(key):
    t = TARGETS[key]
    sep = ";" if os.name == "nt" else ":"
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
           "--onefile", "--windowed",
           "--name", t["name"],
           "--distpath", DIST, "--workpath", BUILD,
           "--specpath", BUILD,
           "--paths", HERE]
    icon = t.get("icon")
    if icon:
        ip = os.path.join(HERE, icon.replace("/", os.sep))
        if os.path.isfile(ip):
            cmd += ["--icon", ip]
    # bootloader splash: baked from EDIMAGES at build time (shown instantly,
    # during onefile extraction; the app closes it when its window is ready).
    # Shown at the BMP's native pixel size, like AoWDevX shows Splash.bmp.
    # Missing artwork just means that tool is built without a splash.
    sp = t.get("splash")
    if sp:
        src = os.path.join(os.path.dirname(HERE), "EDIMAGES", sp)
        if os.path.isfile(src):
            from PIL import Image
            os.makedirs(BUILD, exist_ok=True)
            png = os.path.join(BUILD, t["name"] + "_splash.png")
            Image.open(src).save(png)
            cmd += ["--splash", png]
        else:
            print("note: %s not found - %s built without a splash"
                  % (src, t["name"]))
    for src, dst in t["data"]:
        cmd += ["--add-data", "%s%s%s" % (os.path.join(HERE, src.replace("/", os.sep)), sep, dst)]
    for h in t["hidden"]:
        cmd += ["--hidden-import", h]
    for c in t["collect"]:
        cmd += ["--collect-data", c]
    for e in EXCLUDE:
        cmd += ["--exclude-module", e]
    cmd.append(os.path.join(HERE, t["script"]))
    print("\n=== building %s ===" % t["name"])
    t0 = time.time()
    r = subprocess.run(cmd, cwd=HERE)
    if r.returncode != 0:
        print("FAILED: %s" % t["name"])
        return False
    exe = os.path.join(DIST, t["name"] + (".exe" if os.name == "nt" else ""))
    print("built %s  (%.1f MB, %.0f s)"
          % (exe, os.path.getsize(exe) / 1048576.0, time.time() - t0))
    return True


if __name__ == "__main__":
    keys = sys.argv[1:] or ["img", "quest", "ink", "bard", "gen", "hub"]
    ok = all(build(k) for k in keys if k in TARGETS)
    sys.exit(0 if ok else 1)


