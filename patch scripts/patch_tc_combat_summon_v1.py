#!/usr/bin/env python3
r"""AoWTCPCK.dll: SUMMON SPELLS CASTABLE IN TACTICAL COMBAT - tactical side (2026-10-24, user request).
Pairs with patch_combat_summon_ep_v1.py (AoWEPACK: book listing, CreateCA, the CA that creates unit + combat unit).

  * SpellTypes[id] := 0x27 (AnimateDead class) for the 23 summon spells: vanilla 20-31 + 78 and the pipeline summons
    222 303 332 334 343 347 351 362 364 381 (relocated table 0x43C000, 512 entries; all were 0 = not combat-castable).
    In TC code a summon = SpellTypes 0x27 AND GetSpell(id) category [spell+0x22] == 2 (stGlobal; vanilla 0x27 spells
    are stCombat).
  * IN: TTacticalCombatUnitHS.SelectSpell's `call` site 0x4233A2 (today -> Call of the Dead instant cave 0x442404),
    re-pointed to our cave: a summon is cast at once on the caster's own hex (TXYZList.Clear as the original call,
    AbRangedTC(hs, x, y) 0x423860, jmp 0x4233E0 = the vanilla instant tail - CotD's recipe); else -> 0x442404.
  * BC: TCAbRangedTE.Execute class-0x27 per-effect site 0x40BB26 (today `jmp 0x442010` = CotD) re-pointed: a summon fx
    at tick 0 runs the vanilla raise recipe (0x424058..0x424120) for a NEW unit: combat RNG seeded like Animate Dead
    ([[0x46DC08]] = TAoWHSMap.Random(0xFFFFFF)), CA = spell.CreateCA(caster, caster, push 1) (VMT+0x78 = TAnimateDead's
    via the AoWEPACK patch), TCombat.ExecuteCombatAction, release; the AoWEPACK cave leaves the new COID in [ca+0xD];
    the new combat unit is looked up (TCombatData GetCount/GetObjects); map object = TUnitHS.Create([0x412CC8] =
    TTacticalCombatUnitHS) + Initialize 0x420710 + SetDirection(caster facing [hs+0x14]); placement: the hex IN FRONT
    of the caster (the neighbour n = 1..6 whose AoWTC.GetMeleeDirIndex(cx, cx-nx, cy-ny) == the caster's facing), else
    the first valid hex of CenterHNtoHX rings 1..7 round the caster (TRndTacHsm.SetupUnit's tests: in level bounds,
    terrain byte [field+0x15] != 8, no unit HS 0x220104 on the field) -> THSMap.PlaceHX.  Every tick of a summon fx ->
    0x40CAF2 (no corpse messages).  Other fx -> 0x442010.
Runs inside the TE on every machine (MP-deterministic: synced combat RNG seed, no visual randomness).
PIC (TCPCK rebases): data via call/pop delta; calls rel32 inside the image / to import thunks.
Zone 0x45C000..0x45C800 'TSU1'.  LIFO: chained IN FRONT of Call of the Dead's IN + BC caves -> revert this first.
Backup <game>\backup\AoWTCPCK.dll.bak_combatsummon.  Dry run / --apply / --revert.
"""
import os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DLL = game_file("AoWTCPCK.dll")
V2F = 0x400C00
ZONE, ZONE_END = 0x45C000, 0x45C800
MAGIC = b"TSU1"
SPELLTYPES = 0x43C000
SUMMON_IDS = [20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 78, 222, 303, 332, 334, 343, 347, 351, 362, 364, 381]
CLASS = 0x27
IN_SITE, IN_PREV = 0x4233A2, 0x442404          # `call` site
BC_SITE, BC_PREV = 0x40BB26, 0x442010          # `jmp` site
U_ISSUM, U_IN, U_BC, U_SUM = 0x20, 0x80, 0xE0, 0x140

F = dict(spelltypes=SPELLTYPES, cls=CLASS, g_reg=0x46E8D0, g_hsmap=0x46E8D4, g_seed=0x46DC08, g_map=0x46C064,
         c_uhs=0x412CC8, getspell=0x4029B4, clear=0x402DDC, abranged=0x423860, in_tail=0x4233E0, in_prev=IN_PREV,
         bc_prev=BC_PREV, bc_done=0x40CAF2, rnd=0x40298C, execca=0x40259C, dcount=0x40262C, dobj=0x402634,
         uhs_create=0x4029C4, uhs_init=0x420710, setdir=0x402AF4, getlevel=0x401E64, getfield=0x401E54,
         c2hx=0x4022AC, meleedir=0x430C58, placehx=0x402264,
         issum=ZONE + U_ISSUM, summon=ZONE + U_SUM)


def pic(reg, at):
    r = {"eax": 0, "ecx": 1, "edx": 2, "ebx": 3, "esi": 6, "edi": 7}[reg]
    return b"\xe8\x00\x00\x00\x00" + bytes([0x58 + r, 0x81, 0xE8 + r]) + struct.pack("<I", at + 5)


# issum: eax = spell id -> eax = 1 if summon else 0.  Keeps every other register.
ISSUM = """
    cmp  eax, 0x1ff
    ja   no
    cmp  byte ptr [ecx + eax + {spelltypes:#x}], {cls:#x}
    jne  no
    mov  edx, eax
    mov  eax, dword ptr [ecx + {g_reg:#x}]
    mov  eax, dword ptr [eax]
    mov  eax, dword ptr [eax + 0x84]
    call {getspell:#x}
    test eax, eax
    jz   no
    cmp  byte ptr [eax + 0x22], 2
    jne  no
    mov  eax, 1
    jmp  out
no:
    xor  eax, eax
out:
    pop  edx
    pop  ecx
    ret
"""

IN = """
    push eax
    mov  eax, dword ptr [ebp - 8]
    call {issum:#x}
    test eax, eax
    pop  eax
    jz   notsum
    call {clear:#x}
    mov  eax, dword ptr [ebp - 4]
    mov  edx, dword ptr [eax]
    call dword ptr [edx + 0x78]
    movsx ecx, al
    push ecx
    mov  eax, dword ptr [ebp - 4]
    mov  edx, dword ptr [eax]
    call dword ptr [edx + 0x74]
    movsx edx, al
    pop  ecx
    mov  eax, dword ptr [ebp - 4]
    call {abranged:#x}
    add  esp, 4
    jmp  {in_tail:#x}
notsum:
    jmp  {in_prev:#x}
"""

BC = """
    push eax
    mov  eax, dword ptr [eax + 0x18]
    call {issum:#x}
    test eax, eax
    pop  eax
    jz   notsum
    cmp  dword ptr [eax + 0x10], 0
    jne  done
    call {summon:#x}
done:
    jmp  {bc_done:#x}
notsum:
    jmp  {bc_prev:#x}
"""

# summon: called from BC with the TE frame in ebp ([ebp-4] = TE).  Locals (own frame): -4 delta, -8 ca, -0xC data,
# -0x10 loop, -0x14 new cu, -0x18 hs, -0x1C caster hs, -0x20 dir, -0x24 cx, -0x28 cy, -0x2C level, -0x30 x, -0x34 y,
# -0x38 front n, -0x3C try n, -0x40 new id.
SUMMON = """
    pushad
    mov  esi, dword ptr [ebp - 4]
    push ebp
    mov  ebp, esp
    sub  esp, 0x48
    mov  dword ptr [ebp - 4], ecx
    mov  edi, dword ptr [esi + 0x10]
    test edi, edi
    jz   s_out
    mov  eax, dword ptr [ecx + {g_hsmap:#x}]
    mov  eax, dword ptr [eax]
    mov  edx, 0xffffff
    call {rnd:#x}
    mov  ecx, dword ptr [ebp - 4]
    mov  edx, dword ptr [ecx + {g_seed:#x}]
    mov  dword ptr [edx], eax
    mov  ecx, dword ptr [ebp - 4]
    mov  eax, dword ptr [ecx + {g_reg:#x}]
    mov  eax, dword ptr [eax]
    mov  eax, dword ptr [eax + 0x84]
    mov  edx, dword ptr [esi + 0x18]
    call {getspell:#x}
    test eax, eax
    jz   s_out
    push 1
    mov  edx, edi
    mov  ecx, edi
    mov  ebx, dword ptr [eax]
    call dword ptr [ebx + 0x78]
    mov  dword ptr [ebp - 8], eax
    test eax, eax
    jz   s_out
    mov  ecx, dword ptr [ebp - 4]
    mov  eax, dword ptr [ecx + {g_map:#x}]
    mov  eax, dword ptr [eax + 0xe4]
    mov  edx, dword ptr [ebp - 8]
    call {execca:#x}
    mov  eax, dword ptr [ebp - 8]
    movzx edx, byte ptr [eax + 0xd]
    mov  dword ptr [ebp - 0x40], edx
    mov  edx, dword ptr [eax]
    call dword ptr [edx + 0x2c]
    mov  eax, dword ptr [ebp - 0x40]
    cmp  al, byte ptr [edi + 0xc]
    je   s_out
    mov  ecx, dword ptr [ebp - 4]
    mov  eax, dword ptr [ecx + {g_map:#x}]
    mov  eax, dword ptr [eax + 0xe4]
    mov  eax, dword ptr [eax + 0xc]
    mov  dword ptr [ebp - 0xc], eax
    call {dcount:#x}
    mov  dword ptr [ebp - 0x10], eax
s_find:
    dec  dword ptr [ebp - 0x10]
    js   s_out
    mov  edx, dword ptr [ebp - 0x10]
    mov  eax, dword ptr [ebp - 0xc]
    call {dobj:#x}
    test eax, eax
    jz   s_find
    mov  edx, dword ptr [ebp - 0x40]
    cmp  dl, byte ptr [eax + 0xc]
    jne  s_find
    mov  dword ptr [ebp - 0x14], eax
    mov  ecx, dword ptr [ebp - 4]
    mov  eax, dword ptr [ecx + {c_uhs:#x}]
    xor  ecx, ecx
    mov  dl, 1
    call {uhs_create:#x}
    mov  dword ptr [ebp - 0x18], eax
    mov  edx, dword ptr [ebp - 0x14]
    call {uhs_init:#x}
    mov  eax, dword ptr [edi + 0x60]
    mov  dword ptr [ebp - 0x1c], eax
    movzx edx, byte ptr [eax + 0x14]
    mov  dword ptr [ebp - 0x20], edx
    mov  eax, dword ptr [ebp - 0x18]
    call {setdir:#x}
    mov  eax, dword ptr [ebp - 0x1c]
    mov  edx, dword ptr [eax]
    call dword ptr [edx + 0x74]
    movsx eax, al
    mov  dword ptr [ebp - 0x24], eax
    mov  eax, dword ptr [ebp - 0x1c]
    mov  edx, dword ptr [eax]
    call dword ptr [edx + 0x78]
    movsx eax, al
    mov  dword ptr [ebp - 0x28], eax
    mov  ecx, dword ptr [ebp - 4]
    mov  eax, dword ptr [ecx + {g_map:#x}]
    mov  eax, dword ptr [eax + 0x10]
    xor  edx, edx
    call {getlevel:#x}
    mov  dword ptr [ebp - 0x2c], eax
    test eax, eax
    jz   s_out
    mov  dword ptr [ebp - 0x38], 1
    mov  dword ptr [ebp - 0x3c], 1
s_dirlp:
    mov  ecx, dword ptr [ebp - 0x3c]
    call s_hx
    mov  ecx, dword ptr [ebp - 0x28]
    sub  ecx, dword ptr [ebp - 0x34]
    mov  edx, dword ptr [ebp - 0x24]
    sub  edx, dword ptr [ebp - 0x30]
    mov  eax, dword ptr [ebp - 0x24]
    call {meleedir:#x}
    movzx eax, ax
    cmp  eax, dword ptr [ebp - 0x20]
    jne  s_dirnx
    mov  eax, dword ptr [ebp - 0x3c]
    mov  dword ptr [ebp - 0x38], eax
    jmp  s_try0
s_dirnx:
    inc  dword ptr [ebp - 0x3c]
    cmp  dword ptr [ebp - 0x3c], 6
    jle  s_dirlp
s_try0:
    mov  ecx, dword ptr [ebp - 0x38]
    call s_hx
    call s_ok
    test eax, eax
    jnz  s_place
    mov  dword ptr [ebp - 0x3c], 1
s_trylp:
    mov  ecx, dword ptr [ebp - 0x3c]
    call s_hx
    call s_ok
    test eax, eax
    jnz  s_place
    inc  dword ptr [ebp - 0x3c]
    cmp  dword ptr [ebp - 0x3c], 168
    jle  s_trylp
    jmp  s_out
s_place:
    push dword ptr [ebp - 0x34]
    push 0
    mov  ecx, dword ptr [ebp - 0x30]
    mov  edx, dword ptr [ebp - 0x18]
    mov  esi, dword ptr [ebp - 4]
    mov  eax, dword ptr [esi + {g_map:#x}]
    call {placehx:#x}
s_out:
    mov  esp, ebp
    pop  ebp
    popad
    ret
s_hx:
    lea  eax, [ebp - 0x30]
    push eax
    lea  eax, [ebp - 0x34]
    push eax
    mov  edx, dword ptr [ebp - 0x28]
    mov  eax, dword ptr [ebp - 0x24]
    call {c2hx:#x}
    ret
s_ok:
    mov  eax, dword ptr [ebp - 0x2c]
    mov  edx, dword ptr [ebp - 0x30]
    test edx, edx
    jl   s_bad
    cmp  edx, dword ptr [eax + 0xc]
    jge  s_bad
    mov  ecx, dword ptr [ebp - 0x34]
    test ecx, ecx
    jl   s_bad
    cmp  ecx, dword ptr [eax + 0x10]
    jge  s_bad
    call {getfield:#x}
    test eax, eax
    jz   s_bad
    cmp  byte ptr [eax + 0x15], 8
    je   s_bad
    mov  edx, 0x220104
    mov  ecx, dword ptr [eax]
    call dword ptr [ecx + 0x80]
    test eax, eax
    jnz  s_bad
    mov  eax, 1
    ret
s_bad:
    xor  eax, eax
    ret
"""


def build():
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    z = bytearray(ZONE_END - ZONE)
    z[0:4] = MAGIC
    struct.pack_into("<II", z, 4, IN_PREV, BC_PREV)
    ends = {U_ISSUM: U_IN, U_IN: U_BC, U_BC: U_SUM, U_SUM: len(z)}

    def put(off, head, src):
        va = ZONE + off
        body = bytes(ks.asm(src.format(**F), va + len(head))[0])
        code = head + body
        assert off + len(code) <= ends[off], (hex(off), len(code))
        z[off:off + len(code)] = code

    put(U_ISSUM, b"\x51\x52" + pic("ecx", ZONE + U_ISSUM + 2), ISSUM)     # push ecx/edx ; ecx = delta
    put(U_IN, b"", IN)
    put(U_BC, b"", BC)
    put(U_SUM, b"", SUMMON.replace("    pushad\n    mov  esi, dword ptr [ebp - 4]\n", "", 1))
    # SUMMON needs the delta in ecx at `mov [ebp-4], ecx`: prepend pushad / mov esi,[ebp-4] / pic(ecx) as raw bytes
    va = ZONE + U_SUM
    head = b"\x60" + b"\x8b\x75\xfc" + pic("ecx", va + 4)
    body = bytes(ks.asm(SUMMON.replace("    pushad\n    mov  esi, dword ptr [ebp - 4]\n", "", 1).format(**F),
                        va + len(head))[0])
    code = head + body
    assert U_SUM + len(code) <= len(z), len(code)
    z[U_SUM:U_SUM + len(code)] = code
    call = lambda site, to: b"\xe8" + struct.pack("<i", to - (site + 5))
    jmp = lambda site, to: b"\xe9" + struct.pack("<i", to - (site + 5))
    return bytes(z), call(IN_SITE, ZONE + U_IN), jmp(BC_SITE, ZONE + U_BC)


def relocs(path, ranges):
    import pefile
    pe = pefile.PE(path, fast_load=True)
    pe.parse_data_directories([pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_BASERELOC"]])
    ib = pe.OPTIONAL_HEADER.ImageBase
    return [hex(ib + e.rva) for b in getattr(pe, "DIRECTORY_ENTRY_BASERELOC", []) for e in b.entries
            if e.type and any(lo - 3 <= ib + e.rva < hi for lo, hi in ranges)]


def main():
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    d = bytearray(open(DLL, "rb").read())
    g = lambda va, n: bytes(d[va - V2F:va - V2F + n])
    zone, in_new, bc_new = build()
    in_old = b"\xe8" + struct.pack("<i", IN_PREV - (IN_SITE + 5))
    bc_old = b"\xe9" + struct.pack("<i", BC_PREV - (BC_SITE + 5))
    types = [g(SPELLTYPES + i, 1)[0] for i in SUMMON_IDS]
    st_t = "vanilla" if all(t == 0 for t in types) else "ours" if all(t == CLASS for t in types) else "MIXED %s" % types
    s_in, s_bc, zn = g(IN_SITE, 5), g(BC_SITE, 5), g(ZONE, ZONE_END - ZONE)
    st_in = "vanilla" if s_in == in_old else "ours" if s_in == in_new else "OTHER"
    st_bc = "vanilla" if s_bc == bc_old else "ours" if s_bc == bc_new else "OTHER"
    st_z = "zero" if not any(zn) else "ours" if zn == zone else "older" if zn[:4] == MAGIC else "OTHER"
    print("SpellTypes %s | IN %s | BC %s | zone %s (%d B)" % (st_t, st_in, st_bc, st_z, len(zone.rstrip(b'\0'))))
    if "OTHER" in (st_in, st_bc, st_z) or st_t.startswith("MIXED"):
        print("ABORT (a site was re-chained by another patch since, or table mismatch)"); return 1
    bad = relocs(DLL, [(IN_SITE, IN_SITE + 5), (BC_SITE, BC_SITE + 5), (ZONE, ZONE_END)])
    if bad: print("ABORT relocs", bad); return 1
    want = ("vanilla", "vanilla", "vanilla", "zero") if revert else ("ours", "ours", "ours", "ours")
    if (st_t, st_in, st_bc, st_z) == want: print("already %s" % ("reverted" if revert else "applied")); return 0
    if not apply and not revert: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(DLL, ".bak_combatsummon")
    if not revert and not os.path.exists(bak): shutil.copy2(DLL, bak); print("backup ->", bak)
    writes = [(ZONE, bytes(len(zone)) if revert else zone), (IN_SITE, in_old if revert else in_new),
              (BC_SITE, bc_old if revert else bc_new)]
    writes += [(SPELLTYPES + i, bytes([0 if revert else CLASS])) for i in SUMMON_IDS]
    with open(DLL, "r+b") as f:
        for va, b in writes:
            f.seek(va - V2F); f.write(b)
    d2 = open(DLL, "rb").read()
    assert all(d2[va - V2F:va - V2F + len(b)] == b for va, b in writes)
    print("reverted" if revert else "Written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
