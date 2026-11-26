import struct, shutil
from keystone import Ks, KS_ARCH_X86, KS_MODE_32
from capstone import Cs, CS_ARCH_X86, CS_MODE_32
ks=Ks(KS_ARCH_X86,KS_MODE_32); cs=Cs(CS_ARCH_X86,CS_MODE_32)
FILE="AoWEPACK.dll"
shutil.copy("AoWEPACK.dll.bak_preheroai", FILE)
data=bytearray(open(FILE,'rb').read())
def o(va): return va-0x55700C00

CAVE_ELIG=0x5580FD40
GETAB=0x557501c0; ADDAB=0x55702fcc; GMGR=0x558fa044; PICK=0x55787C21
DONE=0x55787d2a; EXIT=0x55787d43
STAT=[0x55787c90,0x55787ca0,0x55787cad,0x55787cba,0x55787cc7]

# (id, name, unaffordable/bank weight, affordable/lock-in weight)
ABILS=[
 (0x16,"Archery",          5,   5),
 (0x6F,"Charge",          25,  25),
 (0x08,"Cold Immunity",    5,   5),
 (0x0F,"Cold Strike",     25, 500),
 (0x0B,"Death Immunity",   5,   5),
 (0x12,"Death Strike",     5,   5),
 (0x1C,"Dominate",        10, 100),
 (0x37,"Doom Gaze",       25, 250),
 (0x73,"Extra Strike",    25,  50),
 (0x07,"Fire Immunity",    5,   5),
 (0x0E,"Fire Strike",     10,  10),
 (0x74,"First Strike",   250,5000),
 (0x7A,"Frost Bolts",      5,   5),
 (0x2F,"Healing",         50,  50),
 (0x38,"Hero Slaying",    75, 150),
 (0x0C,"Holy Immunity",    5,   5),
 (0x13,"Holy Strike",      5,   5),
 (0x2E,"Leadership",      50,  50),
 (0x76,"Lifestealing",    25,  75),
 (0x7B,"Lightning Bolts",  5,  25),
 (0x09,"Lightning Immunity",5, 5),
 (0x10,"Lightning Strike",250,5000),
 (0x79,"Magic Bolts",     10,  10),
 (0x20,"Marksmanship",     5,   5),
 (0x70,"Monster Slaying", 25,  25),
 (0x71,"Parry",           30,  30),
 (0x11,"Poison Strike",   10,  10),
 (0x72,"Round Attack",     5,   5),
 (0x3A,"Seeker Bolts",    25, 250),
 (0x34,"Spellcasting",   250,2000),
]
NENT=len(ABILS)
IDS   =[t[0] for t in ABILS]
UNAFF =[t[2] for t in ABILS]
AFF   =[t[3] for t in ABILS]
assert all(1<=w<=65535 for w in UNAFF+AFF)
assert len(set(IDS))==NENT, "duplicate id!"

def elig_src(ID_VA, UN_VA, AF_VA):
    gd=CAVE_ELIG+6
    return f"""
    push ebp
    call gd
    gd: pop ebp
    sub ebp, {gd}
    push 0
    lp:
      mov eax, [esp]
      cmp eax, {NENT}
      jge done
      lea ecx, [ebp + {ID_VA}]
      movzx edx, byte ptr [ecx + eax]
      mov eax, [ebp + {GMGR}]
      mov eax, [eax + 0x80]
      call {GETAB}
      test eax, eax
      jz nxt
      push eax
      mov edx, ebx
      mov ecx, [eax]
      call dword ptr [ecx + 0xc4]
      test al, al
      jz nxtpop
      mov eax, [esp]
      mov edx, ebx
      mov ecx, [eax]
      call dword ptr [ecx + 0xc8]
      pop edx
      cmp esi, eax
      mov eax, [esp]
      jb useun
      lea ecx, [ebp + {AF_VA}]
      movzx ecx, word ptr [ecx + eax*2]
      jmp gotw
    useun:
      lea ecx, [ebp + {UN_VA}]
      movzx ecx, word ptr [ecx + eax*2]
    gotw:
      mov edx, [esp]
      lea eax, [ebp + {ID_VA}]
      movzx edx, byte ptr [eax + edx]
      mov eax, edi
      call {ADDAB}
    nxt:
      inc dword ptr [esp]
      jmp lp
    nxtpop:
      pop eax
      jmp nxt
    done:
      add esp, 4
      pop ebp
      jmp {PICK}
    """
c1,_=ks.asm(elig_src(0x11111111,0x22222222,0x33333333),CAVE_ELIG); ELEN=len(c1)
TABLE_ID=CAVE_ELIG+ELEN
TABLE_UN=(TABLE_ID+NENT+1)&~1
TABLE_AF=TABLE_UN+NENT*2
c2,_=ks.asm(elig_src(TABLE_ID,TABLE_UN,TABLE_AF),CAVE_ELIG); assert len(c2)==ELEN
elig=bytes(c2)
tid=bytes(IDS)
tun=b"".join(struct.pack('<H',w) for w in UNAFF)
taf=b"".join(struct.pack('<H',w) for w in AFF)

CAVE_APPLY=(TABLE_AF+len(taf)+3)&~3
gd2=CAVE_APPLY+52
apply_src=f"""
  cmp eax, 0
  je {STAT[0]}
  cmp eax, 1
  je {STAT[1]}
  cmp eax, 2
  je {STAT[2]}
  cmp eax, 3
  je {STAT[3]}
  cmp eax, 4
  je {STAT[4]}
  push ebp
  push eax
  call gd2
  gd2: pop ebp
  sub ebp, {gd2}
  mov eax, [ebp + {GMGR}]
  mov eax, [eax + 0x80]
  mov edx, [esp]
  call {GETAB}
  test eax, eax
  jz sv
  mov edx, ebx
  mov ecx, [eax]
  call dword ptr [ecx + 0xc8]
  cmp esi, eax
  jb sv
  mov edx, [esp]
  mov eax, ebx
  mov ecx, [eax]
  call dword ptr [ecx + 0x94]
  pop eax
  pop ebp
  jmp {DONE}
sv:
  pop eax
  pop ebp
  jmp {EXIT}
"""
ap,_=ks.asm(apply_src,CAVE_APPLY); apply=bytes(ap)
assert apply[gd2-CAVE_APPLY]==0x5d

for blob,base in [(elig,CAVE_ELIG),(tid,TABLE_ID),(tun,TABLE_UN),(taf,TABLE_AF),(apply,CAVE_APPLY)]:
    data[o(base):o(base)+len(blob)]=blob
END=CAVE_APPLY+len(apply)
assert END <= 0x5580FF00, "cave overflow: 0x%X"%END

for va,w in [(0x55787A67,100),(0x55787AB4,50),(0x55787ADC,50),(0x55787B04,100)]:
    assert data[o(va)]==0xb9; data[o(va)+1]=w
h1=0x55787B15; assert bytes(data[o(h1):o(h1)+3])==b'\x8b\x45\x00'
data[o(h1):o(h1)+5]=b'\xe9'+struct.pack('<i',(CAVE_ELIG-(h1+5))&0xffffffff)
h2=0x55787C60; assert bytes(data[o(h2):o(h2)+3])==b'\x83\xf8\x07'
data[o(h2):o(h2)+5]=b'\xe9'+struct.pack('<i',(CAVE_APPLY-(h2+5))&0xffffffff)
open(FILE,'wb').write(data)

print("Updated ability weights. end 0x%X (limit 0x5580FF00)"%END)
print("%-17s id   unaff  aff"%"ability")
for (i,n,u,a) in ABILS:
    print("%-17s 0x%02X  %4d  %4d"%(n,i,u,a))
