#!/usr/bin/env python3
r"""
AoW1 editor PER-DIALOG-TYPE DIRECTORY MEMORY  --  binary patch for
AoWDevEd.exe + HSEPack.dpl.

PROBLEM
  Every file dialog in the editor (File>Open map, Developer>Open Mapset, the
  SaveAs dialogs, text import/export) opens in the same "last visited folder":
  none of them seed FileName/InitialDir, so they all fall back to Windows'
  per-application MRU folder (and the SaveAs pair seed InitialDir=GetCurrentDir,
  which the common dialog itself repoints on every pick). Scenario files and
  mapset/ruleset files live in different directories -> constant re-navigation.

WHAT IT DOES
  Each dialog *type* gets its own remembered path, persisted across sessions in
      <gamedir>\AoWEd_LastDirs.ini   section [LastDirs], keys Map / Set / Text.
  - OPEN dialogs: before Execute, FFileName (+0x6C) := remembered full path and
    FInitialDir (+0x60) := its directory part -> dialog opens in that folder
    with the last-used file preselected. After a successful pick, the chosen
    path is written back to the INI.
  - SAVEAS dialogs (map + set): their `SetInitialDir(GetCurrentDir)` call is
    rerouted: if the INI has a remembered path for that type, its directory
    part is used instead of the CWD; else original behaviour. (When a map
    already has a full path, the VCL puts it in lpstrFile which wins anyway --
    i.e. SaveAs on an existing file still opens at that file's own folder.)
  - First run / missing INI key -> exactly vanilla behaviour; the INI builds up
    as you use the dialogs. No INI file is created until a dialog is accepted.

  Dialog-type -> key map ("Map" is shared by exe-open and HSEPack map dialogs):
    Map : File>Open (exe), THSMEdit.Load, THSMEdit.SaveAs      (*.HSM)
    Set : Developer>Open Mapset (THSSEdit.Load), THSSEdit.SaveAs (*.HSS)
    Text: Export Text / Import Text / Export Ability Info (exe) (*.txt etc.)

HOOKS -- every site is a 5-byte `call <import thunk>` replaced 1:1 by
`call <cave wrapper>`; the wrapper calls the original thunk itself.

  AoWDevEd.exe (fixed base 0x400000):
    seed (call TOpenDialog.Create thunk 0x4019C8):
      0x429840 TMainForm.OpenBtnClick          key Map
      0x42B9AC TMainForm.ImportTextClick       key Text
      0x42B8AC TMainForm.ExportTextClick       key Text  (TSaveDialog, same ctor)
      0x42D436 TMainForm.ExportAbilityInfoClick key Text (TSaveDialog)
    persist (call TOpenDialog.GetFileName thunk 0x4019D0; first call after a
    successful Execute in each handler):
      0x429899 OpenBtnClick / 0x42B9DF ImportText / 0x42B8EC ExportText /
      0x42D488 ExportAbilityInfo

  HSEPack.dpl (preferred 0x55600000, REBASES -> cave is position-independent):
    seed (call Create thunk 0x55601A54):
      0x55615267 THSMEdit.Load   key Map
      0x55615E96 THSSEdit.Load   key Set
    dirseed (call TOpenDialog.SetInitialDir thunk 0x55601A64):
      0x55614D7E THSMEdit.SaveAs key Map
      0x55615C5A THSSEdit.SaveAs key Set
    persist (call GetFileName thunk 0x55601A5C):
      0x556152BD THSMEdit.Load / 0x55614E65 THSMEdit.SaveAs (the post-save one)
      0x55615EE5 THSSEdit.Load / 0x55615C8E THSSEdit.SaveAs

  HSEPack is also loaded by AoW.exe / AoWCompat.exe / AoWEd.exe. The patched
  functions are editor-only entry points (the game never calls THS?Edit.Load/
  SaveAs), and the cave is fully self-contained + host-agnostic (no absolute
  exe addresses), so riding along in other processes is harmless. Bonus:
  AoWEd.exe gets the fix for its map/mapset dialogs through HSEPack for free
  (its own in-exe File>Open dialog would need its own exe patch -- not done).

HOW THE CAVES CALL kernel32 (neither module imports the profile APIs)
  VCL30.dpl contains the IniFiles unit, so *its* import table has
  GetPrivateProfileStringA / WritePrivateProfileStringA. Both patched modules
  import VCL30!Dialogs.TOpenDialog.Create, so at runtime:
      vcl_delta = [own IAT slot holding &TOpenDialog.Create] - 0x4137AFB0
                   (0x4137AFB0 = Create's preferred VA inside VCL30.dpl)
      GetPrivateProfileStringA = [0x413E43B8 + vcl_delta]   (VCL30 IAT slot)
      WritePrivateProfileStringA = [0x413E42F8 + vcl_delta] (VCL30 IAT slot)
      GetModuleFileNameA = [0x413E43C0 + vcl_delta]         (VCL30 IAT slot)
  IAT slot VAs verified against the VCL30.dpl shipped with the game.
  Own IAT slot: AoWDevX.exe 0x432598, HSEPack.dpl 0x556308DC.

RUNTIME INI PATH (v2, 2026-07-31)
  v1 baked the absolute INI path (a build-machine constant) into the cave; that
  silently disabled the whole feature on any other machine / install folder
  (reads empty -> vanilla fallback, writes fail -> no error). v2 builds the
  path at runtime in a lazy `getini` helper: GetModuleFileNameA(NULL,buf,0x104)
  -> truncate after the last '\' -> append "AoWEd_LastDirs.ini". NULL = the
  host EXE, so HSEPack riding in AoW.exe/AoWEd.exe also resolves to the game
  dir. Built once per process (first byte of the buffer doubles as the "done"
  flag); if GetModuleFileNameA ever failed the buffer stays empty and both
  profile APIs no-op -> exactly vanilla behaviour, and the build is retried on
  the next dialog.

STRING HANDOFF to the VCL
  The INI read buffer doubles as a Delphi 3 static AnsiString:
  [buf-8]=refcount -1 (immutable), [buf-4]=length (set after each read).
  System.@LStrAsg copies when source refcount<0 (verified in VCL30 disasm), so
  assigning it into FFileName/FInitialDir is safe; SetInitialDir copies too.

  Delphi register ABI: eax/ecx/edx caller-saved, ebx/esi/edi callee-saved --
  the caves push/pop ebx/esi/edi and only rely on eax across the orig thunks.
  kernel32 APIs are stdcall (callee-cleaned, ebx/esi/edi preserved).

CAVE PLACEMENT
  New PE section ".dlgd" appended to each module (chars 0xE0000060: code+data,
  exec+read+WRITE -- the INI buffer lives in the section). The HSEPack cave
  uses one call/pop helper for its own rebase delta; every data reference is
  [reg+disp32] and every call is rel32 -> no .reloc entries needed.

CONVENTIONS: dry-run by default; --apply to write; idempotent (re-run
verifies); verify-before-write aborts on byte mismatch; auto-backup to
<file>.pre-dlgdirs. Close AoW / AoWCompat / AoWDevEd / AoWEd before --apply
(all of them lock HSEPack.dpl). Revert = copy the .pre-dlgdirs backups back.
NOTE HSEPack.dpl.pre-dlgdirs already contains the mapcursor fix (layered on
.pre-mapcursor) -- reverting THIS feature via .pre-dlgdirs keeps that fix.

Usage:
  python build_dlgdirs.py            # dry-run both modules (prints cave disasm)
  python build_dlgdirs.py --apply    # patch both
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
from capstone import Cs, CS_ARCH_X86, CS_MODE_32

# game dir = two levels up from this script (<game>/Modding Resources/<subdir>/);
# override with the AOW_GAME_DIR environment variable.
GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKUP_SUFFIX = ".pre-dlgdirs"
SECT_NAME = b".dlgd\0\0\0"
INI_FNAME = "AoWEd_LastDirs.ini"   # appended at RUNTIME to the host exe's directory
INI_SECTION = "LastDirs"

ks = Ks(KS_ARCH_X86, KS_MODE_32)
cs = Cs(CS_ARCH_X86, CS_MODE_32)

# ---- VCL30.dpl facts (verified against the shipped VCL30.dpl) ----------------
VCL_CREATE_PREF = 0x4137AFB0   # Dialogs.TOpenDialog.Create preferred VA
VCL_GPPS_SLOT   = 0x413E43B8   # VCL30 IAT slot: kernel32!GetPrivateProfileStringA
VCL_WPPS_SLOT   = 0x413E42F8   # VCL30 IAT slot: kernel32!WritePrivateProfileStringA
VCL_GMFN_SLOT   = 0x413E43C0   # VCL30 IAT slot: kernel32!GetModuleFileNameA
OFF_FILENAME    = 0x6C         # TOpenDialog.FFileName   (RTTI-verified)
OFF_INITIALDIR  = 0x60         # TOpenDialog.FInitialDir (RTTI-verified)

# ---- per-module facts ---------------------------------------------------------
# sites: (kind, va, key)  kind in {seed, save, dirseed}
MODULES = {
    "AoWDevX.exe": dict(   # was AoWDevEd.exe; same base binary, renamed + toolbar/about mods
        ib=0x400000,
        thunk_create=0x4019C8, thunk_getfn=0x4019D0,
        thunk_setinidir=None,               # exe has no SetInitialDir import (unused)
        thunk_lstrasg=0x4010C0,
        vcl_slot=0x432598,                  # IAT slot: VCL30!Dialogs.TOpenDialog.Create
        keys=("Map", "Text"),
        sites=[
            ("seed", 0x429840, "Map"),   ("save", 0x429899, "Map"),
            ("seed", 0x42B9AC, "Text"),  ("save", 0x42B9DF, "Text"),
            ("seed", 0x42B8AC, "Text"),  ("save", 0x42B8EC, "Text"),
            ("seed", 0x42D436, "Text"),  ("save", 0x42D488, "Text"),
        ],
    ),
    "HSEPack.dpl": dict(
        ib=0x55600000,
        thunk_create=0x55601A54, thunk_getfn=0x55601A5C,
        thunk_setinidir=0x55601A64,
        thunk_lstrasg=0x55601130,
        vcl_slot=0x556308DC,
        keys=("Map", "Set"),
        sites=[
            ("seed",    0x55615267, "Map"), ("save", 0x556152BD, "Map"),
            ("dirseed", 0x55614D7E, "Map"), ("save", 0x55614E65, "Map"),
            ("seed",    0x55615E96, "Set"), ("save", 0x55615EE5, "Set"),
            ("dirseed", 0x55615C5A, "Set"), ("save", 0x55615C8E, "Set"),
        ],
    ),
}

# ---- PE helpers (add-section pattern, from build_editor_autosave) -------------
def load_sections(d):
    e = struct.unpack_from('<I', d, 0x3C)[0]
    nsec = struct.unpack_from('<H', d, e+6)[0]
    optsz = struct.unpack_from('<H', d, e+20)[0]
    opt = e+24
    sectbl = opt+optsz
    secs = []
    for i in range(nsec):
        b = sectbl+i*40
        vsz, va, rsz, raw = struct.unpack_from('<IIII', d, b+8)
        secs.append((va, vsz, raw, rsz, b))
    return dict(e=e, nsec=nsec, opt=opt,
                salign=struct.unpack_from('<I', d, opt+32)[0],
                falign=struct.unpack_from('<I', d, opt+36)[0],
                sectbl=sectbl, secs=secs)

def align(x, a): return (x + a - 1) // a * a

def va2off(secs, va, ib):
    r = va - ib
    for va0, vsz, raw, rsz, _ in secs:
        if va0 <= r < va0 + max(vsz, rsz):
            return raw + (r - va0)
    raise ValueError(hex(va))

def rel32(src, dst): return struct.pack('<i', dst - (src + 5))

# ---- cave construction ---------------------------------------------------------
# Layout: [code][pad4][refcnt -1][len][buf 0x108][sect][keys...][empty][inipath]
# All addresses in the asm are PREFERRED VAs; at runtime the ebx delta (from the
# call/pop helper) corrects them. In the exe the delta is simply 0.

def build_cave(cave_va, M):
    keys = M["keys"]

    def asm_source(D):
        # D maps symbolic names -> preferred VAs (dummies on pass 1)
        s = f"""
        /* ---- getdelta: eax := runtime - preferred (module rebase delta) ---- */
        getdelta:
            call gd1
        gd1: pop eax
            sub eax, 0x{D['gd1']:08X}
            ret

        /* ---- getini: lazily build <exedir>\\AoWEd_LastDirs.ini in inipath ----
           in: ebx=delta. preserves ebx/esi/edi/ecx; clobbers eax/edx.
           first byte of inipath doubles as the "already built" flag. */
        getini:
            cmp byte ptr [ebx + 0x{D['inipath']:08X}], 0
            jne gi_done
            push ecx
            push 0x104
            lea eax, [ebx + 0x{D['inipath']:08X}]
            push eax
            push 0                              /* NULL -> host exe path */
            mov eax, [ebx + 0x{M['vcl_slot']:08X}]
            sub eax, 0x{VCL_CREATE_PREF:08X}
            mov eax, [eax + 0x{VCL_GMFN_SLOT:08X}]
            call eax                            /* GetModuleFileNameA -> eax=len */
            mov ecx, eax
        gi_scan:
            dec ecx
            js gi_fail                          /* no '\\' -> leave unbuilt */
            cmp byte ptr [ebx + ecx + 0x{D['inipath']:08X}], 0x5C
            jne gi_scan
            inc ecx                             /* keep dir incl trailing '\\' */
            xor edx, edx
        gi_copy:
            mov al, [ebx + edx + 0x{D['fname']:08X}]
            mov [ebx + ecx + 0x{D['inipath']:08X}], al
            inc ecx
            inc edx
            test al, al
            jne gi_copy                         /* copies the NUL then stops */
            pop ecx
            ret
        gi_fail:
            mov byte ptr [ebx + 0x{D['inipath']:08X}], 0
            pop ecx
        gi_done:
            ret
        """
        # seed wrappers + common (Create sites)
        for k in keys:
            s += f"""
        seed_{k}:
            call 0x{M['thunk_create']:08X}      /* original ctor; eax = dialog */
            push ebx
            push esi
            mov esi, eax
            call getdelta
            mov ebx, eax
            lea ecx, [ebx + 0x{D['key'+k]:08X}]
            jmp seed_common
        """
        s += f"""
        seed_common:            /* esi=dialog ebx=delta ecx=&key */
            call getini
            lea eax, [ebx + 0x{D['inipath']:08X}]
            push eax
            push 0x104
            lea eax, [ebx + 0x{D['buf']:08X}]
            push eax
            lea eax, [ebx + 0x{D['empty']:08X}]
            push eax
            push ecx
            lea eax, [ebx + 0x{D['sect']:08X}]
            push eax
            mov eax, [ebx + 0x{M['vcl_slot']:08X}]
            sub eax, 0x{VCL_CREATE_PREF:08X}
            mov eax, [eax + 0x{VCL_GPPS_SLOT:08X}]
            call eax                            /* GetPrivateProfileStringA -> eax=len */
            test eax, eax
            jz seed_done
            cmp eax, 0x103
            jae seed_done                       /* truncated -> ignore */
            mov [ebx + 0x{D['len']:08X}], eax
            lea eax, [esi + 0x{OFF_FILENAME:02X}]
            lea edx, [ebx + 0x{D['buf']:08X}]
            call 0x{M['thunk_lstrasg']:08X}     /* FFileName := remembered path */
            mov ecx, [ebx + 0x{D['len']:08X}]
        seed_scan:
            dec ecx
            js seed_done                        /* no backslash -> skip InitialDir */
            cmp byte ptr [ebx + ecx + 0x{D['buf']:08X}], 0x5C
            jne seed_scan
            inc ecx
            mov [ebx + 0x{D['len']:08X}], ecx   /* len = dir incl. trailing '\\' */
            lea eax, [esi + 0x{OFF_INITIALDIR:02X}]
            lea edx, [ebx + 0x{D['buf']:08X}]
            call 0x{M['thunk_lstrasg']:08X}     /* FInitialDir := dir part */
        seed_done:
            mov eax, esi                        /* return the dialog */
            pop esi
            pop ebx
            ret
        """
        # save wrappers + common (GetFileName sites)
        for k in keys:
            s += f"""
        save_{k}:
            push ebx
            push esi
            push edi
            mov esi, edx                        /* @out string var */
            mov edi, eax                        /* dialog */
            call getdelta
            mov ebx, eax
            lea ecx, [ebx + 0x{D['key'+k]:08X}]
            jmp save_common
        """
        s += f"""
        save_common:            /* esi=@out edi=dialog ebx=delta ecx=&key */
            call getini
            push ecx
            mov eax, edi
            mov edx, esi
            call 0x{M['thunk_getfn']:08X}       /* original GetFileName */
            pop ecx
            mov edx, [esi]                      /* AnsiString ptr (0 if empty) */
            test edx, edx
            jz save_done
            lea eax, [ebx + 0x{D['inipath']:08X}]
            push eax
            push edx
            push ecx
            lea eax, [ebx + 0x{D['sect']:08X}]
            push eax
            mov eax, [ebx + 0x{M['vcl_slot']:08X}]
            sub eax, 0x{VCL_CREATE_PREF:08X}
            mov eax, [eax + 0x{VCL_WPPS_SLOT:08X}]
            call eax                            /* WritePrivateProfileStringA */
        save_done:
            pop edi
            pop esi
            pop ebx
            ret
        """
        # dirseed wrappers + common (SetInitialDir sites; HSEPack only)
        if M["thunk_setinidir"]:
            for k in keys:
                s += f"""
        dirseed_{k}:
            push ebx
            push esi
            push edi
            mov esi, eax                        /* dialog */
            push edx                            /* original InitialDir string */
            call getdelta
            mov ebx, eax
            lea ecx, [ebx + 0x{D['key'+k]:08X}]
            jmp dirseed_common
        """
            s += f"""
        dirseed_common:         /* esi=dialog ebx=delta ecx=&key [esp]=orig edx */
            call getini
            lea eax, [ebx + 0x{D['inipath']:08X}]
            push eax
            push 0x104
            lea eax, [ebx + 0x{D['buf']:08X}]
            push eax
            lea eax, [ebx + 0x{D['empty']:08X}]
            push eax
            push ecx
            lea eax, [ebx + 0x{D['sect']:08X}]
            push eax
            mov eax, [ebx + 0x{M['vcl_slot']:08X}]
            sub eax, 0x{VCL_CREATE_PREF:08X}
            mov eax, [eax + 0x{VCL_GPPS_SLOT:08X}]
            call eax
            test eax, eax
            jz dirseed_orig
            cmp eax, 0x103
            jae dirseed_orig
            mov ecx, eax
        dirseed_scan:
            dec ecx
            js dirseed_orig                     /* no backslash -> keep orig */
            cmp byte ptr [ebx + ecx + 0x{D['buf']:08X}], 0x5C
            jne dirseed_scan
            inc ecx
            mov [ebx + 0x{D['len']:08X}], ecx
            pop edx                             /* discard original CWD string */
            lea edx, [ebx + 0x{D['buf']:08X}]
            jmp dirseed_call
        dirseed_orig:
            pop edx                             /* original InitialDir */
        dirseed_call:
            mov eax, esi
            pop edi
            pop esi
            pop ebx
            jmp 0x{M['thunk_setinidir']:08X}    /* tail: original SetInitialDir */
        """
        return s

    # pass 1: dummy data VAs (all >0x10000000 so operand sizes are stable)
    dummy = dict(gd1=0x11111111, inipath=0x11111112, buf=0x11111113,
                 empty=0x11111114, sect=0x11111115, len=0x11111116,
                 fname=0x11111117)
    for k in keys:
        dummy["key"+k] = 0x11111100
    code0, _ = ks.asm(asm_source(dummy), cave_va)
    code_len = len(code0)

    # data layout after code
    off = align(code_len, 4)
    lay = {}
    lay['refcnt'] = off;            off += 4
    lay['len'] = off;               off += 4
    lay['buf'] = off;               off += 0x108
    lay['sect'] = off;              off += len(INI_SECTION) + 1
    for k in keys:
        lay['key'+k] = off;         off += len(k) + 1
    lay['empty'] = off;             off += 1
    lay['fname'] = off;             off += len(INI_FNAME) + 1
    lay['inipath'] = off;           off += 0x120   # runtime-built; byte0 = done-flag
    # 0x120 headroom: dir part <= 0x103 (GetModuleFileNameA truncates at 0x104)
    # + len(INI_FNAME)+1 = 19+1 -> max 0x117 < 0x120

    D = {n: cave_va + o for n, o in lay.items()}
    D['gd1'] = cave_va + 5          # gd1 label = getdelta+5 (call rel32 is 5 bytes)
    code, _ = ks.asm(asm_source(D), cave_va)
    code = bytes(code)
    assert len(code) == code_len, "cave length changed between passes"

    blob = bytearray(code)
    blob += b"\x00" * (lay['refcnt'] - len(blob))
    blob += struct.pack("<i", -1)                    # static AnsiString refcount
    blob += struct.pack("<I", 0)                     # length (runtime-set)
    blob += b"\x00" * 0x108                          # buf
    blob += INI_SECTION.encode() + b"\x00"
    for k in keys:
        blob += k.encode() + b"\x00"
    blob += b"\x00"                                  # empty default
    blob += INI_FNAME.encode() + b"\x00"
    blob += b"\x00" * 0x120                          # inipath (runtime-built)
    assert len(blob) == off

    # wrapper entry points: parse label addresses back out of a fresh assemble
    # (keystone has no symbol output; recompute by assembling prefixes) -- simpler:
    # regenerate with capstone and match. Instead we just track order: labels are
    # laid out in source order; find them by assembling the source incrementally.
    # Pragmatic approach: disassemble and identify wrapper starts by pattern.
    # -> we instead compute them analytically below.
    return blob, code, asm_source(D)

def find_entry_points(code, cave_va, M):
    """Locate wrapper entry VAs by instruction pattern (order matches source)."""
    keys = M["keys"]
    entries = {}
    insns = list(cs.disasm(bytes(code), cave_va))
    # getdelta is at cave_va. seed_<k> starts with 'call <thunk_create>'.
    calls_create = [i.address for i in insns
                    if i.mnemonic == "call" and i.op_str == f"0x{M['thunk_create']:x}"]
    assert len(calls_create) == len(keys), (calls_create, keys)
    for k, a in zip(keys, calls_create):
        entries["seed_"+k] = a
    # save_<k>: starts 'push ebx' right after previous ret; find by the
    # push ebx;push esi;push edi;mov esi,edx;mov edi,eax prologue sequence.
    seq = []
    for idx in range(len(insns)-4):
        if ([insns[idx+j].mnemonic for j in range(5)] ==
                ["push", "push", "push", "mov", "mov"] and
                insns[idx].op_str == "ebx" and insns[idx+1].op_str == "esi" and
                insns[idx+2].op_str == "edi" and insns[idx+3].op_str == "esi, edx"):
            seq.append(insns[idx].address)
    assert len(seq) == len(keys), ("save wrappers", seq)
    for k, a in zip(keys, seq):
        entries["save_"+k] = a
    if M["thunk_setinidir"]:
        seq = []
        for idx in range(len(insns)-4):
            if ([insns[idx+j].mnemonic for j in range(5)] ==
                    ["push", "push", "push", "mov", "push"] and
                    insns[idx].op_str == "ebx" and insns[idx+3].op_str == "esi, eax"):
                seq.append(insns[idx].address)
        assert len(seq) == len(keys), ("dirseed wrappers", seq)
        for k, a in zip(keys, seq):
            entries["dirseed_"+k] = a
    return entries

# ---- process one module --------------------------------------------------------
def process(name, apply):
    M = MODULES[name]
    ib = M["ib"]
    path = os.path.join(GAME, name)
    d = bytearray(open(path, "rb").read())
    F = load_sections(d)
    secs = F["secs"]

    if any(bytes(d[s[4]:s[4]+5]) == SECT_NAME[:5] for s in secs):
        print(f"[{name}] already patched (.dlgd section present) - idempotent no-op")
        return True

    # verify all original site bytes BEFORE building anything
    thunk_of = dict(seed=M["thunk_create"], save=M["thunk_getfn"],
                    dirseed=M["thunk_setinidir"])
    for kind, va, key in M["sites"]:
        exp = b"\xE8" + rel32(va, thunk_of[kind])
        off = va2off(secs, va, ib)
        got = bytes(d[off:off+5])
        if got != exp:
            print(f"[{name}] ABORT: site 0x{va:08X} ({kind}/{key}) bytes mismatch\n"
                  f"     exp {exp.hex(' ')}  got {got.hex(' ')}")
            return False
    if F["sectbl"] + F["nsec"]*40 + 40 > secs[0][2]:
        print(f"[{name}] ABORT: no PE header room for a new section")
        return False

    newva = align(max(s[0] + max(s[1], s[3]) for s in secs), F["salign"])
    cave_va = ib + newva
    blob, code, _src = build_cave(cave_va, M)
    entries = find_entry_points(code, cave_va, M)

    print(f"[{name}] cave @ 0x{cave_va:08X}  ({len(code)}B code, {len(blob)}B total)")
    for n, a in sorted(entries.items(), key=lambda kv: kv[1]):
        print(f"    {n:<14} 0x{a:08X}")
    for kind, va, key in M["sites"]:
        tgt = entries[f"{kind}_{key}"]
        print(f"    site 0x{va:08X}  {kind:<8} {key:<4} -> call 0x{tgt:08X}")

    if not apply:
        print(f"[{name}] dry-run OK (all {len(M['sites'])} sites verified)")
        return True

    backup = path + BACKUP_SUFFIX
    if not os.path.exists(backup):
        shutil.copy2(path, backup)
        print(f"[{name}] backup -> {os.path.basename(backup)}")

    newraw = align(len(d), F["falign"])
    if len(d) < newraw:
        d += b"\x00" * (newraw - len(d))
    rawsz = align(len(blob), F["falign"])
    d += bytes(blob) + b"\x00" * (rawsz - len(blob))
    b = F["sectbl"] + F["nsec"]*40
    struct.pack_into("<8sIIII", d, b, SECT_NAME, len(blob), newva, rawsz, newraw)
    struct.pack_into("<IIHHI", d, b+24, 0, 0, 0, 0, 0xE0000060)  # code|idata|X|R|W
    struct.pack_into("<H", d, F["e"]+6, F["nsec"]+1)
    struct.pack_into("<I", d, F["opt"]+56, align(newva + len(blob), F["salign"]))

    for kind, va, key in M["sites"]:
        off = va2off(secs, va, ib)
        d[off:off+5] = b"\xE8" + rel32(va, entries[f"{kind}_{key}"])

    try:
        open(path, "wb").write(d)
    except PermissionError:
        print(f"[{name}] LOCKED - close AoW/AoWCompat/AoWDevEd/AoWEd and retry")
        return False
    print(f"[{name}] written. Revert = copy {os.path.basename(backup)} over it.")
    return True

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--disasm", action="store_true", help="dump full cave disasm")
    args = ap.parse_args()
    ok = True
    print(f"AoW1 editor per-dialog directory memory  |  INI: <exedir>\\{INI_FNAME} (runtime-derived)\n")
    for name in MODULES:
        if args.disasm:
            M = MODULES[name]
            d = bytearray(open(os.path.join(GAME, name), "rb").read())
            F = load_sections(d)
            newva = align(max(s[0]+max(s[1], s[3]) for s in F["secs"]), F["salign"])
            blob, code, _ = build_cave(M["ib"]+newva, M)
            print(f"===== {name} cave disasm =====")
            for ins in cs.disasm(bytes(code), M["ib"]+newva):
                print(f"  {ins.address:08X}  {ins.bytes.hex(' '):<21} {ins.mnemonic} {ins.op_str}")
        ok &= process(name, args.apply)
        print()
    if not args.apply:
        print("[dry-run] Re-run with --apply to write (close the game/editors first).")
    elif ok:
        print("[done] Applied both modules.")
    else:
        sys.exit(1)

main()
