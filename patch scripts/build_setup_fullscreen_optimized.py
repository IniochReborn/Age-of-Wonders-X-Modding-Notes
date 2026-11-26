#!/usr/bin/env python3
r"""FEATURE: add "Fullscreen (Optimized)" to AoWSetup.exe's video mode list,
matching the entry the game itself offers.

BACKGROUND
    On Windows 8+ there are no 16bpp display modes, so AoW's DirectDraw
    enumeration returns nothing and AoWSetup's video list collapses to the
    single DFM item "Window". The game gained a "Fullscreen (Optimized)" entry
    (build_borderless_fullscreen.py) which renders at windowed size and
    stretches to fill the screen; it is selected by Video\Display Mode = 2.
    AoWSetup could not offer it, so the launcher and the game disagreed.
    ⚠ REQUIRES build_setup_registry_isolation.py - without it AoWSetup writes
    the vanilla registry key and nothing it saves reaches the mod.

HOW AoWSetup's VIDEO LIST WORKS (all RE'd 2026-08-12)
    Form TLoaderForm: +0x1FC = VideoModes combobox, +0x288 = TDisplayModeList.
    Settings object = [0x46BA34]; SetDisplayMode 0x467358, SetScreenWidth
    0x4673E0, SetScreenHeight 0x467468, GetDisplayMode 0x467310.
    ComboBox GetItemIndex 0x433564 (CB_GETCURSEL), SetItemIndex 0x433580
    (CB_SETCURSEL). TStrings vcalls: +0x18 GetObject, +0x38 AddObject.
    - FormCreate (~0x468BF8+) builds the mode list, calls SetItemIndex(0), then
      appends one "WxH" item per enumerated mode with Object = mode index.
    - SettingsOkBtnClick 0x469090: `GetItemIndex > 0` ? fullscreen (mode 1 +
      that mode's w/h) : windowed (mode 0 + 640x480).
    - The finder 0x468E54 (run each time Settings opens) restores the selection:
      if GetDisplayMode() != 0 it walks the items, mapping each item's Object
      through TDisplayModeList.GetItem and comparing w/h.
    ⚠ GetItem @0x44386C range-checks with x86 `BOUND` (0..0x07FFFFFE), so a
      NEGATIVE Object raises a range-check error - our sentinel must never
      reach it (see hook D).

THE PATCH (4 hooks + a cave; AoWSetup.exe has no ASLR so absolute refs are fine)
    Cave @0x469810 = trailing zero padding of CODE (437 B free from 0x46980B).
    Data: STR = Delphi -1-refcount AnsiString "Fullscreen (Optimized)";
          MYIDX = the combobox index our item landed at.
    A) FormCreate 0x468C26 `call SetItemIndex` -> CAVE_ADD: performs the
       original SetItemIndex(0), then AddObject(STR, Object = -2) and stores
       the returned index in MYIDX. Our entry therefore sits directly after
       "Window" and before the (usually empty) resolution list.
    B) SettingsOkBtnClick 0x4691EB `test eax,eax / jg` -> CAVE_SAVE: looks up
       the selected item's Object; -2 -> SetDisplayMode(2) + 640x480 (mirroring
       the windowed branch, since the game keeps its own render size in
       General\rectangles\100) then jumps to the shared tail 0x4692C3;
       otherwise reproduces the original test/branch exactly.
    C) Finder 0x468E86 `call GetDisplayMode` -> CAVE_FIND: on mode 2 it selects
       MYIDX and returns 0, which makes the caller's `test/je` skip the
       resolution search entirely; any other mode is passed through unchanged.
    D) Finder 0x468ED3 (`mov edx,edi / mov eax,[ebx+0x288]`) -> CAVE_SKIP:
       skips items whose Object is negative (i.e. ours) before GetItem is
       reached, so the mode-1 search cannot hit the BOUND range check.

    Backup: AoWSetup.exe.bak_fsopt. Dry-run default; --apply / --revert.
"""
import os, shutil, struct, sys

GAME = os.environ.get("AOW_GAME_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
EXE = os.path.join(GAME, "AoWSetup.exe")
BAK = EXE + ".bak_fsopt"

VA2FILE = 0x400C00
CAVE_BASE, CAVE_LIMIT = 0x469810, 0x4699C0
# Writable scratch: BSS is READ|WRITE, spans VA 0x46B000..0x46BA39 (vsize) and
# its page runs to 0x46C000, so the tail is mapped, zero-filled and unused
# (highest BSS address referenced anywhere in the file is 0x46BA34).
BSS_MYIDX = 0x46BB00
BSS_LO, BSS_HI = 0x46BA39, 0x46C000

LABEL = b"Fullscreen (Optimized)"
SENTINEL = 0xFFFFFFFE                      # -2

F_SETITEMINDEX = 0x433580
F_GETDISPLAYMODE = 0x467310
F_SETDISPLAYMODE = 0x467358
F_SETSCRW = 0x4673E0
F_SETSCRH = 0x467468
G_SETTINGS = 0x46BA34
OFF_COMBO = 0x1FC
OFF_ITEMS = 0x118
OFF_MODELIST = 0x288

F_GETITEMINDEX = 0x433564

H_ADD = 0x468C26                            # call SetItemIndex(0) in FormCreate
H_ADD_OLD = bytes.fromhex("e855a9fcff")
# ⚠ the `jg` after this call is a SHORT jump (85 C0 7F 2F = 4 bytes total), too
# small to detour - so hook the GetItemIndex call just before it instead.
H_SAVE = 0x4691E6                           # call GetItemIndex
H_SAVE_OLD = bytes.fromhex("e879a3fcff")
SAVE_DONE = 0x4692C3                        # shared tail (what the windowed branch jumps to)
H_FIND = 0x468E86                           # call GetDisplayMode in the finder
H_FIND_OLD = bytes.fromhex("e885e4ffff")
H_SKIP = 0x468ED3                           # mov edx,edi / mov eax,[ebx+288]
H_SKIP_OLD = bytes.fromhex("8bd78b8388020000")
SKIP_RESUME = 0x468EDB                      # the original call GetItem
SKIP_NEXT = 0x468F1B                        # loop continue (inc [ebp-4])


def build():
    """returns (cave_bytes, {hook_va: patch_bytes})"""
    assert BSS_LO <= BSS_MYIDX < BSS_HI - 4, "scratch outside the writable BSS page tail"
    base = CAVE_BASE
    buf = bytearray()
    lbl = {}
    fix = []                                 # (offset_in_buf, label, kind)

    def db(*b): buf.extend(b)
    def dd(v): buf.extend((v & 0xFFFFFFFF).to_bytes(4, 'little'))
    def here(): return base + len(buf)
    def call_abs(t): db(0xE8); dd((t - (here() + 4)) & 0xFFFFFFFF)
    def jmp_abs(t): db(0xE9); dd((t - (here() + 4)) & 0xFFFFFFFF)
    def mark(name): lbl[name] = here()
    def j8(op, name):
        db(op); fix.append((len(buf), name)); db(0)

    # ---------- data ----------
    dd(0xFFFFFFFF)                           # refcount -1
    dd(len(LABEL))                           # length
    STR = here()
    buf.extend(LABEL); db(0)
    while len(buf) % 4:
        db(0)
    # ⚠ MYIDX must NOT live in the cave: AoWSetup.exe's CODE section is
    # READ|EXECUTE only (chars 0x60000020) - unlike AoWx.exe's custom .xbfs
    # section, which was made RWX precisely so it could hold patch state.
    # Writing to the cave access-violates. Use zero-filled BSS tail instead.
    MYIDX = BSS_MYIDX

    # ---------- A: add the item ----------
    mark('add')
    db(0x50)                                 # push eax            (combobox)
    call_abs(F_SETITEMINDEX)                 # original SetItemIndex(0)
    db(0x58)                                 # pop eax
    db(0x53)                                 # push ebx
    db(0x8B, 0x80); dd(OFF_ITEMS)            # mov eax,[eax+0x118] (TStrings)
    db(0xBA); dd(STR)                        # mov edx, STR
    db(0xB9); dd(SENTINEL)                   # mov ecx, -2
    db(0x8B, 0x18)                           # mov ebx,[eax]
    db(0xFF, 0x53, 0x38)                     # call [ebx+0x38]     AddObject -> eax
    db(0xA3); dd(MYIDX)                      # mov [MYIDX],eax
    db(0x5B)                                 # pop ebx
    db(0xC3)

    # ---------- B: save ----------
    # Replaces `call GetItemIndex`; must still RETURN the index in eax so the
    # caller's own `test eax,eax / jg` behaves exactly as before.
    mark('save')                             # eax = the VideoModes combobox
    db(0x50)                                 # push eax            (combobox)
    call_abs(F_GETITEMINDEX)                 # eax = ItemIndex
    db(0x59)                                 # pop ecx             (combobox)
    db(0x50)                                 # push eax            (save index)
    db(0x8B, 0xD0)                           # mov edx,eax         (index)
    db(0x8B, 0x81); dd(OFF_ITEMS)            # mov eax,[ecx+0x118] (TStrings)
    db(0x8B, 0x08)                           # mov ecx,[eax]
    db(0xFF, 0x51, 0x18)                     # call [ecx+0x18]     GetObject
    db(0x83, 0xF8, 0xFE)                     # cmp eax,-2
    db(0x58)                                 # pop eax             (index; POP keeps flags)
    j8(0x74, 'borderless')
    db(0xC3)                                 # ret -> original path, unchanged
    mark('borderless')
    db(0x83, 0xC4, 0x04)                     # add esp,4  (drop our return address so the
                                             # stack matches the windowed branch)
    db(0xBA); dd(2)                          # mov edx,2
    db(0xA1); dd(G_SETTINGS)                 # mov eax,[settings]
    call_abs(F_SETDISPLAYMODE)
    db(0xBA); dd(640)
    db(0xA1); dd(G_SETTINGS)
    call_abs(F_SETSCRW)
    db(0xBA); dd(480)
    db(0xA1); dd(G_SETTINGS)
    call_abs(F_SETSCRH)
    jmp_abs(SAVE_DONE)

    # ---------- C: restore selection ----------
    mark('find')                             # ebx = form
    call_abs(F_GETDISPLAYMODE)
    db(0x83, 0xF8, 0x02)                     # cmp eax,2
    j8(0x75, 'find_out')
    db(0x8B, 0x15); dd(MYIDX)                # mov edx,[MYIDX]
    db(0x8B, 0x83); dd(OFF_COMBO)            # mov eax,[ebx+0x1FC]
    call_abs(F_SETITEMINDEX)
    db(0x33, 0xC0)                           # xor eax,eax   -> caller skips the search
    mark('find_out')
    db(0xC3)

    # ---------- D: skip our item during the mode-1 search ----------
    mark('skip')                             # edi = Object, ebx = form
    db(0x85, 0xFF)                           # test edi,edi
    j8(0x78, 'skip_next')                    # js -> negative == ours
    db(0x8B, 0xD7)                           # mov edx,edi
    db(0x8B, 0x83); dd(OFF_MODELIST)         # mov eax,[ebx+0x288]
    jmp_abs(SKIP_RESUME)
    mark('skip_next')
    jmp_abs(SKIP_NEXT)

    for off, name in fix:
        d = lbl[name] - (base + off + 1)
        assert -128 <= d <= 127, (name, d)
        buf[off] = d & 0xFF
    assert base + len(buf) <= CAVE_LIMIT, "cave overflow: %d" % len(buf)

    def rel32(src_end, dst):
        return (dst - src_end).to_bytes(4, 'little', signed=True)

    patches = {
        H_ADD:  b"\xE8" + rel32(H_ADD + 5, lbl['add']),
        H_SAVE: b"\xE8" + rel32(H_SAVE + 5, lbl['save']),
        H_FIND: b"\xE8" + rel32(H_FIND + 5, lbl['find']),
        H_SKIP: b"\xE9" + rel32(H_SKIP + 5, lbl['skip']) + b"\x90" * 3,
    }
    return bytes(buf), patches


def main():
    apply = "--apply" in sys.argv
    revert = "--revert" in sys.argv
    if revert:
        if os.path.exists(BAK):
            shutil.copy2(BAK, EXE)
            print("restored AoWSetup.exe from", os.path.basename(BAK))
            return 0
        print("no backup found:", BAK)
        return 1

    d = bytearray(open(EXE, 'rb').read())
    # prerequisite check
    assert bytes(d[0x066480:0x066480 + 43]).endswith(b"Age of Wonders X" + bytes([0x5C])), \
        "run build_setup_registry_isolation.py first (AoWSetup still uses the vanilla key)"

    cave, patches = build()
    c_off = CAVE_BASE - VA2FILE
    cur = bytes(d[c_off:c_off + len(cave)])
    assert cur == bytes(len(cave)) or cur[:4] == cave[:4], "cave not free: " + cur[:8].hex()

    for va, old in ((H_ADD, H_ADD_OLD), (H_SAVE, H_SAVE_OLD),
                    (H_FIND, H_FIND_OLD), (H_SKIP, H_SKIP_OLD)):
        o = va - VA2FILE
        got = bytes(d[o:o + len(old)])
        assert got == old or got[0] in (0xE8, 0xE9), \
            "unexpected bytes at VA 0x%X: %s (expected %s)" % (va, got.hex(), old.hex())

    d[c_off:c_off + len(cave)] = cave
    for va, blob in patches.items():
        o = va - VA2FILE
        d[o:o + len(blob)] = blob

    print("cave %d B @0x%X (limit 0x%X)" % (len(cave), CAVE_BASE, CAVE_LIMIT))
    for va in sorted(patches):
        print("  hook VA 0x%X -> %s" % (va, patches[va][:5].hex()))
    print('adds "%s" to the video list (Display Mode 2)' % LABEL.decode())
    if not apply:
        print("Dry run OK - rerun with --apply (or --revert).")
        return 0
    if not os.path.exists(BAK):
        shutil.copy2(EXE, BAK)
        print("Backup ->", os.path.basename(BAK))
    open(EXE, 'wb').write(d)
    print("Written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
