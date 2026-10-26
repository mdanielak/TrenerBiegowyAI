@echo off
setlocal
pushd "%~dp0"
if errorlevel 1 exit /b 1

set "PY_EXE="
if exist ".venv\Scripts\python.exe" set "PY_EXE=.venv\Scripts\python.exe"
if "%PY_EXE%"=="" (
    python -c "import uvicorn" >nul 2>&1
    if not errorlevel 1 set "PY_EXE=python"
)
if "%PY_EXE%"=="" (
    py -3.12 -c "import uvicorn" >nul 2>&1
    if not errorlevel 1 set "PY_EXE=py -3.12"
)
if "%PY_EXE%"=="" (
    py -c "import uvicorn" >nul 2>&1
    if not errorlevel 1 set "PY_EXE=py"
)

if "%PY_EXE%"=="" (
    echo Nie znaleziono srodowiska z uvicorn: brak .venv, conda ani python z pakietem uvicorn.
    echo Przygotuj srodowisko zgodnie z README.md lub zainstaluj zaleznosci:
    echo     pip install -r requirements.txt
    popd
    pause
    exit /b 1
)

echo Uzywany interpreter: %PY_EXE%
echo Dashboard: http://127.0.0.1:8001
echo Zatrzymanie: Ctrl+C
%PY_EXE% -m uvicorn api.main:app --host 127.0.0.1 --port 8001
set "EXIT_CODE=%ERRORLEVEL%"
popd
if not "%EXIT_CODE%"=="0" pause
exit /b %EXIT_CODE%
