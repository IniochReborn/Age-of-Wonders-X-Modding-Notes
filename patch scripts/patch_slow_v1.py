#!/usr/bin/env python3
r"""
SLOW (spell 380, Earth/Water sphere pair 19, tier 1) - the vanilla Slow re-added as a dual-sphere clone, FIXED.
2026-10-15.  The vanilla slot (spell 0x6E, ability 0x84) stays Hunter's Mark (Earth).

VANILLA SLOW (why it "did nothing"):
  * TSlow (CombatSpells, ctor 0x557F8890: id 0x6E, [+0x34] strength 9, [+0x39] range 0x0C) -> TSlowCA:
    Create @0x557F89B3 skips a target that already holds 0x84, rolls strength vs RES (0x55725D98);
    Execute 0x557F8818 -> TAbilityOwner.ExpandAbility(0x84) + GetAbilityData(0x84).[+0x10] enchantment
    SetDuration/SetSource.  Ability 0x84 = TSlowEnchantmentAbility (VMT 0x557B96F8, ctor 0x557B9E78, registered at
    0x557BCAD6..0x557BCAE6), combat-only (its CreateEnchantment override 0x557B9F18 sets [ench+0x14] = 3).
  * The ability itself has NO movement code.  The only reader of 0x84 is TAbstractUnit.CreateMovePointTable
    0x5577FDC4 @0x5577FF8D: GetAbilityEnabled(0x84) -> every terrain cost > 0 gets +2.  That table is the STRATEGIC
    per-terrain cost table; TCPCK rebuilds a copy at selection/path time (TCombatUnitSelectionControl.Update
    0x41FEB8 / CalculateMovePath / TCAI.EvalBattle) but a tactical unit's per-turn allowance is
    TTacticalCombatUnit.NewTurn 0x41CF44: [unit+0x5C] := VMT+0x94 (max move points) - never touched by 0x84.  A +2
    per-terrain bump is not "halving", and in combat it does not reliably reach the move allowance at all - hence
    "slow didn't do anything".  (Hunter's Mark later repointed the ability VMT's GetDefense/GetResistance slots
    0x60/0x64 to `or eax,-1` stubs 0x557B9E6C/0x557B9E70 = -1 DEF/-1 RES; the +2 cost branch is still live for it.)

THE FIX (380 only; Hunter's Mark untouched):
  AoWEPACK zone 0x55820000..0x55822000 (PIC call/pop delta - AoWEPACK rebases):
    reg   0x557BCAE6 (call RegisterAbility for 0x84): replay, then construct a SECOND TSlowEnchantmentAbility
          (ctor 0x557B9E78 via the classref [0x557B96B8]), [+0xC] := 0xB9, name "Slowed", RegisterAbility.
          Same class = same combat-only enchantment machinery (TSlowCA.Execute needs GetAbilityData.[+0x10]).
    sid   0x557F89B3 / 0x557F884F / 0x557F8863 (the three `mov edx, 0x84` in TSlowCA Create/Execute):
          call -> edx := 0xB9 when [ca+0x18] (the spell id) == 380, else 0x84.
    def/res VMT slots 0x557B9758 / 0x557B975C (TSlowEnchantmentAbility +0x60/+0x64, Hunter's Mark -1 stubs):
          -> caves: id 0x84 -> -1 (Hunter's Mark unchanged), anything else -> TAbility base (0).
  AoWTCPCK zone 0x43F000..0x43F040:
    nt    0x41CF7D (TTacticalCombatUnit.NewTurn `mov edx,[ebp-4] / mov [edx+0x5C],eax`): replay, then if the
          strategic unit [unit+0x4C] holds 0xB9 (GetAbilityEnabled VMT+0x148) -> [unit+0x5C] := MP >> 1 (min 1).
          Runs at every turn start of that unit's side, on every peer -> deterministic, MP-safe.  The enemy cast on
          is halved from its next turn (= the whole rest of the combat).
Ability.pfs record 195 (0xB9 + 10) = patch_slow_ability_pfs_v1.py.  Ladder: append 0xB9.
Dry-run default; --apply / --revert / --dis.  Backups .bak_slow (first apply only).
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

EP = game_file("AoWEPACK.dll"); TC = game_file("AoWTCPCK.dll")
EP_BASE, EP_V2F = 0x55700000, 0x55700C00
TC_BASE, TC_V2F = 0x400000, 0x400C00
EZ, EZ_END = 0x55820000, 0x55822000
TZ, TZ_END = 0x43F000, 0x43F040    # 10/15: was 0x43F400 - Soul Siphon fx (patch_tc_soulsiphon_fx_v1.py) lives at 0x43F040
SPELL_ID, SLOWED, OLD_ID, NAME = 380, 0xB9, 0x84, b"Slowed"
REGABIL, LSTRASG = 0x55750238, 0x55701150
SLOW_CLASSREF, SLOW_CTOR = 0x557B96B8, 0x557B9E78
BASE_DEF, BASE_RES = 0x5574E994, 0x5574E998                 # TAbility.GetDefense / GetResistance (xor eax,eax)
HM_DEF, HM_RES = 0x557B9E6C, 0x557B9E70                     # Hunter's Mark: `or eax,-1 / ret`
SLOT_DEF, SLOT_RES = 0x557B96F8 + 0x60, 0x557B96F8 + 0x64
EP_SITES = [   # (name, va, vanilla bytes, kind, target cave)
    ("reg",  0x557BCAE6, bytes.fromhex("e84d37f9ff"), "call", "reg"),
    ("sid1", 0x557F89B3, bytes.fromhex("ba84000000"), "call", "sid"),
    ("sid2", 0x557F884F, bytes.fromhex("ba84000000"), "call", "sid"),
    ("sid3", 0x557F8863, bytes.fromhex("ba84000000"), "call", "sid"),
]
EP_SLOTS = [("def", SLOT_DEF, HM_DEF, BASE_DEF), ("res", SLOT_RES, HM_RES, BASE_RES)]   # (name, slot, HM ptr, vanilla ptr)
TC_SITES = [("nt", 0x41CF7D, bytes.fromhex("8b55fc89425c"), "jmp", "nt")]
NT_BACK = 0x41CF83
THUNKS = {LSTRASG: b"@LStrAsg"}

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


def build_ep():
    out = bytearray(); where = {}
    out += struct.pack("<ii", -1, len(NAME)); where["name"] = EZ + len(out); out += NAME + b"\0"
    def place(name, src):
        while len(out) % 16: out.append(0)
        va = EZ + len(out); where[name] = va; out.extend(asm_pic(src, va))
    # 2026-10-15 v1.1: xor ecx,ecx before the ctor (vanilla passes ecx=0; v1 left RegisterAbility's ecx -> startup Runtime error 216)
    place("reg", """
        call %(reg)#x
        push ebp
        call $D
        pop ebp
        sub ebp, $D
        xor ecx, ecx
        mov dl, 1
        mov eax, dword ptr [ebp + %(cref)#x]
        call %(ctor)#x
        mov dword ptr [eax + 0xc], %(sl)d
        push eax
        lea edx, [ebp + %(name)#x]
        add eax, 8
        call %(lstrasg)#x
        pop edx
        mov eax, ebx
        call %(reg)#x
        pop ebp
        ret
    """ % {"reg": REGABIL, "cref": SLOW_CLASSREF, "ctor": SLOW_CTOR, "sl": SLOWED, "name": where["name"], "lstrasg": LSTRASG})
    place("sid", """
        mov edx, %(old)d
        cmp dword ptr [ebx + 0x18], %(id)d
        jne r
        mov edx, %(sl)d
    r:
        ret
    """ % {"old": OLD_ID, "id": SPELL_ID, "sl": SLOWED})
    place("def", """
        cmp dword ptr [eax + 0xc], %(old)d
        jne b
        or eax, -1
        ret
    b:
        jmp %(base)#x
    """ % {"old": OLD_ID, "base": BASE_DEF})
    place("res", """
        cmp dword ptr [eax + 0xc], %(old)d
        jne b
        or eax, -1
        ret
    b:
        jmp %(base)#x
    """ % {"old": OLD_ID, "base": BASE_RES})
    return bytes(out), where


def build_tc():
    out = bytearray(); where = {}
    where["nt"] = TZ
    out += bytes(ks.asm("""
        mov edx, dword ptr [ebp - 4]
        mov dword ptr [edx + 0x5c], eax
        push eax
        mov eax, dword ptr [edx + 0x4c]
        test eax, eax
        jz done
        mov edx, %(sl)d
        mov ecx, dword ptr [eax]
        call dword ptr [ecx + 0x148]
        test al, al
        jz done
        mov edx, dword ptr [ebp - 4]
        mov eax, dword ptr [edx + 0x5c]
        cmp eax, 1
        jle done
        shr eax, 1
        mov dword ptr [edx + 0x5c], eax
    done:
        pop eax
        jmp %(back)#x
    """ % {"sl": SLOWED, "back": NT_BACK}, TZ)[0])
    return bytes(out), where


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


def check_thunks(d):
    import pefile
    pe = pefile.PE(data=bytes(d), fast_load=True); pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]])
    iat = {}
    for ent in getattr(pe, "DIRECTORY_ENTRY_IMPORT", []):
        for imp in ent.imports: iat[imp.address] = imp.name or b""
    for va, want in THUNKS.items():
        b = d[va - EP_V2F:va - EP_V2F + 6]
        assert b[:2] == b"\xff\x25", "thunk %#x is not jmp [mem]: %s" % (va, b.hex())
        slot = struct.unpack_from("<I", b, 2)[0]
        assert want in iat.get(slot, b""), "thunk %#x -> %r, wanted %r" % (va, iat.get(slot), want)


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


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true"); ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    ed = bytearray(open(EP, "rb").read()); td = bytearray(open(TC, "rb").read())
    check_thunks(ed)
    eblob, ewhere = build_ep(); tblob, twhere = build_tc()
    assert EZ + len(eblob) <= EZ_END and TZ + len(tblob) <= TZ_END
    est, epatch = site_states(ed, EP_V2F, EP_SITES, ewhere, EZ, EZ_END)
    tst, tpatch = site_states(td, TC_V2F, TC_SITES, twhere, TZ, TZ_END)
    slots = {}
    for name, va, hm, van in EP_SLOTS:
        lp = struct.unpack_from("<I", ed, va - EP_V2F)[0]
        slots[name] = "hunters-mark" if lp == hm else "vanilla" if lp == van else "ours" if lp == ewhere[name] else "ours(old)" if EZ <= lp < EZ_END else "OTHER %#x" % lp
    def zstate(d, v2f, z, ze, blob):
        zl = bytes(d[z - v2f:ze - v2f])
        return "zero" if not any(zl) else "ours" if zl[:len(blob)] == blob and not any(zl[len(blob):]) else "DIFFERS"
    ez, tz = zstate(ed, EP_V2F, EZ, EZ_END, eblob), zstate(td, TC_V2F, TZ, TZ_END, tblob)
    erl, trl = reloc_set(bytes(ed), EP_BASE), reloc_set(bytes(td), TC_BASE)
    ebad = [hex(r) for r in erl if EZ - 3 <= r < EZ_END or any(va - 3 <= r < va + len(o) for _n, va, o, _k, _c in EP_SITES)]
    tbad = [hex(r) for r in trl if TZ - 3 <= r < TZ_END or any(va - 3 <= r < va + len(o) for _n, va, o, _k, _c in TC_SITES)]
    slot_relocs = all(va in erl for _n, va, _h, _v in EP_SLOTS)
    print("AoWEPACK: sites %s | slots %s | zone %s (%d B: %s) | relocs %s | slot relocs %s" % (est, slots, ez, len(eblob),
          ", ".join("%s=%#x" % kv for kv in ewhere.items() if kv[0] != "name"), ebad or "none", "ok" if slot_relocs else "MISSING"))
    print("AoWTCPCK: sites %s | zone %s (%d B: nt=%#x) | relocs %s" % (tst, tz, len(tblob), twhere["nt"], tbad or "none"))
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        for nm, blob, z, w in (("EP", eblob, EZ, ewhere), ("TC", tblob, TZ, twhere)):
            for k, va in w.items():
                if k == "name": continue
                print("  --", nm, k)
                for i in md.disasm(blob[va - z:va - z + 0x70], va):
                    print("   %08X  %-18s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
                    if i.mnemonic in ("ret", "jmp") and not i.op_str.startswith("0x5582") and not i.op_str.startswith("0x43f"): break
    if ebad or tbad or not slot_relocs or "OTHER" in est.values() or "OTHER" in tst.values() or any(v.startswith("OTHER") for v in slots.values()):
        print("ABORT (relocs, a foreign hook or a slot not in a known state)"); return 1
    ours_e = any(s.startswith("ours") for s in list(est.values()) + list(slots.values())); ours_t = any(s.startswith("ours") for s in tst.values())
    if (ez == "DIFFERS" and not ours_e) or (tz == "DIFFERS" and not ours_t): print("ABORT (zone not free)"); return 1
    eo, to = bytearray(ed), bytearray(td)
    if a.revert:
        for va, orig, _n in epatch.values(): eo[va - EP_V2F:va - EP_V2F + len(orig)] = orig
        for va, orig, _n in tpatch.values(): to[va - TC_V2F:va - TC_V2F + len(orig)] = orig
        for name, va, hm, _van in EP_SLOTS:                                       # back to Hunter's Mark (the pre-state)
            if slots[name].startswith("ours"): struct.pack_into("<I", eo, va - EP_V2F, hm)
        eo[EZ - EP_V2F:EZ_END - EP_V2F] = bytes(EZ_END - EZ); to[TZ - TC_V2F:TZ_END - TC_V2F] = bytes(TZ_END - TZ)
    else:
        eo[EZ - EP_V2F:EZ_END - EP_V2F] = bytes(EZ_END - EZ); eo[EZ - EP_V2F:EZ - EP_V2F + len(eblob)] = eblob
        to[TZ - TC_V2F:TZ_END - TC_V2F] = bytes(TZ_END - TZ); to[TZ - TC_V2F:TZ - TC_V2F + len(tblob)] = tblob
        for va, _o, new in epatch.values(): eo[va - EP_V2F:va - EP_V2F + len(new)] = new
        for va, _o, new in tpatch.values(): to[va - TC_V2F:va - TC_V2F + len(new)] = new
        for name, va, _hm, _van in EP_SLOTS: struct.pack_into("<I", eo, va - EP_V2F, ewhere[name])
    if eo == ed and to == td: print("already applied" if not a.revert else "already reverted"); return 0
    if not (a.apply or a.revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    for path, old, new in ((EP, ed, eo), (TC, td, to)):
        if old == new: continue
        bak = bak_path(path, ".bak_slow")
        if not os.path.exists(bak): shutil.copy2(path, bak); print("backup ->", bak)
        with open(path, "r+b") as f: f.write(bytes(new))
        assert open(path, "rb").read() == bytes(new); print("%s: %s and verified" % (os.path.basename(path), "reverted" if a.revert else "written"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
