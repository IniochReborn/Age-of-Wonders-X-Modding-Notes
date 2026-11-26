#!/usr/bin/env python3
r"""
BLOOD BOIL (spell 404, Fire/Water sphere pair 22, tier 1) - behaviour caves (2026-10-14).  AoWEPACK.dll + AoWTCPCK.dll.

Spec (user): combat spell, long range, single target, bypasses obstructions; 7 ATK / 4 DMG physical; grants Bloodlust;
can't target machines.  The spell object is a TVaporize clone (class 7 = direct single target: no projectile, no LOS)
registered by patch_dual_sphere_spells_v1.py.  NO alias entry is needed: Vaporize (id 0x79 = 121) takes the DEFAULT
case of every id-keyed TC switch (NextStrike table @0x40F0E3: index 21 -> 0x40F227 = default; preview 0x42827A: none;
0x40B541 / 0x40C8D0 are hail-class only) and no TC/exe code compares against 0x79.

RE:
  * Hit = TCombatSpell.CreateCA 0x557F72C0 (TVaporize VMT 0x557F5A9C +0x78; shared with Great Hail) -> TDamageCA;
    its Execute (CA VMT 0x557F3CC8 +0x50) 0x557F6A20 calls TDamageCA.Execute 0x55729D14 (eax = CA, edx = combat
    context) which applies byte [ca+0x10] via attacker VMT+0x108.  [ca+0x18] = spell id, [ca+0xE] = target unit id
    (TCombatData.FindID 0x55728C68(eax = [ctx+0xC], dl = id) -> TCombatUnit).
  * Bloodlust = ability 0xA8 (TBloodlustAbility, mode 1 = days).  Grant recipe = High Prayer / Blood Pact
    (TTacticalCombatHighPrayerCA.Execute 0x557F7E98): GetAbility([[0x558E92E8]]+0x80, 0xA8) 0x557501C0 ->
    ability VMT+0xD0 Expand(eax ability, edx TUnit = [cu+0x4C]) -> TUnit VMT+0x90 Changed.  Combat-only semantics
    are REUSED from patch_bloodbath_v1.py: when the grant CREATED the TDurationAbilityData record (GetAbilityData
    0x5574F1C4 nil before Expand) its +0x10 dword is stamped 350 - Blood Pact's flag - so its c9 (CombatDone removes
    it) and c10 (GetName shows "Bloodlust (combat only)") caves treat it exactly like a Blood Pact Bloodlust.  A
    Blood Shrine Bloodlust already on the unit keeps its days.
  * Machine = TUnit VMT+0x114 GetUnitType == 2 (TUnit.GetUnitType 0x55782808 = [[eax+0x40]+0x30]; heroes 0).
  * Targeting: TCombatUnitSelectionControl.UpdateMoveCursor 0x41F6E8 ([ebp-4] control, [ebp-0x10] selected unit HS
    with action [+0x34] (0x34 = Spellcasting) / spell id [+0x38], [ebp-0x14] the unit HS on the hovered field) sets
    the cursor word [ctl+0x2C] (0x69/0x50 valid, 0x59 invalid) and leaves through 0x41FA14.  The CLICK
    (ExecuteMoveSelection 0x41ED3B) only casts when TCombatUnitSelectionControl.CalculateRangedPath 0x41DC58 built a
    path; its out-of-range / off-map exits jump to 0x41DFCD (no path).  The tactical AI values spell targets through
    TCombatSpell.GetCombatDamageValueEx 0x557F7324 (eax spell, ecx target object, [ebp+8] out record: +0 expected,
    +4 max damage).

Hooks (all keyed on spell 404):
  AoWEPACK
    EX  0x557F6A2A `call TDamageCA.Execute` (5 B) -> call cave: target machine -> damage byte 0 and no grant;
        else Execute, then a still-living target (TCombatUnit VMT+0x88 GetHitPoints > 0) gains Bloodlust 0xA8.
    AI  0x557F744F `xor eax,eax / mov [edi+8],eax` (5 B) -> call cave: replay; a machine target (IsClass TCombatUnit
        [0x55715A54], then GetUnitType 2) gets expected / max damage 0 -> the AI never picks it.
  AoWTCPCK
    RP  0x41DCF0 `mov eax,[ebp-0xC] / cmp [eax+0x34],0x34` (7 B) in CalculateRangedPath -> call cave: a machine on the
        hovered field ([ebp-5] x / [ebp-6] y; GetMapLevel 0x401E64 / GetField 0x401E54 / field VMT+0x80
        FindOwnedChild(0x220104 unit HS)) -> drop the return address, jmp 0x41DFCD (no path = the click casts nothing).
    CU  0x41FA1C `mov dword [eax+0x34],0x100` (7 B) in UpdateMoveCursor's common exit -> call cave: replay; machine
        under the cursor -> cursor 0x59 (invalid).
Fast (auto) combat is NOT covered (TCombatSpell.fcExecuteCombatCommand path: no Bloodlust grant, no machine filter).

Zones: AoWEPACK 0x5585F000..0x5585F800, AoWTCPCK 0x43E700..0x43E900 (verified zero / reloc-free).  PIC via call/pop
delta for in-image absolutes (both DLLs rebase).  Thunks import-table checked: AoWEPACK IsClass 0x557010C0; TCPCK
GetMapLevel 0x401E64, GetField 0x401E54.  Dry-run default; --apply / --revert / --dis.  Backups .bak_bloodboil.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

SPELL_ID, BLOODLUST, BP_FLAG = 404, 0xA8, 350
ks = Ks(KS_ARCH_X86, KS_MODE_32)
ANCHOR = bytes.fromhex("e8000000005b81ebffffff7f")


def asm_pic(src, va):
    """Assemble; every `call $D / pop ebx / sub ebx, $D` delta anchor gets its real address."""
    s1 = src.replace("call $D", ".byte 0xe8, 0, 0, 0, 0").replace("sub ebx, $D", "sub ebx, 0x7fffffff")
    b = bytearray(ks.asm(s1, va)[0]); k = 0
    while True:
        k = b.find(ANCHOR, k)
        if k < 0: break
        struct.pack_into("<I", b, k + 8, va + k + 5); k += len(ANCHOR)
    return bytes(b)


# ------------------------------------------------------------------------------------------------ AoWEPACK
EP = dict(dll="AoWEPACK.dll", base=0x55700000, v2f=0x55700C00, zone=(0x5585F000, 0x5585F800))
FINDID, DMG_EXEC, GETABILITY, GETABDATA, ISCLASS = 0x55728C68, 0x55729D14, 0x557501C0, 0x5574F1C4, 0x557010C0
TCU_CLASSREF, REGISTRY = 0x55715A54, 0x558E92E8


def ep_caves():
    return [
        ("ismach", """
            test eax, eax
            jz im_no0
            push ecx
            push edx
            push ebx
            push eax
            call $D
            pop ebx
            sub ebx, $D
            mov edx, [ebx+%(tcu)#x]
            mov eax, [esp]
            call %(isclass)#x
            test al, al
            jz im_no
            mov eax, [esp]
            mov eax, [eax+0x4c]
            test eax, eax
            jz im_no
            mov edx, [eax]
            call dword ptr [edx+0x114]
            cmp al, 2
            jne im_no
            mov eax, 1
            jmp im_out
        im_no:
            xor eax, eax
        im_out:
            add esp, 4
            pop ebx
            pop edx
            pop ecx
            ret
        im_no0:
            xor eax, eax
            ret
        """),
        ("ex", """
            cmp dword ptr [eax+0x18], %(id)d
            je ex_mine
            jmp %(dmgexec)#x
        ex_mine:
            push ebx
            push esi
            push edi
            mov ebx, eax
            mov esi, edx
            movzx edx, byte ptr [ebx+0xe]
            mov eax, [esi+0xc]
            call %(findid)#x
            mov edi, eax
            call @ismach
            test al, al
            jz ex_dmg
            mov byte ptr [ebx+0x10], 0
            xor edi, edi
        ex_dmg:
            mov eax, ebx
            mov edx, esi
            call %(dmgexec)#x
            test edi, edi
            jz ex_out
            mov eax, edi
            mov edx, [eax]
            call dword ptr [edx+0x88]
            test al, al
            jle ex_out
            mov edi, [edi+0x4c]
            test edi, edi
            jz ex_out
            mov eax, edi
            mov edx, %(blood)d
            call %(abdata)#x
            push eax
            call $D
            pop ebx
            sub ebx, $D
            mov eax, [ebx+%(reg)#x]
            mov eax, [eax]
            mov eax, [eax+0x80]
            mov edx, %(blood)d
            call %(getab)#x
            test eax, eax
            jz ex_pop
            mov edx, edi
            mov ecx, [eax]
            call dword ptr [ecx+0xd0]
            pop ecx
            test ecx, ecx
            jnz ex_changed
            mov eax, edi
            mov edx, %(blood)d
            call %(abdata)#x
            test eax, eax
            jz ex_changed
            mov dword ptr [eax+0x10], %(bpflag)d
        ex_changed:
            mov eax, edi
            mov edx, [eax]
            call dword ptr [edx+0x90]
            jmp ex_out
        ex_pop:
            pop ecx
        ex_out:
            pop edi
            pop esi
            pop ebx
            ret
        """),
        ("ai", """
            xor eax, eax
            mov [edi+8], eax
            cmp dword ptr [ebx+0x10], %(id)d
            jne ai_r
            mov eax, esi
            call @ismach
            test al, al
            jz ai_r
            xor eax, eax
            mov [edi], eax
            mov [edi+4], eax
        ai_r:
            xor eax, eax
            ret
        """),
    ]


EP_HOOKS = [("EX", 0x557F6A2A, bytes.fromhex("e8e532f3ff"), "ex"),           # call TDamageCA.Execute
            ("AI", 0x557F744F, bytes.fromhex("33c0894708"), "ai")]           # xor eax,eax / mov [edi+8],eax
EP_FMT = {"id": SPELL_ID, "tcu": TCU_CLASSREF, "isclass": ISCLASS, "findid": FINDID, "dmgexec": DMG_EXEC,
          "blood": BLOODLUST, "abdata": GETABDATA, "reg": REGISTRY, "getab": GETABILITY, "bpflag": BP_FLAG}

# ------------------------------------------------------------------------------------------------ AoWTCPCK
TC = dict(dll="AoWTCPCK.dll", base=0x400000, v2f=0x400C00, zone=(0x43E700, 0x43E900))
MAP_GLOBAL, GETMAPLEVEL, GETFIELD, UNITHS_CID, RP_INVALID = 0x46C064, 0x401E64, 0x401E54, 0x220104, 0x41DFCD


def tc_caves():
    return [
        ("tcmach", """
            test eax, eax
            jz tm_no
            mov eax, [eax+0x1c]
            test eax, eax
            jz tm_no
            mov eax, [eax+0x4c]
            test eax, eax
            jz tm_no
            push ecx
            push edx
            mov edx, [eax]
            call dword ptr [edx+0x114]
            pop edx
            pop ecx
            cmp al, 2
            jne tm_no
            mov eax, 1
            ret
        tm_no:
            xor eax, eax
            ret
        """),
        ("rp", """
            mov eax, [ebp-0xc]
            cmp dword ptr [eax+0x34], 0x34
            jne rp_ret
            cmp dword ptr [eax+0x38], %(id)d
            jne rp_set
            pushal
            call $D
            pop ebx
            sub ebx, $D
            mov eax, [ebx+%(map)#x]
            mov eax, [eax+0x10]
            xor edx, edx
            call %(getlevel)#x
            test eax, eax
            jz rp_no
            movsx edx, byte ptr [ebp-5]
            movsx ecx, byte ptr [ebp-6]
            call %(getfield)#x
            test eax, eax
            jz rp_no
            mov edx, %(cid)#x
            mov ecx, [eax]
            call dword ptr [ecx+0x80]
            call @tcmach
            test al, al
            jz rp_no
            popal
            add esp, 4
            jmp %(invalid)#x
        rp_no:
            popal
        rp_set:
            mov eax, [ebp-0xc]
            cmp dword ptr [eax+0x34], 0x34
        rp_ret:
            ret
        """),
        ("cu", """
            mov dword ptr [eax+0x34], 0x100
            push eax
            mov eax, [ebp-0x10]
            test eax, eax
            jz cu_out
            cmp dword ptr [eax+0x34], 0x34
            jne cu_out
            cmp dword ptr [eax+0x38], %(id)d
            jne cu_out
            mov eax, [ebp-0x14]
            test eax, eax
            jz cu_out
            cmp eax, [ebp-0x10]
            je cu_out
            call @tcmach
            test al, al
            jz cu_out
            mov eax, [ebp-4]
            mov word ptr [eax+0x2c], 0x59
        cu_out:
            pop eax
            ret
        """),
    ]


TC_HOOKS = [("RP", 0x41DCF0, bytes.fromhex("8b45f483783434"), "rp"),        # mov eax,[ebp-0xc] / cmp [eax+0x34],0x34
            ("CU", 0x41FA1C, bytes.fromhex("c7403400010000"), "cu")]        # mov dword [eax+0x34],0x100
TC_FMT = {"id": SPELL_ID, "map": MAP_GLOBAL, "getlevel": GETMAPLEVEL, "getfield": GETFIELD, "cid": UNITHS_CID,
          "invalid": RP_INVALID}


def build_zone(part, caves, fmt):
    """Lay the caves out 16-aligned from the zone start; `@name` = another cave's address (two passes)."""
    z0, z1 = part["zone"]
    where = {name: z0 for name, _ in caves}
    for _ in range(2):
        out = bytearray(); nw = {}
        for name, src in caves:
            while len(out) % 16: out.append(0)
            va = z0 + len(out); nw[name] = va
            s = src % fmt
            for n2, a2 in where.items(): s = s.replace("@" + n2, "%#x" % a2)
            out += asm_pic(s, va)
        where = nw
    assert z0 + len(out) <= z1, hex(z0 + len(out))
    return bytes(out), where


def relocs(d, base):
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
            if e >> 12 == 3: out.add(base + page + (e & 0xFFF))
        p += size
    return out


def plan(part, caves, fmt, hooks):
    path = game_file(part["dll"]); d = bytearray(open(path, "rb").read()); v2f = part["v2f"]; z0, z1 = part["zone"]
    zone, where = build_zone(part, caves, fmt)
    zl = bytes(d[z0 - v2f:z1 - v2f])
    zstate = "zero" if not any(zl) else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else "DIFFERS"
    states, hookb = {}, {}
    for tag, site, orig, cave in hooks:
        h = b"\xe8" + struct.pack("<i", where[cave] - (site + 5)) + b"\x90" * (len(orig) - 5); hookb[tag] = h
        live = bytes(d[site - v2f:site - v2f + len(orig)])
        if live == orig: states[tag] = "vanilla"
        elif live == h: states[tag] = "ours"
        elif live[0] == 0xE8 and z0 <= site + 5 + struct.unpack_from("<i", live, 1)[0] < z1: states[tag] = "ours(old)"
        else: states[tag] = "OTHER"
    rl = relocs(bytes(d), part["base"])
    bad = [hex(r) for r in rl if z0 <= r < z1 or any(s <= r < s + len(o) for _, s, o, _ in hooks)]
    return dict(path=path, d=d, zone=zone, where=where, zstate=zstate, states=states, hookb=hookb, bad=bad)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true"); a = ap.parse_args()
    parts = [(EP, ep_caves(), EP_FMT, EP_HOOKS), (TC, tc_caves(), TC_FMT, TC_HOOKS)]
    plans = []
    for part, caves, fmt, hooks in parts:
        pl = plan(part, caves, fmt, hooks); plans.append((part, hooks, pl))
        print("%-13s sites %s | zone %s (%d B: %s) | relocs %s" % (part["dll"], pl["states"], pl["zstate"], len(pl["zone"]),
              ", ".join("%s @%#x" % kv for kv in pl["where"].items()), pl["bad"] or "none"))
        if a.dis:
            import capstone
            for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(pl["zone"], part["zone"][0]):
                print("   %08X  %-18s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if any(pl["bad"] or "OTHER" in pl["states"].values() for _, _, pl in plans): print("ABORT"); return 1
    if any(pl["zstate"] == "DIFFERS" and not any(s.startswith("ours") for s in pl["states"].values()) for _, _, pl in plans):
        print("ABORT (zone not free)"); return 1
    outs = []
    for part, hooks, pl in plans:
        d = bytearray(pl["d"]); v2f = part["v2f"]; z0, z1 = part["zone"]
        if a.revert:
            for tag, site, orig, _ in hooks:
                if pl["states"][tag].startswith("ours"): d[site - v2f:site - v2f + len(orig)] = orig
            d[z0 - v2f:z1 - v2f] = bytes(z1 - z0)
        else:
            d[z0 - v2f:z1 - v2f] = bytes(z1 - z0); d[z0 - v2f:z0 - v2f + len(pl["zone"])] = pl["zone"]
            for tag, site, orig, _ in hooks: d[site - v2f:site - v2f + len(orig)] = pl["hookb"][tag]
        outs.append((pl["path"], pl["d"], bytes(d)))
    if all(o == n for _, o, n in outs): print("already %s" % ("reverted" if a.revert else "applied")); return 0
    if not (a.apply or a.revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    for path, old, new in outs:
        if old == new: continue
        bak = bak_path(path, ".bak_bloodboil")
        if not os.path.exists(bak): shutil.copy2(path, bak); print("backup ->", bak)
        with open(path, "r+b") as f: f.write(new)
        assert open(path, "rb").read() == new; print("written", path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
