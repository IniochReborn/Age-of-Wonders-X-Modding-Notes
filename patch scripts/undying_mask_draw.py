import math
from PIL import Image, ImageDraw
TW,TH=320,280; cx,cy=160,146; A=102; YS=1.55
def P(t):
    s=math.sin(t); c=math.cos(t); d=1+s*s
    return cx + A*c/d, cy + YS*A*s*c/d
N=900; t0=math.radians(150)                        # head on the left lobe's upper side
pts=[P(t0+2*math.pi*0.94*i/N) for i in range(N+1)]
def wid(i):                                         # body half-width: 13 px, tapering to 3 over the last 30 %
    u=i/N; return 12.5 if u<0.65 else 12.5-8.5*((u-0.65)/0.35)**1.2
im=Image.new("L",(TW,TH),0); d=ImageDraw.Draw(im)
def stroke(i0,i1,extra=0,fill=255):
    for i in range(i0,i1):
        x,y=pts[i]; r=wid(i)+extra; d.ellipse([x-r,y-r,x+r,y+r],fill=fill)
stroke(0,N)
# crossing: find the second pass through the centre and redraw it OVER with a dark gap
ci=[i for i in range(N) if abs(pts[i][0]-cx)<3 and abs(pts[i][1]-cy)<3]
k=ci[-1]; L=40
for i in range(k-L,k+L):
    x,y=pts[i]; r=wid(i)+6
    if (x-cx)**2+(y-cy)**2 < 38**2: d.ellipse([x-r,y-r,x+r,y+r],fill=0)
stroke(k-L-6,k+L+6)
# head: diamond pointing back along -tangent at the start, wider than the body
x0,y0=pts[0]; x1,y1=pts[6]; ux,uy=x0-x1,y0-y1; n=math.hypot(ux,uy); ux,uy=ux/n,uy/n; px,py=-uy,ux
hx,hy=x0+ux*16.2,y0+uy*16.2
head=[(hx-ux*21.6+px*13.5,hy-uy*21.6+py*13.5),(hx-ux*2.7+px*25.7,hy-uy*2.7+py*25.7),(hx+ux*27.0+px*12.2,hy+uy*27.0+py*12.2),(hx+ux*40.5,hy+uy*40.5),(hx+ux*27.0-px*12.2,hy+uy*27.0-py*12.2),(hx-ux*2.7-px*25.7,hy-uy*2.7-py*25.7),(hx-ux*21.6-px*13.5,hy-uy*21.6-py*13.5)]
d.polygon([(x+ux*0.0,y) for x,y in head],fill=255)
ex,ey=hx+ux*8.1+px*10.8,hy+uy*8.1+py*10.8; d.ellipse([ex-6,ey-6,ex+6,ey+6],fill=0)          # eye
ex,ey=hx+ux*8.1-px*10.8,hy+uy*8.1-py*10.8; d.ellipse([ex-6,ey-6,ex+6,ey+6],fill=0)
tx,ty=hx+ux*40.5,hy+uy*40.5; ttx,tty=tx+ux*18.9,ty+uy*18.9
d.line([(tx,ty),(ttx,tty)],fill=255,width=5)                                        # forked tongue
for s_ in (1,-1): d.line([(ttx,tty),(ttx+ux*12.2+px*9.5*s_,tty+uy*12.2+py*9.5*s_)],fill=255,width=5)
im.save(r"C:\Users\<user>\Desktop\Age of Wonders X - Claude\patch scripts\undying_user_mask.png")
