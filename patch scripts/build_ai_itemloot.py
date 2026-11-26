#!/usr/bin/env python3
r"""AoWx -- AI heroes loot ground items: pick up, UPGRADE-SWAP, stash
use-items; ground items are value-weighted AI targets.

v1 = straight port of BXL's build_ai_itempickup.py + build_ai_itemtarget.py
(fill empty equip slots only, priority from GetObtainValue). v2 (user spec
2026-08-31): every item in our mod has gold cost 10 (campaign-transfer
flattening) so GetObtainValue is useless as a weight. Instead:

  ITEM VALUE = 5*attack + 10*defense + 10*damage + 5*resistance
             + SUM over the item's granted abilities of ability.ExpandCost
             (per-stat costs user-specified 2026-08-31: att 5 / def 10 /
              dam 10 / res 5)
  * stat bytes live at [item+0x46 att][+0x47 def][+0x48 dam][+0x49 res]
    (proved by THeroItems.GetAttack/GetDefense/GetDamage/GetResistance
    @0x55786354/88/BC/F0 summing exactly those bytes over equipped items);
  * an item IS an ability container: child count [item vmt+0x54], children
    at [[item+8]+4][i]; each ability's cost = vcall [vmt+0xC8] ExpandCost
    (base impl `mov eax,[ability+0x14]`, 70+ class overrides) -- the same
    cost the hero level-up system charges, i.e. the user's "total
    stat/ability cost of what the item grants".

  PICKUP/SWAP (AI heroes, strategic map, own turn / on move -- v1 hooks):
    equip slots 0..5: slot type from the engine table (GetPositionItemType
    @0x55786734; slots 3 AND 5 share type 4). The best matching ground item
    STRICTLY exceeding the equipped item's value (empty slot = -1, so any
    matching item) replaces it: drop old via ExecutePlaceItem(hero, oldID,
    0xE = ground) then place new via ExecutePlaceItem(hero, newID, slot).
    Equal value -> no switch, item ignored (user rule). ExecutePlaceItem
    @0x5578907C revalidates through THero.CanPlaceItem and resolves by id
    from the global item registry [map+0xF4], so a stale id no-ops safely.
  USE ITEMS (type [item+0x34]==5, unequippable -- the type->slot table maps
    them to 0x0F): placed into a free inventory slot ([hero+0x74], finder
    @0x5578601C -> 0..7 or -1; inventory positions are 6..13 in
    ExecutePlaceItem's dispatch) -- pos = 6 + slot. Inventory full ->
    ignored (user rule). ONE use-item per hook firing (the ground list is
    freed when it empties -- never rescan a mutated list).
  TARGETING (v2.1, user re-tune 2026-08-31): TItemHS answers broadcast
    0x1200 GROUP-AWARE. An item on the hex counts ONLY if some hero/leader
    in the ASKING group ([msg+0x10] TAIGroupControl -> +0xC TAIGroup, a
    TUnitList; heroes filtered via IsClass THero) would actually take it:
    use items need a free inventory slot on some hero; equip items need a
    matching slot that is empty or holds a STRICTLY worse item (same rule
    as the pickup swap). priority = 10 + min(bestQualifyingValue/2, 65)
    -> 10..75: a good upgradeable item now outranks weak sites and rivals
    strong-site draws; a group whose heroes are already better-equipped is
    not attracted at all.

MP-safe exactly as v1: both pickup hooks run on every peer (NewTurn
broadcast / army-iterated MovedTo), ExecutePlaceItem is side-effect-clean
and deterministic, no RNG anywhere; a token mint here would double-place.

Caves: value/nt/moved/target in the 0x55814840..0x55814A40 zone (v1's,
re-laid), pickup @0x55814B40..0x55814D40 (0x55814A40..0x55814B40 =
build_ai_sitesearch.py cave_msgproc). Next free after this = 0x55814D40.

Usage: dry run default; --apply; --revert (surgical).
"""
import os
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.environ.get("AOW_GAME_DIR") or os.path.dirname(HERE)
DLL = os.path.join(GAME, "AoWEPACK.dll")
BAK = DLL + ".bak_aiitemloot"

D = 0x55700C00

GETPLAYERS = 0x557544D0
GETITEMS = 0x55788C7C
GETITEM = 0x55794A2C
EXECPLACE = 0x5578907C
ISCLASS = 0x557010C0
ABSNEWTURN = 0x55780D4C
INHERITED = 0x55701D4C
GETPOSITEM = 0x55786718        # THeroItems.GetPositionItem(eax=items, edx=pos)
GETUNIT = 0x5578309C           # TUnitList.GetUnit(eax=list, edx=idx)
GETPOSTYPE = 0x55786734        # (dl=pos) -> al slot type (table read)
INVFREESLOT = 0x5578601C       # (eax=inventory) -> 0..7 free slot or -1
                               # ⚠ UNUSED since v2.4: walks the inventory
                               # LIST and returns -1 when the list is EMPTY
                               # -- hero inventories start empty (the UI
                               # passes grid positions directly; placement
                               # grows the list), so this finder said "full"
                               # for every fresh hero and use items were
                               # never picked up (user-hit).
INVGETPOS = 0x55786284         # (eax=inventory, dl=pos 6..13) -> item or 0
                               # 0/out-of-range = free; the engine's own
                               # position semantics -- v2.4 probes 6..13
MAP_GLOBAL = 0x558FA040
HEROREF_CELL = 0x55711FAC
PH_MAP, PH_HERO = 0x11111111, 0x22222222

TABILITY_CELL = 0x5570F214     # vmtSelfPtr cell holding the TAbility classref
ENGINE_CELL = 0x558FA044       # AoWE engine global; [.]+0x80 = ability registry
GETABILITY = 0x557501C0        # (eax=registry, edx=id) -> TAbility or nil
PH_AB, PH_ENG = 0x33333333, 0x44444444

HOOK_NT = 0x55787FD7
HOOK_NT_ORIG = bytes.fromhex("e8708dffff")
HOOK_MV = 0x5578051B
HOOK_MV_ORIG = bytes.fromhex("5f5e5b595d")
VMT_SLOT = 0x55710244

CAVE_VALUE = 0x55814840
CAVE_NT = 0x55814900
CAVE_MOVED = 0x55814920
ZONE1_HI = 0x55814A40          # 0x55814960..0x55814A40 spare in zone 1
CAVE_PICKUP = 0x55814B40
ZONE2_HI = 0x55814D40
CAVE_TARGET = 0x55814D40       # v2.1 group-aware cave outgrew zone 1
ZONE3_HI = 0x55814F00

COST_ATT, COST_DEF, COST_DAM, COST_RES = 5, 10, 10, 5
MSG_ID = 0x1200
USE_TYPE = 5


def asm(src, addr):
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    src = "\n".join(ln.split(";")[0] for ln in src.splitlines())
    code, _ = Ks(KS_ARCH_X86, KS_MODE_32).asm(src, addr)
    return bytearray(code)


def patch_anchor(code, base, marker_after, pairs):
    i = next(k for k in range(len(code) - 5)
             if code[k] == 0xE8 and code[k + 1:k + 5] == b"\x00\x00\x00\x00"
             and code[k + 5] == marker_after)
    anchor = base + i + 5
    for ph, tgt in pairs:
        j = code.find(struct.pack("<I", ph))
        assert j != -1, hex(ph)
        code[j:j + 4] = struct.pack("<i", tgt - anchor)
        assert code.find(struct.pack("<I", ph)) == -1
    return code


def make_value():
    # eax = TItem* -> eax = value. Preserves ebx/esi/edi/ebp.
    # v2.3: CORRECT ability model. TItem is an ability-OWNER, not a child
    # list: [item+8] = ability BITSET pointer, [item+0xC] = word count
    # (the two prior AVs @0x5581487F/0x55814890 were this cave indexing the
    # bitset as if it were a TList). Value walk: for every SET bit (ability
    # id, bt handles >31 as a bit string), fetch the GLOBAL registry
    # instance (GetAbility asserts only on negative ids, returns nil for
    # unregistered) and add its ExpandCost -- nil/vmt/IsClass-guarded.
    src = f"""
        push ebx
        push esi
        push edi
        push ebp
        mov  ebx, eax
        call _a
    _a:
        pop  eax
        mov  ecx, [eax + 0x{PH_AB:X}]
        mov  eax, [eax + 0x{PH_ENG:X}]
        push ecx
        push eax
        movzx eax, byte ptr [ebx+0x46]
        imul eax, eax, {COST_ATT}
        movzx ecx, byte ptr [ebx+0x47]
        imul ecx, ecx, {COST_DEF}
        add  eax, ecx
        movzx ecx, byte ptr [ebx+0x48]
        imul ecx, ecx, {COST_DAM}
        add  eax, ecx
        movzx ecx, byte ptr [ebx+0x49]
        imul ecx, ecx, {COST_RES}
        add  eax, ecx
        mov  esi, eax
        cmp  dword ptr [ebx+8], 0
        jz   _e
        mov  ebp, [ebx+0xC]
        cmp  ebp, 192
        jle  _wok
        mov  ebp, 192
    _wok:
        test ebp, ebp
        jle  _e
        xor  edi, edi
    _l:
        cmp  edi, ebp
        jge  _e
        mov  eax, [ebx+8]
        bt   dword ptr [eax], edi
        jnc  _n
        mov  eax, [esp]
        test eax, eax
        jz   _e
        mov  eax, [eax+0x80]
        test eax, eax
        jz   _e
        mov  edx, edi
        call 0x{GETABILITY:X}
        test eax, eax
        jz   _n
        mov  edx, [eax]
        test edx, edx
        jz   _n
        push eax
        mov  edx, [esp+8]
        call 0x{ISCLASS:X}
        pop  ecx
        test al, al
        jz   _n
        mov  eax, ecx
        mov  edx, [eax]
        call dword ptr [edx+0xC8]
        add  esi, eax
    _n:
        inc  edi
        jmp  _l
    _e:
        pop  ecx
        pop  ecx
        mov  eax, esi
        pop  ebp
        pop  edi
        pop  esi
        pop  ebx
        ret
    """
    code = asm(src, CAVE_VALUE)
    return bytes(patch_anchor(code, CAVE_VALUE, 0x58,
                              [(PH_AB, TABILITY_CELL), (PH_ENG, ENGINE_CELL)]))


def make_pickup():
    # eax = THero*. frame: [esp]=slottype [esp+4]=curID [esp+8]=curval
    #                [esp+0xC]=bestID [esp+0x10]=bestval
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
        mov  eax, [edi + 0x{PH_MAP:X}]
        test eax, eax
        jz   _done
        cmp  dword ptr [eax+0x11C], 0
        jnz  _done
        mov  eax, [eax+0x140]
        movsx edx, byte ptr [ebp+0x24]
        call 0x{GETPLAYERS:X}
        test eax, eax
        jz   _done
        cmp  byte ptr [eax+0xA7], 0
        jz   _done
        cmp  dword ptr [ebp+4], 0
        jz   _done
        cmp  dword ptr [ebp+0x70], 0
        jz   _done
        ;
        ; ---- pass 1: ONE use-item into a free inventory slot ----
        cmp  dword ptr [ebp+0x74], 0
        jz   _equip
        mov  eax, ebp
        call 0x{GETITEMS:X}
        test eax, eax
        jz   _done
        mov  ebx, eax
        xor  esi, esi
    _uloop:
        mov  edx, esi
        mov  eax, ebx
        call 0x{GETITEM:X}
        test eax, eax
        jz   _equip
        cmp  byte ptr [eax+0x34], {USE_TYPE}
        jnz  _unext
        mov  ecx, 6
    _findu:
        cmp  ecx, 14
        jge  _unext
        push eax
        push ecx
        mov  edx, ecx
        mov  eax, [ebp+0x74]
        call 0x{INVGETPOS:X}
        test eax, eax
        pop  ecx
        pop  eax
        jz   _gotu
        inc  ecx
        jmp  _findu
    _gotu:
        mov  edx, [eax+0x14]
        mov  eax, ebp
        call 0x{EXECPLACE:X}
        jmp  _equip
    _unext:
        inc  esi
        jmp  _uloop
        ;
        ; ---- pass 2: equip slots 0..5, upgrade-swap by value ----
    _equip:
        xor  edi, edi
    _slot:
        mov  edx, edi
        xor  eax, eax
        call 0x{GETPOSTYPE:X}
        movzx eax, al
        mov  [esp], eax
        mov  edx, edi
        mov  eax, [ebp+0x70]
        call 0x{GETPOSITEM:X}
        test eax, eax
        jz   _cur0
        mov  ecx, [eax+0x14]
        mov  [esp+4], ecx
        call 0x{CAVE_VALUE:X}
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
        call 0x{GETITEMS:X}
        test eax, eax
        jz   _done
        mov  ebx, eax
        xor  esi, esi
    _iloop:
        mov  edx, esi
        mov  eax, ebx
        call 0x{GETITEM:X}
        test eax, eax
        jz   _endscan
        movzx ecx, byte ptr [eax+0x34]
        cmp  ecx, [esp]
        jnz  _inext
        push eax
        call 0x{CAVE_VALUE:X}
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
        call 0x{EXECPLACE:X}
    _placeonly:
        mov  edx, [esp+0xC]
        mov  ecx, edi
        mov  eax, ebp
        call 0x{EXECPLACE:X}
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
    code = asm(src, CAVE_PICKUP)
    return bytes(patch_anchor(code, CAVE_PICKUP, 0x5F, [(PH_MAP, MAP_GLOBAL)]))


def make_nt():
    src = f"""
        call 0x{ABSNEWTURN:X}
        cmp  bl, byte ptr [esi+0x24]
        jnz  _o
        pushad
        mov  eax, esi
        call 0x{CAVE_PICKUP:X}
        popad
    _o:
        ret
    """
    return bytes(asm(src, CAVE_NT))


def make_moved():
    src = f"""
        pushad
        push ebx
        mov  eax, ebx
        call _b
    _b:
        pop  edi
        mov  edx, [edi + 0x{PH_HERO:X}]
        call 0x{ISCLASS:X}
        pop  ecx
        test al, al
        jz   _o
        mov  eax, ecx
        call 0x{CAVE_PICKUP:X}
    _o:
        popad
        pop  edi
        pop  esi
        pop  ebx
        pop  ecx
        pop  ebp
        ret  4
    """
    code = asm(src, CAVE_MOVED)
    return bytes(patch_anchor(code, CAVE_MOVED, 0x5F, [(PH_HERO, HEROREF_CELL)]))


def make_target():
    # frame: [esp]=itemidx [esp+4]=best [esp+8]=group list [esp+0xC]=item
    #        [esp+0x10]=itemval [esp+0x14]=unitidx [esp+0x18]=itemtype
    #        [esp+0x1C]=THero classref
    src = f"""
        push ebx
        push esi
        push edi
        push ebp
        sub  esp, 0x20
        mov  esi, eax
        mov  edi, edx
        mov  eax, esi
        mov  edx, edi
        call 0x{INHERITED:X}
        cmp  dword ptr [edi], 0x{MSG_ID:X}
        jnz  _done
        cmp  dword ptr [edi+0x18], 0
        jnz  _done
        mov  eax, [edi+8]
        test eax, eax
        jz   _done
        cmp  byte ptr [eax+2], 0
        jnz  _done
        mov  ebx, [edi+0xC]
        test ebx, ebx
        jz   _done
        mov  ebp, [esi+0xC]
        test ebp, ebp
        jz   _done
        mov  eax, [edi+0x10]
        test eax, eax
        jz   _done
        mov  eax, [eax+0xC]
        test eax, eax
        jz   _done
        mov  [esp+8], eax
        call _a
    _a:
        pop  eax
        mov  eax, [eax + 0x{PH_HERO:X}]
        mov  [esp+0x1C], eax
        xor  eax, eax
        mov  [esp], eax
        mov  [esp+4], eax
    _iloop:
        mov  edx, [esp]
        mov  eax, ebp
        call 0x{GETITEM:X}
        test eax, eax
        jz   _have
        mov  [esp+0xC], eax
        call 0x{CAVE_VALUE:X}
        mov  [esp+0x10], eax
        cmp  eax, [esp+4]
        jle  _inext
        mov  eax, [esp+0xC]
        movzx eax, byte ptr [eax+0x34]
        mov  [esp+0x18], eax
        cmp  eax, {USE_TYPE}
        ja   _inext
        xor  eax, eax
        mov  [esp+0x14], eax
    _uloop:
        mov  eax, [esp+8]
        mov  edx, [eax]
        call dword ptr [edx+0x54]
        cmp  [esp+0x14], eax
        jge  _inext
        mov  eax, [esp+8]
        mov  edx, [esp+0x14]
        call 0x{GETUNIT:X}
        inc  dword ptr [esp+0x14]
        test eax, eax
        jz   _uloop
        mov  edi, eax
        mov  edx, [esp+0x1C]
        call 0x{ISCLASS:X}
        test al, al
        jz   _uloop
        cmp  dword ptr [esp+0x18], {USE_TYPE}
        jne  _equipck
        cmp  dword ptr [edi+0x74], 0
        jz   _uloop
        mov  ecx, 6
    _findt:
        cmp  ecx, 14
        jge  _uloop
        push ecx
        mov  edx, ecx
        mov  eax, [edi+0x74]
        call 0x{INVGETPOS:X}
        test eax, eax
        pop  ecx
        jz   _taker
        inc  ecx
        jmp  _findt
    _equipck:
        cmp  dword ptr [edi+0x70], 0
        jz   _uloop
        xor  esi, esi
    _sloop:
        cmp  esi, 6
        jge  _uloop
        mov  edx, esi
        xor  eax, eax
        call 0x{GETPOSTYPE:X}
        movzx eax, al
        cmp  eax, [esp+0x18]
        jnz  _snext
        mov  edx, esi
        mov  eax, [edi+0x70]
        call 0x{GETPOSITEM:X}
        test eax, eax
        jz   _taker
        call 0x{CAVE_VALUE:X}
        cmp  eax, [esp+0x10]
        jl   _taker
    _snext:
        inc  esi
        jmp  _sloop
    _taker:
        mov  eax, [esp+0x10]
        mov  [esp+4], eax
    _inext:
        inc  dword ptr [esp]
        jmp  _iloop
    _have:
        mov  eax, [esp+4]
        test eax, eax
        jz   _done
        shr  eax, 1
        cmp  eax, 65
        jle  _cl
        mov  eax, 65
    _cl:
        add  eax, 10
        cmp  dword ptr [ebx], eax
        jge  _done
        mov  dword ptr [ebx], eax
    _done:
        add  esp, 0x20
        pop  ebp
        pop  edi
        pop  esi
        pop  ebx
        ret
    """
    code = asm(src, CAVE_TARGET)
    return bytes(patch_anchor(code, CAVE_TARGET, 0x58, [(PH_HERO, HEROREF_CELL)]))


def main():
    apply = "--apply" in sys.argv
    revert = "--revert" in sys.argv
    d = bytearray(open(DLL, "rb").read())
    cv, cp, cn, cm, ct = (make_value(), make_pickup(), make_nt(),
                          make_moved(), make_target())
    assert CAVE_VALUE + len(cv) <= CAVE_NT, len(cv)
    assert CAVE_NT + len(cn) <= CAVE_MOVED, len(cn)
    assert CAVE_MOVED + len(cm) <= ZONE1_HI, len(cm)
    assert CAVE_PICKUP + len(cp) <= ZONE2_HI, len(cp)
    assert CAVE_TARGET + len(ct) <= ZONE3_HI, len(ct)

    def rel(src, dst):
        return struct.pack("<i", dst - (src + 5))
    hook_nt = b"\xE8" + rel(HOOK_NT, CAVE_NT)
    hook_mv = b"\xE9" + rel(HOOK_MV, CAVE_MOVED)

    edits = [
        (CAVE_VALUE, bytes(len(cv)), cv, "cave_value (item worth)"),
        (CAVE_NT, bytes(len(cn)), cn, "cave_nt (NewTurn wrapper)"),
        (CAVE_MOVED, bytes(len(cm)), cm, "cave_moved (MovedTo wrapper)"),
        (CAVE_TARGET, bytes(len(ct)), ct, "cave_target (TItemHS 0x1200)"),
        (CAVE_PICKUP, bytes(len(cp)), cp, "cave_pickup v2 (swap + use items)"),
        (HOOK_NT, HOOK_NT_ORIG, hook_nt, "THero.NewTurn call retarget"),
        (HOOK_MV, HOOK_MV_ORIG, hook_mv, "TAbstractUnit.MovedTo epilogue hook"),
        (VMT_SLOT, struct.pack("<I", INHERITED), struct.pack("<I", CAVE_TARGET),
         "TItemHS VMT+0xCC repoint"),
    ]
    states = []
    for va, ob, nb, nm in edits:
        c = bytes(d[va - D:va - D + len(nb)])
        st = "original" if c == ob else "applied" if c == nb else "FOREIGN"
        states.append(st)
        print("  %-36s @0x%08X  %s (%d B)" % (nm, va, st, len(nb)))
    if "FOREIGN" in states:
        print("FOREIGN - refusing")
        return 1
    if revert:
        for va, ob, nb, _ in edits:
            d[va - D:va - D + len(nb)] = ob
        open(DLL, "wb").write(bytes(d))
        print("reverted")
        return 0
    if not apply:
        print("dry run (--apply / --revert)")
        return 0
    if all(s == "applied" for s in states):
        print("already applied")
        return 0
    if not os.path.isfile(BAK):
        shutil.copy2(DLL, BAK)
        print("backed up")
    for va, ob, nb, _ in edits:
        d[va - D:va - D + len(nb)] = nb
    open(DLL, "wb").write(bytes(d))
    print("APPLIED v2 - test: AI hero on a hex with a BETTER item of an "
          "equipped type swaps (old item dropped on the ground); equal or "
          "worse items ignored; potions/scrolls (use items) get stashed "
          "while inventory has room, ignored when full; empty slots still "
          "filled; item attractiveness now tracks stat+ability worth")
    return 0


if __name__ == "__main__":
    sys.exit(main())
