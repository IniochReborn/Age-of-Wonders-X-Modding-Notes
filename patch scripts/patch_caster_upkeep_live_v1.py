#!/usr/bin/env python3
r"""
Caster upkeep follows the CURRENT abilities (AoWEPACK.dll, 2026-10-18).  Requires patch_caster_research_upkeep_v1.py.

User: "if the caster gains the ability (Conjurer / Enchanter / Ritualist III) after the spell is cast, the upkeep
doesn't update - it should; and if the unit loses the ability (e.g. via an item) the upkeep should update as well."

Before: patch_caster_research_upkeep_v1 discounted the upkeep ONCE, at creation (H3 TEnchantment.SetUpkeep, H4 summon
spawn, H5 TGlobalEnchantmentSpell.SetupEnchantment) using the caster's level at that moment, and the discounted value was
stored in the enchantment ([ench+0x10] / [gench+0x20], both saved).  The enchantment does not remember its caster
(TUnitEnchantment is 0x20 bytes, every field used), so a later ability change could never reach it.

Now: the enchantments store the RAW upkeep and every reader applies the discount LIVE from the owning player's roster:
  level = best level of the class ability among the player's heroes (THeroList [player+0x80], leader included);
  level >= 3 -> upkeep (v*7+4) div 10 with a minimum discount of 1 (same d30 as before).
  Unit enchantments (exact TUnitEnchantment, player [ench+0xC]): Summoned records ([+0x1C]=0x9B) -> Conjurer, else
  Enchanter.  Global enchantments of TGlobalEnchantmentSpell (player [gench+0x19]) -> Ritualist.  City enchantments,
  Smoke Cloud and Watcher keep raw (they never had the discount).
  The value is a pure function of saved game state -> MP/save deterministic, no new state.  Gaining/losing the ability
  (level-up, item, hero death/leaving) changes every reader at once: per-turn deduction (GetManaUpkeep 0x5577C964 via
  the turn step 0x5577CE2A), the out-of-mana dispel choice (ValidateEnchantmentsUpkeep), the AI budget/override, the
  summoned unit's mana upkeep, the magic window's enchantment list (exe, patch_caster_upkeep_live_exe_v1.py) and the
  spellbook upkeep line (h_upkeep, used by patch_spellbook_discounts_v1).
  Policy change (documented): "the caster" is now "the best caster on the owning player's roster" (the enchantment
  cannot know its caster) - the same rule research already uses (minus stacking).

Edits:
  C1..C3  patch_caster_research_upkeep_v1 creation caves: `cmp eax,3` -> `cmp eax,0x7F` at 0x55816748 (H3),
          0x55816790 (H4), 0x55816812 (H5) -> creation stores the raw upkeep.
  HU      h_upkeep 0x558168F0 entry (`push ebx/esi/edi; mov ebx,eax`, 5 B) -> jmp h_upkeep2 (roster rule).
  S1      0x5577C980 GetManaUpkeep sum       `call 0x5577C1CC ; add edi,[eax+0x10]`  -> call c_add_edi ; 3x nop
  S2      0x5577CA74 Validate (max search)   `call ... ; mov edi,[eax+0x10]`        -> call c_mov_edi
  S3      0x5577CA82 Validate (max search)   `call ... ; cmp edi,[eax+0x10]`        -> call c_cmp_edi (flags kept)
  S4      0x5577CAA3 Validate (removal)      `call ... ; mov eax,[eax+0x10]`        -> call c_get
  S5      0x5577D618 AIRequestOverrideUpkeep `call ... ; mov eax,[eax+0x10]`        -> call c_get
  S6      0x5577D6E4 AIOverrideUpkeep        `call ... ; mov ecx,[eax+0x10]`        -> call c_mov_ecx
  S7      0x5577FCB9 TAbstractUnit.GetManaUpkeep `mov eax,[eax+0x10] ; jmp 0x5577FCC4` -> jmp c_unit
  G1      12 VMT slots +0x50 (GetUpkeep 0x5577D9D0: TGlobalEnchantment + the 11 GlobalEnchantmentSpells classes) -> adj_g
          (slots carry a .reloc entry; the new value is an in-image VA so the loader fixup stays correct; runtime VMT
          clones of the dual-sphere pipeline copy the patched slot).
  G2      TFloodEnchantment.GetUpkeep 0x557F1AE6 `call 0x5577D9D0` -> call adj_g.
Caves: 0x5581E000.. (zone 0x5581E000-0x5581E800, zero + reloc-free verified; 0x5581F800 = hex-grid option cave).
Exported (fixed) for the exe patch: ADJ_U 0x5581E200 (eax=enchantment -> eax=live upkeep).
Old saves: an enchantment created while its caster had level III holds the already-discounted value and gets discounted
once more (e.g. 5 -> 3 -> 2) until it is recast.
LIFO: revert this BEFORE patch_caster_research_upkeep_v1 (it edits that script's caves) and before
patch_spellbook_discounts_v1 is irrelevant (the exe only calls h_upkeep).  Revert the exe companion first.
Backup AoWEPACK.dll.bak_upkeeplive (in <game>\backup\).  Dry-run default; --apply; --revert; --dis.
"""
import argparse, os, shutil, struct, sys
from bakpath import game_file, bak_path
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

DEFAULT_DLL = game_file(r"AoWEPACK.dll")
BAK = ".bak_upkeeplive"
BASE = 0x55700000
EVOKER, CONJURER, ENCHANTER, RITUALIST = 0xAC, 0xAD, 0xAE, 0xAF
G_ENGINE = 0x558FA040            # [.]+0x140 = player list
GET_PLAYER = 0x557544D0          # (eax=list, edx=idx) -> TPlayer
GET_HERO = 0x5578A208            # (eax=THeroList, edx=i) -> THero
GET_ABILITY_LEVEL = 0x5578831C   # (eax=hero, edx=ability id) -> level
LIST_GET = 0x5577C1CC            # TEnchantmentList.GetEnchantments(eax=list, edx=i)
TUNITENCH_CLS = 0x55722198
GEN_GETUPKEEP = 0x5577D9D0
ZONE, ZONE_END = 0x5581E000, 0x5581E800
ADJ_U_EXPECT = 0x5581E200
VMT_SLOTS = [0x5570B3E8, 0x557EDBAC, 0x557EDE0C, 0x557EE05C, 0x557EE2B8, 0x557EE4F8, 0x557EE740,
             0x557EEC9C, 0x557EEEF4, 0x557EF150, 0x557EF3A8, 0x557EF604]   # TGlobalEnchantment + Roads/Air/Water/Hatred/Harmony/PowerLeak/Life/Death/Fire/Earth Mastery/SpellWard
FLOOD_CALL = 0x557F1AE6
CREATE_IMMS = [0x5581674A, 0x55816792, 0x55816814]     # imm8 of `cmp eax,3` in H3/H4/H5 caves
HU = 0x558168F0
HU_ORIG = bytes.fromhex("53565789c3")
SITES = {   # name: (va, original bytes)
    "S1": (0x5577C980, bytes.fromhex("e847f8ffff037810")),
    "S2": (0x5577CA74, bytes.fromhex("e853f7ffff8b7810")),
    "S3": (0x5577CA82, bytes.fromhex("e845f7ffff3b7810")),
    "S4": (0x5577CAA3, bytes.fromhex("e824f7ffff8b4010")),
    "S5": (0x5577D618, bytes.fromhex("e8afebffff8b4010")),
    "S6": (0x5577D6E4, bytes.fromhex("e8e3eaffff8b4810")),
    "S7": (0x5577FCB9, bytes.fromhex("8b4010eb06")),
}
S7_RESUME = 0x5577FCC4
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, addr):
    enc, _ = ks.asm(src, addr)
    return bytes(enc)


class Layout:
    def __init__(self, base): self.cur = base; self.caves = []; self.sym = {}
    def add(self, name, fn, at=None):
        if at is not None:
            assert at >= self.cur, (name, hex(at), hex(self.cur)); self.cur = at
        va = self.cur; blob = fn(va); self.caves.append((va, blob, name)); self.sym[name] = va
        self.cur = (va + len(blob) + 15) & ~15; return va


def build():
    L = Layout(ZONE)
    # d30: eax=value -> (7v+4) div 10, minimum discount 1 (1->0, 2->1); clobbers nothing else
    D30 = L.add("d30", lambda va: asm("""
        push ecx
        push edx
        mov ecx, eax
        imul eax, eax, 7
        add eax, 4
        xor edx, edx
        push ecx
        mov ecx, 10
        div ecx
        pop ecx
        cmp eax, ecx
        jne d_ret
        test eax, eax
        jz d_ret
        dec eax
    d_ret:
        pop edx
        pop ecx
        ret
    """, va))
    # best: eax=player index (signed), edx=ability id -> eax = best level among the player's heroes (0 if none)
    # PIC (engine global); preserves ebx/esi/edi/ebp; clobbers ecx/edx.
    def best(va):
        pre = asm("""
            push ebx
            push esi
            push edi
            push ebp
            mov esi, eax
            mov edi, edx
            xor ebp, ebp
        """, va)
        call_at = va + len(pre); nxt = call_at + 5
        return pre + asm(f"call {nxt:#x}", call_at) + asm(f"""
            pop ebx
            sub ebx, {nxt:#x}
            test esi, esi
            js b_done
            mov eax, [ebx+{G_ENGINE:#x}]
            test eax, eax
            jz b_done
            mov eax, [eax+0x140]
            test eax, eax
            jz b_done
            mov edx, esi
            call {GET_PLAYER:#x}
            test eax, eax
            jz b_done
            mov esi, [eax+0x80]
            test esi, esi
            jz b_done
            mov eax, esi
            mov edx, [eax]
            call [edx+0x54]
            mov ebx, eax
        b_loop:
            dec ebx
            js b_done
            mov edx, ebx
            mov eax, esi
            call {GET_HERO:#x}
            test eax, eax
            jz b_loop
            mov edx, edi
            call {GET_ABILITY_LEVEL:#x}
            cmp eax, ebp
            jle b_loop
            mov ebp, eax
            jmp b_loop
        b_done:
            mov eax, ebp
            pop ebp
            pop edi
            pop esi
            pop ebx
            ret
        """, nxt)
    # best: eax=player index (signed), edx=ability id -> eax = best level among the player's heroes (0 if none)
    # PIC (engine global); preserves ebx/esi/edi/ebp; clobbers ecx/edx.
    BEST = L.add("best", best)
    # disc: eax=raw, edx=player index, ecx=ability id -> eax = live upkeep
    DISC = L.add("disc", lambda va: asm(f"""
        push esi
        mov esi, eax
        test esi, esi
        jle x_raw
        mov eax, edx
        mov edx, ecx
        call {BEST:#x}
        cmp eax, 3
        jl x_raw
        mov eax, esi
        call {D30:#x}
        pop esi
        ret
    x_raw:
        mov eax, esi
        pop esi
        ret
    """, va))
    # adj_g: eax=TGlobalEnchantment -> eax = live upkeep (Ritualist, player [+0x19])  [VMT slot +0x50 replacement]
    ADJG = L.add("adj_g", lambda va: asm(f"""
        movsx edx, byte ptr [eax+0x19]
        mov eax, [eax+0x20]
        mov ecx, {RITUALIST:#x}
        jmp {DISC:#x}
    """, va))
    # h_upkeep2: eax=hero, edx=spell -> upkeep that hero's player would pay for the spell (spellbook line)
    HU2 = L.add("h_upkeep2", lambda va: asm(f"""
        push ebx
        mov ebx, eax
        mov eax, [edx+0x1C]
        mov ecx, [edx]
        push eax
        mov eax, [ecx+0x6C]
        sub eax, [ecx+0x18]
        cmp eax, 0x6B27C
        je k_conj
        cmp eax, 0x1FF4
        je k_ench
        cmp eax, 0x120
        jne k_rit
        jmp k_raw
    k_conj:
        mov ecx, {CONJURER:#x}
        jmp k_go
    k_ench:
        mov ecx, {ENCHANTER:#x}
        jmp k_go
    k_rit:
        mov ecx, {RITUALIST:#x}
    k_go:
        pop eax
        test ebx, ebx
        jz k_ret
        movsx edx, byte ptr [ebx+0x24]
        call {DISC:#x}
    k_ret:
        pop ebx
        ret
    k_raw:
        pop eax
        pop ebx
        ret
    """, va))
    # adj_u (EXPORTED, fixed VA): eax=enchantment -> eax = live upkeep; preserves ebx/esi/edi/ebp
    def adj_u(va):
        pre = asm("""
            push ebx
            mov ebx, eax
        """, va)
        call_at = va + len(pre); nxt = call_at + 5
        body = asm(f"call {nxt:#x}", call_at)
        body += asm(f"""
            pop ecx
            sub ecx, {nxt:#x}
            lea ecx, [ecx+{TUNITENCH_CLS:#x}]
            mov eax, [ebx+0x10]
            cmp [ebx], ecx
            jne u_ret
            movsx edx, byte ptr [ebx+0xC]
            mov ecx, {ENCHANTER:#x}
            cmp dword ptr [ebx+0x1C], 0x9B
            jne u_go
            mov ecx, {CONJURER:#x}
        u_go:
            call {DISC:#x}
        u_ret:
            pop ebx
            ret
        """, nxt)
        return pre + body
    ADJU = L.add("adj_u", adj_u, at=ADJ_U_EXPECT)
    assert ADJU == ADJ_U_EXPECT
    C_ADD = L.add("c_add_edi", lambda va: asm(f"call {LIST_GET:#x}\ncall {ADJU:#x}\nadd edi, eax\nret", va))
    C_MOVEDI = L.add("c_mov_edi", lambda va: asm(f"call {LIST_GET:#x}\ncall {ADJU:#x}\nmov edi, eax\nret", va))
    C_CMP = L.add("c_cmp_edi", lambda va: asm(f"call {LIST_GET:#x}\ncall {ADJU:#x}\ncmp edi, eax\nret", va))
    C_GET = L.add("c_get", lambda va: asm(f"call {LIST_GET:#x}\ncall {ADJU:#x}\nret", va))
    C_ECX = L.add("c_mov_ecx", lambda va: asm(f"call {LIST_GET:#x}\ncall {ADJU:#x}\nmov ecx, eax\nret", va))
    C_UNIT = L.add("c_unit", lambda va: asm(f"call {ADJU:#x}\njmp {S7_RESUME:#x}", va))
    assert L.cur <= ZONE_END, hex(L.cur)
    cave_for = {"S1": C_ADD, "S2": C_MOVEDI, "S3": C_CMP, "S4": C_GET, "S5": C_GET, "S6": C_ECX}
    patches = []   # (va, orig, new, label)
    for k, (va, orig) in SITES.items():
        if k == "S7":
            new = asm(f"jmp {C_UNIT:#x}", va)
        else:
            new = asm(f"call {cave_for[k]:#x}", va) + b"\x90" * 3
        assert len(new) == len(orig), k
        patches.append((va, orig, new, k))
    patches.append((HU, HU_ORIG, asm(f"jmp {HU2:#x}", HU), "HU h_upkeep -> h_upkeep2"))
    for va in CREATE_IMMS:
        patches.append((va, b"\x03", b"\x7f", "creation cave level gate"))
    for va in VMT_SLOTS:
        patches.append((va, struct.pack("<I", GEN_GETUPKEEP), struct.pack("<I", ADJG), "VMT GetUpkeep slot"))
    patches.append((FLOOD_CALL, asm(f"call {GEN_GETUPKEEP:#x}", FLOOD_CALL), asm(f"call {ADJG:#x}", FLOOD_CALL), "Flood GetUpkeep call"))
    return L, patches


def sections(d):
    e = struct.unpack_from("<I", d, 0x3C)[0]; n = struct.unpack_from("<H", d, e + 6)[0]
    opt = struct.unpack_from("<H", d, e + 20)[0]; out = []
    for i in range(n):
        s = e + 24 + opt + 40 * i
        vs, va, rs, ra = struct.unpack_from("<IIII", d, s + 8); out.append((va, max(vs, rs), ra, rs))
    return out, e


def off(d, va):
    secs, _ = sections(d)
    for sva, size, ra, rs in secs:
        if sva <= va - BASE < sva + size:
            return ra + va - BASE - sva
    raise ValueError(hex(va))


def relocs(d):
    secs, e = sections(d)
    rva, size = struct.unpack_from("<II", d, e + 24 + 136)
    o = off(d, BASE + rva); end = o + size; out = set()
    while o < end:
        page, bs = struct.unpack_from("<II", d, o)
        if bs == 0: break
        for i in range((bs - 8) // 2):
            ent = struct.unpack_from("<H", d, o + 8 + 2 * i)[0]
            if ent >> 12: out.add(BASE + page + (ent & 0xFFF))
        o += bs
    return out


def state(d, L, patches):
    st = []
    for va, orig, new, lab in patches:
        cur = bytes(d[off(d, va):off(d, va) + len(orig)])
        st.append("new" if cur == new else ("orig" if cur == orig else "FOREIGN"))
    z0, z1 = off(d, ZONE), off(d, ZONE_END)
    zone_ours = all(bytes(d[off(d, va):off(d, va) + len(b)]) == b for va, b, _ in L.caves)
    zone_zero = all(v == 0 for v in d[z0:z1])
    return st, zone_ours, zone_zero


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("dll", nargs="?", default=DEFAULT_DLL)
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    L, patches = build()
    if a.dis:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
        md = Cs(CS_ARCH_X86, CS_MODE_32)
        for va, blob, name in L.caves:
            print(f"; {name} @{va:#x} ({len(blob)} B)")
            for i in md.disasm(blob, va): print(f"  {i.address:08X}  {i.mnemonic} {i.op_str}")
    d = bytearray(open(a.dll, "rb").read())
    st, zone_ours, zone_zero = state(d, L, patches)
    rl = relocs(d)
    site_relocs = [hex(r) for va, o, n, lab in patches if lab != "VMT GetUpkeep slot" for r in rl if va - 3 < r < va + len(o)]
    zone_relocs = [hex(r) for r in rl if ZONE <= r < ZONE_END]
    vmt_relocs_ok = all(va in rl for va in VMT_SLOTS)
    for (va, o, n, lab), s in zip(patches, st):
        print(f"  {va:#010x} {lab:<28} {s}")
    print(f"  zone {ZONE:#x}-{ZONE_END:#x}: {'ours' if zone_ours else ('zero' if zone_zero else 'FOREIGN')}; "
          f"cave end {L.cur:#x}; site relocs {site_relocs or 'none'}; zone relocs {zone_relocs or 'none'}; "
          f"VMT slot relocs present {vmt_relocs_ok}")
    assert not site_relocs and not zone_relocs and vmt_relocs_ok
    applied = all(s == "new" for s in st) and zone_ours
    vanilla = all(s == "orig" for s in st) and zone_zero
    if a.revert:
        if vanilla: print("not applied - nothing to revert"); return
        if not all(s in ("new", "orig") for s in st): sys.exit("FOREIGN bytes at a site - refusing")
        for va, o, n, lab in patches:
            p = off(d, va); d[p:p + len(o)] = o
        z0, z1 = off(d, ZONE), off(d, ZONE_END); d[z0:z1] = bytes(z1 - z0)
        with open(a.dll, "r+b") as f: f.seek(0); f.write(d)
        print("reverted (sites restored, zone zeroed)"); return
    if applied: print("already applied"); return
    if not vanilla: sys.exit("mixed / foreign state - refusing")
    if not a.apply: print("dry run OK - nothing written (use --apply)"); return
    bak = bak_path(a.dll, BAK)
    if not os.path.exists(bak): shutil.copyfile(a.dll, bak); print("backup ->", bak)
    for va, blob, name in L.caves:
        p = off(d, va); d[p:p + len(blob)] = blob
    for va, o, n, lab in patches:
        p = off(d, va); d[p:p + len(n)] = n
    with open(a.dll, "r+b") as f: f.seek(0); f.write(d)
    back = bytearray(open(a.dll, "rb").read())
    st2, ours2, _ = state(back, L, patches)
    assert all(s == "new" for s in st2) and ours2
    print("written and verified")


if __name__ == "__main__":
    main()
