"""
BANSHEE GALE (344, Air/Death) - the big SPINNING GALE over the target area (2026-10-15; user: "too similar to Winds of
Fury - make it like Sandstorm, one big spinning wind, with particles like Mind Decay / Disease Cloud spinning quickly").
AoWTCPCK.dll.

One kind-0x26 driver (Sandstorm's sandswirl recipe, simplified): it draws 344's pfs gfx SLOT 1 (kind 0x26's default
slot pick `mov edx/eax, 1` @0x42A5E9 / 0x430059 - every cave chained there only remaps its OWN spell id, so no slot
hook is needed).  Slot 1 = ONE sequence, T = f18+1 = 2 ticks per frame:
    frames [0, R)           RISE   (R = 8)  the gale spins up
    frames [R, R+C)         CYCLE A (C = 12) one full revolution of the loop
    frames [R+C, R+2C)      CYCLE B          the SAME 12 frames again
    frames [R+2C, R+3C)     FADE             the same revolution, fading out (frame k = phase k)
kind-0x26 frames are `GetUnloopedFrameIndex(tick [fx+0x10])` and the effect ends at the last frame (NewFrame 0x42A626),
so the loop is kept SEAMLESS by stepping the tick back by exactly one cycle (C*T ticks, same phase) whenever it reaches
cycle B; at the end it is moved (same phase) into cycle B, so it finishes the current revolution and then plays FADE.

  gate  both `call NextStrike` sites 0x40B6F1 / 0x40CBE7 chain in front of whatever they call now (Flashfreeze's gate
        0x43B440 -> Hurl Boulder 0x43B180 -> sandswirl 0x43E200 -> ... -> NextStrike; decoded at apply, written back
        on --revert).  eax = te.  The phase-1 site runs every Random(3)+4 ticks while the te lives ([te+0x30] wait).
        For [te+0x18] == 344:
          strike 0 pending ([te+0x34] == 0):  first pass (latch [G_TE] != te) -> latch, spawn the driver at the target
              hex (the AoE centre: [te+0x20]/[te+0x22] are only retargeted per unit by patch_banshee_v1's TG cave,
              which runs INSIDE NextStrike) and refuse ([te+0x30] := 1, recheck next tick); later passes refuse until
              the driver's tick >= HOLD (the gale has risen), then pass.
          running ([te+0x34] > 0): latch cleared.  ACTIVE = strikes left ([te+0x34] < [te+0x28]) or any 344 kind-0x2F
              effect (a unit still in flight) in the map effect list.  ACTIVE -> tick >= (R+C)*T ? tick -= C*T.
              Not active -> v6 2026-10-16 (user: the fade skipped frames): tick := FADE start + ((tick - rise) mod SYM_T) - the art is
              3-fold symmetric, so this is the same image, and the fade's first third-turn is still at FULL strength (v5 jumped to
              the same phase in the fade = could enter half-faded; v4 finished the revolution first).
        The driver is found by kind 0x26 / [fx+0x14] 0x34 / [fx+0x18] 344 / marker [fx+0x24] == MARK.
Deterministic (display only, no RNG); the throws/damage are untouched.
v4 (2026-10-16; user: "the hit/displacement happens too soon - later, closer to the end before it fades"; "the sfx
should start fading in right when the animation starts"):
  * HOLD = (R+C)*T - 6: strike 0 (the first throw) waits a full revolution after the rise, launching just before the
    cycle-B step-back point.  No deadlock: while strike 0 is pending only the `holding` branch runs (no step-back), and
    HOLD < (R+C)*T, so the tick always reaches HOLD; the step-back branch (`running`) only runs once strike 0 is gone.
  * the gate plays 344's CUE 0 itself the moment it spawns the driver ([map+0x129] sound flag honoured, as vanilla;
    GetSpell(registry, 344).[+0x28] -> TSFXLibrary play, cue 0 - Flashfreeze's recipe), and 344 is added to the castsnd
    exclusion list (TCPCK 0x43C900, patch_tc_hellfire_portal_v1.py's cave) so the caster's cast animation (which
    NextStrike starts only when strike 0 launches) does not play it a second time; --revert removes 344 again.
Zone 0x43FB00..0x43FD00 (zero, no relocs); latch = DATA-page slack 0x46B8E0 (between Banshee's lists ..0x46B8D8 and
Ashes' queue 0x46B900).  PIC via the call/pop delta.  Backup <game>\\backup\\AoWTCPCK.dll.bak_bvortex.
Dry-run default; --apply / --revert / --dis.
While applied, patch_tc_flashfreeze_v1.py (and everything behind it on the gate chain) dry-runs as 'not ours' / ABORT:
revert THIS first before touching them, re-apply after (the chain is re-decoded).
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
import spellgfx as G

DEFAULT_DLL = game_file("AoWTCPCK.dll")
PFS = game_file(os.path.join("Release", "Spells.pfs"))
BAK_SUFFIX = ".bak_bvortex"
BASE, CODE_V2F = 0x400000, 0x400C00
ZONE, ZONE_END = 0x43FB00, 0x43FD00
SPELL_ID, KIND, FLY_KIND, MARK = 344, 0x26, 0x2F, 7
R_FR, C_FR, T = 36, 24, 2                     # slot-1 layout: rise / cycle frames, ticks per frame (v3 2026-10-16: 84 frames x 2 ticks - smoother, 15 deg/frame; v2 8/12/3, v1 8/12/2)
SYM_T = (C_FR // 3) * T                       # v6: the art is 3-fold symmetric -> the image repeats every third of a revolution
assert SYM_T & (SYM_T - 1) == 0, "SYM_T must be a power of two (AND mask)"
SEQ_FRAMES = R_FR + 3 * C_FR                 # 44 = rise + cycle A + cycle B + fade
HOLD = 66                                    # v7 2026-10-16: fixed (the rise is now 36 frames: grow 12 + spin-up 24) - the first throw stays at ~2.2 s, mid spin-up; must stay < (R+C)*T
assert HOLD < (R_FR + C_FR) * T
GUSH_DX, GUSH_DY = 16, 16                    # effect xyz = the HEX CENTRE
GATE_SITES = [(0x40B6F1, 0x40B6F6), (0x40CBE7, 0x40CBEC)]
NEXTSTRIKE = 0x40D290
MAP_LIST_GLOBAL, MAP_GLOBAL = 0x469420, 0x46C064
HXTOHP, ADDEFFECT, TOBJCREATE, XYZADD, GETXYZ, TXYZ_IAT = 0x4022BC, 0x41C6EC, 0x401040, 0x402DE4, 0x402DF4, 0x46EB24
SPELLREG_GLOBAL, GETSPELL, SFXPLAY = 0x46E8D0, 0x4029B4, 0x4022F4       # as patch_tc_flashfreeze_v1.py's cue-0 play
CASTSND, CASTSND_END = 0x43C900, 0x43C980                              # patch_tc_hellfire_portal_v1.py castsnd cave (id exclusion list)
CASTSND_SKIP, CASTSND_PLAY = 0x421ECC, 0x421D9E
G_TE = 0x46B8E0
# the gate chain we may sit in front of: Flashfreeze, Hurl Boulder, sandswirl, Implosion, oil gush, Ashes, Hellfire
KNOWN_ZONES = [(0x43B440, 0x43B800), (0x43B180, 0x43B440), (0x43E200, 0x43E500), (0x43E000, 0x43E200), (0x43DA00, 0x43DD00),
               (0x43CF00, 0x43D600), (0x43C500, 0x43CA00)]

ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm_delta(src, va):
    s1 = src.replace("call $D", ".byte 0xe8, 0, 0, 0, 0").replace("sub ebx, $D", "sub ebx, 0x7fffffff")
    b = bytearray(ks.asm(s1, va)[0])
    k = b.find(bytes.fromhex("e8000000005b81ebffffff7f")); assert k >= 0, "delta anchor not found"
    struct.pack_into("<I", b, k + 8, va + k + 5)
    return bytes(b)


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
        je holding
        mov [ebx+%(gte)#x], eax
        call spawn
        call cue0
        jmp refuse
    holding:
        mov ecx, %(mark)d
        call find
        test eax, eax
        jz go
        cmp dword ptr [eax+0x10], %(hold)d
        jb refuse
        jmp go
    running:
        mov dword ptr [ebx+%(gte)#x], 0
        mov ecx, %(mark)d
        call find
        test eax, eax
        jz go
        push eax
        mov eax, [esp+4]
        mov edx, [eax+0x34]
        cmp edx, [eax+0x28]
        jb active
        call findany
        test eax, eax
        jnz active
        pop eax
        mov edx, [eax+0x10]
        cmp edx, %(rise_t)d
        jb go
        cmp edx, %(fade_t)d
        jae go
        sub edx, %(rise_t)d
        and edx, %(sym_mask)d
        add edx, %(fade_t)d
        mov [eax+0x10], edx
        jmp go
    active:
        pop eax
        cmp dword ptr [eax+0x10], %(cycb_t)d
        jb go
        sub dword ptr [eax+0x10], %(cyc_t)d
    go:
        pop eax
        pop edi
        pop esi
        pop ebx
    pass:
        jmp %(chain)#x
    refuse:
        pop eax
        pop edi
        pop esi
        pop ebx
        mov dword ptr [eax+0x30], 1
        ret
    find:
        mov esi, [ebx+%(maplist)#x]
        mov esi, [esi]
        mov esi, [esi+0x11c]
        mov edx, [esi+8]
        mov esi, [esi+4]
    fl:
        test edx, edx
        jz fnone
        dec edx
        mov eax, [esi+edx*4]
        cmp byte ptr [eax+0x34], %(kind)d
        jne fl
        cmp dword ptr [eax+0x14], 0x34
        jne fl
        cmp dword ptr [eax+0x18], %(id)d
        jne fl
        cmp [eax+0x24], ecx
        jne fl
        ret
    findany:
        mov esi, [ebx+%(maplist)#x]
        mov esi, [esi]
        mov esi, [esi+0x11c]
        mov edx, [esi+8]
        mov esi, [esi+4]
    fa:
        test edx, edx
        jz fnone
        dec edx
        mov eax, [esi+edx*4]
        cmp byte ptr [eax+0x34], %(fly)d
        jne fa
        cmp dword ptr [eax+0x14], 0x34
        jne fa
        cmp dword ptr [eax+0x18], %(id)d
        jne fa
        ret
    fnone:
        xor eax, eax
        ret
    cue0:
        mov eax, [ebx+%(map)#x]
        cmp byte ptr [eax+0x129], 0
        je cue0_out
        mov eax, [ebx+%(reg)#x]
        mov eax, [eax]
        mov eax, [eax+0x84]
        mov edx, %(id)d
        call %(getspell)#x
        mov eax, [eax+0x28]
        xor edx, edx
        call %(play)#x
    cue0_out:
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
        mov dword ptr [esi+0x24], %(mark)d
        add esp, 8
        ret
    """ % {"id": SPELL_ID, "kind": KIND, "fly": FLY_KIND, "mark": MARK, "hold": HOLD,
           "rise_t": R_FR * T, "cycb_t": (R_FR + C_FR) * T, "cyc_t": C_FR * T, "cyc2_t": 2 * C_FR * T, "fade_t": (R_FR + 2 * C_FR) * T, "sym_mask": SYM_T - 1,
           "maplist": MAP_LIST_GLOBAL, "map": MAP_GLOBAL, "hx": HXTOHP, "add": ADDEFFECT, "txyz": TXYZ_IAT, "create": TOBJCREATE,
           "xyzadd": XYZADD, "getxyz": GETXYZ, "dx": GUSH_DX, "dy": GUSH_DY, "chain": chain, "gte": G_TE,
           "reg": SPELLREG_GLOBAL, "getspell": GETSPELL, "play": SFXPLAY}
    return asm_delta(src, va)


def castsnd_build(ids):
    src = "mov eax, dword ptr [ebp-4]\n" + "".join("cmp dword ptr [eax+0x38], %#x\nje %#x\n" % (i, CASTSND_SKIP) for i in ids) + "jmp %#x\n" % CASTSND_PLAY
    return bytes(ks.asm(src, CASTSND)[0])


def castsnd_parse(blob):
    """The live exclusion list's ids, or None if the cave isn't in the expected shape."""
    import capstone
    ins = list(capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(blob, CASTSND)); ids = []; k = 1
    if not ins or ins[0].mnemonic != "mov": return None
    while k + 1 < len(ins) and ins[k].mnemonic == "cmp" and ins[k].op_str.startswith("dword ptr [eax + 0x38], "):
        if ins[k + 1].mnemonic != "je" or int(ins[k + 1].op_str, 16) != CASTSND_SKIP: return None
        ids.append(int(ins[k].op_str.split(", ")[1], 16)); k += 2
    code = castsnd_build(ids)
    if blob[:len(code)] != code or any(blob[len(code):]): return None
    return ids


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


def applied_chain(d):
    """Our applied gate's `jmp chain` (the `pass:` label = the first E9 whose target is a known chain)."""
    for p in range(ZONE, ZONE_END - 5):
        b = d[p - CODE_V2F:p - CODE_V2F + 5]
        if b[0] != 0xE9: continue
        t = p + 5 + struct.unpack_from("<i", b, 1)[0]
        if in_known(t): return t
    raise AssertionError("applied gate chain not found")


def slot1_frames():
    """Live Spells.pfs record 344+10, gfx slot 1: its frame count (0 = missing) and f18."""
    p = open(PFS, "rb").read(); pairs, kb = G.pfs_tab(p, 7); idx = {t: kb + o for t, o in pairs}
    key = SPELL_ID + 10
    if key not in idx: return 0, None
    nxt = min([v for v in idx.values() if v > idx[key]] + [len(p) - 4])
    slots = G.seq_parse(bytes(G.pfs_fields(p, idx[key], nxt)[0xC]))
    sl = slots[1] if len(slots) > 1 else None
    return (len(sl["frames"]), sl["f18"]) if sl and sl.get("frames") else (0, None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dll", default=DEFAULT_DLL)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    d = open(a.dll, "rb").read()
    targets = [site_target(d, st) for st, _ in GATE_SITES]
    assert None not in targets and len(set(targets)) == 1, "gate sites disagree: %s" % [hex(t) if t else None for t in targets]
    ours = targets[0] == ZONE
    chain = applied_chain(d) if ours else targets[0]
    assert in_known(chain), "unexpected gate chain %#x (another cave in front? revert it first)" % chain
    gate = build_gate(ZONE, chain)
    assert ZONE + len(gate) <= ZONE_END, hex(ZONE + len(gate))
    zl = d[ZONE - CODE_V2F:ZONE_END - CODE_V2F]
    zstate = "zero" if not any(zl) else "ours" if zl[:len(gate)] == gate and not any(zl[len(gate):]) else "DIFFERS"
    csb = bytes(d[CASTSND - CODE_V2F:CASTSND_END - CODE_V2F]); ids = castsnd_parse(csb)
    rl = reloc_set(d)
    bad = [hex(r) for r in rl if ZONE - 3 <= r < ZONE_END or any(st - 3 <= r < st + 5 for st, _ in GATE_SITES) or G_TE <= r < G_TE + 4
           or CASTSND - 3 <= r < CASTSND_END]
    print("gate sites %s -> chain %#x | zone %s (%d B @%#x) | latch %#x | slot 1 = %d frames (rise %d, cycle %d x2, fade %d) x %d ticks, hold %d (first throw ~tick %d = %.2f s) | castsnd ids %s | relocs %s" % (
        "ours" if ours else "pass-through", chain, zstate, len(gate), ZONE, G_TE, SEQ_FRAMES, R_FR, C_FR, C_FR, T, HOLD, HOLD, HOLD / 30.0,
        [hex(i) for i in ids] if ids is not None else "UNPARSEABLE", bad or "none"))
    if bad or ids is None or (zstate == "DIFFERS" and not ours): print("ABORT (zone not free / relocs / castsnd shape)"); return 1
    cs_len = len(castsnd_build(ids + ([SPELL_ID] if SPELL_ID not in ids else [])))
    if cs_len > CASTSND_END - CASTSND: print("ABORT (castsnd cave full: %d B)" % cs_len); return 1
    if a.dis:
        import capstone
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(gate, ZONE): print("   %08X  %-16s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    hooks = {st: b"\xe8" + struct.pack("<i", ZONE - nx) for st, nx in GATE_SITES}
    restore = {st: b"\xe8" + struct.pack("<i", chain - nx) for st, nx in GATE_SITES}
    nfr, f18 = slot1_frames()
    print("pfs 344 slot 1: %d frames, f18 %s (need %d frames, f18 %d)" % (nfr, f18, SEQ_FRAMES, T - 1))
    def set_castsnd(buf, new_ids):
        c = castsnd_build(new_ids); buf[CASTSND - CODE_V2F:CASTSND_END - CODE_V2F] = c + bytes(CASTSND_END - CASTSND - len(c))
    if a.revert:
        if not ours: print("not applied (gate sites -> %#x)" % targets[0]); return 0
        out = bytearray(d); out[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
        for st in hooks: out[st - CODE_V2F:st - CODE_V2F + 5] = restore[st]
        if SPELL_ID in ids: set_castsnd(out, [i for i in ids if i != SPELL_ID])
        write_inplace(a.dll, bytes(out)); print("reverted (gate sites -> %#x, castsnd ids %s)" % (chain, [hex(i) for i in ids if i != SPELL_ID])); return 0
    if ours and zstate == "ours" and SPELL_ID in ids: print("already applied"); return 0
    out = bytearray(d); out[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
    if SPELL_ID not in ids: set_castsnd(out, ids + [SPELL_ID])
    out[ZONE - CODE_V2F:ZONE - CODE_V2F + len(gate)] = gate
    for st in hooks: out[st - CODE_V2F:st - CODE_V2F + 5] = hooks[st]
    if a.apply and (nfr != SEQ_FRAMES or f18 != T - 1):
        print("REFUSED: run the fx builder + pipeline first (344 slot 1 must be the %d-frame f18=%d vortex)" % (SEQ_FRAMES, T - 1)); return 1
    if not a.apply: print("Dry run OK%s - rerun with --apply (or --revert)." % (" (an older build is applied: --apply upgrades it in place)" if ours else "")); return 0
    bak = bak_path(a.dll, BAK_SUFFIX)
    if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    write_inplace(a.dll, bytes(out)); assert open(a.dll, "rb").read() == bytes(out); print("Written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
