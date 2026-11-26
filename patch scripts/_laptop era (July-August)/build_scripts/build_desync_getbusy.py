#!/usr/bin/env python3
"""Confirmation hook for the LAN-desync root cause (AoWEPACK.dll), record-only.

Pairs with build_desync_diag.py (leave that applied too).  The diff of two
live instances pinned the divergence to TAutoProduceAIPA.Process's production
loop: both machines drew the same synced RNG up to the recruit, then one
machine's AI auto-production drew MORE picks than the other.  That loop is
gated per-iteration by TPlayer.GetBusy@0x557516D0, which tail-calls
TPlayer.GetLocal@0x55753720 (reads the network TPlayerCommunicationControl at
[AoWHSMap+0x240] - machine-local).  Hypothesis: the loop runs a different
number of iterations because GetBusy differs between host and client.

This patch instruments ONLY the GetBusy call inside that loop
(0x55735C4A `call GetBusy` -> `call cave_getbusy`).  cave_getbusy calls the
real GetBusy (unchanged return), then also calls GetLocal for the same player,
and appends {player index, busy, local} to a ring in BSS slack:

  GBRING @0x558FAE20 (after the diag RING which ends 0x558FAE08):
    +0 dd count
    +4 .. : 64 entries x dd, each = playerIdx | busy<<8 | local<<16

So the sequence of GetBusy/GetLocal results per production-loop iteration is
recorded on BOTH machines.  If the same player's GetBusy/GetLocal differ
between the two instances at the point the RNG streams split, the local/remote
asymmetry is proven.  Reader: re_tools/desync_dump.py (prints the GBRING).

Cave @0x55811200 (file 0x110600, verified zeros; diag cave ends 0x558111CA).
Dry-run default; --apply writes (backup AoWEPACK.dll.bak_desync_getbusy);
--revert restores the call site + zeros the cave.
"""
import os
import shutil
import sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
TARGET = os.path.join(GAME, "AoWEPACK.dll")
BACKUP = TARGET + ".bak_desync_getbusy"

VA2FILE = 0x55700C00

GETBUSY  = 0x557516D0
GETLOCAL = 0x55753720
GBRING   = 0x558FAE20
GBMASK   = 0x3F                       # 64 entries

HOOK_SITE = 0x55735C4A                # `call GetBusy` in TAutoProduceAIPA.Process
HOOK_OLD  = bytes.fromhex("e881ba0100")

CAVE_BASE  = 0x55811200
CAVE_LIMIT = 0x55811300


class Asm:
    def __init__(self, base):
        self.base = base; self.buf = bytearray(); self.labels = {}
        self.fix32 = []
    def here(self): return self.base + len(self.buf)
    def label(self, n): self.labels[n] = self.here()
    def db(self, *b): self.buf += bytes(b)
    def dd(self, v): self.buf += (v & 0xFFFFFFFF).to_bytes(4, 'little')
    def call(self, t): self.db(0xE8); self._r(t)
    def _r(self, t):
        if isinstance(t, str):
            self.fix32.append((len(self.buf), t)); self.buf += b'\0\0\0\0'
        else:
            self.buf += (t - (self.here() + 4)).to_bytes(4, 'little', signed=True)
    def resolve(self):
        for off, lab in self.fix32:
            self.buf[off:off+4] = (self.labels[lab] - (self.base + off + 4)).to_bytes(4, 'little', signed=True)


def build_cave():
    a = Asm(CAVE_BASE)
    # in: eax = player.  out: al = GetBusy(player) (unchanged for the caller).
    # preserves ebx/esi/edi/ebp (the loop needs them); uses eax/ecx/edx only.
    a.label('cave_getbusy')
    a.db(0x50)                          # push eax                ; [esp]=player
    a.call(GETBUSY)                     # al = busy (eax=player)
    a.db(0x50)                          # push eax                ; [esp]=busy [+4]=player
    a.db(0x8B, 0x44, 0x24, 0x04)        # mov eax,[esp+4]         ; player
    a.call(GETLOCAL)                    # al = local
    a.db(0x50)                          # push eax                ; [esp]=local [+4]=busy [+8]=player
    a.call(a.here() + 5)                # call $+5
    popva = a.here()
    a.db(0x59)                          # pop ecx
    a.db(0x81, 0xE9); a.dd(popva)       # sub ecx, popva          ; ecx = PIC delta
    a.db(0x8B, 0x81); a.dd(GBRING)      # mov eax,[ecx+GBRING]    ; count
    a.db(0x8D, 0x50, 0x01)              # lea edx,[eax+1]
    a.db(0x89, 0x91); a.dd(GBRING)      # mov [ecx+GBRING], edx   ; count++
    a.db(0x25); a.dd(GBMASK)            # and eax, GBMASK         ; slot
    a.db(0x8D, 0x14, 0x81)              # lea edx,[ecx+eax*4]     ; delta + slot*4
    # build packed = playerIdx | busy<<8 | local<<16
    a.db(0x8B, 0x44, 0x24, 0x08)        # mov eax,[esp+8]         ; player
    a.db(0x0F, 0xB6, 0x80); a.dd(0xA6)  # movzx eax, byte [eax+0A6h] ; player index
    a.db(0x8A, 0x64, 0x24, 0x04)        # mov ah, [esp+4]         ; busy -> ah
    a.db(0x0F, 0xB6, 0x0C, 0x24)        # movzx ecx, byte [esp]   ; local
    a.db(0xC1, 0xE1, 0x10)              # shl ecx, 16
    a.db(0x09, 0xC8)                    # or eax, ecx
    a.db(0x89, 0x82); a.dd(GBRING + 4)  # mov [edx+GBRING+4], eax ; store entry
    a.db(0x0F, 0xB6, 0x44, 0x24, 0x04)  # movzx eax,[esp+4]       ; return busy in al
    a.db(0x83, 0xC4, 0x0C)              # add esp, 12
    a.db(0xC3)                          # ret
    a.resolve()
    assert CAVE_BASE + len(a.buf) <= CAVE_LIMIT, "cave overflow %d" % len(a.buf)
    return bytes(a.buf) + bytes(CAVE_LIMIT - CAVE_BASE - len(a.buf)), a.labels


def main():
    apply = "--apply" in sys.argv
    revert = "--revert" in sys.argv
    data = bytearray(open(TARGET, "rb").read())
    cave, labels = build_cave()
    dirty = ok = True
    ok = True
    print("cave: %d bytes @0x%X (file 0x%X)" %
          (len(cave.rstrip(b'\0')), CAVE_BASE, CAVE_BASE - VA2FILE))

    off = CAVE_BASE - VA2FILE
    cur = bytes(data[off:off+len(cave)])
    cave_new = bytes(len(cave)) if revert else cave
    cdirty = False
    if cur == cave_new:
        print("  %-22s already %s" % ("cave", "clear" if revert else "applied"))
    elif cur == bytes(len(cave)) or cur[:1] == b'\x50':
        data[off:off+len(cave_new)] = cave_new
        cdirty = True
        print("  %-22s %s" % ("cave", "clearing" if revert else "ready"))
    else:
        print("  %-22s MISMATCH %s" % ("cave", cur[:8].hex())); ok = False

    new = HOOK_OLD if revert else (bytes([0xE8]) +
          (labels['cave_getbusy'] - (HOOK_SITE + 5)).to_bytes(4, 'little', signed=True))
    off = HOOK_SITE - VA2FILE
    cur = bytes(data[off:off+5])
    hdirty = False
    if cur == new:
        print("  %-22s already applied" % "getbusy call")
    elif cur == HOOK_OLD or cur[0] == 0xE8:
        data[off:off+5] = new
        hdirty = True
        print("  %-22s ready @0x%X" % ("getbusy call", HOOK_SITE))
    else:
        print("  %-22s MISMATCH %s" % ("getbusy call", cur.hex())); ok = False

    if not ok:
        print("ABORT."); return 1
    if not (cdirty or hdirty):
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
