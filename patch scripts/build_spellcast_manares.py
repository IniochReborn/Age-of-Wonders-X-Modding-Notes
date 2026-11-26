#!/usr/bin/env python3
r"""Hero mana income = (Spellcasting level) x 1.5 x Resistance.

2026-09-01: multiplier retuned x2 -> x1.5 per user. Computed as
(level * RES * 3) >> 1 -- one final round-down, never intermediate.

Idea adopted from BXL/Ziggurat's build_spellcast_manares.py (Ziggurat Scrolls
2026-08 drop); addresses re-verified against OUR AoWEPACK.dll, formula changed
per the user's spec (his was level x RES x1, ours is level x2 x RES).

THE CHAIN (his RE, byte-verified here). A hero's mana income is "power
generation": every hero registers a THeroPowerSource (THero.SetPlayer
@0x55787388 / Activate @0x55787512), TPlayerMagicControl.GetPower @0x5577CA00
sums Power() over the list, GetManaIncome @0x5577C95C takes off the research
share. Down the chain:

    THeroPowerSource.Power     @0x557867D0  -> hero.vtable[+0x134]
    THero.GetPowerGeneration   @0x557885E4  =  call TLeader's; ret
    TLeader.GetPowerGeneration @0x5578B43C:
        GetAbilityEnabled(0x34) via vtable[+0x148]   (item-aware)
        GetAbilityLevel(0x34)   via vtable[+0x144]   (item-aware)
        call 0x557885EC          <-- the level->power body, THE ONLY EDIT

SURPRISE FINDING (2026-08-30): our AoWEPACK is NOT vanilla here. Vanilla
computed level*5+5 (10/15/20/25/30) inline in TWO duplicate bodies; an
AoWx-era (pre-Claude) patch already collapsed THero's duplicate into a call
and carved the freed 40 bytes into a 5/10/20/40/80 lookup table -- the exact
structure BXL's script relies on (his tree has an analogous pre-convention
patch with a 10/20/40/60/90 table). So this script only rewrites the zone.

    before   5 / 10 / 20 / 40 / 80    for Spellcasting I..V (AoWx flat table)
    after    (level * 2) * Resistance

REGISTER CONTRACT at 0x557885EC (read out of the caller, verified before any
write): EAX = the Spellcasting level (from `call [ecx+0x144]`), EBX = the
THero/TLeader (set @0x5578B43D; callee-saved through both vtable calls).

RESISTANCE via vtable[+0xCC] = THero.GetResistance @0x5578850C for BOTH
THero and TLeader (asserted) -- the hero-card number (chassis + points +
items + morale), clamped [0,40] inside GetResistance, returned in AL.
GetPower accumulates 32-bit, no truncation. Worst case 2*5*40 = 400/turn.

UNITS UNAFFECTED: TUnit/TAdjustableUnit vtable[+0x134] = the zero stub
@0x5577FDB4 (`xor eax,eax; ret`), asserted. Nothing outside AoWEPACK carries
the formula; every display and the AI budget read through GetPower.

SAFETY (all proved on every run, not assumed):
  * the zone 0x557885EC..0x55788613 is bounded by THero.GetCastingPointsMax
    @0x55788614 (prologue byte-checked);
  * a full-CODE sweep finds exactly ONE reference into the zone: the rel32
    call @0x5578B461. (rel32 calls + absolute dwords both swept);
  * no .reloc entry covers the zone (the new body is register-relative only,
    PIC, needs none -- the DLL rebases at runtime);
  * MP-safe: deterministic, no RNG; both peers need the same DLL as usual.

Usage:
    py -3.10 build_spellcast_manares.py            # dry run / verify state
    py -3.10 build_spellcast_manares.py --apply    # back up + patch
    py -3.10 build_spellcast_manares.py --revert   # restore the AoWx table
"""
import os
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.environ.get("AOW_GAME_DIR") or os.path.dirname(HERE)
TARGET = os.path.join(GAME, "AoWEPACK.dll")
BAK = TARGET + ".bak_manares"

D = 0x55700C00                       # VA - D = file offset (CODE)
BASE = 0x55700000

ZONE_VA = 0x557885EC
ZONE_END = 0x55788614                # THero.GetCastingPointsMax starts here
ZONE_LEN = ZONE_END - ZONE_VA        # 40

CALLER_VA = 0x5578B43C               # TLeader.GetPowerGeneration
CALL_SITE = 0x5578B461               # its `call 0x557885EC`
UNIT_STUB = 0x5577FDB4

VMT134 = {"THero": (0x55711FEC, 0x557885E4),
          "TLeader": (0x55712238, CALLER_VA),
          "TUnit": (0x55710CAC, UNIT_STUB),
          "TAdjustableUnit": (0x55712A54, UNIT_STUB)}
VMT_RES_OFF = 0xCC

# the AoWx-era 5/10/20/40/80 table currently in the zone (--revert target)
OLD_BODY = bytes.fromhex(
    "85c07501c33c017503b005c33c027503b00ac33c037503b014c3"
    "3c047503b028c331c0b050c30000")
# TLeader.GetPowerGeneration body establishing the EAX/EBX contract
CALLER_ORIG = bytes.fromhex(
    "538bd8ba340000008bc38b08ff914801000084c07417"
    "ba340000008bc38b08ff9144010000e886d1ffff5bc3")
# THero.GetPowerGeneration = call TLeader's; ret
THERO_ORIG = bytes.fromhex("e8532e0000c30000")

# level*1.5*RES = (level*RES*3)>>1, register-relative only:
#   movzx eax,al / push eax / mov eax,ebx / mov edx,[eax]
#   call [edx+0xCC] (GetResistance -> al, clamped 0..40)
#   movzx eax,al / pop edx / imul eax,edx / imul eax,eax,3 / shr eax,1 / ret
NEW_BODY = bytes.fromhex(
    "0fb6c0508bc38b10ff92cc0000000fb6c05a0fafc26bc003d1e8c3")
assert len(NEW_BODY) <= ZONE_LEN
# the previous (level*2)*RES body (applied 2026-08-30) - upgradable in place
PREV_2X = bytes.fromhex(
    "0fb6c0508bc38b10ff92cc0000000fb6c05a0fafc201c0c3")


def reloc_vas(d):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    rva, size = struct.unpack_from("<II", d, e + 24 + 96 + 5 * 8)
    out = set()
    if not rva:
        return out
    # .reloc raw: find via section table
    n = struct.unpack_from("<H", d, e + 6)[0]
    p0 = e + 24 + struct.unpack_from("<H", d, e + 20)[0]
    for i in range(n):
        vsz, va, rsz, ro = struct.unpack_from("<IIII", d, p0 + i * 40 + 8)
        if va <= rva < va + max(vsz, rsz):
            p = ro + rva - va
            break
    end = p + size
    while p < end - 8:
        prva, blk = struct.unpack_from("<II", d, p)
        if not blk:
            break
        for k in range(p + 8, p + blk, 2):
            v = struct.unpack_from("<H", d, k)[0]
            if v >> 12:
                out.add(BASE + prva + (v & 0xFFF))
        p += blk
    return out


def refs_into_zone(d):
    """rel32 calls/jmps and absolute dwords targeting the zone, CODE-wide."""
    hits = []
    lo, hi = 0x400, 0x24C000            # generous CODE span
    sec = bytes(d[lo:hi])
    for i in range(len(sec) - 5):
        if sec[i] in (0xE8, 0xE9):
            src = lo + i + D
            tgt = (src + 5 + struct.unpack_from("<i", sec, i + 1)[0]) & 0xFFFFFFFF
            if ZONE_VA <= tgt < ZONE_END:
                hits.append(("rel32", src, tgt))
    for i in range(len(sec) - 3):
        v = struct.unpack_from("<I", sec, i)[0]
        if ZONE_VA <= v < ZONE_END:
            hits.append(("abs", lo + i + D, v))
    return hits


def rd32(d, va):
    return struct.unpack_from("<I", d, va - D)[0]


def main():
    apply = "--apply" in sys.argv
    revert = "--revert" in sys.argv
    d = bytearray(open(TARGET, "rb").read())
    zo = ZONE_VA - D

    cur = bytes(d[zo:zo + ZONE_LEN])
    padded_new = NEW_BODY + b"\x00" * (ZONE_LEN - len(NEW_BODY))
    padded_2x = PREV_2X + b"\x00" * (ZONE_LEN - len(PREV_2X))
    state = ("TABLE" if cur == OLD_BODY else
             "APPLIED" if cur == padded_new else
             "PREV_2X" if cur == padded_2x else "FOREIGN")
    print("hero mana income = (Spellcasting level) x 1.5 x Resistance")
    print("zone 0x%08X..0x%08X, state: %s" % (ZONE_VA, ZONE_END - 1, state))
    for r in (4, 6, 8, 12, 20, 40):
        print("  RES %-2d -> " % r +
              " / ".join("%3d" % (lv * r * 3 // 2) for lv in range(1, 6)) +
              "   (was 5/10/20/40/80 flat)")

    if revert:
        if state == "TABLE":
            print("already the 5/10/20/40/80 table - nothing to do")
            return 0
        if state == "FOREIGN":
            print("state FOREIGN - refusing to revert bytes we did not write")
            return 1
        d[zo:zo + ZONE_LEN] = OLD_BODY
        open(TARGET, "wb").write(bytes(d))
        print("reverted to the AoWx flat table (backup untouched)")
        return 0

    # environment checks (always, so dry runs report drift too)
    ok = True
    if bytes(d[CALLER_VA - D:CALLER_VA - D + len(CALLER_ORIG)]) != CALLER_ORIG:
        print("!! caller @0x%08X changed - EAX/EBX contract unproven" % CALLER_VA)
        ok = False
    if bytes(d[0x557885E4 - D:0x557885E4 - D + 8]) != THERO_ORIG:
        print("!! THero.GetPowerGeneration @0x557885E4 unexpected")
        ok = False
    for cls, (vmt, want) in VMT134.items():
        got = rd32(d, vmt + 0x134)
        if got != want:
            print("!! %s VMT+0x134 = %#x, want %#x" % (cls, got, want))
            ok = False
    if rd32(d, VMT134["THero"][0] + VMT_RES_OFF) != rd32(d, VMT134["TLeader"][0] + VMT_RES_OFF):
        print("!! THero/TLeader disagree on GetResistance")
        ok = False
    if bytes(d[UNIT_STUB - D:UNIT_STUB - D + 4]) != bytes.fromhex("33c0c390"):
        print("!! unit power stub is not xor eax,eax; ret")
        ok = False
    if bytes(d[ZONE_END - D:ZONE_END - D + 3]) != bytes.fromhex("538bd8"):
        print("!! GetCastingPointsMax prologue not at zone end - bound wrong")
        ok = False
    hits = refs_into_zone(d)
    foreign = [h for h in hits if not (h[0] == "rel32" and h[1] == CALL_SITE)]
    if foreign or not hits:
        print("!! zone refs wrong:", hits)
        ok = False
    bad = [v for v in reloc_vas(d) if ZONE_VA <= v < ZONE_END]
    if bad:
        print("!! relocs in zone:", [hex(v) for v in bad])
        ok = False
    print("environment checks:", "ALL PASS" if ok else "FAILED")
    if not ok:
        return 1

    if not apply:
        print("dry run - nothing written (--apply / --revert)")
        return 0
    if state == "APPLIED":
        print("already applied - nothing to do")
        return 0
    if state == "FOREIGN":
        print("state FOREIGN - refusing to overwrite unknown bytes")
        return 1
    if not os.path.isfile(BAK):
        shutil.copy2(TARGET, BAK)
        print("backed up to", os.path.basename(BAK))
    d[zo:zo + ZONE_LEN] = padded_new
    open(TARGET, "wb").write(bytes(d))
    print("APPLIED (%d-byte body, %d spare zeroed)%s"
          % (len(NEW_BODY), ZONE_LEN - len(NEW_BODY),
             " [upgraded in place from x2 body]" if state == "PREV_2X" else ""))
    print("NEEDS IN-GAME TEST: Spellcasting I hero with RES 6 should add 9 "
          "power (was 12 under x2); units with Spellcasting still add 0; "
          "leader scales the same; magic-window per-hero line matches.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
