r"""
AI DIPLOMACY - tributes, gift-sweetened peace/alliance offers, 'declare war on / break alliance with Y' suggestions
and threats toward HUMAN players (2026-10-19).  AoWEPACK.dll only.

RE (AoWEPACK, vanilla):
  Relation scale 0..100 (default 50): TRace.GetPlayerRelationValue 0x5574CDFC (eax=TRace, dl=player idx; idx<=0 -> 50;
    value includes the global offset [[game]+0x144]+0x10).  Bands (0x5575AC78): <=29 Hateful(0), 30-49 Wary(1),
    50-69 Neutral(2), 70-89 Polite(3), >=90 Friendly(4).  "Race relation" toward a player = the AI's race
    (TRaceList.Get 0x5574D1F0 on [[game]+0x144], index = [player+0xA5]) relation value toward that player index.
  Diplomatic state: 0x55754150 (eax=players [[game]+0x140], dl=a, cl=b) -> drPeace 0 / drWar 1 / drAlliance 2 / drUnknown 3.
  TDiplomaticActionType: 0 DeclareWar 1 OfferPeace 2 ProposeAlliance 3 SendMessage 4 ThreatenToAttack 5 MakeTribute
    6 BreakAlliance 7 SendMessageAsY 8 BreakAllianceWithY 9 DeclareWarToY.
  TDiplomaticAction: +0x10 from, +0x11 to, +0x12 Y, +0x13 type, +0x18 gold, +0x1C mana (ExecuteSend 0x5572E5C0 deducts
    them from the sender: gold [player+0xC4], mana [[player+0x54]+0x24]); VMT +0x60 Send(&errstr), +0x2C Release.
    TPlayer.CreateDiplomaticAction 0x55753828 (eax=player, dl=type, cl=target, push Y; ret 4; nil if [target+0x45]<>1)
    fills the default message.  Send refuses while the sender is busy (0x557516D0: pending TE / [player+0x48]).
  AI: TDiplomacyAIPA.Process 0x55730AF0 walks players [self+0x14] (from 1, skipping self + never-met) and calls
    ExecuteDiplomacy 0x557302B4 per player; vanilla only sends 0/1/2/6 (ProposeAlliance with Random(100)<30 when at
    peace).  Process stops for the frame when the AI becomes busy and resumes later at [self+0x14]+1.
  RNG: vanilla seeds System.RandSeed (cell 0x558FB720) = [game+0x22C] + day + aiIdx before Random (0x55701080), i.e.
    lockstep-deterministic.  We do the same with our own salt and RESTORE RandSeed afterwards.

PATCH (zone 0x55884000..0x55886000 'ADP1'; PEND table 16 dwords @ .idata page slack 0x5590BF40..0x5590BF80):
  H1 0x55730B6E (call ExecuteDiplomacy, 5 B) -> ED cave: vanilla ExecuteDiplomacy, then DECIDE one extra action for
     (AI, target) and send it.  If the AI is busy (vanilla just sent something) the action is deferred: PEND[ai] =
     day<<8 | idx+1 and [self+0x14] -= 1, so the next Process frame revisits this target with ONLY the extra action
     (vanilla is not re-run).  One extra action per (AI, human) per day, first success in this order:
       A tribute (type 5)  - target human, state Peace/Alliance, relation >= 70 (Polite+):
            Alliance+Friendly: 5 % windfall 100..250 (gold / mana / both, separate rolls);
            else Peace rel/10 % (Random(1000) < rel), Alliance rel/5 % (Random(1000) < 2*rel);
            Peace: Polite 5..25 / Friendly 10..50, gold OR mana;  Alliance: Polite 25..75 / Friendly 50..100,
            gold / mana / both (separate amounts).
       B suggestion (8 BreakAllianceWithY if the human is allied with Y, 9 DeclareWarToY if at peace with Y;
            skipped if the human is at war with Y or never met Y) - target human, AI not at war / unknown with the
            human; Y = every other living player (not independents) whose AI-race relation is Wary (30..49): 5 %,
            Hateful (<=29): 10 %; first success.  Payment = max(0, rel(AI race -> human) - rel(AI race -> Y)),
            x1.5 when Hateful; gold / mana / both (both = split in two).
       C threat (type 4) - target human, state Peace, relation Neutral 5 % / Wary 10 % / Hateful 15 %.
     All payments are capped at HALF of the AI's current gold / mana (tribute skipped if both caps give 0).
  H2 0x557307FE (vanilla AI DA send block, 8 B) -> GIFT cave: when the vanilla AI sends OfferPeace (1) or
     ProposeAlliance (2) to ANY player: rel/2 % (Random(200) < rel) to attach gold / mana / both, each 1..50
     (capped at half the AI's treasury), then the original Send.
Deterministic (seeded per day/AI/target, RandSeed restored); only synced game state; Delphi register convention;
PIC (call/pop delta) -> rebase-safe.  Dry-run default; --apply / --revert / --dis / --dll <scratch>.
Backup <game>\backup\AoWEPACK.dll.bak_aidiplo.
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r"C:\Users\<user>\Desktop\Age of Wonders X - Claude\patch scripts")
from bakpath import bak_path, game_file
from patch_airdeath_fix_v1 import relocs
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

DLL = game_file("AoWEPACK.dll")
BASE, V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x55884000, 0x55886000
MAGIC = b"ADP1"
ED_ENTRY, GIFT_ENTRY = ZONE + 0x40, ZONE + 0x600
PEND = 0x5590BF40                       # 16 dwords, .idata page slack (runtime zero)
SITE_H1, ORIG_H1 = 0x55730B6E, bytes.fromhex("e841f7ffff")                  # call ExecuteDiplomacy
SITE_H2, ORIG_H2 = 0x557307FE, bytes.fromhex("8d55d08b45d48b08")            # lea edx,[ebp-30] / mov eax,[ebp-2c] / mov ecx,[eax]
H2_BACK = 0x55730806                                                        # call [ecx+0x60]
EXECDIP, GETPLAYER, RELSTATE, GETRACE, GETPRV = 0x557302B4, 0x557544D0, 0x55754150, 0x5574D1F0, 0x5574CDFC
CREATEDA, BUSY, RANDOM, LSTRCLR = 0x55753828, 0x557516D0, 0x55701080, 0x55701140
GAMECELL, SEEDCELL = 0x558FA040, 0x558FB720
SALT1, SALT2 = 0x1D1A5EED, 0x2B2B6177

# ED cave frame: [ebp-4] self, -8 idx, -0xC delta, -0x10 P, -0x14 aiIdx, -0x18 &pend, -0x1C type, -0x20 gold,
# -0x24 mana, -0x28 Y, -0x2C rel, -0x30 race, -0x34 state, -0x38 saved seed, -0x3C mode, -0x40 lo, -0x44 span,
# -0x48 loopY, -0x4C seeded flag, -0x50 errstr, -0x54 count, -0x58 ry, -0x5C chance/tmp
SRC_ED = """
  push ebp
  mov ebp, esp
  sub esp, 0x60
  push ebx
  push esi
  push edi
  mov [ebp-4], eax
  movzx eax, dl
  mov [ebp-8], eax
  call L0
L0:
  pop eax
  sub eax, L0
  mov [ebp-0xC], eax
  mov eax, [ebp-4]
  mov eax, [eax+0xC]
  mov eax, [eax+8]
  mov [ebp-0x10], eax
  movzx ecx, byte ptr [eax+0xA6]
  mov [ebp-0x14], ecx
  cmp ecx, 15
  ja vanilla_only
  mov edx, [ebp-0xC]
  lea edx, [edx+ecx*4+{PEND}]
  mov [ebp-0x18], edx
  mov eax, [ebp-0xC]
  mov eax, [eax+{GAME}]
  mov eax, [eax+0x174]
  shl eax, 8
  mov ecx, [ebp-8]
  inc ecx
  or eax, ecx
  mov edx, [ebp-0x18]
  cmp [edx], eax
  jne normal
  mov dword ptr [edx], 0
  jmp extras
normal:
  mov eax, [ebp-4]
  mov edx, [ebp-8]
  call {EXECDIP}
extras:
  call decide
  cmp eax, -1
  je out
  mov [ebp-0x1C], eax
  mov eax, [ebp-0x10]
  call {BUSY}
  test al, al
  jz send
  mov eax, [ebp-0xC]
  mov eax, [eax+{GAME}]
  mov eax, [eax+0x174]
  shl eax, 8
  mov ecx, [ebp-8]
  inc ecx
  or eax, ecx
  mov edx, [ebp-0x18]
  mov [edx], eax
  mov eax, [ebp-4]
  dec byte ptr [eax+0x14]
  jmp out
send:
  mov eax, [ebp-0x28]
  push eax
  mov ecx, [ebp-8]
  mov edx, [ebp-0x1C]
  mov eax, [ebp-0x10]
  call {CREATEDA}
  test eax, eax
  jz out
  mov ebx, eax
  mov edx, [ebp-0x20]
  mov [ebx+0x18], edx
  mov edx, [ebp-0x24]
  mov [ebx+0x1C], edx
  mov dword ptr [ebp-0x50], 0
  lea edx, [ebp-0x50]
  mov eax, ebx
  mov ecx, [eax]
  call dword ptr [ecx+0x60]
  mov eax, ebx
  mov ecx, [eax]
  call dword ptr [ecx+0x2C]
  lea eax, [ebp-0x50]
  call {LSTRCLR}
  jmp out
vanilla_only:
  mov eax, [ebp-4]
  mov edx, [ebp-8]
  call {EXECDIP}
out:
  pop edi
  pop esi
  pop ebx
  mov esp, ebp
  pop ebp
  ret

rnd:
  call {RANDOM}
  ret
players:
  mov eax, [ebp-0xC]
  mov eax, [eax+{GAME}]
  mov eax, [eax+0x140]
  ret
amounts:
  cmp dword ptr [ebp-0x3C], 1
  je am_m
  mov eax, [ebp-0x44]
  call rnd
  add eax, [ebp-0x40]
  mov [ebp-0x20], eax
am_m:
  cmp dword ptr [ebp-0x3C], 0
  je am_x
  mov eax, [ebp-0x44]
  call rnd
  add eax, [ebp-0x40]
  mov [ebp-0x24], eax
am_x:
  ret
cap:
  mov ecx, [ebp-0x10]
  mov eax, [ecx+0xC4]
  sar eax, 1
  jns cp1
  xor eax, eax
cp1:
  cmp [ebp-0x20], eax
  jle cp2
  mov [ebp-0x20], eax
cp2:
  mov ecx, [ecx+0x54]
  mov eax, [ecx+0x24]
  sar eax, 1
  jns cp3
  xor eax, eax
cp3:
  cmp [ebp-0x24], eax
  jle cp4
  mov [ebp-0x24], eax
cp4:
  ret

decide:
  xor eax, eax
  mov [ebp-0x20], eax
  mov [ebp-0x24], eax
  mov [ebp-0x4C], eax
  mov dword ptr [ebp-0x28], -1
  call players
  mov edx, [ebp-8]
  call {GETPLAYER}
  test eax, eax
  jz none
  cmp byte ptr [eax+0xA7], 0
  jne none
  cmp byte ptr [eax+0x45], 1
  jne none
  call players
  mov edx, [ebp-0x14]
  mov ecx, [ebp-8]
  call {RELSTATE}
  movzx eax, al
  mov [ebp-0x34], eax
  cmp eax, 1
  je none
  cmp eax, 3
  je none
  mov eax, [ebp-0xC]
  mov eax, [eax+{GAME}]
  mov eax, [eax+0x144]
  mov edx, [ebp-0x10]
  movzx edx, byte ptr [edx+0xA5]
  call {GETRACE}
  test eax, eax
  jz none
  mov [ebp-0x30], eax
  mov edx, [ebp-8]
  call {GETPRV}
  mov [ebp-0x2C], eax
  mov ecx, [ebp-0xC]
  mov ecx, [ecx+{SEED}]
  mov eax, [ecx]
  mov [ebp-0x38], eax
  mov edx, [ebp-0xC]
  mov edx, [edx+{GAME}]
  mov eax, [edx+0x22C]
  mov edx, [edx+0x174]
  imul edx, edx, 0x9E37
  add eax, edx
  mov edx, [ebp-0x14]
  imul edx, edx, 0x101
  add eax, edx
  mov edx, [ebp-8]
  imul edx, edx, 0x1F
  add eax, edx
  add eax, {SALT}
  mov [ecx], eax
  mov dword ptr [ebp-0x4C], 1
  cmp dword ptr [ebp-0x2C], 70
  jl stepB
  cmp dword ptr [ebp-0x34], 2
  jne trib_roll
  cmp dword ptr [ebp-0x2C], 90
  jl trib_roll
  mov eax, 100
  call rnd
  cmp eax, 5
  jge trib_roll
  mov eax, 3
  call rnd
  mov [ebp-0x3C], eax
  mov dword ptr [ebp-0x40], 100
  mov dword ptr [ebp-0x44], 151
  call amounts
  jmp trib_done
trib_roll:
  mov eax, 1000
  call rnd
  mov edx, [ebp-0x2C]
  cmp dword ptr [ebp-0x34], 2
  jne tr1
  add edx, edx
tr1:
  cmp eax, edx
  jge stepB
  cmp dword ptr [ebp-0x34], 2
  je tr_ally
  mov dword ptr [ebp-0x40], 5
  mov dword ptr [ebp-0x44], 21
  cmp dword ptr [ebp-0x2C], 90
  jl tr2
  mov dword ptr [ebp-0x40], 10
  mov dword ptr [ebp-0x44], 41
tr2:
  mov eax, 2
  call rnd
  mov [ebp-0x3C], eax
  call amounts
  jmp trib_done
tr_ally:
  mov dword ptr [ebp-0x40], 25
  mov dword ptr [ebp-0x44], 51
  cmp dword ptr [ebp-0x2C], 90
  jl tr3
  mov dword ptr [ebp-0x40], 50
  mov dword ptr [ebp-0x44], 51
tr3:
  mov eax, 3
  call rnd
  mov [ebp-0x3C], eax
  call amounts
trib_done:
  call cap
  mov eax, [ebp-0x20]
  or eax, [ebp-0x24]
  jz stepB_clear
  mov eax, 5
  jmp done
stepB_clear:
  xor eax, eax
  mov [ebp-0x20], eax
  mov [ebp-0x24], eax
stepB:
  call players
  mov edx, [eax]
  call dword ptr [edx+0x54]
  mov [ebp-0x54], eax
  mov dword ptr [ebp-0x48], 1
lpY:
  mov eax, [ebp-0x48]
  cmp eax, [ebp-0x54]
  jge stepC
  cmp eax, [ebp-0x14]
  je nextY
  cmp eax, [ebp-8]
  je nextY
  call players
  mov edx, [ebp-0x48]
  call {GETPLAYER}
  test eax, eax
  jz nextY
  cmp byte ptr [eax+0x45], 1
  jne nextY
  mov eax, [ebp-0x30]
  mov edx, [ebp-0x48]
  call {GETPRV}
  mov [ebp-0x58], eax
  cmp eax, 50
  jge nextY
  call players
  mov edx, [ebp-8]
  mov ecx, [ebp-0x48]
  call {RELSTATE}
  movzx eax, al
  cmp eax, 1
  je nextY
  cmp eax, 3
  je nextY
  mov ecx, 9
  cmp eax, 2
  jne sg1
  mov ecx, 8
sg1:
  mov [ebp-0x1C], ecx
  mov dword ptr [ebp-0x5C], 5
  cmp dword ptr [ebp-0x58], 29
  jg sg2
  mov dword ptr [ebp-0x5C], 10
sg2:
  mov eax, 100
  call rnd
  cmp eax, [ebp-0x5C]
  jge nextY
  mov eax, [ebp-0x2C]
  sub eax, [ebp-0x58]
  jns sg3
  xor eax, eax
sg3:
  cmp dword ptr [ebp-0x58], 29
  jg sg4
  lea eax, [eax+eax*2]
  sar eax, 1
sg4:
  mov [ebp-0x5C], eax
  mov eax, 3
  call rnd
  cmp eax, 1
  je sg_m
  jb sg_g
  mov eax, [ebp-0x5C]
  mov edx, eax
  sar edx, 1
  sub eax, edx
  mov [ebp-0x20], eax
  mov [ebp-0x24], edx
  jmp sg_c
sg_g:
  mov eax, [ebp-0x5C]
  mov [ebp-0x20], eax
  jmp sg_c
sg_m:
  mov eax, [ebp-0x5C]
  mov [ebp-0x24], eax
sg_c:
  call cap
  mov eax, [ebp-0x48]
  mov [ebp-0x28], eax
  mov eax, [ebp-0x1C]
  jmp done
nextY:
  inc dword ptr [ebp-0x48]
  jmp lpY
stepC:
  cmp dword ptr [ebp-0x34], 0
  jne none
  mov eax, [ebp-0x2C]
  cmp eax, 70
  jge none
  mov dword ptr [ebp-0x5C], 5
  cmp eax, 50
  jge th1
  mov dword ptr [ebp-0x5C], 10
  cmp eax, 30
  jge th1
  mov dword ptr [ebp-0x5C], 15
th1:
  mov eax, 100
  call rnd
  cmp eax, [ebp-0x5C]
  jge none
  mov eax, 4
  jmp done
none:
  mov eax, -1
done:
  cmp dword ptr [ebp-0x4C], 0
  je dn
  mov ecx, [ebp-0xC]
  mov ecx, [ecx+{SEED}]
  mov edx, [ebp-0x38]
  mov [ecx], edx
dn:
  ret
"""

# GIFT cave (inside ExecuteDiplomacy's frame: ebp = its frame, [ebp-0x2C] = DA, edi = self)
SRC_GIFT = """
  pushad
  sub esp, 0x20
  call G0
G0:
  pop ebx
  sub ebx, G0
  mov esi, [ebp-0x2C]
  mov al, [esi+0x13]
  cmp al, 1
  je g_go
  cmp al, 2
  jne g_out
g_go:
  mov eax, [edi+0xC]
  mov eax, [eax+8]
  mov [esp], eax
  mov eax, [ebx+{GAME}]
  mov eax, [eax+0x144]
  mov edx, [esp]
  movzx edx, byte ptr [edx+0xA5]
  call {GETRACE}
  test eax, eax
  jz g_out
  movsx edx, byte ptr [esi+0x11]
  call {GETPRV}
  mov [esp+8], eax
  mov ecx, [ebx+{SEED}]
  mov eax, [ecx]
  mov [esp+4], eax
  mov edx, [ebx+{GAME}]
  mov eax, [edx+0x22C]
  mov edx, [edx+0x174]
  imul edx, edx, 0x9E37
  add eax, edx
  mov edx, [esp]
  movzx edx, byte ptr [edx+0xA6]
  imul edx, edx, 0x101
  add eax, edx
  movsx edx, byte ptr [esi+0x11]
  imul edx, edx, 0x1F
  add eax, edx
  add eax, {SALT}
  mov [ecx], eax
  mov eax, 200
  call {RANDOM}
  cmp eax, [esp+8]
  jge g_rest
  mov eax, 3
  call {RANDOM}
  mov [esp+0xC], eax
  xor eax, eax
  mov [esp+0x10], eax
  mov [esp+0x14], eax
  cmp dword ptr [esp+0xC], 1
  je g_m
  mov eax, 50
  call {RANDOM}
  inc eax
  mov [esp+0x10], eax
g_m:
  cmp dword ptr [esp+0xC], 0
  je g_cap
  mov eax, 50
  call {RANDOM}
  inc eax
  mov [esp+0x14], eax
g_cap:
  mov ecx, [esp]
  mov eax, [ecx+0xC4]
  sar eax, 1
  jns gc1
  xor eax, eax
gc1:
  cmp [esp+0x10], eax
  jle gc2
  mov [esp+0x10], eax
gc2:
  mov ecx, [ecx+0x54]
  mov eax, [ecx+0x24]
  sar eax, 1
  jns gc3
  xor eax, eax
gc3:
  cmp [esp+0x14], eax
  jle gc4
  mov [esp+0x14], eax
gc4:
  mov eax, [esp+0x10]
  mov [esi+0x18], eax
  mov eax, [esp+0x14]
  mov [esi+0x1C], eax
g_rest:
  mov ecx, [ebx+{SEED}]
  mov eax, [esp+4]
  mov [ecx], eax
g_out:
  add esp, 0x20
  popad
  lea edx, [ebp-0x30]
  mov eax, [ebp-0x2C]
  mov ecx, [eax]
  jmp {BACK}
"""


def asm(src, at):
    return bytes(Ks(KS_ARCH_X86, KS_MODE_32).asm(src, at)[0])


def build():
    ed = asm(SRC_ED.format(PEND=PEND, GAME=GAMECELL, SEED=SEEDCELL, SALT=SALT1, EXECDIP=EXECDIP, BUSY=BUSY,
                           CREATEDA=CREATEDA, LSTRCLR=LSTRCLR, RANDOM=RANDOM, GETPLAYER=GETPLAYER, RELSTATE=RELSTATE,
                           GETRACE=GETRACE, GETPRV=GETPRV), ED_ENTRY)
    gift = asm(SRC_GIFT.format(GAME=GAMECELL, SEED=SEEDCELL, SALT=SALT2, GETRACE=GETRACE, GETPRV=GETPRV,
                               RANDOM=RANDOM, BACK=H2_BACK), GIFT_ENTRY)
    assert ED_ENTRY + len(ed) <= GIFT_ENTRY, hex(len(ed))
    zone = bytearray(GIFT_ENTRY - ZONE + len(gift))
    zone[0:4] = MAGIC
    zone[4:4 + len(ORIG_H1) + len(ORIG_H2)] = ORIG_H1 + ORIG_H2
    zone[ED_ENTRY - ZONE:ED_ENTRY - ZONE + len(ed)] = ed
    zone[GIFT_ENTRY - ZONE:GIFT_ENTRY - ZONE + len(gift)] = gift
    assert len(zone) <= ZONE_END - ZONE
    s1 = b"\xe8" + struct.pack("<i", ED_ENTRY - (SITE_H1 + 5))
    s2 = b"\xe9" + struct.pack("<i", GIFT_ENTRY - (SITE_H2 + 5)) + b"\x90" * 3
    return bytes(zone), {SITE_H1: (ORIG_H1, s1), SITE_H2: (ORIG_H2, s2)}, len(ed), len(gift)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true"); ap.add_argument("--dll", default=DLL); a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read())
    zone, sites, led, lgift = build()
    zl = bytes(d[ZONE - V2F:ZONE_END - V2F])
    zstate = "zero" if not any(zl) else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else "DIFFERS"
    states = {}
    for s, (o, n) in sites.items():
        b = bytes(d[s - V2F:s - V2F + len(o)])
        states[s] = "vanilla" if b == o else "ours" if b == n else "FOREIGN"
    bad = [hex(r) for r in relocs(bytes(d), BASE) if ZONE - 3 <= r < ZONE_END
           or any(s - 3 <= r < s + len(o) for s, (o, n) in sites.items())]
    for s in sites: print("  site %#x %s" % (s, states[s]))
    print("  zone %#x..%#x %s (ED %d B @%#x, GIFT %d B @%#x) | PEND %#x | relocs %s"
          % (ZONE, ZONE_END, zstate, led, ED_ENTRY, lgift, GIFT_ENTRY, PEND, bad or "none"))
    if a.dis:
        import capstone
        for lo, n in ((ED_ENTRY, led), (GIFT_ENTRY, lgift)):
            print("  --")
            for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(zone[lo - ZONE:lo - ZONE + n], lo):
                print("   %08X  %-18s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    st = set(states.values())
    if bad or "FOREIGN" in st: print("ABORT (site/reloc)"); return 1
    if zstate == "DIFFERS": print("ABORT (zone not free)"); return 1
    if len(st | {zstate.replace("zero", "vanilla")}) > 1: print("ABORT (mixed state)"); return 1
    n = bytearray(d)
    if a.revert:
        for s, (o, _) in sites.items(): n[s - V2F:s - V2F + len(o)] = o
        n[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE)
    else:
        n[ZONE - V2F:ZONE - V2F + len(zone)] = zone
        for s, (_, p) in sites.items(): n[s - V2F:s - V2F + len(p)] = p
    if n == d: print("already %s" % ("reverted" if a.revert else "applied")); return 0
    if not (a.apply or a.revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if os.path.abspath(a.dll) == os.path.abspath(DLL):
        bak = bak_path(a.dll, ".bak_aidiplo")
        if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    with open(a.dll, "r+b") as f: f.write(n)
    assert open(a.dll, "rb").read() == bytes(n); print("written", a.dll)
    return 0


if __name__ == "__main__":
    sys.exit(main())
