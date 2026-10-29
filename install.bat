@echo off
setlocal EnableExtensions
chcp 65001 >nul
pushd "%~dp0"
if errorlevel 1 exit /b 1
title Trener Biegowy - instalacja

rem Instalacja na dwuklik: Python, srodowisko .venv, pakiety, skrot na pulpicie.
rem TRENER_NONINTERACTIVE=1 pomija pytania (testy, instalacja automatyczna).

echo.
echo  ==============================================
echo    Trener Biegowy - instalacja
echo  ==============================================
echo.

if not exist "local" mkdir "local"
set "LOG=%CD%\local\install.log"
echo Instalacja %DATE% %TIME% > "%LOG%"

rem --- 1. Python 3.11 lub nowszy -------------------------------------------
call :find_python
if not defined PY (
    echo [1/4] Nie znalazłem Pythona 3.11 lub nowszego.
    where winget >nul 2>&1
    if errorlevel 1 (
        echo.
        echo       Zainstaluj Pythona ze strony https://www.python.org/downloads/
        echo       i zaznacz w instalatorze "Add python.exe to PATH".
        echo       Potem uruchom install.bat jeszcze raz.
        goto :fail
    )
    if "%TRENER_NONINTERACTIVE%"=="1" goto :fail
    choice /C TN /M "      Zainstalować Pythona 3.12 automatycznie (Microsoft winget)"
    if errorlevel 2 goto :fail
    echo       Instaluję Pythona - zaakceptuj okno uprawnień, jeśli się pojawi...
    winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements >> "%LOG%" 2>&1
    call :find_python
    if not defined PY (
        echo       Python się zainstalował, ale ten terminal go jeszcze nie widzi.
        echo       Zamknij to okno i uruchom install.bat ponownie.
        goto :fail
    )
)
echo [1/4] Python: %PYVER%

rem --- 2. Srodowisko .venv -------------------------------------------------
if exist ".venv\Scripts\python.exe" (
    echo [2/4] Środowisko .venv już istnieje - zaktualizuję pakiety.
) else (
    echo [2/4] Tworzę środowisko aplikacji .venv...
    %PY% -m venv .venv >> "%LOG%" 2>&1
    if errorlevel 1 (
        echo       Nie udało się utworzyć środowiska .venv.
        goto :fail_log
    )
)

rem --- 3. Pakiety -----------------------------------------------------------
echo [3/4] Instaluję pakiety. To może potrwać kilka minut - nie zamykaj okna...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check --upgrade pip >> "%LOG%" 2>&1
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt -c constraints.txt >> "%LOG%" 2>&1
if errorlevel 1 (
    echo       Instalacja pakietów się nie udała. Najczęstsza przyczyna: brak internetu.
    goto :fail_log
)
".venv\Scripts\python.exe" -c "import fastapi, uvicorn, garminconnect, garmindb" >> "%LOG%" 2>&1
if errorlevel 1 (
    echo       Pakiety są niekompletne.
    goto :fail_log
)

rem --- 4. Skrot na pulpicie ---------------------------------------------------
if "%TRENER_NO_SHORTCUT%"=="1" (
    echo [4/4] Pomijam skrót na pulpicie.
) else (
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
      "$d=[Environment]::GetFolderPath('Desktop'); $s=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $d 'Trener Biegowy.lnk')); $s.TargetPath='%CD%\start.bat'; $s.WorkingDirectory='%CD%'; $s.IconLocation='%CD%\static\app.ico'; $s.Description='Trener Biegowy - dashboard'; $s.Save()" >> "%LOG%" 2>&1
    if errorlevel 1 (
        echo [4/4] Nie udało się utworzyć skrótu - uruchamiaj aplikację plikiem start.bat.
    ) else (
        echo [4/4] Na pulpicie jest skrót "Trener Biegowy".
    )
)

echo.
echo  Gotowe! Aplikację uruchamiasz skrótem "Trener Biegowy" albo plikiem start.bat.
echo  Przy pierwszym uruchomieniu przeglądarka poprowadzi Cię przez połączenie zegarka.
echo.
if "%TRENER_NONINTERACTIVE%"=="1" goto :done
choice /C TN /M "Uruchomić aplikację teraz"
if errorlevel 2 goto :done
popd
call "%~dp0start.bat"
exit /b 0

:done
popd
exit /b 0

:fail_log
echo       Szczegóły zapisałem w pliku: %LOG%
:fail
echo.
echo  Instalacja nie została dokończona.
if not "%TRENER_NONINTERACTIVE%"=="1" pause
popd
exit /b 1

rem --- Szuka Pythona >= 3.11 (pomija atrape ze Sklepu Windows) --------------
:find_python
set "PY="
set "PYVER="
for %%C in ("py -3.13" "py -3.12" "py -3.11" "python") do if not defined PY call :try_python %%~C
for %%P in ("%LOCALAPPDATA%\Programs\Python\Python313\python.exe" "%LOCALAPPDATA%\Programs\Python\Python312\python.exe") do (
    if not defined PY if exist "%%~P" call :try_python "%%~P"
)
exit /b 0

:try_python
%* -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
if errorlevel 1 exit /b 0
set "PY=%*"
for /f "delims=" %%V in ('call %* -c "import platform; print(platform.python_version())"') do set "PYVER=%%V"
exit /b 0
