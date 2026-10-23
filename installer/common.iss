; Definições compartilhadas entre o instalador completo e os patches.
#define AppName      "Lumen PDF"
#define AppExe       "LumenPDF.exe"
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
#define ProgId       "LumenPDF.Document"
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\LumenPDF"
#endif
