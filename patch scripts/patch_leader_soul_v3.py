#!/usr/bin/env python3
r"""
Leader's Soul v3 (2026-10-22): v2 + the live-test fixes.  AoWEPACK.dll only.  Upgrades a v2 (or v1) zone IN PLACE.

User live test of v2 (10/22):
  1. Resurrect Hero / Animate Hero on the dead leader CRASHED.
  2. The leader should come back only on a 50 % coin flip when other dead heroes are available (user change).
  3. A soul body possessed IN COMBAT only got High morale after the combat.
  4. "Make sure a Leader's Soul unit can't be charmed / dominated / seduced / tamed etc. like normal leaders."

Fixes:
  oj  (crash) v2 gave the leader's army to the caster with TArmy.SetPlayer([hero+0x20]).  [unit+0x20] is NOT the
      unit's army - the parent army is [unit+4] (TArmy.AddChild 0x5578E86C = unit.SetParent(army) (VMT+8), success
      iff [unit+4] == army; TUnitList.RemoveChild 0x55782F6C = SetParent(nil)).  [+0x20] is a different holder
      object (TAbstractUnit.Killed calls its VMT+0xB0, THero.OfferToJoin its VMT+0xD0 'type == 5'), so v2 either
      ran SetPlayer on a foreign/stale object (-> crash) or skipped it (leader left independent).  v3 uses
      [hero+4].  The soul's return now runs exactly like TArmy.Validate 0x5578CF7C kills a unit: map lock
      (TAoWHSMap 0x55776830 / unlock 0x55776774 - defers GameOver), army BeginUpdate 0x55703284 / EndUpdate
      0x5570328C around the change, so an Incarnate removed from a one-unit stack leaves the army through the
      normal observer path.  A possessed body that loses Possessed gets Changed + UpdateMoraleValue (back to its
      own morale).
  rpc (coin flip) with the caster's own dead leader FOUND: if the vanilla pool (dead heroes the player may
      revive, leaders excluded as in vanilla) is empty -> the leader (the spell never fizzles on the flip);
      otherwise TAoWHSMap.Random(map, 2) - the SAME synced generator ([map+0x230]) and the same map pointer
      ([[0x558E9494]]) vanilla's random hero pick uses right after - 0 -> the leader, 1 -> the vanilla pool
      untouched (PICK stays 0, so oj also stays vanilla).  The extra draw happens identically on every machine
      (same TE, same synced state) -> MP- and replay-safe.
  pg / ic / iv (morale): after the marker moves to a new body / Incarnate, TAbstractUnit.UpdateMoraleValue
      0x5577F058 runs on it at once: base = VMT+0x17C (our vc slot -> 0x5A High), c7 skips every modifier, and
      [unit+0x26] (the morale byte the combat code reads live, e.g. 0x5573A41A/0x5573AC9C) is High immediately.
  c8  (immunity) Mind Decay's CreateCA 0x557F85DC refuses leaders with IsClass(TLeader) @0x557F866C (Mind
      Decay turns the victim to the caster's side and it dies at combat end) - the only vanilla leader immunity
      v2 had not swapped.  Now `call isl` too.
  Immunity audit (every TLeader IsClass in AoWEPACK + AoWTCPCK): Seduce / Charm / Dominate / Tame Animal (0xC9 is a
  TDominateAbility instance) all run TCommandAbility.CreateCommandCA 0x55770358 (c5) + fcGetDamageValueEx
  0x55770274 (c6, autocombat/AI); Possess c3/c4; Mind Decay c8; disband vc +0x190; desertion c7 + upkeep 0.
  Turn Undead / Holy Fear / Panic have no leader exemption in vanilla (not side changes) - unchanged.  The
  TCPCK TLeader checks (0x41369C.., TCAI target value x2) are AI scoring only - unchanged.

Everything else is v2 (see patch_leader_soul_v2.py): marker 0xCE, isl at c1..c7, kd, cr, vc, rf.
Zone AoWEPACK 0x55836800..0x55837800, header keeps every site's original bytes (c8 appended at the end of the
v2 site list, so a v2 header is a prefix of the v3 one).  --apply upgrades v1/v2 in place; --revert accepts
v1/v2/v3 and restores every site + VMT slot from the header.
Dry-run default; --apply / --revert / --dis; --dll <scratch copy>.  Backup <game>\backup\AoWEPACK.dll.bak_leadersoul3
(first v3 apply; the pre-v1 file stays in .bak_leadersoul).  LIFO: same as v2 (RegisterAbility chain 0x557BCF6E).
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
import patch_leader_soul_v2 as V2

DEFAULT_DLL = game_file("AoWEPACK.dll")
BAK_SUFFIX = ".bak_leadersoul3"
BASE, CODE_V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x55836800, 0x55837800
HDR = 0x100
TABLE_OFF, RETV_OFF, NAME_OFF = 0x80, 0xA0, 0xC0
AB, POSSESSED = 0xCE, 0x6B
NAME = b"Leader's Soul"
FOUND, PICK = 0x5590B3C0, 0x5590B3C4                       # runtime-only .idata page slack (RW, beyond raw data)
ISCLASS, GAS = 0x557010C0, 0x5577F618
TLEADER_CELL, MAPCELL, MAPPTR = 0x557121F8, 0x558FA040, 0x558E9494
GAMEOVER, ABKILLED = 0x55776838, 0x5578087C
GETPLAYERS, GETARMY, GETUNIT, GETHERO = 0x557544D0, 0x55750808, 0x5578309C, 0x5578A208
SETPLAYER, RANDOM, UMV = 0x5578D690, 0x5577827C, 0x5577F058
MAPLOCK, MAPUNLOCK, BEGINUPD, ENDUPD = 0x55776830, 0x55776774, 0x55703284, 0x5570328C
REGABIL, LSTRASG = 0x55750238, 0x55701150
AB_VMT, AB_CREATE = 0x5570F254, 0x5574E5F4
VMTS, SLOTS, PTRS = V2.VMTS, V2.SLOTS, V2.PTRS
e8 = V2.e8
SITES = V2.SITES + [("c8", 0x557F866C, 5, e8(0x557F866C, ISCLASS), "call")]   # Mind Decay CreateCA
TARGET = dict(V2.TARGET, c8="isl")
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, va):
    return bytes(ks.asm(src, va)[0])


rel = V2.rel


def build(prev_reg):
    out = bytearray(HDR); where = {}

    def place(name, src):
        while len(out) % 16: out.append(0)
        va = ZONE + len(out); where[name] = va
        out.extend(asm(src, va))

    S = {"ab": AB, "pos": POSSESSED, "gas": GAS, "isclass": ISCLASS, "tlc": TLEADER_CELL, "map": MAPCELL,
         "mapptr": MAPPTR, "go": GAMEOVER, "abk": ABKILLED, "found": FOUND, "pick": PICK, "gp": GETPLAYERS,
         "ga": GETARMY, "gu": GETUNIT, "gh": GETHERO, "sp": SETPLAYER, "rnd": RANDOM, "umv": UMV,
         "mlock": MAPLOCK, "munlock": MAPUNLOCK, "bu": BEGINUPD, "eu": ENDUPD,
         "table": ZONE + TABLE_OFF, "retv": ZONE + RETV_OFF}

    place("isl", """
        push ebx
        mov ebx, eax
        call %(isclass)#x
        test al, al
        jne out
        test ebx, ebx
        je out
        mov eax, ebx
        mov edx, %(ab)d
        call %(gas)#x
    out:
        pop ebx
        ret
    """ % S)
    S["isl"] = where["isl"]

    place("islv", """
        push esi
        call d
    d:
        pop esi
        sub esi, d
        mov edx, [esi + %(tlc)#x]
        pop esi
        jmp %(isl)#x
    """ % S)
    S["islv"] = where["islv"]

    # possess: grant to the new body (+ High morale now), take from the old one
    place("pg", """
        mov eax, ebx
        call %(islv)#x
        test al, al
        je back
        mov eax, [ebp + 0x4c]
        mov edx, %(ab)d
        mov cl, 1
        push esi
        mov esi, [eax]
        call dword ptr [esi + 0x50]
        pop esi
        mov eax, [ebp + 0x4c]
        call %(umv)#x
        mov eax, ebx
        mov edx, %(ab)d
        call %(gas)#x
        test al, al
        je back
        mov eax, ebx
        mov edx, %(ab)d
        xor ecx, ecx
        push esi
        mov esi, [eax]
        call dword ptr [esi + 0x50]
        pop esi
    back:
        mov edx, %(pos)d
        jmp 0x557697EC
    """ % S)

    place("ic", """
        mov eax, [esi + 0x4c]
        test eax, eax
        je back
        mov edx, %(ab)d
        call %(gas)#x
        test al, al
        je back
        mov eax, edi
        mov edx, %(ab)d
        mov cl, 1
        push ebx
        mov ebx, [eax]
        call dword ptr [ebx + 0x50]
        pop ebx
        mov eax, edi
        call %(umv)#x
        mov eax, [esi + 0x4c]
        mov edx, %(ab)d
        xor ecx, ecx
        push ebx
        mov ebx, [eax]
        call dword ptr [ebx + 0x50]
        pop ebx
    back:
        mov eax, [esi + 0x4c]
        mov edx, %(pos)d
        jmp 0x55769A54
    """ % S)

    place("iv", """
        mov eax, esi
        mov edx, %(ab)d
        call %(gas)#x
        test al, al
        je back
        mov eax, ebp
        mov edx, %(ab)d
        mov cl, 1
        push ebx
        mov ebx, [eax]
        call dword ptr [ebx + 0x50]
        pop ebx
        mov eax, ebp
        call %(umv)#x
        mov eax, esi
        mov edx, %(ab)d
        xor ecx, ecx
        push ebx
        mov ebx, [eax]
        call dword ptr [ebx + 0x50]
        pop ebx
    back:
        mov eax, esi
        mov edx, [eax]
        call dword ptr [edx + 0x1ac]
        jmp 0x5578CFFE
    """ % S)

    place("kd", """
        push eax
        push ebx
        push esi
        mov ebx, eax
        call d
    d:
        pop esi
        sub esi, d
        mov eax, ebx
        mov edx, %(ab)d
        call %(gas)#x
        test al, al
        je out
        mov eax, ebx
        mov edx, %(pos)d
        call %(gas)#x
        test al, al
        jne out
        test byte ptr [ebx + 0x25], 2
        je out
        mov eax, [esi + %(map)#x]
        test eax, eax
        je out
        cmp dword ptr [eax + 0x120], 0
        jne out
        mov dl, [ebx + 0x24]
        mov cl, 2
        call %(go)#x
    out:
        pop esi
        pop ebx
        pop eax
        jmp %(abk)#x
    """ % S)

    place("cr", """
        push eax
        mov ecx, [eax]
        call dword ptr [ecx + 0x24]
        cmp eax, 0x20232
        pop eax
        je yes
        mov edx, %(ab)d
        call %(gas)#x
        test al, al
        je no
    yes:
        xor eax, eax
        ret
    no:
        or eax, 1
        ret
    """ % S)

    place("vc", """
        push ecx
        push edx
        push esi
        call d
    d:
        pop esi
        sub esi, d
        push eax
        mov edx, %(ab)d
        call %(gas)#x
        test al, al
        pop eax
        mov ecx, [esp + 12]
        jne mine
        mov ecx, [esi + ecx*4 + %(table)#x]
        add ecx, esi
        mov [esp + 12], ecx
        pop esi
        pop edx
        pop ecx
        ret
    mine:
        mov eax, [esi + ecx*4 + %(retv)#x]
        pop esi
        pop edx
        pop ecx
        add esp, 4
        ret
    """ % S)
    for i in range(len(PTRS)):
        place("t%d" % i, "push %d\njmp %#x" % (i, where["vc"]))

    place("rf", """
        push ebx
        push esi
        mov ebx, eax
        call %(isclass)#x
        test al, al
        je out
        call d
    d:
        pop esi
        sub esi, d
        cmp dword ptr [esi + %(found)#x], 0
        jne one
        mov eax, [ebp - 0xc]
        mov al, [eax + 0x24]
        cmp al, [ebx + 0x5c]
        jne one
        mov [esi + %(found)#x], ebx
    one:
        mov al, 1
    out:
        pop esi
        pop ebx
        ret
    """ % S)

    # after the vanilla filter loop (esi = pool): FOUND -> pool empty ? leader : synced Random(2)==0 ? leader : vanilla
    place("rpc", """
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
        mov eax, esi
        mov edx, [eax]
        call dword ptr [edx + 0x54]
        test eax, eax
        je take
        mov eax, [edi + %(mapptr)#x]
        mov eax, [eax]
        mov edx, 2
        call %(rnd)#x
        test eax, eax
        jne out
    take:
        mov [edi + %(pick)#x], ebx
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
    S["rpc"] = where["rpc"]
    for nm, back in (("rp1", 0x557EC1AE), ("rp2", 0x557EC716)):
        place(nm, """
            call %(rpc)#x
            mov eax, esi
            mov edx, [eax]
            call dword ptr [edx + 0x54]
            jmp %(back)#x
        """ % dict(S, back=back))

    # OfferToJoin replacement for the picked leader: hero eax, owner dl (ExecuteTE: [ebp-0xC]+0x24)
    place("oj", """
        push esi
        call d
    d:
        pop esi
        sub esi, d
        test eax, eax
        je vanilla
        cmp eax, [esi + %(pick)#x]
        jne vanilla
        mov dword ptr [esi + %(pick)#x], 0
        pushad
        mov ebx, eax
        mov edi, edx
        mov eax, [ebx + 4]
        test eax, eax
        je soul
        mov edx, edi
        call %(sp)#x
    soul:
        mov eax, [esi + %(map)#x]
        mov eax, [eax + 0x140]
        mov edx, edi
        movsx edx, dl
        call %(gp)#x
        test eax, eax
        je done
        mov ebp, [eax + 0x28]
        mov eax, ebp
        mov edx, [eax]
        call dword ptr [edx + 0x54]
        mov ebx, eax
    al_loop:
        dec ebx
        js done
        mov edx, ebx
        mov eax, ebp
        call %(ga)#x
        mov edi, eax
        test edi, edi
        je al_loop
        mov eax, edi
        mov edx, [eax]
        call dword ptr [edx + 0x54]
        push eax
    ul:
        dec dword ptr [esp]
        js ul_done
        mov edx, [esp]
        mov eax, edi
        call %(gu)#x
        test eax, eax
        je ul
        push eax
        mov edx, %(ab)d
        call %(gas)#x
        test al, al
        pop eax
        je ul
        mov ebx, eax
        mov eax, [esi + %(map)#x]
        call %(mlock)#x
        mov eax, edi
        call %(bu)#x
        mov eax, ebx
        mov edx, %(ab)d
        xor ecx, ecx
        mov ebp, [eax]
        call dword ptr [ebp + 0x50]
        mov eax, ebx
        mov edx, %(pos)d
        call %(gas)#x
        test al, al
        je kill
        mov eax, ebx
        mov edx, %(pos)d
        mov ebp, [eax]
        call dword ptr [ebp + 0x98]
        mov eax, ebx
        mov ebp, [eax]
        call dword ptr [ebp + 0x90]
        mov eax, ebx
        call %(umv)#x
        jmp unlock
    kill:
        mov eax, ebx
        mov ebp, [eax]
        call dword ptr [ebp + 0x1ac]
    unlock:
        mov eax, edi
        call %(eu)#x
        mov eax, [esi + %(map)#x]
        call %(munlock)#x
        add esp, 4
        jmp done
    ul_done:
        add esp, 4
        jmp al_loop
    done:
        popad
        pop esi
        xor eax, eax
        ret
    vanilla:
        pop esi
        jmp dword ptr [ecx + 0x19c]
    """ % S)

    place("reg", """
        call %(prev)#x
        push esi
        call d
    d:
        pop esi
        sub esi, d
        lea eax, [esi + %(vmt)#x]
        xor ecx, ecx
        mov dl, 1
        call %(create)#x
        mov dword ptr [eax + 0xc], %(ab)d
        mov word ptr [eax + 0x20], 0
        push eax
        lea edx, [esi + %(name)#x]
        add eax, 8
        call %(lstrasg)#x
        pop edx
        mov eax, ebx
        call %(reg)#x
        pop esi
        ret
    """ % dict(S, prev=prev_reg, vmt=AB_VMT, create=AB_CREATE, name=ZONE + NAME_OFF + 8, lstrasg=LSTRASG, reg=REGABIL))
    assert ZONE + len(out) <= ZONE_END, hex(ZONE + len(out))
    for i, (_nm, _va, r) in enumerate(PTRS): out[RETV_OFF + 4 * i:RETV_OFF + 4 * i + 4] = struct.pack("<I", r)
    lit = struct.pack("<ii", -1, len(NAME)) + NAME + b"\0"
    assert NAME_OFF + len(lit) <= HDR
    out[NAME_OFF:NAME_OFF + len(lit)] = lit
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
    for name, va, n, _o, _k in SITES: saved[name] = zl[o:o + n]; o += n
    assert o <= TABLE_OFF, o
    for i, (name, va, _r) in enumerate(PTRS): saved[name] = zl[TABLE_OFF + 4 * i:TABLE_OFF + 4 * i + 4]
    cur = {name: g(va, n) for name, va, n, _o, _k in SITES}
    cur.update({name: g(va, 4) for name, va, _r in PTRS})
    reg_b = saved["reg"] if applied else cur["reg"]
    assert reg_b[0] == 0xE8, "RegisterAbility chain site 0x557BCF6E is not a call (%s)" % reg_b.hex()
    prev_reg = 0x557BCF6E + 5 + struct.unpack_from("<i", reg_b, 1)[0]

    # which version holds the zone?  (v1/v2 code is recognised byte for byte below the shared header)
    zone3, where = build(prev_reg)
    code = {"v3": zone3[HDR:]}
    for tag, v1 in (("v2", False), ("v1", True)):
        z, _w = V2.build(prev_reg, v1=v1); code[tag] = z[HDR:]
    zver = "zero" if not any(zl) else next((t for t, c in code.items() if zl[HDR:HDR + len(c)] == c
                                            and not any(zl[HDR + len(c):])), "DIFFERS")
    if applied and zver in ("v1", "v2") and any(saved["c8"]):
        zver = "DIFFERS"                                     # a v1/v2 header never holds c8
    if zver in ("v1", "v2"): saved["c8"] = cur["c8"]          # c8 was never hooked by v1/v2
    src = saved if applied else cur
    if not applied:
        wrong = [(nm, cur[nm].hex()) for nm, _va, _n, orig, _k in SITES if orig is not None and cur[nm] != orig]
        if wrong: print("ABORT: sites not in the expected (vanilla) state: %s" % wrong); return 1
        for nm, _va, _r in PTRS:
            x = struct.unpack("<I", cur[nm])[0]
            assert 0x55700000 < x < 0x558E8000 and not (ZONE <= x < ZONE_END), (nm, hex(x))
    if zver in ("v1", "v2") and cur["c8"] != SITES[-1][3]:
        print("ABORT: Mind Decay site 0x557F866C is not vanilla (%s)" % cur["c8"].hex()); return 1

    hdr = bytearray(zone3[:HDR]); o = 0
    for name, va, n, _o, _k in SITES: hdr[o:o + n] = src[name]; o += n
    for i, (name, va, _r) in enumerate(PTRS): hdr[TABLE_OFF + 4 * i:TABLE_OFF + 4 * i + 4] = src[name]
    zone = bytes(hdr) + zone3[HDR:]

    # site bytes each version writes (v1 and v2 share cave addresses; v3 re-lays the zone)
    _z2, where2 = V2.build(prev_reg)
    def hooks(wh, sites, target):
        h = {name: rel(0xE8 if kind == "call" else 0xE9, va, wh[target.get(name, name)], n)
             for name, va, n, _o, kind in sites}
        h.update({name: struct.pack("<I", wh["t%d" % i]) for i, (name, va, _r) in enumerate(PTRS)})
        return h
    hooked, hooked2 = hooks(where, SITES, TARGET), hooks(where2, V2.SITES, V2.TARGET)
    allsites = [(nm, va, n) for nm, va, n, _o, _k in SITES] + [(nm, va, 4) for nm, va, _r in PTRS]
    def state(nm):
        if cur[nm] == hooked[nm]: return "v3"
        if nm in hooked2 and cur[nm] == hooked2[nm]: return "v2"
        if cur[nm] == src[nm]: return "orig"
        return "OTHER"
    st = {nm: state(nm) for nm, _va, _n in allsites}
    rl = V2.reloc_set(d)
    bad = [hex(r) for r in rl if ZONE - 3 <= r < ZONE_END or any(va - 3 <= r < va + n for _nm, va, n, _o, _k in SITES)]
    ptr_reloc_ok = all(va in rl for _nm, va, _r in PTRS)
    print("zone %s (%d B used of %d) | sites %s | relocs in zone/sites %s | slot relocs %s | reg prev %#x"
          % (zver, len(zone), ZONE_END - ZONE, " ".join("%s=%s" % (k, st[k]) for k, *_ in allsites),
             bad or "none", "ok" if ptr_reloc_ok else "MISSING", prev_reg))
    print("caves: " + ", ".join("%s=%#x" % (k, v) for k, v in where.items() if not (k.startswith("t") and k != "t0")))
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        inv = {v: k for k, v in where.items()}
        for i in md.disasm(zone[HDR:], ZONE + HDR):
            if i.address in inv: print("  %s:" % inv[i.address])
            print("   %08X  %-24s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad or not ptr_reloc_ok or "OTHER" in st.values() or zver == "DIFFERS": print("ABORT"); return 1
    expect = {"zero": src, "v1": dict(hooked2, c8=src["c8"]), "v2": dict(hooked2, c8=src["c8"]), "v3": hooked}[zver]
    mixed = [nm for nm, _va, _n in allsites if cur[nm] != expect[nm]]
    if mixed: print("ABORT: zone is %s but sites %s are not" % (zver, mixed)); return 1

    if a.revert:
        if not applied: print("already reverted"); return 0
        out = bytearray(d)
        for nm, va, n in allsites: out[va - CODE_V2F:va - CODE_V2F + n] = src[nm]
        out[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
        write(a, d, bytes(out), "reverted %s (sites + VMT slots restored from the zone header)" % zver); return 0
    if zver == "v3": print("already applied (v3)"); return 0
    out = bytearray(d)
    out[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
    out[ZONE - CODE_V2F:ZONE - CODE_V2F + len(zone)] = zone
    for nm, va, n in allsites: out[va - CODE_V2F:va - CODE_V2F + n] = hooked[nm]
    if zver != "zero": print("upgrading the %s zone in place" % zver)
    print("%d bytes change" % sum(1 for x, y in zip(d, out) if x != y))
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    write(a, d, bytes(out), "Written and verified (v3)"); return 0


def write(a, d, data, msg):
    if not (a.apply or a.revert): return
    if os.path.abspath(a.dll) == os.path.abspath(DEFAULT_DLL):
        bak = bak_path(a.dll, BAK_SUFFIX)
        if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    V2.write_inplace(a.dll, data); assert open(a.dll, "rb").read() == data; print(msg)


if __name__ == "__main__":
    sys.exit(main())
