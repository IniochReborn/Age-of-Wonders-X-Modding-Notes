// AoWx bot "online" keeper (2026-10-22): holds the Discord gateway connection so the bot shows online in the
// member list.  /map itself is handled by the separate aowx-map-bot Worker and does not depend on this one.
//   - one Durable Object ("main") owns the WebSocket, heartbeats and reconnects;
//   - a 1-minute cron pokes it, which keeps it in memory and reconnects after any drop or eviction;
//   - GET / on this Worker shows connection status + recent log (no secrets).
// Secret required: DISCORD_BOT_TOKEN (Bot tab -> Reset Token), set with `wrangler secret put DISCORD_BOT_TOKEN`.
import { DurableObject } from "cloudflare:workers";

const GATEWAY = "https://gateway.discord.gg/?v=10&encoding=json";
const STATUS_TEXT = "Type /map to roll a map and races";
const FATAL = [4004, 4010, 4011, 4012, 4013, 4014];   // bad token / intents: stop instead of re-identifying forever

export class Gateway extends DurableObject {
  constructor(ctx, env) {
    super(ctx, env);
    this.ws = null; this.seq = null; this.acked = true; this.beat = null;
    this.ready = false; this.fatal = null; this.lastConnect = 0; this.log = [];
  }

  note(s) {
    this.log.push(new Date().toISOString().slice(0, 19) + "Z  " + s);
    if (this.log.length > 40) this.log.shift();
  }

  async fetch(req) {
    if (new URL(req.url).pathname === "/kick") await this.ensure();
    return new Response(JSON.stringify({ connected: !!this.ws, online: this.ready, stopped: this.fatal, log: this.log }, null, 2),
                        { headers: { "Content-Type": "application/json" } });
  }

  async ensure() {
    if (this.ws || this.fatal || Date.now() - this.lastConnect < 5000) return;
    this.lastConnect = Date.now();
    if (!this.env.DISCORD_BOT_TOKEN) { this.fatal = "DISCORD_BOT_TOKEN secret is not set"; return; }
    let resp;
    try { resp = await fetch(GATEWAY, { headers: { Upgrade: "websocket" } }); }
    catch (e) { this.note("connect failed: " + e); return; }
    const ws = resp.webSocket;
    if (!ws) { this.note("no WebSocket (HTTP " + resp.status + ")"); return; }
    ws.accept();
    this.ws = ws; this.ready = false; this.acked = true;
    ws.addEventListener("message", ev => this.onMessage(ws, ev.data));
    ws.addEventListener("close", ev => this.drop(ws, "closed " + ev.code + (ev.reason ? " " + ev.reason : ""), ev.code));
    ws.addEventListener("error", () => this.drop(ws, "socket error", 0));
    this.note("connected");
  }

  drop(ws, why, code) {
    if (this.ws !== ws) return;
    this.note(why);
    clearInterval(this.beat); this.beat = null;
    this.ws = null; this.ready = false;
    try { ws.close(1000); } catch {}
    if (FATAL.includes(code)) this.fatal = why;
  }

  send(ws, o) {
    try { ws.send(JSON.stringify(o)); } catch (e) { this.drop(ws, "send failed: " + e, 0); }
  }

  onMessage(ws, data) {
    let m;
    try { m = JSON.parse(data); } catch { return; }
    if (m.s != null) this.seq = m.s;
    switch (m.op) {
      case 10:                                                   // HELLO -> start heartbeats, IDENTIFY
        clearInterval(this.beat);
        this.beat = setInterval(() => {
          if (!this.acked) { this.drop(ws, "heartbeat not acknowledged", 0); return; }
          this.acked = false;
          this.send(ws, { op: 1, d: this.seq });
        }, m.d.heartbeat_interval);
        this.send(ws, { op: 2, d: {
          token: this.env.DISCORD_BOT_TOKEN, intents: 0,
          properties: { os: "linux", browser: "aowx-bot", device: "aowx-bot" },
          presence: { status: "online", afk: false, since: null,
                      activities: [{ type: 4, name: "Custom Status", state: STATUS_TEXT }] } } });
        break;
      case 11: this.acked = true; break;                         // heartbeat ACK
      case 1: this.send(ws, { op: 1, d: this.seq }); break;      // server asks for a heartbeat now
      case 0: if (m.t === "READY") { this.ready = true; this.note("online as " + m.d.user.username); } break;
      case 7: this.drop(ws, "Discord asked for a reconnect", 0); break;
      case 9: this.drop(ws, "invalid session", 0); break;
    }
  }
}

const stub = env => env.GATEWAY.get(env.GATEWAY.idFromName("main"));

export default {
  async scheduled(event, env, ctx) { ctx.waitUntil(stub(env).fetch("https://gateway/kick")); },
  async fetch(req, env) {
    const kick = new URL(req.url).pathname === "/kick";
    return stub(env).fetch(kick ? "https://gateway/kick" : "https://gateway/status");
  },
};
