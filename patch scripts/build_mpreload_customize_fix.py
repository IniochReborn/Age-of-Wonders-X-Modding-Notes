#!/usr/bin/env python3
r"""AoWx -- fix the MP "Waiting for other players" hang when resuming /
reloading a saved game (autosave) in a network session.

ROOT CAUSE (RE'd 2026-09-03, VANILLA logic bug exposed by our
patch_mp_setup_defaults.py CustomizeLeaders default ON):

The network game-start handshake is AoWSetup.TSetupControl (AoWEPACK.dll).
Every machine loads the map, sends "map loaded" (setup msg 7) to the host;
the host sets bit 0x08 in TPlayerSetupSettings+0x19 per player and runs
hValidateSetupMap @0x557E1168.  That barrier requires, for every human
slot: bit 0x08 (map loaded) AND -- whenever TSetupSettings+0x2A
(CustomizeLeaders) is on -- bit 0x04 (leader customized).

But bit 0x04 is only ever set by the leader-customization flow
(hLeaderCustomized @0x557E06F0), and MapLoaded @0x557E060C SKIPS that
whole flow for games in progress: TSetupSettings+0x20 (written in hPickMap
@0x557E21A8 from the picked file's in-progress field, nonzero for
saves/autosaves) != 0 -> jump straight to phase 5 spSynchronize (the
"Waiting for other players" TSynchronizeDlg).  So on a resumed save with
CustomizeLeaders on, bit 0x04 can never be set for anyone,
hValidateSetupMap never passes, the host never broadcasts msg 6
(SetupMap), and every machine waits forever.  Vanilla never sees it only
because vanilla defaults CustomizeLeaders OFF.

FIX: make hValidateSetupMap's CustomizeLeaders gate loaded-game-aware,
mirroring MapLoaded's own skip: displace the 6-byte
`cmp byte [ebx+2Ah],0 / je satisfied` @0x557E11AA to a cave that first
checks `dword [ebx+20h]` (game in progress -> customization requirement
waived).  ebx = TSetupSettings (loaded @0x557E11A7, before the hook).
Cave uses only rel32 jmps + register-relative operands -> naturally PIC
(AoWEPACK rebases).  Hook range + cave reloc-scanned at run time.

Host-side logic, but ships in AoWEPACK.dll which must be identical on all
machines anyway.

Cave @0x55815500..0x55815530 (next free after this = 0x55815530).

Usage: dry run default; --apply; --revert (surgical).
"""
import os
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.environ.get("AOW_GAME_DIR") or os.path.dirname(HERE)
DLL = os.path.join(GAME, "AoWEPACK.dll")
BAK = DLL + ".bak_mpreload"

D = 0x55700C00
HOOK = 0x557E11AA
ORIG = bytes.fromhex("807b2a007413")   # cmp byte [ebx+2Ah],0 / je 0x557E11C3
RESUME_BIT4 = 0x557E11B0               # enforce bit-4 check (vanilla path)
SATISFIED = 0x557E11C3                 # requirement met (mov al,1)
CAVE = 0x55815500
CAVE_HI = 0x55815530


def make_cave():
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    # [ebx+0x20] nonzero = game in progress (loaded save) -> customization was
    # skipped by MapLoaded, so waive the bit-4 requirement.  [ebx+0x2a] zero =
    # CustomizeLeaders off -> nothing to require.  Else vanilla bit-4 check.
    src = """
        cmp  dword ptr [ebx+0x20], 0
        jne  _ok
        cmp  byte ptr [ebx+0x2a], 0
        je   _ok
        jmp  0x%X
    _ok:
        jmp  0x%X
    """ % (RESUME_BIT4, SATISFIED)
    code, _ = Ks(KS_ARCH_X86, KS_MODE_32).asm(src, CAVE)
    return bytes(code)


def reloc_rvas(d):
    pe_off = struct.unpack("<I", d[0x3C:0x40])[0]
    nsec = struct.unpack("<H", d[pe_off + 6:pe_off + 8])[0]
    opt = pe_off + 0x18
    rel_rva, rel_sz = struct.unpack("<II", d[opt + 0x88:opt + 0x90])  # dir 5 = basereloc
    secs = []
    p = opt + struct.unpack("<H", d[pe_off + 0x14:pe_off + 0x16])[0]
    for i in range(nsec):
        s = p + i * 0x28
        va, rawsz, raw = struct.unpack("<III", d[s + 0xC:s + 0x18])
        secs.append((va, rawsz, raw))
    def rva2off(rva):
        for va, rawsz, raw in secs:
            if va <= rva < va + rawsz:
                return raw + (rva - va)
        return None
    out = set()
    off = rva2off(rel_rva)
    end = off + rel_sz
    while off < end:
        page, bsz = struct.unpack("<II", d[off:off + 8])
        for i in range(8, bsz, 2):
            e = struct.unpack("<H", d[off + i:off + i + 2])[0]
            if e >> 12:
                out.add(page + (e & 0xFFF))
        off += bsz
    return out


def main():
    apply = "--apply" in sys.argv
    revert = "--revert" in sys.argv
    d = bytearray(open(DLL, "rb").read())
    cave = make_cave()
    assert CAVE + len(cave) <= CAVE_HI, len(cave)
    hook = b"\xE9" + struct.pack("<i", CAVE - (HOOK + 5)) + b"\x90"

    base_rva = 0x55700000 - 0x55700C00 + 0xC00  # image base 0x55700000; rva = va - base
    relocs = reloc_rvas(d)
    for va, ln, nm in ((HOOK, len(hook), "hook"), (CAVE, len(cave), "cave")):
        rva0 = va - 0x55700000
        bad = [hex(r) for r in relocs if rva0 <= r < rva0 + ln]
        assert not bad, "reloc under %s: %s" % (nm, bad)
    print("reloc scan clean (hook+cave)")

    edits = [(CAVE, bytes(len(cave)), cave, "cave_mpreload"),
             (HOOK, ORIG, hook, "hValidateSetupMap gate")]
    states = []
    for va, ob, nb, nm in edits:
        c = bytes(d[va - D:va - D + len(nb)])
        st = "original" if c == ob else "applied" if c == nb else "FOREIGN"
        states.append(st)
        print("  %-26s @0x%08X  %s (%d B)" % (nm, va, st, len(nb)))
    if "FOREIGN" in states:
        print("FOREIGN - refusing")
        return 1
    if revert:
        for va, ob, nb, _ in edits:
            d[va - D:va - D + len(nb)] = ob
        open(DLL, "wb").write(bytes(d))
        print("reverted")
        return 0
    if not apply:
        print("dry run (--apply / --revert)")
        return 0
    if all(s == "applied" for s in states):
        print("already applied")
        return 0
    if not os.path.isfile(BAK):
        shutil.copy2(DLL, BAK)
        print("backed up")
    for va, ob, nb, _ in edits:
        d[va - D:va - D + len(nb)] = nb
    open(DLL, "wb").write(bytes(d))
    print("APPLIED - test: host + join a LAN game, save/autosave, then resume "
          "the save (in-session reload AND lobby re-host): all machines must "
          "pass 'Waiting for other players' and continue the game")
    return 0


if __name__ == "__main__":
    sys.exit(main())
