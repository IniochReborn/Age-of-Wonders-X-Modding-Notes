from PIL import Image, ImageDraw, ImageFont, ImageFilter
import numpy as np
from collections import deque
B='../../backup/'
REF=__import__('os').path.join(__import__('os').path.dirname(__import__('os').path.abspath(__file__)),'sphere_icons','cosmos_star_ref.png')
yy,xx=np.mgrid[0:96,0:96]; R=np.hypot(yy-47.5,xx-47.5)
def lighten(o,center,r0=33.0):
    o=o.copy(); rng=np.random.default_rng(7)
    noise=rng.normal(0,4,(96,96,1))
    t=np.clip(R/r0,0,1)[...,None]
    rim=o[(R>=r0-1)&(R<r0+1)][:,:3].mean(0)
    grad=np.array(center,float)*(1-t**2.2)+rim*(t**2.2)+noise
    m=(R<r0)[...,None]
    o[...,:3]=np.where(m,grad,o[...,:3])
    return o
def star_mask():
    src=Image.open(REF).convert('RGBA'); bg=Image.new('RGBA',src.size,(255,255,255,255)); bg.alpha_composite(src)
    a=np.asarray(bg.convert('L'),float); h,w=a.shape; dark=a<128
    r=np.hypot(*np.mgrid[0:h,0:w]-np.array([h/2,w/2])[:,None,None])
    lab=np.zeros((h,w),int); comps=[]; n=0
    for y in range(h):
        for x in range(w):
            if dark[y,x] and not lab[y,x]:
                n+=1; q=deque([(y,x)]); lab[y,x]=n; cnt=0; mr=0
                while q:
                    p=q.popleft(); cnt+=1; mr=max(mr,r[p])
                    for dy,dx in((1,0),(-1,0),(0,1),(0,-1)):
                        Y,X=p[0]+dy,p[1]+dx
                        if 0<=Y<h and 0<=X<w and dark[Y,X] and not lab[Y,X]: lab[Y,X]=n; q.append((Y,X))
                comps.append((n,cnt,mr))
    ring=max(comps,key=lambda c:c[2])[0]
    star=max([c for c in comps if c[0]!=ring],key=lambda c:c[1])[0]
    m=lab==star
    grow=np.asarray(Image.fromarray((m*255).astype(np.uint8)).filter(ImageFilter.MaxFilter(3)))>0
    al=np.clip((210-a)/160,0,1)*grow
    ys,xs=np.nonzero(m)
    return Image.fromarray((al[ys.min():ys.max()+1,xs.min():xs.max()+1]*255).astype(np.uint8))
def chunky(mk, grow, blur):
    # vanilla look: bolder, rounded points, soft edge (work at 4x)
    big=mk.resize((mk.width*4,mk.height*4),Image.LANCZOS)
    big=big.filter(ImageFilter.MaxFilter(grow)).filter(ImageFilter.GaussianBlur(5))
    big=big.point(lambda v: 255 if v>110 else 0).filter(ImageFilter.GaussianBlur(3))
    return big.resize(mk.size,Image.LANCZOS).filter(ImageFilter.GaussianBlur(blur))
def glyph(base,mk,col=(0,0,0)):
    g=Image.new('RGBA',mk.size,col+(255,)); g.putalpha(mk)
    im=Image.fromarray(np.clip(base,0,255).astype(np.uint8),'RGBA'); im.alpha_composite(g,((96-mk.width)//2,(96-mk.height)//2)); return im
cos=lighten(np.asarray(Image.open(B+'cosmos.png.bak_sph').convert('RGBA'),float),(150,146,206))
sm=star_mask(); H=64; mk=sm.resize((round(H*sm.width/sm.height),H),Image.LANCZOS)
glyph(cos,chunky(mk,13,0.5),(22,18,44)).save('sphere_icons/cosmos.png')
sec=lighten(np.asarray(Image.open(B+'secret.png.bak_sph').convert('RGBA'),float),(196,195,206))
S=4; big=Image.new('L',(96*S,96*S),0); d=ImageDraw.Draw(big); f=None
for fn in ('ariblk.ttf','georgiab.ttf','arialbd.ttf'):
    try: f=ImageFont.truetype(fn,58*S); break
    except Exception: pass
bb=d.textbbox((0,0),'?',font=f); tw,th=bb[2]-bb[0],bb[3]-bb[1]
d.text(((96*S-tw)/2-bb[0],(96*S-th)/2-bb[1]),'?',font=f,fill=255)
glyph(sec,chunky(big.resize((96,96),Image.LANCZOS),5,0.5),(28,26,36)).save('sphere_icons/secret.png')
sh=Image.new('RGBA',(8*100,100),(230,220,200,255))
for i,n in enumerate(['air','cosmos','death','earth','fire','life','secret','water']): sh.alpha_composite(Image.open('sphere_icons/%s.png'%n),(i*100+2,2))
sh.save(r'C:/Users/<user>/AppData/Local/Temp/claude/C--Users-<user>-Desktop-Age-of-Wonders-X---Claude/68556280-d707-4a00-a5ee-7f75589fbb89/scratchpad/sph3.png')
