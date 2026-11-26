#!/usr/bin/env python3
r"""
Miracle (209) - AoWTCPCK.dll half (2026-10-16).  The AoWEPACK half (what the raise does) = patch_miracle_v1.py.

209 is a TRecallSpirit clone with SpellTypes 0x27 (corpse spells: Recall Spirit 0x81 / Animate Dead 0x82 / Harvest Souls
207).  RE: the kind-0x27 TE (TCAbRangedTE, [ebp-4] = TE, [te+0x18] = spell id, [ebp-0x20] = its record) routes ids at
0x40BB26 (`jmp 0x43CB90`: Harvest's routing cave adds 0x82 / 0xCF to vanilla's 0x81) to 0x40BB3F, which at stage 0
broadcasts map msg 0x31008 (FX) and at stage 0x63 msg 0x31009 {+8 caster CU, +0xC spell id} to the 7 hexes around the
target (loops `cmp [ebp-0x10],7 / jne` @0x40BBBE and @0x40BC33).  Each TCCorpseHS on those hexes handles 0x31009 in
MapFieldMsgProc 0x423BAC: the spell-id switch @0x423FDB (`jmp 0x43CCB0`, Harvest's switch cave: 0x81 / 0x82 / 0xCF) ->
GetSpell(id).CreateCA(caster, corpse CU) -> ExecuteCombatAction -> 0x4240AD (if the corpse CU is alive again: new unit
HS on the hex; then the corpse HS is freed).  0x42412D = plain exit (corpse kept).

Hooks (all in front of the current chain; other ids fall through unchanged):
  T1 0x40BB26 (jmp):  [rec+0x18] == 209 -> 0x40BB3F (the corpse-spell path), else the previous target (0x43CB90).
  T2 0x423FDB (jmp, eax = spell id):  209 -> ONE friendly corpse per cast: latch clear AND corpse CU [+0x45] == caster
     CU [+0x45] -> set latch, GetSpell(209).CreateCA(caster, corpse CU, 0) -> ExecuteCombatAction -> Release -> 0x4240AD;
     otherwise 0x42412D (that corpse is left alone).  Other ids -> the previous target (0x43CCB0).
  T3 0x40BBBE (6 B, the FX loop):  209 -> stop after i = 0 (only the target hex sparkles) -> 0x40BBC4.
  T4 0x40BC33 (6 B, the corpse loop):  209 -> stop after i = 0 (only corpses ON the target hex) and clear the latch
     -> 0x40BC39 (Harvest's post-loop jmp stays).
LATCH = byte at DATA zero-fill slack 0x46BFF0 (DATA VS ends 0x46B7C8).  Was 0x46BFB0 = INSIDE Sandstorm's unit list
0x46BF68..0x46BFE0 - moved 2026-10-18 by patch_tcpck_slack_fix_v1.py (this script recognises the old-latch zone).
Zone 0x440C00..0x440E00 (zero, no relocs); its first 8 bytes keep the previous T1 / T2 targets for --revert.  PIC for
the latch and the [0x46E8D0] spell list / [0x46C064] combat globals (call/pop delta; rel32 elsewhere).
Note: Harvest's own switch cave (0x43CCFE) pushes ebx between `push 0` and CreateCA, so the CA's flag arg = the PIC delta
(0 unless TCPCK rebases) - T2 does not copy that.
Backup <game>\backup\AoWTCPCK.dll.bak_miracle.  Dry-run default; --apply / --revert; --dll <copy> for scratch runs.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DEFAULT_DLL = game_file("AoWTCPCK.dll")
BAK_SUFFIX = ".bak_miracle"
BASE, V2F = 0x400000, 0x400C00
ZONE, ZONE_END = 0x440C00, 0x440E00
SPELL = 209
LATCH, LATCH_OLD = 0x46BFF0, 0x46BFB0           # 10/18: moved out of Sandstorm's G_LIST (patch_tcpck_slack_fix_v1.py)
T1_SITE, T1_GO = 0x40BB26, 0x40BB3F
T2_SITE, T2_RAISED, T2_EXIT = 0x423FDB, 0x4240AD, 0x42412D
T3_SITE, T3_ORIG, T3_LOOP, T3_OUT = 0x40BBBE, bytes.fromhex("837df00775b5"), 0x40BB79, 0x40BBC4
T4_SITE, T4_ORIG, T4_LOOP, T4_OUT = 0x40BC33, bytes.fromhex("837df00775b5"), 0x40BBEE, 0x40BC39
SPELLS_G, COMBAT_G, GETSPELL, EXECCA = 0x46E8D0, 0x46C064, 0x4029B4, 0x40259C
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, va):
    return bytes(ks.asm(src, va)[0])


def build(prev1, prev2, latch=LATCH):
    out = bytearray(struct.pack("<II", prev1, prev2)); where = {}

    def place(name, src):
        while len(out) % 16: out.append(0)
        va = ZONE + len(out); where[name] = va
        out.extend(asm(src, va))

    place("T1", """
        cmp dword ptr [eax + 0x18], %(spell)d
        je t1_go
        jmp %(prev)#x
    t1_go:
        jmp %(go)#x
    """ % {"spell": SPELL, "prev": prev1, "go": T1_GO})
    place("T2", """
        cmp eax, %(spell)d
        je t2_mine
        jmp %(prev)#x
    t2_mine:
        push ebx
        call t2d
    t2d:
        pop ebx
        sub ebx, t2d
        cmp byte ptr [ebx + %(latch)#x], 0
        jne t2_skip
        mov edx, [ebp - 4]
        mov edx, [edx + 0xc]
        test edx, edx
        je t2_skip
        mov ecx, [ebp - 8]
        mov ecx, [ecx + 8]
        test ecx, ecx
        je t2_skip
        mov al, byte ptr [edx + 0x45]
        cmp al, byte ptr [ecx + 0x45]
        jne t2_skip
        mov byte ptr [ebx + %(latch)#x], 1
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
        je t2_done
        mov [ebp - 0xc], eax
        mov eax, [ebx + %(combat)#x]
        mov eax, [eax + 0xe4]
        mov edx, [ebp - 0xc]
        call %(execca)#x
        mov eax, [ebp - 0xc]
        mov edx, [eax]
        call dword ptr [edx + 0x2c]
    t2_done:
        pop ebx
        jmp %(raised)#x
    t2_skip:
        pop ebx
        jmp %(exit)#x
    """ % {"spell": SPELL, "prev": prev2, "latch": latch, "spells": SPELLS_G, "combat": COMBAT_G, "getspell": GETSPELL,
           "execca": EXECCA, "raised": T2_RAISED, "exit": T2_EXIT})
    for name, loop, outa, reset in (("T3", T3_LOOP, T3_OUT, False), ("T4", T4_LOOP, T4_OUT, True)):
        lb = name.lower()
        place(name, """
        mov eax, [ebp - 4]
        cmp dword ptr [eax + 0x18], %(spell)d
        jne %(lb)s_norm
%(reset)s        jmp %(out)#x
    %(lb)s_norm:
        cmp dword ptr [ebp - 0x10], 7
        jne %(loop)#x
        jmp %(out)#x
        """ % {"spell": SPELL, "lb": lb, "loop": loop, "out": outa,
               "reset": ("""        call %(lb)s_d
    %(lb)s_d:
        pop eax
        sub eax, %(lb)s_d
        mov byte ptr [eax + %(latch)#x], 0
""" % {"lb": lb, "latch": latch}) if reset else ""})
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
    inzone = lambda va: va is not None and ZONE <= va < ZONE_END
    zero = not any(zl)
    cur1, cur2 = jt(T1_SITE), jt(T2_SITE)
    assert cur1 and cur2, "corpse-spell sites are not jmp-hooked as expected: %s %s" % (g(T1_SITE, 5).hex(), g(T2_SITE, 5).hex())
    prev1, prev2 = (cur1, cur2) if zero else struct.unpack_from("<II", zl, 0)
    zone, where = build(prev1, prev2)
    zold, _w = build(prev1, prev2, LATCH_OLD)
    zstate = "zero" if zero else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else         "oldlatch" if zl[:len(zold)] == zold and not any(zl[len(zold):]) else "DIFFERS"
    sites = [("T1", T1_SITE, 5, None), ("T2", T2_SITE, 5, None), ("T3", T3_SITE, 6, T3_ORIG), ("T4", T4_SITE, 6, T4_ORIG)]
    st = {}
    for k, va, n, orig in sites:
        if g(va, n) == rel(0xE9, va, where[k], n): st[k] = "ours"
        elif orig is not None and g(va, n) == orig: st[k] = "vanilla"
        elif orig is None and not inzone(jt(va)): st[k] = "prev"
        else: st[k] = "OTHER(%s)" % g(va, n).hex()
    rl = reloc_set(d)
    bad = [hex(r) for r in rl if ZONE - 3 <= r < ZONE_END or any(va - 3 <= r < va + n for _k, va, n, _o in sites)]
    print("sites %s | prev T1 -> %#x, T2 -> %#x | zone %s (%d B) | relocs %s | latch @%#x | caves %s"
          % (st, prev1, prev2, zstate, len(zone), bad or "none", LATCH, ", ".join("%s=%#x" % kv for kv in where.items())))
    if bad or zstate == "DIFFERS" or any(v.startswith("OTHER") for v in st.values()): print("ABORT"); return 1
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        for i in md.disasm(zone[8:], ZONE + 8): print("   %08X  %-20s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if zstate == "oldlatch" and not a.revert:
        print("applied with the OLD latch 0x46BFB0 (inside Sandstorm's list) - run patch_tcpck_slack_fix_v1.py --apply"); return 0
    if a.revert:
        if zstate not in ("ours", "oldlatch"): print("nothing to revert"); return 0
        if not all(v == "ours" for v in st.values()): print("ABORT: partial state %s" % st); return 1
        out = bytearray(d)
        for k, va, n, orig in sites:
            out[va - V2F:va - V2F + n] = orig if orig is not None else rel(0xE9, va, prev1 if k == "T1" else prev2, n)
        out[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE)
        write_inplace(a.dll, bytes(out)); print("reverted (T1 -> %#x, T2 -> %#x)" % (prev1, prev2)); return 0
    if zstate == "ours" and all(v == "ours" for v in st.values()): print("already applied"); return 0
    if zstate == "ours": print("ABORT: zone holds our code but the sites do not all point at it: %s" % st); return 1
    out = bytearray(d)
    out[ZONE - V2F:ZONE - V2F + len(zone)] = zone
    for k, va, n, _o in sites: out[va - V2F:va - V2F + n] = rel(0xE9, va, where[k], n)
    print("%d bytes change" % sum(1 for x, y in zip(d, out) if x != y))
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if a.dll == DEFAULT_DLL:
        bak = bak_path(a.dll, BAK_SUFFIX)
        if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    write_inplace(a.dll, bytes(out)); assert open(a.dll, "rb").read() == bytes(out); print("Written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
