import struct, glob, sys
import hsm_grid as H
src = glob.glob("../Scenario/Custom/*Cataclysm.hsm")[0]
g = H.load(src)
def rec(cls, rid):
    return H.build([(50, struct.pack("<I", cls - 1) + bytes([1, 1, 0]) + struct.pack("<I", rid))])
AW, AI = (0x2073E, 0x7b134f), (0x2073E, 0xaf9569)
PW, PI = (0x20153, 0x241c42b), (0x20153, 0xb278f3e)
CW, CI = (0x20153, 0x96db1b1), (0x20153, 0xb491dcf)
GR = (0x20153, 0x808840)
# blobs: each test = centre kind A, ring/right kind B
tests = [(AW, CW), (AW, CI), (AI, CI), (AI, CW), (PW, CW), (PI, CI), (CW, AW), (CI, AI)]
x0, y0 = int(sys.argv[1]), int(sys.argv[2]); r = int(sys.argv[3]); tests = tests[r:] + tests[:r]
for y in range(y0 - 2, y0 + 30):
    for x in range(x0 - 2, x0 + 40):
        g.recs[y * g.W + x] = rec(*GR)
for n, (a, b) in enumerate(tests):
    bx, by = x0 + (n % 4) * 9, y0 + (n // 4) * 12
    for y in range(by, by + 9):
        for x in range(bx, bx + 7):
            inner = 2 <= x - bx <= 4 and 3 <= y - by <= 5
            g.recs[y * g.W + x] = rec(*(b if inner else a))
open("../Scenario/Custom/_wtest.hsm", "wb").write(H.dumps(g))
print("ok", g.W)
