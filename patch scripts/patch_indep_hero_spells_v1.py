#!/usr/bin/env python3
r"""
Independent heroes with Spell Casting cast level-1 Cosmos spells in combat (AoWEPACK.dll + AoWTCPCK.dll, 2026-11-14).

User: "independent heroes who have spellcasting cant use it because they dont have any leader spheres presumably. i
want them to be able to cast level 1 cosmos spells, like dispel magic, enchant weapon, magic missile".

RE:
  * Independents = player 0 (TPlayers.GetPlayer 0x557544D0 takes idx >= 0); its TPlayerMagicControl = [player+0x54]
    (known-spell id list [pmc+0x30], mana [pmc+0x24]).  The AI never uses a spell book: fast combat
    (fcPrefetchCombatCommands loop 0x5576E3CE) and tactical TCAI.EvalBattle (4 IndexOf tests on [pmc+0x30]) only cast
    spells in that list, and THero.CanCastSpellInstantly -> 0x55789710 needs player mana >= CastingMana.  Player 0 has
    no spheres -> empty list, no mana.
  * TCAI.EvalBattle additionally skips the caster when its owner byte [unit+0x24] <= 0 at three of its four spell
    blocks (`cmp byte [eax+0x24],0 / jle` @0x418755, 0x418BA2, 0x4195EB; the block @0x418F7E has no such test).
  * Spell: sphere byte +0x20 (0 = Cosmos: GetSpherePicks `test dl,dl / je -> 4`), tier byte +0x21.

Patch:
  AoWEPACK  TCombat.Create entry 0x5572708C (`jmp 0x5580DCE8`, the per-combat flag reset of the spell-AI work) ->
            cave 0x558E4000..0x558E4100 'IHS1' (PIC), then on to 0x5580DCE8.  At every combat start (fast and
            tactical, every machine): player 0 mana raised to >= 1000, and every spell with sphere 0 / tier 1 that
            is missing from its known list is added (TIntegerList IndexOf 0x55702EA4 / Add 0x55702E74).  Idempotent,
            reads/writes synced state only.
  AoWTCPCK  the three owner gates jle (0F 8E) -> jl (0F 8C): owner 0 may cast, owner < 0 still skipped.
Casting stays limited by the hero's own casting points; which spell is cast is the normal AI scoring.

Dry-run default; --apply / --revert (surgical).  Backups backup\AoWEPACK.dll.bak_indepspell / AoWTCPCK.dll.bak_indepspell.
"""
import os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

SUF = ".bak_indepspell"
EP, EP_D = game_file("AoWEPACK.dll"), 0x55700C00
TC, TC_D = game_file("AoWTCPCK.dll"), 0x400C00
CAVE, CAVE_END, MAGIC = 0x558E4000, 0x558E4100, b"IHS1"
CODE = CAVE + 4
SITE, OLD_TGT = 0x5572708C, 0x5580DCE8
GETPLAYER, SPELLCOUNT, GETSPELL, INDEXOF, ADD = 0x557544D0, 0x55779AC0, 0x55779AC8, 0x55702EA4, 0x55702E74
G_GAME, G_RES = 0x558FA040, 0x558FA044
MANA = 1000
GATES = (0x418755, 0x418BA2, 0x4195EB)


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
