// AoWxUpdater - Age of Wonders X auto-updater (2026-10-20).
// Built by ..\build_updater.py with the in-box .NET Framework 4 compiler (C# 5).
//
// Commands
//   --check              background/scheduled: check only, write status to the registry, never download
//   --game-start <pid>   launched by AoWx.exe at startup: check; Mode Auto -> download + verify in the background,
//                        then wait for the game to exit and install silently; Mode Ask -> check only; Off -> exit
//   --install <pid>      the player confirmed "Update now": wait for the game to exit, download/verify if needed,
//                        install with a small progress window
//   --register           (re)create the per-user scheduled task "AoWx updater" (removed instead when Mode = Off or
//                        Frequency = GameOnly)
//   --unregister         remove the scheduled task
//   --status             print the registry status (diagnostics)
//   --do-install ...     internal: runs from a temp copy so the installer can overwrite the real AoWxUpdater.exe
//
// Trust model: latest.json + latest.json.sig from https://aowx.org/update/[test/] must carry a valid RSA-3072
// PKCS#1 v1.5 / SHA-256 signature by the embedded public key (PublicKey.cs, generated at build time); the version
// must be strictly newer than the installed one; the downloaded installer must match the signed size + SHA-256.
// Anything else is refused and the download deleted.  Test overrides (--base-url / --pubkey) are honoured ONLY when
// HKCU\...\Updater\TestOverrides = 1 AND the base URL is http(s)://127.0.0.1 or localhost - so they cannot be used
// to point a player's updater at a remote server or a foreign key.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Net;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Win32;

namespace AoWxUpdater
{
    internal static class Program
    {
        const string RegPath = @"Software\Triumph Studios\Age of Wonders X\Updater";
        const string TaskName = "AoWx updater";
        const string PublicBase = "https://aowx.org/update/";
        const string MutexName = @"Local\AoWxUpdater.single";

        // status values the game reads
        const int ST_UNKNOWN = 0, ST_UPTODATE = 1, ST_AVAILABLE = 2, ST_READY = 3;

        static string GameDir;          // folder that holds AoWx.exe (the exe's own folder, or --game-dir)
        static string WorkDir;          // %LOCALAPPDATA%\AoWx\Updater
        static string BaseUrlOverride;  // test only
        static string PubKeyOverride;   // test only (path to an RSAKeyValue xml)

        [STAThread]
        static int Main(string[] args)
        {
            try
            {
                ServicePointManager.SecurityProtocol = (SecurityProtocolType)3072;   // TLS 1.2
                WorkDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), @"AoWx\Updater");
                Directory.CreateDirectory(WorkDir);
                GameDir = Path.GetDirectoryName(Path.GetFullPath(Application.ExecutablePath));
                string cmd = args.Length > 0 ? args[0].ToLowerInvariant() : "--check";
                List<string> rest = new List<string>();
                for (int i = 1; i < args.Length; i++) rest.Add(args[i]);
                ParseCommon(rest);
                if (cmd != "--status" && cmd != "--task-xml") Log("run " + cmd + " from " + GameDir);

                switch (cmd)
                {
                    case "--check": return CmdCheck();
                    case "--game-start": return CmdGameStart(ArgInt(rest, 0));
                    case "--install": return CmdInstall(ArgInt(rest, 0), false);
                    case "--repair": return CmdInstall(ArgInt(rest, 0), true);
                    case "--register": return CmdRegister();
                    case "--unregister": return CmdUnregister();
                    case "--status": return CmdStatus();
                    case "--task-xml": Console.WriteLine(TaskXml()); return 0;
                    case "--do-install": return CmdDoInstall(rest);
                    default:
                        Log("unknown command " + cmd);
                        return 2;
                }
            }
            catch (Exception e)
            {
                Log("FATAL " + e);
                return 1;
            }
        }

        // ------------------------------------------------------------------ args / settings
        static void ParseCommon(List<string> rest)
        {
            for (int i = 0; i < rest.Count; i++)
            {
                string a = rest[i];
                if (a == "--game-dir" && i + 1 < rest.Count) { GameDir = Path.GetFullPath(rest[i + 1]); rest.RemoveRange(i, 2); i--; }
                else if (a == "--base-url" && i + 1 < rest.Count) { BaseUrlOverride = rest[i + 1]; rest.RemoveRange(i, 2); i--; }
                else if (a == "--pubkey" && i + 1 < rest.Count) { PubKeyOverride = rest[i + 1]; rest.RemoveRange(i, 2); i--; }
            }
            if (BaseUrlOverride != null || PubKeyOverride != null)
            {
                bool allowed = RegInt("TestOverrides", 0) == 1 && BaseUrlOverride != null && IsLocalUrl(BaseUrlOverride);
                if (!allowed)
                {
                    Log("test overrides ignored (need TestOverrides=1 and a localhost --base-url)");
                    BaseUrlOverride = null; PubKeyOverride = null;
                }
                else Log("TEST MODE: base " + BaseUrlOverride + (PubKeyOverride != null ? " key " + PubKeyOverride : ""));
            }
        }

        static bool IsLocalUrl(string u)
        {
            Uri uri;
            if (!Uri.TryCreate(u, UriKind.Absolute, out uri)) return false;
            return (uri.Scheme == "http" || uri.Scheme == "https") && (uri.Host == "127.0.0.1" || uri.Host == "localhost");
        }

        static int ArgInt(List<string> rest, int i)
        {
            int v;
            return (i < rest.Count && int.TryParse(rest[i], out v)) ? v : 0;
        }

        static RegistryKey Key(bool write)
        {
            return write ? Registry.CurrentUser.CreateSubKey(RegPath) : Registry.CurrentUser.OpenSubKey(RegPath);
        }

        static string RegStr(string name, string def)
        {
            using (RegistryKey k = Key(false))
            {
                object v = k == null ? null : k.GetValue(name);
                return v == null ? def : v.ToString();
            }
        }

        static int RegInt(string name, int def)
        {
            using (RegistryKey k = Key(false))
            {
                object v = k == null ? null : k.GetValue(name);
                if (v is int) return (int)v;
                int r;
                return (v != null && int.TryParse(v.ToString(), out r)) ? r : def;
            }
        }

        static void RegSet(string name, object val)
        {
            using (RegistryKey k = Key(true))
            {
                if (val is int) k.SetValue(name, val, RegistryValueKind.DWord);
                else k.SetValue(name, val == null ? "" : val.ToString(), RegistryValueKind.String);
            }
        }

        static void RegDel(string name)
        {
            using (RegistryKey k = Key(true)) { k.DeleteValue(name, false); }
        }

        static string Mode()       // Auto (default) / Ask / Off
        {
            string m = RegStr("Mode", "Auto");
            if (string.Equals(m, "Ask", StringComparison.OrdinalIgnoreCase)) return "Ask";
            if (string.Equals(m, "Off", StringComparison.OrdinalIgnoreCase)) return "Off";
            return "Auto";
        }

        static string Frequency()  // Scheduled (default) / GameOnly
        {
            return string.Equals(RegStr("Frequency", "Scheduled"), "GameOnly", StringComparison.OrdinalIgnoreCase) ? "GameOnly" : "Scheduled";
        }

        static string BaseUrl()
        {
            if (BaseUrlOverride != null) return BaseUrlOverride.EndsWith("/") ? BaseUrlOverride : BaseUrlOverride + "/";
            return string.Equals(RegStr("Channel", ""), "test", StringComparison.OrdinalIgnoreCase) ? PublicBase + "test/" : PublicBase;
        }

        // ------------------------------------------------------------------ logging
        static readonly object LogLock = new object();
        internal static void Log(string s)
        {
            try
            {
                lock (LogLock)
                {
                    string p = Path.Combine(WorkDir ?? Path.GetTempPath(), "updater.log");
                    FileInfo fi = new FileInfo(p);
                    if (fi.Exists && fi.Length > 256 * 1024)
                    {
                        string old = p + ".1";
                        if (File.Exists(old)) File.Delete(old);
                        File.Move(p, old);
                    }
                    File.AppendAllText(p, DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") + " [" + Process.GetCurrentProcess().Id + "] " + s + Environment.NewLine);
                }
            }
            catch { }
            try { Console.WriteLine(s); } catch { }
        }

        // ------------------------------------------------------------------ installed version
        // Primary source: the engine's own version immediates in AoWEPACK.dll (what the game reports) -
        //   31 D2 42 31 C9 B1 <minor> 68 <patch:u32>   (TAoWEngine.Create; see patch_version_420.py)
        // Fallback: AoWx.version (one line "1.37.420") written into the game root by the installer build.
        internal static int[] InstalledVersion()
        {
            try
            {
                string dll = Path.Combine(GameDir, "AoWEPACK.dll");
                if (File.Exists(dll))
                {
                    byte[] d = File.ReadAllBytes(dll);
                    for (int i = 0; i + 12 <= d.Length; i++)
                    {
                        if (d[i] == 0x31 && d[i + 1] == 0xD2 && d[i + 2] == 0x42 && d[i + 3] == 0x31 && d[i + 4] == 0xC9 &&
                            d[i + 5] == 0xB1 && d[i + 7] == 0x68)
                        {
                            int minor = d[i + 6];
                            int patch = BitConverter.ToInt32(d, i + 8);
                            if (patch > 0 && patch < 100000) return new int[] { 1, minor, patch };
                        }
                    }
                }
            }
            catch (Exception e) { Log("dll version read failed: " + e.Message); }
            try
            {
                string f = Path.Combine(GameDir, "AoWx.version");
                if (File.Exists(f))
                {
                    int[] v = ParseVersion(File.ReadAllText(f).Trim());
                    if (v != null) return v;
                }
            }
            catch (Exception e) { Log("AoWx.version read failed: " + e.Message); }
            return null;
        }

        internal static int[] ParseVersion(string s)
        {
            if (s == null) return null;
            string[] p = s.Trim().TrimStart('v', 'V').Split('.');
            if (p.Length != 3) return null;
            int[] r = new int[3];
            for (int i = 0; i < 3; i++) if (!int.TryParse(p[i], out r[i]) || r[i] < 0) return null;
            return r;
        }

        internal static int CompareVersion(int[] a, int[] b)
        {
            for (int i = 0; i < 3; i++) if (a[i] != b[i]) return a[i] < b[i] ? -1 : 1;
            return 0;
        }

        static string VStr(int[] v) { return v == null ? "unknown" : v[0] + "." + v[1] + "." + v[2]; }

        // ------------------------------------------------------------------ notice fetch + verify
        internal class Notice
        {
            public string Version, Channel, InstallerName, InstallerUrl, Sha256, Notes;
            public long Size;
            public int[] V;
        }

        static byte[] HttpGet(string url, int timeoutMs)
        {
            HttpWebRequest req = (HttpWebRequest)WebRequest.Create(url);
            req.UserAgent = "AoWx-Updater";
            req.AllowAutoRedirect = true;
            req.Timeout = timeoutMs;
            req.ReadWriteTimeout = timeoutMs;
            req.CachePolicy = new System.Net.Cache.RequestCachePolicy(System.Net.Cache.RequestCacheLevel.NoCacheNoStore);
            req.Headers.Add("Cache-Control", "no-cache");
            using (HttpWebResponse resp = (HttpWebResponse)req.GetResponse())
            using (Stream s = resp.GetResponseStream())
            using (MemoryStream ms = new MemoryStream())
            {
                s.CopyTo(ms);
                return ms.ToArray();
            }
        }

        static RSACryptoServiceProvider PublicKey()
        {
            string xml = PublicKeyXml.Value;
            if (PubKeyOverride != null) xml = File.ReadAllText(PubKeyOverride);
            RSACryptoServiceProvider rsa = new RSACryptoServiceProvider();
            rsa.PersistKeyInCsp = false;
            rsa.FromXmlString(xml);
            return rsa;
        }

        // Returns the verified notice, or null (reason logged).  Never trusts unsigned data.
        internal static Notice FetchNotice()
        {
            string b = BaseUrl();
            byte[] body, sig;
            try
            {
                body = HttpGet(b + "latest.json", 30000);
                sig = Convert.FromBase64String(Encoding.ASCII.GetString(HttpGet(b + "latest.json.sig", 30000)).Trim());
            }
            catch (Exception e) { Log("fetch failed: " + e.Message); return null; }
            using (RSACryptoServiceProvider rsa = PublicKey())
            {
                if (!rsa.VerifyData(body, "SHA256", sig)) { Log("REFUSED: latest.json signature invalid"); return null; }
            }
            Dictionary<string, object> j;
            try { j = new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(Encoding.UTF8.GetString(body)); }
            catch (Exception e) { Log("REFUSED: latest.json unreadable: " + e.Message); return null; }
            Notice n = new Notice();
            n.Version = JStr(j, "version"); n.Channel = JStr(j, "channel"); n.InstallerName = JStr(j, "installer_name");
            n.InstallerUrl = JStr(j, "installer_url"); n.Sha256 = (JStr(j, "sha256") ?? "").ToLowerInvariant(); n.Notes = JStr(j, "notes") ?? "";
            object sz; n.Size = (j.TryGetValue("installer_size", out sz) && sz != null) ? Convert.ToInt64(sz) : -1;
            n.V = ParseVersion(n.Version);
            if (n.V == null || n.InstallerUrl == null || n.Sha256.Length != 64 || n.Size <= 0 || string.IsNullOrEmpty(n.InstallerName))
            { Log("REFUSED: latest.json missing fields"); return null; }
            Uri u;
            if (!Uri.TryCreate(n.InstallerUrl, UriKind.Absolute, out u) || (u.Scheme != "https" && !(BaseUrlOverride != null && IsLocalUrl(n.InstallerUrl))))
            { Log("REFUSED: installer_url is not https"); return null; }
            if (n.InstallerName.IndexOfAny(Path.GetInvalidFileNameChars()) >= 0 || !n.InstallerName.EndsWith(".exe", StringComparison.OrdinalIgnoreCase))
            { Log("REFUSED: bad installer_name"); return null; }
            return n;
        }

        static string JStr(Dictionary<string, object> j, string k)
        {
            object v; return j.TryGetValue(k, out v) && v != null ? v.ToString() : null;
        }

        // check + write status.  Returns the notice when a strictly newer version is available, else null.
        static Notice CheckAndRecord()
        {
            int[] inst = InstalledVersion();
            Notice n = FetchNotice();
            RegSet("LastChecked", DateTime.Now.ToString("yyyy-MM-dd HH:mm"));
            if (n == null) { RegSet("LastError", "check failed (see updater.log)"); return null; }
            RegDel("LastError");
            RegSet("LatestVersion", n.Version);
            RegSet("Notes", n.Notes.Length > 200 ? n.Notes.Substring(0, 200) : n.Notes);
            if (inst == null) { Log("installed version unknown - not offering updates"); RegSet("Status", ST_UNKNOWN); return null; }
            if (CompareVersion(n.V, inst) <= 0)
            {
                Log("up to date (installed " + VStr(inst) + ", latest " + n.Version + ")");
                RegSet("Status", ST_UPTODATE);
                return null;
            }
            Log("update available: " + VStr(inst) + " -> " + n.Version);
            if (RegInt("Status", 0) != ST_READY || RegStr("ReadyVersion", "") != n.Version) RegSet("Status", ST_AVAILABLE);
            return n;
        }

        // ------------------------------------------------------------------ download + verify
        static string FileSha256(string path)
        {
            using (FileStream f = File.OpenRead(path))
            using (SHA256 h = SHA256.Create())
            {
                byte[] d = h.ComputeHash(f);
                StringBuilder sb = new StringBuilder();
                foreach (byte x in d) sb.Append(x.ToString("x2"));
                return sb.ToString();
            }
        }

        internal static bool FileMatches(string path, Notice n)
        {
            try { return File.Exists(path) && new FileInfo(path).Length == n.Size && FileSha256(path) == n.Sha256; }
            catch { return false; }
        }

        // Download (or reuse) the installer; returns the verified local path or null.
        internal static string DownloadVerified(Notice n, Action<int> progress)
        {
            string dst = Path.Combine(WorkDir, n.InstallerName);
            if (FileMatches(dst, n)) { Log("reusing verified download " + dst); return dst; }
            string part = dst + ".part";
            try
            {
                if (File.Exists(part)) File.Delete(part);
                HttpWebRequest req = (HttpWebRequest)WebRequest.Create(n.InstallerUrl);
                req.UserAgent = "AoWx-Updater";
                req.AllowAutoRedirect = true;
                req.Timeout = 60000; req.ReadWriteTimeout = 60000;
                using (HttpWebResponse resp = (HttpWebResponse)req.GetResponse())
                using (Stream s = resp.GetResponseStream())
                using (FileStream f = File.Create(part))
                {
                    byte[] buf = new byte[1 << 16];
                    long got = 0; int r, lastPct = -1;
                    while ((r = s.Read(buf, 0, buf.Length)) > 0)
                    {
                        got += r;
                        if (got > n.Size) throw new IOException("download larger than the signed size");
                        f.Write(buf, 0, r);
                        int pct = (int)(got * 100 / n.Size);
                        if (pct != lastPct && progress != null) { lastPct = pct; progress(pct); }
                    }
                }
                if (!FileMatches(part, n))
                {
                    Log("REFUSED: downloaded installer does not match the signed size/SHA-256 - deleted");
                    File.Delete(part);
                    return null;
                }
                if (File.Exists(dst)) File.Delete(dst);
                File.Move(part, dst);
                Log("downloaded + verified " + dst);
                return dst;
            }
            catch (Exception e)
            {
                Log("download failed: " + e.Message);
                try { if (File.Exists(part)) File.Delete(part); } catch { }
                return null;
            }
        }

        // ------------------------------------------------------------------ process helpers
        static readonly string[] BlockingProcs = { "AoWx", "AoWDevX", "AoWSetup", "AoW" };

        static bool AnyGameProcess()
        {
            foreach (string p in BlockingProcs)
            {
                Process[] ps = Process.GetProcessesByName(p);
                foreach (Process x in ps)
                {
                    try
                    {
                        string f = x.MainModule.FileName;
                        if (f != null && string.Equals(Path.GetDirectoryName(f), GameDir, StringComparison.OrdinalIgnoreCase)) return true;
                    }
                    catch { return true; }   // can't inspect (elevated game?) -> treat as blocking
                }
            }
            return false;
        }

        static void WaitPid(int pid)
        {
            if (pid <= 0) return;
            try { Process p = Process.GetProcessById(pid); p.WaitForExit(); } catch { }
        }

        // Running blockers of THIS install, as friendly names (2026-11-04).
        static List<string> RunningBlockers(out bool gameRunning)
        {
            List<string> names = new List<string>();
            gameRunning = false;
            foreach (string p in BlockingProcs)
            {
                bool hit = false;
                foreach (Process x in Process.GetProcessesByName(p))
                {
                    try
                    {
                        string f = x.MainModule.FileName;
                        if (f != null && string.Equals(Path.GetDirectoryName(f), GameDir, StringComparison.OrdinalIgnoreCase)) hit = true;
                    }
                    catch { hit = true; }
                }
                if (!hit) continue;
                if (p == "AoWx" || p == "AoW") gameRunning = true;
                names.Add(p == "AoWDevX" ? "the AoWx map editor (AoWDevX)"
                        : p == "AoWSetup" ? "AoWSetup"
                        : "Age of Wonders X");
            }
            return names;
        }

        static void WaitNoGame()
        {
            while (AnyGameProcess()) Thread.Sleep(2000);
        }

        // Like WaitNoGame, but when the GAME is closed and only the editor / AoWSetup keep the update waiting, tell the
        // player what to close (2026-11-04: players forgot an open AoWDevX and thought the updater was broken).
        // Nothing is closed for them (unsaved editor work); the notice disappears and the update continues by itself.
        static void WaitNoGameNotify()
        {
            NoticeWindow notice = null;
            int seen = 0;
            try
            {
                while (true)
                {
                    bool game;
                    List<string> b = RunningBlockers(out game);
                    if (b.Count == 0) break;
                    if (game) { seen = 0; if (notice != null) { notice.CloseIt(); notice = null; } }
                    else if (++seen >= 3)                      // ~6 s: don't flash for a briefly opened AoWSetup
                    {
                        string msg = "An Age of Wonders X update is ready to install, but this is still open:\n\n";
                        foreach (string s in b) msg += "    •  " + s + "\n";
                        msg += "\nSave your work and close it - the update will continue automatically.";
                        if (notice == null) { Log("waiting for: " + string.Join(", ", b.ToArray())); notice = NoticeWindow.Open(msg); }
                        else notice.SetMessage(msg);
                    }
                    Thread.Sleep(2000);
                }
            }
            finally { if (notice != null) notice.CloseIt(); }
        }

        // ------------------------------------------------------------------ commands
        static Mutex TakeMutex(int waitMs)
        {
            bool created;
            Mutex m = new Mutex(false, MutexName, out created);
            try { if (m.WaitOne(waitMs)) return m; }
            catch (AbandonedMutexException) { return m; }
            m.Dispose();
            return null;
        }

        static int CmdCheck()
        {
            if (Mode() == "Off") { Log("check: mode Off"); return 0; }
            Mutex m = TakeMutex(0);
            if (m == null) { Log("check: another updater instance is running"); return 0; }
            try { CheckAndRecord(); return 0; }
            finally { m.ReleaseMutex(); m.Dispose(); }
        }

        // Discord Rich Presence helper (independent of the update mode); it exits with the game
        static void StartPresence(int pid)
        {
            try
            {
                string exe = Path.Combine(GameDir, "AoWxPresence.exe");
                if (!File.Exists(exe) || pid <= 0) return;
                ProcessStartInfo si = new ProcessStartInfo(exe, pid.ToString());
                si.UseShellExecute = false; si.CreateNoWindow = true; si.WorkingDirectory = GameDir;
                Process.Start(si).Dispose();
            }
            catch (Exception e) { Log("presence: " + e.Message); }
        }

        static int CmdGameStart(int pid)
        {
            StartPresence(pid);
            string mode = Mode();
            if (mode == "Off") { Log("game-start: mode Off"); return 0; }
            EnsureTask();
            Mutex m = TakeMutex(0);
            if (m == null) { Log("game-start: another updater instance is running"); return 0; }
            try
            {
                Notice n = CheckAndRecord();
                if (n == null || mode != "Auto") return 0;
                string file = DownloadVerified(n, null);
                if (file == null) return 0;
                RegSet("ReadyVersion", n.Version);
                RegSet("Status", ST_READY);
                Log("auto: update " + n.Version + " ready - installs when the game closes");
                // wait for this game process, then for every game/editor/setup window of this install to close
                WaitPid(pid);
                Thread.Sleep(1500);
                WaitNoGameNotify();
                if (Mode() == "Off") { Log("auto: mode switched to Off while waiting - not installing"); return 0; }
                bool shown = RegInt("InstallRequested", 0) == 1;
                RegDel("InstallRequested");
                return LaunchInstall(file, n, shown);
            }
            finally { m.ReleaseMutex(); m.Dispose(); }
        }

        // repair = typed REPAIR on the title screen (2026-10-31): download + reinstall the latest release even when the
        // installed version is already current (fixes broken / missing game files).
        static int CmdInstall(int pid, bool repair)
        {
            Mutex m = TakeMutex(repair ? 20000 : 0);
            if (m == null && repair)
            {
                Log("repair: another updater instance is busy");
                MessageBox.Show("The updater is busy right now. Please try the repair again in a minute.",
                                "Age of Wonders X repair", MessageBoxButtons.OK, MessageBoxIcon.Information);
                return 1;
            }
            if (m == null)
            {
                // the game-start instance is already waiting with a verified download: let it do the install
                RegSet("InstallRequested", 1);
                Log("install: handed to the running updater instance");
                return 0;
            }
            try
            {
                Application.EnableVisualStyles();
                ProgressForm form = new ProgressForm();
                int rc = 0;
                Thread t = new Thread(delegate ()
                {
                    try
                    {
                        form.SetText("Waiting for Age of Wonders X to close...");
                        WaitPid(pid);
                        Thread.Sleep(1000);
                        if (AnyGameProcess()) { form.SetText("Close Age of Wonders X, the editor and AoWSetup to continue..."); WaitNoGameNotify(); }
                        form.SetText("Checking for the latest version...");
                        Notice n;
                        if (repair)
                        {
                            Log("repair requested");
                            n = FetchNotice();
                            if (n == null) { form.Fail("Could not reach or verify the update server. Please try again later."); rc = 1; return; }
                            RegSet("LatestVersion", n.Version);
                        }
                        else
                        {
                            n = CheckAndRecord();
                            if (n == null)
                            {
                                form.Fail(RegStr("LastError", "") != "" ? "Could not verify the update. Please try again later." : "Age of Wonders X is already up to date.");
                                rc = 1; return;
                            }
                        }
                        form.SetText((repair ? "Repair: downloading Age of Wonders X " : "Downloading Age of Wonders X ") + n.Version + "...");
                        string file = DownloadVerified(n, delegate (int pct) { form.SetProgress(pct); });
                        if (file == null) { form.Fail("The download could not be verified and was deleted. Please try again later."); rc = 1; return; }
                        RegSet("ReadyVersion", n.Version);
                        RegSet("Status", ST_READY);
                        form.SetText("Installing Age of Wonders X " + n.Version + "...");
                        form.SetProgress(-1);
                        rc = LaunchInstall(file, n, true);
                        form.Done();   // the run copy shows its own "Installing..." window
                    }
                    catch (Exception e) { Log("install thread: " + e); form.Fail("Update failed: " + e.Message); rc = 1; }
                });
                t.IsBackground = true;
                form.Shown += delegate { t.Start(); };
                Application.Run(form);
                return rc;
            }
            finally { m.ReleaseMutex(); m.Dispose(); }
        }

        // Copy ourselves out of the game folder (the installer replaces AoWxUpdater.exe) and run the install from there.
        static int LaunchInstall(string installer, Notice n, bool visible)
        {
            string runDir = Path.Combine(WorkDir, "run");
            Directory.CreateDirectory(runDir);
            string runExe = Path.Combine(runDir, "AoWxUpdater.exe");
            try { File.Copy(Application.ExecutablePath, runExe, true); }
            catch (Exception e) { Log("could not stage the run copy: " + e.Message); return 1; }
            string a = "--do-install \"" + installer + "\" \"" + GameDir + "\" " + n.Version + " " + n.Sha256 + " " + n.Size + (visible ? " visible " : " quiet ") + Process.GetCurrentProcess().Id;
            Log("handing install to " + runExe);
            // do NOT wait: this process lives in the game folder and must exit so the installer can replace it
            Process.Start(new ProcessStartInfo(runExe, a) { UseShellExecute = false, WorkingDirectory = runDir });
            return 0;
        }

        static bool DirWritable(string dir)
        {
            try
            {
                string t = Path.Combine(dir, ".aowx_write_test_" + Process.GetCurrentProcess().Id);
                File.WriteAllText(t, "x");
                File.Delete(t);
                return true;
            }
            catch { return false; }
        }

        // runs from %LOCALAPPDATA%\AoWx\Updater\run\: args = installer, gamedir, version, sha256, size, visible|quiet
        static int CmdDoInstall(List<string> a)
        {
            if (a.Count < 6) { Log("do-install: bad args"); return 2; }
            string installer = a[0]; GameDir = a[1];
            Notice n = new Notice(); n.Version = a[2]; n.Sha256 = a[3]; n.Size = long.Parse(a[4]);
            bool visible = a[5] == "visible";
            int parent = a.Count > 6 ? int.Parse(a[6]) : 0;
            WaitPid(parent);                     // the game-folder updater must be gone before its exe is replaced
            if (visible)
            {
                Application.EnableVisualStyles();
                ProgressForm form = new ProgressForm();
                int rc = 1;
                Thread t = new Thread(delegate ()
                {
                    try { form.SetText("Installing Age of Wonders X " + n.Version + "..."); rc = DoInstallCore(installer, n, true); }
                    catch (Exception e) { Log("do-install: " + e); }
                    form.Done();
                });
                t.IsBackground = true;
                form.Shown += delegate { t.Start(); };
                Application.Run(form);
                return rc;
            }
            return DoInstallCore(installer, n, false);
        }

        static int DoInstallCore(string installer, Notice n, bool visible)
        {
            // re-verify right before running: the file must still be exactly the signed installer
            if (!FileMatches(installer, n)) { Log("do-install: REFUSED - installer changed since verification"); try { File.Delete(installer); } catch { } return 1; }
            if (!File.Exists(Path.Combine(GameDir, "AoWx.exe"))) { Log("do-install: AoWx.exe not found in " + GameDir); return 1; }
            WaitNoGameNotify();
            string logf = Path.Combine(WorkDir, "install.log");
            string args = "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /AOWXUPDATE=1 /DIR=\"" + GameDir + "\" /LOG=\"" + logf + "\"";
            ProcessStartInfo si = new ProcessStartInfo(installer);
            if (DirWritable(GameDir))
            {
                si.Arguments = args + " /CURRENTUSER";       // no UAC prompt when the folder is user-writable
                si.UseShellExecute = false;
            }
            else
            {
                si.Arguments = args;                          // Program Files etc.: Windows asks for admin
                si.UseShellExecute = true;
                si.Verb = "runas";
            }
            Log("running installer " + installer + " " + si.Arguments);
            int code;
            try
            {
                Process p = Process.Start(si);
                p.WaitForExit();
                code = p.ExitCode;
            }
            catch (Exception e)
            {
                Log("installer could not start: " + e.Message);
                if (visible) MessageBox.Show("The update could not be started:\n" + e.Message + "\n\nAntivirus software or a declined administrator prompt can cause this.", "Age of Wonders X update", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return 1;
            }
            Log("installer exit code " + code);
            if (code != 0)
            {
                if (visible) MessageBox.Show("The update did not complete (installer code " + code + ").\nDetails: " + logf, "Age of Wonders X update", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return code;
            }
            int[] inst = InstalledVersion();
            int[] want = ParseVersion(n.Version);
            if (inst != null && want != null && CompareVersion(inst, want) >= 0) RegSet("Status", ST_UPTODATE);
            else { Log("installed version after update: " + VStr(inst) + " (expected " + n.Version + ")"); RegSet("Status", ST_UNKNOWN); }
            RegDel("ReadyVersion");
            try { File.Delete(installer); } catch { }
            // re-register the task with the freshly installed updater (honours Mode/Frequency)
            string gameExe = Path.Combine(GameDir, "AoWxUpdater.exe");
            if (File.Exists(gameExe))
                try { Process.Start(new ProcessStartInfo(gameExe, "--register") { UseShellExecute = false, CreateNoWindow = true }).WaitForExit(30000); } catch { }
            // 2026-10-21 user: open AoWSetup once the update is installed.  Launched from this (non-elevated, user)
            // process - never from the installer's [Run] section, which may run elevated.
            string setup = Path.Combine(GameDir, "AoWSetup.exe");
            if (File.Exists(setup))
            {
                try
                {
                    Process.Start(new ProcessStartInfo(setup) { UseShellExecute = true, WorkingDirectory = GameDir });
                    Log("launched " + setup);
                }
                catch (Exception e) { Log("could not launch AoWSetup: " + e.Message); }
            }
            else Log("AoWSetup.exe not found - not launched");
            return 0;
        }

        static int CmdStatus()
        {
            Console.WriteLine("game dir      : " + GameDir);
            Console.WriteLine("installed     : " + VStr(InstalledVersion()));
            Console.WriteLine("mode          : " + Mode() + "   frequency: " + Frequency() + "   base: " + BaseUrl());
            Console.WriteLine("status        : " + RegInt("Status", 0) + "   latest: " + RegStr("LatestVersion", "") + "   ready: " + RegStr("ReadyVersion", ""));
            Console.WriteLine("last checked  : " + RegStr("LastChecked", "") + "   error: " + RegStr("LastError", ""));
            return 0;
        }

        // ------------------------------------------------------------------ scheduled task
        static string Xml(string s) { return System.Security.SecurityElement.Escape(s); }

        // The task runs AoWxUpdater.exe --check directly (a windowless winexe, per-user, no admin).  1.37.424: it used
        // to run an encoded PowerShell command via conhost --headless so it could unregister itself when the game
        // folder was deleted - antivirus heuristics flag encoded PowerShell from a scheduled task, which blocked
        // updates for some players.  Now a deleted folder just leaves a task that fails silently (no window), and
        // EnsureTask (every game start) re-points the task when the folder moved or an old PowerShell task exists.
        static string TaskExe() { return Path.Combine(GameDir, "AoWxUpdater.exe"); }

        // 1.37.424: a task registered by an ELEVATED process (silent update started with runas, game/AoWSetup set to
        // "Run as administrator") was owned by Administrators with Read-only access for the player, so every later
        // non-elevated --register / EnsureTask failed with "Access is denied" and the task stayed stale forever.
        // The task's own security descriptor now grants the player's account full control (plus Administrators and
        // SYSTEM), whoever registers it.
        static string TaskSddl()
        {
            string sid = System.Security.Principal.WindowsIdentity.GetCurrent().User.Value;
            return "D:(A;;FA;;;BA)(A;;FA;;;SY)(A;;FA;;;" + sid + ")";
        }

        internal static string TaskXml()
        {
            string exe = TaskExe();
            string user = Environment.UserDomainName + "\\" + Environment.UserName;
            string start = DateTime.Today.ToString("yyyy-MM-dd") + "T16:20:00";
            return
"<?xml version=\"1.0\" encoding=\"UTF-16\"?>\r\n" +
"<Task version=\"1.2\" xmlns=\"http://schemas.microsoft.com/windows/2004/02/mit/task\">\r\n" +
"  <RegistrationInfo><Description>Checks aowx.org for Age of Wonders X updates (check only; downloads happen while the game runs).</Description>" +
"<SecurityDescriptor>" + Xml(TaskSddl()) + "</SecurityDescriptor></RegistrationInfo>\r\n" +
"  <Triggers>\r\n" +
"    <LogonTrigger><Enabled>true</Enabled><UserId>" + Xml(user) + "</UserId><Delay>PT2M</Delay></LogonTrigger>\r\n" +
"    <CalendarTrigger><StartBoundary>" + start + "</StartBoundary><Enabled>true</Enabled><ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay></CalendarTrigger>\r\n" +
"  </Triggers>\r\n" +
"  <Principals><Principal id=\"Author\"><UserId>" + Xml(user) + "</UserId><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>\r\n" +
"  <Settings>\r\n" +
"    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>\r\n" +
"    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>\r\n" +
"    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>\r\n" +
"    <StartWhenAvailable>true</StartWhenAvailable>\r\n" +
"    <RunOnlyIfNetworkAvailable>true</RunOnlyIfNetworkAvailable>\r\n" +
"    <ExecutionTimeLimit>PT10M</ExecutionTimeLimit>\r\n" +
"    <Enabled>true</Enabled>\r\n" +
"  </Settings>\r\n" +
"  <Actions Context=\"Author\"><Exec><Command>" + Xml(exe) + "</Command><Arguments>--check</Arguments><WorkingDirectory>" + Xml(GameDir) + "</WorkingDirectory></Exec></Actions>\r\n" +
"</Task>\r\n";
        }

        static int RunSchtasks(string args)
        {
            ProcessStartInfo si = new ProcessStartInfo(Path.Combine(Environment.SystemDirectory, "schtasks.exe"), args);
            si.UseShellExecute = false; si.CreateNoWindow = true; si.RedirectStandardOutput = true; si.RedirectStandardError = true;
            Process p = Process.Start(si);
            string o = p.StandardOutput.ReadToEnd() + p.StandardError.ReadToEnd();
            p.WaitForExit();
            Log("schtasks " + args + " -> " + p.ExitCode + " " + o.Trim());
            return p.ExitCode;
        }

        static string TaskNameEff() { return RegStr("TaskNameOverride", TaskName); }   // tests only

        static int CmdRegister()
        {
            if (Mode() == "Off" || Frequency() == "GameOnly") return CmdUnregister();
            string x = Path.Combine(WorkDir, "task.xml");
            File.WriteAllText(x, TaskXml(), Encoding.Unicode);
            return RunSchtasks("/Create /TN \"" + TaskNameEff() + "\" /XML \"" + x + "\" /F") == 0 ? 0 : 1;
        }

        static int CmdUnregister()
        {
            RunSchtasks("/Delete /TN \"" + TaskNameEff() + "\" /F");
            return 0;
        }

        // game start: if the scheduled check is wanted but the registered task is missing, still the old PowerShell
        // form, or points at another folder -> register it again.  Non-fatal, quiet.
        static void EnsureTask()
        {
            try
            {
                if (Mode() == "Off" || Frequency() == "GameOnly") return;
                ProcessStartInfo si = new ProcessStartInfo(Path.Combine(Environment.SystemDirectory, "schtasks.exe"),
                    "/Query /TN \"" + TaskNameEff() + "\" /XML");
                si.UseShellExecute = false; si.CreateNoWindow = true; si.RedirectStandardOutput = true; si.RedirectStandardError = true;
                Process p = Process.Start(si);
                string x = p.StandardOutput.ReadToEnd(); p.StandardError.ReadToEnd();
                p.WaitForExit();
                bool ok = p.ExitCode == 0 && x.IndexOf("powershell", StringComparison.OrdinalIgnoreCase) < 0
                          && x.IndexOf(Xml(TaskExe()), StringComparison.OrdinalIgnoreCase) >= 0;
                if (!ok) { Log("game-start: scheduled task missing/outdated -> re-register"); CmdRegister(); }
            }
            catch (Exception e) { Log("EnsureTask: " + e.Message); }
        }
    }

    // progress window for player-visible updates (2026-11-04: minimizable, not always-on-top, percent in the title
    // so it reads from the taskbar, rotating "Did you know?" facts like the installer)
    internal class ProgressForm : Form
    {
        readonly Label label, factHead, factBody;
        readonly ProgressBar bar;
        readonly System.Windows.Forms.Timer factTimer;
        readonly Random rnd = new Random();
        int factIdx = -1;
        const string BaseTitle = "Age of Wonders X update";

        public ProgressForm()
        {
            Text = BaseTitle;
            FormBorderStyle = FormBorderStyle.FixedDialog;
            MaximizeBox = false; MinimizeBox = true;
            ShowInTaskbar = true;
            StartPosition = FormStartPosition.CenterScreen;
            ClientSize = new Size(460, 196);
            BackColor = Color.FromArgb(20, 20, 20);
            ForeColor = Color.Gainsboro;
            try { Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath); } catch { }
            label = new Label { Left = 16, Top = 16, Width = 428, Height = 24, Text = "Preparing update..." };
            bar = new ProgressBar { Left = 16, Top = 46, Width = 428, Height = 20, Style = ProgressBarStyle.Marquee };
            factHead = new Label { Left = 16, Top = 82, Width = 428, Height = 20, Text = "Did you know?",
                                   Font = new Font(Font, FontStyle.Bold), ForeColor = Color.FromArgb(0xD0, 0x50, 0x60) };
            factBody = new Label { Left = 16, Top = 104, Width = 428, Height = 80, Text = "" };
            Controls.Add(label); Controls.Add(bar); Controls.Add(factHead); Controls.Add(factBody);
            factTimer = new System.Windows.Forms.Timer { Interval = 7000 };
            factTimer.Tick += delegate { NextFact(); };
            if (Facts.All.Length == 0) { factHead.Visible = false; ClientSize = new Size(460, 84); }
            Shown += delegate { NextFact(); if (Facts.All.Length > 1) factTimer.Start(); };
            FormClosed += delegate { factTimer.Stop(); };
        }

        void NextFact()
        {
            int n = Facts.All.Length;
            if (n == 0) return;
            factIdx = factIdx < 0 ? rnd.Next(n) : (n > 1 ? (factIdx + 1 + rnd.Next(n - 1)) % n : 0);
            factBody.Text = Facts.All[factIdx];
        }

        void Ui(MethodInvoker a) { if (IsHandleCreated) BeginInvoke(a); }

        public void SetText(string s) { Ui(delegate { label.Text = s; }); }

        public void SetProgress(int pct)
        {
            Ui(delegate
            {
                if (pct < 0) { bar.Style = ProgressBarStyle.Marquee; Text = BaseTitle; }
                else
                {
                    int v = Math.Max(0, Math.Min(100, pct));
                    bar.Style = ProgressBarStyle.Continuous; bar.Value = v;
                    Text = BaseTitle + " - " + v + "%";
                }
            });
        }

        public void Fail(string msg)
        {
            Ui(delegate
            {
                if (WindowState == FormWindowState.Minimized) WindowState = FormWindowState.Normal;
                MessageBox.Show(this, msg, "Age of Wonders X update", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                Close();
            });
        }

        public void Done() { Ui(delegate { Close(); }); }
    }

    // "please close the editor" notice (2026-11-04), runs on its own UI thread so any waiting thread can open it;
    // closes itself when the wait ends.  OK only hides it - the update keeps waiting either way.
    internal class NoticeWindow : Form
    {
        readonly Label text;
        readonly ManualResetEvent ready = new ManualResetEvent(false);

        NoticeWindow(string msg)
        {
            Text = "Age of Wonders X update";
            FormBorderStyle = FormBorderStyle.FixedDialog;
            MaximizeBox = false; MinimizeBox = true; ShowInTaskbar = true;
            StartPosition = FormStartPosition.CenterScreen;
            TopMost = true;
            ClientSize = new Size(440, 170);
            BackColor = Color.FromArgb(20, 20, 20);
            ForeColor = Color.Gainsboro;
            try { Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath); } catch { }
            text = new Label { Left = 16, Top = 14, Width = 408, Height = 110, Text = msg };
            Button ok = new Button { Text = "OK", Left = 344, Top = 132, Width = 80, Height = 26,
                                     FlatStyle = FlatStyle.System, DialogResult = DialogResult.OK };
            ok.Click += delegate { Hide(); };
            Controls.Add(text); Controls.Add(ok);
            AcceptButton = ok;
            Shown += delegate { ready.Set(); TopMost = false; Activate(); };
        }

        public static NoticeWindow Open(string msg)
        {
            NoticeWindow w = null;
            ManualResetEvent made = new ManualResetEvent(false);
            Thread t = new Thread(delegate ()
            {
                try { Application.EnableVisualStyles(); } catch { }
                w = new NoticeWindow(msg);
                made.Set();
                Application.Run(w);
            });
            t.SetApartmentState(ApartmentState.STA);
            t.IsBackground = true;
            t.Start();
            made.WaitOne();
            w.ready.WaitOne(5000);
            return w;
        }

        public void SetMessage(string msg)
        {
            try { if (IsHandleCreated) BeginInvoke((MethodInvoker)delegate { if (text.Text != msg) text.Text = msg; }); } catch { }
        }

        public void CloseIt()
        {
            try { if (IsHandleCreated) BeginInvoke((MethodInvoker)delegate { Close(); }); } catch { }
        }
    }
}
