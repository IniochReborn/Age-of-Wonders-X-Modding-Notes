// AoWx Discord map randomizer - Cloudflare Worker (HTTP interactions, no dependencies).
// GENERATED worker.js is built from worker_template.js by build_worker.py - edit the template, not worker.js.
// Worker variable required: DISCORD_PUBLIC_KEY (the app's Public Key from the Discord Developer Portal).

const RACES = ["Humans", "Azracs", "Lizardmen", "Frostlings", "Elves", "Halflings",
               "Dwarves", "High Men", "Dark Elves", "Orcs", "Goblins", "Undead"];
const MAPS = [["1112 LIR Mountain Dive", [1, 5, 10]], ["1150 LIR Amnesia", [4, 5, 6, 7]], ["A Cry in the Heartwood Forest", [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]], ["After The Battle Royale", [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]], ["After the Fall", [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]], ["Altar of the Gods", [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]], ["An Uneasy Silence", [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]], ["Athendore", [0, 1, 3, 4, 5, 6, 9, 10, 11]], ["Banned", [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]], ["Barondir Bay", [0, 1, 2, 3]], ["Before the Fall", [0, 4, 5, 9]], ["Blackwood Forest", [0, 7, 8, 11]], ["Blood Isles", [0, 1, 6, 10]], ["Buried", [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]], ["Cold Fusion", [7, 11]], ["Conquest of Norquist", [0, 4, 8]], ["Cults and Keepers", [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]], ["Desolate Maugogom", [1, 6, 8, 9, 10, 11]], ["Diplomacy with Dragons", [2, 3, 4, 9]], ["Divide and Conquer", [4, 5, 6, 7]], ["Fields of Khaldir", [1, 3, 4, 7]], ["First Conflict", [4, 5, 9, 10]], ["Frosty Lagoon", [0, 3, 4, 5, 6, 7, 8, 9]], ["Frozen Waters of Seshedut", [3, 4, 7, 11]], ["Germany", [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]], ["Greed's Paradise", [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]], ["Green Valley", [0, 1, 4, 6, 8, 9]], ["Heartwood Forest", [4, 5, 9, 10]], ["Honeyvale Falls", [3, 5, 9, 11]], ["Icedale", [0, 3, 6, 11]], ["Icy Embrace", [0, 2, 3, 4, 8, 11]], ["Igor's Folly", [6, 9]], ["Kayland", [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]], ["Kin Slayers", [0, 2, 4, 8]], ["King of the Hill", [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]], ["Kolusurt Caldera", [0, 2, 5]], ["Land of Merhal", [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]], ["Legend Has It", [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]], ["Lord of the Rings", [0, 4, 5, 6, 7, 9, 10, 11]], ["Love thy Neighbor", [8, 9, 10, 11]], ["Mine All Mine", [6, 8, 9]], ["Mirrored Oasis of Nathyazik", [2, 3, 5]], ["Morian Tundra", [2, 3, 5, 7, 8, 11]], ["Morrowind", [0, 1, 2, 3, 4, 5, 7, 8, 9, 10, 11]], ["Mountain Clash", [5, 10]], ["Oracle's Eye", [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]], ["Reign of Chaos", [4, 5, 6, 8, 9, 10]], ["Reign of Terror", [0, 4, 5, 8, 10]], ["River of Life", [0, 1, 4, 5, 6, 8, 9, 10]], ["Rocky Hollow", [0, 3, 8, 9, 11]], ["Search for Excalibur", [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]], ["Sixfold Arena", [3, 4, 7, 8, 9, 11]], ["Slugfest (12P)", [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]], ["Slugfest (3P)", [3, 7, 9]], ["Slugfest (6P)", [0, 3, 4, 7, 8, 9]], ["Spice Achipelago of Heulax", [1, 4, 6, 8, 9]], ["Spice-Marshes of Heulax", [0, 1, 5, 8, 9]], ["Sprint To Power", [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]], ["Swirlmount", [1, 2, 6, 9, 10]], ["The Eye of Yaka", [4, 6, 9, 10]], ["The Feud", [0, 1, 2, 3]], ["The Grand Bazaar of Hakkari", [1, 2, 3, 5]], ["Thinreed Lake", [4, 6, 8, 9]], ["Toadstool Vale", [5, 6, 9, 10]], ["Towers of Khazlkound", [0, 2, 6, 8, 9]], ["Tribute To The Fall", [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]], ["Urgath", [0, 6, 10]], ["Violence Begets Violence", [6, 9]], ["Warlords", [0, 1, 4, 6, 7, 8, 9, 10]], ["Xelm Plateau II - Arcane Gardens", [1, 4, 7, 8, 11]], ["Xelm Plateau", [5, 6, 7, 8, 10, 11]], ["Xergal's Legacy", [6, 9]]];          // [name, [race ids]]
const MESSAGES = ["Time to die in a crypt on turn one!", "Let there be blood!", "More blood... for the Blood God!", "May the best wizard win!", "In the first days of the world...", "Kill them all... let the gods sort them out!", "The slaughter begins!", "Prepare for annihilation!", "By the power of Grayskull!", "Unleash the Hell Hounds!", "A wizard is never late. Everyone else is simply early to their doom.", "The old powers stir once more.", "The fate of the world hangs in the balance.", "Let the chronicles be written in blood.", "An uneasy silence engulfed the lands...", "Time to commit some war crimes!", "Time to ruin some friendships!", "Good luck, have fun, trust nobody.", "May your starting position be blessed and your neighbours incompetent.", "May the RNG gods be ever in your favour...", "May your starting spells suck and your spawn location be unfavourable!", "Diplomacy is just war with extra steps...", "Let the backstabbing commence!", "Unleash the frogs!", "There's no Geneva Convention in the Valley of Wonders!", "Live, Laugh, ~~Love~~ Loot"];
const TITLE = "Age of Wonders X - Map Randomizer";
const MODAL_ID = "aowx_map_modal", FIELD_ID = "players";

function rnd(n) {                 // unbiased 0..n-1
  const lim = Math.floor(0x100000000 / n) * n, b = new Uint32Array(1);
  do crypto.getRandomValues(b); while (b[0] >= lim);
  return b[0] % n;
}
function shuffle(a) {
  for (let i = a.length - 1; i > 0; i--) { const j = rnd(i + 1); [a[i], a[j]] = [a[j], a[i]]; }
  return a;
}
const esc = s => s.replace(/([\\*_~`|])/g, "\\$1");

function roll(text) {
  const players = text.split(/[,\n]/).map(s => s.trim()).filter(Boolean);
  if (!players.length) return { error: "No players listed." };
  const fits = MAPS.filter(m => m[1].length >= players.length);
  if (!fits.length) return { error: `No map has ${players.length} races available (max ${Math.max(...MAPS.map(m => m[1].length))}).` };
  const [name, races] = fits[rnd(fits.length)];
  const pick = shuffle([...races]);
  const lines = [`**Map:** ${esc(name)}`, "**Assigned Races:**",
                 ...players.map((p, i) => `- ${esc(p)}: ${RACES[pick[i]]}`)];
  if (MESSAGES.length) lines.push("", `*${MESSAGES[rnd(MESSAGES.length)]}*`);
  return { content: lines.join("\n") };
}

const hex = h => new Uint8Array(h.match(/../g).map(b => parseInt(b, 16)));
async function verify(req, body, keyHex) {
  const sig = req.headers.get("X-Signature-Ed25519"), ts = req.headers.get("X-Signature-Timestamp");
  if (!sig || !ts || !keyHex) return false;
  const msg = new TextEncoder().encode(ts + body);
  for (const alg of [{ name: "Ed25519" }, { name: "NODE-ED25519", namedCurve: "NODE-ED25519" }]) {
    try {
      const key = await crypto.subtle.importKey("raw", hex(keyHex.trim()), alg, false, ["verify"]);
      return await crypto.subtle.verify(alg, key, hex(sig), msg);
    } catch (e) { lastError = alg.name + ": " + e; }
  }
  return false;
}
let lastError = "";
function status(env) {
  const k = (env.DISCORD_PUBLIC_KEY || "").trim();
  return "AoWx map randomizer is running.\nDISCORD_PUBLIC_KEY: " +
    (!k ? "NOT SET" : /^[0-9a-f]{64}$/i.test(k) ? "set (64 hex chars, looks right)" : `set but looks wrong (${k.length} chars, expected 64 hex)`) +
    (lastError ? "\nlast verify error: " + lastError : "");
}
const json = o => new Response(JSON.stringify(o), { headers: { "Content-Type": "application/json" } });
const reply = (content, ephemeral) =>
  json({ type: 4, data: { content, allowed_mentions: { parse: [] }, ...(ephemeral ? { flags: 64 } : {}) } });

export default {
  async fetch(req, env) {
    if (req.method !== "POST") return new Response(status(env));
    const body = await req.text();
    if (!(await verify(req, body, env.DISCORD_PUBLIC_KEY))) return new Response("bad signature", { status: 401 });
    const it = JSON.parse(body);
    if (it.type === 1) return json({ type: 1 });                                   // PING
    if (it.type === 2 && it.data?.name === "map")                                  // /map -> popup
      return json({ type: 9, data: { custom_id: MODAL_ID, title: TITLE, components: [{ type: 1, components: [{
        type: 4, custom_id: FIELD_ID, style: 1, label: "Please list players (separated by a comma)",
        placeholder: "Alcedes, Booska, Inioch, Paradox", required: true, max_length: 400 }] }] } });
    if (it.type === 5 && it.data?.custom_id === MODAL_ID) {                         // popup submitted
      const field = it.data.components.flatMap(r => r.components).find(c => c.custom_id === FIELD_ID);
      const r = roll(field?.value || "");
      return r.error ? reply(r.error, true) : reply(r.content, false);
    }
    return reply("Unknown command.", true);
  },
};
