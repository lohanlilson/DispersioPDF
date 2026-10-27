; Definições compartilhadas entre o instalador completo e os patches.
#define AppName      "Dispersio PDF"
; nome antigo (atalhos com esse nome são trocados pelos novos na atualização)
#define OldAppName   "Lumen PDF"
#define AppExe       "DispersioPDF.exe"
#ifndef AppPublisher
  #define AppPublisher "Lohan Lilson S. Lopes"
#endif
#ifndef AppEmail
  #define AppEmail "lohanlilson@gmail.com"
#endif
#define AppGuid      "792033AC-5BB3-4C63-8E0C-D8EFE3BA162C"
; "{{" é o escape do Inno para "{" nas seções [Setup]; no [Code] usar AppUninstKey
#define AppIdGuid    "{{" + AppGuid + "}"
#define AppUninstKey "Software\Microsoft\Windows\CurrentVersion\Uninstall\{" + AppGuid + "}_is1"
#define ProgId       "DispersioPDF.Document"
; identificadores do nome antigo: o tipo de arquivo antigo continua abrindo o programa novo
; (o Windows guarda a escolha do leitor padrão pelo ProgId e não deixa trocá-la sem o usuário)
#define OldAppExe    "LumenPDF.exe"
#define OldProgId    "LumenPDF.Document"
#define OldShellDll  "LumenShell.dll"
#define AppMutexes   "DispersioPDF_Running,LumenPDF_Running"
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\DispersioPDF"
#endif
