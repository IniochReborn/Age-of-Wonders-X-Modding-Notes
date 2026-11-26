"""
Oil Spring (372) gush - SMOOTH driver timing (2026-10-17).  AoWTCPCK.dll.  Companion of patch_tc_oilgush_v1.py.

User: "Oil Spring gfx are a bit janky - smoothen them, probably need more frames."  The art is re-rendered at 1 frame
per tick (rise 30 / loop 30 / end 27 blank + 24 collapse = the old 10 / 10 / 9+8 frames at 3 ticks each, same real
time; see _oilspring_smooth_integration.txt).  This script fixes the DRIVER jank:
  * the LOOP was kept alive by resetting its tick [fx+0x10] to 0 on every gate pass -> the fountain snapped back to
    frame 0 mid-cycle (froze if passes come every tick).  Now the loop sequence holds TWO identical 30-tick cycles
    (60 entries, life 60) and a pass only WRAPS the tick (tick >= 30 -> tick - 30): the phase is kept and it never dies
    while strikes continue (passes <= 30 ticks apart, as the old reset already required).
  * the LOOP is spawned at the rise's own phase (initial tick = HOLD = 24 = the rise's tick at that moment), so the
    rise -> loop hand-over shows the same moment of the fountain.
  * LAST strike pass: the loop's tick := (tick mod 30) + 30 -> it dies exactly at the END of its current cycle
    (30 - ph ticks later); the END driver is spawned with initial tick max(0, ph - 3) so its collapse (after 27 blank
    ticks) starts exactly when the loop's cycle ends (the collapse art continues from loop phase 0).
How: the old gate at 0x43DA00 (patch_tc_oilgush_v1, reached from the gate chain via 0x43E068) keeps its bytes except
the first 5, which become `jmp NEWGATE`; NEWGATE (TCPCK 0x447810, zone 0x447800-0x447C00 verified zero + reloc-free)
= the old gate with the three changes, chaining to the same target as the old gate (decoded at apply from the old
gate's own `jmp`).  Zone header: 'OILS' + the 5 original gate bytes + pad + chain.  The old zone's nf / show / drop
caves (other scripts chain into them) are untouched.  Phase latch: DATA-page slack 0x46BF4C (unclaimed).
v2 2026-10-17 (user: "janky, like it's skipping frames at ONE point" + slightly too modern): the skip was the
rise -> loop HAND-OVER at tick 24 - the loop's steady frame already carries the spray of earlier pulses (the full
mushroom, ~4300 px the rise frame lacks) and the rise used a different pulse/ceiling/pool, so the fountain popped.  The
v3 art (_oilspring_smooth2_integration.txt, DualDF 4100-4217) renders the rise as the fountain's own TRANSIENT (66
ticks, a time-warped clock: 2x speed at the start easing to normal by tick 48): from tick 48 (fountain time 24 = the
oldest visible particle age) it is pixel-identical to the steady loop.  Gate v2:
  * refuse strikes until the rise's tick >= RISE_HOLD = 48 (v1: 24 -> the first globs come ~0.7 s later), then spawn
    the loop at tick LOOP0 = 12 (the loop frame equal to the rise frame on screen; the 18 overlapping ticks draw
    identical frames);
  * the END slot's blank prefix is now a full cycle (30) and END starts at tick ph (no -3, no clamp at 0 - v1 drew
    loop + collapse together for 1-3 ticks when the last pass fell in phase 0-2).
Upgrade: with v1 applied, --apply rewrites the zone in place (the header's original gate bytes are kept, so --revert
is still exact against the pre-v1 file).  Gate v2 + the v3 art + the v3 slot lines must go live TOGETHER (v2 timing
on the old 30-frame rise = the rise dies at 30 before the loop starts at 48 -> strikes run without a fountain).
Dry-run default; --apply / --revert / --dll <copy> / --dis.  Backup <game>\\backup\\AoWTCPCK.dll.bak_oilsmooth.
While applied, patch_tc_oilgush_v1.py's dry-run sees its gate's first bytes changed: revert this first to touch it.
"""
import argparse, os, shutil, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import patch_tc_oilgush_v1 as O
from bakpath import bak_path

OLD_GATE = O.ZONE                                  # 0x43DA00
ZONE, ZONE_END = 0x447800, 0x447C00
NEW_GATE = ZONE + 16
G_PH = 0x46BF4C
CYC = 30                                           # loop cycle (ticks = frames at 1 tick/frame)
RISE_HOLD = 48                                     # v2: rise ticks before the loop / strikes (rise slot = 66 frames, steady from 48)
LOOP0 = 12                                         # v2: the loop's spawn tick = its frame identical to rise frame 48 (art: (48 + 24) % 30)
SUF = ".bak_oilsmooth"
TOK = b"OILS"


def build_new_gate(va, chain, ver=2):
    """ver 1 = the first smooth build (HOLD 24, loop spawned at 24, END at max(0, ph - 3)) - kept only to recognise it
    for the in-place upgrade; ver 2 = current."""
    src = """
        cmp dword ptr [eax+0x18], %(id)d
        jne pass
        push ebx
        push esi
        push edi
        push eax
        call $D
        pop ebx
        sub ebx, $D
        mov eax, [esp]
        cmp dword ptr [eax+0x34], 0
        jne running
        cmp [ebx+%(gte)#x], eax
        je running
        mov [ebx+%(gte)#x], eax
        mov dword ptr [eax+0x28], %(nstr)d
        mov ecx, %(mrise)d
        call spawn
        jmp refuse
    running:
        mov eax, [esp]
        mov edx, [eax+0x34]
        inc edx
        cmp edx, [eax+0x28]
        jb notlast
        ja go
        mov dword ptr [ebx+%(gph)#x], 3
        mov ecx, %(mloop)d
        call find
        test eax, eax
        jz lastend
        mov edx, [eax+0x10]
    lw:
        cmp edx, %(cyc)d
        jb lwd
        sub edx, %(cyc)d
        jmp lw
    lwd:
        mov [ebx+%(gph)#x], edx
        add edx, %(cyc)d
        mov [eax+0x10], edx
    lastend:
        mov ecx, %(mend)d
        call find
        test eax, eax
        jnz go
        mov ecx, %(mend)d
        call spawn
        mov edx, [ebx+%(gph)#x]
%(e0fix)s    e0ok:
        mov [esi+0x10], edx
        jmp go
    notlast:
        mov ecx, %(mloop)d
        call find
        test eax, eax
        jz noloop
        mov edx, [eax+0x10]
    nw:
        cmp edx, %(cyc)d
        jb nwd
        sub edx, %(cyc)d
        jmp nw
    nwd:
        mov [eax+0x10], edx
        jmp go
    noloop:
        mov ecx, %(mrise)d
        call find
        test eax, eax
        jz go
        cmp dword ptr [eax+0x10], %(hold)d
        jb refuse
        mov ecx, %(mloop)d
        call spawn
        mov dword ptr [esi+0x10], %(loop0)d
        jmp go
    refuse:
        pop eax
        pop edi
        pop esi
        pop ebx
        mov dword ptr [eax+0x30], 1
        ret
    go:
        mov dword ptr [ebx+%(gte)#x], 0
        pop eax
        pop edi
        pop esi
        pop ebx
    pass:
        jmp %(chain)#x
    find:
        mov esi, [ebx+%(maplist)#x]
        mov esi, [esi]
        mov esi, [esi+0x11c]
        mov edi, ecx
        mov ecx, [esi+8]
        mov esi, [esi+4]
        xor edx, edx
    fl:
        cmp edx, ecx
        jae fnone
        mov eax, [esi+edx*4]
        cmp byte ptr [eax+0x34], %(kind)d
        jne fn
        cmp dword ptr [eax+0x14], 0x34
        jne fn
        cmp dword ptr [eax+0x18], %(id)d
        jne fn
        cmp [eax+0x24], edi
        jne fn
        ret
    fn:
        inc edx
        jmp fl
    fnone:
        xor eax, eax
        ret
    spawn:
        push ecx
        mov eax, [esp+8]
        sub esp, 8
        lea ecx, [esp+4]
        push esp
        movzx edx, word ptr [eax+0x22]
        movzx eax, word ptr [eax+0x20]
        call %(hx)#x
        mov eax, [ebx+%(map)#x]
        mov dl, %(kind)d
        call %(add)#x
        mov esi, eax
        mov dl, 1
        mov eax, [ebx+%(txyz)#x]
        call %(create)#x
        mov edx, eax
        mov eax, [esi+0x1c]
        call %(xyzadd)#x
        mov eax, [esi+0x1c]
        xor edx, edx
        call %(getxyz)#x
        mov edx, [esp+4]
        add edx, %(dx)d
        mov [eax+4], edx
        mov edx, [esp]
        add edx, %(dy)d
        mov [eax+8], edx
        mov dword ptr [esi+0x14], 0x34
        mov dword ptr [esi+0x18], %(id)d
        mov dword ptr [esi+0x2c], 0
        add esp, 8
        pop ecx
        mov [esi+0x24], ecx
        ret
    """ % {"id": O.SPELL_ID, "kind": O.KIND, "mrise": O.M_RISE, "mloop": O.M_LOOP, "mend": O.M_END,
           "hold": O.HOLD if ver == 1 else RISE_HOLD, "loop0": O.HOLD if ver == 1 else LOOP0,
           "e0fix": "        sub edx, 3\n        jns e0ok\n        xor edx, edx\n" if ver == 1 else "",
           "nstr": O.N_STRIKES, "maplist": O.MAP_LIST_GLOBAL, "map": O.MAP_GLOBAL, "hx": O.HXTOHP, "add": O.ADDEFFECT,
           "txyz": O.TXYZ_IAT, "create": O.TOBJCREATE, "xyzadd": O.XYZADD, "getxyz": O.GETXYZ, "dx": O.GUSH_DX,
           "dy": O.GUSH_DY, "chain": chain, "gte": O.G_TE, "gph": G_PH, "cyc": CYC}
    return O.asm_delta(src, va)


def old_gate_chain(d):
    """The old gate's chain = the first `jmp rel32` inside it that leaves its zone for a known chain target."""
    V = O.CODE_V2F
    for p in range(OLD_GATE, OLD_GATE + 0x200):
        b = d[p - V:p - V + 5]
        if b[0] == 0xE9:
            t = p + 5 + struct.unpack_from("<i", b, 1)[0]
            if not (O.ZONE <= t < O.ZONE_END) and O.in_known(t): return t
    raise AssertionError("old gate chain not found")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dll", default=O.DEFAULT_DLL)
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true"); ap.add_argument("--dis", action="store_true")
    a = ap.parse_args(); V = O.CODE_V2F
    d = open(a.dll, "rb").read()
    zl = d[ZONE - V:ZONE_END - V]
    cur5 = d[OLD_GATE - V:OLD_GATE - V + 5]
    jmp_new = b"\xE9" + struct.pack("<i", NEW_GATE - (OLD_GATE + 5))
    applied = zl[:4] == TOK and cur5 == jmp_new
    if a.revert:
        if not applied: print("already reverted (not applied)"); return 0
        out = bytearray(d); out[OLD_GATE - V:OLD_GATE - V + 5] = zl[4:9]; out[ZONE - V:ZONE_END - V] = bytes(ZONE_END - ZONE)
        O.write_inplace(a.dll, bytes(out)); print("reverted (old gate's first 5 bytes restored, zone zeroed)"); return 0
    if applied:
        chain = struct.unpack_from("<I", zl, 12)[0]
        want = TOK + zl[4:9] + bytes(3) + struct.pack("<I", chain) + build_new_gate(NEW_GATE, chain)
        if zl[:len(want)] == want and not any(zl[len(want):]): print("already applied (v2, chain %#x)" % chain); return 0
        v1 = TOK + zl[4:9] + bytes(3) + struct.pack("<I", chain) + build_new_gate(NEW_GATE, chain, 1)
        if not (zl[:len(v1)] == v1 and not any(zl[len(v1):])): print("an unknown build of this script is applied - --revert first"); return 1
        print("v1 applied (chain %#x) -> in-place upgrade to v2 (%d B gate; header / original gate bytes kept)" % (chain, len(want) - 16))
        if a.dis:
            import capstone
            for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(want[16:], NEW_GATE): print("   %08X  %-16s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
        if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
        assert len(want) <= ZONE_END - ZONE
        out = bytearray(d); out[ZONE - V:ZONE_END - V] = want + bytes(ZONE_END - ZONE - len(want))
        if os.path.abspath(a.dll) == os.path.abspath(O.DEFAULT_DLL):
            bak = bak_path(a.dll, SUF + "2")
            if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup (v1 state) ->", bak)
        O.write_inplace(a.dll, bytes(out)); assert open(a.dll, "rb").read() == bytes(out); print("Upgraded to v2 and verified"); return 0
    assert not any(zl), "zone 0x447800 not zero"
    chain = old_gate_chain(d)
    old = O.build_gate(OLD_GATE, chain)
    assert d[OLD_GATE - V:OLD_GATE - V + len(old)] == old, "old gate at 0x43DA00 is not patch_tc_oilgush_v1's build (chain %#x)" % chain
    rl = O.reloc_set(d)
    bad = [hex(r) for r in rl if ZONE <= r < ZONE_END or OLD_GATE <= r < OLD_GATE + 5]
    if bad: print("relocs in the way:", bad, "ABORT"); return 1
    gate = build_new_gate(NEW_GATE, chain)
    blob = TOK + cur5 + bytes(3) + struct.pack("<I", chain) + gate
    assert ZONE + len(blob) <= ZONE_END
    print("old gate %#x (chain %#x) -> jmp new gate %#x (%d B) | zone zero | relocs none" % (OLD_GATE, chain, NEW_GATE, len(gate)))
    if a.dis:
        import capstone
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(gate, NEW_GATE): print("   %08X  %-16s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    out = bytearray(d); out[ZONE - V:ZONE - V + len(blob)] = blob; out[OLD_GATE - V:OLD_GATE - V + 5] = jmp_new
    if os.path.abspath(a.dll) == os.path.abspath(O.DEFAULT_DLL):
        bak = bak_path(a.dll, SUF)
        if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    O.write_inplace(a.dll, bytes(out)); assert open(a.dll, "rb").read() == bytes(out); print("Written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
