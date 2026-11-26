// AoWxPresence - Discord Rich Presence for Age of Wonders X (2026-10-21).
//   AoWxPresence.exe <game pid>    started by AoWxUpdater --game-start (which AoWx.exe launches at startup)
// Polls the game every few seconds and shows
//   Playing Age of Wonders X
//   Single-Player|Multiplayer - <map>
//   Turn N - Playing as <race>
// (two or more AoWx.exe running = "Playtesting - <map>" / "Turn N", no race)
// with the AoWx icon and the elapsed time.  Exits when the game process exits.
// Off switch: HKCU\Software\Triumph Studios\Age of Wonders X\Presence  Enabled = 0 (DWORD).
using System;
using System.Diagnostics;
using System.IO;
using System.Threading;
using Microsoft.Win32;

namespace AoWxPresence
{
    internal static class Program
    {
        const string RegKey = @"Software\Triumph Studios\Age of Wonders X\Presence";
        const int PollMs = 5000, ReconnectMs = 15000;
        static readonly object LogLock = new object();
        static string logPath;

        [STAThread]
        static int Main(string[] args)
        {
            try
            {
                string dir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), @"AoWx\Presence");
                Directory.CreateDirectory(dir);
                logPath = Path.Combine(dir, "presence.log");
            }
            catch { }
            int pid;
            if (args.Length < 1 || !int.TryParse(args[0], out pid)) { Log("usage: AoWxPresence.exe <game pid>"); return 2; }
            if (!Enabled()) { Log("disabled in the registry"); return 0; }
            if (ClientId.Value.Length == 0) { Log("no Discord application id built in"); return 0; }
            Process game;
            try { game = Process.GetProcessById(pid); } catch { Log("game pid " + pid + " not running"); return 0; }
            bool fresh;
            using (Mutex m = new Mutex(true, @"Local\AoWxPresence-" + pid, out fresh))
            {
                if (!fresh) return 0;
                return Run(game, pid);
            }
        }

        static int Run(Process game, int pid)
        {
            long start;
            try { start = (long)(game.StartTime.ToUniversalTime() - new DateTime(1970, 1, 1, 0, 0, 0, DateTimeKind.Utc)).TotalSeconds; }
            catch { start = (long)(DateTime.UtcNow - new DateTime(1970, 1, 1, 0, 0, 0, DateTimeKind.Utc)).TotalSeconds; }
            Log("watching AoWx pid " + pid);
            using (GameState gs = new GameState(pid))
            using (Discord d = new Discord(ClientId.Value))
            {
                string sent = null;
                int nextConnect = 0;
                while (!game.WaitForExit(0))
                {
                    if (!d.Connected && Environment.TickCount - nextConnect >= 0)
                    {
                        if (d.Connect()) { Log("connected to Discord"); sent = null; }
                        else nextConnect = Environment.TickCount + ReconnectMs;
                    }
                    if (d.Connected)
                    {
                        string act = Activity(gs.Read(), start, GameCount() > 1);
                        if (act != sent && d.SetActivity(pid, act)) sent = act;
                        if (!d.Connected) sent = null;
                    }
                    game.WaitForExit(PollMs);
                }
                if (d.Connected) d.SetActivity(pid, null);
            }
            Log("game exited");
            return 0;
        }

        // two or more AoWx.exe running on this PC = the user is playtesting against themselves (LAN simulation)
        static int GameCount()
        {
            Process[] ps = Process.GetProcessesByName("AoWx");
            foreach (Process p in ps) p.Dispose();
            return ps.Length;
        }

        static string Activity(GameInfo g, long start, bool playtest)
        {
            string s = "{";
            if (g != null)
            {
                string mode = playtest ? "Playtesting" : g.Multiplayer ? "Multiplayer" : "Single-Player";
                string details = mode + (string.IsNullOrEmpty(g.Map) ? "" : " - " + g.Map);
                string state = g.Turn > 0 ? "Turn " + g.Turn : null;
                if (g.Race != null && !playtest) state = (state == null ? "" : state + " - ") + "Playing as " + g.Race;
                s += "\"details\":" + Discord.Str(Clip(details)) + ",";
                if (state != null) s += "\"state\":" + Discord.Str(Clip(state)) + ",";
            }
            return s + "\"timestamps\":{\"start\":" + start + "},\"assets\":{\"large_image\":\"aowx4\",\"large_text\":\"Age of Wonders X\"," +
                   "\"small_image\":\"aowx_icon\",\"small_text\":\"Age of Wonders X\"}}";
        }

        static string Clip(string s) { return s.Length <= 128 ? s : s.Substring(0, 125) + "..."; }

        static bool Enabled()
        {
            try
            {
                using (RegistryKey k = Registry.CurrentUser.OpenSubKey(RegKey))
                {
                    object v = k == null ? null : k.GetValue("Enabled");
                    return !(v is int) || (int)v != 0;
                }
            }
            catch { return true; }
        }

        internal static void Log(string s)
        {
            if (logPath == null) return;
            try
            {
                lock (LogLock)
                {
                    FileInfo fi = new FileInfo(logPath);
                    if (fi.Exists && fi.Length > 128 * 1024) File.Delete(logPath);
                    File.AppendAllText(logPath, DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") + "  " + s + Environment.NewLine);
                }
            }
            catch { }
        }
    }
}
