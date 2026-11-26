#!/usr/bin/env python3
r"""
AoWx.exe: the LOAD-GAME dialog lists saves by last-modified date by default (2026-10-11).

TFileDlgWindow (VMT 0x41EB60, instance global [0x45B104]) serves three modes in [dlg+0x148]: **0 = Load** (probed
live 2026-10-11 - the earlier read-only-edit inference had 0/1 backwards), 1 = Save, 2 = New Game (.hsm scenarios).  Its
OnShow TFileDlgWindow.FileDialogShow @0x42058C configures the view for the mode and ends with
`mov eax,[0x45B104] / call FindDrives @0x41F1F4` (@0x4208C0/0x4208C5), which fills FileLB/SaveLB/DateLB in
directory (= alphabetical) order.  Clicking the Date column header runs DateBtnClick @0x420BD4: in modes 0/1 it
attaches DateLB's TDateTime objects to SaveLB's items and sorts them with Engine.SortStringsEx (comparator
@0x420B80 on the doubles at [obj+4]) with FileLB/DateLB as companions, re-selects the previous file by name and
calls FileLBChange.

v1 hooked the `call FindDrives` at the end of FileDialogShow - did NOT work: the Load path (0x41F140.., sets mode 1
@0x41F168, Show @0x41F179) calls FindFiles AGAIN @0x41F1AB after Show, refilling the lists alphabetically.
v2 patch: hook the 7-byte epilogue of FindFiles itself @0x41F90F (`pop edi/pop esi/pop ebx/mov esp,ebp/pop ebp/ret`,
also the finally block's return address pushed @0x41F8D9) -> cave: eax := ebx (self, set @0x41F44A), replay the
epilogue, then if [eax] == TFileDlgWindow VMT 0x41EB60 (guards the exception-unwind path) and [eax+0x148] == 1
(Load) call DateBtnClick(self); ret.  Every refill (show, drive/dir change) re-sorts.  New Game (mode 2) and Save (mode 0) keep the
alphabetical default.  The sort direction is whatever the Date header gives (clicking it again toggles nothing in
vanilla - it re-sorts the same way); SORT_TWICE below is a no-op placeholder if that ever needs flipping.

Cave @0x60ECC0 in `.xbfs`.  Backup <game>\backup\AoWx.exe.bak_datesort.  Dry run by default; --apply / --revert.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DEFAULT_EXE = game_file("AoWx.exe")
BAK_SUFFIX = ".bak_datesort"
BASE, CODE_V2F = 0x400000, 0x400C00
XBFS_VA, XBFS_FILE = 0x60D000, 0x208600
CAVE, CAVE_END = 0x60ECC0, 0x60ED00
HOOK_VA = 0x41F90F
HOOK_ORIG = bytes.fromhex("5f5e5b8be55dc3")         # FindFiles epilogue: pop edi/esi/ebx; mov esp,ebp; pop ebp; ret
DLG_VMT = 0x41EB60
FINDDRIVES, DATEBTNCLICK = 0x41F1F4, 0x420BD4
LOAD_MODE = 0               # PROBED 2026-10-11 (loaddlg_probe.py while the title-screen Load dialog was open): Load = mode 0
DIAG_VA = 0x60EFF0          # --diag counters in .xbfs slack: +0 cave entries, +4 last mode, +8 DateBtnClick calls, +C last self

ks = Ks(KS_ARCH_X86, KS_MODE_32)


def build(diag=False):
    src = """
        mov eax, ebx
        pop edi
        pop esi
        pop ebx
        mov esp, ebp
        pop ebp
        %(d1)s
        cmp dword ptr [eax], %(vmt)#x
        jne done
        %(d2)s
        cmp dword ptr [eax+0x148], %(mode)d
        jne done
        %(d3)s
        call %(dbc)#x
    done:
        ret
    """ % {"vmt": DLG_VMT, "mode": LOAD_MODE, "dbc": DATEBTNCLICK,
           "d1": ("inc dword ptr [%#x]\n        mov [%#x], eax" % (DIAG_VA, DIAG_VA + 12)) if diag else "",
           "d2": ("mov edx, [eax+0x148]\n        mov [%#x], edx" % (DIAG_VA + 4)) if diag else "",
           "d3": ("inc dword ptr [%#x]" % (DIAG_VA + 8)) if diag else ""}
    code = bytes(ks.asm(src, CAVE)[0])
    assert len(code) <= CAVE_END - CAVE, len(code)
    return code


def reloc_set(d):
    pe = struct.unpack_from("<I", d, 0x3C)[0]; opt = struct.unpack_from("<H", d, pe + 20)[0]; nsec = struct.unpack_from("<H", d, pe + 6)[0]
    secs = [struct.unpack_from("<IIII", d, pe + 24 + opt + 40 * k + 8) for k in range(nsec)]
    rrva, rsz = struct.unpack_from("<II", d, pe + 24 + 0x88)
    def r2f(rva):
        for vs, va, rs, ro in secs:
            if va <= rva < va + max(vs, rs): return ro + rva - va
    out = set()
    if not rsz: return out
    p, end = r2f(rrva), r2f(rrva) + rsz
    while p < end:
        page, size = struct.unpack_from("<II", d, p)
        if size < 8: break
        for q in range(p + 8, p + size, 2):
            e = struct.unpack_from("<H", d, q)[0]
            if e >> 12 == 3: out.add(BASE + page + (e & 0xFFF))
        p += size
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=DEFAULT_EXE)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--diag", action="store_true", help="instrumented cave: counters at DIAG_VA (read with loaddlg_probe.py)")
    a = ap.parse_args()
    d = bytearray(open(a.exe, "rb").read())
    code = build(a.diag)
    hf = HOOK_VA - CODE_V2F; cf = XBFS_FILE + (CAVE - XBFS_VA)
    hook = b"\xe9" + struct.pack("<i", CAVE - (HOOK_VA + 5)) + b"\x90" * (len(HOOK_ORIG) - 5)
    live = bytes(d[hf:hf + len(HOOK_ORIG)]); zone = bytes(d[cf:cf + (CAVE_END - CAVE)])
    bad = [hex(r) for r in reloc_set(d) if HOOK_VA <= r < HOOK_VA + len(HOOK_ORIG) or CAVE <= r < CAVE_END]
    state = "vanilla" if live == HOOK_ORIG else "ours" if live == hook else "OTHER"
    zstate = "zero" if not any(zone) else "ours" if zone[:len(code)] == code and not any(zone[len(code):]) else "DIFFERS"
    print("hook %s | cave %s (%d B @%#x) | relocs %s" % (state, zstate, len(code), CAVE, bad or "none"))
    if bad or state == "OTHER": print("ABORT"); return 1
    if a.revert:
        if state != "ours": print("not applied"); return 0
        d[hf:hf + len(HOOK_ORIG)] = HOOK_ORIG; d[cf:cf + (CAVE_END - CAVE)] = bytes(CAVE_END - CAVE)
        open(a.exe, "r+b").write(d); print("reverted"); return 0
    if state == "ours" and zstate == "ours": print("already applied"); return 0
    if state == "vanilla" and zstate not in ("zero", "ours"): print("ABORT: cave not free"); return 1
    d[cf:cf + (CAVE_END - CAVE)] = bytes(CAVE_END - CAVE); d[cf:cf + len(code)] = code
    d[hf:hf + len(HOOK_ORIG)] = hook
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(a.exe, BAK_SUFFIX)
    if not os.path.exists(bak): shutil.copy2(a.exe, bak); print("backup ->", bak)
    with open(a.exe, "r+b") as f: f.seek(0); f.write(d)
    assert open(a.exe, "rb").read() == bytes(d); print("Written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
