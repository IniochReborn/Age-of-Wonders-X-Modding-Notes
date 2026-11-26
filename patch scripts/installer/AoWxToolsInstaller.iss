; AoWx Modding Tools installer.
; Built by build_tools_installer.py, which stages the five tool exes and
; passes: /DAppVer=1.01.0002 /DStagingDir=<dir> /DGameDir=<game root>
;         /DOutDir=<upload> /DOutName=<output base name>
;
; A trimmed derivative of AoWxInstaller.iss: same AoWSetup-styled splash,
; dark style, burgundy progress bar, install SFX and "Did you know?" ticker,
; but a single folder page ("where is Age of Wonders X installed?") prefilled
; from the mod's registry tree. Installs AoWxBard/Gen/Img/Ink/Quest into
; <game>\X\Modding and removes stale copies from the main folder.

#ifndef AppVer
  #define AppVer "1.0-dev"
#endif
#ifndef StagingDir
  #error Pass /DStagingDir=<dir with the five tool exes> (use build_tools_installer.py)
#endif
#ifndef GameDir
  #error Pass /DGameDir=<game root with Start.wav, Sfx, X\Documentation>
#endif
#ifndef OutDir
  #define OutDir "."
#endif
#ifndef OutName
  #define OutName "AoWxTools_Setup"
#endif
#ifndef CharmWav
  #define CharmWav GameDir + "\Sfx\Attack\Charm.WAV"
#endif

[Setup]
AppName=AoWx Modding Tools
AppVersion={#AppVer}
AppPublisher=Inioch
VersionInfoCompany=Inioch
VersionInfoProductName=AoWx Modding Tools
VersionInfoDescription=AoWx Modding Tools Installer
DefaultDirName=C:\Age of Wonders X
AppendDefaultDirName=no
UsePreviousAppDir=no
DirExistsWarning=no
DisableWelcomePage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=admin
OutputDir={#OutDir}
OutputBaseFilename={#OutName}
SetupIconFile=assets\aowx_installer.ico
WizardImageFile=assets\wizard_side.bmp
WizardSmallImageFile=assets\wizard_small.bmp
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern dark includetitlebar
WizardStyleFile=assets\aowx_dark.vsf
WizardBackColor=#141414
WizardImageBackColor=#141414
Uninstallable=no
CreateUninstallRegKey=no

[Files]
Source: "assets\setup_bg_aowxtools.bmp"; Flags: dontcopy
Source: "assets\btn_install_tools.bmp"; Flags: dontcopy
Source: "assets\btn_install_tools_hover.bmp"; Flags: dontcopy
Source: "assets\btn_install_tools_down.bmp"; Flags: dontcopy
Source: "assets\btn_cancel.bmp"; Flags: dontcopy
Source: "assets\btn_cancel_hover.bmp"; Flags: dontcopy
Source: "assets\btn_cancel_down.bmp"; Flags: dontcopy
Source: "{#GameDir}\Start.wav"; Flags: dontcopy
Source: "{#GameDir}\Sfx\Events\NewEvent.WAV"; Flags: dontcopy
Source: "{#GameDir}\Sfx\Events\Mana.WAV"; Flags: dontcopy
Source: "{#CharmWav}"; Flags: dontcopy
Source: "..\manual_build\NeueHammerUnziale.otf"; Flags: dontcopy
Source: "{#GameDir}\X\Documentation\installer fun facts.txt"; Flags: dontcopy
Source: "{#StagingDir}\*.exe"; DestDir: "{code:GetInstallDir}\X\Modding"; Flags: ignoreversion overwritereadonly

[Dirs]
Name: "{code:GetInstallDir}\X\Modding"

[Messages]
SetupAppTitle=Installer
SetupWindowTitle=Installer - AoWx Modding Tools (version {#AppVer})
SelectDirDesc=Where is your Age of Wonders X installation located?
SelectDirLabel3=Navigate to your Age of Wonders X game folder, then click Next.
SelectDirBrowseLabel=To continue, click Next. If you would like to select a different folder, click Browse.
ReadyLabel1=Installer is now ready to begin installing [name] on your computer.
PreparingDesc=Installer is preparing to install [name] on your computer.
InstallingLabel=Please wait while Installer installs [name] on your computer.
ExitSetupTitle=Exit Installer
ExitSetupMessage=Installation is not complete. If you exit now, the modding tools will not be installed.%n%nYou may run the Installer again at another time to complete the installation.%n%nExit Installer?
FinishedHeadingLabel=In the first days of the world...

[Code]
const
  DiscordURL = 'https://discord.gg/zn9yARHDFj';
  RegRootKey = 'Software\Triumph Studios\Age of Wonders X\General';
  SND_PLAY = $20003;  // SND_FILENAME or SND_ASYNC or SND_NODEFAULT
  SND_PLAY_LOOP = $2000B;  // ... or SND_LOOP

var
  GTargetDir: string;
  ResultCodeDummy: Integer;
  GSplash: TSetupForm;
  GChoseInstall: Boolean;
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

procedure PlayWav(const Name: string);
begin
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
  if GInstallSfxOn then
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

function GetInstallDir(Param: string): string;
begin
  if GTargetDir <> '' then
    Result := GTargetDir
  else
    Result := RemoveBackslashUnlessRoot(WizardDirValue);
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
  Body.Height := ScaleY(76);
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
  X := P.X - GSplash.Left;
  Y := P.Y - GSplash.Top;
  Down := GetAsyncKeyState(1) and $8000 <> 0;
  SetBtnState(GBtnL, GBtnLState, BtnStateFor(GBtnL, X, Y, Down), 'btn_install_tools');
  SetBtnState(GBtnR, GBtnRState, BtnStateFor(GBtnR, X, Y, Down), 'btn_cancel');
end;

function ShowSplash: Boolean;
var
  Img: TBitmapImage;
  KbOk, KbCancel: TNewButton;
begin
  ExtractTemporaryFile('setup_bg_aowxtools.bmp');
  ExtractTemporaryFile('btn_install_tools.bmp');
  ExtractTemporaryFile('btn_install_tools_hover.bmp');
  ExtractTemporaryFile('btn_install_tools_down.bmp');
  ExtractTemporaryFile('btn_cancel.bmp');
  ExtractTemporaryFile('btn_cancel_hover.bmp');
  ExtractTemporaryFile('btn_cancel_down.bmp');
  PlayWav('Start.wav');

  GSplash := CreateCustomForm(ScaleX(398), ScaleY(450), False, False);
  try
    GSplash.Caption := 'Installer - AoWx Modding Tools (version {#AppVer})';
    GSplash.BorderStyle := bsNone;
    GSplash.ClientWidth := ScaleX(398);
    GSplash.ClientHeight := ScaleY(450);
    GSplash.Position := poScreenCenter;

    Img := TBitmapImage.Create(GSplash);
    Img.Parent := GSplash;
    Img.Bitmap.LoadFromFile(ExpandConstant('{tmp}\setup_bg_aowxtools.bmp'));
    Img.Stretch := True;
    Img.SetBounds(0, 0, ScaleX(398), ScaleY(450));

    GBtnL := TBitmapImage.Create(GSplash);
    GBtnL.Parent := GSplash;
    GBtnL.Bitmap.LoadFromFile(ExpandConstant('{tmp}\btn_install_tools.bmp'));
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
  Result := ShowSplash();
end;

// ---------- wizard pages ----------

procedure DirBrowseClick(Sender: TObject);
var
  Dir: string;
begin
  Dir := WizardForm.DirEdit.Text;
  if (Dir = '') or not DirExists(Dir) then
    Dir := ExpandConstant('{userdesktop}');
  if BrowseForFolder('Navigate to your Age of Wonders X folder:', Dir, False) then
    WizardForm.DirEdit.Text := Dir;
end;

procedure InitializeWizard;
var
  RootDir: string;
  DirNote: TNewStaticText;
begin
  WizardForm.DirBrowseButton.OnClick := @DirBrowseClick;

  // vanilla-compatibility note below the folder selection area
  DirNote := TNewStaticText.Create(WizardForm);
  DirNote.Parent := WizardForm.SelectDirPage;
  DirNote.Left := WizardForm.DirEdit.Left;
  DirNote.Top := WizardForm.DirEdit.Top + WizardForm.DirEdit.Height + ScaleY(14);
  DirNote.Width := WizardForm.SelectDirPage.Width - 2 * WizardForm.DirEdit.Left;
  DirNote.AutoSize := False;
  DirNote.WordWrap := True;
  DirNote.Height := ScaleY(56);
  DirNote.Caption :=
    'Note: While these modding tools are intended to be used with AoWx, they should ' +
    'generally be compatible with vanilla AoW. Please report any bugs as testing with ' +
    'vanilla was limited.';

  // prefill from the mod's own registry tree when AoWx has run on this machine
  if RegQueryStringValue(HKCU, RegRootKey, 'Root Directory', RootDir)
     and DirExists(RootDir) then
    WizardForm.DirEdit.Text := RemoveBackslashUnlessRoot(RootDir)
  else
    WizardForm.DirEdit.Text := '';

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
  Tail, Link, Excl: TNewStaticText;
begin
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
      'The AoWx modding tools have been successfully installed.' + #13#10#13#10 +
      'They are available from AoWSetup''s Modding button.';
    WizardForm.FinishedLabel.AdjustHeight;

    { last sentence as its own single-line label so the link continues
      INLINE on the same line instead of breaking onto a line of its own }
    Tail := TNewStaticText.Create(WizardForm);
    Tail.Parent := WizardForm.FinishedPage;
    Tail.Caption := 'Questions or creations to share? Join the ';
    Tail.Left := WizardForm.FinishedLabel.Left;
    Tail.Top := WizardForm.FinishedLabel.Top + WizardForm.FinishedLabel.Height + ScaleY(10);

    Link := TNewStaticText.Create(WizardForm);
    Link.Parent := WizardForm.FinishedPage;
    Link.Caption := 'AoWx Discord';
    Link.Left := Tail.Left + Tail.Width;
    Link.Top := Tail.Top;
    Link.Font.Color := $FFA64D;
    Link.Font.Style := [fsUnderline];
    Link.Cursor := crHand;
    Link.OnClick := @OpenDiscord;

    Excl := TNewStaticText.Create(WizardForm);
    Excl.Parent := WizardForm.FinishedPage;
    Excl.Caption := '!';
    Excl.Left := Link.Left + Link.Width;
    Excl.Top := Link.Top;

    WizardForm.NextButton.Caption := 'Close.';
    WizardForm.CancelButton.Visible := False;
  end;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Sel: string;
begin
  Result := True;

  if CurPageID = wpSelectDir then begin
    Sel := RemoveBackslashUnlessRoot(WizardDirValue);
    if not DirExists(Sel) then begin
      AoWInfo('The selected folder does not exist. Please select your Age of Wonders X folder.');
      Result := False;
      exit;
    end;
    if ExtractFileDir(Sel) = Sel then begin  // drive root
      AoWInfo('Please select a game folder, not a drive root.');
      Result := False;
      exit;
    end;
    if not FileExists(Sel + '\AoWx.exe') then
      Result := AoWConfirm('This folder does not appear to contain Age of Wonders X (AoWx.exe was not found).'
        + #13#10#13#10 + 'Do you still wish to continue?');
  end;
end;

function UpdateReadyMemo(Space, NewLine, MemoUserInfoInfo, MemoDirInfo, MemoTypeInfo,
  MemoComponentsInfo, MemoGroupInfo, MemoTasksInfo: string): string;
begin
  Result := 'Install folder:' + NewLine + Space
    + RemoveBackslashUnlessRoot(WizardDirValue) + '\X\Modding' + NewLine + NewLine
    + 'Tools:' + NewLine
    + Space + 'AoWxBard (Music Tool)' + NewLine
    + Space + 'AoWxGen (Map Generator)' + NewLine
    + Space + 'AoWxImg (Image Tool)' + NewLine
    + Space + 'AoWxInk (Text Editor)' + NewLine
    + Space + 'AoWxQuest (Campaign Editor)' + NewLine;
end;

// ---------- install ----------

function PrepareToInstall(var NeedsRestart: Boolean): string;
begin
  Result := '';
  GTargetDir := RemoveBackslashUnlessRoot(WizardDirValue);

  // remove any stale copies left in the main folder by pre-406 releases
  // (both the old dot-prefixed names and any unprefixed copies)
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

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then begin
    StopTicker;
    StopInstallSfx;
  end;
end;
