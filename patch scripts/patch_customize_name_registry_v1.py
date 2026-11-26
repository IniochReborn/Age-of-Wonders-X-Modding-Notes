#!/usr/bin/env python3
r"""
Leader customization: the name typed in the customize-leader screen is saved as the player name
(registry General\strings\0) so the next lobby visit already shows it (AoWx.exe, 2026-09-21).

Vanilla plumbing:
  * pre-lobby "player name" dialog: TAoWRegistry.GetString(0) fills the edit (0x4535C2), OK writes it back with
    SetString(0) (0x45395C); the registry object is [[[0x45DF74]]+0x5C].
  * the customize-leader window TLeaderSetupWin: NameEditChange 0x417110 copies the edit text into the leader
    setup data [[win+0x2E4]+0x60]; the finish routine 0x416D9C (last "Next") takes ctl = [win+0x2D8]
    (TCustomizeLeaderControl), pushes [[ctl+0x14]+0x60] (the name) to DirectPlay via 0x41468C when a remote
    session is active (TSetupControl.GetRemote on [[[0x45A454]]+0x48]), then calls ctl.Done (VMT+0x4C) and frees it.
  * TMainForm.FormDestroy 0x453910 re-saves the settings on shutdown, including SetString(0, name-edit text)
    from the pre-lobby dialog's edits [[0x45A598]]+0x90 / +0xC4 (TAOWEdit) -> a bare registry write is undone at
    exit (v1 failure, 2026-09-21).
Patch (v2): 7-byte hook at 0x416DD8 (`mov eax,esi ; mov edx,[eax] ; call [edx+0x4C]`) -> cave: if a remote
(multiplayer) session is active (same GetRemote test as 0x41468C, so single-player leader names never touch the
registry) and the registry object exists -> TAoWRegistry.SetString(reg, 0, name) AND TAOWEdit.SetGText(name) on
both dialog edits (so the shutdown re-save writes the same name) ; then the displaced ctl.Done call ; back to 0x416DDF.  Absolute addresses are fine in the exe (never rebased); the .reloc entry at 0x416DCD lies
outside the hook bytes.  Cave in `.xbfs` 0x60EB00.. (zero-verified).  Backup AoWx.exe.bak_custname (in <game>\backup\).
Dry-run default; --apply; --revert; --dis.
"""
import argparse, os, shutil, struct, sys
from bakpath import game_dir, game_file, bak_path
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

DEFAULT_EXE = game_file(r"AoWx.exe")
BAK = ".bak_custname"
BASE = 0x400000
G_SETUP = 0x45A454            # [[.]] = setup events object; +0x48 setup control (GetRemote), +0x44 DPlay
G_APP = 0x45DF74              # [[.]]+0x5C = TAoWRegistry
GETREMOTE = 0x402F4C          # thunk AoWSetup.TSetupControl.GetRemote(eax) -> al
SETSTRING = 0x401F04          # thunk AoWReg.TAoWRegistry.SetString(eax=reg, edx=id, ecx=string)
G_OPTWIN = 0x45A598           # [[.]]+0x90 / +0xC4 = the pre-lobby name edits (TAOWEdit)
SETGTEXT = 0x40326C           # thunk AoWEdit.TAOWEdit.SetGText(eax=edit, edx=string)
HOOK_VA = 0x416DD8
HOOK_ORIG = bytes.fromhex("8bc68b10ff524c")   # mov eax,esi ; mov edx,[eax] ; call [edx+0x4C]
RESUME = 0x416DDF
CAVE_BASE, CAVE_END = 0x60EB00, 0x60EBA0
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, addr):
    enc, _ = ks.asm(src, addr)
    return bytes(enc)


def cave_main(va):
    return asm(f"""
        push edi
        mov eax, [{G_SETUP:#x}]
        mov eax, [eax]
        test eax, eax
        jz n_done
        mov eax, [eax+0x48]
        test eax, eax
        jz n_done
        call {GETREMOTE:#x}
        test al, al
        jz n_done
        mov edi, [esi+0x14]
        test edi, edi
        jz n_done
        mov edi, [edi+0x60]
        mov eax, [{G_APP:#x}]
        mov eax, [eax]
        test eax, eax
        jz n_edits
        mov eax, [eax+0x5C]
        test eax, eax
        jz n_edits
        mov ecx, edi
        xor edx, edx
        call {SETSTRING:#x}
    n_edits:
        mov eax, [{G_OPTWIN:#x}]
        mov eax, [eax]
        test eax, eax
        jz n_done
        push eax
        mov eax, [eax+0x90]
        test eax, eax
        jz n_edit2
        mov edx, edi
        call {SETGTEXT:#x}
    n_edit2:
        pop eax
        mov eax, [eax+0xC4]
        test eax, eax
        jz n_done
        mov edx, edi
        call {SETGTEXT:#x}
    n_done:
        pop edi
        mov eax, esi
        mov edx, [eax]
        call [edx+0x4C]
        jmp {RESUME:#x}
    """, va)


def build():
    blob = cave_main(CAVE_BASE)
    assert CAVE_BASE + len(blob) <= CAVE_END
    return [(CAVE_BASE, blob, "custname-registry")]


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
    ap.add_argument("exe", nargs="?", default=DEFAULT_EXE)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    exe = a.exe
    bak = bak_path(exe, BAK, create=a.apply)
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
        shutil.copy2(bak, exe); print(f"reverted {exe} from {bak}"); return
    data = bytearray(open(exe, "rb").read())
    ho = va2off(data, HOOK_VA); cur = bytes(data[ho:ho + len(HOOK_ORIG)])
    applied = cur[0] == 0xE9; vanilla = cur == HOOK_ORIG
    print(f"target: {exe}\n  hook 0x{HOOK_VA:x}: {'ALREADY PATCHED' if applied else 'vanilla' if vanilla else 'UNKNOWN BYTES ' + cur.hex()}")
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
        shutil.copy2(exe, bak); print(f"  backup -> {bak}")
    for va, blob, name in caves:
        o = va2off(data, va); data[o:o + len(blob)] = blob
    data[ho:ho + len(HOOK_ORIG)] = jmp_bytes(HOOK_VA, CAVE_BASE, len(HOOK_ORIG))
    with open(exe, "r+b") as f:
        f.seek(0); f.write(data)
    print("applied.")


if __name__ == "__main__":
    main()
