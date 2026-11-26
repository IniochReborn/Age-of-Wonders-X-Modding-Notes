"""patch_migrate_own_race_v1.py  [--apply | --revert]

City migration: a player may always migrate a city to THEIR OWN race when at least one unrazed, finished city of that
race exists anywhere on the map (any owner, independents included).   (user 2026-11-19)

Vanilla TCity.CanMigrate 0x557AB1D0 (eax=city, dl=race): false when the city already has that race; otherwise true only if
the city's owner ([city+0x30]) or one of its allies owns a city of that race (City.RaceInCity).  Its common exit at
0x557AB245 (`mov eax,ebx / pop edx / pop edi / pop esi / pop ebx / ret`; bl = result, edi = city, [esp] = race) is
redirected to a cave: result still false, race != city race, race == owner's race (player+0xA5) -> walk every player's
structure list ([player+0x1C]) for a TCity (class ref 0x557A73B0) that is finished ([+0x24]==0xFF), not razed
([+0x44]&2 == 0) and of that race ([+0x45]).
Same rule for the AI (UpdateAIMigration uses the same test).  Multiplayer: every player needs the patch (sync).
Cave 0x558BA000 (AoWEPACK CODE, was zero; PIC via call/pop).  In-place apply/revert (no whole-file restore).
"""
import argparse, os, shutil, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path

DLL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "AoWEPACK.dll")
V2F = 0x55700C00
SITE, ORIG = 0x557AB245, bytes.fromhex("8bc35a5f5e")
CAVE, CAVE_MAX = 0x558BA000, 0x100
MAPVAR, CITY_CLASS = 0x558E9494, 0x557A73B0
GETPLAYERS, GETSTRUCTURE, ISCLASS = 0x557544D0, 0x557507FC, 0x557010C0


def build():
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    src = f"""
    hook:
        test bl, bl
        jnz out
        mov al, [esp]
        cmp al, [edi + 0x45]
        je out
        movsx edx, byte ptr [edi + 0x30]
        test edx, edx
        jle out
        push ebp
        call d
    d:
        pop ebp
        sub ebp, d
        mov eax, [ebp + {MAPVAR:#x}]
        mov eax, [eax]
        mov eax, [eax + 0x140]
        push eax
        call {GETPLAYERS:#x}
        test eax, eax
        jz o2
        mov cl, [esp + 8]
        cmp cl, [eax + 0xa5]
        jne o2
        mov eax, [esp]
        mov edx, [eax]
        call dword ptr [edx + 0x54]
        mov esi, eax
    pl:
        dec esi
        js o2
        mov eax, [esp]
        mov edx, esi
        call {GETPLAYERS:#x}
        test eax, eax
        jz pl
        mov eax, [eax + 0x1c]
        test eax, eax
        jz pl
        push eax
        mov edx, [eax]
        call dword ptr [edx + 0x54]
        push eax
    sl:
        dec dword ptr [esp]
        js sdone
        mov edx, [esp]
        mov eax, [esp + 4]
        call {GETSTRUCTURE:#x}
        test eax, eax
        jz sl
        push eax
        mov edx, [ebp + {CITY_CLASS:#x}]
        call {ISCLASS:#x}
        pop edx
        test al, al
        jz sl
        cmp byte ptr [edx + 0x24], 0xff
        jne sl
        test byte ptr [edx + 0x44], 2
        jnz sl
        mov al, [esp + 0x10]
        cmp al, [edx + 0x45]
        jne sl
        mov bl, 1
    sdone:
        add esp, 8
        test bl, bl
        jz pl
    o2:
        add esp, 4
        pop ebp
    out:
        mov eax, ebx
        pop edx
        pop edi
        pop esi
        pop ebx
        ret
    """
    code = bytes(Ks(KS_ARCH_X86, KS_MODE_32).asm(src, CAVE)[0])
    assert len(code) <= CAVE_MAX
    return code


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    a = ap.parse_args()
    cave = build()
    new = bytes([0xE9]) + struct.pack("<i", CAVE - (SITE + 5))
    d = open(DLL, "rb").read()
    scur, ccur = d[SITE - V2F:SITE - V2F + 5], d[CAVE - V2F:CAVE - V2F + CAVE_MAX]
    vanilla = scur == ORIG and not any(ccur)
    ours = scur == new and ccur[:len(cave)] == cave and not any(ccur[len(cave):])
    older = scur == new and not ours
    state = "vanilla" if vanilla else "ours" if ours else "older build" if older else "OTHER"
    print("site %#x, cave %#x (%d B): %s" % (SITE, CAVE, len(cave), state))
    if state == "OTHER": print("ABORT: foreign bytes", scur.hex()); return 1
    if state == ("vanilla" if a.revert else "ours"): print("already %s" % ("reverted" if a.revert else "applied")); return 0
    if not (a.apply or a.revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    b = bak_path(DLL, ".bak_migrateown")
    if a.apply and not os.path.exists(b): shutil.copy2(DLL, b); print("backup ->", b)
    with open(DLL, "r+b") as f:
        f.seek(CAVE - V2F); f.write(bytes(CAVE_MAX))
        if a.apply: f.seek(CAVE - V2F); f.write(cave)
        f.seek(SITE - V2F); f.write(new if a.apply else ORIG)
    print("Written" if a.apply else "reverted")
    return 0


if __name__ == "__main__":
    sys.exit(main())
