#!/usr/bin/env python3
"""
Movement-predictor fix for AoWEPACK.dll (port of BXL's v4 fix, 2026-07-19).

Bug: mixed-ability army stacks predict AND execute movement using
MIN(remaining MP across units) walked against MAX(per-hex cost across units)
-> range underestimated. Fix: TrueReachPos cave walks the path per-unit with
each unit's own cost table (TAbstractUnit.CreateMovePointTable) and own MP;
stack reach = worst unit's stop position.

Four hooks (all previously `call TMovepath.MovePointsToPos` or the +14h store):
  1. TMoveArmyTE.Setup          @ 0x55747B01 - execution path truncation
  2. MoveArmyEx                 @ 0x5574A36E - destination-reached check
  3. TSelectedArmy.Update       @ 0x557936A3 - TMoveSettings+14h synthetic budget (13B)
  4. TSelectedArmy.CalculateMovePath @ 0x55792A18 - refresh budget when path built (v4)

Ported with BXL's v2/v3/v4 corrections that his shared build_patch.py lacks:
  - AoWHSMap global read is position-independent (call/pop delta) - DLL rebases
  - terrain/road bytes read with MOVSX (signed; road -1 = no road)
  - cave_calcpath fourth hook (Update is event-driven, fires before path exists)

Cave relocated to OUR free space: 0x5580DE40 (file 0x10D240), verified zeros.
Dry-run by default; --apply to write. Backup: AoWEPACK.dll.bak_move_predictor
"""
import shutil, sys, os

GAME = os.path.dirname(os.path.abspath(__file__))
DLL  = os.path.join(GAME, "AoWEPACK.dll")
BAK  = DLL + ".bak_move_predictor"

FILE_DELTA = 0x55700C00           # VA - FILE_DELTA = file offset (CODE section)

# game function addresses (all verified present in our build)
TRANSPORTER      = 0x5578E00C     # TArmy.Transporter(eax=army, edx=mask) -> eax unit*/0
UNIT_CREATE_MPT  = 0x5577FDC4     # TAbstractUnit.CreateMovePointTable(eax=unit, edx=buf256)
GETFIELD_STUB    = 0x557020FC     # TMapContainer.GetField(eax=cont, edx=x, ecx=y, push level)
GETMOVESETTINGS  = 0x557639DC     # TMoveSettingsList.GetMoveSettings(eax=list, edx=i)
POS_TO_MP        = 0x55763904     # TMovepath.PosToMovePoints(eax=path, edx=pos) -> eax cost
MP_TO_POS        = 0x557638D8     # TMovepath.MovePointsToPos (original callee at sites 1&2)
AOWHSMAP         = 0x558FA040     # global: pointer to TAoWHSMap (PIC access only!)

CAVE_BASE = 0x5580DE40            # file 0x10D240, zeros verified 2026-07-19

class Asm:
    def __init__(self, base):
        self.base = base; self.buf = bytearray(); self.labels = {}
        self.fix32 = []; self.fix8 = []
    def here(self): return self.base + len(self.buf)
    def label(self, name): self.labels[name] = self.here()
    def db(self, *bs): self.buf += bytes(bs)
    def dd(self, v): self.buf += v.to_bytes(4, 'little')
    def call(self, target): self.db(0xE8); self._rel32(target)
    def jmp32(self, target): self.db(0xE9); self._rel32(target)
    def _rel32(self, target):
        if isinstance(target, str):
            self.fix32.append((len(self.buf), target)); self.buf += b'\0\0\0\0'
        else:
            self.buf += (target - (self.here() + 4)).to_bytes(4, 'little', signed=True)
    def j8(self, opcode, label):
        self.db(opcode); self.fix8.append((len(self.buf), label)); self.db(0x00)
    def resolve(self):
        for off, lab in self.fix32:
            self.buf[off:off+4] = (self.labels[lab] - (self.base + off + 4)).to_bytes(4, 'little', signed=True)
        for off, lab in self.fix8:
            rel = self.labels[lab] - (self.base + off + 1)
            assert -128 <= rel <= 127, f"rel8 out of range for {lab}: {rel}"
            self.buf[off] = rel & 0xFF

a = Asm(CAVE_BASE)

# ---- cave_exec: replaces MovePointsToPos call in TMoveArmyTE.Setup ----------
# in: eax=path, edx=minMP (ignored); caller frame: [ebp-4]=armyHS, [ebp-5]=mask
a.label('cave_exec')
a.db(0x8B, 0xC8)                    # mov ecx, eax           ; path
a.db(0x8B, 0x45, 0xFC)              # mov eax, [ebp-4]       ; armyHS
a.db(0x8B, 0x40, 0x1C)              # mov eax, [eax+0x1C]    ; TArmy
a.db(0x0F, 0xB6, 0x55, 0xFB)        # movzx edx, byte [ebp-5]; mask
a.jmp32('true_reach')

# ---- cave_movearmy: replaces MovePointsToPos call in MoveArmyEx -------------
# in: eax=path; esi=armyHS; [ebp-1]=mask
a.label('cave_movearmy')
a.db(0x8B, 0xC8)                    # mov ecx, eax
a.db(0x8B, 0x46, 0x1C)              # mov eax, [esi+0x1C]    ; TArmy
a.db(0x0F, 0xB6, 0x55, 0xFF)        # movzx edx, byte [ebp-1]; mask
a.jmp32('true_reach')

# ---- cave_display: replaces 13 bytes in TSelectedArmy.Update @0x557936A3 ----
# in: ebp=minMP, esi=settings index, ebx=TSelectedArmy; preserve ebx/esi/edi/ebp
a.label('cave_display')
a.db(0x57)                          # push edi
a.db(0x8B, 0xD6)                    # mov edx, esi
a.db(0x8B, 0x43, 0x08)              # mov eax, [ebx+8]       ; settings list
a.call(GETMOVESETTINGS)             # -> eax = TMoveSettings
a.db(0x8B, 0xF8)                    # mov edi, eax
a.db(0x89, 0x6F, 0x14)              # mov [edi+0x14], ebp    ; vanilla default
a.db(0x8B, 0x4F, 0x08)              # mov ecx, [edi+8]       ; path
a.db(0x83, 0x79, 0x08, 0x02)        # cmp dword [ecx+8], 2   ; path count
a.j8(0x7C, 'disp_out')              # jl  -> keep vanilla
a.db(0x8B, 0x47, 0x10)              # mov eax, [edi+0x10]    ; armyHS
a.db(0x85, 0xC0)                    # test eax, eax
a.j8(0x74, 'disp_out')              # jz  -> keep vanilla
a.db(0x8B, 0x40, 0x1C)              # mov eax, [eax+0x1C]    ; TArmy
a.db(0x0F, 0xB6, 0x57, 0x20)        # movzx edx, byte [edi+0x20] ; selection mask
a.call('true_reach')                # -> eax = true reach position
a.db(0x8B, 0xD0)                    # mov edx, eax
a.db(0x8B, 0x47, 0x08)              # mov eax, [edi+8]       ; path
a.call(POS_TO_MP)                   # -> eax = B* (merged cost of true prefix)
a.db(0x89, 0x47, 0x14)              # mov [edi+0x14], eax    ; synthetic budget
a.label('disp_out')
a.db(0x5F)                          # pop edi
a.db(0xC3)                          # ret

# ---- cave_calcpath (v4): wraps PosToMovePoints call @0x55792A18 -------------
# in: eax=path, edx=0; edi=TMoveSettings (live), esi=TArmyHS
# returns eax = total path cost (original semantics) + refreshes +14h budget
a.label('cave_calcpath')
a.call(POS_TO_MP)                   # eax = total cost (original call)
a.db(0x50)                          # push eax               ; save return value
a.db(0x8B, 0x47, 0x10)              # mov eax, [edi+0x10]    ; armyHS
a.db(0x85, 0xC0)                    # test eax, eax
a.j8(0x74, 'calc_out')              # jz  -> keep vanilla budget
a.db(0x8B, 0x4F, 0x08)              # mov ecx, [edi+8]       ; path
a.db(0x83, 0x79, 0x08, 0x02)        # cmp dword [ecx+8], 2   ; path count
a.j8(0x7C, 'calc_out')              # jl  -> keep vanilla budget
a.db(0x8B, 0x40, 0x1C)              # mov eax, [eax+0x1C]    ; TArmy
a.db(0x0F, 0xB6, 0x57, 0x20)        # movzx edx, byte [edi+0x20] ; selection mask
a.call('true_reach')                # -> eax = true reach position
a.db(0x8B, 0xD0)                    # mov edx, eax
a.db(0x8B, 0x47, 0x08)              # mov eax, [edi+8]       ; path
a.call(POS_TO_MP)                   # -> eax = B*
a.db(0x89, 0x47, 0x14)              # mov [edi+0x14], eax    ; synthetic budget
a.label('calc_out')
a.db(0x58)                          # pop eax                ; restore total
a.db(0xC3)                          # ret

# ---- true_reach: TrueReachPos(eax=TArmy, edx=mask, ecx=path) -> eax pos -----
# position semantics identical to MovePointsToPos (0 = destination)
a.label('true_reach')
a.db(0x55)                          # push ebp
a.db(0x8B, 0xEC)                    # mov ebp, esp
a.db(0x81, 0xEC, 0x10, 0x01, 0x00, 0x00)  # sub esp, 0x110
a.db(0x53)                          # push ebx
a.db(0x56)                          # push esi
a.db(0x57)                          # push edi
a.db(0x89, 0x45, 0xF8)              # mov [ebp-8], eax       ; army
a.db(0x89, 0x55, 0xF4)              # mov [ebp-0xC], edx     ; mask
a.db(0x89, 0x4D, 0xFC)              # mov [ebp-4], ecx       ; path
a.db(0xC7, 0x45, 0xF0, 0xFF, 0xFF, 0xFF, 0xFF)  # mov dword [ebp-0x10], -1
a.call(TRANSPORTER)                 # transporter? (eax=army, edx=mask live)
a.db(0x85, 0xC0)                    # test eax, eax
a.j8(0x74, 'tr_multi')              # jz multi
a.db(0x8B, 0xD8)                    # mov ebx, eax           ; unit = transporter
a.call('unit_walk')
a.db(0x89, 0x45, 0xF0)              # mov [ebp-0x10], eax
a.j8(0xEB, 'tr_done')               # jmp done
a.label('tr_multi')
a.db(0x8B, 0x45, 0xF8)              # mov eax, [ebp-8]
a.db(0x8B, 0x10)                    # mov edx, [eax]
a.db(0xFF, 0x52, 0x54)              # call [edx+0x54]        ; unit count
a.db(0x8B, 0xF8)                    # mov edi, eax           ; count
a.db(0x33, 0xF6)                    # xor esi, esi           ; index
a.label('tr_uloop')
a.db(0x3B, 0xF7)                    # cmp esi, edi
a.j8(0x7D, 'tr_done')               # jge done
a.db(0xB8, 0x01, 0x00, 0x00, 0x00)  # mov eax, 1
a.db(0x8B, 0xCE)                    # mov ecx, esi
a.db(0xD3, 0xE0)                    # shl eax, cl
a.db(0x85, 0x45, 0xF4)              # test [ebp-0xC], eax    ; selected?
a.j8(0x74, 'tr_next')               # jz next
a.db(0x8B, 0x45, 0xF8)              # mov eax, [ebp-8]       ; army
a.db(0x8B, 0x40, 0x08)              # mov eax, [eax+8]       ; TUnitList
a.db(0x8B, 0x40, 0x04)              # mov eax, [eax+4]       ; items
a.db(0x8B, 0x1C, 0xB0)              # mov ebx, [eax+esi*4]   ; unit
a.call('unit_walk')                 # -> eax = unit stop pos
a.db(0x3B, 0x45, 0xF0)              # cmp eax, [ebp-0x10]
a.j8(0x7E, 'tr_next')               # jle next (keep max = worst unit)
a.db(0x89, 0x45, 0xF0)              # mov [ebp-0x10], eax
a.label('tr_next')
a.db(0x46)                          # inc esi
a.j8(0xEB, 'tr_uloop')              # jmp uloop
a.label('tr_done')
a.db(0x8B, 0x45, 0xF0)              # mov eax, [ebp-0x10]
a.db(0x83, 0xF8, 0xFF)              # cmp eax, -1            ; no unit processed?
a.j8(0x75, 'tr_fin')                # jnz fin
a.db(0x8B, 0x45, 0xFC)              # mov eax, [ebp-4]
a.db(0x8B, 0x40, 0x08)              # mov eax, [eax+8]
a.db(0x48)                          # dec eax                ; = source pos (no reach)
a.label('tr_fin')
a.db(0x5F)                          # pop edi
a.db(0x5E)                          # pop esi
a.db(0x5B)                          # pop ebx
a.db(0x8B, 0xE5)                    # mov esp, ebp
a.db(0x5D)                          # pop ebp
a.db(0xC3)                          # ret

# ---- unit_walk: in ebx=unit*, ebp=true_reach frame; out eax=stop position ---
a.label('unit_walk')
a.db(0x56)                          # push esi
a.db(0x57)                          # push edi
a.db(0x8B, 0xC3)                    # mov eax, ebx
a.db(0x8D, 0x95, 0xF0, 0xFE, 0xFF, 0xFF)  # lea edx, [ebp-0x110] ; 256-byte buf
a.call(UNIT_CREATE_MPT)             # build unit cost table (incl. haste etc.)
a.db(0x8B, 0xC3)                    # mov eax, ebx
a.db(0x8B, 0x10)                    # mov edx, [eax]
a.db(0xFF, 0x92, 0xD8, 0x00, 0x00, 0x00)  # call [edx+0xD8] ; unit.MovePoints -> al
a.db(0x0F, 0xBE, 0xF8)              # movsx edi, al          ; edi = mp
a.db(0x8B, 0x45, 0xFC)              # mov eax, [ebp-4]       ; path
a.db(0x8B, 0x70, 0x08)              # mov esi, [eax+8]       ; count
a.db(0x4E)                          # dec esi                ; pos = count-1 (source)
a.label('uw_walk')
a.db(0x85, 0xF6)                    # test esi, esi
a.j8(0x7E, 'uw_done')               # jle done (0 = destination reached)
a.db(0x8B, 0x45, 0xFC)              # mov eax, [ebp-4]
a.db(0x8B, 0x40, 0x04)              # mov eax, [eax+4]       ; items
a.db(0x8B, 0x54, 0xB0, 0xFC)        # mov edx, [eax+esi*4-4] ; next hop entry
a.db(0x8B, 0xCA)                    # mov ecx, edx
a.db(0xC1, 0xE9, 0x10)              # shr ecx, 16
a.db(0x81, 0xE1, 0xFF, 0x00, 0x00, 0x00)  # and ecx, 0xFF   ; level
a.db(0x51)                          # push ecx               ; GetField stack arg
a.db(0x8B, 0xCA)                    # mov ecx, edx
a.db(0xC1, 0xE9, 0x08)              # shr ecx, 8
a.db(0x81, 0xE1, 0xFF, 0x00, 0x00, 0x00)  # and ecx, 0xFF   ; y
a.db(0x81, 0xE2, 0xFF, 0x00, 0x00, 0x00)  # and edx, 0xFF   ; x
# --- PIC read of [AoWHSMap] (v2 fix: DLL rebases; no reloc entry for caves) --
a.call(a.here() + 5)                # call $+5
_pop_va = a.here()
a.db(0x58)                          # pop eax                ; eax = runtime addr of pop
a.db(0x2D); a.dd(_pop_va)           # sub eax, preferred-VA  ; eax = rebase delta
a.db(0x8B, 0x80); a.dd(AOWHSMAP)    # mov eax, [eax+AoWHSMap]
# ----------------------------------------------------------------------------
a.db(0x8B, 0x40, 0x10)              # mov eax, [eax+0x10]    ; TMapContainer
a.call(GETFIELD_STUB)               # -> eax = TMapField*
a.db(0xF6, 0x40, 0x19, 0x40)        # test byte [eax+0x19], 0x40 ; special hex?
a.j8(0x74, 'uw_tbl')                # jz table cost
a.db(0x8B, 0x45, 0xFC)              # mov eax, [ebp-4]       ; special: use stored
a.db(0x8B, 0x40, 0x04)              # mov eax, [eax+4]       ;   merged cost byte
a.db(0x0F, 0xBE, 0x54, 0xB0, 0xFF)  # movsx edx, byte [eax+esi*4-1]
a.j8(0xEB, 'uw_have')               # jmp have
a.label('uw_tbl')
a.db(0x0F, 0xBE, 0x50, 0x14)        # movsx edx, byte [eax+0x14] ; terrain (SIGNED, v3)
a.db(0xC1, 0xE2, 0x04)              # shl edx, 4
a.db(0x0F, 0xBE, 0x48, 0x15)        # movsx ecx, byte [eax+0x15] ; road (SIGNED, -1=none, v3)
a.db(0x03, 0xD1)                    # add edx, ecx
a.db(0x8D, 0x8D, 0xF0, 0xFE, 0xFF, 0xFF)  # lea ecx, [ebp-0x110]
a.db(0x0F, 0xBE, 0x54, 0x11, 0x01)  # movsx edx, byte [ecx+edx+1] ; +1 road-col shift
a.label('uw_have')
a.db(0x85, 0xD2)                    # test edx, edx
a.j8(0x78, 'uw_done')               # js done (0xFF impassable for this unit)
a.db(0x3B, 0xD7)                    # cmp edx, edi
a.j8(0x7F, 'uw_done')               # jg done (cost > remaining mp)
a.db(0x2B, 0xFA)                    # sub edi, edx           ; mp -= cost
a.db(0x4E)                          # dec esi                ; advance one hex
a.j8(0xEB, 'uw_walk')               # jmp walk
a.label('uw_done')
a.db(0x8B, 0xC6)                    # mov eax, esi
a.db(0x5F)                          # pop edi
a.db(0x5E)                          # pop esi
a.db(0xC3)                          # ret

a.resolve()
cave = bytes(a.buf)
print(f"Cave size: {len(cave)} (0x{len(cave):X}) bytes at 0x{CAVE_BASE:X}..0x{CAVE_BASE+len(cave)-1:X}")
for name in ('cave_exec','cave_movearmy','cave_display','cave_calcpath','true_reach','unit_walk'):
    print(f"  {name:14s} @ 0x{a.labels[name]:08X}")
assert CAVE_BASE + len(cave) <= 0x5580E140, "cave overruns verified-zero region (file 0x10D500)"

def rel32(src_call_va, dst_va):
    return (dst_va - (src_call_va + 5)).to_bytes(4, 'little', signed=True)

patches = [
    (0x55747B01,
     bytes([0xE8]) + rel32(0x55747B01, MP_TO_POS),
     bytes([0xE8]) + rel32(0x55747B01, a.labels['cave_exec']),
     "TMoveArmyTE.Setup: MovePointsToPos -> cave_exec"),
    (0x5574A36E,
     bytes([0xE8]) + rel32(0x5574A36E, MP_TO_POS),
     bytes([0xE8]) + rel32(0x5574A36E, a.labels['cave_movearmy']),
     "MoveArmyEx: MovePointsToPos -> cave_movearmy"),
    (0x557936A3,
     bytes([0x8B,0xD6, 0x8B,0x43,0x08, 0xE8]) + rel32(0x557936A8, GETMOVESETTINGS) + bytes([0x89,0x68,0x14]),
     bytes([0xE8]) + rel32(0x557936A3, a.labels['cave_display']) + bytes([0x90]*8),
     "TSelectedArmy.Update: budget store -> cave_display"),
    (0x55792A18,
     bytes([0xE8]) + rel32(0x55792A18, POS_TO_MP),
     bytes([0xE8]) + rel32(0x55792A18, a.labels['cave_calcpath']),
     "TSelectedArmy.CalculateMovePath: PosToMovePoints -> cave_calcpath (v4)"),
    (CAVE_BASE, bytes(len(cave)), cave, "code cave"),
]

with open(DLL, 'rb') as fh:
    data = bytearray(fh.read())

ok = True
for va, orig, new, desc in patches:
    off = va - FILE_DELTA
    cur = bytes(data[off:off+len(orig)])
    if cur == new:
        print(f"ALREADY PATCHED: {desc}")
    elif cur != orig:
        print(f"MISMATCH at VA 0x{va:X} ({desc}):")
        print(f"  expected {orig.hex(' ')}")
        print(f"  found    {cur.hex(' ')}")
        ok = False

if not ok:
    print("Aborting - original bytes did not match."); sys.exit(1)

if '--apply' not in sys.argv:
    print("\nDry run OK. Re-run with --apply to write the patch."); sys.exit(0)

if not os.path.exists(BAK):
    shutil.copyfile(DLL, BAK)
    print(f"Backup written: {BAK}")
for va, orig, new, desc in patches:
    off = va - FILE_DELTA
    data[off:off+len(new)] = new
    print(f"Patched: {desc} @ VA 0x{va:X}")
with open(DLL, 'wb') as fh:
    fh.write(data)
print("AoWEPACK.dll patched successfully.")
