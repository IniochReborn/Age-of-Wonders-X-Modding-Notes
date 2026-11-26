#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# Mouse Wheel Scrolling  --  VCL30.dpl apply-script
# =============================================================================
# Adds mouse-wheel -> WM_VSCROLL/WM_HSCROLL translation to the shared Delphi-3
# runtime VCL30.dpl. Delphi 3 predates VCL wheel support, so scrollbars in the
# game (AoWx.exe) and editor (AoWDevX.exe) ignored the wheel; both processes
# import & call Forms.TApplication.Run, so one patch fixes both.
#
# Mechanism: at TApplication.Run a WH_MOUSE hook is installed whose callback
# finds the WS_VSCROLL/WS_HSCROLL window under the cursor and sends it 3x
# SB_LINEUP/DOWN + SB_ENDSCROLL, then swallows the message. Shift-aware:
# plain wheel = vertical (fallback horizontal), Shift+wheel = horizontal.
# NOTE: this is the "editor v2" state -- vertical+horizontal, NO in-game
# custom-UI (aowInt) path (that was shelved: the WH_MOUSE hook does not fire
# in the game process).
#
# File patched : VCL30.dpl   (ImageBase 0x41300000, CODE roff 0x400 rva 0x1000)
# Baseline     : VCL30.dpl.bak_wheel   (clean pre-wheel runtime)
#
# Three changes:
#   (1) HOOK  file 0x3B09C  VA 0x4133BC9C  TApplication.Run 7-byte prologue
#       55 8B EC 51 89 45 FC  ->  E9 5F CB 06 00 90 90   (jmp +0x6CB5F = cave_B)
#   (2) CAVE_A file 0xA7800  VA 0x413A8400  348-byte MouseProc callback
#   (3) CAVE_B file 0xA7C00  VA 0x413A8800   36-byte SetWindowsHookEx installer
#
# IAT slots used (all pre-imported by VCL30): GetCurrentThreadId 0x413E43E8,
# SetWindowsHookExA 0x413E463C, WindowFromPoint 0x413E45FC, GetWindowLongA
# 0x413E4758, GetParent 0x413E4784, SendMessageA 0x413E468C, CallNextHookEx
# 0x413E4894, GetKeyState 0x413E47B4.
#
# Usage:  py mouse_wheel_scrolling_patch.py [path-to-VCL30.dpl]
# Self-test: py mouse_wheel_scrolling_patch.py --selftest <clean.bak> <live.dpl>
#            (applies to a copy of clean.bak and asserts full-file == live)
# =============================================================================
import sys, os, shutil

HOOK_OFF = 0x3B09C
HOOK_OLD = bytes.fromhex("558bec518945fc")
HOOK_NEW = bytes.fromhex("e95fcb06009090")

CAVE_A_OFF = 0xA7800
CAVE_A = bytes.fromhex(
    "558bec83ec408b450885c00f8cb70000000f85b1000000817d0c0a0200000f85a4"
    "0000008b55100fbf42168945f8ff7204ff32ff15fc453e418945fc6a10ff15b447"
    "3e4166a900800f851e000000c745f400002000c745f015010000c745ec00001000"
    "c745e814010000eb1cc745f400001000c745f014010000c745ec00002000c745e8"
    "150100008b4df4e84f00000085c00f840d0000008b4df0e874000000e918000000"
    "8b4dece83200000085c00f84130000008b4de8e857000000b8010000008be55dc2"
    "0c00ff7510ff750cff75086a00ff1594483e418be55dc20c00894de08b45fc8945"
    "e48b45e485c074226af050ff1558473e418b55e085d0750eff75e4ff1584473e41"
    "8945e4ebdb8b45e4c333c0c38945dc894dd8ba000000008b45f885c07f05ba0100"
    "00008955d4c745d0030000006a00ff75d4ff75d8ff75dcff158c463e41ff4dd075"
    "ea6a006a08ff75d8ff75dcff158c463e41c3")

CAVE_B_OFF = 0xA7C00
CAVE_B = bytes.fromhex(
    "60ff15e8433e41506a006800843a416a07ff153c463e4161558bec518945fce97f34f9ff")

def apply(buf: bytearray):
    # (1) hook prologue
    cur = bytes(buf[HOOK_OFF:HOOK_OFF+7])
    if cur == HOOK_NEW:
        print(f"  [skip] hook @0x{HOOK_OFF:X} already installed")
    else:
        assert cur == HOOK_OLD, f"hook OLD mismatch @0x{HOOK_OFF:X}: got {cur.hex()}"
        buf[HOOK_OFF:HOOK_OFF+7] = HOOK_NEW
        print(f"  [ok]   hook @0x{HOOK_OFF:X} {HOOK_OLD.hex()} -> {HOOK_NEW.hex()}")
    # (2)(3) caves -- baseline must be zero-fill (tail cave) OR already our bytes
    for off, blob, name in ((CAVE_A_OFF, CAVE_A, "cave_A MouseProc"),
                            (CAVE_B_OFF, CAVE_B, "cave_B installer")):
        cur = bytes(buf[off:off+len(blob)])
        if cur == blob:
            print(f"  [skip] {name} @0x{off:X} already present ({len(blob)}B)")
            continue
        assert cur == b"\x00"*len(blob), (f"{name} @0x{off:X} baseline not zero-fill "
                                          f"(got {cur[:16].hex()}...) -- refusing to overwrite")
        buf[off:off+len(blob)] = blob
        print(f"  [ok]   {name} @0x{off:X} written ({len(blob)}B)")

def selftest(clean, live):
    buf = bytearray(open(clean, "rb").read())
    apply(buf)
    ref = open(live, "rb").read()
    assert len(buf) == len(ref), f"size mismatch {len(buf)} vs {len(ref)}"
    if bytes(buf) == ref:
        print("SELFTEST PASS: patched clean baseline == live file, byte-for-byte")
    else:
        diffs = [i for i in range(len(ref)) if buf[i] != ref[i]]
        print(f"SELFTEST FAIL: {len(diffs)} differing bytes, first @0x{diffs[0]:X}")
        sys.exit(1)

def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "--selftest":
        selftest(sys.argv[2], sys.argv[3]); return
    target = sys.argv[1] if len(sys.argv) > 1 else "vcl30.dpl"
    if not os.path.isfile(target):
        sys.exit(f"target not found: {target}")
    buf = bytearray(open(target, "rb").read())
    bak = target + ".bak_wheel_apply"
    if not os.path.exists(bak):
        shutil.copyfile(target, bak); print(f"backup -> {bak}")
    apply(buf)
    open(target, "wb").write(buf)
    print(f"written: {target}")

if __name__ == "__main__":
    main()
