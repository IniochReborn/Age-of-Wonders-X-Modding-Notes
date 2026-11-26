#!/usr/bin/env python3
r"""
Tactical breath attacks: each strike's obstruction line goes to ITS OWN damage hex and stops there
(AoWTCPCK.dll, 2026-09-21).  See memory aowx-breath-attacks for the full RE.

Vanilla (CombatTE.TCAbRangedTE.NextStrike 0x40D290, category-5 case 0x40D345): a breath is 12 strikes, one per
cone hex (BreathHN).  Strike s builds its block line with MakeRangedPath from the shooter to a point at the
cone's full depth (ring-4 centre "aim" hex) rotated by (f*6-30) degrees, f = s (s>9: 19-s) -- the animation's
spray sweep -- while the hex it damages is BreathHN[BreathHit[s]], which is NOT where that line points (the
adjacent straight-ahead hex is tested with the -30 degree line, the far-centre hex with +12).  Any block on
the line (walls/gates/obstacles/rock/water; units never block breaths) zeroes the strike (0x40F06F).  Result:
in a 1-hex corridor the side walls eat most strikes, and obstacles BEYOND a target hex cancel hits on it.

Patch: 5-byte hook at 0x40D5F1 (`push 0x32 ; mov eax,[ebp-4]`, start of the MakeRangedPath argument pushes)
-> cave: for s < 12 recompute the strike's damage hex exactly like 0x40D671..0x40D72A does after the call
(dir = dHXtoDir(shooter, target) ; HN = BreathHN[BreathDir[dir-1]*12 + BreathHit[s] - 12] ; HNtoHX) but into
the "target hex" slots [ebp-0x48]/[ebp-0x4C] that the call is about to push, and zero the pixel offsets
[ebp-0x3C]/[ebp-0x40] (the fan endpoint's offset from the aim hex).  So the line = shooter -> damage hex, ending
there; MakeRangedPath never blocks on the shooter's or the target's own hex.  Everything after the call is
untouched (the damage hex is recomputed to the same value).  s >= 12 -> vanilla values.  The fan angle maths
still runs but its result is no longer used.  PIC via call/pop delta for the three table pointers
0x469404/0x46940C/0x469414 (TCPCK is always rebased); thunk calls are rel32.  All machines execute the same
token code -> multiplayer-safe (Random call count changes identically everywhere).
Cave 0x43AB40.. (zero-verified).  Backup AoWTCPCK.dll.bak_breathline (in <game>\backup\).
Dry-run default; --apply; --revert; --dis.
"""
import argparse, os, shutil, struct, sys
from bakpath import game_dir, game_file, bak_path
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

DEFAULT_DLL = game_file(r"AoWTCPCK.dll")
BAK = ".bak_breathline"
BASE = 0x400000
P_BREATHDIR, P_BREATHHN, P_BREATHHIT = 0x469404, 0x46940C, 0x469414   # runtime pointers to the tables
HX2DIR = 0x4022B4       # thunk dHXtoDir(eax=x1, edx=y1, ecx=x2, [y2]) -> dir 1..6
HN2HX = 0x4022AC        # thunk HNtoHX(eax=x, edx=y, ecx=hn, [&outY], [&outX])
HOOK_VA = 0x40D5F1
HOOK_ORIG = bytes.fromhex("6a328b45fc")   # push 0x32 ; mov eax,[ebp-4]
RESUME = 0x40D5F6
CAVE_BASE, CAVE_END = 0x43AB40, 0x43AC40
STRIKES = 12
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, addr):
    enc, _ = ks.asm(src, addr)
    return bytes(enc)


def cave_main(va):
    pre = """
        push ebx
        push esi
        push edi
    """
    body = f"""
        mov eax, [ebp-4]
        mov esi, [eax+0x34]
        cmp esi, {STRIKES}
        jae b_done
        mov dword ptr [ebp-0x3C], 0
        mov dword ptr [ebp-0x40], 0
        mov eax, [ebp-4]
        movzx eax, word ptr [eax+0x22]
        push eax
        mov eax, [ebp-4]
        mov eax, [eax+0x10]
        mov eax, [eax+0x60]
        mov edx, [eax]
        call [edx+0x78]
        movsx eax, al
        push eax
        mov eax, [ebp-4]
        mov eax, [eax+0x10]
        mov eax, [eax+0x60]
        mov edx, [eax]
        call [edx+0x74]
        movsx eax, al
        mov edx, [ebp-4]
        movzx ecx, word ptr [edx+0x20]
        pop edx
        call {HX2DIR:#x}
        cmp eax, 1
        jl b_done
        cmp eax, 6
        jg b_done
        mov edx, [ebx+{P_BREATHDIR:#x}]
        mov eax, [edx+eax*4-4]
        imul eax, eax, 12
        mov edx, [ebx+{P_BREATHHIT:#x}]
        add eax, [edx+esi*4]
        sub eax, 12
        cmp eax, 0
        jl b_done
        cmp eax, 72
        jge b_done
        mov edx, [ebx+{P_BREATHHN:#x}]
        mov ecx, [edx+eax*4]
        lea eax, [ebp-0x48]
        push eax
        lea eax, [ebp-0x4C]
        push eax
        push ecx
        mov eax, [ebp-4]
        mov eax, [eax+0x10]
        mov eax, [eax+0x60]
        mov edx, [eax]
        call [edx+0x78]
        movsx eax, al
        push eax
        mov eax, [ebp-4]
        mov eax, [eax+0x10]
        mov eax, [eax+0x60]
        mov edx, [eax]
        call [edx+0x74]
        movsx eax, al
        pop edx
        pop ecx
        call {HN2HX:#x}
    b_done:
        pop edi
        pop esi
        pop ebx
        push 0x32
        mov eax, [ebp-4]
        jmp {RESUME:#x}
    """
    p = asm(pre, va)
    call_at = va + len(p); nxt = call_at + 5
    p += asm(f"call {nxt:#x}", call_at)
    p += asm(f"pop ebx\nsub ebx, {nxt:#x}\n" + body, nxt)
    return p


def build():
    blob = cave_main(CAVE_BASE)
    assert CAVE_BASE + len(blob) <= CAVE_END, hex(CAVE_BASE + len(blob))
    return [(CAVE_BASE, blob, "breath-line")]


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
