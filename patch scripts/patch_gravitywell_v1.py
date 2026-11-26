#!/usr/bin/env python3
r"""
GRAVITY WELL (spell 366, Earth/Air sphere pair 17, tier 3) - AoWEPACK half: the GROUNDED status 0xB8 + the +50 %
bonus vs airborne units.  v2 2026-10-15 (user round 1 feedback).  The persistent gravity FIELD on the combat map lives
in AoWTCPCK.dll: patch_gravitywell_field_v1.py (apply THIS script first; the field script calls this zone's exports).

User round 1: "grounded display 1/3 days instead of 1/1 days ... grounded doesnt seem to do anything ... grounded
should only apply to units with flying [+ floating + windwalking] ... should no longer make unit lose all movement ...
gravity well persist for a full turn on the combat map, flying units within its AOE get grounded until they leave the
AOE ... a grounded flyer should be able to be hit by tremors".  Coordinator: the +50 % also applies to Floating and
Windwalking (one shared test).

v1 DIAGNOSIS (why Grounded "did nothing"):
  * WRONG ABILITY GROUP.  The movement-type builder 0x5574F764 (table 0x5574F8FC) has bit 0x02 = FLYING = abilities
    1 Flying / 0x3B Floating / 0xA5 Wind Walking and bit 0x04 = the WATER group 2 Swimming / 0x17 Sailing / 0xA4
    Water Walking / 0xA6 Liquid Form.  v1 tested 2/0x17/0xA4/0xA6 and stripped bit 0x04: Grounded removed SWIMMING
    from units that could swim, and the +50 % went to swimmers, not flyers.  (Vortex RE: aowx-vortex-spell.md.)
  * "1/3 days": TDurationAbility's description (VMT+0x58 0x55764E28) prints "<remaining>/<max>" with max =
    VMT+0x110 0x55764D0C = a constant 3 for every plain TDurationAbility, the remaining count = the record's +0xC.
    Mode 3 (combat only) prints the "(combat only)" text instead - v2 registers 0xB8 as mode 3.
  * Webbed-style lock: removed (user).  The CA-execute grant (exe slot): removed - Grounded now comes from the field.

What the movement bit does (all live reads, no cache): TCPCK TCombatUnitSelectionControl.GetMoveTypes 0x41D320 (combat
pathing), the Tremors damage handler (TTacticalCombatUnitHS.MapFieldMsgProc, msg 0x31004 @0x421686: `test al,2 /
jne skip` = flyers immune), the AI move code 0x42958F / 0x42E10B, Sandstorm's x2 (0x43E588), Vortex.  So clearing bit
0x02 while Grounded makes the unit a walker for movement AND lets Tremors hit it - no separate Tremors patch needed.

Zone AoWEPACK 0x5585A000..0x5585C000 (upgrades the applied v1 in place; PIC call/pop delta - AoWEPACK rebases):
  +0x00 EXPORT jmp gw_sync   (eax = TUnit, dl = 1 'stands on a live gravity hex' / 0 'not'): grants 0xB8 to an
        airborne unit on a gravity hex (TAbilityControl.GetAbility(0xB8).Expand, VMT+0xD0), removes it otherwise
        (TAbstractUnit.RemoveAbility 0x5577F6EC); unit.Changed (VMT+0x90) after either.  Called by the TCPCK field
        script through the TCombatUnit.SetUnit import-slot delta.
  +0x08 EXPORT jmp gw_air    (eax = TUnit) -> al = 1 when GetAbilityEnabled (VMT+0x148, item-aware) of 1 Flying,
        0x3B Floating or 0xA5 Wind Walking - natural airborne-ness, so a GROUNDED flyer still counts.
  reg   0x557BCAFD (call RegisterAbility, Webbed's): replay, then register 0xB8 'Grounded' = plain TDurationAbility,
        [+0x24] 4, [+0x28] 3 = COMBAT ONLY (CombatDone 0x55764E00 removes it; the banner shows "(combat only)").
  mt    0x5574F8F6 (movement-type builder epilogue): bit 0x02 set and the owner holds 0xB8 (VMT+0x88) -> clear 0x02,
        set 0x01 (walks).
  dmg   0x55729CA6 (TCombatSpellCA.Setup, before Scald's dice read): [ca+0x18] == 366, target IsClass TCombatUnit,
        gw_air([cu+0x4C]) -> DMG dice += dice >> 1 (2 -> 3).  Creation-time, dice-only = MP-safe.
  pom   0x55784391 (TUnitHS.PlaceOnMap tail `call 0x55772704`, the oil-spring prologue hook at 0x5578436C stays first):
        jmp -> replay the call, then for a tactical unit HS (ClassID 0x220104) gw_sync(unit, field owns a 0x22010C
        gravity HS), then the vanilla `mov al,1 / pop ebx / ret`.
Retired v1 sites (restored to vanilla when they still point into the zone): lock 0x55724BF7, exe slot 0x557F3D18.
Thunks import-table checked: LStrAsg 0x55701150, IsClass 0x557010C0.  Dry-run default; --apply / --revert / --dis.
Backup .bak_gravitywell (first apply only).  Ability.pfs record 194 = patch_gravitywell_ability_pfs_v1.py.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DLL = game_file("AoWEPACK.dll")
BASE, V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x5585A000, 0x5585C000
EXP_SYNC, EXP_AIR = ZONE, ZONE + 8                   # fixed export entries (the TCPCK field script calls these)
SPELL_ID, GROUNDED, NAME = 366, 0xB8, b"Grounded"
AIR_IDS = (1, 0x3B, 0xA5)                            # Flying / Floating / Wind Walking = movement bit 0x02
FIELD_CLASSID, UNITHS_CLASSID = 0x22010C, 0x220104
REGABIL, LSTRASG, ISCLASS = 0x55750238, 0x55701150, 0x557010C0
DUR_VMT, DUR_CREATE, WEB_WORD20 = 0x5571DD68, 0x55764CD4, 0x557BA314
TCU_CLASSREF = 0x55715A54
REGISTRY, GETABIL, REMOVEABIL = 0x558E92E8, 0x557501C0, 0x5577F6EC
POM_CALL, POM_TAIL = 0x55772704, 0x55784396
CA_EXEC = 0x557F6A20
SITES = [   # (name, va, vanilla bytes, kind)
    ("reg",  0x557BCAFD, bytes.fromhex("e83637f9ff"), "call"),
    ("mt",   0x5574F8F6, bytes.fromhex("8bc35e5bc3"), "jmp"),
    ("dmg",  0x55729CA6, bytes.fromhex("8b45fc8a400c"), "call"),
    ("pom",  0x55784391, bytes.fromhex("e86ee3feff"), "jmp"),
]
RETIRED = [("lock", 0x55724BF7, bytes.fromhex("ba22000000"))]          # v1: Webbed-style lock
RETIRED_SLOTS = [("exe", 0x557F3D18, CA_EXEC)]                         # v1: TCombatSpellCA.Execute grant
THUNKS = {LSTRASG: b"@LStrAsg", ISCLASS: b"@IsClass"}

ks = Ks(KS_ARCH_X86, KS_MODE_32)
ANCHOR = bytes.fromhex("e8000000005d81edffffff7f")      # call $D / pop ebp / sub ebp, $D


def asm_pic(src, va):
    s1 = src.replace("call $D", ".byte 0xe8, 0, 0, 0, 0").replace("sub ebp, $D", "sub ebp, 0x7fffffff")
    b = bytearray(ks.asm(s1, va)[0]); k = 0; n = 0
    while True:
        k = b.find(ANCHOR, k)
        if k < 0: break
        struct.pack_into("<I", b, k + 8, va + k + 5); k += len(ANCHOR); n += 1
    assert n == src.count("call $D"), "delta anchors %d of %d" % (n, src.count("call $D"))
    return bytes(b)


def build(d):
    out = bytearray(16); where = {}                   # +0 / +8: the export jmps, patched in at the end
    out += struct.pack("<ii", -1, len(NAME)); where["name"] = ZONE + len(out); out += NAME + b"\0"
    def place(name, src):
        while len(out) % 16: out.append(0)
        va = ZONE + len(out); where[name] = va; out.extend(asm_pic(src, va))
    w20 = struct.unpack_from("<H", d, WEB_WORD20 - V2F)[0]
    # reg: replay Webbed's RegisterAbility, then register 0xB8 'Grounded' (plain TDurationAbility, mode 3 = combat only)
    place("reg", """
        call %(reg)#x
        push ebp
        call $D
        pop ebp
        sub ebp, $D
        lea eax, [ebp + %(vmt)#x]
        xor ecx, ecx
        mov dl, 1
        call %(create)#x
        mov dword ptr [eax + 0xc], %(gr)d
        mov byte ptr [eax + 0x24], 4
        mov byte ptr [eax + 0x28], 3
        mov word ptr [eax + 0x20], %(w20)d
        push eax
        lea edx, [ebp + %(name)#x]
        add eax, 8
        call %(lstrasg)#x
        pop edx
        mov eax, ebx
        call %(reg)#x
        pop ebp
        ret
    """ % {"reg": REGABIL, "vmt": DUR_VMT, "create": DUR_CREATE, "gr": GROUNDED, "w20": w20, "name": where["name"], "lstrasg": LSTRASG})
    # gw_air(eax = TUnit) -> al: GetAbilityEnabled of Flying / Floating / Wind Walking (ecx, edx clobbered)
    air = "\n".join("""
        mov edx, %d
        mov eax, ebx
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x148]
        test al, al
        jnz a_yes""" % i for i in AIR_IDS)
    place("air", """
        push ebx
        mov ebx, eax
        test ebx, ebx
        jz a_no
""" + air + """
    a_no:
        xor eax, eax
        pop ebx
        ret
    a_yes:
        mov al, 1
        pop ebx
        ret
    """)
    # gw_sync(eax = TUnit, dl = on a gravity hex): grant / remove 0xB8; all registers but eax preserved
    place("sync", """
        push ebx
        push ecx
        push edx
        push esi
        push edi
        mov esi, eax
        mov bl, dl
        test esi, esi
        jz s_out
        test bl, bl
        jz s_off
        mov eax, esi
        call %(air)#x
        test al, al
        jz s_off
        mov eax, esi
        mov edx, %(gr)d
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x148]
        test al, al
        jnz s_out
        push ebp
        call $D
        pop ebp
        sub ebp, $D
        mov eax, dword ptr [ebp + %(registry)#x]
        pop ebp
        mov eax, dword ptr [eax]
        mov eax, dword ptr [eax + 0x80]
        mov edx, %(gr)d
        call %(getabil)#x
        test eax, eax
        jz s_out
        mov edx, esi
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0xd0]
        jmp s_changed
    s_off:
        mov eax, esi
        mov edx, %(gr)d
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x148]
        test al, al
        jz s_out
        mov eax, esi
        mov edx, %(gr)d
        call %(removeabil)#x
    s_changed:
        mov eax, esi
        mov edx, dword ptr [eax]
        call dword ptr [edx + 0x90]
    s_out:
        pop edi
        pop esi
        pop edx
        pop ecx
        pop ebx
        ret
    """ % {"air": where["air"], "gr": GROUNDED, "registry": REGISTRY, "getabil": GETABIL, "removeabil": REMOVEABIL})
    # mt: movement-type builder epilogue (bl = types, esi = ability owner; eax/ecx/edx free)
    place("mt", """
        test bl, 2
        jz m_out
        mov edx, %(gr)d
        mov eax, esi
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x88]
        test al, al
        jz m_out
        and bl, 0xfd
        or bl, 1
    m_out:
        mov eax, ebx
        pop esi
        pop ebx
        ret
    """ % {"gr": GROUNDED})
    # dmg: Setup (ebx = CA, esi = target, [ebp+0x10] = DMG dice arg); eax/ecx/edx free (reloaded before use)
    place("dmg", """
        cmp dword ptr [ebx + 0x18], %(id)d
        jne g_replay
        test esi, esi
        jz g_replay
        push ebp
        call $D
        pop ebp
        sub ebp, $D
        mov eax, esi
        mov edx, dword ptr [ebp + %(tcu)#x]
        call %(isclass)#x
        pop ebp
        test al, al
        jz g_replay
        mov eax, dword ptr [esi + 0x4c]
        call %(air)#x
        test al, al
        jz g_replay
        movzx eax, byte ptr [ebp + 0x10]
        mov ecx, eax
        shr ecx, 1
        add eax, ecx
        mov byte ptr [ebp + 0x10], al
    g_replay:
        mov eax, dword ptr [ebp - 4]
        mov al, byte ptr [eax + 0xc]
        ret
    """ % {"id": SPELL_ID, "tcu": TCU_CLASSREF, "isclass": ISCLASS, "air": where["air"]})
    # pom: TUnitHS.PlaceOnMap tail (ebx = hs, [esp] = the two stack args of 0x55772704 already pushed)
    place("pom", """
        call %(pomcall)#x
        pushal
        mov eax, ebx
        mov edx, dword ptr [eax]
        call dword ptr [edx + 0x24]
        cmp eax, %(unitcls)#x
        jne p_out
        mov eax, dword ptr [ebx + 0x1c]
        test eax, eax
        jz p_out
        mov esi, dword ptr [eax + 0x4c]
        test esi, esi
        jz p_out
        xor edi, edi
        mov eax, dword ptr [ebx + 4]
        test eax, eax
        jz p_sync
        mov edx, %(fieldcls)#x
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x80]
        test eax, eax
        setnz al
        movzx edi, al
    p_sync:
        mov eax, esi
        mov edx, edi
        call %(sync)#x
    p_out:
        popal
        mov al, 1
        pop ebx
        ret
    """ % {"pomcall": POM_CALL, "unitcls": UNITHS_CLASSID, "fieldcls": FIELD_CLASSID, "sync": where["sync"]})
    for k, (va, tgt) in enumerate(((EXP_SYNC, where["sync"]), (EXP_AIR, where["air"]))):
        out[k * 8:k * 8 + 5] = b"\xe9" + struct.pack("<i", tgt - (va + 5))
    return bytes(out), where


def pe_info(d):
    pe = struct.unpack_from("<I", d, 0x3C)[0]; opt = struct.unpack_from("<H", d, pe + 20)[0]; nsec = struct.unpack_from("<H", d, pe + 6)[0]
    secs = [struct.unpack_from("<IIII", d, pe + 24 + opt + 40 * k + 8) for k in range(nsec)]
    def r2f(rva):
        for vs, va, rs, ro in secs:
            if va <= rva < va + max(vs, rs): return ro + rva - va
    return pe, r2f


def reloc_set(d):
    pe, r2f = pe_info(d)
    rrva, rsz = struct.unpack_from("<II", d, pe + 24 + 0x88)
    p = r2f(rrva); end = p + rsz; out = set()
    while p < end:
        page, size = struct.unpack_from("<II", d, p)
        if size < 8: break
        for q in range(p + 8, p + size, 2):
            e = struct.unpack_from("<H", d, q)[0]
            if e >> 12 == 3: out.add(BASE + page + (e & 0xFFF))
        p += size
    return out


def check_thunks(d):
    """Each thunk VA must be `jmp [IAT]` whose import name contains the expected symbol."""
    import pefile
    pe = pefile.PE(data=bytes(d), fast_load=True); pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]])
    iat = {}
    for ent in getattr(pe, "DIRECTORY_ENTRY_IMPORT", []):
        for imp in ent.imports: iat[imp.address] = imp.name or b""
    for va, want in THUNKS.items():
        b = d[va - V2F:va - V2F + 6]
        assert b[:2] == b"\xff\x25", "thunk %#x is not jmp [mem]: %s" % (va, b.hex())
        slot = struct.unpack_from("<I", b, 2)[0]
        assert want in iat.get(slot, b""), "thunk %#x -> %r, wanted %r" % (va, iat.get(slot), want)


def plan(dis):
    d = bytearray(open(DLL, "rb").read())
    check_thunks(d)
    blob, where = build(bytes(d)); assert ZONE + len(blob) <= ZONE_END, hex(ZONE + len(blob))
    states, patched = {}, {}
    for name, va, orig, kind in SITES:
        op = b"\xe8" if kind == "call" else b"\xe9"
        new = op + struct.pack("<i", where[name] - (va + 5)) + b"\x90" * (len(orig) - 5); patched[name] = (va, orig, new)
        live = bytes(d[va - V2F:va - V2F + len(orig)])
        if live == orig: states[name] = "vanilla"
        elif live == new: states[name] = "ours"
        elif live[0] in (0xE8, 0xE9) and ZONE <= va + 5 + struct.unpack_from("<i", live, 1)[0] < ZONE_END: states[name] = "ours(old)"
        else: states[name] = "OTHER"
    restore = {}                                                   # retired v1 sites -> vanilla
    for name, va, orig in RETIRED:
        live = bytes(d[va - V2F:va - V2F + len(orig)])
        if live == orig: states["retired:" + name] = "vanilla"
        elif live[0] in (0xE8, 0xE9) and ZONE <= va + 5 + struct.unpack_from("<i", live, 1)[0] < ZONE_END:
            states["retired:" + name] = "ours(v1)"; restore[name] = (va, orig)
        else: states["retired:" + name] = "OTHER"
    for name, va, orig_ptr in RETIRED_SLOTS:
        live = bytes(d[va - V2F:va - V2F + 4]); lp = struct.unpack("<I", live)[0]
        if lp == orig_ptr: states["retired:" + name] = "vanilla"
        elif ZONE <= lp < ZONE_END: states["retired:" + name] = "ours(v1)"; restore[name] = (va, struct.pack("<I", orig_ptr))
        else: states["retired:" + name] = "OTHER"
    zl = bytes(d[ZONE - V2F:ZONE_END - V2F])
    zstate = "zero" if not any(zl) else "ours" if zl[:len(blob)] == blob and not any(zl[len(blob):]) else "DIFFERS"
    rl = reloc_set(bytes(d))
    bad = [hex(r) for r in rl if ZONE - 3 <= r < ZONE_END or any(va - 3 <= r < va + len(o) for _n, va, o, _k in SITES)
           or any(va - 3 <= r < va + len(o) for _n, va, o in RETIRED)]
    slot_ok = all(va in rl for _n, va, _p in RETIRED_SLOTS)        # the VMT slot keeps its own reloc
    print("AoWEPACK: sites %s | zone %s (%d B: %s) | relocs in sites/zone %s | slot relocs %s" % (states, zstate, len(blob),
          ", ".join("%s=%#x" % kv for kv in where.items() if kv[0] != "name"), bad or "none", "ok" if slot_ok else "MISSING"))
    print("exports: gw_sync %#x -> %#x, gw_air %#x -> %#x" % (EXP_SYNC, where["sync"], EXP_AIR, where["air"]))
    if dis:
        import capstone
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(blob[where["reg"] - ZONE:], where["reg"]):
            print("   %08X  %-18s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    return d, blob, states, patched, restore, zstate, bad, slot_ok


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true"); ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    d, blob, states, patched, restore, zstate, bad, slot_ok = plan(a.dis)
    if bad or not slot_ok or "OTHER" in states.values(): print("ABORT (relocs, a foreign hook or a missing slot reloc)"); return 1
    if zstate == "DIFFERS" and not any(s.startswith("ours") for s in states.values()): print("ABORT (zone not free)"); return 1
    out = bytearray(d)
    for va, orig in restore.values(): out[va - V2F:va - V2F + len(orig)] = orig        # retire v1 sites either way
    if a.revert:
        for va, orig, _new in patched.values(): out[va - V2F:va - V2F + len(orig)] = orig
        out[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE)
    else:
        out[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE); out[ZONE - V2F:ZONE - V2F + len(blob)] = blob
        for va, _orig, new in patched.values(): out[va - V2F:va - V2F + len(new)] = new
    if out == d: print("already applied" if not a.revert else "already vanilla"); return 0
    if not (a.apply or a.revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(DLL, ".bak_gravitywell")
    if not os.path.exists(bak): shutil.copy2(DLL, bak); print("backup ->", bak)
    with open(DLL, "r+b") as f: f.write(bytes(out))
    assert open(DLL, "rb").read() == bytes(out); print("AoWEPACK: %s and verified" % ("reverted" if a.revert else "written"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
