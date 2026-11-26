"""patch_banlist_storage_v1.py  [--apply | --revert | --dis]

BAN LIST storage (user 2026-11-19: editor Map Settings > Ban List - banned spells / abilities, stored per map).
This script only stores the data; the rules (AoWEPACK) and the editor tab (AoWDevX) are separate scripts.

Interface for the other scripts
  BAN_GET = 0x558BA200 (AoWEPACK, PIC):  -> eax = pointer to 96 bytes; every other register preserved.
      bytes  0..63  spell bitset   (spell id 0..511:  byte id >> 3, bit id & 7)
      bytes 64..95  ability bitset (ability id 0..255)
  The bytes live IN THE MAP OBJECT: TAoWHSMap +0x420..+0x480 (InstanceSize 0x420 -> 0x480; NewInstance zero-fills, so
  a new map / a freshly loaded map starts with an empty list and nothing leaks from one map to the next; header and
  preview reads of other map files use their own instance and cannot disturb the running game).  BAN_GET returns
  [AoWE.AoWHSMap 0x558FA040] + 0x420 - the engine's current map, set by TAoWEngine (0x5579868E) in the game and the
  editor alike, nil while no map is open.  With no map it returns FALLBACK = 0x5590B360 (96 B of AoWEPACK .idata page
  slack 0x5590B350..0x5590B3C0, beyond the raw data = zero at load, writable; free between the Smokescreen VMT clone,
  which ends 0x5590B350, and leader-soul's 0x5590B3C0) so callers never get nil.

Stream (maps .hsm and saves .asg/.acg, game + editor; also what the OoS-restore rig and MP joins transfer)
  TAoWHSMap.ReadWrite 0x55776D60 streams tagged properties through an Engine.TEStorageStream (VMT +0 StorageMode,
  +0x1C rwData(eax stream, edx ptr, ecx size, push tag)).  The tags are dwords in a per-object directory: the reader
  looks a tag up (0x5550FE70) and leaves the field alone when it is absent; unknown tags are never visited.  So the
  format is compatible both ways: a map without the tag loads with an empty list, a map WITH the tag loads in an
  unpatched game / editor (which simply drops the list when it saves again).  Same mechanism as the level mask
  (patch_map_levels_ui_editor_v3: tags 0x10062 / 0x60) and the MP lobby name (tag 0x10061).
  Hook: the last property of ReadWrite, `mov eax,esi / mov esi,[eax] / call [esi+0x1C]` @0x55777258 (rwData tag 0x3F;
  7 B, no relocation; edi and esi are dead afterwards) -> cave: replays it, then
      mode = stream.StorageMode   (Read 0x01/0x09, ReadText 0x05, Write 0x02/0x0A, WriteText 0x06,
                                   Translate 0x15, SetupCompare 0x21, Compare 0x41 - the last three run on the LIVE map)
      reading (bit 0, none of 0x70): zero the 96 bytes, then rwData(map+0x420, 96, tag 0x10063)
      compare / translate:           rwData only (nothing is zeroed)
      writing:                       rwData only when the list is not empty (an unused list leaves the file unchanged)
Sites: S1 0x5570E858 dword InstanceSize 0x420 -> 0x480 (the level-mask script set it to 0x420 from vanilla 0x41C - that
script reports its M1 as foreign while this is applied: revert this one first, LIFO);  S2 0x55777258.
Cave 0x558BA200.. (zone 0x558BA200-0x558BA600, was zero, reloc-free).  In-place apply / revert.
Multiplayer: every player needs it (the list travels in the map file).
"""
import argparse, os, shutil, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path

DLL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "AoWEPACK.dll")
BASE, V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x558BA200, 0x558BA600
BAN_GET = ZONE
GLOBAL_MAP, FALLBACK = 0x558FA040, 0x5590B360
MAP_OFS, BAN_SIZE, TAG = 0x420, 0x60, 0x10063
S1, S1_OLD, S1_NEW = 0x5570E858, struct.pack("<I", 0x420), struct.pack("<I", MAP_OFS + BAN_SIZE)
S2, S2_ORIG, S2_BACK = 0x55777258, bytes.fromhex("8bc68b30ff561c"), 0x5577725F


def build():
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    src = f"""
    ban_get:
        call bg_d
    bg_d:
        pop eax
        sub eax, bg_d
        push eax
        mov eax, [eax + {GLOBAL_MAP:#x}]
        test eax, eax
        jz bg_fb
        add esp, 4
        add eax, {MAP_OFS:#x}
        ret
    bg_fb:
        pop eax
        add eax, {FALLBACK:#x}
        ret

    .balign 16
    rw:
        mov eax, esi
        mov edi, esi
        mov esi, [eax]
        call dword ptr [esi + 0x1c]
        mov eax, edi
        mov edx, [eax]
        call dword ptr [edx]
        lea edx, [ebx + {MAP_OFS:#x}]
        test al, 1
        jz rw_wr
        test al, 0x70
        jnz rw_do
        push edi
        mov edi, edx
        xor eax, eax
        mov ecx, {BAN_SIZE // 4:#x}
        rep stosd
        pop edi
        jmp rw_do
    rw_wr:
        mov ecx, {BAN_SIZE // 4:#x}
    rw_l:
        cmp dword ptr [edx + ecx*4 - 4], 0
        jne rw_do
        dec ecx
        jnz rw_l
        jmp rw_done
    rw_do:
        push {TAG:#x}
        lea edx, [ebx + {MAP_OFS:#x}]
        mov ecx, {BAN_SIZE:#x}
        mov eax, edi
        mov esi, [eax]
        call dword ptr [esi + 0x1c]
    rw_done:
        jmp {S2_BACK:#x}
    """
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    code = bytes(ks.asm(src, ZONE)[0])
    rw = struct.unpack("<I", bytes(ks.asm(src + "\n.long rw\n", ZONE)[0])[-4:])[0]
    assert ZONE + len(code) <= ZONE_END
    return code, rw


def relocs(d):
    pe = struct.unpack_from("<I", d, 0x3C)[0]; opt = struct.unpack_from("<H", d, pe + 20)[0]; n = struct.unpack_from("<H", d, pe + 6)[0]
    secs = [struct.unpack_from("<IIII", d, pe + 24 + opt + 40 * k + 8) for k in range(n)]
    def off(rva):
        for vs, va, rs, ro in secs:
            if va <= rva < va + max(vs, rs): return ro + rva - va
    rrva, rsz = struct.unpack_from("<II", d, pe + 24 + 0x88)
    p, out = off(rrva), set(); end = p + rsz
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
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true"); ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    cave, rw = build()
    s2_new = bytes([0xE9]) + struct.pack("<i", rw - (S2 + 5)) + b"\x90\x90"
    d = open(DLL, "rb").read()
    if a.dis:
        import capstone
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(cave, ZONE):
            print("   %08X  %-16s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    rl = relocs(d)
    bad = sorted(r for r in rl if any(lo - 3 <= r < hi for lo, hi in ((S1, S1 + 4), (S2, S2 + 7), (ZONE, ZONE_END))))
    c1, c2, cz = d[S1 - V2F:S1 - V2F + 4], d[S2 - V2F:S2 - V2F + 7], d[ZONE - V2F:ZONE_END - V2F]
    vanilla = c1 == S1_OLD and c2 == S2_ORIG and not any(cz)
    ours = c1 == S1_NEW and c2 == s2_new and cz == cave + bytes(len(cz) - len(cave))
    older = c1 == S1_NEW and c2[0] == 0xE9 and not ours
    state = "vanilla" if vanilla else "ours" if ours else "older build" if older else "OTHER"
    print("S1 %#x InstanceSize %#x, S2 %#x -> rw %#x, BAN_GET %#x, cave %#x..%#x (%d B): %s"
          % (S1, struct.unpack("<I", c1)[0], S2, rw, BAN_GET, ZONE, ZONE + len(cave), len(cave), state))
    if bad: print("ABORT: relocations inside patched ranges:", [hex(r) for r in bad]); return 1
    if state == "OTHER": print("ABORT: foreign bytes", c1.hex(), c2.hex(), "zone zero" if not any(cz) else "zone used"); return 1
    if state == ("vanilla" if a.revert else "ours"): print("already %s" % ("reverted" if a.revert else "applied")); return 0
    if not (a.apply or a.revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    b = bak_path(DLL, ".bak_banstore")
    if a.apply and not os.path.exists(b): shutil.copy2(DLL, b); print("backup ->", b)
    with open(DLL, "r+b") as f:
        f.seek(ZONE - V2F); f.write(bytes(ZONE_END - ZONE))
        if a.apply: f.seek(ZONE - V2F); f.write(cave)
        f.seek(S1 - V2F); f.write(S1_NEW if a.apply else S1_OLD)
        f.seek(S2 - V2F); f.write(s2_new if a.apply else S2_ORIG)
    print("Written" if a.apply else "reverted")
    return 0


if __name__ == "__main__":
    sys.exit(main())
