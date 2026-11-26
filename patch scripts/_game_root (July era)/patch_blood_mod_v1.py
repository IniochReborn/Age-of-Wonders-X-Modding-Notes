#!/usr/bin/env python3
"""
Blue/Green Blood mod (v2 — VERBATIM from Bing Xi Lao's working Ziggurat binary)
================================================================================
Per-unit colour-dependent combat blood (blood-type byte 0=None,1=Red,2=Blue,3=Green,
set per unit in DevEd; read via vanilla [unittype+0x110]). Spurts + ground splatter +
corpse pools, all coloured. CONFIRMED WORKING IN-GAME 2026-07-21.

IMPORTANT — the reference `install_blood_mod.py` is a BUGGY/OUTDATED draft:
  * its show-call rels are 4 bytes off (call 0x438014/0x438028 = garbage -> crash),
  * its corpse hook is at the wrong address (0x4205A6 vs the real 0x4205C3),
  * it omits the corpse RENDER hook at 0x41BADE entirely.
The REAL working patches were extracted verbatim by diffing his live
`reference files/AoW Ziggurat/AoWTCPCK.dpl` against vanilla — that's what this applies.

Adapted for OUR setup:
  * patches AoWTCPCK.DLL (our live file; his is .dpl — same base/VA, va=file+0x400C00),
  * Release.hss combat ISL entries are CLONES of the red entries (only filename swapped)
    at his indices 33-39/47-49/51-54 (all NULL in ours; count 71 @our file 0x293F0D);
    his hardcoded ISL field values (esp f20) were tuned for his red graphics and crash
    HSEPack.ShowScene on ours, so we clone red instead.
Blood mechanism: caves add a colour offset to the blood graphic's ISL index; ground &
corpse encode the index in an object field the show/render hooks decode.
Reverts: AoWTCPCK.dll.bak_preblood, Release/Release.hss.bak_preblood.
Run:  python patch_blood_mod_v1.py --apply    (dry-run default)
"""
import sys, os, struct, binascii, colorsys

GAME = os.path.dirname(os.path.abspath(__file__))
DLL  = os.path.join(GAME, 'AoWTCPCK.dll')
BAK  = DLL + '.bak_preblood'
HSS  = os.path.join(GAME, 'Release', 'Release.hss')
OBJ  = os.path.join(GAME, 'Images', 'TCombat', 'Objects')

# ---- AoWTCPCK.dll patches: (VA, hexbytes) verbatim from his working binary ----
def _fo(va): return va - 0x400C00
DLL_PATCHES = [
 (0x40999D, 'e8fee50200'+'90'*27),                                   # bh_patch -> call bh_cave
 (0x437FA0, '8b45fc8b404c8b10ff921001000084c074093c02740d3c037411'  # bh_cave (blood-type -> +offset [obj+0xc])
            'c38b45f083400c05c38b45f083400c2ec38b45f083400c20c3'),
 (0x420256, 'e9857d01009090'),                                       # gnd_jmp -> gnd_cave
 (0x42021A, '89dac1ea08'),                                           # gnd_inl1: mov edx,ebx; shr edx,8
 (0x420232, '5a'),                                                   # gnd_inl2: [edx+0x10]=ebx (was eax)
 (0x430279, 'e89a7d0000'),                                           # show3a_call -> 0x438018  (CORRECT rel)
 (0x4302AF, 'e8787d000090'),                                         # show3b_call -> 0x43802C  (CORRECT rel)
 (0x4205B0, '10010000508b45fc8b404c8b10ff9278010000e9747a0100'+'90'*20),  # corpse inline+hook -> corpse_cave
 (0x41BADE, 'ff91f8000000'),                                         # corpse RENDER hook: call [ecx+0xf8]
 (0x437FE0, '538955f88945fc8b45fc8b404c8b10ff92100100003c02740b3c03740e'  # gnd_cave
            'bb00040000eb0cbb00240000eb05bb00330000e94882feff00'
            '00008b55fc8b5210c1ea0885d27505ba04000000c300'          # show3a cave
            '8b501081e2ff0000008b45ecc3000000'                       # show3b cave
            '5983e07f80f902741480f903741e83c01e83f8207e23b820000000eb1c'  # corpse_cave
            '83c03483f8367e14b836000000eb0d83c02583f8277e05b827000000'
            '8b55f0894224e96685feff'),
]

def patch_dll(apply):
    data = bytearray(open(DLL, 'rb').read())
    van  = open(BAK, 'rb').read() if os.path.exists(BAK) else None
    ok = True
    for va, hx in DLL_PATCHES:
        o = _fo(va); b = bytes.fromhex(hx)
        cur = bytes(data[o:o+len(b)])
        if cur == b:
            continue  # already applied
        # cave region must be zero; hook region must be vanilla
        is_cave = va in (0x437FA0, 0x437FE0)
        if is_cave and any(x != 0 for x in cur):
            print(f'  [!] cave @0x{va:X} not clear'); ok = False
        if not is_cave and van is not None and cur != van[o:o+len(b)]:
            print(f'  [!] hook @0x{va:X} not vanilla (got {cur.hex()})'); ok = False
    if not ok:
        print('  ABORT: dll verification failed'); return False
    if apply:
        for va, hx in DLL_PATCHES:
            o = _fo(va); b = bytes.fromhex(hx); data[o:o+len(b)] = b
        open(DLL, 'wb').write(data)
        print('  AoWTCPCK.dll: 10 blood patches applied (spurt+ground+corpse)')
    else:
        print('  DRY: caves clear / hooks vanilla -> ready')
    return True

# ---- ILB recolour (RGB565 hue shift) ----
def _565(p):
    r5=(p>>11)&0x1F; g6=(p>>5)&0x3F; b5=p&0x1F
    return (r5<<3)|(r5>>2),(g6<<2)|(g6>>4),(b5<<3)|(b5>>2)
def _to565(r,g,b): return (((r>>3)&0x1F)<<11)|(((g>>2)&0x3F)<<5)|((b>>3)&0x1F)
def _hue(p,dh,bg):
    if p==bg: return p
    r,g,b=_565(p); h,s,vv=colorsys.rgb_to_hsv(r/255,g/255,b/255)
    h=(h+dh/360.0)%1.0; r2,g2,b2=colorsys.hsv_to_rgb(h,s,vv)
    return _to565(int(r2*255),int(g2*255),int(b2*255))
def recolour_ilb(data, hue):
    pds=struct.unpack_from('<I',data,16)[0]; ents=[]; pos=0x20
    while pos<pds:
        if struct.unpack_from('<I',data,pos)[0]!=0x16: break
        nl=data[pos+5]; an=pos+9+nl
        ents.append((struct.unpack_from('<I',data,an+25)[0],struct.unpack_from('<I',data,an+21)[0],
                     struct.unpack_from('<H',data,an+0x41)[0])); pos+=86+nl
    pix=bytearray(data[pds:])
    for poff,psz,bg in ents:
        for i in range(psz//2):
            o=poff+i*2; struct.pack_into('<H',pix,o,_hue(struct.unpack_from('<H',pix,o)[0],hue,bg))
    return data[:pds]+bytes(pix)
ILB_PAIRS=[('BHSml1',),('BHMed1',),('BHBig1',),('GndBlood',),('BFSml1',),('BFMed1',),('BFBig1',)]
def _ci(d,n):
    for fn in os.listdir(d):
        if fn.lower()==n.lower(): return os.path.join(d,fn)
    return None
def generate_ilbs(apply):
    made=[]
    for (red,) in ILB_PAIRS:
        rp=_ci(OBJ,red+'.ILB')
        if not rp: raise FileNotFoundError(red+'.ILB')
        rd=open(rp,'rb').read()
        for suf,hue in (('_G',120.0),('_B',240.0)):
            if apply: open(os.path.join(OBJ,red+suf+'.ILB'),'wb').write(recolour_ilb(rd,hue))
            made.append(red+suf+'.ILB')
    return made

# ---- Release.hss: clone each red blood ISL entry to its green/blue slot ----
def _u32(d,o): return struct.unpack_from('<I',d,o)[0]
def patch_hss(apply):
    d=bytearray(open(HSS,'rb').read()); BS='\\'
    def walk(pos):
        isn=d[pos]; pos+=1
        if isn==1: return pos
        while True:
            sl=_u32(d,pos); pos+=4+sl; anim=d[pos+2]; pos+=3+12
            if anim in (4,5): fc=_u32(d,pos+4); pos+=8+4*fc
            hn=d[pos]; pos+=1
            if hn!=1: break
        return pos
    CO=0x293F0D
    if _u32(d,CO)!=71: print('  ERROR: combat ISL not count 71 @0x293F0D'); return False
    pos=CO+4; idx={}
    for i in range(71): idx[i]=pos; pos=walk(pos)
    def clone(ri,nm):
        red=bytes(d[idx[ri]:idx[ri+1]]); sl=struct.unpack_from('<I',red,1)[0]; rest=red[5+sl:]
        ns=(BS.join(['TCOMBAT','OBJECTS',nm])).encode()
        return b'\x00'+struct.pack('<I',len(ns))+ns+rest
    MAP=[(1,33,'BHSml1_G.ILB'),(2,34,'BHMed1_G.ILB'),(3,35,'BHBig1_G.ILB'),(4,51,'GndBlood_G.ILB'),
         (30,37,'BFSml1_G.ILB'),(31,38,'BFMed1_G.ILB'),(32,39,'BFBig1_G.ILB'),
         (1,47,'BHSml1_B.ILB'),(2,48,'BHMed1_B.ILB'),(3,49,'BHBig1_B.ILB'),(4,36,'GndBlood_B.ILB'),
         (30,52,'BFSml1_B.ILB'),(31,53,'BFMed1_B.ILB'),(32,54,'BFBig1_B.ILB')]
    add={t:clone(r,n) for r,t,n in MAP if d[idx[t]]==1}
    if not add:
        print('  ISL entries already present'); return True
    if not apply:
        print(f'  DRY: would clone {len(add)} entries at {sorted(add)}'); return True
    for t in sorted(add,reverse=True): d[idx[t]:idx[t]+1]=add[t]
    struct.pack_into('<I',d,len(d)-4,binascii.crc32(bytes(d[:-4]))&0xFFFFFFFF)
    open(HSS,'wb').write(d)
    print(f'  Release.hss: {len(add)} ISL clones spliced, CRC recalc, size {len(d)}')
    return True

def main():
    apply='--apply' in sys.argv
    print('Blood mod v2', '(APPLY)' if apply else '(dry-run)')
    print('1) AoWTCPCK.dll:');
    if not patch_dll(apply): sys.exit(1)
    print('2) ILBs:'); print(f'   {len(generate_ilbs(apply))} files')
    print('3) Release.hss:')
    if not patch_hss(apply): sys.exit(1)
    print('DONE.' if apply else 'DRY-RUN OK — rerun with --apply')

if __name__=='__main__': main()
