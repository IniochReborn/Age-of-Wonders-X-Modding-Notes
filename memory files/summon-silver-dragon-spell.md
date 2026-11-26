---
name: summon-silver-dragon-spell
description: "Summon Silver Dragon (spell 0xCB, Secret L4, summons unit 153) — built 2026-08-10 via the Mermaid toolchain with a TSummonGoldDragon chassis; includes the FIRST SPELLICN.ILB record APPEND (new icon id 200). Applied, awaiting test."
metadata: 
  node_type: memory
  type: project
  originSessionId: 68a26f78-5efa-41a9-b957-f58c326322dc
  modified: 2026-08-11T03:00:25.430Z
---

**⚠ v2 FIXES 8/10 (user-reported): unit = 252 (0xFC), NOT 153** — the manual
builder's unit-list index is NOT the unit id (153 is an empty slot → summon
error). **And record key 31 ≠ gold dragon**: sphere/level bytes identify
records — key 31 = Fire L1 (Summon Fire Sprite, icon 64 = winged flame bird);
**key 35 = Life L4 = REAL Summon Gold Dragon, icon id 91**. Vanilla painted
icons = per-sphere full-art frames named SI-<Sphere>.BMP: pair = [sphere glow
burst 40x35][subject frame 40x35, node key 0x4148, near-white bg]. Gold dragon
subject = id 91 node 1 (black dragon silhouette) — copied VERBATIM as our
frame 1 (key matches our cloned slot). Vanilla SECRET bg = purple burst (id
150 node 0; ids 150-153 are SI-Secret pairs) but OUR custom secret spells use
the dark teal-blue cloud (rec 144) — kept that per user's earlier Void Step
choice. Key↔spell-id mapping still not closed-form (mermaid/void/silver keys =
id+10 by our choice and they resolve; call flames 123=117+6; gold dragon
35=25+10?!) — identify vanilla records by sphere+level bytes, not arithmetic.

**Summon Silver Dragon** — spell id **0xCB (203)**, Secret sphere level 4,
summons **unit 252 (0xFC) Silver Dragon**. Built 8/10 by
`build_summon_silver_dragon.py` (single script, 3 patches), APPLIED, awaiting
in-game test. Backups: AoWEPACK.dll/SPELLICN.ILB/Spells.pfs `.bak_silverdragon`.

- **DLL**: cave @0x55810B80 (117B; **next free AoWEPACK cave 0x55810C80**),
  hook = TSummonGoldDragon's RegisterSpell call @0x557E515C in
  RegisterSummonSpells. Clone of the mermaid cave: second TSummonGoldDragon
  (classref [0x557E38D8], Create 0x557E4C1C), pokes id/sphere 7/level 4/name
  "Summon Silver Dragon"/summon-list items[0] 0xD8→0x99. Gold defaults kept:
  [+0x14]=5 cast pts, research [+0x30]=0x28/[+0x34]=0x2EE (user tunes in
  editor). Vanilla gold dragon: spell id 0x19, sphere Life(1), summons unit
  0xD8=216 (summon-variant unit ≠ roster Gold Dragon 117 — AoW1 keeps separate
  summon copies; manual's unit list keys ARE unit ids: Silver Dragon 153).
- **ILB APPEND (first time — recipe)**: SPELLICN.ILB had NO free icon pairs
  left (52=Void Step, 88=Mermaid, 151=Magic Sight all used; 110 ids all
  referenced). New image id 200 appended: byte-clone the id-88 wrapper record
  (class tag 0x100, two nested 40x35 RAW16 nodes 2800B each) from the record
  stream, patch its leading id dword and the two [sz][doff] pairs (doffs are
  BASE-RELATIVE → existing records unaffected), insert before the 0xFFFFFFFF
  stream terminator, append pixel blobs at file end, bump header base (@0x10)
  by clone size + filesize (@0x14). Frame 0 = Secret dark cloud (rec 144 copy),
  frame 1 = gold-dragon glyph (id 64 pair, rec 105, 30x32 sub @(4,2), key
  0xFFFF) composited onto 40x35 canvas filled with the cloned node's OWN header
  key (0x4148). NOTE both bg conventions display fine (mermaid glyph=white bg
  w/ header key 4148; void step=4148 bg) — book keys white AND loader keys
  header key, apparently.
- **PFS**: record key 213 appended (clone of gold dragon key 31: summon-circle
  MAGIC.ILB cast gfx frames 0x14-0x1B + MAGIC01.WAV sound) w/ desc, icon
  64→200, sphere 7, level 4. Key↔id mapping still opaque (31↔0x19, 213↔0xCB
  — key=id+6 for vanilla, custom keys arbitrary, engine finds them anyway).
- **Summons need NO SpellTypes byte** (SpellTypes[201]=0 for working Mermaid;
  [203] left 0) — they're strategic-only; the book-id≥100 display fix is
  global (AoWx.exe, done in mermaid era).
- RegisterSummonSpells hook sites: each vanilla `call RegisterSpell` @
  0x557E50BB..0x557E51CF can host ONE chained cave (mermaid took the last,
  0x557E51CF→cave 0x55810900; silver dragon took gold dragon's 0x557E515C).

Related: [[summon-mermaid-spell]] (toolchain), [[warp-self-combat-spell]]
(Void Step; SPELLICN icon-pair semantics + record header format).
