#!/usr/bin/env python3
# =============================================================================
# Road Build Cost by Decoration  --  AoWEPACK.dll binary patch
# =============================================================================
# Age of Wonders 1 (1999, Delphi).  Hand-assembled x86 patch to AoWEPACK.dll
#   ImageBase 0x55700000 ,  VA = file_offset + 0x55700C00
#
# EFFECT: Construct/Build-Road cost becomes PER-TILE by ground decoration
# instead of the vanilla flat 10 gold/tile:
#     open ground / light vegetation / bones = 2
#     rocks / toadstools                      = 3
#     Vegetation & Dense tree-forest          = 5
# The UI cost preview and the gold actually charged both route through the same
# classifier cave, so the preview always equals the charge.  CONFIRMED WORKING.
#
# BASELINE = pristine vanilla (AoWEPACK_original_backup.dpl).  This is the
# complete vanilla-flat-10 -> decoration-dependent patch.  New bytes are taken
# from the live shipped build, which carries the final tweak (toadstools 5->3,
# a 1-byte je-retarget at 0x5580F757) applied after the bak_roadveg_final
# backup.  Caves are PIC-safe (MapFieldMsgProc address computed via a
# call$+5/pop/sub/add delta-trick).  Scratch SC = 0x558FA800 (writable BSS).
#
# Usage:
#   py road_build_cost_by_decoration_patch.py <target AoWEPACK.dll>
#   py road_build_cost_by_decoration_patch.py --verify
# =============================================================================
import sys, shutil, os

VA_BASE = 0x55700C00

# (VA, length, ORIGINAL hex [vanilla], NEW hex [live]).
PATCHES = [
    # --- hooks / edits in the road-construct + UI-prediction functions ---
    # cave_capA hook @0x557710B6: vanilla `mov cl,[esi+10]; mov esi,[eax]` -> call cave_capA 0x5580F7B0
    (0x557710B6, 5, "8a4e108b30", "e8f5e60900"),
    # cave_capB hook @0x557710D8: vanilla `movsx esi,bl; mov edx,esi` -> call cave_capB 0x5580F7F0
    (0x557710D8, 5, "0fbef38bd6", "e813e70900"),
    # charge edit @0x557710F3: vanilla `sub eax,10` (flat cost) -> `sub eax,ebx; nop` (per-tile cost in ebx)
    (0x557710F3, 3, "83e80a", "2bc390"),
    # cave_pred hook @0x55771195 (UI path-walker adder): vanilla `add [esp+4],10` -> call cave_pred 0x5580F790
    (0x55771195, 5, "834424040a", "e8f6e50900"),
    # --- caves (zero free space -> code) ---
    # cave_roadcost @0x5580F700 (117B): field in eax -> cost 2/3/5 in eax.
    #   [field+0x15] overlay: 9(light)->2 , 1(veg/dense)->5 ; else find deco MO by
    #   MapFieldMsgProc==0x5579BE0C at vtable+0xCC -> [MO+8]=resource, [res+0x44]
    #   category: 1(rocks)->3 , 4(toadstools)->3 , else(bones/none)->2.
    (0x5580F700, 117, "0"*234,
        "5251535657558bf00fb646153c0974593c017447e8000000005f81ef19f7805581c70cbe79550fb64e0d8b560833db3bd97d368b2c9a8b45008b80cc0000003bc7740343ebe98b450885c0741c0fb640443c01740d3c047409eb0eb805000000eb0cb803000000eb05b8020000005d5f5e5b595ac3"),
    # cave_pred @0x5580F790 (14B): field=[esp+0xC] -> roadcost -> add [esp+8],cost ; ret
    (0x5580F790, 14, "0"*28, "8b44240ce867ffffff01442408c3"),
    # cave_capA @0x5580F7B0 (37B): field in esi -> roadcost -> store to SC 0x558FA800 ; replay mov cl,[esi+10]/mov esi,[eax]
    (0x5580F7B0, 37, "0"*74, "5052518bc6e846ffffffe8000000005981e9bff78055898100a88f55595a588a4e108b30c3"),
    # cave_capB @0x5580F7F0 (23B): replay movsx esi,bl/mov edx,esi ; ebx = [SC 0x558FA800] (per-tile cost) ; ret
    (0x5580F7F0, 23, "0"*46, "0fbef38bd6e800000000582dfaf780558b9800a88f55c3"),
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
            print(f"  0x{va:08X} already patched, skip"); continue
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
    base = os.path.join(root, "reference files", "BXL", "AoWEPACK_original_backup.dpl")
    live = os.path.join(root, "AoWEPACK.dll")
    tmp  = os.path.join(here, "_verify_road.tmp")
    shutil.copy(base, tmp); apply(tmp)
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
        print("usage: patch.py <target AoWEPACK.dll> | --verify"); sys.exit(1)
