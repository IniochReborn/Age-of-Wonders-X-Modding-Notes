"""
Two player-reported bugs, 2026-11-26.  AoWTCPCK.dll + AoWEPACK.dll.

A. "Sandstorm + Hurl Skull exploit" (aim a spell, then use a ranged ability -> many skulls / arrows, spell animations,
   Hellfire -> lock-up).
   The ranged tactical effect (TCPCK class cell 0x40795C, Execute 0x40B2F8) is built by ONE factory, 0x40F4B0, called
   from 0x4238B5 with the selected unit HS's action [hs+0x34] (ability id; 0x34 = Spell Casting) and [hs+0x38] (the
   last SPELL picked for that unit).  [hs+0x38] is never cleared, so an archery / Hurl Skull / breath effect carries
   the id of whatever spell was last aimed (or cast) in [te+0x18].  Vanilla only reads [te+0x18] behind
   `cmp [te+0x14],0x34`; many of our spell caves test the spell id alone (Sandstorm strike count, Hellfire gate, hail
   aliases, Suffocate / Flashfreeze drivers ...) and so ran on top of the ranged ability.
   Fix: the factory's store `mov eax,[ebp+8] / mov edx,[ebp-0xC] / mov [edx+0x18],eax` @0x40F52D -> cave 0x455000:
   the spell id is stored only when the ability [ebp+0xC] is 0x34, else 0.  The effect is created on the acting
   machine and streamed (tag 0x1F), so every machine sees the clean id; phase 0 copies it back to [hs+0x38].

B. Rejuvenate (204) / Wither (205) turned Sky into land (surface "covered up", islands in the Firmament).
   Their rule (patch_terrain_spells_v1 caves 0x55862459 / 0x5586246C mapping, 0x5586249E target test) was "anything
   but Water 0 / Ice 6 / Lava 9".  Sky 0xE and Chasm 0xB are now excluded too (same as the Path of Life / Decay
   guards of patch_sky_chasm_engine_v1).  Three 5-byte jumps into cave 0x558BB000 (rel32 only, no absolutes).

Dry-run default; --apply; --revert (restores the exact site bytes, zeroes the caves).  Backups .bak_bugfix1126.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

BAK_SUFFIX = ".bak_bugfix1126"
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, va): return bytes(ks.asm(src, va)[0])
def jmp(at, to): return b"\xe9" + struct.pack("<i", to - (at + 5))


# ---- A: AoWTCPCK
TC_CAVE, TC_ROOM = 0x455000, 0x40
TC_SITE, TC_ORIG = 0x40F52D, bytes.fromhex("8b4508" "8b55f4" "894218")
TC_CAVE_NEW = asm("""
    mov eax, [ebp+8]
    cmp dword ptr [ebp+0xc], 0x34
    je keep
    xor eax, eax
keep:
    mov edx, [ebp-0xc]
    mov [edx+0x18], eax
    jmp 0x40F536
""", TC_CAVE)
TC_SITE_NEW = jmp(TC_SITE, TC_CAVE) + b"\x90" * 4

# ---- B: AoWEPACK
EP_CAVE, EP_ROOM = 0x558BB000, 0x100
OUT, NO, YES = 0x5586247D, 0x558624AD, 0x558624B0
SKIP = "".join("    cmp al, %d\n    je %%(t)s\n" % t for t in (6, 9, 0x0B, 0x0E))


def ep_build():
    a_va = EP_CAVE
    a = asm("    mov al, [ecx]\n    test al, al\n    jz 0x%x\n" % OUT + SKIP % {"t": "0x%x" % OUT}
            + "    mov byte ptr [ecx], 1\n    jmp 0x%x\n" % OUT, a_va)
    b_va = a_va + ((len(a) + 15) & ~15)
    b = asm("    mov al, [ecx]\n    test al, al\n    jz 0x%x\n" % OUT + SKIP % {"t": "0x%x" % OUT}
            + "    mov byte ptr [ecx], 5\n    jmp 0x%x\n" % OUT, b_va)
    c_va = b_va + ((len(b) + 15) & ~15)
    c = asm("    mov al, [esi+0x14]\n    test al, al\n    jz 0x%x\n" % NO + SKIP % {"t": "0x%x" % NO}
            + "    jmp 0x%x\n" % YES, c_va)
    cave = a + bytes(b_va - a_va - len(a)) + b + bytes(c_va - b_va - len(b)) + c
    assert len(cave) <= EP_ROOM
    sites = [(0x55862459, bytes.fromhex("8a0184c074"), jmp(0x55862459, a_va)),      # Rejuvenate mapping
             (0x5586246C, bytes.fromhex("8a0184c074"), jmp(0x5586246C, b_va)),      # Wither mapping
             (0x5586249E, bytes.fromhex("8a461484c0"), jmp(0x5586249E, c_va))]      # shared target test
    return cave, sites


EP_CAVE_NEW, EP_SITES = ep_build()

TARGETS = [
    dict(name="AoWTCPCK.dll", v2f=0x400C00, cave=TC_CAVE, room=TC_ROOM, cave_new=TC_CAVE_NEW,
         sites=[(TC_SITE, TC_ORIG, TC_SITE_NEW)]),
    dict(name="AoWEPACK.dll", v2f=0x55700C00, cave=EP_CAVE, room=EP_ROOM, cave_new=EP_CAVE_NEW, sites=EP_SITES),
]


def reloc_hits(path, ranges):
    import pefile
    pe = pefile.PE(path, fast_load=True)
    pe.parse_data_directories([pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_BASERELOC"]])
    ib = pe.OPTIONAL_HEADER.ImageBase
    out = []
    for blk in getattr(pe, "DIRECTORY_ENTRY_BASERELOC", []):
        for e in blk.entries:
            if e.type and any(lo - 3 <= ib + e.rva < hi for lo, hi in ranges): out.append(hex(ib + e.rva))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    a = ap.parse_args()
    plans = []
    for t in TARGETS:
        path = game_file(t["name"]); d = bytearray(open(path, "rb").read()); v2f = t["v2f"]
        g = lambda va, n: bytes(d[va - v2f:va - v2f + n])
        cave = g(t["cave"], t["room"]); new = t["cave_new"] + bytes(t["room"] - len(t["cave_new"]))
        st = []
        for va, orig, hook in t["sites"]:
            cur = g(va, len(orig))
            st.append("vanilla" if cur == orig else "ours" if cur == hook else "OTHER")
        cst = "zero" if not any(cave) else "ours" if cave == new else "FOREIGN"
        state = ("vanilla" if set(st) == {"vanilla"} and cst == "zero" else
                 "ours" if set(st) == {"ours"} and cst == "ours" else "MIXED")
        print("%s: sites %s | cave %#x %s -> %s" % (t["name"], st, t["cave"], cst, state))
        if state == "MIXED": print("ABORT"); return 1
        bad = reloc_hits(path, [(va, va + len(o)) for va, o, _ in t["sites"]] + [(t["cave"], t["cave"] + t["room"])])
        if bad: print("ABORT: relocs in range", bad); return 1
        writes = []
        if a.revert and state == "ours":
            writes = [(va, o) for va, o, _ in t["sites"]] + [(t["cave"], bytes(t["room"]))]
        elif not a.revert and state == "vanilla":
            writes = [(t["cave"], new)] + [(va, h) for va, _, h in t["sites"]]
        plans.append((path, v2f, writes))
    if not a.apply and not a.revert:
        print("Dry run OK (%d writes) - rerun with --apply (or --revert)." % sum(len(w) for _, _, w in plans)); return 0
    for path, v2f, writes in plans:
        if not writes: print(os.path.basename(path), "- nothing to do"); continue
        bak = bak_path(path, BAK_SUFFIX)
        if not a.revert and not os.path.exists(bak): shutil.copy2(path, bak); print("backup ->", bak)
        with open(path, "r+b") as f:
            for va, b in writes: f.seek(va - v2f); f.write(b)
        print(os.path.basename(path), "reverted" if a.revert else "written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
