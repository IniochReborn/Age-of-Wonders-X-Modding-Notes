// AoW 2P sim.exe / AoW 3P sim.exe - starts 2 or 3 copies of AoWx.exe and arranges their windows.
// Copies 1 and 2 share the screen left/right; copy 3 (3P) is maximised (on a second monitor when there is one).
// The count comes from the launcher's own file name ("3P" -> 3, otherwise 2).  The game is taken from the launcher's folder.
// Build: build_aow_sim.cmd (csc from the .NET Framework that ships with Windows).
// Test without the game:  "AoW 3P sim.exe" --exe notepad.exe --report
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading;
using System.Windows.Forms;

static class AoWSim
{
    [StructLayout(LayoutKind.Sequential)] struct RECT { public int L, T, R, B; }
    delegate bool EnumProc(IntPtr h, IntPtr p);
    [DllImport("user32.dll")] static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] static extern bool EnumWindows(EnumProc f, IntPtr p);
    [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
    [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll")] static extern IntPtr GetWindow(IntPtr h, uint cmd);
    [DllImport("user32.dll")] static extern bool GetWindowRect(IntPtr h, out RECT r);
    [DllImport("user32.dll")] static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int w, int hh, uint flags);
    [DllImport("user32.dll")] static extern bool ShowWindow(IntPtr h, int cmd);
    [DllImport("user32.dll")] static extern bool IsZoomed(IntPtr h);
    [DllImport("dwmapi.dll")] static extern int DwmGetWindowAttribute(IntPtr h, int attr, out RECT r, int size);

    [DllImport("user32.dll")] static extern int GetWindowLong(IntPtr h, int idx);

    // largest visible captioned top-level window of the process (a Delphi main form is OWNED by the hidden application window)
    static IntPtr MainWindow(int pid)
    {
        IntPtr best = IntPtr.Zero; long bestArea = 0;
        EnumWindows(delegate(IntPtr h, IntPtr p)
        {
            uint wp; GetWindowThreadProcessId(h, out wp);
            if (wp != (uint)pid || !IsWindowVisible(h) || (GetWindowLong(h, -16) & 0x00C00000) != 0x00C00000) return true;
            RECT r; GetWindowRect(h, out r);
            long a = (long)(r.R - r.L) * (r.B - r.T);
            if (a > bestArea) { bestArea = a; best = h; }
            return true;
        }, IntPtr.Zero);
        return bestArea >= 200 * 150 ? best : IntPtr.Zero;
    }

    // move so that the VISIBLE frame fills `want` (Windows 10 windows carry an invisible resize border)
    static void Place(IntPtr h, System.Drawing.Rectangle want)
    {
        if (IsZoomed(h)) ShowWindow(h, 9);
        RECT w, f;
        GetWindowRect(h, out w);
        if (DwmGetWindowAttribute(h, 9, out f, 16) != 0) f = w;
        int dl = f.L - w.L, dt = f.T - w.T, dr = w.R - f.R, db = w.B - f.B;
        SetWindowPos(h, IntPtr.Zero, want.Left - dl, want.Top - dt, want.Width + dl + dr, want.Height + dt + db, 0x0014);
    }

    static bool Placed(IntPtr h, System.Drawing.Rectangle want)
    {
        RECT w, f;
        GetWindowRect(h, out w);
        if (DwmGetWindowAttribute(h, 9, out f, 16) != 0) f = w;
        return Math.Abs(f.L - want.Left) <= 2 && Math.Abs(f.T - want.Top) <= 2 && Math.Abs(f.R - want.Right) <= 2 && Math.Abs(f.B - want.Bottom) <= 2;
    }

    [STAThread]
    static int Main(string[] args)
    {
        SetProcessDPIAware();
        string dir = AppDomain.CurrentDomain.BaseDirectory;
        string self = Path.GetFileNameWithoutExtension(Application.ExecutablePath).ToUpperInvariant();
        int count = self.Contains("3P") ? 3 : 2;
        string exe = "AoWx.exe"; bool report = false;
        for (int i = 0; i < args.Length; i++)
        {
            if (args[i] == "--exe" && i + 1 < args.Length) exe = args[++i];
            else if (args[i] == "--report") report = true;
        }
        string path = Path.IsPathRooted(exe) || !File.Exists(Path.Combine(dir, exe)) ? exe : Path.Combine(dir, exe);
        if (exe == "AoWx.exe" && !File.Exists(path))
        {
            MessageBox.Show("AoWx.exe was not found next to this launcher:\n" + dir, "AoW sim", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }

        Screen prim = Screen.PrimaryScreen, other = null;
        foreach (Screen s in Screen.AllScreens) if (!s.Primary) { other = s; break; }
        System.Drawing.Rectangle wa = prim.WorkingArea;
        var slots = new List<System.Drawing.Rectangle>();
        slots.Add(new System.Drawing.Rectangle(wa.Left, wa.Top, wa.Width / 2, wa.Height));
        slots.Add(new System.Drawing.Rectangle(wa.Left + wa.Width / 2, wa.Top, wa.Width - wa.Width / 2, wa.Height));
        if (count == 3) slots.Add((other ?? prim).WorkingArea);          // copy 3: maximised on this screen

        var procs = new List<Process>();
        for (int i = 0; i < count; i++)
        {
            try
            {
                var psi = new ProcessStartInfo(path); psi.WorkingDirectory = dir; psi.UseShellExecute = false;
                procs.Add(Process.Start(psi));
            }
            catch (Exception e)
            {
                MessageBox.Show("Could not start " + path + "\n" + e.Message, "AoW sim", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return 1;
            }
            Thread.Sleep(700);
        }

        // arrange; keep correcting for a while because the game sizes its own window while it starts up
        var done = new bool[count]; var stable = new int[count];
        DateTime start = DateTime.Now, end = start.AddSeconds(60);
        while (DateTime.Now < end)
        {
            bool all = true;
            for (int i = 0; i < count; i++)
            {
                if (procs[i].HasExited) continue;
                IntPtr h = MainWindow(procs[i].Id);
                if (h == IntPtr.Zero) { all = false; continue; }
                if (i == 2)
                {
                    if (!IsZoomed(h)) { Place(h, slots[2]); ShowWindow(h, 3); stable[i] = 0; }
                    else stable[i]++;
                }
                else if (!Placed(h, slots[i])) { Place(h, slots[i]); stable[i] = 0; }
                else stable[i]++;
                done[i] = stable[i] >= 12;                               // unchanged for ~3 s
                if (!done[i]) all = false;
            }
            if (all && DateTime.Now > start.AddSeconds(20)) break;   // the game may re-maximise itself after its intro
            Thread.Sleep(250);
        }
        if (report)
        {
            string t = "";
            for (int i = 0; i < count; i++)
            {
                IntPtr h = procs[i].HasExited ? IntPtr.Zero : MainWindow(procs[i].Id);
                RECT f = new RECT(); if (h != IntPtr.Zero) DwmGetWindowAttribute(h, 9, out f, 16);
                t += string.Format("{0}: pid {1} want {2} got {3},{4},{5},{6} zoomed {7}\r\n", i + 1, procs[i].Id, slots[i], f.L, f.T, f.R, f.B, h != IntPtr.Zero && IsZoomed(h));
            }
            File.WriteAllText(Path.Combine(Path.GetTempPath(), "aow_sim_report.txt"), t);
        }
        return 0;
    }
}
