#!/usr/bin/env python3
r"""
DLL host guard (2026-10-19).  User: AoWDevX "Access violation at address 5586E017 in module 'AoWEPACK.dll'.
Read of address 0060EFE0" while loading a map (intermittent).

Cause: three DLL caves address AoWx.exe memory ABSOLUTELY (the exe never rebases, ImageBase 0x400000), but the
same DLLs are also loaded by AoWDevX.exe, whose image is only 0x400000..0x53CC00 (SizeOfImage 0x13CC00):
  L1/L2  AoWEPACK 0x5586E017 / 0x5586E047  `cmp byte [0x60EFE0],0`  (patch_staticshield_listhide_v1 filter caves in
         front of Static Shield's GetAbilityEnabled tails - HOT path, also runs in the editor) -> 0x60EFE0 lies past
         AoWDevX's image: unmapped = AV, or (intermittent) whatever heap happens to sit there.
  ET     AoWEPACK 0x55860014 `mov eax,[0x45A0CC]` (build_endturn_hotkey_light: Ctrl+E / Ctrl+Enter) -> in AoWDevX
         0x45A0CC is inside .rsrc (garbage pointer, deref'd twice).
  T1/T0  AoWTCPCK 0x444410 / 0x44441D `mov byte [0x60EFE0],1/0` (listhide's combat-panel wrap; AoWDevX imports
         AoWTCPCK too) -> a WRITE past the editor image.
All other absolute exe references found by a full no-reloc scan of AoWEPACK/AoWTCPCK/HSEPack/ILPACK/aowInt/VCL30/
Vcladdon are already host-gated (0x55815370 SOI>=0x20F000 + sig, 0x5581F814 hex grid, 0x55873C20/0x55874410 PEB +
SOI + 'TSHK') or are compare-only (aowInt VMT compares).

Fix: a host gate = PEB.ImageBaseAddress == 0x400000, e_lfanew sane, SizeOfImage >= 0x20F000 and the dword at
0x4574AC (AoWx TTBWindow.TurnButtonChange entry, 53 8B D8 A1) matches.  AoWDevX fails at SizeOfImage (0x13CC00).
  L1/L2 (7 B each) -> `call gate_flag; nop; nop`   gate_flag: not host -> ZF=1 (= "flag clear"), else cmp flag,0
  ET    (5 B)      -> `call gate_tb`              gate_tb:  not host -> eax=0 (cave falls back to plain EndTurn)
  T1/T0 (7 B each) -> `call tc_set1/tc_set0; nop; nop`  not host -> no write; eax (vcall result) preserved
Zones (verified zero, reloc-free): AoWEPACK 0x5581F200..0x5581F300, AoWTCPCK 0x451C00..0x451D00; header 'HGD1' +
the original site bytes for an exact --revert.  A part whose site holds neither the expected original nor our call
is skipped (and reported).  Backups <game>\backup\*.bak_hostguard.  Dry-run default; --apply / --revert.
Revert this BEFORE patch_staticshield_listhide_v1 / build_endturn_hotkey_light.
"""
import argparse, os, re, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
import pefile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

SUF = ".bak_hostguard"
MAGIC = b"HGD1"
SIG_VA, SIG = 0x4574AC, 0xA1D88B53
SOI_MIN = 0x20F000
ks = Ks(KS_ARCH_X86, KS_MODE_32)
def asm(src, va): return bytes(ks.asm(src, va)[0])

EZ, TZ = 0x5581F200, 0x451C00
E_SITES = [("L1", 0x5586E017, bytes.fromhex("803de0ef600000"), "gate_flag"),
           ("L2", 0x5586E047, bytes.fromhex("803de0ef600000"), "gate_flag"),
           ("ET", 0x55860014, bytes.fromhex("a1cca04500"), "gate_tb")]
T_SITES = [("T1", 0x444410, bytes.fromhex("c605e0ef600001"), "tc_set1"),
           ("T0", 0x44441D, bytes.fromhex("c605e0ef600000"), "tc_set0")]

HOST = """
host:
    push eax
    push edx
    mov  eax, dword ptr fs:[0x30]
    mov  eax, dword ptr [eax + 8]
    cmp  eax, 0x400000
    jne  hx
    mov  edx, dword ptr [eax + 0x3c]
    cmp  edx, 0x400
    ja   hx
    cmp  dword ptr [eax + edx + 0x50], %(soi)#x
    jb   hx
    cmp  dword ptr [%(sva)#x], %(sig)#x
hx:
    pop  edx
    pop  eax
    ret
""" % {"soi": SOI_MIN, "sva": SIG_VA, "sig": SIG}

E_SRC = """
gate_flag:
    call host
    jne  gf_z
    cmp  byte ptr [0x60efe0], 0
    ret
gf_z:
    cmp  eax, eax
    ret
gate_tb:
    call host
    jne  gt_z
    mov  eax, dword ptr [0x45a0cc]
    ret
gt_z:
    xor  eax, eax
    ret
""" + HOST

T_SRC = """
tc_set1:
    call host
    jne  t1r
    mov  byte ptr [0x60efe0], 1
t1r:
    ret
tc_set0:
    call host
    jne  t0r
    mov  byte ptr [0x60efe0], 0
t0r:
    ret
""" + HOST


def build(src, base):
    code = asm(src, base)
    lab = {}
    for nm in re.findall(r"^\s*(\w+):\s*$", src, re.M):
        b = asm(src + chr(10) + ".long %s" % nm + chr(10), base)
        lab[nm] = struct.unpack_from("<I", b, len(b) - 4)[0]
    return code, lab


class Img:
    def __init__(s, p):
        s.p = p; s.d = bytearray(open(p, "rb").read()); s.pe = pefile.PE(data=bytes(s.d)); s.b = s.pe.OPTIONAL_HEADER.ImageBase
        s.rel = {e.rva + s.b for bl in getattr(s.pe, "DIRECTORY_ENTRY_BASERELOC", []) for e in bl.entries if e.type}
    def o(s, va): return s.pe.get_offset_from_rva(va - s.b)
    def rd(s, va, n): o = s.o(va); return bytes(s.d[o:o + n])
    def wr(s, va, b): o = s.o(va); s.d[o:o + len(b)] = b
    def relocs(s, lo, hi): return [v for v in s.rel if lo <= v < hi]


def plan(im, zone, sites, src):
    code_va = zone + 0x40
    code, lab = build(src, code_va)
    hdr = MAGIC + b"".join(o for _, _, o, _ in sites)
    assert len(hdr) <= 0x40 and code_va + len(code) <= zone + 0x100
    zcur = im.rd(zone, 0x100)
    zstate = "zero" if not any(zcur) else ("ours" if zcur[:len(hdr)] == hdr and zcur[0x40:0x40 + len(code)] == code else "FOREIGN")
    st = {}
    for nm, va, orig, fn in sites:
        cur = im.rd(va, len(orig))
        call = b"\xE8" + struct.pack("<i", lab[fn] - (va + 5)) + b"\x90" * (len(orig) - 5)
        st[nm] = ("vanilla" if cur == orig else "ours" if cur == call else "OTHER(%s)" % cur.hex(), call)
        assert not im.relocs(va, va + len(orig)), (nm, "reloc under site")
    assert not im.relocs(zone, zone + 0x100), "reloc in zone"
    return hdr, code, lab, zstate, st


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dll", default=game_file("AoWEPACK.dll")); ap.add_argument("--tc", default=game_file("AoWTCPCK.dll"))
    a = ap.parse_args()
    E, T = Img(a.dll), Img(a.tc)
    parts = [(E, EZ, E_SITES, E_SRC, "AoWEPACK.dll"), (T, TZ, T_SITES, T_SRC, "AoWTCPCK.dll")]
    plans = []
    for im, zone, sites, src, nm in parts:
        hdr, code, lab, zs, st = plan(im, zone, sites, src)
        print("%s zone %#x %s (%d B code) | %s" % (nm, zone, zs, len(code), ", ".join("%s %s" % (k, v[0]) for k, v in st.items())))
        assert zs != "FOREIGN", "zone not free - inspect"
        plans.append((im, zone, sites, hdr, code, zs, st, nm))

    if a.revert:
        ch = False
        for im, zone, sites, hdr, code, zs, st, nm in plans:
            for snm, va, orig, fn in sites:
                if st[snm][0] == "ours": im.wr(va, orig); ch = True
            if zs == "ours": im.wr(zone, b"\0" * 0x100); ch = True
        if not ch: print("already reverted"); return 0
        for im, *_ in plans: open(im.p, "r+b").write(im.d)
        print("reverted"); return 0

    todo = any(v[0] == "vanilla" for p in plans for v in p[6].values())
    if not todo: print("already applied (nothing vanilla left)"); return 0
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    for im, zone, sites, hdr, code, zs, st, nm in plans:
        if os.path.abspath(im.p) == os.path.abspath(game_file(nm)):
            b = bak_path(im.p, SUF)
            if not os.path.exists(b): shutil.copy2(im.p, b); print("backup ->", b)
        im.wr(zone, hdr + b"\0" * (0x40 - len(hdr))); im.wr(zone + 0x40, code)
        for snm, va, orig, fn in sites:
            if st[snm][0] == "vanilla": im.wr(va, st[snm][1])
            elif st[snm][0] != "ours": print("  skip %s (%s)" % (snm, st[snm][0]))
    for im, *_ in plans:
        with open(im.p, "r+b") as f: f.write(im.d)
    for im, zone, sites, hdr, code, zs, st, nm in plans:
        assert Img(im.p).rd(zone + 0x40, len(code)) == code
    print("written and verified: DLL caves read/write AoWx.exe memory only when the host is AoWx.exe"); return 0


if __name__ == "__main__":
    sys.exit(main())
