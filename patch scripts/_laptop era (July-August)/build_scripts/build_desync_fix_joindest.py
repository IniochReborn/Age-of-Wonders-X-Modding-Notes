#!/usr/bin/env python3
"""LAN out-of-sync FIX #4 (AoWEPACK.dll): clear stale destination at recruit-join.

DIAG v5 repro #8 (8/9, CRE3/CRE4 probes live) NAMED THE CREATOR: on the
machine where the recruiting human is LOCAL, the divergent mole move
(44,10,2) was created via MoveArmy <- TSelectedArmy.ExecuteMove+0x1F4 -
the UI selected-army path - with NO click.  MoveArmy's only other caller
is the fix #2 cave (pump, blocks non-Global owners), so the UI path is
proven by elimination AND by CRE3 retaddr = MoveArmy+0xF.

Mechanism: when the independent (AI) army's move token initialized
pre-recruit, TMoveArmyTE.InitializeMove+0xaf wrote the army's multi-turn
destination [army+0x25..0x27].  The negotiate JOIN transfers the army but
KEEPS that destination; the owner's machine UI (TSelectedArmy.Update
manages destinations; ExecuteMove's flag!=1 branch = SetDestinationPos +
MoveArmy continuation) then auto-resumes the stored AI path mid-token-
stream.  That token is created on ONE machine only and never delivered ->
one extra synced draw -> OOS (repro #8 ring: CRE3 MoveArmy+0xF ->
CREA (44,10,2) -> executed+ANIMATED owner=1 on A only -> BOOM).

FIX: hook the join-done site in TArmy.IncommingNegotiateOffer
@0x5578FC24 (mov eax,esi; call BeginUpdate - esi = the joining army;
diag v1 hooked this site safely, and v1 dumps proved the offer path runs
in LOCKSTEP on both machines, so the clear is deterministic).  In network
games ([map+0x239]==2), write the no-destination sentinel FF FF FF to
[esi+0x25..0x27] (exactly TArmy.ResetDestinationPos's body).  Recruited
armies simply stand still until commanded - the behavior fix #2 already
gave the pump side.  SP/hotseat untouched.

Companion fixes that stay applied: #1 noanim (cave @0x55812000),
#2 aiowner (cave @0x55812100).  Fix #3 remoteowner stays REVERTED.
This cave @0x55812200-0x55812280 (fix #3's vacated space).
Displaced 7 bytes 8BC6 E85936F7FF (call rel32 re-encoded in cave),
resume @0x5578FC2B.  Reloc scan built in.  PIC delta trick for the
AoWHSMap absolute (rebase-safe).  Backup AoWEPACK.dll.bak_joindest.
Dry-run; --apply / --revert.
"""
import os
import shutil
import struct
import sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
TARGET = os.path.join(GAME, "AoWEPACK.dll")
BACKUP = TARGET + ".bak_joindest"

VA2FILE = 0x55700C00
AOWHSMAP = 0x558FA040

CAVE_BASE  = 0x55812200
CAVE_LIMIT = 0x55812280

BEGINUPD = 0x55703284               # thunk EngineP!TEChangeNotifyNode.BeginUpdate

H_JOIN = 0x5578FC24
JOIN_OLD = bytes.fromhex("8BC6E85936F7FF")   # mov eax,esi; call BeginUpdate
JOIN_RESUME = 0x5578FC2B


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

    # entry: esi = joining army (preserved), ebx = offer rec (untouched)
    a.label('cave_join')
    a.db(0x50)                          # push eax
    a.db(0x51)                          # push ecx
    a.pic_delta_ecx()                   # ecx = load delta
    a.db(0x8B, 0x81); a.dd(AOWHSMAP)    # mov eax,[ecx+AoWHSMap]
    a.db(0x85, 0xC0)
    a.j8(0x74, 'skip')                  # no map -> vanilla
    a.db(0x80, 0xB8); a.dd(0x239); a.db(0x02)  # cmp byte [eax+0x239], 2
    a.j8(0x75, 'skip')                  # not a network game -> vanilla
    a.db(0x85, 0xF6)                    # test esi, esi
    a.j8(0x74, 'skip')
    a.db(0xC6, 0x46, 0x25, 0xFF)        # mov byte [esi+0x25], 0xFF
    a.db(0xC6, 0x46, 0x26, 0xFF)        # mov byte [esi+0x26], 0xFF  ; = TArmy.
    a.db(0xC6, 0x46, 0x27, 0xFF)        # mov byte [esi+0x27], 0xFF  ; ResetDestinationPos
    a.label('skip')
    a.db(0x59)                          # pop ecx
    a.db(0x58)                          # pop eax
    a.db(0x8B, 0xC6)                    # displaced: mov eax, esi
    a.call(BEGINUPD)                    #            call BeginUpdate (re-encoded)
    a.jmp32(JOIN_RESUME)

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

    h_off = H_JOIN - VA2FILE
    c_off = CAVE_BASE - VA2FILE
    hits = reloc_check(data, [(h_off, h_off + len(JOIN_OLD)),
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

    new = JOIN_OLD if revert else (
        bytes([0xE9]) + (labels['cave_join'] - (H_JOIN + 5)).to_bytes(4, 'little', signed=True)
        + b'\x90' * (len(JOIN_OLD) - 5))
    cur = bytes(data[h_off:h_off + len(JOIN_OLD)])
    if cur == new:
        print("  %-14s already applied" % "join-done")
    elif cur == JOIN_OLD or cur[0] == 0xE9:
        data[h_off:h_off + len(new)] = new; dirty = True
        print("  %-14s ready @0x%X (%d bytes)" % ("join-done", H_JOIN, len(new)))
    else:
        print("  %-14s MISMATCH @0x%X: %s" % ("join-done", H_JOIN, cur.hex())); ok = False

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
