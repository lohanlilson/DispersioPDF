; Associação com arquivos PDF e verbos do Windows (abrir, imprimir, imprimir em…).
; Incluído pelo instalador (condição: tarefa assocpdf) e pelos patches (condição: associação já existente).
; Requer #define AssocCond antes do #include.

; Tipo de arquivo (ProgID)
Root: HKA; Subkey: "Software\Classes\{#ProgId}"; ValueType: string; ValueName: ""; ValueData: "Documento PDF"; Flags: uninsdeletekey; {#AssocCond}
Root: HKA; Subkey: "Software\Classes\{#ProgId}"; ValueType: string; ValueName: "FriendlyTypeName"; ValueData: "Documento PDF (Dispersio PDF)"; {#AssocCond}
Root: HKA; Subkey: "Software\Classes\{#ProgId}\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\pdfdoc.ico"; {#AssocCond}
Root: HKA; Subkey: "Software\Classes\{#ProgId}\shell"; ValueType: string; ValueName: ""; ValueData: "open"; {#AssocCond}
Root: HKA; Subkey: "Software\Classes\{#ProgId}\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; {#AssocCond}
; Imprimir (Outlook "Impressão rápida", botão direito > Imprimir, inclusive vários arquivos)
Root: HKA; Subkey: "Software\Classes\{#ProgId}\shell\print"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"; {#AssocCond}
Root: HKA; Subkey: "Software\Classes\{#ProgId}\shell\print\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" /p ""%1"""; {#AssocCond}
Root: HKA; Subkey: "Software\Classes\{#ProgId}\shell\printto\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" /pt ""%1"" ""%2"" ""%3"" ""%4"""; {#AssocCond}
Root: HKA; Subkey: "Software\Classes\.pdf\OpenWithProgids"; ValueType: string; ValueName: "{#ProgId}"; ValueData: ""; Flags: uninsdeletevalue; {#AssocCond}
; Quando escolhido pelo "Abrir com"
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "{#AppName}"; Flags: uninsdeletekey; {#AssocCond}
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\pdfdoc.ico"; {#AssocCond}
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".pdf"; ValueData: ""; {#AssocCond}
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; {#AssocCond}
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\shell\print"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"; {#AssocCond}
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\shell\print\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" /p ""%1"""; {#AssocCond}
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\shell\printto\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" /pt ""%1"" ""%2"" ""%3"" ""%4"""; {#AssocCond}
; Aparecer em Configurações > Aplicativos padrão
Root: HKA; Subkey: "Software\DispersioPDF\Capabilities"; ValueType: string; ValueName: "ApplicationName"; ValueData: "{#AppName}"; {#AssocCond}
Root: HKA; Subkey: "Software\DispersioPDF\Capabilities"; ValueType: string; ValueName: "ApplicationDescription"; ValueData: "Leitor e editor de PDF"; {#AssocCond}
Root: HKA; Subkey: "Software\DispersioPDF\Capabilities"; ValueType: string; ValueName: "ApplicationIcon"; ValueData: "{app}\{#AppExe},0"; {#AssocCond}
Root: HKA; Subkey: "Software\DispersioPDF\Capabilities\FileAssociations"; ValueType: string; ValueName: ".pdf"; ValueData: "{#ProgId}"; {#AssocCond}
Root: HKA; Subkey: "Software\RegisteredApplications"; ValueType: string; ValueName: "{#AppName}"; ValueData: "Software\DispersioPDF\Capabilities"; Flags: uninsdeletevalue; {#AssocCond}

; "Imprimir com Dispersio PDF" no botão direito de qualquer PDF (mesmo que outro programa seja o padrão)
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\DispersioPDF.Print"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Imprimir com Dispersio PDF"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\DispersioPDF.Print"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\{#AppExe},0"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\DispersioPDF.Print"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\DispersioPDF.Print\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" /p ""%1"""

; ——— nome antigo (Lumen PDF) ———
; o tipo de arquivo antigo e o "Abrir com" antigo passam a abrir o programa novo (preserva o leitor padrão escolhido)
Root: HKA; Subkey: "Software\Classes\{#OldProgId}"; ValueType: string; ValueName: "FriendlyTypeName"; ValueData: "Documento PDF (Dispersio PDF)"; Flags: uninsdeletekey; Check: OldProgIdExists
Root: HKA; Subkey: "Software\Classes\{#OldProgId}\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\pdfdoc.ico"; Check: OldProgIdExists
Root: HKA; Subkey: "Software\Classes\{#OldProgId}\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Check: OldProgIdExists
Root: HKA; Subkey: "Software\Classes\{#OldProgId}\shell\print\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" /p ""%1"""; Check: OldProgIdExists
Root: HKA; Subkey: "Software\Classes\{#OldProgId}\shell\printto\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" /pt ""%1"" ""%2"" ""%3"" ""%4"""; Check: OldProgIdExists
Root: HKA; Subkey: "Software\Classes\Applications\{#OldAppExe}"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "{#AppName}"; Flags: uninsdeletekey; Check: OldAppExeKeyExists
Root: HKA; Subkey: "Software\Classes\Applications\{#OldAppExe}\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""; Check: OldAppExeKeyExists
Root: HKA; Subkey: "Software\Classes\Applications\{#OldAppExe}\shell\print\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" /p ""%1"""; Check: OldAppExeKeyExists
Root: HKA; Subkey: "Software\Classes\Applications\{#OldAppExe}\shell\printto\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" /pt ""%1"" ""%2"" ""%3"" ""%4"""; Check: OldAppExeKeyExists
; registros antigos que ficariam duplicados
Root: HKA; Subkey: "Software\Classes\.pdf\OpenWithProgids"; ValueType: none; ValueName: "{#OldProgId}"; Flags: deletevalue
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\shell\LumenPDF.Print"; ValueType: none; Flags: deletekey
Root: HKA; Subkey: "Software\LumenPDF\Capabilities"; ValueType: none; Flags: deletekey
Root: HKA; Subkey: "Software\RegisteredApplications"; ValueType: none; ValueName: "{#OldAppName}"; Flags: deletevalue
Root: HKA; Subkey: "Software\Microsoft\Windows\CurrentVersion\App Paths\{#OldAppExe}"; ValueType: none; Flags: deletekey
