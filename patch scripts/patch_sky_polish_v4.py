#!/usr/bin/env python3
r"""
Sky polish v4 (2026-10-31) - supersedes v3 (revert patch_sky_polish_v3 first; this one re-applies all of it).

User after v3: editor "Access violation at address 0000247C. Read of address 0000247C", tile palette gone.
Cause (static analysis): v2's TAbstractHexagon.ChangeTerrain bypass (0x5560A562) re-picked the tile of ANY Sky /
Clear Sky hexagon whose Clear-ness differed from the brush flag on EVERY same-terrain ChangeTerrain call - also the
engine's own calls outside painting (map set-up), where the re-pick path runs on a hexagon that is not ready ->
call through a garbage VMT slot.  (It also silently turned Clear Sky back into Sky.)
Fix:
  * paint gate byte (HSEPack DATA slack 0x5562E5F1): THSMPlaceControl.MsgProc's change-terrain call
    0x55612989 `call [ebx+0xD0]` -> cave sets gate 1, makes the call, clears it; the ChangeTerrain bypass only
    acts while the gate is set (= an editor brush stroke);
  * Clear Sky combat hexagon RID 0x5A1B0101 -> 0xAA0E02 (same scheme as the other combat hexagons); the 'clear'
    test accepts RID>>16 == 0x5A1B or RID == 0xAA0E02.
Everything else = patch_sky_polish_v3.  Backups .bak_skypolish4.  Dry-run default; --apply; --revert.
"""
import os, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sky_clouds_overlay_asm as OV  # noqa: E402
import patch_sky_polish_v1 as V1  # noqa: E402
import patch_sky_polish_v2 as V2  # noqa: E402
import patch_sky_polish_v3 as V3  # noqa: E402

GATE = V1.FLAG + 1
PC, PC_ORIG, PC_NEXT = 0x55612989, bytes.fromhex("ff93d0000000"), 0x5561298F
CLR_COMBAT_RID = 0xAA0E02

_v1_src = V1.hse_src


def v1_src():
    s = _v1_src()
    a = """        mov eax, dword ptr [esp]
        mov eax, dword ptr [eax + 0xc]
        shr eax, 16
        xor ecx, ecx
        cmp eax, {:#x}
        sete cl""".format(V1.CLEAR_HI)
    assert s.count(a) == 1
    return s.replace(a, """        mov eax, dword ptr [esp]
        mov eax, dword ptr [eax + 0xc]
        xor ecx, ecx
        cmp eax, {:#x}
        je sc_isclr
        shr eax, 16
        cmp eax, {:#x}
        jne sc_notclr
    sc_isclr:
        inc ecx
    sc_notclr:""".format(CLR_COMBAT_RID, V1.CLEAR_HI))


V1.hse_src = v1_src


def hse_src():
    s = V2.hse_src()
    a = """        cmp al, 0xe
        jne ct_skip
        mov ecx, dword ptr [ebx + 8]"""
    assert s.count(a) == 1
    s = s.replace(a, """        cmp al, 0xe
        jne ct_skip
        call ctg
    ctg:
        pop ecx
        sub ecx, ctg
        cmp byte ptr [ecx + {:#x}], 0
        je ct_skip
        mov ecx, dword ptr [ebx + 8]""".format(GATE))
    tail = s.index("    .long sct")
    return s[:tail] + """
    pc1:
        push eax
        call g1
    g1:
        pop eax
        sub eax, g1
        mov byte ptr [eax + {gate:#x}], 1
        pop eax
        call dword ptr [ebx + 0xd0]
        push eax
        call g2
    g2:
        pop eax
        sub eax, g2
        mov byte ptr [eax + {gate:#x}], 0
        pop eax
        jmp {nxt:#x}
""".format(gate=GATE, nxt=PC_NEXT) + s[tail:] + "    .long pc1\n"


def hse_patches():
    code = OV.asm(hse_src(), V1.HZONE + 0x10)
    ents = dict(zip(("sct", "scl", "grr", "pick", "ct", "pc1"), struct.unpack("<6I", code[-24:])))
    code = code[:-24]
    assert 0x10 + len(code) <= V1.HZONE_END - V1.HZONE
    z = V1.HMAGIC + bytes(12) + code
    jmp = lambda at, to, n: b"\xe9" + struct.pack("<i", to - (at + 5)) + b"\x90" * (n - 5)  # noqa: E731
    plf_new = (b"\x8b\xc6" + b"\x0f\xbe\x55\x08" + b"\xe8" + struct.pack("<i", ents["pick"] - (V1.PLF + 6 + 5)) +
               b"\x89\x45\xf0" + b"\x90" * 3)
    vanilla_plf = bytes.fromhex("8b4608e8") + struct.pack("<i", V1.RANDOM - (V1.PLF + 8)) + \
        bytes.fromhex("8b56048b04828945f0")
    return [(V1.SCT, V1.SC_ORIG, jmp(V1.SCT, ents["sct"], 6)), (V1.SCL, V1.SC_ORIG, jmp(V1.SCL, ents["scl"], 6)),
            (V1.GRR, V1.GRR_ORIG, jmp(V1.GRR, ents["grr"], 5)), (V1.PLF, vanilla_plf, plf_new),
            (V2.CT, V2.CT_ORIG, jmp(V2.CT, ents["ct"], 8)), (PC, PC_ORIG, jmp(PC, ents["pc1"], 6)),
            (V1.HZONE, bytes(len(z)), z)]


V2.hse_patches = hse_patches
V2.CLR_RID = CLR_COMBAT_RID
V2.TAG = ".bak_skypolish4"

if __name__ == "__main__":
    sys.exit(V2.main())
