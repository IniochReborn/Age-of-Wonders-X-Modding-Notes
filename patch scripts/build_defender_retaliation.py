#!/usr/bin/env python3
r"""Defender retaliation v5: AI defenders chase THE ARMY THAT ATTACKED THEM,
only if it DAMAGED them, and return home otherwise/afterwards.

HISTORY: v1 crash (TE path list nil at flee) -> v2 stable but indiscriminate ->
v3.x marked-target filter failed + crashed -> v4 observer run delivered the
facts (recorder, 2026-08-14):
 - TGuardAreaAGC.TargetFoundEvent IS the chase-feeding path (53 calls during
   one chase) and position comparison works (53/53 mismatches detected);
 - the combat SIDE lists ([combat+0x1C]) are ALREADY TORN DOWN at flee-driven
   CombatExecuted => v3 never wrote a fresh mark;
 - **[guardAreaAG+0x54] is NOT free — vanilla data lives there** (nonzero in a
   save no mod code ever wrote) => v3 squatted a real field: bogus marks +
   likely the CTD (c3 zeroed it). NEVER store in AG fields.
 - GuardArea state 1: EMPTY target list => state 2 = walk home. So removing
   non-matching targets is exactly the vanilla-blessed way to get
   "can't reach attacker -> return home".

V5 DESIGN (no engine-object fields touched, no event interception):
 - MARK TABLE in own BSS @0x558FAFA0: 12 entries x {group id, unit token}
   (ends 0x558FB000 = BSS page end). Process-local (not in saves — a reload
   simply drops chase intent; acceptable). Wiped on TAoWHSMap.Create (new
   game AND in-game load) so stale ids can never mis-associate.
 - c1 (CombatExecuted exit @0x55749913): result 9 (attacker fled) +
   **damage gate [delta+0x558FAF24]!=0** (defender-side unit damage this
   combat, from build_defender_damage_response — REQUIRED DEPENDENCY) +
   AI-owned defender => promote to GuardArea; pick mark unit from the
   COMBAT DATA object list (TCombatData.GetCount 0x55728BEC / GetObjects
   0x55728BF8 — this list is alive at this point; the result-9 assigner
   itself walks it): objects with ([+0x47]&9)==8 (FLED, not dead), TUnit via
   helper 0x55810F00, THero preferred; token=[unit+0x18]; group id =
   [TArmy.GetGroup(army,0xFF)+0x24]; upsert into table.
 - c2 (TGuardAreaAGC.ProcessStates state-1, hook @0x557D8E06 right after
   TargetList.Validate): if this group's id is marked: resolve token
   (0x5577E948 via [M+0xFC]) -> unit pos (GetLocation 0x5577ED94; unplaced
   yields 0xFFFFFF = matches nothing); sweep the target list TOP-DOWN and
   **Delete (engine API 0x557381EC, proper refcounting) every entry whose
   [t+0x30..32] != unit pos**. All deleted => vanilla walks the guard home.
   Token unresolvable => clear table entry (vanilla behavior resumes).
 - c3 (MoveExecuterDone home-arrival @0x557D8D5E): clear this group's table
   entry (NO writes to AG fields, unlike v3!).
 - c4 (TAoWHSMap.Create entry @0x557748A4): wipe the table.
 - Recorder @0x558FAF60 kept (`--read` live): +0 c1 triggers, +4 army,
   +8 group, +C group id, +0x10 token, +0x14 unused, +0x18 sweeps,
   +0x1C marked sweeps, +0x20 kept, +0x24 deleted, +0x28 resolved unit,
   +0x2C unit pos, +0x30 last target pos.

All PIC (AoWEPACK always rebases). c1/c3/c4 run in lockstep contexts; c2 runs
only on the AI-owner machine but reads lockstep-identical table state.
Usage: --apply | --revert | --status | --read.
Backup AoWEPACK.dll.bak_retaliate (full file, first apply).
"""
import os, struct, sys

GAME = os.environ.get('AOW_GAME_DIR') or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EP  = os.path.join(GAME, 'AoWEPACK.dll')
BAK = EP + '.bak_retaliate'
EP_D = 0x55700C00

SITE1      = 0x55749913
SITE1_ORIG = bytes.fromhex('595a5d5f5e5bc7'.replace('c7','c3'))   # 6 pops + ret
SITE2      = 0x557d8e06                               # state-1: mov eax,[esi+0x24]; call Validate
SITE2_ORIG = bytes.fromhex('8b4624e8faf3f5ff')        # 8 B
SITE3      = 0x557d8d5e
SITE3_ORIG = bytes.fromhex('8b500cc74250ffffff00')    # mov edx,[eax+0xC]; mov [edx+0x50],0xFFFFFF
SITE4      = 0x557748a4                               # TAoWHSMap.Create entry
SITE4_ORIG = bytes.fromhex('558bec83c4c8')            # push ebp; mov ebp,esp; add esp,-0x38
SITE5      = 0x557d8cb8                               # TGuardAreaAGC.TargetFoundEvent entry
SITE5_ORIG = bytes.fromhex('558bec5356')              # push ebp;mov ebp,esp;push ebx;push esi
# SITE6 (state-1 attack-move dispatch @0x557d8f32) REMOVED per user 8/15:
#   assemble-before-strike (v6.2-6.4) felt janky (holds/stop-short caused
#   visible indecision); natural adjacency decides combat participation.
SITE6_UNUSED = 0x557d8f32
SITE6_ORIG_UNUSED = bytes.fromhex('33d28b4624e8f8f1f5ff8a40325033d28b4624e8eaf1f5ff8a40315033d28b4624e8dcf1f5ff8a50308bc6598b18ff537c')
CAVE       = 0x55811120

GETFIELDXYL = 0x557020fc
GETPLAYERS  = 0x557544d0
GETBEHAV    = 0x5578c578
SETBEHAV    = 0x5578c590
GETGROUP    = 0x5578c4a0
HELPER      = 0x55810f00
ISCLASS     = 0x557010c0
RESOLVE     = 0x5577e948
GETLOC      = 0x5577ed94
GETUNITS    = 0x5578309c    # TArmy.GetUnits(eax=army, edx=idx) -> TUnit
#   (unit count = vcall [army vmt+0x54], same as GetOldAIBehavior uses)
VALIDATE    = 0x55738208    # TAIGroupControlTargetList.Validate(eax=list)
GETTARGETS  = 0x55738134    # (eax=list, edx=idx) -> entry
TLADD       = 0x557381e4    # TAIGroupControlTargetList.Add(eax=list, edx=entry)
TLDELETE    = 0x557381ec    # (eax=list, edx=idx)
M_VAR       = 0x558fa040
THERO_VMT   = 0x55711fac
ARMY_CID    = 0x20217
GUARDAREA   = 3
DMG_FLAG1   = 0x558faf24    # defender-side damage flag (defresp patch)
REC         = 0x558faf60
TABLE       = 0x558fa800    # 32 x {id, marktoken, orig_behavior, ownunit_token}
TABLE_N     = 32            #  16 B entries: 0x558FA800-0x558FAA00 (BSS scratch)
TABLE_END   = 0x200         # byte size (32*16)
SCR         = 0x558faa00    # phase-2 scratch: +0 cx +4 cy +8 cl +0xC player
                            #  +0x10 dy +0x14 dx +0x18 joined +0x1C forceadds
                            #  +0x20 holds +0x28 my-army live pos (c6)
RADIUS      = 6             # multi-party join window: +-6 hexes, same level
DHX         = 0x5570266c    # thunk HSEngine.dHXtoRad(eax=x1,edx=y1,ecx=x2,
                            #  push y2) -> hex distance
CENTERHN    = 0x55702694    # thunk HSEngine.CenterHNtoHX(eax=x,edx=y,ecx=idx,
                            #  stack &outX,&outY; idx 0=center, 1..6=ring 1;
                            #  push shape: push esp; lea eax,[esp+8]; push eax)
COHORT_MAX  = 5             # wait for cohort members within this dist of tgt


def rd(p):
    with open(p,'rb') as f: return bytearray(f.read())
def wr(p,dat):
    with open(p,'wb') as f: f.write(bytes(dat))


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


def build_caves():
    a=Asm(CAVE)
    # ============== CAVE 1: combat-end (SITE1; ebx=combat) ==================
    # v6: promotes the victim army AND (for real AI players) every same-player
    # army within RADIUS hexes of the defended hex (same level, not standing
    # on a structure) — all with the same mark. sub_pm does promote+upsert.
    a.label('c1')
    a.db(0x80,0x7B,0x14,0x09)            # cmp byte [ebx+0x14],9
    a.jcc32(0x85,'c1_done')
    a.db(0x8B,0x73,0x0C)                 # esi=[combat+0xC] TCombatData
    a.db(0x85,0xF6); a.jcc32(0x84,'c1_done')
    a.call(a.here()+5)
    a.label('c1pic')
    a.db(0x5F)                           # edi = runtime(c1pic)
    a.db(0x81,0xEF); a.dd(a.lab['c1pic'])
    a.db(0xFF,0x87); a.dd(REC)           # inc c1 triggers
    a.db(0x80,0xBF); a.dd(DMG_FLAG1); a.db(0x00)  # DAMAGE GATE
    a.jcc32(0x84,'c1_done')
    # stash combat pos1 (defended hex) + reset joined count
    a.db(0x8B,0x46,0x08); a.db(0x89,0x87); a.dd(SCR)      # cx
    a.db(0x8B,0x46,0x0C); a.db(0x89,0x87); a.dd(SCR+4)    # cy
    a.db(0x8B,0x46,0x10); a.db(0x89,0x87); a.dd(SCR+8)    # cl
    a.db(0xC7,0x87); a.dd(SCR+0x18); a.dd(0)              # joined=0
    # victim field/army
    a.db(0xFF,0xB7); a.dd(SCR+8)         # push level
    a.db(0x8B,0x8F); a.dd(SCR+4)         # ecx=cy
    a.db(0x8B,0x97); a.dd(SCR)           # edx=cx
    a.db(0x8B,0x87); a.dd(M_VAR)
    a.db(0x8B,0x40,0x10)
    a.call(GETFIELDXYL)
    a.db(0x85,0xC0); a.jcc32(0x84,'c1_done')
    a.db(0xBA); a.dd(ARMY_CID)
    a.db(0x8B,0x08); a.db(0xFF,0x91,0x80,0x00,0x00,0x00)
    a.db(0x85,0xC0); a.jcc32(0x84,'c1_done')
    a.db(0x8B,0x40,0x1C)
    a.db(0x85,0xC0); a.jcc32(0x84,'c1_done')
    a.db(0x8B,0xE8)                      # ebp = victim army
    a.db(0x89,0x87); a.dd(REC+4)
    # player gate + record player id
    a.db(0x0F,0xB6,0x45,0x12)
    a.db(0x89,0x87); a.dd(SCR+0xC)
    a.db(0x85,0xC0); a.j8(0x74,'c1_ai')
    a.db(0x8B,0xD0)
    a.db(0x8B,0x87); a.dd(M_VAR)
    a.db(0x8B,0x80,0x40,0x01,0x00,0x00)
    a.call(GETPLAYERS)
    a.db(0x85,0xC0); a.jcc32(0x84,'c1_done')
    a.db(0x80,0xB8,0xA7,0x00,0x00,0x00,0x00)
    a.jcc32(0x84,'c1_done')              # human -> out
    a.label('c1_ai')
    # ---- TOKEN from the attacker army @ combat pos2 (hero preferred) ----
    a.db(0x8B,0x46,0x1C); a.db(0x50)     # push level2
    a.db(0x8B,0x4E,0x18)                 # ecx=y2
    a.db(0x8B,0x56,0x14)                 # edx=x2
    a.db(0x8B,0x87); a.dd(M_VAR)
    a.db(0x8B,0x40,0x10)
    a.call(GETFIELDXYL)
    a.db(0x85,0xC0); a.jcc32(0x84,'c1_done')
    a.db(0xBA); a.dd(ARMY_CID)
    a.db(0x8B,0x08); a.db(0xFF,0x91,0x80,0x00,0x00,0x00)
    a.db(0x85,0xC0); a.jcc32(0x84,'c1_done')
    a.db(0x8B,0x40,0x1C)
    a.db(0x85,0xC0); a.jcc32(0x84,'c1_done')
    a.db(0x8B,0xF0)                      # esi = attacker army
    a.db(0x33,0xDB)                      # ebx=0 candidate
    a.db(0x8B,0xC6)
    a.db(0x8B,0x10); a.db(0xFF,0x52,0x54)# unit count
    a.db(0x89,0x87); a.dd(REC+0x14)
    a.db(0x50)                           # push count
    a.db(0x33,0xC9)
    a.label('c1_L')
    a.db(0x3B,0x0C,0x24)
    a.jcc32(0x8D,'c1_Le')
    a.db(0x51)
    a.db(0x8B,0xD1)
    a.db(0x8B,0xC6)
    a.call(GETUNITS)
    a.db(0x59)
    a.db(0x85,0xC0); a.j8(0x74,'c1_Ln')
    a.db(0x85,0xDB); a.j8(0x75,'c1_h')
    a.db(0x8B,0xD8)
    a.label('c1_h')
    a.db(0x51)
    a.db(0x8B,0xC8)
    a.db(0x8D,0x97); a.dd(THERO_VMT)
    a.call(ISCLASS)
    a.db(0x84,0xC0)
    a.db(0x5A)
    a.j8(0x74,'c1_nh')
    a.db(0x8B,0xD9)
    a.j8(0xEB,'c1_Le')
    a.label('c1_nh')
    a.db(0x8B,0xCA)
    a.label('c1_Ln')
    a.db(0x41)
    a.j8(0xEB,'c1_L')
    a.label('c1_Le')
    a.db(0x58)                           # pop count
    a.db(0x85,0xDB); a.jcc32(0x84,'c1_done')
    a.db(0x8B,0x73,0x18)                 # esi = TOKEN
    a.db(0x89,0xB7); a.dd(REC+0x10)
    # ---- promote+mark the victim ----
    a.db(0x8B,0xC5)                      # eax=victim army
    a.db(0xE8); a.f32.append((len(a.b),'sub_pm')); a.dd(0)   # call sub_pm
    # ---- multi-party: real AI players only ----
    a.db(0x83,0xBF); a.dd(SCR+0xC); a.db(0x00)   # cmp dword [edi+SCR+0xC],0
    a.jcc32(0x84,'c1_done')                      # independents: victim only
    a.db(0xC7,0x87); a.dd(SCR+0x10); a.dd((-RADIUS)&0xFFFFFFFF)  # dy=-R
    a.label('c1_Y')
    a.db(0xC7,0x87); a.dd(SCR+0x14); a.dd((-RADIUS)&0xFFFFFFFF)  # dx=-R
    a.label('c1_X')
    a.db(0x8B,0x97); a.dd(SCR)           # edx=cx
    a.db(0x03,0x97); a.dd(SCR+0x14)      # +dx
    a.j8(0x78,'c1_nx')                   # js -> negative x
    a.db(0x8B,0x8F); a.dd(SCR+4)         # ecx=cy
    a.db(0x03,0x8F); a.dd(SCR+0x10)      # +dy
    a.j8(0x78,'c1_nx')
    a.db(0x8B,0x87); a.dd(M_VAR)
    a.db(0x8B,0x40,0x10)                 # container
    a.db(0x3B,0x50,0x0C)                 # cmp edx,[cont+0xC] (width)
    a.j8(0x7D,'c1_nx')
    a.db(0x3B,0x48,0x10)                 # cmp ecx,[cont+0x10] (height)
    a.j8(0x7D,'c1_nx')
    a.db(0xFF,0xB7); a.dd(SCR+8)         # push level
    a.call(GETFIELDXYL)                  # (eax=container already)
    a.db(0x85,0xC0); a.j8(0x74,'c1_nx')
    a.db(0xBA); a.dd(ARMY_CID)
    a.db(0x8B,0x08); a.db(0xFF,0x91,0x80,0x00,0x00,0x00)
    a.db(0x85,0xC0); a.j8(0x74,'c1_nx')
    a.db(0x8B,0x40,0x1C)                 # TArmy
    a.db(0x85,0xC0); a.j8(0x74,'c1_nx')
    a.db(0x0F,0xB6,0x50,0x12)            # movzx edx,[army+0x12]
    a.db(0x3B,0x97); a.dd(SCR+0xC)       # same player?
    a.j8(0x75,'c1_nx')
    # NOTE: garrisons/on-structure armies JOIN too (user decision 8/14:
    # multi-hex cities must retaliate with ALL stacks, not be split by bait;
    # chase-mark + return-home + demote bound the exposure)
    a.db(0xE8); a.f32.append((len(a.b),'sub_pm')); a.dd(0)   # call sub_pm
    a.db(0xFF,0x87); a.dd(SCR+0x18)      # joined++
    a.label('c1_nx')
    a.db(0xFF,0x87); a.dd(SCR+0x14)      # dx++
    a.db(0x83,0xBF); a.dd(SCR+0x14); a.db(RADIUS)  # cmp dx,R
    a.jcc32(0x8E,'c1_X')                 # jle
    a.db(0xFF,0x87); a.dd(SCR+0x10)      # dy++
    a.db(0x83,0xBF); a.dd(SCR+0x10); a.db(RADIUS)
    a.jcc32(0x8E,'c1_Y')
    a.jmp32('c1_done')
    # ---- sub_pm(eax=army): promote to GuardArea + upsert mark ----
    # uses edi=delta, esi=token (both preserved by engine calls)
    a.label('sub_pm')
    a.db(0x53)                           # push ebx
    a.db(0x8B,0xD8)                      # ebx=army
    a.db(0x8B,0xC3); a.db(0xB2,0xFF)
    a.call(GETBEHAV)                     # al=orig
    a.db(0x0F,0xB6,0xC8)
    a.db(0x51)                           # push orig
    a.db(0x3C,GUARDAREA); a.j8(0x74,'pm_g')
    a.db(0x8B,0xC3); a.db(0xB2,0xFF); a.db(0xB1,GUARDAREA)
    a.call(SETBEHAV)
    a.label('pm_g')
    a.db(0x8B,0xC3); a.db(0xB2,0xFF)
    a.call(GETGROUP)
    a.db(0x85,0xC0); a.j8(0x74,'pm_x')
    a.db(0x89,0x87); a.dd(REC+8)
    a.db(0x8B,0x50,0x24)                 # id
    a.db(0x89,0x97); a.dd(REC+0xC)
    a.db(0x85,0xD2); a.j8(0x74,'pm_x')
    a.db(0x33,0xC9)
    a.label('pm_U')
    a.db(0x81,0xF9); a.dd(TABLE_END); a.j8(0x7D,'pm_Uf')
    a.db(0x39,0x94,0x0F); a.dd(TABLE)
    a.j8(0x74,'pm_Uw')
    a.db(0x83,0xBC,0x0F); a.dd(TABLE); a.db(0x00)
    a.j8(0x74,'pm_Uw')
    a.db(0x83,0xC1,16); a.j8(0xEB,'pm_U')
    a.label('pm_Uf')
    a.db(0x33,0xC9)
    a.label('pm_Uw')
    a.db(0x89,0x94,0x0F); a.dd(TABLE)    # id
    a.db(0x89,0xB4,0x0F); a.dd(TABLE+4)  # mark token
    a.db(0x8B,0x04,0x24)                 # eax=orig (top of stack)
    a.db(0x89,0x84,0x0F); a.dd(TABLE+8)  # orig
    # own-unit token (for cohort tracking): unit0 of THIS army
    a.db(0x51)                           # push entry offset
    a.db(0x33,0xD2)                      # edx=0
    a.db(0x8B,0xC3)                      # eax=army
    a.call(GETUNITS)
    a.db(0x59)                           # pop entry offset
    a.db(0x85,0xC0); a.j8(0x74,'pm_nu')
    a.db(0x8B,0x40,0x18)                 # eax=[unit0+0x18] token
    a.label('pm_nu')
    a.db(0x89,0x84,0x0F); a.dd(TABLE+0xC)# ownunit token (0 if none)
    a.label('pm_x')
    a.db(0x59)                           # pop orig
    a.db(0x5B)                           # pop ebx
    a.db(0xC3)                           # ret
    a.label('c1_done')
    a.raw(SITE1_ORIG)
    # ============== CAVE 2: state-1 target sweep (SITE2; esi=AGC) ===========
    a.label('c2')
    a.raw(SITE2_ORIG[:3])                # mov eax,[esi+0x24] (displaced)
    a.call(VALIDATE)                     # displaced call, re-emitted rel32
    a.call(a.here()+5)
    a.label('c2pic')
    a.db(0x5B)                           # ebx=delta (fn's ebx is dead here)
    a.db(0x81,0xEB); a.dd(a.lab['c2pic'])
    a.db(0xFF,0x83); a.dd(REC+0x18)      # inc sweeps
    a.db(0x8B,0x46,0x0C)                 # eax=[agc+0xC] group (AG)
    a.db(0x85,0xC0); a.jcc32(0x84,'c2_out')
    a.db(0x8B,0x50,0x24)                 # edx=[group+0x24] id
    a.db(0x85,0xD2); a.jcc32(0x84,'c2_out')
    # lookup id (12-byte entries, ecx = byte offset)
    a.db(0x33,0xC9)
    a.label('c2_K')
    a.db(0x81,0xF9); a.dd(TABLE_END); a.jcc32(0x8D,'c2_out')
    a.db(0x39,0x94,0x0B); a.dd(TABLE)    # cmp [ebx+ecx+TABLE],edx
    a.j8(0x74,'c2_Kf')
    a.db(0x83,0xC1,16); a.j8(0xEB,'c2_K')
    a.label('c2_Kf')
    a.db(0xFF,0x83); a.dd(REC+0x1C)      # inc marked sweeps
    a.db(0x8B,0xBC,0x0B); a.dd(TABLE+4)  # edi=token
    a.db(0x85,0xFF); a.j8(0x74,'c2_hb')  # token 0 = homebound: delete all
    a.db(0x51)                           # push entry offset
    a.db(0x8B,0x83); a.dd(M_VAR)
    a.db(0x8B,0x80,0xFC,0x00,0x00,0x00)
    a.db(0x8B,0xD7)                      # edx=token
    a.call(RESOLVE)
    a.db(0x89,0x83); a.dd(REC+0x28)
    a.db(0x85,0xC0); a.j8(0x75,'c2_hv')
    a.db(0x59)                           # pop entry offset
    a.db(0xC7,0x84,0x0B); a.dd(TABLE+4); a.dd(0)   # token=0 (KEEP id+orig)
    a.label('c2_hb')
    a.db(0xBF); a.dd(0xFFFFFF)           # matchpos = impossible -> delete all
    a.j8(0xEB,'c2_sw')
    a.label('c2_hv')
    a.db(0x59)                           # pop entry offset (done with it)
    a.db(0x83,0xEC,0x04)                 # xyz buffer
    a.db(0x8D,0x54,0x24,0x02); a.db(0x52)
    a.db(0x8D,0x4C,0x24,0x05)
    a.db(0x8D,0x54,0x24,0x04)
    a.call(GETLOC)                       # unplaced -> FF FF FF matches nothing
    a.db(0x8B,0x04,0x24)
    a.db(0x83,0xC4,0x04)
    a.db(0x25); a.dd(0xFFFFFF)           # and eax,0xFFFFFF
    a.db(0x89,0x83); a.dd(REC+0x2C)
    a.db(0x8B,0xF8)                      # edi=match pos
    a.label('c2_sw')
    # sweep top-down
    a.db(0x8B,0x46,0x24)                 # eax=list
    a.db(0x8B,0x10); a.db(0xFF,0x52,0x54)# vcall count
    a.db(0x8B,0xC8)                      # ecx=count
    a.label('c2_S')
    a.db(0x49)                           # dec ecx
    a.jcc32(0x88,'c2_out')               # js out
    a.db(0x51)                           # push idx
    a.db(0x8B,0xD1)
    a.db(0x8B,0x46,0x24)
    a.call(GETTARGETS)
    a.db(0x8B,0x40,0x30)                 # [t+0x30] pos dword
    a.db(0x25); a.dd(0xFFFFFF)
    a.db(0x89,0x83); a.dd(REC+0x30)
    a.db(0x3B,0xC7)                      # cmp eax,edi
    a.db(0x59)                           # pop idx (flags kept)
    a.j8(0x74,'c2_keep')
    a.db(0x51)                           # push idx
    a.db(0x8B,0xD1)
    a.db(0x8B,0x46,0x24)
    a.call(TLDELETE)                     # engine delete (refcount-correct)
    a.db(0xFF,0x83); a.dd(REC+0x24)      # inc deleted
    a.db(0x59)                           # pop idx
    a.j8(0xEB,'c2_S')
    a.label('c2_keep')
    a.db(0xFF,0x83); a.dd(REC+0x20)      # inc kept
    a.j8(0xEB,'c2_S')
    a.label('c2_out')
    a.db(0xE9); a.dd((SITE2+len(SITE2_ORIG))-(a.here()+4))   # resume @0x557D8E0E
    # ============== CAVE 3: home-arrival clears mark (SITE3) ================
    a.label('c3')
    a.raw(SITE3_ORIG)                    # mov edx,[eax+0xC]; mov [edx+0x50],0xFFFFFF
    a.db(0x50)                           # push eax (AGC needed by resume call)
    a.call(a.here()+5)
    a.label('c3pic')
    a.db(0x59)                           # ecx = runtime(c3pic)
    a.db(0x81,0xE9); a.dd(a.lab['c3pic'])# ecx=delta
    a.db(0x8B,0x42,0x24)                 # eax=[group+0x24] id (edx=group)
    a.db(0x85,0xC0); a.j8(0x74,'c3_z')
    a.db(0x33,0xD2)                      # edx = entry byte offset
    a.label('c3_C')
    a.db(0x81,0xFA); a.dd(TABLE_END); a.j8(0x7D,'c3_z')
    a.db(0x39,0x84,0x11); a.dd(TABLE)    # cmp [ecx+edx+TABLE],eax
    a.j8(0x74,'c3_Cf')
    a.db(0x83,0xC2,16); a.j8(0xEB,'c3_C')
    a.label('c3_Cf')
    # demote if orig not in {0, GuardArea}
    a.db(0x8B,0x84,0x11); a.dd(TABLE+8)  # eax=orig
    a.db(0x85,0xC0); a.j8(0x74,'c3_cl')
    a.db(0x83,0xF8,GUARDAREA); a.j8(0x74,'c3_cl')
    a.db(0x51,0x52)                      # save delta, offset
    a.db(0x0F,0xB6,0xC8)                 # movzx ecx,al (behavior)
    a.db(0x8B,0x44,0x24,0x08)            # eax=[esp+8] = pushed AGC
    a.db(0x8B,0x40,0x18)                 # eax=[agc+0x18] = TArmy
    a.db(0x85,0xC0); a.j8(0x74,'c3_sd')
    a.db(0xB2,0xFF)                      # dl=0xFF
    a.call(SETBEHAV)                     # demote (preserves ebx/esi/edi)
    a.label('c3_sd')
    a.db(0x5A,0x59)                      # restore offset, delta
    a.label('c3_cl')
    a.db(0xC7,0x84,0x11); a.dd(TABLE); a.dd(0)
    a.db(0xC7,0x84,0x11); a.dd(TABLE+4); a.dd(0)
    a.db(0xC7,0x84,0x11); a.dd(TABLE+8); a.dd(0)
    a.db(0xC7,0x84,0x11); a.dd(TABLE+0xC); a.dd(0)
    a.label('c3_z')
    a.db(0x58)                           # pop eax
    a.db(0xE9); a.dd((SITE3+len(SITE3_ORIG))-(a.here()+4))
    # ============== CAVE 5: TargetFoundEvent force-add for MARKED target ====
    # Vanilla TGuardAreaAGC.TargetFoundEvent only adds a target if the combat
    # PREDICTOR approves (drops e.g. a lone enemy LEADER it predicts it cannot
    # beat). Retaliation must chase the marked attacker REGARDLESS: if this
    # candidate IS the marked target, add it via the engine list-Add (exactly
    # what the vanilla base handler does) and skip the gate. Else vanilla.
    a.label('c5')
    a.db(0x50,0x51,0x52,0x53,0x56,0x57)  # push eax,ecx,edx,ebx,esi,edi
    a.call(a.here()+5)
    a.label('c5pic')
    a.db(0x5B)
    a.db(0x81,0xEB); a.dd(a.lab['c5pic'])# ebx=delta
    a.db(0x8B,0xF1)                      # esi=target
    a.db(0x8B,0x78,0x0C)                 # edi=[agc+0xC] group
    a.db(0x85,0xFF); a.jcc32(0x84,'c5_v')
    a.db(0x8B,0x57,0x24)                 # edx=[group+0x24] id
    a.db(0x85,0xD2); a.jcc32(0x84,'c5_v')
    a.db(0x33,0xC9)
    a.label('c5_K')
    a.db(0x81,0xF9); a.dd(TABLE_END); a.jcc32(0x8D,'c5_v')
    a.db(0x39,0x94,0x0B); a.dd(TABLE)    # cmp [ebx+ecx+TABLE],edx
    a.j8(0x74,'c5_Kf')
    a.db(0x83,0xC1,16); a.j8(0xEB,'c5_K')
    a.label('c5_Kf')
    a.db(0x8B,0xBC,0x0B); a.dd(TABLE+4)  # edi=token
    a.db(0x85,0xFF); a.jcc32(0x84,'c5_v')
    a.db(0x8B,0x83); a.dd(M_VAR)
    a.db(0x8B,0x80,0xFC,0x00,0x00,0x00)
    a.db(0x8B,0xD7)                      # edx=token
    a.call(RESOLVE)
    a.db(0x85,0xC0); a.jcc32(0x84,'c5_v')# unresolved -> vanilla (c2 clears)
    a.db(0x83,0xEC,0x04)                 # xyz buffer
    a.db(0x8D,0x54,0x24,0x02); a.db(0x52)
    a.db(0x8D,0x4C,0x24,0x05)
    a.db(0x8D,0x54,0x24,0x04)
    a.call(GETLOC)
    a.db(0x8B,0x04,0x24)
    a.db(0x83,0xC4,0x04)
    a.db(0x25); a.dd(0xFFFFFF)           # unit pos (unplaced=0xFFFFFF)
    a.db(0x8B,0x56,0x30)                 # edx=[target+0x30]
    a.db(0x81,0xE2); a.dd(0xFFFFFF)
    a.db(0x3B,0xC2)                      # match?
    a.jcc32(0x85,'c5_v')
    # MATCH: restore regs, then Add(list, target) + ret 4 (skip predictor gate)
    a.db(0xFF,0x83); a.dd(SCR+0x1C)      # inc force-add counter
    a.db(0x5F,0x5E,0x5B,0x5A,0x59,0x58)  # pop edi,esi,ebx,edx,ecx,eax
    a.db(0x8B,0xD1)                      # edx=target (ecx)
    a.db(0x8B,0x40,0x24)                 # eax=[agc+0x24] list
    a.call(TLADD)                        # engine Add (same as base handler)
    a.db(0xC2,0x04,0x00)                 # ret 4
    a.label('c5_v')
    a.db(0x5F,0x5E,0x5B,0x5A,0x59,0x58)  # restore all
    a.raw(SITE5_ORIG)                    # replay prologue
    a.db(0xE9); a.dd((SITE5+len(SITE5_ORIG))-(a.here()+4))  # resume vanilla
    # ============== CAVE 4: table wipe on map create (SITE4) ================
    a.label('c4')
    a.db(0x50,0x51)                      # push eax, ecx
    a.call(a.here()+5)
    a.label('c4pic')
    a.db(0x58)                           # eax = runtime(c4pic)
    a.db(0x2D); a.dd(a.lab['c4pic'])     # sub eax,static -> delta
    a.db(0x33,0xC9)
    a.label('c4_W')
    a.db(0xC7,0x84,0x88); a.dd(TABLE); a.dd(0)   # mov dword [eax+ecx*4+TABLE],0
    a.db(0x41)
    a.db(0x81,0xF9); a.dd(TABLE_END//4); a.j8(0x7C,'c4_W') # 0x80 dwords
    a.db(0x59,0x58)                      # pop ecx, pop eax
    a.raw(SITE4_ORIG)                    # push ebp; mov ebp,esp; add esp,-0x38
    a.db(0xE9); a.dd((SITE4+len(SITE4_ORIG))-(a.here()+4))
    return a.done(), a.lab


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


SITES=[(SITE1,SITE1_ORIG),(SITE2,SITE2_ORIG),(SITE3,SITE3_ORIG),(SITE4,SITE4_ORIG),(SITE5,SITE5_ORIG)]

def hookbytes(site,orig,cave_lab):
    h=bytearray(b'\xE9'+struct.pack('<i',cave_lab-(site+5)))
    h+=b'\x90'*(len(orig)-5)
    return bytes(h)


def apply():
    d=rd(EP)
    # safety: the removed SITE6 (0x557D8F32) must be stock vanilla — a stale
    # hook there (left by a revert run after SITE6 was dropped from SITES,
    # which nearly shipped 8/15) would jump into whatever cave now occupies
    # its old target.
    if d[SITE6_UNUSED-EP_D]==0xE9:
        raise SystemExit('ABORT: stale SITE6 hook @0x557D8F32 — restore SITE6_ORIG_UNUSED bytes first')
    if bytes(d[0x5580dcf4-EP_D:0x5580dcf4-EP_D+6])!=bytes.fromhex('c78020af8f55'):
        raise SystemExit('ABORT: build_defender_damage_response not applied (damage flags missing)')
    for s_,o in SITES:
        cur=bytes(d[s_-EP_D:s_-EP_D+len(o)])
        if cur!=o: raise SystemExit(f'ABORT: site @{s_:#x} bytes {cur.hex()} unexpected (revert first?)')
    cave,lab=build_caves()
    if any(d[CAVE-EP_D:CAVE-EP_D+len(cave)]): raise SystemExit('ABORT: cave region not zero')
    ranges=[(s_,len(o)) for s_,o in SITES]+[(CAVE,len(cave))]
    for rv in parse_relocs(d):
        for s_,l in ranges:
            if s_<=rv<s_+l: raise SystemExit(f'ABORT: reloc @{rv:#x} in patch range')
    FALSE_POS={0x557d8c39,0x557d8c3a,0x557d8f69,0x557d8f6e}
    for off in range(len(d)-6):
        va=EP_D+off
        if va in FALSE_POS: continue
        if 0x557d8f63<=va<0x557d8ff0: continue   # verified by real disasm: only
        # operand bytes of Delete-call/jmp/state-2 code decode as fake jcc here
        if any(s_<=va<s_+len(o) for s_,o in SITES): continue
        b=d[off]; t=None
        if b in (0xE8,0xE9): t=va+5+struct.unpack_from('<i',d,off+1)[0]
        elif b==0x0F and 0x80<=d[off+1]<=0x8F: t=va+6+struct.unpack_from('<i',d,off+2)[0]
        elif b==0xEB or 0x70<=b<=0x7F: t=va+2+struct.unpack_from('<b',d,off+1)[0]
        if t is None: continue
        for s_,o in SITES:
            if s_<t<s_+len(o): raise SystemExit(f'ABORT: branch @{va:#x} targets displaced byte {t:#x}')
    if not os.path.exists(BAK): wr(BAK,d)
    d[CAVE-EP_D:CAVE-EP_D+len(cave)]=cave
    d[SITE1-EP_D:SITE1-EP_D+len(SITE1_ORIG)]=hookbytes(SITE1,SITE1_ORIG,lab['c1'])
    d[SITE2-EP_D:SITE2-EP_D+len(SITE2_ORIG)]=hookbytes(SITE2,SITE2_ORIG,lab['c2'])
    d[SITE3-EP_D:SITE3-EP_D+len(SITE3_ORIG)]=hookbytes(SITE3,SITE3_ORIG,lab['c3'])
    d[SITE4-EP_D:SITE4-EP_D+len(SITE4_ORIG)]=hookbytes(SITE4,SITE4_ORIG,lab['c4'])
    d[SITE5-EP_D:SITE5-EP_D+len(SITE5_ORIG)]=hookbytes(SITE5,SITE5_ORIG,lab['c5'])
    wr(EP,d)
    print(f"APPLIED v5: caves @{CAVE:#x} ({len(cave)} B, next free {CAVE+len(cave):#x}); "
          f"c1@{lab['c1']:#x} c2@{lab['c2']:#x} c3@{lab['c3']:#x} c4@{lab['c4']:#x} c5@{lab['c5']:#x}")


def revert():
    d=rd(EP)
    for s_,o in SITES:
        if d[s_-EP_D]==0xE9: d[s_-EP_D:s_-EP_D+len(o)]=o
        elif bytes(d[s_-EP_D:s_-EP_D+len(o)])!=o:
            raise SystemExit(f'ABORT: unexpected bytes @{s_:#x}; restore from {BAK}')
    d[CAVE-EP_D:CAVE-EP_D+0x800]=b'\x00'*0x800   # covers all cave versions
    wr(EP,d); print('REVERTED')


def status():
    d=rd(EP)
    hooks=[d[s_-EP_D]==0xE9 for s_,o in SITES]
    stock=[bytes(d[s_-EP_D:s_-EP_D+len(o)])==o for s_,o in SITES]
    if all(stock): print('NOT APPLIED')
    elif all(hooks): print('APPLIED (v5, 4 hooks)')
    else: print('MIXED:',hooks,stock); sys.exit(2)


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
            if me.szModule.lower()==b'aowepack.dll': base=me.modBaseAddr; break
            if not k32.Module32Next(snap,ctypes.byref(me)): break
    k32.CloseHandle(snap)
    if base is None: print('AoWEPACK.dll not found'); return
    h=k32.OpenProcess(0x10,False,pid)
    buf=(ctypes.c_byte*0x38)(); got=ctypes.c_size_t()
    k32.ReadProcessMemory(h,ctypes.c_void_p(base+(REC-0x55700000)),buf,0x38,ctypes.byref(got))
    v=struct.unpack_from('<14I',bytes(buf))
    tb=(ctypes.c_byte*(TABLE_N*16))()
    k32.ReadProcessMemory(h,ctypes.c_void_p(base+(TABLE-0x55700000)),tb,TABLE_N*16,ctypes.byref(got))
    sc=(ctypes.c_byte*0x24)()
    k32.ReadProcessMemory(h,ctypes.c_void_p(base+(SCR-0x55700000)),sc,0x24,ctypes.byref(got))
    scv=struct.unpack_from('<9I',bytes(sc))
    k32.CloseHandle(h)
    names=['c1_triggers','army','group','group_id','mark_token','unused',
           'c2_sweeps','c2_marked','kept','deleted','resolved_unit',
           'unit_pos','last_target_pos','pad']
    print(f'AoWEPACK base {base:#x} (delta {base-0x55700000:+#x})')
    print(f'  last combat hex ({scv[0]},{scv[1]},{scv[2]}) player {scv[3]} joined {scv[6]} forceadds {scv[7]} holds {scv[8]}')
    for n,val in zip(names,v):
        print(f'  {n:16} {val:#010x}')
    print('  mark table:')
    any_=False
    for i in range(TABLE_N):
        gid,tok,orig,own=struct.unpack_from('<IIII',bytes(tb),i*16)
        if gid: print(f'    slot {i}: group id {gid:#x} -> token {tok:#x} (orig {orig}, ownunit {own:#x})'); any_=True
    if not any_: print('    (empty)')


if __name__=='__main__':
    arg=sys.argv[1] if len(sys.argv)>1 else '--status'
    if arg=='--apply': apply()
    elif arg=='--revert': revert()
    elif arg=='--read': read_recorder()
    else: status()
