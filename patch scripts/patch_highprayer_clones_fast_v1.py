#!/usr/bin/env python3
r"""
HIGH PRAYER CLONES - FAST COMBAT + AI (spells 300 / 301 / 390 next to Blood Pact 350; 2026-10-19) - AoWEPACK.dll only.

Problem (Blood Pact audit): Awaken Spirit 300, Blessing of the Forest 301 and Frenzied Charge 390 are THighPrayer
clones.  Their real effects are wired only into the TACTICAL CA (earthlife `exe` VMT slot 0x557F4520, Frenzied's
jmp on 0x557F7E98).  In fast/auto combat TFastCombatHighPrayerCA.Execute (VMT slot 0x557F442C -> 0x557F7DA4) runs
the vanilla body: +5 HP heal (patch_bloodbath H6 skips it only for 350) and the High Prayer blessing 0x64 (H4 maps
only 350 -> 0xA8).  And High Prayer's healing-based AI scorers make all three recast every round while the army is
wounded (same flaw patch_bloodpact_ai_v1 fixed for 350).

Fix = an IN-PLACE UPGRADE of patch_bloodpact_ai_v1's zone (0x5581E100..0x5581E400, magic 'BPA1' -> 'HPC1'); its
three scorer caves are generalised to a per-spell "does this unit still benefit" test (`need`) and one new hook is
added for the fast CA:
  need(eax = combat unit, edx = spell id) -> al:
      350 Blood Pact            lacks 0xA8 Bloodlust                    (unchanged v1 rule)
      301 Blessing of the Forest lacks 0xB7 Barkskin
      300 Awaken Spirit         creature (TUnit VMT+0xA0 == TUnit.GetLevel 0x55782B8C, PIC compare) with level <= 2
                                and lacks 0xB6 Awakened                  (= the tactical eligibility)
      390 Frenzied Charge       lacks 0xB3 (Haste instance) OR lacks 0xB4 (Fury instance)
      (TCombatUnit.GetAbilityEnabled 0x55725004)
  c90  VMT+0x90 fcPrefetchCombatCommands: {350,300,301,390} -> v1's loop with `need` (DVtoDEV(300) per benefiting
       unit, vanilla tail 0x557F8093; sum 0 -> command dropped); else previous target.
  c98  VMT+0x98 fcGetDamageValueEx: record {300*n, 3*n, 0, 0, w 0x20} (n = benefiting units; 0 -> all zero).
  c88  VMT+0x88 tcGetDamageValueEx (tactical, per target): {300,3,0,0,0x20} if the target benefits, else zeros.
  fx   TFastCombatHighPrayerCA VMT slot 0x557F442C (Execute; vanilla 0x557F7DA4, reloc'd): for [ca+0x1C] (spell id,
       stamped by patch_bloodbath H3) in {300,301,390}: parent 0x557F6F88 like vanilla, then for every unit id of the
       CA's list ([ca+0x10], count +8, byte get 0x55702F1C) -> combat unit 0x55728C68(level [ctx+0xC], id) -> if
       `need` -> TUnit [cu+0x4C]: 300 -> 0xB6, 301 -> 0xB7, 390 -> 0xB3 + 0xB4 (each only if not yet enabled,
       VMT+0x148), granted through TAbstractUnit.ExpandAbility VMT+0x94 (Expand + Changed) = exactly the tactical
       caves' grant.  NO +5 heal, NO 0x64 blessing (tactical doesn't do them either).  The four abilities are
       combat-only (mode 3) -> TriggerCombatDone removes them after the fast battle like after a tactical one.
       Every other spell (High Prayer 102, Blood Pact 350 -> bloodbath H4/H6/H8) -> the previous slot target.
Deterministic, no RNG -> MP-identical.  PIC: rel32 + call/pop delta (TCombatUnit class ref [0x55715A54], GetLevel).

States: zone 'BPA1' (Blood Pact v1 applied - the intended base) -> upgraded in place; zone zero -> fresh apply
(same result, header records base = none).  --revert restores the base: v1's exact blob + slots (rebuilt with
patch_bloodpact_ai_v1.build) or, base none, the original slot values + zero zone.  LIFO: revert THIS before
patch_bloodpact_ai_v1 (its --revert refuses an 'HPC1' zone), before patch_earthlife_blessings_v1 /
patch_frenzied_charge_v1 / patch_bloodbath_v1 (ability ids / H3 stamp it relies on), and before anything that
later chains on VMT+0x88/+0x90/+0x98 or slot 0x557F442C.  Dry-run default; --apply / --revert / --dis.
Backup <game>\backup\AoWEPACK.dll.bak_hpclones.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
import patch_bloodpact_ai_v1 as BPV1

DEFAULT_DLL = game_file("AoWEPACK.dll")
BAK_SUFFIX = ".bak_hpclones"
BASE, CODE_V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x5581E100, 0x5581E400
MAGIC = b"HPC1"
VMT = 0x557F45CC
SLOTS = {"c88": VMT + 0x88, "c90": VMT + 0x90, "c98": VMT + 0x98, "fx": 0x557F442C}
FX_VANILLA = 0x557F7DA4
SIDE, LISTGET, ISCLASS, CU_ABIL, DVTODEV = 0x55726660, 0x55726DBC, 0x557010C0, 0x55725004, 0x55725F10
TCU_CLASS, TAIL90 = 0x55715A54, 0x557F8093
FC_PARENT, BYTEGET, RESOLVE, GETLEVEL = 0x557F6F88, 0x55702F1C, 0x55728C68, 0x55782B8C
SP_BP, SP_AWAKEN, SP_FOREST, SP_FRENZY = 350, 300, 301, 390
AB_LUST, AB_AWAKENED, AB_BARKSKIN, AB_HASTE, AB_FURY = 0xA8, 0xB6, 0xB7, 0xB3, 0xB4
HDR = 0x20
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def off(va):
    return va - CODE_V2F


def body(prev, pcs):
    def cls(lbl):
        return (f"call {lbl}\n{lbl}:\npop edx\nmov edx, dword ptr [edx + {(TCU_CLASS - pcs.get(lbl, 0)) & 0xFFFFFFFF:#x}]\n")
    return f"""
isours:
    cmp dword ptr [eax + 0x10], {SP_BP}
    je io_r
    cmp dword ptr [eax + 0x10], {SP_AWAKEN}
    je io_r
    cmp dword ptr [eax + 0x10], {SP_FOREST}
    je io_r
    cmp dword ptr [eax + 0x10], {SP_FRENZY}
io_r:
    ret

need:
    push ebx
    push esi
    mov ebx, eax
    mov esi, edx
    cmp esi, {SP_FRENZY}
    jne n_301
    mov edx, {AB_HASTE}
    call {CU_ABIL:#x}
    test al, al
    je n_yes
    mov edx, {AB_FURY}
    jmp n_lack
n_301:
    mov edx, {AB_BARKSKIN}
    cmp esi, {SP_FOREST}
    je n_lack
    mov edx, {AB_LUST}
    cmp esi, {SP_BP}
    je n_lack
    cmp esi, {SP_AWAKEN}
    jne n_no
    mov eax, dword ptr [ebx + 0x4c]
    test eax, eax
    je n_no
    mov ecx, dword ptr [eax]
    mov ecx, dword ptr [ecx + 0xa0]
    call n_pc
n_pc:
    pop edx
    lea edx, [edx + {(GETLEVEL - pcs.get('n_pc', 0)) & 0xFFFFFFFF:#x}]
    cmp ecx, edx
    jne n_no
    call ecx
    cmp al, 2
    jg n_no
    mov edx, {AB_AWAKENED}
n_lack:
    mov eax, ebx
    call {CU_ABIL:#x}
    test al, al
    sete al
    jmp n_out
n_yes:
    mov al, 1
    jmp n_out
n_no:
    xor eax, eax
n_out:
    pop esi
    pop ebx
    ret

c90:
    call isours
    je c90_ours
    jmp {prev['c90']:#x}
c90_ours:
    push ebx
    push esi
    push edi
    push ebp
    add esp, -8
    mov ebp, edx
    mov dword ptr [esp], eax
    xor eax, eax
    mov dword ptr [esp + 4], eax
    mov eax, dword ptr [ebp + 4]
    call {SIDE:#x}
    and eax, 0x7f
    mov edx, dword ptr [ebp + 0x10]
    mov edi, dword ptr [edx + eax*4 + 0x1c]
    mov eax, edi
    mov edx, dword ptr [eax]
    call dword ptr [edx + 0x54]
    mov esi, eax
c90_lp:
    dec esi
    js c90_done
    mov edx, esi
    mov eax, edi
    call {LISTGET:#x}
    mov ebx, eax
    cmp dword ptr [ebx + 0x18], 0
    je c90_lp
    {cls('c90_pc')}
    mov eax, ebx
    call {ISCLASS:#x}
    test al, al
    je c90_lp
    mov edx, dword ptr [esp]
    mov edx, dword ptr [edx + 0x10]
    mov eax, ebx
    call need
    test al, al
    je c90_lp
    push ebx
    mov eax, 300
    mov ecx, dword ptr [ebp + 4]
    xor edx, edx
    call {DVTODEV:#x}
    add dword ptr [esp + 4], eax
    jmp c90_lp
c90_done:
    jmp {TAIL90:#x}

c98:
    call isours
    je c98_ours
    jmp {prev['c98']:#x}
c98_ours:
    push ebx
    push esi
    push edi
    push ebp
    push dword ptr [eax + 0x10]
    xor ebp, ebp
    mov eax, edx
    mov ebx, edx
    call {SIDE:#x}
    and eax, 0x7f
    mov edx, dword ptr [ebx + 8]
    mov edi, dword ptr [edx + eax*4 + 0x1c]
    mov eax, edi
    mov edx, dword ptr [eax]
    call dword ptr [edx + 0x54]
    mov esi, eax
c98_lp:
    dec esi
    js c98_done
    mov edx, esi
    mov eax, edi
    call {LISTGET:#x}
    mov ebx, eax
    cmp dword ptr [ebx + 0x18], 0
    je c98_lp
    {cls('c98_pc')}
    mov eax, ebx
    call {ISCLASS:#x}
    test al, al
    je c98_lp
    mov edx, dword ptr [esp]
    mov eax, ebx
    call need
    test al, al
    je c98_lp
    inc ebp
    jmp c98_lp
c98_done:
    mov eax, dword ptr [esp + 0x18]
    imul ecx, ebp, 300
    mov dword ptr [eax], ecx
    lea ecx, [ebp + ebp*2]
    mov dword ptr [eax + 4], ecx
    xor ecx, ecx
    mov dword ptr [eax + 8], ecx
    mov dword ptr [eax + 0xc], ecx
    test ebp, ebp
    je c98_w
    mov cl, 0x20
c98_w:
    mov word ptr [eax + 0x10], cx
    pop ecx
    pop ebp
    pop edi
    pop esi
    pop ebx
    ret 8

c88:
    call isours
    je c88_ours
    jmp {prev['c88']:#x}
c88_ours:
    mov edx, dword ptr [eax + 0x10]
    mov eax, ecx
    call need
    mov edx, dword ptr [esp + 4]
    xor ecx, ecx
    mov dword ptr [edx + 8], ecx
    mov dword ptr [edx + 0xc], ecx
    test al, al
    je c88_zero
    mov dword ptr [edx], 300
    mov dword ptr [edx + 4], 3
    mov word ptr [edx + 0x10], 0x20
    ret 4
c88_zero:
    mov dword ptr [edx], ecx
    mov dword ptr [edx + 4], ecx
    mov word ptr [edx + 0x10], cx
    ret 4

fx:
    cmp dword ptr [eax + 0x1c], {SP_AWAKEN}
    je fx_ours
    cmp dword ptr [eax + 0x1c], {SP_FOREST}
    je fx_ours
    cmp dword ptr [eax + 0x1c], {SP_FRENZY}
    je fx_ours
    jmp {prev['fx']:#x}
fx_ours:
    push ebx
    push esi
    push edi
    push ebp
    mov ebp, edx
    mov edi, eax
    mov edx, ebp
    mov eax, edi
    call {FC_PARENT:#x}
    mov eax, dword ptr [edi + 0x10]
    mov esi, dword ptr [eax + 8]
fx_lp:
    dec esi
    js fx_done
    mov eax, dword ptr [edi + 0x10]
    mov edx, esi
    call {BYTEGET:#x}
    xor edx, edx
    mov dl, al
    mov eax, dword ptr [ebp + 0xc]
    call {RESOLVE:#x}
    test eax, eax
    je fx_lp
    mov ebx, eax
    mov edx, dword ptr [edi + 0x1c]
    call need
    test al, al
    je fx_lp
    mov ebx, dword ptr [ebx + 0x4c]
    test ebx, ebx
    je fx_lp
    mov eax, dword ptr [edi + 0x1c]
    cmp eax, {SP_FRENZY}
    jne fx_one
    mov ecx, {AB_HASTE}
    call grant
    mov ecx, {AB_FURY}
fx_g:
    call grant
    jmp fx_lp
fx_one:
    mov ecx, {AB_AWAKENED}
    cmp eax, {SP_AWAKEN}
    je fx_g
    mov ecx, {AB_BARKSKIN}
    jmp fx_g
fx_done:
    pop ebp
    pop edi
    pop esi
    pop ebx
    ret
grant:
    push ecx
    mov edx, ecx
    mov eax, ebx
    mov ecx, dword ptr [eax]
    call dword ptr [ecx + 0x148]
    pop edx
    test al, al
    jne g_done
    mov eax, ebx
    mov ecx, dword ptr [eax]
    call dword ptr [ecx + 0x94]
g_done:
    ret
"""


def build(prev):
    """Two-pass assemble (GetPC label addresses feed the delta displacements; instruction sizes are fixed)."""
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    start = ZONE + HDR
    pcs = {"n_pc": start, "c90_pc": start, "c98_pc": start}
    for _ in range(4):
        code = bytes(ks.asm(body(prev, pcs), start)[0])
        ins = list(Cs(CS_ARCH_X86, CS_MODE_32).disasm(code, start))
        assert sum(i.size for i in ins) == len(code), "disassembly gap"
        getpc = [i.address + 5 for i in ins if i.mnemonic == "call" and i.op_str == hex(i.address + 5)]
        assert len(getpc) == 3, getpc
        newpcs = {"n_pc": getpc[0], "c90_pc": getpc[1], "c98_pc": getpc[2]}
        if newpcs == pcs:
            break
        pcs = newpcs
    # entries: the instruction after each `call isours` group start; locate by pattern
    calls_isours = [i.address for i in ins if i.mnemonic == "call" and i.op_str == hex(start)]
    assert len(calls_isours) == 3, calls_isours
    fx_ent = [i.address for i in ins if i.mnemonic == "cmp" and i.op_str == "dword ptr [eax + 0x1c], 0x12c"]
    assert len(fx_ent) == 1
    entries = {"c90": calls_isours[0], "c98": calls_isours[1], "c88": calls_isours[2], "fx": fx_ent[0]}
    return code, entries


def blob_for(prev, base_v1):
    code, ent = build(prev)
    hdr = MAGIC + struct.pack("<IIIIB", prev["c88"], prev["c90"], prev["c98"], prev["fx"], 1 if base_v1 else 0)
    blob = hdr.ljust(HDR, b"\0") + code
    assert ZONE + len(blob) <= ZONE_END, hex(ZONE + len(blob))
    return blob, ent


def parse_hdr(zone):
    c88, c90, c98, fx, b = struct.unpack_from("<IIIIB", zone, 4)
    return {"c88": c88, "c90": c90, "c98": c98, "fx": fx}, bool(b)


def relocs(d):
    import pefile
    pe = pefile.PE(data=bytes(d), fast_load=True)
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_BASERELOC"]])
    return {BASE + e.rva for b in getattr(pe, "DIRECTORY_ENTRY_BASERELOC", []) for e in b.entries if e.type}


def dis(blob):
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    for i in Cs(CS_ARCH_X86, CS_MODE_32).disasm(blob[HDR:], ZONE + HDR):
        print(f"{i.address:08X}  {i.mnemonic} {i.op_str}")


def main():
    ap = argparse.ArgumentParser(description="High Prayer clones 300/301/390: fast-combat effects + AI scorer guard")
    ap.add_argument("--dll", default=DEFAULT_DLL)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read())
    zone = bytes(d[off(ZONE):off(ZONE_END)])
    cur = {k: struct.unpack_from("<I", d, off(va))[0] for k, va in SLOTS.items()}
    rl = relocs(d)
    zrel = [hex(r) for r in rl if ZONE - 3 <= r < ZONE_END]
    slotrel = all(va in rl for va in SLOTS.values())
    state = "ours" if zone[:4] == MAGIC else ("bloodpact v1" if zone[:4] == BPV1.MAGIC else ("zero" if not any(zone) else "DIFFERS"))
    print("zone %#x..%#x: %s; zone relocs %s; slot relocs %s" % (ZONE, ZONE_END, state, zrel or "none", "present" if slotrel else "MISSING"))
    for k, va in SLOTS.items():
        print("  %s slot %#x -> %#x" % (k, va, cur[k]))
    if zrel or not slotrel:
        print("ABORT: unexpected relocs"); return 1

    if a.revert:
        if state != "ours":
            print("not applied"); return 0
        prev, base_v1 = parse_hdr(zone)
        _, ent = blob_for(prev, base_v1)
        for k in SLOTS:
            if cur[k] != ent[k]:
                print("ABORT: slot %s no longer points at our cave (%#x) - another patch chained in front; revert it first" % (k, cur[k])); return 1
        d[off(ZONE):off(ZONE_END)] = bytes(ZONE_END - ZONE)
        if base_v1:
            b1, e1 = BPV1.build({k: prev[k] for k in ("c88", "c90", "c98")})
            d[off(ZONE):off(ZONE) + len(b1)] = b1
            for k in ("c88", "c90", "c98"):
                struct.pack_into("<I", d, off(SLOTS[k]), e1[k])
        else:
            for k in ("c88", "c90", "c98"):
                struct.pack_into("<I", d, off(SLOTS[k]), prev[k])
        struct.pack_into("<I", d, off(SLOTS["fx"]), prev["fx"])
        with open(a.dll, "r+b") as f:
            f.write(d)
        print("reverted -> %s" % ("Blood Pact v1 state" if base_v1 else "pre-Blood-Pact state (slots restored, zone zeroed)")); return 0

    if state == "ours":
        prev, base_v1 = parse_hdr(zone)
        blob, ent = blob_for(prev, base_v1)
        if bytes(d[off(ZONE):off(ZONE) + len(blob)]) == blob and all(cur[k] == ent[k] for k in SLOTS):
            if a.dis:
                dis(blob)
            print("already applied"); return 0
        print("ABORT: zone is ours but differs from this build - --revert first"); return 1
    if cur["fx"] != FX_VANILLA:
        print("ABORT: fast CA Execute slot is not vanilla (%#x)" % cur["fx"]); return 1
    if state == "bloodpact v1":
        p1 = dict(zip(("c88", "c90", "c98"), struct.unpack_from("<III", zone, 4)))
        b1, e1 = BPV1.build(p1)
        if bytes(zone[:len(b1)]) != b1 or any(zone[len(b1):]) or any(cur[k] != e1[k] for k in ("c88", "c90", "c98")):
            print("ABORT: Blood Pact v1 zone/slots not in their expected state"); return 1
        prev = dict(p1, fx=cur["fx"]); base_v1 = True
        print("Blood Pact v1 applied - upgrading in place")
    elif state == "zero":
        for k in ("c88", "c90", "c98"):
            if ZONE <= cur[k] < ZONE_END:
                print("ABORT: slot points into our zone"); return 1
        prev = dict(cur); base_v1 = False
        print("Blood Pact v1 NOT applied - fresh apply (this patch covers 350 too)")
    else:
        print("ABORT: zone not zero and not Blood Pact v1"); return 1
    blob, ent = blob_for(prev, base_v1)
    print("cave %d B (zone %d B); entries %s" % (len(blob), ZONE_END - ZONE, {k: hex(v) for k, v in ent.items()}))
    if a.dis:
        dis(blob)
    if not a.apply:
        print("dry run OK - nothing written (use --apply)"); return 0
    bak = bak_path(a.dll, BAK_SUFFIX)
    if not os.path.exists(bak):
        shutil.copyfile(a.dll, bak); print("backup ->", bak)
    d[off(ZONE):off(ZONE_END)] = bytes(ZONE_END - ZONE)
    d[off(ZONE):off(ZONE) + len(blob)] = blob
    for k, va in SLOTS.items():
        struct.pack_into("<I", d, off(va), ent[k])
    with open(a.dll, "r+b") as f:
        f.write(d)
    back = open(a.dll, "rb").read()
    assert back[off(ZONE):off(ZONE) + len(blob)] == blob
    print("written and verified"); return 0


if __name__ == "__main__":
    sys.exit(main())
