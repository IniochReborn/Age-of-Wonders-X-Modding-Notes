"""
DROUGHT (spell 391) - the map-wide cast effect, ORANGE/RED version of Water Mastery's twinkle (2026-10-14, v2).  AoWEPACK.dll.

RE (live AoWEPACK.dll):
  TWaterMastery.ExecuteTE ends with `mov dl,2 / call 0x55779068` @0x557F0A81.  0x55779068(eax map, dl type) creates an
  AoWE.TWorldFXHS (class cell 0x55709C68 -> VMT 0x55709CA8, instance size 0x28, Create 0x55795FF0), stores the type in
  byte [hs+0x24] (TWorldFXType: 0 fxHatred, 1 fxCrusade, 2 fxWaterMastery, 3 fxSpellWard, 4 fxWMParticle,
  5 fxWMLParticle, 6 fxHatredParticle, 7 fxSWParticle, 8 fxSWBeamParticle, 9 fxEarthMastery, 10 fxEMParticle,
  11 fxTranquility, 12 fxTranqParticle), adds it to the map, returns it in eax.  Purely local display (System.Random
  for positions; nothing synced or saved).
  TWorldFXHS.NewFrame 0x557960B0 (jump table 0x557960FD by type), case 2 fxWaterMastery 0x557964D9: lives 200 ticks
  ([hs+0x10]); every 5 ticks it plays GetSpell(0x2D)[+0x28] sound cue 1 (@0x5579651A `mov edx,0x2D`) and spawns
  ~100-110 type-4 particles at screen position (50,50) bursting outward (spawn @0x5579654D, `mov ebx,eax` @0x55796559)
  plus two rings of type-4 particles (spawn @0x55796609, `mov ebx,eax` @0x55796615) - SCREEN-space, not water hexes.
  TWorldFXHS.Show 0x55797118 (jump table 0x55797175, index type-4), case 4 fxWMParticle @0x557971CB: draws
  GetSpell(0x2D)[+0x2C] image sequence 0 (@0x557971D6 `mov edx,0x2D`) = Water Mastery's record slot 0 (PARTICLE 0-2,
  the blue twinkle).  (Show case 5 = GetSpell(0x40) slot 0, case 7 = 0x4B slot 1, case 8 = 0x2E, ... - every
  particle type borrows a fixed spell's record.)
Patch: a "Drought" marker in the unused padding byte [hs+0x25] (zeroed by InitInstance; no TWorldFXHS code touches
  +0x25..+0x27):
  EV  @0x557F0A81 (7 B -> call + 2 nop): `mov dl,2 / call 0x55779068`, and for spell 391 (ebx = spell) [eax+0x25] := 1.
  ID1 @0x5579651A and ID2 @0x557971D6 (5 B `mov edx,0x2D`): edx = 391 when [[ebp-4]+0x25] != 0 ([ebp-4] = the
      TWorldFXHS in both NewFrame and Show) -> Drought's own record: sound cue 1 / image slot 0.
  P1  @0x55796559 (9 B `mov ebx,eax / mov dword [ebx+0x14],0x32`) and P2 @0x55796615 (5 B `mov ebx,eax /
      mov eax,[ebp-4]`): copy the master's marker byte into each new particle.
Zone 0x5585FF00..0x5585FFC0 (zero, reloc-free; rel32 calls only - position-independent, nothing to rebase).
v1 (dl 0 = fxHatred for 391, 19-B cave at 0x5585FF00) is detected; --apply replaces it in place.
v3 (2026-10-15; user: make Drought's cast gfx more like Overgrowth's, covering the map): for spell 391 the EV cave no
  longer creates the fxWaterMastery TWorldFXHS at all; it calls DRIFT instead = a replay of TAirMastery.ExecuteTE's
  map-wide animation setup (0x557F064E..0x557F06A1): animation object (class cell [0x557FAE60], Create 0x557FB4A8
  eax=class dl=1 ecx=0), [obj+0xB] := 0x1C, [obj+0x28] := the spell (ebx), [obj+0x24] := the Air Mastery draw
  callback 0x557F050C, [obj+0x38] := [[0x558E9494]] (the map), [obj+0x34] := ([map+0x8C] & 0xFFFF) | ([map+0x90] << 16),
  then obj.VMT+0xE0 (start).  The callback draws Random(3) = gfx slots 0..2 of the spell's OWN record ([spell+0x2C])
  all over the screen for 90 ticks - exactly what Overgrowth / World Healer / Ice Age get.  Purely local display, like
  the vanilla Air Mastery cast (no sync impact).  Absolute operands (class cell, callback, map cell) are read PIC
  (call/pop delta); calls are rel32.  DRIFT lives in its own zone 0x5585FC00..0x5585FD00 (zero, reloc-free).  The
  ID1/ID2/P1/P2 sites stay hooked but are now inert (no 391 TWorldFXHS -> the +0x25 marker is never set), and Drought's
  repeating cue-1 sound (DUALFA_DROUGHTP, played by the TWorldFXHS every 5 ticks) no longer plays; the cast sound
  (cue 0, TWaterMastery.ExecuteTE @0x557F0A72) is unchanged.
  NOTE the Air callback draws slots 0..2 -> Drought's record needs three drift frames in slots 0..2 and its hex glow
  moved to slot 3 (patch_drought_glow_v1.py GLOW_SLOT = 3).  v2 (the TWorldFXHS marker version) is detected and
  upgraded in place.
Dry-run default; --apply / --revert (in place: every site back to its original bytes, zones zeroed); --dis.
Backup <game>\\backup\\AoWEPACK.dll.bak_droughtfx.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DLL = game_file("AoWEPACK.dll")
BASE, CODE_V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x5585FF00, 0x5585FFC0   # in the long free run 0x55817000..0x55860000
DZONE, DZONE_END = 0x5585FC00, 0x5585FD00 # v3: DRIFT (zero, reloc-free; drought_once sits at 0x5585FD00)
AIR_ANIM_CELL, AIR_ANIM_CREATE = 0x557FAE60, 0x557FB4A8   # TAirMastery.ExecuteTE @0x557F0652 / 0x557F0657
AIR_DRAW_CB = 0x557F050C                                  # the Air Mastery map-wide draw callback (Random(3) slots 0..2)
MAP_CELL = 0x558E9494                                     # [[cell]] = the TAoWHSMap
SPELL_ID, WM_ID = 391, 0x2D
WORLD_EVENT = 0x55779068
SITES = {   # name: (va, original bytes)
    "EV":  (0x557F0A81, bytes.fromhex("b202e8e085f8ff")),        # mov dl,2 / call 0x55779068
    "ID1": (0x5579651A, bytes.fromhex("ba2d000000")),             # mov edx,0x2D  (NewFrame case 2: sound cue 1)
    "P1":  (0x55796559, bytes.fromhex("8bd8c7431432000000")),     # mov ebx,eax / mov dword [ebx+0x14],0x32
    "P2":  (0x55796615, bytes.fromhex("8bd88b45fc")),             # mov ebx,eax / mov eax,[ebp-4]
    "ID2": (0x557971D6, bytes.fromhex("ba2d000000")),             # mov edx,0x2D  (Show case 4: image slot 0)
}
V1_CAVE = bytes.fromhex("b202817b10870100007502b200")   # v1's cave head (mov dl,2 / cmp [ebx+0x10],391 / jne / mov dl,0)

ks = Ks(KS_ARCH_X86, KS_MODE_32)


def build(v2=False):
    srcs = {
        "EV": """
            mov dl, 2
            call %(ev)#x
            cmp dword ptr [ebx+0x10], %(id)d
            jne e_done
            mov byte ptr [eax+0x25], 1
        e_done:
            ret
        """ if v2 else """
            cmp dword ptr [ebx+0x10], %(id)d
            je e_drift
            mov dl, 2
            call %(ev)#x
            ret
        e_drift:
            call %(drift)#x
            ret
        """,
        "ID": """
            mov edx, %(wm)d
            push ecx
            mov ecx, [ebp-4]
            cmp byte ptr [ecx+0x25], 0
            je i_done
            mov edx, %(id)d
        i_done:
            pop ecx
            ret
        """,
        "P1": """
            mov ebx, eax
            push ecx
            mov ecx, [ebp-4]
            mov cl, byte ptr [ecx+0x25]
            mov byte ptr [ebx+0x25], cl
            pop ecx
            mov dword ptr [ebx+0x14], 0x32
            ret
        """,
        "P2": """
            mov ebx, eax
            mov eax, [ebp-4]
            push ecx
            mov cl, byte ptr [eax+0x25]
            mov byte ptr [ebx+0x25], cl
            pop ecx
            ret
        """,
    }
    drift_src = """
        push edi
        call d_pic
    d_pic:
        pop edi
        sub edi, %(pic)#x
        xor ecx, ecx
        mov dl, 1
        mov eax, dword ptr [edi+%(cell)#x]
        call %(create)#x
        mov byte ptr [eax+0xb], 0x1c
        mov dword ptr [eax+0x28], ebx
        lea edx, [edi+%(cb)#x]
        mov dword ptr [eax+0x24], edx
        mov edx, dword ptr [edi+%(map)#x]
        mov edx, dword ptr [edx]
        mov dword ptr [eax+0x38], edx
        mov ecx, dword ptr [edx+0x90]
        mov edx, dword ptr [edx+0x8c]
        and edx, 0xffff
        shl ecx, 0x10
        or edx, ecx
        mov dword ptr [eax+0x34], edx
        mov edx, dword ptr [eax]
        call dword ptr [edx+0xe0]
        pop edi
        ret
    """
    pic = DZONE + 6                                       # push edi (1) + call (5) -> the popped return address
    drift = bytes(ks.asm(drift_src % {"pic": pic, "cell": AIR_ANIM_CELL, "create": AIR_ANIM_CREATE, "cb": AIR_DRAW_CB, "map": MAP_CELL}, DZONE)[0])
    assert DZONE + len(drift) <= DZONE_END
    caves, out = {}, bytearray()
    for name in ("EV", "ID", "P1", "P2"):
        va = ZONE + len(out)
        out += bytes(ks.asm(srcs[name] % {"ev": WORLD_EVENT, "id": SPELL_ID, "wm": WM_ID, "drift": DZONE}, va)[0]); caves[name] = va
        while len(out) % 16: out.append(0)
    zone = bytes(out).rstrip(b"\x00")
    assert ZONE + len(zone) <= ZONE_END, hex(ZONE + len(zone))
    target = {"EV": caves["EV"], "ID1": caves["ID"], "ID2": caves["ID"], "P1": caves["P1"], "P2": caves["P2"]}
    hooks = {k: b"\xe8" + struct.pack("<i", target[k] - (va_ + 5)) + b"\x90" * (len(orig) - 5) for k, (va_, orig) in SITES.items()}
    caves["DRIFT"] = DZONE
    return zone, hooks, caves, (b"" if v2 else drift)


def reloc_set(d):
    pe = struct.unpack_from("<I", d, 0x3C)[0]; opt = struct.unpack_from("<H", d, pe + 20)[0]; nsec = struct.unpack_from("<H", d, pe + 6)[0]
    secs = [struct.unpack_from("<IIII", d, pe + 24 + opt + 40 * k + 8) for k in range(nsec)]
    rrva, rsz = struct.unpack_from("<II", d, pe + 24 + 0x88)
    def r2f(rva):
        for vs, va, rs, ro in secs:
            if va <= rva < va + max(vs, rs): return ro + rva - va
    p, end, out = r2f(rrva), r2f(rrva) + rsz, set()
    while p < end:
        page, size = struct.unpack_from("<II", d, p)
        if size < 8: break
        for q in range(p + 8, p + size, 2):
            e = struct.unpack_from("<H", d, q)[0]
            if e >> 12 == 3: out.add(BASE + page + (e & 0xFFF))
        p += size
    return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true"); a = ap.parse_args()
    d = bytearray(open(DLL, "rb").read())
    zone, hooks, caves, drift = build()
    zone2 = build(v2=True)[0]
    zl = bytes(d[ZONE - CODE_V2F:ZONE_END - CODE_V2F])
    zstate = ("zero" if not any(zl) else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):])
              else "v2" if zl[:len(zone2)] == zone2 and not any(zl[len(zone2):])
              else "v1" if zl.startswith(V1_CAVE) and not any(zl[0x20:]) else "DIFFERS")
    dz = bytes(d[DZONE - CODE_V2F:DZONE_END - CODE_V2F])
    dstate = "zero" if not any(dz) else "ours" if dz[:len(drift)] == drift and not any(dz[len(drift):]) else "DIFFERS"
    states = {}
    for k, (va, orig) in SITES.items():
        live = bytes(d[va - CODE_V2F:va - CODE_V2F + len(orig)])
        if live == orig: states[k] = "vanilla"
        elif live == hooks[k]: states[k] = "ours"
        elif live[0] == 0xE8 and ZONE <= va + 5 + struct.unpack_from("<i", live, 1)[0] < ZONE_END: states[k] = "ours(old)"
        else: states[k] = "OTHER"
    rl = reloc_set(bytes(d))
    bad = [hex(r) for r in rl if ZONE <= r < ZONE_END or DZONE <= r < DZONE_END or any(va <= r < va + len(orig) for va, orig in SITES.values())]
    print("sites %s | zone %s (%d B: %s) | drift zone %s (%d B) | relocs %s" % (states, zstate, len(zone), ", ".join("%s @%#x" % kv for kv in caves.items()), dstate, len(drift), bad or "none"))
    if a.dis:
        import capstone
        for z_, va0 in ((zone, ZONE), (drift, DZONE)):
            for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(z_, va0): print("   %08X  %-16s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad or "OTHER" in states.values() or zstate == "DIFFERS" or dstate == "DIFFERS": print("ABORT"); return 1
    if a.revert:
        for k, (va, orig) in SITES.items(): d[va - CODE_V2F:va - CODE_V2F + len(orig)] = orig
        d[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
        d[DZONE - CODE_V2F:DZONE_END - CODE_V2F] = bytes(DZONE_END - DZONE)
        with open(DLL, "r+b") as f: f.write(bytes(d))
        print("reverted (all sites vanilla, zone zeroed)"); return 0
    if all(s == "ours" for s in states.values()) and zstate == "ours" and dstate == "ours": print("already applied"); return 0
    d[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE); d[ZONE - CODE_V2F:ZONE - CODE_V2F + len(zone)] = zone
    d[DZONE - CODE_V2F:DZONE_END - CODE_V2F] = bytes(DZONE_END - DZONE); d[DZONE - CODE_V2F:DZONE - CODE_V2F + len(drift)] = drift
    for k, (va, orig) in SITES.items(): d[va - CODE_V2F:va - CODE_V2F + len(orig)] = hooks[k]
    if not a.apply:
        print("Dry run OK%s - rerun with --apply (or --revert)." % (" (%s is applied: --apply replaces it in place)" % zstate if zstate in ("v1", "v2") else "")); return 0
    bak = bak_path(DLL, ".bak_droughtfx")
    if not os.path.exists(bak): shutil.copy2(DLL, bak); print("backup ->", bak)
    with open(DLL, "r+b") as f: f.write(bytes(d))
    assert open(DLL, "rb").read() == bytes(d); print("Written and verified"); return 0


if __name__ == "__main__":
    sys.exit(main())
