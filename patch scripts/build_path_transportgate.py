#!/usr/bin/env python3
r"""AoWx -- Path abilities fire from the TRANSPORTER itself, not only when no
transporter is in the army.

ADOPTED 2026-08-30 from BXL/Ziggurat (his RE verbatim): TAbstractUnit.MovedTo
@0x55780328 gates ALL Path abilities (Life/Decay/Frost/our Sand) behind an
army-level check -- `TArmy.Transporter(army,0xFF) @0x5578E00C` nonzero blocks
EVERY unit in the army, including the transporter itself and escorts, not
just carried passengers. Fix: hook that call; if the returned transporter ==
EBX (the moving unit -- I AM the transporter) return 0, so only genuine
passengers stay blocked:
  no transporter in army   -> 0        -> not blocked (vanilla)
  the transporter itself   -> 0 (NEW)  -> leaves its Path trail
  a carried passenger      -> other!=0 -> blocked (correct, unchanged)
This same passenger-block is what keeps carried units from "touching" the
terrain (relevant to build_terrainfeed.py's walking heal, which replicates
the check for itself).

Cave re-homed (his 0x5580E060 is inside our old cave region). PIC: rel32 only.

Usage: dry run default; --apply; --revert (surgical).
"""
import os
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.environ.get("AOW_GAME_DIR") or os.path.dirname(HERE)
DLL = os.path.join(GAME, "AoWEPACK.dll")
BAK = DLL + ".bak_transportgate"

D = 0x55700C00
TRANSPORTER = 0x5578E00C
HOOK = 0x55780407
CAVE = 0x558140A0


def rel(src, dst):
    return struct.pack("<i", dst - (src + 5))


def make_cave():
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    src = f"""
        call 0x{TRANSPORTER:X}
        cmp  eax, ebx
        jne  _keep
        xor  eax, eax
    _keep:
        ret
    """
    src = "\n".join(ln.split(";")[0] for ln in src.splitlines())
    code, _ = Ks(KS_ARCH_X86, KS_MODE_32).asm(src, CAVE)
    return bytes(code)


def main():
    apply = "--apply" in sys.argv
    revert = "--revert" in sys.argv
    d = bytearray(open(DLL, "rb").read())
    cave = make_cave()
    orig = b"\xE8" + rel(HOOK, TRANSPORTER)
    new = b"\xE8" + rel(HOOK, CAVE)
    edits = [(CAVE, bytes(len(cave)), cave, "cave_transgate"),
             (HOOK, orig, new, "MovedTo Transporter call redirect")]
    states = []
    for va, ob, nb, nm in edits:
        c = bytes(d[va - D:va - D + len(nb)])
        st = "original" if c == ob else "applied" if c == nb else "FOREIGN"
        states.append(st)
        print("  %-34s @0x%08X  %s" % (nm, va, st))
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
    print("APPLIED - test: a land/air transporter with Path of Life/Sand etc. "
          "leaves its trail while moving; carried passengers still leave none")
    return 0


if __name__ == "__main__":
    sys.exit(main())
