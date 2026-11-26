#!/usr/bin/env python3
r"""
Call of the Dead (211, Death tier 4; 2026-10-16) - AoWTCPCK.dll half: every corpse on the battlefield, not the 7 hexes
round the target (AoWEPACK half = patch_callofdead_v1.py: the CA raises each one as an Undead Draugr, unit 201).

RE - TCAbRangedTE.Execute, corpse spells (class 0x27): @0x40BB26 (eax = the effect [ebp-0x20], [eax+0x18] spell id) the
corpse broadcast is only entered for 0x81 / 0x82 (+ Harvest 207 via 0x43CB90, Miracle 209 via 0x440C10, chained jmps);
0x40BB3F: phase = [fx+0x10]: 0 -> msg 0x31008 (corpse FX: each TCCorpseHS spawns the spell's slot-0 sparkles), 0x63 ->
msg 0x31009 (raise), each sent to the 7 hexes CenterHNtoHX(target [te+0x20]/[te+0x22], HN 0..6) through GetMapLevel
0x401E64 ([[0x469420]]+0x10, 0) / GetField 0x401E54 (eax level, edx x, ecx y) / field msg 0x401DDC (eax field, edx msg);
msg = [ebp-0x64] {+0 id, +8 caster [te+0x10], +0xC spell [te+0x18], +0x1C -1}; then 0x40CAF2 (end).
TCCorpseHS.MapFieldMsgProc 0x31009: 0x423FDB switch on [msg+0xC] (Miracle 0x440C30 -> Harvest 0x43CCB0 -> vanilla
`sub eax,0x81`): the 0x82 case 0x423FE9 calls GetSpell(0x82) HARD-CODED (so its CA would carry 0x82, not 211), then
CreateCA(caster [msg+8], corpse CU [hs+0xC]) -> ExecuteCombatAction [[0x46C064]+0xE4] 0x40259C -> Release -> 0x4240AD
(the alive CU gets a new unit HS; the corpse sprite is freed @0x424125).

Two caves, chained in FRONT of whatever the sites jmp to (decoded at apply, kept in the zone header for --revert):
  BC 0x40BB26: 211 -> phase 0: 0x31008, phase 0x63: 0x31009, else 0x40CAF2; the message (caster, spell, -1) is built
     like the vanilla one and sent to EVERY field of map level 0 (x 0..[level+0xC]-1, y 0..[level+0x10]-1 - the level's
     own size, as Ashes' sweep: GetField has no bounds check) that owns a TCCorpseHS (field VMT+0x80 FindOwnedChild
     0x220108); then 0x40CAF2.  Machine wrecks have no CU and are skipped in SW.
  SW 0x423FDB (eax = [msg+0xC]): 211 -> corpse CU [hs+0xC] nil -> leave the wreck alone (0x42412D); else the vanilla 0x82
     block with GetSpell([msg+0xC]) -> CA [+0x18] = 211 -> AoWEPACK: Draugr -> 0x4240AD.  Other ids -> previous target.
Zone 0x442000..0x442400 (zero, no relocs; PIC via call/pop delta for the TCPCK globals).
Backup <game>\backup\AoWTCPCK.dll.bak_callofdead.  Dry-run default; --apply / --revert / --dis; --dll <copy>.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DEFAULT_DLL = game_file("AoWTCPCK.dll")
BAK_SUFFIX = ".bak_callofdead"
BASE, V2F = 0x400000, 0x400C00
ZONE, ZONE_END = 0x442000, 0x442400
SPELL = 211
BC_SITE, BC_END = 0x40BB26, 0x40CAF2
SW_SITE, SW_RAISED, SW_EXIT = 0x423FDB, 0x4240AD, 0x42412D
MAPLIST_G, SPELLS_G, COMBAT_G, MAPDRAW_G, DRAWCOL_G = 0x469420, 0x46E8D0, 0x46C064, 0x46E8D4, 0x46DC08
GETMAPLEVEL, GETFIELD, SENDMSG, GETSPELL, EXECCA, MKCOLOR = 0x401E64, 0x401E54, 0x401DDC, 0x4029B4, 0x40259C, 0x40298C
CORPSE_CLASSID = 0x220108
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, va):
    return bytes(ks.asm(src, va)[0])


def build(prev_bc, prev_sw):
    out = bytearray(struct.pack("<II", prev_bc, prev_sw)); where = {}

    def place(name, src):
        while len(out) % 16: out.append(0)
        va = ZONE + len(out); where[name] = va
        out.extend(asm(src, va))

    place("BC", """
        cmp dword ptr [eax + 0x18], %(spell)d
        je bc_mine
        jmp %(prev)#x
    bc_mine:
        mov eax, [eax + 0x10]
        test eax, eax
        je bc_fx
        cmp eax, 0x63
        je bc_raise
        jmp %(end)#x
    bc_fx:
        mov dword ptr [ebp - 0x64], 0x31008
        jmp bc_go
    bc_raise:
        mov dword ptr [ebp - 0x64], 0x31009
    bc_go:
        mov eax, [ebp - 4]
        mov edx, [eax + 0x10]
        mov [ebp - 0x5c], edx
        mov edx, [eax + 0x18]
        mov [ebp - 0x58], edx
        mov dword ptr [ebp - 0x48], 0xffffffff
        push ebx
        push esi
        push edi
        call bcd
    bcd:
        pop ebx
        sub ebx, bcd
        mov eax, [ebx + %(maplist)#x]
        mov eax, [eax]
        mov eax, [eax + 0x10]
        xor edx, edx
        call %(getlevel)#x
        test eax, eax
        je bc_done
        mov edi, eax
        xor esi, esi
    bc_y:
        xor ebx, ebx
    bc_x:
        mov eax, edi
        mov edx, ebx
        mov ecx, esi
        call %(getfield)#x
        test eax, eax
        je bc_next
        push eax
        mov edx, %(corpse)#x
        mov ecx, [eax]
        call dword ptr [ecx + 0x80]
        test eax, eax
        pop eax
        je bc_next
        lea edx, [ebp - 0x64]
        call %(sendmsg)#x
    bc_next:
        inc ebx
        cmp ebx, [edi + 0xc]
        jl bc_x
        inc esi
        cmp esi, [edi + 0x10]
        jl bc_y
    bc_done:
        pop edi
        pop esi
        pop ebx
        jmp %(end)#x
    """ % {"spell": SPELL, "prev": prev_bc, "end": BC_END, "maplist": MAPLIST_G, "getlevel": GETMAPLEVEL,
           "getfield": GETFIELD, "corpse": CORPSE_CLASSID, "sendmsg": SENDMSG})
    place("SW", """
        cmp eax, %(spell)d
        je sw_mine
        jmp %(prev)#x
    sw_mine:
        mov eax, [ebp - 4]
        cmp dword ptr [eax + 0xc], 0
        jne sw_go
        jmp %(exit)#x
    sw_go:
        call swd
    swd:
        pop ebx
        sub ebx, swd
        mov eax, [ebx + %(mapdraw)#x]
        mov eax, [eax]
        mov edx, 0xffffff
        call %(mkcolor)#x
        mov edx, [ebx + %(drawcol)#x]
        mov [edx], eax
        mov eax, [ebx + %(spells)#x]
        mov eax, [eax]
        mov eax, [eax + 0x84]
        mov edx, [ebp - 8]
        mov edx, [edx + 0xc]
        call %(getspell)#x
        mov edx, [ebp - 4]
        mov ecx, [edx + 0xc]
        mov edx, [ebp - 8]
        mov edx, [edx + 8]
        push esi
        mov esi, [eax]
        push 0
        call dword ptr [esi + 0x78]
        pop esi
        test eax, eax
        je sw_done
        mov [ebp - 0xc], eax
        mov eax, [ebx + %(combat)#x]
        mov eax, [eax + 0xe4]
        mov edx, [ebp - 0xc]
        call %(execca)#x
        mov eax, [ebp - 0xc]
        mov edx, [eax]
        call dword ptr [edx + 0x2c]
    sw_done:
        jmp %(raised)#x
    """ % {"spell": SPELL, "prev": prev_sw, "exit": SW_EXIT, "mapdraw": MAPDRAW_G, "mkcolor": MKCOLOR, "drawcol": DRAWCOL_G,
           "spells": SPELLS_G, "getspell": GETSPELL, "combat": COMBAT_G, "execca": EXECCA, "raised": SW_RAISED})
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
    jt = lambda va: va + 5 + struct.unpack_from("<i", g(va, 5), 1)[0] if g(va, 1) == b"\xE9" else None
    zl = d[ZONE - V2F:ZONE_END - V2F]
    zero = not any(zl)
    cur_bc, cur_sw = jt(BC_SITE), jt(SW_SITE)
    assert cur_bc and cur_sw, "corpse-spell sites are not jmp-hooked as expected: %s %s" % (g(BC_SITE, 5).hex(), g(SW_SITE, 5).hex())
    prev_bc, prev_sw = (cur_bc, cur_sw) if zero else struct.unpack_from("<II", zl, 0)
    zone, where = build(prev_bc, prev_sw)
    zstate = "zero" if zero else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else "DIFFERS"
    st = {}
    for k, va, cur in (("BC", BC_SITE, cur_bc), ("SW", SW_SITE, cur_sw)):
        st[k] = "ours" if g(va, 5) == rel(0xE9, va, where[k], 5) else "prev" if not (ZONE <= cur < ZONE_END) else "OTHER(%s)" % g(va, 5).hex()
    rl = reloc_set(d)
    bad = [hex(r) for r in rl if ZONE - 3 <= r < ZONE_END or BC_SITE - 3 <= r < BC_SITE + 5 or SW_SITE - 3 <= r < SW_SITE + 5]
    print("AoWTCPCK sites %s | prev BC -> %#x, SW -> %#x | zone %s (%d B) | relocs %s | caves %s"
          % (st, prev_bc, prev_sw, zstate, len(zone), bad or "none", ", ".join("%s=%#x" % kv for kv in where.items())))
    if bad or zstate == "DIFFERS" or any(v.startswith("OTHER") for v in st.values()): print("ABORT"); return 1
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        for i in md.disasm(zone[8:], ZONE + 8): print("   %08X  %-20s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if a.revert:
        if zstate != "ours": print("nothing to revert"); return 0
        if not all(v == "ours" for v in st.values()): print("ABORT: partial state %s" % st); return 1
        out = bytearray(d)
        out[BC_SITE - V2F:BC_SITE - V2F + 5] = rel(0xE9, BC_SITE, prev_bc, 5)
        out[SW_SITE - V2F:SW_SITE - V2F + 5] = rel(0xE9, SW_SITE, prev_sw, 5)
        out[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE)
        write_inplace(a.dll, bytes(out)); print("reverted (BC -> %#x, SW -> %#x)" % (prev_bc, prev_sw)); return 0
    if zstate == "ours" and all(v == "ours" for v in st.values()): print("already applied"); return 0
    if zstate == "ours": print("ABORT: zone holds our code but the sites do not all point at it: %s" % st); return 1
    out = bytearray(d)
    out[ZONE - V2F:ZONE - V2F + len(zone)] = zone
    out[BC_SITE - V2F:BC_SITE - V2F + 5] = rel(0xE9, BC_SITE, where["BC"], 5)
    out[SW_SITE - V2F:SW_SITE - V2F + 5] = rel(0xE9, SW_SITE, where["SW"], 5)
    print("%d bytes change" % sum(1 for x, y in zip(d, out) if x != y))
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if os.path.abspath(a.dll) == os.path.abspath(DEFAULT_DLL):
        bak = bak_path(a.dll, BAK_SUFFIX)
        if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    write_inplace(a.dll, bytes(out)); assert open(a.dll, "rb").read() == bytes(out); print("Written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
