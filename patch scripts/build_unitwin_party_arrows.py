#!/usr/bin/env python3
r"""AoWx -- unit window: party cycle arrows in EVERY entry path.

USER REPORT 2026-08-31: opening a hero's unit window from the party side
window shows the little prev/next arrows under the unit portrait (cycle
through the party).  Opening the SAME window from the events-window portrait,
or from the "items found" pickup dialog, shows no arrows.  Wanted: arrows in
those paths too.

============================== RE (this session) =============================
The window is `TUnitWindow` (AoWx.exe, DFM @file 0x1E995C).  The arrows are
two TAOWButtons on UnitMainPnl:
      PNext  = [self+0x210]   OnClick TUnitWindow.PNextClick @0x0040AC9C
      PPrev  = [self+0x214]   OnClick TUnitWindow.PPrevClick @0x0040ABF0
Neither is Visible=False in the DFM, so they are hidden at RUNTIME.

Every entry path funnels through ONE refresh routine, `UpdateUnitWindow`
@0x00407DB8 (15 callers: TControlWin.Unit1FrameMouseDown = the party window,
TItemsFoundDlg.PickupBtnClick = item pickup, TArmyInfoDlg/THeroInfoDlg/
TPInfoW/TRealmWin/TMapEvents/... = the event + info portraits).  Inside it,
0x00407E52..0x00407EAC decides the arrows:

    [[0x45EBDC]] (AoWTC.AoWCombatMap) <> nil        -> hide   (tactical combat)
    [G+0xA4] == nil                                 -> hide
    TGeneral.PartyIndexOf(G, unit) @0x454100 < 0    -> hide
    [G+0x88] (party slot 1) <= -1                   -> hide
    else show PPrev+PNext @0x00407E8D

where `G` = [[0x0045A420]] = the **TGeneral** data module.  Its party fields
are `[G+0x84..0xA0]` = 8 slot indices (-1 = empty), `[G+0xA4]` = the TUnitList
they index, `[G+0xC0]` = the unit the window is showing.

THE CAUSE: those fields are written by exactly ONE routine --
`TMapEvents.TheMapArmySelected` @0x0044EC30 (and cleared by
TheMapArmyDeselected).  They describe the army CURRENTLY SELECTED ON THE MAP,
i.e. the bottom control bar's contents.  The party window is a view of that
selection, so its path always satisfies the test.  The events-portrait and
item-pickup paths only do `[G+0xC0] = unit` -- if no army is selected, or the
selected army is not the one this unit belongs to, every test above fails and
the arrows are hidden.  Nothing is wrong with those callers; the arrows are
simply tied to map selection rather than to the unit being displayed.

THE FIX: drive the arrows from the unit's OWN army instead.  The engine's own
idiom for that is `army := [unit+4]` guarded by `IsClass(army, TArmy)` --
verified in AoWE.TAbstractUnit.CanDisband @0x557825D7 and .GetLocation
@0x5577EDB2 ([unit+4] is TEObject.Owner, set by TEObject.SetOwner @0x55519318
which writes [obj+4]).  Units concealed from the local player are skipped with
`TArmy.GetUnitConcealedForPlayer` = **virtual slot [vmt+0xB8]** (TArmy VMT
0x557130EC) -- the very call TheMapArmySelected uses to build the slot array,
so the cycle order is identical to vanilla's.

AoWx.exe does not import the TArmy class reference, so the cave identifies the
class by walking the Delphi VMT header instead (name at [vmt-0x20], parent at
[vmt-0x18], self-pointer at [vmt-0x40] as a validity guard) looking for
"TArmy" -- equivalent to IsClass and needs no new import.

=================================== SCOPE ===================================
  * Arrows appear whenever the displayed unit's own army holds 2+ units that
    are visible to the local player -- ANY army, including enemy and
    independent stacks.
    v1 of this patch gated on ownership ([unit+0x24] == [[0x45DF7C]+0xA5]) on
    the theory that vanilla only ever showed the arrows for your own party.
    That was WRONG and the user hit it immediately: `TheMapArmySelected`
    @0x0044EC30 has no ownership test, so clicking an ENEMY stack on the map
    fills TGeneral's party slots with it and vanilla shows working arrows for
    it.  v1 left those arrows visible (the vanilla chain passes, so the
    visibility cave never runs) while the rewritten click handlers refused to
    act -- arrows present, clicks dead.  The gate is gone.
    No information leaks: the concealment filter below still runs with the
    LOCAL player's id, so units you cannot see are skipped, and browsing a
    visible enemy stack is exactly what the army-info dialog already offers.
  * The tactical-combat gate is preserved exactly (re-tested inside the cave),
    so nothing changes during combat.
  * PPrevClick/PNextClick are rewritten to step through the unit's own army.
    In the party-window case that is the same army and the same filter, so the
    behaviour there is unchanged.  The vanilla click sound (0x00455DFC with
    dl=0) is still played first.
  * Pure UI: no engine state is written except [G+0xC0] (which vanilla's own
    arrows write too).  Nothing is sent over the wire -- MP-safe.

CAVE: .xbfs @0x0060E700 (section 0x60D000-0x60F000, RWX, last vanilla byte at
0x0060E6C4).  AoWx.exe has DllCharacteristics=0 (no ASLR) and ImageBase
0x400000, so plain absolutes are used -- the same assumption the borderless
fullscreen work in this section already relies on.  All three patch sites and
the cave were verified reloc-free, and nothing branches into the displaced
bytes.

Usage: dry run default; --apply; --revert (surgical).
"""
import os
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.environ.get("AOW_GAME_DIR") or os.path.dirname(HERE)
EXE = os.path.join(GAME, "AoWx.exe")
BAK = EXE + ".bak_partyarrows"

# ---- addresses (AoWx.exe, ImageBase 0x400000, never rebased) ----
CAVE = 0x0060E700
# ⚠ Must NOT reach past our own cave: build_campaign_switch.py owns .xbfs from
# 0x0060E940 onwards, and apply/revert here zero-fill the whole [CAVE,LIMIT)
# range. Keeping the limit tight makes the two patches order-independent.
CAVE_LIMIT = 0x0060E940

HOOK_VIS = 0x00407EAD          # start of the "hide the arrows" block, 8 B
VIS_ORIG = bytes.fromhex("8b068b8014020000")      # mov eax,[esi] / mov eax,[eax+0x214]
VIS_SHOW = 0x00407E8D          # vanilla "show PPrev + PNext"
VIS_CONT = 0x00407EB5          # rest of the vanilla hide block

HOOK_PREV = 0x0040ABF0
HOOK_NEXT = 0x0040AC9C
CLICK_ORIG = bytes.fromhex("53568bf0a1")          # push ebx/push esi/mov esi,eax/mov eax,

REFRESH = 0x00407DB8           # UpdateUnitWindow(Self)
SOUND = 0x00455DFC             # TGeneral.PlayUISound(dl)
P_GENERAL = 0x0045A420         # -> &TGeneral
P_MAP = 0x0045DF7C             # -> &AoWE.AoWHSMap
P_COMBAT = 0x0045EBDC          # -> &AoWTC.AoWCombatMap

SITES = [(HOOK_VIS, VIS_ORIG, "hide-arrows block"),
         (HOOK_PREV, CLICK_ORIG, "TUnitWindow.PPrevClick"),
         (HOOK_NEXT, CLICK_ORIG, "TUnitWindow.PNextClick")]

ASM = r"""
    jmp _vis
    jmp _prev
    jmp _next

; ---------------- _armyof: eax = unit -> eax = own TArmy or 0 ----------------
_armyof:
    test eax, eax
    jz   _ao_fail
    mov  edx, dword ptr [{pmap:#x}]
    test edx, edx
    jz   _ao_fail
    mov  edx, dword ptr [edx]
    test edx, edx
    jz   _ao_fail
    mov  eax, dword ptr [eax + 4]
    test eax, eax
    jz   _ao_fail
    mov  edx, dword ptr [eax]
    test edx, edx
    jz   _ao_fail
    mov  ecx, 6
_ao_walk:
    cmp  edx, dword ptr [edx - 0x40]
    jne  _ao_fail
    push eax
    mov  eax, dword ptr [edx - 0x20]
    test eax, eax
    jz   _ao_popfail
    cmp  byte ptr [eax], 5
    jne  _ao_next
    cmp  dword ptr [eax + 1], 0x6D724154
    jne  _ao_next
    cmp  byte ptr [eax + 5], 0x79
    jne  _ao_next
    pop  eax
    ret
_ao_next:
    pop  eax
    mov  edx, dword ptr [edx - 0x18]
    test edx, edx
    jz   _ao_fail
    dec  ecx
    jnz  _ao_walk
    jmp  _ao_fail
_ao_popfail:
    pop  eax
_ao_fail:
    xor  eax, eax
    ret

; ------------- _viscount: eax = army -> eax = units visible to me ------------
_viscount:
    push esi
    push edi
    push ebp
    sub  esp, 8
    mov  esi, eax
    mov  dword ptr [esp], 0
    mov  dword ptr [esp + 4], 0
    mov  eax, dword ptr [esi + 8]
    test eax, eax
    jz   _vc_done
    mov  edi, dword ptr [eax + 8]
_vc_loop:
    mov  eax, dword ptr [esp]
    cmp  eax, edi
    jge  _vc_done
    mov  eax, dword ptr [{pmap:#x}]
    mov  eax, dword ptr [eax]
    mov  cl,  byte ptr [eax + 0xA5]
    mov  edx, dword ptr [esp]
    mov  eax, esi
    mov  ebp, dword ptr [eax]
    call dword ptr [ebp + 0xB8]
    test al, al
    jnz  _vc_skip
    inc  dword ptr [esp + 4]
_vc_skip:
    inc  dword ptr [esp]
    jmp  _vc_loop
_vc_done:
    mov  eax, dword ptr [esp + 4]
    add  esp, 8
    pop  ebp
    pop  edi
    pop  esi
    ret

; ------------------- visibility hook (displaced 0x407EAD) -------------------
_vis:
    push ebx
    push esi
    push edi
    mov  eax, dword ptr [{pcombat:#x}]
    test eax, eax
    jz   _vis_nocombat
    mov  eax, dword ptr [eax]
    test eax, eax
    jnz  _vis_hide
_vis_nocombat:
    mov  eax, dword ptr [{pgen:#x}]
    test eax, eax
    jz   _vis_hide
    mov  eax, dword ptr [eax]
    test eax, eax
    jz   _vis_hide
    mov  eax, dword ptr [eax + 0xC0]
    call _armyof
    test eax, eax
    jz   _vis_hide
    call _viscount
    cmp  eax, 2
    jl   _vis_hide
    pop  edi
    pop  esi
    pop  ebx
    jmp  {show:#x}
_vis_hide:
    pop  edi
    pop  esi
    pop  ebx
    mov  eax, dword ptr [esi]
    mov  eax, dword ptr [eax + 0x214]
    jmp  {cont:#x}

; ------------------------- PPrevClick / PNextClick --------------------------
_prev:
    mov  ecx, -1
    jmp  _step
_next:
    mov  ecx, 1
_step:
    push ebx
    push esi
    push edi
    push ebp
    sub  esp, 24
    mov  dword ptr [esp + 20], ecx
    mov  dword ptr [esp + 16], eax
    mov  eax, dword ptr [{pgen:#x}]
    test eax, eax
    jz   _st_done
    mov  eax, dword ptr [eax]
    test eax, eax
    jz   _st_done
    mov  ebp, eax
    xor  edx, edx
    call {sound:#x}
    mov  eax, dword ptr [ebp + 0xC0]
    test eax, eax
    jz   _st_done
    mov  esi, eax
    call _armyof
    test eax, eax
    jz   _st_done
    mov  dword ptr [esp], eax
    mov  ecx, dword ptr [eax + 8]
    test ecx, ecx
    jz   _st_done
    mov  edx, dword ptr [ecx + 8]
    mov  dword ptr [esp + 4], edx
    cmp  edx, 2
    jl   _st_done
    mov  dword ptr [esp + 12], edx
    mov  ecx, dword ptr [ecx + 4]
    test ecx, ecx
    jz   _st_done
    xor  eax, eax
_st_find:
    cmp  eax, edx
    jge  _st_done
    cmp  esi, dword ptr [ecx + eax*4]
    je   _st_found
    inc  eax
    jmp  _st_find
_st_found:
    mov  dword ptr [esp + 8], eax
_st_step:
    mov  eax, dword ptr [esp + 8]
    add  eax, dword ptr [esp + 20]
    cmp  eax, 0
    jge  _st_nowrap
    mov  eax, dword ptr [esp + 4]
    dec  eax
_st_nowrap:
    cmp  eax, dword ptr [esp + 4]
    jl   _st_ok
    xor  eax, eax
_st_ok:
    mov  dword ptr [esp + 8], eax
    mov  eax, dword ptr [{pmap:#x}]
    mov  eax, dword ptr [eax]
    mov  cl,  byte ptr [eax + 0xA5]
    mov  edx, dword ptr [esp + 8]
    mov  eax, dword ptr [esp]
    mov  edi, dword ptr [eax]
    call dword ptr [edi + 0xB8]
    test al, al
    jz   _st_gotit
    dec  dword ptr [esp + 12]
    jnz  _st_step
    jmp  _st_done
_st_gotit:
    mov  eax, dword ptr [esp]
    mov  eax, dword ptr [eax + 8]
    mov  eax, dword ptr [eax + 4]
    mov  edx, dword ptr [esp + 8]
    mov  eax, dword ptr [eax + edx*4]
    test eax, eax
    jz   _st_done
    cmp  eax, esi
    je   _st_done
    mov  dword ptr [ebp + 0xC0], eax
    mov  eax, dword ptr [esp + 16]
    call {refresh:#x}
_st_done:
    add  esp, 24
    pop  ebp
    pop  edi
    pop  esi
    pop  ebx
    ret
"""


def sections(d):
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    n = struct.unpack_from("<H", d, pe + 6)[0]
    opt = struct.unpack_from("<H", d, pe + 0x14)[0]
    out = []
    for i in range(n):
        o = pe + 0x18 + opt + i * 40
        nm = d[o:o + 8].rstrip(b"\0").decode()
        vs, va, rs, raw = struct.unpack_from("<IIII", d, o + 8)
        out.append((nm, 0x400000 + va, vs, raw, rs))
    return out


def make_va2off(d):
    secs = sections(d)

    def va2off(va):
        for nm, base, vs, raw, rs in secs:
            if base <= va < base + max(vs, rs):
                return raw + (va - base)
        raise ValueError("VA %#x not mapped" % va)
    return va2off


def build_cave():
    """Assemble the cave.

    NOTE: keystone HANGS on the `;` comment lines here, so comments are
    stripped first.  The three entry points are reached through a fixed
    3-slot jump table at the head of the cave, so the hooks never have to
    resolve a label address (keystone exposes no symbol table, and
    assembling line prefixes to measure offsets breaks on forward refs).
    """
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    src = ASM.format(pmap=P_MAP, pgen=P_GENERAL, pcombat=P_COMBAT,
                     show=VIS_SHOW, cont=VIS_CONT, sound=SOUND, refresh=REFRESH)
    lines = [ln.split(";")[0].rstrip() for ln in src.splitlines()]
    blob, _ = ks.asm("\n".join(ln for ln in lines if ln.strip()), CAVE)
    code = bytes(blob)
    for i, off in enumerate((0, 5, 10)):
        assert code[off] == 0xE9, \
            "entry slot %d is not a near jmp (%02X) - table layout shifted" % (i, code[off])
    marks = {"_vis": CAVE, "_prev": CAVE + 5, "_next": CAVE + 10}
    return code, marks


def main():
    apply = "--apply" in sys.argv
    revert = "--revert" in sys.argv
    d = bytearray(open(EXE, "rb").read())
    va2off = make_va2off(d)
    code, marks = build_cave()
    assert CAVE + len(code) <= CAVE_LIMIT, "cave overflow: %d B" % len(code)

    hooks = {
        HOOK_VIS: b"\xE9" + struct.pack("<i", marks["_vis"] - (HOOK_VIS + 5)) + b"\x90\x90\x90",
        HOOK_PREV: b"\xE9" + struct.pack("<i", marks["_prev"] - (HOOK_PREV + 5)),
        HOOK_NEXT: b"\xE9" + struct.pack("<i", marks["_next"] - (HOOK_NEXT + 5)),
    }

    states = []
    for va, orig, nm in SITES:
        cur = bytes(d[va2off(va):va2off(va) + len(orig)])
        st = "original" if cur == orig else "applied" if cur == hooks[va] else "FOREIGN"
        states.append(st)
        print("  %-24s @0x%08X  %s" % (nm, va, st))
    print("  cave                     @0x%08X  %d B  (_vis %08X _prev %08X _next %08X)"
          % (CAVE, len(code), marks["_vis"], marks["_prev"], marks["_next"]))
    if "FOREIGN" in states:
        print("FOREIGN bytes - refusing")
        return 1

    if revert:
        if not any(s == "applied" for s in states):
            print("already original")
            return 0
        for va, orig, _ in SITES:
            d[va2off(va):va2off(va) + len(orig)] = orig
        d[va2off(CAVE):va2off(CAVE_LIMIT)] = bytes(CAVE_LIMIT - CAVE)
        open(EXE, "wb").write(bytes(d))
        print("reverted (hooks restored, cave zeroed)")
        return 0

    want_region = code + bytes(CAVE_LIMIT - CAVE - len(code))
    if all(s == "applied" for s in states) and \
            bytes(d[va2off(CAVE):va2off(CAVE_LIMIT)]) == want_region:
        print("already applied")
        return 0

    if not apply:
        try:
            from capstone import Cs, CS_ARCH_X86, CS_MODE_32
            print("  ---- cave ----")
            for i in Cs(CS_ARCH_X86, CS_MODE_32).disasm(code, CAVE):
                print("    %08X  %-7s %s" % (i.address, i.mnemonic, i.op_str))
        except ImportError:
            pass
        print("dry run (--apply / --revert)")
        return 0

    if not os.path.isfile(BAK):
        shutil.copy2(EXE, BAK)
        print("  backed up -> %s" % os.path.basename(BAK))
    d[va2off(CAVE):va2off(CAVE_LIMIT)] = bytes(CAVE_LIMIT - CAVE)   # drop any older build
    d[va2off(CAVE):va2off(CAVE) + len(code)] = code
    for va, orig, _ in SITES:
        blob = hooks[va]
        assert len(blob) == len(orig), "hook/orig length mismatch at %#x" % va
        d[va2off(va):va2off(va) + len(blob)] = blob
    try:
        open(EXE, "wb").write(bytes(d))
    except PermissionError:
        print("LOCKED - close AoWx.exe and retry")
        return 1
    print("APPLIED - test: open a unit window from the EVENTS window portrait "
          "and from the ITEMS FOUND pickup dialog; the prev/next arrows under "
          "the portrait should be there and cycle that unit's own stack. They "
          "must also WORK for enemy/independent stacks (v1 regression). The "
          "party side window must behave exactly as before, and no arrows "
          "should appear in tactical combat.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
