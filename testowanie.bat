@echo off
setlocal EnableExtensions
chcp 65001 >nul
title Trener Biegowy - testowanie

rem Testowa kopia aplikacji na zmyslonym tygodniu: dzis sroda, Garmin i AI udawane.
rem Inny dzien tygodnia: testowanie.bat --dzien czwartek
rem Inny biegacz: testowanie.bat --biegacz poczatkujacy   (albo regularny, zaawansowany; domyslnie regularny)
rem Kod kopiowany jest do katalogu tymczasowego, wiec prawdziwe dane (local, plany, .env) zostaja nietkniete.
rem Nie trafia do paczki wydania (export-ignore w .gitattributes).
set "REPO=%~dp0"
set "SANDBOX=%TEMP%\trener-testowanie"
set "URL=http://127.0.0.1:8002"

set "PY_EXE="
if exist "%REPO%.venv\Scripts\python.exe" set "PY_EXE=%REPO%.venv\Scripts\python.exe"
if "%PY_EXE%"=="" set "PY_EXE=python"

rem Stary serwer testowy pokazywalby stary kod i trzymal pliki piaskownicy.
netstat -ano | findstr /R /C:"127.0.0.1:8002 .*LISTENING" >nul
if not errorlevel 1 (
    echo.
    echo  Testowanie juz dziala w innym oknie. Zamknij je i uruchom testowanie.bat ponownie.
    echo.
    pause
    exit /b 1
)

rem Za kazdym razem od zera: poprzednie klikniecia nie psuja kolejnego testu.
if exist "%SANDBOX%" rmdir /s /q "%SANDBOX%"
mkdir "%SANDBOX%" || exit /b 1
rem Znacznik piaskownicy: bez niego testowanie.py odmawia startu i niczego nie zapisuje.
type nul > "%SANDBOX%\.testowanie-piaskownica"
for %%D in (ai api services trainer templates static scripts trener_biegowy_ai_assets) do (
    robocopy "%REPO%%%D" "%SANDBOX%\%%D" /E /XD __pycache__ /NFL /NDL /NJH /NJS /NP >nul
)
for %%F in (pyproject.toml runner_profile.example.json) do copy /Y "%REPO%%%F" "%SANDBOX%\" >nul
rem Publiczny przyklad strategii jako strategia testowa; prywatna strategia nie jest kopiowana.
mkdir "%SANDBOX%\training-plans\long-term"
copy /Y "%REPO%training-plans\long-term\przyklad-strategii.md" "%SANDBOX%\training-plans\long-term\half-marathon-2027.md" >nul

if not "%TRENER_NO_BROWSER%"=="1" start "" /min cmd /c "timeout /t 4 /nobreak >nul & start %URL%"
pushd "%SANDBOX%"
"%PY_EXE%" scripts\testowanie.py %*
set "EXIT_CODE=%ERRORLEVEL%"
popd
if not "%EXIT_CODE%"=="0" pause
exit /b %EXIT_CODE%
