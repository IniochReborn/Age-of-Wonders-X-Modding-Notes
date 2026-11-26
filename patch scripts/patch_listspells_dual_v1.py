#!/usr/bin/env python3
r"""
AoWEPACK.dll: the EDITOR lists dual-sphere spells (2026-10-13).

AoWDevX fills its spell list through TSpellControl.ListSpells(control, target, cx = msAll) @0x55779E9C.  msAll is
the exported word 0x558E8048 = 0x00FF (the eight vanilla spheres); ListSpells keeps a spell only when
    sphere = [spell+0x20] <= 0x0F  AND  bit `sphere` of the mask is set
so every spell of the dual-sphere pairs 9..22 (patch_dual_sphere_plumbing_v1.py) was dropped: the mask has no bit
above 7, and spheres 16..22 fail the <= 0x0F test outright.  TSpellControl.ListSpells has no caller inside the
engine and is imported only by AoWDevX.exe (AoWx.exe imports TPlayerMagicControl.ListSpells, a different method),
so the test is simply widened in place: `cmp al,0x0F / ja skip` (4 B @0x55779ED5) becomes `cmp al,8 / ja ACCEPT` -
spheres 0..8 still go through the mask, anything above (= a sphere pair) is always listed.
No cave, no reloc under the bytes.  Backup <game>\backup\AoWEPACK.dll.bak_listspells.
"""
import argparse, os, shutil, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DEFAULT_DLL = game_file("AoWEPACK.dll")
BAK_SUFFIX = ".bak_listspells"
CODE_V2F = 0x55700C00
SITE = 0x55779ED5
OLD = bytes.fromhex("3c0f7708")       # cmp al,0x0F ; ja 0x55779EE1 (skip)
NEW = bytes.fromhex("3c08770a")       # cmp al,8    ; ja 0x55779EE3 (accept)


def write_inplace(path, data):
    with open(path, "r+b") as f:
        f.seek(0); f.write(data); f.truncate(len(data))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dll", default=DEFAULT_DLL)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    a = ap.parse_args()
    d = open(a.dll, "rb").read()
    off = SITE - CODE_V2F
    cur = d[off:off + 4]
    state = "vanilla" if cur == OLD else "applied" if cur == NEW else "OTHER(%s)" % cur.hex()
    print("ListSpells sphere test @%#x: %s" % (SITE, state))
    if state.startswith("OTHER"): print("ABORT"); return 1
    if a.revert:
        if cur != NEW: print("not applied"); return 0
        out = bytearray(d); out[off:off + 4] = OLD; write_inplace(a.dll, bytes(out)); print("reverted"); return 0
    if cur == NEW: print("already applied"); return 0
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(a.dll, BAK_SUFFIX)
    if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    out = bytearray(d); out[off:off + 4] = NEW; write_inplace(a.dll, bytes(out))
    assert open(a.dll, "rb").read() == bytes(out); print("Written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
