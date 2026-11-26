#!/usr/bin/env python3
r"""
Build the Cloudflare Pages deployment zip for aowx.org (2026-10-20).

Every Cloudflare direct-upload deployment REPLACES the whole site, so the zip must always contain the manual AND the
signed update notices:  upload\index.zip = index.html + every file under upload\site\ (update\latest.json,
update\latest.json.sig, update\test\..., etc.).
2026-10-24: index.html now comes from the GAME manual <game>\.AoWx Manual.html (the one build_manual_from_game.py
regenerates and the install zip ships) and upload\index.html is overwritten with it, so the website can never lag the
release again (1.37.423 + 424 went live with the 422 changelog: upload\index.html was not re-copied and the signer
rebuilt index.zip from that stale copy).  --expect-version 1.37.N refuses unless the manual's changelog has
"Version 1.37.N" (the signer passes the version it signs).

Usage: py -3.10 build_site_zip.py [--manual <path>] [--out <zip path>] [--expect-version 1.37.N]
"""
import argparse, os, re, shutil, sys, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
UP = os.path.join(ROOT, "upload")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manual", default=os.path.join(ROOT, ".AoWx Manual.html"))
    ap.add_argument("--out", default=os.path.join(UP, "index.zip"))
    ap.add_argument("--expect-version", default=None)
    a = ap.parse_args()
    site = os.path.join(UP, "site")
    if not os.path.isfile(a.manual):
        print("manual not found: " + a.manual); return 1
    html = open(a.manual, encoding="utf-8", errors="ignore").read()
    vers = sorted(set(re.findall(r"Version (1\.37\.\d+)", html)), key=lambda v: [int(x) for x in v.split(".")])
    print("manual: %s  (newest changelog entry: %s)" % (a.manual, vers[-1] if vers else "NONE"))
    if a.expect_version and a.expect_version not in vers:
        print("REFUSING: the manual has no 'Version %s' changelog entry - regenerate it (build_manual_from_game.py) "
              "before building the site zip." % a.expect_version); return 1
    idx = os.path.join(UP, "index.html")
    if os.path.abspath(a.manual) != os.path.abspath(idx):
        shutil.copy2(a.manual, idx)
        print("upload\index.html refreshed from the manual")
    if not os.path.isfile(os.path.join(site, "update", "latest.json")):
        print("WARNING: upload\\site\\update\\latest.json is missing - deploying this would REMOVE the public update notice.")
    with zipfile.ZipFile(a.out, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(a.manual, "index.html")
        for dp, _, fs in os.walk(site):
            for f in sorted(fs):
                p = os.path.join(dp, f)
                z.write(p, os.path.relpath(p, site).replace(os.sep, "/"))
    with zipfile.ZipFile(a.out) as z:
        for n in z.namelist():
            print("  " + n)
    print("written " + a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
