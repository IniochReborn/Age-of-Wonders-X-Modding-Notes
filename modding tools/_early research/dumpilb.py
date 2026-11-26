import struct, sys, os
TYPES={0:"Empty",1:"Picture08",2:"RLESprite08",3:"Sprite08",16:"Picture16",17:"RLESprite16",18:"TransparentRLESprite16",19:"BitMask",20:"Shadow",21:"TransparentPicture16",22:"Sprite16"}
def dump(path, maxrec=4):
    d=open(path,'rb').read(); o=0
    def u32():
        nonlocal o; v=struct.unpack_from('<I',d,o)[0]; o+=4; return v
    def u8():
        nonlocal o; v=d[o]; o+=1; return v
    magic=u32(); someid=u32(); ver=struct.unpack_from('<f',d,o)[0]; o+=4; hlen=u32()
    print("%s  magic=%08X someId=%08X ver=%.1f hdrLen=%d size=%d" % (os.path.basename(path),magic,someid,ver,hlen,len(d)))
    npal=0
    if hlen==24:
        imgdir=u32(); flen=u32(); npal=u32()
        print("   imgDir=%d fileLen=%d (actual %d) palettes=%d" % (imgdir,flen,len(d),npal))
        for i in range(npal):
            pid=u32(); assert pid==0x88801B18, hex(pid); o+=1024
    else:
        print("   unknown/palette field=%08X" % u32())
    n=0; counts={}
    while True:
        iid=u32()
        if iid==0xFFFFFFFF: break
        comp=False; t=u32()
        if t==0x100: comp=True; t=u32()
        while True:
            if t==0:
                u32()
                if comp: comp=False; break
                break
            info=u8(); nl=u32(); name=d[o:o+nl].decode('latin1'); o+=nl
            w=u32(); h=u32(); xs=u32(); ys=u32(); sub=u32(); ua=u8(); size=u32()
            off = u32() if info!=1 else None
            tw=u32(); th=u32()
            extra={}
            if t in (1,2,3):
                extra['unkB']=u8()
                if info==3: extra['unkC']=u32(); extra['unkD']=u32()
                if info!=1: extra['pal']=u32()
            else:
                if info==3: extra['drawMode']=u32(); extra['blendVal']=u32()
                extra['pixFmt']=u32()
            if t in (2,3,17,18,22):
                extra['clipW']=u32(); extra['clipH']=u32(); extra['clipX']=u32(); extra['clipY']=u32(); extra['transp']=u32()
            if t in (2,17,18):
                extra['clip_x']=u32()
            if info==1: o+=size
            counts[TYPES.get(t,t)]=counts.get(TYPES.get(t,t),0)+1
            if n<maxrec:
                print("   #%d %-24s %-22s %dx%d shift(%d,%d) sub=%d info=%d unkA=%d size=%d off=%s %s" %
                      (iid,name,TYPES.get(t,t),w,h,xs,ys,sub,info,ua,size,off,
                       " ".join("%s=%s"%(k,(hex(v) if k in('pixFmt','transp','clip_x','drawMode') else v)) for k,v in extra.items())))
            n+=1
            if comp:
                t=u32(); continue
            break
        if not comp:
            end=u32()
            if end!=0xFFFFFFFF: print("   !! bad terminator %08X after #%d"%(end,iid)); return
    print("   records=%d  types=%s" % (n,counts))
    print("   parsed to offset %d of %d  -> %s" % (o,len(d), "OK (data follows)" if o<=len(d) else "OVERRUN"))
for p in sys.argv[1:]:
    try: dump(p)
    except Exception as e: print("  FAIL %s: %s" % (os.path.basename(p), e))
    print()
