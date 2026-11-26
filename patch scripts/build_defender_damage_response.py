#!/usr/bin/env python3
r"""Defender AI responds to taking damage (open field AND siege).

PROBLEM: the tactical-combat defending AI only engages when TCAI's phase-0
threat scan sets [cai+0x34] ("battle joined"). The scan's enemy-spell branch
is supposed to handle even infinite-range (0xFF) spells but fails in practice,
so an attacker bombarding from out of reach is never answered: defenders stand
still and die (user-confirmed on 1.37.404, open field and siege alike).

FIX (three coordinated patches, two binaries):

AoWEPACK.dll (VA = file + 0x55700C00; ALWAYS REBASES -> PIC caves):
 1. Two per-side "this side took unit damage" BSS flags:
       0x558FAF23 = side 0 (attacker)   0x558FAF24 = side 1 (defender)
    right after the per-combat AI-spell flags 0x558FAF20-22.
    Set by a new cave @0x558110C0 hooked into BOTH universal damage sinks:
      A) 0x55726C58  vmt+0x124 common impl (melee/combat damage, all classes)
         entry '53 56 57 55 8b da' (6 B displaced)
      B) 0x55724C1C  TCombatUnit vmt+0x128 impl (spell/CA damage -> TUnit)
         entry '53 56 51 66 89 14 24' (7 B displaced)
    Cave: damage>0, victim IsClass TCombatUnit (reuses wall-fix helper
    0x55810F00 -> walls do NOT trigger), GetSide (0x55726660) in {0,1}
    -> set flag[side]=1 (PIC delta write).
 2. TCombat.Create cave @0x5580DCE8 (ai-combat-spell-once-per-combat)
    clear block @0x5580DCF4 rewritten in place (21 B): three byte-clears
    0x558FAF20/21/22 -> dword-clear 0x558FAF20-23 + byte-clear 0x558FAF24
    + 4 NOPs, so the new flags reset at every tactical combat start.

AoWTCPCK.dll (VA = file + 0x400C00; ALWAYS REBASES -> PIC cave):
 3. TCAI.EvalBattle phase-0 init '[cai+0x34] = (side==0)' @0x4185A1
    (13 B: 8b45fc 80780400 0f94c0 8b55fc 884234) -> jmp cave @0x438620:
       side 0 -> 1 (vanilla: attacker always engaged)
       side 1 -> flag[1]  (defender engaged iff its side took damage)
       side >1 -> 0 (vanilla result for impossible values)
    Cross-module flag read WITHOUT hardcoding AoWEPACK's rebased base:
    IAT slot [0x46E8D4] = &AoWE.AoWHSMap variable (static 0x558FA040);
    flags = that address + 0xEE3/0xEE4 (same image => same rebase delta).

MP-safe: damage runs lockstep on all machines; EvalBattle only runs on the
machine owning the AI player and its choices replicate as tokens.

Usage: --apply | --revert | --status
Backups (full-file, first apply only): AoWEPACK.dll.bak_defresp,
AoWTCPCK.dll.bak_defresp. --revert restores the patched byte ranges only.
"""
import os, struct, sys

GAME = os.environ.get('AOW_GAME_DIR') or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EP  = os.path.join(GAME, 'AoWEPACK.dll')
TC  = os.path.join(GAME, 'AoWTCPCK.dll')
EP_BAK = EP + '.bak_defresp'
TC_BAK = TC + '.bak_defresp'

EP_D = 0x55700C00           # AoWEPACK: VA = file + EP_D
TC_D = 0x400C00             # AoWTCPCK: VA = file + TC_D

# ---- AoWEPACK sites -------------------------------------------------------
SINK_A   = 0x55726C58       # common vmt+0x124 damage impl (eax=victim, edx=dmg)
SINK_A_ORIG = bytes.fromhex('535657558bda')          # 6 B
SINK_B   = 0x55724C1C       # unit vmt+0x128 impl (eax=victim, dx=dmg)
SINK_B_ORIG = bytes.fromhex('53565166891424')        # 7 B
CAVE_EP  = 0x558110C0       # verified zeros (3904 B free run)
HELPER   = 0x55810F00       # wall-fix helper: eax=obj -> eax=TUnit|nil (ZF), edx kept
GETSIDE  = 0x55726660       # AoWE.TCombatObject.GetSide: eax=obj -> al (2=detached)
FLAG0    = 0x558FAF23       # side-0 damage flag (FLAG0+1 = side 1)
CLEARS   = 0x5580DCF4       # inside TCombat.Create cave (eax = PIC delta there)
CLEARS_ORIG = bytes.fromhex('c68020af8f5500' 'c68021af8f5500' 'c68022af8f5500')
CLEARS_NEW  = (bytes.fromhex('c78020af8f55') + b'\x00\x00\x00\x00' +   # dword clear 20-23
               bytes.fromhex('c68024af8f5500') +                        # byte clear 24
               b'\x90'*4)
assert len(CLEARS_NEW) == len(CLEARS_ORIG) == 21

# ---- AoWTCPCK sites -------------------------------------------------------
TC_SITE  = 0x4185A1         # [cai+0x34] init in EvalBattle phase 0
TC_ORIG  = bytes.fromhex('8b45fc' '80780400' '0f94c0' '8b55fc' '884234')  # 16 B
TC_RESUME= TC_SITE + len(TC_ORIG)                    # 0x4185B1
CAVE_TC  = 0x438620         # verified zeros
IAT_MAPVAR = 0x46E8D4       # [slot] = &AoWE.AoWHSMap (static 0x558FA040)
MAPVAR_STATIC = 0x558FA040
FLAG_OFF = FLAG0 - MAPVAR_STATIC                     # 0xEE3


def rd(p):
    with open(p, 'rb') as f: return bytearray(f.read())

def wr(p, d):
    with open(p, 'wb') as f: f.write(bytes(d))


class Asm:
    """tiny fixup assembler emitting at a fixed VA"""
    def __init__(self, base):
        self.base = base; self.b = bytearray(); self.lab = {}; self.fix = []
    def here(self): return self.base + len(self.b)
    def db(self, *x): self.b += bytes(x)
    def raw(self, x): self.b += x
    def dd(self, v): self.b += struct.pack('<I', v & 0xFFFFFFFF)
    def label(self, n): self.lab[n] = self.here()
    def j8(self, op, n):          # short jcc/jmp to label
        self.db(op); self.fix.append(('rel8', len(self.b), n)); self.db(0)
    def call(self, tgt):          # E8 rel32 to absolute VA (same module)
        self.db(0xE8); self.dd(tgt - (self.here() + 4))
    def jmp(self, tgt):
        self.db(0xE9); self.dd(tgt - (self.here() + 4))
    def call_lab(self, n):
        self.db(0xE8); self.fix.append(('rel32', len(self.b), n)); self.dd(0)
    def done(self):
        for kind, pos, n in self.fix:
            tgt = self.lab[n]
            if kind == 'rel8':
                rel = tgt - (self.base + pos + 1)
                assert -128 <= rel <= 127, (n, rel)
                self.b[pos] = rel & 0xFF
            else:
                rel = tgt - (self.base + pos + 4)
                self.b[pos:pos+4] = struct.pack('<i', rel)
        return bytes(self.b)


def build_ep_cave():
    a = Asm(CAVE_EP)
    # ---- stub1: from SINK_A. eax=victim, edx=damage(int32)
    a.label('stub1')
    a.db(0x50, 0x51, 0x52)                    # push eax/ecx/edx
    a.db(0x85, 0xD2)                          # test edx,edx
    a.j8(0x7E, 's1skip')                      # jle
    a.call_lab('setflag')
    a.label('s1skip')
    a.db(0x5A, 0x59, 0x58)                    # pop edx/ecx/eax
    a.raw(SINK_A_ORIG)                        # replay displaced
    a.jmp(SINK_A + len(SINK_A_ORIG))
    # ---- stub2: from SINK_B. eax=victim(unit), dx=damage(word)
    a.label('stub2')
    a.db(0x50, 0x51, 0x52)
    a.db(0x66, 0x85, 0xD2)                    # test dx,dx
    a.j8(0x7E, 's2skip')
    a.call_lab('setflag')
    a.label('s2skip')
    a.db(0x5A, 0x59, 0x58)
    a.raw(SINK_B_ORIG)
    a.jmp(SINK_B + len(SINK_B_ORIG))
    # ---- setflag: eax=victim combat object (caller saved eax/ecx/edx)
    a.label('setflag')
    a.db(0x50)                                # push eax (victim; helper clobbers)
    a.call(HELPER)                            # TCombatUnit? eax=TUnit|nil
    a.db(0x85, 0xC0)                          # test eax,eax
    a.db(0x58)                                # pop eax (victim; flags kept? pop
                                              #  doesn't touch flags)
    a.j8(0x74, 'done')                        # jz -> wall/other: no trigger
    a.call(GETSIDE)                           # al = side (2 = detached)
    a.db(0x3C, 0x01)                          # cmp al,1
    a.j8(0x77, 'done')                        # ja  -> not a battle side
    a.db(0x0F, 0xB6, 0xD0)                    # movzx edx,al
    a.call_lab('pic')                         # PIC delta
    a.label('pic')
    a.db(0x59)                                # pop ecx  (= runtime VA of 'pic')
    a.db(0x81, 0xC1); a.dd(FLAG0 - a.lab['pic'])   # add ecx, FLAG0-static(pic)
    a.db(0xC6, 0x04, 0x11, 0x01)              # mov byte [ecx+edx],1
    a.label('done')
    a.db(0xC3)                                # ret
    return a.done(), a.lab


def build_tc_cave():
    a = Asm(CAVE_TC)
    a.db(0x8B, 0x45, 0xFC)                    # mov eax,[ebp-4]      ; cai
    a.db(0x0F, 0xB6, 0x48, 0x04)              # movzx ecx,byte [eax+4] ; side
    a.db(0xB2, 0x01)                          # mov dl,1
    a.db(0x85, 0xC9)                          # test ecx,ecx
    a.j8(0x74, 'store')                       # side 0 -> engaged (vanilla)
    a.db(0x83, 0xF9, 0x01)                    # cmp ecx,1
    a.j8(0x75, 'zero')                        # side >1 -> 0 (vanilla result)
    # side 1 (defender): dl = damage flag[1]
    a.call_lab('pic')
    a.label('pic')
    a.db(0x59)                                # pop ecx (runtime VA of 'pic')
    a.db(0x81, 0xE9); a.dd(a.lab['pic'])      # sub ecx, static(pic) -> delta
    a.db(0x8B, 0x89); a.dd(IAT_MAPVAR)        # mov ecx,[ecx+IAT]  (PIC IAT read)
    a.db(0x8A, 0x91); a.dd(FLAG_OFF + 1)      # mov dl,[ecx+0xEE4] ; side-1 flag
    a.j8(0xEB, 'store')
    a.label('zero')
    a.db(0xB2, 0x00)                          # mov dl,0
    a.label('store')
    a.db(0x88, 0x50, 0x34)                    # mov [eax+0x34],dl
    a.jmp(TC_RESUME)
    return a.done(), a.lab


# ---------------------------------------------------------------- prechecks
def parse_relocs(d):
    pe = struct.unpack_from('<I', d, 0x3C)[0]; opt = pe + 0x18
    rrva, rsz = struct.unpack_from('<II', d, opt + 0x88)   # data dir #5 = basereloc
    nsec = struct.unpack_from('<H', d, pe + 6)[0]
    so = pe + 0x18 + struct.unpack_from('<H', d, pe + 0x14)[0]
    secs = [struct.unpack_from('<IIII', d, so + i*40 + 8) for i in range(nsec)]
    base = struct.unpack_from('<I', d, opt + 0x1C)[0]
    def r2f(rva):
        for vsz, va, rs, ro in secs:
            if va <= rva < va + rs: return ro + rva - va
    out = []
    o = r2f(rrva); end = o + rsz
    while o and o < end:
        page, bsz = struct.unpack_from('<II', d, o)
        for i in range((bsz - 8) // 2):
            e = struct.unpack_from('<H', d, o + 8 + i*2)[0]
            if e >> 12 == 3: out.append(base + page + (e & 0xFFF))
        o += bsz
    return out

def check_relocs(d, delta, ranges, name):
    base_va = [r for r in parse_relocs(d)]
    for va0, ln in ranges:
        rva0 = va0 - delta          # file offset
        # reloc VAs are imagebase-relative; convert file offset -> imagebase VA
        # our VA convention == imagebase VA for these modules (base+RVA)
        for rv in base_va:
            # rv is imagebase VA; site va0 is the same space
            if va0 <= rv < va0 + ln:
                raise SystemExit(f'ABORT: active reloc @{rv:#x} inside {name} range {va0:#x}+{ln}')

def check_branch_targets(d, va_delta, ranges, name):
    n = len(d)
    prot = [(s + 1, s + ln) for s, ln in ranges]      # interior only
    def hit(t):
        return any(lo <= t < hi for lo, hi in prot)
    def inside(src):                                   # branch FROM a replaced
        return any(s <= src < s + ln for s, ln in ranges)   # range: irrelevant
    for off in range(n - 6):
        if inside(va_delta + off): continue
        b = d[off]
        if b in (0xE8, 0xE9):
            t = va_delta + off + 5 + struct.unpack_from('<i', d, off + 1)[0]
            if hit(t): raise SystemExit(f'ABORT: rel32 {b:02x} @{va_delta+off:#x} targets inside {name}')
        elif b == 0x0F and 0x80 <= d[off+1] <= 0x8F:
            t = va_delta + off + 6 + struct.unpack_from('<i', d, off + 2)[0]
            if hit(t): raise SystemExit(f'ABORT: jcc rel32 @{va_delta+off:#x} targets inside {name}')
        elif b == 0xEB or 0x70 <= b <= 0x7F:
            t = va_delta + off + 2 + struct.unpack_from('<b', d, off + 1)[0]
            if hit(t): raise SystemExit(f'ABORT: rel8 @{va_delta+off:#x} targets inside {name}')


def hook5(dst_va, cave_va, orig_len):
    h = bytearray(b'\xE9' + struct.pack('<i', cave_va - (dst_va + 5)))
    h += b'\x90' * (orig_len - 5)
    return bytes(h)


def status():
    ep = rd(EP); tc = rd(TC)
    a = ep[SINK_A-EP_D:SINK_A-EP_D+6] == SINK_A_ORIG
    b = ep[SINK_B-EP_D:SINK_B-EP_D+7] == SINK_B_ORIG
    c = ep[CLEARS-EP_D:CLEARS-EP_D+21] == CLEARS_ORIG
    t = tc[TC_SITE-TC_D:TC_SITE-TC_D+len(TC_ORIG)] == TC_ORIG
    if a and b and c and t: print('NOT APPLIED (all stock)'); return False
    ha = ep[SINK_A-EP_D] == 0xE9; hb = ep[SINK_B-EP_D] == 0xE9
    hc = ep[CLEARS-EP_D:CLEARS-EP_D+21] == CLEARS_NEW
    ht = tc[TC_SITE-TC_D] == 0xE9
    if ha and hb and hc and ht: print('APPLIED (all four patches present)'); return True
    print(f'MIXED/UNKNOWN state: sinkA={"hook" if ha else "?" if not a else "stock"} '
          f'sinkB={"hook" if hb else "?" if not b else "stock"} '
          f'clears={"new" if hc else "?" if not c else "stock"} '
          f'tcai={"hook" if ht else "?" if not t else "stock"}')
    sys.exit(2)


def apply():
    ep = rd(EP); tc = rd(TC)
    # asserts: everything stock
    for buf, va, delta, orig, nm in [(ep,SINK_A,EP_D,SINK_A_ORIG,'sinkA'),
                                     (ep,SINK_B,EP_D,SINK_B_ORIG,'sinkB'),
                                     (ep,CLEARS,EP_D,CLEARS_ORIG,'clears'),
                                     (tc,TC_SITE,TC_D,TC_ORIG,'tcai')]:
        cur = bytes(buf[va-delta:va-delta+len(orig)])
        if cur != orig:
            raise SystemExit(f'ABORT: {nm} @{va:#x} unexpected bytes {cur.hex()} (already applied? different build?)')
    cave_ep, lab_ep = build_ep_cave()
    cave_tc, lab_tc = build_tc_cave()
    # cave space must be zeros
    if any(ep[CAVE_EP-EP_D:CAVE_EP-EP_D+len(cave_ep)]):
        raise SystemExit('ABORT: AoWEPACK cave space not zero')
    if any(tc[CAVE_TC-TC_D:CAVE_TC-TC_D+len(cave_tc)]):
        raise SystemExit('ABORT: AoWTCPCK cave space not zero')
    # reloc + branch-target prechecks
    check_relocs(ep, EP_D, [(SINK_A,6),(SINK_B,7),(CLEARS,21),(CAVE_EP,len(cave_ep))], 'AoWEPACK')
    check_relocs(tc, TC_D, [(TC_SITE,len(TC_ORIG)),(CAVE_TC,len(cave_tc))], 'AoWTCPCK')
    check_branch_targets(ep, EP_D, [(SINK_A,6),(SINK_B,7)], 'AoWEPACK sinks')
    check_branch_targets(tc, TC_D, [(TC_SITE,len(TC_ORIG))], 'AoWTCPCK tcai site')
    # backups
    if not os.path.exists(EP_BAK): wr(EP_BAK, ep)
    if not os.path.exists(TC_BAK): wr(TC_BAK, tc)
    # write
    ep[CAVE_EP-EP_D:CAVE_EP-EP_D+len(cave_ep)] = cave_ep
    ep[SINK_A-EP_D:SINK_A-EP_D+6] = hook5(SINK_A, lab_ep['stub1'], 6)
    ep[SINK_B-EP_D:SINK_B-EP_D+7] = hook5(SINK_B, lab_ep['stub2'], 7)
    ep[CLEARS-EP_D:CLEARS-EP_D+21] = CLEARS_NEW
    tc[CAVE_TC-TC_D:CAVE_TC-TC_D+len(cave_tc)] = cave_tc
    tc[TC_SITE-TC_D:TC_SITE-TC_D+len(TC_ORIG)] = hook5(TC_SITE, CAVE_TC, len(TC_ORIG))
    wr(EP, ep); wr(TC, tc)
    print(f'APPLIED. AoWEPACK cave {CAVE_EP:#x} ({len(cave_ep)} B, next free {CAVE_EP+len(cave_ep):#x}), '
          f'AoWTCPCK cave {CAVE_TC:#x} ({len(cave_tc)} B, next free {CAVE_TC+len(cave_tc):#x})')


def revert():
    ep = rd(EP); tc = rd(TC)
    ok = True
    if ep[SINK_A-EP_D] == 0xE9: ep[SINK_A-EP_D:SINK_A-EP_D+6] = SINK_A_ORIG
    elif bytes(ep[SINK_A-EP_D:SINK_A-EP_D+6]) != SINK_A_ORIG: ok = False
    if ep[SINK_B-EP_D] == 0xE9: ep[SINK_B-EP_D:SINK_B-EP_D+7] = SINK_B_ORIG
    elif bytes(ep[SINK_B-EP_D:SINK_B-EP_D+7]) != SINK_B_ORIG: ok = False
    if bytes(ep[CLEARS-EP_D:CLEARS-EP_D+21]) == CLEARS_NEW: ep[CLEARS-EP_D:CLEARS-EP_D+21] = CLEARS_ORIG
    elif bytes(ep[CLEARS-EP_D:CLEARS-EP_D+21]) != CLEARS_ORIG: ok = False
    if tc[TC_SITE-TC_D] == 0xE9: tc[TC_SITE-TC_D:TC_SITE-TC_D+len(TC_ORIG)] = TC_ORIG
    elif bytes(tc[TC_SITE-TC_D:TC_SITE-TC_D+len(TC_ORIG)]) != TC_ORIG: ok = False
    if not ok: raise SystemExit('ABORT: unexpected bytes at a patch site; restore from .bak_defresp manually')
    # zero the caves
    cave_ep, _ = build_ep_cave(); cave_tc, _ = build_tc_cave()
    ep[CAVE_EP-EP_D:CAVE_EP-EP_D+len(cave_ep)] = b'\x00'*len(cave_ep)
    tc[CAVE_TC-TC_D:CAVE_TC-TC_D+len(cave_tc)] = b'\x00'*len(cave_tc)
    wr(EP, ep); wr(TC, tc)
    print('REVERTED (sites restored, caves zeroed)')


if __name__ == '__main__':
    arg = sys.argv[1] if len(sys.argv) > 1 else '--status'
    if arg == '--apply': apply()
    elif arg == '--revert': revert()
    else: status()
