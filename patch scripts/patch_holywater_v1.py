#!/usr/bin/env python3
r"""
HOLY WATER (spell 324, Life/Water sphere pair 12, tier 1) - 2026-10-15.
Combat spell, short range, BREATH-style cone; ATK 7 / DMG 3 Holy; undead it hits are TURNED (vanilla Turn Undead).

HOW THE CONE WORKS (no TCPCK patch needed):
  * Spells and abilities share one combat-class space: [te+0x24] = SpellTypes[spell id] for a spell ([te+0x14] == 0x34)
    or the ability category table for an ability (TCAbRangedTE setup 0x40B3E8..0x40B423).  Class 5 = BREATH:
    strike count [te+0x28] := 0x14 (0x40B520), NextStrike case 0x40D345 = the 12-hex fan toward the target (BreathHN /
    BreathDir / BreathHit; patch_breath_line_v1's per-strike block line applies too), landings past strike 12 = sweep.
  * Vanilla already ships two class-5 SPELLS: 0x6C TColdBreath (Air T2 "cone of frigid air", ctor 0x557F8758:
    ATK 8 DMG 4 Cold 0x2 1 shot range 4; cell 0x557F4BD8, site 0x557FA653; Spells.pfs key 118) and 0x72 TFireBreath
    (Fire T2, ctor 0x557F8DA0, same + fast-combat 3; cell 0x557F52E4, site 0x557FA6C6; key 124).  Both override ONLY the
    ctor: CreateCA etc. are TCombatSpell's, so a TColdBreath clone with SpellTypes byte 5 is a working breath spell.
  * An empty damage hex sends msg 0x31013 (spell id) at 0x40C871; a unit there takes it in its MapFieldMsgProc
    (0x421177): spell.CreateCA(attacker, this unit) via the registry -> generic by id.  No TCPCK id switch singles out
    0x6C/0x72 (0x40F0E3 / 0x40B541 / 0x40C8D0 / preview 0x42827A all take the same default case as a raw id 324)
    -> NO alias entry.

TURN UNDEAD (vanilla, spell 0x65 TTurnUndead, cell 0x557F4288, ctor 0x557F7B94: ATK 9 DMG 2 Holy, +0x3C=1, range 4):
  * TTurnUndead.CreateCA 0x557F7C50 builds a TTurnUndeadSpellCA ([0x557F4190], VMT 0x557F41D0, same 0x20 size, parent
    TCombatSpellCA; differs ONLY in ClassID 0x202CC and Execute VMT+0x50) and rolls damage only when the target is a
    TCombatUnit ([0x55715A54]) whose unit has VMT+0x114 < 2 and (race VMT+0xA4 == 0xB Undead or HasAbility 0x81).
  * TTurnUndeadSpellCA.Execute 0x557F7B1C = TCombatSpellCA.Execute 0x557F6A20, then if the hit landed ([ca+0x10]) and
    the target lives ([cu+0x47] bit 0 clear): ability registry.GetAbility(0x22 "Turned: cannot perform actions")
    .VMT+0xD0(target unit) + its data [+0xF] := attacker [+0x45] (the turn stamp).  = "inflicts Turn Undead".

THE PATCH (AoWEPACK only; zone 0x55826000..0x55828000, PIC call/pop delta - AoWEPACK rebases):
  cls  0x557F72D7 in TCombatSpell.CreateCA 0x557F72C0 (`call 0x557298B4` = TObject.Create of the CA class in eax,
       5 B rel32, no reloc; eax = [0x557F3C88] TCombatSpellCA, ebx = spell, edi = target, ecx 0 / dl 1):
       -> call cave: spell id [ebx+0x10] == 324 and the target passes the vanilla Turn Undead test above
       -> eax := TTurnUndeadSpellCA; always re-zero ecx / dl := 1 and tail-jump the ctor.
  Holy Water rolls its OWN damage on everyone (TCombatSpellCA.Setup with the spell's 7/3/0x40 - unchanged path, all
  later CreateCA hooks run as before); undead get the TU subclass, whose Execute adds Turned after the hit.  Nothing
  stored, no RNG -> deterministic / MP-safe; replays re-create the vanilla class id 0x202CC.
Dry-run default; --apply / --revert / --dis.  Backup .bak_holywater (first apply only).
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

EP = game_file("AoWEPACK.dll")
EP_BASE, EP_V2F = 0x55700000, 0x55700C00
EZ, EZ_END = 0x55826000, 0x55828000
SPELL_ID = 324
OBJ_CREATE = 0x557298B4                     # TObject.Create (class in eax, dl alloc flag)
INHERITS = 0x557010C0                       # TObject.InheritsFrom (eax obj, edx class) -> al
CU_CLASSREF = 0x55715A54                    # [ ] = TCombatUnit-family class tested by TTurnUndead.CreateCA
TUCA_CLASSREF = 0x557F4190                  # [ ] = TTurnUndeadSpellCA
UNDEAD_RACE, UNDEAD_ABIL = 0x0B, 0x81
EP_SITES = [("cls", 0x557F72D7, bytes.fromhex("e8d825f3ff"), "call", "cls")]

ks = Ks(KS_ARCH_X86, KS_MODE_32)
ANCHOR = bytes.fromhex("e8000000005e81eeffffff7f")      # call $D / pop esi / sub esi, $D


def asm_pic(src, va):
    s1 = src.replace("call $D", ".byte 0xe8, 0, 0, 0, 0").replace("sub esi, $D", "sub esi, 0x7fffffff")
    b = bytearray(ks.asm(s1, va)[0]); k = 0; n = 0
    while True:
        k = b.find(ANCHOR, k)
        if k < 0: break
        struct.pack_into("<I", b, k + 8, va + k + 5); k += len(ANCHOR); n += 1
    assert n == src.count("call $D"), "delta anchors %d of %d" % (n, src.count("call $D"))
    return bytes(b)


def build_ep():
    where = {"cls": EZ}
    blob = asm_pic("""
        cmp dword ptr [ebx + 0x10], %(id)d
        jne go
        test edi, edi
        je go
        push eax
        push esi
        call $D
        pop esi
        sub esi, $D
        mov eax, edi
        mov edx, dword ptr [esi + %(cu)#x]
        call %(inh)#x
        test al, al
        je no
        mov eax, dword ptr [edi + 0x4c]
        test eax, eax
        je no
        mov edx, dword ptr [eax]
        call dword ptr [edx + 0x114]
        cmp al, 2
        jae no
        mov eax, dword ptr [edi + 0x4c]
        mov edx, dword ptr [eax]
        call dword ptr [edx + 0xa4]
        cmp al, %(race)d
        je yes
        mov eax, dword ptr [edi + 0x4c]
        mov edx, %(abil)d
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x148]
        test al, al
        je no
    yes:
        mov eax, dword ptr [esi + %(tu)#x]
        pop esi
        add esp, 4
        jmp go
    no:
        pop esi
        pop eax
    go:
        xor ecx, ecx
        mov dl, 1
        jmp %(ctor)#x
    """ % {"id": SPELL_ID, "cu": CU_CLASSREF, "inh": INHERITS, "race": UNDEAD_RACE, "abil": UNDEAD_ABIL,
           "tu": TUCA_CLASSREF, "ctor": OBJ_CREATE}, EZ)
    return blob, where


def reloc_set(d, base):
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, pe + 6)[0]; opt = struct.unpack_from("<H", d, pe + 20)[0]
    secs = [struct.unpack_from("<IIII", d, pe + 24 + opt + 40 * i + 8) for i in range(nsec)]
    def r2f(rva):
        for vs, va, rs, ro in secs:
            if va <= rva < va + max(vs, rs): return ro + rva - va
    rrva, rsz = struct.unpack_from("<II", d, pe + 24 + 0x88)
    out = set()
    if not rrva: return out
    p = r2f(rrva); end = p + rsz
    while p < end:
        page, size = struct.unpack_from("<II", d, p)
        if size < 8: break
        for q in range(p + 8, p + size, 2):
            e = struct.unpack_from("<H", d, q)[0]
            if e >> 12 == 3: out.add(base + page + (e & 0xFFF))
        p += size
    return out


def site_states(d, v2f, sites, where, zone, zend):
    st, patched = {}, {}
    for name, va, orig, kind, cave in sites:
        op = b"\xe8" if kind == "call" else b"\xe9"
        new = op + struct.pack("<i", where[cave] - (va + 5)) + b"\x90" * (len(orig) - 5); patched[name] = (va, orig, new)
        live = bytes(d[va - v2f:va - v2f + len(orig)])
        if live == orig: st[name] = "vanilla"
        elif live == new: st[name] = "ours"
        elif live[0] in (0xE8, 0xE9) and zone <= va + 5 + struct.unpack_from("<i", live, 1)[0] < zend: st[name] = "ours(old)"
        else: st[name] = "OTHER"
    return st, patched


def sanity(d):
    rd = lambda va: struct.unpack_from("<I", d, va - EP_V2F)[0]
    vt = rd(TUCA_CLASSREF)
    assert rd(vt + 0x50) == 0x557F7B1C, "TTurnUndeadSpellCA.Execute moved: %#x" % rd(vt + 0x50)
    assert rd(0x557F3C88) == 0x557F3CC8 and rd(vt - 0x1C) == rd(0x557F3CC8 - 0x1C), "CA class/size mismatch"
    assert d[0x557F72D2 - EP_V2F:0x557F72D7 - EP_V2F] == bytes.fromhex("a1883c7f55"), "CreateCA class load moved"


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true"); ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    ed = bytearray(open(EP, "rb").read())
    sanity(ed)
    eblob, ewhere = build_ep()
    assert EZ + len(eblob) <= EZ_END
    est, epatch = site_states(ed, EP_V2F, EP_SITES, ewhere, EZ, EZ_END)
    zl = bytes(ed[EZ - EP_V2F:EZ_END - EP_V2F])
    ez = "zero" if not any(zl) else "ours" if zl[:len(eblob)] == eblob and not any(zl[len(eblob):]) else "DIFFERS"
    erl = reloc_set(bytes(ed), EP_BASE)
    ebad = [hex(r) for r in erl if EZ - 3 <= r < EZ_END or any(va - 3 <= r < va + len(o) for _n, va, o, _k, _c in EP_SITES)]
    print("AoWEPACK: sites %s | zone %s (%d B: cls=%#x) | relocs %s" % (est, ez, len(eblob), ewhere["cls"], ebad or "none"))
    if a.dis:
        import capstone
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(eblob, EZ):
            print("   %08X  %-18s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if ebad or "OTHER" in est.values(): print("ABORT (relocs or a foreign hook)"); return 1
    if ez == "DIFFERS" and not any(s.startswith("ours") for s in est.values()): print("ABORT (zone not free)"); return 1
    eo = bytearray(ed)
    if a.revert:
        for va, orig, _n in epatch.values(): eo[va - EP_V2F:va - EP_V2F + len(orig)] = orig
        eo[EZ - EP_V2F:EZ_END - EP_V2F] = bytes(EZ_END - EZ)
    else:
        eo[EZ - EP_V2F:EZ_END - EP_V2F] = bytes(EZ_END - EZ); eo[EZ - EP_V2F:EZ - EP_V2F + len(eblob)] = eblob
        for va, _o, new in epatch.values(): eo[va - EP_V2F:va - EP_V2F + len(new)] = new
    if eo == ed: print("already applied" if not a.revert else "already reverted"); return 0
    if not (a.apply or a.revert): print("%d bytes change\nDry run OK - rerun with --apply (or --revert)." % sum(1 for x, y in zip(ed, eo) if x != y)); return 0
    bak = bak_path(EP, ".bak_holywater")
    if not os.path.exists(bak): shutil.copy2(EP, bak); print("backup ->", bak)
    with open(EP, "r+b") as f: f.write(bytes(eo))
    assert open(EP, "rb").read() == bytes(eo); print("AoWEPACK.dll: %s and verified" % ("reverted" if a.revert else "written"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
