#!/usr/bin/env python3
"""LAN out-of-sync FIX #6 (AoWEPACK.dll): no UI path auto-arming in MP
("noautoplot").

DIAG v7 repro #13 (NET ring) settled the transport question: the one-sided
recruited-army move WAS sent and WAS received (B p1 batch=3 SyncTE+move+
PassTokenTE at NET#777 == A prefetched p1 batch=3 at NET#778).  The OOS is
ORDER INVERSION: at identical RNG state (seed C9876796) machine A executed
the negotiate token + its (75,81,0) move while machine B executed the mole
move - same tokens, opposite order, draw counts split at the next TSyncTE
compare.  Stream positions are per-machine COUNTS that self-align only when
both machines interleave the same number of tokens; a UI move injected
during the recruit burst (Global AI tokens flowing) resolves differently on
each side.  Quiet-time clicks align trivially - normal play never desyncs.

The move itself is UNINTENDED: clicking the just-recruited army
confirm-executes its stale AI path because the UI AUTO-ARMS a path for the
selected army (TSelectedArmy.Update loop: dest-branch plots from the stored
destination [army+0x25..27]; path-branch replots a lingering path).
SelectPath (mouse) then matches clicked-hex == path[0] == the army's own
hex -> vcall ExecuteMove.  Fix #5 gated only the dest-branch; the
path-branch re-armed the stale path -> no effect (reverted).

FIX: hook the auto-plot block entry in TSelectedArmy.Update @0x557936D2
(10 bytes: test byte [ebx+0x14],1 ; je 0x557937C3).  In network games
([map+0x239]==2) skip the ENTIRE per-army auto-plot loop (jmp 0x557937C3).
Deliberate moves are untouched - the two-click flow plots and confirms via
MouseDownEvent -> SelectPath's own logic, not via Update.  Visual cost in
network games only: the path preview for a selected army with a stored
multi-turn destination no longer auto-appears (plot it by clicking).
SP/hotseat unchanged.

Companions staying applied: #1 noanim @0x55812000, #2 aiowner @0x55812100,
#4 joindest @0x55812200 (keeps the join-time dest clear).  Fixes #3/#5/#5b
stay reverted.  This cave @0x55812280-0x55812300 (clicklock's vacated
space).  PIC delta, reloc scan built in.  Backup AoWEPACK.dll.bak_noautoplot.
Dry-run; --apply / --revert.
"""
import os
import shutil
import struct
import sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
TARGET = os.path.join(GAME, "AoWEPACK.dll")
BACKUP = TARGET + ".bak_noautoplot"

VA2FILE = 0x55700C00
AOWHSMAP = 0x558FA040

CAVE_BASE  = 0x55812280
CAVE_LIMIT = 0x55812300

H_PLOT = 0x557936D2
PLOT_OLD = bytes.fromhex("F64314010F84E7000000")  # test [ebx+14h],1; je +0xE7
PLOT_EXIT = 0x557937C3                            # loop-skip target (both paths)
PLOT_RESUME = 0x557936DC                          # falls into the loop body


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

    # entry: ebx = TSelectedArmy self; no live flags
    a.label('cave_plot')
    a.db(0x50)                          # push eax
    a.db(0x51)                          # push ecx
    a.pic_delta_ecx()                   # ecx = load delta
    a.db(0x8B, 0x81); a.dd(AOWHSMAP)    # mov eax,[ecx+AoWHSMap]
    a.db(0x85, 0xC0)
    a.j8(0x74, 'vanilla')               # no map -> vanilla
    a.db(0x80, 0xB8); a.dd(0x239); a.db(0x02)  # cmp byte [eax+0x239], 2
    a.j8(0x75, 'vanilla')               # not network -> vanilla
    a.db(0x59)                          # pop ecx
    a.db(0x58)                          # pop eax
    a.jmp32(PLOT_EXIT)                  # MP: skip the whole auto-plot loop
    a.label('vanilla')
    a.db(0x59)                          # pop ecx
    a.db(0x58)                          # pop eax
    a.db(0xF6, 0x43, 0x14, 0x01)        # displaced: test byte [ebx+0x14], 1
    a.je32(PLOT_EXIT)                   #            je exit (re-encoded)
    a.jmp32(PLOT_RESUME)

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

    h_off = H_PLOT - VA2FILE
    c_off = CAVE_BASE - VA2FILE
    hits = reloc_check(data, [(h_off, h_off + len(PLOT_OLD)),
                              (c_off, c_off + len(cave))])
    if hits:
        print("ABORT: reloc fixups intersect patch ranges: %s" % hits); return 1
    print("  reloc scan    clean")

    cur = bytes(data[c_off:c_off + len(cave)])
    cave_new = bytes(len(cave)) if revert else cave
    if cur == cave_new:
        print("  %-14s already %s" % ("cave", "clear" if revert else "applied"))
    elif cur == bytes(len(cave)) or cur[:1] == b'\x50':
        data[c_off:c_off + len(cave_new)] = cave_new; dirty = True
        print("  %-14s %s" % ("cave", "clearing" if revert else "ready"))
    else:
        print("  %-14s MISMATCH %s" % ("cave", cur[:8].hex())); ok = False

    new = PLOT_OLD if revert else (
        bytes([0xE9]) + (labels['cave_plot'] - (H_PLOT + 5)).to_bytes(4, 'little', signed=True)
        + b'\x90' * (len(PLOT_OLD) - 5))
    cur = bytes(data[h_off:h_off + len(PLOT_OLD)])
    if cur == new:
        print("  %-14s already applied" % "autoplot")
    elif cur == PLOT_OLD or cur[0] == 0xE9:
        data[h_off:h_off + len(new)] = new; dirty = True
        print("  %-14s ready @0x%X (%d bytes)" % ("autoplot", H_PLOT, len(new)))
    else:
        print("  %-14s MISMATCH @0x%X: %s" % ("autoplot", H_PLOT, cur.hex())); ok = False

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
