#!/usr/bin/env python3
r"""
Tactical group move: entering a group-mate's ORIGIN hex costs its terrain, not 0 (AoWTCPCK.dll, 2026-09-21).
Companion of patch_group_move_repath_v1.py / patch_group_move_passthrough_v1.py -- the last cause of the
"rear units detour" jank.

Diagnosis (live cost-grid reads with grid_probe.py, 3-unit box select, 3-hex advance): the rear unit's grid was
correct EXCEPT that every hex holding a same-side TMovementHS origin marker (a group-mate that will have left)
had the cost of its neighbour, i.e. entering it cost 0.  Cause: TTacticalCombatUnitHS.CanMoveOn 0x42079C,
own-hex branch: it first writes -1/final (unit stands here), then, when a flag-1 marker of the same side is on
the field, writes `[result] := 0, final := 0` (0x42083A) -- the terrain cost the pathfinder passed in [result]
is lost.  The pathfinder's grid then no longer equals path length, and its backward path reconstruction
(AoWE 0x557460B0: "neighbour whose cost == mine - my step cost", first match in direction order) happily
chains through those 0-cost hexes: (12,37)->(15,35) came out as (13,37),(14,38)*,(15,37),(15,36)*,(15,35)
(* = origin hexes, grid cost 12 = "optimal", real length 5 / 20 MP) instead of (13,36),(14,36),(15,35).
Vanilla has the same bug; it is one reason vanilla group moves look drunk.

Patch: 7-byte hook at 0x42083A (`mov eax,[ebp-0xC] ; xor edx,edx ; mov [eax],edx`) -> cave: recompute the
hex's terrain cost exactly like the part branch does (0x420B0C: [mc + terrain*16 + overlay + 0x31],
ctx = [ebp-8]: +0 move control, +4 field) and store it in [result]; back to 0x420841 (final := 0, exit).
No absolute references.  Cave 0x43AB00.. (zero-verified).  Backup AoWTCPCK.dll.bak_grouporigin (in <game>\backup\).
Dry-run default; --apply; --revert; --dis.
"""
import argparse, os, shutil, struct, sys
from bakpath import game_dir, game_file, bak_path
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

DEFAULT_DLL = game_file(r"AoWTCPCK.dll")
BAK = ".bak_grouporigin"
BASE = 0x400000
HOOK_VA = 0x42083A
HOOK_ORIG = bytes.fromhex("8b45f433d28910")   # mov eax,[ebp-0xC] ; xor edx,edx ; mov [eax],edx
RESUME = 0x420841                              # mov eax,[ebp-0xC] ; mov byte [eax+8],0 ; jmp exit
CAVE_BASE, CAVE_END = 0x43AB00, 0x43AB40
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, addr):
    enc, _ = ks.asm(src, addr)
    return bytes(enc)


def cave_main(va):
    return asm(f"""
        mov edx, [ebp-8]
        mov eax, [edx+4]
        movsx ecx, byte ptr [eax+0x14]
        movsx eax, byte ptr [eax+0x15]
        mov edx, [edx]
        shl ecx, 4
        add edx, ecx
        movsx eax, byte ptr [edx+eax+0x31]
        mov edx, [ebp-0xC]
        mov [edx], eax
        jmp {RESUME:#x}
    """, va)


def build():
    blob = cave_main(CAVE_BASE)
    assert CAVE_BASE + len(blob) <= CAVE_END
    return [(CAVE_BASE, blob, "origin-cost")]


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
    ho = va2off(data, HOOK_VA); cur = bytes(data[ho:ho + len(HOOK_ORIG)])
    applied = cur[0] == 0xE9; vanilla = cur == HOOK_ORIG
    print(f"target: {dll}\n  hook 0x{HOOK_VA:x}: {'ALREADY PATCHED' if applied else 'vanilla' if vanilla else 'UNKNOWN BYTES ' + cur.hex()}")
    for va, blob, name in caves:
        print(f"  cave {name} {va:#x}..{va + len(blob):#x} ({len(blob)} B)")
    z0, z1 = va2off(data, CAVE_BASE), va2off(data, CAVE_END)
    zone_zero = all(v == 0 for v in data[z0:z1])
    rl = reloc_hits(data, [(HOOK_VA, HOOK_VA + len(HOOK_ORIG)), (CAVE_BASE, CAVE_END)])
    print(f"  cave zone zero: {zone_zero}; relocs: {[hex(v) for v in rl] or 'none'}")
    if not a.apply:
        print("dry run - nothing written (use --apply)"); return
    if rl:
        sys.exit("relocs intersect the patch - refusing")
    if applied:
        print("already applied - rewriting cave in place")
    elif not vanilla:
        sys.exit("hook-site bytes are neither vanilla nor ours - refusing")
    if not applied and not zone_zero:
        sys.exit("cave zone not empty - refusing")
    if not os.path.exists(bak):
        shutil.copy2(dll, bak); print(f"  backup -> {bak}")
    for va, blob, name in caves:
        o = va2off(data, va); data[o:o + len(blob)] = blob
    data[ho:ho + len(HOOK_ORIG)] = jmp_bytes(HOOK_VA, CAVE_BASE, len(HOOK_ORIG))
    with open(dll, "r+b") as f:
        f.seek(0); f.write(data)
    print("applied.")


if __name__ == "__main__":
    main()
