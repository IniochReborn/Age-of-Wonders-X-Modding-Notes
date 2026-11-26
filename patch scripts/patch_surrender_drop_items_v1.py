"""patch_surrender_drop_items_v1.py  [--apply | --revert]

Surrendering no longer destroys the items a leader / hero carries - they are dropped on the world map like on death.
(user 2026-11-19: closes the "surrender before dying to deny the items" exploit)

1. Surrender in combat (tactical "Surrender" -> CombatTE.TCEndCombatTE.Execute -> every unit's VMT+0x11C =
   TCombatUnit.Surrender 0x557257B8).  Surrender ends in KillUnit -> THero.Killed, whose item drop goes through the
   tactical map (TAoWCombatMap.DropHeroItem) and silently does nothing when the unit's battlefield position cannot be
   found, so the items died with the hero.  Entry hook: unit [cu+0x4C] is a THero (class ref 0x55711FAC) ->
   THero.DropItemsOnMap 0x557870D4 (eax=hero, edx=map, cl=x, push y, push level) at the battle location
   ([[cu+8]+0xC] +8/+0xC/+0x10) - the same call auto-combat makes in TFastCombatUnit.KillUnit 0x55743A78.
2. Surrender on the world map (TPlayer.Surrender -> TGameOverTE -> TPlayer.SetGameOverStatus: every army ->
   TArmy.SetPlayer(0) -> unit VMT+0x16C).  TLeader.SetPlayer 0x5578B4F0 removes a leader that belonged to a real
   player (VMT+8 with nil) without touching its items.  Hook before that removal (0x5578B4FE): leader location
   (TAbstractUnit.GetLocation 0x5577ED94) -> the same DropItemsOnMap.

Cave 0x558BA100 (AoWEPACK CODE, was zero; PIC).  In-place apply/revert.  Multiplayer: every player needs it (sync).
"""
import argparse, os, shutil, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path

DLL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "AoWEPACK.dll")
V2F = 0x55700C00
S1, S1_ORIG, S1_BACK = 0x557257B8, bytes.fromhex("538bd88bc3"), 0x557257BD
S2, S2_ORIG, S2_BACK = 0x5578B4FE, bytes.fromhex("33d28bc38b08"), 0x5578B504
CAVE, CAVE_MAX = 0x558BA100, 0x100
MAPVAR, HERO_CLASS = 0x558FA040, 0x55711FAC
ISCLASS, DROPITEMS, GETLOCATION = 0x557010C0, 0x557870D4, 0x5577ED94


def build():
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    src = f"""
    h1:
        push ebx
        mov ebx, eax
        push esi
        push ebp
        call d1
    d1:
        pop ebp
        sub ebp, d1
        mov esi, [ebx + 0x4c]
        test esi, esi
        jz h1x
        mov eax, esi
        mov edx, [ebp + {HERO_CLASS:#x}]
        call {ISCLASS:#x}
        test al, al
        jz h1x
        mov eax, [ebx + 8]
        test eax, eax
        jz h1x
        mov eax, [eax + 0xc]
        test eax, eax
        jz h1x
        mov dl, [eax + 0xc]
        push edx
        mov dl, [eax + 0x10]
        push edx
        mov cl, [eax + 8]
        mov edx, [ebp + {MAPVAR:#x}]
        mov eax, esi
        call {DROPITEMS:#x}
    h1x:
        pop ebp
        pop esi
        mov eax, ebx
        jmp {S1_BACK:#x}

    h2:
        push ebp
        call d2
    d2:
        pop ebp
        sub ebp, d2
        sub esp, 4
        lea eax, [esp + 2]
        push eax
        lea ecx, [esp + 5]
        lea edx, [esp + 4]
        mov eax, ebx
        call {GETLOCATION:#x}
        cmp byte ptr [esp], 0xff
        je h2x
        movzx eax, byte ptr [esp + 1]
        push eax
        movzx eax, byte ptr [esp + 6]
        push eax
        mov cl, [esp + 8]
        mov edx, [ebp + {MAPVAR:#x}]
        mov eax, ebx
        call {DROPITEMS:#x}
    h2x:
        add esp, 4
        pop ebp
        xor edx, edx
        mov eax, ebx
        mov ecx, [eax]
        jmp {S2_BACK:#x}
    """
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    code = bytes(ks.asm(src, CAVE)[0])
    h2 = struct.unpack("<I", bytes(ks.asm(src + "\n.long h2\n", CAVE)[0])[-4:])[0]
    assert len(code) <= CAVE_MAX
    return code, h2


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    a = ap.parse_args()
    cave, h2 = build()
    n1 = bytes([0xE9]) + struct.pack("<i", CAVE - (S1 + 5))
    n2 = bytes([0xE9]) + struct.pack("<i", h2 - (S2 + 5)) + b"\x90"
    d = open(DLL, "rb").read()
    c1, c2, cc = d[S1 - V2F:S1 - V2F + 5], d[S2 - V2F:S2 - V2F + 6], d[CAVE - V2F:CAVE - V2F + CAVE_MAX]
    vanilla = c1 == S1_ORIG and c2 == S2_ORIG and not any(cc)
    ours = c1 == n1 and c2 == n2 and cc == cave + bytes(CAVE_MAX - len(cave))
    older = c1[0] == 0xE9 and c2[0] == 0xE9 and not ours
    state = "vanilla" if vanilla else "ours" if ours else "older build" if older else "OTHER"
    print("sites %#x / %#x, cave %#x (%d B): %s" % (S1, S2, CAVE, len(cave), state))
    if state == "OTHER": print("ABORT: foreign bytes", c1.hex(), c2.hex()); return 1
    if state == ("vanilla" if a.revert else "ours"): print("already %s" % ("reverted" if a.revert else "applied")); return 0
    if not (a.apply or a.revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    b = bak_path(DLL, ".bak_surrenderdrop")
    if a.apply and not os.path.exists(b): shutil.copy2(DLL, b); print("backup ->", b)
    with open(DLL, "r+b") as f:
        f.seek(CAVE - V2F); f.write(bytes(CAVE_MAX))
        if a.apply: f.seek(CAVE - V2F); f.write(cave)
        f.seek(S1 - V2F); f.write(n1 if a.apply else S1_ORIG)
        f.seek(S2 - V2F); f.write(n2 if a.apply else S2_ORIG)
    print("Written" if a.apply else "reverted")
    return 0


if __name__ == "__main__":
    sys.exit(main())
