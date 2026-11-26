#!/usr/bin/env python3
r"""
SUSPEND (214) - SMOOTH LIFT + SHAKE DURING THE TORNADO (2026-10-16).  AoWTCPCK.dll only.

User: "is it possible to have the unit smoothly/slowly rise to its 'flying height'? It's jarring how the unit skips
upwards at the end of the animation.  Also maybe the unit should shake (slightly, less than Gust) while the tornado is
active."

RE (TTacticalCombatUnitHS.Show 0x421EE0, ebp frame; [ebp-4] = the unit HS, [hs+0x1C] = its TCombatUnit):
  * 0x421FFB `call [ecx+0xA8]` = HasAbility(cu, 1 = Flying); 0x422001 `test al, al`; 0x422003 = the height pick, already
    a chain: `jmp 0x43EF90` (patch_gravitywell_field_v1: flying -> [ebp-0x38] = -8, Grounded 0xB8 -> +6, else 0, then
    `jmp 0x422013`; vanilla = flying -8 / else 0).  So the FLYING HEIGHT = 8 px (the whole 'skip' the user sees).
  * [ebp-0x38] is added to the draw y of the unit sprite AND every overlay drawn by the same Show (0x4224C9, 0x42258F,
    0x42269B, 0x422702 ...) - so the status overlays rise with it.  [ebp-8] = the draw x (0x421F82) used by them too.
  * Suspended (0xC3) is granted when the cast effect lands (end of the tornado) -> Flying (implied by 0xC3) flips on
    then -> -8 in one frame.  During the cast the spell's effect sits in the combat map's effect list
    ([[0x469420]]+0x11C TList, +4 items, +8 count) with [fx+0x14] = 0x34, [fx+0x18] = 214, [fx+0x2C] = the target cu,
    [fx+0x10] = its tick, [fx+0xC] = done flag.
Hook LFT (0x422003, the 5-B `jmp prev` chain head; prev decoded at apply time, kept in the zone header for --revert):
  entered with the flags of `test al, al` (al = HasAbility(1)).  Already flying (natural flyer / already Suspended)
  -> straight to prev (untouched).  Otherwise scan the effect list for a live 214 spell effect whose target is THIS
  unit: if found, t = clamp([fx+0x10], 0, DUR): [ebp-0x38] = LIFT[t] (eased 0 -> -FLY_H, smoothstep), and while
  t < DUR - SETTLE the draw x gets a small jitter SHK[(t >> 1) & 7] (+-1..2 px; Gust's shake is +-3), then
  `jmp 0x422013`.  Not found -> `test al, al` again (flags restored) and jmp prev.  At the landing the ability turns on
  and the normal flying draw (-8) takes over at exactly the height the lift reached -> no skip.
  Visual only (draw offsets of the HS, no game state; no RNG).
v2 (2026-10-16, user: 'still skips/jumps'): the scan no longer skips a DONE effect ([fx+0xC] = 1 from tick 95, the
  kind-7 NewFrame end at GetTotalSequenceFrames-1) - between 'done' and the TE executing the CA (the 0xC3 grant =
  Flying) a done-skip left the fly offset at 0 for a frame = a drop/jump.  t is clamped to DUR, so it holds -FLY_H
  until the grant.  (If an enemy RESISTS, no grant follows and the unit settles back to the ground when the done
  effect is freed.)  Companion: patch_tc_suspend_fadein_v1.py (the overlay fades in after the grant).
Zone AoWTCPCK 0x446800..0x446C00 (verified zero, reloc-free, unclaimed): +0 prev target, +4 tables (LIFT DUR+1 bytes,
SHK 8 bytes), code after.  Dry-run default; --apply / --revert / --dis / --dll <copy>.  Backup .bak_suspendlift.
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
from patch_airdeath_fix_v1 import asm_pic, relocs

DLL = game_file("AoWTCPCK.dll")
BASE, V2F = 0x400000, 0x400C00
ZONE, ZONE_END = 0x446800, 0x446C00
SITE = 0x422003                     # 5-B `jmp prev` (chain head) + 4 nops
RESUME = 0x422013                   # after the height pick
SPELL = 214
DUR = 96                            # cast animation length in ticks (slot 0 = 96 frames x 1 tick) - the lift spans it
FLY_H = 8                           # the engine's flying offset (gravitywell cave / vanilla: -8)
SETTLE = 10                         # stop shaking this many ticks before the end (the unit settles at height)
SHK = [1, -1, 2, -1, 0, 1, -2, 0]   # x jitter, +-1..2 px, changes every 2 ticks
MAP = 0x469420                      # [[MAP]] = the combat map; +0x11C = its effect TList


def lift_table():
    out = []
    for t in range(DUR + 1):
        u = t / float(DUR); s = u * u * (3 - 2 * u)
        out.append(-int(round(FLY_H * s)))
    return out


def build(prev):
    hdr = struct.pack("<I", prev)
    lt = lift_table(); tabs = bytes(b & 0xFF for b in lt) + bytes(b & 0xFF for b in SHK)
    tab_lift = ZONE + 4; tab_shk = tab_lift + DUR + 1
    code_va = (ZONE + 4 + len(tabs) + 15) & ~15
    src = """
        jne l_prev
        push eax
        push ecx
        push edx
        push esi
        push edi
        push ebx
        call $D
        pop ebx
        sub ebx, $D
        mov esi, [ebp-4]
        mov esi, [esi+0x1c]
        test esi, esi
        jz l_no
        mov edx, [ebx+%(map)#x]
        mov edx, [edx]
        test edx, edx
        jz l_no
        mov edx, [edx+0x11c]
        test edx, edx
        jz l_no
        mov ecx, [edx+8]
        mov edx, [edx+4]
    l_scan:
        dec ecx
        js l_no
        mov eax, [edx+ecx*4]
        test eax, eax
        jz l_scan
        cmp dword ptr [eax+0x18], %(spell)d
        jne l_scan
        cmp dword ptr [eax+0x14], 0x34
        jne l_scan
        cmp [eax+0x2c], esi
        jne l_scan
        mov eax, [eax+0x10]
        test eax, eax
        jge l_t0
        xor eax, eax
    l_t0:
        cmp eax, %(dur)d
        jle l_t1
        mov eax, %(dur)d
    l_t1:
        movsx edi, byte ptr [ebx+eax+%(tlift)#x]
        mov [ebp-0x38], edi
        cmp eax, %(shkend)d
        jge l_done
        shr eax, 1
        and eax, 7
        movsx edi, byte ptr [ebx+eax+%(tshk)#x]
        add [ebp-8], edi
    l_done:
        pop ebx
        pop edi
        pop esi
        pop edx
        pop ecx
        pop eax
        jmp %(resume)#x
    l_no:
        pop ebx
        pop edi
        pop esi
        pop edx
        pop ecx
        pop eax
        test al, al
    l_prev:
        jmp %(prev)#x
    """ % dict(map=MAP, spell=SPELL, dur=DUR, tlift=tab_lift, tshk=tab_shk, shkend=DUR - SETTLE, resume=RESUME, prev=prev)
    code = asm_pic(src, code_va)
    blob = bytearray(code_va - ZONE + len(code)); blob[0:4] = hdr; blob[4:4 + len(tabs)] = tabs
    blob[code_va - ZONE:] = code
    assert ZONE + len(blob) <= ZONE_END
    return bytes(blob), code_va


def site_state(d):
    b = bytes(d[SITE - V2F:SITE - V2F + 5])
    if b[0] != 0xE9: return "OTHER", None
    tgt = SITE + 5 + struct.unpack_from("<i", b, 1)[0]
    if ZONE <= tgt < ZONE_END: return "ours", tgt
    return "chain", tgt


def dis(d, lo, hi):
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    for i in md.disasm(bytes(d[lo - V2F:hi - V2F]), lo):
        print("%08X  %-7s %s" % (i.address, i.mnemonic, i.op_str))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true"); ap.add_argument("--dll", default=DLL)
    a = ap.parse_args(); path = a.dll; d = bytearray(open(path, "rb").read())
    R = relocs(d, BASE)
    zr = [hex(r) for r in R if ZONE <= r < ZONE_END]; sr = [hex(r) for r in R if SITE - 3 <= r < SITE + 5]
    zone = bytes(d[ZONE - V2F:ZONE_END - V2F]); st, tgt = site_state(d)
    hdr = struct.unpack_from("<I", zone, 0)[0]
    print("AoWTCPCK suspend lift: site %s -> %s | zone %s | relocs zone %s sites %s" % (
        st, hex(tgt) if tgt else None, "zero" if zone == bytes(len(zone)) else "used", zr or "none", sr or "none"))
    if zr or sr: print("ABORT: relocations in the zone / under the site"); return 1
    if st == "OTHER": print("ABORT: the site is not a jmp chain head"); return 1
    if a.revert:
        if st != "ours": print("already reverted"); return 0
        d[SITE - V2F:SITE - V2F + 5] = b"\xE9" + struct.pack("<i", hdr - (SITE + 5))
        d[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE)
        open(path, "r+b").write(d); print("reverted", path); return 0
    if st == "ours":
        prev = hdr
    else:
        if zone != bytes(len(zone)): print("ABORT: zone not free"); return 1
        prev = tgt
    blob, entry = build(prev)
    if st == "ours" and zone[:len(blob)] == blob and tgt == entry:
        if a.dis: dis(d, entry, ZONE + len(blob))
        print("already applied"); return 0
    if st == "ours": print("older build of this patch detected -> rewriting the zone in place")
    print("zone %d B, entry %#x, prev %#x, lift %s .. %s" % (len(blob), entry, prev, lift_table()[:3], lift_table()[-3:]))
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if os.path.abspath(path) == os.path.abspath(DLL):
        bak = bak_path(DLL, ".bak_suspendlift")
        if not os.path.exists(bak): shutil.copy2(DLL, bak); print("backup ->", bak)
    d[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE); d[ZONE - V2F:ZONE - V2F + len(blob)] = blob
    d[SITE - V2F:SITE - V2F + 5] = b"\xE9" + struct.pack("<i", entry - (SITE + 5))
    open(path, "r+b").write(d); print("written", path)
    if a.dis: dis(d, entry, ZONE + len(blob))
    return 0


if __name__ == "__main__":
    sys.exit(main())
