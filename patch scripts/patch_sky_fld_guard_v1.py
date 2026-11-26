#!/usr/bin/env python3
r"""
Clear Sky battle-setup guard v1 (2026-11-01) - fixes "Access violation ... in module 'AoWTCPCK.dll'. Read of address
0000000D" when entering a city that holds armies (MP report 11/01; the city window runs the same battle setup).

patch_sky_polish_v2/v6 hook 0x424700 (cave 'fld' in zone 0x45B800) walks the centre map field's object list
([fld+8], count byte [fld+0xD]) and, for every object with bit 2 in [obj+0xC], reads [[obj+8]+0xC] as a hexagon
resource RID (Clear Sky = RID>>16 == 0x5A1B).  On a city hex an army/structure object passes the bit-2 test with
[obj+8] = 1 -> read of 0x0000000D.
v1: a new cave at 0x45B8A0 (same zone, after the v6 code which ends at 0x45B89C) re-points the 0x424700 jump:
  * scan only when the field terrain [fld+0x14] is Sky (0x0E) - the flag is still written (0) for every battle;
  * skip object / resource pointers below 0x10000.
The old 'fld' cave stays as dead code.  Re-running patch_sky_polish_v6 --revert first requires reverting this.
Dry-run default; --apply; --revert.  Backup .bak_skyfld1.
"""
import os, struct, sys, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bakpath import bak_path, game_file  # noqa: E402
import sky_clouds_overlay_asm as OV  # noqa: E402

DLL = game_file("AoWTCPCK.dll")
BAK = bak_path(DLL, ".bak_skyfld1")
VA2FILE = 0x400C00
FLD = 0x424700
CAVE, CAVE_END = 0x45B8A0, 0x45BA00
OLD_FLD = 0x45B83D
TC_IAT_AOWHSMAP = 0x46E8D4
SKY = 0x0E


def src():
    return f"""
        cmp dword ptr [ebp - 0x18], 0
        jne g_out
        pushal
        xor esi, esi
        cmp byte ptr [eax + 0x14], {SKY:#x}
        jne g_set
        movzx ecx, byte ptr [eax + 0xd]
        mov edx, dword ptr [eax + 8]
        cmp edx, 0x10000
        jb g_set
    g_loop:
        test ecx, ecx
        je g_set
        dec ecx
        mov ebx, dword ptr [edx + ecx*4]
        cmp ebx, 0x10000
        jb g_loop
        test byte ptr [ebx + 0xc], 2
        je g_loop
        mov ebx, dword ptr [ebx + 8]
        cmp ebx, 0x10000
        jb g_loop
        mov ebx, dword ptr [ebx + 0xc]
        shr ebx, 16
        cmp ebx, 0x5a1b
        jne g_loop
        mov esi, 1
    g_set:
        call g_t
    g_t:
        pop ebx
        sub ebx, g_t
        mov ecx, dword ptr [ebx + {TC_IAT_AOWHSMAP:#x}]
        sub ecx, {OV.GLOBAL_MAP:#x}
        mov eax, esi
        mov byte ptr [ecx + {OV.CCLEAR:#x}], al
        popal
    g_out:
        mov al, byte ptr [eax + 0x14]
        mov edx, dword ptr [ebp - 0x18]
        jmp {FLD + 6:#x}
"""


def jmp(at, to):
    return b"\xe9" + struct.pack("<i", to - (at + 5)) + b"\x90"


def reloc_hits(data, lo, hi):
    import pefile
    pe = pefile.PE(data=bytes(data))
    hits = []
    for blk in getattr(pe, "DIRECTORY_ENTRY_BASERELOC", []):
        for e in blk.entries:
            if e.type and lo <= pe.OPTIONAL_HEADER.ImageBase + e.rva < hi:
                hits.append(hex(pe.OPTIONAL_HEADER.ImageBase + e.rva))
    return hits


def main():
    mode = "--apply" if "--apply" in sys.argv else "--revert" if "--revert" in sys.argv else "dry"
    if mode == "--revert":
        assert os.path.exists(BAK), "no backup " + BAK
        shutil.copy2(BAK, DLL); print("reverted from", BAK); return 0
    d = bytearray(open(DLL, "rb").read())
    code = OV.asm(src(), CAVE)
    assert CAVE + len(code) <= CAVE_END, len(code)
    old_j, new_j = jmp(FLD, OLD_FLD), jmp(FLD, CAVE)
    cur = bytes(d[FLD - VA2FILE:FLD - VA2FILE + 6])
    zone = bytes(d[CAVE - VA2FILE:CAVE - VA2FILE + len(code)])
    if cur == new_j and zone == code:
        print("ALREADY PATCHED"); return 0
    assert cur == old_j, "0x424700 is not the sky_polish v6 jump: " + cur.hex()
    assert zone == bytes(len(code)), "cave 0x45B8A0 not empty"
    assert not reloc_hits(d, FLD, FLD + 6) and not reloc_hits(d, CAVE, CAVE + len(code)), "reloc overlap"
    print("cave %#x..%#x (%d bytes); jump %s -> %s" % (CAVE, CAVE + len(code), len(code), cur.hex(), new_j.hex()))
    if mode == "dry":
        print("dry run - pass --apply"); return 0
    if not os.path.exists(BAK):
        shutil.copy2(DLL, BAK)
    with open(DLL, "r+b") as f:
        f.seek(CAVE - VA2FILE); f.write(code)
        f.seek(FLD - VA2FILE); f.write(new_j)
    print("applied; backup", BAK)
    return 0


if __name__ == "__main__":
    sys.exit(main())
