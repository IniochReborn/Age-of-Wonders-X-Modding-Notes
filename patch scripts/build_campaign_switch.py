#!/usr/bin/env python3
r"""AoWx -- switch between AoWx campaigns and VANILLA campaigns (game side, v4).

USER REQUEST 2026-08-31: a dropdown on AoWSetup's Developer tab that switches
the game between the AoWx campaigns (X\Campaign\, the default) and the
original ones (Scenario\Campaign\) -- including the campaign-select screen
text ("A Human Perspective"/"Challenge Mode" vs "The Keepers"/"The Cult of
Storms") and its goal lines.

THE SETTING: registry named value  General\"Vanilla Campaigns"  in the mod's
isolated tree (HKCU\Software\Triumph Studios\Age of Wonders X). "1" = vanilla
campaigns; absent/anything else = AoWx (the default). AoWSetup writes it (see
build_aowsetup_campaign_dropdown.py); to test by hand:
    reg add "HKCU\Software\Triumph Studios\Age of Wonders X\General" ^
        /v "Vanilla Campaigns" /t REG_SZ /d 1 /f

================= WHY v4 LOOKS LIKE THIS (three live tests) =================
v1  swapped the campaign folder + Dict\AoW.mld from an AoWx.exe unit-init.
    Folder worked; screen text did not: TSelFactionWin's labels are RUNTIME
    RESOURCESTRINGS (LoadResString -> AoWE.TranslateRStr), resolved against
    AoWEPACK's ResourceStringDictionary = Dict\ResStr.mld -- not the form
    dictionary. (AoW.mld still swapped: right file for form-property text.)
v2  redirected AoWEPACK's ResStr file-name push as well. Still nothing: the
    engine (and that dictionary) is created during AOWEPACK'S OWN DLL INIT,
    which runs BEFORE any exe unit-init -- the exe-side buffer fill was too
    late. (TAoWEngine.TranslateRStr @0x55797B30 confirms [engine+0x78] is the
    dictionary consulted, via IvDictio.Translate when [dict+0x44]>0.)
v3  filled the buffer from an AoWEPACK cave inside UpdateStartupDirectory.
    Correct mechanism -- but the SETTING had vanished: v1..v3 stored it in
    General\strings\4, and **General\strings is a game-managed list** (slot 0
    = the player name); the game rewrites that key and deleted our slot after
    the first run. Tests #2/#3 therefore ran with the setting absent.
v4  = v3's mechanism + durable storage: a NAMED value under General (the
    game only touches its own known names there -- Cheat Mode etc. persist),
    read via TAoWRegistry.rwString in read mode. And since AoWEPACK's init
    runs FIRST, the exe-side init hook is REMOVED ENTIRELY -- it would only
    re-fill the buffers afterwards with a second copy of the same decision
    (or, if the two ever disagreed, clobber the right one). The exe now
    carries DATA ONLY.

============================ VERIFIED RE FACTS =============================
AoWx.exe (ImageBase 0x400000, DllCharacteristics 0 -- never rebases):
  * campaign folder literal `X\Campaign\` x4, read from 5 sites:
    0x0040CD3A / 0x004185B8 / 0x0041C2DE / 0x0041D580 (push) + 0x0041D6B4
    (mov ecx). Only the FOLDER differs between the sets -- both use
    Keepers.cam/Storm.cam.
  * form-dictionary file name: single `push 'AoW.MLD'` @0x00453EA2 inside the
    unit-init 0x00453E64 (logical dictionary name 'AoW' is kept -- the .mld's
    internal name must agree, and AoWVan.MLD is a byte copy of vanilla
    AoW.mld so it does).
  * all six pointer immediates carry relocs which STAY VALID (the new values
    are still in-image addresses).
AoWEPACK.dll (rebases -> PIC where needed):
  * `TAoWEngine.UpdateStartupDirectory` @0x557982D0 builds the ResStr path
    ('Dict\' @0x55798386, 'ResStr' @0x5579838B, '.mld' @0x55798390 ->
    LStrCatN into [engine+0x78]+0x7C) and immediately LOADS the dictionary
    ([dict vmt+0x44] @0x557983AA). Its FIRST act is
    TAoWRegistry.GetStartupDirectory on [engine+0x5C] (@0x557982EB), so the
    registry object is alive at our hook.
  * hook site: `mov eax,[0x558FC4E8]` @0x55798376 (5 B, BaseSoundEnginePath
    load; esi = engine there). Its reloc @0x55798377 must be neutralised.
  * `TAoWRegistry.rwString` @0x55703D08: eax=self (a TRegistry -- opens
    '\Software\Triumph Studios\Age of Wonders X' + edx), edx=subkey,
    ecx=value name, stack args [@result] then [mode byte] (0=read: ValueExists
    -> ReadString into @result; 1=write). **ret 8** (callee-cleaned).
    AnsiString literal args are fine: LStrAddRef on refcount -1 is a no-op.
Dictionaries (`Dict\`):
  * AoWVan.MLD = byte copy of vanilla 1.36 AoW.mld (9 differing regions vs
    ours, all TSelFactionWin -- form text).
  * ResStrV.mld = OUR ResStr.mld with ONLY 3 records ("The Keepers",
    "The Cult of Storms", "Choose a Faction") transplanted from vanilla --
    built by build_resstr_vanilla_mld.py; all other AoWx renames (Monster
    Slaying, Cosmic Breath, Seeker Bolts, ...) kept.

================================ THE PATCH ================================
AoWx.exe `.xbfs` cave @0x0060E940 (RWX, chars 0xE0000060) -- DATA ONLY:
  8 constant 32 B AnsiString images (campaign X/V, AoW dict X/V, ResStr X/V,
  'General', 'Vanilla Campaigns') + 3 live buffers, shipped as AoWx defaults.
  The 6 exe pointer sites + AoWEPACK's ResStr push point at the buffers.
AoWEPACK cave @0x558151D0: hooked from 0x55798376. Reads the named value with
  rwString(read); "1" -> copies the V images into all three buffers, else the
  X images (idempotent if init ever runs twice). Buffer/image addresses are
  plain absolutes into the exe image (never rebases, no relocs); rwString and
  LStrClr are intra-module rel32 (rebase-safe); the one displaced absolute
  load is re-based via the call/pop delta idiom.

Usage: dry run default; --apply; --revert (surgical, both binaries).
"""
import os
import shutil
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.environ.get("AOW_GAME_DIR") or os.path.dirname(HERE)
EXE = os.path.join(GAME, "AoWx.exe")
BAK = EXE + ".bak_campswitch"
EPACK = os.path.join(GAME, "AoWEPACK.dll")
EPACK_BAK = EPACK + ".bak_campswitch"
VAN_MLD = os.path.join(GAME, "Dict", "AoWVan.MLD")
RESSTRV_MLD = os.path.join(GAME, "Dict", "ResStrV.mld")
TEXTVAN_PFS = os.path.join(GAME, "Release", "TEXTVAN.PFS")

IMAGE_BASE = 0x400000
EPACK_IMAGE_BASE = 0x55700000

# ---- exe data cave ----
CAVE = 0x0060E940
CAVE_LIMIT = 0x0060F000
BLOCK = 32

CAMP_X = b"X\\Campaign\\"
CAMP_V = b"Scenario\\Campaign\\"
DICT_X = b"AoW.MLD"
DICT_V = b"AoWVan.MLD"
RES_X = b"ResStr"
RES_V = b"ResStrV"
TEXTP_X = b"TEXT.PFS"
TEXTP_V = b"TEXTVAN.PFS"
KEY_GENERAL = b"General"
VAL_NAME = b"Vanilla Campaigns"

(OFF_CAMP_X, OFF_CAMP_V, OFF_DICT_X, OFF_DICT_V, OFF_RES_X, OFF_RES_V,
 OFF_TEXTP_X, OFF_TEXTP_V, OFF_GEN, OFF_VAL) = (BLOCK * i for i in range(10))
(OFF_BUF_CAMP, OFF_BUF_DICT, OFF_BUF_RES,
 OFF_BUF_TEXTP) = (BLOCK * i for i in range(10, 14))
CAVE_SIZE = BLOCK * 14
VA_BUF_CAMP_CHARS = CAVE + OFF_BUF_CAMP + 8
VA_BUF_DICT_CHARS = CAVE + OFF_BUF_DICT + 8
VA_BUF_RES_CHARS = CAVE + OFF_BUF_RES + 8
VA_BUF_TEXTP_CHARS = CAVE + OFF_BUF_TEXTP + 8

# ---- exe pointer sites ----
CAMP_SITES = [0x0040CD3A, 0x004185B8, 0x0041C2DE, 0x0041D580, 0x0041D6B4]
CAMP_ORIG = {0x0040CD3A: 0x0040CDD8, 0x004185B8: 0x004186A0,
             0x0041C2DE: 0x0041C330, 0x0041D580: 0x0041D7A8,
             0x0041D6B4: 0x0041D7A8}
DICT_SITE = 0x00453EA2
DICT_ORIG_PTR = 0x00453F7C
# v1..v3 hooked the exe unit-init here; v4 keeps it VANILLA (restore on apply)
EXE_OLDHOOK = 0x00453E84
EXE_OLDHOOK_ORIG = bytes.fromhex("ba603f4500")
EXE_OLDHOOK_RELOC = 0x00453E85

# ---- AoWEPACK ----
# ⚠⚠ v6 LESSON (user-hit: AoWDevX runtime error 216): **AoWEPACK.dll is NOT
# game-only** -- AoWDevX.exe (and potentially other tools) load it, and its
# engine init runs the SAME UpdateStartupDirectory / dictionary / TEXT.PFS
# code. v5 pointed AoWEPACK's own string reads (ResStr push, TEXT.PFS pushes)
# and the cave's buffer writes at addresses inside AoWx.exe's `.xbfs` section
# -- which is UNMAPPED in the editor's process -> AV during editor startup.
# v6 rules:
#   * anything AOWEPACK code reads/writes lives INSIDE AoWEPACK: constants in
#     the code cave (delta-addressed), live buffers in **BSS slack**
#     (0x558FA240/0x558FA260 -- zero-init R/W, present in every host, no file
#     backing needed since the cave always fills them before any consumer);
#     the repointed pushes stay intra-module, so their ORIGINAL relocs remain
#     ACTIVE (type 3) and rebase keeps them correct in every process.
#   * the exe-image buffers (campaign dir + AoW.MLD, consumed only by
#     AoWx.exe code) are only written after a HOST CHECK: host SizeOfImage
#     (read via [0x40003C] -> [hdr+0x50], always-mapped) >= 0x60F000 AND the
#     `.xbfs` cave signature dword @0x0060E948 == 'X\Ca' -- i.e. the host
#     really is our patched AoWx.exe.
#   * the editor therefore FOLLOWS the setting for ResStr/TEXT.PFS (it shows
#     the same text set as the game -- consistent), and never touches the
#     exe-only buffers.
EPACK_CAVE = 0x558151D0
EPACK_CAVE_LIMIT = 0x55815500
EPACK_EBUF_RES = 0x558FA240            # BSS slack, 32 B AnsiString image
EPACK_EBUF_TEXTP = 0x558FA260
VA_EBUF_RES_CHARS = EPACK_EBUF_RES + 8
VA_EBUF_TEXTP_CHARS = EPACK_EBUF_TEXTP + 8
# ⚠ SizeOfImage is in RVA space: our AoWx.exe = 0x0020F000 (.xbfs ends at RVA
# 0x20F000). v7's first cut compared against 0x60F000 (a VA!) so the gate
# NEVER passed and the exe buffers stayed at AoWx defaults -> "vanilla text
# but AoWx campaign files" (caught by live probe 9/1). AoWDevX = 0xE4000,
# still well below, so the check discriminates as intended.
AOWX_SOI = 0x0020F000                  # our AoWx.exe SizeOfImage (RVA!)
SIG_VA = 0x0060E948                    # .xbfs cave: chars of 'X\Campaign\'
SIG_DW = 0x61435C58                    # 'X\Ca' little-endian
# ⚠⚠⚠ v7 LESSON (user-hit: editor STILL 216 with v6): **the editor never
# calls UpdateStartupDirectory** -- that hook belongs to the GAME's engine
# startup only, so in AoWDevX the BSS buffers stayed EMPTY (len 0), and
# TAoWHSSet.ReadWrite then built `dir + '' ` as the TEXT.PFS path -> load
# failure during editor init -> runtime error 216. Any design that fills the
# buffers at one point and consumes them at another is ORDER-DEPENDENT and
# breaks in hosts with a different init sequence. v7: **each consumer site
# guarantees its own data** -- the three repointed instructions become CALLS
# into stubs that (a) run the fill if the buffers are still empty, sourcing
# the registry from the live engine ([esi+0x5C] at the ResStr site, the
# AoWE.AoWEngine BSS global 0x558FA048 -- which the surrounding TEXT.PFS code
# itself reads -- at the TEXT.PFS sites), then (b) return the buffer pointer
# exactly as the original `push imm32` / `mov ecx, imm32` did. The
# UpdateStartupDirectory hook is GONE (site stays vanilla), and since the
# sites now hold rel32 calls, their relocs are neutralised (restored on
# revert).
EPACK_HOOK = 0x55798376                # v3..v6 hook site -- v7 keeps it VANILLA
EPACK_HOOK_ORIG = bytes.fromhex("a1e8c48f55")
EPACK_HOOK_RELOC = 0x55798377
EPACK_SITE = 0x5579838B                # push 'ResStr'   (68 imm32)
EPACK_SITE_ORIG = bytes.fromhex("68f8837955")
EPACK_ORIG_PTR = 0x557983F8
EPACK_SITE_RELOC = 0x5579838C
ENGINE_GLOBAL = 0x558FA048             # AoWE.AoWEngine (BSS; registry at +0x5C)
RWSTRING = 0x55703D08                  # TAoWRegistry.rwString (ret 8)
EPACK_LSTRCLR = 0x55701140             # System.@LStrClr thunk
EPACK_SOUNDPATH = 0x558FC4E8           # (kept for docs; hook no longer used)

# ---- the campaign JOIN text (the scrolling intro when committing to a
# faction): `TAoWHSSet.ReadWrite` builds dir + 'TEXT.PFS' at two sites
# (`mov ecx, 0x5574CB70` @ +0x2D1 read / +0x475 write) and loads the result
# into [set+0x98] = the TTextControl that TCampaignJoinDlg's
# RetrieveText(0xA/0xB) consults. Repointing the literal at a 4th buffer
# swaps the whole file: Release\TEXTVAN.PFS = byte copy of the vanilla 1.36
# TEXT.pfs. ⚠ In vanilla mode this reverts ALL TEXT.pfs strings, including
# the AoWx diplomacy rewrites -- deliberate: the full vanilla experience.
# TAoWHSSet loads AFTER UpdateStartupDirectory (it needs the basedir), so
# the buffer is already decided. Both imm32s carry relocs -> neutralise.
TEXTP_SITES = [0x5574C7F9, 0x5574C99D]
TEXTP_SITE_ORIG = bytes.fromhex("b970cb7455")   # mov ecx, 'TEXT.PFS'
TEXTP_ORIG_PTR = 0x5574CB70
TEXTP_RELOCS = [0x5574C7FA, 0x5574C99E]

EPACK_SRC = """
_stub_res:
    push dword ptr [esp]
    push eax
    push ebx
    call _anchor0
_anchor0:
    pop  ebx
    sub  ebx, {anchor0:#x}
    mov  eax, dword ptr [esi + 0x5C]
    call _ensure
    lea  eax, [ebx + {ebuf_res_chars:#x}]
    mov  dword ptr [esp + 0xC], eax
    pop  ebx
    pop  eax
    ret

_stub_textp:
    push eax
    push ebx
    call _anchor1
_anchor1:
    pop  ebx
    sub  ebx, {anchor1:#x}
    mov  eax, dword ptr [ebx + {engine_glob:#x}]
    test eax, eax
    jz   _st2
    mov  eax, dword ptr [eax + 0x5C]
_st2:
    call _ensure
    lea  ecx, [ebx + {ebuf_textp_chars:#x}]
    pop  ebx
    pop  eax
    ret

_ensure:
    cmp  dword ptr [ebx + {ebuf_res_len:#x}], 0
    jne  _eret
    pushad
    sub  esp, 8
    mov  dword ptr [esp], 0
    mov  dword ptr [esp + 4], 0
    test eax, eax
    jz   _fill
    mov  edx, esp
    push edx
    push 0
    lea  edx, [ebx + {gen:#x}]
    lea  ecx, [ebx + {val:#x}]
    call {rwstring:#x}
    mov  eax, dword ptr [esp]
    test eax, eax
    jz   _fill
    cmp  byte ptr [eax], 0x31
    jne  _fill
    mov  dword ptr [esp + 4], 1
_fill:
    mov  eax, esp
    call {lstrclr:#x}
    lea  esi, [ebx + {res_x:#x}]
    cmp  dword ptr [esp + 4], 0
    je   _r1
    lea  esi, [ebx + {res_v:#x}]
_r1:
    lea  edi, [ebx + {ebuf_res:#x}]
    call _c32
    lea  esi, [ebx + {textp_x:#x}]
    cmp  dword ptr [esp + 4], 0
    je   _r2
    lea  esi, [ebx + {textp_v:#x}]
_r2:
    lea  edi, [ebx + {ebuf_textp:#x}]
    call _c32
    mov  eax, dword ptr [0x40003C]
    mov  eax, dword ptr [eax + 0x400050]
    cmp  eax, {aowx_soi:#x}
    jb   _noexe
    cmp  dword ptr [{sig_va:#x}], {sig_dw:#x}
    jne  _noexe
    mov  esi, {camp_x:#x}
    cmp  dword ptr [esp + 4], 0
    je   _r3
    mov  esi, {camp_v:#x}
_r3:
    mov  edi, {buf_camp:#x}
    call _c32
    mov  esi, {dict_x:#x}
    cmp  dword ptr [esp + 4], 0
    je   _r4
    mov  esi, {dict_v:#x}
_r4:
    mov  edi, {buf_dict:#x}
    call _c32
_noexe:
    add  esp, 8
    popad
_eret:
    ret

_c32:
    mov  ecx, 8
_cl:
    mov  eax, dword ptr [esi]
    mov  dword ptr [edi], eax
    add  esi, 4
    add  edi, 4
    dec  ecx
    jnz  _cl
    ret
"""


def image(s):
    b = struct.pack("<iI", -1, len(s)) + s + b"\0"
    assert len(b) <= BLOCK, "%r does not fit a %d B block" % (s, BLOCK)
    return b + b"\0" * (BLOCK - len(b))


def build_exe_cave():
    body = bytearray()
    for s in (CAMP_X, CAMP_V, DICT_X, DICT_V, RES_X, RES_V,
              TEXTP_X, TEXTP_V, KEY_GENERAL, VAL_NAME):
        body += image(s)
    body += image(CAMP_X) + image(DICT_X) + image(RES_X) + image(TEXTP_X)
    assert len(body) == CAVE_SIZE
    return bytes(body)


def build_epack_cave():
    """keystone hangs on ';' comments -- source is comment-free.

    v7 PIC discipline: each stub computes the load delta (call/pop anchor)
    into ebx and passes it to _ensure; every AoWEPACK-side reference is
    `[ebx + preferred-VA]`; rwString/LStrClr are intra-module rel32; ONLY the
    host-gated exe-buffer block uses plain absolutes into the exe image.
    Returns (body, va_stub_res, va_stub_textp): 6 constant AnsiString images
    at EPACK_CAVE, code at EPACK_CAVE + 6*BLOCK (stub_res first; stub_textp
    right after stub_res's `ret`).
    """
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    ks = Ks(KS_ARCH_X86, KS_MODE_32)
    e_res_x, e_res_v = EPACK_CAVE, EPACK_CAVE + BLOCK
    e_textp_x, e_textp_v = EPACK_CAVE + BLOCK * 2, EPACK_CAVE + BLOCK * 3
    e_gen, e_val = EPACK_CAVE + BLOCK * 4, EPACK_CAVE + BLOCK * 5
    code_va = EPACK_CAVE + BLOCK * 6
    anchor0, anchor1 = code_va + 10, code_va + 0x40
    for _ in range(12):
        src = EPACK_SRC.format(
            gen=e_gen + 8, val=e_val + 8,
            res_x=e_res_x, res_v=e_res_v,
            textp_x=e_textp_x, textp_v=e_textp_v,
            ebuf_res=EPACK_EBUF_RES, ebuf_textp=EPACK_EBUF_TEXTP,
            ebuf_res_chars=VA_EBUF_RES_CHARS, ebuf_res_len=EPACK_EBUF_RES + 4,
            ebuf_textp_chars=VA_EBUF_TEXTP_CHARS,
            engine_glob=ENGINE_GLOBAL,
            rwstring=RWSTRING, lstrclr=EPACK_LSTRCLR,
            anchor0=anchor0, anchor1=anchor1,
            aowx_soi=AOWX_SOI, sig_va=SIG_VA, sig_dw=SIG_DW,
            camp_x=CAVE + OFF_CAMP_X, camp_v=CAVE + OFF_CAMP_V,
            dict_x=CAVE + OFF_DICT_X, dict_v=CAVE + OFF_DICT_V,
            buf_camp=CAVE + OFF_BUF_CAMP, buf_dict=CAVE + OFF_BUF_DICT)
        code = bytes(ks.asm(src, code_va)[0])
        # locate both `call $+5 / pop ebx` anchors
        idxs = []
        j = 0
        while True:
            j = code.find(bytes([0xE8, 0, 0, 0, 0]), j)
            if j == -1:
                break
            if code[j + 5] == 0x5B:
                idxs.append(code_va + j + 5)
            j += 1
        assert len(idxs) == 2, "expected 2 anchor idioms, got %d" % len(idxs)
        if (anchor0, anchor1) == (idxs[0], idxs[1]):
            body = bytearray()
            for s in (RES_X, RES_V, TEXTP_X, TEXTP_V, KEY_GENERAL, VAL_NAME):
                body += image(s)
            body += code
            # stub_textp = the instruction after stub_res's `ret` (C3),
            # which is the first C3 after the `pop eax` (58 C3 sequence)
            k = code.find(b"\x58\xC3")
            assert k != -1, "stub_res tail not found"
            return bytes(body), code_va, code_va + k + 2
        anchor0, anchor1 = idxs[0], idxs[1]
    raise AssertionError("anchors did not converge")


def load_pe(d, base):
    e = struct.unpack_from("<I", d, 0x3C)[0]
    n = struct.unpack_from("<H", d, e + 6)[0]
    opt = struct.unpack_from("<H", d, e + 20)[0]
    tbl = e + 24 + opt
    secs = []
    for i in range(n):
        b = tbl + i * 40
        nm = d[b:b + 8].rstrip(b"\0").decode()
        vsz, va, rsz, raw = struct.unpack_from("<IIII", d, b + 8)
        secs.append((nm, base + va, vsz, raw, rsz))
    return secs


def make_off(secs):
    def off(va):
        for nm, b, vsz, raw, rsz in secs:
            if b <= va < b + max(vsz, rsz):
                return raw + (va - b)
        raise ValueError("VA %#x unmapped" % va)
    return off


def reloc_entries(d, secs, base):
    rl = [s for s in secs if s[0] == ".reloc"][0]
    off, end = rl[3], rl[3] + rl[4]
    while off < end - 8:
        page, size = struct.unpack_from("<II", d, off)
        if size < 8 or size > 0x1000:
            break
        for i in range(off + 8, off + size, 2):
            w = struct.unpack_from("<H", d, i)[0]
            yield i, base + page + (w & 0xFFF), w >> 12
        off += size


def set_reloc(d, secs, base, va, want_type):
    """Flip the type nibble of the entry at `va` (3<->0). True if changed."""
    for i, eva, ty in reloc_entries(d, secs, base):
        if eva == va and ty != want_type and ty in (0, 3):
            w = struct.unpack_from("<H", d, i)[0]
            struct.pack_into("<H", d, i, (want_type << 12) | (w & 0xFFF))
            return True
    return False


def main():
    do_apply = "--apply" in sys.argv
    revert = "--revert" in sys.argv
    d = bytearray(open(EXE, "rb").read())
    ed = bytearray(open(EPACK, "rb").read())
    xsecs = load_pe(d, IMAGE_BASE)
    esecs = load_pe(ed, EPACK_IMAGE_BASE)
    xoff, eoff = make_off(xsecs), make_off(esecs)
    xcave = build_exe_cave()
    ecave, va_stub_res, va_stub_textp = build_epack_cave()
    assert CAVE + len(xcave) <= CAVE_LIMIT
    assert EPACK_CAVE + len(ecave) <= EPACK_CAVE_LIMIT, len(ecave)
    call_res = bytes([0xE8]) + struct.pack("<i", va_stub_res - (EPACK_SITE + 5))
    call_tp = {va: bytes([0xE8]) + struct.pack("<i", va_stub_textp - (va + 5))
               for va in TEXTP_SITES}

    def ptr_state(buf, off_, orig, patched):
        cur = struct.unpack_from("<I", buf, off_ + 1)[0]
        return ("original" if cur == orig else
                "applied" if cur == patched else "FOREIGN")

    def site_state(buf, off_, orig5, patched5):
        cur = bytes(buf[off_:off_ + 5])
        return ("original" if cur == orig5 else
                "applied" if cur == patched5 else "FOREIGN")

    states = [ptr_state(d, xoff(va), CAMP_ORIG[va], VA_BUF_CAMP_CHARS)
              for va in CAMP_SITES]
    states.append(ptr_state(d, xoff(DICT_SITE), DICT_ORIG_PTR, VA_BUF_DICT_CHARS))
    oldh = bytes(d[xoff(EXE_OLDHOOK):xoff(EXE_OLDHOOK) + 5])
    old_hooked = oldh != EXE_OLDHOOK_ORIG          # any v1..v3 residue
    states.append(site_state(ed, eoff(EPACK_SITE), EPACK_SITE_ORIG, call_res))
    eh = bytes(ed[eoff(EPACK_HOOK):eoff(EPACK_HOOK) + 5])
    ehooked = eh != EPACK_HOOK_ORIG                # v3..v6 residue
    for va in TEXTP_SITES:
        states.append(site_state(ed, eoff(va), TEXTP_SITE_ORIG, call_tp[va]))

    print("  exe campaign sites : %s" % ", ".join(states[:5]))
    print("  exe dict site      : %s" % states[5])
    print("  exe old init hook  : %s" % ("v1-v3 residue (will restore)"
                                         if old_hooked else "vanilla"))
    print("  epack ResStr site  : %s" % states[6])
    print("  epack old hook     : %s   (cave %d B, stubs %08X/%08X)"
          % ("v3-v6 residue (will restore)" if ehooked else "vanilla",
             len(ecave), va_stub_res, va_stub_textp))
    print("  epack TEXT.PFS x2  : %s" % ", ".join(states[7:9]))
    if "FOREIGN" in states:
        print("FOREIGN bytes - refusing")
        return 1

    if revert:
        for va in CAMP_SITES:
            struct.pack_into("<I", d, xoff(va) + 1, CAMP_ORIG[va])
        struct.pack_into("<I", d, xoff(DICT_SITE) + 1, DICT_ORIG_PTR)
        d[xoff(EXE_OLDHOOK):xoff(EXE_OLDHOOK) + 5] = EXE_OLDHOOK_ORIG
        if set_reloc(d, xsecs, IMAGE_BASE, EXE_OLDHOOK_RELOC, 3):
            print("  exe reloc restored")
        d[xoff(CAVE):xoff(CAVE) + (CAVE_LIMIT - CAVE)] = bytes(CAVE_LIMIT - CAVE)
        open(EXE, "wb").write(bytes(d))
        ed[eoff(EPACK_SITE):eoff(EPACK_SITE) + 5] = EPACK_SITE_ORIG
        for va in TEXTP_SITES:
            ed[eoff(va):eoff(va) + 5] = TEXTP_SITE_ORIG
        ed[eoff(EPACK_HOOK):eoff(EPACK_HOOK) + 5] = EPACK_HOOK_ORIG
        ed[eoff(EPACK_CAVE):eoff(EPACK_CAVE) + (EPACK_CAVE_LIMIT - EPACK_CAVE)] = \
            bytes(EPACK_CAVE_LIMIT - EPACK_CAVE)
        for va in [EPACK_HOOK_RELOC, EPACK_SITE_RELOC] + TEXTP_RELOCS:
            if set_reloc(ed, esecs, EPACK_IMAGE_BASE, va, 3):
                print("  epack reloc @0x%08X restored" % va)
        open(EPACK, "wb").write(bytes(ed))
        print("reverted (both binaries): AoWx campaigns hardcoded again")
        return 0

    want_exe = bytes(d[xoff(CAVE):xoff(CAVE) + len(xcave)]) == xcave and \
        not old_hooked and all(s == "applied" for s in states[:6])
    want_ep = all(s == "applied" for s in states[6:]) and not ehooked and \
        bytes(ed[eoff(EPACK_CAVE):eoff(EPACK_CAVE) + len(ecave)]) == ecave
    if want_exe and want_ep:
        print("already applied (v7)")
        return 0

    if not do_apply:
        try:
            from capstone import Cs, CS_ARCH_X86, CS_MODE_32
            print("  ---- epack cave ----")
            for i in Cs(CS_ARCH_X86, CS_MODE_32).disasm(ecave, EPACK_CAVE):
                print("    %08X  %-7s %s" % (i.address, i.mnemonic, i.op_str))
        except ImportError:
            pass
        print("dry run (--apply / --revert)")
        return 0

    for need in (VAN_MLD, RESSTRV_MLD, TEXTVAN_PFS):
        if not os.path.isfile(need):
            print("MISSING %s - refusing" % need)
            return 1
    if not os.path.isfile(BAK):
        shutil.copy2(EXE, BAK)
        print("  backed up -> %s" % os.path.basename(BAK))
    if not os.path.isfile(EPACK_BAK):
        shutil.copy2(EPACK, EPACK_BAK)
        print("  backed up -> %s" % os.path.basename(EPACK_BAK))

    # exe: data cave + pointer redirects; v1..v3 init hook restored to vanilla
    d[xoff(CAVE):xoff(CAVE) + (CAVE_LIMIT - CAVE)] = bytes(CAVE_LIMIT - CAVE)
    d[xoff(CAVE):xoff(CAVE) + len(xcave)] = xcave
    for va in CAMP_SITES:
        struct.pack_into("<I", d, xoff(va) + 1, VA_BUF_CAMP_CHARS)
    struct.pack_into("<I", d, xoff(DICT_SITE) + 1, VA_BUF_DICT_CHARS)
    d[xoff(EXE_OLDHOOK):xoff(EXE_OLDHOOK) + 5] = EXE_OLDHOOK_ORIG
    if set_reloc(d, xsecs, IMAGE_BASE, EXE_OLDHOOK_RELOC, 3):
        print("  exe v1-v3 init hook removed, reloc restored")
    # epack v7: self-ensuring stubs at the 3 consumer sites; hook stays VANILLA
    ed[eoff(EPACK_CAVE):eoff(EPACK_CAVE) + (EPACK_CAVE_LIMIT - EPACK_CAVE)] = \
        bytes(EPACK_CAVE_LIMIT - EPACK_CAVE)
    ed[eoff(EPACK_CAVE):eoff(EPACK_CAVE) + len(ecave)] = ecave
    ed[eoff(EPACK_SITE):eoff(EPACK_SITE) + 5] = call_res
    for va in TEXTP_SITES:
        ed[eoff(va):eoff(va) + 5] = call_tp[va]
    ed[eoff(EPACK_HOOK):eoff(EPACK_HOOK) + 5] = EPACK_HOOK_ORIG
    if set_reloc(ed, esecs, EPACK_IMAGE_BASE, EPACK_HOOK_RELOC, 3):
        print("  epack v3-v6 hook removed, reloc restored")
    for va in [EPACK_SITE_RELOC] + TEXTP_RELOCS:   # sites are rel32 calls now
        if set_reloc(ed, esecs, EPACK_IMAGE_BASE, va, 0):
            print("  epack site reloc @0x%08X neutralised" % va)
    try:
        open(EXE, "wb").write(bytes(d))
        open(EPACK, "wb").write(bytes(ed))
    except PermissionError:
        print("LOCKED - close AoWx.exe and retry")
        return 1
    print('APPLIED (v4) - the setting is now the NAMED value '
          '"Vanilla Campaigns" under General (durable: the game only rewrites '
          'its own names there). Set it with:\n'
          '  reg add "HKCU\\Software\\Triumph Studios\\Age of Wonders X\\'
          'General" /v "Vanilla Campaigns" /t REG_SZ /d 1 /f\n'
          '(/d 0 or deleting it = AoWx campaigns). Restart the game between '
          'changes.')
    return 0


if __name__ == "__main__":
    sys.exit(main())
