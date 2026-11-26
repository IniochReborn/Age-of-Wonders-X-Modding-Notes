"""
Combined AD+RS patch applier for rollback state.

Writes all caves/subroutines fresh, bypassing the incremental version checks
that the individual scripts require. Targets the post-rollback DLL state where
the 4 small JMP/NOP patches are already applied but all cave space is zero.

Locations written:
  0x10BAD2  TRecallSpiritCA v5 summoned cave (54 bytes)
  0x10BB08  TAnimateDeadCA  v5 summoned cave (54 bytes)
  0x10C20D  Animate Dead spawn cave v3 (≤902 bytes + 293-byte table)
  0x10CD8D  Recall Spirit spawn cave v1 (≤411 bytes + 293-byte table)
  0x10D04D  Upkeep subroutine v2 (155 bytes code + 16 zero pad = 171 bytes)

Patch applied:
  0xF9526   BA 82 00 00 00  →  E9 62 38 01 00  (JMP to RS spawn cave)

JMPs already in place (applied during rollback re-implementation):
  0x24166   90*6           (Animate Dead persist)
  0xF9549   E9 84 25 01 00 (JMP to TRecallSpiritCA v5 cave)
  0xF9746   E9 C2 2A 01 00 (JMP to AD spawn cave)
  0xF9769   E9 9A 23 01 00 (JMP to TAnimateDeadCA v5 cave)
"""
import struct

DLL       = "C:/Users/<user>/Desktop/Age of Wonders X - Claude/AoWEPACK.dll"
VA_ADJUST = 0x55700C00

def fva(off): return off + VA_ADJUST

URI_VA = fva(0x4C7C8)   # TUnitResource.UnitResourceIndex

# ── File offsets ───────────────────────────────────────────────────────────────
CAVE1_FILE_OFF = 0x10BAD2   # TRecallSpiritCA v5 cave
CAVE2_FILE_OFF = 0x10BB08   # TAnimateDeadCA  v5 cave
SUB_FILE_OFF   = 0x10D04D   # Upkeep sub v2 (final location)
AD_CAVE_OFF    = 0x10C20D   # AD spawn cave v3
RS_CAVE_OFF    = 0x10CD8D   # RS spawn cave v1
RS_SPAWN_OFF   = 0xF9526    # RS spawn MOV EDX patch site

# Return sites for the v5 summoned caves
RET1_FILE_OFF  = 0xF9558    # PATCH1 (0xF9549) + 15
RET2_FILE_OFF  = 0xF9778    # PATCH2 (0xF9769) + 15

# ══════════════════════════════════════════════════════════════════════════════
# 1. Upkeep subroutine v2 (171-byte block; code=155, pad=16)
# ══════════════════════════════════════════════════════════════════════════════
# Rates: 133->10, 243->8, 216->8, 204->6, 206->6, 44->6, 200->3, 223->3,
#        241->3, else->2
def build_upkeep_sub():
    sub_va = fva(SUB_FILE_OFF)
    s      = bytearray()
    labels = {}
    fixups = []

    def here(): return len(s)
    def lbl(n): labels[n] = here()
    def B(*bs): s.extend(bs)
    def I32(v): s.extend(struct.pack('<I', v & 0xFFFFFFFF))
    def JE(n):  B(0x0F, 0x84); fixups.append((here(), n)); I32(0)
    def resolve():
        for off, name in fixups:
            struct.pack_into('<I', s, off, (labels[name] - off - 4) & 0xFFFFFFFF)
    def SET(val):
        B(0xC7, 0x41, 0x10); I32(val)   # mov dword [ecx+10h], val
        B(0xC3)                           # ret

    B(0x8B, 0x4B, 0x10)   # mov ecx, [ebx+10h]  TUnitEnchantmentAbilityData
    B(0x8B, 0x49, 0x10)   # mov ecx, [ecx+10h]  TUnitEnchantment
    B(0x51)               # push ecx
    B(0x8B, 0x43, 0x40)   # mov eax, [ebx+40h]  TUnitResource ptr
    B(0xE8); I32((URI_VA - (sub_va + here() + 4)) & 0xFFFFFFFF)
    B(0x59)               # pop ecx

    B(0x3D); I32(133); JE('set10')
    B(0x3D); I32(243); JE('set8')
    B(0x3D); I32(216); JE('set8')
    B(0x3D); I32(204); JE('set6')
    B(0x3D); I32(206); JE('set6')
    B(0x3D); I32(44);  JE('set6')
    B(0x3D); I32(200); JE('set3')
    B(0x3D); I32(223); JE('set3')
    B(0x3D); I32(241); JE('set3')
    SET(2)

    lbl('set10'); SET(10)
    lbl('set8');  SET(8)
    lbl('set6');  SET(6)
    lbl('set3');  SET(3)

    resolve()
    BLOCK_SIZE = 171
    code_bytes = bytes(s)
    full_block = code_bytes + b'\x00' * (BLOCK_SIZE - len(code_bytes))
    assert len(full_block) == BLOCK_SIZE, f"Upkeep sub size: {len(code_bytes)} code bytes"
    return full_block

# ══════════════════════════════════════════════════════════════════════════════
# 2. v5 summoned caves (54 bytes each)
# ══════════════════════════════════════════════════════════════════════════════
def build_summoned_cave(cave_file_off, ret_file_off):
    cave_va = fva(cave_file_off)
    sub_va  = fva(SUB_FILE_OFF)
    code    = bytearray()

    code += b'\xC7\x43\x18\x01\x00\x00\x00'  # mov dword [ebx+18h], 1
    code += b'\xBA\x9B\x00\x00\x00'           # mov edx, 0x9B
    code += b'\x8B\xC3'                        # mov eax, ebx
    code += b'\x8B\x08'                        # mov ecx, [eax]
    code += b'\xFF\x91\x94\x00\x00\x00'       # call [ecx+94h]  ExpandAbility
    code += b'\x8B\x43\x10'                    # mov eax, [ebx+10h]
    code += b'\x8B\x40\x10'                    # mov eax, [eax+10h]
    code += b'\x31\xD2'                        # xor edx, edx
    code += b'\x89\x50\x18'                    # mov [eax+18h], edx
    code += b'\x8A\x53\x24'                    # mov dl, [ebx+24h]
    code += b'\x8B\x08'                        # mov ecx, [eax]
    code += b'\xFF\x91\x58\x00\x00\x00'       # call [ecx+58h]  SetSource

    # call upkeep sub
    next_ip = cave_va + len(code) + 5
    code += b'\xE8' + struct.pack('<I', (sub_va - next_ip) & 0xFFFFFFFF)

    # jmp back to return site
    next_ip = cave_va + len(code) + 5
    code += b'\xE9' + struct.pack('<I', (fva(ret_file_off) - next_ip) & 0xFFFFFFFF)

    assert len(code) == 54, f"Summoned cave size: {len(code)}"
    return bytes(code)

# ══════════════════════════════════════════════════════════════════════════════
# 3. Animate Dead spawn cave v3 (≤902 bytes code, then 293-byte table)
# ══════════════════════════════════════════════════════════════════════════════
def build_ad_cave():
    CAVE_VA  = fva(AD_CAVE_OFF)
    JMP_BACK = fva(0xF974B)
    AVAIL    = 902   # 0x10C593 - 0x10C20D

    code=bytearray(); labels={}; fixups=[]
    def here():    return len(code)
    def lbl(n):    labels[n]=here()
    def B(*bs):    code.extend(bs)
    def I32(v):    code.extend(struct.pack('<I',v&0xFFFFFFFF))
    def CALL(va):  B(0xE8); I32((va-(CAVE_VA+here()+4))&0xFFFFFFFF)
    def JMP_VA(va):B(0xE9); I32((va-(CAVE_VA+here()+4))&0xFFFFFFFF)
    def JMP(n):    B(0xE9);      fixups.append((here(),n,'r32')); I32(0)
    def JE(n):     B(0x0F,0x84); fixups.append((here(),n,'r32')); I32(0)
    def JZ(n):     JE(n)
    def JA(n):     B(0x0F,0x87); fixups.append((here(),n,'r32')); I32(0)
    def JB(n):     B(0x0F,0x82); fixups.append((here(),n,'r32')); I32(0)
    def PICREL(base_lbl, target_lbl):
        B(0x81,0xC1); fixups.append((here(),(base_lbl,target_lbl),'picrel')); I32(0)

    def resolve():
        for off,name,typ in fixups:
            if typ=='r32':
                t=labels[name]
                struct.pack_into('<I',code,off,(t-off-4)&0xFFFFFFFF)
            elif typ=='picrel':
                base_lbl,tgt_lbl=name
                val=(labels[tgt_lbl]-labels[base_lbl])&0xFFFFFFFF
                struct.pack_into('<I',code,off,val)

    # Prologue: get unit type ID via URI, then RNG
    B(0x50); B(0x53)
    B(0x8B,0x46,0x4C); B(0x8B,0x40,0x40)
    CALL(URI_VA)
    B(0x3D); I32(292); JA('swordsman')
    B(0x50)
    B(0x0F,0x31); B(0x31,0xD2); B(0xB9); I32(100); B(0xF7,0xF1)
    B(0x89,0xD1)
    B(0x58)

    # PIC table lookup
    B(0x51); B(0xE8,0,0,0,0); lbl('pic_next'); B(0x59)
    PICREL('pic_next','table')
    B(0x0F,0xB6,0x14,0x01); B(0x59)

    # Dispatch (18 groups; group 18 falls through)
    B(0x85,0xD2); JZ('swordsman')
    B(0x83,0xFA,1);  JE('horse')
    B(0x83,0xFA,2);  JE('mummy')
    B(0x83,0xFA,3);  JE('mummy_sub1')
    B(0x83,0xFA,4);  JE('mummy_166')
    B(0x83,0xFA,5);  JE('mummy_self')
    B(0x83,0xFA,6);  JE('horse_self')
    B(0x83,0xFA,7);  JE('wraith')
    B(0x83,0xFA,8);  JE('wraith_i1')
    B(0x83,0xFA,9);  JE('wraith_i2')
    B(0x83,0xFA,10); JE('wraith_self')
    B(0x83,0xFA,11); JE('horror')
    B(0x83,0xFA,12); JE('horror_sub')
    B(0x83,0xFA,13); JE('horror_self')
    B(0x83,0xFA,14); JE('dragon')
    B(0x83,0xFA,15); JE('dragon_self')
    B(0x83,0xFA,16); JE('ram')
    B(0x83,0xFA,17); JE('hound')
    # group 18 (hound_self) falls through

    # Handlers
    lbl('hound_self');  B(0x83,0xF9,70); JB('hound_prim'); JMP('swordsman')
    lbl('dragon_self'); B(0x83,0xF9,50); JB('dragon_prim')
    lbl('swordsman');   B(0xBA); I32(201); JMP('exit')
    lbl('dragon_prim'); B(0xBA); I32(243); JMP('exit')
    lbl('horse');       B(0x83,0xF9,80); JB('horse_prim'); JMP('swordsman')
    lbl('horse_prim');  B(0xBA); I32(200); JMP('exit')
    lbl('horse_self');  B(0x83,0xF9,50); JB('horse_prim'); JMP('swordsman')
    lbl('mummy');       B(0x83,0xF9,80); JB('mummy_prim'); JMP('swordsman')
    lbl('mummy_prim');  B(0xBA); I32(223); JMP('exit')
    lbl('mummy_self');  B(0x83,0xF9,50); JB('mummy_prim'); JMP('swordsman')
    lbl('mummy_sub1');  B(0x83,0xF9,10); JB('m_sub1_w'); B(0x83,0xF9,82); JB('mummy_prim'); JMP('swordsman')
    lbl('m_sub1_w');    B(0xBA); I32(206); JMP('exit')
    lbl('mummy_166');   B(0x83,0xF9,10); JB('m166_h'); B(0x83,0xF9,82); JB('mummy_prim'); JMP('swordsman')
    lbl('m166_h');      B(0xBA); I32(204); JMP('exit')
    lbl('wraith');      B(0x83,0xF9,80); JB('wraith_prim'); JMP('swordsman')
    lbl('wraith_prim'); B(0xBA); I32(206); JMP('exit')
    lbl('wraith_self'); B(0x83,0xF9,50); JB('wraith_prim'); JMP('swordsman')
    lbl('wraith_i1');   B(0x83,0xF9,20); JB('wraith_prim'); JMP('swordsman')
    lbl('wraith_i2');   B(0x83,0xF9,10); JB('wraith_prim'); JMP('swordsman')
    lbl('horror');      B(0x83,0xF9,80); JB('horror_prim'); JMP('swordsman')
    lbl('horror_prim'); B(0xBA); I32(204); JMP('exit')
    lbl('horror_self'); B(0x83,0xF9,50); JB('horror_prim'); JMP('swordsman')
    lbl('horror_sub');  B(0x83,0xF9,10); JB('h_sub_sp'); B(0x83,0xF9,82); JB('horror_prim'); JMP('swordsman')
    lbl('h_sub_sp');    B(0xBA); I32(249); JMP('exit')
    lbl('dragon');      B(0x83,0xF9,80); JB('dragon_prim'); JMP('swordsman')
    lbl('hound');       B(0x83,0xF9,80); JB('hound_prim'); JMP('swordsman')
    lbl('hound_prim');  B(0xBA); I32(202); JMP('exit')
    lbl('ram');         B(0x83,0xF9,80); JB('ram_prim'); JMP('swordsman')
    lbl('ram_prim');    B(0xBA); I32(249); JMP('exit')
    lbl('exit');        B(0x5B); B(0x58); JMP_VA(JMP_BACK)

    # Table (293 bytes)
    lbl('table')
    tbl=[0]*293
    for u in [2,6,20,74,79,92,98,128,132,146,149,164,270,271,281]: tbl[u]=1
    tbl[200]=6
    for u in [1,5,19,37,55,73,78,91,94,109,127,145,163,169,181,189,199,229,238]: tbl[u]=2
    for u in [22,25,42,97,115,134,150,240]: tbl[u]=3
    tbl[166]=4; tbl[223]=5
    for u in [44,80,133,152,203,224,225,226,227,282]: tbl[u]=7
    for u in [151,205,241]: tbl[u]=8
    for u in [76,130]: tbl[u]=9
    tbl[206]=10
    for u in [24,26,41,65,113,116,131,184,187,188,218,221,244,264]: tbl[u]=11
    for u in [23,28,29,45,265]: tbl[u]=12
    tbl[204]=13
    for u in [43,61,170,185,216,217,252,288,289,290,291,292]: tbl[u]=14
    tbl[243]=15
    for u in [62,63,64]: tbl[u]=16
    for u in [38,182,228,237,239,242]: tbl[u]=17
    tbl[202]=18
    code.extend(tbl)

    resolve()

    code_sz = labels['table']
    total   = len(code)
    print(f"AD cave: code={code_sz}B, table=293B, total={total}B / {AVAIL}B avail")
    assert total <= AVAIL, f"AD cave overflow: {total} > {AVAIL}"
    return bytes(code)

# ══════════════════════════════════════════════════════════════════════════════
# 4. Recall Spirit spawn cave v1 (≤411 bytes code, then 293-byte table)
# ══════════════════════════════════════════════════════════════════════════════
def build_rs_cave():
    CAVE_VA  = fva(RS_CAVE_OFF)
    JMP_BACK = fva(0xF952B)
    AVAIL    = 704  # 0x10D04D - 0x10CD8D

    code=bytearray(); labels={}; fixups=[]
    def here():    return len(code)
    def lbl(n):    labels[n]=here()
    def B(*bs):    code.extend(bs)
    def I32(v):    code.extend(struct.pack('<I',v&0xFFFFFFFF))
    def CALL(va):  B(0xE8); I32((va-(CAVE_VA+here()+4))&0xFFFFFFFF)
    def JMP_VA(va):B(0xE9); I32((va-(CAVE_VA+here()+4))&0xFFFFFFFF)
    def JMP(n):    B(0xE9);       fixups.append((here(),n,'r32')); I32(0)
    def JE(n):     B(0x0F,0x84); fixups.append((here(),n,'r32')); I32(0)
    def JZ(n):     JE(n)
    def JA(n):     B(0x0F,0x87); fixups.append((here(),n,'r32')); I32(0)
    def JB(n):     B(0x0F,0x82); fixups.append((here(),n,'r32')); I32(0)
    def PICREL(base_lbl, target_lbl):
        B(0x81,0xC1); fixups.append((here(),(base_lbl,target_lbl),'picrel')); I32(0)

    def resolve():
        for off,name,typ in fixups:
            if typ=='r32':
                t=labels[name]
                struct.pack_into('<I',code,off,(t-off-4)&0xFFFFFFFF)
            elif typ=='picrel':
                base_lbl,tgt_lbl=name
                val=(labels[tgt_lbl]-labels[base_lbl])&0xFFFFFFFF
                struct.pack_into('<I',code,off,val)

    # Prologue
    B(0x50); B(0x53)
    B(0x8B,0x46,0x4C); B(0x8B,0x40,0x40)
    CALL(URI_VA)

    # RNG before bounds check
    B(0x50)
    B(0x0F,0x31); B(0x31,0xD2); B(0xB9); I32(100); B(0xF7,0xF1)
    B(0x89,0xD1)
    B(0x58)

    # Bounds check
    B(0x3D); I32(292); JA('default')

    # PIC table lookup
    B(0x51); B(0xE8,0,0,0,0); lbl('pic_next'); B(0x59)
    PICREL('pic_next','table')
    B(0x0F,0xB6,0x14,0x01); B(0x59)

    # Dispatch (8 groups; group 7 falls through to spirit216)
    B(0x85,0xD2); JZ('default')
    B(0x83,0xFA,1); JE('greater')
    B(0x83,0xFA,2); JE('g241_self')
    B(0x83,0xFA,3); JE('glow_mix')
    B(0x83,0xFA,4); JE('unit42')
    B(0x83,0xFA,5); JE('glow')
    B(0x83,0xFA,6); JE('spirit133')
    # group 7 falls through to spirit216

    # Handlers
    lbl('spirit216'); B(0x83,0xF9,90); JB('ghost_prim'); JMP('s216_prim')
    lbl('default');   B(0x83,0xF9,80); JB('rs_prim');    JMP('ghost_prim')
    lbl('greater');   B(0x83,0xF9,80); JB('ghost_prim'); JMP('rs_prim')
    lbl('g241_self'); B(0x83,0xF9,50); JB('ghost_prim'); JMP('rs_prim')
    lbl('glow_mix');  B(0x83,0xF9,10); JB('glow_prim'); B(0x83,0xF9,30); JB('rs_prim'); JMP('ghost_prim')
    lbl('unit42');    B(0x83,0xF9,40); JB('glow_prim'); B(0x83,0xF9,60); JB('rs_prim'); JMP('ghost_prim')
    lbl('glow');      B(0x83,0xF9,20); JB('glow_prim'); B(0x83,0xF9,40); JB('rs_prim'); JMP('ghost_prim')
    lbl('spirit133'); B(0x83,0xF9,80); JB('ghost_prim'); JMP('s133_prim')

    # Primaries
    lbl('s216_prim');  B(0xBA); I32(216); JMP('exit')
    lbl('s133_prim');  B(0xBA); I32(133); JMP('exit')
    lbl('rs_prim');    B(0xBA); I32(130); JMP('exit')
    lbl('ghost_prim'); B(0xBA); I32(241); JMP('exit')
    lbl('glow_prim');  B(0xBA); I32(44);  JMP('exit')
    lbl('exit');       B(0x5B); B(0x58); JMP_VA(JMP_BACK)

    # Table (293 bytes)
    lbl('table')
    tbl=[0]*293

    # Group 1: major undead — 80% ghost(241), 20% spirit(130)
    for u in [1,5,6,19,22,24,25,55,58,65,73,76,78,79,80,91,95,96,97,98,
              109,115,127,131,132,134,145,149,150,152,163,166,170,181,
              187,189,199,205,206,217,221,223,229,234,238,240,243,244,
              252,264,288,290,291]:
        tbl[u]=1
    # Group 2: ghost(241) corpse — 50/50
    tbl[241]=2
    # Group 3: glow-adjacent — 10% glow, 20% spirit, 70% ghost
    for u in [37,41,43,289]: tbl[u]=3
    # Group 4: unit 42 — 40% glow, 20% spirit, 40% ghost
    tbl[42]=4
    # Group 5: glow creatures — 20% glow, 20% spirit, 60% ghost
    for u in [44,224,225,226,227,282]: tbl[u]=5
    # Group 6: spirit 133 / related — 80% ghost, 20% spirit133
    for u in [133,203]: tbl[u]=6
    # Group 7: spirit 216 / related — 90% ghost, 10% spirit216
    for u in [216,292]: tbl[u]=7

    code.extend(tbl)
    resolve()

    code_sz = labels['table']
    total   = len(code)
    print(f"RS cave: code={code_sz}B, table=293B, total={total}B / {AVAIL}B avail")
    assert total <= AVAIL, f"RS cave overflow: {total} > {AVAIL}"
    return bytes(code)

# ══════════════════════════════════════════════════════════════════════════════
# Build everything
# ══════════════════════════════════════════════════════════════════════════════
upkeep_sub = build_upkeep_sub()
cave1      = build_summoned_cave(CAVE1_FILE_OFF, RET1_FILE_OFF)
cave2      = build_summoned_cave(CAVE2_FILE_OFF, RET2_FILE_OFF)
ad_cave    = build_ad_cave()
rs_cave    = build_rs_cave()

# RS spawn JMP patch
_rs_rel      = (fva(RS_CAVE_OFF) - fva(RS_SPAWN_OFF + 5)) & 0xFFFFFFFF
rs_spawn_jmp = b'\xE9' + struct.pack('<I', _rs_rel)
assert rs_spawn_jmp == bytes([0xE9, 0x62, 0x38, 0x01, 0x00]), \
    f"RS spawn JMP unexpected: {rs_spawn_jmp.hex(' ')}"

print(f"Upkeep sub : {len(upkeep_sub)}B @ 0x{SUB_FILE_OFF:X}")
print(f"Cave1      : {len(cave1)}B @ 0x{CAVE1_FILE_OFF:X}")
print(f"Cave2      : {len(cave2)}B @ 0x{CAVE2_FILE_OFF:X}")
print(f"AD spawn   : {len(ad_cave)}B @ 0x{AD_CAVE_OFF:X}")
print(f"RS spawn   : {len(rs_cave)}B @ 0x{RS_CAVE_OFF:X}")
print(f"RS JMP     : {rs_spawn_jmp.hex(' ')} @ 0x{RS_SPAWN_OFF:X}")

# ══════════════════════════════════════════════════════════════════════════════
# Pre-checks: verify rollback state
# ══════════════════════════════════════════════════════════════════════════════
RS_SPAWN_ORIG = bytes([0xBA, 0x82, 0x00, 0x00, 0x00])

with open(DLL, 'rb') as f:
    f.seek(RS_SPAWN_OFF);    cur_rs_spawn = f.read(5)
    f.seek(CAVE1_FILE_OFF);  cur_cave1    = f.read(4)
    f.seek(CAVE2_FILE_OFF);  cur_cave2    = f.read(4)
    f.seek(AD_CAVE_OFF);     cur_ad       = f.read(4)
    f.seek(RS_CAVE_OFF);     cur_rs       = f.read(4)
    f.seek(SUB_FILE_OFF);    cur_sub      = f.read(4)

assert cur_rs_spawn == RS_SPAWN_ORIG, \
    f"0x{RS_SPAWN_OFF:X} not original RS spawn MOV: {cur_rs_spawn.hex(' ')}"
assert cur_cave1 == b'\x00'*4, f"Cave1 not zero: {cur_cave1.hex(' ')}"
assert cur_cave2 == b'\x00'*4, f"Cave2 not zero: {cur_cave2.hex(' ')}"
assert cur_ad    == b'\x00'*4, f"AD cave not zero: {cur_ad.hex(' ')}"
assert cur_rs    == b'\x00'*4, f"RS cave not zero: {cur_rs.hex(' ')}"
assert cur_sub   == b'\x00'*4, f"Upkeep sub not zero: {cur_sub.hex(' ')}"

print("Pre-checks passed (rollback state confirmed).")

# ══════════════════════════════════════════════════════════════════════════════
# Apply
# ══════════════════════════════════════════════════════════════════════════════
with open(DLL, 'r+b') as f:
    f.seek(SUB_FILE_OFF);   f.write(upkeep_sub)
    f.seek(CAVE1_FILE_OFF); f.write(cave1)
    f.seek(CAVE2_FILE_OFF); f.write(cave2)
    f.seek(AD_CAVE_OFF);    f.write(ad_cave)
    f.seek(RS_CAVE_OFF);    f.write(rs_cave)
    f.seek(RS_SPAWN_OFF);   f.write(rs_spawn_jmp)

# ══════════════════════════════════════════════════════════════════════════════
# Verify
# ══════════════════════════════════════════════════════════════════════════════
with open(DLL, 'rb') as f:
    f.seek(SUB_FILE_OFF);   assert f.read(len(upkeep_sub)) == upkeep_sub
    f.seek(CAVE1_FILE_OFF); assert f.read(len(cave1))      == cave1
    f.seek(CAVE2_FILE_OFF); assert f.read(len(cave2))      == cave2
    f.seek(AD_CAVE_OFF);    assert f.read(len(ad_cave))    == ad_cave
    f.seek(RS_CAVE_OFF);    assert f.read(len(rs_cave))    == rs_cave
    f.seek(RS_SPAWN_OFF);   assert f.read(5)               == rs_spawn_jmp

print("Written and verified OK.")
print()
print("Active patch summary:")
print(f"  0x{RS_SPAWN_OFF:X} : {RS_SPAWN_ORIG.hex(' ')} -> {rs_spawn_jmp.hex(' ')}  (RS spawn JMP)")
print(f"  0x{CAVE1_FILE_OFF:X}: TRecallSpiritCA v5 cave ({len(cave1)}B) -> upkeep sub @ 0x{SUB_FILE_OFF:X}")
print(f"  0x{CAVE2_FILE_OFF:X}: TAnimateDeadCA  v5 cave ({len(cave2)}B) -> upkeep sub @ 0x{SUB_FILE_OFF:X}")
print(f"  0x{AD_CAVE_OFF:X}: Animate Dead spawn cave v3 ({len(ad_cave)}B)")
print(f"  0x{RS_CAVE_OFF:X}: Recall Spirit spawn cave v1 ({len(rs_cave)}B)")
print(f"  0x{SUB_FILE_OFF:X}: Upkeep sub v2 ({len(upkeep_sub)}B)")
print()
print("Upkeep rates: 133->10, 243->8, 216->8, 204->6, 206->6, 44->6,")
print("              200->3, 223->3, 241->3, else->2")
