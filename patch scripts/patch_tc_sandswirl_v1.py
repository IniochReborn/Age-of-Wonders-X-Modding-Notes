"""
SANDSTORM (388, Fire/Air) - the SAND SWIRL over the target area (2026-10-14; a copy of patch_tc_oilgush_v1.py without its drop hook).  AoWTCPCK.dll.

v2 (user: "the gush should last until the end of the spell animation, and the oil globs should only drop from the
height of the gush, not from the sky"): three kind-0x26 drivers instead of one one-shot, the Ashes-swirl recipe:
  marker 1 = RISE  (gfx slot 4, DualDF 1080-1089, one-shot 10 x 3 ticks): spawned on the first strike pass.  All done ([te+0x34] >= [te+0x28]: the gate still runs every tick until the te ends) -> pass through untouched (v2.1 reset the loop here too -> it lived forever).
  marker 2 = LOOP  (slot 5, DualDF 1170-1179, a seamless steady-state fountain): spawned when the rise is nearly done,
             then KEPT ALIVE by resetting its tick [fx+0x10] on every gate pass until the LAST strike pass; after that
             it expires on its own ~30 ticks later = when the last glob has landed.
  marker 3 = END   (slot 6, DualDF 1180-1196 = 10 blank frames + the 7 collapse frames): spawned on the last strike
             pass; its blank lead-in hides it while the loop still plays, then the column sinks into the pool.
The drivers are found/kept by marker in the map's effect list ([[0x469420]]+0x11C TList; kind [fx+0x34], spell
effect [fx+0x14] = 0x34, [fx+0x18] = 372, marker [fx+0x24]).  Effect xyz = the HEX CENTRE (HXtoHP + 16,16); the
slot entries' xs/ys (-48,-96) centre the 128x128 frames' column base on it.

  gate  both `call NextStrike` sites 0x40B6F1 (phase 0) / 0x40CBE7 (phase 1) chain in front of whatever they call
        (the Ashes gate 0x43D020 -> Hellfire -> NextStrike; decoded at apply, written back on --revert).  eax = te.
        For te spell 372 ([te+0x18]): first pass ([te+0x34] == 0, latch [0x46BF40] != te) -> latch, [te+0x28] :=
        N_STRIKES, spawn RISE, refuse ([te+0x30] := 1; ret).  Last pass ([te+0x34]+1 == [te+0x28]) -> reset the loop's tick one
        last time (it then dies exactly 30 ticks later) and spawn END once (9 blank frames = 27 ticks, 3 of overlap), pass.  Otherwise: loop alive -> reset its tick, pass; no loop but rise alive ->
        refuse until the rise's tick >= HOLD, then spawn LOOP and pass; neither -> pass (latch cleared on every pass).
  nf    kind-0x26 NewFrame slot pick 0x42A5E9 (chains to the Ashes nf cave; [ebp-8] = fx; eax must survive; returns
        edx): a 372 effect with marker m in 1..3 -> slot m + 3.
  show  TfxHS.Show kind-0x26 slot pick 0x430059 (chains to the Ashes show cave; [ebp-4] = fx; returns eax): same map.
  drop  NEW call-hook on `sub edx, 0x12C` @0x40E331 in NextStrike's hail case (the glob path starts 300 px above the
        landing point): for a 372 te ([ebp-4]) the start is DROP px above instead (the gush's height), so the globs
        fall out of the mushroom, not from the sky.  The sub's flags survive the ret into the vanilla `jno`.
Zone 0x43DA00..0x43DD00 (zero, no relocs); PIC via the call/pop delta.  Backup <game>\\backup\\AoWTCPCK.dll.bak_oilgush.
Dry-run default; --apply / --revert / --dis.
⚠ While this is applied, patch_tc_ashes_v1.py's dry-run ASSERTS on its gate/nf/show sites - revert this patch before
touching Ashes, re-apply after (the chain is re-decoded).
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DEFAULT_DLL = game_file("AoWTCPCK.dll")
BAK_SUFFIX = ".bak_sandswirl"
BASE, CODE_V2F = 0x400000, 0x400C00
ZONE, ZONE_END = 0x43E200, 0x43E500         # sand swirl (verify zero + reloc-free on apply)
SPELL_ID, KIND = 388, 0x26
M_RISE, M_LOOP, M_END, SLOT_BASE = 1, 2, 3, 3       # marker m -> gfx slot m + SLOT_BASE (4 / 5 / 6)
N_STRIKES = 30                              # placeholder until patch_sandstorm_v1.py's hx hook sets 3 x units at strike 0
HOLD = 12                                   # rise = 8 frames x 2 ticks; the loop takes over 4 ticks before the rise ends
DROP = 0x12C                                # v2.2: back to vanilla (a zero-length path made the invisible-now globs drift); the glob sprites are blank, so nothing falls
GUSH_DX, GUSH_DY = 16, 16                   # effect xyz = the HEX CENTRE
GATE_SITES = [(0x40B6F1, 0x40B6F6), (0x40CBE7, 0x40CBEC)]
NEXTSTRIKE = 0x40D290
NF_SITE, NF_ORIG = 0x42A5E9, bytes.fromhex("ba01000000")       # mov edx,1
SHOW_SITE, SHOW_ORIG = 0x430059, bytes.fromhex("b801000000")   # mov eax,1
DROP_SITE, DROP_ORIG = 0x40E331, bytes.fromhex("81ea2c010000")  # sub edx, 0x12C
MAP_LIST_GLOBAL, MAP_GLOBAL = 0x469420, 0x46C064
HXTOHP, ADDEFFECT, TOBJCREATE, XYZADD, GETXYZ, TXYZ_IAT = 0x4022BC, 0x41C6EC, 0x401040, 0x402DE4, 0x402DF4, 0x46EB24
G_TE = 0x46BF48                             # DATA-page slack (0x46BF40 gush, 0x46BF44 sandstorm HN): the te the rise was spawned for
KNOWN_ZONES = [(0x43C500, 0x43CA00), (0x43CF00, 0x43D600), (0x43DA00, 0x43DD00), (0x43E000, 0x43E200)]      # Hellfire, Ashes, oil gush, Implosion v2 - the chains we sit in front of

ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm_delta(src, va):
    s1 = src.replace("call $D", ".byte 0xe8, 0, 0, 0, 0").replace("sub ebx, $D", "sub ebx, 0x7fffffff")
    b = bytearray(ks.asm(s1, va)[0])
    anchor = bytes.fromhex("e8000000005b81ebffffff7f")
    k = b.find(anchor); assert k >= 0, "delta anchor not found"
    struct.pack_into("<I", b, k + 8, va + k + 5)
    return bytes(b)


def asm(src, va):
    return bytes(ks.asm(src, va)[0])


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
        mov ecx, %(mloop)d
        call find
        test eax, eax
        jz lastend
        mov dword ptr [eax+0x10], 0
    lastend:
        mov ecx, %(mend)d
        call find
        test eax, eax
        jnz go
        mov ecx, %(mend)d
        call spawn
        jmp go
    notlast:
        mov ecx, %(mloop)d
        call find
        test eax, eax
        jz noloop
        mov dword ptr [eax+0x10], 0
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
    """ % {"id": SPELL_ID, "kind": KIND, "mrise": M_RISE, "mloop": M_LOOP, "mend": M_END, "hold": HOLD, "nstr": N_STRIKES,
           "maplist": MAP_LIST_GLOBAL, "map": MAP_GLOBAL, "hx": HXTOHP, "add": ADDEFFECT, "txyz": TXYZ_IAT, "create": TOBJCREATE,
           "xyzadd": XYZADD, "getxyz": GETXYZ, "dx": GUSH_DX, "dy": GUSH_DY, "chain": chain, "gte": G_TE}
    return asm_delta(src, va)


def build_nf(va, chain):
    tail = "jmp %#x" % chain if chain is not None else "mov edx, 1\n        ret"
    src = """
        push eax
        mov eax, [ebp-8]
        cmp dword ptr [eax+0x18], %(id)d
        jne n_pass
        mov edx, [eax+0x24]
        test edx, edx
        jz n_pass
        cmp edx, %(mmax)d
        ja n_pass
        add edx, %(sbase)d
        pop eax
        ret
    n_pass:
        pop eax
        %(tail)s
    """ % {"id": SPELL_ID, "mmax": M_END, "sbase": SLOT_BASE, "tail": tail}
    return asm(src, va)


def build_show(va, chain):
    tail = "jmp %#x" % chain if chain is not None else "mov eax, 1\n        ret"
    src = """
        mov eax, [ebp-4]
        cmp dword ptr [eax+0x18], %(id)d
        jne w_pass
        mov eax, [eax+0x24]
        test eax, eax
        jz w_pass
        cmp eax, %(mmax)d
        ja w_pass
        add eax, %(sbase)d
        ret
    w_pass:
        %(tail)s
    """ % {"id": SPELL_ID, "mmax": M_END, "sbase": SLOT_BASE, "tail": tail}
    return asm(src, va)


def build_drop(va):
    src = """
        mov eax, [ebp-4]
        cmp dword ptr [eax+0x18], %(id)d
        jne d_van
        sub edx, %(drop)d
        ret
    d_van:
        sub edx, 0x12c
        ret
    """ % {"id": SPELL_ID, "drop": DROP}
    return asm(src, va)


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


def tail_target(d, cave_va, length):
    """The applied cave's chain = the first `jmp rel32` inside the zone from cave_va whose target is a known chain."""
    for p in range(cave_va, min(cave_va + length + 64, ZONE_END)):
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
    gate_va = ZONE
    gate_len = len(build_gate(gate_va, NEXTSTRIKE)); nf_va = gate_va + ((gate_len + 15) & ~15)
    nf_len = len(build_nf(nf_va, NEXTSTRIKE)); show_va = nf_va + ((nf_len + 15) & ~15)
    show_len = len(build_show(show_va, NEXTSTRIKE)); drop_va = show_va + ((show_len + 15) & ~15)
    targets = [site_target(d, st) for st, _ in GATE_SITES]
    ours_gate = all(t is not None and ZONE <= t < ZONE_END for t in targets)
    if ours_gate: chain = tail_target(d, targets[0], ZONE_END - targets[0])
    else:
        assert None not in targets and len(set(targets)) == 1, "gate sites disagree: %s" % [hex(t) if t else None for t in targets]
        chain = targets[0]
    assert in_known(chain), "unexpected gate chain %#x" % chain
    nb = d[NF_SITE - CODE_V2F:NF_SITE - CODE_V2F + 5]
    if nb == NF_ORIG: nf_chain, ours_nf = None, False
    else:
        assert nb[0] == 0xE8, "unexpected nf site bytes %s" % nb.hex()
        t = NF_SITE + 5 + struct.unpack_from("<i", nb, 1)[0]; ours_nf = ZONE <= t < ZONE_END
        nf_chain = tail_target(d, t, ZONE_END - t) if ours_nf else t
        assert in_known(nf_chain), "unexpected nf chain %#x" % nf_chain
    sb = d[SHOW_SITE - CODE_V2F:SHOW_SITE - CODE_V2F + 5]
    if sb == SHOW_ORIG: show_chain, ours_show = None, False
    else:
        assert sb[0] == 0xE8, "unexpected show site bytes %s" % sb.hex()
        t = SHOW_SITE + 5 + struct.unpack_from("<i", sb, 1)[0]; ours_show = ZONE <= t < ZONE_END
        show_chain = tail_target(d, t, ZONE_END - t) if ours_show else t
        assert in_known(show_chain), "unexpected show chain %#x" % show_chain
    db = drop_hook = b""; drop_state = "n/a"
    gate, nf, show, drop = build_gate(gate_va, chain), build_nf(nf_va, nf_chain), build_show(show_va, show_chain), build_drop(drop_va)
    zone = gate + bytes(nf_va - gate_va - len(gate)) + nf + bytes(show_va - nf_va - len(nf)) + show
    assert ZONE + len(zone) <= ZONE_END, hex(ZONE + len(zone))
    zl = d[ZONE - CODE_V2F:ZONE_END - CODE_V2F]
    zstate = "zero" if not any(zl) else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else "DIFFERS"
    rl = reloc_set(d)
    bad = [hex(r) for r in rl if ZONE <= r < ZONE_END or any(st <= r < st + 5 for st, _ in GATE_SITES) or NF_SITE <= r < NF_SITE + 5 or SHOW_SITE <= r < SHOW_SITE + 5]
    print("gate sites %s -> chain %#x | nf %s -> %s | show %s -> %s | drop %s | zone %s (%d B: gate @%#x nf @%#x show @%#x drop @%#x) | relocs %s" % (
        "ours" if ours_gate else "pass-through", chain, "ours" if ours_nf else "other", hex(nf_chain) if nf_chain else "vanilla",
        "ours" if ours_show else "other", hex(show_chain) if show_chain else "vanilla", drop_state, zstate, len(zone), gate_va, nf_va, show_va, drop_va, bad or "none"))
    if bad or drop_state == "OTHER": print("ABORT"); return 1
    if a.dis:
        import capstone
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(zone, ZONE): print("   %08X  %-16s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    gate_hooks = {st: b"\xe8" + struct.pack("<i", gate_va - nx) for st, nx in GATE_SITES}
    chain_hooks = {st: b"\xe8" + struct.pack("<i", chain - nx) for st, nx in GATE_SITES}
    nf_hook = b"\xe8" + struct.pack("<i", nf_va - (NF_SITE + 5)); nf_restore = NF_ORIG if nf_chain is None else b"\xe8" + struct.pack("<i", nf_chain - (NF_SITE + 5))
    show_hook = b"\xe8" + struct.pack("<i", show_va - (SHOW_SITE + 5)); show_restore = SHOW_ORIG if show_chain is None else b"\xe8" + struct.pack("<i", show_chain - (SHOW_SITE + 5))
    if a.revert:
        out = bytearray(d); out[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
        for st in gate_hooks: out[st - CODE_V2F:st - CODE_V2F + 5] = chain_hooks[st]
        out[NF_SITE - CODE_V2F:NF_SITE - CODE_V2F + 5] = nf_restore
        out[SHOW_SITE - CODE_V2F:SHOW_SITE - CODE_V2F + 5] = show_restore
        write_inplace(a.dll, bytes(out)); print("reverted (gate sites -> %#x)" % chain); return 0
    applied = ours_gate and ours_nf and ours_show and zstate == "ours" and all(t == gate_va for t in targets) and db == drop_hook
    if applied: print("already applied"); return 0
    if ours_gate or ours_nf or ours_show: print("an OLDER build of this patch is applied - run --revert first, then --apply"); return 1
    out = bytearray(d); out[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
    out[ZONE - CODE_V2F:ZONE - CODE_V2F + len(zone)] = zone
    for st in gate_hooks: out[st - CODE_V2F:st - CODE_V2F + 5] = gate_hooks[st]
    out[NF_SITE - CODE_V2F:NF_SITE - CODE_V2F + 5] = nf_hook
    out[SHOW_SITE - CODE_V2F:SHOW_SITE - CODE_V2F + 5] = show_hook
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(a.dll, BAK_SUFFIX)
    if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    write_inplace(a.dll, bytes(out)); assert open(a.dll, "rb").read() == bytes(out); print("Written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
