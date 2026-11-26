#!/usr/bin/env python3
r"""
Tactical AI: make the hero/leader SELF-heal move executable (AoWTCPCK.dll, 2026-09-20).

Diagnosis (live capture with ai_state_probe.py --watch, memory aowx-ai-hero-idle): the healing patch
(patch_heal_ai_tcpck_v1, cave F) proposes a type-1 touch move for a wounded hero/leader with
destination = its OWN hex.  TCAI phase 5's touch executor (0x41ABD0) walks a path to the destination
and touches the unit at its end; when the computed path has a single node (dest == own hex) it drops
the move at 0x41ACE4 without executing anything and without setting the "executed" flag [ebp-0x31].
Because the self-heal scores high and also bumps the attack counter [cai+0x2C], the leader is gated
out of the cycle and, once no other move remains, the dropped heal ends the whole AI turn: hero and
leader stand still every turn while wounded.

The engine itself CAN touch without moving: TTacticalCombatUnitHS.AbTouchMoveTC 0x423744 handles a
one-node path for a friendly ability by calling AbRangedTC(hs, x, y) 0x423860 on that hex (but it
returns 0 in that branch, so it cannot be used for the success flag).

Patch: 10-byte hook at 0x41ACE4 (`cmp [path+8],1 ; jle drop`) -> cave: path count > 1 -> vanilla;
count == 1 and ability == Healing (0x2F) and dest == the unit's own hex and the unit still has
>= SELF_HEAL_MIN_MP movement points (the proposal side, heal-patch cave F, has no MP check) -> AbRangedTC(hs, x, y) ->
[ebp-0x31] := result -> continue at the normal post-execution tail 0x41ADD0.  Anything else (count 0,
other abilities) -> vanilla drop 0x41AE17.  No absolute data references -> no PIC needed.
Cave 0x43A200.. (zero-verified).  Backup AoWTCPCK.dll.bak_selfheal (in <game>\backup\).
Dry-run default; --apply; --revert; --dis.
"""
import argparse, os, shutil, struct, sys
from bakpath import game_dir, game_file, bak_path
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

DEFAULT_DLL = game_file(r"AoWTCPCK.dll")
BAK = ".bak_selfheal"
BASE = 0x400000

ABRANGEDTC = 0x423860         # TTacticalCombatUnitHS.AbRangedTC(eax=hs, dx=x, cx=y) -> al
HEALING = 0x2F
SELF_HEAL_MIN_MP = 1        # 2026-09-20: a self-heal needs movement points left, like any other action (0 = no check)
HOOK_VA = 0x41ACE4
HOOK_ORIG = bytes.fromhex("837808010f8e29010000")   # cmp dword [eax+8],1 ; jle 0x41AE17
VANILLA_GO = 0x41ACEE          # path count > 1: continue vanilla executor
VANILLA_DROP = 0x41AE17        # free settings, delete move, next
POST_EXEC = 0x41ADD0           # tail after AbTouchMoveTC stored [ebp-0x31]
CAVE_BASE, CAVE_END = 0x43A200, 0x43A300

ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, addr):
    enc, _ = ks.asm(src, addr)
    return bytes(enc)


def cave_main(va):
    return asm(f"""
        mov eax, [ebp-0x30]
        mov eax, [eax+0x68]
        cmp dword ptr [eax+8], 1
        jg s_vanilla
        jl s_drop
        mov edx, [ebp-0x20]
        movsx eax, word ptr [edx+6]
        cmp eax, {HEALING:#x}
        jne s_drop
        mov ecx, [edx+0x14]
        mov ecx, [ecx+4]
        movzx eax, byte ptr [ecx+0x10]
        cmp ax, word ptr [edx+0x1C]
        jne s_drop
        movzx eax, byte ptr [ecx+0x11]
        cmp ax, word ptr [edx+0x1E]
        jne s_drop
        mov ecx, [edx+0x14]
        mov ecx, [ecx+0x1C]
        cmp dword ptr [ecx+0x5C], {SELF_HEAL_MIN_MP}
        jl s_drop
        mov eax, [edx+0x14]
        mov cx, word ptr [edx+0x1E]
        mov dx, word ptr [edx+0x1C]
        call {ABRANGEDTC:#x}
        mov [ebp-0x31], al
        jmp {POST_EXEC:#x}
    s_vanilla:
        jmp {VANILLA_GO:#x}
    s_drop:
        jmp {VANILLA_DROP:#x}
    """, va)


def build():
    blob = cave_main(CAVE_BASE)
    assert CAVE_BASE + len(blob) <= CAVE_END
    return [(CAVE_BASE, blob, "selfheal-exec")]


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
    opt = e_lfanew + 24
    dd_rva, dd_sz = struct.unpack_from("<II", pe_bytes, opt + 0x88)
    if not dd_sz:
        return []
    off = va2off(pe_bytes, BASE + dd_rva); end = off + dd_sz; hits = []
    while off + 8 <= end:
        page, bsz = struct.unpack_from("<II", pe_bytes, off)
        if bsz < 8:
            break
        for i in range((bsz - 8) // 2):
            e = struct.unpack_from("<H", pe_bytes, off + 8 + 2 * i)[0]
            if e >> 12 == 0:
                continue
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
    ho = va2off(data, HOOK_VA)
    cur = bytes(data[ho:ho + len(HOOK_ORIG)])
    applied = cur[0] == 0xE9; vanilla = cur == HOOK_ORIG
    print(f"target: {dll}\n  hook 0x{HOOK_VA:x}: {'ALREADY PATCHED' if applied else 'vanilla' if vanilla else 'UNKNOWN BYTES ' + cur.hex()}")
    for va, blob, name in caves:
        print(f"  cave {name} {va:#x}..{va + len(blob):#x} ({len(blob)} B)")
    z0, z1 = va2off(data, CAVE_BASE), va2off(data, CAVE_END)
    zone_zero = all(b == 0 for b in data[z0:z1])
    rl = reloc_hits(data, [(HOOK_VA, HOOK_VA + len(HOOK_ORIG)), (CAVE_BASE, CAVE_END)])
    print(f"  cave zone zero: {zone_zero}\n  reloc entries in hook/cave ranges: {[hex(v) for v in rl] or 'none'}")
    if not a.apply:
        print("dry run - nothing written (use --apply)"); return
    if rl:
        sys.exit("relocation entries intersect the patch - refusing")
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
