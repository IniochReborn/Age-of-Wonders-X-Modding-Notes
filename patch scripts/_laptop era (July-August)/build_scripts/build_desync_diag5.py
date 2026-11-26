#!/usr/bin/env python3
"""LAN out-of-sync diagnostic v5 (AoWEPACK.dll) - record-only, revertible.

Repro #7 (8/9 1:23 PM, fixes #1+#2+#3 all verified loaded): STILL OOS.
tc_dump of the frozen pair: both executers at executed-count=544, but
machine A held a pending TArmyDefaultMoveTE first-hex=(75,82,0) in
player 4's (comm=Global!) token control - machine B held nothing.  A
one-sided token for a GLOBAL owner, which fix #3 (Remote-owner gate at
MoveArmyEx entry) cannot address by design -> fix #3 reverted 1:40 PM.

The open question is WHO creates these one-sided moves.  The CRE2 probe
records CreateArmyMoveTE's return address, which for funneled calls lands
INSIDE MoveArmyEx (+0x126) and cannot distinguish MoveArmyEx's callers:
MoveArmy wrapper (AI pump / human UI), MoveArmyXYL+0xAF,
TSelectedArmy.ExecuteMove+0x14B, TTeleport.Teleport+0x1B0,
TCave.EnterEx+0x1F8.  (Direct CreateArmyMoveTE callers - TCave.EnterEx
+0x1aa, TTeleport.Teleport+0x15d, TNegotiateTE.Accept/Reject,
TArmyCombatMoveTE.RequestCombatTypeCallBack, CreateArmyMoveXYLTE - already
show distinct CRE2 values.)

v5 = all v4 hooks + H12 at MoveArmyEx entry @0x5574A318 (site vacated by
the fix #3 revert; same displaced bytes 55 8BEC 51 53 56, resume
0x5574A31E):
  'CRE3' val = MoveArmyEx's return address (its true caller)
  'CRE4' val = [esp+0xC] at entry = one dword above the two stack args:
         when the direct caller is a thin wrapper (MoveArmy), this is the
         GRANDPARENT return address; otherwise caller-frame noise - the
         decoder symbolizes it and the reader judges.
Sequence per creation: CRE3 -> CRE4 -> (inside) CREA -> CRE2.  A CRE3
with no CREA after it = MoveArmyEx bailed without creating.

Apply AFTER build_desync_diag4.py --revert (fix caves #1 @0x55812000 and
#2 @0x55812100 untouched, stay applied).  Keeps H3 reloc neutralization.
Cave @0x55811000-0x55811500.  Dry-run default; --apply / --revert.
Backup AoWEPACK.dll.bak_desync_diag5.
Reader: re_tools/desync_dump.py (v5 tags added).
"""
import os
import shutil
import struct
import sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
TARGET = os.path.join(GAME, "AoWEPACK.dll")
BACKUP = TARGET + ".bak_desync_diag5"

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
TAG_CRE2 = 0x43524532
TAG_CRE3 = 0x43524533
TAG_CRE4 = 0x43524534
TAG_ANIM = 0x414E494D
TAG_ELOG = 0x454C4F47
TAG_STAT = 0x53544154

CAVE_BASE  = 0x55811000
CAVE_LIMIT = 0x55811500

H_RANDOM = 0x5577827C
H_MOVE   = 0x557478F2
H_SYNC   = 0x55754D04
H_BOOM   = 0x55754D14
H_CAPT   = 0x5573466C
H_RELS   = 0x557346FC
H_AIUL   = 0x55734608
H_WORK   = 0x557348D7
WORK_JE_TARGET = 0x557348E7
H_CREA   = 0x5574A22C
CREA_JNE_TARGET = 0x5574A23B
H_ANIM   = 0x55792084          # TArmyHS.MoveFirst entry
H_ELOG   = 0x5577653C          # TAoWHSMap.SetExecuteEventLogDelay entry
H_CRE3   = 0x5574A318          # MoveArmyEx entry (fix #3's vacated site)
CRE3_RESUME = 0x5574A31E

RELOC_ENTRY_OFF = 0x27DBD0
RELOC_OLD = 0x3D05
RELOC_NEW = 0x0D05

OLD = {
    H_RANDOM: bytes.fromhex("53568BF28BD8"),
    H_MOVE:   bytes.fromhex("8B43148B4008"),
    H_SYNC:   bytes.fromhex("A140A08F55"),
    H_BOOM:   bytes.fromhex("5356578BD8"),
    H_CAPT:   bytes.fromhex("53568BF28BD8"),
    H_RELS:   bytes.fromhex("538BD8F6431802"),
    H_AIUL:   bytes.fromhex("538BD8837B3000"),
    H_WORK:   bytes.fromhex("8BD884DB740A"),
    H_CREA:   bytes.fromhex("84C0750B33F6"),
    H_ANIM:   bytes.fromhex("53565783C4EC"),    # push ebx/esi/edi; add esp,-14h
    H_ELOG:   bytes.fromhex("8B88DC010000"),    # mov ecx,[eax+1DCh]
    H_CRE3:   bytes.fromhex("558BEC515356"),    # push ebp;mov ebp,esp;push ecx/ebx/esi
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
        self.db(0x59)
        self.db(0x81, 0xE9); self.dd(popva)
    def seed_to_edx(self, suffix):
        self.db(0x8B, 0x91); self.dd(AOWHSMAP)
        self.db(0x85, 0xD2)
        self.j8(0x74, 'z' + suffix)
        self.db(0x8B, 0x92); self.dd(0x230)
        self.j8(0xEB, 'h' + suffix)
        self.label('z' + suffix)
        self.db(0x33, 0xD2)
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

    # ring_append: ecx=delta, eax=val1, edx=val2; preserves ebx/esi/edi/ecx/eax/edx
    a.label('ring_append')
    a.db(0x53)
    a.db(0x56)
    a.db(0x8B, 0x99); a.dd(RING)
    a.db(0x8B, 0xF3)
    a.db(0x83, 0xE6, RINGMASK)
    a.db(0x8D, 0xB4, 0xF1); a.dd(RING + 8)
    a.db(0x89, 0x06)
    a.db(0x89, 0x56, 0x04)
    a.db(0x43)
    a.db(0x89, 0x99); a.dd(RING)
    a.db(0x5E)
    a.db(0x5B)
    a.db(0xC3)

    # tokcnt: ecx=delta -> edx = executed-count & 0xFFFFFF, 0 if nil chain
    a.label('tokcnt')
    a.db(0x8B, 0x91); a.dd(AOWHSMAP)
    a.db(0x85, 0xD2)
    a.j8(0x74, 'tz')
    a.db(0x8B, 0x92); a.dd(0x23C)
    a.db(0x85, 0xD2)
    a.j8(0x74, 'tz')
    a.db(0x8B, 0x52, 0x04)
    a.db(0x85, 0xD2)
    a.j8(0x74, 'tz')
    a.db(0x8B, 0x52, 0x18)
    a.db(0x81, 0xE2); a.dd(0x00FFFFFF)
    a.db(0xC3)
    a.label('tz')
    a.db(0x33, 0xD2)
    a.db(0xC3)

    # H1: Random entry
    a.label('cave_random')
    a.db(0x50); a.db(0x52); a.db(0x51)
    a.pic_delta_ecx()
    a.seed_to_edx('r')
    a.db(0x8B, 0x44, 0x24, 0x0C)
    a.call('ring_append')
    a.db(0x59); a.db(0x5A); a.db(0x58)
    a.db(0x53)
    a.db(0x56)
    a.db(0x8B, 0xF2)
    a.db(0x8B, 0xD8)
    a.jmp32(H_RANDOM + 6)

    # H2: TMoveTE post-Random
    a.label('cave_move')
    a.db(0x50); a.db(0x52); a.db(0x51)
    a.pic_delta_ecx()
    a.db(0x8B, 0x53, 0x14)
    a.db(0x85, 0xD2)
    a.j8(0x74, 'mz')
    a.db(0x8B, 0x42, 0x04)
    a.db(0x85, 0xC0)
    a.j8(0x74, 'mz')
    a.db(0x8B, 0x10)
    a.j8(0xEB, 'mh')
    a.label('mz')
    a.db(0x33, 0xD2)
    a.label('mh')
    a.db(0xB8); a.dd(TAG_MOVE)
    a.call('ring_append')
    a.db(0x59); a.db(0x5A); a.db(0x58)
    a.db(0x8B, 0x43, 0x14)
    a.db(0x8B, 0x40, 0x08)
    a.jmp32(H_MOVE + 6)

    # H3: GetSyncValue entry (reloc-neutralized displaced mov)
    a.label('cave_sync')
    a.db(0x50); a.db(0x52); a.db(0x51)
    a.pic_delta_ecx()
    a.seed_to_edx('s')
    a.db(0xB8); a.dd(TAG_SYNC)
    a.call('ring_append')
    a.db(0x59); a.db(0x5A); a.db(0x58)
    a.db(0x51)
    a.pic_delta_ecx()
    a.db(0x8B, 0x81); a.dd(AOWHSMAP)
    a.db(0x59)
    a.jmp32(H_SYNC + 5)

    # H4: OutOfSync entry
    a.label('cave_boom')
    a.db(0x50); a.db(0x52); a.db(0x51)
    a.pic_delta_ecx()
    a.seed_to_edx('b')
    a.db(0xB8); a.dd(TAG_BOOM)
    a.call('ring_append')
    a.db(0x59); a.db(0x5A); a.db(0x58)
    a.db(0x53)
    a.db(0x56)
    a.db(0x57)
    a.db(0x8B, 0xD8)
    a.jmp32(H_BOOM + 5)

    # H5: CaptureTokenCycles entry
    a.label('cave_capt')
    a.db(0x50); a.db(0x52); a.db(0x51)
    a.pic_delta_ecx()
    a.call('tokcnt')
    a.db(0x0F, 0xB6, 0x40, 0x1A)
    a.db(0xC1, 0xE0, 0x18)
    a.db(0x0B, 0xD0)
    a.db(0xB8); a.dd(TAG_CAPT)
    a.call('ring_append')
    a.db(0x59); a.db(0x5A); a.db(0x58)
    a.db(0x53)
    a.db(0x56)
    a.db(0x8B, 0xF2)
    a.db(0x8B, 0xD8)
    a.jmp32(H_CAPT + 6)

    # H6: TokenCyclesCaptured entry
    a.label('cave_rels')
    a.db(0x50); a.db(0x52); a.db(0x51)
    a.pic_delta_ecx()
    a.call('tokcnt')
    a.db(0x0F, 0xB6, 0x40, 0x1A)
    a.db(0xC1, 0xE0, 0x18)
    a.db(0x0B, 0xD0)
    a.db(0xB8); a.dd(TAG_RELS)
    a.call('ring_append')
    a.db(0x59); a.db(0x5A); a.db(0x58)
    a.db(0x53)
    a.db(0x8B, 0xD8)
    a.db(0xF6, 0x43, 0x18, 0x02)
    a.jmp32(H_RELS + 7)

    # H7: TAIExecuter.Unlock entry
    a.label('cave_aiul')
    a.db(0x50); a.db(0x52); a.db(0x51)
    a.pic_delta_ecx()
    a.call('tokcnt')
    a.db(0x8B, 0x40, 0x30)
    a.db(0xC1, 0xE0, 0x18)
    a.db(0x0B, 0xD0)
    a.db(0xB8); a.dd(TAG_AIUL)
    a.call('ring_append')
    a.db(0x59); a.db(0x5A); a.db(0x58)
    a.db(0x53)
    a.db(0x8B, 0xD8)
    a.db(0x83, 0x7B, 0x30, 0x00)
    a.jmp32(H_AIUL + 7)

    # H8: mode-2 pump post TAIPlayerControl.Process -> WORK then STAT
    a.label('cave_work')
    a.db(0x50); a.db(0x52); a.db(0x51)
    a.pic_delta_ecx()
    a.db(0x8B, 0xD0)
    a.db(0x81, 0xE2); a.dd(0xFF)
    a.db(0x8B, 0x45, 0xFC)
    a.db(0x0F, 0xB6, 0x40, 0x10)
    a.db(0xC1, 0xE0, 0x08)
    a.db(0x0B, 0xD0)
    a.db(0xB8); a.dd(TAG_WORK)
    a.call('ring_append')
    # ---- STAT fingerprint (ecx = delta preserved by ring_append) ----
    a.db(0x8B, 0x81); a.dd(AOWHSMAP)    # mov eax,[ecx+AoWHSMap]
    a.db(0x85, 0xC0)                    # test eax,eax
    a.je32('wskip')                     # jz  wskip (near - block > 127 bytes)
    a.db(0x53)                          # push ebx
    a.db(0x8B, 0xD8)                    # mov ebx, eax        ; map
    a.db(0x8B, 0x45, 0xFC)              # mov eax,[ebp-4]     ; aiexec
    a.db(0x0F, 0xB6, 0x40, 0x10)        # movzx eax, byte [eax+10h] ; idx
    a.db(0x50)                          # push eax            ; save idx
    a.db(0x8B, 0x93); a.dd(0x140)       # mov edx,[ebx+140h]  ; playerlist
    a.db(0x85, 0xD2)                    # test edx,edx
    a.j8(0x74, 'wnop')                  # jz  wnop
    a.db(0x8B, 0x52, 0x08)              # mov edx,[edx+8]
    a.db(0x85, 0xD2)
    a.j8(0x74, 'wnop')
    a.db(0x8B, 0x52, 0x04)              # mov edx,[edx+4]
    a.db(0x85, 0xD2)
    a.j8(0x74, 'wnop')
    a.db(0x8B, 0x14, 0x82)              # mov edx,[edx+eax*4] ; player
    a.db(0x85, 0xD2)
    a.j8(0x74, 'wnop')
    a.db(0x8B, 0x42, 0x48)              # mov eax,[edx+48h]   ; busy counter
    a.db(0x25); a.dd(0xFF)              # and eax, 0xFF
    a.db(0x80, 0x7A, 0x44, 0x00)        # cmp byte [edx+44h], 0
    a.j8(0x74, 'wnof')                  # je  wnof
    a.db(0x0D); a.dd(0x200)             # or  eax, 0x200
    a.label('wnof')
    a.j8(0xEB, 'whave')                 # jmp whave
    a.label('wnop')
    a.db(0xB8); a.dd(0x8000)            # mov eax, 0x8000     ; "no player" marker
    a.label('whave')
    a.db(0x83, 0xBB, 0x20, 0x01, 0x00, 0x00, 0x00)  # cmp dword [ebx+120h],0 ; combat
    a.j8(0x74, 'wnoc')                  # je  wnoc
    a.db(0x0D); a.dd(0x100)             # or  eax, 0x100
    a.label('wnoc')
    a.db(0x8B, 0x93); a.dd(0x1DC)       # mov edx,[ebx+1DCh]  ; elog delay
    a.db(0x81, 0xE2); a.dd(0xFF)        # and edx, 0xFF
    a.db(0xC1, 0xE2, 0x10)              # shl edx, 16
    a.db(0x0B, 0xC2)                    # or  eax, edx
    a.db(0x8B, 0x93); a.dd(0x1D4)       # mov edx,[ebx+1D4h]  ; cb list
    a.db(0x85, 0xD2)
    a.j8(0x74, 'wnoq')
    a.db(0x8B, 0x52, 0x04)              # mov edx,[edx+4]
    a.db(0x85, 0xD2)
    a.j8(0x74, 'wnoq')
    a.db(0x8B, 0x52, 0x08)              # mov edx,[edx+8]     ; count
    a.db(0x83, 0xE2, 0x0F)              # and edx, 0Fh
    a.db(0xC1, 0xE2, 0x0A)              # shl edx, 10
    a.db(0x0B, 0xC2)                    # or  eax, edx
    a.label('wnoq')
    a.db(0x5A)                          # pop edx             ; idx
    a.db(0xC1, 0xE2, 0x18)              # shl edx, 24
    a.db(0x0B, 0xC2)                    # or  eax, edx
    a.db(0x8B, 0xD0)                    # mov edx, eax        ; val
    a.db(0xB8); a.dd(TAG_STAT)          # mov eax,'STAT'
    a.call('ring_append')
    a.db(0x5B)                          # pop ebx
    a.label('wskip')
    a.db(0x59); a.db(0x5A); a.db(0x58)
    a.db(0x8B, 0xD8)
    a.db(0x84, 0xDB)
    a.je32(WORK_JE_TARGET)
    a.jmp32(H_WORK + 6)

    # H9: CreateArmyMoveTE post-Setup
    a.label('cave_crea')
    a.db(0x50); a.db(0x52); a.db(0x51)
    a.pic_delta_ecx()
    a.db(0x8B, 0x53, 0x14)
    a.db(0x85, 0xD2)
    a.j8(0x74, 'cz')
    a.db(0x8B, 0x42, 0x04)
    a.db(0x85, 0xC0)
    a.j8(0x74, 'cz')
    a.db(0x8B, 0x10)
    a.j8(0xEB, 'ch')
    a.label('cz')
    a.db(0x33, 0xD2)
    a.label('ch')
    a.db(0x81, 0xE2); a.dd(0x00FFFFFF)
    a.db(0x8B, 0x44, 0x24, 0x08)
    a.db(0x25); a.dd(0xFF)
    a.db(0xC1, 0xE0, 0x18)
    a.db(0x0B, 0xD0)
    a.db(0xB8); a.dd(TAG_CREA)
    a.call('ring_append')
    a.db(0x8B, 0x55, 0x04)
    a.db(0xB8); a.dd(TAG_CRE2)
    a.call('ring_append')
    a.db(0x59); a.db(0x5A); a.db(0x58)
    a.db(0x84, 0xC0)
    a.db(0x0F, 0x85); a._r(CREA_JNE_TARGET)
    a.db(0x33, 0xF6)
    a.jmp32(H_CREA + 6)

    # H10: TArmyHS.MoveFirst entry (animation start).
    # entry: eax=armyHS, edx=dir, cl=flag - all preserved
    a.label('cave_anim')
    a.db(0x50); a.db(0x52); a.db(0x51)
    a.pic_delta_ecx()
    a.db(0x8B, 0x50, 0x1C)              # mov edx,[eax+1Ch]   ; army
    a.db(0x85, 0xD2)
    a.j8(0x74, 'az')
    a.db(0x8B, 0x42, 0x25)              # mov eax,[edx+25h]   ; dest x,y,l bytes
    a.db(0x25); a.dd(0x00FFFFFF)        # and eax, 0xFFFFFF
    a.db(0x0F, 0xB6, 0x52, 0x12)        # movzx edx, byte [edx+12h] ; owner
    a.db(0xC1, 0xE2, 0x18)              # shl edx, 24
    a.db(0x0B, 0xD0)                    # or  edx, eax
    a.j8(0xEB, 'ah')
    a.label('az')
    a.db(0x33, 0xD2)
    a.label('ah')
    a.db(0xB8); a.dd(TAG_ANIM)
    a.call('ring_append')
    a.db(0x59); a.db(0x5A); a.db(0x58)
    a.db(0x53)                          # displaced: push ebx/esi/edi; add esp,-14h
    a.db(0x56)
    a.db(0x57)
    a.db(0x83, 0xC4, 0xEC)
    a.jmp32(H_ANIM + 6)

    # H11: SetExecuteEventLogDelay entry.  eax=map, edx=newdelay - preserved
    a.label('cave_elog')
    a.db(0x50); a.db(0x52); a.db(0x51)
    a.pic_delta_ecx()
    a.db(0x81, 0xE2); a.dd(0xFF)        # and edx, 0xFF (newdelay)
    a.db(0x53)                          # push ebx
    a.db(0x8B, 0x98, 0xDC, 0x01, 0x00, 0x00)  # mov ebx,[eax+1DCh] ; old delay
    a.db(0x81, 0xE3); a.dd(0xFF)        # and ebx, 0xFF
    a.db(0xC1, 0xE3, 0x08)              # shl ebx, 8
    a.db(0x0B, 0xD3)                    # or  edx, ebx
    a.db(0x8B, 0x98, 0xD4, 0x01, 0x00, 0x00)  # mov ebx,[eax+1D4h] ; cb list
    a.db(0x85, 0xDB)
    a.j8(0x74, 'en')
    a.db(0x8B, 0x5B, 0x04)              # mov ebx,[ebx+4]
    a.db(0x85, 0xDB)
    a.j8(0x74, 'en')
    a.db(0x8B, 0x5B, 0x08)              # mov ebx,[ebx+8]     ; count
    a.db(0x81, 0xE3); a.dd(0xFF)
    a.db(0xC1, 0xE3, 0x10)              # shl ebx, 16
    a.db(0x0B, 0xD3)                    # or  edx, ebx
    a.label('en')
    a.db(0x5B)                          # pop ebx
    a.db(0xB8); a.dd(TAG_ELOG)
    a.call('ring_append')
    a.db(0x59); a.db(0x5A); a.db(0x58)
    a.db(0x8B, 0x88, 0xDC, 0x01, 0x00, 0x00)  # displaced: mov ecx,[eax+1DCh]
    a.jmp32(H_ELOG + 6)

    # H12: MoveArmyEx entry - record true caller (CRE3) + one dword above
    # the two stack args (CRE4 = grandparent retaddr when the direct caller
    # is the thin MoveArmy wrapper; otherwise caller-frame noise).
    # entry: eax=armyHS, edx=sel, ecx=path; [esp]=ret,[+4]/[+8]=2 args
    a.label('cave_cre3')
    a.db(0x50); a.db(0x52); a.db(0x51)  # push eax/edx/ecx
    a.pic_delta_ecx()                   # ecx = load delta
    a.db(0x8B, 0x54, 0x24, 0x0C)        # mov edx,[esp+0Ch]   ; retaddr
    a.db(0xB8); a.dd(TAG_CRE3)          # mov eax,'CRE3'
    a.call('ring_append')
    a.db(0x8B, 0x54, 0x24, 0x18)        # mov edx,[esp+18h]   ; above args
    a.db(0xB8); a.dd(TAG_CRE4)          # mov eax,'CRE4'
    a.call('ring_append')
    a.db(0x59); a.db(0x5A); a.db(0x58)  # pop ecx/edx/eax
    a.db(0x55)                          # displaced: push ebp
    a.db(0x8B, 0xEC)                    #            mov ebp, esp
    a.db(0x51)                          #            push ecx
    a.db(0x53)                          #            push ebx
    a.db(0x56)                          #            push esi
    a.jmp32(CRE3_RESUME)

    a.resolve()
    assert CAVE_BASE + len(a.buf) <= CAVE_LIMIT, "cave overflow %d" % len(a.buf)
    return bytes(a.buf) + bytes(CAVE_LIMIT - CAVE_BASE - len(a.buf)), a.labels


def reloc_scan(data, ranges, allow_off):
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
            eoff = off + 8 + i*2
            w = struct.unpack_from('<H', data, eoff)[0]
            typ, ofs = w >> 12, w & 0xFFF
            if typ == 0 or eoff == allow_off:
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

    ranges = [(va - VA2FILE, va - VA2FILE + len(OLD[va])) for va in OLD]
    ranges.append((CAVE_BASE - VA2FILE, CAVE_LIMIT - VA2FILE))
    hits = reloc_scan(data, ranges, RELOC_ENTRY_OFF)
    if hits:
        print("ABORT: unexpected reloc fixups intersect patch ranges: %s" % hits)
        return 1
    print("  reloc scan    clean (H3 entry excepted)")

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
                          ("H8 Work+Stat", H_WORK, 'cave_work'),
                          ("H9 Create", H_CREA, 'cave_crea'),
                          ("H10 AnimStart", H_ANIM, 'cave_anim'),
                          ("H11 EventLog", H_ELOG, 'cave_elog'),
                          ("H12 MvAExEntry", H_CRE3, 'cave_cre3')):
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
