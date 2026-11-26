r"""
AoWx.exe: Events-tab header portrait follows the Leader's Soul (2026-10-22, 1.37.422).

User spec: while the leader is dead and the player owns a Leader's Soul unit (ability 0xCE, see
patch_leader_soul_v3), the Events-tab header (TPInfoW) shows that SOUL UNIT's portrait - whichever unit holds
0xCE (possessed unit, possessed hero or Incarnate) - and follows it to every new body; once the leader is
resurrected/animated (v3 strips 0xCE from the soul) it is the leader's own face again.  Visual + local only.

Vanilla (static RE):
  TPInfoW (VMT 0x422EC8, instance var 0x45B134; [0x45A4FC] = &var): fields PInfoWin +0x44 (window, +0x75 visible),
  FaceFr +0x74, Player +0x88 (name label = TPlayer.GetName, unchanged by this patch), Race +0x8C, Turn +0x5C.
  FaceFrDraw 0x423770: player = TPlayerList.GetPlayers([map+0x140], [map+0xA5]) (thunk 0x402464);
  face = TPlayer.GetFace(player) (thunk 0x402424 = [player+0xD4] leader VMT+0xF4) at 0x4237F6 (nil test) and
  0x42381F (draw: face VMT+0x88 (edx=^rect, ecx=^drawinfo)).  Unit VMT+0xF4 is GetFace for every unit class
  (THero.GetFace 0x557887DC = hero face lib, TUnit.GetFace 0x5578283C = the unit-window portrait from the unit's
  gfx resource) and both return an image object with the same VMT+0x88 draw, so the header can draw either.
  The header is only repainted by window invalidation; nothing invalidates it when the soul moves.

Patch (zone .xtut 0x648E00-0x649000, free tail after the relocated TREALMWIN DFM which ends at 0x648D56):
  sf  = soul face: scan [player+0x28] armies (count VMT+0x54, items [[l+8]+4]) and their units for ability bit 0xCE
        (inline TAbstractUnit has-ability: id < [u+0xC] and bt [[u+8]], id); found -> unit VMT+0xF4; nil or none ->
        the original TPlayer.GetFace.  Dead test = "a 0xCE unit exists": leader soul v3 grants 0xCE only when the
        leader possesses (the leader is Killed then) and strips it when the leader returns, so it is exactly the
        dead-leader window, and it needs no AoWEPACK addresses (AoWEPACK may rebase; the exe never does).
  F1/F2  0x4237F6 / 0x42381F  call 0x402424 -> call sf.
  tk  per-frame: TBWorldUpdate 0x457A6C (`mov eax,[ebx+0x9C]`, 6 B, after the editor-indicator hook at 0x457A4C)
        -> if the Events window is visible and sf(local player) differs from the last seen face, clear FaceFr's
        drawn flag [+0xA4] (redraw next pass); re-executes the mov, jmp 0x457A72.
Dry-run default; --apply / --revert / --dis; --exe <copy> for scratch tests.  Backup backup\AoWx.exe.bak_soulface.
"""
import argparse, os, shutil, struct, sys

import pefile
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

EXE = game_file("AoWx.exe")
BAK_SUFFIX = ".bak_soulface"
ZONE, ZONE_END = 0x648E00, 0x649000
MAGIC = b"SFP1"
LAST = ZONE + 4                       # last face seen by the per-frame check
CODE = ZONE + 0x10
AB = 0xCE
G_PINFO, G_MAP = 0x45B134, 0x45DF7C
T_GETPLAYERS, T_GETFACE = 0x402464, 0x402424
F1, F2, TK, TK_RET = 0x4237F6, 0x42381F, 0x457A6C, 0x457A72
ORIG_F = b"\xe8" + struct.pack("<i", T_GETFACE - (F1 + 5))
ORIG_F2 = b"\xe8" + struct.pack("<i", T_GETFACE - (F2 + 5))
ORIG_TK = bytes.fromhex("8b839c000000")
DFM_END = 0x648D56

ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm(src, va):
    return bytes(ks.asm(src, va)[0])


def build():
    out = bytearray(MAGIC + b"\0" * 12); where = {}

    def place(name, src):
        while len(out) % 16: out.append(0)
        va = ZONE + len(out); where[name] = va
        out.extend(asm(src % S, va))

    S = {"ab": AB, "gp": T_GETPLAYERS, "gf": T_GETFACE, "pinfo": G_PINFO, "map": G_MAP, "last": LAST,
         "tkret": TK_RET}
    place("sf", """
        push ebx
        push esi
        push edi
        push ebp
        mov ebx, eax
        test ebx, ebx
        je nil
        mov ebp, [ebx + 0x28]
        test ebp, ebp
        je orig
        mov eax, ebp
        mov edx, [eax]
        call dword ptr [edx + 0x54]
        mov esi, eax
    al_loop:
        dec esi
        js orig
        mov eax, [ebp + 8]
        mov eax, [eax + 4]
        mov edi, [eax + esi*4]
        test edi, edi
        je al_loop
        mov eax, edi
        mov edx, [eax]
        call dword ptr [edx + 0x54]
        push eax
    ul:
        dec dword ptr [esp]
        js ul_done
        mov ecx, [esp]
        mov eax, [edi + 8]
        mov eax, [eax + 4]
        mov eax, [eax + ecx*4]
        test eax, eax
        je ul
        cmp dword ptr [eax + 0xC], %(ab)d
        jbe ul
        mov edx, [eax + 8]
        mov ecx, %(ab)d
        bt dword ptr [edx], ecx
        jae ul
        add esp, 4
        mov edx, [eax]
        call dword ptr [edx + 0xF4]
        test eax, eax
        jne done
        jmp orig
    ul_done:
        add esp, 4
        jmp al_loop
    orig:
        mov eax, ebx
        call %(gf)#x
        jmp done
    nil:
        xor eax, eax
    done:
        pop ebp
        pop edi
        pop esi
        pop ebx
        ret
    """)
    S["sf"] = where["sf"]
    place("tk", """
        pushfd
        pushad
        mov esi, [%(pinfo)#x]
        test esi, esi
        je out
        mov eax, [esi + 0x44]
        test eax, eax
        je out
        cmp byte ptr [eax + 0x75], 0
        je out
        mov eax, [%(map)#x]
        mov eax, [eax]
        test eax, eax
        je out
        movsx edx, byte ptr [eax + 0xA5]
        test edx, edx
        js out
        mov eax, [eax + 0x140]
        test eax, eax
        je out
        call %(gp)#x
        test eax, eax
        je out
        call %(sf)#x
        cmp eax, [%(last)#x]
        je out
        mov [%(last)#x], eax
        mov eax, [esi + 0x74]
        test eax, eax
        je out
        mov byte ptr [eax + 0xA4], 0
    out:
        popad
        popfd
        mov eax, [ebx + 0x9C]
        jmp %(tkret)#x
    """)
    assert ZONE + len(out) <= ZONE_END, hex(ZONE + len(out))
    return bytes(out), where


def call_to(src, dst):
    return b"\xe8" + struct.pack("<i", dst - (src + 5))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true"); ap.add_argument("--exe", default=EXE)
    a = ap.parse_args()
    d = bytearray(open(a.exe, "rb").read())
    pe = pefile.PE(data=bytes(d))
    base = pe.OPTIONAL_HEADER.ImageBase
    off = lambda va: pe.get_offset_from_rva(va - base)
    zone, where = build()
    sites = {
        "F1": (F1, ORIG_F, call_to(F1, where["sf"])),
        "F2": (F2, ORIG_F2, call_to(F2, where["sf"])),
        "TK": (TK, ORIG_TK, b"\xe9" + struct.pack("<i", where["tk"] - (TK + 5)) + b"\x90"),
    }
    # the zone must be inside .xtut raw data and past the TREALMWIN DFM resource
    sec = [s for s in pe.sections if s.Name.rstrip(b"\0") == b".xtut"]
    if not sec: print("ABORT: no .xtut section"); return 1
    s = sec[0]
    if not (s.VirtualAddress + base <= ZONE and ZONE_END <= s.VirtualAddress + base + s.SizeOfRawData):
        print("ABORT: zone %#x-%#x not inside .xtut raw data" % (ZONE, ZONE_END)); return 1
    relocs = set()
    if hasattr(pe, "DIRECTORY_ENTRY_BASERELOC"):
        for blk in pe.DIRECTORY_ENTRY_BASERELOC:
            for e in blk.entries:
                if e.type: relocs.add(e.rva + base)
    for name, (va, orig, new) in sites.items():
        if any(r in relocs for r in range(va - 3, va + len(orig))):
            print("ABORT: relocation under site %s %#x" % (name, va)); return 1
    if any(r in relocs for r in range(ZONE - 3, ZONE_END)):
        print("ABORT: relocation inside the zone"); return 1
    # nothing else may point into the zone
    zo = off(ZONE)
    cur_zone = bytes(d[zo:zo + (ZONE_END - ZONE)])
    state = {}
    for name, (va, orig, new) in sites.items():
        o = off(va); cur = bytes(d[o:o + len(orig)])
        state[name] = "patched" if cur == new else "orig" if cur == orig else "OTHER:" + cur.hex()
    zstate = "ours" if cur_zone[:4] == MAGIC else "free" if not any(cur_zone) else "OCCUPIED"
    print("zone %#x-%#x: %s (%d B used) | sites %s" % (ZONE, ZONE_END, zstate, len(zone),
          " ".join("%s=%s" % kv for kv in state.items())))
    print("caves: " + ", ".join("%s=%#x" % kv for kv in where.items()))
    if a.dis:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
        md = Cs(CS_ARCH_X86, CS_MODE_32)
        for i in md.disasm(zone[0x10:], CODE):
            print("  %#x  %-24s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if any(v.startswith("OTHER") for v in state.values()) or zstate == "OCCUPIED":
        print("ABORT: unexpected bytes (another patch owns a site or the zone)"); return 1
    applied = zstate == "ours" and all(v == "patched" for v in state.values())
    vanilla = zstate == "free" and all(v == "orig" for v in state.values())
    if a.revert:
        if vanilla: print("already reverted"); return 0
        if not (a.apply or a.revert): return 0
        with open(a.exe, "r+b") as f:
            for name, (va, orig, new) in sites.items():
                f.seek(off(va)); f.write(orig)
            f.seek(zo); f.write(b"\0" * (ZONE_END - ZONE))
        print("reverted"); return 0
    if applied:
        if cur_zone[:len(zone)] != zone: print("WARNING: zone differs from this build (re-run --revert then --apply)")
        print("already applied"); return 0
    if not vanilla:
        print("ABORT: partial state - run --revert first"); return 1
    if not a.apply:
        print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(a.exe, BAK_SUFFIX)
    if not os.path.exists(bak):
        shutil.copy2(a.exe, bak); print("backup ->", bak)
    with open(a.exe, "r+b") as f:
        f.seek(zo); f.write(zone)
        for name, (va, orig, new) in sites.items():
            f.seek(off(va)); f.write(new)
    chk = open(a.exe, "rb").read()
    ok = chk[zo:zo + len(zone)] == zone and all(chk[off(va):off(va) + len(new)] == new
                                                 for va, orig, new in sites.values())
    print("Written and verified" if ok else "WRITE VERIFY FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
