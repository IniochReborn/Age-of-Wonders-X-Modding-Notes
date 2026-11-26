"""
HURL BOULDER (365) - a brief magical glow at the CASTER before the boulder is thrown (2026-10-15).  AoWTCPCK.dll.

User: "hurl boulder sfx needs more magical noise and maybe a brief magical GFX before the boulder is thrown".

365 is a kind-2 fxComet spell (patch_hurlboulder_v1.py).  TCAbRangedTE.Execute:
  phase 0 (0x40B4E6..): kind 2 takes the default count branch (0x40B5C0, spell VMT+0x7C -> 1 shot), then
    `call NextStrike` @0x40B6F1 (return 0x40B6F6) launches the comet at once.  NextStrike's first spell strike also
    starts the caster's cast animation (SetAction 3 @0x40F3F2) -> the caster-HS action site @0x421D65 plays the
    spell's sound cue 0 (TSFXLibrary.Play 0x4022F4) = cue 0 starts WITH the launch.
  phase 1 (0x40CB9D..): for spells the countdown [te+0x30] is reloaded to Random(3)+4 only when it is <= 0, then
    decremented; at 0 -> `call NextStrike` @0x40CBE7 (return 0x40CBEC).  When the strike list [map+0x11C] is EMPTY
    and strikes remain, the TE may finish (0x40CB23..0x40CB65) -> a delayed strike needs a live effect in the list.
Both NextStrike sites already go through a chain of id-gated gate caves (sandswirl 0x43E200 -> ... -> Hellfire's
-> NextStrike).  This script puts one more gate IN FRONT of that chain (decoded at apply, written back on --revert):
  gate (eax = te; every other id / any call after the launch ([te+0x34] != 0) jumps straight into the chain):
    * called from phase 0 (return address == 0x40B6F6 + delta): spawn ONE kind-0x26 effect at the caster's hex
      (caster CU [te+0x10] -> sprite [cu+0x60] -> X/Y virtuals +0x74/+0x78 -> HXtoHP, +16/+16; [fx+0x14]=0x34,
      [fx+0x18]=365, [fx+0x2C]=NIL) = High Prayer's per-unit aura effect: it draws gfx SLOT 1 of the spell for
      frames*(f18+1) ticks (fxComet only ever reads slot 0, so slot 1 is free); play sound cue 0 now (if
      [map+0x129]); WAIT := WAIT_TICKS; [te+0x30] := 1; return WITHOUT launching.  No caster sprite -> no glow,
      launch at once (an empty strike list during a wait could end the TE without a throw).
    * called from phase 1 while WAIT > 0: WAIT -= 1; [te+0x30] := 1 (-> no Random reload; the countdown hits 0 again
      next tick and calls us again); return.  When WAIT reaches 0: fall into the chain = the real launch.
  The glow effect lives GLOW_FRAMES*(f18+1) = 24 ticks > WAIT_TICKS = 18, so the strike list never runs empty
  during the wait.  WAIT is one dword of DATA page slack (0x46BFE0, past DATA's raw size; page-mapped, zeroed).
No RNG is consumed (the wait keeps [te+0x30] > 0 at the reload test), the delay is a fixed tick count -> the same on
every peer, like the Hellfire / Ashes strike gates.

⚠ Needs two one-line edits in OTHER scripts (checked by this script's dry run; --apply refuses without them):
  1. patch_hurlboulder_v1.py WALL cave: also require kind 2 (`cmp byte ptr [eax+0x34], 2 / jne rp`), else the
     finished glow effect (id 365, no unit, kind 0x26) would send the hail impact msg at the CASTER's hex.
  2. patch_tc_hellfire_portal_v1.py castsnd cave: add 365 to the exclusion list (as 389), else cue 0 plays twice
     (at the glow from here, and again at the launch from the caster's cast animation).
PIC (call/pop delta; the DLL rebases).  Zone 0x43B180..0x43B400 (zero, reloc-free; 0x43B100..0x43B180 =
patch_hurlboulder_v1.py).  Dry-run default; --apply / --revert / --dis.  Backup <game>\\backup\\AoWTCPCK.dll.bak_hbglow.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DLL = game_file("AoWTCPCK.dll")
BASE, CODE_V2F = 0x400000, 0x400C00
SPELL_ID = 365
ZONE, ZONE_END = 0x43B180, 0x43B400
WAIT_VA = 0x46BFE0                    # DATA page slack dword (raw DATA ends 0x46B800; BSS starts 0x46C000)
WAIT_TICKS = 30                       # v2 10/15: ~1.0 s at ~30 ticks/s - the boulder shakes and rises (DualDF 1820-1837), launch at frame 15 (was 18)
GLOW_FRAMES, GLOW_F18 = 18, 1         # slot-1 sequence the pipeline must provide: 18 frames x 2 ticks = 36 ticks > WAIT_TICKS (v1: 12)
GLOW_DX, GLOW_DY = 16, 16             # effect point = hex pixel + 16/16 (the hex centre, as Repent/Harvest); the art's xs/ys place it
GATE_SITES = [(0x40B6F1, 0x40B6F6), (0x40CBE7, 0x40CBEC)]   # (call site, return address): phase 0 / phase 1
NEXTSTRIKE = 0x40D290
KIND_DRIVER = 0x26
HXTOHP, ADDEFFECT, TXYZ_IAT, TOBJCREATE, XYZADD, GETXYZ = 0x4022BC, 0x41C6EC, 0x46EB24, 0x401040, 0x402DE4, 0x402DF4
MAP_GLOBAL, SPELLREG_GLOBAL, GETSPELL, SFXPLAY = 0x46C064, 0x46E8D0, 0x4029B4, 0x4022F4
# prerequisites in other scripts' caves
HB_WALL_CAVE = 0x43B120               # patch_hurlboulder_v1.py WALL cave
HB_KIND_GUARD = bytes.fromhex("80783402")          # cmp byte ptr [eax+0x34], 2
CASTSND_CAVE = (0x43C900, 0x43C980)   # patch_tc_hellfire_portal_v1.py castsnd cave
CASTSND_EXCL = bytes.fromhex("817838") + struct.pack("<I", SPELL_ID)   # cmp dword ptr [eax+0x38], 365

ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm_delta(src, va):
    if "$D" not in src: return bytes(ks.asm(src, va)[0])
    s1 = src.replace("call $D", ".byte 0xe8, 0, 0, 0, 0").replace("sub ebx, $D", "sub ebx, 0x7fffffff")
    b = bytearray(ks.asm(s1, va)[0]); anchor = b"\xe8\x00\x00\x00\x00\x5b\x81\xeb\xff\xff\xff\x7f"
    n, k = 0, b.find(anchor)
    while k >= 0:
        struct.pack_into("<I", b, k + 8, va + k + 5); n += 1; k = b.find(anchor, k + len(anchor))
    assert n == src.count("call $D") == src.count("sub ebx, $D")
    return bytes(b)


def build(chain):
    """Gate cave.  Layout contract: offset 0 = `cmp dword ptr [eax+0x18], imm32` (7 B), offset 7 = `jne rel32`
    (0F 85, 6 B) -> the chain target is decodable from the applied bytes."""
    src = """
        cmp dword ptr [eax+0x18], %(id)d
        jne %(chain)#x
        cmp dword ptr [eax+0x34], 0
        jne %(chain)#x
        push ebx
        call $D
        pop ebx
        sub ebx, $D
        lea ecx, [ebx+%(ret0)#x]
        cmp ecx, [esp+4]
        je spawn
        dec dword ptr [ebx+%(wait)#x]
        jle launch
        mov dword ptr [eax+0x30], 1
        pop ebx
        ret
    launch:
        mov dword ptr [ebx+%(wait)#x], 0
        pop ebx
        jmp %(chain)#x
    spawn:
        mov dword ptr [ebx+%(wait)#x], %(ticks)d
        mov dword ptr [eax+0x30], 1
        push esi
        push edi
        mov edi, eax
        mov eax, [edi+0x10]
        test eax, eax
        jz nofx
        mov esi, [eax+0x60]
        test esi, esi
        jz nofx
        mov eax, esi
        mov edx, [esi]
        call dword ptr [edx+0x78]
        movsx eax, al
        push eax
        mov eax, esi
        mov edx, [esi]
        call dword ptr [edx+0x74]
        movsx eax, al
        pop edx
        sub esp, 8
        lea ecx, [esp+4]
        push esp
        call %(hx)#x
        mov eax, [ebx+%(map)#x]
        mov dl, %(kind)d
        call %(add)#x
        mov esi, eax
        mov dl, 1
        mov eax, [ebx+%(txyz)#x]
        call %(create)#x
        mov edx, eax
        mov eax, [esi+0x1c]
        call %(xyzadd)#x
        mov eax, [esi+0x1c]
        xor edx, edx
        call %(getxyz)#x
        mov edx, [esp+4]
        add edx, %(dx)d
        mov [eax+4], edx
        mov edx, [esp]
        add edx, %(dy)d
        mov [eax+8], edx
        mov dword ptr [esi+0x14], 0x34
        mov dword ptr [esi+0x18], %(id)d
        mov dword ptr [esi+0x2c], 0
        add esp, 8
        mov eax, [ebx+%(map)#x]
        cmp byte ptr [eax+0x129], 0
        je out
        mov eax, [ebx+%(reg)#x]
        mov eax, [eax]
        mov eax, [eax+0x84]
        mov edx, %(id)d
        call %(getspell)#x
        mov eax, [eax+0x28]
        xor edx, edx
        call %(play)#x
    out:
        pop edi
        pop esi
        pop ebx
        ret
    nofx:
        mov eax, edi
        pop edi
        pop esi
        mov dword ptr [ebx+%(wait)#x], 0
        pop ebx
        jmp %(chain)#x
    """ % {"id": SPELL_ID, "chain": chain, "ret0": GATE_SITES[0][1], "wait": WAIT_VA, "ticks": WAIT_TICKS,
           "hx": HXTOHP, "map": MAP_GLOBAL, "kind": KIND_DRIVER, "add": ADDEFFECT, "txyz": TXYZ_IAT, "create": TOBJCREATE,
           "xyzadd": XYZADD, "getxyz": GETXYZ, "dx": GLOW_DX, "dy": GLOW_DY, "reg": SPELLREG_GLOBAL, "getspell": GETSPELL,
           "play": SFXPLAY}
    code = asm_delta(src, ZONE)
    assert code[0:3] == b"\x81\x78\x18" and code[7:9] == b"\x0f\x85", code[:16].hex()
    return code


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


def call_target(d, va):
    b = d[va - CODE_V2F:va - CODE_V2F + 5]
    return va + 5 + struct.unpack("<i", bytes(b[1:]))[0] if b[0] == 0xE8 else None


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true"); ap.add_argument("--dis", action="store_true"); a = ap.parse_args()
    d = bytearray(open(DLL, "rb").read())
    targets = [call_target(d, st) for st, _ in GATE_SITES]
    assert None not in targets and len(set(targets)) == 1, "gate sites disagree: %s" % targets
    ours = targets[0] == ZONE
    if ours:
        z = d[ZONE - CODE_V2F:]
        chain = ZONE + 13 + struct.unpack_from("<i", bytes(z[9:13]))[0]
    else:
        chain = targets[0]
    zone = build(chain); assert ZONE + len(zone) <= ZONE_END
    zl = bytes(d[ZONE - CODE_V2F:ZONE_END - CODE_V2F])
    zstate = "zero" if not any(zl) else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else "DIFFERS"
    rl = relocs(bytes(d))
    bad = [hex(r) for r in rl if ZONE - 3 <= r < ZONE_END or any(st - 3 <= r < st + 5 for st, _ in GATE_SITES)]
    hb = bytes(d[HB_WALL_CAVE - CODE_V2F:HB_WALL_CAVE - CODE_V2F + 0x40])
    cs = bytes(d[CASTSND_CAVE[0] - CODE_V2F:CASTSND_CAVE[1] - CODE_V2F])
    pre = {"hurlboulder kind-2 guard": HB_KIND_GUARD in hb, "castsnd excludes 365": CASTSND_EXCL in cs}
    print("gate sites %s -> chain %#x | zone %s (%d B @%#x) | wait dword %#x = %d ticks, glow %d frames x %d ticks | relocs %s | prerequisites %s"
          % ("ours" if ours else "pass-through", chain, zstate, len(zone), ZONE, WAIT_VA, WAIT_TICKS, GLOW_FRAMES, GLOW_F18 + 1, bad or "none", pre))
    if a.dis:
        import capstone
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(zone, ZONE): print("   %08X  %-18s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad: print("ABORT (relocs)"); return 1
    if a.revert:
        if not ours: print("not applied"); return 0
        for st, nx in GATE_SITES: d[st - CODE_V2F:st - CODE_V2F + 5] = b"\xe8" + struct.pack("<i", chain - nx)
        d[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
        with open(DLL, "r+b") as f: f.write(bytes(d))
        print("reverted (gate sites -> %#x)" % chain); return 0
    if ours and zstate == "ours": print("already applied"); return 0
    if zstate == "DIFFERS" and not ours: print("ABORT (zone not free)"); return 1
    d[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE); d[ZONE - CODE_V2F:ZONE - CODE_V2F + len(zone)] = zone
    for st, nx in GATE_SITES: d[st - CODE_V2F:st - CODE_V2F + 5] = b"\xe8" + struct.pack("<i", ZONE - nx)
    if not a.apply:
        if not all(pre.values()): print("NOTE: --apply will refuse until the prerequisites are in (see the docstring)")
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    if not all(pre.values()): print("ABORT: prerequisites missing %s" % [k for k, v in pre.items() if not v]); return 1
    bak = bak_path(DLL, ".bak_hbglow")
    if not os.path.exists(bak): shutil.copy2(DLL, bak); print("backup ->", bak)
    with open(DLL, "r+b") as f: f.write(bytes(d))
    assert open(DLL, "rb").read() == bytes(d); print("Written and verified"); return 0


if __name__ == "__main__":
    sys.exit(main())
