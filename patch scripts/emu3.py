exec(open("emu.py").read().split("ILGET=")[0])
X="t/S_applied.exe"
pe=pefile.PE(X); code=pe.sections[-1].get_data()
SEC=0x514000; i=code.find(b"\xFF\x25"+struct.pack("<I",SEC+0x110)); READREG=SEC+i+6
def mk():
    mu=Uc(UC_ARCH_X86,UC_MODE_32); load(mu,X,0x400000); mu.mem_map(0x10000000,0x100000)
    stubs={}
    def stub(iat,name,nargs,fn):
        a=0x10010000+len(stubs)*0x10; mu.mem_write(a,b"\xC2"+struct.pack("<H",nargs*4)); w32(mu,iat,a); stubs[a]=(name,nargs,fn)
    return mu,stub,stubs
def go(mu,stubs,start,stop,regs):
    log=[]
    def h(mu,a,s,u):
        if a in stubs:
            name,n,fn=stubs[a]; esp=mu.reg_read(UC_X86_REG_ESP); args=[u32(mu,esp+4+4*k) for k in range(n)]
            log.append((name,fn(mu,args)))
    mu.hook_add(UC_HOOK_CODE,h)
    mu.mem_map(0x30000000,0x1000); mu.mem_write(0x30000000,b"\xE8"+struct.pack("<i",start-0x30000005)+b"\xF4")
    mu.reg_write(UC_X86_REG_ESP,0x10080000)
    for r,v in regs.items(): mu.reg_write(r,v)
    mu.emu_start(0x30000000,stop)
    return log, mu.reg_read(UC_X86_REG_EAX)
for typ,val,rc in ((4,3,0),(4,2,0),(4,1,0),(4,0,0),(4,9,0),(1,0x31,0),(4,3,2)):
    mu,stub,stubs=mk()
    def q(mu,a):
        if rc==0: w32(mu,a[3],typ); w32(mu,a[4],val)
        mu.reg_write(UC_X86_REG_EAX,rc); return rc
    stub(0x46C200,"RegOpen",5,lambda mu,a:(w32(mu,a[4],0x77),mu.reg_write(UC_X86_REG_EAX,0))[1])
    stub(0x46C1FC,"RegQuery",6,q)
    stub(0x46C20C,"RegClose",1,lambda mu,a:mu.reg_write(UC_X86_REG_EAX,0))
    log,eax=go(mu,stubs,READREG,0x30000005,{})
    print("readreg type=%d val=%d rc=%d -> idx %d"%(typ,val,rc,eax))
for sel in (0,1,2,0xFFFFFFFF):
    mu,stub,stubs=mk()
    w32(mu,SEC+0xF0,0x12345)   # g_combo
    mu.mem_write(0x420714,b"\xB8\x99\x00\x00\x00\xC3")   # GetHandle -> 0x99
    stub(0x46C4C0,"SendMsg",4,lambda mu,a:(mu.reg_write(UC_X86_REG_EAX,sel),a)[1])
    stub(0x46C208,"RegCreate",9,lambda mu,a:(w32(mu,a[7],0x77),mu.reg_write(UC_X86_REG_EAX,0),bytes(mu.mem_read(a[1],50)).split(b"\0")[0])[2])
    stub(0x46C1F8,"RegSet",6,lambda mu,a:(bytes(mu.mem_read(a[1],18)),a[3],u32(mu,a[4]),a[5]))
    stub(0x46C20C,"RegClose",1,lambda mu,a:mu.reg_write(UC_X86_REG_EAX,0))
    tail=u32(mu,SEC+0x110)
    log,eax=go(mu,stubs,SEC+0x270,tail,{})
    print("ok sel=%d ->"%(sel if sel<10 else -1), log)
