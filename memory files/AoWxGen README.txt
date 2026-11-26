AoWxGen v6.3
============

A standalone random-map generator for Age of Wonders (AoWx). No install, no
Python needed — just drop "AoWxGen.exe" anywhere inside your Age of Wonders
folder (next to AoW.exe is perfect) and run it. If you keep it elsewhere, it
will ask for your AoW folder on startup.

Generated maps appear in Scenario\Custom, ready to play (open them from
Custom Scenario in the game, or in the map editor). On first run the
generator installs four small "xTemplate" files into Scenario\Custom — leave
those in place; they are the empty canvases it paints on.

What it makes
-------------
1. Random Map Batch — two maps of each size (S/M/L/XL) with default settings.
2. Custom RNG Map — pick size, levels (surface only / +underground / +depths),
   player count (2-12), terrain inversion (surface terrain in the underground,
   from a little around cave entrances up to whole underworld landscapes),
   landmass style (Classic / Isles / Continents) and terrain style presets:
   Classic, Grasslands, Woodlands, Arctic, Desert, Highlands, Marshlands,
   Desolate, Apocalyptic. You can combine up to three styles on one map
   (enter e.g. "3 4 6" — the land splits into one region per style) and set
   a style strength from 1 (subtle) to 9 (extreme); 5 is the default look.
3. Image to Map — turn any picture into playable maps (one per size).
   Blue = water, green = grass (dark green = forest), tan = desert,
   red-brown = mountains, grey = grass.

Every map is full-featured: cities with recruitable rosters, player starts
with leaders and equal parties, roads with bridges, rivers, ice, teleporters,
cave systems with an underground and depths, and structure defenders. Each
map is verified after generation ("validation: OK").

Maps are named with their random seed, e.g. "xGen6 L Marshlands (seed
123456).hsm" — no two runs are alike.

Made with the BXL toolchain. Have fun!
