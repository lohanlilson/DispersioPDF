; Instalador completo do Dispersio PDF (Inno Setup 6)
#include "common.iss"

[Setup]
AppId={#AppIdGuid}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppContact={#AppEmail}
AppSupportURL=mailto:{#AppEmail}
AppPublisherURL=mailto:{#AppEmail}
AppCopyright=© 2026 {#AppPublisher}
VersionInfoCompany={#AppPublisher}
VersionInfoCopyright=© 2026 {#AppPublisher}
VersionInfoVersion={#AppVersion}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
AllowNoIcons=yes
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
SetupIconFile=..\assets\dispersio.ico
OutputDir=..\Saida
OutputBaseFilename=DispersioPDF-Setup-{#AppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
DisableDirPage=no
ChangesAssociations=yes
CloseApplications=yes
; só fecha o próprio programa (nunca o Explorador, que pode estar usando a DispersioShell.dll)
CloseApplicationsFilter=*.exe
RestartApplications=no
AppMutex={#AppMutexes}
MinVersion=10.0

[Languages]
Name: "pt"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na Área de Trabalho"; GroupDescription: "Atalhos:"
Name: "assocpdf"; Description: "Registrar o Dispersio PDF para abrir arquivos .pdf"; GroupDescription: "Integração com o Windows:"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Excludes: "DispersioShell.dll"; Flags: ignoreversion recursesubdirs createallsubdirs
; a DLL pode estar em uso pelo Explorador: se estiver, é substituída na próxima reinicialização
Source: "{#SourceDir}\DispersioShell.dll"; DestDir: "{app}"; Flags: ignoreversion restartreplace uninsrestartdelete skipifsourcedoesntexist
Source: "..\assets\pdfdoc.ico"; DestDir: "{app}"; Flags: ignoreversion

[InstallDelete]
; atalhos com o nome antigo do programa
Type: files; Name: "{autoprograms}\{#OldAppName}.lnk"
Type: files; Name: "{autodesktop}\{#OldAppName}.lnk"
Type: files; Name: "{userprograms}\{#OldAppName}.lnk"
Type: files; Name: "{userdesktop}\{#OldAppName}.lnk"
Type: filesandordirs; Name: "{autoprograms}\{#OldAppName}"
; programa e extensão com o nome antigo
Type: files; Name: "{app}\{#OldAppExe}"
Type: files; Name: "{app}\{#OldShellDll}"

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"; AppUserModelID: "DispersioPDF.App"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; AppUserModelID: "DispersioPDF.App"; Tasks: desktopicon

[Registry]
; Informações do programa (usadas pelos patches)
Root: HKA; Subkey: "Software\DispersioPDF"; ValueType: string; ValueName: "InstallPath"; ValueData: "{app}"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\DispersioPDF"; ValueType: string; ValueName: "Version"; ValueData: "{#AppVersion}"
Root: HKA; Subkey: "Software\Microsoft\Windows\CurrentVersion\App Paths\{#AppExe}"; ValueType: string; ValueName: ""; ValueData: "{app}\{#AppExe}"; Flags: uninsdeletekey
#define AssocCond "Tasks: assocpdf"
#include "assoc.iss"
#include "shellext.iss"

[Run]
Filename: "{app}\{#AppExe}"; Parameters: "--set-default"; Description: "Definir o Dispersio PDF como leitor de PDF padrão"; Flags: nowait postinstall skipifsilent; Tasks: assocpdf
Filename: "{app}\{#AppExe}"; Description: "Abrir o Dispersio PDF agora"; Flags: nowait postinstall skipifsilent unchecked

Filename: "{app}\{#AppExe}"; Flags: nowait runasoriginaluser; Check: WizardSilent

Filename: "{sys}\ie4uinit.exe"; Parameters: "-show"; Flags: runhidden nowait; StatusMsg: "Atualizando ícones…"

[UninstallDelete]
Type: filesandordirs; Name: "{app}\_internal"

[Code]
function OldProgIdExists(): Boolean;
begin
  Result := RegKeyExists(HKLM, 'Software\Classes\{#OldProgId}') or RegKeyExists(HKCU, 'Software\Classes\{#OldProgId}');
end;
function OldAppExeKeyExists(): Boolean;
begin
  Result := RegKeyExists(HKLM, 'Software\Classes\Applications\{#OldAppExe}') or RegKeyExists(HKCU, 'Software\Classes\Applications\{#OldAppExe}');
end;
function ShellExtPresent(): Boolean;
begin
  { a DispersioShell.dll só existe quando o build tinha o compilador C++ }
  Result := FileExists(ExpandConstant('{app}\DispersioShell.dll'));
end;
