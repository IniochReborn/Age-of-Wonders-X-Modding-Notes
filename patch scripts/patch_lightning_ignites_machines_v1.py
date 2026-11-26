#!/usr/bin/env python3
"""
Lightning damage can set MACHINES on fire (AoWEPACK.dll, 2026-09-13).  Ported from BXL's
Ziggurat build_lightning_ignites.py (his was untested in game); mechanism identical.

Machines (TUnit.GetUnitType == 2) are stun-immune: in TAbstractUnit.ExecuteDamageEffectsRole
@0x55781BA4 the lightning branch tests the unit type and, for a machine, jumps straight to the
next branch with nothing applied.  Now a machine that is not Fire-immune (ability 7) takes the
very same roll a creature takes for Stunned (our existing roll cave @0x5580FC00: power 6 vs
Resistance, Lightning Protection bonus applies, Lightning Immunity (ability 9) still exits), and
on success the effect bitset gets the FIRE bit (0x0001) instead of the STUN bit (0x0004).
Downstream TAbstractUnit.ExecuteCombatDamageEffects @0x55781F0D turns bit 0 into
ExpandAbility(0x7F Burning) (+ RemoveAbility(0x5F Frozen)) - the normal Burning status, which
ticks fire damage on following turns.  No extra fire damage is dealt on the hit itself, and
no new random draw is made.  Covers melee, ranged, combat spells and auto-resolve (TDamageCA
+ TFastCombatUnit share the same virtuals).

Vanilla branch (verified identical in the 410 dll):
  55781C56  call [edx+0x114]          ; GetUnitType -> AL (byte! upper EAX holds a pointer)
  55781C5C  cmp al,2 / je 0x55781CAB / mov edx,9     <- B1 window (9 B): the dead exit
  55781C65  ... GetAbilityEnabled(9) ... roll ...
  55781CA0  mov ax,[0x55781E14]       ; 0x0004 (has a .reloc entry at 0x55781CA2 - NOT hookable)
  55781CA6  or ax,bp / mov ebp,eax    <- B2 window (5 B)
  55781CAB  test si,0x10              ; next branch

Caves (PIC, push-free - the function keeps live values at [esp..esp+4]):
  B1: clear mark bit 15 of SI (SI = surviving damage-type set, bits 10..15 unused);
      if AL==2 (machine): if GetAbilityEnabled(7 Fire Immunity) -> dead exit; else set mark;
      replay `mov edx,9`; jmp 0x55781C65.
  B2: if mark set -> ax := 1 (fire) else keep ax (=4 stun); replay or ax,bp / mov ebp,eax;
      jmp 0x55781CAB.
Dry-run default; --apply; --revert; --dll.  Backup: AoWEPACK.dll.bak_lightning_ignites
"""
import argparse, os, shutil, struct, sys
from bakpath import game_dir, game_file   # game folder = AOW_GAME_DIR or parent of patch scripts (2026-09-20)

DEFAULT_DLL = game_file(r"AoWEPACK.dll")
BAK_SUFFIX = ".bak_lightning_ignites"
from bakpath import bak_path   # backups live in <game>\backup\ (2026-09-17)
BASE, FILE_DELTA = 0x55700000, 0x55700C00
HOOK1, HOOK1_ORIG, RESUME1 = 0x55781C5C, bytes.fromhex("3c02744bba09000000"), 0x55781C65
HOOK2, HOOK2_ORIG, RESUME2 = 0x55781CA6, bytes.fromhex("660bc58be8"), 0x55781CAB
DEAD_EXIT = 0x55781CAB
VA_FIRE_BIT, VA_LIGHTNING_BIT = 0x55781E10, 0x55781E14
UT_MACHINE, AB_FIRE_IMMUNITY, SLOT_GETABENABLED = 2, 7, 0x148
MARK = 0x8000
CAVE_LO, CAVE_HI = 0x55813910, 0x55813B80

class Asm:
    def __init__(self, base): self.base = base; self.buf = bytearray(); self.labels = {}; self.fix8 = []
    def here(self): return self.base + len(self.buf)
    def label(self, n): self.labels[n] = self.here()
    def db(self, *bs): self.buf += bytes(bs)
    def jmp32(self, t): self.db(0xE9); self.buf += (t-(self.here()+4)).to_bytes(4, 'little', signed=True)
    def j8(self, op, lab): self.db(op); self.fix8.append((len(self.buf), lab)); self.db(0)
    def done(self):
        for off, lab in self.fix8:
            rel = self.labels[lab]-(self.base+off+1); assert -128 <= rel <= 127; self.buf[off] = rel & 0xFF
        return bytes(self.buf)

def build(fire_bit):
    a = Asm(CAVE_LO)
    a.label('b1')
    a.db(0x66, 0x81, 0xE6); a.buf += struct.pack("<H", (~MARK) & 0xFFFF)   # and si, 0x7FFF
    a.db(0x3C, UT_MACHINE); a.j8(0x75, 'normal')                          # cmp al,2 ; jne normal
    a.db(0xBA); a.buf += struct.pack("<I", AB_FIRE_IMMUNITY)              # mov edx, 7
    a.db(0x8B, 0xC3); a.db(0x8B, 0x08); a.db(0xFF, 0x91); a.buf += struct.pack("<I", SLOT_GETABENABLED)   # GetAbilityEnabled(7)
    a.db(0x84, 0xC0); a.j8(0x75, 'skip')                                  # fire-immune machine -> dead exit
    a.db(0x66, 0x81, 0xCE); a.buf += struct.pack("<H", MARK)              # or si, 0x8000  (mark: success = burning)
    a.label('normal')
    a.db(0xBA, 0x09, 0x00, 0x00, 0x00)                                    # replay: mov edx,9
    a.jmp32(RESUME1)
    a.label('skip'); a.jmp32(DEAD_EXIT)
    a.label('b2')
    a.db(0x66, 0xF7, 0xC6); a.buf += struct.pack("<H", MARK)              # test si, 0x8000
    a.j8(0x74, 'keep')
    a.db(0x66, 0xB8); a.buf += struct.pack("<H", fire_bit)                # mov ax, FIRE_BIT (16-bit, keep EAX high half like vanilla)
    a.label('keep')
    a.db(0x66, 0x0B, 0xC5); a.db(0x8B, 0xE8)                              # replay: or ax,bp ; mov ebp,eax
    a.jmp32(RESUME2)
    return a.done(), a.labels

def write_inplace(path, data):
    assert len(data) == os.path.getsize(path)
    with open(path, "r+b") as f: f.seek(0); f.write(data); f.flush(); os.fsync(f.fileno())

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--dll", default=DEFAULT_DLL)
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    args = ap.parse_args(); dll, bak = args.dll, bak_path(args.dll, BAK_SUFFIX)
    d = bytearray(open(dll, "rb").read())
    fire_bit = struct.unpack_from("<H", d, VA_FIRE_BIT - FILE_DELTA)[0]; stun_bit = struct.unpack_from("<H", d, VA_LIGHTNING_BIT - FILE_DELTA)[0]
    assert (fire_bit, stun_bit) == (1, 4), (fire_bit, stun_bit)
    cave, L = build(fire_bit); assert CAVE_LO + len(cave) <= CAVE_HI
    def rel(src, dst): return b"\xE9" + struct.pack("<i", dst - (src + 5))
    patches = [
        (CAVE_LO, bytes(len(cave)), cave, f"caves b1 @{L['b1']:#x} / b2 @{L['b2']:#x} ({len(cave)} B)"),
        (HOOK1, HOOK1_ORIG, rel(HOOK1, L['b1']) + b"\x90" * 4, "lightning branch machine exit -> b1"),
        (HOOK2, HOOK2_ORIG, rel(HOOK2, L['b2']), "stun-bit deposit -> b2"),
    ]
    try:
        import pefile
        relocs = [e.rva + BASE for blk in pefile.PE(dll).DIRECTORY_ENTRY_BASERELOC for e in blk.entries if e.type]
        for va, old, new, desc in patches:
            hit = [hex(r) for r in relocs if va - 3 <= r < va + len(new)]
            assert not hit, f"reloc inside {desc}: {hit}"
    except ImportError: print("(pefile missing - reloc check skipped)")
    print(f"target: {dll}\n" + "\n".join(f"  {desc}" for _, _, _, desc in patches))
    if args.revert:
        if not all(bytes(d[va-FILE_DELTA:va-FILE_DELTA+len(new)]) == new for va, old, new, _ in patches): print("not applied"); return 1
        for va, old, new, _ in patches: d[va-FILE_DELTA:va-FILE_DELTA+len(old)] = old
        write_inplace(dll, d); print("Reverted."); return 0
    ok = True; applied = 0
    for va, old, new, desc in patches:
        cur = bytes(d[va-FILE_DELTA:va-FILE_DELTA+len(old)])
        if cur == new: applied += 1
        elif cur != old: print(f"MISMATCH @{va:#x} ({desc}): exp {old.hex()} got {cur.hex()}"); ok = False
    if applied == len(patches): print("ALL ALREADY PATCHED"); return 0
    if not ok or applied: print("Aborting (mismatch/partial)."); return 1
    if not args.apply: print("\nDry run OK. Re-run with --apply to write."); return 0
    if not os.path.exists(bak): shutil.copyfile(dll, bak); print(f"Backup: {bak}")
    for va, old, new, desc in patches: d[va-FILE_DELTA:va-FILE_DELTA+len(new)] = new; print("Patched:", desc)
    write_inplace(dll, d); print("AoWEPACK.dll patched successfully."); return 0

if __name__ == "__main__":
    sys.exit(main())
