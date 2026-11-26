#!/usr/bin/env python3
r"""
Tactical AI: a "walk to a firing spot" must clearly beat the unit's best shot NOW (AoWTCPCK.dll, 2026-09-20).

Observed (ranged trace, 2026-09-20): a Shaman with a 448-point shot at a full-health Cavalier walked
instead, because a next-turn shot at a wounded Cavalier scored 896 x 65 % = 582.  The same mechanism
made a leader spend a turn moving to do nothing.  Rule (user): a speculative walk may only outrank the
unit's best available shoot-now move when it is at least WALK_MARGIN_PCT of that shot; otherwise it is
capped to one below the shot.

Hook 0x41A3D3 in TCAI phase 4 (8 B `test eax,eax ; jle 0x41A46D`) -- AFTER the AoO-awareness pass
(0x41A3C0) and the group-bonus loop, BEFORE the descending sort: pass over [cai+0x14]; for every type-5
move (walk to firing spot) find the max value among type-3 moves (shoot now) of the same unit
([move+0x14] unit HS); if such a shot exists (> 0) and walk*100 < shot*WALK_MARGIN_PCT then
walk := min(walk, shot-1).  Move record: +4 type, +0xC value, +0x14 unit HS.  eax (= count-1) is
preserved and the displaced `test eax,eax ; jle` is replayed.  No absolute references.
Cave 0x43A500.. (zero-verified).  Backup AoWTCPCK.dll.bak_walkmargin (in <game>\backup\).
Dry-run default; --apply; --revert; --dis.
"""
import argparse, os, shutil, struct, sys
from bakpath import game_dir, game_file, bak_path
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

DEFAULT_DLL = game_file(r"AoWTCPCK.dll")
BAK = ".bak_walkmargin"
BASE = 0x400000
WALK_MARGIN_PCT = 175       # a walk must be >= this % of the unit's best shoot-now value to outrank it
HOOK_VA = 0x41A3D3
HOOK_ORIG = bytes.fromhex("85c00f8e92000000")   # test eax,eax ; jle 0x41A46D
RESUME = 0x41A3DB
JLE_TARGET = 0x41A46D
CAVE_BASE, CAVE_END = 0x43A500, 0x43A600
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, addr):
    enc, _ = ks.asm(src, addr)
    return bytes(enc)


def cave_main(va):
    # frame: [esp]=i, [esp+4]=j, [esp+8]=best shot value (-1 = none)
    return asm(f"""
        push eax
        push ebx
        push ecx
        push edx
        push esi
        push edi
        sub esp, 12
        mov ebx, [ebp-4]
        mov ebx, [ebx+0x14]
        mov dword ptr [esp], 0
    w_outer:
        mov eax, [esp]
        cmp eax, [ebx+8]
        jge w_done
        mov edx, [ebx+4]
        mov esi, [edx+eax*4]
        inc dword ptr [esp]
        test esi, esi
        jz w_outer
        cmp byte ptr [esi+4], 5
        jne w_outer
        mov edi, [esi+0x14]
        mov dword ptr [esp+8], -1
        mov dword ptr [esp+4], 0
    w_inner:
        mov eax, [esp+4]
        cmp eax, [ebx+8]
        jge w_apply
        mov edx, [ebx+4]
        mov ecx, [edx+eax*4]
        inc dword ptr [esp+4]
        test ecx, ecx
        jz w_inner
        cmp byte ptr [ecx+4], 3
        jne w_inner
        cmp [ecx+0x14], edi
        jne w_inner
        mov eax, [ecx+0xC]
        cmp eax, [esp+8]
        jle w_inner
        mov [esp+8], eax
        jmp w_inner
    w_apply:
        mov ecx, [esp+8]
        cmp ecx, 0
        jle w_outer
        mov eax, [esi+0xC]
        imul eax, eax, 0x64
        mov edx, ecx
        imul edx, edx, {WALK_MARGIN_PCT}
        cmp eax, edx
        jge w_outer
        dec ecx
        cmp [esi+0xC], ecx
        jle w_outer
        mov [esi+0xC], ecx
        jmp w_outer
    w_done:
        add esp, 12
        pop edi
        pop esi
        pop edx
        pop ecx
        pop ebx
        pop eax
        test eax, eax
        jle {JLE_TARGET:#x}
        jmp {RESUME:#x}
    """, va)


def build():
    blob = cave_main(CAVE_BASE)
    assert CAVE_BASE + len(blob) <= CAVE_END
    return [(CAVE_BASE, blob, "walk-margin")]


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
    print(f"  cave zone zero: {zone_zero}; relocs: {[hex(v) for v in rl] or 'none'}; margin {WALK_MARGIN_PCT} %")
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
