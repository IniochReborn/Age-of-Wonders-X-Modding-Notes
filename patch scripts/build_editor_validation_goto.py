#!/usr/bin/env python3
r"""AoWx -- editor: Map Validation entries are clickable and jump to the tile.

Double-clicking a line in the editor's Map Validation dialog centres the map
view on the object that line refers to, switching surface/underground level
first if needed.  Double-clicking an indented "  Warning: ..." detail line
walks UP to its "<Name> at location (x, y, z)" header; lines with no location
above them (player-level warnings, "Map validated successfully") do nothing.

Ported from BXL's `build_validation_goto.py` (their notes:
`reference files/new BXL/.../notes/Validation_Dialog_Clickable_Entries.md`,
confirmed working in their editor 2026-07-28).  ⚠ Per [[bxl-reference]] his
scripts are never run as-is -- his caves overlap ours and his binary is the
pre-rename `AoWDevEd.exe`.  What changed here: our file name + backup/CLI
conventions (`--revert`), our own section bookkeeping, and every address
re-verified against OUR AoWDevX.exe / AoWEPACK.dll before writing a byte.

===================== RE RE-VERIFIED AGAINST OUR BUILD ======================
AoWDevX.exe (ImageBase 0x400000, DllCharacteristics 0 -- never rebases, so
absolute refs are fine, same as `.dlgd`/`.tres` already rely on):
  * `TMainForm.ValidateMapBtnClick` @0x0042CEAC builds the dialog, and at
    0x0042CEC8 does `mov eax,[ebx+0x1DC]; mov edx,[eax+0x130]` -- confirming
    **dialog+0x1DC = the TMemo** and TCustomMemo.FLines = +0x130.  At
    **0x0042CEE2** it does `mov eax,ebx` then `call 0x4012E8` (ShowModal
    thunk, bytes E8 01 44 FD FF) -- so EAX = the dialog at the hook.
  * 0x004012E8 -> [0x4321B0] = `VCL30.dpl!Forms.TCustomForm.ShowModal`  ✓
  * 0x00402E28 -> [0x433370] = `HSEPack.dpl!HSMEdit.THSMEdit.CenterView`  ✓
  * IAT [0x00432354] = `VCL30.dpl!Controls.TControl.Perform`  ✓ (no new import)
  * MainForm instance = [[0x0042F0A8]] (-> BSS 0x004301CC); the THSMEdit map
    control = **mainform+0x22C** -- used that way by SetMapLevel itself and by
    TMainForm.GotoItemClick / GoToHeroClick / GoToLeaderClick /
    TScannerFloater.ScannerChangeTileBox / TPlayerInfoFloater.
    StructureGridDblClick, all of which call CenterView the same way.
  * `SetMapLevel` @0x00429C68 (EAX=form, EDX=level): the precedent
    `TPlayerInfoFloater.StructureGridDblClick` @0x00425BEC does exactly
    `movsx edx,al / mov eax,[[0x42F0A8]] / call 0x429C68` then CenterView --
    this patch is that same sequence with x/y/z parsed from the line text.
  * FOnDblClick TMethod layout proven from OUR VCL30
    `Controls.TControl.DblClick` @0x41342B48:
        cmp word [eax+0xAE],0 ; mov edx,eax ; mov eax,[ebx+0xB0] ;
        call [ebx+0xAC]
    => **Code = +0xAC, Data = +0xB0**, and the Assigned test only looks at the
    HIGH WORD of Code -- fine, our cave sits at 0x004Exxxx.
AoWEPACK.dll (ours, modded): `TStructure.MainValidateMap` @0x5575F4F8 and the
two-space detail prefix @0x5575F6BC (`20 20 00 00`) are intact, as are
City/Teleport/TSetupControl.ValidateMap.  The header's "(x, y, z)" group is
built at runtime by LStrCatN from GetX/GetY/GetLevel (VMT +0x74/+0x78/+0x7C),
so it is **always the last paren group** and survives dictionary translation
-- which is why the handler parses digits right-to-left instead of matching
any (translated) words.  The memo is `ScrollBars=ssBoth` => no word wrap =>
visual lines are logical lines.

================================ THE PATCH =================================
Hook: the one `call ShowModal` at 0x0042CEE2 -> our install cave, which sets
Memo.FOnDblClick and tail-jumps to the real thunk (so the dialog still shows
normally, and the event is re-armed for every freshly created dialog).

Handler (a TNotifyEvent, EDX = the memo):
  line := Perform(memo, EM_LINEFROMCHAR, -1, 0)      -- caret = clicked line
  walk upward: Perform(memo, EM_GETLINE, line, @buf) into a 256 B STACK
  buffer, scan right-to-left for '(' then parse `int , int , int )`
  (spaces optional, ints capped at 999); parse failure -> line--
  on success: sanity z <= 7, SetMapLevel(mainform, z), then
  CenterView(ctrl, x, y, z) -- which clamps to the map edges itself, so
  out-of-range coordinates are harmless.
No writable state: the line buffer is a stack frame, so the section can stay
read+execute.

============================ SAFETY / COMPAT ===============================
  * EDITOR ONLY.  AoWx.exe, AoWEPACK.dll and every gameplay path are
    untouched -- this cannot affect the game or multiplayer.
  * Read-only feature: it only moves the editor's camera.  No map data is
    written, nothing is selected or modified.
  * Every failure mode is a no-op: no location above the line, unparsable
    text, nil MainForm, or z > 7 all just return.
  * ⚠ SECTION ORDERING: the cave goes in a new `.vgo` section appended after
    `.tres`.  build_editor_timerres.py used to rebuild the file as
    `d[:raw]+body` when re-applying, which would have DESTROYED `.vgo`; that
    script now overwrites `.tres` in place instead (its body is 0x76 B in a
    0x200 B slot), so the two are order-independent.  Both scripts revert
    surgically and keep their (inert) section headers, so neither renumbers
    sections.  SizeOfImage is recomputed from the MAX end over ALL sections.

Usage: dry run default; --apply; --revert (surgical: restores the hook and
zeroes the cave, keeping the inert section header).
"""
import os
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.environ.get("AOW_GAME_DIR") or os.path.dirname(HERE)
EXE = os.path.join(GAME, "AoWDevX.exe")
BAK = EXE + ".bak_valgoto"

IMAGE_BASE = 0x400000
SECT_NAME = b".vgo\0\0\0\0"

HOOK_VA = 0x0042CEE2           # in TMainForm.ValidateMapBtnClick
SHOWMODAL_THUNK = 0x004012E8   # VCL30 Forms.TCustomForm.ShowModal thunk
ORIG_HOOK = b"\xE8" + struct.pack("<i", SHOWMODAL_THUNK - (HOOK_VA + 5))
PERFORM_IAT = 0x00432354       # VCL30 Controls.TControl.Perform
MAINFORM_GVAR = 0x0042F0A8     # -> ptr -> TMainForm
HSMEDIT_OFF = 0x22C            # TMainForm field: the THSMEdit control
SETLEVEL_FN = 0x00429C68       # TMainForm.SetMapLevel(EAX=form, EDX=level)
CENTERVIEW_THUNK = 0x00402E28  # THSMEdit.CenterView(EAX=ctrl,EDX=x,ECX=y,push lvl)
DLG_MEMO_OFF = 0x1DC
ONDBL_CODE_OFF = 0xAC
ONDBL_DATA_OFF = 0xB0
EM_GETLINE = 0xC4
EM_LINEFROMCHAR = 0xC9
MAX_COORD = 999
MAX_LEVEL = 7


def install_src(handler_va):
    return """
        push eax
        mov  eax, dword ptr [eax + {memo:#x}]
        mov  dword ptr [eax + {code:#x}], {handler:#x}
        mov  dword ptr [eax + {data:#x}], eax
        pop  eax
        jmp  {showmodal:#x}
    """.format(memo=DLG_MEMO_OFF, code=ONDBL_CODE_OFF, data=ONDBL_DATA_OFF,
               handler=handler_va, showmodal=SHOWMODAL_THUNK)


# frame: [ebp-4]=x [ebp-8]=y [ebp-0xC]=z [ebp-0x10]=len [ebp-0x14]=digits
#        [ebp-0x120 .. ebp-0x21] = 256 B line buffer (EM_GETLINE capacity 254)
HANDLER_SRC = """
        push ebp
        mov  ebp, esp
        sub  esp, 0x120
        push ebx
        push esi
        push edi
        mov  ebx, edx

        push 0
        or   ecx, -1
        mov  edx, {linefromchar:#x}
        mov  eax, ebx
        call dword ptr [{perform:#x}]
        mov  esi, eax

    lineloop:
        test esi, esi
        js   done

        mov  word ptr [ebp - 0x120], 0xFE
        lea  eax, [ebp - 0x120]
        push eax
        mov  ecx, esi
        mov  edx, {getline:#x}
        mov  eax, ebx
        call dword ptr [{perform:#x}]
        mov  dword ptr [ebp - 0x10], eax

        lea  edx, [ebp - 0x120]
        mov  ecx, eax
    findparen:
        dec  ecx
        js   nextline
        cmp  byte ptr [edx + ecx], 0x28
        jne  findparen

        lea  edi, [edx + ecx + 1]
        add  edx, dword ptr [ebp - 0x10]

        call getint
        cmp  eax, -1
        je   nextline
        mov  dword ptr [ebp - 4], eax
        mov  cl, 0x2C
        call getsym
        test eax, eax
        jnz  nextline
        call getint
        cmp  eax, -1
        je   nextline
        mov  dword ptr [ebp - 8], eax
        mov  cl, 0x2C
        call getsym
        test eax, eax
        jnz  nextline
        call getint
        cmp  eax, -1
        je   nextline
        mov  dword ptr [ebp - 0xC], eax
        mov  cl, 0x29
        call getsym
        test eax, eax
        jnz  nextline
        jmp  goto_loc

    nextline:
        dec  esi
        jmp  lineloop

    goto_loc:
        mov  eax, dword ptr [ebp - 0xC]
        cmp  eax, {maxlevel}
        ja   done
        mov  edx, eax
        mov  eax, dword ptr [{mainform:#x}]
        test eax, eax
        jz   done
        mov  eax, dword ptr [eax]
        test eax, eax
        jz   done
        call {setlevel:#x}
        mov  eax, dword ptr [{mainform:#x}]
        mov  eax, dword ptr [eax]
        test eax, eax
        jz   done
        mov  eax, dword ptr [eax + {hsmedit:#x}]
        test eax, eax
        jz   done
        push dword ptr [ebp - 0xC]
        mov  edx, dword ptr [ebp - 4]
        mov  ecx, dword ptr [ebp - 8]
        call {centerview:#x}

    done:
        pop  edi
        pop  esi
        pop  ebx
        mov  esp, ebp
        pop  ebp
        ret

    getint:
        xor  eax, eax
        mov  dword ptr [ebp - 0x14], 0
    gi_sp:
        cmp  edi, edx
        jae  gi_chk
        cmp  byte ptr [edi], 0x20
        jne  gi_dig
        inc  edi
        jmp  gi_sp
    gi_dig:
        cmp  edi, edx
        jae  gi_chk
        movzx ecx, byte ptr [edi]
        sub  ecx, 0x30
        cmp  ecx, 9
        ja   gi_chk
        imul eax, eax, 10
        add  eax, ecx
        cmp  eax, {maxcoord}
        ja   gi_fail
        inc  edi
        inc  dword ptr [ebp - 0x14]
        jmp  gi_dig
    gi_chk:
        cmp  dword ptr [ebp - 0x14], 0
        jne  gi_ok
    gi_fail:
        or   eax, -1
    gi_ok:
        ret

    getsym:
    gs_sp:
        cmp  edi, edx
        jae  gs_fail
        cmp  byte ptr [edi], 0x20
        jne  gs_chk
        inc  edi
        jmp  gs_sp
    gs_chk:
        cmp  byte ptr [edi], cl
        jne  gs_fail
        inc  edi
        xor  eax, eax
        ret
    gs_fail:
        mov  eax, 1
        ret
""".format(linefromchar=EM_LINEFROMCHAR, getline=EM_GETLINE, perform=PERFORM_IAT,
           maxlevel=MAX_LEVEL, maxcoord=MAX_COORD, mainform=MAINFORM_GVAR,
           setlevel=SETLEVEL_FN, hsmedit=HSMEDIT_OFF, centerview=CENTERVIEW_THUNK)


def asm(ks, src, va):
    """keystone (LLVM) HANGS on `;` comments in this project -- strip them."""
    clean = "\n".join(ln.split(";", 1)[0] for ln in src.splitlines())
    code, _ = ks.asm(clean, va)
    return bytes(code)


def load_pe(d):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, e + 6)[0]
    optsz = struct.unpack_from("<H", d, e + 20)[0]
    opt = e + 24
    sectbl = opt + optsz
    secs = []
    for i in range(nsec):
        b = sectbl + i * 40
        vsz, va, rsz, raw = struct.unpack_from("<IIII", d, b + 8)
        secs.append((va, vsz, raw, rsz, b))
    return dict(e=e, nsec=nsec, opt=opt, sectbl=sectbl, secs=secs,
                salign=struct.unpack_from("<I", d, opt + 32)[0],
                falign=struct.unpack_from("<I", d, opt + 36)[0],
                hdrsz=struct.unpack_from("<I", d, opt + 84)[0])


def align(x, a):
    return (x + a - 1) // a * a


def rva2off(secs, rva):
    for va0, vsz, raw, rsz, _ in secs:
        if va0 <= rva < va0 + max(vsz, rsz):
            return raw + (rva - va0)
    raise ValueError("rva %#x maps to no section" % rva)


def main():
    do_apply = "--apply" in sys.argv
    revert = "--revert" in sys.argv
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    ks = Ks(KS_ARCH_X86, KS_MODE_32)

    d = bytearray(open(EXE, "rb").read())
    F = load_pe(d)
    hook_off = rva2off(F["secs"], HOOK_VA - IMAGE_BASE)
    hook_now = bytes(d[hook_off:hook_off + 5])

    sect = None
    for s in F["secs"]:
        if bytes(d[s[4]:s[4] + 4]) == SECT_NAME[:4]:
            sect = s
    newva = sect[0] if sect else align(
        max(s[0] + max(s[1], s[3]) for s in F["secs"]), F["salign"])
    base_va = IMAGE_BASE + newva

    handler_va = base_va
    hcode = asm(ks, HANDLER_SRC, handler_va)
    install_va = base_va + align(len(hcode), 16)
    icode = asm(ks, install_src(handler_va), install_va)
    body = hcode + b"\x90" * (install_va - base_va - len(hcode)) + icode
    patched_hook = b"\xE8" + struct.pack("<i", install_va - (HOOK_VA + 5))

    st = ("original" if hook_now == ORIG_HOOK else
          "applied" if hook_now == patched_hook else "FOREIGN")
    print("  hook @0x%08X  %s  (%s)" % (HOOK_VA, st, hook_now.hex()))
    print("  .vgo  rva 0x%X -> VA 0x%08X   handler %d B @0x%08X, install %d B @0x%08X"
          % (newva, base_va, len(hcode), handler_va, len(icode), install_va))
    print("  section %s" % ("present" if sect else "will be appended"))
    if st == "FOREIGN":
        print("FOREIGN hook bytes (expected %s) - editor build differs, refusing"
              % ORIG_HOOK.hex())
        return 1

    if revert:
        if st == "original":
            print("already vanilla")
            return 0
        d[hook_off:hook_off + 5] = ORIG_HOOK
        if sect:
            va0, vsz, raw, rsz, hdr = sect
            d[raw:raw + rsz] = bytes(rsz)
            print("  .vgo body zeroed (inert section header kept)")
        open(EXE, "wb").write(bytes(d))
        print("reverted: Validate dialog entries are plain text again")
        return 0

    if st == "applied" and sect and \
            bytes(d[sect[2]:sect[2] + len(body)]) == body:
        print("already applied")
        return 0

    if not do_apply:
        try:
            from capstone import Cs, CS_ARCH_X86, CS_MODE_32
            cs = Cs(CS_ARCH_X86, CS_MODE_32)
            print("  ---- handler ----")
            for i in cs.disasm(hcode, handler_va):
                print("    %08X  %-7s %s" % (i.address, i.mnemonic, i.op_str))
            print("  ---- install ----")
            for i in cs.disasm(icode, install_va):
                print("    %08X  %-7s %s" % (i.address, i.mnemonic, i.op_str))
        except ImportError:
            pass
        print("  hook: %s -> %s" % (ORIG_HOOK.hex(), patched_hook.hex()))
        print("dry run (--apply / --revert)")
        return 0

    if not os.path.isfile(BAK):
        shutil.copy2(EXE, BAK)
        print("  backed up -> %s" % os.path.basename(BAK))

    if sect:
        va0, vsz, raw, rsz, hdr = sect
        assert len(body) <= rsz, ".vgo cave outgrew its %#x B slot" % rsz
        d[raw:raw + rsz] = bytearray(body) + bytearray(rsz - len(body))
        struct.pack_into("<II", d, hdr + 8, len(body), va0)
    else:
        assert F["sectbl"] + (F["nsec"] + 1) * 40 <= F["hdrsz"], "no header room"
        newraw = align(len(d), F["falign"])
        d += bytes(newraw - len(d))
        rawsz = align(len(body), F["falign"])
        d += body + bytes(rawsz - len(body))
        b = F["sectbl"] + F["nsec"] * 40
        struct.pack_into("<8sIIII", d, b, SECT_NAME, len(body), newva, rawsz, newraw)
        struct.pack_into("<IIHHI", d, b + 24, 0, 0, 0, 0, 0x60000020)   # code|x|r
        struct.pack_into("<H", d, F["e"] + 6, F["nsec"] + 1)
    # SizeOfImage from the MAX end over ALL sections, never just ours
    F2 = load_pe(d)
    struct.pack_into("<I", d, F2["opt"] + 56,
                     align(max(s[0] + max(s[1], s[3]) for s in F2["secs"]),
                           F2["salign"]))
    d[hook_off:hook_off + 5] = patched_hook
    try:
        open(EXE, "wb").write(bytes(d))
    except PermissionError:
        print("LOCKED - close AoWDevX.exe and retry")
        return 1
    print("APPLIED - test in the EDITOR: load a map, hit the Validate toolbar "
          "button, then double-click an entry -> the view centres on that "
          "object (and switches level for an underground one). Double-click "
          "an indented Warning line -> same, via its header. Double-click "
          "'Map validated successfully' -> nothing happens, no crash.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
