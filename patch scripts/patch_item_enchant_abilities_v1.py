#!/usr/bin/env python3
r"""
Enchantment abilities on items work instead of crashing (AoWEPACK.dll, 2026-10-30).

User: the editor lets any ability be enabled for item selection types; an ENCHANTMENT ability placed on an item
bugs.  Wanted: the hero/leader wearing it (or holding it, Use type) gets the enchantment while equipped/held, with
no upkeep; already having / later gaining the same enchantment must not break (may list twice).

Cause: every enchantment ability is a TUnitEnchantmentAbility (VMT 0x55722364; ids 0x22 0x5E 0x5F 0x7E 0x84
0x98..0x9E 0xA0..0xA7 0xA9, + AoWx clones).  Its state is a per-owner data record (Expand creates it ON THE UNIT,
with the TUnitEnchantment that carries caster/upkeep at [rec+0x10]); an item only has the ability BIT.  Unit-side
paths test "has ability" with GetAbilityEnabled (unit VMT+0x148, which includes worn/held items), then fetch the
record from the unit and dereference it unchecked -> AV:
  RegisterEnchantments (hero Activate: load/placement) 0x5577F2DC, UnregisterEnchantments (Deactivate/Killed)
  0x5577F368, THero.GetFace (0x7E) 0x557887E8, Summoned source lookup 0x5577FC9C, Earth/Fire/Life/Death Mastery
  resets 0x55780968 / 0x55780A1C / 0x55780ABC / 0x55780D1C;
and GetSourceName (unit window ListAbilityInfo with owner = the item, combat panel CreateTCAbList) reads the
record with no check at all: base 0x557657B9 and the Blessed / StoneSkin / FireProtection overrides.

Fix (deterministic, no new objects):
  A. those 8 gates: `call [ecx+0x148]` -> `call [ecx+0x4C]` (GetAbSet = the unit's OWN bits; own bit <=> own record),
     so registration / face / mastery / summoned logic only ever handles the unit's own (spell) copy.
  B. base GetSourceName @0x557657B7: nil record -> source text = the granting item's name ([item+0x18], what
     TItem.GetOwnerName returns); the owner is the item itself, or a unit -> its owner-finder VMT+0x154(id);
     otherwise the vanilla "unknown" branch.
  C. the 3 overrides: nil record -> their own fallback (= base GetSourceName, now safe).
  D. recasting: TBless/TDarkGift/TEnchantWeapon/TFreeMovement/TFury/THaste/TLiquidForm/TStoneSkin.ValidTargetUnit
     refused a target that has the enchantment through an item -> same 0x148 -> 0x4C swap, so a spell can still
     be cast on top (it then gets its own record/upkeep and is dispellable; the item copy survives a dispel).
The item copy never gets a TUnitEnchantment, so it is never registered -> no upkeep and not dispellable; its
effect comes from the normal item-inclusive ability checks.
Zone AoWEPACK 0x55848100..0x55848400 ('IEN1').  PIC (call/pop delta).  Dry-run default; --apply / --revert.
Backup AoWEPACK.dll.bak_itemench.
"""
import os, shutil, struct, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DLL = game_file("AoWEPACK.dll")
BASE = 0x55700000
MAGIC = b"IEN1"
ZONE, ZONE_END = 0x55848100, 0x55848400
GATES = [0x5577F2DC, 0x5577F368, 0x557887E8, 0x5577FC9C, 0x55780968, 0x55780A1C, 0x55780ABC, 0x55780D1C,
         0x557E8396, 0x557E8502, 0x557E6EEA, 0x557E7266, 0x557E70D6, 0x557E6C12, 0x557E814A, 0x557E6D7E]
G_OLD, G_NEW = bytes.fromhex("ff9148010000"), bytes.fromhex("ff914c000000")
GSN_SITE, GSN_ORIG, GSN_BACK, GSN_DONE, GSN_UNK = 0x557657B7, bytes.fromhex("8bd88b4310"), 0x557657BC, 0x55765859, 0x55765842
OVR = [(0x557BB618, 0x557BB63B), (0x557BAEEC, 0x557BAF0F), (0x557BB004, 0x557BB027)]   # (site, fallback)
OVR_ORIG = bytes.fromhex("8b401080780cfe")
TITEM_VMT, TAU_CLASSVAR = 0x5570FAFC, 0x55710700
ISCLASS, LSTRASG = 0x557010C0, 0x55701158
GSN_CODE = ZONE + 0x10
OVR_CODE = [ZONE + 0x100 + 0x20 * i for i in range(3)]


def build():
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    H = lambda v: "0x%X" % v  # noqa: E731
    g = 0x11111111                   # delta anchor (address right after `call g`), solved below
    tmpl = f"""
    test eax, eax
    jz   nilrec
    mov  ebx, eax
    mov  eax, dword ptr [ebx + 0x10]
    jmp  {H(GSN_BACK)}
    nop
    nop
nilrec:
    call {{G}}
    pop  ecx
    sub  ecx, {{G}}
    lea  edx, [ecx + {H(TITEM_VMT)}]
    mov  eax, edi
    test eax, eax
    jz   unk
    cmp  dword ptr [eax], edx
    je   isitem
    push ecx
    mov  edx, dword ptr [ecx + {H(TAU_CLASSVAR)}]
    call {H(ISCLASS)}
    pop  ecx
    test al, al
    jz   unk
    push ecx
    mov  edx, dword ptr [ebx + 0xC]
    mov  eax, edi
    mov  ecx, dword ptr [eax]
    call dword ptr [ecx + 0x154]
    pop  ecx
    test eax, eax
    jz   unk
    lea  edx, [ecx + {H(TITEM_VMT)}]
    cmp  dword ptr [eax], edx
    jne  unk
isitem:
    mov  edx, dword ptr [eax + 0x18]
    mov  eax, esi
    call {H(LSTRASG)}
    jmp  {H(GSN_DONE)}
unk:
    jmp  {H(GSN_UNK)}
"""
    for _ in range(3):
        code = bytes(ks.asm(tmpl.replace("{G}", H(g)), GSN_CODE)[0])
        ci = code.find(b"\x59\x81\xe9")          # pop ecx / sub ecx, imm32  (right after the anchor call)
        assert ci > 0
        new_g = GSN_CODE + ci
        if new_g == g:
            break
        g = new_g
    assert struct.unpack_from("<I", code, ci + 3)[0] == g
    assert struct.unpack_from("<i", code, ci - 4)[0] == 0      # call g == call $+5
    z = bytearray(ZONE_END - ZONE)
    z[0:4] = MAGIC
    z[0x10:0x10 + len(code)] = code
    assert 0x10 + len(code) <= 0x100
    for (site, fb), at in zip(OVR, OVR_CODE):
        oc = bytes(ks.asm(f"""
    test eax, eax
    jz   {H(fb)}
    mov  eax, dword ptr [eax + 0x10]
    cmp  byte ptr [eax + 0xC], 0xFE
    jne  {H(fb)}
    jmp  {H(site + 9)}
""", at)[0])
        assert len(oc) <= 0x20
        z[at - ZONE:at - ZONE + len(oc)] = oc
    return bytes(z)


def jmp5(at, tgt, pad):
    return b"\xe9" + struct.pack("<i", tgt - (at + 5)) + b"\x90" * pad


def game_running():
    try:
        r = subprocess.run(["tasklist"], capture_output=True, text=True).stdout
        return "AoWx.exe" in r or "AoWDevX.exe" in r
    except Exception:
        return False


def main():
    import pefile
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    d = open(DLL, "rb").read()
    pe = pefile.PE(data=d)
    off = lambda va: pe.get_offset_from_rva(va - BASE)  # noqa: E731
    zone = build()
    P = [(a, G_OLD, G_NEW) for a in GATES]
    P.append((GSN_SITE, GSN_ORIG, jmp5(GSN_SITE, GSN_CODE, 0)))
    P += [(s, OVR_ORIG, jmp5(s, at, 2)) for (s, _), at in zip(OVR, OVR_CODE)]
    P.append((ZONE, bytes(len(zone)), zone))
    rl = set()
    for blk in getattr(pe, "DIRECTORY_ENTRY_BASERELOC", []):
        for e in blk.entries:
            if e.type == 3:
                rl.add(BASE + e.rva)
    bad = [hex(r) for r in rl if any(s - 3 <= r < s + len(o) for s, o, _ in P)]
    sts = []
    for s, o, n in P:
        c = d[off(s):off(s) + len(o)]
        sts.append("vanilla" if c == o else "ours" if c == n else "OTHER")
    for (s, o, n), st in zip(P, sts):
        if st != sts[0] or s in (GSN_SITE, ZONE):
            print("  %#x %s" % (s, st))
    print("%d sites, states %s | relocs %s" % (len(P), sorted(set(sts)), bad or "none"))
    if "OTHER" in sts or bad or len(set(sts)) != 1:
        print("ABORT (mixed/foreign state)"); return 1
    want = "vanilla" if revert else "ours"
    if sts[0] == want:
        print("already %s" % ("reverted" if revert else "applied")); return 0
    if not apply and not revert:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if game_running():
        print("AoWx.exe / AoWDevX.exe is running - close it first"); return 1
    bak = bak_path(DLL, ".bak_itemench")
    if not revert and not os.path.exists(bak):
        shutil.copy2(DLL, bak); print("backup ->", bak)
    try:
        with open(DLL, "r+b") as f:                 # in-place (house rule); zone first on apply
            for s, o, n in reversed(P):
                f.seek(off(s)); f.write(o if revert else n)
    except PermissionError:
        print("LOCKED"); return 1
    d2 = open(DLL, "rb").read()
    assert all(d2[off(s):off(s) + len(o)] == (o if revert else n) for s, o, n in P)
    print("reverted" if revert else "written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
