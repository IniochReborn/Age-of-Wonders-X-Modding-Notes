#!/usr/bin/env python3
"""
Drag-and-drop launcher for wav2it — this is what gets compiled into the standalone
"Convert song to IT.exe" (custom AoWx+CD icon). Drop WAV/MP3 files onto the EXE and
each becomes an in-game .IT music track using our tuned preset, saved next to the EXE
(i.e. in the Songs folder). Self-contained: needs no Python install (WAV always works;
MP3 still needs ffmpeg on the machine).
"""
import sys, os
import wav2it

# The tuned preset (matches the vanilla-loudness recipe).
PRESET = dict(rate=22050, bits=16, mv=128, target_db=-12.0, bass_db=6.0, nchan=2, short=True)

def base_dir():
    """Where the .IT output goes. The EXE historically lived IN Songs (output =
    its own folder); now that it sits in the game root as .AoWxBard.exe, prefer
    a Songs subfolder next to it when one exists."""
    here = (os.path.dirname(sys.executable) if getattr(sys, 'frozen', False)
            else os.path.dirname(os.path.abspath(__file__)))
    songs = os.path.join(here, 'Songs')
    return songs if os.path.isdir(songs) else here

def _set_console_icon():
    """Stamp the console window (title bar + taskbar) with the exe's own icon —
    bypasses Windows' icon cache, which can serve a stale image after rebuilds."""
    if not getattr(sys, 'frozen', False) or os.name != 'nt':
        return
    try:
        import ctypes
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if not hwnd:
            return
        hicon = ctypes.windll.shell32.ExtractIconW(0, sys.executable, 0)
        if hicon and hicon > 1:
            ctypes.windll.user32.SendMessageW(hwnd, 0x80, 0, hicon)
            ctypes.windll.user32.SendMessageW(hwnd, 0x80, 1, hicon)
    except Exception:
        pass


def main():
    _set_console_icon()
    files = [a for a in sys.argv[1:] if a.strip()]
    out = base_dir()
    print("=" * 60)
    print(" Age of Wonders X  -  WAV/MP3  ->  IT  Music Converter")
    print("=" * 60)
    if not files:
        print("\nDrag one or more WAV or MP3 files onto this program to convert them.")
        print("New .IT tracks are saved here:\n  " + out)
    else:
        ok = 0
        for f in files:
            name = os.path.basename(f)
            try:
                p, n, gdb = wav2it.convert(f, out, PRESET['rate'], PRESET['bits'], PRESET['mv'],
                                           PRESET['target_db'], PRESET['bass_db'],
                                           PRESET['nchan'], PRESET['short'])
                print(f"  OK   {name}  ->  {os.path.basename(p)}   ({n/1048576:.1f} MB)")
                ok += 1
            except Exception as e:
                print(f"  FAIL {name}:  {e}")
        print(f"\nFinished {ok}/{len(files)} file(s). Restart the game to hear new tracks.")
    try:
        input("\nPress Enter to close...")
    except EOFError:
        pass

if __name__ == '__main__':
    main()
