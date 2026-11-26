#!/usr/bin/env python3
"""LAN out-of-sync FIX (AoWEPACK.dll): no-animation path for Global armies.

ROOT CAUSE (diag v1-v3.2, three consistent repros incl 2026-08-09 home-PC):
AI ("Global", comm-status 2) players are simulated on ALL machines; their
follow-up moves are created by the AI pump only after the previous move's
token completes.  A move token (TMoveTE.Execute) completes in ONE call when
the move is not animated, but spans MANY frames when the local machine
animates it - and animation is gated per-machine by TMoveArmyTE.MoveVisible
(local-viewer visibility) + viewed-level checks in SetupNextMove.  So the
machine watching the army finishes the move LATER, its AI pump issues the
follow-up move in a later capture window, the locally-generated move tokens
interleave differently with the network sync token, each TMoveTE.Execute
consumes one synced Random draw -> seed offset -> OutOfSync.

FIX: hook TMoveArmyTE.MoveVisible @0x55748198 (the ONLY animation gate -
sole callers are SetupNextMove, which starts sprite animation via
TArmyHS.MoveFirst, and ObserveMove; all four token subclasses share
SetupNextMove, and every Animating override bottoms out on GetMoveStatus
which stays 0xFF idle unless SetupNextMove ran MoveFirst).  The cave returns
FALSE (not visible -> instant move, an existing vanilla path used for
off-screen/cross-level moves) when:
  - byte [map+0x239] == 2      (network game only - SP/hotseat untouched), and
  - army owner's communication record byte +8 == 2  (Global, i.e. AI-simulated
    everywhere; record via NetworkE.TPlayerCommunicationControl.GetPlayers
    (import thunk @0x557035DC), pcc = [[map+0x240]+0x1C], owner idx =
    [[[TE+0x28]+0x1C]+0x12]).
Every pointer is nil-checked -> falls through to vanilla MoveVisible.
Visual cost in network games only: AI/independent armies relocate instantly
instead of walking (humans' own armies still animate - they are Local/Remote).

PIC: cave uses the call/pop delta trick for the in-image global 0x558FA040
(ASLR rebases between the two LAN instances - see rebase-crash-runtime-error-216
and patching-over-relocs-gotcha memories).  Hook site + cave verified
reloc-free 2026-08-09 (script re-verifies before writing).

Cave @0x55812000 (clear of diag v3 @0x55811000-0x55811300 and cave_spring
@0x55810000).  Compatible with diag v3 applied or reverted (touches only its
own two byte ranges).  Backup AoWEPACK.dll.bak_noanim = pre-fix state (which
on first apply 2026-08-09 still includes diag v3.2).

Dry-run default; --apply / --revert.
"""
import os
import shutil
import struct
import sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
TARGET = os.path.join(GAME, "AoWEPACK.dll")
BACKUP = TARGET + ".bak_noanim"

VA2FILE = 0x55700C00
AOWHSMAP = 0x558FA040

CAVE_BASE  = 0x55812000
CAVE_LIMIT = 0x55812100

H_MVIS = 0x55748198               # TMoveArmyTE.MoveVisible entry
MVIS_OLD = bytes.fromhex("53568BF28BD8")  # push ebx;push esi;mov esi,edx;mov ebx,eax
GETPLAYERS_THUNK = 0x557035DC     # jmp [NetworkE.TPlayerCommunicationControl.GetPlayers]


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
    def resolve(self):
        for off, lab in self.fix32:
            self.buf[off:off+4] = (self.labels[lab] - (self.base + off + 4)).to_bytes(4, 'little', signed=True)
        for off, lab in self.fix8:
            rel = self.labels[lab] - (self.base + off + 1)
            assert -128 <= rel <= 127, "rel8 %s %d" % (lab, rel)
            self.buf[off] = rel & 0xFF


def build_cave():
    a = Asm(CAVE_BASE)

    # entry regs: eax = TE self, edx = step (both must reach vanilla intact)
    a.label('cave_mvis')
    a.db(0x50)                          # push eax
    a.db(0x52)                          # push edx
    a.db(0x51)                          # push ecx
    a.pic_delta_ecx()                   # ecx = load delta
    a.db(0x8B, 0x81); a.dd(AOWHSMAP)    # mov eax,[ecx+AoWHSMap]
    a.db(0x85, 0xC0)                    # test eax, eax
    a.j8(0x74, 'van')                   # jz  vanilla         ; no map
    a.db(0x80, 0xB8); a.dd(0x239); a.db(0x02)  # cmp byte [eax+0x239], 2
    a.j8(0x75, 'van')                   # jne vanilla         ; not a network game
    a.db(0x8B, 0x88); a.dd(0x240)       # mov ecx,[eax+0x240] ; comm holder
    a.db(0x85, 0xC9)                    # test ecx, ecx
    a.j8(0x74, 'van')                   # jz  vanilla
    a.db(0x8B, 0x49, 0x1C)              # mov ecx,[ecx+0x1C]  ; TPlayerCommunicationControl
    a.db(0x85, 0xC9)                    # test ecx, ecx
    a.j8(0x74, 'van')                   # jz  vanilla
    a.db(0x8B, 0x44, 0x24, 0x08)        # mov eax,[esp+8]     ; TE self
    a.db(0x8B, 0x40, 0x28)              # mov eax,[eax+0x28]  ; armyHS
    a.db(0x85, 0xC0)                    # test eax, eax
    a.j8(0x74, 'van')                   # jz  vanilla
    a.db(0x8B, 0x40, 0x1C)              # mov eax,[eax+0x1C]  ; army
    a.db(0x85, 0xC0)                    # test eax, eax
    a.j8(0x74, 'van')                   # jz  vanilla
    a.db(0x0F, 0xBE, 0x50, 0x12)        # movsx edx, byte [eax+0x12]  ; owner idx
    a.db(0x8B, 0xC1)                    # mov eax, ecx        ; pcc
    a.call(GETPLAYERS_THUNK)            # GetPlayers(pcc, idx); nil if idx bad
    a.db(0x85, 0xC0)                    # test eax, eax
    a.j8(0x74, 'van')                   # jz  vanilla
    a.db(0x80, 0x78, 0x08, 0x02)        # cmp byte [eax+8], 2 ; Global?
    a.j8(0x75, 'van')                   # jne vanilla         ; human (Local/Remote)
    a.db(0x59)                          # pop ecx             ; Global -> not visible
    a.db(0x5A)                          # pop edx
    a.db(0x58)                          # pop eax
    a.db(0x33, 0xC0)                    # xor eax, eax        ; return False
    a.db(0xC3)                          # ret
    a.label('van')
    a.db(0x59)                          # pop ecx
    a.db(0x5A)                          # pop edx
    a.db(0x58)                          # pop eax
    a.db(0x53)                          # push ebx            ; displaced entry
    a.db(0x56)                          # push esi
    a.db(0x8B, 0xF2)                    # mov esi, edx
    a.db(0x8B, 0xD8)                    # mov ebx, eax
    a.jmp32(H_MVIS + 6)

    a.resolve()
    assert CAVE_BASE + len(a.buf) <= CAVE_LIMIT, "cave overflow %d" % len(a.buf)
    return bytes(a.buf) + bytes(CAVE_LIMIT - CAVE_BASE - len(a.buf)), a.labels


def reloc_check(data, ranges):
    """assert no active .reloc fixup intersects any patched file range"""
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

    site_off = H_MVIS - VA2FILE
    cave_off = CAVE_BASE - VA2FILE
    hits = reloc_check(data, [(site_off, site_off + len(MVIS_OLD)),
                              (cave_off, cave_off + len(cave))])
    if hits:
        print("ABORT: reloc fixups intersect patch ranges: %s" % hits); return 1
    print("  reloc scan    clean")

    cur = bytes(data[cave_off:cave_off + len(cave)])
    cave_new = bytes(len(cave)) if revert else cave
    if cur == cave_new:
        print("  %-14s already %s" % ("cave", "clear" if revert else "applied"))
    elif cur == bytes(len(cave)) or cur[:1] == b'\x50':
        data[cave_off:cave_off + len(cave_new)] = cave_new; dirty = True
        print("  %-14s %s" % ("cave", "clearing" if revert else "ready"))
    else:
        print("  %-14s MISMATCH %s" % ("cave", cur[:8].hex())); ok = False

    new = MVIS_OLD if revert else (
        bytes([0xE9]) + (labels['cave_mvis'] - (H_MVIS + 5)).to_bytes(4, 'little', signed=True)
        + b'\x90' * (len(MVIS_OLD) - 5))
    cur = bytes(data[site_off:site_off + len(MVIS_OLD)])
    if cur == new:
        print("  %-14s already applied" % "MoveVisible")
    elif cur == MVIS_OLD or cur[0] == 0xE9:
        data[site_off:site_off + len(new)] = new; dirty = True
        print("  %-14s ready @0x%X (%d bytes)" % ("MoveVisible", H_MVIS, len(new)))
    else:
        print("  %-14s MISMATCH @0x%X: %s" % ("MoveVisible", H_MVIS, cur.hex())); ok = False

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
