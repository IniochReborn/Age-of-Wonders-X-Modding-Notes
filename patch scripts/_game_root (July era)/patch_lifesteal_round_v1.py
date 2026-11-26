#!/usr/bin/env python3
"""
Life Stealing works on Round Attack (AoWEPACK.dll) — port of BXL's
lifesteal-roundattack fix, adapted to OUR binary (2026-07-20).

Vanilla bug (verified): Life Stealing (0x76) flag CA+0x18 bit 0x02 is set only
by the normal-melee builder (TMeleeRound.CreateStrikeCA); round attack uses the
global CreateStrikeCA which never sets it, AND the heal sits in Execute's
CA+0x15-gated first block which round-attack strikes skip. Fix = wire it like
Cause Fear/Entangle: set a fresh flag (bit 0x08) in TStrikeCA.Generate (runs
for EVERY strike, hit-gated by its CA+0x10!=0 block), heal in a plain
flag-block in Execute.

OUR-binary adaptations vs BXL's script:
  - heal +2 (matches our live pre-Claude AoWx tune at SUB_0x5580C110; vanilla
    was +1 `inc edx`). The old block becomes unreachable (cave jumps over it),
    so the old cave at 0x5580C110 goes dead — left in place.
  - keeps vanilla's target gate (dropped by BXL): target IsClass TCombatUnit
    && [target+0x4C] != nil && GetUnitType([target+0x4C]) != 2 (no lifesteal
    off lifeless/type-2 targets). Checked in cave_lsgen where ESI=target.
  - no Dark Gift 0xA9 (that's his mod's ability).
  - offensive-only gate (CA+0x0C bit0 clear): normal melee + round attack,
    NOT retaliation. Flip DEFENSIVE=True and re-apply to include retaliation.
  - PIC: TCombatUnit classref read via call/pop delta (DLL rebases).

Hooks (both vanilla-byte-verified on our .dll):
  TStrikeCA.Execute  @0x5576678C  80 7B 15 00 74 3D -> E9 rel32 90 (cave_lsround, jmp back 0x557667CF)
  TStrikeCA.Generate @0x557668E2  BA 33 00 00 00    -> E9 rel32    (cave_lsgen, replays mov edx,0x33, jmp back 0x557668E7)

Caves in OUR free space: 0x5580E160 / 0x5580E1A0 (file 0x10D560/0x10D5A0, zeros
verified). Dry-run default; --apply. Backup: AoWEPACK.dll.bak_lifesteal_round
"""
import shutil, sys, struct, os

GAME = os.path.dirname(os.path.abspath(__file__))
DLL  = os.path.join(GAME, "AoWEPACK.dll")
BAK  = DLL + ".bak_lifesteal_round"
FILE_DELTA = 0x55700C00

LS_ABIL   = 0x76
LS_FLAG   = 0x08
LS_HEAL   = 2                    # matches live AoWx heal (vanilla was 1)
DEFENSIVE = False                # True: also lifesteal on retaliation strikes

EXEC_INJ  = 0x5576678C; EXEC_ORIG = bytes.fromhex("807b1500743d"); EXEC_CONT = 0x557667CF
GEN_INJ   = 0x557668E2; GEN_ORIG  = bytes.fromhex("ba33000000");   GEN_CONT  = 0x557668E7
CLASSREF  = 0x55715A54           # TCombatUnit classref global (from Execute's own IsClass)
ISCLASS   = 0x557010C0           # System.@IsClass thunk (EAX=obj, EDX=class -> AL)
CAVE1     = 0x5580E160           # cave_lsround (file 0x10D560)
CAVE2     = 0x5580E1A0           # cave_lsgen   (file 0x10D5A0)
CAVE_LIMIT = 0x5580E200          # end of verified-zero region (file 0x10D600)

class Asm:
    def __init__(self, base):
        self.base = base; self.buf = bytearray(); self.labels = {}; self.fix8 = []
    def here(self): return self.base + len(self.buf)
    def label(self, n): self.labels[n] = self.here()
    def db(self, *bs): self.buf += bytes(bs)
    def dd(self, v): self.buf += v.to_bytes(4, 'little')
    def call(self, t): self.db(0xE8); self.buf += (t-(self.here()+4)).to_bytes(4,'little',signed=True)
    def jmp32(self, t): self.db(0xE9); self.buf += (t-(self.here()+4)).to_bytes(4,'little',signed=True)
    def j8(self, op, lab): self.db(op); self.fix8.append((len(self.buf), lab)); self.db(0)
    def done(self):
        for off, lab in self.fix8:
            rel = self.labels[lab]-(self.base+off+1); assert -128 <= rel <= 127
            self.buf[off] = rel & 0xFF
        return bytes(self.buf)

# ---- cave_lsround: Execute heal. EBX=CA, EDI=attacker (preserved regs) ------
a = Asm(CAVE1)
a.db(0xF6, 0x43, 0x18, LS_FLAG)     # test byte [ebx+0x18], LS_FLAG
a.j8(0x74, 'done')                  # jz done
a.db(0x8B, 0xC7)                    # mov eax, edi
a.db(0x8B, 0x10)                    # mov edx, [eax]
a.db(0xFF, 0x92, 0x88,0,0,0)        # call [edx+0x88]        ; GetHitPoints
a.db(0x83, 0xC0, LS_HEAL)           # add eax, LS_HEAL
a.db(0x8B, 0xD0)                    # mov edx, eax
a.db(0x8B, 0xC7)                    # mov eax, edi
a.db(0x8B, 0x08)                    # mov ecx, [eax]
a.db(0xFF, 0x91, 0x8C,0,0,0)        # call [ecx+0x8C]        ; SetHitPoints (clamps)
a.label('done')
a.jmp32(EXEC_CONT)                  # skip old CA+0x15 block (old heal now dead)
cave1 = a.done()
assert CAVE1 + len(cave1) <= CAVE2

# ---- cave_lsgen: Generate flag set. EBX=CA, EDI=attacker, ESI=target --------
a = Asm(CAVE2)
if not DEFENSIVE:
    a.db(0xF6, 0x43, 0x0C, 0x01)    # test byte [ebx+0x0C], 1  ; defensive?
    a.j8(0x75, 'replay')            # jnz replay (no flag on retaliation)
a.db(0xBA, LS_ABIL,0,0,0)           # mov edx, 0x76
a.db(0x8B, 0xC7)                    # mov eax, edi
a.db(0x8B, 0x08)                    # mov ecx, [eax]
a.db(0xFF, 0x91, 0xA8,0,0,0)        # call [ecx+0xA8]        ; attacker GetAbilityEnabled(0x76)
a.db(0x84, 0xC0)                    # test al, al
a.j8(0x74, 'replay')                # jz replay
# vanilla target gate: IsClass(target,TCombatUnit) && [target+4C]!=nil && type!=2
a.call(a.here()+5)                  # call $+5 (PIC anchor)
_pop_va = a.here()
a.db(0x5A)                          # pop edx
a.db(0x81, 0xEA); a.dd(_pop_va)     # sub edx, link addr     ; edx = load delta
a.db(0x8B, 0x92); a.dd(CLASSREF)    # mov edx, [edx+classref]; TCombatUnit class
a.db(0x8B, 0xC6)                    # mov eax, esi           ; target
a.call(ISCLASS)                     # al = target is TCombatUnit
a.db(0x84, 0xC0)                    # test al, al
a.j8(0x74, 'replay')                # jz replay
a.db(0x8B, 0x46, 0x4C)              # mov eax, [esi+0x4C]    ; strategic unit
a.db(0x85, 0xC0)                    # test eax, eax
a.j8(0x74, 'replay')                # jz replay
a.db(0x8B, 0x10)                    # mov edx, [eax]
a.db(0xFF, 0x92, 0x14,1,0,0)        # call [edx+0x114]       ; GetUnitType
a.db(0x3C, 0x02)                    # cmp al, 2
a.j8(0x74, 'replay')                # jz replay (lifeless target: no steal)
a.db(0x80, 0x4B, 0x18, LS_FLAG)     # or byte [ebx+0x18], LS_FLAG
a.label('replay')
a.db(0xBA, 0x33,0,0,0)              # mov edx, 0x33          ; displaced instruction
a.jmp32(GEN_CONT)
cave2 = a.done()
assert CAVE2 + len(cave2) <= CAVE_LIMIT

def rel32(src, dst): return struct.pack("<i", dst-(src+5))
patches = [
    (CAVE1, bytes(len(cave1)), cave1, f"cave_lsround @0x{CAVE1:X} ({len(cave1)}B, heal +{LS_HEAL})"),
    (CAVE2, bytes(len(cave2)), cave2, f"cave_lsgen @0x{CAVE2:X} ({len(cave2)}B, offensive={'no' if DEFENSIVE else 'yes'})"),
    (EXEC_INJ, EXEC_ORIG, b"\xE9"+rel32(EXEC_INJ, CAVE1)+b"\x90",
     "TStrikeCA.Execute -> cave_lsround (skips old CA+0x15 block)"),
    (GEN_INJ, GEN_ORIG, b"\xE9"+rel32(GEN_INJ, CAVE2),
     "TStrikeCA.Generate -> cave_lsgen"),
]

data = bytearray(open(DLL, 'rb').read())
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
    for va, _o, new, desc in patches[:2]:
        print(f"{desc}: {new.hex(' ')}")
    print("\nDry run OK. Re-run with --apply to write."); sys.exit(0)

if not os.path.exists(BAK):
    shutil.copyfile(DLL, BAK); print(f"Backup: {BAK}")
for va, orig, new, desc in patches:
    off = va - FILE_DELTA
    data[off:off+len(new)] = new
    print(f"Patched: {desc}")
open(DLL, 'wb').write(data)
print("AoWEPACK.dll patched successfully.")
