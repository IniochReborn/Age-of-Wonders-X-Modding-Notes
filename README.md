# Age of Wonders X Modding Notes

The patch scripts, development notes and tool sources behind
[Age of Wonders X](https://github.com/IniochReborn/Age-of-Wonders-X), a mod for Age of Wonders (1999)
applied as binary patches to the game's Delphi 3 modules.

**Looking for the mod itself?** Get the installer from the
[Age of Wonders X releases](https://github.com/IniochReborn/Age-of-Wonders-X/releases/latest), or read the manual at [AoWx.org](https://aowx.org).

This is a record, not a tutorial or a build system. Start at `memory files/MEMORY.md`.

| folder | holds |
|---|---|
| `patch scripts/` | The Python scripts that patch the game binaries and build the data, art, sound, manual, installer and updater. Each script's docstring says what it changes. `_game_root (July era)/` and `_laptop era (July-August)/` hold the earliest ones; the latter also has the few scripts, tools and docs by [BXL](https://github.com/BING-XI/Ziggurat-Modding-Notes) that AoWx used as they are. |
| `memory files/` | Working notes kept during development: engine internals, file formats, addresses, what was tried and what failed. `MEMORY.md` is the index. The files with spaces in their names are per-feature explanations from the first months. |
| `modding tools/` | Python source of the AoWx modding tools suite (map generator, music, image, text and quest tools) and its shared library. |
| `Old Hex Editing Notes.xlsx` | The hand-made hex edits from before the scripted patches: component, offset, bytes and comment for each change. |
| `changelogs.txt` | The full release changelog. |

## Read this before running anything

- The scripts were written against one specific set of binaries and applied in a particular order. Many refuse to run on bytes they do not expect; others assume earlier patches are present.
- Addresses and code caves are specific to the AoWx binaries. Running a script against a vanilla install, another mod, or a different AoWx version can corrupt the file. Work on copies.
- The notes are point-in-time. Later notes often correct earlier ones, and entries marked "untested" were never confirmed in game.
- Game binaries, game data, backups, debug dumps and the release signing files are not included. Personal details were replaced with placeholders such as `<user>`.
