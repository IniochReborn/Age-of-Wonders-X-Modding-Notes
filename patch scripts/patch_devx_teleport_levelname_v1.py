#!/usr/bin/env python3
r"""
Editor: teleporter destination level as a NAME + status-bar level name without "Level" (2026-11-04).

User: "can we update the teleporter UI so that instead of showing Z coordinate as a number, it shows it as its name
(Abyss III instead of 5)" / "in the editor at the bottom left ... where it shows the map level, the space is too
small" / "the word 'Level' isnt necessary.  Simply displaying 'Surface', 'Underground', 'Abyss III' etc".
Names = the shared level-name table NAMEFN (patch_map_levels_ui_editor_v3, AoWEPACK 0x55851710):
0 Surface, 1 Caverns, 2 Depths, 3 Firmament, 4 Abyss, 5 Abyss II ... 28 Abyss XXV.

1. TTeleportEditForm (Teleport Properties): the L spinner (LtoEdit, form+0x228) is hidden and a drop-down list
   (runtime TComboBox, csDropDownList, owner = form, parent = GroupBox1) takes its place, listing the map's VISIBLE
   levels in display order (Firmament, Surface, Caverns, Depths, Abyss ...); every item carries its level number as
   its Objects[] value.  The form, ClientPnl and GroupBox1 grow by 3 x spinner height and OK/Cancel shift right.
   The combo pointer is kept in LtoEdit.Tag ([+0x0C]), so it dies with the form.
     load  0x4197B3 call TSpin.SetValue -> stub 0x4E2080 -> tl_load (SetValue, then build/fill/select)
     OK    0x419858 jmp telefirm store cave 0x4ECFE1 -> stub 0x4E2090 -> tl_store (al = Objects[ItemIndex]) -> 0x4ECFE1
   (patch_teleport_firmament_v1 caves stay: the hidden spinner still round-trips -1/3; Firmament is just a name now.)
2. Status bar: the 4 LoadResString(AoWE.LevelXRStr = "Level %s") calls (0x429CD9/0x429E38/0x429F74/0x42A297) ->
   stub 0x4E20A0 -> tl_fmt = "%s" (AoWEPACK's resourcestring itself is untouched - the game may use it).
3. EditStatusBar panel 1 width 65 -> 100 in the live TMAINFORM DFM (.xprn 0x4ED000).
   ⚠ scripts that rewrite the whole live TMAINFORM (prune / theme) would drop this byte - re-run this after them.
Exe stubs: .tres 0x4E2080..0x4E20B0 (.tres VirtualSize 0x76 -> 0x100), via the v3 trampoline 0x429F12.
AoWEPACK zone 0x558E0B00..0x558E1000 'TLV1' (PIC).  Backups .bak_telelvl.  Dry-run; --apply; --revert; --dis.
"""
import os, shutil, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from bakpath import bak_path, game_file  # noqa: E402
import patch_sky_polish_v1 as SP  # noqa: E402

TAG = ".bak_telelvl"
EP, EPBASE = game_file("AoWEPACK.dll"), 0x55700000
EXE, EXEBASE = game_file("AoWDevX.exe"), 0x400000
Z, Z_END, MAGIC = 0x558E0B00, 0x558E1000, b"TLV1"
CODE = Z + 0x10
NAMEFN = 0x55851710
TRAMP = 0x429F12
MAPSLOT, MASK = 0x43289C, 0x41C
T_SPINSET = 0x4030E8
IAT_LSTRASG, IAT_SETVISIBLE, IAT_SETITEMINDEX, IAT_GETITEMINDEX = 0x4320EC, 0x4323A8, 0x4325DC, 0x4325E0
IAT_TBUTTON, IAT_TCOMBOBOX = 0x43263C, 0x432640
STORE_CAVE = 0x4ECFE1
STUB_L, STUB_S, STUB_F = 0x4E2080, 0x4E2090, 0x4E20A0
TRES_VSIZE_FO, TRES_VSIZE_OLD, TRES_VSIZE_NEW = 0x318, 0x76, 0x100
LOAD_SITE, STORE_SITE = 0x4197B3, 0x419858
FMT_SITES = [0x429CD9, 0x429E38, 0x429F74, 0x42A297]
LOADRES = 0x401140
DFM_LIVE, DFM_LEN = 0x4ED000, 0x69376
PANEL_PAT = b"\x0aTStatusBar\x0dEditStatusBar"
PANEL1 = b"\x01\x09Alignment\x07\x08taCenter\x05Width\x02"   # second panel item prefix (first has Width 60)
W_OLD, W_NEW = 0x41, 0x50
ENTRIES = ("tl_load", "tl_store", "tl_fmt")


def asm(src, at):
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    src = "\n".join(l.split(";")[0].rstrip() for l in src.split("\n"))
    return bytes(Ks(KS_ARCH_X86, KS_MODE_32).asm(src, at)[0])


def src():
    return f"""
    tl_load:                              ; eax = LtoEdit, edx = shown value, ebx = form (called)
        push esi
        push edi
        push ebp
        mov  ebp, esp
        sub  esp, 16                      ; -4 combo, -8 mask, -12 sel, -16 k
        mov  esi, eax
        mov  edi, edx
        mov  ecx, {T_SPINSET:#x}
        call ecx
        cmp  edi, -1
        jne  z1
        mov  edi, 3
    z1:
        mov  eax, dword ptr [esi + 0xc]
        mov  dword ptr [ebp - 4], eax
        test eax, eax
        jne  fill
        mov  eax, dword ptr [{IAT_TCOMBOBOX:#x}]
        mov  dl, 1
        mov  ecx, ebx
        call dword ptr [eax + 0x24]
        mov  dword ptr [ebp - 4], eax
        mov  byte ptr [eax + 0x121], 2
        mov  dword ptr [esi + 0xc], eax
        mov  edx, dword ptr [esi + 0x3c]
        lea  edx, [edx + edx*2]
        mov  dword ptr [ebp - 16], edx    ; G (k slot reused before the fill loop)
        mov  eax, ebx
        call grow
        mov  eax, dword ptr [esi + 0x24]
        mov  eax, dword ptr [eax + 0x24]
        mov  eax, dword ptr [eax + 0x24]
        mov  eax, dword ptr [eax + 0x24]
        mov  edx, dword ptr [ebp - 16]
        call grow
        mov  eax, dword ptr [esi + 0x24]
        mov  edx, dword ptr [ebp - 16]
        call grow
        mov  dword ptr [ebp - 8], 0
        call buttons
        mov  eax, dword ptr [ebp - 4]
        mov  edx, dword ptr [esi + 0x24]
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x3c]
        push ebx
        mov  eax, dword ptr [esi + 0x38]
        add  eax, dword ptr [ebp - 16]
        push eax
        push dword ptr [esi + 0x3c]
        mov  edx, dword ptr [esi + 0x30]
        mov  ecx, dword ptr [esi + 0x34]
        mov  eax, dword ptr [ebp - 4]
        mov  ebx, dword ptr [eax]
        call dword ptr [ebx + 0x4c]
        pop  ebx
    fill:
        mov  eax, esi
        xor  edx, edx
        call dword ptr [{IAT_SETVISIBLE:#x}]
        mov  eax, dword ptr [ebp - 4]
        mov  eax, dword ptr [eax + 0x118]
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x40]
        mov  eax, dword ptr [{MAPSLOT:#x}]
        mov  eax, dword ptr [eax]
        mov  edx, dword ptr [eax + {MASK:#x}]
        mov  eax, dword ptr [eax + 0x10]
        mov  ecx, dword ptr [eax + 0x14]
        mov  eax, 1
        shl  eax, cl
        dec  eax
        not  edx
        and  eax, edx
        mov  dword ptr [ebp - 8], eax
        mov  dword ptr [ebp - 12], -1
        mov  dword ptr [ebp - 16], 0
    lp:
        mov  eax, dword ptr [ebp - 16]
        cmp  eax, 29
        jae  lpend
        test eax, eax
        jne  kk1
        mov  eax, 3
        jmp  kk3
    kk1:
        cmp  eax, 4
        jae  kk3
        dec  eax
    kk3:
        bt   dword ptr [ebp - 8], eax
        jae  nxt
        push eax
        call {NAMEFN:#x}
        mov  edx, eax
        mov  ecx, dword ptr [esp]
        mov  eax, dword ptr [ebp - 4]
        mov  eax, dword ptr [eax + 0x118]
        push ebx
        mov  ebx, dword ptr [eax]
        call dword ptr [ebx + 0x38]
        pop  ebx
        pop  ecx
        cmp  ecx, edi
        jne  nxt
        mov  dword ptr [ebp - 12], eax
    nxt:
        inc  dword ptr [ebp - 16]
        jmp  lp
    lpend:
        mov  edx, dword ptr [ebp - 12]
        test edx, edx
        jl   done
        mov  eax, dword ptr [ebp - 4]
        call dword ptr [{IAT_SETITEMINDEX:#x}]
    done:
        mov  esp, ebp
        pop  ebp
        pop  edi
        pop  esi
        ret
    grow:                                 ; eax = control, edx = extra width
        push ebx
        mov  ebx, eax
        mov  eax, dword ptr [ebx + 0x38]
        add  eax, edx
        push eax
        push dword ptr [ebx + 0x3c]
        mov  edx, dword ptr [ebx + 0x30]
        mov  ecx, dword ptr [ebx + 0x34]
        mov  eax, ebx
        mov  ebx, dword ptr [eax]
        call dword ptr [ebx + 0x4c]
        pop  ebx
        ret
    buttons:                              ; shift every TButton of the form right by G, grow the first one's parent
        push esi
        push edi
        push ebx
        mov  esi, dword ptr [ebx + 0x10]
        test esi, esi
        je   bend
        mov  edi, dword ptr [esi + 0x8]
        cmp  edi, 200
        ja   bend
        xor  ebx, ebx
    blp:
        cmp  ebx, edi
        jge  bend
        mov  eax, dword ptr [esi + 0x4]
        mov  eax, dword ptr [eax + ebx*4]
        test eax, eax
        je   bnx
        mov  ecx, dword ptr [eax]
        cmp  ecx, dword ptr [{IAT_TBUTTON:#x}]
        jne  bnx
        cmp  dword ptr [ebp - 8], 1
        je   bmv
        mov  dword ptr [ebp - 8], 1
        push eax
        mov  eax, dword ptr [eax + 0x24]
        test eax, eax
        je   bnp
        mov  edx, dword ptr [ebp - 16]
        call grow
    bnp:
        pop  eax
    bmv:
        push ebx
        push dword ptr [eax + 0x38]
        push dword ptr [eax + 0x3c]
        mov  edx, dword ptr [eax + 0x30]
        add  edx, dword ptr [ebp - 16]
        mov  ecx, dword ptr [eax + 0x34]
        mov  ebx, dword ptr [eax]
        call dword ptr [ebx + 0x4c]
        pop  ebx
    bnx:
        inc  ebx
        jmp  blp
    bend:
        mov  dword ptr [ebp - 8], 0
        pop  ebx
        pop  edi
        pop  esi
        ret
    tl_store:                             ; al = spinner value, ebx = form; continue at the telefirm store cave
        mov  ecx, dword ptr [ebx + 0x228]
        mov  ecx, dword ptr [ecx + 0xc]
        test ecx, ecx
        je   sout
        push eax
        mov  eax, ecx
        call dword ptr [{IAT_GETITEMINDEX:#x}]
        test eax, eax
        jl   srest
        mov  edx, eax
        mov  ecx, dword ptr [ebx + 0x228]
        mov  ecx, dword ptr [ecx + 0xc]
        mov  eax, dword ptr [ecx + 0x118]
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x18]
        add  esp, 4
        jmp  sout
    srest:
        pop  eax
    sout:
        push {STORE_CAVE:#x}
        ret
    tl_fmt:                               ; LoadResString(eax = rec, edx = &result) -> result := '%s'
        mov  eax, edx
        call fm1
        .long 0xffffffff
        .long 2
        .long 0x7325
    fm1:
        pop  edx
        add  edx, 8
        jmp  dword ptr [{IAT_LSTRASG:#x}]
    """


def z_blob():
    s = src()
    full = asm(s + "\n" + "\n".join(".long " + l for l in ENTRIES), CODE)
    code = full[:-4 * len(ENTRIES)]
    ent = dict(zip(ENTRIES, struct.unpack("<%dI" % len(ENTRIES), full[-4 * len(ENTRIES):])))
    assert CODE + len(code) <= Z_END, hex(len(code))
    z = bytearray(CODE - Z + len(code))
    z[:4] = MAGIC
    z[CODE - Z:] = code
    return bytes(z), ent, code


def ep_patches(ent_blob):
    blob = ent_blob
    return [(Z, bytes(len(blob)), blob)]


def exe_patches(ent, dfm_off_va):
    def stub(lab):
        b = b"\x68" + struct.pack("<I", ent[lab]) + b"\xe9" + struct.pack("<i", TRAMP - 0)  # fixed below
        return b
    P = []
    for at, lab in ((STUB_L, "tl_load"), (STUB_S, "tl_store"), (STUB_F, "tl_fmt")):
        b = b"\x68" + struct.pack("<I", ent[lab]) + b"\xe9" + struct.pack("<i", TRAMP - (at + 10))
        P.append((at, bytes(len(b)), b))
    P.append((LOAD_SITE, b"\xe8" + struct.pack("<i", T_SPINSET - (LOAD_SITE + 5)),
              b"\xe8" + struct.pack("<i", STUB_L - (LOAD_SITE + 5))))
    P.append((STORE_SITE, b"\xe9" + struct.pack("<i", STORE_CAVE - (STORE_SITE + 5)),
              b"\xe9" + struct.pack("<i", STUB_S - (STORE_SITE + 5))))
    for s in FMT_SITES:
        P.append((s, b"\xe8" + struct.pack("<i", LOADRES - (s + 5)), b"\xe8" + struct.pack("<i", STUB_F - (s + 5))))
    P.append((EXEBASE + TRES_VSIZE_FO, struct.pack("<I", TRES_VSIZE_OLD), struct.pack("<I", TRES_VSIZE_NEW)))
    P.append((dfm_off_va, bytes([W_OLD]), bytes([W_NEW])))
    return P


def find_panel(d, pe):
    o = pe.get_offset_from_rva(DFM_LIVE - EXEBASE)
    i = d.find(PANEL_PAT, o, o + DFM_LEN)
    assert i > 0, "EditStatusBar not found in the live TMAINFORM"
    j = d.find(PANEL1, i, i + 200)
    j = d.find(PANEL1, j + 1, i + 200)          # second centred panel = the level panel
    assert j > 0
    return pe.get_rva_from_offset(j + len(PANEL1)) + EXEBASE


def state(path, base, P, exe=False):
    import pefile
    d = open(path, "rb").read(); pe = pefile.PE(data=d)
    off = lambda va: (va - base) if va - base < 0x400 else pe.get_offset_from_rva(va - base)  # noqa: E731
    rl = set()
    if hasattr(pe, "DIRECTORY_ENTRY_BASERELOC") and not exe:
        rl = {base + e.rva for b in pe.DIRECTORY_ENTRY_BASERELOC for e in b.entries if e.type == 3}
    bad = [hex(r) for r in rl if any(s - 3 <= r < s + len(o) for s, o, _ in P)]
    st = []
    for s, o, n in P:
        c = d[off(s):off(s) + len(o)]
        st.append("vanilla" if c == o else "ours" if c == n else "OTHER")
    return d, off, st, bad


def write(path, off, P, revert):
    with open(path, "r+b") as f:
        for s, o, n in P:
            f.seek(off(s)); f.write(o if revert else n)
    d = open(path, "rb").read()
    for s, o, n in P:
        assert d[off(s):off(s) + len(o)] == (o if revert else n), hex(s)


def main():
    import pefile
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    blob, ent, code = z_blob()
    if "--dis" in sys.argv:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
        inv = {v: k for k, v in ent.items()}
        for i in Cs(CS_ARCH_X86, CS_MODE_32).disasm(code, CODE):
            if i.address in inv:
                print("%s:" % inv[i.address])
            print("  %08x %s %s" % (i.address, i.mnemonic, i.op_str))
        return 0
    if (apply or revert) and SP.busy():
        print("game/editor running - close it first"); return 1
    d = open(EXE, "rb").read()
    panel_va = find_panel(d, pefile.PE(data=d))
    work = []
    eb = open(EP, "rb").read()
    import pefile as _pf
    _pe = _pf.PE(data=eb); zo = _pe.get_offset_from_rva(Z - EPBASE)
    cur = eb[zo:zo + len(blob)]
    if cur.startswith(MAGIC) and cur != blob:
        if not apply:
            print("AoWEPACK zone holds an OLDER TLV1 build - --apply updates it in place"); return 0
        if SP.busy():
            print("game/editor running - close it first"); return 1
        bk = bak_path(EP, TAG)
        with open(EP, "r+b") as f:
            f.seek(zo); f.write(blob)
        assert open(EP, "rb").read()[zo:zo + len(blob)] == blob
        print("AoWEPACK TLV1 zone updated to the current build")
    for name, path, base, P, exe in (("AoWEPACK", EP, EPBASE, ep_patches(blob), False),
                                      ("AoWDevX", EXE, EXEBASE, exe_patches(ent, panel_va), True)):
        _, off, st, bad = state(path, base, P, exe)
        print("%s %s relocs %s" % (name, st, bad or "none"))
        if "OTHER" in st or bad or len(set(st)) != 1:
            print("ABORT"); return 1
        work.append((name, path, off, P, st[0]))
    if revert:
        for name, path, off, P, st in work:
            if st == "ours":
                write(path, off, P, True); print("reverted", name)
        return 0
    if all(w[4] == "ours" for w in work):
        print("already applied"); return 0
    if not apply:
        print("entries", {k: hex(v) for k, v in ent.items()}, "code", hex(len(code)))
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    for name, path, off, P, st in work:
        if st == "vanilla":
            bk = bak_path(path, TAG)
            if not os.path.exists(bk):
                shutil.copy2(path, bk)
            write(path, off, P, False)
    print("written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
