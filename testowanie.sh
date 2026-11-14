#!/usr/bin/env bash
# Testowa kopia aplikacji na zmyślonym tygodniu: dziś środa, Garmin i AI udawane (odpowiednik testowanie.bat).
# Inny dzień tygodnia: ./testowanie.sh --dzien czwartek
# Inny biegacz: ./testowanie.sh --biegacz poczatkujacy   (albo regularny, zaawansowany; domyślnie regularny)
# Więcej w oknie: ./testowanie.sh --verbose   (zapytania HTTP, Garmin, synchronizacja, pełne zapytania do AI)
# Bez kasowania danych: ./testowanie.sh --zachowaj   (cel, plany i dziennik z poprzedniego testu zostają)
# Kod kopiowany jest do katalogu tymczasowego, więc prawdziwe dane (local, plany, .env) zostają nietknięte.
# TRENER_NO_BROWSER=1 nie otwiera przeglądarki.
set -uo pipefail

REPO=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd) || exit 1
SANDBOX="${TMPDIR:-/tmp}/trener-testowanie"
URL="http://127.0.0.1:8002"

source "$REPO/scripts/linux_common.sh"

pause() { [[ -t 0 ]] && read -rp "Naciśnij Enter, aby zamknąć..." _; }

if [[ -x "$REPO/.venv/bin/python" ]]; then
    PY_EXE="$REPO/.venv/bin/python"
else
    PY_EXE=python3
fi

# Stary serwer testowy pokazywałby stary kod i trzymał pliki piaskownicy.
if port_in_use 8002; then
    echo
    echo " Testowanie już działa w innym oknie. Zamknij je i uruchom ./testowanie.sh ponownie."
    echo
    pause
    exit 1
fi

# --zachowaj: dane z poprzedniego testu (cel, plany, dziennik) zostają, odświeża się tylko kod.
keep=false
for arg in "$@"; do
    [[ "${arg,,}" == "--zachowaj" ]] && keep=true
done
[[ -f "$SANDBOX/.testowanie-piaskownica" ]] || keep=false

# Bez --zachowaj za każdym razem od zera: poprzednie uruchomienia nie psują kolejnego testu.
if ! $keep; then
    # Usuwamy tylko katalog oznaczony jako piaskownica (albo nieistniejący).
    if [[ -e "$SANDBOX" && ! -f "$SANDBOX/.testowanie-piaskownica" ]]; then
        die "$SANDBOX istnieje, ale nie jest piaskownicą testowania. Usuń go ręcznie."
    fi
    rm -rf -- "$SANDBOX"
    mkdir -p -- "$SANDBOX" || exit 1
fi
# Znacznik piaskownicy: bez niego testowanie.py odmawia startu i niczego nie zapisuje.
: > "$SANDBOX/.testowanie-piaskownica"

# Kod w piaskownicy jest dokładną kopią repo; dane (local, training-plans, home, logs) są poza tymi katalogami.
for dir in ai api services trainer templates static scripts trener_biegowy_ai_assets; do
    [[ -d "$REPO/$dir" ]] || continue
    if command -v rsync >/dev/null 2>&1; then
        rsync -a --delete --exclude __pycache__ "$REPO/$dir/" "$SANDBOX/$dir/"
    else
        rm -rf -- "${SANDBOX:?}/$dir"
        cp -a -- "$REPO/$dir" "$SANDBOX/$dir"
        find "$SANDBOX/$dir" -type d -name __pycache__ -prune -exec rm -rf {} +
    fi
done
for file in pyproject.toml runner_profile.example.json; do
    cp -f -- "$REPO/$file" "$SANDBOX/"
done
# Publiczny przykład strategii jako strategia testowa; prywatna strategia nie jest kopiowana.
if ! $keep; then
    mkdir -p -- "$SANDBOX/training-plans/long-term"
    cp -f -- "$REPO/training-plans/long-term/przyklad-strategii.md" \
        "$SANDBOX/training-plans/long-term/strategia.md"
fi

if [[ "${TRENER_NO_BROWSER:-}" != "1" ]] && command -v xdg-open >/dev/null 2>&1; then
    ( sleep 4; xdg-open "$URL" >/dev/null 2>&1 ) &
fi

cd -- "$SANDBOX" || exit 1
"$PY_EXE" scripts/testowanie.py "$@"
exit_code=$?
if [[ $exit_code -ne 0 && $exit_code -ne 130 ]]; then
    pause
fi
exit "$exit_code"
