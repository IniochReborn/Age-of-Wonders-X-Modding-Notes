#!/usr/bin/env python3
r"""Build the AoWx installer exe from a release zip.

Every release now ships BOTH upload\AoWx_1_37_<N>.zip (built first by
..\build_release_zip.py) and upload\AoWx_1_37_<N>_Setup.exe (built by this
script FROM that zip, so both always contain identical files).

Recipe:
  * extract upload\AoWx_1_37_<N>.zip to a temp staging dir
  * sanity-check the staging tree (AoWx.exe/AoWSetup.exe/directplay .reg
    present; retired Launcher / Scroll of Slickness absent)
  * compile AoWxInstaller.iss with ISCC, passing version/staging/output defines
  * remove the staging dir

The installer flow itself (splash styled like AoWSetup, vanilla-vs-update
choice, folder pick, separate-copy/overwrite-rename, permissions grant +
run-as-admin, retired-file cleanup, stability notice, directplay .reg import
by OS bitness, Discord link + "Close and run AoWSetup." finish) lives in
AoWxInstaller.iss.

Usage:
    python build_installer.py --ver 406
"""
import array, os, shutil, subprocess, sys, tempfile, wave, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.abspath(os.path.join(HERE, "..", ".."))
UPLOAD = os.path.join(GAME, "upload")

ISCC_CANDIDATES = [
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"),
    r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    r"C:\Program Files\Inno Setup 6\ISCC.exe",
]

MUST_HAVE = ["AoWx.exe", "AoWSetup.exe", "AoW.exe",
             "directplay-win32.reg", "directplay-win64.reg", "AoWxUpdater.exe", "AoWx.version"]
# UI resources embedded from the game dir (vanilla files not shipped in the zip)
GAME_AUX = ["Start.wav", r"Sfx\Events\NewEvent.WAV", r"Sfx\Events\Mana.WAV",
            r"Sfx\Moves\Horse1.WAV", r"Sfx\Moves\Horse2.WAV",
            r"X\Documentation\installer fun facts.txt"]
MUST_NOT_HAVE = ["Age of Wonders X - Launcher.exe",
                 "AoWx - Scroll of Slickness.ahk",
                 "AoWx - Scroll of Slickness.exe"]

# the install-loop SFX embedded at reduced volume (raw Charm.WAV is too loud)
CHARM_VOLUME = 0.5


def write_quiet_charm(dst):
    w = wave.open(os.path.join(GAME, r"Sfx\Attack\Charm.WAV"), "rb")
    params = w.getparams()
    frames = w.readframes(w.getnframes())
    w.close()
    assert params.sampwidth == 2, "Charm.WAV is not 16-bit PCM"
    a = array.array("h")
    a.frombytes(frames)
    for i in range(len(a)):
        a[i] = int(a[i] * CHARM_VOLUME)
    out = wave.open(dst, "wb")
    out.setparams(params)
    out.writeframes(a.tobytes())
    out.close()


def main():
    args = sys.argv[1:]
    if "--ver" not in args:
        print(__doc__)
        return 1
    ver = args[args.index("--ver") + 1]

    src = os.path.join(UPLOAD, f"AoWx_1_37_{ver}.zip")
    if not os.path.isfile(src):
        print(f"!! release zip not found: {src}")
        return 1

    iscc = next((p for p in ISCC_CANDIDATES if os.path.isfile(p)), None)
    if not iscc:
        print("!! ISCC.exe not found - install Inno Setup 6 (winget install JRSoftware.InnoSetup)")
        return 1

    for n in GAME_AUX:
        if not os.path.isfile(os.path.join(GAME, n)):
            print(f"!! game dir is missing installer resource: {n}")
            return 1

    staging = tempfile.mkdtemp(prefix=f"aowx_stage_{ver}_")
    aux = tempfile.mkdtemp(prefix=f"aowx_aux_{ver}_")
    try:
        charm = os.path.join(aux, "Charm.WAV")
        write_quiet_charm(charm)
        print(f"wrote volume-reduced install SFX ({CHARM_VOLUME:g}x) -> {charm}")

        print(f"extracting {os.path.basename(src)} -> {staging}")
        with zipfile.ZipFile(src) as z:
            z.extractall(staging)

        # auto-updater (2026-10-20): ship the freshly built AoWxUpdater.exe and the plain-text version file it
        # falls back on (primary source = AoWEPACK.dll's engine version immediates)
        upd = os.path.join(GAME, "patch scripts", "updater", "build", "AoWxUpdater.exe")
        if not os.path.isfile(upd):
            print("!! AoWxUpdater.exe not built - run patch scripts/updater/build_updater.py first")
            return 1
        shutil.copy2(upd, os.path.join(staging, "AoWxUpdater.exe"))
        with open(os.path.join(staging, "AoWx.version"), "w", encoding="ascii") as f:
            f.write(f"1.37.{ver}" + chr(10))
        print(f"added AoWxUpdater.exe + AoWx.version (1.37.{ver}) to staging")

        for n in MUST_HAVE:
            if not os.path.isfile(os.path.join(staging, n)):
                print(f"!! staging is missing required file: {n}")
                return 1
        for n in MUST_NOT_HAVE:
            if os.path.exists(os.path.join(staging, n)):
                print(f"!! staging contains retired file: {n}")
                return 1
        print("staging sanity checks passed")

        out_name = f"AoWx Installer (version 1.37.{ver})"
        cmd = [iscc,
               f"/DAppVer=1.37.{ver}",
               f"/DStagingDir={staging}",
               f"/DCharmWav={charm}",
               f"/DGameDir={GAME}",
               f"/DOutDir={UPLOAD}",
               f"/DOutName={out_name}",
               os.path.join(HERE, "AoWxInstaller.iss")]
        print("compiling installer (lzma2/max over ~270 MB, takes a few minutes)...")
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
