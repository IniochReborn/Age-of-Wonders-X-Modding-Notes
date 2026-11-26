"""
SOUL SIPHON (spell 340, Water/Death tier 1) - heal the caster by the damage inflicted (2026-10-15).  AoWEPACK.dll only.

Spec (user): combat spell, medium range, research 50, cost 3, 8 ATK / 4 DMG Death damage, heals the caster equal to the
damage inflicted.  The spell itself is a TDeathRay clone (id 0x67, class 7 direct, no projectile path) made by
patch_dual_sphere_spells_v1.py (pokes ATK 8 / DMG 4 / types 0x20 Death / range 8); this script adds the heal.

RE (vanilla AoW 1.36 AoWEPACK.dpl = live layout, base 0x55700000):
  TDeathRay VMT 0x557F46E0, CreateCA (VMT+0x78) = TCombatSpell.CreateCA 0x557F72C0: CA class = [0x557F3C88] (the
  TCombatSpellCA classref, relocated), [ca+0x18] := spell id, Setup rolls the damage into byte [ca+0x10].
  Execute = TCombatSpellCA VMT+0x50 0x557F6A20 -> TDamageCA.Execute 0x55729D14 (ebx = CA, esi = context):
    edi = caster CU  = GetObjectByID 0x55728C68([ctx+0xC], byte [ca+0xD])
    esi = target CU  = GetObjectByID(..., byte [ca+0xE])
    if [ca+0x10]: 0x55729D4A  call [caster VMT+0x108] (eax caster, edx target, ecx dmg) = TCombatUnit 0x55726B1C, which
                  returns target VMT+0x124 TakeDamage 0x55726C58 = min(dmg, target HP) - the damage ACTUALLY dealt -
                  0x55729D50  mov [ebx+0x15],al   (stored in the CA; serialized)
  Combat unit (TCombatUnit, classref [0x55715A54]): VMT+0x88 = HP (signed byte), VMT+0x8C = SetHP (dl; forwards to the
  strategic unit's clamped SetHitPoints - the path elemental-feeding's combat heal uses, valid for TFastCombatUnit live
  and TTacticalCombatUnit in replay), [cu+0x47] bit 0 = dead, [cu+0x4C] = strategic TUnit (VMT+0xD0 = max HP, as the
  vanilla HealUnit 0x5576C374 reads it).

Patch: SITE 0x55729D4A (9 B `call [edi+0x108] / mov [ebx+0x15],al`, reloc-free, hooked by no other script) ->
  `call cave` + 4 nop.  cave: replay both (eax caster kept on the stack); then, only when the CA IS a TCombatSpellCA
  ([ca] == [classref 0x557F3C88]; plain TDamageCA unit attacks are smaller objects and never read past their end) and
  [ca+0x18] == 340 and the dealt damage > 0 and the caster is a live TCombatUnit with a strategic unit:
  HP := min(HP + dealt, max HP) via CU VMT+0x8C.  Runs inside CA execution, which every peer performs on the same
  recorded CA -> deterministic and MP-safe; no RNG.  No heal popup (the vanilla combat damage path shows the target's
  number only).  Callee-saved registers preserved (esi/edi pushed); eax/ecx/edx are dead after the site (eax is
  reloaded at 0x55729D53).
Zone 0x55830000..0x55832000 (verified zero).  PIC via call/pop delta for the two classref reads (AoWEPACK rebases);
the call to TObject.InheritsFrom 0x557010C0 is rel32.
Dry-run default; --apply / --revert / --dis.  Backup <game>\\backup\\AoWEPACK.dll.bak_soulsiphon.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DLL = game_file("AoWEPACK.dll")
BASE, CODE_V2F = 0x55700000, 0x55700C00
SITE, ORIG = 0x55729D4A, bytes.fromhex("ff9708010000884315")
ZONE, ZONE_END = 0x55830000, 0x55832000
SPELL_ID = 340
CA_CLASSREF = 0x557F3C88          # [ ] = TCombatSpellCA class (VMT ptr), as TCombatSpell.CreateCA loads it
CU_CLASSREF = 0x55715A54          # [ ] = TCombatUnit class
INHERITS = 0x557010C0             # TObject.InheritsFrom (eax obj, edx class) -> al

ks = Ks(KS_ARCH_X86, KS_MODE_32)


def build(va):
    src = """
        push eax
        call dword ptr [edi+0x108]
        mov byte ptr [ebx+0x15], al
        pop edx
        test al, al
        jz out
        push esi
        push edi
        movzx edi, al
        mov esi, edx
        .byte 0xe8, 0, 0, 0, 0
        pop ecx
        sub ecx, 0x7fffffff
        mov eax, dword ptr [ebx]
        cmp eax, dword ptr [ecx+%(car)#x]
        jne done
        cmp dword ptr [ebx+0x18], %(id)d
        jne done
        test esi, esi
        jz done
        mov eax, esi
        mov edx, dword ptr [ecx+%(cur)#x]
        call %(inh)#x
        test al, al
        jz done
        test byte ptr [esi+0x47], 1
        jnz done
        mov eax, dword ptr [esi+0x4c]
        test eax, eax
        jz done
        mov edx, dword ptr [eax]
        call dword ptr [edx+0xd0]
        movzx eax, al
        push eax
        mov eax, esi
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x88]
        movsx eax, al
        pop ecx
        test eax, eax
        jle done
        add eax, edi
        cmp eax, ecx
        jle setp
        mov eax, ecx
    setp:
        mov edx, eax
        mov eax, esi
        mov ecx, dword ptr [eax]
        call dword ptr [ecx+0x8c]
    done:
        pop edi
        pop esi
    out:
        ret
    """ % {"id": SPELL_ID, "car": CA_CLASSREF, "cur": CU_CLASSREF, "inh": INHERITS}
    b = bytearray(ks.asm(src, va)[0])
    anchor = bytes.fromhex("e80000000059" "81e9ffffff7f"); k = b.find(anchor); assert k >= 0, "delta anchor"
    struct.pack_into("<I", b, k + 8, va + k + 5)
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
    hook = b"\xe8" + struct.pack("<i", ZONE - (SITE + 5)) + b"\x90" * 4
    live = bytes(d[SITE - CODE_V2F:SITE - CODE_V2F + 9]); zl = bytes(d[ZONE - CODE_V2F:ZONE_END - CODE_V2F])
    state = "vanilla" if live == ORIG else "ours" if live == hook else "OTHER"
    zstate = "zero" if not any(zl) else "ours" if zl[:len(cave)] == cave and not any(zl[len(cave):]) else "DIFFERS"
    bad = [hex(r) for r in relocs(bytes(d)) if ZONE <= r < ZONE_END or SITE <= r < SITE + 9]
    # sanity: the classref holders still hold in-image class pointers (CreateCA's load + the CU family classref)
    for va in (CA_CLASSREF, CU_CLASSREF):
        v = struct.unpack_from("<I", d, va - CODE_V2F)[0]; assert BASE <= v < BASE + 0x400000, (hex(va), hex(v))
    print("site %s | zone %s (%d B @%#x) | relocs %s" % (state, zstate, len(cave), ZONE, bad or "none"))
    if a.dis:
        import capstone
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(cave, ZONE): print("   %08X  %-18s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad or state == "OTHER": print("ABORT"); return 1
    if a.revert:
        if state != "ours" and zstate == "zero": print("already vanilla"); return 0
        d[SITE - CODE_V2F:SITE - CODE_V2F + 9] = ORIG; d[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
        with open(DLL, "r+b") as f: f.write(bytes(d))
        print("reverted"); return 0
    if state == "ours" and zstate == "ours": print("already applied"); return 0
    if zstate == "DIFFERS" and state != "ours": print("ABORT (zone not free)"); return 1
    d[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE); d[ZONE - CODE_V2F:ZONE - CODE_V2F + len(cave)] = cave
    d[SITE - CODE_V2F:SITE - CODE_V2F + 9] = hook
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(DLL, ".bak_soulsiphon")
    if not os.path.exists(bak): shutil.copy2(DLL, bak); print("backup ->", bak)
    with open(DLL, "r+b") as f: f.write(bytes(d))
    assert open(DLL, "rb").read() == bytes(d); print("Written and verified"); return 0


if __name__ == "__main__":
    sys.exit(main())
