#!/usr/bin/env python3
"""
Items can grant HP and MV; "Use" items grant their bonuses from the backpack
(AoWEPACK.dll, 2026-09-12).  Ported from BXL's Ziggurat build_item_hpmv
(Sept 2026 dpl, he marked it untested) and extended per Inioch's spec:

  * TItem gains two signed-byte fields in its vanilla padding:
      +0x4A = HP bonus (stream tag 0x17), +0x4B = MV bonus (stream tag 0x18)
    Tags identical to BXL's, so item libraries are interchangeable.  Streamed
    by TItem.ReadWrite (0x557945C8) which also backs TEObject.Assign/Copy
    (EngineP: write-to-memory-stream + read-back), so UpdateFromLibrary, map
    items, saves and the item library (.PFS/.ail, TAoWDir tagged container)
    all carry the fields.  Absent tag = 0 (zero-initialised object).
  * THero.GetHits (VMT+0xD0 @0x5578859C) / GetMoves (VMT+0xD4 @0x557885C0)
    add  sum(item.hp / item.mv) over WORN items (THeroItems [hero+0x70]) and
    over BACKPACK items whose type byte [item+0x34] == 6 ("Use" items)
    (THeroInventory [hero+0x74]).  Applied before the vanilla clamp (1..50 in
    this build), like BXL.  TLeader inherits both.  Negative values work.
  * THeroItems.GetTotalAttack/Defense/Damage/Resistance (0x55786354/388/3BC/
    3F0, the worn-item stat sums used by THero.GetAttack/Defense/Damage/
    Resistance) now ALSO add the backpack Use items' +0x46..+0x49 bytes.
    Carrier resolved via the container back-reference [container+4] -> hero ->
    [hero+0x74].  Non-Use items in the backpack keep granting NOTHING.
  * THeroItems flag aggregators 0x55786424/470/4C0 (OR of per-item movement /
    terrain / immunity flags derived from item abilities; used by THero
    VMT+0xE8/+0xEC/+0xF0) likewise include backpack Use items - their
    abilities already reach the hero through the vanilla type-6 inventory
    legs, so the derived flags now agree.

Nothing here touches the editor: author HP/MV with `set_item_hpmv.py`
(same folder) on Release\\ITEMS.PFS / User\\*.ail.

Implementation: one generic PIC walker (cave_walk: container, callback,
type filter) + cave_total (worn + filtered backpack) + tiny callbacks; every
hooked function becomes a stub that computes the callback's runtime address
with the call/pop delta.  All rel32 / delta-based - rebase-safe.
Caves in verified-zero, reloc-free space 0x55813610.. (< 0x55813B80).
Dry-run default; --apply; --revert; --dll <path>.
Backup: AoWEPACK.dll.bak_item_hpmv
"""
import argparse, os, shutil, struct, sys
from bakpath import game_dir, game_file   # game folder = AOW_GAME_DIR or parent of patch scripts (2026-09-20)

DEFAULT_DLL = game_file(r"AoWEPACK.dll")
BAK_SUFFIX  = ".bak_item_hpmv"
from bakpath import bak_path   # backups live in <game>\backup\ (2026-09-17)
BASE        = 0x55700000
FILE_DELTA  = 0x55700C00

F_ATK, F_DEF, F_DAM, F_RES, F_HP, F_MV = 0x46, 0x47, 0x48, 0x49, 0x4A, 0x4B
TAG_HP, TAG_MV = 0x17, 0x18
USE_TYPE = 6                       # [item+0x34] value for "Use" items

# --- hook sites ---
RW_HOOK, RW_CONT = 0x55794712, 0x55794718           # TItem.ReadWrite tail
RW_ORIG = bytes.fromhex("8bc6 8b10 ff12")            # mov eax,esi ; mov edx,[eax] ; call [edx]
HITS_HOOK, HITS_CONT  = 0x5578859C, 0x557885A5      # THero.GetHits
HITS_ORIG  = bytes.fromhex("8b5040 8a5227")          # mov edx,[eax+0x40] ; mov dl,[edx+0x27]
MOVES_HOOK, MOVES_CONT = 0x557885C0, 0x557885C9     # THero.GetMoves
MOVES_ORIG = bytes.fromhex("8b5040 8a5228")
TOT_ORIG  = bytes.fromhex("535657 8bf0")             # push ebx/esi/edi ; mov esi,eax
TOT_SITES = {F_ATK: 0x55786354, F_DEF: 0x55786388, F_DAM: 0x557863BC, F_RES: 0x557863F0}
FLAG_ORIG = bytes.fromhex("53565755 51")             # push ebx/esi/edi/ebp ; push ecx
FLAG_SITES = [  # (site, per-item fn, result mask, initial-constant VA)
    (0x55786424, 0x5574F764, 0xFF,   0x5578646C),
    (0x55786470, 0x5574FADC, 0xFFFF, 0x557864BC),
    (0x557864C0, 0x5574F97C, 0xFFFF, 0x5578650C),
]
CAVE_LO, CAVE_HI = 0x55813610, 0x55813B80


class Asm:
    def __init__(self, base):
        self.base = base; self.buf = bytearray(); self.labels = {}; self.fix8 = []
    def here(self): return self.base + len(self.buf)
    def label(self, n): self.labels[n] = self.here()
    def db(self, *bs): self.buf += bytes(bs)
    def dd(self, v): self.buf += (v & 0xFFFFFFFF).to_bytes(4, 'little')
    def call(self, t): self.db(0xE8); self.buf += (t-(self.here()+4)).to_bytes(4, 'little', signed=True)
    def jmp32(self, t): self.db(0xE9); self.buf += (t-(self.here()+4)).to_bytes(4, 'little', signed=True)
    def j8(self, op, lab): self.db(op); self.fix8.append((len(self.buf), lab)); self.db(0)
    def runtime_addr(self, reg_pop, target):
        """call $+5 / pop reg / add reg, target-pop  -> reg = runtime address of link-time target."""
        self.call(self.here()+5); pop = self.here()
        self.db(0x58 + reg_pop)
        if reg_pop == 0: self.db(0x05)
        else:            self.db(0x81, 0xC0 + reg_pop)
        self.buf += (target - pop).to_bytes(4, 'little', signed=True)
    def done(self):
        for off, lab in self.fix8:
            rel = self.labels[lab]-(self.base+off+1); assert -128 <= rel <= 127, (lab, rel)
            self.buf[off] = rel & 0xFF
        return bytes(self.buf)

EAX, ECX, EDX, EBX, ESP, EBP, ESI, EDI = range(8)

_next = CAVE_LO
caves = []
def place(code_fn, size_hint, desc):
    global _next
    va = (_next + 15) & ~15
    code = code_fn(va)
    _next = va + len(code)
    assert _next <= CAVE_HI, f"cave overflow at {desc}"
    caves.append((va, code, desc)); return va

# --------------------------------------------------------------------------
# cave_walk(EAX=container|0, EDX=callback runtime addr, ECX=type filter|0):
#   for each non-nil item (filter: [item+0x34]==cl) -> call callback(EAX=item)
#   callback accumulates into EBX and preserves ESI/EDI/EBP.  Walk preserves EBX.
def walk(va):
    a = Asm(va)
    a.db(0x56); a.db(0x57); a.db(0x55)               # push esi/edi/ebp
    a.db(0x83, 0xEC, 0x08)                           # sub esp,8   [esp]=filter [esp+4]=count
    a.db(0x89, 0x0C, 0x24)                           # mov [esp], ecx
    a.db(0x8B, 0xE8); a.db(0x8B, 0xFA)               # ebp=container edi=callback
    a.db(0x85, 0xED); a.j8(0x74, 'done')             # nil container
    a.db(0x8B, 0xC5); a.db(0x8B, 0x10); a.db(0xFF, 0x52, 0x54)   # count = [vmt+0x54](container)
    a.db(0x89, 0x44, 0x24, 0x04)                     # mov [esp+4], eax
    a.db(0x33, 0xF6)                                 # esi = 0
    a.label('next')
    a.db(0x3B, 0x74, 0x24, 0x04); a.j8(0x7D, 'done') # cmp esi,[esp+4] ; jge done
    a.db(0x8B, 0x45, 0x08); a.db(0x85, 0xC0); a.j8(0x74, 'done')   # TList
    a.db(0x8B, 0x40, 0x04); a.db(0x85, 0xC0); a.j8(0x74, 'done')   # items array
    a.db(0x8B, 0x04, 0xB0); a.db(0x85, 0xC0); a.j8(0x74, 'skip')   # item = arr[esi]
    a.db(0x80, 0x3C, 0x24, 0x00); a.j8(0x74, 'call') # no filter
    a.db(0x8A, 0x0C, 0x24)                           # mov cl,[esp]
    a.db(0x38, 0x48, 0x34); a.j8(0x75, 'skip')       # cmp [eax+0x34], cl ; jne skip
    a.label('call'); a.db(0xFF, 0xD7)                # call edi
    a.label('skip'); a.db(0x46); a.j8(0xEB, 'next')  # inc esi ; jmp next
    a.label('done')
    a.db(0x83, 0xC4, 0x08); a.db(0x5D); a.db(0x5F); a.db(0x5E); a.db(0xC3)
    return a.done()
CAVE_WALK = place(walk, 0x50, "cave_walk (container iterator w/ type filter)")

# cave_total(EAX=worn container|0, EDX=backpack container|0, ECX=callback) -> EAX = EBX acc
def total(va):
    a = Asm(va)
    a.db(0x53); a.db(0x56); a.db(0x57)               # push ebx/esi/edi
    a.db(0x33, 0xDB)                                 # ebx = 0
    a.db(0x8B, 0xF2); a.db(0x8B, 0xF9)               # esi=backpack edi=callback
    a.db(0x8B, 0xD7); a.db(0x33, 0xC9); a.call(CAVE_WALK)             # walk(worn, cb, 0)
    a.db(0x8B, 0xC6); a.db(0x8B, 0xD7); a.db(0xB9); a.dd(USE_TYPE); a.call(CAVE_WALK)  # walk(backpack, cb, 6)
    a.db(0x8B, 0xC3); a.db(0x5F); a.db(0x5E); a.db(0x5B); a.db(0xC3)
    return a.done()
CAVE_TOTAL = place(total, 0x30, "cave_total (worn + Use-backpack)")

# callbacks: sum signed byte field into EBX
CB = {}
def cb_sum(field):
    def f(va):
        a = Asm(va)
        a.db(0x0F, 0xBE, 0x40, field)                # movsx eax, byte [eax+field]
        a.db(0x03, 0xD8); a.db(0xC3)                 # add ebx, eax ; ret
        return a.done()
    return f
for fld, nm in ((F_ATK,"atk"),(F_DEF,"def"),(F_DAM,"dam"),(F_RES,"res"),(F_HP,"hp"),(F_MV,"mv")):
    CB[fld] = place(cb_sum(fld), 0x10, f"cb_sum_{nm} (+0x{fld:X})")
# callbacks: OR per-item flag fn result into EBX
CBF = {}
for site, fn, mask, cva in FLAG_SITES:
    def f(va, fn=fn, mask=mask):
        a = Asm(va)
        a.call(fn)                                   # eax = flags(item)
        a.db(0x25); a.dd(mask)                       # and eax, mask
        a.db(0x0B, 0xD8); a.db(0xC3)                 # or ebx, eax ; ret
        return a.done()
    CBF[site] = place(f, 0x10, f"cb_or_{fn:X}")

# stubs replacing THeroItems.GetTotalX / flag aggregators: EAX = THeroItems container
def tot_stub(cb):
    def f(va):
        a = Asm(va)
        a.db(0x56); a.db(0x8B, 0xF0)                 # push esi ; esi = container
        a.runtime_addr(ECX, cb)                      # ecx = runtime callback
        a.db(0x33, 0xD2)                             # edx = 0
        a.db(0x8B, 0x46, 0x04); a.db(0x85, 0xC0); a.j8(0x74, 'nohero')   # hero = [container+4]
        a.db(0x8B, 0x50, 0x74)                       # edx = [hero+0x74] backpack
        a.label('nohero')
        a.db(0x8B, 0xC6); a.call(CAVE_TOTAL)         # eax = total(worn=esi, backpack, cb)
        a.db(0x5E); a.db(0xC3)
        return a.done()
    return f
STUB_TOT = {fld: place(tot_stub(CB[fld]), 0x30, f"stub GetTotal +0x{fld:X}") for fld in (F_ATK, F_DEF, F_DAM, F_RES)}
STUB_FLAG = {site: place(tot_stub(CBF[site]), 0x30, f"stub flags 0x{site:X}") for site, *_ in FLAG_SITES}

# THero.GetHits / GetMoves: EAX = hero.  dl = template byte + hero bonus + items ; jmp clamp tail
def hero_stub(tmpl_off, hero_off, cb, cont):
    def f(va):
        a = Asm(va)
        a.db(0x53); a.db(0x8B, 0xD8)                 # push ebx ; ebx = hero
        a.db(0x8B, 0x53, 0x40); a.db(0x8A, 0x52, tmpl_off); a.db(0x02, 0x53, hero_off)  # dl = base
        a.db(0x52)                                   # push edx
        a.runtime_addr(ECX, cb)
        a.db(0x8B, 0x43, 0x70); a.db(0x8B, 0x53, 0x74)   # worn, backpack
        a.call(CAVE_TOTAL)
        a.db(0x5A); a.db(0x02, 0xD0)                 # pop edx ; add dl, al
        a.db(0x5B); a.jmp32(cont)                    # pop ebx ; -> mov eax,edx ; clamp ; ret
        return a.done()
    return f
STUB_HITS  = place(hero_stub(0x27, 0x6D, CB[F_HP], HITS_CONT),  0x30, "stub THero.GetHits (+items)")
STUB_MOVES = place(hero_stub(0x28, 0x6E, CB[F_MV], MOVES_CONT), 0x30, "stub THero.GetMoves (+items)")

# TItem.ReadWrite tail: stream tags 0x17/0x18 for +0x4A/+0x4B then replay
def rw(va):
    a = Asm(va)
    for fld, tag in ((F_HP, TAG_HP), (F_MV, TAG_MV)):
        a.db(0x8D, 0x53, fld); a.db(0xB9); a.dd(tag)         # lea edx,[ebx+fld] ; mov ecx,tag
        a.db(0x8B, 0xC6); a.db(0x8B, 0x38); a.db(0xFF, 0x57, 0x30)   # mov eax,esi ; mov edi,[eax] ; call [edi+0x30]
    a.db(0x8B, 0xC6); a.db(0x8B, 0x10); a.db(0xFF, 0x12)     # replay
    a.jmp32(RW_CONT)
    return a.done()
CAVE_RW = place(rw, 0x30, "cave_itemrw (tags 0x17 HP / 0x18 MV)")
CAVE_END = _next

def rel32(src, dst): return struct.pack("<i", dst-(src+5))
def jmpop(src, dst, pad): return b"\xE9" + rel32(src, dst) + b"\x90"*pad

patches = [(va, bytes(len(code)), code, desc) for va, code, desc in caves]
patches += [
    (RW_HOOK, RW_ORIG, jmpop(RW_HOOK, CAVE_RW, 1), "TItem.ReadWrite tail -> cave_itemrw"),
    (HITS_HOOK, HITS_ORIG, jmpop(HITS_HOOK, STUB_HITS, 1), "THero.GetHits -> stub (+item HP)"),
    (MOVES_HOOK, MOVES_ORIG, jmpop(MOVES_HOOK, STUB_MOVES, 1), "THero.GetMoves -> stub (+item MV)"),
]
for fld, site in TOT_SITES.items():
    patches.append((site, TOT_ORIG, jmpop(site, STUB_TOT[fld], 0), f"THeroItems.GetTotal(+0x{fld:X}) -> stub (worn + Use backpack)"))
for site, fn, mask, cva in FLAG_SITES:
    patches.append((site, FLAG_ORIG, jmpop(site, STUB_FLAG[site], 0), f"THeroItems flags 0x{site:X} -> stub (worn + Use backpack)"))

def write_inplace(path, data):
    assert len(data) == os.path.getsize(path), "size changed - refusing in-place write"
    with open(path, "r+b") as f:
        f.seek(0); f.write(data); f.flush(); os.fsync(f.fileno())

def reloc_check(dll_path):
    try:
        import pefile
    except ImportError:
        print("  (pefile not available - reloc check skipped)"); return True
    pe = pefile.PE(dll_path); ok = True
    relocs = [e.rva + BASE for blk in pe.DIRECTORY_ENTRY_BASERELOC for e in blk.entries if e.type]
    for va, old, new, desc in patches:
        hits = [r for r in relocs if va - 3 <= r < va + len(new)]
        if hits: print(f"  RELOC INTERSECT @0x{va:X} ({desc}): {[hex(h) for h in hits]}"); ok = False
    return ok

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dll", default=DEFAULT_DLL)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    args = ap.parse_args()
    dll, bak = args.dll, bak_path(args.dll, BAK_SUFFIX)
    data = bytearray(open(dll, "rb").read())
    print(f"target: {dll}\ncaves 0x{CAVE_LO:X}..0x{CAVE_END:X} ({CAVE_END-CAVE_LO} B used of {CAVE_HI-CAVE_LO})")
    for va, code, desc in caves: print(f"  0x{va:X} {len(code):3d}B  {desc}")
    # the flag aggregators start from embedded constants; we assume 0 (asserted here)
    for site, fn, mask, cva in FLAG_SITES:
        v = struct.unpack_from("<H", data, cva - FILE_DELTA)[0] & mask
        assert v == 0, f"flag initial constant @0x{cva:X} is 0x{v:X}, not 0 - stub must OR it in"

    if args.revert:
        if not all(bytes(data[va-FILE_DELTA:va-FILE_DELTA+len(new)]) == new for va, old, new, d in patches):
            print("Not (fully) applied - nothing to revert."); return 1
        for va, old, new, desc in patches: data[va-FILE_DELTA:va-FILE_DELTA+len(old)] = old
        write_inplace(dll, data); print("Reverted all patches (caves zeroed, hooks restored)."); return 0

    ok = True; applied = 0
    for va, old, new, desc in patches:
        cur = bytes(data[va-FILE_DELTA:va-FILE_DELTA+len(old)])
        if cur == new: applied += 1
        elif cur != old:
            print(f"MISMATCH @0x{va:X} ({desc}):\n  exp {old.hex(' ')[:80]}\n  got {cur.hex(' ')[:80]}"); ok = False
    if applied == len(patches): print("ALL ALREADY PATCHED"); return 0
    if applied: print(f"partial: {applied}/{len(patches)} already applied"); ok = False
    if not ok: print("Aborting."); return 1
    if not reloc_check(dll): print("Aborting (reloc)."); return 1
    print("\nItems: HP (+0x4A, tag 0x17) and MV (+0x4B, tag 0x18); Use items (type 6) grant all six "
          "stats + ability flags from the backpack; other backpack items grant nothing.")
    if not args.apply: print("\nDry run OK. Re-run with --apply to write."); return 0
    if not os.path.exists(bak): shutil.copyfile(dll, bak); print(f"Backup: {bak}")
    for va, old, new, desc in patches:
        data[va-FILE_DELTA:va-FILE_DELTA+len(new)] = new; print(f"Patched: {desc}")
    write_inplace(dll, data); print("AoWEPACK.dll patched successfully."); return 0

if __name__ == "__main__":
    sys.exit(main())
