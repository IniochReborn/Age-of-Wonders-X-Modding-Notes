r"""
AoWx.exe: always launch `AoWxUpdater.exe --game-start <pid>` on the first title frame (2026-10-22).

patch_exe_updater_title (v1-v4) skips the launch when the updater Mode = Off.  The updater now also starts the
Discord Rich Presence helper (AoWxPresence.exe) from --game-start, before its own Mode check (Off -> it logs and
returns without checking), so the game must launch it in every mode.

Site: in the title 'frame' routine
    cmp dword ptr [MODE], 2 ; je fr_1 ; mov esi, L_pgs("--game-start ") ; mov edi, 0 ; mov ecx, 1 ; call launch
the `je fr_1` (74 xx) becomes `nop; nop`.  Found by pattern (exactly one hit), the je bytes carry no relocation.
Dry-run default; --apply / --revert.  Backup <game>\backup\AoWx.exe.bak_preslaunch.
"""
import argparse, os, re, shutil, sys

import pefile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

EXE = game_file("AoWx.exe")
PAT = re.compile(rb"\x83\x3d(....)\x02(\x74.|\x90\x90)\xbe(....)\xbf\x00\x00\x00\x00\xb9\x01\x00\x00\x00\xe8", re.S)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--exe", default=EXE)
    a = ap.parse_args()
    d = bytearray(open(a.exe, "rb").read())
    pe = pefile.PE(data=bytes(d))
    hits = list(PAT.finditer(d))
    if len(hits) != 1:
        print("ABORT: expected 1 launch site, found %d" % len(hits)); return 1
    m = hits[0]
    off = m.start(2)
    va = pe.get_rva_from_offset(off) + pe.OPTIONAL_HEADER.ImageBase
    s_rva = int.from_bytes(m.group(3), "little") - pe.OPTIONAL_HEADER.ImageBase
    s = pe.get_data(s_rva, 13)
    if s != b"--game-start ":
        print("ABORT: esi string is %r, not '--game-start '" % s); return 1
    cur = bytes(d[off:off + 2])
    relocs = set()
    if hasattr(pe, "DIRECTORY_ENTRY_BASERELOC"):
        for blk in pe.DIRECTORY_ENTRY_BASERELOC:
            for e in blk.entries:
                if e.type: relocs.add(e.rva)
    rva = va - pe.OPTIONAL_HEADER.ImageBase
    if any(r in relocs for r in range(rva - 3, rva + 2)):
        print("ABORT: relocation under the je"); return 1
    state = "applied" if cur == b"\x90\x90" else "vanilla"
    print("launch gate je @%#x (file %#x): %s (%s)" % (va, off, cur.hex(), state))
    if a.revert:
        if state == "vanilla": print("already reverted"); return 0
        # the original displacement: je fr_1 skips the 20-byte launch block (mov esi / mov edi / mov ecx / call)
        new = b"\x74\x14"
    else:
        if state == "applied": print("already applied"); return 0
        if cur != b"\x74\x14": print("ABORT: unexpected je %s" % cur.hex()); return 1
        new = b"\x90\x90"
    if not (a.apply or a.revert):
        print("Dry run OK - rerun with --apply."); return 0
    bak = bak_path(a.exe, ".bak_preslaunch")
    if a.apply and not os.path.exists(bak):
        shutil.copy2(a.exe, bak); print("backup ->", bak)
    with open(a.exe, "r+b") as f:
        f.seek(off); f.write(new)
    print("reverted" if a.revert else "applied")
    return 0


if __name__ == "__main__":
    sys.exit(main())
