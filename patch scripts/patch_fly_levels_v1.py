#!/usr/bin/env python3
r"""
Fly up / down between map levels for flying units (2026-10-31): port of Ziggurat's G0-G4, extended to 29 levels.

A party of flyers standing on Sky (0xE) or Chasm (0xB) gets an activatable Flying ability button: it flies to the
neighbouring level in display order (Firmament > Surface > Caverns > Depths > Abyss I .. XXV, hidden levels
skipped); when both directions are possible it asks "Fly up to the X? Choose No to fly down to the Y.".  Errors:
"There is nowhere to fly from here." / "Every selected unit must be able to fly." / "...needs 4 movement points."
The destination hex must be Sky/Chasm going up, and not EarthWall (7/8/0xF) going down.
Ziggurat AoWEPACK block 0x5584F800..0x558501F0 (tables + messages + code, PIC via ebp delta) relocated byte-for-
byte to 0x558CA000 and adjusted:
  - its fly-neighbour helper 0x5584FAC0 (5-entry tables, byte mask) -> `jmp` our mask-aware 29-level neighbour
    (engine thunk 0x55851210, same convention eax = level, dl = 1 down / 0 up);
  - ValidPath level cap `cmp esi,4` -> 28;
  - the 5x5 prompt-text table -> text built at run time from the level names (NAMEFN of the editor-v3 script)
    into a literal-style AnsiString buffer;
  - its BSS (a clone of the dialog class VMT 0x557B331C with Yes/No overrides, 0x558FAA30..0x558FAAF8) moved to
    0x558FA400.. (ours uses 0x558FAA40 / 0x558FAAE0..F8); text buffer 0x558FA4E0..0x558FA580.
Hooks: TMoveControl.ValidPath 0x55746979, TAbstractUnit.MovedTo 0x55780343, TWarpParty.CalculateWarpLocation
0x557EB2CE (6-byte jmp each), TMovementAbility VMT slots 0x557B7374 (+0x98 GetControlType) / 0x557B7390 (+0xB4
Activate) -> the block's handlers (both relocated entries keep vanilla for every ability other than Flying = 1).
Needs patch_map_levels_engine_v1 + patch_map_levels_ui_editor_v3.  Dry-run default; --apply; --revert.
Backup AoWEPACK.dll.bak_flylevels.
"""
import os, shutil, struct, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DLL, BASE = game_file("AoWEPACK.dll"), 0x55700000
ZIG = r"C:\Users\<user>\Desktop\AoW Ziggurat\Ziggurat\AoWEPACK.dpl"
ZS, ZE = 0x5584F800, 0x558501F0
NEW = 0x558CA000
DELTA = NEW - ZS
ZBSS, ZBSS_END, NBSS = 0x558FAA30, 0x558FAB00, 0x558FA400
TXT = 0x558FA4E0                           # literal-style AnsiString: -1, len, chars (<= 0x90 B)
HELPER = 0x5584FAC0
THUNK = 0x55851210
NAMEFN = 0x55851710
ENTRIES = [0x5584FB10, 0x5584FBB0, 0x5584FC00, 0x5584FCB0, 0x5584FD90, 0x5584FE50, 0x5584FF30, 0x5584FF40,
           0x5584FF50, 0x5584FFE0, 0x55850090, 0x55850160, 0x558501B0]
CAP = 0x558500CF                            # cmp esi, 4
TXT_SITE, TXT_END, TXT_SKIP = 0x5584FDF5, 0x5584FE14, 0x5584FE4C
MK = NEW + 0xC00                            # our mktext zone (strings first, code at +0x40)
HOOKS = [(0x55746979, "8bc3595a5d5f", 0x55850090), (0x55780343, "8bf885ff7d05", 0x55850160),
         (0x557EB2CE, "0fbec0508b44", 0x558501B0)]
VMT_SLOTS = [(0x557B7374, 0x5574E730, 0x5584FFE0), (0x557B7390, 0x5574EF68, 0x5584FE50)]
S1, S2, S3 = b"Fly up to the ", b"? Choose No to fly down to the ", b"."


def asm(src, at):
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    src = "\n".join(l.split(";")[0].rstrip() for l in src.split("\n"))
    return bytes(Ks(KS_ARCH_X86, KS_MODE_32).asm(src, at)[0])


def mktext_zone():
    z = bytearray(0x200)
    p1, p2, p3 = MK, MK + 0x10, MK + 0x30
    for a, s in ((p1, S1), (p2, S2), (p3, S3)):
        z[a - MK:a - MK + len(s)] = s
    code_at = MK + 0x40
    k = 0x11111111
    for _ in range(4):
        code = asm(f"""
            push ebx
            push esi
            push edi
            push edx
            push eax
            call g
        g:
            pop  ebx
            sub  ebx, {k:#x}
            lea  edi, [ebx + {TXT + 8:#x}]
            lea  esi, [ebx + {p1:#x}]
            call cpy
            pop  eax
            call {NAMEFN:#x}
            call cpyl
            lea  esi, [ebx + {p2:#x}]
            call cpy
            pop  eax
            call {NAMEFN:#x}
            call cpyl
            lea  esi, [ebx + {p3:#x}]
            call cpy
            mov  byte ptr [edi], 0
            lea  eax, [ebx + {TXT + 8:#x}]
            mov  ecx, edi
            sub  ecx, eax
            mov  dword ptr [eax - 4], ecx
            mov  dword ptr [eax - 8], -1
            pop  edi
            pop  esi
            pop  ebx
            ret
        cpy:
            lodsb
            test al, al
            je   cpy1
            stosb
            jmp  cpy
        cpy1:
            ret
        cpyl:
            test eax, eax
            je   cpyl1
            mov  ecx, dword ptr [eax - 4]
            mov  esi, eax
            rep movsb
        cpyl1:
            ret
        """, code_at)
        g = code_at + 10                       # 5 pushes (1 B each) + call (5 B)
        if g == k:
            break
        k = g
    assert code[9] == 0xE8 or code[5] == 0xE8
    z[0x40:0x40 + len(code)] = code
    return bytes(z)


def relocated(z, zoff, ours, ooff):
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32, CS_GRP_JUMP, CS_GRP_CALL
    from capstone.x86 import X86_OP_IMM, X86_OP_MEM
    md = Cs(CS_ARCH_X86, CS_MODE_32); md.detail = True
    blk = bytearray(z[zoff(ZS):zoff(ZE)])
    seen, todo, ext, fixes = set(), list(ENTRIES), set(), 0
    while todo:
        a = todo.pop()
        while ZS <= a < ZE and a not in seen:
            ins = next(md.disasm(bytes(blk[a - ZS:a - ZS + 16]), a))
            seen.add(a)
            branch = ins.group(CS_GRP_JUMP) or ins.group(CS_GRP_CALL)
            for op in ins.operands:
                if op.type == X86_OP_IMM and branch:
                    t = op.imm & 0xFFFFFFFF
                    if ZS <= t < ZE:
                        if t != HELPER:
                            todo.append(t)
                    else:
                        ext.add(("code", t))
                        struct.pack_into("<i", blk, a - ZS + ins.size - 4, t - (a + DELTA + ins.size))
                        fixes += 1
            vals = [op.mem.disp & 0xFFFFFFFF for op in ins.operands if op.type == X86_OP_MEM] + \
                   [op.imm & 0xFFFFFFFF for op in ins.operands if op.type == X86_OP_IMM and not branch]
            for v in vals:
                if not 0x55700000 <= v < 0x56000000:
                    continue
                raw = bytes(blk[a - ZS:a - ZS + ins.size])
                k = raw.rfind(struct.pack("<I", v))
                assert k > 0, ins
                if ZS <= v < ZE:
                    struct.pack_into("<I", blk, a - ZS + k, v + DELTA); fixes += 1
                elif ZBSS <= v < ZBSS_END:
                    struct.pack_into("<I", blk, a - ZS + k, v - ZBSS + NBSS); fixes += 1
                else:
                    ext.add(("data", v))
            if ins.mnemonic == "ret" or ins.mnemonic == "jmp":
                break
            a += ins.size
    # every external target / datum must be identical in ours (vanilla code, VMTs, IAT, globals)
    diff = []
    for kind, v in sorted(ext):
        if v in (0x558FA040, 0x558FA044):
            continue
        if z[zoff(v):zoff(v) + 8] != ours[ooff(v):ooff(v) + 8]:
            diff.append((kind, hex(v)))
    assert not diff, diff
    assert (0x5584FAC0 + 0) not in seen
    # helper -> our neighbour
    h = HELPER - ZS
    blk[h:h + 5] = b"\xe9" + struct.pack("<i", THUNK - (HELPER + DELTA + 5))
    # ValidPath cap
    c = CAP - ZS
    assert blk[c:c + 3] == b"\x83\xfe\x04", blk[c:c + 3].hex()
    blk[c + 2] = 0x1C
    # prompt text
    t = TXT_SITE - ZS
    assert blk[t:t + 3] == bytes.fromhex("6bf805")
    rep = asm(f"""
        mov  edi, eax
        mov  eax, esi
        mov  dl, 1
        call {THUNK:#x}
        test eax, eax
        js   {TXT_SKIP + DELTA:#x}
        mov  edx, eax
        mov  eax, edi
        call {MK + 0x40:#x}
        mov  edi, eax
        jmp  {TXT_END + DELTA:#x}
    """, TXT_SITE + DELTA)
    assert len(rep) <= TXT_END - TXT_SITE, len(rep)
    blk[t:TXT_END - ZS] = rep + b"\x90" * (TXT_END - TXT_SITE - len(rep))
    return bytes(blk), len(seen), fixes, len(ext)


def main():
    import pefile
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    z = open(ZIG, "rb").read(); zpe = pefile.PE(data=z)
    zoff = lambda va: zpe.get_offset_from_rva(va - BASE)  # noqa: E731
    d = open(DLL, "rb").read(); pe = pefile.PE(data=d)
    off = lambda va: pe.get_offset_from_rva(va - BASE)  # noqa: E731
    if b"MLU2" not in d or b"MLM1" not in d:
        print("ABORT: patch_map_levels_ui_editor_v3 must be applied first"); return 1
    blk, nins, nfix, next_ = relocated(z, zoff, d, off)
    mk = mktext_zone()
    P = [(NEW, bytes(len(blk)), blk), (MK, bytes(len(mk)), mk)]
    for site, orig, tgt in HOOKS:
        P.append((site, bytes.fromhex(orig), b"\xe9" + struct.pack("<i", tgt + DELTA - (site + 5)) + b"\x90"))
    for slot, old, new in VMT_SLOTS:
        P.append((slot, struct.pack("<I", old), struct.pack("<I", new + DELTA)))
    rl = {BASE + e.rva for b in pe.DIRECTORY_ENTRY_BASERELOC for e in b.entries if e.type == 3}
    badrl = [hex(r) for r in rl if any(s - 3 <= r < s + len(o) for s, o, _ in P[:5]) and
             not any(r == s for s, _, _ in VMT_SLOTS)]
    vmt_rl = all(s in rl for s, _, _ in VMT_SLOTS)
    st = []
    for s, o, n in P:
        c = d[off(s):off(s) + len(o)]
        st.append("vanilla" if c == o else "ours" if c == n else "OTHER")
    print("block %d B -> %#x (%d insns, %d fixups, %d externals verified) | %s | relocs %s | VMT slots relocated %s"
          % (len(blk), NEW, nins, nfix, next_, st, badrl or "none", vmt_rl))
    if "OTHER" in st or badrl or not vmt_rl:
        print("ABORT"); return 1
    want = "vanilla" if revert else "ours"
    if set(st) == {want}:
        print("already %s" % ("reverted" if revert else "applied")); return 0
    if len(set(st)) != 1:
        print("ABORT (mixed state)"); return 1
    if not apply and not revert:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    r = subprocess.run(["tasklist"], capture_output=True, text=True).stdout
    if "AoWx.exe" in r or "AoWDevX.exe" in r:
        print("game/editor running - close it first"); return 1
    bak = bak_path(DLL, ".bak_flylevels")
    if not revert and not os.path.exists(bak):
        shutil.copy2(DLL, bak)
    with open(DLL, "r+b") as f:
        for s, o, n in P:
            f.seek(off(s)); f.write(o if revert else n)
    d2 = open(DLL, "rb").read()
    assert all(d2[off(s):off(s) + len(o)] == (o if revert else n) for s, o, n in P)
    print("reverted" if revert else "written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
