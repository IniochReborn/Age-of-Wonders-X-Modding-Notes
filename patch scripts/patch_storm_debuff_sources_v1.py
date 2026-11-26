#!/usr/bin/env python3
r"""
Divine Storm applies Vertigo; Holy Ground applies Vertigo; Unholy Ground applies Cursed (AoWEPACK.dll, 2026-09-15).
Companion of patch_storm_effect_roll_v1.py (which must be applied first: every debuff added here goes
through its Resistance roll, so none of them lands automatically).

Vanilla facts (410 dll, verified 2026-09-15):
  * TAbstractUnit.ExecuteStormDamage @0x55780668: after the typed damage, the debuff dispatch
    @0x557807EB is `mov al,[esp] (storm idx); sub al,2; je Death; sub al,4; je Pestilence; jmp done`
    -> only Death Storm (idx 2, mask 0x20 Cursed) and Pestilence (idx 6, mask 0x10 Poisoned) ever call
    ExecuteDamageEffects @0x55781E28.  Divine Storm (idx 3) has NO debuff in vanilla - BXL's Ziggurat
    added it (his notes' "Divine Storm only recently started applying vertigo after a patch").
  * THolyGround.TriggerArmyDamage @0x557C7E18 / TUnHolyGround.TriggerArmyDamage @0x557C8FA4: per unit
    (ebx) an alignment gate, the ability-1 exemption, ExecuteDamageRole(holy 0x40 / death 0x20), then
    if damage > 0: SetHitPoints via `mov ecx,[eax]; call [ecx+0xE4]` @0x557C7F9E / @0x557C910B.  No
    debuff at all.  TPoisonPlant.TriggerArmyDamage (0x557C41BB..0x557C41D7) shows the vanilla idiom for
    one: after SetHitPoints, `GetHitPoints (VMT+0xE0) <> 0 -> mov dx,mask; mov eax,unit; call
    ExecuteDamageEffects`.  (The plant itself is dormant when its terrain byte [plant+0x18] is 3 Snow
    or 5 Wasteland - check fn @0x557C3F90 - which is vanilla and untouched here.)

Patch (three PIC caves, rel32 only, no data refs):
  A) storm dispatch hook @0x557807EB (13 B -> jmp + 8 NOP), cave 0x558161C0:
       al = [esp]; dx = 0x20 if al==2, 0x10 if al==6, 0x40 if al==3, else -> 0x55780816;
       mov eax,edi (unit); call ExecuteDamageEffects; jmp 0x55780816
  B) Holy Ground hook @0x557C7F9E (6 B `call [ecx+0xE4]` -> jmp + NOP), cave 0x55816200:
       call [ecx+0xE4]; if GetHitPoints(ebx) <> 0: dx=0x40; eax=ebx; call ExecuteDamageEffects;
       jmp 0x557C7FA4
  C) Unholy Ground hook @0x557C910B (same shape), cave 0x55816240, mask 0x20, resume 0x557C9111.
The vanilla Death/Pestilence blocks at 0x557807F8/0x55780808 become dead code (their .reloc entries stay
valid; nothing there is rewritten).

Result (with the roll patch): Divine Storm (spell and Altar of Ice-style altar storms alike, they share
ExecuteStormDamage) rolls Vertigo on every damaged non-machine unit; Holy Ground rolls Vertigo on the
evil units it burns; Unholy Ground rolls Cursed on the good units it burns; existing Death Storm /
Pestilence / Poison Plant debuffs unchanged apart from the roll.

Backup AoWEPACK.dll.bak_stormsrc.  Dry-run default; --apply; --revert (same-size in-place restore).
"""
import argparse, os, shutil, struct, sys
from bakpath import game_dir, game_file   # game folder = AOW_GAME_DIR or parent of patch scripts (2026-09-20)

DEFAULT_DLL = game_file(r"AoWEPACK.dll")
BAK = ".bak_stormsrc"
from bakpath import bak_path   # backups live in <game>\backup\ (2026-09-17)
BASE = 0x55700000
FN_EFFECTS = 0x55781E28
CAVE_LO, CAVE_HI = 0x558161C0, 0x55816280       # reserved zone (must be zero before first apply)
ROLL_HOOK = (0x55781E28, 0xE9)                  # first byte of the roll patch's hook - prerequisite


def rel32(src, dst):
    return struct.pack("<i", dst - (src + 5))


def cave_storm(va):
    done = 0x55780816
    c = bytearray()
    c += bytes.fromhex("8a0424")                    # mov al,[esp]
    fix = []
    for mask, idx in ((0x20, 2), (0x10, 6), (0x40, 3)):
        c += b"\x66\xBA" + struct.pack("<H", mask)  # mov dx,mask
        c += b"\x3C" + bytes([idx])                 # cmp al,idx
        fix.append(len(c)); c += b"\x74\x00"        # je apply (patched below)
    c += b"\xE9" + rel32(va + len(c), done)         # jmp done
    apply_at = len(c)
    for f in fix:
        c[f + 1] = apply_at - (f + 2)
    c += bytes.fromhex("8bc7")                      # mov eax,edi
    c += b"\xE8" + rel32(va + len(c), FN_EFFECTS)   # call ExecuteDamageEffects
    c += b"\xE9" + rel32(va + len(c), done)         # jmp done
    return bytes(c)


def cave_ground(va, mask, resume):
    c = bytearray()
    c += bytes.fromhex("ff91e4000000")              # call [ecx+0xE4]  SetHitPoints (displaced)
    c += bytes.fromhex("8bc3 8b10 ff92e0000000".replace(" ", ""))   # mov eax,ebx; mov edx,[eax]; call [edx+0xE0]
    c += bytes.fromhex("84c0")                      # test al,al
    c += b"\x74\x0B"                                # je done (skips 4+2+5 = 11 bytes)
    c += b"\x66\xBA" + struct.pack("<H", mask)      # mov dx,mask
    c += bytes.fromhex("8bc3")                      # mov eax,ebx
    c += b"\xE8" + rel32(va + len(c), FN_EFFECTS)   # call ExecuteDamageEffects
    c += b"\xE9" + rel32(va + len(c), resume)       # jmp resume
    return bytes(c)


# (hook VA, original bytes, cave VA, cave builder)
SITES = [
    (0x557807EB, bytes.fromhex("8a04242c0274062c047412eb1e"), 0x558161C0, lambda va: cave_storm(va)),
    (0x557C7F9E, bytes.fromhex("ff91e4000000"), 0x55816200, lambda va: cave_ground(va, 0x40, 0x557C7FA4)),
    (0x557C910B, bytes.fromhex("ff91e4000000"), 0x55816240, lambda va: cave_ground(va, 0x20, 0x557C9111)),
]


def va2off(d, va):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    n = struct.unpack_from("<H", d, e + 6)[0]
    optsz = struct.unpack_from("<H", d, e + 20)[0]
    for i in range(n):
        s = d[e + 24 + optsz + 40 * i:][:40]
        vs, va0, rs, ra = struct.unpack_from("<IIII", s, 8)
        if va0 <= va - BASE < va0 + max(vs, rs):
            return ra + (va - BASE - va0)
    raise ValueError(hex(va))


def relocs_in(d, ranges):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    n = struct.unpack_from("<H", d, e + 6)[0]
    optsz = struct.unpack_from("<H", d, e + 20)[0]
    hits = []
    for i in range(n):
        s = d[e + 24 + optsz + 40 * i:][:40]
        if s[:6] != b".reloc":
            continue
        rs, ra = struct.unpack_from("<II", s, 16)
        p, end = ra, ra + rs
        while p + 8 <= end:
            pr, sz = struct.unpack_from("<II", d, p)
            if sz == 0:
                break
            for q in range(p + 8, p + sz, 2):
                w = struct.unpack_from("<H", d, q)[0]
                if w >> 12 == 3:
                    va = BASE + pr + (w & 0xFFF)
                    if any(lo <= va < hi or lo < va + 4 <= hi for lo, hi in ranges):
                        hits.append(va)
            p += sz
    return hits


def write_inplace(path, data):
    with open(path, "r+b") as f:
        f.seek(0); f.write(data)


def main():
    ap = argparse.ArgumentParser(description="Divine Storm / Holy Ground Vertigo, Unholy Ground Cursed")
    ap.add_argument("--dll", default=DEFAULT_DLL)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    a = ap.parse_args()
    dll = a.dll
    if a.revert:
        if not os.path.exists(bak_path(dll, BAK)):
            print("no backup"); return 1
        bak = open(bak_path(dll, BAK), "rb").read()
        assert len(bak) == os.path.getsize(dll), "size differs from backup; refusing"
        write_inplace(dll, bak); print("restored AoWEPACK.dll from" + BAK); return 0

    d = bytearray(open(dll, "rb").read())
    assert d[va2off(d, ROLL_HOOK[0])] == ROLL_HOOK[1], "patch_storm_effect_roll_v1 is not applied - apply it first"
    plan = []
    state = set()
    for hook_va, orig, cave_va, build in SITES:
        cave = build(cave_va)
        hook = b"\xE9" + rel32(hook_va, cave_va) + b"\x90" * (len(orig) - 5)
        ho, co = va2off(d, hook_va), va2off(d, cave_va)
        cur = bytes(d[ho:ho + len(orig)])
        if cur == hook and bytes(d[co:co + len(cave)]) == cave:
            state.add("patched")
        elif cur == orig:
            state.add("vanilla")
        else:
            print("hook %#x: unexpected bytes %s" % (hook_va, cur.hex())); return 1
        print("hook %#x (%s) -> cave %#x %d B: %s" % (hook_va, "patched" if cur == hook else "vanilla", cave_va, len(cave), cave.hex()))
        plan.append((ho, hook, co, cave, hook_va, len(orig)))
    if state == {"patched"}:
        print("ALL ALREADY PATCHED"); return 0
    assert state == {"vanilla"}, "mixed state - inspect"
    lo, hi = va2off(d, CAVE_LO), va2off(d, CAVE_HI)
    assert bytes(d[lo:hi]) == b"\0" * (hi - lo), "cave zone %#x..%#x is not zero" % (CAVE_LO, CAVE_HI)
    r = relocs_in(d, [(hv, hv + ln) for _, _, _, _, hv, ln in plan] + [(CAVE_LO, CAVE_HI)])
    assert not r, "reloc entries intersect: " + ", ".join(hex(x) for x in r)
    print("checks OK: roll patch present, vanilla hook sites, zero caves, no relocs")
    if not a.apply:
        print("\nDry run OK. Re-run with --apply to write."); return 0
    if not os.path.exists(bak_path(dll, BAK)):
        shutil.copyfile(dll, bak_path(dll, BAK)); print("backup: AoWEPACK.dll" + BAK)
    for ho, hook, co, cave, _, _ in plan:
        d[ho:ho + len(hook)] = hook
        d[co:co + len(cave)] = cave
    write_inplace(dll, bytes(d))
    back = open(dll, "rb").read()
    for ho, hook, co, cave, _, _ in plan:
        assert back[ho:ho + len(hook)] == hook and back[co:co + len(cave)] == cave, "read-back failed"
    print("applied 3 sites.  Test: Divine Storm (spell/altar) on a low-RES stack -> some units get Vertigo"
          " (never machines); Holy Ground vs evil units -> Vertigo; Unholy Ground vs good units -> Cursed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
