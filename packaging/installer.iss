; Inno Setup script for EPUB-Forge.
; Built by .github/workflows/build-windows.yml after PyInstaller has produced
; dist\EPUB-Forge. Compile with:
;   ISCC.exe /DMyAppVersion=0.1.0 packaging\installer.iss

#ifndef MyAppVersion
  #define MyAppVersion "0.1.0"
#endif

#define MyAppName "EPUB F.O.R.G.E."
#define MyAppPublisher "Lukasz Kniotek"
#define MyAppURL "https://github.com/LuKi965/EPUB-F.O.R.G.E."
#define MyAppExeName "EPUB-Forge.exe"

[Setup]
AppId={{7B2F1C64-9E3D-4A57-B0C8-5D1E9A4F6C21}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
LicenseFile=..\LICENSE
OutputDir=..\dist\installer
OutputBaseFilename=EPUB-FORGE-{#MyAppVersion}-setup
SetupIconFile=epubforge.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; Spelled the pre-6.3 way on purpose: "x64compatible" is a hard error on older
; Inno Setup, whereas "x64" merely warns as deprecated on newer versions.
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
; Installing per-user keeps the whole thing UAC-free; the user can still elevate
; from the wizard if they want it available to everyone on the machine.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "polish"; MessagesFile: "compiler:Languages\Polish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "contextmenu"; Description: "Add ""Rebuild with EPUB F.O.R.G.E."" to the right-click menu for .epub files"; GroupDescription: "Shell integration:"; Flags: unchecked

[Files]
; The PyInstaller output already contains the Python runtime, Qt, the bundled
; JRE and EPUBCheck, so nothing else has to be installed on the target machine.
Source: "..\dist\EPUB-Forge\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
; Opens a prompt with the application on PATH for that window only. The
; command-line tool has features the window does not — `epubforge survey` above
; all — and telling somebody to type a path under AppData is not a usable
; instruction. Scoped to the session on purpose: editing the user's real PATH is
; a change to their machine, and this needs no such thing.
Name: "{group}\Wiersz polecen {#MyAppName}"; Filename: "{cmd}"; \
    Parameters: "/K set ""PATH={app};%PATH%"" && epubforge --version"; \
    WorkingDir: "{userdocs}"; Comment: "Command prompt with epubforge available"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; A shell verb, deliberately not a default file association: opening an EPUB
; still goes to whatever reader the user actually uses.
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.epub\shell\EpubForge"; \
    ValueType: string; ValueName: ""; ValueData: "Rebuild with EPUB F.O.R.G.E."; \
    Flags: uninsdeletekey; Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.epub\shell\EpubForge"; \
    ValueType: string; ValueName: "Icon"; ValueData: "{app}\{#MyAppExeName},0"; \
    Tasks: contextmenu
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.epub\shell\EpubForge\command"; \
    ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""; \
    Flags: uninsdeletekey; Tasks: contextmenu

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; \
    Flags: nowait postinstall skipifsilent
