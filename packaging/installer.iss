; Installateur Windows (Inno Setup 6) — compilé par la CI après PyInstaller
#define AppName "Pirate Tracker"
#define AppVersion "3.0.1"

[Setup]
AppId={{6B7C3F9A-1E2D-4C5B-9A8F-PIRATETRACKER}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Pirate Tracker
DefaultDirName={localappdata}\Programs\PirateTracker
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=PirateTracker-Setup-{#AppVersion}
SetupIconFile=..\pirate_tracker\assets\icon.ico
UninstallDisplayIcon={app}\PirateTracker.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
; Mise à jour par-dessus une version installée : fermer l'application si elle tourne
CloseApplications=force
CloseApplicationsFilter=*.exe
RestartApplications=no

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "Créer une icône sur le Bureau"; GroupDescription: "Raccourcis :"
Name: "autostart"; Description: "Lancer Pirate Tracker au démarrage de Windows"; GroupDescription: "Options :"; Flags: unchecked

[Files]
Source: "..\dist\PirateTracker\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\PirateTracker.exe"
Name: "{group}\Désinstaller {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\PirateTracker.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "PirateTracker"; ValueData: """{app}\PirateTracker.exe"" --minimized"; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\PirateTracker.exe"; Description: "Lancer {#AppName}"; Flags: nowait postinstall skipifsilent

[Code]
// Avant d'installer : arrête Pirate Tracker (souvent caché près de l'horloge) et son lecteur de
// replays, sinon leurs fichiers sont verrouillés (« MoveFileEx a échoué ; code 5. Accès refusé »).
procedure StopProcess(const Name: String);
var
  ResultCode: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /T /IM ' + Name, '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  StopProcess('PirateTracker.exe');
  StopProcess('PirateReplayReader.exe');
  Sleep(1000);
  Result := '';
end;
