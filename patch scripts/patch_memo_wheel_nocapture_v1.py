#!/usr/bin/env python3
r"""
Mouse wheel scrolls memos that do not capture input - map signs first of all (aowInt.dpl, 2026-10-30).

User: a long sign message gets a scroll bar in its window (TIWindow SignPnl over the event log, wooden GenericT
texture, "The sign reads:") but the mouse wheel does nothing there.

Cause: the wheel helper WheelScroll (0x59822880) scrolls the control latched in g_hover 0x5983E100, and memos latch
in TAOWMemo.CheckMouseMove (hook 0x5981A29A).  TIWindow.SignText (TAOWMemo, VScrollBar SignTextSB) has
CaptureInput = False ([comp+0xC0], DFM), so its parent never calls its CheckMouseMove:
  TAOWPanel.CheckMouseMove  child loop @0x5981E677  cmp byte [esi+0xC0],0 / je 0x5981E694   (SignPnl = TAOWPanel)
  TAOWWindow.CheckMouseMove child loop @0x5980A2A6  cmp byte [esi+0xC0],0 / je 0x5980A2C3
Same for HelpMemo, Message/MsgReceive/ItemsFound MessageMemo, Tutorial MessageMemo, WorldMap MemoL/R.

Fix: both 9-byte checks -> jmp cave.  CaptureInput set -> original path.  Not set -> hover-only latch, then the
original skip: if the child is exactly a TAOWMemo (VMT 0x5981848C) with a scrollbar [+0x120] and the cursor
(x = [ebp-8], y = [ebp+8] of the dispatcher) is inside the memo's text area - the same rect test TAOWMemo.
CheckMouseMove uses (window [+0x10C] +0x84/+0x88 + own +0x84/+0x88, width +0x7C - inset +0x138, height +0x80) -
g_hover := memo.  No input is delivered to the memo (it stays read-only, no I-beam); g_hover is cleared by the
sweep prologue 0x59822800 like every other latch.  PIC (delta via call/pop), rel32 jumps only.

Zone aowInt 0x59824600..0x59824700 ('MWN1' + original bytes).  Dry-run default; --apply / --revert.
Backup <game>\backup\aowInt.dpl.bak_memowheel.
"""
import os, shutil, struct, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DPL = game_file("aowInt.dpl")
BASE = 0x59800000
MAGIC = b"MWN1"
ZONE, ZONE_END = 0x59824600, 0x59824700
CODE = ZONE + 0x20
G_HOVER = 0x5983E100
VMT_MEMO = 0x5981848C
# (site, continue-with-capture, skip)
SITES = [(0x5981E677, 0x5981E680, 0x5981E694),      # TAOWPanel.CheckMouseMove
         (0x5980A2A6, 0x5980A2AF, 0x5980A2C3)]      # TAOWWindow.CheckMouseMove
ORIG = [bytes.fromhex("80bec00000000074") + bytes([skip - (site + 9)]) for site, _, skip in SITES]


LATCH = CODE
ENTRIES = [CODE + 0x80, CODE + 0xA0]


def build():
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    H = lambda v: "0x%X" % v  # noqa: E731
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    latch = "\n".join([
        "    pushad",
        "    call %s" % H(LATCH + 6),
        "    pop  ebx",
        "    sub  ebx, %s" % H(LATCH + 6),
        f"    lea  eax, [ebx + {H(VMT_MEMO)}]",
        "    cmp  dword ptr [esi], eax",
        "    jne  l_out",
        "    cmp  dword ptr [esi + 0x120], 0",
        "    je   l_out",
        "    mov  eax, dword ptr [esi + 0x10C]",
        "    test eax, eax",
        "    je   l_out",
        "    mov  ecx, dword ptr [ebp - 8]",
        "    mov  edx, dword ptr [ebp + 8]",
        "    mov  edi, dword ptr [eax + 0x84]",
        "    add  edi, dword ptr [esi + 0x84]",
        "    cmp  ecx, edi",
        "    jl   l_out",
        "    add  edi, dword ptr [esi + 0x7C]",
        "    sub  edi, dword ptr [esi + 0x138]",
        "    cmp  ecx, edi",
        "    jge  l_out",
        "    mov  edi, dword ptr [eax + 0x88]",
        "    add  edi, dword ptr [esi + 0x88]",
        "    cmp  edx, edi",
        "    jl   l_out",
        "    add  edi, dword ptr [esi + 0x80]",
        "    cmp  edx, edi",
        "    jge  l_out",
        f"    mov  dword ptr [ebx + {H(G_HOVER)}], esi",
        "l_out:",
        "    popad",
        "    ret"])
    z = bytearray(ZONE_END - ZONE)
    z[0:4] = MAGIC
    for i, o in enumerate(ORIG):
        z[4 + 9 * i:13 + 9 * i] = o
    lc = bytes(ks.asm(latch, LATCH)[0])
    assert LATCH + len(lc) <= ENTRIES[0], hex(len(lc))
    z[LATCH - ZONE:LATCH - ZONE + len(lc)] = lc
    hooks = []
    for e, (site, cont, skip) in zip(ENTRIES, SITES):
        stub = bytes(ks.asm("cmp byte ptr [esi + 0xC0], 0\njne %s\ncall %s\njmp %s" % (H(cont), H(LATCH), H(skip)), e)[0])
        assert len(stub) <= 0x20
        z[e - ZONE:e - ZONE + len(stub)] = stub
        hooks.append(bytes([0xE9]) + struct.pack("<i", e - (site + 5)) + bytes([0x90]) * 4)
    return bytes(z), hooks


def reloc_targets(pe):
    out = set()
    for blk in getattr(pe, "DIRECTORY_ENTRY_BASERELOC", []):
        for e in blk.entries:
            if e.type == 3:
                out.add(BASE + e.rva)
    return out


def game_running():
    try:
        r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq AoWx.exe"], capture_output=True, text=True)
        return "AoWx.exe" in r.stdout
    except Exception:
        return False


def main():
    import pefile
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    d = open(DPL, "rb").read()
    pe = pefile.PE(data=d)
    off = lambda va: pe.get_offset_from_rva(va - BASE)  # noqa: E731
    zone, hooks = build()
    zo = off(ZONE)
    cur_sites = [d[off(s):off(s) + 9] for s, _, _ in SITES]
    cur_zone = d[zo:zo + len(zone)]
    rl = reloc_targets(pe)
    bad = [hex(r) for r in rl if any(s - 3 <= r < s + 9 for s, _, _ in SITES) or ZONE - 3 <= r < ZONE_END]
    if cur_sites == ORIG and not any(cur_zone):
        st = "vanilla"
    elif cur_sites == hooks and cur_zone == zone:
        st = "ours"
    else:
        st = "OTHER"
    for (s, _, _), c in zip(SITES, cur_sites):
        print("site %#x %s" % (s, c.hex()))
    print("zone %#x %s (%d B) | relocs in range: %s -> %s"
          % (ZONE, "zero" if not any(cur_zone) else cur_zone[:4], len(zone.rstrip(b"\0")), bad or "none", st))
    if st == "OTHER" or bad:
        print("ABORT"); return 1
    want = "vanilla" if revert else "ours"
    if st == want:
        print("already %s" % ("reverted" if revert else "applied")); return 0
    if not apply and not revert:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if game_running():
        print("AoWx.exe is running - close the game first"); return 1
    bak = bak_path(DPL, ".bak_memowheel")
    if not revert and not os.path.exists(bak):
        shutil.copy2(DPL, bak); print("backup ->", bak)
    new_sites, new_zone = (ORIG, bytes(len(zone))) if revert else (hooks, zone)
    try:
        with open(DPL, "r+b") as f:                 # in-place (house rule)
            f.seek(zo); f.write(new_zone)
            for (s, _, _), b in zip(SITES, new_sites):
                f.seek(off(s)); f.write(b)
    except PermissionError:
        print("LOCKED - close the game and retry"); return 1
    d2 = open(DPL, "rb").read()
    assert [d2[off(s):off(s) + 9] for s, _, _ in SITES] == list(new_sites) and d2[zo:zo + len(new_zone)] == new_zone
    print("reverted" if revert else "written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
