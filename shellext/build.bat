@echo off
rem Compila a DispersioShell.dll (miniaturas e painel de visualização do Explorador) e o programa de teste.
rem Requer o Visual Studio Build Tools (C++). Chamado pelo build.py; também pode ser rodado direto num
rem "Developer Command Prompt".
setlocal
set OUT=%~dp0..\build\shellext
if not exist "%OUT%" mkdir "%OUT%"
cl /nologo /LD /EHsc /std:c++20 /O2 /MT /W3 /DUNICODE /D_UNICODE "%~dp0DispersioShell.cpp" /Fe:"%OUT%\DispersioShell.dll" /Fo:"%OUT%\\" /link /DEF:"%~dp0DispersioShell.def" || exit /b 1
cl /nologo /EHsc /std:c++20 /O2 /MT /DUNICODE /D_UNICODE "%~dp0test_shellext.cpp" /Fe:"%OUT%\test_shellext.exe" /Fo:"%OUT%\\" || exit /b 1
echo DispersioShell.dll gerada em %OUT%
