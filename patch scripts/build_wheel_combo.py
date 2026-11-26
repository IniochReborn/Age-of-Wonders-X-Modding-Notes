#!/usr/bin/env python3
r"""
Mouse wheel scrolls dropped-down combo boxes (aowInt.dpl TAOWComboBox), e.g. the multiplayer
lobby's race-assignment (Free / Player / CPU ...) and preferred-race lists (2026-09-14).

Layers on build_wheel_aowint.py (which must already be applied): that patch tracks the control under
the cursor in g_hover @0x5983E100 and its WheelScroll helper @0x59822880 dispatches on the control's
class (listbox / memo / else sibling-scrollbar hunt).  Combos never latched g_hover, and the hunt
would have picked the wrong hidden sibling scrollbar anyway (a form keeps two per row, same left).

TAOWComboBox (VMT 0x59811FCC, instance 0x1A0): +0x118 dropped-down flag (-1 open / 0 closed; the
control's height +0x80 covers the open list), +0x11C items (VMT+0x14 = Count), +0x120 its own
TAOWVScrollBar (DFM `VScrollBar`, shown while open; FMin/FMax/FNum/FPos set at drop time),
+0x124 visible rows, +0x12C top item, +0x138 selected, +0x168 item height.  TAOWComboBox.Update
@0x598131CC copies the scrollbar's FPos (+0x148) into +0x12C (clamped) and repaints.

  1. SET4 hook @0x59813AC1 (TAOWComboBox.CheckMouseMove cursor-inside marker, 7 B
     `mov [ebx+0x78],-1`, ebx = combo) -> cave: g_hover = combo only while +0x118 != 0.
  2. CLS hook @0x59822915 inside WheelScroll (the `kind := 2; edi := 0` fallthrough for unknown
     classes, 9 B) -> cave: if g_hover's VMT is TAOWComboBox and it is open, SetFPos(its scrollbar,
     FPos -/+ 3) + TAOWComboBox.Update, then jump to the helper's success exit; otherwise replay the
     two instructions and resume.  The helper keeps working unchanged for every other control.
Caves @0x59823D40 / @0x59823D80 (CODE tail zeros; cave map in memory).  PIC: call/pop delta + rel32.
Backup aowInt.dpl.bak_wheelcombo.  Dry-run default; --apply; --revert.
"""
import os, shutil, struct, sys
from bakpath import game_dir, game_file   # game folder = AOW_GAME_DIR or parent of patch scripts (2026-09-20)

DEFAULT_GAME = game_dir()
BAK = ".bak_wheelcombo"
from bakpath import bak_path   # backups live in <game>\backup\ (2026-09-17)
BASE = 0x59800000
G_HOVER = 0x5983E100
VMT_COMBO = 0x59811FCC
CB_OPEN, CB_VSCROLL = 0x118, 0x120
SB_FPOS = 0x148
F_SETFPOS, F_COMBO_UPDATE = 0x5980CA28, 0x598131CC
LINES = 3
H_SET4, H_SET4_OLD = 0x59813AC1, bytes.fromhex("c74378ffffffff")
H_CLS, H_CLS_OLD = 0x59822915, bytes.fromhex("c745ec0200000033ff")
H_CLS_RESUME = 0x5982291E
HELPER, HELPER_LEN = 0x59822880, 0x200
OKEXIT_PAT = bytes.fromhex("b801000000eb")                 # mov eax,1 ; jmp exit  (WheelScroll success)
CAVE_SET4, CAVE_CLS, CAVE_END = 0x59823D40, 0x59823D80, 0x59823E00


def pe(d):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    n = struct.unpack_from("<H", d, e + 6)[0]
    optsz = struct.unpack_from("<H", d, e + 20)[0]
    secs = []
    for i in range(n):
        s = d[e + 24 + optsz + 40 * i:][:40]
        vs, va, rs, ra = struct.unpack_from("<IIII", s, 8)
        secs.append((s[:8].rstrip(b"\0"), va, vs, ra, rs))
    return secs


def va2off(secs, va):
    r = va - BASE
    for _n, va0, vs, ra, rs in secs:
        if va0 <= r < va0 + max(vs, rs):
            return ra + (r - va0)
    raise ValueError(hex(va))


def reloc_targets(d, secs):
    out = set()
    for nm, va, vs, ra, rs in secs:
        if nm != b".reloc":
            continue
        p, end = ra, ra + vs
        while p + 8 <= end:
            page, size = struct.unpack_from("<II", d, p)
            if size < 8:
                break
            for q in range(p + 8, p + size, 2):
                v = struct.unpack_from("<H", d, q)[0]
                if v >> 12 == 3:
                    out.add(page + (v & 0xFFF))
            p += size
    return out


def assemble(okexit):
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    H = lambda v: "0x%X" % v  # noqa: E731  (keystone reads bare decimals as hex)
    set4 = "\n".join([
        "push eax",
        "call next",                                     # PIC delta in eax
        "next:",
        "pop  eax",
        "sub  eax, next",
        "cmp  dword ptr [ebx + %s], 0" % H(CB_OPEN),     # latch only while dropped down
        "je   skip",
        "mov  [eax + %s], ebx" % H(G_HOVER),
        "skip:",
        "pop  eax",
        "mov  dword ptr [ebx + 0x78], 0xFFFFFFFF",       # displaced
        "jmp  %s" % H(H_SET4 + len(H_SET4_OLD)),
    ])
    cls = "\n".join([                                    # in WheelScroll: ebx = delta, esi = g_hover, [ebp+8] = wheel delta
        "mov  dword ptr [ebp - 0x14], 0x2",              # displaced pair
        "xor  edi, edi",
        "lea  ecx, [ebx + %s]" % H(VMT_COMBO),
        "cmp  [esi], ecx",
        "jne  back",
        "cmp  dword ptr [esi + %s], 0" % H(CB_OPEN),
        "je   back",
        "mov  edi, [esi + %s]" % H(CB_VSCROLL),
        "test edi, edi",
        "je   back",
        "mov  edx, [edi + %s]" % H(SB_FPOS),
        "mov  ecx, [ebp + 0x8]",
        "test ecx, ecx",
        "jle  down",
        "sub  edx, %s" % H(LINES),                       # wheel up
        "jmp  doit",
        "down:",
        "add  edx, %s" % H(LINES),
        "doit:",
        "mov  eax, edi",
        "call %s" % H(F_SETFPOS),                        # clamps to the range set at drop time
        "mov  eax, esi",
        "call %s" % H(F_COMBO_UPDATE),                   # top item := FPos, repaint
        "jmp  %s" % H(okexit),
        "back:",
        "jmp  %s" % H(H_CLS_RESUME),
    ])
    a = bytes(ks.asm(set4, CAVE_SET4)[0]); b = bytes(ks.asm(cls, CAVE_CLS)[0])
    assert CAVE_SET4 + len(a) <= CAVE_CLS and CAVE_CLS + len(b) <= CAVE_END
    return a, b


def main():
    import argparse
    ap = argparse.ArgumentParser(description="mouse wheel for dropped-down combo boxes")
    ap.add_argument("--game", default=DEFAULT_GAME)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    dpl = os.path.join(a.game, "aowInt.dpl")
    if a.revert:
        if not os.path.exists(bak_path(dpl, BAK)):
            print("no backup"); return 1
        shutil.copyfile(bak_path(dpl, BAK), dpl); print("restored aowInt.dpl"); return 0
    d = bytearray(open(dpl, "rb").read()); secs = pe(d)
    helper = bytes(d[va2off(secs, HELPER):va2off(secs, HELPER) + HELPER_LEN])
    assert helper[:6] == bytes.fromhex("558bec83ec18"), "WheelScroll helper (build_wheel_aowint.py) is not installed"
    assert helper.count(OKEXIT_PAT) == 1, "WheelScroll success exit not found once"
    okexit = HELPER + helper.index(OKEXIT_PAT)
    set4, cls = assemble(okexit)
    sites = [(H_SET4, H_SET4_OLD, b"\xE9" + struct.pack("<i", CAVE_SET4 - (H_SET4 + 5)) + b"\x90\x90", "TAOWComboBox.CheckMouseMove inside -> latch"),
             (H_CLS, H_CLS_OLD, b"\xE9" + struct.pack("<i", CAVE_CLS - (H_CLS + 5)) + b"\x90" * 4, "WheelScroll unknown-class fallthrough -> combo"),
             (CAVE_SET4, bytes(len(set4)), set4, "cave: latch"),
             (CAVE_CLS, bytes(len(cls)), cls, "cave: combo scroll")]
    relocs = reloc_targets(d, secs)
    for va, old, new, desc in sites:
        r = va - BASE
        assert not [x for x in relocs if r - 3 <= x < r + len(new)], "reloc inside %s" % desc
    cur = [bytes(d[va2off(secs, va):va2off(secs, va) + len(new)]) for va, _o, new, _d in sites]
    print("WheelScroll success exit @%#x; caves %d B @%#x, %d B @%#x" % (okexit, len(set4), CAVE_SET4, len(cls), CAVE_CLS))
    if a.dis:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
        for va, code in ((CAVE_SET4, set4), (CAVE_CLS, cls)):
            for i in Cs(CS_ARCH_X86, CS_MODE_32).disasm(code, va):
                print("  %08x  %-18s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if all(c == new for c, (_v, _o, new, _d) in zip(cur, sites)):
        print("ALL ALREADY PATCHED"); return 0
    for c, (va, old, _n, desc) in zip(cur, sites):
        assert c == old, "%s: unexpected bytes %s" % (desc, c.hex())
    if not a.apply:
        print("\nDry run OK. Re-run with --apply to write."); return 0
    if not os.path.exists(bak_path(dpl, BAK)):
        shutil.copyfile(dpl, bak_path(dpl, BAK)); print("backup: aowInt.dpl" + BAK)
    for va, _o, new, desc in sites:
        o = va2off(secs, va); d[o:o + len(new)] = new; print("patched:", desc)
    with open(dpl, "r+b") as f:
        f.seek(0); f.write(d)
    print("applied.  Test: open a lobby dropdown with a scrollbar and wheel over its list.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
