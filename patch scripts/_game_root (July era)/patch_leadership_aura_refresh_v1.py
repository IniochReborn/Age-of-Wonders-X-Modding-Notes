#!/usr/bin/env python3
"""
Leadership aura instant-refresh for AoWEPACK.dll (2026-07-19).

Problem: after buying a Leadership level in the hero level-up UI, party units
only get the new aura bonus when the army next updates (move / next turn).

Fix: hook the level-up completion event. THeroUpgradeTE.Execute applies the
stat deltas + abilities and then clears the upgrade-pending flag [hero+0x54]
(the same flag that locks the player out of re-entering the level-up UI).
We repoint its `call TAbilityOwner.UpdateDefaultAbilities` @0x557854E0 to a
cave that runs the original call, then recomputes the aura immediately:

    army = [hero+0x4]                 (hero = EDI at the hook site)
    if army && IsClass(army, TArmy):  (vanilla's own guard from MovedTo -
        TArmy.UpdateFormation(army)    container isn't always an army)

TArmy.UpdateFormation @0x5578D034 (EAX=army) is the engine's sole aura
recomputer (sets/resets external Leadership levels + morale) - the exact
routine that runs on move/turn, so behaviour is identical, just immediate.
MP-safe: turn events execute on every peer.

PIC: classref global read is call/pop delta-fixed; calls are rel32.
Cave @0x5580E120 (file 0x10D520, zeros verified). Dry-run default; --apply.
Backup: AoWEPACK.dll.bak_leadership_aura
"""
import shutil, sys, struct, os

GAME = os.path.dirname(os.path.abspath(__file__))
DLL  = os.path.join(GAME, "AoWEPACK.dll")
BAK  = DLL + ".bak_leadership_aura"
FILE_DELTA = 0x55700C00

UDA        = 0x5574F518          # TAbilityOwner.UpdateDefaultAbilities
HOOK       = 0x557854E0          # call UDA inside THeroUpgradeTE.Execute
NEXT_BYTES = bytes.fromhex("c6475400")   # mov byte [edi+0x54],0 (must follow hook)
CLASSREF   = 0x557130AC          # global holding TArmy classref (extracted from MovedTo guard)
ISCLASS    = 0x557010C0          # System.@IsClass thunk (EAX=obj, EDX=class -> AL)
UPD_FORM   = 0x5578D034          # TArmy.UpdateFormation (EAX=army)
CAVE       = 0x5580E120          # file 0x10D520

class Asm:
    def __init__(self, base):
        self.base = base; self.buf = bytearray(); self.labels = {}; self.fix8 = []
    def here(self): return self.base + len(self.buf)
    def label(self, n): self.labels[n] = self.here()
    def db(self, *bs): self.buf += bytes(bs)
    def dd(self, v): self.buf += v.to_bytes(4, 'little')
    def call(self, t): self.db(0xE8); self.buf += (t - (self.here()+4)).to_bytes(4,'little',signed=True)
    def j8(self, op, lab): self.db(op); self.fix8.append((len(self.buf), lab)); self.db(0)
    def done(self):
        for off, lab in self.fix8:
            rel = self.labels[lab]-(self.base+off+1); assert -128 <= rel <= 127
            self.buf[off] = rel & 0xFF
        return bytes(self.buf)

a = Asm(CAVE)
a.call(UDA)                         # original: UpdateDefaultAbilities(hero, list)
a.db(0x53)                          # push ebx
a.db(0x8B, 0x5F, 0x04)              # mov ebx, [edi+4]       ; hero's container
a.db(0x85, 0xDB)                    # test ebx, ebx
a.j8(0x74, 'skip')                  # jz skip
a.call(a.here()+5)                  # call $+5 (PIC anchor)
_pop_va = a.here()
a.db(0x5A)                          # pop edx                ; runtime addr of pop
a.db(0x81, 0xEA); a.dd(_pop_va)     # sub edx, link addr     ; edx = load delta
a.db(0x8B, 0x92); a.dd(CLASSREF)    # mov edx, [edx+CLASSREF]; TArmy classref (slot value is loader-relocated)
a.db(0x8B, 0xC3)                    # mov eax, ebx
a.call(ISCLASS)                     # al = obj is TArmy
a.db(0x84, 0xC0)                    # test al, al
a.j8(0x74, 'skip')                  # jz skip
a.db(0x8B, 0xC3)                    # mov eax, ebx
a.call(UPD_FORM)                    # TArmy.UpdateFormation  ; instant aura recompute
a.label('skip')
a.db(0x5B)                          # pop ebx
a.db(0xC3)                          # ret
cave = a.done()
assert CAVE + len(cave) <= 0x5580E200, "cave overruns verified-zero region"

def rel32(src, dst): return struct.pack("<i", dst-(src+5))
patches = [
    (CAVE, bytes(len(cave)), cave, f"cave_auraup ({len(cave)}B)"),
    (HOOK, b"\xE8"+rel32(HOOK, UDA), b"\xE8"+rel32(HOOK, CAVE),
     "THeroUpgradeTE.Execute: UpdateDefaultAbilities -> cave_auraup"),
]

data = bytearray(open(DLL, 'rb').read())
# sanity: the flag-clear must directly follow the hook (right function version)
assert bytes(data[HOOK-FILE_DELTA+5 : HOOK-FILE_DELTA+9]) == NEXT_BYTES, "unexpected bytes after hook site"

ok = True; applied = 0
for va, orig, new, desc in patches:
    off = va - FILE_DELTA
    cur = bytes(data[off:off+len(orig)])
    if cur == new: applied += 1
    elif cur != orig:
        print(f"MISMATCH @0x{va:X} ({desc}):\n  exp {orig.hex(' ')}\n  got {cur.hex(' ')}"); ok = False
if applied == len(patches):
    print("ALL ALREADY PATCHED"); sys.exit(0)
if not ok:
    print("Aborting."); sys.exit(1)
if '--apply' not in sys.argv:
    print(f"cave_auraup @0x{CAVE:X} ({len(cave)}B): {cave.hex(' ')}")
    print("\nDry run OK. Re-run with --apply to write."); sys.exit(0)

if not os.path.exists(BAK):
    shutil.copyfile(DLL, BAK); print(f"Backup: {BAK}")
for va, orig, new, desc in patches:
    off = va - FILE_DELTA
    data[off:off+len(new)] = new
    print(f"Patched: {desc}")
open(DLL, 'wb').write(data)
print("AoWEPACK.dll patched successfully.")
