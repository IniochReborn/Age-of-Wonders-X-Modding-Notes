#!/usr/bin/env python3
r"""TEMPORARY diagnostic for the item-ability-level fix (pairs with
itemablvl_probe.py). Wraps cave_lvl1 (build_item_ability_levels.py v2) so we
can see, from a RUNNING game, what owner object the tactical-combat paths pass
to TMultiLevelAbility.GetLevel for Marksmanship (id 0x20) and what level comes
back.

Requires v2 applied. Repoints the MLA site call 0x557651EC from cave_lvl1
(0x55812400) to a wrapper @0x55812560 that records into DATA slack
@0x558E9B00:
  +0  total GetLevel(no-inline) entries      +4  entries with id 0x20
  +8  last owner ptr (id 0x20)               +C  last owner VMT (id 0x20)
  +10 last own-record arg (id 0x20)          +14 last returned level (id 0x20)
then falls through to the real cave_lvl1.

--apply / --revert (restores the site call to cave_lvl1 and zeroes the
wrapper + counters). REMOVE BEFORE RELEASE.
"""
import os, shutil, struct, sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DLL = os.path.join(GAME, "AoWEPACK.dll")
VA2FILE = 0x55700C00
DATA2FILE = 0x55701200          # DATA: va 0x558E8000 raw 0x1E6E00

MLA_SITE  = 0x557651EC
CAVE_LVL1 = 0x55812400
CAVE_DIAG = 0x55812620
DIAG      = 0x558E9B00          # DATA slack counters

MARKS_ID = 0x20


def build_diag2():
    b = bytearray()
    def dd(v): b.extend(struct.pack('<I', v))
    b += b'\xFF\x05'; dd(DIAG + 0)          # inc [D+0]
    b += b'\x8B\x4B\x0C'                    # mov ecx,[ebx+0xC]
    b += bytes([0x83, 0xF9, MARKS_ID])      # cmp ecx,0x20
    jne_at = len(b)
    b += b'\x75\x00'                        # jne -> 'go' (patched below)
    b += b'\xFF\x05'; dd(DIAG + 4)          # inc [D+4]
    b += b'\x89\x35'; dd(DIAG + 8)          # mov [D+8],esi (owner)
    b += b'\x8B\x16'                        # mov edx,[esi]
    b += b'\x89\x15'; dd(DIAG + 0xC)        # mov [D+C],edx (owner VMT)
    b += b'\xA3'; dd(DIAG + 0x10)           # mov [D+0x10],eax (own rec arg)
    go_off = len(b)
    b[jne_at + 1] = go_off - (jne_at + 2)
    b += b'\xE8'; b += struct.pack('<i', CAVE_LVL1 - (CAVE_DIAG + len(b) + 4))
    b += b'\x8B\x4B\x0C'                    # mov ecx,[ebx+0xC]
    b += bytes([0x83, 0xF9, MARKS_ID])      # cmp ecx,0x20
    b += b'\x75\x05'                        # jne +5 -> ret
    b += b'\xA3'; dd(DIAG + 0x14)           # mov [D+0x14],eax (final level)
    b += b'\xC3'                            # ret
    return bytes(b), go_off


def main():
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    d = bytearray(open(DLL, 'rb').read())
    blob, go_off = build_diag2()
    site_off = MLA_SITE - VA2FILE
    cave_off = CAVE_DIAG - VA2FILE
    call_lvl1 = b'\xE8' + struct.pack('<i', CAVE_LVL1 - (MLA_SITE + 5))
    call_diag = b'\xE8' + struct.pack('<i', CAVE_DIAG - (MLA_SITE + 5))
    cur = bytes(d[site_off:site_off+5])
    if revert:
        assert cur in (call_diag, call_lvl1), cur.hex()
        d[site_off:site_off+5] = call_lvl1
        d[cave_off:cave_off+len(blob)] = bytes(len(blob))
        do = DIAG - DATA2FILE
        d[do:do+0x18] = bytes(0x18)
        open(DLL, 'wb').write(d); print("diag removed"); return 0
    assert cur in (call_lvl1, call_diag), "v2 not applied? " + cur.hex()
    seg = bytes(d[cave_off:cave_off+len(blob)])
    assert seg == bytes(len(blob)) or seg[:2] == b'\xFF\x05', seg[:4].hex()
    if not apply:
        print("diag wrapper %dB @0x%X; counters @0x%X; dry run OK (--apply / --revert)"
              % (len(blob), CAVE_DIAG, DIAG)); return 0
    d[cave_off:cave_off+len(blob)] = blob
    d[site_off:site_off+5] = call_diag
    open(DLL, 'wb').write(d)
    print("diag applied (REMOVE BEFORE RELEASE: --revert)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
