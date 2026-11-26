#!/usr/bin/env python3
r"""AoWx -- "Fire heals Fire units", with a "+N" heal number in the popup.

ADOPTED 2026-08-30 from BXL/Ziggurat's build_firefeed.py (his RE; design doc
Fire_Heals_FireUnits_Design.md in the Ziggurat Scrolls dump). PURE fire damage
(damage-type set == exactly 0x0001) HEALS unit resource-index 0xE2 (226, Fire
Elemental) and 0xE4 (228, Fire Sprite) by the would-be damage roll, showing
"+N" in the Party-Damage popup. Mixed-type sources (fireball = fire+physical,
fire strikes) do NOT heal -- user spec 2026-08-30, satisfied by the exact-mask
gate. Covers all strategic/role fire: Firestorm, map-hex fires, Fire Barrier.
Tactical-combat fire is a separate engine path, out of scope.

Touches TWO binaries (we have no AoWCompat):
  AoWEPACK.dll : 3 caves + 3 redirects
  AoWx.exe     : 1 five-byte patch @0x436BFF (and eax,0xFF -> movsx eax,al)

MECHANISM (his, verbatim): cave_fireheal redirects ExecuteDamageRole
@0x55781AC4; for 226/228 hit by pure fire it returns the NEGATED roll -- every
fire caller does SetHP(HP-dmg), so negative heals, and TUnit.SetHitPoints
clamps to [0,max]. cave_mapfire_gate reroutes the fire-immunity pre-gate in
TArmy.TriggerFireDamage @0x5579020C so 226/228 reach the damage path (other
fire-immune units keep "immune"). cave_plusnum patches ShowDamageIcon's
IntToStr so negative values render "+" + IntToStr(-V) (embedded "+"
AnsiString via call/pop delta; rebase-safe).

AoWx DEVIATIONS from his live script (deliberate):
  * cave_mapfire_gate carries the map-fire ATK/DAM as immediates because the
    redirect kills the original body. HIS values (12/6) are Ziggurat's
    stat-doubled ones; OURS are the vanilla 6/3.
  * cave_fireheal reads resistance via vtable+0xCC (GetResistance). His live
    cave uses +0xC4, which his own 2026-08-03 Ghidra correction identifies as
    GetDefense -- looks like an unnoticed bug on his side; the vanilla
    ExecuteDamageRole body uses GetResistance.
  * caves re-homed (his 0x5580DAxx sit inside OUR RS-spawn cave).

Usage:
    py -3.10 build_firefeed.py            # dry run / verify
    py -3.10 build_firefeed.py --apply
    py -3.10 build_firefeed.py --revert   # surgical
"""
import os
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.environ.get("AOW_GAME_DIR") or os.path.dirname(HERE)
DLL = os.path.join(GAME, "AoWEPACK.dll")
EXE = os.path.join(GAME, "AoWx.exe")
BAK_DLL = DLL + ".bak_firefeed"
BAK_EXE = EXE + ".bak_firefeed"

D = 0x55700C00                       # dll: file = VA - D
XD = 0x400C00                        # exe: file = VA - XD

EXECDMGROLE, EXEC_CONT = 0x55781AC4, 0x55781ACA
EXEC_ORIG = bytes.fromhex("558bec83c4f8")
ROLL500 = 0x55725EAC
FIRE_MASK, ID_ELEM, ID_SPRT = 0x0001, 0xE2, 0xE4
SHOWDMG_INJ, SHOWDMG_CONT = 0x5575A94B, 0x5575A956
SHOWDMG_ORIG = bytes.fromhex("8d55f88b450ce8366cfaff")
INTTOSTR, LSTRCAT3 = 0x5570158C, 0x55701190
TRIG_GATE = 0x5579020C
TRIG_ORIG = bytes.fromhex("a801757066")
TRIG_ELSE, TRIG_REJOIN = 0x55790280, 0x55790228
MAPFIRE_DAM, MAPFIRE_ATK = 3, 6      # VANILLA numbers (his doubled 6/12)
EXE_SITE = 0x436BFF
EXE_ORIG = bytes.fromhex("25ff000000")   # and eax,0xFF
EXE_NEW = bytes.fromhex("0fbec09090")    # movsx eax,al + 2 nop

CAVE_A = 0x55813FA0                  # cave_fireheal
CAVE_B = 0x55814000                  # cave_plusnum
CAVE_C = 0x55814050                  # cave_mapfire_gate
CAVE_HI = 0x558140A0


def asm(src, addr):
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    src = "\n".join(ln.split(";")[0] for ln in src.splitlines())
    code, _ = Ks(KS_ARCH_X86, KS_MODE_32).asm(src, addr)
    return bytearray(code)


def rel(src, dst):
    return struct.pack("<i", dst - (src + 5))


def make_fireheal():
    src = f"""
        cmp  word ptr [esp+4], {FIRE_MASK}
        jne  _orig
        push edx
        push ecx
        push eax
        mov  edx, [eax+0x40]
        test edx, edx
        jz   _restore
        mov  ecx, [edx+4]
        mov  eax, ecx
        mov  ecx, [ecx]
        call dword ptr [ecx+0x84]
        cmp  eax, {ID_ELEM}
        je   _heal
        cmp  eax, {ID_SPRT}
        jne  _restore
    _heal:
        pop  eax
        pop  ecx
        pop  edx
        push ecx
        push edx
        mov  edx, [eax]
        call dword ptr [edx+0xcc]
        movsx eax, al
        pop  edx
        sub  edx, eax
        pop  eax
        call 0x{ROLL500:X}
        neg  eax
        ret  4
    _restore:
        pop  eax
        pop  ecx
        pop  edx
    _orig:
        push ebp
        mov  ebp, esp
        add  esp, -8
        jmp  0x{EXEC_CONT:X}
    """
    return bytes(asm(src, CAVE_A))


def make_plusnum():
    PLACEHOLDER = 0xF0F0F0F0
    src = f"""
        mov  eax, dword ptr [ebp+0xc]
        test eax, eax
        jns  _pos
        neg  eax
        lea  edx, [ebp-8]
        call 0x{INTTOSTR:X}
        call _delta
    _delta:
        pop  ecx
        lea  edx, [ecx+0x{PLACEHOLDER:X}]
        mov  ecx, dword ptr [ebp-8]
        lea  eax, [ebp-8]
        call 0x{LSTRCAT3:X}
        jmp  _done
    _pos:
        lea  edx, [ebp-8]
        mov  eax, dword ptr [ebp+0xc]
        call 0x{INTTOSTR:X}
    _done:
        jmp  0x{SHOWDMG_CONT:X}
    """
    code = asm(src, CAVE_B)
    PLUSLIT = bytes.fromhex("ffffffff01000000 2b00".replace(" ", ""))
    i_call = bytes(code).find(b"\xe8\x00\x00\x00\x00")
    assert i_call != -1 and code[i_call + 5] == 0x59
    delta_off = i_call + 5
    pluschar_off = len(code) + 8
    ph = struct.pack("<I", PLACEHOLDER)
    i_ph = bytes(code).find(b"\x8d\x91" + ph)
    assert i_ph != -1
    code[i_ph + 2:i_ph + 6] = struct.pack("<i", pluschar_off - delta_off)
    return bytes(code) + PLUSLIT


def make_mapfire():
    src = f"""
        test al, 1
        jz   _dmg
        mov  eax, [esi+0x40]
        test eax, eax
        jz   _immune
        mov  edx, eax
        mov  eax, [eax+4]
        mov  ecx, [eax]
        call dword ptr [ecx+0x84]
        cmp  eax, {ID_ELEM}
        je   _dmg
        cmp  eax, {ID_SPRT}
        je   _dmg
    _immune:
        jmp  0x{TRIG_ELSE:X}
    _dmg:
        mov  eax, 1
        push eax
        mov  ecx, {MAPFIRE_DAM}
        mov  edx, {MAPFIRE_ATK}
        mov  eax, esi
        call 0x{EXECDMGROLE:X}
        jmp  0x{TRIG_REJOIN:X}
    """
    return bytes(asm(src, CAVE_C))


def main():
    apply = "--apply" in sys.argv
    revert = "--revert" in sys.argv
    d = bytearray(open(DLL, "rb").read())
    x = bytearray(open(EXE, "rb").read())

    caveA, caveB, caveC = make_fireheal(), make_plusnum(), make_mapfire()
    assert CAVE_A + len(caveA) <= CAVE_B and CAVE_B + len(caveB) <= CAVE_C \
        and CAVE_C + len(caveC) <= CAVE_HI, (len(caveA), len(caveB), len(caveC))

    redir_exec = b"\xE9" + rel(EXECDMGROLE, CAVE_A) + b"\x90"
    redir_show = b"\xE9" + rel(SHOWDMG_INJ, CAVE_B) + b"\x90" * 6
    redir_trig = b"\xE9" + rel(TRIG_GATE, CAVE_C)

    dll_edits = [
        (CAVE_A, bytes(len(caveA)), caveA, "cave_fireheal"),
        (CAVE_B, bytes(len(caveB)), caveB, "cave_plusnum"),
        (CAVE_C, bytes(len(caveC)), caveC, "cave_mapfire_gate"),
        (EXECDMGROLE, EXEC_ORIG, redir_exec, "ExecuteDamageRole redirect"),
        (SHOWDMG_INJ, SHOWDMG_ORIG, redir_show, "ShowDamageIcon redirect"),
        (TRIG_GATE, TRIG_ORIG, redir_trig, "TriggerFireDamage gate redirect"),
    ]
    exe_edits = [(EXE_SITE, EXE_ORIG, EXE_NEW, "popup signed value (AoWx.exe)")]

    print("firefeed: pure fire heals 226/228 (+N popup); caves 0x%X..0x%X; "
          "mapfire ATK/DAM %d/%d (vanilla)"
          % (CAVE_A, CAVE_HI, MAPFIRE_ATK, MAPFIRE_DAM))
    states = []
    for buf, delta, edits in ((d, D, dll_edits), (x, XD, exe_edits)):
        for va, ob, nb, nm in edits:
            assert len(ob) == len(nb), nm
            c = bytes(buf[va - delta:va - delta + len(nb)])
            st = "original" if c == ob else "applied" if c == nb else "FOREIGN"
            states.append(st)
            print("  %-34s @0x%08X  %s" % (nm, va, st))
    if "FOREIGN" in states:
        print("FOREIGN bytes - refusing")
        return 1

    if revert:
        for buf, delta, edits in ((d, D, dll_edits), (x, XD, exe_edits)):
            for va, ob, nb, _ in edits:
                buf[va - delta:va - delta + len(nb)] = ob
        open(DLL, "wb").write(bytes(d))
        open(EXE, "wb").write(bytes(x))
        print("reverted both binaries (caves zeroed); backups untouched")
        return 0
    if not apply:
        print("dry run (--apply / --revert)")
        return 0
    if all(s == "applied" for s in states):
        print("already applied")
        return 0
    for p, bak in ((DLL, BAK_DLL), (EXE, BAK_EXE)):
        if not os.path.isfile(bak):
            shutil.copy2(p, bak)
            print("backed up", os.path.basename(p))
    for buf, delta, edits in ((d, D, dll_edits), (x, XD, exe_edits)):
        for va, ob, nb, _ in edits:
            buf[va - delta:va - delta + len(nb)] = nb
    open(DLL, "wb").write(bytes(d))
    open(EXE, "wb").write(bytes(x))
    print("APPLIED - test: damaged Fire Elemental/Sprite healed by Firestorm "
          "and by map fire / Fire Barrier, popup shows +N; fireball (mixed "
          "fire+physical) still DAMAGES them normally? (no - they are fire-"
          "immune vs mixed: unchanged vanilla behaviour); other fire-immune "
          "units still show 'immune'; normal units take normal fire damage.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
