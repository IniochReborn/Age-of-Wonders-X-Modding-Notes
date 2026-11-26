"""
DROUGHT (391) - the glow on desertified hexes (2026-10-14).  AoWEPACK.dll.

Drought marks every hex it changes with a TFrozenWaterHS marker (restore terrain [hs+0xE] | 0x80, see
patch_drought_v1.py).  TFrozenWaterHS.Show (VMT 0x557147B4 +0xA8 = 0x55764BD0) draws the general-FX slot 0x46 (the BLUE
unit-enchantment sparkle) through ImageLib.TImageSequenceList.ShowLoopedEx (thunk 0x5570291C; eax list, edx slot,
ecx x; pushes y, tick, phase, surface; callee pops 4 args).  ShowLoopedEx steps the SHARED sequence's frame counter
on every call (the lesson from the city glow), so hundreds of Drought markers also sped up every unit sparkle.

Hook: the 10 bytes `mov edx,0x46 / call ShowLoopedEx` @0x55764C5B -> `call cave` + 5 nops (no relocs).
  cave: a marker WITHOUT bit 0x80 in [ebx+0xE] (ebx = the marker in Show) -> `mov edx,0x46 / jmp ShowLoopedEx`
        (a tail jump: the callee returns to the hook's return address and pops the 4 args, exactly as before).
        A Drought marker -> a PURE draw (no shared state): seq = GetSpell(391).[spell+0x2C] slot GLOW_SLOT
        (TImageSequenceList.GetImageSequence thunk 0x557028E4); idx = (tick / PERIOD + phase) mod frames;
        id = frames[idx] ([seq+0x1C] TList: +4 items, +8 count); TCustomImageLibrary.ImageExist / Get (thunks
        0x55702944 / 0x55702934, eax = [seq+0x10]); image VMT+0x84 Draw(edx = x + [seq+0x24], ecx = y + [seq+0x28],
        push surface); then `ret 0x10` (pops the 4 args the caller pushed).
v2 (2026-10-15): OVERGROWTH markers too (patch_overgrowth_v1.py v2: [hs+0xE] & 0xC0 == 0x40) -> the same pure draw
with spell 383 gfx slot 3 (OG_SLOT; a dim green haze).  Bit 0x80 (Drought) is tested first and its draw is unchanged;
vanilla / raise-terrain markers ([hs+0xE] = a terrain <= 0xC, bit 0x40 clear) still fall through to the vanilla
sparkle with eax/ecx untouched.  Upgrades v1 in place.
v3 (2026-10-15): ICE AGE markers (patch_overgrowth_v1.py v5: [hs+0xE] & 0xC0 == 0xC0) -> the same pure draw with
spell 399 gfx slot 3 (ICE_SLOT) at ICE_PERIOD ticks per frame: a copy of the vanilla Freeze Water sparkle (general-FX
slot 0x46 = EFFECTS\\SWARM.ILB frames 20..31 + 20,22,..,30, 64x64, anchor (-33, -39), additive 770) at a lower blend.
The 0xC0 test runs first (0xC0 also has bit 0x80 set); Drought (0x80 alone) and Overgrowth (0x40 alone) draw as
before.  The kind (0 Drought / 1 Overgrowth / 2 Ice Age) is kept on the frame ([ebp-0x10]) for the period choice.
Zone 0x5585FE00..0x5585FF00 (free run below the worldfx cave; verified zero / no relocs).  PIC via call/pop delta for
the AoWHSSet global (AoWEPACK rebases).  Dry-run default; --apply / --revert.  Backup .bak_droughtglow.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DLL = game_file("AoWEPACK.dll")
BASE, CODE_V2F = 0x55700000, 0x55700C00
SITE, ORIG = 0x55764C5B, bytes.fromhex("ba46000000e8b7dcf9ff")
SHOWLOOPEDEX = 0x5570291C
GETSPELL, GETIMAGESEQ, IMAGEEXIST, LIBGET = 0x55779AC8, 0x557028E4, 0x55702944, 0x55702934
AOWHSSET = 0x558FA044
ZONE, ZONE_END = 0x5585FE00, 0x5585FF00
SPELL_ID, GLOW_SLOT, PERIOD = 391, 3, 6   # v5 2026-10-15: slot 3 (slots 0..2 = the Air-Mastery-style map drift, patch_drought_worldfx_v1.py v3)
OG_ID, OG_SLOT = 383, 3              # v2: Overgrowth markers ([hs+0xE] & 0xC0 == 0x40) draw spell 383 slot 3
ICE_ID, ICE_SLOT, ICE_PERIOD = 399, 3, 3   # v4 2026-10-15: Drought's slot 1 is now the same sparkle (red/orange) and also steps at ICE_PERIOD; only Overgrowth keeps PERIOD; v3: Ice Age markers ([hs+0xE] & 0xC0 == 0xC0) draw spell 399 slot 3 (vanilla sparkle f18 = 2 -> ~3 ticks/frame)

ks = Ks(KS_ARCH_X86, KS_MODE_32)


def build(va):
    src = """
        test byte ptr [ebx+0xe], 0x80
        jz c40
        test byte ptr [ebx+0xe], 0x40
        jnz d3
        xor eax, eax
        jmp dr
    c40:
        test byte ptr [ebx+0xe], 0x40
        jnz d2
        mov edx, 0x46
        jmp %(slx)#x
    d2:
        push 1
        pop eax
        jmp dr
    d3:
        push 2
        pop eax
    dr:
        push ebp
        mov ebp, esp
        push ebx
        push esi
        push edi
        push eax
        push ecx
        mov edi, eax
        .byte 0xe8, 0, 0, 0, 0
        pop esi
        sub esi, 0x7fffffff
        mov eax, [esi+%(hsset)#x]
        mov eax, [eax+0x84]
        mov edx, %(id)d
        cmp edi, 1
        jb s1
        mov edx, %(ogid)d
        je s1
        mov edx, %(iceid)d
    s1:
        call %(getspell)#x
        test eax, eax
        jz out
        mov eax, [eax+0x2c]
        test eax, eax
        jz out
        mov edx, %(slot)d
        cmp edi, 1
        jb s2
        mov edx, %(ogslot)d
        je s2
        mov edx, %(iceslot)d
    s2:
        call %(getseq)#x
        test eax, eax
        jz out
        mov esi, eax
        mov edi, [esi+0x1c]
        mov ecx, [edi+8]
        test ecx, ecx
        jz out
        mov eax, [ebp+0x10]
        xor edx, edx
        mov ebx, %(period)d
        cmp dword ptr [ebp-0x10], 1
        je p1
        mov ebx, %(iceperiod)d
    p1:
        div ebx
        add eax, [ebp+0xc]
        xor edx, edx
        div ecx
        mov eax, [edi+4]
        mov edi, [eax+edx*4]
        mov edx, edi
        mov eax, [esi+0x10]
        call %(exist)#x
        test al, al
        jz out
        push dword ptr [ebp+8]
        mov edx, edi
        mov eax, [esi+0x10]
        call %(get)#x
        mov ecx, [ebp+0x14]
        add ecx, [esi+0x28]
        mov edx, [esp+4]
        add edx, [esi+0x24]
        mov ebx, [eax]
        call dword ptr [ebx+0x84]
    out:
        pop ecx
        pop edx
        pop edi
        pop esi
        pop ebx
        pop ebp
        ret 0x10
    """ % {"slx": SHOWLOOPEDEX, "hsset": AOWHSSET, "id": SPELL_ID, "getspell": GETSPELL, "slot": GLOW_SLOT, "getseq": GETIMAGESEQ, "ogid": OG_ID, "ogslot": OG_SLOT, "iceid": ICE_ID, "iceslot": ICE_SLOT, "iceperiod": ICE_PERIOD,
           "period": PERIOD, "exist": IMAGEEXIST, "get": LIBGET}
    b = bytearray(ks.asm(src, va)[0])
    anchor = bytes.fromhex("e8000000005e81eeffffff7f"); k = b.find(anchor); assert k >= 0
    struct.pack_into("<I", b, k + 8, va + k + 5)
    return bytes(b)


def relocs(d):
    pe = struct.unpack_from("<I", d, 0x3C)[0]; opt = struct.unpack_from("<H", d, pe + 20)[0]; nsec = struct.unpack_from("<H", d, pe + 6)[0]
    secs = [struct.unpack_from("<IIII", d, pe + 24 + opt + 40 * k + 8) for k in range(nsec)]
    rrva, rsz = struct.unpack_from("<II", d, pe + 24 + 0x88)
    def r2f(rva):
        for vs, va, rs, ro in secs:
            if va <= rva < va + max(vs, rs): return ro + rva - va
    p = r2f(rrva); end = p + rsz; out = set()
    while p < end:
        page, size = struct.unpack_from("<II", d, p)
        if size < 8: break
        for q in range(p + 8, p + size, 2):
            e = struct.unpack_from("<H", d, q)[0]
            if e >> 12 == 3: out.add(BASE + page + (e & 0xFFF))
        p += size
    return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true"); ap.add_argument("--dis", action="store_true"); a = ap.parse_args()
    d = bytearray(open(DLL, "rb").read())
    cave = build(ZONE); assert ZONE + len(cave) <= ZONE_END
    hook = b"\xe8" + struct.pack("<i", ZONE - (SITE + 5)) + b"\x90" * 5
    live = bytes(d[SITE - CODE_V2F:SITE - CODE_V2F + 10]); zl = bytes(d[ZONE - CODE_V2F:ZONE_END - CODE_V2F])
    state = "vanilla" if live == ORIG else "ours" if live == hook else "OTHER"
    zstate = "zero" if not any(zl) else "ours" if zl[:len(cave)] == cave and not any(zl[len(cave):]) else "DIFFERS"
    bad = [hex(r) for r in relocs(bytes(d)) if ZONE <= r < ZONE_END or SITE <= r < SITE + 10]
    print("site %s | zone %s (%d B) | relocs %s" % (state, zstate, len(cave), bad or "none"))
    if a.dis:
        import capstone
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(cave, ZONE): print("   %08X  %-18s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad or state == "OTHER": print("ABORT"); return 1
    if a.revert:
        d[SITE - CODE_V2F:SITE - CODE_V2F + 10] = ORIG; d[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
        open(DLL, "r+b").write(bytes(d)); print("reverted"); return 0
    if state == "ours" and zstate == "ours": print("already applied"); return 0
    if zstate == "DIFFERS" and state != "ours": print("ABORT (zone not free)"); return 1
    d[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE); d[ZONE - CODE_V2F:ZONE - CODE_V2F + len(cave)] = cave
    d[SITE - CODE_V2F:SITE - CODE_V2F + 10] = hook
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(DLL, ".bak_droughtglow")
    if not os.path.exists(bak): shutil.copy2(DLL, bak); print("backup ->", bak)
    with open(DLL, "r+b") as f: f.write(bytes(d))
    assert open(DLL, "rb").read() == bytes(d); print("Written and verified"); return 0


if __name__ == "__main__":
    sys.exit(main())
