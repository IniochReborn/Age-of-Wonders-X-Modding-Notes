"""Paste Hurl Skull v10 art (skull glow fades into the trail) into the fx builder (run from patch scripts\; idempotent).
Replaces, by name, skull_fire_aura / deathfire_puff_smoke / deathfire_puff_fire with the v10 bodies and adds the helper
_df_blend in front of skull_fire_aura.  Ids, frame counts, canvases, anchors and drawModes unchanged -> no row / pfs /
engine change; rebuild with build_dual_sphere_fx_v1.py --apply.  Revert: re-run tmp\bxlabil9\int_skull9.py logic or
paste art9.py's three bodies back (v9 bodies are kept in tmp\bxlabil9\art9.py).
Arg 1 = art file (default art10.py next to this script), arg 2 = fx builder (default the live one in the cwd)."""
import ast, os, sys

ART = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "art10.py")
FX = sys.argv[2] if len(sys.argv) > 2 else "build_dual_sphere_fx_v1.py"
code = open(ART, encoding="utf-8").read().replace("\r\n", "\n")
code = code[code.index("# ---- code begin") + len("# ---- code begin\n"):code.index("# ---- code end")]


def body(name):
    a = code.index("def %s(" % name); b = code.find("\ndef ", a + 5)
    return (code[a:] if b < 0 else code[a:b + 1]).rstrip("\n")


s = open(FX, encoding="utf-8", newline="").read(); nl = "\r\n" if "\r\n" in s else "\n"
if "def _df_blend(" in s:
    print("fx: already applied"); sys.exit(0)
for name in ("skull_fire_aura", "deathfire_puff_smoke", "deathfire_puff_fire"):
    a = s.index("def %s(" % name)
    b = s.find(nl + "def ", a + 5)
    end = (b + len(nl)) if b >= 0 else len(s)
    new = body(name)
    if name == "skull_fire_aura":
        new = body("_df_blend") + "\n\n\n" + new
    s = s[:a] + new.replace("\n", nl) + nl + nl + nl + s[end:].lstrip("\r\n")
ast.parse(s)
open(FX, "w", encoding="utf-8", newline="").write(s)
print("fx: ok")
