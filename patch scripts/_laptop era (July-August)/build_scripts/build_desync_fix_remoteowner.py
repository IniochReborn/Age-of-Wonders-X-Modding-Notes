#!/usr/bin/env python3
"""LAN out-of-sync FIX #3 (AoWEPACK.dll): one creator per move token.

DIAG v4 repro #6 (8/9, fixes #1+#2 verified loaded): the divergent move
(44,10,2) was created OUTSIDE any AI capture window (mid-token-stream, so
NOT the pump - fix #2 held) and executed on ONE machine only; the other
machine's token counter ran past that stream position without ever seeing
it.  RE: AoWE.MoveArmyEx @0x5574A318 is the single funnel that creates army
move tokens and adds them to **the army OWNER's token control on whichever
machine calls it** (tail @0x5574A444: GetTokenControl(owner) -> vcall+0x10
Add).  Its callers include machine-local event paths - Cave.TCave.EnterEx
+0x1F8 (cave-transit continuation, reached via TCave.Enter and the
TEnterCaveEventLog.Yes dialog callback) and Teleport.TTeleport.Teleport
+0x1B0 - so a continuation for a HUMAN-owned army (the recruited moles,
whose stored AI path runs through a cave) can be created on a machine where
that owner is REMOTE: the token lands in a non-broadcasting control and
executes one-sided -> one extra synced draw -> OOS.

FIX: hook MoveArmyEx entry.  In network games ([map+0x239]==2), if the
army owner's communication status is REMOTE (1) on this machine, return 0
("no move created") - the owner's machine creates the token and its Local
control broadcasts it with an agreed stream position.  Local (0) and
Global (2) owners are unaffected: Local = normal human flow (broadcast),
Global = the deterministic both-machines-create AI design (kept correct by
fixes #1+#2).  Covers ALL MoveArmyEx callers: MoveArmy wrapper,
MoveArmyXYL, TSelectedArmy.ExecuteMove, TCave.EnterEx, TTeleport.Teleport.
Callers already handle a False return (it is the existing busy/short-path
failure path).  SP/hotseat untouched (mode gate + nil checks).

Companion fixes that stay applied: #1 noanim (cave @0x55812000),
#2 aiowner (cave @0x55812100).  This cave @0x55812200-0x55812280.
Displaced entry bytes 55 8BEC 51 53 56 (push ebp;mov ebp,esp;push ecx;
push ebx;push esi), resume @0x5574A31E; blocked path must `ret 8`
(MoveArmyEx has two stack args).  Reloc scan built in.
Backup AoWEPACK.dll.bak_remoteowner.  Dry-run; --apply / --revert.
"""
import os
import shutil
import struct
import sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
TARGET = os.path.join(GAME, "AoWEPACK.dll")
BACKUP = TARGET + ".bak_remoteowner"

VA2FILE = 0x55700C00
AOWHSMAP = 0x558FA040

CAVE_BASE  = 0x55812200
CAVE_LIMIT = 0x55812280

GETPLAYERS_THUNK = 0x557035DC

H_MVAEX = 0x5574A318
MVAEX_OLD = bytes.fromhex("558BEC515356")   # push ebp;mov ebp,esp;push ecx;push ebx;push esi
MVAEX_RESUME = 0x5574A31E                    # push edi


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

    # entry: eax=armyHS, dl=sel, ecx=path; [esp]=ret, [esp+4]=flag, [esp+8]=mode
    a.label('cave_mvaex')
    a.db(0x50)                          # push eax
    a.db(0x52)                          # push edx
    a.db(0x51)                          # push ecx
    a.pic_delta_ecx()                   # ecx = load delta
    a.db(0x8B, 0x91); a.dd(AOWHSMAP)    # mov edx,[ecx+AoWHSMap]
    a.db(0x85, 0xD2)
    a.j8(0x74, 'allow')                 # no map -> vanilla
    a.db(0x80, 0xBA); a.dd(0x239); a.db(0x02)  # cmp byte [edx+0x239], 2
    a.j8(0x75, 'allow')                 # not a network game -> vanilla
    a.db(0x8B, 0x8A); a.dd(0x240)       # mov ecx,[edx+0x240]
    a.db(0x85, 0xC9)
    a.j8(0x74, 'allow')
    a.db(0x8B, 0x49, 0x1C)              # mov ecx,[ecx+0x1C]  ; pcc
    a.db(0x85, 0xC9)
    a.j8(0x74, 'allow')
    a.db(0x8B, 0x44, 0x24, 0x08)        # mov eax,[esp+8]     ; armyHS
    a.db(0x85, 0xC0)
    a.j8(0x74, 'allow')
    a.db(0x8B, 0x40, 0x1C)              # mov eax,[eax+0x1C]  ; army
    a.db(0x85, 0xC0)
    a.j8(0x74, 'allow')
    a.db(0x0F, 0xBE, 0x50, 0x12)        # movsx edx, byte [eax+0x12] ; owner
    a.db(0x8B, 0xC1)                    # mov eax, ecx        ; pcc
    a.call(GETPLAYERS_THUNK)            # GetPlayers(pcc, idx)
    a.db(0x85, 0xC0)
    a.j8(0x74, 'allow')                 # nil rec -> vanilla
    a.db(0x80, 0x78, 0x08, 0x01)        # cmp byte [eax+8], 1 ; Remote?
    a.j8(0x75, 'allow')                 # Local/Global -> vanilla
    a.db(0x59)                          # pop ecx  ; REMOTE owner: no local
    a.db(0x5A)                          # pop edx  ; creation - owner's
    a.db(0x58)                          # pop eax  ; machine broadcasts it
    a.db(0x33, 0xC0)                    # xor eax, eax   ; return False
    a.db(0xC2, 0x08, 0x00)              # ret 8          ; pop 2 stack args
    a.label('allow')
    a.db(0x59)                          # pop ecx
    a.db(0x5A)                          # pop edx
    a.db(0x58)                          # pop eax
    a.db(0x55)                          # displaced: push ebp
    a.db(0x8B, 0xEC)                    #            mov ebp, esp
    a.db(0x51)                          #            push ecx
    a.db(0x53)                          #            push ebx
    a.db(0x56)                          #            push esi
    a.jmp32(MVAEX_RESUME)

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

    h_off = H_MVAEX - VA2FILE
    c_off = CAVE_BASE - VA2FILE
    hits = reloc_check(data, [(h_off, h_off + len(MVAEX_OLD)),
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

    new = MVAEX_OLD if revert else (
        bytes([0xE9]) + (labels['cave_mvaex'] - (H_MVAEX + 5)).to_bytes(4, 'little', signed=True)
        + b'\x90' * (len(MVAEX_OLD) - 5))
    cur = bytes(data[h_off:h_off + len(MVAEX_OLD)])
    if cur == new:
        print("  %-14s already applied" % "MoveArmyEx")
    elif cur == MVAEX_OLD or cur[0] == 0xE9:
        data[h_off:h_off + len(new)] = new; dirty = True
        print("  %-14s ready @0x%X (%d bytes)" % ("MoveArmyEx", H_MVAEX, len(new)))
    else:
        print("  %-14s MISMATCH @0x%X: %s" % ("MoveArmyEx", H_MVAEX, cur.hex())); ok = False

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
