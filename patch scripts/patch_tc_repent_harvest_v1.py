#!/usr/bin/env python3
r"""
AoWTCPCK.dll side of REPENT (206) and HARVEST SOULS (207) (2026-10-12; v2 sky beam, v3 static UFO beam, v4 Harvest
caster effects, all the same day).  AoWEPACK side: patch_repent_harvest_v1.py.

REPENT = "a slow holy sparkle followed by a static semi-transparent beam of light from the sky (kind of like a UFO
beam) that starts narrow then grows before disappearing"; v4: "damage to unit should occur when the beam reaches
full width, near the end of the spell gfx".  The spell is SpellTypes class 0x0A (hail), so each strike runs
TCAbRangedTE PROC0005 @0x40E259 (pattern hex = HailPattern[[te+0x34] mod 7], pixel = CenterHNtoHX + Random(20)+6,
path = MakeLinePath (px-100, py-300) -> (px, py) in 30 steps; TfxHS kind 0x0A: slot 0 at the path head (frame =
GetFrameIndex(global clock + (fx ptr>>2) phase) - a free-running loop, useless for a sequenced animation), slot 1
drawn at the previous path points (trail), slot 2 + sound 1 on landing).  So the animation is a separate kind-0x26
"driver" effect like Hellfire's portal (its Show/NewFrame draw spell-list slot 1 at the effect's XYZ, frame = own
tick / (f18+1), lives frames*(f18+1) ticks): spawned at the target hex by the p5 cave, slot 1 of Repent's gfx =
DualDF 400+ (sparkles -> beam grows -> hold -> fade); the strike's own head is a transparent sprite and its trail is
skipped, its path is lengthened so the landing (damage + impact flash + sound 1) comes when the beam is at full
width.  Hooks (all keyed on [te+0x18] == 206, te = [ebp-4]; every Random call kept for RNG parity):
  p5    0x40E259 (10 B `8B45FC 8B4018 83E87C`): strike count [te+0x28] := 1 (hellfire's phase-0 hook @0x40B550 set
        the hail default 0x15; NextStrike 0x40D290 stops once [te+0x34] >= [te+0x28]) + spawn the driver: HXtoHP
        0x4022BC (eax hx, edx hy, ecx &px, push &py) -> AddEffect 0x41C6EC (eax map [0x46C064], dl kind 0x26) ->
        TXYZ (IAT 0x46EB24) created 0x401040 + TXYZList.Add 0x402DE4 to [fx+0x1C], GetXYZ 0x402DF4 -> [xyz+4] =
        px + BEAM_DX, [xyz+8] = py + BEAM_DY (frame top-left: the sequence has xs = ys = 0), [fx+0x14] = 0x34,
        [fx+0x18] = 206, [fx+0x2C] = nil (hellfire v1 lesson: the phase-1 loop treats a unit there as a hit target).
  pat   0x40E294 (7 B, just after the pattern lookup whose `mov eax,[0x4693E0]` carries a .reloc @0x40E28D): ecx
        (HN) := 0 so the strike lands on the target hex (pattern[0] = HN 6).
  jx/jy 0x40E2D2 / 0x40E2E9 (10 B): Random(20) drawn, result forced to 10 (+6 = 16 = hex centre).
  vert  0x40E34B (10 B): no `sub eax,100` -> the (invisible) path is vertical.
  steps 0x40E30D (10 B `50 6A1E 8B45F0 83C01C 50`): MakeLinePath step count 30 -> LAND_TICK so the damage lands when
        the beam is full (sparkle + grow frames x 3 ticks).
  show  0x42FB3A (11 B `55 B801000000 E8..` in TfxHS.Show[0x0A], fx = [ebp-4]): skip the slot-1 trail draw for 206
        (slot 1 is the driver's animation) -> resume at the impact-list call 0x42FB4D.

HARVEST SOULS reuses the Animate Dead corpse machinery (SpellTypes 0x27):
  A. TCAbRangedTE.Execute only broadcasts the corpse messages (0x31008 FX, 0x31009 act) for ids 0x81/0x82 (@0x40BB26
     `cmp [eax+0x18],0x82 / je` 9 B) -> cave adds id 207.  msg = {0: 0x31008/9, 8: caster CU [te+0x10], 0xC: spell}.
  B. TCCorpseHS.MapFieldMsgProc 0x423BAC, 0x31009 branch: switch @0x423FDB (`sub eax,0x81 / je 129 / dec eax /
     jne else` 14 B): 129 and 130 do GetSpell(0x81/0x82).CreateCA(caster=[msg+8], corpse=[hs+0xC]) ->
     ExecuteCombatAction([map+0xE4], ca) -> ca.Release, then the "else" tail @0x4240AD frees the corpse sprite when
     the corpse unit is not enabled (@0x424125 TObject.Free).  Cave: id 207 -> GetSpell(207).CreateCA(caster, corpse)
     (= the AoWEPACK cave: +5 casting points to the caster, returns NIL) -> if nil just fall into the tail (corpse
     freed; the 0x31008 effect already played 18 kind-0x1F sparkles of the spell's slot-0 sprite = DualDF 334-336,
     Animate Dead's own twinkle re-coloured purple); a non-nil CA is executed+released like the vanilla cases.
     v5 "tepop" (hook @0x40BC39, the `jmp 0x40CAF2` that ends the TE's 0x31009 broadcast loop; [ebp-4] = te): for 207
     spawn a kind-0x26 effect at the CASTER's hex (caster CU [te+0x10] -> its map sprite [cu+0x60] -> X/Y virtuals
     +0x74/+0x78 -> HXtoHP, +16/+16; the sequence's own xs/ys place the art) reading slot 1 = DualDF 460-480 (the
     vanilla summon dome MAGIC 89-109 tinted purple) and play sound 1 (ENCHN01) through TSFXLibrary.Play 0x4022F4 if
     [map+0x129] - once per cast by construction (v4 did this per corpse with a clock latch and faulted, see below).
  C. v4 "fx8": the 0x31008 branch, after the corpse pixel is computed (HXtoHP -> [ebp-0x20] px, [ebp-0x24] py; hook
     @0x423C95, 12 B `C745E401000000 B805000000`): for 207 spawn N_STREAM kind-0x1F sparkles (AddEffect 0x1F,
     [+0x14]=0x34, [+0x18]=207 -> drawn with slot 0 = the purple twinkle) on MakeLinePath 0x402E04 (eax x0, edx y0,
     ecx x1, pushed y1 / steps / &[fx+0x1C]) from the corpse (+8..24 px) to the caster's sprite (+10..22, +8..20),
     30..59 steps each -> a stream of circular purple motes drifting to the caster during the whirl.
The 7-hex preview and the strike-table entry come from patch_tc_spell_alias_v1.py (ALIAS 207 -> 0x82).

Caves @0x43CA00-0x43CF00 (PIC via call/pop delta; LATCH cell = DATA slack 0x46B860).  Backup <game>\backup\AoWTCPCK.dll.bak_repharv.
Dry run; --apply / --revert.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DEFAULT_DLL = game_file("AoWTCPCK.dll")
BAK_SUFFIX = ".bak_repharv"
BASE, CODE_V2F = 0x400000, 0x400C00
ZONE, ZONE_END = 0x43CA00, 0x43CF00
# (v5: no latch any more - the pop lives in the TE, once per cast.  History: v4 kept a clock latch in the code zone -> write fault,
#  the CODE section is not writable; v4b moved it to DATA slack 0x46B860 but the clock read [[0x46E8D4]+0x40] (AoWE.AoWHSMap)
#  faulted inside the corpse handler: VEH log 10/13 = AV read 0 @TCPCK+0x3CD2E.)
ID_REPENT, ID_HARVEST = 206, 207
JITTER = 10                      # Random(20) result forced for Repent: +6 = 16 px = the hex centre
# driver geometry/timing - must match build_dual_sphere_fx_v1.py beam_frames() (80x300 frames, foot at y 280) and the
# pipeline's slot-1 f18 (2 -> 3 ticks per frame)
BEAM_W, BEAM_FOOT, TICKS_PER_FRAME = 80, 280, 3
N_SPARK, N_GROW = 14, 14
BEAM_DX, BEAM_DY = 16 - BEAM_W // 2, 16 - BEAM_FOOT
STRIKE_TICKS_PER_STEP = 2            # TfxHS.NewFrame's dispatcher @0x429ED5 adds 1 to [fx+0x10] for EVERY kind, then the hail case @0x42A3D5 adds 1 more
LAND_TICK = (N_SPARK + N_GROW) * TICKS_PER_FRAME * STRIKE_TICKS_PER_STEP   # 168 path points = tick 84 = the beam's first full-width frame (v4/v5 hit early because of the double step)
KIND_DRIVER, KIND_SPARKLE = 0x26, 0x1F
N_STREAM = 10                                             # Harvest motes per corpse
RANDINT, GETSPELL, SPELLREG_GLOBAL, MAP_GLOBAL, EXECCA, CLOCK_GLOBAL, SFXPLAY = 0x401020, 0x4029B4, 0x46E8D0, 0x46C064, 0x40259C, 0x46E8D4, 0x4022F4
HXTOHP, ADDEFFECT, TXYZ_IAT, TOBJCREATE, XYZADD, GETXYZ, MAKELINE = 0x4022BC, 0x41C6EC, 0x46EB24, 0x401040, 0x402DE4, 0x402DF4, 0x402E04
SITES = {
    "p5":     (0x40E259, bytes.fromhex("8b45fc8b401883e87c"), None),                 # mov eax,[ebp-4]; mov eax,[eax+0x18]; sub eax,0x7c
    "pat":    (0x40E294, bytes.fromhex("8b45fc0fb75022"), 0x40E29B),                 # mov eax,[ebp-4]; movzx edx,word [eax+0x22]  (ecx = HN)
    "jx":     (0x40E2D2, bytes.fromhex("b814000000e8442dffff"), 0x40E2DC),           # mov eax,0x14; call RandInt
    "jy":     (0x40E2E9, bytes.fromhex("b814000000e82d2dffff"), 0x40E2F3),
    "steps":  (0x40E30D, bytes.fromhex("506a1e8b45f083c01c50"), 0x40E317),           # push eax; push 0x1e; mov eax,[ebp-0x10]; add eax,0x1c; push eax
    "vert":   (0x40E34B, bytes.fromhex("83e8647105e8d32cffff"), 0x40E355),           # sub eax,0x64; jno; call overflow
    "show":   (0x42FB3A, bytes.fromhex("55b801000000e87fe9ffff"), 0x42FB45),         # push ebp; mov eax,1; call SUB_0042E4C4 (slot pick)
    "bcast":  (0x40BB26, bytes.fromhex("817818820000007410"), 0x40BB2F),             # cmp [eax+0x18],0x82; je 0x40BB3F
    "fx8":    (0x423C95, bytes.fromhex("c745e401000000b805000000"), 0x423CA1),       # mov [ebp-0x1c],1; mov eax,5   (0x31008 branch, corpse px/py ready)
    "switch": (0x423FDB, bytes.fromhex("2d81000000746a480f85c4000000"), 0x4240AD),   # sub eax,0x81; je; dec; jne else
    "tepop":  (0x40BC39, bytes.fromhex("e9b40e0000"), 0x40CAF2),                       # jmp 0x40CAF2 right after the 0x31009 broadcast loop (TE Execute, [ebp-4] = te)
}
P5_HAIL7C, P5_OTHER = 0x40E264, 0x40E26D
SHOW_SKIP, SLOTPICK = 0x42FB4D, 0x42E4C4
BCAST_YES, SW_129, SW_130, SW_ELSE = 0x40BB3F, 0x42404C, 0x423FE9, 0x4240AD
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm_delta(src, va):
    if "$D" not in src: return bytes(ks.asm(src, va)[0])
    s1 = src.replace("call $D", ".byte 0xe8, 0, 0, 0, 0").replace("sub ebx, $D", "sub ebx, 0x7fffffff")
    b = bytearray(ks.asm(s1, va)[0]); anchor = b"\xe8\x00\x00\x00\x00\x5b\x81\xeb\xff\xff\xff\x7f"
    n, k = 0, b.find(anchor)
    while k >= 0:
        struct.pack_into("<I", b, k + 8, va + k + 5); n += 1; k = b.find(anchor, k + len(anchor))
    assert n == src.count("call $D") == src.count("sub ebx, $D")
    return bytes(b)


# shared snippet: the caster's hex pixel -> an 8-byte stack buffer ([esp+4] = px, [esp] = py).  Needs ebx = delta,
# msg in [ebp-8]; clobbers eax/ecx/edx/esi; jumps to %(fail)s (with NOTHING pushed) when there is no caster sprite.
CASTER_PX = """
        mov eax, [ebp-8]
        mov eax, [eax+8]
        test eax, eax
        jz %(fail)s
        mov eax, [eax+0x60]
        test eax, eax
        jz %(fail)s
        mov esi, eax
        mov edx, [esi]
        call dword ptr [edx+0x78]
        movsx eax, al
        push eax
        mov eax, esi
        mov edx, [esi]
        call dword ptr [edx+0x74]
        movsx eax, al
        pop edx
        sub esp, 8
        lea ecx, [esp+4]
        push esp
        call %(hx)#x
"""


def build():
    out = bytearray(); where = {}
    def place(name, src):
        while len(out) % 16: out.append(0)
        va = ZONE + len(out); where[name] = va; out.extend(asm_delta(src, va))
    # --- Repent: PROC0005 entry.  [ebp-4] = TE.  For 206: one strike + spawn the kind-0x26 beam driver at the hex.
    place("p5", """
        mov eax, [ebp-4]
        cmp dword ptr [eax+0x18], %(rep)d
        jne go
        mov dword ptr [eax+0x28], 1
        push ebx
        push esi
        push edi
        call $D
        pop ebx
        sub ebx, $D
        sub esp, 8
        lea ecx, [esp+4]
        push esp
        mov eax, [ebp-4]
        movzx edx, word ptr [eax+0x22]
        movzx eax, word ptr [eax+0x20]
        call %(hx)#x
        mov eax, [ebx+%(map)#x]
        mov dl, %(kind)d
        call %(add)#x
        mov esi, eax
        mov dl, 1
        mov eax, [ebx+%(txyz)#x]
        call %(create)#x
        mov edx, eax
        mov eax, [esi+0x1c]
        call %(xyzadd)#x
        mov eax, [esi+0x1c]
        xor edx, edx
        call %(getxyz)#x
        mov edx, [esp+4]
        add edx, %(dx)d
        mov [eax+4], edx
        mov edx, [esp]
        add edx, %(dy)d
        mov [eax+8], edx
        mov dword ptr [esi+0x14], 0x34
        mov dword ptr [esi+0x18], %(rep)d
        mov dword ptr [esi+0x2c], 0
        add esp, 8
        pop edi
        pop esi
        pop ebx
        mov eax, [ebp-4]
    go:
        mov eax, [eax+0x18]
        sub eax, 0x7c
        jne %(other)#x
        jmp %(hail)#x
    """ % {"rep": ID_REPENT, "other": P5_OTHER, "hail": P5_HAIL7C, "hx": HXTOHP, "map": MAP_GLOBAL, "kind": KIND_DRIVER,
           "add": ADDEFFECT, "txyz": TXYZ_IAT, "create": TOBJCREATE, "xyzadd": XYZADD, "getxyz": GETXYZ, "dx": BEAM_DX, "dy": BEAM_DY})
    place("pat", """
        mov eax, [ebp-4]
        cmp dword ptr [eax+0x18], %(rep)d
        je zero
        cmp dword ptr [eax+0x18], %(implo)d
        jne go
    zero:
        xor ecx, ecx
    go:
        movzx edx, word ptr [eax+0x22]
        jmp %(resume)#x
    """ % {"rep": ID_REPENT, "implo": 389, "resume": SITES["pat"][2]})      # 2026-10-14: Implosion's single strike = HailPattern[0] = HN 6 (a NEIGHBOUR hex) -> no damage; force HN 0 for 389 too (fills the cave's 16-byte padding exactly: 32 B, later caves don't move)
    for nm in ("jx", "jy"):
        place(nm, """
        mov eax, 0x14
        call %(rnd)#x
        mov edx, [ebp-4]
        cmp dword ptr [edx+0x18], %(rep)d
        jne go
        mov eax, %(jit)d
    go:
        jmp %(resume)#x
    """ % {"rnd": RANDINT, "rep": ID_REPENT, "jit": JITTER, "resume": SITES[nm][2]})
    place("steps", """
        push eax
        mov eax, [ebp-4]
        cmp dword ptr [eax+0x18], %(rep)d
        jne thirty
        push %(land)d
        jmp go
    thirty:
        push 0x1e
    go:
        mov eax, [ebp-0x10]
        add eax, 0x1c
        push eax
        jmp %(resume)#x
    """ % {"rep": ID_REPENT, "land": LAND_TICK, "resume": SITES["steps"][2]})
    # vert: eax = px+jx (x end), edx = y start, ecx = x end; flags free.
    place("vert", """
        push edx
        mov edx, [ebp-4]
        cmp dword ptr [edx+0x18], %(rep)d
        pop edx
        je go
        sub eax, 0x64
    go:
        jmp %(resume)#x
    """ % {"rep": ID_REPENT, "resume": SITES["vert"][2]})
    # show: Show[0x0A] after the head draw; fx = [ebp-4]. 206 -> no trail (slot 1 belongs to the driver).
    place("show", """
        mov eax, [ebp-4]
        cmp dword ptr [eax+0x18], %(rep)d
        je %(skip)#x
        push ebp
        mov eax, 1
        call %(pick)#x
        jmp %(resume)#x
    """ % {"rep": ID_REPENT, "skip": SHOW_SKIP, "pick": SLOTPICK, "resume": SITES["show"][2]})
    # --- Harvest Souls
    place("bcast", """
        cmp dword ptr [eax+0x18], 0x82
        je %(yes)#x
        cmp dword ptr [eax+0x18], %(harv)d
        je %(yes)#x
        jmp %(resume)#x
    """ % {"yes": BCAST_YES, "harv": ID_HARVEST, "resume": SITES["bcast"][2]})
    # fx8: 0x31008 branch.  [ebp-8] = msg, [ebp-0x20] = corpse px, [ebp-0x24] = corpse py.  For 207 stream motes.
    place("fx8", """
        mov dword ptr [ebp-0x1c], 1
        mov eax, [ebp-8]
        cmp dword ptr [eax+0xc], %(harv)d
        jne go
        push ebx
        push esi
        push edi
        call $D
        pop ebx
        sub ebx, $D
        %(casterpx)s
        mov edi, %(n)d
    loop:
        mov eax, [ebx+%(map)#x]
        mov dl, %(kind)d
        call %(add)#x
        mov esi, eax
        mov dword ptr [esi+0x14], 0x34
        mov dword ptr [esi+0x18], %(harv)d
        mov dword ptr [esi+0x2c], 0
        mov eax, 12
        call %(rnd)#x
        add eax, [esp]
        add eax, 8
        push eax
        mov eax, 30
        call %(rnd)#x
        add eax, 30
        push eax
        lea eax, [esi+0x1c]
        push eax
        mov eax, 12
        call %(rnd)#x
        add eax, [esp+16]
        add eax, 10
        push eax
        mov eax, 16
        call %(rnd)#x
        add eax, [ebp-0x24]
        add eax, 8
        push eax
        mov eax, 16
        call %(rnd)#x
        add eax, [ebp-0x20]
        add eax, 8
        pop edx
        pop ecx
        call %(line)#x
        dec edi
        jnz loop
        add esp, 8
    nocaster:
        pop edi
        pop esi
        pop ebx
    go:
        mov eax, 5
        jmp %(resume)#x
    """ % {"harv": ID_HARVEST, "casterpx": CASTER_PX % {"fail": "nocaster", "hx": HXTOHP}, "n": N_STREAM, "map": MAP_GLOBAL,
           "kind": KIND_SPARKLE, "add": ADDEFFECT, "rnd": RANDINT, "line": MAKELINE, "resume": SITES["fx8"][2]})
    # switch: eax = spell id at entry; [ebp-8] = msg, [ebp-4] = corpse HS; ebx is free (saved by the handler's prologue).
    place("switch", """
        sub eax, 0x81
        je %(c129)#x
        dec eax
        je %(c130)#x
        cmp eax, %(delta)d
        jne %(els)#x
        call $D
        pop ebx
        sub ebx, $D
        push 0
        mov eax, [ebx+%(reg)#x]
        mov eax, [eax]
        mov eax, [eax+0x84]
        mov edx, [ebp-8]
        mov edx, [edx+0xc]
        call %(getspell)#x
        mov edx, [ebp-4]
        mov ecx, [edx+0xc]
        mov edx, [ebp-8]
        mov edx, [edx+8]
        push ebx
        mov ebx, [eax]
        call dword ptr [ebx+0x78]
        pop ebx
        test eax, eax
        jz %(els)#x
        mov [ebp-0xc], eax
        mov eax, [ebx+%(map)#x]
        mov eax, [eax+0xe4]
        mov edx, [ebp-0xc]
        call %(execca)#x
        mov eax, [ebp-0xc]
        mov edx, [eax]
        call dword ptr [edx+0x2c]
        jmp %(els)#x
    """ % {"c129": SW_129, "c130": SW_130, "delta": ID_HARVEST - 0x82, "els": SW_ELSE, "reg": SPELLREG_GLOBAL,
           "getspell": GETSPELL, "map": MAP_GLOBAL, "execca": EXECCA})
    # tepop (v5): TE Execute right after the 0x31009 broadcast loop - ONCE per cast by construction (no latch).
    # [ebp-4] = te, [te+0x10] = caster CU -> [cu+0x60] its map sprite -> X/Y -> HXtoHP (+16/+16 = hex centre).
    place("tepop", """
        mov eax, [ebp-4]
        cmp dword ptr [eax+0x18], %(harv)d
        jne done
        push ebx
        push esi
        push edi
        call $D
        pop ebx
        sub ebx, $D
        mov eax, [ebp-4]
        mov eax, [eax+0x10]
        test eax, eax
        jz nocaster
        mov eax, [eax+0x60]
        test eax, eax
        jz nocaster
        mov esi, eax
        mov edx, [esi]
        call dword ptr [edx+0x78]
        movsx eax, al
        push eax
        mov eax, esi
        mov edx, [esi]
        call dword ptr [edx+0x74]
        movsx eax, al
        pop edx
        sub esp, 8
        lea ecx, [esp+4]
        push esp
        call %(hx)#x
        mov eax, [ebx+%(map)#x]
        mov dl, %(kind)d
        call %(add)#x
        mov esi, eax
        mov dl, 1
        mov eax, [ebx+%(txyz)#x]
        call %(create)#x
        mov edx, eax
        mov eax, [esi+0x1c]
        call %(xyzadd)#x
        mov eax, [esi+0x1c]
        xor edx, edx
        call %(getxyz)#x
        mov edx, [esp+4]
        add edx, 16
        mov [eax+4], edx
        mov edx, [esp]
        add edx, 16
        mov [eax+8], edx
        mov dword ptr [esi+0x14], 0x34
        mov dword ptr [esi+0x18], %(harv)d
        mov dword ptr [esi+0x2c], 0
        add esp, 8
        mov eax, [ebx+%(map)#x]
        cmp byte ptr [eax+0x129], 0
        je nocaster
        mov eax, [ebx+%(reg)#x]
        mov eax, [eax]
        mov eax, [eax+0x84]
        mov edx, %(harv)d
        call %(getspell)#x
        mov eax, [eax+0x28]
        mov edx, 1
        call %(play)#x
    nocaster:
        pop edi
        pop esi
        pop ebx
    done:
        jmp %(resume)#x
    """ % {"harv": ID_HARVEST, "hx": HXTOHP, "map": MAP_GLOBAL, "kind": KIND_DRIVER, "add": ADDEFFECT, "txyz": TXYZ_IAT,
           "create": TOBJCREATE, "xyzadd": XYZADD, "getxyz": GETXYZ, "reg": SPELLREG_GLOBAL, "getspell": GETSPELL,
           "play": SFXPLAY, "resume": SITES["tepop"][2]})
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
    zone, where = build()
    patches = {n: (va - CODE_V2F, orig, b"\xe9" + struct.pack("<i", where[n] - (va + 5)) + b"\x90" * (len(orig) - 5)) for n, (va, orig, _r) in SITES.items()}
    rl = reloc_set(d)
    bad = [hex(r) for r in rl if any(va - 3 <= r < va + len(o) for va, o, _r in SITES.values()) or ZONE <= r < ZONE_END]
    def classify(n, o, orig, new):
        cur = bytes(d[o:o + len(orig)])
        if cur == orig: return "vanilla"
        if cur == new: return "ours"
        if cur[0] == 0xE9 and ZONE <= SITES[n][0] + 5 + struct.unpack_from("<i", cur, 1)[0] < ZONE_END: return "stale"
        return "OTHER"
    states = {n: classify(n, o, orig, new) for n, (o, orig, new) in patches.items()}
    zl = bytes(d[ZONE - CODE_V2F:ZONE_END - CODE_V2F])
    zstate = "zero" if not any(zl) else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else "DIFFERS"
    print("sites %s | zone %s (%d B) | relocs %s | caves %s" % (states, zstate, len(zone), bad or "none", ", ".join("%s=%#x" % kv for kv in where.items())))
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        for name, s in where.items():
            print("  --", name)
            nxt = min([v for v in where.values() if v > s] + [ZONE + len(zone)])
            for i in md.disasm(zone[s - ZONE:nxt - ZONE], s): print("   %08X  %-16s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad or "OTHER" in states.values(): print("ABORT"); return 1
    if a.revert:
        for n, (o, orig, new) in patches.items():
            if states[n] in ("ours", "stale"): d[o:o + len(orig)] = orig
        d[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
        with open(a.dll, "r+b") as f: f.seek(0); f.write(d)
        print("reverted"); return 0
    if all(s == "ours" for s in states.values()) and zstate == "ours": print("already applied"); return 0
    if "ours" not in states.values() and "stale" not in states.values() and zstate != "zero": print("ABORT: zone not free"); return 1
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
