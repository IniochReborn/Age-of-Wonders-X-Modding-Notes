#!/usr/bin/env python3
r"""
Slowed (ability 0xB9, spell 380 Slow): DOUBLE MOVEMENT COST instead of half movement points (2026-11-16).

User: "currently slowed takes away half a unit's movement. the problem is that it stops them from using ranged
abilities and spellcasting. maybe it should double movement cost instead. this should stack with other movement
bonuses/maluses".

Before (patch_slow_v1): TTacticalCombatUnit.NewTurn cave (TCPCK 0x43F000) halved the combat allowance [cu+0x5C];
ranged shots / casting need move points left, so a Slowed archer or caster lost its actions.

Now: the allowance stays whole and every step costs double.  Combat step costs come from the unit's move point
table: TAbstractUnit.CreateMovePointTable (AoWEPACK 0x5577FDC4; eax unit, edx 16x16 byte table, cell
[terrain*16 + col]; <= 0 = impassable/unused) - called by the player path/reach code
(TCombatUnitSelectionControl.CalculateMovePath/Update) and by every TCAI path evaluation, with the STRATEGIC unit
[cu+0x4C], which is the object that holds 0xB9.  The function is already wrapped at 0x55856440:
    call <vanilla body: terrain template, Haste -1, 0x84 +2, ...> / call 0x558562B0 (Black Tide) / jmp 0x55856380
    (Nimue's Favour).
 1. AoWEPACK 0x5585644E `jmp 0x55856380` -> cave 0x55856480: call 0x55856380, then if the unit has 0xB9
    (VMT+0x148) double every cell > 0 in columns 0..12 of all 16 rows (the same cells the vanilla modifier loops
    touch), capped at 0x7F.  It runs LAST, so it multiplies whatever the other bonuses / maluses produced.
 2. AoWTCPCK 0x43F00C `je +0x21` -> `jmp +0x21`: the NewTurn cave no longer halves [cu+0x5C].
 3. AoWEPACK 0x55839102 `sar esi,1` -> nops: Second Wind's refill cap no longer assumes a halved allowance.
0xB9 is a combat-only duration ability, so the world map is unaffected.  Fast (auto) combat: no effect, as before.
MP: pure function of synced state.  Relative code only, no relocs.
Layered on patch_slow_v1 / patch_secondwind_v1 (their dry runs will report their caves as changed while this is
applied) - revert this FIRST.  Backups .bak_slowx2 on both DLLs.  Dry run by default; --apply / --revert.
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

BAK_SUFFIX = ".bak_slowx2"
EP, EP_V2F = game_file("AoWEPACK.dll"), 0x55700C00
TC, TC_V2F = game_file("AoWTCPCK.dll"), 0x400C00
HOOK_VA, NIMUE, CAVE_VA, CAVE_ROOM = 0x5585644E, 0x55856380, 0x55856480, 0x80
ABIL = 0xB9


def rel(op, at, to): return bytes([op]) + struct.pack("<i", to - (at + 5))


def build_cave():
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    src = """
        push eax
        push edx
        call %#x
        pop edx
        pop eax
        pushad
        mov esi, edx
        mov edx, %#x
        mov ecx, [eax]
        call dword ptr [ecx + 0x148]
        test al, al
        je done
        xor ecx, ecx
    lp:
        mov edx, ecx
        and edx, 0x0f
        cmp edx, 13
        jae nx
        movsx eax, byte ptr [esi + ecx]
        test eax, eax
        jle nx
        add eax, eax
        cmp eax, 0x7f
        jbe ok
        mov eax, 0x7f
    ok:
        mov [esi + ecx], al
    nx:
        inc ecx
        cmp ecx, 0x100
        jb lp
    done:
        popad
        ret
    """ % (NIMUE, ABIL)
    enc, _ = Ks(KS_ARCH_X86, KS_MODE_32).asm(src, CAVE_VA)
    return bytes(enc)


def relocs(path):
    import pefile
    pe = pefile.PE(path, fast_load=True)
    pe.parse_data_directories([pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_BASERELOC"]])
    ib = pe.OPTIONAL_HEADER.ImageBase
    return [ib + e.rva for blk in getattr(pe, "DIRECTORY_ENTRY_BASERELOC", []) for e in blk.entries if e.type]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    a = ap.parse_args()
    cave = build_cave()
    assert len(cave) <= CAVE_ROOM
    # (file, v2f, va, original, new)
    sites = [
        (EP, EP_V2F, HOOK_VA, rel(0xE9, HOOK_VA, NIMUE), rel(0xE9, HOOK_VA, CAVE_VA)),
        (EP, EP_V2F, CAVE_VA, bytes(len(cave)), cave),
        (EP, EP_V2F, 0x55839102, bytes.fromhex("d1fe"), bytes.fromhex("9090")),
        (TC, TC_V2F, 0x43F00C, bytes.fromhex("7421"), bytes.fromhex("eb21")),
    ]
    ctx = [(EP, EP_V2F, 0x558390EF, bytes.fromhex("bab9000000")),            # Second Wind: mov edx,0xB9
           (TC, TC_V2F, 0x43F00E, bytes.fromhex("bab9000000")),              # NewTurn cave: mov edx,0xB9
           (TC, TC_V2F, 0x43F02A, bytes.fromhex("d1e889425c"))]              # shr eax,1 / mov [edx+0x5C],eax
    data = {p: bytearray(open(p, "rb").read()) for p in (EP, TC)}
    for p, v, va, want in ctx:
        if bytes(data[p][va - v:va - v + len(want)]) != want:
            print("ABORT: context at %#x not found (patch_slow_v1 / patch_secondwind_v1 expected)" % va); return 1
    st = []
    for p, v, va, o, n in sites:
        cur = bytes(data[p][va - v:va - v + len(o)])
        st.append("vanilla" if cur == o else "ours" if cur == n else "OTHER")
    print("sites:", ", ".join("%#x=%s" % (s[2], t) for s, t in zip(sites, st)), "| cave %d B" % len(cave))
    if "OTHER" in st or len(set(st)) != 1: print("ABORT (mixed / foreign state)"); return 1
    if st[0] == "vanilla" and any(data[EP][CAVE_VA - EP_V2F:CAVE_VA - EP_V2F + CAVE_ROOM]):
        print("ABORT: cave zone not empty"); return 1
    rl = {EP: relocs(EP), TC: relocs(TC)}
    bad = [hex(r) for p, v, va, o, n in sites for r in rl[p] if va - 3 <= r < va + len(o)]
    if bad: print("ABORT: relocs in range", bad); return 1
    if st[0] == ("vanilla" if a.revert else "ours"):
        print("already %s" % ("reverted" if a.revert else "applied")); return 0
    if not (a.apply or a.revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    for p in (EP, TC):
        bak = bak_path(p, BAK_SUFFIX)
        if not a.revert and not os.path.exists(bak): shutil.copy2(p, bak); print("backup ->", bak)
    for p, v, va, o, n in sites:
        w = o if a.revert else n
        data[p][va - v:va - v + len(w)] = w
        with open(p, "r+b") as f: f.seek(va - v); f.write(w)       # in-place (house rule)
    for p in (EP, TC): assert open(p, "rb").read() == bytes(data[p])
    print("reverted" if a.revert else "Written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
