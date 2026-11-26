; Age of Wonders X installer.
; Built by build_installer.py, which extracts the release zip to a staging dir
; and passes: /DAppVer=1.37.406 /DStagingDir=<dir> /DGameDir=<game root>
;             /DOutDir=<upload> /DOutName=AoWx_1_37_406_Setup
;
; Flow: AoWSetup-styled splash (art buttons, Start.wav) -> install type
; (vanilla/update, registry note) -> folder pick (blank default, Steam/GOG
; shortcuts in vanilla mode) -> [vanilla: separate copy vs overwrite+rename]
; -> permissions choice -> ready -> install (Arena SFX, "Did you know?"
; ticker from X\Documentation\installer fun facts.txt, 7s rotation) ->
; retired-file cleanup -> icacls + RUNASADMIN if chosen -> stability notice ->
; [vanilla: directplay .reg import by OS bitness + verified IPX/LAN popup] ->
; finish (Mana SFX, AoWx Discord link, single "Close and run AoWSetup." button).

#ifndef AppVer
  #define AppVer "1.37.0-dev"
#endif
#ifndef StagingDir
  #error Pass /DStagingDir=<extracted release zip> (use build_installer.py)
#endif
#ifndef GameDir
  #error Pass /DGameDir=<game root with Start.wav, Sfx, X\Documentation>
#endif
#ifndef OutDir
  #define OutDir "."
#endif
#ifndef OutName
  #define OutName "AoWx_Setup"
#endif
; build_installer.py passes a volume-reduced copy (the loop is too loud raw);
; fall back to the game's own file for direct ISCC compiles
#ifndef CharmWav
  #define CharmWav GameDir + "\Sfx\Attack\Charm.WAV"
#endif

[Setup]
AppName=Age of Wonders X
AppVersion={#AppVer}
AppPublisher=Inioch
; VERSIONINFO resource (file Properties > Details). The UAC elevation dialog's
; "Publisher" line is Authenticode-only: it reads a code-signing certificate
; and shows "Unknown" for any unsigned exe regardless of these fields.
VersionInfoCompany=Inioch
VersionInfoProductName=Age of Wonders X
VersionInfoDescription=Age of Wonders X Installer
#ifndef DevTest
VersionInfoVersion={#AppVer}
#endif
DefaultDirName=C:\Age of Wonders
AppendDefaultDirName=no
UsePreviousAppDir=no
DirExistsWarning=no
DisableWelcomePage=yes
DisableProgramGroupPage=yes
; DevTest builds skip elevation so the UI can be exercised without a UAC prompt
#ifdef DevTest
PrivilegesRequired=lowest
#else
PrivilegesRequired=admin
#endif
; AoWxUpdater runs silent updates with /CURRENTUSER when the game folder is user-writable (no UAC prompt);
; otherwise it starts the installer elevated ("runas")
PrivilegesRequiredOverridesAllowed=commandline
OutputDir={#OutDir}
OutputBaseFilename={#OutName}
SetupIconFile=assets\aowx_installer.ico
WizardImageFile=assets\wizard_side.bmp
WizardSmallImageFile=assets\wizard_small.bmp
; DevTest builds skip compression so big dummy stagings compile instantly
#ifdef DevTest
Compression=none
#else
Compression=lzma2/max
#endif
SolidCompression=yes
; aowx_dark.vsf = Inno's built-in dark style with blue accents recolored to
; red/burgundy (built by make_style.py)
WizardStyle=modern dark includetitlebar
WizardStyleFile=assets\aowx_dark.vsf
WizardBackColor=#141414
WizardImageBackColor=#141414
Uninstallable=no
CreateUninstallRegKey=no

[Files]
Source: "assets\setup_bg_aowx.bmp"; Flags: dontcopy
Source: "assets\btn_install.bmp"; Flags: dontcopy
Source: "assets\btn_install_hover.bmp"; Flags: dontcopy
Source: "assets\btn_install_down.bmp"; Flags: dontcopy
Source: "assets\btn_cancel.bmp"; Flags: dontcopy
Source: "assets\btn_cancel_hover.bmp"; Flags: dontcopy
Source: "assets\btn_cancel_down.bmp"; Flags: dontcopy
Source: "{#GameDir}\Start.wav"; Flags: dontcopy
Source: "{#GameDir}\Sfx\Events\NewEvent.WAV"; Flags: dontcopy
Source: "{#GameDir}\Sfx\Events\Mana.WAV"; Flags: dontcopy
Source: "{#CharmWav}"; Flags: dontcopy
Source: "..\manual_build\NeueHammerUnziale.otf"; Flags: dontcopy
Source: "{#GameDir}\X\Documentation\installer fun facts.txt"; Flags: dontcopy
; 1.37.434: the Error Log lives in X\Bug Report (AoWxLog.dll creates it and moves an old X\Error Log.txt there);
; no log file ships, and a player's existing log / bug-report saves are never touched
Source: "{#StagingDir}\*"; DestDir: "{code:GetInstallDir}"; Excludes: "Error Log.txt"; Flags: recursesubdirs createallsubdirs ignoreversion overwritereadonly

[InstallDelete]
; 1.37.422: these maps were renamed from "_s" to "'s" - remove the old copies so they don't show up twice
Type: files; Name: "{code:GetInstallDir}\Scenario\Custom\AoWx - Greed_s Paradise.hsm"
Type: files; Name: "{code:GetInstallDir}\Scenario\Custom\AoWx - Igor_s Folly.hsm"
Type: files; Name: "{code:GetInstallDir}\Scenario\Custom\AoWx - Oracle_s Eye.hsm"

[Run]
; 1.37.424: drop the old scheduled task with Setup's own (normally elevated) rights first.  A task once registered
; by an elevated process (e.g. game/AoWSetup run as administrator) is owned by Administrators and read-only for the
; player, so the user-level --register below failed with "Access is denied" and the task stayed stale for good.
; The updater now writes a security descriptor that keeps the player in control; this one-time delete heals old
; installs.  Waits (no nowait) so the re-register below starts after it.  Non-fatal if there is no task.
Filename: "{sys}\schtasks.exe"; Parameters: "/Delete /TN ""AoWx updater"" /F"; Flags: runhidden
; (re)register the AoWx updater's scheduled check (honours the Mode/Frequency set in AoWSetup); non-fatal
Filename: "{code:GetInstallDir}\AoWxUpdater.exe"; Parameters: "--register"; Flags: runhidden nowait skipifdoesntexist runasoriginaluser

[Dirs]
Name: "{code:GetInstallDir}\X\Save"

[Messages]
SetupAppTitle=Installer
SetupWindowTitle=Installer - Age of Wonders X (version {#AppVer})
SelectDirDesc=Where is your existing installation located?
SelectDirLabel3=Navigate to your existing game folder, then click Next.
SelectDirBrowseLabel=To continue, click Next. If you would like to select a different folder, click Browse.
ReadyLabel1=Installer is now ready to begin installing [name] on your computer.
PreparingDesc=Installer is preparing to install [name] on your computer.
InstallingLabel=Please wait while Installer installs [name] on your computer.
FinishedHeadingLabel=Completing the [name] Installer
ExitSetupTitle=Exit Installer
ExitSetupMessage=Installation is not complete. If you exit now, the game will not be installed.%n%nYou may run the Installer again at another time to complete the installation.%n%nExit Installer?
FinishedHeadingLabel=In the first days of the world...

[Code]
const
  DiscordURL = 'https://discord.gg/zn9yARHDFj';
  TargetName = 'Age of Wonders X';
  SteamDefault = 'C:\Program Files (x86)\Steam\steamapps\common\Age of Wonders';
  GogDefault = 'C:\GOG Games\Age of Wonders';
  SND_PLAY = $20003;  // SND_FILENAME or SND_ASYNC or SND_NODEFAULT
  SND_PLAY_LOOP = $2000B;  // ... or SND_LOOP

var
  TypePage: TInputOptionWizardPage;      // 0 = over vanilla, 1 = update existing AoWx
  VanillaPage: TInputOptionWizardPage;   // 0 = separate folder, 1 = overwrite vanilla
  PermsPage: TInputOptionWizardPage;     // 0 = yes (recommended), 1 = no
  GTargetDir: string;                    // resolved during PrepareToInstall
  ResultCodeDummy: Integer;
  GSplash: TSetupForm;
  GChoseInstall: Boolean;
  GDirBlanked: Boolean;
  DirHintLabel: TNewStaticText;
  SteamBtn, GogBtn: TNewButton;
  Facts: TArrayOfString;
  GFactIdx: Integer;
  GTimerID: LongWord;
  TickHead1, TickBody1, TickHead2, TickBody2: TNewStaticText;

function PlaySoundW(pszSound: String; hmod: Cardinal; fdwSound: Cardinal): Boolean;
  external 'PlaySoundW@winmm.dll stdcall';
function PlaySoundStopW(pszSound: LongWord; hmod: Cardinal; fdwSound: Cardinal): Boolean;
  external 'PlaySoundW@winmm.dll stdcall';
function SetTimer(hWnd: LongWord; nIDEvent: LongWord; uElapse: LongWord; lpTimerFunc: LongWord): LongWord;
  external 'SetTimer@user32.dll stdcall';
function KillTimer(hWnd: LongWord; nIDEvent: LongWord): Boolean;
  external 'KillTimer@user32.dll stdcall';
function GetTickCount: LongWord;
  external 'GetTickCount@kernel32.dll stdcall';
function GetCursorPos(var P: TPoint): Boolean;
  external 'GetCursorPos@user32.dll stdcall';
function GetAsyncKeyState(vKey: Integer): Integer;
  external 'GetAsyncKeyState@user32.dll stdcall';
function AddFontResourceExW(pszFilename: String; fl: Cardinal; pdv: Cardinal): Integer;
  external 'AddFontResourceExW@gdi32.dll stdcall';

// ---------- burgundy progress bar ----------
// The native gauge stays green no matter what (themed msctls_progress32
// ignores PBM_SETBARCOLOR), so hide it and draw our own: two stretched
// 1x1-bitmap images (dark track + burgundy fill) whose fill width follows
// ProgressGauge.Position via a 100ms timer.

var
  GBarBack, GBarFill: TBitmapImage;
  GBarTimer: LongWord;

procedure MakeSwatch(Img: TBitmapImage; Color: Integer);
begin
  Img.Bitmap.Width := 1;
  Img.Bitmap.Height := 1;
  Img.Bitmap.Canvas.Pixels[0, 0] := Color;
  Img.Stretch := True;
end;

procedure BarTimerProc(H: LongWord; Msg: LongWord; IdEvent: LongWord; Time: LongWord);
var
  G: TNewProgressBar;
  W: Integer;
begin
  if GBarFill = nil then
    exit;
  G := WizardForm.ProgressGauge;
  if G.Max <= G.Min then
    W := 0
  else
    W := ((GBarBack.Width - 2) * (G.Position - G.Min)) div (G.Max - G.Min);
  if W < 0 then
    W := 0;
  if W > GBarBack.Width - 2 then
    W := GBarBack.Width - 2;
  GBarFill.Width := W;
end;

procedure StyleProgressBar;
var
  G: TNewProgressBar;
begin
  G := WizardForm.ProgressGauge;
  if GBarBack = nil then begin
    GBarBack := TBitmapImage.Create(WizardForm);
    GBarBack.Parent := G.Parent;
    MakeSwatch(GBarBack, $202020);
    GBarBack.SetBounds(G.Left, G.Top, G.Width, G.Height);
    GBarFill := TBitmapImage.Create(WizardForm);
    GBarFill.Parent := G.Parent;
    MakeSwatch(GBarFill, $361EB0);       // #B01E36 theme burgundy (BGR)
    GBarFill.SetBounds(G.Left + 1, G.Top + 1, 0, G.Height - 2);
  end;
  G.Visible := False;
  if GBarTimer = 0 then
    GBarTimer := SetTimer(0, 0, 100, CreateCallback(@BarTimerProc));
end;

procedure StopProgressBar;
begin
  if GBarTimer <> 0 then begin
    KillTimer(0, GBarTimer);
    GBarTimer := 0;
  end;
end;

// "In the first days of the world..." in the game's uncial manuscript face,
// loaded process-private (FR_PRIVATE) from the embedded OTF
procedure UseUnzialeHeading;
begin
  try
    ExtractTemporaryFile('NeueHammerUnziale.otf');
    if AddFontResourceExW(ExpandConstant('{tmp}\NeueHammerUnziale.otf'), $10, 0) > 0 then begin
      WizardForm.FinishedHeadingLabel.Font.Name := 'Neue Hammer Unziale 1';
      WizardForm.FinishedHeadingLabel.Font.Style := [];
      WizardForm.FinishedHeadingLabel.Font.Size := 15;
      WizardForm.FinishedHeadingLabel.WordWrap := True;
      WizardForm.FinishedHeadingLabel.AdjustHeight;
    end;
  except
  end;
end;

// silent updates started by AoWxUpdater (/VERYSILENT /AOWXUPDATE=1): no splash, no popups, no sounds,
// "update existing installation" + no permission changes
function IsUpdateRun: Boolean;
begin
  Result := WizardSilent or (ExpandConstant('{param:AOWXUPDATE|0}') = '1');
end;

procedure PlayWav(const Name: string);
begin
  if IsUpdateRun then
    exit;
  try
    ExtractTemporaryFile(Name);
    PlaySoundW(ExpandConstant('{tmp}\' + Name), 0, SND_PLAY);
  except
  end;
end;

// ---------- looping install SFX ----------

var
  GInstallSfxOn: Boolean;

procedure StartInstallSfx;
begin
  if GInstallSfxOn or IsUpdateRun then
    exit;
  try
    ExtractTemporaryFile('Charm.WAV');
    PlaySoundW(ExpandConstant('{tmp}\Charm.WAV'), 0, SND_PLAY);
    GInstallSfxOn := True;
  except
  end;
end;

procedure StopInstallSfx;
begin
  if GInstallSfxOn then begin
    PlaySoundStopW(0, 0, 0);
    GInstallSfxOn := False;
  end;
end;

// ---------- popup dialogs (NewEvent SFX instead of Windows sounds) ----------

function AoWDialog(const Msg: string; Confirm: Boolean): Boolean;
var
  F: TSetupForm;
  L: TNewStaticText;
  B1, B2: TNewButton;
begin
  if IsUpdateRun then begin
    Result := True;     // silent update: informational popups are skipped, confirmations default to yes
    exit;
  end;
  PlayWav('NewEvent.WAV');
  F := CreateCustomForm(ScaleX(400), ScaleY(160), False, False);
  try
    F.Caption := 'Installer';
    F.BorderStyle := bsDialog;
    F.BorderIcons := [biSystemMenu];
    F.ClientWidth := ScaleX(400);

    L := TNewStaticText.Create(F);
    L.Parent := F;
    L.Left := ScaleX(16);
    L.Top := ScaleY(16);
    L.Width := ScaleX(368);
    L.AutoSize := False;
    L.WordWrap := True;
    L.Caption := Msg;
    L.AdjustHeight;

    F.ClientHeight := L.Top + L.Height + ScaleY(56);
    F.Position := poScreenCenter;

    B1 := TNewButton.Create(F);
    B1.Parent := F;
    B1.ModalResult := mrOk;
    B1.Default := True;
    if Confirm then begin
      B1.Caption := 'Yes';
      B1.SetBounds(F.ClientWidth - ScaleX(2*85 + 28), F.ClientHeight - ScaleY(35), ScaleX(85), ScaleY(25));
      B2 := TNewButton.Create(F);
      B2.Parent := F;
      B2.Caption := 'No';
      B2.ModalResult := mrCancel;
      B2.Cancel := True;
      B2.SetBounds(F.ClientWidth - ScaleX(85 + 16), F.ClientHeight - ScaleY(35), ScaleX(85), ScaleY(25));
    end else begin
      B1.Caption := 'OK';
      B1.Cancel := True;
      B1.SetBounds(F.ClientWidth - ScaleX(85 + 16), F.ClientHeight - ScaleY(35), ScaleX(85), ScaleY(25));
    end;

    Result := F.ShowModal = mrOk;
  finally
    F.Free;
  end;
end;

procedure AoWInfo(const Msg: string);
begin
  AoWDialog(Msg, False);
end;

function AoWConfirm(const Msg: string): Boolean;
begin
  Result := AoWDialog(Msg, True);
end;

function IsVanillaMode: Boolean;
begin
  Result := TypePage.Values[0];
end;

function IsSeparateFolder: Boolean;
begin
  Result := IsVanillaMode and VanillaPage.Values[0];
end;

function PermsWanted: Boolean;
begin
  Result := PermsPage.Values[0];
end;

// Planned target before any rename/copy has happened (for the Ready page).
function PlannedTargetDir: string;
var
  Sel: string;
begin
  Sel := RemoveBackslashUnlessRoot(WizardDirValue);
  if not IsVanillaMode then
    Result := Sel
  else if CompareText(ExtractFileName(Sel), TargetName) = 0 then
    Result := Sel
  else
    Result := AddBackslash(ExtractFileDir(Sel)) + TargetName;
end;

function GetInstallDir(Param: string): string;
begin
  if GTargetDir <> '' then
    Result := GTargetDir
  else
    Result := PlannedTargetDir;
end;

// ---------- "Did you know?" ticker ----------

procedure EnsureFacts;
var
  Raw: TArrayOfString;
  I, N: Integer;
begin
  if GetArrayLength(Facts) > 0 then
    exit;
  try
    ExtractTemporaryFile('installer fun facts.txt');
    LoadStringsFromFile(ExpandConstant('{tmp}\installer fun facts.txt'), Raw);
  except
    exit;
  end;
  N := 0;
  SetArrayLength(Facts, GetArrayLength(Raw));
  for I := 0 to GetArrayLength(Raw) - 1 do
    if Trim(Raw[I]) <> '' then begin
      Facts[N] := Trim(Raw[I]);
      N := N + 1;
    end;
  SetArrayLength(Facts, N);
  if N > 0 then
    GFactIdx := GetTickCount mod N;
end;

function PickFact: string;
var
  N: Integer;
begin
  Result := '';
  N := GetArrayLength(Facts);
  if N = 0 then
    exit;
  Result := Facts[GFactIdx mod N];
  if N > 1 then
    GFactIdx := (GFactIdx + 1 + Random(N - 1)) mod N;
end;

procedure ShowFact(const S: string);
begin
  if TickBody1 <> nil then
    TickBody1.Caption := S;
  if TickBody2 <> nil then
    TickBody2.Caption := S;
end;

procedure TickerProc(H: LongWord; Msg: LongWord; IdEvent: LongWord; Time: LongWord);
begin
  ShowFact(PickFact);
end;

procedure StartTicker;
begin
  EnsureFacts;
  if GetArrayLength(Facts) = 0 then
    exit;
  // already running (Preparing -> Installing page change): keep the current
  // fact and its 7s cadence instead of resetting mid-read
  if GTimerID <> 0 then
    exit;
  ShowFact(PickFact);
  GTimerID := SetTimer(0, 0, 7000, CreateCallback(@TickerProc));
end;

procedure StopTicker;
begin
  if GTimerID <> 0 then begin
    KillTimer(0, GTimerID);
    GTimerID := 0;
  end;
end;

procedure MakeTicker(Page: TNewNotebookPage; ATop: Integer; var Head, Body: TNewStaticText);
begin
  Head := TNewStaticText.Create(WizardForm);
  Head.Parent := Page;
  Head.Left := 0;
  Head.Top := ATop;
  Head.Caption := 'Did you know?';
  Head.Font.Style := [fsBold];

  Body := TNewStaticText.Create(WizardForm);
  Body.Parent := Page;
  Body.Left := 0;
  Body.Top := Head.Top + Head.Height + ScaleY(6);
  Body.Width := Page.ClientWidth;
  Body.AutoSize := False;
  Body.WordWrap := True;
  Body.Height := ScaleY(76);   // longest facts wrap to 4 lines
  Body.Caption := '';
end;

// ---------- splash ----------

procedure SplashInstallClick(Sender: TObject);
begin
  GChoseInstall := True;
  GSplash.Close;
end;

procedure SplashCancelClick(Sender: TObject);
begin
  GSplash.Close;
end;

// hover/pressed art for the splash buttons, driven by a 40ms cursor poll
// (TBitmapImage exposes no mouse-move/down events)
var
  GBtnL, GBtnR: TBitmapImage;
  GBtnLState, GBtnRState: Integer;     // 0 normal, 1 hover, 2 pressed
  GSplashTimer: LongWord;

procedure SetBtnState(Img: TBitmapImage; var Cur: Integer; NewState: Integer; const Base: string);
var
  Suffix: string;
begin
  if Cur = NewState then
    exit;
  Cur := NewState;
  case NewState of
    1: Suffix := '_hover';
    2: Suffix := '_down';
  else
    Suffix := '';
  end;
  Img.Bitmap.LoadFromFile(ExpandConstant('{tmp}\' + Base + Suffix + '.bmp'));
end;

function BtnStateFor(Img: TBitmapImage; X, Y: Integer; Down: Boolean): Integer;
begin
  Result := 0;
  if (X >= Img.Left) and (X < Img.Left + Img.Width)
     and (Y >= Img.Top) and (Y < Img.Top + Img.Height) then begin
    if Down then
      Result := 2
    else
      Result := 1;
  end;
end;

procedure SplashTimerProc(H: LongWord; Msg: LongWord; IdEvent: LongWord; Time: LongWord);
var
  P: TPoint;
  X, Y: Integer;
  Down: Boolean;
begin
  if GSplash = nil then
    exit;
  GetCursorPos(P);
  X := P.X - GSplash.Left;      // borderless form: client origin = form origin
  Y := P.Y - GSplash.Top;
  Down := GetAsyncKeyState(1) and $8000 <> 0;
  SetBtnState(GBtnL, GBtnLState, BtnStateFor(GBtnL, X, Y, Down), 'btn_install');
  SetBtnState(GBtnR, GBtnRState, BtnStateFor(GBtnR, X, Y, Down), 'btn_cancel');
end;

function ShowSplash: Boolean;
var
  Img: TBitmapImage;
  KbOk, KbCancel: TNewButton;
begin
  ExtractTemporaryFile('setup_bg_aowx.bmp');
  ExtractTemporaryFile('btn_install.bmp');
  ExtractTemporaryFile('btn_install_hover.bmp');
  ExtractTemporaryFile('btn_install_down.bmp');
  ExtractTemporaryFile('btn_cancel.bmp');
  ExtractTemporaryFile('btn_cancel_hover.bmp');
  ExtractTemporaryFile('btn_cancel_down.bmp');
  PlayWav('Start.wav');

  GSplash := CreateCustomForm(ScaleX(398), ScaleY(450), False, False);
  try
    GSplash.Caption := 'Installer - Age of Wonders X (version {#AppVer})';
    GSplash.BorderStyle := bsNone;
    GSplash.ClientWidth := ScaleX(398);
    GSplash.ClientHeight := ScaleY(450);
    GSplash.Position := poScreenCenter;

    Img := TBitmapImage.Create(GSplash);
    Img.Parent := GSplash;
    Img.Bitmap.LoadFromFile(ExpandConstant('{tmp}\setup_bg_aowx.bmp'));
    Img.Stretch := True;
    Img.SetBounds(0, 0, ScaleX(398), ScaleY(450));

    // clickable art buttons over the bottom bar (crops of the same art),
    // with hover/pressed variants swapped in by SplashTimerProc
    GBtnL := TBitmapImage.Create(GSplash);
    GBtnL.Parent := GSplash;
    GBtnL.Bitmap.LoadFromFile(ExpandConstant('{tmp}\btn_install.bmp'));
    GBtnL.Stretch := True;
    GBtnL.SetBounds(ScaleX(11), ScaleY(415), ScaleX(184), ScaleY(22));
    GBtnL.OnClick := @SplashInstallClick;
    GBtnLState := 0;

    GBtnR := TBitmapImage.Create(GSplash);
    GBtnR.Parent := GSplash;
    GBtnR.Bitmap.LoadFromFile(ExpandConstant('{tmp}\btn_cancel.bmp'));
    GBtnR.Stretch := True;
    GBtnR.SetBounds(ScaleX(201), ScaleY(415), ScaleX(185), ScaleY(22));
    GBtnR.OnClick := @SplashCancelClick;
    GBtnRState := 0;

    // offscreen buttons so Enter/Esc still work
    KbOk := TNewButton.Create(GSplash);
    KbOk.Parent := GSplash;
    KbOk.SetBounds(-ScaleX(300), 0, ScaleX(75), ScaleY(23));
    KbOk.ModalResult := mrOk;
    KbOk.Default := True;

    KbCancel := TNewButton.Create(GSplash);
    KbCancel.Parent := GSplash;
    KbCancel.SetBounds(-ScaleX(300), ScaleY(30), ScaleX(75), ScaleY(23));
    KbCancel.ModalResult := mrCancel;
    KbCancel.Cancel := True;

    GSplashTimer := SetTimer(0, 0, 40, CreateCallback(@SplashTimerProc));
    try
      Result := (GSplash.ShowModal = mrOk) or GChoseInstall;
    finally
      KillTimer(0, GSplashTimer);
      GSplashTimer := 0;
    end;
  finally
    GSplash.Free;
    GSplash := nil;
    GBtnL := nil;
    GBtnR := nil;
  end;
end;

function InitializeSetup: Boolean;
begin
#ifdef DevTest
  // /SKIPSPLASH=1 bypasses the art splash so automated UI tests can reach the
  // wizard without injecting real mouse clicks
  if ExpandConstant('{param:SKIPSPLASH|0}') = '1' then begin
    Result := True;
    exit;
  end;
#endif
  if IsUpdateRun then begin
    Result := True;
    exit;
  end;
  Result := ShowSplash();
end;

// ---------- wizard pages ----------

procedure SteamBtnClick(Sender: TObject);
begin
  WizardForm.DirEdit.Text := SteamDefault;
end;

// Browse starts at the user's Desktop (a popular install location) instead
// of the tree root, unless the edit already names an existing folder
procedure DirBrowseClick(Sender: TObject);
var
  Dir: string;
begin
  Dir := WizardForm.DirEdit.Text;
  if (Dir = '') or not DirExists(Dir) then
    Dir := ExpandConstant('{userdesktop}');
  if BrowseForFolder('Navigate to your game folder:', Dir, False) then
    WizardForm.DirEdit.Text := Dir;
end;

procedure GogBtnClick(Sender: TObject);
begin
  WizardForm.DirEdit.Text := GogDefault;
end;

procedure AddPageNote(Page: TInputOptionWizardPage; const NoteText: string);
var
  Note: TNewStaticText;
begin
  // indent items INSIDE the list so the radio circles are not clipped —
  // moving the whole control does not help because the circles are drawn at
  // the control's own client edge; with a note, shrink it to two rows and
  // put the note below it
  Page.CheckListBox.Offset := ScaleX(6);
  if NoteText = '' then
    exit;
  Page.CheckListBox.Height := ScaleY(54);

  Note := TNewStaticText.Create(WizardForm);
  Note.Parent := Page.Surface;
  Note.Left := 0;
  Note.Top := Page.CheckListBox.Top + Page.CheckListBox.Height + ScaleY(14);
  Note.Width := Page.SurfaceWidth;
  Note.AutoSize := False;
  Note.WordWrap := True;
  Note.Height := ScaleY(72);
  Note.Caption := NoteText;
end;

procedure InitializeWizard;
begin
  TypePage := CreateInputOptionPage(wpWelcome,
    'Installation Type', '',
    'Age of Wonders X installs into an existing game folder. Select which method to proceed with, then click Next.',
    True, False);
  TypePage.Add('Installing over vanilla Age of Wonders');
  TypePage.Add('Updating an existing Age of Wonders X installation');
  TypePage.Values[0] := True;
  AddPageNote(TypePage,
    'Note: Age of Wonders X will create its own registry entries, separate from vanilla ' +
    'Age of Wonders. As a result, installing Age of Wonders X will not interfere with any ' +
    'other vanilla or modified installations (ie: Ziggurat Mod), nor will any existing ' +
    'PBEM Wrapper settings be modified.');

  VanillaPage := CreateInputOptionPage(wpSelectDir,
    'Install Location', 'Keep your vanilla installation, or overwrite it?',
    'Either way, the resulting install folder will be named "' + TargetName + '".',
    True, False);
  VanillaPage.Add('Make a separate "' + TargetName + '" folder (your vanilla folder is copied and left untouched)');
  VanillaPage.Add('Overwrite my vanilla installation (the folder is renamed to "' + TargetName + '")');
  VanillaPage.Values[0] := True;
  AddPageNote(VanillaPage, '');

  PermsPage := CreateInputOptionPage(VanillaPage.ID,
    'Folder Permissions', 'Grant full permissions to the install folder?',
    'Some users can experience issues with Windows folder permissions preventing the game ' +
    'from creating new save files or campaign scenarios, most commonly on Windows 11. ' +
    'To alleviate these problems, the installer can force read/write access to the AoWx ' +
    'installation folder (only) and preconfigure game executables to "Run as Administrator". ' +
    'Choosing Yes is highly recommended.',
    True, False);
  PermsPage.Add('Yes, grant full permissions (highly recommended)');
  PermsPage.Add('No, skip this step');
  PermsPage.Values[0] := True;
  AddPageNote(PermsPage,
    'Note: This can still be done manually at a later time if you decline and encounter ' +
    'issues running the game.');

  WizardForm.DirBrowseButton.OnClick := @DirBrowseClick;

  if IsUpdateRun then begin
    TypePage.Values[1] := True;    // updating an existing AoWx installation
    PermsPage.Values[1] := True;   // leave folder permissions / run-as-admin flags as they are
  end;

  // Steam/GOG shortcuts on the folder page (vanilla mode only)
  DirHintLabel := TNewStaticText.Create(WizardForm);
  DirHintLabel.Parent := WizardForm.SelectDirPage;
  DirHintLabel.Left := 0;
  DirHintLabel.Top := WizardForm.DirEdit.Top + WizardForm.DirEdit.Height + ScaleY(24);
  DirHintLabel.Caption := 'Common vanilla install locations:';
  DirHintLabel.Visible := False;

  SteamBtn := TNewButton.Create(WizardForm);
  SteamBtn.Parent := WizardForm.SelectDirPage;
  SteamBtn.SetBounds(0, DirHintLabel.Top + DirHintLabel.Height + ScaleY(8), ScaleX(110), ScaleY(24));
  SteamBtn.Caption := 'Steam default';
  SteamBtn.OnClick := @SteamBtnClick;
  SteamBtn.Visible := False;

  GogBtn := TNewButton.Create(WizardForm);
  GogBtn.Parent := WizardForm.SelectDirPage;
  GogBtn.SetBounds(SteamBtn.Left + SteamBtn.Width + ScaleX(12), SteamBtn.Top, ScaleX(110), ScaleY(24));
  GogBtn.Caption := 'GOG default';
  GogBtn.OnClick := @GogBtnClick;
  GogBtn.Visible := False;

  // "Did you know?" ticker on the preparing and installing pages — SAME top
  // on both (the pages share one coordinate space) so the text holds still
  // through the Preparing -> Installing transition
  MakeTicker(WizardForm.PreparingPage,
    WizardForm.ProgressGauge.Top + WizardForm.ProgressGauge.Height + ScaleY(30),
    TickHead1, TickBody1);
  MakeTicker(WizardForm.InstallingPage,
    WizardForm.ProgressGauge.Top + WizardForm.ProgressGauge.Height + ScaleY(30),
    TickHead2, TickBody2);
end;

procedure OpenDiscord(Sender: TObject);
begin
  ShellExecAsOriginalUser('open', DiscordURL, '', '', SW_SHOWNORMAL, ewNoWait, ResultCodeDummy);
end;

procedure CurPageChanged(CurPageID: Integer);
var
  Link, Excl: TNewStaticText;
begin
  if CurPageID = wpSelectDir then begin
    if IsVanillaMode then
      WizardForm.SelectDirLabel.Caption :=
        'Navigate to your existing vanilla Age of Wonders folder, then click Next.'
    else
      WizardForm.SelectDirLabel.Caption :=
        'Navigate to your existing Age of Wonders X folder, then click Next.';
    DirHintLabel.Visible := IsVanillaMode;
    SteamBtn.Visible := IsVanillaMode;
    GogBtn.Visible := IsVanillaMode;
    if not GDirBlanked then begin
      if ExpandConstant('{param:DIR|}') = '' then
        WizardForm.DirEdit.Text := '';
      GDirBlanked := True;
    end;
  end;

  if (CurPageID = wpPreparing) or (CurPageID = wpInstalling) then
    StartTicker;

  if CurPageID = wpInstalling then begin
    StyleProgressBar;
    StartInstallSfx;
  end;

  if CurPageID = wpFinished then begin
    StopTicker;
    StopInstallSfx;
    StopProgressBar;
    PlayWav('Mana.WAV');

    UseUnzialeHeading;
    WizardForm.FinishedLabel.Top :=
      WizardForm.FinishedHeadingLabel.Top + WizardForm.FinishedHeadingLabel.Height + ScaleY(12);
    WizardForm.FinishedLabel.WordWrap := True;
    WizardForm.FinishedLabel.Caption :=
      'Age of Wonders X has been successfully installed.' + #13#10#13#10 +
      'Looking to play multiplayer? Join an active community on the';
    WizardForm.FinishedLabel.AdjustHeight;

    Link := TNewStaticText.Create(WizardForm);
    Link.Parent := WizardForm.FinishedPage;
    Link.Caption := 'AoWx Discord';
    Link.Left := WizardForm.FinishedLabel.Left;
    Link.Top := WizardForm.FinishedLabel.Top + WizardForm.FinishedLabel.Height + ScaleY(2);
    Link.Font.Color := $FFA64D;   // light blue, readable on the dark style
    Link.Font.Style := [fsUnderline];
    Link.Cursor := crHand;
    Link.OnClick := @OpenDiscord;

    Excl := TNewStaticText.Create(WizardForm);
    Excl.Parent := WizardForm.FinishedPage;
    Excl.Caption := '!';
    Excl.Left := Link.Left + Link.Width;
    Excl.Top := Link.Top;

    WizardForm.NextButton.Caption := 'Close and run AoWSetup.';
    WizardForm.NextButton.Width := ScaleX(150);
    WizardForm.NextButton.Left :=
      WizardForm.CancelButton.Left + WizardForm.CancelButton.Width - WizardForm.NextButton.Width;
    WizardForm.CancelButton.Visible := False;
  end;
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := (PageID = VanillaPage.ID) and not IsVanillaMode;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Sel: string;
begin
  Result := True;

  if CurPageID = wpSelectDir then begin
    Sel := RemoveBackslashUnlessRoot(WizardDirValue);
    if not DirExists(Sel) then begin
      AoWInfo('The selected folder does not exist. Please select your existing game folder.');
      Result := False;
      exit;
    end;
    if ExtractFileDir(Sel) = Sel then begin  // drive root
      AoWInfo('Please select a game folder, not a drive root.');
      Result := False;
      exit;
    end;
    if IsVanillaMode then begin
      if not FileExists(Sel + '\AoW.exe') then
        Result := AoWConfirm('This folder does not appear to contain Age of Wonders (AoW.exe was not found).'
          + #13#10#13#10 + 'Continue anyway?');
    end else begin
      if not FileExists(Sel + '\AoWx.exe') then
        Result := AoWConfirm('This folder does not appear to contain Age of Wonders X (AoWx.exe was not found).'
          + #13#10#13#10 + 'Continue anyway?');
    end;
  end;

  if CurPageID = PermsPage.ID then begin
    if not PermsWanted then
      Result := AoWConfirm('Are you sure? Granting full permissions is highly recommended, '
        + 'however can be done manually at a later time.'
        + #13#10#13#10 + 'Skip granting full permissions?');
  end;

  if (CurPageID = wpFinished) and not IsUpdateRun then begin   // silent updater runs must not launch AoWSetup
    Exec(GetInstallDir('') + '\AoWSetup.exe', '', GetInstallDir(''), SW_SHOWNORMAL, ewNoWait, ResultCodeDummy);
  end;
end;

function UpdateReadyMemo(Space, NewLine, MemoUserInfoInfo, MemoDirInfo, MemoTypeInfo,
  MemoComponentsInfo, MemoGroupInfo, MemoTasksInfo: string): string;
begin
  Result := '';
  if IsVanillaMode then begin
    Result := Result + 'Install type:' + NewLine + Space + 'Over vanilla Age of Wonders' + NewLine + NewLine;
    Result := Result + 'Vanilla folder:' + NewLine + Space + RemoveBackslashUnlessRoot(WizardDirValue) + NewLine + NewLine;
    if IsSeparateFolder then
      Result := Result + 'Vanilla handling:' + NewLine + Space + 'Copied to a separate folder (vanilla untouched)' + NewLine + NewLine
    else
      Result := Result + 'Vanilla handling:' + NewLine + Space + 'Overwritten (folder renamed)' + NewLine + NewLine;
  end else begin
    Result := Result + 'Install type:' + NewLine + Space + 'Update existing Age of Wonders X' + NewLine + NewLine;
  end;
  Result := Result + 'Install folder:' + NewLine + Space + PlannedTargetDir + NewLine + NewLine;
  if PermsWanted then
    Result := Result + 'Permissions:' + NewLine + Space + 'Grant full permissions and run-as-administrator' + NewLine
  else
    Result := Result + 'Permissions:' + NewLine + Space + 'Not changed' + NewLine;
end;

// ---------- install ----------

procedure DirectoryCopy(const SourcePath, DestPath: string);
var
  FindRec: TFindRec;
  S, D: string;
begin
  if FindFirst(SourcePath + '\*', FindRec) then begin
    try
      repeat
        if (FindRec.Name <> '.') and (FindRec.Name <> '..') then begin
          S := SourcePath + '\' + FindRec.Name;
          D := DestPath + '\' + FindRec.Name;
          if FindRec.Attributes and FILE_ATTRIBUTE_DIRECTORY <> 0 then begin
            if not DirExists(D) then
              CreateDir(D);
            DirectoryCopy(S, D);
          end else
            CopyFile(S, D, False);
        end;
      until not FindNext(FindRec);
    finally
      FindClose(FindRec);
    end;
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): string;
var
  Sel: string;
begin
  Result := '';
  Sel := RemoveBackslashUnlessRoot(WizardDirValue);
  GTargetDir := PlannedTargetDir;

  if IsVanillaMode and IsSeparateFolder and (CompareText(GTargetDir, Sel) <> 0) then begin
    WizardForm.PreparingLabel.Caption := 'Copying your vanilla installation (this can take a minute)...';
    WizardForm.PreparingLabel.Update;
    if not DirExists(GTargetDir) then
      if not CreateDir(GTargetDir) then begin
        Result := 'Could not create folder: ' + GTargetDir;
        exit;
      end;
    DirectoryCopy(Sel, GTargetDir);
  end;

  if IsVanillaMode and not IsSeparateFolder and (CompareText(GTargetDir, Sel) <> 0) then begin
    if DirExists(GTargetDir) then begin
      AoWInfo('A folder named "' + TargetName + '" already exists next to your vanilla folder. '
        + 'The Installer will install into that existing folder instead of renaming your vanilla folder.');
    end else if not RenameFile(Sel, GTargetDir) then begin
      AoWInfo('The Installer could not rename your folder to "' + TargetName + '" (it may be in use). '
        + 'Installing into the original folder instead: ' + Sel);
      GTargetDir := Sel;
    end;
  end;

  // retired in 1.37.406: the external launcher and hotkey script are now built in
  DeleteFile(GTargetDir + '\Age of Wonders X - Launcher.exe');
  DeleteFile(GTargetDir + '\AoWx - Scroll of Slickness.ahk');
  DeleteFile(GTargetDir + '\AoWx - Scroll of Slickness.exe');

  // modding tools relocated into X\Modding: remove any stale copies left in the
  // main folder so only the X\Modding versions remain (both the old dot-prefixed
  // names and any unprefixed copies)
  DeleteFile(GTargetDir + '\.AoWxGen.exe');
  DeleteFile(GTargetDir + '\.AoWxBard.exe');
  DeleteFile(GTargetDir + '\.AoWxImg.exe');
  DeleteFile(GTargetDir + '\.AoWxInk.exe');
  DeleteFile(GTargetDir + '\.AoWxQuest.exe');
  DeleteFile(GTargetDir + '\AoWxGen.exe');
  DeleteFile(GTargetDir + '\AoWxBard.exe');
  DeleteFile(GTargetDir + '\AoWxImg.exe');
  DeleteFile(GTargetDir + '\AoWxInk.exe');
  DeleteFile(GTargetDir + '\AoWxQuest.exe');
end;

procedure MarkExesRunAsAdmin(const Dir: string; RootKey: Integer);
var
  FindRec: TFindRec;
  P: string;
begin
  if FindFirst(Dir + '\*', FindRec) then begin
    try
      repeat
        if (FindRec.Name <> '.') and (FindRec.Name <> '..') then begin
          P := Dir + '\' + FindRec.Name;
          if FindRec.Attributes and FILE_ATTRIBUTE_DIRECTORY <> 0 then
            MarkExesRunAsAdmin(P, RootKey)
          else if CompareText(ExtractFileExt(FindRec.Name), '.exe') = 0 then
            RegWriteStringValue(RootKey,
              'SOFTWARE\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers',
              P, '~ RUNASADMIN');
        end;
      until not FindNext(FindRec);
    finally
      FindClose(FindRec);
    end;
  end;
end;

function DetectWin64: Boolean;
var
  Determined: Boolean;
begin
  Determined := True;
  Result := False;
  try
    Result := IsWin64;
  except
    Determined := False;
  end;
  if not Determined then
    Result := AoWConfirm('The Installer could not determine whether your Windows is 32-bit or 64-bit.'
      + #13#10#13#10 + 'Is your Windows 64-bit?'
      + #13#10 + 'If unsure, modern operating systems are almost always 64-bit.');
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  RootKey: Integer;
  RegName, PathVal: string;
begin
  if CurStep = ssPostInstall then begin
    StopTicker;
    StopInstallSfx;

    if PermsWanted then begin
      Exec(ExpandConstant('{sys}\icacls.exe'),
        '"' + GTargetDir + '" /grant *S-1-1-0:(OI)(CI)F /T /C /Q',
        '', SW_HIDE, ewWaitUntilTerminated, ResultCodeDummy);
      if IsWin64 then
        RootKey := HKLM64
      else
        RootKey := HKLM;
      MarkExesRunAsAdmin(GTargetDir, RootKey);
    end;

    AoWInfo('Age of Wonders (Vanilla) is known to have stability issues on modern operating systems. '
      + 'These issues are fixed in Age of Wonders X. As such, downloading the popular '
      + '"MapViewer/Showscene Patch" is not required.');

    if IsVanillaMode then begin
      if DetectWin64 then
        RegName := GTargetDir + '\directplay-win64.reg'
      else
        RegName := GTargetDir + '\directplay-win32.reg';
      Exec(ExpandConstant('{win}\regedit.exe'), '/s "' + RegName + '"',
        '', SW_HIDE, ewWaitUntilTerminated, ResultCodeDummy);
      // verify the import actually landed (32-bit view = Wow6432Node on x64,
      // which is exactly where directplay-win64.reg writes)
      if RegQueryStringValue(HKLM,
           'SOFTWARE\Microsoft\DirectPlay\Service Providers\IPX Connection For DirectPlay',
           'Path', PathVal) and (CompareText(PathVal, 'dpwsockx.dll') = 0) then
        AoWInfo('IPX/LAN functionality has been enabled, along with various fixes. '
          + 'Live multiplayer games can now be played with optimized stability.');
    end;
  end;
end;
