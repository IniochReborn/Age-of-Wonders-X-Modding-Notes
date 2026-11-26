#!/usr/bin/env python3
r"""AI attack-of-opportunity awareness in TACTICAL combat (AoWTCPCK.dll).

PROBLEM (user 2026-08-15): the tactical AI does not model AoO at all — e.g. a
leader with a swordsman ADJACENT walks away (eating the AoO) to attack an
IDENTICAL swordsman farther off. Wanted: a moderate, proportional bias — the
adjacent target should win against an equal one, but a single swordsman must
not freeze a hero when something genuinely better is in reach.

MECHANISM (RE): all candidate moves live in [cai+0x14]; the phase-4 tail
(EvalBattle) deletes type-4 temps, applies group bonuses ([move+0x10]/4 into
[move+0xC]) and then INSERTION-SORTS the list descending by [move+0xC]
(@0x41A3C0); phase 5 executes best-first. Move record: +4 type (0=move,
1=touch, 2=melee, 3=approach, 5=ranged/cast-from-position), +0x14 unit HS
(pos via vcalls +0x74/+0x78), +0x1C/+0x1E dest x/y words (what the executor
feeds SetDestinationPos), +0xC value.

PATCH: hook @0x41A3C0 (12 B: 8b45fc 8b4014 8b4008 83e801 — the sort prologue)
-> cave @0x438660: one pass over the move list BEFORE the sort. For each move
whose unit currently stands ADJACENT (dHXtoRad<=1) to a LIVING enemy
([cai+0x10] entries with ([obj+0x47]&9)==0):
  - types 1/2 (touch/melee): provoked iff dist(unit,dest) > 1
    (attacking the adjacent enemy itself = no movement = no AoO);
  - types 0/3 (move/approach): provoked iff dist(unit,dest) > 0;
  - type 3 (shoot now): never (fires from position); type 5 (WALK to a firing
    spot, corrected 2026-09-20 -- see patch_aoo_type5_fix_v1.py) follows the move rules.
Provoked positive values are scaled: value = value * AOO_PCT / 100.
Percentage bias => never freezes: a big enough prize still wins.
TACTICAL-ONLY (TCAI); fast/auto combat untouched. No absolute addresses in
the cave (fully rebase-proof: field offsets + rel32 thunk call only).

Usage: --apply | --revert | --status.
Backup AoWTCPCK.dll.bak_aoo (full file, first apply).
"""
import os, struct, sys

GAME = os.environ.get('AOW_GAME_DIR') or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TC  = os.path.join(GAME, 'AoWTCPCK.dll')
BAK = TC + '.bak_aoo'
TC_D = 0x400C00

# v4 (2026-08-15, from live recorder data): move values are in a value^2-ish
# currency (~98K for an approach on a ~300-value swordsman) while a melee
# attack on a defended equal target scores NEGATIVE (~-128, retaliation fear)
# -- percent scaling alone can NEVER make the adjacent attack win; that is
# also exactly why vanilla walks away. v4 therefore works subtractively in
# the move-value currency:
#   threatSum = sum over adjacent living enemies of min(rawValue,RAW_CAP)^2
#   eff       = threatSum * f100 / 100     (f100 = 200 - ownHP%, frailty)
#   provoked moves (type0/3 dist>0, type1/2 dist>1), positive values only:
#       val = max(val - eff*PEN_PCT/100, val*MIN_KEEP/100)   (never freezes)
#   safe attacks (type1/2 dist<=1 = hit the adjacent enemy, type5 = ranged/
#   cast from position), ANY value incl. negative:
#       val += min(eff*BOOST_PCT/100, BOOST_CAP)
# The boost lets "attack the thing next to you" outbid "walk off and eat the
# AoO" from a negative base; the cap stops it from turning into suicide-
# charges against adjacent dragons.
# WARNING 2026-10-04 (laptop): the "hits/maxhits are FIELDS [o+0x88]/[o+0x84]" claim below was
# WRONG - TTacticalCombatUnit is 0x68 bytes; +0x84/+0x88 are the VMT slots
# GetHits/GetHitPoints.  The field reads at cave+0xF4 read past the object
# (AV -> "Error during Add Group Bonuses" soft-lock).  Fixed as a LAYERED patch
# by patch_aoo_hits_vcall_v1.py (call-out at 0x438754 -> SUB 0x43C200); if this
# script is ever re-applied from scratch, emit the virtual calls instead.
# (original note:) v3's f100 vcall bug fixed: hits/maxhits
# are FIELDS [o+0x88]/[o+0x84], not vcalls.
PEN_PCT   = 80              # % of eff subtracted from provoked moves
BOOST_PCT = 80              # % of eff added to safe attacks
BOOST_CAP = 150000          # absolute cap on the safe-attack boost
MIN_KEEP  = 25              # provoked moves keep at least this % of value
RAW_CAP   = 2000            # cap on raw enemy value before squaring
# v5: ACTIVE selector bias at the CheckUnit melee score site (SITE2). Target
# selection compares tcDVtoDEV-scale scores per candidate target and breaks
# ties by list order -- so vs two identical enemies it often picks the FAR
# one, and move generation then never even creates the adjacent-attack move.
# Fix: if self stands adjacent to living enemies and the EVALUATED target is
# NOT adjacent, score -= sum(adjacent raw values, capped)/CHK_DIV (~75 per
# swordsman, ~153 per cavalier in DEV currency). Ties break toward the
# adjacent enemy; genuinely better far targets still win.
CHK_DIV   = 4

SITE      = 0x41a3c0
SITE_ORIG = bytes.fromhex('8b45fc8b40148b400883e801')   # 12 B (sort prologue)
# 2nd RECORD-only hook: CheckUnit melee-tail score store @0x415551
# (mov [ebp-0x64],eax; mov eax,[ebp+0x10]) -- logs every (self,target,score)
# melee evaluation so we can see which targets are considered and gated.
SITE2      = 0x415551
SITE2_ORIG = bytes.fromhex('89459c8b4510')              # 6 B
CAVE      = 0x438660
DHX       = 0x4022a4        # thunk HSEngine.dHXtoRad(eax=x1,edx=y1,ecx=x2,push y2)

# --- diagnostic recorder (set RECORD=False for release build) ---------------
# Ring buffer in TCPCK's OWN BSS page slack (BSS vsz ends 0x46c0a1, page runs
# to 0x46d000; RW, zero-init, no file backing). PIC via call/pop module delta.
# Header: +0 count (monotonic; slot=count%REC_N) +4 passes. Records 32 B:
#  per-enemy: unitHS, enemyObj, rawValue, pen, f100, keepAfter, moveVal, i<<8|type
#  final:     unitHS, -1, valueBefore, valueAfter, f100, keepFloored, 0, i<<8|type
RECORD    = False
REC       = 0x46c100
REC_N     = 100             # 0x10 + 100*32 = 0xc90, ends 0x46cd90 < 0x46d000

def rd():
    with open(TC,'rb') as f: return bytearray(f.read())
def wr(d):
    with open(TC,'wb') as f: f.write(bytes(d))

class Asm:
    def __init__(self, base):
        self.base=base; self.b=bytearray(); self.lab={}; self.f8=[]; self.f32=[]
    def here(self): return self.base+len(self.b)
    def db(self,*x): self.b+=bytes(x)
    def raw(self,x): self.b+=x
    def dd(self,v): self.b+=struct.pack('<I',v&0xFFFFFFFF)
    def label(self,n): self.lab[n]=self.here()
    def j8(self,op,n): self.db(op); self.f8.append((len(self.b),n)); self.db(0)
    def jcc32(self,cc,n): self.db(0x0F,cc); self.f32.append((len(self.b),n)); self.dd(0)
    def jmp32(self,n): self.db(0xE9); self.f32.append((len(self.b),n)); self.dd(0)
    def call(self,tgt): self.db(0xE8); self.dd(tgt-(self.here()+4))
    def done(self):
        for pos,n in self.f8:
            rel=self.lab[n]-(self.base+pos+1)
            assert -128<=rel<=127,(n,rel)
            self.b[pos]=rel&0xFF
        for pos,n in self.f32:
            self.b[pos:pos+4]=struct.pack('<i',self.lab[n]-(self.base+pos+4))
        return bytes(self.b)

def build_cave():
    a=Asm(CAVE)
    # frame: [esp]=i +4=ux +8=uy +C=j +0x10=threatSum +0x14=flag(1=prov,2=safe)
    #        +0x18=k/floor +0x1C=f100 +0x20=delta +0x24=raw/before +0x28=eff +0x2C=after
    a.db(0x53,0x56,0x57)                 # push ebx,esi,edi
    a.db(0x8B,0x5D,0xFC)                 # ebx=[ebp-4] cai
    a.db(0x83,0xEC,0x30)
    if RECORD:                           # module delta = runtime - preferred (PIC)
        a.call(a.here()+5)
        a.label('pic')
        a.db(0x58)
        a.db(0x2D); a.dd(a.lab['pic'])
        a.db(0x89,0x44,0x24,0x20)
        a.db(0x8B,0xD0)
        a.db(0xFF,0x82); a.dd(REC+4)     # passes++
    a.db(0xC7,0x04,0x24); a.dd(0)        # i=0
    a.label('L')
    a.db(0x8B,0x43,0x14)                 # move list
    a.db(0x8B,0x48,0x08)
    a.db(0x39,0x0C,0x24)
    a.jcc32(0x8D,'done')
    a.db(0x8B,0x14,0x24)
    a.db(0x8B,0x40,0x04)
    a.db(0x8B,0x3C,0x90)                 # edi=move
    a.db(0x0F,0xB6,0x47,0x04)            # type
    a.db(0x83,0xF8,0x04)
    a.jcc32(0x84,'next')                 # type4 temp-deleted: skip
    a.db(0x8B,0x77,0x14)                 # esi=unit HS
    a.db(0x85,0xF6); a.jcc32(0x84,'next')
    a.db(0x8B,0xC6); a.db(0x8B,0x10); a.db(0xFF,0x52,0x74)
    a.db(0x0F,0xBE,0xC0)
    a.db(0x89,0x44,0x24,0x04)            # ux
    a.db(0x8B,0xC6); a.db(0x8B,0x10); a.db(0xFF,0x52,0x78)
    a.db(0x0F,0xBE,0xC0)
    a.db(0x89,0x44,0x24,0x08)            # uy
    # ---- classify: flag = 1 provoked / 2 safe attack / skip ----
    a.db(0x0F,0xB6,0x47,0x04)
    a.db(0x83,0xF8,0x03)                 # 2026-09-20: type 3 = SHOOT NOW (safe); type 5 = WALK to a firing spot (move rules)
    a.j8(0x75,'dchk')
    a.db(0xC7,0x44,0x24,0x14); a.dd(2)   # type3: safe (fires from position)
    a.jmp32('fdone')
    a.label('dchk')
    a.db(0x0F,0xB7,0x47,0x1E)            # dest y
    a.db(0x50)
    a.db(0x0F,0xB7,0x4F,0x1C)            # ecx=dest x
    a.db(0x8B,0x54,0x24,0x0C)            # edx=uy (shifted)
    a.db(0x8B,0x44,0x24,0x08)            # eax=ux (shifted)
    a.call(DHX)
    a.db(0x33,0xD2)
    a.db(0x8A,0x4F,0x04)
    a.db(0x80,0xF9,0x01); a.j8(0x72,'th')
    a.db(0x80,0xF9,0x02); a.j8(0x77,'th')
    a.db(0xB2,0x01)
    a.label('th')
    a.db(0x3B,0xC2)
    a.j8(0x7F,'prov')                    # dist>threshold: provokes
    a.db(0x80,0xF9,0x01); a.jcc32(0x82,'next')   # type0 stationary: skip
    a.db(0x80,0xF9,0x02); a.jcc32(0x87,'next')   # type3 stationary: skip
    a.db(0xC7,0x44,0x24,0x14); a.dd(2)   # type1/2 dist<=1: safe attack
    a.j8(0xEB,'fdone')
    a.label('prov')
    a.db(0xC7,0x44,0x24,0x14); a.dd(1)
    a.label('fdone')
    # ---- own-HP frailty f100 = 200 - ownHP% (default 100) ----
    a.db(0xC7,0x44,0x24,0x1C); a.dd(100)
    a.db(0xC7,0x44,0x24,0x18); a.dd(0)   # k=0
    a.label('O')
    a.db(0x8B,0x43,0x08)                 # own units list [cai+8]
    a.db(0x8B,0x48,0x08)
    a.db(0x39,0x4C,0x24,0x18)
    a.jcc32(0x8D,'Od')
    a.db(0x8B,0x54,0x24,0x18)
    a.db(0x8B,0x40,0x04)
    a.db(0x8B,0x04,0x90)                 # own obj
    a.db(0x85,0xC0); a.j8(0x74,'On')
    a.db(0x39,0x70,0x60)                 # cmp [o+0x60],esi (our HS?)
    a.j8(0x75,'On')
    a.db(0x8B,0x88,0x84,0x00,0x00,0x00)  # ecx=[o+0x84] maxhits (FIELD)
    a.db(0x8B,0x80,0x88,0x00,0x00,0x00)  # eax=[o+0x88] hits    (FIELD)
    a.db(0x85,0xC9); a.j8(0x7E,'Od')     # max<=0 -> default
    a.db(0x6B,0xC0,0x64)                 # hits*100
    a.db(0x99); a.db(0xF7,0xF9)          # /max = hp%
    a.db(0x83,0xF8,0x64); a.j8(0x7E,'h1')
    a.db(0xB8,0x64,0x00,0x00,0x00)       # clamp 100
    a.label('h1')
    a.db(0x85,0xC0); a.j8(0x79,'h2')
    a.db(0x33,0xC0)                      # clamp 0
    a.label('h2')
    a.db(0xB9,0xC8,0x00,0x00,0x00)       # 200
    a.db(0x2B,0xC8)
    a.db(0x89,0x4C,0x24,0x1C)            # f100
    a.j8(0xEB,'Od')
    a.label('On')
    a.db(0xFF,0x44,0x24,0x18)
    a.jmp32('O')
    a.label('Od')
    # ---- scan enemies, threatSum = sum of min(raw,RAW_CAP)^2 ----
    a.db(0xC7,0x44,0x24,0x10); a.dd(0)   # threatSum=0
    a.db(0xC7,0x44,0x24,0x0C); a.dd(0)   # j=0
    a.label('E')
    a.db(0x8B,0x43,0x10)                 # enemies
    a.db(0x8B,0x48,0x08)
    a.db(0x39,0x4C,0x24,0x0C)
    a.jcc32(0x8D,'Ed')
    a.db(0x8B,0x54,0x24,0x0C)
    a.db(0x8B,0x40,0x04)
    a.db(0x8B,0x34,0x90)                 # esi=enemy obj
    a.db(0x85,0xF6); a.jcc32(0x84,'En')
    a.db(0x8A,0x4E,0x47)
    a.db(0x80,0xE1,0x09)
    a.jcc32(0x85,'En')                   # dead|fled
    a.db(0x8B,0x46,0x60)                 # enemy HS
    a.db(0x85,0xC0); a.jcc32(0x84,'En')
    a.db(0x8B,0x10); a.db(0xFF,0x52,0x78)     # ey
    a.db(0x0F,0xBE,0xC0)
    a.db(0x50)
    a.db(0x8B,0x46,0x60)
    a.db(0x8B,0x10); a.db(0xFF,0x52,0x74)     # ex
    a.db(0x0F,0xBE,0xC8)
    a.db(0x8B,0x54,0x24,0x0C)            # uy (shifted)
    a.db(0x8B,0x44,0x24,0x08)            # ux (shifted)
    a.call(DHX)
    a.db(0x83,0xF8,0x01)
    a.jcc32(0x8F,'En')                   # not adjacent
    a.db(0x8B,0xC6); a.db(0x8B,0x10); a.db(0xFF,0x52,0x5C)   # raw value
    if RECORD: a.db(0x89,0x44,0x24,0x24)
    a.db(0x85,0xC0); a.jcc32(0x8E,'En')  # <=0: ignore
    a.db(0x3D); a.dd(RAW_CAP)
    a.j8(0x7E,'q1')
    a.db(0xB8); a.dd(RAW_CAP)
    a.label('q1')
    a.db(0x0F,0xAF,0xC0)                 # raw^2 (<=4M, no overflow)
    a.db(0x01,0x44,0x24,0x10)            # threatSum +=
    if RECORD:                           # per-enemy record
        a.db(0x8B,0x54,0x24,0x20)
        a.db(0x8B,0x82); a.dd(REC)
        a.db(0xFF,0x82); a.dd(REC)
        a.db(0xB9); a.dd(REC_N)
        a.db(0x33,0xD2); a.db(0xF7,0xF1)
        a.db(0xC1,0xE2,0x05)
        a.db(0x03,0x54,0x24,0x20)
        a.db(0x8B,0x47,0x14); a.db(0x89,0x82); a.dd(REC+0x10)   # unit HS
        a.db(0x89,0xB2); a.dd(REC+0x14)                          # enemy obj
        a.db(0x8B,0x44,0x24,0x24); a.db(0x89,0x82); a.dd(REC+0x18)  # raw
        a.db(0x8B,0x44,0x24,0x10); a.db(0x89,0x82); a.dd(REC+0x1C)  # sum so far
        a.db(0x8B,0x44,0x24,0x1C); a.db(0x89,0x82); a.dd(REC+0x20)  # f100
        a.db(0xC7,0x82); a.dd(REC+0x24); a.dd(0)
        a.db(0x8B,0x47,0x0C);      a.db(0x89,0x82); a.dd(REC+0x28)  # move value
        a.db(0x8B,0x04,0x24); a.db(0xC1,0xE0,0x08)
        a.db(0x0F,0xB6,0x4F,0x04); a.db(0x0B,0xC1)
        a.db(0x89,0x82); a.dd(REC+0x2C)
    a.label('En')
    a.db(0xFF,0x44,0x24,0x0C)
    a.jmp32('E')
    a.label('Ed')
    a.db(0x8B,0x44,0x24,0x10)            # threatSum
    a.db(0x85,0xC0); a.jcc32(0x84,'next')
    a.db(0xF7,0x6C,0x24,0x1C)            # imul dword [esp+0x1C] -> edx:eax = sum*f100
    a.db(0xB9,0x64,0x00,0x00,0x00)
    a.db(0xF7,0xF9)                      # /100 = eff (<=48M)
    a.db(0x89,0x44,0x24,0x28)
    a.db(0x83,0x7C,0x24,0x14,0x02)       # flag==2 ?
    a.jcc32(0x85,'ppath')
    # ---- safe attack: val += min(eff*BOOST_PCT/100, BOOST_CAP) ----
    a.db(0xB9); a.dd(BOOST_PCT)
    a.db(0xF7,0xE9)                      # widening
    a.db(0xB9,0x64,0x00,0x00,0x00)
    a.db(0xF7,0xF9)
    a.db(0x3D); a.dd(BOOST_CAP)
    a.j8(0x7E,'q2')
    a.db(0xB8); a.dd(BOOST_CAP)
    a.label('q2')
    a.db(0x8B,0x4F,0x0C)
    if RECORD: a.db(0x89,0x4C,0x24,0x24) # before
    a.db(0x01,0x47,0x0C)                 # [move+0xC] += boost
    if RECORD:
        a.db(0x8B,0x44,0x24,0x20); a.db(0x8B,0xD0)   # (fill fields below)
        a.db(0x8B,0x47,0x0C); a.db(0x89,0x44,0x24,0x2C)  # after
        a.db(0x8B,0x82); a.dd(REC)
        a.db(0xFF,0x82); a.dd(REC)
        a.db(0xB9); a.dd(REC_N)
        a.db(0x33,0xD2); a.db(0xF7,0xF1)
        a.db(0xC1,0xE2,0x05)
        a.db(0x03,0x54,0x24,0x20)
        a.db(0x8B,0x47,0x14); a.db(0x89,0x82); a.dd(REC+0x10)
        a.db(0xC7,0x82); a.dd(REC+0x14); a.dd(0xFFFFFFFF)
        a.db(0x8B,0x44,0x24,0x24); a.db(0x89,0x82); a.dd(REC+0x18)  # before
        a.db(0x8B,0x44,0x24,0x2C); a.db(0x89,0x82); a.dd(REC+0x1C)  # after
        a.db(0x8B,0x44,0x24,0x1C); a.db(0x89,0x82); a.dd(REC+0x20)  # f100
        a.db(0x8B,0x44,0x24,0x28); a.db(0x89,0x82); a.dd(REC+0x24)  # eff
        a.db(0xC7,0x82); a.dd(REC+0x28); a.dd(2)                     # flag
        a.db(0x8B,0x04,0x24); a.db(0xC1,0xE0,0x08)
        a.db(0x0F,0xB6,0x4F,0x04); a.db(0x0B,0xC1)
        a.db(0x89,0x82); a.dd(REC+0x2C)
    a.jmp32('next')
    # ---- provoked: val = max(val - eff*PEN_PCT/100, val*MIN_KEEP/100) ----
    a.label('ppath')
    a.db(0x8B,0x47,0x0C)
    if RECORD: a.db(0x89,0x44,0x24,0x24)  # before
    a.db(0x85,0xC0); a.j8(0x7E,'nf')     # non-positive: no floor (sink it)
    a.db(0xB9); a.dd(MIN_KEEP)
    a.db(0xF7,0xE9)
    a.db(0xB9,0x64,0x00,0x00,0x00)
    a.db(0xF7,0xF9)
    a.db(0x89,0x44,0x24,0x18)            # floor
    a.j8(0xEB,'ff')
    a.label('nf')
    a.db(0xC7,0x44,0x24,0x18); a.dd(0x80000000)
    a.label('ff')
    a.db(0x8B,0x44,0x24,0x28)            # eff
    a.db(0xB9); a.dd(PEN_PCT)
    a.db(0xF7,0xE9)
    a.db(0xB9,0x64,0x00,0x00,0x00)
    a.db(0xF7,0xF9)                      # pen
    a.db(0x8B,0x4F,0x0C)
    a.db(0x2B,0xC8)                      # v = val - pen
    a.db(0x3B,0x4C,0x24,0x18)
    a.j8(0x7D,'q3')
    a.db(0x8B,0x4C,0x24,0x18)
    a.label('q3')
    a.db(0x89,0x4F,0x0C)
    if RECORD:
        a.db(0x89,0x4C,0x24,0x2C)        # after
        a.db(0x8B,0x54,0x24,0x20)
        a.db(0x8B,0x82); a.dd(REC)
        a.db(0xFF,0x82); a.dd(REC)
        a.db(0xB9); a.dd(REC_N)
        a.db(0x33,0xD2); a.db(0xF7,0xF1)
        a.db(0xC1,0xE2,0x05)
        a.db(0x03,0x54,0x24,0x20)
        a.db(0x8B,0x47,0x14); a.db(0x89,0x82); a.dd(REC+0x10)
        a.db(0xC7,0x82); a.dd(REC+0x14); a.dd(0xFFFFFFFF)
        a.db(0x8B,0x44,0x24,0x24); a.db(0x89,0x82); a.dd(REC+0x18)
        a.db(0x8B,0x44,0x24,0x2C); a.db(0x89,0x82); a.dd(REC+0x1C)
        a.db(0x8B,0x44,0x24,0x1C); a.db(0x89,0x82); a.dd(REC+0x20)
        a.db(0x8B,0x44,0x24,0x28); a.db(0x89,0x82); a.dd(REC+0x24)
        a.db(0xC7,0x82); a.dd(REC+0x28); a.dd(1)
        a.db(0x8B,0x04,0x24); a.db(0xC1,0xE0,0x08)
        a.db(0x0F,0xB6,0x4F,0x04); a.db(0x0B,0xC1)
        a.db(0x89,0x82); a.dd(REC+0x2C)
    a.label('next')
    a.db(0xFF,0x04,0x24)
    a.jmp32('L')
    a.label('done')
    a.db(0x83,0xC4,0x30)
    a.db(0x5F,0x5E,0x5B)
    a.raw(SITE_ORIG)
    a.db(0xE9); a.dd((SITE+len(SITE_ORIG))-(a.here()+4))
    return a.done()

def build_cave2(cave2):
    # ACTIVE: adjusts the melee eval score (eax) at SITE2 before the
    # original store; also emits a CHK record when RECORD.
    a=Asm(cave2)
    a.db(0x60)                           # pushad (saved eax @ +0x1C from its esp)
    a.call(a.here()+5)
    a.label('pic2')
    a.db(0x5B)                           # pop ebx
    a.db(0x81,0xEB); a.dd(a.lab['pic2']) # ebx = module delta
    a.db(0x83,0xEC,0x14)                 # frame: [esp]=penSum +4=idx +8=targetAdj
    #        +0xC=enemyObj +0x10=ex ; pushad-saved eax @ [esp+0x30]
    a.db(0x33,0xC0)
    a.db(0x89,0x04,0x24)
    a.db(0x89,0x44,0x24,0x04)
    a.db(0x89,0x44,0x24,0x08)
    a.db(0x8B,0x45,0x14)                 # self obj
    a.db(0x8B,0x40,0x60)                 # self HS
    a.db(0x85,0xC0); a.jcc32(0x84,'Edone')
    a.db(0x8B,0xF0)                      # esi=HS
    a.db(0x8B,0x10); a.db(0xFF,0x52,0x74)
    a.db(0x0F,0xBE,0xF8)                 # edi=self x
    a.db(0x8B,0xC6); a.db(0x8B,0x10); a.db(0xFF,0x52,0x78)
    a.db(0x0F,0xBE,0xF0)                 # esi=self y
    a.label('Eloop')
    a.db(0x8B,0x45,0xFC)                 # cai
    a.db(0x8B,0x40,0x10)                 # enemy list
    a.db(0x8B,0x48,0x08)
    a.db(0x39,0x4C,0x24,0x04)
    a.jcc32(0x8D,'Edone')
    a.db(0x8B,0x4C,0x24,0x04)
    a.db(0x8B,0x40,0x04)
    a.db(0x8B,0x04,0x88)                 # enemy obj
    a.db(0x85,0xC0); a.jcc32(0x84,'Enext')
    a.db(0x89,0x44,0x24,0x0C)
    a.db(0x8A,0x48,0x47)
    a.db(0x80,0xE1,0x09)
    a.jcc32(0x85,'Enext')                # dead|fled
    a.db(0x8B,0x40,0x60)                 # enemy HS
    a.db(0x85,0xC0); a.jcc32(0x84,'Enext')
    a.db(0x8B,0x10); a.db(0xFF,0x52,0x74)
    a.db(0x0F,0xBE,0xC0)
    a.db(0x89,0x44,0x24,0x10)            # ex
    a.db(0x8B,0x44,0x24,0x0C)
    a.db(0x8B,0x40,0x60)
    a.db(0x8B,0x10); a.db(0xFF,0x52,0x78)
    a.db(0x0F,0xBE,0xD0)                 # edx=ey
    a.db(0x8B,0x4C,0x24,0x10)            # ecx=ex
    a.db(0x52)                           # push ey
    a.db(0x8B,0xD6)                      # edx=self y
    a.db(0x8B,0xC7)                      # eax=self x
    a.call(DHX)
    a.db(0x83,0xF8,0x01)
    a.jcc32(0x8F,'Enext')                # not adjacent
    a.db(0x8B,0x44,0x24,0x0C)
    a.db(0x3B,0x45,0x10)                 # is it the evaluated target?
    a.j8(0x75,'nt')
    a.db(0xC7,0x44,0x24,0x08); a.dd(1)   # target itself is adjacent
    a.jmp32('Enext')
    a.label('nt')
    a.db(0x8B,0x10); a.db(0xFF,0x52,0x5C)     # raw value
    a.db(0x85,0xC0); a.jcc32(0x8E,'Enext')
    a.db(0x3D); a.dd(RAW_CAP)
    a.j8(0x7E,'k1')
    a.db(0xB8); a.dd(RAW_CAP)
    a.label('k1')
    a.db(0x01,0x04,0x24)                 # penSum += raw
    a.label('Enext')
    a.db(0xFF,0x44,0x24,0x04)
    a.jmp32('Eloop')
    a.label('Edone')
    a.db(0x33,0xFF)                      # edi = pen = 0
    a.db(0x83,0x7C,0x24,0x08,0x00)
    a.j8(0x75,'rec')                     # target adjacent -> no penalty
    a.db(0x8B,0x04,0x24)
    a.db(0x85,0xC0); a.j8(0x74,'rec')
    a.db(0xB9); a.dd(CHK_DIV)
    a.db(0x99); a.db(0xF7,0xF9)
    a.db(0x8B,0xF8)                      # edi = pen
    a.db(0x29,0x44,0x24,0x30)            # saved eax (score) -= pen
    a.label('rec')
    if RECORD:
        a.db(0x8B,0x8B); a.dd(REC)       # ecx=count (ebx=delta)
        a.db(0xFF,0x83); a.dd(REC)
        a.db(0x8B,0xC1)
        a.db(0xB9); a.dd(REC_N)
        a.db(0x33,0xD2); a.db(0xF7,0xF1)
        a.db(0xC1,0xE2,0x05)
        a.db(0x03,0xD3)                  # edx = delta + slot*32
        a.db(0x8B,0x45,0x14); a.db(0x89,0x82); a.dd(REC+0x10)
        a.db(0xC7,0x82); a.dd(REC+0x14); a.dd(0xEEEEEEEE)
        a.db(0x8B,0x45,0x10); a.db(0x89,0x82); a.dd(REC+0x18)
        a.db(0x8B,0x44,0x24,0x30); a.db(0x89,0x82); a.dd(REC+0x1C)   # adjusted score
        a.db(0x0F,0xB6,0x85); a.dd(0xFFFFFF77)
        a.db(0x89,0x82); a.dd(REC+0x20)
        a.db(0x8B,0x45,0x98); a.db(0x8B,0x40,0x08)
        a.db(0x89,0x82); a.dd(REC+0x24)
        a.db(0x89,0xBA); a.dd(REC+0x28)                               # pen
        a.db(0x8B,0x45,0xFC); a.db(0x8B,0x40,0x08); a.db(0x8B,0x40,0x08)
        a.db(0x89,0x82); a.dd(REC+0x2C)
    a.db(0x83,0xC4,0x14)
    a.db(0x61)                           # popad (eax = adjusted score)
    a.raw(SITE2_ORIG)
    a.db(0xE9); a.dd((SITE2+len(SITE2_ORIG))-(a.here()+4))
    return a.done()

def parse_relocs(d):
    pe=struct.unpack_from('<I',d,0x3C)[0]; opt=pe+0x18
    rrva,rsz=struct.unpack_from('<II',d,opt+0x88)
    nsec=struct.unpack_from('<H',d,pe+6)[0]
    so=pe+0x18+struct.unpack_from('<H',d,pe+0x14)[0]
    secs=[struct.unpack_from('<IIII',d,so+i*40+8) for i in range(nsec)]
    base=struct.unpack_from('<I',d,opt+0x1C)[0]
    def r2f(rva):
        for vsz,va,rs,ro in secs:
            if va<=rva<va+rs: return ro+rva-va
    out=[]; o=r2f(rrva); end=o+rsz
    while o and o<end:
        page,bsz=struct.unpack_from('<II',d,o)
        for i in range((bsz-8)//2):
            e=struct.unpack_from('<H',d,o+8+i*2)[0]
            if e>>12==3: out.append(base+page+(e&0xFFF))
        o+=bsz
    return out

def apply():
    d=rd()
    cur=bytes(d[SITE-TC_D:SITE-TC_D+len(SITE_ORIG)])
    if cur!=SITE_ORIG:
        if cur[0]==0xE9: print('already applied'); return
        raise SystemExit(f'ABORT: site bytes {cur.hex()} unexpected')
    cave=build_cave()
    CAVE2=(CAVE+len(cave)+15)&~15
    cave2=build_cave2(CAVE2)
    if any(d[CAVE-TC_D:CAVE-TC_D+len(cave)+len(cave2)+16]): raise SystemExit('ABORT: cave not zero')
    if bytes(d[SITE2-TC_D:SITE2-TC_D+len(SITE2_ORIG)])!=SITE2_ORIG:
        raise SystemExit('ABORT: SITE2 bytes unexpected')
    sites=[(SITE,len(SITE_ORIG)),(CAVE,len(cave)+len(cave2)+16),(SITE2,len(SITE2_ORIG))]
    for rv in parse_relocs(d):
        for s_,l in sites:
            if s_<=rv<s_+l: raise SystemExit(f'ABORT: reloc @{rv:#x} in range')
    hooked=[(SITE,len(SITE_ORIG)),(SITE2,len(SITE2_ORIG))]
    for off in range(len(d)-6):
        va=TC_D+off
        if any(s_<=va<s_+l for s_,l in hooked): continue
        b=d[off]; t=None
        if b in (0xE8,0xE9): t=va+5+struct.unpack_from('<i',d,off+1)[0]
        elif b==0x0F and 0x80<=d[off+1]<=0x8F: t=va+6+struct.unpack_from('<i',d,off+2)[0]
        elif b==0xEB or 0x70<=b<=0x7F: t=va+2+struct.unpack_from('<b',d,off+1)[0]
        if t is None: continue
        for s_,l in hooked:
            if s_<t<s_+l:
                raise SystemExit(f'ABORT: branch @{va:#x} targets displaced byte {t:#x}')
    if not os.path.exists(BAK):
        with open(BAK,'wb') as f: f.write(bytes(d))
    d[CAVE-TC_D:CAVE-TC_D+len(cave)]=cave
    hook=bytearray(b'\xE9'+struct.pack('<i',CAVE-(SITE+5)))+b'\x90'*(len(SITE_ORIG)-5)
    d[SITE-TC_D:SITE-TC_D+len(SITE_ORIG)]=hook
    d[CAVE2-TC_D:CAVE2-TC_D+len(cave2)]=cave2
    hook2=bytearray(b'\xE9'+struct.pack('<i',CAVE2-(SITE2+5)))+b'\x90'*(len(SITE2_ORIG)-5)
    d[SITE2-TC_D:SITE2-TC_D+len(SITE2_ORIG)]=hook2
    print(f'  selector-bias hook @{SITE2:#x} -> cave2 @{CAVE2:#x} ({len(cave2)} B), CHK_DIV={CHK_DIV}')
    wr(d)
    print(f'APPLIED v4: AoO pass @cave {CAVE:#x} ({len(cave)} B, next free {CAVE+len(cave):#x}), PEN_PCT={PEN_PCT} BOOST_PCT={BOOST_PCT} BOOST_CAP={BOOST_CAP} MIN_KEEP={MIN_KEEP} RAW_CAP={RAW_CAP}')
    if RECORD: print(f'  RECORDER ON @ {REC:#x} ({REC_N} slots) -- pull live with --read; rebuild with RECORD=False before release')

def revert():
    d=rd()
    if d[SITE-TC_D]==0xE9:
        d[SITE-TC_D:SITE-TC_D+len(SITE_ORIG)]=SITE_ORIG
        if d[SITE2-TC_D]==0xE9:
            d[SITE2-TC_D:SITE2-TC_D+len(SITE2_ORIG)]=SITE2_ORIG
        cave=build_cave()
        d[CAVE-TC_D:CAVE-TC_D+0x800]=b'\x00'*0x800
        wr(d); print('REVERTED')
    elif bytes(d[SITE-TC_D:SITE-TC_D+len(SITE_ORIG)])==SITE_ORIG:
        print('already stock')
    else:
        raise SystemExit('ABORT: unexpected site bytes')

def read_recorder():
    import ctypes
    from ctypes import wintypes
    k32=ctypes.windll.kernel32
    class ME32(ctypes.Structure):
        _fields_=[('dwSize',wintypes.DWORD),('th32ModuleID',wintypes.DWORD),
                  ('th32ProcessID',wintypes.DWORD),('GlblcntUsage',wintypes.DWORD),
                  ('ProccntUsage',wintypes.DWORD),('modBaseAddr',ctypes.c_void_p),
                  ('modBaseSize',wintypes.DWORD),('hModule',ctypes.c_void_p),
                  ('szModule',ctypes.c_char*256),('szExePath',ctypes.c_char*260)]
    class PE32(ctypes.Structure):
        _fields_=[('dwSize',wintypes.DWORD),('cntUsage',wintypes.DWORD),
                  ('th32ProcessID',wintypes.DWORD),('th32DefaultHeapID',ctypes.c_void_p),
                  ('th32ModuleID',wintypes.DWORD),('cntThreads',wintypes.DWORD),
                  ('th32ParentProcessID',wintypes.DWORD),('pcPriClassBase',wintypes.LONG),
                  ('dwFlags',wintypes.DWORD),('szExeFile',ctypes.c_char*260)]
    snap=k32.CreateToolhelp32Snapshot(2,0)
    pe=PE32(); pe.dwSize=ctypes.sizeof(PE32); pid=0
    if k32.Process32First(snap,ctypes.byref(pe)):
        while True:
            if pe.szExeFile.lower()==b'aowx.exe': pid=pe.th32ProcessID; break
            if not k32.Process32Next(snap,ctypes.byref(pe)): break
    k32.CloseHandle(snap)
    if not pid: print('AoWx.exe not running'); return
    snap=k32.CreateToolhelp32Snapshot(0x18,pid)
    me=ME32(); me.dwSize=ctypes.sizeof(ME32); base=None
    if k32.Module32First(snap,ctypes.byref(me)):
        while True:
            if me.szModule.lower()==b'aowtcpck.dll': base=me.modBaseAddr; break
            if not k32.Module32Next(snap,ctypes.byref(me)): break
    k32.CloseHandle(snap)
    if base is None: print('AoWTCPCK.dll not found in process'); return
    h=k32.OpenProcess(0x10,False,pid)
    sz=0x10+REC_N*32
    buf=(ctypes.c_byte*sz)(); got=ctypes.c_size_t()
    k32.ReadProcessMemory(h,ctypes.c_void_p(base+(REC-0x400000)),buf,sz,ctypes.byref(got))
    k32.CloseHandle(h)
    b=bytes(buf)
    count,passes=struct.unpack_from('<II',b,0)
    n=min(count,REC_N)
    print(f'TCPCK base {base:#x} (delta {base-0x400000:+#x}); passes={passes} records={count} (showing last {n})')
    for r in range(count-n,count):
        off=0x10+(r%REC_N)*32
        f=struct.unpack_from('<8i',b,off)
        i=(f[7]>>8)&0xFFFFFF; t=f[7]&0xFF
        if f[1]==-0x11111112:
            print(f'  [{r:3}] CHK   self {f[0]&0xFFFFFFFF:#010x} -> target {f[2]&0xFFFFFFFF:#010x}: score {f[3]}  canstrike {f[4]} pathcnt {f[5]} pen {f[6]} own {f[7]}')
        elif f[1]==-1:
            kind='PROV' if f[6]==1 else 'SAFE'
            print(f'  [{r:3}] {kind}  move#{i} type{t} unit {f[0]&0xFFFFFFFF:#010x}: value {f[2]} -> {f[3]}  eff {f[5]}  f100 {f[4]}')
        else:
            print(f'  [{r:3}] ENEMY move#{i} type{t} unit {f[0]&0xFFFFFFFF:#010x} vs {f[1]&0xFFFFFFFF:#010x}: raw {f[2]} sum->{f[3]} f100 {f[4]}  (mv {f[6]})')

def status():
    d=rd()
    cur=bytes(d[SITE-TC_D:SITE-TC_D+len(SITE_ORIG)])
    if cur==SITE_ORIG: print('NOT APPLIED')
    elif cur[0]==0xE9: print('APPLIED')
    else: print('UNKNOWN:',cur.hex()); sys.exit(2)

if __name__=='__main__':
    arg=sys.argv[1] if len(sys.argv)>1 else '--status'
    if arg=='--apply': apply()
    elif arg=='--revert': revert()
    elif arg=='--read': read_recorder()
    else: status()
