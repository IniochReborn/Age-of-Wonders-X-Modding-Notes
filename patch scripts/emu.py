import struct, pefile
from unicorn import *
from unicorn.x86_const import *
G=r"C:\Users\<user>\Desktop\Age of Wonders X - Claude"
def load(mu, path, base):
    pe=pefile.PE(path)
    size=(pe.OPTIONAL_HEADER.SizeOfImage+0xFFF)&~0xFFF
    mu.mem_map(base,size)
    mu.mem_write(base, pe.__data__[:pe.OPTIONAL_HEADER.SizeOfHeaders])
    for s in pe.sections:
        raw=s.get_data()[:max(s.Misc_VirtualSize,0) or s.SizeOfRawData]
        mu.mem_write(base+s.VirtualAddress, s.get_data()[:min(len(s.get_data()), max(s.Misc_VirtualSize, s.SizeOfRawData))])
    return pe
def u32(mu,a): return struct.unpack("<I",mu.mem_read(a,4))[0]
def w32(mu,a,v): mu.mem_write(a,struct.pack("<I",v&0xFFFFFFFF))
ILGET=pefile.PE(G+r"\Ilpack.dpl"); o=ILGET.get_offset_from_rva(0x1a8b8); GETCODE=ILGET.__data__[o:o+0x25]
REGSTORE={}
def run(exe, epack, px_init, regval, count=94, nil_ids=()):
    mu=Uc(UC_ARCH_X86, UC_MODE_32)
    load(mu, exe, 0x400000)
    load(mu, epack, 0x55700000)
    mu.mem_map(0x10000000,0x100000)   # heap/stub area
    STK=0x10080000; HEAP=0x10000000
    # Get stub = real Ilpack code
    mu.mem_write(HEAP+0x1000, GETCODE); w32(mu,0x558fc1a0,HEAP+0x1000)
    # lib object
    lib=HEAP+0x2000; arr=HEAP+0x3000
    w32(mu,lib+0x44,count); w32(mu,lib+0x48,arr)
    for i in range(count):
        w32(mu,arr+i*8, 0 if i in nil_ids else 0x20000000+i); w32(mu,arr+i*8+4,0xFFFFFFFF)
    # engine/registry
    eng=HEAP+0x4000; reg=HEAP+0x4100
    w32(mu,HEAP+0x4200,eng); w32(mu,0x45df74,HEAP+0x4200); w32(mu,eng+0x5c,reg)
    # rwInteger stub: reads mode [esp+4], @v [esp+8]; read: if regval not None write it; write: record
    stub=HEAP+0x5000
    code=bytes.fromhex("8b442404"   # mov eax,[esp+4] mode
                       "8b4c2408"   # mov ecx,[esp+8] @v
                       "85c0" "7510"  # test/jnz write
                       "a1"+struct.pack("<I",HEAP+0x6000).hex()+   # mov eax,[flag]
                       "85c0" "7408"  # jz ret
                       "a1"+struct.pack("<I",HEAP+0x6004).hex()+"8901"  # mov eax,[val]; mov [ecx],eax
                       "c20800")
    # simpler: emulate via hook instead
    mu.mem_write(stub, b"\xC2\x08\x00")
    delta=(0x55703B28-0x55704424)&0xFFFFFFFF
    w32(mu,0x45DAE8,(stub-delta)&0xFFFFFFFF)
    calls=[]
    def hook(mu,addr,size,ud):
        esp=mu.reg_read(UC_X86_REG_ESP)
        mode=u32(mu,esp+4); pv=u32(mu,esp+8)
        calls.append((mode, mu.reg_read(UC_X86_REG_EAX)==reg,
                      bytes(mu.mem_read(mu.reg_read(UC_X86_REG_EDX),7)), bytes(mu.mem_read(mu.reg_read(UC_X86_REG_ECX),18)), u32(mu,pv)))
        if mode==0 and regval is not None: w32(mu,pv,regval)
    mu.hook_add(UC_HOOK_CODE, hook, begin=stub, end=stub)
    try: mu.mem_write(0x630004, bytes([px_init]))
    except UcError: pass
    # call the site: emulate the DrawGrid context: eax=lib, [esp]=pushed arg
    mu.mem_map(0x30000000,0x1000); mu.mem_write(0x30000000, b"\x50\xe8"+struct.pack("<i",0)+b"")
    # build: push eax ; call site(0x55772E7C) ; hlt
    tramp=0x30000000
    code=b"\x50"+b"\xE8"+struct.pack("<i",0x55772E7C-(tramp+6))+b"\x90"*1
    # after site the original continues at 0x55772E86 which uses ebp vcalls - stop at 0x55772E86
    mu.mem_write(tramp, code)
    mu.reg_write(UC_X86_REG_ESP, STK); mu.reg_write(UC_X86_REG_EAX, lib)
    for r,v in ((UC_X86_REG_EBX,0x1111),(UC_X86_REG_ESI,0x2222),(UC_X86_REG_EDI,0x3333),(UC_X86_REG_EBP,0x4444)):
        mu.reg_write(r,v)
    # place a return address so that the call at tramp+1 returns into 0x55772E81.. no: the site itself is a call to the cave
    mu.emu_start(tramp, 0x55772E86, count=2000)
    eax=mu.reg_read(UC_X86_REG_EAX); esp=mu.reg_read(UC_X86_REG_ESP)
    regs=[mu.reg_read(r) for r in (UC_X86_REG_EBX,UC_X86_REG_ESI,UC_X86_REG_EDI,UC_X86_REG_EBP)]
    return eax-0x20000000 if eax else None, esp==STK-8, regs==[0x1111,0x2222,0x3333,0x4444], (mu.mem_read(0x630004,1)[0] if px_init>=0 else -1), calls
import sys
X,E=sys.argv[1],sys.argv[2]
for px,rv,cnt,nil in ((3,None,94,()),(2,None,94,()),(1,None,94,()),(0,3,94,()),(0,1,94,()),(0,None,94,()),(0,7,94,()),(3,None,92,()),(2,None,94,(92,))):
    print("G_PX=%d reg=%s count=%d nil=%s ->"%(px,rv,cnt,nil), run(X,E,px,rv,cnt,nil))
print("unpatched host (AoWDevX-like, no .xhgr):", run(sys.argv[3], E, -1 & 0, None) if False else "")
