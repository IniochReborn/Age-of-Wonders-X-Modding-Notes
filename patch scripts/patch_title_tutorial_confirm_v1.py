"""Title menu: "Start Tutorial?" Yes/No confirmation before the tutorial starts (2026-10-18).

User: clicking Tutorial on the title menu should first show a popup in the same style as the mid-game
'save before quitting?' dialog, but with two buttons: text "Start Tutorial?", left "Yes" (starts the
tutorial), right "No" (closes the popup, back to the title screen).

RE (AoWx.exe, never rebases - DllCharacteristics 0, no ASLR):
  * Title buttons: TTitleScene.WindowMouseUp 0x41AE94 -> hit test 0x419488 -> `jmp [eax*4+0x41AEE1]`
    (5-entry table, eax = button index, ebx = TTitleScene): 0 0x41AEF5, 1 0x41AF20, 2 0x41AF60 = TUTORIAL
    (LStrCatN([0x45df74]+0x2c, 'Scenario\\Custom\\', 'TUTORIAL.HSM') -> [[0x45a420]] call 0x454B70; if map
    [[0x45df7c]] != nil: map+0x148 := 1, call 0x454D2C, hide title window [ebx+0x48]), 3 0x41AFC4, 4 0x41AFF4.
    All exits go to 0x41B033.
  * The mid-game save prompt is the shared TMessageDlg form (global [0x45a1a0]) = the same window every
    TMessageEventLog uses (TMessageDlg.Execute 0x40E89C); its button set byte 3 = YesNoCancelPnl. The form
    also has YesNoPnl (field +0x4C, Yes/No buttons, DFM Text 'Yes'/'No', translated) -> that is our 2-button
    look. Fields: +0x44 Dlg window, +0x48 TitleLbl, +0x4C YesNoPnl, +0x80 MessageMemo (+0x118 = Lines),
    +0xB0/+0xB4 OnClose TMethod, +0xB8 the message object. YesBtnClick 0x40EA14 / NoBtnClick 0x40EA38 call
    [obj]+0x80 / +0x84 and hide Dlg when they return al != 0; DlgHide -> 0x40E780 clears +0xB0..+0xB8 and
    calls [obj]+0x2C (release). Reset = 0x40E7E4 (hides all button panels, clears the memo, TitleLbl :=
    MessageRStr). Short texts are padded with one blank line on top (Execute style 0: Lines.SetTextStr
    +0x2C, Insert(0,'') +0x54 when length < 0x50) - copied here.
Patch:
  * new section .xtut @VA 0x634000 (RWX, 0x1000 virtual, 0x400 raw) - ⚠ uses the LAST free section-header
    slot of AoWx.exe (table now ends exactly at 0x400 = CODE raw).
  * the 5 jump-table entries 0x41AEE1.. -> DISPATCH: while OUR dialog is open (dlg+0xB8 == our object) every
    title click is ignored (-> 0x41B033); otherwise button 2 -> SHOW, the rest -> their original targets
    (kept in .xtut). SHOW fills the MessageDlg like Execute would (title = TutorialRStr, memo
    'Start Tutorial?', YesNoPnl, a static fake message object whose VMT +0x80 Yes sets a flag, +0x84 No /
    +0x78 OK / +0x7C Cancel just close, everything else returns 0) and shows Dlg. If the dialog is busy
    with another message the click is ignored; if the MessageDlg form does not exist the vanilla tutorial
    code runs directly.
  * Yes does NOT start the tutorial inside the button handler (a tutorial message shown during the load
    would land in the same dialog and get closed by YesBtnClick's Hide); the flag is consumed by
    TTitleScene.WindowUpdate on the next frame: its published-method-table entry (dword @0x4193DA, was
    0x41AE08) -> UPD wrapper = original WindowUpdate, then (flag) the vanilla tutorial sequence verbatim
    (same literals 0x41B068/0x41B084, same calls) with ebx = the title scene.
  The table entries and the method-table dword are absolute pointers with .reloc entries; they are
  replaced by other in-image absolute pointers (still correct under any rebase; the exe never rebases).

Usage: py -3.10 patch_title_tutorial_confirm_v1.py [--apply | --revert] [--exe PATH]   (dry-run default)
Backup: backup\\AoWx.exe.bak_tutconfirm.  Revert removes .xtut while it is the last section (else zeroes
it) and restores the 6 dwords.  Apply AFTER patch_hexgrid_option_v1.py (it appends .xhgr and asserts
SizeOfImage == 0x230000 when appending); revert this one first.
"""
import os
import shutil
import struct
import sys

from keystone import Ks, KS_ARCH_X86, KS_MODE_32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_dir  # noqa: E402

BASE = 0x400000
SEC_NAME, SEC_VA, SEC_VSIZE, SEC_RAW = b".xtut", 0x634000, 0x1000, 0x400
MAGIC = b"TUT1"

JT_VA = 0x41AEE1
JT_ORIG = [0x41AEF5, 0x41AF20, 0x41AF60, 0x41AFC4, 0x41AFF4]
MT_VA, MT_ORIG = 0x4193DA, 0x41AE08          # TTitleScene method table: WindowUpdate code pointer

# .xtut layout
G_GO = SEC_VA + 0x04          # byte: Yes was clicked, start the tutorial on the next WindowUpdate
G_S1 = SEC_VA + 0x08          # AnsiString temps (LStrArrayClr'd together)
G_S2 = SEC_VA + 0x0C
VMT = SEC_VA + 0x60           # fake VMT (negative area 0x634014..0x63405F stays zero: parent nil, etc.)
NSLOTS = 0x24                 # slots +0x00 .. +0x8C
FAKEOBJ = SEC_VA + 0x100      # dword VMT + zero fields
ORIGTBL = SEC_VA + 0x120
STRLIT = SEC_VA + 0x148       # AnsiString literal chars (header at -8: refcount -1, length)
TEXT = b"Start Tutorial?"
CODE = SEC_VA + 0x180

ASM = """
disp:
    mov ecx, dword ptr [0x45a1a0]
    mov ecx, dword ptr [ecx]
    test ecx, ecx
    je pass
    cmp dword ptr [ecx + 0xb8], {FAKEOBJ:#x}
    je ignore
pass:
    cmp eax, 2
    je show
    jmp dword ptr [eax*4 + {ORIGTBL:#x}]
ignore:
    jmp 0x41b033
show:
    mov esi, ecx
    test esi, esi
    je orig2
    cmp dword ptr [esi + 0xb8], 0
    jne ignore
    mov eax, esi
    call 0x40e7e4
    mov eax, dword ptr [0x45e184]
    mov edx, {G_S1:#x}
    call 0x401180
    mov eax, dword ptr [{G_S1:#x}]
    mov edx, {G_S2:#x}
    call 0x4021e4
    mov edx, dword ptr [{G_S2:#x}]
    mov eax, dword ptr [esi + 0x48]
    call 0x403254
    mov eax, dword ptr [esi + 0x80]
    mov eax, dword ptr [eax + 0x118]
    mov edx, {STRLIT:#x}
    mov ecx, dword ptr [eax]
    call dword ptr [ecx + 0x2c]
    mov eax, dword ptr [esi + 0x80]
    mov eax, dword ptr [eax + 0x118]
    mov ecx, dword ptr [eax]
    push dword ptr [ecx + 0x54]
    xor ecx, ecx
    xor edx, edx
    call dword ptr [esp]
    pop ecx
    mov dl, 1
    mov eax, dword ptr [esi + 0x4c]
    mov ecx, dword ptr [eax]
    call dword ptr [ecx + 0x6c]
    xor eax, eax
    mov dword ptr [esi + 0xb0], eax
    mov dword ptr [esi + 0xb4], eax
    mov dword ptr [esi + 0xb8], {FAKEOBJ:#x}
    mov dl, 1
    mov eax, dword ptr [esi + 0x44]
    mov ecx, dword ptr [eax]
    call dword ptr [ecx + 0x6c]
    mov eax, {G_S1:#x}
    mov edx, 0x2
    call 0x4010e0
    jmp 0x41b033
orig2:
    jmp 0x41af60
yes:
    mov byte ptr [{G_GO:#x}], 1
close:
    mov al, 1
    ret
ret0:
    xor eax, eax
    ret
upd:
    push ebx
    mov ebx, eax
    call 0x41ae08
    cmp byte ptr [{G_GO:#x}], 0
    je uout
    mov byte ptr [{G_GO:#x}], 0
    mov eax, dword ptr [0x45df74]
    mov eax, dword ptr [eax]
    push dword ptr [eax + 0x2c]
    push 0x41b068
    push 0x41b084
    mov eax, {G_S1:#x}
    mov edx, 0x3
    call 0x401128
    mov edx, dword ptr [{G_S1:#x}]
    mov eax, dword ptr [0x45a420]
    mov eax, dword ptr [eax]
    call 0x454b70
    mov eax, dword ptr [0x45df7c]
    cmp dword ptr [eax], 0
    je udone
    mov eax, dword ptr [eax]
    mov byte ptr [eax + 0x148], 1
    mov eax, dword ptr [0x45a420]
    mov eax, dword ptr [eax]
    call 0x454d2c
    xor edx, edx
    mov eax, dword ptr [ebx + 0x48]
    mov ecx, dword ptr [eax]
    call dword ptr [ecx + 0x6c]
udone:
    mov eax, {G_S1:#x}
    call 0x4010d8
uout:
    pop ebx
    ret
"""


def assemble():
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    src = ASM.format(FAKEOBJ=FAKEOBJ, ORIGTBL=ORIGTBL, G_S1=G_S1, G_S2=G_S2, G_GO=G_GO, STRLIT=STRLIT)
    labels = ["disp", "show", "yes", "close", "ret0", "upd", "ignore", "orig2"]
    # label addresses: append a probe `mov eax, label` per label (keystone gotcha: keep labels in one text)
    probe = "".join("\n    mov eax, %s" % l for l in labels)
    enc, _ = ks.asm(src + probe, CODE)
    enc = bytes(enc)
    body = enc[:len(enc) - 5 * len(labels)]
    addr = {}
    for k, l in enumerate(labels):
        p = enc[len(body) + 5 * k:len(body) + 5 * k + 5]
        assert p[0] == 0xB8
        addr[l] = struct.unpack_from("<I", p, 1)[0]
    # sanity: re-assemble the body alone must give identical bytes
    body2 = bytes(ks.asm(src, CODE)[0])
    assert body2 == body, "keystone label drift"
    return body, addr


def build_blob():
    code, a = assemble()
    blob = bytearray(SEC_RAW)
    blob[0:4] = MAGIC
    slots = [a["ret0"]] * NSLOTS
    slots[0x2C // 4] = a["ret0"]       # release
    slots[0x78 // 4] = a["close"]      # OK
    slots[0x7C // 4] = a["close"]      # Cancel
    slots[0x80 // 4] = a["yes"]        # Yes
    slots[0x84 // 4] = a["close"]      # No
    o = VMT - SEC_VA
    for i, s in enumerate(slots):
        struct.pack_into("<I", blob, o + 4 * i, s)
    assert o + 4 * NSLOTS <= FAKEOBJ - SEC_VA
    struct.pack_into("<I", blob, FAKEOBJ - SEC_VA, VMT)
    for i, t in enumerate(JT_ORIG):
        struct.pack_into("<I", blob, ORIGTBL - SEC_VA + 4 * i, t)
    so = STRLIT - SEC_VA
    struct.pack_into("<iI", blob, so - 8, -1, len(TEXT))
    blob[so:so + len(TEXT)] = TEXT
    assert so + len(TEXT) < CODE - SEC_VA
    co = CODE - SEC_VA
    assert co + len(code) <= SEC_RAW
    blob[co:co + len(code)] = code
    return bytes(blob), a, code


def sections(d):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    n = struct.unpack_from("<H", d, e + 6)[0]
    opt = struct.unpack_from("<H", d, e + 20)[0]
    tbl = e + 24 + opt
    secs = []
    for i in range(n):
        h = tbl + 40 * i
        name = bytes(d[h:h + 8]).rstrip(b"\0")
        vsz, va, rsz, raw = struct.unpack_from("<IIII", d, h + 8)
        secs.append(dict(name=name, vsz=vsz, va=BASE + va, rsz=rsz, raw=raw, hdr=h))
    return e, n, tbl, secs


def off(secs, va):
    for s in secs:
        if s["va"] <= va < s["va"] + max(s["vsz"], s["rsz"]) and va - s["va"] < s["rsz"]:
            return s["raw"] + va - s["va"]
    raise ValueError(hex(va))


def main():
    args = sys.argv[1:]
    mode = "apply" if "--apply" in args else "revert" if "--revert" in args else "dry"
    exe = args[args.index("--exe") + 1] if "--exe" in args else os.path.join(game_dir(), "AoWx.exe")
    d = bytearray(open(exe, "rb").read())
    blob, a, code = build_blob()
    e, n, tbl, secs = sections(d)
    sec = next((s for s in secs if s["name"] == SEC_NAME), None)

    jt_o = off(secs, JT_VA)
    mt_o = off(secs, MT_VA)
    jt_now = list(struct.unpack_from("<5I", d, jt_o))
    mt_now = struct.unpack_from("<I", d, mt_o)[0]
    jt_state = "vanilla" if jt_now == JT_ORIG else "ours" if jt_now == [a["disp"]] * 5 else None
    mt_state = "vanilla" if mt_now == MT_ORIG else "ours" if mt_now == a["upd"] else None
    sec_state = "absent" if sec is None else "ours" if bytes(d[sec["raw"]:sec["raw"] + len(blob)]) == blob else \
        "zero" if not any(d[sec["raw"]:sec["raw"] + sec["rsz"]]) else None
    print("%s\n  jump table @%#x: %s | WindowUpdate method ptr @%#x: %s | .xtut: %s | code %d B @%#x "
          "(disp %#x upd %#x)" % (exe, JT_VA, jt_state, MT_VA, mt_state, sec_state, len(code), CODE,
                                  a["disp"], a["upd"]))
    if None in (jt_state, mt_state, sec_state):
        print("UNEXPECTED STATE - jt %s mt %#x - refusing" % ([hex(x) for x in jt_now], mt_now))
        return 1
    applied = jt_state == mt_state == sec_state == "ours"
    vanilla = jt_state == mt_state == "vanilla" and sec_state in ("absent", "zero")
    if mode == "dry":
        print("ALREADY APPLIED" if applied else "dry-run OK (vanilla) - run with --apply" if vanilla else "PARTIAL")
        return 0
    bak = bak_path(exe, ".bak_tutconfirm")
    if mode == "apply":
        if applied:
            print("ALREADY APPLIED")
            return 0
        if not vanilla:
            print("PARTIAL state - revert first")
            return 1
        if not os.path.exists(bak):
            shutil.copy2(exe, bak)
            print("backup ->", bak)
        if sec is None:
            assert tbl + 40 * (n + 1) <= min(s["raw"] for s in secs if s["rsz"]), "no room for a section header"
            soi = struct.unpack_from("<I", d, e + 24 + 56)[0]
            assert soi == SEC_VA - BASE, "SizeOfImage %#x != %#x (another section was appended?)" % (soi, SEC_VA - BASE)
            assert len(d) == secs[-1]["raw"] + secs[-1]["rsz"], "file has an overlay - refusing"
            d += bytes((-len(d)) % 0x200)
            raw = len(d)
            d += blob
            hdr = SEC_NAME.ljust(8, b"\0") + struct.pack("<IIIIIIHHI", SEC_VSIZE, SEC_VA - BASE, SEC_RAW, raw,
                                                         0, 0, 0, 0, 0xE0000060)
            d[tbl + 40 * n:tbl + 40 * n + 40] = hdr
            struct.pack_into("<H", d, e + 6, n + 1)
            struct.pack_into("<I", d, e + 24 + 56, SEC_VA - BASE + SEC_VSIZE)
            print("appended .xtut raw @%#x (%#x B); section table now full" % (raw, SEC_RAW))
        else:
            d[sec["raw"]:sec["raw"] + len(blob)] = blob
            print("refreshed .xtut")
        secs = sections(d)[3]
        struct.pack_into("<5I", d, off(secs, JT_VA), *([a["disp"]] * 5))
        struct.pack_into("<I", d, off(secs, MT_VA), a["upd"])
        open(exe, "wb").write(d)
        print("APPLIED: title Tutorial button -> 'Start Tutorial?' Yes/No")
        return 0
    # revert
    if vanilla and sec is None:
        print("ALREADY VANILLA")
        return 0
    struct.pack_into("<5I", d, jt_o, *JT_ORIG)
    struct.pack_into("<I", d, mt_o, MT_ORIG)
    if sec is not None:
        if secs[-1]["name"] == SEC_NAME:
            del d[sec["raw"]:]
            d[sec["hdr"]:sec["hdr"] + 40] = bytes(40)
            struct.pack_into("<H", d, e + 6, n - 1)
            struct.pack_into("<I", d, e + 24 + 56, SEC_VA - BASE)
            print("removed .xtut (last section)")
        else:
            d[sec["raw"]:sec["raw"] + sec["rsz"]] = bytes(sec["rsz"])
            print(".xtut is not the last section - body zeroed, header kept")
    open(exe, "wb").write(d)
    print("REVERTED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
