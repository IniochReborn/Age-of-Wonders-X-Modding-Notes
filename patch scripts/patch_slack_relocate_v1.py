#!/usr/bin/env python3
r"""
Move the weakness block and the Spring-of-Life diag bytes off the defender-retaliation table (2026-10-23).  AoWEPACK.

MP OOS audit 10/23 (user report: Azracs vs Highmen OOS on 1.37.422).  AoWEPACK BSS page slack had overlapping users:
  * defender retaliation (build_defender_retaliation.py, Aug) mark table 32 x 16 B = 0x558FA800..0x558FAA00, ZEROED at
    every TAoWHSMap.Create (cave 0x5581166E) and written by c1/c2/c3/c5 + give-up v3;
  * the weakness abilities (July, reference files\BXL weakness build): scratch dword 0x558FA800 (0x5580F7C6 store /
    0x5580F800 load) + WEAK_IDS[8] 0x558FA810..0x558FA82F (registration 0x5580F9B0; StrikeDmg x1.5 readers 0x5580FA00 /
    0x5580FC40, effect-roll -3 0x5580FC00, slot-0/2 readers 0x55854230/0x55854290, slot-1 reader 0x5585E037).  Live
    probe of a running 422 game: slots 0..3 = 0 (wiped by the retaliation Create) -> weaknesses were dead;
  * Spring of Life wasteland diag breadcrumbs (build_spring_wasteland.py, cave 0x55810000): 0x558FA8F0..0x558FA8F4 =
    retaliation entry 15;
  * (Harvest v8's crop buffers 0x558FA820.. = the actual OOS source - fixed in patch_harvest_v1.py, and give-up v3's
    counters vs Wall of Flames - fixed in patch_retaliation_giveup_v3.py.)
This script repoints every disp32 of the weakness block and the Spring diag into the Harvest-owned tail
0x558FA7C8..0x558FA800 (Harvest's buffers now end at 0x558FA7C8, cap 72):
  Spring diag 0x558FA8F0..8F4 -> 0x558FA7C8..7CC;  weakness scratch 0x558FA800 -> 0x558FA7D0;
  WEAK_IDS 0x558FA810..82F -> 0x558FA7E0..7FF.
The retaliation table keeps 0x558FA800..0x558FAA00 for itself.  Every site is checked with capstone (the instruction
covering it must carry exactly the old address); --revert writes the old addresses back.  The owners' build scripts
(BXL weakness / build_spring_wasteland) will no longer dry-run as "applied" - this script is the record.
Backup .bak_slackreloc.  Dry-run default; --apply / --revert.
"""
import argparse, os, shutil, struct, sys
import capstone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
try:
    from bakpath import bak_path, game_file
    DEFAULT = game_file("AoWEPACK.dll")
except Exception:
    bak_path = lambda p, s: p + s
    DEFAULT = r"C:\Users\<user>\Desktop\Age of Wonders X - Claude\AoWEPACK.dll"

DELTA = 0x55700C00
SUF = ".bak_slackreloc"
# disp32 location -> old target (new = old + shift of its block)
SPRING = {0x55810375: 0x558FA8F0, 0x55810033: 0x558FA8F2, 0x5581032E: 0x558FA8F3, 0x55810346: 0x558FA8F3,
          0x558100A3: 0x558FA8F4,
          **{va: 0x558FA8F1 for va in (0x5581002C, 0x55810051, 0x558100B7, 0x558100F2, 0x55810114, 0x5581017D,
                                       0x5581019C, 0x558101A9, 0x55810265, 0x55810284, 0x558102AB, 0x558102C8,
                                       0x55810361, 0x5581037B)}}
WEAK = {0x5580F7C8: 0x558FA800, 0x5580F802: 0x558FA800,
        0x5580F9B2: 0x558FA810, 0x5580FA1D: 0x558FA810, 0x5580FC13: 0x558FA810, 0x5580FC5D: 0x558FA810,
        0x55854232: 0x558FA810, 0x55854292: 0x558FA810, 0x5585E039: 0x558FA814,
        0x5585423A: 0x558FA818, 0x5585429A: 0x558FA818}
SHIFT_SPRING = 0x558FA7C8 - 0x558FA8F0
SHIFT_WEAK = 0x558FA7D0 - 0x558FA800
SITES = {**{va: (old, old + SHIFT_SPRING) for va, old in SPRING.items()},
         **{va: (old, old + SHIFT_WEAK) for va, old in WEAK.items()}}
MD = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)


def covering(d, va, want):
    """the instruction that contains the disp32 at va and mentions `want`"""
    for back in range(1, 8):
        st = va - back
        for i in MD.disasm(bytes(d[st - DELTA:st - DELTA + 16]), st):
            if i.address + i.size >= va + 4 and ("%#x" % want) in i.op_str:
                return i
            break
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dll", default=DEFAULT)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read())
    st = {}
    for va, (old, new) in SITES.items():
        cur = struct.unpack_from("<I", d, va - DELTA)[0]
        st[va] = "old" if cur == old and covering(d, va, old) else "new" if cur == new and covering(d, va, new) else "OTHER(%#x)" % cur
    vals = set(st.values())
    print("%s\n  %d sites: %s" % (a.dll, len(SITES), {k: list(st.values()).count(k) for k in vals}))
    bad = [hex(va) for va, s in st.items() if s.startswith("OTHER")]
    if bad:
        print("ABORT: unexpected bytes at", bad); return 1
    if a.revert:
        if vals == {"old"}: print("not applied - nothing to revert"); return 0
        for va, (old, new) in SITES.items(): struct.pack_into("<I", d, va - DELTA, old)
        msg = "reverted"
    else:
        if vals == {"new"}: print("already applied"); return 0
        if vals != {"old"}: print("ABORT: partially applied"); return 1
        if not a.apply: print("Dry run OK - rerun with --apply"); return 0
        bp = bak_path(a.dll, SUF)
        if not os.path.exists(bp): shutil.copy2(a.dll, bp); print("backup -> " + bp)
        for va, (old, new) in SITES.items(): struct.pack_into("<I", d, va - DELTA, new)
        msg = "applied: weakness block -> 0x558FA7D0, Spring diag -> 0x558FA7C8"
    with open(a.dll, "r+b") as f:
        f.write(d)
    chk = open(a.dll, "rb").read()
    want = (lambda o, n: o) if a.revert else (lambda o, n: n)
    assert all(struct.unpack_from("<I", chk, va - DELTA)[0] == want(o, n) for va, (o, n) in SITES.items())
    print("Written and verified - " + msg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
