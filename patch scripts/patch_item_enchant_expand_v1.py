#!/usr/bin/env python3
r"""
Editor: adding an ENCHANTMENT ability to an item no longer errors (AoWEPACK.dll, 2026-10-30).
Companion of patch_item_enchant_abilities_v1 (runtime side).

User: "trying to add enchantment abilities to items in the editor causes errors".
AoWDevX TAbilitySelectionDlg Add (0x410690): `call [item VMT+0x94]` = TAbilityOwner.ExpandAbility(id) on the edited
item copy -> ability VMT+0xD0 Expand(owner).  TUnitEnchantmentAbility.Expand 0x55765894 asserts the owner IsClass
TAbstractUnit (assert line 0xB45F) and unit id > 0, then builds the per-unit enchantment record - impossible for an
item.  (Remove 0x557659A8 already handles a missing record: clears the bit.)
Fix: prologue 0x55765894 (7 B `push ebx/esi/edi/ebp/ecx; mov edi,edx`) -> cave: owner not a TAbstractUnit ->
TAbility.Expand 0x5574E90C (= TAdjustableAbility's: owner VMT+0x50 SetAb(id, True), returns True) - exactly what
every non-enchantment item ability gets; units -> original code.  Covers all TUnitEnchantmentAbility subclasses
(shared Expand).  Zone AoWEPACK 0x55848C00..0x55848C80 ('IEX1'), PIC.  Dry-run default; --apply / --revert.
Backup AoWEPACK.dll.bak_itemenchexp.
"""
import os, shutil, struct, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DLL, BASE = game_file("AoWEPACK.dll"), 0x55700000
SITE, ORIG, BACK = 0x55765894, bytes.fromhex("53565755518bfa"), 0x5576589B
BASE_EXPAND, ISCLASS, TAU_VAR = 0x5574E90C, 0x557010C0, 0x55710700
ZONE, ZONE_END = 0x55848C00, 0x55848C80
CODE = ZONE + 0x10
MAGIC = b"IEX1"


def build():
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    g = 0x11111111
    for _ in range(4):
        src = f"""
    push eax
    push edx
    call {g:#x}
    pop  ecx
    sub  ecx, {g:#x}
    mov  eax, edx
    mov  edx, dword ptr [ecx + {TAU_VAR:#x}]
    call {ISCLASS:#x}
    test al, al
    pop  edx
    pop  eax
    jnz  unit
    jmp  {BASE_EXPAND:#x}
unit:
    push ebx
    push esi
    push edi
    push ebp
    push ecx
    mov  edi, edx
    jmp  {BACK:#x}
"""
        code = bytes(ks.asm(src, CODE)[0])
        ci = code.find(b"\x59\x81\xe9")
        if CODE + ci == g:
            break
        g = CODE + ci
    assert struct.unpack_from("<i", code, ci - 4)[0] == 0
    z = bytearray(ZONE_END - ZONE)
    z[0:4] = MAGIC
    z[0x10:0x10 + len(code)] = code
    return bytes(z)


def main():
    import pefile
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    d = open(DLL, "rb").read()
    pe = pefile.PE(data=d)
    off = lambda va: pe.get_offset_from_rva(va - BASE)  # noqa: E731
    zone = build()
    hook = b"\xe9" + struct.pack("<i", CODE - (SITE + 5)) + b"\x90\x90"
    P = [(SITE, ORIG, hook), (ZONE, bytes(len(zone)), zone)]
    rl = {BASE + e.rva for blk in getattr(pe, "DIRECTORY_ENTRY_BASERELOC", []) for e in blk.entries if e.type == 3}
    bad = [hex(r) for r in rl if any(s - 3 <= r < s + len(o) for s, o, _ in P)]
    sts = []
    for s, o, n in P:
        c = d[off(s):off(s) + len(o)]
        sts.append("vanilla" if c == o else "ours" if c == n else "OTHER")
    print("site %#x %s | zone %s | relocs %s" % (SITE, sts[0], sts[1], bad or "none"))
    if "OTHER" in sts or bad or len(set(sts)) != 1:
        print("ABORT"); return 1
    want = "vanilla" if revert else "ours"
    if sts[0] == want:
        print("already %s" % ("reverted" if revert else "applied")); return 0
    if not apply and not revert:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    r = subprocess.run(["tasklist"], capture_output=True, text=True).stdout
    if "AoWx.exe" in r or "AoWDevX.exe" in r:
        print("game/editor running - close it first"); return 1
    bak = bak_path(DLL, ".bak_itemenchexp")
    if not revert and not os.path.exists(bak):
        shutil.copy2(DLL, bak); print("backup ->", bak)
    with open(DLL, "r+b") as f:
        for s, o, n in reversed(P):
            f.seek(off(s)); f.write(o if revert else n)
    d2 = open(DLL, "rb").read()
    assert all(d2[off(s):off(s) + len(o)] == (o if revert else n) for s, o, n in P)
    print("reverted" if revert else "written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
