#!/usr/bin/env python3
r"""
Observe mode ('O') must not reveal concealed armies (2026-10-23).  AoWEPACK.dll only.

User: "when a player is using the Observe function (toggle 'O'), the screen centers on any unit movement by other
factions within vision.  however, this also reveals hidden units (concealed etc.)."

Vanilla chain (all unmodified): TMoveArmyTE.SetupNextMove 0x557483D8 -> ObserveMove 0x557480D8 -> if true
TAoWHSMap.ValidateObservation 0x55775D5C (observe on [map+0x180], not the seated player, hex visible -> centre).
ObserveMove's only stealth test is MoveVisible 0x55748198: hex Visible && !TArmy.FullyConcealed ([army+0x10] & 0x10).
That bit is a CACHED per-seat flag, written only by TArmy.UpdateConcealment 0x5578C98C (TArmy.Update, MsgProc,
TArmyHS msg 0x110D) - a moving army's cache can lag behind its real concealment, and the camera follows it.

Fix: ObserveMove's epilogue 0x55748190 (8B C3 5F 5E 5B C3 = mov eax,ebx / pop edi / pop esi / pop ebx / ret; the
target of all its exits) -> cave.  When the result is true, recompute concealment FRESH for the seated player with
UpdateConcealment's own test, side-effect free (no flag writes - vanilla AI code reads those flags, OOS risk):
    army = [[te+0x28]+0x1C]; on map ([army+0x10]&1); has concealed units ([army+0x2A] != 0);
    seat = [map+0xA5] != 0xFF and != owner [army+0x12]; !([map+0x3C] & 2);
    UnitCount (VMT+0x54) == ConcealedUnitsCount 0x5578CB84;  GetConcealedForPlayer (VMT+0xBC, dl = seat)
  -> all true: ObserveMove returns false (camera does not follow).  Partly concealed armies are drawn, so they
  still get followed.  Camera only - movement, drawing and sounds are untouched.  MP-irrelevant (local view only).
Cave AoWEPACK 0x5583C000..0x5583C100 ('OBC1'); in-image absolutes (AoWHSMap var 0x558FA040) via the PIC delta
trick ([var] IS the map - one deref; 10/23 the first build double-dereferenced it -> AVs); calls are rel32 (same image).  Backup .bak_observeconceal.  Dry-run default; --apply / --revert / --dis.
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

DELTA = 0x55700C00                       # VA = file + DELTA
SITE = 0x55748190
ORIG = bytes.fromhex("8BC35F5E5BC3")
ZONE, ZONE_END = 0x5583C000, 0x5583C100
MAGIC = b"OBC1"
SUF = ".bak_observeconceal"
MAPVAR = 0x558FA040
CONCEALED_COUNT = 0x5578CB84


def build():
    code_va = ZONE + 0x10
    src = f"""
    test bl, bl
    jz out
    pushad
    call get
get:
    pop ebp
    sub ebp, get
    mov edi, dword ptr [esi + 0x28]
    test edi, edi
    jz done
    mov edi, dword ptr [edi + 0x1c]
    test edi, edi
    jz done
    test byte ptr [edi + 0x10], 1
    jz done
    cmp byte ptr [edi + 0x2a], 0
    je done
    mov eax, dword ptr [ebp + {MAPVAR:#x}]
    test eax, eax
    jz done
    mov dl, byte ptr [eax + 0xa5]
    cmp dl, 0xff
    je done
    cmp dl, byte ptr [edi + 0x12]
    je done
    test byte ptr [eax + 0x3c], 2
    jnz done
    mov eax, edi
    mov edx, dword ptr [eax]
    call dword ptr [edx + 0x54]
    mov esi, eax
    mov eax, edi
    call {CONCEALED_COUNT:#x}
    cmp eax, esi
    jne done
    mov eax, dword ptr [ebp + {MAPVAR:#x}]
    mov dl, byte ptr [eax + 0xa5]
    mov eax, edi
    mov ecx, dword ptr [eax]
    call dword ptr [ecx + 0xbc]
    test al, al
    jz done
    mov dword ptr [esp + 0x10], 0
done:
    popad
out:
    mov eax, ebx
    pop edi
    pop esi
    pop ebx
    ret
"""
    enc, _ = Ks(KS_ARCH_X86, KS_MODE_32).asm(src, code_va)
    code = bytes(enc)
    z = bytearray(ZONE_END - ZONE)
    z[0:4] = MAGIC
    assert 0x10 + len(code) <= len(z), hex(len(code))
    z[0x10:0x10 + len(code)] = code
    hook = b"\xE9" + struct.pack("<i", code_va - (SITE + 5)) + b"\x90"
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
    site, cur = bytes(d[so:so + 6]), bytes(d[zo:zo + len(zone)])
    applied = site == hook and cur == zone
    vanilla = site == ORIG and not any(cur)
    rl = sorted(hex(r) for r in relocs(a.dll) if SITE - 3 <= r < SITE + 6 or ZONE - 3 <= r < ZONE_END)
    print("%s\n  site %s | zone %s | code %d B | relocs in site/zone: %s"
          % (a.dll, site.hex(), "OBC1" if applied else ("zero" if not any(cur) else "OTHER"), clen, rl or "none"))
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        for i in md.disasm(zone[0x10:0x10 + clen], ZONE + 0x10):
            print("   %08x  %s %s" % (i.address, i.mnemonic, i.op_str))
    if applied:
        if not a.revert:
            print("already applied"); return 0
        d[so:so + 6] = ORIG
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
        d[so:so + 6] = hook
        msg = "applied: Observe no longer follows armies concealed from the seated player"
    with open(a.dll, "r+b") as f:
        f.write(d)
    chk = open(a.dll, "rb").read()
    assert chk[so:so + 6] == (ORIG if a.revert else hook)
    print("Written and verified - " + msg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
