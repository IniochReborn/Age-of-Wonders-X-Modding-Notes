#!/usr/bin/env python3
r"""AoWx -- AI heroes pick up USE items (potions, wands, flutes, talismans...) (2026-10-19).

User: "do AI not pick up 'use' slot items? an AI picked up every other item from an item bag" + an item-less AI
leader never walked to the loot left on a cleared monster lair.

ROOT CAUSE: build_ai_itemloot.py (v2.x) tests use items as item type [item+0x34] == 5.  Our ITEMS.PFS has NO type-5
items: the Use type is **6** (0 head 31 / 1 torso 27 / 2 weapon 45 / 3 shield 17 / 4 ring 23 / 6 use 33; the
engine's type->position table 0x558E8DB8 maps both 5 and 6 to 0x0F = not equippable).  So:
  * pickup pass 1 (stash a use item in a free backpack slot) never matched anything -> heroes left every use item on
    the ground while taking the equip items ("every other item");
  * the item-targeting answer to AI broadcast 0x1200 skipped type 6 (`cmp type,5 / ja skip`) -> a bag holding only
    use items was invisible to the AI, so no hero was ever drawn to it.

FIX (layer on top of build_ai_itemloot.py v2.5, which stays applied and untouched except below):
  P    0x55814B40  first 5 bytes of cave_pickup -> jmp NEWP (the old body is never entered again)
  NEWP 0x5581C220  cave_pickup v2.5 with use type 6 AND a LOOPED use pass: after stashing one use item it refetches
       the ground list (a place can free it) and stashes the next, until no use item / no free backpack slot / 8
       places (bound: a refused place cannot spin) - then the unchanged equip upgrade-swap pass.
  T1   cave_target+0xBF  `cmp eax,5` -> 6 (item types 0..6 considered)
  T2   cave_target+0x107 `cmp [esp+0x18],5` -> 6 (would-take treats type 6 as a use item: a free backpack slot on
       some hero of the asking group).
Inventory full -> use items ignored (user rule, unchanged).  MP: same hooks/peers as v2.5 (NewTurn broadcast,
MovedTo over army members), ExecutePlaceItem deterministic, no RNG.  Zone 0x5581C220.. (converge owns ..0x5581C212).

Order: apply AFTER build_ai_itemloot.py; revert this BEFORE re-running/reverting build_ai_itemloot.py (its dry run
shows cave_pickup/cave_target FOREIGN while this is on).  Backup .bak_aiitemuse.
Usage: py -3.10 patch_ai_itemloot_use_v1.py [--apply|--revert] [dll]   (dry run default)
"""
import os, shutil, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(1, r"C:\Users\<user>\Desktop\Age of Wonders X - Claude\patch scripts")
import build_ai_itemloot as L
try:
    from bakpath import bak_path
except Exception:
    def bak_path(p, s): return p + s

DLL = L.DLL
D = L.D
NEWP = 0x5581C220
ZONE_HI = 0x5581C800
P_SITE = L.CAVE_PICKUP
P_ORIG = bytes.fromhex("5356575583")
T1 = L.CAVE_TARGET + 0xBD + 2            # imm8 of 83 F8 05
T2 = L.CAVE_TARGET + 0x103 + 4           # imm8 of 83 7C 24 18 05
OLD_USE, NEW_USE = 5, 6
MAXUSE = 8


def make_newp():
    src = f"""
        push ebx
        push esi
        push edi
        push ebp
        sub  esp, 0x14
        mov  ebp, eax
        call _a
    _a:
        pop  edi
        mov  eax, [edi + 0x{L.PH_MAP:X}]
        test eax, eax
        jz   _done
        cmp  dword ptr [eax+0x11C], 0
        jnz  _done
        mov  eax, [eax+0x140]
        movsx edx, byte ptr [ebp+0x24]
        call 0x{L.GETPLAYERS:X}
        test eax, eax
        jz   _done
        cmp  byte ptr [eax+0xA7], 0
        jz   _done
        cmp  dword ptr [ebp+4], 0
        jz   _done
        cmp  dword ptr [ebp+0x70], 0
        jz   _done
        mov  dword ptr [esp+0x10], {MAXUSE}
    _urestart:
        cmp  dword ptr [ebp+0x74], 0
        jz   _equip
        mov  eax, ebp
        call 0x{L.GETITEMS:X}
        test eax, eax
        jz   _done
        mov  ebx, eax
        xor  esi, esi
    _uloop:
        mov  edx, esi
        mov  eax, ebx
        call 0x{L.GETITEM:X}
        test eax, eax
        jz   _equip
        cmp  byte ptr [eax+0x34], {NEW_USE}
        jnz  _unext
        mov  ecx, 6
    _findu:
        cmp  ecx, 14
        jge  _equip
        push eax
        push ecx
        mov  edx, ecx
        mov  eax, [ebp+0x74]
        call 0x{L.INVGETPOS:X}
        test eax, eax
        pop  ecx
        pop  eax
        jz   _gotu
        inc  ecx
        jmp  _findu
    _gotu:
        mov  edx, [eax+0x14]
        mov  eax, ebp
        call 0x{L.EXECPLACE:X}
        dec  dword ptr [esp+0x10]
        jnz  _urestart
        jmp  _equip
    _unext:
        inc  esi
        jmp  _uloop
    _equip:
        xor  edi, edi
    _slot:
        mov  edx, edi
        xor  eax, eax
        call 0x{L.GETPOSTYPE:X}
        movzx eax, al
        mov  [esp], eax
        mov  edx, edi
        mov  eax, [ebp+0x70]
        call 0x{L.GETPOSITEM:X}
        test eax, eax
        jz   _cur0
        mov  ecx, [eax+0x14]
        mov  [esp+4], ecx
        call 0x{L.CAVE_VALUE:X}
        mov  [esp+8], eax
        jmp  _scan
    _cur0:
        mov  dword ptr [esp+4], 0
        mov  dword ptr [esp+8], -1
    _scan:
        mov  dword ptr [esp+0xC], 0
        mov  eax, [esp+8]
        mov  [esp+0x10], eax
        mov  eax, ebp
        call 0x{L.GETITEMS:X}
        test eax, eax
        jz   _done
        mov  ebx, eax
        xor  esi, esi
    _iloop:
        mov  edx, esi
        mov  eax, ebx
        call 0x{L.GETITEM:X}
        test eax, eax
        jz   _endscan
        movzx ecx, byte ptr [eax+0x34]
        cmp  ecx, [esp]
        jnz  _inext
        push eax
        call 0x{L.CAVE_VALUE:X}
        pop  ecx
        cmp  eax, [esp+0x10]
        jle  _inext
        mov  [esp+0x10], eax
        mov  edx, [ecx+0x14]
        mov  [esp+0xC], edx
    _inext:
        inc  esi
        jmp  _iloop
    _endscan:
        mov  eax, [esp+0xC]
        test eax, eax
        jz   _nextslot
        mov  ecx, [esp+4]
        test ecx, ecx
        jz   _placeonly
        mov  edx, ecx
        mov  ecx, 0xE
        mov  eax, ebp
        call 0x{L.EXECPLACE:X}
    _placeonly:
        mov  edx, [esp+0xC]
        mov  ecx, edi
        mov  eax, ebp
        call 0x{L.EXECPLACE:X}
    _nextslot:
        inc  edi
        cmp  edi, 6
        jl   _slot
    _done:
        add  esp, 0x14
        pop  ebp
        pop  edi
        pop  esi
        pop  ebx
        ret
    """
    code = L.asm(src, NEWP)
    return bytes(L.patch_anchor(code, NEWP, 0x5F, [(L.PH_MAP, L.MAP_GLOBAL)]))


def edits():
    np_ = make_newp()
    assert NEWP + len(np_) <= ZONE_HI, len(np_)
    jmp = b"\xE9" + struct.pack("<i", NEWP - (P_SITE + 5))
    return [(NEWP, bytes(len(np_)), np_, "NEWP cave_pickup v3 (use type 6, looped)"),
            (P_SITE, P_ORIG, jmp, "cave_pickup head -> jmp NEWP"),
            (T1, bytes([OLD_USE]), bytes([NEW_USE]), "cave_target type bound 5 -> 6"),
            (T2, bytes([OLD_USE]), bytes([NEW_USE]), "cave_target use-item test 5 -> 6")]


def main(dll=None):
    dll = dll or DLL
    ap = "--apply" in sys.argv
    rv = "--revert" in sys.argv
    d = bytearray(open(dll, "rb").read())
    tc = bytes(d[L.CAVE_TARGET - D:L.CAVE_TARGET - D + 0x110])
    assert tc[0xBD:0xBF] == b"\x83\xF8" and tc[0x103:0x107] == b"\x83\x7C\x24\x18", \
        "cave_target layout not build_ai_itemloot v2.5 - refusing"
    E = edits()
    st = []
    for va, ob, nb, nm in E:
        c = bytes(d[va - D:va - D + len(nb)])
        s = "original" if c == ob else "applied" if c == nb else "FOREIGN"
        st.append(s)
        print("  %-44s @0x%08X  %s (%d B)" % (nm, va, s, len(nb)))
    if "FOREIGN" in st:
        print("FOREIGN - refusing")
        return 1
    if rv:
        if all(s == "original" for s in st):
            print("not applied")
            return 0
        for va, ob, nb, _ in E:
            d[va - D:va - D + len(nb)] = ob
        with open(dll, "r+b") as f:
            f.seek(0); f.write(bytes(d))
        print("reverted")
        return 0
    if not ap:
        print("dry run (--apply / --revert)")
        return 0
    if all(s == "applied" for s in st):
        print("already applied")
        return 0
    bk = bak_path(dll, ".bak_aiitemuse")
    if not os.path.isfile(bk):
        shutil.copy2(dll, bk)
        print("backup ->", bk)
    for va, ob, nb, _ in E:
        d[va - D:va - D + len(nb)] = nb
    with open(dll, "r+b") as f:
        f.seek(0); f.write(bytes(d))
    back = open(dll, "rb").read()
    for va, ob, nb, _ in E:
        assert back[va - D:va - D + len(nb)] == nb
    print("written and verified: AI heroes stash use items (type 6) and are drawn to bags holding them")
    return 0


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    sys.exit(main(a[0] if a else None))
