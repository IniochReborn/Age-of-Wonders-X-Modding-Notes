#!/usr/bin/env python3
r"""
AoWEPACK.dll animated sky overlay - code + data blob (2026-10-31), used by patch_sky_polish_v1.py.

Replaces the target of Ziggurat's Firmament overlay hook (TAoWHSMap.DrawDynamicScene prologue 0x55778A60, which
jumped to the relocated Ziggurat main 0x558C0200).  Runs every frame after the static scene was blitted:
  * every visible hexagon with terrain 0xE, on ANY level;
  * a screen pixel is processed only while it still equals the Sky / Clear Sky tile pixel at that hex position
    (12 packed tile tables, Ziggurat's trick: units/structures/fog drawn over the sky are left alone, and a pixel
    is never processed twice);
  * Sky:   stars twinkle; on the Firmament the Surface (Ziggurat's cached 60 % render, parallax 3/4) shows through
           at 0x30/256; drifting lavender cloud wisps on top;
    Clear: Surface shows through at 0xA0/256 (Firmament only) + white translucent clouds.
  * clouds = two samples of a 256x256 periodic density texture in WORLD pixels, scrolled by timeGetTime (HSEPack's
    winmm import, reached through our HSEPack import delta), alpha from a per-kind curve.
Per-pixel math = sky_clouds_art.model_pixel (verified with unicorn by test_sky_overlay_emu.py).
Ziggurat's surface-cache builder (relocated 0x558C0900, BSS 0x558FAF00..1B) is reused unchanged.
Layout (ZONE 0x558CB000): code 0x000, spans 0x800, LUTs 0x840/0x940, twinkle 0xA40, consts 0xA80,
tile tables 0x1000 (12 x 0x840), cloud texture 0x8000 (64 KB) -> end 0x558E3000.
"""
import os, struct, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sky_clouds_art as A  # noqa: E402

ZONE = 0x558CB000
SPAN, LUT, TWT, FLASH, CONST, TBL = (ZONE + 0x1000, ZONE + 0x1040, ZONE + 0x1540, ZONE + 0x1580, ZONE + 0x15C0,
                                     ZONE + 0x2000)
CPUL = ZONE + 0x1FC0      # 64-byte cloud pulse table (just below the tile tables)
TEX = 0x5588C000          # cloud texture: own zone (verified zero, reloc-free, unclaimed) 0x5588C000..0x5589C000
WEB = 0x5589C000          # Chasm lightning-web texture 0x5589C000..0x558AC000 (same checks)
MAGIC = b"SKY2"
HOOK, HOOK_ZIG = 0x55778A60, 0x558C0200
RESUME = 0x55778A66
ZIG_CACHE = 0x558C0900
GLOBAL_MAP = 0x558FA040
EXTRA = 0x558DB000       # sky_overlay_ext_asm jump table (water build)
EXT_WS, EXT_WF, EXT_SF, EXT_SKH = EXTRA, EXTRA + 5, EXTRA + 10, EXTRA + 15
WATER_VMT = 0x5579A5F8   # AoWHex..TAoWWaterHexagon (ice hexes use the same class)
FOG_K, FOG_WP, FOG_PK = 0xF4, 0xF8, 0xFC   # frame locals (free slots below CACHE): fog kind / water mean pack /
                                          # saved screen pixel
WPACK_WATER = 20 | (58 << 8) | (44 << 16)   # mean water tile colour, 5/6/5 units x4 (r, g, b)
WPACK_ICE = 43 | (98 << 8) | (58 << 16)     # mean ice tile colour
FOG_MINDEN = 0x3C0                          # |sky - water|^2 (x16) below this the fog is not separable
FOG_MAXRES = 0x300                          # max squared distance (x16 units) from the water->sky line
CCLEAR = 0x558FAF30      # BSS byte: 1 = the current battle is on Clear Sky (set by AoWTCPCK battle setup)
GETLEVEL = 0x557020EC
IAT_HSE_GETMAPLEVEL, HSE_GETMAPLEVEL, HSE_IAT_TIMEGETTIME = 0x558FBEA8, 0x55608D48, 0x55630988
BSS_BUF, BSS_W, BSS_H, BSS_OK, BSS_MAP, BSS_FMT = (0x558FAF00, 0x558FAF04, 0x558FAF08, 0x558FAF0C, 0x558FAF10,
                                                   0x558FAF14)
NSKY, NCLR, NCHS = 8, 4, 15
NVAR = NSKY + NCLR + NCHS     # tile tables: 8 Sky + 4 Clear + 15 Chasm
END = TBL + NVAR * 0x840

# frame locals (esp-relative, after pushad + sub esp, FR)
FR = 0x500
WONLY = 0x500      # water build only: frame grows to 0x510, +0x500 = 1 for the water-only post pass
CACHE = 0x100       # 64 slots x (tag x, tag y, c, cloud pulse) for the 4x2-block cloud field
L = dict(MAP=0, DC=4, FMT=8, MASK=0xC, SURF=0x10, SW=0x14, SH=0x18, PX=0x1C, PY=0x20, OX1=0x24, OY1=0x28,
         OX2=0x2C, OY2=0x30, TW=0x34, LVL=0x38, X=0x3C, Y=0x40, XEND=0x44, YEND=0x48, WX=0x4C, WY=0x50, SX=0x54,
         SY=0x58, BX=0x5C, BY=0x60, R=0x64, K=0x68, I=0x6C, CNT=0x70, DST=0x74, CWX=0x78, CWY=0x7C, BCOL=0x80,
         BROW=0x84, KIND=0x88, KEY=0x8C, C=0x90, RR=0x94, GG=0x98, BB=0x9C, NN=0xA0, T=0xA4, MODE=0xA8,
         HK=0xAC, TF=0xB0, FL=0xDC, PH=0xE0, OWX2=0xE4, OWY2=0xE8, BFX=0xB4, BFY=0xB8, BIX=0xBC, BTOP=0xC0, C1=0xC4, OWX=0xC8, OWY=0xCC, CKX=0xD0, CKY=0xD4, SLOT=0xD8, CP=0xEC, TC=0xF0)


def asm(src, at):
    from keystone import Ks, KS_ARCH_X86, KS_MODE_32
    src = "\n".join(l.split(";")[0].rstrip() for l in src.split("\n"))   # keystone hangs on comments
    return bytes(Ks(KS_ARCH_X86, KS_MODE_32).asm(src, at)[0])


def src(water=False):
    FR = 0x510 if water else 0x500
    v = {k: "dword ptr [edi + %#x]" % o for k, o in L.items()}
    def cmps(lo, hi):
        return "\n".join(
            "        movzx ecx, word ptr [esi + %#x]\n        and ecx, edx\n        cmp ecx, eax\n        je %s"
            % (k * 0x840, "kind0" if k < NSKY else "kind1" if k < NSKY + NCLR else "kind2") for k in range(lo, hi))
    if water:
        WATER_MODE = f"""        mov dword ptr [edi + {WONLY:#x}], 0
        cmp ecx, 2
        jne wmode
        mov dword ptr [edi + {WONLY:#x}], 1
        mov {v['MODE']}, 0
    wmode:"""
        DISPATCH = f"""        mov {v['HK']}, 0
        cmp ecx, 0xe
        je skyhex
        mov {v['HK']}, 1
        cmp ecx, 0xb
        je skyhex
        test ecx, ecx
        jne ynext
        cmp dword ptr [edi + {WONLY:#x}], 0
        je ynext
        call {EXT_WS:#x}
        test eax, eax
        je ynext
        mov {v['HK']}, 2
        jmp hexgo
    skyhex:
        cmp dword ptr [edi + {WONLY:#x}], 0
        jne ynext
        call {EXT_SKH:#x}"""
        WATER_ALL = f"""        cmp dword ptr [edi + {L['HK']:#x}], 1
        jne {EXT_WF:#x}"""
        # a water / ice hexagon whose shore uses a Sky-family set (side base >= 0xA0, Ziggurat's own test at
        # 0x55850B10): its sky-fog shore pixels are pure Sky / Clear / Chasm tile pixels -> clouds drift over them
        WATERSKY = ""                   # watersky / fogpix moved to the extension (sky_overlay_ext_asm, EXTRA)
        NOMATCH = "%#x" % EXT_SF
    else:
        WATER_MODE = ""
        DISPATCH = f"""        mov {v['HK']}, 0
        cmp ecx, 0xe
        je hexgo
        mov {v['HK']}, 1
        cmp ecx, 0xb
        jne ynext"""
        WATER_ALL = ""
        WATERSKY = ""
        NOMATCH = "pixnext"
    s = f"""
    main:
        push 0
        call core
        push ebx
        push esi
        mov esi, edx
        mov ebx, eax
        jmp {RESUME:#x}
    combat:
        push 1
        call core
        ret
    core:
        pushal
        sub esp, {FR:#x}
        mov edi, esp
        mov ecx, dword ptr [esp + {FR + 0x24:#x}]
        mov {v['MODE']}, ecx
{WATER_MODE}        call base
    base:
        pop ebp
        sub ebp, base
        mov {v['MAP']}, eax
        mov {v['DC']}, edx
        lea ecx, [edi + {CACHE:#x}]
        push edx
        mov edx, 64
    cinit:
        mov dword ptr [ecx], 0x80000001
        add ecx, 16
        dec edx
        jne cinit
        pop edx
        test edx, edx
        je done
        cmp {v['MODE']}, 0
        jne gmok
        cmp dword ptr [ebp + {GLOBAL_MAP:#x}], eax
        jne done
    gmok:
        mov ecx, dword ptr [edx + 0x28]
        mov {v['FMT']}, 0
        mov {v['MASK']}, 0xFFFF
        cmp ecx, 0x56509310
        je fmtok
        mov {v['FMT']}, 1
        mov {v['MASK']}, 0xFFDF
        cmp ecx, 0x55509310
        jne done
    fmtok:
        mov {v['SURF']}, 0
        cmp {v['MODE']}, 0
        jne timing
        cmp dword ptr [eax + 0x88], 3
        je firm
        mov dword ptr [ebp + {BSS_OK:#x}], 0
        jmp timing
    firm:
        cmp dword ptr [ebp + {BSS_MAP:#x}], eax
        jne rebuild
        cmp dword ptr [ebp + {BSS_FMT:#x}], ecx
        jne rebuild
        cmp dword ptr [ebp + {BSS_OK:#x}], 0
        jne cached
    rebuild:
        call {ZIG_CACHE:#x}
    cached:
        mov ecx, dword ptr [ebp + {BSS_BUF:#x}]
        test ecx, ecx
        je timing
        mov edx, dword ptr [ebp + {BSS_W:#x}]
        test edx, edx
        jle timing
        mov {v['SW']}, edx
        mov edx, dword ptr [ebp + {BSS_H:#x}]
        test edx, edx
        jle timing
        mov {v['SH']}, edx
        mov {v['SURF']}, ecx
        mov eax, {v['MAP']}
        mov ecx, dword ptr [eax + 0x80]
        mov edx, ecx
        sar edx, 2
        sub ecx, edx
        mov {v['PX']}, ecx
        mov ecx, dword ptr [eax + 0x84]
        mov edx, ecx
        sar edx, 2
        sub ecx, edx
        mov {v['PY']}, ecx
    timing:
        mov eax, dword ptr [ebp + {IAT_HSE_GETMAPLEVEL:#x}]
        sub eax, {HSE_GETMAPLEVEL:#x}
        mov eax, dword ptr [eax + {HSE_IAT_TIMEGETTIME:#x}]
        call eax
        mov {v['T']}, eax
        mov eax, {v['T']}
        mov ecx, {abs(A.SPEED['ox1'])}
        xor edx, edx
        div ecx
{'        neg eax' if A.SPEED['ox1'] < 0 else ''}
        mov {v['OX1']}, eax
        mov eax, {v['T']}
        mov ecx, {abs(A.SPEED['oy1'])}
        xor edx, edx
        div ecx
{'        neg eax' if A.SPEED['oy1'] < 0 else ''}
        mov {v['OY1']}, eax
        mov eax, {v['T']}
        mov ecx, {abs(A.SPEED['ox2'])}
        xor edx, edx
        div ecx
{'        neg eax' if A.SPEED['ox2'] < 0 else ''}
        mov {v['OX2']}, eax
        mov eax, {v['T']}
        mov ecx, {abs(A.SPEED['oy2'])}
        xor edx, edx
        div ecx
{'        neg eax' if A.SPEED['oy2'] < 0 else ''}
        mov {v['OY2']}, eax
        mov eax, {v['T']}
        mov ecx, {abs(A.SPEED['owx'])}
        xor edx, edx
        div ecx
{'        neg eax' if A.SPEED['owx'] < 0 else ''}
        mov {v['OWX']}, eax
        mov eax, {v['T']}
        mov ecx, {abs(A.SPEED['owy'])}
        xor edx, edx
        div ecx
{'        neg eax' if A.SPEED['owy'] < 0 else ''}
        mov {v['OWY']}, eax
        mov eax, {v['T']}
        mov ecx, {abs(A.SPEED['owx2'])}
        xor edx, edx
        div ecx
{'        neg eax' if A.SPEED['owx2'] < 0 else ''}
        mov {v['OWX2']}, eax
        mov eax, {v['T']}
        mov ecx, {abs(A.SPEED['owy2'])}
        xor edx, edx
        div ecx
{'        neg eax' if A.SPEED['owy2'] < 0 else ''}
        mov {v['OWY2']}, eax
        mov eax, {v['T']}
        mov ecx, {A.TWINKLE_MS}
        xor edx, edx
        div ecx
        mov {v['TW']}, eax
        mov eax, {v['T']}
        mov ecx, {A.FLASH_MS}
        xor edx, edx
        div ecx
        mov {v['TF']}, eax
        mov eax, {v['T']}
        mov ecx, {A.CPULSE_MS}
        xor edx, edx
        div ecx
        mov {v['TC']}, eax

        mov eax, {v['MAP']}
        mov edx, dword ptr [eax + 0x88]
        mov eax, dword ptr [eax + 0x10]
        call {GETLEVEL:#x}
        test eax, eax
        je done
        mov {v['LVL']}, eax
        mov eax, {v['MAP']}
        mov ecx, dword ptr [eax + 0x94]
        mov {v['X']}, ecx
        add ecx, dword ptr [eax + 0x9c]
        mov {v['XEND']}, ecx
        mov ecx, dword ptr [eax + 0x98]
        add ecx, dword ptr [eax + 0xa0]
        mov {v['YEND']}, ecx

    xloop:
        mov ecx, {v['X']}
        cmp ecx, {v['XEND']}
        jge done
        mov eax, {v['MAP']}
        mov edx, dword ptr [eax + 0x98]
        mov {v['Y']}, edx
    yloop:
        mov edx, {v['Y']}
        cmp edx, {v['YEND']}
        jge xnext
        mov ecx, {v['X']}
        mov ebx, {v['LVL']}
        test ecx, ecx
        js ynext
        test edx, edx
        js ynext
        cmp ecx, dword ptr [ebx + 0xc]
        jge ynext
        cmp edx, dword ptr [ebx + 0x10]
        jge ynext
        mov eax, dword ptr [ebx + 0x74]
        mov eax, dword ptr [eax + ecx*4]
        mov esi, dword ptr [ebx + 0x78]
        add eax, dword ptr [esi + edx*4]
        movzx ecx, byte ptr [eax + 0x14]
{DISPATCH}
    hexgo:
        call dohex
    ynext:
        inc {v['Y']}
        jmp yloop
    xnext:
        inc {v['X']}
        jmp xloop
    done:
        add esp, {FR:#x}
        popal
        ret 4

{WATERSKY}
    dohex:
        mov ecx, {v['X']}
        mov eax, ecx
        shl eax, 5
        mov {v['WX']}, eax
        mov edx, {v['Y']}
        shl edx, 5
        and ecx, 1
        shl ecx, 4
        add edx, ecx
        mov {v['WY']}, edx
        mov ebx, {v['MAP']}
        sub eax, dword ptr [ebx + 0x80]
        mov {v['SX']}, eax
        sub edx, dword ptr [ebx + 0x84]
        mov {v['SY']}, edx
        cmp {v['SURF']}, 0
        je nosurf
        mov eax, {v['WX']}
        sub eax, {v['PX']}
        cdq
        idiv {v['SW']}
        test edx, edx
        jge bxok
        add edx, {v['SW']}
    bxok:
        mov {v['BX']}, edx
        mov eax, {v['WY']}
        sub eax, {v['PY']}
        cdq
        idiv {v['SH']}
        test edx, edx
        jge byok
        add edx, {v['SH']}
    byok:
        mov {v['BY']}, edx
    nosurf:
        mov dword ptr [edi + {L['R']:#x}], 0
        mov dword ptr [edi + {L['K']:#x}], 0
    rowloop:
        mov ecx, dword ptr [edi + {L['R']:#x}]
        cmp ecx, 32
        jge hexdone
        movzx esi, byte ptr [ebp + ecx*2 + {SPAN:#x}]
        movzx eax, byte ptr [ebp + ecx*2 + {SPAN + 1:#x}]
        sub eax, esi
        mov dword ptr [edi + {L['NN']:#x}], eax
        mov ebx, dword ptr [edi + {L['DC']:#x}]
        mov eax, dword ptr [edi + {L['SY']:#x}]
        add eax, ecx
        cmp eax, dword ptr [ebx + 0x14]
        jl rownext
        cmp eax, dword ptr [ebx + 0x1c]
        jge rownext
        imul eax, dword ptr [ebx + 0xc]
        add eax, dword ptr [ebx + 0x20]
        mov edx, dword ptr [edi + {L['SX']:#x}]
        add edx, esi
        xor ecx, ecx
        cmp edx, dword ptr [ebx + 0x10]
        jge x0ok
        mov ecx, dword ptr [ebx + 0x10]
        sub ecx, edx
        mov edx, dword ptr [ebx + 0x10]
    x0ok:
        push ecx
        mov ecx, dword ptr [edi + {L['SX']:#x}]
        add ecx, esi
        add ecx, dword ptr [edi + {L['NN']:#x}]
        cmp ecx, dword ptr [ebx + 0x18]
        jle x1ok
        mov ecx, dword ptr [ebx + 0x18]
    x1ok:
        sub ecx, edx
        mov dword ptr [edi + {L['CNT']:#x}], ecx
        pop ecx
        cmp dword ptr [edi + {L['CNT']:#x}], 0
        jle rownext
        lea eax, [eax + edx*2]
        mov dword ptr [edi + {L['DST']:#x}], eax
        mov eax, dword ptr [edi + {L['K']:#x}]
        add eax, ecx
        mov dword ptr [edi + {L['I']:#x}], eax
        mov eax, dword ptr [edi + {L['WX']:#x}]
        add eax, esi
        add eax, ecx
        mov dword ptr [edi + {L['CWX']:#x}], eax
        mov eax, dword ptr [edi + {L['WY']:#x}]
        add eax, dword ptr [edi + {L['R']:#x}]
        mov dword ptr [edi + {L['CWY']:#x}], eax
        cmp dword ptr [edi + {L['SURF']:#x}], 0
        je pixloop
        mov eax, dword ptr [edi + {L['BY']:#x}]
        add eax, dword ptr [edi + {L['R']:#x}]
    bymod:
        cmp eax, dword ptr [edi + {L['SH']:#x}]
        jl bymodok
        sub eax, dword ptr [edi + {L['SH']:#x}]
        jmp bymod
    bymodok:
        imul eax, dword ptr [edi + {L['SW']:#x}]
        shl eax, 1
        add eax, dword ptr [edi + {L['SURF']:#x}]
        mov dword ptr [edi + {L['BROW']:#x}], eax
        mov eax, dword ptr [edi + {L['BX']:#x}]
        add eax, esi
        add eax, ecx
    bxmod:
        cmp eax, dword ptr [edi + {L['SW']:#x}]
        jl bxmodok
        sub eax, dword ptr [edi + {L['SW']:#x}]
        jmp bxmod
    bxmodok:
        mov dword ptr [edi + {L['BCOL']:#x}], eax

    pixloop:
        mov ebx, dword ptr [edi + {L['DST']:#x}]
        movzx eax, word ptr [ebx]
        cmp dword ptr [edi + {L['FMT']:#x}], 0
        je keyok
        mov ecx, eax
        and ecx, 0x1f
        and eax, 0x7fe0
        shl eax, 1
        or eax, ecx
    keyok:
        mov dword ptr [edi + {L['KEY']:#x}], eax
        mov esi, dword ptr [edi + {L['I']:#x}]
        lea esi, [ebp + esi*2 + {TBL:#x}]
        mov edx, dword ptr [edi + {L['MASK']:#x}]
        cmp dword ptr [edi + {L['HK']:#x}], 0
        jne chkchasm
{cmps(0, NSKY + NCLR)}
        jmp {NOMATCH}
    chkchasm:
{WATER_ALL}
{cmps(NSKY + NCLR, NVAR)}
        jmp {NOMATCH}
    kind2:
        mov dword ptr [edi + {L['KIND']:#x}], 2
        jmp shade
    kind0:
        mov dword ptr [edi + {L['KIND']:#x}], 0
        cmp dword ptr [edi + {L['MODE']:#x}], 0
        je shade
        cmp byte ptr [ebp + {CCLEAR:#x}], 0
        je shade
        mov eax, dword ptr [edi + {L['X']:#x}]
        imul eax, eax, 3
        add eax, dword ptr [edi + {L['Y']:#x}]
        and eax, 3
        add eax, {NSKY}
        imul eax, eax, 0x840
        mov ecx, dword ptr [edi + {L['I']:#x}]
        lea eax, [eax + ecx*2]
        movzx eax, word ptr [ebp + eax + {TBL:#x}]
        mov dword ptr [edi + {L['KEY']:#x}], eax
        mov dword ptr [edi + {L['KIND']:#x}], 1
        jmp shade
    kind1:
        mov dword ptr [edi + {L['KIND']:#x}], 1
    shade:
        call pixel
    pixnext:
        add dword ptr [edi + {L['DST']:#x}], 2
        inc dword ptr [edi + {L['I']:#x}]
        inc dword ptr [edi + {L['CWX']:#x}]
        mov eax, dword ptr [edi + {L['BCOL']:#x}]
        inc eax
        cmp eax, dword ptr [edi + {L['SW']:#x}]
        jl bcolok
        xor eax, eax
    bcolok:
        mov dword ptr [edi + {L['BCOL']:#x}], eax
        dec dword ptr [edi + {L['CNT']:#x}]
        jne pixloop
    rownext:
        mov eax, dword ptr [edi + {L['NN']:#x}]
        add dword ptr [edi + {L['K']:#x}], eax
        inc dword ptr [edi + {L['R']:#x}]
        jmp rowloop
    hexdone:
        ret

    pixel:
        mov eax, dword ptr [edi + {L['CWX']:#x}]
        and eax, -4
        mov ecx, dword ptr [edi + {L['CWY']:#x}]
        and ecx, -2
        mov edx, eax
        shr edx, 2
        and edx, 63
        shl edx, 4
        cmp eax, dword ptr [edi + edx + {CACHE:#x}]
        jne crecalc
        cmp ecx, dword ptr [edi + edx + {CACHE + 4:#x}]
        jne crecalc
        mov eax, dword ptr [edi + edx + {CACHE + 8:#x}]
        mov dword ptr [edi + {L['C']:#x}], eax
        mov eax, dword ptr [edi + edx + {CACHE + 12:#x}]
        mov dword ptr [edi + {L['CP']:#x}], eax
        jmp chave
    crecalc:
        mov dword ptr [edi + edx + {CACHE:#x}], eax
        mov dword ptr [edi + edx + {CACHE + 4:#x}], ecx
        mov dword ptr [edi + {L['SLOT']:#x}], edx
        mov dword ptr [edi + {L['CKX']:#x}], eax
        mov dword ptr [edi + {L['CKY']:#x}], ecx
        shl eax, 4
        add eax, dword ptr [edi + {L['OX1']:#x}]
        mov edx, dword ptr [edi + {L['CKY']:#x}]
        shl edx, 4
        add edx, dword ptr [edi + {L['OY1']:#x}]
        mov ecx, 1
        lea esi, [ebp + {TEX:#x}]
        call bil
        mov dword ptr [edi + {L['C1']:#x}], eax
        mov eax, dword ptr [edi + {L['CKX']:#x}]
        shl eax, 4
        add eax, dword ptr [edi + {L['OX2']:#x}]
        mov edx, dword ptr [edi + {L['CKY']:#x}]
        shl edx, 4
        add edx, dword ptr [edi + {L['OY2']:#x}]
        mov ecx, 2
        lea esi, [ebp + {TEX:#x}]
        call bil
        add eax, dword ptr [edi + {L['C1']:#x}]
        shr eax, 1
        mov dword ptr [edi + {L['C']:#x}], eax
        mov edx, dword ptr [edi + {L['SLOT']:#x}]
        mov dword ptr [edi + edx + {CACHE + 8:#x}], eax
        mov eax, dword ptr [edi + {L['CKX']:#x}]
        shl eax, 4
        add eax, dword ptr [edi + {L['OX2']:#x}]
        mov edx, dword ptr [edi + {L['CKY']:#x}]
        shl edx, 4
        add edx, dword ptr [edi + {L['OY2']:#x}]
        mov ecx, 3
        lea esi, [ebp + {TEX:#x}]
        call bil
        shr eax, 2
        add eax, dword ptr [edi + {L['TC']:#x}]
        and eax, 63
        movzx eax, byte ptr [ebp + eax + {CPUL:#x}]
        mov dword ptr [edi + {L['CP']:#x}], eax
        mov edx, dword ptr [edi + {L['SLOT']:#x}]
        mov dword ptr [edi + edx + {CACHE + 12:#x}], eax
    chave:

        mov eax, dword ptr [edi + {L['KEY']:#x}]
        mov ecx, eax
        shr ecx, 11
        mov dword ptr [edi + {L['RR']:#x}], ecx
        mov ecx, eax
        shr ecx, 5
        and ecx, 63
        mov dword ptr [edi + {L['GG']:#x}], ecx
        and eax, 31
        mov dword ptr [edi + {L['BB']:#x}], eax

        cmp dword ptr [edi + {L['KIND']:#x}], 2
        je chasm
        cmp dword ptr [edi + {L['KIND']:#x}], 0
        jne notwinkle
        mov eax, dword ptr [edi + {L['GG']:#x}]
        shr eax, 1
        add eax, dword ptr [edi + {L['RR']:#x}]
        add eax, dword ptr [edi + {L['BB']:#x}]
        cmp eax, {A.STAR_MIN}
        jl notwinkle
        mov eax, dword ptr [edi + {L['CWX']:#x}]
        shr eax, 1
        imul eax, eax, 7
        mov ecx, dword ptr [edi + {L['CWY']:#x}]
        shr ecx, 1
        imul ecx, ecx, 13
        add eax, ecx
        add eax, dword ptr [edi + {L['TW']:#x}]
        and eax, 63
        movzx ecx, byte ptr [ebp + eax + {TWT:#x}]
        mov eax, dword ptr [edi + {L['RR']:#x}]
        imul eax, ecx
        shr eax, 8
        mov dword ptr [edi + {L['RR']:#x}], eax
        mov eax, dword ptr [edi + {L['GG']:#x}]
        imul eax, ecx
        shr eax, 8
        mov dword ptr [edi + {L['GG']:#x}], eax
        mov eax, dword ptr [edi + {L['BB']:#x}]
        imul eax, ecx
        shr eax, 8
        mov dword ptr [edi + {L['BB']:#x}], eax
    notwinkle:
        cmp dword ptr [edi + {L['SURF']:#x}], 0
        je nosp
        mov eax, dword ptr [edi + {L['BCOL']:#x}]
        mov ecx, dword ptr [edi + {L['BROW']:#x}]
        movzx eax, word ptr [ecx + eax*2]
        test eax, eax
        je nosp
        cmp dword ptr [edi + {L['FMT']:#x}], 0
        je spok
        mov ecx, eax
        and ecx, 0x1f
        and eax, 0x7fe0
        shl eax, 1
        or eax, ecx
    spok:
        mov ebx, dword ptr [edi + {L['KIND']:#x}]
        mov ebx, dword ptr [ebp + ebx*4 + {CONST + 0x24:#x}]
        mov esi, 256
        sub esi, ebx
        mov ecx, eax
        shr ecx, 11
        imul ecx, ebx
        mov edx, dword ptr [edi + {L['RR']:#x}]
        imul edx, esi
        add ecx, edx
        shr ecx, 8
        mov dword ptr [edi + {L['RR']:#x}], ecx
        mov ecx, eax
        shr ecx, 5
        and ecx, 63
        imul ecx, ebx
        mov edx, dword ptr [edi + {L['GG']:#x}]
        imul edx, esi
        add ecx, edx
        shr ecx, 8
        mov dword ptr [edi + {L['GG']:#x}], ecx
        mov ecx, eax
        and ecx, 31
        imul ecx, ebx
        mov edx, dword ptr [edi + {L['BB']:#x}]
        imul edx, esi
        add ecx, edx
        shr ecx, 8
        mov dword ptr [edi + {L['BB']:#x}], ecx
    nosp:
        mov ebx, dword ptr [edi + {L['KIND']:#x}]
        mov eax, ebx
        shl eax, 8
        add eax, dword ptr [edi + {L['C']:#x}]
        movzx esi, byte ptr [ebp + eax + {LUT:#x}]
        mov eax, esi
        imul eax, dword ptr [edi + {L['CP']:#x}]
        shr eax, 8
        imul eax, eax, {A.CP_SKY}
        shr eax, 8
        add esi, eax
        jmp blend

    chasm:
        mov eax, dword ptr [edi + {L['C']:#x}]
        movzx esi, byte ptr [ebp + eax + {LUT + 0x400:#x}]
        mov eax, dword ptr [ebp + {CONST + 0x30:#x}]
        sub eax, dword ptr [edi + {L['RR']:#x}]
        imul eax, esi
        sar eax, 8
        add dword ptr [edi + {L['RR']:#x}], eax
        mov eax, dword ptr [ebp + {CONST + 0x34:#x}]
        sub eax, dword ptr [edi + {L['GG']:#x}]
        imul eax, esi
        sar eax, 8
        add dword ptr [edi + {L['GG']:#x}], eax
        mov eax, dword ptr [ebp + {CONST + 0x38:#x}]
        sub eax, dword ptr [edi + {L['BB']:#x}]
        imul eax, esi
        sar eax, 8
        add dword ptr [edi + {L['BB']:#x}], eax
        mov eax, dword ptr [edi + {L['C']:#x}]
        movzx esi, byte ptr [ebp + eax + {LUT + 0x200:#x}]
        mov eax, esi
        imul eax, dword ptr [edi + {L['CP']:#x}]
        shr eax, 8
        imul eax, eax, {A.CP_CHS}
        shr eax, 8
        sub esi, eax
        mov eax, dword ptr [edi + {L['RR']:#x}]
        imul eax, esi
        shr eax, 8
        sub dword ptr [edi + {L['RR']:#x}], eax
        mov eax, dword ptr [edi + {L['GG']:#x}]
        imul eax, esi
        shr eax, 8
        sub dword ptr [edi + {L['GG']:#x}], eax
        mov eax, dword ptr [edi + {L['BB']:#x}]
        imul eax, esi
        shr eax, 8
        sub dword ptr [edi + {L['BB']:#x}], eax
        mov eax, dword ptr [edi + {L['CWY']:#x}]
        shr eax, 3
        and eax, 0xff
        shl eax, 8
        mov ecx, dword ptr [edi + {L['CWX']:#x}]
        shr ecx, 3
        and ecx, 0xff
        add eax, ecx
        movzx eax, byte ptr [ebp + eax + {TEX:#x}]
        shr eax, 2
        mov dword ptr [edi + {L['PH']:#x}], eax
        add eax, dword ptr [edi + {L['TF']:#x}]
        and eax, 63
        movzx eax, byte ptr [ebp + eax + {FLASH:#x}]
        mov dword ptr [edi + {L['FL']:#x}], eax
        mov eax, dword ptr [edi + {L['CWY']:#x}]
        shl eax, 5
        add eax, dword ptr [edi + {L['OWY2']:#x}]
        sar eax, 4
        and eax, 0xff
        shl eax, 8
        mov ecx, dword ptr [edi + {L['CWX']:#x}]
        shl ecx, 5
        add ecx, dword ptr [edi + {L['OWX2']:#x}]
        sar ecx, 4
        and ecx, 0xff
        add eax, ecx
        movzx eax, byte ptr [ebp + eax + {WEB:#x}]
        movzx esi, byte ptr [ebp + eax + {LUT + 0x300:#x}]
        mov eax, dword ptr [edi + {L['PH']:#x}]
        add eax, dword ptr [edi + {L['TF']:#x}]
        add eax, 21
        and eax, 63
        movzx eax, byte ptr [ebp + eax + {FLASH:#x}]
        imul esi, eax
        shr esi, 8
        imul esi, esi, {A.WEB2_K}
        shr esi, 8
        mov eax, dword ptr [ebp + {CONST + 0x3c:#x}]
        sub eax, dword ptr [edi + {L['RR']:#x}]
        imul eax, esi
        sar eax, 8
        add dword ptr [edi + {L['RR']:#x}], eax
        mov eax, dword ptr [ebp + {CONST + 0x40:#x}]
        sub eax, dword ptr [edi + {L['GG']:#x}]
        imul eax, esi
        sar eax, 8
        add dword ptr [edi + {L['GG']:#x}], eax
        mov eax, dword ptr [ebp + {CONST + 0x44:#x}]
        sub eax, dword ptr [edi + {L['BB']:#x}]
        imul eax, esi
        sar eax, 8
        add dword ptr [edi + {L['BB']:#x}], eax
        mov eax, dword ptr [edi + {L['CWY']:#x}]
        shl eax, 4
        add eax, dword ptr [edi + {L['OWY']:#x}]
        sar eax, 4
        and eax, 0xff
        shl eax, 8
        mov ecx, dword ptr [edi + {L['CWX']:#x}]
        shl ecx, 4
        add ecx, dword ptr [edi + {L['OWX']:#x}]
        sar ecx, 4
        and ecx, 0xff
        add eax, ecx
        movzx eax, byte ptr [ebp + eax + {WEB:#x}]
        movzx esi, byte ptr [ebp + eax + {LUT + 0x300:#x}]
        imul esi, dword ptr [edi + {L['FL']:#x}]
        shr esi, 8
        mov ebx, 2

    blend:
        imul ebx, ebx, 12
        mov eax, dword ptr [ebp + ebx + {CONST:#x}]
        sub eax, dword ptr [edi + {L['RR']:#x}]
        imul eax, esi
        sar eax, 8
        add eax, dword ptr [edi + {L['RR']:#x}]
        shl eax, 11
        mov ecx, eax
        mov eax, dword ptr [ebp + ebx + {CONST + 4:#x}]
        sub eax, dword ptr [edi + {L['GG']:#x}]
        imul eax, esi
        sar eax, 8
        add eax, dword ptr [edi + {L['GG']:#x}]
        shl eax, 5
        or ecx, eax
        mov eax, dword ptr [ebp + ebx + {CONST + 8:#x}]
        sub eax, dword ptr [edi + {L['BB']:#x}]
        imul eax, esi
        sar eax, 8
        add eax, dword ptr [edi + {L['BB']:#x}]
        or ecx, eax
        cmp dword ptr [edi + {L['FMT']:#x}], 0
        je outok
        mov eax, ecx
        and eax, 0x1f
        shr ecx, 1
        and ecx, 0x7fe0
        or ecx, eax
    outok:
        mov eax, dword ptr [edi + {L['DST']:#x}]
        mov word ptr [eax], cx
        ret

    bil:
        mov ebx, eax
        sar ebx, cl
        and ebx, 15
        mov dword ptr [edi + {L['BFX']:#x}], ebx
        add ecx, 4
        sar eax, cl
        and eax, 0xff
        mov dword ptr [edi + {L['BIX']:#x}], eax
        sub ecx, 4
        mov ebx, edx
        sar ebx, cl
        and ebx, 15
        mov dword ptr [edi + {L['BFY']:#x}], ebx
        add ecx, 4
        sar edx, cl
        and edx, 0xff
        shl edx, 8
        mov ecx, dword ptr [edi + {L['BIX']:#x}]
        add esi, edx
        movzx eax, byte ptr [esi + ecx]
        inc ecx
        and ecx, 0xff
        movzx ebx, byte ptr [esi + ecx]
        sub ebx, eax
        imul ebx, dword ptr [edi + {L['BFX']:#x}]
        shl eax, 4
        add eax, ebx
        mov dword ptr [edi + {L['BTOP']:#x}], eax
        sub esi, edx
        add edx, 0x100
        and edx, 0xff00
        add esi, edx
        mov ecx, dword ptr [edi + {L['BIX']:#x}]
        movzx eax, byte ptr [esi + ecx]
        inc ecx
        and ecx, 0xff
        movzx ebx, byte ptr [esi + ecx]
        sub ebx, eax
        imul ebx, dword ptr [edi + {L['BFX']:#x}]
        shl eax, 4
        add eax, ebx
        sub eax, dword ptr [edi + {L['BTOP']:#x}]
        imul eax, dword ptr [edi + {L['BFY']:#x}]
        mov ebx, dword ptr [edi + {L['BTOP']:#x}]
        shl ebx, 4
        add eax, ebx
        sar eax, 8
        ret
    .long main
    .long combat
"""
    return s


def data(game_dir):
    """(span, luts, twinkle, pulse, consts, tables, texture) bytes"""
    span = bytes(b for s, e in A.SPANS for b in (s, e))
    lu = A.luts()
    tiles = A.sky_tiles() + A.clear_tiles() + A.chasm_tiles(game_dir)
    assert len(tiles) == NVAR
    tbl = b"".join(struct.pack("<%dH" % A.NPIX, *A.packed(t)) for t in tiles)
    c = []
    for col in (A.SKY_CLOUD, A.CLR_CLOUD, A.CHS_GLOW):
        c += [col[0] >> 3, col[1] >> 2, col[2] >> 3]
    const = struct.pack("<9I", *c) + struct.pack("<3I", A.SKY_SURF, A.CLR_SURF, 0) + \
        struct.pack("<3I", A.CHS_HAZE[0] >> 3, A.CHS_HAZE[1] >> 2, A.CHS_HAZE[2] >> 3) + \
        struct.pack("<3I", A.CHS_WEB2[0] >> 3, A.CHS_WEB2[1] >> 2, A.CHS_WEB2[2] >> 3) + \
        struct.pack("<3I", A.CHS_CGLOW[0] >> 3, A.CHS_CGLOW[1] >> 2, A.CHS_CGLOW[2] >> 3)
    return span, lu["sky"] + lu["clear"] + lu["dark"] + lu["web"] + lu["haze"], lu["twinkle"], lu["flash"], const, tbl, \
        A.cloud_tex().tobytes(), A.web_tex().tobytes()


def labels_va(water=False):
    """(pixel, pixnext) VAs of the main overlay code - the extension calls / jumps back to them"""
    full = asm(src(water) + "    .long pixel" + chr(10) + "    .long pixnext" + chr(10), ZONE + 0x10)
    return struct.unpack("<2I", full[-8:])


def core_va(water=False):
    """VA of the shared per-frame routine 'core' (eax map, edx draw context, push mode; ret 4)"""
    full = asm(src(water) + "    .long core" + chr(10), ZONE + 0x10)
    return struct.unpack("<I", full[-4:])[0]


def blob(game_dir, water=False):
    """(zone image ZONE..END, cloud texture, web texture, {'main','combat'} entry VAs)"""
    full = asm(src(water), ZONE + 0x10)
    ents = dict(zip(("main", "combat"), struct.unpack("<2I", full[-8:])))
    code = full[:-8]
    assert ents["main"] == ZONE + 0x10 and 0x10 + len(code) <= SPAN - ZONE, hex(len(code))
    span, lut, tw, pulse, const, tbl, tex, web = data(game_dir)
    z = bytearray(END - ZONE)
    z[0:4] = MAGIC
    z[0x10:0x10 + len(code)] = code
    for at, b in ((SPAN, span), (LUT, lut), (TWT, tw), (FLASH, pulse), (CONST, const), (TBL, tbl),
                  (CPUL, A.luts()["cpulse"])):
        z[at - ZONE:at - ZONE + len(b)] = b
    assert len(tex) == len(web) == 0x10000 and len(lut) == 0x500 and len(tw) == 64 and len(pulse) == 64
    assert len(const) == 0x54 and CONST + 0x54 <= TBL
    return bytes(z), tex, web, ents
