#!/usr/bin/env python3
"""LAN out-of-sync diagnostic v3 (AoWEPACK.dll) - record-only, revertible.

v2 verdict (8/7): TOKEN-ORDERING divergence - both machines generate the SAME
AI move tokens, but they execute at different positions relative to the
network sync token (one machine ran move(7,8,0)+combat BEFORE its sync check,
the other AFTER).  AI runs on all machines ("Global" comm status 2) inside
"capture windows": TAIExecuter.TokenControlDoneEvent fires at token-stream
boundaries and calls CaptureTokenCycles(5) -> TTokenExecuter.Lock; the AI
pump (TAoWHSMap.NewFrame -> TAIExecuter.Process, gated by machine-LOCAL
[map+0x11C]/[map+0x118]/AI-lock [aiexec+0x30]) then works for up to 5 frames;
TokenCyclesCaptured -> Unlock releases the stream.  Candidate divergence
sources: (a) real-time budget mode ([aiexec+0x1A]==1 uses
GetElapsedMilliSeconds), (b) combat-UI-callback-driven AI Lock/Unlock timing,
(c) NewFrame combat gates.  v3 records the window boundaries to see which.

Adds to the v2 ring (same RING @0x558FAA00, reader re_tools/desync_dump.py):
  'CAPT' CaptureTokenCycles entry : val = tok-executed-count(low24) | mode<<24
  'RELS' TokenCyclesCaptured entry: val = same encoding
  'AIUL' TAIExecuter.Unlock entry : val = count(low24) | lockdepth-lowbyte<<24
  'WORK' after each TAIPlayerControl.Process call in the mode-2 pump:
         val = result(low8) | playerIdx<<8
tok-executed-count = [[[map+0x23C]]+4]+0x18 (TTokenExecuter's executed
counter) - places every boundary at an exact token-stream position.
mode = [aiexec+0x1A] (0 = logical/deterministic budget, 1 = REALTIME ms).

v3.1 (after first v3 dump): windows/work were IDENTICAL lockstep, timemode=0
everywhere - the divergence is the ORDER two pending AI moves were pulled at
the same stream position ((44,10,2) vs (7,8,0) swapped).  Added:
  'CREA' CreateArmyMoveTE post-Setup @0x5574A22C: val = first path hex
         (low24) | setup-ok<<24 - records move-token CREATION order.
If CREA order differs across machines -> generation-side iteration
nondeterminism (pointer-ordered container under ASLR); if identical ->
enqueue/fetch side (Network.dpl TTokenControl) is next suspect.

Keeps all v2 hooks (Random/MOVE/SYNC/BOOM) and the H3 reloc neutralization
(entry word @file 0x27DBD0, 0x3D05 -> 0x0D05; see v2 docstring - a live
type-3 fixup inside H3's jmp corrupts it on rebased loads).

Apply AFTER build_desync_diag2.py --revert (script aborts on v2's jmps).
Cave @0x55811000-0x55811300 (zeros; old getbusy cave region reverted).
Dry-run default; --apply / --revert.  Backup AoWEPACK.dll.bak_desync_diag3.
"""
import os
import shutil
import sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
TARGET = os.path.join(GAME, "AoWEPACK.dll")
BACKUP = TARGET + ".bak_desync_diag3"

VA2FILE = 0x55700C00
AOWHSMAP = 0x558FA040
RING     = 0x558FAA00
RINGMASK = 0x7F

TAG_MOVE = 0x4D4F5645
TAG_SYNC = 0x53594E43
TAG_BOOM = 0x424F4F4D
TAG_CAPT = 0x43415054
TAG_RELS = 0x52454C53
TAG_AIUL = 0x4149554C
TAG_WORK = 0x574F524B
TAG_CREA = 0x43524541
TAG_CRE2 = 0x43524532   # follows CREA: value = CreateArmyMoveTE's caller VA

CAVE_BASE  = 0x55811000
CAVE_LIMIT = 0x55811300

H_RANDOM = 0x5577827C
H_MOVE   = 0x557478F2
H_SYNC   = 0x55754D04
H_BOOM   = 0x55754D14
H_CAPT   = 0x5573466C
H_RELS   = 0x557346FC
H_AIUL   = 0x55734608
H_WORK   = 0x557348D7
WORK_JE_TARGET = 0x557348E7   # original je +0x0A destination
H_CREA   = 0x5574A22C
CREA_JNE_TARGET = 0x5574A23B  # original jne +0x0B destination

# .reloc entry covering H_SYNC+1 (imm32 of displaced mov eax,[AoWHSMap])
RELOC_ENTRY_OFF = 0x27DBD0
RELOC_OLD = 0x3D05            # type 3 (HIGHLOW)
RELOC_NEW = 0x0D05            # type 0 (ABSOLUTE) = skipped by loader

OLD = {
    H_RANDOM: bytes.fromhex("53568BF28BD8"),    # push ebx;push esi;mov esi,edx;mov ebx,eax
    H_MOVE:   bytes.fromhex("8B43148B4008"),    # mov eax,[ebx+14h];mov eax,[eax+8]
    H_SYNC:   bytes.fromhex("A140A08F55"),      # mov eax,[AoWHSMap]
    H_BOOM:   bytes.fromhex("5356578BD8"),      # push ebx;push esi;push edi;mov ebx,eax
    H_CAPT:   bytes.fromhex("53568BF28BD8"),    # push ebx;push esi;mov esi,edx;mov ebx,eax
    H_RELS:   bytes.fromhex("538BD8F6431802"),  # push ebx;mov ebx,eax;test [ebx+18h],2
    H_AIUL:   bytes.fromhex("538BD8837B3000"),  # push ebx;mov ebx,eax;cmp dword [ebx+30h],0
    H_WORK:   bytes.fromhex("8BD884DB740A"),    # mov ebx,eax;test bl,bl;je +0x0A
    H_CREA:   bytes.fromhex("84C0750B33F6"),    # test al,al;jne +0x0B;xor esi,esi
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

    # tokcnt: ecx=delta -> edx = TTokenExecuter executed-count & 0xFFFFFF
    # ([[[map+0x23C]]+4]+0x18), 0 if any pointer nil.  Clobbers only edx.
    a.label('tokcnt')
    a.db(0x8B, 0x91); a.dd(AOWHSMAP)    # mov edx,[ecx+AoWHSMap]
    a.db(0x85, 0xD2)                    # test edx, edx
    a.j8(0x74, 'tz')                    # jz  tz
    a.db(0x8B, 0x92); a.dd(0x23C)       # mov edx,[edx+0x23C]  ; token manager
    a.db(0x85, 0xD2)                    # test edx, edx
    a.j8(0x74, 'tz')                    # jz  tz
    a.db(0x8B, 0x52, 0x04)              # mov edx,[edx+4]      ; token executer
    a.db(0x85, 0xD2)                    # test edx, edx
    a.j8(0x74, 'tz')                    # jz  tz
    a.db(0x8B, 0x52, 0x18)              # mov edx,[edx+0x18]   ; executed count
    a.db(0x81, 0xE2); a.dd(0x00FFFFFF)  # and edx, 0xFFFFFF
    a.db(0xC3)                          # ret
    a.label('tz')
    a.db(0x33, 0xD2)                    # xor edx, edx
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

    # H5: CaptureTokenCycles entry.  eax=aiexec, edx=cycles
    a.label('cave_capt')
    a.db(0x50); a.db(0x52); a.db(0x51)  # push eax/edx/ecx
    a.pic_delta_ecx()
    a.call('tokcnt')                    # edx = tok count (low24)
    a.db(0x0F, 0xB6, 0x40, 0x1A)        # movzx eax, byte [eax+1Ah]  ; time mode
    a.db(0xC1, 0xE0, 0x18)              # shl eax, 24
    a.db(0x0B, 0xD0)                    # or  edx, eax
    a.db(0xB8); a.dd(TAG_CAPT)          # mov eax,'CAPT'
    a.call('ring_append')
    a.db(0x59); a.db(0x5A); a.db(0x58)  # pop ecx/edx/eax
    a.db(0x53)                          # push ebx            ; displaced
    a.db(0x56)                          # push esi
    a.db(0x8B, 0xF2)                    # mov esi, edx
    a.db(0x8B, 0xD8)                    # mov ebx, eax
    a.jmp32(H_CAPT + 6)

    # H6: TokenCyclesCaptured entry.  eax=aiexec
    a.label('cave_rels')
    a.db(0x50); a.db(0x52); a.db(0x51)  # push eax/edx/ecx
    a.pic_delta_ecx()
    a.call('tokcnt')
    a.db(0x0F, 0xB6, 0x40, 0x1A)        # movzx eax, byte [eax+1Ah]
    a.db(0xC1, 0xE0, 0x18)              # shl eax, 24
    a.db(0x0B, 0xD0)                    # or  edx, eax
    a.db(0xB8); a.dd(TAG_RELS)          # mov eax,'RELS'
    a.call('ring_append')
    a.db(0x59); a.db(0x5A); a.db(0x58)  # pop ecx/edx/eax
    a.db(0x53)                          # push ebx            ; displaced
    a.db(0x8B, 0xD8)                    # mov ebx, eax
    a.db(0xF6, 0x43, 0x18, 0x02)        # test byte [ebx+18h], 2
    a.jmp32(H_RELS + 7)

    # H7: TAIExecuter.Unlock entry.  eax=aiexec
    a.label('cave_aiul')
    a.db(0x50); a.db(0x52); a.db(0x51)  # push eax/edx/ecx
    a.pic_delta_ecx()
    a.call('tokcnt')
    a.db(0x8B, 0x40, 0x30)              # mov eax,[eax+30h]   ; lock depth (pre-dec)
    a.db(0xC1, 0xE0, 0x18)              # shl eax, 24         ; low byte -> top
    a.db(0x0B, 0xD0)                    # or  edx, eax
    a.db(0xB8); a.dd(TAG_AIUL)          # mov eax,'AIUL'
    a.call('ring_append')
    a.db(0x59); a.db(0x5A); a.db(0x58)  # pop ecx/edx/eax
    a.db(0x53)                          # push ebx            ; displaced
    a.db(0x8B, 0xD8)                    # mov ebx, eax
    a.db(0x83, 0x7B, 0x30, 0x00)        # cmp dword [ebx+30h], 0
    a.jmp32(H_AIUL + 7)

    # H8: mode-2 pump, right after TAIPlayerControl.Process returns.
    # eax=result(byte), ebp=TAIExecuter.Process frame ([ebp-4]=aiexec)
    a.label('cave_work')
    a.db(0x50); a.db(0x52); a.db(0x51)  # push eax/edx/ecx
    a.pic_delta_ecx()
    a.db(0x8B, 0xD0)                    # mov edx, eax        ; result
    a.db(0x81, 0xE2); a.dd(0xFF)        # and edx, 0xFF
    a.db(0x8B, 0x45, 0xFC)              # mov eax,[ebp-4]     ; aiexec
    a.db(0x0F, 0xB6, 0x40, 0x10)        # movzx eax, byte [eax+10h] ; player idx
    a.db(0xC1, 0xE0, 0x08)              # shl eax, 8
    a.db(0x0B, 0xD0)                    # or  edx, eax
    a.db(0xB8); a.dd(TAG_WORK)          # mov eax,'WORK'
    a.call('ring_append')
    a.db(0x59); a.db(0x5A); a.db(0x58)  # pop ecx/edx/eax
    a.db(0x8B, 0xD8)                    # mov ebx, eax        ; displaced
    a.db(0x84, 0xDB)                    # test bl, bl
    a.je32(WORK_JE_TARGET)              # je  (re-encoded rel32)
    a.jmp32(H_WORK + 6)

    # H9: CreateArmyMoveTE post-Setup.  ebx=TE (path set up), al=setup ok
    a.label('cave_crea')
    a.db(0x50); a.db(0x52); a.db(0x51)  # push eax/edx/ecx
    a.pic_delta_ecx()
    a.db(0x8B, 0x53, 0x14)              # mov edx,[ebx+14h]   ; path TXYLList
    a.db(0x85, 0xD2)                    # test edx, edx
    a.j8(0x74, 'cz')                    # jz  cz
    a.db(0x8B, 0x42, 0x04)              # mov eax,[edx+4]     ; data ptr
    a.db(0x85, 0xC0)                    # test eax, eax
    a.j8(0x74, 'cz')                    # jz  cz
    a.db(0x8B, 0x10)                    # mov edx,[eax]       ; first XYL
    a.j8(0xEB, 'ch')                    # jmp ch
    a.label('cz')
    a.db(0x33, 0xD2)                    # xor edx, edx
    a.label('ch')
    a.db(0x81, 0xE2); a.dd(0x00FFFFFF)  # and edx, 0xFFFFFF
    a.db(0x8B, 0x44, 0x24, 0x08)        # mov eax,[esp+8]     ; original eax (al=ok)
    a.db(0x25); a.dd(0xFF)              # and eax, 0xFF
    a.db(0xC1, 0xE0, 0x18)              # shl eax, 24
    a.db(0x0B, 0xD0)                    # or  edx, eax
    a.db(0xB8); a.dd(TAG_CREA)          # mov eax,'CREA'
    a.call('ring_append')
    a.db(0x8B, 0x55, 0x04)              # mov edx,[ebp+4]     ; caller retaddr
    a.db(0xB8); a.dd(TAG_CRE2)          # mov eax,'CRE2'
    a.call('ring_append')
    a.db(0x59); a.db(0x5A); a.db(0x58)  # pop ecx/edx/eax
    a.db(0x84, 0xC0)                    # test al, al         ; displaced
    a.db(0x0F, 0x85); a._r(CREA_JNE_TARGET)  # jne (re-encoded rel32)
    a.db(0x33, 0xF6)                    # xor esi, esi
    a.jmp32(H_CREA + 6)

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
                          ("H4 OutOfSync", H_BOOM, 'cave_boom'),
                          ("H5 Capture", H_CAPT, 'cave_capt'),
                          ("H6 Release", H_RELS, 'cave_rels'),
                          ("H7 AIUnlock", H_AIUL, 'cave_aiul'),
                          ("H8 Work", H_WORK, 'cave_work'),
                          ("H9 Create", H_CREA, 'cave_crea')):
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
