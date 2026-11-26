#!/usr/bin/env python3
r"""Readable save-game timestamps in the Load/Save dialog (Date column).

The Date column (TFileDlgWindow's DateLB, dlg+0xE8) is filled in one loop in
AoWx.exe: for every save found by FindFirst it stores
FileDateToDateTime(SearchRec.Time) in a helper object (0x41F716), then formats
each entry with SysUtils.DateTimeToStr (single call site 0x41F89E, thunk
0x401434, IAT slot 0x45D404).

DateTimeToStr uses VCL30's locale-derived globals: ShortDateFormat is taken
from Windows LOCALE_SSHORTDATE *as-is* (vcl30 GetFormatSettings @0x4130EDF4;
the TranslateDateFormat pass @0x4130EBDC only rewrites era formats for CJK
locales), and LongTimeFormat is built as 'h'/'hh' + ':mm:ss' + AM/PM. In 1999
that produced "7/31/98 6:46:09 PM"; modern Windows short-date defaults
(4-digit year, e.g. "M/d/yyyy") push the string to ~20 chars, which overflows
the 130px-wide DateLB (font Age8, digit advance 5px) and shows a garbled
tail like "26 7 02 38" (the ':' glyph is 1px wide and reads as a space).

Fix: call SysUtils.DateTimeToString(var Result; const Format; DateTime) with
an explicit locale-independent format 'yyyy-mm-dd hh:nn:ss' (Delphi 'nn' =
minutes). Its register/stack layout is DateTimeToStr's (eax=^Result, TDateTime
pushed, callee-cleaned) plus edx=Format, so the existing call site needs only
an edx load in front:

  1. New import hint/name entry "SysUtils.DateTimeToString@73F58862" in DATA
     tail slack (vcl30.dpl exports it; verified against the export table).
  2. IAT/ILT slot 0x45D404 repointed to it -> thunk 0x401434 becomes
     DateTimeToString at load time (Borland links with OriginalFirstThunk=0;
     0x45D404 is the only reference in the file).
  3. 10-byte stub in the CODE tail slack: mov edx,<fmt literal>; jmp thunk.
     Format string is a Delphi literal (refcount -1) in DATA slack.
  4. call 0x401434 at 0x41F89E -> call stub.

Output "2026-07-31 18:46:09" is 19 chars but ~88px in Age8 (2px colons), well
inside DateLB's 130px, and sorts/reads the same everywhere.

Backup: AoWx.exe.bak_savedate. Dry-run default; --apply / --revert.
"""
import os, shutil, struct, sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
EXE = os.path.join(GAME, "AoWx.exe")
VCL = os.path.join(GAME, "vcl30.dpl")
BAK = EXE + ".bak_savedate"

CODE2FILE  = 0x400C00      # CODE and DATA: file = VA - this
IDATA2FILE = 0x402400      # .idata: file = VA - this

CALL_SITE = 0x41F89E       # E8 -> thunk 0x401434 (DateTimeToStr), only caller
THUNK_VA  = 0x401434       # jmp [0x45D404]
ILT_VA    = 0x45D404       # import slot, currently name-RVA 0x5F88E
OLD_RVA   = 0x0005F88E     # "SysUtils.DateTimeToStr@0B3E54BB" hint/name entry

STUB_VA   = 0x459FEC       # CODE tail slack (vsz 0x58FEC..raw 0x59000: 20 B, zeros)
STUB_END  = 0x45A000
NAME_VA   = 0x45A634       # DATA tail slack (vsz 0x634..raw 0x800: 0x1CC B, zeros)
DATA_END  = 0x45A800
NEW_IMPORT = b"SysUtils.DateTimeToString@73F58862"
FMT        = b"yyyy-mm-dd hh-nn-ss"   # dashes: Age8's ':' glyph is ~invisible

LIT_HDR   = NAME_VA + ((2 + len(NEW_IMPORT) + 1 + 3) & ~3)   # dword-aligned
LIT_CHARS = LIT_HDR + 8


def build_data():
    blob = bytearray()
    blob += b"\x00\x00" + NEW_IMPORT + b"\x00"     # hint(0) + name + NUL
    blob += bytes(LIT_HDR - NAME_VA - len(blob))   # align pad
    blob += struct.pack("<i", -1)                  # refcount: constant
    blob += struct.pack("<I", len(FMT))            # length
    blob += FMT + b"\x00"
    return bytes(blob)


def build_stub():
    code = bytearray()
    code += b"\xBA" + struct.pack("<I", LIT_CHARS)                    # mov edx,fmt
    code += b"\xE9" + struct.pack("<i", THUNK_VA - (STUB_VA + len(code) + 5))
    return bytes(code)


def main():
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if revert:
        if os.path.exists(BAK):
            shutil.copy2(BAK, EXE); print("restored AoWx.exe"); return 0
        print("no backup"); return 1

    d = bytearray(open(EXE, "rb").read())
    data_blob = build_data()
    stub = build_stub()
    assert NAME_VA + len(data_blob) <= DATA_END, len(data_blob)
    assert STUB_VA + len(stub) <= STUB_END, len(stub)

    # the shipped vcl30.dpl must actually export the new name
    vcl = open(VCL, "rb").read()
    assert NEW_IMPORT + b"\x00" in vcl, "vcl30.dpl lacks %s" % NEW_IMPORT

    # version checks
    call_off = CALL_SITE - CODE2FILE
    old_call = b"\xE8" + struct.pack("<i", THUNK_VA - (CALL_SITE + 5))
    new_call = b"\xE8" + struct.pack("<i", STUB_VA - (CALL_SITE + 5))
    assert d[call_off:call_off+5] in (old_call, new_call), d[call_off:call_off+5].hex()

    thunk_off = THUNK_VA - CODE2FILE
    assert d[thunk_off:thunk_off+6] == b"\xFF\x25" + struct.pack("<I", ILT_VA), \
        d[thunk_off:thunk_off+6].hex()

    ilt_off = ILT_VA - IDATA2FILE
    cur = struct.unpack_from("<I", d, ilt_off)[0]
    assert cur in (OLD_RVA, NAME_VA - 0x400000), hex(cur)

    old_name_off = OLD_RVA + 0x400000 - IDATA2FILE
    assert d[old_name_off+2:old_name_off+2+22] == b"SysUtils.DateTimeToStr", \
        "old import entry moved"

    for va, blob, delta in ((STUB_VA, stub, CODE2FILE), (NAME_VA, data_blob, CODE2FILE)):
        off = va - delta
        seg = bytes(d[off:off+len(blob)])
        assert seg == bytes(len(blob)) or seg == blob, "cave @0x%X in use" % va

    stub_off = STUB_VA - CODE2FILE
    name_off = NAME_VA - CODE2FILE
    d[stub_off:stub_off+len(stub)] = stub
    d[name_off:name_off+len(data_blob)] = data_blob
    struct.pack_into("<I", d, ilt_off, NAME_VA - 0x400000)
    d[call_off:call_off+5] = new_call

    print("AoWx: save-date format -> '%s'" % FMT.decode())
    print("  import slot 0x%X -> %s @0x%X" % (ILT_VA, NEW_IMPORT.decode(), NAME_VA))
    print("  stub %dB @0x%X (mov edx,0x%X; jmp 0x%X); call site 0x%X -> stub"
          % (len(stub), STUB_VA, LIT_CHARS, THUNK_VA, CALL_SITE))
    if not apply:
        print("Dry run OK — rerun with --apply (or --revert)."); return 0
    if not os.path.exists(BAK):
        shutil.copy2(EXE, BAK); print("Backup ->", os.path.basename(BAK))
    open(EXE, "wb").write(d)
    print("Written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
