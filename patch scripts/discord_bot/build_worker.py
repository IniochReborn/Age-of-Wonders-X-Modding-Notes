r"""
Build worker.js (the Cloudflare Worker for the Discord /map randomizer) from worker_template.js.

Maps  = Scenario\Custom\AoWx - *.hsm minus EXCLUDE; races = the map's player-slot races (discord_map_races.races).
        Name = file name without "AoWx - " / ".hsm", with "_" shown as an apostrophe.
Lines = messages.txt next to this script (one flavour line per line, blank lines and #comments ignored).

Rerun after adding/removing maps or editing messages.txt, then paste worker.js into the Cloudflare Worker again.
"""
import glob, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from discord_map_races import races, MAP_DIR

EXCLUDE = {"Into The Fray (glitch)"}


def main():
    maps = []
    for p in sorted(glob.glob(os.path.join(MAP_DIR, "AoWx - *.hsm"))):
        n = os.path.basename(p)[7:-4]
        if n in EXCLUDE:
            continue
        rs = sorted({r for _, r, _ in races(p) if r < 12})
        maps.append([n.replace("_", "'"), rs])
    msgs = []
    mp = os.path.join(HERE, "messages.txt")
    if os.path.exists(mp):
        msgs = [l.strip() for l in open(mp, encoding="utf-8") if l.strip() and not l.lstrip().startswith("#")]
    src = open(os.path.join(HERE, "worker_template.js"), encoding="utf-8").read()
    src = src.replace("/*MAPS*/[]", json.dumps(maps, ensure_ascii=False))
    src = src.replace("/*MESSAGES*/[]", json.dumps(msgs, ensure_ascii=False))
    open(os.path.join(HERE, "worker.js"), "w", encoding="utf-8", newline="\n").write(src)
    print("worker.js: %d maps (%s), %d messages" % (len(maps), ", ".join("%d-race x%d" % (k, sum(len(m[1]) == k for m in maps))
          for k in sorted({len(m[1]) for m in maps})), len(msgs)))


if __name__ == "__main__":
    main()
