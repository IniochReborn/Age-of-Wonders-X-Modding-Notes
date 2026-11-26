#!/usr/bin/env python3
r"""AoWx -- Mind Decay: make the combat roll draw-count invariant (MP OOS).

USER REPORT: casting **Mind Decay** in tactical combat has often desynced
multiplayer games. Confirmed by audit to be a VANILLA defect (the whole gate
below is byte-identical to AoWEPACK.dpl); this is an attempt at hardening it.

========================= WHY THIS IS AN OOS HAZARD =========================
See [[lan-desync-investigation]] for the full two-RNG model. In short:

  * `AoWE.TAoWHSMap.Random` @0x5577827C is the SYNCED generator. Its body
    copies the synced store `[map+0x230]` into Delphi's `System.RandSeed`,
    draws with `@RandInt`, then writes RandSeed back to [map+0x230].
    `TSyncTE` compares [map+0x230] -- that is what raises the OOS dialog.
  * Combat rolls do NOT go through it. `AoWE.HitRole` @0x55725D98 clamps a
    chance to 10..90 and calls **`VCL30!System.@RandInt` directly** (exactly
    one draw per call, no early exit -- verified). That advances RandSeed but
    never writes back to [map+0x230].

=> Combat rolls are INVISIBLE to the sync check, yet they still consume the
   shared RandSeed. Two machines only stay consistent if they make the SAME
   NUMBER of @RandInt draws. A one-sided combat draw silently changes every
   later to-hit/resist result (different damage, different deaths), and the
   synced stream only diverges -- and the dialog only fires -- much later.
   This is FIX #8's bug class one layer down.

`TMindDecay.CreateCA` @0x557F85DC rolls the spell's outcome into `[ca+0x14]`,
and **that roll is conditional behind FIVE gates, four of which dereference
the target's STRATEGIC unit `[combatunit+0x4C]`**:

    IsClass(target, TCombatUnit)                     -> else no roll
    [target+0x4C].GetUnitType()        == 2          -> no roll
    [target+0x4C].GetRace()            == 0x0B       -> no roll
    [target+0x4C].GetAbilityEnabled(0x81)            -> no roll   (0x81 =
                                     PassiveAb.TAnimatedAbility = "Animated")
    IsClass([target+0x4C], TLeader)                  -> no roll

That is by far the widest eligibility gate of any combat spell -- TSlow and
TEntangle gate their roll on ONE check, made against the combat unit's own
virtuals and never touching the strategic layer. So Mind Decay is uniquely
exposed: whenever two machines disagree about the target's unit type, race,
Animated flag or Leader-ness, one draws a RandInt and the other does not, and
the whole combat's RNG stream separates from that point on.

Callers confirm this runs everywhere: `TCombatSpell.fcExecuteCombatCommand`
@0x557F7882/0x557F7A08 (the deterministic all-machine combat simulation), and
AoWTCPCK's `TCAbRangedTE.Execute+0x1257` reads the resulting [ca+0x14] flag.

================================= THE FIX ==================================
Make the draw UNCONDITIONAL and gate only the STORE, so RandSeed consumption
no longer depends on target eligibility at all:

    <same five gates>  ->  eligible = 0/1        (no early exit any more)
    ALWAYS: eax = spellStrength([spell+0x34]) - target.GetResistance()
            call HitRole                          (exactly one @RandInt)
    if eligible: [ca+0x14] = al                   (else leave it 0, as vanilla)

The roll's inputs are safe to hoist: the resistance comes from the target's
OWN virtual **VMT+0x74** (a TCombatObject base-class slot -- TCombatUnit /
TCombatWall / TCombatObject all implement it), NOT from [target+0x4C], and
[spell+0x34] is a constant set in TMindDecay.Create. So no gate input is
needed to compute the roll.

Behaviour vs vanilla:
  * Eligible targets: byte-for-byte identical outcome and identical draw order.
  * Ineligible targets: one extra @RandInt is consumed and discarded --
    UNIFORMLY on every machine (same DLL), so determinism is preserved
    exactly as FIX #8 preserved it. No balance effect (the stream is random).
  * BONUS: adds the nil check vanilla lacks. Vanilla dereferences
    `[target+0x4C]` at 0x557F862C guarded only by IsClass(TCombatUnit) --
    a combat unit with no strategic unit would access-violate. Now it simply
    falls through to "ineligible".

⚠ HONEST SCOPE: this removes the one concrete, mechanically-verifiable RNG
asymmetry unique to Mind Decay. The gates read synced state, so on two
correctly-synced machines they SHOULD already agree -- meaning this is
hardening that stops a divergence from cascading, not a proven root-cause fix.
It cannot make things worse (uniform on both sides), and it fixes a real
crash risk on the way.

================================== PATCH ===================================
Hook 5 bytes @**0x557F861B** (the first gate, also the `je` target from
0x557F8613) -> `jmp cave`; the 3 orphaned bytes are NOP'd. Cave @**0x55815120**
(verified zero-filled, reloc-free; the next free AoWEPACK cave per
[[aowx-project-overview]]).

⚠ **RELOC**: the displaced `mov edx,[0x55715A54]` carries a base relocation on
its imm32 at **0x557F861F**, which lands INSIDE our 5-byte jmp. Left alone the
loader would apply the fixup on top of our rel32 on any rebased load -- the
exact crash [[patching-over-relocs-gotcha]] documents. The script neutralises
that entry (type 3 -> 0) on apply and restores it on revert.

AoWEPACK REBASES, so the cave is PIC: `call $+5; pop; sub <anchor>` gives the
load delta (kept in a stack slot), and both class references are addressed as
`[delta + <preferred VA>]`. All calls/jumps are rel32 (same image).

Usage: dry run default; --apply; --revert (surgical).
"""
import os
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.environ.get("AOW_GAME_DIR") or os.path.dirname(HERE)
DLL = os.path.join(GAME, "AoWEPACK.dll")
BAK = DLL + ".bak_minddecayoos"

IB = 0x55700000
D = 0x55700C00

HOOK = 0x557F861B
ORIG = bytes.fromhex("8bc38b15545a7155")     # mov eax,ebx / mov edx,[TCombatUnit]
RELOC_VA = 0x557F861F                        # imm32 of the displaced mov
TAIL = 0x557F868F                            # common tail: mov eax,esi / pops / ret 4

CAVE = 0x55815120
CAVE_LIMIT = 0x55815240

CLS_COMBATUNIT = 0x55715A54                  # -> AoWE..TCombatUnit
CLS_LEADER = 0x557121F8                      # -> AoWE..TLeader
ISCLASS = 0x557010C0                         # VCL30 System.@IsClass
HITROLE = 0x55725D98                         # AoWE.HitRole
ANIMATED = 0x81                              # PassiveAb.TAnimatedAbility

SRC = """
    sub  esp, 8
    call _anchor
_anchor:
    pop  eax
    sub  eax, {anchor:#x}
    mov  dword ptr [esp], eax
    mov  dword ptr [esp + 4], 0

    mov  eax, ebx
    mov  edx, dword ptr [esp]
    mov  edx, dword ptr [edx + {clsunit:#x}]
    call {isclass:#x}
    test al, al
    je   _roll

    mov  eax, dword ptr [ebx + 0x4C]
    test eax, eax
    je   _roll
    mov  edx, dword ptr [eax]
    call dword ptr [edx + 0x114]
    cmp  al, 2
    je   _roll

    mov  eax, dword ptr [ebx + 0x4C]
    mov  edx, dword ptr [eax]
    call dword ptr [edx + 0xA4]
    movsx eax, al
    cmp  ax, 0xB
    je   _roll

    mov  eax, dword ptr [ebx + 0x4C]
    mov  edx, {animated:#x}
    mov  ecx, dword ptr [eax]
    call dword ptr [ecx + 0x148]
    test al, al
    jne  _roll

    mov  eax, dword ptr [ebx + 0x4C]
    mov  edx, dword ptr [esp]
    mov  edx, dword ptr [edx + {clsleader:#x}]
    call {isclass:#x}
    test al, al
    jne  _roll

    mov  dword ptr [esp + 4], 1

_roll:
    mov  eax, ebx
    mov  edx, dword ptr [eax]
    call dword ptr [edx + 0x74]
    movsx eax, al
    push eax
    movsx eax, byte ptr [edi + 0x34]
    pop  edx
    sub  eax, edx
    call {hitrole:#x}
    cmp  dword ptr [esp + 4], 0
    je   _out
    mov  byte ptr [esi + 0x14], al
_out:
    add  esp, 8
    jmp  {tail:#x}
"""


def build():
    """keystone HANGS on ';' comments in this project -- source is comment-free."""
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    anchor = CAVE + 8                     # sub esp,8 (3) + call rel32 (5)
    for _ in range(6):
        src = SRC.format(anchor=anchor, clsunit=CLS_COMBATUNIT, clsleader=CLS_LEADER,
                         isclass=ISCLASS, hitrole=HITROLE, tail=TAIL,
                         animated=ANIMATED)
        code = bytes(ks.asm(src, CAVE)[0])
        i = code.find(b"\xE8\x00\x00\x00\x00")
        assert i != -1 and code[i + 5] == 0x58, "anchor idiom (call $+5 / pop eax) missing"
        real = CAVE + i + 5
        if real == anchor:
            return code
        anchor = real
    raise AssertionError("anchor did not converge")


def relocs(d):
    """Yield (file_offset_of_entry, va) for every type-3 reloc."""
    secs = {}
    e = struct.unpack_from("<I", d, 0x3C)[0]
    n = struct.unpack_from("<H", d, e + 6)[0]
    opt = struct.unpack_from("<H", d, e + 20)[0]
    tbl = e + 24 + opt
    for i in range(n):
        b = tbl + i * 40
        nm = d[b:b + 8].rstrip(b"\0").decode()
        vsz, va, rsz, raw = struct.unpack_from("<IIII", d, b + 8)
        secs[nm] = (IB + va, max(vsz, rsz), raw, rsz)
    base, _, raw, rsz = secs[".reloc"]
    off, end = raw, raw + rsz
    while off < end - 8:
        page, size = struct.unpack_from("<II", d, off)
        if size < 8 or size > 0x1000:
            break
        for i in range(off + 8, off + size, 2):
            w = struct.unpack_from("<H", d, i)[0]
            if w >> 12 == 3:
                yield i, IB + page + (w & 0xFFF)
        off += size


def main():
    do_apply = "--apply" in sys.argv
    revert = "--revert" in sys.argv
    d = bytearray(open(DLL, "rb").read())
    code = build()
    assert CAVE + len(code) <= CAVE_LIMIT, "cave overflow: %d B" % len(code)
    hook = b"\xE9" + struct.pack("<i", CAVE - (HOOK + 5)) + b"\x90\x90\x90"

    cur = bytes(d[HOOK - D:HOOK - D + 8])
    st = "original" if cur == ORIG else "applied" if cur == hook else "FOREIGN"
    print("  gate hook @0x%08X  %s  (%s)" % (HOOK, st, cur.hex()))
    print("  cave      @0x%08X  %d B" % (CAVE, len(code)))

    ent = [(i, va) for i, va in relocs(d) if va == RELOC_VA]
    print("  reloc @0x%08X  %s" % (RELOC_VA, "PRESENT (type 3)" if ent else
                                   "absent (already neutralised)"))
    if st == "FOREIGN":
        print("FOREIGN bytes (expected %s) - refusing" % ORIG.hex())
        return 1

    if revert:
        if st == "original":
            print("already vanilla")
            return 0
        d[HOOK - D:HOOK - D + 8] = ORIG
        d[CAVE - D:CAVE_LIMIT - D] = bytes(CAVE_LIMIT - CAVE)
        # restore the neutralised reloc (type 0 -> 3) at that VA.
        # RELOC_VA is not page-aligned, so a zero-offset padding entry can
        # never collide with it.
        for i, va in [(i, v) for i, v in _all_entries(d) if v == RELOC_VA]:
            w = struct.unpack_from("<H", d, i)[0]
            if w >> 12 == 0:
                struct.pack_into("<H", d, i, (3 << 12) | (w & 0xFFF))
                print("  reloc restored (type 0 -> 3)")
        open(DLL, "wb").write(bytes(d))
        print("reverted: Mind Decay rolls exactly as vanilla again")
        return 0

    if st == "applied" and bytes(d[CAVE - D:CAVE - D + len(code)]) == code and not ent:
        print("already applied")
        return 0

    if not do_apply:
        try:
            from capstone import Cs, CS_ARCH_X86, CS_MODE_32
            print("  ---- cave ----")
            for i in Cs(CS_ARCH_X86, CS_MODE_32).disasm(code, CAVE):
                print("    %08X  %-7s %s" % (i.address, i.mnemonic, i.op_str))
        except ImportError:
            pass
        print("  hook: %s -> %s" % (ORIG.hex(), hook.hex()))
        print("dry run (--apply / --revert)")
        return 0

    if not os.path.isfile(BAK):
        shutil.copy2(DLL, BAK)
        print("  backed up -> %s" % os.path.basename(BAK))
    d[CAVE - D:CAVE_LIMIT - D] = bytes(CAVE_LIMIT - CAVE)
    d[CAVE - D:CAVE - D + len(code)] = code
    d[HOOK - D:HOOK - D + 8] = hook
    for i, va in ent:
        w = struct.unpack_from("<H", d, i)[0]
        struct.pack_into("<H", d, i, w & 0x0FFF)          # type 3 -> 0 (skip)
        print("  reloc @0x%08X neutralised (type 3 -> 0)" % va)
    try:
        open(DLL, "wb").write(bytes(d))
    except PermissionError:
        print("LOCKED - close AoWx.exe and retry")
        return 1
    print("APPLIED - Mind Decay now consumes exactly one combat RNG draw "
          "whether or not the target is eligible. Test: cast it on a normal "
          "unit (should mind-control exactly as before) and on an Animated / "
          "Leader target (should still fail, no crash).")
    return 0


def _all_entries(d):
    """Every reloc entry regardless of type (needed to restore a neutralised one)."""
    e = struct.unpack_from("<I", d, 0x3C)[0]
    n = struct.unpack_from("<H", d, e + 6)[0]
    opt = struct.unpack_from("<H", d, e + 20)[0]
    tbl = e + 24 + opt
    raw = rsz = None
    for i in range(n):
        b = tbl + i * 40
        if d[b:b + 8].rstrip(b"\0") == b".reloc":
            _vsz, _va, rsz, raw = struct.unpack_from("<IIII", d, b + 8)
    off, end = raw, raw + rsz
    while off < end - 8:
        page, size = struct.unpack_from("<II", d, off)
        if size < 8 or size > 0x1000:
            break
        for i in range(off + 8, off + size, 2):
            w = struct.unpack_from("<H", d, i)[0]
            yield i, IB + page + (w & 0xFFF)
        off += size


if __name__ == "__main__":
    sys.exit(main())
