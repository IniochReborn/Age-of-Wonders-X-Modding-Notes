#!/usr/bin/env python3
r"""
AI hero/leader level-up: Marksmanship only when the hero already has a ranged attack (2026-09-14).

The AI chooser (THero.ExecuteUpgradeHeroAI @0x55787A24, expanded in July 2026 by heroai_build.py
into a 30-entry weighted pool; eligibility cave @0x5580FD40, apply cave @0x5580FE6C) admits a
table entry when `ability.CanTake(hero)` ([vmt+0xC4]) says yes.  Marksmanship (0x20) passes that
test for every hero, so the AI sometimes banks for / picks it with no ranged attack to improve.

This hooks the CanTake call inside the eligibility loop (0x5580FD7B, `call [ecx+0xC4]`, 6 B)
-> cave @0x55816100: runs CanTake as before; if it said yes AND the table entry being tested is
Marksmanship, the hero must additionally own at least one ability whose class descends from
AoWE.TRangedAttackAbility (Archery, the Bolts, Hurl Boulder, ...), checked through the hero's
merged GetAbilityEnabled ([vmt+0x148], items included) over every registered ability id.
Nothing else changes: weights, the other 29 entries, stats and the human level-up dialog are
untouched.  Position-independent (ebp holds the chooser's rebase delta, reused here).

Backup AoWEPACK.dll.bak_aimsgate.  Dry-run default; --apply; --revert.
"""
import argparse, os, shutil, struct, sys
from bakpath import game_dir, game_file   # game folder = AOW_GAME_DIR or parent of patch scripts (2026-09-20)

DEFAULT_GAME = game_dir()
BAK = ".bak_aimsgate"
from bakpath import bak_path   # backups live in <game>\backup\ (2026-09-17)
DLL_BASE = 0x55700000
HOOK, HOOK_ORIG = 0x5580FD7B, bytes.fromhex("ff91c4000000")     # call dword ptr [ecx+0xC4]  (CanTake)
CAVE, CAVE_END = 0x55816100, 0x55816180
ID_TABLE = 0x5580FDD5           # the chooser's 30-byte ability-id table (ebp-relative in the cave)
GETABILITY = 0x557501C0         # AoWE.TAbilityControl.GetAbility (eax=control, edx=id) -> ability|nil (nil past count)
ISCLASS = 0x557010C0            # System.@IsClass thunk (eax=obj, edx=class VMT) -> al
GMGR = 0x558FA044               # AoWE.AoWHSSet: [set+0x80] = TAbilityControl
VMT_RANGED = 0x5571E8D4         # AoWE..TRangedAttackAbility (the class VMT)
GETABILITYENABLED = 0x148       # THero/TLeader VMT slot: merged own|items|inventory
MARKSMANSHIP = 0x20
ID_SCAN_END = 0x100


def pe_secs(d):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    n = struct.unpack_from("<H", d, e + 6)[0]
    optsz = struct.unpack_from("<H", d, e + 20)[0]
    secs = []
    for i in range(n):
        s = d[e + 24 + optsz + 40 * i:][:40]
        vs, va, rs, ra = struct.unpack_from("<IIII", s, 8)
        secs.append((s[:8].rstrip(b"\0"), va, vs, ra, rs))
    return secs


def va2off(secs, va):
    r = va - DLL_BASE
    for _n, va0, vs, ra, rs in secs:
        if va0 <= r < va0 + max(vs, rs):
            return ra + (r - va0)
    raise ValueError(hex(va))


def reloc_targets(d, secs):
    out = set()
    for nm, va, vs, ra, rs in secs:
        if nm != b".reloc":
            continue
        p, end = ra, ra + vs
        while p + 8 <= end:
            page, size = struct.unpack_from("<II", d, p)
            if size < 8:
                break
            for q in range(p + 8, p + size, 2):
                v = struct.unpack_from("<H", d, q)[0]
                if v >> 12 == 3:
                    out.add(page + (v & 0xFFF))
            p += size
    return out


def assemble():
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    H = lambda v: "0x%X" % v  # noqa: E731
    src = "\n".join([
        # in: eax=ability, edx=hero, ecx=ability VMT; [esp+4]=pushed ability, [esp+8]=loop index; ebp=delta; ebx=hero
        "call dword ptr [ecx + 0xC4]",                       # the displaced CanTake
        "test al, al",
        "je   out",
        "mov  ecx, [esp + 0x8]",                             # table index of the entry being tested
        "lea  edx, [ebp + %s]" % H(ID_TABLE),
        "cmp  byte ptr [edx + ecx], %s" % H(MARKSMANSHIP),
        "jne  yes",
        "push esi",
        "push edi",
        "xor  esi, esi",
        "scan:",
        "inc  esi",
        "cmp  esi, %s" % H(ID_SCAN_END),
        "jae  none",
        "mov  eax, [ebp + %s]" % H(GMGR),
        "mov  eax, [eax + 0x80]",
        "mov  edx, esi",
        "call %s" % H(GETABILITY),
        "test eax, eax",
        "je   scan",
        "lea  edx, [ebp + %s]" % H(VMT_RANGED),
        "call %s" % H(ISCLASS),                              # ranged-attack class?
        "test al, al",
        "je   scan",
        "mov  eax, ebx",                                     # hero owns it (merged, items included)?
        "mov  edx, esi",
        "mov  ecx, [eax]",
        "call dword ptr [ecx + %s]" % H(GETABILITYENABLED),
        "test al, al",
        "je   scan",
        "pop  edi",
        "pop  esi",
        "yes:",
        "mov  al, 0x1",
        "ret",
        "none:",
        "pop  edi",
        "pop  esi",
        "xor  eax, eax",
        "out:",
        "ret",
    ])
    code = bytes(ks.asm(src, CAVE)[0])
    assert CAVE + len(code) <= CAVE_END
    return code


def main():
    ap = argparse.ArgumentParser(description="AI level-up: gate Marksmanship behind a ranged attack")
    ap.add_argument("--game", default=DEFAULT_GAME)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    dll = os.path.join(a.game, "AoWEPACK.dll")
    if a.revert:
        if not os.path.exists(bak_path(dll, BAK)):
            print("no backup"); return 1
        shutil.copyfile(bak_path(dll, BAK), dll); print("restored AoWEPACK.dll"); return 0

    d = bytearray(open(dll, "rb").read())
    secs = pe_secs(d)
    code = assemble()
    hook_new = b"\xE8" + struct.pack("<i", CAVE - (HOOK + 5)) + b"\x90"
    ho, co = va2off(secs, HOOK), va2off(secs, CAVE)
    cur_hook, cur_cave = bytes(d[ho:ho + 6]), bytes(d[co:co + len(code)])
    relocs = reloc_targets(d, secs)
    for va, ln in ((HOOK, 6), (CAVE, len(code))):
        assert not [r for r in relocs if va - DLL_BASE - 3 <= r < va - DLL_BASE + ln], "reloc inside %#x" % va
    # sanity: the chooser's id table still has Marksmanship where the cave expects it, and the class VMT name
    tbl = bytes(d[va2off(secs, ID_TABLE):va2off(secs, ID_TABLE) + 30])
    assert MARKSMANSHIP in tbl, "chooser id table not found at %#x" % ID_TABLE
    cn = struct.unpack_from("<I", d, va2off(secs, VMT_RANGED - 0x20))[0]
    o = va2off(secs, cn)
    assert d[o + 1:o + 1 + d[o]] == b"TRangedAttackAbility", "class VMT at %#x is not TRangedAttackAbility" % VMT_RANGED
    if a.dis:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
        for i in Cs(CS_ARCH_X86, CS_MODE_32).disasm(code, CAVE):
            print("  %08x  %-20s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if cur_hook == hook_new and cur_cave == code:
        print("ALL ALREADY PATCHED"); return 0
    assert cur_hook == HOOK_ORIG, "hook site reads %s" % cur_hook.hex()
    assert cur_cave == bytes(len(code)), "cave space at %#x is not free" % CAVE
    print("hook %#x -> cave %#x (%d B); Marksmanship index in table: %d" % (HOOK, CAVE, len(code), tbl.index(MARKSMANSHIP)))
    if not a.apply:
        print("\nDry run OK. Re-run with --apply to write."); return 0
    if not os.path.exists(bak_path(dll, BAK)):
        shutil.copyfile(dll, bak_path(dll, BAK)); print("backup: AoWEPACK.dll" + BAK)
    d[ho:ho + 6] = hook_new
    d[co:co + len(code)] = code
    with open(dll, "r+b") as f:
        f.seek(0); f.write(d)
    print("applied.  UNTESTED: watch AI heroes without a bow/bolts stop taking Marksmanship.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
