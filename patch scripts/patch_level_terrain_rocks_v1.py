#!/usr/bin/env python3
r"""
Level Terrain leaves decorative rocks on the flattened hexes (AoWEPACK.dll, 2026-09-21).

Vanilla: TLevelTerrainTE.Execute (0x5579F16C) -> worker 0x5579F068 HN-walks the 7 hexes (ebx = TMapLevel,
esi = TMapField, edi = TE with level byte [+0x22]; x = [esp+0x10], y = [esp+0x14]); per valid hex it calls
THSMap.ClearTerrain(map, x, y, -1, 0, level) (thunk 0x557025DC; msg 0x10 frees EVERY TTerrainMO on the hex:
mountain, hill, vegetation, decoration) and, for terrain 7 (earth wall), map.ChangeTerrain (VMT+0xD0) to dirt
(0xC) with radius 0.  A flattened mountain/hill is left as a bare hexagon.

Patch: hook the 5-byte `movsx eax,[edi+0x22] ; push eax` @0x5579F109 (start of the ClearTerrain call) -> cave_lvl
replays ClearTerrain + the earth->dirt branch, and when the hex WAS a mountain or hill (pre-clear overlay byte
[field+0x15] in {0 Mountain, 2 Hill}; bare hexes carry 0xFF per TMapField.Initialize) or an earth wall (pre
terrain 7), it calls cave_rocks(map, x, y, terrain=[field+0x14] (post-dig), level) then resumes at 0x5579F153.

cave_rocks = TAoWHSMap.PlaceTerrain (0x55778EEC) with a decoration filter: scans the global resource list
([[0x558FA044]+0x24]+8) for ClassID 0x20167 (TTerrainMO) resources with a single-hex TTerrainList ([res+0x28]:
UsedTerrain==1, GetTerrain(0)==terrain, GetOverlay(0)==0xFF = no overlay => no movement cost) whose decoration
byte [res+0x44] is 1 (Rocks: GR_ROCKS/ZGR_STON, DE_*, SN_*, ST_*, WL_* for terrains 1-5) or 0 when the terrain
is dirt (0xC: the underground UG_ROCKS/UG_CRACKS/ZUG_STON/CA_BONES set carries no decoration tag).  RandSeed is
seeded from map.Random(0xFFFFFF) exactly like PlaceTerrain, the pick is map.Random(count) (synced RNG
[map+0x230], TE context), and the resource's VMT+0x68 CreateAndPlace(res, map, x, y, level) places it.
Terrains without a rock set (lava, ice, water...) simply get nothing.  All absolute data refs go through the
call/pop delta (AoWEPACK rebases).  Caves 0x55816D00 (lvl) and 0x55816DC0 (rocks), end 0x55816F00 (zero-verified).
Backup AoWEPACK.dll.bak_lvlrocks (in <game>\backup\).  Dry-run default; --apply; --revert; --dis.
"""
import argparse, os, shutil, struct, sys
from bakpath import game_dir, game_file, bak_path
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

DEFAULT_DLL = game_file(r"AoWEPACK.dll")
BAK = ".bak_lvlrocks"
BASE = 0x55700000
HOOK_VA, HOOK_ORIG, RESUME = 0x5579F109, bytes.fromhex("0fbe472250"), 0x5579F153
G_MAP_HOLDER = 0x558E9494      # DATA: dword -> dword -> TAoWHSMap (the TE unit's map global)
G_RESHOLDER = 0x558FA044       # BSS: object whose [+0x24]->[+8] is the global THSResource TList
IMP_TLIST = 0x558FB94C         # import slot: Classes.TList classref
IMP_RANDSEED = 0x558FB720      # import slot: System.RandSeed
CLEAR_TERRAIN = 0x557025DC     # thunk THSMap.ClearTerrain(map, x, y, [terrain -1, radius, level])
TOBJ_CREATE, TOBJ_FREE = 0x557010A8, 0x557010B8
TLIST_CLEAR, TLIST_ADD, TLIST_GET = 0x55701624, 0x5570161C, 0x5570163C
TL_USED, TL_GETTERRAIN, TL_GETOVERLAY = 0x55701CA4, 0x55701C8C, 0x55701C94
MAP_RANDOM = 0x5577827C        # TAoWHSMap.Random(eax=map, edx=range) -> eax
CLASSID_TERRAINMO = 0x20167
CAVE_LVL, CAVE_ROCKS, CAVE_END = 0x55816D00, 0x55816DC0, 0x55816F00
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, addr):
    enc, _ = ks.asm(src, addr)
    return bytes(enc)


def cave_lvl(va):
    # entry: worker frame (esp = E): x=[E+0x10], y=[E+0x14]; ebx=level, esi=field, edi=TE
    return asm(f"""
        push ebp
        mov ebp, esp
        sub esp, 8
        call l_here
    l_here:
        pop eax
        sub eax, l_here
        mov [ebp-4], eax
        movzx eax, byte ptr [esi+0x14]
        shl eax, 8
        mov al, [esi+0x15]
        mov [ebp-8], eax
        movsx eax, byte ptr [edi+0x22]
        push eax
        push 0
        push -1
        mov eax, [ebp-4]
        mov eax, [eax+{G_MAP_HOLDER:#x}]
        mov eax, [eax]
        mov ecx, [ebp+0x18]
        mov edx, [ebp+0x14]
        call {CLEAR_TERRAIN:#x}
        movsx eax, byte ptr [esi+0x14]
        cmp ax, 7
        jne l_nodig
        push esi
        mov eax, [ebp+0x18]
        push eax
        movsx eax, byte ptr [edi+0x22]
        push eax
        push 0
        push 0xC
        mov eax, [ebp-4]
        mov eax, [eax+{G_MAP_HOLDER:#x}]
        mov eax, [eax]
        mov ecx, [ebp+0x14]
        xor edx, edx
        mov esi, [eax]
        call dword ptr [esi+0xD0]
        pop esi
    l_nodig:
        mov eax, [ebp-8]
        cmp ah, 7
        je l_rocks
        cmp al, 0
        je l_rocks
        cmp al, 2
        jne l_done
    l_rocks:
        movsx eax, byte ptr [edi+0x22]
        push eax
        movzx eax, byte ptr [esi+0x14]
        push eax
        mov eax, [ebp-4]
        mov eax, [eax+{G_MAP_HOLDER:#x}]
        mov eax, [eax]
        mov edx, [ebp+0x14]
        mov ecx, [ebp+0x18]
        call {CAVE_ROCKS:#x}
    l_done:
        mov esp, ebp
        pop ebp
        jmp {RESUME:#x}
    """, va)


def cave_rocks(va):
    # cave_rocks(eax=map, edx=x, ecx=y, [level, terrain]) -> ret 8 ; [ebp+8]=terrain, [ebp+0xC]=level
    return asm(f"""
        push ebp
        mov ebp, esp
        sub esp, 0x14
        push ebx
        push esi
        push edi
        mov [ebp-4], eax
        mov [ebp-8], edx
        mov [ebp-0xC], ecx
        call r_here
    r_here:
        pop ebx
        sub ebx, r_here
        mov dl, 1
        mov eax, [ebx+{IMP_TLIST:#x}]
        call {TOBJ_CREATE:#x}
        mov [ebp-0x10], eax
        call {TLIST_CLEAR:#x}
        mov eax, [ebx+{G_RESHOLDER:#x}]
        mov eax, [eax+0x24]
        mov esi, [eax+8]
        xor edi, edi
    r_loop:
        cmp edi, [esi+8]
        jge r_pick
        mov eax, [esi+4]
        mov eax, [eax+edi*4]
        mov [ebp-0x14], eax
        mov edx, [eax]
        call dword ptr [edx+0x24]
        cmp eax, {CLASSID_TERRAINMO:#x}
        jne r_next
        mov eax, [ebp-0x14]
        mov eax, [eax+0x28]
        call {TL_USED:#x}
        cmp eax, 1
        jne r_next
        mov eax, [ebp-0x14]
        mov eax, [eax+0x28]
        xor edx, edx
        call {TL_GETTERRAIN:#x}
        cmp al, [ebp+8]
        jne r_next
        mov eax, [ebp-0x14]
        mov eax, [eax+0x28]
        xor edx, edx
        call {TL_GETOVERLAY:#x}
        cmp al, 0xFF
        jne r_next
        mov eax, [ebp-0x14]
        mov al, [eax+0x44]
        cmp al, 1
        je r_add
        test al, al
        jne r_next
        cmp byte ptr [ebp+8], 0xC
        jne r_next
    r_add:
        mov edx, [ebp-0x14]
        mov eax, [ebp-0x10]
        call {TLIST_ADD:#x}
    r_next:
        inc edi
        jmp r_loop
    r_pick:
        mov eax, [ebp-0x10]
        mov edx, [eax+8]
        test edx, edx
        jz r_free
        mov edx, 0xFFFFFF
        mov eax, [ebp-4]
        call {MAP_RANDOM:#x}
        mov edx, [ebx+{IMP_RANDSEED:#x}]
        mov [edx], eax
        mov eax, [ebp-0x10]
        mov edx, [eax+8]
        mov eax, [ebp-4]
        call {MAP_RANDOM:#x}
        mov edx, eax
        mov eax, [ebp-0x10]
        call {TLIST_GET:#x}
        mov edx, [ebp-0xC]
        push edx
        mov edx, [ebp+0xC]
        push edx
        mov ecx, [ebp-8]
        mov edx, [ebp-4]
        mov ebx, [eax]
        call dword ptr [ebx+0x68]
    r_free:
        mov eax, [ebp-0x10]
        call {TOBJ_FREE:#x}
        pop edi
        pop esi
        pop ebx
        mov esp, ebp
        pop ebp
        ret 8
    """, va)


def build():
    a = cave_lvl(CAVE_LVL); assert CAVE_LVL + len(a) <= CAVE_ROCKS, hex(CAVE_LVL + len(a))
    b = cave_rocks(CAVE_ROCKS); assert CAVE_ROCKS + len(b) <= CAVE_END, hex(CAVE_ROCKS + len(b))
    return [(CAVE_LVL, a, "lvl"), (CAVE_ROCKS, b, "rocks")]


def va2off(pe_bytes, va):
    e_lfanew = struct.unpack_from("<I", pe_bytes, 0x3C)[0]
    nsec = struct.unpack_from("<H", pe_bytes, e_lfanew + 6)[0]
    opt = struct.unpack_from("<H", pe_bytes, e_lfanew + 20)[0]
    sec = e_lfanew + 24 + opt
    for i in range(nsec):
        s = sec + 40 * i
        vsz, rva, rsz, roff = struct.unpack_from("<IIII", pe_bytes, s + 8)
        if rva <= va - BASE < rva + max(vsz, rsz):
            return roff + (va - BASE - rva)
    raise ValueError(f"VA {va:#x} not in any section")


def reloc_hits(pe_bytes, ranges):
    e_lfanew = struct.unpack_from("<I", pe_bytes, 0x3C)[0]
    dd_rva, dd_sz = struct.unpack_from("<II", pe_bytes, e_lfanew + 24 + 0x88)
    if not dd_sz:
        return []
    off = va2off(pe_bytes, BASE + dd_rva); end = off + dd_sz; hits = []
    while off + 8 <= end:
        page, bsz = struct.unpack_from("<II", pe_bytes, off)
        if bsz < 8:
            break
        for i in range((bsz - 8) // 2):
            e = struct.unpack_from("<H", pe_bytes, off + 8 + 2 * i)[0]
            if e >> 12:
                va = BASE + page + (e & 0xFFF)
                if any(lo <= va < hi for lo, hi in ranges):
                    hits.append(va)
        off += bsz
    return hits


def jmpop(src, dst):
    return b"\xe9" + struct.pack("<i", dst - (src + 5))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dll", nargs="?", default=DEFAULT_DLL)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    dll = a.dll
    bak = bak_path(dll, BAK, create=a.apply)
    caves = build()
    if a.dis:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
        md = Cs(CS_ARCH_X86, CS_MODE_32)
        for va, blob, name in caves:
            print(f"\n; ---- {name} @{va:#x} ({len(blob)} B) ----")
            for ins in md.disasm(blob, va):
                print(f"{ins.address:08X}  {ins.mnemonic:<7} {ins.op_str}")
    if a.revert:
        if not os.path.exists(bak):
            sys.exit(f"no backup {bak}")
        shutil.copy2(bak, dll); print(f"reverted {dll} from {bak}"); return
    data = bytearray(open(dll, "rb").read())
    ho = va2off(data, HOOK_VA); cur = bytes(data[ho:ho + 5])
    tgt = HOOK_VA + 5 + struct.unpack_from("<i", cur, 1)[0] if cur[0] == 0xE9 else None
    st = "vanilla" if cur == HOOK_ORIG else "ALREADY PATCHED" if tgt == CAVE_LVL else f"UNKNOWN {cur.hex()}"
    print(f"target: {dll}\n  hook 0x{HOOK_VA:x}: {st}")
    for va, blob, name in caves:
        print(f"  cave {name:6} {va:#x}..{va + len(blob):#x} ({len(blob)} B)")
    z0, z1 = va2off(data, CAVE_LVL), va2off(data, CAVE_END)
    zone_zero = all(v == 0 for v in data[z0:z1])
    rl = reloc_hits(data, [(HOOK_VA, HOOK_VA + 5), (CAVE_LVL, CAVE_END)])
    print(f"  cave zone zero: {zone_zero}; relocs: {[hex(v) for v in rl] or 'none'}")
    if not a.apply:
        print("dry run - nothing written (use --apply)"); return
    if rl or st.startswith("UNKNOWN"):
        sys.exit("refusing: relocs or unexpected bytes")
    applied = st == "ALREADY PATCHED"
    if not applied and not zone_zero:
        sys.exit("cave zone not empty - refusing")
    if not os.path.exists(bak):
        shutil.copy2(dll, bak); print(f"  backup -> {bak}")
    for va, blob, name in caves:
        o = va2off(data, va); data[o:o + len(blob)] = blob
    data[ho:ho + 5] = jmpop(HOOK_VA, CAVE_LVL)
    with open(dll, "r+b") as f:
        f.seek(0); f.write(data)
    print("applied." if not applied else "re-applied (caves rewritten).")


if __name__ == "__main__":
    main()
