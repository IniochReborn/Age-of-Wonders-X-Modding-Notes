#!/usr/bin/env python3
r"""AoWSetup -- "AoWx Error Logs" checkbox on the Developer tab (2026-11-20).

User: "in developer settings of AoWSetup, add a new toggle for 'AoWx Error Logs'. it should be on by default".
    HKCU\Software\Triumph Studios\Age of Wonders X\General\"AoWx Error Logs"   REG_DWORD 1 (on) / 0 (off)
    missing / not a DWORD -> ON.  Re-read on every Settings open, written on OK, Cancel changes nothing.
AoWxLog.dll (build_aowxlog.py) reads the same value when the game / editor starts: off = no error log, no
Out-of-Sync record, no bug-report saves.

LAYOUT (Developer tab): Auto Save 222, [NEW 243], Cheat Mode 264 (devtab runtime box: 112, 264, 141x17).
    new TCheckBox (112, 243, 200 x 17), runtime control -> English in every language.

MACHINERY: AoWSetup's section table is FULL -> the last section .xftx (VA 0x515000) is GROWN 0x3000 -> 0x4000, our zone
VA 0x518000..0x519000 'ELC1' (old sizes kept in the zone header for an exact revert).
HOOK CHAIN: SettingsBtnClick 0x4689F4 / SettingsOk 0x469090 site jmps (today -> the audio tab's caves) are re-pointed
to our caves, which tail-jmp through stored slots to the previous targets.
CHAIN ORDER: devtab -> mouse_tab -> campaign_dropdown -> hexgrid_dropdown -> flavor_checkbox -> updater_settings ->
audio_tab -> THIS.  !! LIFO: revert THIS first (an earlier script's revert would cut this zone off).  Re-running an
earlier script's --apply re-points the sites to itself -> re-run this one afterwards.

Usage: py -3.10 build_aowsetup_errorlog_checkbox.py [--apply | --revert] [--exe PATH]   (dry-run default)
Backup: backup\AoWSetup.exe.bak_errlogcb.
"""
import os
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bakpath import bak_path, game_file
import build_aowsetup_hexgrid_dropdown as HG

IMAGE_BASE = 0x400000
HOST_NAME = b".xftx"
HOST_VA = 0x515000
HOST_OLD, HOST_NEW = 0x3000, 0x4000
ZONE_VA, ZONE_SIZE = 0x518000, 0x1000
MAGIC = b"ELC1"
Z_PREV_SHOW, Z_PREV_OK, Z_OLDVS, Z_OLDRAW = 0x04, 0x08, 0x0C, 0x10

CHK_VMT, CHK_CTOR, CHK_GET, CHK_SET = 0x00430368, 0x004345D4, 0x00434694, 0x004346B4
SETTEXT = HG.SETTEXT
SLOT_SETPARENT, SLOT_SETBOUNDS = 0x3C, 0x4C
OFF_DEVSHEET = 0x224
HKCU = 0x80000001
SBTN_VA, OK_VA, CODE_D = HG.SBTN_VA, HG.OK_VA, HG.CODE_D
SUBKEY = HG.SUBKEY
VALNAME = b"AoWx Error Logs"
S_CAPTION = b"AoWx Error Logs"
CB_X, CB_Y, CB_W, CB_H = 112, 243, 200, 17

D_CAPTION, D_SUBKEY, D_VALNAME = 0x20, 0x50, 0x90      # 48 / 64 / 32 B AnsiString blocks (chars at +8)
D_GCB, D_HKEY, D_TYPE, D_SIZE, D_BUF, D_VAL = 0xB0, 0xB4, 0xB8, 0xBC, 0xC0, 0xC8
D_CODE = 0x100

SRC = """
el_show:
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
    push {cb_w:#x}
    push {cb_h:#x}
    mov  ecx, {cb_y:#x}
    mov  edx, {cb_x:#x}
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

el_ok:
    pushad
    mov  eax, dword ptr [{g_cb:#x}]
    test eax, eax
    jz   _okout
    call {chk_get:#x}
    movzx eax, al
    mov  dword ptr [{g_val:#x}], eax
    push {g_type:#x}
    push {g_hkey:#x}
    push 0x0
    push 0x2
    push 0x0
    push 0x0
    push 0x0
    push {s_subkey:#x}
    push {hkcu:#x}
    call dword ptr [{regcreate:#x}]
    test eax, eax
    jnz  _okout
    push 0x4
    push {g_val:#x}
    push 0x4
    push 0x0
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
    push 0x1
    push 0x0
    push {s_subkey:#x}
    push {hkcu:#x}
    call dword ptr [{regopen:#x}]
    test eax, eax
    jnz  _rron
    mov  dword ptr [{g_size:#x}], 0x8
    mov  dword ptr [{g_type:#x}], 0x0
    push {g_size:#x}
    push {g_buf:#x}
    push {g_type:#x}
    push 0x0
    push {s_valname:#x}
    push dword ptr [{g_hkey:#x}]
    call dword ptr [{regquery:#x}]
    push eax
    push dword ptr [{g_hkey:#x}]
    call dword ptr [{regclose:#x}]
    pop  eax
    test eax, eax
    jnz  _rron
    cmp  dword ptr [{g_type:#x}], 0x4
    jne  _rron
    xor  eax, eax
    cmp  dword ptr [{g_buf:#x}], 0x0
    setne al
    ret
_rron:
    mov  eax, 0x1
    ret
"""


def build_zone(prev_show, prev_ok, old_vs, old_raw):
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    Z = ZONE_VA
    src = SRC.format(
        g_cb=Z + D_GCB, g_hkey=Z + D_HKEY, g_type=Z + D_TYPE, g_size=Z + D_SIZE, g_buf=Z + D_BUF, g_val=Z + D_VAL,
        tail_show=Z + Z_PREV_SHOW, tail_ok=Z + Z_PREV_OK,
        s_caption=Z + D_CAPTION + 8, s_subkey=Z + D_SUBKEY + 8, s_valname=Z + D_VALNAME + 8,
        chk_vmt=CHK_VMT, chk_ctor=CHK_CTOR, chk_get=CHK_GET, chk_set=CHK_SET, settext=SETTEXT,
        sheet=OFF_DEVSHEET, setparent=SLOT_SETPARENT, setbounds=SLOT_SETBOUNDS,
        regopen=HG.IAT_REGOPEN, regquery=HG.IAT_REGQUERY, regcreate=HG.IAT_REGCREATE, regset=HG.IAT_REGSET,
        regclose=HG.IAT_REGCLOSE, hkcu=HKCU, cb_x=CB_X, cb_y=CB_Y, cb_w=CB_W, cb_h=CB_H)
    code = bytes(Ks(KS_ARCH_X86, KS_MODE_32).asm(src, Z + D_CODE)[0])
    i = code.find(b"\xFF\x25" + struct.pack("<I", Z + Z_PREV_SHOW))
    assert i != -1
    z = bytearray(ZONE_SIZE)
    z[0:4] = MAGIC
    struct.pack_into("<IIII", z, Z_PREV_SHOW, prev_show, prev_ok, old_vs, old_raw)
    z[D_CAPTION:D_CAPTION + 0x30] = HG.astr(S_CAPTION, 0x30)
    z[D_SUBKEY:D_SUBKEY + 64] = HG.astr(SUBKEY, 64)
    z[D_VALNAME:D_VALNAME + 32] = HG.astr(VALNAME, 32)
    assert D_CODE + len(code) <= ZONE_SIZE
    z[D_CODE:D_CODE + len(code)] = code
    return bytes(z), Z + D_CODE, Z + D_CODE + i + 6


def main():
    a = sys.argv[1:]
    do_apply, revert = "--apply" in a, "--revert" in a
    exe = a[a.index("--exe") + 1] if "--exe" in a else game_file("AoWSetup.exe")
    bak = bak_path(exe, ".bak_errlogcb", create=do_apply)
    d = bytearray(open(exe, "rb").read())
    F = HG.load_pe(d)
    hs = None
    for s in F["secs"]:
        if d[s[5]:s[5] + 5] == HOST_NAME: hs = s
    assert hs is not None and hs[1] + IMAGE_BASE == HOST_VA, ".xftx not found"
    is_last = F["secs"][-1][5] == hs[5]
    sb_off, ok_off = SBTN_VA - CODE_D, OK_VA - CODE_D
    sb_t = HG.site_target(d, sb_off) + CODE_D
    ok_t = HG.site_target(d, ok_off) + CODE_D
    mine = lambda va: ZONE_VA <= va < ZONE_VA + ZONE_SIZE
    zraw = hs[3] + (ZONE_VA - HOST_VA)
    present = hs[2] >= HOST_NEW and hs[4] >= HOST_NEW and bytes(d[zraw:zraw + 4]) == MAGIC
    print("target %s\n  .xftx VS %#x raw %#x (last: %s); zone %s" % (exe, hs[2], hs[4], is_last, "PRESENT" if present else "absent"))
    print("  SettingsBtn -> %08X  SettingsOk -> %08X  (%s)" % (sb_t, ok_t, "OURS" if mine(sb_t) and mine(ok_t) else "prev owners"))

    if revert:
        if not present:
            print("ALREADY VANILLA"); return 0
        p_show, p_ok, old_vs, old_raw = struct.unpack_from("<IIII", d, zraw + Z_PREV_SHOW)
        if mine(sb_t): struct.pack_into("<i", d, sb_off + 1, p_show - (SBTN_VA + 5))
        if mine(ok_t): struct.pack_into("<i", d, ok_off + 1, p_ok - (OK_VA + 5))
        assert is_last, ".xftx is no longer the last section"
        del d[hs[3] + old_raw:]
        struct.pack_into("<I", d, hs[5] + 8, old_vs)
        struct.pack_into("<I", d, hs[5] + 16, old_raw)
        F2 = HG.load_pe(d)
        struct.pack_into("<I", d, F2["opt"] + 56, HG.align(max(s[1] + max(s[2], s[4]) for s in F2["secs"]), F2["salign"]))
        try:
            with open(exe, "r+b") as f:
                f.seek(0); f.write(bytes(d)); f.truncate()
        except PermissionError:
            print("LOCKED - close AoWSetup.exe and retry"); return 1
        if os.path.exists(bak):
            print("  %s backup" % ("EQUALS" if open(exe, "rb").read() == open(bak, "rb").read() else "DIFFERS FROM"))
        print("REVERTED"); return 0

    if present:
        p_show, p_ok, old_vs, old_raw = struct.unpack_from("<IIII", d, zraw + Z_PREV_SHOW)
        if not mine(sb_t): p_show = sb_t
        if not mine(ok_t): p_ok = ok_t
    else:
        p_show, p_ok, old_vs, old_raw = sb_t, ok_t, hs[2], hs[4]
    assert not (mine(p_show) or mine(p_ok))
    zone, show_va, ok_va = build_zone(p_show, p_ok, old_vs, old_raw)
    print("  el_show %08X  el_ok %08X; tails %08X / %08X" % (show_va, ok_va, p_show, p_ok))
    if present and mine(sb_t) and mine(ok_t) and bytes(d[zraw:zraw + ZONE_SIZE]) == zone:
        print("ALREADY APPLIED"); return 0
    if not present:
        assert is_last, ".xftx must be the last section"
        assert len(d) == hs[3] + hs[4], "file has an overlay - refusing"
        assert hs[2] == HOST_OLD and hs[4] == HOST_OLD, ".xftx size unexpected (%#x / %#x)" % (hs[2], hs[4])
    if not do_apply:
        print("dry run OK (--apply / --revert)"); return 0
    if not os.path.isfile(bak):
        shutil.copy2(exe, bak); print("  backup -> %s" % bak)
    if not present:
        d += bytes(hs[3] + HOST_NEW - len(d))
        struct.pack_into("<I", d, hs[5] + 8, HOST_NEW)
        struct.pack_into("<I", d, hs[5] + 16, HOST_NEW)
        F2 = HG.load_pe(d)
        soi = HG.align(max(s[1] + max(s[2], s[4]) for s in F2["secs"]), F2["salign"])
        struct.pack_into("<I", d, F2["opt"] + 56, soi)
        print("  .xftx grown to %#x (SizeOfImage %#x)" % (HOST_NEW, soi))
    d[zraw:zraw + ZONE_SIZE] = zone
    struct.pack_into("<i", d, sb_off + 1, show_va - (SBTN_VA + 5))
    struct.pack_into("<i", d, ok_off + 1, ok_va - (OK_VA + 5))
    try:
        with open(exe, "r+b") as f:
            f.seek(0); f.write(bytes(d)); f.truncate()
    except PermissionError:
        print("LOCKED - close AoWSetup.exe and retry"); return 1
    print("APPLIED - AoWSetup -> Settings -> Developer: 'AoWx Error Logs' checkbox; OK saves General\\\"AoWx Error Logs\" (1/0).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
