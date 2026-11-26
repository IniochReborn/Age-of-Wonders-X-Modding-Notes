"""
Sandstorm (spell 388, Fire/Air tier 1) - v2 2026-10-14.  AoWTCPCK.dll only.

Spec (user): an AoE combat spell, long range, Ooze-sized area (19 hexes), hex-targeted; the repeated strikes hit only
units inside the area and each unit no more than 3 times; 8 ATK / 1 DMG physical; double damage against flyers.

v1 (Swarm clone, class 14, retargeted per strike) CRASHED the game (HSEPack THSMap per-field HS Show loop @0x5560D68F
dereferencing a bad HS pointer, 0xC0000409 then 0xC0000005) and was unit-targeted anyway - replaced.  --revert of a
v1 state is still supported (sites 0x40E977 / 0x40C39E, reloc 0x40E978).

v2 = a GREAT HAIL clone (hail class 0x0A, hex-targeted, the per-landing damage path):
  AoWEPACK donor TGreatHail (cell 0x557F5504, Create 0x557F8F18, site 0x557FA6F4, id 0x74, pfs key 126; its VMT
  slots 0x60..0x98 are the TCombatSpell base ones, same as Swarm's): pokes ATK 8 / DMG 1 / types 0x80 Physical; range
  +0x39 = 0x0C inherited.  Alias 388 -> 0x74 at the id-keyed TC sites (patch_tc_spell_alias_v1.py) so the TC treats
  the te as Great Hail: phase 0 sets 20 strikes, the landing sends the 0x31006 field message, and TUnitHS's handler
  (0x4213BD..) builds the CA = GetSpell(id).CreateCA(caster [msg+8], unit [hs+0x1C]) -> TCombatSpellCA.Setup rolls
  the damage into byte [ca+0x10], then ExecuteCombatAction.  The targeting PREVIEW (0x42827A) should be Ooze's 19-hex
  one -> per-site alias 388 -> 0x7C there (SITE_ALIAS, see the report).
  hx    call-hook 0x40E2B4 (`call HXtoHP`, 5 B, no reloc) in NextStrike's hail case, after the pattern hex went into
        [ebp-0x3C]/[ebp-0x40]: for a 388 te, on strike 0 ([te+0x34] == 0) the 19 hexes around the target
        [te+0x20]/[te+0x22] are enumerated with HSEngine.CenterHNtoHX (thunk 0x4022AC: eax hx, edx hy, ecx HN 0..18,
        pushes &outX then &outY, ret 8), the in-level ones ([level+0xC]/[+0x10]) holding a unit HS (field VMT+0x80
        FindOwnedChild 0x220104) are listed in DATA-page slack (0x46BF68.., 19 pairs) with the te latched at 0x46BF50,
        and the strike count becomes min(30, 3 x units) (7 for show when the area is empty).  Every strike k then
        lands on list[k mod n] (round robin -> no unit is hit more than 3 times), written into [ebp-0x3C]/[ebp-0x40]
        and eax/edx before tail-jumping into HXtoHP.  Deterministic: no RNG draws added or removed -> MP-safe.
  fly   call-hook 0x421415 (`mov [ebp-0x10],eax / mov eax,[ebp-0x10]`, 6 B, no reloc) right after the handler's
        CreateCA: if [ca+0x18] == 388 and the unit ([[ebp-4]+0x1C], a TCombatUnit; VMT+0x88 GetAbilityEnabled) has
        FLYING (1), the rolled damage byte [ca+0x10] is doubled before it is executed.
Zone 0x43DD00..0x43DF00 (zero, reloc-free).  Backup <game>\\backup\\AoWTCPCK.dll.bak_sandstorm (whole-file, taken at
v1 - never restore by copy; use --revert).  Dry-run default; --apply / --revert / --dis.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DEFAULT_DLL = game_file("AoWTCPCK.dll")
BAK_SUFFIX = ".bak_sandstorm"
BASE, CODE_V2F = 0x400000, 0x400C00
ZONE, ZONE_END = 0x43DD00, 0x43DF00
SPELL_ID = 388
AOE_HEXES = 19                              # HN 0..18 = centre + two rings (the Ooze-sized blob)
MAX_STRIKES, HITS_PER_UNIT, SHOW_STRIKES = 30, 3, 7   # v3.1 2026-10-14 (user: still too much damage): 2 landings per unit (was 3, max 30 strikes)
MAX_LIST = 15                               # v4.2 2026-10-15: the unit list (G_LIST 0x46BF68, 8 B/entry) stops at 15 units - 16+ overran the Hurl Boulder / Flashfreeze wait dwords 0x46BFE0/0x46BFE4 (19 would reach BSS 0x46C000) and the 16-entry per-unit table
FLYING = 1
HX_SITE, HX_ORIG = 0x40E2B4, bytes.fromhex("e80340ffff")              # call HXtoHP 0x4022BC
FLY_SITE, FLY_ORIG = 0x421415, bytes.fromhex("8945f08b45f0")          # mov [ebp-0x10],eax / mov eax,[ebp-0x10]
V1_PICK_SITE, V1_PICK_ORIG, V1_RELOC = 0x40E977, bytes.fromhex("a120944600"), 0x40E978
V1_FLY_SITE, V1_FLY_ORIG = 0x40C39E, bytes.fromhex("8b55e0894230")
MAP_LIST_GLOBAL = 0x469420
GETMAPLEVEL, GETFIELD, CENTERHNTOHX, HXTOHP, UNITHS_CLASSID = 0x401E64, 0x401E54, 0x4022AC, 0x4022BC, 0x220104
ZONE2, ZONE2_END = 0x43E500, 0x43E600       # v4: the shared per-unit cap routine + the landing-CA hook cave
LAND_SITE, LAND_ORIG = 0x40C39E, bytes.fromhex("8b55e0894230")       # mov edx,[ebp-0x20] / mov [edx+0x30],eax - right after the landing's direct GetSpell(id).CreateCA(caster, [fx+0x2C])
G_STAT, G_TAB, TAB_N = 0x46BA70, 0x46BA80, 16   # v3 2026-10-14: per-cast stats (+0 landings, +4 units, +8 strike count) + a 16 x {unit HS, landings} table (DATA zero-fill slack 0x46BA70..0x46BB00, between Ashes' queue and its trace ring)
G_TE, G_CX, G_CY, G_HN, G_N, G_LIST = 0x46BF50, 0x46BF54, 0x46BF58, 0x46BF44, 0x46BF64, 0x46BF68   # v2.1: G_HN moved off 0x46BF60 (= Implosion v2's spawn latch)   # DATA-page slack; list ends at 0x46C000 (BSS starts there)

ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm_delta(src, va):
    s1 = src.replace("call $D", ".byte 0xe8, 0, 0, 0, 0").replace("sub ebx, $D", "sub ebx, 0x7fffffff")
    b = bytearray(ks.asm(s1, va)[0])
    anchor = bytes.fromhex("e8000000005b81ebffffff7f")
    k = b.find(anchor); assert k >= 0, "delta anchor not found"
    struct.pack_into("<I", b, k + 8, va + k + 5)
    return bytes(b)


def asm(src, va):
    return bytes(ks.asm(src, va)[0])


def build_hx(va):
    src = """
        push eax
        push ebx
        push esi
        push edi
        push ecx
        push edx
        call $D
        pop ebx
        sub ebx, $D
        mov eax, [ebp-4]
        cmp dword ptr [eax+0x18], %(id)d
        jne pass
        cmp dword ptr [eax+0x34], 0
        jne uselist
        mov [ebx+%(gte)#x], eax
        movzx ecx, word ptr [eax+0x20]
        mov [ebx+%(gcx)#x], ecx
        movzx ecx, word ptr [eax+0x22]
        mov [ebx+%(gcy)#x], ecx
        lea edi, [ebx+%(gstat)#x]
        xor eax, eax
        mov ecx, %(wipe)d
        rep stosd
        mov eax, [ebx+%(maplist)#x]
        mov eax, [eax]
        mov eax, [eax+0x10]
        xor edx, edx
        call %(getlevel)#x
        mov esi, eax
        sub esp, 8
        xor edi, edi
        mov dword ptr [ebx+%(ghn)#x], 0
    hnloop:
        lea eax, [esp]
        push eax
        lea eax, [esp+8]
        push eax
        mov ecx, [ebx+%(ghn)#x]
        mov eax, [ebx+%(gcx)#x]
        mov edx, [ebx+%(gcy)#x]
        call %(cnhx)#x
        mov edx, [esp]
        mov ecx, [esp+4]
        test edx, edx
        js nohit
        test ecx, ecx
        js nohit
        cmp edx, [esi+0xc]
        jge nohit
        cmp ecx, [esi+0x10]
        jge nohit
        mov eax, esi
        call %(getfield)#x
        test eax, eax
        jz nohit
        mov edx, %(unitcls)#x
        mov ecx, [eax]
        call dword ptr [ecx+0x80]
        test eax, eax
        jz nohit
        mov eax, [esp]
        mov [ebx+edi*8+%(glist)#x], eax
        mov eax, [esp+4]
        mov [ebx+edi*8+%(glist4)#x], eax
        inc edi
        cmp edi, %(maxlist)d
        jae listdone
    nohit:
        inc dword ptr [ebx+%(ghn)#x]
        cmp dword ptr [ebx+%(ghn)#x], %(nhex)d
        jb hnloop
    listdone:
        add esp, 8
        mov [ebx+%(gn)#x], edi
        mov [ebx+%(gstat)#x+4], edi
        mov eax, [ebp-4]
        test edi, edi
        jz setshow
        lea ecx, [edi+edi*2]
        cmp ecx, %(maxs)d
        jbe setn
        mov ecx, %(maxs)d
    setn:
        mov [eax+0x28], ecx
        mov [ebx+%(gstat)#x+8], ecx
        jmp uselist
    setshow:
        mov dword ptr [eax+0x28], %(show)d
        mov dword ptr [ebx+%(gstat)#x+8], %(show)d
    uselist:
        mov eax, [ebp-4]
        cmp [ebx+%(gte)#x], eax
        jne pass
        mov edi, [ebx+%(gn)#x]
        test edi, edi
        jz pass
        mov eax, [eax+0x34]
        xor edx, edx
        div edi
        mov eax, [ebx+edx*8+%(glist)#x]
        mov ecx, [ebx+edx*8+%(glist4)#x]
        mov [ebp-0x3c], eax
        mov [ebp-0x40], ecx
        mov [esp+20], eax
        mov [esp], ecx
    pass:
        pop edx
        pop ecx
        pop edi
        pop esi
        pop ebx
        pop eax
        jmp %(hxtohp)#x
    """ % {"id": SPELL_ID, "gte": G_TE, "gcx": G_CX, "gcy": G_CY, "ghn": G_HN, "gn": G_N, "glist": G_LIST, "glist4": G_LIST + 4,
           "maplist": MAP_LIST_GLOBAL, "getlevel": GETMAPLEVEL, "cnhx": CENTERHNTOHX, "getfield": GETFIELD, "unitcls": UNITHS_CLASSID,
           "nhex": AOE_HEXES, "maxlist": MAX_LIST, "maxs": MAX_STRIKES, "show": SHOW_STRIKES, "hxtohp": HXTOHP,
           "gstat": G_STAT, "wipe": (G_TAB + 8 * TAB_N - G_STAT) // 4}
    assert HITS_PER_UNIT == 3
    return asm_delta(src, va)


def build_cap(va):
    """v4 (user: 4 damage to an archer - max should be 3 - and NOT always 3 hits; 1..3 per unit): the ONE per-unit cap,
    called from every place a Sandstorm CA is created (the 0x31006 unit handler = `fly`, and the strike's own landing
    CA 0x40C39B = `land`).  eax = CA, edx = the target TCombatUnit (may be nil).  Key = the CA's target unit id byte
    [ca+0xE] + 1 (so both paths count together).  Quota per unit and cast = 1 + ((key*5 + 3*cx + cy) mod 3), cx/cy =
    the cast's target hex (deterministic -> MP-safe, varies per unit and per cast); landings within the quota do 1
    damage (2 vs Flying, [ca+0x10] clamped), later ones 0.  All registers preserved."""
    src = """
        cmp dword ptr [eax+0x18], %(id)d
        jne cdone_fast
        pushal
        mov esi, eax
        call $D
        pop ebx
        sub ebx, $D
        inc dword ptr [ebx+%(gstat)#x]
        movzx ecx, byte ptr [esi+0xe]
        inc ecx
        lea edi, [ebx+%(gtab)#x]
        mov edx, %(tabn)d
    find:
        cmp [edi], ecx
        je found
        cmp dword ptr [edi], 0
        je newe
        add edi, 8
        dec edx
        jnz find
        jmp counted
    newe:
        mov [edi], ecx
    found:
        lea eax, [ecx+ecx*4]
        mov edx, [ebx+%(gcx)#x]
        lea edx, [edx+edx*2]
        add eax, edx
        add eax, [ebx+%(gcy)#x]
        xor edx, edx
        push ecx
        mov ecx, 3
        div ecx
        pop ecx
        inc edx
        cmp [edi+4], edx
        jae over
        inc dword ptr [edi+4]
    counted:
        cmp byte ptr [esi+0x10], 0
        je cdone
        mov byte ptr [esi+0x10], 1
        mov eax, [esp+0x14]
        test eax, eax
        jz cdone
        mov eax, [eax+0x4c]
        test eax, eax
        jz cdone
        mov ecx, [eax]
        call dword ptr [ecx+0xe8]
        test al, 2
        jz cdone
        mov byte ptr [esi+0x10], 2
        jmp cdone
    over:
        mov byte ptr [esi+0x10], 0
    cdone:
        popal
    cdone_fast:
        ret
    """ % {"id": SPELL_ID, "gstat": G_STAT, "gtab": G_TAB, "tabn": TAB_N, "gcx": G_CX, "gcy": G_CY}   # v4.1 2026-10-14: Flying = TUnit ([cu+0x4C]) VMT+0xE8 GetMovementTypes bit 2 (the Vortex test). The old TCombatUnit VMT+0x88 call dropped the ability id (it forwards to TUnit VMT+0xE0 with edx = a VMT) and returned true for EVERY unit -> every hit did 2 damage (the archer 4 / 5-HP kills)
    return asm_delta(src, va)


def build_land(va, cap_va):
    return asm("""
        push edx
        mov edx, [ebp-0x20]
        mov edx, [edx+0x2c]
        call %(cap)#x
        pop edx
        mov edx, [ebp-0x20]
        mov [edx+0x30], eax
        ret
    """ % {"cap": cap_va}, va)


def build_fly(va, cap_va):
    """v4: the 0x31006 unit handler, right after its CreateCA: the shared cap (unit = [[ebp-4]+0x1C])."""
    return asm("""
        mov [ebp-0x10], eax
        mov edx, [ebp-4]
        mov edx, [edx+0x1c]
        call %(cap)#x
        mov eax, [ebp-0x10]
        ret
    """ % {"cap": cap_va}, va)


def reloc_entries(d):
    pe = struct.unpack_from("<I", d, 0x3C)[0]; opt = struct.unpack_from("<H", d, pe + 20)[0]; nsec = struct.unpack_from("<H", d, pe + 6)[0]
    secs = [struct.unpack_from("<IIII", d, pe + 24 + opt + 40 * k + 8) for k in range(nsec)]
    rrva, rsz = struct.unpack_from("<II", d, pe + 24 + 0x88)
    def r2f(rva):
        for vs, va, rs, ro in secs:
            if va <= rva < va + max(vs, rs): return ro + rva - va
    p, end, out = r2f(rrva), r2f(rrva) + rsz, {}
    while p < end:
        page, size = struct.unpack_from("<II", d, p)
        if size < 8: break
        for q in range(p + 8, p + size, 2):
            e = struct.unpack_from("<H", d, q)[0]
            if e >> 12 in (0, 3): out[BASE + page + (e & 0xFFF)] = (q, e >> 12)
        p += size
    return out


def write_inplace(path, data):
    with open(path, "r+b") as f:
        f.seek(0); f.write(data); f.truncate(len(data))


def in_zone_call(d, site):
    b = d[site - CODE_V2F:site - CODE_V2F + 5]
    return b[0] == 0xE8 and ZONE <= site + 5 + struct.unpack_from("<i", b, 1)[0] < ZONE_END


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dll", default=DEFAULT_DLL)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    d = open(a.dll, "rb").read()
    cap_va = ZONE2; cap = build_cap(cap_va); land_va = cap_va + ((len(cap) + 15) & ~15); land = build_land(land_va, cap_va)
    zone2 = cap + bytes(land_va - cap_va - len(cap)) + land
    assert ZONE2 + len(zone2) <= ZONE2_END, hex(ZONE2 + len(zone2))
    land_hook = b"\xe8" + struct.pack("<i", land_va - (LAND_SITE + 5)) + b"\x90"
    hx_va = ZONE; hx = build_hx(hx_va); fly_va = hx_va + ((len(hx) + 3) & ~3); fly = build_fly(fly_va, cap_va)
    zone = hx + bytes(fly_va - hx_va - len(hx)) + fly
    assert ZONE + len(zone) <= ZONE_END, hex(ZONE + len(zone))
    hx_hook = b"\xe8" + struct.pack("<i", hx_va - (HX_SITE + 5))
    fly_hook = b"\xe8" + struct.pack("<i", fly_va - (FLY_SITE + 5)) + b"\x90"
    hb = d[HX_SITE - CODE_V2F:HX_SITE - CODE_V2F + 5]; fb = d[FLY_SITE - CODE_V2F:FLY_SITE - CODE_V2F + 6]
    hstate = "vanilla" if hb == HX_ORIG else "ours" if hb == hx_hook else "OTHER"
    fstate = "vanilla" if fb == FLY_ORIG else "ours" if fb == fly_hook else "OTHER"
    def old_ours(bb, site):   # v3: a call into our own zone from an earlier build (the cave moved) counts as ours
        return bb[0] == 0xE8 and ZONE <= site + 5 + struct.unpack_from("<i", bb, 1)[0] < ZONE_END
    if hstate == "OTHER" and old_ours(hb, HX_SITE): hstate = "ours(old)"
    if fstate == "OTHER" and old_ours(fb, FLY_SITE): fstate = "ours(old)"
    lb = d[LAND_SITE - CODE_V2F:LAND_SITE - CODE_V2F + 6]
    lstate = "vanilla" if lb == LAND_ORIG else "ours" if lb == land_hook else ("ours(old)" if lb[0] == 0xE8 and ZONE2 <= LAND_SITE + 5 + struct.unpack_from("<i", lb, 1)[0] < ZONE2_END else "OTHER")
    z2 = d[ZONE2 - CODE_V2F:ZONE2_END - CODE_V2F]
    z2state = "zero" if not any(z2) else "ours" if z2[:len(zone2)] == zone2 and not any(z2[len(zone2):]) else "DIFFERS"
    v1 = in_zone_call(d, V1_PICK_SITE) or in_zone_call(d, V1_FLY_SITE)
    zl = d[ZONE - CODE_V2F:ZONE_END - CODE_V2F]
    zstate = "zero" if not any(zl) else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else ("v1" if v1 else "DIFFERS")
    rel = reloc_entries(d)
    bad = [hex(v) for v, (q, t) in rel.items() if t == 3 and (ZONE <= v < ZONE_END or HX_SITE <= v < HX_SITE + 5 or FLY_SITE <= v < FLY_SITE + 6 or ZONE2 <= v < ZONE2_END or LAND_SITE <= v < LAND_SITE + 6)]
    print("hx site %s | fly site %s | land site %s | v1 state %s | zone %s (%d B: hx @%#x fly @%#x) | zone2 %s (%d B: cap @%#x land @%#x) | relocs %s" % (
        hstate, fstate, lstate, "APPLIED" if v1 else "absent", zstate, len(zone), hx_va, fly_va, z2state, len(zone2), cap_va, land_va, bad or "none"))
    if bad or "OTHER" in (hstate, fstate, lstate): print("ABORT"); return 1
    if z2state == "DIFFERS" and not lstate.startswith("ours"): print("ABORT: zone2 holds foreign bytes"); return 1
    if a.dis:
        import capstone
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(zone, ZONE): print("   %08X  %-16s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
        print("  -- zone2")
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(zone2, ZONE2): print("   %08X  %-16s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if a.revert:
        out = bytearray(d); out[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
        if hstate.startswith("ours"): out[HX_SITE - CODE_V2F:HX_SITE - CODE_V2F + 5] = HX_ORIG
        if fstate.startswith("ours"): out[FLY_SITE - CODE_V2F:FLY_SITE - CODE_V2F + 6] = FLY_ORIG
        if lstate.startswith("ours"): out[LAND_SITE - CODE_V2F:LAND_SITE - CODE_V2F + 6] = LAND_ORIG
        out[ZONE2 - CODE_V2F:ZONE2_END - CODE_V2F] = bytes(ZONE2_END - ZONE2)
        if v1:
            out[V1_PICK_SITE - CODE_V2F:V1_PICK_SITE - CODE_V2F + 5] = V1_PICK_ORIG
            out[V1_FLY_SITE - CODE_V2F:V1_FLY_SITE - CODE_V2F + 6] = V1_FLY_ORIG
            q, t = rel[V1_RELOC]; struct.pack_into("<H", out, q, (3 << 12) | (V1_RELOC - BASE) & 0xFFF)
        write_inplace(a.dll, bytes(out)); print("reverted (%s)" % ("v1 sites + reloc restored" if v1 else "v2 sites restored")); return 0
    if v1: print("v1 is APPLIED - run --revert first, then --apply"); return 1
    if hstate == "ours" and fstate == "ours" and lstate == "ours" and zstate == "ours" and z2state == "ours": print("already applied"); return 0
    out = bytearray(d); out[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE); out[ZONE - CODE_V2F:ZONE - CODE_V2F + len(zone)] = zone
    out[HX_SITE - CODE_V2F:HX_SITE - CODE_V2F + 5] = hx_hook; out[FLY_SITE - CODE_V2F:FLY_SITE - CODE_V2F + 6] = fly_hook
    out[ZONE2 - CODE_V2F:ZONE2_END - CODE_V2F] = bytes(ZONE2_END - ZONE2); out[ZONE2 - CODE_V2F:ZONE2 - CODE_V2F + len(zone2)] = zone2
    out[LAND_SITE - CODE_V2F:LAND_SITE - CODE_V2F + 6] = land_hook
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(a.dll, BAK_SUFFIX)
    if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    write_inplace(a.dll, bytes(out)); assert open(a.dll, "rb").read() == bytes(out); print("Written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
