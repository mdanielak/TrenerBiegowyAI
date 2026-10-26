@echo off
setlocal
pushd "%~dp0"
if errorlevel 1 exit /b 1

if not exist ".venv\Scripts\python.exe" (
    echo Brak .venv\Scripts\python.exe. Przygotuj srodowisko Windows zgodnie z README.md.
    popd
    pause
    exit /b 1
)

echo Dashboard: http://127.0.0.1:8001
echo Zatrzymanie: Ctrl+C
".venv\Scripts\python.exe" -m uvicorn api.main:app --host 127.0.0.1 --port 8001
set "EXIT_CODE=%ERRORLEVEL%"
popd
if not "%EXIT_CODE%"=="0" pause
exit /b %EXIT_CODE%
