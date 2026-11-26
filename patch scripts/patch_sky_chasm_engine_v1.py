#!/usr/bin/env python3
r"""
Sky (terrain 0xE, ex-Coast) and Chasm (0xB, ex-uWasteland): flyer-only terrains - engine half (AoWEPACK.dll,
2026-10-31; port of BXL's Ziggurat feature, his LIVE dll = newer than his July scripts).

User: copy Ziggurat's cross-level terrain incl. Sky/Chasm (editor brushes = patch_devx_terrain_palette_v1).
Chasm fly cost 4 (user ruling = Ziggurat's value).

1. Movement (DATA, 8 base tables 0x558E84FC + t*0x100, row = terrain, 16 overlay columns): rows 0xB / 0xE := Ziggurat's
   live rows - Fly/Float table 04 in all 16 columns, every other table FF except the bridge column (col 6 = 3) for
   walkers / forestry / cave / mountain / fire; swim + tunnel FF.  (Startup combines these into MovePointTables, so
   units, AI and path preview follow.)  Our old row 0xB (underground-fly-6 layer) is overwritten.
2. Coast water filter TAoWHexagon.TerrainChanged 0x5579A962 75 -> EB: 0xE no longer turns the hexagon into water.
3. Cliff edges / transitions (Ziggurat v3): hook UpdateTransition 0x5579AA92 (movsx ebp,al; cmp ebp,edi) -> block B
   (Sky/Chasm vs water/ice/cave-water/land pick transition ids 0xB0/0xB3/0xE0..0xE9 from his bigger HEXTRANS.ILB;
   otherwise both count as cave water).  Water hexagons: UpdateTransitions 0x5579AE30 -> block A+0 (Sky/Chasm
   neighbour -> variant 0xA0/0xC0 = his WATERHEX/ICEHEX additions), ShowDynamic call 0x5579B19B -> block A+0x300
   (no wave animation on such edges), TAoWHexagon VMT slot 0x5579A278 (THexagon.Show) -> block A+0x40 (draws the
   land-side cliff rim next to Sky/Chasm; PIC data table at +0x240).  Blocks are copied byte-for-byte from
   Ziggurat's AoWEPACK.dpl (A = 0x5581A000..0x5581A330, B = 0x55812000..0x558120B9), rel32 exits re-targeted.
   Art: copy_sky_chasm_ilbs (in this script, --apply) replaces HEXTRANS/WATERHEX/ICEHEX/PAD1-4/H_La/H_ugWa with
   Ziggurat's add-only supersets (ours were vanilla, hash-checked).
4. Spell/ability guards - never turn Sky/Chasm into something else / never target them:
     Death Storm 0x557CD304, Divine Storm 0x557CD6DC   (whole-function caves, BXL)
     Flood 0x557F1474, Raise Terrain ValidTargetMapF 0x557A35CB + ValidTargetSelectionMapF 0x557A3623 (ours added)
     CHAINED in front of our own caves (they stay untouched):
       Ice Storm 0x557CCEF0 -> frost cave 0x55816000;  Path of Life 0x557801A4 -> 0x558624C0 (+6);
       Path of Decay 0x557801C4 -> 0x558624E0 (+6);  Path of Sand 0x5580F3C6 -> 0x558625B0.
   ⚠ re-running patch_frost_terrain_v1 / patch_terrain_spells_v1 / path-of-sand afterwards would unlink the guards.
Zone AoWEPACK 0x55850800..0x55851000 ('SKC1'); PIC (rel32 only, block A uses call/pop).  Dry-run default;
--apply / --revert.  Backup AoWEPACK.dll.bak_skychasm (+ each ILB .bak_skychasm).
"""
import hashlib, os, shutil, struct, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_dir, game_file

DLL, BASE = game_file("AoWEPACK.dll"), 0x55700000
ZIG_DIR = r"C:\Users\<user>\Desktop\AoW Ziggurat\Ziggurat"
ZIG = os.path.join(ZIG_DIR, "AoWEPACK.dpl")
ZONE, ZONE_END = 0x55850800, 0x55851000
MAGIC = b"SKC1"
A_OLD, A_LEN, A_NEW = 0x5581A000, 0x330, ZONE + 0x10
B_OLD, B_LEN, B_NEW = 0x55812000, 0xB9, ZONE + 0x350
G_BASE = ZONE + 0x410
A_CODE = [(0x5581A000, 0x5581A02A), (0x5581A040, 0x5581A20E), (0x5581A300, 0x5581A325)]
B_CODE = [(0x55812000, 0x558120B9)]

MOVE = 0x558E84FC
ROWS_OURS = {(0, 0xB): "04ffffff0403ff0603ff04ff08ffffff", (1, 0xE): "04ffffff04ffff0404ff04ff08ffffff",
             (2, 0xB): "06ffffff0604ff0604ff06ff0606ffff", (2, 0xE): "04ffffff04ff040404ff04ff0404ffff",
             (3, 0xB): "04ffffff0403ff0603ff04ff08ffffff", (4, 0xB): "04ffffff0403ff0603ff04ff08ffffff",
             (5, 0xB): "04ffffff0403ff0403ff04ff08ffffff", (6, 0xB): "ff" * 16}
BRIDGE = "ffffffffffff03ffffffffffffffffff"
ROWS_NEW = {(0, 0xB): BRIDGE, (1, 0xE): "ff" * 16, (2, 0xB): "04" * 16, (2, 0xE): "04" * 16,
            (3, 0xB): BRIDGE, (4, 0xB): BRIDGE, (5, 0xB): BRIDGE, (6, 0xB): BRIDGE}

ILBS = [r"Images\HEXTRANS.ILB", r"Images\Waterhex.ILB", r"Images\IceHex.ILB", r"Images\PAD1.ILB",
        r"Images\PAD2.ILB", r"Images\PAD3.ILB", r"Images\PAD4.ILB", r"Images\TCombat\Base_hex\H_La.ILB",
        r"Images\TCombat\Base_hex\H_ugWa.ILB"]
ILB_VANILLA = {"HEXTRANS.ILB": "628a49dd", "WATERHEX.ILB": "a6f806fd", "ICEHEX.ILB": "276c70f1",
               "PAD1.ILB": "9d0f2639", "PAD2.ILB": "6288c6f3", "PAD3.ILB": "9644bee5", "PAD4.ILB": "09556083",
               "H_LA.ILB": "20a4240a", "H_UGWA.ILB": "b69bb451"}
ILB_ZIG = {"HEXTRANS.ILB": "4fab4529", "WATERHEX.ILB": "6f07c63b", "ICEHEX.ILB": "a5d73d21",
           "PAD1.ILB": "0a2ad115", "PAD2.ILB": "04052886", "PAD3.ILB": "d45a962c", "PAD4.ILB": "b4eadfeb",
           "H_LA.ILB": "27e4a89f", "H_UGWA.ILB": "b5c8afd0"}


def relocate(blob, old, new, code_ranges, ext_ok):
    """copy a self-contained cave block; rel32 branches leaving the block are re-targeted"""
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    md = Cs(CS_ARCH_X86, CS_MODE_32)
    out = bytearray(blob)
    lo, hi = old, old + len(blob)
    exits = []
    for s, e in code_ranges:
        for ins in md.disasm(blob[s - old:e - old], s):
            b = ins.bytes
            if b[0] in (0xE8, 0xE9) and len(b) == 5:
                at = 1
            elif b[0] == 0x0F and 0x80 <= b[1] <= 0x8F and len(b) == 6:
                at = 2
            else:
                for op in ("0x5581", "0x5570", "0x5571", "0x5572", "0x5573", "0x5574", "0x5575", "0x5576",
                           "0x5577", "0x5578", "0x5579", "0x5580", "0x5582", "0x558e", "0x558f"):
                    assert op not in ins.op_str or ins.mnemonic.startswith("j") or ins.mnemonic == "call", \
                        ("absolute operand", hex(ins.address), ins.mnemonic, ins.op_str)
                continue
            tgt = ins.address + len(b) + struct.unpack_from("<i", b, at)[0]
            if lo <= tgt < hi:
                continue
            assert tgt in ext_ok, ("unexpected exit", hex(ins.address), hex(tgt))
            pos = ins.address - old + at
            struct.pack_into("<i", out, pos, tgt - (new + ins.address - old + len(b)))
            exits.append(tgt)
    return bytes(out), exits


GUARDS = [  # name, site, original bytes (ours), hook length, asm (assembled at its own address)
    ("death", 0x557CD304, "558bec0fbe", 5, """
        push ebp
        mov  ebp, esp
        movsx eax, byte ptr [ecx]
        test ax, ax
        je   sk
        cmp  ax, 6
        je   sk
        cmp  ax, 0xB
        je   sk
        cmp  ax, 0xE
        je   sk
        mov  byte ptr [ecx], 5
    sk:
        pop  ebp
        ret  4"""),
    ("divine", 0x557CD6DC, "558bec0fbe", 5, """
        push ebp
        mov  ebp, esp
        movsx eax, byte ptr [ecx]
        cmp  ax, 6
        je   sk
        test ax, ax
        je   sk
        cmp  ax, 0xB
        je   sk
        cmp  ax, 0xE
        je   sk
        mov  byte ptr [ecx], 1
    sk:
        pop  ebp
        ret  4"""),
    ("ice", 0x557CCEF0, None, 5, """
        cmp  ax, 0xB
        je   sk
        cmp  ax, 0xE
        je   sk
        jmp  0x55816000
    sk:
        jmp  0x557CCF39"""),
    ("flood", 0x557F1474, "8a431484c0", 5, """
        mov  al, byte ptr [ebx + 0x14]
        cmp  al, 0xB
        je   sk
        cmp  al, 0xE
        je   sk
        test al, al
        jmp  0x557F1479
    sk:
        jmp  0x557F1506"""),
    ("raise_map", 0x557A35CB, "8a431484c0", 5, """
        mov  al, byte ptr [ebx + 0x14]
        cmp  al, 0xB
        je   sk
        cmp  al, 0xE
        je   sk
        test al, al
        jmp  0x557A35D0
    sk:
        jmp  0x557A35F6"""),
    ("raise_sel", 0x557A3623, "8a461484c0", 5, """
        mov  al, byte ptr [esi + 0x14]
        cmp  al, 0xB
        je   sk
        cmp  al, 0xE
        je   sk
        test al, al
        jmp  0x557A3628
    sk:
        jmp  0x557A364E"""),
    ("pathlife", 0x557801A4, None, 6, """
        push ebp
        mov  ebp, esp
        movsx eax, byte ptr [ecx]
        cmp  ax, 0xB
        je   sk
        cmp  ax, 0xE
        je   sk
        jmp  0x558624C6
    sk:
        jmp  0x557801BE"""),
    ("pathdecay", 0x557801C4, None, 6, """
        push ebp
        mov  ebp, esp
        movsx eax, byte ptr [ecx]
        cmp  ax, 0xB
        je   sk
        cmp  ax, 0xE
        je   sk
        jmp  0x558624E6
    sk:
        jmp  0x557801DE"""),
    ("pathsand", 0x5580F3C6, None, 6, """
        cmp  ax, 0xB
        je   sk
        cmp  ax, 0xE
        je   sk
        jmp  0x558625B0
    sk:
        jmp  0x5580F3DA"""),
]
# chained sites: their current bytes = jmp to our cave (+nop for 6-byte hooks)
CHAIN_TGT = {"ice": 0x55816000, "pathlife": 0x558624C0, "pathdecay": 0x558624E0, "pathsand": 0x558625B0}
CHAIN_CHECK = {0x558624C0: "5589e50fbe01", 0x558624E0: "5589e50fbe01", 0x55816000: "3c09", 0x558625B0: "6683f806"}


def jmp(site, tgt, n):
    return b"\xe9" + struct.pack("<i", tgt - (site + 5)) + b"\x90" * (n - 5)


def build(zig):
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    import pefile
    zpe = pefile.PE(data=zig, fast_load=True)
    zg = lambda va, n: zpe.get_data(va - BASE, n)  # noqa: E731
    a_blob, b_blob = zg(A_OLD, A_LEN), zg(B_OLD, B_LEN)
    assert hashlib.md5(a_blob).hexdigest()[:8] == "%s" % hashlib.md5(a_blob).hexdigest()[:8]
    A, ax = relocate(a_blob, A_OLD, A_NEW, A_CODE,
                     {0x5579AE38, 0x5579AE7B, 0x55799450, 0x557026B4, 0x55702934, 0x557020DC, 0x5579A178})
    B, bx = relocate(b_blob, B_OLD, B_NEW, B_CODE, {0x5579AC88, 0x5579AA97})
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    z = bytearray(ZONE_END - ZONE)
    z[0:4] = MAGIC
    z[A_NEW - ZONE:A_NEW - ZONE + len(A)] = A
    z[B_NEW - ZONE:B_NEW - ZONE + len(B)] = B
    p = G_BASE
    gaddr = {}
    for name, site, orig, n, src in GUARDS:
        code = bytes(ks.asm(src, p)[0])
        gaddr[name] = p
        z[p - ZONE:p - ZONE + len(code)] = code
        p = (p + len(code) + 0xF) & ~0xF
    assert p <= ZONE_END, hex(p)
    return bytes(z), gaddr


def ilb_state(gd):
    st = []
    for rel in ILBS:
        p = os.path.join(gd, rel)
        h = hashlib.md5(open(p, "rb").read()).hexdigest()[:8]
        k = os.path.basename(rel).upper()
        st.append("vanilla" if h == ILB_VANILLA[k] else "ours" if h == ILB_ZIG[k] else "OTHER:" + k)
    return st


def main():
    import pefile
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    d = open(DLL, "rb").read()
    pe = pefile.PE(data=d)
    off = lambda va: pe.get_offset_from_rva(va - BASE)  # noqa: E731
    zone, gaddr = build(open(ZIG, "rb").read())
    P = []                                                   # (va, original, new, label)
    for (t, r), new in ROWS_NEW.items():
        P.append((MOVE + t * 0x100 + r * 16, bytes.fromhex(ROWS_OURS[(t, r)]), bytes.fromhex(new), "move t%d r%X" % (t, r)))
    P.append((0x5579A962, b"\x75", b"\xeb", "coast filter"))
    P.append((0x5579AA92, bytes.fromhex("0fbee83bef"), jmp(0x5579AA92, B_NEW, 5), "transition hook"))
    P.append((0x5579AE30, bytes.fromhex("0fbe47146683f803"), jmp(0x5579AE30, A_NEW, 8), "water UT hook"))
    P.append((0x5579A278, struct.pack("<I", 0x55799450), struct.pack("<I", A_NEW + 0x40), "hexagon Show slot"))
    P.append((0x5579B19B, struct.pack("<i", 0x5579A178 - 0x5579B19F),
              struct.pack("<i", A_NEW + 0x300 - 0x5579B19F), "ShowDynamic call"))
    for name, site, orig, n, src in GUARDS:
        if orig is None:
            ob = jmp(site, CHAIN_TGT[name], n)
            ct = CHAIN_TGT[name]
            chk = bytes.fromhex(CHAIN_CHECK[ct])
            assert d[off(ct):off(ct) + len(chk)] == chk, ("our chained cave changed", name, hex(ct))
        else:
            ob = bytes.fromhex(orig) + b""
        P.append((site, ob[:n] if orig is None else ob, jmp(site, gaddr[name], n if orig is None else 5), "guard " + name))
    P.append((ZONE, bytes(len(zone)), zone, "zone"))
    rl = {BASE + e.rva for blk in getattr(pe, "DIRECTORY_ENTRY_BASERELOC", []) for e in blk.entries if e.type == 3}
    bad = [hex(r) for r in rl if any(s - 3 <= r < s + len(o) for s, o, _, lab in P if not lab.startswith("hexagon"))]
    sts = []
    for s, o, n, lab in P:
        c = d[off(s):off(s) + len(o)]
        sts.append("vanilla" if c == o else "ours" if c == n else "OTHER")
        if sts[-1] == "OTHER":
            print("  OTHER at %s %#x: %s" % (lab, s, c.hex()))
    gd = game_dir()
    ist = ilb_state(gd)
    print("%d sites: %s | relocs %s | ILBs %s | zone %#x..%#x (guards end %#x)"
          % (len(P), {k: sts.count(k) for k in set(sts)}, bad or "none", {k: ist.count(k) for k in set(ist)},
             ZONE, ZONE_END, max(gaddr.values())))
    if "OTHER" in sts or bad or len(set(sts)) != 1 or any(s.startswith("OTHER") for s in ist):
        print("ABORT"); return 1
    want = "vanilla" if revert else "ours"
    if sts[0] == want and set(ist) == {want}:
        print("already %s" % ("reverted" if revert else "applied")); return 0
    if not apply and not revert:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    r = subprocess.run(["tasklist"], capture_output=True, text=True).stdout
    if "AoWx.exe" in r or "AoWDevX.exe" in r:
        print("game/editor running - close it first"); return 1
    bak = bak_path(DLL, ".bak_skychasm")
    if not revert and not os.path.exists(bak):
        shutil.copy2(DLL, bak); print("backup ->", bak)
    with open(DLL, "r+b") as f:
        for s, o, n, lab in reversed(P):
            f.seek(off(s)); f.write(o if revert else n)
    d2 = open(DLL, "rb").read()
    assert all(d2[off(s):off(s) + len(o)] == (o if revert else n) for s, o, n, lab in P)
    for rel in ILBS:
        dst = os.path.join(gd, rel)
        b = bak_path(dst, ".bak_skychasm")
        if revert:
            if os.path.exists(b):
                shutil.copy2(b, dst)
        else:
            if not os.path.exists(b):
                shutil.copy2(dst, b)
            shutil.copy2(os.path.join(ZIG_DIR, rel), dst)
    ist = ilb_state(gd)
    assert set(ist) == {"vanilla" if revert else "ours"}, ist
    print("reverted" if revert else "written and verified (dll + %d ILBs)" % len(ILBS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
