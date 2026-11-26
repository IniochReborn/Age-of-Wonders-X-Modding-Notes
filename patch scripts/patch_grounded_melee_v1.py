#!/usr/bin/env python3
r"""
GROUNDED MELEE (Gravity Well 366 / Grounded 0xB8, 2026-10-15).  User: "i cant hit a grounded flyer with a ground unit".

ROOT CAUSE.  The ground-vs-flyer melee rule never looks at movement types (which Grounded already strips, see
patch_gravitywell_v1.py 'mt'); it asks the strategic unit GetAbilityEnabled(1 Flying) directly:
  * the strike abilities' "can strike" tests (AoWEPACK 0x55766C44 / 0x55766C98 / 0x5576A304 / 0x5576A390 /
    0x5576B8AC / 0x5576B940 / 0x55770180 ...): `GetAbilityEnabled(target,1) && !GetAbilityEnabled(attacker,1) -> no
    melee strike` (TUnit VMT+0x148);
  * the AI melee scorer TCAI.CheckUnit @0x415478 (`self !Flying && target Flying -> skip`) and every other TCPCK flyer
    test (hover draw 0x421FFB, paths 0x4058F4 / 0x4066E8 / 0x420BE9 ...) go through TCombatUnit.HasAbility (VMT+0xA8
    0x55725004 -> [cu+0x4C] VMT+0x148) = the same function.
  Grounded never removed ability 1, so all of these still saw a flyer.

FIX.  Redirect the GetAbilityEnabled slot (VMT+0x148) of the unit classes to two stubs (one per implementation):
  TAbstractUnit / TUnit / TAdjustableUnit -> 0x5577F5E0,  THero / TLeader -> 0x55812760 (the item-aware cave).
  stub(eax = unit, edx = id): id in {1 Flying, 0x3B Floating, 0xA5 Wind Walking} and the unit holds 0xB8 Grounded
  (orig(unit, 0xB8)) -> al = 0; everything else jumps to the original untouched.
  BYPASS: a call whose return address lies in the Gravity Well zone 0x5585A000..0x5585C000 (gw_air / gw_sync) gets the
  raw answer, so the natural-airborne test that grants/keeps Grounded and the +50 % damage still see the flyer.
  TWallUnit (also 0x5577F5E0) is left alone.  Grounded is combat-only (mode 3), so the strategic map never sees it.
  The paired hover fix (a grounded unit reads Flying = 0 now but must still draw at GROUND_DY) is in
  patch_gravitywell_field_v1.py v2 'hov'.

Zone AoWEPACK 0x55859000..0x5585A000 (PIC call/pop delta for the bypass range check; rel calls/jmps otherwise).
The five VMT slots keep their own relocs (absolute pointers: the slot gets the cave's preferred-base VA).
Dry-run default; --apply / --revert / --dis.  Backup .bak_groundedmelee (first apply only).
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DLL = game_file("AoWEPACK.dll")
BASE, V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x55859000, 0x5585A000
GW_LO, GW_HI = 0x5585A000, 0x5585C000                 # patch_gravitywell_v1.py zone (gw_air / gw_sync callers bypass)
GROUNDED = 0xB8
AIR_IDS = (1, 0x3B, 0xA5)
ORIG_U, ORIG_H = 0x5577F5E0, 0x55812760
SLOTS = [   # (class, slot VA = VMT + 0x148, original target, stub)
    ("TAbstractUnit",   0x55710888, ORIG_U, "u"),
    ("TUnit",           0x55710DF4, ORIG_U, "u"),
    ("TAdjustableUnit", 0x55712B9C, ORIG_U, "u"),
    ("THero",           0x55712134, ORIG_H, "h"),
    ("TLeader",         0x55712380, ORIG_H, "h"),
]

ks = Ks(KS_ARCH_X86, KS_MODE_32)
ANCHOR = bytes.fromhex("e8000000005981e9ffffff7f")      # call $D / pop ecx / sub ecx, $D


def asm_pic(src, va):
    s1 = src.replace("call $D", ".byte 0xe8, 0, 0, 0, 0").replace("sub ecx, $D", "sub ecx, 0x7fffffff")
    b = bytearray(ks.asm(s1, va)[0]); k = 0; n = 0
    while True:
        k = b.find(ANCHOR, k)
        if k < 0: break
        struct.pack_into("<I", b, k + 8, va + k + 5); k += len(ANCHOR); n += 1
    assert n == src.count("call $D"), "delta anchors %d of %d" % (n, src.count("call $D"))
    return bytes(b)


def stub(orig):
    cmps = "\n".join("        cmp edx, %#x\n        je c_chk" % i for i in AIR_IDS)
    return cmps + """
        jmp %(o)#x
    c_chk:
        push ecx
        push edx
        push eax
        call $D
        pop ecx
        sub ecx, $D
        mov edx, dword ptr [esp + 0xc]
        sub edx, ecx
        cmp edx, %(lo)#x
        jb c_test
        cmp edx, %(hi)#x
        jb c_raw
    c_test:
        mov eax, dword ptr [esp]
        mov edx, %(gr)d
        call %(o)#x
        test al, al
        pop eax
        pop edx
        pop ecx
        jnz c_grounded
        jmp %(o)#x
    c_grounded:
        xor eax, eax
        ret
    c_raw:
        pop eax
        pop edx
        pop ecx
        jmp %(o)#x
    """ % {"o": orig, "lo": GW_LO, "hi": GW_HI, "gr": GROUNDED}


def build():
    out = bytearray(); where = {}
    for name, orig in (("u", ORIG_U), ("h", ORIG_H)):
        while len(out) % 16: out.append(0)
        va = ZONE + len(out); where[name] = va; out += asm_pic(stub(orig), va)
    return bytes(out), where


def pe_info(d):
    pe = struct.unpack_from("<I", d, 0x3C)[0]; opt = struct.unpack_from("<H", d, pe + 20)[0]; nsec = struct.unpack_from("<H", d, pe + 6)[0]
    secs = [struct.unpack_from("<IIII", d, pe + 24 + opt + 40 * k + 8) for k in range(nsec)]
    def r2f(rva):
        for vs, va, rs, ro in secs:
            if va <= rva < va + max(vs, rs): return ro + rva - va
    return pe, r2f


def reloc_set(d):
    pe, r2f = pe_info(d)
    rrva, rsz = struct.unpack_from("<II", d, pe + 24 + 0x88)
    p = r2f(rrva); end = p + rsz; out = set()
    while p < end:
        page, size = struct.unpack_from("<II", d, p)
        if size < 8: break
        for q in range(p + 8, p + size, 2):
            e = struct.unpack_from("<H", d, q)[0]
            if e >> 12 == 3: out.add(BASE + page + (e & 0xFFF))
        p += size
    return out


def plan(dis):
    d = bytearray(open(DLL, "rb").read())
    blob, where = build(); assert ZONE + len(blob) <= ZONE_END, hex(ZONE + len(blob))
    states = {}
    for cls, va, orig, s in SLOTS:
        lp = struct.unpack_from("<I", d, va - V2F)[0]
        states[cls] = "vanilla" if lp == orig else "ours" if lp == where[s] else "ours(old)" if ZONE <= lp < ZONE_END else "OTHER(%#x)" % lp
    zl = bytes(d[ZONE - V2F:ZONE_END - V2F])
    zstate = "zero" if not any(zl) else "ours" if zl[:len(blob)] == blob and not any(zl[len(blob):]) else "DIFFERS"
    rl = reloc_set(bytes(d))
    bad = [hex(r) for r in rl if ZONE - 3 <= r < ZONE_END]
    slot_ok = all(va in rl for _c, va, _o, _s in SLOTS)
    print("AoWEPACK: slots %s | zone %s (%d B: stub_u=%#x stub_h=%#x) | relocs in zone %s | slot relocs %s"
          % (states, zstate, len(blob), where["u"], where["h"], bad or "none", "ok" if slot_ok else "MISSING"))
    if dis:
        import capstone
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(blob, ZONE):
            print("   %08X  %-18s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    return d, blob, where, states, zstate, bad, slot_ok


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true"); ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    d, blob, where, states, zstate, bad, slot_ok = plan(a.dis)
    if bad or not slot_ok or any(v.startswith("OTHER") for v in states.values()): print("ABORT (relocs, a foreign slot or a missing slot reloc)"); return 1
    if zstate == "DIFFERS" and not any(v.startswith("ours") for v in states.values()): print("ABORT (zone not free)"); return 1
    out = bytearray(d)
    if a.revert:
        for _c, va, orig, _s in SLOTS: struct.pack_into("<I", out, va - V2F, orig)
        out[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE)
    else:
        out[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE); out[ZONE - V2F:ZONE - V2F + len(blob)] = blob
        for _c, va, _orig, s in SLOTS: struct.pack_into("<I", out, va - V2F, where[s])
    if out == d: print("already applied" if not a.revert else "already vanilla"); return 0
    if not (a.apply or a.revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(DLL, ".bak_groundedmelee")
    if not os.path.exists(bak): shutil.copy2(DLL, bak); print("backup ->", bak)
    with open(DLL, "r+b") as f: f.write(bytes(out))
    assert open(DLL, "rb").read() == bytes(out); print("AoWEPACK: %s and verified" % ("reverted" if a.revert else "written"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
