#!/usr/bin/env python3
r"""
Sky overlay - EXTENSION code (2026-11-07), lives at EXTRA 0x558DB000..0x558DC000 (AoWEPACK CODE, zero/unclaimed,
right after the overlay's tile tables).  Only used by the overlay's water build (sky_clouds_overlay_asm.src(True)),
installed by patch_sky_overlay_water_v1.

User: "sky/clear sky transition needs the same cloud fix" (clouds drift into the transition band).

Fixed jump table at EXTRA (the main overlay reaches it by absolute address):
  +0x00 watersky   eax = map field -> eax 1 if a water hexagon whose shore uses a Sky-family set (FOG_K = fog kind,
                   FOG_WP = water mean colour pack); 0 otherwise
  +0x05 waterfog   per pixel of such a hex (no exact tile match): line WATER(mean) -> each sky kind's tile pixel,
                   best fit wins (v2.9b: per-edge fog wedges - one water hex can carry Sky, Clear and Chasm fog)
  +0x0A skyfog     per pixel of a Sky / Clear / Chasm hex without an exact tile match: line OWN tile pixel -> each
                   OTHER sky kind's tile pixel (the pair-transition cross-fade is exactly such a mix, sampled at the
                   same tile index), best-fitting line wins
  +0x0F skyhex     eax = map field -> FOG_K = own kind (0 Sky / 1 Clear / 2 Chasm)
Line fog: p = A + t (B - A) (+ texture noise), in 5/6/5 x4 units; t = (p-A).(B-A) / |B-A|^2; residual check keeps
units / foreign pixels untouched; t > 1.06 = already clouded (hex tiles overlap 1 px) -> skip.
out = p + (1-t)(cloud(A) - A) + t (cloud(B) - B), cloud() = the overlay's own pixel model (PIXEL with KEY/KIND); for
water A has no cloud.  Block on the stack (0x30): +4 t, +8 A565, +0xC kindA (-1 none), +0x10 B565, +0x14 kindB,
+0x18/+0x1C/+0x20 r/g/b accumulators (x256), +0x24.. skyfog scratch.
"""
import struct

import sky_clouds_overlay_asm as OV

EXTRA, EXTRA_END = 0x558DB000, 0x558DC000
EXT_WS, EXT_WF, EXT_SF, EXT_SKH = EXTRA, EXTRA + 5, EXTRA + 10, EXTRA + 15
CLEAR_RID_HI = 0x5A1B
PROBES = ("watersky", "waterfog", "skyfog", "skyhex", "leval", "apply", "addd", "to4", "tblpix", "cloudof", "kindof",
          "nbk")
CODE0 = EXTRA + 0x20             # the 4 x 5-byte jump table is built by hand (keystone emits short jmps)
# v2.9 (user: "a dirt hex on sky connected to a bridge has a faint chasm lightning animation"): dark cliff pixels
# inside a Chasm hex fitted the Chasm->Sky line under the loose water residual -> got the Chasm lightning.  skyfog
# now (1) only runs on pixels within EDGE_R px of an edge whose neighbour is a DIFFERENT sky kind (all 6 edges: the
# symmetric pair fades also spill into the upper hex), (2) uses SKYFOG_MAXRES (pair-fade pixels: 99.9 % <= 96).
EM = 0x504                       # frame local (water build frame 0x510): edge mask bit e = edge e (UL, top, UR, LR,
                                 # bottom, LL) borders a DIFFERENT sky kind
SKYFOG_MAXRES = 0x60
# v2.9b (user: "the dirt hex between bridges ... has one small flashing spot still"): a sky hex that hangs cliff faces
# (land at its UL / top / UR / LL - Ziggurat block A) and borders another sky kind: a near-black cliff pixel fits the
# own->Chasm line at t ~ 1 -> lightning.  EM bit HANG marks such hexes; there pixels with t > HANG_TMAX stay static.
HANG, HANG_TMAX = 0x40, 0xC0
EDGE_R = 20.0
EDGETBL = EXTRA + 0xB00          # NPIX bytes, per hex-span pixel index: bit e = within EDGE_R of edge e


def edge_table():
    import sky_clouds_art as SA
    edges = [((0.0, 15.5), (15.0, -0.5)), ((15.0, -0.5), (33.0, -0.5)), ((33.0, -0.5), (48.0, 15.5)),
             ((48.0, 15.5), (33.0, 31.5)), ((33.0, 31.5), (15.0, 31.5)), ((15.0, 31.5), (0.0, 15.5))]
    out = bytearray()
    for r, (s0, e0) in enumerate(SA.SPANS):
        for x in range(s0, e0):
            px, py = x + 0.5, r + 0.5
            m = 0
            for e, ((ax, ay), (bx, by)) in enumerate(edges):
                ex, ey = bx - ax, by - ay
                t = min(1.0, max(0.0, ((px - ax) * ex + (py - ay) * ey) / (ex * ex + ey * ey)))
                if ((px - ax - t * ex) ** 2 + (py - ay - t * ey) ** 2) ** 0.5 <= EDGE_R:
                    m |= 1 << e
            out.append(m)
    assert len(out) == SA.NPIX
    return bytes(out)


def src(pixel, pixnext):
    L = OV.L
    K, WP, PK = OV.FOG_K, OV.FOG_WP, OV.FOG_PK
    TBL, NSKY, NCLR = OV.TBL, OV.NSKY, OV.NCLR

    def chan(sh, dst_vs, dst_vp):
        return f"""
        mov eax, ecx
        shr eax, {sh:#x}
        and eax, 0xff
        mov edx, ebx
        shr edx, {sh:#x}
        and edx, 0xff
        sub eax, edx
        mov dword ptr [esp + {dst_vs:#x}], eax
        mov eax, esi
        shr eax, {sh:#x}
        and eax, 0xff
        sub eax, edx
        mov dword ptr [esp + {dst_vp:#x}], eax"""

    def addch(shift, mask, acc):
        return f"""
        mov eax, esi
        shr eax, {shift:#x}
        and eax, {mask:#x}
        push ecx
        shr ecx, {shift:#x}
        and ecx, {mask:#x}
        sub eax, ecx
        pop ecx
        imul eax, ebx
        add dword ptr [edx + {acc:#x}], eax"""

    def outch(shift, mask, acc):
        return f"""
        mov eax, esi
        shr eax, {shift:#x}
        and eax, {mask:#x}
        mov ecx, dword ptr [edx + {acc:#x}]
        sar ecx, 0x8
        add eax, ecx
        jns oc{shift}a
        xor eax, eax
    oc{shift}a:
        cmp eax, {mask:#x}
        jle oc{shift}b
        mov eax, {mask:#x}
    oc{shift}b:
        shl eax, {shift:#x}
        or ebx, eax"""

    return f"""
    watersky:
        movzx ecx, byte ptr [eax + 0x14]
        mov dword ptr [edi + {WP:#x}], {OV.WPACK_WATER:#x}
        cmp ecx, 0x6
        jne wsk_w
        mov dword ptr [edi + {WP:#x}], {OV.WPACK_ICE:#x}
    wsk_w:
        mov esi, eax
        movzx ecx, byte ptr [esi + 0xd]
        mov esi, dword ptr [esi + 0x8]
    wsk_l:
        dec ecx
        js wsk_no
        mov eax, dword ptr [esi + ecx*4]
        test eax, eax
        je wsk_l
        mov edx, dword ptr [eax]
        sub edx, ebp
        cmp edx, {OV.WATER_VMT:#x}
        jne wsk_l
        movzx edx, byte ptr [eax + 0x14]
        xor ecx, ecx
        xor esi, esi
    wsk_d:
        bt edx, ecx
        jae wsk_n
        movzx ebx, byte ptr [eax + ecx + 0x1a]
        cmp ebx, esi
        jbe wsk_n
        mov esi, ebx
    wsk_n:
        inc ecx
        cmp ecx, 0x6
        jb wsk_d
        cmp esi, 0xa0
        jb wsk_no
        mov dword ptr [edi + {K:#x}], 0x0
        cmp esi, 0xc0
        jb wsk_yes
        mov dword ptr [edi + {K:#x}], 0x2
        cmp esi, 0xe0
        jb wsk_yes
        mov dword ptr [edi + {K:#x}], 0x1
    wsk_yes:
        mov eax, 0x1
        ret
    wsk_no:
        xor eax, eax
        ret

    skyhex:
        call kindof
        mov dword ptr [edi + {K:#x}], eax
        mov dword ptr [edi + {EM:#x}], 0
        push ebx
        mov ecx, dword ptr [edi + {L['X']:#x}]
        and ecx, 1
        mov edx, dword ptr [edi + {L['Y']:#x}]
        lea edx, [edx + ecx - 1]
        mov ecx, dword ptr [edi + {L['X']:#x}]
        dec ecx
        mov ebx, 1
        call nbk
        mov ecx, dword ptr [edi + {L['X']:#x}]
        mov edx, dword ptr [edi + {L['Y']:#x}]
        dec edx
        mov ebx, 2
        call nbk
        mov ecx, dword ptr [edi + {L['X']:#x}]
        and ecx, 1
        mov edx, dword ptr [edi + {L['Y']:#x}]
        lea edx, [edx + ecx - 1]
        mov ecx, dword ptr [edi + {L['X']:#x}]
        inc ecx
        mov ebx, 4
        call nbk
        mov ecx, dword ptr [edi + {L['X']:#x}]
        and ecx, 1
        mov edx, dword ptr [edi + {L['Y']:#x}]
        add edx, ecx
        mov ecx, dword ptr [edi + {L['X']:#x}]
        inc ecx
        mov ebx, 8
        call nbk
        mov ecx, dword ptr [edi + {L['X']:#x}]
        mov edx, dword ptr [edi + {L['Y']:#x}]
        inc edx
        mov ebx, 0x10
        call nbk
        mov ecx, dword ptr [edi + {L['X']:#x}]
        and ecx, 1
        mov edx, dword ptr [edi + {L['Y']:#x}]
        add edx, ecx
        mov ecx, dword ptr [edi + {L['X']:#x}]
        dec ecx
        mov ebx, 0x20
        call nbk
        pop ebx
        ret

    nbk:
        test ecx, ecx
        js nb_r
        test edx, edx
        js nb_r
        mov eax, dword ptr [edi + {L['LVL']:#x}]
        cmp ecx, dword ptr [eax + 0xc]
        jge nb_r
        cmp edx, dword ptr [eax + 0x10]
        jge nb_r
        mov esi, dword ptr [eax + 0x74]
        mov esi, dword ptr [esi + ecx*4]
        mov eax, dword ptr [eax + 0x78]
        add esi, dword ptr [eax + edx*4]
        mov eax, esi
        call kindof
        test eax, eax
        jns nb_sky
        test ebx, 0x27
        je nb_r
        movzx eax, byte ptr [esi + 0x14]
        cmp eax, 0xf
        ja nb_r
        mov ecx, 0x103e
        bt ecx, eax
        jae nb_r
        or dword ptr [edi + {EM:#x}], {HANG:#x}
        ret
    nb_sky:
        cmp eax, dword ptr [edi + {K:#x}]
        je nb_r
        or dword ptr [edi + {EM:#x}], ebx
    nb_r:
        ret

    kindof:
        movzx ecx, byte ptr [eax + 0x14]
        cmp ecx, 0xb
        jne ko_1
        mov eax, 0x2
        ret
    ko_1:
        cmp ecx, 0xe
        je ko_2
        or eax, 0xffffffff
        ret
    ko_2:
        movzx ecx, byte ptr [eax + 0xd]
        mov esi, dword ptr [eax + 0x8]
    ko_l:
        dec ecx
        js ko_0
        mov eax, dword ptr [esi + ecx*4]
        cmp eax, 0x10000
        jb ko_l
        mov eax, dword ptr [eax + 0x8]
        cmp eax, 0x10000
        jb ko_l
        mov eax, dword ptr [eax + 0xc]
        shr eax, 0x10
        cmp eax, {CLEAR_RID_HI:#x}
        jne ko_l
        mov eax, 0x1
        ret
    ko_0:
        xor eax, eax
        ret

    tblpix:
        xor eax, eax
        cmp ecx, 0x1
        jne tp_2
        mov eax, {NSKY:#x}
    tp_2:
        cmp ecx, 0x2
        jne tp_3
        mov eax, {NSKY + NCLR:#x}
    tp_3:
        imul eax, eax, 0x840
        mov ecx, dword ptr [edi + {L['I']:#x}]
        lea eax, [eax + ecx*2]
        movzx eax, word ptr [ebp + eax + {TBL:#x}]
        ret

    to4:
        mov ecx, eax
        shr ecx, 0xb
        shl ecx, 0x2
        mov edx, eax
        shr edx, 0x5
        and edx, 0x3f
        shl edx, 0xa
        or ecx, edx
        and eax, 0x1f
        shl eax, 0x12
        or eax, ecx
        ret

    leval:
        push edi
        sub esp, 0x20
{chan(0, 0x0, 0x10)}
{chan(8, 0x4, 0x14)}
{chan(16, 0x8, 0x18)}
        mov eax, dword ptr [esp]
        imul eax, eax
        mov edx, dword ptr [esp + 0x4]
        imul edx, edx
        add eax, edx
        mov edx, dword ptr [esp + 0x8]
        imul edx, edx
        add eax, edx
        cmp eax, {OV.FOG_MINDEN:#x}
        jl le_bad
        mov edi, eax
        mov eax, dword ptr [esp]
        imul eax, dword ptr [esp + 0x10]
        mov edx, dword ptr [esp + 0x4]
        imul edx, dword ptr [esp + 0x14]
        add eax, edx
        mov edx, dword ptr [esp + 0x8]
        imul edx, dword ptr [esp + 0x18]
        add eax, edx
        test eax, eax
        jle le_bad
        shl eax, 0x8
        cdq
        idiv edi
        cmp eax, 0x110
        jg le_bad
        cmp eax, 0x100
        jle le_t
        mov eax, 0x100
    le_t:
        cmp eax, 0x10
        jl le_bad
        mov dword ptr [esp + 0x1c], eax
        xor edi, edi
        mov edx, 0x8
    le_r:
        mov eax, dword ptr [esp + edx]
        imul eax, dword ptr [esp + 0x1c]
        sar eax, 0x8
        sub eax, dword ptr [esp + edx + 0x10]
        imul eax, eax
        add edi, eax
        sub edx, 0x4
        jns le_r
        mov edx, edi
        mov eax, dword ptr [esp + 0x1c]
        jmp le_out
    le_bad:
        mov eax, 0xffffffff
        mov edx, 0x7fffffff
    le_out:
        add esp, 0x20
        pop edi
        ret

    cloudof:
        push ecx
        mov dword ptr [edi + {L['KEY']:#x}], eax
        mov dword ptr [edi + {L['KIND']:#x}], ecx
        call {pixel:#x}
        mov eax, dword ptr [edi + {L['DST']:#x}]
        movzx eax, word ptr [eax]
        cmp dword ptr [edi + {L['FMT']:#x}], 0
        je co_k
        mov ecx, eax
        and ecx, 0x1f
        and eax, 0x7fe0
        shl eax, 1
        or eax, ecx
    co_k:
        pop ecx
        mov ecx, dword ptr [esp + 0x4]
        ret

    addd:
        push esi
        mov esi, eax
{addch(11, 0x1f, 0x18)}
{addch(5, 0x3f, 0x1c)}
{addch(0, 0x1f, 0x20)}
        pop esi
        ret

    apply:
        push eax
        mov edx, eax
        mov dword ptr [edx + 0x18], 0x0
        mov dword ptr [edx + 0x1c], 0x0
        mov dword ptr [edx + 0x20], 0x0
        cmp dword ptr [edx + 0xc], 0x0
        jl ap_b
        push dword ptr [edx + 0x8]
        mov eax, dword ptr [edx + 0x8]
        mov ecx, dword ptr [edx + 0xc]
        call cloudof
        pop ecx
        mov edx, dword ptr [esp]
        mov ebx, 0x100
        sub ebx, dword ptr [edx + 0x4]
        call addd
    ap_b:
        mov edx, dword ptr [esp]
        push dword ptr [edx + 0x10]
        mov eax, dword ptr [edx + 0x10]
        mov ecx, dword ptr [edx + 0x14]
        call cloudof
        pop ecx
        mov edx, dword ptr [esp]
        mov ebx, dword ptr [edx + 0x4]
        call addd
        mov edx, dword ptr [esp]
        mov esi, dword ptr [edi + {PK:#x}]
        xor ebx, ebx
{outch(11, 0x1f, 0x18)}
{outch(5, 0x3f, 0x1c)}
{outch(0, 0x1f, 0x20)}
        mov eax, ebx
        cmp dword ptr [edi + {L['FMT']:#x}], 0
        je ap_o
        mov ecx, eax
        and ecx, 0x1f
        shr eax, 1
        and eax, 0x7fe0
        or eax, ecx
    ap_o:
        mov ecx, dword ptr [edi + {L['DST']:#x}]
        mov word ptr [ecx], ax
        pop eax
        ret

    waterfog:
        mov eax, dword ptr [edi + {L['KEY']:#x}]
        mov dword ptr [edi + {PK:#x}], eax
        sub esp, 0x30
        mov dword ptr [esp + 0x24], 0x7fffffff
        mov dword ptr [esp + 0x28], 0x0
    wf_c:
        mov eax, dword ptr [edi + {PK:#x}]
        call to4
        mov esi, eax
        mov ecx, dword ptr [esp + 0x28]
        call tblpix
        mov dword ptr [esp + 0x2c], eax
        call to4
        mov ecx, eax
        mov ebx, dword ptr [edi + {WP:#x}]
        call leval
        test eax, eax
        js wf_n
        cmp edx, dword ptr [esp + 0x24]
        jge wf_n
        mov dword ptr [esp + 0x24], edx
        mov dword ptr [esp + 0x4], eax
        mov eax, dword ptr [esp + 0x2c]
        mov dword ptr [esp + 0x10], eax
        mov eax, dword ptr [esp + 0x28]
        mov dword ptr [esp + 0x14], eax
    wf_n:
        inc dword ptr [esp + 0x28]
        cmp dword ptr [esp + 0x28], 0x3
        jb wf_c
        cmp dword ptr [esp + 0x24], {OV.FOG_MAXRES:#x}
        jg wf_skip
        mov dword ptr [esp + 0xc], 0xffffffff
        mov eax, esp
        call apply
    wf_skip:
        add esp, 0x30
        jmp {pixnext:#x}

    skyfog:
        mov eax, dword ptr [edi + {L['I']:#x}]
        movzx eax, byte ptr [ebp + eax + {EDGETBL:#x}]
        test eax, dword ptr [edi + {EM:#x}]
        je {pixnext:#x}
        mov eax, dword ptr [edi + {L['KEY']:#x}]
        mov dword ptr [edi + {PK:#x}], eax
        sub esp, 0x30
        mov ecx, dword ptr [edi + {K:#x}]
        call tblpix
        mov dword ptr [esp + 0x8], eax
        mov eax, dword ptr [edi + {K:#x}]
        mov dword ptr [esp + 0xc], eax
        mov dword ptr [esp + 0x24], 0x7fffffff
        mov dword ptr [esp + 0x28], 0x0
    sf_c:
        mov eax, dword ptr [esp + 0x28]
        cmp eax, dword ptr [edi + {K:#x}]
        je sf_n
        mov ecx, eax
        call tblpix
        mov dword ptr [esp + 0x2c], eax
        call to4
        mov dword ptr [esp + 0x18], eax
        mov eax, dword ptr [esp + 0x8]
        call to4
        mov ebx, eax
        mov eax, dword ptr [edi + {PK:#x}]
        call to4
        mov esi, eax
        mov ecx, dword ptr [esp + 0x18]
        call leval
        test eax, eax
        js sf_n
        cmp edx, dword ptr [esp + 0x24]
        jge sf_n
        mov dword ptr [esp + 0x24], edx
        mov dword ptr [esp + 0x4], eax
        mov eax, dword ptr [esp + 0x2c]
        mov dword ptr [esp + 0x10], eax
        mov eax, dword ptr [esp + 0x28]
        mov dword ptr [esp + 0x14], eax
    sf_n:
        inc dword ptr [esp + 0x28]
        cmp dword ptr [esp + 0x28], 0x3
        jb sf_c
        cmp dword ptr [esp + 0x24], {SKYFOG_MAXRES:#x}
        jg sf_skip
        test dword ptr [edi + {EM:#x}], {HANG:#x}
        je sf_ok
        cmp dword ptr [esp + 0x4], {HANG_TMAX:#x}
        jg sf_skip
    sf_ok:
        mov eax, esp
        call apply
    sf_skip:
        add esp, 0x30
        jmp {pixnext:#x}

    probe:
""" + "".join("        mov eax, %s\n" % n for n in PROBES)


def _asm(pixel, pixnext):
    return OV.asm(src(pixel, pixnext), CODE0)


def labels(pixel, pixnext):
    t = _asm(pixel, pixnext)[-5 * len(PROBES):]
    return {n: struct.unpack_from("<I", t, 5 * i + 1)[0] for i, n in enumerate(PROBES)}


def build(pixel, pixnext):
    code = _asm(pixel, pixnext)[:-5 * len(PROBES)]
    lab = labels(pixel, pixnext)
    table = b""
    for i, n in enumerate(("watersky", "waterfog", "skyfog", "skyhex")):
        at = EXTRA + 5 * i
        table += bytes([0xE9]) + struct.pack("<i", lab[n] - (at + 5))
    blob = table + bytes(CODE0 - EXTRA - len(table)) + code
    assert len(blob) <= EDGETBL - EXTRA, hex(len(blob))
    blob += bytes(EDGETBL - EXTRA - len(blob)) + edge_table()
    assert len(blob) <= EXTRA_END - EXTRA, hex(len(blob))
    return blob
