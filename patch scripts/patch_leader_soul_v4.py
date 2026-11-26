#!/usr/bin/env python3
r"""
Leader's Soul v4 (2026-10-22): v3 + the Resurrect/Animate-the-leader placement fix.  AoWEPACK.dll only.
Upgrades a v3 (or v2/v1) zone IN PLACE; every v3 cave keeps its address, v4 caves are appended after v3's.

User retest of v3 (LAN, both machines): Resurrect Hero by the owner on its dead leader ->
"EAccessViolation at 0x557EC271, read of 00000000" / "Exception occured during TSpellTE" - before oj.

Root cause (static):
  0x557EC271 dereferences the result of the hero placer 0x557810FC (edi), which returned nil.  The placer spirals
  outward from the caster's army (ring 0..29, flag byte 5 at 0x557EC40C: bit0 = keep spiralling, bit2 = never
  merge into an army on the hex).  For each hex it builds a TArmyHS, AddChild(hero), then HSE map.Place ->
  TArmyHS VMT+0x110 0x557911F8 -> TArmy.CanBePlacedAt 0x5578DDC4, which for a not-yet-placed army asks EVERY
  unit's VMT+0x180.  THero+0x180 0x55787264 is true for a registered hero ([+0x98] set by THeroControl).
  **TLeader+0x180 0x5578B54C additionally requires 0x557873AC(leader, [player+0xD4]) =
  TEObject.Compare(setup leader, leader) (EngineP: streams both objects and compares the bytes).**  [player+0xD4]
  is the setup TLeader the game was started with (TPlayer 0x55752C58, saved).  A leader that died and was
  revived (Killed flags, the revive status 0x80 / Animate 0x81, XP...) no longer streams identically, so every hex
  fails, the placer returns nil and the TE dereferences it.  This is also why vanilla filters leaders out of the
  Resurrect/Animate pool.  The caster is NOT the problem: TResurrectHero.Cast 0x557EC410 stores the casting unit's
  id ([unit+0x18]) in the TE, TSpellTE.Execute 0x5577994F resolves it and passes it as ecx; TUnitSpellCaster
  0x5577A578 refuses dead casters ([+0x25]&0x10), so the caster is the living hero and 0x5577ED94 returns its
  army's hex.  (Unconfirmed live - the diag counters below confirm it on the next run.)

v4:
  lv   TLeader VMT +0x180 (0x557123B8) -> cave: run the original; if it refuses, accept anyway when the THero part
       (0x55787264) accepts AND the leader is the one being brought back (PICK) or carries the revive status
       0x80 / Animate 0x81 (permanent ability bits, so the revived leader can later join / merge into placed
       armies too).  Every other leader keeps the vanilla setup comparison.
  lc1/lc2  the placement-location calls 0x557EC1C3 / 0x557EC72B (call 0x5577ED94): if the caster's army has no
       map position (0xFF) -> the caster player's army holding the Leader's Soul unit, else the player's first
       army with a map position.  Never a city.  (Belt and braces: with a living caster this never triggers.)
  ng1/ng2  after the placer 0x557EC211 / 0x557EC779 (`mov edi,eax / xor ecx,ecx / mov dl,1`): nil -> clean abort
       instead of the AV: the hero is marked dead again (the [+0x25]&0x10 and [+0x55]&1 bits the revive cleared,
       so it stays in the dead pool), PICK is cleared, and the TE continues at the vanilla "no dead hero" branch
       (0x557EC392 / 0x557EC8FA: message + normal tail).  Deterministic (synced state only) on every machine.
  diag (runtime-only, AoWEPACK .idata slack 0x5590B3C8..0x5590B3D8): +0 TLeader+0x180 refusals, +4 refusals we
       overrode, +8 placer-nil aborts, +0xC location fallbacks used.
Sites lc/ng are plain code; the VMT slot carries a reloc (pointer to our cave is in-image, fine).  Header: v3 site
bytes 0x00..0x7C, VMT table 0x80, return values 0xA0, name 0xC0, v4 site bytes 0xE0..0xFA.
Dry-run default; --apply / --revert / --dis; --dll <scratch copy>.  Backup <game>\backup\AoWEPACK.dll.bak_leadersoul4.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
import patch_leader_soul_v2 as V2
import patch_leader_soul_v3 as V3

DEFAULT_DLL = game_file("AoWEPACK.dll")
BAK_SUFFIX = ".bak_leadersoul4"
CODE_V2F, ZONE, ZONE_END, HDR = V3.CODE_V2F, V3.ZONE, V3.ZONE_END, V3.HDR
EXT_OFF = 0xE0
AB = V3.AB
PICK, DIAG = V3.PICK, 0x5590B3C8
MAPCELL, GETPLAYERS, GETARMY, GETUNIT, GAS = V3.MAPCELL, V3.GETPLAYERS, V3.GETARMY, V3.GETUNIT, V3.GAS
LOC = 0x5577ED94
LEADER180, HERO180 = 0x5578B54C, 0x55787264
LV_SLOT = 0x55712238 + 0x180
e8 = V2.e8
NEW_SITES = [
    ("lc1", 0x557EC1C3, 5, e8(0x557EC1C3, LOC), "call"),
    ("lc2", 0x557EC72B, 5, e8(0x557EC72B, LOC), "call"),
    ("ng1", 0x557EC211, 6, bytes.fromhex("8bf833c9b201"), "jmp"),
    ("ng2", 0x557EC779, 6, bytes.fromhex("8bf833c9b201"), "jmp"),
]
NG = {"ng1": (0x557EC217, 0x557EC392), "ng2": (0x557EC77F, 0x557EC8FA)}
SITES = V3.SITES + NEW_SITES
TARGET = dict(V3.TARGET, lc1="lc", lc2="lc")
PTRS = V3.PTRS
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, va):
    return bytes(ks.asm(src, va)[0])


def build(prev_reg):
    z3, where = V3.build(prev_reg)
    out = bytearray(z3); where = dict(where)

    def place(name, src):
        while len(out) % 16: out.append(0)
        va = ZONE + len(out); where[name] = va
        out.extend(asm(src, va))

    S = {"ab": AB, "pick": PICK, "diag": DIAG, "map": MAPCELL, "gp": GETPLAYERS, "ga": GETARMY, "gu": GETUNIT,
         "gas": GAS, "loc": LOC, "l180": LEADER180, "h180": HERO180}

    # TLeader+0x180 replacement (eax = leader) -> al
    place("lv", """
        push ebx
        mov ebx, eax
        call %(l180)#x
        test al, al
        jne out
        push esi
        call d
    d:
        pop esi
        sub esi, d
        inc dword ptr [esi + %(diag)#x]
        mov eax, ebx
        call %(h180)#x
        test al, al
        je out2
        cmp ebx, [esi + %(pick)#x]
        je allow
        mov eax, ebx
        mov edx, 0x80
        call %(gas)#x
        test al, al
        jne allow
        mov eax, ebx
        mov edx, 0x81
        call %(gas)#x
        test al, al
        jne allow
        xor eax, eax
        jmp out2
    allow:
        inc dword ptr [esi + %(diag)#x + 4]
        mov al, 1
    out2:
        pop esi
    out:
        pop ebx
        ret
    """ % S)

    # placement location (eax caster, edx &x, ecx &y, [esp+4] &z; ret 4)
    place("lc", """
        push ebx
        push esi
        push edi
        push ebp
        mov ebx, eax
        mov esi, edx
        mov edi, ecx
        mov ebp, [esp + 0x14]
        push ebp
        call %(loc)#x
        cmp byte ptr [esi], 0xff
        jne done
        call d
    d:
        pop ecx
        sub ecx, d
        inc dword ptr [ecx + %(diag)#x + 0xc]
        mov eax, [ecx + %(map)#x]
        mov eax, [eax + 0x140]
        movsx edx, byte ptr [ebx + 0x24]
        call %(gp)#x
        test eax, eax
        je done
        push dword ptr [eax + 0x28]
        push 0
    pass_lp:
        mov eax, [esp + 4]
        mov edx, [eax]
        call dword ptr [edx + 0x54]
        push eax
    a_lp:
        dec dword ptr [esp]
        js a_done
        mov edx, [esp]
        mov eax, [esp + 8]
        call %(ga)#x
        test eax, eax
        je a_lp
        cmp dword ptr [esp + 4], 0
        jne try_army
        push eax
        mov edx, [eax]
        call dword ptr [edx + 0x54]
        push eax
    u_lp:
        dec dword ptr [esp]
        js u_none
        mov edx, [esp]
        mov eax, [esp + 4]
        call %(gu)#x
        test eax, eax
        je u_lp
        mov edx, %(ab)d
        call %(gas)#x
        test al, al
        je u_lp
        add esp, 4
        pop eax
        jmp try_army
    u_none:
        add esp, 4
        pop eax
        jmp a_lp
    try_army:
        push ebp
        mov edx, esi
        mov ecx, edi
        mov ebx, [eax]
        call dword ptr [ebx + 0x98]
        cmp byte ptr [esi], 0xff
        je a_lp
        add esp, 12
        jmp done
    a_done:
        add esp, 4
        inc dword ptr [esp]
        cmp dword ptr [esp], 2
        jb pass_lp
        add esp, 8
    done:
        pop ebp
        pop edi
        pop esi
        pop ebx
        ret 4
    """ % S)

    for nm, (back, fail) in NG.items():
        place(nm, """
            test eax, eax
            jne ok
            mov eax, [ebp - 0x14]
            or byte ptr [eax + 0x25], 0x10
            or byte ptr [eax + 0x55], 1
            call d
        d:
            pop eax
            sub eax, d
            mov dword ptr [eax + %(pick)#x], 0
            inc dword ptr [eax + %(diag)#x + 8]
            jmp %(fail)#x
        ok:
            mov edi, eax
            xor ecx, ecx
            mov dl, 1
            jmp %(back)#x
        """ % dict(S, back=back, fail=fail))
    assert ZONE + len(out) <= ZONE_END, hex(ZONE + len(out))
    return bytes(out), where


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dll", default=DEFAULT_DLL)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    d = open(a.dll, "rb").read()
    g = lambda va, n: bytes(d[va - CODE_V2F:va - CODE_V2F + n])
    zl = g(ZONE, ZONE_END - ZONE)
    applied = any(zl[HDR:])
    saved = {}; o = 0
    for name, va, n, _o, _k in V3.SITES: saved[name] = zl[o:o + n]; o += n
    o = EXT_OFF
    for name, va, n, _o, _k in NEW_SITES: saved[name] = zl[o:o + n]; o += n
    saved["lv"] = zl[o:o + 4]; o += 4
    assert o <= HDR, hex(o)
    for i, (name, va, _r) in enumerate(PTRS): saved[name] = zl[V3.TABLE_OFF + 4 * i:V3.TABLE_OFF + 4 * i + 4]
    cur = {name: g(va, n) for name, va, n, _o, _k in SITES}
    cur.update({name: g(va, 4) for name, va, _r in PTRS})
    cur["lv"] = g(LV_SLOT, 4)
    reg_b = saved["reg"] if applied else cur["reg"]
    assert reg_b[0] == 0xE8, "RegisterAbility chain site 0x557BCF6E is not a call (%s)" % reg_b.hex()
    prev_reg = 0x557BCF6E + 5 + struct.unpack_from("<i", reg_b, 1)[0]

    zone4, where = build(prev_reg)
    z3, where3 = V3.build(prev_reg)
    z2, where2 = V2.build(prev_reg)
    code = {"v4": zone4[HDR:], "v3": z3[HDR:], "v2": z2[HDR:], "v1": V2.build(prev_reg, v1=True)[0][HDR:]}
    zver = "zero" if not any(zl) else next((t for t, c in code.items() if zl[HDR:HDR + len(c)] == c
                                            and not any(zl[HDR + len(c):])), "DIFFERS")
    vsites = {"v1": V2.SITES, "v2": V2.SITES, "v3": V3.SITES, "v4": SITES, "zero": []}.get(zver, [])
    hooked_names = {s[0] for s in vsites} | ({"lv"} if zver == "v4" else set())
    # originals: from the header for sites this zone version hooked, else the current (must be vanilla) bytes
    src = {nm: (saved[nm] if (applied and nm in hooked_names) else cur[nm]) for nm in cur}
    for nm, _va, _r in PTRS: src[nm] = saved[nm] if applied else cur[nm]
    if applied and zver != "v4" and any(zl[EXT_OFF:HDR]): zver = "DIFFERS"
    wrong = [(nm, cur[nm].hex()) for nm, _va, _n, orig, _k in SITES
             if orig is not None and nm not in hooked_names and cur[nm] != orig]
    if "lv" not in hooked_names and struct.unpack("<I", cur["lv"])[0] != LEADER180: wrong.append(("lv", cur["lv"].hex()))
    if zver != "DIFFERS" and wrong: print("ABORT: sites not in the expected (vanilla) state: %s" % wrong); return 1
    if not applied:
        for nm, _va, _r in PTRS:
            x = struct.unpack("<I", cur[nm])[0]
            assert 0x55700000 < x < 0x558E8000 and not (ZONE <= x < ZONE_END), (nm, hex(x))

    hdr = bytearray(zone4[:HDR]); o = 0
    for name, va, n, _o, _k in V3.SITES: hdr[o:o + n] = src[name]; o += n
    o = EXT_OFF
    for name, va, n, _o, _k in NEW_SITES: hdr[o:o + n] = src[name]; o += n
    hdr[o:o + 4] = src["lv"]
    for i, (name, va, _r) in enumerate(PTRS): hdr[V3.TABLE_OFF + 4 * i:V3.TABLE_OFF + 4 * i + 4] = src[name]
    zone = bytes(hdr) + zone4[HDR:]

    def hooks(wh, sites, target):
        h = {name: V2.rel(0xE8 if kind == "call" else 0xE9, va, wh[target.get(name, name)], n)
             for name, va, n, _o, kind in sites}
        h.update({name: struct.pack("<I", wh["t%d" % i]) for i, (name, va, _r) in enumerate(PTRS)})
        return h
    hooked = hooks(where, SITES, TARGET); hooked["lv"] = struct.pack("<I", where["lv"])
    allsites = [(nm, va, n) for nm, va, n, _o, _k in SITES] + [(nm, va, 4) for nm, va, _r in PTRS] + [("lv", LV_SLOT, 4)]
    if zver in ("v1", "v2"): exp = dict(src, **hooks(where2, V2.SITES, V2.TARGET))
    elif zver == "v3": exp = dict(src, **hooks(where3, V3.SITES, V3.TARGET))
    elif zver == "v4": exp = hooked
    else: exp = src
    mixed = [nm for nm, _va, _n in allsites if cur[nm] != exp[nm]]
    rl = V2.reloc_set(d)
    bad = [hex(r) for r in rl if ZONE - 3 <= r < ZONE_END or any(va - 3 <= r < va + n for _nm, va, n, _o, _k in SITES)]
    ptr_reloc_ok = all(va in rl for _nm, va, _r in PTRS) and LV_SLOT in rl
    print("zone %s (%d B used of %d) | relocs in zone/sites %s | slot relocs %s | mismatched %s | reg prev %#x"
          % (zver, len(zone), ZONE_END - ZONE, bad or "none", "ok" if ptr_reloc_ok else "MISSING", mixed or "none",
             prev_reg))
    print("v4 caves: " + ", ".join("%s=%#x" % (k, where[k]) for k in ("lv", "lc", "ng1", "ng2")))
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        for k in ("lv", "lc", "ng1", "ng2"):
            print("  %s:" % k)
            off = where[k] - ZONE
            for i in md.disasm(zone[off:off + 0x140], where[k]):
                print("   %08X  %-24s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
                if i.mnemonic in ("ret", "jmp") and i.op_str.startswith("0x557e") or i.mnemonic == "ret" and k == "lc" and i.op_str == "4": break
    if bad or not ptr_reloc_ok or zver == "DIFFERS" or mixed: print("ABORT"); return 1

    if a.revert:
        if not applied: print("already reverted"); return 0
        out = bytearray(d)
        for nm, va, n in allsites: out[va - CODE_V2F:va - CODE_V2F + n] = src[nm]
        out[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
        write(a, bytes(out), "reverted %s (sites + VMT slots restored from the zone header)" % zver); return 0
    if zver == "v4": print("already applied (v4)"); return 0
    out = bytearray(d)
    out[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
    out[ZONE - CODE_V2F:ZONE - CODE_V2F + len(zone)] = zone
    for nm, va, n in allsites: out[va - CODE_V2F:va - CODE_V2F + n] = hooked[nm]
    if zver != "zero": print("upgrading the %s zone in place" % zver)
    print("%d bytes change" % sum(1 for x, y in zip(d, out) if x != y))
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    write(a, bytes(out), "Written and verified (v4)"); return 0


def write(a, data, msg):
    if os.path.abspath(a.dll) == os.path.abspath(DEFAULT_DLL):
        bak = bak_path(a.dll, BAK_SUFFIX)
        if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    V2.write_inplace(a.dll, data); assert open(a.dll, "rb").read() == data; print(msg)


if __name__ == "__main__":
    sys.exit(main())
