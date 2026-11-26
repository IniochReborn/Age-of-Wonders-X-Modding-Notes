#!/usr/bin/env python3
r"""
Spellbook: no needless "charging" book page when a caster-cost discount makes the spell affordable now (AoWx.exe,
2026-10-18).

User: "with 2 casting points, Enchant Weapon (cost 3) starts charging and the book shows how long until it is ready.
With Enchanter the cost drops 3 -> 2 (affordable), but the book popup still appears as if it needs to charge; after
closing it I can cast correctly.  Same for Conjurer / Ritualist / Evoker - whenever a reduced cost makes a spell
castable immediately."

Cause: the strategic spellbook click handler (TSpellBookWindow, fn 0x430788, mode [ebx+0x220]=0) decides between
"cast now and close the book" and "start casting and show the casting page" by comparing the hero's casting points
(VMT+0x12C) with the RAW spell cost [spell+0x14] (0x430844 `cmp eax,[esi+0x14]`).  The engine side (THero.CastSpell /
CanCastSpellInstantly, CastingMana + the caster-cost wallet fix) already uses the discounted cost, so the spell is
cast at once - but the exe then still runs 0x43073C, the "casting in progress" page.

Fix: 0x430833..0x430852 (32 B; the reloc'd dword at 0x430854 is left untouched) now asks the engine:
    lea eax,[ebp-4] ; push eax ; mov ecx,[esi+0x14] ; mov edx,[esi+0x10] ; mov eax,[ebx+0x22C]
    call THero.CanCastSpellInstantly (thunk 0x4027A4) ; test al,al ; jne 0x430871 (cast + close book) ; jmp 0x4308AC
CanCastSpellInstantly 0x55789640 (wallet-fixed: the raw cost argument is replaced by CastingMana = the discounted
cost) is true when cost <= casting points, or the player's free-cast/cheat flag is set (the old 0x40260C test that
this replaces), or the hero is casting this very spell and it is ready - and only if CanCastSpell passes.  Every other
case falls to the original "start casting" branch (CastSpell, then the casting page, or its error message).
[ebp-4] is the handler's own AnsiString local (zeroed in the prologue, finalised by its SEH frame) that CastSpell
already uses for its message.  No exe cave needed.  Visual/UI only, engine untouched -> MP-safe.
Backup AoWx.exe.bak_castnopopup (in <game>\backup\).  Dry-run default; --apply; --revert.
"""
import argparse, os, shutil, struct, sys
from bakpath import game_file, bak_path
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

DEFAULT_EXE = game_file(r"AoWx.exe")
BAK = ".bak_castnopopup"
BASE = 0x400000
SITE = 0x430833
ORIG = bytes.fromhex("8b832c0200008b10ff922c0100000fbec03b46147d288b832c0200000fbe5024")
CANCAST_INSTANT_THUNK = 0x4027A4
CAST_CLOSE, CAST_CHARGE = 0x430871, 0x4308AC
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def new_bytes():
    enc, _ = ks.asm(f"""
        lea eax, [ebp-4]
        push eax
        mov ecx, [esi+0x14]
        mov edx, [esi+0x10]
        mov eax, [ebx+0x22C]
        call {CANCAST_INSTANT_THUNK:#x}
        test al, al
        jne {CAST_CLOSE:#x}
        jmp {CAST_CHARGE:#x}
    """, SITE)
    b = bytes(enc)
    assert len(b) <= len(ORIG), len(b)
    return b + b"\x90" * (len(ORIG) - len(b))


def off(d, va):
    e = struct.unpack_from("<I", d, 0x3C)[0]; n = struct.unpack_from("<H", d, e + 6)[0]
    opt = struct.unpack_from("<H", d, e + 20)[0]
    for i in range(n):
        s = e + 24 + opt + 40 * i
        vs, sva, rs, ra = struct.unpack_from("<IIII", d, s + 8)
        if sva <= va - BASE < sva + max(vs, rs): return ra + va - BASE - sva
    raise ValueError(hex(va))


def main():
    ap = argparse.ArgumentParser(description="spellbook: no charging page when the discounted cost is affordable")
    ap.add_argument("exe", nargs="?", default=DEFAULT_EXE)
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    a = ap.parse_args()
    NEW = new_bytes()
    d = bytearray(open(a.exe, "rb").read()); o = off(d, SITE)
    cur = bytes(d[o:o + len(ORIG)])
    st = "applied" if cur == NEW else ("vanilla" if cur == ORIG else "FOREIGN")
    thunk = bytes(d[off(d, CANCAST_INSTANT_THUNK):off(d, CANCAST_INSTANT_THUNK) + 6])
    assert thunk == bytes.fromhex("ff2590dc4500"), "thunk 0x4027A4 is not jmp [CanCastSpellInstantly 0x45DC90]"
    print(f"AoWx.exe spellbook cast decision @{SITE:#x}: {st}")
    if st == "FOREIGN": sys.exit("unexpected bytes - refusing")
    if a.revert:
        if st == "vanilla": print("not applied"); return
        d[o:o + len(ORIG)] = ORIG
        with open(a.exe, "r+b") as f: f.seek(0); f.write(d)
        print("reverted"); return
    if st == "applied": print("already applied"); return
    if not a.apply: print("dry run OK - nothing written (use --apply)"); return
    bak = bak_path(a.exe, BAK)
    if not os.path.exists(bak): shutil.copyfile(a.exe, bak); print("backup ->", bak)
    d[o:o + len(NEW)] = NEW
    with open(a.exe, "r+b") as f: f.seek(0); f.write(d)
    assert open(a.exe, "rb").read()[o:o + len(NEW)] == NEW
    print("written and verified")


if __name__ == "__main__":
    main()
