"""Paste Hurl Skull v8 into the builders (run from patch scripts\\; idempotent).
Arg 1 = integration txt, args 2/3 = fx / sfx builder paths (defaults: the live builders in the cwd)."""
import ast, sys

INT = sys.argv[1] if len(sys.argv) > 1 else "_bxlranged8_integration.txt"
FX = sys.argv[2] if len(sys.argv) > 2 else "build_dual_sphere_fx_v1.py"
SX = sys.argv[3] if len(sys.argv) > 3 else "build_dual_sphere_sfx_v1.py"
t = open(INT, encoding="utf-8").read().replace("\r\n", "\n")


def blk(h):
    i = t.index(h); i = t.index("\n", i) + 1
    return t[i:t.index("---- end ----", i)]


i = t.index("---- code:"); i = t.index("----\n", i + 10) + 5
code = t[i:t.index("---- end ----", i)]
rows = [r for r in blk("---- rows:").split("\n") if r.strip()]
mix = [" " + r for r in blk("---- MIX:").split("\n") if r.strip()]

s = open(FX, encoding="utf-8", newline="").read(); nl = "\r\n" if "\r\n" in s else "\n"
if "def explbig80(" in s:
    print("fx: already applied")
else:
    for name in ("skull_death_aura", "skull_fire_aura", "deathfire_puff_smoke", "deathfire_puff_fire"):
        a = s.index("def %s(" % name); b = s.index(nl + "def ", a + 5) + len(nl)
        body = code[code.index("def %s(" % name):]
        k = body.find("\ndef ", 5); body = body if k < 0 else body[:k + 1]
        c = body.find("\nSK8_SCALE"); body = body if c < 0 else body[:c + 1]
        s = s[:a] + body.rstrip("\n").replace("\n", nl) + nl + nl + nl + s[b:]
    new = code[code.index("SK8_SCALE"):]
    s = s.replace("def build():", new.rstrip("\n").replace("\n", nl) + nl + nl + nl + "def build():", 1)
    L = s.split(nl); k = [j for j, l in enumerate(L) if "(7680, skull_death_burst()," in l]
    assert len(k) == 1, "the (7680, skull_death_burst(), ...) row was not found exactly once"
    L[k[0] + 1:k[0] + 1] = rows; s = nl.join(L)
    ast.parse(s); open(FX, "w", encoding="utf-8", newline="").write(s); print("fx: ok")

s = open(SX, encoding="utf-8", newline="").read(); nl = "\r\n" if "\r\n" in s else "\n"
if "v8 (user: 'layer in an added CRUNCH" in s:
    print("sfx: already applied")
else:
    a = s.index('"SKULL_HIT.WAV":'); b = s.index('("Attack/A_Force1.WAV"', a); e = s.index(nl, b) + len(nl)
    s = s[:e] + nl.join(mix) + nl + s[e:]
    ast.parse(s); open(SX, "w", encoding="utf-8", newline="").write(s); print("sfx: ok")
