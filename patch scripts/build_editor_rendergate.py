#!/usr/bin/env python3
r"""AoWx -- editor render gate: pace the map RENDER on wall-clock time while
the message pump keeps running flat out. HSEPack.dpl (editor path only).

WHY (user report 2026-08-31, after build_editor_timerres.py):
  "more responsive, but all the animations are sped up."
  ROOT CAUSE, established by RE this session: THSMEdit.UpdateFrame has NO
  wall-clock time base at all -- the only timeGetTime calls in that region
  (0x55613E19.. and 0x55614C4B..) write perf counters ([self+0x248/0x250/
  0x258/0x25C]), nothing gates on them. Animation therefore advances ONCE
  PER UpdateFrame CALL, and the frame loop paces the message pump, so
  animation speed == pump speed. timerres took the pump from ~31 ms to
  ~13 ms, so animations run ~2.4x too fast. The DFM FrameRate property does
  not throttle this (ours is already 60 and BXL measured lowering it makes
  things worse).
  ⇒ Pump rate and animation rate cannot be separated without a gate. This
  is that gate.

THE GATE (adapted from BXL/Ziggurat's build_editor_rendergate.py -- his hook
site, his skip-target warning and his epilogue RE, but TIME-BASED instead of
his every-Nth-pass counter, because a pass counter re-couples animation
speed to pump speed; wall-clock keeps animation correct at ANY pump rate):
  hook the 7 bytes at 0x55614912 (`cmp byte ptr [esi+0x1bc],0`) -> cave:
      now = timeGetTime()                    (HSEPack already imports it;
                                              thunk 0x55601BE4, rel32)
      if (now - last) < interval:  Sleep(skip_ms); eax=0; jmp EPILOGUE
      else:                        last = now; replay the cmp; jmp RESUME
  RESUME 0x55614919 is the original `je`, so the displaced compare's FLAGS
  must be intact -- the cmp is the last thing before the jump.

  ⚠ THE SKIP PATH MUST JUMP TO THE EPILOGUE 0x55614C2E, NOT to the
  function's own early-exit 0x55614C27. That label still runs
  `call TCustomDisplay.UpdateFrame` @0x55614C29, which is where the present
  (GFXE.TDIB16Surface.BltDC -> StretchDIBits) happens; BXL's first attempt
  jumped there and CPU only fell 35% -> 22.5%. (--present-on-skip restores
  that behaviour if a skipped frame ever leaves the window unrepainted.)
  ⚠ Because that same call is what fires OnUpdateFrame -- and hence the
  exe's own Sleep -- a skipped pass must sleep in the cave or the loop
  free-runs.
  Return value on skip: eax=0. Verified safe on OUR exe: the editor's frame
  tick @0x42BDC8 does `call [vmt+0xAC] / test al,al / je 0x42BE87`, and
  0x42BE87 is just `pop ebx; ret` -- i.e. al=0 means "nothing to do, return",
  skipping only the status-bar/scanner updates. No loop-continuation state
  is touched.

PIC (HSEPack rebases): state is reached off a `call $+5; pop ebx` RUNTIME
anchor with NO sub (house rule); every call/jmp is rel32 within the image.
The cave contains no absolute operands, so it needs no .reloc entries.
Hook range 0x55614912..0x55614919 is reloc-free (the fixup at 0x55614920
belongs to `mov eax,[0x5562E2F4]` @0x5561491F and is NOT displaced) --
re-asserted by this script on every run.

DEFAULTS: --interval 31 restores the pre-timerres animation rate (BXL
measured stock pump 31.0 ms; animation stepped once per pump). --skip-sleep 2
keeps the pump at ~2 ms without spinning. The exe's own Sleep is left alone
(build_editor_timerres.py owns it) so the two patches stay INDEPENDENT --
no revert-both-or-neither coupling.

SCOPE: THSMEdit is the EDITOR's map control. AoWx.exe loads HSEPack.dpl but
never executes this path. HSEPack.dpl already ships modified (it carries our
.dlgd section).

Usage: dry run default; --apply [--interval N] [--skip-sleep N]
[--present-on-skip]; --revert (surgical: restores the 7 hook bytes and
zeroes the cave body, leaving the inert section header).
"""
import os
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.environ.get("AOW_GAME_DIR") or os.path.dirname(HERE)
DLL = os.path.join(GAME, "HSEPack.dpl")
BAK = DLL + ".bak_rendergate"

PREF_BASE = 0x55600000
D = 0x55600C00                      # CODE: VA = file + this
SECT_NAME = b".rgt\0\0\0\0"

HOOK_VA = 0x55614912
ORIG_HOOK = bytes([0x80, 0xBE, 0xBC, 0x01, 0x00, 0x00, 0x00])
RESUME_VA = 0x55614919              # the original `je 0x55614C27`
EPILOGUE_VA = 0x55614C2E            # pop ecx/edx/esi/ebx; ret
EPI_BYTES = bytes([0x59, 0x5A, 0x5E, 0x5B, 0xC3])
PRESENT_EXIT_VA = 0x55614C27        # early-exit that STILL presents
TIMEGETTIME_THUNK = 0x55601BE4
SLEEP_THUNK = 0x556014FC
SELF_FLAG = 0x1BC

DEFAULT_INTERVAL = 31
DEFAULT_SKIP_SLEEP = 2


def align(x, a):
    return (x + a - 1) // a * a


def load_pe(d):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, e + 6)[0]
    optsz = struct.unpack_from("<H", d, e + 20)[0]
    opt = e + 24
    sectbl = opt + optsz
    secs = []
    for i in range(nsec):
        b = sectbl + i * 40
        vsz, va, rsz, raw = struct.unpack_from("<IIII", d, b + 8)
        secs.append((va, vsz, raw, rsz, b))
    return dict(e=e, nsec=nsec, opt=opt, sectbl=sectbl, secs=secs,
                salign=struct.unpack_from("<I", d, opt + 32)[0],
                falign=struct.unpack_from("<I", d, opt + 36)[0],
                hdrsz=struct.unpack_from("<I", d, opt + 84)[0])


def rva2off(secs, rva):
    for va0, vsz, raw, rsz, _ in secs:
        if va0 <= rva < va0 + max(vsz, rsz):
            return raw + (rva - va0)
    raise ValueError("rva %#x maps to no section" % rva)


def relocs_in(d, lo, hi):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    opt = e + 24
    rva, size = struct.unpack_from("<II", d, opt + 96 + 5 * 8)
    if not rva:
        return []
    F = load_pe(d)
    p = rva2off(F["secs"], rva)
    end = p + size
    hits = []
    while p < end:
        pg, blk = struct.unpack_from("<II", d, p)
        if blk < 8:
            break
        for k in range(8, blk, 2):
            w = struct.unpack_from("<H", d, p + k)[0]
            if w >> 12 == 3:
                va = PREF_BASE + pg + (w & 0xFFF)
                if lo <= va < hi:
                    hits.append(va)
        p += blk
    return hits


def gen(base_va, interval, skip_sleep, present_on_skip):
    """[last][interval][skip_ms] then code. Returns (body, code_va)."""
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    data_len = 0x10
    code_va = base_va + data_len
    skip_target = PRESENT_EXIT_VA if present_on_skip else EPILOGUE_VA
    src = f"""
        push ebx
        call _a
    _a:
        pop  ebx
        call 0x{TIMEGETTIME_THUNK:X}
        mov  ecx, [ebx + {base_va - 0:#x} - _anchor]
        """
    # keystone has no symbolic anchor arithmetic here; emit by hand instead.
    from keystone import Ks as _K
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    body = bytearray(data_len)
    struct.pack_into("<III", body, 0, 0, interval, skip_sleep)

    code = bytearray()
    code += b"\x53"                                   # push ebx
    code += b"\xE8\x00\x00\x00\x00"                   # call $+5
    anchor = code_va + len(code)                      # runtime addr of `pop ebx`
    code += b"\x5B"                                   # pop ebx
    def disp(off):
        return struct.pack("<i", (base_va + off) - anchor)
    def rel32(op, target, at):
        return op + struct.pack("<i", target - (at + len(op) + 4))
    code += rel32(b"\xE8", TIMEGETTIME_THUNK, code_va + len(code))   # call timeGetTime
    code += b"\x8B\x8B" + disp(0)                     # mov ecx,[ebx+last]
    code += b"\x89\xC2"                               # mov edx,eax
    code += b"\x29\xCA"                               # sub edx,ecx
    code += b"\x3B\x93" + disp(4)                     # cmp edx,[ebx+interval]
    jb_at = len(code)
    code += b"\x0F\x82\x00\x00\x00\x00"               # jb _skip (patched)
    code += b"\x89\x83" + disp(0)                     # mov [ebx+last],eax
    code += b"\x5B"                                   # pop ebx
    code += b"\x80\xBE" + struct.pack("<I", SELF_FLAG) + b"\x00"   # cmp byte[esi+0x1bc],0
    code += rel32(b"\xE9", RESUME_VA, code_va + len(code))         # jmp resume
    skip_off = len(code)
    struct.pack_into("<i", code, jb_at + 2, skip_off - (jb_at + 6))
    code += b"\xFF\xB3" + disp(8)                     # push [ebx+skip_ms]
    code += rel32(b"\xE8", SLEEP_THUNK, code_va + len(code))       # call Sleep
    code += b"\x31\xC0"                               # xor eax,eax
    code += b"\x5B"                                   # pop ebx
    code += rel32(b"\xE9", skip_target, code_va + len(code))       # jmp epilogue
    return bytes(body) + bytes(code), code_va


def main():
    apply = "--apply" in sys.argv
    revert = "--revert" in sys.argv
    present_on_skip = "--present-on-skip" in sys.argv
    interval = DEFAULT_INTERVAL
    skip_sleep = DEFAULT_SKIP_SLEEP
    if "--interval" in sys.argv:
        interval = int(sys.argv[sys.argv.index("--interval") + 1])
    if "--skip-sleep" in sys.argv:
        skip_sleep = int(sys.argv[sys.argv.index("--skip-sleep") + 1])
    if not (5 <= interval <= 200):
        print("--interval out of range (5..200)")
        return 1
    if not (0 <= skip_sleep <= 30):
        print("--skip-sleep out of range (0..30)")
        return 1

    d = bytearray(open(DLL, "rb").read())
    F = load_pe(d)
    hook_off = rva2off(F["secs"], HOOK_VA - PREF_BASE)
    assert bytes(d[EPILOGUE_VA - D:EPILOGUE_VA - D + 5]) == EPI_BYTES, \
        "epilogue signature mismatch"
    hits = relocs_in(d, HOOK_VA, HOOK_VA + len(ORIG_HOOK))
    assert not hits, "relocs inside the displaced range: %s" % [hex(x) for x in hits]

    sect = None
    for s in F["secs"]:
        if bytes(d[s[4]:s[4] + 5]) == SECT_NAME[:5]:
            sect = s
    now = bytes(d[hook_off:hook_off + len(ORIG_HOOK)])

    if revert:
        if now == ORIG_HOOK:
            print("already vanilla")
            return 0
        d[hook_off:hook_off + len(ORIG_HOOK)] = ORIG_HOOK
        if sect:
            d[sect[2]:sect[2] + sect[3]] = bytes(sect[3])
            print("  .rgt body zeroed (inert section header kept)")
        open(DLL, "wb").write(bytes(d))
        print("reverted: UpdateFrame gate removed")
        return 0

    base_va = PREF_BASE + (sect[0] if sect else
                           align(max(s[0] + max(s[1], s[3]) for s in F["secs"]),
                                 F["salign"]))
    body, code_va = gen(base_va, interval, skip_sleep, present_on_skip)
    patched = b"\xE9" + struct.pack("<i", code_va - (HOOK_VA + 5)) + b"\x90\x90"

    print("  .rgt   @0x%08X (%d B, code 0x%08X)" % (base_va, len(body), code_va))
    print("  hook   @0x%08X  %s -> %s" % (HOOK_VA, now.hex(), patched.hex()))
    print("  render every %d ms (skip: Sleep(%d) -> %s)"
          % (interval, skip_sleep,
             "present+exit 0x%08X" % PRESENT_EXIT_VA if present_on_skip
             else "epilogue 0x%08X" % EPILOGUE_VA))

    if sect and now == patched and bytes(d[sect[2]:sect[2] + len(body)]) == body:
        print("already applied")
        return 0
    if now not in (ORIG_HOOK, patched):
        print("FOREIGN hook %s - refusing" % now.hex())
        return 1
    if not apply:
        try:
            from capstone import Cs, CS_ARCH_X86, CS_MODE_32
            print("  ---- cave ----")
            for i in Cs(CS_ARCH_X86, CS_MODE_32).disasm(body[code_va - base_va:], code_va):
                print("    %08X  %-7s %s" % (i.address, i.mnemonic, i.op_str))
        except ImportError:
            pass
        print("dry run (--apply / --revert)")
        return 0

    if not os.path.isfile(BAK):
        shutil.copy2(DLL, BAK)
        print("  backed up")
    if sect:
        va0, vsz, raw, rsz, hdr = sect
        assert raw + rsz >= len(d) - F["falign"], ".rgt is not the last section"
        rawsz = align(len(body), F["falign"])
        d = d[:raw] + bytearray(body) + bytearray(rawsz - len(body))
        struct.pack_into("<II", d, hdr + 8, len(body), va0)
        struct.pack_into("<II", d, hdr + 16, rawsz, raw)
    else:
        assert F["sectbl"] + (F["nsec"] + 1) * 40 <= F["hdrsz"], "no header room"
        newraw = align(len(d), F["falign"])
        d += bytes(newraw - len(d))
        rawsz = align(len(body), F["falign"])
        newva = base_va - PREF_BASE
        d += body + bytes(rawsz - len(body))
        b = F["sectbl"] + F["nsec"] * 40
        struct.pack_into("<8sIIII", d, b, SECT_NAME, len(body), newva, rawsz, newraw)
        struct.pack_into("<IIHHI", d, b + 24, 0, 0, 0, 0, 0xE0000060)   # R/W/X
        struct.pack_into("<H", d, F["e"] + 6, F["nsec"] + 1)
    F2 = load_pe(d)
    soi = align(max(s[0] + max(s[1], s[3]) for s in F2["secs"]), F2["salign"])
    struct.pack_into("<I", d, F2["opt"] + 56, soi)
    d[hook_off:hook_off + len(ORIG_HOOK)] = patched
    try:
        open(DLL, "wb").write(bytes(d))
    except PermissionError:
        print("LOCKED - close AoWDevX.exe and AoWx.exe, then retry")
        return 1
    print("APPLIED (SizeOfImage 0x%X) - test: editor stays responsive AND "
          "animations run at the vanilla speed; re-tune with --interval N "
          "(higher = slower animation, lower CPU)" % soi)
    return 0


if __name__ == "__main__":
    sys.exit(main())
