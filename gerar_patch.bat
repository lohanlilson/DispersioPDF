@echo off
cd /d "%~dp0"
echo Versoes ja geradas (pasta releases):
dir /b releases 2>nul
echo.
echo Antes de continuar, aumente __version__ em dispersio\__init__.py.
set /p FROM=Gerar patch a partir de qual versao instalada? 
if "%FROM%"=="" exit /b 1
call build.bat --patch-from %FROM%
