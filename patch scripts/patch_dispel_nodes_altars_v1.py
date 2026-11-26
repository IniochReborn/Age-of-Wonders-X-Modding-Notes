#!/usr/bin/env python3
r"""
Dispel Magic boosts NODES and ALTARS (2026-10-19).  User: "nodes produce extra mana income if a unit standing on it
has the Dispel Magic ability: extra = Dispel Magic level x 2, not stacking (highest level among the units on the node);
all nodes (regular and elemental).  Altars: charge time reduced by turns equal to the Dispel Magic level."

RE (AoWEPACK, preferred base 0x55700000):
  * Realm power = TPlayerMagicControl.GetPower 0x5577CA00 = sum over registered power sources [mc+0x40] of
    source VMT+0x50; nodes register a TPlayerStructurePowerSource (Power 0x55761B54 = structure VMT+0x1F8 GetPower).
    The same structure VMT+0x1F8 feeds GetNetPower 0x5577CEC4 -> GetNetPowerToMana / ToResearch (per-turn credit in
    NewTurn) AND the UI (magic window totals, node info) -> one hook changes income and display consistently.
      TProductionPlace.GetPower 0x557BE468 (elemental nodes Fire/Earth/Death/Life/Water/Air + AoWx TRandomNode):
        owner>0, not razed (VMT+0x150), not 0x5575F008 -> 10 + 5*sphere picks;  TPowerNode GetPower 0x557D03C8 -> 10.
    Node power is split into mana/research by the realm's power slider (no separate "node mana").  The bonus is
    added to the node's POWER, so it shows as node income everywhere and becomes +2L mana at a full-mana slider.
  * Dispel Magic = ability 0x3C, TDispelMagicAbility.GetLevel 0x5576CEFC (record [rec+0xD], no record & bit -> 1,
    no bit -> 0).  Per-unit level = unit VMT+0x144 GetAbilityLevel(eax=unit, edx=0x3C) (THero override 0x5578831C
    is item-aware).
  * Altars (TAltar 0x557CE7C4 + Fire/Ice/Lightning/Life/Death/Pestilence): VMT+0x22C GetRechargeDays 0x557CF1BC
    = 10 (byte); charge counter byte [altar+0x41] (NewDay 0x557CF1E0 increments while != recharge days; use resets
    it to 0); VMT+0x23C TargetMana = (recharge - counter) * 50 = mana needed to fire it early.

Design (hooks = VMT slot repoints only, no code bytes overwritten):
  dmlevel(struct) = highest Dispel Magic level among the units of the army standing on the structure's location hex
    (VMT+0x74/0x78/0x7C x/y/level -> map [0x558E9494] -> grid 0x557020EC -> field 0x557020DC -> army HS 0x55771EB0
    -> [hs+0x1C]) and ONLY if that army's owner [army+0x12] == the structure owner [struct+0x30] >= 0 (allied or
    enemy units standing on someone else's node/altar give nothing; unowned structures give nothing).
  Nodes: slot +0x1F8 of the 8 node VMTs -> wrapper: power = orig; if power > 0: power += 2 * dmlevel.
    (Razed / unowned / blocked nodes produce 0 and stay 0.)
  Altars: slot +0x22C of the 7 altar VMTs -> wrapper: r = max(1, orig - dmlevel); and if the current charge
    counter c = [+0x41] already exceeds r (unit arrived on a partly charged altar) return c (<= orig) so the altar
    simply reads "charged" -> NewDay's != test stops counting and TargetMana = (r - c)*50 never goes negative.
    When the unit leaves, recharge returns to 10 and charging continues from the kept counter.
Deterministic (game state only), editor-safe (no exe addresses; map holder nil -> 0).
Zone AoWEPACK 0x5581F300..0x5581F800 (header 'DMN1'); verified zero + reloc-free.  Slots carry relocs (in-image VAs).
Backup <game>\backup\AoWEPACK.dll.bak_dispelnodes.  Dry run default; --apply / --revert / --dis [dll].
"""
import os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(1, r"C:\Users\<user>\Desktop\Age of Wonders X - Claude\patch scripts")
try:
    from bakpath import bak_path, game_file
    DLL = game_file("AoWEPACK.dll")
except Exception:
    def bak_path(p, s): return p + s
    DLL = r"C:\Users\<user>\Desktop\Age of Wonders X - Claude\AoWEPACK.dll"

D = 0x55700C00
MAGIC = b"DMN1"
ZONE_LO, ZONE_HI = 0x5581F300, 0x5581F530   # 10/19: 0x5581F530+ = patch_ai_site_converge_v3
CODE = ZONE_LO + 0x10
PP_GETPOWER, PN_GETPOWER, ALT_RECHARGE = 0x557BE468, 0x557D03C8, 0x557CF1BC
NODE_VMTS = {0x557BF624: "TFireNode", 0x557BFAE0: "TEarthNode", 0x557BFFA4: "TDeathNode", 0x557C046C: "TLifeNode",
             0x557C092C: "TWaterNode", 0x557C0DF4: "TAirNode", 0x5580B3D8: "TRandomNode", 0x557CFFE4: "TPowerNode"}
ALTAR_VMTS = {0x557CE7C4: "TAltar", 0x557CF5F8: "TAltarOfFire", 0x557CFAF0: "TAltarOfIce",
              0x557D16F4: "TAltarOfLightning", 0x557D1BCC: "TAltarOfLife", 0x557D2094: "TAltarOfDeath",
              0x557D255C: "TAltarOfPestilence"}
MAPHOLD = 0x558E9494
GETGRID, GETFIELD, ARMYHS, GETUNIT = 0x557020EC, 0x557020DC, 0x55771EB0, 0x5578309C
DM_ID = 0x3C
LCAP = 10
POWER_PER_LEVEL = 2          # extra power per Dispel Magic level (fixed in the asm as add eax,eax)

SRC = """
stub_pp:
    push ebx
    mov  ebx, eax
    call {PP}
    jmp  pw_common
stub_pn:
    push ebx
    mov  ebx, eax
    call {PN}
pw_common:
    test eax, eax
    jle  pw_done
    push eax
    mov  eax, ebx
    call dmlevel
    add  eax, eax
    pop  edx
    add  eax, edx
pw_done:
    pop  ebx
    ret
stub_alt:
    push ebx
    push esi
    mov  ebx, eax
    call {ALT}
    movzx esi, al
    mov  eax, ebx
    call dmlevel
    mov  edx, esi
    sub  edx, eax
    cmp  edx, 1
    jge  a_1
    mov  edx, 1
a_1:
    movzx eax, byte ptr [ebx+0x41]
    cmp  eax, edx
    jle  a_2
    cmp  eax, esi
    jg   a_2
    mov  edx, eax
a_2:
    mov  eax, edx
    pop  esi
    pop  ebx
    ret
dmlevel:
    push ebp
    push ebx
    push esi
    push edi
    sub  esp, 0x10
    mov  ebx, eax
    call d_p
d_p:
    pop  ebp
    xor  edi, edi
    movsx eax, byte ptr [ebx+0x30]
    test eax, eax
    jl   d_out
    mov  [esp+0xC], eax
    mov  eax, ebx
    mov  edx, [eax]
    call dword ptr [edx+0x74]
    movsx eax, al
    mov  [esp], eax
    mov  eax, ebx
    mov  edx, [eax]
    call dword ptr [edx+0x78]
    movsx eax, al
    mov  [esp+4], eax
    mov  eax, ebx
    mov  edx, [eax]
    call dword ptr [edx+0x7c]
    movsx eax, al
    mov  [esp+8], eax
    mov  eax, dword ptr [ebp + {KMAP}]
    test eax, eax
    jz   d_out
    mov  eax, [eax]
    test eax, eax
    jz   d_out
    mov  eax, [eax+0x10]
    test eax, eax
    jz   d_out
    mov  edx, [esp+8]
    call {GETGRID}
    test eax, eax
    jz   d_out
    mov  edx, [esp]
    test edx, edx
    jl   d_out
    cmp  edx, [eax+0xC]
    jge  d_out
    mov  ecx, [esp+4]
    test ecx, ecx
    jl   d_out
    cmp  ecx, [eax+0x10]
    jge  d_out
    call {GETFIELD}
    test eax, eax
    jz   d_out
    call {ARMYHS}
    test eax, eax
    jz   d_out
    mov  esi, [eax+0x1C]
    test esi, esi
    jz   d_out
    movsx edx, byte ptr [esi+0x12]
    cmp  edx, [esp+0xC]
    jne  d_out
    xor  ebx, ebx
d_ul:
    mov  eax, esi
    mov  edx, [eax]
    call dword ptr [edx+0x54]
    cmp  ebx, eax
    jge  d_out
    mov  eax, esi
    mov  edx, ebx
    call {GETUNIT}
    inc  ebx
    test eax, eax
    jz   d_ul
    mov  edx, {DM}
    mov  ecx, [eax]
    call dword ptr [ecx+0x144]
    test eax, eax
    jle  d_ul
    cmp  eax, {LCAP}
    jle  d_cap
    mov  eax, {LCAP}
d_cap:
    cmp  eax, edi
    jle  d_ul
    mov  edi, eax
    jmp  d_ul
d_out:
    mov  eax, edi
    add  esp, 0x10
    pop  edi
    pop  esi
    pop  ebx
    pop  ebp
    ret
"""
LABELS = ("stub_pp", "stub_pn", "pw_common", "pw_done", "stub_alt", "a_1", "a_2", "dmlevel", "d_p", "d_ul",
          "d_cap", "d_out")


def asm(src, addr):
    enc, _ = Ks(KS_ARCH_X86, KS_MODE_32).asm(src, addr)
    return bytes(enc)


def label_addrs(src, addr):
    """Exact label VAs: assemble with a marker `int3` inserted after each label one at a time is costly; instead
    assemble the full source with every label followed by a unique `mov eax, imm` sentinel? -> simpler: keystone
    resolves labels; we measure by assembling the prefix (forward refs use the same disp sizes because every
    branch target sits within the same short/near range class, verified by the length assert in build())."""
    out = {}
    lines = src.split("\n")
    for i, ln in enumerate(lines):
        s = ln.strip()
        if s.endswith(":") and s[:-1] in LABELS:
            out[s[:-1]] = None
    # robust method: append `lbl_probe: ` jumps — use keystone symbol resolution via a trailing table of
    # `.long label` entries
    probe = src + "\n" + "\n".join(".long %s" % l for l in LABELS)
    b = asm(probe, addr)
    tbl = b[-4 * len(LABELS):]
    for k, l in enumerate(LABELS):
        out[l] = struct.unpack_from("<I", tbl, 4 * k)[0]
    return out


def build():
    big = 0x7FFFFF00
    fmt = dict(PP=PP_GETPOWER, PN=PN_GETPOWER, ALT=ALT_RECHARGE, GETGRID=GETGRID, GETFIELD=GETFIELD,
               ARMYHS=ARMYHS, GETUNIT=GETUNIT, DM=DM_ID, LCAP=LCAP)
    s0 = SRC.format(KMAP=big, **fmt)
    lab = label_addrs(s0, CODE)
    pop_va = lab["d_p"]
    s1 = SRC.format(KMAP=(MAPHOLD - pop_va) & 0xFFFFFFFF, **fmt)
    c0, c1 = asm(s0, CODE), asm(s1, CODE)
    assert len(c0) == len(c1)
    assert label_addrs(s1, CODE) == lab
    assert CODE + len(c1) <= ZONE_HI
    zone = MAGIC + bytes(CODE - ZONE_LO - len(MAGIC)) + c1
    return zone, lab


def edits():
    z, lab = build()
    E = [(ZONE_LO, bytes(len(z)), z, "DMN cave")]
    for v, n in NODE_VMTS.items():
        orig = PN_GETPOWER if n == "TPowerNode" else PP_GETPOWER
        tgt = lab["stub_pn"] if n == "TPowerNode" else lab["stub_pp"]
        E.append((v + 0x1F8, struct.pack("<I", orig), struct.pack("<I", tgt), "%s.GetPower slot" % n))
    for v, n in ALTAR_VMTS.items():
        E.append((v + 0x22C, struct.pack("<I", ALT_RECHARGE), struct.pack("<I", lab["stub_alt"]),
                  "%s.GetRechargeDays slot" % n))
    return E, lab


def relocs(dll_bytes):
    import pefile
    pe = pefile.PE(data=dll_bytes)
    base = pe.OPTIONAL_HEADER.ImageBase
    return set(base + e.rva for b in pe.DIRECTORY_ENTRY_BASERELOC for e in b.entries if e.type)


def main(dll=None):
    dll = dll or DLL
    ap, rv = "--apply" in sys.argv, "--revert" in sys.argv
    d = bytearray(open(dll, "rb").read())
    E, lab = edits()
    if "--dis" in sys.argv:
        import capstone
        z = E[0][2]
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(z[CODE - ZONE_LO:], CODE):
            print("  %08X  %-20s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    rel = relocs(bytes(d))
    bad = [hex(r) for r in rel if ZONE_LO - 3 <= r < ZONE_HI]
    assert not bad, "reloc in zone: %s" % bad
    for va, ob, nb, nm in E[1:]:
        assert va in rel, "slot %s has no reloc?" % nm
    tail = bytes(d[ZONE_LO + len(E[0][2]) - D:ZONE_HI - D])
    st = []
    for va, ob, nb, nm in E:
        c = bytes(d[va - D:va - D + len(nb)])
        s = "original" if c == ob else "applied" if c == nb else "FOREIGN"
        st.append(s)
        print("  %-36s @0x%08X  %s" % (nm, va, s))
    print("  stubs: node 0x%08X / power node 0x%08X / altar 0x%08X / dmlevel 0x%08X; code %d B; zone tail free: %s"
          % (lab["stub_pp"], lab["stub_pn"], lab["stub_alt"], lab["dmlevel"], len(E[0][2]) - 0x10, not any(tail)))
    if "FOREIGN" in st or any(tail):
        print("FOREIGN - refusing")
        return 1
    if rv:
        if all(s == "original" for s in st):
            print("not applied")
            return 0
        for va, ob, nb, _ in E:
            d[va - D:va - D + len(nb)] = ob
        with open(dll, "r+b") as f:
            f.seek(0); f.write(bytes(d))
        print("reverted")
        return 0
    if not ap:
        print("dry run (--apply / --revert)")
        return 0
    if all(s == "applied" for s in st):
        print("already applied")
        return 0
    if "original" in st and "applied" in st:
        print("partially applied - refusing (revert first)")
        return 1
    bk = bak_path(dll, ".bak_dispelnodes")
    if not os.path.isfile(bk):
        shutil.copy2(dll, bk)
        print("backup ->", bk)
    for va, ob, nb, _ in E:
        d[va - D:va - D + len(nb)] = nb
    with open(dll, "r+b") as f:
        f.seek(0); f.write(bytes(d))
    back = open(dll, "rb").read()
    for va, ob, nb, _ in E:
        assert back[va - D:va - D + len(nb)] == nb
    print("written and verified: nodes +2 power per Dispel Magic level, altars recharge 1 day faster per level")
    return 0


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    sys.exit(main(a[0] if a else None))
