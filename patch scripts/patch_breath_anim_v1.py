#!/usr/bin/env python3
r"""
Tactical breath attacks: restore the vanilla spray ANIMATION while keeping patch_breath_line_v1's per-strike block line
(AoWTCPCK.dll, 2026-10-18).  Layered on top of patch_breath_line_v1.py (required).

User: "we fixed breath attacks (how they target/hit) but the breath animations got janky - it looks like one straight
breath and a side-to-side breath for the same breath, in open space".

ROOT CAUSE.  A breath (ability category 5) is [te+0x28] = 0x14 = 20 strikes (TCAbRangedTE setup 0x40B520).  Each strike
is one fx (NextStrike 0x40D290, fx = [ebp-0x10]) that flies along ITS OWN path [fx+0x1C], and that path is exactly the
line MakeRangedPath 0x427630 builds for the obstruction test (0x40D65F: &blocks = [ebp-0x5C], &points = fx+0x1C).
Vanilla aims every strike at the cone's full depth rotated by (f*6-30) deg, f = s (s > 9: 19-s): strikes 0..9 sweep
-30 -> +24 deg, strikes 10..19 sweep back +24 -> -30 deg = the side-to-side spray.  patch_breath_line_v1 (0x40D5F1 ->
0x43AB40) re-aims strikes 0..11 at their own DAMAGE hex (BreathHN[BreathHit[s]], order 0,1,4,7,8,2,5,9,10,3,6,11) so
the 12 damaging strikes became short/long jets jumping between hexes (the "straight breath"), followed by the 8
untouched animation-only strikes 12..19 sweeping back (the "side-to-side breath").  The damage hex itself is written
after the call (0x40D671..0x40D72A) and is unaffected.

FIX (two hooks + 24 B of state, s < 12 only; strikes 12..19 stay vanilla):
  A 0x40D5F1 (the breath-line hook `jmp 0x43AB40`) -> SAVE cave: latch te / s and the VANILLA fan values the call is
    about to push (target hex [ebp-0x48]/[ebp-0x4C], pixel offset [ebp-0x3C]/[ebp-0x40]) into G, then jmp the
    breath-line cave (unchanged: it re-aims the block line at the damage hex).
  B 0x40F0B1 (category-5-only tail `mov eax,[ebp-0x10] / xor edx,edx / mov [eax+0x2C],edx`, 8 B, after the block loop
    0x40EE41..0x40F0A2 and Gust's SPR call at 0x40F0A8): for a breath strike s < 12 whose G latch matches (te, s), and
    not Gust / Crashing Wave (spell [te+0x14] == 0x34 and [te+0x18] in {212, 220}: their forward spray is built from the
    damage-hex path by Gust's SPR and their slot 0 is blank - unchanged):
      1. blocked = [fx+0x24] <= 0 (0x40F06F zeroes the damage hex when the block line is stopped; breath ignores units)
         -> D2 = squared pixel distance from the path's first to its (truncated) last point;
      2. free the block records in [ebp-0x5C] (the function epilogue 0x40F3F7 frees whatever the list holds);
      3. MakeRangedPath again with the SAVED vanilla values -> [fx+0x1C] = the vanilla fan line (TXYZList.Clear frees
         the old points), [ebp-0x5C] = its block records (freed by the epilogue as usual);
      4. blocked -> delete fan points from the end while they lie farther than D2 from the start, so the spray stops
         about where the strike was stopped (open space: never blocked -> full vanilla sweep).
    then replay the 8 bytes and jmp 0x40F0B9 (vanilla `jmp 0x40F227`).
  Damage hexes, block results ([fx+0x24]/[fx+0x28]/[fx+0x2C]), RNG use (MakeRangedPath calls no Random) and strike
  order are untouched -> every machine runs the same token code -> multiplayer-safe.  Only the fx path changes.
State G (DATA page slack past the raw size, zero-filled, unreferenced): 0x46BF20 te, +4 s, +8 x, +0xC y, +0x10 ox,
+0x14 oy (Ashes' trace ring ends 0x46BF10, oil gush 0x46BF40).  Zone AoWTCPCK 0x451000..0x451400: +0 'BAN1', +4 the
previous site-A target (0x43AB40), +8 site-B original 8 B, code at +0x20.  PIC (call/pop delta) for G; rel32 calls.
LIFO: apply AFTER patch_breath_line_v1.py; revert THIS before patch_breath_line_v1.py (whose --revert is a whole-file
restore of a 2026-09-21 backup - see full-file-backup-revert-gotcha) and before re-running it.  Site B is not used by
any other script (Gust's SPR is 0x40F0A8, Crashing Wave's BLK 0x40F06F).
Backup <game>\backup\AoWTCPCK.dll.bak_breathanim.  Dry-run default; --apply; --revert (exact: sites + zone); --dis.
"""
import argparse, os, shutil, struct, sys
from bakpath import game_file, bak_path
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

DEFAULT_DLL = game_file(r"AoWTCPCK.dll")
BAK = ".bak_breathanim"
BASE = 0x400000
MAGIC = b"BAN1"
ZONE, ZONE_END = 0x451000, 0x451400
CODE = ZONE + 0x20
G = 0x46BF20                      # te, s, x, y, ox, oy
G_END = G + 0x18
SITE_A = 0x40D5F1                 # breath-line hook (jmp 0x43AB40)
PREV_A_EXPECT = 0x43AB40
SITE_B = 0x40F0B1
SITE_B_ORIG = bytes.fromhex("8b45f033d289502c")
RESUME_B = 0x40F0B9               # vanilla `jmp 0x40F227`
MRP = 0x427630                    # MakeRangedPath
SIDE = 0x40252C                   # thunk: side of the shooter HS (al)
LST_GET, OBJ_FREE = 0x40153C, 0x401050      # TList.Get(eax=list, edx=i) / TObject.Free(eax)
XYZ_GET, XYZ_DEL, XYZ_CNT = 0x402DF4, 0x402DEC, 0x402DFC   # TXYZList.GetXYZ / Delete / GetCount thunks
STRIKES = 12
GUST, CWAVE = 212, 220
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, va):
    return bytes(ks.asm(src, va)[0])


def cave_save(va, prev_a):
    # entered by `jmp` from SITE_A; must leave all registers / flags as found and continue at prev_a
    head = asm("pushfd\npush eax\npush ebx", va)
    c = va + len(head); nxt = c + 5
    body = asm(f"""
        pop ebx
        sub ebx, {nxt:#x}
        mov eax, [ebp-4]
        mov [ebx+{G:#x}], eax
        mov eax, [eax+0x34]
        mov [ebx+{G+4:#x}], eax
        mov eax, [ebp-0x48]
        mov [ebx+{G+8:#x}], eax
        mov eax, [ebp-0x4C]
        mov [ebx+{G+0xC:#x}], eax
        mov eax, [ebp-0x3C]
        mov [ebx+{G+0x10:#x}], eax
        mov eax, [ebp-0x40]
        mov [ebx+{G+0x14:#x}], eax
        pop ebx
        pop eax
        popfd
    """, nxt)
    p = head + asm(f"call {nxt:#x}", c) + body
    p += asm(f"jmp {prev_a:#x}", va + len(p))
    return p


def cave_fan(va):
    # entered by `jmp` from SITE_B (category 5 only); ends with the replayed 8 bytes + jmp RESUME_B
    head = asm("pushad\nsub esp, 8", va)
    c = va + len(head); nxt = c + 5
    body = f"""
        pop ebx
        sub ebx, {nxt:#x}
        mov edi, [ebp-4]
        mov esi, [edi+0x34]
        cmp esi, {STRIKES}
        jae f_out
        cmp [ebx+{G:#x}], edi
        jne f_out
        cmp [ebx+{G+4:#x}], esi
        jne f_out
        mov dword ptr [ebx+{G:#x}], 0
        cmp dword ptr [edi+0x14], 0x34
        jne f_go
        mov eax, [edi+0x18]
        cmp eax, {GUST}
        je f_out
        cmp eax, {CWAVE}
        je f_out
    f_go:
        mov esi, [ebp-0x10]
        mov dword ptr [esp], 0
        mov dword ptr [esp+4], 0
        cmp dword ptr [esi+0x24], 0
        jg f_free
        mov dword ptr [esp], 1
        mov eax, [esi+0x1C]
        call {XYZ_CNT:#x}
        cmp eax, 2
        jl f_free
        lea edx, [eax-1]
        mov eax, [esi+0x1C]
        call {XYZ_GET:#x}
        push dword ptr [eax+8]
        push dword ptr [eax+4]
        xor edx, edx
        mov eax, [esi+0x1C]
        call {XYZ_GET:#x}
        pop ecx
        sub ecx, [eax+4]
        imul ecx, ecx
        pop edx
        sub edx, [eax+8]
        imul edx, edx
        add ecx, edx
        mov [esp+4], ecx
    f_free:
        mov eax, [ebp-0x5C]
        mov edi, [eax+8]
    f_fl:
        dec edi
        js f_mrp
        mov edx, edi
        mov eax, [ebp-0x5C]
        call {LST_GET:#x}
        call {OBJ_FREE:#x}
        jmp f_fl
    f_mrp:
        mov edi, [ebp-4]
        push 0x32
        mov eax, [edi+0x10]
        mov eax, [eax+0x60]
        mov edx, [eax]
        call [edx+0x74]
        movsx eax, al
        push eax
        mov eax, [edi+0x10]
        mov eax, [eax+0x60]
        mov edx, [eax]
        call [edx+0x78]
        movsx eax, al
        push eax
        push dword ptr [ebx+{G+8:#x}]
        push dword ptr [ebx+{G+0xC:#x}]
        push dword ptr [ebx+{G+0x10:#x}]
        push dword ptr [ebx+{G+0x14:#x}]
        push 0
        lea eax, [esi+0x1C]
        push eax
        lea eax, [ebp-0x5C]
        push eax
        mov eax, [edi+0x10]
        call {SIDE:#x}
        mov cx, 0x14
        mov dx, 0x32
        call {MRP:#x}
        cmp dword ptr [esp], 0
        je f_out
    f_cut:
        mov eax, [esi+0x1C]
        call {XYZ_CNT:#x}
        cmp eax, 2
        jl f_out
        mov edi, eax
        lea edx, [eax-1]
        mov eax, [esi+0x1C]
        call {XYZ_GET:#x}
        push dword ptr [eax+8]
        push dword ptr [eax+4]
        xor edx, edx
        mov eax, [esi+0x1C]
        call {XYZ_GET:#x}
        pop ecx
        sub ecx, [eax+4]
        imul ecx, ecx
        pop edx
        sub edx, [eax+8]
        imul edx, edx
        add ecx, edx
        cmp ecx, [esp+4]
        jle f_out
        lea edx, [edi-1]
        mov eax, [esi+0x1C]
        call {XYZ_DEL:#x}
        jmp f_cut
    f_out:
        add esp, 8
        popad
        mov eax, [ebp-0x10]
        xor edx, edx
        mov [eax+0x2C], edx
        jmp {RESUME_B:#x}
    """
    return head + asm(f"call {nxt:#x}", c) + asm(body, nxt)


def build(prev_a):
    sv = cave_save(CODE, prev_a)
    fan_va = (CODE + len(sv) + 15) & ~15
    fan = cave_fan(fan_va)
    assert fan_va + len(fan) <= ZONE_END, hex(fan_va + len(fan))
    return sv, fan_va, fan


def va2off(pe, va):
    e = struct.unpack_from("<I", pe, 0x3C)[0]
    n = struct.unpack_from("<H", pe, e + 6)[0]
    opt = struct.unpack_from("<H", pe, e + 20)[0]
    for i in range(n):
        s = e + 24 + opt + 40 * i
        vsz, rva, rsz, roff = struct.unpack_from("<IIII", pe, s + 8)
        if rva <= va - BASE < rva + max(vsz, rsz):
            return roff + (va - BASE - rva)
    raise ValueError(hex(va))


def reloc_hits(pe, ranges):
    e = struct.unpack_from("<I", pe, 0x3C)[0]
    rva, sz = struct.unpack_from("<II", pe, e + 24 + 0x88)
    off = va2off(pe, BASE + rva); end = off + sz; hits = []
    while off + 8 <= end:
        page, bsz = struct.unpack_from("<II", pe, off)
        if bsz < 8:
            break
        for i in range((bsz - 8) // 2):
            ent = struct.unpack_from("<H", pe, off + 8 + 2 * i)[0]
            if ent >> 12:
                va = BASE + page + (ent & 0xFFF)
                if any(lo - 3 <= va < hi for lo, hi in ranges):
                    hits.append(va)
        off += bsz
    return hits


def g_refs(pe):
    """absolute references to the G slots anywhere in the image (should be none but ours)."""
    out = []
    for i in range(len(pe) - 3):
        v = struct.unpack_from("<I", pe, i)[0]
        if G <= v < G_END:
            out.append(i)
    return out


def jmp(src, dst, ln):
    return b"\xe9" + struct.pack("<i", dst - (src + 5)) + b"\x90" * (ln - 5)


def rel_target(d, va):
    o = va2off(d, va)
    return va + 5 + struct.unpack_from("<i", d, o + 1)[0] if d[o] in (0xE8, 0xE9) else None


def state(d):
    oa, ob, oz = va2off(d, SITE_A), va2off(d, SITE_B), va2off(d, ZONE)
    ta = rel_target(d, SITE_A)
    zone = bytes(d[oz:oz + (ZONE_END - ZONE)])
    ours = zone[:4] == MAGIC
    b = bytes(d[ob:ob + 8])
    return ta, b, ours, zone


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dll", nargs="?", default=DEFAULT_DLL)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read())
    ta, b, ours, zone = state(d)
    print(f"target: {a.dll}")
    print(f"  site A {SITE_A:#x}: {'jmp %#x' % ta if ta else 'NOT A JMP ' + bytes(d[va2off(d, SITE_A):][:5]).hex()}"
          f"  site B {SITE_B:#x}: {b.hex()}  zone {ZONE:#x}: {'OURS' if ours else 'zero' if not any(zone) else 'FOREIGN'}")
    rl = reloc_hits(d, [(SITE_A, SITE_A + 5), (SITE_B, SITE_B + 8), (ZONE, ZONE_END)])
    gr = [o for o in g_refs(d) if not (va2off(d, ZONE) <= o < va2off(d, ZONE_END))]
    print(f"  relocs: {[hex(v) for v in rl] or 'none'}; foreign refs to G {G:#x}..{G_END:#x}: {gr or 'none'}")

    if a.revert:
        if not ours:
            sys.exit("not applied (zone has no BAN1 header) - nothing to revert")
        prev_a = struct.unpack_from("<I", zone, 4)[0]
        orig_b = zone[8:16]
        sv, fan_va, fan = build(prev_a)
        if ta != CODE:
            sys.exit(f"site A no longer jumps to our cave ({ta and hex(ta)}) - a later script re-hooked it; refusing")
        if b != jmp(SITE_B, fan_va, 8):
            sys.exit("site B is not our jmp - refusing")
        oa, ob, oz = va2off(d, SITE_A), va2off(d, SITE_B), va2off(d, ZONE)
        d[oa:oa + 5] = jmp(SITE_A, prev_a, 5)
        d[ob:ob + 8] = orig_b
        d[oz:oz + (ZONE_END - ZONE)] = bytes(ZONE_END - ZONE)
        with open(a.dll, "r+b") as f:
            f.seek(0); f.write(d)
        print(f"reverted: site A -> jmp {prev_a:#x}, site B restored, zone zeroed")
        return

    if ours:
        prev_a = struct.unpack_from("<I", zone, 4)[0]
    else:
        if ta is None or d[va2off(d, SITE_A)] != 0xE9:
            sys.exit("site A is not the breath-line jmp - apply patch_breath_line_v1.py first")
        prev_a = ta
        if prev_a != PREV_A_EXPECT:
            print(f"  note: site A jumps to {prev_a:#x}, not breath-line's {PREV_A_EXPECT:#x} - chaining to it")
    sv, fan_va, fan = build(prev_a)
    if a.dis:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
        md = Cs(CS_ARCH_X86, CS_MODE_32)
        for va, blob, name in ((CODE, sv, "save"), (fan_va, fan, "fan")):
            print(f"\n; ---- {name} @{va:#x} ({len(blob)} B) ----")
            for ins in md.disasm(blob, va):
                print(f"{ins.address:08X}  {ins.mnemonic:<7} {ins.op_str}")
    print(f"  caves: save {CODE:#x} ({len(sv)} B), fan {fan_va:#x} ({len(fan)} B), end {fan_va + len(fan):#x}")
    if ours:
        want_b = jmp(SITE_B, fan_va, 8)
        same = zone[0x20:0x20 + len(sv)] == sv and ta == CODE and b == want_b
        print("  state: APPLIED" + ("" if same else " (stale cave - will rewrite in place)"))
        if same:
            print("already applied"); return
        orig_b = zone[8:16]
    else:
        if b != SITE_B_ORIG:
            sys.exit(f"site B bytes {b.hex()} are neither vanilla nor ours - refusing")
        if any(zone):
            sys.exit("zone not zero - refusing")
        orig_b = SITE_B_ORIG
        print("  state: vanilla (breath-line present)")
    if not a.apply:
        print("dry run - nothing written (use --apply)"); return
    if rl:
        sys.exit("relocs intersect the patch - refusing")
    if gr:
        sys.exit("G slots are referenced elsewhere in the image - refusing")
    bak = bak_path(a.dll, BAK, create=True)
    if not os.path.exists(bak):
        shutil.copy2(a.dll, bak); print(f"  backup -> {bak}")
    oz = va2off(d, ZONE)
    z = bytearray(ZONE_END - ZONE)
    z[0:4] = MAGIC; struct.pack_into("<I", z, 4, prev_a); z[8:16] = orig_b
    z[0x20:0x20 + len(sv)] = sv
    z[fan_va - ZONE:fan_va - ZONE + len(fan)] = fan
    d[oz:oz + len(z)] = z
    oa, ob = va2off(d, SITE_A), va2off(d, SITE_B)
    d[oa:oa + 5] = jmp(SITE_A, CODE, 5)
    d[ob:ob + 8] = jmp(SITE_B, fan_va, 8)
    with open(a.dll, "r+b") as f:
        f.seek(0); f.write(d)
    print("applied.")


if __name__ == "__main__":
    main()
