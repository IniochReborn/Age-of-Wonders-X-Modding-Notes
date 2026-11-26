#!/usr/bin/env python3
r"""AI never-ending-turn fix: cap the AI group-control replan loop (AoWEPACK.dll).

Bug (reproduced live on "AoWx - Athendore", dwarves day 6; also reported online,
frostlings turn 8): TAIGroupControl.MoveExecuterDone treats move-executer result
5 (move plan invalidated - TAIMoveExecuter.InvalidateMove / Process exception)
as "world changed, re-plan": it resets the group state machine (agc+0x16C) to 0
UNCONDITIONALLY. If the target selector then deterministically re-picks a plan
the group can never execute (observed: single 0-MP Nymph army in the Depths;
pool-razeable targets from the AoWx reflecting-pool feature widen the target
surface), the pipeline restarts forever: ~1.7s of target-finding/pathfinding
per pass, group never marked processed, TEndTurnAIPA never runs, the AI player
never ends its turn while the CPU burns on "slow AI".

Fix: count restarts per group-control activation in agc+0x156 (padding byte
after the word at +0x154; verified untouched on TAIGroupControl - the only
+0x156 user in AoWEPACK is TAoWMapControl, a different class; object memory is
zero-initialized on creation so the counter resets per activation). After 20
restarts, call TAIGroupControl.Done (marks the group processed) instead of
restarting. Legit re-plans are rare (<5 per activation); a livelocked group now
costs at most ~35s once, then the turn proceeds. Verified END-TO-END by
injecting these exact bytes into the live stuck game: turn ended in 52s.

Site (RVA 0x38C66, in MoveExecuterDone's result==5 branch):
    33C0 89836C010000 5B C3   xor eax,eax; mov [ebx+16Ch],eax; pop ebx; ret
-> E9 <cave> + 5 NOPs. Cave in the code slack after the pool-raze caves
(file 0x10B7C0, RVA 0x10C3C0, 0x40 zero bytes). Cave uses only ebx-relative
addressing and rel32 calls inside the module - position-independent (AoWEPACK
is rebased at load; observed 0x02680000 and 0x0D70000). Reloc table is checked
to not intersect either range.

Known-remaining (unobserved, tracked in memory notes): the per-class
ProcessStates "state 6" raze-restart (AI levels 3/6/7) is a second, uncapped
restart edge; its failure paths funnel through MoveExecuterDone in practice.

Backup: AoWEPACK.dll.bak_airestartcap. Dry-run default; --apply / --revert.
"""
import os, shutil, struct, sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DLL = os.path.join(GAME, "AoWEPACK.dll")
BAK = DLL + ".bak_airestartcap"

RVA2FILE = 0xC00            # CODE: file = RVA - this
SITE_RVA = 0x38C66
SITE_OLD = bytes.fromhex("33c089836c0100005bc3")
CAVE_RVA = 0x10C3C0         # file 0x10B7C0, after pool-raze caves
CAVE_MAX = 0x40
DONE_RVA = 0x389B0          # AoWE.TAIGroupControl.Done (export)
CAP = 20


def build_cave():
    c = bytearray()
    c += bytes.fromhex("8A8356010000")          # mov al,[ebx+156h]  restart ctr
    c += bytes.fromhex("FEC0")                  # inc al
    c += bytes.fromhex("888356010000")          # mov [ebx+156h],al
    c += bytes([0x3C, CAP])                     # cmp al,CAP
    c += bytes.fromhex("7209")                  # jb allow
    c += bytes.fromhex("8BC3")                  # mov eax,ebx
    c += b"\xE8" + struct.pack("<i", DONE_RVA - (CAVE_RVA + len(c) + 5))
    c += bytes.fromhex("5BC3")                  # pop ebx; ret
    c += bytes.fromhex("33C089836C0100005BC3")  # allow: restart state=0; pop; ret
    assert len(c) == 37, len(c)
    return bytes(c)


def reloc_rvas(d):
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, pe + 6)[0]
    optsz = struct.unpack_from("<H", d, pe + 0x14)[0]
    rel_rva, rel_sz = struct.unpack_from("<II", d, pe + 0x18 + 0x88)  # dir 5 = basereloc
    # find .reloc raw offset
    off = None
    for i in range(nsec):
        o = pe + 0x18 + optsz + i * 40
        vsz, va, rsz, ro = struct.unpack_from("<IIII", d, o + 8)
        if va <= rel_rva < va + max(vsz, rsz):
            off = ro + (rel_rva - va); break
    assert off is not None
    end = off + rel_sz
    while off < end:
        page, bsz = struct.unpack_from("<II", d, off)
        if bsz < 8: break
        for j in range(8, bsz, 2):
            e = struct.unpack_from("<H", d, off + j)[0]
            if e >> 12: yield page + (e & 0xFFF)
        off += bsz


def main():
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if revert:
        if os.path.exists(BAK):
            shutil.copy2(BAK, DLL); print("restored AoWEPACK.dll"); return 0
        print("no backup"); return 1

    d = bytearray(open(DLL, "rb").read())
    cave = build_cave()
    site_off = SITE_RVA - RVA2FILE
    cave_off = CAVE_RVA - RVA2FILE

    patch = b"\xE9" + struct.pack("<i", CAVE_RVA - (SITE_RVA + 5)) + b"\x90" * 5
    assert len(patch) == len(SITE_OLD) == 10

    cur = bytes(d[site_off:site_off + 10])
    assert cur in (SITE_OLD, patch), cur.hex()
    seg = bytes(d[cave_off:cave_off + CAVE_MAX])
    assert seg == bytes(CAVE_MAX) or seg[:len(cave)] == cave, "cave in use"

    # sanity: Done really is at DONE_RVA (starts push ebx/push esi = 53 56)
    assert d[DONE_RVA - RVA2FILE:DONE_RVA - RVA2FILE + 2] == b"\x53\x56", \
        "TAIGroupControl.Done moved"

    # no relocs may point into the patched ranges
    for rva in reloc_rvas(d):
        assert not (SITE_RVA <= rva < SITE_RVA + 10), hex(rva)
        assert not (CAVE_RVA <= rva < CAVE_RVA + CAVE_MAX), hex(rva)

    d[cave_off:cave_off + len(cave)] = cave
    d[site_off:site_off + 10] = patch

    print("AoWEPACK: AI group replan-restart cap (%d) - MoveExecuterDone result-5" % CAP)
    print("  site RVA 0x%X -> cave RVA 0x%X (%dB); ctr byte agc+0x156; Done RVA 0x%X"
          % (SITE_RVA, CAVE_RVA, len(cave), DONE_RVA))
    if not apply:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if not os.path.exists(BAK):
        shutil.copy2(DLL, BAK); print("Backup ->", os.path.basename(BAK))
    open(DLL, "wb").write(d)
    print("Written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
