#ifndef AtraAppId
  #define AtraAppId "Atra.GameTranslator"
#endif
#define AtraVersion "1.0.1"

[Setup]
AppId={#AtraAppId}
AppName=Atra
AppVersion={#AtraVersion}
AppPublisher=Ata Turukmen
DefaultDirName={localappdata}\Programs\Atra
UsePreviousAppDir=no
DisableDirPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist\store-submission
OutputBaseFilename=AtraSetup
SetupIconFile=..\assets\app_icon.ico
Compression=lzma2
SolidCompression=yes
CloseApplications=no
RestartApplications=no
UninstallDisplayIcon={app}\{code:VersionDir}\Atra.exe

[Files]
Source: "..\dist\Atra\*"; DestDir: "{app}\{code:VersionDir}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Atra"; Filename: "{app}\{code:VersionDir}\Atra.exe"; WorkingDir: "{app}\{code:VersionDir}"
Name: "{autodesktop}\Atra"; Filename: "{app}\{code:VersionDir}\Atra.exe"; WorkingDir: "{app}\{code:VersionDir}"; Tasks: desktopicon

[Tasks]
Name: desktopicon; Description: "Masaüstü kısayolu oluştur"; Flags: unchecked

[Code]
var InstallSubdir: String;

function VersionDir(Param: String): String;
var Candidate: String;
    N: Integer;
begin
  if InstallSubdir = '' then begin
    Candidate := 'app-{#AtraVersion}-' + GetDateTimeString('yyyymmdd-hhnnss', '-', ':');
    InstallSubdir := Candidate;
    N := 0;
    while DirExists(ExpandConstant('{app}\') + InstallSubdir) do begin
      N := N + 1;
      InstallSubdir := Candidate + '-' + IntToStr(N);
    end;
  end;
  Result := InstallSubdir;
end;
