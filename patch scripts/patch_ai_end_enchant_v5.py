r"""
AI END-OF-TURN UNIT ENCHANTMENTS v5 (2026-10-19), in-place upgrade of v1-v4 (same slot / zone / PR cave / day table).

Fixes the turn-1 "AI ERROR" lock in "AoWx - After the Fall" (live probe, ai_error_probe_log.txt: AV read at
[eax+0x84] in v4's channel helper 0x5581DA66, called from 0x5581D646 with eax = [ebp-0x18]).

ROOT CAUSE - v1..v4 mis-read the leader:
  [player+0xD4] IS the leader unit itself (TPlayer.SetLeader 0x55752CF0 `mov [eax+0xD4],edx`; ValidateLeader
  0x55752B60 uses [player+0xD4] as a unit: name [+0x60], VMT +0x188; GetLeaderLocation 0x557536E4 calls the
  location method of [[player+0xD4]+4] = the leader's ARMY).  v1 loaded [ebp-0x18] = [[player+0xD4]+4], i.e. the
  leader's TArmy, and [ebp-0x14] = [army+4].  Every hero-field read on [ebp-0x18] ([+0x84] channel id, [+0x80]
  casting points, [+0x25], VMT +0x148/+0x128) therefore read a TArmy: garbage in most games (often "channelling"
  -> the whole pass silently did nothing), and an access violation when the army object sat at the end of a heap
  block (After the Fall, turn 1).  Also the "leader first" target rank and the leader's-party phase never matched.

v5:
  * [ebp-0x18] := [player+0xD4] if IsClass(THero) (TLeader inherits THero, cell 0x55711FAC) else 0;
    [ebp-0x14] := [leader+4] (the leader's army).
  * caster block: IsClass(caster, THero) before any hero field read (heroes-list entries and the leader).
  * v3/v4's channel-reserve scan (helper f_rem) is dropped entirely (CHAN_RESERVE was 0: its result was unused).
  * keeps v4's map-castable test ([spell+0x0C] bit 1) and v2/v3 rules (own party, then own armies in range,
    savings target, upkeep guard, KEEP_PCT / RES_PCT / MAXCASTS; channelling caster skips itself).

Dry-run default; --apply / --revert (revert = pre-end-enchant state, same as v1..v4 --revert) / --dis / --dll.
Applies from zero or upgrades v1/v2/v3/v4 (either CHAN_RESERVE build) in place.  v4's script refuses a v5 zone.
Backup <game>\backup\AoWEPACK.dll.bak_aiendench5.
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
from patch_airdeath_fix_v1 import relocs
import patch_ai_end_enchant_v1 as V1
import patch_ai_end_enchant_v2 as V2
import patch_ai_end_enchant_v3 as V3
import patch_ai_end_enchant_v4 as V4

DLL = game_file("AoWEPACK.dll")
BASE, V2F = V1.BASE, V1.V2F
ZONE, ZONE_END = V1.ZONE, V1.ZONE_END
MAGIC = b"AEN5"
H_DELTA, PR, FIND = V1.H_DELTA, V1.PR, V1.FIND
SLOT, ORIG_PROC = V1.SLOT, V1.ORIG_PROC
CLS_HERO = 0x55711FAC          # THero class-ref cell (TLeader's parent)

OLD_LEAD = """    mov  eax, [ebx+0xd4]
    test eax, eax
    jz   f_nl
    mov  eax, [eax+4]
f_nl:
    mov  [ebp-0x18], eax
"""
NEW_LEAD = """    mov  eax, [ebx+0xd4]
    test eax, eax
    jz   f_nl
    push eax
    mov  ecx, [ebp-0xc]
    mov  edx, [ecx+{CHR}]
    call {IC}
    test al, al
    pop  eax
    jnz  f_nl
    xor  eax, eax
f_nl:
    mov  [ebp-0x18], eax
"""
OLD_GOTC = """f_gotc:
    test eax, eax
    jz   f_cnext
    mov  esi, eax
"""
NEW_GOTC = """f_gotc:
    test eax, eax
    jz   f_cnext
    mov  esi, eax
    mov  ecx, [ebp-0xc]
    mov  edx, [ecx+{CHR}]
    call {IC}
    test al, al
    jz   f_cnext
"""


def src_find():
    s = V2.SRC_FIND
    for old, new in ((V4.MAPBIT_OLD, V4.MAPBIT_NEW), (V4.OLD_CHAN, ""), (OLD_LEAD, NEW_LEAD), (OLD_GOTC, NEW_GOTC)):
        assert s.count(old) == 1, old[:40]
        s = s.replace(old, new)
    assert "0x84], 0\n    jne  f_done" not in s
    return s


def build():
    hd = b"\xe8\x00\x00\x00\x00\x58\x2d" + struct.pack("<I", H_DELTA + 5) + b"\xc3"
    find_src = src_find().replace("{UPK_TEST}", V2.upk_test())
    fnd = V2.asm(find_src.format(MINC=V1.MANAINC, MUPK=V1.MANAUPK, CSL=V1.CLS_SPELLLIST, SLC=V1.SPELLLIST_CREATE,
                                 MASK=V1.LIST_MASK, LSP=V1.LISTSPELLS, SLN=V1.SL_COUNT, GH=V1.GETHERO, CAR=V1.CLS_ARMY,
                                 IC=V1.ISCLASS, KEEP=V1.KEEP_PCT, SLG=V1.SL_GET, CUS=V1.CLS_USPELL, CM=V1.CASTMANA,
                                 CI=V1.CANINSTANT, LSC=V1.LSTRCLR, OF=V1.OBJFREE, GU=V1.GETUNIT, US=V1.USTRENGTH,
                                 NT=V2.N_TURNS, GL=V2.GETLOC, GA=V2.GETARMY, HX=V2.HXRAD, CHR=CLS_HERO), FIND)
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
    if same(zone): return "v5"
    for nm, b in (("v4", lambda: V4.build(0)), ("v4-other", lambda: V4.build(1)), ("v3", lambda: V3.build(0)),
                  ("v3-other", lambda: V3.build(1)), ("v2", V2.build), ("v1", V1.build)):
        if same(b()): return nm
    return "DIFFERS"


OLDS = ("v1", "v2", "v3", "v3-other", "v4", "v4-other")


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
    print("  TEndTurnAIPA.Process slot %#x: %s | zone %#x..%#x %s (v5 %d B, ends %#x) | relocs %s | recruit ZONE_END %s"
          % (SLOT, sstate, ZONE, ZONE_END, zstate, len(zone), ZONE + len(zone), bad or "none",
             "n/a" if rz is None else hex(rz)))
    print("  KEEP_PCT %d  RES_PCT %d  MAXCASTS %d  N_TURNS %d  UPK_DIV %d" % (V1.KEEP_PCT, V1.RES_PCT, V1.MAXCASTS,
                                                                            V2.N_TURNS, V2.UPK_DIV))
    if a.dis:
        import capstone
        for lo, hi in ((H_DELTA, PR), (PR, FIND), (FIND, ZONE + len(zone))):
            print("  --")
            for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(zone[lo - ZONE:hi - ZONE].rstrip(b"\0") or b"\x90", lo):
                print("   %08X  %-22s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad or sstate.startswith("FOREIGN"): print("ABORT (slot/reloc)"); return 1
    if zstate == "DIFFERS": print("ABORT (zone not free)"); return 1
    if (sstate == "ours") != (zstate in OLDS + ("v5",)): print("ABORT (mixed state)"); return 1
    if not a.revert and rz is not None and rz > ZONE:
        print("ABORT: set ZONE_END in patch_ai_site_recruit_v1.py to %#x first" % ZONE); return 1
    if zstate in OLDS and not a.revert: print("  state: %s - upgrading %s -> v5 in place" % (zstate, zstate))
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
        bak = bak_path(a.dll, ".bak_aiendench5")
        if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    with open(a.dll, "r+b") as f: f.write(n)
    assert open(a.dll, "rb").read() == bytes(n); print("written", a.dll)
    return 0


if __name__ == "__main__":
    sys.exit(main())
