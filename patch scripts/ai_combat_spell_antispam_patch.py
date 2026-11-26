#!/usr/bin/env python3
"""
AI Combat-Spell Anti-Spam  (once-per-combat limits)  -- REFERENCE APPLIER
Target: AoWEPACK.dll  (ImageBase 0x55700000, VA = file_off + 0x55700C00)

Turn Undead = always low (val/64); Terror / Slow(Hunters a tester) / Ooze = 1 cast/combat.
See "AI Combat-Spell Anti-Spam.md" for the full mechanism + RE.

These are the EXACT byte patches from our build (byte-diff of the pre-feature
backup vs the confirmed-working DLL). Cave VAs (0x5580xxxx / 0x5580Fxxxx) are OUR
free-space picks and OVERLAP BXL's caves -- read as an exact-byte RE reference,
not a drop-in applier on a different base. Self-verifies every original byte.
"""
import struct, sys
F="AoWEPACK.dll"
d=bytearray(open(F,"rb").read())
def o(va): return va-0x55700C00
PATCHES=[  # (va, original_bytes, new_bytes, comment)
  (0x5572708C, bytes.fromhex("558bec5153"), bytes.fromhex("e9576c0e00"), 'hook TCombat.Create -> reset cave (jmp)'),
  (0x557794E8, bytes.fromhex("535657558be9"), bytes.fromhex("e9a542090090"), 'hook TSpell.CombatCastingDone -> Ooze cast-detect cave (jmp+nop)'),
  (0x557F4350, bytes.fromhex("9c9677"), bytes.fromhex("49fa80"), 'Turn Undead tc-value VMT slot -> divide-by-64 cave'),
  (0x557F4E88, bytes.fromhex("9c9677"), bytes.fromhex("aad280"), 'Slow/Hunters a tester tc-value VMT slot -> boost/nerf wrapper'),
  (0x557F5E48, bytes.fromhex("b4937755c0727f"), bytes.fromhex("38d780559cd680"), 'Ooze VMT +0x74 ActivateCombat & +0x78 CreateCA slots -> flag thunks (fast-combat)'),
  (0x557F5E58, bytes.fromhex("48967f"), bytes.fromhex("d4d680"), 'Ooze VMT +0x84 GetCombatDamageValueEx slot -> value gate'),
  (0x557F5E68, bytes.fromhex("38787f5564747f"), bytes.fromhex("4ed6805504d780"), 'Ooze VMT +0x94 fcExecute & +0x98 fcGetDamageValueEx slots -> thunk + value gate'),
  (0x557F625C, bytes.fromhex("449d7f"), bytes.fromhex("34dd80"), 'Terror tc-value VMT slot -> conditional-shrink wrapper'),
  (0x557F8818, bytes.fromhex("5356578bf2"), bytes.fromhex("e94b550100"), 'hook TSlowCA.Execute -> Slow flag-set cave (jmp)'),
  (0x557F990C, bytes.fromhex("5356578bf2"), bytes.fromhex("e903440100"), 'hook TTacticalCombatTerrorCA.Execute -> Terror flag-set cave (jmp)'),
  (0x5580D2AA, bytes.fromhex("000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"), bytes.fromhex("538b5c240853e8e7c3f6ffe800000000582dbad2805580b822af8f5500750c8b03c1e00383c0648903eb0e8b0385c07408c1e80675014089035bc204"), 'CAVE: Slow boost/nerf value wrapper'),
  (0x5580D64E, bytes.fromhex("0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"), bytes.fromhex("50e800000000582d54d68055c68020af8f550158e9d1a1feff00ff742408ff742408e8ef9dfeff518b4c2408c7010000000059c208"), 'CAVE: Ooze +0x94 fast-combat flag thunk'),
  (0x5580D69C, bytes.fromhex("00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"), bytes.fromhex("50e800000000582da2d68055c68020af8f550158e90b9cfeff000000ff742404e887bffeff518b4c2408c7010000000059c2040000000000ff742404e86bbffeff51e8000000005981e9e3d6805580b920af8f5500740a8b4c2408c7010000000059c20400000000ff742408ff742408e8539dfeff51e8000000005981e917d7805580b920af8f5500740a8b4c2408c7010000000059c2080000000050e800000000582d3ed78055c68020af8f550158e963bcf6ff"), 'CAVES: Ooze +0x78 thunk, value gates (+0x84/+0x98), +0x74 thunk (+ dead diag wrappers)'),
  (0x5580D792, bytes.fromhex("0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"), bytes.fromhex("52e8000000005a81ea98d78055518d8ad45d7f553908597507c68220af8f55015a5356575589cde930bdf6ff"), 'CAVE: Ooze cast-detect (VMT-identity vs TOoze, set F_OOZE)'),
  (0x5580DCE8, bytes.fromhex("0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"), bytes.fromhex("50e800000000582deedc8055c68020af8f5500c68021af8f5500c68022af8f5500585589e55153e97d93f1ff50e800000000582d1add8055c68021af8f55015853565789d6e9dfbbfeff0000538b5c240853e805c0feffe800000000582d44dd805580b821af8f5500740e8b0385c07408c1e80675014089035bc2040000000050e800000000582d6edd8055c68022af8f55015853565789d6e997aafeff0000538b5c240853e809b9f6ffe800000000582d98dd805580b822af8f5500740e8b0385c07408c1e80675014089035bc2040000000050e800000000582dc2dd8055c68020af8f5501585589e55153e9eb94feff0000538b5c240853e8b5b8f6ff8b0385c07408c1e80675014089035bc204"), 'CAVES: shared reset (F_OOZE/F_TERROR/F_SLOW) + Terror set/wrapper + Slow set'),
  (0x5580FA49, bytes.fromhex("00000000000000000000000000000000000000000000000000000000"), bytes.fromhex("538b5c240853e8489cf6ff8b0385c07408c1e80675014089035bc204"), 'CAVE: Turn Undead divide-by-64 value wrapper'),
]
for va,ob,nb,cm in PATCHES:
    cur=bytes(d[o(va):o(va)+len(ob)])
    if cur==nb: print("already applied @0x%08X (%s)"%(va,cm)); continue
    assert cur==ob, "UNEXPECTED bytes @0x%08X: %s (want %s)"%(va,cur.hex(),ob.hex())
    d[o(va):o(va)+len(nb)]=nb
    print("patched @0x%08X len %d  %s"%(va,len(nb),cm))
open(F,"wb").write(d)
print("done: AI combat-spell anti-spam applied (%d regions)."%len(PATCHES))
