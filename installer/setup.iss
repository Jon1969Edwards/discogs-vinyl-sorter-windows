; Inno Setup script for Vinyl Shelf Sorter (Windows)
; Requires: dist/DiscogsVinylSorter/ from PyInstaller

#define MyAppName "Vinyl Shelf Sorter"
#define MyAppVersion "1.0.0-beta.1"
#define MyAppPublisher "Vinyl Shelf Sorter"
#define MyAppURL "https://github.com/your-org/discogs-vinyl-sorter-windows"
#define MyAppExeName "DiscogsVinylSorter.exe"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
LicenseFile=..\LICENSE
InfoBeforeFile=..\PRIVACY.md
OutputDir=..\dist\installer
OutputBaseFilename=VinylShelfSorter-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
; SetupIconFile=..\assets\vinyl_shelf_sorter.ico

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\DiscogsVinylSorter\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
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
