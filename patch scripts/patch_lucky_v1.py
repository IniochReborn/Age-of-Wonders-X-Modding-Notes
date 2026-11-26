#!/usr/bin/env python3
r"""
Lucky (232): the Secret tier-1 unit enchantment - grants +3 RESISTANCE (2026-10-18).

Registered by patch_dual_sphere_spells_v1.py as a TDarkGift clone (exactly like Lionheart 373, see patch_lionheart_v1.py
for the full TDarkGift / TDarkGiftEnchantment RE).  Lucky's ability 0xC8 = a THIRD TDarkGiftEnchantment instance
(after Dark Gift 0xA9 and Lionheart 0xB1), and:
  * ExecuteSpell (0x557E8478) / ValidTarget (0x557E84E8) entry jumps -> caves that handle [spell+0x10] == 232 with
    ability 0xC8 and pass every other spell to the PREVIOUS owner (today Lionheart's caves; vanilla prologue replay if
    the sites are vanilla);
  * the RegisterAbility call after the vanilla TDarkGiftEnchantment (0x557BCDAF) -> cave: previous target first
    (Lionheart's 0xB1 registration or RegisterAbility itself), then a new instance, id 0xC8, name "Lucky";
  * TDarkGiftEnchantment VMT stat getters (TUnitEnchantmentAbility slots: +0x5C ATK, +0x60 DEF, +0x64 RES,
    +0x68 DMG - confirmed against TBlessedEnchantment (+0x60/+0x64 = 1) / TStoneSkinAbility (+0x60 = 2) /
    TEnchantedWeaponAbility (+0x5C/+0x68 = 1)):
      +0x64 RES -> cave: 3 for id 0xC8, else the previous getter (base 0x5574E998 = 0);
      +0x68 DMG -> cave: 0 for id 0xC8, else the previous getter (Lionheart's 0xB1/0xA9 cave) - so Lucky gives no
                   Dark-Gift damage.  Death Strike (checked for 0xA9 only) and Fearless (0xB1 only) are not conferred.
Ability.pfs record 0xC8+10 = patch_lucky_ability_pfs_v1.py; then append 0xC8 to LADDER in patch_tcablist_ceiling_v1.py
and patch_aowx_banner_ceilings_v1.py (bound 0xC9) and re-run both.
Zone 0x55881800..0x55882000 (CODE zero tail, no relocs).  Header = magic + every site's ORIGINAL bytes (exact revert,
chained in front of whatever owned the sites at apply time).  PIC: rel32 + call/pop delta for the cell/name.
LIFO: Lucky chains in front of Lionheart on ex/vt/reg/+0x68 -> revert Lucky before re-running patch_lionheart_v1.py.
Backup <game>\backup\AoWEPACK.dll.bak_lucky.  Dry-run default; --apply / --revert / --dis / --dll <copy>.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DEFAULT_DLL = game_file("AoWEPACK.dll")
BAK_SUFFIX = ".bak_lucky"
BASE, CODE_V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x55881800, 0x55882000
MAGIC = b"LUCKY001"
LUCKY, ABIL_LUCKY = 232, 0xC8
RES_BONUS = 3
DGE_CELL, DGE_CREATE, DGE_VMT = 0x557B935C, 0x557BB69C, 0x557B939C
LSTRASG, REGABIL = 0x55701150, 0x55750238
BASECHECK, GETABILITYDATA = 0x5577ACAC, 0x5574F1C4
EX, VT, REG = 0x557E8478, 0x557E84E8, 0x557BCDAF
EX_VAN, VT_VAN, REG_VAN = bytes.fromhex("558bec515356"), bytes.fromhex("53568bf18bce"), bytes.fromhex("e88434f9ff")
S64, S68 = DGE_VMT + 0x64, DGE_VMT + 0x68
HDR = 0x30          # magic 8 | ex 6 | vt 6 | reg 5 | s64 4 | s68 4
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, va):
    return bytes(ks.asm(src, va)[0])


def u32(d, va): return struct.unpack_from("<I", d, va - CODE_V2F)[0]


def rel_target(b, va):
    return va + 5 + struct.unpack_from("<i", b, 1)[0]


def build(orig):
    """orig = dict of the sites' ORIGINAL (pre-Lucky) contents -> (zone bytes, cave map)."""
    out = bytearray(MAGIC + orig["ex"] + orig["vt"] + orig["reg"] + struct.pack("<II", orig["s64"], orig["s68"]))
    out += bytes(HDR - len(out)); where = {}
    lit = b"Lucky"
    out += struct.pack("<ii", -1, len(lit)); where["name"] = ZONE + len(out); out += lit + b"\0"

    def place(name, src):
        while len(out) % 16: out.append(0)
        va = ZONE + len(out); where[name] = va
        out.extend(asm(src, va))

    # previous owners: the jmp/call target if the site is hooked, else a replay stub of the vanilla prologue
    if orig["ex"][0] == 0xE9: prev_ex = rel_target(orig["ex"], EX)
    else:
        assert orig["ex"] == EX_VAN, orig["ex"].hex()
        place("exprev", "push ebp\nmov ebp, esp\npush ecx\npush ebx\npush esi\njmp %#x" % (EX + 6)); prev_ex = where["exprev"]
    if orig["vt"][0] == 0xE9: prev_vt = rel_target(orig["vt"], VT)
    else:
        assert orig["vt"] == VT_VAN, orig["vt"].hex()
        place("vtprev", "push ebx\npush esi\nmov esi, ecx\nmov ecx, esi\njmp %#x" % (VT + 6)); prev_vt = where["vtprev"]
    assert orig["reg"][0] == 0xE8, orig["reg"].hex(); prev_reg = rel_target(orig["reg"], REG)
    P = dict(lucky=LUCKY, abil=ABIL_LUCKY, gad=GETABILITYDATA, base=BASECHECK, prev_ex=prev_ex, prev_vt=prev_vt,
             prev_reg=prev_reg, prev64=orig["s64"], prev68=orig["s68"], res=RES_BONUS, reg=REGABIL, cell=DGE_CELL,
             create=DGE_CREATE, name=where["name"], lstrasg=LSTRASG)

    # ex: TDarkGift.ExecuteSpell for Lucky (eax spell, edx caster, ecx unit; ret 8) - Lionheart's body with 0xC8
    place("ex", """
        cmp dword ptr [eax+0x10], %(lucky)d
        jne %(prev_ex)#x
        push ebp
        mov ebp, esp
        push ecx
        push ebx
        push esi
        push edi
        mov esi, ecx
        mov [ebp-4], edx
        mov ebx, eax
        mov ecx, esi
        mov edx, [ebp-4]
        mov eax, ebx
        mov edi, [eax]
        call dword ptr [edi+0x9c]
        test al, al
        je fail
        mov edx, %(abil)d
        mov eax, esi
        mov ecx, [eax]
        call dword ptr [ecx+0x94]
        test al, al
        je ok
        mov edx, %(abil)d
        mov eax, esi
        call %(gad)#x
        mov esi, [eax+0x10]
        mov edx, [ebx+0x1c]
        mov eax, esi
        mov ecx, [eax]
        call dword ptr [ecx+0x54]
        mov eax, [ebp-4]
        mov dl, byte ptr [eax+0x24]
        mov eax, esi
        mov ecx, [eax]
        call dword ptr [ecx+0x58]
        mov al, byte ptr [ebx+0x3c]
        mov [esi+0x14], al
    ok:
        mov al, 1
        jmp done
    fail:
        xor eax, eax
    done:
        pop edi
        pop esi
        pop ebx
        pop ecx
        pop ebp
        ret 8
    """ % P)

    # vt: TDarkGift.ValidTarget for Lucky (eax spell, edx caster, ecx unit -> al): base check AND not already Lucky
    place("vt", """
        cmp dword ptr [eax+0x10], %(lucky)d
        jne %(prev_vt)#x
        push ebx
        push esi
        push edi
        mov edi, eax
        mov esi, ecx
        mov ecx, esi
        call %(base)#x
        mov ebx, eax
        test bl, bl
        je no
        mov edx, %(abil)d
        mov eax, esi
        mov ecx, [eax]
        call dword ptr [ecx+0x148]
        test al, al
        je yes
    no:
        xor eax, eax
        jmp done
    yes:
        mov al, 1
    done:
        pop edi
        pop esi
        pop ebx
        ret
    """ % P)

    # r64: TDarkGiftEnchantment.GetResistance (eax = ability): +3 for Lucky, else the previous getter
    place("r64", """
        cmp dword ptr [eax+0xc], %(abil)d
        jne %(prev64)#x
        mov eax, %(res)d
        ret
    """ % P)
    # d68: TDarkGiftEnchantment.GetDamage: 0 for Lucky, else the previous getter (Lionheart's 0xB1 / 0xA9 cave)
    place("d68", """
        cmp dword ptr [eax+0xc], %(abil)d
        jne %(prev68)#x
        xor eax, eax
        ret
    """ % P)
    # reg: previous target (RegisterAbility, or Lionheart's 0xB1 registration) then a TDarkGiftEnchantment id 0xC8 "Lucky"
    place("reg", """
        call %(prev_reg)#x
        push esi
        call next
    next:
        pop esi
        sub esi, next
        lea eax, [esi + %(cell)#x]
        mov eax, [eax]
        xor ecx, ecx
        mov dl, 1
        call %(create)#x
        mov dword ptr [eax + 0xc], %(abil)d
        push eax
        lea edx, [esi + %(name)#x]
        add eax, 8
        call %(lstrasg)#x
        pop edx
        mov eax, ebx
        call %(reg)#x
        pop esi
        ret
    """ % P)
    assert ZONE + len(out) <= ZONE_END, hex(ZONE + len(out))
    return bytes(out), where


def hooks(where):
    return {"ex": b"\xe9" + struct.pack("<i", where["ex"] - (EX + 5)) + b"\x90",
            "vt": b"\xe9" + struct.pack("<i", where["vt"] - (VT + 5)) + b"\x90",
            "reg": b"\xe8" + struct.pack("<i", where["reg"] - (REG + 5))}


def reloc_set(d):
    pe = struct.unpack_from("<I", d, 0x3C)[0]; opt = struct.unpack_from("<H", d, pe + 20)[0]; nsec = struct.unpack_from("<H", d, pe + 6)[0]
    secs = [struct.unpack_from("<IIII", d, pe + 24 + opt + 40 * k + 8) for k in range(nsec)]
    rrva, rsz = struct.unpack_from("<II", d, pe + 24 + 0x88)
    def r2f(rva):
        for vs, va, rs, ro in secs:
            if va <= rva < va + max(vs, rs): return ro + rva - va
    p, end, out = r2f(rrva), r2f(rrva) + rsz, set()
    while p < end:
        page, size = struct.unpack_from("<II", d, p)
        if size < 8: break
        for q in range(p + 8, p + size, 2):
            e = struct.unpack_from("<H", d, q)[0]
            if e >> 12 == 3: out.add(BASE + page + (e & 0xFFF))
        p += size
    return out


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
    zl = d[ZONE - CODE_V2F:ZONE_END - CODE_V2F]
    live = {"ex": d[EX - CODE_V2F:EX - CODE_V2F + 6], "vt": d[VT - CODE_V2F:VT - CODE_V2F + 6],
            "reg": d[REG - CODE_V2F:REG - CODE_V2F + 5], "s64": u32(d, S64), "s68": u32(d, S68)}
    if zl[:8] == MAGIC:
        orig = {"ex": zl[8:14], "vt": zl[14:20], "reg": zl[20:25]}
        orig["s64"], orig["s68"] = struct.unpack_from("<II", zl, 25); zstate = "ours"
    elif not any(zl):
        orig = dict(live); zstate = "zero"
    else:
        print("ABORT: zone %#x..%#x not free" % (ZONE, ZONE_END)); return 1
    zone, where = build(orig)
    hk = hooks(where)
    rl = reloc_set(d)
    bad = [hex(r) for r in rl if ZONE <= r < ZONE_END or EX <= r < EX + 6 or VT <= r < VT + 6 or REG <= r < REG + 5]
    if S64 not in rl or S68 not in rl: bad.append("VMT slot not relocated?")

    def st(k):
        if k in ("s64", "s68"):
            want = where["r64" if k == "s64" else "d68"]
            return "ours" if live[k] == want else ("free" if live[k] == orig[k] else "OTHER")
        return "ours" if live[k] == hk[k] else ("free" if live[k] == orig[k] else "OTHER")
    states = {k: st(k) for k in ("ex", "vt", "reg", "s64", "s68")}
    print("zone %s (%d B) | sites %s | prev ex %#x vt %#x reg %#x r64 %#x d68 %#x | relocs %s" % (
        zstate, len(zone), states,
        rel_target(orig["ex"], EX) if orig["ex"][0] == 0xE9 else 0, rel_target(orig["vt"], VT) if orig["vt"][0] == 0xE9 else 0,
        rel_target(orig["reg"], REG), orig["s64"], orig["s68"], bad or "none"))
    if a.dis:
        import capstone
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(zone[HDR:], ZONE + HDR):
            print("   %08X  %-16s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad: print("ABORT (relocs)"); return 1
    out = bytearray(d)
    if a.revert:
        if zstate != "ours": print("already vanilla (zone not ours)"); return 0
        if any(v != "ours" for v in states.values()):
            print("ABORT: a site no longer points at Lucky (revert the patch chained in front first, LIFO): %s" % states); return 1
        out[EX - CODE_V2F:EX - CODE_V2F + 6] = orig["ex"]; out[VT - CODE_V2F:VT - CODE_V2F + 6] = orig["vt"]
        out[REG - CODE_V2F:REG - CODE_V2F + 5] = orig["reg"]
        struct.pack_into("<I", out, S64 - CODE_V2F, orig["s64"]); struct.pack_into("<I", out, S68 - CODE_V2F, orig["s68"])
        out[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
        write_inplace(a.dll, bytes(out)); print("reverted"); return 0
    if "OTHER" in states.values(): print("ABORT: a site is owned by an unknown patch: %s" % states); return 1
    if all(v == "ours" for v in states.values()) and zl[:len(zone)] == zone and not any(zl[len(zone):]):
        print("already applied"); return 0
    out[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
    out[ZONE - CODE_V2F:ZONE - CODE_V2F + len(zone)] = zone
    out[EX - CODE_V2F:EX - CODE_V2F + 6] = hk["ex"]; out[VT - CODE_V2F:VT - CODE_V2F + 6] = hk["vt"]
    out[REG - CODE_V2F:REG - CODE_V2F + 5] = hk["reg"]
    struct.pack_into("<I", out, S64 - CODE_V2F, where["r64"]); struct.pack_into("<I", out, S68 - CODE_V2F, where["d68"])
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(a.dll, BAK_SUFFIX)
    if a.dll == DEFAULT_DLL and not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    write_inplace(a.dll, bytes(out)); assert open(a.dll, "rb").read() == bytes(out); print("Written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
