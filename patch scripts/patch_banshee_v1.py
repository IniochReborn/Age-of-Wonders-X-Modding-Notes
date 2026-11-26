"""
BANSHEE GALE (spell 344, Air/Death tier 1) - 2026-10-15.  AoWTCPCK.dll + AoWEPACK.dll.

Spec (user): combat spell, long range, LARGE AoE; 7 ATK / 1 DMG Death|Physical; displaces the units in the area like
Winds of Fury but not as far; inflicts Panicked.

Vanilla Winds of Fury (RE 2026-10-15):
  AoWEPACK TWindsOfFury (cell 0x557F62A0, Create 0x557F9E00, registered @0x557FA808): id 0x7E (126), pfs key 136;
  param block ATK 8 / DMG 3 / types 0x80 Physical / 1 shot / range 0xFF; only VMT override = CreateCA 0x557F9EB8
  (a plain TCombatSpellCA via Setup [ca VMT+0x68]; +2 ATK if the target has Flying (1) or 0x3B).
  AoWTCPCK: SpellTypes[0x7E] = 0x2F.  NextStrike class 0x2F case 0x40D935: the strike effect's unit [fx+0x2C] = the
  unit HS on the TE target hex [te+0x20]/[te+0x22]; destination = the first free, in-bounds, same-level, non-water/
  non-lava hex walking the spiral index idx = Random(0x25)+1, idx+1, ... (CenterHNtoHX 0x4022AC: HN 1..6 = ring 1,
  7..18 ring 2, 19..36 ring 3) => Winds throws up to 3 hexes; a jittered 30-point path to it.  The kind-0x2F effect
  (NewFrame 0x42BC69) carries the unit HS along the path and, at path end, moves it there (unit HS VMT+0x10C); cue 0
  at launch, cue 1 at landing.  Damage = the generic strike landing @0x40C31F (GetSpell(id).CreateCA -> execute).

344 = a Winds of Fury clone (pipeline donor TWindsOfFury, tc_type 0x2F) + this script:
TCPCK (all keyed on [te+0x18] == 344; te = [ebp-4] in NextStrike):
  TG  0x40D935 (class-0x2F case entry, 7 B) -> jmp cave: on strike 0 ([te+0x34] == 0) enumerate the 19 hexes HN 0..18
      around the target (Ooze-sized area), list every unit HS on them except the caster, set the strike count
      [te+0x28] = n (1 if empty); every strike k then retargets [te+0x20]/[te+0x22] to list[k] -> each unit in the
      area is thrown once.  Replays the 3 instructions, back to 0x40D93C.
  RN  0x40D9DF (`mov edx,0x25`, 5 B) -> jmp cave: Random(PUSH_N)+1 for 344 (PUSH_N 18 = ring 1-2, i.e. 1-2 hexes;
      Winds' 37 = up to 3).
  OC  0x40DA6E (`test eax,eax / jne 0x40DBF8`, 8 B) -> jmp cave: also rejects a hex already chosen as a landing hex
      by an earlier 344 strike of this cast (units still in flight have not moved yet, so two could pick one hex).
  RC  0x40DC0D (loop exit, 7 B) -> jmp cave: records the chosen landing hex; replays, back to 0x40DC14.
  Data: DATA-page slack 0x46B870..0x46B8D8 (between the Harvest latch 0x46B860 and Ashes' queue 0x46B900), accessed
  via the call/pop delta (the DLL is relocated).  Deterministic: no RNG draws added or removed in TCPCK.
AoWEPACK:
  CR  0x557F9F4E (TWindsOfFury.CreateCA epilogue `mov eax,esi / pop edi / pop esi / pop ebx`, 5 B) -> jmp cave: for
      344, if the rolled damage [ca+0x10] > 0 and the target CU (UnitById([[caster+8]+0xC], [ca+0xE])) is not
      already Panicked (0x6C), not Fearless (0x43) / Lionheart (0xB1), not CU VMT+0x7C bit 0x20, not a machine
      (TUnit VMT+0x114 == 2) -> Chance(PANIC_STR - RES (CU VMT+0x74)) [Chance 0x55725D98 = clamp(50+10d,10,90) %, the
      combat RNG, at CA creation like Terror / Thousand Threads] -> success sets bit 0x80 in the effects word
      [ca+0x13] (serialized; ExecuteDamageEffectsRole never produces 0x80 - Physical has no vanilla effect, and the TC
      effect display 0x407C30 ignores 0x80).
  EX  0x5578202F (TAbstractUnit.ExecuteCombatDamageEffects epilogue `mov eax,edi / pop edx / pop ebp / pop edi`,
      5 B; reached from TDamageCA execute via CU VMT+0x128) -> jmp cave: bit 0x80 in bx (= mask & ~immunities) ->
      unit VMT+0x94 ExpandAbility(0x6C Panicked); then the epilogue.  Generic (the bit is only ever set by CR).
Zones: TCPCK 0x43F800..0x43FB00, AoWEPACK 0x55866800..0x55866A00 (zero, reloc-free; verified on apply).
Backups <game>\\backup\\<dll>.bak_banshee.  Dry-run default; --apply / --revert / --dis.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

SPELL_ID = 344
AOE_HEXES = 19            # HN 0..18 = centre + 2 rings (Ooze-sized)
PUSH_N = 18               # Random(PUSH_N)+1 spiral start: 1..18 = 1-2 hexes (Winds: 37 = up to 3)
PANIC_STR = 6             # Chance(PANIC_STR - RES): RES 3 -> 80 %, 5 -> 60 %, 7 -> 40 %, >= 10 -> 10 %
MAXN = 19

ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, va):
    return bytes(ks.asm(src, va)[0])


def asm_delta(src, va):
    """`call $D / pop ebx / sub ebx, $D` -> ebx = load delta (actual - preferred)."""
    s1 = src.replace("call $D", ".byte 0xe8, 0, 0, 0, 0").replace("sub ebx, $D", "sub ebx, 0x7fffffff")
    b = bytearray(ks.asm(s1, va)[0])
    k = b.find(bytes.fromhex("e8000000005b81ebffffff7f"))
    assert k >= 0, "delta anchor not found"
    struct.pack_into("<I", b, k + 8, va + k + 5)
    return bytes(b)


# ------------------------------------------------------------------------------------------------ TCPCK
TC = dict(dll=game_file("AoWTCPCK.dll"), base=0x400000, v2f=0x400C00, zone=(0x43F800, 0x43FB00),
          sites={"TG": (0x40D935, bytes.fromhex("8d45c8508d4dcc")),
                 "RN": (0x40D9DF, bytes.fromhex("ba25000000")),
                 "OC": (0x40DA6E, bytes.fromhex("85c00f8582010000")),
                 "RC": (0x40DC0D, bytes.fromhex("8d45c0508d4dc4"))},
          scan=(0x40CD20, 0x40F500))
MAPLIST, GETLEVEL, GETFIELD, CNHX, UNITCLS = 0x469420, 0x401E64, 0x401E54, 0x4022AC, 0x220104
G_TE, G_CX, G_CY, G_N, G_HN, G_RN, G_LIST, G_RES = 0x46B870, 0x46B874, 0x46B878, 0x46B87C, 0x46B880, 0x46B884, 0x46B888, 0x46B8B0
assert G_LIST + 2 * MAXN <= G_RES and G_RES + 2 * MAXN <= 0x46B8D8 < 0x46B900


def build_tc():
    v = dict(id=SPELL_ID, maplist=MAPLIST, getlevel=GETLEVEL, getfield=GETFIELD, cnhx=CNHX, unitcls=UNITCLS,
             gte=G_TE, gcx=G_CX, gcy=G_CY, gn=G_N, ghn=G_HN, grn=G_RN, glist=G_LIST, gres=G_RES, nhex=AOE_HEXES,
             maxn=MAXN, pushn=PUSH_N)
    srcs = {
        "tg": """
            pushal
            call $D
            pop ebx
            sub ebx, $D
            mov eax, [ebp-4]
            cmp dword ptr [eax+0x18], %(id)d
            jne tg_out
            cmp dword ptr [eax+0x34], 0
            jne tg_use
            mov [ebx+%(gte)#x], eax
            movzx ecx, word ptr [eax+0x20]
            mov [ebx+%(gcx)#x], ecx
            movzx ecx, word ptr [eax+0x22]
            mov [ebx+%(gcy)#x], ecx
            mov dword ptr [ebx+%(gn)#x], 0
            mov dword ptr [ebx+%(grn)#x], 0
            mov eax, [ebx+%(maplist)#x]
            mov eax, [eax]
            mov eax, [eax+0x10]
            xor edx, edx
            call %(getlevel)#x
            mov esi, eax
            sub esp, 8
            xor edi, edi
            mov dword ptr [ebx+%(ghn)#x], 0
        tg_hn:
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
            js tg_no
            test ecx, ecx
            js tg_no
            cmp edx, [esi+0xc]
            jge tg_no
            cmp ecx, [esi+0x10]
            jge tg_no
            mov eax, esi
            call %(getfield)#x
            test eax, eax
            jz tg_no
            mov edx, %(unitcls)#x
            mov ecx, [eax]
            call dword ptr [ecx+0x80]
            test eax, eax
            jz tg_no
            mov eax, [eax+0x1c]
            mov edx, [ebp-4]
            cmp eax, [edx+0x10]
            je tg_no
            cmp edi, %(maxn)d
            jae tg_no
            mov eax, [esp+4]
            shl eax, 8
            or eax, [esp]
            mov word ptr [ebx+edi*2+%(glist)#x], ax
            inc edi
        tg_no:
            inc dword ptr [ebx+%(ghn)#x]
            cmp dword ptr [ebx+%(ghn)#x], %(nhex)d
            jb tg_hn
            add esp, 8
            mov [ebx+%(gn)#x], edi
            mov eax, [ebp-4]
            mov ecx, edi
            test ecx, ecx
            jnz tg_setn
            mov ecx, 1
        tg_setn:
            mov [eax+0x28], ecx
        tg_use:
            mov eax, [ebp-4]
            cmp [ebx+%(gte)#x], eax
            jne tg_out
            mov edi, [ebx+%(gn)#x]
            mov ecx, [eax+0x34]
            cmp ecx, edi
            jae tg_out
            movzx edx, word ptr [ebx+ecx*2+%(glist)#x]
            movzx ecx, dl
            mov word ptr [eax+0x20], cx
            shr edx, 8
            mov word ptr [eax+0x22], dx
        tg_out:
            popal
            lea eax, [ebp-0x38]
            push eax
            lea ecx, [ebp-0x34]
            jmp 0x40D93C
        """,
        "rn": """
            mov edx, 0x25
            push ecx
            mov ecx, [ebp-4]
            cmp dword ptr [ecx+0x18], %(id)d
            jne rn_out
            mov edx, %(pushn)d
        rn_out:
            pop ecx
            jmp 0x40D9E4
        """,
        "oc": """
            test eax, eax
            jnz oc_bad
            pushal
            mov eax, [ebp-4]
            cmp dword ptr [eax+0x18], %(id)d
            jne oc_ok
            call $D
            pop ebx
            sub ebx, $D
            cmp [ebx+%(gte)#x], eax
            jne oc_ok
            mov eax, [ebp-0x4c]
            shl eax, 8
            or eax, [ebp-0x48]
            mov ecx, [ebx+%(grn)#x]
        oc_lp:
            test ecx, ecx
            jz oc_ok
            dec ecx
            cmp ax, word ptr [ebx+ecx*2+%(gres)#x]
            jne oc_lp
            popal
        oc_bad:
            jmp 0x40DBF8
        oc_ok:
            popal
            jmp 0x40DA76
        """,
        "rc": """
            pushal
            mov eax, [ebp-4]
            cmp dword ptr [eax+0x18], %(id)d
            jne rc_out
            call $D
            pop ebx
            sub ebx, $D
            cmp [ebx+%(gte)#x], eax
            jne rc_out
            mov ecx, [ebx+%(grn)#x]
            cmp ecx, %(maxn)d
            jae rc_out
            mov eax, [ebp-0x4c]
            shl eax, 8
            or eax, [ebp-0x48]
            mov word ptr [ebx+ecx*2+%(gres)#x], ax
            inc dword ptr [ebx+%(grn)#x]
        rc_out:
            popal
            lea eax, [ebp-0x40]
            push eax
            lea ecx, [ebp-0x3c]
            jmp 0x40DC14
        """,
    }
    return srcs, v, {"TG": "tg", "RN": "rn", "OC": "oc", "RC": "rc"}


# ------------------------------------------------------------------------------------------------ AoWEPACK
EP = dict(dll=game_file("AoWEPACK.dll"), base=0x55700000, v2f=0x55700C00, zone=(0x55866800, 0x55866A00),
          sites={"CR": (0x557F9F4E, bytes.fromhex("8bc65f5e5b")),
                 "EX": (0x5578202F, bytes.fromhex("8bc75a5d5f"))},
          scan=(0x557F9EB8, 0x557F9F58))
UNIT_BY_ID, CHANCE, PANICKED, FEARLESS, LIONHEART = 0x55728C68, 0x55725D98, 0x6C, 0x43, 0xB1


def build_ep():
    v = dict(id=SPELL_ID, ub=UNIT_BY_ID, ch=CHANCE, pan=PANICKED, fl=FEARLESS, lh=LIONHEART, str=PANIC_STR)
    srcs = {
        "cr": """
            cmp dword ptr [ebx+0x10], %(id)d
            jne cr_tail
            cmp byte ptr [esi+0x10], 0
            je cr_tail
            pushal
            mov eax, [ebp-4]
            mov eax, [eax+8]
            mov eax, [eax+0xc]
            movzx edx, byte ptr [esi+0xe]
            call %(ub)#x
            test eax, eax
            jz cr_done
            mov ebx, eax
            mov edx, %(pan)d
            mov ecx, [eax]
            call dword ptr [ecx+0xa8]
            test al, al
            jnz cr_done
            mov edx, %(fl)d
            mov eax, ebx
            mov ecx, [eax]
            call dword ptr [ecx+0xa8]
            test al, al
            jnz cr_done
            mov edx, %(lh)d
            mov eax, ebx
            mov ecx, [eax]
            call dword ptr [ecx+0xa8]
            test al, al
            jnz cr_done
            mov eax, ebx
            mov edx, [eax]
            call dword ptr [edx+0x7c]
            test al, 0x20
            jnz cr_done
            mov eax, [ebx+0x4c]
            test eax, eax
            jz cr_done
            mov edx, [eax]
            call dword ptr [edx+0x114]
            cmp al, 2
            je cr_done
            mov eax, ebx
            mov edx, [eax]
            call dword ptr [edx+0x74]
            movsx edx, al
            mov eax, %(str)d
            sub eax, edx
            call %(ch)#x
            test al, al
            jz cr_done
            mov eax, [esp+4]
            or byte ptr [eax+0x13], 0x80
        cr_done:
            popal
        cr_tail:
            mov eax, esi
            pop edi
            pop esi
            pop ebx
            pop ecx
            pop ebp
            ret 4
        """,
        "ex": """
            test bl, 0x80
            jz ex_tail
            mov edx, %(pan)d
            mov eax, esi
            mov ecx, [eax]
            call dword ptr [ecx+0x94]
        ex_tail:
            mov eax, edi
            pop edx
            pop ebp
            pop edi
            pop esi
            pop ebx
            ret
        """,
    }
    return srcs, v, {"CR": "cr", "EX": "ex"}


def reloc_set(d, base):
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
            if e >> 12 == 3: out.add(base + page + (e & 0xFFF))
        p += size
    return out


def branch_into(d, part):
    """Any rel branch inside part['scan'] landing strictly INSIDE a patched site (not at its first byte)?"""
    import capstone
    lo, hi = part["scan"]; v2f = part["v2f"]
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    inner = [(va + 1, va + len(o)) for va, o in part["sites"].values()]
    bad = []
    for i in md.disasm(bytes(d[lo - v2f:hi - v2f]), lo):
        if i.mnemonic.startswith("j") or i.mnemonic == "call":
            try: t = int(i.op_str, 16)
            except ValueError: continue
            if any(a <= t < b for a, b in inner): bad.append("%#x->%#x" % (i.address, t))
    return bad


def do_part(name, part, builder, a):
    d = bytearray(open(part["dll"], "rb").read())
    ZONE, ZONE_END = part["zone"]; v2f = part["v2f"]
    srcs, v, site_cave = builder()
    out, caves = bytearray(), {}
    for cname in srcs:
        va = ZONE + len(out); src = srcs[cname] % v
        code = asm_delta(src, va) if "$D" in src else asm(src, va)
        out += code; caves[cname] = va
        while len(out) % 16: out.append(0)
    zone = bytes(out).rstrip(b"\x00")
    assert ZONE + len(zone) <= ZONE_END, hex(ZONE + len(zone))
    hooks = {k: b"\xe9" + struct.pack("<i", caves[site_cave[k]] - (va + 5)) + b"\x90" * (len(orig) - 5)
             for k, (va, orig) in part["sites"].items()}
    zl = bytes(d[ZONE - v2f:ZONE_END - v2f])
    zstate = "zero" if not any(zl) else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else "DIFFERS"
    states = {}
    for k, (va, orig) in part["sites"].items():
        live = bytes(d[va - v2f:va - v2f + len(orig)])
        if live == orig: states[k] = "vanilla"
        elif live == hooks[k]: states[k] = "ours"
        elif live[0] == 0xE9 and ZONE <= va + 5 + struct.unpack_from("<i", live, 1)[0] < ZONE_END: states[k] = "ours(old)"
        else: states[k] = "OTHER"
    rl = reloc_set(bytes(d), part["base"])
    bad = [hex(r) for r in rl if ZONE - 3 <= r < ZONE_END or any(va - 3 <= r < va + len(o) for va, o in part["sites"].values())]
    into = branch_into(d, part)
    print("%s: sites %s | zone %s (%d B: %s) | relocs %s | branches into sites %s"
          % (name, states, zstate, len(zone), ", ".join("%s @%#x" % kv for kv in caves.items()), bad or "none", into or "none"))
    if a.dis:
        import capstone
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(zone, ZONE): print("   %08X  %-24s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad or into or "OTHER" in states.values(): print("%s: ABORT" % name); return None
    if zstate == "DIFFERS" and not any(s.startswith("ours") for s in states.values()): print("%s: ABORT (zone not free)" % name); return None
    if a.revert:
        for k, (va, orig) in part["sites"].items(): d[va - v2f:va - v2f + len(orig)] = orig
        d[ZONE - v2f:ZONE_END - v2f] = bytes(ZONE_END - ZONE)
        return d, "revert"
    if all(s == "ours" for s in states.values()) and zstate == "ours": return d, "same"
    d[ZONE - v2f:ZONE_END - v2f] = bytes(ZONE_END - ZONE); d[ZONE - v2f:ZONE - v2f + len(zone)] = zone
    for k, (va, orig) in part["sites"].items(): d[va - v2f:va - v2f + len(orig)] = hooks[k]
    return d, "apply"


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true"); ap.add_argument("--tc-dll"); ap.add_argument("--ep-dll"); a = ap.parse_args()
    if a.tc_dll: TC["dll"] = a.tc_dll
    if a.ep_dll: EP["dll"] = a.ep_dll
    res = [("AoWTCPCK", TC, do_part("AoWTCPCK", TC, build_tc, a)), ("AoWEPACK", EP, do_part("AoWEPACK", EP, build_ep, a))]
    if any(r is None for _n, _p, r in res): print("ABORT - nothing written"); return 1
    if all(r[1] == "same" for _n, _p, r in res) and not a.revert: print("already applied"); return 0
    if not (a.apply or a.revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    for name, part, (d, mode) in res:
        if mode == "same": continue
        bak = bak_path(part["dll"], ".bak_banshee")
        if not os.path.exists(bak): shutil.copy2(part["dll"], bak); print("backup ->", bak)
        with open(part["dll"], "r+b") as f: f.write(bytes(d))
        assert open(part["dll"], "rb").read() == bytes(d)
        print("%s: %s written and verified" % (name, "reverted" if mode == "revert" else "patch"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
