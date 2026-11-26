#!/usr/bin/env python3
"""
Wall Crushing I/II/III — damage 2-5 / 3-10 / 4-15 — AoWEPACK.dll
================================================================
Wall Crushing (id 0x75, TWallCrushingAbility : TTouchAbility) becomes a
3-level ability. The touch attack keeps ATK 6; DMG becomes 5 x level
(5/10/15). With wall defense 0 the engine damage roll then produces exactly
the ranges 2-5 / 3-10 / 4-15. Legacy bare-bit units = level I (2-5; vanilla
was DMG 6 -> 2-6, so max drops 6->5).

Level storage: generic ML data record (classref [0x5571DEB8], id word at
rec+0xE, level byte at rec+0xC — the Turn Undead pattern; persists in saves,
old saves load as level I). Cost: vanilla [self+0x14] if nonzero else 3;
GetSkillPoints = level x ExpandCost (display == charge).

REQUIRES: healing-leveled patch (reuses its generic cave_hlcanexp 0x5580E770 +
cave_hlexpname 0x5580E7C0) and lifesteal-leveled patch (cave_lsnames).

Run: python patch_wallcrush_leveled_v1.py [--apply]
Revert: restore AoWEPACK.dll.bak_wallcrush_lvl
"""
import struct, sys, shutil, os

DLL   = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'AoWEPACK.dll')
BAK   = DLL + '.bak_wallcrush_lvl'
DELTA = 0x55700C00

FINDDATA   = 0x5574F1C4
ADDDATA    = 0x5574F278
REMDATA    = 0x5574F284   # (EAX=unit, EDX=rec)
SETBIT     = 0x5574E718   # (EAX=self, EDX=unit, ECX=id, push flag)
TOBJCREATE = 0x55703064
CLASSREF_MLDATA = 0x5571DEB8
LSNAMES    = 0x5580E2A0
CANEXP_GEN = 0x5580E770   # healing's generic CanExpand (mask & GetLevel<3)
EXPNAME_GEN= 0x5580E7C0   # healing's generic ExpandName (GetLevel+1 -> lsnames)
VALHELP    = 0x55726094   # (EAX=atk, EDX=dmg, CX=types, 5 stack) expected value
HITHELP    = 0x55725FE0

CAVES = {
    'wclvl5s':  0x10DFC0,  # (EAX=strat unit|nil) -> 5*clamp(level,1,3)
    'wclvl':    0x10E000,  # GetLevel/GetInherentLevel
    'wcexpcost':0x10E050,
    'wcskillpt':0x10E060,
    'wcgetname':0x10E080,
    'wcexpand': 0x10E0B0,
    'wcremove': 0x10E130,
    'wcest1':   0x10E190,  # +0xD8 rewrite
    'wcest2':   0x10E1F0,  # +0xDC rewrite
    'wcexec':   0x10E2B0,  # combat exec dmg (stack fixup)
    'wcestdmg': 0x10E2D0,  # +0xE4 dmg helper
}
CAVE_END = 0x10E400
def VA(n): return CAVES[n] + DELTA
def rel32(src, dst): return struct.pack('<i', dst - (src + 5))
def call(src, dst): return b'\xE8' + rel32(src, dst)

caves = {}

# --- wclvl5s: (EAX=strategic|nil) -> 5*clamp(level,1..3); preserves ecx/edx
b = bytearray(); base = VA('wclvl5s')
b += b'\x51\x52'                    # push ecx; push edx
b += b'\x85\xC0\x74\x16'            # test eax,eax; jz .one (@28)
b += b'\xBA\x75\x00\x00\x00'        # mov edx,0x75
b += call(base+len(b), FINDDATA)
b += b'\x85\xC0\x74\x08'            # jz .one
b += b'\x0F\xB6\x40\x0C'            # movzx eax, byte [eax+0xC]  (ML-data level)
b += b'\x85\xC0\x75\x05'            # jnz .clamp
b += b'\xB8\x01\x00\x00\x00'        # .one: mov eax,1
b += b'\x83\xF8\x03\x7E\x05'        # .clamp: cmp eax,3; jle .mul
b += b'\xB8\x03\x00\x00\x00'        # mov eax,3
b += b'\x8D\x04\x80'                # .mul: lea eax,[eax+eax*4]  (x5)
b += b'\x5A\x59\xC3'                # pop edx; pop ecx; ret
assert len(b) == 49, len(b)
caves['wclvl5s'] = bytes(b)

# --- wclvl: (EAX=self, EDX=unit strat) -> 0 / 1..3   (+0x70 & +0x94)
b = bytearray(); base = VA('wclvl')
b += b'\x85\xD2\x74\x42'            # test edx,edx; jz .z (@70)
b += b'\x53\x56'
b += b'\x8B\xD8\x8B\xF2'            # ebx=self, esi=unit
b += b'\x8B\x53\x0C'                # mov edx,[ebx+0xC]
b += b'\x8B\xC6\x8B\x08'
b += b'\xFF\x51\x4C'                # HasAbility
b += b'\x84\xC0\x74\x2A'            # jz .z2 (@66)
b += b'\x8B\x53\x0C\x8B\xC6'
b += call(base+len(b), FINDDATA)
b += b'\x85\xC0\x74\x15'            # jz .one (@59)
b += b'\x0F\xB6\x40\x0C'            # movzx eax, byte [eax+0xC]
b += b'\x85\xC0\x74\x0D'            # jz .one
b += b'\x83\xF8\x03\x7E\x05'        # cmp eax,3; jle .ret2 (@56)
b += b'\xB8\x03\x00\x00\x00'
b += b'\x5E\x5B\xC3'                # .ret2
b += b'\xB8\x01\x00\x00\x00\xEB\xF6'  # .one: mov eax,1; jmp .ret2
b += b'\x33\xC0\xEB\xF2'            # .z2: xor eax,eax; jmp .ret2
b += b'\x33\xC0\xC3'                # .z
assert len(b) == 73, len(b)
caves['wclvl'] = bytes(b)

# --- wcexpcost: [self+0x14] else 3
caves['wcexpcost'] = b'\x8B\x40\x14\x85\xC0\x75\x05\xB8\x03\x00\x00\x00\xC3'

# --- wcskillpt: level * expcost
b = bytearray(); base = VA('wcskillpt')
b += b'\x56\x8B\xF0'                # push esi; mov esi,eax
b += b'\x8B\x08\xFF\x51\x70'        # call [ecx+0x70] GetLevel(self,unit)
b += b'\x50\x8B\xC6'                # push eax; mov eax,esi
b += call(base+len(b), VA('wcexpcost'))
b += b'\x5A\x0F\xAF\xC2'            # pop edx; imul eax,edx
b += b'\x5E\xC3'
assert len(b) == 22, len(b)
caves['wcskillpt'] = bytes(b)

# --- wcgetname (+0x58): "Wall Crushing I/II/III"
b = bytearray(); base = VA('wcgetname')
b += b'\x53\x56\x57'
b += b'\x8B\xD8\x8B\xF2\x8B\xF9'    # ebx=self, esi=unit, edi=out
b += b'\x8B\xD6\x8B\xC3'
b += b'\x8B\x08\xFF\x51\x70'        # GetLevel (nil-safe)
b += b'\x8B\xD0\x8B\xCF\x8B\xC3'    # edx=level, ecx=out, eax=self
b += call(base+len(b), LSNAMES)
b += b'\x5F\x5E\x5B\xC3'
assert len(b) == 33, len(b)
caves['wcgetname'] = bytes(b)

# --- wcexpand (+0xD0): ML-data record (id word +0xE, level byte +0xC)
b = bytearray(); base = VA('wcexpand')
b += b'\x53\x56\x57\x55'
b += b'\x8B\xF0\x8B\xFA'            # esi=self, edi=unit
b += b'\x8B\x56\x0C\x8B\xC7'
b += call(base+len(b), FINDDATA)
b += b'\x8B\xE8\x85\xED'
b += b'\x75\x4B'                    # jnz .have (@99)
b += b'\x8B\x56\x0C\x8B\xC7\x8B\x08'
b += b'\xFF\x51\x4C'                # HasAbility
b += b'\x0F\xB6\xD8\x43'            # movzx ebx,al; inc ebx  (level 1|2)
b += b'\xE8\x00\x00\x00\x00'        # call $+5 (PIC)
pop_va = base + len(b)
b += b'\x5A'
b += b'\x8B\x82' + struct.pack('<i', CLASSREF_MLDATA - pop_va)
b += b'\xB2\x01\x33\xC9'
b += call(base+len(b), TOBJCREATE)
b += b'\x8B\xE8'                    # ebp=rec
b += b'\x66\x8B\x46\x0C'            # mov ax,[esi+0xC]  (id)
b += b'\x66\x89\x45\x0E'            # mov [ebp+0xE],ax
b += b'\x88\x5D\x0C'                # mov [ebp+0xC],bl  (level)
b += b'\x6A\x01'                    # push 1
b += b'\x8B\x4E\x0C\x8B\xD7\x8B\xC6'
b += call(base+len(b), SETBIT)
b += b'\x8B\xD5\x8B\xC7'
b += call(base+len(b), ADDDATA)
b += b'\xB0\x01\xEB\x18'            # mov al,1; jmp .out (@123)
assert len(b) == 99, len(b)
b += b'\x0F\xB6\x45\x0C'            # .have: movzx eax,[ebp+0xC]
b += b'\x85\xC0\x75\x01\x40'        # 0 -> 1
b += b'\x83\xF8\x03\x7D\x08'        # cmp 3; jge .fail (@120)
b += b'\x40\x88\x45\x0C'            # inc; store
b += b'\xB0\x01\xEB\x02'            # al=1; jmp .out
b += b'\x32\xC0'                    # .fail
b += b'\x5D\x5F\x5E\x5B\xC3'        # .out @123
assert len(b) == 128, len(b)
caves['wcexpand'] = bytes(b)

# --- wcremove (+0xD4): TU-style (dec level; full remove at level 1)
b = bytearray(); base = VA('wcremove')
b += b'\x53\x56\x57\x55'
b += b'\x8B\xFA\x8B\xE8'            # edi=unit, ebp=self
b += b'\xB3\x01'                    # mov bl,1
b += b'\x8B\x55\x0C\x8B\xC7'        # edx=[ebp+0xC]; eax=edi
b += call(base+len(b), FINDDATA)
b += b'\x8B\xF0\x85\xF6'            # esi=rec
b += b'\x74\x24'                    # jz .norec (@62)
b += b'\x80\x7E\x0C\x01'            # cmp byte [esi+0xC],1
b += b'\x75\x19'                    # jne .dec (@57)
b += b'\x6A\x00'                    # push 0
b += b'\x8B\x4D\x0C\x8B\xD7\x8B\xC5'
b += call(base+len(b), SETBIT)      # remove bit
b += b'\x8B\xD6\x8B\xC7'            # edx=rec; eax=unit
b += call(base+len(b), REMDATA)
b += b'\xEB\x15'                    # jmp .out (@78)
b += b'\xFE\x4E\x0C\xEB\x10'        # .dec: dec [esi+0xC]; jmp .out
b += b'\x6A\x00'                    # .norec @62
b += b'\x8B\x4D\x0C\x8B\xD7\x8B\xC5'
b += call(base+len(b), SETBIT)
b += b'\x33\xDB'                    # xor ebx,ebx
b += b'\x8B\xC3'                    # .out @78: mov eax,ebx
b += b'\x5D\x5F\x5E\x5B\xC3'
assert len(b) == 85, len(b)
caves['wcremove'] = bytes(b)

def push_stat(reg_bytes, slot, movsx):
    """mov eax,<reg>; mov edx,[eax]; call [edx+slot]; (movsx eax,al;) push eax"""
    out = reg_bytes + b'\x8B\x10' + b'\xFF\x92' + struct.pack('<I', slot)
    out += (b'\x0F\xBE\xC0' if movsx else b'') + b'\x50'
    return out

# --- wcest1 (+0xD8 rewrite): (self, EDX=owner strat, ECX=target strat) -> value
b = bytearray(); base = VA('wcest1')
b += b'\x53\x56'
b += b'\x8B\xD9'                    # ebx=target
b += b'\x8B\xC2'                    # eax=owner
b += call(base+len(b), VA('wclvl5s'))
b += b'\x8B\xF0'                    # esi=dmg
for slot, sx in ((0xE0,True),(0xC4,True),(0xCC,True),(0xEC,False),(0xF0,False)):
    b += push_stat(b'\x8B\xC3', slot, sx)
b += b'\x66\xB9\x01\x01'            # mov cx,0x101 (types)
b += b'\x8B\xD6'                    # mov edx,esi (dmg)
b += b'\xB8\x06\x00\x00\x00'        # mov eax,6 (atk)
b += call(base+len(b), VALHELP)
b += b'\x5E\x5B\xC3'
assert len(b) == 96, len(b)
caves['wcest1'] = bytes(b)

# --- wcest2 (+0xDC rewrite): out-record variant, ret 8
b = bytearray(); base = VA('wcest2')
b += b'\x55\x8B\xEC'
b += b'\x53\x56\x57'
b += b'\x8B\xF1'                    # esi=target
b += b'\x8B\x5D\x08'                # ebx=out
b += b'\x8B\xC2'                    # eax=owner (EDX)
b += call(base+len(b), VA('wclvl5s'))
b += b'\x8B\xF8'                    # edi=dmg
b += b'\x80\x7D\x0C\x00'            # cmp byte [ebp+0xC],0
b += b'\x0F\x85' + struct.pack('<i', 0)   # jnz .fail — patched below
jnz_pos = len(b) - 4
for slot, sx in ((0xE0,True),(0xC4,True),(0xCC,True),(0xEC,False),(0xF0,False)):
    b += push_stat(b'\x8B\xC6', slot, sx)
b += b'\x66\xB9\x00\x01'            # mov cx,0x100
b += b'\x8B\xD7'                    # mov edx,edi (dmg)
b += b'\xB8\x06\x00\x00\x00'
b += call(base+len(b), VALHELP)
b += b'\x89\x03'                    # mov [ebx],eax
b += push_stat(b'\x8B\xC6', 0xF0, False)          # push protections
b += b'\x8B\xC6\x8B\x10\xFF\x92\xEC\x00\x00\x00'  # [+0xEC] -> eax
b += b'\x8B\xC8'                    # mov ecx,eax (immunities)
b += b'\x66\xBA\x00\x01'            # mov dx,0x100
b += b'\xB8\x06\x00\x00\x00'        # mov eax,6 (atk)
b += call(base+len(b), HITHELP)
b += b'\x89\x43\x04'                # mov [ebx+4],eax
b += b'\x33\xC0\x89\x43\x08\x89\x43\x0C'
b += b'\xEB\x13'                    # jmp .done
fail_off = len(b)
b[jnz_pos:jnz_pos+4] = struct.pack('<i', fail_off - (jnz_pos + 4))
b += b'\x33\xC0\x89\x03\x89\x43\x04\x89\x43\x08\x89\x43\x0C'
b += b'\x66\xC7\x43\x10\x00\x00'    # mov word [ebx+0x10],0 (fail marker, as vanilla)
done_off = len(b)
assert b[fail_off-2:fail_off] == b'\xEB\x13' and done_off - fail_off == 19, (fail_off, done_off)
b += b'\x5F\x5E\x5B\x5D'
b += b'\xC2\x08\x00'
caves['wcest2'] = bytes(b)

# --- wcexec: replaces `mov ecx,6` in fcExecuteCombatCommand; ESI=attacker combat
b = bytearray(); base = VA('wcexec')
b += b'\x8B\x46\x4C'                # mov eax,[esi+0x4C] (strategic; nil-safe below)
b += call(base+len(b), VA('wclvl5s'))
b += b'\x89\x44\x24\x08'            # mov [esp+8],eax — overwrite pushed DMG (was 6)
b += b'\xB9\x06\x00\x00\x00'        # mov ecx,6 (ATK — replaced instruction)
b += b'\xC3'
assert len(b) == 18, len(b)
caves['wcexec'] = bytes(b)

# --- wcestdmg: replaces `mov edx,6` in +0xE4; owner combat at [ebp-8]; preserves CX
b = bytearray(); base = VA('wcestdmg')
b += b'\x51'                        # push ecx (types)
b += b'\x8B\x45\xF8'                # mov eax,[ebp-8]
b += b'\x85\xC0\x74\x03'            # test; jz .n
b += b'\x8B\x40\x4C'                # mov eax,[eax+0x4C]
b += call(base+len(b), VA('wclvl5s'))
b += b'\x8B\xD0\x59\xC3'            # mov edx,eax; pop ecx; ret
assert len(b) == 20, len(b)
caves['wcestdmg'] = bytes(b)

# --- hook patches
def dword(va): return struct.pack('<I', va)
VMT = 0x20714  # TWallCrushingAbility VMT file offset
PATCHES = [
    (VMT+0x58, dword(0x5574E97C), dword(VA('wcgetname')), 'VMT+0x58 GetName'),
    (VMT+0x70, dword(0x5574E9B0), dword(VA('wclvl')),     'VMT+0x70 GetLevel'),
    (VMT+0x80, dword(0x5574E958), dword(VA('wcskillpt')), 'VMT+0x80 GetSkillPoints'),
    (VMT+0x94, dword(0x5574E954), dword(VA('wclvl')),     'VMT+0x94 GetInherentLevel'),
    (VMT+0xC4, dword(0x5574E8B8), dword(CANEXP_GEN),      'VMT+0xC4 CanExpand (reuse healing cave)'),
    (VMT+0xC8, dword(0x5574E908), dword(VA('wcexpcost')), 'VMT+0xC8 ExpandCost'),
    (VMT+0xCC, dword(0x5574E8F4), dword(EXPNAME_GEN),     'VMT+0xCC ExpandName (reuse healing cave)'),
    (VMT+0xD0, dword(0x5574E90C), dword(VA('wcexpand')),  'VMT+0xD0 Expand'),
    (VMT+0xD4, dword(0x5574E91C), dword(VA('wcremove')),  'VMT+0xD4 Remove'),
    (VMT+0xD8, dword(0x557685B8), dword(VA('wcest1')),    'VMT+0xD8 strategic estimator'),
    (VMT+0xDC, dword(0x55768618), dword(VA('wcest2')),    'VMT+0xDC strategic est record'),
    # fcExecuteCombatCommand: mov ecx,6 -> call wcexec (patches pushed DMG on stack)
    (0x67CF7, b'\xB9\x06\x00\x00\x00', call(0x557688F7, VA('wcexec')), 'exec DMG 6 -> 5*level'),
    # +0xE4 combat estimator: mov edx,6 -> call wcestdmg
    (0x67B52, b'\xBA\x06\x00\x00\x00', call(0x55768752, VA('wcestdmg')), 'combat est DMG -> 5*level'),
]

def main():
    apply = '--apply' in sys.argv
    data = bytearray(open(DLL, 'rb').read())
    ok = True
    for name, off in CAVES.items():
        blob = caves[name]
        if bytes(data[off:off+len(blob)]) != b'\x00'*len(blob):
            print(f'[!] cave {name} region not zero @ {hex(off)}'); ok = False
    hi = max(off+len(caves[n]) for n, off in CAVES.items())
    assert hi <= CAVE_END, hex(hi)
    for off, orig, new, desc in PATCHES:
        cur = bytes(data[off:off+len(orig)])
        if cur != orig:
            print(f'[!] {desc} @ {hex(off)}: expected {orig.hex()} got {cur.hex()}'); ok = False
        assert len(new) == len(orig), desc
    if not ok:
        print('ABORT'); sys.exit(1)
    print('All original bytes + cave zeros verified.')
    for n, off in sorted(CAVES.items(), key=lambda kv: kv[1]):
        print(f'  cave {n:9s} file {hex(off)} VA {hex(off+DELTA)} len {len(caves[n])}')
    if not apply:
        print('DRY RUN ok — rerun with --apply'); return
    if not os.path.exists(BAK):
        shutil.copy2(DLL, BAK); print('backup ->', BAK)
    for n, off in CAVES.items():
        data[off:off+len(caves[n])] = caves[n]
    for off, orig, new, desc in PATCHES:
        data[off:off+len(new)] = new
        print(f'  patched {desc} @ {hex(off)}')
    open(DLL, 'wb').write(data)
    print('APPLIED.')

if __name__ == '__main__':
    main()
