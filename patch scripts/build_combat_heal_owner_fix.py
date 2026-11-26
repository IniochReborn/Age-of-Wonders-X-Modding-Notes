#!/usr/bin/env python3
r"""FIX: combat heal executor passes unvalidated [obj+0x4C] as ability owner.

ROOT CAUSE (2026-08-13, found via guard v3 recorder + detail dialog):
The leveled-Healing patch repurposed HealUnit's Self: vanilla passed the
Healing ABILITY object (GetAbility(0x2F)); the mod passes the HEALER's TUnit
so the cave @0x5580E9B0 can look up the healer's Healing level via
GetAbilityData(Self, 0x2F). At the COMBAT executor site 0x5576BD24 that unit
comes from a raw `mov eax,[edi+0x4C]` on the healer combat object -- no nil
or class check -- and the target likewise (`mov edx,[ebx+0x4C]`). Vanilla
read those fields too but never walked them as an ability owner; the mod's
level lookup walks [owner+0x10] and crashes on junk (recorded: owner
0x0D98EE08 with +0x10 = 0x3C62 / 0xE0000 -- stale/freed-unit signature; the
'wild ability-chain' crash family in [[keeper2-armycombatmovete-crash]]).

THE FIX (in-place, 29 bytes at 0x5576BD24..0x5576BD40, was 3+18 NOP+3+5):
    mov eax,edi ; call 0x55810F00   ; healer  -> TUnit if IsClass TCombatUnit else nil
    push eax
    mov eax,ebx ; call 0x55810F00   ; target  -> TUnit or nil (sets ZF)
    pop ecx                          ; owner (POP does not touch flags)
    je  0x5576BD41                   ; target bogus -> skip the heal entirely
    mov edx,eax ; mov eax,ecx
    call 0x5576C374                  ; HealUnit(owner-or-nil, target)
    nop ; nop
Owner nil -> level-lookup helper 0x5580E6E0 nil-checks and returns the
default heal 5 = vanilla flat behaviour. Target bogus -> heal skipped
(vanilla would have virtual-called junk).
Helper 0x55810F00 (ranged Hero-Slaying fix helper, reused by fix #5 too)
preserves EDX, CLOBBERS ECX -- sequence accounts for both.

Verified pre-conditions (asserted on apply):
  - current live bytes are exactly the leveled-healing patch's
    8B474C + 90*18 + 8B534C + E8 33060000
  - no branch targets into 0x5576BD25..0x5576BD40 (scanned 2026-08-13: none)

*** THE RELOC AT 0x5576BD25 WAS FOUND STILL ACTIVE (type 3) 2026-08-13 ***
The July leveled-healing patch NOP'd over vanilla's `mov eax,[0x558fa044]`
without neutralizing its reloc. Since AoWEPACK always rebases, every load
added the delta to the NOP bytes, materializing a base-dependent JUNK
INSTRUCTION inside the executor (harmless AAA/cmp on this machine's usual
bases; on other bases it can decode to junk reads/rets/writes). This is a
prime suspect for machine-dependent crash/corruption differences in MP.
--apply neutralizes it (type 3 -> 0); --revert restores type 3 (matching the
pre-fix bytes it restores, junk and all).

Usage: --apply | --revert | --status    Backup: AoWEPACK.dll.bak_healowner
"""
import os, shutil, struct, sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DLL = os.path.join(GAME, "AoWEPACK.dll")
BAK = DLL + ".bak_healowner"

VA2FILE = 0x55700C00
SITE = 0x5576BD24
SITE_FILE = SITE - VA2FILE
HELPER = 0x55810F00
HEALUNIT = 0x5576C374
END = 0x5576BD41

OLD = bytes.fromhex("8b474c") + b"\x90" * 18 + bytes.fromhex("8b534c") + \
      b"\xe8" + struct.pack("<i", HEALUNIT - (0x5576BD3C + 5))
assert len(OLD) == 29


def build_new():
    b = bytearray()
    b += bytes.fromhex("8bc7")                                   # mov eax,edi
    b += b"\xe8" + struct.pack("<i", HELPER - (SITE + len(b) + 5))
    b += b"\x50"                                                 # push eax
    b += bytes.fromhex("8bc3")                                   # mov eax,ebx
    b += b"\xe8" + struct.pack("<i", HELPER - (SITE + len(b) + 5))
    b += b"\x59"                                                 # pop ecx
    b += bytes([0x74, END - (SITE + len(b) + 2)])                # je END
    b += bytes.fromhex("8bd0")                                   # mov edx,eax
    b += bytes.fromhex("8bc1")                                   # mov eax,ecx
    b += b"\xe8" + struct.pack("<i", HEALUNIT - (SITE + len(b) + 5))
    b += b"\x90\x90"
    assert len(b) == 29, len(b)
    return bytes(b)


RELOC_RVA = 0x6BD25              # the old absolute's reloc (VA 0x5576BD25)


def find_reloc_word(d):
    """Locate the .reloc WORD for RELOC_RVA. Returns (file_off, cur_word)."""
    import pefile
    pe = pefile.PE(data=bytes(d), fast_load=True)
    sec = next(s for s in pe.sections if s.Name.startswith(b".reloc"))
    raw, size = sec.PointerToRawData, sec.SizeOfRawData
    off = raw
    while off < raw + size:
        page, blksize = struct.unpack_from("<II", d, off)
        if blksize == 0:
            break
        if page == (RELOC_RVA & ~0xFFF):
            for eo in range(off + 8, off + blksize, 2):
                w = struct.unpack_from("<H", d, eo)[0]
                if (w & 0xFFF) == (RELOC_RVA & 0xFFF) and (w >> 12) in (0, 3):
                    return eo, w
        off += blksize
    raise AssertionError("reloc entry for 0x6BD25 not found")


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--status"
    d = bytearray(open(DLL, "rb").read())
    cur = bytes(d[SITE_FILE:SITE_FILE + 29])
    new = build_new()

    if mode == "--status":
        if cur == OLD:
            print("fix NOT applied (leveled-healing bytes present)")
        elif cur == new:
            print("fix APPLIED")
        else:
            print("UNEXPECTED bytes:", cur.hex())
        return 0

    if mode == "--apply":
        assert cur == OLD, "site bytes not as expected: " + cur.hex()
        eo, w = find_reloc_word(d)
        if not os.path.exists(BAK):
            shutil.copy2(DLL, BAK)
            print("backup ->", os.path.basename(BAK))
        if (w >> 12) == 3:
            struct.pack_into("<H", d, eo, w & 0xFFF)   # type 3 -> 0
            print(f"reloc @0x5576BD25 neutralized (was type 3, word @file "
                  f"{eo:#x})")
        d[SITE_FILE:SITE_FILE + 29] = new
        open(DLL, "wb").write(d)
        print(f"APPLIED: combat heal executor now class-checks healer+target "
              f"@{SITE:#x}")
        return 0

    if mode == "--revert":
        assert cur == new, "site does not carry this fix: " + cur.hex()
        eo, w = find_reloc_word(d)
        if (w >> 12) == 0:
            struct.pack_into("<H", d, eo, 0x3000 | (w & 0xFFF))  # restore type 3
            print("reloc @0x5576BD25 restored to type 3")
        d[SITE_FILE:SITE_FILE + 29] = OLD
        open(DLL, "wb").write(d)
        print("reverted to leveled-healing bytes")
        return 0

    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
