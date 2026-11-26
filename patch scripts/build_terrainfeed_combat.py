#!/usr/bin/env python3
r"""AoWx -- elemental terrain feeding in TACTICAL and AUTO combat.

Companion to build_terrainfeed.py (strategic walking heal). User spec
2026-08-30:
  TACTICAL: +1 HP per combat-map hex of home terrain the elemental enters
            (lava -> 0xE2/0xE4, water 0/0xA -> 0xE3, dirt 0xC -> 0xE1).
  AUTOCOMBAT: no real movement, so per combat ROUND every living
            fast-combat elemental whose home terrain matches the BATTLE HEX
            (the defender's hex) heals map.Random(6)+1 -- the user's 1..6
            roll, drawn from the MP-lockstep RNG (fast combat executes in
            the synchronized TE context).

TACTICAL (AoWTCPCK.dll, PIC -- the package always rebases since its
preferred base 0x400000 is the exe's):
  Hook TTacticalCombatUnit.MovedTo @0x41CF88 (6B prologue, replayed; resume
  0x41CF8E). EAX=self. Unit's hex: [tcu+0x60]=its HS, [hs+4]=the combat map
  field -- combat fields share the HSEngine TMapField base, terrain byte at
  [field+0x14]. Strategic unit at [tcu+0x4C] (TCombatUnit base field) for
  the resource-index identity. Heal via the unit's OWN vmt+0x88/+0x8C
  (TTacticalCombatUnit forwards them to AoWEPACK TCombatUnit @0x55725064/
  0x5572507C, which forward to the STRATEGIC unit's clamped SetHitPoints --
  verified). Only register-relative/virtual calls: fully PIC.

AUTOCOMBAT (AoWEPACK.dll):
  Hook TFastCombat.ExecuteCombatRound @0x5574482C (6B prologue, replayed;
  resume 0x55744832). EAX=self; [self+0xC]=TCombatData; battle hex =
  data+8/+0xC/+0x10 (the defender hex; proven by the defender-retaliation
  caves) -> GetFieldXYL thunk 0x557020FC called POSITIONALLY exactly as the
  retaliation cave does: eax=[map]+0x10, edx=[triple+0], ecx=[triple+4],
  push [triple+8]. (⚠ v1 permuted these by guessing semantic x/y/level
  roles -> GetFieldXYL returned garbage -> AV @0x558141F3 reading the
  terrain byte, user-hit on first water autocombat. Copy proven call
  sequences positionally, never by inferred parameter names.)
  RNG (v3): the 1..6 roll uses System.@RandInt @0x55701080 -- the COMBAT
  RNG stream every combat die (HitRole etc.) uses, deterministic across
  peers because RandSeed is installed from synced state at combat start.
  (⚠ v2 used map.Random behind a GetSynchronised guard: fast combat runs
  with GetSynchronised FALSE -- combat never touches the map RNG -- so the
  guard skipped ALL healing, the user's "doesn't heal" symptom. Combat-side
  randomness must come from the combat stream, never map.Random.)
  Predictor simulations run the same code harmlessly: their [+0x4C] units
  are prediction twins, and modelling the heal makes predictions accurate.
  CURSED (v3): units with the Cursed debuff (0x5D) enabled heal nothing --
  all three heal paths (strategic, tactical, autocombat) check it. Walk the object list (GetCount 0x55728BEC /
  GetObjects 0x55728BF8), filter IsClass TFastCombatUnit (VMT 0x5571D4BC via
  the call/pop anchor -- ⚠ walls alias +0x4C, the classic trap), skip dead
  ([obj+0x47]&1), match [obj+0x4C] strategic's index, heal the STRATEGIC
  unit (+0xE0 get / +0xE4 set, clamps; fast-combat HP reads forward to the
  strategic unit, so the ongoing sim sees the heal immediately).

Both hook sites byte-verified vanilla; reloc-scanned. Anchor scheme: pop the
RUNTIME anchor, displacements = target - anchor (never a sub -- see the
raiseterrain-matrix scheme-mixing postmortem).

Usage: dry run default; --apply; --revert (surgical). Patches BOTH dlls.
"""
import os
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.environ.get("AOW_GAME_DIR") or os.path.dirname(HERE)
DLL = os.path.join(GAME, "AoWEPACK.dll")
TCP = os.path.join(GAME, "AoWTCPCK.dll")
BAK_DLL = DLL + ".bak_tfcombat"
BAK_TCP = TCP + ".bak_tfcombat"

D = 0x55700C00
TD = 0x400C00

# tactical (TCPCK)
TC_HOOK = 0x41CF88
TC_ORIG = bytes.fromhex("558bec83c4f4")
TC_RESUME = 0x41CF8E
TC_CAVE = 0x438A00
TC_CAVE_HI = 0x438AC0

# autocombat (AoWEPACK). v4: hook the ROUND LOOP's ValidateWallBreaching
# call inside TFastCombat.Execute -- every round passes here exactly once.
# (⚠ v3 hooked TFastCombat.ExecuteCombatRound @0x5574482C, which the round
# loop only calls when wall-breaching VALIDATES; ordinary open-field rounds
# take the 0x557274B8 branch, so the heal never ran -- the user's "heals at
# end of combat" was actually the strategic walk-on heal after victory.)
FC_HOOK = 0x55744A5E                 # in-loop `call ValidateWallBreaching`
FC_ORIG = b"\xE8" + struct.pack("<i", 0x5574480C - (0x55744A5E + 5))
FC_RESUME = 0x55744A63
VALIDATE_WB = 0x5574480C
FC_CAVE = 0x55814500          # v5 re-homed (grew past the old slot)
FC_CAVE_HI = 0x55814700
GETCOUNT = 0x55728BEC
GETOBJS = 0x55728BF8
ISCLASS = 0x557010C0
FCU_VMT = 0x5571D4BC
GETFIELDXYL = 0x557020FC
RANDINT = 0x55701080          # System.@RandInt thunk (eax=N -> 0..N-1): the
                              # COMBAT RNG stream every combat die uses --
                              # deterministic across peers (RandSeed is
                              # installed from synced state at combat start)
MAPPTR = 0x558E9494
# v6: heal delivered AS A RECORDED COMBAT ACTION so autocombat REPLAYS show
# it. Fast combat is an action-stream architecture: every effect is a
# TCombatAction that AddAction @0x55727224 RECORDS into the replay stream
# (when [combat+8]&4) and then EXECUTES ([action vmt+0x50]); the replay
# viewer (TCPCK TTacticalCombat) deserializes and re-executes the stream.
# v5 healed by poking strategic HP directly -- invisible to the stream, so
# replays diverged: the healed unit appeared to die in the replay yet kept
# acting and "resurrected" (user-observed). v6 emits a THealingCA per heal,
# marked with flag bit 0x80 in the serialized flags byte +0xC (vanilla only
# uses bit 0), amount stored in +0xD (the healer-id byte -- unused by our
# branch), target combat-unit id in +0xE. A 7-byte hook at THealingCA.
# Execute handles marked actions: resolve unit by id (GetObjectByID
# 0x55728C68 on [combat+0xC]), heal via the COMBAT unit's own vmt+0x88/+0x8C
# (valid for both TFastCombatUnit live and TTacticalCombatUnit in replays,
# both forward to clamped strategic SetHitPoints). The amount is SERIALIZED,
# so replays reproduce the exact heals without consuming replay RNG.
CA_HOLDER = 0x5572147C        # THealingCA classref (vmtSelfPtr slot, VMT-0x40)
CA_CREATE = 0x557298B4        # TCombatAction.Create (eax=classref, dl=1, ecx=0)
ADDACTION = 0x55727224        # (eax=combat, edx=action) record + execute
GETOBJBYID = 0x55728C68       # (eax=data, dl=id) -> combat unit
HEALCA_EXEC = 0x5576BCE0      # THealingCA.Execute (vmt+0x50)
HEALCA_ORIG = bytes.fromhex("5356578bf28bd8")   # push ebx/esi/edi; mov esi,edx; mov ebx,eax
HEALCA_RESUME = 0x5576BCE7
EX_CAVE = 0x55814700
EX_CAVE_HI = 0x55814780
PH_MAP, PH_VMT, PH_CA = 0x11111111, 0x22222222, 0x33333333

LAVA_PAIR, WATER_PAIR, DIRT_PAIR = 0x00E400E2, 0x00E300E3, 0x00E100E1


def asm(src, addr):
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    src = "\n".join(ln.split(";")[0] for ln in src.splitlines())
    code, _ = Ks(KS_ARCH_X86, KS_MODE_32).asm(src, addr)
    return bytearray(code)


def rel(src, dst):
    return struct.pack("<i", dst - (src + 5))


def make_tc():
    src = f"""
        pushad
        mov  ebx, eax
        mov  eax, [ebx+0x60]
        test eax, eax
        jz   _out
        mov  esi, [eax+4]
        test esi, esi
        jz   _out
        mov  al, [esi+0x14]
        cmp  al, 9
        je   _l
        cmp  al, 0
        je   _w
        cmp  al, 0xA
        je   _w
        cmp  al, 0xC
        je   _d
        jmp  _out
    _l:
        mov  edi, 0x{LAVA_PAIR:X}
        jmp  _id
    _w:
        mov  edi, 0x{WATER_PAIR:X}
        jmp  _id
    _d:
        mov  edi, 0x{DIRT_PAIR:X}
    _id:
        mov  ecx, [ebx+0x4C]
        test ecx, ecx
        jz   _out
        mov  edx, [ecx+0x40]
        test edx, edx
        jz   _out
        mov  eax, [edx+4]
        mov  ecx, [eax]
        call dword ptr [ecx+0x84]
        movzx ecx, di
        cmp  eax, ecx
        je   _heal
        shr  edi, 16
        cmp  eax, edi
        jne  _out
    _heal:
        mov  ecx, [ebx+0x4C]
        mov  edx, 0x5D
        mov  eax, ecx
        mov  ecx, [eax]
        call dword ptr [ecx+0x148]
        test al, al
        jnz  _out
        mov  eax, ebx
        mov  edx, [eax]
        call dword ptr [edx+0x88]
        movzx edx, al
        inc  edx
        mov  eax, ebx
        mov  ecx, [eax]
        call dword ptr [ecx+0x8C]
    _out:
        popad
        push ebp
        mov  ebp, esp
        add  esp, -0xC
        jmp  0x{TC_RESUME:X}
    """
    return bytes(asm(src, TC_CAVE))


def make_fc():
    # v5: per-SIDE hex (attacker units read the attacker hex data+0x14/18/1C,
    # defender units the defender hex data+8/C/10; side byte = [obj+0x45],
    # 0 = attacker per the TCAI RE), HP==0 guard (fast combat kills by HP
    # without reliably setting the dead bit -- healing an HP-0 twin
    # RESURRECTED it, user-hit), Cursed gate, roll 1..4 off the combat RNG.
    src = f"""
        pushad
        mov  ebx, [eax+0xC]
        test ebx, ebx
        jz   _out0
        call _a
    _a:
        pop  ebp
        push eax
        mov  eax, [ebp + 0x{PH_MAP:X}]
        mov  eax, [eax]
        mov  eax, [eax+0x10]
        mov  edx, [ebx+8]
        mov  ecx, [ebx+0xC]
        push dword ptr [ebx+0x10]
        call 0x{GETFIELDXYL:X}
        call _t2p
        push edi
        mov  eax, [ebp + 0x{PH_MAP:X}]
        mov  eax, [eax]
        mov  eax, [eax+0x10]
        mov  edx, [ebx+0x14]
        mov  ecx, [ebx+0x18]
        push dword ptr [ebx+0x1C]
        call 0x{GETFIELDXYL:X}
        call _t2p
        push edi
        mov  eax, [esp]
        or   eax, [esp+4]
        jz   _out2
        mov  eax, ebx
        call 0x{GETCOUNT:X}
        mov  esi, eax
    _loop:
        dec  esi
        js   _out2
        mov  eax, ebx
        mov  edx, esi
        call 0x{GETOBJS:X}
        test eax, eax
        jz   _loop
        push eax
        lea  edx, [ebp + 0x{PH_VMT:X}]
        call 0x{ISCLASS:X}
        test al, al
        jz   _next
        mov  ecx, [esp]
        test byte ptr [ecx+0x47], 1
        jnz  _next
        mov  ecx, [ecx+0x4C]
        test ecx, ecx
        jz   _next
        push ecx
        mov  eax, ecx
        mov  edx, [eax]
        call dword ptr [edx+0xE0]
        test al, al
        jz   _nextpop
        mov  ecx, [esp]
        mov  edx, [ecx+0x40]
        test edx, edx
        jz   _nextpop
        mov  eax, [edx+4]
        mov  ecx, [eax]
        call dword ptr [ecx+0x84]
        mov  ecx, [esp+4]
        movzx ecx, byte ptr [ecx+0x45]
        test ecx, ecx
        jz   _att
        mov  edi, [esp+0xC]
        jmp  _havep
    _att:
        mov  edi, [esp+8]
    _havep:
        test edi, edi
        jz   _nextpop
        movzx ecx, di
        cmp  eax, ecx
        je   _cursed
        mov  ecx, edi
        shr  ecx, 16
        cmp  eax, ecx
        jne  _nextpop
    _cursed:
        mov  ecx, [esp]
        mov  edx, 0x5D
        mov  eax, ecx
        mov  ecx, [eax]
        call dword ptr [ecx+0x148]
        test al, al
        jnz  _nextpop
        mov  eax, 2
        call 0x{RANDINT:X}
        inc  eax
        mov  edi, eax
        xor  ecx, ecx
        mov  dl, 1
        mov  eax, [ebp + 0x{PH_CA:X}]
        call 0x{CA_CREATE:X}
        mov  byte ptr [eax+0xC], 0x80
        mov  ecx, edi
        mov  [eax+0xD], cl
        mov  ecx, [esp+4]
        mov  cl, [ecx+0xC]
        mov  [eax+0xE], cl
        push eax
        mov  edx, eax
        mov  eax, [esp+0x14]
        call 0x{ADDACTION:X}
        pop  eax
        mov  edx, [eax]
        call dword ptr [edx+0x2C]
        pop  eax
        pop  ecx
        jmp  _loop
    _nextpop:
        pop  ecx
    _next:
        pop  ecx
        jmp  _loop
    _out2:
        add  esp, 0xC
    _out0:
        popad
        call 0x{VALIDATE_WB:X}
        jmp  0x{FC_RESUME:X}
    _t2p:
        test eax, eax
        jz   _t0
        mov  al, [eax+0x14]
        cmp  al, 9
        je   _tl
        cmp  al, 0
        je   _tw
        cmp  al, 0xA
        je   _tw
        cmp  al, 0xC
        je   _td
    _t0:
        xor  edi, edi
        ret
    _tl:
        mov  edi, 0x{LAVA_PAIR:X}
        ret
    _tw:
        mov  edi, 0x{WATER_PAIR:X}
        ret
    _td:
        mov  edi, 0x{DIRT_PAIR:X}
        ret
    """
    code = asm(src, FC_CAVE)
    i = next(k for k in range(len(code) - 5)
             if code[k] == 0xE8 and code[k + 1:k + 5] == b"\x00\x00\x00\x00"
             and code[k + 5] == 0x5D)                 # pop ebp
    anchor = FC_CAVE + i + 5
    for ph, tgt in ((PH_MAP, MAPPTR), (PH_VMT, FCU_VMT), (PH_CA, CA_HOLDER)):
        while True:
            j = code.find(struct.pack("<I", ph))
            if j == -1:
                break
            code[j:j + 4] = struct.pack("<i", tgt - anchor)
    return bytes(code)


def make_ex():
    # THealingCA.Execute hook: marked (bit 0x80) actions are our terrain
    # heals -- resolve target by id and heal by the stored amount; anything
    # else falls through to the vanilla Healing-ability path. Fully PIC
    # (rel32 + register/virtual calls only). Runs identically in the live
    # fast-combat sim and in the replay viewer.
    src = f"""
        test byte ptr [eax+0xC], 0x80
        jz   _v
        push ebx
        push esi
        mov  ebx, eax
        mov  eax, [edx+0xC]
        xor  edx, edx
        mov  dl, [ebx+0xE]
        call 0x{GETOBJBYID:X}
        test eax, eax
        jz   _d
        test byte ptr [eax+0x47], 1
        jnz  _d
        mov  esi, eax
        mov  edx, [eax]
        call dword ptr [edx+0x88]
        test al, al
        jz   _d
        movzx edx, al
        movzx ecx, byte ptr [ebx+0xD]
        add  edx, ecx
        mov  eax, esi
        mov  ecx, [eax]
        call dword ptr [ecx+0x8C]
    _d:
        pop  esi
        pop  ebx
        ret
    _v:
        push ebx
        push esi
        push edi
        mov  esi, edx
        mov  ebx, eax
        jmp  0x{HEALCA_RESUME:X}
    """
    return bytes(asm(src, EX_CAVE))


def main():
    apply = "--apply" in sys.argv
    revert = "--revert" in sys.argv
    d = bytearray(open(DLL, "rb").read())
    t = bytearray(open(TCP, "rb").read())
    tc, fc, ex = make_tc(), make_fc(), make_ex()
    assert TC_CAVE + len(tc) <= TC_CAVE_HI, len(tc)
    assert FC_CAVE + len(fc) <= FC_CAVE_HI, len(fc)
    assert EX_CAVE + len(ex) <= EX_CAVE_HI, len(ex)
    tc_hook = b"\xE9" + rel(TC_HOOK, TC_CAVE) + b"\x90"
    fc_hook = b"\xE9" + rel(FC_HOOK, FC_CAVE)
    ex_hook = b"\xE9" + rel(HEALCA_EXEC, EX_CAVE) + b"\x90\x90"
    dll_edits = [(FC_CAVE, bytes(len(fc)), fc, "cave_fcheal (autocombat)"),
                 (EX_CAVE, bytes(len(ex)), ex, "cave_healca_exec"),
                 (FC_HOOK, FC_ORIG, fc_hook, "ExecuteCombatRound hook"),
                 (HEALCA_EXEC, HEALCA_ORIG, ex_hook, "THealingCA.Execute hook")]
    tcp_edits = [(TC_CAVE, bytes(len(tc)), tc, "cave_tcheal (tactical)"),
                 (TC_HOOK, TC_ORIG, tc_hook, "TacticalCombatUnit.MovedTo hook")]

    states = []
    for buf, delta, edits in ((d, D, dll_edits), (t, TD, tcp_edits)):
        for va, ob, nb, nm in edits:
            c = bytes(buf[va - delta:va - delta + len(nb)])
            st = "original" if c == ob else "applied" if c == nb else "FOREIGN"
            states.append(st)
            print("  %-34s @0x%08X  %s (%d B)" % (nm, va, st, len(nb)))
    if "FOREIGN" in states:
        print("FOREIGN - refusing")
        return 1
    if revert:
        for buf, delta, edits in ((d, D, dll_edits), (t, TD, tcp_edits)):
            for va, ob, nb, _ in edits:
                buf[va - delta:va - delta + len(nb)] = ob
        open(DLL, "wb").write(bytes(d))
        open(TCP, "wb").write(bytes(t))
        print("reverted both dlls")
        return 0
    if not apply:
        print("dry run (--apply / --revert)")
        return 0
    if all(s == "applied" for s in states):
        print("already applied")
        return 0
    for p, bak in ((DLL, BAK_DLL), (TCP, BAK_TCP)):
        if not os.path.isfile(bak):
            shutil.copy2(p, bak)
            print("backed up", os.path.basename(p))
    for buf, delta, edits in ((d, D, dll_edits), (t, TD, tcp_edits)):
        for va, ob, nb, _ in edits:
            buf[va - delta:va - delta + len(nb)] = nb
    open(DLL, "wb").write(bytes(d))
    open(TCP, "wb").write(bytes(t))
    print("APPLIED - test: TACTICAL: elemental walking combat-map lava/water/"
          "dirt tiles gains +1 per hex; AUTOCOMBAT on a lava/water/dirt hex: "
          "matching elementals emerge healthier (1-6/round); non-elementals "
          "and mismatched terrain unchanged; sieges (walls present) don't "
          "crash autocombat")
    return 0


if __name__ == "__main__":
    sys.exit(main())
