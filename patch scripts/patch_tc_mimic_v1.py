"""
Mimic (233, Secret L2, combat, research 100 / cost 5) - engine side, AoWTCPCK.dll only (2026-10-18).

v2 (2026-10-18, user): with NOTHING recorded the book pick now redirects to the REAL vanilla Dispel Magic (id 8) exactly
like a copy (A: edx := LAST or 8, armed) -> Dispel's side-panel preview / targeting / gfx / sfx, Mimic's cost 5
(D charges it), cancellable; D also records the copied id as LAST (so a mimicked Dispel counts as the last spell).
The AI still casts 233 itself = the plain Dispel clone (AI never goes through SelectSpell).  In-place upgrade from a
live v1 (SRC_V1 recognised; backup .bak_mimic2 = the v1 state); --revert from v1 or v2 restores vanilla exactly.

Spec: "Caster copies the LAST spell that was cast in the current combat by ANY player (for Mimic's cost).  If no spell
was previously cast, the caster casts Dispel Magic for Mimic's cost unless cancelled."

Design.  233 itself is a TDispelMagic clone (pipeline entry in _mimic_integration.txt: donor TDispelMagic, pfs 18,
SpellTypes class 7), so with nothing recorded it IS a Dispel Magic at cost 5 - same targeting, cancellable, the AI
sees a dispel.  The copy redirects the human cast into the copied spell's OWN targeting/cast flow:
  E  TAoWCombatMap.Create 0x41B398 (6 B prologue): LAST / ARMED / MIMIC_TE := 0 -> the record is per combat (a combat
     reloaded from a save also starts empty - identical on every client).
  A  TTacticalCombatUnitHS.SelectSpell 0x423270 (6 B prologue; eax = unit HS, edx = spell id; called by the combat
     spell book in AoWx.exe): edx == 233 and LAST != 0 -> ARMED := (hs, LAST) and edx := LAST, so the book's click
     continues as the copied spell (its targeting cursor and range, cancellable as usual).  Any other pick clears
     ARMED.  The book has already checked Mimic's own cost (5).
  B  AbRangedTC 0x4238BA, right after CreateTCAbRangedTE (7 B `mov [ebp-0x10],eax / cmp [ebp-0x10],0`): if the new TE
     belongs to the ARMED hs, ability 0x34 (spellcasting) and spell id == ARMED id -> [te+0x18] |= 0x10000 (the
     "mimicked" mark travels INSIDE the TE: +0x18 is a full streamed dword, TCAbRangedTE.Stream 0x40B268 tag 0x1F),
     then ARMED := 0.  0x4238B5 is the only CreateTCAbRangedTE call site.
  C  TCAbRangedTE.Execute 0x40B32B (6 B `mov byte [ebp-9],0 / xor eax,eax`, before ANY [te+0x18] read - the bound
     check @0x40B3F4, GetSpell @0x40B432 and the Ashes gate chain @0x40B33D all come later): a marked spellcasting TE
     is unmarked and remembered as MIMIC_TE.  Runs on every client -> MP-synced.
  D  0x40B44D, the only call of TSpell.CombatSpellCast (5 B `call 0x4029AC`; eax = GetSpell(id), edx = caster CU,
     [ebp-4] = te), executed by every client in TE order:
       te == MIMIC_TE -> MIMIC_TE := 0; mirror shimmer at the caster (kind-0x26 driver, Mimic's gfx slot 1) + Mimic's
          sound cue 1; mana = THero.CastingMana(hero, GetSpell(233)) (Mimic's cost, Mimic's own caster-ability
          discount) charged through TSpell.CombatCastingDone(copied spell, CU, cost) - i.e. CombatSpellCast with only
          the cost source swapped.  LAST is unchanged (it already holds the copied id).
       otherwise -> LAST := spell id unless it is 233 (Mimic is never copied; its Dispel fallback isn't either);
          a 233 cast (the fallback) also gets the shimmer; then the original CombatSpellCast (tail jump to the thunk).
Globals: 4 dwords in AoWEPACK.dll .idata page slack 0x5590BE40 (runtime-only zero memory past the section's raw data,
like essence 0x5590BD00/BD10 and reversal 0x5590BFF0): +0 LAST, +4 ARMED_HS, +8 ARMED_ID, +0xC MIMIC_TE; reached
rebase-safe as [CombatSpellCast IAT slot 0x46E598] - 0x5577954C (+ the TCPCK call/pop delta for the slot itself).
AI: never goes through SelectSpell -> an AI Mimic is always the plain Dispel Magic (AI priority = the donor's).
Limits: the copied spell's OWN legality checks (e.g. a summon needs a free hex) apply; SelectSpell does not re-check
mana, the book checked 5.  A combat replay re-runs the TE unmarked (the mark is stripped at Execute): it shows the
copied spell, display only.  A TE whose caster vanished before phase 0 would leave MIMIC_TE set until the next combat
(freed TE objects: a reused address could at worst be charged Mimic's 5 instead of its own cost).
Caves: TCPCK 0x44D800-0x44DAC4, packed by caves() (allocation 0x44D800-0x44E000).  No AoWEPACK code (its 0x55880000 allocation unused).
LIFO: independent of every other script (5 vanilla sites, own zone); revert THIS before anything that rewrites the
bytes at 0x423270 / 0x4238BA / 0x40B32B / 0x40B44D / 0x41B398.  Dry-run default; --apply / --revert / --dll <copy>.
Backup <game>\\backup\\AoWTCPCK.dll.bak_mimic.
"""
import argparse, os, shutil, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import patch_tc_banshee_vortex_v1 as BV
from bakpath import bak_path, game_file

SPELL_ID = 233
DISPEL_ID = 8                                       # v2: vanilla Dispel Magic (TDispelMagic.Create sets id 8 @0x557E8993)
MARK = 0x10000
CODE_V2F = 0x400C00
ZONE, ZONE_END, ALLOC_END = 0x44D800, 0x44DC00, 0x44E000
CSC_SLOT, CSC_PREF = 0x46E598, 0x5577954C          # TSpell.CombatSpellCast IAT slot / its preferred-base address
CASTINGMANA, CASTDONE = 0x557894EC, 0x557794E8     # THero.CastingMana / TSpell.CombatCastingDone (preferred base)
G = 0x5590BE40                                     # AoWEPACK .idata page slack (preferred base)
G_LAST, G_ARMHS, G_ARMID, G_MTE = G, G + 4, G + 8, G + 0xC
CSC_THUNK = 0x4029AC
SPELLREG, GETSPELL, SFXPLAY, MAP = BV.SPELLREG_GLOBAL, BV.GETSPELL, BV.SFXPLAY, BV.MAP_GLOBAL
HXTOHP, ADDEFFECT, TOBJCREATE, XYZADD, GETXYZ, TXYZ_IAT = BV.HXTOHP, BV.ADDEFFECT, BV.TOBJCREATE, BV.XYZADD, BV.GETXYZ, BV.TXYZ_IAT
KIND_DRIVER = 0x26
SUF = ".bak_mimic"
# name: (site, vanilla bytes, resume VA or None = call site); cave VAs come from layout() (S first, 16-B aligned)
SITES = {
    "E": (0x41B398, bytes.fromhex("558bec83c4f0"), 0x41B39E),        # TAoWCombatMap.Create prologue
    "A": (0x423270, bytes.fromhex("558bec83c4e0"), 0x423276),        # SelectSpell prologue
    "B": (0x4238BA, bytes.fromhex("8945f0837df000"), 0x4238C1),      # after CreateTCAbRangedTE (je @0x4238C1 uses our flags)
    "C": (0x40B32B, bytes.fromhex("c645f70033c0"), 0x40B331),        # TCAbRangedTE.Execute, before any [te+0x18] read
    "D": (0x40B44D, bytes.fromhex("e85a75ffff"), None),              # call TSpell.CombatSpellCast (thunk 0x4029AC)
}
ORDER = ["S", "E", "A", "B", "C", "D"]


def asm(src, va):
    """keystone + the PIC delta idiom `call $D / pop ebx / sub ebx, $D` (as patch_tc_walloflames_v1.asm_delta)."""
    s1 = src.replace("call $D", ".byte 0xe8, 0, 0, 0, 0").replace("sub ebx, $D", "sub ebx, 0x7fffffff")
    b = bytearray(BV.ks.asm(s1, va)[0]); n = 0
    anchor = bytes([0xE8, 0, 0, 0, 0, 0x5B, 0x81, 0xEB]) + b"\xff\xff\xff\x7f"
    k = b.find(anchor)
    while k >= 0:
        struct.pack_into("<I", b, k + len(anchor) - 4, va + k + 5); n += 1; k = b.find(anchor, k + len(anchor))
    assert n == src.count("call $D"), "delta anchors: %d of %d" % (n, src.count("call $D"))
    return bytes(b)


# ebx = TCPCK delta, ecx = AoWEPACK delta (both 0 at the preferred bases)
EPDELTA = """
        call $D
        pop ebx
        sub ebx, $D
        mov ecx, dword ptr [ebx+%(slot)#x]
        sub ecx, %(pref)#x
"""
P = {"slot": CSC_SLOT, "pref": CSC_PREF, "last": G_LAST, "armhs": G_ARMHS, "armid": G_ARMID, "mte": G_MTE,
     "id": SPELL_ID, "mark": MARK, "thunk": CSC_THUNK, "reg": SPELLREG, "getspell": GETSPELL, "play": SFXPLAY,
     "map": MAP, "hx": HXTOHP, "add": ADDEFFECT, "create": TOBJCREATE, "xyzadd": XYZADD, "getxyz": GETXYZ,
     "txyz": TXYZ_IAT, "kind": KIND_DRIVER, "mana": CASTINGMANA, "done": CASTDONE, "dispel": DISPEL_ID}

SRC = {
    "E": """
        push ebx
        push ecx
""" + EPDELTA + """
        mov dword ptr [ecx+%(last)#x], 0
        mov dword ptr [ecx+%(armhs)#x], 0
        mov dword ptr [ecx+%(armid)#x], 0
        mov dword ptr [ecx+%(mte)#x], 0
        pop ecx
        pop ebx
        push ebp
        mov ebp, esp
        add esp, -0x10
        jmp %(ret)#x
""",
    "A": """
        push ebx
        push ecx
""" + EPDELTA + """
        cmp edx, %(id)d
        jne a_clear
        mov edx, dword ptr [ecx+%(last)#x]
        test edx, edx
        jne a_arm
        mov edx, %(dispel)d
    a_arm:
        mov dword ptr [ecx+%(armhs)#x], eax
        mov dword ptr [ecx+%(armid)#x], edx
        jmp a_out
    a_clear:
        mov dword ptr [ecx+%(armhs)#x], 0
    a_out:
        pop ecx
        pop ebx
        push ebp
        mov ebp, esp
        add esp, -0x20
        jmp %(ret)#x
""",
    "B": """
        mov dword ptr [ebp-0x10], eax
        test eax, eax
        je b_out
        push ebx
        push ecx
        push edx
""" + EPDELTA + """
        mov edx, dword ptr [ecx+%(armhs)#x]
        test edx, edx
        je b_pop
        cmp edx, dword ptr [ebp-4]
        jne b_clr
        cmp dword ptr [eax+0x14], 0x34
        jne b_clr
        mov edx, dword ptr [ecx+%(armid)#x]
        cmp dword ptr [eax+0x18], edx
        jne b_clr
        or dword ptr [eax+0x18], %(mark)#x
    b_clr:
        mov dword ptr [ecx+%(armhs)#x], 0
    b_pop:
        pop edx
        pop ecx
        pop ebx
    b_out:
        cmp dword ptr [ebp-0x10], 0
        jmp %(ret)#x
""",
    "C": """
        mov byte ptr [ebp-9], 0
        mov eax, dword ptr [ebp-4]
        cmp dword ptr [eax+0x14], 0x34
        jne c_out
        test dword ptr [eax+0x18], %(mark)#x
        je c_out
        and dword ptr [eax+0x18], 0xffff
        push ebx
        push ecx
""" + EPDELTA + """
        mov dword ptr [ecx+%(mte)#x], eax
        pop ecx
        pop ebx
    c_out:
        xor eax, eax
        jmp %(ret)#x
""",
    "D": """
        push ebx
        push ecx
""" + EPDELTA + """
        push edx
        mov edx, dword ptr [ebp-4]
        cmp edx, dword ptr [ecx+%(mte)#x]
        pop edx
        je d_mimic
        push edx
        mov edx, dword ptr [eax+0x10]
        cmp edx, %(id)d
        je d_fallback
        mov dword ptr [ecx+%(last)#x], edx
        pop edx
        jmp d_van
    d_fallback:
        pop edx
        push eax
        mov eax, edx
        call %(shimmer)#x
        pop eax
    d_van:
        pop ecx
        pop ebx
        jmp %(thunk)#x
    d_mimic:
        mov dword ptr [ecx+%(mte)#x], 0
        push edx
        mov edx, dword ptr [eax+0x10]
        mov dword ptr [ecx+%(last)#x], edx
        pop edx
        push esi
        push edi
        mov esi, edx
        mov edi, eax
        push ecx
        mov eax, esi
        call %(shimmer)#x
        mov eax, dword ptr [ebx+%(reg)#x]
        mov eax, dword ptr [eax]
        mov eax, dword ptr [eax+0x84]
        mov edx, %(id)d
        call %(getspell)#x
        push eax
        mov edx, dword ptr [ebx+%(map)#x]
        cmp byte ptr [edx+0x129], 0
        je d_nosnd
        mov eax, dword ptr [eax+0x28]
        mov edx, 1
        call %(play)#x
    d_nosnd:
        mov edx, dword ptr [esp]
        mov eax, dword ptr [esi+0x4c]
        mov ecx, dword ptr [esp+4]
        add ecx, %(mana)#x
        call ecx
        mov ecx, eax
        add esp, 4
        pop eax
        add eax, %(done)#x
        mov ebx, eax
        mov eax, edi
        mov edx, esi
        call ebx
        pop edi
        pop esi
        pop ecx
        pop ebx
        ret
""",
    # shimmer(eax = caster CU): kind-0x26 driver at the caster's hex for spell 233 -> draws Mimic's gfx slot 1 once
    # (patch_tc_repent_harvest_v1 "tepop" recipe); visual only, every register preserved.
    "S": """
        pushad
        call $D
        pop ebx
        sub ebx, $D
        test eax, eax
        jz s_out
        mov eax, dword ptr [eax+0x60]
        test eax, eax
        jz s_out
        mov esi, eax
        mov edx, dword ptr [esi]
        call dword ptr [edx+0x78]
        movsx eax, al
        push eax
        mov eax, esi
        mov edx, dword ptr [esi]
        call dword ptr [edx+0x74]
        movsx eax, al
        pop edx
        sub esp, 8
        lea ecx, [esp+4]
        push esp
        call %(hx)#x
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
        mov edx, dword ptr [esp+4]
        add edx, 16
        mov dword ptr [eax+4], edx
        mov edx, dword ptr [esp]
        add edx, 16
        mov dword ptr [eax+8], edx
        mov dword ptr [esi+0x14], 0x34
        mov dword ptr [esi+0x18], %(id)d
        mov dword ptr [esi+0x2c], 0
        add esp, 8
    s_out:
        popad
        ret
""",
}
# v1 sources of the two caves v2 changed (A: nothing recorded -> stayed 233; D: LAST untouched on a copy) -
# kept so a live v1 install is recognised and upgraded in place.
SRC_V1 = {
    "A": """
        push ebx
        push ecx
""" + EPDELTA + """
        cmp edx, %(id)d
        jne a_clear
        cmp dword ptr [ecx+%(last)#x], 0
        je a_clear
        mov dword ptr [ecx+%(armhs)#x], eax
        mov edx, dword ptr [ecx+%(last)#x]
        mov dword ptr [ecx+%(armid)#x], edx
        jmp a_out
    a_clear:
        mov dword ptr [ecx+%(armhs)#x], 0
    a_out:
        pop ecx
        pop ebx
        push ebp
        mov ebp, esp
        add esp, -0x20
        jmp %(ret)#x
""",
    "D": """
        push ebx
        push ecx
""" + EPDELTA + """
        push edx
        mov edx, dword ptr [ebp-4]
        cmp edx, dword ptr [ecx+%(mte)#x]
        pop edx
        je d_mimic
        push edx
        mov edx, dword ptr [eax+0x10]
        cmp edx, %(id)d
        je d_fallback
        mov dword ptr [ecx+%(last)#x], edx
        pop edx
        jmp d_van
    d_fallback:
        pop edx
        push eax
        mov eax, edx
        call %(shimmer)#x
        pop eax
    d_van:
        pop ecx
        pop ebx
        jmp %(thunk)#x
    d_mimic:
        mov dword ptr [ecx+%(mte)#x], 0
        push esi
        push edi
        mov esi, edx
        mov edi, eax
        push ecx
        mov eax, esi
        call %(shimmer)#x
        mov eax, dword ptr [ebx+%(reg)#x]
        mov eax, dword ptr [eax]
        mov eax, dword ptr [eax+0x84]
        mov edx, %(id)d
        call %(getspell)#x
        push eax
        mov edx, dword ptr [ebx+%(map)#x]
        cmp byte ptr [edx+0x129], 0
        je d_nosnd
        mov eax, dword ptr [eax+0x28]
        mov edx, 1
        call %(play)#x
    d_nosnd:
        mov edx, dword ptr [esp]
        mov eax, dword ptr [esi+0x4c]
        mov ecx, dword ptr [esp+4]
        add ecx, %(mana)#x
        call ecx
        mov ecx, eax
        add esp, 4
        pop eax
        add eax, %(done)#x
        mov ebx, eax
        mov eax, edi
        mov edx, esi
        call ebx
        pop edi
        pop esi
        pop ecx
        pop ebx
        ret
""",
}


def caves(ver=2):
    """-> (zone blob, {name: bytes}, {name: VA}); packed in ORDER from ZONE, each cave 16-byte aligned."""
    out, at, va = {}, {}, ZONE
    src = dict(SRC); src.update(SRC_V1 if ver == 1 else {})
    for k in ORDER:
        q = dict(P); q["ret"] = SITES[k][2] if k in SITES else 0; q["shimmer"] = at.get("S", 0)
        out[k] = asm(src[k] % q, va); at[k] = va; va = (va + len(out[k]) + 15) & ~15
    assert va <= ZONE_END, "zone overflow: %#x" % va
    blob = bytearray(ZONE_END - ZONE)
    for k, c in out.items(): blob[at[k] - ZONE:at[k] - ZONE + len(c)] = c
    return bytes(blob), out, at


def site_bytes(name, ver=2):
    site, van, ret = SITES[name]; cave = caves(ver)[2][name]
    if ret is None: return b"\xe8" + struct.pack("<i", cave - (site + 5))
    return b"\xe9" + struct.pack("<i", cave - (site + 5)) + b"\x90" * (len(van) - 5)


def patched(d):
    """The applied image of `d` (bytearray, vanilla at our sites/zone) - used by main() and the emulation test."""
    blob = caves()[0]
    d[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = blob
    for n, (site, van, ret) in SITES.items():
        sb = site_bytes(n); d[site - CODE_V2F:site - CODE_V2F + len(sb)] = sb
    return d


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dll", default=game_file("AoWTCPCK.dll")); a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read())
    f = lambda va, n: bytes(d[va - CODE_V2F:va - CODE_V2F + n])
    blob, parts, _at = caves()
    states = {}
    blob1 = caves(1)[0]
    for n, (site, van, ret) in SITES.items():
        b = f(site, len(van))
        states[n] = ("vanilla" if b == van else "ours" if b == site_bytes(n) else
                     "ours_v1" if b == site_bytes(n, 1) else "OTHER(%s)" % b.hex())
    z = f(ZONE, ALLOC_END - ZONE)
    zone = ("zero" if not any(z) else "ours" if z[:len(blob)] == blob and not any(z[len(blob):]) else
            "ours_v1" if z[:len(blob1)] == blob1 and not any(z[len(blob1):]) else "FOREIGN")
    rl = BV.reloc_set(bytes(d))
    bad = [hex(r) for r in rl if ZONE - 3 <= r < ALLOC_END or any(s - 3 <= r < s + len(v) for s, v, _r in SITES.values())]
    print("sites %s | zone %s | relocs %s | caves %s" % (" ".join("%s=%s" % kv for kv in states.items()), zone, bad or "none",
                                                       " ".join("%s:%d" % (k, len(v)) for k, v in parts.items())))
    if any(s.startswith("OTHER") for s in states.values()) or zone == "FOREIGN" or bad:
        print("ABORT"); return 1
    if a.revert:
        if all(s == "vanilla" for s in states.values()) and zone == "zero": print("not applied"); return 0
        for n, (site, van, ret) in SITES.items(): d[site - CODE_V2F:site - CODE_V2F + len(van)] = van
        d[ZONE - CODE_V2F:ALLOC_END - CODE_V2F] = bytes(ALLOC_END - ZONE)
    else:
        if all(s == "ours" for s in states.values()) and zone == "ours": print("already applied"); return 0
        if any(s in ("ours", "ours_v1") for s in states.values()) or zone in ("ours", "ours_v1"):
            for n, (site, van, ret) in SITES.items(): d[site - CODE_V2F:site - CODE_V2F + len(van)] = van
            print("older build / partial state -> re-applying every site (in-place upgrade to v2)")
        patched(d)
    if not (a.apply or a.revert):
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(a.dll, SUF + ("2" if "ours_v1" in list(states.values()) + [zone] else ""))   # v2 upgrade: .bak_mimic2 = the v1 state
    if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    BV.write_inplace(a.dll, bytes(d))
    assert open(a.dll, "rb").read() == bytes(d)
    print("written and verified"); return 0


if __name__ == "__main__":
    sys.exit(main())
