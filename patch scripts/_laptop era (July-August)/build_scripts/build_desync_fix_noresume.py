#!/usr/bin/env python3
"""LAN out-of-sync FIX #5 (AoWEPACK.dll): no destination auto-resume in MP.

Repro #9 (8/9, fixes #1+#2+#4 + diag v5): STILL OOS, same creator as #8 -
CRE3 = MoveArmy+0xF <- TSelectedArmy.ExecuteMove, on the army owner's local
machine, mid-token-stream.  Fix #4 (clear dest at join) held at the join but
CANNOT hold overall: TMoveArmyTE.InitializeMove+0x126 re-writes the army's
multi-turn destination [army+0x25..27] on EVERY move-token init (synced
state - a pre-join pump move re-seeded it on both machines).  The
machine-local part is the UI DESTINATION AUTO-RESUME: only the owner's
machine runs it, and its token displaced the network-delivered negotiate
token in the stream (repro #9: B ran its local mole token at position ~550
where A ran the negotiate token; A never received the mole token) -> same
tokens, different order -> one extra synced draw skew -> OOS.

TSelectedArmy.Update @0x55793628 auto-resume loop (armies of the current
player [map+0xA5]):
  dest-branch  @0x5579371C: [army+0x25]!=0xFF/0 -> GetField(dest) ->
               vcall+0x20 valid? -> vcall+8 (plot+issue)  <- THE RESUME
  path-branch  @0x55793776: UI path list nonempty -> vcall+8  <- click flow
Both repro #8 and #9 creations came from the dest-branch (dest seeded by
InitializeMove, path empty).  A human click plots the path and executes
via ExecuteMove directly; Update's dest-branch only fires when movement
resumes across turns/events.

FIX: hook the dest check @0x5579371C (7 bytes 8A4225 3CFF 7453 =
mov al,[edx+0x25]; cmp al,0xFF; je 0x55793776).  In network games
([map+0x239]==2), always take the "no destination" exit to the
path-branch @0x55793776.  Else replicate the original compare (resume
@0x55793723 = the test al,al second check).  Effect in MP: multi-turn
move orders no longer auto-continue - re-click the destination each turn;
armies never move un-clicked.  SP/hotseat untouched.

Companions staying applied: #1 noanim @0x55812000, #2 aiowner
@0x55812100, #4 joindest @0x55812200 (kept: harmless + still right at the
join).  This cave @0x55812280-0x55812300.  Reloc scan built in; PIC delta
for the AoWHSMap absolute.  Backup AoWEPACK.dll.bak_noresume.
Dry-run; --apply / --revert.
"""
import os
import shutil
import struct
import sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
TARGET = os.path.join(GAME, "AoWEPACK.dll")
BACKUP = TARGET + ".bak_noresume"

VA2FILE = 0x55700C00
AOWHSMAP = 0x558FA040

CAVE_BASE  = 0x55812280
CAVE_LIMIT = 0x55812300

H_DEST = 0x5579371C
DEST_OLD = bytes.fromhex("8A42253CFF7453")   # mov al,[edx+25h]; cmp al,0FFh; je +53
DEST_RESUME = 0x55793723                      # test al,al; je nodest; ...
NODEST_TARGET = 0x55793776                    # the path-branch ("no destination")


class Asm:
    def __init__(self, base):
        self.base = base; self.buf = bytearray(); self.labels = {}
        self.fix32 = []; self.fix8 = []
    def here(self): return self.base + len(self.buf)
    def label(self, n): self.labels[n] = self.here()
    def db(self, *b): self.buf += bytes(b)
    def dd(self, v): self.buf += (v & 0xFFFFFFFF).to_bytes(4, 'little')
    def call(self, t): self.db(0xE8); self._r(t)
    def jmp32(self, t): self.db(0xE9); self._r(t)
    def je32(self, t): self.db(0x0F, 0x84); self._r(t)
    def _r(self, t):
        if isinstance(t, str):
            self.fix32.append((len(self.buf), t)); self.buf += b'\0\0\0\0'
        else:
            self.buf += (t - (self.here() + 4)).to_bytes(4, 'little', signed=True)
    def j8(self, opcode, label):
        self.db(opcode); self.fix8.append((len(self.buf), label)); self.db(0x00)
    def pic_delta_ecx(self):
        self.call(self.here() + 5)
        popva = self.here()
        self.db(0x59)
        self.db(0x81, 0xE9); self.dd(popva)
    def resolve(self):
        for off, lab in self.fix32:
            self.buf[off:off+4] = (self.labels[lab] - (self.base + off + 4)).to_bytes(4, 'little', signed=True)
        for off, lab in self.fix8:
            rel = self.labels[lab] - (self.base + off + 1)
            assert -128 <= rel <= 127, "rel8 %s %d" % (lab, rel)
            self.buf[off] = rel & 0xFF


def build_cave():
    a = Asm(CAVE_BASE)

    # entry: edx = army (must be preserved); eax free (al being loaded)
    a.label('cave_dest')
    a.db(0x51)                          # push ecx
    a.db(0x52)                          # push edx
    a.pic_delta_ecx()                   # ecx = load delta (edx untouched)
    a.db(0x8B, 0x91); a.dd(AOWHSMAP)    # mov edx,[ecx+AoWHSMap]
    a.db(0x85, 0xD2)
    a.j8(0x74, 'vanilla')               # no map -> vanilla behavior
    a.db(0x80, 0xBA); a.dd(0x239); a.db(0x02)  # cmp byte [edx+0x239], 2
    a.j8(0x75, 'vanilla')               # not a network game -> vanilla
    a.db(0x5A)                          # pop edx
    a.db(0x59)                          # pop ecx
    a.db(0xB0, 0xFF)                    # mov al, 0xFF (pretend "no dest")
    a.jmp32(NODEST_TARGET)              # -> path-branch, no auto-resume
    a.label('vanilla')
    a.db(0x5A)                          # pop edx
    a.db(0x59)                          # pop ecx
    a.db(0x8A, 0x42, 0x25)              # displaced: mov al,[edx+0x25]
    a.db(0x3C, 0xFF)                    #            cmp al, 0xFF
    a.je32(NODEST_TARGET)               #            je (re-encoded near)
    a.jmp32(DEST_RESUME)

    a.resolve()
    assert CAVE_BASE + len(a.buf) <= CAVE_LIMIT, "cave overflow %d" % len(a.buf)
    return bytes(a.buf) + bytes(CAVE_LIMIT - CAVE_BASE - len(a.buf)), a.labels


def reloc_check(data, ranges):
    e_lfanew = struct.unpack_from('<I', data, 0x3C)[0]
    opt = e_lfanew + 24
    nsec = struct.unpack_from('<H', data, e_lfanew + 6)[0]
    opt_size = struct.unpack_from('<H', data, e_lfanew + 20)[0]
    reloc_rva, reloc_sz = struct.unpack_from('<II', data, opt + 96 + 5*8)
    secs = []
    p = opt + opt_size
    for _ in range(nsec):
        vsz, va, rsz, raw = struct.unpack_from('<IIII', data, p + 8)
        secs.append((va, vsz, raw, rsz)); p += 40
    def rva2off(rva):
        for va, vsz, raw, rsz in secs:
            if va <= rva < va + max(vsz, rsz):
                return raw + rva - va
    off = rva2off(reloc_rva); end = off + reloc_sz
    hits = []
    while off < end:
        page_rva, blksz = struct.unpack_from('<II', data, off)
        for i in range((blksz - 8) // 2):
            w = struct.unpack_from('<H', data, off + 8 + i*2)[0]
            typ, ofs = w >> 12, w & 0xFFF
            if typ == 0:
                continue
            foff = rva2off(page_rva + ofs)
            if foff is None:
                continue
            for lo, hi in ranges:
                if lo <= foff + 3 and foff < hi:
                    hits.append((typ, foff))
        off += blksz
    return hits


def main():
    apply = "--apply" in sys.argv
    revert = "--revert" in sys.argv
    data = bytearray(open(TARGET, "rb").read())
    cave, labels = build_cave()
    ok, dirty = True, False
    print("cave: %d bytes @0x%X (file 0x%X)" %
          (len(cave.rstrip(b'\0')), CAVE_BASE, CAVE_BASE - VA2FILE))

    h_off = H_DEST - VA2FILE
    c_off = CAVE_BASE - VA2FILE
    hits = reloc_check(data, [(h_off, h_off + len(DEST_OLD)),
                              (c_off, c_off + len(cave))])
    if hits:
        print("ABORT: reloc fixups intersect patch ranges: %s" % hits); return 1
    print("  reloc scan    clean")

    cur = bytes(data[c_off:c_off + len(cave)])
    cave_new = bytes(len(cave)) if revert else cave
    if cur == cave_new:
        print("  %-14s already %s" % ("cave", "clear" if revert else "applied"))
    elif cur == bytes(len(cave)) or cur[:1] == b'\x51':
        data[c_off:c_off + len(cave_new)] = cave_new; dirty = True
        print("  %-14s %s" % ("cave", "clearing" if revert else "ready"))
    else:
        print("  %-14s MISMATCH %s" % ("cave", cur[:8].hex())); ok = False

    new = DEST_OLD if revert else (
        bytes([0xE9]) + (labels['cave_dest'] - (H_DEST + 5)).to_bytes(4, 'little', signed=True)
        + b'\x90' * (len(DEST_OLD) - 5))
    cur = bytes(data[h_off:h_off + len(DEST_OLD)])
    if cur == new:
        print("  %-14s already applied" % "dest-check")
    elif cur == DEST_OLD or cur[0] == 0xE9:
        data[h_off:h_off + len(new)] = new; dirty = True
        print("  %-14s ready @0x%X (%d bytes)" % ("dest-check", H_DEST, len(new)))
    else:
        print("  %-14s MISMATCH @0x%X: %s" % ("dest-check", H_DEST, cur.hex())); ok = False

    if not ok:
        print("ABORT: unexpected bytes, nothing written."); return 1
    if not dirty:
        print("Nothing to do."); return 0
    if not apply and not revert:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if not os.path.exists(BACKUP):
        shutil.copy2(TARGET, BACKUP); print("Backup -> %s" % os.path.basename(BACKUP))
    open(TARGET, "wb").write(data)
    print("Written %s" % TARGET)
    return 0


if __name__ == "__main__":
    sys.exit(main())
