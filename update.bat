@echo off
setlocal EnableExtensions
chcp 65001 >nul
pushd "%~dp0"
if errorlevel 1 exit /b 1
title Trener Biegowy - aktualizacja

rem Aktualizacja na dwuklik. Mozna tez przeciagnac pobrana paczke ZIP na ten plik.
rem Dane uzytkownika (local\, .env, plany, strategia) zostaja bez zmian.

echo.
echo  ==============================================
echo    Trener Biegowy - aktualizacja
echo  ==============================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo Aplikacja nie jest jeszcze zainstalowana. Uruchom najpierw install.bat.
    goto :fail
)
if not exist "local" mkdir "local"
set "LOG=%CD%\local\update.log"
echo Aktualizacja %DATE% %TIME% > "%LOG%"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\update.ps1" -ZipPath "%~1"
if errorlevel 1 goto :fail

echo.
echo Aktualizuję pakiety. To może potrwać kilka minut - nie zamykaj okna...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt >> "%LOG%" 2>&1
if errorlevel 1 (
    echo Aktualizacja pakietów się nie udała. Szczegóły: local\update.log
    goto :fail
)

echo.
echo  Gotowe! Uruchom aplikację skrótem "Trener Biegowy" albo plikiem start.bat.
echo.
if not "%TRENER_NONINTERACTIVE%"=="1" pause
popd
exit /b 0

:fail
echo.
if not "%TRENER_NONINTERACTIVE%"=="1" pause
popd
exit /b 1
