#!/usr/bin/env python3
"""LAN out-of-sync diagnostic v2 (AoWEPACK.dll) - record-only, revertible.

v1 (build_desync_diag.py, reverted) established: the recruit executes
identically on both machines; the divergence is ONE extra TMoveTE synced-RNG
draw on one machine right before the OOS fires.  Ambiguity left: did the AI
MOVE GENERATION diverge, or did the move token execute in a DIFFERENT ORDER
relative to the sync-check token (same move queued on both, checked at
different stream positions)?

v2 records a merged per-machine timeline in the RING (@0x558FAA00, 128 x
{tag/caller, value}) to settle that:

  - every TAoWHSMap.Random call: {caller retaddr, seed before}   (as v1,
    hardened: seed read via the AoWHSMap GLOBAL with null checks, never
    an unchecked deref)
  - 'MOVE' on each TMoveTE first-execute (hooked right AFTER its Random
    draw at 0x557478F2, so exactly once per move): value = first path
    entry packed x|y<<8|lvl<<16 from [TE+0x14] TXYLList
  - 'SYNC' on each TPlayerControl.GetSyncValue read (fires both when
    SENDING a TSyncTE and when CHECKING one): value = current seed
  - 'BOOM' when TPlayerControl.OutOfSync fires: value = current seed

If B has the same MOVE queued but checked early, its timeline shows
SYNC/BOOM before the MOVE that A's timeline shows after.  If B never
generates the MOVE, it simply won't appear.  Reader: re_tools/desync_dump.py.

No scratch block this time - the ring is the whole record.
Hooks (displaced bytes re-executed byte-for-byte, PIC caves):
  H1 0x5577827C TAoWHSMap.Random entry           (6)
  H2 0x557478F2 TMoveTE.Execute post-Random      (6)
  H3 0x55754D04 TPlayerControl.GetSyncValue      (5)
  H4 0x55754D14 TPlayerControl.OutOfSync entry   (5)
Cave @0x55811000 (file 0x110400, zeros after v1 revert).

H3's displaced instruction (A1 40A08F55, mov eax,[AoWHSMap]) carries a base
relocation on its imm32 (VA 0x55754D05, .reloc entry word at file 0x27DBD0).
Left active, a REBASED instance gets that fixup applied on top of our jmp
rel32 -> wild jump -> "Exception during AoWHSMap.NewFrame" every frame (the
8/7 immediate-freeze).  Apply therefore neutralizes the entry (type 3 -> 0,
loader skips); revert restores it.  The cave re-creates the load PIC-style,
so nothing needs that fixup anymore.

Dry-run default; --apply / --revert.  Backup AoWEPACK.dll.bak_desync_diag2.
"""
import os
import shutil
import sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
TARGET = os.path.join(GAME, "AoWEPACK.dll")
BACKUP = TARGET + ".bak_desync_diag2"

VA2FILE = 0x55700C00
AOWHSMAP = 0x558FA040
RING     = 0x558FAA00
RINGMASK = 0x7F

TAG_MOVE = 0x4D4F5645
TAG_SYNC = 0x53594E43
TAG_BOOM = 0x424F4F4D

CAVE_BASE  = 0x55811000
CAVE_LIMIT = 0x55811200

H_RANDOM = 0x5577827C
H_MOVE   = 0x557478F2
H_SYNC   = 0x55754D04
H_BOOM   = 0x55754D14

# .reloc entry covering H_SYNC+1 (imm32 of displaced mov eax,[AoWHSMap])
RELOC_ENTRY_OFF = 0x27DBD0   # file offset of the 16-bit entry
RELOC_OLD = 0x3D05           # type 3 (HIGHLOW), page 0x54000 + 0xD05
RELOC_NEW = 0x0D05           # type 0 (ABSOLUTE) = skipped by loader

OLD = {
    H_RANDOM: bytes.fromhex("53568BF28BD8"),   # push ebx;push esi;mov esi,edx;mov ebx,eax
    H_MOVE:   bytes.fromhex("8B43148B4008"),   # mov eax,[ebx+14h];mov eax,[eax+8]
    H_SYNC:   bytes.fromhex("A140A08F55"),     # mov eax,[AoWHSMap]
    H_BOOM:   bytes.fromhex("5356578BD8"),     # push ebx;push esi;push edi;mov ebx,eax
}


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
        self.db(0x59)                        # pop ecx
        self.db(0x81, 0xE9); self.dd(popva)  # sub ecx, preferred-VA
    def seed_to_edx(self, suffix):
        # edx := [AoWHSMap global]->seed, 0 if map nil (ecx = delta)
        self.db(0x8B, 0x91); self.dd(AOWHSMAP)   # mov edx,[ecx+AoWHSMap]
        self.db(0x85, 0xD2)                      # test edx, edx
        self.j8(0x74, 'z' + suffix)              # jz  z
        self.db(0x8B, 0x92); self.dd(0x230)      # mov edx,[edx+0x230]
        self.j8(0xEB, 'h' + suffix)              # jmp h
        self.label('z' + suffix)
        self.db(0x33, 0xD2)                      # xor edx, edx
        self.label('h' + suffix)
    def resolve(self):
        for off, lab in self.fix32:
            self.buf[off:off+4] = (self.labels[lab] - (self.base + off + 4)).to_bytes(4, 'little', signed=True)
        for off, lab in self.fix8:
            rel = self.labels[lab] - (self.base + off + 1)
            assert -128 <= rel <= 127, "rel8 %s %d" % (lab, rel)
            self.buf[off] = rel & 0xFF


def build_cave():
    a = Asm(CAVE_BASE)

    # ring_append: ecx=delta, eax=val1, edx=val2; preserves ebx/esi/edi/ecx
    a.label('ring_append')
    a.db(0x53)                          # push ebx
    a.db(0x56)                          # push esi
    a.db(0x8B, 0x99); a.dd(RING)        # mov ebx,[ecx+RING]
    a.db(0x8B, 0xF3)                    # mov esi, ebx
    a.db(0x83, 0xE6, RINGMASK)          # and esi, 7Fh
    a.db(0x8D, 0xB4, 0xF1); a.dd(RING + 8)  # lea esi,[ecx+esi*8+RING+8]
    a.db(0x89, 0x06)                    # mov [esi], eax
    a.db(0x89, 0x56, 0x04)              # mov [esi+4], edx
    a.db(0x43)                          # inc ebx
    a.db(0x89, 0x99); a.dd(RING)        # mov [ecx+RING], ebx
    a.db(0x5E)                          # pop esi
    a.db(0x5B)                          # pop ebx
    a.db(0xC3)                          # ret

    # H1: Random entry.  eax=self, edx=range, [esp]=caller
    a.label('cave_random')
    a.db(0x50); a.db(0x52); a.db(0x51)  # push eax/edx/ecx
    a.pic_delta_ecx()
    a.seed_to_edx('r')                  # edx = seed (null-safe)
    a.db(0x8B, 0x44, 0x24, 0x0C)        # mov eax,[esp+0Ch]   ; caller
    a.call('ring_append')
    a.db(0x59); a.db(0x5A); a.db(0x58)  # pop ecx/edx/eax
    a.db(0x53)                          # push ebx            ; displaced
    a.db(0x56)                          # push esi
    a.db(0x8B, 0xF2)                    # mov esi, edx
    a.db(0x8B, 0xD8)                    # mov ebx, eax
    a.jmp32(H_RANDOM + 6)

    # H2: TMoveTE post-Random.  ebx=TE
    a.label('cave_move')
    a.db(0x50); a.db(0x52); a.db(0x51)  # push eax/edx/ecx
    a.pic_delta_ecx()
    a.db(0x8B, 0x53, 0x14)              # mov edx,[ebx+14h]   ; path TXYLList
    a.db(0x85, 0xD2)                    # test edx, edx
    a.j8(0x74, 'mz')                    # jz  mz
    a.db(0x8B, 0x42, 0x04)              # mov eax,[edx+4]     ; data ptr
    a.db(0x85, 0xC0)                    # test eax, eax
    a.j8(0x74, 'mz')                    # jz  mz
    a.db(0x8B, 0x10)                    # mov edx,[eax]       ; first XYL
    a.j8(0xEB, 'mh')                    # jmp mh
    a.label('mz')
    a.db(0x33, 0xD2)                    # xor edx, edx
    a.label('mh')
    a.db(0xB8); a.dd(TAG_MOVE)          # mov eax,'MOVE'
    a.call('ring_append')
    a.db(0x59); a.db(0x5A); a.db(0x58)  # pop ecx/edx/eax
    a.db(0x8B, 0x43, 0x14)              # mov eax,[ebx+14h]   ; displaced
    a.db(0x8B, 0x40, 0x08)              # mov eax,[eax+8]
    a.jmp32(H_MOVE + 6)

    # H3: GetSyncValue entry.  edx = out-ptr (must survive)
    a.label('cave_sync')
    a.db(0x50); a.db(0x52); a.db(0x51)  # push eax/edx/ecx
    a.pic_delta_ecx()
    a.seed_to_edx('s')                  # edx = seed
    a.db(0xB8); a.dd(TAG_SYNC)          # mov eax,'SYNC'
    a.call('ring_append')
    a.db(0x59); a.db(0x5A); a.db(0x58)  # pop ecx/edx/eax
    a.db(0x51)                          # push ecx            ; displaced (PIC form)
    a.pic_delta_ecx()
    a.db(0x8B, 0x81); a.dd(AOWHSMAP)    # mov eax,[ecx+AoWHSMap]
    a.db(0x59)                          # pop ecx
    a.jmp32(H_SYNC + 5)

    # H4: OutOfSync entry.  eax=self
    a.label('cave_boom')
    a.db(0x50); a.db(0x52); a.db(0x51)  # push eax/edx/ecx
    a.pic_delta_ecx()
    a.seed_to_edx('b')                  # edx = seed
    a.db(0xB8); a.dd(TAG_BOOM)          # mov eax,'BOOM'
    a.call('ring_append')
    a.db(0x59); a.db(0x5A); a.db(0x58)  # pop ecx/edx/eax
    a.db(0x53)                          # push ebx            ; displaced
    a.db(0x56)                          # push esi
    a.db(0x57)                          # push edi
    a.db(0x8B, 0xD8)                    # mov ebx, eax
    a.jmp32(H_BOOM + 5)

    a.resolve()
    assert CAVE_BASE + len(a.buf) <= CAVE_LIMIT, "cave overflow %d" % len(a.buf)
    return bytes(a.buf) + bytes(CAVE_LIMIT - CAVE_BASE - len(a.buf)), a.labels


def main():
    apply = "--apply" in sys.argv
    revert = "--revert" in sys.argv
    data = bytearray(open(TARGET, "rb").read())
    cave, labels = build_cave()
    ok, dirty = True, False
    print("cave: %d bytes @0x%X (file 0x%X)" %
          (len(cave.rstrip(b'\0')), CAVE_BASE, CAVE_BASE - VA2FILE))

    off = CAVE_BASE - VA2FILE
    cur = bytes(data[off:off+len(cave)])
    cave_new = bytes(len(cave)) if revert else cave
    if cur == cave_new:
        print("  %-14s already %s" % ("cave", "clear" if revert else "applied"))
    elif cur == bytes(len(cave)) or cur[:1] == b'\x53':
        data[off:off+len(cave_new)] = cave_new; dirty = True
        print("  %-14s %s" % ("cave", "clearing" if revert else "ready"))
    else:
        print("  %-14s MISMATCH %s" % ("cave", cur[:8].hex())); ok = False

    for name, va, lab in (("H1 Random", H_RANDOM, 'cave_random'),
                          ("H2 MoveTE", H_MOVE, 'cave_move'),
                          ("H3 SyncValue", H_SYNC, 'cave_sync'),
                          ("H4 OutOfSync", H_BOOM, 'cave_boom')):
        old = OLD[va]
        new = old if revert else (
            bytes([0xE9]) + (labels[lab] - (va + 5)).to_bytes(4, 'little', signed=True)
            + b'\x90' * (len(old) - 5))
        off = va - VA2FILE
        cur = bytes(data[off:off+len(old)])
        if cur == new:
            print("  %-14s already applied" % name)
        elif cur == old or cur[0] == 0xE9:
            data[off:off+len(new)] = new; dirty = True
            print("  %-14s ready @0x%X (%d bytes)" % (name, va, len(new)))
        else:
            print("  %-14s MISMATCH @0x%X: %s" % (name, va, cur.hex())); ok = False

    want = RELOC_OLD if revert else RELOC_NEW
    cur = int.from_bytes(data[RELOC_ENTRY_OFF:RELOC_ENTRY_OFF+2], 'little')
    if cur == want:
        print("  %-14s already %s" % ("H3 reloc", "restored" if revert else "off"))
    elif cur in (RELOC_OLD, RELOC_NEW):
        data[RELOC_ENTRY_OFF:RELOC_ENTRY_OFF+2] = want.to_bytes(2, 'little')
        dirty = True
        print("  %-14s ready (0x%04X -> 0x%04X @file 0x%X)"
              % ("H3 reloc", cur, want, RELOC_ENTRY_OFF))
    else:
        print("  %-14s MISMATCH 0x%04X" % ("H3 reloc", cur)); ok = False

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
