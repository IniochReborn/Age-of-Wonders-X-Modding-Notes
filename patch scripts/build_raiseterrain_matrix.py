#!/usr/bin/env python3
r"""AoWx -- Raise Terrain rework: underground casting + temporary conversions.

SUPERSEDES build_raiseterrain_lavadirt.py (run its --revert before --apply
here; this script refuses if the old hooks are still installed).

BEHAVIOR MATRIX (user spec 2026-08-30):
  underground, any hex except Rock(8)/map-border(0xF)/Lava(9)/water-ice/Earth
                          -> TEMPORARY Earth(7), raise glow, no mountain
  underground Lava(9)     -> TEMPORARY Dirt(0xC), glow, no mountain
  surface    Lava(9)      -> TEMPORARY Dirt(0xC), glow, no mountain
  surface    Dirt(0xC)    -> TEMPORARY Wasteland(5) + the normal (temporary)
                             raised mountain on top (renders as the wasteland
                             mountain since mountains skin per terrain)
  surface    anything else-> vanilla (temporary mountain), untouched
Temporary = counts down on the caster's turns and REVERTS to the original
terrain, and the hex carries the same magic sparkle as Freeze Water ice --
because the marker IS a TFrozenWaterHS, extended.

================================ THE JULY MYSTERY, SOLVED =====================
The 2026-07 attempt (raise-terrain-underground, reverted) patched the two
ValidTarget*MapF filters and never found why underground stayed uncastable.
The gate was never in validation: TGlobalTargetSpell's target-error routine
@0x5579E73C checks `[spell+0x39]` -- a SURFACE-ONLY flag -- and if set, pulls
(x,y,level) off the target via 0x5577ED94 (-> position vtable+0x98) and
produces a "must be cast on the surface" resourcestring ([0x558E8FE4]) when
level != 0. TRaiseTerrain.Create sets the flag: `mov byte [esi+0x39],1`
@0x557A3579. TFreezeWater never sets it (hence CaveWater support).
  FIX P0: one immediate byte @0x557A357C: 01 -> 00.

=========================== TEMPORARY-TERRAIN MARKERS =========================
TFrozenWaterHS (VMT 0x557147B4, classref holder [0x55714774], instance size
0x10) is vanilla's temporary-ice marker: +0xC countdown (dec on owner's turn,
NewTurn @0x55764B98), +0xD owner, MeltIce @0x55764AE0 (Ice->Water /
CaveIce->CaveWater via map [0x558FA040] vmt+0xD0, else Destroy via VMT-4),
TerrainChanged @0x55764B6C (self-frees when terrain leaves {6,0xD}),
ReadWrite @0x55764AAC (rwByte +0xC tag 0x1E, +0xD tag 0x1F via stream
vmt+0x3C). Bytes +0xE/+0xF are unused zero-initialised padding.

We extend the class in place:
  [hs+0xE] = ORIGINAL terrain to restore (0 = vanilla ice marker)
  [hs+0xF] = our TARGET terrain
  P3 cave_melt   (hook @0x55764AE0, 6B): [hs+0xE]!=0 -> if the hex still
     holds our target, ChangeTerrainEx back to [hs+0xE] (mirrors the vanilla
     melt recipe; cleanup then happens via TerrainChanged exactly like ice);
     foreign terrain -> straight to the Destroy tail @0x55764B60.
  P4 cave_tchg   (hook @0x55764B7B, 6B): [hs+0xE]!=0 -> keep the marker only
     while the hex holds [hs+0xF]; anything else (incl. our own restore)
     frees it. [arg+8] skip-flag honoured first, as vanilla.
  P5 cave_rw     (hook @0x55764AD3, 7B): appends rwByte(+0xE, tag 0x6E) and
     rwByte(+0xF, tag 0x6F) -- temp terrain survives save/load; old saves
     load 0/0 = vanilla marker (missing tag leaves the field zero).

============================= THE SPELL SIDE ==================================
  P1 cave_convert (hook @0x557A333E, 5B, per valid hex in
     TRaiseTerrainTE.RaiseTerrain; frame: [esp]=TE (level +0x22),
     [esp+4]=arg2 (caster byte +0x24 -- the mountain code reads it there),
     [esp+8]=field): decides per the matrix. Conversions call spawn_marker
     (find-or-create TFrozenWaterHS on the hex -- find 0x55701FFC, create
     0x55703064, PlaceHX 0x557025F4, duration (map.Random(0xB)-5)/5+3 = 2..4
     turns like mountains, all in the SYNCED TE context) then jump to the
     vanilla glow-anim block @0x557A3414 with EBX=field (glow, no mountain).
     The surface-dirt case spawns the marker then falls into the vanilla
     mountain path (replay + 0x557A3343): mountain + glow; terrain flips at
     frame 9 like the rest.
  P2 cave_flip (hook @0x557A31E9, 7B, in NewFrameRaiseTerrainAnimation;
     EAX=field, EDI=frame): at frame 9, if the hex carries one of OUR markers
     ([hs+0xF]!=0) and still holds the original terrain [hs+0xE], flip it to
     [hs+0xF] via map vmt+0xD0 under the (*0x558FA040)+0x3C bit3 guard flag
     (suppresses the "Invalid AoWHSMap.Random use" variant-roll assert from
     the anim context). Replaces the old lava-only dirtdelay.

MP: all STATE (marker spawn, duration, owner, restore, save) happens in
synced contexts. The frame-9 flip remains anim-timed (the accepted residual
from the lavadirt feature; peers flip identically iff the glow ticks on
both). RECAST NOTE: recasting on a converted hex refreshes the marker; a
dirt-from-lava hex recast on the surface becomes wasteland+mountain and will
revert to DIRT (its lava provenance is lost) -- accepted.

CAVES: 0x55813B80..0x55813E00 reservation (after the lavadirt zone; verified
zero). BSS: none. PIC: call/pop delta anchors for the four globals
(0x55714774 classref, 0x558E9494 map, 0x558FA040 guard-map), rel32 to thunks.

Usage:
    py -3.10 build_raiseterrain_matrix.py            # dry run
    py -3.10 build_raiseterrain_matrix.py --apply
    py -3.10 build_raiseterrain_matrix.py --revert   # surgical
"""
import os
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.environ.get("AOW_GAME_DIR") or os.path.dirname(HERE)
DLL = os.path.join(GAME, "AoWEPACK.dll")
BAK = DLL + ".bak_rtmatrix"

D = 0x55700C00

# spell-side sites
FLAG_IMM = 0x557A357C            # ctor `mov byte [esi+0x39],1` immediate
INJ = 0x557A333E
INJ_ORIG = bytes.fromhex("33c08b7508")
RESUME = 0x557A3343
CONT = 0x557A3498
ANIM = 0x557A3414
CB_INJ = 0x557A31E9
CB_ORIG = bytes.fromhex("8bd8ba6a010200")
CB_CONT = 0x557A31F0
# marker-side sites
MELT = 0x55764AE0
MELT_ORIG = bytes.fromhex("538bd88b4304")
MELT_RESUME = 0x55764AE6
MELT_DESTROY = 0x55764B60
MELT_TAIL = 0x55764B23           # pop ebx; ret
TCHG = 0x55764B7B
TCHG_ORIG = bytes.fromhex("807b08007513")
TCHG_VANILLA = 0x55764B81
TCHG_DESTROY = 0x55764B8B
TCHG_KEEP = 0x55764B94
RW = 0x55764AD3
RW_ORIG = bytes.fromhex("8bc68b18ff533c")
RW_EPILOG = 0x55764ADA
# engine entry points / globals
FIND_HS = 0x55701FFC             # (eax=field, edx=classref) -> hs|0
CREATE = 0x55703064              # TEObject create thunk (eax=classref, dl=1, ecx=0)
PLACEHX = 0x557025F4             # (eax=map, edx=hs, ecx=x, push level, push y)
MAP_RANDOM = 0x5577827C
CLASSREF = 0x55714774            # holder of TFrozenWaterHS classref
MAPPTR = 0x558E9494              # map = *(*MAPPTR)
GUARDMAP = 0x558FA040            # (*GUARDMAP)+0x3C bit3 = Random guard flag
TAG_OLD, TAG_TGT = 0x6E, 0x6F

CAVE_LO, CAVE_HI = 0x55813B80, 0x55813ED0
A_CONVERT = 0x55813B80
A_SPAWN = 0x55813C40
A_FLIP = 0x55813CF0
A_MELT = 0x55813DA0
A_TCHG = 0x55813E10
A_RW = 0x55813E40
A_WFLIP = 0x55813E80
PH_CLS, PH_MAP, PH_GRD = 0x11111111, 0x22222222, 0x33333333
PH_ANCH = 0x44444444             # patched to the anchor VA itself (for `sub`)

EARTH, WASTE, ROCK, LAVA, DIRT, BORDER = 7, 5, 8, 9, 0x0C, 0x0F


def asm(src, addr):
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    src = "\n".join(ln.split(";")[0] for ln in src.splitlines())
    code, _ = Ks(KS_ARCH_X86, KS_MODE_32).asm(src, addr)
    return bytearray(code)


def patch_anchor(code, base, targets):
    """call-next/pop anchor WITHOUT a sub: the popped register holds the
    RUNTIME anchor address, and every global is addressed as
    [reg + (target_preferred - anchor_preferred)], which resolves to the
    runtime target under any rebase. (⚠ the failed first cut subtracted the
    preferred anchor first AND used target-anchor displacements -- the two
    cancel wrong, EA off by the anchor VA -> wild read -> 'Exception
    occurred during TRaiseTerrainTE'. Pick ONE scheme; this is the one the
    proven lavadirt caves used.)"""
    i = next(k for k in range(len(code) - 5)
             if code[k] == 0xE8 and code[k + 1:k + 5] == b"\x00\x00\x00\x00"
             and code[k + 5] in (0x58, 0x5B))            # pop eax / pop ebx
    anchor = base + i + 5
    for ph, tgt in targets:
        while True:
            j = code.find(struct.pack("<I", ph))
            if j == -1:
                break
            code[j:j + 4] = struct.pack("<i", tgt - anchor)
    return bytes(code)


def make_convert():
    # v3: ch = the field's overlay byte; the ROAD FAMILY (road=4, bridge=5,
    # per the Flood RE) is excluded from every CONVERSION branch -- flipping
    # terrain under a bridge deleted it (user report). Excluded hexes fall
    # through to vanilla behaviour (mountain path; on lava that wastes the
    # cast exactly like vanilla) except underground, where they do nothing.
    # v3: the surface-dirt case flips dirt->wasteland UP FRONT (cave_wflip,
    # synced TE context, same idiom as Level Terrain) BEFORE the mountain
    # path -- mountains cannot place on dirt, which made the whole case a
    # silent no-op (user report). The frame-9 flip then no-ops naturally
    # (terrain already == target) and the mountain reveals on wasteland.
    src = f"""
        mov  eax, [esp+8]
        movzx ecx, byte ptr [eax+0x14]
        mov  ch, byte ptr [eax+0x15]
        cmp  cl, {LAVA}
        je   _lavachk
        mov  edx, [esp]
        cmp  byte ptr [edx+0x22], 0
        je   _surface
        cmp  cl, {ROCK}
        je   _nothing
        cmp  cl, {BORDER}
        je   _nothing
        cmp  cl, {EARTH}
        je   _nothing
        cmp  ch, 4
        je   _nothing
        cmp  ch, 5
        je   _nothing
        mov  dl, {EARTH}
        jmp  _glowconv
    _surface:
        cmp  cl, {DIRT}
        jne  _mountain
        cmp  ch, 4
        je   _mountain
        cmp  ch, 5
        je   _mountain
        call 0x{A_WFLIP:X}
        mov  cl, {DIRT}
        mov  dl, {WASTE}
        call 0x{A_SPAWN:X}
        jmp  _mountain
    _lavachk:
        cmp  ch, 4
        je   _lavaveto
        cmp  ch, 5
        je   _lavaveto
        mov  dl, {DIRT}
    _glowconv:
        call 0x{A_SPAWN:X}
        mov  ebx, [esp+8]
        jmp  0x{ANIM:X}
    _lavaveto:
        mov  edx, [esp]
        cmp  byte ptr [edx+0x22], 0
        jne  _nothing
        jmp  _mountain
    _nothing:
        jmp  0x{CONT:X}
    _mountain:
        xor  eax, eax
        mov  esi, [ebp+8]
        jmp  0x{RESUME:X}
    """
    return bytes(asm(src, A_CONVERT))


def make_wflip():
    """Flip the field to WASTELAND immediately, in the synced TE context,
    via the map's vtable+0xD0 ChangeTerrainEx (no guard hack needed here --
    Level Terrain calls it from its TE the same way). Called with the same
    frame convention as cave_spawn: field = [ebp+0x10]."""
    src = f"""
        push ebp
        mov  ebp, esp
        pushad
        call _anch
    _anch:
        pop  ebx
        mov  esi, [ebp+0x10]
        mov  eax, [ebx + 0x{PH_GRD:X}]
        movzx ecx, byte ptr [esi+0x11]
        push ecx
        movzx ecx, byte ptr [esi+0x12]
        push ecx
        push 0
        push {WASTE}
        movzx ecx, byte ptr [esi+0x10]
        xor  edx, edx
        mov  edi, [eax]
        call dword ptr [edi+0xd0]
        popad
        pop  ebp
        ret
    """
    return patch_anchor(asm(src, A_WFLIP), A_WFLIP, [(PH_GRD, GUARDMAP)])


def make_spawn():
    # in: cl=old terrain, dl=target. Caller frame (esp at cave_convert entry
    # == E): TE=[E], arg2=[E+4], field=[E+8]. Inside: push ebp -> ebp=E-8,
    # so TE=[ebp+8], arg2=[ebp+0xC], field=[ebp+0x10]. pushad image:
    # ecx@[ebp-8], edx@[ebp-0xC].
    src = f"""
        push ebp
        mov  ebp, esp
        pushad
        call _anch
    _anch:
        pop  ebx
        mov  esi, [ebp+0x10]
        mov  edx, [ebx + 0x{PH_CLS:X}]
        mov  eax, esi
        call 0x{FIND_HS:X}
        test eax, eax
        jnz  _have
        xor  ecx, ecx
        mov  dl, 1
        mov  eax, [ebx + 0x{PH_CLS:X}]
        call 0x{CREATE:X}
        mov  edi, eax
        movsx eax, byte ptr [esi+0x11]
        push eax
        movsx eax, byte ptr [esi+0x12]
        push eax
        movsx ecx, byte ptr [esi+0x10]
        mov  eax, [ebx + 0x{PH_MAP:X}]
        mov  eax, [eax]
        mov  edx, edi
        call 0x{PLACEHX:X}
        mov  eax, edi
    _have:
        push eax
        mov  eax, [ebx + 0x{PH_MAP:X}]
        mov  eax, [eax]
        mov  edx, 0xB
        call 0x{MAP_RANDOM:X}
        sub  eax, 5
        mov  ecx, 5
        cdq
        idiv ecx
        add  al, 3
        pop  edx
        mov  [edx+0xC], al
        mov  eax, [ebp+0xC]
        mov  al, [eax+0x24]
        mov  [edx+0xD], al
        mov  al, [ebp-8]
        mov  [edx+0xE], al
        mov  al, [ebp-0xC]
        mov  [edx+0xF], al
        popad
        pop  ebp
        ret
    """
    code = asm(src, A_SPAWN)
    return patch_anchor(code, A_SPAWN,
                        [(PH_CLS, CLASSREF), (PH_MAP, MAPPTR)])


def make_flip():
    src = f"""
        cmp  edi, 9
        jne  _orig
        push eax
        call _anch
    _anch:
        pop  ebx
        mov  edx, [ebx + 0x{PH_CLS:X}]
        call 0x{FIND_HS:X}
        test eax, eax
        jz   _origpop
        cmp  byte ptr [eax+0xF], 0
        je   _origpop
        mov  ecx, [esp]
        mov  dl, [ecx+0x14]
        cmp  dl, [eax+0xE]
        jne  _origpop
        push esi
        mov  esi, eax
        mov  ecx, [ebx + 0x{PH_GRD:X}]
        movzx edx, byte ptr [ecx+0x3c]
        push edx
        or   byte ptr [ecx+0x3c], 8
        push ecx
        mov  eax, [ebx + 0x{PH_MAP:X}]
        mov  eax, [eax]
        mov  edx, [esp+0xC]
        movzx ebx, byte ptr [edx+0x11]
        push ebx
        movzx ebx, byte ptr [edx+0x12]
        push ebx
        push 0
        movzx ebx, byte ptr [esi+0xF]
        push ebx
        movzx ecx, byte ptr [edx+0x10]
        xor  edx, edx
        mov  ebx, [eax]
        call dword ptr [ebx+0xd0]
        pop  ecx
        pop  edx
        mov  [ecx+0x3c], dl
        pop  esi
    _origpop:
        pop  eax
    _orig:
        mov  ebx, eax
        mov  edx, 0x2016a
        jmp  0x{CB_CONT:X}
    """
    code = asm(src, A_FLIP)
    return patch_anchor(code, A_FLIP,
                        [(PH_CLS, CLASSREF), (PH_MAP, MAPPTR), (PH_GRD, GUARDMAP)])


def make_melt():
    src = f"""
        push ebx
        mov  ebx, eax
        cmp  byte ptr [ebx+0xE], 0
        je   _vanilla
        mov  eax, [ebx+4]
        mov  dl, [eax+0x14]
        cmp  dl, [ebx+0xF]
        jne  _destroy
        push esi
        mov  eax, ebx
        mov  edx, [eax]
        call dword ptr [edx+0x78]
        movsx eax, al
        push eax
        mov  eax, ebx
        mov  edx, [eax]
        call dword ptr [edx+0x7c]
        movsx eax, al
        push eax
        push 0
        movzx eax, byte ptr [ebx+0xE]
        push eax
        mov  eax, ebx
        mov  edx, [eax]
        call dword ptr [edx+0x74]
        movsx ecx, al
        mov  edx, ebx
        call _anch
    _anch:
        pop  eax
        mov  eax, [eax + 0x{PH_GRD:X}]
        mov  esi, [eax]
        call dword ptr [esi+0xd0]
        pop  esi
        jmp  0x{MELT_TAIL:X}
    _destroy:
        jmp  0x{MELT_DESTROY:X}
    _vanilla:
        mov  eax, [ebx+4]
        jmp  0x{MELT_RESUME:X}
    """
    # [0x558FA040] holds the MAP OBJECT directly (single deref) -- vanilla
    # MeltIce itself uses it that way (`mov eax,[0x558fa040]; mov ebx,[eax]`).
    return patch_anchor(asm(src, A_MELT), A_MELT, [(PH_GRD, GUARDMAP)])


def make_tchg():
    src = f"""
        cmp  byte ptr [ebx+8], 0
        jne  _keep
        cmp  byte ptr [esi+0xE], 0
        je   _vanilla
        mov  al, [ebx]
        cmp  al, [esi+0xF]
        je   _keep
        jmp  0x{TCHG_DESTROY:X}
    _vanilla:
        jmp  0x{TCHG_VANILLA:X}
    _keep:
        jmp  0x{TCHG_KEEP:X}
    """
    return bytes(asm(src, A_TCHG))


def make_rw():
    src = f"""
        push ebx
        mov  eax, esi
        mov  ebx, [eax]
        call dword ptr [ebx+0x3c]
        pop  ebx
        lea  edx, [ebx+0xE]
        mov  ecx, 0x{TAG_OLD:X}
        mov  eax, esi
        mov  edi, [eax]
        call dword ptr [edi+0x3c]
        lea  edx, [ebx+0xF]
        mov  ecx, 0x{TAG_TGT:X}
        mov  eax, esi
        mov  edi, [eax]
        call dword ptr [edi+0x3c]
        jmp  0x{RW_EPILOG:X}
    """
    return bytes(asm(src, A_RW))


def rel(src, dst):
    return struct.pack("<i", dst - (src + 5))


def hook(src, dst, length):
    return b"\xE9" + rel(src, dst) + b"\x90" * (length - 5)


def reloc_hits(d, ranges):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    rva, size = struct.unpack_from("<II", d, e + 24 + 96 + 5 * 8)
    n = struct.unpack_from("<H", d, e + 6)[0]
    p0 = e + 24 + struct.unpack_from("<H", d, e + 20)[0]
    for i in range(n):
        vsz, va, rsz, ro = struct.unpack_from("<IIII", d, p0 + i * 40 + 8)
        if va <= rva < va + max(vsz, rsz):
            p = ro + rva - va
            break
    end, hits = p + size, []
    while p < end - 8:
        prva, blk = struct.unpack_from("<II", d, p)
        if not blk:
            break
        for k in range(p + 8, p + blk, 2):
            v = struct.unpack_from("<H", d, k)[0]
            if v >> 12:
                va = 0x55700000 + prva + (v & 0xFFF)
                for lo, hi in ranges:
                    if lo <= va < hi:
                        hits.append(va)
        p += blk
    return hits


def main():
    apply = "--apply" in sys.argv
    revert = "--revert" in sys.argv
    d = bytearray(open(DLL, "rb").read())

    caves = [(A_CONVERT, make_convert(), "cave_convert"),
             (A_SPAWN, make_spawn(), "cave_spawn"),
             (A_FLIP, make_flip(), "cave_flip"),
             (A_MELT, make_melt(), "cave_melt"),
             (A_TCHG, make_tchg(), "cave_tchg"),
             (A_RW, make_rw(), "cave_rw"),
             (A_WFLIP, make_wflip(), "cave_wflip")]
    addrs = [A_CONVERT, A_SPAWN, A_FLIP, A_MELT, A_TCHG, A_RW, A_WFLIP,
             CAVE_HI]
    for i, (va, b, nm) in enumerate(caves):
        assert va + len(b) <= addrs[i + 1], (nm, len(b))

    edits = [(FLAG_IMM, b"\x01", b"\x00", "surface-only flag OFF (P0)")]
    edits += [(va, ob, hook(va, dst, len(ob)), nm) for va, ob, dst, nm in (
        (INJ, INJ_ORIG, A_CONVERT, "RaiseTerrain -> cave_convert (P1)"),
        (CB_INJ, CB_ORIG, A_FLIP, "frame cb -> cave_flip (P2)"),
        (MELT, MELT_ORIG, A_MELT, "MeltIce -> cave_melt (P3)"),
        (TCHG, TCHG_ORIG, A_TCHG, "TerrainChanged -> cave_tchg (P4)"),
        (RW, RW_ORIG, A_RW, "ReadWrite -> cave_rw (P5)"))]
    edits += [(va, bytes(len(b)), bytes(b), nm) for va, b, nm in caves]

    def cur(va, n):
        return bytes(d[va - D:va - D + n])

    print("raiseterrain matrix: UG cast + temporary conversions; caves "
          "0x%X..0x%X (%d B used)" % (CAVE_LO, CAVE_HI,
                                      sum(len(b) for _, b, _ in caves)))
    states = []
    for va, ob, nb, nm in edits:
        assert len(ob) == len(nb), nm
        c = cur(va, len(nb))
        st = "original" if c == ob else "applied" if c == nb else "FOREIGN"
        states.append(st)
        print("  %-38s @0x%08X  %s" % (nm, va, st))
    if "FOREIGN" in states:
        print("FOREIGN bytes present (is build_raiseterrain_lavadirt still "
              "applied? run its --revert first) - refusing")
        return 1

    bad = reloc_hits(d, [(FLAG_IMM, FLAG_IMM + 1), (INJ, INJ + 5),
                         (CB_INJ, CB_INJ + 7), (MELT, MELT + 6),
                         (TCHG, TCHG + 6), (RW, RW + 7),
                         (CAVE_LO, CAVE_HI)])
    if bad:
        print("!! relocs under patched ranges:", [hex(v) for v in bad])
        return 1

    if revert:
        for va, ob, nb, _ in edits:
            d[va - D:va - D + len(nb)] = ob + bytes(max(0, len(nb) - len(ob)))
        open(DLL, "wb").write(bytes(d))
        print("reverted (all hooks + flag restored, caves zeroed)")
        return 0

    if not apply:
        print("dry run - nothing written (--apply / --revert)")
        return 0
    if all(s == "applied" for s in states):
        print("already applied - nothing to do")
        return 0
    if not os.path.isfile(BAK):
        shutil.copy2(DLL, BAK)
        print("backed up to", os.path.basename(BAK))
    for va, ob, nb, _ in edits:
        d[va - D:va - D + len(nb)] = nb
    open(DLL, "wb").write(bytes(d))
    print("APPLIED - needs in-game test:")
    print(" 1. cast Raise Terrain UNDERGROUND (no 'surface' error): floor")
    print("    hexes get glowing temporary Earth walls; rock/border/lava-")
    print("    adjacent behavior per matrix; UG lava -> glowing temp dirt")
    print(" 2. surface lava -> temp dirt (sparkles, reverts after 2-4 of")
    print("    the caster's turns); surface dirt -> wasteland + mountain,")
    print("    reverts to dirt when the marker expires")
    print(" 3. other surface terrain: vanilla temporary mountains, no change")
    print(" 4. vanilla Freeze Water ice still freezes/melts normally")
    print(" 5. save/load mid-duration: temp terrain still reverts on time")
    print(" 6. LOS: temp Earth walls block strategic sight while up")
    return 0


if __name__ == "__main__":
    sys.exit(main())
