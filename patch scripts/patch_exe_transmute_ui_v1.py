"""
TRANSMUTATION (235) - Power Distribution window shows "?" research turns (2026-10-18).  AoWx.exe only.

User: "it works correctly but the mana distribution slider screen shows research TURN durations when it should read
'?' like it does in the main mana tab."

RE (AoWx.exe):
  * main magic tab (0x42ED8C..): ResearchTurns(GetNetPowerToResearch(mc), cost) -> Transmutation's RES hook returns 0
    research for an active caster -> 999 -> 'cmp ebx,0x3e7 / jge' formats "?" (0x42EE37 vtChar '?').
  * Power Distribution window (TPowerWindow update 0x42BCB8): esi = GetNetPower(mc) (0x42BD02), edi = esi * the
    window's OWN slider [[ebx+0x9C]+0x148] / 100 (FP, 0x42BD86..0x42BDA7) - it never calls GetNetPowerToResearch, so the
    Transmutation hook can't reach it; ResearchTurns(edx = edi, ecx = [ebp-0x10] cost) @0x42BDD9 -> [ebp-8] ->
    IntToStr -> label [ebx+0x6C] (0x42BE01..0x42BE12; vanilla shows the number, also "999").

FIX (only while the viewing player's magic control belongs to a player with an ACTIVE Transmutation):
  * H1 0x42BDD7 (7 B `mov edx,edi / call ResearchTurns`) -> cave: research 0 -> ResearchTurns = 999.
  * H2 0x42BE0C (6 B `mov edx,[ebp-0x18] / mov eax,[ebx+0x6C]`) -> cave: turns >= 999 AND Transmutation -> caption "?"
    (an AnsiString literal in the zone, refcount -1).  Everything else (no Transmutation, vanilla 999) unchanged.
  * istrans: walks the global enchantment list ([[AoWEPACK 0x558FA040]+0x188]+0x14, Count = vcall +0x54, Get =
    0x5577E13C) for an ACTIVE ([e+0x10]&1) enchantment id 235 ([e+0x14]) cast by player byte [player+0xA6]
    ([e+0x19]) - the same test as patch_transmutation_v1.py's gxa; AoWEPACK addresses rebased through the AoWx.exe IAT
    slot 0x45DD48 (= runtime GetNetPowerToResearch, preferred 0x5577CF80).  Read-only, UI only (MP-safe).
Zone .xbfs 0x60EE40..0x60EF80 (zero, unclaimed, reloc-free; 0x60ED40.. = secondwind, 0x60EF80.. = static-shield
listhide).  Dry-run default; --apply / --revert (exact) / --dis; --exe <path>.  Backup AoWx.exe.bak_transmui.
Independent of patch_transmutation_v1.py (AoWEPACK) - apply/revert in any order.

v2 2026-10-18 (user: "display 'Transmute to Gold' instead of the spell currently being researched and repeat the
research slider number below it rather than a question mark; only while Transmutation is active"):
  * window labels: [ebx+0x70] = researched spell NAME (GetSpell([mc+0x34])+8 -> TAOWLabel.SetGText 0x403254),
    [ebx+0x6C] = turns caption (FmtTurnsStr 0x40249C); [ebx+0x88] = the research-side slider number = IntToStr(edi)
    (edi = research share, 0x42BDA7), [ebx+0x84] = the mana side (esi).
  * v2 drops v1's H1/H2 (restored to vanilla) and hooks ONE site: H0 0x42BDAB (6 B `cmp [ebp-0xc],0 / je 0x42BE19`,
    the "is a spell being researched" branch).  Active Transmutation for the window's player (same istrans test) ->
    name label := "Transmute to Gold" (AnsiString literal in the zone, refcount -1; English only, no MLD row),
    turns caption := IntToStr(edi) (exactly what the research slider number shows) -> jmp 0x42BE49 (the common tail
    that writes the totals / slider numbers).  Not active -> the replayed cmp/je (vanilla, incl. the "no spell" path).
    Runs on every window update, so it follows the slider live and reverts the moment the enchantment is gone.
  * upgrade: a live v1 (zone magic TRU1, H1/H2 hooked) is rewritten in place (H1/H2 back to vanilla); --revert from
    v1 or v2 restores all three sites to vanilla + zeroes the zone.  Backup AoWx.exe.bak_transmui2.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

ZONE, ZONE_END = 0x60EE40, 0x60EF80
MAGIC, MAGIC_V1, LIT, CAVES = b"TRU2", b"TRU1", 0x20, 0x40
IAT_RES, RES_PREF = 0x45DD48, 0x5577CF80          # AoWx.exe IAT slot of TPlayerMagicControl.GetNetPowerToResearch
EP_MAP, EP_LISTGET, SPELL_ID, PIDX = 0x558FA040, 0x5577E13C, 235, 0xA6
T_RTURNS, T_PLGET, G_GEN = 0x40263C, 0x402464, 0x45DF7C
T_SETTEXT, T_INTTOSTR = 0x403254, 0x4013AC         # TAOWLabel.SetGText / SysUtils.IntToStr thunks
H0 = ("H0", 0x42BDAB, bytes.fromhex("837df4007468"), 0x42BDB1)   # v2: the only hook
V1_SITES = [("H1", 0x42BDD7, bytes.fromhex("8bd7e85e68fdff")), ("H2", 0x42BE0C, bytes.fromhex("8b55e88b436c"))]
J_NOSPELL, J_TAIL = 0x42BE19, 0x42BE49
TTG = b"Transmute to Gold"
ks = Ks(KS_ARCH_X86, KS_MODE_32)


def build():
    out = bytearray(CAVES); out[0:4] = MAGIC
    out[8:8 + 6] = H0[2]                                         # H0's original bytes (documentation)
    struct.pack_into("<iI", out, LIT - 8, -1, len(TTG)); out[LIT:LIT + len(TTG)] = TTG   # AnsiString literal
    assert LIT + len(TTG) + 1 <= CAVES
    where = {}
    C = dict(iat=IAT_RES, pref=RES_PREF, map=EP_MAP, lget=EP_LISTGET, id=SPELL_ID, pidx=PIDX, plget=T_PLGET, gen=G_GEN,
             lit=ZONE + LIT, settext=T_SETTEXT, i2s=T_INTTOSTR, nospell=J_NOSPELL, tail=J_TAIL, back=H0[3])

    def place(name, src):
        while len(out) % 16: out.append(0)
        va = ZONE + len(out); where[name] = va
        out.extend(bytes(ks.asm(src % dict(C, **where), va)[0]))

    # istrans(eax = TPlayerMagicControl) -> eax = 1 if its player has an ACTIVE Transmutation; keeps all else
    place("ist", """
        push ebx
        push ecx
        push edx
        push esi
        push edi
        push ebp
        test eax, eax
        jz i_no
        mov eax, [eax+0x10]
        test eax, eax
        jz i_no
        movsx edi, byte ptr [eax+%(pidx)#x]
        cmp edi, -1
        je i_no
        mov ebx, dword ptr [%(iat)#x]
        sub ebx, %(pref)#x
        mov eax, [ebx+%(map)#x]
        test eax, eax
        jz i_no
        mov eax, [eax+0x188]
        test eax, eax
        jz i_no
        mov esi, [eax+0x14]
        test esi, esi
        jz i_no
        mov eax, esi
        mov edx, [eax]
        call dword ptr [edx+0x54]
        mov ebp, eax
    i_lp:
        dec ebp
        js i_no
        lea ecx, [ebx+%(lget)#x]
        mov eax, esi
        mov edx, ebp
        call ecx
        test eax, eax
        jz i_lp
        cmp dword ptr [eax+0x14], %(id)d
        jne i_lp
        test byte ptr [eax+0x10], 1
        jz i_lp
        movsx edx, byte ptr [eax+0x19]
        cmp edx, edi
        jne i_lp
        mov eax, 1
        jmp i_out
    i_no:
        xor eax, eax
    i_out:
        pop ebp
        pop edi
        pop esi
        pop edx
        pop ecx
        pop ebx
        ret
    """)
    # H0 (0x42BDAB): ebx = the window, edi = its research share, esi = mana share, [ebp-0xc] = researched spell id.
    # Transmutation active for the window's player -> name := "Transmute to Gold", turns caption := IntToStr(edi)
    # (the research slider's own number) -> the common tail; else the replayed vanilla branch.
    place("c0", """
        pushal
        mov eax, dword ptr [%(gen)#x]
        mov eax, [eax]
        movsx edx, byte ptr [eax+0xa5]
        mov eax, [eax+0x140]
        call %(plget)#x
        mov eax, [eax+0x54]
        call %(ist)#x
        test eax, eax
        popal
        jnz c0_tr
        cmp dword ptr [ebp-0xc], 0
        je %(nospell)#x
        jmp %(back)#x
    c0_tr:
        mov edx, %(lit)#x
        mov eax, [ebx+0x70]
        call %(settext)#x
        lea edx, [ebp-0x18]
        mov eax, edi
        call %(i2s)#x
        mov edx, [ebp-0x18]
        mov eax, [ebx+0x6c]
        call %(settext)#x
        jmp %(tail)#x
    """)
    return bytes(out), where


def reloc_set(d, pe):
    rva, size = pe.OPTIONAL_HEADER.DATA_DIRECTORY[5].VirtualAddress, pe.OPTIONAL_HEADER.DATA_DIRECTORY[5].Size
    p = pe.get_offset_from_rva(rva); end, out = p + size, set()
    while p < end:
        page, sz = struct.unpack_from("<II", d, p)
        if sz < 8: break
        for q in range(p + 8, p + sz, 2):
            e = struct.unpack_from("<H", d, q)[0]
            if e >> 12 == 3: out.add(0x400000 + page + (e & 0xFFF))
        p += sz
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=None)
    for fl in ("--apply", "--revert", "--dis"): ap.add_argument(fl, action="store_true")
    a = ap.parse_args()
    import pefile
    exe = a.exe or game_file("AoWx.exe")
    d = open(exe, "rb").read()
    pe = pefile.PE(data=d, fast_load=True); pe.parse_data_directories(directories=[1])
    assert pe.OPTIONAL_HEADER.DllCharacteristics & 0x40 == 0, "AoWx.exe is DYNAMIC_BASE"
    iat_ok = any(imp.address == IAT_RES and (imp.name or b"").startswith(b"AoWE.TPlayerMagicControl.GetNetPowerToResearch")
                 for e in pe.DIRECTORY_ENTRY_IMPORT for imp in e.imports)
    assert iat_ok, "IAT slot %#x is not GetNetPowerToResearch" % IAT_RES
    f = lambda va: pe.get_offset_from_rva(va - 0x400000)
    g = lambda va, n: bytes(d[f(va):f(va) + n])
    code, where = build()
    assert ZONE + len(code) <= ZONE_END
    hook0 = b"\xe9" + struct.pack("<i", where["c0"] - (H0[1] + 5)) + b"\x90"
    zl = g(ZONE, ZONE_END - ZONE)

    def jmp_into_zone(va, n):
        b = g(va, n)
        return b[0] == 0xE9 and ZONE <= va + 5 + struct.unpack_from("<i", b, 1)[0] < ZONE_END
    s0 = ("vanilla" if g(H0[1], 6) == H0[2] else "ours" if g(H0[1], 6) == hook0 else
          "ours(old)" if jmp_into_zone(H0[1], 6) else "OTHER(%s)" % g(H0[1], 6).hex())
    s1 = {nm: "vanilla" if g(va, len(v)) == v else "v1" if jmp_into_zone(va, len(v)) else "OTHER(%s)" % g(va, len(v)).hex()
          for nm, va, v in V1_SITES}
    if not any(zl): zst = "zero"
    elif zl[:len(code)] == code and not any(zl[len(code):]): zst = "ours (v2)"
    elif zl[:4] == MAGIC_V1: zst = "v1"
    elif zl[:4] == MAGIC: zst = "v2 (older build)"
    else: zst = "DIFFERS"
    rl = reloc_set(d, pe)
    allsites = [H0[:3]] + V1_SITES
    bad = [hex(r) for r in rl if ZONE - 3 <= r < ZONE_END or any(va - 3 <= r < va + len(v) for _n, va, v in allsites)]
    print("H0 %s | v1 sites %s | zone %s (%d B: %s) | relocs %s" % (s0, s1, zst, len(code),
          ", ".join("%s=%#x" % kv for kv in where.items()), bad or "none"))
    if a.dis:
        import capstone
        md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
        for i in md.disasm(code[CAVES:], ZONE + CAVES): print("   %08X  %-22s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad or zst == "DIFFERS" or s0.startswith("OTHER") or any(v.startswith("OTHER") for v in s1.values()):
        print("ABORT"); return 1
    out = bytearray(d)

    def vanilla_all():
        for _n, va, v in allsites: out[f(va):f(va) + len(v)] = v
        out[f(ZONE):f(ZONE) + ZONE_END - ZONE] = bytes(ZONE_END - ZONE)
    if a.revert:
        if zst == "zero" and s0 == "vanilla" and all(v == "vanilla" for v in s1.values()): print("nothing to revert"); return 0
        vanilla_all()
        with open(exe, "r+b") as fh: fh.write(bytes(out))
        print("reverted (all three sites vanilla, zone zeroed)"); return 0
    if zst == "ours (v2)" and s0 == "ours" and all(v == "vanilla" for v in s1.values()): print("already applied (v2)"); return 0
    ok_from = ((zst == "zero" and s0 == "vanilla" and all(v == "vanilla" for v in s1.values())) or
               (zst == "v1" and s0 == "vanilla") or (zst.startswith("v2") and s0 in ("ours", "ours(old)")))
    if not ok_from: print("ABORT (partial state)"); return 1
    vanilla_all()
    out[f(ZONE):f(ZONE) + len(code)] = code
    out[f(H0[1]):f(H0[1]) + 6] = hook0
    print("%d bytes change%s" % (sum(1 for x, y in zip(d, out) if x != y),
                                  " (in-place upgrade from %s)" % zst if zst != "zero" else ""))
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = exe + ".bak_transmui2" if a.exe else bak_path(exe, ".bak_transmui2")
    if not os.path.exists(bak): shutil.copy2(exe, bak); print("backup ->", bak)
    with open(exe, "r+b") as fh: fh.write(bytes(out))
    assert open(exe, "rb").read() == bytes(out); print("Written and verified"); return 0


if __name__ == "__main__":
    sys.exit(main())
