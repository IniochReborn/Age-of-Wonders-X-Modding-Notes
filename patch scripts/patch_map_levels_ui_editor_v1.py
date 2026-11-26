#!/usr/bin/env python3
r"""
29 map levels, step 4a: editor level UI (2026-10-31).  Needs patch_map_levels_engine_v1 (level cap 29).

User: "firmament should be 'above' surface level, not beneath depths".  Storage keeps Firmament = level 3 and
Abyss I..XXV = 4..28 (the engine, saved maps and Ziggurat agree on that); the editor now walks them in DISPLAY
order  Firmament > Surface > Caverns > Depths > Abyss I .. XXV  (slot 0..28: level 3 -> 0, 0..2 -> +1, 4+ same).
  1. TMainForm.LevelUpBtnClick 0x429F06 / LevelDownBtnClick 0x429DAE: step one display slot; refused past the top
     or past the last existing level (a 3-level map behaves exactly as vanilla).
  2. Palette page = surface page for levels 0 AND 3 (Firmament), underground otherwise:
     TMainForm.SetMapLevel 0x429D14 (validation Go-to) and AddMapLevelClick's tail 0x42BE4E.
     (Level Up/Down's own page flips are already right in display order.)
  3. RemoveMapLevelClick 0x42BCE3: only the LAST level (count-1) may be removed - removing a middle level would
     renumber every level above it (Caverns removed -> Firmament became Depths).  Other levels -> message.
  4. Status bar "Level %s": the 4 IntToStr calls (0x429CBE, 0x429E1D, 0x429F59, 0x42A27C) -> level NAME
     (Surface, Caverns, Depths, Firmament, Abyss, Abyss II .. Abyss XXV).
  5. Validation Go-to (.vgo) refused z > 7: cap byte 0x4E30B9 7 -> 28.
Code lives in AoWEPACK zone 0x55851700..0x55851D00 ('MLU1'; the name table there is shared with the game strip,
step 4b).  The exe has no free section, so the editor sites jump through a 17-byte trampoline placed in the now
dead tail of the LevelUp site (push target ; jmp tramp ; tramp adds the AoWEPACK rebase delta = [IAT AoWHSMap
0x43289C] - 0x558FA040).  AoWEPACK code returns to the fixed-base exe with push imm32 / ret.
Dry-run default; --apply; --revert.  Backups <file>.bak_mlvui.
"""
import os, shutil, struct, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

EP, EPBASE = game_file("AoWEPACK.dll"), 0x55700000
EXE, EXEBASE = game_file("AoWDevX.exe"), 0x400000
ZONE, ZONE_END = 0x55851700, 0x55851D00
MAGIC = b"MLU1"
NAMEFN = ZONE + 0x10                  # eax = level (29 = remove-refused message) -> eax = AnsiString literal / nil
CODE = ZONE + 0x40
TBL = ZONE + 0x180
GLOBAL_MAP = 0x558FA040
MAPSLOT = 0x43289C                    # editor IAT slot = &AoWE.AoWHSMap

NAMES = ["Surface", "Caverns", "Depths", "Firmament", "Abyss"] + \
        ["Abyss " + r for r in ("II III IV V VI VII VIII IX X XI XII XIII XIV XV XVI XVII XVIII XIX XX "
                                 "XXI XXII XXIII XXIV XXV").split()]
assert len(NAMES) == 29
MSG = ("Only the last map level can be removed: the deepest Abyss level, or the Firmament on a map without "
       "Abyss levels.")

# exe sites
UP, UP_LEN = 0x429F06, 30
DN, DN_LEN = 0x429DAE, 17
SML, SML_LEN = 0x429D14, 10
ADD, ADD_LEN = 0x42BE4E, 15
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
    REM: "80b81d020000000f849d000000",
}


def asm(src, at):
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    return bytes(Ks(KS_ARCH_X86, KS_MODE_32).asm(src, at)[0])


def ep_blob():
    """the whole zone image (ZONE..ZONE_END)"""
    z = bytearray(ZONE_END - ZONE)
    z[:4] = MAGIC
    g = NAMEFN + 5
    fn = asm(f"""
        call {g:#x}
        pop  ecx
        cmp  eax, 29
        ja   nil
        mov  eax, dword ptr [ecx + eax*4 + {TBL - g:#x}]
        add  eax, ecx
        ret
    nil:
        xor  eax, eax
        ret
    """, NAMEFN)
    assert NAMEFN + len(fn) <= CODE
    z[NAMEFN - ZONE:NAMEFN - ZONE + len(fn)] = fn
    src = f"""
    step:
        movsx edx, byte ptr [eax + 0x21D]
        cmp  edx, 3
        je   s0
        jg   sk
        inc  edx
        jmp  sk
    s0: xor  edx, edx
    sk: add  edx, ecx
        js   fail
        test edx, edx
        jne  n1
        mov  edx, 3
        jmp  chk
    n1: cmp  edx, 3
        jg   chk
        dec  edx
    chk:
        mov  ecx, dword ptr [{MAPSLOT:#x}]
        mov  ecx, dword ptr [ecx]
        test ecx, ecx
        je   fail
        mov  ecx, dword ptr [ecx + 0x10]
        cmp  edx, dword ptr [ecx + 0x14]
        jge  fail
        ret
    fail:
        or   edx, -1
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
    add_:
        movsx ecx, byte ptr [eax + 0x21D]
        test ecx, ecx
        je   adds
        cmp  ecx, 3
        je   adds
        mov  edx, dword ptr [ebx + 0x284]
        push 0x42BE5D
        ret
    adds:
        push 0x42BE6A
        ret
    rem:
        movsx edx, byte ptr [eax + 0x21D]
        test edx, edx
        jne  rem1
        push 0x42BD8D
        ret
    rem1:
        mov  ecx, dword ptr [{MAPSLOT:#x}]
        mov  ecx, dword ptr [ecx]
        mov  ecx, dword ptr [ecx + 0x10]
        mov  ecx, dword ptr [ecx + 0x14]
        dec  ecx
        cmp  edx, ecx
        jne  rem2
        push 0x42BCF0
        ret
    rem2:
        mov  eax, 29
        call {NAMEFN:#x}
        mov  ecx, 0x4019E0
        call ecx
        push 0x42BDA2
        ret
    ln:
        push edx
        call {NAMEFN:#x}
        mov  edx, eax
        pop  eax
        mov  ecx, 0x4010C0
        jmp  ecx
    """
    code = asm(src, CODE)
    assert CODE + len(code) <= TBL, hex(len(code))
    z[CODE - ZONE:CODE - ZONE + len(code)] = code
    # entry addresses: assemble again with an int3 after the label; the first differing byte is the entry
    ent = {}
    for lab in ("up", "dn", "sml", "add_", "rem", "ln"):
        probe = src.replace(f"\n    {lab}:\n", f"\n    {lab}:\n        int3\n", 1)
        pc = asm(probe, CODE)
        i = next(j for j in range(len(code)) if pc[j] != code[j])
        assert pc[i] == 0xCC
        ent[lab] = CODE + i
    # literal table + strings
    tbl_n = 30
    pos = TBL + tbl_n * 4
    offs = []
    for s in NAMES + [MSG]:
        pos = (pos + 3) & ~3
        rec = struct.pack("<iI", -1, len(s)) + s.encode("latin1") + b"\0"
        z[pos - ZONE:pos - ZONE + len(rec)] = rec
        offs.append(pos + 8 - g)
        pos += len(rec)
    assert pos <= ZONE_END, hex(pos)
    for i, o in enumerate(offs):
        struct.pack_into("<i", z, TBL - ZONE + i * 4, o)
    return bytes(z), ent


def exe_patches(ent):
    def tgt(lab):
        return struct.pack("<I", ent[lab])

    def jrel(at, to):
        return b"\xe9" + struct.pack("<i", to - (at + 5))
    tramp = bytes.fromhex("50a1") + struct.pack("<I", MAPSLOT) + b"\x2d" + struct.pack("<I", GLOBAL_MAP) + \
        bytes.fromhex("01442404 58 c3".replace(" ", ""))
    assert len(tramp) == 17
    up = b"\x68" + tgt("up") + b"\xeb\x05" + b"\x68" + tgt("ln") + tramp
    up += b"\x90" * (UP_LEN - len(up))
    P = [(UP, up)]
    for site, n, lab in ((DN, DN_LEN, "dn"), (SML, SML_LEN, "sml"), (ADD, ADD_LEN, "add_"), (REM, REM_LEN, "rem")):
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
    return off, st, bad


def main():
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    blob, ent = ep_blob()
    print("entries:", {k: hex(v) for k, v in ent.items()})
    EPP = [(ZONE, bytes(len(blob)), blob)]
    EXP = exe_patches(ent)
    files = [(EP, EPBASE, EPP), (EXE, EXEBASE, EXP)]
    plans = []
    for path, base, P in files:
        off, st, bad = plan(path, base, P)
        print("%-12s %s relocs %s" % (os.path.basename(path), st, bad or "none"))
        plans.append((path, off, P, st, bad))
    allst = {s for p in plans for s in p[3]}
    if "OTHER" in allst or any(p[4] for p in plans):
        if "--dis" not in sys.argv:
            print("ABORT"); return 1
    if "--dis" in sys.argv:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
        for i in Cs(CS_ARCH_X86, CS_MODE_32).disasm(blob[CODE - ZONE:TBL - ZONE].rstrip(b"\0"), CODE):
            print("  %08x %s %s" % (i.address, i.mnemonic, i.op_str))
        return 0
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
        bak = bak_path(path, ".bak_mlvui")
        if not revert and not os.path.exists(bak):
            shutil.copy2(path, bak)
        with open(path, "r+b") as f:
            for s, o, n in P:
                f.seek(off(s)); f.write(o if revert else n)
        d2 = open(path, "rb").read()
        assert all(d2[off(s):off(s) + len(o)] == (o if revert else n) for s, o, n in P)
    print("reverted" if revert else "written and verified (AoWEPACK zone + %d editor sites)" % len(EXP))
    return 0


if __name__ == "__main__":
    sys.exit(main())
