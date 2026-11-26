#!/usr/bin/env python3
r"""
Convert a Discord-style AoWx changelog txt (".          - item" lines, 5 spaces per level) into clean GitHub
release Markdown (2026-10-21).

  "Spells:"                      -> "## Spells"
  first two lines (date / "Version ... released:") -> bold title line + date
  ".<10+5k spaces>- text"        -> nested Markdown bullet at level k (2 spaces per level)
  Discord emoji tokens <:name:id> are removed.

Usage: py -3.10 make_github_notes.py "<changelog txt>" [--out <md>]
Default out: same folder, "<txt name> (GitHub).md".
"""
import argparse, os, re, sys

BULLET = re.compile(r"^\.(\s*)-\s?(.*)$")
EMOJI = re.compile(r"<a?:\w+:\d+>")


def convert(lines):
    out = []
    head = [l.strip() for l in lines[:3]]
    i = 0
    if len(head) >= 2 and head[1].lower().startswith("version"):
        out += ["**%s**" % head[1].rstrip(":"), "", "_%s_" % head[0], ""]
        i = 2
    for raw in lines[i:]:
        line = EMOJI.sub("", raw.rstrip("\r\n")).rstrip()
        m = BULLET.match(line)
        if m:
            level = max(0, (len(m.group(1)) - 10) // 5)
            out.append("  " * level + "- " + m.group(2).strip())
        elif not line.strip():
            if out and out[-1] != "":
                out.append("")
        elif line.strip().endswith(":") and not line.startswith(" "):
            if out and out[-1] != "":
                out.append("")
            out += ["## " + line.strip().rstrip(":"), ""]
        else:
            out.append(line.strip())
    while out and out[-1] == "":
        out.pop()
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("txt")
    ap.add_argument("--out")
    a = ap.parse_args()
    lines = open(a.txt, encoding="utf-8").readlines()
    md = convert(lines)
    out = a.out or os.path.splitext(a.txt)[0] + " (GitHub).md"
    open(out, "w", encoding="utf-8", newline="\n").write(md)
    print("written " + out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
