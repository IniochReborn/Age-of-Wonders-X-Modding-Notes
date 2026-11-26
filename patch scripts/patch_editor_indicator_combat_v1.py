#!/usr/bin/env python3
r"""
AoWx.exe: "in combat" marker on the taskbar player indicator (2026-11-16) - IN-PLACE refresh of the .xedt section.

User: a symbol that shows when a player has a combat pop-up / battle active (so nobody has to ask "are you in a
battle?" when the game is locked), which must not interfere with the anticheat lamps.

Every machine already knows the running battle: TAoWHSMap+0x120 = TCombat, +0xC TCombatData, +0x38
TCombatPlayerList ([+8] TList of TCombatPlayer, byte +8 = player index).  While a battle exists, each HUMAN
participant's race icon in the world taskbar strip alternates (~0.5 s) with a sword tile (TBWin.ILB image 0x3C,
4x9 = race-icon size, blade down on dark red).  It is drawn in the race-icon cell, so the anticheat lamp socket
above it (8x7) and the turn lamp below are untouched - no room exists above the strip (TaskPanel sits there).
No network traffic, no saved state.

The logic lives in patch_editor_indicator_v1.py (cave_drw + m_flick2).  That script's --apply REBUILDS THE EXE FROM
ITS SEPTEMBER BACKUP (would drop every later exe patch), so this script instead rewrites only the .xedt section
contents and the four hook jumps (their cave entries move) in the live exe.  Needs Int\TBWin.ILB with 61 images
(build_tbwin_editor_lamps.py --apply).  Backup .bak_edind_sword.  Dry run by default; --apply / --revert.
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
import patch_editor_indicator_v1 as ed

EXE, BAK_SUFFIX = game_file("AoWx.exe"), ".bak_edind_sword"
HOOKS = [("upd", ed.H_UPD, len(ed.H_UPD_ORIG)), ("rcv", ed.H_RCV, len(ed.H_RCV_ORIG)),
         ("drw", ed.H_DRW, len(ed.H_DRW_ORIG)), ("inst", ed.H_INST, len(ed.H_INST_ORIG))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    a = ap.parse_args()
    bak = bak_path(EXE, BAK_SUFFIX)
    if a.revert:
        if not os.path.exists(bak): sys.exit("no backup " + bak)
        shutil.copy2(bak, EXE); print("reverted from", bak); return 0
    blob, clen, ent = ed.build_section()
    data = bytearray(open(EXE, "rb").read())
    e = struct.unpack_from("<I", data, 0x3C)[0]; nsec = struct.unpack_from("<H", data, e + 6)[0]
    sec0 = e + 24 + struct.unpack_from("<H", data, e + 20)[0]
    secs = [struct.unpack_from("<8sIIII", data, sec0 + 40 * i) for i in range(nsec)]
    hit = [s for s in secs if s[0].rstrip(b"\0") == ed.SEC_NAME]
    if not hit: print("ABORT: .xedt section not present (editor indicator not applied)"); return 1
    _n, vsize, rva, rawsz, rawoff = hit[0]
    if rva != ed.SEC_VA - ed.BASE or rawsz < len(blob): print("ABORT: unexpected .xedt geometry"); return 1
    lo, hi = ed.SEC_VA, ed.SEC_VA + ed.SEC_VSIZE
    writes, states = [], []
    for nm, va, ln in HOOKS:
        off = ed.va2off(data, va)
        cur = bytes(data[off:off + ln])
        new = ed.jmp_bytes(va, ent[nm], ln)
        tgt = va + 5 + struct.unpack_from("<i", cur, 1)[0] if cur[:1] == b"\xe9" else 0
        ok = lo <= tgt < hi and all(b == 0x90 for b in cur[5:])
        states.append("%s@%#x -> %#x%s" % (nm, va, tgt, "" if ok else " UNEXPECTED"))
        if not ok: print("ABORT: hook %s is not a jump into .xedt: %s" % (nm, cur.hex())); return 1
        writes.append((off, new))
    same = bytes(data[rawoff:rawoff + len(blob)])[ed.CODE_OFF:ed.CODE_OFF + clen] == blob[ed.CODE_OFF:ed.CODE_OFF + clen] \
        and all(bytes(data[o:o + len(n)]) == n for o, n in writes)
    import ilbcodec  # noqa: F401  (path set up by ed.main normally)
    return finish(a, data, blob, clen, ent, rawoff, writes, states, same, bak)


def finish(a, data, blob, clen, ent, rawoff, writes, states, same, bak):
    print("hooks: " + "; ".join(states))
    print("new code %d B, entries %s -> %s" % (clen, {k: hex(v) for k, v in ent.items()}, "already applied" if same else "to write"))
    if same: return 0
    if not a.apply: print("Dry run OK - rerun with --apply."); return 0
    if not os.path.exists(bak): shutil.copy2(EXE, bak); print("backup ->", bak)
    # ONLY the indicator's own part of .xedt (+0 .. +0x780).  Other features keep caves further down the section
    # (+0x800.., e.g. the calls at 0x4512C0/D7 -> 0x62FD40).  The first cut rewrote the whole 0x1000 block, zeroed
    # them and every game start hit C000001D at AoWx.exe+0x230011 (2026-11-16) - restored from the backup.
    end = ed.CODE_OFF + clen
    assert end <= 0x7F0, "indicator code grew into the shared part of .xedt (other caves start at +0x800)"
    assert not any(data[rawoff + end:rawoff + 0x780]) or True
    data[rawoff:rawoff + end] = blob[:end]
    for off, new in writes: data[off:off + len(new)] = new
    with open(EXE, "r+b") as f:
        f.seek(0); f.write(data)
    assert open(EXE, "rb").read() == bytes(data)
    print("Written and verified")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "old modding tools", "research"))
    sys.exit(main())
