import struct, os, sys
from PIL import Image
TYPES={0:"Empty",1:"Picture08",2:"RLESprite08",3:"Sprite08",16:"Picture16",17:"RLESprite16",18:"TransparentRLESprite16",22:"Sprite16"}
def read_ilb(path):
    d=open(path,'rb').read(); o=0
    def u32():
        nonlocal o; v=struct.unpack_from('<I',d,o)[0]; o+=4; return v
    def u8():
        nonlocal o; v=d[o]; o+=1; return v
    assert u32()==0x424C4904
    u32(); ver=struct.unpack_from('<f',d,o)[0]; o+=4; hlen=u32()
    pals=[]; imgdir=None
    if hlen==24:
        imgdir=u32(); u32(); npal=u32()
        for _ in range(npal):
            assert u32()==0x88801B18
            p=[]
            for i in range(256):
                r,g,b,_x=d[o],d[o+1],d[o+2],d[o+3]; o+=4; p+= [r,g,b]
            pals.append(p)
    else: u32()
    imgs=[]
    while True:
        iid=u32()
        if iid==0xFFFFFFFF: break
        comp=False; t=u32()
        if t==0x100: comp=True; t=u32()
        parts=[]
        while True:
            if t==0:
                if comp: comp=False; break
                u32(); comp=None; break
            r={'id':iid,'type':t}
            r['info']=u8(); nl=u32(); r['name']=d[o:o+nl].decode('latin1'); o+=nl
            r['w'],r['h'],r['xs'],r['ys'],r['sub']=struct.unpack_from('<5I',d,o); o+=20
            r['unkA']=u8(); r['size']=u32()
            r['off']= u32() if r['info']!=1 else None
            u32(); u32()
            if t in (1,2,3):
                u8()
                if r['info']==3: u32(); u32()
                r['pal']= u32() if r['info']!=1 else 0
            else:
                if r['info']==3: r['draw']=u32(); r['blend']=u32()
                r['pixfmt']=u32()
            if t in (2,3,17,18,22):
                r['cw'],r['ch'],r['cx'],r['cy'],r['transp']=struct.unpack_from('<5I',d,o); o+=20
            else:
                r['cw'],r['ch'],r['cx'],r['cy'],r['transp']=r['w'],r['h'],0,0,None
            if t in (2,17,18): r['clip_x']=u32()
            if r['info']==1: r['inline']=o; o+=r['size']
            parts.append(r)
            if comp: t=u32(); continue
            break
        if comp is not None and not comp: u32()
        if parts: imgs.append(parts)
    return d, ver, imgdir, pals, imgs

def data_start(d, imgdir, r):
    return r['inline'] if r['info']==1 else imgdir + r['off']

def decode(d, imgdir, pals, r):
    t=r['type']; w,h=r['w'],r['h']; cw,ch,cx,cy=r['cw'],r['ch'],r['cx'],r['cy']
    p=data_start(d,imgdir,r); im=Image.new("RGBA",(w,h),(0,0,0,0)); px=im.load()
    def c565(v): return (((v>>11)&31)*255//31, ((v>>5)&63)*255//63, (v&31)*255//31)
    if t==2:   # RLE 8-bit indexed
        pal=pals[r['pal']]; back=r['transp']
        for y in range(cy, cy+ch):
            ln=struct.unpack_from('<I',d,p)[0]; p+=4; n=ln-4; x=cx; q=p
            while n>0:
                b=d[q]; q+=1; n-=1
                if b==back:
                    cnt=d[q]; q+=1; n-=1; x+=cnt
                else:
                    if 0<=x<w and 0<=y<h: px[x,y]=(pal[b*3],pal[b*3+1],pal[b*3+2],255)
                    x+=1
            p=q
    elif t in (17,18):   # RLE 16-bit
        back=r['transp']&0xFFFF
        for y in range(cy, cy+ch):
            ln=struct.unpack_from('<I',d,p)[0]; p+=4
            n=(ln-4)//2; x=cx; q=p; skip=(n%2)>0
            while n>0:
                v=struct.unpack_from('<H',d,q)[0]; q+=2; n-=1
                if v==back:
                    cnt=struct.unpack_from('<H',d,q)[0]; q+=2; n-=1; x+=cnt//2
                else:
                    if 0<=x<w and 0<=y<h: px[x,y]=c565(v)+(255,)
                    x+=1
            p=q+(2 if skip else 0)
    elif t in (16,22):   # raw 16-bit
        back=r['transp']
        for y in range(cy, cy+ch):
            for x in range(cx, cx+cw):
                v=struct.unpack_from('<H',d,p)[0]; p+=2
                if back is None or v!=(back&0xFFFF):
                    if 0<=x<w and 0<=y<h: px[x,y]=c565(v)+(255,)
    elif t==1:   # raw 8-bit
        pal=pals[r['pal']]
        for y in range(cy, cy+ch):
            for x in range(cx, cx+cw):
                b=d[p]; p+=1
                if 0<=x<w and 0<=y<h: px[x,y]=(pal[b*3],pal[b*3+1],pal[b*3+2],255)
    return im

out=sys.argv[2]
for path in sys.argv[1].split(";"):
    d,ver,imgdir,pals,imgs=read_ilb(path)
    base=os.path.splitext(os.path.basename(path))[0]
    print("%-16s v%.1f  images=%d palettes=%d" % (base,ver,len(imgs),len(pals)))
    made=0
    # composite sheet of first 12 non-empty images (flattened composites)
    tiles=[]
    for parts in imgs:
        if made>=12: break
        try:
            layers=[decode(d,imgdir,pals,r) for r in parts]
        except Exception as e:
            print("   decode fail id=%d: %s"%(parts[0]['id'],e)); continue
        W=max(l.width for l in layers); H=max(l.height for l in layers)
        flat=Image.new("RGBA",(W,H),(0,0,0,0))
        for r,l in zip(parts,layers): flat.alpha_composite(l,(r['xs'],r['ys']))
        tiles.append((parts[0],flat)); made+=1
    if not tiles: continue
    TW=max(t[1].width for t in tiles); TH=max(t[1].height for t in tiles)
    sheet=Image.new("RGBA",(TW*len(tiles), TH),(40,40,40,255))
    for i,(r,im) in enumerate(tiles): sheet.alpha_composite(im,(i*TW,0))
    fp=os.path.join(out, base+"_decoded.png"); sheet.save(fp)
    print("   -> %s  (%d tiles, %s, first type=%s)" % (os.path.basename(fp),len(tiles),sheet.size,TYPES.get(tiles[0][0]['type'])))
