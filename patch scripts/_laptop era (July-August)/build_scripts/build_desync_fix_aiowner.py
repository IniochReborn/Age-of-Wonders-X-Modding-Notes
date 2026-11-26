#!/usr/bin/env python3
"""LAN out-of-sync FIX #2 (AoWEPACK.dll): AI pump must not command armies it
no longer owns.

DIAG v4 verdict (8/9, repro #5): the recurring divergent move (44,10,2) is
the recruited mole army - post-recruit its owner is a HUMAN player (ANIM
owner=1), yet TAIMoveExecuter.ProcessExecuteMoves still issues moves for it
from a STALE AI move queue planned before the recruit (RetrieveArmy fetches
whatever army sits on the stored hex; TAIMoveExecuterUnit.Validate checks
unit existence, never ownership - a vanilla bug).  Human-owned army moves
are exempt from fix #1's no-animation gate (by design), so the AI-issued
move of the recruited army animates on the watching machine, the token
spans frames, its synced Random draw lands at different stream positions,
and the sync check fails.  STAT fingerprints (busy/combat/event-log) were
identical on both machines - all other suspects exonerated.

FIX: in NETWORK games (mode byte [map+0x239]==2), the AI pump refuses to
issue a move for an army whose owner's communication status is not Global
(2).  Two call-site hooks inside TAIMoveExecuter.ProcessExecuteMoves ONLY
(the human-UI caller TSelectedArmy.ExecuteMove -> MoveArmy is untouched):
  A) single-move path @0x557428B2  `call AoWE.MoveArmy` -> cave: foreign
     owner => return AL=0 (pump handles it as a normal move failure:
     SetUnitStatus 6, executer state 2 -> group replans), else tail-jmp
     MoveArmy.
  B) multi-move path @0x557427D1  `test al,al; je skip; xor ecx,ecx` ->
     cave: RetrieveArmy failed OR foreign owner => take the original skip
     branch (0x5574284A), else fall through (xor ecx,ecx; resume 0x557427D7).
Owner lookup identical to fix #1: army=[armyHS+0x1C], owner byte +0x12,
rec=TPlayerCommunicationControl.GetPlayers(pcc=[[map+0x240]+0x1C], owner)
via import thunk @0x557035DC, status=[rec+8].  All pointers nil-checked ->
vanilla.  SP/hotseat untouched (mode gate).  Side effect: also fixes the
visible vanilla quirk of freshly-recruited units wandering under AI orders
(in network games).

PIC cave @0x55812100-0x55812200 (fix #1 cave @0x55812000 stays).  Reloc
scan built in.  Backup AoWEPACK.dll.bak_aiowner.  Dry-run; --apply/--revert.
"""
import os
import shutil
import struct
import sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
TARGET = os.path.join(GAME, "AoWEPACK.dll")
BACKUP = TARGET + ".bak_aiowner"

VA2FILE = 0x55700C00
AOWHSMAP = 0x558FA040

CAVE_BASE  = 0x55812100
CAVE_LIMIT = 0x55812200

MOVEARMY = 0x5574A478
GETPLAYERS_THUNK = 0x557035DC

H_SINGLE = 0x557428B2             # call MoveArmy (5 bytes)
SINGLE_OLD = bytes.fromhex("E8C17B0000")
H_MULTI = 0x557427D1              # test al,al; je +0x75; xor ecx,ecx (6 bytes)
MULTI_OLD = bytes.fromhex("84C0747533C9")
MULTI_SKIP = 0x5574284A           # original je target (skip this move)
MULTI_CONT = 0x557427D7           # after displaced xor ecx,ecx


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


def owner_check(a, sfx, army_slot_off, foreign_lab):
    """emit: regs saved (eax,edx,ecx pushed), armyHS at [esp+army_slot_off].
    Jumps to foreign_lab if network game && owner comm status != Global.
    Falls through = allow (vanilla).  Clobbers eax/ecx/edx."""
    a.pic_delta_ecx()                       # ecx = delta
    a.db(0x8B, 0x91); a.dd(AOWHSMAP)        # mov edx,[ecx+AoWHSMap]
    a.db(0x85, 0xD2)                        # test edx, edx
    a.j8(0x74, 'allow' + sfx)               # jz  allow
    a.db(0x80, 0xBA); a.dd(0x239); a.db(0x02)  # cmp byte [edx+0x239], 2
    a.j8(0x75, 'allow' + sfx)               # jne allow (not network)
    a.db(0x8B, 0x8A); a.dd(0x240)           # mov ecx,[edx+0x240]
    a.db(0x85, 0xC9)
    a.j8(0x74, 'allow' + sfx)
    a.db(0x8B, 0x49, 0x1C)                  # mov ecx,[ecx+0x1C]  ; pcc
    a.db(0x85, 0xC9)
    a.j8(0x74, 'allow' + sfx)
    a.db(0x8B, 0x44, 0x24, army_slot_off)   # mov eax,[esp+off]   ; armyHS
    a.db(0x85, 0xC0)
    a.j8(0x74, 'allow' + sfx)
    a.db(0x8B, 0x40, 0x1C)                  # mov eax,[eax+0x1C]  ; army
    a.db(0x85, 0xC0)
    a.j8(0x74, 'allow' + sfx)
    a.db(0x0F, 0xBE, 0x50, 0x12)            # movsx edx, byte [eax+0x12]
    a.db(0x8B, 0xC1)                        # mov eax, ecx        ; pcc
    a.call(GETPLAYERS_THUNK)                # GetPlayers(pcc, idx)
    a.db(0x85, 0xC0)
    a.j8(0x74, 'allow' + sfx)               # nil rec -> vanilla
    a.db(0x80, 0x78, 0x08, 0x02)            # cmp byte [eax+8], 2 ; Global?
    a.j8(0x75, foreign_lab)                 # jne FOREIGN
    a.label('allow' + sfx)


def build_cave():
    a = Asm(CAVE_BASE)

    # Hook A: replaces `call MoveArmy` in the single-move path.
    # entry: eax=armyHS, dl=sel, ecx=path; [esp]=return into pump
    a.label('cave_single')
    a.db(0x50)                              # push eax
    a.db(0x52)                              # push edx
    a.db(0x51)                              # push ecx
    owner_check(a, '1', 0x08, 'foreign1')   # armyHS at [esp+8]
    a.db(0x59)                              # pop ecx   (allow: vanilla call)
    a.db(0x5A)                              # pop edx
    a.db(0x58)                              # pop eax
    a.jmp32(MOVEARMY)                       # tail-jmp; rets to pump
    a.label('foreign1')
    a.db(0x59)                              # pop ecx
    a.db(0x5A)                              # pop edx
    a.db(0x58)                              # pop eax
    a.db(0x33, 0xC0)                        # xor eax, eax  ; AL=0 move failed
    a.db(0xC3)                              # ret to pump

    # Hook B: replaces `test al,al; je skip; xor ecx,ecx` in the multi path.
    # al = RetrieveArmy ok; pump frame: sel@[esp+4], armyHS@[esp+8]
    a.label('cave_multi')
    a.db(0x84, 0xC0)                        # test al, al
    a.j8(0x74, 'skip2')                     # jz  skip (RetrieveArmy failed)
    a.db(0x50)                              # push eax
    a.db(0x52)                              # push edx
    a.db(0x51)                              # push ecx
    owner_check(a, '2', 0x14, 'foreign2')   # armyHS at [esp+8+0xC]
    a.db(0x59)                              # pop ecx   (allow)
    a.db(0x5A)                              # pop edx
    a.db(0x58)                              # pop eax
    a.db(0x33, 0xC9)                        # xor ecx, ecx  ; displaced instr
    a.jmp32(MULTI_CONT)                     # resume fall-through
    a.label('foreign2')
    a.db(0x59)                              # pop ecx
    a.db(0x5A)
    a.db(0x58)
    a.label('skip2')
    a.jmp32(MULTI_SKIP)                     # original je target

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

    s_off = H_SINGLE - VA2FILE
    m_off = H_MULTI - VA2FILE
    c_off = CAVE_BASE - VA2FILE
    hits = reloc_check(data, [(s_off, s_off + len(SINGLE_OLD)),
                              (m_off, m_off + len(MULTI_OLD)),
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

    for name, va, old, lab in (
            ("A single-move", H_SINGLE, SINGLE_OLD, 'cave_single'),
            ("B multi-move", H_MULTI, MULTI_OLD, 'cave_multi')):
        if name.startswith("A"):
            new = old if revert else (
                bytes([0xE8]) + (labels[lab] - (va + 5)).to_bytes(4, 'little', signed=True))
        else:
            new = old if revert else (
                bytes([0xE9]) + (labels[lab] - (va + 5)).to_bytes(4, 'little', signed=True)
                + b'\x90' * (len(old) - 5))
        off = va - VA2FILE
        cur = bytes(data[off:off + len(old)])
        if cur == new:
            print("  %-14s already applied" % name)
        elif cur == old or cur[0] in (0xE8, 0xE9):
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
