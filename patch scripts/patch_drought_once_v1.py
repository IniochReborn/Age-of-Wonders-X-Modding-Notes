"""
DROUGHT (391) - only one active Drought per player (2026-10-14).  AoWEPACK.dll.

TWaterMastery's cast validation (0x557F07B0..: esi = spell, [ebp-1] = player index, edi = &message) calls the base check
0x5577DAE8 @0x557F07CC, then refuses with '%s is already active' when the player's magic flags [x+0x44] have bit 0x08 -
a bit Water Mastery's OWN Activate sets.  Drought (a TWaterMastery clone) skips that Activate (patch_drought_v1.py AC
hook), so it could be cast again and again; reusing bit 0x08 would also block Water Mastery and give its effect.

Hook: `call 0x5577DAE8` @0x557F07CC -> `call cave` (rel32, no reloc).  cave: replay the base call; result 0 or a spell
other than 391 -> return normally (vanilla continues).  For 391: scan the player's global enchantments ([[map
0x558FA040]+0x188]+0x14 list, Count = VMT+0x54, Get 0x5577E13C) for an ACTIVE ([e+0x10] bit 1) Drought ([e+0x14] == 391,
the patch_drought_v1.py marker) cast by this player ([e+0x19] == [ebp-1]); drop the return address and continue at
0x557F07F6 (the 'already active' message path, which zeroes ebx) when found, else at 0x557F0841 (the accept exit,
result in bl) - either way skipping the Water Mastery bit-0x08 test.
Zone 0x5585FD00..0x5585FE00 (zero, no relocs).  PIC via call/pop delta.  Dry-run default; --apply / --revert.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DLL = game_file("AoWEPACK.dll")
BASE, CODE_V2F = 0x55700000, 0x55700C00
SITE, ORIG = 0x557F07CC, bytes.fromhex("e817d3f8ff")
BASE_CHECK, MSG_PATH, ACCEPT_EXIT = 0x5577DAE8, 0x557F07F6, 0x557F0841
MAP_GLOBAL, LIST_GET = 0x558FA040, 0x5577E13C
ZONE, ZONE_END = 0x5585FD00, 0x5585FE00
SPELL_ID = 391

ks = Ks(KS_ARCH_X86, KS_MODE_32)


def build(va):
    src = """
        call %(base)#x
        test al, al
        jz back
        cmp dword ptr [esi+0x10], %(id)d
        je ours
    back:
        ret
    ours:
        add esp, 4
        mov ebx, eax
        push esi
        push edi
        .byte 0xe8, 0, 0, 0, 0
        pop edi
        sub edi, 0x7fffffff
        mov eax, [edi+%(map)#x]
        mov eax, [eax+0x188]
        mov esi, [eax+0x14]
        mov eax, esi
        mov edx, [eax]
        call dword ptr [edx+0x54]
        mov ecx, eax
    scan:
        dec ecx
        js free
        push ecx
        mov eax, esi
        mov edx, ecx
        call %(get)#x
        pop ecx
        test eax, eax
        jz scan
        cmp dword ptr [eax+0x14], %(id)d
        jne scan
        test byte ptr [eax+0x10], 1
        jz scan
        movsx edx, byte ptr [eax+0x19]
        movsx eax, byte ptr [ebp-1]
        cmp edx, eax
        jne scan
        pop edi
        pop esi
        jmp %(msg)#x
    free:
        pop edi
        pop esi
        jmp %(accept)#x
    """ % {"base": BASE_CHECK, "id": SPELL_ID, "map": MAP_GLOBAL, "get": LIST_GET, "msg": MSG_PATH, "accept": ACCEPT_EXIT}
    b = bytearray(ks.asm(src, va)[0])
    anchor = bytes.fromhex("e8000000005f81efffffff7f"); k = b.find(anchor); assert k >= 0
    struct.pack_into("<I", b, k + 8, va + k + 5)
    return bytes(b)


def relocs(d):
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


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true"); ap.add_argument("--dis", action="store_true"); a = ap.parse_args()
    d = bytearray(open(DLL, "rb").read())
    cave = build(ZONE); assert ZONE + len(cave) <= ZONE_END
    hook = b"\xe8" + struct.pack("<i", ZONE - (SITE + 5))
    live = bytes(d[SITE - CODE_V2F:SITE - CODE_V2F + 5]); zl = bytes(d[ZONE - CODE_V2F:ZONE_END - CODE_V2F])
    state = "vanilla" if live == ORIG else "ours" if live == hook else "OTHER"
    zstate = "zero" if not any(zl) else "ours" if zl[:len(cave)] == cave and not any(zl[len(cave):]) else "DIFFERS"
    bad = [hex(r) for r in relocs(bytes(d)) if ZONE <= r < ZONE_END or SITE <= r < SITE + 5]
    print("site %s | zone %s (%d B) | relocs %s" % (state, zstate, len(cave), bad or "none"))
    if a.dis:
        import capstone
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(cave, ZONE): print("   %08X  %-18s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad or state == "OTHER": print("ABORT"); return 1
    if a.revert:
        d[SITE - CODE_V2F:SITE - CODE_V2F + 5] = ORIG; d[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
        open(DLL, "r+b").write(bytes(d)); print("reverted"); return 0
    if state == "ours" and zstate == "ours": print("already applied"); return 0
    if zstate == "DIFFERS" and state != "ours": print("ABORT (zone not free)"); return 1
    d[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE); d[ZONE - CODE_V2F:ZONE - CODE_V2F + len(cave)] = cave
    d[SITE - CODE_V2F:SITE - CODE_V2F + 5] = hook
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(DLL, ".bak_droughtonce")
    if not os.path.exists(bak): shutil.copy2(DLL, bak); print("backup ->", bak)
    with open(DLL, "r+b") as f: f.write(bytes(d))
    assert open(DLL, "rb").read() == bytes(d); print("Written and verified"); return 0


if __name__ == "__main__":
    sys.exit(main())
