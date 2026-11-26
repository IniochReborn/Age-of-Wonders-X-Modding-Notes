"""patch_start_maximized_v1.py  [--apply | --revert]

AoWx.exe: in windowed mode the game always STARTS with a maximised window.   (user 2026-11-19)

TMainForm.FormCreate 0x453184 restores the window state with
    0x45329D  call TAoWRegistry.GetMainWindowState (thunk 0x401FAC, eax = registry)   -> SetWindowState @0x4532A6
(the state is saved at exit, FormDestroy 0x45393D, so the window only came back maximised when the last copy that
closed happened to be maximised).  The call is redirected to a stub in our .xedt zone (0x62FF80):
    display mode (TAoWRegistry.GetDisplayMode, thunk 0x401F24) == 0 (windowed)  -> return 2 (wsMaximized)
    otherwise (1 fullscreen, 2 "Fullscreen (Optimized)")                         -> the saved state as before.
The exe never rebases and the site carries no relocation.  In-place apply/revert.
"""
import argparse, os, shutil, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path

EXE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "AoWx.exe")
V2F = 0x400C00
SITE, GET_STATE, GET_MODE = 0x45329D, 0x401FAC, 0x401F24
STUB, STUB_MAX = 0x62FF80, 0x20
XEDT_VA, XEDT_FO = 0x62F000, 0x228600


def rel(op, frm, to):
    return bytes([op]) + struct.pack("<i", to - (frm + 5))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    a = ap.parse_args()
    st = b"\x50"                                   # push eax (registry)
    st += rel(0xE8, STUB + len(st), GET_MODE)      # call GetDisplayMode
    st += b"\x84\xc0\x58"                          # test al, al / pop eax
    st += b"\x75\x06"                              # jnz +6
    st += b"\xb8\x02\x00\x00\x00\xc3"              # mov eax, 2 / ret
    st += rel(0xE9, STUB + len(st), GET_STATE)     # jmp GetMainWindowState
    assert len(st) <= STUB_MAX
    orig, new = rel(0xE8, SITE, GET_STATE), rel(0xE8, SITE, STUB)
    d = open(EXE, "rb").read()
    so = XEDT_FO + STUB - XEDT_VA
    scur, zcur = d[SITE - V2F:SITE - V2F + 5], d[so:so + STUB_MAX]
    vanilla = scur == orig and not any(zcur)
    ours = scur == new and zcur == st + bytes(STUB_MAX - len(st))
    state = "vanilla" if vanilla else "ours" if ours else "OTHER"
    print("site %#x, stub %#x (%d B): %s" % (SITE, STUB, len(st), state))
    if state == "OTHER": print("ABORT: foreign bytes", scur.hex(), zcur.hex()); return 1
    if state == ("vanilla" if a.revert else "ours"): print("already %s" % ("reverted" if a.revert else "applied")); return 0
    if not (a.apply or a.revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    b = bak_path(EXE, ".bak_startmax")
    if a.apply and not os.path.exists(b): shutil.copy2(EXE, b); print("backup ->", b)
    with open(EXE, "r+b") as f:
        f.seek(so); f.write(st + bytes(STUB_MAX - len(st)) if a.apply else bytes(STUB_MAX))
        f.seek(SITE - V2F); f.write(new if a.apply else orig)
    print("Written" if a.apply else "reverted")
    return 0


if __name__ == "__main__":
    sys.exit(main())
