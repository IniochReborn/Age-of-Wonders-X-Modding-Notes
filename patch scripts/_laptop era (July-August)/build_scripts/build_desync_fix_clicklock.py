#!/usr/bin/env python3
"""LAN out-of-sync FIX #5b (AoWEPACK.dll): refuse UI moves while token
executer is locked ("clicklock").

DIAG v6 repro #11 completed the chain: CRE5 = TMoveSelector.SelectPath+0x73
-> ExecuteMove -> MoveArmy -> the one-sided (44,10,2) token, created
IMMEDIATELY AFTER the capture window opened (CAPT tok#488 -> CRE5).
SelectPath's dispatchers are ALL mouse handlers (TMoveSelector.
MouseDownEvent+0x64, TAoWHSMapMouse.Down+0x4A, TSelectedArmy.MouseDownEvent
+0x2E0): clicking the recruited army whose stale AI path is auto-plotted
(first path hex == army's own hex) confirm-executes the move.  The click
is legitimate vanilla UX - the desync is the TIMING: a token created for a
LOCAL owner while the token executer is locked (AI capture burst) races
the sync stream and executes one-sided; the peer's draw count differs at
the next TSyncTE compare -> OOS.  (Sync compares seed VALUE = f^n(seed0),
so only DRAW COUNTS matter - ordinary clicks while the stream is idle stay
consistent, which is why normal LAN play works.)

FIX: MoveArmyEx's existing busy-refusal (call TPlayer.GetBusy @0x5574A347,
result al!=0 -> refuse @0x5574A46D) runs only for callers WITHOUT the
busy-skip flag [ebp+8] - i.e. the UI paths (MoveArmy wrapper pushes 0).
Replace that 5-byte call with a cave call that:
  1. calls GetBusy (vanilla) - busy stays busy;
  2. if not busy, network game ([map+0x239]==2) AND token executer locked
     ([[[map+0x23C]+4]+0x4C] != 0) AND the army owner's comm status is
     LOCAL (0) -> report busy (al=1).
Global owners (AI pump - which runs INSIDE the lock) and skip-flag callers
(token-side forced moves) unaffected.  SP/hotseat unaffected (mode gate).
UI effect: a click during an AI burst does nothing for a few frames -
identical to clicking a busy army; the next click works.

Companions staying applied: #1 noanim @0x55812000, #2 aiowner @0x55812100,
#4 joindest @0x55812200.  Fixes #3/#5 stay reverted.  This cave
@0x55812280-0x55812300 (fix #5's vacated space).  PIC delta trick, reloc
scan built in.  Backup AoWEPACK.dll.bak_clicklock.
Dry-run; --apply / --revert.
"""
import os
import shutil
import struct
import sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
TARGET = os.path.join(GAME, "AoWEPACK.dll")
BACKUP = TARGET + ".bak_clicklock"

VA2FILE = 0x55700C00
AOWHSMAP = 0x558FA040

CAVE_BASE  = 0x55812280
CAVE_LIMIT = 0x55812300

GETBUSY = 0x557516D0
GETPLAYERS_THUNK = 0x557035DC

H_BUSY = 0x5574A347
BUSY_OLD = bytes.fromhex("E884730000")   # call TPlayer.GetBusy
# esi = armyHS at this site (set at entry, preserved through GetPlayers).


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

    # in: eax = player (GetBusy arg), esi = armyHS (callee-saved, read only)
    # out: al = busy result (vanilla | our lock gate); may clobber ecx/edx
    a.label('cave_busy')
    a.call(GETBUSY)                     # vanilla busy check
    a.db(0x84, 0xC0)                    # test al, al
    a.j8(0x75, 'done')                  # already busy -> keep al=1
    a.pic_delta_ecx()                   # ecx = load delta
    a.db(0x8B, 0x91); a.dd(AOWHSMAP)    # mov edx,[ecx+AoWHSMap]
    a.db(0x85, 0xD2)
    a.j8(0x74, 'allow')                 # no map -> allow
    a.db(0x80, 0xBA); a.dd(0x239); a.db(0x02)  # cmp byte [edx+0x239], 2
    a.j8(0x75, 'allow')                 # not network -> allow
    a.db(0x52)                          # push edx            ; save map
    a.db(0x8B, 0x92); a.dd(0x23C)       # mov edx,[edx+0x23C] ; tokman
    a.db(0x85, 0xD2)
    a.j8(0x74, 'allowp')
    a.db(0x8B, 0x52, 0x04)              # mov edx,[edx+4]     ; executer
    a.db(0x85, 0xD2)
    a.j8(0x74, 'allowp')
    a.db(0x83, 0x7A, 0x4C, 0x00)        # cmp dword [edx+0x4C], 0 ; lock
    a.db(0x5A)                          # pop edx             ; map (flags kept)
    a.j8(0x74, 'allow')                 # not locked -> allow
    a.db(0x8B, 0x46, 0x1C)              # mov eax,[esi+0x1C]  ; army
    a.db(0x85, 0xC0)
    a.j8(0x74, 'allow')
    a.db(0x0F, 0xBE, 0x48, 0x12)        # movsx ecx, byte [eax+0x12] ; owner
    a.db(0x8B, 0x82); a.dd(0x240)       # mov eax,[edx+0x240] ; holder
    a.db(0x85, 0xC0)
    a.j8(0x74, 'allow')
    a.db(0x8B, 0x40, 0x1C)              # mov eax,[eax+0x1C]  ; pcc
    a.db(0x85, 0xC0)
    a.j8(0x74, 'allow')
    a.db(0x8B, 0xD1)                    # mov edx, ecx        ; idx
    a.call(GETPLAYERS_THUNK)            # GetPlayers(pcc, idx) -> rec
    a.db(0x85, 0xC0)
    a.j8(0x74, 'allow')
    a.db(0x80, 0x78, 0x08, 0x00)        # cmp byte [eax+8], 0 ; Local?
    a.j8(0x75, 'allow')                 # Remote/Global -> allow
    a.db(0xB0, 0x01)                    # mov al, 1  ; LOCAL + locked: "busy"
    a.db(0xC3)                          # ret
    a.label('allowp')
    a.db(0x5A)                          # pop edx (stack balance)
    a.label('allow')
    a.db(0x33, 0xC0)                    # xor eax, eax        ; not busy
    a.label('done')
    a.db(0xC3)                          # ret

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

    h_off = H_BUSY - VA2FILE
    c_off = CAVE_BASE - VA2FILE
    hits = reloc_check(data, [(h_off, h_off + len(BUSY_OLD)),
                              (c_off, c_off + len(cave))])
    if hits:
        print("ABORT: reloc fixups intersect patch ranges: %s" % hits); return 1
    print("  reloc scan    clean")

    cur = bytes(data[c_off:c_off + len(cave)])
    cave_new = bytes(len(cave)) if revert else cave
    if cur == cave_new:
        print("  %-14s already %s" % ("cave", "clear" if revert else "applied"))
    elif cur == bytes(len(cave)) or cur[:1] == b'\xE8':
        data[c_off:c_off + len(cave_new)] = cave_new; dirty = True
        print("  %-14s %s" % ("cave", "clearing" if revert else "ready"))
    else:
        print("  %-14s MISMATCH %s" % ("cave", cur[:8].hex())); ok = False

    new = BUSY_OLD if revert else (
        bytes([0xE8]) + (labels['cave_busy'] - (H_BUSY + 5)).to_bytes(4, 'little', signed=True))
    cur = bytes(data[h_off:h_off + len(BUSY_OLD)])
    if cur == new:
        print("  %-14s already applied" % "GetBusy call")
    elif cur == BUSY_OLD or cur[0] == 0xE8:
        data[h_off:h_off + len(new)] = new; dirty = True
        print("  %-14s ready @0x%X (%d bytes)" % ("GetBusy call", H_BUSY, len(new)))
    else:
        print("  %-14s MISMATCH @0x%X: %s" % ("GetBusy call", H_BUSY, cur.hex())); ok = False

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
