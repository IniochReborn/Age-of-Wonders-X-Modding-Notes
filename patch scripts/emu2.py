src=open("emu.py").read().split("ILGET=")[0]
exec(src)
X="t/X_applied.exe"
def setup(px):
    mu=Uc(UC_ARCH_X86, UC_MODE_32); load(mu,X,0x400000); mu.mem_map(0x10000000,0x100000)
    H=0x10000000; eng=H+0x4000; reg=H+0x4100
    w32(mu,H+0x4200,eng); w32(mu,0x45df74,H+0x4200); w32(mu,eng+0x5c,reg)
    stub=H+0x5000; mu.mem_write(stub,b"\xC2\x08\x00")
    w32(mu,0x45DAE8,(stub-((0x55703B28-0x55704424)&0xFFFFFFFF))&0xFFFFFFFF)
    mu.mem_write(0x40B758,b"\xC3")       # stub the vanilla DlgShow body
    form=H+0x7000; cb=H+0x8000; vmt=H+0x9000; setsel=H+0xA000
    w32(mu,0x45B07C,form); w32(mu,form+0xA4,cb); w32(mu,cb,vmt); w32(mu,vmt+0xB8,setsel); mu.mem_write(setsel,b"\xC3")
    mu.mem_write(0x630004,bytes([px]))
    log=[]
    mu.hook_add(UC_HOOK_CODE, lambda mu,a,s,u: log.append(("setsel",mu.reg_read(UC_X86_REG_EDX),mu.mem_read(0x630005,1)[0])), begin=setsel,end=setsel)
    def rw(mu,a,s,u):
        esp=mu.reg_read(UC_X86_REG_ESP); log.append(("rw mode",u32(mu,esp+4),"val",u32(mu,u32(mu,esp+8)),"self ok",mu.reg_read(UC_X86_REG_EAX)==reg))
        if u32(mu,esp+4)==0: w32(mu,u32(mu,esp+8),RV[0])
    mu.hook_add(UC_HOOK_CODE, rw, begin=stub,end=stub)
    mu.mem_map(0x30000000,0x1000); mu.reg_write(UC_X86_REG_ESP,0x10080000)
    return mu,form,cb,log
RV=[3]
import re
L={"show":0x630119,"change":0x630166}
for px in (0,1,2,3):
    RV[0]=3
    mu,form,cb,log=setup(px)
    mu.mem_write(0x30000000,b"\xE8"+struct.pack("<i",L["show"]-0x30000005)+b"\xF4")
    mu.reg_write(UC_X86_REG_EAX,form); mu.reg_write(UC_X86_REG_EDX,0x1234)
    mu.emu_start(0x30000000,0x30000005)
    print("show G_PX=%d:"%px, log, "eax/edx kept", mu.reg_read(UC_X86_REG_EAX)==form, mu.reg_read(UC_X86_REG_EDX)==0x1234, "G_PX now", mu.mem_read(0x630004,1)[0])
for sel in (0,1,2,-1,5):
    mu,form,cb,log=setup(2)
    w32(mu,cb+0x138,sel)
    mu.mem_write(0x30000000,b"\xE8"+struct.pack("<i",L["change"]-0x30000005)+b"\xF4")
    mu.reg_write(UC_X86_REG_EAX,form); mu.reg_write(UC_X86_REG_EDX,cb)
    mu.emu_start(0x30000000,0x30000005)
    print("change sel=%d:"%sel, log, "G_PX", mu.mem_read(0x630004,1)[0])
mu,form,cb,log=setup(2)
mu.mem_write(0x40B6EC,b"\xF4")
mu.mem_write(0x30000000,b"\xE8"+struct.pack("<i",L["change"]-0x30000005)+b"\xF4")
mu.reg_write(UC_X86_REG_EAX,form); mu.reg_write(UC_X86_REG_EDX,0x5555)
mu.emu_start(0x30000000,0x40B6EC)
print("change other sender -> reached original ResCBChange 0x40B6EC; eax/edx kept:", mu.reg_read(UC_X86_REG_EAX)==form, mu.reg_read(UC_X86_REG_EDX)==0x5555)
