import struct, shutil, os

CAVE_FILE_OFF = 0x10B695
CAVE_AVAIL    = 875
VA_ADJUST     = 0x55700C00

def fva(off): return off + VA_ADJUST
CAVE_VA  = fva(CAVE_FILE_OFF)
JMP_BACK = fva(0xF974B)
URI_VA   = fva(0x4C7C8)

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
    # ADD ECX, (target_offset - base_offset) -- position-independent table base
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
B(0xE8,0,0,0,0)          # CALL +0 -> pushes addr of pic_next, falls through
lbl('pic_next')
B(0x59)                  # POP ECX (ECX = runtime VA of pic_next)
PICREL('pic_next','table')  # ADD ECX, (table - pic_next) -> ECX = runtime table VA
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

# ===== HANDLERS =====
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
code.extend(tbl)

resolve()

code_sz = labels['table']
print(f"Code: {code_sz} bytes  Table: 293  Total: {len(code)} / {CAVE_AVAIL}")

delta = labels['table'] - labels['pic_next']
print(f"PICREL delta: {delta} (0x{delta:X})")

exit_off = labels['exit']
jmp_e9_off = exit_off + 2
next_ip_in_cave = jmp_e9_off + 1 + 4
jmp_target = (CAVE_VA + next_ip_in_cave + struct.unpack_from('<i',code,jmp_e9_off+1)[0]) & 0xFFFFFFFF
print(f"JMP back: 0x{jmp_target:08X}  expected: 0x{JMP_BACK:08X}  {'OK' if jmp_target==JMP_BACK else 'FAIL'}")

assert len(code) <= CAVE_AVAIL

DLL = "C:/Users/<user>/Desktop/Age of Wonders X - Claude/AoWEPACK.dll"
with open(DLL,'r+b') as f:
    f.seek(CAVE_FILE_OFF)
    f.write(code)
with open(DLL,'rb') as f:
    f.seek(CAVE_FILE_OFF)
    verify=f.read(len(code))
assert verify==bytes(code)
print("Written and verified OK")

pic_call = labels['pic_next'] - 5
print(f"\nPIC block:")
print(f"  CALL+0:             {' '.join(f'{code[i]:02X}' for i in range(pic_call, pic_call+5))}")
print(f"  POP ECX:            {code[labels['pic_next']]:02X}")
add_off = labels['pic_next']+1
print(f"  ADD ECX,delta:      {' '.join(f'{code[i]:02X}' for i in range(add_off, add_off+6))}")
movzx_off = add_off+6
print(f"  MOVZX EDX,[ECX+EAX]:{' '.join(f'{code[i]:02X}' for i in range(movzx_off, movzx_off+4))}")
