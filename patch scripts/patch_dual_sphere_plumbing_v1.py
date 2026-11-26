#!/usr/bin/env python3
r"""
Dual-sphere plumbing in AoWEPACK.dll (step 2 of the dual-sphere spell project, 2026-10-04).

Sphere ids 9..22 become the 14 sphere PAIRS (every pair except Life/Death; see PAIRS).  A spell whose sphere
byte (spell+0x20, Spells.pfs tag 0x10) is one of them then behaves like a normal sphere everywhere the engine
asks "how many picks does the wizard have in this sphere?" and "is the next tier unlocked?", and shows a
"Life/Earth"-style name wherever the exe prints a sphere name.  Nothing in AoWx.exe is touched.

Three hooks + one data table, all position-independent (rel32 + call/pop load delta):

  H_PICKS  TLeader.GetSpherePicks @0x5578B17C (eax=leader, dl=sphere -> al): for dl in 9..22 return
           picks(A) + picks(B) - 1, or 0 if either is 0 (user rule 2026-10-12: 1+1 -> 1, 2+1 -> 2, 2+2 -> 3, 3+2 -> 4;
           the 2026-10-03 rule was the plain sum).
           Every consumer goes through this one function: ValidResearchSpell (tier <= picks), NewTurn day-1
           free spells, campaign setup; the node-income callers only ever pass ids <= 6.
  H_LADDER TPlayerMagicControl.ValidResearchSpell @0x5577D09C (`cmp dword [esp+eax*4],2 / jl`): the per-
           sphere "2 researched spells of tier N unlock tier N+1" ladder needs only 1 for a pair sphere
           (one spell per tier is the plan).  [esp] = the candidate spell, eax = tier index.
  H_INIT   the last still-direct `call RegisterSpell` in RegisterGlobalEnchantmentSpells @0x557F3AEE
           (package init, after AoWE's resourcestrings are loaded): replicates the call, then builds the
           23-entry sphere-name table NEWTAB in DATA slack: entries 0..8 copied (@LStrAsg) from the vanilla
           `AoWE.TMagicSphereRStr` array (0x558E8118: Cosmos..Water, Secret, None), entries 9..22 =
           name(A) + "/" + name(B) via @LStrAsg/@LStrCat.  The export RVA of TMagicSphereRStr is repointed
           to NEWTAB, so AoWx.exe's IAT slot 0x45E034 (6 display sites, e.g. the spellbook's "{Sphere} {tier}"
           label @0x42E932) and the editor see the extended table by name resolution.  The dll's own
           Finalization still finalizes the old array (harmless).
  Names are built from the raw resourcestrings; the exe translates at display, so a non-English install
  shows "Fire/Water" unless Dict\Release.mld gets rows for the 14 composites (step 3 content).

Addresses: caves 0x55861000.. (CODE zero tail, last patched byte in the live 410 dll is 0x5586007D),
NEWTAB 0x558E9B00 (DATA file-backed zero slack 0x558E9A5C..0x558E9C00, writable at runtime).
Backup <game>\backup\AoWEPACK.dll.bak_dualsphere.  Surgical --revert.  Dry-run default; --apply; --dis.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_dir, game_file

DEFAULT_DLL = game_file("AoWEPACK.dll")   # 2026-10-11: de-baked
BAK_SUFFIX = ".bak_dualsphere"
BASE = 0x55700000
CODE_V2F = 0x55700C00            # CODE: VA 0x55701000 -> file 0x400
DATA_V2F = 0x55700000 + 0x1E8000 - 0x1E6E00   # DATA: VA 0x558E8000 -> file 0x1E6E00

# ---- sphere pairs: id -> (A, B); 1 Life 2 Death 3 Earth 4 Air 5 Fire 6 Water -------------------
PAIRS = {
    9: (1, 3), 10: (1, 4), 11: (1, 5), 12: (1, 6),          # Life/Earth, Life/Air, Life/Fire, Life/Water
    13: (2, 3), 14: (2, 4), 15: (2, 5), 16: (2, 6),         # Death/Earth, Death/Air, Death/Fire, Death/Water
    17: (3, 4), 18: (3, 5), 19: (3, 6),                     # Earth/Air, Earth/Fire, Earth/Water
    20: (4, 5), 21: (4, 6),                                 # Air/Fire, Air/Water
    22: (5, 6),                                             # Fire/Water
}
FIRST_PAIR, N_PAIRS = 9, len(PAIRS)
N_VANILLA = 9                     # TMagicSphereRStr entries 0..8
N_TOTAL = FIRST_PAIR + N_PAIRS    # 23

# ---- engine facts ----------------------------------------------------------------------------------
GETSPHEREPICKS = 0x5578B17C
REGISTERSPELL = 0x55779B40
LSTRASG, LSTRCAT = 0x55701150, 0x55701188           # System.@LStrAsg(eax=@dest, edx=src) / @LStrCat
OLDTAB = 0x558E8118                                  # AoWE.TMagicSphereRStr, 9 AnsiStrings
NEWTAB = 0x558E9B00                                  # DATA slack, N_TOTAL dwords
EXPORT_NAME = b"AoWE.TMagicSphereRStr@D4FDF8A3"

H_PICKS = (0x5578B17C, bytes.fromhex("53568bf084d2"), 0x5578B182)          # push ebx/push esi/mov esi,eax/test dl,dl ; resume at je
H_LADDER = (0x5577D09C, bytes.fromhex("833c84027c05"), None)               # cmp [esp+eax*4],2 / jl 0x5577D0A7
LADDER_FAIL, LADDER_CONT = 0x5577D0A7, 0x5577D0A2
H_INIT = (0x557F3AEE, bytes.fromhex("e84d60f8ff"), 0x557F3AF3)             # call RegisterSpell
# TGlobalMagicControl.GetSphereManaDoubled(eax=ctrl, dl=sphere) -> al: `and edx,7f / cmp [eax+edx*4+18h],0 / setnz al
# / ret` indexes the per-sphere "mana doubled" counters (global enchantments Inc/Dec them for spheres 2/3/5) by the
# raw sphere id -> a pair id 9..22 reads past the 9-entry table into other fields = always "doubled" (THero.CastingMana
# charged every dual-sphere cast double, found 2026-10-07).  Cave: pair -> doubled(A) or doubled(B).
H_DOUBLE = (0x5577E230, bytes.fromhex("83e27f837c9018000f95c0c3"), None)

ZONE, ZONE_END = 0x55861000, 0x55861200      # 0x55861200.. belongs to patch_dual_sphere_spells_v1.py - never clear past it

ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, addr):
    enc, _ = ks.asm(src, addr)
    return bytes(enc)


def asm_pic(va, pre, body):
    """pre ; call next ; next: pop ebx ; sub ebx,next ; body   -> ebx = load delta (PIC)."""
    p = asm(pre, va) if pre.strip() else b""
    call_at = va + len(p)
    nxt = call_at + 5
    p += asm("call %#x" % nxt, call_at)
    p += asm("pop ebx\nsub ebx, %#x\n" % nxt + body, nxt)
    return p


def build_zone():
    """Returns (zone bytes, {name: va})."""
    out = bytearray()
    where = {}

    def place(name, blob, align=16):
        nonlocal out
        while len(out) % align:
            out.append(0)
        where[name] = ZONE + len(out)
        out += blob

    # data: pair table (A,B bytes, ids 9..22 in order) and the "/" literal (Delphi layout: refcnt -1, len, chars, NUL)
    pairs = bytes(b for sid in range(FIRST_PAIR, N_TOTAL) for b in PAIRS[sid])
    place("PAIRS", pairs, 4)
    place("SLASH", struct.pack("<ii", -1, 1) + b"/\0\0\0", 4)

    # H_PICKS cave: `push ebx / call next` = 6 bytes, so next = va+6 (single assembly, labels shared)
    picks_va = ZONE + ((len(out) + 15) & ~15)
    picks = asm("""
        push ebx
        call %#x
        pop ebx
        sub ebx, %#x
        cmp dl, %d
        jb replay
        cmp dl, %d
        jae replay
        push esi
        push edi
        mov esi, eax
        movzx edi, dl
        lea ecx, [ebx + edi*2 + %#x]
        mov dl, [ecx]
        mov eax, esi
        push ecx
        call %#x
        pop ecx
        movzx edi, al
        mov dl, [ecx+1]
        mov eax, esi
        call %#x
        movzx eax, al
        test edi, edi
        jz zero
        test eax, eax
        jz zero
        add eax, edi
        dec eax
        jmp done
    zero:
        xor eax, eax
    done:
        pop edi
        pop esi
        pop ebx
        ret
    replay:
        pop ebx
        push ebx
        push esi
        mov esi, eax
        test dl, dl
        jmp %#x
    """ % (picks_va + 6, picks_va + 6, FIRST_PAIR, N_TOTAL,
           where["PAIRS"] - 2 * FIRST_PAIR, GETSPHEREPICKS, GETSPHEREPICKS, H_PICKS[2]), picks_va)
    place("PICKS", picks)
    assert where["PICKS"] == picks_va

    # H_LADDER cave (no data refs -> plain)
    ladder_va = ZONE + ((len(out) + 15) & ~15)
    ladder = asm("""
        mov edx, [esp]
        cmp byte ptr [edx+0x20], %d
        jb vanilla
        cmp dword ptr [esp+eax*4], 1
        jl %#x
        jmp %#x
    vanilla:
        cmp dword ptr [esp+eax*4], 2
        jl %#x
        jmp %#x
    """ % (FIRST_PAIR, LADDER_FAIL, LADDER_CONT, LADDER_FAIL, LADDER_CONT), ladder_va)
    place("LADDER", ladder)
    assert where["LADDER"] == ladder_va

    # H_INIT cave: replicate RegisterSpell, then build NEWTAB
    init_va = ZONE + ((len(out) + 15) & ~15)      # call(5)+push ebx/esi/edi(3)+call next(5) -> next = va+13
    init = asm("""
        call %#x
        push ebx
        push esi
        push edi
        call %#x
        pop ebx
        sub ebx, %#x
        lea esi, [ebx + %#x]
        lea edi, [ebx + %#x]
        push %d
    copy:
        mov eax, edi
        mov edx, [esi]
        call %#x
        add esi, 4
        add edi, 4
        dec dword ptr [esp]
        jnz copy
        pop eax
        lea esi, [ebx + %#x]
        push %d
    pair:
        movzx eax, byte ptr [esi]
        lea edx, [ebx + %#x]
        mov edx, [edx + eax*4]
        mov eax, edi
        call %#x
        mov eax, edi
        lea edx, [ebx + %#x]
        call %#x
        movzx eax, byte ptr [esi+1]
        lea edx, [ebx + %#x]
        mov edx, [edx + eax*4]
        mov eax, edi
        call %#x
        add esi, 2
        add edi, 4
        dec dword ptr [esp]
        jnz pair
        pop eax
        pop edi
        pop esi
        pop ebx
        ret
    """ % (REGISTERSPELL, init_va + 13, init_va + 13,
           OLDTAB, NEWTAB, N_VANILLA, LSTRASG,
           where["PAIRS"], N_PAIRS,
           OLDTAB, LSTRASG, where["SLASH"] + 8, LSTRCAT, OLDTAB, LSTRCAT), init_va)
    place("INIT", init)
    assert where["INIT"] == init_va

    # H_DOUBLE cave: and(3) cmp(3) jb(2) cmp(3) jae(2) push ebx(1) = 14 -> call at va+14, next = va+19
    dbl_va = ZONE + ((len(out) + 15) & ~15)
    dbl = asm("""
        and edx, 0x7f
        cmp edx, %d
        jb plain
        cmp edx, %d
        jae plain
        push ebx
        call %#x
        pop ebx
        sub ebx, %#x
        push ecx
        lea ecx, [ebx + edx*2 + %#x]
        movzx edx, byte ptr [ecx]
        cmp dword ptr [eax + edx*4 + 0x18], 0
        jnz yes
        movzx edx, byte ptr [ecx+1]
        cmp dword ptr [eax + edx*4 + 0x18], 0
        jnz yes
        xor eax, eax
        jmp out
    yes:
        mov al, 1
    out:
        pop ecx
        pop ebx
        ret
    plain:
        cmp dword ptr [eax + edx*4 + 0x18], 0
        setnz al
        ret
    """ % (FIRST_PAIR, N_TOTAL, dbl_va + 19, dbl_va + 19, where["PAIRS"] - 2 * FIRST_PAIR), dbl_va)
    assert dbl[19:20] == b"\x5b", "DOUBLE delta anchor misplaced"
    place("DOUBLE", dbl)
    assert where["DOUBLE"] == dbl_va
    assert ZONE + len(out) <= ZONE_END, "zone overflow"
    return bytes(out), where


def hook(site, target, kind):
    va, orig, _ = site
    if kind == "jmp":
        b = b"\xe9" + struct.pack("<i", target - (va + 5))
    else:
        b = b"\xe8" + struct.pack("<i", target - (va + 5))
    return b + b"\x90" * (len(orig) - 5)


def sections(d):
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, pe + 6)[0]
    opt = struct.unpack_from("<H", d, pe + 20)[0]
    out = {}
    for k in range(nsec):
        s = pe + 24 + opt + 40 * k
        out[d[s:s + 8].rstrip(b"\0").decode()] = struct.unpack_from("<IIII", d, s + 8)   # vs, va, rs, ro
    return out


def rva2file(secs, rva):
    for vs, va, rs, ro in secs.values():
        if va <= rva < va + max(vs, rs):
            return ro + (rva - va)
    raise ValueError("rva %#x" % rva)


def reloc_set(d, secs):
    vs, va, rs, ro = secs[".reloc"]
    p, out = ro, set()
    while p < ro + vs:
        page, size = struct.unpack_from("<II", d, p)
        if size < 8:
            break
        for q in range(p + 8, p + size, 2):
            e = struct.unpack_from("<H", d, q)[0]
            if e >> 12 == 3:
                out.add(BASE + page + (e & 0xFFF))
        p += size
    return out


def export_entry(d, secs):
    vs, va, rs, ro = secs[".edata"]
    nnames = struct.unpack_from("<I", d, ro + 24)[0]
    addr_rva, names_rva, ord_rva = struct.unpack_from("<III", d, ro + 28)
    for i in range(nnames):
        nrva = struct.unpack_from("<I", d, rva2file(secs, names_rva) + 4 * i)[0]
        noff = rva2file(secs, nrva)
        if d[noff:d.find(b"\0", noff)] == EXPORT_NAME:
            o = struct.unpack_from("<H", d, rva2file(secs, ord_rva) + 2 * i)[0]
            return rva2file(secs, addr_rva) + 4 * o
    raise ValueError("export not found")


def write_inplace(path, data):
    with open(path, "r+b") as f:
        f.seek(0); f.write(data); f.truncate(len(data))


def dis(blob, base, where):
    try:
        import capstone
    except ImportError:
        return
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    names = {v: k for k, v in where.items()}
    for name in ("PICKS", "LADDER", "INIT", "DOUBLE"):
        lo = where[name]
        hi = min([v for v in where.values() if v > lo] + [base + len(blob)])
        print("--- %s @%#x (%d B)" % (name, lo, hi - lo))
        for i in md.disasm(blob[lo - base:hi - base], lo):
            print("   %08X  %-18s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dll", default=DEFAULT_DLL)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    dll = a.dll
    d = open(dll, "rb").read()
    secs = sections(d)
    relocs = reloc_set(d, secs)
    exp_off = export_entry(d, secs)
    zone, where = build_zone()
    hooks = [(H_PICKS, hook(H_PICKS, where["PICKS"], "jmp")),
             (H_LADDER, hook(H_LADDER, where["LADDER"], "jmp")),
             (H_INIT, hook(H_INIT, where["INIT"], "call")),
             (H_DOUBLE, hook(H_DOUBLE, where["DOUBLE"], "jmp"))]
    if a.dis:
        dis(zone, ZONE, where)

    # pre-state (per site: vanilla / ours = a hook into our zone from an earlier build / OTHER)
    live_sites = [bytes(d[s[0] - CODE_V2F:s[0] - CODE_V2F + len(s[1])]) for s, _ in hooks]
    states = []
    for (s, h), l in zip(hooks, live_sites):
        if l == s[1]: states.append("vanilla")
        elif l[0] in (0xE8, 0xE9) and ZONE <= s[0] + 5 + struct.unpack_from("<i", l, 1)[0] < ZONE_END and all(b == 0x90 for b in l[5:]): states.append("ours")
        else: states.append("OTHER")
    vanilla = all(st == "vanilla" for st in states)
    applied = all(l == h for (s, h), l in zip(hooks, live_sites))
    zone_live = d[ZONE - CODE_V2F:ZONE_END - CODE_V2F]
    exp_rva = struct.unpack_from("<I", d, exp_off)[0]
    tab_live = d[NEWTAB - DATA_V2F:NEWTAB - DATA_V2F + 4 * N_TOTAL]
    bad = [r for r in relocs if ZONE <= r < ZONE_END or NEWTAB <= r < NEWTAB + 4 * N_TOTAL
           or any(s[0] <= r < s[0] + len(s[1]) for s, _ in hooks)]
    zstate = "zero" if not any(zone_live) else "ours" if zone_live[:len(zone)] == zone and not any(zone_live[len(zone):]) else "DIFFERS"
    print("sites: %s | zone: %s | export rva: %#x | NEWTAB file bytes zero: %s | relocs in ranges: %s"
          % (states, zstate, exp_rva, not any(tab_live), ["%#x" % r for r in bad] or "none"))
    if bad:
        print("ABORT: reloc entries inside patched ranges"); return 1
    if "OTHER" in states:
        for (s, _), l in zip(hooks, live_sites):
            print("   site %#x: %s (vanilla %s)" % (s[0], l.hex(), s[1].hex()))
        print("ABORT: hook sites not in an expected state"); return 1

    if a.revert:
        if vanilla:
            print("not applied - nothing to revert"); return 1
        out = bytearray(d)
        for (s, _), st in zip(hooks, states):
            if st == "ours": out[s[0] - CODE_V2F:s[0] - CODE_V2F + len(s[1])] = s[1]
        out[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
        struct.pack_into("<I", out, exp_off, OLDTAB - BASE)
        write_inplace(dll, bytes(out)); print("reverted"); return 0

    if applied and zstate == "ours" and exp_rva == NEWTAB - BASE:
        print("already applied"); return 0
    if vanilla and (any(zone_live) or any(tab_live)):
        print("ABORT: zone or NEWTAB not zero on a vanilla dll"); return 1
    if vanilla and exp_rva != OLDTAB - BASE:
        print("ABORT: export rva %#x unexpected" % exp_rva); return 1
    if not vanilla:
        print("re-sync: %d site(s) already ours, zone %s -> rewriting the whole zone" % (states.count("ours"), zstate))

    out = bytearray(d)
    out[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
    out[ZONE - CODE_V2F:ZONE - CODE_V2F + len(zone)] = zone
    for s, h in hooks:
        out[s[0] - CODE_V2F:s[0] - CODE_V2F + len(s[1])] = h
    struct.pack_into("<I", out, exp_off, NEWTAB - BASE)
    print("zone %#x..%#x (%d B): PICKS %#x LADDER %#x INIT %#x DOUBLE %#x | export -> %#x | %d bytes change"
          % (ZONE, ZONE + len(zone), len(zone), where["PICKS"], where["LADDER"], where["INIT"], where["DOUBLE"], NEWTAB,
             sum(1 for x, y in zip(d, out) if x != y)))
    if not a.apply:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(dll, BAK_SUFFIX)
    if not os.path.exists(bak):
        shutil.copy2(dll, bak); print("backup ->", bak)
    write_inplace(dll, bytes(out))
    assert open(dll, "rb").read() == bytes(out)
    print("Written and verified:", dll)
    return 0


if __name__ == "__main__":
    sys.exit(main())
