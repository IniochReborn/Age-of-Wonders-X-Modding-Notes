r"""
AI END-OF-TURN UNIT ENCHANTMENTS v3 (strategic map), 2026-10-19.  AoWEPACK.dll only.  In-place upgrade of
patch_ai_end_enchant_v2.py (same slot, zone, PR cave and per-player day table; only FIND's channel block changes).

User (on v2's "if ANY of the player's casters is channelling, the pass casts nothing"): "if an AI has a hero that is
channelling a spell, then its leader will stop casting?" -> agreed new rule:
  (1) the CHANNELLING caster itself does no extra enchanting until its spell completes (v1/v2 per-caster skip
      `cmp [caster+0x84],0 / jne next`, kept);
  (2) every OTHER caster keeps enchanting.  v2's player-wide `jne f_done` blocks are removed.

RE - vanilla channelling (THero, AoWEPACK):
  * ExecuteStartCasting 0x55789130: refuses unless player mana >= CastingMana and CastingMana > the hero's casting
    points this turn; then [hero+0x8C] := CastingMana(hero, spell) (total cost), PLAYER MANA -= [hero+0x8C] up front
    (0x5577C9B0 SetMana), [hero+0x88] := the hero's casting points [hero+0x80] (progress), [hero+0x80] := 0,
    [hero+0x84] := spell id.
  * CastingReady 0x557895A4: [hero+0x84] != 0 and [hero+0x88] == [hero+0x8C].  CastingTurns 0x55789518 /
    CastingTurnsLeft 0x557895C4: ceil(([+0x8C] - [+0x88]) / casting points max).  CastingDone 0x557893E8 clears
    +0x84/+0x88/+0x8C - no mana is charged at completion (only the instant-cast path 0x55789444 charges mana).
  => the channelled spell's MANA is already paid in full when channelling starts; what remains ([+0x8C] - [+0x88]) is
     the channelling hero's OWN casting points, which other casters cannot touch.  Another caster enchanting can
     therefore never delay a channel, and no mana reserve is needed for it.
  The directive's "floor += remaining cost of channelled spells" is still built in, but OFF by default
  (CHAN_RESERVE = 0): the remaining amount is casting points (not mana) and its mana was already deducted, so adding
  it would double-reserve and make the AI needlessly passive.  Set CHAN_RESERVE = 1 to add sum(+0x8C - +0x88) over
  the player's channelling casters to the mana floor after v2's max(floor, savings target S).

Unchanged from v2: own party first, then other own armies within [spell+0x38]; savings target S; upkeep guard
(upkeep <= net income / UPK_DIV); KEEP_PCT / RES_PCT / MAXCASTS.

Dry-run default; --apply / --revert / --dis / --dll <scratch>.  Upgrades v1 or v2 (or v3 with the other CHAN_RESERVE
setting) in place; --revert = vanilla (exactly what v1/v2 --revert give).  v2's script refuses a v3 zone (magic AEN3
-> "DIFFERS").  Backup <game>\backup\AoWEPACK.dll.bak_aiendench3.
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
from patch_airdeath_fix_v1 import relocs
import patch_ai_end_enchant_v1 as V1
import patch_ai_end_enchant_v2 as V2
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

DLL = game_file("AoWEPACK.dll")
BASE, V2F = V1.BASE, V1.V2F
ZONE, ZONE_END = V1.ZONE, V1.ZONE_END
MAGIC = b"AEN3"
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


def src_find(chan_reserve):
    s = V2.SRC_FIND
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
    if same(zone): return "v3"
    if same(build(1 - CHAN_RESERVE)): return "v3-other"
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
    print("  TEndTurnAIPA.Process slot %#x: %s | zone %#x..%#x %s (v3 %d B, ends %#x) | relocs %s | recruit ZONE_END %s"
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
    if (sstate == "ours") != (zstate in ("v1", "v2", "v3", "v3-other")): print("ABORT (mixed state)"); return 1
    if not a.revert and rz is not None and rz > ZONE:
        print("ABORT: set ZONE_END in patch_ai_site_recruit_v1.py to %#x first" % ZONE); return 1
    if zstate in ("v1", "v2", "v3-other") and not a.revert: print("  state: %s - upgrading %s -> v3 in place" % (zstate, zstate))
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
        bak = bak_path(a.dll, ".bak_aiendench3")
        if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    with open(a.dll, "r+b") as f: f.write(n)
    assert open(a.dll, "rb").read() == bytes(n); print("written", a.dll)
    return 0


if __name__ == "__main__":
    sys.exit(main())
