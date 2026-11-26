"""
GLOBAL ENCHANTMENT DISPEL DIFFICULTY sanitiser (2026-10-15).  AoWEPACK.dll only.

[ench+0x14] of a TGlobalEnchantment is NOT a free field: it is the enchantment's DISPEL DIFFICULTY in percent (set by
every global-enchantment ctor: 175 for the six Masteries, 50 / 20 / 15 / 25 / 100 for the others; streamed as tag 0xF
by TGlobalEnchantment.ReadWrite 0x5577DA1C).  Its only numeric readers are Disjunction's:
    TDisjunctionTE.Validate        0x557EB5A0  @0x557EB619 `fild [ebx+0x14]`  * 0.02 * [disj+0x20] + [disj+0x1C]  (power needed)
    TDisjunctionTE.Process         0x557EB740  @0x557EB767 `fild [eax+0x14]`  * 0.02 * [ebx+0x20]                (dispel roll)
    TDisjunctionSpellCaster.GetMana 0x557EB98C @0x557EB99D `fild [esi+0x14]`  * 0.02 * [ebx+0x18]                (mana cost)
Our global-spell scripts (Golden Age/Black Tide, Steam Power, Drought, Overgrowth/World Healer, Bountiful Harvest,
Blessed Dew/Plague) use [ench+0x14] as their MARKER (= the spell id, 302..391), and Plague additionally packs its
origin hex and infected-city count K into bits 9..31 -> dispelling them needed 1.7-2.2x a Mastery's power, and a Plague
was effectively undispellable (~80 000 000 %), going NEGATIVE (trivially dispelled) once K >= 32.

Fix: the three readers load a SANITISED value instead: v = [ench+0x14]; if v > 255 then v := 175 (the Masteries'
difficulty - every vanilla value is <= 175, every marker is >= 204).  Each site's preceding instruction(s) are folded
into a 5..9-byte window replaced by `call cave` (+ NOPs); the cave replays them, pushes the sanitised dword and
`fild`s it from the stack.  Windows are reloc-free and nothing branches into them.  MANA's window contains its
`test esi,esi / je 0x557EB9B5` (no target enchantment): the cave reproduces it by dropping its return address and
jumping to 0x557EB9B5 (`or eax,-1 / pop esi / pop ebx / ret`).  EFLAGS: fild never set them and no reader depends on
flags across the window (VAL/PRC/MANA are followed by fld/fmul).  No in-image absolute is referenced (no PIC needed).

Zone 0x5582E100..0x5582E200 (zero, reloc-free).  Dry-run default; --apply / --revert / --dis.
Backup <game>\\backup\\AoWEPACK.dll.bak_dispel.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DLL = game_file("AoWEPACK.dll")
BASE, CODE_V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x5582E100, 0x5582E200
MASTERY_DIFF = 175
SITES = {   # name: (va, original bytes)
    "VAL":  (0x557EB617, bytes.fromhex("8bf8db4314")),
    "PRC":  (0x557EB764, bytes.fromhex("8b45f8db4014")),
    "MANA": (0x557EB997, bytes.fromhex("8bf085f67418db4614")),
}
MANA_NONE = 0x557EB9B5
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def build():
    out = bytearray(); where = {}
    def place(name, src):
        while len(out) % 16: out.append(0)
        va = ZONE + len(out); where[name] = va
        out.extend(bytes(ks.asm(src % {"d": MASTERY_DIFF, "none": MANA_NONE}, va)[0]))
    # san: eax = raw difficulty -> eax = sanitised (other regs preserved; flags clobbered - harmless at all 3 sites)
    place("san", """
        cmp eax, 255
        jbe san_ok
        mov eax, %(d)d
    san_ok:
        ret
    """)
    place("val", """
        mov edi, eax
        push eax
        mov eax, dword ptr [ebx+0x14]
        call %(san)#x
        push eax
        fild dword ptr [esp]
        add esp, 4
        pop eax
        ret
    """.replace("%(san)#x", hex(where["san"])))
    place("prc", """
        mov eax, dword ptr [ebp-8]
        push eax
        mov eax, dword ptr [eax+0x14]
        call %(san)#x
        push eax
        fild dword ptr [esp]
        add esp, 4
        pop eax
        ret
    """.replace("%(san)#x", hex(where["san"])))
    place("mana", """
        mov esi, eax
        test esi, esi
        jnz mana_have
        add esp, 4
        jmp %(none)#x
    mana_have:
        push eax
        mov eax, dword ptr [esi+0x14]
        call %(san)#x
        push eax
        fild dword ptr [esp]
        add esp, 4
        pop eax
        ret
    """.replace("%(san)#x", hex(where["san"])))
    return bytes(out), where


CAVE = {"VAL": "val", "PRC": "prc", "MANA": "mana"}


def hook(va, orig, target):
    b = bytearray(b"\xe8" + struct.pack("<i", target - (va + 5)))
    b += b"\x90" * (len(orig) - 5)
    return bytes(b)


def relocs(d):
    pe = struct.unpack_from("<I", d, 0x3C)[0]; opt = struct.unpack_from("<H", d, pe + 20)[0]; nsec = struct.unpack_from("<H", d, pe + 6)[0]
    secs = [struct.unpack_from("<IIII", d, pe + 24 + opt + 40 * k + 8) for k in range(nsec)]
    rrva, rsz = struct.unpack_from("<II", d, pe + 24 + 0x88)
    def r2f(rva):
        for vs, va, rs, ro in secs:
            if va <= rva < va + max(vs, rs): return ro + rva - va
    p = r2f(rrva); end = p + rsz; out = set()
    while p < end:
        page, size = struct.unpack_from("<II", d, p)
        if size < 8: break
        for q in range(p + 8, p + size, 2):
            e = struct.unpack_from("<H", d, q)[0]
            if e >> 12 == 3: out.add(BASE + page + (e & 0xFFF))
        p += size
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true"); ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    d = bytearray(open(DLL, "rb").read())
    zone, where = build(); assert ZONE + len(zone) <= ZONE_END
    rl = relocs(bytes(d))
    bad = [hex(r) for r in rl if ZONE <= r < ZONE_END or any(va <= r < va + len(o) for va, o in SITES.values())]
    states = {}
    for n, (va, orig) in SITES.items():
        live = bytes(d[va - CODE_V2F:va - CODE_V2F + len(orig)]); h = hook(va, orig, where[CAVE[n]])
        states[n] = "vanilla" if live == orig else "ours" if live == h else ("ours(old)" if live[0] == 0xE8 and ZONE <= va + 5 + struct.unpack_from("<i", live, 1)[0] < ZONE_END else "OTHER")
    zl = bytes(d[ZONE - CODE_V2F:ZONE_END - CODE_V2F])
    zstate = "zero" if not any(zl) else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else "DIFFERS"
    print("sites %s | zone %s (%d B: %s) | relocs %s" % (states, zstate, len(zone), ", ".join("%s=%#x" % kv for kv in where.items()), bad or "none"))
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        for i in md.disasm(zone, ZONE): print("   %08X %-18s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad or "OTHER" in states.values(): print("ABORT"); return 1
    if a.revert:
        for n, (va, orig) in SITES.items(): d[va - CODE_V2F:va - CODE_V2F + len(orig)] = orig
        d[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
        open(DLL, "r+b").write(bytes(d)); print("reverted"); return 0
    if all(s == "ours" for s in states.values()) and zstate == "ours": print("already applied"); return 0
    if zstate == "DIFFERS" and not any(s.startswith("ours") for s in states.values()): print("ABORT: zone not free"); return 1
    out = bytearray(d)
    out[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
    out[ZONE - CODE_V2F:ZONE - CODE_V2F + len(zone)] = zone
    for n, (va, orig) in SITES.items(): out[va - CODE_V2F:va - CODE_V2F + len(orig)] = hook(va, orig, where[CAVE[n]])
    print("%d bytes change" % sum(1 for x, y in zip(d, out) if x != y))
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(DLL, ".bak_dispel")
    if not os.path.exists(bak): shutil.copy2(DLL, bak); print("backup ->", bak)
    with open(DLL, "r+b") as f: f.write(bytes(out))
    assert open(DLL, "rb").read() == bytes(out); print("Written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
