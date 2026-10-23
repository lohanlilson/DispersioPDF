; Patch de atualização do Lumen PDF: substitui apenas os arquivos alterados na pasta onde ele está instalado.
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
PrivilegesRequiredOverridesAllowed=dialog
CloseApplications=yes
RestartApplications=yes
AppMutex=LumenPDF_Running
UpdateUninstallLogAppName=no

[Languages]
Name: "pt"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Messages]
WelcomeLabel1=Atualizar o [name]
WelcomeLabel2=Este assistente vai atualizar o Lumen PDF da versão {#FromVersion} para a versão {#AppVersion}.%n%nApenas os arquivos alterados serão substituídos. Feche o Lumen PDF antes de continuar.

[Files]
Source: "..\build\patch\files\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist

#include "..\build\patch\delete.iss"

[Registry]
Root: HKA; Subkey: "Software\LumenPDF"; ValueType: string; ValueName: "Version"; ValueData: "{#AppVersion}"

[Run]
Filename: "{app}\{#AppExe}"; Flags: nowait runasoriginaluser; Check: WizardSilent

[Code]
function InstalledVersion(): String;
var
  Key: String;
begin
  Result := '';
  Key := 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{#AppIdGuid}_is1';
  if not RegQueryStringValue(HKLM, Key, 'DisplayVersion', Result) then
    RegQueryStringValue(HKCU, Key, 'DisplayVersion', Result);
end;

function InitializeSetup(): Boolean;
var
  V: String;
begin
  Result := True;
  V := InstalledVersion();
  if V = '' then
  begin
    MsgBox('O Lumen PDF não está instalado neste computador.' #13#10 +
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
