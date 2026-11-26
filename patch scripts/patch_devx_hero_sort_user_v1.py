#!/usr/bin/env python3
r"""
AoWEPACK: editor Heroes + Items tabs - sort mode 2 "User entries first, then by name" (2026-11-07).

User: "i want to add another sorting button (after sort by level) that would have a 'U' icon (same font as '1' and 'A'),
which would sort heroes by whether they are 'User' or not (and also sort alphabetically)" + "also add that 'User'
sorting for items".

RE (AoWEPACK, verified 11/07):
  * Heroes tab = HeroCtrl.THeroControlGrid (editor form [form+0x3AC]); Items tab = ItemCtrl.TItemControlGrid.  Both keep
    a sort mode byte [grid+0x1EC] (0 name, 1 level/type) and an index list [grid+0x1DC] (indices into the map's
    THeroControl [map+0xF8] / TItemControl [map+0xF4]; map = [[0x558E9494]]).
  * Heroes: UpdateHeroes 0x558093E4 switch @0x55809477 `sub al,1 / jb name 0x5580947F / je level 0x55809491 / jmp
    no-sort 0x558094A1`; name cmp 0x558092FC; GetHero 0x5578A3BC; "User" label when [hero+0x90] == -1
    (THero.GetLibraryHero).
  * Items: UpdateItems 0x558081F8 switch @0x55808274 `sub al,1 / jb name 0x5580828C / jne no-sort 0x5580829C` (falls
    into type 0x5580827A); name cmp 0x5580807C; GetItem 0x55794D70; "User" label when [item+0x24] == -1
    (TItem.GetLibraryItem).  (SortOnName/SortOnType there sort directly; mode 2 is only reached via UpdateItems.)
  * compare fns: eax/edx = two INDICES; list sort = 0x55702ED4(eax = list, edx = cmp fn).
Patch: each switch -> jmp cave: modes 0/1 go to the original arms, mode 2 sorts with cmp_user (user entries first; ties
-> the original name compare), anything else -> no sort.  Both sites reloc-free.
Cave AoWEPACK 0x558E1700..0x558E1880 (PIC: call/pop deltas for [0x558E9494] and the cmp fn address).
The editor side (SortUserBtn / SortItemUserBtn + click -> mode 2 + Update*) lives in AoWxShot.dll /
patch_devx_screenshot_v1.  Dry-run default; --apply; --revert (surgical).  Backup .bak_herosortu
"""
import os, shutil, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bakpath import bak_path  # noqa: E402
import patch_sky_polish_v1 as SP  # noqa: E402
import sky_clouds_overlay_asm as OV  # noqa: E402

TAG = ".bak_herosortu"
CAVE, CAVE_END = 0x558E1700, 0x558E1880
LIST_SORT, PMAP = 0x55702ED4, 0x558E9494
GRIDS = [
    dict(tag="h", site=0x55809477, orig=bytes.fromhex("2c0172047414eb22"), arm0=0x5580947F, arm1=0x55809491,
         nosort=0x558094A1, cmpname=0x558092FC, get=0x5578A3BC, ctrl=0xF8, lib=0x90),
    dict(tag="i", site=0x55808274, orig=bytes.fromhex("2c0172147522"), arm0=0x5580828C, arm1=0x5580827A,
         nosort=0x5580829C, cmpname=0x5580807C, get=0x55794D70, ctrl=0xF4, lib=0x24),
]


def src_one(g, dp, dq):
    t = g["tag"]
    return f"""
    {t}disp:
        cmp al, 0x0
        je {g['arm0']:#x}
        cmp al, 0x1
        je {g['arm1']:#x}
        cmp al, 0x2
        jne {g['nosort']:#x}
        call {t}dp
    {t}dp:
        pop edx
        add edx, {t}cmpu - {dp:#x}
        mov eax, dword ptr [ebx + 0x1dc]
        call {LIST_SORT:#x}
        jmp {g['nosort']:#x}
    {t}cmpu:
        push ebx
        push esi
        push edi
        push ebp
        mov ebx, eax
        mov esi, edx
        call {t}dq
    {t}dq:
        pop edi
        sub edi, {dq:#x}
        mov eax, dword ptr [edi + {PMAP:#x}]
        mov eax, dword ptr [eax]
        mov eax, dword ptr [eax + {g['ctrl']:#x}]
        mov edx, ebx
        call {g['get']:#x}
        xor ebp, ebp
        cmp dword ptr [eax + {g['lib']:#x}], -1
        jne {t}cu1
        inc ebp
    {t}cu1:
        mov eax, dword ptr [edi + {PMAP:#x}]
        mov eax, dword ptr [eax]
        mov eax, dword ptr [eax + {g['ctrl']:#x}]
        mov edx, esi
        call {g['get']:#x}
        xor ecx, ecx
        cmp dword ptr [eax + {g['lib']:#x}], -1
        jne {t}cu2
        inc ecx
    {t}cu2:
        sub ecx, ebp
        jnz {t}cu_ret
        mov eax, ebx
        mov edx, esi
        pop ebp
        pop edi
        pop esi
        pop ebx
        jmp {g['cmpname']:#x}
    {t}cu_ret:
        mov eax, ecx
        pop ebp
        pop edi
        pop esi
        pop ebx
        ret
"""


def build():
    anch = {g["tag"]: [CAVE, CAVE] for g in GRIDS}
    labels = ["%s%s" % (g["tag"], k) for g in GRIDS for k in ("dp", "dq", "disp")]
    for _ in range(8):
        src = "".join(src_one(g, *anch[g["tag"]]) for g in GRIDS)
        src += "    probe:\n" + "".join("        mov eax, %s\n" % l for l in labels)
        code = OV.asm(src, CAVE)
        n = 5 * len(labels)
        tail = code[-n:]
        vals = dict(zip(labels, (int.from_bytes(tail[5 * i + 1:5 * i + 5], "little") for i in range(len(labels)))))
        new = {g["tag"]: [vals[g["tag"] + "dp"], vals[g["tag"] + "dq"]] for g in GRIDS}
        if new == anch:
            break
        anch = new
    else:
        raise AssertionError("anchors did not converge")
    code = code[:-n]
    assert len(code) <= CAVE_END - CAVE, len(code)
    P = [(CAVE, bytes(CAVE_END - CAVE), code + bytes(CAVE_END - CAVE - len(code)))]
    for g in GRIDS:
        s, o = g["site"], g["orig"]
        jmp = b"\xe9" + (vals[g["tag"] + "disp"] - (s + 5)).to_bytes(4, "little", signed=True)
        P.append((s, o, jmp + b"\x90" * (len(o) - 5)))
    return P


def main():
    import pefile
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if (apply or revert) and SP.busy():
        print("game/editor running - close it first"); return 1
    d = open(SP.EPK, "rb").read(); pe = pefile.PE(data=d)
    P = build()
    st, bad = SP.state(d, pe, SP.EBASE, P)
    print("AoWEPACK", st, "relocs", bad or "none", "| cave %d B" % len(P[0][2].rstrip(b"\0")))
    if "--dis" in sys.argv:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
        for i in Cs(CS_ARCH_X86, CS_MODE_32).disasm(P[0][2].rstrip(b"\0"), CAVE):
            print("  %08X %-6s %s" % (i.address, i.mnemonic, i.op_str))
    if "OTHER" in st or bad or len(set(st)) != 1:
        print("ABORT"); return 1
    want = "vanilla" if revert else "ours"
    if st[0] == want:
        print("already", "reverted" if revert else "applied"); return 0
    if not (apply or revert):
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bk = bak_path(SP.EPK, TAG)
    if apply and not os.path.exists(bk):
        shutil.copy2(SP.EPK, bk)
    SP.write_bytes(SP.EPK, SP.EBASE, P, revert)
    st2, _ = SP.state(open(SP.EPK, "rb").read(), pefile.PE(SP.EPK), SP.EBASE, P)
    assert set(st2) == {want}, st2
    print("written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
