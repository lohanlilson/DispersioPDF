; Requer a função ShellExtPresent no [Code] de quem inclui este arquivo.
; Extensões do Explorador (LumenShell.dll): miniatura dos .pdf com a primeira página e painel de visualização.
; Ficam registradas no tipo de arquivo do Dispersio PDF e, como alternativa, para qualquer .pdf
; (SystemFileAssociations tem prioridade menor: não substitui o que outro leitor já registrou no .pdf).
#define ThumbClsid   "{{6E1F4D3A-8C2B-4A57-9B1E-3D5C7A9F0B21}"
#define PreviewClsid "{{7F2A5E4B-9D3C-4B68-AC2F-4E6D8B0A1C32}"
#define ThumbIID     "{{e357fccd-a995-4576-b01f-234630154e96}"
#define PreviewIID   "{{8895b1c6-b41f-4c1c-a562-0d564250836f}"
#define PrevHostApp  "{{6d2b5079-2f0b-48dd-ab7f-97cec514d30b}"

Root: HKA; Subkey: "Software\Classes\CLSID\{#ThumbClsid}"; ValueType: string; ValueName: ""; ValueData: "Dispersio PDF - miniaturas"; Flags: uninsdeletekey; Check: ShellExtPresent
Root: HKA; Subkey: "Software\Classes\CLSID\{#ThumbClsid}\InprocServer32"; ValueType: string; ValueName: ""; ValueData: "{app}\LumenShell.dll"; Check: ShellExtPresent
Root: HKA; Subkey: "Software\Classes\CLSID\{#ThumbClsid}\InprocServer32"; ValueType: string; ValueName: "ThreadingModel"; ValueData: "Apartment"; Check: ShellExtPresent
Root: HKA; Subkey: "Software\Classes\CLSID\{#PreviewClsid}"; ValueType: string; ValueName: ""; ValueData: "Dispersio PDF - visualização"; Flags: uninsdeletekey; Check: ShellExtPresent
Root: HKA; Subkey: "Software\Classes\CLSID\{#PreviewClsid}"; ValueType: string; ValueName: "DisplayName"; ValueData: "Dispersio PDF"; Check: ShellExtPresent
Root: HKA; Subkey: "Software\Classes\CLSID\{#PreviewClsid}"; ValueType: string; ValueName: "AppID"; ValueData: "{#PrevHostApp}"; Check: ShellExtPresent
Root: HKA; Subkey: "Software\Classes\CLSID\{#PreviewClsid}\InprocServer32"; ValueType: string; ValueName: ""; ValueData: "{app}\LumenShell.dll"; Check: ShellExtPresent
Root: HKA; Subkey: "Software\Classes\CLSID\{#PreviewClsid}\InprocServer32"; ValueType: string; ValueName: "ThreadingModel"; ValueData: "Apartment"; Check: ShellExtPresent
Root: HKLM; Subkey: "Software\Microsoft\Windows\CurrentVersion\PreviewHandlers"; ValueType: string; ValueName: "{#PreviewClsid}"; ValueData: "Dispersio PDF"; Flags: uninsdeletevalue; Check: ShellExtPresent

Root: HKA; Subkey: "Software\Classes\{#ProgId}\ShellEx\{#ThumbIID}"; ValueType: string; ValueName: ""; ValueData: "{#ThumbClsid}"; Flags: uninsdeletekey; Check: ShellExtPresent
Root: HKA; Subkey: "Software\Classes\{#ProgId}\ShellEx\{#PreviewIID}"; ValueType: string; ValueName: ""; ValueData: "{#PreviewClsid}"; Flags: uninsdeletekey; Check: ShellExtPresent
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\ShellEx\{#ThumbIID}"; ValueType: string; ValueName: ""; ValueData: "{#ThumbClsid}"; Flags: uninsdeletekey; Check: ShellExtPresent
Root: HKA; Subkey: "Software\Classes\SystemFileAssociations\.pdf\ShellEx\{#PreviewIID}"; ValueType: string; ValueName: ""; ValueData: "{#PreviewClsid}"; Flags: uninsdeletekey; Check: ShellExtPresent
