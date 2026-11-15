#!/usr/bin/env bash
# Aktualizuje kod i zależności w .venv. Nie dotyka local/, .env, planów ani danych HealthData.
# Instalacja z paczki ZIP: pobiera najnowsze wydanie z GitHuba (jak update.bat).
# Kopia repozytorium git: git pull bieżącej gałęzi.
set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
source scripts/linux_common.sh

usage() {
    cat <<EOF
Użycie: $0 [--zip PACZKA.zip] [--no-pull] [--dev] [--test] [--recreate-venv]

  --zip PACZKA     zaktualizuj z pobranej wcześniej paczki ZIP wydania
  --no-pull        nie aktualizuj kodu, zaktualizuj tylko zależności
  --dev            zainstaluj też requirements-dev.txt (pytest, httpx, Pillow)
  --test           po aktualizacji uruchom ./testowanie.sh (włącza --dev)
  --recreate-venv  usuń i utwórz od nowa środowisko .venv
EOF
}

pull=true
zip=''
dev=false
run_tests=false
recreate=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --zip) [[ $# -ge 2 ]] || die "Po --zip podaj ścieżkę do paczki."; zip=$(realpath -- "$2"); shift 2 ;;
        --no-pull) pull=false; shift ;;
        --dev) dev=true; shift ;;
        --test) run_tests=true; dev=true; shift ;;
        --recreate-venv) recreate=true; shift ;;
        -h|--help) usage; exit 0 ;;
        *) usage >&2; die "Nieznana opcja: $1" ;;
    esac
done

# 1. Kod
if $pull && { [[ -n "$zip" ]] || [[ ! -e .git ]]; }; then
    # Instalacja z paczki: ten sam sposób co update.bat — najnowsze wydanie, nie bieżący stan repozytorium.
    if port_in_use "${PORT:-8001}"; then
        die "Aplikacja jest uruchomiona. Zamknij ją (Ctrl+C w oknie start.sh) i uruchom aktualizację ponownie."
    fi
    create_venv_if_missing || true
    "$VENV_PY" scripts/update_release.py ${zip:+--zip "$zip"} || die "Aktualizacja kodu się nie udała - Twoje dane zostały bez zmian."
elif $pull; then
    command -v git >/dev/null 2>&1 || die "Brak polecenia git. Użyj --no-pull."
    git rev-parse --is-inside-work-tree >/dev/null 2>&1 || die "To nie jest repozytorium git. Użyj --no-pull."

    if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
        git status --short --untracked-files=no >&2
        die "Masz niezacommitowane zmiany w śledzonych plikach. Zacommituj je lub odłóż (git stash) i spróbuj ponownie."
    fi

    branch=$(git symbolic-ref --quiet --short HEAD) || die "HEAD nie wskazuje gałęzi (detached HEAD)."
    before=$(git rev-parse HEAD)
    info "Pobieram zmiany dla gałęzi $branch (to kopia repozytorium: stan gałęzi, nie tylko wydania)"
    git pull --ff-only || die "git pull --ff-only nie powiódł się (rozjechana historia lub brak dostępu do zdalnego repo)."
    after=$(git rev-parse HEAD)

    if [[ "$before" == "$after" ]]; then
        info "Kod jest aktualny"
    else
        info "Nowe commity:"
        git --no-pager log --oneline "$before..$after"
    fi
fi

# 2. Środowisko i zależności
if $recreate && [[ -d "$VENV_DIR" ]]; then
    info "Usuwam $VENV_DIR"
    rm -rf -- "$VENV_DIR"
fi
create_venv_if_missing || true
if $dev; then install_requirements dev; else install_requirements; fi

ensure_local_profile

# 3. Kontrola konfiguracji (bez synchronizacji z Garminem)
info "Sprawdzam konfigurację (trainer doctor)"
"$VENV_PY" -m trainer doctor || warn "doctor zgłosił problemy - zobacz komunikaty powyżej."

if port_in_use "${PORT:-8001}"; then
    warn "Dashboard działa na porcie ${PORT:-8001}. Zrestartuj go (Ctrl+C, potem ./start.sh), aby użyć nowej wersji."
fi

if $run_tests; then
    info "Uruchamiam testy"
    exec ./testowanie.sh
fi

info "Aktualizacja zakończona"
