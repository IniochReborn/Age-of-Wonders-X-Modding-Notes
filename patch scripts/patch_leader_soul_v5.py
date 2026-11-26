#!/usr/bin/env python3
r"""
Leader's Soul v5 (2026-10-22): v4 + leader-return rework after the v4 LAN test.  AoWEPACK.dll only.
Upgrades a v4 (or v3/v2/v1) zone IN PLACE (every site is rewritten; v4's rpc/ng caves stay in the zone unused).

User test of v4 (LAN, own living hero casts on the dead leader, soul alive):
  1. "no other hero was dead" and the spell revived nothing.  User rule: the leader is GUARANTEED unless the
     player would really get another hero.
  2. coin flip -> leader: cast fx, then "Exception occured during TSpellTE" + an AV through a garbage method pointer
     in VCL30 (freed object), spell not consumed; Runtime error 217 at exit (heap corruption).

Findings (static):
  * Vanilla pool (0x557EC110..0x557EC1A5): a copy of the map's THeroControl ([map+0xF8]) taking EVERY hero with
    the dead bit [+0x55]&1 - any owner (other players' and independents' dead heroes too) - then minus TLeaders
    (IsClass) and minus heroes whose level 0x55787740 > [castingPlayer+0x6C]+2.  So "no other hero of mine is dead"
    still leaves a non-empty pool (an enemy / independent dead hero) -> v3/v4 flipped the coin and on tails let
    vanilla revive a stranger (placed as an independent next to the caster, OfferToJoin false - easy to miss) ->
    "nothing came back".
  * The leader placement went through the vanilla placer 0x557810FC: per hex it creates a TArmyHS + TArmy,
    AddChild(hero) and only THEN asks HSE map.Place; when Place refuses, the placer FREES the TArmyHS
    (0x557810B8 -> TArmyHS.Destroy 0x557908FC frees its TArmy, whose EngineP list destructor drops the hero it
    holds) and moves on to the next hex with the same hero.  For a normal hero the hex pre-check makes that
    path rare; for the revived leader it is the main suspect for the freed-object AV + 217 (the leader object
    / its parent link no longer valid).  v5 no longer uses the placer for the leader at all.

v5:
  rpc5 (replaces rpc for rp1/rp2): FOUND -> count the pool heroes whose death owner [hero+0x5C] is the caster's
       player.  None -> the leader, always.  Otherwise the synced coin flip (TAoWHSMap.Random(map,2), as v3): 0 ->
       the leader, 1 -> the vanilla pool untouched.
  pj1/pj2 (the placer calls 0x557EC20C / 0x557EC774): hero == PICK -> the leader JOINS THE ARMY OF THE LEADER'S
       SOUL UNIT (the caster player's army holding 0xCE): TArmy.AddChild (VMT+0xAC; TArmy.Add asks the leader's
       VMT+0x180 = v4 lv, which accepts PICK) and returns that army's TArmyHS ([army+0x20]) as the placer result,
       so the event log / OfferToJoin / oj run unchanged.  oj then removes the soul from that same stack (an
       Incarnate is killed with the stack still holding the leader, a possessed body turns back into a normal
       unit).  No new army, no map.Place, nothing freed.  Join refused (stack full, no soul army) -> the vanilla
       placer as before (with v4 lv + ng as the last resort).
  ojw  wrapper around v3 oj (oj1/oj2 sites) - breadcrumbs only.
  ng5  = v4 ng + breadcrumbs.
  diag (runtime only, 0x5590B3C8): +0 lv refusals, +4 lv overrides, +8 placer-nil aborts, +0xC location fallbacks,
       +0x10 STAGE (1 leader picked, 2 coin tails, 3 join attempt, 4 joined soul army, 5 join refused -> placer,
       6 placer returned an army, 7 oj entered, 8 oj left, 9 placer nil -> clean abort), +0x14 hero, +0x18 soul
       army, +0x1C AddChild result.  Read with leader_soul_probe.py (also works while an error dialog is open).
Header: v3 sites 0x00..0x7C, table 0x80, return values 0xA0, name 0xC0..0xD6, pj1 0xD8, v4 sites 0xE0..0xFA, pj2 0xFA.
Dry-run default; --apply / --revert / --dis; --dll <scratch copy>.  Backup <game>\backup\AoWEPACK.dll.bak_leadersoul5.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
import patch_leader_soul_v2 as V2
import patch_leader_soul_v3 as V3
import patch_leader_soul_v4 as V4

DEFAULT_DLL = game_file("AoWEPACK.dll")
BAK_SUFFIX = ".bak_leadersoul5"
CODE_V2F, ZONE, ZONE_END, HDR = V3.CODE_V2F, V3.ZONE, V3.ZONE_END, V3.HDR
AB, FOUND, PICK, DIAG = V3.AB, V3.FOUND, V3.PICK, V4.DIAG
STAGE, HERO, SARMY, JOIN = DIAG + 0x10, DIAG + 0x14, DIAG + 0x18, DIAG + 0x1C
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
    z4, where = V4.build(prev_reg)
    out = bytearray(z4); where = dict(where)

    def place(name, src):
        while len(out) % 16: out.append(0)
        va = ZONE + len(out); where[name] = va
        out.extend(asm(src, va))

    S = {"ab": AB, "found": FOUND, "pick": PICK, "diag": DIAG, "stage": STAGE, "hero": HERO, "sarmy": SARMY,
         "join": JOIN, "map": V3.MAPCELL, "mapptr": V3.MAPPTR, "rnd": V3.RANDOM, "gp": V3.GETPLAYERS,
         "ga": V3.GETARMY, "gu": V3.GETUNIT, "gh": V3.GETHERO, "gas": V3.GAS, "placer": PLACER,
         "oj": where["oj"]}

    # pool pick (esi = pool THeroList, ebp = ExecuteTE frame, [ebp-0xC] = caster unit)
    place("rpc5", """
        push ebx
        push edi
        call d
    d:
        pop edi
        sub edi, d
        mov ebx, [edi + %(found)#x]
        mov dword ptr [edi + %(found)#x], 0
        mov dword ptr [edi + %(pick)#x], 0
        test ebx, ebx
        je out
        mov eax, [ebp - 0xc]
        movzx eax, byte ptr [eax + 0x24]
        push eax
        mov eax, esi
        mov edx, [eax]
        call dword ptr [edx + 0x54]
        push eax
        push 0
    cl_lp:
        dec dword ptr [esp + 4]
        js cl_done
        mov edx, [esp + 4]
        mov eax, esi
        call %(gh)#x
        test eax, eax
        je cl_lp
        mov dl, [eax + 0x5c]
        cmp dl, [esp + 8]
        jne cl_lp
        inc dword ptr [esp]
        jmp cl_lp
    cl_done:
        pop eax
        add esp, 8
        test eax, eax
        je take
        mov eax, [edi + %(mapptr)#x]
        mov eax, [eax]
        mov edx, 2
        call %(rnd)#x
        test eax, eax
        je take
        mov dword ptr [edi + %(stage)#x], 2
        jmp out
    take:
        mov [edi + %(pick)#x], ebx
        mov dword ptr [edi + %(stage)#x], 1
        mov eax, esi
        mov edx, [eax]
        call dword ptr [edx + 0x54]
        push eax
    lp:
        dec dword ptr [esp]
        js ldone
        mov edx, [esp]
        mov eax, esi
        call %(gh)#x
        test eax, eax
        je lp
        mov edx, eax
        mov eax, esi
        mov ecx, [eax]
        call dword ptr [ecx + 0x6c]
        jmp lp
    ldone:
        add esp, 4
        mov edx, ebx
        mov eax, esi
        mov ecx, [eax]
        call dword ptr [ecx + 0x70]
    out:
        pop edi
        pop ebx
        ret
    """ % S)

    # placer call: eax hero, edx x, ecx y, stack z/owner/flags (callee pops 0xC)
    place("pj", """
        push esi
        call d
    d:
        pop esi
        sub esi, d
        cmp eax, [esi + %(pick)#x]
        jne van
        test eax, eax
        je van
        mov dword ptr [esi + %(stage)#x], 3
        mov [esi + %(hero)#x], eax
        mov dword ptr [esi + %(sarmy)#x], 0
        pushad
        mov ebx, eax
        movsx edx, byte ptr [ebx + 0x24]
        mov eax, [esi + %(map)#x]
        mov eax, [eax + 0x140]
        call %(gp)#x
        test eax, eax
        je fail
        mov ebp, [eax + 0x28]
        mov eax, ebp
        mov edx, [eax]
        call dword ptr [edx + 0x54]
        mov edi, eax
    al_lp:
        dec edi
        js fail
        mov edx, edi
        mov eax, ebp
        call %(ga)#x
        test eax, eax
        je al_lp
        push eax
        mov edx, [eax]
        call dword ptr [edx + 0x54]
        push eax
    ul_lp:
        dec dword ptr [esp]
        js ul_none
        mov edx, [esp]
        mov eax, [esp + 4]
        call %(gu)#x
        test eax, eax
        je ul_lp
        mov edx, %(ab)d
        call %(gas)#x
        test al, al
        je ul_lp
        add esp, 4
        pop eax
        mov [esi + %(sarmy)#x], eax
        push eax
        mov edx, ebx
        mov ecx, [eax]
        call dword ptr [ecx + 0xac]
        pop edx
        movzx eax, al
        mov [esi + %(join)#x], eax
        test eax, eax
        je fail
        cmp [ebx + 4], edx
        jne fail
        mov eax, [edx + 0x20]
        test eax, eax
        je fail
        mov dword ptr [esi + %(stage)#x], 4
        mov [esp + 0x1c], eax
        popad
        pop esi
        ret 0xc
    ul_none:
        add esp, 4
        pop eax
        jmp al_lp
    fail:
        mov dword ptr [esi + %(stage)#x], 5
        popad
    van:
        pop esi
        jmp %(placer)#x
    """ % S)
    S["pj"] = where["pj"]

    place("ojw", """
        push esi
        call d
    d:
        pop esi
        sub esi, d
        mov dword ptr [esi + %(stage)#x], 7
        pop esi
        call %(oj)#x
        push esi
        call d2
    d2:
        pop esi
        sub esi, d2
        mov dword ptr [esi + %(stage)#x], 8
        pop esi
        ret
    """ % S)

    for nm, (back, fail) in V4.NG.items():
        place("ng5_" + nm[-1], """
            push eax
            call d
        d:
            pop eax
            sub eax, d
            xchg eax, [esp]
            test eax, eax
            jne ok
            pop eax
            mov dword ptr [eax + %(stage)#x], 9
            mov dword ptr [eax + %(pick)#x], 0
            inc dword ptr [eax + %(diag)#x + 8]
            mov eax, [ebp - 0x14]
            or byte ptr [eax + 0x25], 0x10
            or byte ptr [eax + 0x55], 1
            jmp %(fail)#x
        ok:
            xchg eax, [esp]
            cmp dword ptr [eax + %(stage)#x], 5
            jne keep
            mov dword ptr [eax + %(stage)#x], 6
        keep:
            pop eax
            mov edi, eax
            xor ecx, ecx
            mov dl, 1
            jmp %(back)#x
        """ % dict(S, back=back, fail=fail))

    # rp1/rp2 (v3 caves) start with `call rpc` -> call rpc5
    for nm in ("rp1", "rp2"):
        off = where[nm] - ZONE
        assert out[off] == 0xE8 and off + 5 + struct.unpack_from("<i", out, off + 1)[0] + ZONE == where["rpc"], nm
        out[off:off + 5] = e8(where[nm], where["rpc5"])
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

    zone5, where = build(prev_reg)
    z4, where4 = V4.build(prev_reg)
    z3, where3 = V3.build(prev_reg)
    z2, where2 = V2.build(prev_reg)
    code = {"v5": zone5[HDR:], "v4": z4[HDR:], "v3": z3[HDR:], "v2": z2[HDR:],
            "v1": V2.build(prev_reg, v1=True)[0][HDR:]}
    zver = "zero" if not any(zl) else next((t for t, c in code.items() if zl[HDR:HDR + len(c)] == c
                                            and not any(zl[HDR + len(c):])), "DIFFERS")
    vsites = {"v1": V2.SITES, "v2": V2.SITES, "v3": V3.SITES, "v4": V4.SITES, "v5": SITES}.get(zver, [])
    hooked_names = {s[0] for s in vsites} | ({"lv"} if zver in ("v4", "v5") else set())
    src = {nm: (saved[nm] if (applied and nm in hooked_names) else cur[nm]) for nm in cur}
    for nm, _va, _r in PTRS: src[nm] = saved[nm] if applied else cur[nm]
    if applied and zver not in ("v4", "v5") and any(zl[V4.EXT_OFF:HDR]): zver = "DIFFERS"
    if applied and zver != "v5" and any(zl[0xD8:0xDD]): zver = "DIFFERS"
    wrong = [(nm, cur[nm].hex()) for nm, _va, _n, orig, _k in SITES
             if orig is not None and nm not in hooked_names and cur[nm] != orig]
    if "lv" not in hooked_names and struct.unpack("<I", cur["lv"])[0] != V4.LEADER180: wrong.append(("lv", cur["lv"].hex()))
    if zver != "DIFFERS" and wrong: print("ABORT: sites not in the expected (vanilla) state: %s" % wrong); return 1
    if not applied:
        for nm, _va, _r in PTRS:
            x = struct.unpack("<I", cur[nm])[0]
            assert 0x55700000 < x < 0x558E8000 and not (ZONE <= x < ZONE_END), (nm, hex(x))

    hdr = bytearray(zone5[:HDR]); o = 0
    for name, va, n, _o, _k in V3.SITES: hdr[o:o + n] = src[name]; o += n
    o = V4.EXT_OFF
    for name, va, n, _o, _k in V4.NEW_SITES: hdr[o:o + n] = src[name]; o += n
    hdr[o:o + 4] = src["lv"]
    for name, va, n, _o, _k in PJ_SITES: hdr[PJ_OFF[name]:PJ_OFF[name] + n] = src[name]
    for i, (name, va, _r) in enumerate(PTRS): hdr[V3.TABLE_OFF + 4 * i:V3.TABLE_OFF + 4 * i + 4] = src[name]
    zone = bytes(hdr) + zone5[HDR:]

    def hooks(wh, sites, target):
        h = {name: V2.rel(0xE8 if kind == "call" else 0xE9, va, wh[target.get(name, name)], n)
             for name, va, n, _o, kind in sites}
        h.update({name: struct.pack("<I", wh["t%d" % i]) for i, (name, va, _r) in enumerate(PTRS)})
        return h
    TARGET["pj1"] = TARGET["pj2"] = "pj"
    hooked = hooks(where, SITES, TARGET); hooked["lv"] = struct.pack("<I", where["lv"])
    allsites = [(nm, va, n) for nm, va, n, _o, _k in SITES] + [(nm, va, 4) for nm, va, _r in PTRS] + [("lv", LV_SLOT, 4)]
    if zver in ("v1", "v2"): exp = dict(src, **hooks(where2, V2.SITES, V2.TARGET))
    elif zver == "v3": exp = dict(src, **hooks(where3, V3.SITES, V3.TARGET))
    elif zver == "v4":
        exp = dict(src, **hooks(where4, V4.SITES, V4.TARGET)); exp["lv"] = struct.pack("<I", where4["lv"])
    elif zver == "v5": exp = hooked
    else: exp = src
    mixed = [nm for nm, _va, _n in allsites if cur[nm] != exp[nm]]
    rl = V2.reloc_set(d)
    bad = [hex(r) for r in rl if ZONE - 3 <= r < ZONE_END or any(va - 3 <= r < va + n for _nm, va, n, _o, _k in SITES)]
    ptr_reloc_ok = all(va in rl for _nm, va, _r in PTRS) and LV_SLOT in rl
    print("zone %s (%d B used of %d) | relocs in zone/sites %s | slot relocs %s | mismatched %s | reg prev %#x"
          % (zver, len(zone), ZONE_END - ZONE, bad or "none", "ok" if ptr_reloc_ok else "MISSING", mixed or "none",
             prev_reg))
    print("v5 caves: " + ", ".join("%s=%#x" % (k, where[k]) for k in ("rpc5", "pj", "ojw", "ng5_1", "ng5_2")))
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        for k in ("rpc5", "pj", "ojw", "ng5_1", "ng5_2"):
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
    if zver == "v5": print("already applied (v5)"); return 0
    out = bytearray(d)
    out[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
    out[ZONE - CODE_V2F:ZONE - CODE_V2F + len(zone)] = zone
    for nm, va, n in allsites: out[va - CODE_V2F:va - CODE_V2F + n] = hooked[nm]
    if zver != "zero": print("upgrading the %s zone in place" % zver)
    print("%d bytes change" % sum(1 for x, y in zip(d, out) if x != y))
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    write(a, bytes(out), "Written and verified (v5)"); return 0


def write(a, data, msg):
    if os.path.abspath(a.dll) == os.path.abspath(DEFAULT_DLL):
        bak = bak_path(a.dll, BAK_SUFFIX)
        if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    V2.write_inplace(a.dll, data); assert open(a.dll, "rb").read() == data; print(msg)


if __name__ == "__main__":
    sys.exit(main())
