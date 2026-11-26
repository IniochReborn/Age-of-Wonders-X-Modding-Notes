#!/usr/bin/env python3
r"""
Independent heroes cast level-1 Cosmos spells - part 3: the "Independents" PLAYER (owner 0) (2026-11-14).

Live trace (indep_cast_trace.py): the independent hero 'Tanaris' has owner byte 0 - independents on a map belong to
player 0, the Independents player, which HAS a player object and a TPlayerMagicControl (real players start at 1;
owner -1 = unowned units, handled by the GetPlayer stand-in of patch_indep_hero_spells_v2).  The tactical AI reached
"spell type != 0 -> GetPlayer" for him and stopped at "spell is known": player 0's known-spell list is empty.
(v1 did exactly this grant and was reverted for the wrong reason - what actually blocked it were the AI's owner
gates and the 0x83 spell-loop limit, both fixed by v2 / v2.1.)

AoWEPACK TCombat.Create entry 0x5572708C (`jmp 0x5580DCE8`) -> cave 0x558E4400..0x558E4500 'IHS3' (PIC) -> 0x5580DCE8:
at every combat start player 0's mana is raised to >= 100 and every sphere-0 / tier-1 spell missing from its known
list [pmc+0x30] is added.  Idempotent; needs patch_indep_hero_spells_v2 (gates + loops) to have any effect.
Dry-run default; --apply / --revert.  Backup backup\AoWEPACK.dll.bak_indepspell3.
"""
import os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

SUF = ".bak_indepspell3"
EP, EP_D = game_file("AoWEPACK.dll"), 0x55700C00
TC, TC_D = game_file("AoWTCPCK.dll"), 0x400C00
CAVE, CAVE_END, MAGIC = 0x558E4400, 0x558E4500, b"IHS3"
CODE = CAVE + 4
SITE, OLD_TGT = 0x5572708C, 0x5580DCE8
GETPLAYER, SPELLCOUNT, GETSPELL, INDEXOF, ADD = 0x557544D0, 0x55779AC0, 0x55779AC8, 0x55702EA4, 0x55702E74
G_GAME, G_RES = 0x558FA040, 0x558FA044
MANA = 100
GATES = ()


def jmp(frm, to):
    return b"\xE9" + struct.pack("<i", to - frm - 5)


def cave_code():
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    src = f"""
        pushal
        call n
    n:
        pop ebx
        sub ebx, {CODE + 6:#x}
        mov eax, dword ptr [ebx + {G_GAME:#x}]
        test eax, eax
        jz out
        mov eax, dword ptr [eax + 0x140]
        test eax, eax
        jz out
        xor edx, edx
        call {GETPLAYER:#x}
        test eax, eax
        jz out
        mov esi, dword ptr [eax + 0x54]
        test esi, esi
        jz out
        cmp dword ptr [esi + 0x24], {MANA}
        jge m
        mov dword ptr [esi + 0x24], {MANA}
    m:
        cmp dword ptr [esi + 0x30], 0
        jz out
        mov eax, dword ptr [ebx + {G_RES:#x}]
        test eax, eax
        jz out
        mov ebp, dword ptr [eax + 0x84]
        test ebp, ebp
        jz out
        mov eax, ebp
        call {SPELLCOUNT:#x}
        mov edi, eax
    lp:
        dec edi
        js out
        mov eax, ebp
        mov edx, edi
        call {GETSPELL:#x}
        test eax, eax
        jz lp
        cmp word ptr [eax + 0x20], 0x100
        jne lp
        mov eax, dword ptr [esi + 0x30]
        mov edx, edi
        call {INDEXOF:#x}
        inc eax
        jnz lp
        mov eax, dword ptr [esi + 0x30]
        mov edx, edi
        call {ADD:#x}
        jmp lp
    out:
        popal
        jmp {OLD_TGT:#x}
    """
    enc, _ = Ks(KS_ARCH_X86, KS_MODE_32).asm(src, CODE)
    return bytes(enc)


def main():
    apply, revert = "--apply" in sys.argv, "--revert" in sys.argv
    ep, tc = bytearray(open(EP, "rb").read()), bytearray(open(TC, "rb").read())
    code = cave_code()
    blob = MAGIC + code
    assert len(blob) <= CAVE_END - CAVE, hex(len(blob))
    o_c, o_s = CAVE - EP_D, SITE - EP_D
    cur_site = bytes(ep[o_s:o_s + 5])
    cur_cave = bytes(ep[o_c:o_c + (CAVE_END - CAVE)])
    gates = [bytes(tc[g - TC_D:g - TC_D + 2]) for g in GATES]
    applied = cur_site == jmp(SITE, CODE) and cur_cave.startswith(blob)
    clean = cur_site == jmp(SITE, OLD_TGT) and not any(cur_cave) and all(g == b"\x0F\x8E" for g in gates)
    print("cave %#x..%#x: %d B code | state: %s | gates %s"
          % (CAVE, CAVE + len(blob), len(code), "APPLIED" if applied else "clean" if clean else "UNKNOWN",
             " ".join(g.hex() for g in gates)))
    if revert:
        if not applied:
            print("not applied - nothing to revert"); return 1
        ep[o_s:o_s + 5] = jmp(SITE, OLD_TGT)
        ep[o_c:o_c + (CAVE_END - CAVE)] = bytes(CAVE_END - CAVE)
        for g in GATES:
            assert tc[g - TC_D:g - TC_D + 2] in (b"\x0F\x8C", b"\x0F\x8E")
            tc[g - TC_D + 1] = 0x8E
        open(EP, "wb").write(ep); open(TC, "wb").write(tc)
        print("reverted"); return 0
    if applied and all(g == b"\x0F\x8C" for g in gates):
        print("ALREADY PATCHED"); return 0
    if not clean:
        print("ABORT: unexpected bytes (site %s)" % cur_site.hex()); return 1
    if not apply:
        print("Dry run OK - rerun with --apply"); return 0
    for f in (EP, TC):
        b = bak_path(f, SUF)
        if not os.path.exists(b):
            shutil.copy2(f, b); print("backup ->", b)
    ep[o_c:o_c + len(blob)] = blob
    ep[o_s:o_s + 5] = jmp(SITE, CODE)
    for g in GATES:
        tc[g - TC_D + 1] = 0x8C
    open(EP, "wb").write(ep); open(TC, "wb").write(tc)
    print("applied")
    return 0


if __name__ == "__main__":
    sys.exit(main())
