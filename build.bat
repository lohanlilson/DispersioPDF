@echo off
cd /d "%~dp0"
where py >nul 2>nul && (set PY=py) || (where python >nul 2>nul && (set PY=python) || (
    echo Python nao encontrado. Instale em python.org marcando "Add python.exe to PATH".
    pause & exit /b 1))

if not exist .venv (
    echo Criando ambiente virtual...
    %PY% -m venv .venv || (echo Falha ao criar o ambiente. & pause & exit /b 1)
)
call .venv\Scripts\activate.bat

echo Instalando dependencias...
python -m pip install --upgrade pip -q
python -m pip install -r requirements.txt pyinstaller -q || (echo Falha na instalacao. & pause & exit /b 1)

python -m pip install uharfbuzz -q 2>nul || echo (opcional) uharfbuzz indisponivel: carimbo usara a fonte padrao

python build.py %*
if errorlevel 1 (echo. & echo FALHOU - veja a mensagem acima. & pause & exit /b 1)
echo.
echo Arquivos prontos na pasta Saida.
start "" Saida
pause
