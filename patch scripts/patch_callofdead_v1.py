#!/usr/bin/env python3
r"""
Call of the Dead (211, Death tier 4 combat spell, research 250 / cost 7; 2026-10-16): "Animate all corpses on the
battlefield as Undead Draugr."   AoWEPACK.dll half (TCPCK half = patch_tc_callofdead_v1.py).

Registered by patch_dual_sphere_spells_v1.py as a TAnimateDead instance (donor TAnimateDead = vmtSelfPtr 0x557F68CC /
Create 0x557FA3BC, pfs_donor 140, SpellTypes 0x27 like Animate Dead / Harvest Souls; Create already sets range 0xFF =
infinite).  TAnimateDead.CreateCA (VMT+0x78 0x557FA4BC, Harvest's hcca cave in front) builds a TAnimateDeadCA with
[ca+0x18] = the spell id.

RE - TAnimateDeadCA.Execute 0x557FA2F4 (VMT+0x50 of the CA class [0x557F67E8]; eax = ca, edx = combat; push ebx/esi/edi,
ebx = ca):  `cmp byte [ebx+0x14],0 / je end` (only a DEAD corpse), edi = caster CU, esi = corpse CU (0x55728C68),
ebx := TUnit.Create (CA pointer lost from here on), eax = unit-type list [g+0x5C] -> the mod's type pick 0x557FA346 ->
0x5580CE0D (rdtsc-picked undead by corpse type, returns edx = type id to 0x557FA34B: GetType 0x55785050 / SetType),
owner VMT+0x16C(caster player), mod cave 0x557FA369 -> 0x5580C708 (Summoned 0x9B -> the raised unit PERSISTS after the
battle, upkeep like a summon), VMT+0x184, corpse CU VMT+0x134(new unit), CU destroyed bit cleared, side := caster's.

Call of the Dead = that same CA with two caves in front (every other spell id falls through untouched):
  EX 0x557FA304 (10 B `cmp byte [ebx+0x14],0 / je 0x557FA3B1`, vanilla): LATCH := [ca+0x18] (the spell id - the only
     point where the CA is still in ebx), replay the cmp/je.
  TP 0x557FA346 (jmp -> 0x5580CE0D, the mod's undead pick): LATCH == 211 -> edx := 201 (Unitres 201 = "Undead Draugr",
     level 1) -> 0x557FA34B; else -> the previous target (decoded at apply, kept in the zone header for --revert).
So every corpse the TCPCK half routes to this CA rises as a Draugr under the caster, Summoned like the mod's Animate Dead
(persists, upkeep).  LATCH = dword in AoWEPACK BSS page slack 0x558FAE80 (zero at load; Sanctify uses ..0x558FAE60,
build_* tables from 0x558FAF1F) - PIC via call/pop delta (AoWEPACK rebases).
v2 (2026-10-16, user: "Call of the Dead should raise ALL corpses in autocombat"): FAST COMBAT.  RE: a spell's auto-
combat path = VMT +0x90 fcPrefetchCombatCommands (driver 0x5576E3E1: eax = spell, edx = the caster's command list,
[list+4] = caster CU), +0x98 fcGetDamageValueEx (per target, eax spell / edx caster CU / ecx target / [esp+4] out,
ret 8; out[0] = value, 0 = no command), +0x94 fcExecuteCombatCommand (dispatcher 0x5576DEC8: eax spell, edx caster CU,
ecx TSpellCC).  TAnimateDead (VMT 0x557F690C, shared by Animate Dead 0x82 / Harvest Souls 207 / Call of the Dead 211)
uses the GENERIC +0x90 0x557F76BC and +0x94 0x557F7838: the prefetch only scores ENABLED (living, CU VMT+0x60) objects
and the execute skips destroyed targets ([obj+0x47]&1) - so vanilla Animate Dead never fires in auto-combat at all, and
neither did 211.  v2 repoints the three TAnimateDead VMT slots (0x557F699C / 0x557F69A0 / 0x557F69A4; absolute in-image
pointers that already carry relocs) to caves that pass every other spell id straight to the vanilla method:
  PF  (+0x90): 211 -> count eligible corpses of the caster's combat (CU [+8] = combat, [combat+0xC] = TCombatData,
      [+0x34] TEObjectList, [+8] TList); none -> no command; else PFN := count, run the vanilla prefetch, PFN := 0.
  VAL (+0x98): 211 -> out zeroed (+0x10 word = the vanilla constant @0x557FA4B8), value 200 (Animate Dead's own) for
      every scored (living) target while PFN > 0 - the target only carries the command, the cast ignores it.
  FX  (+0x94): 211 -> for EVERY eligible corpse in list order: CA := spell.CreateCA (VMT+0x78; first call flag 1 =
      the caster-cost wallet charges the cast once), TCombat.ExecuteCombatAction 0x55727224([caster+8], CA), CA VMT+0x2C;
      returns al = 1.  The CA is the same TAnimateDeadCA the tactical half uses, so EX/TP above make each corpse a
      Draugr 201, Summoned 0x9B (persists, upkeep) exactly as in tactical combat.  No RNG is consumed (the TP pick for
      211 is constant), so auto-combat replays stay deterministic.
  eligible corpse = IsClass TCombatUnit (walls excluded), ([+0x47] & 9) == 1 (destroyed, not fled), [+0x4C] unit set,
      unit VMT+0x114 != 2 (no machines) - both sides, heroes rise as Draugr (the hero stays dead), as in tactical.
  PFN = dword 0x558FAE84 (BSS page slack next to LATCH, zero at load, PIC).  Same zone, appended after TP (v1 caves
  keep their addresses -> a live v1 install upgrades in place).
Zone AoWEPACK 0x5586A000..0x5586A800 (zero, no relocs).  Backup <game>\backup\AoWEPACK.dll.bak_callofdead.
Dry-run default; --apply / --revert / --dis; --dll <copy> for scratch runs.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DEFAULT_DLL = game_file("AoWEPACK.dll")
BAK_SUFFIX = ".bak_callofdead"
BASE, V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x5586A000, 0x5586A800
SPELL, DRAUGR = 211, 201
LATCH = 0x558FAE80
EX_SITE, EX_ORIG, EX_GO, EX_END = 0x557FA304, bytes.fromhex("807b14000f84a3000000"), 0x557FA30E, 0x557FA3B1
TP_SITE, TP_BACK = 0x557FA346, 0x557FA34B
PFN = 0x558FAE84                                              # v2: corpse count during the 211 fast-combat prefetch
SLOTS = {"PF": (0x557F699C, 0x557F76BC), "FX": (0x557F69A0, 0x557F7838), "VAL": (0x557F69A4, 0x557FA474)}   # TAnimateDead VMT +0x90/+0x94/+0x98: (slot, vanilla method)
TCU_VMT, VAL_WORD, EXEC_CA, IS_CLASS = 0x55715A94, 0x557FA4B8, 0x55727224, 0x557010C0
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, va):
    return bytes(ks.asm(src, va)[0])


def build(prev_tp, v2=True):
    out = bytearray(struct.pack("<II", prev_tp, 0)); where = {}

    def place(name, src):
        while len(out) % 16: out.append(0)
        va = ZONE + len(out); where[name] = va
        out.extend(asm(src, va))

    place("EX", """
        push eax
        push edx
        call exd
    exd:
        pop eax
        sub eax, exd
        mov edx, [ebx + 0x18]
        mov [eax + %(latch)#x], edx
        pop edx
        pop eax
        cmp byte ptr [ebx + 0x14], 0
        je ex_end
        jmp %(go)#x
    ex_end:
        jmp %(end)#x
    """ % {"latch": LATCH, "go": EX_GO, "end": EX_END})
    place("TP", """
        push eax
        call tpd
    tpd:
        pop eax
        sub eax, tpd
        cmp dword ptr [eax + %(latch)#x], %(spell)d
        pop eax
        je tp_mine
        jmp %(prev)#x
    tp_mine:
        mov edx, %(draugr)d
        jmp %(back)#x
    """ % {"latch": LATCH, "spell": SPELL, "prev": prev_tp, "draugr": DRAUGR, "back": TP_BACK})
    if v2:
        k = {"spell": SPELL, "pfn": PFN, "tcu": TCU_VMT, "isc": IS_CLASS, "vw": VAL_WORD, "exca": EXEC_CA,
             "pf0": SLOTS["PF"][1], "fx0": SLOTS["FX"][1], "val0": SLOTS["VAL"][1]}
        # ELIG: eax = combat object -> al = 1 if it is a raisable corpse
        place("ELIG", """
            push ebx
            mov ebx, eax
            test ebx, ebx
            jz el_no
            mov al, byte ptr [ebx + 0x47]
            and al, 9
            cmp al, 1
            jne el_no
            call eld
        eld:
            pop edx
            sub edx, eld
            add edx, %(tcu)#x
            mov eax, ebx
            call %(isc)#x
            test al, al
            jz el_no
            mov eax, [ebx + 0x4c]
            test eax, eax
            jz el_no
            mov edx, [eax]
            call dword ptr [edx + 0x114]
            cmp al, 2
            je el_no
            mov al, 1
            pop ebx
            ret
        el_no:
            xor eax, eax
            pop ebx
            ret
        """ % k)
        # LIST: eax = caster CU -> eax = its combat's object TList (or 0)
        place("LIST", """
            test eax, eax
            jz li_no
            mov eax, [eax + 8]
            test eax, eax
            jz li_no
            mov eax, [eax + 0xc]
            test eax, eax
            jz li_no
            mov eax, [eax + 0x34]
            test eax, eax
            jz li_no
            mov eax, [eax + 8]
        li_no:
            ret
        """)
        # COUNT: eax = caster CU -> eax = eligible corpses
        place("COUNT", """
            push ebx
            push esi
            push edi
            xor edi, edi
            call %(list)#x
            test eax, eax
            jz co_done
            mov ebx, eax
            xor esi, esi
        co_loop:
            cmp esi, dword ptr [ebx + 8]
            jge co_done
            mov eax, [ebx + 4]
            mov eax, [eax + esi*4]
            call %(elig)#x
            test al, al
            jz co_next
            inc edi
        co_next:
            inc esi
            jmp co_loop
        co_done:
            mov eax, edi
            pop edi
            pop esi
            pop ebx
            ret
        """ % dict(k, list=where["LIST"], elig=where["ELIG"]))
        # PF: TAnimateDead +0x90 (eax = spell, edx = command list, [edx+4] = caster CU)
        place("PF", """
            cmp dword ptr [eax + 0x10], %(spell)d
            je pf_mine
            jmp %(pf0)#x
        pf_mine:
            push eax
            push edx
            mov eax, [edx + 4]
            call %(count)#x
            call pfd
        pfd:
            pop ecx
            sub ecx, pfd
            mov [ecx + %(pfn)#x], eax
            pop edx
            test eax, eax
            pop eax
            jz pf_none
            push ecx
            call %(pf0)#x
            pop ecx
            mov dword ptr [ecx + %(pfn)#x], 0
        pf_none:
            ret
        """ % dict(k, count=where["COUNT"]))
        # VAL: TAnimateDead +0x98 (eax spell, edx caster, ecx target, [esp+4] out, [esp+8]; ret 8)
        place("VAL", """
            cmp dword ptr [eax + 0x10], %(spell)d
            je va_mine
            jmp %(val0)#x
        va_mine:
            push ebx
            mov ebx, [esp + 8]
            xor eax, eax
            mov [ebx], eax
            mov [ebx + 4], eax
            mov [ebx + 8], eax
            mov [ebx + 0xc], eax
            call vad
        vad:
            pop eax
            sub eax, vad
            push edx
            mov dx, word ptr [eax + %(vw)#x]
            mov word ptr [ebx + 0x10], dx
            pop edx
            cmp dword ptr [eax + %(pfn)#x], 0
            je va_done
            mov dword ptr [ebx], 200
        va_done:
            pop ebx
            ret 8
        """ % k)
        # FX: TAnimateDead +0x94 (eax spell, edx caster CU, ecx TSpellCC) -> raise every eligible corpse; al = 1
        place("FX", """
            cmp dword ptr [eax + 0x10], %(spell)d
            je fx_mine
            jmp %(fx0)#x
        fx_mine:
            push ebx
            push esi
            push edi
            push ebp
            mov ebp, eax
            mov edi, edx
            mov eax, [ebp]
            push dword ptr [eax + 0x78]
            push 1
            mov eax, edi
            call %(list)#x
            test eax, eax
            jz fx_done
            mov ebx, eax
            xor esi, esi
        fx_loop:
            cmp esi, dword ptr [ebx + 8]
            jge fx_done
            mov eax, [ebx + 4]
            mov eax, [eax + esi*4]
            push eax
            call %(elig)#x
            pop ecx
            test al, al
            jz fx_next
            push dword ptr [esp]
            mov eax, ebp
            mov edx, edi
            call dword ptr [esp + 8]
            mov dword ptr [esp], 0
            test eax, eax
            jz fx_next
            push eax
            mov edx, eax
            mov eax, [edi + 8]
            call %(exca)#x
            pop eax
            mov edx, [eax]
            call dword ptr [edx + 0x2c]
        fx_next:
            inc esi
            jmp fx_loop
        fx_done:
            add esp, 8
            mov al, 1
            pop ebp
            pop edi
            pop esi
            pop ebx
            ret
        """ % dict(k, list=where["LIST"], elig=where["ELIG"]))
    assert ZONE + len(out) <= ZONE_END, hex(ZONE + len(out))
    return bytes(out), where


def rel(op, va, target, size):
    return bytes([op]) + struct.pack("<i", target - (va + 5)) + b"\x90" * (size - 5)


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
    g = lambda va, n: bytes(d[va - V2F:va - V2F + n])
    u32 = lambda va: struct.unpack_from("<I", d, va - V2F)[0]
    jt = lambda va: va + 5 + struct.unpack_from("<i", g(va, 5), 1)[0] if g(va, 1) == b"\xE9" else None
    zl = d[ZONE - V2F:ZONE_END - V2F]
    zero = not any(zl)
    cur_tp = jt(TP_SITE)
    assert cur_tp, "type-pick site 0x557FA346 is not a jmp: %s" % g(TP_SITE, 5).hex()
    prev_tp = cur_tp if zero else struct.unpack_from("<I", zl, 0)[0]
    zone, where = build(prev_tp)
    zone1, where1 = build(prev_tp, v2=False)
    assert where1["EX"] == where["EX"] and where1["TP"] == where["TP"]
    fits = lambda z: zl[:len(z)] == z and not any(zl[len(z):])
    zstate = "zero" if zero else "ours" if fits(zone) else "v1" if fits(zone1) else "DIFFERS"
    st = {}
    st["EX"] = "ours" if g(EX_SITE, 10) == rel(0xE9, EX_SITE, where["EX"], 10) else "vanilla" if g(EX_SITE, 10) == EX_ORIG else "OTHER(%s)" % g(EX_SITE, 10).hex()
    st["TP"] = "ours" if g(TP_SITE, 5) == rel(0xE9, TP_SITE, where["TP"], 5) else "prev" if not (ZONE <= cur_tp < ZONE_END) else "OTHER(%s)" % g(TP_SITE, 5).hex()
    for nm, (slot, van) in SLOTS.items():
        v = u32(slot); st[nm] = "ours" if v == where[nm] else "vanilla" if v == van else "OTHER(%#x)" % v
    rl = reloc_set(d)
    bad = [hex(r) for r in rl if ZONE - 3 <= r < ZONE_END or EX_SITE - 3 <= r < EX_SITE + 10 or TP_SITE - 3 <= r < TP_SITE + 5]
    noreloc = [hex(slot) for slot, _ in SLOTS.values() if slot not in rl]
    print("AoWEPACK sites %s | prev TP -> %#x | zone %s (%d B) | relocs %s | slot relocs missing %s | latch @%#x pfn @%#x | caves %s"
          % (st, prev_tp, zstate, len(zone), bad or "none", noreloc or "none", LATCH, PFN, ", ".join("%s=%#x" % kv for kv in where.items())))
    if bad or noreloc or zstate == "DIFFERS" or any(v.startswith("OTHER") for v in st.values()): print("ABORT"); return 1
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        for i in md.disasm(zone[8:], ZONE + 8): print("   %08X  %-20s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if a.revert:
        if zstate == "zero": print("nothing to revert"); return 0
        if st["EX"] != "ours" or st["TP"] != "ours": print("ABORT: partial state %s" % st); return 1
        out = bytearray(d)
        out[EX_SITE - V2F:EX_SITE - V2F + 10] = EX_ORIG
        out[TP_SITE - V2F:TP_SITE - V2F + 5] = rel(0xE9, TP_SITE, prev_tp, 5)
        for slot, van in SLOTS.values(): out[slot - V2F:slot - V2F + 4] = struct.pack("<I", van)
        out[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE)
        write_inplace(a.dll, bytes(out)); print("reverted (%s build; TP -> %#x, slots vanilla)" % (zstate, prev_tp)); return 0
    if zstate == "ours" and all(v == "ours" for v in st.values()): print("already applied"); return 0
    if zstate == "ours": print("ABORT: zone holds our code but the sites do not all point at it: %s" % st); return 1
    if zstate == "v1":
        if st["EX"] != "ours" or st["TP"] != "ours" or any(st[n] != "vanilla" for n in SLOTS): print("ABORT: v1 zone but sites %s" % st); return 1
        print("v1 build found -> upgrading to v2 (fast-combat caves appended, 3 TAnimateDead VMT slots repointed)")
    out = bytearray(d)
    out[ZONE - V2F:ZONE - V2F + len(zone)] = zone
    out[EX_SITE - V2F:EX_SITE - V2F + 10] = rel(0xE9, EX_SITE, where["EX"], 10)
    out[TP_SITE - V2F:TP_SITE - V2F + 5] = rel(0xE9, TP_SITE, where["TP"], 5)
    for nm, (slot, van) in SLOTS.items(): out[slot - V2F:slot - V2F + 4] = struct.pack("<I", where[nm])
    print("%d bytes change" % sum(1 for x, y in zip(d, out) if x != y))
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if os.path.abspath(a.dll) == os.path.abspath(DEFAULT_DLL):
        bak = bak_path(a.dll, BAK_SUFFIX)
        if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    write_inplace(a.dll, bytes(out)); assert open(a.dll, "rb").read() == bytes(out); print("Written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
