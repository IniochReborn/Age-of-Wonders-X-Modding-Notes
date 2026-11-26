"""Paste Hurl Skull v9 art into the fx builder (run from patch scripts\\; idempotent).
Replaces, by name, hurl_skull5 / skull_death_aura / skull_fire_aura / deathfire_puff_smoke / deathfire_puff_fire /
skull_death_burst80 with the v9 bodies and adds skull_death_burst2 in front of skull_death_burst80.  Ids, frame counts,
canvases, anchors and drawModes are unchanged -> no row / pfs change; rebuild with build_dual_sphere_fx_v1.py --apply.
Arg 1 = art file (default art9.py next to this script), arg 2 = fx builder (default the live one in the cwd)."""
import ast, os, sys

ART = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "art9.py")
FX = sys.argv[2] if len(sys.argv) > 2 else "build_dual_sphere_fx_v1.py"
code = open(ART, encoding="utf-8").read().replace("\r\n", "\n")
code = code[code.index("# ---- code begin") + len("# ---- code begin\n"):code.index("# ---- code end")]


def body(name):
    a = code.index("def %s(" % name); b = code.find("\ndef ", a + 5)
    return (code[a:] if b < 0 else code[a:b + 1]).rstrip("\n")


s = open(FX, encoding="utf-8", newline="").read(); nl = "\r\n" if "\r\n" in s else "\n"
if "def skull_death_burst2(" in s:
    print("fx: already applied"); sys.exit(0)
for name in ("hurl_skull5", "skull_death_aura", "skull_fire_aura", "deathfire_puff_smoke", "deathfire_puff_fire", "skull_death_burst80"):
    a = s.index("def %s(" % name)
    b = s.find(nl + "def ", a + 5)
    c = s.find(nl + "SK8_SCALE", a + 5)                      # deathfire_puff_fire is followed by skull_death_burst, fine
    end = min(x for x in (b, c) if x >= 0) + len(nl) if (b >= 0 or c >= 0) else len(s)
    new = body(name)
    if name == "skull_death_burst80":
        new = body("skull_death_burst2") + nl + nl + nl + new.replace("\n", nl)
    s = s[:a] + new.replace("\n", nl) + nl + nl + nl + s[end:].lstrip("\r\n")
ast.parse(s)
open(FX, "w", encoding="utf-8", newline="").write(s)
print("fx: ok")
