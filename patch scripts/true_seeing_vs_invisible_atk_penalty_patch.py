#!/usr/bin/env python3
# =============================================================================
# True Seeing vs Invisible ATK Penalty  --  AoWEPACK.dll binary patch
# =============================================================================
# Age of Wonders 1 (1999, Delphi).  Hand-assembled x86 patch to AoWEPACK.dll
#   ImageBase 0x55700000 ,  VA = file_offset + 0x55700C00
#
# EFFECT: an attacker that LACKS True Seeing / True Vision (ability 0x29) and
# strikes a target that HAS Invisibility (ability 0x36) suffers an ATK penalty:
#     melee   -3   (applied at both melee strike-creation sites)
#     ranged   short/tier1 = 0 , medium/tier2 = -2 , long/tier3+ = -3
#             (penalty = min(tier,3) with tier2->-2 curve, tier read [ability+0x28])
# Strike-time injection (needs the TARGET), so it does NOT show on the general
# Attack stat.  Stacks additively with the Night-Vision underground penalty.
# All three caves are PIC-safe (no bare in-image absolute derefs -> rebase-proof).
#
# Byte values were produced by diffing the pre-feature backup
# (AoWEPACK.dll.bak_trueseeing) against the shipped build; the six ranges below
# are ONLY the True-Seeing feature.  (Path-of-Sand and hero-event caves that
# happen to sit nearby were deliberately excluded.)  CONFIRMED WORKING in-game.
#
# Usage:
#   py true_seeing_vs_invisible_atk_penalty_patch.py <target AoWEPACK.dll>
#   py true_seeing_vs_invisible_atk_penalty_patch.py --verify
# =============================================================================
import sys, shutil, os

VA_BASE = 0x55700C00

# (VA, length, ORIGINAL hex, NEW hex).  Combat-object HasAbility = vtable[0xA8].
PATCHES = [
    # --- hooks (steal -> jmp cave -> re-emit stolen -> jmp back) ---
    # melee1  global CreateStrikeCA @0x557666D8: steal `call 0x557298B4` (PIC rel32) -> jmp cave 0x5580F4C0
    (0x557666D8, 5, "e8d731fcff", "e9e38d0a00"),
    # melee2  TMeleeRound.CalculateStrikes @0x55767C89: steal 7B `mov eax,edi;mov edx,[eax];call[edx+70]` -> jmp cave 0x5580F520 (+2 nop)
    (0x55767C89, 7, "8bc78b10ff5270", "e992780a009090"),
    # ranged  CreateRangedAttackCA @0x5576EB1E: steal 10B `mov eax,esi;mov edx,[eax];call[edx+b8]` -> jmp cave 0x5580F580 (+5 nop)
    (0x5576EB1E, 10, "8bc68b10ff92b8000000", "e95d0a0a009090909090"),
    # --- caves (zero free space -> code) ---
    # cave_ts_melee @0x5580F4C0 (64B): attacker=ebp,target=esi; if !GAE(ebp,0x29)&&GAE(esi,0x36): bl-=3 (clamp>=1); re-emit call 0x557298B4; jmp 0x557666DD
    (0x5580F4C0, 64, "0"*128,
        "505152ba290000008bc58b08ff91a800000084c0751dba360000008bc68b08ff91a800000084c0740a80eb0380fb017d02b3015a5958e8b9a3f1ffe9dd71f5ff"),
    # cave_ts_melee3 @0x5580F520 (53B): attacker=esi,target=edi; if !GAE(esi,0x29)&&GAE(edi,0x36): dword[ebx]-=3; re-emit mov eax,edi;call[edx+70]; jmp 0x55767C90
    (0x5580F520, 53, "0"*106,
        "ba290000008bc68b08ff91a800000084c07516ba360000008bc78b08ff91a800000084c07403832b038bc78b10ff5270e93b87f5ff"),
    # cave_ts_rng @0x5580F580 (84B): attacker=esi,target=[ebp-4]; if !GAE(esi,0x29)&&GAE(tgt,0x36): tier[ebx+28] tier<=1->0,tier3+->cap3; byte[esp]-=penalty (clamp>=1); re-emit call[edx+b8]; jmp 0x5576EB28
    (0x5580F580, 84, "0"*168,
        "ba290000008bc68b08ff91a800000084c075328b45fcba360000008b08ff91a800000084c0741e0fb643283c0176163c037602b0038ad08a04242ac23c017d02b0018804248bc68b10ff92b8000000e954f5f5ff"),
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
    base = os.path.join(root, "AoWEPACK.dll.bak_trueseeing")
    live = os.path.join(root, "AoWEPACK.dll")
    tmp  = os.path.join(here, "_verify_ts.tmp")
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
