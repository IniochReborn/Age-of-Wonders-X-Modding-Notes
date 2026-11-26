#!/usr/bin/env python3
r"""
AoWTCPCK.dll DATA/BSS page-slack collision fixes (2026-10-18).

Audit of every TCPCK slack user (DATA page slack 0x46B7C8..0x46C000, BSS page slack 0x46C0A1..0x46D000, .idata page
slack 0x479EC8..0x47A000) found two LIVE overlaps:

  1. Miracle (patch_tc_miracle_v1.py) latch byte 0x46BFB0 sits inside Sandstorm's unit list G_LIST 0x46BF68..0x46BFE0
     (15 x 8 B, entry 9).  A Sandstorm hitting >= 10 units leaves a non-zero pointer byte there (Miracle then never
     raises again until T4 clears it), and a Miracle cast during the Sandstorm's life writes 1/0 into a listed unit HS
     pointer.  FIX: the three `[reg + 0x46BFB0]` displacements in Miracle's zone (0x440C4B / 0x440C70 / 0x440D1A)
     -> 0x46BFF0 (free: suffocate's wait dword 0x46BFE8 ends 0x46BFEC; nothing else references 0x46BFEC..0x46C000).

  2. Heal-AI evaluation log (patch_heal_ai_tcpck_v1.py, ring REC 0x46C800: +0x10.. 60 x 32 B = ..0x46CF90) overlaps
     Oil Spring's runtime TCOozeHS VMT clone 0x46CDC0..0x46CF10 (patch_oilspring_v1.py) - ring slots 45..55 overwrite
     clone slots once enough AI heal evaluations have been logged -> garbage vcalls on an oil decal.  FIX: the log
     sub's ring size `mov ecx, 60` @0x4394A2 -> 44 (ring ends 0x46CD90 < 0x46CDC0).  Read-back (--read) in the heal
     script uses REC_N, now 44 too.

Both are displacement/immediate swaps inside our own caves (same length, no relocs, PIC delta unchanged).
patch_tc_miracle_v1.py now builds with LATCH 0x46BFF0 and recognises the old-latch zone; patch_heal_ai_tcpck_v1.py
REC_N is now 44 (its state check does not look at the log sub).
Dry-run default; --apply / --revert (exact: restores 0x46BFB0 and 60); --dll <copy> for scratch runs.
"""
import argparse, struct, sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import game_file

DEFAULT_DLL = game_file("AoWTCPCK.dll")
V2F = 0x400C00
OLD_LATCH, NEW_LATCH = 0x46BFB0, 0x46BFF0
# (va of the disp32, the opcode/modrm bytes in front of it, the trailing imm8)
LATCH_SITES = [(0x440C4B, bytes.fromhex("80bb"), b"\x00"),     # cmp byte [ebx+L], 0
               (0x440C70, bytes.fromhex("c683"), b"\x01"),     # mov byte [ebx+L], 1
               (0x440D1A, bytes.fromhex("c680"), b"\x00")]     # mov byte [eax+L], 0
HEAL_SITE = 0x4394A2
HEAL_CTX = bytes.fromhex("8b8300c84600ff8300c8460031d2")        # mov eax,[ebx+REC] / inc [ebx+REC] / xor edx,edx
OLD_N, NEW_N = 60, 44


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dll", default=DEFAULT_DLL)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read())
    o = lambda va: va - V2F
    items = []
    for va, pre, post in LATCH_SITES:
        assert bytes(d[o(va) - 2:o(va)]) == pre and bytes(d[o(va) + 4:o(va) + 5]) == post, \
            "Miracle site %#x unexpected: %s" % (va, d[o(va) - 2:o(va) + 5].hex())
        items.append(("miracle latch @%#x" % va, o(va), struct.pack("<I", OLD_LATCH), struct.pack("<I", NEW_LATCH)))
    assert bytes(d[o(HEAL_SITE) - len(HEAL_CTX):o(HEAL_SITE)]) == HEAL_CTX and d[o(HEAL_SITE)] == 0xB9, \
        "heal log sub @%#x unexpected" % HEAL_SITE
    items.append(("heal log ring size @%#x" % (HEAL_SITE + 1), o(HEAL_SITE) + 1, struct.pack("<I", OLD_N), struct.pack("<I", NEW_N)))
    st = []
    for name, off, old, new in items:
        cur = bytes(d[off:off + 4])
        s = "old" if cur == old else "new" if cur == new else "OTHER(%s)" % cur.hex()
        st.append(s); print("  %-28s %s" % (name, s))
    if any(s.startswith("OTHER") for s in st): print("ABORT"); return 1
    want = "old" if a.revert else "new"
    if all(s == want for s in st): print("nothing to do (%s)" % ("reverted" if a.revert else "already applied")); return 0
    for name, off, old, new in items:
        d[off:off + 4] = old if a.revert else new
    if not (a.apply or a.revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    with open(a.dll, "r+b") as f:
        f.seek(0); f.write(d)
    assert open(a.dll, "rb").read() == bytes(d)
    print("%s and verified" % ("reverted" if a.revert else "applied")); return 0


if __name__ == "__main__":
    sys.exit(main())
