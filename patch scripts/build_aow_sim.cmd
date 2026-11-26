@echo off
rem Builds "AoW 2P sim.exe" and "AoW 3P sim.exe" into the game folder (one source; the count comes from the file name).
set CSC=%WINDIR%\Microsoft.NET\Framework\v4.0.30319\csc.exe
set SRC=%~dp0aow_sim_launcher.cs
"%CSC%" /nologo /target:winexe /platform:x86 /optimize+ /r:System.Windows.Forms.dll /r:System.Drawing.dll /out:"%~dp0..\AoW 2P sim.exe" "%SRC%" || exit /b 1
copy /y "%~dp0..\AoW 2P sim.exe" "%~dp0..\AoW 3P sim.exe" >nul
echo built
