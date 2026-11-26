#!/usr/bin/env python3
r"""
aowInt.dpl: fine (+/-1) Power-Distribution slider steps with the mouse-wheel SIDE TILTS (2026-10-12).

The wheel already moves the mana/research slider in steps of 5 (build_wheel_power_slider.py: WheelPower @0x59823700,
driven through the VCL30 pump).  With a high mana income 5 % skips the exact value the user wants; clicking the
slider bar nudges it by 1.  The chord engine (build_mouse_chords.py) turns a plain tilt into VK_LEFT / VK_RIGHT
(keybd_event), so in the game a tilt arrives as an ARROW KEY at TAOWWinManager's key dispatch @0x598072FC
(eax = manager, edx = ptr to the VK word, cl = shift state).  ⚠ v1 clobbered ECX (the shift state) on the pass-through path - every
modifier-dependent key, cheat entry included, saw garbage flags; v2 (2026-10-12) compares the VK word in memory and only touches
ecx once a tilt key is being consumed.

Hook: the 7-byte prologue `53 56 57 55 83 C4 F8` -> jmp cave.  Cave (PIC - the DLL rebases): if g_pslider
@0x5983E10C (latched every mouse-move sweep by the power-slider patch while the Power Distribution window is open
and receiving sweeps) is set AND the key is VK_LEFT/VK_RIGHT: SetFPos(slider, FPos -/+ 1) @0x5980CA28 (clamps
0..100), fire the slider's OnChange (+0x6C code / +0x6E assigned / +0x70 Self -> TPowerDlg.PowerSliderChange,
which recalculates the labels exactly like a click on the bar), then RETURN from the dispatch (the key is consumed,
nothing else sees it).  Otherwise replay the prologue and resume @0x59807303.  Keyboard Left/Right do the same
while that window is open (indistinguishable from a tilt, and harmless).  Direction: tilt right = +1 (toward
research, like wheel up), tilt left = -1.

Cave @0x59823E00 (CODE tail zeros, next free per the aowInt cave map).  Backup <game>\backup\aowInt.dpl.bak_pwrtilt.
Dry run by default; --apply / --revert.  Requires build_wheel_power_slider.py (g_pslider) to be applied.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DEFAULT_DLL = game_file("aowInt.dpl")
BAK_SUFFIX = ".bak_pwrtilt"
BASE, CODE_V2F = 0x59800000, 0x59800C00
CAVE, CAVE_END = 0x59823E00, 0x59823E80
HOOK_VA = 0x598072FC
HOOK_ORIG = bytes.fromhex("5356575583c4f8")         # push ebx/esi/edi/ebp; add esp,-8
RESUME = 0x59807303
G_PSLIDER, G_HOVER = 0x5983E10C, 0x5983E100
SETFPOS = 0x5980CA28
SB_FPOS, SB_EVT_CODE, SB_EVT_HIWD, SB_EVT_DATA = 0x148, 0x6C, 0x6E, 0x70
VK_LEFT, VK_RIGHT, STEP = 0x25, 0x27, 1

ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm_delta(src, va):
    """`call $D / pop ebx / sub ebx, $D` PIC idiom resolved by a two-pass assembly (see the TCPCK scripts)."""
    s1 = src.replace("call $D", ".byte 0xe8, 0, 0, 0, 0").replace("sub ebx, $D", "sub ebx, 0x7fffffff")
    b = bytearray(ks.asm(s1, va)[0])
    anchor = b"\xe8\x00\x00\x00\x00\x5b\x81\xeb\xff\xff\xff\x7f"
    k = b.find(anchor); assert k >= 0
    struct.pack_into("<I", b, k + 8, va + k + 5)
    return bytes(b)


def build():
    src = """
        push ebx
        push esi
        push edi
        push ebp
        cmp word ptr [edx], %(left)d
        je tilt
        cmp word ptr [edx], %(right)d
        jne pass
    tilt:
        movzx ecx, word ptr [edx]
        call $D
        pop ebx
        sub ebx, $D
        mov edi, [ebx+%(pslider)#x]
        test edi, edi
        jz pass
        mov eax, [ebx+%(hover)#x]
        test eax, eax
        jnz pass
        mov edx, [edi+%(fpos)#x]
        cmp ecx, %(right)d
        je up
        sub edx, %(step)d
        jmp doit
    up:
        add edx, %(step)d
    doit:
        mov eax, edi
        call %(setfpos)#x
        cmp word ptr [edi+%(hiwd)#x], 0
        je done
        mov edx, edi
        mov eax, [edi+%(data)#x]
        call dword ptr [edi+%(code)#x]
    done:
        pop ebp
        pop edi
        pop esi
        pop ebx
        ret
    pass:
        add esp, -8
        jmp %(resume)#x
    """ % {"left": VK_LEFT, "right": VK_RIGHT, "pslider": G_PSLIDER, "hover": G_HOVER, "fpos": SB_FPOS, "step": STEP,
           "setfpos": SETFPOS, "hiwd": SB_EVT_HIWD, "data": SB_EVT_DATA, "code": SB_EVT_CODE, "resume": RESUME}
    code = asm_delta(src, CAVE)
    assert len(code) <= CAVE_END - CAVE, len(code)
    return code


def reloc_set(d):
    pe = struct.unpack_from("<I", d, 0x3C)[0]; opt = struct.unpack_from("<H", d, pe + 20)[0]; nsec = struct.unpack_from("<H", d, pe + 6)[0]
    secs = [struct.unpack_from("<IIII", d, pe + 24 + opt + 40 * k + 8) for k in range(nsec)]
    rrva, rsz = struct.unpack_from("<II", d, pe + 24 + 0x88)
    def r2f(rva):
        for vs, va, rs, ro in secs:
            if va <= rva < va + max(vs, rs): return ro + rva - va
    out = set()
    if not rsz: return out
    p, end = r2f(rrva), r2f(rrva) + rsz
    while p < end:
        page, size = struct.unpack_from("<II", d, p)
        if size < 8: break
        for q in range(p + 8, p + size, 2):
            e = struct.unpack_from("<H", d, q)[0]
            if e >> 12 == 3: out.add(BASE + page + (e & 0xFFF))
        p += size
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dll", default=DEFAULT_DLL)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read())
    code = build()
    hf = HOOK_VA - CODE_V2F; cf = CAVE - CODE_V2F
    hook = b"\xe9" + struct.pack("<i", CAVE - (HOOK_VA + 5)) + b"\x90" * (len(HOOK_ORIG) - 5)
    live = bytes(d[hf:hf + len(HOOK_ORIG)]); zone = bytes(d[cf:cf + (CAVE_END - CAVE)])
    bad = [hex(r) for r in reloc_set(d) if HOOK_VA - 3 <= r < HOOK_VA + len(HOOK_ORIG) or CAVE <= r < CAVE_END]
    pslider_patch = d[0x59823700 - CODE_V2F] == 0x55                      # WheelPower present (its signature byte)
    state = "vanilla" if live == HOOK_ORIG else "ours" if live == hook else "OTHER"
    zstate = "zero" if not any(zone) else "ours" if zone[:len(code)] == code and not any(zone[len(code):]) else "DIFFERS"
    print("hook %s | cave %s (%d B @%#x) | relocs %s | power-slider patch %s" % (state, zstate, len(code), CAVE, bad or "none", "present" if pslider_patch else "MISSING"))
    if a.dis:
        import capstone
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(code, CAVE): print("   %08X  %-16s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad or state == "OTHER" or not pslider_patch: print("ABORT"); return 1
    if a.revert:
        if state != "ours": print("not applied"); return 0
        d[hf:hf + len(HOOK_ORIG)] = HOOK_ORIG; d[cf:cf + (CAVE_END - CAVE)] = bytes(CAVE_END - CAVE)
        with open(a.dll, "r+b") as f: f.seek(0); f.write(d)
        print("reverted"); return 0
    if state == "ours" and zstate == "ours": print("already applied"); return 0
    if state == "vanilla" and zstate not in ("zero", "ours"): print("ABORT: cave not free"); return 1
    d[cf:cf + (CAVE_END - CAVE)] = bytes(CAVE_END - CAVE); d[cf:cf + len(code)] = code
    d[hf:hf + len(HOOK_ORIG)] = hook
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(a.dll, BAK_SUFFIX)
    if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    with open(a.dll, "r+b") as f: f.seek(0); f.write(d)
    assert open(a.dll, "rb").read() == bytes(d); print("Written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
