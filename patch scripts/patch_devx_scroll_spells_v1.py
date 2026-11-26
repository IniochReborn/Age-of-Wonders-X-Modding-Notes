#!/usr/bin/env python3
r"""
AoWDevX.exe: item editor gets 7 scroll-spell pickers (2026-10-30).  Needs patch_scroll_spells_store_v1 (AoWEPACK).

TItemEditForm (VMT 0x412D40): ScrollPnl (+0x26C, visible only for itScroll) holds Label11 "Scroll spell:" and
SpellComboBox (+0x274, csDropDownList, all spells sorted by name, Objects = TSpell, id = [spell+0x10]) which
edits slot 1 = [item+0x38] (vanilla, SpellComboBoxChange 0x413BA0).  Slots 2..7 = [item+0x4C+4k] = id+1 (0 = None).

1. DFM (live copy in .xdfm, resource entry @file 0x434E0 -> RVA 0xE6000, size 0x2447): SpellComboBox Width
   217 -> 177; six TComboBox records Sp2..Sp7 (csDropDownList, TabOrder 1..6) inserted after it as ScrollPnl
   children, grid x 20/205 * y 33/61/89/117 (slot order: 1 2 / 3 4 / 5 6 / 7).  Uses 0x1AD of the 0x1B9 B slack;
   resource size updated.  No published fields/methods needed (found by name through Components [comp+0x10]).
2. FormCreate method entry (dword @file 0x12489; currently the item-hpmv wrapper 0x4E519F) -> wrap: original,
   then each Sp combo gets "None" (object nil) + a copy of SpellComboBox.Items.
3. Update routine common exit @0x4135FF (5 B `xor eax,eax / pop edx / pop ecx / pop ecx`, ebx = form; both the
   editable and read-only branches pass here) -> load: Sp_k := index of GetSpell(slot-1) (IndexOfObject), else 0.
4. Edit routine @0x4138D3 (8 B `mov edx,[edi+0x27C] / mov eax,esi`, edi = form, right before original.Assign(copy))
   -> save: slot_k of the edited copy [form+0x27C] := Objects[ItemIndex].id + 1, or 0 for None.
Code in .xthm 0x4E4000..0x4E4240 (tail: item name/cost patch) (RWX, zeroed body of the REVERTED dark theme - ⚠ build_editor_dark_theme.py
must not be re-applied while this is on).  Fixed base, absolute addresses; no reloc on any site.
Backup <game>\backup\AoWDevX.exe.bak_scrollspells.  Dry-run default; --apply; --revert (restores the backup copy
of the DFM region + sites in place).
"""
import os, shutil, struct, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

EXE = game_file("AoWDevX.exe")
BASE = 0x400000
MAGIC = b"SCD1"
RES_FO = 0x434E0
DFM_FO, DFM_SIZE, DFM_RAW_END = 0xDE000, 0x2447, 0xE0600
COMBO_FO, COMBO_END = 0xDE58F, 0xDE614             # SpellComboBox record [COMBO_FO, COMBO_END)
METHOD_FO, METHOD_OLD = 0x12489, 0x4E519F
LD_SITE, LD_ORIG, LD_BACK = 0x4135FF, bytes.fromhex("33c05a5959"), 0x413604
SV_SITE, SV_ORIG, SV_BACK = 0x4138D3, bytes.fromhex("8b977c0200008bc6"), 0x4138DB
ZONE, ZONE_END = 0x4E4000, 0x4E4240   # 0x4E4240..0x4E4800 = patch_devx_item_name_cost_v1
NONE_VA = ZONE + 0x10
CODE = ZONE + 0x40
T_GETSPELL, T_INDEXOFOBJ, T_SETIDX, T_GETIDX = 0x401D28, 0x4018C0, 0x401A98, 0x401A90
T_BEGINUPD, T_ENDUPD, T_LSTRCLR = 0x4018B0, 0x4018B8, 0x4010B0
IAT_HSSET = 0x432898
GRID = [(205, 33), (20, 61), (205, 61), (20, 89), (205, 89), (20, 117)]   # Sp2..Sp7
WIDTH = 177


def ss(s):
    return bytes([len(s)]) + s.encode()


def ival(v):
    return (b"\x02" + struct.pack("<b", v)) if -128 <= v <= 127 else (b"\x03" + struct.pack("<h", v))


def combo_rec(k, x, y):
    return (ss("TComboBox") + ss("Sp%d" % k) + ss("Left") + ival(x) + ss("Top") + ival(y) + ss("Width") + ival(WIDTH)
            + ss("Style") + b"\x07" + ss("csDropDownList") + ss("TabOrder") + ival(k - 1) + b"\x00\x00")


def new_dfm(dfm):
    rel0, rel1 = COMBO_FO - DFM_FO, COMBO_END - DFM_FO
    rec = bytearray(dfm[rel0:rel1])
    w = rec.find(b"\x05Width\x03")
    assert w > 0 and struct.unpack_from("<h", rec, w + 7)[0] == 217
    struct.pack_into("<h", rec, w + 7, WIDTH)
    ins = b"".join(combo_rec(k, x, y) for k, (x, y) in zip(range(2, 8), GRID))
    return dfm[:rel0] + bytes(rec) + ins + dfm[rel1:]


SRC = f"""
wrap:
    push ebx
    mov  ebx, eax
    call {METHOD_OLD:#x}
    pushad
    sub  esp, 0x10
    mov  dword ptr [esp], 0
    mov  esi, dword ptr [ebx + 0x274]
    test esi, esi
    jz   w_out
    mov  esi, dword ptr [esi + 0x118]
    mov  edi, 2
w_k:
    mov  eax, ebx
    mov  edx, edi
    call findc
    test eax, eax
    jz   w_n
    mov  ebp, dword ptr [eax + 0x118]
    mov  eax, ebp
    call {T_BEGINUPD:#x}
    mov  eax, ebp
    mov  edx, {NONE_VA:#x}
    xor  ecx, ecx
    push ebx
    mov  ebx, dword ptr [eax]
    call dword ptr [ebx + 0x38]
    pop  ebx
    mov  eax, esi
    push ebx
    mov  ebx, dword ptr [eax]
    call dword ptr [ebx + 0x14]
    pop  ebx
    mov  dword ptr [esp + 8], eax
    mov  dword ptr [esp + 4], 0
w_i:
    mov  eax, dword ptr [esp + 4]
    cmp  eax, dword ptr [esp + 8]
    jge  w_idone
    lea  ecx, [esp]
    mov  edx, eax
    mov  eax, esi
    push ebx
    mov  ebx, dword ptr [eax]
    call dword ptr [ebx + 0xC]
    pop  ebx
    mov  edx, dword ptr [esp + 4]
    mov  eax, esi
    push ebx
    mov  ebx, dword ptr [eax]
    call dword ptr [ebx + 0x18]
    pop  ebx
    mov  ecx, eax
    mov  edx, dword ptr [esp]
    mov  eax, ebp
    push ebx
    mov  ebx, dword ptr [eax]
    call dword ptr [ebx + 0x38]
    pop  ebx
    inc  dword ptr [esp + 4]
    jmp  w_i
w_idone:
    mov  eax, ebp
    call {T_ENDUPD:#x}
w_n:
    inc  edi
    cmp  edi, 7
    jle  w_k
w_out:
    lea  eax, [esp]
    call {T_LSTRCLR:#x}
    add  esp, 0x10
    popad
    pop  ebx
    ret

findc:
    push ebx
    push esi
    push edi
    lea  edi, [edx + 0x30]
    mov  esi, dword ptr [eax + 0x10]
    test esi, esi
    jz   fc_none
    mov  ecx, dword ptr [esi + 8]
    mov  esi, dword ptr [esi + 4]
fc_l:
    dec  ecx
    js   fc_none
    mov  ebx, dword ptr [esi + ecx*4]
    test ebx, ebx
    jz   fc_l
    mov  eax, dword ptr [ebx + 8]
    test eax, eax
    jz   fc_l
    cmp  dword ptr [eax - 4], 3
    jne  fc_l
    cmp  word ptr [eax], 0x7053
    jne  fc_l
    movzx edx, byte ptr [eax + 2]
    cmp  edx, edi
    jne  fc_l
    mov  eax, ebx
    jmp  fc_out
fc_none:
    xor  eax, eax
fc_out:
    pop  edi
    pop  esi
    pop  ebx
    ret

ld:
    pushad
    mov  esi, dword ptr [ebx + 0x27C]
    test esi, esi
    jz   ld_out
    mov  edi, 2
ld_k:
    mov  eax, ebx
    mov  edx, edi
    call findc
    test eax, eax
    jz   ld_n
    mov  ebp, eax
    xor  edx, edx
    cmp  byte ptr [esi + 0x34], 5
    jne  ld_set
    mov  eax, dword ptr [esi + edi*4 + 0x44]
    test eax, eax
    jz   ld_set
    dec  eax
    mov  edx, eax
    mov  eax, dword ptr [{IAT_HSSET:#x}]
    mov  eax, dword ptr [eax]
    mov  eax, dword ptr [eax + 0x84]
    call {T_GETSPELL:#x}
    xor  edx, edx
    test eax, eax
    jz   ld_set
    mov  edx, eax
    mov  eax, dword ptr [ebp + 0x118]
    call {T_INDEXOFOBJ:#x}
    mov  edx, eax
    test edx, edx
    jge  ld_set
    xor  edx, edx
ld_set:
    mov  eax, ebp
    call {T_SETIDX:#x}
ld_n:
    inc  edi
    cmp  edi, 7
    jle  ld_k
ld_out:
    popad
    xor  eax, eax
    pop  edx
    pop  ecx
    pop  ecx
    jmp  {LD_BACK:#x}

sv:
    pushad
    mov  ebx, edi
    mov  esi, dword ptr [ebx + 0x27C]
    test esi, esi
    jz   sv_out
    mov  edi, 2
sv_k:
    mov  eax, ebx
    mov  edx, edi
    call findc
    test eax, eax
    jz   sv_zero
    mov  ebp, eax
    call {T_GETIDX:#x}
    test eax, eax
    jle  sv_zero
    mov  edx, eax
    mov  eax, dword ptr [ebp + 0x118]
    push ebx
    mov  ebx, dword ptr [eax]
    call dword ptr [ebx + 0x18]
    pop  ebx
    test eax, eax
    jz   sv_zero
    mov  ecx, dword ptr [eax + 0x10]
    inc  ecx
    jmp  sv_st
sv_zero:
    xor  ecx, ecx
sv_st:
    mov  dword ptr [esi + edi*4 + 0x44], ecx
    inc  edi
    cmp  edi, 7
    jle  sv_k
sv_out:
    popad
    mov  edx, dword ptr [edi + 0x27C]
    mov  eax, esi
    jmp  {SV_BACK:#x}
"""


def build():
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    marked = SRC.replace("\nfindc:", "\n    int3\n    int3\n    int3\n    int3\nfindc:") \
                .replace("\nld:", "\n    int3\n    int3\n    int3\n    int3\n    int3\nld:") \
                .replace("\nsv:", "\n    int3\n    int3\n    int3\n    int3\n    int3\n    int3\nsv:")
    code = bytes(ks.asm(marked, CODE)[0])
    ld = CODE + code.index(b"\xcc" * 5) + 5
    sv = CODE + code.index(b"\xcc" * 6) + 6
    assert code[ld - CODE] == 0x60 and code[sv - CODE] == 0x60      # pushad
    z = bytearray(ZONE_END - ZONE)
    z[0:4] = MAGIC
    struct.pack_into("<iI", z, NONE_VA - ZONE - 8, -1, 4)
    z[NONE_VA - ZONE:NONE_VA - ZONE + 4] = b"None"
    assert CODE + len(code) <= ZONE_END
    z[CODE - ZONE:CODE - ZONE + len(code)] = code
    return bytes(z), CODE, ld, sv


def game_running():
    try:
        return "AoWDevX.exe" in subprocess.run(["tasklist"], capture_output=True, text=True).stdout
    except Exception:
        return False


def main():
    import pefile
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    d = open(EXE, "rb").read()
    pe = pefile.PE(data=d)
    assert pe.OPTIONAL_HEADER.DllCharacteristics & 0x40 == 0
    off = lambda va: pe.get_offset_from_rva(va - BASE)  # noqa: E731
    zone, wrap, ld, sv = build()
    rva, size = struct.unpack_from("<II", d, RES_FO)
    assert rva == 0xE6000 and pe.get_offset_from_rva(rva) == DFM_FO
    dfm = d[DFM_FO:DFM_FO + size]
    region = d[DFM_FO:DFM_RAW_END]
    zo, lo, so = off(ZONE), off(LD_SITE), off(SV_SITE)
    meth = struct.unpack_from("<I", d, METHOD_FO)[0]
    chained = d[off(ZONE_END):off(ZONE_END) + 4] == b"INC1" and struct.unpack_from("<I", d, off(ZONE_END) + 4)[0] == wrap
    if chained:                                     # patch_devx_item_name_cost_v1 sits in front of our wrapper
        meth = wrap
    ld_hook = b"\xe9" + struct.pack("<i", ld - (LD_SITE + 5))
    sv_hook = b"\xe9" + struct.pack("<i", sv - (SV_SITE + 5)) + b"\x90" * 3
    if size == DFM_SIZE:
        dst = "vanilla"
        assert d[COMBO_FO + 1:COMBO_FO + 10] == b"TComboBox" and d[COMBO_END - 2:COMBO_END + 1] == b"\x00\x00\x00" and d[COMBO_END - 3] != 0
        assert not any(region[size:])
        nd = new_dfm(dfm)
        assert len(nd) <= DFM_RAW_END - DFM_FO, hex(len(nd))
    else:
        grow = sum(len(combo_rec(k, x, y)) for k, (x, y) in zip(range(2, 8), GRID))
        dst = "ours" if size == DFM_SIZE + grow else "OTHER"
        nd = dfm
    cur = (meth, d[lo:lo + 5], d[so:so + 8], d[zo:zo + len(zone)])
    van = (METHOD_OLD, LD_ORIG, SV_ORIG, bytes(len(zone)))
    our = (wrap, ld_hook, sv_hook, zone)
    cst = "vanilla" if cur == van else "ours" if cur == our else "OTHER"
    print("DFM size %#x (%s) | FormCreate entry %#x | load site %s | save site %s | zone %s -> code %s"
          % (size, dst, meth, cur[1].hex(), cur[2].hex(), "zero" if not any(cur[3]) else cur[3][:4], cst))
    if "OTHER" in (dst, cst) or dst != cst:
        print("ABORT (mixed/foreign state)"); return 1
    want = "vanilla" if revert else "ours"
    if cst == want:
        print("already %s" % ("reverted" if revert else "applied")); return 0
    if chained:
        print("revert patch_devx_item_name_cost_v1 first (it chains in front of this patch)"); return 1
    if not apply and not revert:
        print("Dry run OK (new DFM %#x B, slack left %#x) - rerun with --apply (or --revert)."
              % (len(nd), DFM_RAW_END - DFM_FO - len(nd))); return 0
    if game_running():
        print("AoWDevX.exe is running - close the editor first"); return 1
    bak = bak_path(EXE, ".bak_scrollspells")
    if apply and not os.path.exists(bak):
        shutil.copy2(EXE, bak); print("backup ->", bak)
    if revert:
        b = open(bak, "rb").read()
        new_region, new_size = b[DFM_FO:DFM_RAW_END], struct.unpack_from("<I", b, RES_FO + 4)[0]
        vals = van
    else:
        new_region = nd + bytes((DFM_RAW_END - DFM_FO) - len(nd))
        new_size, vals = len(nd), our
    try:
        with open(EXE, "r+b") as f:                 # in-place (house rule)
            f.seek(zo); f.write(vals[3])
            f.seek(DFM_FO); f.write(new_region)
            f.seek(RES_FO + 4); f.write(struct.pack("<I", new_size))
            f.seek(METHOD_FO); f.write(struct.pack("<I", vals[0]))
            f.seek(lo); f.write(vals[1])
            f.seek(so); f.write(vals[2])
    except PermissionError:
        print("LOCKED"); return 1
    d2 = open(EXE, "rb").read()
    assert d2[DFM_FO:DFM_RAW_END] == new_region and struct.unpack_from("<I", d2, METHOD_FO)[0] == vals[0]
    print("reverted" if revert else "written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
