#!/usr/bin/env python3
r"""
SUSPEND (214) - the 'Suspended' (0xC3) STATUS OVERLAY FADES IN (2026-10-16).  AoWTCPCK.dll only.

User: "the transition is still not smooth. It skips/jumps."
RE (timeline of a Suspend cast, ticks of its kind-7 TfxHS):
  * NextStrike class-7 case (0x40D93C..0x40D9D5): one path point at HXtoHP(target)+16, [fx+0x2C] = the target cu.
  * TfxHS.NewFrame kind 4/7 (0x42D2EF): tick [fx+0x10] advances 1/tick; at tick == GetTotalSequenceFrames(slot 0) - 1
    (= 96 frames x (f18 0 + 1) - 1 = 95; mod cave 0x43B560 -> 0x43B653) it plays sound cue 1 and sets done [fx+0xC].
  * The TE then creates/executes the CA for the done effect ([fx+0x2C] set) -> 0xC3 granted at ~tick 96 = exactly when
    the cast animation ends.  Implied Flying flips on the same moment.
  * The overlay (TTacticalCombatUnitHS.Show loop 0x4227C0..0x42288B): frame = GetFrameIndex(seq, clock [[0x46E8D4]]+
    0x40, phase (hs >> 2) & 0xFFFF) -> its motes/ring phase is per-unit and clock-driven, so it can NEVER match the
    copy baked into the cast's last frames (frame i % 100) -> a visible phase jump; and it appears at FULL strength
    (image 770/60) the instant the cast ends (the copy is drawn at the cast's 770/90) -> a brightness jump.
Fix: hook FADE at 0x422880 (the overlay's `mov ebx,[eax] / call [ebx+0x84]`, 8 B -> call cave + 3 nop): for overlay
  ability 0xC3 only, a per-unit first-seen tick (BSS table 0x46CFA0: 6 x {cu, t0, last}; an entry not seen for GAP
  ticks restarts its fade = re-cast) gives age = clock - t0; while age < N the frame is drawn through GFXE's Intensity
  table at L = L0 + (L1 - L0) * age / N (image VMT+0x94 ShowBlended, the kind-0x1F particle recipe 0x42F801..0x42F8C1)
  instead of the image's own 770/L1 draw; from age N on the vanilla draw (identical at L1).  The cast art dips its copy
  out over its last frames (see _suspend7_integration.txt) and the overlay rises from that level -> no jump in phase
  (hidden at low level) or brightness.  Visual only.  Zone AoWTCPCK 0x446C00..0x447000 (verified zero, reloc-free).
Dry-run default; --apply / --revert / --dis / --dll <copy>.  Backup .bak_suspfadein.
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
from patch_airdeath_fix_v1 import asm_pic, relocs

DLL = game_file("AoWTCPCK.dll")
BASE, V2F = 0x400000, 0x400C00
ZONE, ZONE_END = 0x446C00, 0x447000
SITE, ORIG = 0x422880, bytes.fromhex("8b18ff9384000000")
ABIL = 0xC3
OVTAB = 0x444010                     # overlay ability-id table (patch_tc_suspend_overlay_v1 v3)
CLOCK = 0x46E8D4                     # [[CLOCK]]+0x40 = the battle clock (as 0x422815)
INTENS = 0x46DEC0                    # [[INTENS]] = GFXE.IntensityBlendTable (as 0x42F808)
GETLUT = 0x4018DC                    # GetLookupTables(eax = table, edx = L) -> eax
TAB, NENT = 0x46CFA0, 6              # BSS page slack 0x46CFA0..0x46CFE8 (heal ring ends 0x46CF90)
N, L0, L1, GAP = 24, 12, 60, 30      # fade ticks, start / full Intensity level (= the overlay row's 770/60), re-cast gap


def build():
    src = """
        push eax
        push ecx
        push edx
        push esi
        push edi
        call $D
        pop ebx
        sub ebx, $D
        mov esi, [ebp-0x30]
        cmp dword ptr [ebx+esi*4+%(ovtab)#x], %(abil)d
        jne f_orig
        mov esi, [ebp-4]
        mov esi, [esi+0x1c]
        test esi, esi
        jz f_orig
        mov eax, [ebx+%(clock)#x]
        mov eax, [eax]
        mov edx, [eax+0x40]
        lea edi, [ebx+%(tab)#x]
        mov ecx, %(nent)d
    f_find:
        cmp [edi], esi
        je f_found
        add edi, 12
        dec ecx
        jnz f_find
        lea edi, [ebx+%(tab)#x]
        mov eax, edi
        mov ecx, %(nent1)d
    f_pick:
        add edi, 12
        push edx
        mov edx, [edi+8]
        cmp edx, [eax+8]
        pop edx
        jae f_pk
        mov eax, edi
    f_pk:
        dec ecx
        jnz f_pick
        mov edi, eax
        mov [edi], esi
        mov [edi+4], edx
        jmp f_seen
    f_found:
        mov eax, edx
        sub eax, [edi+8]
        cmp eax, %(gap)d
        jbe f_seen
        mov [edi+4], edx
    f_seen:
        mov [edi+8], edx
        mov eax, edx
        sub eax, [edi+4]
        cmp eax, %(n)d
        jae f_orig
        imul eax, eax, %(dl)d
        xor edx, edx
        mov ecx, %(n)d
        div ecx
        add eax, %(l0)d
        mov edx, eax
        mov eax, [ebx+%(intens)#x]
        mov eax, [eax]
        call %(getlut)#x
        mov ebx, eax
        pop edi
        pop esi
        pop edx
        pop ecx
        pop eax
        xchg ebx, [esp]
        push ebx
        mov ebx, [eax]
        jmp dword ptr [ebx+0x94]
    f_orig:
        pop edi
        pop esi
        pop edx
        pop ecx
        pop eax
        mov ebx, [eax]
        jmp dword ptr [ebx+0x84]
    """ % dict(ovtab=OVTAB, abil=ABIL, clock=CLOCK, tab=TAB, nent=NENT, nent1=NENT - 1, gap=GAP, n=N, dl=L1 - L0, l0=L0,
               intens=INTENS, getlut=GETLUT)
    code = asm_pic(src, ZONE + 0x10)
    blob = b"XFD1" + bytes(12) + code
    assert ZONE + len(blob) <= ZONE_END
    return blob, ZONE + 0x10


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
    zr = [hex(r) for r in R if ZONE <= r < ZONE_END]; sr = [hex(r) for r in R if SITE - 3 <= r < SITE + 8]
    zone = bytes(d[ZONE - V2F:ZONE_END - V2F]); site = bytes(d[SITE - V2F:SITE - V2F + 8])
    blob, entry = build()
    want = b"\xE8" + struct.pack("<i", entry - (SITE + 5)) + b"\x90" * 3
    st = "vanilla" if site == ORIG else ("ours" if site == want else "OTHER")
    zs = "zero" if zone == bytes(len(zone)) else ("ours" if zone[:4] == b"XFD1" else "OTHER")
    print("AoWTCPCK suspend fade-in: site %s | zone %s (%d B, entry %#x) | relocs zone %s site %s" % (
        st, zs, len(blob), entry, zr or "none", sr or "none"))
    if zr or sr: print("ABORT: relocations in the zone / under the site"); return 1
    if st == "OTHER" or zs == "OTHER": print("ABORT: site or zone holds foreign code"); return 1
    if a.revert:
        if st == "vanilla" and zs == "zero": print("already reverted"); return 0
        d[SITE - V2F:SITE - V2F + 8] = ORIG; d[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE)
        open(path, "r+b").write(d); print("reverted", path); return 0
    if st == "ours" and zone[:len(blob)] == blob:
        if a.dis: dis(d, entry, ZONE + len(blob))
        print("already applied"); return 0
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if os.path.abspath(path) == os.path.abspath(DLL):
        bak = bak_path(DLL, ".bak_suspfadein")
        if not os.path.exists(bak): shutil.copy2(DLL, bak); print("backup ->", bak)
    d[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE); d[ZONE - V2F:ZONE - V2F + len(blob)] = blob
    d[SITE - V2F:SITE - V2F + 8] = want
    open(path, "r+b").write(d); print("written", path)
    if a.dis: dis(d, entry, ZONE + len(blob))
    return 0


if __name__ == "__main__":
    sys.exit(main())
