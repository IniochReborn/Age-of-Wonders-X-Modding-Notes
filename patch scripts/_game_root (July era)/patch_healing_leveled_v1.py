#!/usr/bin/env python3
"""
Healing I/II/III leveled ability patch (v1) — AoWEPACK.dll
==========================================================
Converts Healing (ability id 0x2F, THealingAbility : TTouchAbility) into a
3-level ability: I=5 HP, II=7 HP, III=10 HP (combat touch + strategic touch).

Design (mirrors proven TU/DM machinery):
- Level stored at THealingAbilityData +0xD (byte). +0xC stays the transient
  used/enabled flag. No record or level 0 => level 1 (legacy/authored units
  heal 5 = vanilla). Persistence: data ReadWrite gains tagged field 0xB
  (byte, stream method +0x30) exactly like TDispelMagicAbilityData.ReadWrite.
- VMT repoints add GetLevel/GetInherentLevel/CanExpand/ExpandCost/ExpandName/
  Expand/Remove(dec-level)/GetSkillPoints + leveled AI estimators (+0xD8/+0xDC).
- HealUnit (0x5576C374) contract changed: EAX = HEALER strategic unit (was
  unused flyweight); full cave rewrite computes amount 5/7/10 by healer level.
  Both callers patched (THealingCA.Execute passes [edi+0x4C]; THealingTE.Execute
  passes ESI).
- Combat estimator (+0xE4) call to GetHealHitPoints retargeted to cave that
  reads healer combat unit from caller frame [ebp-4] (saved EDX param).
- GetName plain branch hooked in place -> "Healing I/II/III" via generic
  cave_lsnames (0x5580E2A0, from lifesteal-leveled patch — REQUIRED).
- ExpandCost: vanilla [self+0x14] if nonzero, else 10 skill points per level.

Hero buys levels at level-up (CanExpand mask gate 0x241 kept = same classes
as Dispel Magic). Level-up dialog shows "Healing II/III" via ExpandName.

Run: python patch_healing_leveled_v1.py [--apply]   (dry-run default)
Revert: restore AoWEPACK.dll.bak_healing_lvl
"""
import struct, sys, shutil, os

DLL   = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'AoWEPACK.dll')
BAK   = DLL + '.bak_healing_lvl'
DELTA = 0x55700C00  # VA = file_off + DELTA

# ---- fixed engine addresses (VA) ----
FINDDATA    = 0x5574F1C4   # (EAX=strat unit, EDX=ability id) -> rec | nil
ADDDATA     = 0x5574F278   # (EAX=unit, EDX=rec)
SETBIT      = 0x5574E718   # (EAX=self, EDX=unit, ECX=id, push flag) add/remove bit+notify
TOBJCREATE  = 0x55703064   # (EAX=class, DL=1, ECX=0) -> obj
PARENT_RW   = 0x5574E5EC   # TAbilityData.ReadWrite
LSNAMES     = 0x5580E2A0   # generic cave: (EAX=ability, EDX=level, ECX=out) name+" I/II/III"
ORIG_REMOVE = 0x5576C04C   # original THealingAbility.Remove
CLASSREF_HD = 0x55721550   # global: THealingAbilityData class ref
HEALUNIT    = 0x5576C374   # original HealUnit entry (hooked)

# ---- cave layout (file offset, VA) ----
CAVES = {
    'healamt': 0x10DAE0, 'getlvl': 0x10DB20, 'canexp': 0x10DB70,
    'expcost': 0x10DBA0, 'skillpt': 0x10DBB0, 'expname': 0x10DBC0,
    'expand': 0x10DBF0, 'remove': 0x10DC70, 'est1': 0x10DCA0,
    'est2': 0x10DCF0, 'esthp': 0x10DD70, 'heal': 0x10DDB0,
    'gnplain': 0x10DE90, 'datarw': 0x10DEB0,
}
CAVE_END = 0x10DF00   # free-space region verified zeros to 0x10E400
def VA(name): return CAVES[name] + DELTA

def rel32(src_va, dst_va):
    """rel32 for E8/E9 whose opcode starts at src_va"""
    return struct.pack('<i', dst_va - (src_va + 5))

def asm_call(pos_va, dst): return b'\xE8' + rel32(pos_va, dst)
def asm_jmp(pos_va, dst):  return b'\xE9' + rel32(pos_va, dst)

caves = {}

# ---------------- cave_healamt: (EAX=strat unit|nil) -> EAX=5/7/10, preserves ecx/edx
b = bytearray(); base = VA('healamt')
b += b'\x51\x52'                    # push ecx; push edx
b += b'\x85\xC0\x74\x20'            # test eax,eax; jz .l1
b += b'\xBA\x2F\x00\x00\x00'        # mov edx,0x2F
b += asm_call(base+len(b), FINDDATA)
b += b'\x85\xC0\x74\x12'            # test eax,eax; jz .l1
b += b'\x0F\xB6\x40\x0D'            # movzx eax, byte [eax+0xD]
b += b'\x83\xF8\x02'                # cmp eax,2
b += b'\x72\x09'                    # jb .l1
b += b'\x74\x0E'                    # je .l2
b += b'\xB8\x0A\x00\x00\x00'        # mov eax,10
b += b'\xEB\x0C'                    # jmp .done
# .l1 @38
b += b'\xB8\x05\x00\x00\x00'        # mov eax,5
b += b'\xEB\x05'                    # jmp .done
# .l2 @45
b += b'\xB8\x07\x00\x00\x00'        # mov eax,7
# .done @50
b += b'\x5A\x59\xC3'                # pop edx; pop ecx; ret
assert len(b) == 53, len(b)
caves['healamt'] = bytes(b)

# ---------------- cave_getlvl: (EAX=self, EDX=strat unit) -> 0 / 1..3   (+0x70 & +0x94)
b = bytearray(); base = VA('getlvl')
b += b'\x85\xD2\x74\x42'            # test edx,edx; jz .z (@70)
b += b'\x53\x56'                    # push ebx; push esi
b += b'\x8B\xD8\x8B\xF2'            # mov ebx,eax; mov esi,edx
b += b'\x8B\x53\x0C'                # mov edx,[ebx+0xC]
b += b'\x8B\xC6\x8B\x08'            # mov eax,esi; mov ecx,[eax]
b += b'\xFF\x51\x4C'                # call [ecx+0x4C]  HasAbility
b += b'\x84\xC0\x74\x2A'            # test al,al; jz .z2 (@66)
b += b'\x8B\x53\x0C'                # mov edx,[ebx+0xC]
b += b'\x8B\xC6'                    # mov eax,esi
b += asm_call(base+len(b), FINDDATA)
b += b'\x85\xC0\x74\x15'            # test eax,eax; jz .one (@59)
b += b'\x0F\xB6\x40\x0D'            # movzx eax, byte [eax+0xD]
b += b'\x85\xC0\x74\x0D'            # test eax,eax; jz .one
b += b'\x83\xF8\x03\x7E\x05'        # cmp eax,3; jle .ret2 (@56)
b += b'\xB8\x03\x00\x00\x00'        # mov eax,3
# .ret2 @56
b += b'\x5E\x5B\xC3'                # pop esi; pop ebx; ret
# .one @59
b += b'\xB8\x01\x00\x00\x00'        # mov eax,1
b += b'\xEB\xF6'                    # jmp .ret2
# .z2 @66
b += b'\x33\xC0\xEB\xF2'            # xor eax,eax; jmp .ret2
# .z @70
b += b'\x33\xC0\xC3'                # xor eax,eax; ret
assert len(b) == 73, len(b)
caves['getlvl'] = bytes(b)

# ---------------- cave_canexp: (EAX=self, EDX=unit) -> AL   (+0xC4)
b = bytearray(); base = VA('canexp')
b += b'\x53\x56'                    # push ebx; push esi
b += b'\x8B\xD8\x8B\xF2'            # ebx=self, esi=unit
b += b'\x8B\xC6\x8B\x10'            # mov eax,esi; mov edx,[eax]
b += b'\xFF\x92\x8C\x00\x00\x00'    # call [edx+0x8C]  unit class mask
b += b'\x66\x23\x43\x20'            # and ax, [ebx+0x20]
b += b'\x74\x13'                    # jz .no (@41)
b += b'\x8B\xD6\x8B\xC3'            # mov edx,esi; mov eax,ebx
b += b'\x8B\x08\xFF\x51\x70'        # mov ecx,[eax]; call [ecx+0x70]  GetLevel
b += b'\x83\xF8\x03\x7D\x05'        # cmp eax,3; jge .no
b += b'\xB0\x01\x5E\x5B\xC3'        # mov al,1; pop esi; pop ebx; ret
# .no @41
b += b'\x33\xC0\x5E\x5B\xC3'        # xor eax,eax; pops; ret
assert len(b) == 46, len(b)
caves['canexp'] = bytes(b)

# ---------------- cave_expcost: (EAX=self) -> cost   (+0xC8)
b = bytearray()
b += b'\x8B\x40\x14'                # mov eax,[eax+0x14]  vanilla data-driven cost
b += b'\x85\xC0\x75\x05'            # test; jnz .r
b += b'\xB8\x0A\x00\x00\x00'        # mov eax,10 (fallback)
b += b'\xC3'                        # .r: ret
assert len(b) == 13, len(b)
caves['expcost'] = bytes(b)

# ---------------- cave_skillpt: (EAX=self, EDX=unit) -> level*[self+0x14]   (+0x80)
# v1b fix: charge at level-up = GetSkillPoints DELTA, so per-level factor must
# equal ExpandCost ([self+0x14] = 5 for Healing) or display(5) != charge.
b = bytearray()
b += b'\x56\x8B\xF0'                # push esi; mov esi,eax
b += b'\x8B\x08\xFF\x51\x70'        # mov ecx,[eax]; call [ecx+0x70]  GetLevel
b += b'\x0F\xAF\x46\x14'            # imul eax,[esi+0x14]
b += b'\x5E\xC3'                    # pop esi; ret
assert len(b) == 14, len(b)
caves['skillpt'] = bytes(b)

# ---------------- cave_expname: (EAX=self, EDX=unit, ECX=out)   (+0xCC)
b = bytearray(); base = VA('expname')
b += b'\x53\x56\x57'                # push ebx/esi/edi
b += b'\x8B\xD8\x8B\xF2\x8B\xF9'    # ebx=self, esi=unit, edi=out
b += b'\x8B\xD6\x8B\xC3'            # edx=unit, eax=self
b += b'\x8B\x08\xFF\x51\x70'        # call [ecx+0x70]  GetLevel
b += b'\x40'                        # inc eax  (next level)
b += b'\x8B\xD0\x8B\xCF\x8B\xC3'    # edx=level, ecx=out, eax=self
b += asm_call(base+len(b), LSNAMES)
b += b'\x5F\x5E\x5B\xC3'            # pops; ret
assert len(b) == 34, len(b)
caves['expname'] = bytes(b)

# ---------------- cave_expand: (EAX=self, EDX=unit) -> AL   (+0xD0)
b = bytearray(); base = VA('expand')
b += b'\x53\x56\x57\x55'            # push ebx/esi/edi/ebp
b += b'\x8B\xF0\x8B\xFA'            # esi=self, edi=unit
b += b'\x8B\x56\x0C\x8B\xC7'        # mov edx,[esi+0xC]; mov eax,edi
b += asm_call(base+len(b), FINDDATA)
b += b'\x8B\xE8\x85\xED'            # mov ebp,eax; test ebp,ebp
b += b'\x75\x47'                    # jnz .have (@95)
# create path (@24)
b += b'\x8B\x56\x0C\x8B\xC7\x8B\x08' # mov edx,[esi+0xC]; mov eax,edi; mov ecx,[eax]
b += b'\xFF\x51\x4C'                # call [ecx+0x4C]  HasAbility
b += b'\x0F\xB6\xD8\x43'            # movzx ebx,al; inc ebx   level = has?2:1
# PIC classref read (@38)
b += b'\xE8\x00\x00\x00\x00'        # call $+5
pop_va = base + len(b)              # address of the pop (what call pushed)
b += b'\x5A'                        # pop edx
b += b'\x8B\x82' + struct.pack('<i', CLASSREF_HD - pop_va)  # mov eax,[edx+disp]
b += b'\xB2\x01\x33\xC9'            # mov dl,1; xor ecx,ecx
b += asm_call(base+len(b), TOBJCREATE)
b += b'\x8B\xE8'                    # mov ebp,eax  (rec)
b += b'\xC6\x45\x0C\x01'            # mov byte [ebp+0xC],1  enabled
b += b'\x88\x5D\x0D'                # mov [ebp+0xD],bl      level
b += b'\x6A\x01'                    # push 1
b += b'\x8B\x4E\x0C\x8B\xD7\x8B\xC6' # ecx=[esi+0xC]; edx=edi; eax=esi
b += asm_call(base+len(b), SETBIT)
b += b'\x8B\xD5\x8B\xC7'            # edx=ebp(rec); eax=edi(unit)
b += asm_call(base+len(b), ADDDATA)
b += b'\xB0\x01\xEB\x18'            # mov al,1; jmp .out (@119)
# .have @95
assert len(b) == 95, len(b)
b += b'\x0F\xB6\x45\x0D'            # movzx eax,byte [ebp+0xD]
b += b'\x85\xC0\x75\x01\x40'        # test; jnz .n0; inc eax   (0 -> 1)
b += b'\x83\xF8\x03\x7D\x09'        # cmp eax,3; jge .fail (@117)
b += b'\x40\x88\x45\x0D'            # inc eax; mov [ebp+0xD],al
b += b'\xB0\x01\xEB\x02'            # mov al,1; jmp .out
# .fail @117
b += b'\x32\xC0'                    # xor al,al
# .out @119
b += b'\x5D\x5F\x5E\x5B\xC3'        # pop ebp/edi/esi/ebx; ret
assert len(b) == 124, len(b)
caves['expand'] = bytes(b)

# ---------------- cave_remove: (EAX=self, EDX=unit)   (+0xD4)
b = bytearray(); base = VA('remove')
b += b'\x53\x56'                    # push ebx/esi
b += b'\x8B\xF0\x8B\xDA'            # esi=self, ebx=unit
b += b'\x8B\x56\x0C\x8B\xC3'        # mov edx,[esi+0xC]; mov eax,ebx
b += asm_call(base+len(b), FINDDATA)
b += b'\x85\xC0\x74\x0E'            # test eax,eax; jz .orig (@34)
b += b'\x80\x78\x0D\x01\x76\x08'    # cmp byte [eax+0xD],1; jbe .orig
b += b'\xFE\x48\x0D'                # dec byte [eax+0xD]
b += b'\xB0\x01\x5E\x5B\xC3'        # mov al,1; pops; ret
# .orig @34
b += b'\x8B\xD3\x8B\xC6'            # edx=ebx(unit); eax=esi(self)
b += b'\x5E\x5B'                    # pops
b += asm_jmp(base+len(b), ORIG_REMOVE)
assert len(b) == 45, len(b)
caves['remove'] = bytes(b)

# ---------------- cave_est1: (EAX=self, EDX=healer strat, ECX=target strat) -> value  (+0xD8)
b = bytearray(); base = VA('est1')
b += b'\x53\x56'                    # push ebx/esi
b += b'\x8B\xD9\x8B\xF2'            # ebx=target, esi=healer
b += b'\x8B\xC3\x8B\x10'            # mov eax,ebx; mov edx,[eax]
b += b'\xFF\x92\xEC\x00\x00\x00'    # call [edx+0xEC]  immunities
b += b'\xF6\xC4\x02\x75\x31'        # test ah,2; jnz .zero (@70)
b += b'\x8B\xC3\x8B\x10'            # eax=ebx; edx=[eax]
b += b'\xFF\x92\xD0\x00\x00\x00'    # call [edx+0xD0]  GetMaxHP
b += b'\x0F\xBE\xC0\x50'            # movsx eax,al; push eax
b += b'\x8B\xC3\x8B\x10'
b += b'\xFF\x92\xE0\x00\x00\x00'    # call [edx+0xE0]  GetHitPoints
b += b'\x0F\xBE\xC0\x5A'            # movsx eax,al; pop edx
b += b'\x2B\xD0'                    # sub edx,eax    diff
b += b'\x8B\xC6'                    # mov eax,esi    healer
b += asm_call(base+len(b), VA('healamt'))
b += b'\x3B\xD0\x7D\x02\x8B\xC2'    # cmp edx,eax; jge .k; mov eax,edx
b += b'\x6B\xC0\x64'                # .k: imul eax,eax,0x64
b += b'\x5E\x5B\xC3'                # pops; ret
# .zero @70
b += b'\x33\xC0\x5E\x5B\xC3'
assert len(b) == 75, len(b)
caves['est1'] = bytes(b)

# ---------------- cave_est2: (self, EDX=healer, ECX=target, [ebp+8]=out, [ebp+C]=flag) ret 8  (+0xDC)
b = bytearray(); base = VA('est2')
b += b'\x55\x8B\xEC'                # push ebp; mov ebp,esp
b += b'\x53\x56\x57'                # push ebx/esi/edi
b += b'\x8B\xF1\x8B\xFA'            # esi=target, edi=healer
b += b'\x8B\x5D\x08'                # mov ebx,[ebp+8]  out
b += b'\x80\x7D\x0C\x00\x75\x52'    # cmp byte [ebp+0xC],0; jnz .fail (@101)
b += b'\x8B\xC6\x8B\x10'            # eax=esi; edx=[eax]
b += b'\xFF\x92\xEC\x00\x00\x00'    # call [edx+0xEC]
b += b'\xF6\xC4\x02\x75\x43'        # test ah,2; jnz .fail
b += b'\x8B\xC6\x8B\x10'
b += b'\xFF\x92\xD0\x00\x00\x00'    # GetMaxHP
b += b'\x0F\xBE\xC0\x50'            # movsx eax,al; push eax
b += b'\x8B\xC6\x8B\x10'
b += b'\xFF\x92\xE0\x00\x00\x00'    # GetHitPoints
b += b'\x0F\xBE\xC0\x5A'            # movsx eax,al; pop edx
b += b'\x2B\xD0'                    # sub edx,eax
b += b'\x8B\xC7'                    # mov eax,edi  healer
b += asm_call(base+len(b), VA('healamt'))
b += b'\x3B\xD0\x7D\x02\x8B\xC2'    # min(diff, amt)
# .k @77
b += b'\x89\x43\x04'                # mov [ebx+4],eax   amount
b += b'\x6B\xC0\x64\x89\x03'        # imul eax,eax,0x64; mov [ebx],eax  value
b += b'\x33\xC0\x89\x43\x08\x89\x43\x0C'  # zero [ebx+8],[ebx+0xC]
b += b'\x66\xC7\x43\x10\x00\x02'    # mov word [ebx+0x10],0x200
b += b'\xEB\x13'                    # jmp .done (@120)
# .fail @101
assert len(b) == 101, len(b)
b += b'\x33\xC0\x89\x03\x89\x43\x04\x89\x43\x08\x89\x43\x0C'
b += b'\x66\xC7\x43\x10\x00\x00'    # mov word [ebx+0x10],0
# .done @120
b += b'\x5F\x5E\x5B\x5D'            # pops; pop ebp
b += b'\xC2\x08\x00'                # ret 8
assert len(b) == 127, len(b)
caves['est2'] = bytes(b)

# ---------------- cave_esthp: (EDX=target combat; healer combat at caller [ebp-4]) -> amount
b = bytearray(); base = VA('esthp')
b += b'\x53\x56'                    # push ebx/esi
b += b'\x8B\xF2'                    # esi=target
b += b'\x8B\x45\xFC'                # mov eax,[ebp-4]  healer combat (caller frame)
b += b'\x85\xC0\x74\x03'            # test; jz .noh
b += b'\x8B\x40\x4C'                # mov eax,[eax+0x4C]  strategic twin
b += asm_call(base+len(b), VA('healamt'))   # .noh
b += b'\x8B\xD8'                    # mov ebx,eax  amt
b += b'\x8B\xC6\x8B\x10'            # eax=esi; edx=[eax]
b += b'\xFF\x92\x84\x00\x00\x00'    # call [edx+0x84]  combat GetMaxHP
b += b'\x0F\xBE\xC0\x50'            # movsx; push
b += b'\x8B\xC6\x8B\x10'
b += b'\xFF\x92\x88\x00\x00\x00'    # call [edx+0x88]  combat GetHitPoints
b += b'\x0F\xBE\xC0\x5A'            # movsx eax,al; pop edx
b += b'\x2B\xD0'                    # sub edx,eax
b += b'\x3B\xD3\x7D\x02\x8B\xDA'    # cmp edx,ebx; jge .k; mov ebx,edx
b += b'\x8B\xC3'                    # .k: mov eax,ebx
b += b'\x5E\x5B\xC3'                # pops; ret
assert len(b) == 62, len(b)
caves['esthp'] = bytes(b)

# ---------------- cave_heal: HealUnit rewrite. (EAX=healer strat, EDX=target strat) -> AL changed
b = bytearray(); base = VA('heal')
b += b'\x53\x56\x57'                # push ebx/esi/edi
b += b'\x8B\xF2'                    # esi=target
b += asm_call(base+len(b), VA('healamt'))  # amt from healer (EAX)
b += b'\x8B\xF8'                    # edi=amt
b += b'\x33\xDB'                    # xor ebx,ebx  changed flag
b += b'\x8B\xC6\x8B\x10'            # eax=esi; edx=[eax]
b += b'\xFF\x92\xD0\x00\x00\x00'    # GetMaxHP
b += b'\x50'                        # push eax
b += b'\x8B\xC6\x8B\x10'
b += b'\xFF\x92\xE0\x00\x00\x00'    # GetHitPoints
b += b'\x5A'                        # pop edx
b += b'\x3A\xD0\x74\x3C'            # cmp dl,al; je .cure (@100)
b += b'\x8B\xC6\x8B\x10'
b += b'\xFF\x92\xD0\x00\x00\x00'    # GetMaxHP
b += b'\x0F\xBE\xD8'                # movsx ebx,al
b += b'\x8B\xC6\x8B\x10'
b += b'\xFF\x92\xE0\x00\x00\x00'    # GetHitPoints
b += b'\x0F\xBE\xC0'                # movsx eax,al
b += b'\x2B\xD8'                    # sub ebx,eax   diff
b += b'\x3B\xDF\x7E\x02\x8B\xDF'    # cmp ebx,edi; jle .cl; mov ebx,edi
b += b'\x8B\xC6\x8B\x10'            # .cl
b += b'\xFF\x92\xE0\x00\x00\x00'    # GetHitPoints
b += b'\x8B\xD0\x02\xD3'            # mov edx,eax; add dl,bl
b += b'\x8B\xC6\x8B\x08'            # eax=esi; ecx=[eax]
b += b'\xFF\x91\xE4\x00\x00\x00'    # SetHitPoints(dl)
b += b'\xB3\x01'                    # mov bl,1
# .cure @100
assert len(b) == 100, len(b)
for aid in (0x60, 0x35, 0x6C):      # Poisoned / disease / Panicked debuffs cured
    b += b'\xBA' + struct.pack('<I', aid)      # mov edx,id
    b += b'\x8B\xC6\x8B\x08'                   # eax=esi; ecx=[eax]
    b += b'\xFF\x91\x48\x01\x00\x00'           # call [ecx+0x148] GetAbilityEnabled
    b += b'\x84\xC0\x74\x11'                   # test al,al; jz next block
    b += b'\xBA' + struct.pack('<I', aid)
    b += b'\x8B\xC6\x8B\x08'
    b += b'\xFF\x91\x98\x00\x00\x00'           # call [ecx+0x98] RemoveAbility
    b += b'\xB3\x01'                           # mov bl,1
assert len(b) == 208, len(b)
b += b'\x8B\xC6\x8B\x10'            # eax=esi; edx=[eax]
b += b'\xFF\x92\x90\x00\x00\x00'    # call [edx+0x90]  update
b += b'\x8B\xC3'                    # mov eax,ebx
b += b'\x5F\x5E\x5B\xC3'            # pops; ret
assert len(b) == 224, len(b)
caves['heal'] = bytes(b)

# ---------------- cave_gnplain: GetName plain-branch (ebx=self, esi=unit, edi=out live)
b = bytearray(); base = VA('gnplain')
b += b'\x8B\xD6\x8B\xC3'            # edx=esi(unit); eax=ebx(self)
b += b'\x8B\x08\xFF\x51\x70'        # call [ecx+0x70]  GetLevel (nil-safe)
b += b'\x8B\xD0\x8B\xCF\x8B\xC3'    # edx=level; ecx=edi(out); eax=ebx
b += asm_jmp(base+len(b), LSNAMES)  # tail-jmp; lsnames rets to hook site
assert len(b) == 20, len(b)
caves['gnplain'] = bytes(b)

# ---------------- cave_datarw: THealingAbilityData.ReadWrite + tagged level byte
b = bytearray(); base = VA('datarw')
b += b'\x53\x56\x57'                # push ebx/esi/edi
b += b'\x8B\xF2\x8B\xD8'            # esi=stream, ebx=self
b += b'\x8B\xD6\x8B\xC3'            # edx=esi; eax=ebx
b += asm_call(base+len(b), PARENT_RW)
b += b'\x8D\x53\x0C'                # lea edx,[ebx+0xC]
b += b'\xB9\x0A\x00\x00\x00'        # mov ecx,0xA
b += b'\x8B\xC6\x8B\x38'            # eax=esi; edi=[eax]
b += b'\xFF\x57\x38'                # call [edi+0x38]   (enabled byte, tag 0xA — vanilla)
b += b'\x8D\x53\x0D'                # lea edx,[ebx+0xD]
b += b'\xB9\x0B\x00\x00\x00'        # mov ecx,0xB
b += b'\x8B\xC6\x8B\x18'            # eax=esi; ebx=[eax]
b += b'\xFF\x53\x30'                # call [ebx+0x30]   (level byte, tag 0xB — like DM data)
b += b'\x5F\x5E\x5B\xC3'
assert len(b) == 50, len(b)
caves['datarw'] = bytes(b)

# ---------------- hook patches: (file_off, original bytes, new bytes, desc)
def dword(va): return struct.pack('<I', va)
PATCHES = [
    # VMT repoints (THealingAbility VMT file 0x20BBC)
    (0x20C2C, dword(0x5574E9B0), dword(VA('getlvl')),  'VMT+0x70 GetLevel'),
    (0x20C50, dword(0x5574E954), dword(VA('getlvl')),  'VMT+0x94 GetInherentLevel'),
    (0x20C3C, dword(0x5574E958), dword(VA('skillpt')), 'VMT+0x80 GetSkillPoints'),
    (0x20C80, dword(0x5574E8B8), dword(VA('canexp')),  'VMT+0xC4 CanExpand'),
    (0x20C84, dword(0x5574E908), dword(VA('expcost')), 'VMT+0xC8 ExpandCost'),
    (0x20C88, dword(0x5574E8F4), dword(VA('expname')), 'VMT+0xCC ExpandName'),
    (0x20C8C, dword(0x5574E90C), dword(VA('expand')),  'VMT+0xD0 Expand'),
    (0x20C90, dword(0x5576C04C), dword(VA('remove')),  'VMT+0xD4 Remove (dec-level)'),
    (0x20C94, dword(0x5576C214), dword(VA('est1')),    'VMT+0xD8 strategic estimator'),
    (0x20C98, dword(0x5576C258), dword(VA('est2')),    'VMT+0xDC strategic est record'),
    # THealingAbilityData VMT (file 0x20990)
    (0x209A8, dword(0x5576BE18), dword(VA('datarw')),  'DataVMT+0x18 ReadWrite'),
    # HealUnit entry -> cave (contract: EAX=healer strat unit)
    (0x6B774, bytes.fromhex('53568bf233db'),
              asm_jmp(HEALUNIT, VA('heal')) + b'\x90', 'HealUnit entry JMP'),
    # THealingCA.Execute: pass healer [edi+0x4C] instead of GetAbility(0x2F)
    (0x6B124, bytes.fromhex('a144a08f558b8080000000ba2f000000e88744feff'),
              b'\x8B\x47\x4C' + b'\x90'*18, 'CA.Execute healer arg'),
    # THealingTE.Execute: mov eax,ebp -> mov eax,esi (healer)
    (0x6BB8D, b'\x8B\xC5', b'\x8B\xC6', 'TE.Execute healer arg'),
    # est +0xE4: call GetHealHitPoints -> cave_esthp  *** REVERTED 2026-07-21 ***
    # cave_esthp dereferenced [ebp-4] (source/healer param) -> [+0x4c] -> FINDDATA.
    # In the TACTICAL touch-token ExeStrike path that param is NOT a strategic-capable
    # unit, so FINDDATA faulted -> "Error during Token ExeStrike / TCTouchToken 47"
    # (47 = 0x2F = Healing id). The real heal (cave_heal/HealUnit) already applies the
    # correct 5/7/10, so this hook is unnecessary — left as vanilla GetHealHitPoints.
    # (esthp cave is still built below but is now DEAD/unreferenced; AI heal-estimate
    #  is vanilla flat-5, actual heal stays leveled.)
    # (0x6B71F, b'\xE8\x50\xFD\xFF\xFF', asm_call(0x5576C31F, VA('esthp')), 'combat estimator call'),
    # GetName plain branch -> cave_gnplain (keep jmp +0x3F after)
    (0x6B3BF, bytes.fromhex('8bc78b5308e88f51f9ff'),
              asm_call(0x5576BFBF, VA('gnplain')) + b'\x90'*5, 'GetName suffix hook'),
]

def main():
    apply = '--apply' in sys.argv
    data = bytearray(open(DLL, 'rb').read())
    ok = True
    # verify cave region zeros
    for name, off in CAVES.items():
        blob = caves[name]
        region = bytes(data[off:off+len(blob)])
        if region != b'\x00'*len(blob):
            print(f'[!] cave {name} @ {hex(off)}: region NOT zero'); ok = False
    hi = max(off+len(caves[n]) for n, off in CAVES.items())
    assert hi <= CAVE_END, hex(hi)
    # verify hook originals
    for off, orig, new, desc in PATCHES:
        cur = bytes(data[off:off+len(orig)])
        if cur != orig:
            print(f'[!] {desc} @ {hex(off)}: expected {orig.hex()} got {cur.hex()}'); ok = False
        assert len(new) == len(orig), desc
    if not ok:
        print('ABORT: verification failed'); sys.exit(1)
    print('All original bytes + cave zeros verified.')
    for name, off in sorted(CAVES.items(), key=lambda kv: kv[1]):
        print(f'  cave {name:8s} file {hex(off)} VA {hex(off+DELTA)} len {len(caves[name])}')
    if not apply:
        print('DRY RUN ok — rerun with --apply'); return
    if not os.path.exists(BAK):
        shutil.copy2(DLL, BAK); print('backup ->', BAK)
    for name, off in CAVES.items():
        data[off:off+len(caves[name])] = caves[name]
    for off, orig, new, desc in PATCHES:
        data[off:off+len(new)] = new
        print(f'  patched {desc} @ {hex(off)}')
    open(DLL, 'wb').write(data)
    print('APPLIED.')

if __name__ == '__main__':
    main()
