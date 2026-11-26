#!/usr/bin/env python3
r"""AoWx -- AI players explore exploration sites (lair/dungeon/crypt/ruin/
pyramid/item site).  v2: STRENGTH-AWARE (user feedback 2026-08-31 after v1:
"AI gathers stragglers around sites; should only be attracted/search when
strong enough; attraction should scale with defender strength").

See v1 notes in [[ai-explores-sites]] for the base RE. v1 confirmed working
(AI walks to sites, searches, loots) but attracted EVERY idle group at flat
priority 30 regardless of the defender roster -> weak stragglers clustered
around occupied/strong sites.

v2 DESIGN
  Strength metric = the engine's own: TUnitList.GetStrength @0x55783300
  (eax=list, dl=kind 0 -> sum of TAbstractUnit.GetStrength: lazily-updated
  cached per-unit strengths). The defender roster is [site+0x34] (the list
  ExecuteSearch @0x557C1A78 feeds to the search combat; empty -> straight to
  reward). TArmy descends from TUnitList so the on-site army uses the same
  function. The asking AI group's cached aggregate = TAIGroupControl.
  GetStrengthMax @0x557389D4 (eax=gc, dx=kind BITMASK; dx=1 = kind 0).

  TARGETING (now a MapFieldMsgProc override -- the +0x1C4 UpdateAITarget
  dispatch only passes ctx+record, NOT the message, and the asking group
  lives at [msg+0x10]; so v2 repoints the sites' VMT +0xCC (all 7 verified
  = TStructure.MapFieldMsgProc @0x5575F730) to a cave that CHAINS to the
  inherited handler first, then handles msg 0x1200 itself; +0x1C4 stays the
  vanilla stub):
    guards: [msg+0x18]==0 (sub-hex), ctx mode [ctx+2]==0, asking player
    [ctx+0]!=0, site still has loot ([vmt+0x1F0]==0), result rec present.
    S_def = GetStrength(roster);  S_grp = GetStrengthMax(group, 1)
    (ladder re-tuned per user 2026-08-31:)
      S_def == 0            -> priority 100  (free loot -- city-tier draw)
      S_grp <  1.5 * S_def  -> contributes NOTHING (no straggler gathering)
      S_grp >= 10  * S_def  -> priority 100
      S_grp >= 5   * S_def  -> priority 75
      S_grp >= 3   * S_def  -> priority 45
      S_grp >= 2   * S_def  -> priority 30
      else (>= 1.5x)        -> priority 15
    max-combined into [rec+0] only (never +8/+0xC).
  Scale-free ratios: both sides use the same engine metric, so no absolute
  calibration is needed and attraction naturally rises as defenders weaken
  (or the group grows).

  SEARCH MINTING (ExecuteAI, VMT +0x1C0, as v1) adds the matching gate:
  mint only when 3 * armyStrength >= 2 * rosterStrength (army >= 2/3 of the
  defenders -- slightly laxer than the 1.5x attraction bar because a group
  may split; prevents both suicide searches and parked-but-never-searching
  armies). Undefended (S_def==0) always searches. TE mint unchanged from
  v1 (the engine's own no-dialog Search branch, token-serialized, MP-safe;
  ExecuteSearch revalidates on every peer).

Caves: cave_execai @0x55814780..0x55814840 (v1 zone), cave_msgproc
@0x55814A40..0x55814B40 (0x55814840..0x55814A40 = build_ai_itemloot.py).
Next free cave after this = 0x55814B40. PIC: call/pop anchor for the map
holder in cave_execai; cave_msgproc is rel32/register/virtual only. All
repointed VMT slots carry .reloc entries which stay valid (in-image VAs).

Usage: dry run default; --apply; --revert (surgical).
"""
import os
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.environ.get("AOW_GAME_DIR") or os.path.dirname(HERE)
DLL = os.path.join(GAME, "AoWEPACK.dll")
BAK = DLL + ".bak_aisitesearch"

D = 0x55700C00
STUB_EXECAI = 0x5575E698
STRUCT_MSGPROC = 0x5575F730
CANSEARCH = 0x557C1E1C
GETTOKENCTL = 0x5570372C
GETOBJTYPE_ARMYHS = 0x20217
LIST_STRENGTH = 0x55783300     # TUnitList.GetStrength(eax=list, dl=kind)
GC_STRENGTHMAX = 0x557389D4    # TAIGroupControl.GetStrengthMax(eax=gc, dx=mask)
MAPPTR = 0x558E9494
PH_MAP = 0x11111111

CAVE_A = 0x55814780            # ExecuteAI (search minting, strength-gated)
CAVE_A_HI = 0x55814840
CAVE_B = 0x55814A40            # MapFieldMsgProc override (AI targeting)
CAVE_B_HI = 0x55814B40

SITES = [
    ("TExplorationSite", 0x557C1440),
    ("TItemExplorationSite", 0x557C23BC),
    ("TMonsterlair", 0x557C2D24),
    ("TDungeon", 0x557C557C),
    ("TCrypt", 0x557C64D0),
    ("TRuin", 0x557C68FC),
    ("TPyramid", 0x557C6D20),
]


def asm(src, addr):
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    src = "\n".join(ln.split(";")[0] for ln in src.splitlines())
    code, _ = Ks(KS_ARCH_X86, KS_MODE_32).asm(src, addr)
    return bytearray(code)


def make_execai():
    src = f"""
        cmp  ecx, 1
        je   _go
        cmp  ecx, 2
        jne  _no
    _go:
        push ebx
        push esi
        push edi
        mov  ebx, eax
        mov  esi, edx
        mov  edx, esi
        mov  eax, ebx
        call 0x{CANSEARCH:X}
        test al, al
        jz   _out
        mov  eax, [ebx+0x34]
        test eax, eax
        jz   _mint
        xor  edx, edx
        call 0x{LIST_STRENGTH:X}
        mov  edi, eax
        test edi, edi
        jz   _mint
        mov  edx, 0x{GETOBJTYPE_ARMYHS:X}
        mov  eax, [ebx+4]
        mov  ecx, [eax]
        call dword ptr [ecx+0x80]
        test eax, eax
        jz   _out
        mov  eax, [eax+0x1C]
        test eax, eax
        jz   _out
        xor  edx, edx
        call 0x{LIST_STRENGTH:X}
        lea  ecx, [eax + eax*2]
        lea  edx, [edi + edi]
        cmp  ecx, edx
        jl   _out
    _mint:
        mov  eax, ebx
        mov  edx, [eax]
        call dword ptr [edx+0x160]
        mov  esi, eax
        mov  edx, esi
        mov  eax, ebx
        mov  ecx, [eax]
        call dword ptr [ecx+0x164]
        xor  eax, eax
        mov  [esi+0x18], eax
        mov  dword ptr [esi+0x20], 1
        call _a
    _a:
        pop  ebx
        mov  eax, [ebx + 0x{PH_MAP:X}]
        mov  eax, [eax]
        mov  eax, [eax+0x23C]
        movsx edx, byte ptr [esi+0x13]
        call 0x{GETTOKENCTL:X}
        mov  edx, esi
        mov  ecx, [eax]
        call dword ptr [ecx+0x10]
        mov  eax, esi
        mov  edx, [eax]
        call dword ptr [edx+0x2C]
    _out:
        pop  edi
        pop  esi
        pop  ebx
    _no:
        xor  eax, eax
        ret
    """
    code = asm(src, CAVE_A)
    i = next(k for k in range(len(code) - 5)
             if code[k] == 0xE8 and code[k + 1:k + 5] == b"\x00\x00\x00\x00"
             and code[k + 5] == 0x5B)
    anchor = CAVE_A + i + 5
    j = code.find(struct.pack("<I", PH_MAP))
    assert j != -1
    code[j:j + 4] = struct.pack("<i", MAPPTR - anchor)
    return bytes(code)


def make_msgproc():
    src = f"""
        push ebx
        push esi
        push edi
        push ebp
        mov  esi, eax
        mov  edi, edx
        mov  eax, esi
        mov  edx, edi
        call 0x{STRUCT_MSGPROC:X}
        cmp  dword ptr [edi], 0x1200
        jnz  _done
        cmp  dword ptr [edi+0x18], 0
        jnz  _done
        mov  eax, [edi+8]
        test eax, eax
        jz   _done
        cmp  byte ptr [eax+2], 0
        jnz  _done
        cmp  byte ptr [eax], 0
        jz   _done
        mov  ebx, [edi+0xC]
        test ebx, ebx
        jz   _done
        mov  eax, esi
        mov  edx, [eax]
        call dword ptr [edx+0x1F0]
        test al, al
        jnz  _done
        mov  eax, [esi+0x34]
        test eax, eax
        jz   _undef
        xor  edx, edx
        call 0x{LIST_STRENGTH:X}
        mov  ebp, eax
        test ebp, ebp
        jz   _undef
        mov  eax, [edi+0x10]
        test eax, eax
        jz   _done
        mov  dx, 1
        call 0x{GC_STRENGTHMAX:X}
        lea  ecx, [ebp + ebp*2]
        lea  edx, [eax + eax]
        cmp  edx, ecx
        jl   _done
        lea  edx, [ebp + ebp*4]
        add  edx, edx
        cmp  eax, edx
        jge  _p100
        lea  edx, [ebp + ebp*4]
        cmp  eax, edx
        jge  _p75
        cmp  eax, ecx
        jge  _p45
        lea  edx, [ebp + ebp]
        cmp  eax, edx
        jge  _p30
        mov  eax, 15
        jmp  _comb
    _p30:
        mov  eax, 30
        jmp  _comb
    _p100:
        mov  eax, 100
        jmp  _comb
    _p75:
        mov  eax, 75
        jmp  _comb
    _p45:
        mov  eax, 45
        jmp  _comb
    _undef:
        mov  eax, 100
    _comb:
        cmp  dword ptr [ebx], eax
        jge  _done
        mov  dword ptr [ebx], eax
    _done:
        pop  ebp
        pop  edi
        pop  esi
        pop  ebx
        ret
    """
    return bytes(asm(src, CAVE_B))


def main():
    apply = "--apply" in sys.argv
    revert = "--revert" in sys.argv
    d = bytearray(open(DLL, "rb").read())
    ca, cb = make_execai(), make_msgproc()
    assert CAVE_A + len(ca) <= CAVE_A_HI, len(ca)
    assert CAVE_B + len(cb) <= CAVE_B_HI, len(cb)

    edits = [(CAVE_A, bytes(len(ca)), ca, "cave_execai v2 (strength-gated mint)"),
             (CAVE_B, bytes(len(cb)), cb, "cave_msgproc v2 (weighted targeting)")]
    for nm, vmt in SITES:
        edits.append((vmt + 0x1C0, struct.pack("<I", STUB_EXECAI),
                      struct.pack("<I", CAVE_A), "%s ExecuteAI" % nm))
        edits.append((vmt + 0xCC, struct.pack("<I", STRUCT_MSGPROC),
                      struct.pack("<I", CAVE_B), "%s MapFieldMsgProc" % nm))

    states = []
    for va, ob, nb, nm in edits:
        c = bytes(d[va - D:va - D + len(nb)])
        st = "original" if c == ob else "applied" if c == nb else "FOREIGN"
        states.append(st)
        print("  %-40s @0x%08X  %s" % (nm, va, st))
    if "FOREIGN" in states:
        print("FOREIGN - refusing")
        return 1
    if revert:
        for va, ob, nb, _ in edits:
            d[va - D:va - D + len(nb)] = ob
        open(DLL, "wb").write(bytes(d))
        print("reverted")
        return 0
    if not apply:
        print("dry run (--apply / --revert)")
        return 0
    if all(s == "applied" for s in states):
        print("already applied")
        return 0
    if not os.path.isfile(BAK):
        shutil.copy2(DLL, BAK)
        print("backed up")
    for va, ob, nb, _ in edits:
        d[va - D:va - D + len(nb)] = nb
    open(DLL, "wb").write(bytes(d))
    print("APPLIED v2 - test: weak AI stacks NO LONGER gather around strong "
          "sites; strong AI groups still walk to and clear sites (weak "
          "defenders preferred); an undefended unlooted site is highly "
          "attractive and searched promptly; already-looted sites ignored; "
          "humans unchanged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
