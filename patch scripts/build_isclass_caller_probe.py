#!/usr/bin/env python3
r"""DIAGNOSTIC: name the AoWEPACK caller that passes a garbage object to
System.@IsClass.

CONTEXT (2026-08-12; Keeper2 turn-18 autosave = a deterministic repro)
    "Exception occured during TArmyCombatMoveTE" now reports:

        Exception EAccessViolation in module VCL30.dpl at 00003A18.
        Access violation at address 41303A18 ... Read of address 00001902

    0x41303A18 is inside System.@IsClass:

        41303A14  test eax,eax      ; nil-safe ...
        41303A16  je   0x41303A28   ;   -> false
        41303A18  mov  eax,[eax]    ; ... but NOT garbage-safe   <-- faults
        41303A1A  cmp  eax,edx
        41303A1E  mov  eax,[eax-0x18]
        41303A23  jne  0x41303A18   ; parent-chain loop

    eax was **0x00001902** - non-nil, so it passed the nil check and got
    dereferenced. Wrong-class family again, this time through a type test.

⚠ WHY THIS HOOKS THE THUNK, NOT @IsClass ITSELF
    The first attempt detoured @IsClass's entry (6 bytes at 0x41303A14) and
    the game died with **runtime error 216** (unhandled AV) before reaching the
    menu. Reason: 0x41303A18 is the target of @IsClass's OWN loop back-edge
    (`jne 0x41303A18` at 0x41303A23), so the loop re-entered the middle of the
    inserted 5-byte jmp and executed garbage.
    ★ LESSON: scanning .reloc is not enough - before displacing bytes, scan the
    module for BRANCHES LANDING INSIDE the displaced range.
    Hooking AoWEPACK's private import thunk avoids all of that, keeps shared
    RTL untouched (VCL30 is used by the game AND both editors), and gives the
    caller's address in AoWEPACK's own space so the cave can convert it to a
    static VA itself.

⚠ SECOND LESSON (runtime 217 / CloseHSM errors on any map load)
    The first thunk-hook build tail-jumped through ECX, on the wrong belief
    that @IsClass clobbers ECX anyway. It does NOT - @IsClass touches only
    EAX/EDX - so callers legitimately keep live values in ECX across the call
    and the cave corrupted all of them. The pass path now preserves ECX via
    push ecx / PIC lookup in ecx / xchg ecx,[esp] / ret.

⚠ THIRD LESSON (same 217/CloseHSM symptoms even with ECX preserved)
    The original thunk `jmp [0x558FB6BC]` carries a **type-3 .reloc entry at
    0x557010C2** (entry @file 0x272638) - the exact bytes our E9 rel32
    occupies. AoWEPACK ALWAYS rebases, so the loader added the rebase delta
    into the middle of the relative jump and it landed in garbage. A menu-only
    smoke test passes because @IsClass is first called during map load.
    Fix: neutralize the entry (type 3 -> 0) on apply; --revert restores the
    whole file from backup, relocs included. This is exactly the
    patching-over-relocs rule - it applies to IMPORT THUNKS too.

WHAT THIS DOES
    Thunk 0x557010C0 (`jmp [0x558FB6BC]`) -> cave. The cave:
      * non-nil but implausible object  -> deliberately faults reading
        (staticVA(returnAddress) | 0x80000000), so the v2 dialog prints
        `Read of address 8XXXXXXX` and value & 0x7FFFFFFF is the static VA
        right after the offending `call @IsClass`;
      * anything else -> tail-jumps to the real @IsClass through the IAT,
        so behaviour is otherwise identical.
    Only AoWEPACK callers are covered; if nothing fires, the culprit lives in
    AoWTCPCK/AoWx.exe and their thunks need the same treatment.

    Cave @0x55811060, PIC (AoWEPACK rebases). Backup:
    AoWEPACK.dll.bak_isclsprobe. Dry-run default; --apply / --revert.
"""
import os, shutil, sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DLL = os.path.join(GAME, "AoWEPACK.dll")
BAK = DLL + ".bak_isclsprobe"

VA2FILE = 0x55700C00
THUNK = 0x557010C0
IAT_ISCLASS = 0x558FB6BC
OLD = bytes.fromhex("ff25bcb68f55")          # jmp dword ptr [0x558FB6BC]
CAVE_BASE, CAVE_LIMIT = 0x55811060, 0x55811100
MIN_PTR, MAX_PTR = 0x10000, 0x7F000000


def build_cave():
    base = CAVE_BASE
    buf = bytearray(); labels = {}; jcc8 = []

    def db(*b): buf.extend(b)
    def dd(v): buf.extend((v & 0xFFFFFFFF).to_bytes(4, 'little'))
    def here(): return base + len(buf)
    def lab(n): labels[n] = here()
    def j8(op, n): db(op); jcc8.append((len(buf), n)); db(0)

    db(0x85, 0xC0)                  # test eax,eax
    j8(0x74, 'pass')                # nil -> let the real one return false
    db(0x3D); dd(MIN_PTR)           # cmp eax,0x10000
    j8(0x72, 'bogus')
    db(0x3D); dd(MAX_PTR)           # cmp eax,0x7F000000
    j8(0x73, 'bogus')
    lab('pass')
    # PIC tail-jump to the real @IsClass via the IAT. ⚠ @IsClass touches ONLY
    # eax/edx (verified by disassembly), so ecx MUST survive this path — the
    # first build tail-jumped through ecx and corrupted every call site that
    # kept a live value there (CloseHSM / runtime 217 on any map load).
    # Scheme: save ecx, use it for the PIC lookup, then xchg the real @IsClass
    # address with the saved ecx on the stack and RET into it.
    db(0x51)                        # push ecx           (save caller's ecx)
    db(0xE8); dd(0)                 # call $+5
    popva = here()
    db(0x59)                        # pop ecx            (runtime addr of popva)
    db(0x81, 0xE9); dd(popva)       # sub ecx, static -> rebase delta
    db(0x81, 0xC1); dd(IAT_ISCLASS)  # add ecx, &IAT -> runtime IAT slot
    db(0x8B, 0x09)                  # mov ecx,[ecx]      (real @IsClass)
    db(0x87, 0x0C, 0x24)            # xchg ecx,[esp]     (ecx restored; TOS=target)
    db(0xC3)                        # ret -> real @IsClass, all regs intact
    lab('bogus')
    db(0x8B, 0x0C, 0x24)            # mov ecx,[esp]   (caller's return address)
    db(0xE8); dd(0)                 # call $+5
    popva2 = here()
    db(0x5A)                        # pop edx
    db(0x81, 0xEA); dd(popva2)      # sub edx, static -> delta
    db(0x29, 0xD1)                  # sub ecx,edx     -> STATIC VA
    db(0x81, 0xC9); dd(0x80000000)  # or ecx,0x80000000
    db(0x8B, 0x09)                  # mov ecx,[ecx]   -> AV names it
    db(0xC3)

    for off, name in jcc8:
        d = labels[name] - (base + off + 1)
        assert -128 <= d <= 127, (name, d)
        buf[off] = d & 0xFF
    assert base + len(buf) <= CAVE_LIMIT, len(buf)
    return bytes(buf)


def neutralize_relocs(d, va_lo, va_hi):
    """Set type 3->0 for every .reloc entry whose target lies in [va_lo, va_hi).
    Returns the list of (rva, file_offset) neutralized. Asserts none are left
    unhandled (unknown types)."""
    import struct
    pe = struct.unpack_from('<I', d, 0x3C)[0]
    nsec = struct.unpack_from('<H', d, pe + 6)[0]
    base = struct.unpack_from('<I', d, pe + 0x34)[0]
    rel = None
    for i in range(nsec):
        o = pe + 0xF8 + i * 0x28
        if d[o:o + 8].rstrip(b'\0') == b'.reloc':
            rsz = struct.unpack_from('<I', d, o + 0x10)[0]
            raw = struct.unpack_from('<I', d, o + 0x14)[0]
            rel = (raw, rsz)
    assert rel, "no .reloc section"
    raw, size = rel
    hits = []
    o, end = raw, raw + size
    while o < end - 8:
        page, bsz = struct.unpack_from('<II', d, o)
        if bsz == 0:
            break
        for k in range((bsz - 8) // 2):
            eo = o + 8 + k * 2
            e = struct.unpack_from('<H', d, eo)[0]
            typ, off = e >> 12, e & 0xFFF
            va = base + page + off
            if va_lo <= va < va_hi and typ != 0:
                assert typ == 3, "unexpected reloc type %d @VA 0x%X" % (typ, va)
                d[eo:eo + 2] = struct.pack('<H', off)   # type 0, keep offset
                hits.append((page + off, eo))
        o += bsz
    return hits


def main():
    apply = "--apply" in sys.argv
    revert = "--revert" in sys.argv
    if revert:
        if os.path.exists(BAK):
            shutil.copy2(BAK, DLL)
            print("restored AoWEPACK.dll from", os.path.basename(BAK))
            return 0
        print("no backup found:", BAK)
        return 1

    d = bytearray(open(DLL, 'rb').read())
    cave = build_cave()
    t_off = THUNK - VA2FILE
    c_off = CAVE_BASE - VA2FILE
    cur = bytes(d[t_off:t_off + len(OLD)])
    assert cur == OLD or cur[0] == 0xE9, "unexpected thunk bytes: " + cur.hex()
    curc = bytes(d[c_off:c_off + len(cave)])
    assert curc == bytes(len(cave)) or curc[:2] == cave[:2], "cave not free: " + curc[:8].hex()

    d[c_off:c_off + len(cave)] = cave
    d[t_off:t_off + len(OLD)] = (bytes([0xE9]) +
                                 (CAVE_BASE - (THUNK + 5)).to_bytes(4, 'little', signed=True) +
                                 b'\x90')
    # ⚠ CRITICAL: the stock thunk's absolute [0x558FB6BC] operand has a type-3
    # reloc at 0x557010C2 sitting inside our E9 rel32; AoWEPACK always rebases,
    # so an un-neutralized entry corrupts the jump at load time (CloseHSM /
    # runtime 217). Also sweep the cave range defensively.
    hits = neutralize_relocs(d, THUNK, THUNK + len(OLD))
    hits += neutralize_relocs(d, CAVE_BASE, CAVE_BASE + len(cave))
    assert hits, "expected the thunk reloc @0x557010C2 - wrong build?"
    for rva, eo in hits:
        print("reloc neutralized: RVA 0x%X (entry @file 0x%X)" % (rva, eo))
    print("cave %d B @0x%X; @IsClass thunk 0x%X -> cave" % (len(cave), CAVE_BASE, THUNK))
    print("bogus object => dialog reads 'Read of address 8XXXXXXX'")
    print("  caller static VA = value & 0x7FFFFFFF")
    if not apply:
        print("Dry run OK - rerun with --apply (or --revert).")
        return 0
    if not os.path.exists(BAK):
        shutil.copy2(DLL, BAK)
        print("Backup ->", os.path.basename(BAK))
    open(DLL, 'wb').write(d)
    print("Written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
