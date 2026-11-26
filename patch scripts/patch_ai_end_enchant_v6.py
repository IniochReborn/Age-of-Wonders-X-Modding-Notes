r"""
AI END-OF-TURN UNIT ENCHANTMENTS v6 (2026-10-19), in-place upgrade of v5 (same slot / zone / PR cave / day table).

User: "for the 50 % casting points holdback, make it only happen if there are any other races within one turn range
that aren't allies (independent units don't count). That way if the AI is very safe it can expend all its casting
points to get stronger."

v6 = v5 + a THREAT test per caster.  Right after v5 computes the casting-point reserve
    [ebp-0x40] = GetCastingPointsMax * KEEP_PCT / 100
it calls thr(caster); no threat -> [ebp-0x40] := 0 (the caster may spend down to 0 CP).  The mana floor / savings
target, the upkeep guard, MAXCASTS, own-party-first and the channelling skip are all unchanged.

THREAT (pure game state, no RNG -> identical on every peer):
  caster location x/y/level = TAbstractUnit.GetLocation 0x5577ED94 (the call v2 already uses for range casting);
  scan the square |dx|,|dy| <= RMAX on the caster's level with the engine's own field/army lookups (grid 0x557020EC,
  field 0x557020DC, army HS 0x55771EB0, army = [hs+0x1C] - exactly as patch_ai_itemloot_antilure_v1);
  an army is a threat when
    owner = movsx byte [army+0x12] >= 0             (independents skipped)
    owner != AI player index [player+0xA6]           (own armies skipped)
    diplomatic state(AI, owner) != 2 (alliance)      (TPlayers 0x55754150, eax=[[game]+0x140], dl=a, cl=b;
                                                       peace 0 / war 1 / unknown 3 all count as non-allied)
    max(|dx|,|dy|) <= R(army), R = min over its units of GetMoves (VMT+0xD4) div HEX_MP + 1, capped at RMAX.
  R is measured from the THREAT army's own movement ("could that army reach the caster next turn?"), because the
  reserve exists to have casting points left when attacked; the caster's own speed is irrelevant to that.  Same
  reach estimate and constants as the anti-lure guard (HEX_MP 6, RMAX 8; Chebyshev distance on the offset hex grid
  never exceeds the true hex distance, so the test can only over-include = keeps the reserve when in doubt).

Dry-run default; --apply / --revert (revert = pre-end-enchant state, same as v1..v5 --revert) / --dis / --dll.
Applies from zero or upgrades v1..v5 in place.  v5's script refuses a v6 zone (to go back to v5: v6 --revert, then
v5 --apply).  Backup <game>\backup\AoWEPACK.dll.bak_aiendench6.
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(1, r"C:\Users\<user>\Desktop\Age of Wonders X - Claude\patch scripts")
from bakpath import bak_path, game_file
from patch_airdeath_fix_v1 import relocs
import patch_ai_end_enchant_v1 as V1
import patch_ai_end_enchant_v2 as V2
import patch_ai_end_enchant_v3 as V3
import patch_ai_end_enchant_v4 as V4
import patch_ai_end_enchant_v5 as V5

DLL = game_file("AoWEPACK.dll")
BASE, V2F = V1.BASE, V1.V2F
ZONE, ZONE_END = V1.ZONE, V1.ZONE_END
MAGIC = b"AEN6"
H_DELTA, PR, FIND = V1.H_DELTA, V1.PR, V1.FIND
SLOT, ORIG_PROC = V1.SLOT, V1.ORIG_PROC

RMAX, HEX_MP = 8, 6
MAPHOLD, GAME_CELL = 0x558E9494, 0x558FA040
GETGRID, GETFIELD, ARMYHS = 0x557020EC, 0x557020DC, 0x55771EB0
RELSTATE, GETUNIT = 0x55754150, 0x5578309C

OLD_KEEP = """    imul eax, eax, {KEEP}
    cdq
    mov  ecx, 100
    idiv ecx
    mov  [ebp-0x40], eax
"""
NEW_KEEP = OLD_KEEP + """    mov  eax, esi
    mov  edx, [ebp-4]
    mov  ecx, [ebp-0xc]
    call thr
    test eax, eax
    jnz  f_thr
    mov  dword ptr [ebp-0x40], 0
f_thr:
"""

# thr(eax = caster unit, edx = AI player, ecx = load delta) -> eax 1 = threat / 0.  Preserves ebx/esi/edi/ebp.
# frame: [esp+0]=x [+4]=y [+8]=lvl [+0xC]=grid [+0x10]=dy [+0x14]=dx [+0x18]=players [+0x1C]=aiIdx
#        [+0x20]=army [+0x24]=unit idx [+0x28]=minMP [+0x2C..2E]=GetLocation bytes
SRC_THR = """
thr:
    push ebx
    push esi
    push edi
    push ebp
    sub  esp, 0x30
    mov  ebp, ecx
    mov  esi, eax
    movzx eax, byte ptr [edx+0xA6]
    mov  [esp+0x1C], eax
    mov  eax, [ebp+{GAMEC}]
    test eax, eax
    jz   t_no
    mov  eax, [eax+0x140]
    test eax, eax
    jz   t_no
    mov  [esp+0x18], eax
    mov  dword ptr [esp+0x2C], 0
    lea  eax, [esp+0x2E]
    lea  ecx, [esp+0x2D]
    lea  edx, [esp+0x2C]
    push eax
    mov  eax, esi
    call {GL}
    movzx eax, byte ptr [esp+0x2C]
    mov  [esp], eax
    movzx eax, byte ptr [esp+0x2D]
    mov  [esp+4], eax
    movzx eax, byte ptr [esp+0x2E]
    mov  [esp+8], eax
    mov  eax, [ebp+{MAPC}]
    test eax, eax
    jz   t_no
    mov  eax, [eax]
    test eax, eax
    jz   t_no
    mov  eax, [eax+0x10]
    mov  edx, [esp+8]
    call {GETGRID}
    test eax, eax
    jz   t_no
    mov  [esp+0xC], eax
    mov  dword ptr [esp+0x10], -{RMAX}
t_ly:
    mov  dword ptr [esp+0x14], -{RMAX}
t_lx:
    mov  edx, [esp]
    add  edx, [esp+0x14]
    js   t_nx
    mov  ecx, [esp+0xC]
    cmp  edx, [ecx+0xC]
    jge  t_nx
    mov  ecx, [esp+4]
    add  ecx, [esp+0x10]
    js   t_nx
    mov  eax, [esp+0xC]
    cmp  ecx, [eax+0x10]
    jge  t_nx
    call {GETFIELD}
    test eax, eax
    jz   t_nx
    call {ARMYHS}
    test eax, eax
    jz   t_nx
    mov  eax, [eax+0x1C]
    test eax, eax
    jz   t_nx
    mov  [esp+0x20], eax
    movsx ecx, byte ptr [eax+0x12]
    test ecx, ecx
    jl   t_nx
    cmp  ecx, [esp+0x1C]
    je   t_nx
    mov  edx, [esp+0x1C]
    mov  eax, [esp+0x18]
    call {RELSTATE}
    cmp  al, 2
    je   t_nx
    mov  dword ptr [esp+0x24], 0
    mov  dword ptr [esp+0x28], 127
t_ul:
    mov  eax, [esp+0x20]
    mov  edx, [eax]
    call dword ptr [edx+0x54]
    cmp  [esp+0x24], eax
    jge  t_ud
    mov  eax, [esp+0x20]
    mov  edx, [esp+0x24]
    call {GETUNIT}
    inc  dword ptr [esp+0x24]
    test eax, eax
    jz   t_ul
    mov  edx, [eax]
    call dword ptr [edx+0xD4]
    movsx eax, al
    cmp  eax, [esp+0x28]
    jge  t_ul
    mov  [esp+0x28], eax
    jmp  t_ul
t_ud:
    mov  eax, [esp+0x28]
    test eax, eax
    jge  t_pos
    xor  eax, eax
t_pos:
    cdq
    mov  ecx, {HEX_MP}
    idiv ecx
    inc  eax
    cmp  eax, {RMAX}
    jle  t_rok
    mov  eax, {RMAX}
t_rok:
    mov  ecx, [esp+0x14]
    test ecx, ecx
    jge  t_ax
    neg  ecx
t_ax:
    cmp  ecx, eax
    jg   t_nx
    mov  ecx, [esp+0x10]
    test ecx, ecx
    jge  t_ay
    neg  ecx
t_ay:
    cmp  ecx, eax
    jg   t_nx
    mov  eax, 1
    jmp  t_out
t_nx:
    inc  dword ptr [esp+0x14]
    cmp  dword ptr [esp+0x14], {RMAX}
    jle  t_lx
    inc  dword ptr [esp+0x10]
    cmp  dword ptr [esp+0x10], {RMAX}
    jle  t_ly
t_no:
    xor  eax, eax
t_out:
    add  esp, 0x30
    pop  ebp
    pop  edi
    pop  esi
    pop  ebx
    ret
"""


def src_find():
    s = V5.src_find()
    assert s.count(OLD_KEEP) == 1
    s = s.replace(OLD_KEEP, NEW_KEEP)
    return s + SRC_THR


def build():
    hd = b"\xe8\x00\x00\x00\x00\x58\x2d" + struct.pack("<I", H_DELTA + 5) + b"\xc3"
    find_src = src_find().replace("{UPK_TEST}", V2.upk_test())
    fnd = V2.asm(find_src.format(MINC=V1.MANAINC, MUPK=V1.MANAUPK, CSL=V1.CLS_SPELLLIST, SLC=V1.SPELLLIST_CREATE,
                                 MASK=V1.LIST_MASK, LSP=V1.LISTSPELLS, SLN=V1.SL_COUNT, GH=V1.GETHERO, CAR=V1.CLS_ARMY,
                                 IC=V1.ISCLASS, KEEP=V1.KEEP_PCT, SLG=V1.SL_GET, CUS=V1.CLS_USPELL, CM=V1.CASTMANA,
                                 CI=V1.CANINSTANT, LSC=V1.LSTRCLR, OF=V1.OBJFREE, GU=V1.GETUNIT, US=V1.USTRENGTH,
                                 NT=V2.N_TURNS, GL=V2.GETLOC, GA=V2.GETARMY, HX=V2.HXRAD, CHR=V5.CLS_HERO,
                                 GAMEC=GAME_CELL, MAPC=MAPHOLD, RMAX=RMAX, HEX_MP=HEX_MP, GETGRID=GETGRID,
                                 GETFIELD=GETFIELD, ARMYHS=ARMYHS, RELSTATE=RELSTATE, GETUNIT=GETUNIT), FIND)
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
    if same(zone): return "v6"
    for nm, b in (("v5", V5.build), ("v4", lambda: V4.build(0)), ("v4-other", lambda: V4.build(1)),
                  ("v3", lambda: V3.build(0)), ("v3-other", lambda: V3.build(1)), ("v2", V2.build), ("v1", V1.build)):
        if same(b()): return nm
    return "DIFFERS"


OLDS = ("v1", "v2", "v3", "v3-other", "v4", "v4-other", "v5")


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
    print("  TEndTurnAIPA.Process slot %#x: %s | zone %#x..%#x %s (v6 %d B, ends %#x) | relocs %s | recruit ZONE_END %s"
          % (SLOT, sstate, ZONE, ZONE_END, zstate, len(zone), ZONE + len(zone), bad or "none",
             "n/a" if rz is None else hex(rz)))
    print("  KEEP_PCT %d (only under threat: non-allied army within reach, RMAX %d HEX_MP %d)  RES_PCT %d  MAXCASTS %d"
          % (V1.KEEP_PCT, RMAX, HEX_MP, V1.RES_PCT, V1.MAXCASTS))
    if a.dis:
        import capstone
        for lo, hi in ((H_DELTA, PR), (PR, FIND), (FIND, ZONE + len(zone))):
            print("  --")
            for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(zone[lo - ZONE:hi - ZONE].rstrip(b"\0") or b"\x90", lo):
                print("   %08X  %-22s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad or sstate.startswith("FOREIGN"): print("ABORT (slot/reloc)"); return 1
    if zstate == "DIFFERS": print("ABORT (zone not free)"); return 1
    if (sstate == "ours") != (zstate in OLDS + ("v6",)): print("ABORT (mixed state)"); return 1
    if not a.revert and rz is not None and rz > ZONE:
        print("ABORT: set ZONE_END in patch_ai_site_recruit_v1.py to %#x first" % ZONE); return 1
    if zstate in OLDS and not a.revert: print("  state: %s - upgrading %s -> v6 in place" % (zstate, zstate))
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
        bak = bak_path(a.dll, ".bak_aiendench6")
        if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    with open(a.dll, "r+b") as f: f.write(n)
    assert open(a.dll, "rb").read() == bytes(n); print("written", a.dll)
    return 0


if __name__ == "__main__":
    sys.exit(main())
