AoWx Discord /map randomizer
============================
/map opens a popup ("Age of Wonders X - Map Randomizer", one box: players separated by commas). The bot picks a random
AoWx map with enough races, gives each player a different race from that map, and posts the result plus a random line
from messages.txt. Runs as a free Cloudflare Worker - no PC needs to stay on.

Files
  worker_template.js   the bot code (edit this)
  build_worker.py      makes worker.js = template + map/race list + messages   (py -3.10 build_worker.py)
  worker.js            GENERATED - this is what gets pasted into Cloudflare
  messages.txt         flavour lines, one per line
  register_command.py  registers /map with Discord (once)

One-time setup
 1. https://discord.com/developers/applications -> New Application ("AoWx Map Randomizer").
    General Information: copy APPLICATION ID and PUBLIC KEY.
    Bot tab: Reset Token -> copy the TOKEN (keep it private).
 2. Cloudflare dashboard -> Workers & Pages -> Create -> Create Worker -> name it (e.g. aowx-map-bot) -> Deploy.
    Edit code -> delete everything -> paste all of worker.js -> Deploy.
    Settings -> Variables and Secrets -> Add: name DISCORD_PUBLIC_KEY, value = the PUBLIC KEY -> Deploy.
    (Optional) Settings -> Domains & Routes -> Add custom domain, e.g. bot.aowx.org.
 3. Discord portal -> General Information -> INTERACTIONS ENDPOINT URL = the Worker URL
    (https://aowx-map-bot.<your-subdomain>.workers.dev, or https://bot.aowx.org) -> Save Changes.
    Discord checks it right away; if it refuses, the public key variable is wrong or not deployed.
 4. Installation tab -> Guild Install, scope applications.commands -> open the install link -> add it to the server.
 5. py -3.10 register_command.py <APPLICATION ID> <TOKEN> <SERVER ID>
    (SERVER ID = right-click the server -> Copy Server ID, needs Developer Mode; leave it off for all servers.)

Updating (new maps, new flavour lines)
  py -3.10 build_worker.py  ->  Cloudflare -> the Worker -> Edit code -> paste worker.js -> Deploy.
