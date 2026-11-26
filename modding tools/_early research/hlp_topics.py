import struct, os, re

FN = r"C:\Users\<user>\Desktop\Age of Wonders X - Claude\old modding tools\AoWCGE\AOWCGE.HLP"
OUT = os.path.dirname(os.path.abspath(__file__))
d = open(FN, "rb").read()

def internal_file(off):
    rs, us, flags = struct.unpack_from("<iiB", d, off)
    return d[off+9:off+9+us]

files = {'|PhrImage':0x10,'|PhrIndex':0x9C4,'|SYSTEM':0xAB9,'|TOPIC':0xB2A,'|FONT':0x3596,
         '|CTXOMAP':0x3674,'|KWDATA':0x367F,'|KWMAP':0x37D0,'|KWBTREE':0x37E1,
         '|AWDATA':0x3C10,'|AWBTREE':0x3C25,'|TTLBTREE':0x4054,'|CONTEXT':0x4883}

# --- titles from TTLBTREE ---
tt = internal_file(files['|TTLBTREE'])
pagesize, = struct.unpack_from("<H", tt, 4)
totalpages, = struct.unpack_from("<h", tt, 30)
titles = []
for p in range(totalpages):
    po = 38 + p*pagesize
    unused, nent, prevp, nextp = struct.unpack_from("<hhhh", tt, po)
    q = po + 8
    for i in range(nent):
        toff, = struct.unpack_from("<i", tt, q); q += 4
        e = tt.index(b"\0", q)
        titles.append((toff, tt[q:e].decode('latin-1')))
        q = e + 1
print("TITLES (%d):" % len(titles))
for toff, t in titles:
    print("  %08X  %s" % (toff, t))

# --- phrases (Hall) ---
ph = internal_file(files['|PhrIndex'])
magic, entries, compressedsize, phrimagesize, phrimagecompsize, always0 = struct.unpack_from("<iiiiii", ph, 0)
bitfield, unk = struct.unpack_from("<HH", ph, 24)
bits = bitfield & 0x0F
print("PhrIndex: entries=%d bits=%d imgsize=%d imgcomp=%d" % (entries, bits, phrimagesize, phrimagecompsize))

class BitReader:
    def __init__(self, b): self.b = b; self.pos = 0; self.mask = 0; self.val = 0
    def bit(self):
        if self.mask == 0:
            self.val = self.b[self.pos]; self.pos += 1; self.mask = 1
        r = 1 if (self.val & self.mask) else 0
        self.mask = (self.mask << 1) & 0xFF
        return r

br = BitReader(ph[28:])
lengths = []
for _ in range(entries):
    n = 1
    while br.bit(): n += 1 << bits
    for k in range(bits):
        if br.bit(): n += 1 << k
    lengths.append(n)

def zeck_decompress(src):
    out = bytearray(); i = 0
    while i < len(src):
        ctrl = src[i]; i += 1
        for bit in range(8):
            if i >= len(src): break
            if ctrl & (1 << bit):
                w, = struct.unpack_from("<H", src, i); i += 2
                length = ((w >> 12) & 0xF) + 3
                dist = (w & 0xFFF) + 1
                for _ in range(length): out.append(out[-dist] if dist <= len(out) else 0x20)
            else:
                out.append(src[i]); i += 1
    return bytes(out)

img = internal_file(files['|PhrImage'])
if phrimagesize != phrimagecompsize:
    img = zeck_decompress(img)
print("PhrImage decompressed: %d (expect %d)" % (len(img), phrimagesize))
phrases = []
o = 0
for L in lengths:
    phrases.append(img[o:o+L]); o += L
print("sample phrases:", phrases[:15])

def hall_expand(b):
    out = bytearray(); i = 0
    while i < len(b):
        c = b[i]; i += 1
        if (c & 1) == 0:
            idx = c >> 1
            out += phrases[idx] if idx < len(phrases) else b"<P?%d>" % idx
        elif (c & 3) == 1:
            if i >= len(b): break
            idx = 128 + ((c >> 2) << 8) + b[i]; i += 1
            out += phrases[idx] if idx < len(phrases) else b"<P?%d>" % idx
        elif (c & 7) == 3:
            n = (c >> 3) + 1
            out += b[i:i+n]; i += n
        elif (c & 0xF) == 7:
            out += b" " * ((c >> 4) + 1)
        else:  # 0x0F
            out += b"\0" * ((c >> 4) + 1)
    return bytes(out)

# --- topic ---
td = internal_file(files['|TOPIC'])
# strip 12-byte block headers per 4096 block
stream = bytearray()
for boff in range(0, len(td), 4096):
    stream += zeck_decompress(td[boff+12:boff+4096])
stream = bytes(stream)
print("decompressed topic stream: %d" % len(stream))
open(os.path.join(OUT, "topic_decomp.bin"), "wb").write(stream)

results = []
q = 0
while q + 21 <= len(stream):
    blocksize, datalen2, prevb, nextb, datalen1 = struct.unpack_from("<iiiii", stream, q)
    rectype = stream[q+20]
    if blocksize < 21 or blocksize > len(stream) - q or datalen1 < 21 or datalen1 > blocksize or rectype not in (2, 0x20, 0x23):
        q += 1
        continue
    ld1 = stream[q+21:q+datalen1]
    ld2c = stream[q+datalen1:q+blocksize]
    ld2 = ld2c[:datalen2] if len(ld2c) >= datalen2 else hall_expand(ld2c)
    results.append((q, rectype, ld1, ld2, datalen2))
    q += blocksize

print("topic links: %d" % len(results))
with open(os.path.join(OUT, "help_topics.txt"), "w", encoding="utf-8") as f:
    for q, rt, ld1, ld2, dl2 in results:
        f.write("\n===== link@%05X type=%02X dl2=%d (got %d)\n" % (q, rt, dl2, len(ld2)))
        txt = ld2.replace(b"\r", b"").decode('latin-1', 'replace')
        parts = [p for p in txt.split("\0") if p.strip()]
        for p in parts:
            f.write(p + "\n")
print("written help_topics.txt")
