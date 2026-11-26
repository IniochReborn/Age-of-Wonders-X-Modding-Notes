"""
SCALD (spell 405, Fire/Water tier 2) - damage modifiers (2026-10-14).  AoWEPACK.dll only.

Spec (user): 8 ATK / 4 DMG physical, single target, long range, bypasses obstructions; +50 % damage against units with
COLD WEAKNESS, -50 % damage against MACHINES.  The spell itself is a TVaporize clone (class 7 direct, no projectile path
-> obstructions are no shelter) made by patch_dual_sphere_spells_v1.py; this script only scales its damage.

RE (live AoWEPACK.dll):
  TVaporize (cell 0x557F5A5C, VMT 0x557F5A9C, id 0x79 = 121, pfs key 131) shares TCombatSpell.CreateCA 0x557F72C0 with
  Great Hail: it creates the CA, writes [ca+0x18] = spell id, pushes ATK [spell+0x34], DMG [spell+0x35] (through the Repent
  cave 0x55862600/0x55862663), types word [spell+0x36], byte [spell+0x3C] and calls TCombatSpellCA.Setup 0x55729C98
  (ebx = CA, esi = target TCombatUnit), which at 0x55729CBE..0x55729CC5 loads `movsx ecx,[ebp+0x10]` (DMG = number of
  damage dice) and `movsx edx,[ebp+0x14]` (ATK) for target VMT+0x114 = TCombatUnit StrikeDmg2 0x55726A6C
  (roll 0x55725EAC(eax = dice, edx = ATK - DEF), then the weakness/protection cave 0x5580FB80) -> byte [ca+0x10].
  Machines: strategic TUnit ([cu+0x4C]) VMT+0x114 GetUnitType (TUnit.GetUnitType 0x55782808 = [[eax+0x40]+0x30]) == 2.
  Cold Weakness: a MOD ability (weakness-abilities, registered at runtime into gap ids); its id is WEAK_IDS[1] = dword BSS
  0x558FA814 (WEAK_IDS 0x558FA810, index = damage-bit index: Fire 0, Cold 1, ...; 0 = not registered); the combat unit's
  HasAbility is VMT+0xA8 (edx = id) - the same test cave_weakmask 0x5580FA00 uses.  (The weakness cave only boosts COLD
  damage; Scald is physical, so this +50 % is separate and never double-counts.)
Patch: SITE 0x55729CBE (8 B `movsx ecx,[ebp+0x10] / movsx edx,[ebp+0x14]`, no relocs, hooked by no other script) ->
  `call cave` + 3 nop.  cave: replay both loads; for [ebx+0x18] == 405: machine -> dice = (dice+1)>>1 (4 -> 2); else
  Cold Weakness -> dice += dice>>1 (4 -> 6).  Scaling the DICE (not the rolled result) keeps it deterministic and MP-safe.
  Registers: ecx/edx are the outputs, eax is free (reloaded right after), ebx/esi/edi preserved by every callee.
Zone 0x5585E000..0x5585F000 (zero, reloc-free).  PIC via call/pop delta for WEAK_IDS (AoWEPACK rebases).
Dry-run default; --apply / --revert / --dis.  Backup <game>\\backup\\AoWEPACK.dll.bak_scald.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DLL = game_file("AoWEPACK.dll")
BASE, CODE_V2F = 0x55700000, 0x55700C00
SITE, ORIG = 0x55729CBE, bytes.fromhex("0fbe4d100fbe5514")
ZONE, ZONE_END = 0x5585E000, 0x5585F000
SPELL_ID = 405
WEAK_COLD = 0x558FA814            # WEAK_IDS[1] (dword) - the runtime id of Cold Weakness
UNIT_MACHINE = 2

ks = Ks(KS_ARCH_X86, KS_MODE_32)


def build(va):
    src = """
        movsx ecx, byte ptr [ebp+0x10]
        movsx edx, byte ptr [ebp+0x14]
        cmp dword ptr [ebx+0x18], %(id)d
        jne done
        push edx
        push ecx
        mov eax, [esi+0x4c]
        test eax, eax
        jz notmach
        mov edx, [eax]
        call dword ptr [edx+0x114]
        cmp al, %(mach)d
        jne notmach
        pop ecx
        inc ecx
        shr ecx, 1
        pop edx
        ret
    notmach:
        .byte 0xe8, 0, 0, 0, 0
        pop eax
        sub eax, 0x7fffffff
        mov edx, [eax+%(cold)#x]
        test edx, edx
        jz plain
        mov eax, esi
        mov ecx, [eax]
        call dword ptr [ecx+0xa8]
        test al, al
        jz plain
        pop ecx
        mov eax, ecx
        shr eax, 1
        add ecx, eax
        pop edx
        ret
    plain:
        pop ecx
        pop edx
    done:
        ret
    """ % {"id": SPELL_ID, "mach": UNIT_MACHINE, "cold": WEAK_COLD}
    b = bytearray(ks.asm(src, va)[0])
    anchor = bytes.fromhex("e800000000582dffffff7f"); k = b.find(anchor); assert k >= 0, "delta anchor"
    struct.pack_into("<I", b, k + 7, va + k + 5)
    return bytes(b)


def relocs(d):
    pe = struct.unpack_from("<I", d, 0x3C)[0]; opt = struct.unpack_from("<H", d, pe + 20)[0]; nsec = struct.unpack_from("<H", d, pe + 6)[0]
    secs = [struct.unpack_from("<IIII", d, pe + 24 + opt + 40 * k + 8) for k in range(nsec)]
    rrva, rsz = struct.unpack_from("<II", d, pe + 24 + 0x88)
    def r2f(rva):
        for vs, va, rs, ro in secs:
            if va <= rva < va + max(vs, rs): return ro + rva - va
    p = r2f(rrva); end = p + rsz; out = set()
    while p < end:
        page, size = struct.unpack_from("<II", d, p)
        if size < 8: break
        for q in range(p + 8, p + size, 2):
            e = struct.unpack_from("<H", d, q)[0]
            if e >> 12 == 3: out.add(BASE + page + (e & 0xFFF))
        p += size
    return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true"); ap.add_argument("--dis", action="store_true"); a = ap.parse_args()
    d = bytearray(open(DLL, "rb").read())
    cave = build(ZONE); assert ZONE + len(cave) <= ZONE_END
    hook = b"\xe8" + struct.pack("<i", ZONE - (SITE + 5)) + b"\x90" * 3
    live = bytes(d[SITE - CODE_V2F:SITE - CODE_V2F + 8]); zl = bytes(d[ZONE - CODE_V2F:ZONE_END - CODE_V2F])
    state = "vanilla" if live == ORIG else "ours" if live == hook else "OTHER"
    zstate = "zero" if not any(zl) else "ours" if zl[:len(cave)] == cave and not any(zl[len(cave):]) else "DIFFERS"
    bad = [hex(r) for r in relocs(bytes(d)) if ZONE <= r < ZONE_END or SITE <= r < SITE + 8]
    print("site %s | zone %s (%d B) | relocs %s" % (state, zstate, len(cave), bad or "none"))
    if a.dis:
        import capstone
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(cave, ZONE): print("   %08X  %-18s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad or state == "OTHER": print("ABORT"); return 1
    if a.revert:
        d[SITE - CODE_V2F:SITE - CODE_V2F + 8] = ORIG; d[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
        with open(DLL, "r+b") as f: f.write(bytes(d))
        print("reverted"); return 0
    if state == "ours" and zstate == "ours": print("already applied"); return 0
    if zstate == "DIFFERS" and state != "ours": print("ABORT (zone not free)"); return 1
    d[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE); d[ZONE - CODE_V2F:ZONE - CODE_V2F + len(cave)] = cave
    d[SITE - CODE_V2F:SITE - CODE_V2F + 8] = hook
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(DLL, ".bak_scald")
    if not os.path.exists(bak): shutil.copy2(DLL, bak); print("backup ->", bak)
    with open(DLL, "r+b") as f: f.write(bytes(d))
    assert open(DLL, "rb").read() == bytes(d); print("Written and verified"); return 0


if __name__ == "__main__":
    sys.exit(main())
