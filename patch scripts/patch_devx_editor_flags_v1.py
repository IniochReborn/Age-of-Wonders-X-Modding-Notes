#!/usr/bin/env python3
r"""
AoWDevX.exe: allow several editor instances + expose an "asg loaded" flag (2026-09-21).
Companion of patch_editor_indicator_v1.py (AoWx.exe multiplayer "editor open" lamp / chat line).

1. Single-instance guard: startup creates the named file mapping "AOWED" (CreateFileMappingA @0x42EDEF) and, when
   GetLastError == ERROR_ALREADY_EXISTS (0xB7), jumps to the "already running" exit (`je 0x42EF96` @0x42EE04).
   The `je` is NOPed: the mapping is still created (that is the flag the game polls), but a second editor starts.
2. THSMEdit.LoadHSM(eax=self, edx=filename) stores the name at [self+0x1E4]; its import thunk (0x402E50) is
   redirected to a cave that calls the real function and, when the loaded file's extension is .asg
   (case-insensitive), creates one more named mapping "AOWEDASG<nnn>" (nnn = 001, 002, ... per load, capped 999,
   handles never closed) - the game counts them, so every re-load of the next autosave is reported.
   v2 2026-09-21: v1 held a single "AOWEDASG" flag (cleared by THSMEdit.Close), which a cheater could keep set
   from before the game started; the Close thunk is no longer hooked.
Caves + handle global in the free tail of the RWX section .xprn (0x4E9650..; zero-verified).  The two thunk
operands carry .reloc entries (0x402E52/0x402E5A) which are neutralised (type 3->0).
⚠ patch_devx_prune_unused_v2.py rebuilds .xprn from .bak_prune: re-run this script after it.
Backup AoWDevX.exe.bak_edflags (in <game>\backup\).  Dry-run default; --apply; --revert; --dis.
"""
import argparse, os, shutil, struct, sys
from bakpath import game_dir, game_file, bak_path
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

DEFAULT_EXE = game_file(r"AoWDevX.exe")
BAK = ".bak_edflags"
BASE = 0x400000
SLOT_LOADHSM, SLOT_CLOSE = 0x43335C, 0x433358
T_CREATEMAP, T_CLOSEHANDLE = 0x4013B8, 0x4013B0
JE_VA, JE_ORIG = 0x42EE04, bytes.fromhex("0f848c010000")
TH_LOAD, TH_LOAD_ORIG = 0x402E50, bytes.fromhex("ff255c334300")
TH_CLOSE, TH_CLOSE_ORIG = 0x402E58, bytes.fromhex("ff2558334300")
G_CNT = 0x4E9650
D_NAME = 0x4E9658                # "AOWEDASG000\0"
CAVE, CAVE_END = 0x4E9670, 0x4E9700
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, addr):
    src = chr(10).join(l.split(';')[0] for l in src.splitlines())
    enc, _ = ks.asm(src, addr)
    return bytes(enc)


def code(va):
    return asm(f"""
    cave_load:
        push esi
        mov esi, eax
        call dword ptr [{SLOT_LOADHSM:#x}]
        test al, al
        jz l_out
        push eax
        mov edx, [esi + 0x1E4]
        test edx, edx
        jz l_pop
        mov ecx, [edx - 4]
        cmp ecx, 4
        jb l_pop
        mov edx, [edx + ecx - 4]
        or edx, 0x20202000
        cmp edx, 0x6773612E
        jne l_pop
        mov ecx, [{G_CNT:#x}]
        cmp ecx, 999
        jae l_pop
        inc ecx
        mov [{G_CNT:#x}], ecx
        mov eax, ecx
        xor edx, edx
        mov ecx, 100
        div ecx
        add al, '0'
        mov [{D_NAME + 8:#x}], al
        mov eax, edx
        xor edx, edx
        mov ecx, 10
        div ecx
        add al, '0'
        mov [{D_NAME + 9:#x}], al
        add dl, '0'
        mov [{D_NAME + 10:#x}], dl
        push {D_NAME:#x}
        push 0x20
        push 0
        push 2
        push 0
        push -1
        call {T_CREATEMAP:#x}
    l_pop:
        pop eax
    l_out:
        pop esi
        ret
    """, va)


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


def reloc_entries(pe_bytes, ranges):
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
            eo = off + 8 + 2 * i; e = struct.unpack_from("<H", pe_bytes, eo)[0]
            va = BASE + page + (e & 0xFFF)
            if any(lo <= va < hi for lo, hi in ranges):
                hits.append((eo, va, e >> 12))
        off += bsz
    return hits


def jmp_bytes(src, dst, ln):
    return b"\xe9" + struct.pack("<i", dst - (src + 5)) + b"\x90" * (ln - 5)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("exe", nargs="?", default=DEFAULT_EXE)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    exe = a.exe; bak = bak_path(exe, BAK, create=a.apply)
    if a.revert:
        if not os.path.exists(bak):
            sys.exit(f"no backup {bak}")
        shutil.copy2(bak, exe); print(f"reverted {exe} from {bak}"); return
    c = code(CAVE); assert CAVE + len(c) <= CAVE_END, len(c)
    assert c[:5] == bytes.fromhex("5689c6ff15")
    E_LOAD = CAVE
    if a.dis:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
        for ins in Cs(CS_ARCH_X86, CS_MODE_32).disasm(c, CAVE):
            print(f"{ins.address:08X}  {ins.mnemonic:<7} {ins.op_str}")
    data = bytearray(open(exe, "rb").read())
    if a.apply and os.path.exists(bak):
        data = bytearray(open(bak, "rb").read()); print(f"  rebuilding from {bak}")
    sites = [(va2off(data, JE_VA), JE_ORIG, b"\x90" * 6, "single-instance je -> NOP"),
             (va2off(data, TH_LOAD), TH_LOAD_ORIG, jmp_bytes(TH_LOAD, E_LOAD, 6), "LoadHSM thunk -> cave_load")]
    print(f"target: {exe}\n  cave {CAVE:#x}..{CAVE + len(c):#x} ({len(c)} B); G_CNT {G_CNT:#x}")
    states = []
    for off, old, new, desc in sites:
        cur = bytes(data[off:off + len(old)])
        st = "vanilla" if cur == old else "PATCHED" if cur == new else f"UNKNOWN {cur.hex()}"
        states.append(st); print(f"  {desc}: {st}")
    zo = va2off(data, G_CNT); zone = bytes(data[zo:zo + (CAVE_END - G_CNT)])
    zone_zero = all(b == 0 for b in zone)
    rl = reloc_entries(data, [(JE_VA, JE_VA + 6), (TH_LOAD, TH_LOAD + 6), (G_CNT, CAVE_END)])
    print(f"  cave zone zero: {zone_zero}; relocs: {[(hex(va), t) for _, va, t in rl]} (thunk operands expected, neutralised)")
    if not a.apply:
        print("dry run - nothing written (use --apply)"); return
    if any(s.startswith("UNKNOWN") for s in states):
        sys.exit("refusing: unexpected bytes")
    applied = all(s == "PATCHED" for s in states)
    if not applied and not zone_zero:
        sys.exit("cave zone not empty - refusing")
    if not os.path.exists(bak):
        shutil.copy2(exe, bak); print(f"  backup -> {bak}")
    data[zo:zo + (CAVE_END - G_CNT)] = bytes(CAVE_END - G_CNT)
    data[va2off(data, D_NAME):va2off(data, D_NAME) + 12] = b"AOWEDASG000\0"
    data[va2off(data, CAVE):va2off(data, CAVE) + len(c)] = c
    for off, old, new, desc in sites:
        data[off:off + len(new)] = new
    for eo, va, t in rl:
        if t == 3 and va == TH_LOAD + 2:
            struct.pack_into("<H", data, eo, struct.unpack_from("<H", data, eo)[0] & 0x0FFF); print(f"  reloc @{va:#x} neutralised")
    with open(exe, "r+b") as f:
        f.seek(0); f.write(data)
    print("applied." if not applied else "re-applied.")


if __name__ == "__main__":
    main()
