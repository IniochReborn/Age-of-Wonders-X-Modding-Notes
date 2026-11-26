"""
SUFFOCATE (345) - the five hits spread evenly over the cast + one long breath-drain effect for the whole cast
(2026-10-16).  AoWTCPCK.dll.

User: "the hits all happen in quick succession near the end of the animation; they should be spread out from
beginning to end of the animation" + "it should last longer" (whole gfx/sfx).

345 is a class-7 TVaporize clone (5 shots).  TCAbRangedTE.Execute (see patch_tc_flashfreeze_v1.py for the full RE):
  phase 0: `call NextStrike` @0x40B6F1 (return 0x40B6F6) launches strike 0 at once (and starts the caster's cast
    animation -> cue 0, ONCE per cast; nothing re-triggers it - class-7 effects only play cue 1 on landing, and 345's
    pipeline sfx has no cue 1).
  phase 1: the countdown [te+0x30] is reloaded to Random(3)+4 when <= 0 (or every tick while the caster animates),
    decremented, and at 0 -> `call NextStrike` @0x40CBE7 (return 0x40CBEC).
  A class-7 strike (one kind-7 effect drawing gfx SLOT 0 at the target) lands on its sequence's LAST frame.
This script puts one gate IN FRONT of the NextStrike gate chain (live front decoded at apply - today
patch_tc_banshee_vortex_v1.py's 0x43FB00 -> Flashfreeze 0x43B440 -> Hurl Boulder 0x43B180 -> ...; written back on
--revert).  Gate (eax = te; any other spell id, or no strike left ([te+0x34] >= [te+0x28]) -> the chain untouched):
  * phase 0, strike 0: spawn ONE kind-0x26 driver at the TARGET hex (HXtoHP([te+0x20],[te+0x22]) + 16/16 = the hex
    centre; [fx+0x14]=0x34, [fx+0x18]=345, [fx+0x2C]=nil).  Every kind-0x26 slot-pick cave chained at 0x42A5E9 /
    0x430059 remaps only its OWN spell id, so the driver draws the default gfx SLOT 1 (the long drain effect) once and
    is removed at its last frame.  WAIT := GAP_TICKS, then fall into the chain = strike 0 launches NOW (no hold).
  * phase 1: WAIT -= 1; while > 0: [te+0x30] := 1 (the countdown hits 0 next tick and calls us again), return without
    launching; at 0: WAIT := GAP_TICKS and fall into the chain = launch.
  So consecutive launches are ~ (vanilla Random(3)+4) + GAP_TICKS - 1 ticks apart = 17-19 ticks (~0.6 s), and with a
  SLOT0_TICKS-tick slot 0 the hits land at ~ SLOT0_TICKS + k * 18 ticks = 0.53 / 1.13 / 1.73 / 2.33 / 2.93 s
  (strike 1 may slip a few ticks while the caster's cast animation still plays).  The driver (SLOT1_TICKS) outlives
  the last hit.  Fixed tick counts run by the same code on every peer -> MP/replay deterministic; damage untouched.
WAIT = one dword of DATA page slack 0x46BFE8 (raw DATA ends 0x46B800, BSS 0x46C000; 0x46BFE0/E4 = Hurl Boulder /
Flashfreeze waits, Sandstorm's capped list ends 0x46BFE0; no code reference to 0x46BFE8 in the image).
Pipeline prerequisite (checked in the live Release\\Spells.pfs record 355; --apply refuses without slot 1 - the driver
must never draw an EMPTY slot):
    gfx={0: G.seq_entry("EFFECTS\\\\DUALDF.ILB", <8 frames>, xs, ys, f18=1),          # per-hit breath burst, 16 ticks
         1: G.seq_entry("EFFECTS\\\\DUALDF.ILB", <32 frames>, xs, ys, f20=2, f18=2)},   # the whole-cast drain, 96 ticks
    sfx=["SFX\\\\ZSP\\\\DUALAD_SUFFOCATE.WAV"]                                          # cue 0 only (~3.3 s)
PIC (call/pop delta; the DLL rebases).  Zone 0x43FE00..0x43FF00 (zero, reloc-free; 0x43FD00.. = patch_banshee_hop_v1.py).
Dry-run default; --apply / --revert / --dis.  Backup <game>\\backup\\AoWTCPCK.dll.bak_suffocate.
WARNING chain order: while applied, patch_tc_banshee_vortex_v1.py (and everything behind it on the gate chain) dry-runs
as 'not ours' / ABORT - revert THIS first before touching them, re-apply after (the chain is re-decoded).
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
import capstone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
import spellgfx as G

DLL = game_file("AoWTCPCK.dll")
PFS = game_file(os.path.join("Release", "Spells.pfs"))
BASE, CODE_V2F = 0x400000, 0x400C00
SPELL_ID = 345
ZONE, ZONE_END = 0x43FE00, 0x43FF00
WAIT_VA = 0x46BFE8                    # DATA page slack dword (unreferenced; 0x46BFE0/E4 = hbglow / Flashfreeze)
GAP_TICKS = 10                        # v2 2026-10-16 (user: the last hit came after the sound): ~14 ticks (~0.47 s) apart -> hits ~0.53-2.4 s; v1 14
SLOT0_TICKS = 16                      # expected slot 0 lifetime (8 frames x f18 1) - only for the printed timeline
SLOT1_TICKS = 96                      # expected slot 1 lifetime (32 frames x f18 2)
FX_DX, FX_DY = 16, 16                 # effect point = hex pixel + 16/16 (the hex centre)
GATE_SITES = [(0x40B6F1, 0x40B6F6), (0x40CBE7, 0x40CBEC)]   # (call site, return address): phase 0 / phase 1
KIND_DRIVER = 0x26
HXTOHP, ADDEFFECT, TXYZ_IAT, TOBJCREATE, XYZADD, GETXYZ = 0x4022BC, 0x41C6EC, 0x46EB24, 0x401040, 0x402DE4, 0x402DF4
MAP_GLOBAL = 0x46C064

ks = Ks(KS_ARCH_X86, KS_MODE_32)
cs = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32); cs.detail = True


def asm_delta(src, va):
    if "$D" not in src: return bytes(ks.asm(src, va)[0])
    s1 = src.replace("call $D", ".byte 0xe8, 0, 0, 0, 0").replace("sub ebx, $D", "sub ebx, 0x7fffffff")
    b = bytearray(ks.asm(s1, va)[0]); anchor = b"\xe8\x00\x00\x00\x00\x5b\x81\xeb\xff\xff\xff\x7f"
    n, k = 0, b.find(anchor)
    while k >= 0:
        struct.pack_into("<I", b, k + 8, va + k + 5); n += 1; k = b.find(anchor, k + len(anchor))
    assert n == src.count("call $D") == src.count("sub ebx, $D")
    return bytes(b)


def build(chain):
    """Gate cave.  Layout contract (as hbglow / Flashfreeze / the vortex): offset 0 = `cmp dword ptr [eax+0x18], imm32`
    (7 B), offset 7 = `jne rel32` (0F 85, 6 B) -> the chain target is decodable from the applied bytes."""
    src = """
        cmp dword ptr [eax+0x18], %(id)d
        jne %(chain)#x
        mov edx, [eax+0x34]
        cmp edx, [eax+0x28]
        jge %(chain)#x
        push ebx
        call $D
        pop ebx
        sub ebx, $D
        lea ecx, [ebx+%(ret0)#x]
        cmp ecx, [esp+4]
        je phase0
        dec dword ptr [ebx+%(wait)#x]
        jle launch
        mov dword ptr [eax+0x30], 1
        pop ebx
        ret
    launch:
        mov dword ptr [ebx+%(wait)#x], %(gap)d
        pop ebx
        jmp %(chain)#x
    phase0:
        test edx, edx
        jnz launch
        push esi
        push edi
        mov edi, eax
        movzx eax, word ptr [edi+0x20]
        movzx edx, word ptr [edi+0x22]
        sub esp, 8
        lea ecx, [esp+4]
        push esp
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
        mov eax, edi
        pop edi
        pop esi
        jmp launch
    """ % {"id": SPELL_ID, "chain": chain, "ret0": GATE_SITES[0][1], "wait": WAIT_VA, "gap": GAP_TICKS,
           "hx": HXTOHP, "map": MAP_GLOBAL, "kind": KIND_DRIVER, "add": ADDEFFECT, "txyz": TXYZ_IAT, "create": TOBJCREATE,
           "xyzadd": XYZADD, "getxyz": GETXYZ, "dx": FX_DX, "dy": FX_DY}
    code = asm_delta(src, ZONE)
    assert code[0:3] == b"\x81\x78\x18" and code[7:9] == b"\x0f\x85", code[:16].hex()
    return code


def relocs(d):
    pe = struct.unpack_from("<I", d, 0x3C)[0]; opt = struct.unpack_from("<H", d, pe + 20)[0]; nsec = struct.unpack_from("<H", d, pe + 6)[0]
    secs = [struct.unpack_from("<IIII", d, pe + 24 + opt + 40 * k + 8) for k in range(nsec)]
    rrva, rsz = struct.unpack_from("<II", d, pe + 24 + 0x88)
    def r2f(rva):
        for vs, va, rs, ro in secs:
            if va <= rva < va + max(vs, rs): return ro + rva - va
    p = r2f(rrva); end = p + rsz; out = set()
    while p < end:
        page, size = struct.unpack_from("<II", d, p)
        if size < 8: break
        for q in range(p + 8, p + size, 2):
            e = struct.unpack_from("<H", d, q)[0]
            if e >> 12 == 3: out.add(BASE + page + (e & 0xFFF))
        p += size
    return out


def abs_audit(code, va, hi):
    """Every in-image absolute must be ebx(delta)-based; rel32 branches/calls are fine.  -> offending lines."""
    bad = []
    for i in cs.disasm(code, va):
        if i.mnemonic.startswith("j") or i.mnemonic == "call" or (i.mnemonic == "sub" and i.op_str.startswith("ebx, ")): continue
        for o in i.operands:
            if o.type == capstone.x86.X86_OP_IMM and BASE <= o.imm < hi: bad.append("%08X %s %s" % (i.address, i.mnemonic, i.op_str))
            if o.type == capstone.x86.X86_OP_MEM and BASE <= o.mem.disp < hi and o.mem.base != capstone.x86.X86_REG_EBX:
                bad.append("%08X %s %s" % (i.address, i.mnemonic, i.op_str))
    return bad


def pfs_state():
    """Live Spells.pfs record 345+10: (gfx slots list, sound list)."""
    p = open(PFS, "rb").read(); pairs, kb = G.pfs_tab(p, 7); idx = {t: kb + o for t, o in pairs}
    key = SPELL_ID + 10
    if key not in idx: return [], []
    nxt = min([v for v in idx.values() if v > idx[key]] + [len(p) - 4])
    f = G.pfs_fields(p, idx[key], nxt)
    return G.seq_parse(bytes(f[0xC])), G.snd_parse(bytes(f[0xB]))


def call_target(d, va):
    b = d[va - CODE_V2F:va - CODE_V2F + 5]
    return va + 5 + struct.unpack("<i", bytes(b[1:]))[0] if b[0] == 0xE8 else None


def seqdesc(sl):
    return "%s %d-%d (%d frames, xs %d ys %d, f18 %d)" % (sl["name"], sl["frames"][0], sl["frames"][-1], len(sl["frames"]), sl["xs"], sl["ys"], sl["f18"])


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true"); ap.add_argument("--dis", action="store_true"); a = ap.parse_args()
    d = bytearray(open(DLL, "rb").read())
    pe = struct.unpack_from("<I", d, 0x3C)[0]; hi = BASE + struct.unpack_from("<I", d, pe + 24 + 56)[0]
    targets = [call_target(d, st) for st, _ in GATE_SITES]
    assert None not in targets and len(set(targets)) == 1, "gate sites disagree: %s" % targets
    ours = targets[0] == ZONE
    chain = ZONE + 13 + struct.unpack_from("<i", bytes(d[ZONE + 9 - CODE_V2F:ZONE + 13 - CODE_V2F]))[0] if ours else targets[0]
    gate = build(chain)
    assert ZONE + len(gate) <= ZONE_END, len(gate)
    zone = gate + bytes(ZONE_END - ZONE - len(gate))
    zl = bytes(d[ZONE - CODE_V2F:ZONE_END - CODE_V2F])
    zstate = "zero" if not any(zl) else "ours" if zl == zone else "DIFFERS"
    rl = relocs(bytes(d))
    hooks = [(ZONE - 3, ZONE_END), (WAIT_VA - 3, WAIT_VA + 4)] + [(st - 3, st + 5) for st, _ in GATE_SITES]
    bad = [hex(r) for r in rl if any(lo <= r < hi_ for lo, hi_ in hooks)]
    audit = abs_audit(gate, ZONE, hi)
    slots, snd = pfs_state()
    sl0 = slots[0] if slots and slots[0] and slots[0].get("frames") else None
    sl1 = slots[1] if len(slots) > 1 and slots[1] and slots[1].get("frames") else None
    t0 = len(sl0["frames"]) * (sl0["f18"] + 1) if sl0 else SLOT0_TICKS
    t1 = len(sl1["frames"]) * (sl1["f18"] + 1) if sl1 else None
    spacing = 5 + GAP_TICKS - 1
    hits = [t0 + k * spacing for k in range(5)]
    print("gate sites %s -> chain %#x | zone %s (%d B @%#x) | wait %#x: gap %d -> launches ~%d ticks apart | relocs %s | abs audit %s"
          % ("ours" if ours else "pass-through", chain, zstate, len(gate), ZONE, WAIT_VA, GAP_TICKS, spacing, bad or "none", audit or "clean"))
    print("pfs 345: slot 0 = %s | slot 1 = %s | sfx = %s" % (seqdesc(sl0) if sl0 else slots[0] if slots else None, seqdesc(sl1) if sl1 else None, snd))
    print("timeline (ticks, ~33 ms): hits ~%s = %s s | driver lives %s ticks%s"
          % (hits, ["%.2f" % (h / 30.0) for h in hits], t1, "" if t1 is None or t1 >= hits[-1] else "  WARNING: shorter than the last hit"))
    if a.dis:
        for i in cs.disasm(gate, ZONE): print("   %08X  %-18s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad or audit: print("ABORT (relocs / absolutes)"); return 1
    if a.revert:
        if not ours:
            print("ABORT revert: %s" % ("not applied" if zstate == "zero" else "another gate sits in front of this one - revert that one first")); return 1
        for st, nx in GATE_SITES: d[st - CODE_V2F:st - CODE_V2F + 5] = b"\xe8" + struct.pack("<i", chain - nx)
        d[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
        with open(DLL, "r+b") as f: f.write(bytes(d))
        print("reverted (gate sites -> %#x, zone zeroed)" % chain); return 0
    if ours and zstate == "ours": print("already applied"); return 0
    if zstate == "DIFFERS" or (zstate == "ours" and not ours): print("ABORT (zone not free / not ours)"); return 1
    d[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = zone
    for st, nx in GATE_SITES: d[st - CODE_V2F:st - CODE_V2F + 5] = b"\xe8" + struct.pack("<i", ZONE - nx)
    if not a.apply:
        if not sl1: print("NOTE: --apply will refuse until the pipeline gives 345 a gfx slot 1 (see the docstring)")
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if not sl1:
        print("ABORT: 345 lacks gfx slot 1 in Release\\Spells.pfs (the driver would draw an empty slot)"); return 1
    bak = bak_path(DLL, ".bak_suffocate")
    if not os.path.exists(bak): shutil.copy2(DLL, bak); print("backup ->", bak)
    with open(DLL, "r+b") as f: f.write(bytes(d))
    assert open(DLL, "rb").read() == bytes(d); print("Written and verified"); return 0


if __name__ == "__main__":
    sys.exit(main())
