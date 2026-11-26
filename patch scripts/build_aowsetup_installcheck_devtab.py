#!/usr/bin/env python3
r"""AoWSetup.exe patch set v3 (install check, Developer tab, launch targets, Cheat Mode).

FIX 1  Root Directory fallback -- the install check, Start buttons and dictionary
       path all read `General\Root Directory` from the mod's isolated registry
       tree, which does not exist until the game has run once, so fresh installs
       saw only Install/Exit. A cave hooks the getter's registry call and
       substitutes the constant '.' when the value is empty.
FIX 2  Developer tab navigation -- every page of MainPageControl is a screen with
       a hidden tab header (v1 made only the Developer tab visible => one-way
       door). Entry hooks on SettingsBtnClick / SettingsOk / SettingsCancel show
       both SettingsSheet(+0x1EC) and DeveloperSheet(+0x224) tabs while in
       settings and hide them again on exit.
FIX 3  Editor button launches AoWDevX.exe (const repointed; '\aowed.exe' had no
       room to grow).
FIX 4  Start button launches AoWx.exe (const edited in place, len 8->9).
FIX 5  *** CHEAT MODE toggle (new) ***
       The vanilla cheat is armed by launching the game with the command-line
       argument 'beatrix' (AoWEPACK 0x557740EB compares ParamStr(1) against the
       'beatrix' const, then Ctrl+Shift+C toggles cheat mode in game). So no
       game patch is needed -- only the launcher must pass the argument.
       - A real TCheckBox 'Cheat Mode' is CREATED AT RUNTIME on the Developer
         sheet the first time Settings is opened (lazy: if creation ever failed
         the main menu still works). All four stock dev options are kept.
       - Its state persists in `General\Cheat Mode` (same registry helper the
         other checkboxes use), loaded on opening Settings, saved on OK.
       - StartAoWBtnClick's ShellExecute lpParameters argument now points at a
         cave buffer that is filled with 'beatrix' or '' just before launch.

VCL facts (all verified twice -- via TCheckBox's VMT and via VCL's own
CreateMessageDialog @0x4386A0, which builds buttons dynamically):
  TCheckBox VMT 0x430368 (Delphi 3 layout: class name at vmt-0x20)
  ctor          VMT+0x24 = 0x4345D4   (eax=VMT, dl=1, ecx=Owner) -> eax=instance
  SetParent     VMT+0x18 (0x41C7E4)   (eax=ctrl, edx=parent, virtual)
  SetBounds     VMT+0x4C (0x4200B8)   (eax, edx=Left, ecx=Top, push W, push H)
  SetText       0x41CA24              (eax=ctrl, edx=AnsiString)
  Get/SetChecked 0x434694 / 0x4346B4  (from the app's own settings load/save)
  registry rw   0x4670AC (eax=obj, edx=section, ecx=name, push @buf, push flag,
                ret 8); registry object global 0x46BA34; 'General' 0x4679C8
Dev-sheet geometry from the DFM: checkboxes Left 112, Top 128/160/192/232,
so the new one sits at Top 264 (Width 141, Height 17).

Cave space: CODE tail slack 0x4698E0-0x469A00 (file-backed) + DATA tail slack
0x46AEC0-0x46B000, which requires marking DATA executable
(characteristics 0xC0000040 -> 0xE0000040). Variables live in the BSS tail
(0x46BA40+, zero-filled, past the app's last global at 0x46BA34).
Relocations covered by displaced bytes are neutralized on apply and restored on
revert ([[patching-over-relocs-gotcha]]). The exe has no DYNAMIC_BASE flag, so
absolute addresses in the caves are safe.

Usage: --apply | --revert | --status   Backup: AoWSetup.exe.bak_nocheckdev
"""
import os, shutil, struct, sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
EXE = os.path.join(GAME, "AoWSetup.exe")
BAK = EXE + ".bak_nocheckdev"

D = 0x400C00                      # CODE: file = VA - D
# DATA: VirtualAddress 0x6A000, PointerToRawData 0x68E00
#   file = (VA - 0x400000) - 0x6A000 + 0x68E00 = VA - 0x401200
# (⚠ 2026-08-13: first cut used 0x401E00 here and wrote the caves 0xC00 bytes
#  early, leaving the hook targets pointing at zeroed slack -- always verify a
#  cave's bytes are readable back at its VA, not just that the write succeeded.)
DATA_D = 0x401200                 # DATA: file = VA - DATA_D  (0x46AEC0 -> 0x69CC0)

# ---------------- engine / VCL addresses ----------------
REGREAD_GENERIC = 0x4670AC
REG_OBJ = 0x46BA34
GENERAL_STR = 0x4679C8
SETCHECKED, GETCHECKED = 0x4346B4, 0x434694
SETTEXT = 0x41CA24
SETTABVIS = 0x43A32C
CHK_VMT, CHK_CTOR = 0x430368, 0x4345D4
# ⚠ VMT+0x18 is TControl.SetName (0x41C7E4), NOT SetParent -- CreateMessageDialog
# calls it to name its buttons, which is what misled the first cut. Passing a
# TTabSheet there made Delphi validate an object pointer as a component name and
# raise '"<garbage>" is not a valid component name'. The real TControl.SetParent
# is VMT+0x3C (0x41C8CC: compares FParent at +0x24, raises the "cannot have
# itself as parent" resource string @0x46ADFC, then Remove/InsertControl).
SLOT_SETPARENT, SLOT_SETBOUNDS = 0x3C, 0x4C
OFF_SETTINGSSHEET, OFF_DEVSHEET = 0x1EC, 0x224
BOX_LEFT, BOX_TOP, BOX_W, BOX_H = 112, 264, 141, 17

# ---------------- cave layout ----------------
STR_DOT = 0x4698E0          # '.'            (12 B)
PATH_CODE = 0x4698EC        # path fallback  (31 B)
SETBOTH = 0x469910          # tab helper
CHEAT_GET = 0x469930
CHEAT_SET = 0x469950
EDSTR = 0x469978            # '\AoWDevX.exe' (21 B)
HIDECAN = 0x469990
CODE_END = 0x469A00

STR_CHEAT = 0x46AEC0        # 'Cheat Mode'   (19 B) - DATA
ENSURE = 0x46AEE0
SHOW = 0x46AF40
HIDEOK = 0x46AF80
STARTAOW = 0x46AFB0
DATA_END = 0x46B000

CBVAR = 0x46BA40            # BSS: checkbox instance pointer
BUF = 0x46BA44              # BSS: ShellExecute lpParameters buffer (8 B)

# ---------------- hook sites ----------------
HOOK_VA = 0x4675A0                              # call 0x46719C (path getter)
HOOK_OLD = bytes.fromhex("e8f7fbffff")
REGREAD = 0x46719C

EDMOV_VA = 0x46894F                             # mov edx,'\aowed.exe'
EDMOV_OLD = bytes.fromhex("bacc894600")

AOWX_VA = 0x4688DC                              # len dword + '\aow.exe' + pad
AOWX_OLD = struct.pack("<I", 8) + b"\\aow.exe\x00\x00\x00\x00"
AOWX_NEW = struct.pack("<I", 9) + b"\\AoWx.exe\x00\x00\x00"

START_VA = 0x468847                             # push 1 / push '' / push ''
START_OLD = bytes.fromhex("6a0168d488460068d4884600")
START_RESUME = 0x468853

SBTN_VA = 0x4689F4
SBTN_OLD = bytes.fromhex("538bd88bc3")
SBTN_RESUME = 0x4689F9
OK_VA = 0x469090
OK_OLD = bytes.fromhex("558bec83c4f8")
OK_RESUME = 0x469096
CAN_VA = 0x469344
CAN_OLD = bytes.fromhex("538bd8a134ba4600")
CAN_RESUME = 0x46934C


def dd(v):
    return struct.pack("<I", v & 0xFFFFFFFF)


def rel(frm_end, to):
    return struct.pack("<i", to - frm_end)


def call(at, target):
    return b"\xe8" + rel(at + 5, target)


def jmp(at, target):
    return b"\xe9" + rel(at + 5, target)


def astr(s):
    """Delphi refcount -1 string constant: header + chars + NUL."""
    return struct.pack("<i", -1) + dd(len(s)) + s.encode() + b"\x00"


# ---------------- cave builders ----------------
def build_path_cave():
    c = bytearray()
    c += bytes.fromhex("ff742408")                  # push [esp+8]  dest
    c += bytes.fromhex("ff742408")                  # push [esp+8]  default
    c += call(PATH_CODE + len(c), REGREAD)
    c += bytes.fromhex("8b442408")                  # mov eax,[esp+8]
    c += bytes.fromhex("833800")                    # cmp dword [eax],0
    c += bytes.fromhex("7506")                      # jne done
    c += b"\xc7\x00" + dd(STR_DOT + 8)              # mov [eax], @'.'
    c += bytes.fromhex("c20800")                    # ret 8
    return bytes(c)


def build_setboth():
    c = bytearray()
    c += b"\x56\x52"                                # push esi; push edx
    c += bytes.fromhex("8bf0")                      # mov esi,eax
    c += b"\x8b\x86" + dd(OFF_SETTINGSSHEET)        # mov eax,[esi+1EC]
    c += call(SETBOTH + len(c), SETTABVIS)
    c += b"\x5a\x52"                                # pop edx; push edx
    c += b"\x8b\x86" + dd(OFF_DEVSHEET)             # mov eax,[esi+224]
    c += call(SETBOTH + len(c), SETTABVIS)
    c += b"\x5a\x5e\xc3"                            # pop edx; pop esi; ret
    return bytes(c)


def build_cheat_get():
    c = bytearray()
    c += b"\x51"                                    # push ecx (result slot)
    c += bytes.fromhex("c6042400")                  # mov byte [esp],0
    c += b"\x54"                                    # push esp  (@buffer)
    c += b"\x6a\x00"                                # push 0    (read)
    c += b"\xb9" + dd(STR_CHEAT + 8)                # mov ecx,'Cheat Mode'
    c += b"\xba" + dd(GENERAL_STR)                  # mov edx,'General'
    c += call(CHEAT_GET + len(c), REGREAD_GENERIC)
    c += bytes.fromhex("8a0424")                    # mov al,[esp]
    c += b"\x5a\xc3"                                # pop edx; ret
    return bytes(c)


def build_cheat_set():
    c = bytearray()
    c += b"\x51"                                    # push ecx
    c += bytes.fromhex("881424")                    # mov [esp],dl
    c += b"\x54"                                    # push esp
    c += b"\x6a\x01"                                # push 1    (write)
    c += b"\xb9" + dd(STR_CHEAT + 8)
    c += b"\xba" + dd(GENERAL_STR)
    c += call(CHEAT_SET + len(c), REGREAD_GENERIC)
    c += b"\x5a\xc3"                                # pop edx; ret
    return bytes(c)


def build_ensure():
    """eax = form. Creates the Cheat Mode checkbox once."""
    c = bytearray()
    c += b"\x83\x3d" + dd(CBVAR) + b"\x00"          # cmp dword [CBVAR],0
    jne_at = len(c)
    c += b"\x75\x00"                                # jne done (patched below)
    c += b"\x53\x50"                                # push ebx; push eax(form)
    c += bytes.fromhex("8bc8")                      # mov ecx,eax   Owner
    c += b"\xb2\x01"                                # mov dl,1
    c += b"\xb8" + dd(CHK_VMT)                      # mov eax,TCheckBox VMT
    c += call(ENSURE + len(c), CHK_CTOR)            # -> eax = instance
    c += b"\xa3" + dd(CBVAR)                        # mov [CBVAR],eax
    c += b"\x5a"                                    # pop edx (form)
    c += b"\x8b\x92" + dd(OFF_DEVSHEET)             # mov edx,[edx+224]
    c += bytes.fromhex("8b08")                      # mov ecx,[eax]
    c += bytes([0xFF, 0x51, SLOT_SETPARENT])        # call [ecx+3C]  SetParent
    c += b"\xa1" + dd(CBVAR)                        # mov eax,[CBVAR]
    c += bytes.fromhex("8b18")                      # mov ebx,[eax]
    c += b"\x68" + dd(BOX_W)                        # push Width
    c += b"\x6a" + bytes([BOX_H])                   # push Height
    c += b"\xb9" + dd(BOX_TOP)                      # mov ecx,Top
    c += b"\xba" + dd(BOX_LEFT)                     # mov edx,Left
    c += bytes([0xFF, 0x53, SLOT_SETBOUNDS])        # call [ebx+4C]  SetBounds
    c += b"\xba" + dd(STR_CHEAT + 8)                # mov edx,'Cheat Mode'
    c += b"\xa1" + dd(CBVAR)
    c += call(ENSURE + len(c), SETTEXT)
    c += b"\x5b"                                    # pop ebx
    done = len(c)
    c += b"\xc3"
    c[jne_at + 1] = done - (jne_at + 2)
    return bytes(c)


def _entry(base, flag, replay, resume, save_state):
    """Shared shape for the settings entry hooks (eax=form, edx=Sender)."""
    c = bytearray()
    c += b"\x50\x52"                                # push eax; push edx
    c += b"\xb2" + bytes([flag])                    # mov dl,flag
    c += call(base + len(c), SETBOTH)
    if save_state:                                  # OK: checkbox -> registry
        c += b"\xa1" + dd(CBVAR)
        c += bytes.fromhex("85c0")
        skip_at = len(c)
        c += b"\x74\x00"
        c += call(base + len(c), GETCHECKED)        # al = Checked
        c += bytes.fromhex("8ad0")                  # mov dl,al
        c += b"\xa1" + dd(REG_OBJ)
        c += call(base + len(c), CHEAT_SET)
        c[skip_at + 1] = len(c) - (skip_at + 2)
    else:                                           # open: create + load state
        c += bytes.fromhex("8b442404")              # mov eax,[esp+4] (form)
        c += call(base + len(c), ENSURE)
        c += b"\xa1" + dd(REG_OBJ)
        c += call(base + len(c), CHEAT_GET)         # al = stored value
        c += bytes.fromhex("8ad0")                  # mov dl,al
        c += b"\xa1" + dd(CBVAR)
        c += bytes.fromhex("85c0")
        skip_at = len(c)
        c += b"\x74\x00"
        c += call(base + len(c), SETCHECKED)
        c[skip_at + 1] = len(c) - (skip_at + 2)
    c += b"\x5a\x58"                                # pop edx; pop eax
    c += replay
    c += jmp(base + len(c), resume)
    return bytes(c)


def build_show():
    return _entry(SHOW, 1, SBTN_OLD, SBTN_RESUME, save_state=False)


def build_hideok():
    return _entry(HIDEOK, 0, OK_OLD, OK_RESUME, save_state=True)


def build_hidecancel():
    c = bytearray()
    c += b"\x50\x52\xb2\x00"
    c += call(HIDECAN + len(c), SETBOTH)
    c += b"\x5a\x58"
    c += CAN_OLD
    c += jmp(HIDECAN + len(c), CAN_RESUME)
    return bytes(c)


def build_startaow():
    """Fills the lpParameters buffer, then replays the three ShellExecute pushes."""
    c = bytearray()
    c += b"\x50\x52"                                # push eax; push edx
    c += b"\xa1" + dd(REG_OBJ)
    c += call(STARTAOW + len(c), CHEAT_GET)         # al = cheat enabled?
    c += bytes.fromhex("84c0")                      # test al,al
    off_at = len(c)
    c += b"\x74\x00"                                # je off
    c += b"\xc7\x05" + dd(BUF) + dd(0x74616562)     # 'beat'
    c += b"\xc7\x05" + dd(BUF + 4) + dd(0x00786972)  # 'rix\0'
    cont_at = len(c)
    c += b"\xeb\x00"                                # jmp cont
    c[off_at + 1] = len(c) - (off_at + 2)
    c += b"\xc6\x05" + dd(BUF) + b"\x00"            # mov byte [BUF],0
    c[cont_at + 1] = len(c) - (cont_at + 2)
    c += b"\x5a\x58"                                # pop edx; pop eax
    c += b"\x6a\x01"                                # push 1        nShowCmd
    c += b"\x68" + dd(0x4688D4)                     # push ''       lpDirectory
    c += b"\x68" + dd(BUF)                          # push BUF      lpParameters
    c += jmp(STARTAOW + len(c), START_RESUME)
    return bytes(c)


# ---------------- reloc handling ----------------
def reloc_entries(d):
    import pefile
    pe = pefile.PE(data=bytes(d), fast_load=True)
    sec = next(s for s in pe.sections if s.Name.startswith(b".reloc"))
    raw, size = sec.PointerToRawData, sec.SizeOfRawData
    off = raw
    while off + 8 <= raw + size:
        page, blk = struct.unpack_from("<II", d, off)
        if blk < 8:
            break
        for eo in range(off + 8, min(off + blk, raw + size), 2):
            w = struct.unpack_from("<H", d, eo)[0]
            yield eo, w, 0x400000 + page + (w & 0xFFF)
        off += blk


def set_reloc_types(d, ranges, to_type):
    n = 0
    for eo, w, va in list(reloc_entries(d)):
        if (w >> 12) in (0, 3) and any(a <= va < b for a, b in ranges):
            if (w >> 12) != to_type:
                struct.pack_into("<H", d, eo, (to_type << 12) | (w & 0xFFF))
                n += 1
    return n


def data_exec(d, enable):
    import pefile
    pe = pefile.PE(data=bytes(d), fast_load=True)
    sec = next(s for s in pe.sections if s.Name.startswith(b"DATA"))
    off = sec.get_file_offset() + 36                # Characteristics field
    ch = struct.unpack_from("<I", d, off)[0]
    new = (ch | 0x20000000) if enable else (ch & ~0x20000000)
    struct.pack_into("<I", d, off, new)
    return ch, new


# ---------------- driver ----------------
def layout():
    caves_code = [(STR_DOT, astr(".")), (PATH_CODE, build_path_cave()),
                  (SETBOTH, build_setboth()), (CHEAT_GET, build_cheat_get()),
                  (CHEAT_SET, build_cheat_set()),
                  (EDSTR, astr("\\AoWDevX.exe")), (HIDECAN, build_hidecancel())]
    caves_data = [(STR_CHEAT, astr("Cheat Mode")), (ENSURE, build_ensure()),
                  (SHOW, build_show()), (HIDEOK, build_hideok()),
                  (STARTAOW, build_startaow())]
    hooks = [
        (HOOK_VA, HOOK_OLD, call(HOOK_VA, PATH_CODE)),
        (EDMOV_VA, EDMOV_OLD, b"\xba" + dd(EDSTR + 8)),
        (AOWX_VA, AOWX_OLD, AOWX_NEW),
        (START_VA, START_OLD,
         jmp(START_VA, STARTAOW) + b"\x90" * (len(START_OLD) - 5)),
        (SBTN_VA, SBTN_OLD, jmp(SBTN_VA, SHOW) + b"\x90" * (len(SBTN_OLD) - 5)),
        (OK_VA, OK_OLD, jmp(OK_VA, HIDEOK) + b"\x90" * (len(OK_OLD) - 5)),
        (CAN_VA, CAN_OLD, jmp(CAN_VA, HIDECAN) + b"\x90" * (len(CAN_OLD) - 5)),
    ]
    return caves_code, caves_data, hooks


def check_fit(caves, limit, label):
    items = sorted(caves)
    for (va, blob), nxt in zip(items, items[1:] + [(limit, b"")]):
        assert va + len(blob) <= nxt[0], \
            f"{label}: cave @{va:#x} ({len(blob)} B) overruns {nxt[0]:#x}"


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--status"
    d = bytearray(open(EXE, "rb").read())
    caves_code, caves_data, hooks = layout()
    check_fit(caves_code, CODE_END, "CODE")
    check_fit(caves_data, DATA_END, "DATA")
    ranges = [(va, va + len(old)) for va, old, _ in hooks]

    if mode == "--status":
        st = []
        for va, old, new in hooks:
            cur = bytes(d[va - D:va - D + len(old)])
            st.append("v3" if cur == new else "stock" if cur == old else "??")
        import pefile
        pe = pefile.PE(data=bytes(d), fast_load=True)
        sec = next(s for s in pe.sections if s.Name.startswith(b"DATA"))
        print("hooks:", st)
        print("DATA executable:", bool(sec.Characteristics & 0x20000000))
        return 0

    if mode == "--apply":
        for va, old, new in hooks:
            cur = bytes(d[va - D:va - D + len(old)])
            assert cur == old, f"{va:#x}: unexpected bytes {cur.hex()}"
        for va, blob in caves_code:
            assert all(b == 0 for b in d[va - D:va - D + len(blob)]), \
                f"CODE cave @{va:#x} not empty"
        for va, blob in caves_data:
            assert all(b == 0 for b in d[va - DATA_D:va - DATA_D + len(blob)]), \
                f"DATA cave @{va:#x} not empty"
        if not os.path.exists(BAK):
            shutil.copy2(EXE, BAK)
            print("backup ->", os.path.basename(BAK))
        for va, blob in caves_code:
            d[va - D:va - D + len(blob)] = blob
        for va, blob in caves_data:
            d[va - DATA_D:va - DATA_D + len(blob)] = blob
        for va, old, new in hooks:
            d[va - D:va - D + len(old)] = new
        n = set_reloc_types(d, ranges, 0)
        old_ch, new_ch = data_exec(d, True)
        # read every cave back at its VA through the section maps, so a wrong
        # VA->file constant cannot silently leave hooks pointing at slack
        import pefile
        pe = pefile.PE(data=bytes(d), fast_load=True)
        for va, blob in caves_code + caves_data:
            fo = pe.get_offset_from_rva(va - 0x400000)
            assert bytes(d[fo:fo + len(blob)]) == blob, \
                f"cave @{va:#x} not readable back at its VA (file {fo:#x})"
        open(EXE, "wb").write(d)
        print(f"APPLIED v3: install-check fallback, Developer tab, AoWDevX/AoWx "
              f"launch targets, Cheat Mode toggle")
        print(f"  relocs neutralized: {n};  DATA {old_ch:#x} -> {new_ch:#x}")
        return 0

    if mode == "--revert":
        for va, old, new in hooks:
            d[va - D:va - D + len(old)] = old
        for va, blob in caves_code:
            d[va - D:va - D + len(blob)] = bytes(len(blob))
        for va, blob in caves_data:
            d[va - DATA_D:va - DATA_D + len(blob)] = bytes(len(blob))
        n = set_reloc_types(d, ranges, 3)
        data_exec(d, False)
        open(EXE, "wb").write(d)
        print(f"reverted to stock behaviour (relocs restored: {n})")
        return 0

    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
