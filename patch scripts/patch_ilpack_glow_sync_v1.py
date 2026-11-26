#!/usr/bin/env python3
r"""
Ilpack.dpl: a chained light layer that follows its sprite's frame (2026-10-13, Phoenix animated glow).

Unit gfx slots are TImageSequence chains: PRIMARY (shadow / light) -> sub (the sprite).  Both unit draw routines walk
the chain and ask every element for its frame with TImageSequence.GetFrameIndex 0x552186EC (eax = seq, edx = tick,
ecx = seed); a kind-4 sequence keeps ITS OWN counter (+0x34, stepped every f18+1 DISTINCT ticks it is queried on,
+0x2C = last tick, +0x30 = countdown) and returns frames[(counter + seed) mod n].  Two chained kind-4 sequences
therefore drift apart: the sprite is queried by more code paths than the light, so it sees more ticks (in-game
10/13: "looked good at first, slowly fell out of sync").
Patch: the kind-4 entry of GetFrameIndex (0x55218733, `cmp esi,[ebx+0x2c] / je`) jumps to a cave that, when the
sequence's layer byte f8 ([seq+8]) is 0x7F (our animated-light marker) and it has a sub ([seq+0xC]), calls
GetFrameIndex on the SUB (same tick/seed - the sub's own later query in the same tick does not re-advance it),
finds that image id's position in the sub's frame list and returns OUR frame at the same position; anything else
replays the two instructions.  ecx = result -> the function's epilogue 0x5521889F.  Vanilla sequences all have f8 0.
Cave 0x5521C540 (Ilpack CODE zero tail 0x5521C527..0x5522C600, no relocs; rel32 only = PIC).
Backup <game>\backup\Ilpack.dpl.bak_glowsync.  Surgical --revert.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DEFAULT_DLL = game_file("Ilpack.dpl")
BAK_SUFFIX = ".bak_glowsync"
BASE, CODE_V2F = 0x55200000, 0x55200C00
ZONE, ZONE_END = 0x5521C540, 0x5521C640
HOOK = 0x55218733
ORIG = bytes.fromhex("3b732c7420")           # cmp esi,[ebx+0x2c] / je 0x55218758
RESUME, JE_TARGET, EPILOGUE, GETFRAMEINDEX = 0x55218738, 0x55218758, 0x5521889F, 0x552186EC
MARKER = 0x7F
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def build():
    code = ks.asm("""
        cmp byte ptr [ebx+8], %(marker)d
        jne vanilla
        mov eax, [ebx+0xc]
        test eax, eax
        jz vanilla
        push ebx
        push esi
        push edi
        mov edx, esi
        mov ecx, edi
        call %(gfi)#x
        pop edi
        pop esi
        pop ebx
        mov ecx, eax
        cmp eax, -1
        je done
        push esi
        push edi
        mov edx, [ebx+0xc]
        mov edx, [edx+0x1c]
        mov esi, [edx+8]
        mov edi, [edx+4]
        xor ecx, ecx
    find:
        cmp ecx, esi
        jae notfound
        cmp [edi+ecx*4], eax
        je found
        inc ecx
        jmp find
    found:
        mov edx, [ebx+0x1c]
        cmp ecx, [edx+8]
        jae notfound
        mov edx, [edx+4]
        mov ecx, [edx+ecx*4]
        pop edi
        pop esi
        jmp done
    notfound:
        pop edi
        pop esi
        or ecx, -1
    done:
        jmp %(epi)#x
    vanilla:
        cmp esi, [ebx+0x2c]
        je %(je)#x
        jmp %(resume)#x
    """ % {"marker": MARKER, "gfi": GETFRAMEINDEX, "epi": EPILOGUE, "je": JE_TARGET, "resume": RESUME}, ZONE)[0]
    return bytes(code)


def reloc_set(d):
    pe = struct.unpack_from("<I", d, 0x3C)[0]; opt = struct.unpack_from("<H", d, pe + 20)[0]; nsec = struct.unpack_from("<H", d, pe + 6)[0]
    secs = [struct.unpack_from("<IIII", d, pe + 24 + opt + 40 * k + 8) for k in range(nsec)]
    rrva, rsz = struct.unpack_from("<II", d, pe + 24 + 0x88)
    def r2f(rva):
        for vs, va, rs, ro in secs:
            if va <= rva < va + max(vs, rs): return ro + rva - va
    p, end, out = r2f(rrva), r2f(rrva) + rsz, set()
    while p < end:
        page, size = struct.unpack_from("<II", d, p)
        if size < 8: break
        for q in range(p + 8, p + size, 2):
            e = struct.unpack_from("<H", d, q)[0]
            if e >> 12 == 3: out.add(BASE + page + (e & 0xFFF))
        p += size
    return out


def write_inplace(path, data):
    with open(path, "r+b") as f:
        f.seek(0); f.write(data); f.truncate(len(data))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dll", default=DEFAULT_DLL)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    d = open(a.dll, "rb").read()
    zone = build(); assert ZONE + len(zone) <= ZONE_END
    hook = b"\xe9" + struct.pack("<i", ZONE - (HOOK + 5))
    live = d[HOOK - CODE_V2F:HOOK - CODE_V2F + 5]; zl = d[ZONE - CODE_V2F:ZONE_END - CODE_V2F]
    rl = reloc_set(d); bad = [r for r in rl if ZONE <= r < ZONE_END or HOOK <= r < HOOK + 5]
    state = "vanilla" if live == ORIG else "ours" if live == hook else "OTHER"
    zstate = "zero" if not any(zl) else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else "DIFFERS"
    print("hook %s | zone %s (%d B) | relocs %s" % (state, zstate, len(zone), bad or "none"))
    if bad or state == "OTHER": print("ABORT"); return 1
    if a.dis:
        import capstone
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(zone, ZONE): print("   %08X  %-16s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if a.revert:
        out = bytearray(d); out[HOOK - CODE_V2F:HOOK - CODE_V2F + 5] = ORIG; out[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
        write_inplace(a.dll, bytes(out)); print("reverted"); return 0
    if state == "ours" and zstate == "ours": print("already applied"); return 0
    out = bytearray(d); out[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
    out[ZONE - CODE_V2F:ZONE - CODE_V2F + len(zone)] = zone; out[HOOK - CODE_V2F:HOOK - CODE_V2F + 5] = hook
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(a.dll, BAK_SUFFIX)
    if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    write_inplace(a.dll, bytes(out)); assert open(a.dll, "rb").read() == bytes(out); print("Written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
