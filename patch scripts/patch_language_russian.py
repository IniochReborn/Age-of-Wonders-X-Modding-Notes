"""
patch_language_russian.py - make Russian selectable as a 7th language.

The engine stores the language choice in HKCU\\...\\General\\Language (0=Auto,
1=English, 2=German, 3=French, 4=Spanish, 5=Italian) and dispatches it through
`and eax,7F / cmp eax,5 / ja default / jmp [table+eax*4]` switches. Value 6
(Russian) currently falls into every default. This patch:

* AoWx.exe        - main SetLanguage switch (dict @0x45B2BC, thunk 0x4020E4):
                    cmp 5->6, 7-entry table + case-6 stub in a NEW appended
                    .xlng section (VA 0x60F000). Plus the language behavior
                    switch @0x4091E5: case 6 -> the English case.
* AoWEPACK.dll    - two SetLanguage switches (TIvDictionary.SetLanguage import)
                    and five per-language word/grammar switches whose defaults
                    return empty strings; case 6 -> English case so generated
                    text stays translatable via TranslateRStr. Caves in the
                    verified-free CODE tail at 0x55812C80+ (below the 0x55812E00
                    diag reserve).
* AoWSetup.exe    - three SetLanguage switches (statically linked SetLanguage
                    @0x44BA20), caves in a NEW appended .xlng section
                    (VA 0x512000); plus the Settings dialog DFM:
                    "Russian" added to LanguageCB's Items.Strings, compensated
                    by dropping the combo's ItemHeight property (13 bytes freed,
                    9 used, 4 zero-padded at stream end) so the resource size
                    and every following offset stay untouched.
* AoWEd.exe       - untouched: it forces language 1 for every case already,
                    and value 6 falls to its default harmlessly.

The five behavior switches' English-case routing matters because their defaults
return NIL strings - Russian would otherwise get empty grammar words in
generated text.

Prerequisite: the Dict\\*.mld files must already carry the Russian column
(patch_dict_russian.py) - the new case calls SetLanguage(6), which needs
language index 6 to exist. --apply refuses to run without it.

Assumption (house precedent): AoWEPACK.dll loads at its preferred base
0x55700000; the relocated tables hold absolute VAs without new .reloc entries,
exactly like every existing cave patch in that DLL.

⚠ Why dedicated sections and not slack in .xbfs/.xmou: those sections' blobs
END with zero-initialized runtime buffers (the mouse tab's pathbuf alone is
260 zero bytes) that look exactly like free space in the file. The first
version of this patch put its jump tables there and GetModuleFileNameA
overwrote them the moment Settings opened - access violations on every
language action. Never allocate caves in a blob-owned section by scanning for
zeros; append a section or use a documented cave map.

    python patch_language_russian.py            dry run
    python patch_language_russian.py --apply    back up + patch all three
    python patch_language_russian.py --revert   restore the .bak_ru7 backups
"""
import os, struct, sys, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.abspath(os.path.join(HERE, ".."))

for cand in (os.path.join(GAME, "modding tools"),):
    if cand not in sys.path:
        sys.path.insert(0, cand)
from aowxlib.mld import MLDFile                                      # noqa: E402


def u32(v):
    return struct.pack("<I", v & 0xFFFFFFFF)


def rel32(target, next_ip):
    return struct.pack("<i", target - next_ip)


# ---------------------------------------------------------------------------
# patch builders - every entry is (file_offset, expected_old, new_bytes)
# ---------------------------------------------------------------------------
# new-section geometry: (raw file offset, VA) of each exe's .xlng section
XLNG_AOWX = (0x20A600, 0x60F000)      # appended at old EOF, RVA 0x20F000
XLNG_SETUP = (0x10C200, 0x512000)     # appended at old EOF, RVA 0x112000


def aowx_patches():
    raw, va = XLNG_AOWX
    P = []
    # --- main SetLanguage switch @VA 0x453EC8 ---
    P.append((0x0532CD, b"\x05", b"\x06"))                       # cmp eax,5 -> 6
    P.append((0x0532D7, u32(0x453EDB), u32(va)))                 # table -> cave
    tbl = b"".join(u32(v) for v in
                   (0x453EF3, 0x453F02, 0x453F13, 0x453F24,
                    0x453F46, 0x453F35, va + 0x20))
    P.append((raw, b"\0" * 28, tbl))                             # 7-entry table
    stub = (b"\xBA\x06\x00\x00\x00"                              # mov edx,6
            + b"\xA1" + u32(0x45B2BC)                            # mov eax,[dict]
            + b"\xE8" + rel32(0x4020E4, va + 0x2A + 5)           # call SetLanguage
            + b"\xC3")                                           # ret (= exit)
    P.append((raw + 0x20, b"\0" * len(stub), stub))
    # NOTE: AoWx.exe's other language switch @VA 0x4091E5 is deliberately NOT
    # patched. Only the SetLanguage dispatch needs to know about language 6;
    # every other language switch is left to fall to its engine default for
    # value 6 (the same path the unpatched binary takes), which the engine
    # already handles as "beyond the known languages". Extending those was the
    # cause of heap corruption -> RTE 216 at vcl30+0x3924.
    return P


def aowepack_patches():
    P = []
    # --- SetLanguage switch #1 @VA 0x557976A0 (dict in [ebp-4]) ---
    P.append((0x096AA5, b"\x05", b"\x06"))
    P.append((0x096AAB, u32(0x557976AF), u32(0x55812C80)))
    t1 = b"".join(u32(v) for v in
                  (0x557976C7, 0x557976D4, 0x557976E3, 0x557976F2,
                   0x55797710, 0x55797701, 0x55812CC0))
    P.append((0x112080, b"\0" * 28, t1))
    s1 = (b"\xBA\x06\x00\x00\x00"                                # mov edx,6
          + b"\x8B\x45\xFC"                                      # mov eax,[ebp-4]
          + b"\xE8" + rel32(0x5570655C, 0x55812CC8 + 5)          # call SetLanguage
          + b"\xE9" + rel32(0x5579771D, 0x55812CCD + 5))         # jmp continue
    P.append((0x1120C0, b"\0" * len(s1), s1))
    # --- SetLanguage switch #2 @VA 0x55797C90 (dict in [ebx+0x78]) ---
    P.append((0x097095, b"\x05", b"\x06"))
    P.append((0x09709B, u32(0x55797C9F), u32(0x55812CA0)))
    t2 = b"".join(u32(v) for v in
                  (0x55797CB7, 0x55797CC4, 0x55797CD3, 0x55797CE2,
                   0x55797D00, 0x55797CF1, 0x55812CE0))
    P.append((0x1120A0, b"\0" * 28, t2))
    s2 = (b"\xBA\x06\x00\x00\x00"
          + b"\x8B\x43\x78"                                      # mov eax,[ebx+0x78]
          + b"\xE8" + rel32(0x5570655C, 0x55812CE8 + 5)
          + b"\xE9" + rel32(0x55797D0D, 0x55812CED + 5))
    P.append((0x1120E0, b"\0" * len(s2), s2))
    # NOTE: the five per-language grammar/word-form switches at 0x557A7DCA..
    # 0x557A8C43 are deliberately NOT patched - value 6 falls to their engine
    # defaults (nil/base-form), which is safe. Extending them corrupted the
    # heap (RTE 216 at vcl30+0x3924). Generated text for Russian therefore uses
    # base word-forms until a dedicated grammar pass is done - acceptable.
    return P


def aowsetup_patches():
    raw, va = XLNG_SETUP
    # per-site cave slots inside .xlng: tables at +0/0x20/0x40, stubs at
    # +0x60/0x80/0xA0
    P = []
    SITES = [
        # (imm off, operand off, old table VA, entries, table slot, stub slot,
        #  stub bytes)
        (0x067EAB, 0x067EB5, 0x468AB9,
         (0x468AD1, 0x468AE4, 0x468AF9, 0x468B0E, 0x468B38, 0x468B23),
         0x00, 0x60,
         b"\x8B\x45\xFC\x8B\x80\x74\x02\x00\x00"       # mov eax,[ebp-4];[eax+274]
         + b"\xBA\x06\x00\x00\x00"
         + b"\xE8" + rel32(0x44BA20, va + 0x6E + 5)
         + b"\xE9" + rel32(0x468B4B, va + 0x73 + 5)),
        (0x068756, 0x068760, 0x469364,
         (0x46937C, 0x46938C, 0x46939E, 0x4693B0, 0x4693D4, 0x4693C2),
         0x20, 0x80,
         b"\xBA\x06\x00\x00\x00"
         + b"\x8B\x83\x74\x02\x00\x00"                 # mov eax,[ebx+0x274]
         + b"\xE8" + rel32(0x44BA20, va + 0x8B + 5)
         + b"\xE9" + rel32(0x4693E4, va + 0x90 + 5)),
        (0x068833, 0x06883D, 0x469441,
         (0x469459, 0x469469, 0x46947B, 0x46948D, 0x4694B1, 0x46949F),
         0x40, 0xA0,
         b"\xBA\x06\x00\x00\x00"
         + b"\x8B\x83\x74\x02\x00\x00"
         + b"\xE8" + rel32(0x44BA20, va + 0xAB + 5)
         + b"\xE9" + rel32(0x4694C1, va + 0xB0 + 5)),
    ]
    for imm, opnd, tva, ents, tslot, sslot, stub in SITES:
        P.append((imm, b"\x05", b"\x06"))
        P.append((opnd, u32(tva), u32(va + tslot)))
        P.append((raw + tslot, b"\0" * 28,
                  b"".join(u32(v) for v in ents) + u32(va + sslot)))
        P.append((raw + sslot, b"\0" * len(stub), stub))
    # TIvDictionary has TWO validation routines, each with a mode-1 (locale/
    # system) and a mode-2 (codepage) raise. All four are meaningless here -
    # the game renders from its own bitmap fonts, never the OS codepage. Turn
    # every raise-skipping jne into an unconditional jump.
    # routine A ("X is not supported by the {system,code page}"):
    P.append((0x04B17E, b"\x75", b"\xEB"))              # mode-1 short jne->jmp
    P.append((0x04B1B5, b"\x75", b"\xEB"))              # mode-2 short jne->jmp
    # routine B ("The locale (%d,%d) is not supported by the {system,code page}"):
    P.append((0x04B315, b"\x0F\x85", b"\x90\xE9"))      # mode-1 near jne->nop;jmp
    P.append((0x04B36F, b"\x75", b"\xEB"))              # mode-2 short jne->jmp
    return P


def localize_patches():
    # The same two routines inside Localize.dpl (used by AoWx.exe/AoWEPACK.dll
    # via the IvDictio imports). Relative jumps, so package rebasing is fine.
    return [
        (0x006A1A, b"\x75", b"\xEB"),                   # A mode-1
        (0x006A51, b"\x75", b"\xEB"),                   # A mode-2
        (0x006BB1, b"\x0F\x85", b"\x90\xE9"),           # B mode-1 near
        (0x006C0B, b"\x75", b"\xEB"),                   # B mode-2
    ]


# ---------------------------------------------------------------------------
# .xlng section append - modeled on how .xbfs/.xmou themselves were added.
# ---------------------------------------------------------------------------
def ensure_xlng(d, exp_raw, exp_va):
    """Append a 0x200-byte RX '.xlng' section if not present.
    Returns (bytes, appended?)."""
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    nsec = struct.unpack_from("<H", d, pe + 6)[0]
    opt = struct.unpack_from("<H", d, pe + 20)[0]
    base = struct.unpack_from("<I", d, pe + 0x34)[0]
    soi = struct.unpack_from("<I", d, pe + 0x50)[0]
    soh = struct.unpack_from("<I", d, pe + 0x54)[0]
    tbl = pe + 24 + opt
    names = [d[tbl + i * 40:tbl + i * 40 + 8].rstrip(b"\0") for i in range(nsec)]
    if b".xlng" in names:
        return d, False
    hdr_off = tbl + nsec * 40
    if hdr_off + 40 > soh or any(d[hdr_off:hdr_off + 40]):
        raise ValueError("no room for a new section header")
    if len(d) % 0x200:
        raise ValueError("file size not aligned")
    if len(d) != exp_raw or base + soi != exp_va:
        raise ValueError("geometry mismatch: file 0x%X (want 0x%X), "
                         "image end 0x%X (want 0x%X)"
                         % (len(d), exp_raw, base + soi, exp_va))
    d = bytearray(d)
    hdr = (b".xlng\0\0\0"
           + struct.pack("<IIII", 0x200, soi, 0x200, exp_raw)
           + struct.pack("<IIHHI", 0, 0, 0, 0, 0x60000020))
    d[hdr_off:hdr_off + 40] = hdr
    struct.pack_into("<H", d, pe + 6, nsec + 1)
    struct.pack_into("<I", d, pe + 0x50, soi + 0x1000)
    d += b"\0" * 0x200
    return bytes(d), True


# ---------------------------------------------------------------------------
# AoWSetup DFM: add 'Russian' to LanguageCB, drop ItemHeight, pad the stream.
# ---------------------------------------------------------------------------
ITEMHEIGHT = bytes.fromhex("0A4974656D48656967687402")   # len 'ItemHeight' vaInt8
RUSSIAN_ITEM = b"\x06\x07Russian"


def dfm_edit(d):
    """Return the patched AoWSetup image bytes, or None if already patched."""
    d = bytearray(d)
    # locate the LanguageCB combo in the settings-dialog DFM (in .rsrc)
    cb = d.find(b"\x09TComboBox\x0ALanguageCB", 0x73000)
    if cb < 0:
        raise ValueError("LanguageCB DFM not found")
    if d.find(RUSSIAN_ITEM, cb, cb + 0x200) >= 0:
        return None                                        # already patched
    ih = d.find(ITEMHEIGHT, cb, cb + 0x80)
    if ih < 0:
        raise ValueError("ItemHeight property not found (already removed?)")
    # find the resource containing this DFM via the .rsrc directory
    RSRC_RAW, RSRC_VA = 0x73000, 0x78000                   # raw off, section RVA

    def walk(dir_off, depth=0):
        n = struct.unpack_from("<HH", d, RSRC_RAW + dir_off + 12)
        total = n[0] + n[1]
        out = []
        for i in range(total):
            e = RSRC_RAW + dir_off + 16 + i * 8
            _, off = struct.unpack_from("<II", d, e)
            if off & 0x80000000:
                out += walk(off & 0x7FFFFFFF, depth + 1)
            else:
                rva, size = struct.unpack_from("<II", d, RSRC_RAW + off)
                out.append((rva, size))
        return out

    cb_rva = RSRC_VA + (cb - RSRC_RAW)
    res = [(rva, size) for rva, size in walk(0)
           if rva <= cb_rva < rva + size]
    if len(res) != 1:
        raise ValueError("could not isolate the DFM resource (%d hits)" % len(res))
    rva, size = res[0]
    r0 = RSRC_RAW + (rva - RSRC_VA)
    r1 = r0 + size
    if d[r1 - 4:r1].count(0) < 2:
        raise ValueError("DFM does not end with the expected end markers")
    blob = bytearray(d[r0:r1])
    ih_rel = ih - r0
    del blob[ih_rel:ih_rel + len(ITEMHEIGHT) + 1]          # property + value byte
    # insert Russian before the Items.Strings list terminator (00 after Italian)
    it = blob.find(b"\x06\x07Italian")
    if it < 0:
        raise ValueError("Italian item not found after ItemHeight removal")
    ins = it + len(b"\x06\x07Italian")
    if blob[ins] != 0:
        raise ValueError("unexpected byte after Italian item")
    blob[ins:ins] = RUSSIAN_ITEM
    blob += b"\0" * (size - len(blob))                     # net -4 -> pad end
    assert len(blob) == size
    d[r0:r1] = blob
    return bytes(d)


TARGETS = [
    ("AoWx.exe", aowx_patches),
    ("AoWEPACK.dll", aowepack_patches),
    ("AoWSetup.exe", aowsetup_patches),
    ("Localize.dpl", localize_patches),
]


def check_dict_ready():
    m = MLDFile.load(os.path.join(GAME, "Dict", "AoW.mld"))
    return any(l.ISOLanguage == b"ru" for l in m.languages)


def run(apply_it):
    if apply_it and not check_dict_ready():
        print("Dict\\AoW.mld has no Russian column yet - run "
              "patch_dict_russian.py --apply first.")
        sys.exit(1)
    for name, builder in TARGETS:
        path = os.path.join(GAME, name)
        d = bytearray(open(path, "rb").read())
        applied = pending = 0
        problems = []
        sec_note = ""
        if name in ("AoWx.exe", "AoWSetup.exe"):
            geom = XLNG_AOWX if name == "AoWx.exe" else XLNG_SETUP
            try:
                d2, added = ensure_xlng(bytes(d), geom[0], geom[1])
                d = bytearray(d2)
                if added:
                    pending += 1
                    sec_note = ", +.xlng section"
            except ValueError as ex:
                problems.append("section: %s" % ex)
        patches = builder()
        for off, old, new in patches:
            cur = bytes(d[off:off + len(new)])
            if cur == new:
                applied += 1
            elif cur == old:
                pending += 1
                d[off:off + len(new)] = new
            else:
                problems.append("0x%06X: expected %s / %s, found %s"
                                % (off, old.hex(), new.hex(), cur.hex()))
        dfm_note = ""
        if name == "AoWSetup.exe" and not problems:
            try:
                patched = dfm_edit(bytes(d))
                if patched is None:
                    dfm_note = ", DFM already has Russian"
                else:
                    d = bytearray(patched)
                    pending += 1
                    dfm_note = ", DFM +Russian item"
            except ValueError as ex:
                problems.append("DFM: %s" % ex)
        if problems:
            print("  %-13s MISMATCH - not touching this file:" % name)
            for p in problems:
                print("      " + p)
            sys.exit(1)
        print("  %-13s %d patch(es) to write, %d already in place%s%s"
              % (name, pending, applied, sec_note, dfm_note))
        if apply_it and pending:
            bak = path + ".bak_ru7"
            made_bak = not os.path.isfile(bak)
            if made_bak:
                shutil.copy2(path, bak)
            try:
                with open(path, "wb") as fh:
                    fh.write(d)
                print("      written (backup %s)" % os.path.basename(bak))
            except PermissionError:
                if made_bak:
                    os.remove(bak)
                print("      LOCKED - %s is in use (close the running program) "
                      "then re-run --apply" % name)
    if not apply_it:
        print("\nDry run - nothing written. Use --apply.")
    else:
        print("\nDone. Pick Russian in AoWSetup's Settings, or set "
              "HKCU\\Software\\Triumph Studios\\Age of Wonders X\\General\\"
              "Language to 6.")


def revert():
    n = 0
    for name, _ in TARGETS:
        bak = os.path.join(GAME, name + ".bak_ru7")
        if os.path.isfile(bak):
            shutil.copy2(bak, os.path.join(GAME, name))
            print("  restored %s" % name)
            n += 1
    print("Reverted %d file(s)." % n)


if __name__ == "__main__":
    if "--revert" in sys.argv:
        revert()
    else:
        run("--apply" in sys.argv)
