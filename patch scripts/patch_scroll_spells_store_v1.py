#!/usr/bin/env python3
r"""
Scroll items carry up to 7 spells - storage (AoWEPACK.dll, 2026-10-30).

User: scroll-type items (TItemType itScroll = 5) can be set to one spell in the editor but do nothing; a scroll
should grant up to 7 spells to the hero/leader holding it (spell book), list them in its description, and the
editor needs 7 spell pickers (2..7 default "None").

Vanilla: spell 1 = dword [item+0x38] (TItem.ReadWrite tag 0x14).  This patch adds spells 2..7:
  * TItem instance size (VMT 0x5570FAFC - 0x1C = 0x5570FAE0) 0x4C -> 0x64; new dwords [item+0x4C..+0x60]
    (zeroed by NewInstance = "None").  TItem has no subclasses.
  * TItem.ReadWrite: the item-HP/MV cave (patch_item_hpmv_use_v1, 0x558138E0..0x55813909) ends with
    `jmp 0x55794718` @0x55813904 -> jmp our cave, which streams the six dwords as tags 0x19..0x1E with the same
    stream method as tag 0x14 (VMT+0x2C), keeps eax (the stream-flags result tested at 0x55794718) and jumps back.
    TItem.ReadWrite backs Assign/Copy (memstream), so maps, saves, item libraries and the editor's edit-copy all
    carry them.  Old data has no tags -> 0.  Tags < 0x31 (TAbilityOwner's 0x31 list + 0x32+id records untouched).
Zone AoWEPACK 0x55848000..0x55848100 ('SCS1'); rest of 0x55848000..0x5584A000 reserved for the scroll/item-ench
work.  PIC: rel32 jumps only.  Dry-run default; --apply / --revert.  Backup AoWEPACK.dll.bak_scrollstore.
"""
import os, shutil, struct, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DLL = game_file("AoWEPACK.dll")
BASE = 0x55700000
MAGIC = b"SCS1"
INST_VA, INST_OLD, INST_NEW = 0x5570FAE0, 0x4C, 0x64
SITE, SITE_ORIG_TGT = 0x55813904, 0x55794718
ZONE, ZONE_END = 0x55848000, 0x55848100
CODE = ZONE + 0x10
FIRST_OFF, FIRST_TAG, N = 0x4C, 0x19, 6


def build():
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    lines = ["push eax"]
    for i in range(N):
        lines += ["lea  edx, [ebx + 0x%X]" % (FIRST_OFF + 4 * i), "mov  ecx, 0x%X" % (FIRST_TAG + i),
                  "mov  eax, esi", "mov  edi, dword ptr [eax]", "call dword ptr [edi + 0x2C]"]
    lines += ["pop  eax", "jmp  0x%X" % SITE_ORIG_TGT]
    code = bytes(Ks(KS_ARCH_X86, KS_MODE_32).asm("\n".join(lines), CODE)[0])
    z = bytearray(ZONE_END - ZONE)
    z[0:4] = MAGIC
    assert 0x10 + len(code) <= len(z)
    z[0x10:0x10 + len(code)] = code
    return bytes(z)


def rel(at, tgt):
    return b"\xe9" + struct.pack("<i", tgt - (at + 5))


def game_running():
    try:
        r = subprocess.run(["tasklist"], capture_output=True, text=True)
        return any(n in r.stdout for n in ("AoWx.exe", "AoWDevX.exe"))
    except Exception:
        return False


def main():
    import pefile
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    d = open(DLL, "rb").read()
    pe = pefile.PE(data=d)
    off = lambda va: pe.get_offset_from_rva(va - BASE)  # noqa: E731
    zone = build()
    io, so, zo = off(INST_VA), off(SITE), off(ZONE)
    van = (struct.pack("<I", INST_OLD), rel(SITE, SITE_ORIG_TGT), bytes(len(zone)))
    ours = (struct.pack("<I", INST_NEW), rel(SITE, CODE), zone)
    cur = (d[io:io + 4], d[so:so + 5], d[zo:zo + len(zone)])
    rl = set()
    for blk in getattr(pe, "DIRECTORY_ENTRY_BASERELOC", []):
        for e in blk.entries:
            if e.type == 3:
                rl.add(BASE + e.rva)
    bad = [hex(r) for r in rl if ZONE - 3 <= r < ZONE_END or SITE - 3 <= r < SITE + 5]
    st = "vanilla" if cur == van else "ours" if cur == ours else "OTHER"
    print("TItem size %#x | hpmv tail %s | zone %#x %s | relocs %s -> %s"
          % (struct.unpack("<I", cur[0])[0], cur[1].hex(), ZONE, "zero" if not any(cur[2]) else cur[2][:4],
             bad or "none", st))
    if st == "OTHER" or bad:
        print("ABORT"); return 1
    want = "vanilla" if revert else "ours"
    if st == want:
        print("already %s" % ("reverted" if revert else "applied")); return 0
    if not apply and not revert:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if game_running():
        print("AoWx.exe / AoWDevX.exe is running - close it first"); return 1
    bak = bak_path(DLL, ".bak_scrollstore")
    if not revert and not os.path.exists(bak):
        shutil.copy2(DLL, bak); print("backup ->", bak)
    a, b_, c = van if revert else ours
    try:
        with open(DLL, "r+b") as f:                 # in-place (house rule)
            f.seek(zo); f.write(c)
            f.seek(so); f.write(b_)
            f.seek(io); f.write(a)
    except PermissionError:
        print("LOCKED"); return 1
    d2 = open(DLL, "rb").read()
    assert (d2[io:io + 4], d2[so:so + 5], d2[zo:zo + len(c)]) == (a, b_, c)
    print("reverted" if revert else "written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
