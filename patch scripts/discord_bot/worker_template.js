// AoWx Discord map randomizer - Cloudflare Worker (HTTP interactions, no dependencies).
// GENERATED worker.js is built from worker_template.js by build_worker.py - edit the template, not worker.js.
// Worker variable required: DISCORD_PUBLIC_KEY (the app's Public Key from the Discord Developer Portal).

const RACES = ["Humans", "Azracs", "Lizardmen", "Frostlings", "Elves", "Halflings",
               "Dwarves", "High Men", "Dark Elves", "Orcs", "Goblins", "Undead"];
const MAPS = /*MAPS*/[];          // [name, [race ids]]
const MESSAGES = /*MESSAGES*/[];
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
