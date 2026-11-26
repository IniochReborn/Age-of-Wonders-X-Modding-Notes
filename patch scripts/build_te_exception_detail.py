#!/usr/bin/env python3
r"""DIAGNOSTIC (v2): make the "Exception occured during <TE>" dialog reveal
WHERE it failed - for EVERY exception type, not just access violations.

WHY
    Every turn event runs inside a try/except in
    NetworkE.TTokenExecuter.ExecuteTokenEvent @0x55803D24 (Network.dpl):

        call [TE_vmt+0x4C]              ; TMoveTE.Execute etc.
      except:
        ShowMessage('Exception occured during ' + TE.ClassName)

    The exception object is discarded, so the player only sees the TE class.
    Execution then continues with that turn event abandoned - a swallowed
    crash, which is why the game limps on and later throws follow-on errors
    like 'Combat already created'.

v1 -> v2
    v1 appended `E.Message`. That is perfect for an access violation
    ("Access violation at address X in module 'Y'. Read of address Z") but a
    *raised* Delphi exception carries NO address - e.g. HSEngine's
    'Index out of bounds' told us nothing about which TMapField accessor or
    caller was at fault. v2 instead calls **SysUtils.ExceptionErrorMessage**,
    which formats, for every exception class:

        Exception EAccessViolation in module AoWEPACK.dll at 00110C93.
        Access violation at address 01260C93 ... read of address 9EED7398

    i.e. always a module + offset, so a raised exception is as locatable as an
    AV. The module-relative offset is the useful part: add 0x55700000 to get
    the static VA directly, no need to re-read the runtime module base.

HOW
    Hook: the 5-byte `call Dialogs.ShowMessage` at 0x55803DD2 -> `call cave`.
    EAX already holds the finished AnsiString, so the cave shows it, then
    formats and shows the exception detail.

    Getting un-imported RTL routines without adding imports: Network.dpl
    imports SysUtils.Exception.Create (IAT 0x55809564), and in VCL30
        Exception.Create        = 0x4130F444
        ExceptObject            = 0x4130F13C   (-0x308)
        ExceptAddr              = 0x4130F15C   (-0x2E8)
        ExceptionErrorMessage   = 0x4130F188   (-0x2BC)
    so each is a fixed delta from the imported neighbour's runtime address.
    ExceptionErrorMessage(eax=ExceptObject, edx=ExceptAddr, ecx=Buffer,
    Size pushed) returns the length in eax and is `ret 4` (callee cleans) -
    both verified by disassembly. The returned PChar is turned into a
    ShortString by writing the length into the byte before the buffer, then
    @LStrFromString -> ShowMessage -> @LStrClr (no leak).

    ExceptObject returns nil when no exception is active; the cave guards that
    and simply degrades to the stock dialog. Cave @0x55806210 = the all-zero
    padding after Network.dpl's CODE section (0x1F0 bytes, inside
    SizeOfRawData so it is mapped and executable). PIC via the call/pop delta
    trick because Network.dpl rebases.

    Backup: Network.dpl.bak_texcdetail (pristine pre-diagnostic file, so
    --revert works from either v1 or v2). Dry-run default; --apply / --revert.

THIS IS A DIAGNOSTIC BUILD - revert it before shipping.
"""
import os, shutil, struct, sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DLL = os.path.join(GAME, "Network.dpl")
BAK = DLL + ".bak_texcdetail"

VA2FILE = 0x55800C00
CAVE_BASE, CAVE_LIMIT = 0x55806210, 0x55806400

H_SITE = 0x55803DD2                     # call Dialogs.ShowMessage in the handler
H_OLD = bytes.fromhex("e8edd8ffff")     # call 0x558016C4
F_SHOWMESSAGE = 0x558016C4              # Network.dpl import thunks
F_LSTRFROMSTRING = 0x558010B8
F_LSTRCLR = 0x558010A8
IAT_EXC_CREATE = 0x55809564             # VCL30.dpl!SysUtils.Exception.Create
D_EXCOBJ = 0x308                        # Exception.Create - ExceptObject
D_EXCADDR = 0x2E8                       # Exception.Create - ExceptAddr
D_EXCMSG = 0x2BC                        # Exception.Create - ExceptionErrorMessage

BUFSZ = 0xFA                            # 250 chars max (ShortString safe)
LOCALS = 0x140
O_STR = 4                               # [ebp-4]      local AnsiString
O_LEN = 0x111                           # [ebp-0x111]  ShortString length byte
O_BUF = 0x110                           # [ebp-0x110]  chars


def build_cave():
    base = CAVE_BASE
    buf = bytearray(); rel = []; labels = {}; jcc8 = []

    def db(*b): buf.extend(b)
    def dd(v): buf.extend((v & 0xFFFFFFFF).to_bytes(4, 'little'))
    def call(t): db(0xE8); rel.append((len(buf), t)); dd(0)
    def lab(n): labels[n] = len(buf)
    def j8(op, n): db(op); jcc8.append((len(buf), n)); db(0)

    db(0x55)                              # push ebp
    db(0x8B, 0xEC)                        # mov ebp,esp
    db(0x81, 0xC4); dd(-LOCALS & 0xFFFFFFFF)   # add esp,-0x140
    db(0x53)                              # push ebx
    db(0x56)                              # push esi
    db(0x8B, 0xF0)                        # mov esi,eax        (original message)
    db(0x33, 0xC0)                        # xor eax,eax
    db(0x89, 0x45, 0x100 - O_STR)         # mov [ebp-4],eax    (init AnsiString = nil)
    call(base + len(buf) + 5)             # delta trick
    popva = base + len(buf)
    db(0x5B)                              # pop ebx
    db(0x81, 0xEB); dd(popva)             # sub ebx,static -> ebx = delta

    # 1) the original dialog, unchanged
    db(0x8B, 0xC6)                        # mov eax,esi
    call(F_SHOWMESSAGE)

    # 2) E := SysUtils.ExceptObject
    db(0x8B, 0x83); dd(IAT_EXC_CREATE)    # mov eax,[ebx+IAT]
    db(0x2D); dd(D_EXCOBJ)                # sub eax,0x308
    db(0xFF, 0xD0)                        # call eax
    db(0x85, 0xC0)                        # test eax,eax
    j8(0x74, 'done')
    db(0x50)                              # push eax           (save E)

    # 3) addr := SysUtils.ExceptAddr
    db(0x8B, 0x83); dd(IAT_EXC_CREATE)    # mov eax,[ebx+IAT]
    db(0x2D); dd(D_EXCADDR)               # sub eax,0x2E8
    db(0xFF, 0xD0)                        # call eax
    db(0x8B, 0xD0)                        # mov edx,eax        (edx = ExceptAddr)

    # 4) len := ExceptionErrorMessage(E, addr, buf, 250)
    db(0x8B, 0xB3); dd(IAT_EXC_CREATE)    # mov esi,[ebx+IAT]
    db(0x81, 0xEE); dd(D_EXCMSG)          # sub esi,0x2BC
    db(0x58)                              # pop eax            (eax = E)
    db(0x8D, 0x8D); dd(-O_BUF & 0xFFFFFFFF)    # lea ecx,[ebp-0x110]
    db(0x68); dd(BUFSZ)                   # push 250  (imm32: 6A would sign-extend!)
    db(0xFF, 0xD6)                        # call esi           (ret 4 -> callee cleans)

    # 5) PChar -> ShortString -> AnsiString -> ShowMessage
    db(0x3D); dd(BUFSZ)                   # cmp eax,250
    j8(0x76, 'fits')                      # jbe fits
    db(0xB8); dd(BUFSZ)                   # mov eax,250
    lab('fits')
    db(0x88, 0x85); dd(-O_LEN & 0xFFFFFFFF)    # mov [ebp-0x111],al
    db(0x8D, 0x95); dd(-O_LEN & 0xFFFFFFFF)    # lea edx,[ebp-0x111]
    db(0x8D, 0x45, 0x100 - O_STR)         # lea eax,[ebp-4]
    call(F_LSTRFROMSTRING)
    db(0x8B, 0x45, 0x100 - O_STR)         # mov eax,[ebp-4]
    call(F_SHOWMESSAGE)
    db(0x8D, 0x45, 0x100 - O_STR)         # lea eax,[ebp-4]
    call(F_LSTRCLR)

    lab('done')
    db(0x5E)                              # pop esi
    db(0x5B)                              # pop ebx
    db(0x8B, 0xE5)                        # mov esp,ebp
    db(0x5D)                              # pop ebp
    db(0xC3)                              # ret

    for off, tgt in rel:
        buf[off:off+4] = (tgt - (base + off + 4)).to_bytes(4, 'little', signed=True)
    for off, n in jcc8:
        dtl = labels[n] - (off + 1)
        assert -128 <= dtl <= 127, (n, dtl)
        buf[off] = dtl & 0xFF
    assert base + len(buf) <= CAVE_LIMIT, hex(len(buf))
    return bytes(buf)


def reloc_hits(data, ranges):
    e = struct.unpack_from('<I', data, 0x3C)[0]; opt = e + 24
    nsec = struct.unpack_from('<H', data, e + 6)[0]
    osz = struct.unpack_from('<H', data, e + 20)[0]
    rrva, rsz = struct.unpack_from('<II', data, opt + 96 + 5*8)
    secs = []; p = opt + osz
    for _ in range(nsec):
        vs, va, rs, raw = struct.unpack_from('<IIII', data, p + 8)
        secs.append((va, vs, raw, rs)); p += 40

    def r2o(rva):
        for va, vs, raw, rs in secs:
            if va <= rva < va + max(vs, rs):
                return raw + rva - va

    off = r2o(rrva)
    if off is None or rsz == 0:
        return []
    end = off + rsz; hits = []
    while off < end:
        page, blk = struct.unpack_from('<II', data, off)
        if blk < 8:
            break
        for i in range((blk - 8)//2):
            w = struct.unpack_from('<H', data, off + 8 + i*2)[0]
            if w >> 12 == 0:
                continue
            fo = r2o(page + (w & 0xFFF))
            if fo is None:
                continue
            for lo, hi in ranges:
                if lo <= fo + 3 and fo < hi:
                    hits.append(fo)
        off += blk
    return hits


def main():
    apply = "--apply" in sys.argv
    revert = "--revert" in sys.argv
    if revert:
        if os.path.exists(BAK):
            shutil.copy2(BAK, DLL)
            print("restored Network.dpl from", os.path.basename(BAK))
            return 0
        print("no backup found:", BAK)
        return 1

    d = bytearray(open(DLL, 'rb').read())
    cave = build_cave()
    h_off = H_SITE - VA2FILE
    c_off = CAVE_BASE - VA2FILE

    hits = reloc_hits(bytes(d), [(h_off, h_off + 5), (c_off, c_off + 0x1F0)])
    assert not hits, ["reloc in patch range: " + hex(x) for x in hits]

    cur = bytes(d[h_off:h_off+5])
    assert cur == H_OLD or cur[0] == 0xE8, "unexpected bytes at hook: " + cur.hex()

    d[c_off:c_off + 0x1F0] = bytes(0x1F0)          # wipe any previous version
    d[c_off:c_off+len(cave)] = cave
    d[h_off:h_off+5] = bytes([0xE8]) + (CAVE_BASE - (H_SITE + 5)).to_bytes(4, 'little', signed=True)

    print("cave v2 %d B @0x%X (limit 0x%X)" % (len(cave), CAVE_BASE, CAVE_LIMIT))
    print("hook: ShowMessage call @0x%X -> cave" % H_SITE)
    print("2nd dialog now reads: Exception <class> in module <mod> at <offset>. <msg>")
    print("  -> static VA = 0x55700000 + <offset>   (AoWEPACK)")
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
