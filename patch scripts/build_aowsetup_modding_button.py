r"""AoWSetup.exe: the home screen's "Editor" button becomes "Modding" and
launches the AoWxHub modding launcher (X\Modding\AoWxHub.exe) instead of
AoWDevX.exe directly.

Two one-dword site patches feed a tiny appended section '.xhub':

FIX A  Caption "Editor" -> "Modding".
   The DFM caption can't grow in place ("Modding" is one byte longer and the
   TLoaderForm DFM is offset-sensitive), so the caption is set at runtime:
   the class method table entry that binds the DFM's OnCreate=FormCreate
   (dword @file 0x677D2 -> 0x468A2C) is re-pointed to a wrapper that calls
   the original FormCreate, then TControl.SetText(form.StartAoWEdBtn
   [form+0x258], 'Modding'). Runs after FormCreate's own setup, so it wins
   over anything the original does to the button.

FIX B  Launch target.
   StartAoWEdBtnClick builds <installdir> + <string> and ShellExecutes it.
   The devtab patch (build_aowsetup_installcheck_devtab.py, FIX 3) already
   re-pointed the string const at VA 0x46894F from '\aowed.exe' to its
   '\AoWDevX.exe' @0x469980; this script re-points it again to
   '\X\Modding\AoWxHub.exe' in .xhub. (Chain note: re-applying the devtab
   patch reverts this dword to AoWDevX - re-run this script after it.)
   The existing Sleep(4000)+form.Close after the launch is kept: AoWSetup
   still closes, so the hub visually replaces the home window.

FIX C  Don't close AoWSetup when the launch FAILED (added 2026-08-30).
   The vanilla handler tail is unconditional:
       00468967  call GetHandle
       0046896f  call 0x467f24            ; jmp [0x46C710] = ShellExecuteA
       00468974  push 0xfa0               ; <-- 5-byte hook site
       00468979  call Sleep
       0046897e  mov eax,ebx / call TCustomForm.Close
       00468985  jmp 0x46899c             ; epilogue
   so a missing X\Modding\AoWxHub.exe silently closed AoWSetup anyway
   (ShellExecuteA returns 2, nobody checks). The push 0xfa0 becomes a jmp
   into a .xhub guard: EAX > 32 -> replicate push 0xfa0+Sleep+Close+jmp
   (bytes 0x468979..0x468985 become dead); else MessageBoxA (IAT 0x46C1A8)
   "hub not found - reinstall", then jmp to the epilogue WITHOUT closing.

Section '.xhub' @VA 0x512000 (0x1000 virtual / 0x200 raw, RWX; the exe is
fixed-base, absolute addresses safe; sits after mouse-tab's .xmou
@0x510000+0x2000, which must be applied first).

Usage:
    python build_aowsetup_modding_button.py            # dry run
    python build_aowsetup_modding_button.py --apply    # back up + patch
    python build_aowsetup_modding_button.py --revert   # restore backup
"""
import os
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.dirname(HERE)
EXE = os.path.join(GAME, "AoWSetup.exe")
BAK = EXE + ".bak_xhub"

CODE_D = 0x400C00              # VA - CODE_D = file offset (CODE section)

SEC_VA = 0x512000
SEC_RVA = SEC_VA - 0x400000
SEC_VSIZE = 0x1000
SEC_RAW = 0x200
SEC_NAME = b".xhub\x00\x00\x00"

FORMCREATE = 0x468A2C          # TLoaderForm.FormCreate
SETTEXT = 0x41CA24             # TControl.SetText (eax=ctrl, edx=chars ptr)
# form.StartAoWEdBtn. Field table entries are {offset:u32, classidx:u16,
# name:shortstring} - the offset dword PRECEDES the name (0x258 is
# SettingsBtn's; getting this wrong once retitled Settings to "Modding").
OFF_EDBTN = 0x254

# site 1: class method table dword binding OnCreate=FormCreate
MTBL_FILE = 0x677D2            # dword 0x468A2C
# site 2: mov edx,<exe-name string> in StartAoWEdBtnClick
EDMOV_VA = 0x46894F            # BA 80 99 46 00 after the devtab patch
DEVX_CHARS = 0x469980          # devtab's '\AoWDevX.exe' chars

# FIX C sites/targets (StartAoWEdBtnClick tail)
GUARD_VA = 0x468974            # push 0xfa0 (68 A0 0F 00 00) -> jmp cave
SLEEP_FN = 0x405948            # Windows.Sleep
CLOSE_FN = 0x42A6B4            # TCustomForm.Close
EPILOGUE = 0x46899C            # handler epilogue (inside the except frame)
MSGBOXA_IAT = 0x46C1A8         # user32!MessageBoxA IAT slot
SHELLEX_IAT = 0x46C710         # shell32!ShellExecuteA IAT slot
MB_YESNO_ICONQUESTION = 0x24   # MB_YESNO | MB_ICONQUESTION
IDYES = 6

HUB_PATH = b"\\X\\Modding\\AoWxSuite.exe"   # renamed from AoWxHub.exe 2026-09-01
CAPTION = b"Modding"
# A MessageBox cannot hyperlink a word, so the hub dialog's sentence is kept
# verbatim and "download" is made actionable via Yes/No -> browser.
# ⚠ keep TOOLS_URL in sync with AoWxHub.py's TOOLS_URL (link TBD, will change)
TOOLS_URL = b"https://aow.heavengames.com/downloads/lister.php?category=misc"
FAIL_TEXT = (b"AoWx modding tools not found. Please download and install."
             b"\r\n\r\nOpen the download page in your browser?")
FAIL_CAP = b"AoWSetup"


def build_section():
    blob = bytearray()

    def align4():
        while len(blob) % 4:
            blob.append(0)

    def astr(s):
        align4()
        blob.extend(struct.pack("<i", -1))          # refcount: constant
        blob.extend(struct.pack("<I", len(s)))
        chars_va = SEC_VA + len(blob)
        blob.extend(s + b"\x00")
        return chars_va

    def cstr(s):
        va = SEC_VA + len(blob)
        blob.extend(s + b"\x00")
        return va

    hub_chars = astr(HUB_PATH)
    cap_chars = astr(CAPTION)
    align4()
    wrapper_va = SEC_VA + len(blob)
    va = wrapper_va
    code = bytearray()
    code += b"\x50"                                                # push eax
    code += b"\xE8" + struct.pack("<i", FORMCREATE - (va + len(code) + 5))
    code += b"\x58"                                                # pop eax
    code += b"\x8B\x80" + struct.pack("<I", OFF_EDBTN)   # mov eax,[eax+0x254]
    code += b"\xBA" + struct.pack("<I", cap_chars)       # mov edx,caption
    code += b"\xE8" + struct.pack("<i", SETTEXT - (va + len(code) + 5))
    code += b"\xC3"                                                # ret
    blob.extend(code)

    # FIX C guard: plain C strings (WinAPI calls) + launch-result gate
    fail_txt = cstr(FAIL_TEXT)
    fail_cap = cstr(FAIL_CAP)
    url_c = cstr(TOOLS_URL)
    open_c = cstr(b"open")
    align4()
    guard_va = SEC_VA + len(blob)
    va = guard_va
    code = bytearray()
    code += b"\x83\xF8\x20"                              # cmp eax, 32
    code += b"\x7E\x16"                                  # jle fail (+0x16)
    code += b"\x68\xA0\x0F\x00\x00"                      # push 0xfa0 (displaced)
    code += b"\xE8" + struct.pack("<i", SLEEP_FN - (va + len(code) + 5))
    code += b"\x8B\xC3"                                  # mov eax, ebx (form)
    code += b"\xE8" + struct.pack("<i", CLOSE_FN - (va + len(code) + 5))
    code += b"\xE9" + struct.pack("<i", EPILOGUE - (va + len(code) + 5))
    assert len(code) == 5 + 0x16, len(code)              # jle target = here
    code += b"\x6A" + bytes([MB_YESNO_ICONQUESTION])     # push MB_YESNO|QUESTION
    code += b"\x68" + struct.pack("<I", fail_cap)        # push caption
    code += b"\x68" + struct.pack("<I", fail_txt)        # push text
    code += b"\x6A\x00"                                  # push hwnd 0
    code += b"\xFF\x15" + struct.pack("<I", MSGBOXA_IAT)  # call [MessageBoxA]
    code += b"\x83\xF8" + bytes([IDYES])                 # cmp eax, IDYES
    jne_at = len(code)
    code += b"\x75\x18"                                  # jne done (+0x18)
    code += b"\x6A\x01"                                  # push SW_SHOWNORMAL
    code += b"\x6A\x00"                                  # push dir NULL
    code += b"\x6A\x00"                                  # push params NULL
    code += b"\x68" + struct.pack("<I", url_c)           # push URL
    code += b"\x68" + struct.pack("<I", open_c)          # push 'open'
    code += b"\x6A\x00"                                  # push hwnd 0
    code += b"\xFF\x15" + struct.pack("<I", SHELLEX_IAT)  # call [ShellExecuteA]
    assert len(code) == jne_at + 2 + 0x18, len(code)     # jne target = here
    code += b"\xE9" + struct.pack("<i", EPILOGUE - (va + len(code) + 5))
    blob.extend(code)

    assert len(blob) <= SEC_RAW, len(blob)
    return bytes(blob), hub_chars, wrapper_va, guard_va


def main():
    apply = "--apply" in sys.argv
    if "--revert" in sys.argv:
        if not os.path.isfile(BAK):
            print("no backup to revert"); return 1
        shutil.copy2(BAK, EXE)
        print("reverted from", BAK)
        return 0

    d = bytearray(open(EXE, "rb").read())
    e = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, e + 6)[0]
    optsz = struct.unpack_from("<H", d, e + 20)[0]
    sec0 = e + 24 + optsz
    sizeofimage_off = e + 24 + 56

    names = [bytes(d[sec0 + 40 * i: sec0 + 40 * i + 8]).rstrip(b"\x00")
             for i in range(nsec)]
    if b".xmou" not in names:
        print("ABORT: .xmou missing - apply build_aowsetup_mouse_tab.py first")
        return 1
    already = b".xhub" in names

    blob, hub_chars, wrapper_va, guard_va = build_section()

    sites = [
        (MTBL_FILE, struct.pack("<I", FORMCREATE),
         struct.pack("<I", wrapper_va), "OnCreate binding -> caption wrapper"),
        (EDMOV_VA - CODE_D + 1, struct.pack("<I", DEVX_CHARS),
         struct.pack("<I", hub_chars), "launch string -> " + HUB_PATH.decode()),
        (GUARD_VA - CODE_D, b"\x68\xA0\x0F\x00\x00",
         b"\xE9" + struct.pack("<i", guard_va - (GUARD_VA + 5)),
         "Sleep+Close gated on ShellExecute success (FIX C)"),
    ]
    ok = True
    todo = []
    for off, old, new, desc in sites:
        cur = bytes(d[off:off + len(old)])
        # a jmp into .xhub whose displacement no longer matches is an OLDER
        # revision of this patch (the cave layout moved) - refresh it
        stale_jmp = (cur[0:1] == b"\xE9" and new[0:1] == b"\xE9" and
                     SEC_VA <= off + CODE_D + 5 +
                     struct.unpack("<i", cur[1:5])[0] < SEC_VA + SEC_VSIZE)
        # likewise a dword pointing into .xhub is an older cave layout
        stale_ptr = (len(cur) == 4 and new[0:1] != b"\xE9" and
                     SEC_VA <= struct.unpack("<I", cur)[0] < SEC_VA + SEC_VSIZE)
        if cur == old:
            todo.append((off, new, desc))
            print("site @file %#x: %s  (ready)" % (off, desc))
        elif cur == new:
            print("site @file %#x: %s  (already applied)" % (off, desc))
        elif stale_jmp or stale_ptr:
            todo.append((off, new, desc))
            print("site @file %#x: %s  (stale, refreshing)" % (off, desc))
        else:
            print("site @file %#x: UNEXPECTED bytes %s (want %s or %s)"
                  % (off, cur.hex(), old.hex(), new.hex()))
            ok = False
    if not ok:
        print("Aborting - is the devtab patch applied and the exe unmodified "
              "otherwise?")
        return 1

    print("section .xhub @%#x: %d bytes (wrapper @%#x, hub chars @%#x, "
          "guard @%#x)" % (SEC_VA, len(blob), wrapper_va, hub_chars, guard_va))
    if not apply:
        print("dry run - nothing written (use --apply)")
        return 0

    if not os.path.isfile(BAK):
        shutil.copy2(EXE, BAK)
        print("backed up to", BAK)

    if not already:
        img = struct.unpack_from("<I", d, sizeofimage_off)[0]
        assert img == SEC_RVA, ("SizeOfImage %#x != expected %#x - section "
                                "layout changed, re-derive SEC_VA" % (img, SEC_RVA))
        rawoff = len(d)
        hdr = sec0 + 40 * nsec
        assert all(b == 0 for b in d[hdr:hdr + 40]), "no room for section header"
        struct.pack_into("<8sIIIIIIHHI", d, hdr, SEC_NAME, SEC_VSIZE, SEC_RVA,
                         SEC_RAW, rawoff, 0, 0, 0, 0, 0xE00000E0)
        struct.pack_into("<H", d, e + 6, nsec + 1)
        struct.pack_into("<I", d, sizeofimage_off, SEC_RVA + SEC_VSIZE)
        d.extend(blob + bytes(SEC_RAW - len(blob)))
        print("appended .xhub raw @%#x, SizeOfImage -> %#x"
              % (rawoff, SEC_RVA + SEC_VSIZE))
    else:
        for i in range(nsec):
            if bytes(d[sec0 + 40 * i: sec0 + 40 * i + 8]).rstrip(b"\x00") == b".xhub":
                praw = struct.unpack_from("<I", d, sec0 + 40 * i + 20)[0]
                d[praw:praw + SEC_RAW] = blob + bytes(SEC_RAW - len(blob))
                print("refreshed .xhub content in place")

    for off, new, desc in todo:
        d[off:off + len(new)] = new
    open(EXE, "wb").write(d)
    print("APPLIED: Editor button -> 'Modding', launches " + HUB_PATH.decode())
    return 0


if __name__ == "__main__":
    sys.exit(main())
