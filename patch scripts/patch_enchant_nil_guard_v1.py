#!/usr/bin/env python3
r"""
AoWEPACK: nil guard in TAbstractUnit.Register/UnregisterEnchantments (2026-11-07).

User: Ziggurat map "Highpass (Rockfeller_Route).hsm" opens greyed out in the editor, then "exception occurred during
CloseHSM".  VEH log (diag_veh_logger.py --exe AoWDevX.exe --args <map>):
  AV read [0x10] @ AoWE.TAbstractUnit.RegisterEnchantments+0x56 (0x5577F2F2)   <- Activate <- THero/TLeader <- TArmy
     <- TArmyHS.Activate <- TAoWHSMap.MsgProc (map open)  => the open aborts -> grey view
  AV read [0x10] @ AoWE.TAbstractUnit.UnregisterEnchantments+0x56 (0x5577F37E) <- Deactivate <- Destroy (close)
Both loops walk the global enchantment definitions; for each id the unit HasAbility (VMT+0x4C) they call
GetAbility 0x5574F1C4 (guard cave 0x55811000 + the unit's own ability list [unit+0x10]) and dereference the result.
A hero whose ability comes from somewhere other than its own list (Highpass's heroes/leaders) gets nil -> AV.
Fix: `mov ebx,eax / mov eax,[ebx+0x10]` (5 B) at 0x5577F2F0 and 0x5577F37C -> cave: nil -> skip this definition
(the loops' own skip targets 0x5577F31D / 0x5577F3A9), else replay and continue.
Cave AoWEPACK 0x558E16C0..0x558E1700 (zero, unclaimed; next free after the water-shore wedge cave).
Dry-run default; --apply; --revert (surgical).
"""
import os, shutil, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bakpath import bak_path  # noqa: E402
import patch_sky_polish_v1 as SP  # noqa: E402
import sky_clouds_overlay_asm as OV  # noqa: E402

TAG = ".bak_enchnil"
CAVE, CAVE_END = 0x558E16C0, 0x558E1700
SITES = [  # (site, skip target, resume)
    (0x5577F2F0, 0x5577F31D, 0x5577F2F5),     # RegisterEnchantments
    (0x5577F37C, 0x5577F3A9, 0x5577F381),     # UnregisterEnchantments
]
ORIG = bytes([0x8B, 0xD8, 0x8B, 0x43, 0x10])


def rel(at, to):
    return (to - (at + 5)).to_bytes(4, "little", signed=True)


def build():
    src, labels = "", []
    for i, (_s, skip, res) in enumerate(SITES):
        src += f"""
    g{i}:
        mov ebx, eax
        test ebx, ebx
        jz {skip:#x}
        mov eax, dword ptr [ebx + 0x10]
        jmp {res:#x}
"""
        labels.append("g%d" % i)
    src += "    probe:\n" + "".join("        mov eax, %s\n" % l for l in labels)
    code = OV.asm(src, CAVE)
    tail = code[-5 * len(labels):]
    addr = [int.from_bytes(tail[5 * i + 1:5 * i + 5], "little") for i in range(len(labels))]
    code = code[:-5 * len(labels)]
    assert len(code) <= CAVE_END - CAVE
    P = [(CAVE, bytes(CAVE_END - CAVE), code + bytes(CAVE_END - CAVE - len(code)))]
    for (s, _k, _r), a in zip(SITES, addr):
        P.append((s, ORIG, b"\xe9" + rel(s, a)))
    return P


def main():
    import pefile
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if (apply or revert) and SP.busy():
        print("game/editor running - close it first"); return 1
    d = open(SP.EPK, "rb").read(); pe = pefile.PE(data=d)
    P = build()
    st, bad = SP.state(d, pe, SP.EBASE, P)
    print("AoWEPACK", st, "relocs", bad or "none")
    if "OTHER" in st or bad or len(set(st)) != 1:
        print("ABORT"); return 1
    want = "vanilla" if revert else "ours"
    if st[0] == want:
        print("already", "reverted" if revert else "applied"); return 0
    if not (apply or revert):
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bk = bak_path(SP.EPK, TAG)
    if apply and not os.path.exists(bk):
        shutil.copy2(SP.EPK, bk)
    SP.write_bytes(SP.EPK, SP.EBASE, P, revert)
    st2, _ = SP.state(open(SP.EPK, "rb").read(), pefile.PE(SP.EPK), SP.EBASE, P)
    assert set(st2) == {want}, st2
    print("written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
