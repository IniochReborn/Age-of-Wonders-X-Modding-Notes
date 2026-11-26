#!/usr/bin/env python3
r"""
Healing valuation, engine side (AoWEPACK.dpl, 2026-09-16) -- part 1 of the "AI healing priority" work.

THealingAbility.fcGetDamageValueEx @0x5576C2EC is the valuation every AI path uses for Healing (the
tactical AI's touch handler calls it through TAbility.tcGetDamageValueEx = VMT+0xEC -> VMT+0xE4, and the
auto-combat prefetch calls VMT+0xE4 directly).  Vanilla: DV = 100 * min(5, maxHP - curHP), i.e. the
Healing level is ignored (the real heal is 5/7/10 via cave_healamt2) and curing a status is worth 0.

Patch:
  H1 0x5576C31F (call THealingAbility.GetHealHitPoints, 5 B) -> cave:
        amount = cave_healamt2(healer strat unit [self+0x4C])       (5/7/10, level+item aware)
        [rec+0xC] = amount                                          (raw amount, read by the AI patch)
        eax = min(amount, max(0, maxHP-curHP)) + (target Poisoned ? CURE_HP : 0)
     vanilla continues: [rec+4] = eax, [rec] = eax*100.
  H2 0x5576C335 (mov [ebx+0xC],eax -> mov [ebx+8],eax, 1 B): vanilla zeroed rec+0xC after the call; it now
     re-zeroes rec+8 (already 0) so the amount survives.  rec+0xC is [ebp-0x9C] in TCAI.CheckUnit, a slot
     vanilla never reads (verified over the whole function).
Position-independent (rel32 call into the existing healamt2 cave + virtual calls only).
Backup AoWEPACK.dpl.bak_healai.  Dry-run default; --apply; --revert; --dis.
"""
import argparse, os, shutil, struct, sys
from bakpath import game_dir, game_file   # game folder = AOW_GAME_DIR or parent of patch scripts (2026-09-20)
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

DEFAULT_DLL = game_file(r"AoWEPACK.dll")   # the .dll is what the game loads; AoWEPACK.dpl is an older build
BAK = ".bak_healai"
from bakpath import bak_path   # backups live in <game>\backup\ (2026-09-17)
BASE = 0x55700000

CURE_HP = 3                 # a cured Poisoned counts as this many HP healed (value only, not an actual heal)

HEALAMT2 = 0x558129A0       # cave_healamt2 (eax = healer strat unit|nil) -> eax = 5/7/10; preserves ecx/edx/esi
HEALAMT2_HEAD = bytes.fromhex("51525685c074")
H1 = (0x5576C31F, bytes.fromhex("e850fdffff"), 0x5576C324)
H2 = (0x5576C335, bytes.fromhex("89430c"), bytes.fromhex("894308"))
CAVE_BASE, CAVE_END = 0x55816280, 0x55816300
POISONED = 0x60
VMT_GETHITS, VMT_GETHITPOINTS, VMT_GETABILITYENABLED = 0x84, 0x88, 0xA8   # TCombatUnit: GetHits = MAX, GetHitPoints = CUR

ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, addr):
    enc, _ = ks.asm(src, addr)
    return bytes(enc)


def cave(va):
    return asm(f"""
        push edx
        mov eax, [ebp-4]
        mov eax, [eax+0x4C]
        call {HEALAMT2:#x}
        mov [ebx+0xC], eax
        push eax
        mov eax, [esp+4]
        mov edx, [eax]
        call [edx+{VMT_GETHITS:#x}]
        movsx edi, al
        mov eax, [esp+4]
        mov edx, [eax]
        call [edx+{VMT_GETHITPOINTS:#x}]
        movsx eax, al
        sub edi, eax
        pop eax
        test edi, edi
        jge h_m1
        xor edi, edi
    h_m1:
        cmp eax, edi
        jle h_m2
        mov eax, edi
    h_m2:
        mov edi, eax
        mov eax, [esp]
        mov edx, {POISONED:#x}
        mov ecx, [eax]
        call [ecx+{VMT_GETABILITYENABLED:#x}]
        test al, al
        jz h_m3
        add edi, {CURE_HP}
    h_m3:
        pop edx
        mov eax, edi
        jmp {H1[2]:#x}
    """, va)


def sections(d):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    n = struct.unpack_from("<H", d, e + 6)[0]
    optsz = struct.unpack_from("<H", d, e + 20)[0]
    out = []
    for i in range(n):
        s = d[e + 24 + optsz + 40 * i:][:40]
        out.append((s[:8].rstrip(b"\0").decode(),) + struct.unpack_from("<IIII", s, 8))
    return out


def va2off(d, va):
    for name, vs, va0, rs, ra in sections(d):
        if va0 <= va - BASE < va0 + max(vs, rs):
            return ra + (va - BASE - va0)
    raise ValueError(hex(va))


def relocs(d):
    for name, vs, va0, rs, ra in sections(d):
        if name != ".reloc":
            continue
        p, end = ra, ra + rs
        while p + 8 <= end:
            pr, sz = struct.unpack_from("<II", d, p)
            if sz == 0:
                break
            for q in range(p + 8, p + sz, 2):
                w = struct.unpack_from("<H", d, q)[0]
                if w >> 12 == 3:
                    yield BASE + pr + (w & 0xFFF)
            p += sz


def write_inplace(path, data):
    with open(path, "r+b") as f:
        f.seek(0); f.write(data)


def main():
    ap = argparse.ArgumentParser(description="Healing valuation: level-aware amount + Poisoned cure value (AoWEPACK)")
    ap.add_argument("--dll", default=DEFAULT_DLL)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    dll = a.dll
    if a.revert:
        if not os.path.exists(bak_path(dll, BAK)):
            print("no backup"); return 1
        bak = open(bak_path(dll, BAK), "rb").read()
        assert len(bak) == os.path.getsize(dll), "size differs from backup; refusing"
        write_inplace(dll, bak); print("restored " + os.path.basename(dll) + " from" + BAK); return 0

    d = bytearray(open(dll, "rb").read())
    c = cave(CAVE_BASE)
    if a.dis:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
        for i in Cs(CS_ARCH_X86, CS_MODE_32).disasm(c, CAVE_BASE):
            print("   %08x  %-18s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    assert bytes(d[va2off(d, HEALAMT2):][:6]) == HEALAMT2_HEAD, "cave_healamt2 not found at its expected VA"
    o1, o2, oc = va2off(d, H1[0]), va2off(d, H2[0]), va2off(d, CAVE_BASE)
    hookb = b"\xE9" + struct.pack("<i", CAVE_BASE - (H1[0] + 5))
    cur1, cur2 = bytes(d[o1:o1 + 5]), bytes(d[o2:o2 + 3])
    if cur1 == hookb and cur2 == H2[2] and bytes(d[oc:oc + len(c)]) == c:
        print("ALL ALREADY PATCHED"); return 0
    assert cur1 == H1[1] and cur2 == H2[1], "unexpected bytes at hook sites: %s %s" % (cur1.hex(), cur2.hex())
    assert bytes(d[oc:va2off(d, CAVE_END)]) == b"\0" * (CAVE_END - CAVE_BASE), "cave zone not zero"
    assert len(c) <= CAVE_END - CAVE_BASE, "cave too big"
    ranges = [(H1[0], H1[0] + 5), (H2[0], H2[0] + 3), (CAVE_BASE, CAVE_END)]
    r = [hex(v) for v in relocs(d) if any(lo <= v < hi or lo < v + 4 <= hi for lo, hi in ranges)]
    assert not r, "relocs intersect: " + ", ".join(r)
    print("H1 %#x vanilla, H2 %#x vanilla, cave %#x %d B, checks OK" % (H1[0], H2[0], CAVE_BASE, len(c)))
    if not a.apply:
        print("\nDry run OK. Re-run with --apply to write."); return 0
    if not os.path.exists(bak_path(dll, BAK)):
        shutil.copyfile(dll, bak_path(dll, BAK)); print("backup: " + os.path.basename(dll) + BAK)
    d[o1:o1 + 5] = hookb
    d[o2:o2 + 3] = H2[2]
    d[oc:oc + len(c)] = c
    write_inplace(dll, bytes(d))
    back = open(dll, "rb").read()
    assert back[oc:oc + len(c)] == c and back[o1] == 0xE9 and back[o2:o2 + 3] == H2[2], "read-back failed"
    print("applied.  CURE_HP=%d" % CURE_HP)
    return 0


if __name__ == "__main__":
    sys.exit(main())
