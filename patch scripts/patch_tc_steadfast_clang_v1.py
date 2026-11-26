#!/usr/bin/env python3
r"""
STEADFAST (218) - the shield CLANG once per shielded unit (2026-10-17).  AoWTCPCK.dll only, sound only.

User: "for the sfx, repeat the shield clang for each shield/unit. don't change anything else".

The hail-class landing (TfxHS kind 0x34) plays sound cue 1 on EVERY strike hex (empty / enemy hexes too) and a
missing cue 1 AVs (Oil Spring v3.2 lesson), so cue 1 stays (DUALER_STEADHIT.WAV, now only the faint air rush) and the
clang moves to a NEW cue 2 (DUALER_STEADCLANG.WAV, the pipeline's 3rd sfx entry = a list -> spellgfx gives it ID 2),
played by this cave only for the hexes that get a shield:

  land 0x40C609 (the landing tail; te = [ebp-4], fx = [ebp-0x20]) - CHAINED in front of whatever owns it at apply time
       (patch_tc_steadfast_fx_v1.py's land cave today, 0x448C10).  Same filter as that cave (= the 0xC5 grant rules):
       te spell [te+0x18] == 218, fx kind [fx+0x14] == 0x34, target [fx+0x2C] alive (VMT+0x60), on the caster's side
       (byte +0x45; nil caster skips the test), not a machine (TUnit [obj+0x4C] VMT+0x114 != 2) -> if the sound flag
       [map+0x129] is on: TSFXLibrary.Play(GetSpell(218)[+0x28], 2).  Then `jmp prev`.
       The WAV carries a 0.74 s lead so the clang lands on the shield's touch-down (driver T_LAND).

Zone 0x44A000..0x44A800 (verified zero, no relocs).  Header +0 = previous land target, +4 = magic 'SFCL'.  PIC via
call/pop delta (map global 0x46C064 / spell registry import slot 0x46E8D0; TCPCK rebases).
LIFO: while applied, patch_tc_steadfast_fx_v1.py (and the Sanctify-field / Gravity Well field scripts behind it) see
the land site as taken -> revert THIS first, re-run them, re-apply this.
Dry-run default; --apply / --revert / --dis / --dll <copy>.  Backup <game>\backup\AoWTCPCK.dll.bak_steadclang.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DEFAULT_DLL = game_file("AoWTCPCK.dll")
BAK_SUFFIX = ".bak_steadclang"
BASE, CODE_V2F = 0x400000, 0x400C00
ZONE, ZONE_END = 0x44A000, 0x44A800
CAVE = ZONE + 0x10
MAGIC = b"SFCL"
SITE = 0x40C609
SPELL, FX_STRIKE, CUE = 218, 0x34, 2
MAP_GLOBAL, SPELLREG_GLOBAL, GETSPELL, SFXPLAY = 0x46C064, 0x46E8D0, 0x4029B4, 0x4022F4
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def build_cave(prev):
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
        call l0
    l0:
        pop ebx
        sub ebx, %(l0)#x
        mov eax, dword ptr [ebx+%(map)#x]
        test eax, eax
        jz out
        cmp byte ptr [eax+0x129], 0
        je out
        mov eax, dword ptr [ebx+%(reg)#x]
        mov eax, dword ptr [eax]
        mov eax, dword ptr [eax+0x84]
        mov edx, %(id)d
        call %(getspell)#x
        test eax, eax
        jz out
        mov eax, dword ptr [eax+0x28]
        test eax, eax
        jz out
        mov edx, %(cue)d
        call %(play)#x
    out:
        popad
        jmp %(prev)#x
        """ % {"id": SPELL, "kind": FX_STRIKE, "l0": l0, "map": MAP_GLOBAL, "reg": SPELLREG_GLOBAL,
               "getspell": GETSPELL, "play": SFXPLAY, "cue": CUE, "prev": prev}
    b = bytes(ks.asm(src(0x12345678), CAVE)[0]); k = b.find(b"\xe8\x00\x00\x00\x00\x5b"); assert k > 0
    out = bytes(ks.asm(src(CAVE + k + 5), CAVE)[0]); assert len(out) == len(b)
    return out


def build_zone(prev):
    z = struct.pack("<I", prev) + MAGIC + bytes(8) + build_cave(prev)
    assert ZONE + len(z) <= ZONE_END
    return z


def reloc_set(d):
    import pefile
    pe = pefile.PE(data=d, fast_load=True)
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_BASERELOC"]])
    return {e.rva + BASE for b in getattr(pe, "DIRECTORY_ENTRY_BASERELOC", []) for e in b.entries if e.type}


def write_inplace(path, data):
    with open(path, "r+b") as f:
        f.seek(0); f.write(data); f.truncate()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dll", default=DEFAULT_DLL)
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true"); ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read())
    f = lambda va: va - CODE_V2F
    sb = bytes(d[f(SITE):f(SITE) + 5])
    if sb[0] != 0xE8: print("ABORT: land site %#x is not a call (%s)" % (SITE, sb.hex())); return 1
    cur = SITE + 5 + struct.unpack_from("<i", sb, 1)[0]
    zl = bytes(d[f(ZONE):f(ZONE_END)])
    stored = zl[4:8] == MAGIC
    if not stored and any(zl): print("ABORT: zone %#x..%#x not free" % (ZONE, ZONE_END)); return 1
    prev = struct.unpack_from("<I", zl, 0)[0] if stored else cur
    zone = build_zone(prev)
    site_state = "ours" if cur == CAVE else "chain(%#x)" % cur
    zstate = "zero" if not stored else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else "older build"
    rl = reloc_set(bytes(d))
    bad = sorted(hex(r) for r in rl if ZONE <= r < ZONE_END or SITE <= r < SITE + 5)
    print("land site %s | prev %#x | zone %s (%d B, cave @%#x) | relocs %s" % (site_state, prev, zstate, len(zone), CAVE, bad or "none"))
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        for i in md.disasm(zone[0x10:], CAVE): print("   %08X %-20s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad: print("ABORT: relocs"); return 1
    if a.revert:
        if not stored: print("nothing to revert"); return 0
        if cur != CAVE: print("ABORT: the land site no longer points at our cave (%#x) - revert that patch first" % cur); return 1
        out = bytearray(d)
        out[f(SITE) + 1:f(SITE) + 5] = struct.pack("<i", prev - (SITE + 5))
        out[f(ZONE):f(ZONE_END)] = bytes(ZONE_END - ZONE)
        write_inplace(a.dll, bytes(out)); print("reverted (land -> %#x)" % prev); return 0
    if stored and cur != CAVE: print("ABORT: zone is ours but the land site points elsewhere (%#x)" % cur); return 1
    if stored and zstate == "ours": print("already applied"); return 0
    out = bytearray(d)
    out[f(ZONE):f(ZONE_END)] = bytes(ZONE_END - ZONE); out[f(ZONE):f(ZONE) + len(zone)] = zone
    out[f(SITE) + 1:f(SITE) + 5] = struct.pack("<i", CAVE - (SITE + 5))
    print("%d bytes change" % sum(1 for x, y in zip(d, out) if x != y))
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(a.dll, BAK_SUFFIX)
    if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    write_inplace(a.dll, bytes(out)); assert open(a.dll, "rb").read() == bytes(out); print("Written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
