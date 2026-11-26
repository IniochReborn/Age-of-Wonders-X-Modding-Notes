#!/usr/bin/env python3
r"""
Independent heroes with Spell Casting cast level-1 Cosmos spells in combat - v2 (AoWEPACK.dll + AoWTCPCK.dll, 2026-11-14).

v1 was WRONG and is reverted: it assumed independents = player 0.  Independents have owner byte -1 and NO player
object (TAbstractUnit.GetIndependentRelation 0x5577F4F4: `call GetOwner / test al,al / jl -> race relation`);
player 0 is the first real player (v1 gave THAT player the spells and 1000 mana).

Why independents cannot cast: every spell path fetches the owner's TPlayerMagicControl with
`TPlayers.GetPlayer(owner)` 0x557544D0 followed by `mov reg,[eax+0x54]`; for owner -1 GetPlayer returns nil.  The
tactical AI (TCAI.EvalBattle) additionally skips casters with owner <= 0 at three of its four spell blocks.

Patch:
  AoWEPACK  GetPlayer's nil exit 0x557544E6 (`xor eax,eax / ret / lea eax,[eax]`, 6 B) -> jmp cave 0x558E4200 'IHS2'.
            Index >= 0 but out of range -> nil as before.  Index < 0: nil as before UNLESS the caller's next
            instruction is `mov r32,[eax+0x54]` (8B 40|48|50|58|70|78 54), i.e. it would crash on nil anyway ->
            return a private stand-in block P with [P+0x54] = stand-in magic control Q:
                [Q+0x0C] = 0 (no free magic), [Q+0x10] = P, [Q+0x24] = mana, set to 100 on every fetch,
                [Q+0x30] = list {+4 items, +8 count} of every spell with sphere 0 (Cosmos) and tier 1.
            The block (0x400 B) comes from System.@GetMem once per process, its pointer lives in DATA slack
            0x558E9DF0; it is built only once the spell resources exist.  Nothing synced is written.
  AoWTCPCK  the three owner gates (`jle` @0x418755 / 0x418BA2 / 0x4195EB) are NOPed: owner 0 and owner -1 heroes are
            evaluated like everyone else (the fourth block never had the test).
Casting stays limited by the hero's casting points; the spell choice is the normal AI scoring.  Fast (auto) combat
uses the same list through the same GetPlayer call.

Dry-run default; --apply / --revert (surgical).  Backups .bak_indepspell2.
"""
import os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

SUF = ".bak_indepspell2"
EP, EP_D = game_file("AoWEPACK.dll"), 0x55700C00
TC, TC_D = game_file("AoWTCPCK.dll"), 0x400C00
CAVE, CAVE_END, MAGIC = 0x558E4200, 0x558E4400, b"IHS2"
CODE = CAVE + 4
SITE, SITE_OLD = 0x557544E6, bytes.fromhex("33c0c38d4000")
GETMEM, SPELLCOUNT, GETSPELL = 0x55701008, 0x55779AC0, 0x55779AC8
G_RES, SLOT = 0x558FA044, 0x558E9DF0
MANA, MAXIDS = 100, 120
GATES = (0x418755, 0x418BA2, 0x4195EB)
# v2.1: TCAI.EvalBattle's four spell loops stop at id 0x83 (vanilla spell count) although the spell-type table and
# its `bound` limits were relocated to 512 entries -> no spell id >= 131 (every AoWx spell, e.g. Magic Missile 228)
# is ever considered by the tactical AI, for ANY player.  The four `cmp [ebp-x], 0x83` limits become 0x200.
LOOPS = (0x4188D4, 0x418C9B, 0x419076, 0x4196F4)
GATE_OLD = {0x418755: bytes.fromhex("0f8e76010000"), 0x418BA2: bytes.fromhex("0f8ef0000000"),
            0x4195EB: bytes.fromhex("0f8e8b010000")}


def cave_code():
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    src = f"""
        test edx, edx
        jns nil
        mov ecx, dword ptr [esp]
        cmp byte ptr [ecx], 0x8b
        jne nil
        cmp byte ptr [ecx + 2], 0x54
        jne nil
        mov cl, byte ptr [ecx + 1]
        and cl, 0xc7
        cmp cl, 0x40
        je fake
    nil:
        xor eax, eax
        ret
    fake:
        push ebx
        push edx
        call n
    n:
        pop ebx
        sub ebx, n
        mov eax, dword ptr [ebx + {SLOT:#x}]
        test eax, eax
        jnz have
        mov eax, dword ptr [ebx + {G_RES:#x}]
        test eax, eax
        jz out
        cmp dword ptr [eax + 0x84], 0
        jz out0
        mov eax, 0x400
        call {GETMEM:#x}
        test eax, eax
        jz out
        push esi
        push edi
        push ebp
        mov ebp, eax
        mov edi, eax
        mov ecx, 0x100
        xor eax, eax
        rep stosd
        lea eax, [ebp + 0x100]
        mov dword ptr [ebp + 0x54], eax
        mov dword ptr [eax + 0x10], ebp
        lea ecx, [ebp + 0x200]
        mov dword ptr [eax + 0x30], ecx
        lea eax, [ebp + 0x210]
        mov dword ptr [ecx + 4], eax
        mov esi, dword ptr [ebx + {G_RES:#x}]
        mov esi, dword ptr [esi + 0x84]
        mov eax, esi
        call {SPELLCOUNT:#x}
        mov edi, eax
    lp:
        dec edi
        js done
        mov eax, esi
        mov edx, edi
        call {GETSPELL:#x}
        test eax, eax
        jz lp
        cmp word ptr [eax + 0x20], 0x100
        jne lp
        mov ecx, dword ptr [ebp + 0x208]
        cmp ecx, {MAXIDS}
        jae done
        mov dword ptr [ebp + ecx*4 + 0x210], edi
        inc dword ptr [ebp + 0x208]
        mov dword ptr [ebp + 0x20c], {MAXIDS}
        jmp lp
    done:
        mov eax, ebp
        mov dword ptr [ebx + {SLOT:#x}], eax
        pop ebp
        pop edi
        pop esi
    have:
        mov dword ptr [eax + 0x124], {MANA}
    out:
        pop edx
        pop ebx
        ret
    out0:
        xor eax, eax
        jmp out
    """
    enc, _ = Ks(KS_ARCH_X86, KS_MODE_32).asm(src, CODE)
    return bytes(enc)


def jmp(frm, to):
    return b"\xE9" + struct.pack("<i", to - frm - 5)


def main():
    apply, revert = "--apply" in sys.argv, "--revert" in sys.argv
    ep, tc = bytearray(open(EP, "rb").read()), bytearray(open(TC, "rb").read())
    blob = MAGIC + cave_code()
    assert len(blob) <= CAVE_END - CAVE, hex(len(blob))
    o_c, o_s = CAVE - EP_D, SITE - EP_D
    new_site = jmp(SITE, CODE) + b"\x90"
    site, cave = bytes(ep[o_s:o_s + 6]), bytes(ep[o_c:o_c + (CAVE_END - CAVE)])
    gates = {g: bytes(tc[g - TC_D:g - TC_D + 6]) for g in GATES}
    loops = [struct.unpack_from("<I", tc, a - TC_D + 3)[0] for a in LOOPS]
    assert all(tc[a - TC_D] == 0x81 and tc[a - TC_D + 1] == 0x7D for a in LOOPS)
    base = site == new_site and cave.startswith(blob) and all(v == b"\x90" * 6 for v in gates.values())
    applied = base and all(v == 0x200 for v in loops)
    clean = (site == SITE_OLD and not any(cave) and all(gates[g] == GATE_OLD[g] for g in GATES)
             and all(v == 0x83 for v in loops))
    if base and not applied and apply:                      # v2 -> v2.1 upgrade in place
        for a in LOOPS:
            struct.pack_into("<I", tc, a - TC_D + 3, 0x200)
        open(TC, "wb").write(tc); print("upgraded v2 -> v2.1 (spell loops 0x83 -> 0x200)"); return 0
    print("cave %#x: %d B | state: %s" % (CAVE, len(blob), "APPLIED" if applied else "clean" if clean else "UNKNOWN"))
    if revert:
        if not applied:
            print("not applied"); return 1
        ep[o_s:o_s + 6] = SITE_OLD; ep[o_c:o_c + (CAVE_END - CAVE)] = bytes(CAVE_END - CAVE)
        for g in GATES:
            tc[g - TC_D:g - TC_D + 6] = GATE_OLD[g]
        for a in LOOPS:
            struct.pack_into("<I", tc, a - TC_D + 3, 0x83)
        open(EP, "wb").write(ep); open(TC, "wb").write(tc); print("reverted"); return 0
    if applied:
        print("ALREADY PATCHED"); return 0
    if not clean:
        print("ABORT: unexpected bytes (site %s, gates %s)" % (site.hex(), [v.hex() for v in gates.values()])); return 1
    if not apply:
        print("Dry run OK - rerun with --apply"); return 0
    for f in (EP, TC):
        b = bak_path(f, SUF)
        if not os.path.exists(b):
            shutil.copy2(f, b); print("backup ->", b)
    ep[o_c:o_c + len(blob)] = blob
    ep[o_s:o_s + 6] = new_site
    for g in GATES:
        tc[g - TC_D:g - TC_D + 6] = b"\x90" * 6
    for a in LOOPS:
        struct.pack_into("<I", tc, a - TC_D + 3, 0x200)
    open(EP, "wb").write(ep); open(TC, "wb").write(tc)
    print("applied")
    return 0


if __name__ == "__main__":
    sys.exit(main())
