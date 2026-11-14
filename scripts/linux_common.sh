# Wspólne funkcje dla start.sh, update.sh i testowanie.sh (Linux/macOS).
# Plik jest dołączany przez `source`, nie uruchamiaj go bezpośrednio.

VENV_DIR=".venv"
VENV_PY="$VENV_DIR/bin/python"

info() { printf '==> %s\n' "$*"; }
warn() { printf 'UWAGA: %s\n' "$*" >&2; }
die()  { printf 'BŁĄD: %s\n' "$*" >&2; exit 1; }

# Wybiera interpreter do utworzenia .venv: wersja z .python-version, potem python3.
find_system_python() {
    local wanted=''
    if [[ -f .python-version ]]; then
        wanted=$(cut -d. -f1,2 < .python-version | tr -d '[:space:]')
    fi
    local candidate
    for candidate in ${wanted:+"python$wanted"} python3; do
        if command -v "$candidate" >/dev/null 2>&1; then
            command -v "$candidate"
            return 0
        fi
    done
    return 1
}

# Tworzy .venv, jeśli go brakuje. Zwraca 0, gdy środowisko zostało utworzone teraz.
create_venv_if_missing() {
    [[ -x "$VENV_PY" ]] && return 1
    local py
    py=$(find_system_python) || die "Nie znaleziono python3. Zainstaluj Pythona 3 (oraz pakiet python3-venv)."
    info "Tworzę środowisko $VENV_DIR ($("$py" --version 2>&1))"
    "$py" -m venv "$VENV_DIR" || die "Nie udało się utworzyć $VENV_DIR. Na Debianie/Ubuntu zainstaluj pakiet python3-venv."
    return 0
}

# Instaluje zależności. Argument "dev" dokłada requirements-dev.txt.
install_requirements() {
    # constraints.txt przypina wersje, na których aplikacja jest przetestowana (jak update.bat).
    local pin=()
    [[ -f constraints.txt ]] && pin=(-c constraints.txt)
    info "Instaluję zależności z requirements.txt"
    "$VENV_PY" -m pip install --quiet --disable-pip-version-check -r requirements.txt "${pin[@]}"
    if [[ "${1:-}" == "dev" ]]; then
        info "Instaluję zależności deweloperskie z requirements-dev.txt"
        "$VENV_PY" -m pip install --quiet --disable-pip-version-check -r requirements-dev.txt "${pin[@]}"
    fi
}

# Kopiuje przykładowy profil do local/profile.json, jeśli go brakuje (nigdy nie nadpisuje).
ensure_local_profile() {
    mkdir -p local
    if [[ ! -f local/profile.json && -f runner_profile.example.json ]]; then
        cp runner_profile.example.json local/profile.json
        info "Utworzono local/profile.json ze wzoru. Uzupełnij go: $VENV_PY -m trainer setup"
    fi
}

# Zwraca 0, gdy coś nasłuchuje na podanym porcie TCP lokalnie.
port_in_use() {
    local port="$1"
    if command -v ss >/dev/null 2>&1; then
        ss -ltnH "sport = :$port" 2>/dev/null | grep -q .
    elif command -v lsof >/dev/null 2>&1; then
        lsof -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
    else
        (exec 3<>"/dev/tcp/127.0.0.1/$port") 2>/dev/null
    fi
}
