#!/usr/bin/env python3
r"""
AI heroes cast the spells of the scrolls they hold (AoWEPACK.dll + AoWTCPCK.dll, 2026-10-30).
Needs patch_scroll_spells_store_v1 (slots: [item+0x38] = id, [item+0x4C+4k] = id+1, 0 = None; type 5 = scroll).

The AI never uses the spell book; it builds its own spell lists from the player's researched spells:
  1. strategic  TCastSpellAIPA.PrefetchCastSpellActions 0x5577BA54: `call TPlayerMagicControl.ListSpells`
     @0x5577BA86 (eax=pmc, edx=&TSpellList, cl=type set; caster hero = edi) -> wrap: original call, then the
     hero's scroll spells with ListSpells' own filters (spell VMT+0x64 enabled, type [spell+0x22] <= 7 in the set),
     not yet listed -> TSpellList.Add 0x5577A03C.  The loop that follows (CastingTurns < 8 -> VMT+0x5C) is vanilla.
  2. auto/fast combat  TSpellCastingAbility.fcPrefetchCombatCommands: before the researched-list loop @0x5576E3CE
     (9 B, moved) the same per-spell body runs for each scroll spell the player has NOT researched: [spell+0xC]&2,
     THero.CanCastSpellInstantly(hero, id, cost, &[ebp-8]), spell VMT+0x90(spell, edx=edi).
  3. tactical  TCAI.EvalBattle: the 4 "player knows spell id" tests (IndexOf on [pmc+0x30], `call 0x40133C`) at
     0x418796 (unit [[ebp-0x2C]+0x4C]) and 0x418BE3 / 0x418FBE / 0x419631 ([[ebp-0x28]+0x4C]) -> stub: IndexOf;
     if -1 and that unit is a THero holding a scroll with that spell -> 0 ("known").
DIAG v1.1 (10/30): hit counters dwords 0x558E9BD0..0x558E9BEF (DATA slack, claimed): strategic enter/hero/
scroll-spell/added, fast-combat enter/hero/unknown-scroll-spell/cancast; read live with ai_scroll_probe.py.
Only synced state is read (hero backpack in list order) -> identical on every machine.
Zones: AoWEPACK 0x55848400..0x55848800 ('ASC1'), AoWTCPCK 0x454000..0x454400 ('ASC1').  PIC (call/pop delta,
rel32).  Dry-run default; --apply / --revert.  Backups <dll>.bak_aiscroll.
"""
import os, shutil, struct, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

MAGIC = b"ASC1"
H = lambda v: "0x%X" % v  # noqa: E731

# ---------------- AoWEPACK ----------------
EP_DLL, EP_BASE = game_file("AoWEPACK.dll"), 0x55700000
EP_ZONE, EP_END = 0x55848400, 0x55848800
ST_SITE, LISTSPELLS = 0x5577BA86, 0x5577D148
FC_SITE, FC_ORIG, FC_BACK = 0x5576E3CE, bytes.fromhex("8b45f48b40308b7008"), 0x5576E3D7
THERO_SELF = 0x55711FAC            # THero VMT self-pointer slot ([..] = VMT)
ISCLASS, GETSPELL, SL_ADD, IL_INDEXOF, CANCASTI = 0x557010C0, 0x55779AC8, 0x5577A03C, 0x55702EA4, 0x55789640
G_RES = 0x558FA044
ST_CODE, FC_CODE = EP_ZONE + 0x10, EP_ZONE + 0x200


def scroll_iter(hero_reg, body, frame):
    """iterate scroll spells of the hero in `hero_reg` (preserved). frame: esp offsets dict with keys
    items, k, slot, item.  body runs with eax = spell, ebx = delta; may jump to `nx` to skip."""
    f = frame
    return f"""
    mov  eax, dword ptr [{hero_reg} + 0x74]
    test eax, eax
    jz   it_end
    mov  eax, dword ptr [eax + 8]
    test eax, eax
    jz   it_end
    mov  dword ptr [esp + {f['items']}], eax
    mov  dword ptr [esp + {f['k']}], 0
it_next:
    mov  eax, dword ptr [esp + {f['items']}]
    mov  ecx, dword ptr [esp + {f['k']}]
    cmp  ecx, dword ptr [eax + 8]
    jge  it_end
    mov  eax, dword ptr [eax + 4]
    mov  eax, dword ptr [eax + ecx*4]
    test eax, eax
    jz   it_skip
    cmp  byte ptr [eax + 0x34], 5
    jne  it_skip
    mov  dword ptr [esp + {f['item']}], eax
    mov  dword ptr [esp + {f['slot']}], 0
sl_next:
    mov  ecx, dword ptr [esp + {f['slot']}]
    cmp  ecx, 7
    jge  it_skip
    mov  eax, dword ptr [esp + {f['item']}]
    test ecx, ecx
    jnz  sl_x
    mov  edx, dword ptr [eax + 0x38]
    jmp  sl_g
sl_x:
    mov  edx, dword ptr [eax + ecx*4 + 0x48]
    test edx, edx
    jz   nx
    dec  edx
sl_g:
    test edx, edx
    js   nx
    mov  eax, dword ptr [ebx + {H(G_RES)}]
    mov  eax, dword ptr [eax + 0x84]
    call {H(GETSPELL)}
    test eax, eax
    jz   nx
{body}
nx:
    inc  dword ptr [esp + {f['slot']}]
    jmp  sl_next
it_skip:
    inc  dword ptr [esp + {f['k']}]
    jmp  it_next
it_end:
"""


FR = dict(items=0x04, k=0x08, slot=0x0C, item=0x10)   # [esp]: set / spare

ST_SRC = f"""
    push ecx
    push edx
    call {H(LISTSPELLS)}
    pop  edx
    pop  ecx
    pushad
    sub  esp, 0x20
    mov  dword ptr [esp], ecx
    mov  eax, dword ptr [edx]
    mov  dword ptr [esp + 0x14], eax
    call {{G}}
    pop  ebx
    sub  ebx, {{G}}
    inc  dword ptr [ebx + 0x558e9bd0]
    test eax, eax
    jz   out
    mov  eax, edi
    test eax, eax
    jz   out
    mov  edx, dword ptr [ebx + {H(THERO_SELF)}]
    call {H(ISCLASS)}
    test al, al
    jz   out
    inc  dword ptr [ebx + 0x558e9bd4]
{scroll_iter('edi', '''
    inc  dword ptr [ebx + 0x558e9bd8]
    mov  esi, eax
    mov  edx, dword ptr [eax]
    call dword ptr [edx + 0x64]
    test al, al
    jz   nx
    movzx eax, byte ptr [esi + 0x22]
    cmp  eax, 7
    ja   nx
    bt   dword ptr [esp], eax
    jnc  nx
    mov  eax, dword ptr [esp + 0x14]
    mov  eax, dword ptr [eax + 4]
    mov  edx, dword ptr [eax + 4]
    mov  ecx, dword ptr [eax + 8]
dup:
    dec  ecx
    js   doadd
    cmp  dword ptr [edx + ecx*4], esi
    je   nx
    jmp  dup
doadd:
    inc  dword ptr [ebx + 0x558e9bdc]
    mov  eax, dword ptr [esp + 0x14]
    mov  edx, esi
    call %s''' % H(SL_ADD), FR)}
out:
    add  esp, 0x20
    popad
    ret
"""

FC_SRC = f"""
    pushad
    sub  esp, 0x20
    call {{G}}
    pop  ebx
    sub  ebx, {{G}}
    inc  dword ptr [ebx + 0x558e9be0]
    mov  eax, dword ptr [edi + 4]
    test eax, eax
    jz   out
    mov  eax, dword ptr [eax + 0x4C]
    test eax, eax
    jz   out
    mov  dword ptr [esp + 0x14], eax
    mov  edx, dword ptr [ebx + {H(THERO_SELF)}]
    call {H(ISCLASS)}
    test al, al
    jz   out
    mov  esi, dword ptr [esp + 0x14]
    inc  dword ptr [ebx + 0x558e9be4]
{scroll_iter('esi', '''
    mov  dword ptr [esp + 0x18], eax
    test byte ptr [eax + 0xC], 2
    jz   nx
    mov  edx, dword ptr [eax + 0x10]
    mov  eax, dword ptr [ebp - 0xC]
    mov  eax, dword ptr [eax + 0x30]
    call %s
    cmp  eax, -1
    jne  nx
    inc  dword ptr [ebx + 0x558e9be8]
    mov  eax, dword ptr [esp + 0x18]
    lea  ecx, [ebp - 8]
    push ecx
    mov  ecx, dword ptr [eax + 0x14]
    mov  edx, dword ptr [eax + 0x10]
    mov  eax, dword ptr [esp + 0x18]
    call %s
    test al, al
    jz   nx
    inc  dword ptr [ebx + 0x558e9bec]
    mov  edx, edi
    mov  eax, dword ptr [esp + 0x18]
    mov  ecx, dword ptr [eax]
    call dword ptr [ecx + 0x90]''' % (H(IL_INDEXOF), H(CANCASTI)), FR)}
out:
    add  esp, 0x20
    popad
    mov  eax, dword ptr [ebp - 0xC]
    mov  eax, dword ptr [eax + 0x30]
    mov  esi, dword ptr [eax + 8]
    jmp  {H(FC_BACK)}
"""

# ---------------- AoWTCPCK ----------------
TC_DLL, TC_BASE = game_file("AoWTCPCK.dll"), 0x400000
TC_ZONE, TC_END = 0x454000, 0x454400
TC_INDEXOF, TC_ISCLASS, TC_IAT_THERO = 0x40133C, 0x401058, 0x46E914
TC_SITES = [(0x418796, 0x2C), (0x418BE3, 0x28), (0x418FBE, 0x28), (0x419631, 0x28)]
TC_CHK = TC_ZONE + 0x10
TC_STUBS = [TC_ZONE + 0x100 + 0x20 * i for i in range(4)]

TC_CHK_SRC = f"""
    pushad
    call {{G}}
    pop  ebx
    sub  ebx, {{G}}
    mov  esi, ecx
    test esi, esi
    jz   no
    mov  esi, dword ptr [esi + 0x4C]
    test esi, esi
    jz   no
    mov  eax, esi
    mov  edx, dword ptr [ebx + {H(TC_IAT_THERO)}]
    call {H(TC_ISCLASS)}
    test al, al
    jz   no
    mov  edi, dword ptr [esp + 0x14]
    mov  eax, dword ptr [esi + 0x74]
    test eax, eax
    jz   no
    mov  eax, dword ptr [eax + 8]
    test eax, eax
    jz   no
    mov  ecx, dword ptr [eax + 8]
    mov  eax, dword ptr [eax + 4]
k_l:
    dec  ecx
    js   no
    mov  edx, dword ptr [eax + ecx*4]
    test edx, edx
    jz   k_l
    cmp  byte ptr [edx + 0x34], 5
    jne  k_l
    cmp  dword ptr [edx + 0x38], edi
    je   yes
    lea  ebp, [edi + 1]
    mov  esi, 6
s_l:
    cmp  dword ptr [edx + esi*4 + 0x48], ebp
    je   yes
    dec  esi
    jnz  s_l
    jmp  k_l
yes:
    mov  dword ptr [esp + 0x1C], 0
no:
    popad
    ret
"""


def solve(ks, tmpl, at):
    """assemble with the call/pop anchor {G} resolved to the address right after the anchor call."""
    g = 0x11111111
    for _ in range(4):
        code = bytes(ks.asm(tmpl.replace("{G}", H(g)), at)[0])
        ci = code.find(b"\x5b\x81\xeb")                      # pop ebx / sub ebx, imm32
        assert ci > 0
        if at + ci == g:
            assert struct.unpack_from("<i", code, ci - 4)[0] == 0
            return code
        g = at + ci
    raise AssertionError("anchor did not converge")


def build_ep():
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    st = solve(ks, ST_SRC, ST_CODE)
    fc = solve(ks, FC_SRC, FC_CODE)
    assert ST_CODE + len(st) <= FC_CODE and FC_CODE + len(fc) <= EP_END, (hex(len(st)), hex(len(fc)))
    z = bytearray(EP_END - EP_ZONE)
    z[0:4] = MAGIC
    z[ST_CODE - EP_ZONE:ST_CODE - EP_ZONE + len(st)] = st
    z[FC_CODE - EP_ZONE:FC_CODE - EP_ZONE + len(fc)] = fc
    P = [(ST_SITE, b"\xe8" + struct.pack("<i", LISTSPELLS - (ST_SITE + 5)), b"\xe8" + struct.pack("<i", ST_CODE - (ST_SITE + 5))),
         (FC_SITE, FC_ORIG, b"\xe9" + struct.pack("<i", FC_CODE - (FC_SITE + 5)) + b"\x90" * 4),
         (EP_ZONE, bytes(len(z)), bytes(z))]
    return P


def build_tc():
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    chk = solve(ks, TC_CHK_SRC, TC_CHK)
    assert TC_CHK + len(chk) <= TC_STUBS[0]
    z = bytearray(TC_END - TC_ZONE)
    z[0:4] = MAGIC
    z[TC_CHK - TC_ZONE:TC_CHK - TC_ZONE + len(chk)] = chk
    P = []
    for (site, off), at in zip(TC_SITES, TC_STUBS):
        stub = bytes(ks.asm(f"""
    push edx
    call {H(TC_INDEXOF)}
    pop  edx
    cmp  eax, -1
    jne  r
    mov  ecx, dword ptr [ebp - {H(off)}]
    call {H(TC_CHK)}
r:
    ret
""", at)[0])
        assert len(stub) <= 0x20
        z[at - TC_ZONE:at - TC_ZONE + len(stub)] = stub
        P.append((site, b"\xe8" + struct.pack("<i", TC_INDEXOF - (site + 5)), b"\xe8" + struct.pack("<i", at - (site + 5))))
    P.append((TC_ZONE, bytes(len(z)), bytes(z)))
    return P


def relocs(pe, base):
    out = set()
    for blk in getattr(pe, "DIRECTORY_ENTRY_BASERELOC", []):
        for e in blk.entries:
            if e.type == 3:
                out.add(base + e.rva)
    return out


def main():
    import pefile
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    plans = []
    for name, path, base, P in (("AoWEPACK", EP_DLL, EP_BASE, build_ep()), ("AoWTCPCK", TC_DLL, TC_BASE, build_tc())):
        d = open(path, "rb").read()
        pe = pefile.PE(data=d)
        off = lambda va, pe=pe, base=base: pe.get_offset_from_rva(va - base)  # noqa: E731
        rl = relocs(pe, base)
        bad = [hex(r) for r in rl if any(s - 3 <= r < s + len(o) for s, o, _ in P)]
        sts = []
        for s, o, n in P:
            c = d[off(s):off(s) + len(o)]
            sts.append("vanilla" if c == o else "ours" if c == n else "OTHER")
        print("%s: %s | relocs %s" % (name, ", ".join("%#x %s" % (s, st) for (s, _, _), st in zip(P, sts)), bad or "none"))
        if "OTHER" in sts or bad or len(set(sts)) != 1:
            print("ABORT (mixed/foreign state)"); return 1
        plans.append((path, off, P, sts[0]))
    want = "vanilla" if revert else "ours"
    if all(p[3] == want for p in plans):
        print("already %s" % ("reverted" if revert else "applied")); return 0
    if not apply and not revert:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    r = subprocess.run(["tasklist"], capture_output=True, text=True).stdout
    if "AoWx.exe" in r or "AoWDevX.exe" in r:
        print("game/editor running - close it first"); return 1
    for path, off, P, st in plans:
        if st == want:
            continue
        bak = bak_path(path, ".bak_aiscroll")
        if not revert and not os.path.exists(bak):
            shutil.copy2(path, bak); print("backup ->", bak)
        with open(path, "r+b") as f:                 # in-place (house rule); zone first on apply
            for s, o, n in reversed(P):
                f.seek(off(s)); f.write(o if revert else n)
        d2 = open(path, "rb").read()
        assert all(d2[off(s):off(s) + len(o)] == (o if revert else n) for s, o, n in P)
        print(os.path.basename(path), "reverted" if revert else "written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
