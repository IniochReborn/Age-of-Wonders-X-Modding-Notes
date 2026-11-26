#!/usr/bin/env python3
r"""AI hero/leader melee courage in TACTICAL combat (AoWTCPCK.dll).

PROBLEM (user 2026-08-15): AI heroes/leaders are uselessly passive in
tactical combat when they have no mana/casting left — with an enemy standing
NEXT TO THEM they choose to move (eating the opportunity attack, which the AI
does not model at all) and end the turn having done nothing.

ROOT CAUSE (RE): every attack is scored by TCAI.tcDVtoDEV @0x413664:
    DEV = (targetValue2 * damageDV - selfValue2 * retaliationDV) / 100
where a unit's value is multiplied x2 if it is a THero and x2 AGAIN if a
TLeader — applied to BOTH the target (good: killing enemy heroes pays) and
THE SELF (bad: the AI's own hero fears retaliation x2, its leader x4, on top
of the already-high base unit value). Additionally CheckUnit's Melee Check
halves hero melee move values outright (50%; the only such penalty — spell/
touch/ranged have none). Net effect: hero melee never scores positive vs
anything that retaliates, while moving away is costed as free.

PATCH (3 immediate bytes, all tunable below; TACTICAL-ONLY by construction —
tcDVtoDEV/CheckUnit live inside TCAI which fast/auto combat never uses):
 1. @0x41371B  hero SELF-value multiplier   2 -> HERO_SELF_AMP   (default 1)
 2. @0x41373E  leader extra SELF multiplier 2 -> LEADER_SELF_AMP (default 2,
               i.e. leaders keep x2 net self-caution instead of vanilla x4 —
               their death loses the game, some cowardice is correct)
 3. @0x41572C  hero melee move percent   0x32 -> HERO_MELEE_PCT (default 0x50
               = 80%, vanilla 50%)
The TARGET-side amps @0x4136A8/0x4136CB are deliberately untouched.

Usage: --apply | --revert | --status.
Backup AoWTCPCK.dll.bak_herocourage (full file, first apply).
"""
import os, struct, sys

GAME = os.environ.get('AOW_GAME_DIR') or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TC  = os.path.join(GAME, 'AoWTCPCK.dll')
BAK = TC + '.bak_herocourage'
TC_D = 0x400C00

HERO_SELF_AMP   = 1     # vanilla 2   (imul factor; 1 = no extra fear)
LEADER_SELF_AMP = 2     # vanilla 2   (stacks with hero amp: net = product)
HERO_MELEE_PCT  = 0x50  # vanilla 0x32 (50%); 0x50=80%, 0x64=100%

# (site VA, imm offset within instr, vanilla imm, patched imm, context bytes)
SITES = [
    (0x413718, 3, 2,    HERO_SELF_AMP,   bytes.fromhex('6b45ec')),  # imul eax,[ebp-0x14],imm8
    (0x41373b, 3, 2,    LEADER_SELF_AMP, bytes.fromhex('6b45ec')),
    (0x415729, 3, 0x32, HERO_MELEE_PCT,  bytes.fromhex('c745ec')),  # mov dword [ebp-0x14],imm32(lo byte)
]

def rd():
    with open(TC,'rb') as f: return bytearray(f.read())
def wr(d):
    with open(TC,'wb') as f: f.write(bytes(d))

def check(d, patched):
    state=[]
    for va,off,van,new,ctx in SITES:
        o=va-TC_D
        if bytes(d[o:o+3])!=ctx:
            raise SystemExit(f'ABORT: context mismatch @{va:#x}: {bytes(d[o:o+3]).hex()}')
        cur=d[o+off]
        state.append(cur)
    return state

def apply():
    d=rd()
    st=check(d,None)
    if all(cur==new for cur,(va,off,van,new,ctx) in zip(st,SITES)):
        print('already applied'); return
    for cur,(va,off,van,new,ctx) in zip(st,SITES):
        if cur not in (van,new):
            raise SystemExit(f'ABORT: unexpected imm {cur:#x} @{va:#x}')
    if not os.path.exists(BAK):
        with open(BAK,'wb') as f: f.write(bytes(d))
    for va,off,van,new,ctx in SITES:
        d[va-TC_D+off]=new
    wr(d)
    print(f'APPLIED: hero self-amp {SITES[0][2]}->{HERO_SELF_AMP}, '
          f'leader extra {SITES[1][2]}->{LEADER_SELF_AMP}, '
          f'hero melee pct {SITES[2][2]:#x}->{HERO_MELEE_PCT:#x}')

def revert():
    d=rd()
    for va,off,van,new,ctx in SITES:
        d[va-TC_D+off]=van
    wr(d)
    print('REVERTED to vanilla (2 / 2 / 0x32)')

def status():
    d=rd()
    st=check(d,None)
    for cur,(va,off,van,new,ctx) in zip(st,SITES):
        tag='vanilla' if cur==van else ('patched' if cur==new else 'OTHER')
        print(f'  @{va:#x}: imm={cur:#x} ({tag})')

if __name__=='__main__':
    arg=sys.argv[1] if len(sys.argv)>1 else '--status'
    if arg=='--apply': apply()
    elif arg=='--revert': revert()
    else: status()
