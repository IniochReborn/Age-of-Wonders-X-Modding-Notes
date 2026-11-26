#!/usr/bin/env python3
r"""
AoWx updater - verify a published release exactly the way the updater will (2026-10-20).

Downloads https://aowx.org/update/[test/]latest.json + .sig, checks the signature with the public key
(aowx_update_public.pem next to this script), then downloads the installer from installer_url and checks its size and
SHA-256 against the signed notice.  --local checks the files in upload\site\update instead of the website.

Usage: py -3.10 aowx_verify_release.py [--channel test] [--local] [--installer path] [--no-download]
"""
import argparse, base64, hashlib, json, os, sys, urllib.request
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SITE_UPDATE = os.path.join(ROOT, "upload", "site", "update")
PUB = os.path.join(HERE, "aowx_update_public.pem")
BASE = "https://aowx.org/update/"


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "AoWx-Updater-Verify", "Cache-Control": "no-cache"})
    return urllib.request.urlopen(req, timeout=60).read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", choices=("public", "test"), default="public")
    ap.add_argument("--local", action="store_true")
    ap.add_argument("--installer")
    ap.add_argument("--no-download", action="store_true")
    a = ap.parse_args()
    sub = "" if a.channel == "public" else "test/"
    if a.local:
        d = SITE_UPDATE if a.channel == "public" else os.path.join(SITE_UPDATE, "test")
        body = open(os.path.join(d, "latest.json"), "rb").read()
        sig = base64.b64decode(open(os.path.join(d, "latest.json.sig"), "rb").read().strip())
    else:
        body = fetch(BASE + sub + "latest.json")
        sig = base64.b64decode(fetch(BASE + sub + "latest.json.sig").strip())
    pub = serialization.load_pem_public_key(open(PUB, "rb").read())
    try:
        pub.verify(sig, body, padding.PKCS1v15(), hashes.SHA256())
    except Exception:
        print("SIGNATURE INVALID - an updater would REFUSE this notice."); return 1
    n = json.loads(body)
    print("signature OK - version %s (%s), %s, sha256 %s" % (n["version"], n["channel"], n["installer_name"], n["sha256"]))
    if a.installer:
        data = open(a.installer, "rb").read()
    elif a.no_download:
        return 0
    else:
        print("downloading " + n["installer_url"] + " ...")
        data = fetch(n["installer_url"])
    if len(data) != n["installer_size"] or hashlib.sha256(data).hexdigest() != n["sha256"]:
        print("INSTALLER MISMATCH - an updater would REFUSE and delete it."); return 1
    print("installer OK (%d bytes, sha256 matches the signed notice)" % len(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
