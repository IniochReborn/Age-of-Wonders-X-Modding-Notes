import struct, sys, os, glob, collections
TYPES={0:"Empty",1:"Picture08",2:"RLESprite08",3:"Sprite08",16:"Picture16",17:"RLESprite16",18:"TransparentRLESprite16",19:"BitMask",20:"Shadow",21:"TransparentPicture16",22:"Sprite16"}
def parse(path):
    d=open(path,'rb').read(); o=0
    def u32():
        nonlocal o; v=struct.unpack_from('<I',d,o)[0]; o+=4; return v
    def u8():
        nonlocal o; v=d[o]; o+=1; return v
    st={'types':collections.Counter(),'info':collections.Counter(),'unkA':collections.Counter(),
        'pixfmt':collections.Counter(),'clipx':collections.Counter(),'comp':0,'recs':0,'imgs':0,'unkB':collections.Counter()}
    magic=u32()
    if magic!=0x424C4904: raise ValueError("not ILB")
    someid=u32(); ver=struct.unpack_from('<f',d,o)[0]; o+=4; hlen=u32()
    st['ver']=ver; st['someId']=someid
    npal=0
    if hlen==24:
        imgdir=u32(); flen=u32(); npal=u32()
        st['sizeok'] = (flen==len(d))
        for i in range(npal):
            pid=u32()
            if pid!=0x88801B18: raise ValueError("bad palette id %08X"%pid)
            o+=1024
    elif hlen==16:
        u32(); st['sizeok']=None; imgdir=None
    else: raise ValueError("hdrLen %d"%hlen)
    st['npal']=npal
    while True:
        iid=u32()
        if iid==0xFFFFFFFF: break
        st['imgs']+=1
        comp=False; t=u32()
        if t==0x100: comp=True; st['comp']+=1; t=u32()
        while True:
            if t==0:
                if comp: comp=False; break          # end-of-composite: NO extra dword
                u32(); st['types']['Empty']+=1; comp=None; break  # standalone empty: filler, NO terminator
            info=u8(); nl=u32(); o+=nl
            w=u32(); h=u32(); xs=u32(); ys=u32(); sub=u32(); ua=u8(); size=u32()
            off = u32() if info!=1 else None
            tw=u32(); th=u32()
            if t in (1,2,3):
                st['unkB'][u8()]+=1
                if info==3: u32(); u32()
                if info!=1: u32()
            else:
                if info==3: u32(); u32()
                st['pixfmt'][hex(u32())]+=1
            if t in (2,3,17,18,22):
                u32(); u32(); u32(); u32(); u32()
            if t in (2,17,18): st['clipx'][hex(u32())]+=1
            if info==1: o+=size
            st['types'][TYPES.get(t,"T%d"%t)]+=1; st['info'][info]+=1; st['unkA'][ua]+=1; st['recs']+=1
            if comp: t=u32(); continue
            break
        if comp is None:
            pass
        elif not comp:
            end=u32()
            if end!=0xFFFFFFFF: raise ValueError("bad terminator %08X after id %d @%d"%(end,iid,o))
    st['dirend']=o
    if hlen==24 and imgdir is not None and o!=imgdir: st['dirmismatch']=(o,imgdir)
    return st
root=sys.argv[1]
files=[]
for sub in ("Images","Int"):
    files += glob.glob(os.path.join(root,sub,"**","*.ilb"), recursive=True)
    files += glob.glob(os.path.join(root,sub,"**","*.ILB"), recursive=True)
files=sorted(set(os.path.normpath(f) for f in files))
tot=collections.Counter(); info=collections.Counter(); unkA=collections.Counter(); pix=collections.Counter()
clipx=collections.Counter(); vers=collections.Counter(); pals=collections.Counter(); unkB=collections.Counter()
ok=0; bad=[]; comps=0; imgs=0; recs=0; mism=0
for f in files:
    try:
        s=parse(f); ok+=1
        tot+=s['types']; info+=s['info']; unkA+=s['unkA']; pix+=s['pixfmt']; clipx+=s['clipx']; unkB+=s['unkB']
        vers[s['ver']]+=1; pals[s['npal']]+=1; comps+=s['comp']; imgs+=s['imgs']; recs+=s['recs']
        if 'dirmismatch' in s: mism+=1
    except Exception as e: bad.append((os.path.basename(f),str(e)[:70]))
print("files parsed OK: %d / %d" % (ok,len(files)))
print("images: %d   records(incl. sub): %d   composite images: %d   imgDir-offset mismatches: %d" % (imgs,recs,comps,mism))
print("versions:", dict(vers), " palettes-per-file:", dict(pals))
print("image types:", dict(tot))
print("InfoByte:", dict(info), " unknownA:", dict(unkA), " unknownB:", dict(unkB))
print("pixelFormat:", dict(pix))
print("clip_x values:", dict(clipx.most_common(12)))
if bad:
    print("FAILURES (%d):" % len(bad))
    for b in bad[:15]: print("  ", b)

