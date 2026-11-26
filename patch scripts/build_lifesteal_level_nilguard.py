#!/usr/bin/env python3
r"""FIX: Life Stealing's execute-side level lookup can deref a nil unit pointer.

FOUND 2026-08-13 (user question: "we fixed healing, what about lifestealing?").

THE DEFECT
    `TCombatUnit.GetAbilityLevel` (combat VMT+0xB0 @0x55725028) is
        mov eax,[eax+0x4C] ; mov ecx,[eax] ; call [ecx+0x144]
    -- it dereferences the underlying TUnit with NO nil check. Its sibling
    `GetAbilityEnabled` (VMT+0xA8 @0x55725004) IS nil-guarded
        mov ecx,[eax+0x4C] ; test ecx,ecx ; je -> return 0
    i.e. the ENGINE ITSELF treats a nil [obj+0x4C] as a normal state, and only
    ever reaches +0xB0 behind an +0xA8 test.

    Every mod cave that calls +0xB0 honours that pattern -- melee Hero Slaying
    (0x5580E3EE / 0x5580E44E), ranged Hero Slaying (0x5580E53D / 0x5580E58F),
    Monster Slaying (0x5580E479 / 0x5580E4A9) and Wall Crushing (0x5580EAFD /
    0x5580EB1D) all sit directly behind an +0xA8 gate -- EXCEPT the leveled
    Life Stealing heal in `cave_lsround` @0x5580E160, hooked over
    TStrikeCA.Execute @0x5576678C. There the only gate is CA flag 0x08, which
    was set back in TStrikeCA.Generate (cave_lsgen @0x5580E1A0). Between
    Generate and Execute the attacker's combat object is re-resolved from its
    id (GetObject @0x55766748) and combat has moved on, so a unit that has
    since died/detached yields [attacker+0x4C] = nil and the heal faults --
    the same "extra dereference the vanilla path never made" family as the
    combat heal executor fixed earlier today. Vanilla's own lifesteal block
    (0x557667B8) heals through virtual +0x88/+0x8C only and never touches
    +0x4C, which is why this is mod-introduced.

THE FIX (cave rewritten in place, 62 B in the existing 64 B slot
0x5580E160-0x5580E1A0, so nothing else moves)
    Adds `mov eax,[edi+0x4C]; test eax,eax; je level1` ahead of the +0xB0 call.
    A nil unit reference now takes the level-1 default (the same value the
    cave already substitutes for legacy level-0 data) and the heal proceeds
    through the virtual, nil-safe accessors -- so behaviour is unchanged in
    every case that did not previously crash. Encoding trimmed with
    `push 0x76 / pop edx` to fit the original slot.

Usage: --apply | --revert | --status   Backup: AoWEPACK.dll.bak_lsnilguard
"""
import os, shutil, struct, sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DLL = os.path.join(GAME, "AoWEPACK.dll")
BAK = DLL + ".bak_lsnilguard"

VA2FILE = 0x55700C00
CAVE, CAVE_END = 0x5580E160, 0x5580E1A0          # cave_lsround slot (64 B)
RESUME = 0x557667CF                              # stock path after the block

OLD = bytes.fromhex(
    "f6431808"          # test byte [ebx+18],8
    "742e"              # je  done
    "ba76000000"        # mov edx,0x76
    "8bc7"              # mov eax,edi
    "8b08"              # mov ecx,[eax]
    "ff91b0000000"      # call [ecx+B0]      <-- unguarded GetAbilityLevel
    "85c0"              # test eax,eax
    "7501"              # jne +1
    "40"                # inc eax
    "50"                # push eax
    "8bc7"              # mov eax,edi
    "8b10"              # mov edx,[eax]
    "ff9288000000"      # call [edx+88]      GetHitPoints
    "5a"                # pop edx
    "03c2"              # add eax,edx
    "8bd0"              # mov edx,eax
    "8bc7"              # mov eax,edi
    "8b08"              # mov ecx,[eax]
    "ff918c000000"      # call [ecx+8C]      SetHitPoints
)
OLD += b"\xe9" + struct.pack("<i", RESUME - (CAVE + len(OLD) + 5))   # done: jmp back


def build():
    b = bytearray()
    lab = {}
    fix8 = []

    def j8(op, name):
        b.extend((op, 0)); fix8.append((len(b) - 1, name))

    b += bytes.fromhex("f6431808")               # test byte [ebx+0x18],8
    j8(0x74, "done")                             # je done
    b += bytes.fromhex("8b474c")                 # mov eax,[edi+0x4C]   unit
    b += bytes.fromhex("85c0")                   # test eax,eax
    j8(0x74, "level1")                           # je level1  (eax already 0)
    b += bytes.fromhex("6a765a")                 # push 0x76; pop edx
    b += bytes.fromhex("8bc7")                   # mov eax,edi
    b += bytes.fromhex("8b08")                   # mov ecx,[eax]
    b += bytes.fromhex("ff91b0000000")           # call [ecx+0xB0]  GetAbilityLevel
    b += bytes.fromhex("85c0")                   # test eax,eax
    j8(0x75, "heal")                             # jne heal
    lab["level1"] = len(b)
    b += b"\x40"                                 # inc eax   (0 -> 1)
    lab["heal"] = len(b)
    b += b"\x50"                                 # push eax
    b += bytes.fromhex("8bc7")                   # mov eax,edi
    b += bytes.fromhex("8b10")                   # mov edx,[eax]
    b += bytes.fromhex("ff9288000000")           # call [edx+0x88]  GetHitPoints
    b += b"\x5a"                                 # pop edx
    b += bytes.fromhex("03c2")                   # add eax,edx
    b += bytes.fromhex("8bd0")                   # mov edx,eax
    b += bytes.fromhex("8bc7")                   # mov eax,edi
    b += bytes.fromhex("8b08")                   # mov ecx,[eax]
    b += bytes.fromhex("ff918c000000")           # call [ecx+0x8C]  SetHitPoints
    lab["done"] = len(b)
    b += b"\xe9" + struct.pack("<i", RESUME - (CAVE + len(b) + 5))

    for at, name in fix8:
        d = lab[name] - (at + 1)
        assert -128 <= d <= 127, (name, d)
        b[at] = d & 0xFF
    assert CAVE + len(b) <= CAVE_END, f"cave overflow: {len(b)} B"
    return bytes(b)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--status"
    d = bytearray(open(DLL, "rb").read())
    off = CAVE - VA2FILE
    new = build()
    cur = bytes(d[off:off + len(OLD)])

    if mode == "--status":
        if cur == OLD:
            print("nil guard NOT applied (stock cave_lsround present)")
        elif bytes(d[off:off + len(new)]) == new:
            print("nil guard APPLIED")
        else:
            print("UNEXPECTED cave contents:", cur[:16].hex())
        return 0

    if mode == "--apply":
        assert cur == OLD, "cave_lsround is not the expected build: " + cur[:24].hex()
        assert all(b == 0 for b in d[off + len(OLD):CAVE_END - VA2FILE]), \
            "tail of the cave slot is not free"
        if not os.path.exists(BAK):
            shutil.copy2(DLL, BAK)
            print("backup ->", os.path.basename(BAK))
        d[off:CAVE_END - VA2FILE] = new + bytes(CAVE_END - CAVE - len(new))
        open(DLL, "wb").write(d)
        print(f"APPLIED: lifesteal level lookup nil-guarded ({len(new)} B "
              f"in the {CAVE_END - CAVE} B slot @{CAVE:#x})")
        return 0

    if mode == "--revert":
        d[off:CAVE_END - VA2FILE] = OLD + bytes(CAVE_END - CAVE - len(OLD))
        open(DLL, "wb").write(d)
        print("reverted to the unguarded cave_lsround")
        return 0

    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
