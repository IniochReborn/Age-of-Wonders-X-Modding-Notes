#!/usr/bin/env python3
r"""
29 map levels, step 4a v2: editor level UI + hidden-level mask (2026-10-31).  Needs patch_map_levels_engine_v1.
Replaces patch_map_levels_ui_editor_v1 (run `v1 --revert` first; this script refuses while v1 is applied).

User: "whenever i add map levels, it adds them at the bottom. need to expand the add map level function to allow
firmament to be added above the surface, and cave levels and abyss below it".
Storage stays dense (Firmament = level 3, Abyss I..XXV = 4..28; engine, saves and Ziggurat agree), so - like
Ziggurat - a level can exist but be HIDDEN: TAoWHSMap gets a dword mask at +0x41C (InstanceSize 0x41C -> 0x420),
bit n = level n hidden.  Display order  Firmament > Surface > Caverns > Depths > Abyss I .. XXV.
Engine (AoWEPACK):
  M1 InstanceSize 0x5570E858 0x41C -> 0x420 (zero-filled by NewInstance).
  M2 TAoWHSMap.ReadWrite 0x55776E50 (call inherited) -> stream the mask: rwInteger tag 0x10062 (whole mask) +
     rwByte tag 0x60 (Ziggurat's byte mask, OR-ed in on read, so his maps keep their hidden Firmament).  A zero
     mask writes nothing -> unchanged files for maps without hidden levels.
  M3 cave/tunnel neighbour (thunk 0x55851210 of the engine script -> its helper) skips hidden levels.
Editor (AoWDevX):
  1. Level Up / Down 0x429F06 / 0x429DAE: one display slot, skipping hidden levels.
  2. Palette page = surface for levels 0 and 3: SetMapLevel 0x429D14, AddMapLevelClick tail 0x42BE4E.
  3. Add Map Level (0x42BDDE, the AddMapLevel vcall): if both are possible, asks "Yes = Firmament (above the
     Surface) / No = new underground level (below the deepest one)"; otherwise adds the one that is possible.
     Below = the first hidden-or-missing level of 1, 2, 4, 5 .. 28.  A Firmament on a 1-2 level map creates the
     missing underground levels hidden.  Then vanilla's tail (show it, menus, page, modified).
  4. Remove Map Level 0x42BCE3: the current level, if it is the Firmament or the deepest underground level
     (anything else would renumber or orphan levels); confirm, then clear it (TMapLevel.DestroyHS +
     InitializeMapLevel) and hide it; trailing hidden levels are really removed; caves whose twin level vanished
     are destroyed (port of Ziggurat's Map Levels dialog apply + cave cleanup 0x55850C0F..0x55850E36).
  5. Status bar "Level %s" = level name (IntToStr calls 0x429CBE / 0x429E1D / 0x429F59 / 0x42A27C).
  6. Validation Go-to cap 0x4E30B9 7 -> 28.
Zones: AoWEPACK 0x55851700..0x55851D00 'MLU2' (name/message literals, NAMEFN, shared with the game strip) and
0x55834100..0x55835000 'MLM1' (code).  The exe has no free section: its sites jump through a 17-byte trampoline in
the dead tail of the LevelUp site (adds the AoWEPACK rebase delta [IAT AoWHSMap 0x43289C] - 0x558FA040); the
AoWEPACK code returns to the fixed-base exe with push imm32 / ret and calls exe IAT slots directly (editor-only
code).
Dry-run default; --apply; --revert; --dis.  Backups <file>.bak_mlvui2.
"""
import os, shutil, struct, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

EP, EPBASE = game_file("AoWEPACK.dll"), 0x55700000
EXE, EXEBASE = game_file("AoWDevX.exe"), 0x400000
Z1, Z1_END = 0x55851700, 0x55851D00
Z2, Z2_END = 0x55834100, 0x55835000
NAMEFN = Z1 + 0x10                    # eax = index -> eax = AnsiString literal (nil if out of range)
TBL = Z1 + 0x40
CODE = Z2 + 0x10
GLOBAL_MAP = 0x558FA040
MAPSLOT = 0x43289C                    # editor IAT slot = &AoWE.AoWHSMap
MASK = 0x41C

NAMES = ["Surface", "Caverns", "Depths", "Firmament", "Abyss"] + \
        ["Abyss " + r for r in ("II III IV V VI VII VIII IX X XI XII XIII XIV XV XVI XVII XVIII XIX XX "
                                 "XXI XXII XXIII XXIV XXV").split()]
assert len(NAMES) == 29
M_REFUSE, M_ASK, M_CONFIRM, M_FULL = 29, 30, 31, 32
MSGS = ["Only the Firmament or the deepest underground level can be removed.",
        "Which map level do you want to add?\r\n\r\n"
        "Yes:  the Firmament, above the Surface\r\n"
        "No:  a new underground level, below the deepest one\r\n"
        "Cancel:  none",
        "Remove this map level?  Everything on it will be deleted.",
        "All map levels are already in use."]

# engine
INSTSIZE = 0x5570E858
RW_CALL, RW_INHERITED = 0x55776E50, 0x557025AC
THUNK, OLD_HELPER = 0x55851210, 0x55851418
INITLEVEL, ADDLEVEL_VMT = 0x557773CC, 0xAC
SC_COUNT, SC_GET, GETFIELD, TCAVE_VMT, TCAVE_CLS = 0x55762390, 0x55762364, 0x557020FC, 0x557B3018, 0x2037E
# editor
IAT_GETMAPLEVEL, IAT_REMOVELEVEL, IAT_SETSCENE = 0x4329F8, 0x4329E0, 0x433368
HSE_GETMAPLEVEL, HSE_DESTROYHS = 0x55608D48, 0x5560897C
MSGDLG, SHOWMSG, LSTRASG = 0x42BBE4, 0x4019E0, 0x4010C0
UP, UP_LEN = 0x429F06, 30
DN, DN_LEN = 0x429DAE, 17
SML, SML_LEN = 0x429D14, 10
ADD, ADD_LEN = 0x42BE4E, 15
ADDV, ADDV_LEN = 0x42BDDE, 10
REM, REM_LEN = 0x42BCE3, 13
TRAMP = UP + 7 + 5                    # 0x429F12
LNSTUB = UP + 7                       # 0x429F0D: push LN ; falls into the trampoline
STATUS = [0x429CBE, 0x429E1D, 0x429F59, 0x42A27C]
INTTOSTR = 0x4017C8
VGO_CAP = 0x4E30B9
EXE_ORIG = {
    UP: "80b81d020000000f84c80000000fbe901d02000083ea017105e8fc70fdff",
    DN: "0fbe901d02000083c2017105e86172fdff",
    SML: "85f67e138b9384020000",
    ADD: "80b81d020000007e138b9384020000",
    ADDV: "8b008b10ff92ac000000",
    REM: "80b81d020000000f849d000000",
}


def asm(src, at):
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    src = "\n".join(l.split(";")[0].rstrip() for l in src.split("\n"))   # keystone hangs on comments
    return bytes(Ks(KS_ARCH_X86, KS_MODE_32).asm(src, at)[0])


def z1_blob():
    z = bytearray(Z1_END - Z1)
    z[:4] = b"MLU2"
    g = NAMEFN + 5
    fn = asm(f"""
        call {g:#x}
        pop  ecx
        cmp  eax, {len(NAMES) + len(MSGS) - 1}
        ja   nil
        mov  eax, dword ptr [ecx + eax*4 + {TBL - g:#x}]
        add  eax, ecx
        ret
    nil:
        xor  eax, eax
        ret
    """, NAMEFN)
    assert NAMEFN + len(fn) <= TBL
    z[NAMEFN - Z1:NAMEFN - Z1 + len(fn)] = fn
    strs = NAMES + MSGS
    pos = TBL + len(strs) * 4
    for i, s in enumerate(strs):
        pos = (pos + 3) & ~3
        rec = struct.pack("<iI", -1, len(s)) + s.encode("latin1") + b"\0"
        z[pos - Z1:pos - Z1 + len(rec)] = rec
        struct.pack_into("<i", z, TBL - Z1 + i * 4, pos + 8 - g)
        pos += len(rec)
    assert pos <= Z1_END, hex(pos)
    return bytes(z)


def z2_src():
    dh = HSE_DESTROYHS - HSE_GETMAPLEVEL
    return f"""
    ; ---------------- engine: mask stream (eax = map, edx = stream) ----------------
    stream:
        push eax
        push edx
        push esi
        push 0
        mov  eax, dword ptr [esp + 8]
        mov  edx, dword ptr [esp + 12]
        lea  edx, [edx + {MASK:#x}]
        mov  ecx, 0x10062
        mov  esi, dword ptr [eax]
        call dword ptr [esi + 0x2C]
        mov  eax, dword ptr [esp + 12]
        mov  eax, dword ptr [eax + {MASK:#x}]
        mov  dword ptr [esp], eax
        mov  eax, dword ptr [esp + 8]
        mov  edx, esp
        mov  ecx, 0x60
        mov  esi, dword ptr [eax]
        call dword ptr [esi + 0x30]
        movzx eax, byte ptr [esp]
        mov  edx, dword ptr [esp + 12]
        or   dword ptr [edx + {MASK:#x}], eax
        pop  eax
        pop  esi
        pop  edx
        pop  eax
        jmp  {RW_INHERITED:#x}
    ; ---------------- engine: neighbour that skips hidden levels (eax = level, dl = 1 down / 0 up) ----------------
    nbr:
        push ecx
    nbr1:
        call {OLD_HELPER:#x}
        test eax, eax
        js   nbrx
        call gm
        test ecx, ecx
        je   nbrx
        mov  ecx, dword ptr [ecx + {MASK:#x}]
        bt   ecx, eax
        jc   nbr1
    nbrx:
        pop  ecx
        ret
    gm:                                   ; ecx = AoWHSMap or 0 (PIC)
        call gm1
    gm1:
        pop  ecx
        mov  ecx, dword ptr [ecx + GMOFF]
        ret
    ; ---------------- editor helpers (esi = map) ----------------
    vis:                                  ; eax = visible-level mask
        push ecx
        push edx
        mov  eax, dword ptr [esi + 0x10]
        mov  ecx, dword ptr [eax + 0x14]
        mov  eax, 1
        shl  eax, cl
        dec  eax
        mov  edx, dword ptr [esi + {MASK:#x}]
        not  edx
        and  eax, edx
        pop  edx
        pop  ecx
        ret
    setmask:                              ; mask = ~ebp & ((1 << count) - 1)
        mov  eax, dword ptr [esi + 0x10]
        mov  ecx, dword ptr [eax + 0x14]
        mov  eax, 1
        shl  eax, cl
        dec  eax
        mov  edx, ebp
        not  edx
        and  eax, edx
        mov  dword ptr [esi + {MASK:#x}], eax
        ret
    ; step(eax = THSMEdit, ecx = -1 up / +1 down) -> edx = new level or -1
    step:
        push esi
        push edi
        mov  esi, dword ptr [{MAPSLOT:#x}]
        mov  esi, dword ptr [esi]
        test esi, esi
        je   sfail
        movsx edx, byte ptr [eax + 0x21D]
    sagain:
        cmp  edx, 3
        je   s0
        jg   sk
        inc  edx
        jmp  sk
    s0: xor  edx, edx
    sk: add  edx, ecx
        js   sfail
        test edx, edx
        jne  sn1
        mov  edx, 3
        jmp  schk
    sn1:
        cmp  edx, 3
        jg   schk
        dec  edx
    schk:
        mov  edi, dword ptr [esi + 0x10]
        cmp  edx, dword ptr [edi + 0x14]
        jge  sfail
        mov  edi, dword ptr [esi + {MASK:#x}]
        bt   edi, edx
        jc   sagain
        pop  edi
        pop  esi
        ret
    sfail:
        or   edx, -1
        pop  edi
        pop  esi
        ret
    up:
        mov  ecx, -1
        call step
        test edx, edx
        js   upno
        push 0x429F24
        ret
    upno:
        push 0x429FDB
        ret
    dn:
        mov  ecx, 1
        call step
        test edx, edx
        js   dnno
        push 0x429DE4
        ret
    dnno:
        push 0x429E9F
        ret
    sml:
        test esi, esi
        je   smls
        cmp  esi, 3
        je   smls
        mov  edx, dword ptr [ebx + 0x284]
        push 0x429D1E
        ret
    smls:
        push 0x429D2B
        ret
    addt:
        movsx ecx, byte ptr [eax + 0x21D]
        test ecx, ecx
        je   addts
        cmp  ecx, 3
        je   addts
        mov  edx, dword ptr [ebx + 0x284]
        push 0x42BE5D
        ret
    addts:
        push 0x42BE6A
        ret
    ln:
        push edx
        call {NAMEFN:#x}
        mov  edx, eax
        pop  eax
        mov  ecx, {LSTRASG:#x}
        jmp  ecx
    ; ---------------- Add Map Level (ebx = form; only ebx saved by the caller) ----------------
    addui:
        push esi
        push edi
        push ebp
        mov  esi, dword ptr [{MAPSLOT:#x}]
        mov  esi, dword ptr [esi]
        call vis
        mov  edi, eax
        xor  ebp, ebp
        mov  ecx, 1
    afl:
        cmp  ecx, 29
        jae  afl2
        cmp  ecx, 3
        je   afn
        bt   edi, ecx
        jnc  afound
    afn:
        inc  ecx
        jmp  afl
    afound:
        mov  ebp, ecx
    afl2:
        bt   edi, 3
        jc   aonlyb
        test ebp, ebp
        je   afirm
        mov  eax, {M_ASK}
        call {NAMEFN:#x}
        mov  edx, eax
        push 0x0B
        push 0
        mov  eax, ebx
        mov  ecx, 3
        mov  esi, {MSGDLG:#x}
        call esi
        cmp  ax, 6
        je   afirm
        cmp  ax, 7
        je   abelow
        jmp  acancel
    aonlyb:
        test ebp, ebp
        jne  abelow
        mov  eax, {M_FULL}
        call {NAMEFN:#x}
        mov  ecx, {SHOWMSG:#x}
        call ecx
        jmp  acancel
    afirm:
        mov  ebp, 3
    abelow:
        bts  edi, ebp
        mov  eax, ebx
        mov  edx, edi
        call apply
        mov  edx, ebp
        pop  ebp
        pop  edi
        pop  esi
        push 0x42BE07
        ret
    acancel:
        pop  ebp
        pop  edi
        pop  esi
        push 0x42BE87
        ret
    ; ---------------- Remove Map Level (eax = THSMEdit, ebx = form; esi saved by the caller) ----------------
    remui:
        push edi
        movsx edx, byte ptr [eax + 0x21D]
        mov  esi, dword ptr [{MAPSLOT:#x}]
        mov  esi, dword ptr [esi]
        call vis
        mov  edi, eax
        cmp  edx, 3
        je   rok
        test edx, edx
        je   rrefuse
        mov  eax, edi
        and  eax, 0xFFFFFFF6
        bsr  eax, eax
        jz   rrefuse
        cmp  eax, edx
        jne  rrefuse
    rok:
        push edx
        mov  eax, {M_CONFIRM}
        call {NAMEFN:#x}
        mov  edx, eax
        push 0x0B
        push 0
        mov  ecx, 3
        mov  eax, ebx
        mov  esi, {MSGDLG:#x}
        call esi
        pop  edx
        cmp  ax, 6
        jne  rdone
        btr  edi, edx
        mov  eax, ebx
        mov  edx, edi
        call apply
        pop  edi
        push 0x42BD3E
        ret
    rrefuse:
        mov  eax, {M_REFUSE}
        call {NAMEFN:#x}
        mov  ecx, {SHOWMSG:#x}
        call ecx
    rdone:
        pop  edi
        push 0x42BDA2
        ret
    ; ---------------- apply(eax = form, edx = new visible mask) ----------------
    apply:
        push ebx
        push esi
        push edi
        push ebp
        mov  ebx, eax
        mov  ebp, edx
        or   ebp, 1
        mov  esi, dword ptr [{MAPSLOT:#x}]
        mov  esi, dword ptr [esi]
        call vis
        mov  edi, eax
        mov  eax, dword ptr [ebx + 0x22C]
        xor  edx, edx
        call dword ptr [{IAT_SETSCENE:#x}]
        push 1
    pdl:
        mov  ecx, dword ptr [esp]
        cmp  ecx, 29
        jae  pdd
        bt   edi, ecx
        jnc  pdn
        bt   ebp, ecx
        jc   pdn
        mov  eax, dword ptr [esi + 0x10]
        mov  edx, ecx
        call dword ptr [{IAT_GETMAPLEVEL:#x}]
        mov  ecx, dword ptr [{IAT_GETMAPLEVEL:#x}]
        add  ecx, {dh:#x}
        call ecx
        mov  edx, dword ptr [esp]
        mov  eax, esi
        call {INITLEVEL:#x}
    pdn:
        inc  dword ptr [esp]
        jmp  pdl
    pdd:
        pop  ecx
        call setmask
    ptrim:
        mov  eax, dword ptr [esi + 0x10]
        mov  ecx, dword ptr [eax + 0x14]
        cmp  ecx, 1
        jle  pta
        dec  ecx
        bt   ebp, ecx
        jc   pta
        mov  eax, esi
        mov  edx, ecx
        call dword ptr [{IAT_REMOVELEVEL:#x}]
        jmp  ptrim
    pta:
        bsr  ecx, ebp
        mov  eax, dword ptr [esi + 0x10]
        cmp  ecx, dword ptr [eax + 0x14]
        jl   ptd
        mov  eax, esi
        mov  edx, dword ptr [eax]
        call dword ptr [edx + {ADDLEVEL_VMT:#x}]
        test al, al
        jne  pta
    ptd:
        call setmask
        call cleanup
        pop  ebp
        pop  edi
        pop  esi
        pop  ebx
        ret
    ; ---------------- destroy caves whose twin is gone (esi = map) - Ziggurat 0x55850DA1 ----------------
    cleanup:
        push ebx
        push edi
        push ebp
        call cg
    cg:
        pop  ebp
        sub  ebp, CGLINK
    crs:
        mov  eax, dword ptr [esi + 0x100]
        call {SC_COUNT:#x}
        mov  edi, eax
        xor  ebx, ebx
    clp:
        cmp  ebx, edi
        jge  cout
        mov  eax, dword ptr [esi + 0x100]
        mov  edx, ebx
        call {SC_GET:#x}
        inc  ebx
        test eax, eax
        je   clp
        lea  ecx, [ebp + {TCAVE_VMT:#x}]
        cmp  dword ptr [eax], ecx
        jne  clp
        push eax
        movzx edx, byte ptr [eax + 0x30]
        cmp  edx, 1
        ja   ckeep
        mov  ecx, dword ptr [eax + 4]
        movsx eax, byte ptr [ecx + 0x12]
        call {THUNK:#x}
        test eax, eax
        js   ckill
        mov  ecx, dword ptr [esp]
        push eax
        movsx edx, byte ptr [ecx + 0x10]
        movsx ecx, byte ptr [ecx + 0x11]
        mov  eax, dword ptr [esi + 0x10]
        call {GETFIELD:#x}
        test eax, eax
        je   ckill
        mov  edx, {TCAVE_CLS:#x}
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx + 0x80]
        test eax, eax
        je   ckill
        mov  ecx, dword ptr [esp]
        movzx edx, byte ptr [ecx + 0x30]
        xor  edx, 1
        cmp  byte ptr [eax + 0x30], dl
        jne  ckill
    ckeep:
        pop  eax
        jmp  clp
    ckill:
        pop  eax
        mov  dl, 1
        mov  ecx, dword ptr [eax]
        call dword ptr [ecx - 4]
        jmp  crs
    cout:
        pop  ebp
        pop  edi
        pop  ebx
        ret
    """


ENTRIES = ("stream", "nbr", "up", "dn", "sml", "addt", "ln", "addui", "remui")


def z2_blob():
    """two-pass: GMOFF (gm1 -> GLOBAL_MAP) and CGLINK (link address of cg) depend on the layout"""
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    gmoff, cglink = 0x11111111, 0x11111111
    for _ in range(4):
        src = z2_src().replace("GMOFF", hex(gmoff)).replace("CGLINK", hex(cglink))
        labs = ENTRIES + ("gm1", "cg")
        full = asm(src + "\n" + "\n".join(".long " + l for l in labs), CODE)
        code = full[:-4 * len(labs)]
        ent = dict(zip(labs, struct.unpack("<%dI" % len(labs), full[-4 * len(labs):])))
        n1, n2 = (GLOBAL_MAP - ent["gm1"]) & 0xFFFFFFFF, ent["cg"]
        if (n1, n2) == (gmoff, cglink):
            break
        gmoff, cglink = n1, n2
    else:
        raise AssertionError("layout did not settle")
    assert CODE + len(code) <= Z2_END, hex(len(code))
    z = bytearray(Z2_END - Z2)
    z[:4] = b"MLM1"
    z[CODE - Z2:CODE - Z2 + len(code)] = code
    return bytes(z), ent, code


def ep_patches(ent):
    z2, _, _ = z2_blob()
    return [
        (Z1, bytes(Z1_END - Z1), z1_blob()),
        (Z2, bytes(Z2_END - Z2), z2),
        (INSTSIZE, struct.pack("<I", 0x41C), struct.pack("<I", 0x420)),
        (RW_CALL, b"\xe8" + struct.pack("<i", RW_INHERITED - (RW_CALL + 5)),
         b"\xe8" + struct.pack("<i", ent["stream"] - (RW_CALL + 5))),
        (THUNK, b"\xe9" + struct.pack("<i", OLD_HELPER - (THUNK + 5)),
         b"\xe9" + struct.pack("<i", ent["nbr"] - (THUNK + 5))),
    ]


def exe_patches(ent):
    def tgt(lab):
        return struct.pack("<I", ent[lab])

    def jrel(at, to):
        return b"\xe9" + struct.pack("<i", to - (at + 5))
    tramp = bytes.fromhex("50a1") + struct.pack("<I", MAPSLOT) + b"\x2d" + struct.pack("<I", GLOBAL_MAP) + \
        bytes.fromhex("0144240458c3")
    assert len(tramp) == 17
    up = b"\x68" + tgt("up") + b"\xeb\x05" + b"\x68" + tgt("ln") + tramp
    P = [(UP, up + b"\x90" * (UP_LEN - len(up)))]
    for site, n, lab in ((DN, DN_LEN, "dn"), (SML, SML_LEN, "sml"), (ADD, ADD_LEN, "addt"),
                         (ADDV, ADDV_LEN, "addui"), (REM, REM_LEN, "remui")):
        b = b"\x68" + tgt(lab) + jrel(site + 5, TRAMP)
        P.append((site, b + b"\x90" * (n - len(b))))
    out = []
    for site, new in P:
        orig = bytes.fromhex(EXE_ORIG[site])
        assert len(orig) == len(new), hex(site)
        out.append((site, orig, new))
    for s in STATUS:
        out.append((s, b"\xe8" + struct.pack("<i", INTTOSTR - (s + 5)), b"\xe8" + struct.pack("<i", LNSTUB - (s + 5))))
    out.append((VGO_CAP, b"\x07", b"\x1c"))
    return out


def plan(path, base, P):
    import pefile
    d = open(path, "rb").read()
    pe = pefile.PE(data=d)
    off = lambda va: pe.get_offset_from_rva(va - base)  # noqa: E731
    rl = set()
    if hasattr(pe, "DIRECTORY_ENTRY_BASERELOC"):
        rl = {base + e.rva for b in pe.DIRECTORY_ENTRY_BASERELOC for e in b.entries if e.type == 3}
    bad = [hex(r) for r in rl if any(s - 3 <= r < s + len(o) for s, o, _ in P)]
    st = []
    for s, o, n in P:
        c = d[off(s):off(s) + len(o)]
        st.append("vanilla" if c == o else "ours" if c == n else "OTHER")
    return d, off, st, bad


def main():
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    _, ent, code = z2_blob()
    if "--dis" in sys.argv:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
        inv = {v: k for k, v in ent.items()}
        for i in Cs(CS_ARCH_X86, CS_MODE_32).disasm(code, CODE):
            if i.address in inv:
                print("%s:" % inv[i.address])
            print("  %08x %s %s" % (i.address, i.mnemonic, i.op_str))
        return 0
    print("entries:", {k: hex(v) for k, v in ent.items()})
    files = [(EP, EPBASE, ep_patches(ent)), (EXE, EXEBASE, exe_patches(ent))]
    plans = []
    for path, base, P in files:
        d, off, st, bad = plan(path, base, P)
        print("%-12s %s relocs %s" % (os.path.basename(path), st, bad or "none"))
        plans.append((path, off, P, st, bad))
    if plans[0][3][0] == "OTHER" and b"MLU1" in open(EP, "rb").read():
        print("ABORT: patch_map_levels_ui_editor_v1 is applied - run it with --revert first"); return 1
    allst = {s for p in plans for s in p[3]}
    if "OTHER" in allst or any(p[4] for p in plans):
        print("ABORT"); return 1
    want = "vanilla" if revert else "ours"
    if allst == {want}:
        print("already %s" % ("reverted" if revert else "applied")); return 0
    if len(allst) != 1:
        print("ABORT (mixed state)"); return 1
    if not apply and not revert:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    r = subprocess.run(["tasklist"], capture_output=True, text=True).stdout
    if "AoWx.exe" in r or "AoWDevX.exe" in r:
        print("game/editor running - close it first"); return 1
    for path, off, P, st, bad in plans:
        bak = bak_path(path, ".bak_mlvui2")
        if not revert and not os.path.exists(bak):
            shutil.copy2(path, bak)
        with open(path, "r+b") as f:
            for s, o, n in P:
                f.seek(off(s)); f.write(o if revert else n)
        d2 = open(path, "rb").read()
        assert all(d2[off(s):off(s) + len(o)] == (o if revert else n) for s, o, n in P)
    print("reverted" if revert else "written and verified (AoWEPACK %d sites, AoWDevX %d sites)"
          % (len(files[0][2]), len(files[1][2])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
