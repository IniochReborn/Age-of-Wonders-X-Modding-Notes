"""
BANSHEE GALE (spell 344) - camera + one-hop throw - 2026-10-16.  AoWTCPCK.dll only.  Needs patch_banshee_v1.py applied
(it reads that script's DATA slots G_TE / G_CX / G_CY = the strike-0 TE and the ORIGINAL target hex = the AoE centre).

User (after testing): "the camera recenters too much - it should only center on the center of the AOE, not bounce
around between units" + "when the units get displaced I don't want the animation to bounce them around between
multiple hexes before landing - they should go directly to their destination hex in one hop".

RE (NextStrike class-0x2F case, after the landing hex is chosen @0x40DC14, landing pixel -> [ebp-0x3c]/[ebp-0x40]):
  0x40DC1F..0x40DC3E  push 0 / CenterOn([te+0x20], [te+0x22]) = combat map VMT+0xBC (the same call every NextStrike
                      class case makes; the hail cases pass y-5).  patch_banshee_v1's TG cave retargets [te+0x20/22]
                      to each unit of the area per strike, so the view jumped to every thrown unit.
  0x40DC3E..0x40E1F6  the Winds-of-Fury flight path behind the origin point P0 (= origin pixel + 16, made @0x40D94F):
                      30 points jittered +-15 px round the origin (System.RandInt(0x1e) x2 each = the "shake"), then
                      aowFX.MakeArcPathXY (thunk 0x402E24) to a RANDOM point +-150 px away (RandInt(0x12c) x2;
                      [fx+0x24] = count), another to a random point +-100 px (RandInt(0xc8) x2; [fx+0x28] = count),
                      and only then the arc to the landing pixel -> the unit swooped over 2 random spots first.
  MakeArcPathXY(ax x0, dx y0, cx x1, [stack] y1, divisor, height, list^) (aowFXpck 0x4020F8, ret 0x10): points
  = (|dx|+|dy|) / divisor (min 2), k = 0..n, z = sin(k*pi/n) * height.

Hooks (both keyed on [te+0x18] == 344; te = [ebp-4], fx = [ebp-0x10]):
  CAM 0x40DC1F (`push 0 / mov eax,[ebp-4]`, 5 B, ahead of the reloc'd `mov eax,[0x469420]`) -> cave: for 344 the
      view is centred ONCE, on strike 0 ([te+0x34] == 0), on the AoE centre (G_CX, G_CY); later strikes skip the
      call.  Other spells: replay, back to 0x40DC24.
  HOP 0x40DC3E (`xor eax,eax / mov [ebp-0x44],eax`, 5 B) -> cave: for 344, burn the 64 System.RandInt draws the
      vanilla path would have made (RandSeed stream unchanged -> nothing downstream shifts; MP/replay-identical to
      the old draw count), set [fx+0x24] = [fx+0x28] = 1 (the effect's cue-0 indices; patch_airdeath_fix BW skips
      344's cue-0 plays anyway), then ONE MakeArcPathXY from the origin pixel to the landing pixel with divisor =
      max(1, dist / HOP_PTS) (~HOP_PTS + 1 points whatever the distance) and arc height HOP_H, -> 0x40E1F6 (the
      vanilla end of the case: jmp 0x40EDA0).  The landing itself (unit HS moved at path end by the kind-0x2F
      NewFrame) is untouched.  Other spells: replay, back to 0x40DC43.
Zone: TCPCK 0x43FD00..0x43FE00 (zero, reloc-free; verified).  Backup <game>\\backup\\AoWTCPCK.dll.bak_banshee_hop.
Dry-run default; --apply / --revert / --dis / --tc-dll <path> (scratch copies).
"""
import argparse, os, shutil, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bakpath import bak_path, game_file
import patch_banshee_v1 as B

HOP_PTS = 20              # points in the hop arc (~0.7 s of flight at 1 point per tick)
HOP_H = 40                # arc height in pixels (Winds' long arcs use 100)
RAND_BURN = 30 * 2 + 2 + 2   # System.RandInt draws of the vanilla path (jitter loop + 2 random waypoints)

TC = dict(dll=game_file("AoWTCPCK.dll"), base=0x400000, v2f=0x400C00, zone=(0x43FD00, 0x43FE00),
          sites={"CAM": (0x40DC1F, bytes.fromhex("6a008b45fc")),
                 "HOP": (0x40DC3E, bytes.fromhex("33c08945bc"))},
          scan=(0x40CD20, 0x40F500))


def build_tc():
    v = dict(id=B.SPELL_ID, maplist=B.MAPLIST, gte=B.G_TE, gcx=B.G_CX, gcy=B.G_CY, burn=RAND_BURN, pts=HOP_PTS, h=HOP_H)
    srcs = {
        "cam": """
            mov eax, [ebp-4]
            cmp dword ptr [eax+0x18], %(id)d
            jne cam_van
            call $D
            pop ebx
            sub ebx, $D
            cmp [ebx+%(gte)#x], eax
            jne cam_van
            cmp dword ptr [eax+0x34], 0
            jne cam_skip
            push 0
            mov ecx, [ebx+%(gcy)#x]
            mov edx, [ebx+%(gcx)#x]
            mov eax, [ebx+%(maplist)#x]
            mov eax, [eax]
            mov ebx, [eax]
            call dword ptr [ebx+0xbc]
        cam_skip:
            jmp 0x40DC3E
        cam_van:
            push 0
            mov eax, [ebp-4]
            jmp 0x40DC24
        """,
        "hop": """
            mov eax, [ebp-4]
            cmp dword ptr [eax+0x18], %(id)d
            jne hop_van
            push esi
            mov esi, %(burn)d
        hop_rnd:
            mov eax, 1
            call 0x401020
            dec esi
            jnz hop_rnd
            pop esi
            mov eax, [ebp-0x10]
            mov dword ptr [eax+0x24], 1
            mov dword ptr [eax+0x28], 1
            mov eax, [ebp-0x3c]
            sub eax, [ebp-0x34]
            cdq
            xor eax, edx
            sub eax, edx
            mov ecx, eax
            mov eax, [ebp-0x40]
            sub eax, [ebp-0x38]
            cdq
            xor eax, edx
            sub eax, edx
            add eax, ecx
            xor edx, edx
            mov ecx, %(pts)d
            div ecx
            cmp eax, 1
            jge hop_div
            mov eax, 1
        hop_div:
            mov edx, [ebp-0x40]
            add edx, 0x10
            push edx
            push eax
            push %(h)d
            mov eax, [ebp-0x10]
            add eax, 0x1c
            push eax
            mov eax, [ebp-0x34]
            add eax, 0x10
            mov edx, [ebp-0x38]
            add edx, 0x10
            mov ecx, [ebp-0x3c]
            add ecx, 0x10
            call 0x402E24
            jmp 0x40E1F6
        hop_van:
            xor eax, eax
            mov [ebp-0x44], eax
            jmp 0x40DC43
        """,
    }
    return srcs, v, {"CAM": "cam", "HOP": "hop"}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); ap.add_argument("--revert", action="store_true")
    ap.add_argument("--dis", action="store_true"); ap.add_argument("--tc-dll"); a = ap.parse_args()
    if a.tc_dll: TC["dll"] = a.tc_dll
    d0 = open(TC["dll"], "rb").read()
    tg = B.TC["sites"]["TG"][0] - B.TC["v2f"]
    if d0[tg] != 0xE9: print("ABORT - patch_banshee_v1.py is not applied (its TG cave fills G_TE/G_CX/G_CY)"); return 1
    r = B.do_part("AoWTCPCK", TC, build_tc, a)
    if r is None: print("ABORT - nothing written"); return 1
    d, mode = r
    if mode == "same" and not a.revert: print("already applied"); return 0
    if not (a.apply or a.revert): print("Dry run OK - rerun with --apply (or --revert)."); return 0
    bak = bak_path(TC["dll"], ".bak_banshee_hop")
    if not os.path.exists(bak): shutil.copy2(TC["dll"], bak); print("backup ->", bak)
    with open(TC["dll"], "r+b") as f: f.write(bytes(d))
    assert open(TC["dll"], "rb").read() == bytes(d)
    print("AoWTCPCK: %s written and verified" % ("reverted" if mode == "revert" else "patch"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
