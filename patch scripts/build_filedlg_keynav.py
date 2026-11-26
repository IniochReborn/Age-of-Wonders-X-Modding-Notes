#!/usr/bin/env python3
r"""Arrow-key navigation in the map-select / load / save dialog.

The scenario-select, load-game and save-game windows are all TFileDlgWindow
(AoWx.exe), whose file list FileLB is a TAOWListBox from aowInt.dpl. The AoW
toolkit has a full keyboard pipeline: TAOWWinManager dispatches each key to
every visible window (virtual slot 37 / VMT+0x94, args eax=self, edx=&VK word,
cl=shift), TAOWWindowControl @0x59804B80 forwards it to every child control,
and a control claims the key by setting its +0x78 flag. TAOWEdit overrides
slot 37 (caret movement); TAOWListBox does not - arrow keys just fall through.

This patch gives TAOWListBox a key handler by repointing its VMT slot 37
(0x59816030, currently the inherited TAOWControl stub 0x598030A8) at a cave.
The VMT slot has a .reloc entry, which is kept: it rebases our cave pointer
exactly like the old one. The cave itself is fully position-independent
(register-relative field access + rel32 intra-module calls), so no load-delta
is needed.

To avoid hijacking arrows from every listbox in the game (unit panels etc.),
the cave only acts when the hosted listbox's OnChange handler (+0x6C) is
TFileDlgWindow.FileLBChange @0x004201EC - i.e. exactly FileLB in the file
dialog. AoWx.exe is a Delphi image with no .reloc, always loaded at 0x400000,
so the address identifies the handler reliably (same trick as the leader-face
buttons in build_wheel_aowint.py). The script re-derives that address from
AoWx.exe's published-method table ("FileLBChange") and refuses to patch on
mismatch.

Keys (clamped to the list, only when the dialog is open and the list visible):
  Up/Down     select previous / next map or save
  PgUp/PgDn   jump a page ([lb+0x11C] = visible rows)
  Home/End    first / last entry

Selection change mimics a mouse click exactly: set [lb+0x120], dirty the
control (+0xA4=0), fire OnChange (updates the info panel / filename edit via
FileLBChange), then scroll the row into view by driving the dialog's shared
scrollbar ([lb+0x118]: SetFPos @0x5980CA28 + its OnChange = mSBarChange, which
keeps the parallel date/size columns in sync) and TAOWListBox.Update
@0x59817138. The key is claimed (+0x78=-1) so it never leaks to global
hotkeys while the dialog is open.

TAOWListBox field map (recovered from click handler @0x598171C4 and Update):
  +0x6C/+0x6E/+0x70 OnChange method ptr (code/hiword-check/self)
  +0x75 Visible  +0x78 input-claim flag  +0xA4 painted flag (0 = repaint)
  +0x114 items (virtual +0x14 = Count)   +0x118 linked TAOWVScrollBar
  +0x11C visible rows  +0x120 selected index  +0x15C top-item offset

Backup: aowInt.dpl.bak_keynav. Dry-run default; --apply / --revert.
"""
import os, shutil, struct, sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DPL = os.path.join(GAME, "aowInt.dpl")
EXE = os.path.join(GAME, "AoWx.exe")
BAK = DPL + ".bak_keynav"

CODE_OFF = 0x59800C00          # CODE: file = VA - this

VMT_SLOT37 = 0x59816030        # TAOWListBox VMT 0x59815F9C + 37*4
SLOT_OLD   = 0x598030A8        # inherited TAOWControl key stub

CAVE, CAVE_END = 0x59823A00, 0x59823D00   # CODE tail zeros (wheel + pwrslider
                                          # caves end ~0x59823963, zeros to 0x5983D000)

F_SETFPOS    = 0x5980CA28      # TAOWScrollBar.SetFPos(eax=self, edx=pos), clamps
F_SETLISTOFF = 0x598168F4      # TAOWListBox.SetListOff(eax=self, edx=off), clamps
F_UPDATE     = 0x59817138      # TAOWListBox.Update(eax=self)

# AoWx.exe (no .reloc, fixed base 0x400000): TFileDlgWindow.FileLBChange.
# ⚠ COUPLED TO AoWx.exe: verified below against its published-method table.
FILELB_CHANGE = 0x004201EC

VK_PRIOR, VK_NEXT, VK_END, VK_HOME, VK_UP, VK_DOWN = 0x21, 0x22, 0x23, 0x24, 0x26, 0x28


class Asm:
    def __init__(self, base):
        self.base = base; self.buf = bytearray(); self.rel = []
        self.labels = {}; self.j8 = []; self.j32 = []
    def here(self): return self.base + len(self.buf)
    def db(self, *b): self.buf += bytes(b)
    def dd(self, v): self.buf += (v & 0xFFFFFFFF).to_bytes(4, 'little')
    def call(self, t): self.db(0xE8); self.rel.append((len(self.buf), t)); self.dd(0)
    def lab(self, n): self.labels[n] = len(self.buf)
    def jcc8(self, op, n): self.db(op); self.j8.append((len(self.buf), n)); self.db(0)
    def jcc32(self, op, n):
        self.db(0x0F, op); self.j32.append((len(self.buf), n)); self.dd(0)
    def jmp32(self, n):
        self.db(0xE9); self.j32.append((len(self.buf), n)); self.dd(0)
    def fin(self):
        for off, t in self.rel:
            self.buf[off:off+4] = (t - (self.base + off + 4)).to_bytes(4, 'little', signed=True)
        for off, n in self.j8:
            d = self.labels[n] - (off + 1)
            assert -128 <= d <= 127, (n, d)
            self.buf[off] = d & 0xFF
        for off, n in self.j32:
            self.buf[off:off+4] = (self.labels[n] - (off + 4)).to_bytes(4, 'little', signed=True)
        return bytes(self.buf)


def build_keynav():
    """TAOWListBox key handler (VMT slot 37): eax=lb, edx=&key word, cl=shift."""
    a = Asm(CAVE)
    a.db(0x53, 0x56, 0x57)                      # push ebx/esi/edi
    a.db(0x8B, 0xD8)                            # mov ebx,eax (lb)
    a.db(0x8B, 0xF2)                            # mov esi,edx (&key)
    a.db(0x33, 0xC0)                            # xor eax,eax
    a.db(0x89, 0x43, 0x78)                      # mov [ebx+0x78],eax (not handled)
    a.db(0x81, 0x7B, 0x6C); a.dd(FILELB_CHANGE) # cmp [ebx+0x6C],FileLBChange
    a.jcc32(0x85, 'done')                       # jne: not the file dialog's list
    a.db(0x80, 0x7B, 0x75, 0x01)                # cmp byte [ebx+0x75],1 (Visible)
    a.jcc32(0x85, 'done')
    # ---- sibling dedup: the load/save view has TWO columns (SaveLB + DateLB
    # in frame SaveLBFr) both bound to FileLBChange, and the window dispatcher
    # forwards each key to every child - without this, one press moved the
    # selection twice. Only the highest-index gated visible listbox among the
    # parent's children (the first one dispatched) may act; FileLBChange's
    # SetIndex sync keeps the other column aligned. ----
    a.db(0x8B, 0x83); a.dd(0x10C)               # mov eax,[ebx+0x10C] (parent)
    a.db(0x85, 0xC0)
    a.jcc8(0x74, 'act')                         # no parent: act
    a.db(0x8B, 0x80); a.dd(0xD0)                # mov eax,[eax+0xD0] (children)
    a.db(0x85, 0xC0)
    a.jcc8(0x74, 'act')
    a.db(0x8B, 0x48, 0x08)                      # mov ecx,[eax+8] (count)
    a.db(0x8B, 0x78, 0x04)                      # mov edi,[eax+4] (data)
    a.lab('scan')                               # highest index first
    a.db(0x49)                                  # dec ecx
    a.jcc8(0x78, 'act')                         # js: none found -> act
    a.db(0x8B, 0x04, 0x8F)                      # mov eax,[edi+ecx*4]
    a.db(0x85, 0xC0)
    a.jcc8(0x74, 'scan')
    a.db(0x81, 0x78, 0x6C); a.dd(FILELB_CHANGE) # gated sibling?
    a.jcc8(0x75, 'scan')
    a.db(0x80, 0x78, 0x75, 0x01)                # visible?
    a.jcc8(0x75, 'scan')
    a.db(0x3B, 0xC3)                            # cmp eax,ebx
    a.jcc32(0x85, 'done')                       # a sibling outranks us: skip
    a.lab('act')
    a.db(0x8B, 0x83); a.dd(0x114)               # mov eax,[ebx+0x114] (items)
    a.db(0x8B, 0x10)                            # mov edx,[eax]
    a.db(0xFF, 0x52, 0x14)                      # call [edx+0x14] -> eax=Count
    a.db(0x85, 0xC0)                            # test eax,eax
    a.jcc32(0x8E, 'done')                       # jle: empty list
    a.db(0x8B, 0xF8)                            # mov edi,eax (count)
    a.db(0x8B, 0x93); a.dd(0x120)               # mov edx,[ebx+0x120] (sel)
    a.db(0x0F, 0xB7, 0x0E)                      # movzx ecx,word [esi] (key)
    a.db(0x83, 0xF9, VK_UP);    a.jcc8(0x74, 'up')
    a.db(0x83, 0xF9, VK_DOWN);  a.jcc8(0x74, 'down')
    a.db(0x83, 0xF9, VK_PRIOR); a.jcc8(0x74, 'pgup')
    a.db(0x83, 0xF9, VK_NEXT);  a.jcc8(0x74, 'pgdn')
    a.db(0x83, 0xF9, VK_HOME);  a.jcc8(0x74, 'home')
    a.db(0x83, 0xF9, VK_END);   a.jcc8(0x74, 'endk')
    a.jmp32('done')                             # any other key: not ours
    a.lab('up');   a.db(0x4A); a.jcc8(0xEB, 'clamp')          # dec edx
    a.lab('down'); a.db(0x42); a.jcc8(0xEB, 'clamp')          # inc edx
    a.lab('pgup')
    a.db(0x2B, 0x93); a.dd(0x11C)               # sub edx,[ebx+0x11C] (vis rows)
    a.db(0x42); a.jcc8(0xEB, 'clamp')           # inc edx (page-1 keeps context)
    a.lab('pgdn')
    a.db(0x03, 0x93); a.dd(0x11C)               # add edx,[ebx+0x11C]
    a.db(0x4A); a.jcc8(0xEB, 'clamp')           # dec edx
    a.lab('home'); a.db(0x33, 0xD2); a.jcc8(0xEB, 'clamp')    # xor edx,edx
    a.lab('endk'); a.db(0x8D, 0x57, 0xFF)                     # lea edx,[edi-1]
    a.lab('clamp')
    a.db(0x85, 0xD2)                            # test edx,edx
    a.jcc8(0x79, 'c1')                          # jns
    a.db(0x33, 0xD2)                            # edx = 0
    a.lab('c1')
    a.db(0x3B, 0xD7)                            # cmp edx,edi
    a.jcc8(0x7C, 'c2')                          # jl
    a.db(0x8D, 0x57, 0xFF)                      # edx = count-1
    a.lab('c2')
    a.db(0xC7, 0x43, 0x78); a.dd(0xFFFFFFFF)    # mov [ebx+0x78],-1 (claim key)
    a.db(0x3B, 0x93); a.dd(0x120)               # cmp edx,[ebx+0x120]
    a.jcc32(0x84, 'done')                       # je: selection unchanged
    a.db(0x89, 0x93); a.dd(0x120)               # mov [ebx+0x120],edx
    a.db(0xC6, 0x83); a.dd(0xA4); a.db(0x00)    # mov byte [ebx+0xA4],0 (repaint)
    a.db(0x52)                                  # push edx (new sel)
    a.db(0x8B, 0x43, 0x70)                      # mov eax,[ebx+0x70] (handler Self)
    a.db(0x8B, 0xD3)                            # mov edx,ebx (Sender=lb)
    a.db(0xFF, 0x53, 0x6C)                      # call [ebx+0x6C] = FileLBChange
    a.db(0x5A)                                  # pop edx (new sel)
    # ---- scroll the new row into view ----
    a.db(0x8B, 0x8B); a.dd(0x15C)               # mov ecx,[ebx+0x15C] (top off)
    a.db(0x3B, 0xD1)                            # cmp edx,ecx
    a.jcc8(0x7C, 'tnew')                        # jl: above the window -> top=new
    a.db(0x8B, 0xC1)                            # mov eax,ecx
    a.db(0x03, 0x83); a.dd(0x11C)               # add eax,[ebx+0x11C]
    a.db(0x3B, 0xD0)                            # cmp edx,eax
    a.jcc8(0x7C, 'repaint')                     # jl: already visible
    a.db(0x8B, 0xCA)                            # mov ecx,edx
    a.db(0x2B, 0x8B); a.dd(0x11C)               # sub ecx,[ebx+0x11C]
    a.db(0x41)                                  # inc ecx (top = new-vis+1)
    a.jcc8(0xEB, 'have')
    a.lab('tnew')
    a.db(0x8B, 0xCA)                            # mov ecx,edx
    a.lab('have')                               # ecx = wanted top offset
    a.db(0x8B, 0x83); a.dd(0x118)               # mov eax,[ebx+0x118] (scrollbar)
    a.db(0x85, 0xC0)                            # test eax,eax
    a.jcc8(0x74, 'nosb')
    a.db(0x8B, 0xD1)                            # mov edx,ecx
    a.call(F_SETFPOS)                           # SetFPos(sb, top) - clamps
    a.db(0x8B, 0x93); a.dd(0x118)               # mov edx,[ebx+0x118] (Sender=sb)
    a.db(0x66, 0x83, 0x7A, 0x6E, 0x00)          # cmp word [edx+0x6E],0
    a.jcc8(0x74, 'repaint')                     # OnChange unassigned
    a.db(0x8B, 0x42, 0x70)                      # mov eax,[edx+0x70] (Self)
    a.db(0xFF, 0x52, 0x6C)                      # call [edx+0x6C] = mSBarChange
    a.jcc8(0xEB, 'repaint')
    a.lab('nosb')
    a.db(0x8B, 0xC3)                            # mov eax,ebx
    a.db(0x8B, 0xD1)                            # mov edx,ecx
    a.call(F_SETLISTOFF)                        # no scrollbar: move offset direct
    a.lab('repaint')
    a.db(0x8B, 0xC3)                            # mov eax,ebx
    a.call(F_UPDATE)                            # TAOWListBox.Update
    a.lab('done')
    a.db(0x5F, 0x5E, 0x5B)                      # pop edi/esi/ebx
    a.db(0xC3)                                  # ret
    return a.fin()


def reloc_entries(data, ranges):
    """File offsets of reloc-adjusted dwords intersecting ranges [(lo,hi)...]."""
    e = struct.unpack_from('<I', data, 0x3C)[0]; opt = e + 24
    nsec = struct.unpack_from('<H', data, e + 6)[0]
    osz = struct.unpack_from('<H', data, e + 20)[0]
    rrva, rsz = struct.unpack_from('<II', data, opt + 96 + 5*8)
    secs = []; p = opt + osz
    for _ in range(nsec):
        vs, va, rs, raw = struct.unpack_from('<IIII', data, p + 8)
        secs.append((va, vs, raw, rs)); p += 40
    def r2o(rva):
        for va, vs, raw, rs in secs:
            if va <= rva < va + max(vs, rs): return raw + rva - va
    off = r2o(rrva)
    if off is None or not rsz: return []
    end = off + rsz; hits = []
    while off < end:
        page, blk = struct.unpack_from('<II', data, off)
        if blk < 8: break
        for i in range((blk - 8)//2):
            w = struct.unpack_from('<H', data, off + 8 + i*2)[0]
            if w >> 12 == 0: continue
            fo = r2o(page + (w & 0xFFF))
            if fo is None: continue
            for lo, hi in ranges:
                if lo <= fo + 3 and fo < hi: hits.append(fo)
        off += blk
    return hits


def verify_filelbchange():
    """Re-derive FileLBChange from AoWx.exe's published-method table."""
    d = open(EXE, 'rb').read()
    # The name also appears in the three form-stream resources (OnChange
    # bindings for the scenario/load/save dialog variants); the method-table
    # entry is the one preceded by a code address.
    key = b'\x0cFileLBChange'
    cands = []
    i = -1
    while True:
        i = d.find(key, i + 1)
        if i < 0: break
        v = struct.unpack_from('<I', d, i - 4)[0]
        if 0x401000 <= v < 0x460000:
            cands.append(v)
    assert len(cands) == 1, ("FileLBChange table entry not unique", cands)
    addr = cands[0]
    assert addr == FILELB_CHANGE, (
        "FileLBChange moved: table says 0x%X, patch built for 0x%X" % (addr, FILELB_CHANGE))
    # sanity: it must start with a normal prologue (push ebp; mov ebp,esp)
    fo = addr - 0x400000 + 0xC00   # CODE raw 0x400... derive via headers instead
    # AoWx.exe CODE section: find offset properly
    e = struct.unpack_from('<I', d, 0x3C)[0]; opt = e + 24
    nsec = struct.unpack_from('<H', d, e + 6)[0]
    osz = struct.unpack_from('<H', d, e + 20)[0]
    p = opt + osz
    fo = None
    for _ in range(nsec):
        vs, va, rs, raw = struct.unpack_from('<IIII', d, p + 8)
        rva = addr - 0x400000
        if va <= rva < va + max(vs, rs):
            fo = raw + rva - va; break
        p += 40
    assert fo is not None and d[fo:fo+3] == b'\x55\x8b\xec', "unexpected FileLBChange body"


def main():
    apply = "--apply" in sys.argv; revert = "--revert" in sys.argv
    if revert:
        if os.path.exists(BAK):
            shutil.copy2(BAK, DPL); print("restored aowInt.dpl"); return 0
        print("no backup"); return 1

    verify_filelbchange()
    d = bytearray(open(DPL, 'rb').read())
    blob = build_keynav()
    assert CAVE + len(blob) <= CAVE_END, hex(len(blob))

    slot_off = VMT_SLOT37 - CODE_OFF
    cave_off = CAVE - CODE_OFF

    # cave must be reloc-free; the VMT slot must keep its existing reloc entry
    # (it rebases our cave pointer on a rebased load, same as the old value).
    hits = reloc_entries(bytes(d), [(cave_off, cave_off + len(blob))])
    assert not hits, [hex(x) for x in hits]
    slot_relocs = reloc_entries(bytes(d), [(slot_off, slot_off + 4)])
    assert slot_relocs == [slot_off], ("VMT slot reloc missing/odd", slot_relocs)

    cur = struct.unpack_from('<I', d, slot_off)[0]
    assert cur in (SLOT_OLD, CAVE), hex(cur)
    seg = bytes(d[cave_off:cave_off + len(blob)])
    assert seg == bytes(len(blob)) or seg[:3] == b'\x53\x56\x57', seg[:8].hex()

    d[cave_off:cave_off + len(blob)] = blob
    struct.pack_into('<I', d, slot_off, CAVE)

    print("aowInt: KeyNav %dB @0x%X; TAOWListBox VMT slot37 0x%X -> cave"
          % (len(blob), CAVE, VMT_SLOT37))
    if not apply:
        print("Dry run OK — rerun with --apply (or --revert)."); return 0
    if not os.path.exists(BAK):
        shutil.copy2(DPL, BAK); print("Backup ->", os.path.basename(BAK))
    open(DPL, 'wb').write(d)
    print("Written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
