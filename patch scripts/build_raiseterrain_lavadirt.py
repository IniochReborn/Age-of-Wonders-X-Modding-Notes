#!/usr/bin/env python3
r"""AoWx -- Raise Terrain: EVERY lava hex -> dirt, timed to the raise glow.

ADOPTED 2026-08-30 from BXL/Ziggurat's build_raiseterrain_lavadirt.py (v3,
"dirtdelay"); his RE kept, our caves. v2 same day (user ruling): his 50%
random roll is REMOVED -- conversion always applies, which also removes the
whole selection-RNG desync surface (v1 briefly used MP-safe map.Random(2)).

WHAT IT DOES. Raise Terrain (TRaiseTerrainTE.RaiseTerrain @0x557A3280)
already accepts lava targets but mountain placement fails on lava, silently
wasting the cast. Now every LAVA hex in the area becomes DIRT(0xC): the
green raise glow plays, and the terrain flips at glow frame 9 -- the same
moment a real mountain would be revealed. Non-lava hexes keep normal
mountain behaviour.

PATCH 1 -- cave_lavadirt (hook @0x557A333E, 5B `33 C0 8B 75 08`):
  field=[ESP+8]; terrain != Lava(9) -> replay + jmp 0x557A3343 (mountain
  path). Lava -> EBX=field, jmp 0x557A3414: the vanilla raise-anim block
  builds the green-glow TImageSequenceAnimation with
  NewFrameRaiseTerrainAnimation as per-frame callback (data=EBX=field) and
  PlaceHX'es it. NO terrain change up front, no RNG.

PATCH 2 -- cave_dirtdelay (hook @0x557A31E9, 7B `8B D8 BA 6A 01 02 00`, in
  NewFrameRaiseTerrainAnimation @0x557A31B0; EAX=field, EDI=frame):
  frame==9 AND hex still Lava -> ChangeTerrainEx via the map vtable+0xD0
  wrapper (x=[field+0x10], y=+0x11, level=+0x12, terrain=DIRT). The wrapper
  rolls the terrain VARIANT via AoWHSMap.Random, which asserts ("Invalid
  AoWHSMap.Random use") in the render/anim context -- so the guard flag
  ((*0x558FA040)+0x3C bit3) is set for the call and restored after, making
  that variant roll take the raw-RandInt path. Then the displaced bytes
  replay and 0x557A31F0 resumes. Real mountains share the callback but are
  never lava -> no-op.
  (BXL's failed prior, do not retry: calling the lower 7-param
  HSEngine.THSMap.ChangeTerrainEx @0x557025D4 directly = stack corruption.)

⚠ KNOWN MP RESIDUAL (reduced but not zero, LAN-test): which hexes convert is
now fully deterministic (every lava hex), but the conversion still runs from
the ANIMATION callback and the wrapper's variant roll is unsynchronized. If
the glow anim does not tick identically on both peers (e.g. unobserved hex),
the flip or its variant byte could diverge -> OOS. If LAN testing shows this,
the fallback is up-front conversion in patch 1 (wrapper ChangeTerrainEx in
the synced TE context, glow purely cosmetic) -- BXL's earlier variant.

CAVES (ours; his 0x5580DB60/0x5580DC20 sit inside OUR RS-spawn/upkeep caves):
  cave_lavadirt  @0x55813A00   cave_dirtdelay @0x55813A80
  reservation 0x55813A00..0x55813B80, zero-verified (LOS cave owns
  0x55813200..0x55813A00 exclusively -- do not encroach).
Position-independent: call/pop delta for [0x558E9494] map holder and the
0x558FA040 guard-map holder; everything else register-relative/rel32.

Usage:
    py -3.10 build_raiseterrain_lavadirt.py            # dry run
    py -3.10 build_raiseterrain_lavadirt.py --apply
    py -3.10 build_raiseterrain_lavadirt.py --revert   # surgical
"""
import os
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.environ.get("AOW_GAME_DIR") or os.path.dirname(HERE)
DLL = os.path.join(GAME, "AoWEPACK.dll")
BAK = DLL + ".bak_rtlavadirt"

D = 0x55700C00

INJ = 0x557A333E
INJ_ORIG = bytes.fromhex("33c08b7508")
RESUME = 0x557A3343
CONT = 0x557A3498
ANIM = 0x557A3414
CB_INJ = 0x557A31E9
CB_ORIG = bytes.fromhex("8bd8ba6a010200")
CB_CONT = 0x557A31F0
MAP_RANDOM = 0x5577827C          # TAoWHSMap.Random (eax=map, edx=range) MP-lockstep
MAPPTR = 0x558E9494              # map = *(*MAPPTR)
RNDMAPPTR = 0x558FA040           # guard map: (*RNDMAPPTR)+0x3C bit3
LAVA, DIRT = 9, 0x0C

CAVE_LD = 0x55813A00
CAVE_DD = 0x55813A80
CAVE_LO, CAVE_HI = 0x55813A00, 0x55813B80
PH = 0x11111111
PH2 = 0x22222222


def asm(src, addr):
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    src = "\n".join(ln.split(";")[0] for ln in src.splitlines())
    code, _ = Ks(KS_ARCH_X86, KS_MODE_32).asm(src, addr)
    return bytearray(code)


def patch_anchor(code, base, targets):
    """Rewrite the `call next / pop eax` anchor and each placeholder disp32
    to (target - anchor). The call is emitted as `call base` and fixed here."""
    i = next(k for k in range(len(code) - 5)
             if code[k] == 0xE8 and code[k + 5] == 0x58)
    anchor = base + i + 5
    code[i + 1:i + 5] = struct.pack("<i", 0)
    for ph, tgt in targets:
        j = code.find(struct.pack("<I", ph))
        assert j != -1, hex(ph)
        code[j:j + 4] = struct.pack("<i", tgt - anchor)
    return bytes(code)


def make_lavadirt():
    # v2 (user ruling 2026-08-30): NO roll -- every lava hex converts. The
    # earlier 50% map.Random(2) roll was removed entirely (no RNG, no
    # selection-desync surface, no Random-assert surface).
    src = f"""
        mov  eax, [esp+8]
        movsx eax, byte ptr [eax+0x14]
        cmp  eax, {LAVA}
        jne  _mountain
        mov  ebx, [esp+8]
        jmp  0x{ANIM:X}
    _mountain:
        xor  eax, eax
        mov  esi, [ebp+8]
        jmp  0x{RESUME:X}
    """
    return bytes(asm(src, CAVE_LD))


def make_dirtdelay():
    src = f"""
        cmp  edi, 9
        jne  _orig
        cmp  byte ptr [eax+0x14], {LAVA}
        jne  _orig
        push eax
        call 0x{CAVE_DD:X}
        pop  eax
        mov  ebx, [eax + 0x{PH:X}]
        movzx edx, byte ptr [ebx+0x3c]
        push edx
        or   byte ptr [ebx+0x3c], 8
        mov  eax, [eax + 0x{PH2:X}]
        mov  eax, [eax]
        mov  edx, [esp+4]
        movzx ecx, byte ptr [edx+0x11]
        push ecx
        movzx ecx, byte ptr [edx+0x12]
        push ecx
        push 0
        push 0x{DIRT:X}
        movzx ecx, byte ptr [edx+0x10]
        xor  edx, edx
        mov  esi, [eax]
        call dword ptr [esi+0xd0]
        pop  edx
        mov  [ebx+0x3c], dl
        pop  eax
    _orig:
        mov  ebx, eax
        mov  edx, 0x2016a
        jmp  0x{CB_CONT:X}
    """
    return patch_anchor(asm(src, CAVE_DD), CAVE_DD,
                        [(PH, RNDMAPPTR), (PH2, MAPPTR)])


def rel(src, dst):
    return struct.pack("<i", dst - (src + 5))


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

    ld = make_lavadirt()
    dd = make_dirtdelay()
    assert CAVE_LD + len(ld) <= CAVE_DD and CAVE_DD + len(dd) <= CAVE_HI
    hook1 = b"\xE9" + rel(INJ, CAVE_LD)
    hook2 = b"\xE9" + rel(CB_INJ, CAVE_DD) + b"\x90\x90"

    edits = [
        (INJ, INJ_ORIG, hook1, "RaiseTerrain -> cave_lavadirt"),
        (CB_INJ, CB_ORIG, hook2, "frame callback -> cave_dirtdelay"),
        (CAVE_LD, bytes(len(ld)), ld, "cave_lavadirt"),
        (CAVE_DD, bytes(len(dd)), dd, "cave_dirtdelay"),
    ]

    def cur(va, n):
        return bytes(d[va - D:va - D + n])

    print("raiseterrain lava->dirt, all hexes (glow-timed); caves 0x%X/0x%X (%d+%d B)"
          % (CAVE_LD, CAVE_DD, len(ld), len(dd)))
    states = []
    for va, ob, nb, desc in edits:
        c = cur(va, len(nb))
        st = ("original" if c == ob else "applied" if c == nb else "FOREIGN")
        states.append(st)
        print("  %-34s @0x%08X  %s" % (desc, va, st))
    if "FOREIGN" in states:
        print("FOREIGN bytes present - refusing everything")
        return 1

    bad = reloc_hits(d, [(INJ, INJ + 5), (CB_INJ, CB_INJ + 7),
                         (CAVE_LO, CAVE_HI)])
    if bad:
        print("!! relocs under patched ranges:", [hex(v) for v in bad])
        return 1

    if revert:
        if all(s == "original" for s in states):
            print("already original - nothing to do")
            return 0
        for va, ob, nb, _ in edits:
            d[va - D:va - D + len(nb)] = ob
        open(DLL, "wb").write(bytes(d))
        print("reverted (hooks restored, caves zeroed); backup untouched")
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
    print("  1. Raise Terrain on a lava field: EVERY lava hex turns to dirt,")
    print("     each flip at the glow's mountain-reveal moment (not up front)")
    print("  2. non-lava hexes still raise mountains normally")
    print("  3. no 'Invalid AoWHSMap.Random use' popup at the glow peak")
    print("  4. LAN: cast on lava while the other player watches AND while")
    print("     fogged - check for OOS (anim-timing residual, see docstring)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
