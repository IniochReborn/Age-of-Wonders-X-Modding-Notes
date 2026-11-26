#!/usr/bin/env python3
r"""
Open drop-down lists stay open across multiplayer-lobby updates (aowInt.dpl TAOWComboBox, 2026-10-22).

User (422 list): in the MP lobby an open drop-down (race owner / AI level, AI behaviour, preferred race, turns,
...) force-closes whenever another player joins/leaves or changes anything.

Cause (memory lobby-dropdown-stay-open): every lobby message runs TScenSetup's full refresh (AoWx.exe 0x411460 ->
per-race-row 0x410F2C x12), which Clear()s and refills each combo's Items.  Items.OnChange = TAoWComponent.
OnChangeText 0x59802464 (`[cb+0x2E] := 0`, size invalid) -> the next TAoWComponent.Setup 0x598033D0 calls VMT slot
0x30 = TAOWComboBox.SetSize 0x598125E0, whose first instruction clears the dropped-down flag [cb+0x118] -> collapse.
Every other size invalidation (SetWidth/SetHeight/ReAlign/Validate) also ends in that SetSize.

Fix: TAOWComboBox VMT slot 0x30 @0x59811FFC (has a reloc -> holds an absolute VA, adjusted by the loader on rebase)
-> cave SetSizeKeepOpen @0x59823E90:
    closed ([cb+0x118]==0) / hidden ([cb+0x75]==0) / empty list  -> jmp vanilla SetSize (collapse + recompute)
    otherwise re-fit the OPEN list to the refilled items, mirroring the drop-down code in CheckMouseDown
    (0x598134A4..0x598135CC):
      top [cb+0x12C] := min(top, max(0, n - vis[cb+0x124]))      (Draw reads Items[top+row] -> no OOB after a shrink)
      inset [cb+0x150] := frame width, [cb+0x154] := 0
      scrollbar [cb+0x120]: SetFMin 0, SetFMax n-1, SetFPos top, SetFNum vis, show; hide again when its style
      [sb+0x114]==1 and n-1 < vis, else inset := sb width [sb+0x7C]; [cb+0x154] := sb visible; sb size invalid
      call 0x598030B0 (the tail of vanilla SetSize: [cb+0x2E] := 1, repaint, children)
The items stay LIVE (the refresh rebuilt them), CheckMouseUp clamps the clicked index to Count, the handlers act on
the combo's fixed race row (Tag) and resolve players by NAME -> a pick can never land on the wrong player.
Visible-row count is not regrown while open (extra items scroll; a shrink leaves blank rows) - normal on next open.

Composes with build_wheel_combo.py (it SetFPos+Update's the same scrollbar; the range set here is the one it clamps
to) and patch_power_slider_tilt_v1.py (cave 0x59823E00..0x59823E80).  Only rel32 calls/jumps in the cave (PIC);
the only absolute value is the VMT slot, which keeps its reloc.

Zone 0x59823E80..0x59824000 ('CSO1' header + code).  Dry-run default; --apply / --revert / --dis.
Backup <game>\backup\aowInt.dpl.bak_combostay.
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DPL = game_file("aowInt.dpl")
BASE = 0x59800000
ZONE, ZONE_END = 0x59823E80, 0x59824000
CODE = ZONE + 0x10
MAGIC = b"CSO1"
VMT_COMBO = 0x59811FCC
SLOT = VMT_COMBO + 0x30                       # SetSize
SETSIZE = 0x598125E0
SIZEDONE = 0x598030B0                          # vanilla SetSize tail: +0x2E := 1, repaint, children
ILB_LOOKUP = 0x598018D4                        # frame-image lookup used for the inset in CheckMouseDown
SB_FMIN, SB_FMAX, SB_FPOS, SB_FNUM = 0x5980C9B8, 0x5980C9D8, 0x5980CA28, 0x5980C9F8


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
                    out.add(BASE + page + (v & 0xFFF))
            p += size
    return out


def build():
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    H = lambda v: "0x%X" % v  # noqa: E731
    src = "\n".join([
        "cmp  dword ptr [eax + 0x118], 0",       # closed -> vanilla
        "je   vanilla",
        "cmp  byte ptr [eax + 0x75], 0",         # hidden -> vanilla
        "je   vanilla",
        "push ebx",
        "push esi",
        "mov  ebx, eax",
        "mov  eax, [ebx + 0x11C]",
        "mov  edx, [eax]",
        "call dword ptr [edx + 0x14]",           # n = Items.Count
        "mov  esi, eax",
        "test esi, esi",
        "jle  collapse",
        "mov  eax, esi",                          # top := min(top, max(0, n - vis))
        "sub  eax, [ebx + 0x124]",
        "jge  t1",
        "xor  eax, eax",
        "t1:",
        "cmp  [ebx + 0x12C], eax",
        "jle  t2",
        "mov  [ebx + 0x12C], eax",
        "t2:",
        "mov  edx, [ebx + 0x180]",                # inset := frame width (no scrollbar)
        "add  edx, 4",
        "mov  eax, [ebx + 0x15C]",
        "call %s" % H(ILB_LOOKUP),
        "mov  eax, [eax + 0x20]",
        "mov  [ebx + 0x150], eax",
        "mov  byte ptr [ebx + 0x154], 0",
        "mov  eax, [ebx + 0x120]",
        "test eax, eax",
        "je   done",
        "xor  edx, edx",
        "call %s" % H(SB_FMIN),
        "mov  edx, esi",
        "dec  edx",
        "mov  eax, [ebx + 0x120]",
        "call %s" % H(SB_FMAX),
        "mov  edx, [ebx + 0x12C]",
        "mov  eax, [ebx + 0x120]",
        "call %s" % H(SB_FPOS),
        "mov  edx, [ebx + 0x124]",
        "mov  eax, [ebx + 0x120]",
        "call %s" % H(SB_FNUM),
        "mov  dl, 1",                             # show the scrollbar ...
        "mov  eax, [ebx + 0x120]",
        "mov  ecx, [eax]",
        "call dword ptr [ecx + 0x6C]",
        "mov  eax, [ebx + 0x120]",
        "cmp  byte ptr [eax + 0x114], 1",
        "jne  sbinset",
        "mov  eax, esi",
        "dec  eax",
        "cmp  eax, [ebx + 0x124]",
        "jge  sbinset",
        "xor  edx, edx",                          # ... and hide it again when everything fits
        "mov  eax, [ebx + 0x120]",
        "mov  ecx, [eax]",
        "call dword ptr [ecx + 0x6C]",
        "jmp  sbvis",
        "sbinset:",
        "mov  eax, [ebx + 0x120]",
        "mov  eax, [eax + 0x7C]",
        "mov  [ebx + 0x150], eax",
        "sbvis:",
        "mov  eax, [ebx + 0x120]",
        "mov  al, byte ptr [eax + 0x75]",
        "mov  byte ptr [ebx + 0x154], al",
        "mov  eax, [ebx + 0x120]",
        "mov  byte ptr [eax + 0x2E], 0",
        "done:",
        "mov  eax, ebx",
        "call %s" % H(SIZEDONE),
        "pop  esi",
        "pop  ebx",
        "ret",
        "collapse:",
        "mov  eax, ebx",
        "pop  esi",
        "pop  ebx",
        "vanilla:",
        "jmp  %s" % H(SETSIZE),
    ])
    code = bytes(Ks(KS_ARCH_X86, KS_MODE_32).asm(src, CODE)[0])
    zone = MAGIC + bytes(12) + code
    assert len(zone) <= ZONE_END - ZONE, hex(len(zone))
    return zone


def main():
    ap = argparse.ArgumentParser(description="combo drop-downs stay open across lobby updates")
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true"); ap.add_argument("--dpl", default=DPL)
    a = ap.parse_args()
    d = bytearray(open(a.dpl, "rb").read()); secs = pe(d)
    zone = build()
    so, zo = va2off(secs, SLOT), va2off(secs, ZONE)
    slot = struct.unpack_from("<I", d, so)[0]
    sst = "v1" if slot == CODE else "vanilla" if slot == SETSIZE else "OTHER %#x" % slot
    zl = bytes(d[zo:zo + (ZONE_END - ZONE)])
    zst = "v1" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else "zero" if not any(zl) else "OTHER"
    rl = reloc_targets(d, secs)
    slot_reloc = SLOT in rl
    zone_relocs = [hex(r) for r in rl if ZONE - 3 <= r < ZONE_END]
    print("VMT slot 0x30 @%#x = %s (reloc %s) | zone %#x %s (%d B) | relocs in zone %s"
          % (SLOT, sst, "yes" if slot_reloc else "NO", ZONE, zst, len(zone), zone_relocs or "none"))
    if a.dis:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
        for i in Cs(CS_ARCH_X86, CS_MODE_32).disasm(zone[0x10:], CODE):
            print("  %08X  %-22s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if not slot_reloc or zone_relocs:
        print("ABORT: relocation layout unexpected"); return 1
    if a.revert:
        if (sst, zst) == ("vanilla", "zero"):
            print("already reverted"); return 0
        if (sst, zst) != ("v1", "v1"):
            print("ABORT: not in the v1 state - refusing a partial revert"); return 1
        struct.pack_into("<I", d, so, SETSIZE)
        d[zo:zo + (ZONE_END - ZONE)] = bytes(ZONE_END - ZONE)
    else:
        if (sst, zst) == ("v1", "v1"):
            print("already applied"); return 0
        if (sst, zst) != ("vanilla", "zero"):
            print("ABORT: unexpected state (slot must be vanilla SetSize, zone zero)"); return 1
        d[zo:zo + len(zone)] = zone
        struct.pack_into("<I", d, so, CODE)
    if not (a.apply or a.revert):
        print("Dry run OK - rerun with --apply."); return 0
    bak = bak_path(a.dpl, ".bak_combostay")
    if a.apply and not os.path.exists(bak):
        shutil.copy2(a.dpl, bak); print("backup ->", bak)
    with open(a.dpl, "r+b") as f:
        f.seek(0); f.write(d)
    print("reverted" if a.revert else "applied")
    return 0


if __name__ == "__main__":
    sys.exit(main())
