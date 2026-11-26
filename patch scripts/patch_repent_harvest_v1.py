#!/usr/bin/env python3
r"""
AoWEPACK.dll side of the two new tier-2 combat spells (2026-10-12): REPENT (206, Life) and HARVEST SOULS (207, Death).
Both are clones made by patch_dual_sphere_spells_v1.py; the TCPCK side is patch_tc_repent_harvest_v1.py.

REPENT (206) = TDeathRay clone (cell 0x557F46A0, Create 0x557F82B0: ATK 9 / DMG 3 / Death / 1 shot / range 0xC; the
pipeline pokes ATK 7, DMG 1, types 0x40 Holy).  Its damage depends on the TARGET:
    base by alignment (TCombatUnit.GetAlignment 0x55724FF4 = unit VMT+0xFC, TAlignment enum alPureGood 0, alGood 1,
    alPureNeutral 2, alNeutral 3, alEvil 4, alPureEvil 5): good 1, neutral 2, evil / pure neutral 3, pure evil 4;
    + medal: TUnit.GetRank 0x5578294C (0 none / 1 silver / 2 gold, flat XP 10/20) + 1 more when gold AND the
    Legendary gate (our cave 0x5580EF60: ebx = unit, CF clear = legendary) says so -> silver +1, gold +2, legendary +3.
  Hook: TCombatSpell.CreateCA pushes the spell's DMG byte for the damage CA @0x557F72E8 (`8A 43 35 50 66 8B 43 36`, 8 B;
  ebx = spell, edi = target TCombatUnit, esi = the new CA, [ebp-4] = caster) -> cave: for id 206 compute the byte from
  the target, else [spell+0x35]; then replay `push eax / mov ax,[ebx+0x36]` and resume @0x557F72F0.

HARVEST SOULS (207) = TAnimateDead clone (SpellTypes 0x27).  In TCPCK the corpse handler calls spell.CreateCA(caster,
corpse) for it (TCPCK patch) -> TAnimateDead.CreateCA 0x557FA4BC (shared VMT) -> this cave: for id 207 credit the
CASTER 5 CASTING POINTS and return NIL (the TCPCK side skips execution on nil and frees the corpse); any other id
replays the 6-B prologue (`55 8B EC 51 53 56`) and resumes @0x557FA4C2.
  v2 (2026-10-12 evening): v1 credited the player's mana POOL (TPlayerMagicControl.SetMana) - wrong resource, heroes
  cast combat spells from their own casting points.  Unit = [casterCU+0x4C]; TAbstractUnit virtuals (THero VMT
  0x55711FEC / TLeader 0x55712238, same slots): +0x128 GetCastingPointsMax (THero 0x55788614), +0x12C
  GetCastingPoints (THero 0x55788644 = byte [hero+0x80]; base 0x5577FDBC returns 0), +0x130 SetCastingPoints (THero
  0x5578864C: clamps to the max, stores the byte, calls VMT+0x90 = changed/refresh; base 0x5577FDC0 = no-op).  The
  cave does Set(min(Get+5, 127)) - a non-hero caster is a harmless no-op.

Caves @0x55862600 (PIC via call/pop delta).  Backup <game>\backup\AoWEPACK.dll.bak_repharv.  Dry run; --apply / --revert.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DEFAULT_DLL = game_file("AoWEPACK.dll")
BAK_SUFFIX = ".bak_repharv"
BASE, CODE_V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x55862600, 0x55862700
ID_REPENT, ID_HARVEST, HARVEST_CP = 206, 207, 5
GETALIGN, GETRANK, LEGEND_GATE = 0x55724FF4, 0x5578294C, 0x5580EF60
VMT_GETCP, VMT_SETCP = 0x12C, 0x130          # TAbstractUnit.GetCastingPoints / SetCastingPoints (virtual; THero overrides)
SITES = {
    "dmg":  (0x557F72E8, bytes.fromhex("8a433550668b4336"), 0x557F72F0),   # TCombatSpell.CreateCA DMG push
    "hcca": (0x557FA4BC, bytes.fromhex("558bec515356"), 0x557FA4C2),       # TAnimateDead.CreateCA prologue
}
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm_delta(src, va):
    if "$D" not in src: return bytes(ks.asm(src, va)[0])
    s1 = src.replace("call $D", ".byte 0xe8, 0, 0, 0, 0").replace("sub ebx, $D", "sub ebx, 0x7fffffff")
    b = bytearray(ks.asm(s1, va)[0]); anchor = b"\xe8\x00\x00\x00\x00\x5b\x81\xeb\xff\xff\xff\x7f"
    n, k = 0, b.find(anchor)
    while k >= 0:
        struct.pack_into("<I", b, k + 8, va + k + 5); n += 1; k = b.find(anchor, k + len(anchor))
    assert n == src.count("call $D") == src.count("sub ebx, $D")
    return bytes(b)


def build():
    out = bytearray(); where = {}
    def place(name, src):
        while len(out) % 16: out.append(0)
        va = ZONE + len(out); where[name] = va; out.extend(asm_delta(src, va))
    # Repent damage: ebx = spell, edi = target CU.  eax/ecx/edx are free here (esi = CA must survive).
    place("dmg", """
        cmp dword ptr [ebx+0x10], %(rep)d
        jne plain
        mov eax, edi
        call %(align)#x
        movzx eax, al
        mov dl, 1
        cmp eax, 3
        je n2
        cmp eax, 2
        je n3
        cmp eax, 4
        je n3
        cmp eax, 5
        jne medal
        mov dl, 4
        jmp medal
    n2:
        mov dl, 2
        jmp medal
    n3:
        mov dl, 3
    medal:
        mov eax, [edi+0x4c]
        test eax, eax
        jz done
        push edx
        call %(rank)#x
        pop edx
        add dl, al
        cmp al, 2
        jne done
        push ebx
        mov ebx, [edi+0x4c]
        push edx
        call %(legend)#x
        pop edx
        pop ebx
        jc done
        inc dl
    done:
        mov al, dl
        push eax
        mov ax, [ebx+0x36]
        jmp %(resume)#x
    plain:
        mov al, [ebx+0x35]
        push eax
        mov ax, [ebx+0x36]
        jmp %(resume)#x
    """ % {"rep": ID_REPENT, "align": GETALIGN, "rank": GETRANK, "legend": LEGEND_GATE, "resume": SITES["dmg"][2]})
    # Harvest: eax = spell, edx = caster CU, ecx = target (corpse) CU, [esp+4] hero flag; ret 4.
    place("hcca", """
        cmp dword ptr [eax+0x10], %(harv)d
        jne plain
        push esi
        test edx, edx
        jz out
        mov esi, [edx+0x4c]
        test esi, esi
        jz out
        mov eax, esi
        mov edx, [eax]
        call dword ptr [edx+%(get)#x]
        movzx eax, al
        add eax, %(cp)d
        cmp eax, 127
        jle ok
        mov eax, 127
    ok:
        mov edx, eax
        mov eax, esi
        mov ecx, [eax]
        call dword ptr [ecx+%(set)#x]
    out:
        pop esi
        xor eax, eax
        ret 4
    plain:
        push ebp
        mov ebp, esp
        push ecx
        push ebx
        push esi
        jmp %(resume)#x
    """ % {"harv": ID_HARVEST, "get": VMT_GETCP, "set": VMT_SETCP, "cp": HARVEST_CP, "resume": SITES["hcca"][2]})
    assert ZONE + len(out) <= ZONE_END, hex(ZONE + len(out))
    return bytes(out), where


def reloc_set(d):
    pe = struct.unpack_from("<I", d, 0x3C)[0]; opt = struct.unpack_from("<H", d, pe + 20)[0]; nsec = struct.unpack_from("<H", d, pe + 6)[0]
    secs = [struct.unpack_from("<IIII", d, pe + 24 + opt + 40 * k + 8) for k in range(nsec)]
    rrva, rsz = struct.unpack_from("<II", d, pe + 24 + 0x88)
    def r2f(rva):
        for vs, va, rs, ro in secs:
            if va <= rva < va + max(vs, rs): return ro + rva - va
    out = set()
    if not rsz: return out
    p, end = r2f(rrva), r2f(rrva) + rsz
    while p < end:
        page, size = struct.unpack_from("<II", d, p)
        if size < 8: break
        for q in range(p + 8, p + size, 2):
            e = struct.unpack_from("<H", d, q)[0]
            if e >> 12 == 3: out.add(BASE + page + (e & 0xFFF))
        p += size
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dll", default=DEFAULT_DLL)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read())
    zone, where = build()
    patches = {n: (va - CODE_V2F, orig, b"\xe9" + struct.pack("<i", where[n] - (va + 5)) + b"\x90" * (len(orig) - 5)) for n, (va, orig, _r) in SITES.items()}
    rl = reloc_set(d)
    bad = [hex(r) for r in rl if any(va - 3 <= r < va + len(o) for va, o, _r in SITES.values()) or ZONE <= r < ZONE_END]
    def classify(n, o, orig, new):
        cur = bytes(d[o:o + len(orig)])
        if cur == orig: return "vanilla"
        if cur == new: return "ours"
        if cur[0] == 0xE9 and ZONE <= SITES[n][0] + 5 + struct.unpack_from("<i", cur, 1)[0] < ZONE_END: return "stale"
        return "OTHER"
    states = {n: classify(n, o, orig, new) for n, (o, orig, new) in patches.items()}
    zl = bytes(d[ZONE - CODE_V2F:ZONE_END - CODE_V2F])
    zstate = "zero" if not any(zl) else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else "DIFFERS"
    print("sites %s | zone %s (%d B) | relocs %s | caves %s" % (states, zstate, len(zone), bad or "none", ", ".join("%s=%#x" % kv for kv in where.items())))
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        for name, s in where.items():
            print("  --", name)
            nxt = min([v for v in where.values() if v > s] + [ZONE + len(zone)])
            for i in md.disasm(zone[s - ZONE:nxt - ZONE], s): print("   %08X  %-16s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad or "OTHER" in states.values(): print("ABORT"); return 1
    if a.revert:
        for n, (o, orig, new) in patches.items():
            if states[n] in ("ours", "stale"): d[o:o + len(orig)] = orig
        d[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
        with open(a.dll, "r+b") as f: f.seek(0); f.write(d)
        print("reverted"); return 0
    if all(s == "ours" for s in states.values()) and zstate == "ours": print("already applied"); return 0
    if "ours" not in states.values() and "stale" not in states.values() and zstate != "zero": print("ABORT: zone not free"); return 1
    d[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE); d[ZONE - CODE_V2F:ZONE - CODE_V2F + len(zone)] = zone
    for n, (o, orig, new) in patches.items(): d[o:o + len(new)] = new
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(a.dll, BAK_SUFFIX)
    if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    with open(a.dll, "r+b") as f: f.seek(0); f.write(d)
    assert open(a.dll, "rb").read() == bytes(d); print("Written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
