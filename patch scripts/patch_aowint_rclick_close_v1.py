#!/usr/bin/env python3
r"""aowInt.dpl: RIGHT-CLICK OUTSIDE closes the open game window (2026-10-24, user request).

Windows (AoWx.exe dialog class -> how it is recognised -> how it is closed):
    TRelWindow       (relations)              OnKeyDown = RelWinKeyDown 0x4273C0   -> handler(VK_ESCAPE)
    TUnitWindow      (unit window)            OnKeyDown = UnitWinKeyDown 0x40ABD4  -> handler(VK_ESCAPE)
    TPowerDlg        (power distribution)     OnKeyDown = DlgKeyDown 0x42C100      -> handler(VK_ESCAPE)
    TSpellBook       (research / casting)     OnKeyDown = DlgKeyDown 0x43129C      -> handler(VK_ESCAPE)
    THeroUpgradeDlg  (leader / hero level-up) OnKeyDown = DlgKeyDown 0x447510      -> handler(VK_ESCAPE)
    TConstructDlg    (city / shipyard / builders guild build list) OnKeyDown 0x431A3C -> handler(VK_ESCAPE)
    TWizardsTowerDlg (wizard's tower)         OnKeyDown = DlgKeyDown 0x44BD18      -> handler(VK_ESCAPE)
    TArenaDlg        (arena)                  OnKeyDown = DlgKeyDown 0x44C840      -> handler(VK_ESCAPE)
    TIWindow         (structure / city info)  OnResize  = InfoWinResize 0x4420D0   -> CloseClick 0x442118 (sender nil)
    TCityScreen / TProductionScreen (v1.3)    OnKeyDown 0x43E290 / 0x441550         -> handler(VK_ESCAPE)
    TWorldMap book (scenario info, v1.4)      OnShow = BookWinShow 0x41E400 (book window, Self [w+0x1E0]) -> BookStartClick 0x41E358
Every one of those ESC handlers is `cmp word [key],0x1B / jne / [self+win].SetVisible(False) (VMT+0x6C)`, i.e. exactly
what pressing Escape does today (OnHide handlers etc. run as usual).

RE (aowInt): TAOWWinManager.CheckMouseDown 0x59806F10 (eax mgr, dl button: 0 left / 1 right, cl shift; stack y, x;
ret 8) walks the manager's window list [mgr+0xD0] (TList: items +4, count +8) topmost-first (last = top), skipping
windows whose layer [w+0xA0] is below the modal floor [mgr+0x10C]; TAOWWindow.CheckMouseDown claims [w+0x78] when
x in (left-1, left+w), y in (top-1, top+h) (left +0x84, top +0x88, w +0x7C, h +0x80, visible byte +0x75); afterwards
the manager ALWAYS fires its own OnMouseDown [mgr+0x44] (the map).  Window events (RTTI): OnKeyDown code +0x64 /
Self +0x68, OnResize +0x130 / +0x134.
Hook: 0x59806F10 (6 B `push ebp / mov ebp,esp / add esp,-8`) -> cave 'RCC1' 0x59824000..0x59824400 (CODE tail zeros):
  right button only: walk visible windows (layer >= floor) top-down; if ANY window contains the click -> normal
  (so right-clicks on the unit panel / taskbar / another window keep their usual meaning); if the click hits no window
  (= the map) and a TARGET window is open, the topmost target is closed, [mgr+0x78] := -1 and the click is consumed
  (no map order).  Everything else replays the prologue.
Calls into AoWx.exe use absolute immediates (`mov ecx, imm / call ecx` or the handler pointer from the window) - no
rel32 across modules; AoWx.exe has no ASLR.  No relocs at the site.  Backup <game>\backup\aowInt.dpl.bak_rclickclose.
Dry run by default; --apply / --revert.
"""
import os, shutil, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DPL = game_file("aowInt.dpl")
V2F = 0x59800C00
SITE, SITE_ORIG, SITE_BACK = 0x59806F10, bytes.fromhex("558bec83c4f8"), 0x59806F16
ZONE, ZONE_END = 0x59824000, 0x59824400
CODE = ZONE + 0x10
ESC_HANDLERS = [0x4273C0, 0x40ABD4, 0x42C100, 0x43129C, 0x447510, 0x431A3C, 0x44BD18, 0x44C840, 0x43E290, 0x441550]
INFOWIN_RESIZE, INFOWIN_CLOSE = 0x4420D0, 0x442118
UNITWIN_KD, CONTROLWIN_RESIZE = 0x40ABD4, 0x406018           # TUnitWindow.UnitWinKeyDown / TControlWin.ControlWindowResize


def src():
    cmps = "\n".join("    cmp  eax, %#x\n    je   r_tgt" % a for a in ESC_HANDLERS)
    cmps2 = "\n".join("    cmp  eax, %#x\n    je   c_esc" % a for a in ESC_HANDLERS)
    return """
    pushad
    mov  ebp, esp
    push 0
    push 0
    mov  edi, eax
    mov  esi, dword ptr [edi + 0xD0]
    test esi, esi
    jz   done
    mov  ecx, dword ptr [esi + 8]
    cmp  byte ptr [ebp + 0x14], 1
    je   rlp
    cmp  byte ptr [ebp + 0x14], 0
    jne  done
llp:
    dec  ecx
    js   done
    mov  eax, dword ptr [esi + 4]
    mov  ebx, dword ptr [eax + ecx*4]
    call vis
    jz   llp
    cmp  dword ptr [ebx + 0x64], %#x
    jne  l_nouw
    mov  dword ptr [ebp - 8], 1
l_nouw:
    call inside
    jz   llp
    cmp  dword ptr [ebx + 0x130], %#x
    jne  done
    cmp  dword ptr [ebp - 8], 0
    je   done
    mov  dword ptr [edi + 0x78], 0
    mov  dword ptr [ebx + 0x78], 0
    push dword ptr [ebp + 0x28]
    push dword ptr [ebp + 0x24]
    mov  eax, dword ptr [ebx]
    mov  eax, dword ptr [eax + 0x84]
    mov  dword ptr [ebp - 4], eax
    mov  dl, byte ptr [ebp + 0x14]
    mov  cl, byte ptr [ebp + 0x18]
    mov  eax, ebx
    call dword ptr [ebp - 4]
    jmp  consumed
rlp:
    dec  ecx
    js   done
    mov  eax, dword ptr [esi + 4]
    mov  ebx, dword ptr [eax + ecx*4]
    call vis
    jz   rlp
    mov  eax, dword ptr [ebx + 0x64]
%s
    cmp  dword ptr [ebx + 0x130], %#x
    je   r_tgt
    cmp  dword ptr [ebx + 0x1dc], 0x41e400
    je   r_tgt
    cmp  byte ptr [ebx + 0x104], 0
    jne  done
    jmp  rlp
r_tgt:
    call inside
    jnz  done
    cmp  dword ptr [ebx + 0x1dc], 0x41e400
    jne  r_notbook
    mov  eax, dword ptr [ebx + 0x1e0]
    xor  edx, edx
    mov  ecx, 0x41e358
    call ecx
    jmp  consumed
r_notbook:
    mov  eax, dword ptr [ebx + 0x64]
%s
    mov  eax, dword ptr [ebx + 0x134]
    xor  edx, edx
    mov  ecx, %#x
    call ecx
    jmp  consumed
c_esc:
    push 0x1B
    mov  ecx, esp
    push 0
    mov  edx, ebx
    mov  eax, dword ptr [ebx + 0x68]
    call dword ptr [ebx + 0x64]
    add  esp, 4
consumed:
    mov  dword ptr [edi + 0x78], 0xFFFFFFFF
    mov  esp, ebp
    popad
    ret  8
done:
    mov  esp, ebp
    popad
    push ebp
    mov  ebp, esp
    add  esp, -8
    jmp  %#x
vis:
    test ebx, ebx
    jz   vno
    cmp  byte ptr [ebx + 0x75], 1
    jne  vno
    mov  eax, dword ptr [ebx + 0xA0]
    cmp  eax, dword ptr [edi + 0x10C]
    jl   vno
    or   eax, 1
    ret
vno:
    xor  eax, eax
    ret
inside:
    mov  eax, dword ptr [ebx + 0x84]
    dec  eax
    cmp  eax, dword ptr [ebp + 0x28]
    jge  ino
    add  eax, dword ptr [ebx + 0x7C]
    inc  eax
    cmp  eax, dword ptr [ebp + 0x28]
    jle  ino
    mov  eax, dword ptr [ebx + 0x88]
    dec  eax
    cmp  eax, dword ptr [ebp + 0x24]
    jge  ino
    add  eax, dword ptr [ebx + 0x80]
    inc  eax
    cmp  eax, dword ptr [ebp + 0x24]
    jle  ino
    or   eax, 1
    ret
ino:
    xor  eax, eax
    ret
""" % (UNITWIN_KD, CONTROLWIN_RESIZE, cmps, INFOWIN_RESIZE, cmps2, INFOWIN_CLOSE, SITE_BACK)


def build():
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    code = bytes(Ks(KS_ARCH_X86, KS_MODE_32).asm(src(), CODE)[0])
    z = bytearray(ZONE_END - ZONE)
    z[0:4] = b"RCC1"
    z[4:4 + len(SITE_ORIG)] = SITE_ORIG
    assert 0x10 + len(code) <= len(z)
    z[0x10:0x10 + len(code)] = code
    rel = CODE - (SITE + 5)
    site = b"\xe9" + rel.to_bytes(4, "little", signed=True) + b"\x90"
    return bytes(z), site


def relocs(lo, hi):
    import pefile
    pe = pefile.PE(DPL, fast_load=True)
    pe.parse_data_directories([pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_BASERELOC"]])
    ib = pe.OPTIONAL_HEADER.ImageBase
    return [hex(ib + e.rva) for b in getattr(pe, "DIRECTORY_ENTRY_BASERELOC", []) for e in b.entries
            if e.type and lo - 3 <= ib + e.rva < hi]


def main():
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    d = open(DPL, "rb").read()
    g = lambda va, n: d[va - V2F:va - V2F + n]
    zone, site = build()
    s_now, z_now = g(SITE, 6), g(ZONE, ZONE_END - ZONE)
    state = ("vanilla" if s_now == SITE_ORIG and not any(z_now) else
             "ours" if s_now == site and z_now == zone else
             "older build" if s_now == site and z_now[:4] == b"RCC1" else "OTHER")
    print("CheckMouseDown %#x: %s | zone %#x %s -> %s" % (SITE, s_now.hex(), ZONE, "zero" if not any(z_now) else z_now[:4], state))
    if state == "OTHER": print("ABORT (site or zone used by another patch)"); return 1
    bad = relocs(SITE, SITE + 6) + relocs(ZONE, ZONE_END)
    if bad: print("ABORT: relocs", bad); return 1
    if state == ("vanilla" if revert else "ours"): print("already %s" % ("reverted" if revert else "applied")); return 0
    if not apply and not revert: print("Dry run OK (%d B code) - rerun with --apply (or --revert)." % len(zone.rstrip(b"\0"))); return 0
    bak = bak_path(DPL, ".bak_rclickclose")
    if not revert and not os.path.exists(bak): shutil.copy2(DPL, bak); print("backup ->", bak)
    ws, wz = (SITE_ORIG, bytes(len(zone))) if revert else (site, zone)
    try:
        with open(DPL, "r+b") as f:                  # in-place (house rule)
            f.seek(SITE - V2F); f.write(ws)
            f.seek(ZONE - V2F); f.write(wz)
    except PermissionError:
        print("LOCKED - close AoWx.exe and retry"); return 1
    d2 = open(DPL, "rb").read()
    assert d2[SITE - V2F:SITE - V2F + 6] == ws and d2[ZONE - V2F:ZONE - V2F + len(wz)] == wz
    print("reverted" if revert else "Written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
