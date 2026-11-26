#!/usr/bin/env python3
r"""
Evoker / Conjurer / Enchanter / Ritualist as three-level abilities, part 1: registration + casting cost
(AoWEPACK.dll, 2026-09-21).  Parts 2/3 (research cost, upkeep) are separate scripts.

Design (user spec 2026-09-21):
  level I   -> research cost of the ability's spell class -30 %          (patch_caster_research_v1)
  level II  -> casting cost -30 %                                        (this script)
  level III -> Evoker: casting cost -50 % total; others: upkeep -30 %    (this script / patch_caster_upkeep_v1)
Rounding: "nearest, halves down" = new = (cost*pct + 4) div 10 (pct 7 or 5); Evoker additionally guarantees a
discount of at least 1 (user: "minimum discount of 1"); Conjurer/Enchanter/Ritualist II are plain nearest
(a 1-cost spell stays 1, like the old formula).  Examples (30 %): 5->3, 6->4, 10->7, 2->1, 1->1 (Evoker 1->0).

Vanilla/mod state (memory caster-cost-abilities, aowx-caster-cost-ritualist): ids 0xAC-0xAF are built by
cave_reg @0x55814FC0 (splice 0x557BCF04) as flat TEnhancementAbility via CreateEnhancementAbility 0x5576601C
(eax=id, edx=AnsiString name, cx=unit mask 0x3FF); THero.CastingMana entry 0x557894EC jumps to cave_cost
@0x55814F00 which classifies the spell by VMT slot deltas and applies cost - (cost+1) div 3 when the
hero's GetAbilityEnabled (VMT+0x148) says so.

This patch:
  A. cave_mkml @0x55816400: same contract as CreateEnhancementAbility but builds a TMultiLevelAbility
     (classref [0x5571DF90] via PIC delta, TMultiLevelAbility.Create 0x55765168, mask -> [+0x20], id -> [+0xC],
     name -> [+8] via _LStrAsg 0x55701150, cap [+0x28] = 3, level costs via TIntegerList.Put 0x55702EB4 on
     [+0x2C] = COST_PER_LEVEL each).  The four `call 0x5576601C` inside cave_reg are retargeted to it; the
     in-cave name strings (0x5581505E Evoker / 0x5581506D Conjurer / 0x5581507E Enchanter / 0x55815090
     Ritualist) are reused.  Plain ML instances get "Name I/II/III" from the existing cave_lsnames and the
     hero level-up offers levels via TMultiLevelAbility.CanExpand/ExpandCost (chained through cave_canexp).
  B. cave_cost2 @0x55816480: THero.CastingMana entry re-pointed here.  Same prologue/classification as
     cave_cost, then level = THero.GetAbilityLevel 0x5578831C (eax=hero, edx=id; item-aware) and the level
     rules above; continues at 0x557894F3 (vanilla off-sphere x2 still applies afterwards).  cave_cost stays
     in place, dead.
Backup AoWEPACK.dll.bak_casterlevels (in <game>\backup\).  Dry-run default; --apply; --revert; --dis.
"""
import argparse, os, shutil, struct, sys
from bakpath import game_dir, game_file, bak_path
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

DEFAULT_DLL = game_file(r"AoWEPACK.dll")
BAK = ".bak_casterlevels"
BASE = 0x55700000
COST_PER_LEVEL = 15
MAX_LEVEL = 3
EVOKER, CONJURER, ENCHANTER, RITUALIST = 0xAC, 0xAD, 0xAE, 0xAF

ML_CLASSREF = 0x5571DF90       # dword -> TMultiLevelAbility VMT (relocated at load; read through delta)
ML_CREATE = 0x55765168
LSTRASG = 0x55701150
INTLIST_PUT = 0x55702EB4       # thunk TIntegerList.Put(eax=list, edx=idx, ecx=val)
GET_ABILITY_LEVEL = 0x5578831C # THero.GetAbilityLevel(eax=hero, edx=id) -> eax
OLD_CREATE_ENH = 0x5576601C
REG_CALLS = [0x55814FDB, 0x55814FFF, 0x55815023, 0x55815047]   # the four `call CreateEnhancementAbility` in cave_reg
HOOK_VA = 0x557894EC           # THero.CastingMana entry: e9 <cave_cost> 90 90
OLD_COST_CAVE = 0x55814F00
RESUME = 0x557894F3
CAVE_MKML, CAVE_COST2, CAVE_END = 0x55816400, 0x55816480, 0x55816580
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, addr):
    enc, _ = ks.asm(src, addr)
    return bytes(enc)


def cave_mkml(va):
    pre = """
        push ebx
        push esi
        push edi
        push ecx
        mov esi, eax
        mov edi, edx
    """
    body = f"""
        mov eax, [ebx+{ML_CLASSREF:#x}]
        mov dl, 1
        xor ecx, ecx
        call {ML_CREATE:#x}
        mov ebx, eax
        pop ecx
        mov word ptr [ebx+0x20], cx
        mov [ebx+0xC], esi
        lea eax, [ebx+8]
        mov edx, edi
        call {LSTRASG:#x}
        mov dword ptr [ebx+0x28], {MAX_LEVEL}
    """
    for lvl in range(1, MAX_LEVEL + 1):
        body += f"""
        mov eax, [ebx+0x2C]
        mov edx, {lvl}
        mov ecx, {COST_PER_LEVEL}
        call {INTLIST_PUT:#x}
        """
    body += """
        mov eax, ebx
        pop edi
        pop esi
        pop ebx
        ret
    """
    p = asm(pre, va)
    call_at = va + len(p); nxt = call_at + 5
    p += asm(f"call {nxt:#x}", call_at)
    p += asm(f"pop ebx\nsub ebx, {nxt:#x}\n" + body, nxt)
    return p


def cave_cost2(va):
    return asm(f"""
        push ebx
        push esi
        push edi
        mov esi, edx
        mov ebx, [esi+0x14]
        test eax, eax
        jz c_done
        mov ecx, [eax]
        cmp [ecx-0x40], ecx
        jne c_done
        mov ecx, [esi]
        mov edx, [ecx+0x6C]
        sub edx, [ecx+0x18]
        cmp edx, 0x6B27C
        je c_conj
        cmp edx, 0x1FF4
        je c_ench
        cmp edx, 0x120
        jne c_rit
        mov edx, [ecx+0x80]
        sub edx, [ecx+0x18]
        cmp edx, 0x7E034
        jne c_done
        mov edi, {EVOKER:#x}
        jmp c_lvl
    c_conj:
        mov edi, {CONJURER:#x}
        jmp c_lvl
    c_ench:
        mov edi, {ENCHANTER:#x}
        jmp c_lvl
    c_rit:
        mov edi, {RITUALIST:#x}
    c_lvl:
        mov edx, edi
        call {GET_ABILITY_LEVEL:#x}
        cmp eax, 2
        jl c_done
        mov ecx, 7
        cmp edi, {EVOKER:#x}
        jne c_calc
        cmp eax, 3
        jl c_calc
        mov ecx, 5
    c_calc:
        mov eax, ebx
        imul eax, ecx
        add eax, 4
        xor edx, edx
        mov ecx, 10
        div ecx
        cmp eax, ebx
        jne c_set
        cmp edi, {EVOKER:#x}
        jne c_set
        test eax, eax
        jz c_set
        dec eax
    c_set:
        mov ebx, eax
    c_done:
        pop edi
        jmp {RESUME:#x}
    """, va)


def build():
    a = cave_mkml(CAVE_MKML); assert CAVE_MKML + len(a) <= CAVE_COST2, hex(CAVE_MKML + len(a))
    b = cave_cost2(CAVE_COST2); assert CAVE_COST2 + len(b) <= CAVE_END, hex(CAVE_COST2 + len(b))
    return [(CAVE_MKML, a, "mkml"), (CAVE_COST2, b, "cost2")]


def va2off(pe_bytes, va):
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


def reloc_hits(pe_bytes, ranges):
    e_lfanew = struct.unpack_from("<I", pe_bytes, 0x3C)[0]
    dd_rva, dd_sz = struct.unpack_from("<II", pe_bytes, e_lfanew + 24 + 0x88)
    if not dd_sz:
        return []
    off = va2off(pe_bytes, BASE + dd_rva); end = off + dd_sz; hits = []
    while off + 8 <= end:
        page, bsz = struct.unpack_from("<II", pe_bytes, off)
        if bsz < 8:
            break
        for i in range((bsz - 8) // 2):
            e = struct.unpack_from("<H", pe_bytes, off + 8 + 2 * i)[0]
            if e >> 12:
                va = BASE + page + (e & 0xFFF)
                if any(lo <= va < hi for lo, hi in ranges):
                    hits.append(va)
        off += bsz
    return hits


def callop(src, dst):
    return b"\xe8" + struct.pack("<i", dst - (src + 5))


def jmpop(src, dst):
    return b"\xe9" + struct.pack("<i", dst - (src + 5))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dll", nargs="?", default=DEFAULT_DLL)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    dll = a.dll
    bak = bak_path(dll, BAK, create=a.apply)
    caves = build()
    if a.dis:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
        md = Cs(CS_ARCH_X86, CS_MODE_32)
        for va, blob, name in caves:
            print(f"\n; ---- {name} @{va:#x} ({len(blob)} B) ----")
            for ins in md.disasm(blob, va):
                print(f"{ins.address:08X}  {ins.mnemonic:<7} {ins.op_str}")
    if a.revert:
        if not os.path.exists(bak):
            sys.exit(f"no backup {bak}")
        shutil.copy2(bak, dll); print(f"reverted {dll} from {bak}"); return
    data = bytearray(open(dll, "rb").read())
    ho = va2off(data, HOOK_VA); cur = bytes(data[ho:ho + 7])
    hook_tgt = HOOK_VA + 5 + struct.unpack_from("<i", cur, 1)[0] if cur[0] == 0xE9 else None
    hook_state = "vanilla-mod (cave_cost)" if hook_tgt == OLD_COST_CAVE else "ALREADY PATCHED" if hook_tgt == CAVE_COST2 else f"UNKNOWN {cur.hex()}"
    reg_states = []
    for site in REG_CALLS:
        o = va2off(data, site); c = bytes(data[o:o + 5])
        tgt = site + 5 + struct.unpack_from("<i", c, 1)[0] if c[0] == 0xE8 else None
        reg_states.append("enh" if tgt == OLD_CREATE_ENH else "ml" if tgt == CAVE_MKML else f"UNKNOWN {c.hex()}")
    print(f"target: {dll}\n  CastingMana hook 0x{HOOK_VA:x}: {hook_state}\n  cave_reg create calls: {reg_states}")
    for va, blob, name in caves:
        print(f"  cave {name:6} {va:#x}..{va + len(blob):#x} ({len(blob)} B)")
    z0, z1 = va2off(data, CAVE_MKML), va2off(data, CAVE_END)
    zone_zero = all(v == 0 for v in data[z0:z1])
    rl = reloc_hits(data, [(HOOK_VA, HOOK_VA + 5), (CAVE_MKML, CAVE_END)] + [(s, s + 5) for s in REG_CALLS])
    print(f"  cave zone zero: {zone_zero}; relocs: {[hex(v) for v in rl] or 'none'}; cost/level {COST_PER_LEVEL}, cap {MAX_LEVEL}")
    if not a.apply:
        print("dry run - nothing written (use --apply)"); return
    if rl or "UNKNOWN" in hook_state or any(s.startswith("UNKNOWN") for s in reg_states):
        sys.exit("refusing: relocs or unexpected bytes")
    applied = hook_state == "ALREADY PATCHED"
    if not applied and not zone_zero:
        sys.exit("cave zone not empty - refusing")
    if not os.path.exists(bak):
        shutil.copy2(dll, bak); print(f"  backup -> {bak}")
    for va, blob, name in caves:
        o = va2off(data, va); data[o:o + len(blob)] = blob
    data[ho:ho + 5] = jmpop(HOOK_VA, CAVE_COST2)
    for site in REG_CALLS:
        o = va2off(data, site); data[o:o + 5] = callop(site, CAVE_MKML)
    with open(dll, "r+b") as f:
        f.seek(0); f.write(data)
    print("applied." if not applied else "re-applied (caves rewritten).")


if __name__ == "__main__":
    main()
