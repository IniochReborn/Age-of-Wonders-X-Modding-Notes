---
name: discord-map-randomizer-bot
description: "Discord /map bot (random AoWx map + unique race per player) as a Cloudflare Worker; BUILT + locally tested 10/21, awaiting the user's Discord/Cloudflare setup and the flavour-message list"
metadata:
  node_type: memory
  type: project
  originSessionId: 511f9df3-964c-401e-b2ff-e5d99b017377
  modified: 2026-10-22T03:43:30.922Z
---

Design (agreed with the user): `/map` opens a modal "Age of Wonders X - Map Randomizer" with one box, "Please list players (separated by a comma)". The bot picks a random `Scenario\Custom\AoWx - *.hsm` map with at least as many races as players, gives each player a unique race from that map's player slots, and posts `**Map:** X` / `**Assigned Races:**` / `- name: Race` / an italic flavour line. Excluded: Into The Fray (glitch); San Andreas is not an "AoWx - " file anyway. `_` in a name is shown as an apostrophe.

**10/21 BUILT** in `patch scripts\discord_bot\` (README.txt has the user's setup steps):
- `worker_template.js`: dependency-free ES-module Worker; Ed25519 check via crypto.subtle; env `DISCORD_PUBLIC_KEY`. Errors are ephemeral; `allowed_mentions` is none.
- `build_worker.py` writes `worker.js` (72 maps embedded + messages.txt). It imports `races()`/`MAP_DIR` from `patch scripts\discord_map_races.py`, which now has a `__main__` guard.
- `register_command.py <app id> <token> [server id]` PUTs the /map command.
- `messages.txt` holds a placeholder line; the user will send the real list.
- Tested with portable Node 22 (scratchpad): bad signature → 401, PING, modal, submit, empty list, 12 and 13 players, 2000 rolls (no duplicate races; 60 eligible maps for 4 players).
- No Node at home, so the deploy plan is to paste worker.js into the Cloudflare dashboard (no wrangler).
- **Next:** the user does the Discord app + Worker setup; flavour messages → rebuild + repaste.

**10/22 LIVE SETUP:**
- Same Discord app as presence: "Age of Wonders X", id 1562676560949944400.
- Cloudflare Worker `aowx-map-bot` (Hello World, pasted worker.js), var DISCORD_PUBLIC_KEY. Its GET page shows the key status plus the last verify error.
- Interactions Endpoint URL is saved.
- /map is registered as a guild command on server <server id>. The user was told to reset the bot token afterwards; it was pasted in chat, so never store it.
- Remaining: confirm /map works in Discord; flavour lines → build_worker.py + repaste.
- 10/22 ✅ LIVE + user-confirmed: 26 flavour lines (user-written, messages.txt) and placeholder "Alcedes, Booska, Inioch, Paradox". Bot token reset by the user after registration, and the bot keeps working. To update: edit messages.txt or add maps, run build_worker.py, paste worker.js into the Cloudflare Worker, Deploy.
- 10/22 ONLINE KEEPER: a separate Worker `aowx-bot-presence` (https://<worker>.workers.dev; GET = status JSON, /kick = reconnect now).
  - Source: `patch scripts\discord_bot\gateway\` (src/index.js + wrangler.toml).
  - A SQLite Durable Object "main" holds the gateway WebSocket (intents 0, custom status "Type /map to roll a map and races"). A 1-min cron pokes it and reconnects.
  - Secret DISCORD_BOT_TOKEN was set by the user in the dashboard (never seen by Claude).
  - Free plan: about 10,800 of 13,000 GB-s/day; going over means offline until 00:00 UTC, and /map is unaffected.
  - Deploy: `npx wrangler deploy` in that folder, with PATH including C:\Users\<user>\Tools\node (portable Node 22). wrangler 4.40.0 is in node_modules; the user did `wrangler login` (OAuth) on 10/22.
  - Bot username is "CPU Emperor"; online confirmed 06:18Z.
  - Not in the member list = the bot role lacked View Channels (the server gates channels by role). Fixed by giving the Bots role View Channels; shows online, user-confirmed 10/22.
