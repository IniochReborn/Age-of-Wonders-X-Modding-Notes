"""
FLASHFREEZE (397) - an icy implosion ring at the target, then the three frost strikes one after another
(2026-10-15).  AoWTCPCK.dll.

User: "flashfreeze spell gfx should be similar to implosion with a shrinking circle, however it should have fewer
particles and they should be jagged and bluish white. when it fully shrinks, the current ice spike gfx should play 3
times, once for each strike attempt. also the sfx ... should have a similar shrinking circle sfx as implosion except
icy sound, then triple ice sound during hit attempts."

397 is a class-7 TVaporize clone (patch_dual_sphere_spells_v1.py: tc type 7, shots byte 3).  TCAbRangedTE.Execute:
  phase 0: `call NextStrike` @0x40B6F1 (return 0x40B6F6) launches strike 1 at once.
  phase 1 (0x40CB69..): while the caster CU is ready (VMT+0x60) the countdown [te+0x30] is reloaded to Random(3)+4
    only when it is <= 0 (or every tick while the caster sprite animates, [sprite+0x25] != 0), then decremented; at 0
    -> `call NextStrike` @0x40CBE7 (return 0x40CBEC).  An empty strike list [map+0x11C] only ends the TE when no
    strike is left or the caster is not ready (0x40CB16..0x40CB65).
  NextStrike (0x40D290) type 7 (case 0x40D734): one kind-7 effect at the target hex [te+0x20]/[te+0x22] (words)
    drawing gfx SLOT 0; it lands (damage CA) on the sequence's LAST frame (kind-7 NewFrame 0x42D3AE..) and plays the
    spell's sound CUE 1 right there (0x42D3E5, [map+0x129] gated) = a per-strike hit sound is native to class 7: the
    pipeline only has to give 397 a cue 1.  NextStrike's first strike also starts the caster's cast animation -> the
    caster-HS action site 0x421D65 -> castsnd cave plays CUE 0.
Both NextStrike sites already go through the id-gated gate chain (hbglow 0x43B180 -> sandswirl -> ... -> NextStrike).
This script puts one more gate IN FRONT of that chain (decoded at apply, written back on --revert):
  gate (eax = te; any other id, or no strike left ([te+0x34] >= [te+0x28]) -> straight into the chain):
    * phase 0 (return address == 0x40B6F6 + delta), [te+0x34] == 0: spawn ONE kind-0x26 effect at the TARGET hex
      (HXtoHP([te+0x20], [te+0x22]) + 16/16 = the hex centre; [fx+0x14]=0x34, [fx+0x18]=397, [fx+0x2C]=NIL) - it draws
      gfx SLOT 1 (the shrinking frost ring) for RING_FRAMES*(f18+1) ticks; play cue 0 now (the icy in-rush);
      WAIT := RING_TICKS; [te+0x30] := 1; return WITHOUT launching.
    * phase 1 while WAIT > 0: WAIT -= 1; [te+0x30] := 1 (no Random reload; the countdown hits 0 again next tick and
      calls us again); return.  WAIT reaches 0: WAIT := GAP_TICKS and fall into the chain = launch the next strike.
      So strike 1 launches as the ring collapses; strikes 2 and 3 each come GAP_TICKS ticks (counted only while the
      caster is ready, after vanilla's own Random(3)+4) after the previous one -> three frost bursts one after another.
  The ring lives RING_FRAMES*2 = 32 ticks > RING_TICKS = 30.  WAIT = one dword of DATA page slack (0x46BFE4, past
  DATA's raw size; page-mapped, zeroed; hbglow's WAIT is 0x46BFE0).
The waits are fixed tick counts run by the same code on every peer (the Hellfire / Ashes / hbglow gate pattern) ->
MP/replay deterministic; damage resolves untouched (vanilla NextStrike + kind-7 landing).

Second site (in place): patch_tc_hellfire_portal_v1.py castsnd cave (0x43C900..0x43C980, an id exclusion list in
front of the cast animation's cue 0): 397 is added (and removed on --revert), else cue 0 would play twice (the ring
from here + again at strike 1's cast animation).  The cave is parsed and re-assembled; any unexpected shape aborts.

Pipeline prerequisite (patch_dual_sphere_spells_v1.py; checked in the live Release\\Spells.pfs record 407;
--apply refuses without slot 1 - the driver must never draw an EMPTY slot):
    gfx={0: <frost_burst 2170-2185 unchanged>,
         1: G.seq_entry("EFFECTS\\\\DUALDF.ILB", list(range(2190, 2206)), -80, -52, f20=2, f18=1)},   # frost ring
    sfx=["SFX\\\\ZSP\\\\DUALWA_FFRING.WAV", ["SFX\\\\ZSP\\\\DUALWA_FLASHFREEZE.WAV"]]                 # cue 0 ring, cue 1 per hit
PIC (call/pop delta; the DLL rebases).  Zone 0x43B440..0x43B800 (zero, reloc-free; 0x43B400..0x43B440 =
patch_mistystep_v1.py).  Dry-run default; --apply / --revert / --dis.  Backup <game>\\backup\\AoWTCPCK.dll.bak_flashfreeze.
v3 (2026-10-15; user: "the target hit sfx needs to start playing slightly sooner ... the target hit gfx may need a
slightly longer/smoother fade out, and slightly overlapping each other").  Upgrades v2 in place.  Three more hooks:
  LAND  kind-7 NewFrame landing test 0x42D3A2 (12 B `mov edx,[ebp-8] / cmp eax,[edx+0x10] / jg 0x42E3A3`; eax =
        total-1 of the slot-0 sequence, [ebp-8] = fx; no relocs, no branch lands inside) -> `jmp land` + 7 nops.
        For a spell effect ([fx+0x14] == 0x34) of 397 ([fx+0x18]):
          * remaining = total-1 - counter; remaining == CUE_EARLY -> play cue 1 NOW ([map+0x129] gated, as vanilla)
          * remaining > 0 -> 0x42E3A3 (not landed yet, as vanilla's jg)
          * landing tick: spawn the FADE driver (one kind-0x26 effect at the burst's own XYZ point = hex + 16/16,
            [fx+0x14]=0x34, [fx+0x18]=397, [fx+0x2C]=nil, [fx+0x24]=FADE_MARK) and continue at 0x42D411 (vanilla's
            counter := total-1 / landed byte) SKIPPING vanilla's cue 1 (it already played CUE_EARLY ticks ago).
        Damage still resolves on the landing tick (TCAbRangedTE.Execute 0x40C31F reads the landed byte) - untouched.
        Every other kind-7 effect runs the replayed vanilla test.  (Vanilla NewFrame itself calls AddEffect from
        other kinds' branches, so spawning here is a known-safe pattern.)
  NF / SHOW  the kind-0x26 slot picks (NewFrame 0x42A5E9 `mov edx,1`, TfxHS.Show 0x430059 `mov eax,1`; both already
        `call` chains - Sandstorm/Implosion/Ashes/Hellfire/...): our caves go IN FRONT (prev target decoded at apply,
        written back on --revert; a vanilla site gets the 5-byte mov replayed): 397 + [fx+0x24] == FADE_MARK -> slot 2,
        anything else -> the previous chain.  So the fade driver plays gfx SLOT 2 once (kind-0x26 lifetime = entries x
        (f18+1) ticks, then it lands and is removed like the ring), at the burst's anchor (same canvas, xs/ys -37/-71).
        Display only (spawned by the same NewFrame on every peer, no RNG) -> MP/replay safe; it only keeps the strike
        list [map+0x11C] busy for the fade's length after the last hit.  --apply refuses without pfs 397 slot 2.
  GAP_TICKS 14 -> 10: launches ~14-16 ticks apart (vanilla Random(3)+4 + GAP), the bursts are 16 ticks, so each new
  burst starts growing just as the previous one lands and the previous hit's fade runs underneath = a slight overlap.
WARNING chain order: re-applying Sandstorm/Implosion/Ashes/... (scripts that decode the NF/SHOW sites) after this one
  puts them in front - fine.  Reverting one of THEM while this one is in front: revert this one first.
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
SPELL_ID = 397
ZONE, ZONE_END = 0x43B440, 0x43B800
WAIT_VA = 0x46BFE4                    # DATA page slack dword (raw DATA ends 0x46B800; BSS starts 0x46C000; hbglow = 0x46BFE0)
RING_TICKS = 24                       # v7 2026-10-15 (user: more overlap, target gfx/sfx a bit sooner): hit 1 lands ~tick 40 of the 48-tick ring; v6 30 / v5 22 / v4 30 / v3 24
GAP_TICKS = 10                        # v3: launches ~14-16 ticks apart vs a 16-tick burst + the slot-2 fade = a slight overlap (v2 = 14: no overlap)
GAP_TICKS_V2 = 14                        # v2 2026-10-15: extra hold before strikes 2 and 3 (on top of vanilla's Random(3)+4 / the cast animation) - spacing >= 18 ticks > the 16-tick burst (8 frames x 2), so the bursts no longer overlap on the target hex (v1 = 10 with a 32-tick burst: three bursts drawn on top of each other, flash/sound/hit of one strike landing mid-growth of the next)
CUE_EARLY_PREV = (3,)
RING_TICKS_PREV = (24, 22, 30)             # ring holds of earlier applied v3 builds (upgrade-in-place detection)
RING_FRAMES, RING_F18 = 24, 1         # slot-1 sequence the pipeline must provide: 20 frames x 2 ticks = 40 ticks > RING_TICKS (v3: 16)
FX_DX, FX_DY = 16, 16                 # effect point = hex pixel + 16/16 (the hex centre); the art's xs/ys place it
GATE_SITES = [(0x40B6F1, 0x40B6F6), (0x40CBE7, 0x40CBEC)]   # (call site, return address): phase 0 / phase 1
KIND_DRIVER = 0x26
CUE_EARLY = 5                         # v7: 5 (v3-v6: 3); cue 1 (the hit sound) plays this many ticks BEFORE the landing tick
FADE_MARK, FADE_SLOT = 2, 2           # v3: the fade driver's [fx+0x24] marker -> gfx slot 2 (the pipeline's post-hit fade)
LAND_SITE, LAND_ORIG = 0x42D3A2, bytes.fromhex("8b55f83b42100f8ff50f0000")
LAND_OUT, LAND_HIT, LAND_VANILLA = 0x42E3A3, 0x42D411, 0x42D3AE   # not landed yet / vanilla's landing tail after the cue / vanilla's cue block
NF_SITE, NF_ORIG = 0x42A5E9, bytes.fromhex("ba01000000")       # kind-0x26 NewFrame slot pick (mov edx,1); fx = [ebp-8]; eax must survive
SHOW_SITE, SHOW_ORIG = 0x430059, bytes.fromhex("b801000000")   # TfxHS.Show kind-0x26 slot pick (mov eax,1); fx = [ebp-4]
LAND_OFF, NF_OFF, SHOW_OFF = 0x120, 0x2C0, 0x300                # cave offsets inside the zone (gate at 0)
HXTOHP, ADDEFFECT, TXYZ_IAT, TOBJCREATE, XYZADD, GETXYZ = 0x4022BC, 0x41C6EC, 0x46EB24, 0x401040, 0x402DE4, 0x402DF4
MAP_GLOBAL, SPELLREG_GLOBAL, GETSPELL, SFXPLAY = 0x46C064, 0x46E8D0, 0x4029B4, 0x4022F4
CASTSND, CASTSND_END = 0x43C900, 0x43C980          # patch_tc_hellfire_portal_v1.py castsnd cave
CASTSND_SKIP, CASTSND_PLAY = 0x421ECC, 0x421D9E     # its exits: skip the cue / play it

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


def build(chain, gap=None, ticks=None):
    """Gate cave.  Layout contract (as hbglow): offset 0 = `cmp dword ptr [eax+0x18], imm32` (7 B), offset 7 =
    `jne rel32` (0F 85, 6 B) -> the chain target is decodable from the applied bytes."""
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
        mov dword ptr [ebx+%(wait)#x], %(ticks)d
        mov dword ptr [eax+0x30], 1
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
        mov eax, [ebx+%(map)#x]
        cmp byte ptr [eax+0x129], 0
        je out
        mov eax, [ebx+%(reg)#x]
        mov eax, [eax]
        mov eax, [eax+0x84]
        mov edx, %(id)d
        call %(getspell)#x
        mov eax, [eax+0x28]
        xor edx, edx
        call %(play)#x
    out:
        pop edi
        pop esi
        pop ebx
        ret
    """ % {"id": SPELL_ID, "chain": chain, "ret0": GATE_SITES[0][1], "wait": WAIT_VA, "ticks": RING_TICKS if ticks is None else ticks, "gap": GAP_TICKS if gap is None else gap,
           "hx": HXTOHP, "map": MAP_GLOBAL, "kind": KIND_DRIVER, "add": ADDEFFECT, "txyz": TXYZ_IAT, "create": TOBJCREATE,
           "xyzadd": XYZADD, "getxyz": GETXYZ, "dx": FX_DX, "dy": FX_DY, "reg": SPELLREG_GLOBAL, "getspell": GETSPELL,
           "play": SFXPLAY}
    code = asm_delta(src, ZONE)
    assert code[0:3] == b"\x81\x78\x18" and code[7:9] == b"\x0f\x85", code[:16].hex()
    return code



def build_land():
    src = """
        mov edx, dword ptr [ebp-8]
        cmp dword ptr [edx+0x14], 0x34
        jne vanilla
        cmp dword ptr [edx+0x18], %(id)d
        jne vanilla
        push ebx
        push esi
        push edi
        mov edi, edx
        call $D
        pop ebx
        sub ebx, $D
        mov esi, eax
        sub esi, dword ptr [edi+0x10]
        cmp esi, %(early)d
        jne notearly
        mov eax, dword ptr [ebx+%(map)#x]
        cmp byte ptr [eax+0x129], 0
        je notearly
        mov eax, dword ptr [ebx+%(reg)#x]
        mov eax, dword ptr [eax]
        mov eax, dword ptr [eax+0x84]
        mov edx, %(id)d
        call %(getspell)#x
        mov eax, dword ptr [eax+0x28]
        mov edx, 1
        call %(play)#x
    notearly:
        test esi, esi
        jg notyet
        sub esp, 8
        mov eax, dword ptr [edi+0x1c]
        xor edx, edx
        call %(getxyz)#x
        mov edx, dword ptr [eax+4]
        mov dword ptr [esp], edx
        mov edx, dword ptr [eax+8]
        mov dword ptr [esp+4], edx
        mov eax, dword ptr [ebx+%(map)#x]
        mov dl, %(kind)d
        call %(add)#x
        mov esi, eax
        mov dl, 1
        mov eax, dword ptr [ebx+%(txyz)#x]
        call %(create)#x
        mov edx, eax
        mov eax, dword ptr [esi+0x1c]
        call %(xyzadd)#x
        mov eax, dword ptr [esi+0x1c]
        xor edx, edx
        call %(getxyz)#x
        mov edx, dword ptr [esp]
        mov dword ptr [eax+4], edx
        mov edx, dword ptr [esp+4]
        mov dword ptr [eax+8], edx
        mov dword ptr [esi+0x14], 0x34
        mov dword ptr [esi+0x18], %(id)d
        mov dword ptr [esi+0x2c], 0
        mov dword ptr [esi+0x24], %(mark)d
        add esp, 8
        pop edi
        pop esi
        pop ebx
        jmp %(hit)#x
    notyet:
        pop edi
        pop esi
        pop ebx
        jmp %(out)#x
    vanilla:
        cmp eax, dword ptr [edx+0x10]
        jg %(out)#x
        jmp %(van)#x
    """ % {"id": SPELL_ID, "early": CUE_EARLY, "map": MAP_GLOBAL, "reg": SPELLREG_GLOBAL, "getspell": GETSPELL, "play": SFXPLAY,
           "getxyz": GETXYZ, "kind": KIND_DRIVER, "add": ADDEFFECT, "txyz": TXYZ_IAT, "create": TOBJCREATE, "xyzadd": XYZADD,
           "mark": FADE_MARK, "hit": LAND_HIT, "out": LAND_OUT, "van": LAND_VANILLA}
    return asm_delta(src, ZONE + LAND_OFF)


def build_pick(show, prev):
    """NF (show=False: fx [ebp-8], result in edx, eax preserved) / SHOW (fx [ebp-4], result in eax).  The tail at
    pick_tail_off() is `jmp prev` (E9) or, on a vanilla site, the replayed `mov reg,1 / ret` (BA/B8) -> decodable."""
    va = ZONE + (SHOW_OFF if show else NF_OFF)
    if show:
        head = """
        mov eax, dword ptr [ebp-4]
        cmp dword ptr [eax+0x18], %(id)d
        jne nextpick
        cmp dword ptr [eax+0x24], %(mark)d
        jne nextpick
        mov eax, %(slot)d
        ret
    nextpick:
        """
        tail = "jmp %#x" % prev if prev else "mov eax, 1\nret"
    else:
        head = """
        push eax
        mov eax, dword ptr [ebp-8]
        cmp dword ptr [eax+0x18], %(id)d
        jne nextpick
        cmp dword ptr [eax+0x24], %(mark)d
        jne nextpick
        pop eax
        mov edx, %(slot)d
        ret
    nextpick:
        pop eax
        """
        tail = "jmp %#x" % prev if prev else "mov edx, 1\nret"
    return bytes(ks.asm((head % {"id": SPELL_ID, "mark": FADE_MARK, "slot": FADE_SLOT}) + tail, va)[0])


def pick_tail_off(show):
    return len(build_pick(show, ZONE)) - 5


def pick_state(d, site, orig, show):
    """-> (ours, prev): prev = the chain target the site called before us (None = vanilla `mov reg,1`)."""
    b = bytes(d[site - CODE_V2F:site - CODE_V2F + 5]); cave = ZONE + (SHOW_OFF if show else NF_OFF)
    if b == orig: return False, None
    assert b[0] == 0xE8, "%#x: unexpected bytes %s" % (site, b.hex())
    t = site + 5 + struct.unpack("<i", b[1:])[0]
    if t != cave: return False, t
    o = cave + pick_tail_off(show); tb = bytes(d[o - CODE_V2F:o - CODE_V2F + 5])
    if tb[0] == 0xE9: return True, o + 5 + struct.unpack("<i", tb[1:])[0]
    assert tb[0] in (0xBA, 0xB8), "our pick cave tail unreadable: %s" % tb.hex()
    return True, None


def castsnd_build(ids):
    src = "mov eax, dword ptr [ebp-4]\n" + "".join("cmp dword ptr [eax+0x38], %#x\nje %#x\n" % (i, CASTSND_SKIP) for i in ids) + "jmp %#x\n" % CASTSND_PLAY
    return bytes(ks.asm(src, CASTSND)[0])


def castsnd_parse(blob):
    """-> exclusion id list, or None when the cave is not the expected `mov / (cmp, je skip)* / jmp play / zeros`."""
    ins = list(cs.disasm(blob, CASTSND)); ids = []; k = 1
    if not ins or ins[0].mnemonic != "mov" or ins[0].op_str != "eax, dword ptr [ebp - 4]": return None
    while k + 1 < len(ins) and ins[k].mnemonic == "cmp" and ins[k].op_str.startswith("dword ptr [eax + 0x38], "):
        if ins[k + 1].mnemonic != "je" or int(ins[k + 1].op_str, 16) != CASTSND_SKIP: return None
        ids.append(int(ins[k].op_str.split(", ")[1], 16)); k += 2
    code = castsnd_build(ids)
    if blob[:len(code)] != code or any(blob[len(code):]): return None
    return ids


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
        if i.mnemonic.startswith("j") or i.mnemonic == "call" or (i.mnemonic == "sub" and i.op_str.startswith("ebx, ")): continue   # the delta anchor
        for o in i.operands:
            if o.type == capstone.x86.X86_OP_IMM and BASE <= o.imm < hi: bad.append("%08X %s %s" % (i.address, i.mnemonic, i.op_str))
            if o.type == capstone.x86.X86_OP_MEM and BASE <= o.mem.disp < hi and o.mem.base != capstone.x86.X86_REG_EBX:
                bad.append("%08X %s %s" % (i.address, i.mnemonic, i.op_str))
    return bad


def pfs_state():
    """Live Spells.pfs record 397+10: (gfx slots list, sound list)."""
    p = open(PFS, "rb").read(); pairs, kb = G.pfs_tab(p, 7); idx = {t: kb + o for t, o in pairs}
    key = SPELL_ID + 10; nxt = min([v for v in idx.values() if v > idx[key]] + [len(p) - 4])
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
    lb = bytes(d[LAND_SITE - CODE_V2F:LAND_SITE - CODE_V2F + len(LAND_ORIG)])
    land_hook = b"\xe9" + struct.pack("<i", ZONE + LAND_OFF - (LAND_SITE + 5)) + b"\x90" * (len(LAND_ORIG) - 5)
    land_state = "vanilla" if lb == LAND_ORIG else "ours" if lb == land_hook else "FOREIGN"
    nf_ours, nf_prev = pick_state(d, NF_SITE, NF_ORIG, False)
    sh_ours, sh_prev = pick_state(d, SHOW_SITE, SHOW_ORIG, True)
    gate = build(chain); land = build_land(); nf = build_pick(False, nf_prev); show = build_pick(True, sh_prev)
    assert len(gate) <= LAND_OFF and LAND_OFF + len(land) <= NF_OFF and NF_OFF + len(nf) <= SHOW_OFF and ZONE + SHOW_OFF + len(show) <= ZONE_END, (len(gate), len(land), len(nf), len(show))
    zone = bytearray(ZONE_END - ZONE)
    zone[0:len(gate)] = gate; zone[LAND_OFF:LAND_OFF + len(land)] = land; zone[NF_OFF:NF_OFF + len(nf)] = nf; zone[SHOW_OFF:SHOW_OFF + len(show)] = show
    zone = bytes(zone)
    zl = bytes(d[ZONE - CODE_V2F:ZONE_END - CODE_V2F])
    v2 = bytearray(ZONE_END - ZONE); gv2 = build(chain, GAP_TICKS_V2); v2[0:len(gv2)] = gv2
    prev = []
    global CUE_EARLY
    cue_now = CUE_EARLY
    for ce in (cue_now,) + tuple(c for c in CUE_EARLY_PREV if c != cue_now):                    # earlier v3 builds (other ring holds / cue leads)
        CUE_EARLY = ce; lp = build_land()
        for rt in (RING_TICKS,) + RING_TICKS_PREV:
            v3a = bytearray(zone); gp = build(chain, None, rt); v3a[0:LAND_OFF] = bytes(LAND_OFF); v3a[0:len(gp)] = gp
            v3a[LAND_OFF:LAND_OFF + len(lp)] = lp; prev.append(bytes(v3a))
    CUE_EARLY = cue_now
    zstate = "zero" if not any(zl) else "ours" if zl == zone else "v2" if zl == bytes(v2) else "v3r24" if zl in prev else "DIFFERS"
    csb = bytes(d[CASTSND - CODE_V2F:CASTSND_END - CODE_V2F]); ids = castsnd_parse(csb)
    rl = relocs(bytes(d))
    hooks = [(ZONE - 3, ZONE_END), (CASTSND - 3, CASTSND_END), (LAND_SITE - 3, LAND_SITE + len(LAND_ORIG)), (NF_SITE - 3, NF_SITE + 5), (SHOW_SITE - 3, SHOW_SITE + 5)] + [(st - 3, st + 5) for st, _ in GATE_SITES]
    bad = [hex(r) for r in rl if any(lo <= r < hi_ for lo, hi_ in hooks)]
    audit = abs_audit(gate, ZONE, hi) + abs_audit(land, ZONE + LAND_OFF, hi) + abs_audit(nf, ZONE + NF_OFF, hi) + abs_audit(show, ZONE + SHOW_OFF, hi) \
        + abs_audit(castsnd_build((ids or []) + [SPELL_ID]), CASTSND, hi)
    slots, snd = pfs_state()
    sl1 = slots[1] if len(slots) > 1 else None; sl2 = slots[FADE_SLOT] if len(slots) > FADE_SLOT else None
    pre = {"pfs 397 gfx slot 1": bool(sl1 and sl1.get("frames")), "pfs 397 gfx slot 2 (fade)": bool(sl2 and sl2.get("frames")),
           "pfs 397 sfx cue 1 (per-strike)": len(snd) > 1}
    print("gate sites %s -> chain %#x | land %s | nf %s -> %s | show %s -> %s | zone %s (gate %d / land %d / nf %d / show %d B @%#x) | wait %#x: ring %d, gap %d, cue early %d | castsnd ids %s | relocs %s | abs audit %s"
          % ("ours" if ours else "pass-through", chain, land_state, "ours" if nf_ours else "site", hex(nf_prev) if nf_prev else "vanilla",
             "ours" if sh_ours else "site", hex(sh_prev) if sh_prev else "vanilla", zstate, len(gate), len(land), len(nf), len(show), ZONE,
             WAIT_VA, RING_TICKS, GAP_TICKS, CUE_EARLY, [hex(i) for i in ids] if ids is not None else "UNPARSEABLE", bad or "none", audit or "clean"))
    print("pfs 397: slot 0 = %s | slot 1 = %s | slot 2 = %s | sfx = %s | prerequisites %s"
          % (seqdesc(slots[0]) if slots and slots[0] and slots[0].get("frames") else None, seqdesc(sl1) if pre["pfs 397 gfx slot 1"] else sl1,
             seqdesc(sl2) if pre["pfs 397 gfx slot 2 (fade)"] else sl2, snd, pre))
    if pre["pfs 397 gfx slot 1"] and len(sl1["frames"]) * (sl1["f18"] + 1) <= RING_TICKS:
        print("WARNING: slot 1 lives %d ticks <= RING_TICKS %d" % (len(sl1["frames"]) * (sl1["f18"] + 1), RING_TICKS))
    if slots and slots[0] and slots[0].get("frames") and len(slots[0]["frames"]) * (slots[0]["f18"] + 1) - 1 <= CUE_EARLY:
        print("WARNING: slot 0 too short for CUE_EARLY %d - the early cue would never fire" % CUE_EARLY)
    if a.dis:
        for va, code in ((ZONE, gate), (ZONE + LAND_OFF, land), (ZONE + NF_OFF, nf), (ZONE + SHOW_OFF, show)):
            for i in cs.disasm(code, va): print("   %08X  %-18s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
            print()
    if bad or audit or ids is None or land_state == "FOREIGN": print("ABORT (relocs / absolutes / castsnd shape / land site)"); return 1
    if a.revert:
        if not ours or (nf_prev is not None and not nf_ours and call_target(d, NF_SITE) != ZONE + NF_OFF and zstate == "ours") \
                or (zstate == "ours" and (not nf_ours or not sh_ours)):
            print("ABORT revert: another gate/pick cave sits in front of this one (or it is not applied) - revert that one first"); return 1
        for st, nx in GATE_SITES: d[st - CODE_V2F:st - CODE_V2F + 5] = b"\xe8" + struct.pack("<i", chain - nx)
        if land_state == "ours": d[LAND_SITE - CODE_V2F:LAND_SITE - CODE_V2F + len(LAND_ORIG)] = LAND_ORIG
        if nf_ours: d[NF_SITE - CODE_V2F:NF_SITE - CODE_V2F + 5] = (b"\xe8" + struct.pack("<i", nf_prev - (NF_SITE + 5))) if nf_prev else NF_ORIG
        if sh_ours: d[SHOW_SITE - CODE_V2F:SHOW_SITE - CODE_V2F + 5] = (b"\xe8" + struct.pack("<i", sh_prev - (SHOW_SITE + 5))) if sh_prev else SHOW_ORIG
        d[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
        if SPELL_ID in ids:
            c = castsnd_build([i for i in ids if i != SPELL_ID]); d[CASTSND - CODE_V2F:CASTSND_END - CODE_V2F] = c + bytes(CASTSND_END - CASTSND - len(c))
        with open(DLL, "r+b") as f: f.write(bytes(d))
        print("reverted (gate sites -> %#x, land vanilla, nf -> %s, show -> %s, castsnd ids %s)"
              % (chain, hex(nf_prev) if nf_prev else "vanilla", hex(sh_prev) if sh_prev else "vanilla", [hex(i) for i in ids if i != SPELL_ID])); return 0
    if ours and zstate == "ours" and land_state == "ours" and nf_ours and sh_ours and SPELL_ID in ids: print("already applied"); return 0
    if zstate == "DIFFERS" or (zstate in ("ours", "v2", "v3r24") and not ours): print("ABORT (zone not free / not ours)"); return 1
    if zstate != "zero" and ((nf_prev and not nf_ours and ZONE <= nf_prev < ZONE_END) or (sh_prev and not sh_ours and ZONE <= sh_prev < ZONE_END)):
        print("ABORT (a pick site already chains into this zone through someone else)"); return 1
    d[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = zone
    for st, nx in GATE_SITES: d[st - CODE_V2F:st - CODE_V2F + 5] = b"\xe8" + struct.pack("<i", ZONE - nx)
    d[LAND_SITE - CODE_V2F:LAND_SITE - CODE_V2F + len(LAND_ORIG)] = land_hook
    d[NF_SITE - CODE_V2F:NF_SITE - CODE_V2F + 5] = b"\xe8" + struct.pack("<i", ZONE + NF_OFF - (NF_SITE + 5))
    d[SHOW_SITE - CODE_V2F:SHOW_SITE - CODE_V2F + 5] = b"\xe8" + struct.pack("<i", ZONE + SHOW_OFF - (SHOW_SITE + 5))
    if SPELL_ID not in ids:
        c = castsnd_build(ids + [SPELL_ID]); assert len(c) <= CASTSND_END - CASTSND
        d[CASTSND - CODE_V2F:CASTSND_END - CODE_V2F] = c + bytes(CASTSND_END - CASTSND - len(c))
    missing = [k for k, v in pre.items() if not v]
    if not a.apply:
        if missing: print("NOTE: --apply will refuse until the pipeline provides: %s (see the docstring)" % missing)
        print("Dry run OK%s - rerun with --apply (or --revert)." % (" (%s is applied: --apply upgrades it in place)" % zstate if zstate in ("v2", "v3r24") else "")); return 0
    if not pre["pfs 397 gfx slot 1"] or not pre["pfs 397 gfx slot 2 (fade)"]:
        print("ABORT: 397 lacks gfx slot 1 and/or 2 in Release\\Spells.pfs (a driver would draw an empty slot)"); return 1
    bak = bak_path(DLL, ".bak_flashfreeze")
    if not os.path.exists(bak): shutil.copy2(DLL, bak); print("backup ->", bak)
    with open(DLL, "r+b") as f: f.write(bytes(d))
    assert open(DLL, "rb").read() == bytes(d); print("Written and verified"); return 0


if __name__ == "__main__":
    sys.exit(main())
