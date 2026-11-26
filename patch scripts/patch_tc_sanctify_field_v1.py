#!/usr/bin/env python3
r"""
SANCTIFY (spell 208, Life tier 3, 2026-10-16) - the CONSECRATED HEXES on the combat map.  AoWTCPCK.dll.
Needs patch_sanctify_v1.py applied first (AoWEPACK export sn_sync @0x55868020).  Modelled on
patch_gravitywell_field_v1.py (Gravity Well's field), which stays in place behind us.

Behaviour:
  * Every landed Sanctify strike (7: the target hex + its ring, patch_rotaway_v1.py STRIKES[208]) leaves a SANCTIFY HS
    on its hex (one per hex; a second cast on the same hex refreshes owner + lifetime).
  * Lifetime 3 turns: byte [hs+0x19] = TURNS counts down at each start of the CASTER's turn (the turn broadcast
    0x20021001 with the new turn player [map+0xED] == owner [hs+0x14], not while [map+0x3C] & 2); at 0 the hex
    expires (its unit loses 0xC0) and the HS frees itself (TCombatFire.NewTurn's own idiom).  Cast in the caster's
    turn T0 -> active through 3 enemy turns and the caster's turns T1, T2 -> gone when T3 begins.
  * A unit standing on a consecrated hex holds 0xC0 'Sanctified Ground' (patch_sanctify_v1.py: good -> Fearless +
    Holy Champion I, pure good -> Fearless + Holy Champion II, pure neutral / evil -> Panicked, pure evil -> Panicked
    + Vertigo): granted when the hex is consecrated under it (field PlaceOnMap) or when it ends a move there
    (AoWEPACK pom hook), removed when it moves off (pom) or the hex expires (MsgProc).  All of it runs inside TE
    execution / the turn broadcast -> identical on every peer.

Sanctify HS = a runtime CLONE of the TCombatFire VMT (VMT-0x40..+0x110 = all 68 slots - the Oil Spring v3.2 lesson)
in AoWEPACK's BSS page slack at CLONE_EP (0x558FAD00..0x558FAE50, VMT ptr +0x40; referenced by no other script - the
Gravity clone sits at 0x558FA400..0x558FA550), reached through the TCombatUnit.SetUnit import-slot delta, as is the
AoWEPACK export; instance size 0x1C (+0x14 owner, +0x18 TCombatFire's skip byte (unused), +0x19 turns left).  Slots:
   +0x24 ClassID      -> 0x22010E (unused anywhere; 0x22010B oil / 0x22010C gravity)
   +0x44 MsgProc      -> inherited TEObject.MsgProc, then the countdown above
   +0x64 GetLevel / +0x8C GetShowPriority / +0xD0 CanMoveOn -> TCOozeHS's (a ground decal, no movement effect)
   +0xA8 Show         -> spell 208's own image list [spell+0x2C] slot FIELD_SLOT (3), frame by time (TImageSequence.
                         GetFrameIndex(tick, phase = self>>2)), drawn at HXtoHP(hex) - view + the sequence offsets
   +0xAC PlaceOnMap   -> THexagonSprite.PlaceOnMap, then sn_sync(the unit already on the hex, 1)
   +0x58 GetOverlay stays THexagonSprite's default (0xFE = none: terrain / passability untouched).
Site:
   land  0x40C609 - CHAINED: Gravity Well's `call 0x43EEB0` (which replays `mov eax,[ebp-0x20] / cmp dword
         [eax+0x30],0`) becomes `call cave`; the cave places / refreshes the HS for te spell [te+0x18] == 208 and
         fx kind [fx+0x14] == 0x34, then `jmp` to the previous target (its `ret` returns to the site).
         --revert puts Gravity Well's call back (refuses if something else chained in front of us since).
Zone 0x441400..0x441800 (zero, reloc-free).  PIC call/pop delta for every in-image absolute (TCPCK rebases).
Thunks import-table checked.  Dry-run default; --apply / --revert / --dis / --dll <copy> [--ep <AoWEPACK copy>].
Backup <game>\backup\AoWTCPCK.dll.bak_sanctfield.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DEFAULT_DLL = game_file("AoWTCPCK.dll"); DEFAULT_EP = game_file("AoWEPACK.dll")
BASE, V2F = 0x400000, 0x400C00
ZONE, ZONE_END = 0x441400, 0x441800
HDR = 0x10                        # zone header: +0 previous land-site call target
SPELL_ID, FIELD_CLASSID, UNITHS_CLASSID, FX_STRIKE = 208, 0x22010E, 0x220104, 0x34
FIELD_SLOT, TURNS = 3, 3
TURN_MSG = 0x20021001
SETUNIT_SLOT, SETUNIT_VA = 0x46E858, 0x55725194
EP_SYNC = 0x55868020              # patch_sanctify_v1.py export: jmp sn_sync (eax = TUnit, dl = on)
EP_ZONE = (0x55868000, 0x55868800)
CLONE_EP, VMT_LO, VMT_HI = 0x558FAD40, 0x40, 0x110   # AoWEPACK BSS slack 0x558FAD00..0x558FAE50 (VMT ptr = +0x40)
MAPLIST, TICKOBJ, HSSET = 0x469420, 0x46E8D4, 0x46E8D0
FIRE_CELL, OOZE_CELL, FIRE_CREATE = 0x406AE4, 0x41275C, 0x406F68
T_MSGPROC, T_FREE, T_PLACEON, T_GETSPELL, T_GETSEQ, T_FRAMEIDX, T_LIBGET, T_HXTOHP, T_PLACEHX, T_GETLEVEL, T_GETFIELD = (
    0x401404, 0x401050, 0x401C5C, 0x4029B4, 0x4016E4, 0x4016D4, 0x4016F4, 0x4022BC, 0x402264, 0x401E64, 0x401E54)
THUNKS = {T_MSGPROC: "TEObject.MsgProc", T_FREE: "TObject.Free", T_PLACEON: "THexagonSprite.PlaceOnMap",
          T_GETSPELL: "TSpellControl.GetSpell", T_GETSEQ: "GetImageSequence", T_FRAMEIDX: "TImageSequence.GetFrameIndex",
          T_LIBGET: "TCustomImageLibrary.Get", T_HXTOHP: "HSEngine.HXtoHP", T_PLACEHX: "THSMap.PlaceHX",
          T_GETLEVEL: "TMapContainer.GetMapLevel", T_GETFIELD: "TMapLevel.GetField"}
LAND = 0x40C609
LAND_VANILLA = bytes.fromhex("8b45e083783000")

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


def build(prev_land):
    out = bytearray(HDR); where = {}
    struct.pack_into("<I", out, 0, prev_land)
    def place(name, src):
        while len(out) % 16: out.append(0)
        va = ZONE + len(out); where[name] = va; out.extend(asm_delta(src, va))
    P = {"slot": SETUNIT_SLOT, "suva": SETUNIT_VA, "sync": EP_SYNC, "clone": CLONE_EP, "maplist": MAPLIST, "hsset": HSSET,
         "tick": TICKOBJ, "fire": FIRE_CELL, "ooze": OOZE_CELL, "create": FIRE_CREATE, "msgproc": T_MSGPROC, "free": T_FREE,
         "placeon": T_PLACEON, "getspell": T_GETSPELL, "getseq": T_GETSEQ, "frameidx": T_FRAMEIDX, "libget": T_LIBGET,
         "hxtohp": T_HXTOHP, "placehx": T_PLACEHX, "getlevel": T_GETLEVEL, "getfield": T_GETFIELD, "id": SPELL_ID,
         "fcls": FIELD_CLASSID, "ucls": UNITHS_CLASSID, "kind": FX_STRIKE, "fslot": FIELD_SLOT, "turns": TURNS,
         "turn": TURN_MSG, "lo": VMT_LO, "ndw": (VMT_LO + VMT_HI) // 4, "prev": prev_land}
    place("classid", "mov eax, %(fcls)#x\n ret" % P)
    # unit_sync(eax = field, dl = on): the unit standing on the field (if any) -> AoWEPACK sn_sync; preserves all regs
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
    # MsgProc(eax = self, edx = msg, ecx): inherited; on the turn broadcast count the caster's turns down
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
        movsx eax, byte ptr [eax + 0xed]
        cmp eax, [esi + 0x14]
        jne m_out
        dec byte ptr [esi + 0x19]
        jg m_out
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
    # Show(eax = self, edx = dx, ecx = dy, [ebp+8] = surface; ret 4) - TCombatFire.Show with spell 208's own sequence
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
    # land: every landed fx, hex = [ebp-0x28]/[ebp-0x2C], fx = [ebp-0x20], te = [ebp-4]; then the previous target
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
        mov byte ptr [eax + 0x19], %(turns)d
        jmp l_out
    l_new:
        call %(getcls)#x
        xor ecx, ecx
        mov dl, 1
        call %(create)#x
        mov edi, eax
        mov edx, [ebx + %(maplist)#x]
        mov edx, [edx]
        movsx edx, byte ptr [edx + 0xed]
        mov [edi + 0x14], edx
        mov byte ptr [edi + 0x19], %(turns)d
        push dword ptr [ebp - 0x2c]
        push 0
        mov eax, [ebx + %(maplist)#x]
        mov eax, [eax]
        mov edx, edi
        mov ecx, [ebp - 0x28]
        call %(placehx)#x
        test al, al
        jnz l_out
        mov eax, edi
        call %(free)#x
    l_out:
        popal
        jmp %(prev)#x
    """ % dict(P, getcls=where["getcls"]))
    zone = bytes(out)
    assert ZONE + len(zone) <= ZONE_END, hex(ZONE + len(zone))
    return zone, where


def reloc_set(d):
    pe = struct.unpack_from("<I", d, 0x3C)[0]; opt = struct.unpack_from("<H", d, pe + 20)[0]; nsec = struct.unpack_from("<H", d, pe + 6)[0]
    secs = [struct.unpack_from("<IIII", d, pe + 24 + opt + 40 * k + 8) for k in range(nsec)]
    rrva, rsz = struct.unpack_from("<II", d, pe + 24 + 0x88)
    def r2f(rva):
        for vs, va, rs, ro in secs:
            if va <= rva < va + max(vs, rs): return ro + rva - va
    p = r2f(rrva); end = p + rsz; out = set()
    while p < end:
        page, size = struct.unpack_from("<II", d, p)
        if size < 8: break
        for q in range(p + 8, p + size, 2):
            e = struct.unpack_from("<H", d, q)[0]
            if e >> 12 == 3: out.add(BASE + page + (e & 0xFFF))
        p += size
    return out


def check_thunks(d):
    import pefile
    pe = pefile.PE(data=bytes(d), fast_load=True); pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]])
    iat = {}
    for ent in getattr(pe, "DIRECTORY_ENTRY_IMPORT", []):
        for imp in ent.imports: iat[imp.address] = imp.name or b""
    for va, want in THUNKS.items():
        b = d[va - V2F:va - V2F + 6]
        assert b[:2] == b"\xff\x25", "thunk %#x is not jmp [mem]: %s" % (va, b.hex())
        slot = struct.unpack_from("<I", b, 2)[0]
        name = iat.get(slot, b"").decode("latin-1")
        assert all(p in name for p in want.split(".")), "thunk %#x -> %r, wanted %r" % (va, name, want)
    assert "SetUnit" in iat.get(SETUNIT_SLOT, b"").decode("latin-1"), "import slot %#x is %r" % (SETUNIT_SLOT, iat.get(SETUNIT_SLOT))
    assert 0x558FA231 <= CLONE_EP - VMT_LO and CLONE_EP + VMT_HI <= 0x558FB000, "clone room outside the AoWEPACK BSS page slack"


def ep_ready(path):
    """The AoWEPACK export must be live (patch_sanctify_v1.py applied) and the clone room must be untouched BSS slack."""
    d = open(path, "rb").read(); o = EP_SYNC - 0x55700C00
    if d[o] != 0xE9: return "AoWEPACK export missing (apply patch_sanctify_v1.py first)"
    t = EP_SYNC + 5 + struct.unpack_from("<i", d, o + 1)[0]
    return None if EP_ZONE[0] <= t < EP_ZONE[1] else "AoWEPACK export points outside its zone (%#x)" % t


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--dll", default=DEFAULT_DLL); ap.add_argument("--ep", default=DEFAULT_EP)
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true"); ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read())
    check_thunks(d)
    rd = lambda va, n: bytes(d[va - V2F:va - V2F + n])
    inzone = lambda t: ZONE <= t < ZONE_END
    zl = rd(ZONE, ZONE_END - ZONE)
    site = rd(LAND, 7)
    if site == LAND_VANILLA:
        state, prev = "vanilla", 0
    elif site[0] == 0xE8 and site[5:] == b"\x90\x90":
        t = LAND + 5 + struct.unpack_from("<i", site, 1)[0]
        if inzone(t): state, prev = "ours", struct.unpack_from("<I", zl, 0)[0]
        else: state, prev = "chain", t
    else:
        state, prev = "OTHER(%s)" % site.hex(), 0
    zone, where = build(prev if prev else 0x7FFFFFF0)
    rl = reloc_set(bytes(d))
    bad = [hex(r) for r in rl if ZONE - 3 <= r < ZONE_END or LAND - 3 <= r < LAND + 7]
    zstate = "zero" if not any(zl) else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) \
        else "ours(old)" if state == "ours" else "DIFFERS"
    epmsg = ep_ready(a.ep)
    print("AoWTCPCK sanctify field: land %s (prev %#x) | zone %s (%d B: %s) | relocs %s | AoWEPACK %s" % (
        state, prev, zstate, len(zone), ", ".join("%s=%#x" % kv for kv in where.items()), bad or "none", epmsg or "export ok"))
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        cav = sorted((v, k) for k, v in where.items()) + [(ZONE + len(zone), None)]
        for (va, nm), (nx, _n) in zip(cav, cav[1:]):
            print("  [%s]" % nm)
            for i in md.disasm(zone[va - ZONE:nx - ZONE], va):
                if i.mnemonic == "add" and i.op_str == "byte ptr [eax], al": break
                print("   %08X  %-18s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad or state.startswith("OTHER") or zstate == "DIFFERS" or (state == "vanilla" and not a.revert):
        print("ABORT (%s)" % ("Gravity Well's field must be applied first - this script chains in front of it" if state == "vanilla" else "relocs / foreign hook / zone not free"))
        return 1
    if a.revert:
        if state != "ours": print("ABORT revert: not applied, or another patch is chained in front (%s)" % state); return 1
        d[LAND - V2F:LAND - V2F + 5] = b"\xe8" + struct.pack("<i", prev - (LAND + 5))
        d[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE)
        with open(a.dll, "r+b") as f: f.write(bytes(d))
        print("reverted (land site -> %#x, zone zeroed)" % prev); return 0
    if epmsg: print("ABORT (%s)" % epmsg); return 1
    if state == "ours" and zstate == "ours": print("already applied"); return 0
    if zstate == "ours(old)": print("older build of this patch detected -> rewriting the zone in place")
    d[ZONE - V2F:ZONE_END - V2F] = bytes(ZONE_END - ZONE); d[ZONE - V2F:ZONE - V2F + len(zone)] = zone
    d[LAND - V2F:LAND - V2F + 5] = b"\xe8" + struct.pack("<i", where["land"] - (LAND + 5))
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(a.dll, ".bak_sanctfield")
    if a.dll == DEFAULT_DLL and not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    with open(a.dll, "r+b") as f: f.write(bytes(d))
    assert open(a.dll, "rb").read() == bytes(d); print("Written and verified"); return 0


if __name__ == "__main__":
    sys.exit(main())
