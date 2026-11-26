#!/usr/bin/env python3
r"""Build the AoWx Modding Tools release: a zip AND an installer exe.

The modding tools (AoWxBard/Gen/Img/Ink/Quest) ship SEPARATELY from the main
mod as of 2026-08-30. The main mod ships AoWSetup's Modding button + AoWxHub
(which greys out the tool buttons and points players at the download when the
tools are absent); this script packages the five tools themselves.

Outputs (in upload\):
  * AoWx_Modding_Tools_<ver>.zip - extract into the game folder
    (entries are X/Modding/<tool>.exe, so drag-drop merge works)
  * AoWx Modding Tools Installer (version <ver>).exe - Inno Setup wizard
    (AoWxToolsInstaller.iss) that finds the AoWx install via the mod's
    registry tree and installs into <game>\X\Modding

The shipped exes are taken from the LIVE X\Modding copies (the deployed,
tested builds), never from modding tools\dist. The launcher (AoWxSuite.exe,
ex-AoWxHub.exe) is deliberately NOT shipped here - it belongs to the main
mod release. (Tried moving it here 2026-09-01: pushes this installer to
302 MB, over AoWHeaven's 256 MB upload limit - keep it in the base mod.)

Version comes from modding tools\aowxlib\gui.py VERSION unless --ver is given.

Usage:
    py -3.10 build_tools_installer.py            # build zip + installer
    py -3.10 build_tools_installer.py --zip-only
    py -3.10 build_tools_installer.py --ver 1.01.0003
"""
import os, re, shutil, subprocess, sys, tempfile, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.abspath(os.path.join(HERE, "..", ".."))
UPLOAD = os.path.join(GAME, "upload")
MODDING = os.path.join(GAME, "X", "Modding")

TOOLS = ["AoWxBard.exe", "AoWxGen.exe", "AoWxImg.exe", "AoWxInk.exe",
         "AoWxQuest.exe"]

ISCC_CANDIDATES = [
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"),
    r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    r"C:\Program Files\Inno Setup 6\ISCC.exe",
]

# installer UI resources embedded from the game dir (same set as the main
# installer, minus the directplay bits)
GAME_AUX = ["Start.wav", r"Sfx\Events\NewEvent.WAV", r"Sfx\Events\Mana.WAV",
            r"Sfx\Attack\Charm.WAV",
            r"X\Documentation\installer fun facts.txt"]

sys.path.insert(0, HERE)
from build_installer import write_quiet_charm, CHARM_VOLUME  # noqa: E402


def tools_version():
    gui = os.path.join(GAME, "modding tools", "aowxlib", "gui.py")
    m = re.search(r'VERSION\s*=\s*["\']([\d.]+)["\']', open(gui).read())
    if not m:
        print(f"!! could not read VERSION from {gui}")
        sys.exit(1)
    return m.group(1)


def main():
    args = sys.argv[1:]
    ver = args[args.index("--ver") + 1] if "--ver" in args else tools_version()
    ver_us = ver.replace(".", "_")

    for n in TOOLS:
        if not os.path.isfile(os.path.join(MODDING, n)):
            print(f"!! live tool missing: X\\Modding\\{n}")
            return 1
    for n in GAME_AUX:
        if not os.path.isfile(os.path.join(GAME, n)):
            print(f"!! game dir is missing installer resource: {n}")
            return 1

    os.makedirs(UPLOAD, exist_ok=True)

    # ---- the zip (drag-drop layout: X/Modding/<tool>.exe) ----
    zpath = os.path.join(UPLOAD, f"AoWx_Modding_Tools_{ver_us}.zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for d in ("X/", "X/Modding/"):
            zi = zipfile.ZipInfo(d)
            zi.external_attr = (0o40755 << 16) | 0x10
            z.writestr(zi, b"")
        for n in TOOLS:
            z.write(os.path.join(MODDING, n), f"X/Modding/{n}")
    with zipfile.ZipFile(zpath) as z:
        assert z.testzip() is None
    print(f"WROTE {zpath}  ({os.path.getsize(zpath)/1e6:.1f} MB)")

    if "--zip-only" in args:
        return 0

    # ---- the installer ----
    iscc = next((p for p in ISCC_CANDIDATES if os.path.isfile(p)), None)
    if not iscc:
        print("!! ISCC.exe not found - install Inno Setup 6 (winget install JRSoftware.InnoSetup)")
        return 1

    staging = tempfile.mkdtemp(prefix=f"aowxtools_stage_{ver_us}_")
    aux = tempfile.mkdtemp(prefix=f"aowxtools_aux_{ver_us}_")
    try:
        for n in TOOLS:
            shutil.copy2(os.path.join(MODDING, n), os.path.join(staging, n))
        charm = os.path.join(aux, "Charm.WAV")
        write_quiet_charm(charm)
        print(f"wrote volume-reduced install SFX ({CHARM_VOLUME:g}x) -> {charm}")

        out_name = f"AoWx Modding Tools Installer (version {ver})"
        cmd = [iscc,
               f"/DAppVer={ver}",
               f"/DStagingDir={staging}",
               f"/DCharmWav={charm}",
               f"/DGameDir={GAME}",
               f"/DOutDir={UPLOAD}",
               f"/DOutName={out_name}",
               os.path.join(HERE, "AoWxToolsInstaller.iss")]
        print("compiling installer (lzma2/max over ~250 MB, takes a few minutes)...")
        r = subprocess.run(cmd, capture_output=True, text=True)
        tail = (r.stdout or "").strip().splitlines()[-15:]
        print("\n".join(tail))
        if r.returncode != 0:
            print(r.stderr)
            print(f"!! ISCC failed with code {r.returncode}")
            return 1

        out = os.path.join(UPLOAD, out_name + ".exe")
        print(f"\nWROTE {out}  ({os.path.getsize(out)/1e6:.1f} MB)")
        return 0
    finally:
        shutil.rmtree(staging, ignore_errors=True)
        shutil.rmtree(aux, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
