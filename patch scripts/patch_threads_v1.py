"""
THOUSAND THREADS (Earth/Death tier 4, spell id 335) - the WEB effect (2026-10-14).  AoWEPACK.dll only.
v2 2026-11-26 (user: make it like Entangle): the web attempt is ONE roll, Chance(STRENGTH 4 - target Resistance) = the Web ability's strength, the
same single-roll shape as TEntangle.CreateCA 0x557F8B20 (strength vs CU VMT+0x74); the to-hit roll vs Defense described below
is gone.  Only the `cr` cave changed; written in place (see CAVE_OFF).

335 is a GREAT HAIL clone (hail class 0x0A, 7 strikes = one per pattern hex; the strike count / landing / alias /
preview plumbing is NOT here - the Rot Away fork's scripts own it).  A strike landing on a unit hex makes a direct CA:
GetSpell(335).CreateCA = TGreatHail VMT+0x78 0x557F72C0 -> a TCombatSpellCA (VMT 0x557F3CC8, instance 0x20) whose
Setup 0x55729C98 rolls damage into [ca+0x10]; the CA executes via VMT+0x50 0x557F6A20.  Pokes give 335 DMG 0, so the
CA never deals damage; this script adds a vanilla web attempt to it.

Vanilla Web (ability 0x1B, TWebAbility VMT 0x5571F690; the Giant Spider's ranged web):
  fcExecuteCombatCommand 0x5576A5A4 -> CreateWebCA 0x5576A210 (eax ability, edx attacker CU, ecx target CU): a TWebCA
  whose byte [ca+0x10] = ability VMT+0x110 = the touch roll 0x557681B0:
    hit  = Chance(attacker CU VMT+0x6C (attack) - target CU VMT+0x70 (defense))
    if hit and strength != -10: Chance(strength - target CU VMT+0x74 (resistance)), strength = ability VMT+0x10C = 4
    Chance 0x55725D98: p = clamp(50 + 10 * diff, 10, 90) %, drawn with System.RandInt 0x55701080 (the combat RNG).
  TWebCA.Execute 0x5576A06C: if [ca+0x10]: unit = 0x55728C68([ctx+0xC], [ca+0xE]); GetAbility(0x61 = Webbed,
  TWebbedAbility) VMT+0xD0 (eax ability, edx = [unit+0x4C] the TUnit) = grant Webbed.  The roll happens at CA
  CREATION and only the result is serialized (TWebCA.ReadWrite), so it is MP-safe in the same way.
  TWebAbility.CanTouch 0x5576A254 (eax ability, edx attacker CU, ecx target CU): base touch check 0x557682AC, both
  are TCombatUnits, target not already Webbed (CU VMT+0xA8(0x61)).

This patch (all keyed on spell id 335; the same rolls, same RNG, at the same moment = CA creation):
  CR  0x557F72F7 (5 B `mov edx,[ebp-4] / mov eax,esi`, just before CreateCA calls Setup - ecx = edi already; ebx = spell,
      esi = CA, edi = target CU, [ebp-4] = caster CU) -> call cave + 2 nop: CanTouch, then
      Chance(spell ATK [spell+0x34] - target DEF), then Chance(web strength 4 - target RES); success -> scratch byte
      [ca+0x17] = 1 (not serialized; Setup doesn't touch it).  Then replays the 2 movs (pushal/popal keep ecx = target).
      (v1.1: moved from 0x557F72F5, which overlapped patch_rotaway_v1.py's 7-byte jmp at 0x557F72F0.)
  EP  0x557F7317 (CreateCA's epilogue `mov eax,esi / pop edi / pop esi / pop ebx` ...) -> jmp cave: for 335 move the
      scratch flag into bit 0x80 of [ca+0x12] (the high byte of the damage-types word +0x11, which IS serialized,
      tag 0x11; Setup rewrote +0x11 so the flag has to be set after it; with DMG 0 the types word is never used),
      clear the scratch; then the full epilogue (`mov eax,esi / pop edi / pop esi / pop ebx / pop ecx / pop ebp /
      ret 4`).  The `je 0x557F7317` at 0x557F7307 lands on the hook, as intended.
  EX  0x557F6A20 (CA execute entry `push ebx / push esi / mov esi,edx / mov ebx,eax`) -> jmp cave: replays them; for
      335 with the flag: grant Webbed exactly like TWebCA.Execute; back to 0x557F6A26.  (patch_bloodboil_v1.py hooks
      0x557F6A2A further down the same function - untouched.)
Zone AoWEPACK 0x5584D000..0x5584D200 (inside the fork's 0x5584D000-0x55850000; zero, reloc-free).  PIC: the only
in-image absolute (AoWHSSet 0x558FA044) is read via the call/pop delta.  Sites are reloc-free.
Dry-run default; --apply / --revert / --dis.  Backup <game>\\backup\\AoWEPACK.dll.bak_threads.
"""
import argparse, os, shutil, struct, sys
from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file

DLL = game_file("AoWEPACK.dll")
BASE, CODE_V2F = 0x55700000, 0x55700C00
ZONE, ZONE_END = 0x5584D000, 0x5584D200
SPELL_ID = 335
AOWHSSET, GETABILITY, CANTOUCH, CHANCE, UNIT_BY_ID = 0x558FA044, 0x557501C0, 0x5576A254, 0x55725D98, 0x55728C68
WEB_ID, WEBBED_ID = 0x1B, 0x61
STRENGTH = 4          # v2 2026-11-26 (user: web strength 4 like the Web ability, but ONE roll): Chance(4 - target Resistance); no to-hit roll vs Defense, the spell's ATK byte and the web ability's strength 4 are no longer used
CAVE_OFF = {"cr": 0x00, "ep": 0x90, "ex": 0xC0}   # v2: fixed cave layout (ep/ex stay where v1 put them - EX's site is chained by a later patch, so the zone is edited in place)
EX_RESUME = 0x557F6A26
SITES = {   # name: (va, original bytes, 'call' | 'jmp')
    "CR": (0x557F72F7, bytes.fromhex("8b55fc8bc6"), "call"),        # v1.1: after `mov ecx,edi` @0x557F72F5 (patch_rotaway_v1.py jmp-hooks 0x557F72F0..F6)
    "EP": (0x557F7317, bytes.fromhex("8bc65f5e5b"), "jmp"),
    "EX": (0x557F6A20, bytes.fromhex("53568bf28bd8"), "jmp"),
}

ks = Ks(KS_ARCH_X86, KS_MODE_32)


def asm_delta(src, va):
    s1 = src.replace("call $D", ".byte 0xe8, 0, 0, 0, 0").replace("sub eax, $D", "sub eax, 0x7fffffff")
    b = bytearray(ks.asm(s1, va)[0])
    anchor = bytes.fromhex("e8000000005825ffffff7f")   # placeholder, replaced below
    k = b.find(bytes.fromhex("e80000000058"))
    assert k >= 0 and b[k + 6] == 0x2D, "delta anchor not found"         # pop eax / sub eax, imm32 (2D)
    struct.pack_into("<I", b, k + 7, va + k + 5)
    return bytes(b)


def build():
    v = {"id": SPELL_ID, "hs": AOWHSSET, "ga": GETABILITY, "ct": CANTOUCH, "ch": CHANCE, "ub": UNIT_BY_ID,
         "web": WEB_ID, "webbed": WEBBED_ID, "res": EX_RESUME, "strength": STRENGTH}
    srcs = {
        "cr": """
            cmp dword ptr [ebx+0x10], %(id)d
            jne cr_replay
            pushal
            call $D
            pop eax
            sub eax, $D
            mov eax, [eax+%(hs)#x]
            mov eax, [eax+0x80]
            mov edx, %(web)d
            call %(ga)#x
            test eax, eax
            jz cr_done
            push eax
            mov ecx, edi
            mov edx, [ebp-4]
            call %(ct)#x
            test al, al
            jz cr_pop
            mov eax, edi
            mov edx, [eax]
            call dword ptr [edx+0x74]
            movsx edx, al
            mov eax, %(strength)d
            sub eax, edx
            call %(ch)#x
            test al, al
            jz cr_pop
            mov byte ptr [esi+0x17], 1
        cr_pop:
            add esp, 4
        cr_done:
            popal
        cr_replay:
            mov edx, [ebp-4]
            mov eax, esi
            ret
        """,
        "ep": """
            cmp dword ptr [esi+0x18], %(id)d
            jne ep_tail
            cmp byte ptr [esi+0x17], 0
            je ep_tail
            or byte ptr [esi+0x12], 0x80
            mov byte ptr [esi+0x17], 0
        ep_tail:
            mov eax, esi
            pop edi
            pop esi
            pop ebx
            pop ecx
            pop ebp
            ret 4
        """,
        "ex": """
            push ebx
            push esi
            mov esi, edx
            mov ebx, eax
            cmp dword ptr [ebx+0x18], %(id)d
            jne ex_back
            test byte ptr [ebx+0x12], 0x80
            jz ex_back
            pushal
            xor edx, edx
            mov dl, byte ptr [ebx+0xe]
            mov eax, [esi+0xc]
            call %(ub)#x
            test eax, eax
            jz ex_done
            mov edi, eax
            call $D
            pop eax
            sub eax, $D
            mov eax, [eax+%(hs)#x]
            mov eax, [eax+0x80]
            mov edx, %(webbed)d
            call %(ga)#x
            test eax, eax
            jz ex_done
            mov edx, [edi+0x4c]
            test edx, edx
            jz ex_done
            mov ecx, [eax]
            call dword ptr [ecx+0xd0]
        ex_done:
            popal
        ex_back:
            jmp %(res)#x
        """,
    }
    out, caves = bytearray(), {}
    for name in ("cr", "ep", "ex"):
        va = ZONE + CAVE_OFF[name]
        assert len(out) <= CAVE_OFF[name], name
        out += bytes(CAVE_OFF[name] - len(out))
        src = srcs[name] % v
        code = asm_delta(src, va) if "$D" in src else bytes(ks.asm(src, va)[0])
        out += code; caves[name] = va
    zone = bytes(out).rstrip(b"\x00")
    assert ZONE + len(zone) <= ZONE_END, hex(ZONE + len(zone))
    target = {"CR": caves["cr"], "EP": caves["ep"], "EX": caves["ex"]}
    hooks = {}
    for k, (va, orig, kind) in SITES.items():
        op = b"\xe8" if kind == "call" else b"\xe9"
        hooks[k] = op + struct.pack("<i", target[k] - (va + 5)) + b"\x90" * (len(orig) - 5)
    return zone, hooks, caves


def reloc_set(d):
    pe = struct.unpack_from("<I", d, 0x3C)[0]; opt = struct.unpack_from("<H", d, pe + 20)[0]; nsec = struct.unpack_from("<H", d, pe + 6)[0]
    secs = [struct.unpack_from("<IIII", d, pe + 24 + opt + 40 * k + 8) for k in range(nsec)]
    rrva, rsz = struct.unpack_from("<II", d, pe + 24 + 0x88)
    def r2f(rva):
        for vs, va, rs, ro in secs:
            if va <= rva < va + max(vs, rs): return ro + rva - va
    p, end, out = r2f(rrva), r2f(rrva) + rsz, set()
    while p < end:
        page, size = struct.unpack_from("<II", d, p)
        if size < 8: break
        for q in range(p + 8, p + size, 2):
            e = struct.unpack_from("<H", d, q)[0]
            if e >> 12 == 3: out.add(BASE + page + (e & 0xFFF))
        p += size
    return out


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true"); a = ap.parse_args()
    d = bytearray(open(DLL, "rb").read())
    zone, hooks, caves = build()
    zl = bytes(d[ZONE - CODE_V2F:ZONE_END - CODE_V2F])
    zstate = "zero" if not any(zl) else "ours" if zl[:len(zone)] == zone and not any(zl[len(zone):]) else "DIFFERS"
    states = {}
    for k, (va, orig, kind) in SITES.items():
        live = bytes(d[va - CODE_V2F:va - CODE_V2F + len(orig)])
        if live == orig: states[k] = "vanilla"
        elif live == hooks[k]: states[k] = "ours"
        elif live[0] in (0xE8, 0xE9) and ZONE <= va + 5 + struct.unpack_from("<i", live, 1)[0] < ZONE_END: states[k] = "ours(old)"
        else: states[k] = "OTHER"
    rl = reloc_set(bytes(d))
    bad = [hex(r) for r in rl if ZONE <= r < ZONE_END or any(va <= r < va + len(orig) for va, orig, _ in SITES.values())]
    print("sites %s | zone %s (%d B: %s) | relocs %s" % (states, zstate, len(zone), ", ".join("%s @%#x" % kv for kv in caves.items()), bad or "none"))
    if a.dis:
        import capstone
        for i in capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32).disasm(zone, ZONE): print("   %08X  %-18s %s %s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
    if bad or "OTHER" in states.values(): print("ABORT"); return 1
    if zstate == "DIFFERS" and not any(s.startswith("ours") for s in states.values()): print("ABORT (zone not free)"); return 1
    if a.revert:
        for k, (va, orig, kind) in SITES.items(): d[va - CODE_V2F:va - CODE_V2F + len(orig)] = orig
        d[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE)
        with open(DLL, "r+b") as f: f.write(bytes(d))
        print("reverted (all sites vanilla, zone zeroed)"); return 0
    if all(s == "ours" for s in states.values()) and zstate == "ours": print("already applied"); return 0
    d[ZONE - CODE_V2F:ZONE_END - CODE_V2F] = bytes(ZONE_END - ZONE); d[ZONE - CODE_V2F:ZONE - CODE_V2F + len(zone)] = zone
    for k, (va, orig, kind) in SITES.items(): d[va - CODE_V2F:va - CODE_V2F + len(orig)] = hooks[k]
    if not a.apply: print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(DLL, ".bak_threads")
    if not os.path.exists(bak): shutil.copy2(DLL, bak); print("backup ->", bak)
    with open(DLL, "r+b") as f: f.write(bytes(d))
    assert open(DLL, "rb").read() == bytes(d); print("Written and verified"); return 0


if __name__ == "__main__":
    sys.exit(main())
