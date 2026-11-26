r"""
AI END-OF-TURN UNIT ENCHANTMENTS v4 (2026-10-19), in-place upgrade of v3 (same slot / zone / PR cave / day table).

Hardening after the turn-1 "AI ERROR" lock in "AoWx - After the Fall": v1-v3 picked ANY TUnitSpell from
TPlayerMagicControl.ListSpells mask 6 ([spell+0x22] in {1,2}) - that list also holds our COMBAT-ONLY unit spells
(cast context [spell+0x0C] without map bit 1: 214 Suspend, 215 Static Shield, 233 Mimic, 234 Reversal, 310 Second
Wind, 346 Borrow Time, 360 Martyr - see patch_caster_evoker33_v1.py), and CanCastSpellInstantly does not check the
context.  v4 adds `test byte ptr [spell+0x0C],1 / jz next` right after the TUnitSpell IsClass test, so only spells
castable on the strategic map are considered (every vanilla unit spell has the bit).  Nothing else changes.

Dry-run default; --apply / --revert (revert = pre-end-enchant state, same as v1/v2/v3 --revert) / --dis / --dll.
Backup <game>ackup\AoWEPACK.dll.bak_aiendench4.  v3's script refuses a v4 zone ("zone not free").
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
from patch_airdeath_fix_v1 import relocs
import patch_ai_end_enchant_v1 as V1
import patch_ai_end_enchant_v2 as V2
import patch_ai_end_enchant_v3 as V3
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

DLL = game_file("AoWEPACK.dll")
BASE, V2F = V1.BASE, V1.V2F
ZONE, ZONE_END = V1.ZONE, V1.ZONE_END
MAGIC = b"AEN4"
H_DELTA, PR, FIND = V1.H_DELTA, V1.PR, V1.FIND
SLOT, ORIG_PROC = V1.SLOT, V1.ORIG_PROC
CHAN_RESERVE = 0          # 1 = add the channelled spells' remaining cost to the mana floor (see docstring: off)

OLD_CHAN = """    mov  eax, [ebp-0x18]
    test eax, eax
    jz   f_ch0
    cmp  dword ptr [eax+0x84], 0
    jne  f_done
f_ch0:
    mov  dword ptr [ebp-0x2c], 0
f_chl:
    mov  edx, [ebp-0x2c]
    cmp  edx, [ebp-0x30]
    jge  f_chd
    mov  eax, [ebx+0x80]
    call {GH}
    test eax, eax
    jz   f_chn
    cmp  dword ptr [eax+0x84], 0
    jne  f_done
f_chn:
    inc  dword ptr [ebp-0x2c]
    jmp  f_chl
f_chd:
"""
# -0x90 = sum of the remaining channel cost ([h+0x8C] - [h+0x88]) over the player's channelling casters
NEW_CHAN = """    mov  dword ptr [ebp-0x90], 0
    mov  eax, [ebp-0x18]
    test eax, eax
    jz   f_ch0
    call f_rem
f_ch0:
    mov  dword ptr [ebp-0x2c], 0
f_chl:
    mov  edx, [ebp-0x2c]
    cmp  edx, [ebp-0x30]
    jge  f_chd
    mov  eax, [ebx+0x80]
    call {GH}
    test eax, eax
    jz   f_chn
    cmp  eax, [ebp-0x18]
    je   f_chn
    call f_rem
f_chn:
    inc  dword ptr [ebp-0x2c]
    jmp  f_chl
f_chd:
"""
OLD_S2 = """f_s2:
    mov  dword ptr [ebp-0x1c], 0
"""
NEW_S2_ON = """f_s2:
    mov  eax, [ebp-0x90]
    add  [ebp-8], eax
    mov  dword ptr [ebp-0x1c], 0
"""
F_REM = """
f_rem:
    cmp  dword ptr [eax+0x84], 0
    je   f_rr
    mov  ecx, [eax+0x8c]
    sub  ecx, [eax+0x88]
    jle  f_rr
    add  [ebp-0x90], ecx
f_rr:
    ret
"""


MAPBIT_OLD = """    jz   f_snext
    cmp  dword ptr [edi+0x40], -1
    je   f_snext
    mov  eax, [edi+0x1c]
"""
MAPBIT_NEW = """    jz   f_snext
    test byte ptr [edi+0x0c], 1
    jz   f_snext
    cmp  dword ptr [edi+0x40], -1
    je   f_snext
    mov  eax, [edi+0x1c]
"""


def src_find(chan_reserve):
    s = V2.SRC_FIND
    assert s.count(MAPBIT_OLD) == 1
    s = s.replace(MAPBIT_OLD, MAPBIT_NEW)
    assert s.count(OLD_CHAN) == 1 and s.count(OLD_S2) == 1
    s = s.replace(OLD_CHAN, NEW_CHAN)
    if chan_reserve:
        s = s.replace(OLD_S2, NEW_S2_ON)
    return s.rstrip() + "\n" + F_REM


def build(chan_reserve=CHAN_RESERVE):
    hd = b"\xe8\x00\x00\x00\x00\x58\x2d" + struct.pack("<I", H_DELTA + 5) + b"\xc3"
    find_src = src_find(chan_reserve).replace("{UPK_TEST}", V2.upk_test())
    fnd = V2.asm(find_src.format(MINC=V1.MANAINC, MUPK=V1.MANAUPK, CSL=V1.CLS_SPELLLIST, SLC=V1.SPELLLIST_CREATE,
                                 MASK=V1.LIST_MASK, LSP=V1.LISTSPELLS, SLN=V1.SL_COUNT, GH=V1.GETHERO, CAR=V1.CLS_ARMY,
                                 IC=V1.ISCLASS, KEEP=V1.KEEP_PCT, SLG=V1.SL_GET, CUS=V1.CLS_USPELL, CM=V1.CASTMANA,
                                 CI=V1.CANINSTANT, LSC=V1.LSTRCLR, OF=V1.OBJFREE, GU=V1.GETUNIT, US=V1.USTRENGTH,
                                 NT=V2.N_TURNS, GL=V2.GETLOC, GA=V2.GETARMY, HX=V2.HXRAD), FIND)
    pr = V2.asm(V1.SRC_PR.format(HD=H_DELTA, NS=V1.NSLOT, TBL=V1.TABLE, MAP=V1.MAPCELL, MAXC=V1.MAXCASTS,
                                 RES=V1.RES_PCT, FIND=FIND, ORIG=ORIG_PROC, EXPM=V1.EXPMADE, CTE=V1.CLS_USPELLTE,
                                 TEC=V1.TE_CREATE, CM=V1.CASTMANA, TEI=V1.TE_INIT, ILA=V1.INTLIST_ADD,
                                 GTC=V1.GETTOKCTRL), PR)
    assert len(pr) <= FIND - PR, len(pr)
    zone = bytearray(FIND - ZONE + len(fnd))
    zone[0:4] = MAGIC
    zone[4:8] = struct.pack("<I", ORIG_PROC)
    for addr, blob in ((H_DELTA, hd), (PR, pr), (FIND, fnd)):
        zone[addr - ZONE:addr - ZONE + len(blob)] = blob
    assert len(zone) <= ZONE_END - ZONE, hex(len(zone))
    return bytes(zone)


def zstate_of(zl, zone):
    if not any(zl): return "zero"
    def same(z): return zl[:len(z)] == z and not any(zl[len(z):])
    if same(zone): return "v4"
    if same(build(1 - CHAN_RESERVE)): return "v4-other"
    if same(V3.build(0)): return "v3"
    if same(V3.build(1)): return "v3-other"
    if same(V2.build()): return "v2"
    if same(V1.build()): return "v1"
    return "DIFFERS"


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true"); ap.add_argument("--dll", default=DLL); a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read())
    zone = build()
    zl = bytes(d[ZONE - V2F:ZONE_END - V2F])
    zstate = zstate_of(zl, zone)
    sv = struct.unpack_from("<I", d, SLOT - V2F)[0]
    sstate = "vanilla" if sv == ORIG_PROC else "ours" if sv == PR else "FOREIGN(%#x)" % sv
    bad = [hex(r) for r in relocs(bytes(d), BASE) if ZONE - 3 <= r < ZONE_END]
    rz = V1.recruit_zone_end()
    print("  TEndTurnAIPA.Process slot %#x: %s | zone %#x..%#x %s (v4 %d B, ends %#x) | relocs %s | recruit ZONE_END %s"
          % (SLOT, sstate, ZONE, ZONE_END, zstate, len(zone), ZONE + len(zone), bad or "none",
             "n/a" if rz is None else hex(rz)))
    print("  KEEP_PCT %d  RES_PCT %d  MAXCASTS %d  N_TURNS %d  UPK_DIV %d  CHAN_RESERVE %d"
          % (V1.KEEP_PCT, V1.RES_PCT, V1.MAXCASTS, V2.N_TURNS, V2.UPK_DIV, CHAN_RESERVE))
    if a.dis:
        import capstone
        for lo, hi in ((H_DELTA, PR), (PR, FIND), (FIND, ZONE + len(zone))):
            print("  --")
            for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(zone[lo - ZONE:hi - ZONE].rstrip(b"\0") or b"\x90", lo):
                print("   %08X  %-22s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad or sstate.startswith("FOREIGN"): print("ABORT (slot/reloc)"); return 1
    if zstate == "DIFFERS": print("ABORT (zone not free)"); return 1
    if (sstate == "ours") != (zstate in ("v1", "v2", "v3", "v3-other", "v4", "v4-other")): print("ABORT (mixed state)"); return 1
    if not a.revert and rz is not None and rz > ZONE:
        print("ABORT: set ZONE_END in patch_ai_site_recruit_v1.py to %#x first" % ZONE); return 1
    if zstate in ("v1", "v2", "v3", "v3-other", "v4-other") and not a.revert: print("  state: %s - upgrading %s -> v4 in place" % (zstate, zstate))
    n = bytearray(d)
    if a.revert:
        struct.pack_into("<I", n, SLOT - V2F, ORIG_PROC)
        n[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE)
    else:
        n[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE)
        n[ZONE - V2F:ZONE - V2F + len(zone)] = zone
        struct.pack_into("<I", n, SLOT - V2F, PR)
    if n == d: print("already %s" % ("reverted" if a.revert else "applied")); return 0
    if not (a.apply or a.revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if os.path.abspath(a.dll) == os.path.abspath(DLL):
        bak = bak_path(a.dll, ".bak_aiendench4")
        if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    with open(a.dll, "r+b") as f: f.write(n)
    assert open(a.dll, "rb").read() == bytes(n); print("written", a.dll)
    return 0


if __name__ == "__main__":
    sys.exit(main())
