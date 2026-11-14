#!/usr/bin/env bash
# Uruchamia dashboard i otwiera go w przeglądarce (odpowiednik start.bat).
# TRENER_NO_BROWSER=1 nie otwiera przeglądarki (testy).
set -uo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")" || exit 1
source scripts/linux_common.sh

URL="http://127.0.0.1:8001"

# Pauza przed zamknięciem okna, gdy skrypt uruchomiono z menedżera plików.
pause() { [[ -t 0 ]] && read -rp "Naciśnij Enter, aby zamknąć..." _; }

open_url() {
    [[ "${TRENER_NO_BROWSER:-}" == "1" ]] && return
    command -v xdg-open >/dev/null 2>&1 || return
    ( sleep "$1"; xdg-open "$URL" >/dev/null 2>&1 ) &
}

# Już działa? Wtedy tylko otwórz przeglądarkę, zamiast startować drugi raz.
if port_in_use 8001; then
    echo "Trener Biegowy już działa - otwieram przeglądarkę."
    open_url 0
    exit 0
fi

# Python: najpierw .venv, potem systemowy z zainstalowanym uvicorn.
PY_EXE=()
if [[ -x "$VENV_PY" ]]; then
    PY_EXE=("$VENV_PY")
else
    for candidate in python3 python3.12 python; do
        if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c "import uvicorn" >/dev/null 2>&1; then
            PY_EXE=("$candidate")
            break
        fi
    done
fi

if [[ ${#PY_EXE[@]} -eq 0 ]]; then
    echo
    echo " Aplikacja nie jest jeszcze zainstalowana na tym komputerze."
    echo " Instalacja jest jednorazowa: tworzy .venv i pobiera potrzebne pakiety."
    echo
    answer=n
    [[ -t 0 ]] && read -rp "Uruchomić instalację teraz? [T/n] " answer
    if [[ -t 0 && ! "$answer" =~ ^[nN] ]]; then
        create_venv_if_missing
        install_requirements || { echo "Instalacja pakietów się nie udała." >&2; pause; exit 1; }
        ensure_local_profile
        PY_EXE=("$VENV_PY")
    else
        pause
        exit 1
    fi
fi

echo
echo " Trener Biegowy działa pod adresem $URL"
echo " Przeglądarka otworzy się za chwilę sama."
echo " Żeby zakończyć, zamknij to okno albo wciśnij Ctrl+C."
echo
open_url 3
# Przy starcie: pobranie nieaktualnych danych z zegarka i sprawdzenie, czy jest nowsza wersja.
export TRENER_STARTUP_TASKS=1
"${PY_EXE[@]}" -m uvicorn api.main:app --host 127.0.0.1 --port 8001
exit_code=$?
# 130 = zatrzymanie przez Ctrl+C, to nie jest błąd.
if [[ $exit_code -ne 0 && $exit_code -ne 130 ]]; then
    echo
    echo " Aplikacja zatrzymała się z błędem. Zrób zrzut tego okna, jeśli prosisz kogoś o pomoc."
    pause
fi
exit "$exit_code"
