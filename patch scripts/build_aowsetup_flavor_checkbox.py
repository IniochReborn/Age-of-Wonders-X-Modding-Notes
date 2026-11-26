#!/usr/bin/env python3
r"""AoWSetup -- "Title Screen Flavor Text" checkbox on the Settings tab (2026-10-19).

User: "in aowsetup settings, add a fourth checkbox that reads 'Title Screen Flavor Text'. Toggling it off should make
our quotes not visible."  Checked = the title screen shows a quote (patch_exe_title_quotes_v3.py reads the same value).
    HKCU\Software\Triumph Studios\Age of Wonders X\General\"Title Flavor Text"   REG_DWORD 1 (on) / 0 (off)
    missing / not a DWORD -> ON.   Saved on Settings OK; Cancel changes nothing (the box is re-read from the registry
    every time the Settings tab opens).

LAYOUT: the three existing checkboxes are SkipIntroBox (14,200,177x21) + UseDSound (192,200,177x21) on one row and
AllowResolutionSwitchesCB (14,226,337x21) alone below.  The new box takes the free right half of that second row:
    AllowResolutionSwitchesCB  Width 337 -> 177  (in-place DFM integer edit, same I16 encoding = same length)
    new TCheckBox              (192, 226, 177 x 21)  caption "Title Screen Flavor Text"
-> a 2x2 grid; nothing else moves (the tab keeps the hex-grid dropdown's layout).  The box is a runtime VCL control
(like the Campaigns / hex-grid rows) -> English in every language.

RE (AoWSetup.exe, Delphi 3 VMT: selfptr -0x40, typeinfo -0x30, classname -0x20):
  TCheckBox VMT 0x430368, ctor = slot +0x24 0x4345D4 (same slot as TComboBox 0x4333C0 / TLabel 0x431CEC);
  RTTI 'Checked': GetChecked 0x434694 (al), SetChecked 0x4346B4 (eax self, dl bool) -> FState, so a later click
  toggles from the right state (a raw BM_SETCHECK would desync VCL's FState).  SetParent [vmt+0x3C], SetBounds
  [vmt+0x4C], Caption = TControl.SetText 0x41CA24.  SettingsSheet = [form+0x1EC].  advapi32 IAT as in
  build_aowsetup_hexgrid_dropdown.py.

MACHINERY: new RWX section .xftx @VA 0x515000 (RVA 0x115000 = the current SizeOfImage; it takes the LAST free
section-header slot - AoWSetup's header table is FULL afterwards).  HOOK CHAIN: the SettingsBtnClick (0x4689F4) and
SettingsOk (0x469090) site jmps currently point at the hex-grid dropdown's caves (.xhgd); they are re-pointed here and
our caves tail-jmp (through stored slots) to whatever the sites pointed at before.
CHAIN ORDER: devtab -> mouse_tab -> campaign_dropdown -> hexgrid_dropdown -> THIS.  Revert THIS one first (LIFO);
re-running an earlier script re-points the sites to itself -> re-run this one afterwards.

Usage: py -3.10 build_aowsetup_flavor_checkbox.py [--apply | --revert] [--exe PATH]   (dry-run default)
Backup: backup\AoWSetup.exe.bak_flavorcb.  --revert restores the two site jmps + the DFM width and removes .xftx while
it is the last section (else zeroes its body) -> byte-identical to the pre-apply file.
"""
import os
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bakpath import bak_path, game_file
import dfm_edit as D
import build_aowsetup_hexgrid_dropdown as HG

IMAGE_BASE = 0x400000
SEC_VA = 0x515000            # RVA 0x115000
SEC_SIZE = 0x400
SEC_NAME = b".xftx\x00\x00\x00"

CHK_VMT, CHK_CTOR = 0x00430368, 0x004345D4
CHK_GET, CHK_SET = 0x00434694, 0x004346B4
SETTEXT = HG.SETTEXT
SLOT_SETPARENT, SLOT_SETBOUNDS = 0x3C, 0x4C
OFF_SETTINGSSHEET = 0x1EC
HKCU = 0x80000001
SBTN_VA, OK_VA = HG.SBTN_VA, HG.OK_VA
CODE_D = HG.CODE_D

SUBKEY = HG.SUBKEY
VALNAME = b"Title Flavor Text"
S_CAPTION = b"Title Screen Flavor Text"
CB_X, CB_Y, CB_W, CB_H = 192, 226, 177, 21

DFM_EDITS = [("/SettingsSheet/AllowResolutionSwitchesCB", "Width", 337, 177)]

# ---- data layout (offsets from SEC_VA) ----
D_CAPTION = 0x00             # 48 B
D_SUBKEY = 0x30              # 64 B
D_VALNAME = 0x70             # 32 B
D_GCB = 0x90
D_HKEY = 0x94
D_TYPE = 0x98
D_SIZE = 0x9C
D_BUF = 0xA0                 # 8 B
D_VAL = 0xA8
D_TAIL_SHOW = 0xAC
D_TAIL_OK = 0xB0
D_CODE = 0xC0

SRC = """
ft_show:
    pushad
    mov  ebp, eax
    cmp  dword ptr [{g_cb:#x}], 0
    jne  _have
    mov  ecx, ebp
    mov  dl, 1
    mov  eax, {chk_vmt:#x}
    call {chk_ctor:#x}
    mov  dword ptr [{g_cb:#x}], eax
    mov  ebx, eax
    mov  edx, dword ptr [ebp + {sheet:#x}]
    mov  ecx, dword ptr [eax]
    call dword ptr [ecx + {setparent:#x}]
    push {cb_w}
    push {cb_h}
    mov  ecx, {cb_y}
    mov  edx, {cb_x}
    mov  eax, ebx
    mov  edi, dword ptr [eax]
    call dword ptr [edi + {setbounds:#x}]
    mov  edx, {s_caption:#x}
    mov  eax, ebx
    call {settext:#x}
_have:
    call _readreg
    mov  edx, eax
    mov  eax, dword ptr [{g_cb:#x}]
    call {chk_set:#x}
    popad
    jmp  dword ptr [{tail_show:#x}]

ft_ok:
    pushad
    mov  eax, dword ptr [{g_cb:#x}]
    test eax, eax
    jz   _okout
    call {chk_get:#x}
    movzx eax, al
    mov  dword ptr [{g_val:#x}], eax
    push {g_type:#x}
    push {g_hkey:#x}
    push 0
    push 2
    push 0
    push 0
    push 0
    push {s_subkey:#x}
    push {hkcu:#x}
    call dword ptr [{regcreate:#x}]
    test eax, eax
    jnz  _okout
    push 4
    push {g_val:#x}
    push 4
    push 0
    push {s_valname:#x}
    push dword ptr [{g_hkey:#x}]
    call dword ptr [{regset:#x}]
    push dword ptr [{g_hkey:#x}]
    call dword ptr [{regclose:#x}]
_okout:
    popad
    jmp  dword ptr [{tail_ok:#x}]

_readreg:
    push {g_hkey:#x}
    push 1
    push 0
    push {s_subkey:#x}
    push {hkcu:#x}
    call dword ptr [{regopen:#x}]
    test eax, eax
    jnz  _rron
    mov  dword ptr [{g_size:#x}], 8
    mov  dword ptr [{g_type:#x}], 0
    push {g_size:#x}
    push {g_buf:#x}
    push {g_type:#x}
    push 0
    push {s_valname:#x}
    push dword ptr [{g_hkey:#x}]
    call dword ptr [{regquery:#x}]
    push eax
    push dword ptr [{g_hkey:#x}]
    call dword ptr [{regclose:#x}]
    pop  eax
    test eax, eax
    jnz  _rron
    cmp  dword ptr [{g_type:#x}], 4
    jne  _rron
    xor  eax, eax
    cmp  dword ptr [{g_buf:#x}], 0
    setne al
    ret
_rron:
    mov  eax, 1
    ret
"""


def build_code():
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    src = SRC.format(
        g_cb=SEC_VA + D_GCB, g_hkey=SEC_VA + D_HKEY, g_type=SEC_VA + D_TYPE, g_size=SEC_VA + D_SIZE,
        g_buf=SEC_VA + D_BUF, g_val=SEC_VA + D_VAL, tail_show=SEC_VA + D_TAIL_SHOW, tail_ok=SEC_VA + D_TAIL_OK,
        s_caption=SEC_VA + D_CAPTION + 8, s_subkey=SEC_VA + D_SUBKEY + 8, s_valname=SEC_VA + D_VALNAME + 8,
        chk_vmt=CHK_VMT, chk_ctor=CHK_CTOR, chk_get=CHK_GET, chk_set=CHK_SET, settext=SETTEXT,
        sheet=OFF_SETTINGSSHEET, setparent=SLOT_SETPARENT, setbounds=SLOT_SETBOUNDS,
        regopen=HG.IAT_REGOPEN, regquery=HG.IAT_REGQUERY, regcreate=HG.IAT_REGCREATE, regset=HG.IAT_REGSET,
        regclose=HG.IAT_REGCLOSE, hkcu=HKCU, cb_x=CB_X, cb_y=CB_Y, cb_w=CB_W, cb_h=CB_H)
    code = bytes(ks.asm(src, SEC_VA + D_CODE)[0])
    marker = b"\xFF\x25" + struct.pack("<I", SEC_VA + D_TAIL_SHOW)
    i = code.find(marker)
    assert i != -1, "tail_show jmp not found"
    return code, SEC_VA + D_CODE, SEC_VA + D_CODE + i + 6        # ft_ok starts right after the tail_show jmp


def build_body(tail_show, tail_ok):
    code, va_show, va_ok = build_code()
    body = bytearray(SEC_SIZE)
    body[D_CAPTION:D_CAPTION + 0x30] = HG.astr(S_CAPTION, 0x30)
    body[D_SUBKEY:D_SUBKEY + 64] = HG.astr(SUBKEY, 64)
    body[D_VALNAME:D_VALNAME + 32] = HG.astr(VALNAME, 32)
    struct.pack_into("<I", body, D_TAIL_SHOW, tail_show)
    struct.pack_into("<I", body, D_TAIL_OK, tail_ok)
    assert D_CODE + len(code) <= SEC_SIZE, len(code)
    body[D_CODE:D_CODE + len(code)] = code
    return bytes(body), va_show, va_ok


def dfm_sites(d):
    import pefile
    pe = pefile.PE(data=bytes(d))
    ent = None
    for t in pe.DIRECTORY_ENTRY_RESOURCE.entries:
        if t.id == 10:
            for x in t.directory.entries:
                if str(x.name) == "TLOADERFORM":
                    ent = x.directory.entries[0].data.struct
    assert ent is not None
    base = pe.get_offset_from_rva(ent.OffsetToData)
    dfm = bytes(d[base:base + ent.Size])
    w = D.walk(dfm)
    out = []
    for suffix, prop, old, new in DFM_EDITS:
        hits = [p for p in w.props if p[0].endswith(suffix) and p[1] == prop]
        assert len(hits) == 1, (suffix, prop, len(hits))
        _, _, t, a, b, val = hits[0]
        vstart = a + 1 + len(prop)
        assert t == D.I16, (suffix, prop, t)
        ob = bytes([t]) + struct.pack("<h", old)
        nb = bytes([t]) + struct.pack("<h", new)
        assert dfm[vstart:b] in (ob, nb), "%s.%s: unexpected value %r" % (suffix, prop, val)
        out.append((base + vstart, ob, nb))
    return out


def main():
    a = sys.argv[1:]
    do_apply, revert = "--apply" in a, "--revert" in a
    exe = a[a.index("--exe") + 1] if "--exe" in a else game_file("AoWSetup.exe")
    bak = bak_path(exe, ".bak_flavorcb", create=do_apply)
    d = bytearray(open(exe, "rb").read())
    F = HG.load_pe(d)
    sect = None
    for s in F["secs"]:
        if d[s[5]:s[5] + 5] == SEC_NAME[:5]:
            sect = s
    sb_off, ok_off = SBTN_VA - CODE_D, OK_VA - CODE_D
    sb_t = HG.site_target(d, sb_off) + CODE_D
    ok_t = HG.site_target(d, ok_off) + CODE_D
    mine = lambda va: SEC_VA <= va < SEC_VA + 0x1000
    dsites = dfm_sites(d)
    dnew = sum(bytes(d[o:o + len(ob)]) == nb for o, ob, nb in dsites)
    print("target %s" % exe)
    print("  SettingsBtn site -> %08X  (%s)" % (sb_t, "OURS" if mine(sb_t) else "prev owner"))
    print("  SettingsOk  site -> %08X  (%s)" % (ok_t, "OURS" if mine(ok_t) else "prev owner"))
    print("  section .xftx: %s;  AllowResolutionSwitchesCB width: %s" % (
        "present" if sect else "absent", "177 (ours)" if dnew else "337"))

    if revert:
        if not sect and not dnew:
            print("ALREADY VANILLA")
            return 0
        if sect:
            raw = sect[3]
            old_show = struct.unpack_from("<I", d, raw + D_TAIL_SHOW)[0]
            old_ok = struct.unpack_from("<I", d, raw + D_TAIL_OK)[0]
            if mine(sb_t):
                struct.pack_into("<i", d, sb_off + 1, old_show - (SBTN_VA + 5))
            if mine(ok_t):
                struct.pack_into("<i", d, ok_off + 1, old_ok - (OK_VA + 5))
            print("  sites -> %08X / %08X" % (old_show, old_ok))
        for o, ob, nb in dsites:
            d[o:o + len(ob)] = ob
        if sect:
            if F["secs"][-1][0] == ".xftx":
                del d[sect[3]:]
                d[sect[5]:sect[5] + 40] = bytes(40)
                struct.pack_into("<H", d, F["e"] + 6, F["n"] - 1)
                struct.pack_into("<I", d, F["opt"] + 56, SEC_VA - IMAGE_BASE)
                print("  removed .xftx (last section)")
            else:
                d[sect[3]:sect[3] + sect[4]] = bytes(sect[4])
                print("  .xftx is not the last section - body zeroed, header kept")
        try:
            with open(exe, "r+b") as f:
                f.seek(0); f.write(bytes(d)); f.truncate()
        except PermissionError:
            print("LOCKED - close AoWSetup.exe and retry")
            return 1
        if os.path.exists(bak):
            print("  %s backup" % ("EQUALS" if open(exe, "rb").read() == open(bak, "rb").read() else "DIFFERS FROM"))
        print("REVERTED")
        return 0

    tails = (sb_t, ok_t)
    if sect and mine(sb_t):
        raw = sect[3]
        tails = (struct.unpack_from("<I", d, raw + D_TAIL_SHOW)[0], struct.unpack_from("<I", d, raw + D_TAIL_OK)[0])
    assert not mine(tails[0]) and not mine(tails[1]), "tail points into our own section"
    body, va_show, va_ok = build_body(*tails)
    print("  ft_show @%08X, ft_ok @%08X, tails %08X / %08X" % (va_show, va_ok, tails[0], tails[1]))

    if sect and mine(sb_t) and mine(ok_t) and bytes(d[sect[3]:sect[3] + SEC_SIZE]) == body and dnew == len(dsites):
        print("ALREADY APPLIED")
        return 0
    if not sect:
        assert F["tbl"] + (F["n"] + 1) * 40 <= F["hdrsz"], "no section-header room"
        assert F["soi"] == SEC_VA - IMAGE_BASE, "SizeOfImage %#x != %#x" % (F["soi"], SEC_VA - IMAGE_BASE)
        last = F["secs"][-1]
        assert len(d) == last[3] + last[4], "file has an overlay - refusing"
    if not do_apply:
        print("dry run OK (--apply / --revert)")
        return 0

    if not os.path.isfile(bak):
        shutil.copy2(exe, bak)
        print("  backup -> %s" % bak)
    if sect:
        raw = sect[3]
        d[raw:raw + sect[4]] = bytes(sect[4])
        d[raw:raw + SEC_SIZE] = body
    else:
        newraw = HG.align(len(d), F["falign"])
        d += bytes(newraw - len(d))
        rawsz = HG.align(SEC_SIZE, F["falign"])
        d += body + bytes(rawsz - SEC_SIZE)
        b = F["tbl"] + F["n"] * 40
        struct.pack_into("<8sIIII", d, b, SEC_NAME, SEC_SIZE, SEC_VA - IMAGE_BASE, rawsz, newraw)
        struct.pack_into("<IIHHI", d, b + 24, 0, 0, 0, 0, 0xE0000060)
        struct.pack_into("<H", d, F["e"] + 6, F["n"] + 1)
        F2 = HG.load_pe(d)
        soi = HG.align(max(s[1] + max(s[2], s[4]) for s in F2["secs"]), F2["salign"])
        struct.pack_into("<I", d, F2["opt"] + 56, soi)
        print("  .xftx appended (section table now FULL), SizeOfImage -> 0x%X" % soi)
    struct.pack_into("<i", d, sb_off + 1, va_show - (SBTN_VA + 5))
    struct.pack_into("<i", d, ok_off + 1, va_ok - (OK_VA + 5))
    for o, ob, nb in dsites:
        d[o:o + len(nb)] = nb
    try:
        with open(exe, "r+b") as f:
            f.seek(0); f.write(bytes(d)); f.truncate()
    except PermissionError:
        print("LOCKED - close AoWSetup.exe and retry")
        return 1
    print("APPLIED - AoWSetup -> Settings: 'Title Screen Flavor Text' checkbox (right of Allow Resolution Switches); "
          "OK saves General\\\"Title Flavor Text\" (1/0).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
