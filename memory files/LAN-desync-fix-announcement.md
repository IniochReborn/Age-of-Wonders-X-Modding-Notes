# 🛠️ AoWx Patch — LAN Out-of-Sync on Recruiting Fixed

**TL;DR:** The out-of-sync crash that happened when you moved onto and recruited a neutral/independent stack in LAN/multiplayer games is **fixed.** ✅

## What was happening

In a network game both machines run the exact same "dice rolls" in the same order to stay identical — if they ever get one roll out of step, the game detects it and throws an **Out of Sync** error.

Buried in the movement code was a **wasted dice roll**: every time a unit moved, the game rolled the RNG once and then **threw the result away without ever using it.**

Normally harmless — both PCs did the wasted roll at the same moment. But moving onto a neutral to recruit it knocked the timing apart just enough that one PC did the wasted roll a split-second before the other. For that instant the two machines had rolled a different number of times → **desync.**

## The fix

We simply **removed the wasted roll.** The number was being discarded anyway, so nothing about gameplay changes — but now there's no stray roll to fall out of step, so it can't trigger a desync anymore.

Confirmed working: recruit the moles (or any neutral) in a 2-player LAN game — no more OOS, and both clients stay perfectly in sync afterward.

## For the curious 🤓

- The culprit was a discarded `Random()` call in the move-token execution path (`TMoveTE.Execute`). Its result was overwritten on the very next instruction — pure dead RNG consumption.
- Because it advanced the shared synced seed, it desynced whenever a human move executed at a slightly different stream position than the peer (which is exactly what recruiting-during-AI-activity caused).
- Removing it is deterministic-safe: the same instruction is gone on both machines, so the RNG stream just advances identically one-fewer-per-move on every client.

*Nothing to configure — just grab the updated build. Report any weirdness and we'll take a look.* 🎮
