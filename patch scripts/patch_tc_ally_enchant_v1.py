r"""
ALLIED TARGETS FOR OWN-SIDE COMBAT SPELLS (2026-10-18).  AoWTCPCK.dll only.

User: "unit enchantments on allies: the cursor crosshair turns red when hovering over an ally in combat, and it
doesn't let me actually click and enchant them."  (Wanted: allies yes, enemies still no.)

RE - the tactical LEFT-CLICK gate (TCPCK 0x41F4A0..0x41F6D4, inside the map-click handler):
  [ebp-8]    = the combat-object HS on the clicked field (FindOwnedChild 0x220104), nil -> 0x41E408 directly
  [ebp-4]    = the controller; 0x41D2E8 = its selected HS (+0x1C = the caster TCombatObject)
  [ebp-0x15] = the action's side mask (spell: TC GetCombatInfo byte 7 = TUnitSpell 1 'own side'; ability: VMT+0x104
               byte 0; no action: 2).  bit 1 = own side, bit 2 = other side.
  0x41F5A6: same PLAYER and !bit1          -> select that unit instead
  0x41F5EF: same PLAYER and bit1           -> 0x41E408 (cast / act)
  0x41F616: different PLAYER: bit2 ? 0x41E408 : NOTHING     <-- an ALLY (same side, other player) is refused here
  The gate compares TCombatObject.GetPlayer (thunk 0x402544), whereas the hover cursor (UpdateMoveCursor 0x41F9A8..)
  and everything downstream (CalculateRangedPath 0x41DC58, AbRangedTC 0x423860 -> TE, AoWEPACK ExecuteSpell /
  ValidTarget) are side-based or owner-agnostic.  So own-side spells could never be clicked onto an allied unit.
FIX - site 0x41F63B (`test byte [ebp-0x15],2 / je 0x41F6D4`, 10 B, reloc-free) -> jmp cave + 5 NOP:
      bit2                                        -> 0x41F645 (vanilla: other-player target, other-side spell)
      bit1 and GetSide(target) == GetSide(caster) -> 0x41F645 (NEW: ally on my side, own-side spell)
      else                                        -> 0x41F6D4 (nothing, vanilla)
  Enemies stay refused (their side differs); neutral players never join a battle.  The cast itself is the normal
  click path (TE broadcast by AbRangedTC), so MP clients execute it identically; ExecuteSpell does not re-check the
  owner (the enchantment is registered to the CASTER's player -> the caster pays any upkeep).
Zone AoWTCPCK 0x450000..0x450040 (zero, reloc-free, PIC: rel32 only).  Dry-run default; --apply / --revert / --dis /
--dll <scratch copy>.  Backup <game>\backup\AoWTCPCK.dll.bak_allyench.  No other hook on this site (independent).
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
from patch_airdeath_fix_v1 import relocs
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

DLL = game_file("AoWTCPCK.dll")
BASE, V2F = 0x400000, 0x400C00
ZONE, ZONE_END = 0x450000, 0x450040
SITE = 0x41F63B
VANILLA = bytes.fromhex("f645eb020f848f000000")
CAST, NOTHING, GETSIDE, SELHS = 0x41F645, 0x41F6D4, 0x40252C, 0x41D2E8

CAVE = """
    test byte ptr [ebp-0x15], 2
    jnz do_cast
    test byte ptr [ebp-0x15], 1
    jz do_nothing
    mov eax, [ebp-8]
    mov eax, [eax+0x1c]
    call %(getside)#x
    mov bl, al
    mov eax, [ebp-4]
    call %(selhs)#x
    mov eax, [eax+0x1c]
    call %(getside)#x
    cmp bl, al
    jne do_nothing
do_cast:
    jmp %(cast)#x
do_nothing:
    jmp %(nothing)#x
""" % dict(getside=GETSIDE, selhs=SELHS, cast=CAST, nothing=NOTHING)


def build():
    zone = bytes(Ks(KS_ARCH_X86, KS_MODE_32).asm(CAVE, ZONE)[0])
    assert len(zone) <= ZONE_END - ZONE
    site = b"\xe9" + struct.pack("<i", ZONE - (SITE + 5)) + b"\x90" * 5
    return zone, site


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true"); ap.add_argument("--dll", default=DLL); a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read())
    zone, site = build()
    zl = bytes(d[ZONE - V2F:ZONE_END - V2F]); sb = bytes(d[SITE - V2F:SITE - V2F + 10])
    sstate = "vanilla" if sb == VANILLA else "ours" if sb == site else "FOREIGN"
    zstate = "zero" if not any(zl) else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else "DIFFERS"
    bad = [hex(r) for r in relocs(bytes(d), BASE) if ZONE - 3 <= r < ZONE_END or SITE - 3 <= r < SITE + 10]
    print("AoWTCPCK site %#x %s | zone %#x %s (%d B) | relocs %s" % (SITE, sstate, ZONE, zstate, len(zone), bad or "none"))
    if a.dis:
        import capstone
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(zone, ZONE):
            print("   %08X  %-18s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad or sstate == "FOREIGN": print("ABORT (site/reloc)"); return 1
    if zstate == "DIFFERS": print("ABORT (zone not free)"); return 1
    if (sstate == "ours") != (zstate == "ours"): print("ABORT (mixed state)"); return 1
    n = bytearray(d)
    if a.revert:
        n[SITE - V2F:SITE - V2F + 10] = VANILLA; n[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE)
    else:
        n[ZONE - V2F:ZONE - V2F + len(zone)] = zone; n[SITE - V2F:SITE - V2F + 10] = site
    if n == d: print("already %s" % ("reverted" if a.revert else "applied")); return 0
    if not (a.apply or a.revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if os.path.abspath(a.dll) == os.path.abspath(DLL):
        bak = bak_path(a.dll, ".bak_allyench")
        if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    with open(a.dll, "r+b") as f: f.write(n)
    assert open(a.dll, "rb").read() == bytes(n); print("written", a.dll)
    return 0


if __name__ == "__main__":
    sys.exit(main())
