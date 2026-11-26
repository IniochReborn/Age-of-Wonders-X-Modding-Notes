#!/usr/bin/env python3
r"""Cut a release zip by re-reading the PREVIOUS release's file list from disk.

The release zip has always been assembled by hand; this script encodes the
recipe that 402->403->404 used, so a cut is reproducible and auditable:

  * take the previous zip's namelist IN ORDER (it is the authoritative list of
    what ships -- notably `X/Documentation/changelogs.txt` is NOT in it, since
    players get the changelog baked into `.AoWx Manual.html`)
  * re-read every one of those paths from the live game directory
  * refuse to write if anything on the list is missing from disk
  * report exactly which entries changed against the previous zip, so the diff
    can be eyeballed before upload

Also refreshes the website manual zips (`.AoWx Manual.zip` / `index.zip`,
single entry `index.html`) from the freshly built `.AoWx Manual.html`.

Usage:
    py -3.10 build_release_zip.py --prev 403 --next 404          # dry run
    py -3.10 build_release_zip.py --prev 403 --next 404 --apply
    py -3.10 build_release_zip.py --prev 403 --next 404 --apply --manual

`--drop a;b;c` removes entries from the shipped list (exact zip paths,
semicolon-separated) -- for files a release deliberately retires
(405->406 dropped the Launcher and Scroll of Slickness).

`--add a;b;c` appends new entries (exact zip paths; end with / for a
directory entry) -- for files a release newly ships. The 407 cut adds
`X/Modding/;X/Modding/AoWxSuite.exe` (the launcher ships with the MAIN mod --
moving it to the tools installer pushes that exe over AoWHeaven's 256 MB
upload limit; the five tools ship separately via build_tools_installer.py).
"""
import hashlib, os, sys, zipfile

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
UPLOAD = os.path.join(GAME, "upload")
MANUAL = os.path.join(GAME, ".AoWx Manual.html")


def md5(b):
    return hashlib.md5(b).hexdigest()


def main():
    args = sys.argv[1:]
    prev = args[args.index("--prev") + 1] if "--prev" in args else "403"
    nxt = args[args.index("--next") + 1] if "--next" in args else "404"
    apply = "--apply" in args
    do_manual = "--manual" in args
    drop = set(args[args.index("--drop") + 1].split(";")) if "--drop" in args else set()
    add = args[args.index("--add") + 1].split(";") if "--add" in args else []

    src = os.path.join(UPLOAD, f"AoWx_1_37_{prev}.zip")
    dst = os.path.join(UPLOAD, f"AoWx_1_37_{nxt}.zip")
    zin = zipfile.ZipFile(src)
    names = zin.namelist()
    print(f"previous release: {os.path.basename(src)}  ({len(names)} entries)")

    if drop:
        unknown = drop - set(names)
        if unknown:
            print(f"!! --drop name(s) not in previous zip: {sorted(unknown)}")
            return 1
        for n in sorted(drop):
            print(f"dropping retired entry: {n}")
        names = [n for n in names if n not in drop]

    for n in add:
        if n in names:
            print(f"note: --add entry already shipped, skipping: {n}")
        else:
            print(f"adding new entry: {n}")
            names.append(n)

    # The game never creates its save dir (TFileStream.Create won't make parent
    # dirs), so a fresh install without X/Save/ dies with EFCreateError on the
    # first save write. Guarantee the dir entries even when cutting from a zip
    # that predates the fix (405 was patched by hand on 2026-08-15).
    for required in ("X/", "X/Save/"):
        if required not in names:
            print(f"note: prev zip lacks required dir entry {required} - adding")
            names.append(required)

    missing, changed, total = [], [], 0
    payload = []
    for n in names:
        disk = os.path.join(GAME, n.replace("/", os.sep))
        if n.endswith("/"):
            # directory entry: ship it (data=None), zips drop empty dirs otherwise
            if os.path.isdir(disk):
                payload.append((n, None))
            else:
                missing.append(n)
            continue
        if not os.path.isfile(disk):
            missing.append(n)
            continue
        data = open(disk, "rb").read()
        total += len(data)
        payload.append((n, data))
        try:
            old = zin.read(n)
        except KeyError:            # --add entry: not in the previous zip
            changed.append((n, 0, len(data)))
            continue
        if md5(data) != md5(old):
            changed.append((n, len(old), len(data)))

    print(f"read {len(payload)} files from disk, {total/1e6:.1f} MB uncompressed")
    if missing:
        print(f"!! {len(missing)} listed file(s) MISSING from disk:")
        for m in missing:
            print("   ", m)
        print("refusing to cut a release that drops files; fix or edit the list")
        return 1

    print(f"changed vs {prev}: {len(changed)}")
    for n, a, b in changed:
        print(f"   {n}  ({a} -> {b} bytes)")

    if not apply:
        print("\nDry run only - rerun with --apply to write", os.path.basename(dst))
        return 0

    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as z:
        for n, data in payload:
            if data is None:  # directory entry
                zi = zipfile.ZipInfo(n)
                zi.external_attr = (0o40755 << 16) | 0x10
                z.writestr(zi, b"")
            else:
                z.writestr(n, data)
    print(f"\nWROTE {os.path.basename(dst)}  "
          f"({os.path.getsize(dst)/1e6:.1f} MB, {len(payload)} entries)")

    with zipfile.ZipFile(dst) as z:
        assert z.namelist() == [n for n, _ in payload], "entry order/list mismatch"
        bad = z.testzip()
        assert bad is None, f"corrupt entry: {bad}"
    print("verified: entry list matches and all entries decompress cleanly")

    if do_manual:
        html = open(MANUAL, "rb").read()
        for name in (".AoWx Manual.zip", "index.zip"):
            p = os.path.join(UPLOAD, name)
            with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as z:
                z.writestr("index.html", html)
            print(f"refreshed {name} ({os.path.getsize(p)/1e6:.1f} MB, "
                  f"index.html = {len(html)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
