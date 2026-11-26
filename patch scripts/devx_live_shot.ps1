param([string]$Out, [int]$Launch = 0, [int]$Wait = 12, [string]$Map = "_wtest.hsm")
Add-Type -AssemblyName System.Drawing, System.Windows.Forms
Add-Type @"
using System; using System.Runtime.InteropServices;
public class W32 {
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr dc, uint f);
  public struct RECT { public int L, T, R, B; }
}
"@
[W32]::SetProcessDPIAware() | Out-Null
$game = "C:\Users\<user>\Desktop\Age of Wonders X - Claude"
if ($Launch) {
  Start-Process -WindowStyle Minimized -FilePath "$game\AoWDevX.exe" -ArgumentList "`"$game\Scenario\Custom\$Map`"" -WorkingDirectory $game
  Start-Sleep -Seconds $Wait
}
$p = Get-Process AoWDevX -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
if (-not $p) { "no window"; exit 1 }
$p.MainWindowTitle
# no foreground steal: the window is captured with PrintWindow (the user may be working on the desktop)
$r = New-Object W32+RECT
[W32]::GetWindowRect($p.MainWindowHandle, [ref]$r) | Out-Null
$w = $r.R - $r.L; $h = $r.B - $r.T
"$($r.L) $($r.T) $w $h"
$bmp = New-Object System.Drawing.Bitmap $w, $h
$gr = [System.Drawing.Graphics]::FromImage($bmp)
$dc = $gr.GetHdc(); [W32]::PrintWindow($p.MainWindowHandle, $dc, 2) | Out-Null; $gr.ReleaseHdc($dc)
$bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
