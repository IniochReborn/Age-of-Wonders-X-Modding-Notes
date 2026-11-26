"""
Reflecting Pool Raze patch v1 — makes Reflecting Pools razeable.

Changes to AoWEPACK.dll:
1. TReflectingPoolResource.Create: razeable flag [res+0x58] 0 -> 1
2. Code caves (free space at 0x10B6A0):
   - GetRazed:  returns bit0 of [self+0x39] (padding byte, zero-initialized)
   - SetRazed:  set -> call TReflectingPool.Deactivate (removes vision/delists
                from owner), clear owner byte [self+0x30]=FF, set razed bit.
                clear (rebuild) -> clear razed bit.
   - ReadWrite: call TPlayerStructure.ReadWrite, then serialize [self+0x39]
                as byte field id 0x70 (serializer is keyed-field based:
                missing id on read -> zero fill; zero value -> not written,
                so old saves/maps stay fully compatible)
3. TReflectingPool VMT slots redirected to the caves:
   +0x018 ReadWrite, +0x14C SetRazed, +0x150 GetRazed
   (+0x154 GetRazeable stays inherited - reads the resource flag from #1)

Field ids already used in the pool's record chain: TMapObject=1,
TMultiHexMO=3,4, TStructure=0,0x62,0x63, TPlayerStructure=5,6,7 -> 0x70 free.
"""
import shutil, struct, sys

DLL = "AoWEPACK.dll"
BAK = "AoWEPACK.dll.bak_reflecting_pool_raze"
FILE2VA = 0x55700C00  # CODE: VA = file_offset + this

CAVE_GETRAZED  = 0x10B6A0
CAVE_SETRAZED  = 0x10B6B0
CAVE_READWRITE = 0x10B6D8
CAVE_END       = 0x10B700

data = bytearray(open(DLL, "rb").read())
va = lambda off: off + FILE2VA
off_of = lambda v: v - FILE2VA

def find_once(pattern, what):
    i = data.find(pattern)
    if i < 0:
        sys.exit(f"FAIL: pattern for {what} not found")
    if data.find(pattern, i + 1) >= 0:
        sys.exit(f"FAIL: pattern for {what} not unique")
    print(f"  {what}: file 0x{i:X} (VA 0x{va(i):08X})")
    return i

print("== Locating patch sites ==")

# 1. TReflectingPoolResource.Create tail: mov [esi+44h],1; [esi+45h],0; [esi+64h],0; [esi+58h],0
res_create = find_once(bytes.fromhex("C6464401C6464500C6466400C6465800"),
                       "TReflectingPoolResource.Create flag block")
flag_off = res_create + 15  # the 00 of 'C6 46 58 00'

# 2. TReflectingPool VMT via class name
name = b"\x0FTReflectingPool"
hits = []
i = data.find(name)
while i >= 0:
    hits.append(i)
    i = data.find(name, i + 1)
vmt = None
for h in hits:
    name_va = va(h)
    p = data.find(struct.pack("<I", name_va))
    while p >= 0:
        oe = p - 0x20                      # Object_Entry: name ptr at +0x20
        self_ptr = struct.unpack_from("<I", data, oe)[0]
        inst_size = struct.unpack_from("<I", data, oe + 0x24)[0]
        if self_ptr == va(oe + 0x40) and inst_size == 0x40:
            vmt = oe + 0x40
            break
        p = data.find(struct.pack("<I", name_va), p + 1)
    if vmt:
        break
if not vmt:
    sys.exit("FAIL: TReflectingPool VMT not found")
print(f"  TReflectingPool VMT_Entry: file 0x{vmt:X} (VA 0x{va(vmt):08X})")

slot = lambda o: struct.unpack_from("<I", data, vmt + o)[0]

# 3. Validate current slot contents
# TStructure stubs: GetRazeable(8B4008 8A4058 C3) 90 GetRazed(33C0 C3) 90 SetRazed(C3)
stubs = find_once(bytes.fromhex("8B40088A4058C39033C0C390C3"),
                  "TStructure GetRazeable/GetRazed/SetRazed stubs")
va_getrazeable = va(stubs)
va_getrazed    = va(stubs + 8)
va_setrazed    = va(stubs + 12)

assert slot(0x14C) == va_setrazed,    f"slot 0x14C != TStructure.SetRazed (got {slot(0x14C):08X}, want {va_setrazed:08X})"
assert slot(0x150) == va_getrazed,    f"slot 0x150 != TStructure.GetRazed"
assert slot(0x154) == va_getrazeable, f"slot 0x154 != TStructure.GetRazeable"
print("  VMT slots 0x14C/0x150/0x154 verified = TStructure stubs")

# Pool ReadWrite (slot 0x18): 'call TPlayerStructure.ReadWrite; ret' -> extract target
pool_rw_off = off_of(slot(0x18))
assert data[pool_rw_off] == 0xE8 and data[pool_rw_off + 5] == 0xC3, \
    "pool ReadWrite is not call+ret"
va_tps_readwrite = va(pool_rw_off + 5) + struct.unpack_from("<i", data, pool_rw_off + 1)[0]
# sanity: TPlayerStructure.ReadWrite starts push ebx/esi/edi; mov esi,edx; mov ebx,eax
assert data[off_of(va_tps_readwrite):off_of(va_tps_readwrite) + 7] == bytes.fromhex("5356578BF28BD8"), \
    "TPlayerStructure.ReadWrite prologue mismatch"
print(f"  TPlayerStructure.ReadWrite: VA 0x{va_tps_readwrite:08X}")

# Deactivate (slot 0xE4): starts push ebx/esi; mov esi,eax; mov eax,esi; call ...
va_deactivate = slot(0xE4)
assert data[off_of(va_deactivate):off_of(va_deactivate) + 6] == bytes.fromhex("53568BF08BC6"), \
    "TReflectingPool.Deactivate prologue mismatch"
print(f"  TReflectingPool.Deactivate: VA 0x{va_deactivate:08X}")

# 4. Verify cave space is free
if any(data[CAVE_GETRAZED:CAVE_END]):
    sys.exit("FAIL: cave space 0x10B6A0-0x10B700 not empty")
print(f"  cave space 0x{CAVE_GETRAZED:X}-0x{CAVE_END:X} verified zero")

# Verify razeable flag byte is currently 0
assert data[flag_off] == 0x00, "razeable flag not 00 - already patched?"

print("== Applying ==")
shutil.copyfile(DLL, BAK)
print(f"  backup -> {BAK}")

rel = lambda frm_end, to_va: struct.pack("<i", to_va - va(frm_end))

# Cave: GetRazed  = test byte [eax+39h],1; setnz al; ret
cave_g = bytes.fromhex("F64039010F95C0C3")
data[CAVE_GETRAZED:CAVE_GETRAZED + len(cave_g)] = cave_g

# Cave: SetRazed
#   push ebx; mov ebx,eax; test dl,dl; jz clear
#   mov eax,ebx; call Deactivate; mov byte[ebx+30h],FF; or byte[ebx+39h],1; pop ebx; ret
#   clear: and byte[ebx+39h],FE; pop ebx; ret
cave_s = bytes.fromhex("538BD884D274118BC3E8") \
    + rel(CAVE_SETRAZED + 14, va_deactivate) \
    + bytes.fromhex("C64330FF804B39015BC3806339FE5BC3")
assert len(cave_s) == 30
data[CAVE_SETRAZED:CAVE_SETRAZED + len(cave_s)] = cave_s

# Cave: ReadWrite
#   push ebx; push esi; mov esi,edx; mov ebx,eax
#   call TPlayerStructure.ReadWrite            (eax=self, edx=stream intact)
#   lea edx,[ebx+39h]; mov ecx,70h; mov eax,esi; mov esi,[eax]; call [esi+30h]
#   pop esi; pop ebx; ret
cave_r = bytes.fromhex("53568BF28BD8E8") \
    + rel(CAVE_READWRITE + 11, va_tps_readwrite) \
    + bytes.fromhex("8D5339B9700000008BC68B30FF56305E5BC3")
assert len(cave_r) == 29
data[CAVE_READWRITE:CAVE_READWRITE + len(cave_r)] = cave_r

# Razeable flag
data[flag_off] = 0x01

# VMT slots
struct.pack_into("<I", data, vmt + 0x018, va(CAVE_READWRITE))
struct.pack_into("<I", data, vmt + 0x14C, va(CAVE_SETRAZED))
struct.pack_into("<I", data, vmt + 0x150, va(CAVE_GETRAZED))

open(DLL, "wb").write(data)
print("== Done ==")
print(f"  razeable flag @ file 0x{flag_off:X}: 00 -> 01")
print(f"  GetRazed  cave @ 0x{CAVE_GETRAZED:X} (VA 0x{va(CAVE_GETRAZED):08X})")
print(f"  SetRazed  cave @ 0x{CAVE_SETRAZED:X} (VA 0x{va(CAVE_SETRAZED):08X})")
print(f"  ReadWrite cave @ 0x{CAVE_READWRITE:X} (VA 0x{va(CAVE_READWRITE):08X})")
print(f"  VMT +0x18/+0x14C/+0x150 @ file 0x{vmt + 0x18:X}/0x{vmt + 0x14C:X}/0x{vmt + 0x150:X}")
