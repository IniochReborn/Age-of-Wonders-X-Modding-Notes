"""
Implosion (389, Fire/Air tier 2) - TCPCK caves (2026-10-14; v2 same day).  AoWTCPCK.dll only.

Design: a GREAT HAIL clone (hail class 0x0A) because that class is the only one whose strike (a) targets a HEX
instead of a unit object, (b) comes straight down (no path, no line of sight -> "bypasses obstructions") and
(c) deals its damage through the field message 0x31006 at the landing, whose four handlers (CityWall 0x406094,
CombatTerrain 0x410682, unit HS 0x4213FA, CombatStructure 0x432F68) all roll the SPELL'S OWN GetCombatInfo
(ATK/DMG/types; patch_tc_hail_msg_spell_v1.py writes the real id into the message) -> walls, structures and
units all take Implosion's 8/8 fire+physical+wall hit.  A class-7 direct spell can never target a wall: its
strike needs a TCombatUnit on the hex ([fx+0x2C] = [unitHS+0x1C], NextStrike tail 0x40D91A) and the cursor
validates units (TUnitSpell.ValidTargetUnit); projectiles explicitly drop non-unit targets (0x40F04C).

Pipeline entry (patch_dual_sphere_spells_v1.py): DONOR "TGreatHail": (0x557F5504, 0x557F8F18) site 0x557FA6F4;
id 389, pfs_donor 126, tc_type 10, pokes [(0x34,1,8),(0x35,1,8),(0x36,2,0x181),(0x38,1,1),(0x39,1,4),(0x3A,1,1)].
Alias (patch_tc_spell_alias_v1.py): ALIAS[389] = 0x74; SITE_KEEP[0x40B541] += {389}; SITE_KEEP[0x42827A] += {389}.

ZONE A caves (v1, 0x43DF00..0x43E000):
  cnt   call-hook on the phase-0 DEFAULT strike-count store 0x40B571 (`mov dword [eax+0x28],0x23`, eax = te):
        replays it, then for te spell 389 stores 1 -> ONE strike = pattern hex 0 = the target hex.
  sc1/  call-hooks on the two landing-offset sites 0x40E2DC / 0x40E2F3 (`add eax,6 / jno / call OverflowError`,
  sc2   eax = Random(20) just drawn): for a 389 te the offset becomes 0x10 = the hex centre (RNG count unchanged).
ZONE B caves (v2, 0x43E000..0x43E200) - the RING (user: "a red Animate-Dead circle reversed: it spawns around the
target and shrinks into it; when fully shrunk, Fireball's explosion gfx/sfx"):
  gate  both `call NextStrike` sites 0x40B6F1 / 0x40CBE7 chain in FRONT of whatever they call now (the oil-gush
        gate 0x43DA00 -> Ashes 0x43D020 -> Hellfire -> NextStrike; decoded at apply, restored on --revert).  eax = te.
        For a 389 te with strikes left ([te+0x34] < [te+0x28]): first pass ([te+0x34] == 0, latch [0x46BF60] != te)
        -> latch, spawn ONE kind-0x26 driver at the target hex centre (HXtoHP 0x4022BC + (16,16); AddEffect
        0x41C6EC(map [0x46C064], dl 0x26); TXYZ 0x46EB24 + Create 0x401040; XYZList.Add 0x402DE4 / GetXYZ 0x402DF4;
        [fx+0x14] = 0x34, [fx+0x18] = 389, [fx+0x2C] = 0, marker [fx+0x24] = 1 -> gfx SLOT 3 = the shrinking ring,
        one-shot 14 frames x 3 ticks) and refuse the strike ([te+0x30] := 1; ret); later passes: refuse while the
        ring driver's tick [fx+0x10] < RING_TICKS, then pass (latch cleared) -> the single invisible hail strike
        falls (~30 ticks, path of 0x1E steps) and lands with slot 2 = Fireball's explosion + cue 1 = BLAST.
        RING_TICKS = ring length (42) - fall time (30) so the landing coincides with the ring's end - TUNE IT.
        Done state ([te+0x34] >= [te+0x28]: the gate keeps running every tick until the te ends) -> pass through.
  nf    kind-0x26 NewFrame slot pick 0x42A5E9 (chains to the oil-gush nf cave 0x43DB80 -> Ashes -> Hellfire ->
        vanilla; [ebp-8] = fx; eax must survive; returns edx): a 389 effect with marker 1 -> slot 3.
  show  TfxHS.Show kind-0x26 slot pick 0x430059 (chains to the oil-gush show cave 0x43DBB0 -> ...; [ebp-4] = fx;
        returns eax): same map.
Zones asserted zero + reloc-free; PIC via the call/pop delta.  Backup <game>\\backup\\AoWTCPCK.dll.bak_implosion.
Dry-run default; --apply (v1-applied state: adds zone B + chains the three sites) / --revert (all) / --dis.
⚠ While v2 is applied, patch_tc_oilgush_v1.py / patch_tc_ashes_v1.py see their gate/nf/show sites pointing into
ZONE B (gush: "pass-through" with an unknown chain unless its KNOWN_ZONES gets (0x43E000, 0x43E200); Ashes:
asserts).  Never --apply either of them while this is in - revert this first, then re-apply this afterwards.
Gfx slot roles (hail class): 0 = falling projectile (BLANK 340), 1 = trail (BLANK), 2 = impact at the landing hex
(Fireball's EXPLBIG), 3 = the ring driver (marker 1).  Sounds: cue 0 = cast = the ring sound, cue 1 = per-landing
impact = Fireball's BLAST.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DEFAULT_DLL = game_file("AoWTCPCK.dll")
BAK_SUFFIX = ".bak_implosion"
BASE, CODE_V2F = 0x400000, 0x400C00
ZONE_A, ZONE_A_END = 0x43DF00, 0x43E000
ZONE_B, ZONE_B_END = 0x43E000, 0x43E200
SPELL_ID, KIND = 389, 0x26
N_STRIKES = 1
LAND_CENTRE = 0x10
MARKER, RING_SLOT = 1, 3
RING_TICKS = 11                            # 2026-10-14 (user: the damage came too early in the animation): release the strike at driver tick 14 -> the ~30-tick fall lands it just after the ring closes, in the explosion flash (works for 2 or 3 ticks/frame)
GUSH_DX, GUSH_DY = 16, 16                   # effect xyz = the hex centre; the slot-3 entry's xs/ys centre the frame
G_TE = 0x46BF60                             # DATA-page slack latch (gush 0x46BF40, sandstorm 0x46BF50..58)
SITES_A = {
    "cnt": (0x40B571, bytes.fromhex("c7402823000000")),              # mov dword ptr [eax+0x28], 0x23
    "sc1": (0x40E2DC, bytes.fromhex("83c0067105e8422dffff")),        # add eax,6 / jno +5 / call 0x401028
    "sc2": (0x40E2F3, bytes.fromhex("83c0067105e82b2dffff")),        # add eax,6 / jno +5 / call 0x401028
}
GATE_SITES = [(0x40B6F1, 0x40B6F6), (0x40CBE7, 0x40CBEC)]
NEXTSTRIKE = 0x40D290
NF_SITE, NF_ORIG = 0x42A5E9, bytes.fromhex("ba01000000")
SHOW_SITE, SHOW_ORIG = 0x430059, bytes.fromhex("b801000000")
MAP_LIST_GLOBAL, MAP_GLOBAL = 0x469420, 0x46C064
HXTOHP, ADDEFFECT, TOBJCREATE, XYZADD, GETXYZ, TXYZ_IAT = 0x4022BC, 0x41C6EC, 0x401040, 0x402DE4, 0x402DF4, 0x46EB24
KNOWN_ZONES = [(0x43C500, 0x43CA00), (0x43CF00, 0x43D600), (0x43DA00, 0x43DD00), (0x43E200, 0x43E500)]   # Hellfire portal, Ashes, oil gush, sand swirl

ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, va):
    return bytes(ks.asm(src, va)[0])


def asm_delta(src, va):
    s1 = src.replace("call $D", ".byte 0xe8, 0, 0, 0, 0").replace("sub ebx, $D", "sub ebx, 0x7fffffff")
    b = bytearray(ks.asm(s1, va)[0])
    anchor = bytes.fromhex("e8000000005b81ebffffff7f")
    k = b.find(anchor); assert k >= 0, "delta anchor not found"
    struct.pack_into("<I", b, k + 8, va + k + 5)
    return bytes(b)


def build_cnt(va):
    """phase-0 default strike count: replay `mov [eax+0x28],0x23`; for 389 one strike AND (2026-10-14, user: the ring
    sound started too late) play the spell's sound 0 = the vacuum right here at the cast start, as the ring spawns
    (the caster cast-animation site 0x421D91 skips 389 - patch_tc_hellfire_portal_v1.py castsnd - because the cast
    animation only starts with the strike, after the ring)."""
    return asm_delta("""
        mov dword ptr [eax+0x28], 0x23
        cmp dword ptr [eax+0x18], %(id)d
        jne c_done
        mov dword ptr [eax+0x28], %(n)d
        pushal
        call $D
        pop ebx
        sub ebx, $D
        mov eax, [ebx+%(map)#x]
        test eax, eax
        jz c_pop
        cmp byte ptr [eax+0x129], 0
        je c_pop
        mov eax, [ebx+%(reg)#x]
        mov eax, [eax]
        mov eax, [eax+0x84]
        mov edx, %(id)d
        call %(getspell)#x
        test eax, eax
        jz c_pop
        mov eax, [eax+0x28]
        xor edx, edx
        call %(play)#x
    c_pop:
        popal
    c_done:
        ret
    """ % {"id": SPELL_ID, "n": N_STRIKES, "map": MAP_GLOBAL, "reg": 0x46E8D0, "getspell": 0x4029B4, "play": 0x4022F4}, va)


def build_sc(va):
    return asm("""
        mov edx, [ebp-4]
        cmp dword ptr [edx+0x18], %(id)d
        je s_mid
        cmp dword ptr [edx+0x18], 388
        jne s_van
    s_mid:
        mov eax, %(c)d
    s_van:
        add eax, 6
        ret
    """ % {"id": SPELL_ID, "c": LAND_CENTRE - 6}, va)


def build_gate(va, chain):
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
        mov edx, [eax+0x34]
        cmp edx, [eax+0x28]
        jae go
        test edx, edx
        jne running
        cmp [ebx+%(gte)#x], eax
        je running
        mov [ebx+%(gte)#x], eax
        call spawn
        jmp refuse
    running:
        call find
        test eax, eax
        jz go
        cmp dword ptr [eax+0x10], %(ring)d
        jb refuse
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
        cmp dword ptr [eax+0x24], %(marker)d
        jne fn
        ret
    fn:
        inc edx
        jmp fl
    fnone:
        xor eax, eax
        ret
    spawn:
        mov eax, [esp+4]
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
        mov dword ptr [esi+0x24], %(marker)d
        add esp, 8
        ret
    """ % {"id": SPELL_ID, "kind": KIND, "marker": MARKER, "ring": RING_TICKS, "gte": G_TE, "maplist": MAP_LIST_GLOBAL, "map": MAP_GLOBAL,
           "hx": HXTOHP, "add": ADDEFFECT, "txyz": TXYZ_IAT, "create": TOBJCREATE, "xyzadd": XYZADD, "getxyz": GETXYZ,
           "dx": GUSH_DX, "dy": GUSH_DY, "chain": chain}
    return asm_delta(src, va)


def build_nf(va, chain):
    tail = "jmp %#x" % chain if chain is not None else "mov edx, 1\n        ret"
    return asm("""
        push eax
        mov eax, [ebp-8]
        cmp dword ptr [eax+0x18], %(id)d
        jne n_pass
        cmp dword ptr [eax+0x24], %(marker)d
        jne n_pass
        pop eax
        mov edx, %(slot)d
        ret
    n_pass:
        pop eax
        %(tail)s
    """ % {"id": SPELL_ID, "marker": MARKER, "slot": RING_SLOT, "tail": tail}, va)


def build_show(va, chain):
    tail = "jmp %#x" % chain if chain is not None else "mov eax, 1\n        ret"
    return asm("""
        mov eax, [ebp-4]
        cmp dword ptr [eax+0x18], %(id)d
        jne w_pass
        cmp dword ptr [eax+0x24], %(marker)d
        jne w_pass
        mov eax, %(slot)d
        ret
    w_pass:
        %(tail)s
    """ % {"id": SPELL_ID, "marker": MARKER, "slot": RING_SLOT, "tail": tail}, va)


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


def site_target(d, site):
    b = d[site - CODE_V2F:site - CODE_V2F + 5]
    if b[0] != 0xE8: return None
    return site + 5 + struct.unpack_from("<i", b, 1)[0]


def in_known(t):
    return t == NEXTSTRIKE or any(lo <= t < hi for lo, hi in KNOWN_ZONES)


def tail_target(d, cave_va):
    """The applied cave's chain = the first `jmp rel32` inside zone B from cave_va whose target is a known chain."""
    for p in range(cave_va, ZONE_B_END):
        b = d[p - CODE_V2F:p - CODE_V2F + 5]
        if b[0] != 0xE9: continue
        t = p + 5 + struct.unpack_from("<i", b, 1)[0]
        if in_known(t): return t
    raise AssertionError("applied cave chain not found from %#x" % cave_va)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dll", default=DEFAULT_DLL)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    d = open(a.dll, "rb").read()
    # ---- zone A (v1): cnt / sc1 / sc2
    caves_a, va = {}, ZONE_A
    for name, builder in (("cnt", build_cnt), ("sc1", build_sc), ("sc2", build_sc)):
        code = builder(va); caves_a[name] = (va, code); va += (len(code) + 15) & ~15
    assert va <= ZONE_A_END
    zone_a = bytearray(ZONE_A_END - ZONE_A)
    for name, (cva, code) in caves_a.items(): zone_a[cva - ZONE_A:cva - ZONE_A + len(code)] = code
    zone_a = bytes(zone_a); zla = d[ZONE_A - CODE_V2F:ZONE_A_END - CODE_V2F]
    za_state = "zero" if not any(zla) else "ours" if zla == zone_a else "DIFFERS"
    hooks_a, states_a = {}, {}
    for name, (sva, orig) in SITES_A.items():
        hooks_a[name] = b"\xe8" + struct.pack("<i", caves_a[name][0] - (sva + 5)) + b"\x90" * (len(orig) - 5)
        live = d[sva - CODE_V2F:sva - CODE_V2F + len(orig)]
        states_a[name] = "vanilla" if live == orig else "ours" if live == hooks_a[name] else "OTHER"
    # ---- zone B (v2): gate / nf / show, chained in front of the live targets
    gate_va = ZONE_B
    gate_len = len(build_gate(gate_va, NEXTSTRIKE)); nf_va = gate_va + ((gate_len + 15) & ~15)
    nf_len = len(build_nf(nf_va, NEXTSTRIKE)); show_va = nf_va + ((nf_len + 15) & ~15)
    targets = [site_target(d, st) for st, _ in GATE_SITES]
    ours_gate = all(t is not None and ZONE_B <= t < ZONE_B_END for t in targets)
    if ours_gate: chain = tail_target(d, targets[0])
    else:
        assert None not in targets and len(set(targets)) == 1, "gate sites disagree: %s" % [hex(t) if t else None for t in targets]
        chain = targets[0]
    assert in_known(chain), "unexpected gate chain %#x" % chain
    nb = d[NF_SITE - CODE_V2F:NF_SITE - CODE_V2F + 5]
    if nb == NF_ORIG: nf_chain, ours_nf = None, False
    else:
        assert nb[0] == 0xE8, "unexpected nf site bytes %s" % nb.hex()
        t = NF_SITE + 5 + struct.unpack_from("<i", nb, 1)[0]; ours_nf = ZONE_B <= t < ZONE_B_END
        nf_chain = tail_target(d, t) if ours_nf else t
        assert in_known(nf_chain), "unexpected nf chain %#x" % nf_chain
    sb = d[SHOW_SITE - CODE_V2F:SHOW_SITE - CODE_V2F + 5]
    if sb == SHOW_ORIG: show_chain, ours_show = None, False
    else:
        assert sb[0] == 0xE8, "unexpected show site bytes %s" % sb.hex()
        t = SHOW_SITE + 5 + struct.unpack_from("<i", sb, 1)[0]; ours_show = ZONE_B <= t < ZONE_B_END
        show_chain = tail_target(d, t) if ours_show else t
        assert in_known(show_chain), "unexpected show chain %#x" % show_chain
    gate, nf, show = build_gate(gate_va, chain), build_nf(nf_va, nf_chain), build_show(show_va, show_chain)
    zone_b = gate + bytes(nf_va - gate_va - len(gate)) + nf + bytes(show_va - nf_va - len(nf)) + show
    assert ZONE_B + len(zone_b) <= ZONE_B_END, hex(ZONE_B + len(zone_b))
    zlb = d[ZONE_B - CODE_V2F:ZONE_B_END - CODE_V2F]
    zb_state = "zero" if not any(zlb) else "ours" if zlb[:len(zone_b)] == zone_b and not any(zlb[len(zone_b):]) else "DIFFERS"
    rl = reloc_set(d)
    bad = [hex(r) for r in rl if ZONE_A <= r < ZONE_B_END or any(sva <= r < sva + len(orig) for sva, orig in SITES_A.values())
           or any(st <= r < st + 5 for st, _ in GATE_SITES) or NF_SITE <= r < NF_SITE + 5 or SHOW_SITE <= r < SHOW_SITE + 5]
    print("zone A %s sites %s | zone B %s (%d B: gate @%#x nf @%#x show @%#x) gate sites %s -> chain %#x | nf %s -> %s | show %s -> %s | relocs %s" % (
        za_state, states_a, zb_state, len(zone_b), gate_va, nf_va, show_va, "ours" if ours_gate else "pass-through", chain,
        "ours" if ours_nf else "other", hex(nf_chain) if nf_chain else "vanilla", "ours" if ours_show else "other", hex(show_chain) if show_chain else "vanilla", bad or "none"))
    if bad or "OTHER" in states_a.values() or za_state == "DIFFERS": print("ABORT"); return 1
    if a.dis:
        import capstone
        for n, (cva, code) in list(caves_a.items()) + [("gate", (gate_va, gate)), ("nf", (nf_va, nf)), ("show", (show_va, show))]:
            print("  -- %s" % n)
            for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(code, cva): print("   %08X  %-16s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    gate_hooks = {st: b"\xe8" + struct.pack("<i", gate_va - nx) for st, nx in GATE_SITES}
    chain_hooks = {st: b"\xe8" + struct.pack("<i", chain - nx) for st, nx in GATE_SITES}
    nf_hook = b"\xe8" + struct.pack("<i", nf_va - (NF_SITE + 5)); nf_restore = NF_ORIG if nf_chain is None else b"\xe8" + struct.pack("<i", nf_chain - (NF_SITE + 5))
    show_hook = b"\xe8" + struct.pack("<i", show_va - (SHOW_SITE + 5)); show_restore = SHOW_ORIG if show_chain is None else b"\xe8" + struct.pack("<i", show_chain - (SHOW_SITE + 5))
    if a.revert:
        out = bytearray(d); out[ZONE_A - CODE_V2F:ZONE_B_END - CODE_V2F] = bytes(ZONE_B_END - ZONE_A)
        for name, (sva, orig) in SITES_A.items(): out[sva - CODE_V2F:sva - CODE_V2F + len(orig)] = orig
        if ours_gate:
            for st in gate_hooks: out[st - CODE_V2F:st - CODE_V2F + 5] = chain_hooks[st]
        if ours_nf: out[NF_SITE - CODE_V2F:NF_SITE - CODE_V2F + 5] = nf_restore
        if ours_show: out[SHOW_SITE - CODE_V2F:SHOW_SITE - CODE_V2F + 5] = show_restore
        write_inplace(a.dll, bytes(out)); print("reverted (v1 + v2; gate sites -> %#x)" % chain); return 0
    v2_applied = ours_gate and ours_nf and ours_show and zb_state == "ours" and all(t == gate_va for t in targets)
    if all(s == "ours" for s in states_a.values()) and za_state == "ours" and v2_applied: print("already applied (v2)"); return 0
    if (ours_gate or ours_nf or ours_show) and not v2_applied: print("an OLDER v2 build is applied - run --revert first, then --apply"); return 1
    if zb_state == "DIFFERS": print("ABORT: zone B holds foreign bytes"); return 1
    out = bytearray(d)
    out[ZONE_A - CODE_V2F:ZONE_A_END - CODE_V2F] = zone_a
    for name, (sva, orig) in SITES_A.items(): out[sva - CODE_V2F:sva - CODE_V2F + len(orig)] = hooks_a[name]
    out[ZONE_B - CODE_V2F:ZONE_B_END - CODE_V2F] = bytes(ZONE_B_END - ZONE_B); out[ZONE_B - CODE_V2F:ZONE_B - CODE_V2F + len(zone_b)] = zone_b
    for st in gate_hooks: out[st - CODE_V2F:st - CODE_V2F + 5] = gate_hooks[st]
    out[NF_SITE - CODE_V2F:NF_SITE - CODE_V2F + 5] = nf_hook
    out[SHOW_SITE - CODE_V2F:SHOW_SITE - CODE_V2F + 5] = show_hook
    print("state: v1 %s -> v2 adds zone B and chains gate/nf/show in front of %#x / %s / %s" % ("applied" if za_state == "ours" else "not applied", chain, hex(nf_chain) if nf_chain else "vanilla", hex(show_chain) if show_chain else "vanilla"))
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(a.dll, BAK_SUFFIX)
    if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    write_inplace(a.dll, bytes(out)); assert open(a.dll, "rb").read() == bytes(out); print("Written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
