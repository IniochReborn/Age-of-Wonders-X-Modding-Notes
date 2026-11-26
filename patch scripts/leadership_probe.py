#!/usr/bin/env python3
r"""Dump the live Leadership (0x2E) state of every unit in the RUNNING game, grouped by party.

Use: start AoWx, make a stack with a Leadership unit + plain units (swordsmen), leave the
game on the map, then:  py "patch scripts\leadership_probe.py"

Per unit: class, player, own Leadership BIT, the Leadership record ([+0xC] own level,
[+0x10] borrowed level), and the cached attack/defence bonus bytes [+0x44]/[+0x45]
(TUnit reads its bonuses from that cache; heroes compute live).
"""
import struct, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from heal_probe import pids, modules, rd, u32, u8, scan_for, has_bit, load_names, k32, PREF

LEAD_ID = 0x2E
VMT_TUNIT, VMT_THERO, VMT_TLEADER = 0x55710CAC, 0x55711FEC, 0x55712238


def lstr(h, p):
    if not p:
        return ""
    n = u32(h, p - 4) or 0
    b = rd(h, p, min(n, 40)) if 0 < n < 200 else b""
    return b.decode("latin-1", "replace") if b else ""


def main():
    ps = pids()
    if not ps:
        print("AoWx.exe is not running."); return 1
    names = load_names()
    for pid in ps:
        h = k32.OpenProcess(0x410, False, pid)
        if not h:
            print(f"pid {pid}: cannot open"); continue
        base = modules(h).get("aowepack.dll")
        if not base:
            continue
        delta = base - PREF
        print(f"=== pid {pid}: AoWEPACK base {base:#x} (delta {delta:+#x})")
        targets = {VMT_TUNIT + delta: "TUnit", VMT_THERO + delta: "THero", VMT_TLEADER + delta: "TLeader"}
        parties = {}
        seen = set()
        for vmtval, va in scan_for(h, list(targets)):
            if va in seen:
                continue
            seen.add(va)
            party = u32(h, va + 4) or 0
            parties.setdefault(party, []).append((va, targets[vmtval]))
        for party, units in sorted(parties.items()):
            pvmt = (u32(h, party) or 0) - delta if party else 0
            pname = names.get(pvmt, "vmt=%08X" % pvmt) if party else "(no party)"
            interesting = False
            rows = []
            for va, kind in units:
                bit = has_bit(h, va, LEAD_ID)
                rec = None
                node = u32(h, va + 0x10); n = 0
                while node and n < 40:
                    if (u32(h, node + 0xC) or 0) >> 16 & 0xFFFF == LEAD_ID:
                        rec = node; break
                    node = u32(h, node + 8); n += 1
                own = u8(h, rec + 0xC) if rec else None
                bor = u8(h, rec + 0x10) if rec else None
                src = lstr(h, u32(h, rec + 0x14) or 0) if rec else ""
                atk, dfn = u8(h, va + 0x44), u8(h, va + 0x45)
                if bit or rec:
                    interesting = True
                rows.append(f"    {kind:8s} @{va:08X} player={u8(h, va + 0x24)} leadBIT={int(bit)} "
                            f"rec={'%08X' % rec if rec else '-':8s} own={own} borrowed={bor} src={src!r} "
                            f"cache atk/def=+{atk}/+{dfn}")
            if interesting and len(units) > 1:
                print(f"\n  party {party:08X} {pname} ({len(units)} units)")
                print("\n".join(rows))
        k32.CloseHandle(h)
    return 0


if __name__ == "__main__":
    sys.exit(main())
