#!/usr/bin/env python3
r"""
AoWEPACK.dll: passengers of a destroyed transport are terrain-checked; Sky/Chasm deaths read "Units Fell"
(2026-11-16).

User: a unit without flying on Sky (transport destroyed, enchantment lost ...) should die; transports can also be
killed outside combat (altar, Vortex ...).  And Sky/Chasm deaths should not say "Units Crushed".

Vanilla: TArmy.ValidateTerrain (0x5578CF70 -> ValidateTerrainEx 0x5578CC9C) kills every unit whose
TAbstractUnit.ValidTerrain fails unless the army still has a valid Transporter; it runs when the hex terrain
changes or a movement enchantment is removed - never when the TRANSPORT dies, so its passengers stayed alive on
water / lava / Sky.

Every unit death goes through TUnit.Killed (VMT+0x1AC, 0x55782818: Deactivate, SetOwner(nil) -> army.RemoveChild).
  kl  TUnit.Killed entry (5 B): the unit is a transporter (VMT+0x108) owned by a TArmy -> remember the army in an
      8-slot table (DATA tail 0x558E9D00..0x558E9D20).
  up  TArmy.Update tail (`call TriggerOnUpdateEvent` @0x5578D238; Update runs when the army's update lock drops
      to 0, i.e. after TArmy.Validate / TArmy.Kill finished their unit loops): army is in the table and no combat
      is running ([map+0x120] == 0) -> drop it from the table and ValidateTerrain(army, its hex terrain/overlay).
  dc  TAoWHSMap.DestroyCombat (entry wrapped): after the combat object is gone, validate every remembered army
      (transport lost in tactical or fast combat - passengers are never touched while the battle runs).
  ad  TArmy.Destroy entry (6 B): purge the army from the table (no dangling pointers).
Units die exactly like vanilla drowning (event log, game-over check); a transfer (SetOwner to another army) never
goes through Killed, so merging / splitting stacks is unaffected.  Also applies to ships sunk at sea.
  rs  the two `call LoadResString` of the 'Units Crushed' branch (0x5578CE30 / 0x5578CE56): terrain [ebp-1] is
      Chasm 0x0B or Sky 0x0E -> literal "Units Fell" instead (still passed through TranslateRStr by the caller).
Caves 0x55856500.. (zero, reloc-free); PIC (call/pop delta) for globals / BSS / the literal.
Backup .bak_transval.  Dry run by default; --apply / --revert.
"""
import argparse, os, shutil, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DLL, V2F, BAK_SUFFIX = game_file("AoWEPACK.dll"), 0x55700C00, ".bak_transval"
ZONE, ZONE_END = 0x55856500, 0x55856700
PEND, SLOTS = 0x558E9D00, 8          # DATA tail (zero-filled past the raw data); 0x558FA5A0 was NOT free -> combat-start AV
MAPG, ARMYCLS = 0x558FA040, 0x557130AC
LOADRES, LSTRASG, ISCLASS = 0x55701210, 0x55701150, 0x557010C0
GETARMYHS, VALTER, TRIGUPD = 0x5578C8B8, 0x5578CF70, 0x5578D240
TEXT = b"Units Fell"

# name, va, original bytes, kind
SITES = [
    ("kl", 0x55782818, bytes.fromhex("538bd88bc3"), "jmp"),
    ("up", 0x5578D238, None, "call"),                       # call TriggerOnUpdateEvent
    ("dc", 0x557787F8, bytes.fromhex("558bec6a00"), "jmp"),
    ("ad", 0x5578C1B8, bytes.fromhex("53568bda8bf0"), "jmp"),
    ("rs", 0x5578CE30, None, "call"),                       # call LoadResString
    ("rs", 0x5578CE56, None, "call"),
]


def rel(op, at, to): return bytes([op]) + struct.pack("<i", to - (at + 5))


SITES = [(n, va, o if o else rel(0xE8, va, TRIGUPD if n == "up" else LOADRES), k) for n, va, o, k in SITES]

SRC = """
lit:
    .long 0xffffffff
    .long %(tlen)d
str:
    .ascii "%(text)s"
    .byte 0, 0
    .align 16

rs:
    cmp byte ptr [ebp-1], 0x0b
    je rs_sky
    cmp byte ptr [ebp-1], 0x0e
    je rs_sky
    jmp %(loadres)#x
rs_sky:
    mov eax, edx
    call rs_d
rs_d:
    pop edx
    add edx, str - rs_d
    jmp %(lstrasg)#x

kl:
    pushad
    mov esi, eax
    mov edx, [eax]
    call dword ptr [edx+0x108]
    test al, al
    jz kl_out
    mov edi, [esi+4]
    test edi, edi
    jz kl_out
    call kl_d
kl_d:
    pop ebx
    sub ebx, kl_d
    mov eax, edi
    mov edx, [ebx+%(armycls)#x]
    call %(isclass)#x
    test al, al
    jz kl_out
    lea edx, [ebx+%(pend)#x]
    mov ecx, %(slots)d
kl_s:
    cmp [edx], edi
    je kl_out
    add edx, 4
    dec ecx
    jnz kl_s
    lea edx, [ebx+%(pend)#x]
    mov ecx, %(slots)d
kl_e:
    cmp dword ptr [edx], 0
    je kl_put
    add edx, 4
    dec ecx
    jnz kl_e
    jmp kl_out
kl_put:
    mov [edx], edi
kl_out:
    popad
    push ebx
    mov ebx, eax
    mov eax, ebx
    jmp %(kl_back)#x

val:
    push esi
    mov esi, eax
    test byte ptr [esi+0x10], 1
    jz val_out
    call %(getarmyhs)#x
    test eax, eax
    jz val_out
    cmp [eax+0x1c], esi
    jne val_out
    mov eax, [eax+4]
    test eax, eax
    jz val_out
    mov cl, [eax+0x15]
    mov dl, [eax+0x14]
    mov eax, esi
    call %(valter)#x
val_out:
    pop esi
    ret

up:
    call %(trigupd)#x
    pushad
    mov edi, ebx
    call up_d
up_d:
    pop ebx
    sub ebx, up_d
    mov eax, [ebx+%(mapg)#x]
    test eax, eax
    jz up_out
    cmp dword ptr [eax+0x120], 0
    jne up_out
    lea edx, [ebx+%(pend)#x]
    mov ecx, %(slots)d
up_s:
    cmp [edx], edi
    je up_hit
    add edx, 4
    dec ecx
    jnz up_s
    jmp up_out
up_hit:
    mov dword ptr [edx], 0
    mov eax, edi
    call val
up_out:
    popad
    ret

dc:
    call dc_body
    pushad
    call dc_d
dc_d:
    pop ebx
    sub ebx, dc_d
    lea esi, [ebx+%(pend)#x]
    mov edi, %(slots)d
dc_l:
    mov eax, [esi]
    mov dword ptr [esi], 0
    test eax, eax
    jz dc_n
    call val
dc_n:
    add esi, 4
    dec edi
    jnz dc_l
    popad
    ret
dc_body:
    push ebp
    mov ebp, esp
    push 0
    jmp %(dc_back)#x

ad:
    pushad
    mov edi, eax
    call ad_d
ad_d:
    pop ebx
    sub ebx, ad_d
    lea edx, [ebx+%(pend)#x]
    mov ecx, %(slots)d
ad_l:
    cmp [edx], edi
    jne ad_n
    mov dword ptr [edx], 0
ad_n:
    add edx, 4
    dec ecx
    jnz ad_l
    popad
    push ebx
    push esi
    mov ebx, edx
    mov esi, eax
    jmp %(ad_back)#x
"""


def build():
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32, KS_OPT_SYNTAX_INTEL
    p = dict(tlen=len(TEXT), text=TEXT.decode(), loadres=LOADRES, lstrasg=LSTRASG, armycls=ARMYCLS, isclass=ISCLASS,
             pend=PEND, slots=SLOTS, kl_back=0x5578281D, getarmyhs=GETARMYHS, valter=VALTER, trigupd=TRIGUPD,
             mapg=MAPG, dc_back=0x557787FD, ad_back=0x5578C1BE)
    src = SRC % p
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    code = bytes(ks.asm(src, ZONE)[0])
    # label addresses: assemble prefixes up to each label
    where = {}
    lines = src.split("\n")
    for lab in ("rs", "kl", "up", "dc", "ad", "str"):
        k = lines.index(lab + ":")
        pre = "\n".join(lines[:k])
        # forward references inside the prefix need the full symbol set -> measure via a marker instead
        marked = "\n".join(lines[:k] + ["mark_%s:" % lab] + lines[k:])
        full = bytes(ks.asm(marked + "\n.long mark_%s\n" % lab, ZONE)[0])
        where[lab] = struct.unpack("<I", full[-4:])[0]
    assert len(code) <= ZONE_END - ZONE
    return code, where


def relocs(path):
    import pefile
    pe = pefile.PE(path, fast_load=True)
    pe.parse_data_directories([pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_BASERELOC"]])
    ib = pe.OPTIONAL_HEADER.ImageBase
    secs = [(ib + s.VirtualAddress, ib + s.VirtualAddress + ((max(s.Misc_VirtualSize, s.SizeOfRawData) + 0xFFF) & ~0xFFF), s.SizeOfRawData,
             s.Characteristics) for s in pe.sections]
    return set(ib + e.rva for blk in getattr(pe, "DIRECTORY_ENTRY_BASERELOC", []) for e in blk.entries if e.type), secs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true")
    a = ap.parse_args()
    code, where = build()
    if a.dis:
        import capstone
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(code[0x20:], ZONE + 0x20):
            print("  %08X %-20s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
        print({k: hex(v) for k, v in where.items()})
    d = bytearray(open(DLL, "rb").read())
    g = lambda va, n: bytes(d[va - V2F:va - V2F + n])
    new = {}
    for n, va, o, k in SITES:
        new[va] = rel(0xE9 if k == "jmp" else 0xE8, va, where[n]) + b"\x90" * (len(o) - 5)
    st = ["vanilla" if g(va, len(o)) == o else "ours" if g(va, len(o)) == new[va] else "OTHER" for n, va, o, k in SITES]
    zone = g(ZONE, ZONE_END - ZONE)
    zst = "zero" if not any(zone) else "ours" if zone[:len(code)] == code and not any(zone[len(code):]) else "OTHER"
    print("sites:", ", ".join("%s@%#x=%s" % (s[0], s[1], t) for s, t in zip(SITES, st)), "| zone %s (%d B)" % (zst, len(code)))
    state = "vanilla" if set(st) == {"vanilla"} and zst == "zero" else "ours" if set(st) == {"ours"} and zst == "ours" else "OTHER"
    if state == "OTHER": print("ABORT (mixed / foreign state)"); return 1
    rl, secs = relocs(DLL)
    bad = [hex(r) for r in rl if ZONE - 3 <= r < ZONE_END or any(va - 3 <= r < va + len(o) for n, va, o, k in SITES)]
    if bad: print("ABORT: relocs in range", bad); return 1
    sec = [s for s in secs if s[0] <= PEND and PEND + 4 * SLOTS <= s[1]]
    if not sec or not sec[0][3] & 0x80000000: print("ABORT: PEND table is not in a writable section"); return 1
    if PEND - sec[0][0] < sec[0][2] and any(g(PEND, 4 * SLOTS)): print("ABORT: PEND table bytes not zero"); return 1
    if state == ("vanilla" if a.revert else "ours"):
        print("already %s" % ("reverted" if a.revert else "applied")); return 0
    if not (a.apply or a.revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(DLL, BAK_SUFFIX)
    if not a.revert and not os.path.exists(bak): shutil.copy2(DLL, bak); print("backup ->", bak)
    ws = [(ZONE, bytes(ZONE_END - ZONE) if a.revert else code)]
    ws += [(va, o if a.revert else new[va]) for n, va, o, k in SITES]
    with open(DLL, "r+b") as f:                      # in-place (house rule)
        for va, b in ws:
            d[va - V2F:va - V2F + len(b)] = b; f.seek(va - V2F); f.write(b)
    assert open(DLL, "rb").read() == bytes(d)
    print("reverted" if a.revert else "Written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
