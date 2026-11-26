#!/usr/bin/env python3
r"""
AoWTCPCK.dll: Bloodbath's slot-1 effect starts WITH the sparkles instead of after them (2026-10-07).

TfxHS.NewFrame kind 0x25 (the High Prayer cast effect, CASE_00429EF7_PROC0025 @0x42DC19) runs 100 ticks: at ticks
0,5,..,95 it spawns kind-0x1F rising sparkles (slot 0) per friendly unit, and at tick 100 it spawns the kind-0x26
"aura" effect per unit (PROC0002 @0x42DE3D) which plays the spell's slot-1 sequence for frames*(delay+1) ticks and
then dies.  Bloodbath's slot 1 is the descending shadow sword + blood gush, which must run alongside the sparkles,
so for spell id 350 ([fx+0x18]) the hook spawns the aura at tick 0 and skips the vanilla spawn at tick 100.
High Prayer (0x66) and every other spell are untouched (the cave replays the original compare and resumes).

Hook 0x42DC19 (9 B: mov eax,[ebp-8] / mov eax,[eax+10h] / cmp eax,64h) -> jmp cave + 4 nop; cave resumes at the
`ja` 0x42DC22 with the compare flags set.  Cave 0x43C480.. (CODE zero tail after the hail-msg caves).
v2: the vanilla aura spawn ENDS the parent effect (its tail @0x42DFD3 sets [fx+0x10] = -1 and [fx+0x2C] = nil), which
with the tick-0 spawn killed the sparkles - second hook at 0x42DFD3 keeps the parent alive for spell 350 (skips the
-1 / nil stores and goes straight to the epilogue), so sparkles (ticks 5..95) and the sword run together.
Backup <game>\backup\AoWTCPCK.dll.bak_bbaura.  Surgical --revert.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_dir, game_file

DEFAULT_DLL = game_file("AoWTCPCK.dll")   # 2026-10-11: de-baked
BAK_SUFFIX = ".bak_bbaura"
BASE, CODE_V2F = 0x400000, 0x400C00
ZONE, ZONE_END = 0x43C480, 0x43C500      # 0x43C500.. = patch_tc_hellfire_portal_v1.py
SPELL_ID = 350
SPELL_ID2 = 390      # 2026-10-14: Frenzied Charge (THighPrayer clone) - same tick-0 spawn of slot 1 (the swords play ONCE in place on each unit, with the cast sound) instead of the 20 rising slot-0 particles per unit
RESUME, SPAWN_AURA, END = 0x42DC22, 0x42DE3D, 0x42E3A3
SPELL_ID3, CHORUS_AURA_TICK = 308, 45   # v3 2026-10-16: Heavenly Chorus (THighPrayer clone) - user: the rising sparkles last too long -> sparkles at ticks 0..40 only, the slot-1 halo per unit spawns at tick 45 (the vanilla spawn path, whose tail ends the parent as at tick 100)
TAIL, TAIL_RESUME = 0x42DFD3, 0x42DFDD
HOOKS = [("entry", 0x42DC19, bytes.fromhex("8b45f88b401083f864")),            # mov eax,[ebp-8] / mov eax,[eax+10h] / cmp eax,64h
         ("tail", 0x42DFD3, bytes.fromhex("8b45f8c74010ffffffff"))]          # mov eax,[ebp-8] / mov dword [eax+10h],-1
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def build():
    out = bytearray(); where = {}
    def place(name, src):
        while len(out) % 4: out.append(0)                          # v3: 4-byte alignment (the 128-byte zone is full with 16)
        va = ZONE + len(out); where[name] = va; out.extend(bytes(ks.asm(src, va)[0]))
    # tick 0 -> spawn the aura (PROC0002), whose tail would end the parent: the tail cave skips the -1 while the
    # counter is still 0.  tick 100 -> jump straight to the vanilla tail (counter 100 != 0 -> ends the parent as
    # vanilla does; without this the effect never finishes and the combat waits on it forever = freeze).
    place("entry", """
        mov eax, [ebp-8]
        cmp dword ptr [eax+0x18], %d
        jne not308
        mov eax, [eax+0x10]
        cmp eax, %d
        je %#x
        cmp eax, 0x64
        jmp %#x
    not308:
        cmp dword ptr [eax+0x18], %d
        je ours
        cmp dword ptr [eax+0x18], %d
        jne vanilla
    ours:
        mov eax, [eax+0x10]
        test eax, eax
        jz %#x
        cmp eax, 0x64
        je %#x
        mov eax, [ebp-8]
    vanilla:
        mov eax, [eax+0x10]
        cmp eax, 0x64
        jmp %#x
    """ % (SPELL_ID3, CHORUS_AURA_TICK, SPAWN_AURA, RESUME, SPELL_ID, SPELL_ID2, SPAWN_AURA, TAIL, RESUME))
    place("tail", """
        mov eax, [ebp-8]
        cmp dword ptr [eax+0x18], %d
        je ours
        cmp dword ptr [eax+0x18], %d
        jne vanilla
    ours:
        cmp dword ptr [eax+0x10], 0
        je %#x
    vanilla:
        mov dword ptr [eax+0x10], -1
        jmp %#x
    """ % (SPELL_ID, SPELL_ID2, END, TAIL_RESUME))
    assert ZONE + len(out) <= ZONE_END
    return bytes(out), where


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
    code, where = build()
    hooks = [(va, orig, b"\xe9" + struct.pack("<i", where[name] - (va + 5)) + b"\x90" * (len(orig) - 5)) for name, va, orig in HOOKS]
    live = [bytes(d[va - CODE_V2F:va - CODE_V2F + len(orig)]) for va, orig, _h in hooks]
    zl = d[ZONE - CODE_V2F:ZONE_END - CODE_V2F]
    rl = reloc_set(d)
    bad = [r for r in rl if ZONE <= r < ZONE_END or any(va <= r < va + len(orig) for va, orig, _h in hooks)]
    def is_ours(l, va):
        return l[0] == 0xE9 and ZONE <= va + 5 + struct.unpack_from("<i", l, 1)[0] < ZONE_END and all(b == 0x90 for b in l[5:])
    state = ["vanilla" if l == orig else "ours" if is_ours(l, va) else "OTHER" for (va, orig, _h), l in zip(hooks, live)]
    zstate = "zero" if not any(zl) else "ours" if zl[:len(code)] == code and not any(zl[len(code):]) else "DIFFERS"
    print("sites %s | zone %s | relocs %s | caves %s" % (state, zstate, bad or "none", ", ".join("%s=%#x" % kv for kv in where.items())))
    if bad or "OTHER" in state: print("ABORT"); return 1
    if a.dis:
        import capstone
        for name, s in where.items():
            print("  --", name)
            for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(code[s - ZONE:], s):
                print("   %08X  %-16s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
                if i.mnemonic == "jmp" and not i.op_str.startswith("0x43c"): break
    if a.revert:
        out = bytearray(d)
        for (va, orig, _h), st in zip(hooks, state):
            if st == "ours": out[va - CODE_V2F:va - CODE_V2F + len(orig)] = orig
        out[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
        write_inplace(a.dll, bytes(out)); print("reverted"); return 0
    if all(s == "ours" for s in state) and zstate == "ours" and all(l == h for (va, orig, h), l in zip(hooks, live)):
        print("already applied"); return 0
    if "ours" not in state and zstate != "zero": print("ABORT: zone not zero on a vanilla dll"); return 1
    out = bytearray(d)
    out[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
    out[ZONE - CODE_V2F:ZONE - CODE_V2F + len(code)] = code
    for va, orig, h in hooks: out[va - CODE_V2F:va - CODE_V2F + len(orig)] = h
    print("%d bytes change" % sum(1 for x, y in zip(d, out) if x != y))
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(a.dll, BAK_SUFFIX)
    if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    write_inplace(a.dll, bytes(out)); assert open(a.dll, "rb").read() == bytes(out); print("Written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
