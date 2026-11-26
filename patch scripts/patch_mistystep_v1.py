#!/usr/bin/env python3
r"""Misty Step (396, Water/Air L1): a short-range Void Step - the caster teleports to a hex within 4, over walls.

Void Step (0xCA, build_warp_self_*) is a TCallFlames clone whose combat effect is replaced by a teleport cave in
AoWTCPCK (hook 0x40B452 -> cave 0x438100, phase 0 of TCAbRangedTE.Execute).  That cave hard-codes the spell id
0xCA in three places; this patch makes it serve 396 too, so 396 = a pipeline TCallFlames clone (pfs donor = Void
Step's record 212: teleport cast-fx + TELEPORT sound) with range 4 runs the same teleport:
  E1 0x43811B `cmp dword [eax+0x18],0xCA` (7 B) -> `call chk; nop; nop` (chk: ZF=1 for 0xCA or 396; the following
     jne at 0x438122 then works unchanged)
  E2 0x43833B `mov edx,0xCA` (sound GetSpell) -> `mov edx,[esi+0x18]` (esi = the token) + 2 nops
  E3 0x438456 `mov dword [edi+0x18],0xCA` (the cast-fx puff's spell tag, frames resolved from GetSpell(id)) ->
     `mov eax,[esi+0x18]; mov [edi+0x18],eax; nop` (esi = the token, still intact in the helper; eax is reloaded
     right after)
The teleport is a straight warp (one-step move to the destination, engine-validated per the caster's own movement
abilities): walls BETWEEN caster and target never matter - only the destination must be valid (the v4 dest search
spirals to the nearest valid hex).  So "can bypass walls" holds as-is.
AoWEPACK (siege qualification, build_warp_self_siege.py: knowing Void Step lets a hero attack walled structures):
  S1 0x55810B13 `cmp eax,0xCA` (5 B) -> `call chk` (ZF for 0xCA or 396) - Misty Step qualifies too.
Zones (verified zero): TCPCK 0x43B400..0x43B440, AoWEPACK 0x55834000..0x55834040.  No absolutes (rel32 only).
Dry-run default; --apply / --revert.  Backups *.bak_mistystep.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

MISTY = 396
ks = Ks(KS_ARCH_X86, KS_MODE_32)
TARGETS = {
    "AoWTCPCK": dict(dll=game_file("AoWTCPCK.dll"), base=0x400000, v2f=0x400C00, zone=(0x43B400, 0x43B440),
                     chk="cmp dword ptr [eax+0x18], 0xCA\n je ok\n cmp dword ptr [eax+0x18], %d\n ok:\n ret" % MISTY,
                     sites={"E1": (0x43811B, bytes.fromhex("817818ca000000"), "call"),
                            "E2": (0x43833B, bytes.fromhex("baca000000"), bytes.fromhex("8b56189090")),
                            "E3": (0x438456, bytes.fromhex("c74718ca000000"), bytes.fromhex("8b4618894718" + "90"))}),
    "AoWEPACK": dict(dll=game_file("AoWEPACK.dll"), base=0x55700000, v2f=0x55700C00, zone=(0x55834000, 0x55834040),
                     chk="cmp eax, 0xCA\n je ok\n cmp eax, %d\n ok:\n ret" % MISTY,
                     sites={"S1": (0x55810B13, bytes.fromhex("3dca000000"), "call")}),
}


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


def plan(name, t):
    d = bytearray(open(t["dll"], "rb").read()); v2f = t["v2f"]; z0, z1 = t["zone"]
    blob = bytes(ks.asm(t["chk"], z0)[0]); assert z0 + len(blob) <= z1
    def new_bytes(va, orig, repl):
        if repl == "call":
            b = b"\xe8" + struct.pack("<i", z0 - (va + 5)); return b + b"\x90" * (len(orig) - 5)
        assert len(repl) == len(orig); return repl
    rl = relocs(bytes(d), t["base"])
    bad = [hex(r) for r in rl if z0 <= r < z1 or any(va <= r < va + len(o) for va, o, _ in t["sites"].values())]
    states = {}
    for n, (va, orig, repl) in t["sites"].items():
        live = bytes(d[va - v2f:va - v2f + len(orig)])
        states[n] = "vanilla" if live == orig else "ours" if live == new_bytes(va, orig, repl) else "OTHER"
    zl = bytes(d[z0 - v2f:z1 - v2f])
    zstate = "zero" if not any(zl) else "ours" if zl[:len(blob)] == blob and not any(zl[len(blob):]) else "DIFFERS"
    print("%s: sites %s | zone %s (%d B @%#x) | relocs %s" % (name, states, zstate, len(blob), z0, bad or "none"))
    out = bytearray(d); rev = bytearray(d)
    out[z0 - v2f:z1 - v2f] = bytes(z1 - z0); out[z0 - v2f:z0 - v2f + len(blob)] = blob
    rev[z0 - v2f:z1 - v2f] = bytes(z1 - z0)
    for n, (va, orig, repl) in t["sites"].items():
        out[va - v2f:va - v2f + len(orig)] = new_bytes(va, orig, repl); rev[va - v2f:va - v2f + len(orig)] = orig
    ok = not bad and "OTHER" not in states.values() and (zstate != "DIFFERS" or any(s == "ours" for s in states.values()))
    applied = all(s == "ours" for s in states.values()) and zstate == "ours"
    return ok, applied, bytes(d), bytes(out), bytes(rev)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    a = ap.parse_args()
    plans = {n: plan(n, t) for n, t in TARGETS.items()}
    if not all(p[0] for p in plans.values()): print("ABORT"); return 1
    if a.revert:
        for n, (ok, applied, d, out, rev) in plans.items():
            with open(TARGETS[n]["dll"], "r+b") as f: f.write(rev)
        print("reverted"); return 0
    if all(p[1] for p in plans.values()): print("already applied"); return 0
    print("%d bytes change" % sum(sum(1 for x, y in zip(p[2], p[3]) if x != y) for p in plans.values()))
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    for n, (ok, applied, d, out, rev) in plans.items():
        bak = bak_path(TARGETS[n]["dll"], ".bak_mistystep")
        if not os.path.exists(bak): shutil.copy2(TARGETS[n]["dll"], bak); print("backup ->", bak)
        with open(TARGETS[n]["dll"], "r+b") as f: f.write(out)
        assert open(TARGETS[n]["dll"], "rb").read() == out
    print("Written and verified"); return 0


if __name__ == "__main__":
    sys.exit(main())
