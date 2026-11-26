#!/usr/bin/env python3
r"""
BLOOD PACT AI (spell 350; 2026-10-19) - AoWEPACK.dll only.  User: "Blood Pact gets spammed in autocombat repeatedly".

Root cause: Blood Pact is a THighPrayer instance (dual-sphere pipeline, donor THighPrayer).  High Prayer's three AI
scorers value the spell by the HEALING it would do - per friendly unit min(5, maxHP - HP) * 100 - and never look at
whether the blessing is already on the unit:
  fast/auto combat  VMT+0x90 fcPrefetchCombatCommands 0x557F8008 (sum of DVtoDEV 0x55725F10(missingHP*100) over the
                    caster's side; command dropped only when the sum is 0) and VMT+0x98 fcGetDamageValueEx 0x557F811C;
  tactical combat   VMT+0x88 tcGetDamageValueEx 0x557F8224 (per target: min(5, missingHP) * 100).
Blood Pact does not heal (patch_bloodbath_v1 H5/H6 skip the +5 HP) and re-casting only refreshes Bloodlust, so while
any friendly unit is wounded the AI recasts it EVERY round (mana wasted, nothing gained), and it never casts it on an
unwounded army (where Bloodlust would actually help).

Fix: for spell 350 only, all three scorers value UNITS STILL LACKING BLOODLUST (ability 0xA8, TCombatUnit
.GetAbilityEnabled 0x55725004 -> [cu+0x4C] VMT+0x148): 300 per such friendly unit (= the value of healing 3 HP),
0 when every friendly unit already has it -> the command is dropped, no more recasts.  Every other spell (incl.
Crosswind 213 / Heavenly Chorus 308 which earlier patches zero on the same slots) goes to the previous slot target.
  c90  VMT+0x90 slot 0x557F465C: 350 -> own loop (vanilla frame + loop shape, DVtoDEV per lacking unit), then the
       vanilla command-building tail 0x557F8093; else jmp previous (0x5586B9C0 Crosswind -> 0x5583A2E0 Chorus -> 0x557F8008).
  c98  VMT+0x98 slot 0x557F4664: 350 -> record {300*n, 3*n, 0, 0, w 0x20} (n = 0 -> all zero); else jmp previous.
  c88  VMT+0x88 slot 0x557F4654: 350 -> target lacks 0xA8 ? {300, 3, 0, 0, w 0x20} : zeros; else jmp previous
       (vanilla 0x557F8224).
Deterministic (no RNG) -> MP-identical.  Zone 0x5581E100..0x5581E400 (header 'BPA1' + the three previous slot values;
verified zero / reloc-free); PIC: rel32 + call/pop delta for TCombatUnit's class ref [0x55715A54].  Slots carry relocs
(VMT entries) by design.  Dry-run default; --apply / --revert (restores the three slot values from the header, zeroes
the zone) / --dis.  Backup <game>\backup\AoWEPACK.dll.bak_bloodpactai.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DEFAULT_DLL = game_file("AoWEPACK.dll")
BAK_SUFFIX = ".bak_bloodpactai"
BASE, CODE_V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x5581E100, 0x5581E400
MAGIC = b"BPA1"
SPELL, ABIL = 350, 0xA8
VMT = 0x557F45CC
SLOTS = {"c88": VMT + 0x88, "c90": VMT + 0x90, "c98": VMT + 0x98}
VANILLA = {"c88": 0x557F8224, "c90": 0x557F8008, "c98": 0x557F811C}
SIDE, LISTGET, ISCLASS, CU_ABIL, DVTODEV = 0x55726660, 0x55726DBC, 0x557010C0, 0x55725004, 0x55725F10
TCU_CLASS = 0x55715A54
TAIL90 = 0x557F8093
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def off(va):
    return va - CODE_V2F


def body(prev, pcs):
    """pcs = dict label -> preferred VA of the label right after each GetPC call (0 on the first pass)."""
    def cls(lbl):
        return (f"call {lbl}\n{lbl}:\npop edx\nmov edx, dword ptr [edx + {(TCU_CLASS - pcs.get(lbl, 0)) & 0xFFFFFFFF:#x}]\n")
    return f"""
c90:
    cmp dword ptr [eax + 0x10], {SPELL}
    je c90_bp
    jmp {prev['c90']:#x}
c90_bp:
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
    mov eax, ebx
    mov edx, {ABIL:#x}
    call {CU_ABIL:#x}
    test al, al
    jne c90_lp
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
    cmp dword ptr [eax + 0x10], {SPELL}
    je c98_bp
    jmp {prev['c98']:#x}
c98_bp:
    push ebx
    push esi
    push edi
    push ebp
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
    mov eax, ebx
    mov edx, {ABIL:#x}
    call {CU_ABIL:#x}
    test al, al
    jne c98_lp
    inc ebp
    jmp c98_lp
c98_done:
    mov eax, dword ptr [esp + 0x14]
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
    pop ebp
    pop edi
    pop esi
    pop ebx
    ret 8

c88:
    cmp dword ptr [eax + 0x10], {SPELL}
    je c88_bp
    jmp {prev['c88']:#x}
c88_bp:
    push ebx
    mov eax, ecx
    mov edx, {ABIL:#x}
    call {CU_ABIL:#x}
    mov edx, dword ptr [esp + 8]
    xor ecx, ecx
    mov dword ptr [edx + 8], ecx
    mov dword ptr [edx + 0xc], ecx
    test al, al
    jne c88_zero
    mov dword ptr [edx], 300
    mov dword ptr [edx + 4], 3
    mov word ptr [edx + 0x10], 0x20
    pop ebx
    ret 4
c88_zero:
    mov dword ptr [edx], ecx
    mov dword ptr [edx + 4], ecx
    mov word ptr [edx + 0x10], cx
    pop ebx
    ret 4
"""


def build(prev):
    """Two-pass assemble: the GetPC labels' addresses feed the delta displacements (fixed instruction sizes)."""
    from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    start = ZONE + 0x20
    pcs = {"c90_pc": start, "c98_pc": start}
    for _ in range(4):
        code = bytes(ks.asm(body(prev, pcs), start)[0])
        ins = list(Cs(CS_ARCH_X86, CS_MODE_32).disasm(code, start))
        getpc = [i.address + 5 for i in ins if i.mnemonic == "call" and i.op_str == hex(i.address + 5)]
        ents = [i.address for i in ins if i.mnemonic == "cmp" and i.op_str == "dword ptr [eax + 0x10], 0x15e"]
        assert len(getpc) == 2 and len(ents) == 3, (getpc, ents)
        newpcs = {"c90_pc": getpc[0], "c98_pc": getpc[1]}
        if newpcs == pcs:
            break
        pcs = newpcs
    entries = {"c90": ents[0], "c98": ents[1], "c88": ents[2]}
    hdr = MAGIC + struct.pack("<III", prev["c88"], prev["c90"], prev["c98"])
    blob = hdr.ljust(0x20, b"\0") + code
    assert ZONE + len(blob) <= ZONE_END, hex(len(blob))
    return blob, entries


def relocs(d):
    import pefile
    pe = pefile.PE(data=bytes(d), fast_load=True)
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_BASERELOC"]])
    out = set()
    for b in getattr(pe, "DIRECTORY_ENTRY_BASERELOC", []):
        for e in b.entries:
            if e.type:
                out.add(BASE + e.rva)
    return out


def main():
    ap = argparse.ArgumentParser(description="Blood Pact (350) AI values units still lacking Bloodlust")
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
    ours = zone[:4] == MAGIC
    print("zone %#x..%#x: %s; zone relocs %s; slot relocs %s" % (ZONE, ZONE_END, "ours" if ours else ("zero" if not any(zone) else "DIFFERS"),
                                                                 zrel or "none", "present" if slotrel else "MISSING"))
    for k, va in SLOTS.items():
        print("  %s slot %#x -> %#x" % (k, va, cur[k]))
    if zrel or not slotrel:
        print("ABORT: unexpected relocs"); return 1

    if a.revert:
        if not ours:
            print("not applied"); return 0
        prev = dict(zip(("c88", "c90", "c98"), struct.unpack_from("<III", zone, 4)))
        _, ent = build(prev)
        for k, va in SLOTS.items():
            if cur[k] != ent[k]:
                print("ABORT: slot %s no longer points at our cave (%#x) - another patch chained in front; revert it first" % (k, cur[k])); return 1
        for k, va in SLOTS.items():
            struct.pack_into("<I", d, off(va), prev[k])
        d[off(ZONE):off(ZONE_END)] = bytes(ZONE_END - ZONE)
        open(a.dll, "r+b").write(d)
        print("reverted (slots restored, zone zeroed)"); return 0

    if ours:
        prev = dict(zip(("c88", "c90", "c98"), struct.unpack_from("<III", zone, 4)))
        blob, ent = build(prev)
        if bytes(d[off(ZONE):off(ZONE) + len(blob)]) == blob and all(cur[k] == ent[k] for k in SLOTS):
            if a.dis:
                from capstone import Cs, CS_ARCH_X86, CS_MODE_32
                for i in Cs(CS_ARCH_X86, CS_MODE_32).disasm(blob[0x20:], ZONE + 0x20):
                    print(f"{i.address:08X}  {i.mnemonic} {i.op_str}")
            print("already applied"); return 0
        print("ABORT: zone is ours but differs from this build - --revert first"); return 1
    if any(zone):
        print("ABORT: zone not zero"); return 1
    for k in SLOTS:
        if ZONE <= cur[k] < ZONE_END:
            print("ABORT: slot points into our zone"); return 1
    prev = cur
    blob, ent = build(prev)
    print("cave %d B; entries %s" % (len(blob), {k: hex(v) for k, v in ent.items()}))
    if a.dis:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
        for i in Cs(CS_ARCH_X86, CS_MODE_32).disasm(blob[0x20:], ZONE + 0x20):
            print(f"{i.address:08X}  {i.mnemonic} {i.op_str}")
    if not a.apply:
        print("dry run OK - nothing written (use --apply)"); return 0
    bak = bak_path(a.dll, BAK_SUFFIX)
    if not os.path.exists(bak):
        shutil.copyfile(a.dll, bak); print("backup ->", bak)
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
