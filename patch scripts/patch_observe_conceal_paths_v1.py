#!/usr/bin/env python3
r"""
Observe mode ('O'): no camera centring on concealed armies from ANY observe path (2026-10-23).  AoWEPACK.dll only.

User: "add the same check to the other observe paths too" (after patch_observe_conceal_v1 fixed the move path).

Every observe path ends in TAoWHSMap.ValidateObservation 0x55775D5C (eax = map, dl = acting player, cl = x,
stack: y [ebp+0x10], z [ebp+0xC], radius [ebp+8]; ret 0xC).  Callers: TMoveArmyTE.SetupNextMove, THealingTE,
TDispelMagicAbilityTE, TSpell.PlayDefaultCastEffects, TWarpPartyTE, TTownGate, TDisjunctionTE, TResurrect/Animate/
CallHero, TCrusade, the global enchantments (Enchanted Roads, Masteries, Hatred, Harmony, Power Leak, Flood, Spell
Ward) and 4 unnamed sites - none of them test concealment.  It walks the hexes within radius for one visible to
the seated player (bl = found) and then centres via map VMT+0xC8.

Hook 0x55775E38 (84 DB 74 1C 0F BE 45 0C = test bl,bl / je 0x55775E58 / movsx eax,[ebp+0xC]) -> cave: when about
to centre, look at the REQUESTED hex (x, y, z): for every child of TMapContainer.GetField with ClassID (VMT+0x24)
0x20217 (TArmyHS, as in TMoveArmyTE.GetNoneMovingArmyHS), army = [hs+0x1C]; if that army is fully concealed from
the seated player - fresh, side-effect-free test identical to patch_observe_conceal_v1 (on map, mask [army+0x2A],
not own, !([map+0x3C]&2), UnitCount == ConcealedUnitsCount, GetConcealedForPlayer(seat)) - the centring is skipped
(result false).  Otherwise the original bytes run.  Camera only; local view only (MP-irrelevant).
Cave AoWEPACK 0x5583C100..0x5583C300 ('OBC2'); AoWHSMap var via the PIC delta trick ([var] IS the map - one deref; the first build double-dereferenced it -> AVs); calls rel32.  Independent of
patch_observe_conceal_v1 (different site/zone).  Backup .bak_observepaths.  Dry-run default; --apply/--revert/--dis.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
try:
    from bakpath import bak_path, game_file
    DEFAULT = game_file("AoWEPACK.dll")
except Exception:
    bak_path = lambda p, s: p + s
    DEFAULT = r"C:\Users\<user>\Desktop\Age of Wonders X - Claude\AoWEPACK.dll"

DELTA = 0x55700C00
SITE, SITE_LEN = 0x55775E38, 8
ORIG = bytes.fromhex("84DB741C0FBE450C")
RESUME, SKIP = 0x55775E40, 0x55775E58
ZONE, ZONE_END = 0x5583C100, 0x5583C300
MAGIC = b"OBC2"
SUF = ".bak_observepaths"
MAPVAR = 0x558FA040
GETFIELD = 0x557020FC                    # thunk HSEngine.TMapContainer.GetField (eax=cont, edx=x, ecx=y, push z)
CONCEALED_COUNT = 0x5578CB84
ARMYHS_CLASSID = 0x20217


def build():
    code_va = ZONE + 0x10
    src = f"""
    test bl, bl
    jz skip
    pushad
    call get
get:
    pop ebx
    sub ebx, get
    mov eax, dword ptr [ebx + {MAPVAR:#x}]
    test eax, eax
    jz done
    cmp byte ptr [eax + 0xa5], 0xff
    je done
    test byte ptr [eax + 0x3c], 2
    jnz done
    movsx ecx, byte ptr [ebp + 0xc]
    push ecx
    movsx ecx, byte ptr [ebp + 0x10]
    movsx edx, byte ptr [ebp - 5]
    mov eax, dword ptr [eax + 0x10]
    call {GETFIELD:#x}
    test eax, eax
    jz done
    mov esi, eax
    mov edx, dword ptr [eax]
    call dword ptr [edx + 0x54]
    mov edi, eax
next:
    dec edi
    js done
    mov eax, dword ptr [esi + 8]
    mov eax, dword ptr [eax + edi*4]
    test eax, eax
    jz next
    push eax
    mov edx, dword ptr [eax]
    call dword ptr [edx + 0x24]
    pop ecx
    cmp eax, {ARMYHS_CLASSID:#x}
    jne next
    mov eax, dword ptr [ecx + 0x1c]
    call conceal
    test al, al
    jz next
    mov dword ptr [esp + 0x10], 0
done:
    popad
    test bl, bl
    jz skip
    movsx eax, byte ptr [ebp + 0xc]
    jmp {RESUME:#x}
skip:
    jmp {SKIP:#x}

conceal:
    push esi
    push edi
    mov edi, eax
    test edi, edi
    jz c_no
    test byte ptr [edi + 0x10], 1
    jz c_no
    cmp byte ptr [edi + 0x2a], 0
    je c_no
    mov eax, dword ptr [ebx + {MAPVAR:#x}]
    mov dl, byte ptr [eax + 0xa5]
    cmp dl, byte ptr [edi + 0x12]
    je c_no
    mov eax, edi
    mov edx, dword ptr [eax]
    call dword ptr [edx + 0x54]
    mov esi, eax
    mov eax, edi
    call {CONCEALED_COUNT:#x}
    cmp eax, esi
    jne c_no
    mov eax, dword ptr [ebx + {MAPVAR:#x}]
    mov dl, byte ptr [eax + 0xa5]
    mov eax, edi
    mov ecx, dword ptr [eax]
    call dword ptr [ecx + 0xbc]
    jmp c_out
c_no:
    xor eax, eax
c_out:
    pop edi
    pop esi
    ret
"""
    enc, _ = Ks(KS_ARCH_X86, KS_MODE_32).asm(src, code_va)
    code = bytes(enc)
    z = bytearray(ZONE_END - ZONE)
    z[0:4] = MAGIC
    assert 0x10 + len(code) <= len(z), hex(len(code))
    z[0x10:0x10 + len(code)] = code
    hook = b"\xE9" + struct.pack("<i", code_va - (SITE + 5)) + b"\x90" * (SITE_LEN - 5)
    return bytes(z), hook, len(code)


def relocs(path):
    import pefile
    pe = pefile.PE(path, fast_load=True)
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_BASERELOC"]])
    base = pe.OPTIONAL_HEADER.ImageBase
    return {en.rva + base for b in getattr(pe, "DIRECTORY_ENTRY_BASERELOC", []) for en in b.entries if en.type}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dll", default=DEFAULT)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    d = bytearray(open(a.dll, "rb").read())
    zone, hook, clen = build()
    so, zo = SITE - DELTA, ZONE - DELTA
    site, cur = bytes(d[so:so + SITE_LEN]), bytes(d[zo:zo + len(zone)])
    applied = site == hook and cur == zone
    vanilla = site == ORIG and not any(cur)
    rl = sorted(hex(r) for r in relocs(a.dll) if SITE - 3 <= r < SITE + SITE_LEN or ZONE - 3 <= r < ZONE_END)
    print("%s\n  site %s | zone %s | code %d B | relocs in site/zone: %s"
          % (a.dll, site.hex(), "OBC2" if applied else ("zero" if not any(cur) else "OTHER"), clen, rl or "none"))
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        for i in md.disasm(zone[0x10:0x10 + clen], ZONE + 0x10):
            print("   %08x  %s %s" % (i.address, i.mnemonic, i.op_str))
    if applied:
        if not a.revert:
            print("already applied"); return 0
        d[so:so + SITE_LEN] = ORIG
        d[zo:zo + len(zone)] = bytes(len(zone))
        msg = "reverted"
    else:
        if a.revert:
            print("not applied - nothing to revert"); return 0
        if not vanilla or rl:
            print("ABORT: site/zone not in the expected state"); return 1
        if not a.apply:
            print("Dry run OK - rerun with --apply"); return 0
        bp = bak_path(a.dll, SUF)
        if not os.path.exists(bp):
            shutil.copy2(a.dll, bp); print("backup -> " + bp)
        d[zo:zo + len(zone)] = zone
        d[so:so + SITE_LEN] = hook
        msg = "applied: no observe path centres on an army concealed from the seated player"
    with open(a.dll, "r+b") as f:
        f.write(d)
    chk = open(a.dll, "rb").read()
    assert chk[so:so + SITE_LEN] == (ORIG if a.revert else hook)
    print("Written and verified - " + msg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
