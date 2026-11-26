#!/usr/bin/env python3
r"""
GRAVITY WELL (spell 366) - the persistent GRAVITY FIELD on the combat map + the Grounded visuals.  AoWTCPCK.dll.
2026-10-15 (user round 1).  Needs patch_gravitywell_v1.py v2 applied first (AoWEPACK exports gw_sync @0x5585A000).

Behaviour:
  * Every landed Gravity Well strike (7: the target hex + its ring, patch_rotaway_v1.py STRIKES[366]) leaves a GRAVITY
    HS on its hex (one per hex; a second cast on the same hex refreshes it).  The field lives until the CASTER's next
    turn begins: exactly TCombatFire's lifetime rule (TCombatFire.Activate 0x407054 stores the turn player
    [map+0xED] in +0x14 and a 'skip once' flag +0x18; NewTurn 0x4070CC, reached from MsgProc 0x4071B4 on the turn
    broadcast 0x20021001 (not while [map+0x3C] & 2), clears the flag on the first turn change and frees the HS on the
    owner's next turn).  Ours does the same WITHOUT the fire's damage / spreading.
  * While a field stands, any Flying / Floating / Wind Walking unit on one of its hexes holds GROUNDED 0xB8 (combat
    only): granted when the field lands on it (field PlaceOnMap) or when the unit ends a move on a field hex
    (AoWEPACK pom hook), removed when it moves off (pom) or the field expires (MsgProc).  The movement-type strip in
    patch_gravitywell_v1.py turns it into a walker -> ground pathing, and Tremors (msg 0x31004 handler, `test al,2`
    @0x42168C) no longer skips it.  Everything runs inside TE execution / the turn broadcast -> same on every peer.
  * Grounded visuals: the Flying hover offset (-8 px, TTacticalCombatUnitHS.Show @0x422003) becomes GROUND_DY for a
    unit holding 0xB8, and its shadow (TTacticalCombatUnitHS.ShowShadow 0x422D68) is not drawn.

Gravity HS = a runtime CLONE of the TCombatFire VMT (copied once, VMT-0x40..+0x110 = all 68 slots, into AoWEPACK's
BSS page slack at CLONE_EP (TCPCK has no free writable room for 0x150 bytes) - reached through the TCombatUnit.SetUnit
import-slot delta, as are the AoWEPACK exports), instance size 0x1C (TCombatFire's +0x14 owner / +0x18 skip flag),
slots replaced:
   +0x24 ClassID      -> 0x22010C (unused anywhere)
   +0x44 MsgProc      -> inherited TEObject.MsgProc; on 0x20021001 the fire's rule; on expiry gw_sync(unit on the
                         hex, 0), then TObject.Free (TCombatFire.NewTurn frees itself the same way)
   +0x64 GetLevel / +0x8C GetShowPriority / +0xD0 CanMoveOn -> TCOozeHS's (a ground decal, no movement effect)
   +0xA8 Show         -> spell 366's own image list [spell+0x2C] slot FIELD_SLOT, frame by time like TCombatFire.Show
                         (TImageSequence.GetFrameIndex(tick [[0x46E8D4]+0x40], phase = self>>2)), drawn at
                         HXtoHP(hex) - view + the sequence's own offsets (+0x24/+0x28 = the pipeline seq_entry dx/dy)
   +0xAC PlaceOnMap   -> THexagonSprite.PlaceOnMap, then gw_sync(the unit already on the hex, 1)
   +0x58 GetOverlay stays THexagonSprite's default (0xFE = none: the field's terrain/passability are untouched).
Sites (all vanilla, reloc-free, referenced by no other script):
   land  0x40C609 (7 B `mov eax,[ebp-0x20] / cmp dword [eax+0x30],0`, right after every landed strike's hex
         [ebp-0x28]/[ebp-0x2C] is computed, BEFORE the strike's CA executes): call -> for te id [te+0x18] == 366 and
         fx kind [fx+0x14] == 0x34 place / refresh the gravity HS (TCombatFire.Create 0x406F68 with the clone class,
         THSMap.PlaceHX(map, hs, x, y, 0); Free on failure; owner +0x14 := [map+0xED] / skip flag +0x18 := 1 set
         explicitly after placing, as TCombatFire.Activate does), then replay the two instructions (flags for the jz).
   hov   0x422003 (9 B `je +9 / mov [ebp-0x38],-8`): jmp -> flyers holding 0xB8 get GROUND_DY.
   shd   0x422D68 (6 B ShowShadow prologue): jmp -> holding 0xB8 -> `ret 4` (no shadow).
Zone 0x43EC40..0x43F000 (zero, reloc-free; 0x43EC00..0x43EC40 = the rot-overlay id table).  PIC call/pop delta for
every in-image absolute (TCPCK rebases).  Thunks import-table checked.  Dry-run default; --apply / --revert / --dis.
Backup <game>\backup\AoWTCPCK.dll.bak_gravityfield.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DLL = game_file("AoWTCPCK.dll"); EP_DLL = game_file("AoWEPACK.dll")
BASE, V2F = 0x400000, 0x400C00
ZONE, ZONE_END = 0x43EC40, 0x43F000
SPELL_ID, GROUNDED, FIELD_CLASSID, UNITHS_CLASSID, FX_STRIKE = 366, 0xB8, 0x22010C, 0x220104, 0x34
FIELD_SLOT = 3                    # spell 366 image-list slot drawn as the field (pipeline gfx slot 3)
GROUND_DY = 6                     # y offset of a grounded FLYING unit (vanilla flyers -8 = hover, walkers 0)
TURN_MSG = 0x20021001
# AoWEPACK side (reached through the TCombatUnit.SetUnit import slot: runtime VA = [slot] - SETUNIT_VA + target)
SETUNIT_SLOT, SETUNIT_VA = 0x46E858, 0x55725194
EP_SYNC = 0x5585A000              # patch_gravitywell_v1.py v2 export: jmp gw_sync (eax = TUnit, dl = on field)
CLONE_EP, VMT_LO, VMT_HI = 0x558FA440, 0x40, 0x110   # AoWEPACK BSS slack 0x558FA400..0x558FA550 (VMT ptr = +0x40)
# AoWTCPCK
MAPLIST, AOWHSSET, TICKOBJ = 0x469420, 0x46E8D0, 0x46E8D4
FIRE_CELL, OOZE_CELL, FIRE_CREATE = 0x406AE4, 0x41275C, 0x406F68
T_MSGPROC, T_FREE, T_PLACEON, T_GETSPELL, T_GETSEQ, T_FRAMEIDX, T_LIBGET, T_HXTOHP, T_PLACEHX, T_GETLEVEL, T_GETFIELD = (
    0x401404, 0x401050, 0x401C5C, 0x4029B4, 0x4016E4, 0x4016D4, 0x4016F4, 0x4022BC, 0x402264, 0x401E64, 0x401E54)
THUNKS = {T_MSGPROC: "TEObject.MsgProc", T_FREE: "TObject.Free", T_PLACEON: "THexagonSprite.PlaceOnMap",
          T_GETSPELL: "TSpellControl.GetSpell", T_GETSEQ: "GetImageSequence", T_FRAMEIDX: "TImageSequence.GetFrameIndex",
          T_LIBGET: "TCustomImageLibrary.Get", T_HXTOHP: "HSEngine.HXtoHP", T_PLACEHX: "THSMap.PlaceHX",
          T_GETLEVEL: "TMapContainer.GetMapLevel", T_GETFIELD: "TMapLevel.GetField"}
SITES = [   # (name, va, vanilla bytes, kind, resume)
    ("land", 0x40C609, bytes.fromhex("8b45e083783000"), "call", None),
    ("hov",  0x422003, bytes.fromhex("7409c745c8f8ffffff"), "jmp", None),
    ("shd",  0x422D68, bytes.fromhex("558bec83c4d0"), "jmp", None),
]
HOV_ZERO, HOV_DONE, SHD_RESUME = 0x42200E, 0x422013, 0x422D6E

ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm_delta(src, va):
    """PIC delta idiom `call $D / pop R / sub R, $D` (R = ebx, esi, edi): every anchor patched with its own VA."""
    s1 = src.replace("call $D", ".byte 0xe8, 0, 0, 0, 0")
    for r in ("ebx", "esi", "edi"): s1 = s1.replace("sub %s, $D" % r, "sub %s, 0x7fffffff" % r)
    b = bytearray(ks.asm(s1, va)[0]); n = 0
    for pop, sub in ((0x5B, 0xEB), (0x5E, 0xEE), (0x5F, 0xEF)):
        anchor = bytes([0xE8, 0, 0, 0, 0, pop, 0x81, sub]) + b"\xff\xff\xff\x7f"
        k = b.find(anchor)
        while k >= 0:
            struct.pack_into("<I", b, k + len(anchor) - 4, va + k + 5); n += 1; k = b.find(anchor, k + len(anchor))
    assert n == src.count("call $D"), "delta anchors: %d of %d" % (n, src.count("call $D"))
    return bytes(b)


def build():
    out = bytearray(); where = {}
    def place(name, src):
        while len(out) % 16: out.append(0)
        va = ZONE + len(out); where[name] = va; out.extend(asm_delta(src, va))
    P = {"slot": SETUNIT_SLOT, "suva": SETUNIT_VA, "sync": EP_SYNC, "clone": CLONE_EP, "maplist": MAPLIST, "hsset": AOWHSSET,
         "tick": TICKOBJ, "fire": FIRE_CELL, "ooze": OOZE_CELL, "create": FIRE_CREATE, "msgproc": T_MSGPROC, "free": T_FREE,
         "placeon": T_PLACEON, "getspell": T_GETSPELL, "getseq": T_GETSEQ, "frameidx": T_FRAMEIDX, "libget": T_LIBGET,
         "hxtohp": T_HXTOHP, "placehx": T_PLACEHX, "getlevel": T_GETLEVEL, "getfield": T_GETFIELD, "id": SPELL_ID,
         "gr": GROUNDED, "fcls": FIELD_CLASSID, "ucls": UNITHS_CLASSID, "kind": FX_STRIKE, "fslot": FIELD_SLOT,
         "gdy": GROUND_DY, "turn": TURN_MSG, "lo": VMT_LO, "ndw": (VMT_LO + VMT_HI) // 4,
         "hz": HOV_ZERO, "hd": HOV_DONE, "shr": SHD_RESUME}
    place("classid", "mov eax, %(fcls)#x\n ret" % P)
    # unit_sync(eax = field, dl = on): the unit standing on the field (if any) -> AoWEPACK gw_sync; preserves all but eax
    place("usync", """
        pushal
        mov bl, dl
        test eax, eax
        jz u_out
        mov edx, %(ucls)#x
        mov ecx, [eax]
        call dword ptr [ecx + 0x80]
        test eax, eax
        jz u_out
        mov eax, [eax + 0x1c]
        test eax, eax
        jz u_out
        mov eax, [eax + 0x4c]
        test eax, eax
        jz u_out
        push eax
        call $D
        pop esi
        sub esi, $D
        mov ecx, [esi + %(slot)#x]
        sub ecx, %(suva)#x
        add ecx, %(sync)#x
        pop eax
        mov dl, bl
        call ecx
    u_out:
        popal
        ret
    """ % P)
    # PlaceOnMap(eax = self) -> al: inherited, then ground the airborne unit already on the hex
    place("placeon", """
        push esi
        mov esi, eax
        call %(placeon)#x
        push eax
        mov eax, [esi + 4]
        mov dl, 1
        call %(usync)#x
        pop eax
        pop esi
        ret
    """ % dict(P, usync=where["usync"]))
    # MsgProc(eax = self, edx = msg, ecx): inherited; on the turn broadcast the fire's lifetime rule without the fire
    place("msg", """
        push ebx
        push esi
        push edi
        mov esi, eax
        mov edi, edx
        call %(msgproc)#x
        cmp dword ptr [edi], %(turn)#x
        jne m_out
        call $D
        pop ebx
        sub ebx, $D
        mov eax, [ebx + %(maplist)#x]
        mov eax, [eax]
        test byte ptr [eax + 0x3c], 2
        jnz m_out
        cmp byte ptr [esi + 0x18], 0
        je m_owner
        mov byte ptr [esi + 0x18], 0
        jmp m_out
    m_owner:
        movsx eax, byte ptr [eax + 0xed]
        cmp eax, [esi + 0x14]
        jne m_out
        mov eax, [esi + 4]
        xor edx, edx
        call %(usync)#x
        mov eax, esi
        call %(free)#x
    m_out:
        pop edi
        pop esi
        pop ebx
        ret
    """ % dict(P, usync=where["usync"]))
    # Show(eax = self, edx = dx, ecx = dy, [ebp+8] = surface; ret 4) - TCombatFire.Show with spell 366's own sequence
    place("show", """
        push ebp
        mov ebp, esp
        add esp, -0x1c
        push ebx
        push esi
        mov [ebp - 0xc], ecx
        mov [ebp - 8], edx
        mov [ebp - 4], eax
        call $D
        pop esi
        sub esi, $D
        lea eax, [ebp - 0x1c]
        push eax
        lea ecx, [ebp - 0x18]
        mov eax, [ebp - 4]
        mov eax, [eax + 4]
        movsx edx, byte ptr [eax + 0x11]
        movsx eax, byte ptr [eax + 0x10]
        call %(hxtohp)#x
        mov eax, [ebp - 0x18]
        sub eax, [ebp - 8]
        mov [ebp - 8], eax
        mov eax, [ebp - 0x1c]
        sub eax, [ebp - 0xc]
        mov [ebp - 0xc], eax
        mov eax, [esi + %(hsset)#x]
        mov eax, [eax]
        mov eax, [eax + 0x84]
        mov edx, %(id)d
        call %(getspell)#x
        test eax, eax
        jz s_fin
        mov eax, [eax + 0x2c]
        test eax, eax
        jz s_fin
        mov edx, %(fslot)d
        call %(getseq)#x
        mov [ebp - 0x10], eax
    s_again:
        cmp dword ptr [ebp - 0x10], 0
        je s_fin
        mov ecx, [ebp - 4]
        shr ecx, 2
        and ecx, 0xffff
        mov eax, [esi + %(tick)#x]
        mov eax, [eax]
        mov edx, [eax + 0x40]
        mov eax, [ebp - 0x10]
        call %(frameidx)#x
        mov [ebp - 0x14], eax
        cmp eax, -1
        je s_next
        mov eax, [ebp + 8]
        push eax
        mov edx, [ebp - 0x14]
        mov eax, [ebp - 0x10]
        mov eax, [eax + 0x10]
        call %(libget)#x
        mov ecx, [ebp - 0xc]
        mov edx, [ebp - 0x10]
        add ecx, [edx + 0x28]
        mov edx, [ebp - 8]
        mov ebx, [ebp - 0x10]
        add edx, [ebx + 0x24]
        mov ebx, [eax]
        call dword ptr [ebx + 0x84]
    s_next:
        mov eax, [ebp - 0x10]
        mov eax, [eax + 0xc]
        mov [ebp - 0x10], eax
        jmp s_again
    s_fin:
        pop esi
        pop ebx
        mov esp, ebp
        pop ebp
        ret 4
    """ % P)
    # getcls -> eax = the clone VMT (built on first use from TCombatFire's VMT + TCOozeHS's decal slots); keeps regs
    place("getcls", """
        push ebx
        push ecx
        push edx
        push esi
        push edi
        call $D
        pop ebx
        sub ebx, $D
        mov edx, [ebx + %(slot)#x]
        sub edx, %(suva)#x
        add edx, %(clone)#x
        cmp dword ptr [edx - 0x40], 0
        jne g_done
        mov esi, [ebx + %(fire)#x]
        sub esi, %(lo)d
        lea edi, [edx - %(lo)d]
        mov ecx, %(ndw)d
        .byte 0xf3, 0xa5
        mov [edx - 0x40], edx
        lea ecx, [ebx + %(classid)#x]
        mov [edx + 0x24], ecx
        lea ecx, [ebx + %(msg)#x]
        mov [edx + 0x44], ecx
        lea ecx, [ebx + %(show)#x]
        mov [edx + 0xa8], ecx
        lea ecx, [ebx + %(placeon)#x]
        mov [edx + 0xac], ecx
        mov esi, [ebx + %(ooze)#x]
        mov ecx, [esi + 0x64]
        mov [edx + 0x64], ecx
        mov ecx, [esi + 0x8c]
        mov [edx + 0x8c], ecx
        mov ecx, [esi + 0xd0]
        mov [edx + 0xd0], ecx
    g_done:
        mov eax, edx
        pop edi
        pop esi
        pop edx
        pop ecx
        pop ebx
        ret
    """ % dict(P, classid=where["classid"], msg=where["msg"], show=where["show"], placeon=where["placeon"]))
    # land: every landed fx, hex = [ebp-0x28]/[ebp-0x2C], fx = [ebp-0x20], te = [ebp-4]
    place("land", """
        pushal
        mov eax, [ebp - 4]
        cmp dword ptr [eax + 0x18], %(id)d
        jne l_out
        mov eax, [ebp - 0x20]
        cmp dword ptr [eax + 0x14], %(kind)d
        jne l_out
        cmp dword ptr [ebp - 0x28], -1
        jle l_out
        call $D
        pop ebx
        sub ebx, $D
        mov eax, [ebx + %(maplist)#x]
        mov eax, [eax]
        mov eax, [eax + 0x10]
        xor edx, edx
        call %(getlevel)#x
        test eax, eax
        jz l_out
        mov edx, [ebp - 0x28]
        mov ecx, [ebp - 0x2c]
        call %(getfield)#x
        test eax, eax
        jz l_out
        mov edx, %(fcls)#x
        mov ecx, [eax]
        call dword ptr [ecx + 0x80]
        test eax, eax
        jz l_new
        mov edx, [ebx + %(maplist)#x]
        mov edx, [edx]
        movsx edx, byte ptr [edx + 0xed]
        mov [eax + 0x14], edx
        mov byte ptr [eax + 0x18], 1
        jmp l_out
    l_new:
        call %(getcls)#x
        xor ecx, ecx
        mov dl, 1
        call %(create)#x
        mov edi, eax
        push dword ptr [ebp - 0x2c]
        push 0
        mov eax, [ebx + %(maplist)#x]
        mov eax, [eax]
        mov edx, edi
        mov ecx, [ebp - 0x28]
        call %(placehx)#x
        test al, al
        jz l_fail
        mov edx, [ebx + %(maplist)#x]
        mov edx, [edx]
        movsx edx, byte ptr [edx + 0xed]
        mov [edi + 0x14], edx
        mov byte ptr [edi + 0x18], 1
        jmp l_out
    l_fail:
        mov eax, edi
        call %(free)#x
    l_out:
        popal
        mov eax, [ebp - 0x20]
        cmp dword ptr [eax + 0x30], 0
        ret
    """ % dict(P, getcls=where["getcls"]))
    # hov: Show, after `test al,al` on GetAbilityEnabled(Flying) (flags live): grounded flyers sink to GROUND_DY
    # v2 (2026-10-15, patch_grounded_melee_v1.py): a grounded unit now reads Flying = 0, so the 0xB8 test runs on BOTH
    # paths - grounded -> GROUND_DY whatever the Flying read says; else flyers hover (-8), walkers take vanilla 0.
    place("hov", """
        setne cl
        push ecx
        mov eax, [ebp - 4]
        mov eax, [eax + 0x1c]
        mov edx, %(gr)d
        mov ecx, [eax]
        call dword ptr [ecx + 0xa8]
        pop ecx
        test al, al
        jnz h_ground
        test cl, cl
        jz %(hz)#x
        mov dword ptr [ebp - 0x38], -8
        jmp %(hd)#x
    h_ground:
        mov dword ptr [ebp - 0x38], %(gdy)d
        jmp %(hd)#x
    """ % P)
    # shd: ShowShadow prologue (eax = hs, edx/ecx = view, [esp+4] = surface; ret 4)
    place("shd", """
        push eax
        push ecx
        push edx
        mov eax, [eax + 0x1c]
        test eax, eax
        jz d_draw
        mov edx, %(gr)d
        mov ecx, [eax]
        call dword ptr [ecx + 0xa8]
        test al, al
        jz d_draw
        pop edx
        pop ecx
        pop eax
        ret 4
    d_draw:
        pop edx
        pop ecx
        pop eax
        push ebp
        mov ebp, esp
        add esp, -0x30
        jmp %(shr)#x
    """ % P)
    assert ZONE + len(out) <= ZONE_END, hex(ZONE + len(out))
    return bytes(out), where


def pe_info(d):
    pe = struct.unpack_from("<I", d, 0x3C)[0]; opt = struct.unpack_from("<H", d, pe + 20)[0]; nsec = struct.unpack_from("<H", d, pe + 6)[0]
    secs = [struct.unpack_from("<IIII", d, pe + 24 + opt + 40 * k + 8) for k in range(nsec)]
    def r2f(rva):
        for vs, va, rs, ro in secs:
            if va <= rva < va + max(vs, rs): return ro + rva - va
    return pe, r2f


def reloc_set(d, base):
    pe, r2f = pe_info(d)
    rrva, rsz = struct.unpack_from("<II", d, pe + 24 + 0x88)
    p = r2f(rrva); end = p + rsz; out = set()
    while p < end:
        page, size = struct.unpack_from("<II", d, p)
        if size < 8: break
        for q in range(p + 8, p + size, 2):
            e = struct.unpack_from("<H", d, q)[0]
            if e >> 12 == 3: out.add(base + page + (e & 0xFFF))
        p += size
    return out


def check_thunks(d):
    import pefile
    pe = pefile.PE(data=bytes(d), fast_load=True); pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]])
    iat = {}
    for ent in getattr(pe, "DIRECTORY_ENTRY_IMPORT", []):
        for imp in ent.imports: iat[imp.address] = (imp.name or b"").decode("latin1")
    for va, want in THUNKS.items():
        b = d[va - V2F:va - V2F + 6]
        assert b[:2] == b"\xff\x25", "thunk %#x is not jmp [mem]: %s" % (va, b.hex())
        slot = struct.unpack_from("<I", b, 2)[0]
        assert want in iat.get(slot, ""), "thunk %#x -> %r, wanted %r" % (va, iat.get(slot), want)
    assert "SetUnit" in iat.get(SETUNIT_SLOT, ""), "import slot %#x is %r" % (SETUNIT_SLOT, iat.get(SETUNIT_SLOT))


def check_epack():
    """The AoWEPACK half must be live: jmp at the gw_sync export, and the clone BSS slack untouched by the file."""
    e = open(EP_DLL, "rb").read(); off = EP_SYNC - 0x55700C00
    ok = e[off] == 0xE9
    return "ok" if ok else "MISSING (apply patch_gravitywell_v1.py v2 first)"


def plan(dis):
    d = bytearray(open(DLL, "rb").read())
    check_thunks(d)
    blob, where = build()
    states, patched = {}, {}
    for name, va, orig, kind, _r in SITES:
        op = b"\xe8" if kind == "call" else b"\xe9"
        new = op + struct.pack("<i", where[name] - (va + 5)) + b"\x90" * (len(orig) - 5); patched[name] = (va, orig, new)
        live = bytes(d[va - V2F:va - V2F + len(orig)])
        if live == orig: states[name] = "vanilla"
        elif live == new: states[name] = "ours"
        elif live[0] in (0xE8, 0xE9) and ZONE <= va + 5 + struct.unpack_from("<i", live, 1)[0] < ZONE_END: states[name] = "ours(old)"
        else: states[name] = "OTHER"
    zl = bytes(d[ZONE - V2F:ZONE_END - V2F])
    zstate = "zero" if not any(zl) else "ours" if zl[:len(blob)] == blob and not any(zl[len(blob):]) else "DIFFERS"
    rl = reloc_set(bytes(d), BASE)
    bad = [hex(r) for r in rl if ZONE - 3 <= r < ZONE_END or any(va - 3 <= r < va + len(o) for _n, va, o, _k, _r in SITES)]
    ep = check_epack()
    print("AoWTCPCK: sites %s | zone %s (%d B: %s) | relocs %s | AoWEPACK gw_sync export %s" % (states, zstate, len(blob),
          ", ".join("%s=%#x" % kv for kv in where.items()), bad or "none", ep))
    if dis:
        import capstone
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(blob, ZONE):
            print("   %08X  %-18s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    return d, blob, states, patched, zstate, bad, ep


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true"); ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    d, blob, states, patched, zstate, bad, ep = plan(a.dis)
    if bad or "OTHER" in states.values(): print("ABORT (relocs or a foreign hook)"); return 1
    if zstate == "DIFFERS" and not any(s.startswith("ours") for s in states.values()): print("ABORT (zone not free)"); return 1
    if a.apply and ep != "ok": print("ABORT: AoWEPACK half missing"); return 1
    out = bytearray(d)
    if a.revert:
        for va, orig, _new in patched.values(): out[va - V2F:va - V2F + len(orig)] = orig
        out[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE)
    else:
        out[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE); out[ZONE - V2F:ZONE - V2F + len(blob)] = blob
        for va, _orig, new in patched.values(): out[va - V2F:va - V2F + len(new)] = new
    if out == d: print("already applied" if not a.revert else "already vanilla"); return 0
    if not (a.apply or a.revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(DLL, ".bak_gravityfield")
    if not os.path.exists(bak): shutil.copy2(DLL, bak); print("backup ->", bak)
    with open(DLL, "r+b") as f: f.write(bytes(out))
    assert open(DLL, "rb").read() == bytes(out); print("AoWTCPCK: %s and verified" % ("reverted" if a.revert else "written"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
