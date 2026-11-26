#!/usr/bin/env python3
r"""
AoWTCPCK.dll: the "hail impact" map message 0x31006 carries the real spell id (2026-10-05).

Great Hail (0x74) and clones aliased to it (Hellfire 354 via patch_tc_spell_alias_v1.py) deal their tactical damage
through map-field message 0x31006, sent from the ranged-TE impact switch @0x40C8E2.  The four handlers
  0x406094 CityWall.TCityWall           0x410682 CombatTerrain.TCombatTerrain
  0x4213FA AoWTC.TTacticalCombatUnitHS   0x432F68 CombatStructure.TCombatStructure
all do `mov edx,0x74 / call TSpellControl.GetSpell` and take attack/damage/damage-types from GREAT HAIL's spell
object, so an aliased clone hit walls, terrain and units with Great Hail's physical damage instead of its own.

Fix:
  sender 0x40C8F2  `mov dword [ebp-0x48],-1` (7 B) -> call cave + 2 nop.  The cave replays the store and also
                   writes [te+0x18] (the TE's spell id, te = [ebp-0x20]) into msg+0xC ([ebp-0x58]), which the
                   0x31006 record left uninitialised (0x31013 uses the same slot for its spell id).
  handlers (5 B)   `mov edx,0x74` -> call cave: edx = [msg+0xC] (msg = [ebp-8] in all four) or 0x74 when zero.
Clones therefore only need the alias table entry (so the sender fires) and their own +0x34.. combat params.

Caves 0x43C400.. (CODE zero tail after the alias caves).  Backup <game>\backup\AoWTCPCK.dll.bak_hailmsg.
Surgical --revert.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_dir, game_file

DEFAULT_DLL = game_file("AoWTCPCK.dll")   # 2026-10-11: de-baked
BAK_SUFFIX = ".bak_hailmsg"
BASE, CODE_V2F = 0x400000, 0x400C00
ZONE, ZONE_END = 0x43C400, 0x43C480
# --trace: diagnostic build - the caves also log into the DATA page slack past the section's VirtualSize
# (0x46B7C8.., raw-only bytes nothing references; the DLL is always relocated so the caves address it via the
# call/pop delta).  Read back with hail_trace_probe.py (elevated) while the game runs.  Layout:
#   +0x46B7C8 handler hit count, +0x46B7CC sender hit count, +0x46B7D0 8 x {msg+0xC, msg id} ring, +0x46B810 last
#   sender spell id.  Re-apply without --trace to go back to the production caves.
TRACE_BASE = 0x46B7C8

SENDER = (0x40C8F2, bytes.fromhex("c745b8ffffffff"), "s")
HANDLERS = [(va, bytes.fromhex("ba74000000"), "h") for va in (0x406094, 0x410682, 0x4213FA, 0x432F68)]
HOOKS = [SENDER] + HANDLERS
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, va):
    return bytes(ks.asm(src, va)[0])


def asm_delta(src, va):
    """Assemble src at va; `$D` = the address right after the `call $D` line (the call/pop delta anchor)."""
    if "$D" not in src: return asm(src, va)
    lines = src.split("\n")
    k = next(i for i, l in enumerate(lines) if "call $D" in l)
    prefix = asm("\n".join(lines[:k]).replace("$D", "0x7fffffff"), va)
    anchor = va + len(prefix) + 5
    return asm(src.replace("$D", "%#x" % anchor), va)


def build(trace=False):
    out = bytearray(); where = {}
    def place(name, src):
        while len(out) % 16: out.append(0)
        va = ZONE + len(out); where[name] = va
        out.extend(asm_delta(src, va))
    if not trace:
        place("s", """
            mov dword ptr [ebp-0x48], -1
            mov eax, [ebp-0x20]
            mov eax, [eax+0x18]
            mov [ebp-0x58], eax
            ret
        """)
        place("h", """
            mov edx, [ebp-8]
            mov edx, [edx+0xc]
            test edx, edx
            jnz ok
            mov edx, 0x74
        ok:
            ret
        """)
    else:
        place("s", """
            mov dword ptr [ebp-0x48], -1
            mov eax, [ebp-0x20]
            mov eax, [eax+0x18]
            mov [ebp-0x58], eax
            push ecx
            call $D
            pop ecx
            sub ecx, $D
            inc dword ptr [ecx+%#x]
            mov [ecx+%#x], eax
            pop ecx
            ret
        """ % (TRACE_BASE + 4, TRACE_BASE + 0x48))
        place("h", """
            push ecx
            push eax
            call $D
            pop eax
            sub eax, $D
            mov ecx, [eax+%#x]
            and ecx, 7
            lea ecx, [eax+ecx*8+%#x]
            mov edx, [ebp-8]
            mov edx, [edx+0xc]
            mov [ecx], edx
            mov edx, [ebp-8]
            mov edx, [edx]
            mov [ecx+4], edx
            inc dword ptr [eax+%#x]
            pop eax
            pop ecx
            mov edx, [ebp-8]
            mov edx, [edx+0xc]
            test edx, edx
            jnz ok
            mov edx, 0x74
        ok:
            ret
        """ % (TRACE_BASE, TRACE_BASE + 8, TRACE_BASE))
    assert ZONE + len(out) <= ZONE_END, hex(ZONE + len(out))
    return bytes(out), where


def hook(va, orig, target):
    return b"\xe8" + struct.pack("<i", target - (va + 5)) + b"\x90" * (len(orig) - 5)


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
    ap.add_argument("--trace", action="store_true", help="diagnostic caves that log into DATA slack (see header)")
    a = ap.parse_args()
    d = open(a.dll, "rb").read()
    zone, where = build(a.trace)
    hooks = [(va, orig, hook(va, orig, where[cave])) for va, orig, cave in HOOKS]
    live = [bytes(d[va - CODE_V2F:va - CODE_V2F + len(orig)]) for va, orig, _h in hooks]
    zl = d[ZONE - CODE_V2F:ZONE_END - CODE_V2F]
    rl = reloc_set(d)
    bad = [r for r in rl if ZONE <= r < ZONE_END or any(va <= r < va + len(orig) for va, orig, _h in hooks)]
    def is_ours(l, va):
        return l[0] == 0xE8 and ZONE <= va + 5 + struct.unpack_from("<i", l, 1)[0] < ZONE_END and all(b == 0x90 for b in l[5:])
    state = ["vanilla" if l == orig else "ours" if is_ours(l, va) else "OTHER" for (va, orig, _h), l in zip(hooks, live)]
    zstate = "zero" if not any(zl) else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else "DIFFERS"
    print("sites %s | zone %s | relocs %s | caves %s" % (state, zstate, bad or "none", ", ".join("%s=%#x" % kv for kv in where.items())))
    if bad or "OTHER" in state: print("ABORT"); return 1
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        for name, s in where.items():
            print("  --", name)
            for i in md.disasm(zone[s - ZONE:], s):
                print("   %08X  %-16s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
                if i.mnemonic == "ret": break
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
    out[ZONE - CODE_V2F:ZONE - CODE_V2F + len(zone)] = zone
    for va, orig, h in hooks: out[va - CODE_V2F:va - CODE_V2F + len(orig)] = h
    print("%d bytes change" % sum(1 for x, y in zip(d, out) if x != y))
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(a.dll, BAK_SUFFIX)
    if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    write_inplace(a.dll, bytes(out)); assert open(a.dll, "rb").read() == bytes(out); print("Written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
