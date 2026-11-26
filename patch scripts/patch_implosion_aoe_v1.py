"""
IMPLOSION (389) - small AoE (2026-10-14).  AoWTCPCK.dll.

User: "change it to small AOE instead of single hex damage".  Implosion's one invisible hail strike lands on the target
hex (patch_tc_repent_harvest_v1.py `pat` forces HN 0 for 389) and the hail impact sender (ranged-TE impact switch
0x40C8E2..) delivers map-field message 0x31006 to that ONE field: [ebp-0x64] = msg (0x31006, +8 caster = [ebp-0x5C],
+0xC spell id = [ebp-0x58] via patch_tc_hail_msg_spell_v1.py, +0x18 = [ebp-0x4C]), landing hex x = [ebp-0x28],
y = [ebp-0x2C]; `GetMapLevel(0) / GetField(level, x, y)` then `lea edx,[ebp-0x64] / call SendMapFieldMsg` @0x40C915.

Hook SEND @0x40C915 (8 B `lea edx,[ebp-0x64] / call 0x401DDC` -> `call cave` + 3 nop; no relocs): the cave replays the
send (eax = the centre field), then for spell 389 sends the same message to the 6 neighbours HN 1..6 of the landing
hex (HSEngine.CenterHNtoHX thunk 0x4022AC: eax x, edx y, ecx HN, pushes &outX then &outY; level bounds
[level+0xC]/[level+0x10]; TMapContainer.GetMapLevel 0x401E64 / TMapLevel.GetField 0x401E54 / TMapField.SendMapFieldMsg
0x401DDC - all import-table checked), restoring msg+0x18 before each send.  Every unit, wall and structure in the
7 hexes takes Implosion's own hit (its unit handler builds the CA from GetSpell(389)).  Display only on the centre
(the driver's explosion); no RNG drawn here.
Zone 0x43E600..0x43E700 (zero, reloc-free).  PIC via call/pop delta for the map-list global.  Dry-run default;
--apply / --revert / --dis.  Backup <game>\\backup\\AoWTCPCK.dll.bak_implaoe.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DLL = game_file("AoWTCPCK.dll")
BASE, CODE_V2F = 0x400000, 0x400C00
SITE, ORIG = 0x40C915, bytes.fromhex("8d559ce8bf54ffff")
SENDMSG, GETMAPLEVEL, GETFIELD, CENTERHNTOHX = 0x401DDC, 0x401E64, 0x401E54, 0x4022AC
MAP_LIST_GLOBAL = 0x469420
ZONE, ZONE_END = 0x43E600, 0x43E700
SPELL_ID, RING = 389, 6

ks = Ks(KS_ARCH_X86, KS_MODE_32)


def build(va):
    src = """
        push dword ptr [ebp-0x4c]
        lea edx, [ebp-0x64]
        call %(send)#x
        cmp dword ptr [ebp-0x58], %(id)d
        jne out
        pushal
        .byte 0xe8, 0, 0, 0, 0
        pop ebx
        sub ebx, 0x7fffffff
        mov eax, [ebx+%(maplist)#x]
        mov eax, [eax]
        mov eax, [eax+0x10]
        xor edx, edx
        call %(getlevel)#x
        mov esi, eax
        test esi, esi
        jz done
        sub esp, 8
        mov edi, 1
    lp:
        lea eax, [esp]
        push eax
        lea eax, [esp+8]
        push eax
        mov ecx, edi
        mov eax, [ebp-0x28]
        mov edx, [ebp-0x2c]
        call %(cnhx)#x
        mov edx, [esp]
        mov ecx, [esp+4]
        test edx, edx
        js nx
        test ecx, ecx
        js nx
        cmp edx, [esi+0xc]
        jge nx
        cmp ecx, [esi+0x10]
        jge nx
        mov eax, esi
        call %(getfield)#x
        test eax, eax
        jz nx
        mov edx, [esp+0x28]
        mov [ebp-0x4c], edx
        lea edx, [ebp-0x64]
        call %(send)#x
    nx:
        inc edi
        cmp edi, %(ring)d
        jbe lp
        add esp, 8
    done:
        popal
    out:
        add esp, 4
        ret
    """ % {"send": SENDMSG, "id": SPELL_ID, "maplist": MAP_LIST_GLOBAL, "getlevel": GETMAPLEVEL, "cnhx": CENTERHNTOHX,
           "getfield": GETFIELD, "ring": RING}
    b = bytearray(ks.asm(src, va)[0])
    anchor = bytes.fromhex("e8000000005b81ebffffff7f"); k = b.find(anchor); assert k >= 0
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
    hook = b"\xe8" + struct.pack("<i", ZONE - (SITE + 5)) + b"\x90" * 3
    live = bytes(d[SITE - CODE_V2F:SITE - CODE_V2F + 8]); zl = bytes(d[ZONE - CODE_V2F:ZONE_END - CODE_V2F])
    state = "vanilla" if live == ORIG else "ours" if live == hook else "OTHER"
    zstate = "zero" if not any(zl) else "ours" if zl[:len(cave)] == cave and not any(zl[len(cave):]) else "DIFFERS"
    bad = [hex(r) for r in relocs(bytes(d)) if ZONE <= r < ZONE_END or SITE <= r < SITE + 8]
    print("site %s | zone %s (%d B) | relocs %s" % (state, zstate, len(cave), bad or "none"))
    if a.dis:
        import capstone
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(cave, ZONE): print("   %08X  %-18s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad or state == "OTHER": print("ABORT"); return 1
    if a.revert:
        d[SITE - CODE_V2F:SITE - CODE_V2F + 8] = ORIG; d[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
        open(DLL, "r+b").write(bytes(d)); print("reverted"); return 0
    if state == "ours" and zstate == "ours": print("already applied"); return 0
    if zstate == "DIFFERS" and state != "ours": print("ABORT (zone not free)"); return 1
    d[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE); d[ZONE - CODE_V2F:ZONE - CODE_V2F + len(cave)] = cave
    d[SITE - CODE_V2F:SITE - CODE_V2F + 8] = hook
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(DLL, ".bak_implaoe")
    if not os.path.exists(bak): shutil.copy2(DLL, bak); print("backup ->", bak)
    with open(DLL, "r+b") as f: f.write(bytes(d))
    assert open(DLL, "rb").read() == bytes(d); print("Written and verified"); return 0


if __name__ == "__main__":
    sys.exit(main())
