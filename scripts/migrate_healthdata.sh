#!/usr/bin/env bash
# Kopiuje lokalne dane HealthData na Linux; nie synchronizuje ich z Garminem.
set -euo pipefail

usage() {
    printf '%s\n' "Użycie: $0 --source KATALOG [--target KATALOG] [--include-backups] [--dry-run]"
    printf '%s\n' 'Kopiuje HealthData na Linux. Domyślnie pomija pliki i katalogi *.bak*.'
}

source_dir=''
target_dir="$HOME/HealthData"
include_backups=false
dry_run=false

while [ "$#" -gt 0 ]; do
    case "$1" in
        --source)
            [ "$#" -ge 2 ] || { printf '%s\n' 'Brak wartości po --source.' >&2; exit 2; }
            source_dir="$2"
            shift 2
            ;;
        --target)
            [ "$#" -ge 2 ] || { printf '%s\n' 'Brak wartości po --target.' >&2; exit 2; }
            target_dir="$2"
            shift 2
            ;;
        --include-backups) include_backups=true; shift ;;
        --dry-run) dry_run=true; shift ;;
        --help|-h) usage; exit 0 ;;
        *) printf 'Nieznana opcja: %s\n' "$1" >&2; usage >&2; exit 2 ;;
    esac
done

[ -n "$source_dir" ] || { printf '%s\n' 'Wymagana jest opcja --source KATALOG.' >&2; usage >&2; exit 2; }
[ -d "$source_dir" ] || { printf 'Katalog źródłowy nie istnieje: %s\n' "$source_dir" >&2; exit 1; }

source_path=$(realpath -e "$source_dir")
target_path=$(realpath -m "$target_dir")

if [ "$source_path" = "$target_path" ]; then
    printf '%s\n' 'Źródło i cel wskazują tę samą ścieżkę. Przerwano, aby nie kopiować danych na siebie.' >&2
    exit 1
fi

if [ -d "$source_path/DBs" ]; then
    db_dir='DBs'
elif [ -d "$source_path/dbs" ]; then
    db_dir='dbs'
    printf '%s\n' 'OSTRZEŻENIE: znaleziono tylko małe „dbs”. Linux rozróżnia wielkość liter; zalecany jest katalog „DBs”.' >&2
else
    printf 'Katalog źródłowy nie wygląda jak HealthData: brakuje %s/DBs lub %s/dbs.\n' "$source_path" "$source_path" >&2
    exit 1
fi

# Sprawdź najbliższy istniejący katalog, zanim cokolwiek zostanie utworzone.
existing_parent="$target_path"
while [ ! -e "$existing_parent" ]; do
    existing_parent=$(dirname "$existing_parent")
done
if git -C "$existing_parent" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    printf 'Cel znajduje się w drzewie roboczym Git: %s\n' "$target_path" >&2
    printf '%s\n' 'Wybierz katalog poza repozytorium, aby nie ryzykować dodania danych zdrowotnych do Git.' >&2
    exit 1
fi

printf 'Źródło: %s\nCel: %s\nWykryty katalog baz: %s\n' "$source_path" "$target_path" "$db_dir"
printf '%s\n' 'Wolne miejsce w systemie plików celu:'
df -h "$existing_parent"

if [ "$dry_run" = true ]; then
    printf '%s\n' 'TRYB PODGLĄDU: żadne pliki nie zostaną skopiowane.'
fi

copy_with_cp() {
    local item base child relative
    item="$1"
    base=$(basename "$item")
    if [ "$include_backups" = false ] && [[ "$base" == *'.bak'* ]]; then
        return
    fi
    relative=${item#"$source_path"/}
    if [ "$db_dir" = 'dbs' ]; then
        case "$relative" in
            dbs) relative='DBs' ;;
            dbs/*) relative="DBs/${relative#dbs/}" ;;
        esac
    fi
    if [ -d "$item" ] && [ ! -L "$item" ]; then
        if [ "$dry_run" = false ]; then
            mkdir -p "$target_path/$relative"
        fi
        shopt -s nullglob dotglob
        for child in "$item"/*; do
            copy_with_cp "$child"
        done
        shopt -u nullglob dotglob
    elif [ "$dry_run" = false ]; then
        mkdir -p "$target_path/$(dirname "$relative")"
        cp -a "$item" "$target_path/$relative"
    fi
}

if command -v rsync >/dev/null 2>&1; then
    rsync_args=(-a --human-readable --info=progress2)
    if [ "$include_backups" = false ]; then
        rsync_args+=(--exclude='*.bak*')
    fi
    if [ "$dry_run" = true ]; then
        rsync_args+=(--dry-run)
    fi
    if [ "$dry_run" = false ]; then
        mkdir -p "$target_path"
    fi
    if [ "$db_dir" = 'dbs' ]; then
        rsync "${rsync_args[@]}" --exclude='dbs/' "$source_path/" "$target_path/"
        rsync "${rsync_args[@]}" "$source_path/dbs/" "$target_path/DBs/"
    else
        rsync "${rsync_args[@]}" "$source_path/" "$target_path/"
    fi
else
    printf '%s\n' 'rsync nie jest dostępny; używam zachowawczego kopiowania cp -a.' >&2
    if [ "$dry_run" = false ]; then
        mkdir -p "$target_path"
    fi
    shopt -s nullglob dotglob
    for entry in "$source_path"/*; do
        copy_with_cp "$entry"
    done
    shopt -u nullglob dotglob
fi

if [ "$dry_run" = false ]; then
    printf '%s\n' 'Rozmiar i liczba plików w wyniku:'
    du -sh "$target_path"
    find "$target_path" -type f | wc -l
fi

printf '%s\n' "Dodaj do profilu powłoki: export HEALTH_DATA_DIR=$(printf '%q' "$target_path")"
printf '%s\n' 'Katalog ~/.GarminDb nie został skopiowany i nie zawiera go migracja. Zalecane jest ponowne logowanie do Garmin na Linuxie.'
printf '%s\n' 'Następnie uruchom: python -m trainer doctor'
