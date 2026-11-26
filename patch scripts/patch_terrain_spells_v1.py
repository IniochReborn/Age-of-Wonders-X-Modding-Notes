#!/usr/bin/env python3
r"""
AoWEPACK.dll: per-spell terrain rules for the TRejuvenate clones - Rejuvenate (204) and Wither (205) (2026-10-12).

Background.  Vanilla Rejuvenate (id 0x29, TRejuvenate, cell 0x5579D4D4 / Create 0x5579F560, TE TRejuvenateTE) was
turned into "Scorch Terrain" long ago: Spells.pfs record 51 (Fire, tier 2, cost 5, research 30, icon 154, desc
"Sears a large area, desiccating the terrain.") + ResStr.mld row Rejuvenate -> "Scorch Terrain" + two mod caves:
  * 0x5580C000 = the per-hex mapping (callback stub @0x5579F3E4 `push ebp / call 0x5580C000 / pop ebp / ret 4`,
    ecx = &terrain byte): 1 Grass->4 Steppe, 3 Snow->1 Grass, 4 Steppe->2 Desert, 5 Wasteland->2 Desert,
    6 Ice->0 Water, 0xC Dirt->4 Steppe.
  * 0x5580C0C0 = the valid-target set, called from both TRejuvenate target predicates (slots +0xB0 @0x5579F630 and
    +0xB4 @0x5579F608: `call base check; call 0x5580C0C0` with ebx = spell, esi = field; the cave first `je`s on the
    base check's flags, then accepts field terrain [esi+0x14] in {1,3,4,5,6,0xC}).
The user wants the vanilla Rejuvenate back (Life, tier 1, cost 5, research 30) and a Death twin, Wither (tier 1,
cost 6, research 40) that makes wasteland.  patch_dual_sphere_spells_v1.py clones TRejuvenate into ids 204/205
(record data, name, sphere/tier/cost/research, icon, FX); THIS patch makes the shared class behave per spell:

  A. TRejuvenateTE +0x54 (the execute, 0x5579F3F8, 7-B prologue `53 56 57 8B F2 8B D8`) -> cave_exec stores the TE's
     spell id [te+0x10] in G_TSPELL (DATA slack dword) before anything else runs; the ForEach-hex callback below runs
     inside this routine, so the global is valid for it.
  B. the callback stub's `call 0x5580C000` @0x5579F3E5 -> cave_map (v2, user: "same terrain as Path of Life / Path
     of Decay" = TAbstractUnit.PathOfLifeTerrainChange 0x557801A4 / PathOfDecayTerrainChange 0x557801C4: any terrain
     except 0 Water and 6 Ice, surface only, -> 1 Grass / 5 Wasteland): id 204 -> not 0/6 -> 1; id 205 -> not 0/6
     -> 5; any other id -> jmp 0x5580C000 (Scorch unchanged).  (The level gate lives in the target check.)
  C. both `call 0x5580C0C0` sites (0x5579F617, 0x5579F63F) -> cave_valid: replay the `je reject` on the entry flags,
     then by [ebx+0x10]: 204 / 205 accept a SURFACE field ([field+0x12] == 0) whose terrain is not 0 / 6, others ->
     jmp 0x5580C0C2 (Scorch's set).
  D. the execute reads spell 0x29's sound/gfx lists for its cast effect (`mov edx,0x29` @0x5579F465 and @0x5579F4DF,
     ebx = te) -> `mov edx,[ebx+0x10]` so every clone plays the FX of ITS OWN Spells.pfs record (Scorch still 0x29).

Terrain ids: 0 Water 1 Grass 2 Desert 3 Snow 4 Steppe 5 Wasteland 6 Ice 7 EarthWall 9 Lava A CaveWater C Dirt D CaveIce.
Caves @0x55862400 (PIC via call/pop delta; the DLL rebases), G_TSPELL @0x558E9B64 (DATA slack after the dual-sphere
NEWTAB/STASH).  Backup <game>\backup\AoWEPACK.dll.bak_tspells.  Dry run by default; --apply / --revert.
"""
import argparse, os, shutil, struct, sys
import pefile
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DEFAULT_DLL = game_file("AoWEPACK.dll")
BAK_SUFFIX = ".bak_tspells"
BASE, CODE_V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x55862400, 0x55862600
G_TSPELL = 0x558E9B64
ID_REJUV, ID_WITHER = 204, 205
SCORCH_MAP, SCORCH_VALID_TAIL = 0x5580C000, 0x5580C0C2
SITES = {  # name: (va, original bytes)
    "exec":  (0x5579F3F8, bytes.fromhex("5356578bf28bd8")),      # TRejuvenateTE +0x54 prologue
    "map":   (0x5579F3E5, bytes.fromhex("e816cc0600")),          # callback stub: call 0x5580C000
    "val1":  (0x5579F617, bytes.fromhex("e8a4ca0600")),          # slot +0xB4 predicate: call 0x5580C0C0
    "val2":  (0x5579F63F, bytes.fromhex("e87cca0600")),          # slot +0xB0 predicate: call 0x5580C0C0
    "fx1":   (0x5579F465, bytes.fromhex("ba29000000")),          # mov edx,0x29 (cast effect gfx list)
    "fx2":   (0x5579F4DF, bytes.fromhex("ba29000000")),          # mov edx,0x29 (cast sound list)
    # v3 (2026-10-12): Path of Life / Path of Decay never touch lava: TAbstractUnit.PathOfLifeTerrainChange 0x557801A4 /
    # PathOfDecayTerrainChange 0x557801C4 (eax=unit, edx=field, ecx=&terrain; 6-B prologue `55 8BEC 0FBE01`) -> caves that
    # replay the prologue, `cmp ax,9 / je <epilogue>`, and resume at the vanilla `cmp ax,6`.
    "pol":   (0x557801A4, bytes.fromhex("558bec0fbe01")),
    "pod":   (0x557801C4, bytes.fromhex("558bec0fbe01")),
    # v3: Wither's area is one hex smaller: the three `push 2` radii in the TE execute (visibility gate x2, ForEachHex)
    # become `push ([te+0x10] == 205 ? 1 : 2)`; ebx = te at all three.  The targeting highlight radius comes from
    # [spell+0x39] (TGlobalTargetSpell.ShowTargetSelection @0x5579E3BD) -> poked to 0 for 205 by the pipeline.
    "r1":    (0x5579F40C, bytes.fromhex("8a4322506a02")),         # mov al,[ebx+0x22]; push eax; push 2
    "r2":    (0x5579F424, bytes.fromhex("8a4322506a02")),
    "r3":    (0x5579F4F8, bytes.fromhex("0fbe4322506a02")),       # movsx eax,[ebx+0x22]; push eax; push 2
    # v4 (2026-10-12): the TARGETING PREVIEW is built by TRejuvenate's slot +0xA4 override @0x5579F658 (SetupTargetSelection:
    # base setup, then the selection's TShortIntList (+8) is cleared and filled with RadToHN(3) = 19 zero entries = the
    # 19-hex (radius 2) highlight; RadToHN(2) = 7).  Entry hook (6 B `53 56 8BF1 8BCE`) publishes [spell+0x10] into
    # G_TSPELL; the `mov eax,3` @0x5579F66B becomes 2 for 205.  (The earlier [spell+0x39] poke was the wrong object.)
    "sel0":  (0x5579F658, bytes.fromhex("53568bf18bce")),
    "seln":  (0x5579F66B, bytes.fromhex("b803000000")),
    # v4: Path of Sand (our July ability, callback cave 0x5580F3C0 = a clone of PathOfLife's) must not touch lava either:
    # its `cmp ax,6 / je skip` (6 B @0x5580F3C6) -> cave adding `cmp ax,9`.  Path of Frost keeps its lava->wasteland rule.
    "pos":   (0x5580F3C6, bytes.fromhex("6683f806740e")),
}
SEL0_RESUME, SELN_RESUME = 0x5579F65E, 0x5579F670
POS_RESUME, POS_SKIP = 0x5580F3CC, 0x5580F3DA
POL_RESUME, POL_SKIP, POD_RESUME, POD_SKIP = 0x557801AA, 0x557801BE, 0x557801CA, 0x557801DE
R1_RESUME, R2_RESUME, R3_RESUME = 0x5579F412, 0x5579F42A, 0x5579F4FF
EXEC_RESUME = 0x5579F3FF
FX_NEW = bytes.fromhex("8b531090 90")                           # mov edx,[ebx+0x10]; nop; nop

ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm_delta(src, va):
    if "$D" not in src: return bytes(ks.asm(src, va)[0])
    s1 = src.replace("call $D", ".byte 0xe8, 0, 0, 0, 0").replace("sub ebx, $D", "sub ebx, 0x7fffffff")
    b = bytearray(ks.asm(s1, va)[0])
    anchor = b"\xe8\x00\x00\x00\x00\x5b\x81\xeb\xff\xff\xff\x7f"
    n, k = 0, b.find(anchor)
    while k >= 0:
        struct.pack_into("<I", b, k + 8, va + k + 5); n += 1; k = b.find(anchor, k + len(anchor))
    assert n == src.count("call $D") == src.count("sub ebx, $D")
    return bytes(b)


def build():
    out = bytearray(); where = {}
    def place(name, src):
        while len(out) % 16: out.append(0)
        va = ZONE + len(out); where[name] = va; out.extend(asm_delta(src, va))
    # A: eax = te.  Store [te+0x10] into G_TSPELL, replay the prologue, resume.
    place("exec", """
        push ebx
        call $D
        pop ebx
        sub ebx, $D
        mov ecx, [eax+0x10]
        mov [ebx+%(g)#x], ecx
        pop ebx
        push ebx
        push esi
        push edi
        mov esi, edx
        mov ebx, eax
        jmp %(resume)#x
    """ % {"g": G_TSPELL, "resume": EXEC_RESUME})
    # B: callback, ecx = &terrain.  Preserve everything but flags.
    place("map", """
        push ebx
        push eax
        call $D
        pop ebx
        sub ebx, $D
        mov eax, [ebx+%(g)#x]
        cmp eax, %(rj)d
        je rejuv
        cmp eax, %(wi)d
        je wither
        pop eax
        pop ebx
        jmp %(scorch)#x
    rejuv:
        mov al, [ecx]
        test al, al
        jz done
        cmp al, 6
        je done
        cmp al, 9
        je done
        mov byte ptr [ecx], 1
        jmp done
    wither:
        mov al, [ecx]
        test al, al
        jz done
        cmp al, 6
        je done
        cmp al, 9
        je done
        mov byte ptr [ecx], 5
    done:
        pop eax
        pop ebx
        ret
    """ % {"g": G_TSPELL, "rj": ID_REJUV, "wi": ID_WITHER, "scorch": SCORCH_MAP})
    # C: valid-target predicate tail.  Entry flags = the base check's result (ZF set -> reject), ebx = spell,
    # esi = field.  Returns al = 0/1.
    place("valid", """
        je reject
        mov eax, [ebx+0x10]
        cmp eax, %(rj)d
        je rejuv
        cmp eax, %(wi)d
        je wither
        jmp %(scorch_tail)#x
    rejuv:
    wither:
        cmp byte ptr [esi+0x12], 0
        jne reject
        mov al, [esi+0x14]
        test al, al
        jz reject
        cmp al, 6
        je reject
        cmp al, 9
        jne yes
    reject:
        xor eax, eax
        ret
    yes:
        mov al, 1
        ret
    """ % {"rj": ID_REJUV, "wi": ID_WITHER, "scorch_tail": SCORCH_VALID_TAIL})
    for name, resume, skip in (("pol", POL_RESUME, POL_SKIP), ("pod", POD_RESUME, POD_SKIP)):
        place(name, """
        push ebp
        mov ebp, esp
        movsx eax, byte ptr [ecx]
        cmp ax, 9
        je %(skip)#x
        jmp %(resume)#x
    """ % {"skip": skip, "resume": resume})
    for name, load, resume in (("r1", "mov al, [ebx+0x22]", R1_RESUME), ("r2", "mov al, [ebx+0x22]", R2_RESUME), ("r3", "movsx eax, byte ptr [ebx+0x22]", R3_RESUME)):
        place(name, """
        %(load)s
        push eax
        cmp dword ptr [ebx+0x10], %(wi)d
        jne two
        push 1
        jmp %(resume)#x
    two:
        push 2
        jmp %(resume)#x
    """ % {"load": load, "wi": ID_WITHER, "resume": resume})
    place("sel0", """
        push ebx
        push esi
        mov esi, ecx
        call $D
        pop ebx
        sub ebx, $D
        mov ecx, [eax+0x10]
        mov [ebx+%(g)#x], ecx
        mov ecx, esi
        jmp %(resume)#x
    """ % {"g": G_TSPELL, "resume": SEL0_RESUME})
    place("seln", """
        push ebx
        call $D
        pop ebx
        sub ebx, $D
        mov eax, 3
        cmp dword ptr [ebx+%(g)#x], %(wi)d
        jne ok
        mov eax, 2
    ok:
        pop ebx
        jmp %(resume)#x
    """ % {"g": G_TSPELL, "wi": ID_WITHER, "resume": SELN_RESUME})
    place("pos", """
        cmp ax, 6
        je %(skip)#x
        cmp ax, 9
        je %(skip)#x
        jmp %(resume)#x
    """ % {"skip": POS_SKIP, "resume": POS_RESUME})
    assert ZONE + len(out) <= ZONE_END, hex(ZONE + len(out))
    return bytes(out), where


def reloc_set(d):
    pe = struct.unpack_from("<I", d, 0x3C)[0]; opt = struct.unpack_from("<H", d, pe + 20)[0]; nsec = struct.unpack_from("<H", d, pe + 6)[0]
    secs = [struct.unpack_from("<IIII", d, pe + 24 + opt + 40 * k + 8) for k in range(nsec)]
    rrva, rsz = struct.unpack_from("<II", d, pe + 24 + 0x88)
    def r2f(rva):
        for vs, va, rs, ro in secs:
            if va <= rva < va + max(vs, rs): return ro + rva - va
    out = set()
    if not rsz: return out
    p, end = r2f(rrva), r2f(rrva) + rsz
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
    ap.add_argument("--dll", default=DEFAULT_DLL)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read())
    pe = pefile.PE(a.dll, fast_load=True)
    g_off = pe.get_offset_from_rva(G_TSPELL - BASE)
    zone, where = build()
    patches = {}   # name -> (file off, orig, new)
    for name, (va, orig) in SITES.items():
        off = va - CODE_V2F
        if name == "exec": new = b"\xe9" + struct.pack("<i", where["exec"] - (va + 5)) + b"\x90" * (len(orig) - 5)
        elif name == "map": new = b"\xe8" + struct.pack("<i", where["map"] - (va + 5))
        elif name in ("val1", "val2"): new = b"\xe8" + struct.pack("<i", where["valid"] - (va + 5))
        elif name in ("pol", "pod", "r1", "r2", "r3", "sel0", "seln", "pos"): new = b"\xe9" + struct.pack("<i", where[name] - (va + 5)) + b"\x90" * (len(orig) - 5)
        else: new = FX_NEW
        patches[name] = (off, orig, new)
    rl = reloc_set(d)
    bad = [hex(r) for r in rl if any(va - 3 <= r < va + len(o) for va, o in SITES.values()) or ZONE <= r < ZONE_END or G_TSPELL <= r < G_TSPELL + 4]
    def classify(n, o, orig, new):
        cur = bytes(d[o:o + len(orig)])
        if cur == orig: return "vanilla"
        if cur == new: return "ours"
        if n not in ("fx1", "fx2") and cur[0] in (0xE8, 0xE9) and ZONE <= (SITES[n][0] + 5 + struct.unpack_from("<i", cur, 1)[0]) < ZONE_END: return "stale"   # older layout of this patch
        return "OTHER"
    states = {n: classify(n, o, orig, new) for n, (o, orig, new) in patches.items()}
    zl = bytes(d[ZONE - CODE_V2F:ZONE_END - CODE_V2F])
    zstate = "zero" if not any(zl) else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else "DIFFERS"
    gstate = "zero" if not any(d[g_off:g_off + 4]) else "NONZERO"
    print("sites %s | zone %s (%d B) | G_TSPELL %s | relocs %s | caves %s" % (states, zstate, len(zone), gstate, bad or "none", ", ".join("%s=%#x" % kv for kv in where.items())))
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        for name, s in where.items():
            print("  --", name)
            for i in md.disasm(zone[s - ZONE:], s):
                print("   %08X  %-16s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
                if i.mnemonic == "ret" and name != "map" and i.address > s + 40: break
                if i.mnemonic == "jmp" and i.op_str in ("%#x" % EXEC_RESUME,): break
    if bad or "OTHER" in states.values(): print("ABORT"); return 1
    if a.revert:
        for n, (o, orig, new) in patches.items():
            if states[n] in ("ours", "stale"): d[o:o + len(orig)] = orig
        d[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
        with open(a.dll, "r+b") as f: f.seek(0); f.write(d)
        print("reverted"); return 0
    if all(s == "ours" for s in states.values()) and zstate == "ours": print("already applied"); return 0
    if any(s == "stale" for s in states.values()) or (zstate == "DIFFERS" and "ours" in states.values()): print("older layout of this patch found: re-syncing zone + hooks")
    if "ours" not in states.values() and zstate not in ("zero",): print("ABORT: zone not free"); return 1
    if gstate != "zero" and "ours" not in states.values(): print("ABORT: G_TSPELL slot not free"); return 1
    d[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE); d[ZONE - CODE_V2F:ZONE - CODE_V2F + len(zone)] = zone
    for n, (o, orig, new) in patches.items(): d[o:o + len(new)] = new
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(a.dll, BAK_SUFFIX)
    if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    with open(a.dll, "r+b") as f: f.seek(0); f.write(d)
    assert open(a.dll, "rb").read() == bytes(d); print("Written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
