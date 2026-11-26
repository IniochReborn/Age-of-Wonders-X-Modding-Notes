#!/usr/bin/env python3
r"""
AoWx multilevel abilities take their per-level skill cost from Release\Ability.pfs (AoWEPACK.dll, 2026-09-22).

Our TMultiLevelAbility objects (Holy/Unholy Champion 0x92/0x93 via patch_champion_leveled_ranged_v1, Evoker/
Conjurer/Enchanter/Ritualist 0xAC-0xAF via patch_caster_levels_v1) get a cost list [+0x2C] filled with a constant
at registration (TIntegerList.Put idx 1..cap), while TAbility.ReadWrite (0x5574F07C) later loads the pfs cost
(tag 6) into [+0x14].  TMultiLevelAbility.ExpandCost/GetSkillPoints read the LIST, TAbility.ExpandCost reads
[+0x14] -> the two UIs disagreed after the user changed the pfs costs (editor kept showing the registration
constants).  Hook: `mov ecx,7` @0x5574F0AA (right after the tag-6 rwInt) -> cave: if [ability+0xC] id is one of
ours and 1 <= cap [+0x28] <= 5, Put(list, i, [+0x14]) for i = 1..cap; replay `mov ecx,7`; resume 0x5574F0AF.
ReadWrite also runs when the editor SAVES Ability.pfs (same value, harmless).  Vanilla multilevel abilities are
not touched.  Cave 0x55816F80 (zero-verified).  Backup AoWEPACK.dll.bak_mlcost (in <game>\backup\).
Dry-run default; --apply; --revert; --dis.
"""
import argparse, os, shutil, struct, sys
from bakpath import game_file, bak_path
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

DLL = game_file(r"AoWEPACK.dll"); BAK = ".bak_mlcost"; BASE = 0x55700000
HOOK, HOOK_ORIG, RESUME = 0x5574F0AA, bytes.fromhex("b907000000"), 0x5574F0AF
INTLIST_PUT = 0x55702EB4
IDS = [0x92, 0x93, 0xAC, 0xAD, 0xAE, 0xAF]
CAVE, CAVE_END = 0x55816F80, 0x55817000
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, addr):
    src = chr(10).join(l.split(';')[0] for l in src.splitlines())
    enc, _ = ks.asm(src, addr); return bytes(enc)


def cave(va):
    checks = "".join(f"        cmp eax, {i:#x}\n        je c_ours\n" for i in IDS)
    return asm(f"""
        mov eax, [ebx + 0xC]
{checks}
        jmp c_out
    c_ours:
        mov ecx, [ebx + 0x28]
        cmp ecx, 1
        jb c_out
        cmp ecx, 5
        ja c_out
        push esi
        push edi
        mov esi, 1
        mov edi, ecx
    c_loop:
        mov eax, [ebx + 0x2C]
        mov edx, esi
        mov ecx, [ebx + 0x14]
        call {INTLIST_PUT:#x}
        inc esi
        cmp esi, edi
        jbe c_loop
        pop edi
        pop esi
    c_out:
        mov ecx, 7
        jmp {RESUME:#x}
    """, va)


def va2off(d, va):
    e = struct.unpack_from("<I", d, 0x3C)[0]; n = struct.unpack_from("<H", d, e + 6)[0]; sec = e + 24 + struct.unpack_from("<H", d, e + 20)[0]
    for i in range(n):
        vsz, rva, rsz, roff = struct.unpack_from("<IIII", d, sec + 40 * i + 8)
        if rva <= va - BASE < rva + max(vsz, rsz):
            return roff + (va - BASE - rva)
    raise ValueError(hex(va))


def reloc_hits(d, ranges):
    e = struct.unpack_from("<I", d, 0x3C)[0]; dd_rva, dd_sz = struct.unpack_from("<II", d, e + 24 + 0x88)
    off = va2off(d, BASE + dd_rva); end = off + dd_sz; hits = []
    while off + 8 <= end:
        page, bsz = struct.unpack_from("<II", d, off)
        if bsz < 8:
            break
        for i in range((bsz - 8) // 2):
            ent = struct.unpack_from("<H", d, off + 8 + 2 * i)[0]; va = BASE + page + (ent & 0xFFF)
            if ent >> 12 and any(lo <= va < hi for lo, hi in ranges):
                hits.append(hex(va))
        off += bsz
    return hits


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true"); ap.add_argument("--dis", action="store_true")
    a = ap.parse_args(); bak = bak_path(DLL, BAK, create=a.apply)
    if a.revert:
        if not os.path.exists(bak):
            sys.exit(f"no backup {bak}")
        shutil.copy2(bak, DLL); print(f"reverted {DLL} from {bak}"); return
    blob = cave(CAVE); assert CAVE + len(blob) <= CAVE_END, len(blob)
    if a.dis:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
        for ins in Cs(CS_ARCH_X86, CS_MODE_32).disasm(blob, CAVE):
            print(f"{ins.address:08X}  {ins.mnemonic:<7} {ins.op_str}")
    d = bytearray(open(DLL, "rb").read()); ho = va2off(d, HOOK); cur = bytes(d[ho:ho + 5])
    st = "vanilla" if cur == HOOK_ORIG else "ALREADY PATCHED" if cur[0] == 0xE9 and HOOK + 5 + struct.unpack_from("<i", cur, 1)[0] == CAVE else f"UNKNOWN {cur.hex()}"
    zone_zero = all(v == 0 for v in d[va2off(d, CAVE):va2off(d, CAVE_END)]); rl = reloc_hits(d, [(HOOK, HOOK + 5), (CAVE, CAVE_END)])
    print(f"target: {DLL}\n  hook 0x{HOOK:x}: {st}\n  cave {CAVE:#x}..{CAVE + len(blob):#x} ({len(blob)} B); zone zero {zone_zero}; relocs {rl or 'none'}; ids {[hex(i) for i in IDS]}")
    if not a.apply:
        print("dry run - nothing written (use --apply)"); return
    if rl or st.startswith("UNKNOWN") or (st == "vanilla" and not zone_zero):
        sys.exit("refusing")
    if not os.path.exists(bak):
        shutil.copy2(DLL, bak); print(f"  backup -> {bak}")
    d[va2off(d, CAVE):va2off(d, CAVE) + len(blob)] = blob
    d[ho:ho + 5] = b"\xe9" + struct.pack("<i", CAVE - (HOOK + 5))
    with open(DLL, "r+b") as f:
        f.seek(0); f.write(d)
    print("applied.")


if __name__ == "__main__":
    main()
