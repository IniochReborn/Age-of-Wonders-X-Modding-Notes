#!/usr/bin/env python3
r"""
Tactical AI: honest obstruction trade-off for ranged shots (AoWTCPCK.dll, 2026-09-18).

All in AoWTC.TCAI.CheckUnit's ranged handler (0x417420..).  RE facts: memory aowx-ranged-obstacles.
  [ebp-0x64] DEV_cur  = shot value from the CURRENT hex after TCAI.EvalPath (obstruction, friendly fire)
  [ebp-0x28] DEV0     = clean value (saved at 0x41759B before EvalPath)
  [ebp-0x58] "loss"   = DEV0 - DEV_cur, later overwritten by the (a)-search result
  [ebp-0x68] terrain path self->target (index 0 = own hex), [ebp-0x6C] path2 (best alternative spot -> end)
  [ebp-0x14] AddMove pct (100, or 10 vs walls after round 1), [ebp-0x18] divisor of the vanilla split,
  [ebp-0x54] positional term, [ebp-0x2C] chosen path index, [ebp+0x10] target, [ebp+0x14] self, [ebp-4] cai.
  Move types (phase-5 table 0x41A4E8): 3 = fire now (AbRangedTC), 5 = WALK to a firing spot (same handler
  as type 0) -- moving forbids shooting for the rest of the turn, so a type-5 move is always a next-turn shot.

Vanilla behaviour being replaced:
  (a) obstructed now: backward search over the path for a strictly-lower-loss hex; if found the walk is
      valued as if that hex were CLEAN ([ebp-0x58] := DEV0) and the split formula share^2/total makes the
      walk beat the shot for ANY strict improvement (10 % now vs 9 % there -> walk, shot forfeited).
  (b) out of range / already moved: forward search accepting only hexes with EXACTLY 0 % and no unit of
      either side in the line; last (closest-to-target) accepted wins.

Patch (8 hooks, all rel32/PIC caves, coexists with patch_ai_melee_vs_ranged_v1 (0x417451/0x417510) and
patch_heal_ai_tcpck_v1 (touch handler) -- none of their bytes are touched):
  H0 0x41747E  handler init: [ebp-0xA4] (best (b) value) := -1, [ebp-0x9C] (DEV0 copy) := 0.
  H1 0x41759B  DEV0 copy := [ebp-0x64] (the hook keeps the vanilla [ebp-0x28] store).
  H2 0x4179CE  (a) found a better hex: [ebp-0x58] := DEV_best * D / 100 instead of DEV0.
               D = walk discount = P(the shot is still there next turn):
                 BASE_PCT / HERO_PCT / LEADER_PCT by the TARGET's class (leader checked first),
                 * DANGER_PCT/100 when the SHOOTER is in mortal danger (cur HP <= summed GetDamage of living
                   enemies that can REACH it next turn, dist <= GetMoves/HEX_MP + 1; adjacent-only before 2026-09-20),
                 := HOPELESS_PCT when additionally the shooter is low-value (strength < LOWVAL_PCT % of the
                   strongest living own unit) -- a cheap dying unit shoots no matter what.
  H5 0x417D2C  shoot-now (type 3) divisor := DEV_cur  ->  value = DEV_cur * pct   (was DEV_cur^2/|DEV_cur+X|)
  H6 0x417E15  walk (type 5, in range) divisor := [ebp-0x58] -> value = (DEV_best*D/100 + pos) * pct
               The phase-4 sort then compares DEV_cur against DEV_best*D directly: the unit walks only when
               the destination's REAL value, discounted, beats the shot it has right now.
  H3 0x417A59  (b) candidate evaluation starts from DEV0 instead of the 1000 sentinel.
  H4 0x417AB2  (b) acceptance: value_i*100 >= DEV0*ACCEPT_PCT and value_i >= best so far (ties -> later =
               closer to target, as vanilla); best kept in [ebp-0xA4].
  H7 0x417F3C  else-branch walk value := best_(b) * D_base/100 + pos when (b) chose a hex (D_base = target
               class only, no shoot-now competitor there); vanilla sum otherwise.
Caves 0x439E00.. (zero-verified to 0x466BAC).  Backup AoWTCPCK.dll.bak_rangedobs (in <game>\backup\).
Dry-run default; --apply; --revert; --dis.
"""
import argparse, os, shutil, struct, sys
from bakpath import game_dir, game_file   # game folder = AOW_GAME_DIR or parent of patch scripts (2026-09-20)
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

DEFAULT_DLL = game_file(r"AoWTCPCK.dll")
BAK = ".bak_rangedobs"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path
BASE = 0x400000

# ---- tunables (all percent) --------------------------------------------------------------------
BASE_PCT = 65        # walk discount, ordinary target: shoots now through up to ~35 % when a clean hex exists
HERO_PCT = 45        # ... hero target  (~55 %)
LEADER_PCT = 30      # ... leader target (~70 %)
DANGER_PCT = 50      # multiplier on the above when the shooter is in mortal danger
HOPELESS_PCT = 0     # discount when the shooter is in danger AND low value (0 = always take the shot)
LOWVAL_PCT = 40      # "low value" = strength below this % of the strongest living own unit
HEX_MP = 4           # 2026-09-20: 'danger' counts every living enemy that can REACH the shooter next turn (dist <= GetMoves/HEX_MP + 1), not only adjacent ones
ACCEPT_PCT = 50      # (b) search: a hex is a usable firing spot if its value >= this % of the clean value

# ---- engine facts -------------------------------------------------------------------------------
ISCLASS, DHX = 0x401058, 0x4022A4                 # System.@IsClass(eax=obj, edx=cls); dHXtoRad(eax=x1,edx=y1,ecx=x2,[y2])
IAT_THERO, IAT_TLEADER, IAT_TCUNIT = 0x46E914, 0x46E910, 0x46E904
CAVE_BASE, CAVE_END = 0x439E00, 0x43A400

# (name, hook VA, original bytes, resume VA)
H0 = ("init", 0x41747E, bytes.fromhex("33c08945a8"), 0x417483)
H1 = ("dev0", 0x41759B, bytes.fromhex("8b459c8945d8"), 0x4175A1)
H2 = ("a-found", 0x4179CE, bytes.fromhex("8b45d00145a87105e84d96feff"), 0x4179DB)
H3 = ("b-start", 0x417A59, bytes.fromhex("c745d8e8030000"), 0x417A60)
H4 = ("b-accept", 0x417AB2, bytes.fromhex("837de800750f817dd8e803000075068b45ec8945d4"), 0x417AC7)
H5 = ("shoot-div", 0x417D2C, bytes.fromhex("8945e8837de8017d07c745e801000000"), 0x417D3C)
H6 = ("walk-div", 0x417E15, bytes.fromhex("6a018b45ecf76da8"), 0x417E1D)
H7 = ("else-val", 0x417F3C, bytes.fromhex("8b55a80355ac7105e8df90feff03559c7105e8d590feff"), 0x417F53)
HOOKS = [H0, H1, H2, H3, H4, H5, H6, H7]

ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, addr):
    enc, _ = ks.asm(src, addr)
    return bytes(enc)


def asm_pic(va, pre, body):
    """pre ; call next ; next: <body starting with pop ebx / sub ebx, next>  -> ebx = load delta."""
    p = asm(pre, va) if pre.strip() else b""
    call_at = va + len(p)
    next_va = call_at + 5
    p += asm(f"call {next_va:#x}", call_at)
    p += asm(f"pop ebx\nsub ebx, {next_va:#x}\n" + body, next_va)
    return p


# ---- caves ---------------------------------------------------------------------------------------
def cave_udist(va):
    # eax = unit A, edx = unit B  ->  eax = hex distance (hex-space object at +0x60, VMT+0x74 x / +0x78 y)
    return asm(f"""
        push esi
        push edi
        mov esi, eax
        mov edi, edx
        mov eax, [edi+0x60]
        mov edx, [eax]
        call [edx+0x78]
        movsx eax, al
        push eax
        mov eax, [edi+0x60]
        mov edx, [eax]
        call [edx+0x74]
        movsx eax, al
        push eax
        mov eax, [esi+0x60]
        mov edx, [eax]
        call [edx+0x78]
        movsx eax, al
        push eax
        mov eax, [esi+0x60]
        mov edx, [eax]
        call [edx+0x74]
        movsx eax, al
        pop edx
        pop ecx
        call {DHX:#x}
        pop edi
        pop esi
        ret
    """, va)


def cave_disc(va, udist):
    # ecx = 1 -> include shooter danger/hopeless; 0 -> target class only.  Returns eax = discount pct.
    pre = """
        push ebx
        push esi
        push edi
        sub esp, 20
        mov [esp+12], ecx
    """
    body = f"""
        mov dword ptr [esp+16], {BASE_PCT}
        mov eax, [ebp+0x10]
        mov edx, [ebx+{IAT_TCUNIT:#x}]
        call {ISCLASS:#x}
        test al, al
        jz d_cls_done
        mov eax, [ebp+0x10]
        mov eax, [eax+0x4C]
        test eax, eax
        jz d_cls_done
        mov esi, eax
        mov edx, [ebx+{IAT_TLEADER:#x}]
        call {ISCLASS:#x}
        test al, al
        jz d_not_leader
        mov dword ptr [esp+16], {LEADER_PCT}
        jmp d_cls_done
    d_not_leader:
        mov eax, esi
        mov edx, [ebx+{IAT_THERO:#x}]
        call {ISCLASS:#x}
        test al, al
        jz d_cls_done
        mov dword ptr [esp+16], {HERO_PCT}
    d_cls_done:
        cmp dword ptr [esp+12], 0
        je d_ret
        xor eax, eax
        mov [esp], eax
        mov [esp+4], eax
        mov [esp+8], eax
    d_en_loop:
        mov eax, [ebp-4]
        mov eax, [eax+0x10]
        mov ecx, [esp+4]
        cmp ecx, [eax+8]
        jge d_en_end
        mov eax, [eax+4]
        mov esi, [eax+ecx*4]
        inc dword ptr [esp+4]
        test esi, esi
        jz d_en_loop
        test byte ptr [esi+0x47], 9
        jnz d_en_loop
        mov eax, esi
        mov edx, [ebp+0x14]
        call {udist:#x}
        mov edi, eax
        mov eax, esi
        mov edx, [esi]
        call [edx+0x94]
        cdq
        mov ecx, {HEX_MP}
        idiv ecx
        inc eax
        cmp edi, eax
        jg d_en_loop
        mov eax, esi
        mov edx, [esi]
        call [edx+0x78]
        movsx eax, al
        add [esp], eax
        jmp d_en_loop
    d_en_end:
        cmp dword ptr [esp], 0
        jle d_ret
        mov eax, [ebp+0x14]
        mov edx, [eax]
        call [edx+0x88]
        movsx eax, al
        cmp eax, [esp]
        jg d_ret
        xor eax, eax
        mov [esp+4], eax
    d_own_loop:
        mov eax, [ebp-4]
        mov eax, [eax+8]
        mov ecx, [esp+4]
        cmp ecx, [eax+8]
        jge d_own_end
        mov eax, [eax+4]
        mov esi, [eax+ecx*4]
        inc dword ptr [esp+4]
        test esi, esi
        jz d_own_loop
        test byte ptr [esi+0x47], 9
        jnz d_own_loop
        mov eax, esi
        mov edx, [esi]
        call [edx+0x5C]
        cmp eax, [esp+8]
        jle d_own_loop
        mov [esp+8], eax
        jmp d_own_loop
    d_own_end:
        mov eax, [ebp+0x14]
        mov edx, [eax]
        call [edx+0x5C]
        imul eax, eax, 100
        mov ecx, [esp+8]
        imul ecx, ecx, {LOWVAL_PCT}
        cmp eax, ecx
        jge d_danger
        mov dword ptr [esp+16], {HOPELESS_PCT}
        jmp d_ret
    d_danger:
        mov eax, [esp+16]
        imul eax, eax, {DANGER_PCT}
        cdq
        mov ecx, 100
        idiv ecx
        mov [esp+16], eax
    d_ret:
        mov eax, [esp+16]
        add esp, 20
        pop edi
        pop esi
        pop ebx
        ret
    """
    return asm_pic(va, pre, body)


def cave_h0(va):
    return asm(f"""
        xor eax, eax
        mov [ebp-0x58], eax
        mov dword ptr [ebp-0xA4], -1
        mov [ebp-0x9C], eax
        jmp {H0[3]:#x}
    """, va)


def cave_h1(va):
    return asm(f"""
        mov eax, [ebp-0x64]
        mov [ebp-0x28], eax
        mov [ebp-0x9C], eax
        jmp {H1[3]:#x}
    """, va)


def cave_h2(va, disc):
    return asm(f"""
        mov ecx, 1
        call {disc:#x}
        mov ecx, eax
        mov eax, [ebp-0x30]
        imul ecx
        mov ecx, 100
        cdq
        idiv ecx
        mov [ebp-0x58], eax
        jmp {H2[3]:#x}
    """, va)


def cave_h3(va):
    return asm(f"""
        mov eax, [ebp-0x9C]
        mov [ebp-0x28], eax
        jmp {H3[3]:#x}
    """, va)


def cave_h4(va):
    return asm(f"""
        mov eax, [ebp-0x28]
        mov ecx, [ebp-0x9C]
        test ecx, ecx
        jle h4_skip
        imul edx, eax, 100
        imul ecx, ecx, {ACCEPT_PCT}
        cmp edx, ecx
        jl h4_skip
        cmp eax, [ebp-0xA4]
        jl h4_skip
        mov [ebp-0xA4], eax
        mov eax, [ebp-0x14]
        mov [ebp-0x2C], eax
    h4_skip:
        jmp {H4[3]:#x}
    """, va)


def cave_h5(va):
    return asm(f"""
        mov eax, [ebp-0x64]
        cmp eax, 1
        jge h5_ok
        mov eax, 1
    h5_ok:
        mov [ebp-0x18], eax
        jmp {H5[3]:#x}
    """, va)


def cave_h6(va):
    # must end with the imul so the resume point's jno sees its flags
    return asm(f"""
        push 1
        mov eax, [ebp-0x58]
        cmp eax, 1
        jge h6_ok
        mov eax, 1
    h6_ok:
        mov [ebp-0x18], eax
        mov eax, [ebp-0x14]
        imul dword ptr [ebp-0x58]
        jmp {H6[3]:#x}
    """, va)


def cave_h7(va, disc):
    # ecx (move-pct for MultDEV) is live here -> preserved
    return asm(f"""
        cmp dword ptr [ebp-0xA4], 0
        jl h7_van
        push ecx
        xor ecx, ecx
        call {disc:#x}
        mov ecx, eax
        mov eax, [ebp-0xA4]
        imul ecx
        mov ecx, 100
        cdq
        idiv ecx
        mov edx, eax
        add edx, [ebp-0x54]
        pop ecx
        jmp {H7[3]:#x}
    h7_van:
        mov edx, [ebp-0x58]
        add edx, [ebp-0x54]
        add edx, [ebp-0x64]
        jmp {H7[3]:#x}
    """, va)


def build():
    """Returns (caves: list of (va, bytes, name), hook_targets: {hook name: cave va})."""
    caves, cur = [], CAVE_BASE

    def place(name, blob):
        nonlocal cur
        caves.append((cur, blob, name))
        va = cur
        cur = (cur + len(blob) + 15) & ~15
        return va

    udist = place("udist", cave_udist(cur))
    disc = place("disc", cave_disc(cur, udist))
    tgt = {}
    tgt["init"] = place("H0 init", cave_h0(cur))
    tgt["dev0"] = place("H1 dev0", cave_h1(cur))
    tgt["a-found"] = place("H2 a-found", cave_h2(cur, disc))
    tgt["b-start"] = place("H3 b-start", cave_h3(cur))
    tgt["b-accept"] = place("H4 b-accept", cave_h4(cur))
    tgt["shoot-div"] = place("H5 shoot-div", cave_h5(cur))
    tgt["walk-div"] = place("H6 walk-div", cave_h6(cur))
    tgt["else-val"] = place("H7 else-val", cave_h7(cur, disc))
    assert cur <= CAVE_END, f"caves overflow: {cur:#x}"
    return caves, tgt, cur


def va2off(pe_bytes, va):
    """Map VA to file offset via the section table."""
    e_lfanew = struct.unpack_from("<I", pe_bytes, 0x3C)[0]
    nsec = struct.unpack_from("<H", pe_bytes, e_lfanew + 6)[0]
    opt = struct.unpack_from("<H", pe_bytes, e_lfanew + 20)[0]
    sec = e_lfanew + 24 + opt
    for i in range(nsec):
        s = sec + 40 * i
        vsz, rva, rsz, roff = struct.unpack_from("<IIII", pe_bytes, s + 8)
        if rva <= va - BASE < rva + max(vsz, rsz):
            return roff + (va - BASE - rva)
    raise ValueError(f"VA {va:#x} not in any section")


def jmp_bytes(src, dst, ln):
    return b"\xe9" + struct.pack("<i", dst - (src + 5)) + b"\x90" * (ln - 5)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dll", nargs="?", default=DEFAULT_DLL)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    dll = a.dll
    bak = bak_path(dll, BAK, create=a.apply)

    caves, tgt, end = build()
    if a.dis:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
        md = Cs(CS_ARCH_X86, CS_MODE_32)
        for va, blob, name in caves:
            print(f"\n; ---- {name} @{va:#x} ({len(blob)} B) ----")
            for ins in md.disasm(blob, va):
                print(f"{ins.address:08X}  {ins.mnemonic:<7} {ins.op_str}")
        print(f"\ncaves end at {end:#x} (zone {CAVE_BASE:#x}..{CAVE_END:#x})")

    if a.revert:
        if not os.path.exists(bak):
            sys.exit(f"no backup {bak}")
        shutil.copy2(bak, dll)
        print(f"reverted {dll} from {bak}")
        return

    data = bytearray(open(dll, "rb").read())
    applied = all(data[va2off(data, h[1])] == 0xE9 for h in HOOKS)
    vanilla = all(bytes(data[va2off(data, h[1]):va2off(data, h[1]) + len(h[2])]) == h[2] for h in HOOKS)
    print(f"target: {dll}\n  hook sites: {'ALREADY PATCHED' if applied else 'vanilla' if vanilla else 'UNKNOWN BYTES'}")
    for va, blob, name in caves:
        print(f"  cave {name:14} {va:#x}..{va + len(blob):#x} ({len(blob)} B)")
    z0, z1 = va2off(data, CAVE_BASE), va2off(data, CAVE_END)
    zone_zero = all(b == 0 for b in data[z0:z1])
    print(f"  cave zone zero: {zone_zero}")
    print(f"  discounts: base {BASE_PCT} / hero {HERO_PCT} / leader {LEADER_PCT} %, danger x{DANGER_PCT} %, "
          f"hopeless {HOPELESS_PCT} % (low value < {LOWVAL_PCT} %), (b) accept >= {ACCEPT_PCT} % of clean")
    if not a.apply:
        print("dry run - nothing written (use --apply)")
        return
    if applied:
        print("already applied - rewriting caves in place (hooks unchanged)")
    elif not vanilla:
        sys.exit("hook-site bytes are neither vanilla nor ours - refusing")
    if not applied and not zone_zero:
        sys.exit("cave zone not empty - refusing")
    if not os.path.exists(bak):
        shutil.copy2(dll, bak)
        print(f"  backup -> {bak}")
    for va, blob, name in caves:
        o = va2off(data, va)
        data[o:o + len(blob)] = blob
    for name, va, orig, resume in HOOKS:
        o = va2off(data, va)
        data[o:o + len(orig)] = jmp_bytes(va, tgt[name], len(orig))
    open(dll, "wb").write(data)
    print("applied.")


if __name__ == "__main__":
    main()
