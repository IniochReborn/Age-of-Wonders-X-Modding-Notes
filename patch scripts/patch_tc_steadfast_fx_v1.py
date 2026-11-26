#!/usr/bin/env python3
r"""
STEADFAST (218) v2 VISUALS - a green shield floating down onto every FRIENDLY unit in the area (2026-10-17).
AoWTCPCK.dll only.  Visual only (no RNG, no gameplay state): the 0xC5 grant / live DEF stay in patch_steadfast_v1.py.

User: "steadfast gfx sucks. change the gfx to be green not yellow. and have it be shields above each unit in the AOE
that float down similar to other spells we've made. maybe a very subtle green transparent pillar of light? and change
the ground circles to something more unique".

RE: 218 is a Great Hail clone (hail class 0x0A, 7 strikes = the target hex + its ring).  Each strike's TfxHS (kind
0x34) draws the spell's gfx slot 0 (projectile) / 1 (trail) / 2 (impact) itself - v1 slot 2 = the per-HEX ring, which
also played on empty and enemy hexes.  v2: slots 0-2 are all the blank image (pipeline), and the landing spawns a
per-UNIT effect instead:

  land  0x40C609 (the landing tail, hex = [ebp-0x28]/[ebp-0x2C], fx = [ebp-0x20], te = [ebp-4]) - CHAINED: the
        site's `call` (Sanctify's field cave today, which itself chains Gravity Well's) is redirected to our cave,
        which ends in `jmp prev`.  For te spell [te+0x18] == 218 and fx kind [fx+0x14] == 0x34 whose target
        [fx+0x2C] (the combat object NextStrike found on the strike hex) is ALIVE (VMT+0x60), on the CASTER's side
        (byte [obj+0x45] == [[te+0x10]+0x45]; a nil caster skips the side test) and not a machine (TUnit [obj+0x4C]
        VMT+0x114 != 2 - patch_steadfast_v1's own grant rules): ONE kind-0x26 driver (the Soul Siphon / Crosswind
        recipe: AddEffect 0x41C6EC dl 0x26, TXYZ via the import slot, XYZList.Add / GetXYZ) at the unit's hex centre
        (sprite [obj+0x60] VMT+0x74/+0x78 -> HXtoHP 0x4022BC + 16/16), [fx+0x14] 0x34, [fx+0x18] 218, [fx+0x24] =
        MARKER 3, [fx+0x2C] nil.  Enemies, machines and empty hexes get nothing.
  nf    0x42A5E9 (kind-0x26 NewFrame slot pick, fx = [ebp-8], returns edx = slot) - CHAINED call: 218 + marker 3 ->
        slot 3 (driver lifetime = slot 3's frames x (f18+1)); anything else -> previous target.
  show  0x430059 (TfxHS.Show kind-0x26 slot pick, fx = [ebp-4], returns eax = slot) - CHAINED call: same mapping.
The art (DualDF 4400-4425 `steadfast_shield`, 96x128, anchor -48/-112 = the hex-centre point) is slot 3 of the
pipeline entry (see _steadfast2_integration.txt).

Zone 0x448C00..0x449400 (verified zero, no relocs; 0x448400..0x448C00 = Mend Walls v2).  Header +0/+4/+8 = previous
land / nf / show targets (decoded at apply time, restored by --revert, which refuses when something has been chained
in front of one of our sites since).  PIC via call/pop delta for the in-image globals (TCPCK rebases).
Dry-run default; --apply / --revert / --dis / --dll <copy>.  Backup <game>\backup\AoWTCPCK.dll.bak_steadfastfx.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DEFAULT_DLL = game_file("AoWTCPCK.dll")
BAK_SUFFIX = ".bak_steadfastfx"
BASE, CODE_V2F = 0x400000, 0x400C00
ZONE, ZONE_END = 0x448C00, 0x449400
HDR = 0x10
SPELL, MARKER, FX_STRIKE = 218, 3, 0x34
SITES = {"land": 0x40C609, "nf": 0x42A5E9, "show": 0x430059}          # all 5-byte `call rel32` sites
ORDER = ("land", "nf", "show")
MAP_GLOBAL, TXYZ_IAT = 0x46C064, 0x46EB24
HXTOHP, ADDEFFECT, TOBJCREATE, XYZADD, GETXYZ = 0x4022BC, 0x41C6EC, 0x401040, 0x402DE4, 0x402DF4
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, va):
    return bytes(ks.asm(src, va)[0])


def build_land(va, prev):
    def src(l0):
        return """
        pushad
        mov eax, dword ptr [ebp-4]
        cmp dword ptr [eax+0x18], %(id)d
        jne out
        mov eax, dword ptr [ebp-0x20]
        cmp dword ptr [eax+0x14], %(kind)d
        jne out
        mov esi, dword ptr [eax+0x2c]
        test esi, esi
        jz out
        mov eax, esi
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x60]
        test al, al
        jz out
        mov eax, dword ptr [ebp-4]
        mov eax, dword ptr [eax+0x10]
        test eax, eax
        jz noside
        mov al, byte ptr [eax+0x45]
        cmp al, byte ptr [esi+0x45]
        jne out
    noside:
        mov eax, dword ptr [esi+0x4c]
        test eax, eax
        jz out
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x114]
        cmp al, 2
        je out
        mov edi, dword ptr [esi+0x60]
        test edi, edi
        jz out
        call l0
    l0:
        pop ebx
        sub ebx, %(l0)#x
        sub esp, 8
        mov eax, edi
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x78]
        movsx esi, al
        mov eax, edi
        mov edx, dword ptr [eax]
        call dword ptr [edx+0x74]
        movsx eax, al
        lea edx, [esp+4]
        push edx
        lea ecx, [esp+4]
        mov edx, esi
        call %(hx)#x
        mov eax, dword ptr [ebx+%(map)#x]
        mov dl, 0x26
        call %(add)#x
        mov edi, eax
        mov dword ptr [edi+0x14], %(kind)d
        mov dword ptr [edi+0x18], %(id)d
        mov dword ptr [edi+0x24], %(marker)d
        mov dword ptr [edi+0x2c], 0
        mov dl, 1
        mov eax, dword ptr [ebx+%(txyz)#x]
        call %(create)#x
        mov edx, eax
        mov eax, dword ptr [edi+0x1c]
        call %(xyzadd)#x
        mov eax, dword ptr [edi+0x1c]
        xor edx, edx
        call %(getxyz)#x
        mov edx, dword ptr [esp]
        add edx, 16
        mov dword ptr [eax+4], edx
        mov edx, dword ptr [esp+4]
        add edx, 16
        mov dword ptr [eax+8], edx
        add esp, 8
    out:
        popad
        jmp %(prev)#x
        """ % {"id": SPELL, "kind": FX_STRIKE, "marker": MARKER, "l0": l0, "hx": HXTOHP, "map": MAP_GLOBAL,
               "add": ADDEFFECT, "txyz": TXYZ_IAT, "create": TOBJCREATE, "xyzadd": XYZADD, "getxyz": GETXYZ, "prev": prev}
    b = asm(src(0x12345678), va); k = b.find(b"\xe8\x00\x00\x00\x00\x5b"); assert k > 0        # dummy imm32 -> same encoding
    out = asm(src(va + k + 5), va); assert len(out) == len(b)
    return out


def build_nf(va, prev):
    return asm("""
        push eax
        mov eax, dword ptr [ebp-8]
        cmp dword ptr [eax+0x18], %(id)d
        jne p
        cmp dword ptr [eax+0x24], %(m)d
        jne p
        pop eax
        mov edx, %(m)d
        ret
    p:
        pop eax
        jmp %(prev)#x
    """ % {"id": SPELL, "m": MARKER, "prev": prev}, va)


def build_show(va, prev):
    return asm("""
        mov eax, dword ptr [ebp-4]
        cmp dword ptr [eax+0x18], %(id)d
        jne p
        cmp dword ptr [eax+0x24], %(m)d
        jne p
        mov eax, %(m)d
        ret
    p:
        jmp %(prev)#x
    """ % {"id": SPELL, "m": MARKER, "prev": prev}, va)


BUILD = {"land": build_land, "nf": build_nf, "show": build_show}


def reloc_set(d):
    import pefile
    pe = pefile.PE(data=d, fast_load=True)
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_BASERELOC"]])
    return {e.rva + BASE for b in getattr(pe, "DIRECTORY_ENTRY_BASERELOC", []) for e in b.entries if e.type}


def write_inplace(path, data):
    with open(path, "r+b") as f:
        f.seek(0); f.write(data); f.truncate()


def build_zone(prevs):
    out = bytearray(struct.pack("<III", *(prevs[k] for k in ORDER)) + bytes(HDR - 12)); where = {}
    for k in ORDER:
        while len(out) % 16: out.append(0)
        va = ZONE + len(out); where[k] = va; out += BUILD[k](va, prevs[k])
    assert ZONE + len(out) <= ZONE_END, hex(ZONE + len(out))
    return bytes(out), where


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dll", default=DEFAULT_DLL)
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true"); ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read())
    f = lambda va: va - CODE_V2F
    cur, state = {}, {}
    for k, s in SITES.items():
        b = bytes(d[f(s):f(s) + 5]); assert b[0] == 0xE8, "%s site %#x is not a call (%s)" % (k, s, b.hex())
        cur[k] = s + 5 + struct.unpack_from("<i", b, 1)[0]
        state[k] = "ours" if ZONE <= cur[k] < ZONE_END else "chain(%#x)" % cur[k]
    zl = bytes(d[f(ZONE):f(ZONE_END)])
    hdr_prev = dict(zip(ORDER, struct.unpack_from("<III", zl, 0)))
    n_ours = sum(1 for k in ORDER if state[k] == "ours")
    if n_ours not in (0, 3): print("ABORT: partially applied", state); return 1
    applied = n_ours == 3
    prevs = hdr_prev if applied else cur
    zone, where = build_zone(prevs)
    zstate = "zero" if not any(zl) else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else "DIFFERS"
    rl = reloc_set(bytes(d))
    bad = sorted(hex(r) for r in rl if ZONE <= r < ZONE_END or any(s <= r < s + 5 for s in SITES.values()))
    print("sites %s | prev %s | zone %s (%d B: %s) | relocs %s" % (state, {k: hex(v) for k, v in prevs.items()}, zstate, len(zone),
          ", ".join("%s=%#x" % (k, v) for k, v in where.items()), bad or "none"))
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        for i in md.disasm(zone[HDR:], ZONE + HDR): print("   %08X %-20s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad: print("ABORT: relocs"); return 1
    if a.revert:
        if not applied: print("nothing to revert"); return 0
        out = bytearray(d)
        for k, s in SITES.items():
            if cur[k] != where[k]: print("ABORT: %s site no longer points at our cave (%#x)" % (k, cur[k])); return 1
            out[f(s) + 1:f(s) + 5] = struct.pack("<i", hdr_prev[k] - (s + 5))
        out[f(ZONE):f(ZONE_END)] = bytes(ZONE_END - ZONE)
        write_inplace(a.dll, bytes(out)); print("reverted"); return 0
    if applied and zstate == "ours" and all(cur[k] == where[k] for k in ORDER): print("already applied"); return 0
    if not applied and zstate != "zero": print("ABORT: zone not zero"); return 1
    out = bytearray(d)
    out[f(ZONE):f(ZONE_END)] = bytes(ZONE_END - ZONE); out[f(ZONE):f(ZONE) + len(zone)] = zone
    for k, s in SITES.items():
        out[f(s) + 1:f(s) + 5] = struct.pack("<i", where[k] - (s + 5))
    print("%d bytes change" % sum(1 for x, y in zip(d, out) if x != y))
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(a.dll, BAK_SUFFIX)
    if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    write_inplace(a.dll, bytes(out)); assert open(a.dll, "rb").read() == bytes(out); print("Written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
