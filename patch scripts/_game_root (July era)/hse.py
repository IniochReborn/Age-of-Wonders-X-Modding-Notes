
import struct, capstone, re
data=open(r"C:\Users\<user>\Desktop\Age of Wonders X - Claude\HSEPack.dpl","rb").read()
BASE=0x55600000
SECS=[('CODE',4096,182784,1024),('DATA',188416,1536,183808),('.idata',196608,25088,185344),('.edata',225280,51712,210432)]
def va2o(va):
    rva=va-BASE
    for n,r,sz,off in SECS:
        if r<=rva<r+sz: return off+rva-r
    return None
# exports
pe=struct.unpack_from('<I',data,0x3C)[0]; opt=pe+24
exp_rva=struct.unpack_from('<I',data,opt+96)[0]
def r2o(rva):
    for n,r,sz,off in SECS:
        if r<=rva<r+sz: return off+rva-r
e=r2o(exp_rva)
nnames=struct.unpack_from('<I',data,e+24)[0]
aof,aon,aoo=struct.unpack_from('<III',data,e+28)
NAMES={}
for i in range(nnames):
    nrva=struct.unpack_from('<I',data,r2o(aon)+i*4)[0]
    o=r2o(nrva); s=data[o:data.index(chr(0).encode(),o)].decode('latin1')
    ordn=struct.unpack_from('<H',data,r2o(aoo)+i*2)[0]
    NAMES[s]=BASE+struct.unpack_from('<I',data,r2o(aof)+ordn*4)[0]
REV={v:k for k,v in NAMES.items()}
md=capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
def dis(va, n=80, label=None):
    o=va2o(va)
    print("=== %s @ %s ==="%(label or REV.get(va,'?'),hex(va)))
    cnt=0
    for i in md.disasm(data[o:o+800], va):
        tgt=''
        if i.mnemonic=='call' and i.op_str.startswith('0x'):
            t=int(i.op_str,16); tgt='  ; '+REV.get(t, '')
        print("%s: %-8s %s%s"%(hex(i.address),i.mnemonic,i.op_str,tgt))
        cnt+=1
        if cnt>=n or i.mnemonic=='ret': break
def find(pat):
    for k,v in sorted(NAMES.items()):
        if re.search(pat,k,re.I): print(hex(v),k)
