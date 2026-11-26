#!/usr/bin/env python3
r"""
Channeler I/II/III (ability 0xCB, 2026-10-18) - AoWEPACK.dll engine part.

User spec: new multilevel ability "Channeler I/II/III", 10 skill points per level.  Level I = +30 % casting points,
II = +50 %, III = +100 % (of the unit's MAX casting points).  A unit without Spell Casting gets nothing.

Vanilla facts (RE 2026-10-18):
  * THero.GetCastingPointsMax 0x55788614 (THero VMT 0x55711FEC and TLeader VMT 0x55712238, slot +0x128):
        if [vmt+0x148] GetAbilityEnabled(0x34 Spell Casting) then result := 10 * [vmt+0x144] GetAbilityLevel(0x34)
    -> 10..50.  Every reader goes through the virtual: the new-day refill 0x55788741 ([hero+0x80] := max),
    SetCastingPoints 0x5578864C (clamps to it), the unit window / spellbook / hero-info labels in AoWx.exe, TCPCK.
    The current points are a SIGNED byte [hero+0x80] (SetCastingPoints compares with `cmp bl,al`) -> results are
    clamped to 127 (Channeler III at Spell Casting V = 100, so the clamp never bites in practice).
  * Ability registration: the reg chain head `call` @0x557BCF6E (ebx = registry; currently Tame v2's reg cave,
    patch_tame_animal_v2.py) - abilities are registered in id order, Tamed 0xCA is the last.
  * Multilevel abilities: same construction as patch_caster_levels_v1.py's cave_mkml (TMultiLevelAbility classref
    [0x5571DF90] via PIC delta, Create 0x55765168 (eax = VMT, dl = 1, ecx = 0), [+0x20] mask, [+0xC] id, [+8] name
    (_LStrAsg 0x55701150), [+0x28] cap 3, level costs TIntegerList.Put 0x55702EB4 on [+0x2C] idx 1..3 = 10).
    "Channeler I/II/III" names come from the generic cave_lsnames (TMultiLevelAbility VMT+0x10C).

This patch (zone 0x55819000..0x5581B000, header 'CHN1' + originals at the zone start):
  REG  @0x557BCF6E: call -> cave reg: call the previous head (Tame v2), then build + register ML 0xCB "Channeler"
       (cap 3, 10/10/10, mask 0x3FE = Spell Casting's).
  GCPM @0x55788614 (8 B: push ebx / mov ebx,eax / mov edx,0x34) -> jmp cave gcpm: the vanilla body, then
       level := [vmt+0x144](0xCB) (item-aware THero.GetAbilityLevel); 1 -> max*13 div 10, 2 -> max*15 div 10,
       >=3 -> max*2; result clamped to 127.  Spell Casting 0 -> 0 (Channeler does nothing).
  Rounds DOWN (50 -> 65 / 75 / 100, 30 -> 39 / 45 / 60, 10 -> 13 / 15 / 20).
  Current-point semantics are vanilla: the new day refills to the (new) max; SetCastingPoints clamps to it; gaining
  Channeler mid-turn raises the cap only (the extra points arrive at the next refill); losing it mid-turn leaves the
  current points until they are spent / the next refill (vanilla behaviour for any max drop, e.g. losing an item).
PIC: the reg cave reaches the classref / name literal through a call-pop delta; everything else is rel32 or virtual.
Editor-safe: GCPM only calls the unit's own virtuals (the same ones vanilla calls).  MP: deterministic.

Companions: patch_channeler_ability_pfs_v1.py (Ability.pfs record 213) and patch_exe_channeler_label_v1.py (unit
window "100/100" font), then LADDER += 0xCB in patch_aowx_banner_ceilings_v1.py + patch_tcablist_ceiling_v1.py.
LIFO: this becomes the reg chain head -> revert it BEFORE patch_tame_animal_v2.py / patch_reversal_v1.py.
Dry-run default; --apply / --revert / --dis; --dll <scratch copy>.  Backup <game>\backup\AoWEPACK.dll.bak_channeler.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DEFAULT_DLL = game_file("AoWEPACK.dll")
BAK_SUFFIX = ".bak_channeler"
BASE = 0x55700000
ZONE, ZONE_END = 0x55819000, 0x5581B000
HDR = 0x40
MAGIC = b"CHN1"
AB = 0xCB
NAME = b"Channeler"
MASK = 0x3FE
COST, CAP = 10, 3
PCT = {1: 13, 2: 15}                 # tenths; level >= 3 doubles
CLAMP = 127

REG_SITE = 0x557BCF6E
GCPM_SITE = 0x55788614
GCPM_ORIG = bytes.fromhex("538bd8ba34000000")
ML_CLASSREF, ML_CREATE = 0x5571DF90, 0x55765168
LSTRASG, INTLIST_PUT, REGABIL = 0x55701150, 0x55702EB4, 0x55750238
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, va):
    return bytes(ks.asm(src, va)[0])


def lit(s):
    return struct.pack("<ii", -1, len(s)) + s + b"\0"


def sections(d):
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    n = struct.unpack_from("<H", d, pe + 6)[0]; opt = struct.unpack_from("<H", d, pe + 20)[0]
    out = []
    for i in range(n):
        s = pe + 24 + opt + 40 * i
        vs, va, rs, ro = struct.unpack_from("<IIII", d, s + 8)
        out.append((vs, va, rs, ro))
    return out, pe


def va2off(d, va):
    for vs, rva, rs, ro in sections(d)[0]:
        if rva <= va - BASE < rva + max(vs, rs):
            return ro + va - BASE - rva
    raise ValueError(hex(va))


def reloc_set(d):
    secs, pe = sections(d)
    rrva, rsz = struct.unpack_from("<II", d, pe + 24 + 0x88)
    p = va2off(d, BASE + rrva); end = p + rsz; out = set()
    while p < end:
        page, size = struct.unpack_from("<II", d, p)
        if size < 8: break
        for q in range(p + 8, p + size, 2):
            e = struct.unpack_from("<H", d, q)[0]
            if e >> 12 == 3: out.add(BASE + page + (e & 0xFFF))
        p += size
    return out


def build(prev_reg):
    out = bytearray(HDR); where = {}

    def place(name, src):
        while len(out) % 16: out.append(0)
        va = ZONE + len(out); where[name] = va
        out.extend(asm(src, va))

    b = lit(NAME); out[0x20:0x20 + len(b)] = b; where["name"] = ZONE + 0x20 + 8
    assert 0x20 + len(b) <= HDR
    costs = "".join("""
        mov eax, dword ptr [edi + 0x2c]
        mov edx, %d
        mov ecx, %d
        call %#x""" % (lvl, COST, INTLIST_PUT) for lvl in range(1, CAP + 1))
    place("reg", """
        call %(prev)#x
        push esi
        push edi
        call rd
    rd:
        pop esi
        sub esi, rd
        mov eax, dword ptr [esi + %(cref)#x]
        mov dl, 1
        xor ecx, ecx
        call %(create)#x
        mov edi, eax
        mov word ptr [edi + 0x20], %(mask)#x
        mov dword ptr [edi + 0xc], %(ab)#x
        lea eax, [edi + 8]
        lea edx, [esi + %(name)#x]
        call %(lstrasg)#x
        mov dword ptr [edi + 0x28], %(cap)d
        %(costs)s
        mov edx, edi
        mov eax, ebx
        call %(reg)#x
        pop edi
        pop esi
        ret
    """ % {"prev": prev_reg, "cref": ML_CLASSREF, "create": ML_CREATE, "mask": MASK, "ab": AB, "name": where["name"],
           "lstrasg": LSTRASG, "cap": CAP, "costs": costs, "reg": REGABIL})
    place("gcpm", """
        push ebx
        push esi
        mov ebx, eax
        mov edx, 0x34
        mov eax, ebx
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x148]
        test al, al
        je gzero
        mov edx, 0x34
        mov eax, ebx
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x144]
        add eax, eax
        lea esi, [eax + eax*4]
        mov edx, %(ab)#x
        mov eax, ebx
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x144]
        cmp eax, 1
        jl gdone
        je gl1
        cmp eax, 2
        je gl2
        add esi, esi
        jmp gdone
    gl1:
        imul eax, esi, %(p1)d
        jmp gdiv
    gl2:
        imul eax, esi, %(p2)d
    gdiv:
        xor edx, edx
        mov ecx, 10
        div ecx
        mov esi, eax
    gdone:
        cmp esi, %(clamp)d
        jle gok
        mov esi, %(clamp)d
    gok:
        mov eax, esi
        pop esi
        pop ebx
        ret
    gzero:
        xor eax, eax
        pop esi
        pop ebx
        ret
    """ % {"ab": AB, "p1": PCT[1], "p2": PCT[2], "clamp": CLAMP})
    assert ZONE + len(out) <= ZONE_END
    return out, where


def write_inplace(path, data):
    with open(path, "r+b") as f:
        f.seek(0); f.write(data); f.truncate(len(data))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dll", default=DEFAULT_DLL)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    d = open(a.dll, "rb").read()
    g = lambda va, n: bytes(d[va2off(d, va):va2off(d, va) + n])
    zl = g(ZONE, ZONE_END - ZONE)
    cur_reg, cur_gcpm = g(REG_SITE, 5), g(GCPM_SITE, 8)
    ours = zl[:4] == MAGIC
    if ours:
        sav_reg, sav_gcpm = zl[4:9], zl[0x0C:0x14]
    else:
        sav_reg, sav_gcpm = cur_reg, cur_gcpm
    assert sav_reg[0] == 0xE8, "reg site original is not a call (%s)" % sav_reg.hex()
    assert sav_gcpm == GCPM_ORIG, "GetCastingPointsMax prologue %s (expected %s) - another patch?" % (sav_gcpm.hex(), GCPM_ORIG.hex())
    prev_reg = REG_SITE + 5 + struct.unpack_from("<i", sav_reg, 1)[0]
    zone, where = build(prev_reg)
    zone[0:4] = MAGIC; zone[4:9] = sav_reg; zone[0x0C:0x14] = sav_gcpm
    zone = bytes(zone)
    hooked_reg = b"\xE8" + struct.pack("<i", where["reg"] - (REG_SITE + 5))
    hooked_gcpm = b"\xE9" + struct.pack("<i", where["gcpm"] - (GCPM_SITE + 5)) + b"\x90" * 3
    st_reg = "ours" if cur_reg == hooked_reg else "orig" if cur_reg == sav_reg else "OTHER"
    st_gcpm = "ours" if cur_gcpm == hooked_gcpm else "orig" if cur_gcpm == sav_gcpm else "OTHER"
    zstate = "zero" if not any(zl) else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else "DIFFERS"
    rl = reloc_set(d)
    bad = [hex(r) for r in rl if ZONE - 3 <= r < ZONE_END or REG_SITE - 3 <= r < REG_SITE + 5 or GCPM_SITE - 3 <= r < GCPM_SITE + 8]
    print("%s\n  reg site %#x: %s (prev head %#x) | GetCastingPointsMax %#x: %s | zone %#x: %s (%d B) | relocs %s"
          % (a.dll, REG_SITE, st_reg, prev_reg, GCPM_SITE, st_gcpm, ZONE, zstate, len(zone), bad or "none"))
    print("  caves " + ", ".join("%s=%#x" % kv for kv in where.items()))
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        for i in md.disasm(zone[HDR:], ZONE + HDR): print("   %08X  %-24s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad or "OTHER" in (st_reg, st_gcpm) or zstate == "DIFFERS":
        print("ABORT"); return 1
    out = bytearray(d)
    put = lambda va, b: out.__setitem__(slice(va2off(d, va), va2off(d, va) + len(b)), b)
    if a.revert:
        if not ours and st_reg == st_gcpm == "orig": print("nothing to revert"); return 0
        put(REG_SITE, sav_reg); put(GCPM_SITE, sav_gcpm); put(ZONE, bytes(ZONE_END - ZONE))
        write_inplace(a.dll, bytes(out)); print("reverted (reg site, GetCastingPointsMax, zone cleared)"); return 0
    if ours and st_reg == st_gcpm == zstate == "ours": print("already applied"); return 0
    put(ZONE, zone); put(REG_SITE, hooked_reg); put(GCPM_SITE, hooked_gcpm)
    print("  %d bytes change" % sum(1 for x, y in zip(d, out) if x != y))
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if os.path.abspath(a.dll) == os.path.abspath(DEFAULT_DLL):
        bak = bak_path(a.dll, BAK_SUFFIX)
        if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    write_inplace(a.dll, bytes(out))
    assert open(a.dll, "rb").read() == bytes(out)
    print("Written and verified.  Next: patch_channeler_ability_pfs_v1.py --apply, patch_exe_channeler_label_v1.py --apply,"
          " then LADDER += 0xCB in the two ceiling scripts and re-run them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
