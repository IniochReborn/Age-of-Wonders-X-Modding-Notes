#!/usr/bin/env python3
# =============================================================================
# Underground Night Vision ATK Penalty  --  AoWEPACK.dll binary patch
# =============================================================================
# Age of Wonders 1 (1999, Delphi).  Hand-assembled x86 patch to AoWEPACK.dll
#   ImageBase 0x55700000 ,  VA = file_offset + 0x55700C00
#
# EFFECT: units/heroes that LACK the Night Vision ability (id 0x27) suffer an
# ATK penalty on UNDERGROUND map levels:
#     melee  -1        (regular units via TUnit.GetAttack, heroes via THero.GetAttack)
#     ranged  short/tier1 = 0 , medium/tier2 = -1 , long/tier3+ = -2
#            (penalty = max(0, min(tier,3)-1) , tier read from [ability+0x28])
#
# The byte values below were produced by diffing the pre-feature backup
# (AoWEPACK.dll.bak_nightvision) against the shipped build
# (AoWEPACK.dll.bak_nightvision_fix2 == live at these offsets) and are the
# COMPLETE, in-game-confirmed feature (incl. the city-production crash fix:
# guards for unplaced/prototype units on every cave that runs during unit
# display / strength calc).
#
# DEPENDENCY: the two melee/hero pieces PIGGYBACK on a pre-existing "morale"
# cave pair (call 0x5580F0B0 @0x55782A00 ; hero-morale cave exiting at
# 0x5580F127).  This script assumes that cave already exists in the target
# (it does in bak_nightvision).  Applying to pristine vanilla would relink the
# morale call to a cave that vanilla lacks -- apply on a binary that already
# has the morale-ATK/RES feature, or port that first.
#
# Usage:
#   py underground_night_vision_atk_penalty_patch.py <target AoWEPACK.dll>
#   py underground_night_vision_atk_penalty_patch.py --verify   (self-test)
# =============================================================================
import sys, shutil, os

VA_BASE = 0x55700C00  # VA = file_off + this  ->  file_off = VA - 0x55700C00

# (VA, length, ORIGINAL hex [pre-feature], NEW hex [shipped]).  Caves originate
# in zero free space; the two 5-byte "repoint" entries edit existing call/jmp
# rel32 targets (full instruction shown).
PATCHES = [
    # --- hooks / repoints ---
    # GetAttackRA entry @0x5576E660: steal `mov bl,[eax+2a]; test esi,esi` -> jmp cave_ranged
    (0x5576E660, 5, "8a582a85f6", "e99b0b0a00"),
    # TUnit.GetAttack morale call @0x55782A00: call 0x5580F0B0 -> call cave_matk 0x5580F2C4
    (0x55782A00, 5, "e8abc60800", "e8bfc80800"),
    # hero-morale cave exit @0x5580F127: jmp 0x557883B6 -> jmp cave_hmatk 0x5580F340
    (0x5580F127, 5, "e98a92f7ff", "e914020000"),
    # --- caves (zero free space -> code) ---
    # cave_ranged @0x5580F200 (98B): stash tier[eax+28]/base[eax+2a]; guard esi&[esi+4];
    #   NV via [ecx+0x88] id 0x27; GetLocation 0x5577ED94 underground; sub bl by tier-1 (cap2); jmp 0x5576E665
    (0x5580F200, 98, "0"*196,
        "0fb650288a582a85f674508b460485c0744952ba270000008bc68b08ff91880000005a84c075345283ec038d442402508d4c24048d5424038bc6e855fbf6ff8a44240283c4035a3c0074108ac23c01760afec83c027602b0022ad885f6e903f4f5ff"),
    # cave_matk @0x5580F2C4 (76B): call morale 0x5580F0B0; guard ebx&[ebx+4];
    #   NV [ecx+0x88] 0x27; GetLocation(ebx) underground -> dec al (melee -1); ret
    (0x5580F2C4, 76, "0"*152,
        "e8e7fdffff5085db74408b430485c07439ba270000008bc38b08ff918800000084c0752683ec038d442402508d4c24048d5424038bc3e895faf6ff8a44240283c4033c00740458fec8c358c3"),
    # cave_hmatk @0x5580F340 (75B): guard [ebp+8]&[ebp+4]; NV [ecx+0x88] 0x27;
    #   GetLocation(ebp) underground -> dec byte[esp] (hero melee -1); jmp 0x557883B6
    (0x5580F340, 75, "0"*150,
        "8b450885c0743f8b450485c07438ba270000008bc58b08ff918800000084c0752583ec038d442402508d4c24048d5424038bc5e81cfaf6ff8a44240283c4033c007403fe0c24e92b90f7ff"),
]

def apply(path):
    with open(path, "rb") as f:
        data = bytearray(f.read())
    for va, ln, orig, new in PATCHES:
        o = va - VA_BASE
        ob = bytes.fromhex(orig); nb = bytes.fromhex(new)
        assert len(nb) == ln, f"len mismatch @0x{va:X}"
        cur = bytes(data[o:o+ln])
        if cur == nb:
            print(f"  0x{va:08X} already patched, skip")
            continue
        assert cur == ob, (f"UNEXPECTED bytes @0x{va:08X} (file 0x{o:X}):\n"
                           f"    have {cur.hex()}\n    want {ob.hex()}")
        data[o:o+ln] = nb
        print(f"  0x{va:08X}  {ob.hex()} -> {nb.hex()}")
    with open(path, "wb") as f:
        f.write(data)
    print(f"OK: wrote {len(PATCHES)} ranges to {path}")

def verify():
    here = os.path.dirname(os.path.abspath(__file__))
    root = r"C:\Users\<user>\Desktop\Age of Wonders X - Claude"
    base = os.path.join(root, "AoWEPACK.dll.bak_nightvision")
    live = os.path.join(root, "AoWEPACK.dll")
    tmp  = os.path.join(here, "_verify_nv.tmp")
    shutil.copy(base, tmp)
    apply(tmp)
    a = open(tmp, "rb").read(); b = open(live, "rb").read()
    ok = all(a[va-VA_BASE:va-VA_BASE+ln] == b[va-VA_BASE:va-VA_BASE+ln]
             for va, ln, _, _ in PATCHES)
    os.remove(tmp)
    print("VERIFY:", "PASS - all ranges match live AoWEPACK.dll" if ok else "FAIL")

if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--verify":
        verify()
    elif len(sys.argv) == 2:
        apply(sys.argv[1])
    else:
        print(__doc__ or "usage: patch.py <target> | --verify")
        sys.exit(1)
