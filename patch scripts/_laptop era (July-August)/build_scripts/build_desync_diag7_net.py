#!/usr/bin/env python3
"""LAN out-of-sync diagnostic v7 (Network.dpl!) - send/receive tracer.

Transport RE (8/9): locally-created tokens go TC.AddEvent -> TC list; at the
TC's round-robin activation TTokenExecuter.Process calls PrefetchTokenEvents
(assigns stream positions, moves events to the executer pending list
[exec+0x10], clears the TC list) then TC.TokenEventsPrefetched(pendinglist)
which - for a strictly-LOCAL tc with events - vcalls the distributer's
SendTokenEvents (broadcast).  The receive side is TTokenPackageDistributer.
TokenPackageReceived -> events land in the matching REMOTE tc's list ->
GetPrefetchableTokenEvents accepts them only when counters == expected.
TNegotiateTE.Accept/Reject bypass ALL of this via TTokenExecuter.
InsertExecuteEvent (the only two callers in the game) - never transmitted,
symmetric only because Accept executes on both machines.

OPEN QUESTION this diag answers: for the one-sided recruited-army move, did
the owner's machine actually SEND the batch (TokenEventsPrefetched with
count>0 for that player) and did the peer RECEIVE anything?

Hooks (record-only, Network-local mini-ring @BSS 0x55808100: +0 count,
+4: 32 x u32 entries; PIC via Network delta - Network.dpl DOES rebase):
  H1 'send-candidate' TTokenControl.TokenEventsPrefetched entry @0x55803B48
     (6B 53 56 8BF1 8BD8, resume 0x55803B4E): entry = playeridx | inner
     list count<<8 | 0<<31.  Fires per TC activation (post-prefetch, list =
     executer pending incl. SyncTE/PassTokenTE wrappers).
  H2 'recv' TTokenPackageDistributer.TokenPackageReceived entry @0x55803588
     (6B 53 56 57 55 8BF2, resume 0x5580358E): entry = source playeridx
     ([package+8]) | 1<<31.
Cave @0x55806220-0x55806400 (CODE section padding, verified zeros).
Reader: desync_dump.py (netring section).  Backup Network.dpl.bak_diag7.
Dry-run; --apply / --revert.
"""
import os
import shutil
import struct
import sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
TARGET = os.path.join(GAME, "Network.dpl")
BACKUP = TARGET + ".bak_diag7"

VA2FILE = 0x55800C00                  # Network.dpl: VA = file_off + 0x55800C00
NRING    = 0x55808100                 # Network BSS page (zero-filled, writable)
NRINGMASK = 0x1F                      # 32 entries

CAVE_BASE  = 0x55806220
CAVE_LIMIT = 0x55806400

H_SEND = 0x55803B48
SEND_OLD = bytes.fromhex("53568BF18BD8")   # push ebx;push esi;mov esi,ecx;mov ebx,eax
SEND_RESUME = 0x55803B4E

H_RECV = 0x55803588
RECV_OLD = bytes.fromhex("535657558BF2")   # push ebx/esi/edi/ebp;mov esi,edx
RECV_RESUME = 0x5580358E


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

    # nring_append: ecx=delta, edx=value.  Clobbers nothing (saves ebx/esi).
    a.label('nring_append')
    a.db(0x53)                          # push ebx
    a.db(0x56)                          # push esi
    a.db(0x8B, 0x99); a.dd(NRING)       # mov ebx,[ecx+NRING]     ; count
    a.db(0x8B, 0xF3)                    # mov esi, ebx
    a.db(0x83, 0xE6, NRINGMASK)         # and esi, MASK
    a.db(0x8D, 0xB4, 0xB1); a.dd(NRING + 4)  # lea esi,[ecx+esi*4+NRING+4]
    a.db(0x89, 0x16)                    # mov [esi], edx
    a.db(0x43)                          # inc ebx
    a.db(0x89, 0x99); a.dd(NRING)       # mov [ecx+NRING], ebx
    a.db(0x5E)                          # pop esi
    a.db(0x5B)                          # pop ebx
    a.db(0xC3)                          # ret

    # H1: TokenEventsPrefetched entry.  eax=tc, ecx=list (both must survive)
    a.label('cave_send')
    a.db(0x50)                          # push eax
    a.db(0x52)                          # push edx
    a.db(0x51)                          # push ecx
    a.db(0x8B, 0xD1)                    # mov edx, ecx        ; list
    a.db(0x8B, 0x48, 0x0C)              # mov ecx,[eax+0xC]   ; playeridx
    a.db(0x81, 0xE1); a.dd(0xFF)        # and ecx, 0xFF
    # inner count: [[list+8]+8]+8, nil-checked
    a.db(0x85, 0xD2)                    # test edx, edx
    a.j8(0x74, 'sz')
    a.db(0x8B, 0x52, 0x08)              # mov edx,[edx+8]
    a.db(0x85, 0xD2)
    a.j8(0x74, 'sz')
    a.db(0x8B, 0x52, 0x08)              # mov edx,[edx+8]
    a.db(0x85, 0xD2)
    a.j8(0x74, 'sz')
    a.db(0x8B, 0x52, 0x08)              # mov edx,[edx+8]     ; count
    a.db(0x81, 0xE2); a.dd(0xFFFF)      # and edx, 0xFFFF
    a.j8(0xEB, 'sh')
    a.label('sz')
    a.db(0x33, 0xD2)                    # xor edx, edx
    a.label('sh')
    a.db(0xC1, 0xE2, 0x08)              # shl edx, 8
    a.db(0x0B, 0xD1)                    # or  edx, ecx        ; idx | count<<8
    a.pic_delta_ecx()                   # ecx = delta
    a.call('nring_append')
    a.db(0x59)                          # pop ecx
    a.db(0x5A)                          # pop edx
    a.db(0x58)                          # pop eax
    a.db(0x53)                          # displaced: push ebx
    a.db(0x56)                          #            push esi
    a.db(0x8B, 0xF1)                    #            mov esi, ecx
    a.db(0x8B, 0xD8)                    #            mov ebx, eax
    a.jmp32(SEND_RESUME)

    # H2: TokenPackageReceived entry.  eax=self, edx=package (both survive)
    a.label('cave_recv')
    a.db(0x50)                          # push eax
    a.db(0x52)                          # push edx
    a.db(0x51)                          # push ecx
    a.db(0x8B, 0x52, 0x08)              # mov edx,[edx+8]     ; src playeridx
    a.db(0x81, 0xE2); a.dd(0xFF)        # and edx, 0xFF
    a.db(0x81, 0xCA); a.dd(0x80000000)  # or  edx, 0x80000000 ; RECV marker
    a.pic_delta_ecx()                   # ecx = delta
    a.call('nring_append')
    a.db(0x59)                          # pop ecx
    a.db(0x5A)                          # pop edx
    a.db(0x58)                          # pop eax
    a.db(0x53)                          # displaced: push ebx
    a.db(0x56)                          #            push esi
    a.db(0x57)                          #            push edi
    a.db(0x55)                          #            push ebp
    a.db(0x8B, 0xF2)                    #            mov esi, edx
    a.jmp32(RECV_RESUME)

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

    ranges = [(H_SEND - VA2FILE, H_SEND - VA2FILE + len(SEND_OLD)),
              (H_RECV - VA2FILE, H_RECV - VA2FILE + len(RECV_OLD)),
              (CAVE_BASE - VA2FILE, CAVE_LIMIT - VA2FILE)]
    hits = reloc_check(data, ranges)
    if hits:
        print("ABORT: reloc fixups intersect patch ranges: %s" % hits); return 1
    print("  reloc scan    clean")

    c_off = CAVE_BASE - VA2FILE
    cur = bytes(data[c_off:c_off + len(cave)])
    cave_new = bytes(len(cave)) if revert else cave
    if cur == cave_new:
        print("  %-14s already %s" % ("cave", "clear" if revert else "applied"))
    elif cur == bytes(len(cave)) or cur[:1] == b'\x53':
        data[c_off:c_off + len(cave_new)] = cave_new; dirty = True
        print("  %-14s %s" % ("cave", "clearing" if revert else "ready"))
    else:
        print("  %-14s MISMATCH %s" % ("cave", cur[:8].hex())); ok = False

    for name, va, old, lab in (("H1 send-cand", H_SEND, SEND_OLD, 'cave_send'),
                               ("H2 recv", H_RECV, RECV_OLD, 'cave_recv')):
        new = old if revert else (
            bytes([0xE9]) + (labels[lab] - (va + 5)).to_bytes(4, 'little', signed=True)
            + b'\x90' * (len(old) - 5))
        off = va - VA2FILE
        cur = bytes(data[off:off + len(old)])
        if cur == new:
            print("  %-14s already applied" % name)
        elif cur == old or cur[0] == 0xE9:
            data[off:off + len(new)] = new; dirty = True
            print("  %-14s ready @0x%X (%d bytes)" % (name, va, len(new)))
        else:
            print("  %-14s MISMATCH @0x%X: %s" % (name, va, cur.hex())); ok = False

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
