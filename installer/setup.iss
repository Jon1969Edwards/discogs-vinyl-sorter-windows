; Inno Setup script for Spindle (Windows)
; Requires: dist/Spindle/ from PyInstaller

#define MyAppName "Spindle"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Jonathan C Edwards"
#define MyAppURL "https://github.com/Jon1969Edwards/discogs-vinyl-sorter-windows"
#define MyAppExeName "Spindle.exe"

[Setup]
; Stable AppId — do not change after first public release (breaks upgrades).
AppId={{F6AF4BB6-3E32-4AA0-A97D-F2914247AF95}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
LicenseFile=..\LICENSE
InfoBeforeFile=..\PRIVACY.md
OutputDir=..\dist\installer
OutputBaseFilename=Spindle-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile=..\assets\spindle.ico

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\Spindle\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\PRIVACY.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\TERMS.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Privacy Policy"; Filename: "{app}\PRIVACY.md"
Name: "{group}\Terms of Use"; Filename: "{app}\TERMS.md"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Messages]
SetupAppTitle=Install {#MyAppName}
SetupWindowCaption=Install {#MyAppName}
WelcomeLabel2=This will install {#MyAppName} on your computer.%n%nNot affiliated with Discogs.
