import struct

# Cave moved to 0x10C20D (1011 zero bytes available) to make room for
# RAM (groups 62,63,64 -> 249) and HOUND (groups 38,182,228,237,239,242 -> 202)
# entries that didn't fit in the original 875-byte cave.
CAVE_FILE_OFF = 0x10C20D
CAVE_AVAIL    = 1011
VA_ADJUST     = 0x55700C00

def fva(off): return off + VA_ADJUST
CAVE_VA  = fva(CAVE_FILE_OFF)
JMP_BACK = fva(0xF974B)
URI_VA   = fva(0x4C7C8)

# Old cave to clear
OLD_CAVE_FILE_OFF = 0x10B695
OLD_CAVE_SIZE     = 813

# 5-byte JMP patch site (same as v2)
JMP_PATCH_OFF = 0xF9746
JMP_PATCH_OLD = bytes([0xE9, 0x4A, 0x1F, 0x01, 0x00])   # v2 — points to old cave

# Compute new 5-byte JMP patch
_next_ip = 0xF974B
_rel = (fva(CAVE_FILE_OFF) - fva(_next_ip)) & 0xFFFFFFFF
JMP_PATCH_NEW = b'\xE9' + struct.pack('<I', _rel)
assert len(JMP_PATCH_NEW) == 5

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

# ===== PROLOGUE =====
B(0x50); B(0x53)
B(0x8B,0x46,0x4C); B(0x8B,0x40,0x40)
CALL(URI_VA)
B(0x3D); I32(292); JA('swordsman')
B(0x50)
B(0x0F,0x31)
B(0x31,0xD2)
B(0xB9); I32(100)
B(0xF7,0xF1)
B(0x89,0xD1)
B(0x58)

# PIC table lookup
B(0x51)                  # PUSH ECX (save random)
B(0xE8,0,0,0,0)          # CALL +0 -> pushes addr of pic_next
lbl('pic_next')
B(0x59)                  # POP ECX (ECX = runtime VA of pic_next)
PICREL('pic_next','table')  # ADD ECX, (table - pic_next)
B(0x0F,0xB6,0x14,0x01)  # MOVZX EDX, BYTE [ECX+EAX]
B(0x59)                  # POP ECX (restore random)

# ===== DISPATCH =====
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
B(0x83,0xFA,15); JE('dragon_self')  # explicit (was implicit fall-through in v2)
B(0x83,0xFA,16); JE('ram')          # NEW: RAM group
B(0x83,0xFA,17); JE('hound')        # NEW: HOUND group
# Group 18 (hound_self) falls through to first handler below

# ===== HANDLERS =====
# hound_self placed first as fall-through target for group 18 (unit 202 corpse)
# 70% -> spawn 202, 30% -> swordsman (anti-spam: harder to chain-animate)
lbl('hound_self'); B(0x83,0xF9,70); JB('hound_prim'); JMP('swordsman')

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
# NEW: hound (corpses 38,182,228,237,239,242) -> 80% spawn 202, 20% swordsman
lbl('hound');       B(0x83,0xF9,80); JB('hound_prim'); JMP('swordsman')
lbl('hound_prim');  B(0xBA); I32(202); JMP('exit')
# NEW: ram (corpses 62,63,64) -> 80% spawn 249, 20% swordsman
lbl('ram');         B(0x83,0xF9,80); JB('ram_prim');  JMP('swordsman')
lbl('ram_prim');    B(0xBA); I32(249); JMP('exit')
lbl('exit');        B(0x5B); B(0x58); JMP_VA(JMP_BACK)

# ===== TABLE =====
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
# NEW entries
for u in [62,63,64]: tbl[u]=16           # RAM -> spawn 249
for u in [38,182,228,237,239,242]: tbl[u]=17  # HOUND -> spawn 202
tbl[202]=18                               # HOUND corpse -> spawn 202 (30% swordsman)
code.extend(tbl)

resolve()

code_sz = labels['table']
print(f"Code: {code_sz} bytes  Table: 293  Total: {len(code)} / {CAVE_AVAIL}")
assert len(code) <= CAVE_AVAIL, f"Cave overflow: {len(code)} > {CAVE_AVAIL}"

delta = labels['table'] - labels['pic_next']
print(f"PICREL delta: {delta} (0x{delta:X})")

exit_off = labels['exit']
jmp_e9_off = exit_off + 2
next_ip_in_cave = jmp_e9_off + 1 + 4
jmp_target = (CAVE_VA + next_ip_in_cave + struct.unpack_from('<i',code,jmp_e9_off+1)[0]) & 0xFFFFFFFF
print(f"JMP back: 0x{jmp_target:08X}  expected: 0x{JMP_BACK:08X}  {'OK' if jmp_target==JMP_BACK else 'FAIL'}")
print(f"JMP patch: {JMP_PATCH_NEW.hex(' ')}  (0x{CAVE_FILE_OFF:X})")

# ── Pre-checks (verify v2 state) ──────────────────────────────────────────────
OLD_CAVE_SIG = bytes([0x50, 0x53, 0x8B, 0x46])  # push eax; push ebx; mov eax,[esi+4Ch]

DLL = "C:/Users/<user>/Desktop/Age of Wonders X - Claude/AoWEPACK.dll"
with open(DLL, 'rb') as f:
    f.seek(JMP_PATCH_OFF);    cur_jmp      = f.read(5)
    f.seek(OLD_CAVE_FILE_OFF); cur_old_cave = f.read(4)
    f.seek(CAVE_FILE_OFF);    new_space    = f.read(len(code))

assert cur_jmp      == JMP_PATCH_OLD, f"JMP patch not v2: {cur_jmp.hex(' ')}"
assert cur_old_cave == OLD_CAVE_SIG,  f"Old cave sig mismatch: {cur_old_cave.hex(' ')}"
assert new_space    == b'\x00' * len(code), \
    f"New cave not zero at 0x{CAVE_FILE_OFF:X}: {new_space[:16].hex(' ')}..."

print("Pre-checks passed (v2 state confirmed).")

# ── Apply ─────────────────────────────────────────────────────────────────────
with open(DLL, 'r+b') as f:
    f.seek(CAVE_FILE_OFF);     f.write(code)
    f.seek(JMP_PATCH_OFF);     f.write(JMP_PATCH_NEW)
    f.seek(OLD_CAVE_FILE_OFF); f.write(b'\x00' * OLD_CAVE_SIZE)

# ── Verify ────────────────────────────────────────────────────────────────────
with open(DLL, 'rb') as f:
    f.seek(CAVE_FILE_OFF);     assert f.read(len(code)) == bytes(code)
    f.seek(JMP_PATCH_OFF);     assert f.read(5) == JMP_PATCH_NEW
    f.seek(OLD_CAVE_FILE_OFF); assert f.read(OLD_CAVE_SIZE) == b'\x00' * OLD_CAVE_SIZE

print("Written and verified OK.")
print()
print(f"  Cave moved: 0x{OLD_CAVE_FILE_OFF:X} -> 0x{CAVE_FILE_OFF:X} ({len(code)} bytes)")
print(f"  JMP at 0x{JMP_PATCH_OFF:X}: {JMP_PATCH_OLD.hex(' ')} -> {JMP_PATCH_NEW.hex(' ')}")
print()
print("  New groups:")
print("    16 RAM  (62,63,64)                : 80% -> 249, 20% -> 201")
print("    17 HOUND(38,182,228,237,239,242)  : 80% -> 202, 20% -> 201")
print("    18 HOUND corpse (202)             : 70% -> 202, 30% -> 201")
