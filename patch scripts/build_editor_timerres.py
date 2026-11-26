#!/usr/bin/env python3
r"""AoWx -- editor responsiveness: raise the process timer resolution.
AoWDevX.exe only.

ADOPTED 2026-08-31 from BXL/Ziggurat's build_editor_timerres.py (his RE and
measurements kept; re-homed to our renamed editor + house conventions).

THE PROBLEM (his measurement 2026-07-28, RE re-verified on OUR binaries):
  The editor's frame loop calls Sleep(1) TWICE per frame --
      HSEPack.dpl!HSMEdit.THSMEdit.UpdateFrame +0x09  (push 1 / call Sleep)
      AoWDevX.exe!TMainForm.HSMEditUpdateFrame +0x29  (push 1 / call Sleep)
  and NO AoW module ever calls timeBeginPeriod, so the process runs at
  Windows' DEFAULT 15.625 ms timer granularity: each Sleep(1) really sleeps
  ~15.6 ms, two of them = ~31 ms per frame. The render loop paces the whole
  message pump, so the editor services its queue only ~32x/second. A UI-
  thread profile showed 76% of the thread inside those two sleeps and ~5%
  doing real work. (This is also why raising the DFM FrameRate stopped
  helping -- ours is already 60 and FrameRate cannot pace below the Sleep
  floor.)

THE FIX: call timeBeginPeriod(1) once so Sleep(1) really is ~1 ms. He proved
it live before writing the patch by injecting the call into a running editor
with CreateRemoteThread: pump period 31.5 ms -> 8.0 ms with nothing else
changed.

HOW: hook the exe's kernel32 Sleep import THUNK @0x4013C8 (jmp [0x4322A0])
-> jmp cave. The cave does a one-time init on the FIRST Sleep call
(guaranteed to be the first frame), then tail-jumps to the real Sleep with
the caller's stack untouched -- no startup hook needed, one compare per later
call. AoWDevX.exe imports neither LoadLibraryA nor GetProcAddress, so the
cave reaches them through VCL30.dpl's IAT (the trick our dialog-dirs work
uses for the profile APIs):
    vcl_delta      = [0x432210] - 0x41336300   (exe IAT slot for
                     Forms.TCustomForm.Create, preferred VCL30 base+0x36300)
    LoadLibraryA   = [0x413E4360 + vcl_delta]
    GetProcAddress = [0x413E43B4 + vcl_delta]
then LoadLibraryA("winmm.dll") / GetProcAddress("timeBeginPeriod") / call(1).
Deliberately NOT derived from winmm's own export RVAs -- those change with
every Windows update and would turn a servicing update into a crash.
Windows drops the request when the process exits, so no timeEndPeriod.

ALL FOUR ANCHORS RE-VERIFIED ON OUR FILES 2026-08-31: thunk bytes vanilla;
`push 1` at 0x428D3F; exe IAT 0x432210 really is VCL30 Forms.TCustomForm.
Create; VCL30 imports LoadLibraryA @0x413E4360 and GetProcAddress
@0x413E43B4 exactly.

⚠ THE FRAME BUDGET MUST BE PUT BACK BY HAND. With a 1 ms timer the loop
free-runs: measured pump 8 ms but ~55% of a core (it then blits the map
~125x/s for nothing). Per-frame work is ~4 ms, so CPU ~= work/period:
    stock (15.6 ms timer)   pump ~31 ms   CPU ~14%
    1 ms timer, Sleep(8)    pump ~13 ms   CPU ~30%   <- our default
    1 ms timer, Sleep(1)    pump ~8 ms    CPU ~55%   <- ONLY with the render
                                                       gate installed
So we patch the exe's own Sleep argument (the imm8 of `push 1` @0x428D3F)
instead of giving up the accurate timer. **--sleep 1 is only safe once
build_editor_rendergate.py is installed** (its skip path paces the loop);
alone, use 8. The editor self-throttles when NOT foreground (~1-3% CPU), so
the idle cost only applies while it is the active window.

NEW SECTION `.tres` appended to AoWDevX.exe (its CODE tail cave is full --
see [[aowdevx-binary-notes]]). Our existing `.dlgd` section and the
identity cave inside its slack sit at the file tail and are NOT moved by an
append. SizeOfImage is recomputed from the MAX end over ALL sections (never
from our own -- that is the bug class that would unmap a later section).

The exe never rebases, so absolutes are fine; the VCL30 reach is delta-based
because VCL30 does rebase.

Usage: dry run default; --apply [--sleep N]; --revert (surgical: restores
the thunk + the Sleep arg and zeroes the .tres body, leaving the inert
section header in place so re-apply rewrites it without header churn).
"""
import os
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.environ.get("AOW_GAME_DIR") or os.path.dirname(HERE)
EXE = os.path.join(GAME, "AoWDevX.exe")
BAK = EXE + ".bak_timerres"

IMAGE_BASE = 0x400000
SECT_NAME = b".tres\0\0\0"

THUNK_VA = 0x4013C8
IAT_SLEEP = 0x4322A0
ORIG_THUNK = b"\xFF\x25" + struct.pack("<I", IAT_SLEEP)

VCL_BASE = 0x41300000
IAT_TCUSTOMFORM_CREATE = 0x432210
VCL_CREATE_PREF = VCL_BASE + 0x36300
VCL_IAT_LOADLIBRARYA = 0x413E4360
VCL_IAT_GETPROCADDRESS = 0x413E43B4

TARGET_MS = 1
SLEEP_ARG_VA = 0x428D40          # imm8 of `push 1` at 0x428D3F
ORIG_SLEEP_ARG = 1
DEFAULT_SLEEP = 8                # safe standalone value (BXL defaulted to 1,
                                 # which needs the render gate -- see above)


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


def gen(base_va, sleep_ms):
    """Returns (body bytes, code VA). Layout: [done flag][strings][code]."""
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    off = 0
    g_done = base_va + off
    off += 4
    s_winmm = base_va + off
    winmm_b = b"winmm.dll\0"
    off += len(winmm_b)
    s_tbp = base_va + off
    tbp_b = b"timeBeginPeriod\0"
    off += len(tbp_b)
    off = (off + 15) & ~15
    code_va = base_va + off
    data_len = off

    src = f"""
        cmp  dword ptr [{g_done:#x}], 0
        jne  _tail
        mov  dword ptr [{g_done:#x}], 1
        pushad
        mov  eax, dword ptr [{IAT_TCUSTOMFORM_CREATE:#x}]
        sub  eax, {VCL_CREATE_PREF:#x}
        mov  ebx, eax
        mov  eax, dword ptr [ebx + {VCL_IAT_LOADLIBRARYA:#x}]
        test eax, eax
        jz   _pop
        mov  edi, dword ptr [ebx + {VCL_IAT_GETPROCADDRESS:#x}]
        test edi, edi
        jz   _pop
        push {s_winmm:#x}
        call eax
        test eax, eax
        jz   _pop
        push {s_tbp:#x}
        push eax
        call edi
        test eax, eax
        jz   _pop
        push {TARGET_MS}
        call eax
    _pop:
        popad
    _tail:
        jmp  dword ptr [{IAT_SLEEP:#x}]
    """
    code, _ = Ks(KS_ARCH_X86, KS_MODE_32).asm(src, code_va)
    body = bytearray(data_len) + bytes(code)
    body[s_winmm - base_va:s_winmm - base_va + len(winmm_b)] = winmm_b
    body[s_tbp - base_va:s_tbp - base_va + len(tbp_b)] = tbp_b
    return bytes(body), code_va


def main():
    apply = "--apply" in sys.argv
    revert = "--revert" in sys.argv
    sleep_ms = DEFAULT_SLEEP
    if "--sleep" in sys.argv:
        sleep_ms = int(sys.argv[sys.argv.index("--sleep") + 1])
    if not (1 <= sleep_ms <= 60):
        print("--sleep out of range (1..60)")
        return 1

    d = bytearray(open(EXE, "rb").read())
    F = load_pe(d)
    th_off = rva2off(F["secs"], THUNK_VA - IMAGE_BASE)
    sl_off = rva2off(F["secs"], SLEEP_ARG_VA - IMAGE_BASE)
    assert d[sl_off - 1] == 0x6A, "expected `push imm8` at %#x" % (SLEEP_ARG_VA - 1)

    sect = None
    for s in F["secs"]:
        if bytes(d[s[4]:s[4] + 6]) == SECT_NAME[:6]:
            sect = s
    th_now = bytes(d[th_off:th_off + 6])

    if revert:
        if th_now == ORIG_THUNK and d[sl_off] == ORIG_SLEEP_ARG:
            print("already vanilla")
            return 0
        if not os.path.isfile(BAK):
            print("no backup; reverting surgically anyway")
        d[th_off:th_off + 6] = ORIG_THUNK
        d[sl_off] = ORIG_SLEEP_ARG
        if sect:
            va0, vsz, raw, rsz, hdr = sect
            d[raw:raw + rsz] = bytes(rsz)
            print("  .tres body zeroed (inert section header kept)")
        open(EXE, "wb").write(bytes(d))
        print("reverted: Sleep thunk + frame-loop Sleep(1) restored")
        return 0

    base_va = IMAGE_BASE + (sect[0] if sect else
                            align(max(s[0] + max(s[1], s[3]) for s in F["secs"]),
                                  F["salign"]))
    body, code_va = gen(base_va, sleep_ms)
    patched = b"\xE9" + struct.pack("<i", code_va - (THUNK_VA + 5)) + b"\x90"

    print("  .tres           @0x%08X (%d B body, hook 0x%08X)" % (base_va, len(body), code_va))
    print("  Sleep thunk     @0x%08X  %s -> %s" % (THUNK_VA, th_now.hex(), patched.hex()))
    print("  frame-loop arg  @0x%08X  Sleep(%d) -> Sleep(%d)" % (SLEEP_ARG_VA - 1, d[sl_off], sleep_ms))

    if sect and th_now == patched and bytes(d[sect[2]:sect[2] + len(body)]) == body \
            and d[sl_off] == sleep_ms:
        print("already applied")
        return 0
    if bool(sect) != (th_now == patched) and th_now != ORIG_THUNK:
        print("INCONSISTENT state (section=%s thunk=%s) - refusing" % (bool(sect), th_now.hex()))
        return 1
    if th_now not in (ORIG_THUNK, patched):
        print("FOREIGN thunk %s - refusing" % th_now.hex())
        return 1
    if not apply:
        try:
            from capstone import Cs, CS_ARCH_X86, CS_MODE_32
            print("  ---- cave ----")
            for i in Cs(CS_ARCH_X86, CS_MODE_32).disasm(body[code_va - base_va:], code_va):
                print("    %08X  %-7s %s" % (i.address, i.mnemonic, i.op_str))
        except ImportError:
            pass
        print("dry run (--apply [--sleep N] / --revert)")
        return 0

    if not os.path.isfile(BAK):
        shutil.copy2(EXE, BAK)
        print("  backed up")

    if sect:
        va0, vsz, raw, rsz, hdr = sect
        if len(body) <= rsz:
            # Overwrite IN PLACE. The old code rebuilt the file as
            # d[:raw] + body, which silently DESTROYS any section appended
            # after .tres -- e.g. `.vgo` from build_editor_validation_goto.py.
            # The body is ~0x76 B against a 0x200 B raw slot, so this path is
            # the normal one; the truncating path below only runs if the cave
            # ever outgrows its slot (and still refuses when it is not last).
            d[raw:raw + rsz] = bytearray(body) + bytearray(rsz - len(body))
            struct.pack_into("<II", d, hdr + 8, len(body), va0)
        else:
            assert raw + rsz >= len(d) - F["falign"], \
                ".tres outgrew its slot and is not the last section - revert " \
                "the later section(s) first (see [[aowdevx-binary-notes]])"
            rawsz = align(len(body), F["falign"])
            d = d[:raw] + bytearray(body) + bytearray(rawsz - len(body))
            struct.pack_into("<II", d, hdr + 8, len(body), va0)
            struct.pack_into("<II", d, hdr + 16, rawsz, raw)
    else:
        assert F["sectbl"] + (F["nsec"] + 1) * 40 <= F["hdrsz"], "no header room"
        newraw = align(len(d), F["falign"])
        d += bytes(newraw - len(d))
        rawsz = align(len(body), F["falign"])
        newva = base_va - IMAGE_BASE
        d += body + bytes(rawsz - len(body))
        b = F["sectbl"] + F["nsec"] * 40
        struct.pack_into("<8sIIII", d, b, SECT_NAME, len(body), newva, rawsz, newraw)
        struct.pack_into("<IIHHI", d, b + 24, 0, 0, 0, 0, 0xE0000060)   # R/W/X
        struct.pack_into("<H", d, F["e"] + 6, F["nsec"] + 1)
    # SizeOfImage from the MAX end over ALL sections, never just ours
    F2 = load_pe(d)
    soi = align(max(s[0] + max(s[1], s[3]) for s in F2["secs"]), F2["salign"])
    struct.pack_into("<I", d, F2["opt"] + 56, soi)

    d[th_off:th_off + 6] = patched
    d[sl_off] = sleep_ms
    try:
        open(EXE, "wb").write(bytes(d))
    except PermissionError:
        print("LOCKED - close AoWDevX.exe and retry")
        return 1
    print("APPLIED (SizeOfImage 0x%X) - test: editor UI/clicks/tab switches "
          "feel markedly snappier; map still animates; foreground CPU rises "
          "(~30%% of a core) until the render gate is added" % soi)
    return 0


if __name__ == "__main__":
    sys.exit(main())
