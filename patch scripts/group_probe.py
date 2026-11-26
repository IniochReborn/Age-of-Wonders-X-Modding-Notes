#!/usr/bin/env python3
"""Read-only: dump the current tactical group selection (box-select) from the running game: each unit's
origin, hover destination (path node 0), stored path (dest-first), and replay the ordering rule of
patch_group_move_repath_v1 in Python (in-way count via cube distance, ties by path length)."""
import sys, struct
sys.argv=['x']; sys.path.insert(0,'.')
import ai_state_probe as P
pid,mods=P.find_game(); tc=mods['aowtcpck.dll']; mem=P.Mem(pid)
cmap=mem.u32(P.G_COMBATMAP+tc-P.BASE)
if not cmap: sys.exit("no combat map")
sel=mem.u32(cmap+0x100); wrap=mem.u32(sel+8); lst=mem.u32(wrap+8)
items=mem.u32(lst+4); n=mem.u32(lst+8)
print(f"combat map {cmap:#x} selection ctl {sel:#x} settings-list wrapper {wrap:#x} TList {lst:#x} count {n}")
def cube(x,y): r=y-(x-(x&1))//2; return (x,r,-x-r)
def dist(a,b): c1,c2=cube(*a),cube(*b); return max(abs(c1[i]-c2[i]) for i in range(3))
units=[]
for i in range(n):
    ms=mem.u32(items+4*i); hs=mem.u32(ms+0x10); ho=mem.u32(hs+4); cu=mem.u32(hs+0x1C)
    org=(mem.u8(ho+0x10),mem.u8(ho+0x11))
    path=mem.u32(ms+8); pc=mem.u32(path+8); pi=mem.u32(path+4)
    nodes=[]
    for k in range(pc):
        v=mem.u32(pi+4*k); nodes.append((v&0xFF,(v>>8)&0xFF,(v>>24)&0xFF))
    unit=mem.u32(cu+0x4C) if cu else 0; res=mem.u32(unit+0x40) if unit else 0
    name=mem.ansistr(mem.u32(res+0x24)) if res else (mem.classname(unit) if unit else '?')
    units.append(dict(i=i,name=name,org=org,dest=(nodes[0][0],nodes[0][1]) if nodes else None,nodes=nodes,mp=mem.i32(ms+0x14),reach=mem.i32(ms+0x24)))
for u in units:
    print(f"  [{u['i']}] {u['name']:12} origin {u['org']} dest {u['dest']} len {len(u['nodes'])} mp {u['mp']} path(dest-first) {[(x,y) for x,y,c in u['nodes']]} costs {[c for x,y,c in u['nodes']]}")
print("\n--- ordering rule replay (in-way count, then length) ---")
taken=set(); order=[]
while len(order)<n:
    best=None
    for u in units:
        if u['i'] in taken: continue
        L=len(u['nodes']) if u['nodes'] else 0xFFF
        if not u['dest']: key=0x7FFFFFFE; inway=None
        else:
            D=dist(u['org'],u['dest']); inway=[]
            for v in units:
                if v['i']==u['i'] or v['i'] in taken: continue
                if dist(u['org'],v['org'])+dist(v['org'],u['dest'])==D: inway.append(v['i'])
            key=(len(inway)<<12)|min(L,0xFFF)
        if best is None or key<best[0]: best=(key,u['i'],inway,D if u['dest'] else None)
    order.append(best[1]); taken.add(best[1])
    u=units[best[1]]
    print(f"  pick [{best[1]}] {u['name']:12} org {u['org']} -> {u['dest']} D={best[3]} in-way {best[2]} key {best[0]:#x}")
