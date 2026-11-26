#!/usr/bin/env python3
r"""GetExplored nil-guard for AoWTCPCK.dll (MP exploration-site combat).

STORY (2026-08-11):
The mod stubbed AoWTCPCK's import thunk for `AoWE.TAoWMapField.GetExplored`
to `mov eax,1; ret` ("always explored" - the defenders-act-immediately change).
Restoring the real thunk fixed "Error - TCAI: Error during Create Unit List",
but MP then produced **"Error - TCMoveToken: Error during Token"** on the
OBSERVER, freezing their combat while the explorer played on.

WHY: `CombatTE.TCombatMoveTE.DefaultMove` does, at 0x408DBF..0x408DE5:

    mov   eax,[0x469420] / mov eax,[eax] / mov eax,[eax+0x10]
    call  TMapContainer.GetField          ; -> eax = destination field  (MAY BE NIL)
    mov   edx,[0x469420] / mov edx,[edx]
    movsx edx,byte [edx+0xA5]             ; the seated (viewing) player
    call  0x40287C                        ; GetExplored(field, player)
    test  al,al / je skip-the-visual

and the REAL `TAoWMapField.GetExplored` @0x55771BF4 is
`stc; mov ecx,edx; mov edx,[eax+0x18]; rcr edx,cl; ...` - it dereferences the
field IMMEDIATELY. A nil field therefore access-violates, and DefaultMove's
try/except turns that into "Error during Token" (handler @0x408F5D). The old
always-1 stub never touched eax, which is exactly why it hid this.

FIX: keep the REAL exploration semantics, but never dereference nil.
The thunk becomes `jmp cave`; the cave is:

    test eax,eax
    jz   nil                ; nil field -> report NOT explored (conservative:
    call n / n: pop ecx     ;              the caller then just skips the visual)
    sub  ecx,<static n>     ; PIC - AoWTCPCK always rebases
    add  ecx,<&IAT slot>
    jmp  dword [ecx]        ; tail-call the real GetExplored (eax/edx untouched)
  nil:
    xor  eax,eax
    ret

Only ecx is clobbered, and the real GetExplored overwrites ecx itself, so this
is transparent to all 10 call sites (DefaultMove, TCMeleeMoveTE/
TCAbTouchMoveTE.LastMove, TCAbRangedTE.Execute, TCAI.EvalBattle,
TCombatUnitSelectionControl.ExecuteMoveSelection x3 / .UpdateMoveCursor x2).

NOTE: this restores vanilla "defenders wait until seen". Re-add the
attack-immediately behaviour separately and narrowly (per defending unit),
not by lying about exploration to all of AoWTCPCK.

Cave @0x4385C0. Backup AoWTCPCK.dll.bak_nilguard. Dry-run default;
--apply / --revert.
"""
import os, shutil, struct, sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DLL = os.path.join(GAME, "AoWTCPCK.dll")
BAK = DLL + ".bak_nilguard"

VA2FILE = 0x400C00
THUNK = 0x40287C                  # the import thunk we own
IAT_SLOT = 0x46E630               # AoWEPACK.dll!AoWE.TAoWMapField.GetExplored
CAVE, CAVE_END = 0x4385C0, 0x438620
REAL = b"\xFF\x25" + struct.pack("<I", IAT_SLOT)
STUB = bytes.fromhex("B801000000C3")


COMBATMAP_G = 0x46C064          # global -> TAoWCombatMap
M_SEATED = 0xEC                 # [combatmap+0xEC] combat seat; 0xFF = nobody


def build_cave():
    """GetExplored(eax=field, edx=player) wrapper:
         nil field            -> 0 (never deref nil - the bug the old stub hid)
         observer machine     -> 1 (see the note below)
         otherwise            -> the real answer
    OBSERVER CLAUSE: an observer has no combat seat ([combatmap+0xEC]==0xFF,
    cleared by the observer-vision cave). Returning "explored" to AoWTCPCK on
    that machine does NOT reveal anything - fog is drawn by AoWEPACK's own
    DrawFog, which calls GetExplored internally and never goes through this
    thunk. It only affects AoWTCPCK's own decisions, and the one that matters
    is the move-visual gate in TCombatMoveTE.DefaultMove (and the melee/touch/
    ranged equivalents), which is what centres the camera on a moving unit.
    Without it the observer's camera only follows units moving through tiles
    the explorer has already revealed - i.e. it never follows the defenders.
    """
    b = bytearray()
    b += bytes([0xE8, 0x00, 0x00, 0x00, 0x00])     # call next
    n_off = len(b)
    b += bytes([0x59])                             # pop ecx
    b += bytes([0x81, 0xE9]) + struct.pack("<I", CAVE + n_off)   # sub ecx,static -> delta
    b += bytes([0x51])                             # push ecx        (save delta)
    b += bytes([0x85, 0xC0])                       # test eax,eax
    jz_at = len(b) + 1
    b += bytes([0x74, 0x00])                       # jz nil
    b += bytes([0x81, 0xC1]) + struct.pack("<I", IAT_SLOT)       # add ecx,&IAT slot
    b += bytes([0xFF, 0x11])                       # call dword [ecx]  (real GetExplored)
    jmp_at = len(b) + 1
    b += bytes([0xEB, 0x00])                       # jmp chk
    nil_off = len(b)
    b += bytes([0x31, 0xC0])                       # xor eax,eax
    chk_off = len(b)
    b += bytes([0x59])                             # pop ecx         (delta)
    b += bytes([0x81, 0xC1]) + struct.pack("<I", COMBATMAP_G)    # add ecx,&global
    b += bytes([0x8B, 0x09])                       # mov ecx,[ecx]   (the combat map)
    b += bytes([0x85, 0xC9])                       # test ecx,ecx
    jz2_at = len(b) + 1
    b += bytes([0x74, 0x00])                       # jz done
    b += bytes([0x80, 0xB9]) + struct.pack("<I", M_SEATED) + bytes([0xFF])  # cmp [ecx+0xEC],0xFF
    jne_at = len(b) + 1
    b += bytes([0x75, 0x00])                       # jne done
    b += bytes([0xB0, 0x01])                       # mov al,1        (observer)
    done_off = len(b)
    b += bytes([0xC3])                             # ret
    b[jz_at] = nil_off - (jz_at + 1)
    b[jmp_at] = chk_off - (jmp_at + 1)
    b[jz2_at] = done_off - (jz2_at + 1)
    b[jne_at] = done_off - (jne_at + 1)
    for v in (b[jz_at], b[jmp_at], b[jz2_at], b[jne_at]):
        assert 0 < v < 0x7F
    return bytes(b)


def reloc_entries(data):
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    nsec = struct.unpack_from("<H", data, pe + 6)[0]
    sec0 = pe + 24 + struct.unpack_from("<H", data, pe + 20)[0]
    raw = size = None
    for i in range(nsec):
        o = sec0 + i * 40
        if data[o:o+8].rstrip(b"\0") == b".reloc":
            size, _, _, raw = struct.unpack_from("<IIII", data, o + 8)
    out, p = [], raw
    while p < raw + size:
        page, bsz = struct.unpack_from("<II", data, p)
        if bsz == 0:
            break
        for q in range(p + 8, p + bsz, 2):
            e = struct.unpack_from("<H", data, q)[0]
            out.append((q, 0x400000 + page + (e & 0xFFF), e >> 12))
        p += bsz
    return out


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--dry-run"
    if mode == "--revert":
        if not os.path.exists(BAK):
            sys.exit("no backup")
        shutil.copyfile(BAK, DLL)
        print("reverted", DLL)
        return

    data = bytearray(open(DLL, "rb").read())
    cur = bytes(data[THUNK - VA2FILE: THUNK - VA2FILE + 6])
    ours = b"\xE9" + struct.pack("<i", CAVE - (THUNK + 5)) + b"\x90"
    recave = (cur == ours)
    if recave:
        print("thunk already points at our cave - rewriting the cave in place")
    elif cur == STUB:
        print("NOTE: thunk currently holds the always-1 STUB; replacing it.")
    elif cur == REAL:
        print("thunk currently holds the real jmp [IAT]; replacing it.")
    else:
        sys.exit("unrecognised thunk: %s" % cur.hex(' '))
    if not recave:
        assert not any(data[CAVE - VA2FILE: CAVE_END - VA2FILE]), "cave not empty"

    code = build_cave()
    assert len(code) <= CAVE_END - CAVE
    hook = b"\xE9" + struct.pack("<i", CAVE - (THUNK + 5)) + b"\x90"

    rels = reloc_entries(data)
    # if the real thunk is in place its operand at THUNK+2 carries a HIGHLOW
    tgt = [(q, va, t) for q, va, t in rels if va == THUNK + 2 and t == 3]
    inside = [hex(va) for _, va, t in rels if CAVE <= va < CAVE_END and t == 3]
    assert not inside, "relocs inside cave: %s" % inside

    print("cave @ %08X (%d bytes): %s" % (CAVE, len(code), code.hex(' ')))
    print("thunk @ %08X: %s -> %s" % (THUNK, cur.hex(' '), hook.hex(' ')))
    print("reloc at THUNK+2: %s" % ("neutralise 3->0" if tgt else "none / already done"))
    if mode != "--apply":
        print("dry run OK - rerun with --apply")
        return

    if not os.path.exists(BAK):
        shutil.copyfile(DLL, BAK)
        print("backup ->", os.path.basename(BAK))
    data[CAVE - VA2FILE: CAVE - VA2FILE + len(code)] = code
    if not recave:
        data[THUNK - VA2FILE: THUNK - VA2FILE + 6] = hook
    for q, va, t in tgt:
        e = struct.unpack_from("<H", data, q)[0]
        struct.pack_into("<H", data, q, e & 0x0FFF)
    open(DLL, "wb").write(data)
    print("APPLIED - real exploration semantics, nil fields report 'not explored'.")


main()
