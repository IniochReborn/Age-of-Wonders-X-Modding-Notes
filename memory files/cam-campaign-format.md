---
name: cam-campaign-format
description: "Reverse-engineered AoW1 .CAM campaign format (TAoWDir tagged-directory container), verified by byte-identical round-trip of all 12 campaign files"
metadata: 
  node_type: memory
  type: reference
  originSessionId: 66c54916-064a-4d90-b1cc-a7e1edb96f02
  modified: 2026-08-25T00:32:57.100Z
---

The AoW1 `.CAM` campaign format, recovered from `AoWCGE.exe` and **verified by rebuilding all
12 unique .cam files on this machine byte-identically** (vanilla, AoW+ 1.45, and the user's own
modded campaigns). Working codec: `old modding tools\research\camcodec.py`
(`read_campaign()` / `rewrite()`); the subagent's independent parser is `cam_parse.py`.
See [[old-modding-tools]] and [[ilb-image-format]].

**It is NOT Delphi DFM/RTTI.** Every domain class has 0 published properties. The author
hand-rolled a self-describing tagged container, class `TAoWDir`. Every structural node is:

    magic (0/3/4/7 bytes, node-type specific)
    CountByte C   -> (C & 0x7F) short entries; (C & 0x80) means a long-count follows
    [int32 L]     -> number of long entries
    short table   -> L times (uint8 FieldID, uint8 RelOffset)
    long  table   -> L times (int32 FieldID, int32 RelOffset)
    payload       -> offsets are relative to the end of the tables

**There is no per-entry size field** — an entry's length is `next.RelOffset - this.RelOffset`,
and the last entry runs to the end of the enclosing node. The writer picks the short form when
the offset is < 0x100. Magics: root `01 00 00 00 50 22 00`, list/chapter `01 01 00`,
scenario/countermeasure record `01 50 22 00`, book page `02 50 22 00`, settings blob = none.
Scalars: int32; byte; ShortString (`uint8 len` + bytes); LongString (`int32 len` + bytes).
A missing field is legal and means "default" — absence is also the **type tag**.

**Root fields**: 0x07 settings blob (35 bytes of round-tripped constants), 0x0A record list,
0x0C campaign name ShortString, 0x0E 8 zero bytes, 0x10 5 zero bytes, 0x11 = 2, 0x13 = 1,
**0x1E present ⇒ this replaces Cult of Storms; absent ⇒ Keepers**.

**Record fields** (scenario vs counter-action is discriminated by `HasField(0x0C)`):
0x09 ID, 0x0A short title, 0x0B `.csm` scenario file, 0x0C `.it` music file (**scenario only**;
defaults to `Title.it`, cannot be empty), 0x0D full title, 0x0E counter-action description,
0x10/0x11 map X/Y, 0x13 prologue chapter, 0x14 epilogue chapter, 0x15 link block,
0x16 unknown byte (the author's own group box is captioned "Unknown"; correlates with campaign
stage 0=early/1=mid/2=late).

**Link block 0x15** = six int32: `[0]=0 sentinel, [1]=4 sentinel, [2..4]=NextMission IDs
(-1 = none, max 3), [5]=CounterMeasure ID`. Counter-action records instead carry `[-1, 0]`.

**Book chapters** are always exactly **10 pages**. Page fields: 0x0A body text (LongString),
0x0B title, 0x0C `.ILB` image library, 0x0D image index. An empty page is exactly 5 bytes
(`02 50 22 00 00`), so a trailing run of that pattern is the signature of empty chapters.

**Key limitation to fix in any replacement**: there is **no start-scenario field** — the game
implicitly uses list index 0. AoWCGE's own "Known Issues" lists this, and the UI that would
have fixed it (`TForm1` / `AoWCampaignPropertiesForm`, with "Start Scenario ID" and a
Keepers/Storm radio group) is compiled in but orphaned and unreachable.

The user's live `X\Campaign\Keepers.cam` is a large custom campaign: **70 scenarios,
69 counter actions, 412 story pages** (vanilla is 28/14/164). Their `X\Campaign\Storm.cam`
is named Storm but carries **no field 0x1E**, i.e. it is flagged as replacing *Keepers* —
worth confirming that is intentional.
