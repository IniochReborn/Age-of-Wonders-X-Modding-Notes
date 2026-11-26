#!/usr/bin/env python3
r"""patch_caster_cost_wallet_v1.py -- make EVERY spell cost gate / charge agree with THero.CastingMana.

Background (2026-09-13). The 410 dll carries the Evoker/Conjurer/Enchanter/Ritualist casting-cost
abilities (laptop port of BXL's build_caster_cost.py: cost classifier cave @0x55814F00 on
THero.CastingMana, discount = cost - (cost+1)/3). That port classifies EVERY spell that is not a
summon / unit enchantment / combat spell as "Ritualist", i.e. 50 classes, but only the two BXL
wallet caves (TGlobalEnchantmentSpell.Activate, TSummonSpell.Activate) and the in-place
TSummonSpellTE.Process fix push the DISCOUNTED cost into the token event. Every other path still
reads the spell's RAW cost field [spell+0x14].

Symptom: THero.CastSpell enters the instant branch when CastingMana <= casting points; the token
event is built with the raw cost; TSpellTE.Validate -> THero.CanCastSpellInstantly rejects it
because raw cost > points. The spell "starts" (targeting / animation) then silently does nothing
and charges nothing. Band: discounted <= points < raw, i.e. only after some points were spent.
Where the raw cost does fit, the hero was simply charged the raw cost (discount shown, not applied).

The same gate-vs-recheck mismatch exists for the other three abilities:
  * Evoker: seven fast-combat CreateCA routines store the raw cost into the combat action, and the
    exe spellbook (combat mode) + AoWTCPCK.dpl call THero.CanCastSpellInstantly with the raw cost,
    so a discounted combat spell is REFUSED when points < raw cost.
  * Enchanter: Cosmagic Scrying's own caster class pushes the raw cost (token event AND combat CA).
  * Conjurer: already consistent (BXL's Sites B/C) -- nothing to do.

What this script does (all rebase-safe: rel32 only, or call/pop delta for the one global):

  A. 25 token-event creation sites push CastingMana(caster, spell) instead of [spell+0x14]
     (per-site caves; the caster/spell registers differ per site, see SITES).
  B. 7 TE.Execute overrides that charged [spell+0x14] now charge [TE+0x1C] (4-byte in-place
     `push [reg+0x1C]; nop`, BXL's Site-C idiom).
  C. 4 spell.ExecuteTE routines with no TE pointer (Smoke Cloud, Crusade, Water Mastery, Call Hero)
     charge CastingMana(unit, spell).
  D. Cosmagic Scrying: token-event cost and combat-CA cost via CastingMana; TUnitSpell.CreateCA
     (every unit enchantment cast inside tactical combat) likewise stored the raw cost.
  E. Evoker fast-combat: 7 CreateCA raw stores -> CastingMana([caster+0x4C], spell), exactly what
     the correctly-written CreateCA variants do.
  F. THero.CanCastSpellInstantly entry hook: if the cost passed in equals the spell's raw cost, the
     caller did not know about CastingMana (exe spellbook, AoWTCPCK, AI) -> recompute it. Callers
     that already pass a discounted or unrelated cost (Disjunction) are untouched.

  Multi-turn channelling was checked and is already consistent (mana paid up front from
  CastingMana in ExecuteStartCasting; completion validated by channel identity, not cost).
  AI expense bookkeeping paths (AICastSpellExpenseMade etc.) stay raw on purpose: they only
  over-reserve.

Cave zone 0x55815800..0x55815FFF (verified all-zero, .reloc-free in the 410 dll).
Dry-run default; --apply; --revert; --dll <path>; --dis dumps the caves.
Backup: AoWEPACK.dll.bak_castercost_wallet
"""
import argparse, os, shutil, struct, sys
from bakpath import game_dir, game_file   # game folder = AOW_GAME_DIR or parent of patch scripts (2026-09-20)

DEFAULT_DLL = game_file("AoWEPACK.dll")
BAK_SUFFIX  = ".bak_castercost_wallet"
from bakpath import bak_path   # backups live in <game>\backup\ (2026-09-17)
BASE        = 0x55700000
FILE_DELTA  = 0x55700C00          # CODE section: file offset = VA - FILE_DELTA

CASTINGMANA = 0x557894EC          # THero.CastingMana(eax=caster unit, edx=spell) -> eax
GETSPELL    = 0x55779AC8          # TSpellControl.GetSpell(eax=ctrl, edx=id) -> spell
SPELLCTRL_G = 0x558FA044          # [g] -> object; [obj+0x84] = TSpellControl   (needs PIC delta)
CCSI_HOOK   = 0x5578964A          # THero.CanCastSpellInstantly: mov edi,ecx; mov esi,edx; mov ebx,eax
CCSI_RESUME = 0x55789650

CAVE_LO, CAVE_HI = 0x55815800, 0x55816000


# --------------------------------------------------------------------------- tiny assembler
class Asm:
    def __init__(self, va): self.va, self.buf, self.lab, self.fix = va, bytearray(), {}, []
    def here(self): return self.va + len(self.buf)
    def db(self, *b): self.buf += bytes(b); return self
    def dd(self, v): self.buf += struct.pack("<I", v & 0xFFFFFFFF); return self
    def raw(self, b): self.buf += bytes(b); return self
    def call(self, t): self.db(0xE8); self.buf += struct.pack("<i", t - (self.here() + 4)); return self
    def jmp(self, t): self.db(0xE9); self.buf += struct.pack("<i", t - (self.here() + 4)); return self
    def label(self, n): self.lab[n] = self.here()
    def j8(self, op, n): self.db(op); self.fix.append((len(self.buf), n)); self.db(0)
    def done(self):
        for off, n in self.fix:
            rel = self.lab[n] - (self.va + off + 1)
            assert -128 <= rel <= 127
            self.buf[off] = rel & 0xFF
        return bytes(self.buf)


# --------------------------------------------------------------------------- site table
# Each entry: (hook VA, original bytes, kind, params, description)
#   kind "push":   cave = <setup>; call CastingMana; push eax; <replay tail>; jmp back
#   kind "store":  cave = <setup>; call CastingMana; <store>; jmp back      (fast-combat CA cost)
#   kind "charge": cave = push eax; <setup>; call CastingMana; mov ecx,eax; pop eax; <replay>; jmp back
#   kind "inplace": 4-byte substitution, no cave
#   "setup" is a byte string that leaves eax=caster unit, edx=spell (may use the stack).
REG = dict(eax=0, ecx=1, edx=2, ebx=3, esp=4, ebp=5, esi=6, edi=7)
def mov_rr(dst, src): return bytes([0x8B, 0xC0 | (REG[dst] << 3) | REG[src]])
def mov_r_m8(dst, base, disp):  # mov dst,[base+disp8]  (base != esp)
    return bytes([0x8B, 0x40 | (REG[dst] << 3) | REG[base], disp & 0xFF])

A1 = ("push", mov_rr("eax", "edi") + mov_rr("edx", "esi"), b"\x8a\x4f\x24")     # esi=spell edi=caster
A2 = ("push", mov_rr("eax", "esi") + mov_rr("edx", "edi"), b"\x8b\x57\x10")     # edi=spell esi=caster
A3 = ("push", mov_rr("eax", "ebx") + mov_rr("edx", "esi"), b"\x8a\x4b\x24")     # esi=spell ebx=caster

SITES = [
    # ---- A. token-event creation: TGlobalTargetSpell target-picked functions (eax=spell->esi, edx=caster->edi)
    (0x5579EC96, b"\x8b\x46\x14\x50\x8a\x4f\x24", *A1, "A  TFreezeWater TE cost"),
    (0x5579F00E, b"\x8b\x46\x14\x50\x8a\x4f\x24", *A1, "A  TFireBarrier TE cost"),
    (0x5579F38A, b"\x8b\x46\x14\x50\x8a\x4f\x24", *A1, "A  TLevelTerrain TE cost"),
    (0x5579F6B2, b"\x8b\x46\x14\x50\x8a\x4f\x24", *A1, "A  TRejuvenate TE cost"),
    (0x557A20BE, b"\x8b\x46\x14\x50\x8a\x4f\x24", *A1, "A  THealingShowers/SmokeCloud TE cost (0x557A209C)"),
    (0x557A221E, b"\x8b\x46\x14\x50\x8a\x4f\x24", *A1, "A  global-target TE cost (0x557A21FC)"),
    (0x557A36D2, b"\x8b\x46\x14\x50\x8a\x4f\x24", *A1, "A  TRaiseTerrain TE cost"),
    (0x557C4B9A, b"\x8b\x46\x14\x50\x8a\x4f\x24", *A1, "A  TPoisonPlantSpell TE cost"),
    (0x557C896E, b"\x8b\x46\x14\x50\x8a\x4f\x24", *A1, "A  THolyGroundSpell TE cost"),
    (0x557C9AEE, b"\x8b\x46\x14\x50\x8a\x4f\x24", *A1, "A  TUnholyGroundSpell TE cost"),
    # ---- A. Activate-style (edi=spell, esi=caster)
    (0x557A0281, b"\x8b\x47\x14\x50\x8b\x57\x10", *A2, "A  TWatcher TE cost"),
    (0x557A1025, b"\x8b\x47\x14\x50\x8b\x57\x10", *A2, "A  TTornado TE cost"),
    (0x557A18E9, b"\x8b\x47\x14\x50\x8b\x57\x10", *A2, "A  TVortex TE cost"),
    (0x557CDBB9, b"\x8b\x47\x14\x50\x8b\x57\x10", *A2, "A  TStormSpell TE cost (all 6 storms)"),
    # ---- A. Activate-style (esi=spell, ebx=caster)
    (0x557EA6A2, b"\x8b\x46\x14\x50\x8a\x4b\x24", *A3, "A  TConcealArea TE cost"),
    (0x557EAC4E, b"\x8b\x46\x14\x50\x8a\x4b\x24", *A3, "A  TBirdsView TE cost"),
    (0x557EB4C2, b"\x8b\x46\x14\x50\x8a\x4b\x24", *A3, "A  TWarpParty TE cost"),
    (0x557EC476, b"\x8b\x46\x14\x50\x8a\x4b\x24", *A3, "A  TResurrectHero TE cost"),
    (0x557ECA16, b"\x8b\x46\x14\x50\x8a\x4b\x24", *A3, "A  TAnimateHero TE cost"),
    (0x557ECB79, b"\x8b\x46\x14\x50\x8a\x4b\x24", *A3, "A  TCallHero TE cost"),
    (0x557ED6CA, b"\x8b\x46\x14\x50\x8a\x4b\x24", *A3, "A  TCrusade TE cost"),
    # ---- A. TCityTargetSpell helper (eax=spell, ecx=caster, ebx=TE) -- eax/ecx must survive
    (0x557B097E, b"\x8b\x50\x14\x52\x8a\x49\x24", "push",
     b"\x50\x51" + mov_rr("edx", "eax") + mov_rr("eax", "ecx"), b"__CITY__", "A  TCityTargetSpell TE cost (10 city spells)"),
    # ---- A. Disjunction (eax=spell 0x33 = Disjunction itself, esi=caster)
    (0x557EBC8B, b"\x8b\x40\x14\x50\x8a\x4e\x24", "push",
     mov_rr("edx", "eax") + mov_rr("eax", "esi"), b"\x8a\x4e\x24", "A  TDisjunction TE cost"),
    # ---- D. Cosmagic Scrying caster (eax=spell 0x3B, esi=caster unit, ebx=caster object)
    (0x557E85F9, b"\x8b\x40\x14\x50\x8b\xce\x8b\x53\x08", "push",
     mov_rr("edx", "eax") + mov_rr("eax", "esi"), b"\x8b\xce\x8b\x53\x08", "D  Cosmagic Scrying TE cost"),
    # ---- A. TUnitSpell.AIExecuteCastSpellAction (ebx=spell, esi=hero)
    (0x5577B6ED, b"\x8b\x43\x14\x50\x8b\xce", "push",
     mov_rr("eax", "esi") + mov_rr("edx", "ebx"), b"\x8b\xce", "A  TUnitSpell AI cast TE cost"),

    # ---- B. TE.Execute overrides: charge [TE+0x1C] instead of [spell+0x14]  (in place)
    (0x5579EE33, b"\x8b\x40\x14\x50", "inplace", b"\xff\x73\x1c\x90", None, "B  TFireBarrierTE.Execute charge <- [TE+1C]"),
    (0x5579F1A8, b"\x8b\x40\x14\x50", "inplace", b"\xff\x73\x1c\x90", None, "B  TLevelTerrainTE.Execute charge <- [TE+1C]"),
    (0x5579F533, b"\x8b\x40\x14\x50", "inplace", b"\xff\x73\x1c\x90", None, "B  TRejuvenateTE.Execute charge <- [TE+1C]"),
    (0x557A017E, b"\x8b\x40\x14\x50", "inplace", b"\xff\x73\x1c\x90", None, "B  TWatcherTE.Execute charge <- [TE+1C]"),
    (0x557A06A7, b"\x8b\x40\x14\x50", "inplace", b"\xff\x73\x1c\x90", None, "B  TTornadoTE.Execute charge <- [TE+1C]"),
    (0x557A1414, b"\x8b\x40\x14\x50", "inplace", b"\xff\x76\x1c\x90", None, "B  TVortexTE.Execute charge <- [TE+1C]"),
    (0x557EB074, b"\x8b\x40\x14\x50", "inplace", b"\xff\x76\x1c\x90", None, "B  TWarpPartyTE.Execute charge <- [TE+1C]"),

    # ---- C. spell.ExecuteTE with no TE pointer: charge CastingMana(unit, spell)
    (0x557A2388, b"\x8b\x55\xfc\x8b\x4a\x14\x8b\x55\xf8", "charge",
     b"\x8b\x45\xf8\x8b\x55\xfc", b"\x8b\x55\xf8", "C  TSmokeCloudSpell.ExecuteTE charge"),
    (0x557ED629, b"\x8b\x55\xfc\x8b\x4a\x14\x8b\x55\xf8", "charge",
     b"\x8b\x45\xf8\x8b\x55\xfc", b"\x8b\x55\xf8", "C  TCrusade.ExecuteTE charge"),
    (0x557F0A88, b"\x8b\x4b\x14\x8b\xd6\x8b\xc3", "charge2",
     mov_rr("eax", "esi") + mov_rr("edx", "ebx"), b"\x8b\xd6\x8b\xc3", "C  TWaterMastery.ExecuteTE charge"),
    (0x557ED0E9, b"\x8b\x56\x10\xe8\xd7\xc9\xf8\xff\x8b\x40\x14\x50", "push",
     mov_rr("eax", "ebx") + mov_rr("edx", "esi"), b"", "C  TCallHero.ExecuteTE charge"),

    # ---- E. fast-combat CreateCA raw stores (edx param = caster; hero = [caster+0x4C]) + D. Cosmagic CA
    (0x557E8A78, b"\x8b\x46\x14\x89\x43\x18", "store",
     b"\x8b\x47\x4c" + mov_rr("edx", "esi"), b"\x89\x43\x18", "D  TDispelMagic/Cosmagic combat CA cost"),
    # TUnitSpell.CreateCA (tactical combat, all unit enchantments): eax=CA, esi=caster, ebx=spell
    (0x5577B35C, b"\x8b\x53\x14\x89\x50\x1c", "storeax",
     b"\x8b\x46\x4c" + mov_rr("edx", "ebx"), b"\x89\x50\x1c", "D  TUnitSpell combat CA cost (Enchanter in combat)"),
    (0x557F7C89, b"\x8b\x47\x14\x89\x43\x1c", "store",
     b"\x8b\x45\xfc\x8b\x40\x4c" + mov_rr("edx", "edi"), b"\x89\x43\x1c", "E  TTurnUndead combat CA cost"),
    (0x557F7FFA, b"\x8b\x53\x14\x89\x50\x10", "storeax",
     b"\x8b\x46\x4c" + mov_rr("edx", "ebx"), b"\x89\x50\x10", "E  THighPrayer combat CA cost"),
    (0x557F8615, b"\x8b\x47\x14\x89\x46\x10", "store",
     b"\x8b\x45\xfc\x8b\x40\x4c" + mov_rr("edx", "edi"), b"\x89\x46\x10", "E  TMindDecay combat CA cost"),
    (0x557F89AD, b"\x8b\x46\x14\x89\x43\x10", "store",
     b"\x8b\x45\xfc\x8b\x40\x4c" + mov_rr("edx", "esi"), b"\x89\x43\x10", "E  TSlow combat CA cost"),
    (0x557F8B59, b"\x8b\x47\x14\x89\x43\x10", "store",
     b"\x8b\x45\xfc\x8b\x40\x4c" + mov_rr("edx", "edi"), b"\x89\x43\x10", "E  TEntangle combat CA cost"),
    (0x557FA2DC, b"\x8b\x53\x14\x89\x50\x10", "storeax",
     b"\x8b\x45\xfc\x8b\x40\x4c" + mov_rr("edx", "ebx"), b"\x89\x50\x10", "E  TRecallSpirit combat CA cost"),
    (0x557FA4FC, b"\x8b\x53\x14\x89\x50\x10", "storeax",
     b"\x8b\x45\xfc\x8b\x40\x4c" + mov_rr("edx", "ebx"), b"\x89\x50\x10", "E  TAnimateDead combat CA cost"),
]


def build_site_cave(va, hook, orig, kind, setup, tail):
    back = hook + len(orig)
    a = Asm(va)
    if kind == "push":
        if tail == b"__CITY__":                      # eax=spell, ecx=caster must survive
            a.raw(setup); a.call(CASTINGMANA)
            a.raw(mov_rr("edx", "eax")); a.db(0x59, 0x58)        # pop ecx; pop eax
            a.db(0x52); a.db(0x8a, 0x49, 0x24)                    # push edx; mov cl,[ecx+0x24]
        else:
            a.raw(setup); a.call(CASTINGMANA); a.db(0x50); a.raw(tail)
    elif kind == "store":                             # eax free at the site
        a.raw(setup); a.call(CASTINGMANA); a.raw(tail)
    elif kind == "storeax":                           # eax = the CA, must survive
        a.db(0x50); a.raw(setup); a.call(CASTINGMANA)
        a.raw(mov_rr("edx", "eax")); a.db(0x58); a.raw(tail)     # pop eax; mov [eax+..],edx
    elif kind == "charge":                            # eax = spell (GetSpell result) must survive
        a.db(0x50); a.raw(setup); a.call(CASTINGMANA)
        a.raw(mov_rr("ecx", "eax")); a.db(0x58); a.raw(tail)
    elif kind == "charge2":                           # Water Mastery: eax/edx re-set by the tail
        a.raw(setup); a.call(CASTINGMANA); a.raw(mov_rr("ecx", "eax")); a.raw(tail)
    else:
        raise ValueError(kind)
    a.jmp(back)
    return a.done()


def build_cave_ccsi(va):
    """THero.CanCastSpellInstantly entry: recompute a RAW cost through CastingMana."""
    a = Asm(va)
    a.raw(b"\x8b\xf9\x8b\xf2\x8b\xd8")               # replay: edi=cost esi=id ebx=hero
    a.db(0x85, 0xDB); a.j8(0x74, "done")             # nil hero
    a.raw(b"\xE8\x00\x00\x00\x00")                   # call $+5
    anchor = a.here()
    a.db(0x59)                                       # pop ecx      ; ecx = anchor (runtime)
    a.db(0x81, 0xE9); a.dd(anchor)                   # sub ecx,anchor ; ecx = load delta
    a.db(0x8B, 0x81); a.dd(SPELLCTRL_G)              # mov eax,[ecx+g]
    a.db(0x85, 0xC0); a.j8(0x74, "done")
    a.db(0x8B, 0x80); a.dd(0x84)                     # mov eax,[eax+0x84]  ; TSpellControl
    a.db(0x85, 0xC0); a.j8(0x74, "done")
    a.raw(mov_rr("edx", "esi")); a.call(GETSPELL)    # eax = spell
    a.db(0x85, 0xC0); a.j8(0x74, "done")
    a.db(0x3B, 0x78, 0x14); a.j8(0x75, "done")       # cmp edi,[eax+0x14]; jne done
    a.raw(mov_rr("edx", "eax")); a.raw(mov_rr("eax", "ebx")); a.call(CASTINGMANA)
    a.raw(mov_rr("edi", "eax"))
    a.label("done"); a.jmp(CCSI_RESUME)
    return a.done()


# --------------------------------------------------------------------------- layout
def layout():
    caves, patches, p = [], [], CAVE_LO
    def alloc(n):
        nonlocal p
        va = p; p = (p + n + 3) & ~3; return va
    for hook, orig, kind, setup, tail, desc in SITES:
        if kind == "inplace":
            patches.append((hook, orig, setup, desc)); continue
        # size pass then place
        body = build_site_cave(CAVE_LO, hook, orig, kind, setup, tail)
        va = alloc(len(body)); body = build_site_cave(va, hook, orig, kind, setup, tail)
        caves.append((va, body, desc))
        new = b"\xE9" + struct.pack("<i", va - (hook + 5)) + b"\x90" * (len(orig) - 5)
        assert len(orig) >= 5
        patches.append((hook, orig, new, desc))
    body = build_cave_ccsi(CAVE_LO); va = alloc(len(body)); body = build_cave_ccsi(va)
    caves.append((va, body, "F  CanCastSpellInstantly raw-cost recompute"))
    patches.append((CCSI_HOOK, b"\x8b\xf9\x8b\xf2\x8b\xd8",
                    b"\xE9" + struct.pack("<i", va - (CCSI_HOOK + 5)) + b"\x90",
                    "F  THero.CanCastSpellInstantly entry -> cave_ccsi"))
    assert p <= CAVE_HI, "cave zone overflow"
    for va, body, desc in caves:
        patches.append((va, bytes(len(body)), body, "cave " + desc))
    return caves, patches, p


# --------------------------------------------------------------------------- checks
def relocs(data):
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    rva, size = struct.unpack_from("<II", data, pe + 24 + 96 + 5 * 8)
    p = va2off(data, BASE + rva); end = p + size; out = set()
    while p < end:
        pg, blk = struct.unpack_from("<II", data, p)
        if blk < 8: break
        for k in range(8, blk, 2):
            e = struct.unpack_from("<H", data, p + k)[0]
            if e >> 12 == 3: out.add(BASE + pg + (e & 0xFFF))
        p += blk
    return out


def va2off(data, va):
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    nsec = struct.unpack_from("<H", data, pe + 6)[0]
    opt = struct.unpack_from("<H", data, pe + 20)[0]
    for i in range(nsec):
        o = pe + 24 + opt + i * 40
        vsz, sva, rsz, praw = struct.unpack_from("<IIII", data, o + 8)
        if BASE + sva <= va < BASE + sva + max(vsz, rsz):
            return praw + (va - BASE - sva)
    raise ValueError("VA %08X not in a section" % va)


def disasm(code, va):
    try:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
    except ImportError:
        return "  (capstone not installed)"
    return "\n".join("  %08X  %-20s %-6s %s" % (i.address, i.bytes.hex(" "), i.mnemonic, i.op_str)
                     for i in Cs(CS_ARCH_X86, CS_MODE_32).disasm(code, va))


def write_inplace(path, data):
    """Same-size in-place write: a plain 'wb' open of this dll intermittently fails with EINVAL here."""
    assert len(data) == os.path.getsize(path), "size changed - refusing in-place write"
    with open(path, "r+b") as f:
        f.seek(0); f.write(data); f.flush(); os.fsync(f.fileno())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dll", default=DEFAULT_DLL)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true")
    args = ap.parse_args()
    dll, bak = os.path.abspath(args.dll), bak_path(os.path.abspath(args.dll), BAK_SUFFIX)
    data = bytearray(open(dll, "rb").read())
    caves, patches, end = layout()

    print("target: %s" % dll)
    print("caves 0x%X..0x%X (%d B used of %d), %d hook sites + %d in-place"
          % (CAVE_LO, end, end - CAVE_LO, CAVE_HI - CAVE_LO, len(caves),
             sum(1 for s in SITES if s[2] == "inplace")))
    if args.dis:
        for va, body, desc in caves:
            print("\n%s @0x%X (%d B)\n%s" % (desc, va, len(body), disasm(body, va)))

    state = []
    for va, old, new, desc in patches:
        off = va2off(data, va); cur = bytes(data[off:off + len(old)])
        state.append("patched" if cur == new else "vanilla" if cur == old else "OTHER")
    if args.revert:
        if any(s != "patched" for s in state):
            print("Not (fully) applied - nothing to revert."); return 1
        for va, old, new, desc in patches:
            off = va2off(data, va); data[off:off + len(old)] = old
        write_inplace(dll, data); print("Reverted: hooks restored, caves zeroed."); return 0
    if all(s == "patched" for s in state):
        print("ALL ALREADY PATCHED"); return 0
    bad = [(p, s) for p, s in zip(patches, state) if s == "OTHER"]
    if bad:
        for (va, old, new, desc), s in bad:
            off = va2off(data, va)
            print("MISMATCH @0x%X (%s)\n  exp %s\n  got %s" % (va, desc, old.hex(" ")[:72],
                                                              bytes(data[off:off + len(old)]).hex(" ")[:72]))
        print("Aborting."); return 1
    if any(s == "patched" for s in state):
        print("partial state - aborting."); return 1
    R = relocs(data); hits = []
    for va, old, new, desc in patches:
        hits += [r for r in R if va - 3 <= r < va + len(new)]
    if hits:
        print("RELOC INTERSECT: %s" % ", ".join("%08X" % h for h in sorted(set(hits)))); return 1
    print("no .reloc entry touches any hook window or cave byte.")
    for va, old, new, desc in patches:
        print("  [%-7s] %08X  %s" % (state[patches.index((va, old, new, desc))], va, desc))
    if not args.apply:
        print("\nDry run OK. Re-run with --apply to write."); return 0
    if not os.path.exists(bak):
        shutil.copyfile(dll, bak); print("Backup: %s" % bak)
    for va, old, new, desc in patches:
        off = va2off(data, va); data[off:off + len(new)] = new
    write_inplace(dll, data)
    print("AoWEPACK.dll patched: %d sites, %d caves." % (len(patches) - len(caves), len(caves)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
