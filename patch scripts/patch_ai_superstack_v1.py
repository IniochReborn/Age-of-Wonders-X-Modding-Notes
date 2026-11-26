r"""
AI LEADER SUPERSTACK v1 (2026-10-20).  AoWEPACK.dll only.

User: "often the AI has stronger units near its leader, or adjacent to it, and won't merge with the leader, or keeps a
full party of weaker units with the leader and doesn't switch them out for nearby stronger units.  Can the AI create
'superstacks' like human players do - stack all their strongest nearby units with their leader?"

Implemented: the ADJACENT version (conservative).  At the START of every AI turn (units have full move points), before
the vanilla TInitializeAIPA work, the AI leader's army pulls in / swaps with the units of its own armies standing on the
6 hexes around it - one native move per AI step, exactly the move a human makes when dragging units between stacks:

  HOOK  TInitializeAIPA VMT slot Process 0x55719014 (was 0x55734A0C; the slot carries a reloc -> rebase-safe).
        TAIPlayerControl.Process 0x5573416C calls the current PA's Process; al = 1 keeps it current and it is called
        again once the player's TE queue is idle; al = 0 drops it.  So the cave issues ONE move per call (returns 1) and
        hands over to the vanilla Process (budget/AI init, returns 0) when nothing is left to do.
  MOVE  AoWE.MoveArmyXYL 0x5574A490 (eax = source TArmyHS, dl = unit-index selection mask, cl = x; push y, level,
        flag=0) - the human move path: pathfinder for the selected units' move-point table, GetMoveAction on the
        destination (own army -> TArmyCombineMoveTE), TE queued on the player's TE queue ([[0x558FA040]+0x23C]) - the
        same queue the AI's own TMultiMoveTE uses -> synced like every AI move.  Returns 0 when no TE was made (no
        path / busy) -> the cave stops for the day.
  RULES (per call, re-evaluated from scratch each time - deterministic, game state only):
    leader = [player+0xD4] (IsClass TLeader), L = [leader+4] (IsClass TArmy, owner [L+0x12] == [player+0xA6]).
    Neighbours: HSEngine InitHNWalk/WalkToNextHN (ring 1 of L's hex, same level, map bounds), army = field
    0x55771EB0, own army only.  Candidate unit u in a neighbour army A: not the leader, current move points > 0
    (unit VMT+0xD8), strength = TAbstractUnit.GetStrength(u, 0xFFFF) 0x5577F924 (ALL damage kinds).
    - L has room (< 8 units) -> move the strongest candidate into L.  If A stands in a city (field object 0x20108) it
      must keep >= MIN_GARRISON (2) units.
    - L full -> w = weakest non-leader unit of L with move points > 0; if best candidate strength >= w * (100 +
      SWAP_PCT)/100 and A has room (< 8) -> move w onto A's hex (next call then pulls the candidate into L - city
      garrison count is preserved by the swap).
    - Cap MAXMOVES moves per player per day: 16-slot table at .idata page slack 0x5590B5A0..0x5590B5E0 (beyond raw
      data -> zero at load; between leader-safety table B (ends 0x5590B590) and smokescreen W 0x5590B600):
      dword = day << 8 | count, slot = player index & 15.  MoveArmyXYL refusal -> count := MAXMOVES.
  Not done (reported): pulling units from further than adjacent (2-3 hexes), mission awareness of AI groups.
Zone AoWEPACK 0x55819400..0x55819C00 (header 'SST1' + the original slot dword).  All calls rel32; absolute data
([0x558FA040], class-ref cells, the table) via a call/pop delta -> position independent.
Dry-run default; --apply / --revert / --dis / --dll.  Backup <game>\backup\AoWEPACK.dll.bak_superstack.
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
from patch_airdeath_fix_v1 import relocs
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

DLL = game_file("AoWEPACK.dll")
BASE, V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x55819400, 0x55819C00     # after site-army SCB1 (ends 0x55819400); verified zero, no script owner
CODE = ZONE + 0x10
SLOT, ORIG_TARGET = 0x55719014, 0x55734A0C          # TInitializeAIPA.Process
TABLE = 0x5590B5A0
MAXMOVES, MIN_GARRISON, SWAP_PCT, ARMY_MAX = 8, 0, 15, 8   # 10/20 user: no city garrison minimum (was 2)
MAGIC = b"SST1"

GAME = 0x558FA040
ISCLASS, CLS_LEADER, CLS_ARMY = 0x557010C0, 0x557121F8, 0x557130AC
GETUNIT, USTR, GETARMYHS = 0x5578309C, 0x5577F924, 0x5578C8B8
GRID, FIELD, FIELDARMY = 0x557020EC, 0x557020DC, 0x55771EB0
INITWALK, NEXTWALK, MOVEXYL = 0x557026D4, 0x557026DC, 0x5574A490

# locals (esp-relative after the 4 pushes and sub esp, 0x90)
W, DELTA, PA, PLAYER, IDX, SLOTP, LARMY, LHS, LX, LY, LL, NL = 0x00, 0x20, 0x24, 0x28, 0x2C, 0x30, 0x34, 0x38, 0x3C, 0x40, 0x44, 0x48
WI, WS, BS, BA, BHS, BI, BCNT, BCITY, AX, AY, GRIDV, TMPU, LEADER = (0x4C, 0x50, 0x54, 0x58, 0x5C, 0x60, 0x64, 0x68,
                                                                   0x6C, 0x70, 0x74, 0x78, 0x7C)
FRAME = 0x90

ASM = f"""
ss:
    push ebx
    push esi
    push edi
    push ebp
    sub  esp, {FRAME:#x}
    mov  [esp+{PA:#x}], eax
    call dl0
dl0:
    pop  ebx
    sub  ebx, dl0
    mov  [esp+{DELTA:#x}], ebx
    mov  eax, [esp+{PA:#x}]
    mov  eax, [eax+0xc]
    test eax, eax
    jz   orig
    mov  eax, [eax+8]
    test eax, eax
    jz   orig
    mov  [esp+{PLAYER:#x}], eax
    movsx ecx, byte ptr [eax+0xa6]
    test ecx, ecx
    js   orig
    cmp  ecx, 15
    jg   orig
    mov  [esp+{IDX:#x}], ecx
    lea  edx, [ebx+{TABLE:#x}+ecx*4]
    mov  [esp+{SLOTP:#x}], edx
    mov  eax, [ebx+{GAME:#x}]
    test eax, eax
    jz   orig
    mov  eax, [eax+0x174]
    and  eax, 0xffffff
    mov  ecx, [edx]
    mov  esi, ecx
    shr  esi, 8
    cmp  esi, eax
    je   sameday
    shl  eax, 8
    mov  [edx], eax
    jmp  daydone
sameday:
    movzx ecx, cl
    cmp  ecx, {MAXMOVES}
    jge  orig
daydone:
    mov  eax, [esp+{PLAYER:#x}]
    mov  eax, [eax+0xd4]
    test eax, eax
    jz   orig
    mov  [esp+{LEADER:#x}], eax
    mov  edx, [ebx+{CLS_LEADER:#x}]
    call {ISCLASS:#x}
    test al, al
    jz   orig
    mov  eax, [esp+{LEADER:#x}]
    mov  eax, [eax+4]
    test eax, eax
    jz   orig
    mov  [esp+{LARMY:#x}], eax
    mov  edx, [ebx+{CLS_ARMY:#x}]
    call {ISCLASS:#x}
    test al, al
    jz   orig
    mov  eax, [esp+{LARMY:#x}]
    mov  ecx, [esp+{IDX:#x}]
    cmp  byte ptr [eax+0x12], cl
    jne  orig
    call {GETARMYHS:#x}
    test eax, eax
    jz   orig
    mov  [esp+{LHS:#x}], eax
    mov  edx, [eax]
    call dword ptr [edx+0x74]
    movsx eax, al
    mov  [esp+{LX:#x}], eax
    mov  eax, [esp+{LHS:#x}]
    mov  edx, [eax]
    call dword ptr [edx+0x78]
    movsx eax, al
    mov  [esp+{LY:#x}], eax
    mov  eax, [esp+{LHS:#x}]
    mov  edx, [eax]
    call dword ptr [edx+0x7c]
    movsx eax, al
    mov  [esp+{LL:#x}], eax
    mov  eax, [ebx+{GAME:#x}]
    mov  eax, [eax+0x10]
    test eax, eax
    jz   orig
    mov  edx, [esp+{LL:#x}]
    call {GRID:#x}
    test eax, eax
    jz   orig
    mov  [esp+{GRIDV:#x}], eax

    mov  esi, [esp+{LARMY:#x}]
    mov  eax, esi
    mov  edx, [eax]
    call dword ptr [edx+0x54]
    mov  [esp+{NL:#x}], eax
    mov  dword ptr [esp+{WI:#x}], -1
    mov  dword ptr [esp+{WS:#x}], 0x7fffffff
    xor  edi, edi
wl:
    cmp  edi, [esp+{NL:#x}]
    jge  wdone
    mov  edx, edi
    mov  eax, esi
    call {GETUNIT:#x}
    test eax, eax
    jz   wnx
    cmp  eax, [esp+{LEADER:#x}]
    je   wnx
    mov  [esp+{TMPU:#x}], eax
    mov  edx, [eax]
    call dword ptr [edx+0xd8]
    test al, al
    jle  wnx
    mov  eax, [esp+{TMPU:#x}]
    mov  dx, 0xffff
    call {USTR:#x}
    cmp  eax, [esp+{WS:#x}]
    jge  wnx
    mov  [esp+{WS:#x}], eax
    mov  [esp+{WI:#x}], edi
wnx:
    inc  edi
    jmp  wl
wdone:

    mov  dword ptr [esp+{BS:#x}], -1
    mov  dword ptr [esp+{BA:#x}], 0
    push 0
    lea  eax, [esp+4+{W:#x}]
    mov  edx, [esp+4+{LX:#x}]
    mov  ecx, [esp+4+{LY:#x}]
    call {INITWALK:#x}
nl_top:
    cmp  dword ptr [esp+{W:#x}+0xc], 1
    jg   scan_done
    mov  edx, [esp+{W:#x}+0x10]
    mov  ecx, [esp+{W:#x}+0x14]
    cmp  edx, [esp+{LX:#x}]
    jne  nl_go
    cmp  ecx, [esp+{LY:#x}]
    je   nl_next
nl_go:
    test edx, edx
    js   nl_next
    test ecx, ecx
    js   nl_next
    mov  eax, [esp+{GRIDV:#x}]
    cmp  edx, [eax+0xc]
    jge  nl_next
    cmp  ecx, [eax+0x10]
    jge  nl_next
    call {FIELD:#x}
    test eax, eax
    jz   nl_next
    mov  ebp, eax
    call {FIELDARMY:#x}
    test eax, eax
    jz   nl_next
    mov  [esp+{TMPU:#x}], eax
    mov  esi, [eax+0x1c]
    test esi, esi
    jz   nl_next
    cmp  esi, [esp+{LARMY:#x}]
    je   nl_next
    mov  eax, esi
    mov  edx, [ebx+{CLS_ARMY:#x}]
    call {ISCLASS:#x}
    test al, al
    jz   nl_next
    mov  ecx, [esp+{IDX:#x}]
    cmp  byte ptr [esi+0x12], cl
    jne  nl_next

    mov  eax, ebp
    mov  edx, 0x20108
    mov  ecx, [eax]
    call dword ptr [ecx+0x80]
    xor  ebp, ebp
    test eax, eax
    setnz cl
    movzx ebp, cl

    mov  eax, esi
    mov  edx, [eax]
    call dword ptr [edx+0x54]
    test ebp, ebp
    jz   cnt_city_ok
    cmp  eax, {MIN_GARRISON + 1}
    jl   nl_next
cnt_city_ok:
    cmp  dword ptr [esp+{NL:#x}], {ARMY_MAX}
    jl   cnt_ok
    cmp  eax, {ARMY_MAX}
    jge  nl_next
cnt_ok:
    push eax
    xor  edi, edi
ul:
    cmp  edi, [esp]
    jge  ul_done
    mov  edx, edi
    mov  eax, esi
    call {GETUNIT:#x}
    test eax, eax
    jz   ul_nx
    cmp  eax, [esp+4+{LEADER:#x}]
    je   ul_nx
    push eax
    mov  edx, [eax]
    call dword ptr [edx+0xd8]
    test al, al
    pop  eax
    jle  ul_nx
    mov  dx, 0xffff
    call {USTR:#x}
    cmp  eax, [esp+4+{BS:#x}]
    jle  ul_nx
    mov  [esp+4+{BS:#x}], eax
    mov  [esp+4+{BA:#x}], esi
    mov  ecx, [esp+4+{TMPU:#x}]
    mov  [esp+4+{BHS:#x}], ecx
    mov  [esp+4+{BI:#x}], edi
    mov  ecx, [esp]
    mov  [esp+4+{BCNT:#x}], ecx
    mov  [esp+4+{BCITY:#x}], ebp
    mov  ecx, [esp+4+{W:#x}+0x10]
    mov  [esp+4+{AX:#x}], ecx
    mov  ecx, [esp+4+{W:#x}+0x14]
    mov  [esp+4+{AY:#x}], ecx
ul_nx:
    inc  edi
    jmp  ul
ul_done:
    add  esp, 4
nl_next:
    lea  eax, [esp+{W:#x}]
    call {NEXTWALK:#x}
    jmp  nl_top
scan_done:
    cmp  dword ptr [esp+{BA:#x}], 0
    je   orig
    cmp  dword ptr [esp+{NL:#x}], {ARMY_MAX}
    jge  full

    cmp  dword ptr [esp+{BCITY:#x}], 0
    je   pull
    cmp  dword ptr [esp+{BCNT:#x}], {MIN_GARRISON + 1}
    jl   orig
pull:
    mov  ecx, [esp+{BI:#x}]
    mov  edx, 1
    shl  edx, cl
    push dword ptr [esp+{LY:#x}]
    push dword ptr [esp+4+{LL:#x}]
    push 0
    mov  ecx, [esp+0xc+{LX:#x}]
    mov  eax, [esp+0xc+{BHS:#x}]
    call {MOVEXYL:#x}
    jmp  moved
full:
    cmp  dword ptr [esp+{WI:#x}], 0
    jl   orig
    cmp  dword ptr [esp+{BCNT:#x}], {ARMY_MAX}
    jge  orig
    cmp  dword ptr [esp+{BCITY:#x}], 0
    je   swapok
    cmp  dword ptr [esp+{BCNT:#x}], {MIN_GARRISON}
    jl   orig
swapok:
    mov  eax, [esp+{WS:#x}]
    imul eax, eax, {100 + SWAP_PCT}
    mov  ecx, [esp+{BS:#x}]
    imul ecx, ecx, 100
    cmp  ecx, eax
    jl   orig
    mov  ecx, [esp+{WI:#x}]
    mov  edx, 1
    shl  edx, cl
    push dword ptr [esp+{AY:#x}]
    push dword ptr [esp+4+{LL:#x}]
    push 0
    mov  ecx, [esp+0xc+{AX:#x}]
    mov  eax, [esp+0xc+{LHS:#x}]
    call {MOVEXYL:#x}
moved:
    mov  edx, [esp+{SLOTP:#x}]
    test al, al
    jz   stopday
    inc  byte ptr [edx]
    mov  al, 1
    jmp  out
stopday:
    mov  byte ptr [edx], {MAXMOVES}
orig:
    mov  eax, [esp+{PA:#x}]
    mov  ebx, [esp+{DELTA:#x}]
    add  esp, {FRAME:#x}
    pop  ebp
    pop  edi
    pop  esi
    lea  ecx, [ebx+{ORIG_TARGET:#x}]
    pop  ebx
    jmp  ecx
out:
    add  esp, {FRAME:#x}
    pop  ebp
    pop  edi
    pop  esi
    pop  ebx
    ret
"""


def build():
    code = bytes(Ks(KS_ARCH_X86, KS_MODE_32).asm(ASM, CODE)[0])
    zone = MAGIC + struct.pack("<I", ORIG_TARGET) + bytes(8) + code
    assert len(zone) <= ZONE_END - ZONE, hex(len(zone))
    return zone, CODE


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true"); ap.add_argument("--dll", default=DLL); a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read())
    zone, entry = build()
    rd = lambda lo, hi: bytes(d[lo - V2F:hi - V2F])
    zl = rd(ZONE, ZONE_END)
    slot = struct.unpack("<I", rd(SLOT, SLOT + 4))[0]
    sstate = "vanilla" if slot == ORIG_TARGET else "v1" if slot == entry else "FOREIGN(%#x)" % slot
    zst = "zero" if not any(zl) else "v1" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else "DIFFERS"
    tbl_lo, tbl_hi = TABLE, TABLE + 0x40
    rl = relocs(bytes(d), BASE)
    bad = [hex(r) for r in rl if ZONE - 3 <= r < ZONE_END]
    slot_reloc = SLOT in rl
    print("AoWEPACK TInitializeAIPA.Process slot %#x %s | zone %#x %s (%d B, entry %#x) | table %#x..%#x | relocs in zone %s"
          " | slot reloc %s" % (SLOT, sstate, ZONE, zst, len(zone), entry, tbl_lo, tbl_hi, bad or "none", slot_reloc))
    if a.dis:
        import capstone
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(zone[0x10:], CODE):
            print("   %08X  %-22s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad or not slot_reloc or sstate.startswith("FOREIGN") or zst == "DIFFERS":
        print("ABORT"); return 1
    if (sstate, zst) not in {("vanilla", "zero"), ("v1", "v1")}: print("ABORT (mixed state)"); return 1
    n = bytearray(d)
    n[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE)
    if a.revert:
        n[SLOT - V2F:SLOT - V2F + 4] = struct.pack("<I", ORIG_TARGET)
    else:
        n[ZONE - V2F:ZONE - V2F + len(zone)] = zone
        n[SLOT - V2F:SLOT - V2F + 4] = struct.pack("<I", entry)
    if n == d: print("already %s" % ("reverted" if a.revert else "applied")); return 0
    if not (a.apply or a.revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if os.path.abspath(a.dll) == os.path.abspath(DLL):
        bak = bak_path(a.dll, ".bak_superstack")
        if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    with open(a.dll, "r+b") as f: f.write(n)
    assert open(a.dll, "rb").read() == bytes(n); print("written", a.dll)
    return 0


if __name__ == "__main__":
    sys.exit(main())
