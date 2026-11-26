#!/usr/bin/env python3
r"""
AoWTCPCK.dll: Soul Siphon (spell 340) visuals - a LINGERING effect at the target and a STREAM of soul motes flowing
from the target to the caster (2026-10-15, v1; user: "make the target hit gfx linger longer, and have particles
floating towards the caster for its duration").  Visual only; the heal is patch_soulsiphon_v1.py (AoWEPACK).

Why not just lengthen slot 0: a class-7 strike effect LANDS (damage CA, and so the heal) only when its slot-0 sequence
reaches its LAST frame (kind-7 NewFrame 0x42D2EF) - a longer slot 0 would delay the damage.  So slot 0 stays the
24-tick hit and two extra effects are spawned when the strike is created:

SPAWN - hook 0x40D8AF in NextStrike's shared strike-effect tail (0x40D8A3: every class-7-style branch converges here
  right after the view is centred; [ebp-4] = TE, [ebp-0x10] = the new strike effect, [ebp-0x34]/[ebp-0x38] = target
  pixel; 6 bytes `mov [ebp-0x50],eax / mov eax,[ebp-0x34]`, no relocs, no branch lands inside).  `call spawn; nop`;
  the cave replays both instructions.  For spell 340 ([te+0x18]):
    * DRIVER: one kind-0x26 effect on the target hex (the Ashes/Hellfire recipe: HXtoHP 0x4022BC, AddEffect
      0x41C6EC(map [0x46C064], dl 0x26), TXYZ [0x46EB24] Create 0x401040, XYZList.Add 0x402DE4 / GetXYZ 0x402DF4;
      [fx+0x14]=0x34, [fx+0x18]=340, [fx+0x2C]=nil, [fx+0x24]=0).  With no marker the chained kind-0x26 slot picks
      (Ashes -> Hellfire caves, NewFrame 0x42A5E9 / Show 0x430059) fall through to the vanilla slot 1, so the driver
      draws spell 340 gfx SLOT 1 for its sequence's full length (kind-4 lifetime = entries x (f18+1) ticks).
    * MOTES: if the caster's combat sprite exists ([te+0x10] -> [cu+0x60], hex via VMT+0x74/+0x78), N_MOTES kind-0x1F
      effects on MakeLinePath 0x402E04 (eax x0, edx y0, ecx x1; push y1, steps, &[fx+0x1C]) from the target to the
      caster.  NO RNG: mote k starts at a fixed spread over the target hex and takes 14 + 4k path steps, so the
      12 motes leave together and arrive one after another over ~2 s = a stream lasting the driver's lifetime.
      No caster sprite (a leader casting from outside the battle) -> no motes.
SLOT - a kind-0x1F sparkle draws its spell's gfx slot 0 (the hit!), so the sprite-slot picker SUB_0042E4C4 is chained
  like Ashes does: a kind-0x1F effect of spell 340 asking for slot 0 gets MOTE_SLOT 2.  The site is normally already a
  `jmp` into the Ashes cave (-> Hellfire); ours goes IN FRONT and tail-jumps to whatever the site jumped to (decoded at
  apply, decoded back out of our cave on --revert); on a vanilla site the cave replays the 7-byte prologue instead.

Zone 0x43F040..0x43F400 (verified zero, no relocs; 0x43F000..0x43F035 = patch_slow_v1).  PIC via call/pop delta.
⚠ Chain order: patch_tc_ashes_v1.py decodes the slot site's target when it (re)applies - revert THIS script first
  before re-applying or reverting Ashes, then re-apply this one.
Backup <game>\backup\AoWTCPCK.dll.bak_soulsiphonfx.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DEFAULT_DLL = game_file("AoWTCPCK.dll")
BAK_SUFFIX = ".bak_soulsiphonfx"
BASE, CODE_V2F = 0x400000, 0x400C00
ZONE, ZONE_END = 0x43F040, 0x43F400
SPELL_ID = 340
SPAWN_SITE, SPAWN_ORIG = 0x40D8AF, bytes.fromhex("8945b08b45cc")
SLOT_SITE, SLOT_ORIG, SLOT_RESUME = 0x42E4C4, bytes.fromhex("558bec518945fc"), 0x42E4CB
MAP_GLOBAL, TXYZ_IAT = 0x46C064, 0x46EB24
HXTOHP, ADDEFFECT, TOBJCREATE, XYZADD, GETXYZ, MAKELINE = 0x4022BC, 0x41C6EC, 0x401040, 0x402DE4, 0x402DF4, 0x402E04
DRV_DX, DRV_DY = 16, 16                # the hex centre (the slot-1 sequence carries its own xs/ys anchor)
N_MOTES, MOTE_SLOT = 12, 2
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, va):
    return bytes(ks.asm(src, va)[0])


def build_spawn(va):
    """called from SPAWN_SITE (eax = the new TXYZ, ebp = NextStrike's frame).  NO `;` comments inside the source."""
    def src(l0):
        return """
        mov dword ptr [ebp-0x50], eax
        push eax
        mov eax, dword ptr [ebp-4]
        cmp dword ptr [eax+0x18], %(id)d
        jne out
        pushad
        call l0
    l0:
        pop ebx
        sub ebx, %(l0)#x
        mov esi, dword ptr [ebp-4]
        sub esp, 16
        lea ecx, [esp+4]
        push esp
        movzx eax, word ptr [esi+0x20]
        movzx edx, word ptr [esi+0x22]
        call %(hx)#x
        mov eax, dword ptr [ebx+%(map)#x]
        mov dl, 0x26
        call %(add)#x
        mov edi, eax
        mov dword ptr [edi+0x14], 0x34
        mov dword ptr [edi+0x18], %(id)d
        mov dword ptr [edi+0x2c], 0
        mov dword ptr [edi+0x24], 0
        mov dl, 1
        mov eax, dword ptr [ebx+%(txyz)#x]
        call %(create)#x
        mov edx, eax
        mov eax, dword ptr [edi+0x1c]
        call %(xyzadd)#x
        mov eax, dword ptr [edi+0x1c]
        xor edx, edx
        call %(getxyz)#x
        mov edx, dword ptr [esp+4]
        add edx, %(ddx)d
        mov dword ptr [eax+4], edx
        mov edx, dword ptr [esp]
        add edx, %(ddy)d
        mov dword ptr [eax+8], edx
        mov eax, dword ptr [esi+0x10]
        test eax, eax
        jz done
        mov eax, dword ptr [eax+0x60]
        test eax, eax
        jz done
        mov edi, eax
        mov edx, dword ptr [edi]
        call dword ptr [edx+0x78]
        movsx eax, al
        push eax
        mov eax, edi
        mov edx, dword ptr [edi]
        call dword ptr [edx+0x74]
        movsx eax, al
        pop edx
        lea ecx, [esp+12]
        lea edi, [esp+8]
        push edi
        call %(hx)#x
        xor edi, edi
    mloop:
        mov eax, dword ptr [ebx+%(map)#x]
        mov dl, 0x1f
        call %(add)#x
        mov esi, eax
        mov dword ptr [esi+0x14], 0x34
        mov dword ptr [esi+0x18], %(id)d
        mov dword ptr [esi+0x2c], 0
        mov eax, edi
        imul eax, eax, 3
        and eax, 7
        add eax, dword ptr [esp+8]
        add eax, 6
        push eax
        mov eax, edi
        shl eax, 2
        add eax, 14
        push eax
        lea eax, [esi+0x1c]
        push eax
        mov eax, edi
        imul eax, eax, 5
        and eax, 7
        add eax, dword ptr [esp+24]
        add eax, 8
        mov ecx, eax
        mov eax, edi
        imul eax, eax, 11
        and eax, 15
        add eax, dword ptr [esp+12]
        add eax, 4
        mov edx, eax
        mov eax, edi
        imul eax, eax, 7
        and eax, 15
        add eax, dword ptr [esp+16]
        add eax, 6
        call %(line)#x
        inc edi
        cmp edi, %(n)d
        jb mloop
    done:
        add esp, 16
        popad
    out:
        pop eax
        mov eax, dword ptr [ebp-0x34]
        ret
        """ % {"id": SPELL_ID, "l0": l0, "hx": HXTOHP, "map": MAP_GLOBAL, "add": ADDEFFECT, "txyz": TXYZ_IAT,
               "create": TOBJCREATE, "xyzadd": XYZADD, "getxyz": GETXYZ, "ddx": DRV_DX, "ddy": DRV_DY,
               "line": MAKELINE, "n": N_MOTES}
    b = asm(src(0x12345678), va); k = b.find(b"\xe8\x00\x00\x00\x00\x5b"); assert k > 0          # dummy imm32 so both passes encode alike
    out = asm(src(va + k + 5), va); assert len(out) == len(b)
    return out


def build_slot(va, chain):
    tail = "jmp %#x" % chain if chain is not None else ".byte " + ", ".join("%#x" % x for x in SLOT_ORIG) + "\n        jmp %#x" % SLOT_RESUME
    return asm("""
        push ecx
        mov ecx, dword ptr [esp+8]
        mov ecx, dword ptr [ecx-4]
        cmp byte ptr [ecx+0x34], 0x1f
        jne s_pass
        cmp dword ptr [ecx+0x18], %(id)d
        jne s_pass
        test eax, eax
        jne s_pass
        mov eax, %(slot)d
    s_pass:
        pop ecx
        %(tail)s
    """ % {"id": SPELL_ID, "slot": MOTE_SLOT, "tail": tail}, va)


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
    spawn_va = ZONE
    spawn = build_spawn(spawn_va)
    slot_va = (ZONE + len(spawn) + 15) & ~15
    # ---- the slot site: vanilla prologue, a jmp into someone's cave, or already ours
    sb = bytes(d[f(SLOT_SITE):f(SLOT_SITE) + 7])
    ours_slot = False
    if sb == SLOT_ORIG:
        slot_chain = None
    else:
        assert sb[0] == 0xE9 and sb[5:7] == b"\x90\x90", "unexpected slot-site bytes %s" % sb.hex()
        t = SLOT_SITE + 5 + struct.unpack_from("<i", sb, 1)[0]
        if ZONE <= t < ZONE_END:                                # already ours: recover the previous target from our tail
            ours_slot = True
            tb = bytes(d[f(t):f(ZONE_END)]); k = tb.find(b"\x59\xe9")
            if k >= 0 and tb[k:k + 2] == b"\x59\xe9":
                slot_chain = t + k + 6 + struct.unpack_from("<i", tb, k + 2)[0]
            else:
                slot_chain = None
            if slot_chain == SLOT_RESUME: slot_chain = None
        else:
            slot_chain = t
    slot = build_slot(slot_va, slot_chain)
    zone = bytearray(spawn) + bytes(slot_va - ZONE - len(spawn)) + slot
    assert ZONE + len(zone) <= ZONE_END, hex(ZONE + len(zone))
    spawn_hook = b"\xe8" + struct.pack("<i", spawn_va - (SPAWN_SITE + 5)) + b"\x90"
    slot_hook = b"\xe9" + struct.pack("<i", slot_va - (SLOT_SITE + 5)) + b"\x90\x90"
    live_spawn = bytes(d[f(SPAWN_SITE):f(SPAWN_SITE) + 6])
    st_spawn = "vanilla" if live_spawn == SPAWN_ORIG else "ours" if live_spawn == spawn_hook else "OTHER"
    st_slot = "ours" if ours_slot else ("vanilla" if slot_chain is None else "chained(%#x)" % slot_chain)
    zl = bytes(d[f(ZONE):f(ZONE_END)])
    zstate = "zero" if not any(zl) else "ours" if zl[:len(zone)] == bytes(zone) and not any(zl[len(zone):]) else "DIFFERS"
    rl = reloc_set(bytes(d))
    bad = sorted(hex(r) for r in rl if ZONE <= r < ZONE_END or SPAWN_SITE <= r < SPAWN_SITE + 6 or SLOT_SITE <= r < SLOT_SITE + 7)
    print("sites {spawn: %s, slot: %s} | zone %s (%d B: spawn=%#x slot=%#x) | relocs %s" % (st_spawn, st_slot, zstate, len(zone), spawn_va, slot_va, bad or "none"))
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        for i in md.disasm(bytes(zone), ZONE): print("   %08X %-20s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad or st_spawn == "OTHER": print("ABORT"); return 1
    if a.revert:
        if st_spawn == "vanilla" and not ours_slot: print("nothing to revert"); return 0
        d[f(SPAWN_SITE):f(SPAWN_SITE) + 6] = SPAWN_ORIG
        if ours_slot:
            d[f(SLOT_SITE):f(SLOT_SITE) + 7] = SLOT_ORIG if slot_chain is None else b"\xe9" + struct.pack("<i", slot_chain - (SLOT_SITE + 5)) + b"\x90\x90"
        d[f(ZONE):f(ZONE_END)] = bytes(ZONE_END - ZONE)
        write_inplace(a.dll, bytes(d)); print("reverted"); return 0
    if st_spawn == "ours" and ours_slot and zstate == "ours": print("already applied"); return 0
    if st_spawn == "vanilla" and not ours_slot and zstate != "zero": print("ABORT: zone not zero"); return 1
    out = bytearray(d)
    out[f(ZONE):f(ZONE_END)] = bytes(ZONE_END - ZONE); out[f(ZONE):f(ZONE) + len(zone)] = zone
    out[f(SPAWN_SITE):f(SPAWN_SITE) + 6] = spawn_hook
    out[f(SLOT_SITE):f(SLOT_SITE) + 7] = slot_hook
    print("%d bytes change" % sum(1 for x, y in zip(d, out) if x != y))
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(a.dll, BAK_SUFFIX)
    if not os.path.exists(bak): shutil.copy2(a.dll, bak); print("backup ->", bak)
    write_inplace(a.dll, bytes(out)); assert open(a.dll, "rb").read() == bytes(out); print("Written and verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
