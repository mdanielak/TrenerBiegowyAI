@echo off
setlocal EnableExtensions
chcp 65001 >nul
pushd "%~dp0"
if errorlevel 1 exit /b 1
title Trener Biegowy

rem Uruchamia dashboard i otwiera go w przegladarce.
rem TRENER_NO_BROWSER=1 nie otwiera przegladarki (testy).
set "URL=http://127.0.0.1:8001"

rem Juz dziala? Wtedy tylko otworz przegladarke, zamiast startowac drugi raz.
netstat -ano | findstr /R /C:"127.0.0.1:8001 .*LISTENING" >nul
if not errorlevel 1 (
    echo Trener Biegowy już działa - otwieram przeglądarkę.
    if not "%TRENER_NO_BROWSER%"=="1" start "" "%URL%"
    popd
    exit /b 0
)

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
    echo.
    echo  Aplikacja nie jest jeszcze zainstalowana na tym komputerze.
    echo  Wystarczy jednorazowo uruchomić plik install.bat.
    echo.
    if exist "install.bat" (
        choice /C TN /M "Uruchomić instalację teraz"
        if not errorlevel 2 (
            popd
            call "%~dp0install.bat"
            exit /b
        )
    )
    popd
    pause
    exit /b 1
)

echo.
echo  Trener Biegowy działa pod adresem %URL%
echo  Przeglądarka otworzy się za chwilę sama.
echo  Żeby zakończyć, zamknij to okno albo wciśnij Ctrl+C.
echo.
if not "%TRENER_NO_BROWSER%"=="1" start "" /min cmd /c "timeout /t 3 /nobreak >nul & start %URL%"
%PY_EXE% -m uvicorn api.main:app --host 127.0.0.1 --port 8001
set "EXIT_CODE=%ERRORLEVEL%"
popd
if not "%EXIT_CODE%"=="0" (
    echo.
    echo  Aplikacja zatrzymała się z błędem. Zrób zrzut tego okna, jeśli prosisz kogoś o pomoc.
    pause
)
exit /b %EXIT_CODE%