; Patch de atualização do Dispersio PDF: substitui apenas os arquivos alterados na pasta onde ele está instalado.
#include "common.iss"
#ifndef FromVersion
  #error "Informe /DFromVersion=x.y.z"
#endif

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
UsePreviousAppDir=yes
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=no
UninstallDisplayIcon={app}\{#AppExe}
SetupIconFile=..\assets\lumenpdf.ico
OutputDir=..\Saida
OutputBaseFilename=LumenPDF-Atualizacao-{#FromVersion}-para-{#AppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
CloseApplications=yes
CloseApplicationsFilter=*.exe
RestartApplications=yes
ChangesAssociations=yes
AppMutex=LumenPDF_Running
UpdateUninstallLogAppName=no

[Languages]
Name: "pt"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Messages]
WelcomeLabel1=Atualizar o [name]
WelcomeLabel2=Este assistente vai atualizar o Dispersio PDF da versão {#FromVersion} para a versão {#AppVersion}.%n%nApenas os arquivos alterados serão substituídos. Feche o Dispersio PDF antes de continuar.

[Files]
Source: "..\build\patch\files\*"; DestDir: "{app}"; Excludes: "LumenShell.dll"; Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist
Source: "..\build\patch\files\LumenShell.dll"; DestDir: "{app}"; Flags: ignoreversion restartreplace uninsrestartdelete skipifsourcedoesntexist

Source: "..\assets\pdfdoc.ico"; DestDir: "{app}"; Flags: ignoreversion

#include "..\build\patch\delete.iss"

[InstallDelete]
; atalhos com o nome antigo do programa
Type: files; Name: "{autoprograms}\{#OldAppName}.lnk"
Type: files; Name: "{autodesktop}\{#OldAppName}.lnk"
Type: files; Name: "{userprograms}\{#OldAppName}.lnk"
Type: files; Name: "{userdesktop}\{#OldAppName}.lnk"
Type: filesandordirs; Name: "{autoprograms}\{#OldAppName}"

[Icons]
; recria os atalhos com o identificador do app (ícone correto na barra de tarefas)
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"; AppUserModelID: "LumenPDF.App"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; AppUserModelID: "LumenPDF.App"; Check: DesktopIconExists

[Registry]
Root: HKA; Subkey: "Software\LumenPDF"; ValueType: string; ValueName: "Version"; ValueData: "{#AppVersion}"
#define AssocCond "Check: AssocInstalled"
#include "assoc.iss"
#include "shellext.iss"

[Run]
Filename: "{sys}\ie4uinit.exe"; Parameters: "-show"; Flags: runhidden nowait
Filename: "{app}\{#AppExe}"; Flags: nowait runasoriginaluser; Check: WizardSilent

[Code]
function ShellExtPresent(): Boolean;
begin
  { a LumenShell.dll só existe quando o build tinha o compilador C++ }
  Result := FileExists(ExpandConstant('{app}\LumenShell.dll'));
end;
function AssocInstalled(): Boolean;
begin
  Result := RegKeyExists(HKLM, 'Software\Classes\{#ProgId}') or RegKeyExists(HKCU, 'Software\Classes\{#ProgId}');
end;

var
  HadDesktopIcon: Integer;

function DesktopIconExists(): Boolean;
begin
  { decide antes de apagar o atalho com o nome antigo }
  if HadDesktopIcon = 0 then
  begin
    if FileExists(ExpandConstant('{autodesktop}\{#AppName}.lnk')) or FileExists(ExpandConstant('{autodesktop}\{#OldAppName}.lnk')) or
       FileExists(ExpandConstant('{userdesktop}\{#OldAppName}.lnk')) then HadDesktopIcon := 1 else HadDesktopIcon := 2;
  end;
  Result := HadDesktopIcon = 1;
end;

function InstalledVersion(): String;
begin
  { procura nas visões 64 e 32 bits do registro e na instalação por usuário }
  Result := '';
  if not RegQueryStringValue(HKLM64, '{#AppUninstKey}', 'DisplayVersion', Result) then
    if not RegQueryStringValue(HKLM32, '{#AppUninstKey}', 'DisplayVersion', Result) then
      RegQueryStringValue(HKCU, '{#AppUninstKey}', 'DisplayVersion', Result);
end;

function InitializeSetup(): Boolean;
var
  V: String;
begin
  Result := True;
  DesktopIconExists();   { guarda se havia atalho na área de trabalho antes de trocar o nome }
  V := InstalledVersion();
  if V = '' then
  begin
    MsgBox('O Dispersio PDF não está instalado neste computador.' #13#10 +
           'Use o instalador completo (LumenPDF-Setup).', mbError, MB_OK);
    Result := False;
  end
  else if (V <> '{#FromVersion}') and (V <> '{#AppVersion}') then
  begin
    MsgBox('Este patch atualiza a versão {#FromVersion}, mas a versão instalada é ' + V + '.' #13#10 +
           'Aplique os patches na ordem ou use o instalador completo da versão {#AppVersion}.', mbError, MB_OK);
    Result := False;
  end;
end;
