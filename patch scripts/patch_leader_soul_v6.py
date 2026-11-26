#!/usr/bin/env python3
r"""
Leader's Soul v6 (2026-10-22): v5 + the returning leader joins the CASTER's stack.  AoWEPACK.dll only.
Upgrades a v5 (or v4/v3/v2/v1) zone IN PLACE.

v5 live (LAN): works - both machines STAGE 8 / AddChild 1, clean exit.  User change: the leader should come back at
the CASTER (the hero that cast Resurrect / Animate Hero), not at the soul.

v6: pj6 in front of v5's pj at the placer calls 0x557EC20C / 0x557EC774.  For the picked leader:
  1. the caster's stack: caster = the TE's casting unit [ebp-0xC], its army [caster+4] (IsClass TArmy, cell
     0x557130AC) -> TArmy.AddChild (VMT+0xAC; TArmy.Add asks the leader's +0x180 = v4 lv, which accepts PICK);
     success = AddChild true, [leader+4] == that army, [army+0x20] TArmyHS -> returned as the placer result;
  2. else (stack full / no army) -> v5 pj: the Leader's Soul unit's stack;
  3. else the vanilla placer near the caster with the v4/v5 nil guard.
  oj is unchanged: it removes the soul wherever it is (possessed body -> normal unit in place, Incarnate killed).
  The coin flip and the own-dead-heroes rule (v5 rpc5) are unchanged.
  Breadcrumb STAGE adds 10 = caster-stack join attempt, 11 = joined the caster's stack (then 7/8 from oj).
Header layout = v5.  Dry-run default; --apply / --revert / --dis; --dll <scratch copy>.
Backup <game>\backup\AoWEPACK.dll.bak_leadersoul6.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
import patch_leader_soul_v2 as V2
import patch_leader_soul_v3 as V3
import patch_leader_soul_v4 as V4
import patch_leader_soul_v5 as V5

DEFAULT_DLL = game_file("AoWEPACK.dll")
BAK_SUFFIX = ".bak_leadersoul6"
TARMY_CELL, ISCLASS = 0x557130AC, V3.ISCLASS
ARMYHS_CELL, ARMYHS_CREATE, HEXCHECK, PLACEHX, FREE = 0x55713360, 0x557908BC, 0x55781008, 0x557025F4, 0x557010B8
WALKINIT, WALKNEXT = 0x557026D4, 0x557026DC
CODE_V2F, ZONE, ZONE_END, HDR = V3.CODE_V2F, V3.ZONE, V3.ZONE_END, V3.HDR
AB, FOUND, PICK, DIAG = V3.AB, V3.FOUND, V3.PICK, V4.DIAG
STAGE, HERO, SARMY, JOIN, TRIES = DIAG + 0x10, DIAG + 0x14, DIAG + 0x18, DIAG + 0x1C, DIAG + 0x20
PLACER = 0x557810FC
e8 = V2.e8
PJ_SITES = [("pj1", 0x557EC20C, 5, e8(0x557EC20C, PLACER), "call"),
            ("pj2", 0x557EC774, 5, e8(0x557EC774, PLACER), "call")]
PJ_OFF = {"pj1": 0xD8, "pj2": 0xFA}
SITES = V4.SITES + PJ_SITES
TARGET = dict(V4.TARGET, oj1="ojw", oj2="ojw", ng1="ng5_1", ng2="ng5_2")
PTRS, LV_SLOT = V3.PTRS, V4.LV_SLOT
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, va):
    return bytes(ks.asm(src, va)[0])


def build(prev_reg):
    z5, where = V5.build(prev_reg)
    out = bytearray(z5); where = dict(where)

    def place(name, src):
        while len(out) % 16: out.append(0)
        va = ZONE + len(out); where[name] = va
        out.extend(asm(src, va))

    S = {"pick": PICK, "stage": STAGE, "sarmy": SARMY, "join": JOIN, "tries": TRIES, "cell": TARMY_CELL,
         "isclass": ISCLASS, "map": V3.MAPCELL, "hscell": ARMYHS_CELL, "hsnew": ARMYHS_CREATE, "sp": V3.SETPLAYER,
         "hexok": HEXCHECK, "place": PLACEHX, "free": FREE, "winit": WALKINIT, "wnext": WALKNEXT}
    place("pj6", """
        push esi
        call d
    d:
        pop esi
        sub esi, d
        cmp eax, [esi + %(pick)#x]
        jne go
        test eax, eax
        je go
        pushad
        mov ebx, eax
        mov dword ptr [esi + %(tries)#x], 0
        mov dword ptr [esi + %(sarmy)#x], 0
        mov eax, [ebp - 0xc]
        test eax, eax
        je ring
        mov edi, [eax + 4]
        test edi, edi
        je ring
        mov eax, edi
        mov edx, [esi + %(cell)#x]
        call %(isclass)#x
        test al, al
        je ring
        mov dword ptr [esi + %(stage)#x], 10
        mov [esi + %(sarmy)#x], edi
        mov eax, edi
        mov edx, ebx
        mov ecx, [eax]
        call dword ptr [ecx + 0xac]
        movzx eax, al
        mov [esi + %(join)#x], eax
        test eax, eax
        je ring
        cmp [ebx + 4], edi
        jne ring
        mov eax, [edi + 0x20]
        test eax, eax
        je ring
        mov dword ptr [esi + %(stage)#x], 11
        mov [esp + 0x1c], eax
        popad
        pop esi
        ret 0xc

    ring:
        mov dword ptr [esi + %(stage)#x], 12
        sub esp, 0x28
        mov eax, [esp + 0x58]
        mov [esp + 0x20], eax
        movzx eax, byte ptr [ebx + 0x24]
        mov [esp + 0x24], eax
        push 0
        mov ecx, [esp + 0x44]
        mov edx, [esp + 0x40]
        lea eax, [esp + 4]
        call %(winit)#x
    rl:
        mov eax, esp
        call %(wnext)#x
        cmp dword ptr [esp + 0xc], 0x1e
        jge rfail
        push dword ptr [esp + 0x20]
        push dword ptr [esp + 0x28]
        push 5
        mov ecx, [esp + 0x20]
        mov edx, [esp + 0x1c]
        mov eax, ebx
        call %(hexok)#x
        test al, al
        je rl
        inc dword ptr [esi + %(tries)#x]
        mov eax, [esi + %(hscell)#x]
        xor ecx, ecx
        mov dl, 1
        call %(hsnew)#x
        mov edi, eax
        mov eax, [edi + 0x1c]
        mov edx, [esp + 0x24]
        call %(sp)#x
        mov eax, [edi + 0x1c]
        mov edx, ebx
        mov ecx, [eax]
        call dword ptr [ecx + 0xac]
        test al, al
        je rfree
        mov eax, [edi + 0x1c]
        cmp [ebx + 4], eax
        jne rdetach
        push dword ptr [esp + 0x14]
        push dword ptr [esp + 0x24]
        mov ecx, [esp + 0x18]
        mov edx, edi
        mov eax, [esi + %(map)#x]
        call %(place)#x
        test al, al
        jne rok
    rdetach:
        mov eax, ebx
        xor edx, edx
        mov ecx, [eax]
        call dword ptr [ecx + 8]
    rfree:
        mov eax, edi
        call %(free)#x
        jmp rl
    rok:
        add esp, 0x28
        mov eax, [edi + 0x1c]
        mov [esi + %(sarmy)#x], eax
        mov dword ptr [esi + %(stage)#x], 13
        mov [esp + 0x1c], edi
        popad
        pop esi
        ret 0xc
    rfail:
        add esp, 0x28
        mov dword ptr [esi + %(stage)#x], 14
        mov dword ptr [esp + 0x1c], 0
        popad
        pop esi
        ret 0xc
    go:
        pop esi
        jmp %(placer)#x
    """ % dict(S, placer=PLACER))
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
    o = V4.EXT_OFF
    for name, va, n, _o, _k in V4.NEW_SITES: saved[name] = zl[o:o + n]; o += n
    saved["lv"] = zl[o:o + 4]; o += 4
    for name, va, n, _o, _k in PJ_SITES: saved[name] = zl[PJ_OFF[name]:PJ_OFF[name] + n]
    for i, (name, va, _r) in enumerate(PTRS): saved[name] = zl[V3.TABLE_OFF + 4 * i:V3.TABLE_OFF + 4 * i + 4]
    cur = {name: g(va, n) for name, va, n, _o, _k in SITES}
    cur.update({name: g(va, 4) for name, va, _r in PTRS})
    cur["lv"] = g(LV_SLOT, 4)
    reg_b = saved["reg"] if applied else cur["reg"]
    assert reg_b[0] == 0xE8, "RegisterAbility chain site 0x557BCF6E is not a call (%s)" % reg_b.hex()
    prev_reg = 0x557BCF6E + 5 + struct.unpack_from("<i", reg_b, 1)[0]

    zone6, where = build(prev_reg)
    z5, where5 = V5.build(prev_reg)
    z4, where4 = V4.build(prev_reg)
    z3, where3 = V3.build(prev_reg)
    z2, where2 = V2.build(prev_reg)
    code = {"v6": zone6[HDR:], "v5": z5[HDR:], "v4": z4[HDR:], "v3": z3[HDR:], "v2": z2[HDR:],
            "v1": V2.build(prev_reg, v1=True)[0][HDR:]}
    zver = "zero" if not any(zl) else next((t for t, c in code.items() if zl[HDR:HDR + len(c)] == c
                                            and not any(zl[HDR + len(c):])), "DIFFERS")
    vsites = {"v1": V2.SITES, "v2": V2.SITES, "v3": V3.SITES, "v4": V4.SITES, "v5": SITES, "v6": SITES}.get(zver, [])
    hooked_names = {s[0] for s in vsites} | ({"lv"} if zver in ("v4", "v5", "v6") else set())
    src = {nm: (saved[nm] if (applied and nm in hooked_names) else cur[nm]) for nm in cur}
    for nm, _va, _r in PTRS: src[nm] = saved[nm] if applied else cur[nm]
    if applied and zver not in ("v4", "v5", "v6") and any(zl[V4.EXT_OFF:HDR]): zver = "DIFFERS"
    if applied and zver not in ("v5", "v6") and any(zl[0xD8:0xDD]): zver = "DIFFERS"
    wrong = [(nm, cur[nm].hex()) for nm, _va, _n, orig, _k in SITES
             if orig is not None and nm not in hooked_names and cur[nm] != orig]
    if "lv" not in hooked_names and struct.unpack("<I", cur["lv"])[0] != V4.LEADER180: wrong.append(("lv", cur["lv"].hex()))
    if zver != "DIFFERS" and wrong: print("ABORT: sites not in the expected (vanilla) state: %s" % wrong); return 1
    if not applied:
        for nm, _va, _r in PTRS:
            x = struct.unpack("<I", cur[nm])[0]
            assert 0x55700000 < x < 0x558E8000 and not (ZONE <= x < ZONE_END), (nm, hex(x))

    hdr = bytearray(zone6[:HDR]); o = 0
    for name, va, n, _o, _k in V3.SITES: hdr[o:o + n] = src[name]; o += n
    o = V4.EXT_OFF
    for name, va, n, _o, _k in V4.NEW_SITES: hdr[o:o + n] = src[name]; o += n
    hdr[o:o + 4] = src["lv"]
    for name, va, n, _o, _k in PJ_SITES: hdr[PJ_OFF[name]:PJ_OFF[name] + n] = src[name]
    for i, (name, va, _r) in enumerate(PTRS): hdr[V3.TABLE_OFF + 4 * i:V3.TABLE_OFF + 4 * i + 4] = src[name]
    zone = bytes(hdr) + zone6[HDR:]

    def hooks(wh, sites, target):
        h = {name: V2.rel(0xE8 if kind == "call" else 0xE9, va, wh[target.get(name, name)], n)
             for name, va, n, _o, kind in sites}
        h.update({name: struct.pack("<I", wh["t%d" % i]) for i, (name, va, _r) in enumerate(PTRS)})
        return h
    TARGET["pj1"] = TARGET["pj2"] = "pj6"
    hooked = hooks(where, SITES, TARGET); hooked["lv"] = struct.pack("<I", where["lv"])
    allsites = [(nm, va, n) for nm, va, n, _o, _k in SITES] + [(nm, va, 4) for nm, va, _r in PTRS] + [("lv", LV_SLOT, 4)]
    if zver in ("v1", "v2"): exp = dict(src, **hooks(where2, V2.SITES, V2.TARGET))
    elif zver == "v3": exp = dict(src, **hooks(where3, V3.SITES, V3.TARGET))
    elif zver == "v4":
        exp = dict(src, **hooks(where4, V4.SITES, V4.TARGET)); exp["lv"] = struct.pack("<I", where4["lv"])
    elif zver == "v5":
        t5 = dict(TARGET, pj1="pj", pj2="pj")
        exp = dict(src, **hooks(where5, SITES, t5)); exp["lv"] = struct.pack("<I", where5["lv"])
    elif zver == "v6": exp = hooked
    else: exp = src
    mixed = [nm for nm, _va, _n in allsites if cur[nm] != exp[nm]]
    rl = V2.reloc_set(d)
    bad = [hex(r) for r in rl if ZONE - 3 <= r < ZONE_END or any(va - 3 <= r < va + n for _nm, va, n, _o, _k in SITES)]
    ptr_reloc_ok = all(va in rl for _nm, va, _r in PTRS) and LV_SLOT in rl
    print("zone %s (%d B used of %d) | relocs in zone/sites %s | slot relocs %s | mismatched %s | reg prev %#x"
          % (zver, len(zone), ZONE_END - ZONE, bad or "none", "ok" if ptr_reloc_ok else "MISSING", mixed or "none",
             prev_reg))
    print("v6 caves: " + ", ".join("%s=%#x" % (k, where[k]) for k in ("rpc5", "pj", "pj6", "ojw", "ng5_1", "ng5_2")))
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        for k in ("rpc5", "pj", "pj6", "ojw", "ng5_1", "ng5_2"):
            print("  %s:" % k)
            off = where[k] - ZONE; end = min([v - ZONE for v in where.values() if v > where[k]] + [len(zone)])
            for i in md.disasm(zone[off:end], where[k]):
                print("   %08X  %-24s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad or not ptr_reloc_ok or zver == "DIFFERS" or mixed: print("ABORT"); return 1

    if a.revert:
        if not applied: print("already reverted"); return 0
        out = bytearray(d)
        for nm, va, n in allsites: out[va - CODE_V2F:va - CODE_V2F + n] = src[nm]
        out[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
        write(a, bytes(out), "reverted %s (sites + VMT slots restored from the zone header)" % zver); return 0
    if zver == "v6": print("already applied (v6)"); return 0
    out = bytearray(d)
    out[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
    out[ZONE - CODE_V2F:ZONE - CODE_V2F + len(zone)] = zone
    for nm, va, n in allsites: out[va - CODE_V2F:va - CODE_V2F + n] = hooked[nm]
    if zver != "zero": print("upgrading the %s zone in place" % zver)
    print("%d bytes change" % sum(1 for x, y in zip(d, out) if x != y))
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    write(a, bytes(out), "Written and verified (v6)"); return 0


def write(a, data, msg):
    if os.path.abspath(a.dll) == os.path.abspath(DEFAULT_DLL):
        bak = bak_path(a.dll, BAK_SUFFIX)
        if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    V2.write_inplace(a.dll, data); assert open(a.dll, "rb").read() == data; print(msg)


if __name__ == "__main__":
    sys.exit(main())
