#!/usr/bin/env python3
r"""
Suspend (214) fixes, 2026-10-16 (user test of the first build).  AoWEPACK.dll only.

1. "It only lets me cast Suspend on my own units":  the tactical cursor (TCPCK UpdateMoveCursor 0x41F6E8, side byte
   [ebp-0x15]) and the click (CalculateRangedPath, around 0x41DD1F) both take the target SIDE from the spell's
   GetCombatInfo (VMT+0x7C) info byte +7 (bit 1 = own units, bit 2 = enemies).  TRemedy inherits
   TUnitSpell.GetCombatInfo 0x5577AC78, which HARD-CODES that byte to 1 @0x5577AC86 (`mov al,1 / mov [ebx+7],al`).
   (The pipeline's poke (0x3B, 1, 3) does nothing useful for a TUnitSpell: +0x38..+0x3B is its range DWORD - the
   damage-spell layout +0x3B 'target side' only exists for TCombatSpell damage spells.)
   GCI  call-hook @0x5577AC86 (5 B, vanilla, reloc-free; esi = spell, ebx = info): side := 3 for spell 214, else 1.
        Covers the hover cursor AND the click (both read the same info).

2. "ATK 7 against enemies, never miss against friendly":  RL  chained IN FRONT of whatever owns TRemedy.ExecuteSpell
   0x557E736C (live: Static Shield -> Suspend -> Second Wind ...; the previous jmp target is decoded at APPLY time
   and kept in the zone header for --revert).  For spell 214 on the TACTICAL path only (return address = the
   caster-cost cave's 0x558166D3 and esi = the caster CU with [esi+0x4C] == caster unit - Suspend's own test):
   find the target's TCombatUnit in the caster's combat object list ([[[[esi+8]+0xC]+0x34]+8] TList, item with
   [+0x4C] == target unit and IsClass TCombatUnit); if its side [cu+0x45] differs from the caster's
   -> HitRole(7 - RES) (0x55725D98: clamp(10*(ATK-RES)+50, 10, 90) vs RandInt(100) - the generator ExecuteDamageRole
   and the Thousand Threads / Miracle execute-time rolls use -> replay / LAN deterministic; RES = target unit
   VMT+0xCC, as TCombatUnit VMT+0x74).  A miss returns al = 1 (cast spent, no effect).  A hit, a friendly target,
   or any non-tactical caller falls through to the previous owner unchanged (-> Suspend's grant).
   No 'resisted' popup is shown (none exists for TUnitSpell casts; a miss is silent - the unit simply is not lifted).

3. v3 (user: "show 7 ATK in the PREVIEW PANEL, like Entangle"): the combat preview panel (AoWx.exe 0x433D9C) prints the
   GetCombatInfo ATTACK byte (info+0, shown when > 0, else '-'); TUnitSpell's filler 0x5577945C sets it to 0.  The GCI
   cave now also writes info+0 = 7 for 214 (display only - see build()).  Upgrades v1/v2 in place.

Zone AoWEPACK 0x5586D800..0x5586E000 (verified zero, reloc-free).  Header: [+0] the 5 vanilla GCI bytes,
[+8] the 6 RL site bytes found at apply.  PIC: in-image absolutes (CA_RET, the TCombatUnit class cell) via a
call/pop delta.  Dry-run default; --apply / --revert / --dis; --dll <scratch copy>.
Backup <game>\backup\AoWEPACK.dll.bak_suspendfix.  Apply AFTER patch_suspend_v1.py and patch_staticshield_v1.py;
revert BEFORE them (while applied their dry-runs report the ex site as OTHER - expected).
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
from patch_suspend_v1 import asm, rel, reloc_set, write_inplace

DEFAULT_DLL = game_file("AoWEPACK.dll")
BAK_SUFFIX = ".bak_suspendfix"
CODE_V2F = 0x55700C00
ZONE, ZONE_END = 0x5586D800, 0x5586E000
HDR = 0x20
SPELL, ATK = 214, 7
SHOW_ATK = 7                                             # v3: the preview panel's ATK (= the RL roll's fixed ATK 7)
RANGE, GCI_EPI = 0x0C, 0x5577AC95                       # v2: long range; TUnitSpell.GetCombatInfo epilogue (after its 'range := 0xFF')
CA_RET = 0x558166D3
HITROLE, IS_CLASS, TCU_CELL = 0x55725D98, 0x557010C0, 0x55715A94   # TCU_CELL = the TCombatUnit VMT itself (as patch_callofdead_v1's IsClass arg)
GCI_SITE, GCI_ORIG = 0x5577AC86, bytes.fromhex("b001884307")
RL_SITE = 0x557E736C


def build(prev_rl, v1=False, ver=3):
    out = bytearray(HDR); where = {}

    def place(name, src):
        while len(out) % 16: out.append(0)
        va = ZONE + len(out); where[name] = va; out.extend(asm(src, va))

    if v1:
        place("gci", """
            mov al, 1
            cmp dword ptr [esi + 0x10], %(spell)d
            jne g1
            mov al, 3
        g1:
            mov byte ptr [ebx + 7], al
            ret
        """ % {"spell": SPELL})
    elif ver == 3:
        # v3 (2026-10-16, user: "Suspend should show 7 ATK in the PREVIEW PANEL, like Entangle"): the combat preview panel
        # (AoWx.exe 0x433D9C: GetSpell([sel+0x38]).GetCombatInfo(unit, &info) -> info+0 > 0 ? IntToStr(ATK) : '-' into
        # label [panel+0xB0]; info+1 = DMG into [panel+0xC0]) prints the combat-info ATTACK byte.  TCombatSpell (Entangle,
        # Slow ...) copies [spell+0x34] there; TUnitSpell's filler 0x5577945C writes 0, so a TRemedy clone shows '-'.
        # For 214 info+0 := 7 (display only: the TCPCK readers of that byte (0x41041C.., 0x432CDF) serve the hard-coded
        # spell 0x75 only; cursor / click / AI / shot count read other bytes; the real roll is the RL cave below, a fixed
        # ATK 7 vs RES on enemies, friendlies never rolled).  One dword writes shots 1 / range 0x0C / targets 0 / side 3
        # (info+4..7), the return is dropped with 'pop eax' and it jumps past the 'range := 0xFF' to the epilogue.
        # 30 bytes - still the v1/v2 32-byte slot, so the RL cave keeps its address.
        place("gci", """
            cmp dword ptr [esi + 0x10], %(spell)d
            jne g1
            mov dword ptr [ebx + 4], %(info47)#x
            mov byte ptr [ebx], %(atk)d
            pop eax
            jmp %(epi)#x
        g1:
            mov byte ptr [ebx + 7], 1
            ret
        """ % {"spell": SPELL, "info47": 0x03000001 | (RANGE << 8), "atk": SHOW_ATK, "epi": GCI_EPI})
    else:
        # v2 (2026-10-16, user: Suspend should be LONG range, not infinite): the combat-info byte +5 is the RANGE (combat
        # spells copy [spell+0x38] -> info+4..7 = shots/range/targets/side, TCombatSpell.GetCombatInfo 0x557F7258), and
        # TUnitSpell.GetCombatInfo hard-codes it to 0xFF (= unlimited) at 0x5577AC91 AFTER this hook - so for 214 the cave
        # drops its return, writes side 3 + range 0x0C (Great Hail / Slow / Remedy's 12) and jumps straight to the epilogue
        # 0x5577AC95 (pop edi / pop esi / pop ebx / ret).  Every other TUnitSpell (Static Shield 215 incl.) keeps 0xFF.
        # Fits the v1 cave's 32-byte slot, so the RL cave stays at the same address (sites unchanged on upgrade).
        place("gci", """
            mov al, 1
            cmp dword ptr [esi + 0x10], %(spell)d
            jne g1
            mov byte ptr [ebx + 7], 3
            add esp, 4
            mov byte ptr [ebx + 5], %(rng)d
            jmp %(epi)#x
        g1:
            mov byte ptr [ebx + 7], al
            ret
        """ % {"spell": SPELL, "rng": RANGE, "epi": GCI_EPI})

    place("rl", """
        cmp dword ptr [eax + 0x10], %(spell)d
        je mine
        jmp %(prev)#x
    mine:
        push eax
        push edx
        push ecx
        push ebx
        push esi
        push edi
        call here
    here:
        pop ebx
        sub ebx, here
        mov eax, [esp + 0x18]
        sub eax, ebx
        cmp eax, %(caret)#x
        jne pass
        test esi, esi
        je pass
        mov eax, [esp + 0x10]
        cmp [esi + 0x4c], eax
        jne pass
        mov eax, [esi + 8]
        test eax, eax
        je pass
        mov eax, [eax + 0xc]
        test eax, eax
        je pass
        mov eax, [eax + 0x34]
        test eax, eax
        je pass
        mov edi, [eax + 8]
        test edi, edi
        je pass
        xor ecx, ecx
    lp:
        cmp ecx, [edi + 8]
        jge pass
        mov eax, [edi + 4]
        mov eax, [eax + ecx*4]
        test eax, eax
        je nx
        mov edx, [esp + 0xc]
        cmp [eax + 0x4c], edx
        jne nx
        push ecx
        push eax
        lea edx, [ebx + %(tcu)#x]
        call %(isc)#x
        test al, al
        pop eax
        pop ecx
        jne found
    nx:
        inc ecx
        jmp lp
    found:
        mov dl, byte ptr [eax + 0x45]
        cmp dl, byte ptr [esi + 0x45]
        je pass
        mov eax, [esp + 0xc]
        mov edx, [eax]
        call dword ptr [edx + 0xcc]
        movsx edx, al
        mov eax, %(atk)d
        sub eax, edx
        call %(hit)#x
        test al, al
        jne pass
        pop edi
        pop esi
        pop ebx
        pop ecx
        pop edx
        pop eax
        mov al, 1
        ret 8
    pass:
        pop edi
        pop esi
        pop ebx
        pop ecx
        pop edx
        pop eax
        jmp %(prev)#x
    """ % {"spell": SPELL, "prev": prev_rl, "caret": CA_RET, "tcu": TCU_CELL, "isc": IS_CLASS, "atk": ATK, "hit": HITROLE})
    assert ZONE + len(out) <= ZONE_END, hex(ZONE + len(out))
    return bytes(out), where


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dll", default=DEFAULT_DLL)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    d = open(a.dll, "rb").read()
    g = lambda va, n: bytes(d[va - CODE_V2F:va - CODE_V2F + n])
    zl = g(ZONE, ZONE_END - ZONE)
    applied = any(zl[HDR:])
    gci_cur, rl_cur = g(GCI_SITE, 5), g(RL_SITE, 6)
    rl_saved = zl[8:14] if applied else rl_cur
    assert rl_saved[0] == 0xE9, "RL site %#x is not a jmp: %s" % (RL_SITE, rl_saved.hex())
    prev_rl = RL_SITE + 5 + struct.unpack_from("<i", rl_saved, 1)[0]
    if not applied: assert gci_cur == GCI_ORIG, "GCI site not vanilla: %s" % gci_cur.hex()
    zone, where = build(prev_rl)
    zone = GCI_ORIG + bytes(3) + rl_saved + bytes(2) + zone[16:]
    zone1, where1 = build(prev_rl, v1=True)
    zone1 = GCI_ORIG + bytes(3) + rl_saved + bytes(2) + zone1[16:]
    zone2, where2 = build(prev_rl, ver=2)
    zone2 = GCI_ORIG + bytes(3) + rl_saved + bytes(2) + zone2[16:]
    assert where1 == where == where2, "v2/v3 must keep the v1 cave addresses"
    hooked = {"gci": rel(0xE8, GCI_SITE, where["gci"], 5), "rl": rel(0xE9, RL_SITE, where["rl"], 6)}
    st = {"gci": "ours" if gci_cur == hooked["gci"] else "vanilla" if gci_cur == GCI_ORIG else "OTHER",
          "rl": "ours" if rl_cur == hooked["rl"] else "chain" if rl_cur == rl_saved else "OTHER"}
    zstate = ("zero" if not any(zl) else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):])
              else "v1" if zl[:len(zone1)] == zone1 and not any(zl[len(zone1):])
              else "v2" if zl[:len(zone2)] == zone2 and not any(zl[len(zone2):]) else "DIFFERS")
    rl_set = reloc_set(d)
    bad = [hex(r) for r in rl_set if ZONE - 3 <= r < ZONE_END or GCI_SITE - 3 <= r < GCI_SITE + 5 or RL_SITE - 3 <= r < RL_SITE + 6]
    print("sites %s | prev rl %#x | zone %s (%d B) | relocs %s | caves %s"
          % (st, prev_rl, zstate, len(zone), bad or "none", ", ".join("%s=%#x" % kv for kv in where.items())))
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        for i in md.disasm(zone[HDR:], ZONE + HDR): print("   %08X  %-24s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad or "OTHER" in st.values() or zstate == "DIFFERS": print("ABORT"); return 1
    if a.revert:
        if not applied: print("already reverted"); return 0
        out = bytearray(d)
        out[GCI_SITE - CODE_V2F:GCI_SITE - CODE_V2F + 5] = GCI_ORIG
        out[RL_SITE - CODE_V2F:RL_SITE - CODE_V2F + 6] = rl_saved
        out[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
        write_inplace(a.dll, bytes(out)); print("reverted"); return 0
    if st == {"gci": "ours", "rl": "ours"} and zstate == "ours": print("already applied"); return 0
    if st == {"gci": "ours", "rl": "ours"} and zstate in ("v1", "v2"):
        print("%s build found -> upgrading to v3 (Suspend range 12 + preview-panel ATK %d)" % (zstate, SHOW_ATK))
    elif applied: print("ABORT: zone holds our code but the sites do not point at it"); return 1
    out = bytearray(d)
    out[ZONE - CODE_V2F:ZONE - CODE_V2F + len(zone)] = zone
    out[GCI_SITE - CODE_V2F:GCI_SITE - CODE_V2F + 5] = hooked["gci"]
    out[RL_SITE - CODE_V2F:RL_SITE - CODE_V2F + 6] = hooked["rl"]
    print("%d bytes change" % sum(1 for x, y in zip(d, out) if x != y))
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if os.path.abspath(a.dll) == os.path.abspath(DEFAULT_DLL):
        bak = bak_path(a.dll, BAK_SUFFIX)
        if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    write_inplace(a.dll, bytes(out)); assert open(a.dll, "rb").read() == bytes(out); print("Written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
