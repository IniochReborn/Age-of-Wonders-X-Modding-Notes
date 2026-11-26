#!/usr/bin/env python3
r"""
Event tab: no auto-jump to the newest event while the mouse cursor is over the event list (AoWx.exe, 2026-09-21).

The logbook window ([0x45A4FC]) refreshes on TheMapLogbookChanged (0x44F97C) via 0x423304: it clears and refills
its TAOWListBox ([win+0x54], items [+0x114]) from the player's TEventLogbook ([player+0xD8]) and then scrolls to
the last entry with `call TAOWListBox.SetListOff(list, count-1)` @0x42336A (thunk 0x403664, IAT slot 0x45EC94).
aowInt.dpl's mouse-wheel patch keeps g_hover @0x5983E100 = the TAOWListBox under the cursor (set in
TAOWListBox.CheckMouseMove's inside branch, cleared at every WinManager mouse-move sweep).
Patch: hook the 5-byte call -> cave: &g_hover = [IAT SetListOff] + (0x5983E100 - 0x598168F4) (rebase-proof);
if g_hover == the event list, skip the scroll; else call SetListOff as before.  Once the cursor leaves the list
the next event (or turn start) jumps to the bottom again, as vanilla.
Cave in .xbfs 0x60EC20.. (zero-verified).  Backup AoWx.exe.bak_evhover (in <game>\backup\).
Dry-run default; --apply; --revert; --dis.
"""
import argparse, os, shutil, struct, sys
from bakpath import game_dir, game_file, bak_path
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

DEFAULT_EXE = game_file(r"AoWx.exe")
BAK = ".bak_evhover"
BASE = 0x400000
IAT_SETLISTOFF = 0x45EC94
SETLISTOFF_LINK = 0x598168F4
G_HOVER = 0x5983E100
SETLISTOFF_THUNK = 0x403664
HOOK_VA, HOOK_ORIG, RESUME = 0x42336A, bytes.fromhex("e8f502feff"), 0x42336F
CAVE, CAVE_END = 0x60EC20, 0x60EC60
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, addr):
    enc, _ = ks.asm(src, addr)
    return bytes(enc)


def cave_main(va):
    return asm(f"""
        mov ecx, [{IAT_SETLISTOFF:#x}]
        add ecx, {(G_HOVER - SETLISTOFF_LINK) & 0xFFFFFFFF:#x}
        cmp [ecx], eax
        je h_skip
        call {SETLISTOFF_THUNK:#x}
    h_skip:
        jmp {RESUME:#x}
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("exe", nargs="?", default=DEFAULT_EXE)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    exe = a.exe
    bak = bak_path(exe, BAK, create=a.apply)
    blob = cave_main(CAVE); assert CAVE + len(blob) <= CAVE_END
    if a.dis:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
        for ins in Cs(CS_ARCH_X86, CS_MODE_32).disasm(blob, CAVE):
            print(f"{ins.address:08X}  {ins.mnemonic:<7} {ins.op_str}")
    if a.revert:
        if not os.path.exists(bak):
            sys.exit(f"no backup {bak}")
        shutil.copy2(bak, exe); print(f"reverted {exe} from {bak}"); return
    data = bytearray(open(exe, "rb").read())
    ho = va2off(data, HOOK_VA); cur = bytes(data[ho:ho + 5])
    tgt = HOOK_VA + 5 + struct.unpack_from("<i", cur, 1)[0] if cur[0] in (0xE8, 0xE9) else None
    st = "vanilla" if cur == HOOK_ORIG else "ALREADY PATCHED" if cur[0] == 0xE9 and tgt == CAVE else f"UNKNOWN {cur.hex()}"
    zone_zero = all(v == 0 for v in data[va2off(data, CAVE):va2off(data, CAVE_END)])
    rl = reloc_hits(data, [(HOOK_VA, HOOK_VA + 5), (CAVE, CAVE_END)])
    print(f"target: {exe}\n  hook 0x{HOOK_VA:x}: {st}\n  cave {CAVE:#x}..{CAVE + len(blob):#x} ({len(blob)} B); zone zero {zone_zero}; relocs {[hex(v) for v in rl] or 'none'}")
    if not a.apply:
        print("dry run - nothing written (use --apply)"); return
    if rl or st.startswith("UNKNOWN"):
        sys.exit("refusing")
    if st == "vanilla" and not zone_zero:
        sys.exit("cave zone not empty - refusing")
    if not os.path.exists(bak):
        shutil.copy2(exe, bak); print(f"  backup -> {bak}")
    data[va2off(data, CAVE):va2off(data, CAVE) + len(blob)] = blob
    data[ho:ho + 5] = b"\xe9" + struct.pack("<i", CAVE - (HOOK_VA + 5))
    with open(exe, "r+b") as f:
        f.seek(0); f.write(data)
    print("applied.")


if __name__ == "__main__":
    main()
