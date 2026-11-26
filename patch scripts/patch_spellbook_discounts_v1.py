#!/usr/bin/env python3
r"""
Spellbook shows the caster-discounted research turns and upkeep (AoWx.exe, 2026-09-21).
Companion of patch_caster_research_upkeep_v1 (AoWEPACK helpers h_research 0x55816830 (eax=player, edx=spell)
and h_upkeep 0x558168F0 (eax=hero, edx=spell)).

Spellbook info builder 0x42E8E0 (esi = window, [esi+0x22C] = the hero whose book is open, ebx = spell):
  * casting cost already goes through THero.CastingMana (import slot 0x45DCA4, thunk 0x40277C @0x42EB05);
  * upkeep line: 0x42EC83 `mov edx,[ebx+0x1C] ; mov [ebp-0x20],edx` (6 B) -> cave: edx := h_upkeep(hero, spell);
    ⚠ eax holds the Format string ([ebp-0x14], loaded at 0x42EC80) across the hook -> the cave reloads it after the
    helper call (v1 clobbered it: AV in @LStrLAsg reading FFFFFFF9 = upkeep value used as a string, 2026-09-21);
  * research window 0x42BCB8 reads the remaining points at 0x42BD29 (`mov eax,[eax+0x54] ; mov eax,[eax+0x38]`)
    -> cave: eax := h_remain(ctl) (v2: [ctl+0x38] is raw, the discount is applied on read);
  * TMagicWin (VMT 0x42C150): the mana-distribution/enchantment refresh 0x42D2CC runs on more events than the
    research overview 0x42CDE8 (only PlayerMagicChanged for the current player) -> its entry is hooked to run
    0x42CDE8 first, so the research turns line is rebuilt whenever the tab refreshes (v3 2026-09-21);
  * 0x42D480 (PlayerMagicChanged -> research overview 0x42CDE8) only refreshed when the changed player is the
    current player; the `jne` @0x42D497 is NOPed (v4) so a hero lost during another player's turn also repaints the
    current player's overview (0x42CDE8 always reads the current player's data anyway);
  * research line: 0x42ED93 `mov ecx,[ebx+0x18] ; mov eax,esi` (5 B; esi = TPlayerMagicControl here, edx = net
    power) -> cave: ecx := h_research([ctl+0x10] player, spell); ResearchTurns(ctl, power, ecx) follows.
AoWEPACK is rebased at runtime, so the caves reach the helpers via the CastingMana import slot:
  helper = [0x45DCA4] + (HELPER - 0x557894EC).  Caves in .xbfs 0x60EB80.. (zero-verified).
Backup AoWx.exe.bak_bookdisc (in <game>\backup\).  Dry-run default; --apply; --revert; --dis.
"""
import argparse, os, shutil, struct, sys
from bakpath import game_dir, game_file, bak_path
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

DEFAULT_EXE = game_file(r"AoWx.exe")
BAK = ".bak_bookdisc"
BASE = 0x400000
IMP_CASTINGMANA = 0x45DCA4
CASTINGMANA_LINK = 0x557894EC
H_RESEARCH, H_UPKEEP, H_REMAIN = 0x55816830, 0x558168F0, 0x55816A20
HU, HU_ORIG, HU_RESUME = 0x42EC83, bytes.fromhex("8b531c8955e0"), 0x42EC89
HR, HR_ORIG, HR_RESUME = 0x42ED93, bytes.fromhex("8b4b188bc6"), 0x42ED98
HW, HW_ORIG, HW_RESUME = 0x42BD29, bytes.fromhex("8b40548b4038"), 0x42BD2F   # research window: mov eax,[eax+0x54] ; mov eax,[eax+0x38]
HM, HM_ORIG, HM_RESUME = 0x42D2CC, bytes.fromhex("558bec83c4f45356"), 0x42D2D4   # TMagicWin mana/enchantment refresh entry
CAVE_U, CAVE_R, CAVE_W, CAVE_M, CAVE_END = 0x60EB80, 0x60EBC0, 0x60EBE0, 0x60EC00, 0x60EC40
GATE, GATE_ORIG, GATE_NEW = 0x42D497, bytes.fromhex("7505"), bytes.fromhex("9090")   # TMagicWin PlayerMagicChanged: `jne skip` unless changed player == current
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, addr):
    enc, _ = ks.asm(src, addr)
    return bytes(enc)


def cave_upkeep(va):
    return asm(f"""
        mov ecx, [{IMP_CASTINGMANA:#x}]
        add ecx, {(H_UPKEEP - CASTINGMANA_LINK) & 0xFFFFFFFF:#x}
        mov eax, [esi+0x22C]
        mov edx, ebx
        call ecx
        mov edx, eax
        mov eax, [ebp-0x14]
        mov [ebp-0x20], edx
        jmp {HU_RESUME:#x}
    """, va)


def cave_research(va):
    return asm(f"""
        push edx
        mov ecx, [{IMP_CASTINGMANA:#x}]
        add ecx, {(H_RESEARCH - CASTINGMANA_LINK) & 0xFFFFFFFF:#x}
        mov eax, [esi+0x10]
        mov edx, ebx
        call ecx
        mov ecx, eax
        pop edx
        mov eax, esi
        jmp {HR_RESUME:#x}
    """, va)


def cave_window(va):
    return asm(f"""
        mov eax, [eax+0x54]
        mov ecx, [{IMP_CASTINGMANA:#x}]
        add ecx, {(H_REMAIN - CASTINGMANA_LINK) & 0xFFFFFFFF:#x}
        call ecx
        jmp {HW_RESUME:#x}
    """, va)


def cave_magicwin(va):
    return asm(f"""
        push eax
        call 0x42CDE8
        pop eax
        push ebp
        mov ebp, esp
        add esp, -0xC
        push ebx
        push esi
        jmp {HM_RESUME:#x}
    """, va)


def build():
    a = cave_upkeep(CAVE_U); assert CAVE_U + len(a) <= CAVE_R
    b = cave_research(CAVE_R); assert CAVE_R + len(b) <= CAVE_W
    c = cave_window(CAVE_W); assert CAVE_W + len(c) <= CAVE_M, hex(CAVE_W + len(c))
    m = cave_magicwin(CAVE_M); assert CAVE_M + len(m) <= CAVE_END
    return [(CAVE_U, a, "book-upkeep"), (CAVE_R, b, "book-research"), (CAVE_W, c, "research-window"), (CAVE_M, m, "magicwin-refresh")]


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
    hooks = [("upkeep", HU, HU_ORIG, CAVE_U), ("research", HR, HR_ORIG, CAVE_R), ("window", HW, HW_ORIG, CAVE_W), ("magicwin", HM, HM_ORIG, CAVE_M)]
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
    print(f"target: {exe}")
    states = []
    for name, va, orig, cave in hooks:
        o = va2off(data, va); cur = bytes(data[o:o + len(orig)])
        st = "vanilla" if cur == orig else "ALREADY PATCHED" if cur[0] == 0xE9 and va + 5 + struct.unpack_from("<i", cur, 1)[0] == cave else f"UNKNOWN {cur.hex()}"
        states.append(st); print(f"  {name:9} 0x{va:x}: {st}")
    for va, blob, name in caves:
        print(f"  cave {name:14} {va:#x}..{va + len(blob):#x} ({len(blob)} B)")
    z0, z1 = va2off(data, CAVE_U), va2off(data, CAVE_END)
    zone_zero = all(v == 0 for v in data[z0:z1])
    rl = reloc_hits(data, [(va, va + len(orig)) for _, va, orig, _ in hooks] + [(CAVE_U, CAVE_END)])
    print(f"  cave zone zero: {zone_zero}; relocs: {[hex(v) for v in rl] or 'none'}")
    if not a.apply:
        print("dry run - nothing written (use --apply)"); return
    if rl or any(s.startswith("UNKNOWN") for s in states):
        sys.exit("refusing: relocs or unexpected bytes")
    applied = any(s == "ALREADY PATCHED" for s in states)
    if not applied and not zone_zero:
        sys.exit("cave zone not empty - refusing")
    if not os.path.exists(bak):
        shutil.copy2(exe, bak); print(f"  backup -> {bak}")
    for va, blob, name in caves:
        o = va2off(data, va); data[o:o + len(blob)] = blob
    for name, va, orig, cave in hooks:
        o = va2off(data, va); data[o:o + len(orig)] = jmp_bytes(va, cave, len(orig))
    go = va2off(data, GATE)
    if bytes(data[go:go + 2]) in (GATE_ORIG, GATE_NEW):
        data[go:go + 2] = GATE_NEW
    else:
        sys.exit(f"gate bytes unexpected: {bytes(data[go:go+2]).hex()}")
    with open(exe, "r+b") as f:
        f.seek(0); f.write(data)
    print("applied." if not applied else "re-applied (caves rewritten).")


if __name__ == "__main__":
    main()
