#!/usr/bin/env python3
r"""
Town Quake retune (AoWEPACK.dll, 2026-09-21).

Vanilla TTownQuake.ExecuteTE (0x557B1DFC) phase 0x32: `map.Random(10) < 7` -> TCity.SetWallType(0) (70 % for any
wall), then every army in the city -> TriggerArmyDamage (0x557B1BF4): per unit ExecuteDamageRole(ATK 7, DMG 5,
Physical).  See memory town-quake-spell.
New rules (user):
  * walls: wood 80 %, stone 50 %; underground (+depths) +10 % each (90 % / 60 %); no walls -> nothing to destroy;
  * unit damage: underground cities with no walls or wooden walls roll at ATK 9 instead of 7 (= +20 percentage
    points of hit chance for the usual DEF range, capped at 90 % by the engine's 10 % fumble); stone walls keep 7.
Hook A 0x557B1E79 (10 B `mov edx,0xA ; call Random`) -> cave_walls: Random(10); N = 8 (wood [city+0x4C]==1) /
5 (stone ==2) / 0 (none); +1 when [city+0x12] (level) != 0 and N != 0; stores the damage ATK (9 or 7) in a BSS
global; `cmp eax, N` and resume at the vanilla `jge` (0x557B1E86).  Hook B 0x557B1CE7 (`mov edx,7`) -> cave_atk:
edx = G_ATK (7 when unset).  BSS global 0x558FA2B0 (next to G_CASTER 0x558FA2A0); PIC via call/pop delta.
Caves 0x55816F00.. (zero-verified).  Backup AoWEPACK.dll.bak_townquake (in <game>\backup\).
Dry-run default; --apply; --revert; --dis.
"""
import argparse, os, shutil, struct, sys
from bakpath import game_dir, game_file, bak_path
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

DEFAULT_DLL = game_file(r"AoWEPACK.dll")
BAK = ".bak_townquake"
BASE = 0x55700000
MAP_RANDOM = 0x5577827C
G_ATK = 0x558FA2B0
HA, HA_ORIG, HA_RESUME = 0x557B1E79, bytes.fromhex("ba0a000000e8f963fcff"), 0x557B1E86
HB, HB_ORIG, HB_RESUME = 0x557B1CE7, bytes.fromhex("ba07000000"), 0x557B1CEC
CAVE_A, CAVE_B, CAVE_END = 0x55816F00, 0x55816F60, 0x55816F80
WOOD_PCT, STONE_PCT, UG_BONUS = 8, 5, 1
ATK_NORMAL, ATK_UG = 7, 9
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, addr):
    src = chr(10).join(l.split(';')[0] for l in src.splitlines())
    enc, _ = ks.asm(src, addr)
    return bytes(enc)


def cave_walls(va):
    return asm(f"""
        mov edx, 10
        call {MAP_RANDOM:#x}
        movzx ecx, byte ptr [ebx + 0x4C]
        mov edx, {WOOD_PCT}
        cmp ecx, 1
        je w_have
        mov edx, {STONE_PCT}
        cmp ecx, 2
        je w_have
        xor edx, edx
    w_have:
        push eax
        mov eax, {ATK_NORMAL}
        cmp byte ptr [ebx + 0x12], 0
        je w_store
        test edx, edx
        jz w_ug
        add edx, {UG_BONUS}
    w_ug:
        cmp ecx, 2
        je w_store
        mov eax, {ATK_UG}
    w_store:
        push ecx
        call w_here
    w_here:
        pop ecx
        sub ecx, w_here
        mov [ecx + {G_ATK:#x}], eax
        pop ecx
        pop eax
        cmp eax, edx
        jmp {HA_RESUME:#x}
    """, va)


def cave_atk(va):
    return asm(f"""
        call a_here
    a_here:
        pop edx
        sub edx, a_here
        mov edx, [edx + {G_ATK:#x}]
        test edx, edx
        jnz a_ok
        mov edx, {ATK_NORMAL}
    a_ok:
        jmp {HB_RESUME:#x}
    """, va)


def build():
    a = cave_walls(CAVE_A); assert CAVE_A + len(a) <= CAVE_B, hex(CAVE_A + len(a))
    b = cave_atk(CAVE_B); assert CAVE_B + len(b) <= CAVE_END, hex(CAVE_B + len(b))
    return [(CAVE_A, a, "walls"), (CAVE_B, b, "atk")]


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


def jmp_bytes(src, dst, ln):
    return b"\xe9" + struct.pack("<i", dst - (src + 5)) + b"\x90" * (ln - 5)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dll", nargs="?", default=DEFAULT_DLL)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    dll = a.dll; bak = bak_path(dll, BAK, create=a.apply)
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
    hooks = [("walls", HA, HA_ORIG, CAVE_A), ("atk", HB, HB_ORIG, CAVE_B)]
    states = []
    print(f"target: {dll}")
    for name, va, orig, cave in hooks:
        o = va2off(data, va); cur = bytes(data[o:o + len(orig)])
        st = "vanilla" if cur == orig else "ALREADY PATCHED" if cur[0] == 0xE9 and va + 5 + struct.unpack_from("<i", cur, 1)[0] == cave else f"UNKNOWN {cur.hex()}"
        states.append(st); print(f"  hook {name:5} 0x{va:x}: {st}")
    for va, blob, name in caves:
        print(f"  cave {name:5} {va:#x}..{va + len(blob):#x} ({len(blob)} B)")
    z0, z1 = va2off(data, CAVE_A), va2off(data, CAVE_END)
    zone_zero = all(v == 0 for v in data[z0:z1])
    rl = reloc_hits(data, [(va, va + len(orig)) for _, va, orig, _ in hooks] + [(CAVE_A, CAVE_END)])
    print(f"  cave zone zero: {zone_zero}; relocs: {[hex(v) for v in rl] or 'none'}; wood {WOOD_PCT*10}% stone {STONE_PCT*10}% (+{UG_BONUS*10}% UG), UG ATK {ATK_UG}")
    if not a.apply:
        print("dry run - nothing written (use --apply)"); return
    if rl or any(s.startswith("UNKNOWN") for s in states):
        sys.exit("refusing: relocs or unexpected bytes")
    applied = any(s == "ALREADY PATCHED" for s in states)
    if not applied and not zone_zero:
        sys.exit("cave zone not empty - refusing")
    if not os.path.exists(bak):
        shutil.copy2(dll, bak); print(f"  backup -> {bak}")
    for va, blob, name in caves:
        o = va2off(data, va); data[o:o + len(blob)] = blob
    for name, va, orig, cave in hooks:
        o = va2off(data, va); data[o:o + len(orig)] = jmp_bytes(va, cave, len(orig))
    with open(dll, "r+b") as f:
        f.seek(0); f.write(data)
    print("applied." if not applied else "re-applied (caves rewritten).")


if __name__ == "__main__":
    main()
